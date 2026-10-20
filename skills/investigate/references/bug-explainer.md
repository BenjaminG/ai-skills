# Bug explainer artifact

A private Artifact page that tells the user the story of the bug in plain words
while the Explore agents dig, then carries the diagnosis once they report. One
file, one URL for the whole investigation. Write it in the user's language and
apply `explain-plainly` to every sentence: no identifier appears before the
glossary defines it.

Before writing the file, load the `artifact-design` skill (the Artifact tool
requires it). Publish with `icon: "bug"`, from a file in the scratchpad named
after the issue (`<ISSUE-ID>-explainer.html`), so the §7 republish reuses that
path and keeps the URL.

## Draft — right after spawning the §6 agents

Built from the §5 summary alone, in the same turn as the `Agent` calls, before
any agent reports. A status banner at the top reads **cause en cours
d'analyse** (or its equivalent in the user's language).

Blocks, in this order:

1. **Symptom**: what the user sees, two sentences, zero jargon.
2. **Expected vs actual path**: an inline SVG of the user's journey, two lanes,
   with the step where they diverge marked. Load `artifact-diagramming` for it.
3. **Timeline**: who reported what and when, from the thread and comments.
4. **Worked example**: real values from the ticket, or plausible ones labelled
   as invented.
5. **Glossary**: one row per identifier, field name and domain word, mapped to
   everyday words; old-vs-new fields flagged as such.
6. **What the agents are checking**: the starting hypotheses and which agent
   tests which.

Block 2 is mandatory. Drop any other block the §5 summary gives nothing to fill.
Screenshots are described in words inside blocks 1 and 2, never embedded.

The draft is done when it is published and its link is in the terminal.

## Diagnosis — at §7

Republish the same file path once both syntheses are merged. The banner shows
the real state of the investigation:

- **Cause trouvée**: add a **Cause** section after block 2, in plain words,
  with a diagram of where it breaks in the code (same two-lane shape, now
  pointing at the component). Below it, a `<details>` section, collapsed,
  holding the `file:line` root cause, its evidence, and the files, tests and
  docs to touch. Drop block 6.
- **Pas encore trouvée**: replace block 6 with the hypotheses ruled out (each
  with the evidence that ruled it out) and the leads for the next round.
