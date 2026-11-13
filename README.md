# RikoVM

A software virtual computer: a simulated 16-bit CPU with registers,
flags, 64 KiB of memory, a custom instruction set, and a
fetch-decode-execute loop. Programs are written in RikoVM assembly,
assembled into machine code, loaded into virtual memory, and executed
by the virtual CPU — with a debugger to watch every step.

Built to understand how a computer actually executes programs. Not an
OS, not a hypervisor, not a wrapper around QEMU.

## Status

**M0 done — specification frozen, no code yet.** The full v1 rules live
in [`docs/spec.md`](docs/spec.md): machine state, flags, memory map,
the 26-instruction ISA table with exact encodings, the `RKP1` program
image format, fault behaviour, and the milestone plan. Code starts
after the spec is reviewed.

| Milestone | State |
|---|---|
| M0: Decisions (spec) | ✅ Done |
| M1: Machine state (registers, flags, memory) | Next |
| M2: CPU loop (LDI / ADD / HALT) | — |
| M3: Full ISA (26 instructions) | — |
| M4: Assembler | — |
| M5: Loader | — |
| M6: Debugger + CLI | — |
| M7: Hardening | — |

## Layout (planned)

```
rikovm/        # the VM core (no CLI imports here)
tests/         # stdlib unittest, one file per module
docs/          # spec.md — the frozen v1 contract
examples/      # .rka assembly programs
```

## Running tests (once M1 lands)

```sh
python3 -m unittest discover -s tests -v
```

Python 3, standard library only. Nothing to install.

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
