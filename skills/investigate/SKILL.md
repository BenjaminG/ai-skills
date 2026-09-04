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

Linear and Jira IDs share one shape, so probe: `linear issue view <ID>` succeeds → Linear (use the `linear-cli` skill for details, comments, related issues, attachments); otherwise Jira (use the `acli` skill). Record the tracker next to each ID.

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

**Bug with an error signature**: also query Datadog logs for that signature/tenant when the Datadog MCP is present, so the root cause is checked against production and not code alone.

## 7. Synthesize and plan

Merge both syntheses into one picture. If the issue is clear and actionable, switch to plan mode with the code changes, tests and docs to touch. Otherwise, name the precise areas to dig next round.
