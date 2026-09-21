---
name: jev-verify
description: This skill should be used to measure whether TypeSafe's Jev model can replace gate-wf's sonnet skeptics in the Verify phase. Replays findings from gate-wf state files against Jev — one request per finding, four typed questions — and reports where the two disagree, plus cost and latency for both paths. Read-only; never modifies gate-wf or its state. Triggers on "/jev-verify", "compare jev against the gate", "can jev replace the skeptics", "calibrate jev thresholds".
argument-hint: "[run|corpus|calibrate] [--no-call] [--synthetic] [--limit N]"
---

# jev-verify — Jev against gate-wf's skeptics

This skill **measures**; it does not replace anything. It runs beside `gate-wf`, reads its state
files, and writes only under `~/.claude/jev-verify/`. No file under `skills/gate-wf/` is touched.

## Why

`gate-wf` spends one sonnet subagent per skeptic vote — 3 per BLOCKER, 1 per MAJOR, ≤6 tool calls
each — to turn an already-investigated finding into a boolean. Jev answers that shape of question
in ~100 ms for **$0.042 per million input tokens** (output free), and returns a calibrated
probability instead of a 3-vote quorum that exists only to smooth one agent's noise.

Whether it answers it *well* is an open question. This skill produces the numbers.

## Prerequisites

- **`TYPESAFE_API_KEY`** in the environment. Get one at <https://console.typesafe.ai/>, then
  `export TYPESAFE_API_KEY=...`. Not needed for `--no-call`.
- **A prior `gate-wf` run.** `run` reads this branch's state file; `corpus` reads every state file
  for the current repo. The skill never launches the gate.
- Python 3, stdlib only. No SDK, no pip install.

## Resolve the script

```bash
JV=""
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/jev-verify/scripts/jev_verify.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/jev-verify/scripts/jev_verify.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/jev-verify/scripts/jev_verify.py"; do
  [ -n "$c" ] && [ -f "$c" ] && JV="$c" && break
done
[ -z "$JV" ] && { echo "jev-verify: jev_verify.py not found — reinstall the plugin" >&2; exit 2; }
```

## Commands

```bash
python3 "$JV" run [--no-call] [--json] [--synthetic]
python3 "$JV" corpus [--limit N] [--synthetic]
python3 "$JV" calibrate
jev_verify.py batch [--repo <root>]   # gate-wf --jev: findings on stdin
python3 "$JV" --self-check
```

| Command | What it does |
| --- | --- |
| `run` | This branch's last gate-wf findings. The everyday mode. Exits 1 with gate-wf's own message when there is no prior run. |
| `run --no-call` | Prints the exact Jev payloads and hits no network. Use it first — it is how you check the code slice actually contains the cited line before spending anything. |
| `corpus` | Every gate-wf state file for the current repo. This is the calibration mode. Branches whose recorded commit is gone from the repo are skipped and counted. |
| `preflight` | One ~300-token call (~$0.00001). The API exposes no balance or quota endpoint — only `/v1/systemone` — so a served call is the only proof of credit. Exit 1 with the exact reason (401 / 429 / network) on failure. gate-wf's `--jev` runs this before its reviewers spawn. |
| `calibrate` | Threshold sweep over everything accumulated under `~/.claude/jev-verify/<repo-slug>/`. |
| `--synthetic` | Also scores deliberately-broken copies of each finding (re-anchored past the window). Sensitivity floor — see **The bias** below. |
| `batch` | The gate-wf `--jev` contract: findings array on stdin, one JSON object `{rows, usage}` on stdout. Each row carries `decision` (`keep`/`kill`/`escalate`), `defect_real`, `needs_wider_context` and a `msg_len` the caller checks against its own finding. **Every failure — API down, unreadable file, no message — routes to `escalate`**, so the caller's fallback is a sonnet skeptic and no finding is ever lost. |

Run from inside the repo. The state directory is keyed on a one-way hash of the repo root, so
`corpus` can only see the repo you are standing in.

## What it asks Jev

One request per finding, four independent questions over the same state — they evaluate in
parallel and the input is billed once.

`state` = `{file, line, code, finding: {rule_id, message, evidence, suggested_fix}, rule_citation?}`
where `code` is a numbered ±40-line window with the cited line marked `>`.

| Question | Type | Role |
| --- | --- | --- |
| `defect_real` | Noul | Does the defect occur in the code shown? → replaces the skeptic's vote |
| `severity` | Score `NIT / MAJOR / BLOCKER` | Severity made comparable across the 6 reviewers |
| `fix_addresses` | Noul | Would `suggested_fix` actually remove the defect? |
| `needs_wider_context` | Noul | Is code outside the window required to decide? |

