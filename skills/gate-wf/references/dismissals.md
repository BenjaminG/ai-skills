# Dismissals — durable false-positive suppression

The findings cache (`$STATE_FILE`) is keyed on `CACHE_KEY`, which includes `WT_HASH` — so it is invalidated by design on every diff change. That is correct for a *result* cache, but it means a finding the author judged a false-positive on diff N is re-discovered and re-reported on diff N+1 (the code is unchanged, so reviewers re-flag it), and `pr-comment` re-posts it. Indefinitely.

This file specifies the **dismissal registry**: a small per-branch store, kept **outside `CACHE_KEY`**, that records "this finding was rejected" with a **content-stable identity** so the suppression survives diff churn but lifts automatically if the offending code is actually changed.

A dismissed finding is **excluded from `findings[]`** (so `pr-comment`, which reads `.findings[]`, never re-posts it) and from the tier counts (so it never re-FAILs the gate), but is always shown in a `Dismissed (N)` section with its citation — suppressed, never hidden.

---

## Registry file

`$DISMISS_FILE = $STATE_DIR/${BRANCH_SAFE}.dismissed.json` (alongside `$STATE_FILE`, **not** part of `CACHE_KEY`).

```json
{
  "version": 1,
  "dismissals": [
    {
      "anchor": "<12-char sha — content identity>",
      "rule_id": "security-sql-injection",
      "file": "src/db/users.ts",
      "anchor_text": "db.query('SELECT * FROM users WHERE id = ' + id)",
      "source": "pr-thread | manual",
      "confidence": "resolved | rebutted | manual",
      "citation": "PR thread resolved by @author: \"id is validated upstream\"",
      "dismissed_at": "2026-06-30T10:00:00Z"
    }
  ]
}
```

A missing file means an empty registry (`{"version":1,"dismissals":[]}`).

---

## Content-anchor — the identity that survives line drift

The key is **not** `(rule_id, file, line)` — the line drifts on every commit. It is **not** the reviewer's `evidence` string — that is non-reproducible LLM prose. It is `(rule_id, file, sha(normalized text of the anchor line read from disk))`:

```bash
# gatewf_anchor RULE_ID FILE LINE  → prints 12-char sha, or non-zero exit if the line is unreadable.
# Inline this where needed (bash functions do not persist across the skill's separate bash blocks).
gatewf_anchor() {
  local rule_id="$1" file="$2" line="$3" txt
  txt=$(sed -n "${line}p" -- "$REPO_ROOT/$file" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
  [ -z "$txt" ] && return 1
  printf '%s' "${rule_id}::${file}::${txt}" | shasum | cut -c1-12
}
```

Why this works:

- Read at render-time from the file at HEAD → **deterministic** (not the LLM paraphrase).
- Compares the **text**, not the position → survives line drift when surrounding code is added/removed.
- If the author later **edits the offending code** → the text changes → the anchor changes → the finding **reappears** (correct: it is no longer the same code, the dismissal should not carry over).
- `rule_id + file` scope it so a generic line (`return null;`) dismissed for one rule does not silence an unrelated finding on an identical line.

`// ponytail: single-line anchor; two identical lines in one file collide (both get dismissed together). Acceptable. Upgrade path: fold a small ±2-line window into the hash if collisions bite.`

---

## Auto-populate from PR review threads (cache-miss path only)

The context-checker (see `agents/context-checker.md`) emits, for any input finding that a resolved/rebutted PR review thread rejects, an annotation with `verdict: "DISMISSED"`, `dismiss_confidence: "resolved" | "rebutted"`, and `citation` (the thread text verbatim). This only happens on a full run (cache miss), when the bundle's `### Review threads` is fresh.

After the workflow returns, for each annotation with `verdict == "DISMISSED"`, find its finding (match on `rule_id + file + line`), compute its anchor, and **upsert** into the registry:

```bash
# Upsert one dismissal (dedupe by anchor). NEW=<one dismissal JSON object>
jq --argjson d "$NEW" '
  .dismissals |= ( map(select(.anchor != $d.anchor)) + [$d] )
' "$DISMISS_FILE" > "$DISMISS_FILE.tmp" && mv "$DISMISS_FILE.tmp" "$DISMISS_FILE"
```

