# QA Playbook

The playbook is what makes run N faster than run 1. It has two levels:

| Level | Lives in | Holds |
|---|---|---|
| **Site** | `~/.claude/qa-playbook/<repo>.md` | ticket-independent facts: env URLs, accounts, the login batch, quirks |
| **Scenario** | a single mutable `## QA Playbook` comment on the plan issue (`--tracker local`: `tasks/<TASK>/qa-playbook.md`) | one replayable block per `§X.Y` |

`<repo>` = `basename "$(git rev-parse --show-toplevel)"` — plain, so a human can
open and hand-edit it. A missing file means an empty playbook, never an error.

## The Preamble

Shipped boilerplate, **not** learned knowledge — it lives here so there is one
copy to fix, not one per repo. Every batch pastes it verbatim. `$CDP` is the
resolved path to the `chrome-cdp` skill's `scripts/cdp.mjs`; `$T` is the target
id the orchestrator resolved at pre-flight.

```bash
C(){ "$CDP" "$@"; }                        # act
# wait-for-element, doubles as the assertion
W(){ C eval $T "(async()=>{for(let i=0;i<40;i++){if(document.querySelector('$1'))return 'ok';await new Promise(r=>setTimeout(r,250))}throw new Error('wait: $1')})()"; }
# wait-for-text
A(){ C eval $T "(async()=>{for(let i=0;i<40;i++){if(document.body.innerText.includes('$1'))return 'ok';await new Promise(r=>setTimeout(r,250))}throw new Error('text: $1')})()"; }
# click-by-text — querySelector rejects :has-text()/:contains()
K(){ C eval $T "[...document.querySelectorAll('$1')].find(e=>e.textContent.trim()==='$2')?.click()??(()=>{throw new Error('no $1 with text $2')})()"; }
```

Why these work with no new script:

- `eval` runs `Runtime.evaluate` with `awaitPromise: true`, so an async polling IIFE **is** the wait primitive.
- Polls cap at 40 × 250ms = 10s. Do not raise it: `cdp.send` hard-rejects at 15s and you would lose the error message.
- A thrown JS error becomes `exceptionDetails`, the CLI exits 1, and `&&` stops the chain — so a batch fails at the first bad step and stderr names the selector.
- Keep selectors and assertion text free of single quotes; the helpers interpolate into a `'…'` JS literal.

## Site playbook template

````markdown
# QA site playbook — <repo>

## Env
- App: https://<app-host>
- BO: https://<bo-host>
- Mail: http://localhost:8025

## Accounts
- `admin` — qa-admin@example.com / <where the password comes from>
- `supplier` — …

## Login
Referenced from scenario blocks as `@login(admin)`. Idempotent — the isolated
profile keeps cookies between runs, so it may already be authenticated.

```bash
C nav $T "https://<bo-host>/login" \
  && { C click $T 'input[name=email]' && C type $T 'qa-admin@example.com' \
       && C click $T 'input[name=password]' && C type $T '<pw>' \
       && C click $T 'button[type=submit]' ; true; } \
  && W '[data-testid=bo-shell]' \
  && A 'qa-admin@example.com'
```

## Quirks
- <pagination / debounce / toast-timing / iframe gotcha, one line each>

## Not automatable
- <flow> — <why: canvas, cross-origin drag, OS file picker>
````

Two rules carry more weight than the format:

- **The login block ends in an `A '<account email>'` whoami assertion.** Isolated Chrome reuses `$HOME/.chrome-debug-profile`, so cookies survive between runs — run 2 can arrive pre-authenticated **as the wrong role**, silently invalidating every precondition below it. Asserting *identity*, not "the form is gone", is the only guard.
- **Idempotency is `{ …; true; }`, not branching.** `click` errors only when its element is absent, so "click if not already logged in" is safe to swallow; the trailing `W` + `A` decide whether the block worked.

Append-only, deduped by first line. If a section passes ~15 lines, say so in the
run summary — that is a signal the app is unstable, not a licence to grow the file.

## Scenario block template

