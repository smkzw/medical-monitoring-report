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
| subjects（可多 sheet，按 sid 合并） | `sid`* `site` `center` `icf` `age` `sex` `ht` `wt` `bmi` `eth` `rand` `rand_d` `strat` `status` `fd` `ld` `eot_d` `eot_why` `eos_d` `eos_done` `eos_why` `cond` |
| visits | `sid`* `visit`* `date`* |
| exposure | `sid`* `visit` `start`* `end` `dose` `pause` |
| ae | `sid`* `no` `term`* `pt` `soc` `llt`（MedDRA 编码，AESI 按 PT/SOC 定义时必需）`start`* `end` `grade` `serious` `aesi` `rel` `action` `outcome` `cm` `withdraw` `dili` `aware`（获知日期）`rpt`（报告日期）|
| mh | `sid`* `no` `term`* `start` `end` `ongoing` |
| cm | `sid`* `no` `term`* `start` `end` `ongoing` `dose` `freq` `route` `indication` `ind_kind` |
| proc | `sid`* `no` `term`* `start` `end` |
| findings | `sid`* `visit` `date` `time` `tpt` `test`* `value`* `unit` `lo` `hi` `clin` `desc` `link` `done`；spec 级 `domain`(lab/vs/ecg/img/pe/exam/pk/ada…；lab/vs/ecg 以外的域自动成为个例页通用「专项检查」组，如妇科超声、眼科、影像) `group` `layout`(long/wide) `tests`(宽表) |
| efficacy | `sid`* `visit` `date` `metric`* `value`* |
| pd | `sid`* `cat` `desc` `date` |
| extq | `sid`* `form` `visit` `row` `text`* |
| groups | `sid`* `grp` `strat` |

\* 必需。`link`（检验页“关联 AE/MH”字段）支持 `AE+1+头痛`、`MH+4+贫血` 等写法（多条以 ; ， 、 或换行分隔），解析为 `[类型, 术语, _, 编号]`。

## 宽表 tests
```json
{"wb":"edc","sheet":"VS","domain":"vs","group":"生命体征","layout":"wide",
 "cols":{"sid":"SUBJID","visit":"VISIT","date":"VSDAT","tpt":"VSTPT"},
 "tests":{"收缩压":{"value":"SYSBP","unit":"mmHg","clin":"SYSCS","lo":90,"hi":139},
          "体重":{"value":"WEIGHT","unit":"kg"}}}
```
`unit/lo/hi` 写常量（数字或不在表头中的字符串）即按常量；写列名即取列值。

## 校验
- 运行后检查每域行数；`! <sheet>: unresolved columns [...]` 必须清零或确认不需要。
- `visit_map` 未覆盖的访视会原样保留，导致不进入 SoA/趋势；`clin_map` 未覆盖的取值视为未评价。
