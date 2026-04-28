---
name: second-pass
description: This skill should be used when the user wants to rebuild a just-completed implementation from scratch on a fresh branch, applying everything learned during the first pass. The first pass is exploration; the second pass is the real solution. Triggers on "second pass", "rewrite now that you know", "rebuild from scratch", "do it again better", or "knowing what you know now".
---

# Second Pass

Throw away the implementation you just finished, branch from the base, and rebuild it with everything you learned. The first pass was exploration. The second pass is the solution.

## When to use

After a non-trivial bug fix or feature where the problem shape only came into focus during implementation. Skip for trivial changes or for work you already understood before writing.

## Before starting

1. Require a clean working tree. Refuse to proceed if anything is uncommitted — the first pass must be a stable reference.
2. Record the current branch as `<first-pass>`.
3. Resolve the base branch, in order:
   - An explicit ref the user provides.
   - The upstream tracking branch (`git rev-parse --abbrev-ref --symbolic-full-name @{u}`) if it is not the first-pass branch itself.
   - The default branch (`git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main` then `master`).
4. List test files changed on the first pass:
   `git diff --name-only <base>...<first-pass> -- '**/*test*' '**/*spec*' '**/__tests__/**'`
   Adapt patterns to the project.
5. State the plan: first-pass branch, base, proposed new branch name (`<first-pass>-v2`), and the tests that will be carried over. Wait for confirmation.

## Run the pass

1. Create the rewrite branch from the base: `git switch -c <first-pass>-v2 <base>`. The first-pass branch is never modified — it is the reference and the fallback.
2. Carry the tests across unchanged: `git checkout <first-pass> -- <test-paths>`. Commit as `second-pass: carry over tests from first pass`.
3. Re-read the task description, then read the first-pass diff once (`git diff <base>..<first-pass>`) to recall the problem shape and the edge cases discovered.
4. Close the diff and implement from scratch. Do not copy blocks from the first pass — retype from understanding. The first pass informs the second; it does not seed it.
5. Run the preserved tests continuously. They are the behavioral contract.

## Optimize on three dimensions at once

The rewrite must beat the first pass on every dimension. If it fails any, reset the branch and try again, or decline and keep the first pass.

- **Elegance** — fewer moving parts, shorter, clearer intent. Drop scaffolding the exploration needed but the solution does not.
- **Robustness** — edge cases discovered mid-first-pass are first-class in the second. Targeted handling only; no defensive code "just in case".
- **Architectural fit** — match the conventions of the surrounding code. First passes often fight the house style; second passes respect it.

## Finishing

Report:
- First-pass branch, rewrite branch, and base.
- Line-count delta (`git diff --shortstat <base>..<first-pass>` vs `...<first-pass>-v2`).
- One paragraph on what changed structurally and why it is better on all three dimensions.
- Whether the preserved tests pass on the rewrite branch.
- Next step for the user: `git diff <first-pass>..<first-pass>-v2` to compare, then merge whichever branch they prefer.

Do not delete the first-pass branch. That is the user's call.
