/* mm4 页面呈现逻辑单测（node，无浏览器；python test_mm4.KnowledgeStatePages 调用）：
 * kz.js 纯函数，桩数据断言——
 * ① K.knCard：degraded → 红字警示（MedDRA 字典不可用…请检查授权字典配置后重建）；可用 → 绿字
 *    （MedDRA 版本/AE 器官归类 n 条/关联预判 n 行）；无键 → 空串（旧构建无扰）。
 * ② K.knBar：degraded → 总览顶部警示条；可用/无键 → 空串。
 * ③ K.knHint：degraded → query 页头「关联类核对未含知识层预判」；其余 → 空串。
 * ④ K.ptCons（术语一致性按 PT 归并）：同 PT 两写法 → 1 桶 2 术语；不同 PT 各一写法 → 不进卡；
 *    pt 全空 → 降级提示；混合按覆盖率（<20% 降级，≥20% 正常归并）。
 * 用法：node scripts/test_render_logic.js <templates/site/assets 目录> */
'use strict';
const path = require('path');
const dir = process.argv[process.argv.length - 1];
global.window = {};
global.window.K = {};
Object.defineProperty(global, 'K', { get: () => global.window.K, configurable: true });   // kz.js IIFE 后的顶层语句用裸 K（浏览器解析为 window.K，IIFE 内会重建 window.K）
global.document = { addEventListener() {}, querySelector() { return null; }, createElement() { return { style: {} }; } };
global.ResizeObserver = class { observe() {} };
require(path.resolve(dir, 'kz.js'));
const K = window.K;
if (!K || !K.knCard || !K.knBar || !K.knHint || !K.ptCons) {
  console.error('缺纯函数：K.knCard/K.knBar/K.knHint/K.ptCons（kz.js）');
  process.exit(1);
}
let fails = 0;
const ok = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); fails++; } };

/* ---- 知识层状态卡（研究依据页 关键口径区） ---- */
const DEGRADED = { meddra_ok: false, meddra_version: '', ae_soc: 0, implausible: 0, plausible: 0, unknown: 0, degraded: true };
const OKKN = { meddra_ok: true, meddra_version: '29.0', ae_soc: 278, implausible: 3, plausible: 30, unknown: 12, degraded: false };
const red = K.knCard(DEGRADED);
ok(red.includes('红') || red.includes('p red'), '降级卡应有红色状态标');
ok(red.includes('MedDRA 字典不可用'), '降级卡缺警示文案');
ok(red.includes('AE 未按器官系统归类'), '降级卡缺 AE 归类缺失说明');
ok(red.includes('临床意义关联合理性未预判'), '降级卡缺关联预判缺失说明');
ok(red.includes('请检查授权字典配置后重建'), '降级卡缺处置指引');
const green = K.knCard(OKKN);
ok(green.includes('grn'), '可用卡应有绿色状态标');
ok(green.includes('29.0'), '可用卡应显示 MedDRA 版本');
ok(green.includes('AE 器官归类 278 条'), '可用卡应显示 AE 器官归类 n 条');
ok(green.includes('关联预判 45 行'), '可用卡应显示关联预判 n 行（3+30+12）');
ok(K.knCard(null) === '', '无 knowledge 键 → 不渲染（旧构建无扰）');

/* ---- 总览顶部警示条 ---- */
const bar = K.knBar(DEGRADED);
ok(bar.includes('医学术语词典暂不可用') && !bar.includes('知识层'), '总览警示条缺降级文案（且不得出现工程用语）');
ok(bar.includes('box red'), '总览警示条应为红色警示样式');
ok(K.knBar(OKKN) === '' && K.knBar(null) === '', '非降级不渲染总览警示条');

/* ---- query 页头提示 ---- */
const hint = K.knHint(DEGRADED);
ok(hint.includes('关联类核对不完整'), 'query 页头提示缺固定文案');
ok(K.knHint(OKKN) === '' && K.knHint(null) === '', '非降级不渲染 query 页头提示');

