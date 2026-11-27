#!/usr/bin/env node
// Render a timeline (engine.py's, or showcase's timeline.py) to a silent mp4, one screenshot of
// assets/stage.html per frame. An existing <out.mp4> is kept as <out>.prev.mp4.
// Usage: NODE_PATH=<dir holding playwright> node render.js <timeline.json> <out.mp4>
//        NODE_PATH=… node render.js <timeline.json> --at 10,13.5   (only those frames, as <dir>/at-<t>.png)
//        NODE_PATH=… node render.js --preview <theme.css> <app-screenshot.png> <dir>
//          a theme on a card, a chapter's title, the whole window and a zoom, as <dir>/at-<t>.png,
//          before anything is filmed
// theme.css next to the timeline, when present, gives the stage the app's brand.
// The video renders in WORKERS parts at once, one browser each, joined without re-encoding.
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { once } = require('events');
const { spawn, execFileSync } = require('child_process');

// A two-shot timeline over a still of the app: the card, then a chapter whose title is up at 0.9 s,
// whose whole window shows at 2.6 s and whose zoom has settled at 4.8 s. Returns render's arguments
// to film those four frames.
function preview(theme, still, dir) {
  if (!theme || !still || !dir) throw new Error('usage: render.js --preview <theme.css> <app-screenshot.png> <dir>');
  fs.mkdirSync(dir, { recursive: true });
  fs.copyFileSync(theme, path.join(dir, 'theme.css'));
  const video = path.join(dir, 'app.mp4');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-loop', '1', '-i', still, '-t', '2', '-r', '30',
    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080,format=yuv420p', video]);
  const tl = { fps: 60, size: [1920, 1080], duration: 9, recs: { main: { video, fps: 30 } }, shots: [
    { id: 'card', kind: 'card', start: 0, dur: 3, kicker: 'Weekly update', title: 'A new feature,', accent: 'shown', subtitle: 'What it does for the user', badges: ['Preview'] },
    { id: 'chapter', kind: 'chapter', rec: 'main', start: 3, dur: 6, label: '01', caption: 'The title of a chapter', intro: 1.8,
      map: [[0, 0], [6, 0]], focus: [{ t: 3.0, box: { x: 760, y: 420, width: 400, height: 160 }, light: true }], cursor: { moves: [], clicks: [] } },
  ] };
  const tlPath = path.join(dir, 'timeline.json');
  fs.writeFileSync(tlPath, JSON.stringify(tl));
  return [tlPath, '--at', '2.4,3.9,5.6,7.8'];
}

const WORKERS = Math.max(1, Math.min(4, os.cpus().length - 2));

// A browser on the stage, the timeline loaded.
async function stage(tl, dir) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: tl.size[0], height: tl.size[1] } });
  await page.goto(`file://${path.join(__dirname, '..', 'assets', 'stage.html')}`);
  const theme = path.join(dir, 'theme.css');
  if (fs.existsSync(theme)) await page.addStyleTag({ path: theme });
  await page.evaluate((t) => window.load(t), tl);
  await page.evaluate(() => document.fonts.ready);
  return { browser, page };
}

// Frames [from, to) of the video, encoded to out. tick() counts each frame done.
async function film(tl, dir, from, to, out, tick) {
  const { browser, page } = await stage(tl, dir);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(tl.fps), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', out],
  { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = once(ff, 'close');
  for (let i = from; i < to; i++) {
    await page.evaluate((t) => window.seek(t), i / tl.fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await once(ff.stdin, 'drain');
    tick();
  }
  ff.stdin.end();
  const [code] = await done;
  await browser.close();
  if (code !== 0) throw new Error(`ffmpeg exited ${code} on frames ${from}-${to}`);
}

async function main() {
  let [tlPath, out, at] = process.argv.slice(2);
  if (tlPath === '--preview') [tlPath, out, at] = preview(out, at, process.argv[5]);
  if (!tlPath || !out || (out === '--at' && !at)) throw new Error('usage: render.js <timeline.json> <silent.mp4> | --at <t>[,<t>…]');
  const tl = JSON.parse(fs.readFileSync(tlPath, 'utf8'));
  const dir = path.dirname(path.resolve(tlPath));

  // The stage seeks still frames, not a <video>: exact on every frame, no codec in the browser.
  for (const [name, rec] of Object.entries(tl.recs)) {
    const fd = path.join(dir, 'frames', name);
    const stale = !fs.existsSync(fd) || fs.statSync(rec.video).mtimeMs > fs.statSync(fd).mtimeMs;
    if (stale) {
      fs.rmSync(fd, { recursive: true, force: true });
      fs.mkdirSync(fd, { recursive: true });
      execFileSync('ffmpeg', ['-v', 'error', '-i', rec.video, '-vf', `fps=${rec.fps || tl.fps}`, '-q:v', '3', path.join(fd, '%05d.jpg')]);
    }
    rec.frames = fs.readdirSync(fd).filter((f) => f.endsWith('.jpg')).length;
    rec.base = `file://${fd}/`;
  }

  if (out === '--at') { // check a few frames in seconds instead of rendering the whole video
    const { browser, page } = await stage(tl, dir);
    for (const t of at.split(',').map(Number)) {
      await page.evaluate((s) => window.seek(s), t);
      const png = path.join(dir, `at-${t}.png`);
      await page.screenshot({ path: png });
      console.log(png);
    }
    await browser.close();
    return;
  }

  if (fs.existsSync(out)) fs.renameSync(out, out.replace(/(\.\w+)$/, '.prev$1'));
  const n = Math.round(tl.duration * tl.fps);
  const t0 = Date.now();
  const parts = fs.mkdtempSync(path.join(dir, 'parts-'));
  const size = Math.ceil(n / WORKERS);
  let frames = 0;
  const tick = () => { if (++frames % (tl.fps * 10) === 0) process.stderr.write(`frame ${frames}/${n}\n`); };
  const files = Array.from({ length: Math.ceil(n / size) }, (_, w) => path.join(parts, `${w}.mp4`));
  try {
    await Promise.all(files.map((f, w) => film(tl, dir, w * size, Math.min(n, (w + 1) * size), f, tick)));
    fs.writeFileSync(path.join(parts, 'list.txt'), files.map((f) => `file '${f}'\n`).join(''));
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(parts, 'list.txt'),
      '-c', 'copy', '-movflags', '+faststart', out]);
  } finally {
    fs.rmSync(parts, { recursive: true, force: true });
  }
  console.log(`${out}: ${n} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s, ${files.length} at once`);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
