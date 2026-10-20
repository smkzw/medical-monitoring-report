---
name: subject-timeline-builder
description: 根据当前项目的研究方案、电子数据列表、禁用或限制用药解释、方案偏离或核查发现、分组表、不良事件、实验室检查、药代动力学和药效学数据，构建中文交互式受试者时间线和风险汇总工作簿。适用于受试者时间线、个例资料时间轴、禁用药漏报核查、入排违背风险、不良事件判定合理性核查、既往及合并用药或治疗、病史、访视、发现项和采样信息的受试者级重构。
metadata:
  slug: subject-timeline-builder
  displayName: 受试者时间线构建器
  version: 0.1.2
  summary: 基于临床试验方案和数据列表生成中文受试者时间线，并输出禁用用药、入排、判定合理性等风险汇总。
---

# Subject Timeline Builder

## Core Rule

Do not hardcode rules from a previous project. Derive study periods, visit names, medication/history definitions, prohibited/restricted medication rules, AE-risk categories, eligibility criteria, sheet mappings, and column mappings from the current uploaded protocol and listings. If a rule or field cannot be confidently derived, run precheck and ask the user to confirm before building.

Fully deconstruct every uploaded file before building. Do not skip protocol, listing, grouping, finding, prohibited-medication explanation, lab, AE, or PK/PD review because the task is long. If field matching is unclear or disputed, stop and tell the user exactly which data were not identified or were ambiguous; do not make an unconfirmed decision.

## Workflow

1. Inventory inputs.
   - Protocol: PDF/DOCX/TXT/HTML that defines study period, visits, medication rules, and history rules.
   - Data listing: EDC export workbook with subject, visit, AE, MH, CM, lab/PK or other sheets.
   - Finding listing: optional self-inspection/finding workbook or CSV.
   - Prohibited/restricted-medication explanation: optional workbook, table, appendix, or memo that interprets protocol rules.
   - Lab listing: required when eligibility or safety risk logic depends on numeric lab thresholds.
   - PK listing: optional workbook or sheet; may be inside data listing.
   - Subject grouping/randomization table: required when group labels, randomized-only output, or screen-failure labels are requested. If no uploaded file contains grouping/randomization/screening result information, ask the user to upload or identify it.

2. Ask required build-scope questions before mapping.
   - Ask whether to include all subjects or only randomized subjects.
   - Ask whether to include USV/计划外访视 data. If included, show USV only at subject level and place each USV by its actual USV date on the timeline.
   - If the user selects randomized-only and randomization/screen-failure fields cannot be found, stop and ask the user to identify the relevant file/sheet/columns.

3. Precheck workbook structure.
   - Run `scripts/inspect_workbook.py` on every workbook.
   - Identify candidate sheets and exact headers for visits, subject demographics, AE, MH, CM, non-drug therapy, labs, findings/deviations, randomization, and PK/PD.
   - For PK/PD, determine whether the file contains concrete concentration/result data or only visit-level collection flags. If the listing only records whether PK/PD was collected, do not map collection flags as concentration results and do not display LLOQ or quantitative interpretation by default.
   - Preserve row identifiers, subject IDs, item numbers, dates, source sheet names, and source row numbers in intermediate data so every displayed item can be traced back.
   - Keep a decision ledger for each derived risk or prompt: source locator, protocol/rule locator, raw term, normalized term, date window, calculation, status, and uncertainty. Do not let a display label replace the underlying evidence.
   - Record missing or ambiguous fields in a short precheck list.

4. Read and deconstruct the protocol.
   - Extract visit schedule and normalize visit order.
   - Extract concomitant medication and prior medication definitions.
   - Extract prior/concomitant non-drug therapy definitions when present.
   - Extract current/past medical history definitions.
   - Extract prohibited/restricted medications, prohibited/restricted therapies, allowed rescue/background therapies, washout requirements, and exemptions. Distinguish fixed washout periods from half-life-based washouts; when a rule says “whichever is longer”, calculate or flag using the longer applicable window.
   - Extract eligibility criteria that can be evaluated from listings, especially medical-history exclusions, prior-therapy exclusions, and lab-threshold exclusions.
   - Extract AE safety topics from the protocol, IB, approved label, and same-target or same-class safety information only when the source is supplied or explicitly requested.
   - Extract PK/PD sampling schedule if relevant.
   - Confirm whether PK/PD output should show actual results, collection status only, or be omitted when no concrete result listing is available.
   - Extract the study flow table and use it to define actual visit labels and order. Prefer compact timeline labels such as `V1D-7`, `V2D1`, `V3D8`, and `UNSD79`; do not put long phase prose in timeline tags unless the user requests it.
   - If no concomitant medication definition is found, ask whether to use: “non-study medications whose use range overlaps first study drug administration through treatment-period final visit”.
   - If no current medical history definition is found, ask whether to use: “conditions whose date range overlaps first study drug administration through the subject’s last study visit”.