/* ---- 术语一致性按 PT 归并（安全页 AE tab） ---- */
let r = K.ptCons([{ t: '头痛', pt: '头痛' }, { t: '偏头痛', pt: '头痛' }, { t: '恶心', pt: '恶心' }]);
ok(!r.deg, 'pt 覆盖率高 → 不降级');
ok(r.rows.length === 1, `同 PT 两写法应归 1 桶（得 ${r.rows.length}）`);
ok(r.rows[0][0] === '头痛' && r.rows[0][1].length === 2, '桶内应收集 2 个不同原文术语');
r = K.ptCons([{ t: '头痛', pt: '头痛' }, { t: '恶心', pt: '恶心' }]);
ok(r.rows.length === 0, '不同 PT 各一写法 → 不进卡（无同 PT 多写法桶）');
r = K.ptCons([{ t: '头痛', pt: '' }, { t: '恶心', pt: '' }]);
ok(r.deg, 'pt 全空 → 降级');
ok(!(r.rows || []).length, '降级时不按原文术语陈列冒充判定');
r = K.ptCons([{ t: '头痛', pt: '头痛' }, { t: '偏头痛', pt: '头痛' },
  ...Array.from({ length: 9 }, (_, i) => ({ t: '术语' + i, pt: '' }))]);   // 2/11 ≈ 18% < 20%
ok(r.deg, '混合：pt 覆盖率 <20% → 降级');
r = K.ptCons([{ t: '头痛', pt: '头痛' }, { t: '偏头痛', pt: '头痛' },
  ...Array.from({ length: 8 }, (_, i) => ({ t: '术语' + i, pt: '' }))]);   // 2/10 = 20% 未低于
ok(!r.deg && r.rows.length === 1, '混合：pt 覆盖率 20%（未低于）→ 正常归并');
ok(K.ptCons([]).deg, '无 AE → 降级提示（无 PT 可归并）');

/* ---- 钻取行「判定与关联」列（参与者资料页 CS 项点开，用户 2026-10-30 裁定） ---- */
/* 行桩：既有 14 位（r[7]=clin）＋尾部扩位 [归因码, 原文说明, 关联摘要] */
const drow = (clin, code, txt, sum) => ['2026-06-20', 'V2', 88, '88', 'U/L', 9, 50, clin, '', 'LB', 5, '', '', 0, code, txt, sum];
if (typeof K.judgeCell !== 'function') { console.error('缺纯函数：K.judgeCell（kz.js）'); process.exit(1); }
const jAE = K.judgeCell(drow(2, 'AE', '与3号AE有关', 'AE 丙氨酸氨基转移酶升高·2026-06-10'), 'S1');
ok(jAE.includes('CS'), '有判定与关联信息的行应带 CS pill');
ok(jAE.includes('AE 关联'), 'AE 归因应显示「AE 关联」标签');
ok(jAE.includes('丙氨酸氨基转移酶升高') && jAE.includes('2026-06-10'), '关联应显示术语与日期');
ok(jAE.includes('subjects.html#s=S1&t=ae'), 'AE 关联应可跳转参与者资料页 AE tab');
ok(jAE.includes('与3号AE有关'), '原文说明应显示');
const jMH = K.judgeCell(drow(2, 'MH', '', '病史 贫血'), 'S1');
ok(jMH.includes('病史关联') && jMH.includes('贫血'), 'MH 关联应显示标签与术语');
ok(jMH.includes('subjects.html#s=S1&t=mh'), 'MH 关联应跳转 MH tab');
const jDis = K.judgeCell(drow(2, 'disease', '与研究疾病加重有关', ''), 'S1');
ok(jDis.includes('研究疾病'), 'disease 归因应显示「研究疾病」标签');
ok(!jDis.includes('subjects.html'), '无关联对象不渲染跳转链接');
ok(jDis.includes('与研究疾病加重有关'), 'disease 原文说明应显示');
const jNA = K.judgeCell(drow(null, 'NA', '', ''), 'S1');
ok(jNA.includes('未评价'), 'NA（超范围未评价）应显示标签');
ok(jNA.includes('ND'), '无临床意义判定应显示 ND pill');
const jNone = K.judgeCell(drow(2, '', '', ''), 'S1');
ok(jNone.includes('未关联'), 'CS 行全空应显示「未关联」灰字');
const jPlain = K.judgeCell(drow(0, '', '', ''), 'S1');
ok(jPlain === '' || !jPlain.includes('未关联'), '正常行不显示「未关联」（仅 CS 行）');

