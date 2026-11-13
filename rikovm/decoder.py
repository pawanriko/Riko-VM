"""Instruction decoder (spec sections 4-5).

Reads instruction bytes at an address and turns them into a validated
``Instruction``. Anything malformed -- unknown opcode, register byte
outside 0-7, bytes running past the end of memory -- is a DecodeFault
raised BEFORE anything executes, so a bad instruction can never
half-run.
"""

from .errors import DecodeFault, MemoryFault
from .isa import ADDR16, IMM16, REG, Instruction, definition_for_opcode


def decode(memory, address):
    """Decode the instruction stored at ``address`` in ``memory``."""
    opcode = memory.read_byte(address)
    definition = definition_for_opcode(opcode)
    if definition is None:
        raise DecodeFault(f"unknown opcode {opcode:#04x} at {address:#06x}")

    operands = []
    pos = address + 1
    try:
        for kind in definition.operands:
            if kind == REG:
                value = memory.read_byte(pos)
                pos += 1
                if value > 7:
                    raise DecodeFault(
                        f"invalid register byte {value} in "
                        f"{definition.mnemonic} at {address:#06x} "
                        "(registers are R0-R7)"
                    )
                operands.append(value)
            elif kind in (IMM16, ADDR16):
                low = memory.read_byte(pos)
                high = memory.read_byte(pos + 1)
                pos += 2
                operands.append(low | (high << 8))
            else:  # pragma: no cover - the ISA table only uses known kinds
                raise DecodeFault(f"unknown operand kind {kind!r}")
    except MemoryFault as exc:
        raise DecodeFault(
            f"truncated {definition.mnemonic} at {address:#06x}: "
            "instruction bytes run past the end of memory"
        ) from exc

    return Instruction(
        mnemonic=definition.mnemonic,
        opcode=opcode,
        operands=tuple(operands),
        length=definition.length,
        address=address,
    )
