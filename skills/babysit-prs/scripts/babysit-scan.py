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
WATCHED = ("ci", "unresolved_bot", "unresolved_human", "held", "merge_state", "head")

FRAGMENT = """
fragment S on PullRequest {
  number url title isDraft headRefName baseRefName mergeable mergeStateStatus
  reviewThreads(first: 100) {
    nodes {
      id isResolved
      comments(first: 1) { nodes { author { __typename login } } }
      last: comments(last: 1) { nodes { id author { login } } }
    }
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


_ME = []


def me():
    """The authenticated login — a bot thread whose last word is ours is held, not unanswered."""
    if not _ME:
        _ME.append(gh("api", "user", "-q", ".login").strip())
    return _ME[0]


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


def fetch_raw(numbers):
    """One aliased query for every PR. Returns {number: payload}."""
    if not numbers:
        return {}
    aliases = "\n".join(f"  p{n}: pullRequest(number: {n}) {{ ...S }}" for n in numbers)
    query = f"query($o:String!,$r:String!){{\n repository(owner:$o,name:$r){{\n{aliases}\n }}\n}}\n{FRAGMENT}"
    owner, name = repo()
    raw = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"))
    return {p["number"]: p for p in raw["data"]["repository"].values() if p}


def thread_ids(p):
    """{thread id: id of its last comment} — the snapshot an agent's report certifies as seen."""
    out = {}
    for t in p["reviewThreads"]["nodes"]:
        last = t["last"]["nodes"]
        if not t["isResolved"] and last:
            out[t["id"]] = last[-1]["id"]
    return out


def row(p, seen):
    unresolved = [t for t in p["reviewThreads"]["nodes"] if not t["isResolved"]]
    bot, human, held = ventilate(unresolved, me(), seen)
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
        "unresolved_bot": len(bot),
        "unresolved_human": len(human),
        "held": len(held),
        "humans": sorted({a["login"] for a in human}),
    }


def ventilate(unresolved, mine, seen):
    """Split open threads three ways: bot (an agent's), human (the author's), held.

    A bot thread is work only while it has *moved since an agent last looked at it*. Two things
    say it has not: our own reply sitting last (the agent adjudicated and left the decision to
    the author), or a last comment `seen` already records (the agent read that very comment and
    chose to leave it). Both stay open — that is the point, a resolved thread is one the author
    cannot find — so neither counts as `unresolved_bot`.

    Without `seen`, a bot that answers its own thread ("justification accepted") reopens the
    work forever: every pass spawns an agent that re-adjudicates the head of the thread. With
    it, an acknowledgement costs one pass and a genuine rebuttal still gets its agent, because
    a rebuttal is a comment id nobody has seen.
    """
    bot, human, held = [], [], []
    for t in unresolved:
        first = t["comments"]["nodes"]
        if not first:
            continue
        author = first[0]["author"]
        if not is_bot(author["login"], author["__typename"]):
            human.append(author)
            continue
        last = t["last"]["nodes"]
        settled = last and (last[-1]["author"]["login"] == mine
                            or seen.get(t["id"]) == last[-1]["id"])
        (held if settled else bot).append(author)
    return bot, human, held


def link_stack(prs):
    """A PR whose base is another open PR's head sits on top of it. Pure join, no API call."""
    by_head = {r["branch"]: n for n, r in prs.items()}
    for r in prs.values():
        r["parent"] = by_head.get(r["base"])
    return prs


def stacks(prs):
    """{pr: [every PR of its stack, lowest first]} — a stack is a chain of parent links."""
    def chain(n):
        c, walked = [n], {n}
        p = prs[n].get("parent")
        while p in prs and p not in walked:
            c.append(p)
            walked.add(p)
            p = prs[p].get("parent")
        return c                       # [self, parent, …, root]

    groups = {}
    for n in prs:
        groups.setdefault(chain(n)[-1], []).append(n)
    order = {}
    for members in groups.values():
        members.sort(key=lambda n: len(chain(n)))
        for n in members:
            order[n] = members
    return order


