---
name: rca
description: Investigate a High/Urgent bug on Linear and post a structured root-cause comment in the team's format (Root cause → Timeline of PRs → Category → what the fix does → follow-up). Drafts in chat first; posts to Linear only on explicit approval. This skill should be used when asked to document why a bug happened, write a root-cause comment, or "post the root cause" for a Linear issue ID or URL.
argument-hint: "[Linear issue ID or URL]"
disable-model-invocation: true
allowed-tools: Bash(linear:*), Bash(devsql:*), Bash(git:*), Bash(gh:*), Read, Grep, Glob, AskUserQuestion
---

# Root cause comment

Document **why** a High/Urgent bug happened and post it as a Linear comment, per the team rule that High/Urgent bugs get a written root cause. Draft-then-confirm: post only when explicitly approved.

## 1 — Gather context (sequential, before anything else)

Run `/investigate $ARGUMENTS` to pull the ticket, synced Slack thread, prior work, and the relevant code. Do not start code search or `devsql` until the ticket + thread are summarized.

If `/investigate` isn't run, at minimum: `linear issue view <id>` for the ticket and its synced Slack thread, then trace the offending behaviour to the write paths / commits that introduced and re-introduced it (`git log -S`, `gh pr view`).

## 2 — Find the real cause, not the symptom

Identify the **earliest** decision that made the bug possible and every later PR that re-introduced or only partially fixed it. The goal is the *category* of mistake (e.g. "deprecated pattern re-copied into new write paths", "no backfill when a dual-write was introduced"), not a single faulty line. Confirm against code/data — never assert a cause you haven't verified.

## 3 — Draft in the team format

Render in chat for review. Structure (keep what applies, drop what doesn't):

```markdown
**Root cause: <one-line category, stated as the real cause not the symptom>.**

<2-4 sentences: the invariant that was violated, and the narrow condition under
which it surfaces — why it stayed invisible most of the time.>

**Timeline:**
* **<PR/ticket ref>** (date): what it changed, and how it set up or re-introduced the bug.
* ...

**Category:** <missing source of truth / regression by copy of deprecated pattern /
forward-only fix without backfill / ...>. Stayed invisible because <condition>.

**This PR ([#NNNN](url)):** <forward fix + backfill scope, with row counts if known>.

Follow-up: <the change that stops the recurrence — usually a single source of truth>.
```

Rules:
- Functional and didactic, jargon explained — written for a teammate, not an implementation dump. See `[[feedback_pr_didactic_descriptions]]`.
- Link every PR and ticket as markdown links.
- Cap claims at what you verified; say "unconfirmed" rather than guessing.

## 4 — Post on approval only

Write the body to a temp file and post with the file flag (preserves markdown):

```bash
linear issue comment add <issue-id> --body-file /tmp/root-cause.md
```

Reply in an existing thread with `-p <parentCommentId>` (get IDs from `linear issue comment list <id>`). Never post without explicit confirmation.

## Reference examples

BOF-390 (currency/VAT from company instead of proposal) and BOF-423 (proposal-level cohort asymmetry) are the canonical examples of this format — pull them with `linear issue comment list BOF-390` if you need a model.
