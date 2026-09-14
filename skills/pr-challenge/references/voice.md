# Voice — how a colleague's comment is written

A reviewer's comment and a findings entry are different objects. A finding states a defect and
justifies itself. A comment asks a person something the asker cannot answer alone. Everything below
follows from that.

## The eleven rules

1. **Open with the question, and let it stand alone.** Not with context, not with what you noticed,
   not with what the diff does. The author is looking at the diff; they know what it does. First four
   words carry the ask, and the first sentence ends at the question mark — evidence, if any, waits for
   the second sentence.
2. **One or two sentences, under about 35 words — thirteen is the real median.** A person typing into
   a 300px box writes short. Length is the most reliable tell there is.
3. **Name the thing by path.** `utils/money.ts:12` or `formatCurrency` makes a question answerable
   in one sentence. "There may be an existing utility" makes it unanswerable, and reads as a guess —
   because it is one.
4. **Never restate the diff.** A comment whose first clause paraphrases the line it is attached to
   has spent its budget describing what both people can see.
5. **One hedge per review, maximum.** "I might be missing something, but…" is how a person softens
   a challenge. Twice in one review is a tic; on every comment it is a signature.
6. **No severity words, and no `Consider`.** No "important", "critical", "significant", "it would be
   worth", "I'd suggest refactoring this to improve maintainability". A question carries no severity
   — that is what makes it a question.
7. **No closing offer.** "Happy to pair on this", "let me know if you'd like me to open a
   follow-up", "happy to be wrong here". A colleague asks and waits. The offer is padding, and it is
   the single most recognisable tell in an automated review.
8. **Contractions, present tense, first person.** "why not use" beats "why was it decided not to
   use". "on a déjà" beats "il existe déjà".
9. **No structure.** No bullet lists, no bold headers, no tables, no "**Issue:** / **Suggestion:**"
   scaffolding in an inline comment. Inline code for symbols and paths only. A fenced
   ` ```suggestion ` block is fine when the replacement is two or three lines and exact — that is a
   thing people use — and wrong when it is a rewrite.
10. **No thanks, no padding praise.** "Nice work on this!" before a challenge fools nobody. Praise
    only when it is specific and you mean it, and then as its own comment.
11. **Leave room to be right.** Draft so that "no, because…" is a complete answer costing the author
    one sentence. A question the author can only answer by rewriting the PR was an instruction
    wearing a question mark.

## Before / after

**`exists`** — the repo already has it.

- ✗ `I noticed that this PR introduces a new currency formatting function. The codebase already
  contains a similar utility at utils/money.ts:12 (formatCurrency). Consider reusing the existing
  implementation to avoid duplication and improve maintainability.`
- ✓ `Why not `formatCurrency` from `utils/money.ts`? Looks like the same job unless the rounding
  needs to differ here.`

**`approach`** — the alternative the PR could have taken. Carries the most context behind it, so
it is the kind that comes out as an essay. Both ✗ fail for opposite reasons.

- ✗ `Le drawer fingerprinte `cardState` et `limit` et borne l'attente à quatre refreshes, parce que
  les mutations renvoient un `Boolean` nu et ne bumpent jamais `revision`, donc un refetch peut
  rendre l'ancien état. Est-ce que c'est la bonne couche pour gérer ça ?` — three chained clauses of
  proof, question last.
- ✗ `pourquoi avoir choisi cette approche ? il y avait peut-être plus simple` — short, question
  first, and worth nothing: the author can only answer "because". An `approach` with no named
  alternative is a ✗, not a short comment.
- ✓ `pourquoi pas remonter `cardState` dans la mutation plutôt que le deviner côté client ? ça
  retire tout `payout-card-settlement.ts``

**`intent`** — what is this for.

- ✗ `Could you clarify the purpose of this method? It appears to iterate over the results and apply
  a transformation, but the rationale is unclear from the diff.`
- ✓ `What needs this? I can see what it returns, I just don't see who calls it yet.`

**`simpler`** — the shorter shape.

- ✗ `This logic could potentially be simplified. Consider whether a more concise approach might be
  feasible here, which would reduce complexity.`
- ✓ `Can't this be a single `map`? The index doesn't seem used after the loop.`

**`scope`** — is this in this PR.

- ✗ `This change appears to be unrelated to the stated objective of the pull request. It may be
  preferable to extract it into a separate pull request for clarity.`
- ✓ `Is the auth refactor part of this one? The PR says it's the checkout fix, and this is a
  different area.`

**`convention`** — we do this differently.

- ✗ `The implementation deviates from established patterns in the codebase. Other services utilise
  the repository pattern, as demonstrated in several existing files.`
- ✓ `The other services go through `UserRepository` for this — `orders.ts:40`, `quotes.ts:31`. Any
  reason to hit Prisma directly here?`

**Chained evidence** — the failure mode this file exists to stop. Same content, same facts; the ✗
front-loads three clauses of proof and lands the question last, and nobody can act on it.

- ✗ `markEmitted disparaît sur toutes les payouts CARD ici, avant le gate du flag, alors que
  eligible-actions le propose encore et que le write path l'accepte toujours. est-ce qu'on considère
  que c'est un choix produit acté, ou quelque chose que le serveur devrait arrêter de donner ?`
- ✓ `c'est voulu de retirer `markEmitted` sur les payouts CARD ? `eligible-actions` le propose
  encore.`

**`nit`** — kept, and marked as cheap.

- ✗ `Minor: the variable name could be more descriptive, which would improve code readability for
  future maintainers.`
- ✓ `nit: `d` → `deadline`? took me a second.`

## French register

Same rules; the tells differ. Drop "Il serait préférable de", "Je me demande s'il ne serait pas
judicieux de", "N'hésite pas à". Keep it to how it is actually typed in a review box:

- ✓ `pourquoi pas `formatCurrency` de `utils/money.ts` ? même job a priori`
- ✓ `ça sert à quoi ? je vois pas d'appelant`
- ✓ `un `map` suffit non ? l'index est pas réutilisé`
- ✓ `c'est dans le scope de cette PR ? la description parle du fix checkout`
- ✓ `nit: `d` → `deadline` ?`

Lowercase openings and a missing `?`-space are normal in French review boxes; do not correct them
into prose. `humanizer` still runs — it applies the user's `STYLE.md`, which outranks every example
here.
