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
    kr = KZ.get('kri')                                      # V5：KRI / 研究层面容忍限度
    if kr is None:
        WARN.append('KZ.kri missing (pre-V5 build: KRI / 容忍限度 / 中心画像 KRI 不显示)')
    elif not (isinstance(kr, dict) and isinstance(kr.get('defs'), list) and isinstance(kr.get('study'), dict) and isinstance(kr.get('sites'), dict)):
        ERR.append('KZ.kri should be {defs:list, study:dict, sites:dict}')
    else:
        keys = {d.get('k') for d in kr['defs']}
        for df in kr['defs']:
            if df.get('qtl') is not None and (not isinstance(df['qtl'], list) or len(df['qtl']) != 3):
                ERR.append(f"KZ.kri.defs {df.get('k')}: qtl should be [严格, 标准, 宽松]")
        for scope in [kr['study']] + list(kr['sites'].values()):
            bad = [k for k, v in scope.items() if k not in keys or not (isinstance(v, list) and len(v) == 2)]
            if bad:
                ERR.append(f'KZ.kri value {bad[0]} should be [分子, 分母] of a defined KRI')
                break
    for row in (KZ.get('ops') or {}).get('due') or []:
        if len(row) != 12:
            ERR.append(f'ops.due row has {len(row)} fields (expected 12: …, EDC 记为未进行 0/1)')
            break
    if 'cred' in KZ and not isinstance((KZ['cred'] or {}).get('sites'), dict):
        ERR.append('KZ.cred.sites should be dict')
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
        WARN.append('KZX.soa missing (方案偏离 SoA 完成度为空)')
    # mm4 方案偏离数据面：分类/分级/状态合法、参与者存在、证据 sheet 可回查、信号回链有效
    P = KZ.get('pd')
    if P:
        tax = {x[0] for x in P.get('taxonomy') or []}
        sids = {s[0] for s in KZ.get('subs', [])}
        ids = [x.get('id') for x in (P.get('potential') or []) + (P.get('confirmed') or [])]
        if len(ids) != len(set(ids)):
            ERR.append('KZ.pd: duplicate ids')
        for x in P.get('potential') or []:
            if x.get('cat') not in tax:
                ERR.append(f"pd {x.get('id')}: unknown category {x.get('cat')}")
            if x.get('grade') not in ('重要', '一般', '待判定'):
                ERR.append(f"pd {x.get('id')}: bad grade {x.get('grade')}")
            if x.get('sid') not in sids:
                ERR.append(f"pd {x.get('id')}: unknown subject {x.get('sid')}")
            if x.get('status') not in ('已记录', '未见记录', '无 PD 记录可比对'):
                ERR.append(f"pd {x.get('id')}: bad status {x.get('status')}")
            sig = x.get('sig')
            if sig:
                coll = KZ.get('others' if sig[0] == 'oth' else 'labrows') or []
                if not (isinstance(sig[1], int) and sig[1] < len(coll) and coll[sig[1]].get('pdId') == x.get('id')):
                    ERR.append(f"pd {x.get('id')}: signal back-link broken {sig[:2]}")
            for e in x.get('src') or []:
                if e and e[0] and sheets and e[0] not in sheets and e[0] not in ((run.get('source') or {}).get('sheets_by_name') or {}):
                    WARN.append(f"pd {x.get('id')}: evidence sheet {e[0]} not in _source sheets")
        for x in P.get('confirmed') or []:
            if x.get('cat') not in tax:
                ERR.append(f"pd {x.get('id')}: unknown category {x.get('cat')}")
        if KZX is not None and P.get('potential') and 'pdex' not in KZX:
            WARN.append('KZX.pdex missing (方案偏离抽屉无源行原文)')
    if KZ.get('cfg', {}).get('blind', {}).get('on'):
        blob = json.dumps({k: KZ.get(k) for k in ('subs', 'aes', 'eff')}, ensure_ascii=False)
        if re.search(r'"(arm|ARM|trt|TRT01P|ACTARM)"', blob):
            ERR.append('blind.on but arm/treatment fields present in KZ')
        if any(s[20] for s in KZ.get('subs', []) if len(s) > 20):
            WARN.append('blind.on but subs[].grp populated — make sure it is not the randomised arm')
    if a.source_check and sheets:
        # 批量核验：按（工作簿, sheet）聚合所需行号，每 sheet 单次顺序扫描。
        # 大研究（如 500 参与者/10 万行、数千 query）下 O(行数) 取代 O(query×行数) 的逐条
        # iter_rows(min_row=row) 重扫（read_only 模式每次都要从头解析 XML 流）。
        import openpyxl
        need = {}
        for q in KZ.get('queries', []):
            for ev in q.get('ev', []):
                sh, row = ev[0], ev[1]
                meta = sheets.get(sh)
                if not meta or not row:
                    continue
                path = run['source']['workbooks'][meta['wb']]
                # PR-8: `sheets` keyed by unique 'wb:sheet' id — the plain sheet name is meta['sheet']
                need.setdefault((path, meta.get('sheet') or sh), {}).setdefault(int(row), []).append(q['id'])
        wbs = {}
        for (path, sh), rows in need.items():
            wb = wbs.setdefault(path, openpyxl.load_workbook(path, read_only=True, data_only=True))
            pending = dict(rows)
            for r_idx, cells in enumerate(wb[sh].iter_rows(values_only=True), start=1):
                if not pending:
                    break
                hit = pending.pop(r_idx, None)
                if hit and not any(v not in (None, '') for v in cells):
                    for qid in hit:
                        ERR.append(f"query {qid}: source {sh} row {r_idx} is empty")
            for r_idx, qids in pending.items():
                # 引用行超出 sheet 实际范围：与逐行 iter_rows 的空行口径一致（ERROR）
                for qid in qids:
                    ERR.append(f"query {qid}: source {sh} row {r_idx} is empty")
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
