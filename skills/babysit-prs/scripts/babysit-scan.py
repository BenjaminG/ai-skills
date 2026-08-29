#!/usr/bin/env python3
"""Objective state of the author's open PRs — the only reader of GitHub truth for babysit-prs.

Usage: babysit-scan.py [PR...]        one pass, matrix JSON on stdout
       babysit-scan.py --watch [SECS] poll forever (default 60s), one line per transition
       babysit-scan.py --include-drafts  keep draft PRs in the scan
       babysit-scan.py --self-check   offline assertions on the diff logic

Named PR numbers are the selection: they are fetched as given, past the author and the
draft filter alike.

Owns the mechanical: PR discovery, one aliased GraphQL call for every PR, bot/human
ventilation of unresolved threads, the previous state on disk, the diff, and the emit
filter. Owns no judgment: never decides whether a thread deserves an action.
"""
import argparse
import json
import os
import subprocess
import time

POLL_DEFAULT = 60
# Same list as pr-feedback/scripts/fetch-pr.py — a machine account posting with a PAT
# reads as `User`, so __typename alone is not enough.
BOT_LOGINS = {"naboo-ai-reviews", "cursor", "coderabbitai", "sonarcloud"}
# Fields whose transition is an event. Anything else (a single check flipping, a new
# resolved thread) is churn: 22 checks per PR would emit 22 lines per push.
WATCHED = ("ci", "unresolved_bot", "unresolved_human", "merge_state", "head")

FRAGMENT = """
fragment S on PullRequest {
  number url title isDraft headRefName baseRefName mergeable mergeStateStatus
  reviewThreads(first: 100) {
    nodes { isResolved comments(first: 1) { nodes { author { __typename login } } } }
  }
  commits(last: 1) { nodes { commit { oid statusCheckRollup { state } } } }
}
"""


def gh(*args):
    p = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:400])
    return p.stdout


_REPO = []


def repo():
    """owner, name — asked once per process, not once per poll."""
    if not _REPO:
        owner, _, name = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip().partition("/")
        _REPO.extend((owner, name))
    return _REPO


def repo_slug():
    return "_".join(repo())


def state_dir():
    d = os.path.join(os.path.expanduser("~"), ".claude", "babysit-state", repo_slug())
    os.makedirs(d, exist_ok=True)
    return d


def is_bot(login, typename):
    return typename == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS


def open_prs(include_drafts=False):
    args = ["pr", "list", "--author", "@me", "--state", "open"]
    if not include_drafts:
        args.append("--draft=false")
    out = gh(*args, "--json", "number", "-q", ".[].number")
    return sorted(int(n) for n in out.split())


def fetch(numbers):
    """One aliased query for every PR. Returns {number: row}."""
    if not numbers:
        return {}
    aliases = "\n".join(f"  p{n}: pullRequest(number: {n}) {{ ...S }}" for n in numbers)
    query = f"query($o:String!,$r:String!){{\n repository(owner:$o,name:$r){{\n{aliases}\n }}\n}}\n{FRAGMENT}"
    owner, name = repo()
    raw = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"))
    return {p["number"]: row(p) for p in raw["data"]["repository"].values() if p}


def row(p):
    unresolved = [t for t in p["reviewThreads"]["nodes"] if not t["isResolved"]]
    openers = [t["comments"]["nodes"][0]["author"] for t in unresolved if t["comments"]["nodes"]]
    commit = (p["commits"]["nodes"] or [{}])[0].get("commit", {}) or {}
    rollup = commit.get("statusCheckRollup") or {}
    return {
        "number": p["number"],
        "url": p["url"],
        "title": p["title"],
        "draft": p["isDraft"],
        "branch": p["headRefName"],
        "base": p["baseRefName"],
        "merge_state": p["mergeStateStatus"],
        "mergeable": p["mergeable"],
        "ci": rollup.get("state") or "NONE",
        "head": (commit.get("oid") or "")[:7],
        "unresolved_bot": sum(1 for a in openers if is_bot(a["login"], a["__typename"])),
        "unresolved_human": sum(1 for a in openers if not is_bot(a["login"], a["__typename"])),
        "humans": sorted({a["login"] for a in openers if not is_bot(a["login"], a["__typename"])}),
    }


