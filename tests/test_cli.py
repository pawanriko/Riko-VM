"""Tests for the CLI (spec section 9), driving main() in-process with
temporary files and captured output."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from rikovm.cli import main
from rikovm.loader import parse_image


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = os.path.join(self.tmp.name, "add.rka")
        with open(self.source, "w") as handle:
            handle.write("LDI R1, 7\nLDI R2, 5\nADD R3, R1, R2\nHALT\n")
        self.image = os.path.join(self.tmp.name, "add.rkp")

    def run_cli(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def assemble(self):
        code, out, _ = self.run_cli(
            ["assemble", self.source, "-o", self.image]
        )
        self.assertEqual(code, 0, out)
        return out


class TestCliAssemble(CliTestCase):
    def test_assemble_writes_valid_image(self):
        out = self.assemble()
        self.assertIn("assembled 13 bytes", out)
        with open(self.image, "rb") as handle:
            entry, code = parse_image(handle.read())
        self.assertEqual(entry, 0)
        self.assertEqual(len(code), 13)

    def test_assemble_with_entry(self):
        code, out, _ = self.run_cli(
            ["assemble", self.source, "-o", self.image, "--entry", "0x100"]
        )
        self.assertEqual(code, 0)
        self.assertIn("entry 0x0100", out)

    def test_assemble_bad_source_reports_error(self):
        bad = os.path.join(self.tmp.name, "bad.rka")
        with open(bad, "w") as handle:
            handle.write("BOGUS R1\n")
        code, _, err = self.run_cli(["assemble", bad, "-o", self.image])
        self.assertEqual(code, 1)
        self.assertIn("unknown mnemonic", err)

    def test_assemble_missing_file_reports_error(self):
        code, _, err = self.run_cli(
            ["assemble", os.path.join(self.tmp.name, "nope.rka"), "-o", self.image]
        )
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)


class TestCliRun(CliTestCase):
    def test_run_halts_and_shows_registers(self):
        self.assemble()
        code, out, _ = self.run_cli(["run", self.image])
        self.assertEqual(code, 0)
        self.assertIn("halted after 4 step(s)", out)
        self.assertIn("R3=0x000c", out)
        self.assertIn("flags:", out)

    def test_run_fault_returns_1(self):
        faulty = os.path.join(self.tmp.name, "fault.rka")
        with open(faulty, "w") as handle:
            handle.write("LDI R1, 1\nLDI R2, 0\nDIV R3, R1, R2\nHALT\n")
        faulty_image = os.path.join(self.tmp.name, "fault.rkp")
        self.run_cli(["assemble", faulty, "-o", faulty_image])
        code, out, _ = self.run_cli(["run", faulty_image])
        self.assertEqual(code, 1)
        self.assertIn("fault after 2 step(s)", out)
        self.assertIn("division by zero", out)

    def test_run_step_limit(self):
        self.assemble()
        code, out, _ = self.run_cli(["run", self.image, "--max-steps", "2"])
        self.assertEqual(code, 1)
        self.assertIn("step limit reached", out)

    def test_run_bad_image_reports_error(self):
        bad = os.path.join(self.tmp.name, "bad.rkp")
        with open(bad, "wb") as handle:
            handle.write(b"garbage!!")
        code, _, err = self.run_cli(["run", bad])
        self.assertEqual(code, 1)
        self.assertIn("bad magic", err)


class TestCliStepAndInspect(CliTestCase):
    def test_step_executes_one_instruction(self):
        self.assemble()
        code, out, _ = self.run_cli(["step", self.image])
        self.assertEqual(code, 0)
        self.assertIn("0x0000: LDI R1, 0x0007", out)
        self.assertIn("R1=0x0007", out)
        self.assertIn("PC=0x0004", out)

    def test_step_multiple_then_halt(self):
        self.assemble()
        code, out, _ = self.run_cli(["step", self.image, "--steps", "4"])
        self.assertEqual(code, 0)
        self.assertIn("ADD R3, R1, R2", out)
        self.assertIn("halted", out)
        self.assertIn("R3=0x000c", out)

    def test_inspect_registers_without_running(self):
        self.assemble()
        code, out, _ = self.run_cli(["inspect", "registers", self.image])
        self.assertEqual(code, 0)
        self.assertIn("R1=0x0000", out)  # not run yet: still zero
        self.assertIn("PC=0x0000", out)

    def test_inspect_memory_hex_dump(self):
        self.assemble()
        code, out, _ = self.run_cli(["inspect", "memory", self.image, "0", "5"])
        self.assertEqual(code, 0)
        self.assertIn("0x0000: 03 01 07 00 03", out)

    def test_inspect_memory_out_of_range(self):
        self.assemble()
        code, _, err = self.run_cli(
            ["inspect", "memory", self.image, "0xFFFF", "2"]
        )
        self.assertEqual(code, 1)
        self.assertIn("past memory", err)


class TestCliTrace(CliTestCase):
    def test_trace_lists_every_instruction(self):
        self.assemble()
        code, out, _ = self.run_cli(["trace", self.image])
        self.assertEqual(code, 0)
        self.assertIn("0x0000: LDI R1, 0x0007", out)
        self.assertIn("0x0004: LDI R2, 0x0005", out)
        self.assertIn("0x0008: ADD R3, R1, R2", out)
        self.assertIn("0x000c: HALT", out)
        self.assertIn("halted after 4 step(s)", out)


if __name__ == "__main__":
    unittest.main()
