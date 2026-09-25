#!/usr/bin/env python3
"""Collect and deterministically gate a manual Naboo PR risk assessment."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil

# All subprocess calls use fixed executable paths and argv lists without a shell.
import subprocess  # nosec B404
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY = "naboo-team/naboo"
POLICY_VERSION = "naboo-v0.1"
RUNNER_VERSION = "manual-skill-v1"
LOW_RISK_SCORE_LIMIT = 40
MAX_REVIEWABLE_FILES = 50
MAX_REVIEWABLE_CHANGED_LINES = 2_000
MAX_GRAPHQL_PAGES = 20

DIMENSIONS = {
    "businessImpact": {
        "allowed": [0, 10, 20, 30],
        "levels": {
            "0": "No runtime or user-visible consequence.",
            "10": "Local behavior or display change.",
            "20": "Booking, quote, notification, or domain-write consequence.",
            "30": "Money, tax, currency, identity, permission, or sensitive-data consequence.",
        },
    },
    "blastRadius": {
        "allowed": [0, 5, 10, 20],
        "levels": {
            "0": "No runtime surface.",
            "5": "One local component and at most three production files.",
            "10": "One broad app or two apps.",
            "20": "Three or more apps, a shared library, or multiple domains.",
        },
    },
    "contractsAndState": {
        "allowed": [0, 5, 10, 20],
        "levels": {
            "0": "No contract or state change.",
            "5": "Compatible internal behavior.",
            "10": "Additive contract or state.",
            "20": "Changed compatibility, persistence semantics, or migration.",
        },
    },
    "operationalRisk": {
        "allowed": [0, 5, 10, 15],
        "levels": {
            "0": "Plain code revert with no durable effect.",
            "5": "Verified compatibility and simple rollback.",
            "10": "Runtime dependency, build, deploy, retry, cache, or external service.",
            "15": "Durable external effect or hard rollback.",
        },
    },
    "verificationGap": {
        "allowed": [0, 5, 10, 15],
        "levels": {
            "0": "Exact changed behavior is proven.",
            "5": "Exact path is covered with partial edge coverage.",
            "10": "Only indirect or adjacent proof exists.",
            "15": "Changed behavior lacks relevant proof.",
        },
    },
}

HUMAN_ONLY_SURFACES = {
    "iam_auth",
    "finance_billing",
    "migration_backfill",
    "secrets_encryption_privacy",
    "infrastructure_workflow",
    "approval_policy",
    "codeowners_agent_instructions",
}

HUMAN_ONLY_PATHS = [
    (
        "approval_policy",
        re.compile(r"^\.github/(?:rulesets/|restricted-label-owners\.txt$)"),
    ),
    (
        "codeowners_agent_instructions",
        re.compile(
            r"(?:^|/)(?:CODEOWNERS|AGENTS\.md|CLAUDE\.md)$|^\.(?:claude|cursor)/"
        ),
    ),
    (
        "infrastructure_workflow",
        re.compile(r"^\.github/(?:workflows|scripts)/|^cd/"),
    ),
    (
        "migration_backfill",
        re.compile(r"(?:^|/)(?:migrations?|backfills?)(?:/|\.|-)", re.IGNORECASE),
    ),
    (
        "iam_auth",
        re.compile(
            r"(?:^|/)(?:auth|authentication|authorization|permissions?|guards?)(?:/|\.|-)",
            re.IGNORECASE,
        ),
    ),
    (
        "finance_billing",
        re.compile(
            r"(?:^|/)(?:fintech|finance|funding-orchestration|payments?|payouts?|billing|invoices?|prices?|currency|tax)(?:/|\.|-)",
            re.IGNORECASE,
        ),
    ),
    (
        "secrets_encryption_privacy",
        re.compile(r"(?:^|/)(?:secrets?|encryption|privacy)(?:/|\.|-)", re.IGNORECASE),
    ),
]

ASSESSMENT_KEYS = {
    "dimensions",
    "humanOnlySurfaces",
    "exactPathEvidence",
    "evidence",
    "findings",
    "unknowns",
    "explanation",
}

FINDING_SEVERITIES = ["HIGH", "MEDIUM", "LOW"]
FINDING_KEYS = {"severity", "title", "detail", "file"}
COMMENT_MARKER = "<!-- pr-risk-score -->"

THREADS_QUERY = """
query($owner:String!,$repo:String!,$number:Int!,$cursor:String){
  repository(owner:$owner,name:$repo){pullRequest(number:$number){
    reviewThreads(first:100,after:$cursor){
      pageInfo{hasNextPage endCursor}
      nodes{
        id path line isResolved isOutdated
        comments(first:20){pageInfo{hasNextPage} totalCount}
      }
    }
  }}
}
"""


class CommandError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    accepted_codes: tuple[int, ...] = (0,),
) -> str:
    # Keep every input in its own argv element; never interpolate through a shell.
    process = subprocess.run(  # nosec B603
        command,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode not in accepted_codes:
        rendered = " ".join(command[:5])
        detail = process.stderr.strip() or process.stdout.strip()
        raise CommandError(f"{rendered}: {detail[:500]}")
    return process.stdout


def command_path(name: str, fallback: Path | None = None) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if fallback and fallback.is_file():
        return str(fallback)
    raise CommandError(f"Required command unavailable: {name}")


def gh_json(arguments: list[str]) -> Any:
    raw = run([command_path("gh"), *arguments])
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise CommandError(f"gh returned invalid JSON: {error}") from error


def write_json(path: Path, value: Any) -> None:
    path.write_text(f"{json.dumps(value, indent=2, ensure_ascii=False)}\n")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON file {path}: {error}") from error


def assert_naboo_checkout() -> None:
    remote = run([command_path("git"), "remote", "get-url", "origin"]).strip()
    if not re.search(r"github\.com[:/]naboo-team/naboo(?:\.git)?$", remote):
        raise CommandError(
            f"Run from a {REPOSITORY} checkout; origin is {remote or 'unavailable'}"
        )


def resolve_pr_number(reference: str | None) -> int:
    if reference is None:
        data = gh_json(["pr", "view", "--repo", REPOSITORY, "--json", "number"])
        return positive_integer(data.get("number"), "PR number")

    normalized = reference.strip()
    direct = re.fullmatch(r"#?(\d+)", normalized)
    if direct:
        return positive_integer(int(direct.group(1)), "PR number")

    url = re.fullmatch(
        r"https://github\.com/naboo-team/naboo/pull/(\d+)(?:[/?#].*)?", normalized
    )
    if url:
        return positive_integer(int(url.group(1)), "PR number")

    raise ValueError("Expected a Naboo PR number or github.com/naboo-team/naboo URL")


def positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def paged_rest(endpoint: str) -> list[dict[str, Any]]:
    pages = gh_json(["api", "--paginate", "--slurp", endpoint])
    if not isinstance(pages, list):
        raise CommandError(f"Unexpected paginated response for {endpoint}")
    items: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise CommandError(f"Unexpected page shape for {endpoint}")
        items.extend(item for item in page if isinstance(item, dict))
    return items


def fetch_thread_page(pr_number: int, cursor: str | None) -> dict[str, Any]:
    owner, repo = REPOSITORY.split("/", maxsplit=1)
    arguments = [
        "api",
        "graphql",
        "-f",
        f"query={THREADS_QUERY}",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={pr_number}",
    ]
    if cursor:
        arguments.extend(["-F", f"cursor={cursor}"])
    response = gh_json(arguments)
    if response.get("errors"):
        raise CommandError(f"GitHub GraphQL failed: {response['errors']}")
    try:
        return response["data"]["repository"]["pullRequest"]["reviewThreads"]
    except (KeyError, TypeError) as error:
        raise CommandError("Pull request review threads unavailable") from error


def compact_threads(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    threads: list[dict[str, Any]] = []
    complete = True
    for thread in nodes:
        comments = thread.get("comments") or {}
        complete = complete and not bool(
            (comments.get("pageInfo") or {}).get("hasNextPage")
        )
        threads.append(
            {
                "id": thread.get("id"),
                "path": thread.get("path"),
                "line": thread.get("line"),
                "isResolved": bool(thread.get("isResolved")),
                "isOutdated": bool(thread.get("isOutdated")),
                "commentCount": comments.get("totalCount", 0),
            }
        )
    return threads, complete


def fetch_threads(pr_number: int) -> tuple[list[dict[str, Any]], bool]:
    threads: list[dict[str, Any]] = []
    cursor: str | None = None
    complete = True
    for _ in range(MAX_GRAPHQL_PAGES):
        page = fetch_thread_page(pr_number, cursor)
        page_threads, page_complete = compact_threads(page.get("nodes") or [])
        threads.extend(page_threads)
        complete = complete and page_complete
        page_info = page.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return threads, complete
        cursor = page_info.get("endCursor")
        if not cursor:
            raise CommandError("Review-thread pagination cursor unavailable")

    raise CommandError(f"Review-thread pagination exceeded {MAX_GRAPHQL_PAGES} pages")


def fetch_check_runs(head_sha: str) -> list[dict[str, Any]]:
    endpoint = f"repos/{REPOSITORY}/commits/{head_sha}/check-runs?per_page=100"
    pages = gh_json(["api", "--paginate", "--slurp", endpoint])
    if not isinstance(pages, list):
        raise CommandError("Unexpected check-run response")
    check_runs: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise CommandError("Unexpected check-run page")
        check_runs.extend(
            check for check in page.get("check_runs") or [] if isinstance(check, dict)
        )
    return check_runs


def latest_validation_gate(check_runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        check
        for check in check_runs
        if "Validation Gate" in str(check.get("name", ""))
        or check.get("name") == "Gate - Check validation results"
    ]
    return max(candidates, key=lambda check: int(check.get("id") or 0), default=None)


def active_changes_request(reviews: list[dict[str, Any]]) -> bool:
    latest: dict[str, str] = {}
    for review in reviews:
        user = review.get("user") or {}
        author = user.get("login")
        state = review.get("state")
        if not author or state in {"COMMENTED", "PENDING", None}:
            continue
        latest[str(author)] = str(state)
    return "CHANGES_REQUESTED" in latest.values()


def fetch_pull_request(pr_number: int) -> dict[str, Any]:
    pr = gh_json(["api", f"repos/{REPOSITORY}/pulls/{pr_number}"])
    if pr.get("mergeable") is None and pr.get("state") == "open":
        time.sleep(2)
        return gh_json(["api", f"repos/{REPOSITORY}/pulls/{pr_number}"])
    return pr


def pull_request_shas(pr: dict[str, Any]) -> tuple[str, str]:
    head_sha = str((pr.get("head") or {}).get("sha") or "")
    base_sha = str((pr.get("base") or {}).get("sha") or "")
    if not head_sha or not base_sha:
        raise CommandError("PR head or base SHA unavailable")
    return head_sha, base_sha


def compact_validation_gate(
    validation_gate: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if validation_gate is None:
        return None
    return {
        "id": validation_gate.get("id"),
        "name": validation_gate.get("name"),
        "status": validation_gate.get("status"),
        "conclusion": validation_gate.get("conclusion"),
    }


def unresolved_thread_count(threads: list[dict[str, Any]]) -> int:
    return sum(
        1 for thread in threads if not thread["isResolved"] and not thread["isOutdated"]
    )


def machine_state(pr_number: int, *, include_files: bool) -> dict[str, Any]:
    pr = fetch_pull_request(pr_number)
    head_sha, base_sha = pull_request_shas(pr)
    reviews = paged_rest(f"repos/{REPOSITORY}/pulls/{pr_number}/reviews")
    threads, threads_complete = fetch_threads(pr_number)
    validation_gate = latest_validation_gate(fetch_check_runs(head_sha))
    state: dict[str, Any] = {
        "pr": pr,
        "headSha": head_sha,
        "baseSha": base_sha,
        "threadsComplete": threads_complete,
        "unresolvedThreadCount": unresolved_thread_count(threads),
        "changesRequested": active_changes_request(reviews),
        "validationGate": compact_validation_gate(validation_gate),
    }
    if include_files:
        state["files"] = paged_rest(f"repos/{REPOSITORY}/pulls/{pr_number}/files")
    return state


def mechanical_fingerprint(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": snapshot.get("state"),
        "draft": snapshot.get("draft"),
        "mergeable": snapshot.get("mergeable"),
        "unresolvedThreadCount": snapshot.get("unresolvedThreadCount"),
        "changesRequested": snapshot.get("changesRequested"),
        "validationGate": snapshot.get("validationGate"),
    }


def read_artifacts(pr_number: int, gh_axi: str, yq: str) -> dict[str, str]:
    pr_text = run([gh_axi, "pr", "view", str(pr_number), "--full"])
    reviews_text = run([gh_axi, "pr", "view", str(pr_number), "--reviews", "--full"])
    checks_text = run([gh_axi, "pr", "checks", str(pr_number)])
    diff_yaml = run([gh_axi, "pr", "diff", str(pr_number), "--full"])
    return {
        "pr": pr_text,
        "reviews": reviews_text,
        "checks": checks_text,
        "diff": run([yq, "-r", ".pr_diff.diff"], input_text=diff_yaml),
    }


def snapshot_stats(state: dict[str, Any], diff: str) -> dict[str, Any]:
    pr = state["pr"]
    files = state["files"]
    filenames = [str(file.get("filename")) for file in files if file.get("filename")]
    changed_lines = int(pr.get("additions") or 0) + int(pr.get("deletions") or 0)
    file_count = int(pr.get("changed_files") or 0)
    diff_file_count = len(re.findall(r"^diff --git ", diff, flags=re.MULTILINE))
    diff_complete = (
        bool(diff.strip())
        and len(filenames) == file_count
        and diff_file_count == file_count
    )
    validation_gate = state["validationGate"]
    return {
        "filenames": filenames,
        "changedLines": changed_lines,
        "fileCount": file_count,
        "diffComplete": diff_complete,
        "ciGreen": bool(
            validation_gate
            and validation_gate.get("status") == "completed"
            and validation_gate.get("conclusion") == "success"
        ),
    }


def collection_issues(state: dict[str, Any], stats: dict[str, Any]) -> list[str]:
    pr = state["pr"]
    candidates = [
        (pr.get("state") != "open", "PR is not open."),
        (not stats["diffComplete"], "Diff or file inventory is incomplete."),
        (
            not state["threadsComplete"],
            "Review-thread comments are not fully paginated.",
        ),
        (
            stats["fileCount"] > MAX_REVIEWABLE_FILES,
            f"PR changes {stats['fileCount']} files; limit is {MAX_REVIEWABLE_FILES}.",
        ),
        (
            stats["changedLines"] > MAX_REVIEWABLE_CHANGED_LINES,
            f"PR changes {stats['changedLines']} lines; limit is "
            f"{MAX_REVIEWABLE_CHANGED_LINES}.",
        ),
        (pr.get("mergeable") is None, "GitHub mergeability is unknown."),
    ]
    return [reason for failed, reason in candidates if failed]


def artifact_paths(output_dir: Path) -> dict[str, str]:
    return {
        "pr": str((output_dir / "pr.txt").resolve()),
        "reviews": str((output_dir / "reviews.txt").resolve()),
        "checks": str((output_dir / "checks.txt").resolve()),
        "diff": str((output_dir / "diff.patch").resolve()),
        "snapshot": str((output_dir / "snapshot.json").resolve()),
    }


def write_artifacts(output_dir: Path, artifacts: dict[str, str]) -> None:
    (output_dir / "pr.txt").write_text(artifacts["pr"])
    (output_dir / "reviews.txt").write_text(artifacts["reviews"])
    (output_dir / "checks.txt").write_text(artifacts["checks"])
    (output_dir / "diff.patch").write_text(artifacts["diff"])


def prepare_output_dir(output_dir: Path) -> None:
    if output_dir.is_symlink():
        raise ValueError("Output directory cannot be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    conflicts = sorted(path.name for path in output_dir.iterdir())
    if conflicts:
        raise ValueError(f"Output directory must be empty: {', '.join(conflicts)}")


def build_snapshot(
    pr_number: int,
    state: dict[str, Any],
    stats: dict[str, Any],
    paths: dict[str, str],
    issues: list[str],
) -> dict[str, Any]:
    pr = state["pr"]
    snapshot = {
        "policyVersion": POLICY_VERSION,
        "runnerVersion": RUNNER_VERSION,
        "repository": REPOSITORY,
        "prNumber": pr_number,
        "url": pr.get("html_url"),
        "title": pr.get("title") or "",
        "author": (pr.get("user") or {}).get("login") or "",
        "state": pr.get("state"),
        "draft": bool(pr.get("draft")),
        "mergeable": pr.get("mergeable"),
        "headSha": state["headSha"],
        "baseSha": state["baseSha"],
        "baseBranch": (pr.get("base") or {}).get("ref"),
        "fileCount": stats["fileCount"],
        "changedLines": stats["changedLines"],
        "files": stats["filenames"],
        "diffComplete": stats["diffComplete"],
        "threadsComplete": state["threadsComplete"],
        "ciGreen": stats["ciGreen"],
        "validationGate": state["validationGate"],
        "unresolvedThreadCount": state["unresolvedThreadCount"],
        "changesRequested": state["changesRequested"],
        "reviewable": len(issues) == 0,
        "collectionIssues": issues,
        "mechanicalFingerprint": {},
        "paths": paths,
        "collectedAt": now_iso(),
    }
    snapshot["mechanicalFingerprint"] = mechanical_fingerprint(snapshot)
    return snapshot


def collect(reference: str | None, output_dir: Path) -> dict[str, Any]:
    assert_naboo_checkout()
    prepare_output_dir(output_dir)
    gh_axi = command_path("gh-axi", Path.home() / ".n/bin/gh-axi")
    yq = command_path("yq")
    pr_number = resolve_pr_number(reference)
    state = machine_state(pr_number, include_files=True)
    artifacts = read_artifacts(pr_number, gh_axi, yq)
    stats = snapshot_stats(state, artifacts["diff"])
    issues = collection_issues(state, stats)

    paths = artifact_paths(output_dir)
    write_artifacts(output_dir, artifacts)
    snapshot = build_snapshot(pr_number, state, stats, paths, issues)
    write_json(output_dir / "snapshot.json", snapshot)
    return snapshot


def rubric() -> dict[str, Any]:
    return {
        "policyVersion": POLICY_VERSION,
        "scoreLimit": LOW_RISK_SCORE_LIMIT,
        "comparison": "score < scoreLimit",
        "maxReviewableFiles": MAX_REVIEWABLE_FILES,
        "maxReviewableChangedLines": MAX_REVIEWABLE_CHANGED_LINES,
        "dimensions": DIMENSIONS,
        "humanOnlySurfaces": sorted(HUMAN_ONLY_SURFACES),
        "exactPathEvidence": ["complete", "insufficient", "not_required"],
        "findingSeverities": FINDING_SEVERITIES,
    }


def validate_dimensions(dimensions: Any) -> None:
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise ValueError(f"Dimension keys must be exactly {sorted(DIMENSIONS)}")
    for name, definition in DIMENSIONS.items():
        score = dimensions.get(name)
        if type(score) is not int or score not in definition["allowed"]:
            raise ValueError(f"{name} must be one of {definition['allowed']}")


def validate_surfaces(surfaces: Any) -> None:
    if not isinstance(surfaces, list) or len(surfaces) > len(HUMAN_ONLY_SURFACES):
        raise ValueError("humanOnlySurfaces must be a list of at most seven values")
    if any(surface not in HUMAN_ONLY_SURFACES for surface in surfaces):
        raise ValueError("humanOnlySurfaces contains an unknown value")


def validate_evidence(evidence: Any) -> None:
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 12:
        raise ValueError("evidence must contain between one and twelve entries")
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"file", "reason"}:
            raise ValueError("Each evidence entry requires file and reason")
        if not all(isinstance(item[key], str) and item[key].strip() for key in item):
            raise ValueError("Evidence file and reason must be non-empty strings")


def validate_findings(findings: Any) -> None:
    if not isinstance(findings, list) or len(findings) > 10:
        raise ValueError("findings must be a list of at most ten entries")
    for item in findings:
        if not isinstance(item, dict) or set(item) != FINDING_KEYS:
            raise ValueError(f"Each finding requires exactly {sorted(FINDING_KEYS)}")
        if item["severity"] not in FINDING_SEVERITIES:
            raise ValueError(f"Finding severity must be one of {FINDING_SEVERITIES}")
        if not all(isinstance(item[key], str) and item[key].strip() for key in item):
            raise ValueError("Finding fields must be non-empty strings")


def validate_unknowns(unknowns: Any) -> None:
    if not isinstance(unknowns, list) or len(unknowns) > 10:
        raise ValueError("unknowns must be a list of at most ten values")
    if any(not isinstance(item, str) or not item.strip() for item in unknowns):
        raise ValueError("Every unknown must be a non-empty string")


def validate_assessment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ASSESSMENT_KEYS:
        raise ValueError(f"Assessment keys must be exactly {sorted(ASSESSMENT_KEYS)}")

    validate_dimensions(value.get("dimensions"))
    validate_surfaces(value.get("humanOnlySurfaces"))
    validate_evidence(value.get("evidence"))
    validate_findings(value.get("findings"))
    validate_unknowns(value.get("unknowns"))
    if value.get("exactPathEvidence") not in {
        "complete",
        "insufficient",
        "not_required",
    }:
        raise ValueError("exactPathEvidence is invalid")
    explanation = value.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("explanation must be a non-empty string")

    return value


def infer_human_only_surfaces(files: list[str]) -> list[str]:
    surfaces: list[str] = []
    for file in files:
        for surface, pattern in HUMAN_ONLY_PATHS:
            if pattern.search(file) and surface not in surfaces:
                surfaces.append(surface)
    return surfaces


def gate(identifier: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"id": identifier, "passed": passed, "reason": reason}


def input_gates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    complete = bool(snapshot.get("diffComplete")) and bool(
        snapshot.get("threadsComplete")
    )
    file_count = int(snapshot.get("fileCount") or 0)
    changed_lines = int(snapshot.get("changedLines") or 0)
    reviewable_size = (
        file_count <= MAX_REVIEWABLE_FILES
        and changed_lines <= MAX_REVIEWABLE_CHANGED_LINES
    )
    open_pr = snapshot.get("state") == "open"
    return [
        gate("pr_open", open_pr, "PR is open." if open_pr else "PR is not open."),
        gate(
            "complete_input",
            complete,
            "Diff, files, and review threads are complete."
            if complete
            else "Diff, files, or review threads are incomplete.",
        ),
        gate(
            "reviewable_size",
            reviewable_size,
            f"{file_count} files and {changed_lines} changed lines; limits are "
            f"{MAX_REVIEWABLE_FILES} and {MAX_REVIEWABLE_CHANGED_LINES}.",
        ),
    ]


def readiness_gates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    mergeable = snapshot.get("mergeable")
    ci_green = bool(snapshot.get("ciGreen"))
    is_draft = bool(snapshot.get("draft"))
    return [
        gate(
            "mergeability_known",
            mergeable is not None,
            "GitHub mergeability is known."
            if mergeable is not None
            else "GitHub mergeability is unknown.",
        ),
        gate(
            "ci_green",
            ci_green,
            "Latest Validation Gate is green."
            if ci_green
            else "Latest Validation Gate is not green.",
        ),
        gate(
            "mergeable",
            mergeable is True,
            "GitHub reports the PR mergeable."
            if mergeable is True
            else "GitHub does not report the PR mergeable.",
        ),
        gate(
            "not_draft",
            not is_draft,
            "PR is ready for review." if not is_draft else "PR is a draft.",
        ),
    ]


def review_gates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    unresolved_threads = int(snapshot.get("unresolvedThreadCount") or 0)
    changes_requested = bool(snapshot.get("changesRequested"))
    no_open_findings = unresolved_threads == 0 and not changes_requested
    return [
        gate(
            "no_open_findings",
            no_open_findings,
            f"{unresolved_threads} unresolved threads; "
            f"changes requested: {changes_requested}.",
        ),
    ]


def mechanical_gates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *input_gates(snapshot),
        *readiness_gates(snapshot),
        *review_gates(snapshot),
    ]


def inconclusive_reasons(snapshot: dict[str, Any]) -> list[str]:
    detected = [
        (snapshot.get("state") != "open", "PR is not open."),
        (not snapshot.get("diffComplete"), "Diff or file inventory is incomplete."),
        (not snapshot.get("threadsComplete"), "Review-thread evidence is incomplete."),
        (
            int(snapshot.get("fileCount") or 0) > MAX_REVIEWABLE_FILES,
            "File count exceeds the reviewable limit.",
        ),
        (
            int(snapshot.get("changedLines") or 0) > MAX_REVIEWABLE_CHANGED_LINES,
            "Changed lines exceed the reviewable limit.",
        ),
        (snapshot.get("mergeable") is None, "GitHub mergeability is unknown."),
    ]
    reasons = [reason for failed, reason in detected if failed]
    return list(dict.fromkeys([*(snapshot.get("collectionIssues") or []), *reasons]))


def result_base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "policyVersion": POLICY_VERSION,
        "runnerVersion": RUNNER_VERSION,
        "repository": snapshot.get("repository", REPOSITORY),
        "prNumber": snapshot.get("prNumber"),
        "headSha": snapshot.get("headSha"),
        "generatedAt": now_iso(),
    }


def assessment_unavailability_reasons(
    snapshot: dict[str, Any],
    assessment: dict[str, Any] | None,
    assessment_error: str | None,
) -> list[str]:
    reasons = inconclusive_reasons(snapshot)
    if assessment_error:
        reasons.append(f"Assessment invalid: {assessment_error}")
    if assessment is None and not reasons:
        reasons.append("Structured assessment unavailable.")
    return reasons


def build_inconclusive_result(
    snapshot: dict[str, Any],
    assessment: dict[str, Any] | None,
    assessment_error: str | None,
    reasons: list[str],
) -> dict[str, Any]:
    assessment_complete = assessment is not None and assessment_error is None
    gates = [
        *mechanical_gates(snapshot),
        gate(
            "assessment_complete",
            assessment_complete,
            "Structured assessment is valid."
            if assessment_complete
            else assessment_error or "Structured assessment unavailable.",
        ),
    ]
    why_not = " ".join(dict.fromkeys(reasons))
    return {
        **result_base(snapshot),
        "score": None,
        "band": None,
        "confidence": None,
        "dimensions": None,
        "verdict": "INCONCLUSIVE",
        "explanation": assessment["explanation"] if assessment else why_not,
        "whyNot": why_not,
        "evidence": assessment.get("evidence", []) if assessment else [],
        "findings": assessment.get("findings", []) if assessment else [],
        "humanOnlySurfaces": [],
        "unknowns": assessment.get("unknowns", []) if assessment else reasons,
        "gates": gates,
        "failedGates": [item for item in gates if not item["passed"]],
        "assessmentError": assessment_error,
    }


def risk_band(score: int) -> str:
    if score < LOW_RISK_SCORE_LIMIT:
        return "Low"
    return "Medium" if score < 70 else "High"


def confidence(assessment: dict[str, Any]) -> int:
    # ponytail: fixed steps, not a model; recalibrate once shadow runs show misses.
    base = 60 if assessment["exactPathEvidence"] == "insufficient" else 90
    return max(30, base - 10 * len(assessment["unknowns"]))


def exact_path_reason(exact_path_evidence: str) -> str:
    reasons = {
        "complete": "Evidence traverses the changed behavior.",
        "not_required": "No runtime behavior changed.",
        "insufficient": "Exact changed behavior is not proven.",
    }
    return reasons[exact_path_evidence]


def build_assessment_gates(
    assessment: dict[str, Any], score: int, human_only_surfaces: list[str]
) -> list[dict[str, Any]]:
    no_unknowns = len(assessment["unknowns"]) == 0
    exact_path_evidence = assessment["exactPathEvidence"]
    return [
        gate("assessment_complete", True, "Structured assessment is valid."),
        gate(
            "known_risk",
            no_unknowns,
            "No material unknowns."
            if no_unknowns
            else f"Unknowns: {'; '.join(assessment['unknowns'])}.",
        ),
        gate(
            "exact_path_proof",
            exact_path_evidence != "insufficient",
            exact_path_reason(exact_path_evidence),
        ),
        gate(
            "human_only_surface",
            len(human_only_surfaces) == 0,
            "No human-only surface detected."
            if not human_only_surfaces
            else f"Human-only surfaces: {', '.join(human_only_surfaces)}.",
        ),
        gate(
            "score_threshold",
            score < LOW_RISK_SCORE_LIMIT,
            f"Risk is {risk_band(score).upper()} (only LOW, under "
            f"{LOW_RISK_SCORE_LIMIT}, can auto-approve).",
        ),
    ]


def build_scored_result(
    snapshot: dict[str, Any], assessment: dict[str, Any]
) -> dict[str, Any]:
    score = sum(assessment["dimensions"].values())
    path_surfaces = infer_human_only_surfaces(snapshot.get("files") or [])
    human_only_surfaces = list(
        dict.fromkeys([*path_surfaces, *assessment["humanOnlySurfaces"]])
    )
    gates = [
        *mechanical_gates(snapshot),
        *build_assessment_gates(assessment, score, human_only_surfaces),
    ]
    failed = [item for item in gates if not item["passed"]]
    verdict = "LOW_RISK_CANDIDATE" if not failed else "HUMAN_REVIEW_REQUIRED"
    return {
        **result_base(snapshot),
        "score": score,
        "band": risk_band(score),
        "confidence": confidence(assessment),
        "dimensions": assessment["dimensions"],
        "verdict": verdict,
        "explanation": assessment["explanation"],
        "whyNot": " ".join(item["reason"] for item in failed),
        "evidence": assessment["evidence"],
        "findings": assessment["findings"],
        "humanOnlySurfaces": human_only_surfaces,
        "unknowns": assessment["unknowns"],
        "gates": gates,
        "failedGates": failed,
        "assessmentError": None,
    }


def evaluate_snapshot(
    snapshot: dict[str, Any],
    assessment: dict[str, Any] | None,
    assessment_error: str | None = None,
) -> dict[str, Any]:
    reasons = assessment_unavailability_reasons(snapshot, assessment, assessment_error)
    if reasons:
        return build_inconclusive_result(
            snapshot, assessment, assessment_error, reasons
        )
    if assessment is None:
        raise ValueError("Structured assessment unavailable")
    return build_scored_result(snapshot, assessment)


def evaluate_command(
    snapshot_path: Path,
    assessment_path: Path | None,
    output_path: Path | None,
) -> dict[str, Any]:
    snapshot = load_json(snapshot_path)
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be a JSON object")

    assessment: dict[str, Any] | None = None
    assessment_error: str | None = None
    if assessment_path:
        try:
            assessment = validate_assessment(load_json(assessment_path))
        except ValueError as error:
            assessment_error = str(error)

    result = evaluate_snapshot(snapshot, assessment, assessment_error)
    if output_path:
        write_json(output_path, result)
    return result


def verification_result(
    snapshot: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    expected_fingerprint = snapshot.get("mechanicalFingerprint") or {}
    pr = current["pr"]
    current_fingerprint = mechanical_fingerprint(
        {
            "state": pr.get("state"),
            "draft": bool(pr.get("draft")),
            "mergeable": pr.get("mergeable"),
            "unresolvedThreadCount": current["unresolvedThreadCount"],
            "changesRequested": current["changesRequested"],
            "validationGate": current["validationGate"],
        }
    )
    head_matches = current["headSha"] == snapshot.get("headSha")
    state_matches = current_fingerprint == expected_fingerprint
    matches = head_matches and state_matches
    reasons: list[str] = []
    if not head_matches:
        reasons.append("PR head changed during assessment.")
    if not state_matches:
        reasons.append("PR checks or review state changed during assessment.")
    return {
        "matches": matches,
        "expectedHeadSha": snapshot.get("headSha"),
        "currentHeadSha": current["headSha"],
        "mechanicalStateMatches": state_matches,
        "verdict": None if matches else "INCONCLUSIVE",
        "reason": "Snapshot is current." if matches else " ".join(reasons),
    }


def verify_head(snapshot_path: Path) -> dict[str, Any]:
    assert_naboo_checkout()
    snapshot = load_json(snapshot_path)
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be a JSON object")
    pr_number = positive_integer(snapshot.get("prNumber"), "PR number")
    current = machine_state(pr_number, include_files=False)
    return verification_result(snapshot, current)


VERDICT_CELLS = {
    "LOW_RISK_CANDIDATE": "✅ **Eligible** — advice only, a human still merges",
    "HUMAN_REVIEW_REQUIRED": "🧭 **No** — human review required",
    "INCONCLUSIVE": "⚠️ **Inconclusive** — not scored",
}


def text(value: str) -> str:
    # Assessment text quotes the PR; keep it on one line and out of the HTML.
    return html.escape(" ".join(value.split()), quote=False)


def finding_count(findings: list[dict[str, Any]]) -> str:
    counts = [
        f"{count} {severity.lower()}"
        for severity in FINDING_SEVERITIES
        if (count := sum(1 for item in findings if item["severity"] == severity))
    ]
    return f"{', '.join(counts)} finding(s)" if counts else "no findings"


def render(result: dict[str, Any]) -> str:
    scored = result["score"] is not None
    score = f"**{result['score']}/100 · {result['band']}**" if scored else "—"
    confidence_cell = f"**{result['confidence']}%**" if scored else "—"
    findings = sorted(
        result["findings"], key=lambda item: FINDING_SEVERITIES.index(item["severity"])
    )
    lines = [
        COMMENT_MARKER,
        "| Risk score | Auto-approval | Confidence |",
        "| --- | --- | ---: |",
        f"| {score} | {VERDICT_CELLS[result['verdict']]} | {confidence_cell} |",
        "",
    ]
    if result["whyNot"]:
        label = "Why not approved" if scored else "Why not scored"
        lines += [f"> **{label}:** {text(result['whyNot'])}", ""]
    lines += [
        f"**Summary:** {text(result['explanation'])}",
        "",
        "<details>",
        f"<summary>Review details · {finding_count(findings)}</summary>",
        "",
    ]
    if findings:
        lines += ["**Review notes**", ""]
        lines += [
            f"- **{item['severity']}: {text(item['title'])}** — "
            f"{text(item['detail'])} (`{text(item['file'])}`)"
            for item in findings
        ]
        lines.append("")
    if result["dimensions"]:
        lines += [
            "**Dimensions**",
            "",
            "| Dimension | Score | Max |",
            "| --- | ---: | ---: |",
        ]
        lines += [
            f"| {name} | {value} | {DIMENSIONS[name]['allowed'][-1]} |"
            for name, value in result["dimensions"].items()
        ]
        lines.append("")
    lines += ["**Gates**", ""]
    lines += [
        f"- {'✅' if item['passed'] else '❌'} `{item['id']}` — {text(item['reason'])}"
        for item in result["gates"]
    ]
    lines.append("")
    if result["unknowns"]:
        lines += [
            "**Unknowns**",
            "",
            *[f"- {text(item)}" for item in result["unknowns"]],
            "",
        ]
    if result["evidence"]:
        lines += ["**Evidence**", ""]
        lines += [
            f"- `{text(item['file'])}` — {text(item['reason'])}"
            for item in result["evidence"]
        ]
        lines.append("")
    lines += [
        f"<sub>{result['policyVersion']} · head {str(result['headSha'])[:12]} · "
        "advice only, never an approval</sub>",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"


def post(snapshot_path: Path, result_path: Path) -> dict[str, Any]:
    freshness = verify_head(snapshot_path)
    if not freshness["matches"]:
        raise CommandError(f"Not posted: {freshness['reason']}")
    snapshot = load_json(snapshot_path)
    result = load_json(result_path)
    if not isinstance(result, dict) or result.get("headSha") != snapshot.get("headSha"):
        raise ValueError("Result does not describe the snapshot head")

    pr_number = positive_integer(snapshot.get("prNumber"), "PR number")
    login = gh_json(["api", "user"]).get("login")
    existing = next(
        (
            comment
            for comment in paged_rest(f"repos/{REPOSITORY}/issues/{pr_number}/comments")
            if (comment.get("user") or {}).get("login") == login
            and str(comment.get("body") or "").startswith(COMMENT_MARKER)
        ),
        None,
    )
    method, endpoint = (
        ("PATCH", f"repos/{REPOSITORY}/issues/comments/{existing['id']}")
        if existing
        else ("POST", f"repos/{REPOSITORY}/issues/{pr_number}/comments")
    )
    raw = run(
        [command_path("gh"), "api", "-X", method, endpoint, "--input", "-"],
        input_text=json.dumps({"body": render(result)}),
    )
    return {
        "action": "updated" if existing else "created",
        "url": json.loads(raw).get("html_url"),
    }


def sample_snapshot(**overrides: Any) -> dict[str, Any]:
    snapshot = {
        "repository": REPOSITORY,
        "prNumber": 123,
        "headSha": "abc123",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "diffComplete": True,
        "threadsComplete": True,
        "fileCount": 2,
        "changedLines": 40,
        "files": ["src/card.tsx", "src/card.test.tsx"],
        "ciGreen": True,
        "unresolvedThreadCount": 0,
        "changesRequested": False,
        "collectionIssues": [],
    }
    snapshot.update(overrides)
    return snapshot


def sample_assessment(**overrides: Any) -> dict[str, Any]:
    assessment = {
        "dimensions": {
            "businessImpact": 10,
            "blastRadius": 5,
            "contractsAndState": 0,
            "operationalRisk": 0,
            "verificationGap": 0,
        },
        "humanOnlySurfaces": [],
        "exactPathEvidence": "complete",
        "evidence": [{"file": "src/card.tsx", "reason": "Targeted rendering test."}],
        "findings": [],
        "unknowns": [],
        "explanation": "Contained UI change with exact-path proof.",
    }
    assessment.update(overrides)
    return assessment


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_candidate_and_threshold() -> None:
    low = evaluate_snapshot(sample_snapshot(), validate_assessment(sample_assessment()))
    require(
        low["score"] == 15 and low["verdict"] == "LOW_RISK_CANDIDATE",
        "Low-risk candidate failed",
    )
    threshold = sample_assessment(
        dimensions={
            "businessImpact": 20,
            "blastRadius": 10,
            "contractsAndState": 5,
            "operationalRisk": 5,
            "verificationGap": 0,
        }
    )
    result = evaluate_snapshot(sample_snapshot(), validate_assessment(threshold))
    require(
        result["score"] == 40 and result["verdict"] == "HUMAN_REVIEW_REQUIRED",
        "Strict threshold failed",
    )


def check_exact_path_regression() -> None:
    insufficient = sample_assessment(exactPathEvidence="insufficient")
    result = evaluate_snapshot(sample_snapshot(), validate_assessment(insufficient))
    require(
        result["score"] == 15 and result["verdict"] == "HUMAN_REVIEW_REQUIRED",
        "Exact-path regression failed",
    )
    require(
        any(gate_["id"] == "exact_path_proof" for gate_ in result["failedGates"]),
        "Exact-path gate missing",
    )


def check_sensitive_surfaces() -> None:
    sensitive = sample_snapshot(files=[".github/CODEOWNERS"])
    result = evaluate_snapshot(sensitive, validate_assessment(sample_assessment()))
    require(
        result["humanOnlySurfaces"] == ["codeowners_agent_instructions"],
        "CODEOWNERS surface missing",
    )
    require(result["verdict"] == "HUMAN_REVIEW_REQUIRED", "Sensitive path passed")
    paths = [
        ".github/rulesets/dev.json",
        ".github/workflows/ci-example.yaml",
        "packages/api/migrations/backfill-users.ts",
        "packages/api/src/auth/guard.ts",
        "packages/api/src/fintech/payouts/service.ts",
        "packages/api/src/privacy/encryption.ts",
    ]
    inferred = set(infer_human_only_surfaces(paths))
    require(
        inferred
        == {
            "approval_policy",
            "infrastructure_workflow",
            "migration_backfill",
            "iam_auth",
            "finance_billing",
            "secrets_encryption_privacy",
        },
        "Sensitive path families are incomplete",
    )


def check_hard_gates() -> None:
    for overrides in [
        {"draft": True},
        {"ciGreen": False},
        {"mergeable": False},
        {"unresolvedThreadCount": 1},
        {"changesRequested": True},
    ]:
        result = evaluate_snapshot(
            sample_snapshot(**overrides), validate_assessment(sample_assessment())
        )
        require(
            result["verdict"] == "HUMAN_REVIEW_REQUIRED",
            f"Hard gate passed: {overrides}",
        )
    unknown = sample_assessment(unknowns=["Production invariant is unverified."])
    result = evaluate_snapshot(sample_snapshot(), validate_assessment(unknown))
    require(result["verdict"] == "HUMAN_REVIEW_REQUIRED", "Unknown risk passed")


def check_inconclusive_inputs() -> None:
    for overrides in [
        {"diffComplete": False},
        {"threadsComplete": False},
        {"fileCount": 51},
        {"changedLines": 2_001},
        {"mergeable": None},
        {"state": "closed"},
    ]:
        result = evaluate_snapshot(sample_snapshot(**overrides), None)
        require(
            result["score"] is None and result["verdict"] == "INCONCLUSIVE",
            f"Incomplete input produced a score: {overrides}",
        )
    result = evaluate_snapshot(
        sample_snapshot(diffComplete=False), validate_assessment(sample_assessment())
    )
    assessment_gate = next(
        gate_ for gate_ in result["gates"] if gate_["id"] == "assessment_complete"
    )
    require(assessment_gate["passed"] is True, "Valid assessment marked unavailable")


def check_invalid_assessment() -> None:
    invalid = sample_assessment()
    invalid["dimensions"]["businessImpact"] = 7
    try:
        validate_assessment(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid score accepted")


def check_input_and_freshness() -> None:
    require(resolve_pr_number("#123") == 123, "Numeric PR reference failed")
    require(
        resolve_pr_number("https://github.com/naboo-team/naboo/pull/123") == 123,
        "PR URL reference failed",
    )
    snapshot = sample_snapshot()
    snapshot["mechanicalFingerprint"] = mechanical_fingerprint(snapshot)
    current = {
        "pr": {"state": "open", "draft": False, "mergeable": True},
        "headSha": "abc123",
        "unresolvedThreadCount": 0,
        "changesRequested": False,
        "validationGate": None,
    }
    require(
        verification_result(snapshot, current)["matches"] is True, "Fresh state failed"
    )
    current["headSha"] = "def456"
    require(
        verification_result(snapshot, current)["verdict"] == "INCONCLUSIVE",
        "Changed head was accepted",
    )


def check_report() -> None:
    medium = sample_assessment(
        dimensions={
            "businessImpact": 20,
            "blastRadius": 10,
            "contractsAndState": 5,
            "operationalRisk": 5,
            "verificationGap": 5,
        },
        findings=[
            {
                "severity": "LOW",
                "title": "Legacy route now 404s",
                "detail": "Status change only.\n</details> injected",
                "file": "src/route.ts",
            },
            {
                "severity": "HIGH",
                "title": "Cache key dropped",
                "detail": "Stale reads.",
                "file": "src/cache.ts",
            },
        ],
        unknowns=["Traffic unverified."],
    )
    result = evaluate_snapshot(sample_snapshot(), validate_assessment(medium))
    require(
        (result["band"], result["confidence"]) == ("Medium", 80), "Band or confidence"
    )
    require(result["explanation"] == medium["explanation"], "Summary replaced by gates")
    report = render(result)
    require(report.startswith(COMMENT_MARKER), "Comment marker missing")
    require("| **45/100 · Medium** | 🧭 **No**" in report, "Score cell wrong")
    require("> **Why not approved:** Unknowns" in report, "Why-not line wrong")
    require("Review details · 1 high, 1 low finding(s)" in report, "Finding count")
    require(report.index("HIGH: Cache") < report.index("LOW: Legacy"), "Severity order")
    require(report.count("</details>") == 1, "Finding text escaped the details block")

    inconclusive = render(evaluate_snapshot(sample_snapshot(mergeable=None), None))
    require(
        "| — | ⚠️ **Inconclusive**" in inconclusive
        and "**Why not scored:**" in inconclusive,
        "Inconclusive report wrong",
    )
    low = render(
        evaluate_snapshot(sample_snapshot(), validate_assessment(sample_assessment()))
    )
    require("Why not" not in low and "✅ **Eligible**" in low, "Candidate report wrong")


def self_check() -> None:
    check_candidate_and_threshold()
    check_report()
    check_exact_path_regression()
    check_sensitive_surfaces()
    check_hard_gates()
    check_inconclusive_inputs()
    check_invalid_assessment()
    check_input_and_freshness()
    print("self-check ok")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("reference", nargs="?")
    collect_parser.add_argument("--output-dir", type=Path, required=True)

    commands.add_parser("rubric")

    evaluate_parser = commands.add_parser("evaluate")
    evaluate_parser.add_argument("--snapshot", type=Path, required=True)
    evaluate_parser.add_argument("--assessment", type=Path)
    evaluate_parser.add_argument("--output", type=Path)

    verify_parser = commands.add_parser("verify-head")
    verify_parser.add_argument("--snapshot", type=Path, required=True)

    render_parser = commands.add_parser("render")
    render_parser.add_argument("--result", type=Path, required=True)

    post_parser = commands.add_parser("post")
    post_parser.add_argument("--snapshot", type=Path, required=True)
    post_parser.add_argument("--result", type=Path, required=True)
    return root


def main(argv: list[str]) -> int:
    if argv == ["--self-check"]:
        self_check()
        return 0

    arguments = parser().parse_args(argv)
    if arguments.command == "collect":
        print(json.dumps(collect(arguments.reference, arguments.output_dir), indent=2))
        return 0
    if arguments.command == "rubric":
        print(json.dumps(rubric(), indent=2))
        return 0
    if arguments.command == "evaluate":
        result = evaluate_command(
            arguments.snapshot, arguments.assessment, arguments.output
        )
        print(json.dumps(result, indent=2))
        return 0
    if arguments.command == "verify-head":
        print(json.dumps(verify_head(arguments.snapshot), indent=2))
        return 0
    if arguments.command == "render":
        print(render(load_json(arguments.result)), end="")
        return 0
    if arguments.command == "post":
        print(json.dumps(post(arguments.snapshot, arguments.result), indent=2))
        return 0
    raise AssertionError(f"Unhandled command: {arguments.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (CommandError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
