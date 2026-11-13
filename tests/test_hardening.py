"""Hardening tests: boundary conditions and edge cases (M7)."""

import unittest

from rikovm.assembler import assemble
from rikovm.cpu import CPU
from rikovm.errors import AssembleError
from rikovm.loader import build_image, load_image


def ldi(rd, value):
    return bytes([0x03, rd, value & 0xFF, (value >> 8) & 0xFF])


def run_bytes(program, entry=0):
    cpu = CPU()
    cpu.memory.load(bytes(program), entry)
    cpu.reset(entry)
    return cpu, cpu.run()


class TestRunBoundaries(unittest.TestCase):
    def test_zero_step_limit_stops_immediately(self):
        cpu = CPU()
        cpu.memory.load(ldi(1, 7) + bytes([0x00]), 0)
        result = cpu.run(max_steps=0)
        self.assertEqual(result.status, "step_limit")
        self.assertEqual(result.steps, 0)
        self.assertEqual(cpu.registers.read(1), 0)

    def test_halt_at_last_memory_byte(self):
        cpu = CPU()
        cpu.memory.write_byte(0xFFFF, 0x00)  # HALT at the very end
        cpu.reset(entry=0xFFFF)
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.pc, 0xFFFF)

    def test_jump_to_last_byte_halts(self):
        cpu, result = run_bytes(bytes([0x12, 0xFF, 0xFF]))
        # Memory is zeroed, so 0xFFFF already holds HALT.
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.pc, 0xFFFF)

    def test_snapshot_is_isolated_from_cpu_state(self):
        cpu, _ = run_bytes(ldi(1, 7) + bytes([0x00]))
        snapshot = cpu.snapshot()
        snapshot["registers"]["R1"] = 999
        snapshot["flags"]["Z"] = True
        fresh = cpu.snapshot()
        self.assertEqual(fresh["registers"]["R1"], 7)
        self.assertFalse(fresh["flags"]["Z"])


class TestFlagBoundaries(unittest.TestCase):
    def test_add_both_sign_extremes(self):
        # 0x8000 + 0x8000 = 0x0000 with carry AND signed overflow.
        cpu, _ = run_bytes(
            ldi(1, 0x8000) + ldi(2, 0x8000)
            + bytes([0x06, 0x03, 0x01, 0x02]) + bytes([0x00])
        )
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertTrue(cpu.flags.c)
        self.assertTrue(cpu.flags.v)
        self.assertTrue(cpu.flags.z)

    def test_sub_overflow_positive_minus_negative(self):
        # 0x7FFF - 0xFFFF = 0x8000: signed overflow.
        cpu, _ = run_bytes(
            ldi(1, 0x7FFF) + ldi(2, 0xFFFF)
            + bytes([0x07, 0x03, 0x01, 0x02]) + bytes([0x00])
        )
        self.assertEqual(cpu.registers.read(3), 0x8000)
        self.assertTrue(cpu.flags.v)
        self.assertFalse(cpu.flags.c)  # 0x7FFF < 0xFFFF: borrowed

    def test_shl_by_15(self):
        cpu, _ = run_bytes(
            ldi(1, 0x0001) + ldi(2, 15)
            + bytes([0x0E, 0x03, 0x01, 0x02]) + bytes([0x00])
        )
        self.assertEqual(cpu.registers.read(3), 0x8000)
        self.assertFalse(cpu.flags.c)
        self.assertTrue(cpu.flags.n)

    def test_shr_by_15(self):
        cpu, _ = run_bytes(
            ldi(1, 0x8000) + ldi(2, 15)
            + bytes([0x0F, 0x03, 0x01, 0x02]) + bytes([0x00])
        )
        self.assertEqual(cpu.registers.read(3), 1)
        self.assertFalse(cpu.flags.c)

    def test_mul_by_zero(self):
        cpu, _ = run_bytes(
            ldi(1, 0xBEEF) + ldi(2, 0)
            + bytes([0x08, 0x03, 0x01, 0x02]) + bytes([0x00])
        )
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertTrue(cpu.flags.z)
        self.assertFalse(cpu.flags.v)


class TestAssemblerBoundaries(unittest.TestCase):
    def test_program_too_large_is_rejected(self):
        source = "LDI R1, 0\n" * 16385  # 16385 * 4 = 65540 bytes
        with self.assertRaises(AssembleError):
            assemble(source)

    def test_label_named_like_a_mnemonic(self):
        # Labels and mnemonics are different namespaces.
        source = "JMP add\nadd: HALT\n"
        self.assertEqual(assemble(source), bytes([0x12, 0x03, 0x00, 0x00]))

    def test_many_labels_and_forward_refs(self):
        source = "\n".join(
            [f"JMP end", "LDI R1, 1", "LDI R2, 2", "LDI R3, 3", "end: HALT"]
        )
        code = assemble(source)
        self.assertEqual(code[1:3], (15).to_bytes(2, "little"))

    def test_image_with_entry_at_top_of_memory(self):
        cpu = CPU()
        load_image(cpu, build_image(bytes([0x00]), entry=0xFFFF))
        result = cpu.run()
        self.assertEqual(result.status, "halted")


if __name__ == "__main__":
    unittest.main()
