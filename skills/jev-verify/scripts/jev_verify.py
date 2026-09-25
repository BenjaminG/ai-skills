#!/usr/bin/env python3
"""Replay gate-wf's Verify phase against Jev and report where the two disagree.

gate-wf spends one sonnet subagent per skeptic vote (3 per BLOCKER, 1 per MAJOR),
each with a 6-tool-call budget, to turn an already-investigated finding into a
boolean. Jev answers that shape of question in ~100ms for $0.042/M input tokens.
This measures whether it answers it *well* — it does not change gate-wf, which is
neither imported for writing nor modified.

    jev_verify.py run [--branch X] [--no-call] [--json]
    jev_verify.py corpus [--limit N] [--synthetic]
    jev_verify.py calibrate
    jev_verify.py --self-check

Every gate-wf state file on disk carries its skeptic votes in
`verifications: [{refuted, reason}]`, so `corpus` calibrates against hundreds of
real sonnet judgments without running the gate once.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
PRICE_PER_MTOK = 0.042  # input only; output is free

RADIUS = int(os.environ.get("JEV_RADIUS", "40"))  # lines each side of the cited line
MAX_CODE_CHARS = 200 * RADIUS  # Jev caps state + longest question at 32k tokens

# Kill below, keep above, escalate to a real skeptic in between. Calibrated on
# the Naboo corpus (125 findings, 36 gate-wf runs): at 0.50 the two error curves
# peak together — 92% of real findings kept, 94% of planted ones killed.
KILL_BELOW = 0.50
KEEP_ABOVE = 0.70
# A finding resting on a quoted project rule is refutable three ways only
# (agents/skeptic.md); uncertainty resolves in favour of the rule.
KILL_BELOW_CITED = 0.10

TIER_INDEX = {"NIT": 0, "MAJOR": 1, "BLOCKER": 2}
INDEX_TIER = {v: k for k, v in TIER_INDEX.items()}


def _load_findings_module():
    """gate-wf owns findings.py; there must be exactly one implementation of the
    content anchor and the state-path derivation, so import it rather than
    copying it."""
    cands = []
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        cands.append(os.path.join(root, "skills/gate-wf/scripts"))
    cands.append(os.path.join(_HERE, "../../gate-wf/scripts"))
    cands += sorted(
        glob.glob(os.path.expanduser(
            "~/.claude/plugins/cache/*/ai-skills/*/skills/gate-wf/scripts")),
        reverse=True,
    )
    cands.append(os.path.expanduser("~/.claude/skills/gate-wf/scripts"))
    for c in cands:
        if os.path.isfile(os.path.join(c, "findings.py")):
            sys.path.insert(0, os.path.realpath(c))
            import findings  # noqa: F401
            return findings
    print("jev-verify: gate-wf's scripts/findings.py not found — "
          "reinstall the plugin", file=sys.stderr)
    raise SystemExit(2)


F = _load_findings_module()


# --- pure helpers (all covered by test_jev_verify.py) ------------------------

def squeeze(s):
    """Same normalization gate-wf's content anchor uses (findings.py:106-130)."""
    return " ".join((s or "").split())


def head_sha(cache_key):
    """cache_key is '<HEAD_SHA>_<BASE_SHA>_<WT_HASH>_v5'."""
    parts = (cache_key or "").split("_")
    return parts[0] if parts and len(parts[0]) >= 7 else None


def slice_code(lines, line, radius=RADIUS, max_chars=MAX_CODE_CHARS):
    """Numbered window around `line`. Numbers are load-bearing: they are how Jev
    ties finding.line to a row of `code`."""
    if not lines:
        return ""
    n = len(lines)
    if not isinstance(line, int) or line < 1:
        line = 1
    lo = max(1, line - radius)
    hi = min(n, line + radius)
    out = []
    for i in range(lo, hi + 1):
        mark = ">" if i == line else " "
        out.append("%s%6d | %s" % (mark, i, lines[i - 1].rstrip("\n")))
    text = "\n".join(out)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    return text


def quoted_spans(evidence, minlen=8):
    """The backticked code fragments inside `evidence`, split on elisions.

    `evidence` is not a quote field. Two thirds of it is prose with no code in
    it at all, and what is quoted is routinely abridged — "`if (x) { ... }`".
    So: pull the backticked spans, cut them at the ellipsis, keep the fragments
    long enough to mean something."""
    out = []
    for span in re.findall(r"`([^`]+)`", evidence or ""):
        for frag in re.split(r"\.\.\.|\u2026", span):
            frag = squeeze(frag).strip(" ;,")
            if len(frag) >= minlen:
                out.append(frag)
    return out


