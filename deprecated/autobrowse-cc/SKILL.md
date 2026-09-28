---
name: autobrowse-cc
description: Build or harden a reliable browser-automation skill through a self-improving loop, with no Anthropic API key. Each iteration runs a headless `claude -p` inner agent that drives a local isolated Chrome via chrome-cdp, reads the run trace, adds one heuristic to strategy.md, and repeats until the task passes — then publishes a standalone skill. Use when asked to make a browser navigation task reliable, build/improve a browser automation skill, auto-tune a web workflow, or run a "self-improving browser loop". Local Chrome only (no Browserbase/remote, no codegen, no parallel fan-out).
argument-hint: "<task-name> [max-iterations]"
---

# autobrowse-cc

Self-improving browser automation, key-free. Port of Browserbase's `autobrowse`:
the inner agent is `claude -p` (reuses your session/Bedrock auth — no `ANTHROPIC_API_KEY`)
and the browser primitive is the local `chrome-cdp` skill (no `browse` CLI, no Browserbase).
The `claude -p --output-format stream-json` transcript serves as the trace.

You (the main session) ARE the outer loop. Drive it by hand per the algorithm below —
this is not a bash for-loop; you read each trace and reason about the next change.

## Layout

```
./autobrowse-cc/                 # runtime workspace, in CWD (created on demand)
├── tasks/<task>/task.md         # input spec (you author from references/example-task.md)
├── tasks/<task>/strategy.md     # accumulated heuristics (starts empty, you edit each iter)
└── traces/<task>/run-NNN.jsonl  # stream-json transcript per run; latest.jsonl symlinks it
```

Browser driving and graduation reuse the sibling skills. Prereqs: Node 22+ (chrome-cdp),
`jq`, and a working `claude` CLI. Default browser is the **isolated** Chrome profile
(`~/.chrome-debug-profile`) — the loop never touches the user's real browser.

## Algorithm

### 1. Set up the task
- If `./autobrowse-cc/tasks/<task>/task.md` doesn't exist, create it from
  `references/example-task.md`. Pin down the **success condition** precisely — the loop
  is only as good as what "done" means. Ask the user for URL, inputs, and steps if unclear.
- Leave `strategy.md` empty on first run (the runner creates it).

### 2. Iterate (default max 5)
Repeat until the stop condition in step 3:

1. Run one attempt:
   ```bash
   scripts/run-iteration.sh <task>
   ```
   It launches isolated Chrome, runs the `claude -p` inner agent scoped to `cdp.mjs`,
   writes `traces/<task>/run-NNN.jsonl`, and prints the verdict JSON + trace path.
2. **Read the trace.** Open `traces/<task>/latest.jsonl`. Walk the assistant turns and
   tool calls; find the EXACT turn where it failed or stalled (wrong selector, missing
   wait, unexpected page state, bad assumption). Quote it.
3. **Form ONE hypothesis** — a single concrete heuristic that would prevent that specific
   failure (e.g. "wait for `#results` to appear before clicking", "use selector `[name=q]`
   not the placeholder"). One change per iteration; never batch fixes.
4. **Edit `strategy.md`** — append the heuristic under the right section (Fast Path /
   Workflow / Site-Specific Knowledge / Failure Recovery). Keep everything that worked.
5. **Judge.** Re-run (back to step 1). If the verdict improved (passed, or got
   measurably further), keep the strategy edit. If it regressed, revert that edit and try
   a different hypothesis. Log nothing else — the traces and strategy.md are the record.

### 3. Stop condition
Stop when the task passes on **2 of the last 3** runs, or you hit max iterations. If max
is reached without 2/3 passing, report the best run and the open failure — don't publish a
flaky skill.

### 4. Graduate
On success, synthesize a **self-contained** skill at `~/.claude/skills/<task>/SKILL.md`
using `references/example-published-skill.md` as the template. Fold the winning
`strategy.md` and the verified step sequence into it — do not raw-copy strategy.md; the
published skill must reproduce the task from itself alone. Then tell the user the path and
the pass rate.

## Scope (deliberately dropped vs upstream autobrowse)
No Browserbase/remote sessions, no Playwright/Stagehand codegen, no parallel multi-task
fan-out. Single local task against isolated Chrome. Add those back only if a task needs
bot-protection handling or multi-task throughput.
