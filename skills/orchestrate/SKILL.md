---
name: orchestrate
description: Run a dependency-ordered list of Linear tickets through Herdr. One tab, one worktree, one agent per layer, committed and checked before the next layer starts, PRs opened at the end. Use when asked to orchestrate, run, or dérouler a stack of tickets, or given a parent ticket whose sub-issues carry a build order.
argument-hint: "<parent-ticket | TICKET…>"
disable-model-invocation: true
---

# Orchestrate

Run one layer, then the next, until no layer is left. A layer is one Linear ticket, one branch,
one agent. You hold the graph and the Linear board. Each agent gets one ticket.

This needs Herdr. Before anything else:

```bash
test "${HERDR_ENV:-}" = 1
```

If that check fails, say you are not inside Herdr and stop.

The `linear-cli` skill documents the Linear commands and the `herdr` skill documents the Herdr
ones. Read them when a syntax is in doubt.

## Step 1. Resolve the graph

From a parent ticket, take its sub-issues. From a list of tickets, take the list. The order comes
from relations, not from the hierarchy:

```bash
linear issue relation list <TICKET>     # blocks / blocked by, per node
```

Each node becomes a layer with four values. Its ticket id, a short label, a branch name
(`feat/<TICKET>-<kebab-slug>`), and its base. The base is the branch of the layer that blocks it,
or `dev` for a node nothing blocks.

Print the resolved graph with the order, each branch and each base. Wait for the user's go. After
that one confirmation, run to the end without asking again.

## Step 2. Run the ready layers, two at a time

A layer is ready when every layer that blocks it is Done. Start ready layers until two are live,
and start another each time one of them finishes.

For each layer:

```bash
# 1. the board first. An unassigned Todo ticket with an agent working on it looks
#    exactly like an untouched one.
linear issue update <TICKET> --state "In Progress" --assignee self

# 2. a tab on the MAIN repo. `wt` does the moving, you do not.
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" \
  --label "<TICKET> <short label>" --no-focus

# 3. the worktree, from the pane. `wt` is a zsh function, so only an interactive
#    pane resolves it. `wt switch --create` copies the ignored files, node_modules
#    included, so the worktree needs no install.
herdr pane run <pane> "wt switch --create --base <base-branch> <branch>"

# 4. wait on a content marker, not on a shell prompt. Prompt regexes time out.
until herdr pane read <pane> --source detection --lines 10 2>/dev/null \
  | grep -q '<worktree-dir-name>'; do sleep 2; done

# 5. ccy is claude --dangerously-skip-permissions
#    cxy is codex --dangerously-bypass-approvals-and-sandbox
herdr agent start <ticket-slug> --kind claude --pane <pane> -- --dangerously-skip-permissions
```

Use `--kind codex -- --dangerously-bypass-approvals-and-sandbox` when the user asked for Codex on
this run.

Then give the agent its work. The prompt stays short, because the agent reads its own ticket:

```
Tu es la couche <n>/<N> d'une stack. Branche `<branch>`, basée sur `<base>`.
Lis le ticket : linear issue view <TICKET>

/implement <TICKET>

Commite sur la branche courante. Laisse le push et la PR à l'orchestrateur.
```

Send it with `herdr agent prompt <name> "<text>" --wait --timeout 3600000`.

## Step 3. Check the repository, not the agent

`/implement` runs its own tests and review and reports nothing a caller can read. `idle` and
`done` only mean the agent stopped. Read the repository instead:

```bash
git -C <worktree> log --oneline <base>..HEAD     # must list at least one commit
git -C <worktree> status --porcelain             # must print nothing
```

When both commands pass:

```bash
linear issue update <TICKET> --state "Done"
herdr tab close <tab>          # keep the worktree. A later layer may need to go back.
```

When either fails, leave the ticket In Progress, leave the tab and the agent running so the user
can read them, tell the user which layer stopped and what the two commands printed, and carry on
with the layers this one does not block. Layers above it stay unstarted.

## Step 4. Send every question to the user

`herdr agent get <name>` reports `blocked` when the agent hit a question its ticket did not
answer. Read the question with `herdr agent read <name> --source visible`, since a blocked agent
refuses a large `--lines`. Relay it to the user with the layer it came from, and keep the other
layers moving. The user answers, and you forward that answer with `herdr agent prompt`.

## Step 5. Open the stack

Once no layer is left, or whenever the user asks for it earlier, go through the layers from the
bottom up:

```bash
gh pr create --base <base-branch> --head <branch> --title "…" --body "…"
linear issue link <TICKET> <pr-url>
```

No layer moved during the run, so nothing needs a rebase and `gh stack` stays out of it. Stage
explicit paths if anything still needs committing from a worktree, because `git add .` there
stages 33 symlinked entries.

## Resuming

There is no state file. Linear and the branches are the state. Running the skill again on the
same parent resolves the graph again, reads each ticket's state, and restarts at the first ready
layer.

A ticket In Progress with no live agent is an orphan from a dead run. Compare the board against
`herdr agent list` in step 1 and name the orphans before asking for the go.
