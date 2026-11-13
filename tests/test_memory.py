"""Tests for virtual memory (spec section 3.3)."""

import unittest

from rikovm.errors import MemoryFault
from rikovm.memory import MAX_ADDRESS, SIZE, Memory


class TestMemory(unittest.TestCase):
    def test_size_is_64kib(self):
        self.assertEqual(len(Memory()), SIZE)
        self.assertEqual(SIZE, 65536)

    def test_initial_contents_are_zero(self):
        mem = Memory()
        self.assertEqual(mem.read_byte(0), 0)
        self.assertEqual(mem.read_word(0x8000), 0)
        self.assertEqual(mem.read_byte(MAX_ADDRESS), 0)

    def test_byte_write_and_read_roundtrip(self):
        mem = Memory()
        mem.write_byte(0x0100, 0xAB)
        self.assertEqual(mem.read_byte(0x0100), 0xAB)

    def test_byte_writes_are_masked_to_8_bits(self):
        mem = Memory()
        mem.write_byte(0, 0x1AB)
        self.assertEqual(mem.read_byte(0), 0xAB)

    def test_word_is_little_endian(self):
        mem = Memory()
        mem.write_word(0x0100, 0x1234)
        self.assertEqual(mem.read_byte(0x0100), 0x34)  # low byte first
        self.assertEqual(mem.read_byte(0x0101), 0x12)
        self.assertEqual(mem.read_word(0x0100), 0x1234)

    def test_word_read_assembles_bytes_little_endian(self):
        mem = Memory()
        mem.write_byte(0x0200, 0x78)
        mem.write_byte(0x0201, 0x56)
        self.assertEqual(mem.read_word(0x0200), 0x5678)

    def test_word_at_last_valid_address(self):
        mem = Memory()
        mem.write_word(0xFFFE, 0xBEEF)
        self.assertEqual(mem.read_word(0xFFFE), 0xBEEF)

    def test_word_at_0xffff_faults(self):
        mem = Memory()
        with self.assertRaises(MemoryFault):
            mem.read_word(0xFFFF)
        with self.assertRaises(MemoryFault):
            mem.write_word(0xFFFF, 1)

    def test_out_of_range_access_faults(self):
        mem = Memory()
        for bad in (-1, SIZE, 0x1_0000):
            with self.assertRaises(MemoryFault):
                mem.read_byte(bad)
            with self.assertRaises(MemoryFault):
                mem.write_byte(bad, 0)

    def test_read_bytes_slice(self):
        mem = Memory()
        mem.load(b"\x01\x02\x03", 0x0300)
        self.assertEqual(mem.read_bytes(0x0300, 3), b"\x01\x02\x03")
        self.assertEqual(mem.read_bytes(0x0301, 0), b"")

    def test_read_bytes_past_end_faults(self):
        mem = Memory()
        with self.assertRaises(MemoryFault):
            mem.read_bytes(0xFFFF, 2)

    def test_load_copies_and_bounds_checks(self):
        mem = Memory()
        mem.load(b"\xde\xad", 0x0000)
        self.assertEqual(mem.read_word(0), 0xADDE)
        with self.assertRaises(MemoryFault):
            mem.load(b"\x01\x02", 0xFFFF)  # would not fit
        # Failed load changed nothing.
        self.assertEqual(mem.read_byte(0xFFFF), 0)


if __name__ == "__main__":
    unittest.main()
