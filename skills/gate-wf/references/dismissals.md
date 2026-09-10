# Dismissals — durable false-positive suppression

The findings cache (`$STATE_FILE`) is keyed on `CACHE_KEY`, which includes `WT_HASH` — so it is invalidated by design on every diff change. That is correct for a *result* cache, but it means a finding the author judged a false-positive on diff N is re-discovered and re-reported on diff N+1 (the code is unchanged, so reviewers re-flag it), and `pr-comment` re-posts it. Indefinitely.

This file specifies the **dismissal registry**: a small per-branch store, kept **outside `CACHE_KEY`**, that records "this finding was rejected" with a **content-stable identity** so the suppression survives diff churn but lifts automatically if the offending code is actually changed.

A dismissed finding is **excluded from `findings[]`** (so `pr-comment`, which reads `.findings[]`, never re-posts it) and from the tier counts (so it never re-FAILs the gate), but is always shown — as a count in the terminal, in full in `report.md`. Suppressed, never hidden.

**Implementation**: `scripts/findings.py` (`anchor`, `partition`, `upsert_dismissal`, `remove_dismissal`) and the `render.py` subcommands. This file is the *why*; the code is the *how*. Nothing here is executed by hand.

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

A missing file means an empty registry.

---

## Content-anchor — the identity that survives line drift

The key is **not** `(rule_id, file, line)` — the line drifts on every commit. It is **not** the reviewer's `evidence` string — that is non-reproducible LLM prose. It is `sha(rule_id::file::normalized text of the anchor line read from disk at HEAD)`, first 12 chars — `findings.anchor()`.

Why this works:

- Read at render-time from the file at HEAD → **deterministic** (not the LLM paraphrase).
- Compares the **text**, not the position → survives line drift when surrounding code is added or removed.
- If the author later **edits the offending code** → the text changes → the anchor changes → the finding **reappears** (correct: it is no longer the same code, the dismissal should not carry over).
- `rule_id + file` scope it, so a generic line (`return null;`) dismissed for one rule does not silence an unrelated finding on an identical line.
- An unreadable line (file or line gone, blank line) yields no anchor and the finding stays **active** — its absence means the code moved; let it surface.

Whitespace is squeezed before hashing, byte-compatibly with the bash `gatewf_anchor` this replaced — `scripts/test_render.py::test_anchor_matches_bash` pins that against the original shell implementation, because a drift there would silently resurrect every dismissal ever recorded.

`# ponytail: single-line anchor; two identical lines in one file collide (both get dismissed together). Acceptable. Upgrade path: fold a ±2-line window into the hash if collisions bite.`

---

## Auto-populate from PR review threads

The context-checker (`agents/context-checker.md`) emits, for any input finding that a resolved/rebutted PR review thread rejects, an annotation with `verdict: "DISMISSED"`, `dismiss_confidence: "resolved" | "rebutted"`, and `citation` (the thread text verbatim). The workflow merges it back onto the finding.

`render.py ingest` upserts every such finding into the registry **before** partitioning, so the thread's rejection applies in the same render. This only happens on a full run (cache miss), when the bundle's `### Review threads` is fresh.

`resolved` (thread closed) is a strong signal; `rebutted` (author contested but left the thread open) is weaker — both suppress, but `report.md` labels `rebutted` so it reads as "author contested, thread still open", not a settled call.

---

## Render

The partition runs on **every** output path — fresh run, cache-hit replay, manual flag — because `ingest`, `show`, `dismiss` and `undismiss` all call the same `_repartition`. Input is `findings[] + dismissed[]` with ids dropped, so a dismissal added between two renders takes effect with no re-run.

Consequences, all handled in code:

- Verdict math and tier counts run over **active** only.
- Active findings get `B1/M1/N1…`; dismissed get `D1, D2, …`.
- `$STATE_FILE` is rewritten with the new partition, so `--undismiss` can promote a finding back and `pr-comment` never sees a suppressed one.
- The terminal shows `N dismissed` in the tally line and nothing more — you already arbitrated those. `report.md` carries the full section with each citation.

A manual `--dismiss` takes effect **instantly even on a cache hit**, because the registry is applied at render-time, independent of `CACHE_KEY`. Only detecting a *brand-new* PR-thread dismissal needs a full run so the context-checker can see the thread — which happens naturally on the next push.

---

## Manual flags (no gate run)

All three skip the workflow entirely and require a prior run on the branch (`render.py` exits non-zero with `no prior gate-wf run on this branch` otherwise):

```bash
python3 "$RENDER" dismiss B1,M2     # look up by rendered id, anchor, upsert as manual, re-render
python3 "$RENDER" undismiss D1      # drop the anchor from the registry, re-render (finding re-counts)
python3 "$RENDER" show-dismissed    # print the registry, no render
```

`dismiss`/`undismiss` re-render without an `En clair` summary — the finding set barely moved. To refresh it, run `brief` → write the summary → `show --summary-file`.

---

## GC (Step 5c)

When the orphan-state GC removes a `$STATE_DIR/<branch>.json` whose branch no longer exists, remove the sibling `<branch>.dismissed.json` and `<branch>.report.md` too.
