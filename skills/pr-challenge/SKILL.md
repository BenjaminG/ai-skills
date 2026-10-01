---
name: pr-challenge
description: This skill should be used when reviewing someone else's pull request the way a colleague would — a few questions that challenge the approach, the reuse, the shape, the intent or the naming — or an LGTM when the PR reads clean. Drafts the comments and hands them to pr-comment to post. Triggers on "review this PR", "challenge this PR", "leave a human review", "review @someone's PR", "what would I ask on this PR".
argument-hint: "[pr-number-or-url] [--max N] [--label] [--lang fr|en]"
---

# PR Challenge

Review someone else's PR the way a colleague who works in this repo reviews it: a few questions with stakes, each one answerable only by the author. Read-only: this skill drafts, `pr-comment` posts. It never edits code, approves, or requests changes.

This is the half of a review a findings table cannot produce: *why does this exist, why not reuse what we have, why not the simpler shape, what is this for*. Defects belong to `gate-wf`; one that turns up here leaves through **the other door** (§7), never as a question.

## Arguments

- `$0` (optional): PR number or URL. Omitted → detect from the current branch.
- `--max N` (default `6`): hard cap on posted comments — a ceiling, never a target.
- `--label`: prefix each comment with its conventional-comment label (§6). Off by default; a bare question reads more like a person.
- `--lang fr|en`: force the drafting language (§6).

## 1. Fetch the PR and its stated goal

Resolve the script the way `pr-feedback` resolves its own, then run it:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-challenge/scripts/fetch-pr-context.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-challenge/scripts/fetch-pr-context.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-challenge/scripts/fetch-pr-context.py"; do
  [ -n "$c" ] && [ -f "$c" ] && FETCH="$c" && break
done
python3 "$FETCH" [pr-number-or-url]
```

Read the diff from `diff_path`. `threads` includes settled ones.

**`is_own_pr: true` → stop** and offer `gate-wf`: challenging your own code produces questions you already know the answer to.

Write down **the stated goal** in one sentence, from the title, the body, and any `issue_refs` worth reading (`gh issue view <n>`, or `acli jira workitem view <key>` for a Jira key). Every question is measured against it. An empty body has no stated goal, and that is the first comment of the review.

**Done when**: the PR is resolved for the user (`#<n> — <url>`, author, size), the stated goal is one sentence, and the diff is in hand.

## 2. Read the repo, not just the diff

A colleague's review differs from a bot's by knowing what the repo already has. Every question in §4 is drafted from what this step finds.

Dispatch the `ai-skills:ponytail-reviewer` subagent first, so it works while you read. Give it `diff_path`, `new_declarations`, and the output file `~/.claude/pr-challenge-state/<owner>_<repo>/<n>.ponytail.json`. It runs `/ponytail-review` on the diff and greps the repo for an existing equivalent of every added symbol. When `gate-wf` state for this branch already holds `ponytail-*` findings, use those instead of dispatching.

Meanwhile, for the files the diff touches:

- **Siblings.** Read one or two existing files next to each changed one. A pattern followed twice elsewhere and broken here is a convention question.
- **Call sites.** For a changed signature, type, or component, read who calls it.
- **The repo's own rules.** `CLAUDE.md`, `AGENTS.md`, `.cursor/*.md`, `BUGBOT.md`, `docs/adr/`. `gate-wf`'s `context-checker` already reports broken rules; raise one here only when the author made a *choice* against a documented preference.

`gate-wf` state for this branch, if any, also feeds §4 with its `simplify-*` and `slop-*` findings. Its `bug-*` and `sec-*` findings are defects and stay behind the other door.

