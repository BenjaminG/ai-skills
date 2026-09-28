// Recording template for Playwright MCP `browser_run_code_unsafe`.
// Copy to <DIR>/record.js, set OUT and the scenario, then run it with `filename`.
// The new context reuses the MCP page's login (storageState), so the video starts signed in.
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
      const dot = document.createElement('div');
      dot.style.cssText = 'position:fixed;left:-40px;top:-40px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(220,38,38,.55);border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.4);z-index:2147483647;pointer-events:none;transition:transform .08s';
      document.body.appendChild(dot);
      window.addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
      window.addEventListener('mousedown', () => { dot.style.transform = 'scale(.7)'; }, true);
      window.addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
    });
  });

  const p = await ctx.newPage();
  const video = p.video();
  const t0 = Date.now();
  const at = () => (Date.now() - t0) / 1000;
  const markers = [];
  const span = (kind) => async (label, fn) => { const start = at(); await fn(); markers.push({ kind, label, start, end: at() }); };
  const cut = span('cut');   // dropped from the video: page loads, off-camera setup
  const wait = span('wait'); // sped up: extraction, polling, server work

  const click = async (locator) => {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 });
    await p.waitForTimeout(150);
    await locator.click();
  };
  const type = async (locator, text) => { await click(locator); await locator.press('ControlOrMeta+a'); await locator.pressSequentially(text, { delay: 18 }); };
  const title = async (heading, subtitle = '') => {
    await p.evaluate(([h, s]) => {
      const card = document.createElement('div');
      card.id = '__title';
      card.style.cssText = 'position:fixed;inset:0;z-index:2147483646;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(17,24,39,.9);color:#fff;font-family:system-ui,sans-serif;text-align:center';
      card.innerHTML = `<div style="font-size:44px;font-weight:700;margin-bottom:12px">${h}</div><div style="font-size:24px;opacity:.85">${s}</div>`;
      document.body.appendChild(card);
    }, [heading, subtitle]);
    await p.waitForTimeout(2500);
    await p.evaluate(() => document.getElementById('__title')?.remove());
  };

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
