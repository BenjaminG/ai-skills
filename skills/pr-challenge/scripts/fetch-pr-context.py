#!/usr/bin/env python3
"""Fetch what pr-challenge needs to review someone else's PR, as one JSON blob.

Unlike pr-feedback's fetcher, which collects what reviewers said about *our* PR, this
one collects what a reviewer needs before speaking: the stated goal, the diff, the
symbols the diff introduces (the reuse pass runs off those), and every point already
made on the thread — so the pass never asks a question the PR already answers.

Usage: fetch-pr-context.py [pr-number-or-url]   (no arg = detect from current branch)
       fetch-pr-context.py --self-check         (offline assertions on the parsing)
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BODY_CAP = 2000
COMMENT_CAP = 400
SAMPLE_CAP = 300
DIFF_CAP = 4_000_000
BOT_LOGINS = {"naboo-ai-reviews", "cursor", "coderabbitai", "sonarcloud", "codecov"}

# Top-level declarations a diff adds. Each pattern's first group is the symbol name;
# the reuse pass greps the repo for every one of them before any comment is drafted.
DECL_PATTERNS = [
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)"),
    re.compile(r"^\s*export\s+(?:abstract\s+)?class\s+(\w+)"),
    re.compile(r"^\s*export\s+(?:const|let)\s+(\w+)"),
    re.compile(r"^\s*export\s+(?:type|interface|enum)\s+(\w+)"),
    re.compile(r"^\s*(?:public\s+|private\s+)?(?:async\s+)?def\s+(\w+)"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)"),
    re.compile(r"^\s*(?:public\s+|internal\s+)?(?:final\s+)?(?:class|struct|protocol|actor)\s+(\w+)"),
]


def gh(*args, check=True):
    p = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if p.returncode and check:
        raise RuntimeError(f"gh {' '.join(args)[:80]}: {p.stderr.strip()[:200]}")
    return p.stdout


def trunc(s, cap=BODY_CAP):
    s = (s or "").strip()
    return s if len(s) <= cap else s[:cap] + " […]"


def is_bot(login, typename=""):
    return typename == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS


def declarations(diff):
    """Symbols the diff introduces, per file, from `+` lines only.

    A name that also appears on a `-` line in the same file is a move or a rename, not
    a new thing, so it is dropped: asking "does this already exist" about code the PR
    is relocating wastes the one question budget that matters.
    """
    out, path, added, removed = {}, None, {}, {}
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            continue
        if not path or line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            body, bucket = line[1:], added
        elif line.startswith("-"):
            body, bucket = line[1:], removed
        else:
            continue
        for pat in DECL_PATTERNS:
            m = pat.match(body)
            if m:
                bucket.setdefault(path, set()).add(m.group(1))
                break
    for p, names in added.items():
        fresh = sorted(names - removed.get(p, set()))
        if fresh:
            out[p] = fresh
    return out


def issue_refs(body):
    """Ticket and issue references in the PR body — where the stated goal usually lives."""
    text = body or ""
    refs = set(re.findall(r"(?<![\w/])#(\d+)\b", text))
    keys = set(re.findall(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b", text))
    return sorted(f"#{r}" for r in refs) + sorted(keys)


def fetch_threads(owner, repo, num):
    """Every point already made on this PR, resolved ones included.

    A resolved thread still counts as said: re-raising it is how an automated pass
    announces itself. So they ship in the same list, flagged.
    """
    q = """
    query($owner:String!,$repo:String!,$num:Int!,$cursor:String){
      repository(owner:$owner,name:$repo){ pullRequest(number:$num){
        reviewThreads(first:100,after:$cursor){
          pageInfo{ hasNextPage endCursor }
          nodes{ path line isResolved isOutdated
            comments(first:20){ nodes{ author{ login __typename } body } } } } } } }
    """
    out, cursor = [], None
    while True:
        raw = gh("api", "graphql", "-f", f"query={q}", "-F", f"owner={owner}",
                 "-F", f"repo={repo}", "-F", f"num={num}",
                 *(["-F", f"cursor={cursor}"] if cursor else []))
        page = json.loads(raw)["data"]["repository"]["pullRequest"]["reviewThreads"]
        for t in page["nodes"]:
            cs = t.get("comments", {}).get("nodes", [])
            if not cs:
                continue
            out.append({
                "path": t.get("path"), "line": t.get("line"),
                "settled": bool(t.get("isResolved") or t.get("isOutdated")),
                "comments": [{"author": (c.get("author") or {}).get("login", "ghost"),
                              "is_bot": is_bot((c.get("author") or {}).get("login", ""),
                                               (c.get("author") or {}).get("__typename", "")),
                              "body": trunc(c.get("body"), COMMENT_CAP)} for c in cs],
            })
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def fetch_pr_comments(owner, repo, num):
    raw = gh("api", f"repos/{owner}/{repo}/issues/{num}/comments", "--paginate")
    return [{"author": (c.get("user") or {}).get("login", "ghost"),
             "is_bot": is_bot((c.get("user") or {}).get("login", ""),
                              (c.get("user") or {}).get("type", "")),
             "body": trunc(c.get("body"), COMMENT_CAP)} for c in json.loads(raw)]


def fetch_language_sample(owner, repo):
    """Short human review comments from elsewhere in the repo.

    The drafting pass writes in the language and register the team actually reviews in;
    this is the only evidence of what that is. Long bodies are dropped — an essay is a
    bot or a design discussion, not the one-line register we are matching.
    """
    raw = gh("api", f"repos/{owner}/{repo}/pulls/comments?per_page=60&sort=created&direction=desc",
             check=False)
    if not raw.strip():
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out = []
    for c in items if isinstance(items, list) else []:
        login = (c.get("user") or {}).get("login", "")
        body = (c.get("body") or "").strip()
        if is_bot(login, (c.get("user") or {}).get("type", "")):
            continue
        if not body or len(body) > SAMPLE_CAP or "```" in body:
            continue
        out.append({"author": login, "body": body})
        if len(out) == 8:
            break
    return out


def state_dir(owner, repo):
    d = Path(os.path.expanduser("~")) / ".claude" / "pr-challenge-state" / f"{owner}_{repo}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main(argv):
    ref = argv[0] if argv else None
    fields = ("number,url,title,body,author,headRefName,headRefOid,baseRefName,state,"
              "isDraft,additions,deletions,changedFiles,files")
    view = ["pr", "view"] + ([ref] if ref else []) + ["--json", fields]
    pr = json.loads(gh(*view))
    num, url = pr["number"], pr["url"]
    author = (pr.get("author") or {}).get("login", "")
    owner, repo = re.search(r"github\.com/([^/]+)/([^/]+)/pull/", url).groups()

    errors = []
    viewer = ""
    try:
        viewer = json.loads(gh("api", "user")).get("login", "")
    except Exception as e:
        errors.append(f"viewer: {e}")

    diff = ""
    try:
        diff = gh("pr", "diff", str(num), "--repo", f"{owner}/{repo}")[:DIFF_CAP]
    except Exception as e:
        errors.append(f"diff: {e}")

    diff_path = state_dir(owner, repo) / f"{num}.diff"
    diff_path.write_text(diff)

    jobs = {
        "threads": lambda: fetch_threads(owner, repo, num),
        "pr_comments": lambda: fetch_pr_comments(owner, repo, num),
        "language_sample": lambda: fetch_language_sample(owner, repo),
    }
    result = {}
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fn): k for k, fn in jobs.items()}
        for f in cf.as_completed(futs):
            k = futs[f]
            try:
                result[k] = f.result()
            except Exception as e:
                result[k] = []
                errors.append(f"{k}: {e}")

    files = [{"path": f.get("path"), "additions": f.get("additions"),
              "deletions": f.get("deletions")} for f in pr.get("files") or []]

    json.dump({
        "pr": {"number": num, "url": url, "owner": owner, "repo": repo, "author": author,
               "title": pr.get("title"), "body": trunc(pr.get("body")),
               "head": pr["headRefName"], "head_sha": pr["headRefOid"],
               "base": pr["baseRefName"], "state": pr["state"], "draft": pr["isDraft"],
               "additions": pr.get("additions"), "deletions": pr.get("deletions"),
               "changed_files": pr.get("changedFiles")},
        "viewer": viewer,
        "is_own_pr": bool(viewer) and viewer == author,
        "issue_refs": issue_refs(pr.get("body")),
        "files": files,
        "diff_path": str(diff_path),
        "diff_bytes": len(diff),
        "new_declarations": declarations(diff),
        "threads": result["threads"],
        "pr_comments": result["pr_comments"],
        "language_sample": result["language_sample"],
        "errors": errors,
    }, sys.stdout, indent=1)
    print()


def self_check():
    diff = "\n".join([
        "diff --git a/src/money.ts b/src/money.ts",
        "--- a/src/money.ts",
        "+++ b/src/money.ts",
        "+export function formatCurrency(n: number) {",
        "+export const TAX_RATE = 0.2",
        " unchanged line",
        "diff --git a/src/old.ts b/src/old.ts",
        "--- a/src/old.ts",
        "+++ b/src/old.ts",
        "-export function moved(a: number) {",
        "+export function moved(a: number, b: number) {",
        "+export type Receipt = { id: string }",
        "diff --git a/api/handler.py b/api/handler.py",
        "--- a/api/handler.py",
        "+++ b/api/handler.py",
        "+def handle_webhook(req):",
    ])
    d = declarations(diff)
    assert d["src/money.ts"] == ["TAX_RATE", "formatCurrency"], d["src/money.ts"]
    # `moved` is on both sides: a signature change, not a new symbol. Only `Receipt` is new.
    assert d["src/old.ts"] == ["Receipt"], d["src/old.ts"]
    assert d["api/handler.py"] == ["handle_webhook"], d["api/handler.py"]
    assert "unchanged line" not in json.dumps(d)
    assert declarations("") == {}

    assert issue_refs("fixes #412 and PROJ-88") == ["#412", "PROJ-88"]
    assert issue_refs("see https://x.dev/a/b#42") == []          # anchor in a URL is not a ref
    assert issue_refs(None) == []

    assert is_bot("dependabot[bot]", "User") and is_bot("cursor") and not is_bot("alice", "User")
    assert trunc("a" * 3000, COMMENT_CAP).endswith("[…]")
    assert len(trunc("a" * 3000, COMMENT_CAP)) == COMMENT_CAP + 4
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main([a for a in sys.argv[1:] if not a.startswith("--")])
