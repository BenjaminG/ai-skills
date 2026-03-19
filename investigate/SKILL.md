---
name: investigate
description: Investigate a task or conversation from Jira or Slack. Fetch context from Jira tickets, Slack threads, previous work, and the codebase to understand an issue and plan next steps. This skill should be used when asked to investigate, look into, or gather context about a Jira key, Jira URL, or Slack message/thread URL.
argument-hint: "[JIRA-KEY, Jira URL, or Slack thread URL]"
disable-model-invocation: true
---

## 0. Detect Input Type

Inspect `$ARGUMENTS` to determine the source:

**Slack URL** (matches `https://<workspace>.slack.com/archives/<channel_id>/p<timestamp>`):
- Extract `channel_id` from the path segment after `/archives/` (e.g., `C09JSQNCR33`)
- Extract message timestamp: remove the `p` prefix from the last path segment, insert `.` before the last 6 digits (e.g., `p1773934352256539` → `1773934352.256539`)
- Proceed to Step 1a.

**Jira key or URL** (matches `[A-Z]{2,}-\d+` pattern or contains `atlassian.net`):
- Extract the Jira key. If a full URL, parse the key from the path.
- Proceed to Step 1b.

If the input is unclear, ask the user to clarify.

## 1a. Fetch Slack Thread

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

If Jira keys were found, proceed to Step 1b for each key. Otherwise, skip to Step 2.

## 1b. Fetch Task Details from Jira
Use /acli skill to retrieve and review details about a task from Jira.
Fetch the task's description, status, assignee, attachments, linked issues, and any relevant comments to understand its context and current state.

## 2. Fetch previous work and conversations
Use devsql skill to query for any previous work, discussions, or related tasks that might provide additional context about the issue at hand. This can include past commits, pull requests, or any relevant documentation.

## 3. Code Investigation
Search the codebase for any relevant files, functions, or modules that are related to the task. Review the code to identify potential areas that might be causing issues or require changes.

## 4. Plan Next Steps
Based on the information gathered from Jira, Slack, previous work, and code investigation, outline the next steps for addressing the task. If the issue is clear and actionable, switch to plan mode and create a detailed plan for how to proceed with the task, including any necessary code changes, testing, and documentation updates. If further investigation is needed, identify specific areas to focus on in the next round of investigation. If the investigation started from a Slack thread, incorporate the conversation context alongside Jira and code findings when outlining next steps.
