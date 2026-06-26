---
name: build-in-public
description: This skill should be used when the user wants to write their end-of-day / evening "build-in-public" update for a given Linear project — 2-3 impact-focused bullets plus a Next line synthesized from the project's Linear activity and the repo's git/PR shipping evidence, ready to paste into the pod thread. Invoke as /build-in-public with a Linear project ID. Triggers on "build-in-public post", "evening update", "what did I ship today", "end-of-day update", or any variant of "what did I do today" for a work update — even without the word "skill". Default to drafting; never post anywhere automatically.
argument-hint: "<linear-project-id>"
allowed-tools: Bash(linear:*), Bash(git:*), Bash(gh:*), Bash(devsql:*), Bash(date:*), Bash(jq:*), AskUserQuestion
---

# Build in public

Turn a day's raw work into a short, high-signal evening update that reads as *impact and direction*, not activity. It is NOT a demo and NOT a status report — its currency is **progress + decisions + what got unblocked**, which is exactly what foundation/groundwork days produce.

**The reader is a PM / project owner, not a teammate dev.** They do NOT know what a `BOF-438` is, what a "walking skeleton" is, or which file a schema lives in. Write in **features and business outcomes**: name the feature ("Host submission form"), say what it unlocks for the product, and keep ticket IDs as trailing tags only — never as the subject of a sentence. If a bullet can't be understood by someone who has never opened the repo, it's written wrong. Jargon is the enemy, not length.

**Match the pod's house style — this is how the user actually posts:**

- **Bullets are `•`, not `-`.** Each is a complete, readable clause (not a telegraphic fragment): a full thought a PM can parse on its own. Don't compress a real sentence into noun-soup to save words.
- **Trailing ticket tags, not inline PR links.** Close a bullet with `(BOF-518)` or `[BOF-438]` — the work item, not a `#1234` PR number. The pod tracks tickets; a bare PR number means nothing to the reader. Only surface a PR link when the bullet *is* "ready for review" and the link is the call to action.
- **First name only**, no surname. The user signs `🛠️ Benjamin — DD/MM`.
- **2-3 substantive bullets + one `⏭️ Next` line.** Closer to 2 than 4. Cut anything that doesn't carry impact or position.

Here are three real posts (use them as the target shape, not the abstract template):

```
🛠️ Benjamin — 22/06
• Spec'd out the Host submission form: locked the last open product questions on the host form + its payment-schedule data in the back-office, so the build can start clean. [BOF-438]
• Design session this morning with the team to move the payment queue itself forward.
• ⏭️ Next: kick off phase 1 of the Host submission form — first implementation slice.
```

```
🛠️ Benjamin — 23/06
• Host submission form fully coded: hosts set their payment schedule (deposit → intermediary → balance) directly in the BO on the V2 schema. 4 PRs created, not yet merged (BOF-438).
• Two reminder features turned on in prod via feature flags: the daily Slack digest flagging signed deals missing a PO or card payment to AM/AEs (BOF-402), and the client-facing PO reminder email, Enterprise-only (BOF-430). Built earlier, activated today.
• ⏭️ Next: self-review + QA the 4 PRs. Then spin up an ephemeral env to open product QA, and request code review on each PR (BOF-438).
```

```
🛠️ Benjamin — 25/06
• Rebuilt the payment-schedule feature as a clean 5-PR stack. The first pass wasn't up to bar — PRs too big to review, and the UI drifted too far from the mockups. Re-sliced by user story so each piece is small, reviewable, and ships on its own risk: Foundations (BOF-518), Marketplace form (BOF-519), Enterprise €50k gate (BOF-520), BO editing + host lock (BOF-521), rollout + telemetry (BOF-522). (BOF-438)
• Foundations is the shared base every slice rides on — payment-schedule contracts, schedule builder + validation, and sticky V2 assignment that locks a booking onto staged payments once chosen (BOF-518).
• ⏭️ Next: get Foundations reviewed (it gates the rest), then walk the stack up — Marketplace form (BOF-519), then Enterprise gate (BOF-520).
```

These bullets are *complete clauses with a decision baked in*, not one-line fragments — but the decision is stated, not narrated over a paragraph (see rule 4).

The update is **scoped to one Linear project**, passed as `$ARGUMENTS`. If no project ID is given, ask for it before gathering anything — it is the scope anchor and there is no sensible default.

## Step 1 — Resolve the project, then gather today's work

Pull the raw material first. Don't ask the user to type it out if the tools can find it. Linear is the primary source (the project scopes the work); git/PRs are the *shipping evidence*; devsql is *enrichment + a heads-down backstop*.

**Resolve the project ID → name first.** `linear issue query` filters by `--project` *name*, not ID, while `$ARGUMENTS` is a project *ID*. Look up the name (and team) once:

