# Mapping Config Schema

Create one JSON file per build. Keep it explicit; do not rely on fuzzy matching during final build.

## Minimal Shape

```json
{
  "title": "研究名称 受试者时间线",
  "language": "zh-CN",
  "study_window": {
    "type": "first_visit_to_last_visit"
  },
  "history_window": {
    "type": "first_dose_to_last_visit",
    "start_visit_match": "基线"
  },
  "modules": {
    "ae": true,
    "mh": true,
    "cm": true,
    "therapy": true,
    "labs": false,
    "findings": true,
    "pk": true,
    "pd": false,
    "risk_workbook": false
  },
  "population": "all",
  "include_usv": false,
  "sheets": {
    "visits": {
      "name": "SV--访视日期",
      "center": "研究中心",
      "subject": "受试者",
      "visit": "访视名称",
      "date": "访视日期",
      "occurred": "访视是否发生？"
    },
    "usv": {
      "name": "USV",
      "center": "试验中心名称",
      "subject": "受试者编号",
      "date": "检查日期(USVDAT)",
      "label": "USV"
    },
    "group": {
      "name": "Sheet1",
      "subject": "受试者编号",
      "group": "治疗组",
      "status": "受试者状态",
      "random_no": "随机号"
    },
    "cm": {
      "name": "CM--既往及合并用药治疗",
      "center": "研究中心",
      "subject": "受试者",
      "drug_name": "药物名称",
      "reason": "治疗原因",
      "reason_mh": "治疗原因为病史，请选择（可多选）",
      "reason_ae": "治疗原因为不良事件，请选择（可多选）",
      "reason_detail_columns": ["其他既往及现病史(CMMHNO)", "不良事件(CMAENO)", "备注(CMCO)"],
      "note": "备注(CMCO)",
      "dose": "单次剂量",
      "unit": "单位",
      "frequency": "给药频率",
      "route": "给药途径",
      "start": "开始日期",
      "ongoing": "是否持续",
      "end": "结束日期"
    }
  },
  "visit_order": [
    {"match": "筛选", "label": "筛选", "order": 0},
    {"match": "基线", "label": "基线", "order": 1},
    {"match": "2W", "label": "2W", "order": 2}
  ],
  "research_drug_name_patterns": ["研究药物", "试验药物"]
}
```

## Study Window Types

- `first_visit_to_last_visit`: first actual visit date through last actual visit date. Use when the protocol defines concomitant medication as “研究期间”.
- `first_dose_to_treatment_end`: first study drug/D1 through treatment end. Use when the protocol defines concomitant medication as “研究药物治疗期间”.
- `first_dose_to_last_visit`: first study drug/D1 through the subject’s final actual study visit. Often used for current medical history fallback.
- `custom_columns`: use explicit columns configured in `study_window.start_sheet/start_column/end_sheet/end_column`.

For `first_dose_*`, set `start_visit_match` when D1/baseline labels vary. For `first_dose_to_treatment_end`, set `end_visit_match` when the treatment-end label is known; otherwise the builder falls back to 24W-like labels and then the last visit.

## Optional Sheets

Add only if the module is enabled.

## Population and USV

- `population: "all"`: include every subject found in the mapped listings.
- `population: "randomized"`: include only subjects identified as randomized from `sheets.group` via treatment group or random number. If grouping/randomization cannot be mapped, stop and ask the user.
- `include_usv: true`: include unscheduled visits at subject level and place them by actual USV date. Configure `sheets.usv`.
- `include_usv: false`: exclude USV from the timeline.

Subject dropdown labels use `subject | group/status` when `sheets.group` is configured. If group status indicates screening failure, display `筛败`.

### AE

