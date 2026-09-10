"""Shared state access for gate-wf and triage-findings.

Owns everything deterministic about a finding set: where the state lives, the
content-anchor identity used by the dismissal registry, the active/dismissed
partition, verdict math, and stable ID assignment.

`render.py` (gate-wf) and the triage-findings skill both import this — the
anchor computation in particular must have exactly one implementation, since a
drift between them would silently resurrect dismissed findings.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TIERS = ("BLOCKER", "MAJOR", "NIT")
TIER_PREFIX = {"BLOCKER": "B", "MAJOR": "M", "NIT": "N"}


# --- locations ---------------------------------------------------------------


def _git(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def repo_root() -> Path:
    return Path(_git("rev-parse", "--show-toplevel"))


def branch(root: Path) -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD", cwd=str(root))


def state_dir(root: Path) -> Path:
    # Mirrors SKILL.md Step 1b: shasum of the repo root, first 12 chars.
    slug = hashlib.sha1(str(root).encode()).hexdigest()[:12]
    return Path.home() / ".claude" / "gate-wf-state" / slug


class Paths:
    def __init__(self, root: Path | None = None):
        self.root = root or repo_root()
        self.branch = branch(self.root)
        safe = self.branch.replace("/", "_")
        d = state_dir(self.root)
        self.dir = d
        self.state = d / f"{safe}.json"
        self.dismissed = d / f"{safe}.dismissed.json"
        self.report = d / f"{safe}.report.md"


# --- state + registry io -----------------------------------------------------


def load_state(p: Paths) -> dict:
    if not p.state.exists():
        return {}
    return json.loads(p.state.read_text())


def save_state(p: Paths, state: dict) -> None:
    p.dir.mkdir(parents=True, exist_ok=True)
    p.state.write_text(json.dumps(state, indent=2) + "\n")


def load_registry(p: Paths) -> dict:
    if not p.dismissed.exists():
        return {"version": 1, "dismissals": []}
    return json.loads(p.dismissed.read_text())


def save_registry(p: Paths, reg: dict) -> None:
    p.dir.mkdir(parents=True, exist_ok=True)
    p.dismissed.write_text(json.dumps(reg, indent=2) + "\n")


def upsert_dismissal(reg: dict, entry: dict) -> dict:
    reg["dismissals"] = [
        d for d in reg.get("dismissals", []) if d.get("anchor") != entry["anchor"]
    ] + [entry]
    return reg


def remove_dismissal(reg: dict, anchor: str) -> dict:
    reg["dismissals"] = [
        d for d in reg.get("dismissals", []) if d.get("anchor") != anchor
    ]
    return reg


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- content anchor ----------------------------------------------------------


def anchor(root: Path, rule_id: str, file: str, line) -> str | None:
    """Content identity of a finding: sha(rule_id::file::normalized line at HEAD).

    Byte-compatible with the bash `gatewf_anchor` it replaces, so registries
    written by earlier versions keep matching. None when the line is unreadable
    (file or line gone) — such a finding stays active by design.
    """
    try:
        n = int(line)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    try:
        with open(root / file, "r", errors="replace") as fh:
            for i, raw in enumerate(fh, 1):
                if i == n:
                    txt = " ".join(raw.split())
                    if not txt:
                        return None
                    key = f"{rule_id}::{file}::{txt}"
                    return hashlib.sha1(key.encode()).hexdigest()[:12]
    except OSError:
        return None
    return None


# --- partition, verdict, ids -------------------------------------------------


def all_findings(state: dict) -> list[dict]:
    """Every finding the last run knew about, ids dropped for re-partition."""
    out = []
    for f in list(state.get("findings", [])) + list(state.get("dismissed", [])):
        f = dict(f)
        f.pop("id", None)
        out.append(f)
    return out


def partition(root: Path, findings: list[dict], reg: dict) -> tuple[list, list]:
    by_anchor = {d["anchor"]: d for d in reg.get("dismissals", []) if d.get("anchor")}
    active, dismissed = [], []
    for f in findings:
        a = anchor(root, f.get("rule_id", ""), f.get("file", ""), f.get("line"))
        entry = by_anchor.get(a) if a else None
        if entry:
            f = dict(f)
            f["anchor"] = a
            f["source"] = entry.get("source", "manual")
            f["confidence"] = entry.get("confidence", "manual")
            f["citation"] = entry.get("citation", f.get("citation", ""))
            dismissed.append(f)
        else:
            active.append(f)
    return active, dismissed


def counted(active: list[dict]) -> list[dict]:
    """Findings that still weigh on the verdict. A finding triage-findings has
    fixed stays in the state file — the run's record of what was done — but
    stops counting, the same way a dismissed one does."""
    return [f for f in active if not f.get("fixed")]


def counts(active: list[dict]) -> dict:
    live = counted(active)
    return {t: sum(1 for f in live if f.get("tier") == t) for t in TIERS}


def verdict(active: list[dict]) -> str:
    c = counts(active)
    if c["BLOCKER"]:
        return "FAIL"
    if c["MAJOR"] or c["NIT"]:
        return "PASS WITH NOTES"
    return "PASS"


def _sort_key(f: dict):
    tier = f.get("tier", "NIT")
    order = TIERS.index(tier) if tier in TIERS else len(TIERS)
    try:
        line = int(f.get("line") or 0)
    except (TypeError, ValueError):
        line = 0
    return (order, f.get("file", ""), line, f.get("rule_id", ""))


def assign_ids(active: list[dict], dismissed: list[dict]) -> tuple[list, list]:
    """Sort by tier → file → line and number in place. Deterministic, so a
    re-render of an unchanged finding set produces the same IDs."""
    active = sorted(active, key=_sort_key)
    dismissed = sorted(dismissed, key=_sort_key)
    seq = {t: 0 for t in TIERS}
    for f in active:
        tier = f.get("tier") if f.get("tier") in TIERS else "NIT"
        seq[tier] += 1
        f["id"] = f"{TIER_PREFIX[tier]}{seq[tier]}"
    for i, f in enumerate(dismissed, 1):
        f["id"] = f"D{i}"
    return active, dismissed


def mark_fixed(state: dict, ids) -> list[dict]:
    """Flag findings as fixed by id. Returns the ones actually flagged."""
    want = {str(i).strip().upper() for i in ids if str(i).strip()}
    hit = []
    for f in state.get("findings", []):
        if str(f.get("id", "")).upper() in want:
            f["fixed"] = True
            hit.append(f)
    return hit


def stale(root: Path, f: dict) -> bool:
    """True when the flagged line has changed since the gate ran.

    `anchor0` is stamped at ingest. A finding whose line was already unreadable
    then carries no anchor0 and is treated as fresh — unknowable is not the same
    as obsolete, and dropping it silently is the one failure that would make
    triage propose work that no longer exists.
    """
    base = f.get("anchor0")
    if not base:
        return False
    return anchor(root, f.get("rule_id", ""), f.get("file", ""), f.get("line")) != base


def refute_votes(f: dict) -> tuple[int, int]:
    v = f.get("verifications") or []
    return sum(1 for x in v if x.get("refuted")), len(v)


def unverified(f: dict) -> bool:
    return not (f.get("verifications") or [])


def resolve(state: dict, ids) -> list[dict]:
    """Look up findings by rendered id (B1, D2, …) across active and dismissed."""
    want = {i.strip().upper() for i in ids if i.strip()}
    pool = list(state.get("findings", [])) + list(state.get("dismissed", []))
    return [f for f in pool if str(f.get("id", "")).upper() in want]


# --- selection (used by triage-findings) -------------------------------------

CLEANUP_PREFIXES = ("slop-", "simplify-", "ponytail-")
BUG_PREFIXES = ("bug-", "security-")

SHORTCUTS = {
    "blockers": lambda f: f.get("tier") == "BLOCKER",
    "majors": lambda f: f.get("tier") == "MAJOR",
    "nits": lambda f: f.get("tier") == "NIT",
    "all": lambda f: True,
    "cleanup": lambda f: str(f.get("rule_id", "")).startswith(CLEANUP_PREFIXES),
    "bugs": lambda f: str(f.get("rule_id", "")).startswith(BUG_PREFIXES),
}


def select(findings: list[dict], token: str | None) -> list[dict] | None:
    """Resolve a literal selector to a finding subset.

    None when the token is not a literal one — the caller (triage) hands the
    phrase to a model instead. No token at all means BLOCKER + MAJOR.
    """
    if not token or not token.strip():
        return [f for f in findings if f.get("tier") in ("BLOCKER", "MAJOR")]
    tok = token.strip()
    low = tok.lower()
    if low in SHORTCUTS:
        return [f for f in findings if SHORTCUTS[low](f)]
    ids = [t for t in tok.replace(",", " ").split() if t]
    if ids and all(
        i[0].upper() in "BMND" and i[1:].isdigit() for i in ids if len(i) > 1
    ):
        want = {i.upper() for i in ids}
        return [f for f in findings if str(f.get("id", "")).upper() in want]
    if "/" in tok or "." in tok:
        return [
            f
            for f in findings
            if tok in f.get("file", "") or os.path.basename(f.get("file", "")) == tok
        ]
    return None
