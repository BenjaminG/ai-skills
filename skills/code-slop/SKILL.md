---
name: code-slop
description: This skill should be used when the user wants to find AI-generated code slop — unnecessary comments, defensive checks, `any` casts, and style inconsistencies — in a branch's changes. Produces suggestions only; does not apply edits.
---

# Find AI Code Slop

Review the diff between the working branch and its baseline, and propose removals for AI-generated slop. Do not modify files.

## Resolve the baseline

Pick the first available reference, in order:

1. An explicit ref the user provides (e.g. "compare against develop", a commit SHA, or a tag).
2. The upstream tracking branch (`git rev-parse --abbrev-ref --symbolic-full-name @{u}`).
3. The repo's default branch (`git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main` then `master`).
4. The merge-base of `HEAD` and the resolved ref above (`git merge-base`).

State the resolved baseline in the report so the user can confirm.

## Comments: guilty until proven innocent

Treat **every comment added in the diff as slop by default.** A senior engineer writes almost none; the diff should read the same way. Do not look for reasons to flag a comment — flag it, then look for a reason to *keep* it. A comment survives only if it passes ALL of these:

1. **Durable** — still reads in six months with no diff in view. (Fails: anything narrating the change — what moved, was dropped, renamed-from, ticket tags like `BOF-xxx`, "seed 0 rather than null now", "TODO from review".)
2. **Non-redundant** — says something the code cannot. (Fails: restating the symbol name, the type, or the next line in prose — `// increment counter` above `counter++`, `// the user's email` above `userEmail`.)
3. **Load-bearing** — its absence would actually mislead a competent reader. It explains a *why* that isn't in the code: a non-obvious invariant, a workaround for an external bug (with a link), a deliberate deviation, a perf/security tradeoff. "Might be nice context" does not clear this bar.

If you find yourself writing a "keep" justification longer than the comment, it's slop — cut it. When genuinely unsure, flag it: the cost of a wrong flag is one ignored suggestion; the cost of a kept comment is permanent noise.

This is not softened by the surrounding file. A chatty file does not license one more chatty comment — judge each added comment on the three tests above, never on how its neighbours read.

## Other slop

- Defensive checks or try/catch blocks abnormal for that area of the codebase (especially on trusted / validated codepaths)
- Casts to `any` used to sidestep type issues
- Any other style inconsistent with the surrounding file

## Output

Do not edit files. Emit a structured list, one entry per proposed change:

- **File:line** — `path/to/file.ts:42`
- **Category** — comment | defensive-check | any-cast | style
- **Snippet** — the exact lines to remove or replace (≤5 lines)
- **Suggested replacement** — the exact replacement, or "delete"
- **Why** — one sentence

End with a 1–3 sentence summary of the proposed cleanup and the resolved baseline. Tell the user they can accept suggestions individually or ask for them all to be applied.
