# study.json 规范

顶层：`cfg`（前端显示配置）· `study`（研究要点页内容）· `rules`（规则数组或 `"rules.json"`）· `ibtag` · `analysis`（分析引擎）·
人工审阅：`queries_manual` · `review` · `todo` · `unres` · `methods`（均可为数组或相对路径 json 文件名）。完整示例：`examples/demo/study.json`。

## cfg
| 键 | 说明 |
|---|---|
| `study` | `{title, short, code, subtitle, tags:[[文字, 样式]], planned}`；样式 `org/yel/red/grn/blu/gray` |
| `brand` / `footer` | `{org, logo}` / `{left, right}` 页脚 |
| `visits` | `{order:[SoA 顺序], unsched:["USV"], early:["ET"], d1:"D1", labels:{代码: 显示名}}` |
| `grading` | **必填**（或旧键 `ctcaeVersion: "CTCAE v5.0"`）。`{system:"CTCAE", version:"5.0"\|"6.0", file?, overrides?, label?}`：内置表 `scripts/grading/ctcae_v<版本>.json`；方案自定义毒性表用 `file`（相对 study.json，格式同内置表）；`overrides:{代码:[criteria…]\|null}` 替换/删除个别条目（如方案对 QTcF 另有分级）。未指定版本时构建报错 |
| `baselineRules` | 基线定义（先匹配先用）：`[{match:"<指标id正则>", method:"visit"\|"lastPre"\|"mean", visits:[…], tpt:"<时间点正则>", ref:"fd"\|"rand"\|"icf", unsched:true\|false, fallback:"lastPre"\|"none", label}]`。visit=指定访视；lastPre=首剂/随机/ICF 前最近有效值（`unsched:false` 排除计划外）；mean=指定访视多次测量均值（如三联 ECG）。未匹配的指标按 `baseline` 旧键，再缺省为首剂前最近有效值 |
| `baseline` | 旧键（仍支持）：`{lab:"V1", vs:"D1", vsTpt:"前", ecg:"D1", ecgTpt:"前", labLabel}`；缺失时回退首剂前最近有效值并标注「替代」 |
| `blind` | `{on, tag, hidden:[被隐藏内容说明]}`；on=true 时清空分组、隐藏分组对比 |
| `ctcaeMap` | 可选覆盖：`{"<域>:<检查项>": "<分级代码>"}`；`""` 表示不分级。缺省由 `scripts/grading/analytes.json` 按检查项名（中/英/缩写）自动映射，结果写入 `analysis/grading_map.json` 供核对 |
| `ctcaeVersion` | 由构建自动写为分级标签（如 `CTCAE v5.0`），前端显示用；手写仅作旧键兼容 |
| `relChange` | `{metrics:"<正则>"}`：REL 双阈值候选的指标限定（`pct` 已废弃——相对变化补充筛查语义由 M14 REL 双阈值取代） |
| `thresholds` | `{dev:0.3, base:0.3, per_metric:{}}`：双阈值 T_dev（偏离上下限）/T_base（同向较基线变化），默认各 30%（血压同为 30%）；`per_metric` 按指标覆盖（如 `{"vs:收缩压":{"dev":0.1}}`，默认为空） |
| `metricDir` | `{指标正则: "up"|"down"}`：单向不利指标只计不利方向（如降压药研究中血压只计升高） |
| `metricThreshold` | `[{metric, dev?, base?, quote}]`：项目收紧阈值，有效值=min(所选档位,收紧值)，两参数各自计算；须带方案/IB 原文（`quote`） |
| `labGroups` | `{sheet名: 组名}` 用于 query 表单名匹配与展示 |
| `strat` | `{label, flag}` 分层因素显示 |
| `refLines` | `{检查项: [[值, 标签]]}` 趋势图参考线 |
| `ulnMult` | `[[检查项正则, 倍数]]` 趋势图 ×ULN 参考线 |
| `metricRules` | `[{match, note, flags:[{on:"val|chg|pct", op, v, why}], lines:{val:[[v,label]], chg:[...]}}]` 客观检查页指标级规则 |
| `query` | `{label, file, extLabel, extShort, note}` 质疑页文案与工作簿名 |
| `defaultTest` | 客观检查页默认指标 id（如 `lab:丙氨酸氨基转移酶`） |
| `keyDays` | `[[研究日, 标签]]` 时间线关键日 |
| `timeline` | `{preDays:30}` 时间线向 ICF 前延伸天数（CM/MH 条带截断） |
| `taxonomy` | 可选；`{domains:[...]}` 信号分类分组，缺省按类别自动生成 |

