# RikoVM Specification — v1 (M0 Freeze)

*Status: M0 — decisions frozen in this document on 14 Nov 2026. No code
written yet. Every decision below is Riko's proposal, written to be
reviewed: Pawan can overturn any line in one message, and the doc gets
updated before the affected milestone is built. Nothing here is
implemented until a milestone says so.*

*Source intent: `RikoVM_AI_Project_Explanation.pdf` (project brief,
13 Nov 2026). This spec turns the brief's proposed baseline and open
questions into frozen v1 rules.*

## 1. What RikoVM is

RikoVM is a software virtual computer: a simulated 16-bit CPU with
registers, flags, 64 KiB of memory, a custom instruction set (ISA), and
a fetch-decode-execute loop. Programs are written in RikoVM assembly
(`.rka`), assembled into machine code, loaded into virtual memory, and
executed by the virtual CPU. A debugger and CLI expose registers,
memory, and execution traces.

It is NOT an operating system, a hypervisor, or a wrapper around QEMU,
VirtualBox, Docker, or any real hardware. It has no I/O in v1.

## 2. Host implementation (decided)

| Decision | Rule | Why |
|---|---|---|
| Host language | Python 3, standard library only, zero dependencies | Pawan's choice; speed does not matter for a learning VM; zero-install keeps the project readable and runnable anywhere |
| Layout | Flat package: `rikovm/` at repo root, plus `tests/`, `docs/`, `examples/` | Fewest nesting levels; every file is one obvious idea, readable file by file |
| Tests | Python stdlib `unittest`, run from repo root: `python3 -m unittest discover -s tests -v` | No test framework to install; deterministic, no network |
| Module boundary | VM core never imports the CLI; the CLI only calls public core interfaces | The brief's core rule: the CPU must be usable and testable without any CLI |

## 3. Machine state (M1)

### 3.1 Registers

- 8 general-purpose registers, `R0`–`R7`, each 16-bit (values `0x0000`–`0xFFFF`).
- **R0 has no special role.** All eight registers behave identically.
  (Simpler to learn, simpler to test; a zero-register is a v2 idea, not v1.)
- Writes are masked to 16 bits: writing `0x10000` stores `0x0000`.
- Register operand bytes in instructions must be `0`–`7`; `8`–`255`
  is a decode fault (see §7).
- `PC` (program counter), 16-bit. `SP` (stack pointer), 16-bit.
- Reset state: all registers `0`, PC = entry point, SP = `0xFFFF`,
  all flags clear.

### 3.2 Flags

Four status flags: `Z` (zero), `C` (carry), `N` (negative), `V` (overflow).
Update rules per operation family (exact semantics — the decoder and the
tests both follow this table):

| Operation | Z | N | C | V |
|---|---|---|---|---|
| ADD / SUB / CMP | result == 0 | bit 15 of result | ADD: carry out of bit 15. SUB/CMP: `1` when no borrow (Ra >= Rb unsigned), `0` when borrow | signed overflow |
| MUL | result == 0 | bit 15 of result | unchanged | `1` when full product > `0xFFFF` |
| DIV | result == 0 | bit 15 of result | unchanged | unchanged |
| AND / OR / XOR / NOT / TEST | result == 0 | bit 15 of result | cleared (`0`) | cleared (`0`) |
| SHL / SHR | result == 0 | bit 15 of result | last bit shifted out; `0` when shift count is `0` | cleared (`0`) |
| MOV / LDI / LOAD / STORE / JMP / JZ / JNZ / JC / CALL / RET / PUSH / POP / NOP / HALT | unchanged | unchanged | unchanged | unchanged |

Notes:
- The SUB/CMP carry convention is ARM-style: `C=1` means "no borrow".
  `JC` therefore jumps when the last subtraction did not borrow. This
  is a deliberate choice, documented here so it never gets flipped
  by accident.
- `CMP`/`TEST` compute and set flags but discard the result and write
  no register.
- Shift count is the low 4 bits of the shift register (`Rb & 0xF`),
  i.e. `0`–`15`. A count of `0` leaves the value unchanged, sets Z/N
  from it, and clears C.

### 3.3 Memory

- 64 KiB, byte-addressed, addresses `0x0000`–`0xFFFF`.
- Multi-byte values are little-endian: the low byte lives at the lower
  address. A word read at `0x0100` returns
  `memory[0x0100] | (memory[0x0101] << 8)`.
- Every access is bounds-checked. A byte access at `0x10000`, or a word
  access starting at `0xFFFF` (its second byte would be `0x10000`), is
  a memory fault. There is no wraparound.
- v1 memory model is **flat**: no protection, no paging. Regions below
  are conventions the loader and stack follow, not hardware-enforced
  boundaries (except the stack limits in §3.4, which ARE enforced).

