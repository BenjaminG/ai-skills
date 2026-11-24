---
name: shots
description: Takes screenshots of a change or a feature in the local app through Playwright MCP, as before/after pairs or as a gallery of a feature's states, from a pull request, a branch or a feature named in words. Hands them off as a folder of PNGs with a ready-to-paste Markdown section, and attaches them to the PR description when the source is a PR. This skill should be used when asked for screenshots or captures of a PR, a branch or a feature ("avant/après", "before/after", "screens de la feature", "captures pour partager sur Slack"), or to re-take or update them.
argument-hint: "[compare|gallery] [PR | branch | \"feature\"] [--base <ref>]"
---

# Shots

A **shot** is one screen of the local app in one state, captured at a fixed 1440×900 viewport. The
skill has two modes:

- **compare**, for a fix or an improvement: each shot is a **pair**, the same screen and framing
  before the change and after it.
- **gallery**, for a new feature: one shot per state of the feature (empty, filled, error, loading,
  another role's view…).

The **source** is what the shots show: a PR, a branch, or a feature or app area named in words.
Everything for one source lives in `DIR=~/.cache/shots/<owner>-<repo>/<slug>/`, the slug being
`pr-<n>`, the branch name with `/` replaced by `-`, or a short kebab-case slug of the words. A second
run with the same slug is a **re-take**: it reuses the shot list and scripts already there.

## 1. Resolve

From `$ARGUMENTS`: the mode, `--base <ref>`, and the source. No source → the current branch's PR
(`gh pr view`), else the current branch when it is not the default one, else ask.

- **PR**: `gh pr view [<n>] --json number,url,title,headRefName,baseRefName,headRepositoryOwner,body`.
  The worktree is the one on its head branch.
- **branch**: the worktree on it (`git worktree list`); the default branch is
  `git symbolic-ref --short refs/remotes/origin/HEAD`.
- **words**: the current worktree, as it is.

The **before ref** of compare: `--base` when given, taken as is; else the merge-base of `HEAD` with the
PR's base (PR) or with the default branch (branch). A source in words without `--base` has none, so
only gallery applies.

The mode defaults to `compare` when the PR title or the branch name starts with `fix`, `perf` or
`refactor` and a before ref exists, else `gallery`; state the mode in one line. Create `DIR`. Locate
pr-demo, whose setup this skill shares:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-demo}" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-demo 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-demo"; do
  [ -n "$c" ] && [ -f "$c/SKILL.md" ] && echo "$c" && break
done
```

Use the printed path as `$DEMO` literally.

**Done when** the source, the mode, the worktree, the before ref (compare), `DIR` and `$DEMO` are known.

## 2. Environment

Read `$DEMO/SKILL.md` and run its sections **Local-app doc**, **Environment** and **Data**, with
this skill's `DIR` in place of the demo directory and the source's worktree in place of the PR's: same
`docs/agents/local-app.md`, same running servers, `DIR/reset` and `DIR/restore` for the start state.
`$SKILL` in those sections is `$DEMO`.

**Done when** pr-demo's three criteria hold.

## 3. Shot list

Read what the source gives: for a PR, its description, the ticket it links and that ticket's mockups
(a design file, an artifact), then the diff; for a branch, the ticket its name points to and the diff
against the before ref or the default branch; for words, the routes and screens they name. When the
point of the change is unclear from them, ask the user.

- **compare**: one pair per screen the change visibly alters.
- **gallery**: one shot per state a reader needs to see to judge the feature.

Write `DIR/shots.md`, one line per shot: number, slug, URL, the state and how to reach it, framing
(full page, or the changed component). A re-take starts from the existing `shots.md` and adapts it to
the new diff. Show the list and wait for the user's go.

**Done when** the user has accepted the list.

## 4. Capture

In the Playwright MCP browser: `browser_resize` to 1440×900, sign in as the local-app doc's **auth** section says. Before
each shot, hide the dev overlays with `browser_evaluate`, injecting the `display: none` rule from
`$DEMO/assets/record.js`. Capture with `browser_take_screenshot` and `filename`, passing `element` and
`ref` for a component framing:

- **gallery**: `DIR/<n>-<slug>.png`, with `reset` before each state that needs it.
- **compare**: in the source's worktree, with a clean tree (`git status --porcelain` empty), note the
  current branch, then:
  1. `git switch --detach <before ref>`. When the lockfile differs between the two commits,
     reinstall dependencies. Wait for the servers to reload, run `reset`, then capture every
     `DIR/<n>-<slug>-before.png`.
  2. `git switch <branch>` (reinstall again if needed), wait for the reload, run `reset`, then
     capture every `DIR/<n>-<slug>-after.png` with the same URL, state, and framing as its pair.

**Done when** every line of `shots.md` has its file(s) and the worktree is back on its branch.

## 5. Check

Read every PNG. No shot shows a login page, a dev overlay, an error toast, or a blank screen; both
halves of a pair have the same framing. An *after* that differs from what the source promises (the
PR's description, the ticket, the user's words) is a finding: report it as a possible bug before any
re-take. So is a screen the mockups lack or show differently. Run `DIR/restore`.

**Done when** every shot passes, the data is restored, and the user has said the shots are good.

## 6. Hand off

1. **Section** (English, or the user's language when the shots are for the team), referencing each
   file as `./<file>`:
   - **compare**: `| Before | After |`, one row per pair, the slug as row caption above the table
     or in a first column.
   - **gallery**: per shot, a one-line caption naming the state, then the image.

   Write it to `DIR/share.md`, run `open DIR`, and give the user the path of `DIR`.
2. **PR source only**, offer to attach the shots to the PR. On yes:
   1. **Pushed**: `git fetch` in the worktree, then compare `HEAD` with `origin/<branch>`. When they
      differ, the shots show code the PR does not have: stop and offer to push.
   2. **Place**: from `gh pr view <n> --json body -q .body`, first match wins: the previous run's
      screenshots section (replaced whole); the template's screenshots section; a new `## Screenshots`
      just above `Closes`. Write the body with the section in it to `DIR/body.md`.
   3. **Upload**, from `DIR`, one `--attach` per file (the reference and the argument must be the same
      string; `#` adds alt text):
      `gh pr edit <n> -R <owner>/<repo> --body-file body.md --attach './1-slug-before.png#<alt>' …`

**Done when** `DIR/share.md` references every shot and the folder is open; for an attached PR, its body
holds the new `user-attachments` URLs in the section, and none from the previous run.
