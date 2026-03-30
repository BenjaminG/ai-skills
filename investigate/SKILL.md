---
name: investigate
description: Investigate a task or conversation from Jira or Slack. Fetch context from Jira tickets, Slack threads, previous work, and the codebase to understand an issue and plan next steps. This skill should be used when asked to investigate, look into, or gather context about a Jira key, Jira URL, or Slack message/thread URL.
argument-hint: "[JIRA-KEY, Jira URL, or Slack thread URL]"
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

**Jira key or URL** (matches `[A-Z]{2,}-\d+` pattern or contains `atlassian.net`):
- Extract the Jira key. If a full URL, parse the key from the path.
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
- Extract all Jira issue keys mentioned (pattern: `[A-Z]{2,}-\d+`)
- Note any links to PRs, Confluence pages, or other resources

If Jira keys were found, proceed to Step 1.1b for each key. Otherwise, skip to Step 1.2.

## 1.1b Fetch Task Details from Jira

Use /acli skill to retrieve and review details about a task from Jira.
Fetch the task's description, status, assignee, attachments, linked issues, and any relevant comments to understand its context and current state.

## 1.2 Produce Context Summary

After fetching the ticket/thread, write down a structured summary before proceeding. This summary is the input for Phase 2:

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
Use devsql skill to query for previous work related to the issue. Search using the ticket key, subject keywords, and entity names from the context summary. Look for past commits, prompts, and related discussions.

**Code investigation:**
Search the codebase using the specific terms from the context summary:
- Use entity names, error messages, and feature names as search terms
- Look for files/modules identified in "Relevant systems/modules"
- Search for recent changes (`git log`) related to the ticket's area
- Review the code to identify potential root causes or areas requiring changes

## 2.2 Plan Next Steps

Based on the information gathered from Jira, Slack, previous work, and code investigation, outline the next steps for addressing the task. If the issue is clear and actionable, switch to plan mode and create a detailed plan for how to proceed with the task, including any necessary code changes, testing, and documentation updates. If further investigation is needed, identify specific areas to focus on in the next round of investigation. If the investigation started from a Slack thread, incorporate the conversation context alongside Jira and code findings when outlining next steps.
