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


def thread_summary(row, expected_schema):
    fields = (
        "threads_bot_open",
        "threads_bot_closed",
        "threads_human_open",
        "threads_human_closed",
    )
    if row.get("schema_version") != expected_schema or not all(
        key in row for key in fields
    ):
        return "⚠ scanner outdated"
    bot_open = row.get(
        "threads_bot_open", row.get("unresolved_bot", 0) + row.get("held", 0)
    )
    bot_closed = row.get("threads_bot_closed", 0)
    human_open = row.get("threads_human_open", row.get("unresolved_human", 0))
    human_closed = row.get("threads_human_closed", 0)
    human = f"👤 {human_open} open · {human_closed} closed"
    logins = ", ".join(row.get("humans") or [])
    if logins:
        human += f" ({logins})"
    return f"🤖 {bot_open} open · {bot_closed} closed\n{human}"


def stack_layout(prs, order):
    output = []
    stack_number = 0
    groups = {tuple(members): None for members in order.values()}
    for members in sorted(groups, key=min):
        if len(members) == 1:
            output.append((members[0], "◆ SINGLE"))
            continue
        stack_number += 1
        # Head first: the PR on top of the stack reads at the top, the one on the trunk at the
        # bottom — the way the branches sit.
        for index, number in enumerate(reversed(members)):
            role = "├ MID"
            if index == 0:
                role = "╭ HEAD"
            elif index == len(members) - 1:
                role = "╰ BASE"
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


def with_drafts(state, scanner):
    """Drafts the scan filtered out, fetched for display only — state is never written."""
    missing = [n for n in scanner.open_prs(include_drafts=True) if str(n) not in state]
    merged = dict(state)
    for number, raw in scanner.fetch_raw(missing).items():
        merged[str(number)] = dict(
            scanner.row(raw, {}),
            schema_version=scanner.STATE_SCHEMA_VERSION,
            report=None,
        )
    scanner.link_stack({int(key): value for key, value in merged.items()})
    return merged


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
        output.append(
            [
                clip(row.get("branch") or "—", 22),
                stack,
                Cell(f"#{number} {pr_title(row)}", row.get("url")),
                Cell(
                    issue, None if issue == "—" else f"https://linear.app/issue/{issue}"
                ),
                diff_size(row),
                label,
                "🤖 ACTIVE" if number in running else "·",
                ci_status(row),
                merge_status(row),
                thread_summary(row, scanner.STATE_SCHEMA_VERSION),
                note(row),
            ]
        )
    return output


def diff_size(row):
    """Size of the change: `+adds −dels · Nf`, or `—` when the scanner knew no diff fields."""
    additions = row.get("additions")
    if type(additions) is not int:
        return "—"
    deletions = row.get("deletions", 0)
    files = row.get("files", 0)
    return f"+{additions} −{deletions} · {files}f"


