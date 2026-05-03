---
name: elevate
description: This skill should be used when the user wants a ranked list of the highest-leverage technical or architectural improvements to make to their project, presented as a ranking matrix. The technical counterpart to `innovate`. Triggers on requests like "elevate", "biggest tech wins", "best architectural moves", "what should I upgrade", "improvement opportunities", or "tech audit". Accepts an optional focus argument (e.g., "feedback-loop", "dx", "build speed", "testing", "observability") to constrain the search.
argument-hint: "[focus area]"
---

# Elevate

Explore the current project deeply, then answer:

**What are the highest-leverage architectural, framework, tooling, or DX improvements you could make to this project right now?**

Produce a **ranked list of 5–10 opportunities** with a scoring matrix. The technical twin of `innovate` (which asks for product moves).

## Focus argument

The skill accepts an optional free-form focus string (e.g., `feedback-loop`, `developer experience`, `build speed`, `testing`, `observability`, `CI pipeline`).

- **No focus:** survey all four dimensions (architecture, libraries, tooling, DX/infra).
- **With focus:** interpret the string, map it to relevant dimensions, and return **only** opportunities that match. Do not include off-focus candidates, even if they look higher-leverage.

## Process

1. **Read the project.** CLAUDE.md, README, key config (package.json, tsconfig, build configs, lockfiles, CI workflows).
2. **Discover ADRs and architectural rules.** Check in order:
   - `docs/adr/`, `docs/adrs/`, `docs/architecture/decisions/`, `adr/`, `adrs/`
   - `.claude/rules/` (architectural guidelines stored as rules)
   - If none found, grep for `ADR-` or `# Architecture Decision` to catch non-standard layouts.
   Parse each ADR/rule to extract what it prescribes or forbids.
3. **Skim for friction.** Recent git history, hot-path code, repeated workarounds, slow builds, awkward patterns, stale deps, TODOs.
4. **Generate candidates** across four dimensions:
   - **Architecture** — layering, module boundaries, data flow, state shape
   - **Libraries & frameworks** — outdated/deprecated deps, better alternatives, version bumps
   - **Build & tooling** — bundler, compiler, package manager, monorepo structure, CI/CD, type system
   - **DX & infrastructure** — testing strategy, observability, logging, error tracking, feature flags, local dev
5. **Apply focus filter** if a focus argument was given. Drop non-matching candidates.
6. **Check each candidate against ADRs/rules.** If a candidate contradicts an ADR, keep it in the matrix but flag it as **ADR-blocked** and de-rank it (it is not actionable without revisiting the ADR first).
7. **Score** each surviving candidate on four axes (see below).
8. **Surface load-bearing assumptions.** For each candidate, list the 1–3 assumptions the Impact and Effort scores depend on. Classify each:
   - **`[verified]`** — the assumption is self-evident from code/config already read (cite `file:line` or a specific snippet). Treat as verified.
   - **`[probe:feasibility]`** — confirms the change is technically viable on **this** codebase (tool parity, plugin compat, known edge cases, semantic gaps between alternatives). Failure of a feasibility probe **kills the candidate**, regardless of impact.
   - **`[probe:impact]`** — confirms the magnitude of the gain (wallclock, bundle size, error rate, contributor time saved).
   - **`[unverifiable]`** — needs infra or prod data the skill can't touch (prod error rate, CI minutes). Keep, but mark.

   For each `[probe:*]`, specify a concrete, cheap command or measurement the user can run in **under ~10 min** to confirm. Examples: minimal repro file compiled with both tools to diff output, `turbo run <task> --dry=json | jq '...'` to tell real work from no-ops, `hyperfine` for wallclock, `du -sh node_modules/.cache` for cache plausibility, `rg -c <pattern>` for call-site counts, reading one file the skill hasn't yet read.

   **Feasibility-first rule:** if a `[probe:feasibility]` exists and runs in <10 min, surface it as the **first probe to run** for that candidate. Its result can kill the candidate before any impact measurement is worth doing.

   **Do not auto-run probes.** The skill suggests; the user decides whether to execute. Any candidate with an unverified `[probe:*]` or `[unverifiable]` assumption driving an L/XL Impact or S Effort score must be scored **Confidence = Low**, regardless of how strong the structural signal looks. Keep it in the matrix; don't cap its Impact — let Confidence do the demotion.
