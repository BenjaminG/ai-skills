#!/usr/bin/env python3
"""Plan, time and mux a showcase video, on pr-demo's montage engine.

Usage:
  timeline.py table <script.json>
      The script as a Markdown table with estimated durations, for the user to approve.
  timeline.py build <script.json> --rec <name>=<markers.json> [...] [--voice-dir DIR] --out <timeline.json>
      The timeline pr-demo's stage.html plays: each shot's start and length, and for a chapter the
      output-time -> recording-time knots, its zooms and its cursor. A name given again is a retake
      (record.js's TAKE): its chapters replace the earlier takes'.
  timeline.py mux <timeline.json> <silent.mp4> <out.mp4> [--sheet sheet.png]
      Lay the voice files on the rendered video (or copy it when there is no voice).
  timeline.py --self-test

A chapter plays its recording at 1x: it lasts as long as its action or its voice line (plus GAP),
whichever is longer, then holds its last frame TAIL seconds so the viewer reads the result. The
voice stops when its line ends: silence while the action finishes is natural. Without voice the
chapter also lasts long enough to read its caption.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pr-demo" / "scripts"))
import engine  # noqa: E402  pr-demo's montage engine, shared on purpose

GAP = 0.35          # silence after each voice line
TAIL = 1.5          # a chapter holds its last frame this long before the next shot
INTRO = 1.8         # a chapter opens on its title, over its first frame held still this long
VOICE_WPS = 2.6     # words per second of a voice line, for the estimate


def estimate(shot, voiced):
    """Seconds a shot should last, before any recording exists."""
    intro = INTRO if shot["kind"] == "chapter" and shot.get("caption") else 0.0
    if voiced and shot.get("voice"):
        return round(engine.words(shot["voice"]) / VOICE_WPS + GAP + intro, 1)
    texts = [shot.get("caption")] if shot["kind"] == "chapter" else engine.card_text(shot)
    return round(engine.read_time(texts) + intro, 1)


def labels(shots):
    """Chapter pill text: an explicit label ("Before"), else 01, 02, ..."""
    out, n = {}, 0
    for s in shots:
        if s["kind"] == "chapter":
            if s.get("label"):
                out[s["id"]] = s["label"]
            else:
                n += 1
                out[s["id"]] = f"{n:02d}"
    return out


def table(script):
    voiced = script.get("voice", True)
    head = "| # | Shot | On screen | Voice-over | ~s |" if voiced else "| # | Shot | On screen | ~s |"
    rows = [head, "|" + "---|" * (head.count("|") - 1)]
    lab, total = labels(script["shots"]), 0.0
    for s in script["shots"]:
        sec = estimate(s, voiced)
        total += sec
        if s["kind"] == "card":
            name = f"card · {s.get('title', '')}"
            screen = " / ".join(t for t in engine.card_text(s) if t)
        else:
            name = f"{lab[s['id']]} · {s.get('caption', '')}"
            screen = s.get("show", "")
        cells = [s["id"], name, screen] + ([s.get("voice", "")] if voiced else []) + [f"{sec:g}"]
        rows.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    rows.append(f"\nTotal ≈ {total:.0f} s")
    return "\n".join(rows)


def build(script, named, voice_dir):
    """`named`: the recordings as (name, markers), in the order filmed."""
    voiced = script.get("voice", True) and voice_dir is not None
    lab, files, want = labels(script["shots"]), {}, {}
    for s in script["shots"]:
        if voiced and s.get("voice"):
            f = os.path.join(voice_dir, f"{s['id']}.mp3")
            if not os.path.exists(f):
                raise SystemExit(f"missing voice file {f}")
            files[s["id"]], want[s["id"]] = f, engine.duration(f) + GAP
    recs, last = engine.takes(named)
    shots = [{**s, "label": lab[s["id"]], "rec": last.get((s.get("rec", "main"), s["id"]), s.get("rec", "main"))}
             if s["kind"] == "chapter" else s for s in script["shots"]]
    tl = engine.build(shots, recs, want, max_rate=1.0, tail=TAIL)
    t = 0.0
    for s in tl["shots"]:
        if s["kind"] == "chapter" and s.get("caption"):
            with_intro(s)
        s["start"] = round(t, 3)
        t += s["dur"]
    tl["duration"] = round(t, 3)
    # a chapter's voice starts as its title leaves
    starts = {s["id"]: s["start"] + max(0.0, s.get("intro", 0) - 0.4) for s in tl["shots"]}
    tl["audio"] = [{"file": os.path.abspath(f), "start": round(starts[i], 3)} for i, f in files.items()]
    return tl


def with_intro(s):
    """Open a chapter on INTRO seconds of its first frame, held still under its title: everything
    the chapter plays moves INTRO seconds later."""
    def later(t):
        return round(t + INTRO, 3)

    s["intro"] = INTRO
    s["map"] = [[0.0, s["map"][0][1]]] + [[later(o), r] for o, r in s["map"]]
    s["focus"] = [{**f, "t": later(f["t"])} for f in s["focus"]]
    s["cursor"] = {"moves": [{**m, "t0": later(m["t0"]), "t1": later(m["t1"])} for m in s["cursor"]["moves"]],
                   "clicks": [later(c) for c in s["cursor"]["clicks"]]}
    s["dur"] = later(s["dur"])


def mux(tl, silent, out, sheet):
    if os.path.exists(out):
        root, ext = os.path.splitext(out)
        os.replace(out, f"{root}.prev{ext}")
    if tl["audio"]:
        inputs, chains = ["-i", silent], []
        for i, a in enumerate(tl["audio"], start=1):
            inputs += ["-i", a["file"]]
            ms = int(a["start"] * 1000)
            chains.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(1, len(tl["audio"]) + 1))
        graph = ";".join(chains) + f";{mix}amix=inputs={len(tl['audio'])}:normalize=0[aout]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph,
                        "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{tl['duration']:.3f}", "-movflags", "+faststart", out], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-c", "copy", "-an",
                        "-movflags", "+faststart", out], check=True)
    if sheet:
        engine.sheet(out, sheet, "4x3")
    print(f"{out}: {engine.duration(out):.1f}s, {os.path.getsize(out) / 1e6:.1f} MB, "
          f"{'voice' if tl['audio'] else 'no audio'}")


def self_test():
    script = {"voice": False, "shots": [
        {"id": "intro", "kind": "card", "kicker": "Weekly update", "title": "Redesign pod",
         "subtitle": "This week's progress", "badges": ["Work in progress"]},
        {"id": "before", "kind": "chapter", "rec": "main", "label": "Before", "caption": "Five tabs"},
        {"id": "c1", "kind": "chapter", "rec": "main", "caption": "What your twin needs from you"}]}
    assert labels(script["shots"]) == {"before": "Before", "c1": "01"}
    rec = {"video": "rec.webm", "total": 40, "markers": [
        {"kind": "chapter", "label": "before", "start": 0, "end": 10},
        {"kind": "chapter", "label": "c1", "start": 10, "end": 30},
        {"kind": "cut", "label": "load", "start": 10, "end": 14},
        {"kind": "wait", "label": "extract", "start": 18, "end": 26},
        {"kind": "focus", "label": "brief", "start": 16, "end": 16, "box": {"x": 1, "y": 2, "width": 3, "height": 4}},
        {"kind": "focus", "label": "out", "start": 27, "end": 27, "box": None}]}
    tl = build(script, [("main", rec)], None)
    intro, before, c1 = tl["shots"]
    assert intro["start"] == 0 and intro["dur"] == 4.3, intro             # 10 words read at 3/s + 1
    assert before["start"] == 4.3 and before["dur"] == 13.3, before        # INTRO + action (outlasts caption) + TAIL
    assert c1["start"] == 17.6 and c1["dur"] == 12.3 and c1["label"] == "01" and len(c1["focus"]) == 2, c1
    assert c1["focus"][0]["light"] and c1["caption"] == "What your twin needs from you"
    assert tl["audio"] == [] and tl["duration"] == 29.9
    # The title holds the chapter's first frame; its action, zooms and cursor all start INTRO later.
    assert c1["map"][0] == [0.0, c1["map"][1][1]] and c1["map"][1][0] == INTRO, c1["map"]
    assert c1["focus"][0]["t"] >= INTRO
    # A retake of c1 alone: c1 plays from it, "before" from the first take.
    retake = {"video": "rec-2.webm", "total": 9, "markers": [{"kind": "chapter", "label": "c1", "start": 1, "end": 7}]}
    tl = build(script, [("main", rec), ("main", retake)], None)
    assert [(s["id"], s.get("rec")) for s in tl["shots"]] == [("intro", None), ("before", "main"), ("c1", "main-2")]
    assert tl["shots"][2]["map"][1][1] == 1 and set(tl["recs"]) == {"main", "main-2"}, tl

    t = table({"voice": True, "shots": [{"id": "c1", "kind": "chapter", "caption": "The brief",
                                         "show": "brief card", "voice": "one two three four five six seven eight nine ten eleven twelve thirteen"}]})
    assert "| c1 | 01 · The brief | brief card |" in t and "| 7.1 |" in t, t
    assert "Voice-over" not in table({**script, "voice": False})
    print("ok")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("table")
    t.add_argument("script")
    b = sub.add_parser("build")
    b.add_argument("script")
    b.add_argument("--rec", action="append", required=True, help="name=markers.json")
    b.add_argument("--voice-dir")
    b.add_argument("--out", required=True)
    m = sub.add_parser("mux")
    m.add_argument("timeline")
    m.add_argument("silent")
    m.add_argument("out")
    m.add_argument("--sheet")
    a = ap.parse_args()
    if a.cmd == "table":
        print(table(json.load(open(a.script))))
    elif a.cmd == "build":
        named = []
        for r in a.rec:
            name, path = r.split("=", 1)
            named.append((name, json.load(open(path))))
        tl = build(json.load(open(a.script)), named, a.voice_dir)
        json.dump(tl, open(a.out, "w"), indent=1)
        print(f"{a.out}: {len(tl['shots'])} shots, {tl['duration']:.1f}s")
    else:
        mux(json.load(open(a.timeline)), a.silent, a.out, a.sheet)


if __name__ == "__main__":
    main()
