---
name: medical-monitoring-report
description: |
  临床试验医学监察（Medical Monitoring）报告一体化技能：基于研究方案、EDC 数据 listing（可选：分组/随机表、PD listing、CRO 已发质疑、
  量表/中心实验室/中心阅片、PK/PD/ADA）以及研究者手册（IB，可选），自动完成文件盘点、方案/IB 规则抽取、listing 解构与字段匹配、
  深度医学分析（按方案指定分级标准/版本自动分级——内置 CTCAE v5.0 / v6.0，支持方案自定义表、单位换算、指标自动映射；AE 漏报风险、AE/MH 关联、方案基线定义、方案阈值/AESI（术语/PT/SOC/实验室组合如 Hy’s law）、TEAE/AE 收集期、SAE/AESI 报告时限、禁用药与洗脱期、入排、访视窗、AE 记录质量、中心偏离漏斗图、
  有效性合理性、PD 逐事件比对），生成 9 页康哲风格交互式 HTML 报告（总览/研究要点/受试者 Profile/受试者时间线/安全性/有效性/客观检查/
  质疑/方法学）与可直接粘贴 EDC 的申办方 MM query 工作簿。
  触发词：医学监察报告、医学监查、MM 报告、medical monitoring、AE 漏报、实验室异常核查、受试者时间线、patient profile、
  受试者画像、个例 profile、禁用药核查、入排违背、医学 query、数据审阅。
  融合并取代 clinical-patient-profile-html、ae-risk-assessment、subject-timeline-builder 三个技能。
metadata:
  version: 1.0.0
  author: smkzw
  summary: 方案 + listing → 规则抽取 → 解构映射 → 深度医学分析 → 9 页医学监察 HTML + EDC query 工作簿（康哲设计体系）。
---

# 医学监察报告（Medical Monitoring Report）

面向任何临床试验的医学监察交付物生成器。输出必须**源数据可追溯**（每条信号带 workbook/sheet/Excel 行号与原值）、
**方案驱动**（规则来自当前方案/IB 原文，带出处）、**可直接行动**（query 文本可粘贴 EDC、与 CRO 已发质疑自动查重）。

## 核心原则（不可违反）

1. **不硬编码上一个项目的规则。** 研究分期、访视名称、基线、阈值、AESI、禁用药、入排、终点、分组、sheet/列映射一律从当前方案、IB、listing 推导；
   推导不出就预检提问，不得沿用旧项目。脚本只放通用逻辑，项目差异全部进 `study.json` / `rules.json` / `mapping.json`。
   - **分级标准及版本必须来自方案**（`cfg.grading`：CTCAE v5.0 / v6.0 / 方案自定义表 + overrides）；未指定时构建直接报错，绝不默认。
   - **检查模块按方案与 listing 出现与否决定**：妇科超声、眼科、肺功能、影像等只要 listing 有就自动成为通用「专项检查」组，没有就不出现；
     页面、图表、query 模板中不得出现当前研究不存在的模块或旧项目术语。
   - **方案设计要素先归类再落配置**：基线定义（指定访视/首剂或随机前最近/多次均值，可按指标不同）、AESI（术语/PT/SOC/组合/最低级别）、
     AE 收集期与 TEAE、报告时限、访视窗锚点（首剂/随机/前一访视）——按 `references/protocol-ib-extraction.md` 的模式目录识别。
2. **完整解构每一个上传文件。** 不因任务长而跳过方案、IB、listing 任一 sheet、PD、CRO 质疑、实验室、量表、PK/PD。
   字段匹配不清或有争议时，明确告诉用户哪个文件/sheet/字段无法识别，**问而不猜**。
3. **证据落到源行。** 每条风险/质疑保留 `sheet` + `row` + 原值/单位/参考范围/临床意义；报告图表只是导航，最终以 listing 为准。
4. **研究者判定优先于数值推断。** 不自动把检验与 AE 关联（时间窗内的候选 AE 只作上下文，并改问「是否关联」而非「补报 AE」）；
   分级表中没有数值条目（或单位无法换算）的指标不自动分级，需症状/干预判断的级别不推断；被规则降级的记录保留原始风险与降级依据。
