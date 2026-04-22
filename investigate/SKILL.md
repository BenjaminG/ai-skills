---
name: investigate
description: Investigate a task or conversation from an issue tracker (Linear or Jira) or Slack. Fetch context from the tracker ticket, Slack threads, previous work, and the codebase to understand an issue and plan next steps. This skill should be used when asked to investigate, look into, or gather context about an issue ID (e.g. ENG-1234, MITB-565), an issue URL (Linear or Jira), or a Slack message/thread URL.
argument-hint: "[ISSUE-ID, Linear/Jira URL, or Slack thread URL]"
disable-model-invocation: true
---

# Phase 1 — Context Gathering (sequential, no parallelism)

> **CRITICAL:** Complete ALL of Phase 1 before starting Phase 2. Do NOT launch any code search, devsql queries, or subagents until the ticket/thread content is fully available and summarized. The entire point of this phase is to build context that makes Phase 2 searches effective.

## 1.0 Detect Input Type

Inspect `$ARGUMENTS` to determine the source:

**Slack URL** (matches `https://<workspace>.slack.com/archives/<channel_id>/p<timestamp>`):
- Extract `channel_id` from the path segment after `/archives/` (e.g., `C09JSQNCR33`)
- Extract message timestamp: remove the `p` prefix from the last path segment, insert `.` before the last 6 digits (e.g., `p1773934352256539` → `1773934352.256539`)
- Proceed to Step 1.1a.

**Linear URL** (contains `linear.app`):
- Parse the issue ID from the path (pattern: `[A-Z]+-\d+`, e.g., `linear.app/<workspace>/issue/ENG-1234/...` → `ENG-1234`)
- Proceed to Step 1.1b.

**Jira URL** (contains `atlassian.net`):
- Parse the issue ID from the path (pattern: `[A-Z]+-\d+`)
- Proceed to Step 1.1b.

**Bare issue ID** (matches `[A-Z]+-\d+`):
- Use the ID directly. Linear and Jira IDs share the same shape; the tracker is resolved in Step 1.1b.
- Proceed to Step 1.1b.

If the input is unclear, ask the user to clarify.

## 1.1a Fetch Slack Thread

Read the thread using the extracted channel_id and message timestamp:

```
mcp__claude_ai_Slack__slack_read_thread channel_id: "<channel_id>" message_ts: "<timestamp>"
```

If the message has no replies (not a thread parent), fetch surrounding channel context instead:

```
mcp__claude_ai_Slack__slack_read_channel channel_id: "<channel_id>" latest: "<timestamp>" limit: 20
```

From the messages:
- Summarize the conversation: who said what, key decisions, action items, questions raised
- Extract all issue IDs mentioned (pattern: `[A-Z]+-\d+` — matches both Linear and Jira)
- Note any links to PRs, Linear/Jira issues, Confluence pages, or other resources

If issue IDs were found, proceed to Step 1.1b for each ID. Otherwise, skip to Step 1.2.

## 1.1b Resolve Tracker and Fetch Issue Details

Issue IDs from Linear and Jira share the `[A-Z]+-\d+` shape, so resolve the tracker before fetching. Try Linear first, fall back to Jira:

```bash
if linear issue view <ID> >/dev/null 2>&1; then
  TRACKER=Linear
else
  TRACKER=Jira
fi
```

Requires the `linear` CLI on PATH (provided by the `linear-cli` skill). If `linear` is unavailable, treat the ID as Jira.

**If `TRACKER=Linear`:** Use the `linear-cli` skill to retrieve issue details (`linear issue view <ID>`, comments, related issues, attachments).

**If `TRACKER=Jira`:** Use the `acli` skill to retrieve issue details (description, status, assignee, attachments, linked issues, comments).

Record the tracker (`Linear` or `Jira`) alongside each ID so later steps and the context summary reference the correct source.

## 1.2 Produce Context Summary

After fetching the ticket(s)/thread, write down a structured summary before proceeding. This summary is the input for Phase 2:

- **Source:** Slack thread, Linear issue, or Jira issue (include ID and tracker)
- **Subject:** One-line summary of the issue
- **Description:** Key details from the ticket body or thread
- **Key terms:** Entity names, feature names, error messages, module names, API endpoints mentioned
- **Relevant systems/modules:** Which parts of the codebase are likely involved
- **People:** Who reported, who is assigned, who commented

Do NOT proceed to Phase 2 until this summary is written.

---

# Phase 2 — Investigation (can parallelize, driven by Phase 1 context)

> **CRITICAL:** Every search in this phase MUST use the key terms, entity names, error messages, and module names extracted in Step 1.2. Do not search for generic terms — use the specific context from the ticket/thread.

## 2.1 Fetch Previous Work and Code Investigation

Run these in parallel, using the context summary from Step 1.2:

**Previous work (devsql):**
Use devsql skill to query for previous work related to the issue. Search using the issue ID, subject keywords, and entity names from the context summary. Look for past commits, prompts, and related discussions.

**Code investigation:**
Search the codebase using the specific terms from the context summary:
- Use entity names, error messages, and feature names as search terms
- Look for files/modules identified in "Relevant systems/modules"
- Search for recent changes (`git log`) related to the ticket's area — including the issue ID (both Linear and Jira IDs commonly appear in branch names and commit messages)
- Review the code to identify potential root causes or areas requiring changes

## 2.2 Plan Next Steps

Based on the information gathered from the tracker (Linear or Jira), Slack, previous work, and code investigation, outline the next steps for addressing the task. If the issue is clear and actionable, switch to plan mode and create a detailed plan for how to proceed with the task, including any necessary code changes, testing, and documentation updates. If further investigation is needed, identify specific areas to focus on in the next round of investigation. If the investigation started from a Slack thread, incorporate the conversation context alongside tracker and code findings when outlining next steps.
