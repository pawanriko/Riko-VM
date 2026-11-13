"""Tests for the instruction decoder (spec sections 4-5)."""

import unittest

from rikovm.decoder import decode
from rikovm.errors import DecodeFault
from rikovm.memory import Memory


def memory_with(program, address=0):
    mem = Memory()
    mem.load(bytes(program), address)
    return mem


class TestDecoder(unittest.TestCase):
    def test_decode_halt(self):
        instr = decode(memory_with([0x00]), 0)
        self.assertEqual(instr.mnemonic, "HALT")
        self.assertEqual(instr.operands, ())
        self.assertEqual(instr.length, 1)
        self.assertEqual(instr.address, 0)

    def test_decode_ldi_reads_little_endian_immediate(self):
        instr = decode(memory_with([0x03, 0x01, 0x34, 0x12]), 0)
        self.assertEqual(instr.mnemonic, "LDI")
        self.assertEqual(instr.operands, (1, 0x1234))
        self.assertEqual(instr.length, 4)

    def test_decode_add_reads_three_registers(self):
        instr = decode(memory_with([0x06, 0x03, 0x01, 0x02]), 0)
        self.assertEqual(instr.mnemonic, "ADD")
        self.assertEqual(instr.operands, (3, 1, 2))
        self.assertEqual(instr.length, 4)

    def test_decode_at_nonzero_address(self):
        mem = memory_with([0x00, 0x00, 0x03, 0x02, 0x05, 0x00])
        instr = decode(mem, 2)
        self.assertEqual(instr.mnemonic, "LDI")
        self.assertEqual(instr.address, 2)

    def test_unknown_opcode_faults(self):
        with self.assertRaises(DecodeFault):
            decode(memory_with([0xFF]), 0)
        with self.assertRaises(DecodeFault):
            decode(memory_with([0x1A]), 0)  # just past the last opcode

    def test_register_byte_above_7_faults(self):
        with self.assertRaises(DecodeFault):
            decode(memory_with([0x03, 0x08, 0x00, 0x00]), 0)

    def test_truncated_instruction_faults(self):
        # LDI at 0xFFFE: its 4 bytes would run past the end of memory.
        mem = Memory()
        mem.write_byte(0xFFFE, 0x03)
        mem.write_byte(0xFFFF, 0x01)
        with self.assertRaises(DecodeFault):
            decode(mem, 0xFFFE)

    def test_every_isa_row_decodes(self):
        # Each opcode in the table decodes from zeroed operand bytes.
        from rikovm.isa import INSTRUCTIONS

        for definition in INSTRUCTIONS:
            program = [definition.opcode] + [0] * (definition.length - 1)
            instr = decode(memory_with(program), 0)
            self.assertEqual(instr.mnemonic, definition.mnemonic)
            self.assertEqual(instr.length, definition.length)


if __name__ == "__main__":
    unittest.main()
