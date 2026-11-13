"""Tests for the CPU loop and the M2 instruction subset (spec section 4).

The acceptance program from the spec, in raw bytes:
    LDI R1, 7      03 01 07 00
    LDI R2, 5      03 02 05 00
    ADD R3, R1, R2 06 03 01 02
    HALT           00
"""

import unittest

from rikovm.cpu import CPU
from rikovm.errors import VMFault
from rikovm.memory import Memory

ADD_PROGRAM = bytes(
    [
        0x03, 0x01, 0x07, 0x00,
        0x03, 0x02, 0x05, 0x00,
        0x06, 0x03, 0x01, 0x02,
        0x00,
    ]
)


def cpu_with(program):
    cpu = CPU()
    cpu.memory.load(program, 0)
    return cpu


class TestCpuM2(unittest.TestCase):
    def test_add_program_halts_with_r3_equal_12(self):
        cpu = cpu_with(ADD_PROGRAM)
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(result.steps, 4)
        self.assertEqual(cpu.registers.read(3), 12)
        self.assertTrue(cpu.halted)

    def test_pc_stays_on_halt_instruction(self):
        cpu = cpu_with(ADD_PROGRAM)
        cpu.run()
        self.assertEqual(cpu.registers.pc, 12)  # address of HALT

    def test_step_advances_pc_by_instruction_length(self):
        cpu = cpu_with(ADD_PROGRAM)
        entry = cpu.step()
        self.assertEqual(entry.mnemonic, "LDI")
        self.assertEqual(cpu.registers.pc, 4)
        self.assertEqual(cpu.registers.read(1), 7)
        cpu.step()
        self.assertEqual(cpu.registers.pc, 8)
        cpu.step()
        self.assertEqual(cpu.registers.pc, 12)
        self.assertEqual(cpu.registers.read(3), 12)

    def test_stepping_a_halted_cpu_raises(self):
        cpu = cpu_with(bytes([0x00]))
        cpu.run()
        with self.assertRaises(VMFault):
            cpu.step()

    def test_ldi_leaves_flags_unchanged(self):
        cpu = cpu_with(bytes([0x03, 0x01, 0x00, 0x00, 0x00]))
        cpu.flags.z = True
        cpu.flags.c = True
        cpu.run()
        self.assertTrue(cpu.flags.z)
        self.assertTrue(cpu.flags.c)

    def test_add_sets_zero_flag(self):
        cpu = cpu_with(
            bytes([0x03, 0x01, 0x00, 0x00, 0x03, 0x02, 0x00, 0x00,
                   0x06, 0x03, 0x01, 0x02, 0x00])
        )
        cpu.run()
        self.assertTrue(cpu.flags.z)
        self.assertFalse(cpu.flags.n)

    def test_add_sets_carry_on_unsigned_overflow(self):
        cpu = cpu_with(
            bytes([0x03, 0x01, 0xFF, 0xFF, 0x03, 0x02, 0x01, 0x00,
                   0x06, 0x03, 0x01, 0x02, 0x00])
        )
        cpu.run()
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertTrue(cpu.flags.c)
        self.assertTrue(cpu.flags.z)

    def test_add_sets_overflow_on_signed_overflow(self):
        cpu = cpu_with(
            bytes([0x03, 0x01, 0xFF, 0x7F, 0x03, 0x02, 0x01, 0x00,
                   0x06, 0x03, 0x01, 0x02, 0x00])
        )
        cpu.run()
        self.assertEqual(cpu.registers.read(3), 0x8000)
        self.assertTrue(cpu.flags.v)
        self.assertTrue(cpu.flags.n)
        self.assertFalse(cpu.flags.c)

    def test_add_negative_flag_without_overflow(self):
        cpu = cpu_with(
            bytes([0x03, 0x01, 0xFF, 0xFF, 0x03, 0x02, 0x00, 0x00,
                   0x06, 0x03, 0x01, 0x02, 0x00])
        )
        cpu.run()
        self.assertTrue(cpu.flags.n)
        self.assertFalse(cpu.flags.v)

    def test_run_with_trace_records_every_instruction(self):
        cpu = cpu_with(ADD_PROGRAM)
        result = cpu.run(trace=True)
        self.assertEqual([e.mnemonic for e in result.trace],
                         ["LDI", "LDI", "ADD", "HALT"])
        self.assertEqual([e.address for e in result.trace], [0, 4, 8, 12])

    def test_step_limit_stops_a_long_run(self):
        cpu = cpu_with(ADD_PROGRAM)
        result = cpu.run(max_steps=2)
        self.assertEqual(result.status, "step_limit")
        self.assertEqual(result.steps, 2)
        self.assertFalse(cpu.halted)

    def test_unknown_opcode_is_a_fault_result_not_an_exception(self):
        cpu = cpu_with(bytes([0xFF]))
        result = cpu.run()
        self.assertEqual(result.status, "fault")
        self.assertIn("unknown opcode", result.error)
        self.assertEqual(result.steps, 0)

    def test_running_into_zeroed_memory_halts(self):
        # Memory starts zeroed and 0x00 is HALT: running off the end of
        # a program halts instead of executing garbage.
        cpu = cpu_with(bytes([0x03, 0x01, 0x07, 0x00]))  # LDI, then zeros
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(1), 7)

    def test_reset_clears_state_but_keeps_memory(self):
        cpu = cpu_with(ADD_PROGRAM)
        cpu.run()
        cpu.reset()
        self.assertFalse(cpu.halted)
        self.assertEqual(cpu.registers.pc, 0)
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertEqual(cpu.executed_count, 0)
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(3), 12)


if __name__ == "__main__":
    unittest.main()
