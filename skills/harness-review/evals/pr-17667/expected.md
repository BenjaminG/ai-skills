# Harness review — PR #17667 — fix(api): show impersonation consent states and audit feed [SEC2-198]
Items: 15 kept (humans 7 · bots 8) · 5 dropped · 7 causes

| # | Cause | Items | Level | Coverage | Target |
|---|---|---|---|---|---|
| 1 | Build neighbour unit tests with `TestBed.solitary`, never `new X(stub as unknown as T)` | thread#2 impersonation-audit.service.unit.test.ts:— @naboo-ai-reviews, thread#3 impersonation.host.resolver.unit.test.ts:— @naboo-ai-reviews, thread#6 impersonation.admin.resolver.unit.test.ts:— @chrispop22, thread#7 impersonation-request.service.unit.test.ts:— @chrispop22 | 2 | covered (.claude/rules/adr/adr-031-cell-and-neighbour-testing.md:60) | new `*.unit.test.ts` outside cells must import `@suites/unit`, changed files only |
| 2 | Nest `describe` subject > method > behaviour, title each `it` `should X when Y` | thread#10 impersonation-audit.service.unit.test.ts:— @chrispop22, thread#11 impersonation-request.service.unit.test.ts:— @chrispop22, thread#12 impersonation.host.resolver.unit.test.ts:— @chrispop22 | 2 | covered (.claude/rules/adr/adr-031-cell-and-neighbour-testing.md:68) | `valid-title` `mustMatch`, changed files only |
| 3 | Keep `mongoose` out of resolvers (ADR 018) | thread#0 impersonation.host.resolver.ts:— @naboo-ai-reviews | 2 | partial (packages/wome-api/oxlint.config.ts:146) | `no-restricted-imports` override for `**/*.resolver.ts` |
| 4 | Register a GraphQL enum in the file that defines it | thread#1 impersonation-consent.output.dto.ts:— @naboo-ai-reviews | 2 | none | packages/eslint-plugin-naboo rule, changed files only |
| 5 | Use semantic DS tokens, not raw Tailwind palette classes | thread#4 ConsentStatusCard.tsx:— @naboo-ai-reviews, thread#5 WrongAccountContent.tsx:55 @naboo-ai-reviews | 2 | partial (packages/ai-review/agents/i18n-ds.md:9) | ban palette classes in packages/app-host/oxlint.config.ts |
| 6 | Teach the DS reviewer the facts it cannot see: no token for the `bg-gray-50` page background, generated icons set `aria-hidden` | thread#13 ConsentStatusCard.tsx:21 @naboo-ai-reviews, thread#14 ConsentStatusCard.tsx:25 @naboo-ai-reviews | 3 | none | learnings in packages/ai-review/learnings/i18n-ds.md |
| 7 | Prove a fix with a test that goes red when the fix line is removed | thread#8 ImpersonationRequestForm.tsx:389 @chrispop22, thread#9 impersonation-audit.service.boot.test.ts:131 @chrispop22 | 4 | none | a "remove the fix, see it fail" step in the TDD skill |

## Dropped
- review#0 @naboo-ai-reviews — summary recapping inline threads
- review#1 @chrispop22 — empty approval
- comment#0 @linear[bot] — tracker bot
- comment#1 @snyk-io-eu[bot] — dependency bot
- comment#2 @github-actions[bot] — CI report
