---
name: clinical-patient-profile-html
description: 当用户要求基于临床试验 listing、研究方案、受试者分组表、Finding 台账等文件制作 patient profile、受试者画像、个例 Profile 或中心层汇总 HTML 时使用；适用于疗效、实验室、生命体征、AE 和 Finding 的受试者级或中心级历时核查展示。
metadata:
  slug: clinical-patient-profile-html
  displayName: 临床 Patient Profile HTML
  version: 1.0.2
---

# Clinical Patient Profile HTML

Use this skill for clinical-study patient profile HTML work where the output must stay source-grounded and inspection-ready.

This skill is best when the user provides subject listings, protocol/amendment files, and optionally finding trackers, and wants an offline HTML that combines subject profile, efficacy trends, lab trends, vital signs, and optional finding review.

If the user explicitly says `制作patient profile` or an equivalent phrase after uploading files, invoke this skill immediately and start with file inspection rather than waiting for extra instructions.
Do not require an additional “开始构建” instruction.

## Workflow

1. Run the bundled precheck as soon as the uploaded files are available:

```bash
python3 scripts/build_patient_profile_html.py \
  --work-dir "<project-folder>" \
  --output-dir "<project-folder>/patient_profile_output" \
  --precheck-only
```

2. Read `input_precheck.md`.
Also inspect:

- `suggested_project_config.json`
- `protocol_endpoint_summary.md`

3. Before any full build, explicitly settle these two scope questions if they are not already stated by the user:

- 纳入全部受试者，还是仅纳入已随机受试者。
- 是否纳入 USV/计划外访视数据。

Also settle these when precheck cannot resolve them from the uploaded files:

- 是否纳入全部中心，还是仅纳入指定中心。
- 实验室 / 心电图 / 生命体征在中心层是否应将 SCR / D1 合并为“基线”。

4. If precheck shows only `提示`, continue directly to full build.

5. If precheck shows `阻断` or `需确认`, ask only the smallest necessary question and stop.
Do not guess missing centers, finding sheet mappings, subject ID columns, or substitute sheet names.
If the user confirms that some metrics, sheets, or fields do not need to be included, treat that as authorization to proceed without them.

6. If precheck shows `需确认` but the user has already made a scope decision such as “该字段不纳入” or “该数据不体现”, update the config accordingly and continue directly.

7. Once inputs are sufficient or the user has accepted the reduced scope, run the full build immediately. Prefer using the generated config file so the build uses the same detected mappings:

```bash
python3 scripts/build_patient_profile_html.py \
  --work-dir "<project-folder>" \
  --config-json "<project-folder>/patient_profile_output/suggested_project_config.json" \
  --output-dir "<project-folder>/patient_profile_output"
```

8. Validate the result against the source tables before presenting it.
Use `references/validation_checklist.md`.
Create or retain the source-to-output mapping and subject completeness artifacts as a downstream handoff. A profile display is context for later medical review, not a substitute for the source listing.

## Required Inputs

- A main listing workbook with subject-level tabs for demographics, randomization, visits, efficacy, labs, AE, and vital signs.
- A protocol, amendment, or errata file that contains endpoint definitions and the study flow/assessment schedule.
- A finding workbook or self-inspection/audit tracker when the user wants finding linkage or fixed finding display.

## Optional Inputs

- A subject report workbook for cross-checking sex, age group, and treatment assignment.
- Reference HTML files if the project already has an approved patient-profile style to follow.

## When To Ask The User

Ask the user instead of proceeding when any of these happen:

- More than one center is detected and the target center scope is not explicitly stated.
- The user has not yet chosen `全部受试者` or `仅纳入已随机受试者`.
- The user has not yet chosen whether to include `USV/计划外访视` data.
- The protocol is missing or unreadable.
- The protocol does not yield a clear endpoint-to-metric mapping.
- The protocol does not make it clear whether an efficacy variable is continuous or binary.
- The protocol does not make it clear whether lab / ECG / vital-sign screening results can be used as center-level baseline.
- The finding workbook exists but the relevant sheet or subject column cannot be confirmed.
- Key efficacy sheets are missing or likely renamed.
- A protocol-required assessment category appears in the study flow table but no corresponding listing sheet or field can be found.
- Lab reference ranges are absent and the user must decide whether to keep those rows with blank normal-range display.
- A sheet appears to contain needed data but the field mapping is ambiguous.
- A critical profile field such as screening date, consent date, or baseline/randomization date cannot be located reliably.

