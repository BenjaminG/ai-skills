---
name: chrome-cdp
description: Interact with a local Chrome browser session via Chrome DevTools Protocol (only on explicit user approval after being asked to inspect, debug, or interact with a page open in Chrome). Pass `--isolated` to drive a sandboxed Chrome with a dedicated profile instead of the user's real browser.
argument-hint: "[--isolated]"
---

# Chrome CDP

Lightweight Chrome DevTools Protocol CLI. Connects directly via WebSocket — no Puppeteer, works with 100+ tabs, instant connection.

## Modes

### Default — connect to the user's real Chrome

When invoked without flags, `scripts/cdp.mjs` auto-discovers the running Chrome instance from the standard profile location (`~/Library/Application Support/Google/Chrome/...` on macOS, `~/.config/google-chrome/...` on Linux, `%LOCALAPPDATA%\Google\Chrome\User Data\...` on Windows). Remote debugging must be enabled in the user's Chrome (toggle once at `chrome://inspect/#remote-debugging`).

Use this mode when the user wants to inspect a page they already have open.

### `--isolated` — sandboxed Chrome with a dedicated profile

When the user passes `--isolated`, drive a separate Chrome instance using `--user-data-dir=$HOME/.chrome-debug-profile` and `--remote-debugging-port=9222`. The user's real Chrome profile is untouched (no extensions, no logins, no cookies leak in either direction).

Two-step protocol for every `--isolated` invocation:

1. Run the launcher (idempotent — exits fast if the sandboxed Chrome is already up):
   ```bash
   scripts/chrome-debug.sh
   ```
2. Run any `cdp.mjs` command with `CDP_PORT_FILE` pointing at the isolated profile, e.g.:
   ```bash
   CDP_PORT_FILE="$HOME/.chrome-debug-profile/DevToolsActivePort" scripts/cdp.mjs list
   CDP_PORT_FILE="$HOME/.chrome-debug-profile/DevToolsActivePort" scripts/cdp.mjs shot <target>
   ```

The env var overrides auto-discovery (see `getWsUrl()` in `scripts/cdp.mjs`), forcing the connection to the sandboxed instance. Without the env var, the same `cdp.mjs` would connect to the user's real Chrome.

Both scripts are referenced relative to the skill directory — Claude Code resolves them against the skill's root.

## Argument parsing

Before running any command, scan the user's request for `--isolated`:

- Present → follow the **Isolated** protocol above for every `cdp.mjs` call in this turn.
- Absent → call `scripts/cdp.mjs <command>` directly without the env var.

Never silently pick isolated mode. If the user says "screenshot tab X", that's default mode. If they say "use a clean profile", "don't touch my Chrome", or pass `--isolated`, that's isolated mode. When ambiguous, ask.

## Prerequisites

- Node.js 22+ (uses built-in WebSocket).
- For default mode: enable remote debugging once at `chrome://inspect/#remote-debugging` in the user's Chrome.
- For `--isolated`: nothing — `scripts/chrome-debug.sh` will launch Chrome on demand.

## Commands

All commands use `scripts/cdp.mjs`. The `<target>` is a **unique** targetId prefix from `list`; copy the full prefix shown in the `list` output (for example `6BE827FA`). The CLI rejects ambiguous prefixes.

### List open pages

```bash
scripts/cdp.mjs list
```

### Take a screenshot

```bash
scripts/cdp.mjs shot <target> [file]    # default: screenshot-<target>.png in runtime dir
```

Captures the **viewport only**. Scroll first with `eval` if you need content below the fold. Output includes the page's DPR and coordinate conversion hint (see **Coordinates** below).

### Accessibility tree snapshot

```bash
scripts/cdp.mjs snap <target>
```

### Evaluate JavaScript

```bash
scripts/cdp.mjs eval <target> <expr>
```

