---
name: triage-findings
description: This skill should be used to act on the findings of a previous gate-wf run — select a subset by tier, by rule family, by id, by file, or by a free-text intent ("only the ones that shrink the code"), then fix them after one confirmation. Triggers on "/triage-findings", "fix the blockers", "clean up the nits", "apply the gate findings", "take the findings that simplify the code". Requires a prior gate-wf run on the branch; it never launches one.
argument-hint: "[blockers | majors | nits | cleanup | bugs | all | <ids> | <file> | free text]"
---

# Triage findings

Act on what `gate-wf` found. The gate produces a verdict and does not touch code;
this skill picks a subset of its findings, proposes a plan, and — once confirmed —
applies and verifies it.

It **never runs `gate-wf`**. A gate run is dozens of agents; launching one from a
command the user expects to be cheap is never right. No state on the branch → say
so and stop.

## Arguments

`$0…` — the selector, as one phrase. Literal selectors are matched exactly:

| Selector | Selects |
| --- | --- |
| _(none)_ | BLOCKER + MAJOR |
| `blockers` / `majors` / `nits` | that tier |
| `all` | everything fresh |
| `cleanup` | `slop-*`, `simplify-*`, `ponytail-*` — the ones that delete rather than add |
| `bugs` | `bug-*`, `security-*` |
| `B1 M2 N7` (or `B1,M2`) | those findings |
| `a.ts` / `src/utils/a.ts` | findings in that file |

Anything else is a free-text intent. The script then prints the whole fresh set
and you pick from it by meaning — `"prioritize findings that reduce code size"`,
`"everything touching money"`, `"nothing in the tests"`.

## Step 1: Get the plan

Resolve the script (same order as gate-wf resolves `workflow.js`), then run it:

```bash
TRIAGE=""
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/triage-findings/scripts/triage.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/triage-findings/scripts/triage.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/triage-findings/scripts/triage.py"; do
  [ -n "$c" ] && [ -f "$c" ] && TRIAGE="$c" && break
done
[ -z "$TRIAGE" ] && { echo "triage-findings: triage.py not found — reinstall the plugin" >&2; exit 2; }

python3 "$TRIAGE" plan <selector...>
```

It reads gate-wf's `$STATE_FILE`, **drops findings the code has outrun** (each
finding carries the content anchor stamped when the gate ran; if the flagged line
reads differently at HEAD, the finding is obsolete and is not proposed), applies
the selector, and prints the survivors **grouped by file** with `what` / `evidence`
/ `lead` / `rule` per finding.

If it reports outdated findings, say how many in your plan — that number is the
signal that `gate-wf` is due for a re-run, and it is the user's call, not yours.

## Step 2: Turn it into a plan the user can judge

Read the grouped output and each file it names. Three things to settle before you
propose anything:

1. **Pull out what needs a decision, not a fix.** A code/spec disagreement
   (`bug-spec-mismatch` is the usual one, but judge, don't pattern-match) has no
   mechanical answer — the code says one thing, the PR body or the Linear AC says
   another, and only the author knows which is wrong. List those separately as
   **decision required**, with the two readings stated plainly, and keep them out
   of the batch. Never pick a side yourself: guessing on a spec disagreement
   writes a bug with confidence.
2. **Reconcile findings that fight.** Two findings in one file can pull opposite
   ways, and a fix in one file can invalidate one in another (moving an export
   changes its importers). Say what you will do when they conflict, in the plan,
   before touching anything.
3. **`suggested_fix` is a lead, not an instruction.** The reviewer saw the diff,
   never the whole file — it is right about the problem and only sometimes right
   about the remedy. Read the real code and decide. If your fix differs from the
   lead shown in the plan, say so in Step 6.

Present, per file: the path, the findings by id, and one sentence each on what
will change. Mark `unverified` findings — NITs are shown but never adversarially
checked, so `nits` and `cleanup` batches are entirely unverified; the user's
confirmation is what verifies them.

## Step 3: Confirm

Ask once, with `AskUserQuestion`: apply the batch as planned, or narrow it. Include
the decision-required list in the message, not as a question — it is context for
the choice, not a second exam.

Stop here if the user declines. Do not apply "just the safe ones" on your own.

## Step 4: Apply

Sequentially, yourself, file by file in the order shown. No subagents: the plan
groups by file so writes never collide, but meaning does — a fix that moves a
symbol changes files another finding owns, and a per-file agent cannot see that.

## Step 5: Verify

What decides the depth is **the diff you produced**, not the finding's `rule_id`.
A `simplify-redundant` whose fix rewrites three calculations is logic; a
`solid-dip` that only moves an import is not.

- Diff touches only comments, imports, or dead exports → run the project's typecheck.
- Diff touches anything else → typecheck **plus** the tests covering the changed
  files. Money, auth and data paths are never exempt: an unverified fix there moves
  the risk instead of removing it.

Failure → **one** repair attempt, then stop, show the actual error output, and
leave every change in place. Do not loop on repairs, and never `git checkout` the
batch: that throws away eight correct fixes for a ninth bad one.

## Step 6: Record and report

```bash
python3 "$TRIAGE" mark-fixed B1,N2,N4
```

Marks those findings `fixed` in gate-wf's state — they stay on the record but stop
counting toward the verdict, which is recomputed. Nothing is committed: the commit
is the user's, and nine cleanup fixes under a message they did not write is a
favour nobody wants.

Then report, briefly:

- what was fixed, by id;
- where your fix diverged from the reviewer's lead, and why;
- what is left — decision-required items, outdated findings, anything the user cut
  in Step 3, and any verification that failed.

Do not re-print the gate report. `gate-wf` re-renders on demand, and the state is
already up to date.

## Notes

- **Reads, never writes, gate-wf's schema**: `scripts/triage.py` imports
  `skills/gate-wf/scripts/findings.py` rather than copying it. The content anchor
  in particular must have exactly one implementation — a second copy that drifts
  would make freshness and dismissals disagree about the same line.
- **Fixed vs dismissed**: `fixed` means the code changed; dismissed means the
  finding was wrong. Use `gate-wf --dismiss <ids>` for the second — a dismissal is
  durable and lifts by itself if the code is later edited.
- **A fix that silently failed reopens by itself**: the next gate run re-flags it,
  because the code did not change the way the fix claimed.
