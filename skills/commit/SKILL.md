---
name: commit
description: Stage and commit pending changes with an automatically generated concise message. This skill should be used when the user asks to "commit", "stage and commit", "make a commit", or "save changes to git". Does not push or create PRs.
---

# Commit

Stage pending changes and create a single commit with a concise, accurate message.

## Process

1. Gather context. Run these in parallel:
   - `git status` — list changed and untracked files
   - `git diff HEAD` — see actual content changes
   - `git branch --show-current` — confirm branch
   - `git log --oneline -5` — learn the repo's commit message style

2. Run safety checks before staging.
   - If the current branch is `main`, `master`, or `develop`, stop and ask the user whether to proceed. Feature branches are the default.
   - Scan the file list for secrets or stray binaries: `.env`, `.env.*`, `credentials*`, `*.key`, `*.pem`, `id_rsa*`, or any file larger than 5 MB. If any match, stop and confirm with the user before staging.

3. Stage files explicitly by name. Never use `git add .` or `git add -A`.
   - Example: `git add src/foo.ts src/bar.ts tests/foo.test.ts`
   - Include both modified and new files that belong in the commit.
   - Leave anything that was flagged in step 2 unstaged unless the user approves.

4. Draft the commit message.
   - Match the style observed in `git log --oneline -5` (conventional commits, prefixes, casing).
   - Subject ≤70 chars, imperative mood ("add X", "fix Y", not "added" or "fixes").
   - Focus on the *why* when it isn't obvious from the diff.

5. Create the commit with a HEREDOC so formatting is preserved:

   ```bash
   git commit -m "$(cat <<'EOF'
   your message here
   EOF
   )"
   ```

6. Verify the commit. Run `git status` and confirm the working tree is clean (or only contains files intentionally left unstaged in step 2).

## Do NOT

- Push to remote or create a PR.
- Amend the previous commit. If a hook fails, fix the issue and create a NEW commit.
- Pass `--no-verify`, `--no-gpg-sign`, or otherwise skip hooks.
- Stage `.env`, credentials, keys, or unreviewed binaries.
- Use `git add .` or `git add -A`.
