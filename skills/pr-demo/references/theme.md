# The video theme

How a host app gives `pr-demo` and `showcase` videos its own look. The theme is one CSS file,
`docs/agents/video-theme.css` in the host repo, written by `setup-ai-skills`
(`references/video-theme.md` of that skill). A run copies it into its directory as `theme.css`;
`scripts/render.js` adds it after the stylesheet of `assets/stage.html`, so it sets the variables
below and may restyle any of the selectors listed. Without a theme the stage is a neutral dark one.

## Variables

| Variable | What it paints | Default |
|---|---|---|
| `--bg`, `--fg`, `--muted` | a card's background, text and secondary text | dark gradient, near white, grey |
| `--accent`, `--accent-soft` | the accent word of a card title, badges, the chapter number pill | lavender |
| `--surface` | the window behind the app while a frame loads | white |
| `--font-display`, `--font-body`, `--font-mono` | titles; body text; nothing until a rule uses it | system fonts |
| `--stage` | the scene the app's window sits on | a dark gradient of `--accent` |
| `--stage-fg` | a chapter's title, over the scene | white |
| `--window-radius` | the window's corners | 14px |
| `--veil` | the color the scene fades toward under a chapter's title, at full strength (give it an alpha) | `rgba(6, 8, 11, .6)` |
| `--band` | a strip under each title, drawn from left to right; unset, no strip | unset |

`--band` takes any background, usually the brand's palette as hard stops:
`linear-gradient(90deg, #f3bc77 0 33.3%, #d4a5f6 0 66.6%, #99ccc1 0)`.

## Selectors a theme may restyle

| Selector | Element |
|---|---|
| `.kicker`, `.title`, `.title .accent`, `.subtitle`, `.badge`, `.rule` | a card's lines |
| `#title`, `.pill`, `.caption` | a chapter's title: its block, its number, its words |
| `.band` | the strip, on cards and titles (size, spacing) |
| `#frame` | the app's window: border, shadow |

Leave alone what `stage.html` animates: `transform`, `opacity`, `clip-path` and `filter` of these
elements, and the size and place of `#frame`, which the camera relies on.

## Fonts

The stage is a `file://` page with no network: each font is an `@font-face` whose `src` is a base64
`data:` URL of a `woff2`. A font the file names without inlining it falls back to the system font.

## Preview

```bash
NODE_PATH=<dir holding playwright> node scripts/render.js --preview <theme.css> <app-screenshot.png> <dir>
```

writes `<dir>/at-2.4.png` (a card), `at-3.9.png` (a chapter's title over the app),
`at-5.6.png` (the whole window on the scene) and `at-7.8.png` (a zoom), in a few seconds.