```bash
linear project view "$ARGUMENTS" --json | jq -r '{name, team: .teams.nodes[0].key}'
```

**Linear — issues in that project that moved today** (use the resolved name):

```bash
linear issue query --project "<name>" --assignee "@me" \
  --updated-after "$(date +%F)" --all-states --limit 50 --json
```

Split the results into *shipped* (state type `completed`, or state name matching `/review/i`) vs *in-flight* (`started`). See the `linear-cli` skill for any further CLI mechanics — don't re-document them here.

**Linear is the scope authority. git/PRs are evidence only when they map to a Linear issue *in this project*.** A repo holds work for many projects; today's commits and PRs may belong to a different one entirely. Before any PR/commit becomes a bullet, confirm its issue is in the project's `linear issue query` result above. If it isn't — drop it, don't narrate it. Likewise, a CLOSED PR is not "in-flight": don't invent a story to reconcile it. **When in doubt about whether a day produced shippable code at all, ask the user one line ("code today, or spec/planning?") rather than assembling a plausible-looking shipping narrative from loose git activity.** Fabrication is the worst failure mode here.

**git / PRs — shipping evidence from the current repo:**

```bash
# PRs authored today (opened, updated, or merged)
gh pr list --author "@me" --state all --search "updated:>=$(date +%F)"

# Commits today (current branch/repo only — no --all)
git log --author="$(git config user.email)" --since="00:00" --oneline
```

**devsql — what was actually worked on and decided today (this repo):** local Claude Code/Codex history joined with git. Use it to *recover decisions and their rationale* (the "because Z" in rule 4) and to *substantiate a heads-down day* (rule 7) when git+Linear are thin — NOT to list activity.

```bash
# Today's session topics for this repo
devsql "SELECT s.title, s.git_branch, s.user_message_count
  FROM sessions s
  WHERE s.cwd = '$(pwd)'
    AND date(s.last_timestamp) = date('now','localtime')
  ORDER BY s.last_timestamp DESC"
```

For prompt-level detail (the actual decisions debated), query `history.display` filtered to today. See the `devsql-querying` skill for schema and query mechanics (note `cwd` can be a worktree path, and `title` may be empty on in-progress sessions — fall back to `git_branch`). devsql reads local history only and may be absent — treat it as optional. It is the weakest of the three signals: never let a raw prompt become a bullet, and never let it inflate the post toward activity-over-impact.

If a source isn't reachable (no `linear`/`gh`/`devsql`, auth fails, project ID invalid), fall back to asking the user to paste their issues/PRs — never fabricate activity.

## Step 2 — Synthesize (this is the whole point)

Apply these rules, in priority order. They exist because a daily that just lists tasks ("worked on X, worked on Y") signals effort, not impact — and on a foundation day it makes real work look like nothing.

1. **Foundation as headline.** If several items share a piece of infra/groundwork built (a flag, a collection, an abstraction, a schema), lead with that shared foundation and make the features the *evidence it already pays off* ("two consumers ride on it"). Cross-cutting groundwork is the strongest impact signal — never bury it in a parenthetical.
2. **Report movement, not effort.** Ban "started / began / worked on / spent time on". State what is now *true* (shipped / in review / in flight) and where it sits on the trajectory. "Started the email" → "Email scaffolded from the PRD; data layer done."
3. **One impact anchor.** At least one bullet ties to the business *why* / what it unlocks (the "so that"). If the why isn't obvious from the work, DO NOT invent it — surface it as a one-line note for the user to confirm or fill in.
4. **Decisions carry their rationale.** When the day's work was a choice, render it "X over Y because Z" rather than just naming the change. The "because Z" usually isn't in git or Linear — mine the devsql session/prompt history to recover it.
5. **Tag the work item.** Every concrete item closes with its issue tag — `(BOF-518)` or `[BOF-438]`, the work item the pod tracks. Inline PR numbers (`#1234`) are NOT the default: surface a PR link only when the bullet itself is a review request ("ready for review", "needs a reviewer") and the link is the call to action.
6. **Split the Next line by grain.** Separate in-flight continuations from new big items. Don't flatten a multi-day new workstream to the same level as "finish the thing I'm already on".
7. **A heads-down day is a legitimate report.** If there's no shippable or visual output, say so honestly and give position + ETA ("Deep in the X schema, no visible output yet, first cut tomorrow"). When git+Linear are thin, the devsql session titles/topics are what tell you *where* you got to and what's next. This sets expectations and kills the "what are they doing?" question. Never pad to look busy.
8. **Complete clauses, not fragments — 2-3 bullets + one Next.** Each bullet is a full, readable thought (the real posts above are the bar), not a telegraphic noun-phrase. But brevity lives in the *count*: closer to 2 substantive bullets than 4, riding on shared pod context. A bullet may carry a decision and its consequence; it must not sprawl into a paragraph.

