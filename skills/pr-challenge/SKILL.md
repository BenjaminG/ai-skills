---
name: pr-challenge
description: This skill should be used when reviewing someone else's pull request and the goal is the review a colleague would leave — questions that challenge the code, asking why something was written instead of reusing what the repo has, naming a simpler shape, asking what a piece is for. Produces a few drafted comments — or an LGTM when the PR reads clean — never a findings table, and hands what it has to pr-comment to post. Triggers on "review this PR", "challenge this PR", "leave a human review", "review @someone's PR", "what would I ask on this PR".
argument-hint: "[pr-number-or-url] [--max N] [--label] [--lang fr|en]"
---

# PR Challenge

Review someone else's PR the way a colleague who works in this repo reviews it: a few questions with stakes, each one answerable only by the author. Read-only until `pr-comment` posts — this skill drafts, it never edits code, approves, or requests changes.

**This is not a gate.** `gate-wf` hunts defects and returns a verdict; `pr-comment` posts those findings with tier markers. This skill covers the other half of a review, the half a findings table cannot produce: *why does this exist, why not reuse what we have, why not the simpler shape, what is this for*. A defect that turns up along the way leaves through the other door — see §6.

## Arguments

- `$0` (optional): PR number or URL. Omitted → detect from the current branch.
- `--max N` (default `6`): hard cap on posted comments. See §4 — a ceiling, never a target.
- `--label`: prefix each comment with its conventional-comment label (`question:`, `suggestion:`, `nit:`). Off by default; a bare question reads more like a person.
- `--lang fr|en`: force the drafting language instead of inferring it (§5).

## 1. Fetch the PR and what it claims to do

The script ships with the plugin; resolve its path the way `pr-feedback` resolves its own (plugin-root env → newest plugin cache → global-skills fallback), then run it:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-challenge/scripts/fetch-pr-context.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-challenge/scripts/fetch-pr-context.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-challenge/scripts/fetch-pr-context.py"; do
  [ -n "$c" ] && [ -f "$c" ] && FETCH="$c" && break
done
python3 "$FETCH" [pr-number-or-url]
```

One JSON blob: the `pr` (with `head_sha`, `title`, `body`, size), `viewer`, `is_own_pr`, `issue_refs`, `files`, `diff_path` (the diff on disk — read it from there), `new_declarations` (the symbols the diff introduces, per file), every `threads` entry including settled ones, the `pr_comments`, and a `language_sample` of short human review comments from elsewhere in the repo.

**`is_own_pr: true` → stop.** Reviewing your own branch is `gate-wf`; say so and offer it. Challenging your own code produces questions you already know the answer to.

Then write down **the stated goal** in one sentence, from the title, the body, and any `issue_refs` worth reading (`gh issue view <n>`, or the `acli` skill for a Jira key). That sentence is the yardstick for §3's scope pass and the thing every question is measured against. A PR whose body is empty has no stated goal, and that is itself the first comment of the review.

**Done when**: the PR is resolved for the user (`#<n> — <url>`, author, size), the stated goal is written down in one sentence, and the diff is in hand.

## 2. Read the repo, not just the diff

The whole difference between a colleague's review and a bot's is that the colleague knows what is already in the repo. This step buys that knowledge, and it is the step that must not be skipped — every question in §3 is drafted from what it finds.

For each entry in `new_declarations`, grep for an existing equivalent: the name, then the *job* the thing does (two or three keywords from its body), widening file → module → package. A hit that does the same job is the material for a reuse question, and it must be **read** before it is cited — a helper that shares a name and not a job produces the worst comment in a review.

Then, for the files the diff touches:

- **Siblings.** Read one or two existing files next to each changed one. How does this repo write a service, a hook, a handler, a test? A pattern followed twice elsewhere and broken here is a convention question.
- **Call sites.** For a changed signature, type, or component, read who calls it. A reviewer asking "what happens to the other callers" has read them.
- **The repo's own rules.** `CLAUDE.md`, `AGENTS.md`, `.cursor/*.md`, a `BUGBOT.md`, `docs/adr/`. A rule the diff breaks is not a question, it is a citation — and `gate-wf`'s `context-checker` already reports those, so only raise one here when it is genuinely a *choice* the author made against a documented preference.

