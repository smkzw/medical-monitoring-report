# 文件与 sheet 识别

## 常见 listing 形态
- **双表头**：第 1 行中文标签、第 2 行变量名、第 3 行起数据（默认 `label_row=1, var_row=2, data_start=3`）。`inspect_listing.py` 会自动探测其他表头位置并写入 spec。
- **单表头**：`var_row` 设为与 `label_row` 相同或 `null`。
- **长表**：每行一个检查项（LBTEST/LBORRES）。**宽表**：每列一个检查项（SYSBP/DIABP/PULSE）。
- 同一域拆成多个 sheet（血常规/血生化/尿常规/凝血），每个 sheet 一个 spec，`group` 写中文组名。

## sheet 名 → 域（inspect_listing.py 的默认正则，可扩展）
| 域 | 正则（sheet 名开头） |
|---|---|
| subjects | DM、人口学、受试者信息、筛选、知情、ENR、RAND、随机；DS、完成、结束、退出、EOS、EOT、研究总结 |
| visits | SV、访视日期、访视 |
| exposure | EC、EX、给药、研究药物、用药记录、服药、DA、药物发放 |
| ae / mh / cm / proc | AE、不良事件 / MH、病史 / CM、合并用药 / PR、手术、操作 |
| findings:lab | LB、血常规、血生化、尿常规、凝血、实验室、甲功、血脂、肝功、肾功、电解质、妊娠、HEMA/CHEM/URIN/COAG |
| findings:vs / ecg | VS、生命体征 / EG、ECG、心电图 |
| efficacy | QS、EFF、RS、TU、TR、量表、评分、疗效、有效性、问卷、日记 |
| pd | DV、PD、方案偏离 |
| extq（CRO 质疑） | 含 质疑/QUERY，或以 CROQ/DCF/EDCQ 开头 |
| pk / ada | PK、PC、药代、血药浓度、采样 / ADA、IS、免疫原性 |

未匹配的 sheet 在 `inventory.md` 中列为「未识别」，必须人工判断（可能是中心阅片、日记卡、器械、问卷子表等）。

## 可选数据的接入方式
- **分组/随机表**：`domains.groups` → `{sid, grp, strat}`；盲态构建时 `grp` 被强制清空。
- **中心实验室**：作为 `findings`（`domain: "lab"`），`group` 写「中心实验室」；与 EDC 本地实验室并存时注意同名指标用不同 `group` 区分。
- **中心阅片 / 影像**：定性结果 → `findings`，在 `analysis.qualTestRe` 中登记定性指标；定量终点 → `efficacy`。
- **量表/日记**：`efficacy` 长表（metric/value）；派生指标（较基线变化、百分比、应答）在 `analysis.efficacy` 中按方案定义。
- **PK/PD/ADA**：`findings` 并设 `domain: "pk"|"ada"`；只有采样状态无结果时，仅展示采集状态，并在预检中说明。
- **PD listing**：`pd` → `{sid, cat, desc, date}`；用于与禁用药/入排/超窗信号逐事件比对。
- **CRO 已发质疑**：`extq` → `{sid, form, visit, row, text}`；用于查重与冲突检测。
