#!/usr/bin/env python3
"""Import / cross-check grading tables against the official NCI CTCAE Excel.

  python3 scripts/ctcae_import.py CTCAE_v5.0.xlsx --out work/ctcae_v5.0_terms.json
  python3 scripts/ctcae_import.py CTCAE_v5.0.xlsx --check scripts/grading/ctcae_v5.0.json [--report work/ctcae_check.md]

The official workbook (one row per CTCAE term) has columns like: MedDRA Code | MedDRA SOC | CTCAE Term | Grade 1 … Grade 5 |
Definition. Header names are matched loosely, so v4.03 / v5.0 / v6.0 files all work.

--check: for every criterion term used in the machine table, find the official term and verify that each numeric threshold of
the machine table appears in the official text of the same grade (in the table's standard unit, or as a ×ULN / ×baseline
multiple). Anything that cannot be confirmed is listed for manual review. Numeric extraction is heuristic: a "not confirmed"
line means "look at it", not "wrong". Symptom/intervention-based grades are never auto-graded and are only shown for reference.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import openpyxl


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def read_official(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:15]) if any(re.search(r'CTCAE\s*Term', norm(c), re.I) for c in r)), None)
        if hi is None:
            continue
        H = [norm(c) for c in rows[hi]]
        col = lambda rx: next((i for i, h in enumerate(H) if re.search(rx, h, re.I)), None)
        ct, soc, code, dfn = col(r'CTCAE\s*Term'), col(r'SOC'), col(r'MedDRA\s*Code|^Code'), col(r'Definition')
        gcols = {g: col(rf'^Grade\s*{g}\b') for g in range(1, 6)}
        for r in rows[hi + 1:]:
            t = norm(r[ct]) if ct is not None and ct < len(r) else ''
            if not t:
                continue
            out[t.lower()] = {'term': t, 'soc': norm(r[soc]) if soc is not None else '', 'meddra': norm(r[code]) if code is not None else '',
                              'grades': {g: norm(r[c]).replace('\u2013', '-') for g, c in gcols.items() if c is not None and c < len(r) and norm(r[c]) not in ('', '-')},
                              'definition': norm(r[dfn]) if dfn is not None else ''}
    return out


NUM = re.compile(r'(?<![A-Za-z])(\d+(?:\.\d+)?)')


def nums(text):
    return {float(x) for x in NUM.findall(text.replace(',', ''))}


def check(off, table):
    lines, ok, bad, miss = [], 0, 0, 0
    units = table.get('units', {})
    for code, crits in table['items'].items():
        for c in crits:
            o = off.get(c['term'].lower())
            if not o:
                miss += 1
                lines.append(f"- ❓ {code} · {c['term']}：官方文件中未找到该术语（版本差异或拼写）")
                continue
            facs = [1.0] + [1 / f for u, f in (units.get(code) or {}).items() if u != '_std' and f]
            for s in c['steps']:
                v = s['v']
                if not isinstance(v, (int, float)):
                    continue
                txt = o['grades'].get(s['g']) or o['grades'].get(str(s['g'])) or ''
                ns = nums(txt)
                good = any(abs(n - v * f) <= max(0.051, abs(v * f) * 0.011) for n in ns for f in facs) or \
                    (v == 1 and ((s['by'] == 'xuln' and 'ULN' in txt) or (s['by'] == 'xlln' and 'LLN' in txt) or (s['by'] == 'xbase' and 'baseline' in txt.lower())))
                if good:
                    ok += 1
                else:
                    bad += 1
                    lines.append(f"- ⚠️ {code} · {c['term']} · G{s['g']} 机器表 {s['by']} {s['op']} {v}；官方原文：{txt or '（该级无文本）'}")
    head = f"# 分级表核对：{table.get('label')}\n\n- 已确认阈值 {ok} · 未确认 {bad} · 未找到术语 {miss}\n- 未确认 ≠ 错误：请对照官方原文人工判断（单位、区间端点、症状条件）。\n\n"
    return head + '\n'.join(lines) + '\n', bad + miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsx')
    ap.add_argument('--out')
    ap.add_argument('--check')
    ap.add_argument('--report')
    a = ap.parse_args()
    off = read_official(a.xlsx)
    if not off:
        sys.exit('未在工作簿中找到含 “CTCAE Term” 表头的工作表')
    print(f'official terms: {len(off)}')
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(list(off.values()), ensure_ascii=False, indent=1), encoding='utf-8')
        print('written', a.out)
    if a.check:
        rep, n = check(off, json.loads(Path(a.check).read_text(encoding='utf-8')))
        if a.report:
            Path(a.report).write_text(rep, encoding='utf-8')
            print('report', a.report)
        else:
            print(rep)
        print(f'items needing manual review: {n}')


if __name__ == '__main__':
    main()
