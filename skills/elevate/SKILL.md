---
name: elevate
description: This skill should be used when the user wants the highest-leverage technical or architectural changes for their project, ranked from what breaks in production (recurring bugs, incidents, slow paths, frictions reported in Slack, Linear or Datadog) and from the code itself, ending on two recommended changes, a quick win and a structural bet, each written as a project brief. The technical counterpart to `innovate`. Triggers on "elevate", "biggest tech wins", "what keeps breaking", "tech audit", "improvement opportunities", or "what should we re-architect". Accepts an optional focus (e.g., "feedback-loop", "dx", "build speed", "observability", "invoicing") and a window (`--since 30d`, default 90 days). `--until <date>` replays the run as of a past date, to test whether elevate would have proposed a change the team later made.
argument-hint: "[focus area] [--since <days>d] [--until <YYYY-MM-DD>]"
---

# Elevate

Answer: **which change to this project would remove the most pain, starting from what actually
hurts?** Pain is read first from production and from the team, then traced into the code. The
answer is a ranked list of **levers** and two winners, each with a project brief: a **quick win**
that stops one cluster, and a **structural bet** that removes what several clusters share.

Leading words used throughout:

- **Symptom**: something a user or the team saw go wrong, in their words, with a link.
- **Ledger**: the table of symptoms gathered from every source.
- **Cluster**: symptoms that share one cause in the code.
- **Causal chain**: one sentence, "X runs in Y, so Z", that ties a cluster to the code.
- **Meta-cluster**: an absence several clusters share (no single owner, no single place that
  decides, no boundary between two domains).
- **Lever**: what to change to break a causal chain. Moving work elsewhere is one family of levers
  among five.

## 1. Scope

Read CLAUDE.md, README, key config (package.json, tsconfig, build configs, CI workflows). Set the
focus (none: every dimension) and the window (default 90 days, ending today).

With `--until <date>`, the run is a **replay**: the window ends at that date, and the run sees only
what existed before it.

- **Code.** Take the last commit of the default branch before the date
  (`git rev-list -1 --before=<date> origin/<default>`). When the current checkout is not at it, add
  a detached worktree there and read every file from it, ADRs and rules included.
- **Cutoff.** Anything dated after the date is not evidence: a message, an issue, a project, a
  commit, an ADR, a session. Filter by date in the query when the source allows it; otherwise drop
  the item on reading and count it. Sources whose data from before the date has expired (log
  retention) are `unavailable (retention)`; their metrics and monitor history may still answer.

**Done when** the focus, the window and the included dimensions are written at the top of the run,
and, in a replay, `Replay until <date> at <sha>`.

## 2. Build the ledger

The host repo's `docs/agents/signals.md` says where symptoms are reported (Datadog services, Slack
channels by role, Linear teams and labels, PostHog, the git fix convention) and through which tool
each answered. Read it in the main worktree (`git worktree list | head -1`) when the current one
lacks it. When it is missing, ask the user: set it up now (read
`$SKILL/../setup-ai-skills/SKILL.md`, run it for `signals`, then come back here), or run on git
alone with every other source `unavailable`.

When the doc has no `priority` section, ask the user once which Slack channels and Linear teams or
projects to search first (or none), and write the answer in the doc.

Dispatch one read-only subagent per source the doc marks proven, in parallel. Give each
[`references/ledger.md`](references/ledger.md), its section of `signals.md`, the `priority`
section, the window (its end date in a replay) and the focus. Each returns ledger rows only; the main context holds the
ledger, never the raw messages.

A source that contradicts `signals.md` (retention shorter than the window, a channel renamed, a
monitor routed to another channel, an alias to merge) gets fixed in the doc, in the copy read
above, in this same run, and named in the final report.

**Done when** every source is `checked` or `unavailable (<reason>)`, every row carries a link, and
in a replay each source names how many items after the cutoff it dropped.

## 3. Cluster

Group rows by the work behind them, not by message or by channel. A cluster is **recurring** when
two independent sources report it, or when it shows up three times or more across two weeks or
more. Rows that fit no cluster go to an **isolated bugs** list, shown at the end and never ranked.

**Done when** each cluster has a name, its cost to users in their own words, and its count of rows
per source.

## 4. Trace the causal chain

