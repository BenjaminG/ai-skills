#!/usr/bin/env python3
"""Objective state of the author's open PRs — the one reader of GitHub truth, for pr-dash and
babysit-prs alike.

Usage: pr-scan.py [PR...] [--include-drafts]           a fresh pass, matrix JSON on stdout
       pr-scan.py --follow [PR...] [--include-drafts]  that selection's event lines, forever
       pr-scan.py --watch [SECS] [--repo OWNER/NAME]   the service itself (poll, default 60s)
       pr-scan.py --self-check                         offline assertions

One service per repo writes ~/.claude/pr-state/<owner_repo>/state.json: every open PR of the
author, drafts included, plus any PR a babysit selection names. Whoever needs it first starts it
(`ensure`); nobody runs it by hand. It passes every SECS seconds or on SIGUSR1, appends one line
per transition to events.log, and exits once no reader has touched reader.heartbeat for
READER_TTL. Readers filter on their side: the dashboard hides drafts, babysit-prs keeps its own
selection.

Named PR numbers are the selection: they are fetched as given, past the author and the
draft filter alike.

Owns the mechanical: PR discovery, aliased GraphQL pagination, bot/human ventilation
of threads, the previous state on disk, the diff, and the emit filter. Owns no judgment:
never decides whether a thread deserves an action.
"""
import argparse
import fcntl
import json
import os
import re
import select
import signal
import subprocess
import sys
import time

POLL_DEFAULT = 60
MUTE_TTL = 3600
READER_TTL = 1800
PASS_WAIT = 10
EVENTS_MAX = 1 << 20
SCRIPT = os.path.realpath(__file__)
STATE_SCHEMA_VERSION = 3
# Same list as pr-feedback/scripts/fetch-pr.py — a machine account posting with a PAT
# reads as `User`, so __typename alone is not enough.
BOT_LOGINS = {"naboo-ai-reviews", "cursor", "coderabbitai", "sonarcloud"}
# Fields whose transition is an event. Anything else (a single check flipping, a new
# resolved thread) is churn: 22 checks per PR would emit 22 lines per push.
WATCHED = ("ci", "unresolved_bot", "unresolved_human", "held", "merge_state", "head")

THREAD_FIELDS = """
nodes {
  id isResolved
  comments(first: 1) { nodes { author { __typename login } } }
  last: comments(last: 1) { nodes { id author { login } } }
}
pageInfo { hasNextPage endCursor }
"""

FRAGMENT = """
fragment S on PullRequest {
  number url title state isDraft headRefName baseRefName mergeable mergeStateStatus
  author { login }
  additions deletions changedFiles
  stackEntry { position stack { number } }
  reviewThreads(first: 100) {
""" + THREAD_FIELDS + """
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


def repo(slug=None):
    """owner, name — asked once per process, not once per poll. Every reader resolves it here,
    so the dashboard and the service can never land on two different repos. `slug` pins it:
    the service is handed its repo, because the worktree it was started from can disappear."""
    if not _REPO:
        slug = slug or gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
        owner, _, name = slug.partition("/")
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
    home = os.path.join(os.path.expanduser("~"), ".claude")
    d = os.path.join(home, "pr-state", repo_slug())
    legacy = os.path.join(home, "babysit-state", repo_slug())
    if not os.path.exists(d) and os.path.isdir(legacy):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        try:
            os.rename(legacy, d)  # mutes, reports and seen comment ids come along
        except OSError:
            pass                  # another reader migrated it first
    os.makedirs(d, exist_ok=True)
    return d


def is_bot(login, typename):
    return typename == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS


def open_prs():
    """Every open PR of the author, drafts included: filtering is each reader's business."""
    out = gh("pr", "list", "-R", "/".join(repo()), "--author", "@me", "--state", "open",
             "--json", "number", "-q", ".[].number")
    return sorted(int(n) for n in out.split())


