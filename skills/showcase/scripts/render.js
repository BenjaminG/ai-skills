#!/usr/bin/env node
// Render a showcase timeline to a silent mp4, one screenshot of assets/stage.html per frame.
// Usage: NODE_PATH=<dir holding playwright> node render.js <timeline.json> <silent.mp4>
//        NODE_PATH=… node render.js <timeline.json> --at 10,13.5   (only those frames, as <dir>/at-<t>.png)
// theme.css next to the timeline, when present, gives the stage the app's brand.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { once } = require('events');
const { spawn, execFileSync } = require('child_process');

async function main() {
  const [tlPath, out, at] = process.argv.slice(2);
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
      execFileSync('ffmpeg', ['-v', 'error', '-i', rec.video, '-vf', `fps=${tl.fps}`, '-q:v', '3', path.join(fd, '%05d.jpg')]);
    }
    rec.frames = fs.readdirSync(fd).filter((f) => f.endsWith('.jpg')).length;
    rec.base = `file://${fd}/`;
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: tl.size[0], height: tl.size[1] } });
  await page.goto(`file://${path.join(__dirname, '..', 'assets', 'stage.html')}`);
  const theme = path.join(dir, 'theme.css');
  if (fs.existsSync(theme)) await page.addStyleTag({ path: theme });
  await page.evaluate((t) => window.load(t), tl);
  await page.evaluate(() => document.fonts.ready);

  if (out === '--at') { // check a few frames in seconds instead of rendering the whole video
    for (const t of at.split(',').map(Number)) {
      await page.evaluate((s) => window.seek(s), t);
      const png = path.join(dir, `at-${t}.png`);
      await page.screenshot({ path: png });
      console.log(png);
    }
    await browser.close();
    return;
  }

  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(tl.fps), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = once(ff, 'close');
  const n = Math.round(tl.duration * tl.fps);
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    await page.evaluate((t) => window.seek(t), i / tl.fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await once(ff.stdin, 'drain');
    if (i % (tl.fps * 10) === 0) process.stderr.write(`frame ${i}/${n}\n`);
  }
  ff.stdin.end();
  const [code] = await done;
  await browser.close();
  if (code !== 0) throw new Error(`ffmpeg exited ${code}`);
  console.log(`${out}: ${n} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
