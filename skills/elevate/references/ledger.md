# Ledger rows

What a source subagent does: read one source over the window and return ledger rows. Read only;
post, react, label and edit nothing.

## Row

```
| Symptom | Where | Source | First seen | Last seen | Count | Links |
```

- **Symptom**: what went wrong, in the reporter's words, short ("pages slow while invoices are
  generated", "quote PDF generated twice"). A symptom, never a guessed cause.
- **Where**: the service, screen, endpoint, job or feature it hit, as precise as the source says.
- **Count**: occurrences in the window: messages, issues, error events, monitor triggers. Several
  reports of one event count once; say so in the row.
- **Links**: one or more permalinks: Slack message, Linear issue, Datadog view, commit.
- People appear by role ("a back-office user", "a partner"), never by name or email.

Merge rows that describe the same symptom in the same place. Return at most 40 rows, the most
frequent and the most recent first, and say how many were left out. Rows from a channel, team or
project the `priority` section lists are marked `priority` and kept past that cap.

In a replay (`--until`), read nothing dated after the window's end: filter by date in the query,
else drop the item and count it. Return that count with the rows.

**Done when** the whole window of the source is read and every row has a link.

## Per source

Use the tool and the names `docs/agents/signals.md` gives for the source.

- **datadog**: for each listed service in the production `env`: error rate and its top error
  groups, endpoints whose p95 latency drifted or spiked, timeouts, and the monitors that triggered
  most often in the window. Load the Datadog skill for the query syntax first.
- **slack**: in each listed channel and each priority channel, search the listed search words over the window, then read the
  threads with the most replies or reactions. A thread that says "again" or links an older one
  marks a recurrence: keep both dates.
- **linear**: issues with the listed bug or incident labels in the listed teams, created or updated
  in the window, plus every issue of a priority project, labelled or not. Note reopened issues,
  issues linked as duplicates, and customer needs when the doc says they are recorded.
- **posthog**: error tracking issues of the project, ordered by occurrences in the window.
- **git**: fix commits in the window, following the doc's convention, counted per top-level
  directory or package, plus reverts. A row per area with three fixes or more:
  "`<area>`: <n> fixes", the commit links, and the subjects that repeat.
