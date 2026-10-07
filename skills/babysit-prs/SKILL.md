---
name: babysit-prs
description: Drive every open PR to merge-ready without polling by hand. Follows the transitions pr-dash's shared scan service writes, through a persistent Monitor, and hands each PR that has bot feedback or a red check to its own subagent, which answers, folds and pushes on its own. Human reviews are counted, never touched. Use when asked to babysit, watch, or surveiller open PRs, or to keep them moving until they can merge.
argument-hint: "[--once] [--include-drafts] [PR…]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. There is no cadence here: the loop wakes on a
real change and sleeps otherwise.

With function hooks on (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`), `/babysit` does this manager's
work in code, from the same scan and the same agent prompt, with no manager in the conversation
(`/babysit dry` says what it would spawn). This skill is the manager where hooks do not run.

Two roles, and they never overlap. **You are the manager**: you own orchestration state, and no
thread body, diff, or reply draft ever enters this context. **A subagent
owns one PR**: it fetches its own problems, fixes them, answers them, and reports four numbers.

The split that makes it work: everything factual comes from one script, and everything requiring
judgment comes from an agent that never tells you how it judged.

## 1. Resolve the script

The scanner belongs to `pr-dash`, which runs without this skill; babysit-prs is one of its
readers. Resolve its path the same way `pr-feedback` resolves its own:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-dash/scripts/pr-scan.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-dash/scripts/pr-scan.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-dash/scripts/pr-scan.py"; do
  [ -n "$c" ] && [ -f "$c" ] && SCAN="$c" && break
done
python3 "$SCAN" $ARGS      # the user's PR numbers and --include-drafts, verbatim
```

One scan service per repo writes the state, whoever started it — the dashboard or you. This call
starts it if none runs, asks it for a pass now, waits for that pass (ten seconds at most — past
that the blob carries `stale` and the last state on disk), and prints your selection of it as one
JSON blob: every open PR of the author with `schema_version`, `merge_state`, `ci` rollup,
open/closed bot/human thread counts, `unresolved_bot`, `unresolved_human`, `held` (open bot threads that have not moved since an agent
last looked — our reply sits last, or the bot's does and an agent already read it; either way they
wait on the author, not on an agent), `humans`, `head`, `base`, `parent` (the open PR this one is
stacked on, `null` at the bottom of a stack), the last agent `report`, plus `needs_agent`,
`waits_on`, `merge_ready` and `status`. It is the **only** reader of GitHub truth in this skill — never
run `gh pr view`, `gh pr checks`, or a thread query yourself, and never ask an agent for a status
the script already carries. The service's query is aliased across PRs; only PRs above 100
review threads need extra paginated calls. Two readers produce contradictory status for checks
that changed minutes ago.

The blob opens with `state_dir` — the absolute path where mutes and agent reports live. Every path
you write into an agent's prompt must be that value expanded, never `$STATE_DIR`: a subagent has no
such variable, and a report written to a literal `$STATE_DIR/…` is a report you never receive.

Two flags shape the scan, and both come from the user, never from you:

- **`--include-drafts`** — by default drafts stay out of your selection (the service tracks them
  for the dashboard, never for you), so a draft never spawns an agent; marking one ready for review
  brings it in on the next pass. With the flag, drafts are babysat like any other PR: bots and CI already run on them,
  and clearing their findings before the PR goes out is the point.
- **PR numbers** (`123 456`) — a named PR **is** the selection. It is fetched as given, past the
  author filter and past the draft filter alike: name a colleague's PR and its agent will push
  to their branch. Nothing else is in the blob, and the service keeps fetching a named PR for as
  long as your watch runs.

Empty PR list? Say so and stop.

## 2. Use state; leave display to `pr-dash`

The JSON is orchestration input. Do not reproduce its PR table in chat. The author gets the current
view with `pr-dash status` or keeps it open with `pr-dash status --watch` (see the `pr-dash` skill);
that dashboard reads the same state and never folds reports, changes mutes, or starts agents. While
your watch runs, it adds what only you know — live agents, their notes, `WAITS` — and without you
it shows GitHub's word alone. Its `r` asks the service for a pass; the events of that pass reach
your watch like any other.
A stack is the one `gh stack` drew, the parent chain only where GitHub knows none: a stack opened
on top of another one's head is its own stack, with its own agent, and the dashboard draws each one
head first, base at the bottom.

An agent report is a snapshot; the scanner is the present. Use the scanner's live `held` count over
`report.held`. A `report.blocked` suppresses another agent; the scanner lifts it once the head
moves or a bot thread opens after the report, so a `report.blocked` still present is still true.

Out-of-band work is safe while `held` is non-zero because the scanner will not spawn an agent on
that PR. A stacked conflict belongs to the agent as a restack. A clean draft waits for the author.

Send a concise notification only for `merge_ready` or `held`; include the PR number and the action
the author owes — for `held`, `/pr-explain <n>`, which explains the thread in its own tab. On startup, report how many PRs are watched and mention `pr-dash status --watch`.

## 3. Spawn an agent, but only where one is needed

For each PR with `needs_agent: true`, **`waits_on: null`, `agent_running: false`** and no
`report.blocked` — meaning it has at least one unresolved **bot** thread, a failing check, or
`mergeable: "CONFLICTING"`, nothing below it in its stack is being rewritten right now, it does
not already have an agent, and no agent has called its current state blocked — mute it, then spawn its owner. Send them in a single message so they run
concurrently. A PR that is green, mergeable and free of bot threads gets no agent: its state is complete,
and an agent would have nothing to say that the script has not said.

`agent_running: true` is the mute file still on disk: an agent is alive on that PR and has not
reported. It keeps `needs_agent: true` the whole time it works — its threads only clear as it
answers them — so spawning on `needs_agent` alone puts a second agent on a branch the first is
about to force-push. Leave it. A live agent also outranks
bottom-first: it already holds the branch, so a lower PR waits its turn rather than preempting it.
A mute nothing has lifted within the hour is a dead agent, and the script drops it on its own.

`waits_on: <n>` is a stack holding its own line. **A stack gets one agent at a time, and it is
drained from the bottom** — run two and the child restacks against a base still moving, so its
rebase is either thrown away or lands and buries the parent's fix. The script picks the owner: the
PR of that stack whose agent is still alive, else the **lowest** one that needs one. Every other PR
of the stack reads `waits_on: <owner>` — including one *below* the owner, because a rebase anywhere
in a chain moves every branch above it. Spawn nothing for those PRs. The owner's
push moves `head`, the watch emits, the next PR up becomes the lowest that needs work, and it gets
its agent on that pass. A five-PR stack therefore takes five passes, in order, never five agents.

The mute file is what makes that hold, so **create it before the agent, not after**: it is the only
signal that an agent is still alive on a PR whose threads it has already answered but whose fix it
has not pushed. Skip it and the script sees a clean parent, releases the child, and both rewrite
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

**A reported agent is killed, never reused.** The moment a pass folds a report — the scan prints
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
  command: "python3 <absolute path of pr-scan.py> --follow <the same args>",
  description: "transitions on <n> open PRs",
  persistent: true,
  timeout_ms: 3600000,
})
```

Substitute the resolved absolute path — shell variables do not survive between Bash calls, so a `$SCAN` left in there arms a monitor that dies on its first poll.

**The watch takes the same arguments as the first pass** — the same PR numbers, the same
`--include-drafts`. Drop them and the watch follows a different selection: the drafts you asked for
go silent, and PRs you never selected start emitting.

`--follow` reads the service's event log and prints the lines of your selection: one per PR whose
CI rollup, unresolved-thread counts, `mergeStateStatus` or head sha actually moved — not one line
per check, which would be dozens per push and would get the monitor shut down as a firehose. Muted
PRs emit nothing. A dropped report is folded in and lifts its own mute — `TaskStop` its agent then,
in the same pass, before spawning anything. It also keeps the service alive, and restarts it if it
died.

The watch holds `<state_dir>/babysit.lock` for its lifetime. If startup reports `babysit-prs
already active`, another manager is babysitting this repo: leave it and stop — two managers would
spawn two agents on the same branch.

Then end the turn. Do not arm a `ScheduleWakeup`, do not poll, do not ask an agent whether it is
done: an agent going idle is not a signal, and its report file is. Today's silence is the design
working.

On each batch of events: run one pass (the §1 call), stop agents whose reports were folded, spawn any PR that now
needs an agent, notify only author actions or merge-ready PRs, and end the turn again.

`--once` means one pass, no monitor and no agents. Run the §1 call and reply with one line pointing
to `pr-dash status`.

## Stopping

`TaskStop` the monitor when every PR is merged or closed, or when the user says stop. Nothing else
stops the watch. The service outlives it: it keeps the dashboard current and exits on its own
half an hour after its last reader. Held items and unresolved conflicts stay visible in `pr-dash`; keep watching. A
dashboard where everything waits on a human costs no agent work while nothing changes.

## What lives where

| Concern | Skill |
|---|---|
| PR discovery, GitHub truth, the diff, the emit filter, mute, reports | `pr-scan.py` (the `pr-dash` skill) |
| Rebasing a conflicting branch onto its base | the PR's agent, directly |
| Fetching threads, verdicts, P1/P2/Nit, the dismissals registry | `pr-feedback`, inside the PR's agent |
| Code changes, replies, reactions, resolving threads | `pr-respond` |
| Finding the introducing commit, fold, force-push | `fixup` |
| Restacking children | `gh-stack` |
| Terminal dashboard | `pr-dash` |
| Spawning, the watch, stopping | here |