```json
"ae": {
  "name": "AE--不良事件",
  "center": "研究中心",
  "subject": "受试者",
  "term": "不良事件名称",
  "start": "最早开始日期",
  "grade": "最严重程度（CTCAE V5.0）",
  "relationship": "与研究用药的关系",
  "action": "对研究用药采取的措施",
  "outcome": "转归",
  "ongoing": "是否持续？",
  "end": "结束日期",
  "sae": "是否为严重不良事件（SAE）？"
}
```

### MH

```json
"mh": {
  "name": "MH--既往及现病史",
  "center": "研究中心",
  "subject": "受试者",
  "term": "疾病名称",
  "start": "开始日期",
  "ongoing": "是否持续",
  "end": "结束日期"
}
```

### Therapy

Use this when the listing separates non-drug therapy from medications. If the study displays medication and non-drug therapy together on the graph, keep their source modules distinct in details and risk workbooks.

```json
"therapy": {
  "name": "PR--既往及合并非药物治疗",
  "center": "研究中心",
  "subject": "受试者",
  "term": "治疗名称",
  "reason": "治疗原因",
  "reason_mh": "治疗原因为病史，请选择（可多选）",
  "reason_ae": "治疗原因为不良事件，请选择（可多选）",
  "start": "开始日期",
  "ongoing": "是否持续",
  "end": "结束日期",
  "note": "备注"
}
```

### Labs

Map labs when eligibility or safety-risk logic depends on numeric thresholds.

```json
"labs": {
  "name": "LB--实验室检查",
  "center": "研究中心",
  "subject": "受试者",
  "visit": "访视名称",
  "date": "采样日期",
  "test": "检查项目",
  "result": "结果",
  "unit": "单位",
  "lln": "正常下限",
  "uln": "正常上限",
  "flag": "异常标识"
}
```

### PK/PD

```json
"pk": {
  "name": "Sheet1",
  "subject": "辅助列：受试者筛选号",
  "visit": "访视名称",
  "result": "检测结果（ng/mL）",
  "lloq": "LLOQ  ",
  "date": "采样日期",
  "time": "采样时间",
  "note": "样本说明"
}
```

If the same workbook contains PD, add a sibling `pd` mapping with the same shape and source-specific labels. If the PK/PD sheet only records whether samples were collected at visits, map the collection flag as collection status only or omit the module; do not label that field as a concentration or biomarker result. Do not configure `lloq` unless the listing has a real LLOQ column/value tied to concrete result data.

When a PK/PD page appears to show `是/否` collection status for all subjects/visits rather than numeric results, stop during precheck and ask whether to display collection status only, request a separate result listing, or omit the module.

### Findings or PD/Deviation Listings

```json
"findings": {
  "name": "Sheet1",
  "center": "中心",
  "subject": "受试者编号",
  "category": "问题分类",
  "visit": "涉及访视",
  "severity": "问题严重程度",
  "description": "原始问题描述",
  "response": "建议现场核查回复口径"
}
```

For risk registration matching, findings/PD mappings should preserve columns for source row number, category, severity/importance, description, visit/date, response, and any explicit medication/event terms when available.

### Optional Risk Workbook Output

When the user requests prohibited-medication, eligibility, or AE-assessment risk review, create explicit derived risk rows. A recommended internal/output shape is:

```json
"risk_output": {
  "enabled": true,
  "tabs": {
    "medication_therapy": true,
    "eligibility": true,
    "ae_assessment": true
  },
  "columns": [
    "subject",
    "item_no",
    "risk_type",
    "source_module",
    "source_sheet",
    "source_row",
    "source_term",
    "start",
    "end",
    "matched_rule",
    "matched_keyword",
    "pd_finding_status",
    "rationale",
    "evidence"
  ]
}
```

Status fields must be event-level. For example, a finding/PD row for the same subject and same broad class is not enough; match context, term or normalized core term, and date/range when available.

## Header Rule

If a sheet has duplicate headers, the scripts suffix later duplicates as `__2`, `__3`. For CM medication names, choose the raw/original medication name column, usually the earlier duplicate, unless the user explicitly requests coded names.