def widths(columns):
    terminal = max(133, min(220, shutil.get_terminal_size((180, 24)).columns))
    fixed = [22, 11, None, 9, 13, 15, 9, 8, 11, 20, None]
    available = terminal - 30 - sum(value or 0 for value in fixed)
    flexible = [max(12, available * 44 // 100), max(10, available * 56 // 100)]
    result = []
    flex = iter(flexible)
    for index, value in enumerate(fixed):
        width = value if value is not None else next(flex)
        result.append(max(width, len(columns[index])))
    return result


def wrap(value, width):
    text = value.text if isinstance(value, Cell) else str(value)
    lines = []
    for part in text.splitlines() or [""]:
        lines.extend(wrap_line(part, width))
    return lines


def wrap_line(text, width):
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
    if column == 1:
        match = re.match(r"S(\d+)", clean)
        if not match:
            return f"\033[90m{value}{RESET}"
        color = STACK_COLORS[(int(match.group(1)) - 1) % len(STACK_COLORS)]
        return f"{color}{value}{RESET}"
    semantic_columns = (5, 6, 7, 8)
    if column not in semantic_columns:
        return value
    color = next((color for key, color in COLORS.items() if key in clean), None)
    return f"{color}{value}{RESET}" if color else value


def table(data, color=False):
    columns = [
        "Branch",
        "Stack",
        "PR",
        "Issue",
        "Diff",
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


def snapshot(directory, repo, scanner, color=False, drafts=False):
    state, path = load_state(directory)
    if drafts:
        state = with_drafts(state, scanner)
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


def refresh(directory):
    """One scanner pass, on demand: the same pass `babysit-scan.py --watch` runs every 60
    seconds, without the watcher. It writes state; the redraw follows from the state moving.
    Returns a hint line when no pass can run here, else None.

    The scanner derives its state dir from the checkout it runs in, so this only works from
    the watched repo's checkout — the same place the dashboard resolves its own state dir.
    """
    script = os.path.join(os.path.dirname(os.path.realpath(__file__)), "babysit-scan.py")
    try:
        here = repository()
    except RuntimeError:
        return "r: refresh needs the repo checkout as cwd"
    if here.replace("/", "_") != os.path.basename(directory):
        return f"r: cwd is {here}, not the repo this dashboard watches"
    process = subprocess.run(
        (sys.executable, script), capture_output=True, text=True
    )
    if process.returncode:
        return "r: scan pass failed — run babysit-prs to see why"
    return None


def watch(directory, repo, scanner, drafts=False):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("--watch requires an interactive terminal")
    original = termios.tcgetattr(sys.stdin)
    previous = None
    hint = None
    try:
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write("\033[?1049h\033[?25l")
        while True:
            current = signature(directory)
            if current != previous:
                content = snapshot(directory, repo, scanner, color=True, drafts=drafts)
                footer = f"{hint}\n" if hint else ""
                sys.stdout.write(f"\033[H\033[2J{content}\n{footer}r refresh · q quit\n")
                sys.stdout.flush()
                previous = current
                hint = None
            readable, _, _ = select.select([sys.stdin], [], [], 0.25)
            if not readable:
                continue
            key = sys.stdin.read(1).lower()
            if key == "q":
                break
            if key == "r":
                hint = refresh(directory)
                previous = None  # a failed pass wrote nothing; its message still owes a redraw
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
        "threads_bot_open": 0,
        "threads_bot_closed": 0,
        "threads_human_open": 0,
        "threads_human_closed": 0,
        "held": 0,
        "humans": [],
        "report": None,
        "schema_version": scanner.STATE_SCHEMA_VERSION,
    }
    sample = {
        "42": dict(
            base,
            number=42,
            title="Fix cart [BOF-42]",
            branch="fix/BOF-42-cart",
            parent=None,
            threads_bot_closed=5,
            threads_human_closed=2,
            report={"pushed": 1, "blocked": "failing e2e"},
        ),
        "43": dict(
            base,
            number=43,
            title="Wire cart [BOF-43]",
            branch="fix/BOF-43-cart",
            parent=42,
            ci="PENDING",
            threads_bot_open=1,
            threads_bot_closed=2,
            threads_human_closed=1,
        ),
        "44": dict(
            base,
            number=44,
            title="Finish cart [BOF-44]",
            branch="fix/BOF-44-cart",
            parent=43,
            ci="SUCCESS",
            merge_state="CLEAN",
            additions=120,
            deletions=8,
            files=6,
        ),
        "45": dict(
            base,
            number=45,
            title="Reprice cart [BOF-45]",
            branch="fix/BOF-45-cart",
            parent=44,
            stack=17312,
            stack_pos=1,
            ci="SUCCESS",
            merge_state="CLEAN",
        ),
        "46": dict(
            base,
            number=46,
            title="Ship cart [BOF-46]",
            branch="fix/BOF-46-cart",
            parent=45,
            stack=17312,
            stack_pos=2,
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

    # Head first inside a stack, and the stack `gh stack` opened on top of the chain stays its own
    # — the base link alone would read all five PRs as one.
    assert [row[1] for row in rendered] == [
        "S1 ╭ HEAD",
        "S1 ├ MID",
        "S1 ╰ BASE",
        "S2 ╭ HEAD",
        "S2 ╰ BASE",
        "◆ SINGLE",
    ]
    assert [row[2].text.split()[0] for row in rendered] == [
        "#44",
        "#43",
        "#42",
        "#46",
        "#45",
        "#99",
    ]
    shown = {row[2].text.split()[0]: row for row in rendered}
    assert shown["#42"][0] == "fix/BOF-42-cart"
    assert shown["#42"][3].text == "BOF-42"
    assert shown["#42"][4] == "—", "state without diff fields reads as no size"
    assert shown["#42"][5:] == [
        "👀 REVIEW",
        "·",
        "❌ FAIL",
        "⛔ BLOCKED",
        "🤖 0 open · 5 closed\n👤 0 open · 2 closed",
        "✓ 1 fixed · ⛔ failing e2e",
    ]
    assert shown["#43"][5:9] == [
        "🔧 WORKING",
        "🤖 ACTIVE",
        "⏳ RUN",
        "⛔ BLOCKED",
    ]
    assert shown["#43"][9] == "🤖 1 open · 2 closed\n👤 0 open · 1 closed"
    assert (
        thread_summary({"unresolved_bot": 3}, scanner.STATE_SCHEMA_VERSION)
        == "⚠ scanner outdated"
    )
    assert diff_size({"additions": 12, "deletions": 3, "files": 4}) == "+12 −3 · 4f"
    assert diff_size({"additions": "12"}) == "—", "a non-int is pre-schema state, not a size"
    assert shown["#44"][4] == "+120 −8 · 6f"
    assert shown["#44"][5] == "✅ READY"
    assert shown["#99"][5:9] == ["📝 DRAFT", "·", "· NONE", "📝 DRAFT"]
    class DraftScanner:
        STATE_SCHEMA_VERSION = scanner.STATE_SCHEMA_VERSION
        link_stack = staticmethod(scanner.link_stack)

        @staticmethod
        def open_prs(include_drafts=False):
            return [42, 43, 44, 45, 46, 99, 100]

        @staticmethod
        def fetch_raw(numbers):
            assert numbers == [100], numbers
            return {100: {"number": 100}}

        @staticmethod
        def row(raw, seen):
            return dict(base, number=raw["number"], title="Draft top",
                        branch="d", base="fix/BOF-44-cart", draft=True,
                        merge_state="DRAFT")

    merged = with_drafts(sample, DraftScanner)
    assert set(merged) == {"42", "43", "44", "45", "46", "99", "100"}
    assert merged["100"]["parent"] == 44, merged["100"]
    assert merged["100"]["report"] is None
    assert sample.keys() == {"42", "43", "44", "45", "46", "99"}, "drafts stay out of state"

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
    status.add_argument(
        "--drafts", action="store_true", help="also show draft PRs the scan skipped"
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
            watch(directory, repo, scanner, args.drafts)
        else:
            print(
                snapshot(
                    directory,
                    repo,
                    scanner,
                    color=sys.stdout.isatty(),
                    drafts=args.drafts,
                )
            )
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError) as error:
        print(f"pr-dash: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
