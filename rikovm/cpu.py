"""Virtual CPU: the fetch-decode-execute loop (spec section 4).

Implements the full 26-instruction ISA (spec section 5). Each
instruction has one handler in ``_HANDLERS``; the loop itself never
changes when instructions are added.

PC semantics: PC holds the address of the next instruction to fetch.
It advances at commit -- normally by the instruction length, or to a
branch target. After HALT, PC stays on the HALT instruction so the
debugger shows exactly where execution stopped.
"""

from dataclasses import dataclass, field

from .decoder import decode
from .errors import ArithmeticFault, StackFault, VMFault
from .flags import Flags
from .memory import Memory
from .registers import RegisterFile

MASK_16 = 0xFFFF
SIGN_BIT = 0x8000
STACK_BOTTOM = 0xF000  # lowest stack address (spec section 3.4)

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
            "HALT": self._exec_halt,
            "NOP": self._exec_nop,
            "MOV": self._exec_mov,
            "LDI": self._exec_ldi,
            "LOAD": self._exec_load,
            "STORE": self._exec_store,
            "ADD": self._exec_add,
            "SUB": self._exec_sub,
            "MUL": self._exec_mul,
            "DIV": self._exec_div,
            "AND": self._exec_and,
            "OR": self._exec_or,
            "XOR": self._exec_xor,
            "NOT": self._exec_not,
            "SHL": self._exec_shl,
            "SHR": self._exec_shr,
            "CMP": self._exec_cmp,
            "TEST": self._exec_test,
            "JMP": self._exec_jmp,
            "JZ": self._exec_jz,
            "JNZ": self._exec_jnz,
            "JC": self._exec_jc,
            "CALL": self._exec_call,
            "RET": self._exec_ret,
            "PUSH": self._exec_push,
            "POP": self._exec_pop,
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

    # -- Instruction handlers (full ISA, spec section 5) -----------------
    # Each handler returns the next PC, or None for the default
    # (current PC + instruction length). Handlers validate before they
    # mutate, so a fault never leaves partial state behind.

    def _exec_halt(self, instruction):
        self.halted = True
        return instruction.address  # PC stays on the HALT instruction

    def _exec_nop(self, instruction):
        return None

    def _exec_mov(self, instruction):
        rd, rs = instruction.operands
        self.registers.write(rd, self.registers.read(rs))
        return None  # flags unchanged

    def _exec_ldi(self, instruction):
        rd, immediate = instruction.operands
        self.registers.write(rd, immediate)
        return None  # flags unchanged

    def _exec_load(self, instruction):
        rd, address = instruction.operands
        self.registers.write(rd, self.memory.read_word(address))
        return None  # flags unchanged

    def _exec_store(self, instruction):
        rs, address = instruction.operands
        self.memory.write_word(address, self.registers.read(rs))
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

    def _sub_flags(self, a, b):
        """Set flags as if computing ``a - b``; return the result.

        Shared by SUB and CMP. Carry is ARM-style: C=1 means the
        subtraction did NOT borrow (a >= b unsigned).
        """
        result = (a - b) & MASK_16
        self.flags.c = a >= b
        # Signed overflow: operand signs differ, result sign differs
        # from the first operand's sign.
        self.flags.v = bool(((a ^ b) & (a ^ result)) & SIGN_BIT)
        self.flags.update_zn(result)
        return result

    def _exec_sub(self, instruction):
        rd, ra, rb = instruction.operands
        result = self._sub_flags(
            self.registers.read(ra), self.registers.read(rb)
        )
        self.registers.write(rd, result)
        return None

    def _exec_mul(self, instruction):
        rd, ra, rb = instruction.operands
        product = self.registers.read(ra) * self.registers.read(rb)
        result = product & MASK_16
        self.flags.v = product > MASK_16
        # C is unchanged by MUL.
        self.flags.update_zn(result)
        self.registers.write(rd, result)
        return None

    def _exec_div(self, instruction):
        rd, ra, rb = instruction.operands
        divisor = self.registers.read(rb)
        if divisor == 0:
            raise ArithmeticFault("division by zero")
        result = self.registers.read(ra) // divisor
        # C and V are unchanged by DIV.
        self.flags.update_zn(result)
        self.registers.write(rd, result)
        return None

    def _logic_result(self, result):
        """Shared flag update for logic ops: Z/N from result, C/V cleared."""
        self.flags.c = False
        self.flags.v = False
        self.flags.update_zn(result)
        return result

    def _exec_and(self, instruction):
        rd, ra, rb = instruction.operands
        result = self._logic_result(
            self.registers.read(ra) & self.registers.read(rb)
        )
        self.registers.write(rd, result)
        return None

    def _exec_or(self, instruction):
        rd, ra, rb = instruction.operands
        result = self._logic_result(
            self.registers.read(ra) | self.registers.read(rb)
        )
        self.registers.write(rd, result)
        return None

    def _exec_xor(self, instruction):
        rd, ra, rb = instruction.operands
        result = self._logic_result(
            self.registers.read(ra) ^ self.registers.read(rb)
        )
        self.registers.write(rd, result)
        return None

    def _exec_not(self, instruction):
        rd, ra = instruction.operands
        result = self._logic_result(~self.registers.read(ra) & MASK_16)
        self.registers.write(rd, result)
        return None

    def _exec_shl(self, instruction):
        rd, ra, rb = instruction.operands
        a = self.registers.read(ra)
        count = self.registers.read(rb) & 0xF
        if count == 0:
            result, carry = a, False
        else:
            result = (a << count) & MASK_16
            carry = bool((a >> (16 - count)) & 1)
        self.flags.c = carry
        self.flags.v = False
        self.flags.update_zn(result)
        self.registers.write(rd, result)
        return None

    def _exec_shr(self, instruction):
        rd, ra, rb = instruction.operands
        a = self.registers.read(ra)
        count = self.registers.read(rb) & 0xF
        if count == 0:
            result, carry = a, False
        else:
            result = a >> count
            carry = bool((a >> (count - 1)) & 1)
        self.flags.c = carry
        self.flags.v = False
        self.flags.update_zn(result)
        self.registers.write(rd, result)
        return None

    def _exec_cmp(self, instruction):
        ra, rb = instruction.operands
        self._sub_flags(self.registers.read(ra), self.registers.read(rb))
        return None  # no register is written

    def _exec_test(self, instruction):
        ra, rb = instruction.operands
        self._logic_result(self.registers.read(ra) & self.registers.read(rb))
        return None  # no register is written

    def _exec_jmp(self, instruction):
        (address,) = instruction.operands
        return address

    def _exec_jz(self, instruction):
        (address,) = instruction.operands
        return address if self.flags.z else None

    def _exec_jnz(self, instruction):
        (address,) = instruction.operands
        return address if not self.flags.z else None

    def _exec_jc(self, instruction):
        (address,) = instruction.operands
        return address if self.flags.c else None

    def _push(self, value):
        """Push a word: full-descending stack, overflow-checked first."""
        if self.registers.sp - 2 < STACK_BOTTOM:
            raise StackFault("stack overflow: stack is full")
        self.registers.sp -= 2
        self.memory.write_word(self.registers.sp, value)

    def _pop(self):
        """Pop a word: underflow-checked first."""
        if self.registers.sp == 0xFFFF:
            raise StackFault("stack underflow: pop from an empty stack")
        value = self.memory.read_word(self.registers.sp)
        self.registers.sp += 2
        return value

    def _exec_call(self, instruction):
        (address,) = instruction.operands
        # Return address: the instruction AFTER this CALL.
        self._push(instruction.address + instruction.length)
        return address

    def _exec_ret(self, instruction):
        return self._pop()

    def _exec_push(self, instruction):
        (rs,) = instruction.operands
        self._push(self.registers.read(rs))
        return None

    def _exec_pop(self, instruction):
        (rd,) = instruction.operands
        self.registers.write(rd, self._pop())
        return None