def waits_on(r, prs, order, running):
    """One agent per stack at a time, and always the lowest PR that needs one.

    A parent's force-push moves the child's base under it, so a restack against a base still
    being rewritten is thrown away — or lands and buries the parent's fix. `running` is the set
    of PRs whose agent is still alive (its mute file). It has to be consulted first: an agent
    that already answered its threads but has not pushed yet leaves `needs_agent` false while
    still owning the branch, and judging by `needs_agent` alone would release the child straight
    into the rebase.
    """
    members = order[r["number"]]
    own = next((n for n in members if n in running), None)
    if own is None:
        own = next((n for n in members if needs_agent(prs[n])), None)
    return own if own is not None and own != r["number"] else None


def needs_agent(r):
    """An agent is worth an Opus triage only if there is something only it can judge.

    A conflicting branch counts: it blocks the merge, no thread and no check reports it, and on a
    draft `mergeStateStatus` says DRAFT — `mergeable` is the only field that still says CONFLICTING.
    """
    return r["unresolved_bot"] >= 1 or r["ci"] == "FAILURE" or r["mergeable"] == "CONFLICTING"


def merge_ready(r):
    return (r["merge_state"] == "CLEAN" and r["ci"] == "SUCCESS"
            and not r["unresolved_bot"] and not r["unresolved_human"] and not r["held"])


def status(r, prs, order, running):
    """Can it merge, in one word — the Status column. First rung that holds wins."""
    if needs_agent(r):
        # bot threads, red CI or a conflict — an agent owns it, unless another PR of its stack
        # holds the single agent that stack gets. A PR with nothing to fix never says `waits`:
        # a green root behind a busy child is still mergeable, and hiding it would be a lie.
        return "waits" if waits_on(r, prs, order, running) is not None else "working"
    if r["held"]:
        return "your-call"  # adjudicated, open, waiting on a decision only the author makes
    if merge_ready(r):
        return "ready"
    if r["ci"] == "PENDING":
        return "ci"
    if r.get("draft"):
        return "draft"
    return "review"         # green and quiet: waiting on a human approval or a base bump


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


def save_state(d, prs, reports, seen):
    blob = {str(n): dict(r, report=reports.get(str(n)), seen=seen.get(n, {}))
            for n, r in prs.items()}
    tmp = os.path.join(d, "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(blob, f)
    os.replace(tmp, os.path.join(d, "state.json"))


def fold_reports(d):
    """An agent writes <pr>.report.json and stops. Reading it lifts that PR's mute."""
    out, lines = {}, []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".report.json"):
            continue
        n = name[: -len(".report.json")]
        path = os.path.join(d, name)
        try:
            with open(path) as f:
                rep = json.load(f)
        except ValueError:
            rep = {"blocked": "unreadable report file"}
        out[n] = rep
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


def resolve_unknown(prs, seen):
    """`mergeable` is computed lazily: UNKNOWN means "ask again", not a state change."""
    unknown = [n for n, r in prs.items() if r["mergeable"] == "UNKNOWN"]
    if not unknown:
        return prs
    time.sleep(3)
    for n, p in fetch_raw(unknown).items():
        r = row(p, seen.get(n, {}))
        if r["mergeable"] != "UNKNOWN":
            prs[n] = r
    return prs


def scan(d, only=None, include_drafts=False):
    prev = load_state(d)
    seen = {int(k): dict(v.get("seen") or {}) for k, v in prev.items()}
    # Fold before ventilating: an agent's report certifies everything still open on that PR as
    # deliberately left open, and the row that comes out of this pass has to reflect that — or
    # the manager reads a stale `unresolved_bot` and respawns the agent that just finished.
    reports, report_lines = fold_reports(d)
    # Named numbers are the selection: fetching by number bypasses author and draft alike.
    raw = fetch_raw(only or open_prs(include_drafts))
    for k in reports:
        n = int(k)
        if n in raw:
            seen[n] = thread_ids(raw[n])
    prs = link_stack(resolve_unknown(
        {n: row(p, seen.get(n, {})) for n, p in raw.items()}, seen))
    return prs, reports, report_lines, seen, prev


