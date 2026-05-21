# Reviewer prompts

This file holds the reviewer-specific blocks (rule enums, tier rules, heuristics, prompt fragments) that get injected into each reviewer task in `Step 3b`. The orchestrator (`SKILL.md`) references these blocks by name; the lead pastes the relevant block verbatim into each `TaskCreate`.

Per-block discipline: blocks are **append-only**. Inserting content earlier in a block invalidates the prompt-cache prefix across all reviewers and runs. Add new rules at the end of the enum, new heuristics at the end of the heuristics section.

---

## Block: react-reviewer

**Skill invoked**: `/vercel-react-best-practices`

**Rule prefix**: `react-*`

**Rule enum** (closed set):

```
react-missing-key, react-stale-closure, react-deps-missing, react-deps-extra,
react-no-memo-needed, react-effect-misuse, react-server-client-mismatch,
react-hydration-risk, react-state-derivation,
react-boolean-prop-bloat, react-lifted-state-opportunity, react-compound-component-opportunity,
react-other
```

**Heuristics (composition rules — F7)**:

- `react-boolean-prop-bloat`: any new component prop interface introduces ≥3 boolean props with prefix `is|has|show|can|should` ON THE SAME COMPONENT — emit MAJOR. Suggested fix: collapse into a `variant` enum or compound-component shape.
- `react-lifted-state-opportunity`: state declared in a parent only to thread through 3+ levels of children where children co-own reads/writes — emit MAJOR. Suggested fix: extract a context provider OR colocate into the leaf.
- `react-compound-component-opportunity`: parent component renders multiple non-trivial sub-parts via render-prop or boolean toggles — emit MAJOR. Suggested fix: expose `<Modal.Header/>`, `<Modal.Footer/>` etc.

**Tier defaults**: per the canonical tier rules in SKILL.md §3e. Composition findings (`react-boolean-prop-bloat`, `react-lifted-state-opportunity`, `react-compound-component-opportunity`) are MAJOR by default — design-debt, not merge-blocking.

**Auto-fixable**: composition findings are NOT auto-fixable (refactor scope is non-mechanical). Excluded from `--fix`.

---

## Block: solid-reviewer

**Skill invoked**: `/solid`

**Rule prefix**: `solid-*`

**Rule enum**:

```
solid-srp, solid-ocp, solid-lsp, solid-isp, solid-dip,
solid-coupling, solid-cohesion, solid-other
```

**Tier defaults**: MAJOR (per SKILL.md §3e — SOLID violations).

---

## Block: security-reviewer

**Skill invoked**: `/security-review`

**Rule prefix**: `security-*`

**Rule enum**:

```
security-xss, security-sql-injection, security-injection-other, security-secrets-leak,
security-auth-bypass, security-csrf, security-ssrf, security-path-traversal,
security-unsafe-deserialization, security-other
```

**Tier defaults**: BLOCKER for verified vulns. DOWNGRADE to MAJOR if validator deems "theoretical."

---

## Block: simplify-reviewer

**Skill invoked**: `/simplify`

**Rule prefix**: `simplify-*`

**Rule enum**:

```
simplify-dead-code, simplify-overengineering, simplify-naming, simplify-redundant,
simplify-extract, simplify-inline, simplify-missing-test, simplify-other
```

**Heuristic — `simplify-missing-test` (F5 tests-coverage-gap)**:

For each newly-added export in the diff that matches one of these patterns:

- `export function <name>` / `export const <name> =`
- `@Mutation` / `@Query` / `@Resolver` (NestJS / TypeGraphQL decorators)
- `public <name>(` inside an `export class`

Search the diff for a sibling test file covering the export:

- Same directory: `<name>.test.ts`, `<name>.spec.ts`
- `__tests__/` subdirectory: `__tests__/<name>.ts`, `__tests__/<name>.test.ts`

If no matching test file is touched in this diff, emit:

- `simplify-missing-test` MAJOR
- DOWNGRADE to NIT for: pure functions with no branching, type-only modules, `*/index.ts` re-exports
- `evidence`: the function signature
- `suggested_fix`: "add a test file or test case for `<name>`"

**Auto-fixable**: NO — generating tests is anti-pattern slop. `simplify-missing-test` is explicitly excluded from `--fix` (Step 8).

---

## Block: slop-reviewer

**Skill invoked**: `/code-slop`

**Rule prefix**: `slop-*`

**Rule enum**:

```
slop-defensive-check, slop-comment-noise, slop-any-cast, slop-style-drift,
slop-unused, slop-other
```

**Tier defaults**: MAJOR or NIT. No BLOCKERs from this reviewer.

---

## Block: a11y-reviewer (F6 — conditional)

