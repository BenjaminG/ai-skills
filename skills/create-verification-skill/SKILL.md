---
name: create-verification-skill
description: "Generates a project-local Claude Code skill (.claude/skills/verify-<app>/) that drives the repo's app the way a user does and captures proof, for any language, framework, or platform. This skill should be used for /create-verification-skill, \"make a verify skill for this repo\", or when a project has no scripted way to prove UI, CLI, or service behavior."
disable-model-invocation: true
---

# Create a verification skill

Adapted from pstack's `create-verification-skill` (cursor/plugins, MIT) for Claude Code.

Every serious project needs a scripted way to drive the real app and prove behavior: launch it, exercise a feature the way a user would, and capture evidence. This skill generates that as a project-local skill (`.claude/skills/verify-<app>/`) tailored to the repo. Write it for the next agent, not for a human: a Claude Code session will read it cold, mid-task, without ever having seen the app.

## 1. Interview the repo, not the user

Answer these from the codebase and only ask the user (AskUserQuestion) what cannot be observed:

- **Surface:** what does a user actually touch? A web UI, a CLI/TUI, a desktop app, an API, a mobile app, a library? A repo can have several; pick the primary one and note the rest.
- **Run:** how does the app start locally? Prefer the repo's own documented dev command (package scripts, Makefile, README quickstart, CLAUDE.md). Note ports, env vars, seed data, auth.
- **Drive:** how can an agent interact with it programmatically? Existing harnesses first — Playwright/Cypress specs, expect scripts, PTY helpers, curl-able endpoints, a debug port. Only then pick a generic recipe from the table in step 2.
- **Observe:** what evidence can be captured? Screenshots, ARIA snapshots, terminal transcripts, response bodies, logs, exit codes, DB state.
- **Isolate:** can two instances run side by side (ports, data dirs, profiles)? If not, say so in the generated skill: refusing to double-drive a shared instance beats corrupting the user's session.

If the checkout doesn't build or start as-is, fix that first (or report it precisely) before generating; a skill written against a broken base teaches wrong steps. When an irrelevant missing asset blocks startup (a static dir the API never serves, a sample config), the generated skill may create it, clearly marked as verification scaffolding, and remove it in cleanup.

## 2. Generate the skill

Pick the generic recipes only where the repo has no harness of its own:

| Surface | Process host | Drive with |
|---|---|---|
| Long-lived server (web app, API, desktop dev server) | herdr pane when `test "${HERDR_ENV:-}" = 1`, else a detached tmux session | — |
| Web UI, Electron renderer | same | Playwright MCP (`mcp__playwright__browser_*`) |
| CLI | none: one Bash call per command | Bash, capturing stdout, stderr, exit code |
| TUI, interactive prompt | one tmux session per drive | `tmux send-keys` / `tmux capture-pane -p` |
| HTTP service | same as server | `curl -sS -w '%{http_code}'` |

Long-lived processes never run through Bash `run_in_background`, `&`, or `nohup`: their output must stay readable by the user and by the next agent. The recipes, to adapt into the generated skill with the repo's real command and ready text:

```bash
# herdr: sibling pane, unfocused; read the new pane id from the JSON reply
herdr pane split --current --direction down --no-focus
herdr pane run <pane_id> '<dev command>'
herdr pane wait-output <pane_id> --match '<ready text>' --timeout 120000
herdr pane read <pane_id> --source recent-unwrapped --lines 80   # logs
herdr pane send-keys <pane_id> ctrl+c && herdr pane close <pane_id>   # teardown

# tmux fallback
tmux new-session -d -s verify-<app>-$RUN_ID -x 200 -y 50 '<dev command>'
until tmux capture-pane -p -t verify-<app>-$RUN_ID -S -200 | grep -q '<ready text>'; do sleep 1; done
tmux capture-pane -p -t verify-<app>-$RUN_ID -S -200   # logs
tmux kill-session -t verify-<app>-$RUN_ID              # teardown
```

Wrap the tmux wait in a timeout. Record the pane id or session name the run created: cleanup kills exactly that.

