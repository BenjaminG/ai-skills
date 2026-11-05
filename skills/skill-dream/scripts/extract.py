#!/usr/bin/env python3
"""Cut every run of one ai-skills skill out of the local Claude Code transcripts.

Usage: extract.py <skill> [--since 30d|YYYY-MM-DD] [--max 60] [--out DIR]
                  [--projects DIR] [--repo DIR | --no-repo]

A run starts where the skill is invoked (a `/ai-skills:<skill>` command or a Skill tool call)
and stops at the next slash command, a re-invocation, or after MAX_TURNS human messages.
Writes one plain-text window per run, the skill's text at each version seen, `index.json`,
and prints a JSON summary. Transcripts are data: nothing here follows what they say.
"""

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

PREFIX = "ai-skills"
MAX_TURNS = 4
CMD = re.compile(r"<command-name>/([\w:.-]+)</command-name>")
VERSION = re.compile(r"/ai-skills/(\d+\.\d+\.\d+)/skills/")
# Replies that carry no judgement on the run: an approval, a menu pick, a "go on".
TRIVIAL = re.compile(r"^(go|ok|okay|oui|yes|y|all|tout|continue|merci|thanks|lgtm|vas-y( lance)?|"
                     r"lance|applique tout|apply all|\d{1,2}|[a-z]|👍)[ .!]*$", re.I)
NOISE = ("<local-command", "<task-notification", "<system-reminder", "<bash-", "Another Claude session",
         "Caveat:")


def parse_since(value):
    m = re.fullmatch(r"(\d+)d", value)
    if m:
        return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(m.group(1)))
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc)


def ts_of(d):
    t = d.get("timestamp")
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def blocks(d):
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def human_text(d):
    """The text a person typed, or None for meta, tool results, subagents and harness notices."""
    if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
        return None
    bs = blocks(d)
    if any(b.get("type") == "tool_result" for b in bs):
        return None
    text = " ".join(b.get("text", "") for b in bs if b.get("type") == "text").strip()
    if not text or (text.startswith(NOISE) and "<command-name>" not in text):
        return None
    return text


