#!/usr/bin/env python3
"""Human review comments on merged PRs, as one JSON corpus for review-mining to classify.

Usage: mine-reviews.py [owner/repo] [--since 30d|YYYY-MM-DD] [--limit 300]
       mine-reviews.py --self-check        offline assertions on the filters

Owns the mechanical: PR selection by merge date, one aliased GraphQL call per chunk,
the human filter, the corpus file. Owns no judgment: never decides what a comment means.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

BODY_CAP = 600
MIN_BODY = 15          # "LGTM", "done", "👍" carry no rule
CHUNK = 20             # PRs per GraphQL call — 20 x 100 threads x 20 comments stays under the node cap
# Same list as pr-feedback/scripts/fetch-pr.py and babysit-prs/scripts/babysit-scan.py —
# a machine account posting with a PAT reads as `User`, so __typename alone is not enough.
BOT_LOGINS = {"naboo-ai-reviews", "cursor", "coderabbitai", "sonarcloud"}

# A review an agent wrote and a human pasted under their own login. On naboo-team/naboo
# this was 27 of 66 "human" comments over two weeks, so mining them as team convention
# would feed the loop its own output. Flagged, not dropped: the tells are probabilistic,
# and Step 2 of the skill does the judging.
AGENT_TELLS = [re.compile(p, re.M | re.I) for p in (
    r"\*\*Confidence:?\*\*", r"\*\*Confiance\s*:?\*\*",     # gate / gate-wf finding header
    r"^#{2,3}\s*[🔴🟡🔵🟢]", r"\[[A-Z]{3,5}-[0-9A-Z]{1,3}\]",   # severity headers, cluster ids
    r"\*\*(?:Blocker|Bloquant|Major|Minor|Mineur)\s*[—–-]",
    r"Two-axis review", r"Revue multi-agents", r"adversari",
    r"relecteurs? (?:sp[ée]cialis|ind[ée]pendant)",
    r"^\*\*Rule:?\*\*", r"\bR\d+\.\d+[a-z]?\b",             # rule-file citations
)]
# Long and citation-dense reads as machine work even with no explicit tell.
CITATION = re.compile(r"`[\w./\[\]()-]+\.\w{2,4}:\d+")


def agent_shaped(body):
    if any(p.search(body) for p in AGENT_TELLS):
        return True
    return len(body) > 400 and len(CITATION.findall(body)) >= 2


FRAGMENT = """
fragment S on PullRequest {
  number url title mergedAt author { login }
  reviewThreads(first: 100) {
    nodes { isResolved isOutdated path line
      comments(first: 20) { nodes { author { login __typename } body createdAt } } }
  }
  reviews(first: 50) { nodes { author { login __typename } state body } }
}
"""


def gh(*args):
    p = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)[:60]}: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def trunc(s, cap=BODY_CAP):
    s = (s or "").strip()
    return s if len(s) <= cap else s[:cap] + " […]"


def is_bot(login, typename):
    return typename == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS


def who(node):
    a = node.get("author") or {}
    return a.get("login", "ghost"), a.get("__typename", "")


def since_date(s):
    """`30d` or an ISO date -> YYYY-MM-DD."""
    m = re.fullmatch(r"(\d+)d", s)
    if m:
        return (dt.date.today() - dt.timedelta(days=int(m.group(1)))).isoformat()
    try:
        return dt.date.fromisoformat(s).isoformat()
    except ValueError:
        # Never widen the window on a typo: a silently wrong window makes every count wrong.
        raise ValueError(f"--since wants `30d` or `YYYY-MM-DD`, got {s!r}")


def resolve_repo(arg):
    if arg and re.fullmatch(r"[\w.-]+/[\w.-]+", arg):
        return arg
    return gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()


def merged_prs(slug, since, limit):
    """Selection first, threads second: a repo has thousands of merged PRs and an
    unfiltered GraphQL walk over them never returns."""
    out = gh("pr", "list", "--repo", slug, "--limit", str(limit),
             "--search", f"is:merged merged:>={since}",
             "--json", "number,mergedAt")
    return json.loads(out)


def fetch_chunk(slug, numbers):
    owner, _, name = slug.partition("/")
    aliases = "\n".join(f"  p{n}: pullRequest(number: {n}) {{ ...S }}" for n in numbers)
    query = f"query($o:String!,$r:String!){{\n repository(owner:$o,name:$r){{\n{aliases}\n }}\n}}\n{FRAGMENT}"
    raw = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"))
    return [p for p in raw["data"]["repository"].values() if p]


def extract(pr):
    """One record per human-initiated review thread and per human review body.

    Returns (records, bot_thread_reactions).
    """
    pr_author = (pr.get("author") or {}).get("login", "")
    num, url = pr["number"], pr["url"]
    out, reactions = [], 0

    for t in pr["reviewThreads"]["nodes"]:
        cs = t["comments"]["nodes"]
        if not cs:
            continue
        login, typename = who(cs[0])
        if is_bot(login, typename):
            # A human arguing inside a bot's thread reacts to the bot; it is not a
            # convention the team imposes. Counted, kept out of the corpus.
            if any(not is_bot(*who(c)) for c in cs[1:]):
                reactions += 1
            continue
        if login == pr_author:
            continue                      # authors annotating their own diff are not reviewing it
        body = trunc(cs[0].get("body"))
        if len(body) < MIN_BODY:
            continue
        out.append({"pr": num, "url": url, "author": login, "kind": "thread",
                    "path": t.get("path"), "line": t.get("line"),
                    "resolved": bool(t.get("isResolved")), "thread_len": len(cs),
                    "agent_shaped": agent_shaped(body), "body": body})

    for r in pr["reviews"]["nodes"]:
        login, typename = who(r)
        if is_bot(login, typename) or login == pr_author:
            continue
        body = trunc(r.get("body"))
        if len(body) < MIN_BODY:
            continue
        out.append({"pr": num, "url": url, "author": login, "kind": "review",
                    "path": None, "line": None, "resolved": None, "thread_len": 1,
                    "agent_shaped": agent_shaped(body), "state": r.get("state"), "body": body})

    return out, reactions


def state_dir(slug):
    d = os.path.join(os.path.expanduser("~"), ".claude", "review-mining-state", slug.replace("/", "_"))
    os.makedirs(d, exist_ok=True)
    return d


def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("repo", nargs="?", default=None)
    ap.add_argument("--since", default="30d")
    ap.add_argument("--limit", type=int, default=300)
    a = ap.parse_args(argv)

    slug = resolve_repo(a.repo)
    try:
        since = since_date(a.since)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    prs = merged_prs(slug, since, a.limit)
    if not prs:
        print(json.dumps({"repo": slug, "prs": 0, "window": [since, dt.date.today().isoformat()],
                          "error": "no merged PR in this window"}), flush=True)
        return 1

    numbers = [p["number"] for p in prs]
    comments, reactions, truncated, errors = [], 0, [], []
    for i in range(0, len(numbers), CHUNK):
        batch = numbers[i:i + CHUNK]
        try:
            payloads = fetch_chunk(slug, batch)
        except Exception as e:
            errors.append(f"PRs {batch[0]}-{batch[-1]}: {e}")
            continue
        for p in payloads:
            cs, r = extract(p)
            comments += cs
            reactions += r
            # ponytail: no cursor pagination inside a PR. A PR at the 100-thread cap is
            # reported here; add cursors only when a `truncated` entry actually appears.
            if len(p["reviewThreads"]["nodes"]) >= 100:
                truncated.append(p["number"])

    dates = sorted(p["mergedAt"][:10] for p in prs)
    corpus = {
        "repo": slug,
        "prs": len(prs),
        "window": [dates[0], dates[-1]],
        "bot_thread_reactions": reactions,
        "agent_shaped": sum(1 for c in comments if c["agent_shaped"]),
        "humans_seen": sorted({c["author"] for c in comments}),
        "truncated": truncated,
        "errors": errors,
        "comments": comments,
    }
    path = os.path.join(state_dir(slug), f"raw-{dt.date.today().isoformat()}.json")
    with open(path, "w") as f:
        json.dump(corpus, f, indent=1)

    summary = {k: v for k, v in corpus.items() if k != "comments"}
    summary["comments"] = len(comments)
    summary["agent_shaped_by_author"] = {
        a: sum(1 for c in comments if c["author"] == a and c["agent_shaped"])
        for a in corpus["humans_seen"]}
    summary["file"] = path
    print(json.dumps(summary, indent=1))
    return 0


def self_check():
    assert is_bot("dependabot[bot]", "User") and is_bot("x", "Bot") and is_bot("cursor", "User")
    assert not is_bot("alice", "User")
    assert since_date("30d") == (dt.date.today() - dt.timedelta(days=30)).isoformat()
    assert since_date("2026-01-02") == "2026-01-02"
    try:
        since_date("last month")
        assert False, "a bad --since must raise, not silently widen the window"
    except ValueError:
        pass
    assert len(trunc("a" * 900)) == BODY_CAP + 4 and trunc("a" * 900).endswith("[…]")
    assert resolve_repo("naboo-team/naboo") == "naboo-team/naboo"

    def th(login, typename="User", body="please extract this into a service", extra=None,
           resolved=False, path="a.ts", line=1):
        cs = [{"author": {"login": login, "__typename": typename}, "body": body}]
        cs += extra or []
        return {"isResolved": resolved, "isOutdated": False, "path": path, "line": line,
                "comments": {"nodes": cs}}

    pr = {
        "number": 412, "url": "u", "title": "t", "mergedAt": "2026-09-01T00:00:00Z",
        "author": {"login": "carol"},
        "reviewThreads": {"nodes": [
            th("alice", resolved=True),                                   # kept
            th("cursor", "Bot", extra=[{"author": {"login": "carol", "__typename": "User"},
                                        "body": "disagree, this is intentional"}]),  # reaction
            th("naboo-ai-reviews", "User"),                               # bot alone: dropped
            th("carol"),                                                  # PR author: dropped
            th("alice", body="LGTM"),                                     # too short: dropped
            th("bob", extra=[{"author": {"login": "carol", "__typename": "User"},
                              "body": "fixed"}], path="b.ts", line=7),    # kept, thread_len 2
        ]},
        "reviews": {"nodes": [
            {"author": {"login": "bob", "__typename": "User"}, "state": "CHANGES_REQUESTED",
             "body": "split this controller, it holds business logic"},   # kept
            {"author": {"login": "naboo-ai-reviews", "__typename": "User"}, "state": "COMMENTED",
             "body": "3 issues found, see inline"},                       # bot: dropped
            {"author": {"login": "alice", "__typename": "User"}, "state": "APPROVED",
             "body": ""},                                                 # empty: dropped
            {"author": {"login": "carol", "__typename": "User"}, "state": "COMMENTED",
             "body": "self review: renamed the helper for clarity"},      # PR author: dropped
        ]},
    }
    recs, reactions = extract(pr)
    assert reactions == 1, reactions
    assert [(r["author"], r["kind"]) for r in recs] == [
        ("alice", "thread"), ("bob", "thread"), ("bob", "review")], recs
    assert recs[0]["resolved"] is True and recs[0]["thread_len"] == 1
    assert recs[1]["thread_len"] == 2 and recs[1]["path"] == "b.ts" and recs[1]["line"] == 7
    assert recs[2]["path"] is None and recs[2]["state"] == "CHANGES_REQUESTED"
    assert not any(r["agent_shaped"] for r in recs), "plain prose is not agent-shaped"
    assert agent_shaped("**Blocker — the double and the real adapter disagree.**")
    assert agent_shaped("### 🔴 [A] Le `replaceOne` écrase les colonnes")
    assert agent_shaped("Use `getByRole` — higher priority per R4.1 and avoids R4.2.")
    assert agent_shaped("**Confidence:** HIGH\n\nThe schema has no `.max()`.")
    assert agent_shaped("x" * 401 + " `a/b.ts:12` and `c/d.ts:44`"), "long + citation-dense"
    assert not agent_shaped("cause => reason")
    assert not agent_shaped("this can be null when the cart expired, guard it first")
    # A short comment citing one line stays human: that is how people point at code.
    assert not agent_shaped("see `foo/bar.ts:12`, same null case as last week")
    # A thread whose head is a bot never enters the corpus, however long the human argument.
    assert all(r["author"] not in BOT_LOGINS for r in recs)
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        sys.exit(main(sys.argv[1:]))