## Step 2.5 — Order before you write

Rule 1 is a principle the model reads then ignores, generating in the chronological order it gathered (engine → mail → "oh and the shared path"). This step is the forcing function. Do it explicitly before writing a single bullet:

1. **Name the one cross-cutting item** — the shared infra/groundwork that ties multiple items together (here: the single PO-detection path both consumers ride). There is at most one.
2. **It appears exactly once.** If a bullet's tail re-describes it (e.g. "…riding on the shared X the cron also uses"), cut the tail. No point is stated twice — least of all the shared-infra one.
3. **Placement (tiebreak rule 1 vs 3):**
   - Shared-infra **is** the day's biggest deliverable → headline (bullet 1).
   - Otherwise → bullet 2, as the spine connecting the consumers. **Never last, never a parenthetical.**
   - Don't mechanically promote a minor arch note to the top just to satisfy rule 1.

## Step 2.7 — De-slop with humanizer

Once the bullets are written, pass the draft through the `humanizer` skill to strip AI tells (inflated/promotional words, vague attributions, filler phrases, signposting) and apply the user's personal `STYLE.md` if present.

**The Output format below overrides humanizer** — this post's conventions are intentional, not slop. Humanizer must NOT touch:

- **em-dashes and `→` arrows** — they are structure (foundation → unlock, decision X → Y), not dash overuse.
- **terse fragments** — bullets are not required to be full sentences; the post rides on shared pod context.
- **emoji, `•` bullets, and ticket tags** — `🛠️`, `⏭️`, `•`, `(BOF-518)`, `[BOF-438]` all stay.

So: keep the shape, remove the tells. If humanizer is unavailable, ship the draft as-is — it's a polish pass, not a gate.

## Output format

ALWAYS produce exactly this shape, as a fenced markdown block ready to paste:

```
🛠️ <first name> — <date>
• <foundation or highest-impact item — complete clause, what it unlocks, trailing (TICKET)>
• <consumer / feature item — status, trailing (TICKET)>
• ⏭️ Next: <in-flight continuation>. Then <new item (TICKET)>; + <smaller item (TICKET)>.
```

- Bullets are `•`. First name only in the header. Date via `$(date +%d/%m)`.
- 2-3 substantive bullets + the Next line. A third bullet only if it carries its own impact — otherwise stop at 2.
- Close each concrete item with its `(TICKET)` tag. Use a PR link only on a review-request bullet (rule 5).

## Gate before delivering

This is not a decorative checklist — it is a gate. Before emitting, run every item. **If any item fails, rewrite the post and re-run the whole list. Emit nothing until all pass.**

- [ ] No "started / began / worked on" — every line states movement or position.
- [ ] Every bullet is readable by a PM who has never opened the repo — feature/business language, no jargon, ticket IDs as trailing tags only.
- [ ] Bullets are `•`, header is first-name-only, each bullet is a complete clause (not a telegraphic fragment).
- [ ] Every PR/commit cited maps to a Linear issue in *this* project — nothing pulled in from other projects, nothing fabricated to explain loose git activity.
- [ ] The one cross-cutting item is headline or bullet 2 — never last, never buried (Step 2.5).
- [ ] No point is stated twice — least of all the shared-infra one.
- [ ] At least one real impact/unlock anchor — and nothing invented.
- [ ] Every concrete item closes with its `(TICKET)` tag; PR links appear only on review-request bullets.
- [ ] Next separates in-flight from new.
- [ ] 2-3 bullets + one Next line — closer to 2 than 4.
- [ ] Any inferred "why" flagged for the user to confirm.
- [ ] Draft passed through humanizer (slop removed; em-dashes/→/fragments/emoji preserved).

## Delivery

Output the block in chat for the user to review and paste. **Never post to Slack (or anywhere) automatically.** Only if the user explicitly asks, create a Slack *draft* (a draft, not a send) so they review it in their client. Always list any assumptions made about the "why" as a short note under the draft.

## Example

**Raw work (input):**
- Started migrating the auth module to an adapter pattern
- Worked on the SSO config UI
- Fixed the cron timeouts

**Update (output):**
```
🛠️ Benjamin — 18/06
• Laid the shared auth adapter: one provider abstraction replacing the per-IdP branches, so multi-tenant SSO and future IdPs ride on a single path instead of new code each time (PROJ-211).
• SSO config UI wired onto the adapter — in review (PROJ-214).
• ⏭️ Next: finish the SSO UI. Then a new workstream — SCIM provisioning (PROJ-88).
```

Note the transform: the adapter (foundation) becomes the headline, the UI becomes proof it pays off, "fixed/worked on" become movement, each bullet is a complete clause closing on its ticket tag, and 3 raw tasks collapse to 2 bullets + Next. Compare against the three real posts up top — same shape.
