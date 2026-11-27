---
name: showcase
description: Produces a narrated, branded demo video of a feature, a pull request, a branch or an area of an app, for the team (a pod's weekly update, a feature launch), from the local app filmed through Playwright MCP. The script is approved before anything is filmed; the voice-over comes from the ElevenLabs MCP, or is left out with --no-voice. This skill should be used when asked for a demo video, a weekly demo, a pod update video, a "vidéo de démo" for Slack, or a video "like Yohan's" — not for a reviewer video attached to a PR, which is pr-demo.
argument-hint: "[PR | branch | \"feature\"] [--no-voice] [--lang fr]"
---

# Showcase

A **showcase** is a video that tells the team what a feature does for its users: about a minute for
one feature, longer for an exhaustive tour. It runs as a sequence of **shots**, one per line of the
**script**:

- a **card**: kicker, title, subtitle, badges, or a title with an accent, on the brand background;
- a **chapter**: it opens on its title over the whole screen, the numbered pill (or a label such as
  `Before`) and the caption rising word by word over its first frame, held still and blurred, then
  leaving for the action. The app plays in a window on a gradient of the brand's color. The camera films the whole scene, Screen Studio
  style: it zooms in on the first click or typing, stays zoomed and pans while the actions follow each
  other, zooms deeper on the element the voice is about, and blurs its fast moves. A drawn cursor
  glides between the clicks, as a hand on links and buttons and a text bar on fields.

The montage is pr-demo's engine (`$DEMO/scripts/engine.py`, `assets/stage.html`, `scripts/render.js`);
this skill adds the script, the cards' brand and the voice.

A card lasts as long as its voice line. A chapter opens on its title for 1.8 s, its voice line
starting as the title leaves, then plays its action at real speed, lasts as long as the
action or its voice line, whichever is longer, then holds its last frame 1.5 s. With `--no-voice`, a
shot also lasts the time to read it.

Everything for one showcase lives in `DIR=~/.cache/showcase/<owner>-<repo>/<slug>/`, the slug being the
PR number or the feature in kebab case: `script.json`, `record.js`, `main.json`, `before.json`,
`voice/`, `theme.css`, `timeline.json`, `frames/`, `showcase.mp4`, `sheet.png`, `jumps.png`. A second
run with the same slug is a **re-take**: it reuses what is there.

## 1. Resolve

From `$ARGUMENTS`: the source (a PR number or URL, a branch, or free text naming a feature or an app
area; none → the current branch's PR), `--no-voice`, `--lang fr` (default `en`). For a PR:
`gh pr view [<n>] --json number,url,title,headRefName,baseRefName,headRepositoryOwner,body`.
Create `DIR`. Locate this skill and pr-demo, whose setup and montage engine it shares:

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

Film the local app, where the data, the accounts and the feature flags are yours to set; a shared
environment adds SSO and emailed login codes the recording cannot pass. Read `$DEMO/SKILL.md` and run its sections **Local-app doc**, **Environment**, **Data** and
**Dry run**, with this skill's `DIR` in place of the demo directory and `$DEMO` in place of `$SKILL`. A source that is not a PR runs from the
current worktree.

**Done when** pr-demo's four criteria hold, the dry run included, on a re-take too: an app that changed
since the last video breaks its locators, and each failed take costs its chapters in real time.

## 5. Brand

The app's look lives in its repo: `docs/agents/video-theme.css` (from the main worktree,
`git worktree list | head -1`, when the docs are excluded). Copy it to `DIR/theme.css`. When it is
missing, read `$DEMO/../setup-ai-skills/SKILL.md` and set up its `video-theme` doc, which ends on a
preview the user approves; an older `~/.cache/showcase/<owner>-<repo>/theme.css` is its starting point.
What a theme may set is `$DEMO/references/theme.md`.

**Done when** `DIR/theme.css` is a copy of the repo's `docs/agents/video-theme.css`.

## 6. Record

Copy `$DEMO/assets/record.js` to `DIR/record.js` (a re-take edits the existing one; one without a
`reveal` helper predates the current engine: copy the template again and move its chapters into it)
and write the scenario with pr-demo's helpers. Then:

- wrap each chapter in `await chapter('<shot id>', async () => { … })`, in script order, from the
  chapter's start screen to its hold on the result. The chapter opens on that screen, whole and still:
  what takes the page there (closing the last chapter's dialog, a navigation, a reload) goes in a
  `cut` at its head, never in a `wait`, which plays a reload sped up. The montage holds the whole page
  for a second before the first zoom;
- act through `click` and `type`: the camera zooms on each of them on its own, and the cursor follows;
- call `await focus('<label>', locator)` when the voice turns to an element no click names (a card, a
  result), and `await focus('<label>', null)` to zoom out: a focus holds the camera on its element
  until the next `focus`, or until the page moves under it. A click, a `cut`, a `wait`,
  `scroll(locator)` and `press(key)` end it; scroll and close dialogs through them, never `p.mouse.wheel` or
  `p.keyboard`. The helpers scroll only when the element is off screen, in a glide the camera films;
  `scrollIntoViewIfNeeded`, `scrollBy` and `scrollTo` move the page in one frame: only inside a `cut`;
- give each chapter its reading time: hold on the result (`p.waitForTimeout`) as long as the viewer
  needs to read it. The montage plays the recording at 1x, never faster, and the voice may end before
  the action does;
- show a PDF as an image: headless Chromium has no PDF viewer, so an `<embed>` or `<iframe>` of a PDF
  stays blank or downloads the file. Render page 1 (`pdftoppm -r 110 -f 1 -l 1 -png -singlefile`),
  serve the PNG with `ctx.route(url, (r) => r.fulfill({ path }))`, and paint it with `addStyleTag`:
  hide the `embed` and set the PNG as its container's background. Search the local-app doc for `PDF`
  first: a record cloned from production may link its PDFs to storage the local app cannot read;
- keep a 16:9 size (1920×1080, or 1600×900 when the app's layout needs it): the stage frames the
  recording in a 16:9 window.

Run it as pr-demo's **Record** section does and save the returned JSON as `DIR/main.json`; a failed
step is re-filmed there too, in a retake of the chapters left (`TAKE`), saved as `DIR/main-2.json`. For a
`Before` chapter, run shots' compare switch (`git switch --detach` on the merge-base, reinstall when
the lockfile differs, wait for the reload, `reset`), record its chapters into `DIR/before.json`, then
switch back to the branch.

**Done when** each chapter of the script has its `chapter` marker in a take (`main*.json`, `before.json`), and
the worktree is back on its branch.

## 7. Voice

Skip with `--no-voice`. Otherwise, for each shot with a `voice` line, generate `DIR/voice/<id>.mp3` with
the ElevenLabs MCP (search the tools for `elevenlabs`). Its text-to-speech writes no file: each line
becomes a node on a flow, and its audio a signed URL.

1. `creative_create_flow` once; pass its `flow_id` to every call below.
2. `creative_generate_speech` with `voice_id`, `prompt` (the line) and `flow_id` returns the line's `node_id`.
3. Poll `creative_get_flow_node` (`flow_id`, `node_id`) every few seconds until one of its
   `generations` is completed; `creative_get_generations` with that generation's id gives its `full_res_url`.
4. `curl -sL <full_res_url> -o DIR/voice/<id>.mp3`.

Send the lines two at a time. A "busy" error started nothing and charged nothing: wait 30 s and send
the same line again. After any other error, read the flow (`creative_get_flow`) before sending the
line again: its node may have run, and a second call pays a second take. Use one voice for the whole video. Pick it once per language with the MCP's voice search, then
keep its id in `~/.cache/showcase/voice-<lang>.txt`. When the MCP is missing, generate placeholders
with `say -o voice/<id>.aiff "<line>"` and convert them with
`ffmpeg -i voice/<id>.aiff voice/<id>.mp3`, then say the voice is a placeholder.

**Done when** every voiced shot has its `mp3`.

## 8. Render and check

```bash
python3 $SKILL/scripts/timeline.py build DIR/script.json --rec main=DIR/main.json [--rec main=DIR/main-2.json …] [--rec before=DIR/before.json] \
        [--voice-dir DIR/voice] --out DIR/timeline.json
NODE_PATH=<the app repo's node_modules holding playwright> node $DEMO/scripts/render.js DIR/timeline.json --at <t>,<t>…
```

Leave out `--voice-dir` with `--no-voice`. With pnpm, `NODE_PATH` is
`$(ls -d <repo>/node_modules/.pnpm/playwright@*/node_modules | sort -V | tail -1)`.

`--at` writes `DIR/at-<t>.png` in a second or two: pass the middle of each focus (the `focus`
entries with `"light": true` in `timeline.json`) and read the frames. The zoom centers on the element the caption names. When a box
misses, fix it in `main.json`, rebuild the timeline and check again with `--at`: no re-take, no full
render. Then render the video, at 60 fps in four parts at once, about two seconds per second of video:

```bash
NODE_PATH=… node $DEMO/scripts/render.js DIR/timeline.json DIR/silent.mp4
python3 $SKILL/scripts/timeline.py mux DIR/timeline.json DIR/silent.mp4 DIR/showcase.mp4 --sheet DIR/sheet.png
python3 $DEMO/scripts/engine.py jumps DIR/showcase.mp4 DIR/timeline.json DIR/jumps.png
```

Read `sheet.png`. No frame shows a login page, a dev overlay, an error toast or a blank window. Then
read `jumps.png`, the frames that change at once, as pr-demo's **Render and check** section says: a
click's result appearing is the flow; the page moving on its own or a cut inside a chapter is a
defect to fix in `record.js`, then record again. A screen that differs from what the source promises
is a finding: report it as a possible bug before any re-take. Run `DIR/restore`. Copy the video to
`DIR/showcase-v<N>.mp4`, the next free `N`, and `open` that copy: a player that still holds
`showcase.mp4` shows the old take. Report its path, length, size and whether it has a voice.

**Done when** the sheet and `jumps.png` pass, the data is restored, and the user has said the video is
good.

## 9. Hand off

Draft the Slack message that goes with the video. Write two or three lines in the language of the
channel: what shipped and why it matters to the team. Pass it through the `humanizer` skill and give
it with the path of the video. The user posts both.

**Done when** the user has the file path and the message.