/* ---- V5：校正与尾概率、null 安全比较、研究层面容忍限度 ---- */
global.localStorage = (() => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) }; })();
global.CustomEvent = class { constructor(n, o) { this.type = n; this.detail = (o || {}).detail; } };
global.document.dispatchEvent = () => {};
require(path.resolve(dir, 'kz5.js'));
const bq = K.bh([0.01, 0.04, 0.03, null]);
ok(Math.abs(bq[0] - 0.03) < 1e-9 && Math.abs(bq[1] - 0.04) < 1e-9 && bq[3] === null, 'K.bh：BH 校正（0.01×3/1＝0.03；后缀最小）且 null 原样');
ok(K.qlt(null, 0.1) === false && K.qlt(0.05, 0.1) === true, 'K.qlt：null 不得当作 0（null<0.1 在 JS 为真）');
ok(Math.abs(K.poisUp(1, 1) - (1 - Math.exp(-1))) < 1e-6, 'K.poisUp 精确尾概率');
ok(K.poisUp(200, 100) < 1e-6 && K.poisLo(50, 100) < 1e-4, '期望 >60 用正态近似仍给出极小尾概率');
ok(K.qStyle(null, null) === '' && K.qStyle(0.2, null) === '', '不显著不着色');
window.KZ = { cfg: { study: { code: 'T' } }, kri: { defs: [{ k: 'wd', l: '提前退出率', u: '%', dir: 'high', qtl: [10, 15, 20] }], tiers: [['strict', '严格'], ['std', '标准'], ['loose', '宽松']], tierDefault: 'std', study: { wd: [16, 100] }, sites: {}, na: {} } };
const qs = K.qtlState('wd', [16, 100]);
ok(qs.st === 'exceed' && Math.abs(qs.v - 16) < 1e-9 && qs.lim === 15, '容忍限度：标准档 16% > 15% → 超出');
ok(K.qtlState('wd', [13, 100]).st === 'warn', '超过限度的 80% → 接近限度');

/* ---- V5 修复波④：热力图小中心「个案驱动」标注（不改判定，只改呈现）----
 * 分母极小（随访人日 <200；无 fu 时给药人数 ≤3）且校正后偏高（q<0.10）的格子 → cased 判定＋标注文案。 */
window.KZ = { cfg: {}, meta: {},
  centers: [{ site: '01', name: '大中心', n: 120, dosed: 120 }, { site: '02', name: '小中心', n: 2, dosed: 2 }, { site: '03', name: '少给药中心', n: 3, dosed: 2 }],
  subs: [], others: [], aes: [], queries: [], cro: [], labrows: [],
  pd: { potential: [{ sid: 'S9', site: '02', grade: '一般', rule: 'PD-1', id: 1, title: 'x', fact: '' }] },
  ops: { fu: { S1: 90000, S9: 50, S10: 50, S11: 9000 }, nnum: { '01': 500, '02': 20, '03': 10 }, entry: [] } };
