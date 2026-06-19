---
name: build-in-public
description: This skill should be used when the user wants to write their end-of-day / evening "build-in-public" update for a given Linear project — 3-4 impact-focused bullets plus a Next line synthesized from the project's Linear activity and the repo's git/PR shipping evidence, ready to paste into the pod thread. Invoke as /build-in-public with a Linear project ID. Triggers on "build-in-public post", "evening update", "what did I ship today", "end-of-day update", or any variant of "what did I do today" for a work update — even without the word "skill". Default to drafting; never post anywhere automatically.
argument-hint: "<linear-project-id>"
allowed-tools: Bash(linear:*), Bash(git:*), Bash(gh:*), Bash(devsql:*), Bash(date:*), Bash(jq:*), AskUserQuestion
---

# Build in public

Turn a day's raw work into a short, high-signal evening update that reads as *impact and direction*, not activity. The reader is the pod: they already share the spec and the standup, so the update can be terse and ride on that context. It is NOT a demo and NOT a status report — its currency is **progress + decisions + what got unblocked**, which is exactly what foundation/groundwork days produce.

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
5. **Links beat descriptions.** Every concrete item carries its PR (`#1234`) or issue (`BOF-430`) link. A link the reader can open > a sentence describing it.
6. **Split the Next line by grain.** Separate in-flight continuations from new big items. Don't flatten a multi-day new workstream to the same level as "finish the thing I'm already on".
7. **A heads-down day is a legitimate report.** If there's no shippable or visual output, say so honestly and give position + ETA ("Deep in the X schema, no visible output yet, first cut tomorrow"). When git+Linear are thin, the devsql session titles/topics are what tell you *where* you got to and what's next. This sets expectations and kills the "what are they doing?" question. Never pad to look busy.
8. **Stay terse.** 3-4 bullets + one Next line, max. It rides on shared pod context; it does not need to be self-contained like a demo.

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
- **emoji and markdown links** — `🛠️`, `⏭️`, `#1234`, `BOF-430` all stay.

So: keep the shape, remove the tells. If humanizer is unavailable, ship the draft as-is — it's a polish pass, not a gate.

## Output format

ALWAYS produce exactly this shape, as a fenced markdown block ready to paste:

```
🛠️ <name> — <date>
- <foundation or highest-impact item, with link and what it unlocks>
- <consumer / feature item, with link and status>
- <other item or honest heads-down line, with link/ETA>
- ⏭️ Next: <in-flight continuation>. Then <new item, with link>; + <smaller item, with link>.
```

Use `$(date +%d/%m)` for the date. Keep bullets to one line each where possible. Use the user's real ticket/PR links in markdown form.

## Gate before delivering

This is not a decorative checklist — it is a gate. Before emitting, run every item. **If any item fails, rewrite the post and re-run the whole list. Emit nothing until all pass.**

- [ ] No "started / began / worked on" — every line states movement or position.
- [ ] The one cross-cutting item is headline or bullet 2 — never last, never buried (Step 2.5).
- [ ] No point is stated twice — least of all the shared-infra one.
- [ ] At least one real impact/unlock anchor — and nothing invented.
- [ ] Every concrete item links its PR/issue.
- [ ] Next separates in-flight from new.
- [ ] 4 bullets or fewer + one Next line.
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
🛠️ Alex — 18/06
- Laid the shared auth adapter: single provider abstraction replacing the per-IdP branches → unblocks multi-tenant SSO + future IdPs. PR WIP #211.
- SSO config UI wired onto the adapter (#214, in review).
- Root-caused the cron timeouts: connection pool, not the query. Fix merged (#209).
- ⏭️ Next: finish the SSO UI. Then new workstream — SCIM provisioning (PROJ-88).
```

Note the transform: the adapter (foundation) becomes the headline, the UI becomes proof it pays off, "fixed/worked on" become movement, and every line links out. No visual was needed for any of it.
