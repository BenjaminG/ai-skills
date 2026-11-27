// Recording template for Playwright MCP `browser_run_code_unsafe`.
// Copy to <DIR>/record.js, set OUT and the scenario, then run it with `filename`.
// The new context reuses the MCP page's login (storageState), so the video starts signed in.
// Nothing is drawn on the page: the markers tell scripts/engine.py where to cut, where the camera
// zooms and where the cursor goes, and assets/stage.html draws them over the recording.
async (page) => {
  const OUT = '__DIR__'; // absolute path of the demo directory
  const SIZE = { width: 1920, height: 1080 };
  // A retake: the ids of the chapters (titles of the scenarios) to film again. The others are skipped,
  // so reset puts the data in the state the first of them starts from.
  const TAKE = null;

  const storageState = await page.context().storageState();
  const ctx = await page.context().browser().newContext({ storageState, viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
  await ctx.addInitScript(() => {
    window.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = 'nextjs-portal, .tsqd-open-btn-container, [aria-label="Open React Query Devtools"] { display: none !important }';
      document.head.appendChild(style);
    });
  });

  const p = await ctx.newPage();
  const video = p.video();
  const t0 = Date.now();
  const at = () => (Date.now() - t0) / 1000;
  const markers = [];
  let filming = null; // the chapter being filmed, named when a step fails
  // A lit focus holds a box measured once: drop it before anything moves the page under it
  // (a cut, a wait, a click, a scroll, a key that closes a dialog), or the mask lights the wrong spot.
  let lit = null; // { locator, box } of the lit element
  const unlight = (start = at()) => { if (lit) { markers.push({ kind: 'focus', label: 'out', start, end: start, box: null }); lit = null; } };
  // The page has stopped moving: two screenshots 250 ms apart match (a reload restoring its scroll,
  // a list filling in). A cut ends on it, so the shot after it opens on a still page.
  const still = async () => {
    let last = await p.screenshot();
    for (let i = 0; i < 20; i++) {
      await p.waitForTimeout(250);
      const next = await p.screenshot();
      if (next.equals(last)) return;
      last = next;
    }
  };
  const span = (kind) => async (label, fn) => {
    if (kind !== 'chapter') unlight();
    const start = at(); await fn();
    if (kind === 'cut') await still();
    markers.push({ kind, label, start, end: at() });
  };
  const filmed = (label) => !TAKE || TAKE.includes(label);
  const cut = span('cut');   // dropped from the video: page loads, navigations, reloads, off-camera setup
  const wait = span('wait'); // sped up: extraction, polling, server work
  const chapter = async (id, fn) => { // showcase: one chapter of the script, by its id
    if (!filmed(id)) return;
    filming = id; await span('chapter')(id, fn); filming = null;
  };
  const scenario = async (title, fn, subtitle = '') => { // pr-demo: one scenario; with several, a card names each
    if (!filmed(title)) return;
    filming = title;
    const start = at(); await fn(); markers.push({ kind: 'chapter', label: title, subtitle, start, end: at() });
    filming = null;
  };
  // Bring an element on screen as a viewer would: no scroll when it is already in view, else an eased
  // scroll of 0.4 to 1.2 s the camera films. scrollIntoViewIfNeeded, scrollBy and mouse.wheel move the
  // page in one frame, and the browser's own smooth scroll in about 0.2 s: both jump on camera.
  // Returns the element's box, in viewport coordinates, once it is still (the scroll over, a dialog
  // done opening).
  const reveal = async (locator) => {
    await locator.waitFor();
    await locator.evaluate((el) => new Promise((done) => {
      const r = el.getBoundingClientRect();
      if (r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth) return done();
      // Where each scrolling ancestor ends: jump there, read it, jump back, then glide.
      const nodes = [];
      for (let n = el.parentElement; n; n = n.parentElement) nodes.push(n);
      if (!nodes.includes(document.scrollingElement)) nodes.push(document.scrollingElement);
      const from = nodes.map((n) => [n.scrollLeft, n.scrollTop]);
      el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      const moves = nodes.map((n, i) => ({ n, x0: from[i][0], y0: from[i][1], x1: n.scrollLeft, y1: n.scrollTop, css: n.style.scrollBehavior }))
        .filter((m) => m.x0 !== m.x1 || m.y0 !== m.y1);
      for (const m of moves) { m.n.style.scrollBehavior = 'auto'; m.n.scrollTo(m.x0, m.y0); }
      const ms = Math.min(1200, 400 + 0.5 * Math.max(0, ...moves.map((m) => Math.hypot(m.x1 - m.x0, m.y1 - m.y0))));
      const ease = (x) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);
      const t0 = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - t0) / ms), e = ease(k);
        for (const m of moves) m.n.scrollTo(m.x0 + (m.x1 - m.x0) * e, m.y0 + (m.y1 - m.y0) * e);
        if (k < 1) return requestAnimationFrame(step);
        for (const m of moves) m.n.style.scrollBehavior = m.css;
        done();
      };
      requestAnimationFrame(step);
    }));
    let box = await locator.boundingBox();
    for (let i = 0; i < 40; i++) { // still when two reads 100 ms apart agree
      await p.waitForTimeout(100);
      const next = await locator.boundingBox();
      if (Math.abs(next.x - box.x) < 1 && Math.abs(next.y - box.y) < 1 && Math.abs(next.height - box.height) < 1) return next;
      box = next;
    }
    return box;
  };
  const focus = async (label, locator) => { // showcase: zoom on this element and light it from now on (null: zoom out)
    let box = null;
    if (locator) {
      const scrolledAt = at();
      box = await reveal(locator);
      if (lit) { // off from the moment the scroll moved the lit element
        const now = await lit.locator.boundingBox().catch(() => null);
        if (!now || Math.abs(now.x - lit.box.x) > 2 || Math.abs(now.y - lit.box.y) > 2) unlight(scrolledAt);
      }
    }
    markers.push({ kind: 'focus', label, start: at(), end: at(), box });
    lit = box ? { locator, box } : null;
  };
  const scroll = async (locator) => { unlight(); await reveal(locator); };
  const press = async (key) => { unlight(); await p.keyboard.press(key); }; // Escape closes a lit dialog

  let pos = { x: SIZE.width / 2, y: SIZE.height / 2 };
  const moveTo = async (x, y) => {
    const d = Math.hypot(x - pos.x, y - pos.y);
    if (d < 2) return;
    const ms = 180 + 16 * Math.sqrt(d); // longer for a longer way, after webreel's cursor-motion.ts (Apache-2.0)
    const start = at();
    await p.mouse.move(x, y, { steps: Math.max(1, Math.round(ms / 16)) });
    const rest = ms - (at() - start) * 1000;
    if (rest > 0) await p.waitForTimeout(rest);
    // the shape the system cursor takes there, which the stage draws: a hand, a text bar or the arrow
    const cursor = await p.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      if (!el) return 'default';
      const c = getComputedStyle(el).cursor;
      if (c === 'pointer' || c === 'text') return c;
      const editable = el.closest('textarea, [contenteditable]:not([contenteditable="false"]), input:not([type=checkbox], [type=radio], [type=button], [type=submit], [type=reset], [type=range], [type=file], [type=color], [type=image])');
      return c === 'auto' && editable ? 'text' : 'default';
    }, { x, y }).catch(() => 'default');
    markers.push({ kind: 'move', label: '', start, end: at(), from: pos, to: { x, y }, cursor });
    pos = { x, y };
  };
  const act = async (label, locator, fn) => { // the camera zooms on the element while fn runs
    unlight();
    const start = at();
    const box = await reveal(locator);
    await moveTo(box.x + box.width / 2, box.y + box.height / 2);
    await p.waitForTimeout(150);
    markers.push({ kind: 'click', label, start: at(), end: at() });
    await fn();
    markers.push({ kind: 'act', label, start, end: at(), box });
  };
  const click = (locator) => act('click', locator, () => locator.click());
  const type = (locator, text) => act('type', locator, async () => {
    await locator.click(); await locator.press('ControlOrMeta+a'); await locator.pressSequentially(text, { delay: 18 });
  });

  let failed = null;
  try {
    // ---- scenario ----
    await cut('load', async () => {
      await p.goto('__URL__');
      await p.getByText('__FIRST_VISIBLE_TEXT__').first().waitFor({ timeout: 60000 });
      await p.waitForLoadState('networkidle').catch(() => {});
    });
    await p.waitForTimeout(1200); // let the viewer read the starting state
    // await click(p.getByRole('button', { name: '...' }));
    // await wait('server work', () => p.getByText('...').waitFor({ timeout: 120000 }));
    await p.waitForTimeout(2000); // hold on the result
    // ---- end scenario ----
  } catch (e) {
    // The chapters done so far keep their markers: a retake films only the rest (TAKE).
    failed = { chapter: filming, error: e.message.split('\n')[0], screenshot: `${OUT}/failed.png` };
    await p.screenshot({ path: failed.screenshot }).catch(() => {});
  } finally {
    await ctx.close();
  }
  return { video: await video.path(), markers, ...(failed && { failed }) };
}
