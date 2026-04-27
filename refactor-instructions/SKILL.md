---
name: refactor-instructions
description: >-
  Audit and refactor CLAUDE.md, AGENTS.md, and .claude/rules/ files to follow
  progressive-disclosure principles. This skill should be used when the user
  wants to reorganize, clean up, or optimize their instruction files and rules
  by splitting monolithic files into a minimal root, domain-scoped rules with
  path globs, and linked reference docs. Triggers on requests like "refactor my
  CLAUDE.md", "clean up my rules", "audit my instructions", "organize my agent
  config", "optimize my rules files", or "migrate my CLAUDE.md to rules".
argument-hint: "[path/to/CLAUDE.md]"
---

# Refactor Instructions

Refactor monolithic instruction files into a minimal root, scoped `.claude/rules/` files, and reference docs.

## Why this matters

- The root file loads on **every** request. A bloated file steals tokens from the actual task and pushes the agent past its effective instruction budget (~150–200 rules before attention drops).
- `.claude/rules/` files with `paths:` globs load **only** when matching files are touched — scoped rules keep the base context lean without losing coverage.
- **Stale docs poison context.** File paths rot fastest — describe capabilities, not structure.
- Instruction files grow as **balls of mud** when rules are added reactively after every agent misstep. Small and focused beats comprehensive.

## Process

1. **Detect scope.** If a path argument was given (`$ARGUMENTS`), use that file as the target. Otherwise, use `AskUserQuestion` to ask which scope to refactor: project-level `.claude/CLAUDE.md`, user-level `~/.claude/CLAUDE.md`, or both. Then scan for `CLAUDE.md`, `AGENTS.md`, and `.claude/rules/*.md` at the chosen scope. In monorepos, also check `**/CLAUDE.md`. If both `CLAUDE.md` and `AGENTS.md` exist with different content, surface this — they may want a symlink. Determine docs location: use existing `docs/` if present at repo root, else default to `.claude/docs/`. When working at project level, also read `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` **read-only** for contradiction checking.

2. **Read every target file in full** — root files and every `.claude/rules/` file — before proposing anything. Do not rely on skimming.

3. **Find contradictions.** Check across all sources: root vs rules, rules vs rules, project-level vs user-level. List every conflicting pair. For each, use `AskUserQuestion` to ask which version to keep. Do not silently pick.

4. **Identify essentials for the root.** Keep only what applies to *every single task*:
   - One-sentence project description (anchors the agent's role)
   - Package manager, only if non-default (`pnpm`, `yarn`, `bun`, `uv`, etc.)
   - Non-standard build / typecheck / test commands
   - Truly universal rules (e.g., "never commit to `main`")
   - Domain concepts that differ from common usage (e.g., "organization" means X, not Y) — these are more stable than file paths and worth keeping

5. **Classify remaining content.** For each extracted section, decide the destination:
   - **`.claude/rules/<domain>.md`** — short, actionable rules. For each, recommend whether to add `paths:` frontmatter (lazy) or leave without (always loaded), with a one-line rationale.
   - **`docs/<TOPIC>.md`** — longer reference material, domain knowledge, examples, guides.
   - **Delete** — see step 7.

6. **Audit existing rules files.** For each `.claude/rules/` file already present, check:
   - Redundancy with the root file or other rules
   - Vague or unactionable content
   - Missing `paths:` globs that should be scoped
   - Overly broad globs that defeat lazy loading
   - Merge or split opportunities

7. **Flag for deletion.** Mark instructions (in root, rules, or docs) that are:
   - **Redundant** — the agent already knows this (e.g., "write readable code")
   - **Too vague** to be actionable
   - **Inferable** — agents discover project structure on their own; codebase overviews and architecture descriptions trigger extra exploration without improving accuracy
   - **Structural** — file paths, directory layouts, or architectural maps that rot and mislead
   - **Over-directive** — imperative instructions that force unnecessary work (e.g., "always run the full test suite", "review all related modules") without scoping when they apply

8. **Propose the structure before writing.** Output:
   - The new minimal root file (with links)
   - Each `.claude/rules/` file with its proposed frontmatter
   - Each docs file's content
   - A deletion list with a one-line rationale per item

   Use `AskUserQuestion` to present all proposed rules with their glob recommendations in a single table — confirm or override in one pass. Then use `AskUserQuestion` to confirm the full plan before writing anything to disk.

9. **Write the files** once approved. Rules files use this frontmatter format:
   ```yaml
   ---
   paths:
     - "src/api/**/*.ts"
     - "**/*.test.{ts,tsx}"
   ---
   ```
   Omit `paths:` for rules that should always load. Use a light touch in the root — conversational references, not all-caps commands.

## Where each rule belongs

| Rule scope | Goes in |
|---|---|
| Applies to every task in the repo | Root `CLAUDE.md` (keep minimal) |
| Short, actionable, applies to specific file types | `.claude/rules/<domain>.md` with `paths:` globs |
| Short, actionable, applies globally | `.claude/rules/<domain>.md` (no frontmatter) |
| Longer reference material or domain knowledge | `docs/<TOPIC>.md` or `.claude/docs/<TOPIC>.md` |
| Large body of reference material | Nested tree under `docs/` |
| Package-specific in a monorepo | `packages/<pkg>/CLAUDE.md` (merges with root) |
| Invokable procedure / playbook | Agent skill, not a doc |

## Avoid

- Documenting file-system paths in the root — they rot.
- Forceful tone (`"ALWAYS"`, `"NEVER"`, caps) for rules that don't truly need emphasis.
- Auto-regenerating the root via `init` scripts — generated files prioritize comprehensiveness over restraint.
- Ignoring the `AGENTS.md` ↔ `CLAUDE.md` symlink option when the repo is used by multiple agents.
- Writing files before the user has approved the proposed structure.
- Creating rules files that duplicate what is already in the root.
- Modifying user-level `~/.claude/rules/` when operating at project scope.
- Using overly broad globs (e.g., `**/*`) that defeat lazy loading.
- Splitting a single coherent rule across multiple files.
