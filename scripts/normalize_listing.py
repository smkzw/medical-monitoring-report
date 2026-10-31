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
from pathlib import Path

import openpyxl

from common import clin_code, dump_json, load_json, norm_date, open_workbook_lenient, parse_desc_links, parse_links, parse_typed_links, to_num, yes

DATE_FIELDS = {'date', 'start', 'end', 'icf', 'eot_d', 'eos_d', 'rand_d', 'fd', 'ld', 'aware', 'rpt'}
NUM_FIELDS = {'age', 'bmi', 'ht', 'wt', 'lo', 'hi'}
BOOL_FIELDS = {'serious', 'aesi', 'ongoing_b'}
SHEETS = {}

# F01①（RUX 深审）：完成标志类布尔列不作指标值——值域⊂{0,1,是,否} 勾选形态，且列名含 是否/完成/勾选、
# 或同表多数测试列同为勾选形态（整表是页面完成情况清单，如「计划外访视询问」UNSIGA 类列）。
_CHK_RX = re.compile(r'是否|完成|勾选')
_CHK_VALS = {'0', '1', '0.0', '1.0', '是', '否', '无', '有', 'true', 'false', 'y', 'n', '√'}
# F03（RUX 深审）：SAE 标准勾选列（取值 1/0 或 是/否）——标签口径；「请说明」列不算，已映射列不重复采集。
_SAE_CRIT_RX = re.compile(r'致死|导致死亡|危及生命|住院|致残|残疾|先天异常|出生缺陷|重要医学事件')
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


def form_names(book):
    """EDC 导出常带目录页（TOC/目录：表单编号 → 表单名称），用于把 LBCH、OTH 等代码显示成中文表单名。"""
    out = {}
    names = set(book.wb.sheetnames)
    for n in book.wb.sheetnames:
        ws = book.wb[n]
        rows = list(ws.iter_rows(min_row=1, max_row=400, values_only=True))
        head = ' '.join(str(x) for x in (rows[0] if rows else []) if x)
        if not (re.fullmatch(r'TOC|目录|Contents?|表单目录', n.strip(), re.I) or re.search(r'表单名称|Form\s*Name', head, re.I)):
            continue
        for r in rows[1:]:
            c = [str(x).strip() for x in r if x not in (None, '')]
            if len(c) >= 2 and c[0] in names and c[0] != n:
                out[c[0]] = c[1]
    return out


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


def read_spec(spec, books, M):
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
    hlk = ('value', 'clin', 'desc', 'link', 'grade', 'rel', 'term', 'aesi', 'serious', 'action', 'indication', 'start', 'end', 'date')
    # PR-8: SHEETS keyed by per-workbook unique id "wb:sheet" — same-name sheets in different
    # workbooks no longer collapse into one meta entry (each keeps its own highlight columns / sid label).
    sid_key = f"{alias}:{spec['sheet']}"
    meta = SHEETS.setdefault(sid_key, {'wb': alias, 'sheet': spec['sheet'], 'label_row': lr, 'var_row': vr, 'data_start': ds, 'hl': [], 'sid': None})
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
    flag_i = next((i for i, lb in enumerate(labels)
                   if _AE_FLAG_RX.search(lb) and re.search(r'不良事件|AE', lb, re.I) and not _AE_FLAG_BAD.search(lb)), None)
    term_is = [i for i, lb in enumerate(labels) if _AE_TERM_RX.search(lb) and not re.search(r'编码|CODE|版本|语言', lb, re.I)]
    crit_is = [i for i, lb in enumerate(labels) if _SAE_CRIT_RX.search(lb) and not re.search(r'请说明|描述', lb)
               and i not in set(cols.values())]
    for rown, r in data:
        rec = {k: conv(k, r[i] if i is not None and i < len(r) else None, M) for k, i in cols.items()}
        if not rec.get('sid'):
            continue
        if flag_i is not None and term_is and flag_i < len(r):
            fv = '' if r[flag_i] is None else str(r[flag_i]).strip().lower()
            if fv in _AE_NO_VALS and all(i >= len(r) or r[i] in (None, '') for i in term_is):
                continue          # 发生标志=否 且无任何术语 → 空白日志行，不是事件记录（F04：RUX 标志列名不同此前漏跳）
        if crit_is:               # F03：SAE 标准勾选（1/是/true/Y→勾选），勾选的条目名收集为 sae_crit
            hit = [labels[i].strip() for i in crit_is if i < len(r) and yes(r[i])]
            rec['sae_crit'] = '、'.join(hit)
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
        rec['wb'] = alias           # PR-8: owning workbook alias on every record (row-level attribution)
        rec['sheet'] = spec['sheet']
        rec['row'] = rown
        rec.update(spec.get('const', {}))
        yield rec, r, labels, vars_


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
    for rec, r, labels, vars_ in read_spec(spec, books, M):
        base = {k: rec.get(k) for k in ('sid', 'visit', 'date', 'time', 'tpt', 'sheet', 'row', 'done', 'wb', 'reason', 'reason_text', '_chg',
                                        'reason_disease', 'reason_link', 'reason_other', 'flag')}
        if base.get('_chg') is None:
            base.pop('_chg')                          # 只有差异导出模式才带变更标记
        base['domain'] = spec.get('domain', 'lab')
        base['group'] = spec.get('group', spec['sheet'])
        if lay == 'long':
            if str(rec.get('test') or '') in flag_tests:
                continue                      # F01①：长表按测试名同样排除完成标志类
            items = [dict(rec)]
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
                items.append(it)
        for it in items:
            raw = it.get('value')
            if raw in (None, '') and it.get('clin') is None:
                continue
            f = dict(base)
            f.update({'test': str(it.get('test') or '').strip(), 'raw': None if raw is None else str(raw),
                      'value': to_num(raw), 'unit': it.get('unit'), 'lo': to_num(it.get('lo')), 'hi': to_num(it.get('hi')),
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
                f['unit'] = f['unit'].replace('μ', 'µ')   # F10：μ 两种写法归一（U+03BC → U+00B5，与分级表键一致）
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
        if dom == 'findings':
            recs = [f for s in specs for f in findings(s, books, M)]
        else:
            recs = []
            for s in specs:
                for rec, *_ in read_spec(s, books, M):
                    if dom in ('ae', 'mh', 'cm', 'proc') and 'term' in (s.get('cols') or {}) and not str(rec.get('term') or '').strip():
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
               'formNames': {k: v for b in books.values() for k, v in form_names(b).items()}}, out / '_source.json')


if __name__ == '__main__':
    main()
