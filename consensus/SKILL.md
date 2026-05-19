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

## Step 2: Build the pass prompt

The prompt sent to the executing agent on each pass MUST be assembled in the order below — **static blocks first, dynamic blocks last** — so prompt caching kicks in across the 3 passes.

**Static blocks** (identical across all passes):

1. Role: "You are running pass `<i>` of `<N>` for a self-consistency consensus task. On each pass, reason about the input from scratch. Do NOT reference earlier passes. Convergence on the same finding across passes is a positive signal — copying for consistency is not the goal."
2. The user's `<prompt>` verbatim.
3. The required JSON schema (from cache).
4. Strict instruction: "Output ONLY a JSON object/array matching the schema. No prose, no markdown fences, no preamble."

**Dynamic block** (changes per pass — small, kept last to preserve cache prefix):

5. `Pass index: <i>/<N>` — only the index varies between passes.

The input data is **inside the user's prompt** (we use inline mode — see decision log). Reviewers don't need a separate `<input>` block.

## Step 3: Execute N passes (serial, single agent)

Run a loop of `N` passes from a single execution context. Do NOT spawn N agents. Do NOT use TeamCreate.

For each pass `i` in `1..N`:

1. Send the prompt with the dynamic `Pass index: i/N` line.
2. Capture the response.
3. Try `json.loads` on the response.
4. Validate against the schema (required fields present, enums respected).
5. If valid → write to `/tmp/consensus-pass-<i>.json`.
6. If invalid → retry the pass once (re-send same prompt). If still invalid → mark this pass as `failed`, log the reason, and continue. Do NOT abort the run.

Track a list `failed_passes: [{index, reason}]`.

After all passes: if **all** passes failed, abort with an error. Otherwise continue with the valid subset.

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
- **Why serial passes, not parallel**: aligns with `gate`, maximizes prompt caching across passes (~95% prefix shared), avoids dependency on Agent Teams.
- **Why deterministic vote**: the whole point of self-consistency is turning N noisy samples into a stable answer. A LLM-judge consolidator would reintroduce the variance.
- **Reference**: Wang et al., 2022 — "Self-Consistency Improves Chain of Thought Reasoning in Language Models" (https://arxiv.org/abs/2203.11171).