def needs_agent(r):
    """An agent is worth an Opus triage only if there is something only it can judge."""
    return r["unresolved_bot"] >= 1 or r["ci"] == "FAILURE"


def merge_ready(r):
    return r["merge_state"] == "CLEAN" and r["ci"] == "SUCCESS" and not r["unresolved_bot"] and not r["unresolved_human"]


def diff(old, new):
    """One line per PR whose watched fields moved. Pure — the self-check drives it."""
    lines = []
    for n, r in sorted(new.items()):
        prev = old.get(str(n)) or old.get(n)
        if not prev:
            lines.append(f"#{n} new: ci {r['ci']}, {r['merge_state']}, bot {r['unresolved_bot']}, human {r['unresolved_human']}")
            continue
        moved = [f"{f} {prev[f]}→{r[f]}" for f in WATCHED if prev.get(f) != r[f]]
        if moved:
            lines.append(f"#{n} " + ", ".join(moved))
    for n in sorted(set(int(k) for k in old) - set(new)):
        lines.append(f"#{n} gone (merged or closed)")
    return lines


def load_state(d):
    try:
        with open(os.path.join(d, "state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(d, prs, reports):
    blob = {str(n): dict(r, report=reports.get(str(n))) for n, r in prs.items()}
    tmp = os.path.join(d, "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(blob, f)
    os.replace(tmp, os.path.join(d, "state.json"))


def fold_reports(d, numbers):
    """An agent writes <pr>.report.json and stops. Reading it lifts that PR's mute."""
    out, lines = {}, []
    for n in numbers:
        path = os.path.join(d, f"{n}.report.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                rep = json.load(f)
        except ValueError:
            rep = {"blocked": "unreadable report file"}
        out[str(n)] = rep
        os.remove(path)
        mute = os.path.join(d, f"{n}.muted")
        if os.path.exists(mute):
            os.remove(mute)
        lines.append(
            f"#{n} report: pushed {rep.get('pushed', 0)}, inflight {rep.get('inflight', 0)}, "
            f"held {rep.get('held', 0)}, blocked {rep.get('blocked') or '-'}"
        )
    return out, lines


def muted(d, n):
    return os.path.exists(os.path.join(d, f"{n}.muted"))


def resolve_unknown(prs):
    """`mergeable` is computed lazily: UNKNOWN means "ask again", not a state change."""
    unknown = [n for n, r in prs.items() if r["mergeable"] == "UNKNOWN"]
    if not unknown:
        return prs
    time.sleep(3)
    for n, r in fetch(unknown).items():
        if r["mergeable"] != "UNKNOWN":
            prs[n] = r
    return prs


def scan(d, only=None, include_drafts=False):
    # Named numbers are the selection: fetching by number bypasses author and draft alike.
    prs = resolve_unknown(fetch(only or open_prs(include_drafts)))
    reports, report_lines = fold_reports(d, prs)
    return prs, reports, report_lines


def once(d, only=None, include_drafts=False):
    prs, reports, _ = scan(d, only, include_drafts)
    prev = load_state(d)
    carried = {k: (prev.get(k) or {}).get("report") for k in prev}
    carried.update(reports)
    save_state(d, prs, carried)
    print(json.dumps({
        "state_dir": d,
        "prs": [dict(r, report=carried.get(str(n)), needs_agent=needs_agent(r), merge_ready=merge_ready(r))
                for n, r in sorted(prs.items())],
    }, indent=2))


def watch(d, secs, only=None, include_drafts=False):
    while True:
        try:
            prs, reports, lines = scan(d, only, include_drafts)
            prev = load_state(d)
            visible = {n: r for n, r in prs.items() if not muted(d, n)}
            lines += diff({k: v for k, v in prev.items() if int(k) in visible}, visible)
            for n, r in sorted(prs.items()):
                if merge_ready(r):
                    lines.append(f"#{n} MERGE-READY — {r['url']}")
            carried = {k: (prev.get(k) or {}).get("report") for k in prev}
            carried.update(reports)
            save_state(d, prs, carried)
            for line in lines:
                print(line, flush=True)
        except Exception as e:  # a transient gh failure must not kill the watch
            print(f"scan error: {e}", flush=True)
        time.sleep(secs)


def self_check():
    a = {"number": 1, "ci": "SUCCESS", "unresolved_bot": 0, "unresolved_human": 0,
         "merge_state": "CLEAN", "head": "aaaaaaa", "mergeable": "MERGEABLE"}
    assert diff({"1": a}, {1: a}) == [], "no move, no event"
    assert diff({"1": a}, {1: dict(a, ci="FAILURE")}) == ["#1 ci SUCCESS→FAILURE"]
    two = diff({"1": a}, {1: dict(a, ci="PENDING", head="bbbbbbb")})
    assert two == ["#1 ci SUCCESS→PENDING, head aaaaaaa→bbbbbbb"], two
    # A push flips head + ci only: 2 fields, one line — not one line per check.
    assert len(two) == 1
    assert diff({}, {1: a})[0].startswith("#1 new:")
    assert diff({"1": a}, {}) == ["#1 gone (merged or closed)"]
    # Churn that must stay silent: a thread gets resolved, counts unchanged.
    assert diff({"1": a}, {1: dict(a, mergeable="UNKNOWN")}) == [], "mergeable is not watched"
    assert needs_agent(dict(a, unresolved_bot=1)) and needs_agent(dict(a, ci="FAILURE"))
    assert not needs_agent(a), "green PR with no bot thread needs no agent"
    assert not needs_agent(dict(a, unresolved_human=2)), "human threads are yours, not an agent's"
    assert merge_ready(a) and not merge_ready(dict(a, unresolved_human=1))
    # A draft carries mergeStateStatus DRAFT, so it can never leave the matrix on its own.
    assert not merge_ready(dict(a, merge_state="DRAFT"))
    assert is_bot("cursor", "User") and is_bot("x[bot]", "User") and not is_bot("viclafouch", "User")

    # Report on disk survives a dead agent, and reading it lifts that PR's mute.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "42.muted"), "w").close()
        with open(os.path.join(d, "42.report.json"), "w") as f:
            json.dump({"pushed": 2, "inflight": 0, "held": 3, "blocked": None}, f)
        assert muted(d, 42)
        reports, lines = fold_reports(d, [42, 43])
        assert reports["42"]["held"] == 3
        assert lines == ["#42 report: pushed 2, inflight 0, held 3, blocked -"], lines
        assert not muted(d, 42), "folding the report must lift the mute"
        assert fold_reports(d, [42]) == ({}, []), "a folded report is consumed once"
    ns = parser().parse_args(["123", "456", "--include-drafts", "--watch", "60"])
    assert (ns.prs, ns.watch, ns.include_drafts) == ([123, 456], 60, True), ns
    assert parser().parse_args([]).prs == [] and parser().parse_args([]).watch is None
    assert parser().parse_args(["--watch"]).watch == POLL_DEFAULT, "bare --watch keeps the default"
    print("self-check ok")


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prs", nargs="*", type=int, help="PR numbers to scan; default is every open PR")
    ap.add_argument("--watch", nargs="?", const=POLL_DEFAULT, type=int, metavar="SECS")
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    return ap


if __name__ == "__main__":
    ns = parser().parse_args()
    if ns.self_check:
        self_check()
    elif ns.watch is not None:
        watch(state_dir(), ns.watch, ns.prs, ns.include_drafts)
    else:
        once(state_dir(), ns.prs, ns.include_drafts)
