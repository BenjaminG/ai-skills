# Harness review — PR #17603 — feat(api): drop the company a venue is no longer bound to [RAR-1399]
Items: 18 kept (humans 10 · bots 8) · 15 dropped · 12 causes

| # | Cause | Items | Level | Coverage | Target |
|---|---|---|---|---|---|
| 1 | Restore spies even when a test throws | thread#14 creditsafe-report.service.unit.test.ts:903 @gwenaelmonier-naboo | 1 | none | `restoreMocks: true` in packages/wome-api/vitest.legacy.config.ts |
| 2 | Accept an empty 204 body on every SDK write response | thread#12 monitoring.schema.ts:— @gwenaelmonier-naboo | 1 | partial (packages/creditsafe-sdk/src/schemas/monitoring.schema.ts:97) | map `''` to `{}` in packages/creditsafe-sdk/src/resources/base.ts before `safeParse` |
| 3 | Handle rejection on every detached (`void`) promise | thread#1 creditsafe-report.service.ts:412 @naboo-ai-reviews, thread#4 creditsafe-report.service.ts:407 @cursor | 2 | partial (packages/wome-api/oxlint.config.ts:229) | `no-floating-promises` with `ignoreVoid: false` |
| 4 | Title every `it` "should X when Y" | thread#8 creditsafe-report.service.unit.test.ts:— @sarah-bourgeois | 2 | covered (adr/008-solitary-unit-testing-strategy.md:60) | `valid-title` `mustMatch`, changed files only |
| 5 | Document every new SDK method in the package README | thread#9 monitoring.ts:117 @sarah-bourgeois, thread#13 monitoring.ts:117 @gwenaelmonier-naboo | 2 | covered (adr/025-external-api-sdk-architecture.md:330) | CI / lefthook check diffing resource methods against README headings |
| 6 | Use `HttpStatus` constants, not bare status codes | thread#10 creditsafe-report.service.unit.test.ts:— @sarah-bourgeois | 2 | covered (.claude/rules/code-style.md:83) | packages/eslint-plugin-naboo rule |
| 7 | Ship zero comments | thread#7 creditsafe-report.service.ts:— @sarah-bourgeois, thread#15 creditsafe-report.service.ts:— @gwenaelmonier-naboo | 3 | covered (.claude/rules/code-style.md:82, .cursor/BUGBOT.md:51) | strengthen the line (MUST) and add it to packages/ai-review/agents/ |

## Verdicts
- 0 · Ship every ticket piece or de-scope it in writing — thread#6 creditsafe-report.service.ts:— @sarah-bourgeois — a one-off scope miss
- 0 · Base the removal on the latest claim — thread#0 creditsafe-report.service.ts:417 @cursor, thread#3 creditsafe-report.service.ts:416 @cursor, thread#16 creditsafe-report.service.ts:— @cursor, thread#17 creditsafe-report.service.ts:411 @cursor — domain race the bot caught
- 0 · Read a CreditSafe 404 on DELETE as already absent — thread#2 creditsafe-report.service.ts:439 @cursor — vendor fact the bot caught
- 0 · Derive `*Params` from the sibling type — thread#5 creditsafe-report.service.ts:73 @naboo-ai-reviews — the rule exists and the bot fired
- 0 · Keep fallible reads off the path after the billed call — thread#11 creditsafe-report.service.ts:182 @gwenaelmonier-naboo — contract of this one file

## Dropped
- review#0 @cursor — stale Bugbot pass
- review#1 @naboo-ai-reviews — summary recapping inline threads
- review#2 @cursor — stale Bugbot pass
- review#3 @naboo-ai-reviews — summary recapping inline threads
- review#4 @cursor — stale Bugbot pass
- review#5 @naboo-ai-reviews — summary, no findings
- review#6 @sarah-bourgeois — summary recapping her inline threads
- review#7 @cursor — stale Bugbot pass
- review#8 @gwenaelmonier-naboo — empty
- review#9 @gwenaelmonier-naboo — empty
- review#10 @cursor — summary recapping an inline thread
- review#11 @gwenaelmonier-naboo — empty approval
- comment#0 @linear[bot] — tracker bot
- comment#1 @snyk-io-eu[bot] — dependency bot
- comment#2 @github-actions[bot] — CI report
