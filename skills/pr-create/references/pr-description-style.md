# PR Description Style — Worked Before/After Example

This is the standard for `fix` and `feature` PR descriptions: lead with the
functional story, explain the cause in everyday language, drop the implementation
detail. The reviewer reads the diff and commits for the code; the description exists
to make the *point* understandable to anyone.

The example below is a real fix PR. The "before" is how an implementation-first
description reads. The "after" is the target.

---

## ❌ Before — implementation dump (don't do this)

> ### Root Cause
>
> `clientRequest.companySnapshot` is a denormalized copy of the associated company.
> Since #13411, the `getCompany` field resolver serves `company.name` from
> `companySnapshot` (under flag `BOOKING_SNAPSHOT_QUERY_PATH`) for snapshot-covered
> selections — and `GetClientRequestBriefAdmin` selects exactly `company { _id name }`.
> But `companySnapshot` was refreshed only by the Atlas trigger
> `sync-client-request-company-snapshots`, which fires on `companymodels` updates —
> never when a clientRequest's `companyId` changes. […]
>
> ### Fix
>
> New pure helper `buildCompanySnapshotFields(company)` returning the aligned
> `{ companyId, companyName, companySnapshot }` write-fragment. Wired into all 5 sites:
> `createClientRequest`, `updateClientRequestBriefAdmin`, `createReInvoicingClientRequest`,
> `submitWhiteLabelBrief`, `adminUpdateClientRequestEntity`, `userUpdateClientRequestEntity`.
> Backfill migration `1781180649000-bof-424-…ts` realigns drifted docs via `$lookup`…

**Why it fails:** symbol names, file paths, flags, the "5 write paths", migration
internals. A non-technical reader is lost; even a developer has to reconstruct the
functional meaning themselves.

---

## ✅ After — functional-first (do this)

> ### What this fixes
>
> In the back office, every transaction has a "Client brief" tab where an admin picks
> the **associated company**. Picking a new company, saving, and watching the field
> snap back to the old one — that's what this fixes. (Reported as `KUDELSKI SECURITY
> FRANCE` reverting to `intersec group`.)
>
> ### Why it happened
>
> To stay fast, the app keeps a **photocopy** of the company's details right next to
> the transaction, and the screen reads the name from that photocopy. When the admin
> switched companies, the app updated the **link** to the new company but forgot to
> redo the photocopy — so the screen kept showing the old name, even though the
> underlying link was correct.
>
> ### How it's fixed
>
> The link and the photocopy are now always updated together, so they can't disagree
> anymore. A one-off cleanup also repairs transactions whose photocopy had already
> drifted.
>
> In a nutshell: changing a transaction's company used to update the link but not the
> displayed copy, so the old name came back. Now both update together, and existing
> bad data is repaired.
>
> ### Related Issues
>
> **Linear issue**: https://linear.app/naboo-team/issue/BOF-424

**Why it works:** the analogy ("photocopy") carries the whole mechanism; no code
identifiers appear; it ends with a one-sentence recap.

---

## When technical detail *is* justified

The rule isn't "never be technical" — it's "be technical only when the change itself
is technical." Calibrate to the nature of the change:

| Nature of change | Technical detail |
|---|---|
| User-facing bug, feature with no notable internal shift | **Out.** Functional story only; reviewer reads the diff for code. |
| Data-model / schema change, structural refactor, infra or technical-only work | **In, deliberately.** After the plain-language framing, add the schema, a small diagram, the key concept under its real name, or the relevant business logic — whatever a reviewer needs to evaluate it. |

Even when detail is warranted: still **open with plain language** (what this changes
and why it matters), keep it to **what's needed to judge the change**, and signpost
precise terms rather than assuming the reader knows them. The difference between a
justified schema and a reflexive dump is whether each piece earns its place.

---

## Pre-publish check

Open with the functional story, then ask: **is this change functional or technical?**

- **Functional** → the description should contain none of: file names/paths,
  function/class/symbol names, flag/config-key names, "which service touches which"
  mappings, data-flow or migration internals. If any slipped in, rewrite that
  sentence at the behaviour level.
- **Technical** → keep only the detail a reviewer needs to evaluate the change
  (schema, diagram, key concept, business logic). Drop anything that doesn't earn its
  place. The diff still carries the line-by-line.
