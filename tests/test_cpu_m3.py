"""Tests for the full ISA (M3, spec sections 3.2 and 5).

Programs here are raw bytes, hand-encoded from the ISA table. The
assembler tests (M4) cover the same behaviour through assembly source.
"""

import unittest

from rikovm.cpu import CPU

HALT = bytes([0x00])


def ldi(rd, value):
    return bytes([0x03, rd, value & 0xFF, (value >> 8) & 0xFF])


def run_program(program):
    cpu = CPU()
    cpu.memory.load(bytes(program), 0)
    result = cpu.run()
    return cpu, result


class TestDataMovement(unittest.TestCase):
    def test_nop_advances_pc_and_changes_nothing(self):
        cpu, result = run_program(bytes([0x01, 0x00]))
        self.assertEqual(result.status, "halted")
        self.assertEqual(result.steps, 2)
        self.assertEqual(cpu.registers.pc, 1)

    def test_mov_copies_register(self):
        cpu, _ = run_program(ldi(1, 99) + bytes([0x02, 0x02, 0x01]) + HALT)
        self.assertEqual(cpu.registers.read(2), 99)

    def test_load_and_store_roundtrip(self):
        program = (
            ldi(1, 0xBEEF)
            + bytes([0x05, 0x01, 0x00, 0x20])  # STORE R1, 0x2000
            + ldi(1, 0)
            + bytes([0x04, 0x02, 0x00, 0x20])  # LOAD R2, 0x2000
            + HALT
        )
        cpu, result = run_program(program)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 0xBEEF)

    def test_store_to_0xffff_faults_without_writing(self):
        cpu, result = run_program(
            ldi(1, 0xFFFF) + bytes([0x05, 0x01, 0xFF, 0xFF]) + HALT
        )
        self.assertEqual(result.status, "fault")
        self.assertIn("past end of memory", result.error)
        self.assertEqual(cpu.memory.read_byte(0xFFFF), 0)


