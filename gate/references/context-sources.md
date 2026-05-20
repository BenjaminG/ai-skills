# Context sources (Step 1f / Step 3g extensions)

This file specifies the discovery and freshness-probe logic for the two new context sources added in v3 — `claude_md` and the **applicability filter** for `adr` — and how they are consumed by the context-checker (Step 6).

The source-by-source freshness model (1 probe → re-fetch only stale sources) is unchanged from v2; this file describes the additions, not the existing Linear/PR/sessions/ADR fetch.

---

## F2 — claude-md-rules-discovery

### Discovery (where to find the rules)

```bash
# Root CLAUDE.md (always checked when present)
[ -f "$REPO_ROOT/CLAUDE.md" ] && echo "$REPO_ROOT/CLAUDE.md"

# Per-touched-directory CLAUDE.md
# For each directory of every changed file, walk up to repo root
for f in $CHANGED_FILES; do
  dir=$(dirname "$f")
  while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
    [ -f "$REPO_ROOT/$dir/CLAUDE.md" ] && echo "$REPO_ROOT/$dir/CLAUDE.md"
    dir=$(dirname "$dir")
  done
done | sort -u
```

This produces a unique list of in-scope `CLAUDE.md` files (root + every ancestor dir of each touched file that has a `CLAUDE.md`).

### Freshness signal

```bash
# Capture the git SHA of the most recent commit touching any in-scope CLAUDE.md
CLAUDE_MD_LIST=$(... discovery above ...)
if [ -n "$CLAUDE_MD_LIST" ]; then
  CLAUDE_MD_GIT_SHA=$(git log -1 --format=%H -- $CLAUDE_MD_LIST 2>/dev/null | cut -c1-12)
fi
# null if no in-scope CLAUDE.md
```

Stored in `freshness_signals.claude_md_git_sha`. Probed in **Step 1f** alongside the existing 4 probes (parallel, ~free).

### Cache invalidation: WT_HASH inclusion

Editing a `CLAUDE.md` rule should invalidate the **findings** cache (not just the context bundle), because the same diff may now produce a different verdict (a previously-OK finding is now CONFLICT).

Step 1b extension — when `CLAUDE_MD_LIST` is non-empty, include the SHA in `WT_HASH`:

```bash
# After computing the existing WT_HASH from CHANGED_FILES diff:
if [ -n "$CLAUDE_MD_LIST" ]; then
  WT_HASH=$(echo "$WT_HASH $CLAUDE_MD_GIT_SHA" | shasum | cut -c1-12)
fi
```

This way a CLAUDE.md edit (commit OR working tree change) flips the findings cache to MISS without bumping the skill version.

### Fetch (Step 3g)

The context-fetcher reads each in-scope `CLAUDE.md` verbatim and writes a `## CLAUDE.md` section in `/tmp/gate-context-bundle.md`:

```
## CLAUDE.md

### <repo-root>/CLAUDE.md
<verbatim content>

### <repo-root>/packages/wome-api/CLAUDE.md
<verbatim content>
```

The teammate does not interpret the rules — interpretation is the context-checker's job.

### Enforcement (Step 6)

The context-checker prompt is extended (additional instructions appended at the **end** of the existing prompt — append-only for cache safety):

```
## CLAUDE.md rule enforcement

For each finding in the input list, additionally check the CLAUDE.md
section of the context bundle:

  - If a CLAUDE.md rule explicitly forbids the pattern in the finding's
    evidence (rule contains "MUST NOT", "must not", "never", "forbidden"):
    upgrade the verdict from OK to CONFLICT, set source: "claude-md",
    citation: the rule verbatim (capped at 240 chars).

  - If a CLAUDE.md rule explicitly permits or recommends the pattern
    (rule contains "MUST", "always", "required"):
    if the finding contradicts the rule, set verdict: CONFLICT.
    Otherwise leave OK.

  - If the rule is silent on the pattern, leave the verdict unchanged.

In addition to per-finding annotation, emit synthesized findings for
CLAUDE.md rules that the diff itself violates (independent of any
reviewer finding). Format:

  {
    "rule_id": "claude-md-violation",
    "tier": "BLOCKER" if rule contains "MUST NOT", else "MAJOR",
    "file": <file in diff that violates>,
    "line": <line where the pattern appears>,
    "evidence": <code excerpt>,
    "citation": <rule verbatim, ≤240 chars>,
    "source": "claude-md"
  }
```

Synthesized `claude-md-violation` findings flow through Step 7 verdict counting normally — a `MUST NOT` violation produces a BLOCKER and FAILs the gate.

### Auto-fix

`claude-md-violation` is **not auto-fixable** (policy violation, not a mechanical edit). Excluded from `--fix` filtering in Step 8.

---

## F3 — adr-discovery-dynamic (applicability filter)

The existing v2 ADR fetch reads every `docs/adr/*.md` and filters bodies for changed-file/symbol mentions. v3 generalises the **roots** ADRs are read from and makes the applicability decision more precise by adding **two** matching strategies on top of the existing body-mention heuristic.

### ADR roots (where ADRs live)

ADRs are read from the union of these conventional locations — whichever exist in the repo (computed once in Step 1b as `ADR_ROOTS`):

