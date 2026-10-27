# 方案偏离（PD）规则与口径

引擎：`scripts/pd_rules.py`（`mm_build.py` 在全部信号生成后调用）→ `KZ.pd`、`KZX.pdex`；页面：`deviations.html`。
本文件是 PD 的**审阅口径**，所有数值阈值、窗口、关键访视等都来自当前方案（`study.json`），代码不写任何研究取值。

## 1. 定义（按证据级别）

| 概念 | 口径 | 依据 |
|---|---|---|
| 方案偏离（PD） | 对方案设计或程序（含方案引用的手册/计划，如实验室手册、SAP）的任何改变、背离或偏移；与过错和原因无关 | ICH E3 Q&A (R1) 2012 Q7；ICH E6(R3) 2025 术语表；TransCelerate PD Process Guide §3.1 |
| 重要方案偏离 | PD 的子集：可能显著影响关键研究数据的完整性、准确性、可靠性，或显著影响受试者权益、安全、福祉；申办方应制定试验特定的判定标准 | ICH E3 Q&A (R1) Q7；ICH E6(R3) Annex 1 §3.9.3；FDA PD 指南草案（2024-12）§III.A.1 |
| 方案违背 / Major / 严重 | 与「重要方案偏离」混用的别名；本系统主字段用 重要 / 一般，别名只做映射 | ICH E3 Q&A Q7；TransCelerate §3.2 |
| 中国要求 | 所有偏离应记录；重要方案偏离要解释、采取纠正预防措施，并向伦理与申办者报告 | 《药物临床试验质量管理规范（2026 年修订）》第二十三条（2026-09-01 施行） |
| 不算 PD | 与方案无关的 GCP 问题（如授权表缺签名）；录入错误更正后不再偏离；按方案条件使用的补救治疗（属伴发事件） | FDA 草案 §II；TransCelerate §3.4、§7；ICH E9(R1) §A.3.1 |

## 2. 已记录 PD 与潜在 PD

- **已记录 PD**：PD listing（`domains.pd`）中的事件。原文类别按关键词归一到统一分类（`analysis.pd.catMap` 可前置覆盖），
  原文严重程度映射：严重/重要/重大/major → 重要；轻微/一般/minor → 一般；其余（如「根据实际情况判定」）→ 待判定。
- **潜在 PD**：数据规则推出、待 CRA/研究者核实的候选，**不是结论，不计入 PD 率**。每条带：分级＋依据（why）、处理建议、比对状态。
- **比对**：同受试者＋同分类＋日期 ±`analysis.pdWindow`（缺省 `analysis.pd.window`，默认 30 天）→「已记录」；PD listing 有但无匹配 →「未见记录」；
  未提供 PD listing →「无 PD 记录可比对」。
- **处理建议**：发 query（数据层面可澄清）／CRA 核实（需源文件）／录入 PD（数据已足以确认）。

## 3. 分类（层面 → CDISC DVCAT）

| 码 | 名称 | 层面 | DVCAT（SDTM CT C225352） |
|---|---|---|---|
| ICF | 知情同意 | 执行 | INFORMED CONSENT/ASSENT |
| RAND | 随机与盲态 | 执行 | STUDY INTERVENTION |
| VIS | 访视计划 | 执行 | TRIAL PROCEDURES |
| ASMT | 评估与检查 | 执行 | TRIAL PROCEDURES |
| IP | 研究药物与给药 | 执行 | STUDY INTERVENTION |
| SAMP | 样本采集 | 执行 | TRIAL PROCEDURES |
| ELIG | 入组资格 | 科学 | INCLUSION/EXCLUSION |
| CM | 合并用药 | 科学 | PROHIBITED CONCOMITANT INTERVENTION |
| SAFE | 安全性记录与报告 | 科学 | SAFETY REPORTING |
| WD | 退出与停药 | 科学 | DISCONTINUATION |
| OTH | 其他 | — | — |

## 4. 规则目录（默认分级 → 升级条件）

