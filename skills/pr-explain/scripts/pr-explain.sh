#!/usr/bin/env bash
# One explainer tab per PR: a fresh Claude session runs /pr-feedback, then /explain-plainly.
# Usage: pr-explain.sh [PR number or URL …] — no argument takes every held PR from the scan.
set -uo pipefail

[ "${HERDR_ENV:-}" = 1 ] || { echo "pr-explain: not inside a herdr pane" >&2; exit 1; }

EXPLAIN="/explain-plainly explique-moi le thread ouvert et quelles sont les solutions que tu suggères ?"

if [ $# -eq 0 ]; then
  # shellcheck disable=SC2046 # PR numbers, word-safe
  set -- $(python3 "$(dirname "$0")/../../pr-dash/scripts/pr-scan.py" |
    jq -r '.prs[] | select(.held > 0) | .number')
  [ $# -gt 0 ] || { echo "pr-explain: no held PR"; exit 0; }
fi

# A shell pane alone in its tab, at its prompt, in this repo: "<pane> <tab>".
# ponytail: a tab the user named ("dev server …") is reserved; herdr's own labels read "<n> · …".
free_pane() {
  local tabs
  tabs=$(herdr tab list --workspace "$HERDR_WORKSPACE_ID" |
    jq -c '[.result.tabs[] | select(.pane_count == 1 and (.label | test("^[0-9]+ · "))) | .tab_id]')
  herdr pane list --workspace "$HERDR_WORKSPACE_ID" |
    jq -r --argjson tabs "$tabs" --arg cwd "$PWD" --arg me "$HERDR_PANE_ID" '
      .result.panes[] | select(.tab_id | IN($tabs[]))
      | select(.agent == null and .foreground_cwd == $cwd and .pane_id != $me)
      | "\(.pane_id) \(.tab_id)"' |
    while read -r pane tab; do
      herdr pane process-info --pane "$pane" |
        jq -e '.result.process_info | .foreground_processes[0].pid == .shell_pid' >/dev/null &&
        { echo "$pane $tab"; break; }
    done
}

for arg in "$@"; do
  n=${arg##*/pull/}; n=${n#\#}; n=${n%%[!0-9]*}
  [ -n "$n" ] || { echo "pr-explain: not a PR: $arg" >&2; continue; }
  name="explain-$n"

  if tab=$(herdr agent get "$name" 2>/dev/null | jq -er '.result.agent.tab_id'); then
    echo "#$n → explainer tab $tab already open (agent $name)"
    continue
  fi

  read -r pane tab < <(free_pane)
  if [ -z "${pane:-}" ]; then
    created=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --no-focus) || continue
    pane=$(jq -r '.result.root_pane.pane_id' <<<"$created")
    tab=$(jq -r '.result.tab.tab_id' <<<"$created")
  fi

  herdr agent start "$name" --kind claude --pane "$pane" -- --dangerously-skip-permissions >/dev/null ||
    { echo "pr-explain: #$n: claude did not start in $pane" >&2; continue; }

  # Detached: the caller gets its prompt back; the herdr notification says when it is ready.
  # shellcheck disable=SC2016 # expanded by the inner bash
  nohup bash -c '
    if herdr agent prompt "$1" "/pr-feedback $2" --wait && herdr agent prompt "$1" "$3" --wait; then
      herdr notification show "PR #$2 expliquée" --body "agent explain-$2" --sound done
    else
      herdr notification show "PR #$2 : la session attend ta réponse" --body "agent explain-$2" --sound request
    fi' _ "$name" "$n" "$EXPLAIN" >/dev/null 2>&1 &

  echo "#$n → explainer tab $tab (agent $name)"
  unset pane tab
done
