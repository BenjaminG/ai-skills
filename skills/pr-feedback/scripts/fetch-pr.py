#!/usr/bin/env python3
"""Fetch everything pr-feedback triage needs about a PR, as one compact JSON blob.

Usage: fetch-pr.py [pr-number-or-url]   (no arg = detect from current branch)
       fetch-pr.py --self-check         (offline assertions on the normalisation)
"""
import concurrent.futures as cf
import json
import re
import time
import subprocess
import sys

BODY_CAP = 1200
SETTLED_CAP = 300
LOG_LINES = 50
LOG_CHARS = 3000
BOT_LOGINS = {"naboo-ai-reviews", "cursor", "coderabbitai", "sonarcloud"}


def gh(*args, check=True):
    p = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if p.returncode and check:
        raise RuntimeError(f"gh {' '.join(args)[:80]}: {p.stderr.strip()[:200]}")
    return p.stdout


def trunc(s, cap=BODY_CAP):
    s = (s or "").strip()
    return s if len(s) <= cap else s[:cap] + " […]"


def is_bot(login, typename):
    return typename == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS


def flatten(comments, cap):
    return [{"author": (c.get("author") or {}).get("login", "ghost"),
             "is_bot": is_bot((c.get("author") or {}).get("login", ""),
                              (c.get("author") or {}).get("__typename", "")),
             "body": trunc(c.get("body"), cap)} for c in comments]


def normalise_threads(nodes, pr_author):
    """Split threads into the live working set and the settled (resolved/outdated) ones.

    Returns (threads, settled).
    """
    out, settled = [], []
    for t in nodes:
        comments = t.get("comments", {}).get("nodes", [])
        if not comments:
            continue
        # ponytail: resolved or outdated means done, no exception. GitHub exposes no
        # resolve timestamp, so "a comment landed after the resolve" is not decidable
        # here; a reviewer who spots a regression unresolves the thread or opens a new
        # one. Settled threads still ship as short excerpts, because a PR-level bot
        # summary carries no path:line and only they can show it is stale.
        if t.get("isResolved") or t.get("isOutdated"):
            settled.append({
                "path": t.get("path"),
                "line": t.get("line"),
                "resolved": bool(t.get("isResolved")),
                "outdated": bool(t.get("isOutdated")),
                "comments": flatten(comments, SETTLED_CAP),
            })
            continue
        cs = flatten(comments, BODY_CAP)
        awaiting = cs[-1]["author"] == pr_author
        rounds = sum(1 for c in cs if c["author"] == pr_author)
        out.append({
            "id": t.get("id"),
            "comment_id": comments[0].get("databaseId"),
            "path": t.get("path"),
            "line": t.get("line"),
            "awaiting_reviewer": awaiting,
            # How many times we have already answered here. `rounds >= 1` with a bot speaking
            # last means the item is the bot's *reply*, not the finding it opened with.
            "rounds": rounds,
            # A bot thread we already answered and deliberately left open: the decision is the
            # author's. Re-triaging it would post a second reply nobody reads and could resolve
            # away the very thread that marks where the author has to look.
            "held": awaiting and cs[0]["is_bot"],
            "comments": cs,
        })
    return out, settled


QUERY = """query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
  repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
    reviewThreads(first:100,after:$cursor){ pageInfo{hasNextPage endCursor}
      nodes{ id isResolved isOutdated path line
        comments(first:20){ nodes{ databaseId author{login __typename} body } } } } } }
}"""


