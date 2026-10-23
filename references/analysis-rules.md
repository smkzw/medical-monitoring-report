# 分析规则

## 1. 人群、日期与基线
- 首剂 `fd` = 给药记录最早有效开始日；末剂 `ld` = 最晚结束/开始日；末次观察 `lo` = 所有域最晚日期。
- 状态：筛选失败（无首剂且无随机号）/ 完成试验 / 提前退出 / 治疗结束 / 已入组（可被 `subjects.status` 覆盖）。
- 给药后：日期 > 首剂，或首剂当日且时间点匹配 `postTptRe`。研究日 = 日期 − 首剂 + 1（无 D0）。
- 基线：按 `cfg.baselineRules`（指定访视 / 首剂·随机·ICF 前最近有效值 / 多次均值，可逐指标定义）；缺失 → 按规则回退（默认首剂前最近有效值），标注「替代」；仍无 → 「基线缺失」。
- TEAE / AE 收集期：`analysis.teae`、`analysis.aePeriod`（方案定义）；收集期后的检验异常不生成漏报风险。
- USV/ET：个例页显示，汇总、中心漏斗图、访视均值不纳入。

## 2. 分级（`scripts/ctcae.py` 声明式求值器 + `scripts/grading/*.json`；前端 `assets/ctcae.js` 读 `data/grading.js`）
- **标准与版本来自方案**（`cfg.grading`）：内置 CTCAE v5.0、v6.0；方案自定义/其他体系（FDA 2007、DAIDS 等）写成同格式 JSON 用 `file` 指定；`overrides` 改个别条目。
- 条目格式：`{代码: [{term, zh, dir:H|L, when:baseNormal|baseAbnormal, absolute, note, steps:[{by:val|xuln|xlln|xbase|chg|pct|duln, op, v:数值|ULN|LLN|BASE, g, and}]}]}`；
  `units` 声明标准单位与换算系数，`ratio` 为无单位指标。版本差异（如 v5.0 肝酶基线异常按 ×基线、v6.0 的 ALT/AST/ALP 新规则）全部在表里，不在代码里。
- 指标 → 代码：`analytes.json` 自动映射 + `cfg.ctcaeMap` 覆盖；% 单位（如中性粒细胞%）不映射。
- 单位：原单位按 `analysis.unitConv` 或表内 `units` 换算到标准单位；无法换算 → 不分级，`unitIssue` 写入构建日志与 `grading_map.json`。
- 只自动判定可凭数值确定的级别；需症状/干预/临床后果的级别（如低钠 2 vs 3 级）不推断，条目 `note` 说明。
- 分级表无条目（如尿酸在 v6、多数尿常规）：不分级，可用 `relChange` 相对变化补充筛查。
- 内置表交付前可用 `ctcae_import.py <官方xlsx> --check` 对照 NCI 官方文本（数值阈值逐级核对，未确认项人工复核）。

## 3. AE 漏报风险（检验/生命体征/心电图）
对每个 受试者×指标，仅看给药后记录，满足“新发或加重”才纳入：判 CS；或 CTCAE 等级 > 基线；或临床意义高于基线；或基线正常而现异常。

| 层级 | 条件 | pr | 默认动作 |
|---|---|---|---|
| **CSX** | 任一点判 CS，且未关联 AE/MH | 4 | query：请评估是否记录 AE；时间窗内有候选 AE → 改为「CS未关联·同期疑似AE」，请求关联 |
| **MH** | 判 CS，仅关联病史 | 3 | 与基线比较：加重 → query（是否给药后加重应记 AE）；同级 → 提示 |
| **NCS2** | 均判 NCS，但分级 ≥2 级，且未关联 AE | 3 | query：说明 NCS 依据或更正 |
| **NA2** | 无临床意义评价，但分级 ≥2 级 | 3 | query：请研究者评价临床意义并评估是否记录 AE |
| AE | 已关联 AE | 1 | 仅核对 AE 等级一致性（见 §5） |
| NCS | NCS 且 <2 级 | 1 | 不发 query |

原则：先 NCS 判定口径、后 CS 漏报；“候选 AE”只作上下文，绝不自动关联；关联对象不存在（AE+3 但无 AE3）单独提示。

## 4. AE/MH 关联合理性
- 关联解析自检验页“关联”字段；对关联对象核对：存在性、器官/样本一致（血 vs 尿）、方向一致（升高 vs 降低、体重增加 vs 减轻）、时间先后。
- `aeMatch` 用于发现“时间窗内可能对应但未关联”的 AE。

