---
name: pr-comment
description: This skill should be used when reviewing someone else's pull request and you want drafted review comments posted to GitHub — either gate / gate-wf findings (tier-marked) or pr-challenge's reviewer questions (unmarked) — each drafted through humanizer and posted as a standalone inline comment at its file:line, after one confirmation. Triggers on "post these as review comments", "comment the gate findings on the PR", "draft and post my review", "leave review comments", after a gate / gate-wf run or a pr-challenge pass on a PR you're reviewing.
argument-hint: "[pr-number-or-url] [tiers — e.g. 'all' | 'B,M' | specific IDs]"
---

# PR Comment

Post drafted review comments on a PR you're reviewing as **standalone inline comments** — one independent comment per item, placed at its `file:line`. Each is drafted through `humanizer` and posted only after one confirmation. There is no review wrapper and no summary comment. Out-of-diff items (can't be inline) go to the PR conversation. This skill never approves or requests changes — that stays a manual call.

## Two sources, one poster

The mechanics below — placement, batch preview, single confirmation, `gh api` calls, stale-line skip — are identical for both. What differs is only whether a comment carries a tier marker.

| Mode | Input | Marker |
|---|---|---|
| **findings** (default) | `gate` / `gate-wf` findings — defect claims with a tier | mandatory (`**blocker:** ` / `**major:** ` / `nit: `) |
| **challenge** | `pr-challenge` comments — reviewer questions with a `kind` | none, or a conventional-comment label the caller already applied |

Pick by what's in hand: a `pr-challenge` set in the conversation → challenge mode. Otherwise findings mode. Never mix the two in one batch — a question sitting among tier-marked defects reads as a defect nobody scored.

## Prerequisites — findings mode

Findings come from a prior `gate` / `gate-wf` run, in priority order:

1. The findings already in this conversation (the gate verdict you just saw), or
2. The state file for the current branch — whichever skill ran: `~/.claude/gate-state/<repo-slug>/<branch>.json` (`gate`) or `~/.claude/gate-wf-state/<repo-slug>/<branch>.json` (`gate-wf`) → `.findings[]`.

Both produce the same shape: `id` (B1/M1/N1), `tier` (BLOCKER/MAJOR/NIT), `file`, `line`, `location` (`diff-line` | `adjacent`), `message`, `suggested_fix`.

## Prerequisites — challenge mode

Comments come from `pr-challenge` in this conversation, already cut to size, already through `humanizer`, and already in the PR's language. Each carries `kind` (`approach` / `intent` / `exists` / `simpler` / `naming` / `scope` / `convention` / `nit`), `file`, `line`, `location`, the drafted `body`, and the PR's `owner` / `repo` / number / `head_sha`.

Those bodies are **finished**. Do not re-draft them, do not expand them, and above all do not add a tier: `pr-challenge` spent a whole step cutting and phrasing them, and a second pass over a one-sentence question only puts the AI tells back. Route a body through `humanizer` here only if it arrived unhumanized (the caller says so, or it reads like a finding).

## Resolve the PR

Both modes need the PR and its head commit:

- `gh pr view <n> --json number,headRefOid,headRepositoryOwner,headRepository` — owner/repo + `headRefOid` (the `commit_id` every inline comment needs). In challenge mode the fetcher already returned `head_sha`; use it and skip the call.

Drafting in findings mode goes through the `humanizer` skill — that dependency is mandatory, not optional.

## The loop

Work order: findings mode orders by `tier` (BLOCKER → MAJOR → NIT); challenge mode keeps `pr-challenge`'s own ranking, which put what the reviewer most wants answered first. For each selected item:

1. **Draft the comment** — *findings mode only*: turn `message` + `suggested_fix` into a 1–3 sentence reviewer comment and route it through the `humanizer` skill. **Never post a raw draft — always route it through humanizer first.** In challenge mode the body is already drafted; take it as-is.
2. **Label it** — *findings mode only*: prepend the tier marker to the humanized body, in this order (humanizer runs on the prose only, never on the marker, so it can't rewrite or drop it): `**blocker:** ` / `**major:** ` / `nit: `. Verify the final body still starts with the marker before batching; re-add it if humanizer's output lost it. In challenge mode there is no marker to add — any label the caller wanted is already on the body.
3. **Place it** — `location: diff-line` → standalone inline comment at `file:line`. `location: adjacent` (legacy code outside the diff) **cannot be inline** (GitHub only accepts comments on diff lines) → post as a top-level PR conversation comment citing `file:line`.
4. **Collect it** — add the drafted comment to the pending batch (inline or conversation) for one preview.

Show the **one batch preview** — every comment with its marker (findings) or `kind` (challenge) and its placement (`file:line` inline, or "conversation") — then post the whole batch only after a **single** confirmation. In findings mode, a comment in the preview with no tier marker is a bug: fix it before posting. In challenge mode, a comment *with* a tier marker is the bug.

**Done when** every selected item has been posted as either an inline comment (diff-line) or a conversation comment (adjacent), *and* the summary reports the counts (inline / conversation / skipped-stale) with comment links.

## Submit (after confirmation)

Post each comment independently — no review object. After the single confirmation:

`diff-line` → one standalone inline comment per item:

```bash
gh api repos/{owner}/{repo}/pulls/<n>/comments \
  -f commit_id=<headRefOid> -f path=src/db/users.ts -F line=42 \
  -f body="**blocker:** User input is concatenated into raw SQL — use a parameterized query."
```

`adjacent` → one top-level PR conversation comment per item:

```bash
gh api repos/{owner}/{repo}/issues/<n>/comments \
  -f body="\`src/legacy.ts:88\` — …"
```

Notes:

- GitHub only accepts inline comments on lines present in the diff; `adjacent` items go to the conversation, never to `pulls/<n>/comments`.
- This skill never submits APPROVE or REQUEST_CHANGES — comments only.
- An item whose `file:line` is not on the diff (stale location) is skipped and reported, not posted.
