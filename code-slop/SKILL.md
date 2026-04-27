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

- Comments a human wouldn't write or that are inconsistent with the rest of the file
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
