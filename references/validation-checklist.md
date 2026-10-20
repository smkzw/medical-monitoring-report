# 交付前检查清单

## 自动
- [ ] `normalize_listing.py`：无 `unresolved columns`；各域行数与 listing 行数相符（抽查 2–3 个 sheet）。
- [ ] `build_site.py` 摘要数字合理（人群数 = 预期；labrows/others/queries 非 0 且非爆量）。
- [ ] `node scripts/render_check.js out/S/HTML --shots out/S/shots`：9 页 + 个例 + 时间线 + 所有 tab + 抽屉，**0 错误**。
- [ ] `python3 scripts/validate_contract.py out/S/HTML --source-check`：OK（无 ERROR；WARN 逐条解释）。

## 人工（看截图 + 抽查源数据）
- [ ] 总览 KPI 与安全性页计数一致；USV/ET 未进入汇总。
- [ ] 随机抽 3 条 CSX、2 条 NCS2、2 条规则信号，回到 listing 源行核对原值/单位/范围/判定/关联。
- [ ] query 文本：事实可在源行找到；请求可操作；无“漏报”“违规”等定性措辞；同单元格已合并。
- [ ] CRO 查重：抽查 2 条「同主题已查重」是否确为同主题。
- [ ] 盲态：任何页面、悬浮提示、导出文件均无分组信息。
- [ ] 时间线：给药、AE、CM 条带起止正确；风险行独立；无截断/重叠。
- [ ] 规则溯源：每条规则有方案/IB 出处；冲突已写入 consensus。
- [ ] 视觉：无整宽色条；中文无乱码；图表无空白容器。
- [ ] 方法学页列出人群、基线、USV、盲态、未提供的模块（如无 IB / 无 PD）。
