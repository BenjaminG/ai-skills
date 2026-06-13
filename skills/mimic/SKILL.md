---
name: mimic
description: >-
  Extract and reproduce a specific person's coding style from a git repository.
  Use this skill whenever the user wants to analyze how a teammate codes, build a
  reusable style profile from someone's commits or PRs, make code generation match
  a particular author's conventions, onboard into a codebase by mirroring its
  dominant author, or clone/imitate a coding style. Triggers on requests like
  "match X's style", "how does X code", "write this the way X would", "extract
  someone's coding patterns", "reproduce my teammate's conventions" — even when
  not phrased as a "skill" and even when the author is referred to indirectly.
---

# Mimic — Coding-style extraction & reproduction

## What this produces
A `style-profile.md`: a set of **decisions** (not prose descriptions) an author makes,
each backed by real examples mined from the repo, with do/avoid pairs and a confidence
score. The profile is written to be consumed as a skill or `CLAUDE.md` fragment so future
code generation reproduces the style. The skill ends with a hold-out validation loop that
measures reproduction fidelity — do not skip it.

## Core principle
**Style worth extracting = the residual after auto-formatting.** Strip everything
Prettier/ESLint/EditorConfig already enforce (whitespace, quotes, semicolons, import
order, naming case). That is reproducible by tooling and is pure noise. Target only the
decisions no linter can impose: decomposition, type modeling, error handling, async
patterns, test philosophy, abstraction level, and where business logic lives.

A second principle: **a rule with no concrete example is worthless.** Abstract rules
("prefer immutability") do not reproduce anything. A before/after pulled from the actual
repo does. Every entry in the profile must cite `path:line`.

