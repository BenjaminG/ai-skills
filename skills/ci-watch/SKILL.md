---
name: ci-watch
description: Watch a PR's CI hands-free after a push. A persistent Monitor streams each check as it lands; the skill auto-handles the mechanical (rebase a clean conflict, fix lint) and STOPs on any judgment (failing tests, a stack restack, going ready). Triggers on "watch CI", "surveille la CI", "attends la CI", or right after /pr-create or a push.
argument-hint: "[pr-number|url]"
disable-model-invocation: true
---

# CI Watch

Watch the current PR's checks without babysitting them by hand. A persistent Monitor streams every state change while the session keeps working; you react per the classification table below.

**The boundary, one line:** act without asking only when the action is **mechanical** (reversible, no decision) — rebase a clean conflict, fix lint, push, `gh pr ready`. Every **judgment** (which finding to fix, a red test, restacking a stack, the final go) is a **STOP**: surface it and hand back.

CI has three states, and each routes differently: **green** (advance), **red** (classify the failure), **conflict** (rebase or restack).

## Step 1 — Resolve

Find the PR to watch:

```bash
gh pr view --json number,url,baseRefName,isDraft   # current branch; a [pr-number|url] argument overrides
```

If there is no PR for the branch and no argument, stop and say so — there is nothing to watch.

The Monitor and notification tools are deferred; load them before arming:

```
ToolSearch "select:Monitor,PushNotification"
```

**Done when:** the PR is resolved and `Monitor` + `PushNotification` are loaded.

## Step 2 — Arm

Arm a **persistent** Monitor that polls the PR's checks and mergeable state and emits one event per state change, so the session can keep working while checks land:

```bash
gh pr checks <pr-url>                                    # per-check status
gh pr view <pr-url> --json mergeable,mergeStateStatus     # conflict detection
```

Poll no faster than every 30s (API rate limits). Read the loaded `Monitor` schema for how to phrase the until-condition and interval.

**Done when:** the Monitor is running and has emitted its first snapshot.

## Step 3 — React

Route each event through the table. **Do not declare green on the first passing check** — wait until *every required check is terminal* (none `pending` / `in_progress`), or a premature "all clear" will fire while checks are still running.

| Signal | Action | Nature |
|--------|--------|--------|
| all required checks **green** | `PushNotification`, go to Step 4 | mechanical |
| **conflict** · isolated branch (not in a stack) | `git rebase <baseRefName>` + `git push --force-with-lease` | mechanical |
| **conflict** · branch in a git-spice stack (`gs ls` lists it) | propose `gs stack restack` + cascade push — **one confirmation** | judgment |
| **conflict** with leftover markers to resolve | STOP, hand back | judgment |
| **red** · lint / format only | deterministic fix (`prettier --write` / `eslint --fix`), commit, push | mechanical |
| **red** · test / typecheck | `/pr-feedback` to triage, surface the P1, STOP | judgment |
| **red** · a known-flaky check (list below) | re-run once, then escalate | waiting |

**Known-flaky allow-list** (the only checks a red state may auto-retry — everything else red stops):

- **i18n `_latest` in the merge queue** — fix: run `i18n:pull`, then re-run the check.

**Done when:** every required check is terminal and its row has been actioned.

## Step 4 — Green

The PR is green and ready for a human review.

1. `PushNotification` — "PR ready for human review."
2. If the PR is still draft, ask **"mark it ready?"** (STOP — this is a judgment). On yes: `gh pr ready <pr-url>`.
3. **Never** request a review on GitHub and **never** post to Slack. Soliciting the team is the user's call.

**Done when:** the notification is sent and, if approved, the PR is marked ready.
