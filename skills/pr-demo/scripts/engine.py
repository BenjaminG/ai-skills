#!/usr/bin/env python3
"""The montage engine pr-demo and showcase share: from a recording's markers to the timeline that
assets/stage.html plays (render.js films it), then a contact sheet.

Usage:
  engine.py demo <markers.json> --out <timeline.json>
      A PR demo: one chapter per `scenario` of the recording, each after a card naming it when
      there are several; the whole recording as one chapter when there is none.
  engine.py sheet <video.mp4> <sheet.png> [--tiles 3x2]
  engine.py jumps <video.mp4> <timeline.json> <jumps.png>
      Frames that change at once (a page that jumps, a light that snaps off): one row per jump in
      jumps.png, the frame before | the frame, and where it falls in the recording.
  engine.py --self-test

Markers come from assets/record.js:
  cut      dropped from the video (page loads, off-camera setup)
  wait     sped up to last WAIT_TO seconds (server work)
  chapter  a showcase shot or a pr-demo scenario, by its label
  act      a click or a typing, with the element's box: the camera zooms on it
  focus    showcase: zoom on an element and light it (box null: zoom out); overrides the acts
  move     the cursor going from one point to another; click: the cursor pressing
"""
import argparse
import json
import os
import re
import subprocess
import tempfile

FPS = 30
WAIT_TO = 1.0       # a wait marker plays in this many seconds
MAX_RATE = 2.5      # fastest a chapter's recording may play to fit a voice line
MIN_SHOT = 3.0      # shortest shot
READ_WPS = 3.0      # words per second a viewer reads on screen
HOLD = 2.5          # the camera stays zoomed this long after an act, and pans when the next comes sooner
END_CLEAR = 1.2     # every chapter ends on the whole page for at least this long
START_CLEAR = 1.0   # and opens on it for this long before any zoom
MIN_ZOOM = 0.8      # an act with less room than this before the zoom-out gets no zoom
JUMP = 1.0          # mean difference (ffmpeg scdet's mafd) of a frame that changes at once...
JUMP_ALONE = 2.5    # ...this many times more than each of the two frames on either side: a glide
                    # (scroll, zoom) changes every frame a little, a jump one frame a lot
JUMP_ROWS = 8       # most jumps jumps.png shows, the strongest


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


def words(*texts):
    return sum(len((t or "").split()) for t in texts)


def card_text(shot):
    return [shot.get(k) for k in ("kicker", "title", "subtitle", "accent")] + shot.get("badges", [])


def read_time(texts):
    return round(max(MIN_SHOT, words(*texts) / READ_WPS + 1.0), 1)


def chapter_span(rec, shot_id):
    for m in rec["markers"]:
        if m["kind"] == "chapter" and m["label"] == shot_id:
            return m["start"], m["end"]
    raise SystemExit(f"no chapter marker '{shot_id}' in {rec['video']}")


def kept(rec, start, end, total):
    """The (start, end, speed) spans of [start, end] that survive cuts and waits."""
    edits = [m for m in rec["markers"] if m["kind"] in ("cut", "wait")]
    out = []
    for s, e, sp in segments(edits, total, WAIT_TO):
        s, e = max(s, start), min(e, end)
        if e - s > 0.01:
            out.append((s, e, sp))
    return out


def knots(spans, dur, max_rate=MAX_RATE, tail=0.0):
    """Output-time -> recording-time knots for a chapter of `dur` seconds, and its rate.

    A jump between two knots at the same output time is a cut. The last knot holds the final
    frame when the action ends before `dur`, and `tail` seconds more after it.
    """
    natural = sum((e - s) / sp for s, e, sp in spans)
    rate = min(max_rate, max(1.0, natural / dur)) if dur > 0 else 1.0
    out, o = [], 0.0
    for s, e, sp in spans:
        out.append([round(o, 3), s])
        o += (e - s) / (sp * rate)
        out.append([round(o, 3), e])
    end = max(dur, o) + tail
    if o < end:
        out.append([round(end, 3), spans[-1][1]])
    return out, rate, end


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


