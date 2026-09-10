#!/usr/bin/env python3
"""gate-wf report renderer + dismissal registry CLI.

Everything deterministic about the report lives here: verdict math, ID
assignment, the active/dismissed partition, refute-vote counts, and the two
outputs (a scannable terminal table, a full-detail markdown file).

The model's only writing job is the 5-line summary, handed in via
`--summary-file` so it lands above the table rather than below it.

    render.py ingest --findings f.json --run-id wf_x --files 12 --add 998 --del 3
    render.py brief                        # compact digest, for writing the summary
    render.py show --summary-file s.md     # terminal report + report.md
    render.py dismiss B1,M2 | undismiss D1 | show-dismissed
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import findings as F  # noqa: E402

TIER_SHORT = {"BLOCKER": "BLK", "MAJOR": "MAJ", "NIT": "NIT"}
COLOR = {"BLOCKER": "\033[1;31m", "MAJOR": "\033[33m", "NIT": "\033[2m"}
RESET = "\033[0m"


def _tty() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _paint(s: str, tier: str) -> str:
    return f"{COLOR.get(tier, '')}{s}{RESET}" if _tty() else s


def _one_line(s) -> str:
    return " ".join(str(s or "").split())


def _clip(s: str, w: int) -> str:
    """Truncate with an explicit ellipsis — a silent cut reads as content."""
    return s if len(s) <= w else s[: w - 1] + "…"


def _clip_mid(s: str, w: int) -> str:
    """Keep both ends: a path's head identifies it, its tail carries the line."""
    if len(s) <= w:
        return s
    keep = w - 1
    head = (keep + 1) // 2
    return s[:head] + "…" + s[len(s) - (keep - head) :]


def _mark(f: dict) -> str:
    if f.get("context_verdict") in ("CONFLICT", "UNCERTAIN"):
        return "!"
    return "?" if F.unverified(f) else " "


# --- terminal report ---------------------------------------------------------


def _table(active: list[dict]) -> list[str]:
    rows = []
    for f in F.counted(active):
        loc = f"{os.path.basename(f.get('file', ''))}:{f.get('line', '')}"
        rows.append((f["id"], f.get("tier", "NIT"), _mark(f), loc,
                     _one_line(f.get("rule_id")), _one_line(f.get("message"))))

    width = max(80, min(shutil.get_terminal_size((120, 24)).columns, 200))
    file_w = min(max(len(r[3]) for r in rows), 40)
    rule_w = min(max(len(r[4]) for r in rows), 24)
    # prefix: "B10 BLK ! " → 4 + 4 + 2
    gutter = 10 + 2 + 2
    while width - gutter - file_w - rule_w < 24 and (file_w > 24 or rule_w > 14):
        if file_w - 24 >= rule_w - 14:
            file_w -= 1
        else:
            rule_w -= 1
    msg_w = max(12, width - gutter - file_w - rule_w)

    out = []
    for fid, tier, mark, loc, rule, msg in rows:
        out.append(
            f"{fid:<3} {_paint(TIER_SHORT.get(tier, tier[:3]), tier):<3} {mark} "
            f"{_clip_mid(loc, file_w):<{file_w}}  "
            f"{_clip(rule, rule_w):<{rule_w}}  {_clip(msg, msg_w)}".rstrip()
        )
    return out


def _tips(state: dict, active: list[dict], dismissed: list[dict]) -> list[str]:
    """At most two, and only when they apply — a tip printed on every run stops
    being read by the third one."""
    tips = []
    if F.counted(active):
        tips.append(
            'Tip: /triage-findings <filter> to act on these — or name IDs ("fix B1, M1").'
        )
    if state.get("run_id") and any(F.unverified(f) for f in active):
        tips.append(
            f"Tip: edit any agents/*.md, then re-run with --resume {state['run_id']} "
            "to skip unchanged agent calls."
        )
    if state.get("pr"):
        tips.append(
            "Tip: reviewing someone else's PR? Invoke the `pr-comment` skill to post "
            "these findings as a review."
        )
    if not dismissed:
        tips.append(
            "Tip: --dismiss <ids> suppresses a false-positive; it lifts by itself "
            "if the code is edited."
        )
    return tips[:2]