Do not ask the user to “confirm starting the build” when uploaded files and scope are already sufficient.

Use the prompt patterns in `references/mapping_and_decisions.md`.

## Adaptation Rules

This skill ships with a working builder that reproduces the current patient-profile style closely, but efficacy identification must be protocol-driven rather than copied from a prior project.
Metric aliases and candidate efficacy names must also be derived from the current protocol wording, especially the primary/secondary endpoint text and the study flow table, rather than from a hardcoded disease-specific alias catalog.
Responder or response labels must also be protocol-driven: only emit them when the current protocol explicitly defines a rule and the available data can calculate it. Otherwise leave the response field blank.

Prefer updating `suggested_project_config.json` before editing Python.

The skill must fully deconstruct every uploaded file that could affect mapping or scope.
Do not skip sheet-level inspection because a prior project looked similar.
Do not silently fall back to a previous project’s endpoint set, phase labels, subject-ID format, or visit model.
Do not continue to HTML generation if critical mapping remains ambiguous; stop and ask the user for a concrete file/sheet/field example.
If the study flow table says a category should be collected but the listing yields no usable rows, stop and ask instead of silently omitting it.

## Generalization Boundary

Keep this skill project-agnostic. Do not add disease-specific, compound-specific, endpoint-specific, or single-project modules to the default builder or documentation.

Examples of project-specific content that must not be hardcoded:

- disease-specific symptom scores, questionnaires, or endpoint names unless detected from the current protocol and listing
- project-specific SAP analyses, daily diary windows, or responder rules not explicitly defined in the current protocol
- biomarker, PK, PD, immunogenicity, exposure, environmental, or device modules unless the user supplies them and the current protocol/config explicitly requests them
- project-specific sheet names, visit windows, center names, trial names, product names, colors, or report titles

When a project needs an extra module, implement it as a project-local extension or config-driven optional block. Do not promote it into the reusable skill unless it applies broadly across clinical projects.

Retain broadly reusable lessons from prior builds:

- sort subjects numerically in every selector or sidebar list
- sort subject-level longitudinal rows by actual assessment date, including unplanned visits
- exclude unplanned visits from overall/center aggregates unless the user explicitly asks otherwise
- keep subject-level unplanned visits when the user chooses to include USV data
- collapse one-sided or qualitative normal ranges into a single display value instead of forcing separate lower/upper columns
- verify the rendered HTML, not only the CSV outputs; UI clipping can look like missing data
- retain a downstream handoff containing population scope, source workbook/sheet/row, field mapping, actual assessment date, raw value/unit/reference range, derived label, and missingness or uncertainty status
- require downstream risk modules to re-confirm population and use the source listing as the final truth; do not infer a risk from a chart or a truncated selector alone

Adjust the script only in these places when the new project differs beyond config:

- protocol parsing and endpoint extraction logic
- `EFFICACY_CONFIG` for candidate efficacy sheet names and value columns
- `LAB_CONFIG` for lab workbook tabs
- `CORE_SHEET_CATALOG` for nonstandard main listing tabs
- `FINDING_SHEET_SPECS` or finding-sheet auto-detection behavior
- group and center normalization helpers

Do not fabricate subject dates, ranges, response flags, or normal limits.
If there is no finding workbook, continue without the finding module and without subject-level “关联Finding” descriptions.

## Outputs

The builder writes at least these files to the chosen output directory:

- `patient_profile.html`
- `cleaned_subject_profile_dataset.csv`
- `efficacy_longitudinal_dataset.csv`
- `lab_longitudinal_dataset.csv`
- `vital_signs_longitudinal_dataset.csv`
- `finding_subject_level_dataset.csv`
- `data_source_field_mapping.csv`
- `data_qc_summary.csv`
- `data_issue_log.csv`
- `subject_data_completeness.csv`
- `unresolved_data_questions.md`
- `input_precheck.md`
- `input_precheck.json`
- `protocol_endpoint_summary.md`
- `protocol_endpoint_summary.json`

The output HTML must stay Chinese-first in title, labels, filters, tables, and review text, using a professional internal-review style rather than project-specific wording.

## References

- For missing-field questions and exclusion decisions, read `references/mapping_and_decisions.md`.
- For final source-consistency checks, read `references/validation_checklist.md`.
- For a copy-paste quick start, read `references/quickstart_template.md`.
- For handing profile data to a medical risk or checklist workflow, read `references/downstream-risk-handoff.md`.
