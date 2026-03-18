---
name: investigate
description: Fetch and review details about a task from Jira.
argument-hint: "[JIRA-KEY]"
disable-model-invocation: true
---

## 1. Fetch Task Details from Jira
Use /atlassian-cli-jira skill to retrieve and review details about a task from Jira.
Fetch the task's description, status, assignee, attachments, linked issues, and any relevant comments to understand its context and current state.

## 2. Fetch previous work and conversations
Use devsql skill to query for any previous work, discussions, or related tasks that might provide additional context about the issue at hand. This can include past commits, pull requests, or any relevant documentation.

## 3. Code Investigation
Search the codebase for any relevant files, functions, or modules that are related to the task. Review the code to identify potential areas that might be causing issues or require changes.

## 4. Plan Next Steps
Based on the information gathered from Jira, previous work, and code investigation, outline the next steps for addressing the task. If the issue is clear and actionable, switch to plan mode and create a detailed plan for how to proceed with the task, including any necessary code changes, testing, and documentation updates. If further investigation is needed, identify specific areas to focus on in the next round of investigation.