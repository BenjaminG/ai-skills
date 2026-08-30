---
name: pr-feedback
description: Triage a pull request — sort every unresolved review item and failing check into P1 / P2 / Nit with a disposition, for `pr-respond` to act on. Use when triaging a PR, asking what is blocking a PR, or given a bare PR number or URL.
argument-hint: "[pr-number-or-url] [--auto <policy>]"
---

# PR Feedback Triage

Triage a pull request: sort every unresolved review item and failing check by urgency, then hand the user's picks to `pr-respond`. Read-only — never edit files, post replies, or re-run CI.

`--auto <policy>` lets a caller (a loop, another skill) supply the selection up front, so §4 reports without asking and §5 hands off directly. `--auto confirmed` selects every failing check, every Nit, and every item whose verdict is ✅ confirmed. A check carries no verdict and is not a Nit — naming it here is what keeps it from falling out of the selection and being held, which is the one thing a red check must never be. It leaves three kinds unselected and flagged for the user: ❓ unclear, ❌ refuted-but-blocking, and anything needing a merge decision. Without `--auto`, §4 asks as usual.

Two limits hold under every `--auto` policy, because the caller is unattended:

- **Only bots and checks are selectable.** An item authored by a human is reported and held, never
  acted on — no reply, no reaction, no resolve, no code change. A human wrote to the author, and an
  automated pass answering in their place is the one thing no policy authorises.
