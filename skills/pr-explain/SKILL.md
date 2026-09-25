---
name: pr-explain
description: Open a herdr tab where a fresh Claude session triages a PR and explains its held thread in plain words.
argument-hint: "[PR…]"
disable-model-invocation: true
---

# PR explain

A held thread asks the author a question that reads as noise outside the PR's context. The
**explainer tab** is a fresh Claude session, in a herdr tab of this workspace, that rebuilds that
context: it runs `/pr-feedback <n>`, then `/explain-plainly` on the open thread and the fixes it
would suggest. The thread is read in the explainer tab, so this session only relays one line per PR
and its context stays clean — the reason it is safe to run from the babysit-prs manager.

## 1. Resolve

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/pr-explain/scripts/pr-explain.sh}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/pr-explain/scripts/pr-explain.sh 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/pr-explain/scripts/pr-explain.sh"; do
  [ -n "$c" ] && [ -f "$c" ] && EXPLAIN="$c" && break
done
```

**Done when** `$EXPLAIN` names a file that exists.

## 2. Launch

Append it to step 1's Bash call (shell variables do not survive between calls), run from this
session's cwd — the explainer tab opens in that checkout:

```bash
bash "$EXPLAIN" $ARGUMENTS
```

No argument takes every PR the scan reports as held. The script returns in seconds; the explainer
tab keeps working on its own, reusing an idle shell tab of this repo or opening a new one, and
leaves focus where it is.

**Done when** the script has exited and printed one line per PR.

## 3. Relay

Reply with the script's lines as printed, then end the turn. The explainer tab signals it is ready
with a herdr notification and its Done badge.