| 规则 | 检查 | 默认 | 升级 / 说明 | 需要的数据与配置 |
|---|---|---|---|---|
| ICF-01 | 研究程序早于知情同意 | 重要 | 排除方案允许的 ICF 前既往检查（`pd.preIcfAllowed`）；同日无时刻不判 | 知情日期＋各程序日期 |
| ICF-02 | 修订版要求再签而未再签 | 重要 | — | `domains.icf`＋`pd.icfVersions` |
| RAND-01/02 | 首剂早于随机；未随机即给药 | 重要 | 「无随机信息」只在 `pd.requireRand` 时判 | 随机日期/号＋给药 |
| ELIG-01 | 入排数值不符仍入组 | 重要 | 判定值见 analysis-rules §8 | `analysis.eligibility*` |
| ELIG-02 | 洗脱期不足 | 重要 | — | `analysis.washout` |
| VIS-01 | 访视超窗 | 一般 | 关键访视（`pd.criticalVisits`）→ 重要 | `analysis.visitWindows` |
| VIS-02 | 计划访视缺失 | 一般 | 窗口在截止前关闭且仍在研才判；关键访视 → 重要；随之缺失的检查不另报；配置访视半数以上在 listing 中不存在 → 不运行（标未配置，避免代码对不上时整批误报） | 同上 |
| ASMT-01 | 已到访视的 SoA 评估缺失 | 一般 | 关键评估（`pd.criticalItems` 正则）→ 重要；SoA 未配置时按数据推断并标低置信 | `analysis.soa` |
| ASMT-02 | 评估记录为未做 | 待判定 | 是否方案允许（条件性/可复用）需看原因 | 「是否进行」字段 |
| ASMT-03 | 访视内先后顺序违背 | 一般 | 同一宽表行只计一次 | `pd.order`＋时刻字段 |
| IP-01 | 途径/频次与方案不符 | 待判定 | — | `pd.dosing` |
| IP-02 | 终止治疗/研究结束/妊娠阳性后仍给药 | 重要 | 区间型给药记录取结束日期 | 给药＋治疗结束 |
| IP-03 | 依从性超出方案范围 | 重要 | 累计 ≥ `minDays` 才评估；范围内但非 100% 不报（避免每例一条） | `pd.compliance`＋`exposure.qty` |
| IP-04 | 非空腹给药 | 一般 | — | `pd.fasting`＋`exposure.fast` |
| SAMP-01 | 给药前样本晚于给药 | 重要 | PK 谷浓度不可用 | `domains.sample` 时刻＋给药时刻 |
| SAMP-02 | 给药后样本超窗 | 一般 | 时点标签自带窗口（「4h±30min」）优先，其次 `pd.sample.windowMin`；方案允许超窗采样时可在 `pd.grades` 改为待判定 | `pd.sample.windowMin` |
| CM-01 | 禁用药 | 待判定 | `prohibited[].important` 的类别 → 重要 | `analysis.prohibited` |
| CM-02 | 补救早于允许时间 | 重要 | — | `pd.rescue.earliestDay` |
| CM-03 | 补救后未按要求停药 | 重要 | — | `pd.rescue.stopRequired` |
| SAFE-01 | 潜在 AE 漏记（CSX / DISW / 病史加重） | 待判定 | 数值 ≥3 级 → 重要；经确认未记录才构成 PD | labrows |
| SAFE-02 | SAE/AESI 报告超时 | 重要 | — | `analysis.reportRules`＋获知/报告日期 |
| SAFE-03 | 方案阈值事件未见对应 AE | 待判定 | — | `thresholdRules[].expectAE` |
| WD-01 | 达到停药标准仍给药 | 重要 | — | `thresholdRules[].stop` |

`analysis.pd.grades = {规则: 分级}` 可整体覆盖默认分级（例如把本研究 PD 界定表的「严重/轻微」落进来）。缺配置的规则不运行，
`KZ.pd.rules[].state = unconfigured`（页面「检查规则与覆盖」可见），不猜。

## 5. 只能经源文件核查 / 外部系统确认（页面如实标注，不从 listing 推断）

知情同意书原件与签名要素、伦理批准版本；药物运输/储存温度/有效期/药号/发放回收清点；随机系统分层与药号、紧急揭盲；
SAE 获知与报告提交时间（listing 无日期时）；访视内操作细节（静息、空腹、采血与 ECG 先后，无时刻字段时）；样本处理与冷链；
研究者判断类入排条件；伦理规范执行。

## 6. 配置（`analysis.pd`）

```json
{"criticalVisits": ["W12"], "criticalItems": "症状评分|EASI",
 "preIcfAllowed": [{"item": "胸部CT|CRCT", "ref": "icf", "days": 31}, {"item": "HBV|HCV|IGRA", "ref": "fd", "days": 28}],
 "icfVersions": [{"ver": "2.0", "effective": "2026-04-15", "reconsent": true}],
 "dosing": {"route": "口服", "freq": "QD|每日一次"}, "fasting": true,
 "compliance": {"perDay": 1, "lo": 80, "hi": 120, "minDays": 14},
 "sample": {"preRe": "给药前", "windowMin": {"default": 15}},
 "order": [{"before": "生命体征|量表", "tptRe": "给药前", "visits": ["D1"], "label": "给药前评估须在首剂前完成"}],
 "rescue": {"re": "补救", "earliestDay": 29, "stopRequired": false},
 "requireRand": true, "catMap": [["访视.*超", "VIS"]], "grades": {"VIS-01": "一般"}, "window": 30, "enabled": true}
```
`thresholdRules[].stop: true`（永久停药阈值）与 `prohibited[].important: true`（影响疗效/安全的禁用类别）也参与分级。
工作台由方案模型（PM3/PM4/PM7 任务）抽取并编译这些参数；人工编写时每项都应能在方案中找到原文。