class TestArithmetic(unittest.TestCase):
    def test_sub_basic_and_carry_no_borrow(self):
        cpu, _ = run_program(
            ldi(1, 10) + ldi(2, 4) + bytes([0x07, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 6)
        self.assertTrue(cpu.flags.c)  # no borrow
        self.assertFalse(cpu.flags.z)

    def test_sub_borrow_clears_carry(self):
        cpu, _ = run_program(
            ldi(1, 4) + ldi(2, 10) + bytes([0x07, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 0xFFFA)
        self.assertFalse(cpu.flags.c)  # borrowed
        self.assertTrue(cpu.flags.n)

    def test_sub_signed_overflow(self):
        cpu, _ = run_program(
            ldi(1, 0x8000) + ldi(2, 1) + bytes([0x07, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 0x7FFF)
        self.assertTrue(cpu.flags.v)

    def test_sub_equal_values_set_zero_and_carry(self):
        cpu, _ = run_program(
            ldi(1, 7) + ldi(2, 7) + bytes([0x07, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertTrue(cpu.flags.z)
        self.assertTrue(cpu.flags.c)

    def test_mul_basic(self):
        cpu, _ = run_program(
            ldi(1, 6) + ldi(2, 7) + bytes([0x08, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 42)
        self.assertFalse(cpu.flags.v)

    def test_mul_overflow_sets_v_and_wraps(self):
        cpu, _ = run_program(
            ldi(1, 0x100) + ldi(2, 0x100) + bytes([0x08, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 0)
        self.assertTrue(cpu.flags.v)
        self.assertTrue(cpu.flags.z)

    def test_mul_leaves_carry_unchanged(self):
        cpu = CPU()
        cpu.memory.load(
            ldi(1, 2) + ldi(2, 3) + bytes([0x08, 0x03, 0x01, 0x02]) + HALT, 0
        )
        cpu.flags.c = True
        cpu.run()
        self.assertTrue(cpu.flags.c)

    def test_div_basic(self):
        cpu, _ = run_program(
            ldi(1, 17) + ldi(2, 5) + bytes([0x09, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(cpu.registers.read(3), 3)

    def test_div_by_zero_faults_and_writes_nothing(self):
        cpu, result = run_program(
            ldi(1, 10) + ldi(2, 0) + ldi(3, 0xBEEF)
            + bytes([0x09, 0x03, 0x01, 0x02]) + HALT
        )
        self.assertEqual(result.status, "fault")
        self.assertIn("division by zero", result.error)
        self.assertEqual(cpu.registers.read(3), 0xBEEF)  # untouched


class TestLogicAndShifts(unittest.TestCase):
    def _run_logic(self, opcode, a, b):
        return run_program(
            ldi(1, a) + ldi(2, b) + bytes([opcode, 0x03, 0x01, 0x02]) + HALT
        )

    def test_and(self):
        cpu, _ = self._run_logic(0x0A, 0b1100, 0b1010)
        self.assertEqual(cpu.registers.read(3), 0b1000)

    def test_or(self):
        cpu, _ = self._run_logic(0x0B, 0b1100, 0b1010)
        self.assertEqual(cpu.registers.read(3), 0b1110)

    def test_xor(self):
        cpu, _ = self._run_logic(0x0C, 0b1100, 0b1010)
        self.assertEqual(cpu.registers.read(3), 0b0110)

    def test_logic_ops_clear_carry_and_overflow(self):
        cpu = CPU()
        cpu.memory.load(
            ldi(1, 0xFF) + ldi(2, 0x0F) + bytes([0x0A, 0x03, 0x01, 0x02]) + HALT, 0
        )
        cpu.flags.c = True
        cpu.flags.v = True
        cpu.run()
        self.assertFalse(cpu.flags.c)
        self.assertFalse(cpu.flags.v)

    def test_not(self):
        cpu, _ = run_program(ldi(1, 0x0F0F) + bytes([0x0D, 0x03, 0x01]) + HALT)
        self.assertEqual(cpu.registers.read(3), 0xF0F0)
        self.assertTrue(cpu.flags.n)

    def test_shl_basic_and_carry(self):
        cpu, _ = self._run_logic(0x0E, 0x8001, 1)
        self.assertEqual(cpu.registers.read(3), 0x0002)
        self.assertTrue(cpu.flags.c)

    def test_shl_count_zero_leaves_value_and_clears_carry(self):
        cpu, _ = self._run_logic(0x0E, 0x1234, 0)
        self.assertEqual(cpu.registers.read(3), 0x1234)
        self.assertFalse(cpu.flags.c)

    def test_shl_count_uses_low_4_bits(self):
        cpu, _ = self._run_logic(0x0E, 0x0001, 0x11)  # count 0x11 & 0xF = 1
        self.assertEqual(cpu.registers.read(3), 0x0002)

    def test_shr_basic_and_carry(self):
        cpu, _ = self._run_logic(0x0F, 0x0003, 1)
        self.assertEqual(cpu.registers.read(3), 0x0001)
        self.assertTrue(cpu.flags.c)

    def test_shr_count_zero(self):
        cpu, _ = self._run_logic(0x0F, 0x1234, 0)
        self.assertEqual(cpu.registers.read(3), 0x1234)
        self.assertFalse(cpu.flags.c)


class TestCompareAndBranches(unittest.TestCase):
    def test_cmp_sets_flags_without_writing(self):
        cpu, _ = run_program(
            ldi(1, 5) + ldi(2, 5) + ldi(3, 0xBEEF)
            + bytes([0x10, 0x01, 0x02]) + HALT
        )
        self.assertTrue(cpu.flags.z)
        self.assertTrue(cpu.flags.c)
        self.assertEqual(cpu.registers.read(3), 0xBEEF)

    def test_test_sets_flags_from_and_without_writing(self):
        cpu, _ = run_program(
            ldi(1, 0xF0) + ldi(2, 0x0F) + bytes([0x11, 0x01, 0x02]) + HALT
        )
        self.assertTrue(cpu.flags.z)
        self.assertFalse(cpu.flags.c)

    def test_jmp_skips_code(self):
        # JMP 7: skips the LDI R1, 99 at address 3.
        program = bytes([0x12, 0x07, 0x00]) + ldi(1, 99) + ldi(1, 7) + HALT
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(1), 7)

    def test_jz_taken_when_zero(self):
        program = (
            ldi(1, 5) + ldi(2, 5)
            + bytes([0x10, 0x01, 0x02])          # CMP R1, R2 -> Z=1
            + bytes([0x13, 0x12, 0x00])          # JZ 18
            + ldi(3, 99)                          # skipped
            + ldi(3, 7)                           # address 18
            + HALT
        )
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(3), 7)

    def test_jz_falls_through_when_not_zero(self):
        program = (
            ldi(1, 5) + ldi(2, 6)
            + bytes([0x10, 0x01, 0x02])          # CMP -> Z=0
            + bytes([0x13, 0x12, 0x00])          # JZ 18 (not taken)
            + ldi(3, 99)                          # address 14
            + HALT                                # address 18
        )
        # JZ not taken: falls through to LDI R3, 99, then HALT.
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(3), 99)

    def test_jnz_taken_when_not_zero(self):
        program = (
            ldi(1, 5) + ldi(2, 6)
            + bytes([0x10, 0x01, 0x02])
            + bytes([0x14, 0x12, 0x00])          # JNZ 18
            + ldi(3, 99)                          # skipped
            + ldi(3, 7)                           # address 18
            + HALT
        )
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(3), 7)

    def test_jc_taken_when_no_borrow(self):
        program = (
            ldi(1, 10) + ldi(2, 4)
            + bytes([0x10, 0x01, 0x02])          # CMP: 10>=4, C=1
            + bytes([0x15, 0x12, 0x00])          # JC 18
            + ldi(3, 99)                          # skipped
            + ldi(3, 7)                           # address 18
            + HALT
        )
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(3), 7)

    def test_jc_falls_through_after_borrow(self):
        program = (
            ldi(1, 4) + ldi(2, 10)
            + bytes([0x10, 0x01, 0x02])          # CMP: borrow, C=0
            + bytes([0x15, 0x12, 0x00])          # JC 18 (not taken)
            + ldi(3, 99)
            + HALT
        )
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(3), 99)

    def test_countdown_loop_sums_1_to_5(self):
        # R1=5 counter, R2=0 sum, R3=1 step; loop at 12.
        program = (
            ldi(1, 5) + ldi(2, 0) + ldi(3, 1)
            + bytes([0x06, 0x02, 0x02, 0x01])    # 12: ADD R2, R2, R1
            + bytes([0x07, 0x01, 0x01, 0x03])    # 16: SUB R1, R1, R3
            + bytes([0x14, 0x0C, 0x00])          # 20: JNZ 12
            + HALT                                # 23
        )
        cpu, result = run_program(program)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 15)
        self.assertEqual(cpu.registers.read(1), 0)


class TestStackAndCalls(unittest.TestCase):
    def test_push_pop_roundtrip_and_sp_movement(self):
        program = (
            ldi(1, 0xBEEF)
            + bytes([0x18, 0x01])                # PUSH R1
            + ldi(1, 0)
            + bytes([0x19, 0x02])                # POP R2
            + HALT
        )
        cpu, result = run_program(program)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 0xBEEF)
        self.assertEqual(cpu.registers.sp, 0xFFFF)  # empty again

    def test_stack_is_lifo(self):
        program = (
            ldi(1, 1) + bytes([0x18, 0x01])
            + ldi(1, 2) + bytes([0x18, 0x01])
            + bytes([0x19, 0x02]) + bytes([0x19, 0x03])
            + HALT
        )
        cpu, _ = run_program(program)
        self.assertEqual(cpu.registers.read(2), 2)
        self.assertEqual(cpu.registers.read(3), 1)

    def test_pop_from_empty_stack_faults(self):
        cpu, result = run_program(bytes([0x19, 0x01]) + HALT)
        self.assertEqual(result.status, "fault")
        self.assertIn("underflow", result.error)

    def test_push_past_stack_bottom_faults(self):
        cpu = CPU()
        cpu.memory.load(bytes([0x18, 0x01, 0x00]), 0)
        cpu.registers.sp = 0xF000  # one word of room left... actually none:
        # PUSH needs SP-2 >= 0xF000; SP=0xF000 gives 0xEFFE -> fault.
        result = cpu.run()
        self.assertEqual(result.status, "fault")
        self.assertIn("overflow", result.error)

    def test_push_at_last_valid_slot_succeeds(self):
        cpu = CPU()
        cpu.memory.load(ldi(1, 0x1234) + bytes([0x18, 0x01]) + HALT, 0)
        cpu.registers.sp = 0xF002
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.sp, 0xF000)
        self.assertEqual(cpu.memory.read_word(0xF000), 0x1234)

    def test_call_and_ret(self):
        program = (
            bytes([0x16, 0x04, 0x00])            # 0: CALL 4
            + HALT                                # 3: return here
            + ldi(1, 42)                          # 4: subroutine
            + bytes([0x17])                       # 8: RET
        )
        cpu, result = run_program(program)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(1), 42)
        self.assertEqual(cpu.registers.sp, 0xFFFF)
        self.assertEqual(cpu.registers.pc, 3)  # HALT after return

    def test_ret_on_empty_stack_faults(self):
        cpu, result = run_program(bytes([0x17]) + HALT)
        self.assertEqual(result.status, "fault")
        self.assertIn("underflow", result.error)

    def test_nested_calls(self):
        # main CALLs A (at 4); A CALLs B (at 12); B sets R1, returns.
        program = (
            bytes([0x16, 0x04, 0x00])            # 0: CALL 4
            + HALT                                # 3
            + bytes([0x16, 0x0C, 0x00])          # 4: CALL 12
            + bytes([0x17])                       # 7: RET (back to 3)
            + bytes([0x01, 0x01, 0x01, 0x01])    # 8-11: padding NOPs
            + ldi(1, 7)                           # 12: B
            + bytes([0x17])                       # 16: RET (back to 7)
        )
        cpu, result = run_program(program)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(1), 7)
        self.assertEqual(cpu.registers.sp, 0xFFFF)


if __name__ == "__main__":
    unittest.main()
