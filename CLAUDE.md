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

## Creating a Skill

Use the initializer script:

```bash
python skills/skill-creator/scripts/init_skill.py <skill-name> --path skills/
```

To package for distribution:

```bash
python skills/skill-creator/scripts/package_skill.py <skill-name>
```

## Local plugin testing

```bash
# Load this repo as a plugin without installing
claude --plugin-dir .

# Reload after edits
/reload-plugins
```

## Key Conventions

- **Progressive disclosure**: Keep `SKILL.md` lean (<5k words). Move detailed schemas, API docs, and examples to `references/` files.
- **Writing style**: Imperative/verb-first throughout (`"To do X, run Y"` — not `"You should…"`).
- **`name` field**: Matches the directory name. No redundant `name:` inside markdown body.
- **`description` field**: Third-person phrasing (`"This skill should be used when…"`).
- Skills with `disable-model-invocation: true` run without invoking a model (used for data-gathering workflows like `daily-standup`).

## Skill Categories

- **Daily workflow** (`daily-update`): Standup compilation from Linear/Slack.
- **Code quality** (`gate`, `gate-wf`, `quality-gate`, `triage-findings`, `code-slop`, `applying-solid-principles`, `second-pass`): Review and auto-fix workflows using agent teams. `gate-wf` reviews and renders a verdict; `triage-findings` acts on what it found (both share `skills/gate-wf/scripts/findings.py`).
- **Review & PR** (`pr-create`, `pr-challenge`, `pr-feedback`, `pr-respond`, `pr-comment`, `fixup`, `ci-watch`, `babysit-prs`, `review-mining`, `qa-plan`, `qa-run`, `consensus`): Git/GitHub and review automation. `pr-challenge` reviews someone else's PR as a colleague would (questions, not findings) and hands its drafts to `pr-comment`, which also posts `gate-wf` findings.
- **CLI integrations** (`acli`, `confluence-cli`, `codex-cli`, `chrome-cdp`): Wrappers for external CLI tools.
- **Investigation & planning** (`interview`, `investigate`, `elevate`, `innovate`, `retrospective`, `ralph-loop`, `skill-creator`): Structured thinking workflows.
- **Specialist agents** (`backend-developer`, `frontend-developer`, `swiftui-performance`): Domain-specific subagent definitions.