def zooms(markers, cs, ce, opening=None):
    """Camera targets of a chapter in recording time: [{t, box, light}], box None = whole page.

    Each act zooms on its element and holds HOLD seconds; a sooner act pans there instead. A wait
    or a cut zooms out, and so does the chapter's last END_CLEAR seconds. An explicit focus lights
    its element and silences the acts until the next focus marker. Nothing zooms before `opening`:
    the chapter shows the whole page first.
    """
    opening = cs if opening is None else opening
    inside = sorted((m for m in markers if cs <= m["start"] <= ce), key=lambda m: m["start"])
    focus = [m for m in inside if m["kind"] == "focus"]
    held = [(f["start"], focus[i + 1]["start"] if i + 1 < len(focus) else ce)
            for i, f in enumerate(focus) if f.get("box")]
    breaks = [m["start"] for m in inside if m["kind"] in ("wait", "cut")]

    def is_held(t):
        return any(s <= t < e for s, e in held)

    out, until = [], None
    for a in (m for m in inside if m["kind"] == "act" and m.get("box")):
        if is_held(a["start"]):
            continue
        start = max(a["start"], opening)
        end = min([a["end"] + HOLD, ce - END_CLEAR] + [b for b in breaks if b >= a["end"]])
        zoomed = until is not None and start <= until
        if not zoomed and end - start < MIN_ZOOM:   # already zoomed, a short act still gets the pan
            continue
        if until is not None and not zoomed:
            out.append({"t": until, "box": None, "light": False})
        out.append({"t": start, "box": a["box"], "light": False})
        until = end
    if until is not None:
        out.append({"t": until, "box": None, "light": False})
    out = [z for z in out if not is_held(z["t"])]
    out += [{"t": max(f["start"], opening), "box": f.get("box"), "light": bool(f.get("box"))} for f in focus]
    return sorted(out, key=lambda z: z["t"])


def out_times(spans, rate, entries):
    """Map entries to output time; of several landing on one instant (a cut), the last wins."""
    out = []
    for z in entries:
        z = {**z, "t": round(to_out(spans, rate, z["t"]), 3)}
        if out and out[-1]["t"] == z["t"]:
            out[-1] = z
        else:
            out.append(z)
    return out


def cursor(markers, cs, ce, spans, rate):
    """The cursor the stage draws, in output time: its moves and its clicks."""
    def o(t):
        return round(to_out(spans, rate, t), 3)

    inside = [m for m in markers if cs <= m["start"] <= ce]
    moves = [{"t0": o(m["start"]), "t1": o(m["end"]), "from": m["from"], "to": m["to"]}
             for m in sorted(inside, key=lambda m: m["start"]) if m["kind"] == "move"]
    return {"moves": moves, "clicks": sorted(o(m["start"]) for m in inside if m["kind"] == "click")}


def build(shots, recs, want=None, max_rate=MAX_RATE, tail=0.0):
    """The timeline stage.html plays. `want` gives a shot the length it should last (a voice line);
    `max_rate` and `tail` go to knots()."""
    want = want or {}
    # "total" stands in for the video length in the self-tests, where no video exists
    totals = {n: duration(r["video"]) if os.path.exists(r["video"]) else r.get("total", 0)
              for n, r in recs.items()}
    out, t = [], 0.0
    for s in shots:
        shot = {k: v for k, v in s.items() if k not in ("voice", "show")}
        w = want.get(s["id"])
        if s["kind"] == "card":
            dur = max(w or 0, read_time(card_text(s)))   # a short line still leaves time to read the card
        else:
            name = s.get("rec", "main")
            rec = recs[name]
            cs, ce = chapter_span(rec, s["id"])
            spans = kept(rec, cs, ce, totals[name])
            natural = sum((e - b) / sp for b, e, sp in spans)
            dur = max(w or natural, read_time([s.get("caption")]))
            shot["map"], rate, dur = knots(spans, dur, max_rate, tail)
            shot["focus"] = out_times(spans, rate, zooms(rec["markers"], cs, ce, spans[0][0] + START_CLEAR))
            shot["cursor"] = cursor(rec["markers"], cs, ce, spans, rate)
            shot["rec"] = name
        shot["start"], shot["dur"] = round(t, 3), round(dur, 3)
        out.append(shot)
        t += dur
    return {"fps": FPS, "size": [1920, 1080], "duration": round(t, 3),
            "recs": {n: {"video": os.path.abspath(r["video"])} for n, r in recs.items()},
            "shots": out}


