#!/usr/bin/env python3
"""Turn a raw Playwright recording into a PR demo mp4, plus a contact sheet.

Usage: edit.py <markers.json> <out.mp4> [--sheet sheet.png] [--wait-to 1.0]
       edit.py --self-test

markers.json is what record.js returns: {"video": ".../page@x.webm", "markers": [...]}.
A `cut` marker is dropped from the video; a `wait` marker longer than --wait-to is sped up
to last --wait-to seconds. An existing <out.mp4> is kept as <out>.prev.mp4.
"""
import argparse
import json
import os
import subprocess


def segments(markers, total, wait_to):
    """(start, end, speed) spans to keep, in order."""
    spans, cursor = [], 0.0
    for m in sorted(markers, key=lambda m: m["start"]):
        if m["start"] > cursor:
            spans.append((cursor, m["start"], 1.0))
        length = m["end"] - m["start"]
        if m["kind"] == "wait" and length > 0:
            spans.append((m["start"], m["end"], max(1.0, length / wait_to)))
        cursor = max(cursor, m["end"])
    if total > cursor:
        spans.append((cursor, total, 1.0))
    return [s for s in spans if s[1] - s[0] > 0.05]


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markers")
    ap.add_argument("out")
    ap.add_argument("--sheet")
    ap.add_argument("--wait-to", type=float, default=1.0)
    args = ap.parse_args()

    rec = json.load(open(args.markers))
    spans = segments(rec["markers"], duration(rec["video"]), args.wait_to)
    parts = [f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=(PTS-STARTPTS)/{sp:.3f}[v{i}]"
             for i, (s, e, sp) in enumerate(spans)]
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(spans))) \
        + f"concat=n={len(spans)}:v=1:a=0,fps=30[out]"

    if os.path.exists(args.out):
        root, ext = os.path.splitext(args.out)
        os.replace(args.out, f"{root}.prev{ext}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", rec["video"], "-filter_complex", graph,
                    "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "24",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out], check=True)

    length = duration(args.out)
    if args.sheet:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.out, "-vf",
                        f"fps=6/{length:.3f},scale=640:-1,tile=3x2", "-frames:v", "1",
                        args.sheet], check=True)
    print(f"{args.out}: {length:.1f}s, {os.path.getsize(args.out) / 1e6:.1f} MB")


def self_test():
    m = [{"kind": "cut", "label": "load", "start": 0, "end": 4},
         {"kind": "wait", "label": "extract", "start": 10, "end": 20},
         {"kind": "wait", "label": "toast", "start": 25, "end": 25.5}]
    assert segments(m, 30, 1.0) == [(4, 10, 1.0), (10, 20, 10.0), (20, 25, 1.0),
                                    (25, 25.5, 1.0), (25.5, 30, 1.0)]
    assert segments([], 12, 1.0) == [(0.0, 12, 1.0)]
    print("ok")


if __name__ == "__main__":
    import sys
    self_test() if sys.argv[1:] == ["--self-test"] else main()