def fetch_threads(owner, repo, num, pr_author):
    nodes, cursor = [], None
    while True:
        args = ["api", "graphql", "-f", f"query={QUERY}", "-F", f"owner={owner}",
                "-F", f"repo={repo}", "-F", f"pr={num}"]
        if cursor:
            args += ["-F", f"cursor={cursor}"]
        page = json.loads(gh(*args))["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return normalise_threads(nodes, pr_author)


def fetch_reviews(owner, repo, num):
    slug = f"{owner}/{repo}"   # explicit: a PR URL may point outside the current checkout
    rs = json.loads(gh("pr", "view", str(num), "--repo", slug, "--json", "reviews"))["reviews"]
    out = []
    for r in rs:
        login = (r.get("author") or {}).get("login", "ghost")
        if not r.get("body", "").strip() and r.get("state") == "COMMENTED":
            continue
        bot = is_bot(login, r.get("authorAssociation", ""))
        # ponytail: a bot re-reviews on every push, so its older passes are superseded
        # verbatim. Keep the last one per bot; humans keep their whole history.
        if bot and out and out[-1]["author"] == login:
            out[-1] = {"author": login, "state": r.get("state"), "body": trunc(r.get("body"))}
            continue
        out.append({"author": login, "state": r.get("state"), "body": trunc(r.get("body"))})
    return out


def fetch_comments(owner, repo, num):
    cs = json.loads(gh("api", f"repos/{owner}/{repo}/issues/{num}/comments", "--paginate"))
    return [{"author": (c.get("user") or {}).get("login", "ghost"),
             "is_bot": is_bot((c.get("user") or {}).get("login", ""),
                              (c.get("user") or {}).get("type", "")),
             "body": trunc(c.get("body"))} for c in cs]


def fetch_checks(owner, repo, num):
    slug = f"{owner}/{repo}"
    raw = gh("pr", "checks", str(num), "--repo", slug, check=False)
    out = []
    for line in raw.splitlines():
        cols = line.split("\t")
        if len(cols) < 4 or cols[1] not in ("fail", "failure"):
            continue
        name, url = cols[0], cols[3]
        job = re.search(r"/job/(\d+)", url)
        tail = ""
        if job:
            log = gh("run", "view", "--repo", slug, "--log-failed", "--job", job.group(1),
                     check=False)
            tail = "\n".join(log.splitlines()[-LOG_LINES:])[-LOG_CHARS:]
        out.append({"name": name, "url": url, "log_tail": tail})
    return out


def main(argv):
    ref = argv[0] if argv else None
    view = ["pr", "view"] + ([ref] if ref else []) + [
        "--json", "number,url,headRefName,baseRefName,state,author,isDraft,mergeable"]
    pr = json.loads(gh(*view))
    if pr.get("mergeable") == "UNKNOWN":   # GitHub computes it async; one retry usually settles it
        time.sleep(3)
        pr = json.loads(gh(*view))
    num, url = pr["number"], pr["url"]
    author = (pr.get("author") or {}).get("login", "")
    owner, repo = re.search(r"github\.com/([^/]+)/([^/]+)/pull/", url).groups()

    errors = []
    jobs = {
        "threads": lambda: fetch_threads(owner, repo, num, author),
        "reviews": lambda: fetch_reviews(owner, repo, num),
        "comments": lambda: fetch_comments(owner, repo, num),
        "failing_checks": lambda: fetch_checks(owner, repo, num),
    }
    result = {}
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fn): k for k, fn in jobs.items()}
        for f in cf.as_completed(futs):
            k = futs[f]
            try:
                result[k] = f.result()
            except Exception as e:
                result[k] = ([], []) if k == "threads" else []
                errors.append(f"{k}: {e}")

    json.dump({
        "pr": {"number": num, "url": url, "author": author, "owner": owner, "repo": repo,
               "head": pr["headRefName"], "base": pr["baseRefName"], "state": pr["state"],
               "draft": pr["isDraft"], "mergeable": pr["mergeable"]},
        "threads": result["threads"][0] if result["threads"] else [],
        "settled_threads": result["threads"][1] if result["threads"] else [],
        "reviews": result["reviews"],
        "comments": result["comments"],
        "failing_checks": result["failing_checks"],
        "errors": errors,
    }, sys.stdout, indent=1)
    print()