def evidence_status(lines, line, evidence, radius=RADIUS):
    """A report flag, never a kill signal.

    'no-quote' is the common case and says nothing about the finding. 'off-anchor'
    is the one genuinely useful verdict: the quoted code exists, but not where the
    finding says it does."""
    if lines is None:
        return "unreadable"
    spans = quoted_spans(evidence)
    if not spans:
        return "no-quote"
    whole = squeeze(" ".join(lines))
    if not isinstance(line, int) or line < 1:
        line = 1
    near = squeeze(" ".join(
        lines[max(1, line - radius) - 1:min(len(lines), line + radius)]))
    hits = [sp for sp in spans if sp in whole]
    if not hits:
        return "none"
    if len(hits) < len(spans):
        return "some"
    return "all" if all(sp in near for sp in hits) else "off-anchor"


def build_state(f, code):
    st = {
        "file": f.get("file"),
        "line": f.get("line"),
        "code": code,
        "finding": {
            "rule_id": f.get("rule_id"),
            "message": f.get("message"),
            "evidence": f.get("evidence"),
            "suggested_fix": f.get("suggested_fix"),
        },
    }
    if f.get("citation"):
        st["rule_citation"] = {
            "source": f.get("source"),
            "text": f.get("citation"),
        }
    return st


def jev_decision(p, cited):
    """Map a defect_real probability onto what gate-wf's verify phase would do."""
    floor = KILL_BELOW_CITED if cited else KILL_BELOW
    if p is None:
        return "error"
    if p < floor:
        return "kill"
    if p >= KEEP_ABOVE:
        return "keep"
    return "escalate"


def sonnet_verdict(f):
    """What gate-wf's skeptics concluded. Everything on disk survived, so this is
    always 'keep' — the votes tell us how close it came."""
    ref, tot = F.refute_votes(f)
    return {"kept": True, "refuted": ref, "total": tot}


def sweep(real, syn=(), lo=0.05, hi=0.95, step=0.05):
    """Both error directions as the kill threshold moves.

    Every finding on disk was KEPT by the sonnet skeptics, so `kept` alone only
    measures false negatives. `killed` over the planted findings from --synthetic
    supplies the other half; the useful threshold is where the two curves cross.
    Yields (threshold, kept, n_real, killed, n_syn)."""
    r = [x for x in real if x.get("defect_real") is not None]
    y = [x for x in syn if x.get("defect_real") is not None]
    out = []
    t = lo
    while t <= hi + 1e-9:
        out.append((round(t, 2),
                    sum(1 for x in r if x["defect_real"] >= t), len(r),
                    sum(1 for x in y if x["defect_real"] < t), len(y)))
        t += step
    return out


SHIFT = 2 * RADIUS + 20  # far enough that the mutated window shares no line


def mutate(f, i):
    """Turn a survivor into a finding we know is wrong, so the refute direction
    can be measured at all. Not recall — a sensitivity floor: if Jev scores these
    as high as the originals, defect_real says 'true' to everything.

    The shift must exceed twice the window radius. A smaller one (the +15 this
    started as) leaves the mutated window overlapping the original by 80%, so
    Jev is shown almost the same code and scores it almost the same — that
    measures the control, not the model."""
    g = dict(f)
    ln = f.get("line")
    g["line"] = (ln + SHIFT) if isinstance(ln, int) else SHIFT
    g["_synthetic"] = "line shifted +%d" % SHIFT
    return g


# --- git / io ---------------------------------------------------------------

