---
name: skill-dream
description: Improve one ai-skills skill from its own past runs — cut every run out of the local Claude Code transcripts, find where the user had to correct it, chain it by hand, or watch a prescribed command fail, drop what later versions already fixed, and open a draft PR with the recurring fixes. This skill should be used when asked to "dream on a skill", improve or tune a skill from how it was actually used, or "what does the user keep correcting in <skill>".
argument-hint: "<skill> [--since 30d] [--max 60] [--min 3]"
disable-model-invocation: true
---

# Skill dream

A skill's transcripts record every time it fell short: the user said "too long", "in English", "why
didn't you check", ran the same follow-up by hand, or watched a command the skill prescribes fail.
This skill reads those runs with hindsight, the way a dream reads past sessions into memory, but the
memory it improves is the skill's own text.

Steps 1 to 3 read. Step 4 writes, only the themes the user picks, and only to a draft PR.

**Arguments:** `<skill>` is the directory name under `skills/` (`investigate`, not
`ai-skills:investigate`). `--since` (default `30d`, or a date) bounds the runs, `--max` (default 60)
caps how many run windows the analyzers read, `--min` (default 3) is the recurrence threshold in
distinct sessions.

**Run from a checkout of `BenjaminG/ai-skills`.** Step 2 diffs the skill's history and step 4 edits
it. Elsewhere, ask for the checkout's path.

**The repo is public.** Transcripts hold work content: Slack threads, tickets, customer names,
colleagues. Nothing from a transcript reaches a commit, the PR or a skill file except as a
paraphrase: no names, URLs, ticket ids or quotes longer than six words.

## 1. Extract

Resolve the script the way `review-mining` resolves its own, then run it from the checkout:

```bash
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/skill-dream/scripts/extract.py}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/skill-dream/scripts/extract.py 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/skill-dream/scripts/extract.py"; do
  [ -n "$c" ] && [ -f "$c" ] && EXTRACT="$c" && break
done
python3 -I "$EXTRACT" <skill> --since 30d --max 60
```

A run starts where the skill is invoked (`/ai-skills:<skill>` or a Skill tool call) and ends at the
next slash command, at another skill the model calls after the user replied, or after four user
messages. The script writes to `~/.claude/skill-dream-state/<skill>/<date>/`: one window per
candidate run in `windows/`, the skill's text at each version seen in `skill-versions/`,
`index.json`, and `summary.json`. A run is a candidate when the user wrote more than an approval,
interrupted it, or a tool call failed.

Echo the summary in one block: `invocations`, `candidates`, `dropped_candidates`, `reasons`, the
versions spanned, and the top of `next` and `handoffs`. Those last two are the chaining signal: what
the user said or ran right after the skill, over all runs.

- `invocations` below `--min`: too few runs to tell a pattern from an accident. Say so and stop.
- `dropped_candidates` above 0: the analyzers read the newest `--max` only. Say which dates that covers.
- A version missing from `version_commits` cannot be diffed in step 2; name it.

**Done when:** the summary is printed and the windows exist.

## 2. Analyze and organize

Resolve `scripts/workflow.js` the same way, then invoke it with the `Workflow` tool:

```
Workflow({
  scriptPath: <WF_SCRIPT>,
  args: {
    skill: "<skill>",
    outDir: "<out from the summary>",
    repo: "<absolute path of the checkout>",
    skillDir: "skills/<skill>",
    summaryPath: "<out>/summary.json",
    versionCommits: <version_commits from the summary>,
    windows: <index.json windows where candidate is true, each as {id, file, version, session}>
  }
})
```

The workflow gives batches of eight windows to read-only Haiku agents. Each reports frictions the
skill's text can be blamed for, each tied to the instruction involved (or its absence). One organizer
then groups them into themes and checks each theme against the commits since the run's version: a
theme a later commit already addresses comes back `fixed`. It returns `{themes, frictions, skipped,
failedBatches}`; each theme carries `sessions`, its count of distinct sessions.

- `failedBatches` above 0: those windows are not covered. Say how many.
- `organizerFailed`: stop, and report the frictions count so the run can be resumed with
  `resumeFromRunId`.

**Done when:** the themes are in hand.

## 3. Report

A theme **recurs** when `sessions >= --min`, whatever its kind. A chaining theme's `tally` is context
only: the organizer can match a follow-up to only one exact phrasing, so it undercounts. The
analyzers over-report (most windows yield a friction); the threshold is what filters one-offs, so
never lower it to fill the report. Write `<out>/report.md` and print it:

```md
# Skill dream: investigate, 2026-10-06 → 2026-11-05
104 runs · 60 read (27 older candidates not read) · 31 frictions · 9 themes: 3 open and recurring, 2 fixed since, 4 one-off

| # | Theme | Kind | Sessions | Change |
|---|-------|------|----------|--------|
| 1 | Offer the humanized summary instead of waiting to be asked | chaining | 48/104 | Add a closing step that offers the humanizer rewrite |
| 2 | Report language follows the destination, not the chat | correction | 5 | State the language rule in the Report step |

## 1. Offer the humanized summary instead of waiting to be asked
**Now:** "Print the report in chat." (SKILL.md, Report)
**Draft:** End with one line offering to rewrite the report through `humanizer` for Slack or the ticket.
**Evidence:** w004, w011, w023 (windows in <out>/windows/)

## Fixed since
- Claims checked before the report: 64ed81c (1.82.0) added the verification step

## One-off
- …
```

Then ask which rows to apply. A `conflict` theme is listed with both sides and never applied without
the user choosing a side.

**Done when:** the report is written and the user has named the rows (or none).

## 4. Draft PR

For the picked rows only:

1. `wt switch --create skill-dream/<skill>-<date>` in the checkout.
2. When `skills/<skill>/evals/README.md` exists, run it as it says on the current text first, and
   keep the scores as the baseline.
3. One commit per theme: edit the file the theme names, in the skill's style (imperative, verb first,
   progressive disclosure: detail goes to `references/`). Message: `fix(<skill>): <theme>`.
4. Rerun the evals. A score below the baseline means a theme made the skill worse: name the theme,
   drop its commit, and say so.
5. Show the diff. After a yes, push and open the PR with `gh pr create --draft`. The body says, for
   each theme, the paraphrased signal, the session count, the change, and the eval delta. Draft it
   through `ai-skills:humanizer`. No version bump: the release happens at merge.

**Done when:** the draft PR's URL is printed, or each picked row is named as skipped with its reason.
