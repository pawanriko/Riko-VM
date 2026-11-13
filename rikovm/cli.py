"""Command-line interface for RikoVM (spec section 9).

Usage (from the repository root):

    python3 -m rikovm assemble examples/add.rka -o build/add.rkp
    python3 -m rikovm run build/add.rkp
    python3 -m rikovm step build/add.rkp --steps 2
    python3 -m rikovm inspect registers build/add.rkp
    python3 -m rikovm inspect memory build/add.rkp 0x0100 32
    python3 -m rikovm trace build/add.rkp

Numbers accept decimal (``42``) or hex (``0x2A``). Exit code is 0 when
a program halts cleanly, 1 on faults and errors.
"""

import argparse
import sys

from .assembler import assemble
from .cpu import CPU, DEFAULT_MAX_STEPS
from .debugger import Debugger
from .errors import AssembleError, LoadError, VMFault
from .isa import ADDR16, IMM16, REG, definition_for_mnemonic
from .loader import build_image


def _parse_int(text):
    """Parse a CLI number: decimal or 0x-prefixed hex."""
    try:
        return int(text, 0)
    except ValueError:
        raise ValueError(f"not a number: {text!r}")


def _format_registers(state):
    regs = state["registers"]
    parts = [f"R{i}=0x{regs[f'R{i}']:04x}" for i in range(8)]
    parts.append(f"PC=0x{regs['PC']:04x}")
    parts.append(f"SP=0x{regs['SP']:04x}")
    return " ".join(parts)


def _format_flags(state):
    flags = state["flags"]
    return " ".join(f"{name}={int(flags[name])}" for name in ("Z", "C", "N", "V"))


def _format_operands(mnemonic, operands):
    definition = definition_for_mnemonic(mnemonic)
    if definition is None:
        return " ".join(str(o) for o in operands)
    parts = []
    for kind, value in zip(definition.operands, operands):
        if kind == REG:
            parts.append(f"R{value}")
        elif kind in (IMM16, ADDR16):
            parts.append(f"0x{value:04x}")
        else:
            parts.append(str(value))
    return ", ".join(parts)


def _format_entry(entry):
    rendered = _format_operands(entry.mnemonic, entry.operands)
    text = f"0x{entry.address:04x}: {entry.mnemonic}"
    if rendered:
        text += f" {rendered}"
    return text


def _format_memory(address, data):
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hexes = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"0x{address + offset:04x}: {hexes}")
    return "\n".join(lines)


def _fail(message):
    print(f"error: {message}", file=sys.stderr)
    return 1