def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def read_lines(root, path, sha, cur_head, cache):
    """Worktree when the state was written at the commit we are on (gate-wf's own
    anchor reads from disk); the recorded blob otherwise."""
    key = (path, sha if sha != cur_head else None)
    if key in cache:
        return cache[key]
    lines = None
    if sha and sha != cur_head:
        blob = _git(root, "show", "%s:%s" % (sha, path))
        if blob is not None:
            lines = blob.splitlines()
    if lines is None:
        try:
            with open(os.path.join(str(root), path), encoding="utf-8",
                      errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = None
    cache[key] = lines
    return lines


def out_paths(root, branch):
    slug = F.state_dir(root).name
    d = os.path.expanduser(os.path.join("~/.claude/jev-verify", slug))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s.json" % branch.replace("/", "_"))


# --- preflight (gate-wf --jev fail-fast) --------------------------------------

PROBE_QUESTION = {
    "type": "noul",
    "instructions": "Preflight probe. Reply true.",
    "criteria": {"true": "yes", "false": "no"},
}
PROBE_TOKENS = 300  # measured: a one-char state + one noul question ~= 287


def preflight(api_key, budget=PROBE_TOKENS):
    """The API exposes no balance or quota endpoint (only /v1/systemone), so
    'is there credit' can only be established by spending some: one minimal
    call, ~300 tokens, ~0.001 cents. That is the point — gate-wf --jev checks
    this BEFORE its reviewers spend anything, not after.

    Returns (ok, message). ok=False carries the exact reason to fail fast on;
    the caller decides whether to abort or fall back to plain skeptics."""
    try:
        resp = call_jev({"probe": "x"}, {"probe": PROBE_QUESTION}, api_key)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 401:
            return False, "401 unauthorized: bad or revoked TYPESAFE_API_KEY"
        if e.code == 429:
            return False, "429 rate-limited: %s" % body
        return False, "http %s: %s" % (e.code, body)
    except (urllib.error.URLError, OSError) as e:
        return False, "network unreachable: %s" % str(e)[:120]
    # A 200 means credits exist: the API has no free tier distinction and no
    # documented zero-credit error, so a served call IS the check.
    toks = resp.get("usage", {}).get("input_tokens", 0)
    if not toks:
        return False, "probe returned no usage — treating as failure"
    return True, "probe ok (%d input tokens, ~$%.5f)" % (toks, toks / 1e6 * PRICE_PER_MTOK)


# --- the call ---------------------------------------------------------------

def load_questions():
    with open(os.path.join(_HERE, "questions.json"), encoding="utf-8") as fh:
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


def verify_one(f, root, sha, cur_head, questions, api_key, cache, no_call):
    lines = read_lines(root, f.get("file") or "", sha, cur_head, cache)
    row = {
        "id": f.get("id"), "rule_id": f.get("rule_id"), "file": f.get("file"),
        "line": f.get("line"), "tier": f.get("tier"),
        "reviewer": f.get("reviewer"), "cited": bool(f.get("citation")),
        "sonnet": sonnet_verdict(f),
        "evidence": evidence_status(lines, f.get("line"), f.get("evidence")),
        "input_tokens": 0,
    }
    if f.get("_synthetic"):
        row["synthetic"] = f["_synthetic"]
    if lines is None:
        row["error"] = "unreadable"
        return row
    state = build_state(f, slice_code(lines, f.get("line")))
    if no_call:
        row["payload"] = state
        return row
    try:
        resp = call_jev(state, questions, api_key)
    except (urllib.error.URLError, OSError, ValueError) as e:
        row["error"] = str(e)[:160]
        return row
    a = resp.get("answers", {})
    row["defect_real"] = a.get("defect_real", {}).get("noul")
    row["fix_addresses"] = a.get("fix_addresses", {}).get("noul")
    row["needs_wider_context"] = a.get("needs_wider_context", {}).get("noul")
    sc = a.get("severity", {})
    if "score" in sc:
        row["severity"] = sc["score"]
        row["severity_tier"] = INDEX_TIER.get(int(round(sc["score"])), "?")
        row["severity_confidence"] = sc.get("confidence")
    row["input_tokens"] = resp.get("usage", {}).get("input_tokens", 0)
    row["decision"] = jev_decision(row["defect_real"], row["cited"])
    return row


# --- batch mode (gate-wf --jev) ----------------------------------------------

BATCH_SCHEMA_KEYS = ("file", "line", "rule_id", "tier", "message", "evidence",
                     "suggested_fix", "citation", "source")


def batch_one(f, root, questions, api_key, cache, cur_head):
    """Judge one finding handed over by gate-wf's workflow. Same pipeline as
    `run`/`corpus` but no state discovery: the caller owns the finding set."""
    lines = read_lines(root, f.get("file") or "", None, cur_head, cache)
    row = {
        "file": f.get("file"), "line": f.get("line"), "rule_id": f.get("rule_id"),
        "tier": f.get("tier"), "cited": bool(f.get("citation")),
        "msg_len": len(f.get("message") or ""),
        "input_tokens": 0,
    }
    if lines is None:
        row["error"] = "unreadable"
        row["decision"] = "escalate"  # no code -> a skeptic must look
        return row
    state = build_state(f, slice_code(lines, f.get("line")))
    try:
        resp = call_jev(state, questions, api_key)
    except (urllib.error.URLError, OSError, ValueError) as e:
        row["error"] = str(e)[:160]
        row["decision"] = "escalate"  # API down -> fall back to sonnet, never lose the finding
        return row
    a = resp.get("answers", {})
    row["defect_real"] = a.get("defect_real", {}).get("noul")
    row["needs_wider_context"] = a.get("needs_wider_context", {}).get("noul")
    if "score" in a.get("severity", {}):
        row["severity"] = a["severity"]["score"]
    row["input_tokens"] = resp.get("usage", {}).get("input_tokens", 0)
    row["decision"] = jev_decision(row["defect_real"], row["cited"])
    # Context starvation measured in the corpus: 70% of findings want code the
    # window cannot show. When Jev itself says it cannot decide from what it was
    # given, that is an escalation regardless of the probability.
    if (row.get("needs_wider_context") or 0) >= 0.5 and row["decision"] == "keep":
        row["decision"] = "escalate"
    return row


def cmd_batch(a):
    """gate-wf's --jev path. stdin: findings array (only BATCH_SCHEMA_KEYS are
    read, so the workflow can pass its full finding objects). stdout: one JSON
    object {rows: [...]} — printed verbatim by the jev-runner agent and
    integrity-checked by the workflow before use."""
    try:
        fs = json.load(sys.stdin)
    except ValueError as e:
        print(json.dumps({"error": True, "stderr": "bad stdin json: %s" % e}))
        return 2
    if not isinstance(fs, list):
        print(json.dumps({"error": True, "stderr": "stdin is not a list"}))
        return 2
    fs = [f for f in fs if isinstance(f, dict) and (f.get("message") or "").strip()]
    if not fs:
        print(json.dumps({"rows": []}))
        return 0
    api_key = api_key_or_die(False)
    root = a.repo or os.getcwd()
    questions = load_questions()
    cur_head = (_git(root, "rev-parse", "HEAD") or "").strip()
    cache = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(lambda f: batch_one(f, root, questions, api_key,
                                               cache, cur_head), fs))
    out = {
        "rows": rows,
        "usage": {
            "input_tokens": sum(r.get("input_tokens", 0) for r in rows),
            "requests": len(rows),
        },
    }
    print(json.dumps(out))
    return 0