Trace five recurring clusters, one read-only subagent per cluster, in parallel: first the clusters
holding a `priority` row, then those with the most rows. List the other recurring clusters as
`not traced`; they are not ranked. For each traced cluster, read the code path behind it and
answer:

1. Which rule is guaranteed nowhere (no type, no constraint, no test)?
2. Where does this work run, and what does it share there (process, pool, database, queue)?
3. When does it run: inside the user's request, or after?
4. What happens when it is retried?
5. How often did the failing link fire in production over the window? Count it where it shows: a
   log line or metric in the source `signals.md` names, rows in the database or a local clone.

A chain whose failing link was not counted is `unconfirmed`, and its levers cap at Confidence Low.

**Done when** each traced cluster has a `file:line`, a causal chain in one sentence, and the count
of its failing link or `unconfirmed`.

## 5. Look across clusters, then diverge

**Synthesis.** Lay the traced chains side by side with the names of the untraced recurring
clusters. Name every absence two or more of them share: no single owner, no single place that
decides, no boundary between two domains, one primitive modelled several ways, one decision made in
many files. Count it in the code (files, call sites, copies of the rule). Each shared absence is a
**meta-cluster**; its pain is the union of its clusters' rows. An untraced cluster that joins a
meta-cluster gets traced now, as in step 4.

**Divergence.** Dispatch one read-only subagent per lens, in parallel. Give each the meta-clusters,
the three largest traced clusters, their chains, and the code. Each returns 3 to 5 candidate
changes, each with the probability, estimated, that a typical team would propose it:

- **Name the concept**: what event or object is missing from the code's language?
- **Draw the boundary**: what should one owner hold, behind one entry point?
- **Change the runtime**: where should this work run instead?
- **Borrow a pattern**: where was a problem of this shape solved, and under what name? Cite the
  source.
- **Delete**: what if this path or feature did not exist?

Each lens keeps at least one candidate under 20 %. Then one more subagent, given each candidate's
one-line change but not its rationale, merges the duplicates.

**Done when** each meta-cluster has its count in the code, and every lens returned candidates,
duplicates merged.

## 6. Generate levers

For each traced cluster, write at least three levers from
[`references/levers.md`](references/levers.md), from at least two families. One of them is always
the lightest lever that would stop the cluster from coming back. Each lever names the link of the
causal chain it breaks. Detecting the cluster breaks no link: **Make it observable** is the measure
in another lever's rollout, and a lever of its own only when the chain is a detection failure
(alert noise, a failure nobody sees).

Then run the **proactive lane**: candidates no symptom asks for, across architecture, libraries,
build and tooling, DX and infrastructure (stale deps, slow builds, awkward patterns, TODOs, recent
git friction). A proactive candidate caps at Confidence Med.

With a focus, keep only clusters and candidates that match it, even when an off-focus one looks
stronger.

Step 5's candidates become levers too. Each names the meta-cluster or chain it breaks; its family
is its lens when no family of `levers.md` fits.

**Done when** each traced cluster has three or more levers across two or more families, each
tied to its causal chain, and each meta-cluster has at least one lever.

## 7. Check each lever

- **Rules.** Read `docs/agents/domain.md` when it exists for where the ADRs and the glossary live;
  else check `docs/adr/`, `adr/`, `docs/architecture/decisions/` and `.claude/rules/`. A lever that
  contradicts an ADR or an architecture doc stays ranked on its own merit, tagged **revisits
  <doc>**, with the evidence that the doc's context has changed since it was written, or
  `context unchanged` when none was found.
- **Current work.** Search the issue tracker (`docs/agents/issue-tracker.md` says which and how)
  for active projects and issues on the same cluster. Active work that covers the lever removes it;
  an uncovered remainder may stay. A structural lever is not removed by active work that covers only
part of it: that work becomes its first slice, named in Notes. In a replay, active means created before the cutoff and not
  finished before it.
- **Prior attempts.** Search this project's Claude/Codex history with `devsql` (the
  `devsql-querying` skill has the tables) and git commits, with two keywords or more per lever,
  scoped to the current project, before the cutoff in a replay. Read the matching prompts and
  commits before classifying: a keyword hit is not proof. Tag the lever:
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
  A feasibility probe is listed first. Step 8 runs the kill-switches of the top 3.

**Done when** every surviving lever has a prior-attempt tag, its assumptions classified, and each
probe its command.

