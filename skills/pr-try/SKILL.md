---
name: pr-try
description: Hands the local app, running a PR's or branch's code, to the user for a manual test, one scenario at a time from its start state, in a visible browser. This skill should be used when the user wants to test a PR, a branch or a fix by hand ("je veux tester", "tester à la main").
argument-hint: "[PR|branch]"
---

# PR try

A **session** is the user testing a change by hand in the Playwright MCP browser window, one
scenario at a time; it ends with a report in the chat.

Everything for one target lives in `DIR=~/.cache/pr-try/<owner>-<repo>/<PR number or branch slug>/`.

## 1. Resolve

Take the PR number or branch from `$ARGUMENTS`, else the current branch. With a PR (given, or open
for the branch): `gh pr view [<n>] --json number,url,headRefName,headRepositoryOwner,body,baseRefName`.
Without one, the base is the repo's default branch. Create `DIR`. Locate
pr-demo, whose setup this skill shares:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-demo}" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-demo 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-demo"; do
  [ -n "$c" ] && [ -f "$c/SKILL.md" ] && echo "$c" && break
done
```

Use the printed path as `$DEMO` literally.

**Done when** the branch, its base, the PR (or none), `DIR` and `$DEMO` are known.

## 2. Environment

Read `$DEMO/SKILL.md` and run its sections **Local-app doc** and **Environment** for this branch.
`$SKILL` in those sections is `$DEMO`. Note the herdr panes this run creates; Close stops them.

**Done when** pr-demo's two criteria hold.

## 3. Checklist

Read the PR's "How can it be tested?" section (when there is a PR), then the diff against the base.
Write `DIR/checklist.md`: 3 to 6 numbered scenarios, each with its start state, what to try, and the
expected result. Cover what the change promises, its edge cases, and the likely regressions around
the code it touches. Show the list and wait for the user's go; the user may edit it.

**Done when** every behaviour the diff changes on screen has a scenario, and the user has accepted
the checklist.

## 4. Data

Run pr-demo's **Data** section with this skill's `DIR`, with one change: `DIR/reset <n>` takes a
scenario number and sets that scenario's start state; `DIR/restore` puts everything back.

**Done when** `DIR/reset <n>` runs for every scenario and each start state reads back from the
database.

## 5. Session

For each scenario, in order:

1. **Set up**: `DIR/reset <n>`. In the Playwright MCP browser, sign in as the local-app doc's
   **auth** section says (once per session), then reach the start state with the screen map and
   `browser_snapshot`, playing the steps before it when the state is deeper than a URL. Check the
   snapshot shows it. "Browser is already in use" means another session holds the MCP profile and
   the user has no window to drive: stop and tell them.
2. **Hand over**: the user drives, Claude watches. One short message with the scenario number, what to try and the expected result.
   From here Claude is **hands-off**: it reads with `browser_snapshot`, `browser_console_messages`,
   `browser_network_requests` and `browser_take_screenshot`, and leaves clicks, typing and
   navigation to the user until the user answers.
3. **Answer**: tick the checklist in the chat as the user replies.
   - `ok` → ✅, next scenario.
   - `suivant` → ⏭️, next scenario.
   - `reset` → back to step 1 for the same scenario.
   - `ko: <what they see>` → **Fix loop** below.

### Fix loop

1. **Diagnose** from evidence: the console, the failed requests, the server panes
   (`herdr pane read`), then the code. Name the root cause
   and the proposed fix in a few lines, and wait for the user's go. A declined fix leaves the
   scenario ❌ with the cause noted.
2. **Apply** the fix in the worktree, uncommitted. Wait for hot reload (restart the server in its
   pane when the change needs it), then set up the scenario again (step 1) and hand over.
3. **Fold**: when the user answers `ok` on the retest, run the `fixup` skill on that change; the
   scenario is ✅. `ko` again → back to Diagnose.

**Done when** every scenario is ✅, ❌ or ⏭️, or the user says `fini`.

## 6. Close

1. `DIR/restore`, then `cleanup.sh`.
2. `browser_close`.
3. Stop the server panes this run created (`ctrl+c`, then close them). Leave the worktree and every
   other pane.
4. Report: the ticked checklist, the commits folded by `fixup`, the fixes still uncommitted in the
   worktree, and any change made to the local-app doc.

**Done when** the data is restored, the panes this run created are gone, and the report is out.
