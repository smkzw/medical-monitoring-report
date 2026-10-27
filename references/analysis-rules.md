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

| **DISW** | 判 CS、研究者原因选「研究疾病」、无关联，但给药后较基线加重 | 3 | query：按 AE 定义（不论因果）评估是否记录 AE（D21） |
| DIS | 判 CS 且归因研究疾病，未较基线加重；或判 CS、未关联未填原因，但指标属方案/IB 列出的研究疾病表现（`indicationBackground`，如特应性皮炎的嗜酸性粒细胞增多）且较基线未进一步加重 | 1 | 不作为风险：不发 query、不进潜在 PD，可见（背景标「研究疾病表现·未加重」） |

**较基线加重（D14/D19，全报告同一口径）**：①分级升高——基线已 ≥1 级后再升级，或升到 ≥2 级；**0 级 → 1 级不单独算**（用户 2026-10-27 确认，避免略超上限即判加重）；②超出参考范围且同向较基线变化 ≥T_base（默认 30%）。二者满足其一即加重；仅临床意义由 NCS 变 CS（判定波动）不算加重。实现：skill `ext_rules.grade_up`、`mm_build.worse_vs_base`，工作台 `review/csb.py::deterministic_worsening`，三处同口径。

原则：先 NCS 判定口径、后 CS 漏报；“候选 AE”只作上下文，绝不自动关联；关联对象不存在（AE+3 但无 AE3）单独提示。
**CS 原因（mm4）**：findings 可映射研究者填写的原因 `reason`（单选文本，按 `reason_map` 归类为 disease 研究疾病 / link 病史·不良事件 / other 其他）
或复选框 `reason_disease/reason_link/reason_other`；关联字段写法见 mapping-schema（`病史-3 - 贫血 - 日期`、`AE+1+头痛` 等）。
原因选「病史/不良事件」但未关联编号 → 仍按 CSX（事实即未关联），上下文注明；同一行既有研究疾病又有关联时以关联为准。
关联按（受试者×指标）汇总，但逐点核对：某次 CS 结果自身未关联、且日期不在本组已关联 AE/MH 的起止期间内 → 该组仍按 CSX（避免一次关联掩盖其他访视的未关联）。

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
- 禁限用药：药名正则命中，且用药期与「首剂前 daysBefore 天 ~ 末剂/末次观察」重叠。类别名含「系统/全身/口服/静脉」的不匹配外用/局部给药（按给药途径或剂型）；用药原因为「补救治疗」且在首剂后开始的，由补救规则（CM-02/03）核查，不按禁用药报。
- 洗脱期：距知情/首剂不足 N 天仍在用或末次在窗内。
- 命中后与 PD listing 逐事件比对（§10）。

## 8. 入排（mm4：受试者级判定，消除复查/计划外噪音）
- `eligibility`：每位受试者 × 每条标准**只判一次**。判定集合＝入组（随机，无随机日期时首剂）之前的测量；`visits` 限定访视，
  未写时取 SoA 中首剂访视之前的计划访视＋计划外（筛选期复查常记为计划外）；`window` 限定距入组日天数。
  判定值 `pick`：`last`（默认，入组前末次有效测量——方案允许复查时以复查值为准）/ `first`（首次筛选值）/ `any`（方案明确不允许复查）。
  其余不符测量写入上下文，不另成信号。`kind: inclusion|exclusion` 只影响事实句措辞；`on: val|uln|lln`。
- `eligibilitySubject`：人口学字段（年龄、BMI…）。
- 入排信号同时成为潜在 PD（ELIG-01/02，见 protocol-deviation.md）。

## 9. 访视窗与 SoA
- 超窗：实际研究日不在 `[目标−前窗, 目标+后窗]`。
- SoA 完成度热图：访视 × 检查项，按实际发生访视比对；计划外访视单列，不计入缺失。

## 10. 方案偏离（mm4，详见 protocol-deviation.md）
- 已记录 PD 归一（分类＋分级映射）；潜在 PD = 既有信号（入排/洗脱/禁用药/超窗/潜在 AE 漏记/报告时限/阈值未见 AE）＋执行层面规则
  （程序早于知情、未再次知情、首剂早于随机、访视缺失、评估缺失/未做、访视内顺序、途径/频次、停药后给药、依从性、空腹、样本时点、补救）。
- 分级：重要 / 待判定 / 一般，附依据；逐事件比对：已记录 / 未见记录 / 无 PD 记录可比对。
- 旧的 `pdCats` 关键词比对仍保留：PD 已记录的禁用药/入排/超窗信号 pr 降为 2（不再发 query）。

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

## 16. 扩展规则（M13–M23 确定性部分；编号沿用工作台执行包 03 §3）
词表键：`analysis.mhMatch` [[指标Re, 病史术语Re]]、`analysis.cmIndicationMap` [[用药原因Re, 疾病术语Re]]、
`analysis.indicationBackground` [[指标Re, 说明]]、`analysis.cmProtocolRequired` [药名Re]、`analysis.aeMatch`（已有）、
`study.diseaseProgressionNotAE` {quote, loc, confirmed}。**词表缺失 → 对应规则零命中＋todo 列「词表未配置」**（不猜医学对应）。

