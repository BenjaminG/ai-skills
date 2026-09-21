#!/usr/bin/env python3
"""Offline checks for jev_verify.py. No network, ever.

    python3 scripts/test_jev_verify.py

The pure helpers live in jev_verify.self_check(); this file covers what needs a
real repo on disk: the worktree/git-blob fallback, state-file discovery, and an
end-to-end --no-call run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import jev_verify as J  # noqa: E402


def sh(*args, cwd=None, env=None, stdin=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                          input=stdin)


def make_repo(d):
    """A repo with two commits, so a state file can point at the older blob."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    sh("git", "init", "-q", "-b", "main", d, env=env)
    src = os.path.join(d, "a.ts")
    with open(src, "w") as fh:
        fh.write("\n".join("old line %d" % i for i in range(1, 21)) + "\n")
    sh("git", "add", "-A", cwd=d, env=env)
    sh("git", "commit", "-qm", "one", cwd=d, env=env)
    old = sh("git", "rev-parse", "HEAD", cwd=d).stdout.strip()
    with open(src, "w") as fh:
        fh.write("\n".join("new line %d" % i for i in range(1, 21)) + "\n")
    sh("git", "add", "-A", cwd=d, env=env)
    sh("git", "commit", "-qm", "two", cwd=d, env=env)
    new = sh("git", "rev-parse", "HEAD", cwd=d).stdout.strip()
    return old, new


def test_read_lines():
    with tempfile.TemporaryDirectory() as d:
        old, new = make_repo(d)
        cache = {}
        # recorded sha == current HEAD -> worktree
        lines = J.read_lines(d, "a.ts", new, new, cache)
        assert lines[0] == "new line 1", lines[:1]
        # older sha -> that blob, not the worktree
        lines = J.read_lines(d, "a.ts", old, new, cache)
        assert lines[0] == "old line 1", lines[:1]
        # cached separately per (path, sha)
        assert len(cache) == 2, cache.keys()
        # unknown path -> None, and no crash
        assert J.read_lines(d, "nope.ts", new, new, cache) is None
        # sha gone from the repo -> falls back to the worktree
        lines = J.read_lines(d, "a.ts", "0" * 40, new, {})
        assert lines[0] == "new line 1"
    print("✓ read_lines: worktree / blob / fallback")


def test_state_discovery():
    with tempfile.TemporaryDirectory() as d:
        sd = os.path.join(d, "state")
        os.makedirs(sd)
        for n in ("br.json", "br.dismissed.json", "br.context.json",
                  "br.scope.json", "other.json"):
            with open(os.path.join(sd, n), "w") as fh:
                fh.write("{}")

        class P:
            name = "slug"
            def __str__(self): return sd
        orig = J.F.state_dir
        J.F.state_dir = lambda root: P()
        try:
            got = [os.path.basename(p) for p in J.state_files(d)]
        finally:
            J.F.state_dir = orig
        assert got == ["br.json", "other.json"], got

        with open(os.path.join(sd, "legacy.json"), "w") as fh:
            fh.write("[]")
        assert J.load_one(os.path.join(sd, "legacy.json")) is None, "pre-v5 bare list"
        assert J.load_one(os.path.join(sd, "br.json")) == {}
        assert J.load_one(os.path.join(sd, "missing.json")) is None
    print("✓ state discovery: sidecars skipped, legacy lists skipped")


