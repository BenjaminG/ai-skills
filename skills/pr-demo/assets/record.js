// Recording template for Playwright MCP `browser_run_code_unsafe`.
// Copy to <DIR>/record.js, set OUT and the scenario, then run it with `filename`.
// The new context reuses the MCP page's login (storageState), so the video starts signed in.
// Nothing is drawn on the page: the markers tell scripts/engine.py where to cut, where the camera
// zooms and where the cursor goes, and assets/stage.html draws them over the recording.
async (page) => {
  const OUT = '__DIR__'; // absolute path of the demo directory
  const SIZE = { width: 1920, height: 1080 };

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
  // A lit focus holds a box measured once: drop it before anything moves the page under it
  // (a cut, a wait, a click, a scroll, a key that closes a dialog), or the mask lights the wrong spot.
  let lit = null; // { locator, box } of the lit element
  const unlight = (start = at()) => { if (lit) { markers.push({ kind: 'focus', label: 'out', start, end: start, box: null }); lit = null; } };
  const span = (kind) => async (label, fn) => { if (kind !== 'chapter') unlight(); const start = at(); await fn(); markers.push({ kind, label, start, end: at() }); };
  const cut = span('cut');   // dropped from the video: page loads, off-camera setup
  const wait = span('wait'); // sped up: extraction, polling, server work
  const chapter = span('chapter'); // showcase: one chapter of the script, by its id
  const scenario = async (title, fn, subtitle = '') => { // pr-demo: one scenario; with several, a card names each
    const start = at(); await fn(); markers.push({ kind: 'chapter', label: title, subtitle, start, end: at() });
  };
  const focus = async (label, locator) => { // showcase: zoom on this element and light it from now on (null: zoom out)
    // The box is in viewport coordinates: measure it once the element is in view and the scroll has settled.
    let box = null;
    if (locator) {
      const scrolledAt = at();
      await locator.scrollIntoViewIfNeeded();
      if (lit) { // off from the moment the scroll moved the lit element
        const now = await lit.locator.boundingBox().catch(() => null);
        if (!now || Math.abs(now.x - lit.box.x) > 2 || Math.abs(now.y - lit.box.y) > 2) unlight(scrolledAt);
      }
      await p.waitForTimeout(400); box = await locator.boundingBox();
    }
    markers.push({ kind: 'focus', label, start: at(), end: at(), box });
    lit = box ? { locator, box } : null;
  };
  const scroll = async (locator) => { unlight(); await locator.scrollIntoViewIfNeeded(); await p.waitForTimeout(400); };
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
    markers.push({ kind: 'move', label: '', start, end: at(), from: pos, to: { x, y } });
    pos = { x, y };
  };
  const act = async (label, locator, fn) => { // the camera zooms on the element while fn runs
    unlight();
    const start = at();
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
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
  } finally {
    await ctx.close();
  }
  return { video: await video.path(), markers };
}
