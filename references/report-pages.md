# 报告页面（templates/site）

| 页面 | 职责 | 主要数据 |
|---|---|---|
| `index.html` 总览 | mm5：首屏「先看这里」（CS 未关联、较基线加重、重要潜在 PD、需关注中心、本次新增/加重、疑似录入错误、待发质疑，最多 6 张，点击直达）＋页面导览；KPI 全部可下钻；「需关注中心」与风险页热力图同一算法（K.centerRisk）。其余：KPI（含方案偏离）、医学风险分层（入排/用药/访视类信号转方案偏离）、方案偏离概览（执行/科学层面＋重要潜在 PD）、AE 谱×IB、AESI、中心风险矩阵（含潜在/重要 PD）、入组、主要待办；**底部折叠区「审阅要点与方法学」**（与 methods.html 同一渲染器，含方案偏离审阅要点） | KZ.meta/subs/labrows/others/queries/todo/pd/review |
| `study.html` 研究依据 | 只陈述「依据什么」：研究概况（设计流程、要素、终点）→ 关键口径（状态：方案规定/口径裁定/待确认/项目配置/默认采用）→ 监查规则 tab（入组资格逐条可核查性 · 合并用药 · 访视与执行 · 安全性判定 · 产品与适应症风险）→ 方案/IB 规则库。数据结果（SoA 完成度、AE×IB）移至方案偏离与总览/AE 页 | KZ.study/rules/basis/pd |
| `subjects.html` 受试者 Profile | 左侧受试者列表（数字排序、状态/风险筛选）；个例：基本信息、访视、AE/MH/CM/给药、检验矩阵（异常着色、CTCAE 等级、临床意义）、CRO 质疑 | data/s/<sid>.js |
| `timeline.html` 受试者时间线 | 研究日轴（ICF−preDays 起），给药/AE/CM/MH/PR 条带，访视点，**风险事件独立行**，关键日；悬浮提示含源 sheet/行 | data/s/<sid>.js (tl) |
| `deviations.html` 方案偏离（mm4） | KPI（已记录 / 潜在执行层面 / 潜在科学层面 / 未见记录 / 涉及受试者 / 检查覆盖）、类别×分级矩阵、中心分布；tab：潜在 PD·执行层面 · 潜在 PD·科学层面 · 已记录 PD · SoA 完成度 · 检查规则与覆盖；抽屉：事实、分级依据、源行原文、判定规则与 CDISC 术语、与已记录比对、关联信号与质疑、处理建议 | KZ.pd, KZX.pdex, KZX.soa |
| `profile.html` 安全性概况（mm5） | 三级 Profile：全试验 / 中心（`#c=`）/ 受试者（`#s=`）。AE（TEAE/TRAE/SAE/AESI/≥3级/停药/各级）、AE 类别发生率、病史、合并用药（含给药后新开始）、检验异常（风险层每例＋基线→基线后最差新发/加重）、检验/客观指标趋势（整体箱线＋中心中位线＋本例线，数值/较基线/较基线%）、有效性趋势；中心对照整体、受试者对照所在中心与整体。渲染器 `assets/profile.js` 的 `K.profile`，参与者资料页「概况」页签复用 | KZ.aes/mhcm/labrows/eff、KZT（按需载入） |
| `monitor.html` 临床监察（mm5） | tab：入组与进度（漏斗、筛败率与原因、重复筛选、知情→首剂、累计入组）· 访视执行（按方案访视窗推算应完成、逾期未见记录、超窗）· 给药与知情（漏服/中断/剂量偏离/未空腹、知情晚于程序、再知情、样本超窗）· 退出与数据质量（原因、各中心质疑与数据质量信号）· 疑似录入错误。比率按观察/期望着色。listing 无录入/核查时间戳，录入及时性与 SDV 不做 | KZ.ops、pd、queries、cro、others |
| `safety.html` 安全性 | mm5 首个 tab「中心总览」：中心 × 风险类别热力图（检验/AE/方案偏离/质疑/数据质量 14 类），颜色＝观察数较按本中心给药人数推算的期望数的泊松 z（K.oe），点击下钻；左侧筛选/筛败/给药/进度。其余 tab：AE 汇总（分类/IB 标签/TEAE/SAE/AESI，不分组）· 检验风险（CSX/MH/NCS2…，可筛选）· 其他信号（阈值/AE 质量/禁用药/入排/超窗/PD）· 一致性 | KZ.aes/aesum/labrows/others/cons |
| `efficacy.html` 有效性 | 终点分布、访视轨迹、异常与缺失；盲态下不分组 | KZ.eff |
| `objective.html` 客观检查 | 指标趋势（均值±SD、个体线、参考线、轴断裂）、×ULN、中心漏斗图（±2SE/±3SE） | KZT |
| `queries.html` 质疑 | query 清单（按域/类别/中心/CRO 查重筛选），抽屉展示源行原文与 CRO 原文，可复制 | KZ.queries, KZX.ex |
| `methods.html` 审阅要点 | 不在主导航（mm4）：由总览底部折叠区进入；按数据页组织的审阅要点（含方案偏离 tab，实例取 KZX.pdex）、内置方法 M01–M17 | KZ.methods/review/unres |

通用：顶部导航（mm5：主导航 总览·安全性概况·AE/MH风险·方案偏离·临床监察·医学质疑·参与者资料，其余收进「更多」）＋全局受试者搜索；
**全程数据面板**（mm5 `K.seriesPanel`）：风险行、专项核查、医学质疑、潜在 PD、疑似录入错误的抽屉都显示该受试者该指标从首次到最后一次的全部记录（图＋表：结果、范围、较基线、等级、CS/NCS、CS 原因与关联、说明、来源；本条证据加粗）及本例 AE/病史/合并用药；hash 路由（如 `safety.html#tab=lab&risk=CSX`、`subjects.html#sid=01003`）；所有表格可排序；抽屉 `[data-q]`/`[data-r]`。
扩展页面：复制任一 `*.html` + `assets/p-*.js`，复用 `assets/kz.js` 中的 `K.*` 工具（渲染、格式化、`K.rng`、图表封装）。
