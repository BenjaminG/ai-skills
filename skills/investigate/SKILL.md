---
name: investigate
description: Pull the full context of a Linear/Jira issue or Slack thread — ticket, thread, prior work, code — then plan next steps.
argument-hint: "[ISSUE-ID, Linear/Jira URL, or Slack thread URL]"
disable-model-invocation: true
---

Read everything humans already wrote about the issue **before** touching the codebase, then search the code with the ticket's own words. Phase 1 runs alone; Phase 2 fans out.

# Phase 1 — Gather context (sequential)

## 1. Detect the source in `$ARGUMENTS`

| Input | Extraction | Next |
|---|---|---|
| `https://<ws>.slack.com/archives/<channel_id>/p<digits>` | `channel_id` = segment after `/archives/`; `ts` = drop the `p`, insert `.` before the last 6 digits (`p1773934352256539` → `1773934352.256539`) | §2 |
| URL containing `linear.app` or `atlassian.net` | issue ID = `[A-Z]+-\d+` in the path | §3 |
| Bare `[A-Z]+-\d+` | use as-is | §3 |

## 2. Read the Slack thread

With the Slack MCP, read the thread at `channel_id` / `ts`. A message with no replies is not a thread parent: read the ~20 channel messages up to `ts` instead.

Summarize who said what, decisions, open questions. Collect every `[A-Z]+-\d+` and every PR/issue/doc link. For each issue ID found, run §3.

## 3. Resolve the tracker and read the issue

Linear and Jira IDs share one shape, so probe: `linear issue view <ID>` succeeds → Linear (use the `linear-cli` skill for details, comments, related issues, attachments); otherwise Jira (`acli jira workitem view <ID>`). Record the tracker next to each ID.

## 4. Read the evidence (both sources)

- **Images**: read every attached screenshot — they carry the on-screen error, UI state or stack trace nobody retyped.
- **Links**: `WebFetch` the docs that bear on the issue (runbooks, Confluence, specs); leave the rest. PR links wait for Phase 2, issue links go through §3.

## 5. Write the context summary

Phase 1 is complete when this summary is written, with every field filled or explicitly marked none:

- **Source**: Slack thread / Linear issue / Jira issue, with ID and tracker
- **Subject**: one line
- **Description**: key details from the body or thread
- **Key terms**: entity names, feature names, error messages, module names, endpoints
- **Relevant modules**: where in the codebase this likely lives
- **Visual evidence**: what the images show
- **Linked resources**: takeaways from fetched docs; PR numbers for Phase 2
- **People**: reporter, assignee, commenters

# Phase 2 — Investigate (parallel, driven by the summary)

Every search below uses the **key terms** of §5 verbatim — the error string, the entity name, the issue ID — so that results are specific to this ticket.

## 6. Two Explore agents, one message

Spawn both with `Agent` (`subagent_type: "Explore"`) in a single message, each carrying the full §5 summary. Each returns a **synthesis** (`file:line` + hypotheses), never raw rows or diffs.

- **`prior-work-scout`** — via the `devsql` skill (`history` / `jhistory`), search the issue ID, subject keywords and entity names. Synthesis: what was already tried or touched.
- **`code-investigator`** — grep the key terms, read the modules of §5, `git log` around that area including the issue ID (it appears in branch names and commit messages), and `gh pr view <n> --json title,body,comments,reviews` + `gh pr diff <n>` for any PR from §5. Synthesis: candidate root causes and files to change.

Done when every key term of §5 has been searched by at least one agent.

**Symptom** (§5 describes something observed on a screen or in the data, whether or not it is a bug yet): in the same turn as the `Agent` calls, build and publish the explainer draft per [`references/symptom-explainer.md`](references/symptom-explainer.md), without waiting for either agent.

**Symptom with an error signature**: also query Datadog logs for that signature/tenant when the Datadog MCP is present, so the root cause is checked against production and not code alone.

## 7. Synthesize and plan

Merge both syntheses into one picture. Before reporting, check every factual
claim yourself — the ticket's, the thread's, the user's and the agents' — against
code, prod data (BigQuery, Datadog, local clone) and the attached files (open the
PDF). Run a read-only check rather than ask whether to run it. A claim no source
can confirm stays in the report labelled **not reproduced**, never stated as the
cause.

Answer in the user's language. Text meant for a ticket, a PR, a channel or
another person goes in the language that destination already uses; English when
it is mixed or empty.

**Symptom**: republish the explainer with the diagnosis per
[`references/symptom-explainer.md`](references/symptom-explainer.md). The page
carries the length — the **avant / après**, the cause, the timeline, the
technical detail — so the terminal stays short. The report is done when the
republished link is in the terminal, under exactly these lines:

1. What the user sees, with the real values, then what they would see instead.
2. The cause in one plain sentence, or **pas encore trouvée**.
3. The page link.
4. Each question the source asked, answered in one line.
5. The decision: the options, your pick, and the words that launch it.

**No symptom** (a question, a feature request): report in two blocks — plain
language first, technical detail second.

**What is happening** — apply the `explain-plainly` skill to your own conclusion:
open with the purpose and the user-visible symptom in two sentences with zero
jargon, add one worked example with real numbers (invent plausible ones and say
so if the real ones aren't at hand), then a one-row-per-term table mapping every
identifier, field name and domain word to everyday words. No term you use below
is left undefined, and old-vs-new fields are flagged as such.

**Technical detail** — root cause with `file:line`, each claim tagged
**verified** (the query or `file:line` that proves it) or **not reproduced**, and
the files, tests and docs to touch.

If the issue is clear and actionable, switch to plan mode with those code
changes. Otherwise, name the precise areas to dig next round.
