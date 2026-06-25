#!/usr/bin/env bash
# run-iteration.sh — run ONE inner-agent attempt at a browser task.
#
# The inner agent is a headless `claude -p` invocation scoped to Bash running
# only the chrome-cdp `cdp.mjs` driver. It reads task.md + strategy.md, drives an
# isolated Chrome, and prints a final JSON verdict. The stream-json transcript IS
# the trace the outer loop reads back.
#
# No ANTHROPIC_API_KEY: auth comes from the existing `claude` session/Bedrock setup.
#
# Usage: run-iteration.sh <task-name> [workspace] [run-number]
#   <task-name>   directory under <workspace>/tasks/
#   [workspace]   default ./autobrowse-cc
#   [run-number]  default = next free run-NNN

set -euo pipefail

TASK="${1:?usage: run-iteration.sh <task-name> [workspace] [run-number]}"
WORKSPACE="${2:-./autobrowse-cc}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CHROME_CDP_DIR="$(cd "$SKILL_DIR/../chrome-cdp" && pwd)"   # sibling skill
PORT_FILE="${CDP_PORT_FILE:-$HOME/.chrome-debug-profile/DevToolsActivePort}"

TASK_DIR="$WORKSPACE/tasks/$TASK"
TRACE_DIR="$WORKSPACE/traces/$TASK"
[ -f "$TASK_DIR/task.md" ] || { echo "missing $TASK_DIR/task.md" >&2; exit 2; }
touch "$TASK_DIR/strategy.md"
mkdir -p "$TRACE_DIR"

# Pick run number: explicit arg, else next free run-NNN.
if [ -n "${3:-}" ]; then
  RUN=$(printf '%03d' "$3")
else
  N=1
  while [ -e "$TRACE_DIR/run-$(printf '%03d' "$N").jsonl" ]; do N=$((N + 1)); done
  RUN=$(printf '%03d' "$N")
fi
TRACE="$TRACE_DIR/run-$RUN.jsonl"

# 1. Ensure isolated Chrome is up (idempotent).
"$CHROME_CDP_DIR/scripts/chrome-debug.sh" >&2

# 2. Compose the inner-agent prompt: rules + task spec + accumulated strategy.
PROMPT="$(cat "$SKILL_DIR/references/inner-agent-prompt.md")

The cdp.mjs driver lives at: $CHROME_CDP_DIR/scripts/cdp.mjs
Always prefix every cdp.mjs call with: CDP_PORT_FILE=\"$PORT_FILE\"

===== TASK =====
$(cat "$TASK_DIR/task.md")

===== STRATEGY (learned heuristics — follow these) =====
$(cat "$TASK_DIR/strategy.md")"

# 3. Run the inner agent, tee the stream-json transcript to the trace file.
echo "run-iteration: task=$TASK run=$RUN trace=$TRACE" >&2
set +e
claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  --allowed-tools "Bash" \
  --permission-mode acceptEdits \
  --add-dir "$CHROME_CDP_DIR" \
  | tee "$TRACE"
STATUS=${PIPESTATUS[0]}
set -e

ln -sfn "run-$RUN.jsonl" "$TRACE_DIR/latest.jsonl"

# 4. Extract the final result text (the inner agent's JSON verdict line).
VERDICT="$(jq -rs 'map(select(.type=="result")) | last | .result // empty' "$TRACE" 2>/dev/null || true)"
echo "===== VERDICT (run-$RUN) =====" >&2
echo "${VERDICT:-<no result line — claude -p exited $STATUS>}" >&2
echo "trace: $TRACE" >&2
exit "$STATUS"
