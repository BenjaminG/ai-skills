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

## What counts as slop

- **Changelog comments** — comments that narrate the change (what moved, what was dropped, renamed-from, ticket tags like `BOF-xxx`, "seed 0 rather than null") instead of describing the code as it stands. Two checkable tests, either one fails it: (a) durability — would it still read in six months with no diff in view? and (b) redundancy — does the symbol name (prop, variable, function) already say it? Accuracy is not a defence: a precise comment that logs the change or restates the name is still slop.
- Defensive checks or try/catch blocks abnormal for that area of the codebase (especially on trusted / validated codepaths)
- Casts to `any` used to sidestep type issues
- Any other style inconsistent with the surrounding file

> Surrounding-file consistency is not a pass for comments: a verbose file does not license a verbose comment. Judge each comment on the two tests above, not on how chatty its neighbours are.

## Output

Do not edit files. Emit a structured list, one entry per proposed change:

- **File:line** — `path/to/file.ts:42`
- **Category** — comment | defensive-check | any-cast | style
- **Snippet** — the exact lines to remove or replace (≤5 lines)
- **Suggested replacement** — the exact replacement, or "delete"
- **Why** — one sentence

End with a 1–3 sentence summary of the proposed cleanup and the resolved baseline. Tell the user they can accept suggestions individually or ask for them all to be applied.