- `docs/adr/`
- `docs/architecture/decisions/`
- `.claude/rules/`

`.claude/rules/` is treated as a full ADR root: every `*.md` directly under it is a candidate ADR. The applicability filter (below) handles narrowing — generic rules like `search-tools.md` won't surface unless the diff matches their domain via paths/keyword/body-mention.

If none of the roots exist, the fetcher emits `## ADR\nnone` and `adr_git_sha: null` (same shape as today).

### Strategy 1 — frontmatter `paths:` glob

ADRs can declare which file paths they apply to via YAML frontmatter:

```yaml
---
paths:
  - "packages/api/resolvers/**"
  - "packages/api/types/**"
---
```

This frontmatter is read **directly from each ADR file** (any of the roots above). For each ADR with a `paths:` array, evaluate the globs against `CHANGED_FILES` — any match → mark this ADR as **applicable**.

The legacy *companion-file* form is still supported for ADRs that live under `docs/adr/`. A `.claude/rules/adr-*.md` file with frontmatter like:

```yaml
---
adr_id: 0001
paths:
  - "packages/api/resolvers/**"
---
```

maps to `docs/adr/0001-*.md`. Both forms coexist; either marks the ADR applicable.

### Strategy 2 — filename keyword match

If no companion rule exists, fall back to matching the ADR filename keywords against extensions / directory segments of the changed files. Examples:

| ADR filename | Triggers on |
|---|---|
| `0007-graphql-nullability.md` | files containing `resolvers/`, `*.resolver.ts`, `schema.graphql` |
| `0012-error-handling.md` | files containing `errors/`, `*.error.ts`, `try {`/`catch` blocks |

The keyword extraction is a simple regex on the filename (split on `-`, drop the leading number, drop stopwords). Heuristic — accept some false positives, the checker filters them out.

### Strategy 3 — body-mention fallback (existing v2)

If neither Strategy 1 nor Strategy 2 marks the ADR applicable, the existing v2 body-mention logic still applies (read body, check if any changed file or symbol is mentioned).

### Output

The fetched `## ADR` section in `/tmp/gate-context-bundle.md` includes only **applicable** ADRs (full body), plus a one-line index of all ADR paths at the top. Paths are full (not just filenames), since multiple roots may contribute:

```
## ADR

### Index (all ADRs)
- docs/adr/0001-graphql-nullability.md
- docs/adr/0007-error-handling.md
- .claude/rules/no-direct-prisma.md
...

### Applicable to this diff

#### docs/adr/0001-graphql-nullability.md
<verbatim body>

#### .claude/rules/no-direct-prisma.md
<verbatim body>
```

### Enforcement (Step 6)

The context-checker prompt is extended (append-only):

```
## ADR enforcement

For each finding, additionally check the ADR section of the context bundle.
Only the "Applicable to this diff" subsection contains relevant ADRs;
the index is for reference.

For each applicable ADR:

  - Search for "MUST", "MUST NOT", "SHALL", "SHALL NOT" clauses.
  - If a clause's subject pattern matches the finding's evidence:
    set verdict: CONFLICT, source: "adr",
    citation: "ADR-<id>: <clause verbatim, ≤240 chars>" for numbered ADRs
    under docs/adr/, or "<ADR full path>: <clause verbatim, ≤240 chars>"
    for unnumbered files (e.g. .claude/rules/<name>.md).

  - If a clause "SHOULD" / "RECOMMENDED" pattern matches but the finding
    is not blocking-severity, set verdict: OK (informational only).

Synthesized findings for ADR-violating diffs:

  {
    "rule_id": "adr-violation",
    "tier": "BLOCKER" if clause contains "MUST" or "SHALL",
            "MAJOR"   if clause contains "SHOULD" or "RECOMMENDED",
    "file": <file in diff that violates>,
    "line": <line where the pattern appears>,
    "evidence": <code excerpt>,
    "citation": "ADR-<id>: <clause verbatim, ≤240 chars>",
    "source": "adr"
  }
```

### Auto-fix

`adr-violation` is **not auto-fixable**. Excluded from `--fix`.

---

## Summary of v3 freshness signals

```
freshness_signals = {
  linear_ticket_id, linear_updated_at,        # v2
  github_pr_number, github_pr_updated_at,     # v2
  adr_git_sha,                                # v2
  claude_md_git_sha,                          # v3 NEW
  devsql_max_history_ts, devsql_max_jhistory_ts  # v2
}
```

```
bundle_sources = {
  linear,    # v2
  pr,        # v2
  adr,       # v2 — content now includes the index + applicability filter,
             #      and roots are unioned across docs/adr/, docs/architecture/decisions/, .claude/rules/
  claude_md, # v3 NEW
  sessions   # v2
}
```

---

## Order of implementation

1. F2 first — CLAUDE.md is mostly mechanical (discovery + verbatim fetch + checker prompt extension) and exercises the new `bundle_sources.claude_md` slot end-to-end.
2. F3 second — ADR applicability is incremental on top of the existing v2 fetch; once the v3 plumbing is in place, the filter is a localized change.

Both features compose at Step 6: the context-checker becomes the single point that enforces "policy as findings," with citations back to the source. No new reviewer is needed for either.