def _read_file(path, binary):
    try:
        mode = "rb" if binary else "r"
        with open(path, mode, encoding=None if binary else "utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise VMFault(f"cannot read {path}: {exc.strerror or exc}")


def _load_debugger(image_path):
    debugger = Debugger(CPU())
    try:
        data = _read_file(image_path, binary=True)
        debugger.load(data)
    except (VMFault, LoadError) as exc:
        return None, str(exc)
    return debugger, None


def _cmd_assemble(args):
    try:
        entry = _parse_int(args.entry)
        source = _read_file(args.source, binary=False)
        code = assemble(source, entry=entry)
        image = build_image(code, entry=entry)
    except (ValueError, AssembleError, LoadError, VMFault) as exc:
        return _fail(str(exc))
    try:
        with open(args.output, "wb") as handle:
            handle.write(image)
    except OSError as exc:
        return _fail(f"cannot write {args.output}: {exc.strerror or exc}")
    print(f"assembled {len(code)} bytes, entry 0x{entry:04x} -> {args.output}")
    return 0


def _print_state(debugger):
    state = debugger.state()
    print(_format_registers(state))
    print(f"flags: {_format_flags(state)}")


def _cmd_run(args):
    debugger, error = _load_debugger(args.image)
    if error is not None:
        return _fail(error)
    try:
        max_steps = _parse_int(args.max_steps)
    except ValueError as exc:
        return _fail(str(exc))
    result = debugger.run(max_steps=max_steps)
    if result.status == "halted":
        print(f"halted after {result.steps} step(s)")
    elif result.status == "step_limit":
        print(f"step limit reached after {result.steps} step(s)")
    else:
        print(f"fault after {result.steps} step(s): {result.error}")
    _print_state(debugger)
    return 0 if result.status == "halted" else 1


def _cmd_step(args):
    debugger, error = _load_debugger(args.image)
    if error is not None:
        return _fail(error)
    try:
        count = _parse_int(args.steps)
    except ValueError as exc:
        return _fail(str(exc))
    for _ in range(count):
        if debugger.cpu.halted:
            print("halted")
            break
        try:
            entry = debugger.step()
        except VMFault as exc:
            print(f"fault: {exc}")
            _print_state(debugger)
            return 1
        print(_format_entry(entry))
        if debugger.cpu.halted:
            print("halted")
    _print_state(debugger)
    return 0


def _cmd_inspect(args):
    debugger, error = _load_debugger(args.image)
    if error is not None:
        return _fail(error)
    if args.what == "registers":
        _print_state(debugger)
        return 0
    try:
        address = _parse_int(args.address)
        length = _parse_int(args.length)
        data = debugger.memory(address, length)
    except (ValueError, VMFault) as exc:
        return _fail(str(exc))
    print(_format_memory(address, data))
    return 0


def _cmd_trace(args):
    debugger, error = _load_debugger(args.image)
    if error is not None:
        return _fail(error)
    try:
        max_steps = _parse_int(args.max_steps)
    except ValueError as exc:
        return _fail(str(exc))
    result = debugger.run(max_steps=max_steps)
    for entry in debugger.trace():
        print(_format_entry(entry))
    if result.status == "halted":
        print(f"halted after {result.steps} step(s)")
    elif result.status == "step_limit":
        print(f"step limit reached after {result.steps} step(s)")
    else:
        print(f"fault after {result.steps} step(s): {result.error}")
    _print_state(debugger)
    return 0 if result.status == "halted" else 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rikovm", description="RikoVM: a software virtual computer."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_assemble = sub.add_parser("assemble", help="assemble .rka source to a .rkp image")
    p_assemble.add_argument("source", help="assembly source file (.rka)")
    p_assemble.add_argument("-o", "--output", required=True, help="output image file (.rkp)")
    p_assemble.add_argument("--entry", default="0", help="load address (default: 0)")
    p_assemble.set_defaults(func=_cmd_assemble)

    p_run = sub.add_parser("run", help="load an image and run it")
    p_run.add_argument("image", help="program image file (.rkp)")
    p_run.add_argument("--max-steps", default=str(DEFAULT_MAX_STEPS))
    p_run.set_defaults(func=_cmd_run)

    p_step = sub.add_parser("step", help="execute one or more instructions")
    p_step.add_argument("image", help="program image file (.rkp)")
    p_step.add_argument("--steps", default="1", help="instructions to execute")
    p_step.set_defaults(func=_cmd_step)

    p_inspect = sub.add_parser("inspect", help="inspect a loaded image without running")
    inspect_sub = p_inspect.add_subparsers(dest="what", required=True)
    p_regs = inspect_sub.add_parser("registers", help="show registers and flags")
    p_regs.add_argument("image", help="program image file (.rkp)")
    p_mem = inspect_sub.add_parser("memory", help="show a memory range")
    p_mem.add_argument("image", help="program image file (.rkp)")
    p_mem.add_argument("address", help="start address")
    p_mem.add_argument("length", help="number of bytes")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_trace = sub.add_parser("trace", help="run and print every executed instruction")
    p_trace.add_argument("image", help="program image file (.rkp)")
    p_trace.add_argument("--max-steps", default=str(DEFAULT_MAX_STEPS))
    p_trace.set_defaults(func=_cmd_trace)

    return parser


def main(argv=None):
    """CLI entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    return args.func(args)
