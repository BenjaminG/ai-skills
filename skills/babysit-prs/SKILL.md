---
name: babysit-prs
description: Drive every open PR to merge-ready without polling by hand. Maintains shared dashboard state, watches GitHub for real transitions through a persistent Monitor, and hands each PR that has bot feedback or a red check to its own subagent, which answers, folds and pushes on its own. Human reviews are counted, never touched. Use when asked to babysit, watch, or surveiller open PRs, or to keep them moving until they can merge.
argument-hint: "[--once] [--include-drafts] [PR…]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. There is no cadence here: the loop wakes on a
real change and sleeps otherwise.

Two roles, and they never overlap. **You are the manager**: you own orchestration state, and no
thread body, diff, or reply draft ever enters this context. **A subagent
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
python3 "$SCAN" $ARGS      # the user's PR numbers and --include-drafts, verbatim
```

One pass, one JSON blob: every open PR of the author with `schema_version`, `merge_state`, `ci` rollup,
open/closed bot/human thread counts, `unresolved_bot`, `unresolved_human`, `held` (open bot threads that have not moved since an agent
last looked — our reply sits last, or the bot's does and an agent already read it; either way they
wait on the author, not on an agent), `humans`, `head`, `base`, `parent` (the open PR this one is
stacked on, `null` at the bottom of a stack), the last agent `report`, plus `needs_agent`,
`waits_on`, `merge_ready` and `status`. It is the **only** reader of GitHub truth in this skill — never
run `gh pr view`, `gh pr checks`, or a thread query yourself, and never ask an agent for a status
the script already carries. The initial query is aliased across PRs; only PRs above 100 review
threads need extra paginated calls. Two readers produce contradictory status for checks that
changed minutes ago.

The blob opens with `state_dir` — the absolute path where mutes and agent reports live. Every path
you write into an agent's prompt must be that value expanded, never `$STATE_DIR`: a subagent has no
such variable, and a report written to a literal `$STATE_DIR/…` is a report you never receive.

Two flags shape the scan, and both come from the user, never from you:

- **`--include-drafts`** — by default the scan filters drafts at the source, so a draft never
  enters the state and never spawns an agent; marking one ready for review brings it in on the next
  pass. With the flag, drafts are babysat like any other PR: bots and CI already run on them,
  and clearing their findings before the PR goes out is the point.
- **PR numbers** (`123 456`) — a named PR **is** the selection. It is fetched as given, past the
  author filter and past the draft filter alike: name a colleague's PR and its agent will push
  to their branch. Nothing else is scanned that pass.

Empty PR list? Say so and stop.

## 2. Use state; leave display to `pr-dash`

The JSON is orchestration input. Do not reproduce its PR table in chat. The author gets the current
view with `pr-dash status` or keeps it open with `pr-dash status --watch`; that dashboard reads the
state written by the scanner and never folds reports, changes mutes, or starts agents. Add
`--drafts` to also list the drafts the scan filtered out: the dashboard reads them from GitHub for
that one render and writes nothing, so they stay out of the state and no agent is spawned on them.
A stack is the one `gh stack` drew, the parent chain only where GitHub knows none: a stack opened
on top of another one's head is its own stack, with its own agent, and the dashboard draws each one
head first, base at the bottom.

An agent report is a snapshot; the scanner is the present. Use the scanner's live `held` count over
`report.held`. A `report.blocked` suppresses another agent only while the named failure or conflict
is unchanged; once that condition clears or the head moves, let the current scan decide again.

Out-of-band work is safe while `held` is non-zero because the scanner will not spawn an agent on
that PR. A stacked conflict belongs to the agent as a restack. A clean draft waits for the author.

Send a concise notification only for `merge_ready` or `held`; include the PR number and the action
the author owes. On startup, report how many PRs are watched and mention `pr-dash status --watch`.

## 3. Spawn an agent, but only where one is needed

For each PR with `needs_agent: true`, **`waits_on: null` and `agent_running: false`**, unless its
`report.blocked` still names the unchanged failure or conflict — meaning it has at least one
unresolved **bot** thread, a failing check, or `mergeable: "CONFLICTING"`, and nothing below it in
its stack is being rewritten right now, and it does not already have an agent — mute it, then spawn its owner. Send them in a single message so they run
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

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  name: "pr-<n>",
  description: "Own PR #<n>",
  prompt: "Think hard. You own PR #<n> end to end. **End to end ends at your push**, not at green CI.

    Invoke `pr-feedback` on PR #<n> with `--auto confirmed`, then take its handoff through
    `pr-respond` with the same policy — it drafts through `humanizer`, folds through `fixup`,
    force-pushes and resolves, all without asking you anything.

    **Bots, checks and merge state are yours.** A thread opened by a bot, a failing check, a
    branch behind its base: fix it, answer it, fold it through `fixup`, force-push, resolve the
    thread, restack children through `gh-stack`. Resolve rebase conflicts yourself. No
    confirmation needed — this is why you exist.

    **A conflicting branch is yours too, and it does not come through `pr-feedback`.** That skill
    holds a conflict as a merge decision because its handoff cannot rebase; here you own merge
    state, so take it: rebase onto `<base>` (this PR is stacked on **PR #<parent>**, so the rebase is
    a `gh-stack` restack, not a hand rebase — omit this clause when `parent` is null), resolve every
    conflict on its merits — never by taking one side wholesale — verify the branch still builds,
    then force-push with lease and count it in `pushed`. A conflict you cannot resolve without
    guessing the author's intent is `blocked`, with the file that stopped you as the gist.

    **Never wait, never watch.** Once your fix is on the remote you are done: do not arm a
    `Monitor`, do not sleep on a check, do not re-poll `gh pr checks` for the CI you just triggered,
    do not verify your own push landed green. A manager is already watching this PR and will see
    that rollup before you would. Waiting is not thoroughness here, it is damage: your mute holds
    your whole stack hostage while you idle, it ages out after an hour and hands your live branch to
    a second agent, and the verdict you were waiting for arrives in a context that is about to be
    thrown away. Push, report, stop — if the check comes back red, the next pass spawns a fresh
    agent that reads the real failure.

    **Human review threads are not yours.** Never reply to one, never resolve one, never change
    code because of one. The author handles those in a manual pass.

    **Threads already resolved are settled.** `fetch-pr.py` drops them; do not go around it to
    re-adjudicate them.

    **A thread you have already answered is not a new finding.** Bots answer back — accepting,
    conceding, sometimes arguing. `rounds >= 1` marks those threads: the item is the bot's **last**
    reply, never the claim at the top. An acknowledgement owes nothing — no reply, no resolve, and
    a question an earlier pass left with the author stays exactly where it is. A real rebuttal you
    answer on its own terms, without restating what you already wrote. Answering the head of a
    thread whose tail you did not read is the one failure that makes this loop look broken.

    **A claim you answered is a thread you close.** \"Real, but deliberate\", \"scoped on purpose\",
    \"refuted\", \"already covered by <test/doc>\" — those settle the claim: reply with the
    adjudication and its evidence, then **resolve**. Nothing is owed, so nothing is held; holding it
    would park the PR on `your-call` waiting for a decision nobody has to make.

    **When the remedy is a choice, not a fix**: a bot claim you confirmed whose fix means picking
    an architecture, or that contradicts a decision recorded in an ADR, `CLAUDE.md`, project
    memory, or the git history — reply in that bot's thread with your adjudication **and the question
    it leaves open**, **leave the thread open**, and count the item as held with a one-line gist. Do
    not decide for the author, and do not resolve the thread either: a resolved thread is one the
    author cannot find, and the dashboard only carries the gist. Your reply is the last word on it,
    which is what tells the scan this thread waits on a human and stops it spawning an agent here
    forever. Held is for a question, never for an explanation — if your reply ends the matter, resolve.

    **A check an earlier agent already tried to fix** means the obvious cause is not the cause. You
    will not see it fail twice yourself — you never wait for CI — so read the branch: a commit on
    `<head>` that already targets this exact check, or a thread where a previous pass says it fixed
    it, is your signal. Do not fix it a second time the same way. Either you find a different cause,
    or it is blocked, with that check as the gist.

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
  command: "python3 <absolute path of babysit-scan.py> --watch 60 <the same args>",
  description: "transitions on <n> open PRs",
  persistent: true,
  timeout_ms: 3600000,
})
```

