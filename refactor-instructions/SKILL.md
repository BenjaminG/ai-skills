---
name: refactor-instructions
description: Refactor CLAUDE.md or AGENTS.md files to follow progressive disclosure principles. This skill should be used when the user wants to reorganize, clean up, or optimize their instruction files (CLAUDE.md, AGENTS.md) by splitting monolithic files into a minimal root file with linked topic files. Triggers on requests like "refactor my CLAUDE.md", "clean up my AGENTS.md", "organize my instructions", "split my config", or "optimize my agent instructions".
---

# Refactor Instructions

Refactor a monolithic `CLAUDE.md` or `AGENTS.md` into a small, focused root file that points to topic-specific files via progressive disclosure.

## Why this matters

- The root file loads on **every** agent request. A bloated file steals tokens from the actual task and pushes the agent past its effective instruction budget (~150–200 rules before attention drops).
- **Stale docs poison context.** File paths rot fastest — if the root says `"auth lives in src/auth/handlers.ts"` and that file moved, the agent confidently looks in the wrong place. Describe capabilities, not structure.
- Instruction files grow as **balls of mud** when rules are added reactively after every agent misstep. Small and focused beats comprehensive. Reference nested docs instead of inlining.

## Process

1. **Detect target files.** Run `ls CLAUDE.md AGENTS.md` at the repo root. Handle whichever exist. In monorepos, also check `**/AGENTS.md` and `**/CLAUDE.md` — nested files merge with the root at their scope. If both `CLAUDE.md` and `AGENTS.md` exist with different content, surface this to the user: they may want a symlink (`ln -s AGENTS.md CLAUDE.md`) so every tool sees the same file.

2. **Read every target file in full** before proposing anything. Do not rely on skimming.

3. **Find contradictions.** List every pair of instructions that conflict. For each, use `AskUserQuestion` to ask which version to keep. Do not silently pick.

4. **Identify essentials for the root.** Keep only what applies to *every single task*:
   - One-sentence project description (anchors the agent's role)
   - Package manager, only if non-default (`pnpm`, `yarn`, `bun`, `uv`, etc.)
   - Non-standard build / typecheck / test commands
   - Truly universal rules (e.g., "never commit to `main`")

5. **Group everything else by domain.** Typical buckets: TypeScript conventions, testing patterns, API design, git workflow, styling, state management, deployment. One file per domain under `docs/`.

6. **Flag for deletion.** Mark instructions that are:
   - **Redundant** — the agent already knows this (e.g., "write readable code")
   - **Too vague** to be actionable
   - **Overly obvious** (e.g., "use descriptive variable names")
   - **Inferable** from the codebase or standard docs (e.g., "run `npm install` to install dependencies", "this project uses TypeScript", "this project uses Playwright for e2e testing")
   - **Structural** — documents file paths or directory layouts that will rot (convert to capability descriptions or delete entirely)

7. **Propose the structure before writing.** Output:
   - The new minimal root file (with links to topic files)
   - Each topic file's content
   - The full `docs/` folder tree
   - A deletion list with a one-line rationale per item
   
   Use `AskUserQuestion` to confirm the plan before writing anything to disk.

8. **Write the files** once approved. Use a light touch in the root — conversational references, not all-caps commands:
   > For TypeScript conventions, see [docs/TYPESCRIPT.md](docs/TYPESCRIPT.md).
   
   Topic files can themselves reference deeper documents — progressive disclosure nests.

## Where each rule belongs

| Rule scope | Goes in |
|---|---|
| Relevant to every task in the repo | Root file |
| Relevant to one domain (TS, testing, API…) | `docs/<TOPIC>.md` |
| Large body of reference material | Nested tree under `docs/` |
| Package-specific in a monorepo | `packages/<pkg>/AGENTS.md` (merges with root) |
| Invokable procedure / playbook | Agent skill, not a doc |

## Avoid

- Documenting file-system paths in the root — they rot.
- Forceful tone (`"ALWAYS"`, `"NEVER"`, caps) for rules that don't truly need emphasis. Save shouting for the few rules that must not be broken.
- Auto-regenerating the root via `init` scripts. Generated files prioritize comprehensiveness over restraint.
- Ignoring the `AGENTS.md` ↔ `CLAUDE.md` symlink option when the repo is used by multiple agents.
- Writing files before the user has approved the proposed structure.
