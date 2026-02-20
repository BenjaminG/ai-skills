# Claude Code Skills

Personal collection of Claude Code skills from `~/.claude/skills/`.

## Skills

| Skill | Description |
|-------|-------------|
| **Daily workflow** (`daily/`) | |
| `daily-standup` | Morning standup — compile Jira/Slack priorities into a task list |
| `daily-next` | Pick up next task and gather full context (Jira, Slack, GitHub) |
| `daily-done` | Mark current task as done and show progress |
| `daily-standby` | Park a blocked task with a required reason |
| `daily-unblock` | Activate a standby task when its blocker is resolved |
| **Other skills** | |
| `applying-solid-principles` | SOLID principles and clean code practices |
| `atlassian-cli-jira` | Jira management via acli |
| `backend-developer` | TypeScript backend specialist (NestJS, APIs, databases) |
| `codex-cli` | OpenAI Codex CLI for automated code analysis |
| `confluence-cli` | Confluence content management via CLI |
| `frontend-design` | Production-grade frontend UI design |
| `frontend-developer` | React/TypeScript frontend specialist |
| `hooks` | Create and manage Claude Code hooks |
| `interview` | Interview users about plan files |
| `madai-investigator` | MadAI/MadKudu support ticket investigation |
| `quality` | Quality gate review for React/Next.js |
| `ralph-loop` | Refactoring patterns and templates |
| `refactor-instructions` | Code refactoring guidelines |
| `skill-creator` | Guide for creating Claude Code skills |
| `ui-skills` | Opinionated constraints for better interfaces |
| `vercel-react-best-practices` | React/Next.js performance optimization |

## Installation

To sync these skills back to `~/.claude/skills/`:

```bash
cp -r ~/Dev/ai-skills/* ~/.claude/skills/
```

## Excluded

The following symlinked skills were **not** included:
- `find-skills` → `~/.agents/skills/`
- `prd` → `~/.agents/skills/`
- `swiftui-expert-skill` → `~/.agents/skills/`
- `performance-profiling` → Skillbox cache
