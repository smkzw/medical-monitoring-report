/* render_check 的 ego-browser 版本（V5，用户 2026-10-31：本机不装 Playwright、不起第二个 Chromium，浏览器只走 ego lite）。
 * 与 render_check.js 同口径：逐页打开 → 收集脚本报错（window.onerror / unhandledrejection / console.error）、空容器、ECharts 实例数 → 整页截图
 * → 点遍每组页签 → 打开一个证据抽屉；页面清单读 scripts/pages.json。输出格式相同（JSON 报告＋末行 OK/FAIL），任一页有报错 exit 1。
 *
 * 运行（ego-browser 的 Node 运行时不继承 shell 参数与环境变量，参数经 globalThis.RC 传入）：
 *   ego-browser nodejs -e "globalThis.RC={html:'/abs/out/HTML',shots:'/abs/out/shots',sid:'',tabShots:false,noTabs:false};await import('file:///abs/scripts/render_check_ego.mjs')"
 * measure 模式（工作台信息条高度门禁）：RC={html, measure:'#kz-sys-bar'} → 末行输出 {"selector","height","found"} JSON。 */
const fs = await import('node:fs');
const path = await import('node:path');
const url = await import('node:url');
const RC = globalThis.RC || {};
const here = path.dirname(url.fileURLToPath(import.meta.url));
const dir = path.resolve(RC.html || 'out/site/HTML');
const shots = path.resolve(RC.shots || path.join(dir, '..', 'shots'));
const PL = JSON.parse(fs.readFileSync(path.join(here, 'pages.json'), 'utf8'));
const HOOK = "window.__rcErr=[];addEventListener('error',e=>__rcErr.push('pageerror: '+e.message));addEventListener('unhandledrejection',e=>__rcErr.push('pageerror: '+String(e.reason)));" +
  "(()=>{const o=console.error.bind(console);console.error=(...a)=>{__rcErr.push('console: '+a.map(String).join(' '));o(...a)}})();";
const task = await taskSpace('mm 报告渲染检查');
const page = (await task.pages())[0] || await task.newPage();
await page.cdp('Page.addScriptToEvaluateOnNewDocument', { source: HOOK });
await page.cdp('Network.setCacheDisabled', { cacheDisabled: true });
const fileUrl = rel => url.pathToFileURL(path.join(dir, rel.split('#')[0])).href + (rel.includes('#') ? '#' + rel.split('#')[1] : '');
const open = async rel => { await page.goto('about:blank'); await page.goto(fileUrl(rel)); await page.waitForTimeout(rel.startsWith('profile') || rel.startsWith('subjects') ? 3000 : 1800); };
const shot = async name => {
  await page.evaluate(() => { if (window.K && K.flushCharts) K.flushCharts(); });   // V6：首次进入视野才渲染的图在整页截图前画完
  await page.waitForTimeout(800);
  try {
    const r = await page.cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    fs.writeFileSync(path.join(shots, name + '.png'), Buffer.from(r.data, 'base64'));
  } catch (e) { await page.screenshot({ path: path.join(shots, name + '.png') }); }
};

if (RC.measure) {
  await open('index.html');
  await page.waitForTimeout(1200);
  const m = await page.evaluate(sel => { const e = document.querySelector(sel); return { selector: sel, height: e ? e.clientHeight : null, found: !!e }; }, RC.measure);
  console.log(JSON.stringify({ ok: m.found, height: m.found ? m.height : null, page: 'index.html', selector: m.selector }));   // 与 mm3/ui/measure_bar.js 同形
} else {
  fs.mkdirSync(shots, { recursive: true });
  const sid = RC.sid || (() => { try { const t = fs.readFileSync(path.join(dir, 'data', 'core.js'), 'utf8'); const m = t.match(/"queries":\s*\[\s*\{"id":\s*"Q001",\s*"sid":\s*"([^"]+)"/); return m && m[1]; } catch (e) { return null; } })();
  const targets = PL.pages.map(p => [p, `${p}.html`]);
  if (sid) PL.drill.forEach(p => targets.push([p + '_drill', `${p}.html#s=${sid}`]));
  (PL.deep || []).forEach(u => targets.push(['deep_' + u.replace(/[^a-z0-9]+/gi, '_'), u]));
  const report = []; let bad = 0;
  for (const [name, rel] of targets) {
    await open(rel);
    const info = await page.evaluate(() => {
      const charts = [...document.querySelectorAll('div[_echarts_instance_]')].length;
      const empty = [...document.querySelectorAll('[id]')].filter(e => /^(DIV|SECTION|TBODY)$/.test(e.tagName) && !e.children.length && !e.textContent.trim() && e.offsetParent !== null && !e.hasAttribute('_echarts_instance_')).map(e => e.id).slice(0, 12);
      return { title: document.title, charts, empty, h: document.body.scrollHeight, text: document.body.innerText.length };
    });
    await shot(name);
    const ntab = await page.evaluate(() => document.querySelectorAll('.tabs button').length);
    for (let i = 1; i < ntab && !RC.noTabs; i++) {
      await page.evaluate(i => { const b = document.querySelectorAll('.tabs button')[i]; if (b) b.click(); }, i);
      await page.waitForTimeout(500);
      if (RC.tabShots) await shot(`${name}_tab${i}`);
    }
    const opened = await page.evaluate(() => { const el = document.querySelector('[data-q],[data-r]'); if (el) { el.click(); return true; } return false; });
    if (opened) { await page.waitForTimeout(400); if (RC.tabShots) await shot(`${name}_drawer`); }
    const errors = await page.evaluate(() => window.__rcErr || []);
    info.tabs = ntab;
    report.push({ page: name, ...info, errors });
    if (errors.length) bad++;
  }
  console.log(JSON.stringify(report, null, 1));
  console.log(bad ? `FAIL: ${bad} page(s) with errors` : `OK: ${report.length} pages rendered without errors → ${shots}`);
  process.exitCode = bad ? 1 : 0;
}
