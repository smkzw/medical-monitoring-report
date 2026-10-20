#!/usr/bin/env node
/* Render every report page headless (sandbox Chromium via Playwright), collect console/page errors, empty
 * containers and ECharts instances, and save screenshots.
 *   node scripts/render_check.js out/demo/HTML [--shots out/demo/shots] [--sid 03001]
 * Exit code 1 when any page throws or logs a console error. Run from a dir where `playwright` resolves (e.g. /data). */
const path = require('path'), fs = require('fs');
let pw;
for (const c of ['playwright', path.join(process.cwd(), 'node_modules', 'playwright'), '/vercel/sandbox/node_modules/playwright', ...(process.env.NODE_PATH || '').split(':').filter(Boolean).map(p => path.join(p, 'playwright'))]) {
  try { pw = require(c); break; } catch (e) { /* try next */ }
}
if (!pw) { console.error('playwright not found: npm i playwright (or set NODE_PATH)'); process.exit(2); }
const args = process.argv.slice(2);
const dir = path.resolve(args[0] || 'out/site/HTML');
const opt = k => { const i = args.indexOf(k); return i > 0 ? args[i + 1] : null; };
const shots = path.resolve(opt('--shots') || path.join(dir, '..', 'shots'));
fs.mkdirSync(shots, { recursive: true });
const PAGES = ['index', 'study', 'subjects', 'timeline', 'safety', 'efficacy', 'objective', 'queries', 'methods'];
(async () => {
  const exe = [process.env.CHROMIUM, '/usr/local/bin/chromium', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean).find(p => fs.existsSync(p));
  const browser = await pw.chromium.launch({ executablePath: exe, args: ['--no-sandbox', '--allow-file-access-from-files'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  const report = []; let bad = 0;
  const sid = opt('--sid') || (() => { try { const t = fs.readFileSync(path.join(dir, 'data', 'core.js'), 'utf8'); const m = t.match(/"queries":\s*\[\s*\{"id":\s*"Q001",\s*"sid":\s*"([^"]+)"/); return m && m[1]; } catch (e) { return null; } })();
  const targets = PAGES.map(p => [p, `${p}.html`]);
  if (sid) targets.push(['subjects_drill', `subjects.html#s=${sid}`], ['timeline_drill', `timeline.html#s=${sid}`]);
  for (const [name, rel] of targets) {
    const page = await ctx.newPage();
    const errs = [];
    page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    page.on('pageerror', e => errs.push('pageerror: ' + e.message));
    await page.goto('file://' + path.join(dir, rel.split('#')[0]) + (rel.includes('#') ? '#' + rel.split('#')[1] : ''), { waitUntil: 'load' });
    await page.waitForTimeout(1800);
    const info = await page.evaluate(() => {
      const charts = [...document.querySelectorAll('div[_echarts_instance_]')].length;
      const empty = [...document.querySelectorAll('[id]')].filter(e => /^(DIV|SECTION|TBODY)$/.test(e.tagName) && !e.children.length && !e.textContent.trim() && e.offsetParent !== null && !e.hasAttribute('_echarts_instance_')).map(e => e.id).slice(0, 12);
      return { title: document.title, charts, empty, h: document.body.scrollHeight, text: document.body.innerText.length };
    });
    await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true });
    // click through every tab group (.tabs button) so lazily rendered panels are exercised too
    const ntab = await page.evaluate(() => document.querySelectorAll('.tabs button').length);
    for (let i = 1; i < ntab && !args.includes('--no-tabs'); i++) {
      await page.evaluate(i => { const b = document.querySelectorAll('.tabs button')[i]; if (b) b.click(); }, i);
      await page.waitForTimeout(500);
      if (args.includes('--tab-shots')) await page.screenshot({ path: path.join(shots, `${name}_tab${i}.png`), fullPage: true });
    }
    // open one evidence drawer (query / rule / subject row) to check drawer rendering
    const opened = await page.evaluate(() => { const el = document.querySelector('[data-q],[data-r]'); if (el) { el.click(); return true; } return false; });
    if (opened) { await page.waitForTimeout(400); if (args.includes('--tab-shots')) await page.screenshot({ path: path.join(shots, `${name}_drawer.png`) }); }
    info.tabs = ntab;
    report.push({ page: name, ...info, errors: errs });
    if (errs.length) bad++;
    await page.close();
  }
  console.log(JSON.stringify(report, null, 1));
  console.log(bad ? `FAIL: ${bad} page(s) with errors` : `OK: ${report.length} pages rendered without errors → ${shots}`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
