"""The one authoritative ISA definition (spec section 5).

The assembler and the decoder both read this table -- if they ever
disagree, the table is wrong, not the modules. Instruction lengths are
derived from the operand list, never written by hand, so the table
cannot contradict itself about lengths.

Encoding scheme: first byte is the opcode, operand bytes follow in
order. Register operands are one byte (0-7). ``imm16``/``addr16`` are
two bytes, little-endian.
"""

from dataclasses import dataclass

REG = "reg"
IMM16 = "imm16"
ADDR16 = "addr16"

OPERAND_SIZES = {REG: 1, IMM16: 2, ADDR16: 2}


@dataclass(frozen=True)
class InstructionDef:
    """One row of the ISA table: what an instruction is."""

    opcode: int
    mnemonic: str
    operands: tuple  # operand kinds, in order

    @property
    def length(self):
        """Total instruction length in bytes, derived from operands."""
        return 1 + sum(OPERAND_SIZES[kind] for kind in self.operands)


@dataclass(frozen=True)
class Instruction:
    """One decoded instruction: what the CPU fetched at an address."""

    mnemonic: str
    opcode: int
    operands: tuple  # decoded operand values (ints)
    length: int
    address: int  # address it was fetched from


def _build_table():
    rows = [
        (0x00, "HALT", ()),
        (0x01, "NOP", ()),
        (0x02, "MOV", (REG, REG)),
        (0x03, "LDI", (REG, IMM16)),
        (0x04, "LOAD", (REG, ADDR16)),
        (0x05, "STORE", (REG, ADDR16)),
        (0x06, "ADD", (REG, REG, REG)),
        (0x07, "SUB", (REG, REG, REG)),
        (0x08, "MUL", (REG, REG, REG)),
        (0x09, "DIV", (REG, REG, REG)),
        (0x0A, "AND", (REG, REG, REG)),
        (0x0B, "OR", (REG, REG, REG)),
        (0x0C, "XOR", (REG, REG, REG)),
        (0x0D, "NOT", (REG, REG)),
        (0x0E, "SHL", (REG, REG, REG)),
        (0x0F, "SHR", (REG, REG, REG)),
        (0x10, "CMP", (REG, REG)),
        (0x11, "TEST", (REG, REG)),
        (0x12, "JMP", (ADDR16,)),
        (0x13, "JZ", (ADDR16,)),
        (0x14, "JNZ", (ADDR16,)),
        (0x15, "JC", (ADDR16,)),
        (0x16, "CALL", (ADDR16,)),
        (0x17, "RET", ()),
        (0x18, "PUSH", (REG,)),
        (0x19, "POP", (REG,)),
    ]
    return [InstructionDef(op, name, ops) for op, name, ops in rows]


INSTRUCTIONS = _build_table()

BY_OPCODE = {d.opcode: d for d in INSTRUCTIONS}
BY_MNEMONIC = {d.mnemonic: d for d in INSTRUCTIONS}


def definition_for_opcode(opcode):
    """ISA row for an opcode byte, or None for an unknown opcode."""
    return BY_OPCODE.get(opcode)


def definition_for_mnemonic(mnemonic):
    """ISA row for a mnemonic (case-insensitive), or None if unknown."""
    return BY_MNEMONIC.get(mnemonic.upper())
