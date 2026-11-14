# mapping.json 规范（normalize_listing.py）

```json
{
  "workbooks": {"edc": "EDC.xlsx", "pdq": "PD_and_CRO.xlsx"},
  "label_row": 1, "var_row": 2, "data_start": 3,
  "visit_map": {"筛选期": "V1", "第1天": "D1", "re:^第(\\d+)周$": "W\\1", "计划外访视": "USV", "提前退出": "ET"},
  "clin_map": [["异常有临床意义", 2], ["异常无临床意义", 1], ["正常", 0]],
  "domains": {"subjects": [...], "visits": [...], "exposure": [...], "ae": [...], "mh": [...], "cm": [...], "proc": [...],
              "findings": [...], "efficacy": [...], "pd": [...], "extq": [...], "groups": [...]}
}
```
- workbook 路径相对 mapping 文件；列引用可写变量名或中文标签（先匹配变量名行，再匹配标签行）。
- 每个 spec：`{"wb", "sheet", "cols": {...}, "label_row"?, "var_row"?, "data_start"?, "filter"?: {"col","eq"|"not"}, "const"?: {...}}`。
- 每条输出记录自动带 `sheet` 与 `row`（Excel 行号），用于证据回查。
- 日期字段自动规范为 `YYYY-MM-DD`（不完整日期（UK/UNK 等）保留原文，不做插补）；`lo/hi/age/bmi/ht/wt` 转数值。

## 各域字段

| 域 | 字段 |
|---|---|
| subjects（可多 sheet，按 sid 合并） | `sid`* `site` `center` `icf` `age` `sex` `ht` `wt` `bmi` `eth` `rand` `rand_d` `strat` `status` `fd` `ld` `eot_d` `eot_why` `eos_d` `eos_done` `eos_why` `cond` ＋mm4：`rescreen`（是否重复筛选）`prev_sid`（首次筛选编号）|
| visits | `sid`* `visit`* `date`* |
| exposure | `sid`* `visit` `start`* `end` `dose` `pause` ＋mm4：`time`（给药时刻）`route` `freq` `fast`（是否空腹）`qty`（实际用量，依从性）；剂量制记录用 `dose_plan`（每日计划剂量）`dose_act`（每日实际剂量）`miss_qty`/`extra_qty`（漏服/多服总剂量，只在无法给出具体日期时计）；实际剂量为 0 的区间视为暂停，不算首/末次给药 |
| ae | `sid`* `no` `term`* `pt` `soc` `llt`（MedDRA 编码，AESI 按 PT/SOC 定义时必需）`start`* `end` `grade` `serious` `aesi` `rel` `action` `outcome` `cm` `withdraw` `dili` `aware`（获知日期）`rpt`（报告日期）|
| mh | `sid`* `no` `term`* `start` `end` `ongoing` |
| cm | `sid`* `no` `term`* `start` `end` `ongoing` `dose` `freq` `route` `indication` `ind_kind` |
| proc | `sid`* `no` `term`* `start` `end` |
| findings | `sid`* `visit` `date` `time` `tpt` `test`* `value`* `unit` `lo` `hi` `clin` `desc` `link` `link_mh` `link_ae`（按类型分列的关联编号列，取值如「003>窦性心动过缓>2026-07-07」）`done`；spec 级 `domain`(lab/vs/ecg/img/pe/exam/pk/ada…；lab/vs/ecg 以外的域自动成为个例页通用「专项检查」组，如妇科超声、眼科、影像) `group` `layout`(long/wide) `tests`(宽表) |
| efficacy | `sid`* `visit` `date` `metric`* `value`* ＋mm4：量表宽表（一行一次评分，如 EASI 各部位＋总分）每个汇总列一条 spec，`const: {metric: "EASI得分"}`，有总分时只取总分；只有「是否评估/日期」没有得分的表不生成 spec，预检提示 |
| pd | `sid`* `cat` `desc` `date` ＋`sub`（子类）`grade`（严重程度原文）`status` |
| icf（mm4） | `sid`* `ver` `date`* |
| sample（mm4） | `sid`* `visit` `tpt`（计划时间点）`date`* `time` `dose_date` `dose_time` `done` |
| dispense（mm4，预留） | `sid`* `visit` `date` `disp` `ret` |
| extq | `sid`* `form` `visit` `row` `text`* |
| groups | `sid`* `grp` `strat` |
| events（2026-11-14，方案事件） | `sid`* `start`* `type`（或 const.type＝事件名）`end` `ongoing` `treat`（处理方式：住院/急诊/全身激素…）`hosp` `period`（研究阶段）`link_cm` `link_ae` `desc` `no` `visit`——方案规定的逐条事件（急性发作、复发、出血发作…），不限病种 |

\* 必需。`link`（检验页“关联 AE/MH”字段）支持 `AE+1+头痛`、`MH+4+贫血`、`病史-3 - 贫血 - 2020-01-01`、`不良事件-2 - 头痛 - 日期`、`AE 3` 等写法
（多条以 ; ， 、 换行或连续空格分隔），解析为 `[类型, 术语, _, 编号]`；特殊写法用 mapping 级 `link_re`（命名组 type/no/term）。
findings 另可映射 `reason`（CS 原因单选文本，mapping 级 `reason_map: [[正则, disease|link|other]]` 覆盖默认归类）、`reason_text`，
或复选框 `reason_disease` / `reason_link` / `reason_other`（是/否）；宽表 tests 内同名键逐指标覆盖。

**列引用**：变量名 / 中文标签 / 列序号（int）；同名列用 `"名称#2"` 取第 2 次出现。单行表头写成「不良事件名称(AETERM)」时，括号内变量名或括号前标签均可引用。
**行过滤**：spec `filter` 可为对象或数组（`eq` / `not` / `not_re`）；mapping 级 `row_filter` 对所有含该列的 sheet 生效，
如 EDC 差异导出的已删除行：`"row_filter": [{"col": "Flag", "not_re": "^Deleted$"}]`。
**变更标记**（差异导出合并用）：mapping 级 `change_flag: ["Flag", "变更标记", …]`（候选列名，取第一个存在的列）→ 每条记录带 `_chg`
（原值，如 New/Changed/Deleted）；不写则不带。宿主据此把差异导出合并到上一次数据（工作台 lifecycle/delta.py），此时不应再用
`row_filter` 过滤删除行。`allow_missing_sheets: true`：spec 指向的 sheet 不在文件中时跳过（差异导出可只含有变化的表单）；缺省报错。

## 宽表 tests
```json
{"wb":"edc","sheet":"VS","domain":"vs","group":"生命体征","layout":"wide",
 "cols":{"sid":"SUBJID","visit":"VISIT","date":"VSDAT","tpt":"VSTPT"},
 "tests":{"收缩压":{"value":"SYSBP","unit":"mmHg","clin":"SYSCS","lo":90,"hi":139},
          "体重":{"value":"WEIGHT","unit":"kg"}}}
```
`unit/lo/hi` 写常量（数字或不在表头中的字符串）即按常量；写列名即取列值。范围常量支持检测限/科学计数原文：「<1*10^3 拷贝数/mL」「≤1×10³」按 1000 解析（F8），参考范围列是文本时按列绑定（norm 行解析，不给静默常量）。

## 校验
- 运行后检查每域行数；`! <sheet>: unresolved columns [...]` 必须清零或确认不需要。
- `visit_map` 未覆盖的访视会原样保留，导致不进入 SoA/趋势；`clin_map` 未覆盖的取值视为未评价。