def short(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def result_text(b):
    c = b.get("content")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c or ""


def invoked(d, skill):
    """True when this line invokes `ai-skills:<skill>`."""
    name = f"{PREFIX}:{skill}"
    if d.get("type") == "assistant" and not d.get("isSidechain"):
        return any(b.get("type") == "tool_use" and b.get("name") == "Skill"
                   and (b.get("input") or {}).get("skill") == name for b in blocks(d))
    h = human_text(d)
    m = CMD.search(h or "")
    return bool(m and m.group(1) == name)


def cut(lines, start, skill):
    """One run from lines[start]: rendered text plus the signals the index keeps."""
    out, reasons = [], set()
    nxt = handoff = version = skill_text = None
    turns, skills_after, last_tool = 0, [], "?"
    for d in lines[start + 1:]:
        if d.get("isSidechain"):
            continue
        if invoked(d, skill):
            break
        if d.get("type") == "user" and d.get("isMeta") and version is None:
            text = " ".join(b.get("text", "") for b in blocks(d) if b.get("type") == "text")
            if text.startswith("Base directory for this skill:"):
                m = VERSION.search(text.split("\n", 1)[0])
                version = m.group(1) if m else "local"
                skill_text = text.split("\n\n", 1)[1] if "\n\n" in text else ""
            continue
        h = human_text(d)
        if h is not None:
            m = CMD.search(h)
            if m:
                handoff = "/" + m.group(1)
                break
            if h.startswith("[Request interrupted"):
                reasons.add("interrupted")
                out.append("[interrupted]")
                continue
            turns += 1
            if nxt is None:
                nxt = short(h, 200)
            if not TRIVIAL.match(h.strip()):
                reasons.add("reply")
            out.append("USER: " + short(h, 1500))
            if turns >= MAX_TURNS:
                break
            continue
        bs = blocks(d)
        # After a reply, the model calling another skill starts a new task: that skill is the handoff.
        later = None
        if turns and d.get("type") == "assistant":
            later = next((b for b in bs if b.get("type") == "tool_use" and b.get("name") == "Skill"), None)
        if later:
            handoff = (later.get("input") or {}).get("skill", "?")
            skills_after.append(handoff)
            break
        for b in bs:
            t = b.get("type")
            if d.get("type") == "assistant" and t == "text" and b.get("text", "").strip():
                out.append("AGENT: " + short(b["text"], 800))
            elif t == "tool_use":
                inp = b.get("input") or {}
                if b.get("name") == "Skill":
                    skills_after.append(inp.get("skill", "?"))
                arg = inp.get("command") or inp.get("skill") or inp.get("file_path") or json.dumps(inp, ensure_ascii=False)
                out.append(f"TOOL CALL {b.get('name')}: {short(arg, 200)}")
                last_tool = b.get("name")
            elif t == "tool_result" and b.get("is_error"):
                reasons.add("tool_error")
                out.append(f"TOOL ERROR ({last_tool}): {short(result_text(b), 400)}")
    return {"text": "\n".join(out), "reasons": sorted(reasons), "next": nxt, "handoff": handoff,
            "version": version or "unknown", "skill_text": skill_text, "skills_after": skills_after}


def version_commits(repo, versions):
    found = {}
    for v in versions:
        if not re.fullmatch(r"\d+\.\d+\.\d+", v):
            continue
        # The release tag first; the `[x.y.z]` in a commit subject for versions released without one.
        for cmd in (["rev-list", "-n", "1", f"v{v}"],
                    ["log", "-1", "--format=%H", "--fixed-strings", "--grep", f"[{v}]"]):
            r = subprocess.run(["git", "-C", repo, *cmd], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                found[v] = r.stdout.strip()
                break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skill")
    ap.add_argument("--since", default="30d")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--out")
    ap.add_argument("--repo")
    ap.add_argument("--no-repo", action="store_true")
    a = ap.parse_args()
    since = parse_since(a.since)
    out_dir = a.out or os.path.expanduser(
        f"~/.claude/skill-dream-state/{a.skill}/{dt.date.today().isoformat()}")
    os.makedirs(os.path.join(out_dir, "windows"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "skill-versions"), exist_ok=True)

    runs = {}  # invocation uuid -> run; a resumed session repeats the uuids of the one it copies
    for path in glob.glob(os.path.join(a.projects, "*", "*.jsonl")):
        try:
            with open(path, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            continue
        for i, d in enumerate(lines):
            if not invoked(d, a.skill):
                continue
            when = ts_of(d)
            if when is None or when < since:
                continue
            run = cut(lines, i, a.skill)
            run.update(uuid=d.get("uuid") or f"{path}:{i}", when=when.isoformat(),
                       session=os.path.basename(path)[:8], project=os.path.basename(os.path.dirname(path)),
                       cwd=next((x.get("cwd") for x in lines if x.get("cwd")), None))
            kept = runs.get(run["uuid"])
            if kept is None or len(run["text"]) > len(kept["text"]):
                runs[run["uuid"]] = run

    ordered = sorted(runs.values(), key=lambda r: r["when"], reverse=True)
    candidates = [r for r in ordered if r["reasons"]]
    read = {r["uuid"] for r in candidates[: a.max]}
    index, versions = [], collections.Counter()
    nexts, handoffs, after = collections.Counter(), collections.Counter(), collections.Counter()
    for n, r in enumerate(ordered):
        versions[r["version"]] += 1
        if r["next"]:
            nexts[r["next"] if len(r["next"]) <= 40 else "<free text>"] += 1
        if r["handoff"]:
            handoffs[r["handoff"]] += 1
        for s in set(r["skills_after"]):
            after[s] += 1
        if r["skill_text"]:
            vpath = os.path.join(out_dir, "skill-versions", f"{r['version']}.md")
            if not os.path.exists(vpath):
                with open(vpath, "w", encoding="utf-8") as f:
                    f.write(r["skill_text"])
        entry = {k: r[k] for k in ("uuid", "when", "session", "project", "cwd", "version", "reasons",
                                   "next", "handoff", "skills_after")}
        entry["candidate"] = r["uuid"] in read
        if entry["candidate"]:
            entry["id"] = f"w{n:03d}-{r['session']}"
            entry["file"] = f"windows/{entry['id']}.txt"
            with open(os.path.join(out_dir, entry["file"]), "w", encoding="utf-8") as f:
                f.write(f"# {a.skill} {r['version']} · {r['when']} · {r['project']}\n\n{r['text']}\n")
        index.append(entry)

    repo = None if a.no_repo else (a.repo or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or None)
    commits = version_commits(repo, versions) if repo else {}
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"skill": a.skill, "since": since.isoformat(), "version_commits": commits, "windows": index},
                  f, ensure_ascii=False, indent=1)

    summary = {
        "skill": a.skill, "since": since.isoformat(), "out": out_dir, "invocations": len(ordered), "candidates": len(read),
        "dropped_candidates": max(0, len(candidates) - a.max),
        "reasons": dict(collections.Counter(x for r in candidates for x in r["reasons"])),
        "versions": dict(versions), "version_commits": commits,
        "next": dict(nexts.most_common(15)), "handoffs": dict(handoffs.most_common(10)),
        "skills_after": dict(after.most_common(10)),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