> **Watch out:** avoid index-based selection (`querySelectorAll(...)[i]`) across multiple `eval` calls when the DOM can change between them (e.g. after clicking Ignore, card indices shift). Collect all data in one `eval` or use stable selectors.

### Other commands

```bash
scripts/cdp.mjs html    <target> [selector]   # full page or element HTML
scripts/cdp.mjs nav     <target> <url>         # navigate and wait for load
scripts/cdp.mjs net     <target>               # resource timing entries
scripts/cdp.mjs click   <target> <selector>    # click element by CSS selector
scripts/cdp.mjs clickxy <target> <x> <y>       # click at CSS pixel coords
scripts/cdp.mjs type    <target> <text>         # Input.insertText at current focus; works in cross-origin iframes unlike eval
scripts/cdp.mjs loadall <target> <selector> [ms]  # click "load more" until gone (default 1500ms between clicks)
scripts/cdp.mjs evalraw <target> <method> [json]  # raw CDP command passthrough
scripts/cdp.mjs open    [url]                  # open new tab (each triggers Allow prompt)
scripts/cdp.mjs stop    [target]               # stop daemon(s)
```

### Jev judgments — `pick` and `verify`

Fast typed judgments via TypeSafe's Jev (`~$0.00006/call`, ~1s latency) instead of reading a full `snap` into context. Both need `TYPESAFE_API_KEY` (console.typesafe.ai). Neither command acts on the page — `pick` returns a selector for the caller to `click`, `verify` returns a verdict for the caller to record.

```bash
scripts/cdp.mjs pick   <target> <intent>   # which element matches the intent?
scripts/cdp.mjs verify <target> <claim>    # does the tree show the claimed state?
```

- `pick` harvests interactive elements in code, registers them as Choice options (the model cannot invent a selector that isn't on the page), and prints `pick <selector> (confidence …)` plus the next command to run. Below the confidence gate it prints `escalate` and exits **3** — snap and choose the element yourself.
- `verify` asks a Noul over the a11y tree and prints `pass` / `fail` / `escalate` (uncertain band), exiting 0 / 0 / 3.
- Tunables: `CDP_JEV_MIN_CONF` (default 0.6), `CDP_JEV_PASS_AT` (0.8), `CDP_JEV_FAIL_AT` (0.2).
- **Verify after the page settles** — `verify` has no wait. Right after a click, poll first (e.g. `eval` with `awaitPromise`) or the judgment runs on the pre-render tree. A `fail` right after an action usually means "too early", not "wrong state" — re-run once.
- Measured on the replay corpus in `evals/jev-chrome-cdp/`: pick 100% precision at conf ≥ 0.6 (10/10 acted); verify 18/19 correct, 0 false-pass. Corpus is login-heavy — treat dense-page picks with the same escalation discipline.

## Coordinates

`shot` saves an image at native resolution: image pixels = CSS pixels × DPR. CDP Input events (`clickxy` etc.) take **CSS pixels**.

```
CSS px = screenshot image px / DPR
```

`shot` prints the DPR for the current page. Typical Retina (DPR=2): divide screenshot coords by 2.

## Tips

- Prefer `snap` over `html` for page structure — the daemon always returns it compact.
- Use `type` (not eval) to enter text in cross-origin iframes — `click`/`clickxy` to focus first, then `type`.
- Chrome shows an "Allow debugging" modal once per tab on first access. A background daemon keeps the session alive so subsequent commands need no further approval. Daemons auto-exit after 20 minutes of inactivity.
- In `--isolated` mode the sandboxed Chrome starts with no extensions, no logins, and a blank profile. Re-launching it (`scripts/chrome-debug.sh`) is a no-op while it's running.
- **Batching:** because the daemon holds the session open, chaining several `cdp.mjs` calls with `&&` in one Bash call is already a batch — `click` throws when its selector is missing, so a bad step stops the chain instead of mis-clicking the next one. There's no wait command; poll for a post-action element with `eval`'s `awaitPromise: true` support instead of a fixed `sleep`.