## study（研究依据页）
mm4 新增：`calibers:[[主题, 采用口径, 状态, 规则id, 说明]]`（关键口径；缺省由配置推导，状态 方案规定/口径裁定/待确认/项目配置/默认采用）·
`criteria:[{no, kind, text, check:data|partial|judgment, rule}]`（入排逐条与可核查性）· `endpoints:[[类型, 文本, 规则id]]` · `design.facts:[[要素, 值, 规则id]]`。

`design{sub, refs, flow:[{n,b,x}], arms, baselines}` · `soaNote` · `soaRefs` · `consensus:[[主题, 冲突, 采用口径, 色, 规则id]]` ·
`thresholds:[{t, c, rows:[[条件, 色, 处理]]}]` · `ib{notes:{分类:[说明, 规则id]}}` · `prohibited{groups:[[名称, 色, [药名]]], note, refs}` ·
`eligibility:[[项目, 标准, 规则id]]` · `eligCats` · `ruleGroups:[[组名, 规则id正则]]`。

## analysis（分析引擎；括号内为默认值）
**人群与时间**
- `population`（`dosed`）：`dosed` | `randomized` | `all`。
- `postTptRe`（`后`）：首剂当日时间点匹配则视为给药后。
- `visitWindows`：`{访视: [目标研究日, 前窗, 后窗]}`（锚点首剂，研究日 = 访视日 − 首剂日 + 1）或 `{访视: {target, minus, plus, anchor:"fd"|"rand"|"icf"|"<前一访视代码>"}}`（非首剂锚点时 target = 距锚点天数）。访视代码与 listing 写法不同（如方案「V6/W4/D29」、EDC「W4/D29V6」）时，构建按访视标记集合（字母＋数字）自动对齐到 listing 写法（同组唯一、其次唯一超集）；visits.order/d1/unsched/early、soa、pd 关键访视同样对齐。
- `aePeriod`：`{ref:"ld"|"fd"|"eos_d", days}` AE 收集期终点（如末次给药后 28 天）；之后的检验异常不再生成漏报 AE 风险。`eos_d` 锚点而受试者仍在研 → 收集期开放（不回退到末次给药）。
- `teae`：`{ref, days}` TEAE 定义（首剂后起至 ref+days）；AE 汇总与受试者计数按 TEAE 口径。
- `soa`：`[{name, sheet, visits:[...], cond}]` 自定义 SoA 完成度；缺省从 findings/visits 推断。

**AE**
- `relatedRe` / `unrelatedRe`：相关性取值正则。
- `aeCatMap`：`[[术语正则, 分类]]`（分类与 `ibtag` 对齐）。
- `aesi`：方案 AESI 定义 `[{id, name, terms:"<术语/PT/LLT 正则>", soc:"<SOC 正则>", minGrade}]`；实验室/多指标型 AESI 用 `thresholdRules`/`comboRules` 并设 `aesi:true`。旧键 `aesiTermRe` 仍支持。
- `aeChecks`（全部开启）：`predose_related`、`grade_vs_lab`、`cm_flag`、`aesi_terms`（符合定义未勾选）、`aesi_unmatched`（勾选但不符合任何纯术语型定义）、`duplicate`。
- `reportRules`：`[{flag:"serious"|"aesi", days:1, from:"aware"|"start", label:"SAE 24h", pr(3), requireDate}]` 报告时限（需 AE 映射 `aware`/`rpt` 日期）。