- **M13 MHX-T**：首剂前判 NCS/未评价且偏离 ≥T_dev（或 ≥2 级/定性 ≥+）且病史未记录（`mhMatch` 未命中、检验页未关联病史）
  → labrows 候选 pr2（不发 query）。排除 CS（M23）、研究疾病表现（`indicationBackground`）、已触发入排核查（M09）的同一数值；
  首剂前 ≥2 次或首剂后同向持续 → ctx「持续异常」；`cmIndicationMap` 对应用药 → ctx「有对应用药」。qkey `lab|sid|MHX-T|wb:sheet|mid|主访视`。
- **M15 血压**：与其他数值项一致（T_dev/T_base 默认 30%，D18）；listing 未给范围时默认上限 收缩压 139 / 舒张压 89 mmHg（仅用于偏离计算）。
- **M16 定性**：±/弱阳性/微量 → pr1 提示（判 CS 走 M01）；基线阴性 → 给药后 ≥+ → 定性新发：研究者未评价临床意义 → pr3 发 query；已评价为正常/NCS → pr1 仅提示（研究者判定优先，2026-10-27 用户确认）；判 CS 者由 M01/M23 分层。
- **M17 CM-IND**：合并用药原因指向疾病、病史与 AE 均无对应记录（`cmIndicationMap`）→ pr3 发 query；首剂前开始问病史、首剂后问 AE；
  排除预防用药与 `cmProtocolRequired` 方案合并治疗。qkey `oth|sid|M17|wb:sheet|CM 编号`。
- **M18 PREG**：任何时点妊娠试验阳性或 hCG 超范围 → pr4 发 query（不进 AE 漏报分层）。
- **M19 AE-EX**：给药中断（原因=不良事件）±`aeExWindow`（默认 7）天无对应措施的 AE；或 AE 措施=暂停/停药但给药记录无中断 → pr3 发 query。给药记录的「中断」包括暂停原因文本、实际剂量为 0 的区间、相邻给药区间的空档；措施为停药时末次给药日期在 ±窗口内即视为一致。
- **M20 AE-SAE**：SAE=是但标准全空 / 勾选标准但 SAE=否 / 转归死亡与研究结束日期不一致 / 死亡后仍有给药、访视或检验 → pr4 发 query。
- **M21 AE-COURSE**：AE 已结束但关联检验结束后仍异常（≥2 级）→ pr2 提示（`query:false`）；末次访视异常未恢复且 AE 未结束无随访安排 → pr2 提示。
- **M23 CSB（步骤 1/1′/2/3/4 确定性＋候选导出）**：所有时点判 CS 的检验/检查——
  关联对象不存在 → **LINK** query（pr3）；关联对应性优先用宿主预判 `analysis.linkVerdicts`（`{"wb:sheet|行号": {v: implausible|plausible|unknown, why}}`，
  工作台以 MedDRA SOC＋指标器官系统、方向、时间等正面证据生成）：implausible → LINK，plausible → 视同对应，unknown → 步骤 5；
  无预判时词表命中 → 对应、**词表未命中 → 步骤 5（词表未覆盖≠关联错误）**，仅 `linkStrict: true` 沿用旧口径；
  研究者原因为「研究疾病」且无关联：给药前或未恶化 → 通过，给药后恶化 → DISW（M01）；关联 AE 对应 → 通过（等级一致性 M07）；
  关联/匹配（`mhMatch` 时段覆盖）病史：给药前或未恶化 → 通过，给药后恶化 → **MH 加重** query（pr3）；
  同期匹配 AE（`aeMatch`）→ **CSX_AE**（pr4，不自动关联）；指标属方案/IB 列出的研究疾病表现（`indicationBackground`）：较基线未进一步加重 → **DIS**（不作为风险）；较基线进一步加重（上方加重口径）→ **CSX_DIS**（pr4，请评估是否给药后加重应记 AE，或注明属疾病自然波动）；基线缺失 → 仍按 CSX；给药后确定性恶化（等级升高/CS 新出现/超范围且同向较基线 ≥T_base/
  基线缺失按新发；T_base 取 `cfg.thresholds.base`）→ 基线异常 **CSW**（pr4）/ 基线正常或缺失 **CSX**（pr4），不调模型（D19）；
  方案进展条款已确认（`diseaseProgressionNotAE.confirmed`）且有研究疾病线索的确定性恶化 → 转候选交 A5R5（D21）；
  其余（给药前未绑定、给药后未恶化未绑定、词表无法判断、文本型恶化未知）→ **步骤 5 候选**导出
  `analysis/csb_candidates.json`（字段：ref/sid/domain/test/label/visit/date/post/value/unit/lo/hi/grade/gl/clin/desc/
  baseline/worsening{known,value,flags}/binding{link,matched_ae,matched_mh}/disease_hint/source），
  由工作台 `review/csb.py::explain_cs` 做 A5R5 三问＋恶化与 A6 复核。
- **DATEORD 日期序**：AE/合并用药/给药 开始>结束（均有完整日期，影响洗脱/TEAE/给药期判定）→ pr3 发 query（S45 收口）；
  不做纯格式/缺失类数据管理核查。

## 组合规则（`comboRules`）
同一受试者同日（或 `window` 天内）多指标同时满足 `all` 且不满足 `none`，如 Hy’s law：ALT 或 AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN。
命中后核对 `expectAE` 时间窗内是否有对应 AE（`aesi:true` 时同时核对 AESI 勾选）；`pr` 决定是否发 query。