```markdown
### §1.2 — Discount applies to a published house
**Fixture:** house `6f3a` (pinned — the scenario needs *this* record)
**Reach** — verified 20260820-141203
    @login(admin) && C nav $T "$BO/houses/6f3a" && W '[data-testid=house-detail]' && A 'Published'
**Verify** — verified 20260820-141203, run PASSED
    C click $T '[data-testid=apply-discount]' && W '[data-testid=discount-badge]' && A '15% applied'
**Manual tail:** none
**Stale:** 0
```

`Reach` gets to the precondition the plan declares. `Verify` exercises the
behaviour under test. The split is what keeps a failing run from teaching the bug
path as if it were the happy path — see **Learning** below.

**Every act is followed by a `W`/`A` on something that exists only in the
post-act state.** A fast path is a chain of act→assert pairs. That one rule
supplies the missing wait *and* makes a stale entry structurally incapable of
succeeding silently: the chain cannot advance past a state it failed to confirm.

## Selector policy

Record only these, in this order of preference:

1. `[data-testid=…]` / `[data-test=…]` / `[data-cy=…]`
2. `#id` — **unless** it looks generated. Reject `\d{4,}`, `:r[0-9a-z]+:` (React `useId`), `mui-\d+`, `headlessui-…`
3. `[name=…]`, `[type=submit]`, `[href="/exact/path"]`, `[aria-label=…]`, `[placeholder=…]`
4. `K '<css>' '<exact text>'`

**Never record:**

| Banned | Why |
|---|---|
| snap `ref=` / nodeId | invalidated by any action |
| `clickxy` coordinates | raw CSS pixels with **no element identity check** — clicks whatever now occupies that point |
| `querySelectorAll(...)[i]` | indices shift as the DOM changes |
| `:nth-child` on list rows | same, positional |

Each of these can *succeed on the wrong element*. A false PASS is worse than the
slow exploratory loop this playbook exists to remove.

**First-match caveat.** `querySelector` returns the first match, which is itself
positional. `[data-testid=row] a` is legitimate when the scenario says "any"; when
it depends on a specific record, pin it (`a[href="/houses/6f3a"]`) and record the
`Fixture:` line. Fixtures created fresh each run cannot be pinned — end `Reach`
at the creation step with a `W` on the resulting detail view.

**`clickxy`-only steps truncate the fast path.** Record `Reach`/`Verify` up to the
last CSS-addressable step; everything after goes in `Manual tail:` as prose, plus
the anchor selector so the next run re-derives coordinates from
`getBoundingClientRect` at replay time. A coordinate never enters the playbook.

## Learning

The scenario sub-agent returns `playbook.site` (0–2 new lines, tagged by section)
and `playbook.scenario` (a complete replacement block). The orchestrator merges
**once**, at end of run — nobody reads the playbook mid-run.

- **`Verify` may only be returned on a PASS.** It is a recording of a confirmed pass.
- **`Reach` may be returned from any verdict**, because it ends on a state the *plan* declares as a precondition, not on the behaviour under test. A FAIL therefore contributes `Reach` plus `Verify: none — <why>`: the next run gets the setup for free and still exercises the assertion by hand.
- SKIP and plan-defect contribute site lines only.

**Staleness — repair, then evict:**

| Situation | Action |
|---|---|
| `stale:*` and a new verified block came back | replace the block, `Stale: 0`. Self-healing; the common case. |
| `stale:*` and no new block | keep it, `Stale: 1`, append `<!-- broke at <sel> @ <ts> -->` |
| already `Stale: 1` and stale again | **delete the block.** A fast path that works half the time costs more than none — its failure surfaces only after a wasted batch. |

**Do not import `autobrowse-cc`'s keep-if-improved / revert-if-regressed loop.**
It tunes an unknown procedure against a *known-good* verdict. qa-run is the
inverse: the procedure is given by the plan, and the verdict is the unknown
output. Grading a playbook edit by "did the verdict improve" would reward edits
that turn real FAILs into PASSes — suppressing bug detection, the one thing this
skill exists to do. Replace-on-pass plus two-strike eviction is the whole policy.