9. **Rank** by composite ROI signal. Trim to the 5–10 strongest. Fewer is fine for small/pristine codebases; more is fine for messy ones — let signal decide.
10. **Output** the matrix and per-opportunity details. For the **top 3 candidates**, include a `Cheapest kill-switch` line: the single fastest test that invalidates the candidate if it fails. This is usually the `[probe:feasibility]` already listed, restated as the literal first thing to run.
11. **Ask** which row(s) the user wants expanded into implementation steps. Do not auto-expand.

## Scoring scale

Use T-shirt sizes — honest about the estimation involved, no false precision.

| Axis | Scale | Meaning |
|---|---|---|
| **Impact** | S / M / L / XL | Pain removed or velocity unlocked, measured as **user-observable outcome** (wallclock, error rate, contributor time saved). Structural proxies alone — DAG edges removed, files touched, lines deleted, tasks in a graph — are not Impact; if only a proxy is available, Confidence caps at Low. |
| **Effort** | S / M / L / XL | Rough engineering cost (hours → weeks). Includes **both implementation AND validation cost**. A 10-line config change that touches a surface of 300+ files (call sites, decorators, schemas) cannot be S — the validation tail dominates. Estimate the real "until I trust it shipped" cost, not just the diff size. |
| **Risk** | Low / Med / High | Blast radius + reversibility |
| **Confidence** | Low / Med / High | How sure the skill is about Impact and Effort given codebase signals. Any unverified `[probe:*]` or `[unverifiable]` assumption behind an L/XL Impact or S Effort forces this to Low. |

Ranking heuristic: favor **high Impact + low Effort + low Risk + high Confidence**. ADR-blocked candidates sink to the bottom. **Candidates with unverified load-bearing assumptions sink via Confidence=Low**, even if their structural signal looks XL — this is intentional, and prevents proxy-driven overestimates from topping the list.

## Scope — explicitly refuse to propose

- **Pure code cleanup** — dead code, renames, file splits belong to `simplify` / `code-slop` / `quality-gate`
- **Single-bug fixes** — if it's scoped to one bug, it isn't an architectural leap
- **Feature additions** — product capabilities are `innovate`'s turf
- **Speculative rewrites** — no "rewrite in Rust" or "migrate to microservices" unless the codebase genuinely demands it; bias toward proven, reversible changes

## Output shape

```
# Elevate — <focus area or "full audit">

ADRs consulted: <list of ADR files / rules found, or "none found">

## Ranking matrix

| # | Opportunity | Impact | Effort | Risk | Confidence | Probes | Notes |
|---|---|---|---|---|---|---|---|
| 1 | <name> | L | S | Low | High | ok | |
| 2 | <name> | XL | M | Med | Low | 2 pending (1 feasibility) | unverified `[probe:feasibility]` gates XL |
| … |
| N | <name> | M | S | Low | Low | ok | ⚠️ ADR-blocked (ADR-0012) |

`Probes` column: `ok` when every load-bearing assumption is `[verified]`; otherwise `<N> pending` where N counts outstanding `[probe:*]` / `[unverifiable]` entries. If any pending probe is `feasibility`, call it out: `<N> pending (<M> feasibility)`.

## Opportunities

### 1. <Opportunity name>
**Problem:** <real friction visible in the code/stack>
**Change:** <what to do, concretely>
**Impact:** <what this unlocks, in user-observable terms>
**Risk:** <what could go wrong; reversibility>
**Migration path:** <incremental steps, not big-bang>
**Evidence:** <file paths, git signals, hot-paths that motivated this>
**Assumptions & probes:**
- `[verified]` <assumption> — <file:line or reasoning already in context>
- `[probe:feasibility]` <assumption> — run: `<command>` → expect `<signal>` to confirm; failure kills the candidate
- `[probe:impact]` <assumption> — run: `<command>` → expect `<signal>` to confirm magnitude
- `[unverifiable]` <assumption> — <why it can't be checked now>
**Cheapest kill-switch:** <single command/test, <10 min, that invalidates the candidate if it fails> *(top 3 only)*

### 2. …

### N. <ADR-blocked opportunity>
**Problem:** <…>
**Change:** <…>
**ADR conflict:** Contradicts `<ADR path / title>` which states "<quoted directive>". Not actionable without revisiting that decision.
**Evidence:** <…>
```

After the matrix and details, ask:

> Which opportunities would you like expanded into implementation steps?

Do not auto-generate implementation steps. Wait for the user to pick.