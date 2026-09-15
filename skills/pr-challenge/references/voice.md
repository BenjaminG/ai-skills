# Voice — how a colleague's comment is written

A reviewer's comment and a findings entry are different objects. A finding states a defect and
justifies itself. A comment asks a person something the asker cannot answer alone. Everything below
follows from that.

## The twelve rules

1. **Open with the ask, and let it stand alone.** Not with context, not with what you noticed,
   not with what the diff does. The author is looking at the diff; they know what it does. First four
   words carry the ask, and the first sentence ends at the question mark — evidence, if any, waits for
   the second sentence. Usually that ask is a question; rule 12 says when it may be an imperative
   instead, and the question mark is still where it ends.
2. **One or two sentences, under about 35 words — thirteen is the real median.** A person typing into
   a 300px box writes short. Length is the most reliable tell there is.
3. **Name the thing by path.** `utils/money.ts:12` or `formatCurrency` makes a question answerable
   in one sentence. "There may be an existing utility" makes it unanswerable, and reads as a guess —
   because it is one. The exception is `naming`, which has no path to give: there the clause naming
   the gap does the same work, and without it there is no comment.
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
12. **An imperative is allowed, if it keeps its tag.** Barely half of what a real team types is
    interrogative. The other half looks like `use the existing query instead no ?` or `rename to
    clientCurrency peut etre no ?` — an instruction with the tag that gives it back. That tag is the
    whole difference between those and `rename here too`, which leaves the author nowhere to stand.
    `exists`, `simpler`, `naming` and nits may open on an imperative ending in `no ?` / `non ?` /
    `right ?` / a bare `?`. `intent`, `approach` and `scope` stay interrogative — the imperative form
    of "what is this for" is "delete this".

## Before / after

The ✗ examples are invented — nobody writes those, they are what an automated pass produces. The ✓
examples are modelled on how a real team actually types into the review box: about thirteen words,
lowercase openings, a trailing tag instead of a formal question, and paths carried as bare symbols.

**`exists`** — the repo already has it.

- ✗ `I noticed that this PR introduces a new currency formatting function. The codebase already
  contains a similar utility at utils/money.ts:12 (formatCurrency). Consider reusing the existing
  implementation to avoid duplication and improve maintainability.`
- ✓ `Why not `formatCurrency` from `utils/money.ts`? Looks like the same job unless the rounding
  needs to differ here.`
- ✓ `use the query that already fetches the order instead no ?` — the imperative form of rule 12.
- ✓ `same here if `DISCOUNT` already exists` — six words, and it lands because the reader is already
  looking at the line.

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

**`intent`** — what is this for. Stays interrogative, always.

- ✗ `Could you clarify the purpose of this method? It appears to iterate over the results and apply
  a transformation, but the rationale is unclear from the diff.`
- ✓ `What needs this? I can see what it returns, I just don't see who calls it yet.`
- ✓ `is it used anywhere outside the tests ?`
- ✓ `why do you create this file?` — five words, and the author cannot answer it without saying
  something the reviewer did not already know. That is the whole bar.

**`simpler`** — the shorter shape.

- ✗ `This logic could potentially be simplified. Consider whether a more concise approach might be
  feasible here, which would reduce complexity.`
- ✗ `looks hacky, could be simplified` — short, typed by a person, and still a ✗: no shape named, so
  the author can only guess at what to do. Brevity is not the bar; the named replacement is.
- ✓ `Can't this be a single `map`? The index doesn't seem used after the loop.`
- ✓ `why the wrapper ? just `ledgerRow` non ?`

**`naming`** — the name promises one thing, the code is another. No path to cite, so the clause
carries it.

- ✗ `Consider renaming this variable to something more descriptive, which would improve readability
  for future maintainers.`
- ✗ `I'd probably call this `resolvedTotal` instead.` — short, and still a ✗: a preference with no gap
  behind it. §5 drops it as taste with no cost.
- ✓ `the name says the opposite of what it returns no ? it's true when there's no email and no iban`
- ✓ ``enrichmentStore` doesn't mean anything on the business side, what's behind it exactly ?`
- ✓ ``unified` shows up here and nowhere else in this queue — is it the same thing ?`

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

**`nit`** — kept, and marked as cheap. Comment noise lives here, not in a kind of its own: a comment
that restates the line under it costs the author one commit and buys the next reader a little, which
is the definition of a nit.

- ✗ `Minor: the variable name could be more descriptive, which would improve code readability for
  future maintainers.`
- ✗ `nit: These block comments restate what the test name and the assertions already express, which
  duplicates information and adds maintenance burden.` — a nit with a paragraph behind it is not a
  nit any more.
- ✓ `nit: `d` → `deadline`? took me a second.`
- ✓ `nit: are these comments necessary ?`
- ✓ `nit: that comment is a bit long` — four words past the prefix, and it is the whole comment.

## French register

Same rules; the tells differ. Drop "Il serait préférable de", "Je me demande s'il ne serait pas
judicieux de", "N'hésite pas à". Keep it to how it is actually typed in a review box:

- ✓ `pourquoi pas `formatCurrency` de `utils/money.ts` ? même job a priori`
- ✓ `ça sert à quoi ? je vois pas d'appelant`
- ✓ `un `map` suffit non ? l'index est pas réutilisé`
- ✓ `c'est dans le scope de cette PR ? la description parle du fix checkout`
- ✓ `c'est utilisé ailleurs que dans les tests ?`
- ✓ `rename peut etre en `clientCurrency` no ?` — the imperative of rule 12, in the register it is
  actually typed in: tag at the end, no accent on `etre`, `no` for `non`.
- ✓ ``BLOCKED_COPY` ? j'ai pas compris ni à quoi ça sert ni pourquoi y'a copy dans le nom`
- ✓ `nit: `d` → `deadline` ?`

Lowercase openings, a missing `?`-space, dropped `ne` (`je vois pas`, `c'est pas`), missing accents
and `y'a` are all normal in French review boxes; do not correct them into prose. They are most of
what makes the register recognisable. `humanizer` still runs — it applies the user's `STYLE.md`,
which outranks every example here.