The wordings live in `scripts/questions.json`. **Retune them there, not in the code** — when
agreement plateaus low, the criteria are the problem, not the pipeline.

Two things happen before Jev is asked anything:

- **Quote check, zero tokens.** A report flag, never a kill signal. `evidence` turns out not to be
  a quote field: two thirds of it is prose with no code in it, and what is quoted is routinely
  abridged (`` `if (x) { ... }` ``). So the check pulls the backticked spans, splits them at the
  ellipsis, and looks for the fragments. Verdicts: `no-quote` (the common case, says nothing),
  `all`, `some`, `none`, and `off-anchor` — the code exists but not where the finding says it
  does, which is the one genuinely useful one. The finding goes to Jev either way.
- **Citation asymmetry.** `agents/skeptic.md` holds that a finding quoting a project rule is
  refutable three ways only. That is enforced in code, not prompt: a cited finding dies below
  `0.10` where an uncited one dies below `0.30`.

Thresholds (`KILL_BELOW=0.50`, `KEEP_ABOVE=0.70`, `KILL_BELOW_CITED=0.10`) come from the
corpus calibration below; `calibrate` re-derives them from newer runs: it prints both error curves against the kill
threshold — real findings kept (the sonnet skeptics kept them too) and planted findings killed —
and names where the worst of the two peaks.

## First results

One run over 125 judgeable findings from 36 gate-wf state files on a real repo, with the planted
control:

```
thresh   real kept    planted killed
0.30      98.4%         66.4%
0.45      91.2%         90.4%   <- balanced
0.70      62.4%         99.2%
```

252 requests, 511k input tokens, **$0.021, 28s** — against 186 sonnet skeptic subagents at ≤6 tool
calls each for the same findings. `defect_real` separates cleanly (mean 0.74 real vs 0.21 planted).

Two caveats that did not clear: the per-vote signal is still thin (only 4 findings on record had a
skeptic vote refute, mean 0.72 against 0.80 for the rest — no conclusion), and `needs_wider_context`
still fires on 70% of findings at ±80, which says the window is not the constraint — doubling it
moved the flag by 6 points only.

**Window size, A/B'd on the identical corpus** (`JEV_RADIUS`, default 40):

| | ±40 | ±80 |
| --- | --- | --- |
| balanced threshold | 0.45 (90%) | **0.50 (92%)** |
| real kept / planted killed at balance | 91.2% / 90.4% | 92.8% / 91.2% |
| needs_wider_context ≥ 0.5 | 76% | 70% |
| corpus cost | 511k tok, $0.021 | 663k tok, $0.028 |

±80 wins on every axis but by ~1.5 points for +30% tokens. Take ±80 at these prices; revisit only
if the corpus grows 10×.

## The bias you must not forget

**gate-wf discards refuted findings**, so every finding on disk is one the skeptics *kept*. The
corpus therefore measures one direction: *does Jev keep what sonnet kept?* — the false-negative
risk. It cannot measure whether Jev kills what sonnet killed.

`--synthetic` is the substitute: re-anchor each survivor 100 lines away, where the code has nothing
to do with the finding, and check Jev scores it lower. Not recall — a sensitivity floor. Without it
you cannot tell `defect_real` from a function that returns `true`.

**The shift must exceed twice the window radius.** The first version moved the line by 15 against a
±40 window: the mutated slice overlapped the original by 80%, Jev was shown almost the same code,
and the gap came out at 0.06 — which reads as "the model cannot tell real findings from planted
ones" when it actually measured the control. With a disjoint window the same corpus gives 0.74 vs
0.21. If you retune `RADIUS`, retune `SHIFT` with it.

The report also splits the real findings by whether any skeptic voted refute. If Jev's mean is
lower on those, it is tracking the same signal sonnet was.

## Known limits

- **One file per finding.** A cross-file finding (`bug-cross-file-parity`) only sees its anchor
  line's window. `needs_wider_context` measures how often that bites instead of guessing.
- Jev has no tools. The classic skeptic refutation "already validated upstream" needs a caller Jev
  cannot go read. That is the real fidelity gap, and the escalate band exists for it.
- `corpus` is bounded by what git still has. Merged-and-deleted branches whose commit was garbage
  collected are skipped, not faked.

## Self-check

```bash
python3 skills/jev-verify/scripts/test_jev_verify.py
```

Offline, no network: slice extraction, the evidence grep, the worktree/git-blob fallback,
state-file discovery, threshold math, and a full `run --no-call` in a throwaway repo.
