"""Virtual CPU: the fetch-decode-execute loop (spec section 4).

M2 implements the loop plus the tiny initial subset: LDI, ADD, HALT.
M3 adds the remaining handlers to ``_HANDLERS``; the loop itself does
not change.

PC semantics: PC holds the address of the next instruction to fetch.
It advances at commit -- normally by the instruction length, or to a
branch target. After HALT, PC stays on the HALT instruction so the
debugger shows exactly where execution stopped.
"""

from dataclasses import dataclass, field

from .decoder import decode
from .errors import VMFault
from .flags import Flags
from .memory import Memory
from .registers import RegisterFile

MASK_16 = 0xFFFF
SIGN_BIT = 0x8000

DEFAULT_MAX_STEPS = 1_000_000


@dataclass
class TraceEntry:
    """One executed instruction, for the tracer and debugger."""

    address: int
    mnemonic: str
    operands: tuple
    length: int


@dataclass
class RunResult:
    """Outcome of ``CPU.run``: exactly one status, always."""

    status: str  # "halted" | "fault" | "step_limit"
    steps: int  # instructions completed (a faulting one is not counted)
    error: str | None = None
    trace: list = field(default_factory=list)


class CPU:
    """Owns registers, flags, and memory; executes instructions."""

    def __init__(self, memory=None, registers=None, flags=None):
        self.memory = memory if memory is not None else Memory()
        self.registers = registers if registers is not None else RegisterFile()
        self.flags = flags if flags is not None else Flags()
        self.halted = False
        self.executed_count = 0
        self._handlers = {
            "LDI": self._exec_ldi,
            "ADD": self._exec_add,
            "HALT": self._exec_halt,
        }

    def reset(self, entry=0x0000):
        """Reset CPU state; memory is untouched (the loader fills it)."""
        self.registers.reset(entry)
        self.flags.reset()
        self.halted = False
        self.executed_count = 0

    def step(self):
        """Fetch, decode, and execute one instruction.

        Returns a TraceEntry. Raises VMFault on any fault, and raises
        VMFault if the CPU has halted (reset before stepping again).
        """
        if self.halted:
            raise VMFault("CPU is halted; reset before stepping again")
        pc = self.registers.pc
        instruction = decode(self.memory, pc)
        handler = self._handlers.get(instruction.mnemonic)
        if handler is None:
            raise VMFault(f"unimplemented instruction: {instruction.mnemonic}")
        next_pc = handler(instruction)
        if next_pc is None:
            next_pc = (pc + instruction.length) & MASK_16
        self.registers.pc = next_pc
        self.executed_count += 1
        return TraceEntry(
            address=pc,
            mnemonic=instruction.mnemonic,
            operands=instruction.operands,
            length=instruction.length,
        )

    def run(self, max_steps=DEFAULT_MAX_STEPS, trace=False):
        """Run until HALT, a fault, or the step limit.

        Never raises for VM faults: they come back as a RunResult with
        status "fault" so callers can inspect the state at the fault.
        """
        entries = []
        steps = 0
        while not self.halted:
            if steps >= max_steps:
                return RunResult(
                    status="step_limit",
                    steps=steps,
                    error=f"step limit ({max_steps}) reached",
                    trace=entries,
                )
            try:
                entry = self.step()
            except VMFault as exc:
                return RunResult(
                    status="fault", steps=steps, error=str(exc), trace=entries
                )
            steps += 1
            if trace:
                entries.append(entry)
        return RunResult(status="halted", steps=steps, trace=entries)

    def snapshot(self):
        """Full inspectable CPU state, for the debugger (read-only view)."""
        return {
            "registers": self.registers.dump(),
            "flags": self.flags.as_dict(),
            "halted": self.halted,
            "executed": self.executed_count,
        }

    # -- Instruction handlers (M2 subset) --------------------------------
    # Each handler returns the next PC, or None for the default
    # (current PC + instruction length). Handlers validate before they
    # mutate, so a fault never leaves partial state behind.

    def _exec_ldi(self, instruction):
        rd, immediate = instruction.operands
        self.registers.write(rd, immediate)
        return None  # flags unchanged

    def _exec_add(self, instruction):
        rd, ra, rb = instruction.operands
        a = self.registers.read(ra)
        b = self.registers.read(rb)
        total = a + b
        result = total & MASK_16
        self.flags.c = total > MASK_16
        # Signed overflow: operands had the same sign, result differs.
        self.flags.v = bool((~(a ^ b) & (a ^ result)) & SIGN_BIT)
        self.flags.update_zn(result)
        self.registers.write(rd, result)
        return None

    def _exec_halt(self, instruction):
        self.halted = True
        return instruction.address  # PC stays on the HALT instruction