5. **盲态保护。** `cfg.blind.on=true` 时不展示分组、不做分组对比、不展示可揭示分组的有效性汇总（`validate_contract.py` 会拦截）。
6. **计划外访视（USV）与提前退出（ET）不进入汇总/中心统计**，只在个体层面显示（除非用户明确要求）。
7. 已有足够文件与范围时**不要再问“是否开始构建”**；只就阻断项提问，一次问完。

## 输入

| 类型 | 必需 | 说明 |
|---|---|---|
| 研究方案（PDF/DOCX） | ✅ | 设计、SoA、基线、访视窗、阈值/AESI、禁用药/洗脱、入排、终点定义 |
| EDC 数据 listing（xlsx） | ✅ | 可多文件；支持“中文标签行 + 变量名行”双表头、长表/宽表 |
| 分组/随机表 | 可选 | 盲态项目通常不提供；提供时仅用于非盲场景 |
| PD listing | 可选 | 用于与禁用药/入排/超窗信号逐事件比对 |
| CRO 已发质疑 | 可选 | 用于查重，避免重复发 query |
| 量表/中心实验室/中心阅片/PK/PD/ADA | 可选 | 作为 findings 或 efficacy 域接入；无具体结果只展示采集状态 |
| 研究者手册（IB） | 可选 | 已知风险/常见不良反应 → AE 分类标签（`ibtag`）与 IB 注释 |

## 工作流（分阶段，对话式）

先读 `references/workflow.md`（每阶段的细节、提问模板、产物）。脚本均在 `scripts/`，从技能根目录运行；工作区建议 `work/<study>/`，输出 `out/<study>/`。

**阶段 0 · 文件盘点**
```bash
python3 scripts/inspect_listing.py edc=EDC.xlsx pd=PD.xlsx lab=central_lab.xlsx --out work/S
```
产出 `inventory.md`（每个 sheet 的表头行、域识别、列猜测、行数）、`mapping.draft.json`（`_guess` 标记待确认）、`precheck.md`（阻断/需确认/提示）。
同时通读方案与 IB（PDF 用 `pdftotext -layout`，DOCX 用 `markitdown`），列出章节与 SoA。

**阶段 1 · 方案/IB 规则抽取** → `rules.json` + `study.json`
按 `references/protocol-ib-extraction.md` 逐条抽取：每条规则 `{id, dom, st, src:[[位置, 原文摘录, 来源类型]]}`；
方案正文与 SoA 脚注冲突时写入 `study.consensus` 并标注采用口径。再把可执行部分落到 `study.json.analysis`
（分级标准 `cfg.grading`、基线 `cfg.baselineRules`、阈值/组合规则、AESI 定义、AE 收集期/TEAE、报告时限、禁用药正则、洗脱期、入排、
访视窗及锚点、有效性终点、aeMatch）。键说明见 `references/study-config.md`。

**阶段 2 · listing 解构与映射** → `mapping.json`
以 `mapping.draft.json` 为起点逐 sheet 确认（`references/mapping-schema.md`）：受试者/中心、访视、给药（首剂/末剂）、AE、MH、CM、PR、
实验室（长表）、生命体征/心电图（常为宽表，需写 `tests`）、有效性、PD、CRO 质疑、PK/ADA；`visit_map` 与 `clin_map`（正常 0 / NCS 1 / CS 2）必须完整。

**阶段 3 · 预检与最少提问**
汇总 `precheck.md` + 抽取中的不确定点，用一条消息问清阻断项（模板见 `references/workflow.md`）：分析人群（全部/已随机/已给药）、
USV 是否纳入、各指标基线定义、分级标准及版本、AESI 定义、AE 收集期/TEAE、非分级表指标阈值、是否盲态、多中心范围、缺失模块是否展示。
方案中能抽到的先抽，抽不到才问；问时附上方案原文位置或“方案未规定”。

