# 前端数据契约（HTML/data）

`mm_build.py` 输出，`validate_contract.py` 校验。所有文件为 `window.X = <JSON>;`，可离线 `file://` 打开。

## data/core.js → `window.KZ`
| 键 | 类型 | 内容 |
|---|---|---|
| `cfg` | dict | study.json.cfg（补默认值，含 taxonomy） |
| `meta` | dict | 生成时间、源文件、人群口径、计数 |
| `subs` | list | 受试者摘要（id, site, center, status, icf, fd, ld, age, sex, 风险计数…；盲态下无 grp） |
| `centers` | list | 中心汇总（n、csx/mhx/ncs2、AE 率、漏斗图数据） |
| `aes` / `aesum` | list / dict | AE 明细（含分类、IB 标签、TEAE、相关性、SAE/AESI）/ 汇总 |
| `labrows` | list | 检验风险组：`sid test mid risk pts[[visit,date,raw,unit,grade,clin,pct,sheet,row,desc]] base rel ctx q cro…` |
| `others` | list | 规则信号：`sid cat pr sum v d sh row test rel ctx risk q…` |
| `queries` | list | `id sid cat sh text parts ev[[sheet,row,visit,test]] cro …` |
| `cro` | list | CRO 已发质疑 |
| `cons` | list | 同中心判定一致性 |
| `rules` / `methods` / `study` | list / list / dict | 规则溯源、方法学、研究要点 |
| `eff` | dict | 有效性：metrics, data, anomalies, rulesText |
| `review` / `todo` / `unres` | list | 审阅流程、待办、未决 |

## data/trend.js → `window.KZT`
`meta.visits`、`subjects`、`centers`、`metrics[{id,label,unit,lo,hi,dom,grp,…}]`、`obs{metricId: [...]}`（每个 metric 必须在 obs 中有键）。

## data/extra.js → `window.KZX`
`soa`（SoA 完成度矩阵）、`soacols`、`ex{queryId: {rows:[{sh,row,f:{列:值},hl}], cro:[...]}}`（query 抽屉中的源行原文）。

## data/grading.js → `window.KZG`
`{label, system, version, source, items{代码:[criteria]}, map{metricId: 代码}, fac{metricId: {单位: 系数}}}`——由 `cfg.grading` 加载的分级表（含 overrides）与本研究指标映射；
`assets/ctcae.js` 只读此文件，不含任何版本特定阈值。`validate_contract.py` 校验 `KZG.label == cfg.ctcaeVersion` 且 map 中代码均在表内。

## data/s/<sid>.js → `KZ_SUB({...})`
个例：基本信息、`visits[[code,label,date,flag]]`、`ae` `mh` `cm` `ec`（给药）`pr` `labs` `vs` `ecg`（按指标的时间序列；行 `[date,visit,value,raw,unit,lo,hi,clin,desc,sheet,row,tpt,time,isBaseline]`）`ext`（CRO 质疑）`eff` `tl`（时间线事件/风险行）。
`KZ.subs` 中每个受试者都必须有对应文件（按需加载）。

## 不变量
- 证据 `[sheet,row]` 必须指向 `_source.json.sheets` 中的 sheet，`--source-check` 时必须是源 workbook 的非空行。
- query id 唯一；labrows/others 的 sid 必须在 subs 中。
- `cfg.blind.on` 时任何文件不得出现分组字段/分组名（守卫检查）。