# --- state loading ----------------------------------------------------------

def collect(state, synthetic=False):
    """Returns (judgeable, dropped). Findings written by gate-wf before v5 carry
    only rule_id and tier — no message, no evidence, nothing for Jev to weigh.
    Sending them costs tokens and dilutes the agreement rate with rows that had
    no question in them."""
    fs = [f for f in (state.get("findings") or [])
          if isinstance(f, dict) and not f.get("fixed")]
    keep = [f for f in fs if (f.get("message") or "").strip()]
    if synthetic:
        keep = keep + [mutate(f, i) for i, f in enumerate(keep)]
    return keep, len(fs) - len([f for f in fs if (f.get("message") or "").strip()])


def state_files(root):
    d = F.state_dir(root)
    skip = (".dismissed.json", ".context.json", ".scope.json")
    return sorted(p for p in glob.glob(os.path.join(str(d), "*.json"))
                  if not p.endswith(skip))


def load_one(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None  # pre-v5 files were bare lists


# --- rendering --------------------------------------------------------------

def _clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n - 1] + "…"


def report(rows, elapsed, label):
    ok = [r for r in rows if "error" not in r and r.get("defect_real") is not None]
    print("\n%s — %d findings, %d scored" % (label, len(rows), len(ok)))
    print("%-4s %-8s %-30s %-7s %-6s %-9s %s" % (
        "id", "tier", "file:line", "sonnet", "jev", "severity", "flags"))
    print("-" * 100)
    for r in sorted(rows, key=lambda x: (x.get("defect_real") is None,
                                         x.get("defect_real") or 0)):
        s = r["sonnet"]
        flags = []
        if r.get("evidence") in ("none", "some", "off-anchor"):
            flags.append("quote:%s" % r["evidence"])
        if (r.get("needs_wider_context") or 0) >= 0.5:
            flags.append("needs-context")
        if r.get("fix_addresses") is not None and r["fix_addresses"] < 0.5:
            flags.append("fix?")
        if r.get("cited"):
            flags.append("cited")
        if r.get("synthetic"):
            flags.append("SYNTH")
        if r.get("severity_tier") and r["severity_tier"] != r.get("tier"):
            flags.append("tier→%s" % r["severity_tier"])
        d = r.get("decision", r.get("error", "?"))
        if d in ("kill", "escalate"):
            flags.insert(0, d.upper())
        print("%-4s %-8s %-30s %-7s %-6s %-9s %s" % (
            r.get("id") or "-", r.get("tier") or "-",
            _clip("%s:%s" % (os.path.basename(r.get("file") or "?"), r.get("line")), 30),
            "%d/%d" % (s["refuted"], s["total"]) if s["total"] else "none",
            ("%.2f" % r["defect_real"]) if r.get("defect_real") is not None else "-",
            ("%.2f %s" % (r["severity"], r.get("severity_tier", "")))
            if r.get("severity") is not None else "-",
            " ".join(flags)))

    toks = sum(r.get("input_tokens", 0) for r in rows)
    real_rows = [r for r in rows if not r.get("synthetic")]
    kill = sum(1 for r in real_rows if r.get("decision") == "kill")
    esc = sum(1 for r in real_rows if r.get("decision") == "escalate")
    votes = sum(r["sonnet"]["total"] for r in real_rows)
    print("-" * 100)
    print("jev:    %d requests, %d input tokens, $%.4f, %.1fs"
          % (len(rows), toks, toks / 1e6 * PRICE_PER_MTOK, elapsed))
    print("sonnet: %d skeptic subagents for the same findings (≤6 tool calls each)"
          % votes)
    print("disagreement: jev would KILL %d and ESCALATE %d of the %d real findings sonnet kept"
          % (kill, esc, len(real_rows)))
    real = [r for r in ok if not r.get("synthetic")]
    syn = [r for r in ok if r.get("synthetic")]
    if syn:
        skilled = sum(1 for r in syn if r.get("decision") == "kill")
        print("sensitivity: real mean %.2f vs synthetic mean %.2f — "
              "%d/%d planted findings killed (%.0f%%)"
              % (sum(r["defect_real"] for r in real) / max(len(real), 1),
                 sum(r["defect_real"] for r in syn) / len(syn),
                 skilled, len(syn), 100.0 * skilled / len(syn)))
    close = [r for r in real if r["sonnet"]["refuted"] > 0]
    clean = [r for r in real if r["sonnet"]["total"] and not r["sonnet"]["refuted"]]
    if close and clean:
        print("signal: mean %.2f where a skeptic voted refute (n=%d) vs %.2f where none did (n=%d)"
              % (sum(r["defect_real"] for r in close) / len(close), len(close),
                 sum(r["defect_real"] for r in clean) / len(clean), len(clean)))
    errs = [r for r in rows if "error" in r]
    if errs:
        print("errors: %d (%s)" % (len(errs), _clip(errs[0]["error"], 60)))


