---
name: pr-respond
description: This skill should be used after pr-feedback triage, when the user has picked which review items to act on and wants them applied and answered — apply the agreed code change per item, then post the reply, reaction, and (for inline threads) thread resolution in one confirmed batch. Triggers on "apply the PR feedback", "respond to the reviewers", "resolve the threads", "post my replies", or selecting items after a pr-feedback report.
argument-hint: "[items — e.g. 'all P1' | 'all' | specific item numbers] [--auto <policy>]"
---

# PR Respond

Apply the agreed code changes for the review items the user picked, then post the reply, reaction, and (for inline threads) thread resolution — all after a single confirmation.

## Prerequisites

This skill consumes the prior `pr-feedback` triage from the conversation. Each selected item carries:

- **disposition** — fix (apply the change) / reply (answer, no change) / decline (won't fix) / defer (track for later)
- **verdict** — for a defect claim: confirmed / refuted / unclear, with the `file:line` that settled it. The reply to a refuted claim is written from that evidence, so a refuted item arriving without it goes back to `pr-feedback` for adjudication rather than getting a hand-waved reply.
- **inline-thread `id`** — GraphQL node id (from §2 of pr-feedback), needed to resolve the thread
- **first-comment `databaseId`** — needed for the reply and reaction endpoints
- **`owner` / `repo` / PR number**

If that context is absent (no triage in this conversation), run `pr-feedback` first — this skill does not re-fetch.

**Selecting is not forcing a fix.** "apply all" / "apply all P1" / picking items means *act on each per its disposition* — only `fix` items get a code change. The verb `fix` is reserved for actually changing code; it is never how the user selects items. When the user's instruction contradicts a disposition (e.g. "apply all" over a `decline` item), the **disposition wins** — flag the mismatch in the batch preview ("you said apply, but this was recommended `decline`: replying without a code change — say so if you want to force a fix") rather than silently editing.

Replies are drafted through the `humanizer` skill (see below) — that dependency is mandatory, not optional.

## The loop

`disposition` drives each item. Process in priority order (P1 → P2 → Nit), batching edits by file. Per item:

1. **Apply** — for `fix`, make the agreed code change. Skip the edit for `reply`, `decline`, and `defer`.
2. **Draft the reply** — a 1–3 sentence reply stating what was done (applied + how) or why it was declined. Route it through the `humanizer` skill. **Never post a raw draft — always route it through humanizer first.**

   Into a **bot** thread, that reply ends the exchange. It reports a decision already taken — applied, refuted, declined, deferred — and closes. No question ("what do you think?"), no offer waiting on an answer ("happy to open a follow-up if you think it's relevant"), no choice handed to a reader who is not there. Humanizer shapes the voice; this rule fixes what the sentence commits to. A human thread keeps the full register — a question there has a reader.
3. **Pick the reaction** — `fix` / agreed → 👍 (`+1`); `decline` → 👎 (`-1`). `reply` / `defer` → no reaction unless you're agreeing.
4. **Add to the batch preview** — three blocks, in this order, so nothing that leaves the machine is missing from it:

```
## Batch — PR #<n>
### Code (<k> files)                    one line of delta per file
### Fixup + push                        <n> fixups → <m> original commits,
                                        git push --force-with-lease, <old> → <new>
### Reply to @<login> (thread <id>)     the humanizer draft, the reaction,
                                        resolved or left open
```

Step 1's edits are **local**: they come before the preview because they are what makes it concrete. Everything that leaves the machine — `commit`, `rebase`, `push`, replies, reactions, resolutions — comes after the confirmation. Under `--auto`, that confirmation is the policy the caller already gave.

Show the **one batch preview**, then post everything only after a **single** confirmation. One confirmation covers all three blocks. Under `--auto <policy>`, passed through by `pr-feedback`, the caller has already authorized the batch. Show the preview and proceed without waiting — within the limit that policy carries: a **human-authored** item is never in the batch. Every bot item in it is replied to, reacted to and resolved — including a claim confirmed as real but deliberate, which your reply settles. The one exception is an item whose reply ends in a question only the author can answer, which is replied to, **left open** and reported as **held**.

**Done when** every selected item has been either applied-and-answered or explicitly skipped with its reason, *and* the summary lists each item's outcome (reply posted / reaction set / thread resolved-or-not). Don't stop before every picked item is accounted for.

## Ship the code first

A reply saying "applied" is a lie until the code is on the remote. The reviewer clicks the thread and sees the old line. So once the batch is confirmed, and before any reply goes out, invoke the `fixup` skill if any item changed code. It folds each change into the commit that introduced it and force-pushes with lease.

If `fixup` stops, whether on a merged-base commit, a rebase conflict, or a non-empty verify diff, post nothing. Report the blocker and leave the threads open.

If no item changed code, meaning everything was `reply`, `decline`, or `defer`, skip straight to posting.

## Posting (after confirmation, and after the push)

- **Reply — inline review thread:** `gh api repos/{owner}/{repo}/pulls/<n>/comments -f body='…' -F in_reply_to=<databaseId>`
- **Reaction — review comment:** `gh api repos/{owner}/{repo}/pulls/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Reaction — issue / conversation comment:** `gh api repos/{owner}/{repo}/issues/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Resolve — inline threads only:** `gh api graphql -f query='mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } } }' -f id=<thread-id>` using the thread `id` from triage.

Notes:

- **A bot thread ends resolved once it is settled.** Reply, react, resolve — in that order, every time you actually settled it. Leaving a settled thread open waits on a reader who will not come: the bot never answers, and the thread just sits there.
- **An answer settles the thread; only a question holds it open.** The test is one sentence: *does my reply end in something the author has to answer before the code can be right?* "Confirmed, but deliberate — the test at `foo.spec.ts:12` names the intent", "confirmed, but scoped on purpose per `doc.md:164`", "refuted", "already covered": those are answers. Nothing is owed, so reply, react, **resolve** — a settled thread left open reads as an outstanding claim and drags the PR's status to `your-call` for nothing. Hold a thread open only when the remedy is a choice you cannot make for the author — an architecture to pick, a trade-off only they can weigh, an ADR to change — and your reply names that choice as an open question.
- **A held thread stays open, and that is the whole point.** For that kind of item — a real question left with the author — reply with the adjudication and the question, react, and **stop there**: no resolve. A resolved thread is one the author has to go looking for behind a "show resolved" toggle, which is exactly the wrong place for the only thing still asking them something. Report the item as **held**; the gist reaches them in the summary, the question stays where the code is. Our reply sitting last on a bot thread is also the signal `fetch-pr.py` reads as `held` and `babysit-scan.py` counts outside `unresolved_bot`, so an open held thread costs nothing: it spawns no agent and draws no second reply. Only the author closes it. A bot that answers *back* on a held thread does not reopen the item either — the next pass reads that reply, and an acknowledgement is answered with silence, never with a second post on top of the question.
- **A thread already marked `held` is not an item.** An earlier pass answered it and left it open on purpose. Post nothing, resolve nothing, carry it into the held count.
- **Only a thread with a Resolve button gets a reply.** PR-level conversation comments — a review bot's `AI Review` summary, a CI recap, anything posted on the conversation tab rather than on a line — have no thread to resolve, and a reply there is a new top-level comment everyone gets mailed about. React if it helps; never reply. Fix what such a comment got right in the code, and say in the summary that it was acted on without an answer.
- **A review submission is not a thread either.** The body of an APPROVED or CHANGES_REQUESTED review lives on the conversation tab, same as any PR-level comment.
- **Draft the answer, never post it.** An item marked `reply (hand back)` still gets written — a refutation, a correction, whatever the claim earns — but it goes in the summary handed back to the author, ready to paste, and never through `gh pr comment` or `gh pr review`. Only the author decides to mail the whole PR. To clear a stale CHANGES_REQUESTED, offer `gh pr edit <n> --add-reviewer <login>`; don't run it.
- CI-check items have nothing to reply to; they're fixed by editing code, not by posting.
