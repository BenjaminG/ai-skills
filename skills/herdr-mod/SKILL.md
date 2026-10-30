---
name: herdr-mod
description: Builds a mod for the Herdr desktop app (a panel, sidebar, popup or key-driven view in ~/.config/herdr-app/mods/) and, with --publish, shares it on herdr.dev/mods through a public GitHub repo. This skill should be used when asked to make, change or publish a Herdr mod or panel.
argument-hint: "<name or idea> [--publish]"
---

# Herdr mod

`~/.config/herdr-app/AGENTS.md` is the **source of truth**: Herdr rewrites it, `herdr.d.ts` and
`gpui-kit.d.ts` on every start to match the installed version. Read it before writing a line, and
take every API, file shape and rule from it and the `.d.ts` files, never from memory. This skill
adds only the steps around it and the publishing convention.

## 1. Build

1. Read `AGENTS.md` in full, then the two `.d.ts` files for every function you call. Read the
   shipped mod closest to the idea (`mods/agents`, `mods/spaces`, `mods/tabs`…) as an example.
2. Pick a `<name>` free in `~/.config/herdr-app/mods/`: shipped names are Herdr's, and an installer
   renames on a clash.
3. Write `mods/<name>/` (`main.js`, `mod.json`, any modules and SVGs). Keys go in the person's
   `keys.json`, under `mod:<name>` and `global` entries pointing at `<name>.<command>`; ask before
   replacing a key they already use.
4. Run `herdr-app check ~/.config/herdr-app/mods/<name>` after every change, and `herdr-app status`
   for live errors.
5. Show the mod in the window, then `herdr-app shot <scratchpad>/check.png` and Read the PNG.

Done when the check passes **and** the shot shows the mod rendering real data the way the idea
asked. A passing check with an empty or misplaced panel is not done.

Without `--publish`, stop here and tell the person what the mod does and which keys it binds.

## 2. Publish (`--publish`)

All mods live in one public repo, `BenjaminG/herdr-mods`, cloned at `~/Dev/herdr-mods`, one folder
per mod. Create it once if missing: from `~/Dev`, `gh repo create BenjaminG/herdr-mods --public --clone`,
then `gh repo edit BenjaminG/herdr-mods --add-topic herdr-mod`.

```
herdr-mods/<name>/
  mods/<name>/   the mod folder, copied as built
  keys.json      only this mod's keys (its mod:<name> section, global keys aimed at <name>.*); omit if none
  RECIPE.md
  preview.png
```

No `layouts/` folder: herdr.dev lists it as a mod only without one.

1. Copy the mod folder and write the `keys.json` snippet from the real files.
2. **preview.png**: arrange the window so the mod fills most of it, `herdr-app shot`, then Read the
   PNG. The shot is the whole window: every visible terminal, path, branch and agent prompt gets
   published. Show only throwaway or public content; re-shoot until nothing private is visible.
3. **RECIPE.md**: write it the way `AGENTS.md`'s "Layouts and mods other people made" section
   describes (its six sections, in order), from the copied files. In Watch out, state whether the
   mod reaches the network, runs programs (`exec`, `hc`) or reads files outside its folder: an
   installer's agent warns the person about each.
4. Show the person the file tree, the recipe and the preview, and wait for their OK. Pushing
   publishes it to everyone.
5. Commit and push. Confirm the repo has the `herdr-mod` topic (`gh repo view --json
   repositoryTopics`).

Done when the push lands and the topic is set. Tell the person it appears on herdr.dev/mods under
Community within the hour, and that its picture is screened for at least 24 hours first.
