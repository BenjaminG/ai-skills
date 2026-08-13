---
name: pr-feedback
description: Triage a pull request — sort every unresolved review item and failing check into P1 / P2 / Nit with a disposition, for `pr-respond` to act on. Use when triaging a PR, asking what is blocking a PR, or given a bare PR number or URL.
argument-hint: "[pr-number-or-url]"
---

# PR Feedback Triage

Triage a pull request: sort every unresolved review item and failing check by urgency, then hand the user's picks to `pr-respond`. Read-only — never edit files, post replies, or re-run CI.

## 1. Resolve the PR

Use the argument when it is a PR number or URL; otherwise detect from the current branch: `gh pr view --json number,url,headRefName,baseRefName,state,author`.

**Done when**: the resolved `#<n> — <url>` is stated for the user, and `owner` / `repo` / the PR author's login are captured for the calls below.

## 2. Fetch every source

Four sources, fetched in parallel. Cap any log output aggressively.

- **Inline review threads** — `gh pr view` has **no** `reviewThreads` JSON field (it errors with `Unknown JSON field`), so use GraphQL. This is where bot findings (Cursor Bugbot, `naboo-ai-reviews`) live. Paginate until `hasNextPage` is false: a PR can carry more than 100 threads, and an unfetched page is a silently dropped finding.

  ```bash
  gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
    repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
      reviewThreads(first:100,after:$cursor){ pageInfo{hasNextPage endCursor}
        nodes{ id isResolved isOutdated path line
          comments(first:20){ nodes{ databaseId author{login __typename} body } } } } } }
  }' -F owner=OWNER -F repo=REPO -F pr=<n> -F cursor=<endCursor>
  ```

  Omit `-F cursor=` on the first call; pass `pageInfo.endCursor` on each next one. Fetch the whole thread, not just its opening comment — the last comment is what tells you whether the ball is still in your court (§4). Keep `id` (the node id `pr-respond` needs to resolve the thread), the first comment's `databaseId` (its reply and reaction endpoints), `isResolved`, `isOutdated`, `path`, `line`, and every comment's author and body. `author.__typename` is the human-vs-bot signal.
- **Review summaries** — `gh pr view <n> --json reviews`: state (APPROVED / CHANGES_REQUESTED / COMMENTED), author, body.
- **Conversation comments** — `gh api repos/{owner}/{repo}/issues/<n>/comments`.
- **Status checks** — `gh pr checks <n>`. For each FAIL, a short log tail: `gh run view --log-failed --job <job-id> | tail -n 50`.

Drop a thread when `isResolved` or `isOutdated` is true, unless a later comment in it flags a regression.

**Done when**: all four sources are in, `hasNextPage` is false, and the working set holds every surviving thread, review, conversation comment, and failing check.

## 3. Adjudicate each claim

A review comment is a **claim**, not a fact. Before an item gets a priority it gets a **verdict**, and the verdict is earned by reading the code — never by reading the comment more carefully. Default to **refuted** when the evidence does not arrive: a bot's fluent prose is not evidence, the file is.

For every item asserting a defect — bug, race, security hole, missing test, broken behavior, dead code, wrong type:

1. Read the cited `path:line`, plus enough of its callers to see the claimed path actually run.
2. Try to **refute** it. Name the input that triggers the defect, or the reason it cannot occur. "No caller passes null here" refutes; "looks fine" does not.
3. Record the verdict with its evidence — **confirmed** (`file:line` + the triggering case) | **refuted** (`file:line` + why it cannot happen) | **unclear** (the one thing that would settle it).

Items asserting taste — naming, formatting, phrasing, an optional refactor — assert no fact, so they carry no verdict. Send them straight to §4.

**Done when**: every defect-asserting item carries a verdict naming a `file:line` read in this run. A verdict resting only on the comment's own wording is not a verdict — go read the file.

## 4. Classify

First, set aside the threads that are **awaiting reviewer** — those whose last comment is the PR author's. The ball is with the reviewer, so they take no priority and no disposition, and they land at the end of the report. One exception keeps a thread in the buckets: the author's reply only promised a change, and that change is not in the code — read the cited file to tell the two apart.

Everything else takes one priority:

- **P1 — blocking**: a failing required check, a **confirmed** correctness or security bug, an item carrying CHANGES_REQUESTED, new behavior shipped without a test. A defect claim reaches P1 on its verdict, not on its wording — an unadjudicated claim is not P1 material.
- **P2 — important, not blocking**: design concerns, maintainability, perf tradeoffs, ambiguous behavior, a reviewer question that needs an answer before merge.
- **Nit**: naming, formatting, phrasing, optional refactors, taste. Signalled by `nit:`, `optional:`, `consider`, `suggestion:`.

Doubt about **severity** rounds up — take the higher priority and note it was close. Doubt about **truth** rounds down: an `unclear` verdict caps at P2, and a **refuted** one at Nit unless a reviewer blocked the PR on it. A refuted claim still earns an answer, just not a code change.

And one **disposition** — `fix` (change the code) | `reply` (answer, no change) | `decline` (won't fix) | `defer` (track for later). `pr-respond` acts on the disposition, not on the priority, so mark an item `fix` only when code must actually change. A refuted claim is `reply` carrying the refutation, or `decline` — never `fix`.

**Done when**: every item in the working set carries a priority and a disposition consistent with its verdict, or is marked awaiting-reviewer. A bot's item is adjudicated like anyone else's — its author decides neither the verdict nor the priority.

## 5. Report

Group by priority, P1 → P2 → Nit. Per item:

- **Where** — `path/to/file.ts:42`, or the check name
- **Author** — 👤 `<login>`, or 🤖 when `author.__typename` is `Bot`, the login ends in `[bot]`, or it is a known bot account (`naboo-ai-reviews`, `cursor` / Bugbot)
- **Source** — review-comment | review-summary | conversation | check
- **Quote** — ≤2 lines from the comment or the check failure
- **Verdict** — defect claims only: confirmed | refuted | unclear, plus the `file:line` that settled it
- **Why** — one sentence on the priority
- **Disposition** — fix | reply | decline | defer

Then the ordered plan: P1 first, grouped by file so edits batch cleanly, then P2, then Nits. Then the awaiting-reviewer threads, one line each (author, location, what they are waiting on) — visible, but nothing to act on. Close with 1–3 sentences on overall health, counting the refutations alongside the rest ("2 P1 CI failures + 1 confirmed P1 review comment, 2 bot claims refuted, 3 P2s, 5 nits, 2 awaiting reviewer"), then:

> Tell me which items to act on, or say "apply all P1" / "apply all".

**Done when**: every triaged item appears in the report — count them against step 4's working set — and the user has been asked to pick.

## 6. Hand off

Invoke `pr-respond` with the user's picks. It reads this triage from the conversation and does not re-fetch, so carry each picked item's priority, disposition, verdict with its evidence (the reply to a refuted claim is written from it), thread `id`, first-comment `databaseId`, `owner`, `repo` and PR number into the handoff.

**Done when**: `pr-respond` is invoked, or the user picks nothing and the triage is left as the deliverable.