def self_check():
    nodes = [
        {"id": "T1", "isResolved": True, "isOutdated": False, "path": "a.ts", "line": 1,
         "comments": {"nodes": [{"databaseId": 1, "author": {"login": "bob", "__typename": "User"},
                                 "body": "x"}]}},
        {"id": "T2", "isResolved": False, "isOutdated": False, "path": "b.ts", "line": 2,
         "comments": {"nodes": [
             {"databaseId": 2, "author": {"login": "cursor", "__typename": "Bot"}, "body": "y"},
             {"databaseId": 3, "author": {"login": "me", "__typename": "User"}, "body": "fixed"}]}},
        {"id": "T3", "isResolved": False, "isOutdated": False, "path": "c.ts", "line": 3,
         "comments": {"nodes": [{"databaseId": 4, "author": {"login": "naboo-ai-reviews",
                                                             "__typename": "User"}, "body": "z"}]}},
        {"id": "T4", "isResolved": True, "isOutdated": False, "path": "d.ts", "line": 4,
         "comments": {"nodes": [
             {"databaseId": 5, "author": {"login": "bob", "__typename": "User"}, "body": "old"},
             {"databaseId": 6, "author": {"login": "bob", "__typename": "User"},
              "body": "regressed again"}]}},
    ]
    out, settled = normalise_threads(nodes, pr_author="me")
    ids = [t["id"] for t in out]
    assert ids == ["T2", "T3"], ids                           # T1 and T4 resolved: out of the set
    assert [s["path"] for s in settled] == ["a.ts", "d.ts"]   # kept as evidence, not as items
    assert settled[0]["resolved"] and not settled[0]["outdated"]
    assert len(settled[1]["comments"]) == 2                   # whole exchange, so a stale
    assert settled[1]["comments"][-1]["body"] == "regressed again"   # summary can be matched
    assert len(trunc("a" * 2000, SETTLED_CAP)) == SETTLED_CAP + 4
    assert out[0]["awaiting_reviewer"] is True                # last comment is the PR author
    assert out[0]["comments"][0]["is_bot"] is True            # __typename Bot
    assert out[0]["comment_id"] == 2                          # first comment's databaseId
    assert out[0]["held"] is True, "bot thread, our reply last: held for the author, not re-triaged"
    assert out[0]["rounds"] == 1 and out[1]["rounds"] == 0
    assert out[1]["awaiting_reviewer"] is False and out[1]["held"] is False
    # The bot answers back on a thread we already replied to: not held, but not a new finding —
    # `rounds` is what tells the triage the item is that reply, not the head of the thread.
    again, _ = normalise_threads([
        {"id": "T6", "isResolved": False, "isOutdated": False, "path": "f.ts", "line": 6,
         "comments": {"nodes": [
             {"databaseId": 9, "author": {"login": "cursor", "__typename": "Bot"}, "body": "claim"},
             {"databaseId": 10, "author": {"login": "me", "__typename": "User"}, "body": "no"},
             {"databaseId": 11, "author": {"login": "cursor", "__typename": "Bot"},
              "body": "accepted"}]}},
    ], pr_author="me")
    assert again[0]["held"] is False and again[0]["rounds"] == 1
    # A human thread we answered last awaits its reviewer — it is theirs, never ours to hold.
    human, _ = normalise_threads([
        {"id": "T5", "isResolved": False, "isOutdated": False, "path": "e.ts", "line": 5,
         "comments": {"nodes": [
             {"databaseId": 7, "author": {"login": "bob", "__typename": "User"}, "body": "?"},
             {"databaseId": 8, "author": {"login": "me", "__typename": "User"}, "body": "done"}]}},
    ], pr_author="me")
    assert human[0]["awaiting_reviewer"] is True and human[0]["held"] is False
    assert out[1]["comments"][0]["is_bot"] is True            # known bot login, User typename
    assert trunc("a" * 2000).endswith("[…]") and len(trunc("a" * 2000)) == BODY_CAP + 4
    assert is_bot("dependabot[bot]", "User") and not is_bot("alice", "User")
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main([a for a in sys.argv[1:] if not a.startswith("--")])