**Trigger**: `SPAWN_A11Y == 1` — any `.tsx` or `.jsx` file in the diff. Set in Step 2 conditional reviewer detection.

**Skill invoked**: none — this reviewer runs an inline Opus prompt (no upstream skill exists).

**Model**: Opus 4.7. **Pass count**: 3 (self-consistency).

**Rule prefix**: `a11y-*`

**Rule enum** (closed set):

```
a11y-missing-alt, a11y-missing-aria-label, a11y-missing-form-label,
a11y-keyboard-trap, a11y-missing-keyboard-handler, a11y-color-contrast,
a11y-missing-role, a11y-other
```

**Reviewer instructions (full prompt body — paste verbatim into the task description)**:

```
You are auditing the JSX/TSX added in this diff for accessibility regressions.
Scope: only NEW UI added by the diff. Do NOT audit pre-existing components
that are unchanged. The Boy Scout rule (location=adjacent capped at MAJOR)
still applies for adjacent legacy code.

For each finding, choose the correct rule_id from the enum:

- a11y-missing-alt          — <img> / <Image> without alt text
- a11y-missing-aria-label   — icon-only buttons / links without aria-label
- a11y-missing-form-label   — <input>/<select>/<textarea> with no <label> or aria-labelledby
- a11y-missing-role         — non-semantic interactive element without role
- a11y-keyboard-trap        — focus trapped (modal without escape, autofocus loop)
- a11y-missing-keyboard-handler — onClick on a non-interactive element without
                                  matching onKeyDown / role=button
- a11y-color-contrast       — color combination inferable from className that
                              fails WCAG AA (e.g. text-gray-300 on bg-gray-200)
- a11y-other                — anything else accessibility-related

Tier rules:
  - a11y-missing-form-label on form inputs → BLOCKER
    (screen-reader users cannot operate the form)
  - All other a11y findings → MAJOR

Output the auto_fixable flag per finding:
  yes  — a11y-missing-alt, a11y-missing-aria-label (icon-only),
         a11y-missing-role (interactive element)
  partial — a11y-missing-form-label (template available; placement needs care)
  no   — a11y-keyboard-trap, a11y-missing-keyboard-handler, a11y-color-contrast
```

**Auto-fixable** (per rule_id, surfaced in finding JSON for Step 8 filtering):

| rule_id | auto_fixable |
|---|---|
| `a11y-missing-alt` | yes |
| `a11y-missing-aria-label` (icon button) | yes |
| `a11y-missing-role` (icon button) | yes |
| `a11y-missing-form-label` | partial (template, but placement may need human) |
| `a11y-keyboard-trap` | no |
| `a11y-missing-keyboard-handler` | no |
| `a11y-color-contrast` | no |

---

## Block: i18n-reviewer (F8 — conditional)

**Trigger**: `SPAWN_I18N == 1` — `SPAWN_A11Y == 1` (any `.tsx`/`.jsx` in diff) AND `package.json` deps include one of: `react-intl`, `next-intl`, `formatjs`, `i18next`. Set in Step 2 conditional reviewer detection.

**Skill invoked**: none — inline Opus prompt.

**Model**: Opus 4.7. **Pass count**: 3.

**Rule prefix**: `i18n-*`

**Rule enum** (closed set):

```
i18n-hardcoded-string, i18n-dynamic-message-id, i18n-string-interpolation,
i18n-missing-namespace, i18n-locale-formatting, i18n-plural-handling,
i18n-other
```

**Reviewer instructions (full prompt body — paste verbatim)**:

```
You are auditing the JSX/TSX added in this diff for i18n / l10n regressions.
The project uses one of: react-intl, next-intl, formatjs, i18next.

Detect, in user-visible code only:

- i18n-hardcoded-string       — literal user-facing string in JSX children
                                or attributes (button labels, headings, error
                                messages, placeholders, tooltips) NOT wrapped
                                in FormattedMessage / intl.formatMessage / t().
- i18n-dynamic-message-id     — message ID computed at runtime
                                (e.g. <FormattedMessage id={`app.${kind}`}/>)
                                — breaks the extractor.
- i18n-string-interpolation   — user-facing text built via string concat or
                                template literal instead of FormattedMessage
                                values prop.
- i18n-missing-namespace      — new translation key without the project's
                                namespace prefix convention.
- i18n-locale-formatting      — date / number / currency formatted manually
                                (toLocaleString, toString) instead of using
                                Intl or project i18n utilities.
- i18n-plural-handling        — countable noun / message branching on count
                                without intl.plural / `{count, plural, …}`.
- i18n-other                  — anything else i18n-related.

Tier rules:
  - i18n-hardcoded-string, i18n-dynamic-message-id → MAJOR
    (extractor-breaking, ships untranslated UI)
  - i18n-string-interpolation, i18n-locale-formatting, i18n-plural-handling → MAJOR
  - i18n-missing-namespace → NIT

Exclusion list — DO NOT flag these as i18n issues:
  - log strings: console.*, logger.*, this.logger.*, debug(), info(), warn(), error()
  - GraphQL field / argument names, schema definitions
  - server-side thrown error messages (NestJS HttpException, throw new Error())
  - telemetry event names, analytics keys
  - test descriptions (it(), describe(), expect().toX())
  - file paths, URLs, env-var names

Output the auto_fixable flag per finding:
  partial — i18n-hardcoded-string IF the string is ≤ 8 words AND the file
            already imports FormattedMessage / intl / t. Else mark "no" and
            emit suggested_fix as text-only suggestion.
  yes — i18n-key-naming-inconsistent, i18n-missing-namespace, i18n-plural-handling
        (template insertions / renames are mechanical)
  no — i18n-dynamic-message-id, i18n-locale-formatting, i18n-string-interpolation
       (require redesign / API choice the human must make)
```