- **A confirmed item that §2 turned into a `reply` for want of a decision** is posted as a reply,
  its thread is **left open**, and it is counted as held and named in §4's held line. Resolving it
  would file the one thing the author still has to act on under the threads GitHub hides: the report
  carries a gist, the open thread carries the question, and the author needs both. Our reply being
  the last word is also what marks the thread `held` on the next fetch, so it is reported and never
  re-triaged, re-answered or spawned on again.

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
`base`, `state`, `draft`, `mergeable`), every **live** inline review `thread` (paginated, with `id`, `comment_id`,
`path`, `line`, `awaiting_reviewer`, `held`, and each comment's `author` / `is_bot` / `body`),
`settled_threads` — the resolved and outdated ones, same shape in 300-char excerpts — the
`reviews`, the conversation `comments`, and each entry in `failing_checks` with a 50-line
`log_tail`. A bot's superseded review passes are collapsed to its latest one.

**Then ask whether the PR sits in a stack** — one call, and it changes what the code in the diff
means:

```bash
gh pr list --state open --json number,headRefName,baseRefName
```

The **parent** is the open PR whose `headRefName` equals this PR's `base`; the **children** are
those whose `baseRefName` equals this PR's `head`. Note the numbers and stop there — no diff, no
threads, nothing else is fetched until a claim actually needs them (§2).

Omit the argument to detect the PR from the current branch. A source that failed leaves a line in
`errors[]` instead of taking the run down: triage the rest and say in the report which source is
missing.

The working set is `threads` + `reviews` + `comments` + `failing_checks` + the **branch state**
(`mergeable`, `draft`). A branch that cannot merge blocks the PR as hard as a red check and shows up
in no thread and no check run, so `mergeable: "CONFLICTING"` is an item like any other — see §3. `settled_threads` is
**not** part of it: someone closed those, so they earn no verdict, no priority and no row. They
ship for one job — a PR-level summary carries no `path:line` of its own and recaps findings that
each got a thread, so the settled excerpts are the only evidence that separates a live claim from
one already answered. Read them for that (§3), then leave them closed: never re-adjudicate one
against current code, and never re-fetch their full bodies.

**Done when**: the resolved `#<n> — <url>` is stated for the user and the JSON is in hand.

## 2. Adjudicate each claim

A review comment is a **claim**, not a fact. Before an item gets a priority it gets a **verdict**, and the verdict is earned by reading the code — never by reading the comment more carefully. Default to **refuted** when the evidence does not arrive: a bot's fluent prose is not evidence, the file is.

For every item asserting a defect — bug, race, security hole, missing test, broken behavior, dead code, wrong type:

1. Read the cited `path:line`, plus enough of its callers to see the claimed path actually run.
2. Try to **refute** it. Name the input that triggers the defect, or the reason it cannot occur. "No caller passes null here" refutes; "looks fine" does not.
3. Record the verdict with its evidence — **confirmed** (`file:line` + the triggering case) | **refuted** (`file:line` + why it cannot happen) | **unclear** (the one thing that would settle it).

Items asserting taste — naming, formatting, phrasing, an optional refactor — assert no fact, so they carry no verdict. Send them straight to §3.

### Was it written that way on purpose?

Reading the code proves a defect **exists**. It cannot prove the defect is an accident — that lives
in the history, not in the file. So for an item that came out **confirmed** and would become a
`fix`, and only for those, spend one more look: `git log`/`git blame` on the cited lines, the ADRs,
`CLAUDE.md`, and the project memory under `~/.claude/projects/<slug>/memory/`.

Find a deliberate decision that the claim contradicts, or an ambiguity you cannot settle from those
sources, and the verdict stays confirmed while the disposition becomes `reply` — the remedy is a
choice, and choices belong to the author. Say which source settled it. Find nothing, or find a
source that backs the claim, and `fix` stands.

### Does the rest of the stack answer it?

History is not the only place a decision hides. A stacked PR ships foundations **on purpose**: the
caller, the second implementation, the test that exercises the new path all land one PR up. So a
claim from the family *unused / never called / dead code / only one implementation / premature
abstraction / parameter never read* is not adjudicated against this diff alone — read the child's
diff (`gh pr diff <child>`) before ruling.

Find the consumer there and the claim is **refuted**, evidence `#<child>` plus the consuming
`file:line`, disposition `reply`. Find nothing in any child and it stands: a stack is a plan, not an
alibi, and code that no PR in the stack ever uses is dead today.

The other direction matters as much. A **confirmed** defect on lines this PR did not introduce —
they belong to the parent's commits, outside `base..HEAD` — is not this PR's to fix: folding it here
rewrites the parent's history under it, and `fixup` refuses that by design. Verdict stays confirmed,
disposition becomes `reply` naming the parent PR as where the fix belongs.

### Registry of past refutations

A bot re-raises what another bot already lost. `gate-wf` keeps the store for this — see its
`references/dismissals.md` for the file path and the content-anchor helper; the same registry is
shared, so a claim refuted here stops being re-flagged there.

Before adjudicating, compute each item's anchor and drop the ones already in the registry, noting
them in one line ("2 claims already refuted on this branch"). After adjudicating, upsert every
**refuted** item with `rule_id: "bot:<login>"`, `source: "pr-thread"`, and `confidence: "resolved"`
once its thread is closed (`"rebutted"` while it is still open). An item with no `file:line` — a
PR-level recap comment — has no anchor and stays out.

**Done when**: every defect-asserting item carries a verdict naming a `file:line` read in this run, every confirmed `fix` has had its history checked, and the refutations are in the registry. A verdict resting only on the comment's own wording is not a verdict — go read the file.

## 3. Classify

The threads marked `awaiting_reviewer` are **awaiting reviewer**: the ball is with the reviewer, so they take no priority and no disposition, and they land at the end of the report. Two exceptions pull a thread back out. The author's reply only promised a change, and that change is not in the code — read the cited file to tell the two apart. Or the reviewer is a **bot**: `awaiting_reviewer` only means the last comment is the author's, and no bot ever takes that ball back.

A bot thread we answered last carries `held: true`, and that is a **deliberately** open thread — an earlier pass adjudicated the claim and left the decision to the author. It is not an item: no priority, no disposition, no reply, and above all no resolve. Name it on the held line of §4 and move on. `pr-respond` resolves in the same batch it replies, so a bot thread still open with our answer on top is one that was held on purpose; only threads predating that rule are stragglers, and closing those is the author's call, not an automated pass's.

Everything else takes one priority:

- **P1 — blocking**: `mergeable: "CONFLICTING"` (the branch conflicts with `base`), a failing required check, a **confirmed** correctness or security bug, an item carrying CHANGES_REQUESTED, new behavior shipped without a test. A defect claim reaches P1 on its verdict, not on its wording — an unadjudicated claim is not P1 material.
- **P2 — important, not blocking**: design concerns, maintainability, perf tradeoffs, ambiguous behavior, a reviewer question that needs an answer before merge.
- **Nit**: naming, formatting, phrasing, optional refactors, taste. Signalled by `nit:`, `optional:`, `consider`, `suggestion:`.

Doubt about **severity** rounds up — take the higher priority and note it was close. Doubt about **truth** rounds down: an `unclear` verdict caps at P2, and a **refuted** one at Nit unless a reviewer blocked the PR on it. A refuted claim still earns an answer, just not a code change.

An item with no Resolve button — a PR-level conversation comment (a bot's `AI Review` summary, a CI recap), or the body of an APPROVED / CHANGES_REQUESTED review submission — gets one check before anything else: **match each of its claims against `settled_threads`.** Such a summary recaps findings that each got their own thread, and it is frozen at the SHA that produced it — answering the findings does not rewrite it. A claim that already sits in a settled thread is answered; it produces no row. Say it in one line under the table ("the AI Review body recaps 3 threads, all resolved") and move on. Only a claim with no settled counterpart survives as an item.

What survives is triaged like any other, `reply` included: an answer is often exactly what it deserves. What changes is who posts it. There is no thread to answer there, so a reply becomes a new top-level comment everyone gets mailed about, and that is the author's call. Mark it `reply (hand back)` — the answer is **written into §4's report**, ready to paste, and nothing posts it: not `pr-respond`, not you. `gh pr comment` and `gh pr review` are outside this skill and its handoff, whatever the disposition says.

And one **disposition** — `fix` (change the code) | `reply` (answer, no change) | `decline` (won't fix) | `defer` (track for later). `pr-respond` acts on the disposition, not on the priority, so mark an item `fix` only when code must actually change. A refuted claim is `reply` carrying the refutation, or `decline` — never `fix`.

A conflicting branch is the one `fix` that never travels: resolving it is a rebase against `base`,
which `pr-respond` does not do. Mark it `fix (hand back)`, name the base it conflicts with, and
leave it to the user — under `--auto` it is held, like anything needing a merge decision.

When that `base` is **another open PR**, say so in the row: a stacked branch goes conflicting on its
own the moment its parent is rewritten under it, so the remedy is a restack (`gh-stack`), not a
judgment call on whose side of a conflict wins. Same hand-back, different sentence — and under
`babysit-prs` the PR's own agent performs it.

**Done when**: every item in the working set carries a priority and a disposition consistent with its verdict, or is marked awaiting-reviewer. A bot's item is adjudicated like anyone else's — its author decides neither the verdict nor the priority.

## 4. Report

**Empty working set — no table.** `mergeable` is not `CONFLICTING`, no live thread, no failing check,
and every PR-level claim matched a settled thread: say that in two or three lines (the PR state, what the settled stock already
covers, what is actually left — usually an approval), and stop. No rows, no dispositions, no
`apply all` prompt, no handoff. A row is a commitment to act, and a settled PR has nothing to commit
to; a `†` footnote on a row that says "already answered" is that row admitting it should not exist.
Under `--auto` that is a report of zero selected, zero held — the ordinary state of a green PR whose
threads are all settled.

Otherwise, one markdown table — pipes and header included, one row per item, rows ordered P1 → P2 → Nit. Never a per-item list or a paragraph: the point is scanning a column, and a cell that will not fit goes to a footnote.

| # | Where | Who | Claim | Verdict | Do |
|---|-------|-----|-------|---------|----|
| P1 | `auth.ts:42` | 🤖 bugbot | null deref on `user.id` | ✅ confirmed — `auth.ts:42`, callers pass undefined | fix |
| P1 | `merge` | ⚙️ branch | conflicts with `main`, cannot merge | — | fix (hand back) |
| P1 | `ci / build` | ⚙️ check | `tsc` fails, 3 errors | — | fix |
| P2 | `sync.ts:110` | 👤 alice | why not batch these writes? | ❓ unclear — needs perf numbers | reply |
| Nit | `api.ts:8` | 🤖 bugbot | unused import | ❌ refuted — used at `api.ts:31` | decline |

- **#** — P1 | P2 | Nit. Append `†` when the priority was rounded up, and footnote the reason in one line under the table.
- **Where** — `path/to/file.ts:42`, the check name, or `merge` for the branch state.
- **Who** — 👤 `<login>` for a human, 🤖 `<login>` when `author.__typename` is `Bot`, the login ends in `[bot]`, or it is a known bot account (`naboo-ai-reviews`, `cursor` / Bugbot), ⚙️ `check` for a failing check.
- **Claim** — the item in one line, paraphrased. Quote only when the exact wording is the point.
- **Verdict** — ✅ confirmed | ❌ refuted | ❓ unclear, then the `file:line` that settled it. `—` for taste items and checks, which carry no verdict.
- **Do** — fix | reply | decline | defer.

Keep every cell to one line so rows stay scannable; the evidence that will not fit goes in a footnote under the table.

Then the awaiting-reviewer threads in their own table — Where | Who | Waiting on — one row each, nothing to act on.

Close with one line of files touched by the `fix` rows, then 1–3 sentences on overall health, counting the refutations alongside the rest ("2 P1 CI failures + 1 confirmed P1 review comment, 2 bot claims refuted, 3 P2s, 5 nits, 2 awaiting reviewer"). Never call a PR clean while it conflicts with its base, and say so when it is still a `draft`. Then:

> Tell me which items to act on — "all P1" / "all" works. Nothing is edited, pushed or posted on
> that answer: it picks the items, then `pr-respond` drafts everything and shows you one batch to
> approve.

Under `--auto`, skip that prompt. Mark each row selected or held, then list the held rows in one line ("2 held for you: #3 unclear, #7 needs a merge call").

**Done when**: every triaged item is a row — count the rows against step 3's working set — and the user has been asked to pick, or the `--auto` policy has selected for them. Zero items is a valid outcome, reported in prose with no prompt and no handoff.

## 5. Hand off

- **A selection is not an authorization.** "apply all" names items; it authorizes no edit, no
  commit, no push, no publication. Consent is a separate act, asked on `pr-respond`'s batch
  preview, never on the selection. **Under `--auto`, the caller gave that consent up front**:
  `pr-respond` shows the batch and proceeds without waiting. The gate protects an attended run; it
  is not a stall for an unattended one.
- **Nothing leaves this skill directly.** `pr-feedback` never runs `gh pr comment`,
  `gh pr review`, `gh api …/comments`, a `gh api graphql` mutation, `git commit`, `git rebase`
  or `git push`. The picks leave by one door: `pr-respond`, whose dispositions are the whole
  outward surface — a `defer` is a note in the report, not a Linear issue; a `reply (hand back)`
  is a draft, not a posted comment. Anything beyond that, the user asks for by name.
- **Do not reimplement `pr-respond`.** Doing its work inline — editing, folding, pushing,
  replying — bypasses `humanizer`, the batch preview and the confirmation, which exist only there.
  If `pr-respond` cannot be invoked, stop and say so — under `--auto`, that means reporting the
  item as **blocked**, not abandoning it quietly. Never carry on by hand.

Invoke `pr-respond` with the user's picks. It reads this triage from the conversation and does not re-fetch, so carry each picked item's priority, disposition, verdict with its evidence (the reply to a refuted claim is written from it), thread `id`, first-comment `databaseId`, `owner`, `repo` and PR number into the handoff.

Under `--auto`, pass the policy through so `pr-respond` skips its confirmation too.

**Done when**: `pr-respond` is invoked, or the user picks nothing (or there was nothing to pick) and the triage is left as the deliverable — and no write command ran inside this skill. A file edited, a commit, a push or a comment posted before `pr-respond` earned its confirmation is a failed step, not a shortcut.
