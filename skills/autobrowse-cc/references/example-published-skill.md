This is a template for the SKILL.md you write to `~/.claude/skills/<task>/SKILL.md`
when a task graduates. It must be SELF-CONTAINED — a fresh agent should reproduce the
task from this file alone, without the workspace, strategy.md, or this skill. Synthesize
it from the winning strategy.md plus the working step sequence; do not raw-copy strategy.md.

---
name: <task>
description: Reliably <do the task> on <site> via local isolated Chrome (chrome-cdp). Use when asked to <trigger phrasing>.
---

# <Task> Navigation

Drive an isolated Chrome via the chrome-cdp `cdp.mjs` CLI. Launch with
`chrome-debug.sh`, prefix calls with `CDP_PORT_FILE="$HOME/.chrome-debug-profile/DevToolsActivePort"`.

## Fast path
Direct URL / shortcut that skips exploration:
- Navigate straight to `<deep-url>` instead of the landing page.

## Workflow
Exact sequence with the timing/selectors that proved stable:
1. `cdp.mjs nav <target> <url>`
2. `cdp.mjs snap <target>` — wait for `<stable element>` to appear (≈Nms).
3. `cdp.mjs click <target> "<selector>"`
4. ... (one verified step per line)
N. Verify success condition: `<what to read and what value means done>`.

## Site-specific knowledge
- Stable selectors: `#id`, `[name=...]` ...
- Success indicator: `<exact text / element>`
- Gotchas: spinner delays, dropdowns needing a re-snap, cross-origin iframes (use `type`).

## Failure recovery
- If <symptom>: <recovery step>.

## Output
```json
{ "success": true, "confirmation": "<proof>", "error_reasoning": null }
```
