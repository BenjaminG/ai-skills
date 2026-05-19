#!/usr/bin/env python3
"""Deterministic vote consolidation for the consensus skill.

Reads N pass JSON files and a schema/vote-key spec, groups items by the vote
key (with optional numeric tolerance), keeps groups whose count meets the
threshold, and writes a consolidated result. No LLM calls, no randomness.

Spec format (YAML, written by SKILL.md Step 1):

    template: finding-list | extraction | classification | generic-structured
    schema: { ... JSON schema, used for reference only ... }
    vote_key:
      fields: [field1, field2, ...]
      numeric_tolerance:
        line: 5
      single_object: false              # true for classification / nested object outputs
      arrays:                           # only for generic-structured with multiple voted arrays
        risks: { fields: [id] }
        follow_ups: { fields: [id] }
      ignore_fields: [intent]           # generic-structured: scalar fields not voted on

Usage:
    vote.py --schema spec.yaml --threshold 2 --output result.json \\
            --passes pass1.json pass2.json pass3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def normalize_string(s: Any) -> str:
    if not isinstance(s, str):
        return str(s)
    return s.strip().casefold()


def make_group_key(
    item: dict, fields: list[str], numeric_tolerance: dict[str, int]
) -> tuple:
    """Build a hashable group key from an item.

    Numeric fields with tolerance are bucketed into floor(value / (2*tol+1)) so
    items within ±tol of each other share a bucket. This is a coarse proxy for
    fuzzy matching that keeps grouping deterministic and transitive.
    """
    parts: list[Any] = []
    for f in fields:
        val = item.get(f)
        if f in numeric_tolerance and isinstance(val, (int, float)):
            tol = numeric_tolerance[f]
            bucket_size = max(2 * tol + 1, 1)
            parts.append(("num", int(val) // bucket_size))
        elif isinstance(val, str):
            parts.append(("str", normalize_string(val)))
        else:
            parts.append(("raw", val))
    return tuple(parts)


def vote_list(
    passes: list[list[dict]],
    fields: list[str],
    numeric_tolerance: dict[str, int],
    threshold: int,
) -> tuple[list[dict], list[dict]]:
    """Group items across passes; return (consensus, divergences)."""
    groups: dict[tuple, list[tuple[int, dict]]] = defaultdict(list)
    for pass_idx, items in enumerate(passes):
        seen_keys: set[tuple] = set()
        for item in items:
            key = make_group_key(item, fields, numeric_tolerance)
            if key in seen_keys:
                continue  # an item only counts once per pass
            seen_keys.add(key)
            groups[key].append((pass_idx, item))

    consensus: list[dict] = []
    divergences: list[dict] = []
    for key, members in groups.items():
        votes = len(members)
        representative = members[0][1].copy()
        representative["_votes"] = votes
        representative["_pass_indices"] = sorted(idx for idx, _ in members)
        if votes >= threshold:
            consensus.append(representative)
        else:
            divergences.append(representative)

    consensus.sort(key=lambda x: (-x["_votes"], json.dumps(x, sort_keys=True)))
    divergences.sort(key=lambda x: (-x["_votes"], json.dumps(x, sort_keys=True)))
    return consensus, divergences


def vote_classification(
    passes: list[dict], threshold: int
) -> tuple[dict, list[dict]]:
    """Single-object classification — majority on `label`."""
    counts: dict[str, int] = defaultdict(int)
    rationales: dict[str, list[str]] = defaultdict(list)
    for p in passes:
        label = p.get("label")
        if label is None:
            continue
        counts[label] += 1
        rationale = p.get("rationale")
        if rationale:
            rationales[label].append(rationale)

    if not counts:
        return {"label": "undecided", "_votes": 0, "_reason": "no labels emitted"}, []

    winner_label, winner_votes = max(counts.items(), key=lambda kv: kv[1])
    all_labels = [{"label": lbl, "votes": v} for lbl, v in counts.items()]
    all_labels.sort(key=lambda x: -x["votes"])

    if winner_votes >= threshold:
        consensus = {
            "label": winner_label,
            "_votes": winner_votes,
            "rationales": rationales[winner_label],
        }
    else:
        consensus = {
            "label": "undecided",
            "_votes": winner_votes,
            "_reason": f"no label reached threshold {threshold}",
            "_distribution": all_labels,
        }
    return consensus, all_labels


def vote_generic_object(
    passes: list[dict],
    arrays_spec: dict[str, dict],
    ignore_fields: list[str],
    threshold: int,
) -> tuple[dict, dict]:
    """Single-object generic-structured — vote on each declared array; keep first
    non-empty value for ignored scalar fields.
    """
    consensus: dict[str, Any] = {}
    divergences: dict[str, Any] = {}
    for arr_name, arr_spec in arrays_spec.items():
        per_pass = [p.get(arr_name, []) or [] for p in passes]
        cons, div = vote_list(
            per_pass,
            arr_spec.get("fields", []),
            arr_spec.get("numeric_tolerance", {}) or {},
            threshold,
        )
        consensus[arr_name] = cons
        divergences[arr_name] = div

    for fname in ignore_fields:
        for p in passes:
            if fname in p and p[fname] not in (None, "", []):
                consensus[fname] = p[fname]
                break

    return consensus, divergences


def main() -> int:
    parser = argparse.ArgumentParser(description="Consensus vote consolidator")
    parser.add_argument("--schema", required=True, help="Path to spec YAML")
    parser.add_argument("--threshold", type=int, required=True)
    parser.add_argument("--passes", nargs="+", required=True, help="Pass JSON files")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    with open(args.schema) as f:
        spec = yaml.safe_load(f)

    pass_files = [Path(p) for p in args.passes]
    passes_data: list[Any] = []
    for pf in pass_files:
        if not pf.exists():
            continue  # failed pass — skipped silently here, surfaced by caller
        try:
            passes_data.append(json.loads(pf.read_text()))
        except json.JSONDecodeError as e:
            print(f"WARN: {pf} is not valid JSON: {e}", file=sys.stderr)

    if not passes_data:
        print("ERROR: no valid pass JSONs to vote on", file=sys.stderr)
        return 1

    template = spec.get("template", "")
    vote_key = spec.get("vote_key", {})
    threshold = args.threshold

    result: dict[str, Any] = {
        "template": template,
        "threshold": threshold,
        "passes_voted": len(passes_data),
        "passes_provided": len(pass_files),
    }

    if template == "classification" or vote_key.get("single_object") and not vote_key.get("arrays"):
        # Pure classification: pass-level objects with `label`.
        if not all(isinstance(p, dict) for p in passes_data):
            print("ERROR: classification expects each pass to be a JSON object", file=sys.stderr)
            return 1
        consensus, distribution = vote_classification(passes_data, threshold)
        result["consensus"] = consensus
        result["divergences"] = distribution
    elif vote_key.get("arrays"):
        # Generic-structured object with one or more voted arrays.
        if not all(isinstance(p, dict) for p in passes_data):
            print("ERROR: generic-structured expects each pass to be a JSON object", file=sys.stderr)
            return 1
        consensus, divergences = vote_generic_object(
            passes_data,
            vote_key["arrays"],
            vote_key.get("ignore_fields", []) or [],
            threshold,
        )
        result["consensus"] = consensus
        result["divergences"] = divergences
    else:
        # Default: list-of-items (finding-list, extraction, generic array).
        if not all(isinstance(p, list) for p in passes_data):
            print("ERROR: list templates expect each pass to be a JSON array", file=sys.stderr)
            return 1
        consensus, divergences = vote_list(
            passes_data,
            vote_key.get("fields", []),
            vote_key.get("numeric_tolerance", {}) or {},
            threshold,
        )
        result["consensus"] = consensus
        result["divergences"] = divergences

    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True))
    print(f"OK: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
