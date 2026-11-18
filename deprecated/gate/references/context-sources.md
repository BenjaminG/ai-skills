# Context sources (Step 1f / Step 3g extensions)

This file specifies the discovery and freshness-probe logic for the two new context sources added in v3 — `claude_md` and the **applicability filter** for `adr` — and how they are consumed by the context-checker (Step 6).

The source-by-source freshness model (1 probe → re-fetch only stale sources) is unchanged from v2; this file describes the additions, not the existing Linear/PR/sessions/ADR fetch.

---

## F2 — claude-md-rules-discovery

### Discovery (where to find the rules)

```bash
# Root instruction files. AGENTS.md and .claude/CLAUDE.md are as canonical as CLAUDE.md and were
# read by nothing — a repo whose AGENTS.md is one line ("Follow @.claude/CLAUDE.md") had its
# entire rule set invisible to the gate.
ROOT_RULE_FILES=("CLAUDE.md" "CLAUDE.local.md" "AGENTS.md" ".claude/CLAUDE.md")
for r in "${ROOT_RULE_FILES[@]}"; do [ -f "$REPO_ROOT/$r" ] && echo "$REPO_ROOT/$r"; done

# Per-touched-directory CLAUDE.md / AGENTS.md — for each changed file, walk up to repo root
for f in $CHANGED_FILES; do
  dir=$(dirname "$f")
  while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
    [ -f "$REPO_ROOT/$dir/CLAUDE.md" ] && echo "$REPO_ROOT/$dir/CLAUDE.md"
    [ -f "$REPO_ROOT/$dir/AGENTS.md" ] && echo "$REPO_ROOT/$dir/AGENTS.md"
    dir=$(dirname "$dir")
  done
done | sort -u
```

Then **one level** of `@`-import resolution over that list: a pointer file's targets are rule files
too. Only `*.md` targets, resolved relative to the repo root — a directory import (`@adr/`,
`@docs/`) is ADR discovery's job, and recursing past one level pulls a repo's whole doc tree into
the bundle. Same `@`-path convention as the ADR companion form under F3 Strategy 1.

This produces a unique list of in-scope instruction files: the root set, their one-level `@`-imports,
and every ancestor dir of each touched file that has a `CLAUDE.md` or `AGENTS.md`.

### Freshness signal

```bash
# Content hash over every in-scope instruction file — NOT `git log`. CLAUDE.local.md and
# .claude/rules/local/ are git-ignored in most repos, so a git-log fold silently no-ops and a
# rule edit serves a stale cached verdict. Hashing bytes works tracked or not, and additionally
# catches uncommitted edits. See SKILL.md Step 1b for the zsh word-splitting caveat.
CLAUDE_MD_LIST=$(... discovery above ...)
if [ -n "$CLAUDE_MD_LIST" ]; then
  CLAUDE_MD_GIT_SHA=$(printf '%s\n' "$CLAUDE_MD_LIST" | while IFS= read -r f; do
    [ -n "$f" ] && cat -- "$f"
  done | shasum | cut -c1-12)
fi
# null if no in-scope instruction file
```

The same applies to `ADR_GIT_SHA`: hash the contents of the `*.md` files under `ADR_ROOTS`, not
`git log -1 -- "${ADR_ROOTS[@]}"`. A git-ignored rules directory (`.claude/rules/local/`) has no
commit, so the git-log fold never moves when one of its rules changes.

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

The context-fetcher reads each in-scope `CLAUDE.md` verbatim and writes a `## CLAUDE.md` section in `<TMP_DIR>/context-bundle.md` (per-session scratch dir; see SKILL.md §1b):

```
## CLAUDE.md

### <repo-root>/CLAUDE.md
<verbatim content>

### <repo-root>/packages/wome-api/CLAUDE.md
<verbatim content>
```

The teammate does not interpret the rules — interpretation is the context-checker's job.

### Enforcement

`agents/context-checker.md` Part 2 is the single source of truth for how a rule's normative force
maps to a tier, and for the caps that keep a rule-heavy repo from producing forty findings.
Nothing appends enforcement instructions to the checker's prompt — do not add a second copy here.
`claude-md-violation` and `adr-violation` are policy violations, not mechanical edits: both are
excluded from `--fix`.

---

## F3 — adr-discovery-dynamic (applicability filter)

The existing v2 ADR fetch reads every `docs/adr/*.md` and filters bodies for changed-file/symbol mentions. v3 generalises the **roots** ADRs are read from and makes the applicability decision more precise by adding **two** matching strategies on top of the existing body-mention heuristic.

### ADR roots (where ADRs live)

ADRs are read from the union of these conventional locations — whichever exist in the repo (computed once in Step 1b as `ADR_ROOTS`):

- `docs/adr/`
- `adr/`
- `docs/architecture/decisions/`
- `.claude/rules/`

Each root is walked **recursively**: every `*.md` at any depth under it is a candidate ADR. A repo that files its rules by domain — `.claude/rules/backend/`, `.claude/rules/frontend/`, `.claude/rules/local/` — has them read like any other; a non-recursive walk silently skipped those, which is the common cause of a documented rule that never fires. The applicability filter (below) handles narrowing — generic rules like `search-tools.md` won't surface unless the diff matches their domain via paths/keyword/body-mention.