## Inputs — collect before starting
Confirm these with the user (don't guess):
1. **Author** — git author name and/or email pattern (substring match, e.g. `Stephane` or `stephane@`).
2. **Scope** — path glob to constrain analysis (e.g. `packages/feature-views/`). Defaults to repo root.
3. **Window** — how far back (default 6 months; style drifts, recency matters).
4. **Target** — where to write the profile and in what form (standalone skill vs `CLAUDE.md` section).

## Stage 1 — Select the corpus (deterministic, scripted)
Run the bundled script. It does NOT dump everything — it computes per-file **line ownership**
via `git blame` (after a cheap author pre-filter to stay tractable on large repos) and keeps
only files where the author dominates. This is what keeps Stage 3 inside the context budget.

```bash
chmod +x scripts/select-corpus.sh
scripts/select-corpus.sh -a "<author-pattern>" -s "<path-scope>" -d "6 months ago" -t 50 -n 40
```

Outputs to `.mimic-corpus/`:
- `owned-files.txt` — files the author owns ≥ threshold %, ranked. **Highest-signal: read these in full.**
- `ownership.tsv` — full ranking (pct, lines, total, path) for inspection.
- `recent.diff` — their diffs over the window, lockfiles/dist/snapshots excluded, capped.
- `commits.txt` — `sha|date|subject`, reveals commit granularity & discipline.

## Stage 2 — Signal hierarchy
Read sources in this priority. Spend the context budget top-down.

| Source | Weight | What it reveals | How to get it |
|---|---|---|---|
| Owned files (full read) | ★★★ | Architecture, decomposition, type modeling — the complete vision | `owned-files.txt` |
| PR review comments | ★★★ | **Explicit** preferences ("use X not Y") — aspirational style, often cleaner than their own code under deadline | `gh` (see below) |
| Incremental diffs | ★★ | Style under constraint of existing code | `recent.diff` |
| Commit subjects | ★ | Atomicity, granularity, message conventions | `commits.txt` |
| Scattered blame lines | ✗ | Too fragmented — ignore | — |

Optional but high-value — pull the author's review comments (preferences they *impose* on others):
```bash
gh pr list --reviewer "@<login>" --state merged --limit 50 --json url -q '.[].url' \
  | while read url; do gh pr view "$url" --comments --json comments \
      -q '.comments[] | select(.author.login=="<login>") | .body'; done
```

## Stage 3 — Extract the profile
This is judgment work. Do it yourself, or spawn a subagent with a clean context window if the
corpus is large. For **each dimension** below, emit: a rule, **2 evidence citations** (`path:line`
+ one-line note), **1 counter-example** (what the author demonstrably avoids), and a confidence
(`high`/`med`/`low`, with n = number of supporting instances). Drop any dimension with < 2 instances —
say "insufficient signal" rather than inventing a rule.

Dimensions:
1. **Module & file decomposition** — one responsibility per file? co-location of types/tests? barrel files?
2. **Type modeling** — discriminated unions vs classes, branded/nominal types, richness vs pragmatic `any`/`unknown`, inference vs explicit annotations.
3. **Error handling & boundaries** — throw vs `Result`/`Either`, where errors surface, custom error types, exhaustiveness.
4. **Async & concurrency** — async/await vs promise chains, parallelism patterns, cancellation, retry/backoff.
5. **State & data flow** — where business logic lives (component / hook / service / domain), mutation posture, dependency injection style.
6. **Function shape & abstraction** — arg count, options-object threshold, early-return vs nesting, when they extract vs inline, tolerance for abstraction.
7. **Testing philosophy** — test structure (AAA, nesting), mock posture (heavy mocks vs real deps), what gets tested vs skipped, fixture style.
8. **Comments & docs** — JSDoc presence, comment density, what they comment (why vs what), TODO conventions.
9. **Dependency posture** — build vs buy, recurring library choices, reluctance/eagerness to add deps.
10. **Domain naming** — semantic naming beyond lint rules (domain vocabulary, abbreviation tolerance, boolean/handler naming patterns).

Output schema per dimension:
```md
### <dimension>
- **Rule:** <decision in one sentence>
- **Evidence:** `path/to/file.ts:42` — <why this shows it>; `other.ts:88` — <…>
- **Avoids:** <the alternative they demonstrably reject>
- **Confidence:** med (n=4)
```

## Stage 4 — Validate (hold-out, mandatory)
A profile that isn't validated is decoration. Run an eval-style loop:

1. Pick a **recent commit/PR by the author NOT used** in extraction (check it's not among the cited files).
2. Reconstruct the pre-state: `git checkout <sha>~1` (or a worktree).
3. Hand Claude the task + the `style-profile.md`, have it implement.
4. `git diff` the generated code against the author's real `<sha>` implementation.
5. Each meaningful divergence is a verdict: a **missing rule** (add it) or an **over-rigid rule** (loosen it).
6. Iterate until divergences are stylistically negligible. Report a fidelity summary (what matches, what doesn't, residual gaps).

Restore state afterward: `git checkout -` / remove the worktree.

## Output artifact
Write `style-profile.md` with: a header (author, scope, window, corpus size — n files / n commits),
the 10 dimensions, and a closing **validation report**. If the target is a reusable skill, wrap it
with frontmatter so it loads contextually; if `CLAUDE.md`, prepend a one-line "When writing in
`<scope>`, follow these conventions:" anchor.

## Guardrails
- **Formatting noise** — if any rule could be enforced by Prettier/ESLint, delete it; the extraction missed the point.
- **Squash merges** destroy blame granularity. If the repo squashes, derive incremental style from PR diffs via `gh`, not `git blame`.
- **Attribution pollution** — vendored, generated, or copy-pasted code attributed to the author skews the profile. The script excludes `*.lock`/`dist`/`*.snap`; flag anything else that looks non-authored.
- **Team vs personal** — what the author does under repo constraint ≠ their preference. Review comments disambiguate; weight them.
- **Sample size** — below ~5 owned files or ~15 commits, label the whole profile low-confidence and say so explicitly.
- **No fabrication** — a dimension without ≥ 2 real examples is reported as "insufficient signal," never as an invented rule.
