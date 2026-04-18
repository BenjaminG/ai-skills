---
name: elevate
description: This skill should be used when the user wants to identify the single highest-leverage technical or architectural improvement to make to their project. The technical counterpart to `innovate`. Triggers on requests like "elevate", "biggest tech win", "best architectural move", "what should I upgrade", "next tech leap", or when seeking the most compelling structural change to a codebase.
---

# Elevate

Explore the current project deeply, then answer:

**What's the single highest-leverage architectural, framework, tooling, or DX change you could make to the project right now?**

This is the technical twin of `innovate`. Where `innovate` asks for the best *product* move, `elevate` asks for the best *technical* move.

## Process

1. Read CLAUDE.md, README, and key config files (package.json, tsconfig, build configs, lockfiles, CI) to understand stack and architecture
2. Skim recent git history and hot-path code to spot real friction (repeated workarounds, slow builds, awkward patterns, stale deps)
3. Consider candidates across four dimensions:
   - **Architecture patterns** — layering, module boundaries, data flow, state shape
   - **Libraries & frameworks** — outdated/deprecated deps, better alternatives, meaningful version bumps
   - **Build & tooling** — bundler, compiler, package manager, monorepo structure, CI/CD, type system
   - **DX & infrastructure** — testing strategy, observability, logging, error tracking, feature flags, local dev
4. Evaluate 3–5 candidates, pick ONE winner by pure **leverage / ROI** — the best effort-to-impact ratio wins
5. Present the winner with: problem it solves, proposed change, impact, risk, migration path
6. List the runners-up briefly so the reasoning is visible
7. Only if the user wants to proceed, outline implementation steps

## Selection criterion

**Leverage / ROI only.** A two-day change that unlocks 10x dev velocity beats a month-long rewrite. Favor changes tied to visible pain in the codebase over theoretical improvements.

## Explicitly refuse to propose

- **Pure code cleanup** — dead code, renames, file splits belong to `simplify` / `code-slop` / `quality-gate`
- **Single-bug fixes** — if it's scoped to one bug, it isn't an architectural leap
- **Feature additions** — product capabilities are `innovate`'s turf
- **Speculative rewrites** — no "rewrite in Rust" or "migrate to microservices" unless the codebase genuinely demands it; bias toward proven, reversible changes

## Output shape

```
## Winner: <change name>

**Problem:** <real friction visible in the code/stack>
**Change:** <what to do, concretely>
**Impact:** <what this unlocks; why it's the highest ROI>
**Risk:** <what could go wrong; reversibility>
**Migration path:** <incremental steps, not big-bang>

## Runners-up
- <candidate 2> — <one-line why it lost>
- <candidate 3> — <one-line why it lost>
- <candidate 4> — <one-line why it lost>
```

Stop there. Offer implementation steps only if the user says go.
