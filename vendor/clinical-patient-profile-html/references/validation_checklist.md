# Validation Checklist

Run this after building and before delivering the HTML.

## Input consistency

- Confirm the selected center list matches the intended scope.
- Confirm the main listing workbook is the intended source workbook.
- Confirm the finding workbook and sheet mappings match the intended centers.

## Row-count checks

Compare output CSV counts against the source-driven expectation:

- subjects
- efficacy rows
- lab rows
- vital-sign rows
- finding rows

Large unexpected drops usually mean a center filter, sheet-name mismatch, or value-column mismatch.

Also compare subject coverage against every authoritative subject source available, such as ICF, SV, DM, randomization, and subject report sheets. For each source, record:

- unique subject count
- missing subjects in output
- extra subjects in output
- duplicate output subject IDs
- per-center subject counts and first/last subject IDs after numeric sorting

Do not treat a top selector check as enough. A subject can exist in the data and top dropdown while still being hidden by a sidebar, collapsed group, filter state, or layout clipping.

## Subject-level spot checks

Check at least a few subjects across different scenarios:

- randomized active subject
- randomized control subject
- screen-failure subject
- subject with findings
- subject with abnormal labs

For each spot check, compare HTML against the source workbook on:

- sex
- age group
- treatment group
- visit labels
- efficacy values
- lab values and reference ranges
- vital-sign values
- linked finding IDs

## Longitudinal chronology checks

Verify all plotted and tabulated subject-level longitudinal records sort by actual assessment date, not by planned visit label alone.

- USV / UNS / 计划外 / 非计划 rows must appear at their actual dates in subject-level graphs and tables.
- Overall and center-level aggregate graphs/tables should exclude unplanned visits unless the user explicitly requested otherwise.
- Screening/D1 baseline merging is allowed only when the protocol or user confirms that rule; subject-level raw records should remain traceable.

If a graph is missing because the first row is an unplanned visit, fix the chart eligibility logic instead of moving the unplanned visit to the end.

## Response logic checks

Verify that response flags are only assigned where the current protocol explicitly defines a responder rule and the rule is computable from the available subject-level data.

If the protocol defines only continuous efficacy endpoints, the response flag column should remain blank rather than carrying forward any prior-project responder labels.

## Project-agnostic boundary checks

Before updating the reusable skill, scan the skill files for project-specific terms introduced during local project work.

Do not commit default code or documentation for:

- disease-specific symptom scores or questionnaire names unless they are examples already used by the generic fixture
- project-specific SAP endpoint calculations or diary windows
- PK, PD, immunogenicity, biomarker, environmental, device, or exposure modules unless they are made config-driven and broadly applicable
- project names, compound names, center names, local file paths, or project-specific report titles

Keep project-specific extensions in the project folder or a separate optional extension, not in the generic skill.

## Rendered HTML checks

Open the generated HTML in a browser and verify:

- selectors and any subject navigation lists are numerically sorted
- long center groups are scrollable and not clipped
- selecting a known subject renders the expected profile card
- filters that hide a module do not leave related summary blocks visible
- page-level horizontal overflow is absent, while wide tables/charts scroll locally
- browser console has no errors

## Final decision rule

If the source workbook and HTML disagree, treat the source workbook as the current truth until the mapping or build logic is corrected.
