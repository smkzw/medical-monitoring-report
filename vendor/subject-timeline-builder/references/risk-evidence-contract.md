# Risk Evidence Contract

Use this contract whenever the timeline includes derived medication, eligibility, AE-assessment, or Finding/PD risk output. It keeps a readable timeline from becoming an untraceable conclusion.

## Required fields

Each derived row or card should retain, either directly or through a stable item ID:

| Field | Requirement |
|---|---|
| `subject` / `center` | Preserve the source identifiers and the normalized display identifiers. |
| `source_sheet` / `source_row` | Point to the raw listing row, workbook tab, or explicit derived-data record. |
| `source_term` | Preserve the original medication, therapy, AE, MH, lab, or Finding wording. |
| `matched_rule` / `rule_locator` | Name the protocol section, explanation-table row, IB/label topic, or user-confirmed rule used. |
| `date_start` / `date_end` | Preserve raw dates and the interval used for comparison; flag partial-date bounds. |
| `calculation` | Record washout anchor, half-life assumption, threshold, CTCAE comparison, or other derivation. |
| `status` | Use separate values for `risk`, `prompt`, `registered_finding`, `rescue_or_exempt`, `not_applicable`, and `uncertain`; do not collapse them into one risk label. |
| `match_key` | For Finding/PD linkage, retain subject, context/category, term or rule keyword, and overlapping date range. |
| `evidence` | Keep the short raw text or source-field values that support the decision. |

## Medication and history decisions

- Read prior-medication washout from the current protocol. Distinguish fixed-day, half-life-based, and “longer of” rules; if half-life evidence is absent, record uncertainty rather than inventing a value.
- For a history that continues into screening or baseline, evaluate the actual applicable inclusion/exclusion criterion. A disease name alone is not evidence of eligibility violation when the protocol requires a threshold, activity definition, or time window.
- If a protocol exempts rescue treatment, keep the treatment visible as a prompt or exempt item while keeping it out of the potential missed-Finding/PD risk count. Preserve the exemption basis.

## Finding/PD registration

Registration is event-level, not subject-level. The minimum comparison key is:

```text
subject + risk context/category + raw or normalized term + applicable rule keyword + overlapping date/range
```

If one element is unavailable, retain `uncertain` and state which element could not be compared. Do not mark every same-subject, same-class event as registered because one similar event is present in the Finding/PD listing.

## Handoff and QC

The risk workbook and HTML should allow a reviewer to move from a card to its source row and rule basis. Before delivery, compare counts and selected records against the raw listing, then search the output for unsupported “已登记” or “已确认” language. A generated display is not a replacement for the source listing or protocol.