def terminal_report(p: F.Paths, state: dict, active, dismissed, summary: str) -> str:
    c = F.counts(active)
    v = state.get("verdict", "PASS")
    diff = state.get("diff") or {}
    head = f"Gate-WF Verdict: {v}"
    bits = [head]
    if diff:
        bits.append(f"{diff.get('files', 0)} files, +{diff.get('add', 0)}/-{diff.get('del', 0)}")
    if state.get("run_id"):
        bits.append(state["run_id"])
    lines = []
    if state.get("base_banner"):
        lines += [state["base_banner"], ""]
    lines.append(" · ".join(bits))

    if not active and not dismissed:
        lines.append(f"No findings. Report: {p.report}")
        return "\n".join(lines) + "\n"

    if summary:
        lines += ["", "En clair"]
        lines += ["  " + ln for ln in summary.strip().splitlines()]

    tally = " · ".join(f"{t} {c[t]}" for t in F.TIERS)
    if any(f.get("fixed") for f in active):
        tally += f" · {sum(1 for f in active if f.get('fixed'))} fixed"
    if dismissed:
        tally += f" · {len(dismissed)} dismissed"
    tally += (
        " — cannot merge until BLOCKER items are resolved."
        if v == "FAIL"
        else " — meets the merge bar; MAJOR and NIT are informational."
    )
    lines += ["", tally, ""]

    fixed = [f for f in active if f.get("fixed")]
    live = F.counted(active)
    if live:
        lines += _table(active)
        marks = {_mark(f) for f in live}
        legend = []
        if "!" in marks:
            legend.append("! context conflict")
        if "?" in marks:
            legend.append("? unverified")
        if legend:
            lines += ["", " · ".join(legend)]

    if fixed:
        lines += ["", "Fixed by triage (not counted): " + ", ".join(f["id"] for f in fixed)]
    lines += ["", f"Report: {p.report}"]
    lines += _tips(state, active, dismissed)
    return "\n".join(lines) + "\n"


# --- markdown report ---------------------------------------------------------


def _md_finding(f: dict) -> list[str]:
    k, n = F.refute_votes(f)
    badge = f"[refute votes: {k}/{n}]" if n else "[unverified]"
    extra = ""
    if f.get("also_flagged_by"):
        who = ", ".join(a.get("reviewer", "?") for a in f["also_flagged_by"])
        extra += f" (also: {who})"
    if f.get("context_verdict") == "UNCERTAIN":
        extra += " ❔ ambiguous historical context"
    elif f.get("context_verdict") == "CONFLICT":
        extra += " ⚠️ conflicts with past decision"

    out = [f"### {f['id']} — [{f.get('reviewer', '?')}] {f.get('rule_id', '?')}", ""]
    out.append(f"- `{f.get('file')}:{f.get('line')}` ({f.get('location', 'diff-line')}) {badge}{extra}")
    if f.get("citation"):
        out.append(f"  rule reference: {_one_line(f['citation'])}")
    out.append(f"  message: {_one_line(f.get('message'))}")
    if f.get("evidence"):
        out.append(f"  evidence: {_one_line(f['evidence'])}")
    if f.get("suggested_fix"):
        out.append(f"  fix: {_one_line(f['suggested_fix'])}")
    if f.get("context_citation") and f.get("context_verdict") in ("UNCERTAIN", "CONFLICT"):
        out.append(f"  context: {_one_line(f['context_citation'])}")
    out.append("")
    return out


