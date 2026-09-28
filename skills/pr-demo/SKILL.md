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

## 2. Project note

The project's memory holds a **demo note**: the ports of each local server and their start
commands, the login URL and test account, the database and its shell, where test fixtures live.
Find it in the project memory directory (grep `pr-demo`). When there is none, gather those facts
from the repo (`package.json` scripts, `.env*`, `CLAUDE.md`, older memories) and write the note
once step 6 has proved them, as a `reference` memory named `pr-demo-local-env`.

**Done when** every item of the note has a value, from the note or from the repo.

## 3. Environment

1. **Worktree**: the PR branch's worktree (`git worktree list`). None → `wt switch <branch>`
   (worktrunk skill), then install dependencies.
2. **Servers**: for each port in the note, `lsof -nP -iTCP:<port> -sTCP:LISTEN -t`, then the
   process's cwd (`lsof -a -p <pid> -d cwd -Fn`).
   - Nothing listening → start it in the herdr tab "dev server" (herdr skill), from the worktree.
   - Listening from another worktree → ask before killing it; the user may be using it.

**Done when** every server answers over HTTP and each listening process runs from the PR's worktree.

## 4. Scenario

Read the PR's "How can it be tested?" section, then the diff. Write each scenario as a start state,
the actions, and the final visible result — the thing the PR changes on screen. Show the plan (one
line per scenario) only when there are several scenarios or the flow is ambiguous; otherwise go on.
A re-take starts from `DIR/record.js` and adapts it to the new diff.

**Done when** each scenario names its start state and its final result, and the total fits the
duration budget.

## 5. Data

Write `DIR/reset` (save the touched documents to `DIR/backup/`, then put them in the start state)
and `DIR/restore` (write `DIR/backup/` back), using the database from the note. A start state the
UI cannot reach quickly (a past event date, a document already extracted) is set by `reset`, off
camera. Run `reset`.

**Done when** the start state reads back from the database and shows in the app.

## 6. Dry run

In the Playwright MCP browser, sign in with the note's account, then use `browser_snapshot` to find
locators (roles and names over CSS). Run the scenario once with `browser_run_code_unsafe`, without
recording, returning what each step saw. Then run `reset` again.

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
promises is a finding: report it as a possible bug before any re-take. Run `DIR/restore`, then
`open DIR/demo.mp4`, and report its length and size.

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
