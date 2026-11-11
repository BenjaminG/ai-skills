---
name: elevate
description: This skill should be used when the user wants the highest-leverage technical or architectural changes for their project, ranked from what breaks in production (recurring bugs, incidents, slow paths, frictions reported in Slack, Linear or Datadog) and from the code itself, ending on one recommended change written as a project brief. The technical counterpart to `innovate`. Triggers on "elevate", "biggest tech wins", "what keeps breaking", "tech audit", "improvement opportunities", or "what should we re-architect". Accepts an optional focus (e.g., "feedback-loop", "dx", "build speed", "observability", "invoicing") and a window (`--since 30d`, default 90 days).
argument-hint: "[focus area] [--since <days>d]"
---

# Elevate

Answer: **which change to this project would remove the most pain, starting from what actually
hurts?** Pain is read first from production and from the team, then traced into the code. The
answer is a ranked list of **levers**, one recommended lever, and a project brief for it.

Leading words used throughout:

- **Symptom**: something a user or the team saw go wrong, in their words, with a link.
- **Ledger**: the table of symptoms gathered from every source.
- **Cluster**: symptoms that share one cause in the code.
- **Causal chain**: one sentence, "X runs in Y, so Z", that ties a cluster to the code.
- **Lever**: what to change to break a causal chain. Moving work elsewhere is one family of levers
  among five.

## 1. Scope

Read CLAUDE.md, README, key config (package.json, tsconfig, build configs, CI workflows). Set the
focus (none: every dimension) and the window (default 90 days).

**Done when** the focus, the window and the included dimensions are written at the top of the run.

## 2. Build the ledger

The host repo's `docs/agents/signals.md` says where symptoms are reported (Datadog services, Slack
channels by role, Linear teams and labels, PostHog, the git fix convention) and through which tool
each answered. Read it in the main worktree (`git worktree list | head -1`) when the current one
lacks it. When it is missing, ask the user: set it up now (read
`$SKILL/../setup-ai-skills/SKILL.md`, run it for `signals`, then come back here), or run on git
alone with every other source `unavailable`.

Dispatch one read-only subagent per source the doc marks proven, in parallel. Give each
[`references/ledger.md`](references/ledger.md), its section of `signals.md`, the window and the
focus. Each returns ledger rows only; the main context holds the ledger, never the raw messages.

A source that contradicts `signals.md` (retention shorter than the window, a channel renamed, a
monitor routed to another channel, an alias to merge) gets fixed in the doc, in the copy read
above, in this same run, and named in the final report.

**Done when** every source is `checked` or `unavailable (<reason>)`, and every row carries a link.

## 3. Cluster

Group rows by the work behind them, not by message or by channel. A cluster is **recurring** when
two independent sources report it, or when it shows up three times or more across two weeks or
more. Rows that fit no cluster go to an **isolated bugs** list, shown at the end and never ranked.

**Done when** each cluster has a name, its cost to users in their own words, and its count of rows
per source.

## 4. Trace the causal chain

Trace the five recurring clusters with the most rows, one read-only subagent per cluster, in
parallel. List the other recurring clusters as `not traced`; they are not ranked. For each traced
cluster, read the code path behind it and answer:

1. Which rule is guaranteed nowhere (no type, no constraint, no test)?
2. Where does this work run, and what does it share there (process, pool, database, queue)?
3. When does it run: inside the user's request, or after?
4. What happens when it is retried?

**Done when** each traced cluster has a `file:line` and a causal chain in one sentence.

## 5. Generate levers

For each traced cluster, write at least three levers from
[`references/levers.md`](references/levers.md), from at least two families. One of them is always
the lightest lever that would stop the cluster from coming back. Each lever names the link of the
causal chain it breaks.

Then run the **proactive lane**: candidates no symptom asks for, across architecture, libraries,
build and tooling, DX and infrastructure (stale deps, slow builds, awkward patterns, TODOs, recent
git friction). A proactive candidate caps at Confidence Med.

With a focus, keep only clusters and candidates that match it, even when an off-focus one looks
stronger.

**Done when** each traced cluster has three or more levers across two or more families, each
tied to its causal chain.

## 6. Check each lever

- **Rules.** Read `docs/agents/domain.md` when it exists for where the ADRs and the glossary live;
  else check `docs/adr/`, `adr/`, `docs/architecture/decisions/` and `.claude/rules/`. A lever that
  contradicts an ADR stays in the matrix, flagged **ADR-blocked**, and sinks to the bottom.
- **Current work.** Search the issue tracker (`docs/agents/issue-tracker.md` says which and how)
  for active projects and issues on the same cluster. Active work that covers the lever removes it;
  an uncovered remainder may stay.
