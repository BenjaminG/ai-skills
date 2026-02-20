# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A personal collection of Claude Code skills synced from `~/.claude/skills/`. Each top-level directory is a self-contained skill package.

## Skill Structure

Every skill follows this layout:

```
skill-name/
├── SKILL.md          # Required: YAML frontmatter + instructions
├── scripts/          # Executable Python/Bash scripts
├── references/       # Documentation loaded into context as needed
└── assets/           # Output files (templates, fonts, images)
```

**SKILL.md frontmatter** must include `name` and `description`. The `description` determines when Claude invokes the skill — make it specific and include trigger conditions.

## Creating a Skill

Use the initializer script:

```bash
python skill-creator/scripts/init_skill.py <skill-name> --path .
```

To package for distribution:

```bash
python skill-creator/scripts/package_skill.py <skill-name>
```

## Syncing to Claude

```bash
cp -r ~/Dev/ai-skills/* ~/.claude/skills/
```

## Key Conventions

- **Progressive disclosure**: Keep `SKILL.md` lean (<5k words). Move detailed schemas, API docs, and examples to `references/` files.
- **Writing style**: Imperative/verb-first throughout (`"To do X, run Y"` — not `"You should…"`).
- **`name` field**: Matches the directory name. No redundant `name:` inside markdown body.
- **`description` field**: Third-person phrasing (`"This skill should be used when…"`).
- Skills with `disable-model-invocation: true` run without invoking a model (used for data-gathering workflows like `daily-standup`).

## Skill Categories

- **Daily workflow** (`daily-*`): Standup compilation, task tracking, Jira/Slack integration. Uses `~/.claude/standups/` and `~/.claude/daily-tasks/` for persistence.
- **Code quality** (`quality-gate`, `code-slop`, `applying-solid-principles`): Review and auto-fix workflows using agent teams.
- **Developer tools** (`pr`, `hooks`, `commit`): Git/GitHub automation.
- **CLI integrations** (`atlassian-cli-jira`, `confluence-cli`, `codex-cli`): Wrappers for external CLI tools.
- **Specialist agents** (`backend-developer`, `frontend-developer`, `madai-investigator`): Domain-specific subagent definitions.