**Auto-fixable** (per rule_id, surfaced in finding JSON for Step 8 filtering):

| rule_id | auto_fixable | Conditions |
|---|---|---|
| `i18n-hardcoded-string` | partial | string ≤ 8 words AND file already imports `FormattedMessage` / `intl` |
| `i18n-missing-namespace` | yes | template insertion / rename |
| `i18n-plural-handling` | yes | template |
| `i18n-string-interpolation` | no | requires redesign |
| `i18n-locale-formatting` | no | manual API choice |
| `i18n-dynamic-message-id` | no | requires extraction redesign |

---

## Block: migration-reviewer (F4 — conditional)

**Trigger** (Step 2 conditional detection): `SPAWN_MIGRATION == 1`. Diff matches one of:

- File path: `migrations/`, `*migration*.ts`, `*.migration.ts`
- Diff content: `updateMany`, `bulkWrite`, `deleteMany`

AND **excludes** paths matching `(test|spec|fixture|__mocks__)`.

**Rule prefix**: `migration-*`

**Rule enum (provisional)**:

```
migration-cron-conflict, migration-filter-under-selection, migration-filter-over-selection,
migration-missing-rollback, migration-rollback-mismatch, migration-business-rule-conflict,
migration-other
```

**Tier defaults**:

| rule_id | tier | reason |
|---|---|---|
| `migration-cron-conflict` | BLOCKER | data-loss class |
| `migration-filter-under-selection` | BLOCKER | data-loss class |
| `migration-missing-rollback` | BLOCKER | recovery-blocking |
| `migration-filter-over-selection` | MAJOR | wrong-rows class |
| `migration-rollback-mismatch` | MAJOR | recovery debt |
| `migration-business-rule-conflict` | MAJOR | needs context-checker confirmation |
| `migration-other` | MAJOR | default |

**Reviewer steps** (encoded in the prompt):

1. Detect every migration / bulk-update in the diff.
2. For each filtered field (e.g. `status`), enumerate all write paths in the codebase: `grep -rn "<field>\s*[:=]" --include="*.ts"`.
3. Cross-check against background jobs and crons: `grep -rn "@Cron|cron.service|setInterval|updateMany|bulkWrite" --include="*.ts" -l`.
4. Verify filter completeness:
   - `$in: [...]` may under-select if a document can transition further while the bug persists. Prefer `$ne: <good_value>` when the goal is "everything not yet good."
5. Verify filter precision (over-selection): does the filter capture rows it shouldn't?
6. Verify `down()` / rollback restores exactly what `up()` changed.
7. If context bundle has documented business rules → cross-check.

**Auto-fixable**: NO — every `migration-*` finding is excluded from `--fix` (Step 8). Migration fixes require human design.

---

## Block: context-fetcher

**No skill invoked** — direct logic in the teammate prompt. See SKILL.md §3g for the full spec.

**Model**: Haiku 4.5.

**Pass count**: 1 (no self-consistency).

**Output**: `<TMP_DIR>/context-bundle.md` + `<TMP_DIR>/freshness-signals.json`, where `<TMP_DIR> = /tmp/gate-${SESSION_ID}` is the per-session scratch dir from SKILL.md §1b.

**Sources** (each conditional on `sources_to_fetch`):

- `linear` — Linear ticket + comments
- `pr` — GitHub PR body + reviews + conversation
- `adr` — ADR catalog (filenames + applicability via path globs from `.claude/rules/adr-*.md` frontmatter; bodies of applicable ADRs)
- `claude_md` — root `CLAUDE.md` + every `<touched_dir>/CLAUDE.md` (raw content — context-checker enforces rules)
- `sessions` — past Claude Code / Codex sessions touching the changed files
