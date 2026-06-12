---
name: product-qa
description: >-
  Announce that a feature is ready for manual QA on its ephemeral environment
  by creating a "[PRODUCT QA]" sub-issue on Linear with the QA label applied at
  creation, so the team's product_bot auto-posts the ephemeral-env links to the
  #product-qa Slack channel. Drafts the body from the PR diff and the parent
  Linear issue (what-to-test + scope + env block), renders in chat for approval,
  and publishes only on explicit confirmation. This skill should be used when
  asked to announce a feature for product QA, signal that a PR is ready for QA
  on an ephemeral/preview env, notify the QA channel, or "annonce QA".
argument-hint: "[pr-number-or-url] [--label <name>]"
---

# Product QA Announcer

!IMPORTANT: The QA label **must be applied on the `linear issue create` call itself**. The `product_bot` listens to the Linear *"issue created"* event filtered by label — applying the label later with `linear issue update` does **not** re-fire the bot and the channel is never notified. Never split create-then-label.

!IMPORTANT: Draft and iterate in chat. Create the sub-issue only after explicit user approval.

## Step 0: Parse arguments

Parse `$ARGUMENTS`:
- Strip `--label <name>` into `LABEL` (default: `QA Produit`). This is the label the bot keys on; it must already exist on the target team.
- The remainder, if any, is the PR reference.

## Step 1: Resolve the PR

- **PR ref given** (number or URL) → use it directly.
- **No PR ref** → detect from the current branch:
  ```bash
  gh pr list --head "$(git branch --show-current)" --state open --json number,url,title,headRefName,baseRefName --limit 5
  ```
  - Exactly one result → use it.
  - Zero results → abort: "No open PR found for branch. Pass a PR number (e.g. `/product-qa 13627`)."
  - More than one → list them and ask which to use.

Echo the resolved PR as `#<n> — <title> — <url>` so the user can confirm.

## Step 2: Find the parent Linear key

- Regex `[A-Z]+-\d+` against the branch name (e.g. `bof-399-kill-deposit-ceiling` → `BOF-399`).
- If no match, grep the PR body for a Linear URL or `[A-Z]+-\d+`.
- If still nothing, abort: "No Linear ticket key found in branch name or PR body. Pass the parent key explicitly."

Derive `TEAM` from the key prefix (e.g. `BOF-399` → `BOF`).

## Step 3: Fetch context

```bash
gh pr view <N> --json title,url,body,headRefName,baseRefName,number
linear issue view <KEY> --json
```

Read the parent issue for acceptance criteria, the validated product rule, and any scope/matrix table. Optionally run `gh pr diff <N>` for a behavior summary. Use these to write the "What can be tested" bullets in tester-facing, user-observable terms (not implementation detail).

## Step 4: Build the ephemeral-env block

The deploy bot posts the ephemeral-env URLs in a PR comment. Extract them:

```bash
gh pr view <N> --repo <owner/repo> --json comments \
  | jq -r '.comments[].body' \
  | grep -ioE 'https?://[a-z0-9.-]*naboo-pr-<N>[a-z0-9.:/?=&_-]*' | sort -u
```

Map the matches to labeled lines, keeping only product-QA-relevant surfaces:

- 🖥️ **Backoffice:** `https://admin.naboo-pr-<N>.getnaboo.net`
- 📱 **App:** `https://naboo-pr-<N>.getnaboo.net`
- 🏠 **App Host:** `https://hotes.naboo-pr-<N>.getnaboo.net`
- 🎉 **App Event:** `https://event.naboo-pr-<N>.getnaboo.net`
- 🏪 **Marketplace:** `https://marketplace.naboo-pr-<N>.getnaboo.net`
- 🏛️ **Mice:** `https://mice.naboo-pr-<N>.getnaboo.net`
- 📧 **Mailpit:** `https://mailpit.naboo-pr-<N>.getnaboo.net`
- 🫀 **Api (GraphQL):** `https://api.naboo-pr-<N>.getnaboo.net/graphql`
- ✨ **Data (docs):** `https://data.naboo-pr-<N>.getnaboo.net/docs`

Omit infra-only links (`mongodb`, `redis`, `minio` api) — not useful for a PM/QA tester.

If the grep returns no matches, the env may not be deployed yet. Warn the user, and fall back to the conventional URLs derived from the PR number, flagging them as **unverified** (the env must be deployed before the PM can test).

## Step 5: Draft the `[PRODUCT QA]` body

Assemble the description (English copy, per repo convention):

```markdown
Product QA for **<KEY>** — <one-line summary of what changed, from PR/Linear>.

**What can be tested:**

* <user-observable behavior 1 — tied to an acceptance criterion>
* <user-observable behavior 2>
* <…>

<optional scope/matrix table copied/adapted from the parent issue>

## 🌐 Ephemeral environment (PR #<N>)

* 🖥️ **Backoffice:** <url>
* 📱 **App:** <url>
* … (only the lines resolved in Step 4)

🔗 **PR:** <pr-url>
```

Keep "What can be tested" framed for a non-developer: things observable in the browser / admin UI / email sandbox, not endpoint or DB assertions.

## Step 6: Render in chat & iterate

Render the drafted body (fenced markdown). Then ask:

> Review the announcement. Reply with edits, or `publish` to create the `[PRODUCT QA]` sub-issue under `<KEY>` (label `<LABEL>`) — the bot will then post to #product-qa.

Apply edits and re-render until the user says `publish` (or "ship it", "go", "ok publish"). Never proceed to Step 7 without explicit approval.

## Step 7: Publish — create the sub-issue WITH the label

Write the approved body to a temp file first (avoids HEREDOC breakage on backticks, `$`, `|`, nested fences), then create with the label **on the same call**:

```bash
TMP=$(mktemp -t product-qa.XXXXXX.md)
# Write the approved body to $TMP via the Write tool
linear issue create \
  --team <TEAM> \
  --parent <KEY> \
  --label "<LABEL>" \
  --title "[PRODUCT QA] - <feature>" \
  --description-file "$TMP" \
  --no-interactive
rm -f "$TMP"
```

The command prints the new issue URL.

## Step 8: Confirm

Print:

> Sub-issue created: <URL>
> `product_bot` should post to #product-qa within a few seconds — check the channel.

## linear CLI quirks (verified)

- `linear issue create` accepts `--team --parent --label --title --description-file --no-interactive`. It **rejects** `--json` and `--no-pager` (re-prints help on unknown flags).
- `linear issue update <KEY>` has **no** `--no-interactive` flag.
- `linear issue delete <KEY>` requires `--confirm`.
- `linear issue view --json` omits labels from its output. To read labels back, query GraphQL:
  ```bash
  linear api 'query { issue(id:"<KEY>") { labels { nodes { name } } } }'
  ```

## Notes

- **Why a dedicated skill:** `qa-plan --linear` intentionally creates the sub-issue *without* a label (label names vary per team) and tells the user to add it manually — which, for this team's bot, silently fails to notify. This skill is the label-at-creation path that reliably triggers the announcement.
- **The bot resolves the env itself** from the issue/parent's linked PR, but including the env block in the body gives the PM the links inline and survives if the bot's resolution changes.
- **Scope:** announcement only. For the test checklist itself, use `qa-plan`; to execute it, use `qa-run`.
