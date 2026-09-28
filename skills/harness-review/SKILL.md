---
name: harness-review
description: Turn one PR's review comments into harness fixes — classify each cause by the most solid place it can live (codebase, lint, rules, skill), then draft the fixes in a separate PR.
argument-hint: "[pr-number-or-url]"
disable-model-invocation: true
---

# Harness review

Every review comment is a correction someone had to write by hand. Fixing the PR answers it once;
fixing the **harness** (the code, lint, rules and skills the next agent works inside) answers it
for good. This skill reads one PR's review, finds the **cause** behind each comment, and places
each cause on the ladder in [`references/levels.md`](references/levels.md): 1 codebase, 2 static
analysis, 3 rules, 4 skill, with 0 (one-off) and 5 (nothing encodable) as verdicts.

Steps 1 to 4 read. Step 5 writes, and only what the user picked. Nothing is ever posted on the
source PR: its link lives in the harness PR's description.

Run from a checkout of the PR's repo: the coverage grep in step 3 searches it. Without one, ask for
its path.

## 1. Fetch

Resolve `pr-feedback`'s fetch script the way `pr-feedback` does, and run it with `--full` so no
comment body is cut:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-feedback/scripts/fetch-pr.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-feedback/scripts/fetch-pr.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-feedback/scripts/fetch-pr.py"; do
  [ -n "$c" ] && [ -f "$c" ] && FETCH="$c" && break
done
python3 "$FETCH" [pr-number-or-url] --full
```

The JSON holds `threads` (live), `settled_threads` (resolved or outdated), `reviews` and
`comments`. All four feed this skill: a resolved thread is usually the most instructive one, since
someone changed the code for it. `errors[]` names a source that failed; say which, and go on.

**Done when:** `#<n> — <url>` is stated and the JSON is in hand.

## 2. Keep the review items

An **item** is one reviewer's point: the head of a thread, one point in a review body, or one
conversation comment. Keep items written by:

- a human other than the PR author, including text an agent wrote and a human posted;
- a review bot (`cursor[bot]`, `naboo-ai-reviews[bot]`, or the repo's equivalent).

Replies inside a thread are context for its head item, not items. Drop:

- dependency, tracker and CI bots (snyk, linear, github-actions, renovate);
- a review body with no point of its own: empty, dismissed, a stale bot pass, or a summary in which a
  reviewer (bot or human) recaps their own inline threads. A body that recaps *and* adds a point keeps
  that point as `review#<i>.<k>`;
- anything the PR author wrote, replies to review bodies included.

Key each item by its position in the JSON, so the report can be checked against the PR, and
follow the key with the file and line (or `—`) so a human can find it:

- thread → `thread#<i> <file>:<line> @author` (`i` = index in `threads + settled_threads`, live
  first; `<file>` is the basename, `<line>` is `—` when GitHub gives none, as on outdated threads)
- review body → `review#<i> @author` (`i` = index in `reviews`); when two or more of its
  points are kept, `review#<i>.<k>` for the k-th kept point
- conversation comment → `comment#<i> @author` (`i` = index in `comments`)
- a thread head or comment with two or more kept points → `thread#<i>.<k>`, `comment#<i>.<k>`

Write `@author` as the JSON spells the login.

For each item, read the thread's replies (and `gh pr diff <n>` when they are silent) to learn
whether it changed the code. An item that changed nothing is still classified: a rejected claim is
usually level 0, but a reviewer who had to explain the codebase to the author may point at a
missing rule.

**Done when:** every item is kept or dropped with a reason, and kept + dropped equals the total.

## 3. Find the causes and place them

Read [`references/levels.md`](references/levels.md) in full, then:

1. Group the kept items into causes. Every kept item belongs to exactly one cause.
2. Walk the ladder top-down for each cause and stop at the first rung that holds. Name the rung
   above that failed and why, in one line.
3. For every cause at level 1 to 4, run the coverage grep over every surface `levels.md` lists,
   not only the chosen level's, and record the strongest match: `none`, `partial (file:line)` or
   `covered (file:line)`. When the case is covered at one level and partial at another, name both.
4. Name the concrete target: the file to create or edit, or the ticket to open for a level-1 change
   that spans many files.

**Done when:** every kept item maps to one cause, every cause has a level, and every level 1 to 4
cause has a coverage verdict and a target.

## 4. Report

Print the report in chat, level 1 to 4 rows first, sorted by level, then within a level `covered`,
`partial`, `none`: a rule that exists and does not fire is the loudest finding. Leave out an empty
`Verdicts` or `Dropped` section:

```md
# Harness review — PR #17603 — <title>

Items: 21 kept (humans 12 · bots 9) · 6 dropped · 7 causes

| #   | Cause                                                 | Items                                                          | Level | Coverage                                    | Target                                                          | Why                                                                                          |
| --- | ----------------------------------------------------- | -------------------------------------------------------------- | ----- | ------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| 1   | Resolve the tenant from the session, never from input | thread#0 x.resolver.ts:42 @alice, thread#5 y.resolver.ts:17 @cursor | 1     | covered (.claude/rules/backend/authz.md:12) | `assertClientAccess` helper required by the resolver base class | rule exists as prose, three resolvers still skip it; a required argument makes it unwritable |

## Verdicts

- 0 · Keep the cents conversion in the formatter — thread#2 z.ts:9 @bob — domain fact local to this file
- 5 · Rename the feature to match the product brief — review#2 @carol — product naming beyond the glossary

## Dropped

- comment#0 @snyk-io-eu[bot] — dependency bot
```

Then ask which rows to act on. Levels 0 and 5 are not actionable; they are listed so the user can
promote one they disagree with.

**Done when:** the report is printed and the user has named the rows (or none).

## 5. Draft the fixes

For the picked rows, and only those:

- **Level 1 that spans many files** → a Linear ticket (via the `linear` CLI), with the cause, the
  items as evidence, the target and the source PR link. Show the draft and create it after a yes.
- **Levels 1 (contained), 2, 3, 4** → one harness branch for the whole source PR:
  `wt switch --create harness/<pr-number>-<slug>` in the target repo. Write each fix there:
  - **2**: the rule, its test, and its registration, following the repo's lint-plugin docs
    (naboo: `packages/eslint-plugin-naboo/`, `docs/eslint-plugin-naboo.md`). Run the plugin's tests
    and the rule against the source PR's pre-fix code: it must go **red** on the flagged line.
  - **3**: the rule line in the file the enforcer loads, phrased as the repo phrases rules. Where
    `context-checker` reads it, lead with MUST or SHOULD and add a `Not:` clause that keeps it off
    correct code. For a `covered` cause, edit the existing line; never add a second one.
  - **4**: the step in the skill that owns the process. A skill in the `ai-skills` plugin gets its
    own branch in that repo, same naming.
- Show the diff. After a yes, open the PR with the target repo's PR skill (naboo:
  `create-pull-request`), title and body in English, the source PR linked in the description with
  one line per cause.

**Done when:** every picked row is a ticket, a line in the harness PR, or named as skipped with the
reason.