### 3.4 Memory map and stack (v1, by convention)

| Range | Use |
|---|---|
| `0x0000`–`0x7FFF` | Code + data. The loader places the program at the entry point (default `0x0000`). |
| `0x8000`–`0xEFFF` | Free / data. Nothing reserved in v1. |
| `0xF000`–`0xFFFF` | Stack region. Grows downward from the top. |

Stack rules (full-descending, enforced):
- `SP` starts at `0xFFFF` (empty stack).
- `PUSH Rs`: if `SP - 2 < 0xF000`, stack-overflow fault (before any
  write). Otherwise `SP -= 2`, then write the word at `SP`.
- `POP Rd`: if `SP == 0xFFFF`, stack-underflow fault. Otherwise read
  the word at `SP`, then `SP += 2`.
- `CALL` pushes the return address (the address of the instruction
  AFTER the CALL) using the same PUSH rules; `RET` pops it into PC
  using the same POP rules. A `RET` with an empty stack faults.

## 4. Fetch-decode-execute cycle (M2)

1. **FETCH** — read instruction bytes starting at `PC`.
2. **DECODE** — identify opcode, operand forms, and total length from
   the ISA table (§5). Unknown opcode, invalid register byte, or bytes
   running past `0xFFFF` is a fault before anything executes.
3. **VALIDATE** — operand encodings and memory addresses are checked
   during decode/execute; any violation faults without partial state
   change (an instruction either completes fully or faults — it never
   half-writes and then faults).
4. **EXECUTE** — perform the operation on CPU + memory state.
5. **COMMIT** — update destination, flags, and PC together. **PC
   advances at commit**: for normal instructions, `PC += length`; for
   taken branches/calls/returns, PC is set to the target.
6. **REPEAT** — stop on HALT, a fault, or the step limit.

Run outcomes (the CLI reports exactly one of these):
- `HALTED` — a HALT instruction executed. Clean stop.
- `FAULT: <message>` — decode, memory, stack, or arithmetic fault,
  with the PC and a human-readable reason. The host process never
  crashes; the fault is data the debugger shows.
- `STEP_LIMIT` — the run exceeded the maximum step count (default
  1,000,000, configurable). Prevents infinite loops hanging the CLI.

Deliberate emergent behaviour: `HALT` is opcode `0x00`, and memory
starts zeroed — so a program that runs off the end of its code into
empty memory halts instead of executing garbage. Zero memory is safe
memory.

## 5. Instruction Set Architecture (ISA) — frozen v1 table

Encoding scheme: the first byte is the opcode; operand bytes follow in
the order listed. Register operands are one byte each (`0`–`7`).
`imm16`/`addr16` are two bytes, little-endian (low byte first).
`len` is the total instruction length in bytes.

| Opcode | Mnemonic | Format | Len | Semantics | Flags |
|---|---|---|---|---|---|
| `0x00` | HALT | — | 1 | Stop execution cleanly. | — |
| `0x01` | NOP | — | 1 | Do nothing. | — |
| `0x02` | MOV Rd, Rs | `op rd rs` | 3 | `Rd = Rs` | — |
| `0x03` | LDI Rd, imm16 | `op rd lo hi` | 4 | `Rd = imm16` | — |
| `0x04` | LOAD Rd, addr16 | `op rd lo hi` | 4 | `Rd = mem16[addr]` | — |
| `0x05` | STORE Rs, addr16 | `op rs lo hi` | 4 | `mem16[addr] = Rs` | — |
| `0x06` | ADD Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra + Rb` (mod 2^16) | Z N C V |
| `0x07` | SUB Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra - Rb` (mod 2^16) | Z N C V |
| `0x08` | MUL Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = (Ra * Rb) & 0xFFFF` | Z N V |
| `0x09` | DIV Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra // Rb`; `Rb == 0` faults | Z N |
| `0x0A` | AND Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra & Rb` | Z N, C/V=0 |
| `0x0B` | OR Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra \| Rb` | Z N, C/V=0 |
| `0x0C` | XOR Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra ^ Rb` | Z N, C/V=0 |
| `0x0D` | NOT Rd, Ra | `op rd ra` | 3 | `Rd = ~Ra & 0xFFFF` | Z N, C/V=0 |
| `0x0E` | SHL Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = (Ra << (Rb & 0xF)) & 0xFFFF` | Z N C, V=0 |
| `0x0F` | SHR Rd, Ra, Rb | `op rd ra rb` | 4 | `Rd = Ra >> (Rb & 0xF)` (logical) | Z N C, V=0 |
| `0x10` | CMP Ra, Rb | `op ra rb` | 3 | Flags as `Ra - Rb`; no write | Z N C V |
| `0x11` | TEST Ra, Rb | `op ra rb` | 3 | Flags as `Ra & Rb`; no write | Z N, C/V=0 |
| `0x12` | JMP addr16 | `op lo hi` | 3 | `PC = addr` | — |
| `0x13` | JZ addr16 | `op lo hi` | 3 | `if Z: PC = addr` | — |
| `0x14` | JNZ addr16 | `op lo hi` | 3 | `if not Z: PC = addr` | — |
| `0x15` | JC addr16 | `op lo hi` | 3 | `if C: PC = addr` | — |
| `0x16` | CALL addr16 | `op lo hi` | 3 | Push return address; `PC = addr` | — |
| `0x17` | RET | — | 1 | `PC = pop()` | — |
| `0x18` | PUSH Rs | `op rs` | 2 | Push `Rs` (§3.4) | — |
| `0x19` | POP Rd | `op rd` | 2 | `Rd = pop()` (§3.4) | — |

