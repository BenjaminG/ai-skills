---
name: interview
description: Interview the user about a plan file to clarify implementation details, UI/UX decisions, concerns, tradeoffs, edge cases, and dependencies. Use when drilling into a plan before writing a spec.
argument-hint: [plan]
model: claude-opus-4-5-20251101
---

Read plan file $0. Interview the user using AskUserQuestion about:
- Technical implementation details
- UI/UX decisions
- Concerns and tradeoffs
- Edge cases
- Dependencies and constraints

Ask non-obvious questions only. One question at a time. Go deep.

After each answer, either:
1. Ask a follow-up or new question
2. If all ambiguities resolved, summarize findings and ask where to write the spec

Continue until user says "done" or all meaningful questions exhausted.