def markdown_report(state: dict, active, dismissed) -> str:
    c = F.counts(active)
    diff = state.get("diff") or {}
    out = [f"# Gate-WF Verdict: {state.get('verdict', 'PASS')}", ""]
    if state.get("base_banner"):
        out += [state["base_banner"], ""]
    out += [
        f"Diff: {diff.get('files', 0)} files, +{diff.get('add', 0)}/-{diff.get('del', 0)}",
        f"Run: {state.get('run_id', '—')}",
        f"Generated: {state.get('cached_at', '—')}",
        "",
        f"BLOCKER: {c['BLOCKER']}  MAJOR: {c['MAJOR']}  NIT: {c['NIT']}",
        "",
    ]
    for tier in F.TIERS:
        group = [f for f in F.counted(active) if f.get("tier") == tier]
        if not group:
            continue
        out += [f"## {tier}", ""]
        for f in group:
            out += _md_finding(f)
    fixed = [f for f in active if f.get("fixed")]
    if fixed:
        out += ["## Fixed by triage (not counted toward the verdict)", ""]
        for f in fixed:
            out += [f"- `{f['id']}` {f.get('file')}:{f.get('line')} — "
                    f"{_one_line(f.get('message'))}"]
        out += [""]
    if dismissed:
        out += ["## Dismissed (suppressed — not counted toward the verdict)", ""]
        for f in dismissed:
            conf = f.get("confidence", "manual")
            label = "rebutted (thread still open)" if conf == "rebutted" else "resolved"
            src = "PR thread" if f.get("source") == "pr-thread" else "manual"
            out += [
                f"### {f['id']} — [{f.get('reviewer', '?')}] {f.get('rule_id', '?')}",
                "",
                f"- `{f.get('file')}:{f.get('line')}` · {label} · {src}",
                f"  was: {_one_line(f.get('message'))}",
            ]
            if f.get("citation"):
                out.append(f'  citation: "{_one_line(f["citation"])}"')
            out.append("")
    return "\n".join(out)


# --- commands ----------------------------------------------------------------


def _repartition(p: F.Paths, state: dict) -> tuple[list, list]:
    reg = F.load_registry(p)
    active, dismissed = F.partition(p.root, F.all_findings(state), reg)
    active, dismissed = F.assign_ids(active, dismissed)
    state["verdict"] = F.verdict(active)
    state["findings"] = active
    state["dismissed"] = dismissed
    F.save_state(p, state)
    return active, dismissed


def cmd_ingest(p: F.Paths, a) -> int:
    raw = json.loads(open(a.findings).read())
    items = raw.get("findings", raw) if isinstance(raw, dict) else raw

    # PR-thread dismissals the context-checker found this run enter the registry
    # before the partition, so they suppress in the same render.
    reg = F.load_registry(p)
    for f in items:
        # Ingest-time content identity — triage-findings compares against it to
        # drop findings whose code moved on since the gate ran.
        f["anchor0"] = F.anchor(p.root, f.get("rule_id", ""), f.get("file", ""), f.get("line"))
        if f.get("context_verdict") != "DISMISSED":
            continue
        anc = F.anchor(p.root, f.get("rule_id", ""), f.get("file", ""), f.get("line"))
        if not anc:
            continue
        F.upsert_dismissal(reg, {
            "anchor": anc,
            "rule_id": f.get("rule_id", ""),
            "file": f.get("file", ""),
            "anchor_text": _one_line(f.get("evidence"))[:200],
            "source": "pr-thread",
            "confidence": f.get("dismiss_confidence", "resolved"),
            "citation": _one_line(f.get("context_citation")),
            "dismissed_at": F.now_iso(),
        })
    F.save_registry(p, reg)

    state = {
        "cache_key": a.cache_key or "",
        "cached_at": F.now_iso(),
        "run_id": a.run_id or "",
        "pr": a.pr or "",
        "base_banner": a.base_banner or "",
        "diff": {"files": a.files, "add": a.add, "del": getattr(a, "del")},
        "findings": items,
        "dismissed": [],
    }
    active, dismissed = _repartition(p, state)
    print(f"ingested {len(active)} active, {len(dismissed)} dismissed → {state['verdict']}")
    return 0