5. Resolve definitions into explicit windows.
   - For this skill, “合并用药/治疗” often means non-study medication or therapy whose use interval overlaps the protocol-defined study window. If the protocol says “研究期间”, use first actual visit through last actual visit. If it says “研究药物治疗期间”, use first study drug administration/D1 through treatment end.
   - Split details into prior and concomitant sections when requested. A safe default is: prior medication/therapy ended before ICF; concomitant medication/therapy starts on/after ICF or starts before study drug and continues after study drug begins. Keep the timeline graph focused on concomitant items when prior items would crowd the graph, but retain prior details below the graph.
   - Use partial dates conservatively: `YYYY-MM-uk` starts at day 1 for interval starts and ends at month end for interval ends; `YYYY-uk-uk` starts Jan 1 and ends Dec 31.
   - Do not use fields such as “该治疗是否在本研究治疗期间使用？” as the sole classifier when protocol definitions are date-window based. Treat them as source context only.
   - Number AE, CM, therapy, MH, and finding details in the same stable order used in the timeline graph. Sort by source order within equal or partial dates unless the protocol or listing supplies explicit item numbers.
   - CM reason display: when the reason is “其他及既往病史/其他既往及现病史” or “不良事件”, extract the specific linked MH/AE from the corresponding listing columns. Also inspect “备注” columns as fallback. If the linked MH/AE cannot be extracted, stop for user confirmation.
   - AE display must include outcome/转归 when available.
   - Timeline bars for CM, AE, and MH must expose specific source details on hover. AE hover text should include event name, dates, severity, relationship/action, SAE status, outcome, and notes when available. MH hover text should include disease, dates, ongoing status, and notes. CM hover text should include drug name, dates, ongoing status, dose/unit, frequency, route, indication/reason, and notes.

6. Build risk logic from sources, not from project memory.
   - Prohibited/restricted medication risk: parse protocol rules and any explanation workbook with merged-cell forward-fill, category labels, examples, route/form constraints, washout windows, allowed exceptions, rescue-treatment exceptions, and PD/finding-report expectations.
   - Match prohibited medication by raw drug name, generic ingredient, class keywords, route/form, indication/reason, and date window. Avoid matching disease names, MH terms, or free-text reasons as a drug name unless the source rule explicitly defines that term as a prohibited treatment.
   - Keep rescue treatment as a risk item when the protocol restricts the drug or class, but do not classify it as a potential missed PD/finding if the supplied rules exempt rescue treatment from PD reporting. Display it as a risk with the rescue/exemption basis.
   - For prior medications and therapies, evaluate washout against ICF, screening, randomization, first study drug, or other anchor exactly as defined by the protocol. For half-life rules, calculate from supplied half-life evidence when available; otherwise flag the uncertainty instead of inventing a half-life.
   - PD/finding matching must be event-level: subject plus risk context/category plus drug/treatment or rule term plus exact date/range when dates are available. Never mark every same-subject or same-class event as registered just because one similar event appears in the finding listing.
   - Generate robust match keys from raw term, matched protocol/list keyword, normalized name, generic/core ingredient, and route/form-stripped variants. Normalize common salt prefixes, dosage-form suffixes, spaces, punctuation, and route prefixes so source wording differences still match, while preserving enough specificity to avoid class-wide false positives.
   - Eligibility/MH risk: flag only active or relevant history that violates an explicit inclusion/exclusion criterion. For lab-related history or lab exclusions, evaluate actual screening/randomization lab values and protocol thresholds; do not flag by disease or abnormality name alone when the protocol defines a numeric threshold.
   - Direct lab-threshold risks may exist even without matching MH. Include them when the user asks for eligibility or PD-risk review and the listing supports the threshold calculation.
   - AE assessment risk: special-mark AESI, SUSAR, SAR, SAE, and grade >=3 AE only when source fields support those labels. Potential “AE assessment improper” should generally require both an unrelated/possibly unrelated causality judgment and a match to supplied IB, label, protocol, same-target, or same-class safety topics. If a matched safety-topic AE is judged related, display the safety-topic cue but do not put it in the potential assessment-improper card solely for that reason.

7. Create a mapping JSON.
   - Use `references/config-schema.md`.
   - Include sheet names, column names, visit order, study-window rules, optional research drug name patterns, and optional display labels.
   - Include grouping/randomization mapping when available. Display group or status labels after subject IDs in cards and subject dropdowns, using the current study's own group/status wording.
   - If the user opts out of a module, omit its mapping and ensure the HTML does not show that module.

