# Symptom explainer artifact

A private Artifact page that tells the user the story of the symptom in plain
words while the Explore agents dig, then carries the diagnosis once they report.
One file, one URL for the whole investigation. The symptom may turn out to be a
bug, a data problem, or the intended behaviour: the page says which once it is
known, and never assumes it up front. Write it in the user's language and apply
`explain-plainly` to every sentence: no identifier appears before the glossary
defines it.

Before writing the file, load the `artifact-design` skill (the Artifact tool
requires it). Publish with `icon: "bug"`, from a file in the scratchpad named
after the source (`<ISSUE-ID>-explainer.html`, or `<channel_id>-<ts>-explainer.html`
for a Slack thread), so the §7 republish reuses that path and keeps the URL.

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

Republish the same file path once both syntheses are merged. The page now
reads top to bottom as the answer, in this order:

1. **Banner**: the real state — **cause trouvée** (bug, data, or intended
   behaviour, said plainly) or **pas encore trouvée**.
2. **Avant / après** (when the symptom shows on a screen): two mock-ups of
   that screen side by side. **Avant** is what the user sees in prod today;
   **après** is what they would see under the proposed rule. Build each in HTML
   from the component's source — its layout, its labels, its translation
   strings — and fill both with the verified prod values, the left through the
   current logic, the right through the proposed one. Highlight every value
   that differs. Caption the pair *maquette reconstruite depuis le code, pas une
   capture*; when the cause is not yet confirmed as a bug, caption **après** as
   a proposal to validate. A symptom with no screen (a job, an API, an export)
   keeps the two-lane diagram of block 2 in this slot instead.
3. **Cause**, in plain words, with the two-lane diagram now pointing at the
   component where the paths split.
4. **Timeline** of the data: what happened to the record, and when, from the
   prod logs.
5. **Questions from the source**: each question the ticket or thread asked,
   answered in one or two sentences, pointing at the **avant / après** when it
   shows the answer.
6. **What changes, what stays**: the proposed fix, and what it leaves untouched
   and why.
7. **Glossary**.
8. A `<details>` section, collapsed, holding the `file:line` root cause, each
   claim tagged **verified** (the query, audit id or `file:line` that proves it)
   or **not reproduced**, and the files, tests and docs to touch.

**Pas encore trouvée**: drop blocks 2, 3 and 6; add the hypotheses ruled out
(each with the evidence that ruled it out) and the leads for the next round.
