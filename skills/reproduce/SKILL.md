---
name: reproduce
description: Reproduces a bug from its ticket in the local app, on code that does not fix it, and keeps the captures, the steps and a replayable start state; a second run on the fixed branch checks the symptom is gone. This skill should be used when asked to reproduce a bug or see it locally ("reproduis ce bug", "voir le bug en local"), or to check a fix against its reproduction.
argument-hint: "<ISSUE-ID or URL>"
---

# Reproduce

A **reproduction** is a bug's symptom observed in the local app on code that does not fix it, with
the captures, the steps and the start state that show it. This skill observes; finding the cause is
`investigate`'s job.

Everything for one ticket lives in `DIR=~/.cache/reproduce/<owner>-<repo>/<ISSUE-ID>/`. When
`DIR/steps.md` already exists, this run is a **replay**: go to §6 after §2.

## 1. Ticket

Read the issue: Linear `get_issue` and `list_comments`, else `acli jira workitem view <ID>`. Read
its screenshots and the bug report it links. Create `DIR` and write `DIR/plan.md`:

- **Symptom**: what the user sees, with the ticket's real values.
- **Expected**: what they should see instead.
- **Start state**: the records the ticket names (ids) and the conditions the symptom needs
  (statuses, dates, flags, roles).
- **Actions**: the persona and its account, the screen, the steps to the symptom. For a symptom in
  an API answer (an email sent, a mutation that fails), the call that triggers it.
- **Proof**: `ui` (captures), `api` (the call's answer), or `out of reach` when only a scheduled job
  or a third party can trigger it.

Show the plan and go on. Ask the user only when the ticket does not say what the user sees. `out of
reach` goes straight to §5 with the verdict **not reproducible locally** and the reason.

**Done when** every field of `plan.md` holds a value from the ticket.

## 2. Environment

The ticket's worktree is the one whose branch names the ticket ID (`git worktree list`, any case),
else Linear's `gitBranchName`, created with `wt switch --create <branch>` from the default branch
(worktrunk skill). A replay runs there. A first run runs there too, unless that worktree already
holds a fix (commits beyond the default branch, or uncommitted changes): then it runs on the main
worktree (`git worktree list | head -1`) at the default branch, the code that does not fix it.
Locate pr-demo, whose setup this skill shares:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-demo}" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-demo 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-demo"; do
  [ -n "$c" ] && [ -f "$c/SKILL.md" ] && echo "$c" && break
done
```

Use the printed path as `$DEMO` literally. Read `$DEMO/SKILL.md` and run its sections **Local-app
doc** and **Environment** for this branch; `$SKILL` in those sections is `$DEMO`. Note the herdr
panes this run creates.

**Done when** pr-demo's two criteria hold.

## 3. Start state

Take the first tier that holds the start state of `plan.md`, using the local-app doc's **data**
section (shell, backups, known traps):

1. **Exact**: the ticket's own records, from the local clone.
2. **Look-alike**: a record of the clone that meets every condition of the start state.
3. **Shaped**: a recent record set to the start state by `reset`.

Write `DIR/reset` and `DIR/restore` as pr-demo's **Data** section does: `reset` saves every
document it touches to `DIR/backup/` (derived collections included, as the data section lists them)
and applies the doc's local trap fixes; `restore` writes the backup back. Run `reset`. Note the tier
in `plan.md`, with why each tier above it failed.

**Done when** the start state reads back from the database.

## 4. Observe

- **ui**: sign in as the ticket's persona with `signin.sh <persona> <the ticket user's email>`, as
  the doc's **auth** section says; when that account cannot sign in, use the doc's default persona
  and note it. Reach the screen with the screen map, play the actions in the Playwright MCP browser,
  and save `browser_take_screenshot` captures to `DIR/captures/`: the start state, then the
  symptom. Read `browser_console_messages` and `browser_network_requests` for errors on the way.
- **api**: keep `signin.sh`'s cookies in a shell variable, call the API at the URL of the doc's
  **launch** section with `curl`, and save the answer to `DIR/captures/`.

Write `DIR/steps.md`: the persona, the URL, each action (role and accessible name, never CSS) or the
call, and what each capture shows.

The verdict is **reproduced** when a capture shows the symptom of `plan.md`. Symptom absent: run
`DIR/restore`, then §3 with the next tier. After the third tier, the verdict is **not reproduced**,
with what differs between here and the ticket: the clone's date against the ticket's (newest `_id`
of the collection), the ticket's records changed since (`updatedAt`), and the commits of the
default branch since the ticket that touch the files it names (`git log --since`), one of which may
already fix it. The start state stays the one `plan.md` describes.

**Done when** the verdict is written in `plan.md` and every capture is named in `steps.md`.

## 5. Report

1. `DIR/restore`, then `cleanup.sh`, `browser_close`, and stop the server panes this run created.
2. In the terminal: the verdict, the tier and the persona used, the captures' paths, the steps, and
   for **not reproduced** what differs.
3. Offer a comment on the ticket in the ticket's language: the verdict, the steps, the captures
   uploaded through the tracker's file upload. Draft it through the `humanizer` skill, show it, and
   post it once the user confirms. The ticket's state stays as it is.

**Done when** the data is restored, the panes this run created are gone, and the report is out.

## 6. Replay

Run `DIR/reset`, play `DIR/steps.md` on the current branch, and save the captures as
`DIR/captures/after-*`. The verdict is **symptom gone** when the expected behaviour of `plan.md`
shows, else **still there**. Then §5; the ticket comment puts the first captures and the `after-*`
ones side by side.

**Done when** the verdict is written in `plan.md` and every `after-*` capture is named in
`steps.md`.
