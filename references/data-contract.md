# 前端数据契约（HTML/data）

`mm_build.py` 输出，`validate_contract.py` 校验。所有文件为 `window.X = <JSON>;`，可离线 `file://` 打开。

## data/core.js → `window.KZ`
| 键 | 类型 | 内容 |
|---|---|---|
| `cfg` | dict | study.json.cfg（补默认值，含 taxonomy） |
| `meta` | dict | 生成时间、源文件、人群口径、计数 |
| `subs` | list | 受试者摘要（id, site, center, status, icf, fd, ld, age, sex, 风险计数…；盲态下无 grp） |
| `centers` | list | 中心汇总（n、csx/mhx/ncs2、AE 率、漏斗图数据） |
| `aes` / `aesum` | list / dict | AE 明细（含分类、IB 标签、TEAE、相关性、SAE/AESI；mm5 `rl`＝与试验药相关，TRAE 用）/ 汇总 |
| `labrows` | list | 检验风险组：`sid test mid risk pts[[visit,date,raw,unit,grade,clin,pct,sheet,row,desc]] base rel ctx q cro qkey…` |
| `others` | list | 规则信号：`sid cat pr sum v d sh row test rel ctx risk q qkey…` |
| `queries` | list | `id sid cat sh text parts ev[[sheet,row,visit,test]] cro qkey…`（PR-8：`sh`/`ev[0]` 用逐工作簿唯一 id `wb:sheet`，如 `lab:LB`） |
| `cro` | list | CRO 已发质疑 |
| `cons` | list | 同中心判定一致性 |
| `rules` / `methods` / `study` | list / list / dict | 规则溯源、方法学、研究要点 |
| `eff` | dict | 有效性：metrics, data, anomalies, rulesText |
| `review` / `todo` / `unres` | list | 审阅流程、待办、未决 |
| `pd` | dict | mm4 方案偏离：`taxonomy[[码,名称,层面,说明,DVCAT]]`、`potential[{id,sid,site,cat,layer,rule,title,dv,fact,date,visit,grade,why,action,src[[sheet,row,标签]],sig[类型,索引,qkey],ctx,status,matched}]`、`confirmed[{id,sid,site,cat,layer,rawCat,sub,desc,date,grade,rawGrade,status,src,matched[规则]}]`、`rules[{id,cat,title,grade,action,dv,logic,cfg,data,state,n}]`、`notDetectable`、`cutoff`、`hasListing`、`sites`、`critical`；signal 回链：`others[i].pdId`/`labrows[i].pdId` |
| `ops` | dict | mm5 临床监察：`subs`（字段名见 `fields`：id,site,status,icf,first 首个访视日期,rand,rand_d,fd,ld,eot_d,eot_why,eos_d,eos_why,rescreen,prev）、`vis{sid:[[访视,日期]]}`、`win`（方案访视窗）、`planned`、`cutoff`、`stage`、`ex{sid:{n,miss,pause,fast,devi}}`、`icf{sid:[[版本,日期]]}`、`entry[{sid,site,test,visit,date,raw,unit,why,sh,row,ctq?}]`（疑似录入错误）；V5 追加 `due[[sid,site,访视,窗起,窗止,实际,overdue|out|ok,研究日,目标日,−窗,+窗]]`、`upcoming[[sid,site,访视,窗起,窗止,目标日期]]`、`fresh{site:[最近记录日,距截止天数,在研例数]}`、`fu{sid:随访人日}`、`nnum{site:数值型检验记录数}`、`planned`（缺省取方案设计摘要「计划例数」） |
| `kri` | dict | V5：`defs[{k,l,g,u,dir,qtl:[严格,标准,宽松]|null,note}]`、`tiers`、`tierDefault`、`study{k:[分子,分母]}`、`sites{site:{k:[分子,分母]}}`、`na{k:原因}`、`pem{visits,items}`、`source`；随阈值档位（TIER_KEYS） |
| `cred` | dict | V5 数据可信度：`sites{site:{dig:[n,末位0/5数,p,q], flat:[可判组数,完全相同组数,p,q], shift:[检验数,偏离数,[[指标,z,n,中心均值,整体均值]]], dup:[组数]}}`、`flat[[sid,site,指标,值,次数]]`、`dup[[site,日期,[sid],值]]`、`digAll`、`flatRate`、`note` |
| `mhcm` | dict | mm5 安全性概况：`mh[[sid,术语,持续0/1]]`、`cm[[sid,药名,开始,结束,持续0/1,用药原因]]`（仅给药者） |
| `micro` | list | 微生物培养/药敏分域（判读型结果，不进检验异常/CS/阈值/PD/风险链；`micro_panel_mark` 先于 `build_findings`，带 `_micro` 的行不进 C.F/C.metric）：`[[sid,日期,访视,项目,结果原文,判读/说明,C\|S,sheet,row]]`（仅给药者；同受试者同日培养行 C 在药敏行 S 之前）。受试者文件 `ext` 同步追加「微生物培养与药敏」组 |
| `basis` | dict | mm4 研究依据页只读视图（visitWindows/eligibility*/prohibited/washout/aesi/reportRules/thresholdRules/comboRules/indicationBackground/cmProtocolRequired/pd/effRulesText） |

`qkey`（labrows / others / queries 各自带，PR-2）：跨快照稳定的业务键，格式 `lab|<sid>|<risk>|<wb>:<sheet>|<mid>|<主访视>`、
`oth|<sid>|<规则id或cat>|<wb>:<sheet>|<记录业务键>`（关联记录优先用 AE/CM 编号，无编号回退「术语＋开始日期」；检验类规则用「指标|访视|日期」）、
queries 取其主源（首源，合并格同此）的 qkey，手写 query（`study.queries_manual`）为 `man|<sid>|<cat>|<wb>:<sheet>|<访视>|<日期>|<指标>`。
行号与原值不进入 qkey——他人行增删导致的行号漂移、同一记录的数值更正都不改变身份；sheet 名以工作簿别号限定，同名 sheet 跨工作簿可区分。