8. Build the HTML and risk workbook.
   - Run `scripts/build_timeline_html.py --listing <data.xlsx> --config <mapping.json> --output <timeline.html>`.
   - Add `--pk-listing`, `--finding-listing`, and `--group-listing` when those data are separate files and mappings are present.
   - Treat the bundled builder as the baseline configurable timeline generator. When the requested risk logic exceeds the generic script, extend the script or create a narrow project-local builder from the mapped source data; do not pretend unsupported risk modules are handled by the baseline script.
   - If source-derived risk logic is requested, also export an Excel or CSV risk summary with separate tabs or files for medication/therapy risk, eligibility/MH/lab risk, and AE assessment risk. Include subject, item number, source row, source term, matched rule, matched keyword, date window, PD/finding status, rationale, and evidence text.
   - The output must cover all requested centers and subjects. Use the top-right filters to locate center and subject.
   - Put subject-level risk cards above the timeline only for risk categories the user requested, and keep card entries one row per event/risk item. Use clear rounded tags for important statuses such as missing PD/finding, registered PD/finding, rescue exemption, unrelated causality, and major/important findings; do not show internal instruction phrases or reviewer-facing process notes.
   - Use visually distinct but restrained styles for higher-risk timeline bars and tags. Keep core layout, font scale, and line-height stable unless the user asks for a redesign.

9. Validate before delivery.
   - Confirm subject count, center count, AE/MH/CM/therapy/lab/finding/PK/PD row counts, and missing window count.
   - Spot-check at least one subject with pre-study medication, one with study-period medication, one with ongoing medication, one with AE, and one with PK if present.
   - Verify no encoded drug names are used when a raw medication name column is available.
   - Verify subject labels show group/screen-failure information when grouping is enabled.
   - Verify AE rows show outcome/转归.
   - Verify CM reasons show linked AE/MH details for AE/MH-related medication reasons.
   - Verify CM/AE/MH timeline bars show meaningful hover details rather than only generic IDs or names.
   - Verify PK/PD display matches the actual data type: actual result listing, collection status only, or omitted module. Do not show `LLOQ` or interpret collection flags as concentrations unless an LLOQ column/value and result column were explicitly mapped from a concrete result listing.
   - Verify USV dates appear at their actual date positions when USV is enabled.
   - Cross-check the risk workbook against raw listings: every risk row must trace to a raw row or explicit derived lab threshold; every PD/finding status must be justified by event-level matching, not subject-level matching.
   - Validate the risk evidence contract in `references/risk-evidence-contract.md`: risk, prompt, and registered Finding/PD are separate statuses; an item marked registered must retain the event-level match key and source locator.
   - Open or parse the HTML and ensure the filters, cards, Chinese labels, tooltips, and risk tags render.
   - Use browser automation or equivalent rendered-output checks for dense timelines. Check at least one desktop viewport and one narrow viewport when layout matters. Confirm visit labels do not overlap; for close dates, alternate labels above/below the axis and increase vertical label area dynamically.
   - Search final HTML and workbook text for stale instruction wording, placeholder labels, project-specific terms from prior work, and accidental internal notes.

## Precheck Questions

Ask concise questions only for blockers:

- Required file missing: “未提供 data listing，无法构建受试者级访视、AE、MH、CM。是否先仅基于 finding listing 构建问题索引？”
- Ambiguous definition: “方案中未明确合并用药是否按研究期间或治疗期间定义。是否按首次试验药物用药至治疗期末次访视重叠定义合并用药？”
- Ambiguous raw/coded medication names: “CM sheet 中存在多个药物名称列。是否使用靠前的原始录入药名列？”
- Optional module absent: “未识别 PK listing。是否不展示 PK 模块？”
- PK structure ambiguous: “当前 PK sheet 似乎仅记录各访视是否采集 PK，未见具体浓度/检测结果列。请确认是否仅展示 PK 采集状态，或另行上传具体 PK 结果 listing；若不展示 PK 模块，HTML 中将移除该模块。”
- Missing grouping: “未识别受试者分组/随机结果/筛选结果信息。请上传受试者分组表或指出对应 sheet 和列。”
- Population scope: “请确认 HTML 纳入所有受试者，还是仅纳入已随机受试者？”
- USV scope: “请确认是否纳入计划外访视（USV）数据；若纳入，将按 USV 实际日期显示在个例时间线中。”

If the user chooses not to show a module, remove that module from the config and from the HTML output.

## Resources

- `scripts/inspect_workbook.py`: print workbook sheets, headers, duplicate headers, and sample rows for mapping.
- `scripts/build_timeline_html.py`: generic configurable baseline HTML builder; extend or wrap it when a study-specific risk workbook or advanced risk overlay is required.
- `references/config-schema.md`: required mapping JSON fields and examples.
- `references/protocol-extraction.md`: protocol facts to extract and fallback rules.
- `references/risk-evidence-contract.md`: provenance, event-level matching, uncertainty, and downstream risk handoff requirements.
