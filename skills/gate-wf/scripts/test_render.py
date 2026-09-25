#!/usr/bin/env python3
"""Self-check for the gate-wf renderer. Run: python3 scripts/test_render.py

The anchor test is the one that matters: it re-implements the bash
`gatewf_anchor` this replaces and compares, because a drift there silently
resurrects every dismissed finding on the next run.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import findings as F  # noqa: E402
import render as R  # noqa: E402

BASH_ANCHOR = r"""
gatewf_anchor() {
  local rule_id="$1" file="$2" line="$3" txt
  txt=$(sed -n "${line}p" -- "$REPO_ROOT/$file" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
  [ -z "$txt" ] && return 1
  printf '%s' "${rule_id}::${file}::${txt}" | shasum | cut -c1-12
}
gatewf_anchor "$1" "$2" "$3"
"""


def test_anchor_matches_bash():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        (root / "src" / "a.ts").write_text(
            "const x = 1;\n"
            "  return   safeMultiplyByFactor(totals?.subtotalExclVat ?? null) ?? 0;\t\n"
            "\n"
            "\tdeep\tindent\n"
        )
        for line in (1, 2, 4):
            mine = F.anchor(root, "claude-md-violation", "src/a.ts", line)
            theirs = subprocess.run(
                ["bash", "-c", BASH_ANCHOR, "_", "claude-md-violation", "src/a.ts", str(line)],
                capture_output=True, text=True, env={**os.environ, "REPO_ROOT": str(root)},
            ).stdout.strip()
            assert mine == theirs, f"line {line}: python {mine} != bash {theirs}"
        # A blank line and an out-of-range line are unanchorable → stay active.
        assert F.anchor(root, "r", "src/a.ts", 3) is None
        assert F.anchor(root, "r", "src/a.ts", 99) is None
        assert F.anchor(root, "r", "src/gone.ts", 1) is None
        # rule_id scopes the anchor: same line, different rule → different id.
        assert F.anchor(root, "r1", "src/a.ts", 1) != F.anchor(root, "r2", "src/a.ts", 1)


def test_verdict_and_ids():
    mk = lambda t, f, l: {"tier": t, "file": f, "line": l, "rule_id": "r", "message": "m"}
    fs = [mk("NIT", "b.ts", 2), mk("BLOCKER", "z.ts", 1), mk("MAJOR", "a.ts", 9),
          mk("MAJOR", "a.ts", 3), mk("NIT", "a.ts", 1)]
    active, dismissed = F.assign_ids(list(fs), [])
    assert [f["id"] for f in active] == ["B1", "M1", "M2", "N1", "N2"]
    # tier → file → line, so M1 is a.ts:3 and M2 is a.ts:9
    assert (active[1]["file"], active[1]["line"]) == ("a.ts", 3)
    assert F.verdict(active) == "FAIL"
    assert F.verdict([f for f in active if f["tier"] != "BLOCKER"]) == "PASS WITH NOTES"
    assert F.verdict([]) == "PASS"
    # Re-running is stable: same set in, same ids out.
    again, _ = F.assign_ids(list(reversed(fs)), [])
    assert [f["id"] for f in again] == [f["id"] for f in active]


def test_partition_and_selection():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "a.ts").write_text("const x = 1;\n")
        f = {"tier": "MAJOR", "file": "a.ts", "line": 1, "rule_id": "slop-unused", "message": "m"}
        anc = F.anchor(root, "slop-unused", "a.ts", 1)
        reg = {"version": 1, "dismissals": [
            {"anchor": anc, "source": "manual", "confidence": "manual", "citation": "c"}]}
        active, dismissed = F.partition(root, [dict(f)], reg)
        assert not active and len(dismissed) == 1 and dismissed[0]["citation"] == "c"
        # Editing the flagged code lifts the dismissal by itself.
        (root / "a.ts").write_text("const x = 2;\n")
        active, dismissed = F.partition(root, [dict(f)], reg)
        assert len(active) == 1 and not dismissed

    pool = [
        {"id": "B1", "tier": "BLOCKER", "rule_id": "claude-md-violation", "file": "x/a.ts"},
        {"id": "M1", "tier": "MAJOR", "rule_id": "bug-parity", "file": "x/b.ts"},
        {"id": "N1", "tier": "NIT", "rule_id": "slop-unused", "file": "x/a.ts"},
        {"id": "N2", "tier": "NIT", "rule_id": "simplify-redundant", "file": "x/c.ts"},
    ]
    ids = lambda sel: [f["id"] for f in sel]
    assert ids(F.select(pool, None)) == ["B1", "M1"]
    assert ids(F.select(pool, "blockers")) == ["B1"]
    assert ids(F.select(pool, "cleanup")) == ["N1", "N2"]
    assert ids(F.select(pool, "bugs")) == ["M1"]
    assert ids(F.select(pool, "B1 N2")) == ["B1", "N2"]
    assert ids(F.select(pool, "a.ts")) == ["B1", "N1"]
    assert F.select(pool, "things that shrink the code") is None  # → model


def test_render_never_cuts_silently():
    long = "safeMultiplyByFactor(totals?.subtotalExclVat ?? null) ?? 0 everywhere"
    assert R._clip(long, 20).endswith("…") and len(R._clip(long, 20)) == 20
    assert R._clip("short", 20) == "short"
    mid = R._clip_mid("quote-document-extraction-from-re-invoicing.utils.ts:81", 30)
    assert len(mid) == 30 and "…" in mid
    assert mid.startswith("quote-doc") and mid.endswith(":81")  # line number survives
    assert R._one_line("a\n  b\tc") == "a b c"


def test_workflow_script_loads():
    """The Workflow tool refuses a script that fails to parse or whose meta reads a variable."""
    src = Path(__file__).with_name("workflow.js").read_text()
    with tempfile.TemporaryDirectory() as d:
        # The harness runs the body inside an async function (top-level return/await).
        body = Path(d) / "w.js"
        body.write_text("(async () => {\n" + src.replace("export const meta", "const meta", 1) + "\n})")
        r = subprocess.run(["node", "--check", str(body)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    meta = src.split("export const meta = ", 1)[1].split("\n}\n", 1)[0] + "\n}"
    r = subprocess.run(["node", "-e", f"({meta})"], capture_output=True, text=True)
    assert r.returncode == 0, "meta must be a pure literal:\n" + r.stderr


def test_end_to_end(tmp_state=True):
    """ingest → brief → show on a throwaway git repo, exercising the real CLI."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "repo"
        root.mkdir()
        env = {**os.environ, "HOME": d, "NO_COLOR": "1"}
        run = lambda *a, **k: subprocess.run(*a, **k, cwd=root, env=env,
                                             capture_output=True, text=True)
        run(["git", "init", "-q", "-b", "main"])
        (root / "a.ts").write_text("const total = value ?? 0;\nexport const dead = 1;\n")
        run(["git", "add", "-A"])
        run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"])

        fjson = Path(d) / "f.json"
        fjson.write_text(json.dumps([
            {"tier": "BLOCKER", "file": "a.ts", "line": 1, "rule_id": "claude-md-violation",
             "reviewer": "context-checker", "message": "?? 0 papers over a nullable return",
             "evidence": "value ?? 0", "suggested_fix": "branch on null",
             "citation": "CLAUDE.md:38", "verifications": [{"refuted": False}] * 3},
            {"tier": "NIT", "file": "a.ts", "line": 2, "rule_id": "slop-unused",
             "reviewer": "slop-reviewer", "message": "export with no consumer",
             "verifications": []},
        ]))
        script = Path(__file__).with_name("render.py")
        out = run([sys.executable, str(script), "ingest", "--findings", str(fjson),
                   "--run-id", "wf_test", "--files", "1", "--add", "2", "--del", "0"])
        assert "FAIL" in out.stdout, out.stderr

        brief = run([sys.executable, str(script), "brief"]).stdout
        assert "B1 BLOCKER claude-md-violation a.ts:1" in brief
        assert "evidence" not in brief  # brief drops the bulky fields

        summary = Path(d) / "s.md"
        summary.write_text("Un seul truc bloque : B1.\nN1 est du menage.")
        shown = run([sys.executable, str(script), "show", "--summary-file", str(summary)]).stdout
        assert "En clair" in shown and "Un seul truc bloque" in shown
        assert shown.index("En clair") < shown.index("B1 ")  # summary above the table
        assert "? unverified" in shown  # N1 carries the marker and its legend
        report = Path(d) / ".claude/gate-wf-state"
        md = next(report.rglob("*.report.md")).read_text()
        assert "refute votes: 0/3" in md and "fix: branch on null" in md

        # Dismissing B1 flips the verdict without re-running the gate.
        dis = run([sys.executable, str(script), "dismiss", "B1"]).stdout
        assert "PASS WITH NOTES" in dis and "1 dismissed" in dis
        back = run([sys.executable, str(script), "undismiss", "D1"]).stdout
        assert "FAIL" in back


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"✅ All tests passed ({len(fns)} tests)")
