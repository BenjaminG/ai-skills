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

`hooks/hooks.json` names one hooks module, `hooks/register.ts`, which registers the mods under `hooks/`: the panes `/prs`, `/wt` and `/xray` (skill usage and prompt cost), `next-step.ts` (proposes the chained skill after a turn, Tab to take) and `fixup-guard.ts` (asks before a commit that rewrites an earlier branch commit's lines). Early access: the module loads only with `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`.

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
- **Review & PR** (`pr-create`, `pr-challenge`, `pr-feedback`, `pr-respond`, `pr-comment`, `fixup`, `babysit-prs`, `pr-dash`, `pr-explain`, `pr-demo`, `review-mining`, `harness-review`, `qa-plan`, `qa-run`): Git/GitHub and review automation. `pr-challenge` reviews someone else's PR as a colleague would (questions, not findings) and hands its drafts to `pr-comment`, which also posts `gate-wf` findings. `pr-dash` owns the scan service (`pr-scan.py`) that both it and `babysit-prs` read; neither needs the other. `pr-explain` opens a herdr tab where a fresh session explains a `held` thread in plain words. `pr-demo` films a PR's flow in the local app through Playwright MCP and attaches the video to the PR. `harness-review` is the per-PR counterpart of `review-mining`: it places each review comment's cause on the harness ladder (codebase, lint, rules, skill) and drafts the fixes in a separate PR; it reads through `pr-feedback`'s `fetch-pr.py --full`.
- **CLI integrations** (`codex-cli`, `chrome-cdp`): Wrappers for external CLI tools.
- **Investigation & planning** (`interview`, `investigate`, `elevate`, `innovate`, `retrospective`, `orchestrate`): Structured thinking workflows.
- **Specialist agents** (`backend-developer`, `frontend-developer`): Domain-specific subagent definitions.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `BenjaminG/ai-skills` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
