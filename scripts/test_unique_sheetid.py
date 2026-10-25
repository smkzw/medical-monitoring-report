#!/usr/bin/env python3
"""PR-8 regression: per-workbook unique sheet ids for same-name sheets (all data fictional).

Builds a tiny two-workbook study (EDC + central lab) where BOTH workbooks contain a sheet named
`LB`, then asserts the positive and negative properties of the unique-id scheme:

  positive: _source.json `sheets` holds two distinct keys `edc:LB` and `lab:LB`; queries raised on
            central-lab rows carry `sh`/`ev[0]` = `lab:LB`; qkeys are workbook-qualified and distinct.
  negative: source-check resolves `lab:LB` evidence rows against the LAB workbook only — the same
            row number in the EDC workbook is left empty, so any name-keyed (wrong-workbook)
            attribution would be reported as an empty source row (validate_contract exit 1).

Usage: python3 scripts/test_unique_sheetid.py [--keep]
Exit 0 on all assertions passing.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

HERE = Path(__file__).parent


def make_fixture(d: Path):
    edc = d / 'EDC.xlsx'
    lab = d / 'CentralLab.xlsx'
    w1 = openpyxl.Workbook()
    ws = w1.active
    ws.title = 'LB'
    ws.append(['受试者编号', '访视', '采样日期', '检查项', '结果', '单位', '临床意义评价'])
    ws.append(['SUBJID', 'VISIT', 'LBDAT', 'LBTEST', 'LBORRES', 'LBORRESU', 'LBCLSIG'])
    # EDC 本地 LB：行 3–4 留空（负向锚点：lab 证据行 3 若被错误归到 edc:LB → 空行被 source-check 报错），行 5 有正常值
    ws.append([None, None, None, None, None, None, None])
    ws.append([None, None, None, None, None, None, None])
    ws.append(['S001', 'W4', '2026-02-02', '丙氨酸氨基转移酶', 30, 'U/L', '正常'])
    dm = w1.create_sheet('DM')
    dm.append(['受试者编号', '首剂日期'])
    dm.append(['SUBJID', 'RFSTDAT'])
    dm.append(['S001', '2026-01-10'])
    w1.save(edc)

    w2 = openpyxl.Workbook()
    ws2 = w2.active
    ws2.title = 'LB'
    ws2.append(['受试者编号', '访视', '采样日期', '检查项', '结果', '单位', '临床意义评价'])
    ws2.append(['SUBJID', 'VISIT', 'LBDAT', 'LBTEST', 'LBORRES', 'LBORRESU', 'LBCLSIG'])
    # 中心实验室 LB：行 3 = CS 异常（同一受试者同一访视同一指标 → 应产生 CSX query，归属 lab:LB）
    ws2.append(['S001', 'W4', '2026-02-02', '丙氨酸氨基转移酶', 150, 'U/L', '异常有临床意义'])
    w2.save(lab)

    mapping = {
        'workbooks': {'edc': 'EDC.xlsx', 'lab': 'CentralLab.xlsx'},
        'label_row': 1, 'var_row': 2, 'data_start': 3,
        'domains': {
            'subjects': [{'wb': 'edc', 'sheet': 'DM', 'cols': {'sid': 'SUBJID', 'fd': 'RFSTDAT'}}],
            'findings': [
                {'wb': 'edc', 'sheet': 'LB', 'domain': 'lab', 'group': '本地实验室', 'layout': 'long', 'cols': {
                    'sid': 'SUBJID', 'visit': 'VISIT', 'date': 'LBDAT', 'test': 'LBTEST', 'value': 'LBORRES',
                    'unit': 'LBORRESU', 'clin': 'LBCLSIG'}},
                {'wb': 'lab', 'sheet': 'LB', 'domain': 'lab', 'group': '中心实验室', 'layout': 'long', 'cols': {
                    'sid': 'SUBJID', 'visit': 'VISIT', 'date': 'LBDAT', 'test': 'LBTEST', 'value': 'LBORRES',
                    'unit': 'LBORRESU', 'clin': 'LBCLSIG'}},
            ],
        },
    }
    (d / 'mapping.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding='utf-8')
    study = {
        'cfg': {
            'study': {'title': 'PR-8 unique sheet id 回归（虚构）', 'short': 'PR8-T', 'code': 'PR8-001'},
            'visits': {'order': ['W4']},
            'baselineRules': [{'match': '^lab:', 'method': 'lastPre', 'label': '首剂前最近值'}],
            'blind': {'on': False},
            'grading': {'system': 'CTCAE', 'version': '5.0'},
            'labGroups': {'LB': '实验室检查'},
            'footer': {'left': 'PR-8 回归夹具', 'right': '虚构数据'},
        },
        'analysis': {'population': 'dosed', 'aePeriod': {'ref': 'ld', 'days': 28}},
    }
    (d / 'study.json').write_text(json.dumps(study, ensure_ascii=False, indent=1), encoding='utf-8')
    return edc, lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true', help='keep the temp dir (debug)')
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix='pr8_')
    d = Path(tmp)
    make_fixture(d)
    fails = []

    def run(cmd):
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(d))
        if p.returncode != 0:
            fails.append(f"{' '.join(cmd[:3])} exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}")
        return p

    py = sys.executable
    run([py, str(HERE / 'normalize_listing.py'), 'mapping.json', '--out', 'work/norm'])
    src = json.loads((d / 'work/norm/_source.json').read_text(encoding='utf-8'))
    sheets = src.get('sheets') or {}
    by_name = src.get('sheets_by_name') or {}
    if set(sheets) != {'edc:LB', 'edc:DM', 'lab:LB'}:
        fails.append(f"positive: sheets keys 应为逐工作簿唯一 id，实得 {sorted(sheets)}")
    if sorted(by_name.get('LB') or []) != ['edc:LB', 'lab:LB']:
        fails.append(f"positive: sheets_by_name['LB'] 应列两个归属，实得 {by_name.get('LB')}")
    if sheets.get('lab:LB', {}).get('wb') != 'lab' or sheets.get('lab:LB', {}).get('sheet') != 'LB':
        fails.append("positive: lab:LB meta 应带 wb=lab 与 sheet=LB")
    # 记录级归属：中心实验室行带 wb=lab
    edc_lb = json.loads((d / 'work/norm/findings.json').read_text(encoding='utf-8'))
    lab_rows = [r for r in edc_lb if r.get('raw') == '150']
    if not lab_rows or lab_rows[0].get('wb') != 'lab' or lab_rows[0].get('sheet') != 'LB':
        fails.append(f"positive: 中心实验室 150 U/L 行应带 wb=lab，实得 {lab_rows[:1]}")

    run([py, str(HERE / 'build_site.py'), '--study', 'study.json', '--norm', 'work/norm', '--out', 'out/S'])
    vc = run([py, str(HERE / 'validate_contract.py'), 'out/S/HTML', '--source-check'])
    if 'FAIL' in vc.stdout:
        fails.append(f"negative: validate_contract --source-check 应通过（正确归属下 lab:LB 行非空），输出：\n{vc.stdout[-400:]}")
    KZ = json.loads((d / 'out/S/HTML/data/core.js').read_text(encoding='utf-8').split('=', 1)[1].rsplit(';', 1)[0])
    lab_q = [q for q in KZ.get('queries', []) if q.get('sid') == 'S001' and '150' in q.get('text', '')]
    if not lab_q:
        fails.append('positive: 中心实验室 CS 行应产生 query（150 U/L CS）')
    else:
        q = lab_q[0]
        if q.get('sh') != 'lab:LB':
            fails.append(f"positive: query sh 应为 lab:LB，实得 {q.get('sh')}")
        if not q.get('ev') or q['ev'][0][0] != 'lab:LB':
            fails.append(f"positive: query ev[0][0] 应为 lab:LB，实得 {q.get('ev')}")
        if not str(q.get('qkey', '')).startswith('lab|S001|') or 'lab:LB' not in q.get('qkey', ''):
            fails.append(f"positive: qkey 应含 lab:LB 限定，实得 {q.get('qkey')}")
    # 负向（错归属即失败）：把该 query 的 ev 改指 edc:LB（同名 sheet 的另一工作簿行 4＝空行）→ source-check 必须报错
    if lab_q:
        qfile = d / 'out/S/analysis/queries.json'
        qs = json.loads(qfile.read_text(encoding='utf-8'))
        for q in qs:
            if q.get('sid') == 'S001' and '150' in q.get('text', ''):
                q['ev'] = [['edc:LB', q['ev'][0][1]] + list(q['ev'][0][2:])] if q.get('ev') else q['ev']
        qfile.write_text(json.dumps(qs, ensure_ascii=False), encoding='utf-8')
        # core.js 同步（validate 读 core.js）
        core = d / 'out/S/HTML/data/core.js'
        for q in KZ['queries']:
            if q.get('sid') == 'S001' and '150' in q.get('text', '') and q.get('ev'):
                q['ev'][0][0] = 'edc:LB'
        core.write_text('window.KZ = ' + json.dumps(KZ, ensure_ascii=False, separators=(',', ':'), default=str) + ';', encoding='utf-8')
        vc2 = subprocess.run([py, str(HERE / 'validate_contract.py'), 'out/S/HTML', '--source-check'],
                             capture_output=True, text=True, cwd=str(d))
        if vc2.returncode == 0 or 'is empty' not in vc2.stdout:
            fails.append(f"negative: 证据错归属到 edc:LB 空行应被 source-check 报错，实得 rc={vc2.returncode}：\n{vc2.stdout[-400:]}")

    print('\n'.join(fails) if fails else 'OK: unique sheet id 正向/负向断言全部通过（虚构数据）')
    if not a.keep:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
