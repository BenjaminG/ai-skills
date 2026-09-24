---
name: pr-dash
description: This skill should be used when the user wants to see their open PRs at a glance — a terminal dashboard of the current repo's open PRs (stacks, CI, merge state, bot and human threads) that stays current on its own, with or without babysit-prs. Triggers on "pr-dash", "show my PRs", "PR dashboard", "où en sont mes PR", or when asked why the dashboard is not updating.
---

# pr-dash

A dashboard of the current repo's open PRs. It needs no agent: a small scan service keeps its
state current, started by whoever needs it first.

## Open it

Resolve the script the way `pr-feedback` resolves its own, then run it from any checkout of the
repo (any worktree):

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-dash/scripts/pr-dash.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-dash/scripts/pr-dash.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-dash/scripts/pr-dash.py"; do
  [ -n "$c" ] && [ -f "$c" ] && DASH="$c" && break
done
python3 "$DASH" status            # one render
python3 "$DASH" status --watch    # live: redraws when the state moves; r rescans, q quits
```

`--drafts` also lists draft PRs. `--watch` needs an interactive terminal: tell the user to run it in
a pane of their own rather than running it through Bash. Inside Claude Code, `/prs` shows the same
state in a side pane.

## How it stays current

- `scripts/pr-scan.py --watch` is the service: one per repo, the only reader of GitHub and the only
  writer of `~/.claude/pr-state/<owner_repo>/state.json`. It passes every 60 s, or at once on
  `r`, and appends one line per transition to `events.log`.
- Every reader — `pr-dash`, `/prs`, `babysit-prs` — starts it when none runs and touches
  `reader.heartbeat`. Half an hour without a reader, it exits. Reopening shows the last state
  with its age while the first pass runs.
- It restarts itself when its script changes on disk, and a newer copy of the script replaces an
  older one's service.
- Status without babysit-prs is GitHub's word alone: `🤖 BOT n` (bot threads waiting), `🔨 FIX`
  (red check or conflict), `🙋 YOUR CALL`, `✅ READY`, `🧪 CI`, `👀 REVIEW`, `📝 DRAFT`. While
  babysit-prs follows the repo (it holds `babysit.lock`), the header says `babysit-prs on`, and
  its agents, notes and `WAITS` join the table.

## When it looks stale

Read the header: `updated HH:MM:SS (… ago)`. Then look in the state dir: `scan.log` holds the
service's lines and its `scan error: …`; `watch.lock` names the service's pid and script. Only
review threads count as threads — a bot's top-level PR comment is never counted.
