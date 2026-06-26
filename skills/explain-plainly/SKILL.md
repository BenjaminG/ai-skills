---
name: explain-plainly
description: Re-explain a technical concept, code path, or review finding you just produced in plain language, for a reader who is not in that domain. Use when the user says it's "charabia"/gibberish, asks you to "explique simplement", "traduis en clair", "je comprends pas", "explain like I'm not a specialist", or otherwise signals the previous explanation was too jargon-dense.
---

# Explain plainly

The previous explanation was opaque because it led with jargon and named the
parts before the purpose. Re-explain with three moves, in order. Answer in the
user's language.

## 1. Ground in the why

Open with the **business purpose** — what problem this serves, in one or two
sentences a PM would nod at. No technical term yet.

Then give **one worked example with real numbers**. Concrete figures (30% / 20%
/ 50%, a one-third split, a specific date) are the anchor every term below hangs
on. Invent plausible numbers if the real ones aren't at hand — say so.

Completion criterion: the reader understands what the thing is _for_ before any
identifier or jargon word appears.

## 2. Map each term to plain meaning

Take every jargon word, identifier, or domain term from the original
explanation and give each **one row**: the term, then its meaning in everyday
words, tied back to the worked example. A short table is usually clearest.

Two rules that carry most of the clarity:

- **Flag old-vs-new explicitly.** If a field/concept is the _legacy_ one kept
  for compatibility, say so — "this is the OLD field, from before this change."
  Most confusion is a reader not knowing which era a name belongs to.
- **Translate, don't restate.** "fractional split → paying in three equal
  thirds, 33.33% each" lands; "fractional split → a split that is fractional"
  is a no-op.

Completion criterion: no term from the original explanation is left undefined.
Re-scan your own previous message and confirm every piece of jargon has a row.

## 3. Check and offer the next step

Close by asking if it's clearer, and offer the concrete next action (apply the
fix, see the corrections in plain terms, move on). Keep it to one or two lines.
