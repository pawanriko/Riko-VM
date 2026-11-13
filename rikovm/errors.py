"""Fault hierarchy for RikoVM (spec section 10).

Every VM-level error is a ``VMFault``. Faults are data, not crashes: the
run loop catches them, reports the outcome, and the debugger can show
the machine state at the fault. A fault never leaves a half-written
instruction behind -- instructions validate before they mutate.
"""


class VMFault(Exception):
    """Base class for all RikoVM faults."""


class DecodeFault(VMFault):
    """Unknown opcode, invalid register byte, or truncated instruction."""


class MemoryFault(VMFault):
    """Out-of-range memory access, or a word straddling 0xFFFF."""


class StackFault(VMFault):
    """Stack overflow (below 0xF000) or underflow (pop from empty stack)."""


class ArithmeticFault(VMFault):
    """Division by zero."""


class LoadError(VMFault):
    """Bad program image: bad magic, truncation, or oversize."""


class AssembleError(Exception):
    """Assembly failure, carrying the source line/column of the problem.

    This is deliberately NOT a VMFault: it happens before any machine
    exists, while translating source text. The message always names the
    line and column so the programmer can find the mistake.
    """

    def __init__(self, message, line=None, column=None):
        self.line = line
        self.column = column
        if line is not None:
            where = f"line {line}"
            if column is not None:
                where += f", column {column}"
            message = f"{where}: {message}"
        super().__init__(message)
