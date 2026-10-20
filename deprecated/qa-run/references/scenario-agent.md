# Scenario sub-agent contract

One sub-agent per scenario, spawned sequentially (never parallel — Rule in
SKILL.md). It drives Chrome via the `chrome-cdp` skill in `--isolated` mode and
returns a single structured payload. Its DOM dumps, screenshots, and any source
reads stay in its own context — the orchestrator does all the writing.

## Setup (once, before the first scenario)

```bash
scripts/chrome-debug.sh   # from the chrome-cdp skill, idempotent
export CDP_PORT_FILE="$HOME/.chrome-debug-profile/DevToolsActivePort"
T=$(cdp.mjs list | awk 'NR==1{print $1}')   # confirm this is the app under test before trusting it
```

`$T` is resolved once by the orchestrator and passed to every scenario
sub-agent. Never bake a target id into a playbook entry — ids change on every
Chrome launch.

## Step 1: replay if a fast path exists

If the `## QA Playbook` comment has a `### §X.Y` block for this scenario, paste
the site Preamble (`references/playbook.md`), expand `@login(<role>)` from the
site playbook's Login block, then run `Reach` and `Verify` as **one** Bash call:

```bash
<preamble>
<login block, if not already authenticated as this role>
{ <Reach chain> && <Verify chain> ; }; RC=$?
C shot $T tasks/<TASK>/evidence/<X.Y>.png >/dev/null 2>&1
C snap $T | tail -60; echo "RC=$RC"
```

- **`RC=0`** — the final `W`/`A` in the chain observed the expected end state.
  That *is* the verification; no extra confirmation snap is needed. Report
  `replay: hit`.
- **`RC≠0`** — the last `Error:` line names the selector that broke, and you
  already have the post-mortem `snap`/`shot`. **Resume interactive exploration
  from that step. Do not re-run the chain and do not restart from step 1.**
  Report `replay: stale:<selector>`.
- **No block for this scenario** — skip to Step 2. Report `replay: none`.

## Step 2: explore (no fast path, or replay went stale)

Drive interactively: `click`/`type` → `snap` → look → decide the next action.
After **every** action that can change the page, re-`snap` — refs and the DOM
invalidate on change. Use `snap`, not `html`, for structure; save `shot` only
for the proof/debug screenshots called for below.

As you go, note which selectors actually worked and what each landed on — this
becomes the `playbook.scenario` block you return (Step 3). Never bake a `snap`
ref, a `clickxy` coordinate, or an index-based selector into that block; see
the selector policy in `references/playbook.md`.

## Step 3: return payload

```json
{
  "status": "pass|fail|skip",
  "note": "<one line>",
  "proof": "tasks/<TASK>/evidence/<X.Y>.png",
  "debug": ["tasks/<TASK>/evidence/<X.Y>-debug-1.png", "..."],
  "trace": { "account": "<email/role>", "path": ["<action> → <URL>", "..."] },
  "finding": {
    "title": "...", "severity": "blocker|improvement|nit|plan-defect",
    "repro": "...", "expected": "...", "observed": "...",
    "root_cause": "<file:line, dev runner only>"
  },
  "replay": "hit|stale:<selector>|none",
  "playbook": {
    "site": ["<Env|Accounts|Login|Quirks|Not automatable> — <new fact>"],
    "scenario": "<complete replacement ### §X.Y block, per rules below>"
  }
}
```

`finding` is present only when `status` is `fail` or a plan-defect `skip`.
`playbook.site` is 0–2 new lines; omit the key entirely when nothing new
surfaced. `playbook.scenario` rules (see `references/playbook.md` § Learning):

- **`Verify` only from a PASS.** A fail/skip returns `Reach` (if a precondition
  was reached) plus `Verify: none — <why>` — never a `Verify` chain. Recording a
  bug path as a fast path would teach the next run to reproduce the bug as if it
  were the happy path.
- On a stale replay that got fixed, return the corrected block with `Stale: 0`.
- On a stale replay you could **not** fix this run, return the existing block
  unchanged except `Stale: 1` (or omit `playbook.scenario` and let the
  orchestrator bump it — either is fine, the orchestrator owns the counter).
