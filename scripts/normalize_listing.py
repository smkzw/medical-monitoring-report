#!/usr/bin/env python3
"""Deconstruct raw EDC data listings into tidy tables using a mapping file.

Usage: python3 normalize_listing.py mapping.json --out work/norm

mapping.json (see references/mapping-schema.md):
{
  "workbooks": {"edc": "EDC_listing.xlsx", "lab": "central_lab.xlsx"},   # alias -> path (relative to mapping file)
  "label_row": 1, "var_row": 2, "data_start": 3,                         # defaults; may be overridden per spec
  "visit_map": {"筛选期访视1": "V1", "re:^第(\\d+)周$": "W\\1"},
  "clin_map": [["无临床意义", 1], ["有临床意义", 2], ["正常", 0]],
  "domains": {
    "subjects":  [{"wb": "edc", "sheet": "DM", "cols": {"sid": "SUBJID", "site": "SITEID", ...}}],
    "visits":    [{"sheet": "SV", "cols": {"sid": "SUBJID", "visit": "VISIT", "date": "SVDAT"}}],
    "exposure":  [...], "ae": [...], "mh": [...], "cm": [...], "proc": [...], "pd": [...], "efficacy": [...], "extq": [...],
    "findings":  [{"sheet": "LBHEMA", "domain": "lab", "group": "血常规", "layout": "long",
                   "cols": {"sid": "SUBJID", "visit": "VISIT", "date": "LBDAT", "test": "LBTEST", "value": "LBORRES",
                            "unit": "LBORRESU", "lo": "LBORNRLO", "hi": "LBORNRHI", "clin": "LBCLSIG", "desc": "LBDESC", "link": "LBLINK"}},
                  {"sheet": "VS", "domain": "vs", "layout": "wide", "cols": {"sid": "SUBJID", "visit": "VISIT", "date": "VSDAT", "tpt": "VSTPT"},
                   "tests": {"收缩压": {"value": "SYSBP", "unit": "mmHg", "clin": "SYSCLSIG"}}}]
  }
}
Column references may be the variable name (row var_row) or the Chinese label (row label_row); first match wins.
Every output record keeps `sheet` and `row` (Excel row number) so findings/queries trace back to the source row.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

import openpyxl

from common import clin_code, dump_json, load_json, norm_date, num_bound, num_state, open_workbook_lenient, parse_desc_links, parse_links, parse_typed_links, redact_row, to_num, yes
from inspect_listing import STRUCT_OK, guess, is_meta_col, is_struct_col

DATE_FIELDS = {'date', 'start', 'end', 'icf', 'eot_d', 'eos_d', 'rand_d', 'fd', 'ld', 'aware', 'rpt', 'win_lo', 'win_hi'}
NUM_FIELDS = {'age', 'bmi', 'ht', 'wt', 'lo', 'hi'}
BOOL_FIELDS = {'serious', 'aesi', 'ongoing_b', 'dili'}   # V6：dili 也是「是/否」——原样字符串「否」在下游 bool() 为真（D002 全部 AE 标 DILI）
EVENT_DOMS = ('ae', 'mh', 'cm', 'proc', 'pd')      # 带 term 的事件型域
SHEETS = {}

# F01①（RUX 深审）：完成标志类布尔列不作指标值——值域⊂{0,1,是,否} 勾选形态，且列名含 是否/完成/勾选、
# 或同表多数测试列同为勾选形态（整表是页面完成情况清单，如「计划外访视询问」UNSIGA 类列）。
_CHK_RX = re.compile(r'是否|完成|勾选')
_CHK_VALS = {'0', '1', '0.0', '1.0', '是', '否', '无', '有', 'true', 'false', 'y', 'n', '√'}
# F03（RUX 深审）：SAE 标准勾选列（取值 1/0 或 是/否）——标签口径；「请说明」列不算，已映射列不重复采集。
_SAE_CRIT_RX = re.compile(r'致死|导致死亡|危及生命|住院|致残|残疾|先天异常|出生缺陷|重要医学事件')
_SAE_CRIT_VAR = re.compile(r'AES(DTH|DETH|LIFE|HOSP|DISAB|CONG|MIE)', re.I)   # SDTM AE 严重性标准变量
_SAE_CRIT_NAME = {'DTH': '致死', 'DETH': '致死', 'LIFE': '危及生命', 'HOSP': '住院或延长住院', 'DISAB': '致残',
                  'CONG': '先天异常', 'MIE': '其他重要医学事件'}
# F04（RUX 深审）：AE 发生标志列（列名各厂商不同：是否发生不良事件？/有无不良事件/是否发生AE——
# 但不含 严重/SAE/AESI/持续/措施 等，那些是别的字段）；真实术语列＝名称/术语类标签。
_AE_FLAG_RX = re.compile(r'是否|有无')
_AE_FLAG_BAD = re.compile(r'严重|SAE|AESI|持续|治疗|采取|合并|关系|转归')
_AE_TERM_RX = re.compile(r'不良事件名称|事件名称|AETERM|术语')
_AE_NO_VALS = {'否', '无', '没有', '0', 'n', 'no', 'false', '未发生'}


class Book:
    def __init__(self, path, log=print):
        self.path = path
        name = Path(path).name
        # PLAN §21 P1：EDC 全量导出的非法 autoFilter／截断 dimension 会让 read_only 静默近空读——
        # 读表入口统一走容错封装（带伤文件回退普通模式／剥离副本，宁可慢也要读全，日志含表名与原因）。
        self.wb, _notes = open_workbook_lenient(
            path, read_only=True, data_only=True,
            log=(lambda m: log(f'  ! {name} {m}')) if log else None)
        self._cache = {}

    def sheet(self, name, label_row, var_row, data_start):
        key = (name, label_row, var_row, data_start)
        if key in self._cache:
            return self._cache[key]
        ws = self.wb[name]
        rows = list(ws.iter_rows(values_only=True))
        labels = [str(x).strip() if x is not None else '' for x in (rows[label_row - 1] if len(rows) >= label_row else [])]
        vars_ = [str(x).strip() if x is not None else '' for x in (rows[var_row - 1] if var_row and len(rows) >= var_row else [])]
        data = [(i + 1, r) for i, r in enumerate(rows) if i + 1 >= data_start and any(c not in (None, '') for c in r)]
        self._cache[key] = (labels, vars_, data)
        return self._cache[key]


def catalog_map(sheet_rows, names):
    """表单目录 → {表单代码: 表单名称}。sheet_rows：{sheet 名: 前若干行}；names：工作簿全部 sheet 名。
    目录页形态不固定（TOC/目录、DOMAIN_NAME 四列「版本 | 数据集名 | 表单 OID | 表单名称」…）：
    找一列取值大多是其他 sheet 名（≥3 个且 ≥一半行），名称取同行右侧第一个含中文/非代码的单元格。V6（MY008211A）。"""
    out = {}
    for n, rows in sheet_rows.items():
        body = [r for r in rows[1:] if r]
        if not body:
            continue
        ncol = max(len(r) for r in body)
        head = ' '.join(str(x) for x in (rows[0] or ()) if x)
        # 表名就是目录（TOC/DOMAIN_NAME…）→ 1 张表对上即可；只有表头含「表单名称」→ 至少 2 张（工程审阅：单行 SAE 报告表
        # 的「关联表单」填 AE 会被误判为目录页）；其余 ≥3 张
        need = 1 if re.fullmatch(r'TOC|目录|Contents?|表单目录|DOMAIN_NAME', str(n).strip(), re.I) else \
            2 if re.search(r'表单名称|Form[\s_]*Name', head, re.I) else 3
        for j in range(ncol):
            vals = [str(r[j]).strip() if j < len(r) and r[j] not in (None, '') else '' for r in body]
            hit = [v for v in vals if v in names and v != n]
            # MGK：目录页按 CRF 版本重复列出（V3.0/V3.1 各一遍）——同代码同名称的重复行只算一次
            hs = set(hit)
            rows_u = {(str(r[j]).strip(), tuple(r[j + 1:])) for r in body if j < len(r) and str(r[j]).strip() in hs}
            if len(hit) < need or len(hit) < 0.5 * len([v for v in vals if v]) or len(hs) < 0.8 * len(rows_u):
                continue                                 # 目录里每张表只出现一次（代码表/字典逐选项重复出现，不是目录）
            m = {}
            for r in body:
                code = str(r[j]).strip() if j < len(r) and r[j] not in (None, '') else ''
                if code not in names or code == n:
                    continue
                nm = next((str(x).strip() for x in r[j + 1:] if x not in (None, '') and str(x).strip() not in names
                           and re.search(r'[\u4e00-\u9fff]', str(x))), '')
                if nm:
                    m.setdefault(code, nm)
            if len(m) >= need:
                for k, v in m.items():
                    out.setdefault(k, v)                 # 多个目录页：先到先得（与工作台 detect.catalog_map 同口径）
                break
    return out


def form_names(book):
    """EDC 导出常带目录页（表单代码 → 表单名称），用于把 LBCH、OTH、LB3 等代码显示成中文表单名。结果缓存在 book 上。"""
    if getattr(book, '_form_names', None) is not None:
        return book._form_names
    names = set(book.wb.sheetnames)
    rows = {}
    for n in book.wb.sheetnames:
        ws = book.wb[n]
        if ws.max_row and ws.max_row > 2000:              # 数据表不可能是目录页；只取较小的表扫描
            continue
        rows[n] = list(ws.iter_rows(min_row=1, max_row=400, values_only=True))
    try:
        book._form_names = catalog_map(rows, names)
    except AttributeError:                                # 不可挂属性的 book 对象：不缓存
        return catalog_map(rows, names)
    return book._form_names


def col_index(ref, labels, vars_):
    """列引用：变量名 / 中文标签 / 列序号（int，0 起）；同名列用「名称#n」取第 n 次出现（1 起），如「其他，请描述#2」。"""
    if ref is None:
        return None
    if isinstance(ref, int):
        return ref
    name, nth = ref, 1
    m = re.fullmatch(r'(.+)#(\d+)', str(ref))
    if m and not any(ref in arr for arr in (vars_, labels)):
        name, nth = m.group(1), int(m.group(2))
    for arr in (vars_, labels):
        idx = [i for i, x in enumerate(arr) if x == name]
        if len(idx) >= nth:
            return idx[nth - 1]
    # mm4：「不良事件名称(AETERM)」式表头（单行表头把变量名写在括号里）→ 变量名或括号前标签均可引用
    for grp in (2, 1):
        idx = [i for i, x in enumerate(labels) if (m := _LABEL_VAR.fullmatch(str(x or '').strip())) and m.group(grp) == name]
        if len(idx) >= nth:
            return idx[nth - 1]
    return None