def fetch_raw(numbers):
    """One initial aliased query, then aliased pages only for PRs above 100 threads."""
    if not numbers:
        return {}
    aliases = "\n".join(f"  p{n}: pullRequest(number: {n}) {{ ...S }}" for n in numbers)
    query = f"query($o:String!,$r:String!){{\n repository(owner:$o,name:$r){{\n{aliases}\n }}\n}}\n{FRAGMENT}"
    owner, name = repo()
    raw = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"))
    prs = {p["number"]: p for p in raw["data"]["repository"].values() if p}
    return fetch_remaining_threads(prs, owner, name)


def fetch_remaining_threads(prs, owner, name):
    pending = {n: p["reviewThreads"]["pageInfo"]["endCursor"] for n, p in prs.items()
               if p["reviewThreads"]["pageInfo"]["hasNextPage"]}
    while pending:
        aliases = "\n".join(
            f"  p{n}: pullRequest(number: {n}) {{ reviewThreads(first: 100, after: {json.dumps(cursor)}) {{ {THREAD_FIELDS} }} }}"
            for n, cursor in pending.items())
        query = f"query($o:String!,$r:String!){{\n repository(owner:$o,name:$r){{\n{aliases}\n }}\n}}"
        raw = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"))["data"]["repository"]
        following = {}
        for n in pending:
            page = raw[f"p{n}"]["reviewThreads"]
            prs[n]["reviewThreads"]["nodes"].extend(page["nodes"])
            prs[n]["reviewThreads"]["pageInfo"] = page["pageInfo"]
            if page["pageInfo"]["hasNextPage"]:
                following[n] = page["pageInfo"]["endCursor"]
        pending = following
    return prs


def thread_ids(p):
    """{thread id: id of its last comment} — the snapshot an agent's report certifies as seen."""
    out = {}
    for t in p["reviewThreads"]["nodes"]:
        last = t["last"]["nodes"]
        if not t["isResolved"] and last:
            out[t["id"]] = last[-1]["id"]
    return out


def row(p, seen):
    threads = p["reviewThreads"]["nodes"]
    unresolved = [t for t in threads if not t["isResolved"]]
    bot, human, held = ventilate(unresolved, me(), seen)
    counts = thread_counts(threads)
    commit = (p["commits"]["nodes"] or [{}])[0].get("commit", {}) or {}
    rollup = commit.get("statusCheckRollup") or {}
    return {
        "number": p["number"],
        "url": p["url"],
        "title": p["title"],
        "author": (p.get("author") or {}).get("login"),
        "draft": p["isDraft"],
        "branch": p["headRefName"],
        "base": p["baseRefName"],
        "merge_state": p["mergeStateStatus"],
        # GitHub's own stack, when the PR belongs to one: the split `gh stack` drew, which the
        # base chain cannot show — one stack based on another's head reads as a single chain.
        "stack": ((p.get("stackEntry") or {}).get("stack") or {}).get("number"),
        "stack_pos": (p.get("stackEntry") or {}).get("position"),
        "mergeable": p["mergeable"],
        "ci": rollup.get("state") or "NONE",
        "head": (commit.get("oid") or "")[:7],
        "additions": p["additions"],
        "deletions": p["deletions"],
        "files": p["changedFiles"],
        "unresolved_bot": len(bot),
        "unresolved_human": len(human),
        "held": len(held),
        "humans": sorted({a["login"] for a in human}),
        **counts,
    }


