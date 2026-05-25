---
name: innovate
description: This skill should be used when the user wants a ranked list of the highest-value product additions or feature changes to make to their project, presented as a ranking matrix with one explicit recommendation. The product counterpart to `elevate` (which targets architecture/tooling/DX). Triggers on requests like "innovate", "what should I build next", "best product moves", "next big thing", or "what feature would matter most". Accepts an optional focus argument (e.g., "activation", "differentiation", "AI", "onboarding").
argument-hint: "[focus area]"
---

# Innovate

Explore the current project deeply, then answer:

**What are the highest-value product additions or capability changes you could make to this project right now — and if you had to pick just one, which one and why?**

Produce a **ranked list of 5–10 opportunities** with a scoring matrix, then designate **one explicit winner** with justification. The product twin of `elevate` (which asks for technical/architectural moves).

## Focus argument

The skill accepts an optional free-form focus string (e.g., `activation`, `retention`, `differentiation`, `AI`, `onboarding`, `power users`).

- **No focus:** survey all four product dimensions (user value, differentiation, activation/retention, force-multiplier).
- **With focus:** interpret the string, map it to relevant dimensions, and return **only** opportunities that match. Do not include off-focus candidates, even if they look higher-leverage.

## Process

1. **Read the project.** CLAUDE.md, README, key config, public-facing docs (landing page, marketing copy, changelog) to understand the product's current positioning and user-visible surface.
2. **Map the user surface.** Identify entry points (CLI commands, routes, API endpoints, UI flows), then trace the user journey from first contact to power use. Note where the journey breaks, dead-ends, or requires workarounds.
3. **Skim for product friction.**
   - Issues / discussions / open PRs labelled `enhancement`, `feature request`, `RFC`, or with high reaction counts
   - TODOs and FIXMEs in code that hint at deferred capabilities
   - Comments like "for now", "until we...", "workaround for"
   - Recent git history for half-built features or aborted attempts
   - User-facing strings with placeholder/empty states ("coming soon", "not yet supported")
4. **Generate candidates** across four product dimensions:
   - **User value** — features that resolve a visible pain (high-reaction issues, repeated workarounds, friction in core flows)
   - **Differentiation** — capabilities that make this project distinct vs. obvious alternatives; what would make a reviewer say "oh, *that's* interesting"
   - **Activation & retention** — onboarding, first-success time, sticky surfaces (dashboards, notifications, integrations users return to)
   - **Force-multiplier** — capabilities that amplify what already works (integrations, automations, API exposure, AI augments on existing flows)
5. **Apply focus filter** if a focus argument was given. Drop non-matching candidates.
6. **Filter by prior-attempt status.** For each candidate, do a quick check (commits, recent git history, project changelog) to detect:
   - **`shipped`** → drop the candidate (already done)
   - **`in-progress`** → drop the candidate (active work, not an ideation target)
   - **`previously-discussed`** → keep, surface in Notes ("RFC #N filed 2024-XX, not pursued — context: ...") so the user has the prior thinking, but no scoring penalty
   - **`none`** → normal scoring

   Unlike `elevate`, do **not** penalize ideas that were rejected in the past. Markets, users, and tech move; a "no" 12 months ago can be a "yes" today. The history check is informational, not punitive.
7. **Score** each surviving candidate on six axes (see below).
8. **Surface load-bearing assumptions.** For each candidate, list the 1–3 assumptions the Impact and Scope/Effort scores depend on. Classify each:
   - **`[verified]`** — self-evident from code/config/docs already read (cite source).
   - **`[probe:demand]`** — confirms users actually want this. Cheap signals: count of related issues/discussions, search for workarounds in code, references in support channels, presence of half-built attempts. Failure of a demand probe **kills the candidate** — a feature nobody asked for is not innovation, it's noise.
   - **`[probe:feasibility]`** — confirms the change is technically buildable on this codebase without architectural overhaul. Failure kills the candidate.
   - **`[probe:scope]`** — confirms the size estimate. Cheap signals: `rg -c <pattern>` for call sites, listing files/modules touched, checking whether a shared package needs to change.
   - **`[unverifiable]`** — needs prod data, user research, or stakeholder input the skill can't access. Keep, but mark.

   For each `[probe:*]`, specify a concrete, cheap command or measurement runnable in **under ~10 min**. Examples: `gh issue list --label enhancement --json reactions | jq '...'`, `rg -c "TODO.*<feature>"`, reading the latest changelog, listing modules under a relevant package.

   **Demand-first rule:** if a `[probe:demand]` exists and runs in <10 min, surface it as the **first probe to run** for that candidate. A feature with no demand signal isn't worth feasibility-checking.

   **Do not auto-run probes.** The skill suggests; the user decides. Any candidate with an unverified `[probe:*]` or `[unverifiable]` assumption driving an L/XL Impact, S Effort, or S Scope score must be scored **Confidence = Low**.
9. **Rank** by composite ROI signal (heuristic below). Trim to 5–10 strongest.
10. **Designate one winner.** After the matrix, write a short `## Recommendation` section: pick the single candidate to pursue *if you had to pick one*, and explain why it beats the runners-up. The winner is usually #1, but not always — sometimes a slightly-lower-ranked candidate wins because of strategic timing, dependency unlock, or because #1 is too risky to start without more research. Be explicit about that reasoning.
11. **Output** the matrix, per-opportunity details, and recommendation. For the **top 3 candidates**, include a `Cheapest kill-switch` line: the single fastest test that invalidates the candidate.
12. **Ask** which row(s) the user wants expanded into implementation steps. Do not auto-expand, even for the recommended winner.