def test_no_call_end_to_end():
    """A full `run --no-call` in a throwaway repo with a doctored HOME."""
    with tempfile.TemporaryDirectory() as d:
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        old, new = make_repo(repo)
        home = os.path.join(d, "home")
        env = {**os.environ, "HOME": home, "NO_COLOR": "1"}
        env.pop("TYPESAFE_API_KEY", None)

        # Ask findings.py itself where this repo's state file goes — the repo
        # path here is a symlink (/var -> /private/var) and the slug is a hash of
        # whatever `git rev-parse --show-toplevel` resolves to.
        out = sh(sys.executable, "-c",
                 "import sys;sys.path.insert(0,%r);import findings as F;"
                 "print(F.Paths().state)"
                 % os.path.join(_HERE, "../../gate-wf/scripts"),
                 cwd=repo, env=env)
        sfile = out.stdout.strip()
        assert sfile, out.stderr
        os.makedirs(os.path.dirname(sfile), exist_ok=True)
        state = {
            "cache_key": "%s_%s_ab_v5" % (new, old),
            "verdict": "FAIL",
            "findings": [{
                "id": "B1", "rule_id": "bug-x", "file": "a.ts", "line": 10,
                "tier": "BLOCKER", "message": "boom", "evidence": "new line 10",
                "suggested_fix": "do not boom", "reviewer": "bug",
                "verifications": [{"refuted": False, "reason": "real"}],
            }, {
                "id": "N1", "rule_id": "slop-y", "file": "gone.ts", "line": 3,
                "tier": "NIT", "message": "m", "evidence": "e",
                "suggested_fix": "s", "reviewer": "slop", "verifications": [],
            }],
        }
        with open(sfile, "w") as fh:
            json.dump(state, fh)

        r = sh(sys.executable, os.path.join(_HERE, "jev_verify.py"),
               "run", "--no-call", cwd=repo, env=env)
        assert r.returncode == 0, r.stderr
        payloads = json.loads(r.stdout)
        assert len(payloads) == 1, "the unreadable file is dropped, not crashed on"
        p = payloads[0]
        assert p["file"] == "a.ts" and p["line"] == 10
        assert ">    10 | new line 10" in p["code"], p["code"][:200]
        assert p["finding"]["rule_id"] == "bug-x"
        assert "rule_citation" not in p

        # no key + a real call -> refuses before touching the network
        r = sh(sys.executable, os.path.join(_HERE, "jev_verify.py"),
               "run", cwd=repo, env=env)
        assert r.returncode == 2 and "TYPESAFE_API_KEY" in r.stderr, r.stderr

        # no state file at all -> gate-wf's own message, exit 1
        empty = os.path.join(d, "empty")
        os.makedirs(empty)
        make_repo(empty)
        r = sh(sys.executable, os.path.join(_HERE, "jev_verify.py"),
               "run", "--no-call", cwd=empty, env=env)
        assert r.returncode == 1 and "run the gate first" in r.stderr, r.stderr
    print("✓ run --no-call: payload shape, missing file, missing key, no state")