## data/trend.js → `window.KZT`
`meta.visits`、`subjects`、`centers`、`metrics[{id,label,unit,lo,hi,dom,grp,…}]`、`obs{metricId: [...]}`（每个 metric 必须在 obs 中有键）。

## data/extra.js → `window.KZX`
`soa`（SoA 完成度矩阵）、`soacols`、`ex{queryId: {rows:[{sh,row,f:{列:值},hl}], cro:[...]}}`（query 抽屉中的源行原文）、
`pdex{pdId: [{sh,row,lab,f,hl}]}`（mm4 方案偏离抽屉的源行原文）。
labrows `pts` 行：`[visit,date,raw,unit,grade,clin,pct,sheet,row,desc,dev,wb]`——`pts[10]` 为偏离比例（仅 REL/MHX-T 填值），`pts[11]` 为归属工作簿（mm4 修正 PR-8 的位冲突）。

## data/grading.js → `window.KZG`
`{label, system, version, source, items{代码:[criteria]}, map{metricId: 代码}, fac{metricId: {单位: 系数}}}`——由 `cfg.grading` 加载的分级表（含 overrides）与本研究指标映射；
`assets/ctcae.js` 只读此文件，不含任何版本特定阈值。`validate_contract.py` 校验 `KZG.label == cfg.ctcaeVersion` 且 map 中代码均在表内。

## data/s/<sid>.js → `KZ_SUB({...})`
个例：基本信息、`visits[[code,label,date,flag]]`、`ae` `mh` `cm` `ec`（给药）`pr` `labs` `vs` `ecg`（按指标的时间序列；行 `[0 date,1 visit,2 value,3 raw,4 unit,5 lo,6 hi,7 clin,8 desc,9 sheet,10 row,11 tpt,12 time,13 isBaseline,14 归因码,15 原因说明,16 关联摘要（「；」分隔）,17 分级,18 较基线%,19 疑似录入错误说明]`，既有位不动、只在尾部扩位）`ext`（CRO 质疑）`eff` `tl`（时间线事件/风险行）。
`KZ.subs` 中每个受试者都必须有对应文件（按需加载）。

## 不变量
- 证据 `[sheet,row]` 必须指向 `_source.json.sheets` 中的 sheet（PR-8 起键＝逐工作簿唯一 id `wb:sheet`；同名 sheet 于不同工作簿各有其键，`sheets_by_name` 供名称反查），`--source-check` 时必须是源 workbook 的非空行。
- query id 唯一；labrows/others 的 sid 必须在 subs 中。
- `cfg.blind.on` 时任何文件不得出现分组字段/分组名（守卫检查）。

### V5 追加字段
- 检验风险行、专项信号、疑似录入错误、潜在 PD 可带 `ctq`（关键数据原因：关键访视 / 关键评估 / 停药相关指标）。检验与录入错误只按指标判定，访视只用于方案偏离与访视类信号。
- 新专项类别：`范围内明显变化`、`持续变化趋势`（pr＝2，不发质疑），归入领域「检验变化预警」。
- 工作台系统层（`window.KZS`，可无）：`sigstate{键:{s,r,n,rk,by,at}}`（处置状态）、`history[{bid,snap,cutoff,n{lab,oth,pd,ent,q},rd{new,worse,resolved},kri,sites}]`（跨上传，旧→新，≤12）、`timeliness{basis,snaps,sites{site:{n,med,p90,gt14,mod:[修改删除数,当前记录数],lastNew}}}`；汇总失败时 `trendError`。

### V6 追加（2026-11-02）
- **原始数据层**（`raw_export.py`）：`data/rawidx.js` → `window.KZRI={sheets:{<表单id>:{name,wb,mapped,domain,cols,const,hl,n,nsub}},subs:{sid:[表单id…]},dropped:[隐私列名…]}`；`data/r/<sid>.js` → `KZ_RAW(sid,{<表单id>:[[原始行号,…值]]})`。覆盖全部工作簿中含受试者列的表单（含未映射表单）；剔除姓名/缩写/身份证/电话/住址类列；全导出行同值的列上提为 `const`；差异导出中标记删除的行不导出。表单 id 与 `_source.json.sheets` 同口径，证据 `[sh,row]` 可直接定位。
- `_source.json`：`sheets.<id>.domain`（映射域）、`unmapped`（未映射表名，终点无数据时给候选来源表）。
- `KZ.ops`：`visitAlias{方案访视键:数据代码}`、`visitUnmapped[…]`、`kriPending{ipd,elig}`（待核实未计入容忍限度分子的受试者数）；访视推算 `due` 的研究日按锚点（首剂 D1 记法；末次给药/随机/知情/前一访视为「锚点后第 t 天」）。
- `KZ.bind.notes[]`：规则指标正则零命中时的重绑说明、有效性终点 src 名称核心对齐说明（研究依据页显示）。
- `KZ.eff.missing[].cands[]`：可能的来源表（未映射）。
- `KZ.qx[]`（工作台回写）：AI 来源质疑（ai_csb/ai_review），`kz.js` 载入时按 qkey 并入 `KZ.queries`。
- `analysis.consMinDiff`（默认 0.05）：判定一致性「更差方」须多偏离参考边界的相对幅度；0＝无最小差（2026-10-30 旧口径）。
- 页面：参与者资料空间新增 `raw.html`（原始数据浏览）；个例页新增「原始数据」页签、受试者旅程图、异常指标热力图；中心页新增受试者风险构成图；行动项按「受试者×日期×类别×表单」聚合。
