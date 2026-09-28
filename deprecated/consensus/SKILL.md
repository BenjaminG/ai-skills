---
name: consensus
description: Run a structured prompt N times and consolidate via deterministic vote (self-consistency, Wang et al. 2022). Use when output stability matters more than latency — code review, finding extraction, classification, triage. Triggers on "self-consistency", "consensus", "vote on", "stable output", "run N times and merge".
argument-hint: "<prompt> [--passes N] [--threshold M] [--force-fresh]"
---

# consensus

Apply self-consistency to a structured prompt: run it N times, parse each output as JSON, fuzzy-match findings across passes, keep only what converges.

The vote is **deterministic** — a Python script consolidates the JSON outputs without any LLM judge. The schema and vote key are agreed upfront and cached, so repeat invocations on the same prompt skip the schema-design step.

## Arguments

- `<prompt>` (positional, required): the structured prompt. Must describe a task whose output can be a JSON list/object (findings, extractions, classifications). Free-form text generation is **not supported** — the vote needs structure.
- `--passes N` (optional, default `3`): how many times to run the prompt. Must be ≥2.
- `--threshold M` (optional, default `ceil(N/2)`): minimum votes for a finding to be retained. Must satisfy `1 ≤ M ≤ N`.
- `--force-fresh` (optional flag): bypass the schema cache and re-derive the schema from scratch.

## Step 0: Validate inputs

```bash
PASSES=${PASSES:-3}
THRESHOLD=${THRESHOLD:-$(( (PASSES + 1) / 2 ))}

[ "$PASSES" -lt 2 ] && { echo "--passes must be ≥2 (got $PASSES)"; exit 2; }
[ "$THRESHOLD" -lt 1 ] || [ "$THRESHOLD" -gt "$PASSES" ] && { echo "--threshold must be in [1, $PASSES] (got $THRESHOLD)"; exit 2; }
```

If `<prompt>` is empty, abort with a usage message.

## Step 1: Resolve schema (with cache)

### 1a. Compute prompt hash

```bash
PROMPT_HASH=$(echo -n "$PROMPT" | shasum | cut -c1-16)
CACHE_DIR="$HOME/.claude/consensus-cache"
CACHE_FILE="$CACHE_DIR/${PROMPT_HASH}.yaml"
mkdir -p "$CACHE_DIR"
```

### 1b. Cache lookup

If `--force-fresh` is NOT set and `$CACHE_FILE` exists, load it. Skip to Step 2.

The cache file contains:

```yaml
prompt_hash: <hash>
prompt: <verbatim prompt>
template: finding-list | extraction | classification | generic-structured
schema:
  # JSON schema for each pass output
  type: array
  items:
    type: object
    properties: { ... }
    required: [ ... ]
vote_key:
  fields: [field1, field2, ...]   # exact-match fields
  numeric_tolerance:               # optional, only for numeric fields
    line: 5                        # ±5 line match
```

### 1c. Cache miss — derive schema

Read the four templates in `templates/`:

- `templates/finding-list.md` — issues at coordinates (file, line, rule_id)
- `templates/extraction.md` — typed values pulled from input
- `templates/classification.md` — labels with optional confidence
- `templates/generic-structured.md` — fallback for everything else

For each template, evaluate "does the user's prompt match this template's shape?" by checking:

1. Does the prompt ask for a **list of items** (finding-list, extraction) or a **single label** (classification)?
2. Do the items have **coordinates** (file/line) → finding-list. Or **typed values** → extraction. Or no list at all → classification.
3. If unsure, fall back to `generic-structured`.

Pick the best-matching template. Adapt its schema to the prompt — for example:

- `finding-list` for SQL injection: `rule_id` enum becomes `[sql-string-concat, sql-template-literal, sql-other]`
- `extraction` for ticket parsing: types become the entities the prompt asks for (`person`, `date`, `system`)
- `classification` for triage: labels become the categories the prompt names (`bug`, `feature`, `question`)

### 1d. Confirm with user

Present the derived schema using `AskUserQuestion`:

```
Matched template: <template_name>
Proposed schema:
  <schema in concise form>
Vote key: <fields> [+ numeric tolerance if any]

[Accept / Edit / Cancel]
```

- **Accept** → write `$CACHE_FILE`, continue to Step 2.
- **Edit** → ask the user what to change, regenerate, re-confirm.
- **Cancel** → exit cleanly.

The cache is **only** written after Accept. An edited-then-accepted schema is also cached.

## Step 2: Build the per-pass prompt

Each pass runs in an **independent sub-agent** (Step 3) — the lead does NOT execute the prompt itself. This independence is load-bearing: it preserves the statistical assumption behind self-consistency (Wang et al. 2022 samples are i.i.d.). A serial loop in the lead's own context would let pass 2/3 see pass 1's output and bias toward repetition.

The prompt sent to **each** sub-agent is identical except for the `Pass index` field. Build it from these blocks:

