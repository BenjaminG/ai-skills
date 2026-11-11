# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A personal collection of skills, distributed as a Claude Code plugin and a Codex plugin. Skills live under `skills/<name>/`; plugin manifests live under `.claude-plugin/` and `.codex-plugin/`.

## Skill Structure

Every skill lives at `skills/<name>/` and follows this layout:

```
skills/<name>/
├── SKILL.md          # Required: YAML frontmatter + instructions
├── scripts/          # Executable Python/Bash scripts
├── references/       # Documentation loaded into context as needed
└── assets/           # Output files (templates, fonts, images)
```

**SKILL.md frontmatter** must include `name` and `description`. The `description` determines when Claude invokes the skill — make it specific and include trigger conditions.

## Deprecated skills

`deprecated/<name>/` holds retired skills. None of the installers look there: the Claude plugin loads `skills/`, the Codex manifest points `skills` at `./skills/`, and `npx skills` searches `skills/` first and only falls back to a recursive search when that finds nothing. Do not reference a deprecated skill from a shipped one.

## Local plugin testing

```bash
# Load this repo as a plugin without installing
claude --plugin-dir .

# Reload after edits
/reload-plugins
```

## Mods (function hooks)

`hooks/hooks.json` names one hooks module, `hooks/register.ts`, which registers the mods under `hooks/`: the panes `/prs` (the author's open PRs, read from the standalone `pr-dash`'s `state.json`), `/wt` and `/xray` (skill usage and prompt cost), `next-step.ts` (proposes the chained skill after a turn, Tab to take), `/slack-follow` / `/slack-unfollow` (`slack-thread.ts`: polls a Slack thread through the claude.ai Slack MCP, submits new replies once the session is idle) and `/shepherd` (`babysit.ts`: the babysit-prs manager in code, reading `pr-dash`'s `state.json`, holding `skills/babysit-prs/scripts/watch.sh` around `pr-dash follow`, and spawning unnamed agents with `skills/babysit-prs/references/agent-prompt.md`, the prompt the skill uses too). Early access: the module loads only with `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`.

```bash
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude --plugin-dir .   # run from source
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin test .    # tests/*.test.ts
tsc -p tsconfig.json                                        # typecheck against .claude/types
```

Loader rules the tests enforce: one hook per event without a matcher per module (so `session.start` lives in `register.ts`); `$` may only be passed to a function declared in the same file, never across an import (so each mod keeps its own small `git` helper); `on` only to a function imported by name. `.claude/types/claude-code.d.ts` is what `/plugin-types` writes — regenerate it after a Claude Code update.

## Key Conventions

- **Progressive disclosure**: Keep `SKILL.md` lean (<5k words). Move detailed schemas, API docs, and examples to `references/` files.
- **Writing style**: Imperative/verb-first throughout (`"To do X, run Y"` — not `"You should…"`).
- **`name` field**: Matches the directory name. No redundant `name:` inside markdown body.
- **`description` field**: Third-person phrasing (`"This skill should be used when…"`).
- Skills with `disable-model-invocation: true` run without invoking a model (used for data-gathering workflows like `daily-standup`).

## Skill Categories

- **Daily workflow** (`daily-update`): Standup compilation from Linear/Slack.
- **Code quality** (`gate`, `gate-wf`, `triage-findings`, `code-slop`): Review and auto-fix workflows using agent teams. `gate-wf` reviews and renders a verdict; `triage-findings` acts on what it found (both share `skills/gate-wf/scripts/findings.py`).
- **Review & PR** (`pr-create`, `pr-challenge`, `pr-feedback`, `pr-respond`, `pr-comment`, `fixup`, `babysit-prs`, `pr-explain`, `pr-demo`, `pr-shots`, `pr-try`, `showcase`, `review-mining`, `harness-review`, `qa-plan`): Git/GitHub and review automation. `pr-challenge` reviews someone else's PR as a colleague would (questions, not findings) and hands its drafts to `pr-comment`, which also posts `gate-wf` findings. `babysit-prs`, `/prs` and `pr-explain` are Readers of the standalone `pr-dash` CLI (`npm i -g github:BenjaminG/pr-dash`, its own repo): they call `pr-dash state-dir`, `ensure`, `wake --wait` and `follow`, and read `state.json`. `pr-explain` opens a herdr tab where a fresh session explains a `held` thread in plain words. `pr-demo` films a PR's flow in the local app through Playwright MCP and attaches the video to the PR. `pr-shots` takes screenshots of the same local app, before/after pairs (base vs PR branch) or a gallery of a feature's states, and attaches them; it reuses pr-demo's local-app doc, environment and data steps. `pr-try` runs on the same setup but hands the visible Playwright MCP window to the user: one scenario at a time, it resets the data and drives the app to the start state, then watches the console, network and server logs while the user tests, and folds an accepted fix with `fixup` once the user's retest passes. `showcase` makes the team-facing counterpart of pr-demo: a narrated video of a feature, PR or app area (weekly pod update), with brand cards, numbered chapters and zooms. The user approves its script before filming; the voice comes from the ElevenLabs MCP, or none with `--no-voice`. It reuses pr-demo's setup, `record.js` (its `chapter`/`focus` helpers) and `edit.py`'s `segments`, and renders `assets/stage.html` frame by frame through Playwright. `harness-review` is the per-PR counterpart of `review-mining`: it places each review comment's cause on the harness ladder (codebase, lint, rules, skill) and drafts the fixes in a separate PR; it reads through `pr-feedback`'s `fetch-pr.py --full`.
- **Setup** (`setup-ai-skills`): writes and proves the host repo's `docs/agents/` docs, one contract each in `references/`: `local-app.md` and its scripts (prepare, launch, doctor, cleanup, screen map), which `pr-demo`, `pr-shots`, `pr-try` and `showcase` read, and `signals.md` (where production symptoms are reported: Datadog services, Slack channels by role, Linear bug labels, PostHog, git fix convention, each proven by a 30-day query), which `elevate` reads. Readers run it when their doc is missing and fix the doc when a run meets a new trap. A second run refreshes it. It replaces `create-verification-skill` and `maintain-verification-skill`, now in `deprecated/`.
- **CLI integrations** (`codex-cli`): Wrappers for external CLI tools.
- **Investigation & planning** (`interview`, `investigate`, `elevate`, `innovate`, `retrospective`, `orchestrate`): Structured thinking workflows. `elevate` starts from production symptoms (the host's `docs/agents/signals.md`), clusters them, traces each cluster to a causal chain in the code, and ranks levers from five families (guard, simplify, harden, change when, change where), ending on one project brief.
- **Self-improvement** (`skill-dream`, `dream`): `skill-dream <skill>` cuts the skill's runs out of the local transcripts (`scripts/extract.py`), has read-only agents find frictions the skill's text can be blamed for (`scripts/workflow.js`), drops themes later versions fixed (the `[x.y.z]` at the end of a commit subject maps a run's version to a commit), and opens a draft PR. The repo is public: transcript content only reaches it as a paraphrase. `dream` does the same for memory files.
- **Herdr** (`herdr-mod`): builds a mod for the Herdr app from the app's own `~/.config/herdr-app/AGENTS.md`; `--publish` shares it in `BenjaminG/herdr-mods` with the `herdr-mod` topic.
- **Specialist agents** (`backend-developer`, `frontend-developer`): Domain-specific subagent definitions.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `BenjaminG/ai-skills` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
