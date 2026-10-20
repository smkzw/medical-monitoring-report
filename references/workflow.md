# 工作流细节

> 所有命令从技能根目录执行。`S` 为研究简称（如 `DEMO`）。原始文件不修改，只读。

## 阶段 0 · 文件盘点

1. 列出用户上传的全部文件（类型、大小、页数/sheet 数）。
2. listing：`python3 scripts/inspect_listing.py edc=<EDC.xlsx> [pd=<PD.xlsx>] [lab=<中心实验室.xlsx>] [eff=<量表.xlsx>] --out work/S`
   - `inventory.md`：每个 sheet 的表头行（标签行/变量名行/数据起始行）、识别出的域、列猜测、行数、长/宽表判断。
   - `mapping.draft.json`：映射草稿，`_guess: true` 表示需人工确认。
   - `precheck.md`：`阻断`（无法构建）/`需确认`（影响口径）/`提示`（缺失模块）。
3. 方案/IB：`pdftotext -layout protocol.pdf work/S/protocol.txt`；DOCX 用 `markitdown protocol.docx > work/S/protocol.md`。
   扫描目录、SoA 表（必要时 `pdfplumber` 抽表或截图查看）、脚注。
4. 对未被识别的 sheet 逐一打开前 5 行人工判断，**不得忽略**。

## 阶段 1 · 方案/IB 抽取

按 `protocol-ib-extraction.md` 清单输出 `work/S/rules.json`，同时起草 `work/S/study.json`：
- `cfg`：study 标题/编号/分期标签、visits.order（SoA 顺序）、grading（必填）、baselineRules、blind、ctcaeMap（可选覆盖）、refLines、metricRules、keyDays…
- `study`：design（流程图、分组、基线）、soaNote、consensus（口径冲突裁定）、thresholds、ib、prohibited、eligibility、ruleGroups。
- `analysis`：thresholdRules、aesiTermRe、aeCatMap、aeMatch、prohibited、washout、eligibility/eligibilitySubject、visitWindows、efficacy、effRules。
- `ibtag`：AE 分类 → `["IB常见"]`/`["IB潜在"]` 标签。

## 阶段 2 · 映射

以草稿为底，逐 sheet 填写 `mapping.json`（`mapping-schema.md`）。要点：
- 列引用优先变量名（第 2 行），没有时用中文标签；同名列取第一个 → 必要时改用另一种引用。
- 同一域多个 sheet（血常规/生化/尿常规分 sheet）写成多个 spec，并给 `group`。
- 宽表（VS/EG 每列一个指标）必须写 `tests`：`{"收缩压": {"value": "SYSBP", "unit": "mmHg", "clin": "SYSCS", "lo": 90, "hi": 139}}`。
- `visit_map` 覆盖 listing 中出现的全部访视文本（可用 `re:` 正则）；`clin_map` 覆盖全部临床意义取值。
- 运行 `normalize_listing.py` 后检查 stdout 的每域行数与 `work/S/norm/_source.json`，行数为 0 的域要追查。

## 阶段 3 · 提问模板（一次问完，只问阻断项）

```
已完成文件盘点与方案抽取，构建前需确认以下 N 点：
1. 分析人群：全部受试者 / 已随机 / 已给药（建议：已给药，筛选失败仅列表展示）？
2. 计划外访视（USV）：是否纳入汇总？（建议：不纳入汇总，仅个例展示）
3. 基线：方案 §x 规定「……」，拟按 <实验室 …／生命体征 …／ECG …（如三次均值）> 执行，缺失时用首剂前最近有效值——是否同意？（方案未规定时给出建议口径）
   分级：方案 §x 规定按 <CTCAE vX.X／自定义分级>（方案未写 → 阻断项，必须确认）；AESI：方案 §x 列出 <…>；AE 收集期/TEAE：<…>。
4. 分级表无条目的指标（如 尿酸、体重）的异常阈值：建议 较基线变化 ≥20% 作补充筛查，是否同意？
5. 盲态：方案为双盲，报告不展示分组与分组对比——是否同意？
6. 多中心：共识别 K 个中心，是否全部纳入？
7. 未识别：<文件/sheet/字段>，请指出对应位置或确认不展示该模块。
```
用户未回复的可选项按“建议”执行，并在交付说明与 `methods` 页注明。

## 阶段 4 · 构建

```
python3 scripts/normalize_listing.py work/S/mapping.json --out work/S/norm
python3 scripts/build_site.py --study work/S/study.json --norm work/S/norm --out out/S
```
- stdout 摘要：受试者数 · 人群 · AE · 检验风险行 · 其他信号 · query 数 · 指标数。数量异常（0 或远超预期）先排查映射。
- `--no-xlsx` 跳过 query 工作簿；工作簿默认标注证据行最多的 workbook（`export_queries.py --wb` 可指定）。

## 阶段 5 · 医学审阅

- 逐条看 `analysis/labrows.json`（CSX/MH/NCS2 优先）、`others.json`（阈值/AE 质量/禁用药/入排/超窗/PD）、`queries.json`、`cons.json`（同中心判定一致性）。
- 误报：调整 `analysis` 规则（如 aeMatch 窗口、aeCatMap、阈值）而不是删数据；确属无需质疑的可设 `R.query=false` 或调高 `queryMinPr`。
- 需要医学判断的补充 query 写 `queries_manual`：
  `{"sid":"01003","cat":"AE记录质量","sh":"AE","row":12,"v":"W4","d":"2026-03-02","test":"","fact":"…事实…","ask":"…请求…"}`
- `review`（审阅流程）、`todo`（待办）、`unres`（未决问题）可手写覆盖默认生成内容。

## 阶段 6 · 验证 → 阶段 7 · 交付

见 `validation-checklist.md`。交付压缩包：`HTML/`、`<listing>_申办方MM_query_首列版.xlsx`、`analysis/`（可选 `shots/`）。
交付说明模板：
```
已完成 <S> 医学监察报告：<n> 例受试者（分析人群 <m>），检验风险 <a> 行、其他信号 <b> 条，申办方 query <q> 条（LB x / AE y …），
其中 <k> 条与 CRO 已发质疑同主题已标注。口径：<人群/基线/USV/盲态>。未决：<…>。
```
