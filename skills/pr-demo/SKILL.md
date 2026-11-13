---
name: pr-demo
description: Records a short demo video of a pull request's feature in the local app through Playwright MCP, then attaches it to the PR description. This skill should be used when asked for a demo video of a PR or feature ("vidéo de démo", "parcours le flow… donne-moi la vidéo"), to re-record or update the video on a PR, or to attach a video to a PR.
argument-hint: "[PR]"
---

# PR demo

A **demo** is a short video of the feature on the local app, from the state before the change to
its visible result, that a reviewer watches in the PR description. It is **tight**: page loads and
logins are cut, server waits last about a second, the cursor is a red dot the eye can follow. A
flow runs about 15 s per scenario, 30 s at most for a single one; past 60 s, propose splitting
the demo before filming. Title cards (in English, like the PR) go in only when a video chains
several scenarios.

Everything for one PR lives in its **demo directory**, `DIR=~/.cache/pr-demo/<owner>-<repo>/<PR>/`:
`record.js`, `reset`, `restore`, `backup/`, `markers.json`, `demo.mp4`, `demo.prev.mp4`,
`sheet.png`. A second run on the same PR is a **re-take**: it reuses what is there.

## 1. Resolve

Take the PR from `$ARGUMENTS`, else the current branch's PR:
`gh pr view [<n>] --json number,url,headRefName,headRepositoryOwner,body,baseRefName`.
Create `DIR`. Locate the edit script:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-demo}" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-demo 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-demo"; do
  [ -n "$c" ] && [ -f "$c/scripts/edit.py" ] && echo "$c" && break
done
```

Shell variables do not survive between Bash calls: use the printed path as `$SKILL` literally.

**Done when** the PR number, its branch, `DIR` and `$SKILL` are known, and you know whether this is
a re-take (`DIR/record.js` exists).

## 2. Local-app doc

The host repo's `docs/agents/local-app.md` and its scripts say how to prepare, launch, check, sign in
to and seed the local app. Read it in the PR's worktree when it is committed there, else in the main
worktree (`git worktree list | head -1`), which holds the reference copy; run its scripts from the
PR's worktree. When it is missing, or has no `signin.sh`, read `$SKILL/../setup-ai-skills/SKILL.md`,
run it, then come back here.

A trap the doc does not cover (a missing build step, a bad record, a flag) gets fixed in the doc or
its script, in the copy read above, once the fix is proven, in this same run, and named in the final
report.

**Done when** the doc is read.

## 3. Environment

1. **Worktree**: the PR branch's worktree (`git worktree list`). None → `wt switch <branch>`
   (worktrunk skill), then install dependencies.
2. **Prepare**: `docs/agents/local-app/prepare.sh`.
3. **Servers**: for each line of `launch.sh --list`, check the port
   (`lsof -nP -iTCP:<port> -sTCP:LISTEN -t`, then `lsof -a -p <pid> -d cwd -Fn`).
   - Nothing listening → run `launch.sh <name>` in its own pane of the herdr tab "dev server"
     (herdr skill), from the worktree, and wait for its ready text with its timeout. A miss means
     reading the pane, not waiting longer.
   - Listening from another worktree → ask before stopping it; the user may be using it.

**Done when** `doctor.sh` prints no `FAIL` and each server runs from the PR's worktree.

## 4. Scenario

Read the PR's "How can it be tested?" section, the ticket it links and that ticket's mockups (a
design file, an artifact), then the diff. When nothing on screen moves (a new label, status or
layout), screenshots tell it better: propose `pr-shots` and stop if the user takes it.

Write one scenario per state the diff renders (each value of a status or kind the screen shows), each
as a start state, the actions, and the final visible result — the thing the PR changes on screen. A
screen the change adds that the mockups lack, or shows differently, is a finding for the report.
Show the plan (one line per scenario) only when there are several scenarios or the flow is
ambiguous; otherwise go on. A re-take starts from `DIR/record.js` and adapts it to the new diff.

**Done when** every state the diff renders has its scenario, each names its start state and its
final result, and the total fits the duration budget.

## 5. Data

Write `DIR/reset` (save the touched documents to `DIR/backup/`, then put them in the start state)
and `DIR/restore` (write `DIR/backup/` back), with the doc's **data** section. Force the flags the
scenario needs as its **flags** section says. A start state the
UI cannot reach quickly (a past event date, a document already extracted) is set by `reset`, off
camera. Run `reset`.

**Done when** the start state reads back from the database and shows in the app.

## 6. Dry run

First `doctor.sh <start URL of each scenario>`: a 404, a 500 or a server error shows here in
seconds. Then, in the Playwright MCP browser, sign in as the doc's **auth** section says, and use the
screen map and `browser_snapshot` to find locators (roles and names over CSS). Run the scenario once
with `browser_run_code_unsafe`, without recording, with `page.setDefaultTimeout(5000)` so a wrong
locator fails in seconds, returning what each step saw. When the diff touches a path another case shares (a single-day fix in a
picker that also takes ranges), dry-run that case too, unfilmed, and name it in the report. Then run
`reset` again.

**Done when** the dry run passes end to end and the start state is back.

## 7. Record

Copy `$SKILL/assets/record.js` to `DIR/record.js` (a re-take edits the existing one), fill `OUT`
and the scenario with its helpers — `click`, `type`, `title`, `cut(label, fn)` around loads and
off-camera setup, `wait(label, fn)` around server work — then run it through
`browser_run_code_unsafe` with `filename: DIR/record.js`. Save the returned JSON as
`DIR/markers.json`.

"Browser is already in use" means another session holds the MCP profile: leave it, and run the same
scenario from a Node script (`chromium.launch` from the repo's `playwright` package, signing in
first inside a `cut`).

**Done when** `markers.json` names an existing `.webm`.

## 8. Edit and check

```bash
python3 "$SKILL/scripts/edit.py" DIR/markers.json DIR/demo.mp4 --sheet DIR/sheet.png
```

Read `sheet.png`. The first frame shows the start state and the last frame the result; no frame is
blank, shows a login page, a dev overlay or an error toast. A result that differs from what the PR
promises is a finding: report it as a possible bug before any re-take. Run `DIR/restore` and
`cleanup.sh`, then `open DIR/demo.mp4`, and report its length, size and any change made to the
local-app doc.

**Done when** the sheet passes, the data is restored, and the user has said the video is good.

## 9. Attach

1. **Pushed**: `git fetch` in the worktree, then compare `HEAD` with `origin/<branch>`. When they
   differ, the video shows code the PR does not have: stop and offer to push.
2. **Place**: from `gh pr view <n> --json body -q .body`, splice `![](./demo.mp4)` in, first match
   wins — the line of the previous demo's `user-attachments` URL; the template's video or
   screenshots section; a new `## Demo` section just above `Closes`. Write it to `DIR/body.md`.
3. **Upload**, from `DIR` (the reference and the `--attach` argument must be the same string):
   `gh pr edit <n> -R <owner>/<repo> --body-file body.md --attach ./demo.mp4`

**Done when** the PR body holds the new `user-attachments` URL where the video goes, and no longer
the previous one.
