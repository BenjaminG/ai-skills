---
name: daily-update
description: Draft Benjamin's daily Slack update for the Naboo team from Linear. Pulls his issues closed since the previous work day (DONE), currently started (IN PROGRESS), and optionally blocked (BLOCKERS), formats them in the team's Slack style, and iterates in chat until approved. Triggers on "daily update", "daily post", "write my daily", "standup post", or "what did I do yesterday".
allowed-tools: Bash(linear:*), Bash(jq:*), Bash(date:*), AskUserQuestion
---

# Daily Update

Draft Benjamin's `#daily-naboo` Slack post from Linear, in the team's format. Draft-then-confirm — never post.

## Output format (target)

```
DAILY :
:white_check_mark: DONE :
 <https://linear.app/naboo-team/issue/KEY/slug|KEY: Title>
:rocket: IN PROGRESS:
 <https://linear.app/naboo-team/issue/KEY/slug|KEY: Title>
:x: BLOCKERS:
 <https://linear.app/naboo-team/issue/KEY/slug|KEY: Title>
:hourglass_flowing_sand: TODO:
 <https://linear.app/naboo-team/issue/KEY/slug|KEY: Title>
```

Rules:
- One space before each bullet line (matches team style).
- Each line ends with a comma; the whole post ends with a lone `.`.
- Omit any section that has zero items.
- Bullets use Slack link syntax `<url|KEY: Title>` so Slack renders one clickable label per line (no unfurl cards).
- If a title contains `|` or `>`, replace them with a space in the label (they break Slack link syntax); keep the full title in the URL.

## Step 1 — Resolve the "yesterday" window

Get the previous working day in ISO (YYYY-MM-DD). Treat Saturday/Sunday as still belonging to Friday.

```bash
DOW=$(date +%u)   # 1=Mon .. 7=Sun
case "$DOW" in
  1) SINCE=$(date -v-3d +%Y-%m-%d) ;;  # Mon → previous Fri
  *) SINCE=$(date -v-1d +%Y-%m-%d) ;;
esac
echo "$SINCE"
```

Echo the window to the user: `"Pulling DONE since <SINCE> and all started issues."`

## Step 2 — Fetch issues from Linear

Run both queries in parallel. `benjamin.gelis` is the assignee (confirm once with `linear auth whoami` if unsure).

```bash
# Completed since SINCE
linear issue query --assignee benjamin.gelis --all-teams \
  --state completed --updated-after "$SINCE" --limit 50 --json

# Currently started
linear issue query --assignee benjamin.gelis --all-teams \
  --state started --limit 50 --json
```

Parse with `jq '.nodes[] | {id: .identifier, title, url, state: .state.name, updatedAt}'`.

### Filtering rules

- **DONE**: union of
  - completed query results with `state.type == "completed"` and `updatedAt >= SINCE` (exclude `canceled`), and
  - started query results whose `state.name` matches `/review/i` (team convention: "In Review" items are reported as DONE).
- **IN PROGRESS**: started query results **not** matching `/review/i` in `state.name`. Deduplicate against DONE (an issue in both lists stays in DONE only).
- **BLOCKERS**: issues from the started query that carry a label matching `/blocked/i` OR are linked as "blocked by" another open issue. If none, skip the section.

If you want to override a bucket (e.g. treat an "In Review" PR that's reverted as still IN PROGRESS), say so in chat — the iteration step handles re-bucketing.

## Step 3 — Draft in chat

Render the post in a fenced block. Above the block, show a one-line summary:
`"<n> done · <m> in progress · <k> blockers · window: <SINCE>"`.

Below the block, list anything the user may want to add manually (non-Linear work like "review PRs", "onboarding session") as a nudge — do not insert these into the draft.

## Step 4 — Iterate

Wait for free-form tweaks. Common ones to support without asking:

- "drop BOF-XXX" → remove that line.
- "move BOF-XXX to done / in progress / blockers" → re-bucket.
- "add blocker: <text>" → append a free-text line under `:x: BLOCKERS:`.
- "shorter titles" → truncate each title to ~60 chars.

Re-render the full block after each change. Never silently drop items.

## Step 5 — Finalize

When the user confirms ("ok", "ship it", "lgtm", "copy"), print the final block once more, clean, with no surrounding prose. Do **not** post to Slack — Benjamin copies it himself.

## Notes

- If `linear` is missing or auth fails, abort with the install command from the `linear-cli` skill.
- If both queries return zero issues for Benjamin, say so explicitly and ask whether to draft from yesterday's Slack post (skill does not fetch Slack by default — keep it simple).
- Timezone: the Linear CLI returns UTC. The team posts from Europe/Paris; a UTC cutoff at midnight is close enough — if an issue sits right on the boundary, the user can re-bucket manually.
