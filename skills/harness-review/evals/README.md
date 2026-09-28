# harness-review evals

Three merged naboo PRs, frozen. Each case holds:

- `pr.json`: the output of `fetch-pr.py <n> --full` at the time the case was labelled, so the input
  never drifts.
- `expected.md`: the cause table labelled by hand, in the skill's report format. Only the item keys
  and their levels are scored; cause names, coverage and targets are for the human reading a diff.

## Run

For each case, give a fresh subagent this prompt, from a naboo checkout:

> Follow `skills/harness-review/SKILL.md` steps 2 to 4 on PR #<n>. Use
> `skills/harness-review/evals/pr-<n>/pr.json` as the step 1 output instead of fetching. Write the
> step 4 report to `skills/harness-review/evals/results/<timestamp>/pr-<n>.md` and stop: do not ask
> which rows to act on.

Then score each report:

```bash
python3 skills/harness-review/evals/score.py evals/pr-<n>/expected.md evals/results/<timestamp>/pr-<n>.md
```

`agreement` is the share of items placed at the expected level. `actionable P/R` is precision and
recall on the items that deserve a harness fix (levels 1 to 4): low precision means the skill
invents rules for one-offs, low recall means it lets real causes go. Rerun after every edit to
`SKILL.md` or `references/levels.md`, and compare with the previous `results/` run.
