---
name: pr-feedback
description: Triage a pull request — sort every unresolved review item and failing check into P1 / P2 / Nit with a disposition, for `pr-respond` to act on. Use when triaging a PR, asking what is blocking a PR, or given a bare PR number or URL.
argument-hint: "[pr-number-or-url] [--auto <policy>]"
---

# PR Feedback Triage

Triage a pull request: sort every unresolved review item and failing check by urgency, then hand the user's picks to `pr-respond`. Read-only — never edit files, post replies, or re-run CI.

`--auto <policy>` lets a caller (a loop, another skill) supply the selection up front, so §4 reports without asking and §5 hands off directly. `--auto confirmed` selects every Nit plus every item whose verdict is ✅ confirmed. It leaves three kinds unselected and flagged for the user: ❓ unclear, ❌ refuted-but-blocking, and anything needing a merge decision. Without `--auto`, §4 asks as usual.

## 1. Fetch

The script ships with the plugin; resolve its path the same way `gate-wf` resolves its own
(plugin-root env → newest plugin cache → global-skills fallback), then run it:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-feedback/scripts/fetch-pr.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-feedback/scripts/fetch-pr.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-feedback/scripts/fetch-pr.py"; do
  [ -n "$c" ] && [ -f "$c" ] && FETCH="$c" && break
done
python3 "$FETCH" [pr-number-or-url]
```

One call, one JSON blob on stdout: the PR (`number`, `url`, `owner`, `repo`, `author`, `head`,
`base`, `state`), every unresolved inline review `thread` (paginated, with `id`, `comment_id`,
`path`, `line`, `awaiting_reviewer`, and each comment's `author` / `is_bot` / `body`), the
`reviews`, the conversation `comments`, and each entry in `failing_checks` with a 50-line
`log_tail`. Resolved and outdated threads are already dropped — `dropped_threads` counts them, so
the omission is visible rather than silent — and a bot's superseded review passes are collapsed to
its latest one.

Omit the argument to detect the PR from the current branch. A source that failed leaves a line in
`errors[]` instead of taking the run down: triage the rest and say in the report which source is
missing.

**Done when**: the resolved `#<n> — <url>` is stated for the user and the JSON is in hand.

## 2. Adjudicate each claim

A review comment is a **claim**, not a fact. Before an item gets a priority it gets a **verdict**, and the verdict is earned by reading the code — never by reading the comment more carefully. Default to **refuted** when the evidence does not arrive: a bot's fluent prose is not evidence, the file is.

For every item asserting a defect — bug, race, security hole, missing test, broken behavior, dead code, wrong type:

1. Read the cited `path:line`, plus enough of its callers to see the claimed path actually run.
2. Try to **refute** it. Name the input that triggers the defect, or the reason it cannot occur. "No caller passes null here" refutes; "looks fine" does not.
3. Record the verdict with its evidence — **confirmed** (`file:line` + the triggering case) | **refuted** (`file:line` + why it cannot happen) | **unclear** (the one thing that would settle it).

Items asserting taste — naming, formatting, phrasing, an optional refactor — assert no fact, so they carry no verdict. Send them straight to §3.

**Done when**: every defect-asserting item carries a verdict naming a `file:line` read in this run. A verdict resting only on the comment's own wording is not a verdict — go read the file.

## 3. Classify

The threads marked `awaiting_reviewer` are **awaiting reviewer**: the ball is with the reviewer, so they take no priority and no disposition, and they land at the end of the report. One exception pulls a thread back into the buckets: the author's reply only promised a change, and that change is not in the code — read the cited file to tell the two apart.

Everything else takes one priority:

- **P1 — blocking**: a failing required check, a **confirmed** correctness or security bug, an item carrying CHANGES_REQUESTED, new behavior shipped without a test. A defect claim reaches P1 on its verdict, not on its wording — an unadjudicated claim is not P1 material.
- **P2 — important, not blocking**: design concerns, maintainability, perf tradeoffs, ambiguous behavior, a reviewer question that needs an answer before merge.
- **Nit**: naming, formatting, phrasing, optional refactors, taste. Signalled by `nit:`, `optional:`, `consider`, `suggestion:`.

Doubt about **severity** rounds up — take the higher priority and note it was close. Doubt about **truth** rounds down: an `unclear` verdict caps at P2, and a **refuted** one at Nit unless a reviewer blocked the PR on it. A refuted claim still earns an answer, just not a code change.

And one **disposition** — `fix` (change the code) | `reply` (answer, no change) | `decline` (won't fix) | `defer` (track for later). `pr-respond` acts on the disposition, not on the priority, so mark an item `fix` only when code must actually change. A refuted claim is `reply` carrying the refutation, or `decline` — never `fix`.

**Done when**: every item in the working set carries a priority and a disposition consistent with its verdict, or is marked awaiting-reviewer. A bot's item is adjudicated like anyone else's — its author decides neither the verdict nor the priority.

## 4. Report

One table, rows ordered P1 → P2 → Nit:

| # | Where | Who | Claim | Verdict | Do |
|---|-------|-----|-------|---------|----|
| P1 | `auth.ts:42` | 🤖 bugbot | null deref on `user.id` | ✅ confirmed — `auth.ts:42`, callers pass undefined | fix |
| P1 | `ci / build` | ⚙️ check | `tsc` fails, 3 errors | — | fix |
| P2 | `sync.ts:110` | 👤 alice | why not batch these writes? | ❓ unclear — needs perf numbers | reply |
| Nit | `api.ts:8` | 🤖 bugbot | unused import | ❌ refuted — used at `api.ts:31` | decline |

- **#** — P1 | P2 | Nit. Append `†` when the priority was rounded up, and footnote the reason in one line under the table.
- **Where** — `path/to/file.ts:42`, or the check name.
- **Who** — 👤 `<login>` for a human, 🤖 `<login>` when `author.__typename` is `Bot`, the login ends in `[bot]`, or it is a known bot account (`naboo-ai-reviews`, `cursor` / Bugbot), ⚙️ `check` for a failing check.
- **Claim** — the item in one line, paraphrased. Quote only when the exact wording is the point.
- **Verdict** — ✅ confirmed | ❌ refuted | ❓ unclear, then the `file:line` that settled it. `—` for taste items and checks, which carry no verdict.
- **Do** — fix | reply | decline | defer.

Keep every cell to one line so rows stay scannable; the evidence that will not fit goes in a footnote under the table.

Then the awaiting-reviewer threads in their own table — Where | Who | Waiting on — one row each, nothing to act on.

Close with one line of files touched by the `fix` rows, then 1–3 sentences on overall health counting the refutations alongside the rest ("2 P1 CI failures + 1 confirmed P1 review comment, 2 bot claims refuted, 3 P2s, 5 nits, 2 awaiting reviewer"), then:

> Tell me which items to act on, or say "apply all P1" / "apply all".

Under `--auto`, skip that prompt. Mark each row selected or held, then list the held rows in one line ("2 held for you: #3 unclear, #7 needs a merge call").

**Done when**: every triaged item is a row — count the rows against step 3's working set — and the user has been asked to pick, or the `--auto` policy has selected for them.

## 5. Hand off

Invoke `pr-respond` with the user's picks. It reads this triage from the conversation and does not re-fetch, so carry each picked item's priority, disposition, verdict with its evidence (the reply to a refuted claim is written from it), thread `id`, first-comment `databaseId`, `owner`, `repo` and PR number into the handoff.

Under `--auto`, pass the policy through so `pr-respond` skips its confirmation too.

**Done when**: `pr-respond` is invoked, or the user picks nothing and the triage is left as the deliverable.
