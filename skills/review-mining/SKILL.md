---
name: review-mining
description: Mine human review comments from merged PRs into recurring themes and propose where each rule should live (lefthook/Danger, CLAUDE.md, gate-wf reviewer). Report only, no edits.
argument-hint: "[owner/repo] [--since 30d] [--limit 300] [--min 3]"
disable-model-invocation: true
---

# Review mining

Human reviewers on merged PRs are the only cheap record of what the team catches and the bots miss, and of the conventions no `CLAUDE.md` states. This skill turns that record into a ranked list of rule proposals.

**The deliverable is the report.** Applying a rule is a separate PR, in a separate session. Every step here reads.

Arguments: the first bare token matching `owner/repo` is the target repo, otherwise the current checkout. `--since` (default `30d`) sets the merge window, `--limit` (default 300) caps the PRs pulled, `--min` (default 3) sets the recurrence threshold. Walk the tokens; each flag takes the next token as its value. `--min` is the skill's own, not the script's.

**Coverage needs a local checkout of the target repo.** Without one, Step 3 can still route a theme but cannot tell you whether a rule for it already exists, which is the most useful column in the report. Ask for the path, or say the column is `n/a` and why.

## Step 1 — Fetch

The script ships with the plugin; resolve its path the way `pr-feedback` resolves its own (plugin-root env, then newest plugin cache, then global skills), then run it:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/review-mining/scripts/mine-reviews.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/review-mining/scripts/mine-reviews.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/review-mining/scripts/mine-reviews.py"; do
  [ -n "$c" ] && [ -f "$c" ] && MINE="$c" && break
done
python3 "$MINE" [owner/repo] --since 30d --limit 300
```

`--limit` caps how many merged PRs the window may yield, so a busy repo cannot blow up the corpus. When the script reports `prs` equal to the limit, the window was cut short: say which dates were actually covered, since that is the window the report describes.

The script selects merged PRs by date, then pulls review threads and review bodies, keeps only what a **human other than the PR author** wrote first, and writes the corpus to `~/.claude/review-mining-state/<owner>_<repo>/raw-<date>.json`. It prints a summary; echo `prs`, `window`, `comments`, `agent_shaped` and `humans_seen` to the user.

Two numbers in that summary decide whether the run is worth continuing.

- `humans_seen` must hold only people. A bot login there means `BOT_LOGINS` in the script is stale and the corpus is polluted. Say so and stop.
- `agent_shaped` counts comments an agent wrote and a human pasted under their own login. Mining those would feed the loop its own output. When they outnumber the rest, say what fraction of the corpus survives before spending a classification pass on it.

**Done when:** the summary is printed, `errors` is empty, and `humans_seen` holds only people.

## Step 2 — Classify

Read the corpus file. Above roughly 150k characters, split it by the top-level directory of `path` and hand each part to a subagent with this step's instructions.

**Pass A — keep the corrections.** A **correction** asks for the code to be different, in a person's own words.

Drop every record flagged `agent_shaped`. Then drop what the flag missed, **but only among bodies over roughly 200 characters**: a severity header, a confidence line, a cluster id, a rule-file citation, a table of findings, prose citing several `path:line` anchors. Those are this repo's own reviewers talking, and promoting them to a rule would close the loop on itself.

Below that length the tells mean nothing. `nit:`, `**major:**` and `minor: violates code-style.md` are how people write a one-liner, and the loop risk lives in the long essays. Keep short comments. Report the missed group as its own number, separate from the script's flag.

Then drop the noise: praise, a question the thread answers with an explanation and no code change, a typo, a remark about the PR description or the ticket, a reviewer narrating their own process. A bare ` ```suggestion ` block is a correction; read its rule from what the block replaces.

**Pass B — cluster into themes.** A **theme** is one imperative sentence a reviewer would put in a style guide: "guard nullable Prisma results before use", "no business logic in controllers". Assign every correction to exactly one theme, and open a new theme rather than stretch an existing one.

If a prior report sits in the state directory, read its table first and **reuse its theme names** wherever the meaning matches. Renaming a theme breaks the delta in Step 4.

Count **distinct PRs** per theme, never comments: three nits on one PR are one occurrence. At or above `--min`, the theme is **recurring**; below, it is **one-shot** and appears as a count only.

Sort each recurring theme **objective** or **subjective** by the residual test: could a regex, an ESLint rule, or a ten-line lefthook/Danger check decide this from the diff alone, with no reading of intent? Yes, objective. Needs judgement about design, naming meaning, or scope, subjective.

**Done when:** flagged plus missed plus corrections plus noise equals the corpus comment count, the sum is reported, and every theme carries a distinct-PR count.

## Step 3 — Route

Each recurring theme gets one destination, one draft, evidence, and a coverage verdict.

