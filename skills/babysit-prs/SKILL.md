---
name: babysit-prs
description: Drive every open PR to merge-ready without polling by hand. Follows the transitions the shared pr-dash Scan service writes, through a persistent Monitor, and hands each PR that has bot feedback or a red check to its own subagent, which answers, folds and pushes on its own. Human reviews are counted, never touched. Use when asked to babysit, watch, or surveiller open PRs, or to keep them moving until they can merge.
argument-hint: "[--once] [--include-drafts] [PR…]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. There is no cadence here: the loop wakes on a
real change and sleeps otherwise.

With function hooks on (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`), `/shepherd` does this manager's
work in code, from the same State and the same agent prompt, with no manager in the conversation
(`/shepherd dry` says what it would spawn). This skill is the manager where hooks do not run.

Two roles, and they never overlap. **You are the manager**: you own orchestration state, and no
thread body, diff, or reply draft ever enters this context. **A subagent
owns one PR**: it fetches its own problems, fixes them, answers them, and reports four numbers and the bot threads it left open.

The split that makes it work: everything factual comes from one State file, and everything requiring
judgment comes from an agent that never tells you how it judged.

## 1. Read the State

The scanner is `pr-dash`, a standalone CLI that runs without this skill; babysit-prs is one of its
Readers. If `command -v pr-dash` finds nothing, stop with one line: `npm i -g github:BenjaminG/pr-dash`.

```bash
pr-dash wake --wait                     # a fresh pass now; exits 1 if none lands within ~10 s
cat "$(pr-dash state-dir)state.json"    # the State that pass wrote, or the last good one
```

One Scan service per repo writes the State, whoever started it: the dashboard, `/prs` or you.
`wake --wait` starts it if none runs, asks it for a pass now and waits for that pass. A wait that
times out still leaves the last State on disk; read it. `state.json` is
`{schema_version: 4, taken_at, repo, error, prs: [row…]}`, every open PR of the author, drafts
included. Each row carries `draft`, `merge_state`, `ci` rollup, open/closed bot/human thread
counts, `unresolved_bot`, `unresolved_human`, `held` (open bot threads that have not moved since an
agent last looked: our reply sits last, or the bot's does and an agent already read it; either way
they wait on the author, not on an agent), `humans`, `head`, `base`, `parent` (the open PR this one
is stacked on, `null` at the bottom of a stack), `stack_members`, the last agent `report`, plus
`needs_agent`, `waits_on`, `agent_running`, `merge_ready` and `status`. A non-null `error` means the
last pass failed and the rows are the last good ones: say its `message` once and carry on. A
`schema_version` other than 4 means this skill and `pr-dash` disagree: say so and stop. The State is
the **only** reader of GitHub truth in this skill. Never run `gh pr view`, `gh pr checks`, or a
thread query yourself, and never ask an agent for a status the State already carries. Two readers
produce contradictory status for checks that changed minutes ago.

`pr-dash state-dir` prints the absolute directory where the State, mutes, agent reports and
`babysit.lock` live; `<state_dir>` below is that path without its trailing `/`. Every path you
write into an agent's prompt must be that value expanded, never
`$STATE_DIR`: a subagent has no such variable, and a report written to a literal `$STATE_DIR/…` is a
report you never receive.

The selection is yours to cut from the rows, from the user's arguments, never from your own idea:

- **No PR numbers**: every row except the drafts.
- **`--include-drafts`**: drafts are babysat like any other PR. Bots and CI already run on them,
  and clearing their findings before the PR goes out is the point. Without it a draft never spawns
  an agent; marking one ready for review brings it in on the next pass.
- **PR numbers** (`123 456`): those rows **are** the selection, drafts among them. A named PR that
  is not in the State (not open, or not the author's) is reported in one line and skipped:
  following someone else's PR is out of scope.

Empty selection? Say so and stop.

## 2. Use state; leave display to `pr-dash`

The State is orchestration input. Do not reproduce its PR table in chat. The author keeps the
dashboard open with `pr-dash` (no arguments, or `npx github:BenjaminG/pr-dash`); it reads the same
State and never folds reports, changes mutes, or starts agents. While your agents run, it shows
what only they add (live agents, their reports, who waits on whom) and without you it shows
GitHub's word alone. The events of a pass it asks for reach your watch like any other.
A stack is the one `gh stack` drew, the parent chain only where GitHub knows none: a stack opened
on top of another one's head is its own stack, with its own agent, and the dashboard draws each one
head first, base at the bottom.

An agent report is a snapshot; the State is the present. Use the row's live `held` count over
`report.held`. A `report.blocked` suppresses another agent; the Scan service lifts it once the head
moves or a bot thread opens after the report, so a `report.blocked` still present is still true.

Out-of-band work is safe while `held` is non-zero because no agent is spawned on that PR. A stacked conflict belongs to the agent as a restack. A clean draft waits for the author.

Send a concise notification only for `merge_ready` or `held`; include the PR number and the action
the author owes — for `held`, `/pr-explain <n>`, which explains the thread in its own tab. On startup, report how many PRs are watched and mention the `pr-dash` dashboard.

## 3. Spawn an agent, but only where one is needed

For each PR with `needs_agent: true`, **`waits_on: null`, `agent_running: false`** and no
`report.blocked` — meaning it has at least one unresolved **bot** thread, a failing check, or
`mergeable: "CONFLICTING"`, nothing below it in its stack is being rewritten right now, it does
not already have an agent, and no agent has called its current state blocked — mute it, then spawn its owner. Send them in a single message so they run
concurrently. A PR that is green, mergeable and free of bot threads gets no agent: its state is complete,
and an agent would have nothing to say that the State has not said.

`agent_running: true` is the mute file still on disk: an agent is alive on that PR and has not
reported. It keeps `needs_agent: true` the whole time it works — its threads only clear as it
answers them — so spawning on `needs_agent` alone puts a second agent on a branch the first is
about to force-push. Leave it. A live agent also outranks
bottom-first: it already holds the branch, so a lower PR waits its turn rather than preempting it.
A mute nothing has lifted within the hour is a dead agent, and the Scan service drops it on its own.

`waits_on: <n>` is a stack holding its own line. **A stack gets one agent at a time, and it is
drained from the bottom** — run two and the child restacks against a base still moving, so its
rebase is either thrown away or lands and buries the parent's fix. The Scan service picks the owner: the
PR of that stack whose agent is still alive, else the **lowest** one that needs one. Every other PR
of the stack reads `waits_on: <owner>` — including one *below* the owner, because a rebase anywhere
in a chain moves every branch above it. Spawn nothing for those PRs. The owner's
push moves `head`, the watch emits, the next PR up becomes the lowest that needs work, and it gets
its agent on that pass. A five-PR stack therefore takes five passes, in order, never five agents.

The mute file is what makes that hold, so **create it before the agent, not after**: it is the only
signal that an agent is still alive on a PR whose threads it has already answered but whose fix it
has not pushed. Skip it and the Scan service sees a clean parent, releases the child, and both rewrite
the same branch.

```bash
touch "<state_dir>/<n>.muted"    # its own pushes must not wake you, and its stack stays reserved
```

Then spawn its owner, the prompt read from `references/agent-prompt.md` and filled from that PR's
row as the file says:

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  name: "pr-<n>",
  description: "Own PR #<n>",
  prompt: "<references/agent-prompt.md, filled>",
})
```

An agent that finishes writes its report and dies. Its memory is not lost: refutations live in the
dismissals registry (see `pr-feedback` §2), so the next agent on that PR does not re-argue them.

**A reported agent is killed, never reused.** The moment a pass folds a report — the watch prints
`#<n> report: …` — `TaskStop` that PR's agent (`ToolSearch "select:TaskStop"`) before acting again.
Never `SendMessage` it back to work: its context is a snapshot of a branch that has since moved, and
a revived agent goes around the mute entirely. Every pass spawns a **fresh** agent that redoes its
own `pr-feedback` triage on the current state.

Killing it is also what keeps the name honest: `pr-<n>` is one agent per PR, so **a name collision
means an agent is still alive on that PR** — leave that PR alone. Never accept a suffixed name
(`pr-<n>b`): that suffix is a second agent about to force-push the branch the first one holds.

At the very first pass — the only moment every PR needs triage at once — spawn in waves of about
four. After that the regime is quiet: one agent at a time, usually none.

## 4. Arm the watch, then stop working

```
Monitor({
  command: "<absolute path of scripts/watch.sh> <the same PR numbers>",
  description: "transitions on <n> open PRs",
  persistent: true,
  timeout_ms: 3600000,
})
```

`scripts/watch.sh` sits next to this file; substitute its absolute path. Shell variables do not
survive between Bash calls, so a variable left in there arms a monitor that dies on its first poll.

**The watch takes the same PR numbers as the selection**, and no `--include-drafts`: that flag is
yours to apply when you read the State. Without the numbers the watch emits for PRs you never
selected.

`watch.sh` runs `pr-dash follow`, which tails the service's `events.log` from now and prints the
lines of those PRs (a line naming no PR always passes): one per PR whose CI rollup,
unresolved-thread counts, `mergeStateStatus` or head sha actually moved, not one line per check,
which would be dozens per push and would get the monitor shut down as a firehose. Muted PRs emit
nothing. A dropped report is folded in and lifts its own mute; its line reads `#<n> report: …`.
`TaskStop` its agent then, in the same pass, before spawning anything. The follower also keeps the
service alive, and restarts it if it died. A draft you did not select may still emit; the pass
that line sets off finds nothing to do for it.

`watch.sh` holds `<state_dir>/babysit.lock` for its lifetime (a pid file; a lock whose process is
gone is taken over). If it prints `babysit-prs already active`, another manager is babysitting this
repo: leave it and stop. Two managers would spawn two agents on the same branch.

Then end the turn. Do not arm a `ScheduleWakeup`, do not poll, do not ask an agent whether it is
done: an agent going idle is not a signal, and its report file is. Today's silence is the design
working.

On each batch of events: run one pass (§1: `wake --wait`, read the State, cut the selection), stop
agents whose reports were folded, spawn any PR that now needs an agent, notify only author actions
or merge-ready PRs, and end the turn again.

`--once` means one pass, no monitor and no agents: `pr-dash wake --wait`, read the State, and reply
with one line (how many selected PRs need an agent, are held, are merge-ready) pointing to the
`pr-dash` dashboard.

## Stopping

`TaskStop` the monitor when every PR is merged or closed, or when the user says stop. Nothing else
stops the watch. The service outlives it: it keeps the dashboard current and exits on its own
half an hour after its last reader. Held items and unresolved conflicts stay visible in `pr-dash`; keep watching. A
dashboard where everything waits on a human costs no agent work while nothing changes.

Stop babysit before upgrading ai-skills or `pr-dash`, or in-flight mutes and reports are lost. The
old `~/.claude/pr-state/` directory is abandoned as is.

## What lives where

| Concern | Skill |
|---|---|
| PR discovery, GitHub truth, the event log, folding mutes and reports | `pr-dash` (the State in `pr-dash state-dir`) |
| The one-manager lock | `scripts/watch.sh` |
| Rebasing a conflicting branch onto its base | the PR's agent, directly |
| Fetching threads, verdicts, P1/P2/Nit, the dismissals registry | `pr-feedback`, inside the PR's agent |
| Code changes, replies, reactions, resolving threads | `pr-respond` |
| Finding the introducing commit, fold, force-push | `fixup` |
| Restacking children | `gh-stack` |
| Terminal dashboard | `pr-dash` (no arguments) |
| Spawning, the watch, stopping | here |
