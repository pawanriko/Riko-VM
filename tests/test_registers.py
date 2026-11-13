"""Tests for the register file (spec section 3.1)."""

import unittest

from rikovm.registers import STACK_TOP, RegisterFile


class TestRegisterFile(unittest.TestCase):
    def test_initial_state_is_zeroed_with_empty_stack(self):
        regs = RegisterFile()
        for i in range(8):
            self.assertEqual(regs.read(i), 0)
        self.assertEqual(regs.pc, 0)
        self.assertEqual(regs.sp, STACK_TOP)

    def test_write_and_read_roundtrip(self):
        regs = RegisterFile()
        regs.write(3, 0x1234)
        self.assertEqual(regs.read(3), 0x1234)
        # Other registers are untouched.
        self.assertEqual(regs.read(2), 0)

    def test_r0_is_a_plain_register(self):
        # R0 has no special role: it stores whatever is written.
        regs = RegisterFile()
        regs.write(0, 42)
        self.assertEqual(regs.read(0), 42)

    def test_writes_are_masked_to_16_bits(self):
        regs = RegisterFile()
        regs.write(1, 0x1_0000)
        self.assertEqual(regs.read(1), 0)
        regs.write(1, 0x1_FFFF)
        self.assertEqual(regs.read(1), 0xFFFF)

    def test_invalid_index_raises(self):
        regs = RegisterFile()
        for bad in (-1, 8, 255):
            with self.assertRaises(ValueError):
                regs.read(bad)
            with self.assertRaises(ValueError):
                regs.write(bad, 1)

    def test_pc_and_sp_are_masked(self):
        regs = RegisterFile()
        regs.pc = 0x1_0005
        self.assertEqual(regs.pc, 5)
        regs.sp = 0x1_FFFF
        self.assertEqual(regs.sp, 0xFFFF)

    def test_reset_restores_initial_state_with_entry_point(self):
        regs = RegisterFile()
        regs.write(0, 99)
        regs.pc = 0x1234
        regs.sp = 0xF000
        regs.reset(entry=0x0200)
        for i in range(8):
            self.assertEqual(regs.read(i), 0)
        self.assertEqual(regs.pc, 0x0200)
        self.assertEqual(regs.sp, STACK_TOP)

    def test_dump_reports_all_state(self):
        regs = RegisterFile()
        regs.write(7, 7)
        regs.pc = 0x10
        dump = regs.dump()
        self.assertEqual(dump["R7"], 7)
        self.assertEqual(dump["R0"], 0)
        self.assertEqual(dump["PC"], 0x10)
        self.assertEqual(dump["SP"], STACK_TOP)


if __name__ == "__main__":
    unittest.main()