_LABEL_VAR = re.compile(r'(.+?)\s*[（(]([A-Z][A-Z0-9_]{1,19})[)）]')


REASON_DEFAULT = [(r'研究疾病|原发病|研究适应症|疾病本身|study disease|underlying disease', 'disease'),
                  (r'病史|不良事件|^AE|^MH|既往|adverse|medical history', 'link'),
                  (r'其他|其它|other', 'other')]


def reason_code(v, patterns=None):
    """CS 原因取值 → disease（研究疾病）/ link（病史或不良事件，需关联编号）/ other（其他+文本）/ None。"""
    if v is None or str(v).strip() == '':
        return None
    s = str(v).strip()
    for pat, code in (patterns or REASON_DEFAULT):
        if re.search(pat, s, re.I):
            return code
    return 'other'


def _term_guard(sheet, ti, labels, vars_):
    """第三轮 E2E（RUX 复审）：事件域 term 列落在结构性元数据列（访视名称/页面名称/研究中心…，陈旧或误确认的 mapping）
    → 按 FIELD_SYN（F-A 判据：CMTRT/MHTERM/PRTRT/AETERM 具体列优先、名称$ 不吃访视/页面/表单/中心）重找真实术语列；
    找不到置空（无术语列的表不是事件记录，与映射层「没有术语列不纳入」同口径）。日志可见，不静默。"""
    lab = labels[ti] if ti < len(labels) else ''
    var = vars_[ti] if ti < len(vars_) else ''
    if not is_struct_col(lab, var):
        return ti
    fix = guess([(l, vars_[i] if i < len(vars_) else '') for i, l in enumerate(labels)], 'term')
    j = col_index(fix, labels, vars_) if fix else None
    if j == ti:
        j = None
    print(f"  ! {sheet}: term 列「{lab or var}」是结构性元数据列（访视/页面/表单/中心），"
          + (f"改用「{labels[j] or vars_[j]}」" if j is not None else '表内无术语列，事件记录不纳入'))
    return j