def carry(prev, reports):
    out = {k: (prev.get(k) or {}).get("report") for k in prev}
    out.update(reports)
    return out


def once(d, only=None, include_drafts=False):
    prs, reports, _, seen, prev = scan(d, only, include_drafts)
    carried = carry(prev, reports)
    order, running = stacks(prs), {n for n in prs if muted(d, n)}
    save_state(d, prs, carried, seen)
    print(json.dumps({
        "state_dir": d,
        "prs": [dict(r, report=carried.get(str(n)), needs_agent=needs_agent(r),
                     agent_running=n in running,
                     waits_on=waits_on(r, prs, order, running), merge_ready=merge_ready(r),
                     status=status(r, prs, order, running))
                for n, r in sorted(prs.items())],
    }, indent=2))


def watch(d, secs, only=None, include_drafts=False):
    while True:
        try:
            prs, reports, lines, seen, prev = scan(d, only, include_drafts)
            visible = {n: r for n, r in prs.items() if not muted(d, n)}
            lines += diff({k: v for k, v in prev.items() if int(k) in visible}, visible)
            for n, r in sorted(prs.items()):
                if merge_ready(r):
                    lines.append(f"#{n} MERGE-READY — {r['url']}")
            save_state(d, prs, carry(prev, reports), seen)
            for line in lines:
                print(line, flush=True)
        except Exception as e:  # a transient gh failure must not kill the watch
            print(f"scan error: {e}", flush=True)
        time.sleep(secs)


