# Project Rules Contract

The core assessment logic is intentionally generic. Use a project-local JSON file for protocol- or medical-review-specific exclusions and risk presentation rules.

## Example

```json
{
  "version": "1",
  "population_scope": "all",
  "non_ctcae_threshold_pct": 20,
  "excluded_tests": ["项目A"],
  "excluded_directional_patterns": ["项目B升高"],
  "bp": {
    "收缩压": {
      "info_max": 140,
      "medium_max_pct_change": 50
    }
  },
  "special_focus": ["AESI", "ADR/IB"]
}
```

## Semantics

- `population_scope` is `all` by default. Set it to `group_table` only when the supplied group table is confirmed to represent the target randomized population, or to `allowlist` with an explicit `subjects` array. A missing or ambiguous population source is a build blocker.
- `non_ctcae_threshold_pct` overrides the generic default only for this run. The chosen value must be shown in the assessment metadata and report header.
- `excluded_tests` uses case-insensitive exact-or-contained matching against the normalized test name. Excluded tests are removed before CTCAE indexing and risk counting.
- `excluded_directional_patterns` matches the normalized test name plus the detected direction, such as `项目B升高`. It removes only the matching directional event, not the opposite-direction assessment.
- `bp` and other indicator blocks may set `info_max` to classify an otherwise detected item as `info`, and `medium_max_pct_change` to prevent a high-risk classification when the maximum absolute baseline change is within the configured limit.
- `special_focus` is metadata for downstream display or review. It does not create a risk without source evidence.

## Precedence and evidence

1. The current protocol, approved safety source, and user-confirmed project rule take precedence over generic defaults.
2. An explicit CLI threshold overrides the JSON threshold for that run.
3. A rule never fabricates a missing result, reference range, CTCAE grade, AE/MH explanation, or Finding linkage.
4. Preserve the applied rule file and rule note in `assessment.json`. If a rule cannot be applied because a required value or direction is missing, retain `uncertain` rather than silently treating the item as normal.