def cmd_brief(p: F.Paths, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no prior gate-wf run on this branch — run the gate first", file=sys.stderr)
        return 1
    active, dismissed = _repartition(p, state)
    c = F.counts(active)
    diff = state.get("diff") or {}
    print(f"{state['verdict']} · {diff.get('files', 0)} files, "
          f"+{diff.get('add', 0)}/-{diff.get('del', 0)} · "
          + " ".join(f"{t}={c[t]}" for t in F.TIERS)
          + (f" dismissed={len(dismissed)}" if dismissed else ""))
    for f in active:
        print(f"{f['id']} {f.get('tier')} {f.get('rule_id')} "
              f"{f.get('file')}:{f.get('line')}")
        print(f"   {_one_line(f.get('message'))}")
    return 0


def cmd_show(p: F.Paths, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no prior gate-wf run on this branch — run the gate first", file=sys.stderr)
        return 1
    active, dismissed = _repartition(p, state)
    summary = ""
    if getattr(a, "summary_file", None) and os.path.exists(a.summary_file):
        summary = open(a.summary_file).read()
    p.dir.mkdir(parents=True, exist_ok=True)
    p.report.write_text(markdown_report(state, active, dismissed))
    sys.stdout.write(terminal_report(p, state, active, dismissed, summary))
    return 0


def cmd_dismiss(p: F.Paths, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no prior gate-wf run on this branch — run the gate first", file=sys.stderr)
        return 1
    reg = F.load_registry(p)
    ids = [i for i in a.ids.replace(",", " ").split() if i]
    hit = F.resolve(state, ids)
    missing = {i.upper() for i in ids} - {f["id"].upper() for f in hit}
    for f in hit:
        anc = F.anchor(p.root, f.get("rule_id", ""), f.get("file", ""), f.get("line"))
        if not anc:
            print(f"{f['id']}: line unreadable, cannot dismiss", file=sys.stderr)
            continue
        F.upsert_dismissal(reg, {
            "anchor": anc,
            "rule_id": f.get("rule_id", ""),
            "file": f.get("file", ""),
            "anchor_text": _one_line(f.get("evidence"))[:200],
            "source": "manual",
            "confidence": "manual",
            "citation": "manual dismissal",
            "dismissed_at": F.now_iso(),
        })
    F.save_registry(p, reg)
    if missing:
        print(f"unknown ids: {', '.join(sorted(missing))}", file=sys.stderr)
    return cmd_show(p, a)


def cmd_undismiss(p: F.Paths, a) -> int:
    state = F.load_state(p)
    if not state:
        print("no prior gate-wf run on this branch — run the gate first", file=sys.stderr)
        return 1
    reg = F.load_registry(p)
    for f in F.resolve(state, [i for i in a.ids.replace(",", " ").split() if i]):
        if f.get("anchor"):
            F.remove_dismissal(reg, f["anchor"])
    F.save_registry(p, reg)
    return cmd_show(p, a)


def cmd_show_dismissed(p: F.Paths, a) -> int:
    reg = F.load_registry(p)
    ds = reg.get("dismissals", [])
    if not ds:
        print("no dismissals on this branch")
        return 0
    for d in ds:
        print(f"{d.get('rule_id', '?'):<28} {d.get('file', '?')}")
        print(f"  {d.get('confidence', '?')} · {d.get('dismissed_at', '?')} · "
              f"{_one_line(d.get('citation'))[:120]}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="render.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest")
    ing.add_argument("--findings", required=True)
    ing.add_argument("--run-id", default="")
    ing.add_argument("--cache-key", default="")
    ing.add_argument("--pr", default="")
    ing.add_argument("--base-banner", default="")
    ing.add_argument("--files", type=int, default=0)
    ing.add_argument("--add", type=int, default=0)
    ing.add_argument("--del", type=int, default=0, dest="del")

    sub.add_parser("brief")

    sh = sub.add_parser("show")
    sh.add_argument("--summary-file", default="")

    for name in ("dismiss", "undismiss"):
        s = sub.add_parser(name)
        s.add_argument("ids")
        s.add_argument("--summary-file", default="")

    sub.add_parser("show-dismissed")

    a = ap.parse_args(argv)
    p = F.Paths()
    return {
        "ingest": cmd_ingest,
        "brief": cmd_brief,
        "show": cmd_show,
        "dismiss": cmd_dismiss,
        "undismiss": cmd_undismiss,
        "show-dismissed": cmd_show_dismissed,
    }[a.cmd](p, a)


if __name__ == "__main__":
    sys.exit(main())
