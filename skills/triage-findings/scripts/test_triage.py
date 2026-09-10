#!/usr/bin/env python3
"""Self-check for triage-findings. Run: python3 scripts/test_triage.py

Covers the two things that would make the skill propose wrong work: staleness
(offering a fix for code already changed) and mark-fixed (a finding that keeps
FAILing the gate after it was fixed).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRIAGE = HERE / "triage.py"
RENDER = HERE.parent.parent / "gate-wf" / "scripts" / "render.py"

FINDINGS = [
    {"tier": "BLOCKER", "file": "a.ts", "line": 1, "rule_id": "claude-md-violation",
     "reviewer": "context-checker", "message": "?? 0 papers over a nullable return",
     "suggested_fix": "branch on null", "verifications": [{"refuted": False}] * 3},
    {"tier": "MAJOR", "file": "b.ts", "line": 1, "rule_id": "bug-spec-mismatch",
     "reviewer": "bug-reviewer", "message": "code refuses both, spec says the second",
     "verifications": [{"refuted": False}]},
    {"tier": "NIT", "file": "a.ts", "line": 2, "rule_id": "slop-unused",
     "reviewer": "slop-reviewer", "message": "export with no consumer",
     "verifications": []},
    {"tier": "NIT", "file": "b.ts", "line": 2, "rule_id": "simplify-redundant",
     "reviewer": "simplify-reviewer", "message": "two near-identical map blocks",
     "verifications": []},
]


def _repo(d: Path):
    root = d / "repo"
    root.mkdir()
    env = {**os.environ, "HOME": str(d), "NO_COLOR": "1"}
    run = lambda *a: subprocess.run(*a, cwd=root, env=env, capture_output=True, text=True)
    run(["git", "init", "-q", "-b", "main"])
    (root / "a.ts").write_text("const total = value ?? 0;\nexport const dead = 1;\n")
    (root / "b.ts").write_text("refuseAll(entries);\nitems.map(x => x.a);\n")
    run(["git", "add", "-A"])
    run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"])
    fj = d / "f.json"
    fj.write_text(json.dumps(FINDINGS))
    run([sys.executable, str(RENDER), "ingest", "--findings", str(fj),
         "--run-id", "wf_t", "--files", "2", "--add", "4", "--del", "0"])
    return root, run


def test_selectors_and_grouping():
    with tempfile.TemporaryDirectory() as d:
        root, run = _repo(Path(d))
        default = run([sys.executable, str(TRIAGE), "plan"]).stdout
        assert "default (BLOCKER + MAJOR) → 2 selected" in default
        assert "== a.ts" in default and "== b.ts" in default
        assert "lead: branch on null" in default  # suggested_fix reaches the plan
        # bug-spec-mismatch is surfaced as decision-required, not as work
        assert "decision-required" in default and "M1" in default

        cleanup = run([sys.executable, str(TRIAGE), "plan", "cleanup"]).stdout
        assert "→ 2 selected" in cleanup and "slop-unused" in cleanup
        assert "claude-md-violation" not in cleanup
        assert "(unverified)" in cleanup  # nits are never adversarially checked

        ids = run([sys.executable, str(TRIAGE), "plan", "B1", "N2"]).stdout
        assert "→ 2 selected" in ids

        free = run([sys.executable, str(TRIAGE), "plan", "things that shrink the code"]).stdout
        assert "is not a literal one" in free and "→ 4" not in free
        assert free.count("== ") == 2  # whole fresh set handed over, still grouped


def test_stale_findings_are_dropped():
    with tempfile.TemporaryDirectory() as d:
        root, run = _repo(Path(d))
        # Fix B1 by hand: its anchor line no longer reads the same.
        (root / "a.ts").write_text("const total = value ?? fallback;\nexport const dead = 1;\n")
        out = run([sys.executable, str(TRIAGE), "plan", "all"]).stdout
        assert "1 outdated, dropped" in out
        assert "B1 " not in out, out


def test_mark_fixed_moves_the_verdict():
    with tempfile.TemporaryDirectory() as d:
        root, run = _repo(Path(d))
        out = run([sys.executable, str(TRIAGE), "mark-fixed", "B1"]).stdout
        assert "verdict PASS WITH NOTES" in out
        shown = run([sys.executable, str(RENDER), "show"]).stdout
        assert "PASS WITH NOTES" in shown
        assert "1 fixed" in shown and "Fixed by triage (not counted): B1" in shown
        assert "B1 " not in shown.split("Fixed by triage")[0].split("BLOCKER 0")[1]
        # A fixed finding no longer offered as work.
        assert "B1" not in run([sys.executable, str(TRIAGE), "plan", "all"]).stdout
        md = next((Path(d) / ".claude/gate-wf-state").rglob("*.report.md")).read_text()
        assert "## Fixed by triage" in md


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"✅ All tests passed ({len(fns)} tests)")
