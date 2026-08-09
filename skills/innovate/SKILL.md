---
name: innovate
description: This skill should be used to rank evidence-backed product additions or capability changes and recommend one winner, across either the full product or an optional focus such as activation, retention, differentiation, AI, onboarding, or power users. Use `elevate` for architecture, tooling, or DX.
---

# Innovate

Identify the strongest product opportunities the available evidence supports now. Prefer observed problems and differentiated capabilities over feature-volume.

## Workflow

1. **Set scope.** With a focus argument, translate it into a concrete product outcome and keep only matching candidates. Without one, consider user value, differentiation, activation/retention, and force-multipliers. Finish when the target outcome and included dimensions are explicit.

2. **Build a bounded evidence base.** Inspect the highest-signal available sources for product value:
   - Repository instructions (`AGENTS.md`, `CLAUDE.md`), README, public-facing docs, config, landing copy, and changelog
   - User-visible entry points: CLI commands, routes, APIs, integrations, and UI flows
   - Primary journeys from first contact through first value to repeated or power use
   - Issues, discussions, open PRs, TODOs, workarounds, empty states, recent history, and abandoned attempts
   - Accessible analytics, support themes, interviews, sales feedback, or user research
   - Closest alternatives and their relevant capabilities, using current primary sources when differentiation matters

   Inspect one primary identity source, every primary user-visible surface, recent history, and up to three high-signal artifacts per remaining evidence class. Expand only when sources conflict or candidate validation needs it. Record the sample and unavailable evidence classes. Finish when the target user, core job, product identity, primary surfaces, journey breaks, direct or behavioral demand signals, and evidence gaps are recorded with sources.

3. **Generate signal-led candidates.** Each candidate must name:
   - A concrete feature, capability, or user-facing surface
   - The user and scenario it serves
   - At least one signal: direct demand, observed behavior/workaround, journey friction, or a sourced strategic gap
   - Its distinct angle versus current behavior and obvious alternatives

   Across a full audit, consider all four dimensions; treat them as coverage, not quotas. Let evidence determine candidate count. Keep product capabilities, onboarding, integrations, automations, and user-facing workflows. Route technical debt and refactors to `elevate`; route isolated bugs to the relevant debugging or quality skill. Exclude vague visions, undifferentiated copies, and unsupported category pivots.

   Finish when every candidate has a concrete change, beneficiary, scenario, signal, and differentiation claim.

4. **Validate every candidate.** Check commits, current work, changelog, and prior discussion:
   - **`shipped`** — remove only when the proposed user outcome already exists; an evidenced extension may remain as a distinct candidate
   - **`in-progress`** — remove when active work covers the same outcome and scope; an uncovered remainder may remain
   - **`previously-discussed`** — retain; cite the prior rationale and reflect any still-valid blocker in Risk, Fit, or Confidence
   - **`none`** — score normally

   List every load-bearing assumption, normally 1–3, using:
   - **`[verified]`** — directly supported by a cited source
   - **`[probe:demand]`** — tests whether the problem and likely adoption are real; negative evidence kills the candidate, while missing evidence lowers Confidence
   - **`[probe:feasibility]`** — tests whether the capability is viable without an architectural overhaul; failure kills the candidate
   - **`[probe:scope]`** — tests the size estimate through call sites, modules, packages, data, or infrastructure touched
   - **`[unverifiable]`** — requires inaccessible production data, user research, credentials, or stakeholder input

   Spend at most 10 minutes total running safe read-only probes, starting with one demand probe per candidate before any second probe. Leave inaccessible, unsafe, longer, or lower-priority probes pending, each with a concrete command or measurement and expected signal.

   Finish when every surviving candidate has a prior-attempt status, cited evidence, complete assumptions, probe results or pending probes, and an evidence-calibrated Confidence.

5. **Score and rank.** Rank up to seven evidence-supported candidates; return fewer when the project, focus, or evidence supports fewer. Designate one winner and explain its advantage over the runners-up.

## Scoring

Use T-shirt sizes; avoid invented precision.

| Axis | Scale | Anchor |
|---|---|---|
| **Impact** | S / M / L / XL | S: edge case; M: meaningful cohort or journey step; L: core journey or major cohort; XL: product-wide adoption, retention, or differentiation shift |
| **Effort** | S / M / L / XL | Total design, implementation, testing, rollout, migration, and documentation cost |
| **Scope** | XS / S / M / L / XL | XS: config/file; S: module; M: cross-module; L: cross-package/system; XL: cross-repo, infrastructure, or data-layer coordination |
| **Risk** | Low / Med / High | Adoption plus downside: trust, privacy, legal, migration, operational, and user disruption |
| **Fit** | Low / Med / High | Alignment with the product's users, identity, trajectory, and stated strategy |
| **Confidence** | Low / Med / High | Strength and coverage of evidence behind Impact, Effort, and Scope |

Set Confidence to Low when an unverified assumption drives L/XL Impact, S Effort, or XS/S Scope. Rank by these deterministic tiers:

1. High/Med Fit with High/Med Confidence
2. High/Med Fit with Low Confidence
3. Low Fit

Within a tier, order by Impact descending, then Effort, Scope, and Risk ascending. Break ties with stronger direct or behavioral demand evidence. A Low-Fit candidate cannot win. The recommendation may differ from row 1 only for an explicit timing, dependency, or validation reason.

## Output

Produce:

1. `# Innovate — <focus or full audit>`
2. Evidence coverage for repository, customer signal, market/alternatives, and prior attempts: `checked` or `unavailable`, with gaps
3. A ranking matrix:

   `| # | Opportunity | Impact | Effort | Scope | Risk | Fit | Confidence | Probes | Prior | Notes |`

4. `## Recommendation` with one explicit pick and a 2–4 sentence comparison against the runners-up. If its Confidence is Low, recommend its cheapest validation before build commitment.
5. `## Opportunities` with details for the top three only:
   - Problem and signal
   - Concrete change
   - User value and differentiation
   - Evidence and prior-attempt context
   - Risk and incremental rollout
   - Every assumption and completed or pending probe
   - `Cheapest kill-switch`: the fastest test that invalidates the candidate
6. Ask which row the user wants expanded into implementation steps, then stop.
