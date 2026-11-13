"""Assembler: RikoVM assembly source (.rka) -> program bytes (spec 6).

Pipeline: source text -> lexer -> parser -> symbol table / label
resolution -> validation -> byte encoding. The ISA table in ``isa.py``
is the single source of truth for mnemonics, operand forms, and
encodings, so the assembler cannot drift from the decoder.

Source rules:
- One instruction per line; comments start with ``;``.
- Labels end with ``:`` and mark the address of the next instruction.
  A label may share a line with an instruction, or stand alone.
  Forward references (using a label before its definition) work.
- Mnemonics and registers are case-insensitive. Operands may be
  separated by commas, whitespace, or both.
- Numbers: decimal (``42``), hex (``0x2A``), binary (``0b101``), and
  negative immediates (``-1`` -> ``0xFFFF``). Immediates must fit in
  16 bits; addresses must be 0..0xFFFF.
- ``entry`` is the address the code will be loaded at, so absolute
  branch targets (labels) resolve to the right addresses.
"""

import re
from dataclasses import dataclass, field

from .errors import AssembleError
from .isa import ADDR16, IMM16, REG, definition_for_mnemonic

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
REGISTER = re.compile(r"[Rr]([0-7])\Z")
REGISTER_LIKE = re.compile(r"[Rr][0-9]+\Z")

MAX_PROGRAM_SIZE = 65536


@dataclass
class _Token:
    text: str
    column: int  # 1-based column where the token starts


@dataclass
class _ParsedLine:
    mnemonic: str
    operands: list  # list of _Token
    line: int
    column: int  # column of the mnemonic
    labels: list = field(default_factory=list)  # [(name, line, column)]
    address: int = 0  # assigned in pass 1


def _tokenize(line):
    """Split one source line into tokens, dropping comments.

    Commas are separators, like whitespace. Each token keeps the
    1-based column where it starts, for error messages.
    """
    code = line.split(";", 1)[0]
    code = code.replace(",", " ")
    return [_Token(m.group(0), m.start() + 1) for m in re.finditer(r"\S+", code)]


def _parse_lines(source):
    """Lexer + parser: source text -> list of _ParsedLine.

    Validates mnemonics and operand counts here; operand VALUES are
    resolved in pass 2, once labels are known.
    """
    parsed = []
    pending_labels = []
    for line_no, raw_line in enumerate(source.splitlines(), start=1):
        tokens = _tokenize(raw_line)
        if not tokens:
            continue
        first = tokens[0]
        if first.text.endswith(":"):
            name = first.text[:-1]
            if not IDENTIFIER.match(name):
                raise AssembleError(
                    f"invalid label name {name!r}", line_no, first.column
                )
            pending_labels.append((name, line_no, first.column))
            tokens = tokens[1:]
            if not tokens:
                continue  # label-only line
        mnemonic_token = tokens[0]
        definition = definition_for_mnemonic(mnemonic_token.text)
        if definition is None:
            raise AssembleError(
                f"unknown mnemonic {mnemonic_token.text!r}",
                line_no,
                mnemonic_token.column,
            )
        operands = tokens[1:]
        if len(operands) != len(definition.operands):
            raise AssembleError(
                f"{definition.mnemonic} takes {len(definition.operands)} "
                f"operand(s), got {len(operands)}",
                line_no,
                mnemonic_token.column,
            )
        parsed.append(
            _ParsedLine(
                mnemonic=definition.mnemonic,
                operands=operands,
                line=line_no,
                column=mnemonic_token.column,
                labels=pending_labels,
            )
        )
        pending_labels = []
    return parsed, pending_labels


def _resolve_operand(token, kind, symbols, line):
    """Resolve one operand token to its integer value."""
    text = token.text
    if kind == REG:
        match = REGISTER.match(text)
        if match is None:
            raise AssembleError(
                f"expected a register (R0-R7), got {text!r}", line, token.column
            )
        return int(match.group(1))
    # IMM16 / ADDR16: a number, or a label.
    try:
        value = int(text, 0)
    except ValueError:
        value = None
    if value is not None:
        if kind == IMM16:
            if not -32768 <= value <= 65535:
                raise AssembleError(
                    f"immediate {value} does not fit in 16 bits",
                    line,
                    token.column,
                )
            return value & 0xFFFF
        if not 0 <= value <= 0xFFFF:
            raise AssembleError(
                f"address {value} is out of range 0..0xFFFF", line, token.column
            )
        return value
    if REGISTER_LIKE.match(text):
        raise AssembleError(
            f"register {text!r} used where a number or label was expected",
            line,
            token.column,
        )
    if text in symbols:
        return symbols[text]
    raise AssembleError(f"unknown label {text!r}", line, token.column)


def assemble(source, entry=0x0000):
    """Assemble ``source`` text into program bytes loadable at ``entry``.

    Raises AssembleError with line/column on any problem.
    """
    if not 0 <= entry <= 0xFFFF:
        raise AssembleError(f"entry point {entry:#x} is out of range")
    parsed, trailing_labels = _parse_lines(source)

    # Pass 1: assign addresses, build the symbol table.
    symbols = {}
    address = entry
    for line in parsed:
        line.address = address
        for name, def_line, def_col in line.labels:
            if name in symbols:
                raise AssembleError(
                    f"duplicate label {name!r}", def_line, def_col
                )
            symbols[name] = address
        address += definition_for_mnemonic(line.mnemonic).length
    for name, def_line, def_col in trailing_labels:
        if name in symbols:
            raise AssembleError(f"duplicate label {name!r}", def_line, def_col)
        symbols[name] = address  # label at end of code: address past last byte
    if address - entry > MAX_PROGRAM_SIZE or address > 0x10000:
        raise AssembleError("program does not fit in 64 KiB of memory")

    # Pass 2: encode.
    out = bytearray()
    for line in parsed:
        definition = definition_for_mnemonic(line.mnemonic)
        out.append(definition.opcode)
        for token, kind in zip(line.operands, definition.operands):
            value = _resolve_operand(token, kind, symbols, line.line)
            if kind == REG:
                out.append(value)
            else:
                out.append(value & 0xFF)
                out.append((value >> 8) & 0xFF)
    return bytes(out)
