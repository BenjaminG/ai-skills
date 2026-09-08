#!/usr/bin/env python3
"""Read-only terminal dashboard for babysit-prs state."""

import argparse
import importlib.util
import json
import os
import re
import select
import shutil
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from dataclasses import dataclass
from datetime import datetime


STATUS_LABELS = {
    "ready": "✅ READY",
    "your-call": "🙋 YOUR CALL",
    "working": "🔧 TODO",
    "waits": "⏳ WAITS",
    "ci": "🧪 CI",
    "review": "👀 REVIEW",
    "draft": "📝 DRAFT",
}
COLORS = {
    "READY": "\033[32m",
    "YOUR CALL": "\033[33m",
    "WORKING": "\033[36m",
    "WAITS": "\033[36m",
    "CI": "\033[34m",
    "TODO": "\033[33m",
    "ACTIVE": "\033[36m",
    "PASS": "\033[32m",
    "FAIL": "\033[31m",
    "RUN": "\033[33m",
    "CLEAN": "\033[32m",
    "CONFLICT": "\033[31m",
    "BEHIND": "\033[33m",
    "REVIEW": "\033[35m",
    "DRAFT": "\033[90m",
    "BLOCKED": "\033[31m",
}
STACK_COLORS = [
    "\033[38;5;117m",
    "\033[38;5;183m",
    "\033[38;5;81m",
    "\033[38;5;215m",
    "\033[38;5;150m",
    "\033[38;5;147m",
]
RESET = "\033[0m"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
OSC8 = re.compile(r"\x1b\]8;;.*?\x1b\\")
ISSUE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
TITLE_PREFIX = re.compile(r"^[a-z]+(?:\([^)]*\))?:\s*", re.IGNORECASE)
TITLE_ISSUE = re.compile(r"\s*\[[A-Z][A-Z0-9]+-\d+\]\s*$")


@dataclass(frozen=True)
class Cell:
    text: str
    url: str = None


