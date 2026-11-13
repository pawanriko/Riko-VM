"""Register file for the RikoVM CPU (spec section 3.1).

Eight general-purpose 16-bit registers, R0-R7. R0 has no special role:
all eight behave identically. The program counter (PC) and stack
pointer (SP) live here too, since they are part of CPU state.

Every write is masked to 16 bits, so a register can never hold a value
outside 0x0000-0xFFFF.
"""

MASK_16 = 0xFFFF
NUM_REGISTERS = 8
STACK_TOP = 0xFFFF  # SP value for an empty stack (spec section 3.4)


class RegisterFile:
    """R0-R7 plus PC and SP."""

    def __init__(self):
        self._regs = [0] * NUM_REGISTERS
        self._pc = 0
        self._sp = STACK_TOP

    def reset(self, entry=0x0000):
        """Zero all registers, point PC at the entry point, empty the stack."""
        self._regs = [0] * NUM_REGISTERS
        self._pc = entry & MASK_16
        self._sp = STACK_TOP

    def read(self, index):
        """Read register ``index`` (0-7)."""
        self._check_index(index)
        return self._regs[index]

    def write(self, index, value):
        """Write ``value`` to register ``index`` (0-7), masked to 16 bits."""
        self._check_index(index)
        self._regs[index] = value & MASK_16

    @staticmethod
    def _check_index(index):
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError(f"register index must be an int, got {index!r}")
        if not 0 <= index < NUM_REGISTERS:
            raise ValueError(
                f"invalid register index {index}: registers are R0-R7"
            )

    @property
    def pc(self):
        """Program counter: address of the next instruction to fetch."""
        return self._pc

    @pc.setter
    def pc(self, value):
        self._pc = value & MASK_16

    @property
    def sp(self):
        """Stack pointer: address of the top word, or 0xFFFF when empty."""
        return self._sp

    @sp.setter
    def sp(self, value):
        self._sp = value & MASK_16

    def dump(self):
        """Full CPU register state as a plain dict, for the debugger."""
        state = {f"R{i}": self._regs[i] for i in range(NUM_REGISTERS)}
        state["PC"] = self._pc
        state["SP"] = self._sp
        return state

    def __repr__(self):
        regs = " ".join(f"R{i}={v:#06x}" for i, v in enumerate(self._regs))
        return f"RegisterFile({regs} PC={self._pc:#06x} SP={self._sp:#06x})"
