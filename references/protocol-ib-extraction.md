# 方案 / IB 抽取规范

目标：把方案与 IB 中**可执行、可核查**的内容抽成带出处的规则（`rules.json`），再把其中可编程的部分写入 `study.json.analysis`。
抽取由模型逐章阅读完成；不得凭经验补全方案没写的规则。

## 抽取清单（逐项过，缺失写“方案未规定”）

| 主题 | 典型章节 | 落点 |
|---|---|---|
| 研究设计、分组、盲态、治疗/随访时长 | 概要、§3 | `R-DES-*`；`study.design`；`cfg.blind` |
| SoA：访视名称、顺序、各访视检查项、时间点（给药前/后） | SoA 表 + 脚注 | `cfg.visits.order`、`analysis.soa`、`study.soaNote` |
| 访视窗（含锚点：首剂/随机/前一访视） | SoA / 访视章节 | `R-VW-*`；`analysis.visitWindows` |
| 基线定义（逐指标/逐域） | 统计（SAP）/评估章节 | `R-BL-*`；`cfg.baselineRules` |
| 分级标准及版本（含方案自定义分级、个别指标特殊分级） | 安全性章节 / 附录 | `R-AE-*`；`cfg.grading`（**必填**） |
| AE 收集期、TEAE 定义 | 安全性 / 统计 | `R-AE-*`；`analysis.aePeriod`、`analysis.teae` |
| AESI / 特别关注事件定义 | 安全性章节 / IB | `R-AESI-*`；`analysis.aesi`、`thresholdRules`/`comboRules`（`aesi:true`） |
| SAE/AESI/妊娠等报告时限 | 安全性报告章节 | `R-AE-*`；`analysis.reportRules` |
| 数值阈值：AESI、停药/暂停、复查、剂量调整、Hy's law | 安全性/剂量调整 | `R-*`；`analysis.thresholdRules`、`cfg.metricRules`、`cfg.refLines`、`cfg.ulnMult` |
| 禁用/限用药、洗脱期 | 合并用药章节 | `R-CM-*`；`analysis.prohibited`、`analysis.washout`、`study.prohibited` |
| 入选/排除标准（可数据化的） | 入排章节 | `R-IE-*`；`analysis.eligibility`、`analysis.eligibilitySubject`、`study.eligibility` |
| 终点定义（主要/次要/探索）、量表范围与方向、应答定义 | 终点/统计 | `R-EFF-*`；`analysis.efficacy`、`analysis.effRules` |
| 研究结束/退出、提前终止访视 | 退出章节 | `cfg.visits.early` |
| IB：常见不良反应、潜在/已识别风险、器官系统 | IB 安全性汇总 | `R-IB-*`；`ibtag`、`study.ib.notes` |

## 方案设计要素的模式目录（先识别属于哪种模式，再写配置；不要假设与上一个项目相同）

**基线定义**
| 方案常见写法 | 配置 |
|---|---|
| “基线定义为 V2（D1）给药前的最后一次评估” | `{"match":"^lab:","method":"visit","visits":["D1"],"tpt":"前","fallback":"lastPre"}` |
| “基线为首次给药前最后一次非缺失值（含计划外）” | `{"match":".","method":"lastPre","unsched":true}` |
| “……不含计划外/复查值” | `{"method":"lastPre","unsched":false}` |
| “随机前最后一次”（未给药人群/给药与随机不同日） | `{"method":"lastPre","ref":"rand"}` |
| “D1 给药前三次 ECG 的均值” | `{"match":"^ecg:","method":"mean","visits":["D1"],"tpt":"前"}` |
| 实验室取筛选期、生命体征/ECG 取 D1 给药前（按域不同） | 多条规则按 `match` 分域；先匹配先用 |
| 方案未写 | 预检提问；建议“首剂前最近有效值”，并在方法学页注明“方案未规定，采用…” |

**AESI**
| 方案常见写法 | 配置 |
|---|---|
| 列出事件术语（如“QT 间期延长、尖端扭转型室速”） | `aesi:[{"id":"AESI-1","name":"QT 延长","terms":"QT.*延长|尖端扭转"}]` |
| 以 MedDRA PT/SMQ/SOC 定义 | `terms` 写 PT 正则（AE 需映射 `pt`/`llt`），`soc` 写 SOC 正则；SMQ 需展开为 PT 列表 |
| “≥3 级的皮疹” | `{"terms":"皮疹","minGrade":3}` |
| 实验室阈值（“QTcF ≥500 ms”“ALT >5×ULN”） | `thresholdRules` + `aesi:true` + `expectAE` |
| 组合标准（Hy’s law：ALT/AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN） | `comboRules` + `aesi:true` |
| 特殊情况（妊娠、过量、用药错误） | 规则写入 `rules.json`；listing 有对应表单时用 `thresholdRules`/人工 query 核对 |
| 方案无 AESI | `aesi` 留空，不开 AESI 相关检查，页面不显示 AESI 统计 |