Recursion plus multiple roots means the same ADR can be reached twice, so **deduplicate before emitting** (see the companion-file form under Strategy 1): a candidate whose body `@`-references another candidate is that ADR's companion, not a second ADR. Merge the pair and emit **one** entry: the companion supplies `paths:`, the summary **and the body**; the referenced file is cited as `full text: <path> (read on demand)`. Emit the companion body, not the referenced one — a companion is the condensed, `paths:`-scoped rule set (a few hundred words) while the ADR it points at is the full record (often several thousand). Inlining the long form spends the checker's whole context on prose that carries no scoping, and buries the enforceable clauses. The checker has `Read` if it needs the full text.

If none of the roots exist, the fetcher emits `## ADR\nnone` and `adr_git_sha: null` (same shape as today).

### Strategy 0 — no `paths:` frontmatter means global

A candidate with no `paths:` array in its frontmatter is an **unscoped** rule file: it applies to
the whole repo, so it is applicable to every diff and emits `binds: all changed files (no
`paths:` declared)`. Check this before the strategies below.

This is not a fallback, it is the common case for a repo's top-level style and language rules
(`code-style.md`, `typescript.md`). Those files carry the naming, structure and reuse rules that
draw the most review comments, and they scope themselves by being global rather than by listing
globs — treating a missing `paths:` as "not applicable" is how they end up enforced by nothing.

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

The legacy _companion-file_ form is still supported for ADRs that live under `docs/adr/`. A `.claude/rules/adr-*.md` file with frontmatter like:

```yaml
---
adr_id: 0001
paths:
  - "packages/api/resolvers/**"
---
```

maps to `docs/adr/0001-*.md`.

A second companion form links by **reference instead of id**: a rule file whose body carries an `@`-path to another candidate — say `.claude/rules/adr/adr-008-solitary-unit-testing.md` containing `@adr/008-solitary-unit-testing.md` — is that ADR's companion. Resolve the `@`-path relative to the repo root and pair the two. Use this form when the companion carries the `paths:` scoping and the digest; the referenced file is cited by path, not inlined.

All forms coexist; any of them marks the ADR applicable, and each pair emits once.

### Strategy 2 — filename keyword match

If no companion rule exists, fall back to matching the ADR filename keywords against extensions / directory segments of the changed files. Examples:

| ADR filename                  | Triggers on                                                      |
| ----------------------------- | ---------------------------------------------------------------- |
| `0007-graphql-nullability.md` | files containing `resolvers/`, `*.resolver.ts`, `schema.graphql` |
| `0012-error-handling.md`      | files containing `errors/`, `*.error.ts`, `try {`/`catch` blocks |

The keyword extraction is a simple regex on the filename (split on `-`, drop the leading number, drop stopwords). Heuristic — accept some false positives, the checker filters them out.

### Strategy 3 — body-mention fallback (existing v2)

If neither Strategy 1 nor Strategy 2 marks the ADR applicable, the existing v2 body-mention logic still applies (read body, check if any changed file or symbol is mentioned).

### Output

The fetched `## ADR` section in `<TMP_DIR>/context-bundle.md` includes only **applicable** rules,
plus a one-line index of all candidate paths at the top. Paths are full (not just filenames), since
multiple roots may contribute. Each applicable entry carries two derived lines before its body:

- `description:` — the rule's own frontmatter summary. One line, and it is the cheapest triage the
  checker gets before reading the body.
- `binds:` — the **changed files this rule covers**, i.e. the output of the `paths:` glob evaluation
  the applicability filter already performed. Emit the result, not the input: `paths:` is a glob
  list the checker would have to re-evaluate, `binds:` is a lookup. A rule with no `paths:`
  frontmatter emits `binds: all changed files (no paths: declared)`.

`binds:` is what makes the context-checker's scoping guard enforceable ("the file appears on that
rule's `binds:` line") and what lets a skeptic refute on "the rule's `paths:` do not cover this file".

```
## ADR

### Index (all ADRs)
- docs/adr/0001-graphql-nullability.md
- .claude/rules/code-style.md
- .claude/rules/backend/guard-resolved-document-reuse.md
...

### Applicable to this diff

#### .claude/rules/backend/guard-resolved-document-reuse.md
- description: Reuse documents already fetched by guards — never re-fetch the same document in downstream services or resolvers.
- binds: packages/wome-api/src/app-event/app-event.resolver.ts, packages/wome-api/src/app-event/app-event.service.ts
<verbatim body>

#### .claude/rules/code-style.md
- description: Code style rules — naming, structure, abstractions, reuse, lint disables.
- binds: all changed files (no `paths:` declared)
<verbatim body>

#### .claude/rules/adr/adr-028-hexagonal-architecture.md
- description: Hexagonal architecture — CQRS dispatch, layers, entity rules, ports/DI, events.
- binds: packages/wome-api/src/contexts/fintech/quote/domain/quote.entity.ts
- full text: adr/028-hexagonal-architecture.md (read on demand)
<verbatim body of the companion>
```

### Enforcement

Same as F2: `agents/context-checker.md` Part 2 owns the force-to-tier mapping and the caps.

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
             #      and roots are unioned across docs/adr/, adr/, docs/architecture/decisions/,
             #      .claude/rules/ — each walked recursively, companions deduped
  claude_md, # v3 NEW
  sessions   # v2
}
```

---

## Order of implementation

1. F2 first — CLAUDE.md is mostly mechanical (discovery + verbatim fetch + checker prompt extension) and exercises the new `bundle_sources.claude_md` slot end-to-end.
2. F3 second — ADR applicability is incremental on top of the existing v2 fetch; once the v3 plumbing is in place, the filter is a localized change.

Both features compose at Step 6: the context-checker becomes the single point that enforces "policy as findings," with citations back to the source. No new reviewer is needed for either.
