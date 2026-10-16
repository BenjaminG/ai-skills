---
name: pr-shots
description: Takes screenshots of a pull request's change in the local app through Playwright MCP, as before/after pairs or as a gallery of a feature's states, then attaches them to the PR description. This skill should be used when asked for screenshots or captures of a PR ("avant/après", "before/after", "screens de la feature"), or to re-take or update the screenshots on a PR.
argument-hint: "[compare|gallery] [PR]"
---

# PR shots

A **shot** is one screen of the local app in one state, captured at a fixed 1440×900 viewport. The
skill has two modes:

- **compare**, for a fix or an improvement: each shot is a **pair**, the same screen and framing on
  the base branch (before) and on the PR branch (after).
- **gallery**, for a new feature: one shot per state of the feature (empty, filled, error, loading,
  another role's view…).

Everything for one PR lives in `DIR=~/.cache/pr-shots/<owner>-<repo>/<PR>/`. A second run on the same
PR is a **re-take**: it reuses the shot list and scripts already there.

## 1. Resolve

Take the mode and the PR from `$ARGUMENTS`. The mode defaults from the PR title: `fix`, `perf` or
`refactor` → `compare`, anything else → `gallery`; state the mode in one line. PR, else the current
branch's: `gh pr view [<n>] --json number,url,title,headRefName,baseRefName,headRepositoryOwner,body`.
Create `DIR`. Locate pr-demo, whose setup this skill shares:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-demo}" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-demo 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-demo"; do
  [ -n "$c" ] && [ -f "$c/SKILL.md" ] && echo "$c" && break
done
```

Use the printed path as `$DEMO` literally.

**Done when** the mode, the PR number, its head and base branches, `DIR` and `$DEMO` are known.

## 2. Environment

Read `$DEMO/SKILL.md` and run its sections **Project note**, **Environment** and **Data**, with this
skill's `DIR` in place of the demo directory: same `pr-demo-local-env` memory, same running servers
from the PR's worktree, `DIR/reset` and `DIR/restore` for the start state.

**Done when** pr-demo's three criteria hold.

## 3. Shot list

Read the PR's description, then the diff.

- **compare**: one pair per screen the diff visibly changes.
- **gallery**: one shot per state a reviewer needs to see to judge the feature.

Write `DIR/shots.md`, one line per shot: number, slug, URL, the state and how to reach it, framing
(full page, or the changed component). A re-take starts from the existing `shots.md` and adapts it to
the new diff. Show the list and wait for the user's go.

**Done when** the user has accepted the list.

## 4. Capture

In the Playwright MCP browser: `browser_resize` to 1440×900, sign in with the note's account. Before
each shot, hide the dev overlays with `browser_evaluate`, injecting the `display: none` rule from
`$DEMO/assets/record.js`. Capture with `browser_take_screenshot` and `filename`, passing `element` and
`ref` for a component framing:

- **gallery**: `DIR/<n>-<slug>.png`, with `reset` before each state that needs it.
- **compare**: in the PR's worktree, with a clean tree (`git status --porcelain` empty):
  1. `git switch --detach $(git merge-base origin/<base> HEAD)`. When the lockfile differs between
     the two commits, reinstall dependencies. Wait for the servers to reload, run `reset`, then
     capture every `DIR/<n>-<slug>-before.png`.
  2. `git switch <branch>` (reinstall again if needed), wait for the reload, run `reset`, then
     capture every `DIR/<n>-<slug>-after.png` with the same URL, state, and framing as its pair.

**Done when** every line of `shots.md` has its file(s) and the worktree is back on the PR branch.

## 5. Check

Read every PNG. No shot shows a login page, a dev overlay, an error toast, or a blank screen; both
halves of a pair have the same framing. An *after* that differs from what the PR promises is a
finding: report it as a possible bug before any re-take. Run `DIR/restore`.

**Done when** every shot passes, the data is restored, and the user has said the shots are good.

## 6. Attach

1. **Pushed**: `git fetch` in the worktree, then compare `HEAD` with `origin/<branch>`. When they
   differ, the shots show code the PR does not have: stop and offer to push.
2. **Section** (English, like the PR), referencing each file as `./<file>`:
   - **compare**: `| Before | After |`, one row per pair, the slug as row caption above the table
     or in a first column.
   - **gallery**: per shot, a one-line caption naming the state, then the image.
3. **Place**: from `gh pr view <n> --json body -q .body`, first match wins: the previous run's
   screenshots section (replaced whole); the template's screenshots section; a new `## Screenshots`
   just above `Closes`. Write it to `DIR/body.md`.
4. **Upload**, from `DIR`, one `--attach` per file (the reference and the argument must be the same
   string; `#` adds alt text):
   `gh pr edit <n> -R <owner>/<repo> --body-file body.md --attach './1-slug-before.png#<alt>' …`

**Done when** the PR body holds the new `user-attachments` URLs in the section, and none from the
previous run.