**Done when**: the ponytail subagent is dispatched (or `gate-wf`'s `ponytail-*` findings are in hand), and at least one sibling file per changed area has been read.

## 3. Step back: the approach pass

Read the diff whole before reading it closely: that is how you review the solution the author chose, not just the lines they wrote. Write down:

1. **The behaviour.** What someone using this code sees, traced end to end through the diff, in two sentences. A gap against §1's stated goal is already a question.
2. **The mechanism.** The largest new thing the diff introduces — a state machine, a polling loop, a cache, a table, a module, an abstraction — by path. A PR that changes a value, fixes a branch or adds a field has none: write "no mechanism" and go to §4. That is the common case.
3. **The constraint it works around**, and **where it lives** — usually another layer, another package, sometimes another team's file: an API that returns the wrong thing, a write path that settles out of band, a type that cannot be widened.

Then ask: **could the constraint have moved instead?** Eight hundred lines of client-side machinery against a constraint that is one return type on the server is an `approach` candidate no line-level pass can find.

The candidate is **the alternative**: another solution, named, concrete, cheaper in a way one clause states, that **removes machinery in this diff** rather than introducing a pattern that isn't there. No alternative you can name → no candidate, and no comment: an approach question without its alternative can only be answered "because".

**Done when**: the behaviour is two sentences, the mechanism is named or "none", and where there is one, the constraint is named and there is either an alternative that removes machinery from this diff, or nothing.

## 4. The passes

Fold in the ponytail findings from §2 first; wait for the subagent if it has not returned. Each finding is a lead, never a comment: drop its `tier` and map it by `rule_id`.

| `rule_id` | Becomes |
|---|---|
| `ponytail-exists` | `exists` — **read** the existing symbol yourself before citing it: a helper that shares a name and not a job produces the worst comment in a review |
| `ponytail-stdlib`, `ponytail-native`, `ponytail-shrink` | `simpler`, its `suggested_fix` as the named shape |
| `ponytail-yagni`, `ponytail-delete` | `intent` ("what needs this?"); on the mechanism §3 named, evidence for its `approach` alternative |

Each pass looks for candidates; on most PRs most come back empty. A candidate carries a `kind`, a `file:line` on the diff, the question in one clause, and its **evidence**. Evidence admits the candidate and stays in your notes for §5 to cut on; the comment spends at most one clause of it. Evidence that cannot survive that compression is a defect report wearing a question mark — the other door.

| Kind | Asks | Evidence that admits it | What reaches the comment |
|---|---|---|---|
| `approach` (§3) | could the constraint have moved? | mechanism and constraint by path, plus the named alternative | the alternative, one clause |
| `intent` | what is this for? | the diff shows *what*; neither it, the body nor the ticket shows *why* | nothing — the question stands alone |
| `exists` | why not reuse what we have? | `path:symbol` of the existing thing, read, doing the same job | the `path:symbol` |
| `simpler` | why not the shorter shape? | the replacement, named in one clause | the shape |
| `naming` | what does the name promise, against what it does? | the gap in one clause: what the name claims, what the thing is | the gap, plus the domain term or the repo's own word if one exists |
| `scope` | is this in this PR? | the stated goal, and the lines outside it | the stated goal, half a sentence |
| `convention` | why differently from the repo? | **two or more** existing call sites from §2 | the call sites |

`approach` is the strategy of the whole PR and removes machinery; `simpler` is a shape inside one hunk. `approach` is also the rarest kind by far — about 1800 mined human-reviewed PRs on a repo of this shape held none — so treat one as an unusual event whose evidence must be exactly right.

**`intent` earns the review, and is the easiest to fake.** Can you state, from the PR alone, what this code does *and* why the product needs it? Both → no comment. The what but not the why → that is the question. Neither → back to §2. A question answered three lines down in the diff is the worst comment a reviewer can leave.

**`exists` and `simpler` ask, they do not instruct**: the author may have a reason the grep cannot see — a deliberate fork, a deprecation in flight, a perf constraint.

**`naming` is the gap, never the preference.** "I would have called it something else" is taste, and §5 drops it.

**Done when**: every candidate carries a kind, a `file:line` present in the diff, and evidence of its own family. Nothing admitted → **LGTM**: go straight to §7.

## 5. Cut to the review a person would leave

**LGTM is a complete review.** Across forty-five days of this team's PRs, most got no human comment and the rest got one or two. A review with something to say on every PR, or eighteen comments on one, is how anyone spots a machine.

Drop, in this order:

1. **Answered.** The diff, the body, a linked ticket, or a `threads` entry — settled ones included — already made the point. Re-raising a resolved thread is the loudest automated tell.
2. **No evidence.** §4's bar, applied without mercy.
3. **No stake.** What changes when the author replies? Nothing → gone.
4. **Collapse.** Candidates circling one worry become **one** comment on the line where the worry starts. Where an `approach` survives, drop the local candidates inside the mechanism it questions: answering it rewrites them anyway.
5. **Taste with no cost.** A formatting preference, or a rename that costs a commit and buys nobody anything. Keep a nit only when it would bother the next reader of the file.

Then two ceilings:

- **One `naming` comment**, on its own budget: a domain expert can be right eight times on one PR, a pass that read the repo for an hour cannot. Keep the name that costs the reader most.
- **One or two nits.** A comment that restates the line under it is a nit.

Rank what is left by what you most want answered and take the top `--max`. The first comment sets how the review reads: a surviving `approach` is worth putting first — once the PR merges, the machinery stays — but it does not open by right.

**Done when**: every candidate has met the five drops and both ceilings, survivors are at or under `--max`, each has a reason it survived, and the drops are counted by cause. An empty set is an LGTM.

## 6. Draft in a reviewer's voice

Pick the language: `--lang`, else the language of this PR's human `threads`, else the majority of `language_sample`, else the PR body's. Never this conversation's — the author and their team read it, not the user.

Read `references/voice.md` before the first comment and draft each survivor to its shape; that shape is the one thing in this skill that does not bend.

Route every comment through the `humanizer` skill — mandatory, it applies the user's `STYLE.md` — then re-check the shape: a rewrite that buries the ask fails this step.

With `--label`, prefix `question: ` for `intent` and `scope`, `suggestion: ` for `exists` / `simpler` / `naming` / `convention`. A nit keeps `nit: ` always, label or not: that prefix is how a person says "do not block on this".

**Done when**: every comment follows `voice.md`'s shape, is in the PR's language, has been through humanizer, and carries no tier marker — a `**blocker:**` or `**major:**` here means a defect leaked in.

## 7. Hand off to pr-comment

**LGTM → no handoff.** Report the stated goal, what §2 read (symbols searched, siblings opened, call sites checked), and one line saying nothing here needs asking. An LGTM that names nothing it read is a shrug.

Otherwise report in three or four lines: the stated goal, one line per comment (`kind · file:line · the question`), drop counts by cause, and any **defect** §2 turned up, in one sentence pointing at the other door: `gate-wf` on the branch, then `pr-comment` for the findings. A null deref phrased as "is this always defined?" is a bug report the author closes with "yes".

Then invoke `pr-comment` in **challenge mode** with, per comment: `kind`, `file`, `line`, `location` (`diff-line` on the diff, `adjacent` otherwise), the body, and the PR's `owner` / `repo` / number / `head_sha`. `pr-comment` owns the preview, the confirmation, the posting and the stale-line skip; this skill never runs `gh api …/comments`, `gh pr review` or `gh pr comment`.

**Done when**: `pr-comment` is invoked with the comment set, or the LGTM report is the whole review.
