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
8. **Rank** by composite ROI signal. Trim to the 5–10 strongest. Fewer is fine for small/pristine codebases; more is fine for messy ones — let signal decide.
9. **Output** the matrix and per-opportunity details.
10. **Ask** which row(s) the user wants expanded into implementation steps. Do not auto-expand.

## Scoring scale

Use T-shirt sizes — honest about the estimation involved, no false precision.

| Axis | Scale | Meaning |
|---|---|---|
| **Impact** | S / M / L / XL | Pain removed or velocity unlocked |
| **Effort** | S / M / L / XL | Rough engineering cost (hours → weeks) |
| **Risk** | Low / Med / High | Blast radius + reversibility |
| **Confidence** | Low / Med / High | How sure the skill is about Impact and Effort given codebase signals |

Ranking heuristic: favor **high Impact + low Effort + low Risk + high Confidence**. ADR-blocked candidates sink to the bottom regardless.

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

| # | Opportunity | Impact | Effort | Risk | Confidence | Notes |
|---|---|---|---|---|---|---|
| 1 | <name> | L | S | Low | High | |
| 2 | <name> | XL | M | Med | Med | |
| … |
| N | <name> | M | S | Low | Low | ⚠️ ADR-blocked (ADR-0012) |

## Opportunities

### 1. <Opportunity name>
**Problem:** <real friction visible in the code/stack>
**Change:** <what to do, concretely>
**Impact:** <what this unlocks>
**Risk:** <what could go wrong; reversibility>
**Migration path:** <incremental steps, not big-bang>
**Evidence:** <file paths, git signals, hot-paths that motivated this>

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
