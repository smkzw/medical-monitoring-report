# 报告页面（templates/site）

| 页面 | 职责 | 主要数据 |
|---|---|---|
| `index.html` 总览 | KPI（中心值 + 淡显总体）、风险分布、按域信号块（仅显示 n>0 的项）、待办、中心概况 | KZ.meta/subs/labrows/others/queries/todo |
| `study.html` 研究要点 | 设计流程、SoA 完成度热图、基线与口径裁定（consensus）、阈值卡、IB 注释、禁用药、入排、规则溯源（按 ruleGroups 分组，带原文出处） | KZ.study/rules/cons，KZX.soa |
| `subjects.html` 受试者 Profile | 左侧受试者列表（数字排序、状态/风险筛选）；个例：基本信息、访视、AE/MH/CM/给药、检验矩阵（异常着色、CTCAE 等级、临床意义）、CRO 质疑 | data/s/<sid>.js |
| `timeline.html` 受试者时间线 | 研究日轴（ICF−preDays 起），给药/AE/CM/MH/PR 条带，访视点，**风险事件独立行**，关键日；悬浮提示含源 sheet/行 | data/s/<sid>.js (tl) |
| `safety.html` 安全性 | tab：AE 汇总（分类/IB 标签/TEAE/SAE/AESI，不分组）· 检验风险（CSX/MH/NCS2…，可筛选）· 其他信号（阈值/AE 质量/禁用药/入排/超窗/PD）· 一致性 | KZ.aes/aesum/labrows/others/cons |
| `efficacy.html` 有效性 | 终点分布、访视轨迹、异常与缺失；盲态下不分组 | KZ.eff |
| `objective.html` 客观检查 | 指标趋势（均值±SD、个体线、参考线、轴断裂）、×ULN、中心漏斗图（±2SE/±3SE） | KZT |
| `queries.html` 质疑 | query 清单（按域/类别/中心/CRO 查重筛选），抽屉展示源行原文与 CRO 原文，可复制 | KZ.queries, KZX.ex |
| `methods.html` 方法学 | 审阅流程、内置方法 M01–M12、规则来源、IB 分类、局限与未决 | KZ.methods/review/unres |

通用：顶部导航 + 全局受试者搜索；hash 路由（如 `safety.html#tab=lab&risk=CSX`、`subjects.html#sid=01003`）；所有表格可排序；抽屉 `[data-q]`/`[data-r]`。
扩展页面：复制任一 `*.html` + `assets/p-*.js`，复用 `assets/kz.js` 中的 `K.*` 工具（渲染、格式化、`K.rng`、图表封装）。