# --- commands ---------------------------------------------------------------

def run_rows(fs, root, sha, questions, api_key, no_call, workers=8):
    cur = (_git(root, "rev-parse", "HEAD") or "").strip()
    cache = {}
    if no_call:
        return [verify_one(f, root, sha, cur, questions, api_key, cache, True)
                for f in fs]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(
            lambda f: verify_one(f, root, sha, cur, questions, api_key, cache, False),
            fs))


def api_key_or_die(no_call):
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key and not no_call:
        print("jev-verify: TYPESAFE_API_KEY is not set. Get one at "
              "https://console.typesafe.ai/ then `export TYPESAFE_API_KEY=...`",
              file=sys.stderr)
        raise SystemExit(2)
    return key


def cmd_run(a):
    p = F.Paths()
    st = load_one(str(p.state))
    if not st:
        print("no prior gate-wf run on this branch — run the gate first",
              file=sys.stderr)
        return 1
    fs, dropped = collect(st, a.synthetic)
    if dropped:
        print("skipping %d finding(s) with no message (pre-v5 gate-wf state)" % dropped)
    if not fs:
        print("gate-wf state has no judgeable findings on this branch")
        return 0
    key = api_key_or_die(a.no_call)
    t0 = time.time()
    rows = run_rows(fs, p.root, head_sha(st.get("cache_key")),
                    load_questions(), key, a.no_call)
    if a.no_call:
        print(json.dumps([r.get("payload") for r in rows if r.get("payload")],
                         indent=2, ensure_ascii=False))
        return 0
    out = out_paths(p.root, p.branch)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"branch": p.branch, "at": F.now_iso(),
                   "verdict": st.get("verdict"), "rows": rows}, fh, indent=2)
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        report(rows, time.time() - t0, "%s (gate-wf: %s)"
               % (p.branch, st.get("verdict")))
        print("→ %s" % out)
    return 0