- **Prior attempts.** Search this project's Claude/Codex history with `devsql` (the
  `devsql-querying` skill has the tables) and git commits, with two keywords or more per lever,
  scoped to the current project. Read the matching prompts and commits before classifying: a
  keyword hit is not proof. Tag the lever:
  - **`shipped`**: matching commits, not reverted. Drop the lever.
  - **`reverted-recent`** (under 3 months): Confidence Low; Notes cite the revert SHA and its likely
    reason.
  - **`reverted-stale`** (6 months or more): keep the Confidence; Notes ask the user whether the
    blocker still applies. A failure that old may be viable today.
  - **`struggled`**: many prompts, no commit. Confidence Low; Notes cite the day.
  - **`deferred`**: discussed, never attempted. Notes give the rationale.
  - **`none`**: score normally.

  Without `devsql` or history rows, print `Prior-attempt history: unavailable` above the matrix.
- **Assumptions.** List the 1 to 3 assumptions each lever's Impact and Effort rest on:
  - `[verified]`: evident from code, config or a ledger row already read; cite it.
  - `[probe:feasibility]`: whether the lever works on this codebase. Failure kills the lever.
  - `[probe:impact]`: the size of the gain.
  - `[unverifiable]`: needs data this run cannot reach.

  Each probe comes with a command or measurement under 10 minutes and the signal that confirms it.
  A feasibility probe is listed first. The user decides whether to run probes.

**Done when** every surviving lever has a prior-attempt tag, its assumptions classified, and each
probe its command.

## 7. Score and rank

| Axis | Scale | Meaning |
|---|---|---|
| **Impact** | S / M / L / XL | Pain removed, as a user-observable outcome: the cluster's incidents, the cohort it touches, how often it comes back, wallclock or contributor time saved. A structural proxy alone (files touched, lines deleted, graph edges) caps Confidence at Low. |
| **Effort** | S / M / L / XL | Until the change is trusted in production: implementation, validation, rollout. A small diff over a wide surface is not S. |
| **Risk** | Low / Med / High | Blast radius and reversibility. |
| **Confidence** | Low / Med / High | Strength of the evidence behind Impact and Effort. An unverified probe behind an L/XL Impact or an S Effort forces Low. |

Favor high Impact, low Effort, low Risk, high Confidence. ADR-blocked levers sink to the bottom.
Keep the 5 to 10 strongest; fewer when the evidence supports fewer. Pick **one winner** and say in
2 to 4 sentences why it beats the next two. A recommendation may differ from row 1 only for a
timing, dependency or validation reason, stated.

**Done when** every row points to its cluster or is marked `proactive`, and one winner is named.

## 8. Write the brief

For the winner, write a project brief as [`references/brief.md`](references/brief.md) shapes it.

**Done when** the brief stands alone: a reader who did not see the run understands the pain, the
change, the rollout, and how to switch it off.

Then ask which the user wants: publish the brief (as `docs/agents/issue-tracker.md` says to create a
project), expand another row, or run a pending probe. Publish nothing before the answer.

## Out of scope

- **Isolated bugs**: listed, never ranked. A bug family that recurs is a cluster, and in scope.
- **Code cleanup** (dead code, renames, file splits): `simplify` and `code-slop`.
- **Product capabilities**: `innovate`.
- **Rewrites** ("rewrite in Rust", "move to microservices") only when a recurring cluster's causal
  chain demands it; prefer reversible levers rolled out one slice at a time.

## Output

```
# Elevate · <focus or "full audit"> · <window>

Signal coverage: <source> checked (<rows>) · <source> unavailable (<reason>) · …
ADRs consulted: <files, or "none found">

## Ledger
| Cluster | Users see | Sources | Rows | Since |
Isolated bugs: <count>, listed at the end

## Ranking matrix
| # | Lever | Family | Cluster | Impact | Effort | Risk | Confidence | Prior | Probes | Notes |

## Recommendation
<the winner, and why it beats #2 and #3>

## Levers
### 1. <lever>
**Symptoms:** <cluster, rows, links>
**Causal chain:** <X runs in Y, so Z> (`file:line`)
**Change:** <what to do>
**Impact:** <user-observable outcome>
**Risk:** <what could break; how to switch it off>
**Assumptions & probes:** <[verified] / [probe:feasibility] / [probe:impact] / [unverifiable]>
**Cheapest kill-switch:** <the fastest test that invalidates it> (top 3 only)

## Brief: <winner>

## Isolated bugs and untraced clusters
```

`Prior`: `none / reverted-recent / reverted-stale / struggled / deferred`. `Probes`: `ok` when
every assumption is verified, else `<N> pending (<M> feasibility)`.
