---
name: interview
description: Interview user to clarify any topic - exploring codebase, investigating issues, planning features, understanding requirements, or drilling into plans. Socratic questioning to uncover details.
argument-hint: "[topic or file]"
disable-model-invocation: true
---

Topic: $0

If topic is a file path, read it first. Otherwise, use topic as context.

Before asking the user anything, explore the codebase for answers yourself. Only ask what code can't tell you.

Interview the user relentlessly using AskUserQuestion or request_user_input tool. Walk each branch of the topic systematically — resolve dependencies between decisions before moving to dependent questions.

For each question:
1. Provide your recommended answer based on codebase exploration and context
2. Let the user confirm, adjust, or reject

Adapt questions to topic type:

**Codebase exploration:** Architecture decisions, patterns used, why certain approaches
**Issue investigation:** Symptoms, reproduction steps, what changed, when started
**New feature:** Requirements, constraints, affected systems, acceptance criteria
**Plan/spec review:** Implementation details, UI/UX, tradeoffs, edge cases, dependencies

Guidelines:
- Ask non-obvious questions only — don't ask what you can find in code
- One question at a time, with your recommended answer
- Go deep on answers before moving to the next branch
- Challenge assumptions and vague answers — push for specifics
- Uncover hidden complexity and dependencies between decisions

After each answer, either:
1. Ask a deeper follow-up or move to the next branch
2. If all branches exhausted, summarize findings and ask what to do with them (write spec, create tasks, document, etc.)

Continue until user says "done" or all meaningful questions exhausted.