## 5. AE 记录质量（`aeChecks`）
- `predose_related`：首剂前开始的 AE 记为相关。
- `grade_vs_lab`：AE 等级 < 关联检验的数值分级（按方案分级标准）。
- `cm_flag`：AE 记“无合并用药”，但 CM 用药原因指向该 AE。
- `aesi_terms`：术语/PT/SOC 符合 AESI 定义（`analysis.aesi`，含 minGrade）但未勾选 AESI；`aesi_unmatched`：勾选 AESI 但不符合任何纯术语型定义。
- `reportRules`：SAE/AESI 报告日期 − 获知（或发生）日期 > 方案时限。
- `duplicate`：同术语时间重叠的重复记录。

## 6. 方案阈值专项（`thresholdRules`）
逐点比对方案原文阈值（绝对值/较基线/百分比/×ULN/×LLN），核对 `expectAE` 时间窗内是否有对应 AE/AESI：
无 → 「未见对应 AE 记录」保持高优先；有但 AESI 未勾选 → 提示；有且完整 → 降为 pr 2。

## 7. 合并用药
- 禁限用药：药名正则命中，且用药期与「首剂前 daysBefore 天 ~ 末剂/末次观察」重叠。
- 洗脱期：距知情/首剂不足 N 天仍在用或末次在窗内。
- 命中后与 PD listing 逐事件比对（§10）。

## 8. 入排
- `eligibility`：给药前检验/体征数值满足排除条件但已入组。
- `eligibilitySubject`：人口学字段（年龄、BMI…）。

## 9. 访视窗与 SoA
- 超窗：实际研究日不在 `[目标−前窗, 目标+后窗]`。
- SoA 完成度热图：访视 × 检查项，按实际发生访视比对；计划外访视单列，不计入缺失。

## 10. PD 逐事件比对
对禁用药/入排/洗脱/超窗信号：同受试者、类别关键词（`pdCats`）匹配、日期 ±`pdWindow` 天 → 「PD 已记录」；否则「未见 PD 记录」提示补录。

## 11. 同中心判定一致性（cons）
同中心、同指标、同单位/参考范围、同方向，数值相差 ≤`consTol`：一例 CS 一例 NCS → 提示判定尺度不一致（不以多数为准）。

## 12. 中心偏离（漏斗图）
中心层面 CS 率/异常率/AE 率等 vs 总体，控制限 ±2SE（关注）/ ±3SE（明显偏离）；n<2 不判；不含 USV/ET；只做中心沟通，不对个例发 query。

## 13. 有效性
按方案终点定义派生（绝对值/较基线变化/百分比/应答），检查范围越界（`effRules`）、关键访视缺失、个体轨迹异常跳变；**盲态下不分组、不展示可揭示分组的对比**。

## 14. PK / PD / ADA / 中心阅片
- 有结果：作为 findings 展示趋势与个例；PK 关注采样时间偏差（与给药时间）、BLQ、异常高值；ADA 阳性与 AE（超敏/注射部位反应）时间关联。
- 只有采样状态：仅展示采集完成度，不做数值判断。
- 中心阅片与研究者评估不一致：作为有效性/安全性核对信号，由 MM 决定是否发 query（`queries_manual`）。

## 15. REL 双阈值候选（较基线显著变化且超出参考范围）
给药后数值超出参考范围、偏离 ≥T_dev（高于上限 (x−ULN)/ULN、低于下限 (LLN−x)/LLN；单侧只算有界一侧），
且同向较基线变化 ≥T_base（|x−基线|/|基线|，方向须与超出方向一致；`metricDir` 单向不利指标只计不利方向）
→ REL 风险项（pr2，不自动发 query，可转 query）。范围内变化不论较基线变化多大都不计风险（明细可见 Δ%）；
超出范围但 Δ<T_base（基线已异常）不算新风险。构建按最低档 20% 写全量候选（`per_metric`/`metricThreshold`
更低时取收紧值），每点携带偏离比例（`pts[10]`），页面按所选 T_dev/T_base 即时重分类、不重新构建；
同一 (受试者,指标) 已有 pr≥3 条目时 REL 不重复列行，双阈值事实写入该条目上下文。

## 组合规则（`comboRules`）
同一受试者同日（或 `window` 天内）多指标同时满足 `all` 且不满足 `none`，如 Hy’s law：ALT 或 AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN。
命中后核对 `expectAE` 时间窗内是否有对应 AE（`aesi:true` 时同时核对 AESI 勾选）；`pr` 决定是否发 query。