Substitute the resolved absolute path — shell variables do not survive between Bash calls, so a `$SCAN` left in there arms a monitor that dies on its first poll.

**The watch takes the same arguments as the first pass** — the same PR numbers, the same
`--include-drafts`. Drop them and the watch surveys a different selection: the drafts you asked for
go silent, and PRs you never selected start emitting.

The script emits one line per PR whose CI rollup, unresolved-thread counts, `mergeStateStatus` or
head sha actually moved — not one line per check, which would be dozens per push and would get the
monitor shut down as a firehose. Muted PRs emit nothing. A dropped report is folded in and lifts
its own mute — `TaskStop` its agent then, in the same pass, before spawning anything.

The watch holds `<state_dir>/watch.lock` for its lifetime. If startup reports an active watcher,
keep that watcher and stop; retrying would create competing writers for the same state.

Then end the turn. Do not arm a `ScheduleWakeup`, do not poll, do not ask an agent whether it is
done: an agent going idle is not a signal, and its report file is. Today's silence is the design
working.

On each batch of events: run one pass, stop agents whose reports were folded, spawn any PR that now
needs an agent, notify only author actions or merge-ready PRs, and end the turn again.

`--once` means one pass, no monitor and no agents. Refresh the dashboard state and reply with one
line pointing to `pr-dash status`.

## Stopping

`TaskStop` the monitor when every PR is merged or closed, or when the user says stop. Nothing else
stops the watch. Held items and unresolved conflicts stay visible in `pr-dash`; keep watching. A
dashboard where everything waits on a human costs no agent work while nothing changes.

## What lives where

| Concern | Skill |
|---|---|
| PR discovery, GitHub truth, the diff, the emit filter, mute, reports | `babysit-scan.py` |
| Rebasing a conflicting branch onto its base | the PR's agent, directly |
| Fetching threads, verdicts, P1/P2/Nit, the dismissals registry | `pr-feedback`, inside the PR's agent |
| Code changes, replies, reactions, resolving threads | `pr-respond` |
| Finding the introducing commit, fold, force-push | `fixup` |
| Restacking children | `gh-stack` |
| Terminal dashboard | `pr-dash.py` |
| Spawning, the watch, stopping | here |