Frozen rules around this table:
- **Branches are absolute addresses in v1** (simpler to assemble,
  debug, and test; relative offsets are a v2 addition, not a v1 gap).
- **ADD/SUB/etc. are register-register only in v1.** Immediates reach
  registers only through `LDI`. (A register-immediate `ADDI` is the
  obvious v2 extension; v1 stays small enough to test thoroughly.)
- **DIV by zero is a fault**, not a wrap or a zero result.
- **Arithmetic wraps modulo 2^16**; overflow is reported via flags,
  never by raising.
- **One authoritative ISA definition.** The assembler and the decoder
  share one table (one Python module). If they ever disagree, the
  table is wrong, not the modules. Golden encoding tests (§8) lock
  the table: each instruction has a test asserting its exact bytes.

## 6. Assembly language and assembler (M4)

- Source files use `.rka`. One instruction per line; comments start
  with `;`. Labels end with `:` and mark the address of the next
  instruction. Registers are `R0`–`R7` (case-insensitive mnemonics,
  case-insensitive registers). Numbers: decimal (`42`), hex (`0x2A`),
  and negative immediates (`-1` → `0xFFFF`, range-checked to fit 16 bits).
- Example (the acceptance program, §8):
  ```asm
  ; add.rka — load 7 and 5, add them, halt
  LDI R1, 7
  LDI R2, 5
  ADD R3, R1, R2
  HALT
  ```
- Assembler pipeline: source text → lexer → parser → symbol table /
  label resolution → validation → byte encoding → program image (§7).
- Diagnostics carry line and column numbers for invalid mnemonics,
  malformed operands, out-of-range immediates, and unresolved labels.
- The assembler accepts forward label references (labels used before
  they are defined) — two-pass assembly.

## 7. Program image and loader (M5)

v1 image format ("RKP1"), all multi-byte fields little-endian:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | Magic bytes: `RKP1` (`0x52 0x4B 0x50 0x31`) |
| 4 | 2 | Entry point address |
| 6 | 2 | Code length in bytes (must equal the remaining file size) |
| 8 | N | Code bytes |

Loader rules:
- Reject bad magic, truncated headers, and length mismatches with a
  clear load error (never a crash, never a partial load).
- Reject `entry + length > 0x10000` (code must fit in memory).
- On success: copy code bytes to memory at `entry`, set PC to `entry`,
  reset registers/flags/SP (§3.1), and report the loaded range.
- Code memory is writable after loading in v1 (flat model, §3.3) —
  self-modifying code is possible and not special-cased.

## 8. Correctness, testing, acceptance (all milestones)

- Every instruction and state transition has deterministic tests:
  known initial state in, exact expected final state out.
- **Golden encoding tests**: for every ISA row, one test asserting the
  assembler emits exactly the bytes in §5, and one asserting the
  decoder reads those bytes back to the same instruction. This is the
  mitigation for the #1 risk (assembler/decoder drift).
- Module tests: registers (masking, invalid indices), flags (every
  row of §3.2), memory (byte/word, endianness, `0x0000`/`0xFFFF`
  boundaries, word-at-`0xFFFF` fault, out-of-range), decoder
  (truncated instructions, unknown opcodes, bad register bytes),
  execution (result values, flags, PC movement, fault cases),
  assembler (labels incl. forward refs, literals, syntax errors with
  line/col, exact bytes), loader (bad magic, truncation, oversize).
- Integration tests: assemble a real program, load it, run it, verify
  final registers + trace.
- Regression rule: every bug fix adds a test that would have caught
  the bug.
- **Minimum end-to-end acceptance test**: assemble `add.rka` (§6),
  load it, execute it, and prove via register inspection and trace
  that `R3 == 12` because the VM executed the instructions — not
  because anything printed a canned result.

