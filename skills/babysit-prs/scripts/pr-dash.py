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
import textwrap
import time
import tty
from datetime import datetime


STATUS_LABELS = {
    "ready": "READY",
    "your-call": "YOUR CALL",
    "working": "WORKING",
    "waits": "WAITS",
    "ci": "CI",
    "review": "REVIEW",
    "draft": "DRAFT",
}
COLORS = {
    "READY": "\033[32m",
    "YOUR CALL": "\033[33m",
    "WORKING": "\033[36m",
    "WAITS": "\033[36m",
    "CI": "\033[34m",
    "REVIEW": "\033[35m",
    "DRAFT": "\033[90m",
    "SUCCESS": "\033[32m",
    "FAILURE": "\033[31m",
    "PENDING": "\033[33m",
    "CONFLICTING": "\033[31m",
    "BLOCKED": "\033[31m",
}
RESET = "\033[0m"
ISSUE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
TITLE_PREFIX = re.compile(r"^[a-z]+(?:\([^)]*\))?:\s*", re.IGNORECASE)
TITLE_ISSUE = re.compile(r"\s*\[[A-Z][A-Z0-9]+-\d+\]\s*$")


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


def mergeable(row):
    if row.get("draft"):
        suffix = " (CONFLICTING)" if row.get("mergeable") == "CONFLICTING" else ""
        return f"DRAFT{suffix}"
    if row.get("mergeable") == "CONFLICTING":
        parent = f" on #{row['parent']}" if row.get("parent") else ""
        return f"CONFLICTING{parent}"
    return row.get("merge_state", "UNKNOWN")


def report_cells(row):
    report = row.get("report") or {}
    pushed = report.get("pushed", 0)
    fixed = str(pushed if type(pushed) is int else int(bool(pushed)))
    held = "—"
    if row.get("held"):
        gist = clip(report.get("held_gist") or "decision pending", 180)
        held = f"{row['held']} · {gist}"
    blocked = clip(report.get("blocked"), 140) if report.get("blocked") else "—"
    if (
        blocked != "—"
        and row.get("ci") != "FAILURE"
        and row.get("mergeable") != "CONFLICTING"
    ):
        blocked = "—"
    return fixed, held, blocked


def dashboard_status(number, row, prs, order, running, scanner):
    if number in running:
        return "WORKING"
    if row.get("held"):
        return "YOUR CALL"
    report = row.get("report") or {}
    blocker_is_current = report.get("blocked") and (
        row.get("ci") == "FAILURE" or row.get("mergeable") == "CONFLICTING"
    )
    if blocker_is_current:
        return "REVIEW"
    waiting = scanner.waits_on(row, prs, order, running)
    if waiting is not None:
        return f"WAITS #{waiting}"
    return STATUS_LABELS[scanner.status(row, prs, order, running)]


def rows(state, directory, scanner):
    prs = {int(key): dict(value) for key, value in state.items()}
    if not prs:
        return []
    order = scanner.stacks(prs)
    running = active_agents(directory, prs, scanner.MUTE_TTL)
    output = []
    for number, row in sorted(prs.items()):
        label = dashboard_status(number, row, prs, order, running, scanner)
        humans = row.get("unresolved_human", 0)
        logins = ", ".join(row.get("humans") or [])
        threads = f"{row.get('unresolved_bot', 0)} bot, {humans} humain"
        if humans > 1:
            threads += "s"
        if logins:
            threads += f" ({logins})"
        fixed, held, blocked = report_cells(row)
        output.append(
            [
                f"#{number} {pr_title(row)}",
                issue_key(row),
                label,
                mergeable(row),
                row.get("ci", "NONE"),
                threads,
                fixed,
                held,
                blocked,
            ]
        )
    return output


def widths(columns):
    terminal = max(108, min(220, shutil.get_terminal_size((180, 24)).columns))
    fixed = [None, 9, 10, 13, 9, 14, 5, None, None]
    available = terminal - 28 - sum(value or 0 for value in fixed)
    flexible = [max(14, available * 34 // 100), max(8, available * 36 // 100)]
    flexible.append(max(8, available - sum(flexible)))
    result = []
    flex = iter(flexible)
    for index, value in enumerate(fixed):
        width = value if value is not None else next(flex)
        result.append(max(width, len(columns[index])))
    return result


def wrap(value, width):
    return textwrap.wrap(
        str(value), width=width, break_long_words=True, break_on_hyphens=False
    ) or [""]


def tint(value, column, enabled):
    if not enabled or column not in (2, 3, 4):
        return value
    clean = value.strip()
    if not clean:
        return value
    color = COLORS.get(clean) or COLORS.get(clean.split()[0])
    return f"{color}{value}{RESET}" if color else value


def table(data, color=False):
    columns = [
        "PR",
        "Issue",
        "Status",
        "Mergeable",
        "CI",
        "Threads",
        "Fixed",
        "Held",
        "Blocked",
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
                parts.append(f" {tint(raw.ljust(size), column, color and colored)} ")
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
    sample = {
        "42": {
            "number": 42,
            "url": "https://example.test/42",
            "title": "Fix cart [BOF-42]",
            "draft": False,
            "branch": "fix/BOF-42-cart",
            "base": "dev",
            "parent": None,
            "merge_state": "BLOCKED",
            "mergeable": "MERGEABLE",
            "ci": "FAILURE",
            "unresolved_bot": 0,
            "unresolved_human": 1,
            "held": 0,
            "humans": ["reviewer"],
            "report": {"pushed": 1, "blocked": "failing e2e"},
        }
    }
    rendered = rows(sample, "/missing", scanner)[0]
    assert rendered[1:7] == [
        "BOF-42",
        "REVIEW",
        "BLOCKED",
        "FAILURE",
        "0 bot, 1 humain (reviewer)",
        "1",
    ]
    assert rendered[8] == "failing e2e"
    assert "#42 Fix cart" in table([rendered])
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
