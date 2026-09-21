#!/usr/bin/env python3
"""jev-chrome-cdp: replay autobrowse traces against Jev to measure whether
typed judgments can replace the inner agent's tree-reading loop.

Subcommands:
  extract  build the decision-point corpus from ~/.config/autobrowse/traces
  eval     send each decision point to Jev (or --no-call to print payloads)
  report   agreement + cost/latency summary over everything accumulated

Read-only over the traces; writes only under ~/.claude/jev-chrome-cdp/ and
next to this script (corpus.json).
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE_ROOT = os.path.expanduser("~/.config/autobrowse/traces")
TASKS_ROOT = os.path.expanduser("~/.config/autobrowse/tasks")
STATE_DIR = os.path.expanduser("~/.claude/jev-chrome-cdp")
CORPUS = os.path.join(HERE, "corpus.json")
RESPONSES = os.path.join(STATE_DIR, "responses.json")

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
PRICE_PER_MTOK = 0.042  # input; output is free on System One

MAX_TREE_CHARS = 20000
MAX_CANDIDATES = 255

REF_RE = re.compile(r"^\[(\d+-\d+)\]")
REF_IN_TEXT = re.compile(r"\[\d+-\d+\]")


# --- corpus ---------------------------------------------------------------

def load_tree_lines(tree):
    return [ln for ln in tree.splitlines() if ln.strip()]


def parse_ref_token(cmd):
    """`browse click [0-5]` / `browse fill [0-4] x@y` -> the ref, else None."""
    m = re.search(r"\[(\d+-\d+)\]", cmd)
    return m.group(1) if m else None


def interactive_lines(tree_lines):
    """Lines whose node is a plausible action target, with ref kept."""
    roles = ("button", "textbox", "link", "checkbox", "radio", "combobox",
             "menuitem", "tab", "option", "searchbox", "switch", "slider")
    out = []
    for ln in tree_lines:
        m = re.search(r"\[(\d+-\d+)\] ([A-Za-z]+)(?::\s*(.*))?$", ln.strip())
        if not m:
            continue
        ref, role, name = m.group(1), m.group(2).lower(), (m.group(3) or "")
        if role in roles and name.strip():
            out.append({"ref": ref, "role": role, "name": name.strip()})
    return out


def redact_action(cmd):
    """Ground truth out of the intent: replace the ref and any literal text."""
    c = re.sub(r"\[\d+-\d+\]", "<element>", cmd)
    c = re.sub(r"(?<= )\S+@\S+", "<email>", c)
    c = re.sub(r"(?:^| )/Users/\S+", " <path>", c)
    return c.replace("browse ", "", 1).strip()


def intent_for(d, i, task, act):
    """What a production harness would know at decision time: the agent's own
    reasoning just before the action, else the task goal plus flow position
    and the action verb (never the ground-truth ref — strategy.md would be
    circular, and the literal typed value is redacted)."""
    # The agent reasons AFTER reading the snapshot and BEFORE acting, so the
    # intent lives forward of i, not behind it. It names the field ("click the
    # password field"), never the ref — that is intent, not the answer.
    for f in d[i + 1:i + 5]:
        if f.get("role") == "assistant" and f.get("reasoning"):
            return REF_IN_TEXT.sub("<element>", f["reasoning"].strip())[:500]
        if f.get("role") == "assistant" and "tool_name" in f:
            break
    goal = TASK_GOALS.get(task, "")
    v = next((k for k in ("click", "fill", "type")
              if act.startswith("browse " + k)), "act on")
    desc = {"click": "Click the next element the flow requires.",
            "fill": "Type the login email into the next element the flow "
                    "requires.",
            "type": "Type into the next element the flow requires."}.get(v)
    ordinal = sum(1 for f in d[:i]
                  if f.get("role") == "tool_result"
                  and "snapshot" in str(f.get("command", "")))
    return "Step %d of the task %r. %s" % (ordinal + 1, goal, desc)


def load_task_goals():
    """task.md headers, one paragraph — the non-circular intent source."""
    goals = {}
    if not os.path.isdir(TASKS_ROOT):
        return goals
    for task in os.listdir(TASKS_ROOT):
        p = os.path.join(TASKS_ROOT, task, "task.md")
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        body = next((ln.strip("# ").strip() for ln in lines[:5]
                     if ln.startswith("# ")), task)
        goals[task] = body[:200]
    return goals


TASK_GOALS = load_task_goals()


def build_state(dp, questions):
    """The options ARE the candidate refs (pre-parsed value extraction shape):
    criteria is built per decision point, so Jev cannot answer with a ref that
    is not on the page. `none` stays as the no-match escape hatch."""
    tree = dp["tree"][:MAX_TREE_CHARS]
    cands = dp["candidates"][:MAX_CANDIDATES]
    state = {
        "tree": tree,
        "intent": dp["intent"],
        "candidates": cands,
        "claim": dp.get("claim"),
    }
    pick = dict(questions["pick_element"])
    criteria = {c["ref"]: "%s: %s" % (c["role"], c["name"]) for c in cands}
    criteria.update(questions["pick_element"]["criteria"])  # the `none` option
    pick["criteria"] = criteria
    q = {"pick_element": pick}
    if dp.get("claim"):
        q["state_matches"] = questions["is_login_form"]
    return state, q


def extract():
    if not os.path.isdir(TRACE_ROOT):
        print("jev-chrome-cdp: no trace dir at %s" % TRACE_ROOT, file=sys.stderr)
        return 2
    corpus = []
    for task in sorted(os.listdir(TRACE_ROOT)):
        tdir = os.path.join(TRACE_ROOT, task)
        if not os.path.isdir(tdir):
            continue
        for run in sorted(os.listdir(tdir)):
            rdir = os.path.join(tdir, run)
            tpath = os.path.join(rdir, "trace.json")
            if not os.path.isfile(tpath):
                continue
            with open(tpath, encoding="utf-8") as fh:
                d = json.load(fh)
            for i, e in enumerate(d):
                if e.get("role") != "tool_result":
                    continue
                cmd = str(e.get("command", ""))
                if "snapshot" not in cmd:
                    continue
                try:
                    snap = json.loads(e.get("output", ""))
                except ValueError:
                    continue
                if not isinstance(snap, dict) or "tree" not in snap:
                    continue
                # next browse click/fill/type within 3 entries
                act = None
                for f in d[i + 1:i + 4]:
                    if f.get("role") == "assistant" and "tool_name" in f:
                        c = str(f.get("tool_input", {}).get("command", ""))
                        if c.startswith(("browse click", "browse fill", "browse type")):
                            act = c
                            break
                if not act:
                    continue
                truth = parse_ref_token(act)
                if not truth:
                    continue  # selector-based action; no ref ground truth
                tree_lines = load_tree_lines(snap["tree"])
                cands = interactive_lines(tree_lines)
                if not any(c["ref"] == truth for c in cands):
                    continue  # truth not covered — not a fair Choice
                corpus.append({
                    "id": "%s/%s@%d" % (task, run, i),
                    "tree": snap["tree"],
                    "candidates": cands,
                    "intent": intent_for(d, i, task, act) or redact_action(act),
                    "action": act,
                    "truth": truth,
                })
    with open(CORPUS, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, ensure_ascii=False)
    print("jev-chrome-cdp: %d decision points -> %s" % (len(corpus), CORPUS))
    return 0


# --- eval -----------------------------------------------------------------

def load_questions():
    with open(os.path.join(HERE, "questions.json"), encoding="utf-8") as fh:
        return json.load(fh)


def call_jev(state, questions, api_key, timeout=60):
    body = json.dumps({"model": MODEL, "state": state,
                       "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={"Authorization": "Bearer %s" % api_key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def eval_all(no_call):
    if not os.path.isfile(CORPUS):
        print("jev-chrome-cdp: no corpus — run extract first", file=sys.stderr)
        return 2
    questions = load_questions()
    with open(CORPUS, encoding="utf-8") as fh:
        corpus = json.load(fh)
    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    cache = {}
    if os.path.isfile(RESPONSES):
        with open(RESPONSES, encoding="utf-8") as fh:
            cache = json.load(fh)
    rows, saved = [], 0
    for dp in corpus:
        if dp["id"] in cache:
            rows.append(cache[dp["id"]])
            continue
        state, qs = build_state(dp, questions)
        if no_call:
            rows.append({"id": dp["id"], "payload": state})
            continue
        if not api_key:
            print("jev-chrome-cdp: TYPESAFE_API_KEY not set", file=sys.stderr)
            return 3
        t0 = time.time()
        try:
            resp = call_jev(state, qs, api_key)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return api_fail(e)
        ms = int((time.time() - t0) * 1000)
        a = resp.get("answers", {})
        pick = a.get("pick_element", {})
        row = {
            "id": dp["id"],
            "truth": dp["truth"],
            "pick": pick.get("choice"),
            "pick_conf": pick.get("confidence"),
            "state_matches": (a.get("state_matches", {}) or {}).get("noul"),
            "ms": ms,
            "input_tokens": resp.get("usage", {}).get("input_tokens", 0),
        }
        rows.append(row)
        cache[dp["id"]] = row
        saved += 1
        if saved % 10 == 0:
            persist(cache)
    persist(cache)
    if no_call:
        print(json.dumps(rows[:2], ensure_ascii=False, indent=2))
        print("jev-chrome-cdp: --no-call, %d payloads built, nothing sent"
              % len(rows))
    return 0


def persist(cache):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(RESPONSES, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


def api_fail(e):
    msg = ""
    if isinstance(e, urllib.error.HTTPError):
        try:
            msg = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        print("jev-chrome-cdp: http %s: %s" % (e.code, msg), file=sys.stderr)
    else:
        print("jev-chrome-cdp: network error: %s" % str(e)[:160],
              file=sys.stderr)
    return 4




# --- claims (state_matches / verifyState) -----------------------------------

CLAIMS = os.path.join(HERE, "claims.json")
CLAIM_RESPONSES = os.path.join(STATE_DIR, "claims-responses.json")
MAX_CLAIM_TREE_CHARS = 20000


def eval_claims(no_call):
    """Replay hand-curated (claim, tree) pairs against the verifyState noul.
    Ground truth comes from the corpus builder; trees come from the same
    recorded traces. --no-call prints payloads, spends nothing."""
    if not os.path.isfile(CLAIMS):
        print("jev-chrome-cdp: no claims.json — build it first", file=sys.stderr)
        return 2
    questions = load_questions()
    with open(CLAIMS, encoding="utf-8") as fh:
        rows_in = json.load(fh)
    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    cache = {}
    if os.path.isfile(CLAIM_RESPONSES):
        with open(CLAIM_RESPONSES, encoding="utf-8") as fh:
            cache = json.load(fh)
    out, saved = [], 0
    for i, dp in enumerate(rows_in):
        key = "c%02d" % i
        if key in cache:
            out.append(cache[key]); continue
        state = {
            "tree": dp["claim__tree"][:MAX_CLAIM_TREE_CHARS],
            "claim": dp["claim"],
        }
        q = {"state_matches": questions["is_login_form"]}
        if no_call:
            out.append({"key": key, "tag": dp["tag"], "expect": dp["expect"],
                        "claim": dp["claim"], "payload_state_keys": sorted(state)})
            continue
        if not api_key:
            print("jev-chrome-cdp: TYPESAFE_API_KEY not set", file=sys.stderr)
            return 3
        t0 = time.time()
        try:
            resp = call_jev(state, q, api_key)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return api_fail(e)
        ms = int((time.time() - t0) * 1000)
        noul = (resp.get("answers", {}).get("state_matches", {}) or {}).get("noul")
        row = {"key": key, "tag": dp["tag"], "expect": dp["expect"],
               "claim": dp["claim"], "noul": noul, "ms": ms,
               "input_tokens": resp.get("usage", {}).get("input_tokens", 0)}
        out.append(row)
        cache[key] = row
        saved += 1
        persist_claims(cache)
    persist_claims(cache)
    if no_call:
        print("jev-chrome-cdp: --no-call, %d claim payloads built" % len(out))
        for r in out[:3]:
            print("  %-8s expect=%-5s %s" % (r["tag"], r["expect"], r["claim"][:70]))
    return 0


def persist_claims(cache):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CLAIM_RESPONSES, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


def report_claims():
    if not os.path.isfile(CLAIM_RESPONSES):
        print("jev-chrome-cdp: no claims served yet — run eval-claims",
              file=sys.stderr)
        return 2
    with open(CLAIM_RESPONSES, encoding="utf-8") as fh:
        rows = list(json.load(fh).values())
    called = [r for r in rows if "noul" in r]
    if not called:
        print("jev-chrome-cdp: no served claim rows yet")
        return 0
    n = len(called)
    # decision bands mirror cdp.mjs verify: pass >= 0.8, fail <= 0.2, else escalate
    def decision(noul):
        if noul >= 0.8: return "pass"
        if noul <= 0.2: return "fail"
        return "escalate"
    ok = fp = fn = esc = 0
    misses = []
    for r in called:
        d = decision(r["noul"])
        want = "pass" if r["expect"] == "true" else "fail"
        if d == want: ok += 1
        elif d == "escalate":
            esc += 1
            misses.append(("escalated", r))
        elif d == "pass": fp += 1; misses.append(("FALSE-PASS", r))
        else: fn += 1; misses.append(("FALSE-FAIL", r))
    toks = sum(r.get("input_tokens", 0) for r in called)
    ms = sorted(r.get("ms", 0) for r in called)
    print("claims %d | correct %d | escalated %d | FALSE-PASS %d | FALSE-FAIL %d"
          % (n, ok, esc, fp, fn))
    print("false-passes are the fatal metric (a QA step marked passed wrongly)")
    print("input tokens %d (~$%.4f) | latency p50 %d ms"
          % (toks, toks / 1e6 * PRICE_PER_MTOK, ms[len(ms)//2] if ms else 0))
    for kind, r in misses:
        print("  %s  %-8s noul=%s  %s" % (kind, r["tag"], r["noul"], r["claim"][:80]))
    return 0


# --- report ---------------------------------------------------------------

def report():
    if not os.path.isfile(RESPONSES):
        print("jev-chrome-cdp: nothing accumulated yet — run eval",
              file=sys.stderr)
        return 2
    with open(RESPONSES, encoding="utf-8") as fh:
        rows = list(json.load(fh).values())
    called = [r for r in rows if "pick" in r]
    if not called:
        print("jev-chrome-cdp: no served rows yet")
        return 0
    n = len(called)
    ok = sum(1 for r in called if r.get("pick") == r.get("truth"))
    none_picks = sum(1 for r in called if r.get("pick") == "none")
    low_conf = [r for r in called if (r.get("pick_conf") or 0) < 0.5]
    toks = sum(r.get("input_tokens", 0) for r in called)
    ms = sorted(r.get("ms", 0) for r in called)
    p50 = ms[len(ms) // 2] if ms else 0
    cost = toks / 1e6 * PRICE_PER_MTOK
    print("rows %d | pick correct %d/%d (%.0f%%) | picked none %d | "
          "conf<0.5 %d" % (n, ok, n, 100.0 * ok / max(n, 1), none_picks,
                           len(low_conf)))
    print("input tokens %d (~$%.4f) | latency p50 %d ms" % (toks, cost, p50))
    # Production shape: act only above a confidence threshold, escalate below.
    # Precision is what matters — a wrong click is not idempotent.
    print("  thr   acted  correct  precision  escalated")
    for thr in (0.5, 0.6, 0.7, 0.8, 0.9):
        acted = [r for r in called
                 if r.get("pick") != "none" and (r.get("pick_conf") or 0) >= thr]
        good = sum(1 for r in acted if r.get("pick") == r.get("truth"))
        prec = 100.0 * good / len(acted) if acted else 0.0
        print("  %.1f   %4d   %4d     %5.1f%%     %4d"
              % (thr, len(acted), good, prec, n - len(acted)))
    wrong = [r for r in called if r.get("pick") != r.get("truth")]
    for r in wrong[:10]:
        print("  MISS %s: picked %s (conf %s) truth %s"
              % (r["id"], r.get("pick"), r.get("pick_conf"), r.get("truth")))
    return 0


def main():
    a = sys.argv[1:]
    if not a or a[0] == "report":
        return report()
    if a[0] == "extract":
        return extract()
    if a[0] == "eval":
        return eval_all("--no-call" in a[1:])
    if a[0] == "eval-claims":
        return eval_claims("--no-call" in a[1:])
    if a[0] == "report-claims":
        return report_claims()
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
