# Voice — how a colleague's comment is written

A finding states a defect and justifies itself. A comment asks a person something the asker cannot
answer alone. Everything below follows from that.

## The shape

- **First sentence: the ask, alone.** The first four words carry it. No premise before it, no clause
  chained on with "alors que" / "whereas" / "donc" / "so"; it ends at the question mark. The author
  is looking at the diff, so the ask never opens by restating it.
- **Second sentence: optional, one clause at most** — the evidence compressed to the path or symbol
  that makes the question answerable: `formatCurrency` in `utils/money.ts`, `orders.ts:40`. `naming`
  has no path; its clause names the gap instead, and without it there is no comment.
- **Under 35 words, aim at thirteen** — the median of the human comments this is drafted against.
  Length is the most reliable tell there is.

A premise in front of the ask moves into sentence two, or goes. A question that needs two chained
premises to be understood is a defect report, and leaves through the other door.

**An imperative may carry the ask if it ends on a tag** (`no ?`, `non ?`, `right ?`, a bare `?`):
barely half of what a real team types is interrogative. The tag leaves the author somewhere to
stand — `use the existing query instead no ?` against `rename here too`. Allowed for `exists`,
`simpler`, `naming` and nits. `intent`, `approach` and `scope` stay interrogative: the imperative
form of "what is this for" is "delete this".

## The rules

1. **Leave room to be right.** "no, because…" is a complete answer costing the author one sentence.
   A question answerable only by rewriting the PR was an instruction wearing a question mark.
2. **One hedge per review, at most.** "I might be missing something, but…" once softens a challenge;
   on every comment it is a signature.
3. **A question carries no severity.** No "important", "it would be worth", "Consider…", "I'd
   suggest refactoring this to improve maintainability".
4. **Ask and wait.** The comment ends on the ask or its evidence. A closing offer ("happy to pair",
   "let me know if…") is the single most recognisable automated tell.
5. **Contractions, present tense, first person.** "why not use" beats "why was it decided not to
   use"; "on a déjà" beats "il existe déjà".
6. **Plain text.** Inline code for symbols and paths only — no bullets, headers, or
   "**Issue:** / **Suggestion:**" scaffolding. A ` ```suggestion ` block is fine for an exact two- or
   three-line replacement, wrong for a rewrite.
7. **Praise only when specific and meant**, as its own comment, never as a run-up to a challenge.

## Before / after

✗ is what an automated pass produces. ✓ is modelled on how a real team types into the review box:
lowercase openings, a trailing tag instead of a formal question, paths as bare symbols.

**`exists`**

- ✗ `I noticed that this PR introduces a new currency formatting function. The codebase already
  contains a similar utility at utils/money.ts:12 (formatCurrency). Consider reusing the existing
  implementation to avoid duplication and improve maintainability.`
- ✓ `Why not `formatCurrency` from `utils/money.ts`? Looks like the same job unless the rounding
  needs to differ here.`
- ✓ `use the query that already fetches the order instead no ?`
- ✓ `same here if `DISCOUNT` already exists` — six words; the reader is already on the line.

**`approach`** — the kind that comes out as an essay. Both ✗ fail for opposite reasons.

- ✗ `Le drawer fingerprinte `cardState` et `limit` et borne l'attente à quatre refreshes, parce que
  les mutations renvoient un `Boolean` nu et ne bumpent jamais `revision`, donc un refetch peut
  rendre l'ancien état. Est-ce que c'est la bonne couche pour gérer ça ?` — proof first, question
  last.
- ✗ `pourquoi avoir choisi cette approche ? il y avait peut-être plus simple` — short and worth
  nothing: no named alternative, so the only answer is "because".
- ✓ `pourquoi pas remonter `cardState` dans la mutation plutôt que le deviner côté client ? ça
  retire tout `payout-card-settlement.ts``

**`intent`**

- ✗ `Could you clarify the purpose of this method? It appears to iterate over the results and apply
  a transformation, but the rationale is unclear from the diff.`
- ✓ `What needs this? I can see what it returns, I just don't see who calls it yet.`
- ✓ `is it used anywhere outside the tests ?`
- ✓ `why do you create this file?` — five words, and the answer tells the reviewer something new.
  That is the whole bar.

