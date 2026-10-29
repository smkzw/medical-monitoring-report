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

from common import clin_code, dump_json, load_json, norm_date, open_workbook_lenient, parse_links, parse_typed_links, to_num, yes

DATE_FIELDS = {'date', 'start', 'end', 'icf', 'eot_d', 'eos_d', 'rand_d', 'fd', 'ld', 'aware', 'rpt'}
NUM_FIELDS = {'age', 'bmi', 'ht', 'wt', 'lo', 'hi'}
BOOL_FIELDS = {'serious', 'aesi', 'ongoing_b'}
SHEETS = {}


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
    for rown, r in data:
        rec = {k: conv(k, r[i] if i is not None and i < len(r) else None, M) for k, i in cols.items()}
        if not rec.get('sid'):
            continue
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


def findings(spec, books, M):
    out = []
    lay = spec.get('layout', 'long')
    for rec, r, labels, vars_ in read_spec(spec, books, M):
        base = {k: rec.get(k) for k in ('sid', 'visit', 'date', 'time', 'tpt', 'sheet', 'row', 'done', 'wb', 'reason', 'reason_text', '_chg',
                                        'reason_disease', 'reason_link', 'reason_other', 'flag')}
        if base.get('_chg') is None:
            base.pop('_chg')                          # 只有差异导出模式才带变更标记
        base['domain'] = spec.get('domain', 'lab')
        base['group'] = spec.get('group', spec['sheet'])
        if lay == 'long':
            items = [dict(rec)]
        else:
            items = []
            for test, tc in spec['tests'].items():
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
            if isinstance(f['unit'], str) and re.match(r'^10\^?\d', f['unit']):
                f['unit'] = '×' + f['unit']  # "10^9/L" → "×10^9/L" so "68 ×10^9/L" reads correctly
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