| Bucket | Destination | Draft |
|---|---|---|
| already `covered` and still recurring | wherever the enforcer looks, or a higher tier | no new rule. Either move the existing line into the file the agent loads, or raise the tier of the reviewer rule that already fires and gets ignored. Say which, and quote the line you are moving. |
| objective | a lefthook or lint rule in the target repo; a Danger rule only if it already has a `Dangerfile` | 5 to 10 lines, warning by default. Failing the build takes evidence that the team treats it as a blocker. |
| subjective, applies to any diff | a line in the `CLAUDE.md` the agent actually loads | `MUST …` when the repo already phrases the rule absolutely ("forbidden", "banned", "never"), else `SHOULD …` |
| subjective, one domain | a rule row in one `agents/<x>-reviewer.md` of this repo | the three edits: the `rule_id` in the enum, the "what to look for" row, the tier row |

Which reviewer owns a domain: bugs and parity go to `bug-reviewer`, layering, boundaries and coupling to `solid-reviewer`, dead and speculative code to `ponytail-reviewer`, extraction and duplication to `simplify-reviewer`, comment noise and defensive junk to `slop-reviewer`. A theme that is really an ADR violation goes to the ADR, not to a reviewer.

`agents/context-checker.md` maps a **MUST** to BLOCKER and a **SHOULD** to MAJOR, and it reads only a `CLAUDE.md` or an ADR. A rule sitting in a rules directory the enforcer never opens is the most common cause of a covered-and-recurring theme, so name the file the agent loads: follow the repo's `AGENTS.md` or `CLAUDE.md` pointer rather than assuming the root.

Picking the modal verb needs evidence the corpus does not hold. GitHub's resolved flag is true on almost every thread and says nothing about whether code changed, so it cannot carry an 80% test. Read the repo's own wording instead: absolute phrasing earns MUST, everything else SHOULD. Upgrading past that needs the script to record whether a commit followed the thread, which it does not yet do.

**Coverage** is grep, not judgement. Take two or three keywords from the theme and search `agents/*.md` here, plus in the target checkout: every `CLAUDE.md` and `AGENTS.md` including per-package ones, `.claude/rules/`, `.cursor/*.md` (a `BUGBOT.md` is often the richest checklist in a repo), `adr/`, `lefthook.yml`, `Dangerfile*`, `.eslintrc*` and `**/oxlint.config.*`. Report `none`, `partial (file:line)`, `covered (file:line)`, or `n/a` with no local checkout, and list which paths were missing. **A covered theme that still recurs is the headline finding**: the rule exists and is not firing. Lead the report with it and say what stops it firing.

**Evidence** is two or three citations per theme, `PR #412 · src/x.ts:42 · @alice: "…"`, quotes under 120 characters, preferring threads that ended in a code change.

**Done when:** every recurring theme has a destination, a draft, at least two citations, and a coverage verdict.

## Step 4 — Report

Write `~/.claude/review-mining-state/<owner>_<repo>/<date>.md` and print it:

```md
# Review mining — owner/repo — 2026-09-04
143 merged PRs (2026-08-05 → 2026-09-04) · 538 comments by humans · 190 agent-shaped flagged · 148 more by the same tells · 122 corrections · 78 noise
Sum: 190 + 148 + 122 + 78 = 538
212 human replies inside bot threads (not analyzed — that measures bot precision, not team convention)
Recurring themes: 7 (objective 3 · subjective 4) · one-shot: 41

| # | Theme | PRs | Bucket | Destination | Coverage | Δ prev |
|---|-------|-----|--------|-------------|----------|--------|
| 1 | Guard nullable Prisma results | 9 | subjective | CLAUDE.md MUST | none | new |
| 2 | Migration without a down() | 4 | objective | lefthook warn | partial agents/migration-reviewer.md:31 | 6 → 4 |

## 1. Guard nullable Prisma results — 9 PRs, 4 reviewers
**Rule draft:** MUST null-check `findUnique` / `findFirst` results before dereferencing.
**Why here:** 8 of 9 threads ended in a code change, so reviewers block on it — MUST, which context-checker raises as a BLOCKER.
**Evidence:**
- PR #412 · src/booking.ts:42 · @alice: "this can be null when the cart expired" · resolved by commit
- PR #398 · src/quote.ts:88 · @bob: "same null case as last week" · resolved by commit
```

Close the file with the near-misses one PR below `--min`, a count of the one-shots, what was left out and why, and the coverage paths that were missing. The file holds the report and nothing else; observations about the skill itself go in the chat reply.

On a first run, every `Δ prev` is `new` and there is no delta line. When a prior report exists, match themes by lowercased name and fill `Δ prev` with `new`, `gone`, or `n → m`, then add one line: "Since last audit: N gone, M new." A theme that went `gone` after its destination was applied is the loop closing. Name it.

**Done when:** the file is written and the table is in chat.
