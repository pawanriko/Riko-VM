"""End-to-end integration tests: real .rka files from examples/ go
through assemble -> image -> load -> run, and the final machine state
must match the result each example promises in its comments."""

import os
import unittest

from rikovm.assembler import assemble
from rikovm.cpu import CPU
from rikovm.decoder import decode
from rikovm.loader import build_image, load_image

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def run_example(filename, entry=0):
    with open(os.path.join(EXAMPLES, filename)) as handle:
        source = handle.read()
    cpu = CPU()
    load_image(cpu, build_image(assemble(source, entry=entry), entry=entry))
    result = cpu.run()
    return cpu, result


class TestExamples(unittest.TestCase):
    def test_add(self):
        cpu, result = run_example("add.rka")
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(3), 12)

    def test_countdown(self):
        cpu, result = run_example("countdown.rka")
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 15)
        self.assertEqual(cpu.registers.read(1), 0)

    def test_factorial(self):
        cpu, result = run_example("factorial.rka")
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 120)

    def test_stack(self):
        cpu, result = run_example("stack.rka")
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(1), 84)
        self.assertEqual(cpu.registers.sp, 0xFFFF)

    def test_memory(self):
        cpu, result = run_example("memory.rka")
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(2), 0xBEEF)


class TestPipeline(unittest.TestCase):
    def test_assembled_labels_decode_back_to_branch_targets(self):
        # Assemble the countdown loop, then decode every instruction
        # from memory and check the JNZ targets the loop start.
        cpu, _ = run_example("countdown.rka")
        mnemonics = []
        address = 0
        while True:
            instr = decode(cpu.memory, address)
            mnemonics.append(instr.mnemonic)
            if instr.mnemonic == "HALT":
                break
            if instr.mnemonic == "JNZ":
                self.assertEqual(instr.operands, (12,))  # address of 'loop'
            address += instr.length
        self.assertEqual(
            mnemonics, ["LDI", "LDI", "LDI", "ADD", "SUB", "JNZ", "HALT"]
        )

    def test_program_loaded_at_nonzero_entry(self):
        cpu, result = run_example("add.rka", entry=0x100)
        self.assertEqual(result.status, "halted")
        self.assertEqual(cpu.registers.read(3), 12)
        self.assertEqual(cpu.registers.pc, 0x10C)  # HALT at 0x100 + 12

    def test_empty_image_halts_immediately(self):
        cpu = CPU()
        load_image(cpu, build_image(b""))
        result = cpu.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(result.steps, 1)  # zeroed memory is HALT


if __name__ == "__main__":
    unittest.main()