def self_check():
    a = {"number": 1, "ci": "SUCCESS", "unresolved_bot": 0, "unresolved_human": 0,
         "held": 0, "merge_state": "CLEAN", "head": "aaaaaaa", "mergeable": "MERGEABLE"}
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
    assert needs_agent(dict(a, mergeable="CONFLICTING", merge_state="DRAFT")), \
        "a conflicting branch blocks the merge even when mergeStateStatus only says DRAFT"
    assert not needs_agent(dict(a, unresolved_human=2)), "human threads are yours, not an agent's"
    assert merge_ready(a) and not merge_ready(dict(a, unresolved_human=1))
    # A held thread spawns no agent — and lets nothing merge either.
    assert not needs_agent(dict(a, held=2)), "a held thread waits on the author, not on an agent"
    assert not merge_ready(dict(a, held=1)), "a decision still owed is not merge-ready"

    # Ventilation: opener decides bot vs human, our own last word decides held.
    def th(opener, typename="Bot", last=None, tid="T", cid="c1"):
        return {"id": tid, "isResolved": False,
                "comments": {"nodes": [{"author": {"login": opener, "__typename": typename}}]},
                "last": {"nodes": [{"id": cid, "author": {"login": last or opener}}]}}
    bot, human, held = ventilate(
        [th("cursor", "User"), th("cursor", "User", last="bgelis"),
         th("viclafouch", "User"), th("viclafouch", "User", last="bgelis")], "bgelis", {})
    assert (len(bot), len(human), len(held)) == (1, 2, 1), (bot, human, held)
    assert held[0]["login"] == "cursor", "a human thread we answered stays the author's, never held"
    assert ventilate([{"id": "T", "isResolved": False, "comments": {"nodes": []},
                       "last": {"nodes": []}}], "bgelis", {}) == ([], [], [])

    # The bot answers its own thread. Unseen, that is work; once an agent's report has recorded
    # that very comment, it is settled — and a *newer* bot comment is work again.
    ack = [th("cursor", "User", last="cursor", tid="T9", cid="ack")]
    assert len(ventilate(ack, "bgelis", {})[0]) == 1, "an unseen bot reply is work"
    assert len(ventilate(ack, "bgelis", {"T9": "ack"})[2]) == 1, \
        "an agent read this exact comment and left the thread open: settled, no new agent"
    assert len(ventilate(ack, "bgelis", {"T9": "older"})[0]) == 1, \
        "a bot rebuttal posted after the agent looked is a comment id nobody has seen: work again"
    assert thread_ids({"reviewThreads": {"nodes": [
        th("cursor", "User", tid="T9", cid="ack"),
        dict(th("cursor", "User", tid="T8", cid="x"), isResolved=True)]}}) == {"T9": "ack"}, \
        "a resolved thread needs no memory"
    # A draft carries mergeStateStatus DRAFT, so it can never leave the matrix on its own.
    assert not merge_ready(dict(a, merge_state="DRAFT"))
    # A stack: each PR based on the one below it. The join is pure — no API call.
    st = link_stack({1: dict(a, number=1, branch="feat-a", base="main"),
                     2: dict(a, number=2, branch="feat-b", base="feat-a"),
                     3: dict(a, number=3, branch="feat-c", base="feat-b", unresolved_bot=1)})
    assert st[1]["parent"] is None and st[2]["parent"] == 1 and st[3]["parent"] == 2
    o = stacks(st)
    assert o[1] == o[2] == o[3] == [1, 2, 3], o[3]
    assert waits_on(st[3], st, o, set()) is None, "a green stack below blocks nobody"
    st[2]["unresolved_bot"] = 1
    assert waits_on(st[3], st, o, set()) == 2, "a PR lower in the stack needs an agent: wait"
    assert waits_on(st[2], st, o, set()) is None, "the lowest PR that needs an agent always runs"
    assert status(st[3], st, o, set()) == "waits" and status(st[2], st, o, set()) == "working"
    # One agent per stack, transitively: the grandparent owns it even through a clean parent.
    st[2]["unresolved_bot"] = 0
    st[1]["ci"] = "FAILURE"
    assert waits_on(st[3], st, o, set()) == 1, "a busy grandparent still owns the stack"
    st[1]["ci"] = "SUCCESS"
    # A live agent owns the stack even once its threads are clean: it has not force-pushed yet.
    assert waits_on(st[3], st, o, {1}) == 1, "a mute means an agent is still rewriting #1"
    assert waits_on(st[1], st, o, {3}) == 3, "and it holds in the other direction too"
    assert status(st[1], st, o, {3}) == "ready", \
        "a green root behind a busy child is still mergeable — it never says waits"
    # Two PRs stacked on the same parent: one group, still one agent.
    br = link_stack({1: dict(a, number=1, branch="feat-a", base="main", ci="FAILURE"),
                     2: dict(a, number=2, branch="feat-b", base="feat-a"),
                     3: dict(a, number=3, branch="feat-c", base="feat-a")})
    ob = stacks(br)
    assert ob[2] == ob[3] and ob[2][0] == 1
    assert waits_on(br[2], br, ob, set()) == 1 and waits_on(br[3], br, ob, set()) == 1
    solo = link_stack({1: dict(a, number=1, branch="feat-a", base="main")})
    os_, none = stacks(solo), set()
    def st1(**kw):
        return status(dict(solo[1], **kw), solo, os_, none)
    assert st1() == "ready"
    assert st1(held=1) == "your-call"
    assert st1(unresolved_bot=1, held=1) == "working", \
        "an agent still has work: the author is not on the hook yet"
    assert st1(ci="PENDING", merge_state="BLOCKED") == "ci"
    assert st1(unresolved_human=1, merge_state="BLOCKED") == "review"
    assert st1(draft=True, merge_state="DRAFT") == "draft"
    assert is_bot("cursor", "User") and is_bot("x[bot]", "User") and not is_bot("viclafouch", "User")

    # Report on disk survives a dead agent, and reading it lifts that PR's mute.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "42.muted"), "w").close()
        with open(os.path.join(d, "42.report.json"), "w") as f:
            json.dump({"pushed": 2, "inflight": 0, "held": 3, "blocked": None}, f)
        assert muted(d, 42)
        reports, lines = fold_reports(d)
        assert reports["42"]["held"] == 3
        assert lines == ["#42 report: pushed 2, inflight 0, held 3, blocked -"], lines
        assert not muted(d, 42), "folding the report must lift the mute"
        assert fold_reports(d) == ({}, []), "a folded report is consumed once"
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