def thread_counts(threads):
    counts = {"threads_bot_open": 0, "threads_bot_closed": 0,
              "threads_human_open": 0, "threads_human_closed": 0}
    for t in threads:
        first = t["comments"]["nodes"]
        if not first:
            continue
        author = first[0]["author"]
        kind = "bot" if is_bot(author["login"], author["__typename"]) else "human"
        state = "closed" if t["isResolved"] else "open"
        counts[f"threads_{kind}_{state}"] += 1
    return counts


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
    """{pr: [every PR of its stack, lowest first]} — `gh stack` first, the parent chain otherwise.

    A stack opened on top of another one's head is one chain of bases, so the parent links alone
    would merge the two and serialise their agents into a single queue. GitHub's own stack is the
    split the author drew; only PRs it knows no stack for fall back to the chain.
    """
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
        groups.setdefault(prs[n].get("stack") or ("chain", chain(n)[-1]), []).append(n)
    order = {}
    for members in groups.values():
        members.sort(key=lambda n: prs[n].get("stack_pos") or len(chain(n)))
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
    # A draft cannot be merged whatever else is green, and a stacked draft does report CLEAN.
    return (not r.get("draft") and r.get("merge_state") == "CLEAN" and r.get("ci") == "SUCCESS"
            and not r.get("unresolved_bot") and not r.get("unresolved_human") and not r.get("held"))


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
    """One line per PR whose watched fields moved, plus MERGE-READY once, on the transition
    into it — not every poll. Pure — the self-check drives it."""
    lines = []
    for n, r in sorted(new.items()):
        prev = old.get(str(n)) or old.get(n)
        if not prev:
            lines.append(f"#{n} new: ci {r['ci']}, {r['merge_state']}, bot {r['unresolved_bot']}, human {r['unresolved_human']}")
        else:
            moved = [f"{f} {prev[f]}→{r[f]}" for f in WATCHED if prev.get(f) != r[f]]
            if moved:
                lines.append(f"#{n} " + ", ".join(moved))
        if merge_ready(r) and not (prev and merge_ready(prev)):
            lines.append(f"#{n} MERGE-READY — {r['url']}")
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
    blob = {str(n): dict(r, schema_version=STATE_SCHEMA_VERSION,
                        report=reports.get(str(n)), seen=seen.get(n, {}))
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


def emit(d, lines):
    """Print for scan.log, append for `--follow`. Past EVENTS_MAX the log starts over: a follower
    only ever reads forward, and state.json carries the present."""
    if not lines:
        return
    path = os.path.join(d, "events.log")
    try:
        full = os.path.getsize(path) > EVENTS_MAX
    except OSError:
        full = False
    with open(path, "w" if full else "a") as f:
        f.write("".join(f"{line}\n" for line in lines))
    for line in lines:
        print(line, flush=True)


def read_selection(d):
    """PR numbers a babysit-prs run named: fetched on top of the author's own."""
    try:
        with open(os.path.join(d, "selection.json")) as f:
            return [int(n) for n in json.load(f)]
    except (OSError, ValueError, TypeError):
        return []


def write_selection(d, only):
    with open(os.path.join(d, "selection.json"), "w") as f:
        json.dump(sorted(only), f)


def touch(path):
    with open(path, "a"):
        pass
    os.utime(path)


def mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def take_lock(path, what, tries=10):
    """flock `path` for this process's lifetime and write our pid and script into it.

    A few tries, not one: a reader's `holder` probe holds the lock for an instant, and a service
    starting in that instant must not give up and leave the repo unwatched.
    """
    lock = open(path, "a+")
    for attempt in range(tries):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if attempt == tries - 1:
                lock.seek(0)
                owner = (lock.read().split() or ["unknown"])[0]
                lock.close()
                raise RuntimeError(f"{what} already active (pid {owner})")
            time.sleep(0.2)
    lock.seek(0)
    lock.truncate()
    lock.write(f"{os.getpid()}\n{SCRIPT}\n")
    lock.flush()
    return lock


def holder(path):
    """(pid, script) of whoever holds the lock at `path`, or None when nobody does.

    The lock itself answers, not the pid: the kernel drops it when its process dies, where a pid
    left in a file can be reused by any process — and SIGUSR1 kills a process that expects none.
    """
    try:
        f = open(path, "a+")
    except OSError:
        return None
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            pid, _, script = f.read().partition("\n")
            return (int(pid) if pid.isdigit() else None), script.strip()
        fcntl.flock(f, fcntl.LOCK_UN)
        return None


def outdated(script):
    """Is the running service another, older copy of this script? A plugin update lands in a new
    directory, and the copy left behind would scan with old code until the service idles out.
    Newer on disk wins, so two versions never take turns replacing each other."""
    if script == SCRIPT:
        return False
    try:
        return os.path.getmtime(SCRIPT) > os.path.getmtime(script)
    except OSError:
        return True  # its copy is gone


def ensure(d):
    """Mark a reader alive, and start the service unless one runs. (pid, started)."""
    touch(os.path.join(d, "reader.heartbeat"))
    lock = os.path.join(d, "watch.lock")
    held = holder(lock)
    if held and not outdated(held[1]):
        return held[0], False
    if held and held[0]:
        os.kill(held[0], signal.SIGTERM)
        for _ in range(25):
            if not holder(lock):
                break
            time.sleep(0.2)
    with open(os.path.join(d, "scan.log"), "a") as log:
        child = subprocess.Popen(
            (sys.executable, SCRIPT, "--watch", str(POLL_DEFAULT), "--repo", "/".join(repo()),
             "--state-dir", d),
            cwd=d, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    return child.pid, True


def wake(d):
    """Ask the running service for a pass now. False when none runs to ask."""
    held = holder(os.path.join(d, "watch.lock"))
    if not held or not held[0]:
        return False
    os.kill(held[0], signal.SIGUSR1)
    return True


def fresh_pass(d):
    """A pass the caller can read: start or wake the service, then wait for state.json to move.
    A service just started runs its first pass on its own — and has no SIGUSR1 handler yet."""
    state = os.path.join(d, "state.json")
    before = mtime(state)
    _, started = ensure(d)
    if not started:
        wake(d)
    deadline = time.time() + PASS_WAIT
    while time.time() < deadline:
        if mtime(state) != before:
            return True
        time.sleep(0.2)
    return False


def muted(d, n):
    """Is an agent still alive on this PR? Its mute file says so — until it goes stale.

    A mute is lifted by the agent's report, and an agent that dies never writes one. Left alone
    that mute reserves the whole stack forever, and the lowest PR that needs work never gets its
    turn. ponytail: age it out on a flat hour — long enough for a real triage-fix-rebase pass on
    a big PR, short enough that a crash costs one hour and not the run. Per-PR budgets if an
    agent ever legitimately runs longer.
    """
    path = os.path.join(d, f"{n}.muted")
    try:
        if time.time() - os.path.getmtime(path) <= MUTE_TTL:
            return True
        os.remove(path)
    except OSError:
        pass
    return False


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


def scan(d, extras=()):
    prev = load_state(d)
    seen = {int(k): dict(v.get("seen") or {}) for k, v in prev.items()}
    # Fold before ventilating: an agent's report certifies everything still open on that PR as
    # deliberately left open, and the row that comes out of this pass has to reflect that — or
    # the manager reads a stale `unresolved_bot` and respawns the agent that just finished.
    reports, report_lines = fold_reports(d)
    # A named PR is fetched by number, past the author filter — and dropped once it closes.
    raw = {n: p for n, p in fetch_raw(sorted(set(open_prs()) | set(extras))).items()
           if p.get("state", "OPEN") == "OPEN"}
    for k in reports:
        n = int(k)
        if n in raw:
            seen[n] = thread_ids(raw[n])
    prs = link_stack(resolve_unknown(
        {n: row(p, seen.get(n, {})) for n, p in raw.items()}, seen))
    return prs, reports, report_lines, seen, prev


def carry(prev, reports, prs):
    """Carry the last report forward, minus the part the world has moved past.

    A held gist points at an open thread. That thread can be resolved by anyone — the next agent,
    or the author in another session, who read the gist and fixed it by hand. The scan sees it on
    the next pass; the report never would. So a gist outlives its thread by exactly zero passes.
    Only PRs this scan actually looked at are touched.
    """
    out = {k: (prev.get(k) or {}).get("report") for k in prev}
    out.update(reports)
    for k, rep in out.items():
        r = prs.get(int(k))
        if rep and r and not r["held"]:
            out[k] = dict(rep, held=0, held_gist=None)
    return out


def selected(state, only, include_drafts, mine):
    """The rows a babysit selection covers: the named PRs, else the author's own, drafts only on
    request. `mine` guards the default: a PR an earlier run named stays in the state, and
    babysitting it unasked would push to a colleague's branch."""
    prs = {int(k): {f: v for f, v in r.items() if f != "seen"} for k, r in state.items()}
    if only:
        return {n: r for n, r in prs.items() if n in only}
    return {n: r for n, r in prs.items() if r.get("author", mine) == mine
            and (include_drafts or not r.get("draft"))}


def once(d, only=(), include_drafts=False):
    """babysit-prs' pass: the service's, freshly run, as that selection's matrix."""
    if only:
        write_selection(d, only)
    fresh = fresh_pass(d)
    prs = link_stack(selected(load_state(d), only, include_drafts, me()))
    order, running = stacks(prs), {n for n in prs if muted(d, n)}
    out = {
        "state_dir": d,
        "prs": [dict(r, needs_agent=needs_agent(r), agent_running=n in running,
                     waits_on=waits_on(r, prs, order, running), merge_ready=merge_ready(r),
                     status=status(r, prs, order, running))
                for n, r in sorted(prs.items())],
    }
    if not fresh:
        out["stale"] = f"no pass landed within {PASS_WAIT}s; this is the last state on disk"
    print(json.dumps(out, indent=2))


def keep(line, state, only, include_drafts, mine):
    """Does this event line belong to the follower's selection? One naming no PR (a scan error)
    does; so does a `gone` line, whose row has left the state and says nothing more."""
    match = re.match(r"#(\d+) ", line)
    if not match:
        return True
    n = int(match.group(1))
    if str(n) not in state:
        return not only or n in only
    return n in selected({str(n): state[str(n)]}, only, include_drafts, mine)


def follow(d, only=(), include_drafts=False):
    """babysit-prs' Monitor: the service's event lines for one selection, until killed.

    Holds babysit.lock, which is how the dashboard knows agents are on the job, and re-ensures
    the service every 30 s: its heartbeat keeps it alive, and a service that died comes back.
    """
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # TaskStop: run the finally below
    try:
        lock = take_lock(os.path.join(d, "babysit.lock"), "babysit-prs")
    except RuntimeError as e:
        print(f"scan error: {e}", flush=True)
        return 1
    path = os.path.join(d, "events.log")
    try:
        if only:
            write_selection(d, only)
        mine, offset, tick = me(), os.path.getsize(path) if os.path.exists(path) else 0, 0
        while True:
            if tick % 30 == 0:
                ensure(d)
            tick += 1
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if size < offset:
                offset = 0  # the service started the log over
            if size > offset:
                with open(path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read()
                whole = chunk[: chunk.rfind(b"\n") + 1]  # a line still being written waits
                offset += len(whole)
                state = load_state(d)
                for line in whole.decode().splitlines():
                    if line and keep(line, state, only, include_drafts, mine):
                        print(line, flush=True)
            time.sleep(1)
    finally:
        if only:
            try:
                os.remove(os.path.join(d, "selection.json"))
            except OSError:
                pass
        lock.close()


def service(d, secs):
    """The one writer of the state. A pass every `secs`, or at once on SIGUSR1."""
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)  # a signal makes the select below return early
    signal.signal(signal.SIGUSR1, lambda *_: None)
    try:
        lock = take_lock(os.path.join(d, "watch.lock"), "watcher")
    except RuntimeError as e:
        print(f"scan error: {e}", flush=True)
        return
    os.chdir(d)
    born = mtime(SCRIPT)
    try:
        while True:
            try:
                prs, reports, lines, seen, prev = scan(d, read_selection(d))
                visible = {n: r for n, r in prs.items() if not muted(d, n)}
                lines += diff({k: v for k, v in prev.items() if int(k) in visible}, visible)
                save_state(d, prs, carry(prev, reports, prs), seen)
                emit(d, lines)
            except Exception as e:  # a transient gh failure must not kill the service
                emit(d, [f"scan error: {e}"])
            if time.time() - (mtime(os.path.join(d, "reader.heartbeat")) or 0) / 1e9 > READER_TTL:
                print(f"no reader for {READER_TTL // 60} min: exiting", flush=True)
                return
            now = mtime(SCRIPT)
            if now is None:
                print("script removed: exiting", flush=True)
                return
            if now != born:
                print("script changed: restarting", flush=True)
                lock.close()
                os.execv(sys.executable, [sys.executable, SCRIPT, *sys.argv[1:]])
            select.select([wake_r], [], [], secs)
            try:
                os.read(wake_r, 512)
            except BlockingIOError:
                pass
    finally:
        lock.close()


def self_check():
    global gh

    a = {"number": 1, "ci": "SUCCESS", "unresolved_bot": 0, "unresolved_human": 0,
         "held": 0, "merge_state": "CLEAN", "head": "aaaaaaa", "mergeable": "MERGEABLE",
         "url": "u"}
    assert diff({"1": a}, {1: a}) == [], "no move, no event"
    assert diff({"1": a}, {1: dict(a, ci="FAILURE")}) == ["#1 ci SUCCESS→FAILURE"]
    two = diff({"1": a}, {1: dict(a, ci="PENDING", head="bbbbbbb")})
    assert two == ["#1 ci SUCCESS→PENDING, head aaaaaaa→bbbbbbb"], two
    # A push flips head + ci only: 2 fields, one line — not one line per check.
    assert len(two) == 1
    assert diff({}, {1: dict(a, ci="PENDING")})[0].startswith("#1 new:")
    assert diff({"1": a}, {}) == ["#1 gone (merged or closed)"]
    # Churn that must stay silent: a thread gets resolved, counts unchanged.
    assert diff({"1": a}, {1: dict(a, mergeable="UNKNOWN")}) == [], "mergeable is not watched"
    ready = a
    assert diff({"1": dict(ready, ci="PENDING")}, {1: ready})[-1] == "#1 MERGE-READY — u"
    assert diff({"1": ready}, {1: ready}) == [], "MERGE-READY fires on the transition, not every poll"
    assert diff({}, {1: ready})[-1] == "#1 MERGE-READY — u", "a PR born ready still announces once"
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
    counts = thread_counts([
        th("cursor", "User", tid="B1"), dict(th("cursor", "User", tid="B2"), isResolved=True),
        th("viclafouch", "User", tid="H1"), dict(th("viclafouch", "User", tid="H2"), isResolved=True)])
    assert counts == {"threads_bot_open": 1, "threads_bot_closed": 1,
                      "threads_human_open": 1, "threads_human_closed": 1}, counts

    original_gh = gh
    calls = []
    def fake_gh(*args):
        calls.append(args)
        assert any('after: "next"' in arg for arg in args), args
        return json.dumps({"data": {"repository": {"p7": {"reviewThreads": {
            "nodes": [{"id": "T100"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}})
    try:
        gh = fake_gh
        page = {"reviewThreads": {"nodes": [{"id": f"T{i}"} for i in range(100)],
                                  "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}
        paginated = fetch_remaining_threads({7: page}, "owner", "repo")
    finally:
        gh = original_gh
    assert len(paginated[7]["reviewThreads"]["nodes"]) == 101 and len(calls) == 1
    # A draft carries mergeStateStatus DRAFT, so it can never leave the matrix on its own —
    # except in a stack, where GitHub reports CLEAN on a draft that nobody can merge.
    assert not merge_ready(dict(a, merge_state="DRAFT"))
    assert not merge_ready(dict(a, draft=True, merge_state="CLEAN", ci="SUCCESS"))
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
    # Bottom to top, one at a time: with the whole stack dirty the root goes first, and each
    # PR's turn only comes once everything below it is clean. The owner is the only `None`.
    def turn():
        return [waits_on(st[n], st, o, set()) for n in (1, 2, 3)]
    for n in st:
        st[n]["unresolved_bot"] = 1
    assert turn() == [None, 1, 1], turn()
    st[1]["unresolved_bot"] = 0
    assert turn() == [2, None, 2], turn()
    st[2]["unresolved_bot"] = 0
    assert turn() == [3, 3, None], turn()
    st[3]["unresolved_bot"] = 0
    assert turn() == [None, None, None], "a clean stack reserves nothing"
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
    # Two `gh stack` stacks, the second based on the first's head: separate queues.
    two = link_stack({1: dict(a, number=1, branch="feat-a", base="main", stack=10, stack_pos=1,
                              ci="FAILURE"),
                      2: dict(a, number=2, branch="feat-b", base="feat-a", stack=10, stack_pos=2),
                      3: dict(a, number=3, branch="feat-c", base="feat-b", stack=11, stack_pos=1)})
    ot = stacks(two)
    assert ot[1] == [1, 2] and ot[3] == [3], ot
    assert waits_on(two[2], two, ot, set()) == 1, "a stack still serialises on itself"
    assert waits_on(two[3], two, ot, set()) is None, \
        "the stack above has its own agent — GitHub's split is the author's"
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
    assert st1(draft=True) == "draft", "a green draft is still nobody's to merge"
    assert is_bot("cursor", "User") and is_bot("x[bot]", "User") and not is_bot("viclafouch", "User")

    # Report on disk survives a dead agent, and reading it lifts that PR's mute.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "watch.lock")
        assert holder(path) is None, "nobody holds a fresh lock"
        lock = take_lock(path, "watcher")
        try:
            assert holder(path) == (os.getpid(), SCRIPT), holder(path)
            try:
                take_lock(path, "watcher", tries=1)
                assert False, "a second watcher acquired the same state"
            except RuntimeError as e:
                assert "watcher already active" in str(e)
        finally:
            lock.close()
        assert holder(path) is None, "a closed lock is free: its holder died"
        take_lock(path, "watcher").close()
        assert not outdated(SCRIPT) and outdated(os.path.join(d, "gone.py")), \
            "our own copy is current; a copy removed from disk is not"
        open(os.path.join(d, "42.muted"), "w").close()
        with open(os.path.join(d, "42.report.json"), "w") as f:
            json.dump({"pushed": 2, "inflight": 0, "held": 3, "blocked": None}, f)
        assert muted(d, 42)
        reports, lines = fold_reports(d)
        assert reports["42"]["held"] == 3
        assert lines == ["#42 report: pushed 2, inflight 0, held 3, blocked -"], lines
        assert not muted(d, 42), "folding the report must lift the mute"
        assert fold_reports(d) == ({}, []), "a folded report is consumed once"
        # The event log grows by appends, and starts over past its cap.
        import contextlib
        import io
        log = os.path.join(d, "events.log")
        with contextlib.redirect_stdout(io.StringIO()):
            emit(d, [])
            assert not os.path.exists(log), "no line, no log"
            emit(d, ["#42 report: pushed 2"])
            emit(d, ["#7 ci FAILURE→SUCCESS"])
        with open(log) as f:
            assert f.read() == "#42 report: pushed 2\n#7 ci FAILURE→SUCCESS\n"
        with open(log, "w") as f:
            f.write("x" * (EVENTS_MAX + 1))
        with contextlib.redirect_stdout(io.StringIO()):
            emit(d, ["#7 head a→b"])
        with open(log) as f:
            assert f.read() == "#7 head a→b\n", "a full log starts over"
        # A selection survives on disk for the service, and garbage reads as none.
        write_selection(d, [456, 123])
        assert read_selection(d) == [123, 456]
        with open(os.path.join(d, "selection.json"), "w") as f:
            f.write("{")
        assert read_selection(d) == []
        # A dead agent writes no report. Its mute must not reserve the stack forever.
        stale = os.path.join(d, "7.muted")
        open(stale, "w").close()
        assert muted(d, 7)
        os.utime(stale, (0, time.time() - MUTE_TTL - 1))
        assert not muted(d, 7) and not os.path.exists(stale), "a stale mute is lifted, not obeyed"
    # A gist outlives its thread by zero passes — whoever resolved it, agent or author elsewhere.
    rep = {"pushed": 1, "held": 1, "held_gist": "gate the pre-event CTA", "blocked": None}
    prev = {"42": {"report": rep}, "7": {"report": rep}}
    live = {42: dict(a, held=1), 7: dict(a, held=0)}
    kept, cleared = carry(prev, {}, live)["42"], carry(prev, {}, live)["7"]
    assert kept["held_gist"] == rep["held_gist"], "an open held thread keeps its gist"
    assert (cleared["held"], cleared["held_gist"]) == (0, None), "a resolved thread drops its gist"
    assert cleared["pushed"] == 1, "pushed is history, not state — it survives"
    assert carry(prev, {}, {})["7"]["held_gist"] == rep["held_gist"], \
        "a PR this pass never scanned keeps its gist"

    # Readers filter the service's full state: babysit-prs sees its own selection only.
    state = {"1": dict(a, author="me", seen={"T": "c"}), "2": dict(a, number=2, author="me", draft=True),
             "3": dict(a, number=3, author="colleague")}
    assert set(selected(state, (), False, "me")) == {1}, "own PRs, no draft, no leftover named PR"
    assert set(selected(state, (), True, "me")) == {1, 2}
    assert set(selected(state, [3], False, "me")) == {3}, "a named PR is the selection"
    assert "seen" not in selected(state, (), False, "me")[1], "comment ids stay out of the matrix"
    assert set(selected({"9": dict(a, number=9)}, (), False, "me")) == {9}, \
        "a row from before the author field is the author's"
    assert keep("#1 ci SUCCESS→FAILURE", state, (), False, "me")
    assert not keep("#2 head a→b", state, (), False, "me"), "a draft stays quiet unless asked"
    assert not keep("#3 head a→b", state, (), False, "me"), "so does a PR nobody named this run"
    assert keep("#3 head a→b", state, [3], False, "me") and not keep("#1 head a→b", state, [3], False, "me")
    assert keep("#8 gone (merged or closed)", state, (), False, "me")
    assert not keep("#8 gone (merged or closed)", state, [3], False, "me")
    assert keep("scan error: gh: timeout", state, [3], False, "me"), "an error concerns everyone"

    ns = parser().parse_args(["123", "456", "--include-drafts", "--follow"])
    assert (ns.prs, ns.follow, ns.include_drafts) == ([123, 456], True, True), ns
    assert parser().parse_args([]).prs == [] and parser().parse_args([]).watch is None
    assert parser().parse_args(["--watch"]).watch == POLL_DEFAULT, "bare --watch keeps the default"
    assert parser().parse_args(["--watch", "--repo", "o/n"]).repo == "o/n"
    print("self-check ok")


def parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prs", nargs="*", type=int, help="PR numbers to select; default is every open PR")
    ap.add_argument("--watch", nargs="?", const=POLL_DEFAULT, type=int, metavar="SECS")
    ap.add_argument("--follow", action="store_true")
    ap.add_argument("--repo", metavar="OWNER/NAME")
    ap.add_argument("--state-dir", help=argparse.SUPPRESS)  # where the reader that started it reads
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    return ap


if __name__ == "__main__":
    ns = parser().parse_args()
    if ns.self_check:
        self_check()
    else:
        repo(ns.repo)
        d = ns.state_dir or state_dir()
        if ns.watch is not None:
            service(d, ns.watch)
        elif ns.follow:
            sys.exit(follow(d, ns.prs, ns.include_drafts))
        else:
            once(d, ns.prs, ns.include_drafts)