**阶段 4 · 规范化与构建**
```bash
python3 scripts/normalize_listing.py work/S/mapping.json --out work/S/norm
python3 scripts/build_site.py --study work/S/study.json --norm work/S/norm --out out/S [--echarts echarts.min.js]
```
`build_site.py` 依次调用 `mm_build.py`（分析 → `HTML/data/*.js` + `analysis/*.json`）与 `export_queries.py`（在原 listing 副本首列写入「申办方MM query」）。
ECharts ≥6（轴断裂）：`--echarts` → `$ECHARTS_JS` → `~/.cache/mm-report/` → jsDelivr/unpkg 自动下载。

**阶段 5 · 医学审阅与人工 query**
阅读 `out/S/analysis/*.json` 与报告，按 `references/analysis-rules.md` 复核每类信号；需要补充的医学判断写入
`study.json` 的 `queries_manual`（人工 query）、`review`（审阅流程说明）、`todo`、`unres`（未决问题），再重建。query 写法见 `references/query-writing.md`。

**阶段 6 · 验证（必须执行，不能只看 JSON）**
```bash
node scripts/render_check.js out/S/HTML --shots out/S/shots      # 9 页 + 个例钻取 + 所有 tab + 抽屉；有报错 exit 1
python3 scripts/validate_contract.py out/S/HTML --source-check   # 数据契约、交叉引用、盲态守卫、源行回查
```
构建日志的 `grading … · graded metrics … · unit issues …` 必须核对：单位问题 >0 时补 `analysis.unitConv` 或 `cfg.ctcaeMap`。
内置分级表交付前可用 `python3 scripts/ctcae_import.py <NCI官方CTCAE.xlsx> --check scripts/grading/ctcae_v5.0.json` 对照官方文本。
用 `view_image` 抽查截图（总览、受试者、时间线、安全性、质疑、方法学）。检查清单见 `references/validation-checklist.md`。

**阶段 7 · 交付**
打包 `out/S/HTML/`（双击 `index.html` 离线可用）+ query 工作簿 + `analysis/`。向用户说明：人群口径、基线口径、信号数、query 数（按域）、
CRO 查重结果、未决问题与已知局限。

## 报告页面

`index` 总览 · `study` 研究要点与规则 · `subjects` 受试者 Profile · `timeline` 受试者时间线 · `safety` 安全性（AE/检验风险/其他信号）·
`efficacy` 有效性（盲态下不分组）· `objective` 客观检查趋势/中心漏斗图 · `queries` 质疑清单 · `methods` 方法学与规则溯源。
页面职责与数据来源见 `references/report-pages.md`；视觉规范见 `references/design-system.md`。

## 演示（端到端自测）

```bash
python3 scripts/make_demo.py --out examples/demo           # 生成虚构 EDC/PD/CRO 数据
python3 scripts/normalize_listing.py examples/demo/mapping.json --out work/demo/norm
python3 scripts/build_site.py --study examples/demo/study.json --norm work/demo/norm --out out/demo
node scripts/render_check.js out/demo/HTML && python3 scripts/validate_contract.py out/demo/HTML --source-check
```

## 参考文件

- `scripts/grading/` — 版本化分级表（`ctcae_v5.0.json`、`ctcae_v6.0.json`）与 `analytes.json`（指标自动映射）
- `references/workflow.md` — 分阶段操作细节、提问模板、交付话术
- `references/input-inventory.md` — 文件/sheet 识别规则与常见 listing 形态
- `references/protocol-ib-extraction.md` — 方案/IB 抽取清单与 rules.json 规范
- `references/mapping-schema.md` — mapping.json 全字段
- `references/study-config.md` — study.json（cfg / study / analysis / 人工审阅）全字段
- `references/analysis-rules.md` — 所有分析规则与风险分级
- `references/query-writing.md` — query 文本规范、查重、合并
- `references/data-contract.md` — 前端数据契约（KZ/KZT/KZX、个例文件）
- `references/report-pages.md` — 9 页职责
- `references/design-system.md` — 康哲设计体系与用户偏好
- `references/validation-checklist.md` — 交付前检查
- `references/lessons-learned.md` — 既往项目经验
- `vendor/` — 三个上游技能原文（仅供追溯，不直接调用）
