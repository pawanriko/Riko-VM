"""Tests for the assembler (spec section 6), including the golden
encoding tests: every ISA row must assemble to exactly the bytes in
the spec's table, and the decoder must read those bytes back to the
same instruction. This is the anti-drift lock between assembler and
decoder."""

import unittest

from rikovm.assembler import assemble
from rikovm.decoder import decode
from rikovm.errors import AssembleError
from rikovm.memory import Memory

# (source line, exact expected bytes) -- one row per ISA instruction.
GOLDEN = [
    ("HALT", bytes([0x00])),
    ("NOP", bytes([0x01])),
    ("MOV R1, R2", bytes([0x02, 0x01, 0x02])),
    ("LDI R3, 0x1234", bytes([0x03, 0x03, 0x34, 0x12])),
    ("LOAD R1, 0x2000", bytes([0x04, 0x01, 0x00, 0x20])),
    ("STORE R1, 0x2000", bytes([0x05, 0x01, 0x00, 0x20])),
    ("ADD R3, R1, R2", bytes([0x06, 0x03, 0x01, 0x02])),
    ("SUB R3, R1, R2", bytes([0x07, 0x03, 0x01, 0x02])),
    ("MUL R3, R1, R2", bytes([0x08, 0x03, 0x01, 0x02])),
    ("DIV R3, R1, R2", bytes([0x09, 0x03, 0x01, 0x02])),
    ("AND R3, R1, R2", bytes([0x0A, 0x03, 0x01, 0x02])),
    ("OR R3, R1, R2", bytes([0x0B, 0x03, 0x01, 0x02])),
    ("XOR R3, R1, R2", bytes([0x0C, 0x03, 0x01, 0x02])),
    ("NOT R3, R1", bytes([0x0D, 0x03, 0x01])),
    ("SHL R3, R1, R2", bytes([0x0E, 0x03, 0x01, 0x02])),
    ("SHR R3, R1, R2", bytes([0x0F, 0x03, 0x01, 0x02])),
    ("CMP R1, R2", bytes([0x10, 0x01, 0x02])),
    ("TEST R1, R2", bytes([0x11, 0x01, 0x02])),
    ("JMP 0x1234", bytes([0x12, 0x34, 0x12])),
    ("JZ 0x1234", bytes([0x13, 0x34, 0x12])),
    ("JNZ 0x1234", bytes([0x14, 0x34, 0x12])),
    ("JC 0x1234", bytes([0x15, 0x34, 0x12])),
    ("CALL 0x1234", bytes([0x16, 0x34, 0x12])),
    ("RET", bytes([0x17])),
    ("PUSH R1", bytes([0x18, 0x01])),
    ("POP R1", bytes([0x19, 0x01])),
]


class TestGoldenEncodings(unittest.TestCase):
    def test_every_isa_row_assembles_to_exact_bytes(self):
        self.assertEqual(len(GOLDEN), 26)  # the full v1 ISA
        for source, expected in GOLDEN:
            with self.subTest(source=source):
                self.assertEqual(assemble(source), expected)

    def test_decoder_reads_assembled_bytes_back(self):
        for source, expected in GOLDEN:
            with self.subTest(source=source):
                mem = Memory()
                mem.load(expected, 0)
                instr = decode(mem, 0)
                self.assertEqual(instr.mnemonic, source.split()[0])
                self.assertEqual(instr.length, len(expected))


