#!/usr/bin/env node
// End to end: films tests/fixture/app.html with the real assets/record.js (two scenarios, a load
// cut, a 2.5 s save in a wait), builds the timeline with scripts/engine.py and renders it with
// scripts/render.js. Leaves tests/out/ to open: markers.json, timeline.json, demo.mp4, sheet.png,
// and at-<t>.png frames in the middle of a zoom and on the final, zoomed-out result.
// Usage: NODE_PATH=<dir holding playwright> node skills/pr-demo/tests/e2e.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(__dirname, 'out');
const APP = 'file://' + path.join(__dirname, 'fixture', 'app.html');
const run = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const probe = (f) => Number(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]));

const SCENARIO = `
    await cut('load', async () => {
      await p.goto(${JSON.stringify(APP)});
      await p.getByText('Add a venue').waitFor();
    });
    await scenario('Add a venue', async () => {
      await p.waitForTimeout(1200);
      await type(p.locator('#name'), 'Abbaye de Royaumont');
      await type(p.locator('#city'), 'Asnières-sur-Oise');
      await type(p.locator('#cap'), '150');
      await click(p.getByRole('button', { name: 'Save venue' }));
      await wait('save', () => p.getByText('Venue saved').waitFor({ timeout: 10000 }));
      await p.waitForTimeout(2000);
    }, 'From the venue list');
    await scenario('Open the dashboard', async () => {
      await p.waitForTimeout(800);
      await click(p.getByRole('link', { name: 'Dashboard' }));
      await p.waitForTimeout(2000);
    });
`;

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  // The template as a skill run fills it: OUT and the scenario block, at a smaller viewport than
  // the 1920×1080 output, as a run does when the app's layout needs it.
  let src = fs.readFileSync(path.join(ROOT, 'assets', 'record.js'), 'utf8').replace("'__DIR__'", JSON.stringify(OUT))
    .replace('{ width: 1920, height: 1080 }', '{ width: 1600, height: 900 }');
  src = src.replace(/\/\/ ---- scenario ----[\s\S]*\/\/ ---- end scenario ----/, SCENARIO);
  const record = eval(src);

  const browser = await chromium.launch();
  const page = await (await browser.newContext()).newPage();
  const rec = await record(page);
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'markers.json'), JSON.stringify(rec, null, 1));

  const kinds = (k) => rec.markers.filter((m) => m.kind === k);
  assert.strictEqual(kinds('act').length, 5, 'three typings and two clicks');
  assert.strictEqual(kinds('click').length, 5);
  assert.ok(kinds('move').length >= 4, 'the cursor travels between the fields');
  assert.deepStrictEqual(kinds('chapter').map((m) => m.label), ['Add a venue', 'Open the dashboard']);

  const engine = path.join(ROOT, 'scripts', 'engine.py');
  const tlPath = path.join(OUT, 'timeline.json');
  const mp4 = path.join(OUT, 'demo.mp4');
  console.log(run('python3', [engine, 'demo', path.join(OUT, 'markers.json'), '--out', tlPath]));
  const tl = JSON.parse(fs.readFileSync(tlPath, 'utf8'));
  assert.deepStrictEqual(tl.shots.map((s) => s.kind), ['card', 'chapter', 'card', 'chapter']);
  assert.strictEqual(tl.shots[0].title, 'Add a venue');
  assert.strictEqual(tl.shots[0].subtitle, 'From the venue list');

  const add = tl.shots[1];
  const zoomed = add.focus.filter((f) => f.box);
  assert.ok(zoomed.length >= 3, 'the camera follows the fields');
  assert.ok(add.focus.every((f) => !f.light), 'auto zooms are never lit');
  assert.strictEqual(add.focus.at(-1).box, null, 'the chapter ends on the whole page');
  // The fields follow each other within HOLD: the camera pans between them, it never zooms out.
  const firstOut = add.focus.findIndex((f) => !f.box);
  assert.ok(firstOut >= 3, `a zoom-out before the save: ${JSON.stringify(add.focus)}`);
  assert.ok(add.cursor.moves.length >= 4 && add.cursor.clicks.length === 4);

  console.log(run('node', [path.join(ROOT, 'scripts', 'render.js'), tlPath, mp4]));
  run('python3', [engine, 'sheet', mp4, path.join(OUT, 'sheet.png')]);
  const raw = probe(rec.video), got = probe(mp4);
  assert.ok(Math.abs(got - tl.duration) < 0.2, `video ${got}s, timeline ${tl.duration}s`);
  // Chapters = recording - the load cut - the save wait sped up to 1 s (and what lies outside the scenarios).
  const len = (m) => m.end - m.start;
  const filmed = kinds('chapter').reduce((s, m) => s + len(m), 0) - (len(kinds('wait')[0]) - 1);
  const chapters = got - tl.shots[0].dur - tl.shots[2].dur;
  assert.ok(Math.abs(chapters - filmed) < 0.2, `chapters last ${chapters.toFixed(2)}s, scenarios minus the wait ${filmed.toFixed(2)}s`);
  assert.ok(chapters < raw - len(kinds('cut')[0]) - 1, `the cut and the wait shorten the film (${raw}s raw)`);

  // At each click, the drawn cursor tip, mapped back into the recording's pixels, is on the clicked element.
  const fd = path.join(OUT, 'frames', 'main');
  const sb = await chromium.launch();
  const stage = await sb.newPage({ viewport: { width: tl.size[0], height: tl.size[1] } });
  await stage.goto('file://' + path.join(ROOT, 'assets', 'stage.html'));
  await stage.evaluate((t) => window.load(t), { ...tl, recs: { main: { ...tl.recs.main, base: `file://${fd}/`, frames: fs.readdirSync(fd).length } } });
  for (const [i, c] of add.cursor.clicks.entries()) {
    await stage.evaluate((t) => window.seek(t), add.start + c);
    const tip = await stage.evaluate(() => {
      const c = document.querySelector('#cursor').getBoundingClientRect(), img = document.querySelector('#shot'), r = img.getBoundingClientRect();
      return { x: (c.left - r.left) / r.width * img.naturalWidth, y: (c.top - r.top) / r.height * img.naturalHeight };
    });
    const b = kinds('act')[i].box;
    assert.ok(tip.x >= b.x && tip.x <= b.x + b.width && tip.y >= b.y && tip.y <= b.y + b.height,
      `click ${i}: cursor drawn at ${tip.x.toFixed(0)},${tip.y.toFixed(0)} of the recording, element at ${JSON.stringify(b)}`);
  }
  await sb.close();

  const midZoom = add.start + zoomed[1].t + 0.9;     // the camera has panned onto the second field
  const result = add.start + add.dur - 0.3;          // the saved venue, whole page
  run('node', [path.join(ROOT, 'scripts', 'render.js'), tlPath, '--at', `${midZoom.toFixed(2)},${result.toFixed(2)}`]);
  console.log(`✅ e2e passed: ${got.toFixed(1)}s demo from ${raw.toFixed(1)}s of recording; open ${OUT}`);
})().catch((e) => { console.error(`❌ ${e.stack || e}`); process.exit(1); });