def test_batch_mode():
    """The gate-wf --jev contract: findings on stdin, one JSON object on stdout,
    every failure routing to escalate so no finding is ever lost."""
    with tempfile.TemporaryDirectory() as d:
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        make_repo(repo)
        with open(os.path.join(repo, "a.ts"), "a") as fh:
            fh.write("\n".join("line %d boom" % i for i in range(1, 101)) + "\n")
        env = {**os.environ, "HOME": os.path.join(d, "home"), "NO_COLOR": "1",
               "TYPESAFE_API_KEY": "k_test"}

        import unittest.mock as mock
        findings = [
            {"file": "a.ts", "line": 50, "rule_id": "r", "tier": "MAJOR",
             "message": "boom", "evidence": "boom", "suggested_fix": "x"},
            {"file": "a.ts", "line": 50, "rule_id": "c", "tier": "BLOCKER",
             "message": "cited boom", "citation": "rule", "source": "CLAUDE.md"},
            {"file": "gone.ts", "line": 1, "rule_id": "r", "tier": "NIT",
             "message": "m"},          # unreadable -> escalate
            {"rule_id": "r"},           # no message -> filtered out
        ]

        qs = J.load_questions()
        cache = {}

        def run_batch():
            return [J.batch_one(f, repo, qs, "k_test", cache, "any")
                    for f in findings
                    if (f.get("message") or "").strip()]

        # high confidence, no wider context -> keep
        # The mock must patch the subprocess's urllib, not ours: set the env
        # var the script reads to a sentinel and patch at source level via a
        # wrapper module is overkill — instead run with PYTHONDONTWRITEBYTECODE
        # and patch urlopen through the API_URL indirection the script uses...
        # Simplest reliable route: fake the API by pointing API_URL at a local
        # socket is heavy; so monkeypatch via `sitecustomize` is too. We patch
        # in-process instead (batch_one is pure apart from call_jev).
        with mock.patch.object(J, "call_jev",
                               side_effect=lambda st, q, k, t=60: {
                                   "answers": {"defect_real": {"noul": 0.9},
                                               "needs_wider_context": {"noul": 0.2}},
                                   "usage": {"input_tokens": 10}}):
            rows = run_batch()
            assert len(rows) == 3, rows
            assert rows[0]["decision"] == "keep"
            assert rows[0]["msg_len"] == 4
            assert rows[1]["decision"] == "keep"  # cited: also kept at 0.9
            assert rows[2]["decision"] == "escalate" and rows[2]["error"] == "unreadable"

        # mid-band -> escalate; needs-context overrides a keep
        with mock.patch.object(J, "call_jev",
                               side_effect=lambda st, q, k, t=60: {
                                   "answers": {"defect_real": {"noul": 0.55},
                                               "needs_wider_context": {"noul": 0.9}},
                                   "usage": {"input_tokens": 10}}):
            rows = run_batch()
            assert rows[0]["decision"] == "escalate"  # 0.55 in band
            assert rows[1]["decision"] == "escalate"

        # low -> kill. Cited findings resist only inside the band (floor 0.10
        # vs 0.50), not below it: 0.05 is a clear refutation even for a rule.
        with mock.patch.object(J, "call_jev",
                               side_effect=lambda st, q, k, t=60: {
                                   "answers": {"defect_real": {"noul": 0.05},
                                               "needs_wider_context": {"noul": 0.1}},
                                   "usage": {"input_tokens": 10}}):
            rows = run_batch()
            assert rows[0]["decision"] == "kill"
            assert rows[1]["decision"] == "kill"   # cited floor is 0.10, not a blanket keep
            assert rows[2]["decision"] == "escalate"

        # and the band itself: 0.30 kills an uncited finding, spares a cited one
        with mock.patch.object(J, "call_jev",
                               side_effect=lambda st, q, k, t=60: {
                                   "answers": {"defect_real": {"noul": 0.30},
                                               "needs_wider_context": {"noul": 0.1}},
                                   "usage": {"input_tokens": 10}}):
            rows = run_batch()
            assert rows[0]["decision"] == "kill"
            assert rows[1]["decision"] == "escalate"  # cited: 0.30 is above its floor

        # API down -> every row escalates, nothing is lost
        def boom(st, q, k, t=60):
            raise J.urllib.error.URLError("api down")
        with mock.patch.object(J, "call_jev", side_effect=boom):
            rows = run_batch()
            assert all(x["decision"] == "escalate" for x in rows), rows
            assert "api down" in rows[0]["error"], rows[0]["error"]  # urllib wraps: '<urlopen error ...>' 

        # no key -> error object, exit 2
        env2 = dict(env); env2.pop("TYPESAFE_API_KEY")
        r = sh(sys.executable, os.path.join(_HERE, "jev_verify.py"),
               "batch", "--repo", repo, env=env2,
               stdin=json.dumps(findings[:1]))
        assert r.returncode == 2, (r.returncode, r.stderr)
    print("\u2713 batch: keep/kill/escalate routing, api-down fallback, no-message filter")


def test_cited_threshold():
    """The one asymmetry copied from agents/skeptic.md: a finding resting on a
    quoted project rule needs far more doubt before it dies."""
    for p in (0.11, 0.2, 0.29):
        assert J.jev_decision(p, False) == "kill"
        assert J.jev_decision(p, True) != "kill"
    print("✓ cited findings survive where uncited ones are killed")


if __name__ == "__main__":
    J.self_check()
    test_read_lines()
    test_state_discovery()
    test_no_call_end_to_end()
    test_batch_mode()
    test_cited_threshold()
    print("\nall passed")
