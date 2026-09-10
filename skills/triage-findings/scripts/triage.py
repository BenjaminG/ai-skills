#!/usr/bin/env python3
"""Selection side of triage-findings: read gate-wf's state, drop what the code
has outrun, resolve the selector, print a plan grouped by file.

Grouped by file because that is the unit of work: five findings in one mapper is
one edit, not five, and their fixes routinely contradict each other. A plan
listed finding-by-finding hides that and produces five successive rewrites of
the same file.

    triage.py plan [selector]     # selector: blockers | nits | cleanup | bugs | B1 M2 | a.ts | (free text)
    triage.py mark-fixed B1,N2
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_findings_module():
    """gate-wf owns findings.py; there must be exactly one implementation of the
    content anchor, so import it rather than copying it."""
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
            sys.path.insert(0, os.path.abspath(c))
            import findings  # noqa: F401
            return findings
    print("triage-findings: gate-wf's scripts/findings.py not found — "
          "reinstall the plugin", file=sys.stderr)
    raise SystemExit(2)


F = _load_findings_module()

# Reviewers whose findings are a disagreement to settle, not a fix to apply.
# Kept as a hint: the model still reads each one and decides.
DECISION_RULES = ("bug-spec-mismatch",)


def _one(s) -> str:
    return " ".join(str(s or "").split())


def cmd_plan(p, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no gate-wf findings for this branch — run `gate-wf` first "
              "(triage never launches it for you: that is dozens of agents)",
              file=sys.stderr)
        return 1

    live = [f for f in state.get("findings", []) if not f.get("fixed")]
    fresh = [f for f in live if not F.stale(p.root, f)]
    n_stale = len(live) - len(fresh)

    selector = " ".join(a.selector).strip()
    picked = F.select(fresh, selector or None)
    free_text = picked is None
    if free_text:
        picked = fresh

    print(f"branch: {p.branch}   gate run: {state.get('run_id') or '—'} "
          f"({state.get('cached_at', '—')})")
    print(f"{len(live)} findings on record · {len(fresh)} still match the code"
          + (f" · {n_stale} outdated, dropped" if n_stale else ""))
    if n_stale and not fresh:
        print("every finding is outdated — re-run `gate-wf` before triaging.")
        return 1
    if free_text:
        print(f'selector "{selector}" is not a literal one — the full fresh set '
              "follows; pick from it by intent, then confirm the plan.")
    else:
        print(f"selector: {selector or 'default (BLOCKER + MAJOR)'} "
              f"→ {len(picked)} selected")

    decision = [f for f in picked if f.get("rule_id") in DECISION_RULES]
    if decision:
        print("\n-- likely decision-required (verify, then keep out of the batch) --")
        for f in decision:
            print(f"{f['id']} {f.get('file')}:{f.get('line')} — {_one(f.get('message'))}")

    by_file: dict[str, list] = {}
    for f in picked:
        by_file.setdefault(f.get("file", "?"), []).append(f)

    for path in sorted(by_file):
        group = sorted(by_file[path], key=lambda f: int(f.get("line") or 0))
        print(f"\n== {path}  ({len(group)} finding{'s' if len(group) > 1 else ''})")
        for f in group:
            flags = []
            if F.unverified(f):
                flags.append("unverified")
            if f.get("context_verdict") in ("CONFLICT", "UNCERTAIN"):
                flags.append(f.get("context_verdict").lower())
            head = f"{f['id']} [{f.get('tier')}] {f.get('rule_id')} :{f.get('line')}"
            print(f"  {head}" + (f"  ({', '.join(flags)})" if flags else ""))
            print(f"    what: {_one(f.get('message'))}")
            if f.get("evidence"):
                print(f"    evidence: {_one(f.get('evidence'))}")
            if f.get("suggested_fix"):
                print(f"    lead: {_one(f.get('suggested_fix'))}")
            if f.get("citation"):
                print(f"    rule: {_one(f.get('citation'))}")
    return 0


def cmd_mark_fixed(p, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no gate-wf findings for this branch", file=sys.stderr)
        return 1
    ids = [i for i in a.ids.replace(",", " ").split() if i]
    hit = F.mark_fixed(state, ids)
    state["verdict"] = F.verdict(state.get("findings", []))
    F.save_state(p, state)
    missing = {i.upper() for i in ids} - {f["id"].upper() for f in hit}
    print(f"marked fixed: {', '.join(f['id'] for f in hit) or 'none'} "
          f"→ verdict {state['verdict']}")
    if missing:
        print(f"unknown ids: {', '.join(sorted(missing))}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="triage.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("selector", nargs="*")
    mf = sub.add_parser("mark-fixed")
    mf.add_argument("ids")
    a = ap.parse_args(argv)
    p = F.Paths()
    return {"plan": cmd_plan, "mark-fixed": cmd_mark_fixed}[a.cmd](p, a)


if __name__ == "__main__":
    sys.exit(main())
