---
name: fixup
description: Fold an uncommitted fix into the commit that introduced the code, so the branch reads as if the bug never existed — find the introducing commit, `--fixup` + `--autosquash` (or `--amend` at the tip), then force-push with lease. Use for every fix on an unmerged branch — review feedback, CI failure, bug — and whenever asked to amend, fold, squash into, or fixup a commit.
argument-hint: "[--no-push]"
---

# Fixup

A **fold** puts the fix in the commit that introduced the code. Every fix on an unmerged branch — bot review feedback, CI failure, bug — gets folded, never appended.

## 1. Find the introducing commit

Per changed hunk, from the *removed* side of the diff (the code being fixed, not the fix):

```bash
git log -S'<snippet>' --oneline <base>..HEAD    # or: git blame -L <line>,<line> -- <file>
```

`<base>` is the PR's merge-base, not a stale local branch: `git merge-base HEAD origin/<baseRef>`.

**Report the mapping before rewriting anything** — one row per file/hunk: `file:line → <sha> <subject>`. Rewriting history on a guess is how a fix lands in the wrong commit.

- Several hunks, several commits → one `--fixup` each. Never one blanket fixup.
- The snippet resolves to a commit **already merged** on the base branch → say so, make a normal commit, and stop. Do not rewrite merged history.
- Nothing resolves (genuinely new code) → normal commit.

## 2. Fold

```bash
git add <files>
git commit --amend --no-edit            # target is HEAD
git commit --fixup=<sha>                # target is anywhere else
git rebase -i --autosquash <base>       # then, once per batch
```

Note `git rev-parse HEAD` before the rebase — that SHA is the undo (`git reset --hard <sha>`).

Conflicts during autosquash are **semantic**: resolve them, or abort and report. Never `--skip`.

## 3. Verify, then push

```bash
git diff <pre-rebase-sha> HEAD --stat   # expect empty: same tree, different history
git push --force-with-lease
```

A non-empty diff means the rebase dropped or duplicated something — stop and report, don't push.

`--no-push` folds and verifies but leaves the push to the caller.

## Stacked branches

On a stack, folding rewrites the parent's SHAs and orphans its children. Hand the restack to the `gh-stack` skill rather than rebasing children by hand.
