# jev-chrome-cdp — replay harness

Measures whether TypeSafe's Jev can replace the LLM decision loop in
chrome-cdriving skills (qa-run scenario agents, autobrowse-cc inner agents).

Corpus: the recorded autobrowse traces at `~/.config/autobrowse/traces/` —
`claude -p` stream-json transcripts of an inner agent driving an isolated
Chrome. Each `snapshot` result followed by a `browse click/fill/type` is one
**decision point** with known ground truth (the ref the agent acted on).

Two judgments, both fed from a snapshot alone (no screenshot, no vision):

| Question | Type | Replaces |
| --- | --- | --- |
| `pick_element` | Choice over candidate refs harvested from the tree | the agent reading the tree and writing the selector/ref |
| `is_login_form` | Noul: does the tree show a described state | the agent reading the tree to verify an outcome |

Ground truth refs never enter `state`. Intent comes from the agent's
reasoning text or a redacted command description (what a production harness
would know at decision time).

Read-only over the traces. Writes only here and to `~/.claude/jev-chrome-cdp/`
(response cache). Uses `TYPESAFE_API_KEY`; `--no-call` prints payloads and
spends nothing, mirroring jev-verify.

## Run

```bash
python3 evals/jev-chrome-cdp/jev_cdp_eval.py extract   # build corpus from traces
python3 evals/jev-chrome-cdp/jev_cdp_eval.py eval --no-call   # dry-run payloads
TYPESAFE_API_KEY=... python3 evals/jev-chrome-cdp/jev_cdp_eval.py eval   # spend
python3 evals/jev-chrome-cdp/jev_cdp_eval.py report
```

Exit codes: 0 ok, 2 no corpus/trace dir, 3 no API key, 4 API error.
