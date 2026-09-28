# Harness levels

A **cause** is the reason a review comment had to be written: the gap in the harness that let the
agent (or the human) produce the flagged code. Several comments can share one cause; one comment
carries one cause. Name a cause as the imperative a reviewer would put in a style guide
("guard the tenant on every client mutation"), never as the local symptom ("fix line 42").

Every cause gets exactly one **level**: the most solid place the correction can live so the same
mistake cannot come back. Walk the ladder top-down and stop at the first rung that holds.

| Level | Where the correction lives                                                                              | Holds when                                                                                          |
| ----- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1     | **Codebase**: a type, a data structure, an API shape, a shared helper that makes the mistake unwritable | the wrong code can be made to fail to compile, or the right path can become the only path           |
| 2     | **Static analysis**: a lint rule, a compiler option, a lefthook / CI check                              | a machine can decide it from the diff alone, with no reading of intent                              |
| 3     | **Rules**: a line in the rules the agent loads, an ADR, a review-bot config                             | it needs judgement, and it applies beyond this one PR                                               |
| 4     | **Skill**: a workflow step or playbook in a skill                                                       | the mistake is a missing _process_ (a check that was never run, a step skipped), not a missing rule |
| 0     | **Nothing**: a one-off fix                                                                              | see below                                                                                           |
| 5     | **Nothing encodable**: a verdict, not a destination                                                     | see below                                                                                           |

## Level 0 — one-off

The comment was right and the fix was local, and no general rule would have prevented it: a
domain fact true only here, a typo, a wrong constant, a question answered without a code change,
praise. Test: phrase the would-be rule. If it only makes sense with this PR's file names in it, it
is level 0.

A remark about the prose around the code (the PR description, the ticket, its scope or acceptance
criteria) is level 0 even when a rule could be phrased: the harness governs the code.

## Level 5 — human judgement only

A general lesson exists but no rule, lint or skill can carry it without firing on correct code:
taste in naming beyond what the glossary pins, product trade-offs, "this feature should not exist".
Say in one line why nothing encodes it. Level 5 is rare; reaching for it means rungs 1 to 4 were
each tried and each named a concrete reason to fail.

## Choosing between rungs

- **1 before 2.** A lint rule that bans a pattern is weaker than a type that cannot express it.
  Prefer 1 when the fix is a contained change (a branded type, a required parameter, a helper that
  replaces a hand-rolled pattern). A level-1 cause whose change spans many files is still level 1;
  it becomes a ticket, not a draft.
- **2 before 3.** Run the residual test: could a regex, an AST rule or a ten-line hook decide it
  from the diff alone? Yes → 2. Needs intent, naming meaning or scope → 3.
- **3 before 4.** A rule says _what_ the code must be. A skill says _how_ to work. "Money is in
  cents" is 3. "Run the e2e suite for the finance view before pushing" is 4.
- **A bot caught it.** A bot comment means rung 3 already fired, late. Ask whether rung 1 or 2
  would have stopped it before review. If yes, that is the level; if no, and the bot is right,
  the cause is 0 (the harness worked). A right finding the author accepted as a known risk is 0
  too.
- **A bot was wrong.** A false positive the author declined is a cause too: the bot will raise it
  again on the next PR. Level 3, in that bot's config (a learning, an exclusion), and so is a bot
  enforcing a convention most of the codebase does not follow. A declined claim is its own cause,
  even when the same bot's sibling claim in the same file was accepted and sits at another level.
- **Config that makes it impossible is 1.** Judge the effect, not the file: a test-runner or
  compiler option that removes the mistake (`restoreMocks: true`) is level 1; one that only reports
  it is level 2.
- **A rule with a judgement exception stays at 3.** When the rule itself allows deliberate cases
  ("zero comments, except one line naming a workaround"), a lint would fire on the exceptions;
  strengthen the rule where the agents and bots read it.
- **Legacy violations do not demote a lint.** A pattern hundreds of old files break is still
  level 2 when a rule can decide it: scope the rule to changed files.
- **Level means the work left.** When the PR itself already landed the fix at the right rung (the
  reviewer asked for a required parameter and got it), nothing is left: level 0, even when the
  lesson would help code elsewhere. Other code with the same flaw is a cause for the review that
  finds it, with its own evidence.

## Coverage

Before proposing a new rule, grep the target repo for two or three keywords of the cause.

| Verdict               | Meaning                                                    | Proposal                                                                                                                                                                                               |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `none`                | no rule anywhere                                           | a new entry at the chosen level                                                                                                                                                                        |
| `partial (file:line)` | a rule exists but misses this case                         | widen that rule                                                                                                                                                                                        |
| `covered (file:line)` | a rule exists and names this case, yet the mistake shipped | **strengthen or promote**: rewrite the line so its enforcer fires (e.g. add MUST / SHOULD, fix a `paths:` scope that excludes the file), or move it one rung up (3 → 2, 2 → 1). Never add a duplicate. |

A `covered` cause is the most valuable row: the harness knows the rule and it is not firing.
Say what stops it firing.

## Surfaces to search (naboo-team/naboo)

| Level | Paths                                                                                                                                                                                                                             |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | the owning domain module, `packages/utils`, `packages/hooks`, `packages/design-system`                                                                                                                                            |
| 2     | `packages/eslint-plugin-naboo/rules/`, `packages/oxc-config`, `packages/*/oxlint.config.ts`, `lefthook.yml`, `.github/workflows/`, `tsconfig*.json`                                                                               |
| 3     | `.claude/rules/**` (tracked only — `.claude/rules/local/` and `CLAUDE.local.md` are git-ignored and bind nobody), `.claude/CLAUDE.md`, `adr/`, `.cursor/BUGBOT.md`, `packages/ai-review/agents/`, `packages/ai-review/learnings/` |
| 4     | `.claude/skills/` in the repo for a naboo-specific process; the `ai-skills` plugin for a general one                                                                                                                              |

Two naboo traps for level 2:

- `lint:ci` runs `oxlint --quiet`, so a `warn` rule never blocks CI; it only guides editors and
  agents. A rule meant to stop the mistake ships as `error`, scoped to the files it can already
  pass on. oxlint has no "changed files only" mode; the repo's two precedents are wome-api
  `cellRule()` (error on an opt-in file list) and e2e `lint:adr-015` (lints the diff's files).
- `no-restricted-syntax` runs nowhere (its plugin is not installed), so its existing selectors are
  dead and count as `none` in coverage. A new selector ban is a rule in
  `packages/eslint-plugin-naboo`.

On another repo, discover the equivalent surfaces first (lint config, rules dirs, ADRs, bot
configs) and search those.
