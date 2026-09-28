# Harness review — PR #17609 — fix(feature-views): flag a registration type the billing country does not offer [RAR-1403]
Items: 13 kept (humans 11 · bots 2) · 9 dropped · 10 causes

| # | Cause | Items | Level | Coverage | Target |
|---|---|---|---|---|---|
| 0 | Map every error label the API raises to a message in each form | review#1 @robinthiry-naboo | 1 | partial (.claude/rules/adr/adr-009-error-management-best-practices.md:55) | Linear ticket: a typed union of error labels, forms typed `Record<Label, Message>` |
| 1 | Assert the whole validation issue (path and message) | thread#4 house-billing.types.test.ts:— @robinthiry-naboo | 3 | none | .claude/rules/frontend/unit-tests.md |
| 2 | Keep every name (identifier, test title) true to what the code does now | thread#7 house-billing.types.ts:— @robinthiry-naboo, thread#10 house-billing.hook.test.tsx:619 @robinthiry-naboo | 3 | partial (.claude/rules/code-style.md:9) | widen Naming in code-style.md |
| 3 | Reuse a derivation already named in the same file | thread#9 useHouseBillingDetails.ts:— @robinthiry-naboo | 3 | partial (.claude/rules/code-style.md:64) | widen Extract & Reuse to local derivations |
| 5 | Pin every guard the diff adds with a test that goes red when the guard is removed | thread#3 house-billing.types.test.ts:426 @robinthiry-naboo, thread#8 house-billing.hook.ts:192 @robinthiry-naboo | 4 | none | a "remove the guard, see it fail" step in the TDD skill |

## Verdicts
- 0 · Pass the query's real load state to the schema — thread#0 house-billing.types.ts:— @naboo-ai-reviews, thread#1 house-billing.types.ts:— @robinthiry-naboo — the PR landed the level-1 fix (required parameter)
- 0 · Word a validation message after the condition it tests — thread#2 house-billing.types.ts:— @robinthiry-naboo, thread#6 house-billing.types.ts:131 @robinthiry-naboo — local domain facts
- 0 · Keep the ticket AC in step with the shipped copy — thread#5 house-billing.types.ts:199 @naboo-ai-reviews — ticket updated, no code change
- 0 · Rewrite the PR description when a fix removes what it describes — review#3 @robinthiry-naboo — rare, about the description

## Dropped
- review#0 @naboo-ai-reviews — summary recapping an inline thread
- review#2 @naboo-ai-reviews — summary recapping an inline thread
- review#4 @naboo-ai-reviews — summary, no findings
- review#5 @robinthiry-naboo — status table of findings already kept
- review#6 @robinthiry-naboo — empty approval
- comment#0 @linear[bot] — tracker bot
- comment#1 @snyk-io-eu[bot] — dependency bot
- comment#2 @gwenaelmonier-naboo — PR author's reply
- comment#3 @github-actions[bot] — CI report