def scanner_module():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "babysit-scan.py")
    spec = importlib.util.spec_from_file_location("babysit_scan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repository():
    process = subprocess.run(
        ("git", "config", "--get", "remote.origin.url"),
        capture_output=True,
        text=True,
    )
    if process.returncode:
        raise RuntimeError("cannot resolve repository; run from its checkout")
    remote = process.stdout.strip().removesuffix(".git")
    if "github.com:" in remote:
        slug = remote.rsplit("github.com:", 1)[1]
    elif "github.com/" in remote:
        slug = remote.rsplit("github.com/", 1)[1]
    else:
        raise RuntimeError("origin is not a GitHub repository")
    if slug.count("/") != 1:
        raise RuntimeError("cannot resolve GitHub owner/repository")
    return slug


def resolve_state_dir(explicit=None):
    if explicit:
        return os.path.expanduser(explicit), None
    repo = repository()
    directory = os.path.join(
        os.path.expanduser("~"), ".claude", "babysit-state", repo.replace("/", "_")
    )
    return directory, repo


def load_state(directory):
    path = os.path.join(directory, "state.json")
    try:
        with open(path) as handle:
            state = json.load(handle)
    except FileNotFoundError:
        raise RuntimeError("no babysit state; start babysit-prs first")
    except json.JSONDecodeError:
        raise RuntimeError("babysit state is unreadable; wait for the next scan")
    if not isinstance(state, dict):
        raise RuntimeError("babysit state has an invalid shape")
    return state, path


def active_agents(directory, numbers, ttl):
    now = time.time()
    running = set()
    for number in numbers:
        path = os.path.join(directory, f"{number}.muted")
        try:
            if now - os.path.getmtime(path) <= ttl:
                running.add(number)
        except OSError:
            pass
    return running


def issue_key(row):
    match = ISSUE.search(f"{row.get('branch', '')} {row.get('title', '')}")
    return match.group(0) if match else "—"


def pr_title(row):
    title = TITLE_PREFIX.sub("", row.get("title", ""))
    return TITLE_ISSUE.sub("", title)


def clip(value, limit):
    value = str(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def ci_status(row):
    return {
        "SUCCESS": "✅ PASS",
        "FAILURE": "❌ FAIL",
        "PENDING": "⏳ RUN",
        "NONE": "· NONE",
    }.get(row.get("ci"), f"? {row.get('ci', 'NONE')}")


def merge_status(row):
    if row.get("mergeable") == "CONFLICTING":
        return "💥 CONFLICT"
    return {
        "CLEAN": "✅ CLEAN",
        "BLOCKED": "⛔ BLOCKED",
        "BEHIND": "↩ BEHIND",
        "DIRTY": "💥 CONFLICT",
        "DRAFT": "📝 DRAFT",
    }.get(row.get("merge_state"), f"? {row.get('merge_state', 'UNKNOWN')}")


def fixed_count(report):
    pushed = report.get("pushed", 0)
    return pushed if type(pushed) is int else int(bool(pushed))


def note(row):
    report = row.get("report") or {}
    parts = []
    fixed = fixed_count(report)
    if fixed:
        parts.append(f"✓ {fixed} fixed")
    if row.get("held"):
        gist = clip(report.get("held_gist") or "decision pending", 180)
        parts.append(f"🙋 {row['held']} · {gist}")
    blocked = clip(report.get("blocked"), 140) if report.get("blocked") else "—"
    if (
        blocked != "—"
        and row.get("ci") != "FAILURE"
        and row.get("mergeable") != "CONFLICTING"
    ):
        blocked = "—"
    if blocked != "—":
        parts.append(f"⛔ {blocked}")
    return " · ".join(parts) or "—"


def stack_layout(prs, order):
    children = {number: [] for number in prs}
    for number, row in prs.items():
        parent = row.get("parent")
        if parent in children:
            children[parent].append(number)

    groups = {}
    for members in order.values():
        groups.setdefault(tuple(members), None)

    output = []
    stack_number = 0
    for members in sorted(groups, key=lambda item: item[0]):
        if len(members) == 1:
            output.append((members[0], "◆ SINGLE"))
            continue
        stack_number += 1
        for number in members:
            if prs[number].get("parent") not in prs:
                role = "╭ BASE"
            elif not children[number]:
                role = "╰ HEAD"
            else:
                role = "├ MID"
            output.append((number, f"S{stack_number} {role}"))
    return output


def dashboard_status(number, row, prs, order, running, scanner):
    if number in running:
        return "🔧 WORKING"
    if row.get("held"):
        return "🙋 YOUR CALL"
    report = row.get("report") or {}
    blocker_is_current = report.get("blocked") and (
        row.get("ci") == "FAILURE" or row.get("mergeable") == "CONFLICTING"
    )
    if blocker_is_current:
        return "👀 REVIEW"
    status = scanner.status(row, prs, order, running)
    if status == "waits":
        return f"⏳ WAITS #{scanner.waits_on(row, prs, order, running)}"
    return STATUS_LABELS[status]


def rows(state, directory, scanner):
    prs = {int(key): dict(value) for key, value in state.items()}
    if not prs:
        return []
    order = scanner.stacks(prs)
    running = active_agents(directory, prs, scanner.MUTE_TTL)
    output = []
    for number, stack in stack_layout(prs, order):
        row = prs[number]
        issue = issue_key(row)
        label = dashboard_status(number, row, prs, order, running, scanner)
        humans = row.get("unresolved_human", 0)
        logins = ", ".join(row.get("humans") or [])
        threads = f"{row.get('unresolved_bot', 0)} bot, {humans} humain"
        if humans > 1:
            threads += "s"
        if logins:
            threads += f" ({logins})"
        output.append(
            [
                stack,
                Cell(f"#{number} {pr_title(row)}", row.get("url")),
                Cell(
                    issue, None if issue == "—" else f"https://linear.app/issue/{issue}"
                ),
                label,
                "🤖 ACTIVE" if number in running else "·",
                ci_status(row),
                merge_status(row),
                threads,
                note(row),
            ]
        )
    return output


def widths(columns):
    terminal = max(116, min(220, shutil.get_terminal_size((180, 24)).columns))
    fixed = [11, None, 9, 15, 9, 8, 11, 14, None]
    available = terminal - 28 - sum(value or 0 for value in fixed)
    flexible = [max(12, available * 44 // 100), max(10, available * 56 // 100)]
    result = []
    flex = iter(flexible)
    for index, value in enumerate(fixed):
        width = value if value is not None else next(flex)
        result.append(max(width, len(columns[index])))
    return result


def wrap(value, width):
    text = value.text if isinstance(value, Cell) else str(value)
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if display_width(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        while display_width(word) > width:
            piece, word = split_at_width(word, width)
            lines.append(piece)
        current = word
    if current:
        lines.append(current)
    return lines


def character_width(character):
    if unicodedata.category(character).startswith(("C", "M")):
        return 0
    return 2 if unicodedata.east_asian_width(character) in ("W", "F") else 1


def display_width(value):
    plain = ANSI.sub("", OSC8.sub("", value))
    return sum(character_width(character) for character in plain)


def split_at_width(value, width):
    used = 0
    for index, character in enumerate(value):
        size = character_width(character)
        if used + size > width:
            return value[:index], value[index:]
        used += size
    return value, ""


def pad(value, width):
    return value + " " * max(0, width - display_width(value))


def hyperlink(value, url, enabled):
    if not enabled or not url:
        return value
    return f"\033]8;;{url}\033\\{value}\033]8;;\033\\"


def tint(value, column, enabled):
    if not enabled:
        return value
    clean = value.strip()
    if not clean:
        return value
    if column == 0:
        match = re.match(r"S(\d+)", clean)
        if not match:
            return f"\033[90m{value}{RESET}"
        color = STACK_COLORS[(int(match.group(1)) - 1) % len(STACK_COLORS)]
        return f"{color}{value}{RESET}"
    semantic_columns = (3, 4, 5, 6)
    if column not in semantic_columns:
        return value
    color = next((color for key, color in COLORS.items() if key in clean), None)
    return f"{color}{value}{RESET}" if color else value


def table(data, color=False):
    columns = [
        "Stack",
        "PR",
        "Issue",
        "Status",
        "Agent",
        "CI",
        "Merge",
        "Threads",
        "Note",
    ]
    sizes = widths(columns)
    top = "┌" + "┬".join("─" * (size + 2) for size in sizes) + "┐"
    middle = "├" + "┼".join("─" * (size + 2) for size in sizes) + "┤"
    bottom = "└" + "┴".join("─" * (size + 2) for size in sizes) + "┘"

    def render(values, colored=True):
        cells = [wrap(value, size) for value, size in zip(values, sizes)]
        height = max(len(cell) for cell in cells)
        lines = []
        for line in range(height):
            parts = []
            for column, (cell, size) in enumerate(zip(cells, sizes)):
                raw = cell[line] if line < len(cell) else ""
                styled = tint(pad(raw, size), column, color and colored)
                source = values[column]
                url = source.url if raw and isinstance(source, Cell) else None
                parts.append(f" {hyperlink(styled, url, color and colored)} ")
            lines.append("│" + "│".join(parts) + "│")
        return lines

    output = [top, *render(columns, colored=False), middle]
    values = data or [["No open PRs"] + [""] * (len(columns) - 1)]
    for index, row in enumerate(values):
        output.extend(render(row))
        if index < len(values) - 1:
            output.append(middle)
    output.append(bottom)
    return "\n".join(output)


def snapshot(directory, repo, scanner, color=False):
    state, path = load_state(directory)
    updated = (
        datetime.fromtimestamp(os.path.getmtime(path)).astimezone().strftime("%H:%M:%S")
    )
    name = repo or os.path.basename(directory).replace("_", "/", 1)
    return f"pr-dash · {name} · updated {updated}\n{table(rows(state, directory, scanner), color)}"


def signature(directory):
    names = ["state.json"]
    try:
        names.extend(
            entry.name
            for entry in os.scandir(directory)
            if entry.name.endswith(".muted")
        )
    except OSError:
        pass
    values = []
    for name in sorted(names):
        path = os.path.join(directory, name)
        try:
            stat = os.stat(path)
            values.append((name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            values.append((name, None, None))
    return tuple(values), shutil.get_terminal_size((180, 24)).columns


def watch(directory, repo, scanner):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("--watch requires an interactive terminal")
    original = termios.tcgetattr(sys.stdin)
    previous = None
    try:
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write("\033[?1049h\033[?25l")
        while True:
            current = signature(directory)
            if current != previous:
                content = snapshot(directory, repo, scanner, color=True)
                sys.stdout.write(f"\033[H\033[2J{content}\nq quit\n")
                sys.stdout.flush()
                previous = current
            readable, _, _ = select.select([sys.stdin], [], [], 0.25)
            if readable and sys.stdin.read(1).lower() == "q":
                break
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original)
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def self_check(scanner):
    import tempfile

    base = {
        "url": "https://example.test/42",
        "draft": False,
        "base": "dev",
        "merge_state": "BLOCKED",
        "mergeable": "MERGEABLE",
        "ci": "FAILURE",
        "unresolved_bot": 0,
        "unresolved_human": 0,
        "held": 0,
        "humans": [],
        "report": None,
    }
    sample = {
        "42": dict(
            base,
            number=42,
            title="Fix cart [BOF-42]",
            branch="fix/BOF-42-cart",
            parent=None,
            report={"pushed": 1, "blocked": "failing e2e"},
        ),
        "43": dict(
            base,
            number=43,
            title="Wire cart [BOF-43]",
            branch="fix/BOF-43-cart",
            parent=42,
            ci="PENDING",
        ),
        "44": dict(
            base,
            number=44,
            title="Finish cart [BOF-44]",
            branch="fix/BOF-44-cart",
            parent=43,
            ci="SUCCESS",
            merge_state="CLEAN",
        ),
        "99": dict(
            base,
            number=99,
            title="Draft report [BOF-99]",
            branch="feat/BOF-99-report",
            parent=None,
            draft=True,
            ci="NONE",
            merge_state="DRAFT",
        ),
    }
    with tempfile.TemporaryDirectory() as directory:
        open(os.path.join(directory, "43.muted"), "w").close()
        rendered = rows(sample, directory, scanner)

    assert [row[0] for row in rendered] == [
        "S1 ╭ BASE",
        "S1 ├ MID",
        "S1 ╰ HEAD",
        "◆ SINGLE",
    ]
    assert rendered[0][2].text == "BOF-42"
    assert rendered[0][3:] == [
        "👀 REVIEW",
        "·",
        "❌ FAIL",
        "⛔ BLOCKED",
        "0 bot, 0 humain",
        "✓ 1 fixed · ⛔ failing e2e",
    ]
    assert rendered[1][3:7] == [
        "🔧 WORKING",
        "🤖 ACTIVE",
        "⏳ RUN",
        "⛔ BLOCKED",
    ]
    assert rendered[2][3] == "✅ READY"
    assert rendered[3][3:7] == ["📝 DRAFT", "·", "· NONE", "📝 DRAFT"]
    colored = table(rendered, color=True)
    line_widths = {display_width(line) for line in colored.splitlines()}
    assert len(line_widths) == 1, line_widths
    assert "#42 Fix cart" in colored
    assert "\033]8;;https://example.test/42" in colored
    assert "\033]8;;https://linear.app/issue/BOF-42" in colored
    assert "No open PRs" in table([], color=True)
    print("self-check ok")


def parser():
    command = argparse.ArgumentParser(prog="pr-dash")
    command.add_argument("--state-dir", help=argparse.SUPPRESS)
    command.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    actions = command.add_subparsers(dest="command")
    status = actions.add_parser("status", help="show babysit-prs state")
    status.add_argument(
        "--watch", action="store_true", help="redraw when state changes"
    )
    return command


def main():
    args = parser().parse_args()
    scanner = scanner_module()
    if args.self_check:
        self_check(scanner)
        return
    if args.command != "status":
        parser().error("the following arguments are required: command")
    try:
        directory, repo = resolve_state_dir(args.state_dir)
        if args.watch:
            watch(directory, repo, scanner)
        else:
            print(snapshot(directory, repo, scanner, color=sys.stdout.isatty()))
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError) as error:
        print(f"pr-dash: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
