"""Tests for the status flags (spec section 3.2)."""

import unittest

from rikovm.flags import Flags


class TestFlags(unittest.TestCase):
    def test_initial_state_is_all_clear(self):
        flags = Flags()
        self.assertEqual(flags.as_dict(), {"Z": False, "C": False, "N": False, "V": False})

    def test_update_zn_sets_zero_for_zero(self):
        flags = Flags()
        flags.update_zn(0)
        self.assertTrue(flags.z)
        self.assertFalse(flags.n)

    def test_update_zn_sets_negative_for_bit15(self):
        flags = Flags()
        flags.update_zn(0x8000)
        self.assertFalse(flags.z)
        self.assertTrue(flags.n)

    def test_update_zn_clears_both_for_plain_positive(self):
        flags = Flags()
        flags.z = True
        flags.n = True
        flags.update_zn(1)
        self.assertFalse(flags.z)
        self.assertFalse(flags.n)

    def test_update_zn_masks_to_16_bits(self):
        flags = Flags()
        flags.update_zn(0x1_0000)  # low 16 bits are zero
        self.assertTrue(flags.z)
        self.assertFalse(flags.n)

    def test_update_zn_leaves_carry_and_overflow_alone(self):
        flags = Flags()
        flags.c = True
        flags.v = True
        flags.update_zn(5)
        self.assertTrue(flags.c)
        self.assertTrue(flags.v)

    def test_reset_clears_everything(self):
        flags = Flags()
        flags.z = flags.c = flags.n = flags.v = True
        flags.reset()
        self.assertEqual(flags.as_dict(), {"Z": False, "C": False, "N": False, "V": False})


if __name__ == "__main__":
    unittest.main()
