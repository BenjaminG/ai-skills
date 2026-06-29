---
name: pr-comment
description: This skill should be used when reviewing someone else's pull request and you want to turn gate / gate-wf findings into posted GitHub comments — each comment drafted through humanizer and posted as a standalone inline comment at its file:line, after one confirmation. Triggers on "post these as review comments", "comment the gate findings on the PR", "draft and post my review", "leave review comments", after a gate / gate-wf run on a PR you're reviewing.
argument-hint: "[pr-number-or-url] [tiers — e.g. 'all' | 'B,M' | specific IDs]"
---

# PR Comment

Post `gate` / `gate-wf` findings on a PR you're reviewing as **standalone inline comments** — one independent comment per finding, placed at its `file:line`. Each is drafted through `humanizer` and posted only after one confirmation. There is no review wrapper and no summary comment. Out-of-diff findings (can't be inline) go to the PR conversation. This skill never approves or requests changes — that stays a manual call.

## Prerequisites

Findings come from a prior `gate` / `gate-wf` run, in priority order:

1. The findings already in this conversation (the gate verdict you just saw), or
2. The gate-wf state file for the current branch: `~/.claude/gate-wf-state/<repo-slug>/<branch>.json` → `.findings[]`.

Both produce the same shape: `id` (B1/M1/N1), `tier` (BLOCKER/MAJOR/NIT), `file`, `line`, `location` (`diff-line` | `adjacent`), `message`, `suggested_fix`.

Also resolve the PR and its head commit:

- `gh pr view <n> --json number,headRefOid,headRepositoryOwner,headRepository` — owner/repo + `headRefOid` (the `commit_id` every inline comment needs).

Drafting goes through the `humanizer` skill — that dependency is mandatory, not optional.

## The loop

`tier` orders the work (BLOCKER → MAJOR → NIT). For each selected finding:

1. **Draft the comment** — turn `message` + `suggested_fix` into a 1–3 sentence reviewer comment. Route it through the `humanizer` skill. **Never post a raw draft — always route it through humanizer first.** For NIT findings, prefix the body with `nit:`.
2. **Place it** — `location: diff-line` → standalone inline comment at `file:line`. `location: adjacent` (legacy code outside the diff) **cannot be inline** (GitHub only accepts comments on diff lines) → post as a top-level PR conversation comment citing `file:line`.
3. **Collect it** — add the drafted comment to the pending batch (inline or conversation) for one preview.

Show the **one batch preview** — every comment with its placement (`file:line` inline, or "conversation") — then post the whole batch only after a **single** confirmation.

**Done when** every selected finding has been posted as either an inline comment (diff-line) or a conversation comment (adjacent), *and* the summary reports the counts (inline / conversation / skipped-stale) with comment links.

## Submit (after confirmation)

Post each comment independently — no review object. After the single confirmation:

`diff-line` → one standalone inline comment per finding:

```bash
gh api repos/{owner}/{repo}/pulls/<n>/comments \
  -f commit_id=<headRefOid> -f path=src/db/users.ts -F line=42 \
  -f body="User input is concatenated into raw SQL — use a parameterized query."
```

`adjacent` → one top-level PR conversation comment per finding:

```bash
gh api repos/{owner}/{repo}/issues/<n>/comments \
  -f body="\`src/legacy.ts:88\` — …"
```

Notes:

- GitHub only accepts inline comments on lines present in the diff; `adjacent` findings go to the conversation, never to `pulls/<n>/comments`.
- This skill never submits APPROVE or REQUEST_CHANGES — comments only.
- A finding whose `file:line` is not on the diff (stale location) is skipped and reported, not posted.
