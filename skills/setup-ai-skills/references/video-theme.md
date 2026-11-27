# The video theme

What `setup-ai-skills` writes in the host repo so the videos of `pr-demo` and `showcase` take the
app's look: its colors, its fonts, the scene its window sits on, how chapter titles read. The
variables and selectors a theme may set are pr-demo's `references/theme.md`; read it first.

```
docs/agents/video-theme.css   the theme, fonts inlined, and a header comment naming its sources
```

## Sections

The file is CSS. A header comment lists, one line each, where each value came from (a token file
and its line, a computed style, the user) and the date of the proof. Then:

1. **Fonts**: one `@font-face` per font the theme names, `src` a base64 `data:` URL of the `woff2`.
2. **Colors**: `--bg`, `--fg`, `--muted`, `--accent`, `--accent-soft`, `--surface`, from the
   design system's semantic tokens (background, foreground, muted foreground, primary).
3. **Scene**: `--stage`, `--stage-fg`, `--veil`, `--window-radius`. On a light brand (its pages sit
   on a pale background), the scene is that background, the title its ink, and the veil that
   background at about 85 %; on a dark or saturated brand, the default dark gradient of `--accent`
   fits. The user chooses between the two from the preview.
4. **Brand marks**, when the design system has them: `--band` from its palette, a mono or uppercase
   style for `.pill` and `.kicker` when the brand uses mono eyebrows, a `#frame` border in its
   border token.

## Explore

- **Design system tokens**: a `tokens.css` or theme file (`--background`, `--foreground`,
  `--primary`, `--secondary`, palette primitives), a Tailwind preset or config, a package named
  `design-system` (also under `node_modules` when it is installed from a registry), its guidelines
  or skill files: they name the fonts and their role.
- **Font files**: `woff2` files in the repo (`fd -e woff2`), matched to the token font names.
- **The running app**, when no token file exists: in the Playwright MCP browser, the computed
  background and text colors, the primary button's color, a muted text color, and the font family
  of a heading and of the body (`browser_evaluate`).
- **Brand material**: a deck, a marketing page or a doc the user points to. The design system wins
  where they differ.
- **Already written**: `~/.cache/showcase/<owner>-<repo>/theme.css`, an older theme of this repo.
- **Memory words**: `theme|brand|design system|font|color|palette`.

## Proof

Take a 1920×1080 screenshot of a typical screen of the app, then run pr-demo's preview:

```bash
NODE_PATH=<the app repo's node_modules holding playwright> node <pr-demo>/scripts/render.js --preview docs/agents/video-theme.css <screenshot.png> <scratch dir>
```

Read the four frames. Each font renders in its own face (no system fallback), the chapter's title
reads clearly over the veiled app, the window stands out from the scene. Show the frames to the user,
apply their changes and run the preview again, until they approve.

## Retirable sources

`~/.cache/showcase/<owner>-<repo>/theme.css`, once the doc is written: the readers read the doc first.
