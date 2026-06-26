# ai-skills

Benjamin's collection of skills for Claude Code, Codex, and other AI agents — packaged as a plugin and as a `skills`-installable bundle.

## Install

### Claude Code

```sh
/plugin marketplace add BenjaminG/ai-skills
/plugin install ai-skills@bgelis-ai-skills
```

Skills are namespaced after install: `/ai-skills:gate`, `/ai-skills:interview`, etc.

### Codex

```sh
codex plugin marketplace add BenjaminG/ai-skills
codex plugin add ai-skills@bgelis-ai-skills
```

You can also install it from `codex` → `/plugins` → `bgelis-ai-skills`.

### npx skills (any agent)

```sh
npx skills add BenjaminG/ai-skills
```

See the [`skills` CLI docs](https://www.skills.sh/docs) for scoping flags (`-g` global, `-a <agent>`, etc.).

## Skills

| Skill | Description |
|-------|-------------|
| **Daily workflow** | |
| `daily-update` | Draft a daily Slack update from Linear |
| **Code quality** | |
| `applying-solid-principles` | SOLID principles and clean code practices |
| `code-slop` | Detect and fix slop patterns |
| `gate` | Deterministic branch quality gate with parallel reviewers |
| `quality-gate` | Quality gate review for React/Next.js |
| `refactor-instructions` | Code refactoring guidelines |
| `second-pass` | Second-pass review of recent work |
| `ubiquitous-language` | Domain-driven naming review |
| **Review & PR** | |
| `consensus` | Run a prompt N times and consolidate by vote |
| `pr` | Publish a PR with type detection + Linear/Jira linking |
| `pr-feedback` | Triage and classify PR review comments + CI |
| `pr-respond` | Apply picked PR feedback + post replies/reactions/resolve |
| `pr-comment` | Post gate/gate-wf findings as a humanizer-drafted PR review |
| `qa-plan` | Manual QA plan generation |
| `qa-run` | Execute a manual QA plan |
| **Developer tools** | |
| `acli` | Jira management via acli |
| `chrome-cdp` | Drive a local Chrome session via DevTools Protocol |
| `codex-cli` | OpenAI Codex CLI for automated code analysis |
| `commit` | Stage + commit with auto-generated message |
| `confluence-cli` | Confluence content management via CLI |
| `hooks` | Create and manage Claude Code hooks |
| **Investigation & planning** | |
| `elevate` | Elevate a draft idea into a sharp proposal |
| `innovate` | Generate divergent solutions for a problem |
| `interview` | One-question-at-a-time clarification loop |
| `investigate` | Structured investigation workflow |
| `ralph-loop` | Run autonomous iterative loops over multi-step tasks |
| `retrospective` | Reflect on the work done on the current branch vs main |
| `skill-creator` | Guide for creating skills |
| **Specialist agents** | |
| `backend-developer` | TypeScript backend specialist |
| `frontend-developer` | React/TypeScript frontend specialist |
| `swiftui-performance` | SwiftUI performance optimization |
| `ui-skills` | Opinionated constraints for better interfaces |

## Repo layout

```
.
├── .agents/
│   └── plugins/
│       └── marketplace.json # Codex marketplace catalog
├── .claude-plugin/
│   ├── plugin.json         # Claude Code plugin manifest
│   └── marketplace.json    # one-plugin marketplace catalog
├── .codex-plugin/
│   └── plugin.json         # Codex plugin manifest
├── plugins/
│   └── ai-skills -> ..     # Codex marketplace path to root plugin
├── scripts/
│   └── bump-version.sh     # bump version in both manifests + tag a release
├── skills/                 # all skills live here as <name>/SKILL.md
└── ...
```

## Develop

```sh
# Test the Claude Code plugin locally without installing
claude --plugin-dir .

# Reload after edits
/reload-plugins
```

To create a new skill, see `skills/skill-creator/SKILL.md`.

## Release

Both plugin manifests carry a `version` field (semver). Claude Code's `/plugin update`
compares it: users only receive an update once the number changes — pushing commits
without a bump ships nothing. Codex compares it the same way.

Bump both manifests in lockstep and tag the release with the helper:

```sh
scripts/bump-version.sh patch        # 1.0.0 -> 1.0.1
scripts/bump-version.sh minor        # 1.0.0 -> 1.1.0
scripts/bump-version.sh major        # 1.0.0 -> 2.0.0
scripts/bump-version.sh 1.4.0        # explicit
scripts/bump-version.sh patch -n     # rewrite manifests only, no commit/tag
```

It updates `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, commits as
`chore(release): vX.Y.Z`, and creates an annotated tag — but does **not** push. Ship it:

```sh
git push && git push origin vX.Y.Z
```