`resolved` (thread closed) is a strong signal; `rebutted` (author contested but left the thread open) is weaker — both suppress, but the render labels `rebutted` so it reads as "author contested, thread still open", not a settled call.

---

## Render with dismissals (shared core — Step 4)

This partition runs in **every** path that produces output: fresh run, cache-hit replay, and after a manual flag. Input is the full finding set (fresh-run findings, or `.findings[] + .dismissed[]` from `$STATE_FILE` on replay — drop their old ids and re-partition):

1. Load the registry anchors: `jq -r '.dismissals[].anchor' "$DISMISS_FILE" 2>/dev/null` (empty if no file).
2. For each finding, compute `gatewf_anchor "$rule_id" "$file" "$line"`. If it is in the registry → **dismissed**; else → **active**. A finding whose anchor line is unreadable (file/line gone) is **active** (its absence means the code moved; let it surface).
3. **Verdict math (Step 4b) runs over `active` only.** Dismissed findings never count toward BLOCKER/MAJOR/NIT.
4. **IDs (Step 4c):** active → `B1/M1/N1…` as before; dismissed → `D1, D2, …` sorted by tier then `(file, line)`.
5. Persist (Step 5a): `$STATE_FILE` gets `findings: [active]` and `dismissed: [dismissed]` (each dismissed entry carries its full finding payload + `id` (`Dn`) + `anchor` + `source` + `confidence` + `citation`, so `--undismiss` can promote it back).

Render the `Dismissed` section after the active findings (omit if empty):

```
## Dismissed (suppressed — not counted toward the verdict)

### D1 — [security-reviewer] security-sql-injection
- `src/db/users.ts:42` · resolved · PR thread by @author
  was: User input concatenated into raw SQL query
  citation: "id is validated upstream — see middleware/auth.ts:30"
```

For `confidence: rebutted`, render `· rebutted (thread still open)` instead of `· resolved`.

Append to the closing tips:

```
Tip: a dismissed finding reappears automatically if its code is edited (the dismissal is keyed on the code, not the line).
Tip: --dismiss <ids> to suppress a false-positive; --undismiss <Dn> to bring one back; --show-dismissed to list them.
```

---

## Manual flags (replay path — no gate run)

These mutate the registry and re-render from `$STATE_FILE` — they do **not** invoke the workflow. They require a prior run (a `$STATE_FILE`); if absent, print `no prior gate-wf run on this branch — run the gate first` and exit.

- **`--dismiss <ids>`** (comma-separated active ids, e.g. `B1,M2`): for each id, look it up in `.findings[]`, compute its anchor, upsert with `source: "manual"`, `confidence: "manual"`, `citation: "manual dismissal"`. Then run the shared render core.

  ```bash
  jq -r --arg id "$ID" '.findings[] | select(.id==$id) | [.rule_id,.file,.line]|@tsv' "$STATE_FILE"
  # → feed into gatewf_anchor, build the dismissal object, upsert as above.
  ```

- **`--undismiss <ids>`** (comma-separated `Dn` ids): for each, resolve its `anchor` from `.dismissed[]`, remove it from the registry, then run the shared render core (the finding is promoted back into `active` and re-counted).

  ```bash
  ANCHOR=$(jq -r --arg id "$ID" '.dismissed[] | select(.id==$id) | .anchor' "$STATE_FILE")
  jq --arg a "$ANCHOR" '.dismissals |= map(select(.anchor != $a))' "$DISMISS_FILE" \
    > "$DISMISS_FILE.tmp" && mv "$DISMISS_FILE.tmp" "$DISMISS_FILE"
  ```

- **`--show-dismissed`** (flag): print the registry as a table (`rule_id`, `file`, `confidence`, `citation`, `dismissed_at`) and exit. No render, no run.

A manual `--dismiss` takes effect **instantly even on a cache hit**, because the registry is applied at render-time, independent of `CACHE_KEY`. Only detecting a *brand-new* PR-thread dismissal needs a full run (cache miss) so the context-checker can see the thread — which happens naturally on the next push.

---

## GC (Step 5c)

When the orphan-state GC removes a `$STATE_DIR/<branch>.json` whose branch no longer exists, remove the sibling `<branch>.dismissed.json` too (mirror the existing state-file cleanup).
