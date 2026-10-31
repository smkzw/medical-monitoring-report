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
global.K = global.window.K = {};   // kz.js IIFE 后的顶层语句用裸 K（浏览器解析为 window.K）
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
ok(bar.includes('MedDRA 不可用') && bar.includes('知识层降级'), '总览警示条缺降级文案');
ok(bar.includes('box red'), '总览警示条应为红色警示样式');
ok(K.knBar(OKKN) === '' && K.knBar(null) === '', '非降级不渲染总览警示条');

/* ---- query 页头提示 ---- */
const hint = K.knHint(DEGRADED);
ok(hint.includes('关联类核对未含知识层预判'), 'query 页头提示缺固定文案');
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

if (fails) { console.error(`${fails} 处断言失败`); process.exit(1); }
console.log('render logic ok: knCard/knBar/knHint/ptCons/judgeCell');
