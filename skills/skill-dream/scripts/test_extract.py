#!/usr/bin/env python3
"""Self-check for extract.py. Run: python3 scripts/test_extract.py

Builds a fake ~/.claude/projects tree from real-shaped JSONL lines and runs the script on it.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "extract.py"

BASE = "/Users/x/.claude/plugins/cache/bgelis-ai-skills/ai-skills/1.79.0/skills/investigate"


def human(uuid, ts, text):
    return {"type": "user", "uuid": uuid, "timestamp": ts, "sessionId": "s", "cwd": "/repo",
            "message": {"role": "user", "content": text}}


def meta(uuid, ts, text):
    return {"type": "user", "uuid": uuid, "timestamp": ts, "isMeta": True,
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def assistant(uuid, ts, *blocks, sidechain=False):
    return {"type": "assistant", "uuid": uuid, "timestamp": ts, "isSidechain": sidechain,
            "message": {"role": "assistant", "content": list(blocks)}}


def tool_result(uuid, ts, tid, text, error):
    return {"type": "user", "uuid": uuid, "timestamp": ts,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]}}


def cmd(name, args=""):
    return (f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>\n"
            f"<command-args>{args}</command-args>")


SESSION_A = [
    {"type": "mode"},
    human("a1", "2026-11-01T10:00:00Z", cmd("ai-skills:investigate", "BOF-1")),
    meta("a2", "2026-11-01T10:00:01Z", f"Base directory for this skill: {BASE}\n\n# Investigate\n\nStep 1. Read the ticket."),
    assistant("a3", "2026-11-01T10:00:02Z", {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "linear issue view BOF-1"}}),
    tool_result("a4", "2026-11-01T10:00:03Z", "t1", "linear: command not found", True),
    # A skill the run calls before anyone replies is part of the run.
    assistant("a5", "2026-11-01T10:00:04Z", {"type": "tool_use", "id": "t2", "name": "Skill", "input": {"skill": "ai-skills:humanizer"}},
              {"type": "text", "text": "Root cause: the cache."}),
    assistant("a5b", "2026-11-01T10:00:04Z", {"type": "text", "text": "subagent noise"}, sidechain=True),
    human("a6", "2026-11-01T10:01:00Z", "pourquoi tu n'as pas vérifié ?"),
    human("a8", "2026-11-01T10:02:00Z", "[Request interrupted by user]"),
    human("a9", "2026-11-01T10:03:00Z", cmd("ai-skills:pr-respond")),
    human("a10", "2026-11-01T10:04:00Z", "after the window"),
    # Second run, invoked by the model, answered with a bare "go": not a candidate.
    assistant("b1", "2026-11-02T09:00:00Z", {"type": "tool_use", "id": "t3", "name": "Skill", "input": {"skill": "ai-skills:investigate"}}),
    meta("b2", "2026-11-02T09:00:01Z", f"Base directory for this skill: {BASE.replace('1.79.0', '1.86.0')}\n\n# Investigate v2"),
    assistant("b3", "2026-11-02T09:00:02Z", {"type": "text", "text": "Done."}),
    human("b4", "2026-11-02T09:01:00Z", "go"),
    # After a reply, another skill is a new task: the run ends, and the skill is its handoff.
    assistant("b5", "2026-11-02T09:01:05Z", {"type": "tool_use", "id": "t4", "name": "Skill", "input": {"skill": "ai-skills:pr-respond"}}),
    tool_result("b6", "2026-11-02T09:01:06Z", "t4", "red test, as expected", True),
]

# A resumed copy of session A carries the same message uuids: it must not count twice.
SESSION_FORK = SESSION_A[:6]

# An invocation older than --since.
SESSION_OLD = [
    human("o1", "2026-01-01T10:00:00Z", cmd("ai-skills:investigate")),
    human("o2", "2026-01-01T10:01:00Z", "wrong again"),
]

# Another plugin's skill of the same name is not ours.
SESSION_OTHER = [
    human("x1", "2026-11-01T10:00:00Z", cmd("other:investigate")),
    human("x2", "2026-11-01T10:01:00Z", "should be ignored"),
]


def write(dirpath, name, lines):
    with open(dirpath / name, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def run():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj = tmp / "projects" / "-repo"
        proj.mkdir(parents=True)
        write(proj, "aaaaaaaa-1.jsonl", SESSION_A)
        write(proj, "ffffffff-2.jsonl", SESSION_FORK)
        write(proj, "oooooooo-3.jsonl", SESSION_OLD)
        write(proj, "xxxxxxxx-4.jsonl", SESSION_OTHER)
        out = tmp / "out"
        res = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "investigate", "--projects", str(tmp / "projects"),
             "--out", str(out), "--since", "2026-10-01", "--no-repo"],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        summary = json.loads(res.stdout)
        index = json.loads((out / "index.json").read_text())
        wins = index["windows"]

        assert summary["invocations"] == 2, summary
        assert summary["candidates"] == 1, summary
        assert summary["versions"] == {"1.79.0": 1, "1.86.0": 1}, summary

        first = next(w for w in wins if w["version"] == "1.79.0")
        assert first["candidate"] is True
        assert set(first["reasons"]) == {"reply", "tool_error", "interrupted"}, first["reasons"]
        assert first["next"] == "pourquoi tu n'as pas vérifié ?", first["next"]
        assert first["handoff"] == "/ai-skills:pr-respond", first["handoff"]
        assert "ai-skills:humanizer" in first["skills_after"]

        text = (out / first["file"]).read_text()
        assert "USER: pourquoi tu n'as pas vérifié ?" in text
        assert "TOOL ERROR (Bash): linear: command not found" in text
        assert "AGENT: Root cause: the cache." in text
        assert "[interrupted]" in text
        assert "subagent noise" not in text
        assert "after the window" not in text

        second = next(w for w in wins if w["version"] == "1.86.0")
        assert second["candidate"] is False and second["next"] == "go"
        assert second["handoff"] == "ai-skills:pr-respond" and second["reasons"] == [], second

        assert (out / "skill-versions" / "1.79.0.md").read_text().startswith("# Investigate")
        assert summary["next"]["go"] == 1
        assert summary["handoffs"] == {"/ai-skills:pr-respond": 1, "ai-skills:pr-respond": 1}, summary["handoffs"]
    print("ok")


if __name__ == "__main__":
    run()
