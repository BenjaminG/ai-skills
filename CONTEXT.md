# ai-skills

Skills that drive a developer's work on a host repo: tickets, local app, PRs and reviews.

## Language

**Reproduction**:
A bug's symptom observed in the local app on code that does not fix it, with the captures, the steps and the start state that show it.
_Avoid_: repro, verification (checking a claim against prod data is what `investigate` does)

**Start state**:
The data and screen a scenario begins from, set by a run's `reset` and undone by its `restore`.
_Avoid_: fixture, seed
