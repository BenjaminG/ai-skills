---
name: fixup
description: Fold an uncommitted fix into the commit that introduced the code, so the branch reads as if the bug never existed. Finds the introducing commit, runs `--fixup` plus `--autosquash` (or `--amend` at the tip), then force-pushes with lease. Use for every fix on an unmerged branch, whether it came from review feedback, a CI failure, or a bug, and whenever asked to amend, fold, squash into, or fixup a commit.
argument-hint: "[--no-push]"
---

# Fixup

A fold puts the fix in the commit that introduced the code. Every fix on an unmerged branch gets folded, never appended. That covers bot review feedback, CI failures, and bugs found along the way.

## 1. Find the introducing commit

Search from the removed side of the diff, the code being fixed rather than the fix itself. One search per hunk.

```bash
git log -S'<snippet>' --oneline <base>..HEAD    # or: git blame -L <line>,<line> -- <file>
```

`<base>` is the PR's merge-base, never a stale local branch. Get it with `git merge-base HEAD origin/<baseRef>`.

Report the mapping before rewriting anything, one row per hunk: `file:line → <sha> <subject>`. Rewriting history on a guess is how a fix lands in the wrong commit.

Several hunks pointing at several commits get one `--fixup` each. Never one blanket fixup.

If the snippet resolves to a commit already merged on the base branch, say so, make a normal commit, and stop. Merged history stays as it is.

If nothing resolves, the code is new. Normal commit.

## 2. Fold

```bash
git add <files>
git commit --amend --no-edit            # target is HEAD
git commit --fixup=<sha>                # target is anywhere else
git rebase -i --autosquash <base>       # then, once per batch
```

Note `git rev-parse HEAD` before the rebase. That SHA is the undo, via `git reset --hard <sha>`.

Conflicts during autosquash are semantic. Resolve them, or abort and report. Never `--skip`.

## 3. Verify, then push

```bash
git diff <pre-rebase-sha> HEAD --stat   # expect empty: same tree, different history
git push --force-with-lease
```

A non-empty diff means the rebase dropped or duplicated something. Stop and report, don't push.

`--no-push` folds and verifies, then leaves the push to the caller.

## Stacked branches

On a stack, folding rewrites the parent's SHAs and orphans its children. Hand the restack to the `gh-stack` skill instead of rebasing children by hand.
