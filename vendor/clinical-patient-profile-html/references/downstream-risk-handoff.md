# Downstream Risk Handoff

Patient Profile is an inspection view upstream of medical risk review. When another workflow will use the profile to seed AE/MH, medication, laboratory, or protocol-deviation review, preserve the following contract.

## Handoff content

For each subject-level value, event, or derived label that may be used downstream, retain:

| Field | Requirement |
|---|---|
| Scope | Population decision (`all`, `randomized`, or another confirmed scope), center scope, and USV/UNS decision. |
| Provenance | Source workbook, sheet, row or record identifier, and the field mapping used. |
| Subject identity | Subject ID, center, group/status, and the normalization applied for display only. |
| Time | Raw visit label and actual assessment date; keep USV/UNS at its actual date when included. |
| Measurement | Raw result, unit, reference range, investigator assessment, and any source explanation. |
| Derived display | Baseline label, endpoint alias, response flag, or other calculated field plus the rule/source that supports it. |
| Completeness | Present, missing, not collected, not applicable, or unresolved mapping. Never represent a missing value as zero or silently drop a protocol-required category. |

## Scope and authority

- Reconfirm the population and USV/UNS scope in the downstream risk workflow. Do not assume the profile's visible selector is the complete population.
- Use the original listing and protocol as the authority for a risk conclusion. Profile CSVs and HTML are traceable views, not a replacement for source records.
- If the study flow says a category should be collected but no usable rows are found, carry an explicit completeness issue forward instead of treating the category as absent.
- Keep screening/D1 baseline merging as a display decision. Preserve the raw records and the protocol basis so a downstream calculation can reconstruct the baseline.

## Minimum QC before handoff

1. Compare subject and center coverage with the authoritative DM/randomization/visit sources.
2. Spot-check raw values, dates, units, normal ranges, and linked Finding IDs against the output CSV and rendered HTML.
3. Verify numeric date sorting, actual USV/UNS placement, and absence of layout clipping in the browser.
4. Record unresolved mappings and excluded fields in the handoff rather than hiding them in a narrative note.