K._subs = [{ id: 'S1', site: '01', fd: '2026-01-01' }, { id: 'S9', site: '02', fd: '2026-01-01' }, { id: 'S10', site: '02', fd: '2026-01-01' }, { id: 'S11', site: '03', fd: '2026-01-01' }];
K._subsBy = Object.fromEntries(K._subs.map(s => [s.id, s]));
K.lab = [];
K._cr = null;
const CR = K.centerRisk();
ok(CR.small && CR.small.has('02') && !CR.small.has('01'), '分母极小中心集合：随访人日 100<200 → small；90000 → 非 small');
ok(CR.small.has('03'), '给药 ≤3（随访人日 9000 大）也进 small（「或」口径）');
ok(typeof CR.cased === 'function' && CR.cased('pd', '02'), '小中心偏高格（q<0.10）→ 个案驱动判定为真');
ok(!CR.cased('pd', '01'), '大中心同格（不偏高）不标');
ok(!CR.cased('pd', 'zz'), '未知中心安全返回假');
ok(K.caseNote({ qu: 0.01 }, true).includes('个案驱动'), '标注文案含「个案驱动」');
ok(K.caseNote({ qu: 0.9 }, true) === '', '不偏高（q≥0.10）无标注');
ok(K.caseNote({ qu: 0.01 }, false) === '', '非小中心无标注');
ok(K.caseNote(null, true) === '', '无格数据无标注');

/* ---- R2-1（D002 E2E 深链页渲染崩溃）：ECharts markLine/markPoint 空数据守卫 ----
 * 实测（build ec34087 安全/监察深链页 pageerror×6）：markLine data 项坐标不可用（yAxis:undefined——
 * KRI 未配置容忍限度、中心中位数对空集合=null/NaN）在 ECharts 内部 marker 转换后进 Array.filter，
 * e[0].coord 取 undefined 崩整页。守卫＝K.chart 入口统一判空：不可数值化/缺失坐标的 marker 项剔除，
 * 全部无效则整个 markLine/markPoint 撤除（不渲染辅助线，不崩页）。 */
ok(typeof K.chartGuard === 'function', '缺 K.chartGuard（kz.js 空数据 marker 守卫）');
if (typeof K.chartGuard === 'function') {
  const o1 = { series: [{ type: 'line', data: [], markLine: { symbol: 'none', data: [{ yAxis: undefined }, { yAxis: 3 }] } }] };
  K.chartGuard(o1);
  ok(o1.series[0].markLine.data.length === 1 && o1.series[0].markLine.data[0].yAxis === 3, 'undefined 坐标项剔除、有效项保留');
  const o2 = { series: [{ type: 'scatter', data: [], markLine: { symbol: 'none', data: [{ xAxis: null }, { yAxis: NaN }, { xAxis: '' }] } }] };
  K.chartGuard(o2);
  ok(!o2.series[0].markLine, 'marker 项全部无效 → 整个 markLine 撤除');
  const o3 = { series: [{ type: 'line', markLine: { data: [{ xAxis: '2026-03-30' }, { yAxis: 0 }, { coord: [3, 4] }, [{ coord: [1, 2] }, { coord: [3, 4] }] ] } }, { type: 'bar', data: [1, 2] }] };
  const keep3 = o3.series[0].markLine.data.length;
  K.chartGuard(o3);
  ok(o3.series[0].markLine.data.length === keep3 && keep3 === 4, '字符串日期/数值/coord/点对 形态全部保留（不误伤既有研究）');
  ok(o3.series[1].data[0] === 1, '无 marker 的 series 原样通过');
  const o4 = { series: [{ type: 'line', markPoint: { data: [{ coord: [NaN, 1] }, { coord: [2, 3] }] } }] };
  K.chartGuard(o4);
  ok(o4.series[0].markPoint.data.length === 1, 'markPoint 同口径守卫（coord 含 NaN 剔除）');
  const o6 = { series: [{ type: 'line', markArea: { data: [[{ xAxis: '2026-01-01' }, { xAxis: undefined }]] } }, { type: 'line', markArea: { data: [[{ yAxis: 1 }, { yAxis: 3 }]] } }] };
  K.chartGuard(o6);
  ok(!o6.series[0].markArea && o6.series[1].markArea.data.length === 1, 'markArea：端点缺失整块撤除、完整区间保留（V6 抽屉图空白）');
  ok(K.dt('2026-01-02', '2025-01-27 10:23:11') === '2026-01-02' && K.dt('2026-01-02', '9:05') === '2026-01-02T09:05', 'K.dt：只接受时:分');
  ok(K.cmpTxt('2025-01-03', '2025-02-01') < 0 && K.cmpTxt('2025-03-01 09:00', '2025-03-01 10:00') < 0, 'K.cmpTxt：日期按字符串比（不只比年份）');
  ok(K.cmpTxt('10', '9') > 0 && K.cmpTxt('0.53 ×10^9/L', '1.2') < 0 && K.cmpTxt('甲', '乙') !== 0, 'K.cmpTxt：数值与文字');
  ok(K.dt('2026-01-02', '9:30:00') === '2026-01-02T09:30:00', 'K.dt：单位数小时补零（含秒）');
  const o5 = { series: [{ type: 'line', markLine: { data: [] } }] };
  K.chartGuard(o5);
  ok(!o5.series[0].markLine, '空 data 数组的 marker 撤除');
}