**检验/生命体征/心电图**
- `labDomains`（`["lab","vs","ecg"]`）：参与 AE 漏报风险的 findings 域。
- `unitConv`：`{"lab:血红蛋白": {"g/dL": 10}}` 覆盖分级换算系数（原单位 → 分级表标准单位）；缺省用分级表 `units`（g/dL、mg/dL、/mm³ 等常见换算已内置）。无法换算 → 不分级并记 `unitIssue`。
- `qualTestRe`：定性指标正则（不做数值分级）。
- `aeMatch`：`[[指标正则, AE术语正则, ±天数]]` 时间窗内候选 AE（只作上下文，不自动关联）。
- `consTol`（0.05）：同中心判定一致性的数值容差。
- `extFlagPct`（50）：变化幅度红色高亮阈值。

**规则信号**
- `thresholdRules`：`[{id, metric(正则), on:val|chg|pct|uln|lln|grade, op, v, label, cat, pr, aesi, expectAE(正则), window, visits, post(true), once, sum(模板), ask, query, qcat, lane, level}]`；
  `sum` 可用 `{test} {value} {unit} {visit} {date} {thr} {base} {chg} {pct} {uln} {lln}`。
- `comboRules`：多指标组合（如 Hy’s law）`[{id, name, all:[{metric, on:val|uln|lln|chg|pct|grade, op, v}], none:[…], window:0(同日), aesi, expectAE, aeWindow(30), pr, cat, sum, ask, once}]`。
- `prohibited`：`[{name, re, daysBefore, daysAfter, pr(4), cat, note}]` 与首剂前 N 天至末次给药后 M 天重叠。
- `washout`：`[{name, re, days, ref:"icf"|"fd", pr(3), cat}]`。`prohibited`/`washout` 可选 `exceptRe`（点名除外的药名正则）与
  `classes`（`[[类名, 成员正则], …]`，质疑文案只列该药实际命中的类）；条款原文写「镇静抗组胺…（允许/可使用非镇静抗组胺药）」时
  必须把例外写进 `note`——引擎据此不把二代非镇静抗组胺（西替利嗪/氯雷他定/依巴斯汀等通用名）计入该条款（F1/F3，一代镇静照常）；
  「外用疗法」类条目写 `route:"topical"`——吸入/雾化/鼻用/眼用/注射复方不按外用核查（F2）。
- `eligibility`：`[{id, metric, visits, on:val|uln|lln, op, v, text, pr, cat, pick:last|first|any, window, kind:inclusion|exclusion}]`（受试者×标准一条，判定值见 analysis-rules §8）；`eligibilitySubject`：`[{field, op, v, label, text}]`。
- `prohibited[].important`：该禁用类别影响疗效评价或安全（潜在 PD 分级为重要）；`thresholdRules[].stop`：永久停药阈值（WD-01）。
- `linkVerdicts`：`{"wb:sheet|行号": {v, why}}` CS 关联对应性预判（宿主生成）；`linkStrict`（false）：无预判时词表未命中是否直接 LINK。
- `pd`：方案偏离参数（criticalVisits/criticalItems/preIcfAllowed/icfVersions/dosing/fasting/compliance/sample/order/rescue/requireRand/catMap/grades/window/enabled），见 protocol-deviation.md §6。
- `pdCats`：`{信号类别: PD 关键词正则}`；`pdWindow`（45 天）：PD 逐事件匹配时间窗。

