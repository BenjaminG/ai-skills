#!/usr/bin/env python3
"""Score a harness-review report against a labelled expected.md, item by item.

Usage: score.py <expected.md> <actual.md>
       score.py --self-check
"""
import re
import sys

ITEM = re.compile(r"(?P<loc>(?:thread|review|comment)#\d+(?:\.\d+)?)(?:\s+[^\s@,|]+)?\s+@(?P<author>[\w\[\]-]+)")
ACTIONABLE = {"1", "2", "3", "4"}


def keys(text):
    return {m["loc"] for m in ITEM.finditer(text)}


def parse(md):
    """Map every item key in a report to its level ('0'-'5' or 'drop')."""
    levels, header, section = {}, None, None
    for line in md.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            header = None
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
            elif not set(cells[0]) <= set("-: ") and "items" in header and "level" in header:
                level = re.sub(r"\D", "", cells[header.index("level")])[:1]
                for key in keys(cells[header.index("items")]):
                    levels[key] = level
            continue
        header = None
        if line.startswith("- "):
            level = "drop" if section == "dropped" else line[2:].split("·")[0].strip()
            for key in keys(line):
                levels[key] = level
    return collapse_lone_points(levels)


def collapse_lone_points(levels):
    """`review#3.1` alone is `review#3`: a sub-key only means something next to a sibling."""
    bases = [key.split(".")[0] for key in levels]
    return {(key.split(".")[0] if bases.count(key.split(".")[0]) == 1 else key): level
            for key, level in levels.items()}


def score(expected, actual):
    items = sorted(expected.keys() | actual.keys())
    agree = [k for k in items if expected.get(k) == actual.get(k)]
    exp_act = {k for k, v in expected.items() if v in ACTIONABLE}
    got_act = {k for k, v in actual.items() if v in ACTIONABLE}
    hit = exp_act & got_act
    return {
        "items": len(items),
        "agreement": len(agree) / len(items) if items else 1.0,
        "actionable_precision": len(hit) / len(got_act) if got_act else 1.0,
        "actionable_recall": len(hit) / len(exp_act) if exp_act else 1.0,
        "diffs": [(k, expected.get(k, "missing"), actual.get(k, "missing"))
                  for k in items if expected.get(k) != actual.get(k)],
    }


def main(expected_path, actual_path):
    result = score(parse(open(expected_path).read()), parse(open(actual_path).read()))
    print(f"items {result['items']} · agreement {result['agreement']:.0%} · "
          f"actionable P {result['actionable_precision']:.0%} R {result['actionable_recall']:.0%}")
    for key, want, got in result["diffs"]:
        print(f"  {key}: expected {want}, got {got}")


def self_check():
    expected = parse("""
| # | Cause | Items | Level | Coverage | Why |
|---|---|---|---|---|---|
| 1 | Guard tenant | thread#0 a.ts:4 @alice, thread#3 b.ts @cursor[bot] | 1 | none | helper |
| 2 | Ban clsx | thread#1 c.tsx:2 @bob | 2 | none | lint |

## Verdicts
- 0 · Local constant — thread#2 d.ts:1 @alice, review#4.2 @alice — one-off

## Dropped
- comment#0 @snyk-io-eu[bot] — dependency bot
""")
    assert expected == {"thread#0": "1", "thread#3": "1", "thread#1": "2", "thread#2": "0",
                        "review#4": "0", "comment#0": "drop"}, expected
    actual = dict(expected, **{"thread#1": "3", "thread#2": "2"})
    del actual["comment#0"]
    result = score(expected, actual)
    assert result["items"] == 6
    assert result["agreement"] == 3 / 6
    assert result["actionable_precision"] == 3 / 4   # thread#2 promoted from 0 to 2: a false fix
    assert result["actionable_recall"] == 1.0        # both expected fixes still actionable
    assert ("comment#0", "drop", "missing") in result["diffs"]
    assert parse("## Dropped\n- review#3.1 @a — x") == {"review#3": "drop"}
    assert set(parse("## Dropped\n- review#3.1 @a — x\n- review#3.2 @a — y")) == {"review#3.1", "review#3.2"}
    assert keys("thread#7 x.ts:4 @cursor[bot]") == keys("thread#7 x.ts:4 @cursor") == {"thread#7"}
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main(*sys.argv[1:3])