class TestAssemblerFeatures(unittest.TestCase):
    def test_acceptance_program(self):
        source = "LDI R1, 7\nLDI R2, 5\nADD R3, R1, R2\nHALT\n"
        self.assertEqual(
            assemble(source),
            bytes([
                0x03, 0x01, 0x07, 0x00,
                0x03, 0x02, 0x05, 0x00,
                0x06, 0x03, 0x01, 0x02,
                0x00,
            ]),
        )

    def test_comments_and_blank_lines_are_ignored(self):
        source = "; header comment\n\n  LDI R1, 7 ; trailing\n; only\nHALT\n"
        self.assertEqual(
            assemble(source), bytes([0x03, 0x01, 0x07, 0x00, 0x00])
        )

    def test_case_insensitive_mnemonics_and_registers(self):
        self.assertEqual(assemble("ldi r1, 7"), assemble("LDI R1, 7"))
        self.assertEqual(assemble("Add R3, r1, R2"), assemble("ADD R3, R1, R2"))

    def test_operands_without_commas(self):
        self.assertEqual(assemble("ADD R3 R1 R2"), assemble("ADD R3, R1, R2"))

    def test_backward_label_reference(self):
        source = "loop:\nADD R1, R1, R2\nJMP loop\n"
        code = assemble(source)
        # loop is at 0; JMP at 4 targets 0.
        self.assertEqual(code, bytes([0x06, 0x01, 0x01, 0x02, 0x12, 0x00, 0x00]))

    def test_forward_label_reference(self):
        source = "JMP done\nLDI R1, 99\ndone:\nHALT\n"
        code = assemble(source)
        # done is at 7 (3 + 4).
        self.assertEqual(
            code, bytes([0x12, 0x07, 0x00, 0x03, 0x01, 0x63, 0x00, 0x00])
        )

    def test_label_on_same_line_as_instruction(self):
        source = "JMP target\ntarget: HALT\n"
        self.assertEqual(assemble(source), bytes([0x12, 0x03, 0x00, 0x00]))

    def test_label_as_immediate(self):
        source = "LDI R1, data\nHALT\ndata:\n"
        # data is at 5 (end of code).
        self.assertEqual(
            assemble(source), bytes([0x03, 0x01, 0x05, 0x00, 0x00])
        )

    def test_number_formats(self):
        self.assertEqual(assemble("LDI R1, 42"), bytes([0x03, 0x01, 0x2A, 0x00]))
        self.assertEqual(assemble("LDI R1, 0x2A"), bytes([0x03, 0x01, 0x2A, 0x00]))
        self.assertEqual(assemble("LDI R1, 0b101010"), bytes([0x03, 0x01, 0x2A, 0x00]))

    def test_negative_immediate_encodes_twos_complement(self):
        self.assertEqual(assemble("LDI R1, -1"), bytes([0x03, 0x01, 0xFF, 0xFF]))
        self.assertEqual(assemble("LDI R1, -32768"), bytes([0x03, 0x01, 0x00, 0x80]))

    def test_entry_point_shifts_label_addresses(self):
        source = "JMP done\ndone: HALT\n"
        self.assertEqual(
            assemble(source, entry=0x100),
            bytes([0x12, 0x03, 0x01, 0x00]),  # done = 0x103
        )

    def test_empty_source_assembles_to_empty_bytes(self):
        self.assertEqual(assemble(""), b"")
        self.assertEqual(assemble("; nothing here\n"), b"")


class TestAssemblerErrors(unittest.TestCase):
    def assert_assemble_error(self, source, fragment):
        with self.assertRaises(AssembleError) as ctx:
            assemble(source)
        self.assertIn(fragment, str(ctx.exception))

    def test_unknown_mnemonic_reports_line_and_column(self):
        with self.assertRaises(AssembleError) as ctx:
            assemble("HALT\nBOGUS R1\n")
        message = str(ctx.exception)
        self.assertIn("line 2", message)
        self.assertIn("BOGUS", message)

    def test_wrong_operand_count(self):
        self.assert_assemble_error("ADD R1, R2\n", "takes 3 operand(s), got 2")
        self.assert_assemble_error("HALT R1\n", "takes 0 operand(s), got 1")

    def test_invalid_register(self):
        self.assert_assemble_error("LDI R8, 1\n", "expected a register")
        self.assert_assemble_error("LDI RA, 1\n", "expected a register")

    def test_unresolved_label(self):
        self.assert_assemble_error("JMP nowhere\n", "unknown label 'nowhere'")

    def test_duplicate_label(self):
        self.assert_assemble_error(
            "top: HALT\ntop: HALT\n", "duplicate label 'top'"
        )

    def test_invalid_label_name(self):
        self.assert_assemble_error("9lives: HALT\n", "invalid label name")

    def test_immediate_out_of_range(self):
        self.assert_assemble_error("LDI R1, 65536\n", "does not fit in 16 bits")
        self.assert_assemble_error("LDI R1, -32769\n", "does not fit in 16 bits")

    def test_address_out_of_range(self):
        self.assert_assemble_error("JMP 0x10000\n", "out of range")
        self.assert_assemble_error("JMP -1\n", "out of range")

    def test_register_where_number_expected(self):
        self.assert_assemble_error("LDI R1, R2\n", "where a number or label")


if __name__ == "__main__":
    unittest.main()