/* ---- V6：信号聚合（同受试者×同日期×同类别×同表单 → 一条；不同受试者/不同类型不合并；无受试者的研究/中心项原样） ---- */
require(path.resolve(dir, 'kz6.js'));
{
  const mk = (t, s, d, sh) => ({ kind: 'lab', sid: s, title: t, score: 90, x: { pts: [['W2', d, '1', '', null, 2, null, sh, 3, '', null, 'wb']] }, open() {} });
  const g = K.groupSig([mk('MCH · CS 未关联', '01', '2026-04-13', 'LB'), mk('MCV · CS 未关联', '01', '2026-04-13', 'LB'),
    mk('MCV · CS 未关联', '02', '2026-04-13', 'LB'), mk('MCV · CS 未关联', '01', '2026-05-01', 'LB'), { kind: 'qtl', sid: '', title: 'x', score: 85 }]);
  ok(g.length === 4, 'groupSig：只合并同受试者同日期同类同表单');
  const grp = g.find(x => x.group);
  ok(grp && grp.group.length === 2 && /2 项/.test(grp.title) && grp.why === 'MCH、MCV', 'groupSig：合并卡标题计数、列出指标');
}

/* ---- V6（用户审阅 RUX 第 1/5 条）：风险排名——角色过滤（roles）＋加权（ROLEW）、中心筛选、按分值降序；无处置状态 ---- */
{
  window.KZ = { cfg: {}, meta: {}, centers: [], subs: [], aes: [], queries: [], cro: [], labrows: [], pd: { potential: [] },
    others: [{ sid: 'S1', site: '01', cat: '入排标准核对', pr: 4, sum: 'a', d: '2026-01-01', sh: 'IE', row: 1, ctx: [] },
             { sid: 'S2', site: '02', cat: '访视超窗核对', pr: 3, sum: 'b', d: '2026-01-02', sh: 'SV', row: 2, ctx: [] }],
    ops: { entry: [{ sid: 'S3', site: '01', test: 'ALT', visit: 'W2', raw: '1', unit: 'U/L', why: 'x' }] } };
  K._cr = null; K._risk = null; K._subs = []; K._subsBy = {}; K.lab = [];
  ok(K.riskFor('all').length === 3, '风险排名：全部角色含专项与录入错误');
  ok(K.riskFor('cra').length === 1 && K.riskFor('cra')[0].kind === 'ent', '风险排名：临床监查只取其角色项');
  ok(K.riskFor('all', '01').length === 2, '风险排名：中心筛选');
  const pm = K.riskFor('pm'); ok(pm.length === 0, '风险排名：项目经理无对应项');
  const mm = K.riskFor('mm'); ok(mm.length === 2 && mm[0].score >= mm[1].score && mm[0].sig === undefined, '风险排名：按分值降序且无处置状态');
  ok(typeof K.sigSet === 'undefined' && typeof K.sigPill === 'undefined', '处置状态接口已删除');
}

if (fails) { console.error(`${fails} 处断言失败`); process.exit(1); }
console.log('render logic ok: knCard/knBar/knHint/ptCons/judgeCell/bh/poisUp/qlt/qtl/heatCase/chartGuard/groupSig/riskFor');