## Scoring scale

Use T-shirt sizes — honest about the estimation involved, no false precision.

| Axis | Scale | Meaning |
|---|---|---|
| **Impact** | S / M / L / XL | User-observable value: pain removed, new capability unlocked, differentiation gained, activation/retention lifted. NOT lines of code shipped, NOT features added — *value users would feel*. If only structural/internal proxies are available, Confidence caps at Low. |
| **Effort** | S / M / L / XL | Total engineering cost (hours → weeks): design + implementation + testing + onboarding/docs. Includes the validation tail, not just diff size. |
| **Scope** | XS / S / M / L / XL | Codebase surface touched. **XS** = config or single file. **S** = one module/folder. **M** = cross-module within one package. **L** = cross-package (multiple packages in the monorepo). **XL** = cross-repo, or requires infra/CI/data-layer changes. Helps spot quick wins (low Scope) vs. multi-team coordination work (L/XL Scope). Note: Effort and Scope are correlated but not redundant — a config tweak (XS Scope) can take a week (M Effort) due to design/tuning; a mechanical refactor (L Scope) can ship in a day with codemods (S Effort). |
| **Risk** | Low / Med / High | Primarily **adoption risk** for `innovate`: will users actually use this? Secondary: blast radius if it underperforms. Reversibility matters less than for `elevate` because product features that flop can usually be quietly removed. |
| **Fit** | Low / Med / High | How well this aligns with the project's current trajectory and identity. A brilliant feature that pulls the product in a different direction than its core users want is a Low-Fit. Fit is the product equivalent of `elevate`'s ADR check. |
| **Confidence** | Low / Med / High | How sure the skill is about Impact / Scope / Effort given codebase + history signals. Any unverified `[probe:*]` or `[unverifiable]` assumption behind L/XL Impact, S Effort, or S Scope forces this to Low. |

**Ranking heuristic:** favor **high Impact + low Effort + low Scope + low Risk + high Fit + high Confidence**. At equal Impact and Effort, prefer the candidate with lower Scope (smaller PR = faster ship = faster user feedback). Low-Fit candidates sink to the bottom — keep them in the matrix as "tempting but off-trajectory" so the user sees them, but they should not win.

## Scope — explicitly refuse to propose

- **Pure technical debt or refactors** — that's `elevate`'s turf
- **Single-bug fixes** — `quality-gate` / `simplify`
- **Vague vision statements** — "add AI", "go viral", "build community" without a concrete artifact
- **Me-too features** — "like [competitor] but for us" without a distinct angle
- **Speculative pivots** — changing the product's category (B2B → B2C, library → SaaS) unless there's overwhelming signal in the codebase/issues that this is already happening

## Output shape

```
# Innovate — <focus area or "full audit">

Prior-attempt history: <"checked" or "unavailable">

## Ranking matrix

| # | Opportunity | Impact | Effort | Scope | Risk | Fit | Confidence | Probes | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | <name> | XL | M | M | Low | High | High | ok | |
| 2 | <name> | L | S | XS | Low | High | Med | 1 pending (demand) | quick win if demand confirmed |
| 3 | <name> | XL | L | L | Med | High | Low | 2 pending (1 demand, 1 feasibility) | high upside, needs validation |
| … |
| N | <name> | XL | M | S | Low | Low | High | ok | tempting but off-trajectory |

`Probes` column: `ok` if every load-bearing assumption is `[verified]`; otherwise `<N> pending` with breakdown by type when relevant: `<N> pending (<X> demand, <Y> feasibility, <Z> scope)`.

## Recommendation

**Pick: #<n> — <opportunity name>**

<2–4 sentences explaining why this candidate wins over the runners-up. Be explicit about tradeoffs: if #1 has the best raw score but you're recommending #2, say why (e.g., "#1 has higher Impact but unverified demand; #2 ships faster with confirmed signal and unblocks #1 later").>

## Opportunities

### 1. <Opportunity name>
**Problem / opportunity:** <visible friction, missing capability, or untapped angle>
**Change:** <what to build, concretely — a feature, capability, or surface, not a vague direction>
**User value:** <who benefits, how, in what scenario>
**Differentiation angle:** <why this matters vs. alternatives, or why now>
**Risk:** <primary adoption risk; what would make users not adopt this>
**Migration / rollout path:** <incremental shipping plan; MVP → expansion>
**Evidence:** <issues, file paths, code patterns, comments, changelog entries that motivated this>
**Assumptions & probes:**
- `[verified]` <assumption> — <source>
- `[probe:demand]` <assumption> — run: `<command>` → expect `<signal>`; failure kills the candidate
- `[probe:feasibility]` <assumption> — run: `<command>` → expect `<signal>`; failure kills the candidate
- `[probe:scope]` <assumption> — run: `<command>` → expect `<signal>` to confirm size
- `[unverifiable]` <assumption> — <why it can't be checked now>
**Cheapest kill-switch:** <single command/test, <10 min, that invalidates the candidate if it fails> *(top 3 only)*

### 2. …

### N. <Low-Fit opportunity>
**Problem / opportunity:** <…>
**Change:** <…>
**Fit concern:** <why this pulls the product off-trajectory; quote the project's stated direction or core user>
**Evidence:** <…>
```

After the matrix, recommendation, and details, ask:

> Which opportunities would you like expanded into implementation steps?

Do not auto-generate implementation steps, even for the recommended winner. Wait for the user to pick.