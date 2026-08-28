---
name: babysit-prs
description: Drive every open PR to merge-ready without polling by hand. Holds a matrix of the author's open PRs, watches GitHub for real transitions through a persistent Monitor, and hands each PR that has bot feedback or a red check to its own subagent, which answers, folds and pushes on its own. Human reviews are counted, never touched. Use when asked to babysit, watch, or surveiller open PRs, or to keep them moving until they can merge.
argument-hint: "[--once]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. There is no cadence here: the loop wakes on a
real change and sleeps otherwise.

Two roles, and they never overlap. **You are the manager**: you hold the matrix, you own every
objective column, and no thread body, diff, or reply draft ever enters this context. **A subagent
owns one PR**: it fetches its own problems, fixes them, answers them, and reports four numbers.

The split that makes it work: everything factual comes from one script, and everything requiring
judgment comes from an agent that never tells you how it judged.

## 1. Resolve the script

It ships with the plugin; resolve its path the same way `pr-feedback` resolves its own:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/babysit-prs/scripts/babysit-scan.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/babysit-prs/scripts/babysit-scan.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/babysit-prs/scripts/babysit-scan.py"; do
  [ -n "$c" ] && [ -f "$c" ] && SCAN="$c" && break
done
python3 "$SCAN"
```

One pass, one JSON blob: every open PR of the author with `merge_state`, `ci` rollup,
`unresolved_bot`, `unresolved_human`, `humans`, `head`, `base`, the last agent `report`, plus
`needs_agent` and `merge_ready`. It is the **only** reader of GitHub truth in this skill — never
run `gh pr view`, `gh pr checks`, or a thread query yourself, and never ask an agent for a status
the script already carries. Two readers is how a matrix ends up showing a check that went red
minutes ago.

The blob opens with `state_dir` — the absolute path where mutes and agent reports live. Every path
you write into an agent's prompt must be that value expanded, never `$STATE_DIR`: a subagent has no
such variable, and a report written to a literal `$STATE_DIR/…` is a report you never receive.

Drafts are out of scope: the scan filters them at the source, so a draft never fills a row
and never spawns an agent. Marking one ready for review brings it into the matrix on the next
pass.

Empty PR list? Say so and stop.

## 2. Fill the matrix

One row per PR. The objective columns come from the script, the last three from the PR's agent:

| PR | Issue | Mergeable | CI | Threads | Fixed | Held | Blocked |
|---|---|---|---|---|---|---|---|
| `[#num title](url)` | `[<KEY> title](https://linear.app/issue/<KEY>)`, `—` if the branch carries no key | `merge_state` | `ci` | `<bot> bot`, `<human> humain (<login>)` | `report.pushed` | `report.held`, then `— <report.held_gist>` when there is one | `report.blocked` or `—` |

Take the Linear key from the branch name and the title from `linear-cli` once per PR, then reuse
it — it does not change between events.

Nothing else goes in the table, and nothing goes under it. The `held_gist` is the whole substance
you get: its thread is resolved, so the matrix is where the author learns a decision is waiting.
One line, no expansion under the table.

A PR reported `merge_ready` earns a `PushNotification` (`ToolSearch "select:PushNotification"`)
and leaves the matrix. The merge itself is yours.

## 3. Spawn an agent, but only where one is needed

For each PR with `needs_agent: true` — meaning it has at least one unresolved **bot** thread or a
failing check — mute it, then spawn its owner. Send them in a single message so they run
concurrently. A PR that is green with no bot thread gets no agent: its row is already complete,
and an agent would have nothing to say that the script has not said.

```bash
touch "<state_dir>/<n>.muted"    # its own pushes must not wake you
```

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  name: "pr-<n>",
  description: "Own PR #<n>",
  prompt: "Think hard. You own PR #<n> end to end.

    Invoke `pr-feedback` on PR #<n> with `--auto confirmed`, then take its handoff through
    `pr-respond` with the same policy — it drafts through `humanizer`, folds through `fixup`,
    force-pushes and resolves, all without asking you anything.

    **Bots, checks and merge state are yours.** A thread opened by a bot, a failing check, a
    branch behind its base: fix it, answer it, fold it through `fixup`, force-push, resolve the
    thread, restack children through `gh-stack`. Resolve rebase conflicts yourself. No
    confirmation needed — this is why you exist.

    **Human review threads are not yours.** Never reply to one, never resolve one, never change
    code because of one. The author handles those in a manual pass.

    **Threads already resolved are settled.** `fetch-pr.py` drops them; do not go around it to
    re-adjudicate them.

    **When the remedy is a choice, not a fix**: a bot claim you confirmed whose fix means picking
    an architecture, or that contradicts a decision recorded in an ADR, `CLAUDE.md`, project
    memory, or the git history — reply in that bot's thread with your adjudication, **resolve the
    thread**, and count the item as held with a one-line gist. Do not decide for the author, and do
    not park the decision in a thread nobody reads: a bot never answers, and an open bot thread
    keeps this PR spawning an agent forever. The author reads held items in the matrix.

    **The same check failing twice after you fixed it** means your fix missed the cause. Stop
    touching it, count it as blocked.

    Finally — always, including when you fixed nothing or hit a blocker — write
    <state_dir>/<n>.report.json (the absolute path, substituted here by the manager):

      {\"pushed\": <fixes on the remote>, \"inflight\": <started, not pushed>,
       \"held\": <items left for the author>, \"held_gist\": \"<one gist or null>\",
       \"blocked\": \"<one gist or null>\"}

    That file is your only report; nothing else you say reaches the manager. Write it, then stop."
})
```

An agent that finishes writes its report and dies. Its memory is not lost: refutations live in the
dismissals registry (see `pr-feedback` §2), so the next agent on that PR does not re-argue them.

At the very first pass — the only moment every PR needs triage at once — spawn in waves of about
four. After that the regime is quiet: one agent at a time, usually none.

## 4. Arm the watch, then stop working

```
Monitor({
  command: "python3 <absolute path of babysit-scan.py> --watch 60",
  description: "transitions on <n> open PRs",
  persistent: true,
  timeout_ms: 3600000,
})
```

Substitute the resolved absolute path — shell variables do not survive between Bash calls, so a `$SCAN` left in there arms a monitor that dies on its first poll.

The script emits one line per PR whose CI rollup, unresolved-thread counts, `mergeStateStatus` or
head sha actually moved — not one line per check, which would be dozens per push and would get the
monitor shut down as a firehose. Muted PRs emit nothing. A dropped report is folded in and lifts
its own mute.

Then end the turn. Do not arm a `ScheduleWakeup`, do not poll, do not ask an agent whether it is
done: an agent going idle is not a signal, and its report file is. Today's silence is the design
working.

On each batch of events: re-render the matrix, spawn an agent for any PR that now needs one, and
end the turn again.

`--once` means one pass, one matrix, no monitor and no agents.

## Stopping

`TaskStop` the monitor when every PR is merged or closed, or when the user says stop. Nothing else
stops the watch — a held item and a rebase conflict both mean report it in the matrix and keep
watching, and a matrix where everything waits on a human is the cheapest state there is: no
events, no tokens, no ticks.

## What lives where

| Concern | Skill |
|---|---|
| PR discovery, GitHub truth, the diff, the emit filter, mute, reports | `babysit-scan.py` |
| Fetching threads, verdicts, P1/P2/Nit, the dismissals registry | `pr-feedback`, inside the PR's agent |
| Code changes, replies, reactions, resolving threads | `pr-respond` |
| Finding the introducing commit, fold, force-push | `fixup` |
| Restacking children | `gh-stack` |
| The matrix, spawning, the watch, stopping | here |