1. Role: "You are an isolated worker for a self-consistency consensus task. You will see ONLY the prompt and the schema. You do NOT have access to other passes' outputs. Reason about the input from scratch and produce your best answer."
2. The user's `<prompt>` verbatim.
3. The required JSON schema (from cache).
4. Strict instruction: "Output ONLY a JSON object/array matching the schema. No prose, no markdown fences, no preamble."
5. `Pass index: <i>/<N>` — for traceability only; does not change the task.
6. Output instruction: "Write your JSON output to `/tmp/consensus-pass-<i>.json`. Do not write anything else to the conversation."

The input data is **inside the user's prompt** (we use inline mode — see decision log). Sub-agents don't need a separate `<input>` block.

## Step 3: Execute N passes in parallel (independent sub-agents)

**Spawn N independent sub-agents in a single message** using the `Agent` tool. Do NOT loop in the lead's context. Do NOT use `TeamCreate` (no need for inter-agent messaging — sub-agents are fully isolated).

For each pass `i` in `1..N`, prepare an `Agent` call with:

- **subagent_type**: `general-purpose`
- **description**: `consensus pass <i>/<N>`
- **prompt**: the full per-pass prompt from Step 2, with `<i>` substituted

Send all N `Agent` calls in **one assistant message** so they run concurrently (parallel sub-agents). Each sub-agent:

1. Receives only its prompt — has zero visibility into the other passes
2. Produces its JSON output
3. Writes it to `/tmp/consensus-pass-<i>.json`
4. Returns a brief completion notification to the lead

After all N notifications arrive, the lead validates each `/tmp/consensus-pass-<i>.json`:

1. Load the file. If missing → mark pass as `failed` (sub-agent returned nothing parseable).
2. `json.loads` the content.
3. Validate against the schema (required fields present, enums respected).
4. If invalid → re-spawn a single replacement sub-agent for that pass (one retry max). If retry also fails → mark `failed`, continue.

Track a list `failed_passes: [{index, reason}]`.

After validation: if **all** passes failed, abort with an error. Otherwise continue with the valid subset.

**Why parallel sub-agents, not a serial loop**: in a serial loop, pass 2's context window contains pass 1's full output. Auto-regressive models attend to that prior output and disproportionately repeat it — producing artificially inflated convergence ("agreement within a conversation") instead of independent samples. Parallel sub-agents recover the i.i.d. property the technique requires. Cost: each sub-agent pays the prompt input once (no shared cache across sub-agents), so input cost is roughly N× a single-pass prompt. For typical consensus prompts (a few KB) this is negligible compared to the integrity gain.

## Step 4: Vote (deterministic)

Invoke the vote script:

```bash
python3 ~/.claude/skills/consensus/scripts/vote.py \
  --schema "$CACHE_FILE" \
  --threshold "$THRESHOLD" \
  --passes /tmp/consensus-pass-*.json \
  --output "/tmp/consensus-result-$(date +%s).json"
```

The script:
1. Loads each pass's JSON.
2. For finding-list / extraction templates: groups items by `vote_key` (exact match on string fields, ±tolerance on numeric fields).
3. For classification templates: tallies the single `label` value across passes.
4. Keeps groups with `count >= threshold`.
5. Emits both the **consensus list** and the **divergences** (items below threshold).
6. Writes the consolidated result to `--output`.

The script is fully deterministic — no LLM call, no randomness, no network.

## Step 5: Render report

Read the consolidated JSON. Display:

```
## Consensus (votes ≥ M/N)

<rendered consensus items grouped sensibly — by file for finding-list, by type for extraction, single label for classification>

## Divergences (below threshold — dropped)

<one-line summary per item: "appeared in <k>/<N> passes — see result.json for details">

## Run metadata

- Passes: <valid>/<N> succeeded
- Failed passes: <list of indices and reasons, if any>
- Threshold: ≥<M>
- Result JSON: /tmp/consensus-result-<timestamp>.json
```

If `failed_passes` is non-empty, show a warning: `⚠️ <k>/<N> passes failed — convergence may be degraded. Re-run with --force-fresh or higher --passes if results look unstable.`

## Step 6: Cleanup

```bash
rm -f /tmp/consensus-pass-*.json
# Keep /tmp/consensus-result-*.json for downstream skills to consume.
```

## Notes

- **No auto-fix, no auto-action**: this skill returns consensus, full stop. Apply, triage, or follow-up actions are out of scope.
- **Composable**: the result JSON path is stable (`/tmp/consensus-result-<timestamp>.json`) so other skills can chain off of it.
- **Cache invalidation**: edit the prompt → new hash → cache miss → schema redesign. Use `--force-fresh` to redesign the schema for an unchanged prompt.
- **Why parallel sub-agents, not a serial loop**: serial passes in the lead's context break the i.i.d. assumption that makes self-consistency informative — pass `i+1` sees pass `i`'s output and the model's auto-regressive bias inflates apparent convergence. Independent sub-agents preserve true sampling. Cost trade-off: ~N× prompt input vs serial (no shared cache), accepted to keep the technique honest.
- **Why deterministic vote**: the whole point of self-consistency is turning N noisy samples into a stable answer. A LLM-judge consolidator would reintroduce the variance.
- **Reference**: Wang et al., 2022 — "Self-Consistency Improves Chain of Thought Reasoning in Language Models" (https://arxiv.org/abs/2203.11171).
