---
name: interview
description: Interview user to clarify any topic - exploring codebase, investigating issues, planning features, understanding requirements, or drilling into plans. Socratic questioning to uncover details.
argument-hint: "[topic or file]"
disable-model-invocation: true
---

Topic: $0

If topic is a file path, read it. Explore the code and any referenced spec before asking anything.

## The loop

Run this loop. Do NOT prepare a question list in advance — each question is chosen *after* the previous answer.

1. **Ground.** Read the code/spec relevant to the next open branch. Broad sweep on first iteration, narrow re-reads after that — the prior answer often reframes what to look at.
2. **Decide: ask or assume?** For each candidate piece of information, run it through the filter below.
   - Passes filter → ask it.
   - Fails filter → assume it and move on. Surface the assumption inline only if it's load-bearing for the next question.
3. **Ask exactly one question** with your recommended answer. Wait.
4. **Incorporate the answer.** It may close a branch, open a new one, or invalidate an earlier assumption. Go back to step 1.

## The filter — ask ONLY if the question meets at least one

- **PM / product judgment** — users, scope, priorities, UX tradeoffs you shouldn't decide unilaterally.
- **Genuinely ambiguous** — multiple plausible interpretations the code/spec don't resolve.
- **Hidden constraint** — deadlines, stakeholders, past incidents, preferences not in the repo.
- **Irreversible / high blast-radius** — public API shape, naming, schema — cheap now, expensive to reverse.
- **Confidence < 90%** — your recommended answer is a guess, not a grounded inference from code/spec.

## Don't ask

- What the code already shows (layout, existing patterns, naming in use).
- What the user's initial message already stated or implied.
- Implementation defaults when one obvious choice matches repo conventions.
- Yes/no questions where "no" would be absurd given context.
- Permission to proceed ("should I continue?") — just continue or stop.
- Multiple questions in one turn, even related ones.

## Topic hints

- **Codebase exploration:** architecture decisions, why certain approaches.
- **Issue investigation:** symptoms, repro, what changed, when it started.
- **New feature:** scope, users, acceptance criteria, affected systems.
- **Plan / spec review:** tradeoffs, edge cases, dependencies.

## Style

- One question per turn, with a recommended answer.
- Go deep on the current branch before switching — resolve dependencies between decisions first.
- Challenge vague answers — push for specifics.

## Exit

When all meaningful branches are exhausted or the user says "done", summarize findings and ask what to do with them (write spec, create tasks, document).
