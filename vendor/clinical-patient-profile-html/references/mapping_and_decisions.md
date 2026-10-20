# Mapping And Decision Rules

Use this file when precheck shows `阻断` or `需确认`.

## Non-negotiable rules

- Use subject-level listings and finding trackers as the primary source.
- Use protocol/amendment files to identify efficacy endpoints first, including primary endpoints, secondary endpoints, and study-flow assessment timing.
- If a field cannot be mapped confidently, mark it as unresolved and ask the user.
- If a sheet should be excluded, get explicit user confirmation.
- Keep the generated `suggested_project_config.json` as the first place to revise mappings. Do not edit Python unless the project structure falls outside the config model.

## Questions to ask the user

Use short, concrete questions.

### Center scope

`识别到多个中心。请确认是纳入全部中心，还是仅纳入以下中心：<center list>？`

### Subject scope

`请确认本轮是纳入全部受试者，还是仅纳入已随机受试者。若纳入全部受试者，中心层面的筛选期数据可能与CSR统计不完全一致。`

### USV scope

`请确认是否纳入USV/计划外访视数据。若纳入，仅在个例层面展示，并按USV实际日期放入历时图表。`

### Baseline rule

`方案提示筛选期近D1的数据可能作为基线，但当前无法自动确认中心层是否应将 SCR/D1 合并为“基线”。请确认 <实验室/心电图/生命体征> 的中心层展示口径，以及个例层基线比较应采用哪个访视值。`

### Main listing workbook

`当前目录识别到多个可能的主listing文件。请确认以哪一个作为主数据源：<file list>？`

### Finding sheet mapping

`Finding工作簿已识别到 <sheet name>，但无法确认受试者字段/中心归属。请确认该sheet对应中心，以及应使用哪一列作为受试者编号。`

### Missing efficacy sheet

`未识别到 <metric> 的明确sheet。请确认该项目没有该指标，还是sheet名称不同；如名称不同，请提供正确sheet名。`

### Endpoint variable type

`方案中提到了 <metric>，但当前无法判断它应按连续型还是二分类展示。请确认该指标的展示口径。`

### Critical profile field missing

`<field name> 无法稳定定位。请指出它位于哪个listing、哪个sheet、使用哪一列识别；如有多个候选记录，请说明应采用哪一条。`

### Protocol-required assessment missing

`研究流程表提示需要收集 <assessment>，但当前listing中未识别到对应数据。请指出该数据位于哪个sheet，或明确本轮不纳入。`

### Early-exit visit

`方案和listing均识别到提前退出访视。请确认是否按默认规则处理：中心层图中不绘制该访视、表格最后一行保留；个例层按最后一个访视点展示。`

### Optional exclusion

`以下sheet存在但字段不足以稳定映射：<sheet list>。请确认是补充字段说明后纳入，还是本轮先排除。`

## Configuration blocks to review first

If the project structure differs, inspect these blocks before changing rendering logic:

- `EFFICACY_CONFIG`
- `LAB_CONFIG`
- `FINDING_SHEET_SPECS`
- `FIELD_ALIASES`
- `normalize_study_group`
- `standardize_center_name`

## Typical exclusion decisions

These can be excluded only after user confirmation:

- empty duplicate exports
- site-level admin sheets unrelated to subject data
- malformed finding tabs without subject linkage
- efficacy/pro tables that only duplicate already preferred total-score tabs
