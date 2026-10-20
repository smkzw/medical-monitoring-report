# 上游技能（只读归档）

本目录保留被合并的三个技能原文，用于追溯设计来源；`SKILL.md` 已重命名为 `UPSTREAM_SKILL.md`，避免被当作独立技能加载。

| 上游 | 版本 | 合并到本技能的能力 |
|---|---|---|
| [smkzw/clinical-patient-profile-html](https://github.com/smkzw/clinical-patient-profile-html) | 1.0.2 | 受试者 Profile、方案驱动终点识别、预检提问、USV/排序/单侧范围等经验 → `subjects`/`efficacy` 页、workflow |
| [smkzw/ae-risk-assessment](https://github.com/smkzw/ae-risk-assessment) | 1.3.0 | CTCAE 分级、基线定义、临床意义列检测、风险分级、AE/MH 关联合理性 → `analysis-rules` §2–4、`safety` 页 |
| [smkzw/subject-timeline-builder](https://github.com/smkzw/subject-timeline-builder) | 0.1.2 | 受试者时间线、禁用药/入排/判定合理性风险、方案抽取与证据契约 → `timeline` 页、`protocol-ib-extraction` |

新功能请在根目录 `scripts/` 与 `templates/` 中实现，不要修改本目录。
