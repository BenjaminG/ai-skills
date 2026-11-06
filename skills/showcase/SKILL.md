---
name: showcase
description: Produces a narrated, branded demo video of a feature, a pull request, a branch or an area of an app, for the team (a pod's weekly update, a feature launch), from the local app filmed through Playwright MCP. The script is approved before anything is filmed; the voice-over comes from the ElevenLabs MCP, or is left out with --no-voice. This skill should be used when asked for a demo video, a weekly demo, a pod update video, a "vidéo de démo" for Slack, or a video "like Yohan's" — not for a reviewer video attached to a PR, which is pr-demo.
argument-hint: "[PR | branch | \"feature\"] [--no-voice] [--lang fr]"
---

# Showcase

A **showcase** is a 45–75 s video that tells the team what a feature does for its users. It runs as
a sequence of **shots**, one per line of the **script**:

- a **card**: kicker, title, subtitle, badges, or a title with an accent, on the brand background;
- a **chapter**: a numbered pill (or a label such as `Before`) and a caption above the app, which plays
  inside a framed window, zooms on the element the voice is about and dims the rest.

Each shot lasts as long as its voice line. With `--no-voice`, the time to read it and to play its action.

Everything for one showcase lives in `DIR=~/.cache/showcase/<owner>-<repo>/<slug>/`, the slug being the
PR number or the feature in kebab case: `script.json`, `record.js`, `main.json`, `before.json`,
`voice/`, `theme.css`, `timeline.json`, `frames/`, `showcase.mp4`, `sheet.png`. A second run with the
same slug is a **re-take**: it reuses what is there.

## 1. Resolve

From `$ARGUMENTS`: the source (a PR number or URL, a branch, or free text naming a feature or an app
area; none → the current branch's PR), `--no-voice`, `--lang fr` (default `en`). For a PR:
`gh pr view [<n>] --json number,url,title,headRefName,baseRefName,headRepositoryOwner,body`.
Create `DIR`. Locate this skill and pr-demo, whose setup it shares:

```bash
for n in showcase pr-demo; do
  for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/$n}" \
           $(ls -d "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/$n 2>/dev/null | sort -V | tail -1) \
           "$HOME/.claude/skills/$n"; do
    [ -n "$c" ] && [ -f "$c/SKILL.md" ] && echo "$n=$c" && break
  done
done
```

Use the printed paths as `$SKILL` and `$DEMO` literally.

**Done when** the source, the flags, `DIR`, `$SKILL` and `$DEMO` are known, and you know whether this is
a re-take (`DIR/script.json` exists).

## 2. Story

Read what the source gives: the PR's description and diff, its Linear issue, or for a feature or an
area the routes and screens it names. When the point of the feature is unclear from them, ask the user
what the team should take away. When the source is a PR or a branch that changes a screen that already
existed, ask whether to open on a `Before` chapter filmed on the base branch.

Plan the shots: an intro card, a section card when the video covers one feature among several, an
optional `Before` chapter, 3 to 8 chapters, an outro card with a one-line takeaway. The audience is the
team, not a reviewer: name what the user of the app sees and gains, never a component, an endpoint or a
file. A chapter shows one thing.

**Done when** every shot has its role and the chapters follow the order the app is used in.

## 3. Script

Write `DIR/script.json`:

```json
{"lang": "en", "voice": true, "shots": [
  {"id": "intro", "kind": "card", "kicker": "Weekly update · Nov 6, 2026", "title": "Redesign pod",
   "subtitle": "This week's progress", "badges": ["Work in progress"], "voice": "..."},
  {"id": "before", "kind": "chapter", "rec": "before", "label": "Before", "caption": "Split across five tabs",
   "show": "the old deal page, tab by tab", "voice": "..."},
  {"id": "twin", "kind": "chapter", "caption": "What your twin needs from you",
   "show": "zoom on the focus card", "voice": "..."},
  {"id": "outro", "kind": "card", "title": "One page.", "accent": "The whole deal.", "kicker": "AM Twin", "voice": "..."}
]}
```

- `caption`: six words at most, a noun phrase. `show`: what the camera does, for you and the user.
- `voice`: one or two spoken sentences, 25 words at most, in `lang`. With `--no-voice`, set
  `"voice": false` and write no `voice` field.
- `rec`: `before` for a chapter filmed on the base branch; `main` (the default) otherwise.

Pass the captions, card texts and voice lines through the `humanizer` skill. Then show
`python3 $SKILL/scripts/timeline.py table DIR/script.json` and apply the user's changes until they
approve. On a re-take, show only the rows that change. Film nothing before the approval: the voice
costs ElevenLabs credits and the recording follows the script.

**Done when** the user has approved the table and `script.json` holds that version.

## 4. Environment and data

Read `$DEMO/SKILL.md` and run its sections **Project note**, **Environment**, **Data** and **Dry
run**, with this skill's `DIR` in place of the demo directory. A source that is not a PR runs from the
current worktree.

**Done when** pr-demo's four criteria hold.

## 5. Brand

Reuse `~/.cache/showcase/<owner>-<repo>/theme.css` when it exists: copy it into `DIR`. Otherwise build it
from the app's own design system. In the Playwright MCP browser on the app, read with `browser_evaluate`
the computed background and text colors of the page, the primary button's color, a muted text color,
and the font families of a heading and of the body. For Naboo, they come from `@repo/tailwind-config`
and the `data-ds-theme` theme. Write them as these variables, which `assets/stage.html` reads:

```css
:root { --bg: …; --fg: …; --muted: …; --accent: …; --accent-soft: …; --surface: …; --radius: …;
        --font-display: "…", serif; --font-body: "…", sans-serif; }
```

The stage is a `file://` page: inline each brand font as `@font-face` with a base64 `data:` URL of the
`woff2` the app serves. Save the file to both places.

**Done when** `DIR/theme.css` exists and its fonts are inlined.

## 6. Record

Copy `$DEMO/assets/record.js` to `DIR/record.js` (a re-take edits the existing one) and write the
scenario with pr-demo's helpers. Then:

- wrap each chapter in `await chapter('<shot id>', async () => { … })`, in script order, from the
  chapter's start screen to its hold on the result;
- call `await focus('<label>', locator)` when the voice turns to an element, and
  `await focus('<label>', null)` to zoom out;
- keep the 1920×1080 size: the stage frames the recording at that size.

Run it as pr-demo's **Record** section does and save the returned JSON as `DIR/main.json`. For a
`Before` chapter, run pr-shots' compare switch (`git switch --detach` on the merge-base, reinstall when
the lockfile differs, wait for the reload, `reset`), record its chapters into `DIR/before.json`, then
switch back to the branch.

**Done when** each chapter of the script has its `chapter` marker in `main.json` or `before.json`, and
the worktree is back on its branch.

## 7. Voice

Skip with `--no-voice`. Otherwise, for each shot with a `voice` line, generate `DIR/voice/<id>.mp3` with
the ElevenLabs MCP's text-to-speech tool (search the tools for `elevenlabs`), moving its output file
there. Use one voice for the whole video. Pick it once per language with the MCP's voice search, then
keep its id in `~/.cache/showcase/voice-<lang>.txt`. When the MCP is missing, generate placeholders
with `say -o voice/<id>.aiff "<line>"` and convert them with
`ffmpeg -i voice/<id>.aiff voice/<id>.mp3`, then say the voice is a placeholder.

**Done when** every voiced shot has its `mp3`.

## 8. Render and check

```bash
python3 $SKILL/scripts/timeline.py build DIR/script.json --rec main=DIR/main.json [--rec before=DIR/before.json] \
        [--voice-dir DIR/voice] --out DIR/timeline.json
NODE_PATH=<the app repo's node_modules holding playwright> node $SKILL/scripts/render.js DIR/timeline.json DIR/silent.mp4
python3 $SKILL/scripts/timeline.py mux DIR/timeline.json DIR/silent.mp4 DIR/showcase.mp4 --sheet DIR/sheet.png
```

Leave out `--voice-dir` with `--no-voice`. With pnpm, `NODE_PATH` is
`$(ls -d <repo>/node_modules/.pnpm/playwright@*/node_modules | sort -V | tail -1)`. The render takes about
one second per two seconds of video.

Read `sheet.png`, plus a frame from the middle of each zoom (`ffmpeg -ss <t> -frames:v 1`, times in
`timeline.json`). No frame shows a login page, a dev overlay, an error toast or a blank window. The lit area
sits on the element the caption names. A screen that differs from what the source promises is a
finding: report it as a possible bug before any re-take. Run `DIR/restore`, then `open DIR/showcase.mp4`,
and report its length, size and whether it has a voice.

**Done when** the checks pass, the data is restored, and the user has said the video is good.

## 9. Hand off

Draft the Slack message that goes with the video. Write two or three lines in the language of the
channel: what shipped and why it matters to the team. Pass it through the `humanizer` skill and give
it with the path of `showcase.mp4`. The user posts both.

**Done when** the user has the file path and the message.