**有效性**
- `efficacy`：`[{id, label, unit, kind:continuous|ordinal|binary, src:"eff:<metric>"|"lab:<test>"|"exam:<test>", derive:chg|pct, baseVisit, visits, keyVisit, signed, refLines, categories, note, kpi, agg:"max"}]`。
  mm4 起由工作台确定性生成（`mm3/protocol/efficacy.py`：方案终点 × listing 量表/检验/检查指标），不再手填；`src` 可指向 lab/exam 指标（如 Hb、肌瘤体积）；`agg:"max"` 用于终点写「最大的…」时同访视多条记录取最大。基线取方案基线访视（D1/首次给药前）；该指标没有 D1 访视时取给药前最后一次。lab/exam 来源的测量值做量级检查（同一受试者某次与本人其余访视中位数相差 ≥10 倍 → pr3 query「有效性数据量级异常」，疑似单位/录入错误，同时在有效性页列出；量表不查）。
- `diseaseTerms`：研究疾病缩写（如 `["AD"]`，工作台从方案「特应性皮炎（AD）」写法编译），用于识别备注里的研究疾病归因。
- ~~`clinConsistTol`~~：已废止（2026-10-30 判定一致性改为方向性口径，见 analysis-rules）。
- `expectedAE`：`[{term, label, re, pt, soc, basis, src: ib|protocol, loc, labs: [[analyte, label, direction]]}]` 产品风险（工作台从 IB 风险表/方案风险章节编译）：AE 按术语/PT 匹配打「IB重要潜在风险·…」标记（同 SOC 的标「同SOC」），检验按风险的检验表现在背景中注明。
- `queryTexts`：`{qkey: {h, text}}` 工作台模型按事实卡写好的质疑句子；`h` 与本次构建的事实卡哈希一致才采用，否则用程序措辞。事实卡输出在 `analysis/query_cards.json`。
- `formNames`：`{表单代码: 中文名}`，缺省读 EDC 导出的目录页（TOC）；页面证据位置显示「血生化（LBCH）第 n 行」。
- `cfg.dataStage`：数据阶段 `daily`（日常监查，数据滚动录入）/ `prelock`（锁库前全量）/ `cfdi`（锁库后核查前）；工作台入口选择后写入。`daily` 下不判定计划访视缺失（VIS-02）与「无记录」类评估缺失（ASMT-01），有效性关键访视只提示「暂未见记录」。缺省按全量处理。
- `effNotes`：`[文本]` 生成说明（未对上终点的量表、主要终点无 listing 数据等），有效性页页头显示；没有指标时页面显示「未生成有效性趋势」＋原因，不再是「未配置」。
- `effRules`：`[{metric, op, v, label, cls, st, visits, qcat}]`；`effRulesText` 页面说明。

**query 生成**
- `queryRisks`（`["CSX","MH","NCS2","NA2"]`；NA2 = 未评价临床意义但达分级 ≥2 级）：检验风险中自动成 query 的层级。
- `queryMinPr`（3）：规则信号 pr ≥ 该值才生成 query；单条规则可 `query:false`。
- `queryTemplates`：覆盖内置模板 `{key: [类别, 事实模板, 请求]}`（key：CSX/MH/CSX_AE/NCS2/NA2；模板可用 `{gl}` 分级标签）。
- `askByCat`：`{类别: 默认请求语}`。
- `mergeSameCell`（true）：同一 EDC 单元格多条信号合并为一条 query（追加「另：…」）。
- CRO 查重：`synonyms`（`[[ALT,丙氨酸氨基转移酶],…]`）、`dedupStop`、`dedupMinOverlap`（0.45）、`dedupMinOverlapNum`（0.2，含相同数字时）、
  `formNames`（`{sheet: 表单名}`）、`conflictRe`（CRO 质疑含“无需/删除”等视为冲突）、`skipDuplicates`（false，true 时同主题已查重不再输出）。

## 人工审阅键
- `queries_manual`：`[{sid, cat, sh, row, v, d, test, fact, ask}]` → 进入 query 清单与工作簿，来源标记为人工。
- `review`：审阅流程卡片；`todo`：`[[标题, 样式, 说明, 链接]]`；`unres`：未决问题；`methods`：覆盖内置方法学表。