For Playwright MCP, check the `mcp__playwright__*` tools are loaded; if not, the generated skill says to run `claude mcp add playwright -- npx @playwright/mcp@latest --isolated` and restart the session. The MCP addresses elements by the `ref` that `browser_snapshot` returns, so recipes name each element by its accessible role and name (`button "New note"`) and resolve the ref from a fresh snapshot before every click or fill. One MCP browser serves the whole session: drive features serially, and open a tab per instance if two run side by side.

Write `.claude/skills/verify-<app>/SKILL.md` with YAML frontmatter (`name: verify-<app>` and a `description` in the third person that names the app, the surface, and when to reach for it — without frontmatter the skill never registers) and these sections, each grounded in what the interview actually found (no placeholders left):

- **Launch:** the exact command that starts the app for verification, its process host from the table, and how to tell it's ready (a log line, a prompt). Launch must reach a usable state from an empty data dir, including any migrations and seed data. Ready means usable, not just that a process answers. A database health check can pass while its init scripts are still running. Include teardown. For a short-lived CLI or TUI there is no server to keep alive: launch means build the binary (or install deps) once, then start each drive in its own isolated tmux session or Bash call.
- **Doctor:** one read-only check that answers "is this instance worth driving?" — process up, right version/build, port owned by this run (`lsof -iTCP:<port> -sTCP:LISTEN` matches the pane or session's process), auth valid. An agent runs this first whenever anything looks off.
- **Drive:** the harness recipe with real selectors/commands from this repo, not examples. Prefer stable handles (ARIA roles and names, data attributes, prompt strings, route paths) over coordinates and tab order.
- **Evidence:** what to capture for a proof and where it goes: a directory the skill names, one subdirectory per run, added to `.gitignore` (such as `.verify-artifacts/<run-id>/`; Playwright MCP's `browser_take_screenshot` and `browser_snapshot` take a `filename`; pass a path inside it). State the proof standards: exercise the real user path, not internal setters or test-only endpoints; capture the action and the resulting state, not just the final screen; verify side effects (files written, rows inserted, messages sent) alongside what's visible; mocks only where a production boundary already isolates the external system. When the safe path is a dry-run or test mode, verify what it actually skips by observing (files, network, git refs) rather than trusting its name: some dry-runs still touch the network or open a browser.
- **Cleanup:** how to tear down instances the run created. Never kill by process name; kill what you started (the recorded pane id, tmux session, or PID), and close the MCP tab you opened. Never close a herdr pane the run did not create. Cleanup removes instances and scratch state, never the evidence: proof artifacts survive the teardown, in the location the skill names.
- **Helpers:** any script the skill ships lives in `.claude/skills/verify-<app>/scripts/`, is executable, and its invocation is shown in the skill body with its path from the repo root. A helper the reader has to reverse-engineer is not a helper.

## 3. Seed the feature map

Create `.claude/skills/verify-<app>/features/README.md` plus one file per user-facing feature you can identify (aim for the top 3-5 to start, from routes, commands, menus, or docs). Follow the shape in [`references/feature-map-example/`](references/feature-map-example/), with a README index and one file per feature. Each file answers, from the user's point of view: what the feature is, how to reach it, how to drive it with the harness, and what observable end state proves it works. The four H2s are `Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>`, and `Gotchas`. If the seed data lacks a precondition that a journey needs, the journey reports a failure and the reason goes in that feature's `Gotchas`. Never weaken the journey to make it pass. The map is the repo's maintained verification source; a proof that drives one convenient entry point is incomplete when the map lists others.

## 4. Prove the generated skill before handing it over

Run its own instructions end to end once, reading the generated SKILL.md rather than memory of it: launch, doctor, drive ONE mapped feature (one is enough; the map exists so later runs can cover the rest), capture evidence, clean up. After cleanup, confirm the evidence still exists at the named location — a cleanup that eats the proof fails this step. Fix what fails, and run the generated cleanup after every failed iteration too, so broken attempts don't strand panes, sessions, and ports. A generated skill that was never executed is a draft, not a deliverable. If you proved it in a stand-in for the real target (a container in place of a fresh VM, a local stack in place of a remote one, the herdr host where teammates will use tmux), list every setup step the stand-in did that the target will not. Those steps stay unverified until a run on the real target covers them.

## 5. Offer the maintenance loop

Point the user at `/maintain-verification-skill` for keeping the map honest as the app changes. Suggest a cadence only if they ask.
