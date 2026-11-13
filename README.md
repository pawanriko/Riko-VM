# RikoVM

A software virtual computer: a simulated 16-bit CPU with registers,
flags, 64 KiB of memory, a custom instruction set, and a
fetch-decode-execute loop. Programs are written in RikoVM assembly,
assembled into machine code, loaded into virtual memory, and executed
by the virtual CPU — with a debugger to watch every step.

Built to understand how a computer actually executes programs. Not an
OS, not a hypervisor, not a wrapper around QEMU.

## Status

**All milestones M0–M7 done.** The full v1 machine is implemented and
tested: 26 instructions, assembler, loader, debugger, and CLI.

| Milestone | State |
|---|---|
| M0: Decisions (spec) | ✅ Done |
| M1: Machine state (registers, flags, memory) | ✅ Done |
| M2: CPU loop (LDI / ADD / HALT) | ✅ Done |
| M3: Full ISA (26 instructions) | ✅ Done |
| M4: Assembler | ✅ Done |
| M5: Loader | ✅ Done |
| M6: Debugger + CLI | ✅ Done |
| M7: Hardening | ✅ Done |

The frozen v1 rules live in [`docs/spec.md`](docs/spec.md): machine
state, flag semantics, memory map, the ISA table with exact encodings,
the `RKP1` program image format, fault behaviour, and the test plan.

## Quickstart

Python 3, standard library only. Nothing to install.

```sh
# Assemble an example into a program image
python3 -m rikovm assemble examples/add.rka -o build/add.rkp

# Run it
python3 -m rikovm run build/add.rkp

# See every executed instruction
python3 -m rikovm trace build/add.rkp

# Execute one instruction at a time
python3 -m rikovm step build/add.rkp --steps 2

# Inspect a loaded image without running it
python3 -m rikovm inspect registers build/add.rkp
python3 -m rikovm inspect memory build/add.rkp 0x0000 16
```

## The idea in 30 seconds

```asm
; add.rka — load 7 and 5, add them, halt
LDI R1, 7
LDI R2, 5
ADD R3, R1, R2
HALT
```

Assemble it, load it, run it, inspect `R3` — and prove from the trace
that the VM really executed the instructions. That proof is the whole
point of the project.

## Examples

| File | What it shows | Expected result |
|---|---|---|
| `examples/add.rka` | Load, add, halt | `R3 == 12` |
| `examples/countdown.rka` | Loop + conditional branch | `R2 == 15` |
| `examples/factorial.rka` | Multiply loop | `R2 == 120` |
| `examples/stack.rka` | `CALL`/`RET`, `PUSH`/`POP` | `R1 == 84`, stack empty |
| `examples/memory.rka` | `STORE`/`LOAD` | `R2 == 0xBEEF` |

## Layout

```
rikovm/            # the VM core (never imports the CLI)
  errors.py        # fault hierarchy
  flags.py         # Z/C/N/V status flags
  registers.py     # R0-R7, PC, SP
  memory.py        # 64 KiB, little-endian, bounds-checked
  isa.py           # the one authoritative ISA table
  decoder.py       # bytes -> validated Instruction
  cpu.py           # fetch-decode-execute loop + all 26 handlers
  assembler.py     # .rka source -> program bytes
  loader.py        # RKP1 image format + loader
  debugger.py      # step / inspect / trace
  cli.py           # assemble / run / step / inspect / trace
tests/             # stdlib unittest, one file per module + integration
docs/              # spec.md — the frozen v1 contract
examples/          # .rka assembly programs
```

## Tests

```sh
python3 -m unittest discover -s tests -v
```

167 tests: unit tests per module, golden encoding tests locking the
ISA table (assembler output must equal the spec's bytes, and the
decoder must read them back), fault and boundary cases, and
end-to-end runs of every example.

## Deliberately not in v1

No I/O, no GUI, no memory protection, no relative branches, no
register-immediate arithmetic, no breakpoints, no JIT. Clarity and
correctness beat speed — see `docs/spec.md` section 13.