`gate-wf` state for this branch, if any, is fair input for this step: fold in its `ponytail-*`, `simplify-*` and `slop-*` findings as **candidates** for §3. Never its `bug-*` or `sec-*` findings — those are defects, they already have a door, and dressing one up as a question buries it.

**Done when**: every symbol in `new_declarations` has been searched for, each hit that will be cited has been read, and at least one sibling file per changed area has been read. A reuse question resting on a grep hit nobody opened is not evidence.

## 3. The four passes

Each pass looks for candidates, and on most PRs most passes come back empty. A candidate carries a `kind`, a `file:line` on the diff, the question in one clause, and its **evidence** — and a candidate with no evidence is not a candidate.

**Evidence is what admits a candidate, not what the comment says.** It is held here, in your notes, so that §4 can cut on it; §5 spends at most one clause of it, usually just a cited path or symbol. A candidate whose evidence cannot survive that compression is a defect report wearing a question mark — §6's other door.

| Pass | Asks | Evidence that admits it (held, not written out) | What survives into the comment |
|---|---|---|---|
| `intent` | what is this for? why is it needed? | the thing that is missing: the diff shows *what*, and neither the diff nor the PR body nor the linked ticket shows *why* | nothing — the question stands alone |
| `exists` | why not reuse what we have? | `path:symbol` of the existing thing, read in §2, doing the same job | the `path:symbol`, cited |
| `simpler` | why not the shorter shape? | the replacement named in one clause — the shape, not "consider simplifying" | the shape, named |
| `scope` | is this in this PR? | the stated goal from §1, and the lines that fall outside it | the stated goal, in a half-sentence |

A fifth kind is allowed where §2 found it: `convention` — this repo does this differently, with **two or more** existing call sites as evidence. One counter-example is not a convention.

Two disciplines hold across all four:

**The `intent` pass is the one that earns the review, and the one easiest to fake.** The test is a sentence: can you state, from the PR alone, both what this code does *and* why the product needs it? Both yes → no comment, whatever the code looks like. Can state the what but not the why → that is the question, and it is a real one. Neither → you have not read enough to ask anything; go back to §2. A question whose answer is three lines down in the diff is the single worst comment a reviewer can leave, and it is the one an automated pass leaves most.

**`exists` and `simpler` ask, they do not instruct.** The author may have a reason the grep cannot see — a deliberate fork, a deprecation in flight, a perf constraint. Draft the question so a "no, because…" is a complete answer, and so that answer costs the author one sentence.

**Done when**: every candidate that exists carries a kind, a `file:line` present in the diff, and evidence of its own family. Four passes run and nothing admitted is a finished §3 and an **LGTM** — skip §4 and §5 and go straight to §6.

## 4. Cut to the review a person would leave

**LGTM is a complete review.** Twenty human comments across forty-five days of this team's PRs — most PRs got none, and the ones that got any got one or two. A colleague spends a comment on what they actually want to know and says nothing on the rest.

An eighteen-comment review is how anyone can tell a machine wrote it, and so is a review that found something to say on every PR it touched. `--max` is a ceiling, never a target.

Nothing survived §3 → the review is an LGTM; go to §6 and report what you read. Otherwise drop, in this order:

1. **Answered.** The diff answers it, the PR body answers it, a linked ticket answers it, or a `threads` entry already made the point — settled threads included. Re-raising a resolved thread is the loudest automated tell there is.
2. **No evidence.** §3's bar, applied without mercy. A reuse question with no path, a simpler question with no named shape, a convention question with one example: gone.
3. **No stake.** Would you want the answer, or is this talk to fill a review? Ask of each: what changes when the author replies? Nothing → gone.
4. **Collapse.** Several candidates circling one worry — the same helper, the same abstraction, the same field — become **one** comment on the line where the worry starts. Not one per angle.
5. **Taste with no cost.** A rename or a formatting preference that costs the author a commit and buys nobody anything. Keep a nit only when it would bother the next person to read the file, and cap the review at one or two.

