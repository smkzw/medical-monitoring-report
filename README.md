# medical-monitoring-report · 医学监察报告技能

把 **研究方案 + EDC 数据 listing**（可选：分组表、PD listing、CRO 已发质疑、量表/中心实验室/中心阅片、PK/PD/ADA、IB）
自动转成 **9 页交互式医学监察 HTML 报告** 和 **可直接粘贴 EDC 的申办方 MM query 工作簿**，采用康哲设计体系。

融合并取代：`clinical-patient-profile-html`（受试者 Profile）· `ae-risk-assessment`（AE 漏报风险）· `subject-timeline-builder`（受试者时间线）。

## 能力
- **文件盘点**：自动识别 sheet → 域、双表头、长/宽表、列映射草稿、访视与临床意义取值映射、预检（阻断/需确认/提示）。
- **方案/IB 抽取**：规则带原文出处（`rules.json`），口径冲突显式裁定，可执行部分进入分析配置。
- **深度分析**：按方案分级标准自动分级（内置 CTCAE v5.0 / v6.0，可自定义；自动指标映射与单位换算）· 方案基线定义引擎 · AE 漏报风险分层（CS 未关联 / 仅关联病史 / NCS 但 ≥2 级）· AE/MH 关联合理性 · 方案阈值/AESI（术语/PT/SOC/组合规则如 Hy’s law）· TEAE/AE 收集期 · 报告时限 ·
  AE 记录质量 · 禁限用药与洗脱期 · 入排 · 访视窗与 SoA 完成度 · 同中心判定一致性 · 中心漏斗图 · 有效性合理性 · PD 逐事件比对 · CRO 质疑查重。
- **报告**：总览 / 研究要点 / 受试者 Profile / 受试者时间线 / 安全性 / 有效性 / 客观检查 / 质疑 / 方法学；离线可用；盲态守卫。
- **验证**：无头渲染全部页面与 tab、数据契约与源行回查。

## 快速开始（演示数据，全部虚构）
```bash
pip install openpyxl            # 其余依赖为标准库；渲染检查需 Node + playwright + chromium
python3 scripts/make_demo.py --out examples/demo
python3 scripts/normalize_listing.py examples/demo/mapping.json --out work/demo/norm
python3 scripts/build_site.py --study examples/demo/study.json --norm work/demo/norm --out out/demo
node scripts/render_check.js out/demo/HTML --shots out/demo/shots
python3 scripts/validate_contract.py out/demo/HTML --source-check
open out/demo/HTML/index.html
```
`build_site.py` 需要 ECharts ≥6：`--echarts <path>` / `$ECHARTS_JS` / `~/.cache/mm-report/echarts.min.js`，否则自动从 jsDelivr/unpkg 下载。

## 真实项目
```bash
python3 scripts/inspect_listing.py edc=EDC.xlsx pd=PD.xlsx --out work/S      # → inventory.md / mapping.draft.json / precheck.md
# 由 Agent 阅读方案/IB → work/S/rules.json + work/S/study.json；确认映射 → work/S/mapping.json；问清阻断项
python3 scripts/normalize_listing.py work/S/mapping.json --out work/S/norm
python3 scripts/build_site.py --study work/S/study.json --norm work/S/norm --out out/S
```
完整流程见 [SKILL.md](SKILL.md)，配置说明见 [references/](references/)。

## 目录
```
SKILL.md                 技能入口（工作流 + 核心原则）
agents/openai.yaml       Agent 界面配置
scripts/                 inspect_listing · normalize_listing · mm_build · build_site · export_queries · ctcae（+ grading/*.json）· ctcae_import · validate_contract · render_check.js · make_demo
templates/site/          9 页 HTML 模板 + assets（kz.css / kz.js / ctcae.js / p-*.js）
references/              工作流、抽取、映射、配置、分析规则、query、数据契约、页面、设计、检查清单、经验
examples/demo/           mapping.json / study.json / rules.json（xlsx 由 make_demo.py 生成）
vendor/                  三个上游技能原文归档
```

## 说明
- 演示数据为程序生成的虚构数据，不含任何真实受试者信息。
- 方案/IB 规则抽取由 Agent 按 `references/protocol-ib-extraction.md` 完成，脚本不内置任何特定项目规则。
