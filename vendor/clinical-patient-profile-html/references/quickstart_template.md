# Quickstart Template

给其他同事直接复制用，先做预检查，再正式构建。
注意：疗效指标的识别应先依据研究方案中的主次要终点和研究流程，不应默认沿用既往项目中的 EASI、IGA 等固定设置。

## 1. 预检查

把下面命令里的 `<项目文件夹>` 替换成当前项目资料所在目录：

```bash
python3 ~/.codex/skills/clinical-patient-profile-html/scripts/build_patient_profile_html.py \
  --work-dir "<项目文件夹>" \
  --subject-scope randomized \
  --include-usv no \
  --output-dir "<项目文件夹>/patient_profile_output" \
  --precheck-only
```

看输出目录里的：

- `input_precheck.md`
- `suggested_project_config.json`
- `protocol_endpoint_summary.md`

如果里面有 `阻断` 或 `需确认`，先补文件、确认字段映射，或明确哪些内容本轮不纳入。

## 2. 正式构建

确认完预检查结果后，运行：

```bash
python3 ~/.codex/skills/clinical-patient-profile-html/scripts/build_patient_profile_html.py \
  --work-dir "<项目文件夹>" \
  --config-json "<项目文件夹>/patient_profile_output/suggested_project_config.json" \
  --subject-scope randomized \
  --include-usv no \
  --output-dir "<项目文件夹>/patient_profile_output"
```

主要输出文件：

- `patient_profile.html`
- `cleaned_subject_profile_dataset.csv`
- `efficacy_longitudinal_dataset.csv`
- `lab_longitudinal_dataset.csv`
- `vital_signs_longitudinal_dataset.csv`
- `finding_subject_level_dataset.csv`
- `protocol_endpoint_summary.md`

## 常见情况

- 缺少研究方案：当前 Skill 不应直接套用旧项目疗效口径，需先补研究方案，或人工明确本轮纳入哪些疗效指标。
- 自动识别到多个中心：先明确本轮纳入哪些中心，再继续构建。
- 方案里写了筛选期结果可作为基线，但程序没有自动判清：先确认实验室 / 心电图 / 生命体征在中心层是否将 SCR / D1 合并展示为“基线”。
- 方案里提到了终点，但 listing 里找不到对应 sheet：先确认该指标是否未导出，或决定本轮不纳入。
- 方案中无法判断某疗效指标是连续型还是二分类：先由项目团队确认展示口径。
- 某个指标的结果列或日期列没识别准：优先修改 `suggested_project_config.json`，不要先改 Python。
- Finding sheet 找不到受试者字段：先让项目组确认该列，或决定该 sheet 暂不纳入。
- 本轮没有 Finding 文件：可以继续构建，但不会生成 Finding 固定展示模块，也不会做个例层 Finding 关联标注。