Then rank what survives by what you most want answered, and take the top `--max`. Order matters: the first comment sets how the review reads.

**Done when**: every candidate has been held against the five drops, the survivors are at or under `--max`, each survivor has a reason it survived, and the drops are counted by cause (one line, for §6's summary). An empty survivor set passes this step like any other — it is an LGTM.

## 5. Draft in a reviewer's voice

Read `references/voice.md` before writing the first comment — it holds the rules and the before/after pairs, and this is the step where an automated review gives itself away in the first four words.

Pick the language first: `--lang` if given, else the language of this PR's existing human `threads`, else the majority language of `language_sample`, else the PR body's. Never the language of this conversation — the comment is read by the author and their team, not by the user.

Then draft each surviving candidate into this shape, which is the one thing in this skill that does not bend:

- **First sentence: the ask, alone.** The question and nothing else — no premise before it, no clause chained on with "alors que" / "whereas" / "donc" / "so". It ends at the question mark.
- **Second sentence: optional, one clause at most**, and it is the §3 evidence compressed to the path or symbol that makes the question answerable — `convertBookingPrice` in `convert-booking-price.ts`, `orders.ts:40`. Never two clauses, never a re-derivation of what the diff does.
- **Under 35 words all in**, and aim at half that: the human comments this is drafted against run about thirteen.

A draft whose first sentence carries a premise before the question is not a comment yet — move the premise into sentence two, or drop it. A question that needs two chained premises to be understood is a defect report, not a question; it leaves through §6's other door.

Route every comment through the `humanizer` skill. That dependency is mandatory, not optional: humanizer strips the tells (the rule of three, the signposting, "Consider…", the hedged parallelism) and applies the user's `STYLE.md`. Re-check the shape after humanizer runs — it rewrites sentences, and a rewrite that buries the question fails this step.

With `--label`, prefix the humanized body: `question: ` for `intent`, `suggestion: ` for `exists` / `simpler` / `convention`, `nit: ` for a kept nit, and `scope` takes `question: `. Without it, post bare — except a nit, which keeps `nit: ` always, because that prefix is how a person says "do not block on this".

**Done when**: every comment opens on its question, keeps at most one clause of evidence behind it, sits under 35 words, is in the PR's language, has been through humanizer, and carries no tier marker. A `**blocker:**` or `**major:**` in this set is a bug — those belong to `pr-comment`'s findings mode, and their presence here means a defect leaked in from §2.

## 6. Hand off to pr-comment

Invoke `pr-comment` in **challenge mode**, carrying for each comment: `kind`, `file`, `line`, `location` (`diff-line` when the line is on the diff, `adjacent` otherwise), the drafted body, and the PR's `owner` / `repo` / number / `head_sha`. `pr-comment` owns the batch preview, the single confirmation, the `gh api` posting and the stale-line skip — do not reimplement any of it here, and never run `gh api …/comments`, `gh pr review` or `gh pr comment` from this skill.

**On an LGTM, there is no handoff.** Do not invoke `pr-comment` at all. Report instead: the stated goal, what §2 actually read — the symbols searched for, the sibling files opened, the call sites checked — and one line saying nothing here needs asking. An LGTM backed by a reading you can cite is a review; one that names nothing is a shrug.

Otherwise, before the handoff, report in three or four lines: the stated goal you reviewed against, the surviving comments as one line each (`kind · file:line · the question`), the drop counts by cause, and — if §2 turned up an actual **defect** — one sentence naming it and pointing at the other door: `gate-wf` on the branch, then `pr-comment` for the findings. Never smuggle a defect into this batch as a question; a null deref phrased as "is this always defined?" is a bug report the author can close by saying "yes".

**Done when**: `pr-comment` is invoked with the comment set, or the review was an LGTM and the report is the whole of it. Nothing was posted from inside this skill.
