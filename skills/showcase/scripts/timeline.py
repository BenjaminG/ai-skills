#!/usr/bin/env python3
"""Plan, time and mux a showcase video.

Usage:
  timeline.py table <script.json>
      The script as a Markdown table with estimated durations, for the user to approve.
  timeline.py build <script.json> --rec <name>=<markers.json> [...] [--voice-dir DIR] --out <timeline.json>
      The timeline stage.html plays: each shot's start and length, and for a chapter the
      output-time -> recording-time knots and its zoom targets.
  timeline.py mux <timeline.json> <silent.mp4> <out.mp4> [--sheet sheet.png]
      Lay the voice files on the rendered video (or copy it when there is no voice).
  timeline.py --self-test

A chapter lasts as long as its voice line (plus GAP). Without voice it lasts long enough to read
its caption and to play its action. Its recording is played at the speed that fits, between 1x
and MAX_RATE, and holds its last frame when the action is shorter than the voice.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pr-demo" / "scripts"))
from edit import duration, segments  # noqa: E402  pr-demo's cut/wait logic, shared on purpose

FPS = 30
GAP = 0.35          # silence after each voice line
MAX_RATE = 2.5      # fastest a chapter's recording may play to fit its voice
MIN_SHOT = 3.0      # shortest shot without voice
VOICE_WPS = 2.6     # words per second of a voice line, for the estimate
READ_WPS = 3.0      # words per second a viewer reads a caption


def words(*texts):
    return sum(len((t or "").split()) for t in texts)


def card_text(shot):
    return [shot.get(k) for k in ("kicker", "title", "subtitle", "accent")] + shot.get("badges", [])


def estimate(shot, voiced):
    """Seconds a shot should last, before any recording exists."""
    if voiced and shot.get("voice"):
        return round(words(shot["voice"]) / VOICE_WPS + GAP, 1)
    text = [shot.get("caption")] if shot["kind"] == "chapter" else card_text(shot)
    return round(max(MIN_SHOT, words(*text) / READ_WPS + 1.0), 1)


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
            screen = " / ".join(t for t in card_text(s) if t)
        else:
            name = f"{lab[s['id']]} · {s.get('caption', '')}"
            screen = s.get("show", "")
        cells = [s["id"], name, screen] + ([s.get("voice", "")] if voiced else []) + [f"{sec:g}"]
        rows.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    rows.append(f"\nTotal ≈ {total:.0f} s")
    return "\n".join(rows)


def chapter_span(rec, shot_id):
    for m in rec["markers"]:
        if m["kind"] == "chapter" and m["label"] == shot_id:
            return m["start"], m["end"]
    raise SystemExit(f"no chapter marker '{shot_id}' in {rec['video']}")


def kept(rec, start, end, total):
    """The (start, end, speed) spans of [start, end] that survive cuts and waits."""
    edits = [m for m in rec["markers"] if m["kind"] in ("cut", "wait")]
    out = []
    for s, e, sp in segments(edits, total, 1.0):
        s, e = max(s, start), min(e, end)
        if e - s > 0.01:
            out.append((s, e, sp))
    return out


def knots(spans, dur):
    """Output-time -> recording-time knots for a chapter of `dur` seconds, and its rate.

    A jump between two knots at the same output time is a cut. The last knot holds the final
    frame when the action ends before `dur`.
    """
    natural = sum((e - s) / sp for s, e, sp in spans)
    rate = min(MAX_RATE, max(1.0, natural / dur)) if dur > 0 else 1.0
    out, o = [], 0.0
    for s, e, sp in spans:
        out.append([round(o, 3), s])
        o += (e - s) / (sp * rate)
        out.append([round(o, 3), e])
    if o < dur:
        out.append([round(dur, 3), spans[-1][1]])
    return out, rate, max(dur, o)


def to_out(spans, rate, raw):
    """Output time of a recording time inside a chapter (a time inside a cut snaps forward)."""
    o = 0.0
    for s, e, sp in spans:
        if raw < s:
            return o
        if raw <= e:
            return o + (raw - s) / (sp * rate)
        o += (e - s) / (sp * rate)
    return o


def build(script, recs, voice_dir):
    voiced = script.get("voice", True) and voice_dir is not None
    lab, shots, audio, t = labels(script["shots"]), [], [], 0.0
    # "total" stands in for the video length in the self-test, where no video exists
    totals = {n: duration(r["video"]) if os.path.exists(r["video"]) else r.get("total", 0)
              for n, r in recs.items()}
    for s in script["shots"]:
        voice_file = None
        if voiced and s.get("voice"):
            voice_file = os.path.join(voice_dir, f"{s['id']}.mp3")
            if not os.path.exists(voice_file):
                raise SystemExit(f"missing voice file {voice_file}")
        want = duration(voice_file) + GAP if voice_file else None
        shot = {k: v for k, v in s.items() if k not in ("voice", "show")}
        if s["kind"] == "card":
            dur = max(want or 0, estimate(s, False))   # a short line still leaves time to read the card
        else:
            name = s.get("rec", "main")
            rec = recs[name]
            cs, ce = chapter_span(rec, s["id"])
            spans = kept(rec, cs, ce, totals[name])
            natural = sum((e - b) / sp for b, e, sp in spans)
            dur = max(want or natural, estimate(s, False))
            shot["map"], rate, dur = knots(spans, dur)
            shot["focus"] = [{"t": round(to_out(spans, rate, m["start"]), 3), "box": m.get("box")}
                             for m in rec["markers"] if m["kind"] == "focus" and cs <= m["start"] <= ce]
            shot["rec"], shot["label"] = name, lab[s["id"]]
        shot["start"], shot["dur"] = round(t, 3), round(dur, 3)
        if voice_file:
            audio.append({"file": os.path.abspath(voice_file), "start": round(t, 3)})
        shots.append(shot)
        t += dur
    return {"fps": FPS, "size": [1920, 1080], "duration": round(t, 3),
            "recs": {n: {"video": os.path.abspath(r["video"])} for n, r in recs.items()},
            "shots": shots, "audio": audio}


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
    length = duration(out)
    if sheet:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf",
                        f"fps=12/{length:.3f},scale=640:-1,tile=4x3", "-frames:v", "1", sheet], check=True)
    print(f"{out}: {length:.1f}s, {os.path.getsize(out) / 1e6:.1f} MB, "
          f"{'voice' if tl['audio'] else 'no audio'}")


def self_test():
    # A chapter from 10 to 30 s with a 4 s load cut and an 8 s wait sped up to 1 s.
    rec = {"video": "rec.webm", "total": 40, "markers": [
        {"kind": "chapter", "label": "c1", "start": 10, "end": 30},
        {"kind": "cut", "label": "load", "start": 10, "end": 14},
        {"kind": "wait", "label": "extract", "start": 18, "end": 26},
        {"kind": "focus", "label": "brief", "start": 16, "end": 16, "box": {"x": 1, "y": 2, "width": 3, "height": 4}},
        {"kind": "focus", "label": "out", "start": 27, "end": 27, "box": None}]}
    spans = kept(rec, 10, 30, 40)
    assert spans == [(14, 18, 1.0), (18, 26, 8.0), (26, 30, 1.0)], spans
    # Natural length 4 + 1 + 4 = 9 s. A 6 s voice line plays it at 1.5x.
    k, rate, dur = knots(spans, 6.0)
    assert rate == 1.5 and dur == 6.0 and k[0] == [0.0, 14] and k[-1] == [6.0, 30], (k, rate, dur)
    # A 12 s voice line plays it at 1x and holds the last frame for 3 s.
    k, rate, dur = knots(spans, 12.0)
    assert rate == 1.0 and k[-2] == [9.0, 30] and k[-1] == [12.0, 30], k
    # A 2 s voice line would need 4.5x: capped, so the chapter outlasts the voice.
    k, rate, dur = knots(spans, 2.0)
    assert rate == MAX_RATE and dur == 9 / MAX_RATE, (rate, dur)
    # Focus at 16 s is 2 s into the kept action; a time inside a cut snaps to the next span.
    assert to_out(spans, 1.0, 16) == 2.0 and to_out(spans, 1.0, 12) == 0.0
    assert to_out(spans, 1.0, 27) == 6.0

    script = {"voice": False, "shots": [
        {"id": "intro", "kind": "card", "kicker": "Weekly update", "title": "Redesign pod",
         "subtitle": "This week's progress", "badges": ["Work in progress"]},
        {"id": "before", "kind": "chapter", "rec": "main", "label": "Before", "caption": "Five tabs"},
        {"id": "c1", "kind": "chapter", "rec": "main", "caption": "What your twin needs from you"}]}
    assert labels(script["shots"]) == {"before": "Before", "c1": "01"}
    rec2 = {"video": "rec.webm", "total": 40, "markers": rec["markers"] + [
        {"kind": "chapter", "label": "before", "start": 0, "end": 10}]}
    tl = build(script, {"main": rec2}, None)
    intro, before, c1 = tl["shots"]
    assert intro["start"] == 0 and intro["dur"] == 4.3, intro             # 10 words read at 3/s + 1
    assert before["start"] == 4.3 and before["dur"] == 10.0, before        # action outlasts caption
    assert c1["dur"] == 9.0 and c1["label"] == "01" and len(c1["focus"]) == 2, c1
    assert tl["audio"] == [] and tl["duration"] == 23.3

    t = table({"voice": True, "shots": [{"id": "c1", "kind": "chapter", "caption": "The brief",
                                         "show": "brief card", "voice": "one two three four five six seven eight nine ten eleven twelve thirteen"}]})
    assert "| c1 | 01 · The brief | brief card |" in t and "| 5.3 |" in t, t
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
        recs = {}
        for r in a.rec:
            name, path = r.split("=", 1)
            recs[name] = json.load(open(path))
        tl = build(json.load(open(a.script)), recs, a.voice_dir)
        json.dump(tl, open(a.out, "w"), indent=1)
        print(f"{a.out}: {len(tl['shots'])} shots, {tl['duration']:.1f}s")
    else:
        mux(json.load(open(a.timeline)), a.silent, a.out, a.sheet)


if __name__ == "__main__":
    main()