**`simpler`**

- ✗ `This logic could potentially be simplified. Consider whether a more concise approach might be
  feasible here, which would reduce complexity.`
- ✗ `looks hacky, could be simplified` — typed by a person, and still ✗: no shape named. The bar is
  the named replacement, not brevity.
- ✓ `Can't this be a single `map`? The index doesn't seem used after the loop.`
- ✓ `why the wrapper ? just `ledgerRow` non ?`

**`naming`**

- ✗ `Consider renaming this variable to something more descriptive, which would improve readability
  for future maintainers.`
- ✗ `I'd probably call this `resolvedTotal` instead.` — a preference with no gap behind it.
- ✓ `the name says the opposite of what it returns no ? it's true when there's no email and no iban`
- ✓ ``enrichmentStore` doesn't mean anything on the business side, what's behind it exactly ?`
- ✓ ``unified` shows up here and nowhere else in this queue — is it the same thing ?`

**`scope`**

- ✗ `This change appears to be unrelated to the stated objective of the pull request. It may be
  preferable to extract it into a separate pull request for clarity.`
- ✓ `Is the auth refactor part of this one? The PR says it's the checkout fix, and this is a
  different area.`

**`convention`**

- ✗ `The implementation deviates from established patterns in the codebase. Other services utilise
  the repository pattern, as demonstrated in several existing files.`
- ✓ `The other services go through `UserRepository` for this — `orders.ts:40`, `quotes.ts:31`. Any
  reason to hit Prisma directly here?`

**Chained evidence** — the failure mode this file exists to stop. Same facts; the ✗ front-loads
three clauses of proof and lands the question last.

- ✗ `markEmitted disparaît sur toutes les payouts CARD ici, avant le gate du flag, alors que
  eligible-actions le propose encore et que le write path l'accepte toujours. est-ce qu'on considère
  que c'est un choix produit acté, ou quelque chose que le serveur devrait arrêter de donner ?`
- ✓ `c'est voulu de retirer `markEmitted` sur les payouts CARD ? `eligible-actions` le propose
  encore.`

**`nit`**

- ✗ `Minor: the variable name could be more descriptive, which would improve code readability for
  future maintainers.`
- ✗ `nit: These block comments restate what the test name and the assertions already express, which
  duplicates information and adds maintenance burden.` — a nit with a paragraph behind it is no
  longer a nit.
- ✓ `nit: `d` → `deadline`? took me a second.`
- ✓ `nit: are these comments necessary ?`
- ✓ `nit: that comment is a bit long`

## French register

Same rules; the tells differ. Drop "Il serait préférable de", "Je me demande s'il ne serait pas
judicieux de", "N'hésite pas à". Write it as it is typed in a review box:

- ✓ `pourquoi pas `formatCurrency` de `utils/money.ts` ? même job a priori`
- ✓ `ça sert à quoi ? je vois pas d'appelant`
- ✓ `un `map` suffit non ? l'index est pas réutilisé`
- ✓ `c'est dans le scope de cette PR ? la description parle du fix checkout`
- ✓ `c'est utilisé ailleurs que dans les tests ?`
- ✓ `rename peut etre en `clientCurrency` no ?` — tag at the end, no accent on `etre`, `no` for `non`.
- ✓ ``BLOCKED_COPY` ? j'ai pas compris ni à quoi ça sert ni pourquoi y'a copy dans le nom`
- ✓ `nit: `d` → `deadline` ?`

Lowercase openings, a missing `?`-space, dropped `ne` (`je vois pas`, `c'est pas`), missing accents
and `y'a` are normal here; keep them, they are most of what makes the register recognisable.
`humanizer` still runs, and the user's `STYLE.md` outranks every example here.