def map_visit(v, vm):
    if v is None:
        return None
    s = str(v).strip()
    if s in vm:
        return vm[s]
    for k, code in vm.items():
        if k.startswith('re:') and re.search(k[3:], s):
            return re.sub(k[3:], code, s) if '\\' in code else code
    return s


def conv(field, v, M):
    if field in DATE_FIELDS:
        return norm_date(v)
    if field in ('lo', 'hi'):
        return num_bound(v)          # 宽表/列绑定的参考范围同样认科学计数与单位乘方（审阅者 2026-11-09：曾只在长表常量路径生效）
    if field in NUM_FIELDS:
        return to_num(v)
    if field in BOOL_FIELDS:
        return yes(v)
    if field == 'visit':
        return map_visit(v, M.get('visit_map', {}))
    if field == 'clin':
        return clin_code(v, M.get('clin_map'))
    if field == 'sid':
        return None if v is None else str(v).strip()
    if v is None:
        return None
    return v if isinstance(v, (int, float)) else str(v).strip()


def read_spec(spec, books, M, dom=None):
    alias = spec.get('wb', next(iter(books)))
    book = books[alias]
    lr = spec.get('label_row', M.get('label_row', 1))
    vr = spec.get('var_row', M.get('var_row', 2))
    ds = spec.get('data_start', M.get('data_start', 3))
    if M.get('allow_missing_sheets') and spec['sheet'] not in book.wb.sheetnames:   # 差异导出可只含有变化的表单
        print(f"  - {alias}:{spec['sheet']} 不在本次文件中，跳过")
        return []
    labels, vars_, data = book.sheet(spec['sheet'], lr, vr, ds)
    cols = {k: col_index(c, labels, vars_) for k, c in spec.get('cols', {}).items()}
    if dom in EVENT_DOMS and cols.get('term') is not None:
        cols['term'] = _term_guard(spec['sheet'], cols['term'], labels, vars_)
    for k in [k for k, ix in cols.items() if ix is not None and k not in STRUCT_OK and k != 'term']:
        ix = cols[k]                     # V6：事实字段落在结构性/稽查元数据列（陈旧或误确认的 mapping：time=页面最近修改时间）→ 不读
        lab, var = (labels[ix] if ix < len(labels) else ''), (vars_[ix] if ix < len(vars_) else '')
        if is_meta_col(lab, var):
            print(f"  ! {spec['sheet']}: {k} 列「{lab or var}」是结构性/稽查元数据列，不作为 {k} 读取")
            cols[k] = None
    hlk = ('value', 'clin', 'desc', 'link', 'grade', 'rel', 'term', 'aesi', 'serious', 'action', 'indication', 'start', 'end', 'date')
    # PR-8: SHEETS keyed by per-workbook unique id "wb:sheet" — same-name sheets in different
    # workbooks no longer collapse into one meta entry (each keeps its own highlight columns / sid label).
    sid_key = f"{alias}:{spec['sheet']}"
    meta = SHEETS.setdefault(sid_key, {'wb': alias, 'sheet': spec['sheet'], 'label_row': lr, 'var_row': vr, 'data_start': ds, 'hl': [], 'sid': None,
                                       'domain': spec.get('domain') or dom})
    for k, i in cols.items():
        if i is not None and i < len(labels) and k in hlk and labels[i] not in meta['hl']:
            meta['hl'].append(labels[i])
        if k == 'sid' and i is not None and i < len(labels):
            meta['sid'] = labels[i]
    for tc in (spec.get('tests') or {}).values():
        for k, c in tc.items():
            i = col_index(c, labels, vars_) if isinstance(c, str) else None
            if i is not None and k in hlk and labels[i] not in meta['hl']:
                meta['hl'].append(labels[i])
    missing = [k for k, i in cols.items() if i is None]
    if missing:
        print(f"  ! {spec['sheet']}: unresolved columns {missing}")
    # filter：{"col","eq"|"not"|"not_re"}，可为数组（全部满足）；mapping 级 row_filter 对所有 spec 生效
    # （如 EDC 差异导出的 Flag=Deleted 行：{"col": "Flag", "not_re": "^Deleted$"}——已删除记录不得进入分析）。
    filts = [x for x in ([spec['filter']] if isinstance(spec.get('filter'), dict) else (spec.get('filter') or []))]
    filts += [x for x in (M.get('row_filter') or []) if col_index(x['col'], labels, vars_) is not None]
    fidx = [(x, col_index(x['col'], labels, vars_)) for x in filts]
    # mm4 增量：差异导出模式下保留变更标记（新增/修改/删除）供工作台合并，不在此过滤（mapping 级 change_flag: [列名…]）
    cfi = next((i for i in (col_index(c, labels, vars_) for c in (M.get('change_flag') or [])) if i is not None), None)
    # F04：AE 日志页的发生标志列＋真实术语列（按标签识别，与 mapping 是否映射无关）；F03：SAE 标准勾选列。
    # mm5 审阅修正：只在 AE 域生效——合并用药「是否因不良事件用药=否」、检验「是否记录为AE=否」都是真实记录，不能跳过
    flag_i = next((i for i, lb in enumerate(labels)
                   if _AE_FLAG_RX.search(lb) and re.search(r'不良事件|AE', lb, re.I) and not _AE_FLAG_BAD.search(lb)), None) if dom == 'ae' else None
    term_is = [i for i, lb in enumerate(labels) if _AE_TERM_RX.search(lb) and not re.search(r'编码|CODE|版本|语言', lb, re.I)]
    crit_is = [i for i, lb in enumerate(labels) if _SAE_CRIT_RX.search(lb) and not re.search(r'请说明|描述|Code Value|编码值', lb, re.I)
               and i not in set(cols.values())]       # V6（MY008）：「…(Code Value)」编码副本列不重复计入 SAE 标准
    if dom == 'ae':                                   # MGK 2026-11-14：只有变量名表头时按 SDTM 标准变量名认 SAE 标准（AESHOSP…）
        crit_is += [i for i, v in enumerate(vars_ if any(vars_) else labels)
                    if i not in crit_is and _SAE_CRIT_VAR.fullmatch(str(v or '').strip()) and i not in set(cols.values())]
    crit_txt = next((i for i, lb in enumerate(labels) if re.search(r'SAE\s*标准|严重(性)?标准', lb) and not re.search(r'是否|Code Value|编码值', lb, re.I)
                     and i not in crit_is), None) if dom == 'ae' else None
    # 审阅者 2026-11-10：合并用药表自带 WHODrug 编码时（锁库/稽查数据常见：ATC1–4 编码/代码列），收集全部层级 ATC 代码——
    # 引擎按 ATC 判类别与途径（比药名准）；无编码列时由本地 WHODrug 对照表按药名补
    atc_is = [i for i, lb in enumerate(labels) if re.search(r'ATC\s*\d?\s*(编码|代码|code|cd)$|^ATC\d?CD$|ATC\s*\d?\s*(编码|代码)', lb, re.I)
              and not re.search(r'术语|名称|term|text', lb, re.I)] if dom == 'cm' else []
    si = cols.get('sid')
    hdr_sid = {str(x).strip() for x in ((labels[si] if si is not None and si < len(labels) else None),
                                         (vars_[si] if si is not None and si < len(vars_) else None)) if x}
    for rown, r in data:
        r = redact_row(labels, list(r))    # 审阅者 2026-11-09：自由文本里夹带的本行姓名缩写打码（PD 详述「受试者HLSH…」）
        rec = {k: conv(k, r[i] if i is not None and i < len(r) else None, M) for k, i in cols.items()}
        if not rec.get('sid') or str(rec['sid']).strip() in hdr_sid:
            continue              # V6（MY008 MH1）：表中间重复导出的表头行（受试者列＝「SUBJID」）不是记录
        for k_ in ('eot_why', 'eos_why'):     # 原因是勾选列（MY008 筛选结束页「不符合入选标准 √」）→ 原因＝该列标签
            i_ = cols.get(k_)
            if i_ is not None and re.fullmatch(r'\s*[√✓✔☑]\s*|\s*(是|1|Y|Yes)\s*', str(rec.get(k_) or ''), re.I) and i_ < len(labels):
                rec[k_] = re.sub(r'[（(]\s*Code Value\s*[)）]', '', str(labels[i_])).strip()
        if 'nd' in rec:           # 「未做」勾选列（1/是/√＝未做）→ done=否（与「是否进行」同口径）
            if yes(rec.pop('nd')):
                rec['done'] = '否'
        if flag_i is not None and term_is and flag_i < len(r):
            fv = '' if r[flag_i] is None else str(r[flag_i]).strip().lower()
            if fv in _AE_NO_VALS and all(i >= len(r) or r[i] in (None, '') for i in term_is):
                continue          # 发生标志=否 且无任何术语 → 空白日志行，不是事件记录（F04：RUX 标志列名不同此前漏跳）
        if crit_is:               # F03：SAE 标准勾选（1/是/true/Y→勾选），勾选的条目名收集为 sae_crit
            hit = [_SAE_CRIT_NAME.get(str(labels[i]).strip().upper()[4:], str(labels[i]).strip()) for i in crit_is if i < len(r) and yes(r[i])]
            rec['sae_crit'] = '、'.join(hit)
        if dom == 'ae':
            rec['sae_crit_known'] = bool(crit_is) or crit_txt is not None   # 表里根本没有 SAE 标准信息 ≠ 标准均未勾选
        if atc_is:
            codes = sorted({str(r[i]).strip().upper() for i in atc_is if i < len(r) and r[i] not in (None, '')
                            and re.fullmatch(r'[A-Z]\d{2}([A-Z]([A-Z](\d{2})?)?)?', str(r[i]).strip().upper())})
            if codes:
                rec['atc'] = codes
        if crit_txt is not None and crit_txt < len(r) and r[crit_txt] not in (None, '') and not rec.get('sae_crit'):
            rec['sae_crit'] = str(r[crit_txt]).strip()   # D001：SAE 标准是文本列（「需要住院治疗或延长住院时间」），曾判「标准均未勾选」
        if cfi is not None:
            cv = r[cfi] if cfi < len(r) else None
            rec['_chg'] = '' if cv is None else str(cv).strip()
        skip = False
        for fx, fi in fidx:
            fv = r[fi] if fi is not None and fi < len(r) else None
            s = '' if fv is None else str(fv).strip()
            if ('eq' in fx and s != str(fx['eq'])) or ('not' in fx and s == str(fx['not'])) or \
                    ('not_re' in fx and re.search(fx['not_re'], s)):
                skip = True
                break
        if skip:
            continue
        if dom == 'ie' and cols.get('met') is not None and cols['met'] < len(labels):
            rec['met_q'] = labels[cols['met']]   # 入排总问的问法（「是否满足全部…」与「是否有不符合…」极性相反）
        rec['wb'] = alias           # PR-8: owning workbook alias on every record (row-level attribution)
        rec['sheet'] = spec['sheet']
        rec['row'] = rown
        rec.update(spec.get('const', {}))
        yield rec, r, labels, vars_


