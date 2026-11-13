"""Tests for the RKP1 image format and loader (spec section 7)."""

import unittest

from rikovm.cpu import CPU
from rikovm.errors import LoadError
from rikovm.loader import MAGIC, build_image, load_image, parse_image

CODE = bytes([0x03, 0x01, 0x07, 0x00, 0x00])


class TestBuildImage(unittest.TestCase):
    def test_image_layout(self):
        image = build_image(CODE, entry=0x0200)
        self.assertEqual(image[0:4], MAGIC)
        self.assertEqual(image[4:6], b"\x00\x02")  # entry, little-endian
        self.assertEqual(image[6:8], b"\x05\x00")  # length, little-endian
        self.assertEqual(image[8:], CODE)

    def test_default_entry_is_zero(self):
        entry, code = parse_image(build_image(CODE))
        self.assertEqual(entry, 0)
        self.assertEqual(code, CODE)

    def test_empty_code_is_valid(self):
        entry, code = parse_image(build_image(b""))
        self.assertEqual((entry, code), (0, b""))

    def test_oversize_code_rejected(self):
        with self.assertRaises(LoadError):
            build_image(bytes(65536))
        with self.assertRaises(LoadError):
            build_image(b"\x00\x00", entry=0xFFFF)
        with self.assertRaises(LoadError):
            build_image(CODE, entry=0x10000)


class TestParseImage(unittest.TestCase):
    def test_bad_magic_rejected(self):
        image = bytearray(build_image(CODE))
        image[0:4] = b"XXXX"
        with self.assertRaises(LoadError) as ctx:
            parse_image(bytes(image))
        self.assertIn("bad magic", str(ctx.exception))

    def test_truncated_header_rejected(self):
        with self.assertRaises(LoadError):
            parse_image(b"RKP1\x00")

    def test_length_mismatch_rejected(self):
        image = bytearray(build_image(CODE))
        image[6] = 0x04  # declare 4 bytes, hold 5
        with self.assertRaises(LoadError) as ctx:
            parse_image(bytes(image))
        self.assertIn("declares 4", str(ctx.exception))

    def test_trailing_garbage_rejected(self):
        with self.assertRaises(LoadError):
            parse_image(build_image(CODE) + b"\x00")

    def test_entry_plus_length_overflow_rejected(self):
        image = MAGIC + (0xFFFF).to_bytes(2, "little") + (2).to_bytes(2, "little")
        image += b"\x00\x00"
        with self.assertRaises(LoadError):
            parse_image(image)


class TestLoadImage(unittest.TestCase):
    def test_load_places_code_and_resets_cpu(self):
        cpu = CPU()
        cpu.registers.write(1, 99)
        info = load_image(cpu, build_image(CODE, entry=0x0100))
        self.assertEqual(info, {"entry": 0x0100, "length": len(CODE)})
        self.assertEqual(cpu.memory.read_bytes(0x0100, len(CODE)), CODE)
        self.assertEqual(cpu.registers.pc, 0x0100)
        self.assertEqual(cpu.registers.read(1), 0)  # reset cleared it
        self.assertFalse(cpu.halted)

    def test_loaded_program_runs(self):
        cpu = CPU()
        load_image(cpu, build_image(CODE, entry=0))
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(1), 7)

    def test_failed_load_leaves_cpu_untouched(self):
        cpu = CPU()
        cpu.memory.load(b"\xAA", 0x0100)
        cpu.registers.write(1, 55)
        with self.assertRaises(LoadError):
            load_image(cpu, b"not an image at all........")
        self.assertEqual(cpu.memory.read_byte(0x0100), 0xAA)
        self.assertEqual(cpu.registers.read(1), 55)


if __name__ == "__main__":
    unittest.main()
