#!/usr/bin/env bash
# chrome-debug.sh — launch an isolated Chrome instance for CDP usage.
#
# Uses a dedicated user-data-dir (~/.chrome-debug-profile) so the debugger
# session never touches your real Chrome profile. Idempotent: if the instance
# is already running, it's a no-op.

set -euo pipefail

PROFILE_DIR="${CHROME_DEBUG_PROFILE_DIR:-$HOME/.chrome-debug-profile}"
PORT="${CHROME_DEBUG_PORT:-9222}"
PORT_FILE="$PROFILE_DIR/DevToolsActivePort"

mkdir -p "$PROFILE_DIR"

is_running() {
  pgrep -f "remote-debugging-port=$PORT.*user-data-dir=$PROFILE_DIR" >/dev/null 2>&1 \
    || pgrep -f "user-data-dir=$PROFILE_DIR.*remote-debugging-port=$PORT" >/dev/null 2>&1
}

ALREADY_RUNNING=0
if is_running; then
  ALREADY_RUNNING=1
  echo "chrome-debug: already running (port $PORT, profile $PROFILE_DIR)"
else
  echo "chrome-debug: launching isolated Chrome..."
  open -na "Google Chrome" --args \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check
fi

# Wait for the CDP endpoint to respond, then synthesize the port file.
# Chrome doesn't always write DevToolsActivePort when the port is fixed
# (--remote-debugging-port=<n>), so we build it from /json/version ourselves.
WS_URL=""
for _ in $(seq 1 50); do
  WS_URL=$(curl -fsS "http://127.0.0.1:$PORT/json/version" 2>/dev/null \
    | /usr/bin/python3 -c 'import sys,json;print(json.load(sys.stdin).get("webSocketDebuggerUrl",""))' 2>/dev/null || true)
  [ -n "$WS_URL" ] && break
  sleep 0.1
done

if [ -z "$WS_URL" ]; then
  echo "chrome-debug: CDP endpoint http://127.0.0.1:$PORT did not come up" >&2
  exit 1
fi

# webSocketDebuggerUrl = ws://host:port/devtools/browser/<uuid>
# DevToolsActivePort format expected by cdp.mjs:
#   line 1: port
#   line 2: /devtools/browser/<uuid>
WS_PATH="/${WS_URL#*://*/}"
printf '%s\n%s\n' "$PORT" "$WS_PATH" > "$PORT_FILE"
echo "chrome-debug: ready (DevToolsActivePort -> $PORT_FILE)"
