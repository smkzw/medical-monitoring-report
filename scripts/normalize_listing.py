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

from common import clin_code, dump_json, load_json, norm_date, parse_links, to_num, yes

DATE_FIELDS = {'date', 'start', 'end', 'icf', 'eot_d', 'eos_d', 'rand_d', 'fd', 'ld', 'aware', 'rpt'}
NUM_FIELDS = {'age', 'bmi', 'ht', 'wt', 'lo', 'hi'}
BOOL_FIELDS = {'serious', 'aesi', 'ongoing_b'}
SHEETS = {}


class Book:
    def __init__(self, path):
        self.path = path
        self.wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
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


def col_index(ref, labels, vars_):
    if ref is None:
        return None
    if isinstance(ref, int):
        return ref
    for arr in (vars_, labels):
        if ref in arr:
            return arr.index(ref)
    return None


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
    wb = books[spec.get('wb', next(iter(books)))]
    lr = spec.get('label_row', M.get('label_row', 1))
    vr = spec.get('var_row', M.get('var_row', 2))
    ds = spec.get('data_start', M.get('data_start', 3))
    labels, vars_, data = wb.sheet(spec['sheet'], lr, vr, ds)
    cols = {k: col_index(c, labels, vars_) for k, c in spec.get('cols', {}).items()}
    hlk = ('value', 'clin', 'desc', 'link', 'grade', 'rel', 'term', 'aesi', 'serious', 'action', 'indication', 'start', 'end', 'date')
    meta = SHEETS.setdefault(spec['sheet'], {'wb': spec.get('wb', next(iter(books))), 'label_row': lr, 'var_row': vr, 'data_start': ds, 'hl': [], 'sid': None})
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
    filt = spec.get('filter')  # {"col": "LBSTAT", "not": "未查"}
    for rown, r in data:
        rec = {k: conv(k, r[i] if i is not None and i < len(r) else None, M) for k, i in cols.items()}
        if not rec.get('sid'):
            continue
        if filt:
            fi = col_index(filt['col'], labels, vars_)
            fv = r[fi] if fi is not None else None
            if 'eq' in filt and str(fv) != str(filt['eq']):
                continue
            if 'not' in filt and str(fv) == str(filt['not']):
                continue
        rec['sheet'] = spec['sheet']
        rec['row'] = rown
        rec.update(spec.get('const', {}))
        yield rec, r, labels, vars_


def findings(spec, books, M):
    out = []
    lay = spec.get('layout', 'long')
    for rec, r, labels, vars_ in read_spec(spec, books, M):
        base = {k: rec.get(k) for k in ('sid', 'visit', 'date', 'time', 'tpt', 'sheet', 'row', 'done')}
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
                      'clin': it.get('clin'), 'desc': it.get('desc'), 'links': parse_links(it.get('link'))})
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
    dump_json({'workbooks': {k: b.path for k, b in books.items()}, 'label_row': M.get('label_row', 1),
               'var_row': M.get('var_row', 2), 'data_start': M.get('data_start', 3), 'sheets': SHEETS}, out / '_source.json')


if __name__ == '__main__':
    main()
