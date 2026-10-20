#!/usr/bin/env python3
"""Validate a built report against the front-end data contract (references/data-contract.md).

python3 validate_contract.py out/site/HTML [--source-check]

Checks: required globals/keys and types in data/core.js, trend.js, extra.js, per-subject files; every subject in KZ.subs has
data/s/<sid>.js; query ids unique, evidence rows [sheet,row,...] point to sheets recorded in _source meta (and, with
--source-check, to real non-empty rows of the source workbook); labrows/others reference known subjects; blinding guard
(no arm/treatment columns leaked when cfg.blind.on). Exit 1 on any ERROR.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ERR, WARN = [], []


def load_js(p, var):
    if not Path(p).exists():
        ERR.append(f'{Path(p).name} missing')
        return None
    t = Path(p).read_text(encoding='utf-8')
    m = re.search(r'window\.' + var + r'\s*=\s*', t)
    if not m:
        ERR.append(f'{p.name}: window.{var} not found')
        return None
    body = t[m.end():].strip().rstrip(';')
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        ERR.append(f'{p.name}: JSON parse error {e}')
        return None


REQ_KZ = {'cfg': dict, 'meta': dict, 'subs': list, 'centers': list, 'aes': list, 'aesum': dict, 'labrows': list, 'others': list,
          'queries': list, 'cro': list, 'cons': list, 'rules': list, 'methods': list, 'eff': dict, 'study': dict, 'review': list, 'todo': list}
REQ_CFG = ['study', 'visits', 'baseline']
Q_KEYS = ['id', 'sid', 'cat', 'sh', 'text', 'parts', 'ev', 'cro']
LR_KEYS = ['sid', 'test', 'risk', 'pts', 'rel', 'ctx', 'q']
OT_KEYS = ['sid', 'cat', 'pr', 'sum', 'sh', 'row', 'q']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html')
    ap.add_argument('--source-check', action='store_true')
    a = ap.parse_args()
    d = Path(a.html) / 'data'
    KZ = load_js(d / 'core.js', 'KZ')
    KZT = load_js(d / 'trend.js', 'KZT')
    KZX = load_js(d / 'extra.js', 'KZX')
    KZG = load_js(d / 'grading.js', 'KZG')
    if KZ is None:
        return finish()
    if KZG is not None:
        for k in ('label', 'items', 'map'):
            if k not in KZG:
                ERR.append(f'KZG.{k} missing')
        lab = KZ.get('cfg', {}).get('ctcaeVersion')
        if lab and KZG.get('label') and lab != KZG['label']:
            ERR.append(f"cfg.ctcaeVersion ({lab}) != KZG.label ({KZG['label']})")
        for mid, code in (KZG.get('map') or {}).items():
            if code and code not in (KZG.get('items') or {}):
                ERR.append(f'KZG.map {mid} → {code} not in grading table')
    for k, t in REQ_KZ.items():
        if k not in KZ:
            ERR.append(f'KZ.{k} missing')
        elif not isinstance(KZ[k], t):
            ERR.append(f'KZ.{k} should be {t.__name__}')
    for k in REQ_CFG:
        if k not in KZ.get('cfg', {}):
            WARN.append(f'cfg.{k} missing (front-end falls back to defaults)')
    sids = {s[0] for s in KZ.get('subs', [])}
    for s in KZ.get('subs', []):
        if len(s) < 21:
            ERR.append(f'subs row {s[0]} has {len(s)} fields (<21, see K.SUBF)')
        if not (d / 's' / f'{s[0]}.js').exists():
            ERR.append(f'subject file data/s/{s[0]}.js missing')
    ids = [q.get('id') for q in KZ.get('queries', [])]
    if len(ids) != len(set(ids)):
        ERR.append('duplicate query ids')
    run = {}
    rp = Path(a.html).parent / 'analysis' / 'run.json'
    if rp.exists():
        run = json.loads(rp.read_text(encoding='utf-8'))
    sheets = (run.get('source') or {}).get('sheets', {})
    for q in KZ.get('queries', []):
        miss = [k for k in Q_KEYS if k not in q]
        if miss:
            ERR.append(f"query {q.get('id')}: missing {miss}")
        if q.get('sid') not in sids:
            ERR.append(f"query {q.get('id')}: unknown subject {q.get('sid')}")
        for ev in q.get('ev', []):
            if not isinstance(ev, list) or len(ev) < 2:
                ERR.append(f"query {q.get('id')}: bad ev {ev}")
            elif sheets and ev[0] not in sheets:
                WARN.append(f"query {q.get('id')}: ev sheet {ev[0]} not in _source sheets")
        if not str(q.get('text', '')).strip():
            ERR.append(f"query {q.get('id')}: empty text")
        if re.search(r'None|nan|undefined|\{\w+\}', str(q.get('text', ''))):
            ERR.append(f"query {q.get('id')}: unresolved placeholder/None in text")
    for g in KZ.get('labrows', []):
        miss = [k for k in LR_KEYS if k not in g]
        if miss:
            ERR.append(f"labrow {g.get('sid')}/{g.get('test')}: missing {miss}")
    for o in KZ.get('others', []):
        miss = [k for k in OT_KEYS if k not in o]
        if miss:
            ERR.append(f"other {o.get('sid')}/{o.get('cat')}: missing {miss}")
    qids = set(ids)
    for coll in ('labrows', 'others'):
        for x in KZ.get(coll, []):
            for qid in x.get('q', []):
                if qid not in qids:
                    ERR.append(f'{coll} {x.get("sid")} references unknown query {qid}')
    if KZT:
        for m in KZT.get('metrics', []):
            if m['id'] not in KZT.get('obs', {}):
                ERR.append(f"KZT.obs missing metric {m['id']}")
    if KZX is not None and 'soa' not in KZX:
        WARN.append('KZX.soa missing (研究依据 SoA heatmap empty)')
    if KZ.get('cfg', {}).get('blind', {}).get('on'):
        blob = json.dumps({k: KZ.get(k) for k in ('subs', 'aes', 'eff')}, ensure_ascii=False)
        if re.search(r'"(arm|ARM|trt|TRT01P|ACTARM)"', blob):
            ERR.append('blind.on but arm/treatment fields present in KZ')
        if any(s[20] for s in KZ.get('subs', []) if len(s) > 20):
            WARN.append('blind.on but subs[].grp populated — make sure it is not the randomised arm')
    if a.source_check and sheets:
        import openpyxl
        wbs = {}
        for q in KZ.get('queries', []):
            for ev in q.get('ev', []):
                sh, row = ev[0], ev[1]
                meta = sheets.get(sh)
                if not meta or not row:
                    continue
                path = run['source']['workbooks'][meta['wb']]
                wb = wbs.setdefault(path, openpyxl.load_workbook(path, read_only=True, data_only=True))
                vals = [c.value for c in next(wb[sh].iter_rows(min_row=row, max_row=row))]
                if not any(v not in (None, '') for v in vals):
                    ERR.append(f"query {q['id']}: source {sh} row {row} is empty")
    return finish(KZ)


def finish(KZ=None):
    for w in WARN:
        print('WARN ', w)
    for e in ERR:
        print('ERROR', e)
    if KZ:
        print(f"subjects {len(KZ['subs'])} · queries {len(KZ['queries'])} · labrows {len(KZ['labrows'])} · others {len(KZ['others'])}")
    print('FAIL' if ERR else 'OK', f'({len(ERR)} errors, {len(WARN)} warnings)')
    sys.exit(1 if ERR else 0)


if __name__ == '__main__':
    main()
