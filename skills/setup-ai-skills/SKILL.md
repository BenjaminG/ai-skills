---
name: setup-ai-skills
description: Configures a host repo for the ai-skills that read it, by writing and proving its `docs/agents/` docs - `local-app.md` and its scripts (pr-demo, pr-shots, pr-try, showcase) and `signals.md`, where production symptoms live (elevate). This skill should be used for /setup-ai-skills, when one of those skills finds its doc missing, or to refresh a doc after the repo or its tooling changed.
argument-hint: "[local-app|signals]"
disable-model-invocation: true
---

# Setup ai-skills

A **host doc** is everything specific to the host repo that a skill needs and cannot rediscover
cheaply on every run. Each doc has a **contract** in `references/`: its files, its sections, where
to look for values, and the proof that the doc works. Read the doc's contract before step 1.

| Doc | Contract | Readers |
|---|---|---|
| `docs/agents/local-app.md` and `docs/agents/local-app/` | [`references/local-app.md`](references/local-app.md) | pr-demo, pr-shots, pr-try, showcase |
| `docs/agents/signals.md` | [`references/signals.md`](references/signals.md) | elevate |

The argument names the doc. Without one, set up every doc in the table, one after the other, each
through all six steps. A reader that found its doc missing sets up that doc only.

A run on a repo that has the doc is a **refresh**: the doc is the starting point, and the run proves
it again.

## 1. Explore

Read what exists; ask the user only what cannot be observed.

- **The sources the contract's Explore section lists.**
- **What is already written**: the doc itself (refresh), the other docs in `docs/agents/`, and the
  project memory directory (`~/.claude/projects/<slug>/memory/`, grep the contract's memory words).
  Each note about the doc's subject is input.

**Done when** each section of the contract has either a value from the repo, the tools or the
memory, or a question for the user.

## 2. Present and ask

Show one line per section: the value found and its source, or the gap. Ask the gaps in one
AskUserQuestion round. When `docs/agents/` holds no doc yet, add one question: commit the docs, or
add `docs/agents/` to `.git/info/exclude` (recommended when the team does not use these skills).
When it already holds docs, follow the choice they show.

**Done when** every gap has an answer and the commit-or-exclude choice is known.

## 3. Write

Write every file the contract lists. On a refresh, change only what the proof contradicts or what
the repo changed. Apply the commit-or-exclude choice.

**Done when** every file of the contract exists, scripts are executable, and no placeholder is left.

## 4. Prove

Run the contract's Proof section, reading the written doc rather than memory of it. Fix the doc or
its scripts at each failure and run the failed step again. Write in the doc what was proven, when, and what was
not.

**Done when** the contract's proof passes in one go from the written files.

## 5. Retire the old sources

List what the doc now covers: the sources the contract names as retirable and each memory note
whose content the doc now carries. Delete them once the user confirms the list. A memory note that
still holds a reason the doc does not keep, or that another skill still reads, stays, trimmed to
what the doc lacks.

**Done when** each listed source is deleted or trimmed, as the user confirmed.

## 6. Report

Give the files written, whether they are committed or excluded, what is `unproven` or
`unavailable`, and the sources retired.