## 8. Score and rank

| Axis | Scale | Meaning |
|---|---|---|
| **Impact** | S / M / L / XL | Pain removed, as a user-observable outcome: the cluster's incidents, the cohort it touches, how often it comes back, wallclock or contributor time saved. A structural proxy alone (files touched, lines deleted, graph edges) caps Confidence at Low, except for a structural bet whose Impact is counted across clusters. |
| **Effort** | S / M / L / XL | Until the change is trusted in production: implementation, validation, rollout. A small diff over a wide surface is not S. |
| **Risk** | Low / Med / High | Blast radius and reversibility. |
| **Confidence** | Low / Med / High | Strength of the evidence behind Impact and Effort. An unverified probe behind an L/XL Impact or an S Effort forces Low. |

Favor high Impact, low Effort, low Risk, high Confidence. Keep the 5 to 10 strongest; fewer when the evidence supports fewer.

Run the cheapest kill-switch of the top 3 yourself, read-only: a log query, the code, a local clone
of the database. A lever whose kill-switch fires drops out and the next one moves up. Ask the user
only for a probe that writes, costs money, or needs access this run lacks.

Pick two winners and say for each, in 2 to 4 sentences, why it beats the next two of its kind:

- **Quick win**: the strongest lever by the rule above. It may differ from row 1 only for a timing,
  dependency or validation reason, stated.
- **Structural bet**: the strongest lever that comes from a meta-cluster, from Change when or Change
  where, or from the concept, boundary or pattern lenses. Its test is a replay over the window's
  rows, run read-only instead of a 10-minute kill-switch: of the N rows of its clusters, how many
  would the change have prevented, or located at once? A spike that writes or runs longer is listed
  as a probe for the user.

**Done when** every row points to its cluster or meta-cluster or is marked `proactive`, the top 3
kill-switches have run, the bet's replay has run, and both winners are named.

## 9. Write the briefs

For each winner, write a project brief as [`references/brief.md`](references/brief.md) shapes it.

**Done when** each brief stands alone: a reader who did not see the run understands the pain, the
change, the rollout, and how to switch it off.

In a replay, stop here: publish nothing and run no new probe. Otherwise ask which the user wants: publish a brief (as `docs/agents/issue-tracker.md` says to create a
project), expand another row, or run a pending probe. Publish nothing before the answer.

## Out of scope

- **Isolated bugs**: listed, never ranked. A bug family that recurs is a cluster, and in scope.
- **Code cleanup** (dead code, renames, file splits): `simplify` and `code-slop`.
- **Product capabilities**: `innovate`.
- **Rewrites** ("rewrite in Rust", "move to microservices") only when a recurring cluster's causal
  chain or a meta-cluster demands it; prefer reversible levers rolled out one slice at a time.

## Output

```
# Elevate · <focus or "full audit"> · <window>
<in a replay: Replay until <date> at <sha> · items after the cutoff dropped: <n per source>>

Signal coverage: <source> checked (<rows>) · <source> unavailable (<reason>) · …
ADRs consulted: <files, or "none found">

## Ledger
| Cluster | Users see | Sources | Rows | Since |
Meta-clusters: <absence · clusters it joins · count in the code>
Isolated bugs: <count>, listed at the end

## Ranking matrix
| # | Lever | Family | Cluster | Impact | Effort | Risk | Confidence | Prior | Probes | Notes |

## Recommendation
**Quick win:** <lever, and why it beats the next two>
**Structural bet:** <lever, why it beats the next two, and its replay result>

## Levers
### 1. <lever>
**Symptoms:** <cluster, rows, links>
**Causal chain:** <X runs in Y, so Z> (`file:line`)
**Change:** <what to do>
**Impact:** <user-observable outcome>
**Risk:** <what could break; how to switch it off>
**Assumptions & probes:** <[verified] / [probe:feasibility] / [probe:impact] / [unverifiable]>
**Cheapest kill-switch:** <the fastest test that invalidates it, and its result> (top 3 only)

## Brief: <quick win>
## Brief: <structural bet>

## Isolated bugs and untraced clusters
```

`Prior`: `none / reverted-recent / reverted-stale / struggled / deferred`. `Probes`: `ok` when
every assumption is verified, else `<N> pending (<M> feasibility)`.
