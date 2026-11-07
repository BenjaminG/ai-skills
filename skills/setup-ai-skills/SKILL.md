---
name: setup-ai-skills
description: Configures a host repo for the ai-skills that drive its local app (pr-demo, pr-shots, showcase) by writing and proving `docs/agents/local-app.md` and its scripts (prepare, launch, doctor, cleanup, screen map). This skill should be used for /setup-ai-skills, when one of those skills finds no `docs/agents/local-app.md`, or to refresh that doc after the app's setup changed.
disable-model-invocation: true
---

# Setup ai-skills

The **local-app doc** is everything specific to the host repo that a skill needs to run its app:
how to make a checkout runnable, start the servers, tell a healthy instance from a broken one, sign
in, find data, force a flag, and reach each screen. Skills read it instead of rediscovering the repo
on every run. [`references/local-app.md`](references/local-app.md) is the contract: the files, what
each script does, the sections of the doc. Read it before step 3.

A second run on a repo that has the doc is a **refresh**: the doc and the scripts are the starting
point, and the run proves them again.

## 1. Explore

Read what exists; ask the user only what cannot be observed.

- **The repo**: package scripts, `turbo.json` or the build tool's task graph (every code generation
  task, including those of shared packages), `docker-compose*`, `.env.example` files, README,
  `CLAUDE.md`/`AGENTS.md`, CI setup steps.
- **What is already written**: `docs/agents/local-app.md` (refresh), `.claude/skills/verify-*/`
  (its scripts and feature map become the starting point), and the project memory directory
  (`~/.claude/projects/<slug>/memory/`, grep `local|env|dev server|login|demo|turbo|flag`): each
  note about the local app is input.
- **What is running**: each port the repo uses, its process and that process's cwd.

**Done when** each of the eight sections of the doc has either a value from the repo or the memory,
or a question for the user.

## 2. Present and ask

Show one line per section: the value found and its source, or the gap. Ask the gaps in one
AskUserQuestion round, plus one question: commit the doc, or add `docs/agents/` to
`.git/info/exclude` (recommended when the team does not use these skills).

**Done when** every gap has an answer and the commit-or-exclude choice is made.

## 3. Write

Write `docs/agents/local-app.md`, the four scripts and the screen map, as the contract says. The
screen map starts from the verify skill's feature map when there is one, else from one to three
screens the user reaches most. On a refresh, change only what the proof below contradicts or what
the repo changed. Apply the commit-or-exclude choice.

**Done when** every file of the contract exists, the scripts are executable, and no placeholder is
left.

## 4. Prove

Run the doc, reading it rather than memory of it:

1. `prepare.sh`.
2. The servers. Nothing listening: run each `launch.sh <name>` in its own herdr pane in a tab named
   `dev server` (herdr skill), and wait for its ready text. Something listening: ask before stopping
   it, since it may serve the user's work. When the user keeps it, run the whole proof from the
   checkout those servers run from, and mark the launch section `unproven` in the doc.
3. `doctor.sh <start URL of one mapped screen>`: every line `ok`.
4. In the Playwright MCP browser, sign in as the auth section says and drive that screen's recipe.
   Data the recipe needs changed is backed up first and put back after.
5. `cleanup.sh`, then stop the panes this step created.

Fix the doc or the script at each failure, run `cleanup.sh`, and start the step again. A failure
caused by the data (a record the branch cannot read) is a finding for the doc: `doctor.sh` or the
fixture finder learns to name it, and the data section says how a `reset` fixes it. Write in the doc
what was proven, on which checkout, and what was not.

**Done when** the five steps pass in one go from the written files.

## 5. Retire the old sources

List what the doc now covers: the `verify-*` skill directory and each memory note folded in. Delete
them once the user confirms the list. A memory note that still holds a reason the doc does not keep
stays, trimmed to that reason.

**Done when** each listed source is deleted or trimmed, as the user confirmed.

## 6. Report

Give the files written, whether they are committed or excluded, what is `unproven`, and the sources
retired.