def _numv(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def _record_level_clin(items, spec):
    """V6 R2（审阅者 2026-11-02，D002/SAR 复盘）：宽表里一个「临床意义」列被多个参数共用（心电图整份一个判定）时，
    原实现把同一 CS 抄给每个参数 → 心率/PR/QRS… 各发一条「CS 未关联 AE」。改为：判定只留在超出参考范围的参数上；
    没有参数可判异常（或无参考范围）时，生成一条「<表>·总体评价」记录承载该判定（关联/描述随行），参数本身不带判定。"""
    cnt = Counter(it['_clin_col'] for it in items if it.get('_clin_col'))
    shared = {c for c, n in cnt.items() if n >= 2}
    if not shared:
        return items
    out = [it for it in items if it.get('_clin_col') not in shared]
    for col in shared:
        grp = [it for it in items if it.get('_clin_col') == col]
        cv = next((it.get('clin') for it in grp if it.get('clin') not in (None, '')), None)
        abn = []
        for it in grp:
            v, lo, hi = _numv(it.get('value')), _numv(it.get('lo')), _numv(it.get('hi'))
            if v is not None and ((lo is not None and v < lo) or (hi is not None and v > hi)):
                abn.append(it)
        rec = None
        if cv is not None and not abn:
            # 审阅修正（MM/CRA 2026-11-02：88 条「「」判定为CS」）：关联/描述先于参数清理取出；结果写描述或各参数值，不留空
            rec = {'test': f"{spec.get('group') or spec['sheet']}·总体评价", 'clin': cv}
            for k in ('link', 'link_mh', 'link_ae', 'desc', 'reason_disease', 'reason_link', 'reason_other'):
                v = next((it.get(k) for it in grp if it.get(k) not in (None, '')), None)
                if v is not None:
                    rec[k] = v
            summ = '；'.join(f"{it['test']} {it.get('value')}" for it in grp if it.get('value') not in (None, ''))
            rec['value'] = str(rec.get('desc') or summ or '')[:120] or None
        for it in grp:
            if it not in abn:
                it['clin'] = None
                for k in ('link', 'link_mh', 'link_ae', 'desc'):
                    it.pop(k, None)                    # 整份记录的关联/描述随判定走（异常参数或总体评价）
            out.append(it)
        if rec:
            out.append(rec)
    for it in out:
        it.pop('_clin_col', None)
    return out


def _bool_flag_tests(spec, book, M, lay):
    """F01①：完成标志类布尔测试集合。宽表逐测试列看全列值域；长表按测试名分组看值域。
    判据（通用）：值域非空且⊂{0,1,是,否…}勾选形态，且（测试名/列名含 是否/完成/勾选，或同表多数测试列
    同为勾选形态——整表是页面完成情况清单如「计划外访视询问」）→ 该测试不是数值指标。"""
    alias = spec.get('wb', next(iter(book and M.get('workbooks') or {})))
    tests = spec.get('tests') or {}
    if lay == 'wide' and not tests:
        return set()
    lr = spec.get('label_row', M.get('label_row', 1))
    vr = spec.get('var_row', M.get('var_row', 2))
    ds = spec.get('data_start', M.get('data_start', 3))
    try:
        labels, vars_, data = book.sheet(spec['sheet'], lr, vr, ds)
    except Exception:
        return set()
    vals = {}                                   # 测试键 → 全列/全组取值集合
    if lay == 'wide':
        cols = {}
        for t, tc in tests.items():
            c = tc.get('value') if isinstance(tc, dict) else None
            i = col_index(c, labels, vars_) if isinstance(c, str) else None
            if i is not None:
                cols[t] = i
        for _n, r in data:
            for t, i in cols.items():
                if i < len(r) and r[i] not in (None, ''):
                    vals.setdefault(t, set()).add(str(r[i]).strip().lower())
        named = {t for t in cols if _CHK_RX.search(str(t))}
    else:
        ti = col_index(spec.get('cols', {}).get('test'), labels, vars_) if isinstance(spec.get('cols', {}).get('test'), str) else None
        vi = col_index(spec.get('cols', {}).get('value'), labels, vars_) if isinstance(spec.get('cols', {}).get('value'), str) else None
        if ti is None or vi is None:
            return set()
        for _n, r in data:
            if ti < len(r) and vi < len(r) and r[vi] not in (None, ''):
                vals.setdefault(str(r[ti]).strip(), set()).add(str(r[vi]).strip().lower())
        named = {t for t in vals if _CHK_RX.search(str(t))}
    shaped = {t for t, vs in vals.items() if vs and vs <= _CHK_VALS}
    if not shaped:
        return set()
    # 多数测试列同为勾选形态 → 整表是完成情况清单，全部勾选形态列都不作指标；仅个别列靠列名提示识别
    if 2 * len(shaped) > len(vals):
        return shaped
    return {t for t in shaped if t in named or _CHK_RX.search(str(t))}


def findings(spec, books, M):
    out = []
    lay = spec.get('layout', 'long')
    alias = spec.get('wb', next(iter(books)))
    flag_tests = _bool_flag_tests(spec, books[alias], M, lay)
    # V6（MY008 工程审阅：PE/MO/XT/LB 等单项检查表没有检查项列，整表 3000 余行被 `if not f['test']` 丢掉）：
    # 长表未绑检查项列时，检查项＝表单名（目录页中文名优先），记录不丢
    no_test_col = lay == 'long' and not (spec.get('cols') or {}).get('test')
    form_nm = (form_names(books[alias]).get(spec['sheet']) or spec['sheet']) if no_test_col else ''
    for rec, r, labels, vars_ in read_spec(spec, books, M):
        loc = str(rec.get('loc') or '').strip()       # V6：测量部位限定词（DXA 腰椎/股骨颈/全髋）拼进检查名
        base = {k: rec.get(k) for k in ('sid', 'visit', 'vcode', 'date', 'time', 'tpt', 'sheet', 'row', 'done', 'wb', 'reason', 'reason_text', '_chg',
                                        'reason_disease', 'reason_link', 'reason_other', 'flag')}
        if base.get('_chg') is None:
            base.pop('_chg')                          # 只有差异导出模式才带变更标记
        base['domain'] = spec.get('domain', 'lab')
        base['group'] = spec.get('group', spec['sheet'])
        if lay == 'long':
            if str(rec.get('test') or '') in flag_tests:
                continue                      # F01①：长表按测试名同样排除完成标志类
            items = [dict(rec)]
            if not str(items[0].get('test') or '') and items[0].get('metric'):
                items[0]['test'] = items[0]['metric']   # efficacy 窄表（const metric）：测试名回落到 metric，记录不丢
            elif no_test_col and not str(items[0].get('test') or ''):
                items[0]['test'] = form_nm
        else:
            items = []
            for test, tc in spec['tests'].items():
                if test in flag_tests:
                    continue                      # F01①：完成标志列不作指标值
                it = {'test': test}
                for k, c in tc.items():
                    if k in ('unit', 'lo', 'hi') and not isinstance(c, str):
                        it[k] = c
                        continue
                    i = col_index(c, labels, vars_)
                    if i is None:
                        it[k] = c if k in ('unit',) else None
                    else:
                        it[k] = conv(k, r[i] if i < len(r) else None, M)
                if tc.get('clin') is not None:
                    it['_clin_col'] = str(tc['clin'])
                for k_ in ('link', 'link_mh', 'link_ae', 'desc'):          # 记录级关联/描述对该行全部检查项生效（SAR 心电图 EGMHNO）
                    if it.get(k_) in (None, '') and rec.get(k_) not in (None, ''):
                        it[k_] = rec[k_]
                items.append(it)
            items = _record_level_clin(items, spec)
        for it in items:
            raw = it.get('value')
            if raw in (None, '') and it.get('clin') is None:
                continue
            # F8：结果/范围统一走 num_state/num_bound——「2分-中度」「中度（2）」内嵌分数/级别词取出数值（主要终点趋势不丢）；
            # 「<50」「<1*10^3」按删失态处理（value=None，不参与超上限比较，判据走 result_state）；const/列范围「<1*10^3」取幅度。
            st = num_state(raw) if raw not in (None, '') else None
            f = dict(base)
            f.update({'test': str(it.get('test') or '').strip() + (f'·{loc}' if loc else ''), 'raw': None if raw is None else str(raw),
                      'value': st[1] if st is not None and st[0] == 'value' else None,
                      'unit': it.get('unit'), 'lo': num_bound(it.get('lo')), 'hi': num_bound(it.get('hi')),
                      'clin': it.get('clin'), 'desc': it.get('desc'),
                      'links': parse_links(it.get('link'), M.get('link_re')) + parse_typed_links(it.get('link_mh'), 'MH') +
                      parse_typed_links(it.get('link_ae'), 'AE')})
            # F02（RUX 深审）：「异常有临床意义请说明」列的关联引用同样采集——编号型（MHn/MH#n/MHn#术语）
            # 由 parse_links 识别，词目型（XX既往史/与XX有关）由 parse_desc_links 识别；与 link 列去重合并，
            # 编号是否真实存在由 build 层 resolve_links 回溯（不存在 → l[4]=False，仍按未关联发 query）。
            for dl in parse_links(f.get('desc')) + parse_desc_links(f.get('desc')):
                if dl[:2] not in [x[:2] for x in f['links']]:
                    f['links'].append(dl)
            if f.get('clin') == 'ND':
                # K11：临床意义取值「未查/未做/未检/ND」＝条目未完成（clin_map 映射 'ND'）——置未完成标记，
                # 不作为结果、不落「未评价」（避免误入「超出参考范围·未评价」；也不得被选作基线）。
                f['clin'], f['raw'], f['value'], f['desc'] = None, None, None, None
                f['done'] = '否'
            for k in ('reason', 'reason_text', 'reason_disease', 'reason_link', 'reason_other'):
                if it.get(k) not in (None, ''):          # 宽表逐指标原因列覆盖行级
                    f[k] = it.get(k)
            # CS 原因（mm4）：单选文本 reason（reason_map 归类）或复选框 reason_disease/reason_link/reason_other（是/否）
            codes = []
            f['reason_raw'] = f.get('reason')              # 原因选项原文（如「与研究疾病加重有关」），供备注加重识别
            if f.get('reason') not in (None, ''):
                codes.append(reason_code(f['reason'], M.get('reason_map')))
            for k, c in (('reason_disease', 'disease'), ('reason_link', 'link'), ('reason_other', 'other')):
                if yes(f.pop(k, None)) and c not in codes:
                    codes.append(c)
            f['reason'] = '+'.join(c for c in codes if c) or None
            if f['links'] and 'link' not in (f['reason'] or ''):
                f['reason'] = '+'.join(filter(None, [f['reason'], 'link']))
            if not f['test']:
                continue
            if isinstance(f['unit'], str) and f['unit']:
                f['unit'] = f['unit'].replace('μ', 'µ')   # F12⑤修正：数据层归一到 U+00B5（与分级表键一致，V5 F10 既有约定——ext1 夹具实证 03BC 方向破坏 CSW 判定翻转路径的键比较）
            if isinstance(f['unit'], str) and re.search(r'10\s*[Ee]\s*\d', f['unit']):
                f['unit'] = re.sub(r'(?<![\d.])10\s*[Ee]\s*(\d+)', r'10^\1', f['unit'])   # V6（MY008）：10E12/L＝×10^12/L
            if isinstance(f['unit'], str) and '10^' in f['unit']:
                # 单位科学计数归一（一处分叉收口）：运算符统一为 ×——大小写 x/X、全半角乘号 ＊/×/✕/⨯ 及其与
                # 数字间的空格都收（SAR 实测 *10^9/L、x10^9/L、×10^9/L 混存）；数字直接粘 10^（星号在复制/导出链
                # 被吞的成品形态「310^9/L」）补 ×；裸 10^9/L 前缀口径保留。归一后程序文案 {raw}{unit} 无分隔拼接自然正确。
                u = re.sub(r'^\s*[*＊xXｘＸ✕⨯×]+\s*10\^', '×10^', f['unit'])
                u = re.sub(r'(\d)\s*[*＊xXｘＸ✕⨯×]+\s*10\^', r'\1×10^', u)
                u = re.sub(r'(\d)10\^', r'\1×10^', u)
                if re.match(r'^\s*10\^', u):
                    u = '×' + u.lstrip()  # "10^9/L" → "×10^9/L" so "68 ×10^9/L" reads correctly
                f['unit'] = u
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mapping')
    ap.add_argument('--out', default='work/norm')
    a = ap.parse_args()
    mp = Path(a.mapping)
    M = load_json(mp)
    books = {k: Book(str((mp.parent / v).resolve()) if not Path(v).is_absolute() else v) for k, v in M['workbooks'].items()}
    out = Path(a.out)
    D = M['domains']
    for dom, specs in D.items():
        if dom in ('findings', 'efficacy'):
            # efficacy 与 findings 同构处理（V5 修复波：D001INC 实测 efficacy 宽表 tests 不展开 → 量表列值
            # 全空、eff.metrics 空、KPI 缺失）。展开后每条记录补 metric＝test（build_eff 按 eff:<metric> 归组）；
            # 窄表（const metric）在 findings() 内回落 test＝metric，metric 语义不变。
            recs = []
            for s in specs:
                sp = dict(s)
                if dom == 'efficacy':
                    if not sp.get('domain'):
                        sp['domain'] = 'efficacy'
                    if sp.get('tests') and not sp.get('layout'):
                        sp['layout'] = 'wide'          # 实测（D001INC/RUX）：efficacy 宽表只带 tests 不写 layout → 按宽表展开
                for f in findings(sp, books, M):
                    f.setdefault('metric', f.get('test'))
                    recs.append(f)
        else:
            recs = []
            for s in specs:
                for rec, *_ in read_spec(s, books, M, dom):
                    if dom in ('ae', 'mh', 'cm', 'proc') and 'term' in (s.get('cols') or {}) and \
                            re.fullmatch(r'(是|否|有|无|Y|N|Yes|No|NA|N/A|不适用|未知|不详)?', str(rec.get('term') or '').strip(), re.I):
                        continue                         # 日志表的占位行（如「是否发生了不良事件？=否」）不是事件记录
                    if dom in ('mh', 'cm') and 'ongoing' in rec:
                        rec['ongoing'] = yes(rec['ongoing'])
                    recs.append(rec)
        if dom == 'subjects':  # merge several sheets per subject
            by = {}
            for r in recs:
                cur = by.setdefault(r['sid'], {'sid': r['sid']})
                for k, v in r.items():
                    if v not in (None, '') and cur.get(k) in (None, ''):
                        cur[k] = v
            recs = list(by.values())
        dump_json(recs, out / f'{dom}.json')
        print(f'{dom}: {len(recs)}')
    # PR-8: `sheets` is keyed by per-workbook unique id "wb:sheet"; `sheets_by_name` maps each plain
    # sheet name to its owning ids (migration/back-compat: name-keyed consumers resolve deterministically).
    by_name = {}
    for sid_key, m in SHEETS.items():
        by_name.setdefault(m['sheet'], []).append(sid_key)
    dump_json({'workbooks': {k: b.path for k, b in books.items()}, 'label_row': M.get('label_row', 1),
               'var_row': M.get('var_row', 2), 'data_start': M.get('data_start', 3),
               'sheets': SHEETS, 'sheets_by_name': by_name,
               # V6 B4：未映射的表名（终点无数据时据此给出「可能的来源表」候选，不自动绑定）
               'unmapped': sorted({n for b in books.values() for n in b.wb.sheetnames} - {m['sheet'] for m in SHEETS.values()}),
               'formNames': {k: v for b in books.values() for k, v in form_names(b).items()}}, out / '_source.json')


if __name__ == '__main__':
    main()