**分级标准**
| 方案写法 | 配置 |
|---|---|
| “按 NCI-CTCAE v5.0 分级” | `cfg.grading: {"system":"CTCAE","version":"5.0"}` |
| v6.0 | `{"system":"CTCAE","version":"6.0"}` |
| 方案附录自定义毒性分级 / FDA 2007 健康志愿者毒性分级 / DAIDS | 抄成 `scripts/grading/` 同格式 JSON，`{"system":"…","version":"…","file":"grading_custom.json"}` |
| “QTc 按方案附录 X 分级”等个别条目 | `overrides: {"QTCF": [ … ]}` |
| 方案未写 | **阻断项**，预检提问；不得默认 |

**AE 收集期 / TEAE / 报告时限**：“签署 ICF 至末次给药后 28 天” → `aePeriod:{"ref":"ld","days":28}`；
“首次给药后发生或加重的 AE” → `teae:{"ref":"ld","days":28}`（终点按方案）；“SAE 获知后 24 小时内报告” → `reportRules:[{"flag":"serious","days":1,"from":"aware"}]`。

**检查模块**：只为方案 SoA 中存在、且 listing 中有数据的检查建页/建组（妇科超声、眼科、肺功能、影像、体格检查等均自动归入通用「专项检查」组，
`cfg.extTab` 可改名）；方案没有的模块不出现、不提问。

## rules.json 规范

```json
[{"id": "R-AESI-01", "dom": "AESI", "st": "QTcF ≥500 ms 或较基线增加 >60 ms 为 AESI，24 小时内报告。",
  "src": [["方案 §8.3.2", "QTcF ≥500 ms 或 ΔQTcF >60 ms……", "protocol_operative"],
          ["IB §6.4", "非临床研究提示 hERG 抑制……", "ib"]]}]
```
- `id`：`R-<主题>-<序号>`；主题与 `study.ruleGroups`（`[[组名, 正则]]`）对应，用于研究要点页分组。
- `st`：一句话可执行陈述（数值、单位、时限写全）。
- `src`：`[位置, 原文摘录（≤80 字）, 来源类型]`；来源类型：`protocol_operative`（正文）、`protocol_soa`（SoA/脚注）、`protocol_appendix`、`ib`、`sap`、`user_confirmed`（用户口头确认）。
- 原文冲突（正文 vs SoA 脚注 vs 附录）：两条都保留，并写 `study.consensus`：`[主题, 冲突描述, 采用口径, 颜色(grn/org/red), 规则id]`。

## 从规则到配置的示例

| 方案原文 | analysis 配置 |
|---|---|
| ALT 或 AST >3×ULN 需 48–72h 复查 | `{"id":"T-ALT","metric":"^lab:(丙氨酸|天门冬)","on":"uln","op":">","v":3,"expectAE":"转氨酶|ALT|AST|肝","window":14,"pr":4,...}` |
| 禁用强效 CYP3A4 抑制剂（首剂前 14 天至末次给药） | `{"name":"强效 CYP3A4 抑制剂","re":"克拉霉素|酮康唑|伊曲康唑","daysBefore":14,"pr":4,"note":"R-CM-01"}` |
| 筛选前 30 天内使用全身性激素者排除 | `{"name":"全身性糖皮质激素","re":"泼尼松|甲泼尼龙|地塞米松","days":30,"ref":"icf"}` |
| 年龄 18–65 岁 | `eligibilitySubject: [{"field":"age","op":"<","v":18,...},{"field":"age","op":">","v":65,...}]` |
| 筛选期 eGFR <60 排除 | `eligibility: [{"id":"R-IE-05","metric":"^lab:eGFR","visits":["V1"],"op":"<","v":60,"text":"排除标准 5"}]` |
| W4 访视 D29 ±3 天 | `visitWindows: {"W4": [29, 3, 3]}` |
| 随访访视为末次给药后 28±7 天 | `visitWindows: {"FU": {"target":28,"minus":7,"plus":7,"anchor":"<末次给药访视代码>"}}` |
| 禁用药：首剂前 14 天至末次给药后 7 天 | `prohibited: [{"name":…,"re":…,"daysBefore":14,"daysAfter":7}]` |

## IB 使用
- 只抽“已识别/潜在风险、常见不良反应（发生率）”，不抽非临床细节。
- `ibtag`：`{"<AE分类>": ["IB常见"|"IB潜在"]}`，分类名需与 `analysis.aeCatMap` 输出一致。
- IB 未提供：`ibtag` 为空，`methods` 页注明“未提供 IB，AE 预期性未评估”。