## 9. Debugger and CLI (M6)

v1 commands (names frozen here; exact flags follow in M6):

```
rikovm assemble examples/add.rka -o build/add.rkp
rikovm run build/add.rkp
rikovm step build/add.rkp            # execute one instruction, show state
rikovm inspect registers
rikovm inspect memory 0x0100 32
rikovm trace build/add.rkp           # full execution trace
```

- The debugger inspects state through read-only accessors; UI code
  never mutates CPU internals directly.
- Breakpoints come after M6 only if instruction addresses and
  source-line mappings are reliable — not a v1 promise.
- Output must show real state (PC, registers, flags, executed count),
  proving execution happened.

## 10. Faults (all milestones)

One exception hierarchy, defined once, used everywhere:

- `VMFault` — base. Every VM-level error is a `VMFault` with a message.
- `DecodeFault(VMFault)` — unknown opcode, bad register byte, truncated
  instruction.
- `MemoryFault(VMFault)` — out-of-range access, word straddling `0xFFFF`.
- `StackFault(VMFault)` — stack overflow / underflow (§3.4).
- `ArithmeticFault(VMFault)` — division by zero.
- `LoadError(VMFault)` — bad image (magic, truncation, oversize).

Faults are data: the run loop catches them, reports outcome `FAULT`
with PC + message, and the debugger can show the state at the fault.
A fault never crashes the host process and never leaves a half-written
instruction behind (§4, step 3).

## 11. Milestones and exit conditions

| Milestone | Deliverable / exit condition | Status |
|---|---|---|
| M0: Decisions | This spec, frozen and reviewed. | DONE (this doc) |
| M1: Machine state | Register file, flags, memory, faults — unit tests green. | Next |
| M2: CPU loop | Fetch-decode-execute for `LDI`, `ADD`, `HALT` + step limit + trace. Tests green. | — |
| M3: ISA expansion | All 26 instructions (§5) with flag + fault tests. | — |
| M4: Assembler | Source-to-bytes with labels, diagnostics, golden encoding tests. | — |
| M5: Loader | Validated `RKP1` images loaded at the entry point. | — |
| M6: Debugger + CLI | Run, step, inspect, trace a real program. | — |
| M7: Hardening | Edge cases, examples, docs, full suite green, README complete. | — |

Each milestone ends with: tests run and green, a short explanation of
what changed, and a list of remaining issues. No milestone generates
the whole repository in one pass.

## 12. Risks and mitigations (from the brief, kept)

- Assembler/decoder drift → one shared ISA table + golden tests (§5, §8).
- PC off-by-one errors → PC semantics frozen in §4 before any code.
- Overlarge first release → M2 ships 3 instructions; the full ISA is M3.
- Fake execution → state-transition tests + register/memory inspection.
- Host crashes on bad programs → explicit fault hierarchy (§10).
- Hidden coupling → documented module interfaces; core/CLI split (§2).

## 13. What is deliberately NOT in v1

- No I/O, no devices, no interrupts.
- No GUI (CLI proves the VM; a GUI is a later project, not a v1 need).
- No memory protection, no paging.
- No relative branches, no register-immediate arithmetic (v2 candidates).
- No breakpoints until source-line mapping is reliable (post-M6).
- No JIT, no optimisation. Clarity and correctness beat speed.

## 14. Decisions log

| # | Decision | Decided | By |
|---|---|---|---|
| D1 | Host language: Python 3, stdlib only | 14 Nov 2026 | Pawan |
| D2 | R0 is a plain general-purpose register | 14 Nov 2026 | Proposed (M0) — overturn anytime before M3 |
| D3 | Flags Z/C/N/V with §3.2 semantics (ARM-style carry) | 14 Nov 2026 | Proposed (M0) |
| D4 | Flat 64 KiB memory; stack region `0xF000`–`0xFFFF`, full-descending | 14 Nov 2026 | Proposed (M0) |
| D5 | PC = next instruction; advances at commit | 14 Nov 2026 | Proposed (M0) |
| D6 | Opcode-first variable-length encoding; §5 table frozen | 14 Nov 2026 | Proposed (M0) |
| D7 | Absolute branches; register-register arithmetic only (v1) | 14 Nov 2026 | Proposed (M0) |
| D8 | `RKP1` image format (§7) | 14 Nov 2026 | Proposed (M0) |
| D9 | No I/O in v1 | 14 Nov 2026 | Proposed (M0) |
| D10 | DIV-by-zero faults; arithmetic wraps with flag reporting | 14 Nov 2026 | Proposed (M0) |
| D11 | Flat `rikovm/` package + stdlib `unittest` | 14 Nov 2026 | Proposed (M0) |
