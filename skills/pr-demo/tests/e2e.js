#!/usr/bin/env node
// End to end: films tests/fixture/app.html with the real assets/record.js (two scenarios, a load
// cut, a 2.5 s save in a wait, a lit focus far below the fold and a click back at the top), builds
// the timeline with scripts/engine.py and renders it with scripts/render.js. Leaves tests/out/ to
// open: markers.json, timeline.json, demo.mp4, sheet.png, jumps.png, and at-<t>.png frames in the
// middle of a zoom and on the final, zoomed-out result.
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
      await focus('notes', p.locator('#bottom'));
      await p.waitForTimeout(1500);
      await click(p.getByRole('link', { name: 'Dashboard' }));
      await p.waitForTimeout(2000);
    });
`;

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  // The template as a skill run fills it: OUT and the scenario block, at a smaller viewport than
  // the 1920×1080 output, as a run does when the app's layout needs it.
  const film = async (scenario, take = null) => {
    const src = fs.readFileSync(path.join(ROOT, 'assets', 'record.js'), 'utf8').replace("'__DIR__'", JSON.stringify(OUT))
      .replace('{ width: 1920, height: 1080 }', '{ width: 1600, height: 900 }').replace('const TAKE = null;', `const TAKE = ${JSON.stringify(take)};`)
      .replace(/\/\/ ---- scenario ----[\s\S]*\/\/ ---- end scenario ----/, scenario);
    const browser = await chromium.launch();
    const page = await (await browser.newContext()).newPage();
    try { return await eval(src)(page); } finally { await browser.close(); }
  };
  const rec = await film(SCENARIO);
  assert.ok(!rec.failed, `the take failed: ${JSON.stringify(rec.failed)}`);
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
  // The drawn cursor takes the shape the page gives: a text bar on the fields, a hand on the button and the link.
  const shapes = kinds('move').map((m) => m.cursor);
  assert.deepStrictEqual(shapes.slice(0, 3), ['text', 'text', 'text'], `cursor shapes ${shapes}`);
  assert.strictEqual(shapes.at(-1), 'pointer', `cursor shapes ${shapes}`);
  const dash = tl.shots[3];
  const lit = dash.focus.filter((f) => f.light);
  assert.strictEqual(lit.length, 1, `one lit focus: ${JSON.stringify(dash.focus)}`);
  assert.ok(dash.focus.every((f) => f.t >= 1), 'the chapter opens on the whole page');
  assert.ok(lit[0].box.y > 0 && lit[0].box.y + lit[0].box.height < 900, `the lit notes are on screen: ${JSON.stringify(lit[0].box)}`);

  console.log(run('node', [path.join(ROOT, 'scripts', 'render.js'), tlPath, mp4]));
  run('python3', [engine, 'sheet', mp4, path.join(OUT, 'sheet.png')]);
  // The page scrolls down to the notes and back up to the link, and the light goes off: on camera,
  // with no frame that changes at once.
  const jumps = run('python3', [engine, 'jumps', mp4, tlPath, path.join(OUT, 'jumps.png')]);
  assert.ok(!jumps.includes("'Open the dashboard'"), `a jump in the scrolling chapter:\n${jumps}`);
  const raw = probe(rec.video), got = probe(mp4);
  assert.ok(Math.abs(got - tl.duration) < 0.2, `video ${got}s, timeline ${tl.duration}s`);
  // Rendered in parts at once and joined: every frame there, once.
  const frames = parseInt(run('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries', 'stream=nb_read_packets', '-of', 'csv=p=0', mp4]));
  assert.strictEqual(frames, Math.round(tl.duration * tl.fps), 'frames lost or doubled where the parts join');
  // Chapters = recording - the load cut - the save wait sped up to 1 s (and what lies outside the scenarios).
  const len = (m) => m.end - m.start;
  const filmed = kinds('chapter').reduce((s, m) => s + len(m), 0) - (len(kinds('wait')[0]) - 1);
  const chapters = got - tl.shots[0].dur - tl.shots[2].dur;
  assert.ok(Math.abs(chapters - filmed) < 0.2, `chapters last ${chapters.toFixed(2)}s, scenarios minus the wait ${filmed.toFixed(2)}s`);
  assert.ok(chapters < raw - len(kinds('cut')[0]) - 1, `the cut and the wait shorten the film (${raw}s raw)`);

  // At each click, the drawn cursor tip, mapped back into the recording's pixels, is on the clicked element.
  const fd = path.join(OUT, 'frames', 'main');
  const recs = { main: { ...tl.recs.main, base: `file://${fd}/`, frames: fs.readdirSync(fd).length } };
  const sb = await chromium.launch();
  const stage = await sb.newPage({ viewport: { width: tl.size[0], height: tl.size[1] } });
  await stage.goto('file://' + path.join(ROOT, 'assets', 'stage.html'));
  await stage.evaluate((t) => window.load(t), { ...tl, recs });
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
  // The camera never jumps. Around a cut the engine can send a zoom-out and the next zoom 1 ms apart
  // (pod-083's client demo): the next zoom leaves from where the camera is, not from the whole page.
  const settled = zoomed[1].t + 1.1;
  const hop = { ...add, start: 0, focus: [...add.focus.filter((f) => f.t < settled),
    { t: settled, box: null, light: false }, { t: settled + 0.001, box: zoomed[0].box, light: false }] };
  await stage.evaluate((t) => window.load(t), { ...tl, shots: [hop], recs });
  let last = null;
  for (let f = -3; f <= 6; f++) {
    await stage.evaluate((t) => window.seek(t), settled + f / tl.fps);
    const scale = await stage.evaluate(() => parseFloat(/scale\(([\d.]+)\)/.exec(document.querySelector('#scene').style.transform)[1]));
    if (last) assert.ok(scale / last < 1.15 && last / scale < 1.15, `the camera jumps from ×${last.toFixed(2)} to ×${scale.toFixed(2)} in one frame`);
    last = scale;
  }
  // Motion blur while the camera moves, none once it has settled.
  await stage.evaluate((t) => window.load(t), { ...tl, recs });
  const filterAt = (t) => stage.evaluate((s) => window.seek(s).then(() => document.querySelector('#scene').style.filter), t);
  assert.notStrictEqual(await filterAt(add.start + zoomed[0].t + 0.15), 'none', 'no blur in the middle of the first zoom');
  assert.strictEqual(await filterAt(add.start + add.dur - 0.05), 'none', 'blur on a settled camera');
  await sb.close();

  // A host theme previews in four frames before anything is filmed, its band drawn under the title.
  const theme = path.join(OUT, 'preview-theme.css');
  fs.writeFileSync(theme, ':root { --stage: #f7f8f4; --stage-fg: #030302; --veil: rgba(247, 248, 244, .85); --band: linear-gradient(90deg, #f15a15 0 50%, #1e9397 0); }');
  run('node', [path.join(ROOT, 'scripts', 'render.js'), '--preview', theme, path.join(fd, '00001.jpg'), path.join(OUT, 'preview')]);
  for (const t of ['2.4', '3.9', '5.6', '7.8']) assert.ok(fs.existsSync(path.join(OUT, 'preview', `at-${t}.png`)), `no preview frame at ${t}s`);
  const rgb = execFileSync('ffmpeg', ['-v', 'error', '-i', path.join(OUT, 'preview', 'at-3.9.png'), '-vf', 'crop=700:500:180:300',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 24 });
  let orange = 0;
  for (let i = 0; i < rgb.length; i += 3) if (rgb[i] > 220 && rgb[i + 1] < 120 && rgb[i + 2] < 60) orange++;
  assert.ok(orange > 500, `the band's orange is missing under the title (${orange} pixels)`);
  // A take fails in its second scenario: the first keeps its markers, and a retake (TAKE) films the
  // second alone. The demo plays each scenario from its last take, in the order first filmed.
  const TAKES = path.join(OUT, 'takes');
  fs.mkdirSync(TAKES);
  const broken = await film(SCENARIO.replace("await focus('notes', p.locator('#bottom'));", "await p.locator('#missing').click({ timeout: 500 });"));
  assert.strictEqual(broken.failed?.chapter, 'Open the dashboard', `failed: ${JSON.stringify(broken.failed)}`);
  assert.ok(fs.existsSync(broken.failed.screenshot), 'no screenshot of the failed step');
  assert.deepStrictEqual(broken.markers.filter((m) => m.kind === 'chapter').map((m) => m.label), ['Add a venue']);
  const retake = await film(SCENARIO, ['Open the dashboard']);
  assert.deepStrictEqual(retake.markers.filter((m) => m.kind === 'chapter').map((m) => m.label), ['Open the dashboard']);
  fs.writeFileSync(path.join(TAKES, 'take-1.json'), JSON.stringify(broken));
  fs.writeFileSync(path.join(TAKES, 'take-2.json'), JSON.stringify(retake));
  const takesTl = path.join(TAKES, 'timeline.json');
  run('python3', [engine, 'demo', path.join(TAKES, 'take-1.json'), path.join(TAKES, 'take-2.json'), '--out', takesTl]);
  const joined = JSON.parse(fs.readFileSync(takesTl, 'utf8'));
  assert.deepStrictEqual(joined.shots.map((s) => [s.id, s.rec]), [['card-1', undefined], ['Add a venue', 'main'], ['card-2', undefined], ['Open the dashboard', 'main-2']]);
  const fromRetake = joined.shots[3].start + 1;
  run('node', [path.join(ROOT, 'scripts', 'render.js'), takesTl, '--at', String(fromRetake)]);
  assert.ok(fs.existsSync(path.join(TAKES, `at-${fromRetake}.png`)), 'the retake does not render');

  const midZoom = add.start + zoomed[1].t + 1.1;     // the camera has panned onto the second field
  const result = add.start + add.dur - 0.3;          // the saved venue, whole page
  run('node', [path.join(ROOT, 'scripts', 'render.js'), tlPath, '--at', `${midZoom.toFixed(2)},${result.toFixed(2)}`]);
  console.log(`✅ e2e passed: ${got.toFixed(1)}s demo from ${raw.toFixed(1)}s of recording; open ${OUT}`);
})().catch((e) => { console.error(`❌ ${e.stack || e}`); process.exit(1); });
