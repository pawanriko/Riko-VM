"""Tests for the debugger (spec section 9)."""

import unittest

from rikovm.assembler import assemble
from rikovm.cpu import CPU
from rikovm.debugger import Debugger
from rikovm.errors import VMFault
from rikovm.loader import build_image


def debugger_with(source):
    debugger = Debugger(CPU())
    debugger.load(build_image(assemble(source)))
    return debugger


class TestDebugger(unittest.TestCase):
    def test_load_reports_entry_and_length(self):
        debugger = Debugger(CPU())
        info = debugger.load(build_image(assemble("HALT")))
        self.assertEqual(info, {"entry": 0, "length": 1})
        self.assertEqual(debugger.trace(), [])

    def test_step_executes_and_records_trace(self):
        debugger = debugger_with("LDI R1, 7\nHALT\n")
        entry = debugger.step()
        self.assertEqual(entry.mnemonic, "LDI")
        self.assertEqual(debugger.registers()["R1"], 7)
        self.assertEqual([e.mnemonic for e in debugger.trace()], ["LDI"])
        debugger.step()
        self.assertTrue(debugger.state()["halted"])
        self.assertEqual(len(debugger.trace()), 2)

    def test_run_records_full_trace(self):
        debugger = debugger_with("LDI R1, 7\nLDI R2, 5\nADD R3, R1, R2\nHALT\n")
        result = debugger.run()
        self.assertEqual(result.status, "halted")
        self.assertEqual(
            [e.mnemonic for e in debugger.trace()],
            ["LDI", "LDI", "ADD", "HALT"],
        )

    def test_load_clears_previous_trace(self):
        debugger = debugger_with("HALT\n")
        debugger.run()
        self.assertEqual(len(debugger.trace()), 1)
        debugger.load(build_image(assemble("HALT")))
        self.assertEqual(debugger.trace(), [])

    def test_registers_and_flags_inspection(self):
        debugger = debugger_with("LDI R1, 7\nHALT\n")
        debugger.step()
        self.assertEqual(debugger.registers()["R1"], 7)
        self.assertEqual(debugger.registers()["PC"], 4)
        self.assertEqual(
            debugger.flags(), {"Z": False, "C": False, "N": False, "V": False}
        )

    def test_memory_inspection(self):
        debugger = debugger_with("LDI R1, 7\nHALT\n")
        self.assertEqual(debugger.memory(0, 4), bytes([0x03, 0x01, 0x07, 0x00]))

    def test_memory_inspection_out_of_range_raises(self):
        debugger = debugger_with("HALT\n")
        with self.assertRaises(VMFault):
            debugger.memory(0xFFFF, 2)

    def test_state_snapshot(self):
        debugger = debugger_with("LDI R1, 7\nHALT\n")
        debugger.step()
        state = debugger.state()
        self.assertEqual(state["executed"], 1)
        self.assertFalse(state["halted"])
        self.assertEqual(state["registers"]["R1"], 7)


if __name__ == "__main__":
    unittest.main()