def demo(rec, total):
    """A PR demo's shots: its scenarios, each after a card when there are several."""
    scenarios = sorted((m for m in rec["markers"] if m["kind"] == "chapter"), key=lambda m: m["start"])
    if not scenarios:
        rec["markers"].append({"kind": "chapter", "label": "demo", "start": 0.0, "end": total})
        return [{"id": "demo", "kind": "chapter"}]
    if len(scenarios) == 1:
        return [{"id": scenarios[0]["label"], "kind": "chapter"}]
    shots = []
    for i, m in enumerate(scenarios):
        shots.append({"id": f"card-{i + 1}", "kind": "card", "title": m["label"],
                      **({"subtitle": m["subtitle"]} if m.get("subtitle") else {})})
        shots.append({"id": m["label"], "kind": "chapter"})
    return shots


def sheet(video, png, tiles="3x2"):
    cols, rows = map(int, tiles.split("x"))
    length = duration(video)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
                    f"fps={cols * rows}/{length:.3f},scale=640:-1,tile={tiles}", "-frames:v", "1", png],
                   check=True)


def raw_at(knots_, lt):
    """Recording time at output time `lt` of a chapter: stage.html's rawAt."""
    i = 0
    while i + 1 < len(knots_) and knots_[i + 1][0] <= lt:
        i += 1
    (o0, r0), nxt = knots_[i], knots_[i + 1] if i + 1 < len(knots_) else None
    if nxt is None or nxt[0] == o0:
        return r0
    return r0 + (nxt[1] - r0) * (lt - o0) / (nxt[0] - o0)


def find_jumps(diffs, tl, rows=JUMP_ROWS):
    """[(t, diff, where)] of the chapter frames that change at once, shot changes left out.
    `diffs`: (time, mean difference from the frame before) of every frame of the video."""
    def shot_at(t):
        return next((x for x in tl["shots"] if x["start"] <= t < x["start"] + x["dur"]), None)

    bounds = [s["start"] for s in tl["shots"]] + [tl["duration"]]
    hits = [(t, d) for i, (t, d) in enumerate(diffs)
            if d >= JUMP and all(n * JUMP_ALONE < d for _, n in diffs[max(0, i - 2):i] + diffs[i + 1:i + 3])
            and all(abs(t - b) > 0.4 for b in bounds) and (shot_at(t) or {}).get("kind") == "chapter"]
    out = []
    for t, d in sorted(hits, key=lambda h: -h[1])[:rows]:
        shot = shot_at(t)
        lt, m = t - shot["start"], shot["map"]
        near = 1.5 / tl["fps"]
        if any(a[0] == b[0] and a[1] != b[1] and abs(a[0] - lt) < near for a, b in zip(m, m[1:])):
            how = ", a cut"
        elif any(a[0] < lt <= b[0] + near and b[1] - a[1] > 1.01 * (b[0] - a[0]) for a, b in zip(m, m[1:])):
            how = ", in a sped-up wait"
        else:
            how = ""
        out.append((t, d, f"'{shot['id']}' at {lt:.2f}s, recording {raw_at(m, lt):.2f}s{how}"))
    return sorted(out)


def jumps(video, tl, png):
    log = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", "scale=480:-1,scdet=threshold=0,metadata=print:file=-",
                          "-f", "null", "-"], capture_output=True, text=True, check=True).stdout
    diffs = [(float(t), float(d)) for t, d in re.findall(r"pts_time:([\d.]+)\nlavfi\.scd\.mafd=([\d.]+)", log)]
    found = find_jumps(diffs, tl)
    if not found:
        print("no jump")
        return
    with tempfile.TemporaryDirectory() as tmp:
        rows = []
        for i, (t, _, _) in enumerate(found):
            row = os.path.join(tmp, f"{i}.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, t - 1 / tl['fps']):.3f}", "-i", video,
                            "-frames:v", "1", "-vf", "scale=800:-1,tile=2x1:padding=8", row], check=True)
            rows.append(row)
        inputs = [a for r in rows for a in ("-i", r)]
        stack = f"vstack=inputs={len(rows)}" if len(rows) > 1 else "null"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", stack, png], check=True)
    for i, (t, d, where) in enumerate(found, start=1):
        print(f"row {i}: {t:.2f}s (diff {d:.1f}) — {where}")
    print(png)


