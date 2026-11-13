"""Debugger: step, inspect, and trace a loaded program (spec section 9).

The debugger only inspects through read-only accessors: it never
mutates CPU internals directly. All state changes happen through the
CPU's own step/run/load operations.
"""

from .cpu import DEFAULT_MAX_STEPS
from .loader import load_image


class Debugger:
    """Wraps a CPU with load/step/run and a persistent trace log."""

    def __init__(self, cpu):
        self.cpu = cpu
        self.trace_log = []

    def load(self, data):
        """Load a program image; clears the trace log. Returns load info."""
        info = load_image(self.cpu, data)
        self.trace_log = []
        return info

    def step(self):
        """Execute one instruction; record it in the trace log."""
        entry = self.cpu.step()
        self.trace_log.append(entry)
        return entry

    def run(self, max_steps=DEFAULT_MAX_STEPS):
        """Run to completion, recording every instruction in the trace."""
        result = self.cpu.run(max_steps=max_steps, trace=True)
        self.trace_log.extend(result.trace)
        return result

    def registers(self):
        """Register state (PC/SP included) as a plain dict."""
        return self.cpu.snapshot()["registers"]

    def flags(self):
        """Flag state as a plain dict."""
        return self.cpu.snapshot()["flags"]

    def memory(self, address, length):
        """``length`` bytes of memory starting at ``address``."""
        return self.cpu.memory.read_bytes(address, length)

    def state(self):
        """Full CPU snapshot: registers, flags, halted, executed count."""
        return self.cpu.snapshot()

    def trace(self):
        """The trace log so far (a copy; entries are immutable)."""
        return list(self.trace_log)
