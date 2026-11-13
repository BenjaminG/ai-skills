# The signals doc

What `setup-ai-skills` writes in the host repo so a reader (elevate) can build a **symptom ledger**:
what users and the team saw go wrong in production, recently or again and again. The doc says where
each kind of symptom is reported and through which tool to read it. How a reader turns those places
into ledger rows is the reader's business, not the doc's.

```
docs/agents/signals.md   one section per source, each proven or marked unavailable
```

## Sections

Short entries. Each source section ends with its proof line (`proven <date>: <rows> rows over 30
days`) or `unavailable: <reason>` (no connector in the session, no access, the team does not use
it). Names and IDs only, never a token or a secret.

1. **datadog**: the connector or CLI that answered, the site, the production `env` tag, and the
   services that serve users, one line each: `<service>`: what a user sees when it degrades. Then
   the monitors or monitor tags worth reading, if the team keeps some.
2. **slack**: the connector that answered (when two are installed, the one that reached every
   listed channel, private ones included), then the channels by role: `bugs`, `incidents`,
   `support`, `ops` (alerts, deploys). One line each: `#<channel>`: role, who posts there. Then the
   **search words** the team uses for a symptom, in each language it writes in (`lent`, `timeout`,
   `en double`, `encore`, `slow`, `duplicate`, `again`).
3. **linear**: the tool that answered (`linear` CLI or connector; `issue-tracker.md` names the
   team's), the teams whose bugs land in this repo, the labels that mark a bug or an incident,
   whether customer needs are recorded.
4. **posthog**: the project, whether error tracking is on.
5. **git**: how a fix shows in history (commit prefix such as `fix:`, branch prefix such as `fix/`,
   revert commits), so a reader can count fixes per area.
6. **priority**: the Slack channels and the Linear teams or projects the user wants searched
   first, one line each with the reason. `none` is a valid answer. A reader traces the clusters
   that touch them before the larger ones.
7. **proof**: the date of the last proof and one line per source: rows found, or `unavailable`.

## Explore

- **Connected tools**: the session's MCP servers and CLIs for each source. List every Slack
  connector, not only the first one found.
- **Datadog in the repo**: `DD_SERVICE`, `DD_ENV`, `service:` tags, `dd-trace` init, deploy
  manifests (Helm values, Terraform, `serverless.yml`). Each service name found there is a
  candidate; confirm it exists in Datadog.
- **Slack**: channels whose name holds `bug`, `incident`, `support`, `alert`, `ops`, `prod` or
  `tech`, found through the connector's channel search. Read the topic of each candidate; the
  topic often names the role.
- **Linear**: `docs/agents/issue-tracker.md`, the team keys in branch names (`git branch -a`), the
  team's labels.
- **PostHog**: the project key in the repo's config, the connector's project list.
- **git**: `git log --since=90.days --oneline`; read the prefixes the fix commits actually use.
- **Memory words**: `slack|channel|datadog|monitor|incident|alert|linear|posthog|support`.
- **Priority** is the user's call, never inferred: ask it, offering as options the channels found
  above and the active Linear projects of the listed teams.

## Proof

For each source, run one read-only query over the last 30 days, the kind a reader would run:

- **datadog**: errors or slow requests on the listed services in the production `env`.
- **slack**: one search word in each listed channel.
- **linear**: issues with a listed bug label in the listed teams.
- **posthog**: error tracking issues of the project.
- **git**: `git log --since=30.days --oneline` filtered on the fix convention.

A source passes when its query returns at least one row. Zero rows is a question for the user, not
a pass: a quiet channel may be the wrong one, a label may have been renamed. With two Slack
connectors, run the Slack query through each and keep the one that reaches every listed channel.
Write the row counts in the proof section.

## Retirable sources

None by default. A memory note that lists channels or services often serves another skill too
(a daily update reads its channel from one): keep it unless the user names it.