def self_test():
    m = [{"kind": "cut", "label": "load", "start": 0, "end": 4},
         {"kind": "wait", "label": "extract", "start": 10, "end": 20},
         {"kind": "wait", "label": "toast", "start": 25, "end": 25.5}]
    assert segments(m, 30, 1.0) == [(4, 10, 1.0), (10, 20, 10.0), (20, 25, 1.0),
                                    (25, 25.5, 1.0), (25.5, 30, 1.0)]
    assert segments([], 12, 1.0) == [(0.0, 12, 1.0)]

    # A chapter from 10 to 30 s with a 4 s load cut and an 8 s wait sped up to 1 s.
    rec = {"video": "rec.webm", "total": 40, "markers": [
        {"kind": "chapter", "label": "c1", "start": 10, "end": 30},
        {"kind": "cut", "label": "load", "start": 10, "end": 14},
        {"kind": "wait", "label": "extract", "start": 18, "end": 26}]}
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
    # At max_rate 1 the same chapter plays its 9 s at 1x, past the voice, then holds a 1.5 s tail.
    k, rate, dur = knots(spans, 2.0, max_rate=1.0, tail=1.5)
    assert rate == 1.0 and dur == 10.5 and k[-2] == [9.0, 30] and k[-1] == [10.5, 30], (k, rate, dur)
    # A time 2 s into the kept action; a time inside a cut snaps to the next span.
    assert to_out(spans, 1.0, 16) == 2.0 and to_out(spans, 1.0, 12) == 0.0
    assert to_out(spans, 1.0, 27) == 6.0

    # Zooms. A and B are 1 s apart: the camera pans from A to B. The wait at 6 zooms out.
    # C zooms out HOLD after it ends. D sits in the chapter's last END_CLEAR seconds: no zoom.
    box = lambda n: {"x": n, "y": n, "width": 100, "height": 40}  # noqa: E731
    act = lambda s, e, n: {"kind": "act", "label": "click", "start": s, "end": e, "box": box(n)}  # noqa: E731
    acts = [act(2, 3, 1), act(4, 5, 2), {"kind": "wait", "label": "save", "start": 6, "end": 16},
            act(17, 18, 3), act(28.5, 29, 4)]
    z = zooms(acts, 0, 30)
    assert [(e["t"], e["box"] and e["box"]["x"]) for e in z] == \
        [(2, 1), (4, 2), (6, None), (17, 3), (20.5, None)], z
    assert not any(e["light"] for e in z)
    # A click right before a wait has no room for a zoom of its own, but the camera pans to it.
    z = zooms([act(2, 3, 1), act(3.5, 4, 2), {"kind": "wait", "label": "save", "start": 4.1, "end": 9}], 0, 30)
    assert [(e["t"], e["box"] and e["box"]["x"]) for e in z] == [(2, 1), (3.5, 2), (4.1, None)], z
    # An explicit focus from 3.5 to 5.5 lights its element and silences B.
    f = [{"kind": "focus", "label": "brief", "start": 3.5, "end": 3.5, "box": box(9)},
         {"kind": "focus", "label": "out", "start": 5.5, "end": 5.5, "box": None}]
    z = zooms(acts + f, 0, 30)
    assert [(e["t"], e["box"] and e["box"]["x"], e["light"]) for e in z] == \
        [(2, 1, False), (3.5, 9, True), (5.5, None, False), (5.5, None, False),
         (17, 3, False), (20.5, None, False)], z
    # Mapped to output time, the two zoom-outs at 5.5 collapse into one.
    assert [e["t"] for e in out_times([(0, 30, 1.0)], 1.0, z)] == [2, 3.5, 5.5, 17, 20.5]

    # A chapter opens on the whole page. A click at its first frame, then a wait 0.6 s later: no
    # room for a zoom once START_CLEAR has passed. A longer click zooms at the end of the opening,
    # and a focus at the first frame waits for it too.
    wait = lambda s, e: {"kind": "wait", "label": "reload", "start": s, "end": e}  # noqa: E731
    assert zooms([act(10, 11.6, 1), wait(11.6, 12)], 10, 20, 11) == []
    z = zooms([act(10, 12, 1)], 10, 20, 11)
    assert [(e["t"], e["box"] and e["box"]["x"]) for e in z] == [(11, 1), (14.5, None)], z
    z = zooms([{"kind": "focus", "label": "card", "start": 10, "end": 10, "box": box(9)}], 10, 20, 11)
    assert [(e["t"], e["light"]) for e in z] == [(11, True)], z

    # Jumps, on a card then a chapter with a cut 5 s in, every frame a little noisy. Found: a frame
    # alone in changing much, and the cut. Left out: a change in the card, one at the shot change, a
    # glide of 15 frames changing as much as the jump, a lone frame under JUMP.
    tl = {"fps": 30, "duration": 13, "shots": [
        {"id": "card-1", "kind": "card", "start": 0, "dur": 3},
        {"id": "c", "kind": "chapter", "start": 3, "dur": 10, "map": [[0, 1], [5, 6], [5, 9], [10, 14]]}]}
    diff = {30: 9.0, 96: 5.0, 181: 6.0, 240: 3.0, 290: 0.8} | {i: 6.0 for i in range(200, 215)}
    found = find_jumps([(i / 30, diff.get(i, 0.01)) for i in range(390)], tl)
    assert [(round(t, 3), d) for t, d, _ in found] == [(6.033, 6.0), (8.0, 3.0)], found
    assert "recording 4.03s" in found[0][2] and "cut" not in found[0][2], found
    assert found[1][2].endswith("recording 9.00s, a cut"), found

    # The cursor follows the chapter's clock: a move after the 4 s cut starts at 0 s.
    mv = [{"kind": "move", "label": "", "start": 14.5, "end": 15, "from": {"x": 0, "y": 0}, "to": {"x": 9, "y": 9}},
          {"kind": "click", "label": "click", "start": 15.2, "end": 15.2},
          {"kind": "move", "label": "", "start": 5, "end": 6, "from": {"x": 0, "y": 0}, "to": {"x": 1, "y": 1}}]
    c = cursor(mv, 10, 30, spans, 1.0)
    assert c == {"moves": [{"t0": 0.5, "t1": 1.0, "from": {"x": 0, "y": 0}, "to": {"x": 9, "y": 9}}],
                 "clicks": [1.2]}, c

    # A demo with two scenarios: a card before each. With one: no card. With none: the whole video.
    two = {"video": "rec.webm", "total": 20, "markers": [
        {"kind": "chapter", "label": "Add a venue", "subtitle": "From the list", "start": 0, "end": 8},
        {"kind": "chapter", "label": "Delete it", "start": 8, "end": 20}]}
    shots = demo(two, 20)
    assert [s["kind"] for s in shots] == ["card", "chapter", "card", "chapter"], shots
    assert shots[0]["title"] == "Add a venue" and shots[0]["subtitle"] == "From the list"
    tl = build(shots, {"main": two})
    assert [s["dur"] for s in tl["shots"]] == [3.0, 8.0, 3.0, 12.0] and tl["duration"] == 26.0, tl
    assert "label" not in tl["shots"][1] and "caption" not in tl["shots"][1]
    one = {"video": "rec.webm", "total": 9, "markers": [{"kind": "chapter", "label": "x", "start": 1, "end": 9}]}
    assert demo(one, 9) == [{"id": "x", "kind": "chapter"}]
    none = {"video": "rec.webm", "total": 9, "markers": [{"kind": "cut", "label": "load", "start": 0, "end": 3}]}
    tl = build(demo(none, 9), {"main": none})
    assert tl["duration"] == 6.0 and tl["shots"][0]["map"][0] == [0.0, 3], tl
    print("ok")


def main():
    import sys
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("markers")
    d.add_argument("--out", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("video")
    s.add_argument("png")
    s.add_argument("--tiles", default="3x2")
    j = sub.add_parser("jumps")
    j.add_argument("video")
    j.add_argument("timeline")
    j.add_argument("png")
    a = ap.parse_args()
    if a.cmd == "sheet":
        return sheet(a.video, a.png, a.tiles)
    if a.cmd == "jumps":
        return jumps(a.video, json.load(open(a.timeline)), a.png)
    rec = json.load(open(a.markers))
    tl = build(demo(rec, duration(rec["video"])), {"main": rec})
    json.dump(tl, open(a.out, "w"), indent=1)
    print(f"{a.out}: {len(tl['shots'])} shots, {tl['duration']:.1f}s")


if __name__ == "__main__":
    main()
