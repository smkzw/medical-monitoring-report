# Protocol Extraction Checklist

Extract these facts from the current protocol before building.

## Visit Model

- Screening, baseline/D1, treatment visits, open-label visits, EOT, safety follow-up, unscheduled visits.
- Visit labels and order for display.
- Extract labels from the study flow table. Use Vxx/访视xx labels only if the flow table has them. Otherwise use Dxx or Wxx exactly as supported by the flow table.
- Which visits define “study period”, “treatment period”, and “follow-up period”.
- Whether unscheduled visits should count in first/last actual visit. Default: include if the protocol says “研究期间” and the visit occurred.

## Medication Rules

Find the exact definition for:

- Prior medication / 既往用药.
- Concomitant medication / 合并用药.
- Prior therapy and concomitant non-drug therapy if the protocol tracks them separately.
- Whether the definition uses “研究期间”, “治疗期间”, “研究药物治疗期间”, “签署知情同意后”, or “首次给药后”.
- Whether study drug should be excluded from CM. Default: exclude research/study drug if it appears in CM, using configured name patterns.
- Prohibited/restricted medication and therapy categories, including route/form restrictions, examples, washout windows, allowed exceptions, rescue-treatment exceptions, background-therapy requirements, and whether findings/PDs must be recorded.
- Whether washout is fixed time, half-life based, or “longer of fixed time and half-lives”. Do not convert half-life rules unless the half-life evidence is supplied or can be derived from source documents the user provided.

If no definition is found, ask the user whether to use the default fallback:

- 合并用药: non-study medication whose date range overlaps first study drug administration through treatment-period final visit.

## Eligibility and Lab Rules

Extract only criteria that can be evaluated from the supplied listings.

- Medical-history exclusions and required stability/absence windows.
- Prior medication, prior therapy, procedure, or vaccine exclusions.
- Laboratory exclusion thresholds, units, timing anchors, repeat/retest rules, and whether abnormality history alone is sufficient.
- If a criterion is numeric, evaluate actual screening/randomization values before flagging; do not flag only from a diagnosis or abnormality name.
- If a threshold cannot be calculated because units, dates, or reference ranges are missing, report uncertainty instead of inventing a verdict.

## AE Risk Source Rules

Extract AE risk topics only from supplied or explicitly identified sources.

- Protocol-defined AESI or special interest categories.
- IB, approved label, protocol, same-target, or same-class safety topics that should prompt an AE assessment review.
- AE seriousness and severity fields needed to mark SAE, SAR, SUSAR, and grade >=3 events.
- Causality terms that correspond to unrelated, possibly unrelated, related, and unknown. Preserve source wording in display.

Potential AE assessment risk generally requires both a safety-topic match and an unrelated/possibly unrelated causality judgment. Related events may still show the safety-topic cue, but should not be called assessment-improper solely because they match the safety topic.

## Finding/PD Matching Rules

Before assigning “registered” or “missing” status, define event-level matching keys:

- Subject ID.
- Risk context/category.
- Raw drug/therapy/event term.
- Matched protocol/list keyword or class.
- Normalized/core term after stripping common salts, route prefixes, dosage forms, punctuation, and whitespace.
- Exact date or overlapping date range when dates are available.

Do not use subject-level matching as proof of registration. One registered event does not register another same-subject event unless the term/context and date window also match.

## Medical History Rules

Find the exact definition for:

- Past medical history / 既往史.
- Current medical history / 现病史.
- Whether ongoing conditions at screening, D1, first dose, or study end are current history.

If no definition is found, ask the user whether to use the default fallback:

- 现病史: condition whose date range overlaps first study drug administration through the subject’s last study visit.

## Date Handling

- Preserve original partial dates in displayed text.
- For interval classification only:
  - `YYYY-MM-uk`: start bound = first day of month, end bound = last day of month.
  - `YYYY-uk-uk`: start bound = Jan 1, end bound = Dec 31.
- If date imputation changes classification, flag it in precheck.

## Precheck Output

Before building, report:

- Files recognized and modules enabled.
- Sheet/column mapping summary.
- Definitions found in protocol, with exact short paraphrase and source section/page when available.
- Missing definitions or ambiguous fields requiring user confirmation.
- Population decision: all subjects vs randomized subjects only.
- USV decision: include or exclude planned/unplanned visit data.
- Grouping/randomization source: uploaded group table, randomization sheet, screening result sheet, or unresolved.
- Risk modules enabled: prohibited medication/therapy, eligibility/MH/lab, AE assessment, or none.
- Risk-source summary: protocol sections, explanation tables, finding/PD listings, IB/label sources, and lab listings used.