def cmd_corpus(a):
    p = F.Paths()
    key = api_key_or_die(False)
    qs = load_questions()
    cur = (_git(p.root, "rev-parse", "HEAD") or "").strip()
    jobs, skipped, dropped = [], 0, 0
    for path in state_files(p.root):
        st = load_one(path)
        if not st:
            continue
        sha = head_sha(st.get("cache_key"))
        if sha and sha != cur and _git(p.root, "cat-file", "-e",
                                       "%s^{commit}" % sha) is None:
            skipped += 1
            continue
        branch = os.path.basename(path)[:-5]
        found, drop = collect(st, a.synthetic)
        dropped += drop
        for f in found:
            jobs.append((branch, sha, f))
    if a.limit:
        jobs = jobs[:a.limit]
    if not jobs:
        print("no replayable findings in %s" % F.state_dir(p.root), file=sys.stderr)
        return 1
    print("replaying %d findings from %d branches "
          "(%d branches skipped: commit gone; %d findings skipped: no message)"
          % (len(jobs), len({j[0] for j in jobs}), skipped, dropped))
    cache = {}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(
            lambda j: dict(verify_one(j[2], p.root, j[1], cur, qs, key, cache, False),
                           branch=j[0]),
            jobs))
    out = out_paths(p.root, "_corpus")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"at": F.now_iso(), "rows": rows}, fh, indent=2)
    report(rows, time.time() - t0, "corpus")
    print("→ %s" % out)
    return 0


def cmd_calibrate(a):
    p = F.Paths()
    slug = F.state_dir(p.root).name
    files = sorted(glob.glob(os.path.expanduser(
        os.path.join("~/.claude/jev-verify", slug, "*.json"))))
    real, syn, seen = [], [], set()
    for f in files:
        d = load_one(f)
        if not d:
            continue
        for r in d.get("rows", []):
            if r.get("defect_real") is None:
                continue
            k = (r.get("branch"), r.get("file"), r.get("line"), r.get("rule_id"),
                 bool(r.get("synthetic")))
            if k in seen:   # _corpus.json and the per-branch files overlap
                continue
            seen.add(k)
            (syn if r.get("synthetic") else real).append(r)
    rows = real
    if not rows:
        print("nothing to calibrate — run `jev_verify.py corpus` first",
              file=sys.stderr)
        return 1
    print("%d real findings, %d planted, from %d files\n"
          % (len(real), len(syn), len(files)))
    print("%-7s  %-22s %s" % ("thresh", "real kept (sonnet", "planted killed"))
    print("%-7s  %-22s %s" % ("", "kept them too)", "(want high)"))
    print("-" * 60)
    best, best_t = -1.0, None
    for t, kept, n, killed, m in sweep(real, syn):
        x = kept / n if n else 0
        y = killed / m if m else 0
        if m and min(x, y) > best:
            best, best_t = min(x, y), t
        print("%-7.2f  %5d/%-5d %6.1f%%   %5d/%-5d %6.1f%%"
              % (t, kept, n, 100 * x, killed, m, 100 * y))
    if best_t is not None:
        print("\nbalanced at %.2f (worst of the two curves: %.0f%%)"
              % (best_t, 100 * best))
    else:
        print("\nNo planted findings on record. Every row here was KEPT by the "
              "sonnet\nskeptics, so this column alone cannot tell jev apart from "
              "a function\nthat always returns true. Run `corpus --synthetic`.")
    return 0


# --- self-check -------------------------------------------------------------

def self_check():
    L = ["aaa", "  bbb  ccccccc ", "ddd", "eee", "fff"]
    assert squeeze("  a   b \n c ") == "a b c"
    assert squeeze(None) == ""
    assert head_sha("abc1234_def5678_99_v5") == "abc1234"
    assert head_sha("") is None and head_sha(None) is None
    s = slice_code(L, 3, radius=1)
    assert "\n" in s and ">     3 | ddd" in s and "aaa" not in s, s
    assert slice_code(L, 1, radius=10).count("\n") == 4
    assert slice_code(L, 99, radius=1) == ""  # window past EOF
    assert slice_code([], 1) == ""
    assert slice_code(L, 0, radius=0).strip().startswith(">"), slice_code(L, 0, radius=0)
    assert len(slice_code(["x" * 100] * 200, 100, max_chars=50)) < 80
    assert quoted_spans("prose only, no code") == []
    assert quoted_spans("see `bbb  ccccccc` here") == ["bbb ccccccc"]
    assert quoted_spans("`if (x) { ... } else { yyyyyyyy }`") == \
        ["if (x) {", "} else { yyyyyyyy }"], quoted_spans("`if (x) { ... } else { yyyyyyyy }`")
    assert quoted_spans("`short`") == []               # below minlen
    assert evidence_status(L, 2, "no backticks here") == "no-quote"
    assert evidence_status(L, 2, "quote `bbb  ccccccc` x") == "all"  # whitespace-insensitive
    assert evidence_status(L, 5, "`bbb ccccccc`", radius=1) == "off-anchor"
    assert evidence_status(L, 1, "`zzzzzzzzzz`") == "none"
    assert evidence_status(L, 1, "`bbb ccccccc` and `zzzzzzzzzz`") == "some"
    assert evidence_status(None, 1, "`a`") == "unreadable"
    assert jev_decision(0.9, False) == "keep"
    assert jev_decision(0.5, False) == "escalate"
    assert jev_decision(0.1, False) == "kill"
    assert jev_decision(0.1, True) == "escalate", "cited findings resist refutation"
    assert jev_decision(0.05, True) == "kill"
    assert jev_decision(None, False) == "error"
    st = build_state({"file": "a.ts", "line": 3, "rule_id": "r", "message": "m",
                      "evidence": "e", "suggested_fix": "s"}, "CODE")
    assert st["code"] == "CODE" and "rule_citation" not in st
    assert build_state({"citation": "c", "source": "CLAUDE.md"}, "")["rule_citation"]["text"] == "c"
    sw = sweep([{"defect_real": 0.9}, {"defect_real": 0.4}, {"defect_real": None}],
               [{"defect_real": 0.1}])
    assert sw[0] == (0.05, 2, 2, 0, 1), sw[0]
    assert sw[-1] == (0.95, 0, 2, 1, 1), sw[-1]
    assert mutate({"line": 10}, 0)["line"] == 10 + SHIFT
    assert mutate({"line": None}, 0)["line"] == SHIFT
    assert SHIFT > 2 * RADIUS, "mutated window must not overlap the original"
    assert collect({"findings": [{"message": "m"}, {"fixed": True},
                                 {"rule_id": "r"}]}) == ([{"message": "m"}], 1)
    assert len(collect({"findings": [{"line": 1, "message": "m"}]},
                       synthetic=True)[0]) == 2
    print("✓ self-check passed")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jev_verify.py")
    ap.add_argument("--self-check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("batch", help="judge findings from stdin (gate-wf --jev)")
    b.add_argument("--repo", default="", help="repo root (default: cwd)")

    r = sub.add_parser("run", help="replay this branch's last gate-wf run")
    r.add_argument("--no-call", action="store_true",
                   help="print the Jev payloads, hit no network")
    r.add_argument("--json", action="store_true")
    r.add_argument("--synthetic", action="store_true")

    c = sub.add_parser("corpus", help="replay every gate-wf run for this repo")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--synthetic", action="store_true")

    sub.add_parser("preflight", help="one ~300-token call: is the key live and credited")

    sub.add_parser("calibrate", help="threshold sweep over accumulated results")

    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()
    if a.cmd == "batch":
        return cmd_batch(a)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "corpus":
        return cmd_corpus(a)
    if a.cmd == "preflight":
        key = api_key_or_die(False)
        ok, msg = preflight(key)
        print(("\u2713 " if ok else "\u2717 ") + msg)
        return 0 if ok else 1
    if a.cmd == "calibrate":
        return cmd_calibrate(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
