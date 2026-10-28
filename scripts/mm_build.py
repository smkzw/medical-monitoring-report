#!/usr/bin/env python3
"""Medical-monitoring analysis engine: tidy tables (normalize_listing.py) + study.json → front-end data contract.

Usage: python3 mm_build.py --study work/study.json --norm work/norm --out out/site/data

Outputs  data/core.js  (window.KZ)   data/trend.js (window.KZT)   data/extra.js (window.KZX)   data/s/<sid>.js (KZ_SUB)
         ../../analysis/*.json  (labrows/others/queries … for audit and for export_queries.py)
See references/data-contract.md for every field, references/analysis-rules.md for the rules implemented here.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ctcae
import ext_rules
import pd_rules
from common import days, dump_json, fmt, is_full_date, load_json, quantile, study_day, zero_dose

AGG_EXCL = set()


# ----------------------------------------------------------------------------- helpers
def js_write(path, var, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(f'window.{var}=' + json.dumps(obj, ensure_ascii=False, separators=(',', ':'), default=str) + ';', encoding='utf-8')


def grade_int(g):
    if g is None:
        return None
    m = re.search(r'\d', str(g))
    return int(m.group()) if m else None


def gtxt(g):
    gi = grade_int(g)
    return f'{gi}级' if gi is not None else (str(g) if g else '—')


def rx(p):
    return re.compile(p) if p else None


def deviation(v, lo, hi):
    """偏离参考范围的比例（T_dev 口径）：高于上限 (x−ULN)/ULN，低于下限 (LLN−x)/LLN；
    范围内 = 0.0；无值或无范围 = None。与工作台问数据引擎同口径（mm3/ask/dataset.py deviation）。"""
    if v is None or (lo is None and hi is None):
        return None
    if hi is not None and v > hi:
        return (v - hi) / abs(hi) if hi else None
    if lo is not None and v < lo:
        return (lo - v) / abs(lo) if lo else None
    return 0.0


def sheet_meta(C, sheet):
    """PR-8: resolve sheet meta from the unique per-workbook id ('wb:sheet' key of normalize _source.json
    sheets) or a plain sheet name (deterministic first owning id in _source order). {} when unknown."""
    sheets = C.src.get('sheets') or {}
    if sheet in sheets:
        return sheets[sheet]
    for m in sheets.values():
        if m.get('sheet') == sheet:
            return m
    return {}


def wb_sheet(C, sheet):
    """Workbook-qualified sheet name (business-key scope): same-name sheets in different workbooks stay distinct.
    PR-8: accepts a unique id ('wb:sheet') or a plain sheet name (resolved via sheet_meta)."""
    sheet = str(sheet or '')
    if not sheet:
        return ''
    m = sheet_meta(C, sheet)
    return f"{m['wb']}:{m['sheet']}" if m.get('wb') else sheet


def oth_qkey(C, sid, cat, sh, v, d, test, rel, rule, bkey=None):
    """Business key of a rule signal (PR-2): rule id + workbook-qualified form + record business key.
    Row numbers and raw values never enter the key: a row drift or a value edit keeps the identity.
    Record key preference: explicit bkey > linked record number (AE/CM, fallback term+start) >
    metric+visit+date (finding-based rules) > visit/date (form-level checks)."""
    rid = (rule or {}).get('id') or cat
    if bkey:
        rec = str(bkey)
    elif rel:
        l0 = rel[0]
        rec = f"{l0[0]}:{l0[3]}" if l0[3] not in (None, '') else f"{l0[1]}|{l0[2]}"
    elif test and (v or d):
        rec = f"{test}|{v or ''}|{d or ''}"
    else:
        rec = f"{v or ''}|{d or ''}"
    return f"oth|{sid}|{rid}|{wb_sheet(C, sh)}|{rec}"


def cmp(op, a, b):
    if a is None or b is None:
        return False
    return {'>=': a >= b, '>': a > b, '<=': a <= b, '<': a < b, '==': a == b}.get(op, False)


def _num(v):
    try:
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def fill(tpl, **kw):
    def rep(m):
        v = kw.get(m.group(1))
        return '' if v is None else (fmt(v) if isinstance(v, float) else str(v))
    return re.sub(r'\{(\w+)\}', rep, tpl)


class Ctx:
    pass


# ----------------------------------------------------------------------------- load
def load(study_p, norm_p):
    C = Ctx()
    C.S = load_json(study_p)
    C.dir = Path(study_p).parent
    for k in ('rules', 'methods', 'review', 'queries_manual', 'ibtag', 'study', 'unres', 'todo'):
        if isinstance(C.S.get(k), str):  # allow "rules": "rules.json"
            C.S[k] = load_json(C.dir / C.S[k], [])
    C.cfg = C.S.setdefault('cfg', {})
    C.A = C.S.get('analysis', {})
    # 双阈值（T_dev/T_base，PR-4）：默认 30%/30%，per_metric 覆盖默认为空；血压同为 30%（D18）
    TH = C.cfg.get('thresholds') or {}
    TH.setdefault('dev', 0.3); TH.setdefault('base', 0.3); TH.setdefault('per_metric', {})
    C.cfg['thresholds'] = TH
    ext_rules.set_metric_dir(C.A.get('metricDir'))   # 指标不利方向：项目配置优先，其次医学常识默认表
    C.mdir = C.A.get('metricDir') or {}        # {metricRe: 'up'|'down'} 单向不利指标（方法卡计数用）
    C.mthr = C.A.get('metricThreshold') or []  # 项目收紧：有效值=min(所选,收紧值)，两参数各自（须带方案/IB 原文）
    C.G = ctcae.load(C.cfg, C.dir)  # grading system/version from the protocol (cfg.grading or cfg.ctcaeVersion) — never defaulted
    C.cfg['ctcaeVersion'] = C.G.label
    C.GL = C.G.label
    N = Path(norm_p)
    C.src = load_json(N / '_source.json', {})
    for dom in ('subjects', 'visits', 'exposure', 'ae', 'mh', 'cm', 'proc', 'findings', 'efficacy', 'pd', 'extq', 'groups',
                'icf', 'sample', 'dispense'):   # mm4：知情同意记录 / 样本采集 / 发药回收（可选域，PD 执行层面核查用）
        setattr(C, dom, load_json(N / f'{dom}.json', []) or [])
    # 表单中文名：EDC 目录页 ＜ study.json analysis.formNames；分组名缺省（等于表单代码）时用中文名，避免页面出现「OTH」
    C.A['formNames'] = {**(C.src.get('formNames') or {}), **(C.A.get('formNames') or {})}
    for f in C.findings:
        if f.get('sheet') in C.A['formNames'] and f.get('group') in (None, '', f.get('sheet')):
            f['group'] = C.A['formNames'][f['sheet']]
    align_visit_codes(C)
    vis = C.cfg.setdefault('visits', {})
    C.VIS = vis.get('order') or sorted({f['visit'] for f in C.findings if f.get('visit')})
    vis['order'] = C.VIS
    C.UNS = set(vis.get('unsched', ['USV']))
    C.ET = set(vis.get('early', ['ET']))
    C.isAgg = lambda v: v not in C.UNS and v not in C.ET
    C.vi = lambda v: C.VIS.index(v) if v in C.VIS else len(C.VIS)
    return C


def _vkey(code):
    return frozenset(re.findall(r'[A-Z]+\d+', str(code or '').upper()))


_VCLASS = [re.compile(r'筛选|screen|^SCR$|^[WD]\s*-\s*\d', re.I), re.compile(r'提前|退出|^ET$|early', re.I),
           re.compile(r'计划外|^USV$|unsched', re.I)]


def align_visit_codes(C):
    """mm4：方案写「V6/W4/D29」、EDC 导出写「W4/D29V6」——同一组访视标记（字母＋数字）视为同一访视，把配置里的访视代码改写成
    listing 实际写法（visitWindows、visits.order/d1/unsched/early、soa、pd 关键访视与顺序规则）。只在 listing 中恰有一个同组标记时改写。"""
    L = {r.get('visit') for dom in ('visits', 'findings', 'efficacy', 'exposure') for r in getattr(C, dom) if r.get('visit')}
    by = defaultdict(set)
    for v in L:
        if _vkey(v):
            by[_vkey(v)].add(v)
    amap = {}

    def m(c):
        if c in L or not isinstance(c, str):
            return c
        k = _vkey(c)
        hit = by.get(k) or {v for kk, vs in by.items() if k and k < kk for v in vs}   # 精确同组，其次唯一的超集（V9/W18 ↔ W18/D127V9）
        if k and len(hit) == 1:
            amap[c] = next(iter(hit))
            return amap[c]
        for rx in _VCLASS:                                # 再按访视类别（筛选 / 提前退出 / 计划外）唯一匹配：「W-4~W-1」↔ SCR
            if rx.search(c):
                hit = {v for v in L if rx.search(v)}
                if len(hit) == 1:
                    amap[c] = next(iter(hit))
                    return amap[c]
        return c
    vis = C.cfg.get('visits') or {}
    for k in ('order', 'unsched', 'early'):
        if isinstance(vis.get(k), list):
            vis[k] = [m(x) for x in vis[k]]
    if vis.get('d1'):
        vis['d1'] = m(vis['d1'])
    if isinstance(vis.get('labels'), dict):
        vis['labels'] = {m(k): v for k, v in vis['labels'].items()}
    if isinstance(C.A.get('visitWindows'), dict):
        C.A['visitWindows'] = {m(k): v for k, v in C.A['visitWindows'].items()}
    for s in C.A.get('soa') or []:
        s['visits'] = [m(x) for x in s.get('visits') or []]
    P = C.A.get('pd') or {}
    if P.get('criticalVisits'):
        P['criticalVisits'] = [m(x) for x in P['criticalVisits']]
    for o in P.get('order') or []:
        if o.get('visits'):
            o['visits'] = [m(x) for x in o['visits']]
    for x in (P.get('sample') or {}).get('windows') or []:
        x['visit'] = m(x.get('visit'))
    C.visitAlias = amap


# ----------------------------------------------------------------------------- subjects
def build_subjects(C):
    groups = {g['sid']: g for g in C.groups}
    ex = defaultdict(list)
    for e in C.exposure:
        ex[e['sid']].append(e)
    lastobs = defaultdict(str)
    for dom in ('visits', 'exposure', 'ae', 'findings', 'efficacy', 'cm'):
        for r in getattr(C, dom):
            for k in ('date', 'start', 'end'):
                d = r.get(k)
                if is_full_date(d) and d > lastobs[r['sid']]:
                    lastobs[r['sid']] = d
    C.subj = {}
    for s in sorted(C.subjects, key=lambda x: x['sid']):
        sid = s['sid']
        e = sorted([x for x in ex[sid] if is_full_date(x.get('start')) and not zero_dose(x)], key=lambda x: x['start'])   # 0 剂量区间不算首/末次给药
        fd = e[0]['start'] if e else s.get('fd')
        ld = max([x.get('end') or x['start'] for x in e if is_full_date(x.get('end') or x['start'])], default=None) if e else s.get('ld')
        st = s.get('status')
        if not st:
            st = '筛选失败' if not fd and not s.get('rand') else ('完成试验' if str(s.get('eos_done')) in ('是', 'Y') else
                                                                 '提前退出' if s.get('eos_d') else '治疗结束' if s.get('eot_d') else '已入组')
        g = groups.get(sid, {})
        C.subj[sid] = dict(s, fd=fd, ld=ld, status=st, lo=lastobs.get(sid) or ld or fd,
                           strat=s.get('strat') or g.get('strat'), grp=s.get('grp') or g.get('grp'),
                           site=str(s.get('site') or sid[:2]), center=s.get('center') or '')
    def _end(spec):  # {"ref": "ld"|"fd"|"lo"|"eos_d", "days": N} → last date of the window (None = open)
        if not spec:
            return {}
        out = {}
        for sid, s in C.subj.items():
            ref = spec.get('ref', 'ld')
            # mm4：锚点为研究结束（eos_d）而受试者仍在研 → 收集期尚未结束（开放），不回退到末次给药
            r = s.get(ref) if ref == 'eos_d' else (s.get(ref) or s.get('ld') or s.get('fd'))
            out[sid] = (dt.date.fromisoformat(r) + dt.timedelta(days=spec.get('days', 0))).isoformat() if is_full_date(r) else None
        return out
    C.aeEnd = _end(C.A.get('aePeriod'))     # protocol AE-collection period end (findings after it do not generate missed-AE queries)
    C.teEnd = _end(C.A.get('teae'))         # TEAE definition: onset ≥ first dose and ≤ ref + days
    pop = C.A.get('population', 'dosed')  # dosed | randomized | all
    C.dosed = {sid for sid, s in C.subj.items() if s['fd']}
    C.pop = C.dosed if pop == 'dosed' else ({sid for sid, s in C.subj.items() if s.get('rand') or s['fd']} if pop == 'randomized' else set(C.subj))
    if C.cfg.get('blind', {}).get('on'):
        for s in C.subj.values():
            s['grp'] = None  # never ship arm assignment in a blinded build


def is_post(C, sid, date, tpt=None):
    fd = C.subj.get(sid, {}).get('fd')
    if not fd or not is_full_date(date):
        return False
    if date > fd:
        return True
    if date == fd and tpt and re.search(C.A.get('postTptRe', '后'), str(tpt)):
        return True
    return False


# ----------------------------------------------------------------------------- AE / MH / CM
def build_events(C):
    relre = rx(C.A.get('relatedRe', r'肯定|很可能|^可能有关|可能相关|related'))
    unrel = rx(C.A.get('unrelatedRe', r'无关|不相关|可能无关|unrelated'))
    catmap = [(re.compile(a), b) for a, b in C.A.get('aeCatMap', [])]
    C.aesiDefs = [dict(d, _t=rx(d.get('terms')), _soc=rx(d.get('soc'))) for d in (C.A.get('aesi') or [])]
    if C.A.get('aesiTermRe'):
        C.aesiDefs.append({'id': 'AESI', 'name': 'AESI', '_t': rx(C.A['aesiTermRe']), '_soc': None})
    C.ae_by = defaultdict(list)
    C.aes = []
    for a in sorted(C.ae, key=lambda x: (x['sid'], x.get('start') or '', str(x.get('no') or ''))):
        sid = a['sid']
        if sid not in C.subj:
            continue
        s = C.subj[sid]
        term = a.get('term') or ''
        txt = ' '.join(str(a.get(k) or '') for k in ('term', 'pt', 'llt'))  # verbatim + MedDRA PT/LLT when mapped
        cat = a.get('cat')
        if not cat:
            cat = next((b for p, b in catmap if p.search(txt)), None) or a.get('soc') or term
        gi = grade_int(gtxt(a.get('grade'))) or 0
        aesi_hit = [d.get('name') or d.get('id') for d in C.aesiDefs if (d['_t'] and d['_t'].search(txt)) or (d['_soc'] and d['_soc'].search(str(a.get('soc') or '')))
                    if gi >= d.get('minGrade', 0)]
        rel = a.get('rel') or ''
        related = bool(relre and relre.search(rel)) and not (unrel and unrel.search(rel))
        rec = {'n': a.get('no') or len(C.ae_by[sid]) + 1, 't': term, 'c': cat, 's': a.get('start') or '', 'e': a.get('end') or '',
               'g': gtxt(a.get('grade')), 'sae': bool(a.get('serious')), 'aesi': bool(a.get('aesi')),
               'dili': bool(a.get('dili')), 'rel': rel or '—', 'act': a.get('action') or '—', 'out': a.get('outcome') or '—',
               'cm': a.get('cm') or '', 'wd': a.get('withdraw') or '', 'row': a['row'], 'sh': a['sheet'], 'wb': a.get('wb') or '', 'sid': sid, 'site': s['site'], 'fd': s['fd'] or '',
               'pre': bool(s['fd'] and is_full_date(a.get('start')) and a['start'] < s['fd']), '_rel': related,
               '_aesi_term': bool(aesi_hit), '_aesi_def': aesi_hit, 'pt': a.get('pt') or '', 'soc': a.get('soc') or '',
               'rpt': a.get('rpt') or '', 'aware': a.get('aware') or ''}
        rec['te'] = (not rec['pre']) and bool(s['fd']) and (not C.teEnd.get(sid) or not is_full_date(rec['s']) or rec['s'] <= C.teEnd[sid])
        rec['ib'] = ib_match(C, rec)
        C.ae_by[sid].append(rec)
        C.aes.append(rec)
    C.mh_by = defaultdict(list)
    for m in C.mh:
        C.mh_by[m['sid']].append({'n': m.get('no') or len(C.mh_by[m['sid']]) + 1, 't': m.get('term') or '', 's': m.get('start') or '',
                                  'e': m.get('end') or '', 'ong': '是' if m.get('ongoing') else '否', 'row': m['row'], 'sh': m['sheet'], 'wb': m.get('wb') or ''})
    C.cm_by = defaultdict(list)
    for c in C.cm:
        ind = c.get('indication') or ''
        wk = c.get('ind_kind') or ('AE' if re.search(r'^AE|不良事件', ind) else 'MH' if re.search(r'^MH|病史', ind) else '')
        C.cm_by[c['sid']].append({'n': c.get('no') or len(C.cm_by[c['sid']]) + 1, 't': c.get('term') or '', 's': c.get('start') or '',
                                  'e': c.get('end') or '', 'ong': bool(c.get('ongoing')), 'dose': c.get('dose') or '', 'fq': c.get('freq') or '',
                                  'rt': c.get('route') or '', 'why': ind, 'wk': wk, 'row': c['row'], 'sh': c['sheet'], 'wb': c.get('wb') or '', 'f': '',
                                  'aeno': str(c.get('aeno') or '')})


def ae_summary(C):
    post = [a for a in C.aes if a['sid'] in C.pop and a['te']]
    cats = defaultdict(lambda: {'n': 0, 's': set(), 'g2': 0, 'rel': 0, 'aesi': 0, 'terms': Counter()})
    for a in post:
        c = cats[a['c']]
        c['n'] += 1
        c['s'].add(a['sid'])
        c['g2'] += (grade_int(a['g']) or 0) >= 2
        c['rel'] += a['_rel']
        c['aesi'] += a['aesi']
        c['terms'][a['t']] += 1
    C.aesum = {k: {'n': v['n'], 's': len(v['s']), 'g2': v['g2'], 'rel': v['rel'], 'aesi': v['aesi'], 'terms': [t for t, _ in v['terms'].most_common()]}
               for k, v in sorted(cats.items(), key=lambda kv: -kv[1]['n'])}


# ----------------------------------------------------------------------------- findings
# IB/方案列明的产品风险（analysis.expectedAE，工作台从 IB 风险表编译）：AE 按术语/PT 匹配，按 SOC 匹配的标「同类」；检验按风险的检验表现匹配
LAB_ALIAS = {'CK': '肌酸激酶|CK|CPK', 'CPK': '肌酸激酶|CK|CPK', 'HGB': '(?<!糖化)血红蛋白|Hb|HGB', 'HB': '(?<!糖化)血红蛋白|Hb|HGB', 'WBC': '白细胞', 'NEUT': '中性粒细胞',
             'ANC': '中性粒细胞', 'LYM': '淋巴细胞', 'LYMPH': '淋巴细胞', 'PLT': '血小板', 'ALT': '丙氨酸氨基转移酶|ALT', 'AST': '天门冬氨酸氨基转移酶|天冬氨酸|AST',
             'TBIL': '总胆红素', 'TG': '甘油三酯', 'TC': '总胆固醇', 'LDL': '低密度脂蛋白', 'CREA': '肌酐', 'QTCF': 'QTc'}


def _exp_list(C):
    if not hasattr(C, '_exp'):
        C._exp = []
        for e in C.A.get('expectedAE') or []:
            labs = []
            for a, lab, d in e.get('labs') or []:
                pat = LAB_ALIAS.get(str(a or '').upper())
                if not pat and lab and re.search(r'[一-鿿]', str(lab)):      # 别名表没有的指标用中文名（去掉升降词）
                    pat = re.escape(re.sub(r'(升高|降低|增高|减少|下降|异常)$', '', str(lab))[:6])
                if not pat and a:
                    pat = re.escape(str(a))
                if pat:
                    labs.append((re.compile(pat, re.I), d))
            core = re.sub(r'^(严重|重要|重度)|[（(].*?[)）]', '', str(e.get('term') or '')).strip()   # 只按风险名本身匹配（PT 另做相等比较）
            C._exp.append({**e, '_re': re.compile(re.escape(core)) if len(core) >= 2 else None, '_labs': labs})
    return C._exp


def ib_match(C, rec):
    out = []
    for e in _exp_list(C):
        name = f"{e['label']}·{e['term']}"
        term = str(e.get('term') or '')
        opp = ('升高|增多|增高|增加' if re.search(r'减少|降低|下降|减低', term) else '减少|降低|下降|减低' if re.search(r'升高|增多|增高|增加', term) else None)
        if opp and re.search(opp, rec['t']):
            continue
        serious_only = bool(re.match(r'严重|重要|重度', term))
        severe = bool(rec.get('sae') or (grade_int(rec.get('g')) or 0) >= 3)
        hit = (e.get('pt') and rec.get('pt') == e['pt']) or (e['_re'] and e['_re'].search(rec['t']))
        if hit and serious_only and not severe:      # 用户 2026-10-28：「严重感染」类风险点只认严重或 ≥3 级的 AE
            continue
        if hit:
            out.append(name)
        elif severe and rec.get('soc') and rec['soc'] in [re.sub(r'/\d+$', '', s.strip()) for s in re.split(r'[；;]', e.get('soc') or '')
                                                          if s.strip() and not s.strip().startswith('各类检查')]:
            out.append(name + '（同SOC，严重/≥3级）')           # 同 SOC 只保留严重或 ≥3 级                 # 「心脏器官疾病/10007541；血管与淋巴管类疾病/…」多 SOC 写法拆开比对
    return list(dict.fromkeys(out))


def ib_lab_tags(C, mid, label, pts):
    up = any(r.get('value') is not None and r.get('hi') is not None and r['value'] > r['hi'] for r in pts)
    dn = any(r.get('value') is not None and r.get('lo') is not None and r['value'] < r['lo'] for r in pts)
    out = []
    for e in _exp_list(C):
        for rx_, d in e['_labs']:
            if rx_.search(label) and (d not in ('high', 'low') or (d == 'high' and up) or (d == 'low' and dn)):
                out.append(f"{e['label']}：{e['term']}")
                break
    return out


def build_findings(C):
    """Attach metric id, post flag, baseline, Δ, Δ%, toxicity grade (cfg.grading) to every finding."""
    conv = C.A.get('unitConv', {})  # {"lab:血红蛋白": {"g/dL": 10}} — overrides the grading table's unit factors
    qualre = rx(C.A.get('qualTestRe'))
    C.F = defaultdict(list)  # (sid, mid) -> rows
    C.metric = {}
    for f in C.findings:
        if f['sid'] not in C.subj:
            continue
        mid = f"{f['domain']}:{f['test']}"
        f['mid'] = mid
        f['post'] = is_post(C, f['sid'], f.get('date'), f.get('tpt'))
        f['qual'] = f.get('value') is None and bool(f.get('raw')) and (qualre is None or bool(qualre.search(f['test'])))
        m = C.metric.setdefault(mid, {'id': mid, 'label': f['test'], 'domain': f['domain'], 'group': f.get('group') or f['domain'], 'units': Counter(), 'n': 0, 'nq': 0})
        m['units'][f.get('unit') or ''] += 1
        m['n' if f.get('value') is not None else 'nq'] += 1
        if f.get('clin') is not None:
            m['hasClin'] = True                   # 该指标在数据中有临床意义评价（表单有该字段）
        C.F[(f['sid'], mid)].append(f)
    # metric → grading code: cfg.ctcaeMap overrides ('' disables), otherwise automatic analyte dictionary (scripts/grading/analytes.json)
    C.cmap = ctcae.automap(C.metric, C.G, C.cfg.get('ctcaeMap') or {})
    C.cfg['ctcaeMap'] = C.cmap
    C.fac = {}
    for mid, m in C.metric.items():
        code = C.cmap.get(mid)
        if not code:
            continue
        u0 = (m['units'].most_common(1) or [('', 0)])[0][0]
        f0 = conv.get(mid, {}).get(u0) if u0 in conv.get(mid, {}) else C.G.factor(code, u0)
        C.fac[mid] = f0
        m['gcode'], m['gunit'] = code, u0
        if f0 is None:
            m['unitIssue'] = f'单位「{u0}」无法换算到 {C.GL} 标准单位，未自动分级'
        elif not u0 and code not in C.G.ratio:
            m['unitIssue'] = '单位缺失：按分级标准单位处理'
    rules = C.blrules = baseline_rules(C)
    C.btype = {}
    for (sid, mid), rows in C.F.items():
        rows.sort(key=lambda r: (r.get('date') or '', C.vi(r.get('visit')), str(r.get('time') or '')))
        b, btype = pick_baseline(C, sid, mid, rows, rules)
        C.btype[(sid, mid)] = btype if b else '缺失'
        code = C.cmap.get(mid)
        for r in rows:
            r['base'] = b
            r['isb'] = r is b or (b is not None and b.get('_of') is not None and r in b['_of'])
            u = r.get('unit') or ''
            fac = conv.get(mid, {}).get(u) if u in conv.get(mid, {}) else (C.G.factor(code, u) if code else 1)
            v, bv = r.get('value'), (b or {}).get('value')
            r['chg'] = None if v is None or bv is None or r['isb'] else v - bv
            r['pct'] = None if r['chg'] is None or not bv else r['chg'] / abs(bv) * 100
            r['dev'] = ext_rules.dev_of(r)          # M15：vs 收缩压/舒张压无上限时用默认上限（139/89）
            r['grade'], r['gterm'] = None, ''
            if code and v is not None and fac is not None:
                lo = r.get('lo') * fac if r.get('lo') is not None else None
                hi = r.get('hi') * fac if r.get('hi') is not None else None
                g = C.G.grade(code, v * fac, lo, hi, bv * fac if bv is not None else None, r['isb'])
                if g:
                    r['grade'], r['gterm'] = g[0], g[1]
            r['oor'] = v is not None and ((r.get('hi') is not None and v > r['hi']) or (r.get('lo') is not None and v < r['lo']))
        C.metric[mid].setdefault('btype', Counter())[btype if b else '缺失'] += 1


def baseline_rules(C):
    """cfg.baselineRules (first match wins) + legacy cfg.baseline {dom: visit, domTpt: re}. Each rule:
    {match: metric-id regex, method: visit|lastPre|mean, visits: [..], tpt: re, ref: fd|rand|icf, fallback: lastPre|none, unsched: bool, label}"""
    rules = []
    for R in C.cfg.get('baselineRules') or []:
        rules.append(dict(R, _re=re.compile(R.get('match') or '.')))
    bl = C.cfg.get('baseline', {})
    for dom, v in bl.items():
        if dom.endswith('Tpt') or dom.endswith('Label') or not isinstance(v, (str, list)):
            continue
        rules.append({'_re': re.compile('^' + re.escape(dom) + ':'), 'method': 'visit', 'visits': v if isinstance(v, list) else [v], 'tpt': bl.get(dom + 'Tpt'), 'fallback': 'lastPre'})
    return rules


def baseline_desc(C, mid):
    """Human-readable baseline definition for one metric (shown on the objective page)."""
    R = next((r for r in getattr(C, 'blrules', []) if r['_re'].search(mid)), {'method': 'lastPre'})
    if R.get('label'):
        d = R['label']
    else:
        ref = {'rand': '随机', 'icf': '知情同意'}.get(R.get('ref'), '首剂')
        vs = '/'.join(R.get('visits') or [])
        tp = f"（{R['tpt']}）" if R.get('tpt') else ''
        d = {'visit': f"{vs}{tp}", 'mean': f"{vs}{tp} 多次测量均值", 'lastPre': f"{ref}前最近有效值{'（不含计划外）' if R.get('unsched') is False else ''}"}.get(R.get('method', 'visit'), vs)
    fb = '；缺失时用首剂前最近有效值' if R.get('method', 'visit') != 'lastPre' and R.get('fallback', 'lastPre') == 'lastPre' else ''
    return f"规定基线：{d}{fb}"


def pick_baseline(C, sid, mid, rows, rules):
    R = next((r for r in rules if r['_re'].search(mid)), {'method': 'lastPre'})
    s = C.subj[sid]
    ref = s.get({'rand': 'rand_d', 'icf': 'icf'}.get(R.get('ref'), 'fd')) or s['fd']
    cand = [r for r in rows if (r.get('value') is not None or r.get('clin') is not None or r.get('raw')) and not r['post']
            and (not ref or not is_full_date(r.get('date')) or r['date'] <= ref)]
    if R.get('unsched') is False:
        cand = [r for r in cand if r.get('visit') not in C.UNS]
    tre = rx(R.get('tpt'))
    meth = R.get('method', 'visit')
    b, btype = None, '规定'
    if meth in ('visit', 'mean'):
        for v in R.get('visits') or []:
            xs = [r for r in cand if r.get('visit') == v and (not tre or tre.search(str(r.get('tpt') or '')))]
            if xs:
                if meth == 'mean' and len([x for x in xs if x.get('value') is not None]) > 1:
                    vals = [x['value'] for x in xs if x.get('value') is not None]
                    b = dict(xs[-1], value=sum(vals) / len(vals), raw=fmt(sum(vals) / len(vals)), clin=max([x.get('clin') or 0 for x in xs]),
                             _of=xs, tpt=f"{len(vals)} 次均值")
                else:
                    b = xs[-1]
                break
    elif meth == 'lastPre':
        b, btype = (cand[-1] if cand else None), '首剂前最近'
    if b is None and meth != 'lastPre' and R.get('fallback', 'lastPre') == 'lastPre':
        b, btype = (cand[-1] if cand else None), '替代'
    return b, btype


def finding_abn(r):
    return (r.get('clin') in (1, 2)) or (r.get('grade') or 0) >= 1 or r.get('oor')


def resolve_links(C, sid, links):
    out = []
    for kind, term, _, no in links:
        pool = C.ae_by[sid] if kind == 'AE' else C.mh_by[sid]
        ev = next((x for x in pool if str(x['n']) == str(no)), None)
        out.append([kind, term or (ev or {}).get('t', ''), (ev or {}).get('s', ''), no, bool(ev)])
    return out


worse_vs_base = ext_rules.worse_vs_base
disease_kw = ext_rules.disease_kw


def build_labrows(C):
    doms = set(C.A.get('labDomains', ['lab', 'vs', 'ecg']))
    match = [(re.compile(a), re.compile(b), w) for a, b, w in C.A.get('aeMatch', [])]  # [metricRe, aeTermRe, ±days]
    dz = disease_kw(C)

    def disease_ae(sid, mid, pts):
        return ext_rules.disease_ae(C, sid, mid, pts, dz)
    C.labrows = []
    for (sid, mid), rows in C.F.items():
        if sid not in C.pop or mid.split(':')[0] not in doms or C.metric[mid]['nq'] > C.metric[mid]['n']:
            continue
        b = rows[0]['base'] if rows else None
        bg = (b or {}).get('grade') or 0
        bc = (b or {}).get('clin') or 0
        pts, cat = [], '治疗后新发/加重检验异常'
        for r in rows:
            if not r['post'] or (C.aeEnd.get(sid) and is_full_date(r.get('date')) and r['date'] > C.aeEnd[sid]):
                continue
            new = finding_abn(r) and (r.get('clin') == 2 or (r.get('grade') or 0) > bg or (r.get('clin') or 0) > bc or not (b and finding_abn(b)))
            if new:
                pts.append((r, False))
        if not pts:
            continue
        links = []
        for r, _ in pts:
            for l in resolve_links(C, sid, r.get('links') or []):
                if l[:2] not in [x[:2] for x in links]:
                    links.append(l)
        ctx = []
        opp = ext_rules.opposite_dir([r for r, _ in pts])   # mm4：方向相反的 AE 不算同期疑似（嗜酸性粒细胞升高 ≠「白细胞减少」）
        # inferred AE (no dynamic link but a plausible AE exists in time window) → context only, never auto-links
        for mre, are, w in match:
            if mre.search(mid):
                for a in C.ae_by[sid]:
                    if are.search(a['t']) and not opp.search(a['t']) and any(days(a['s'], r['date']) is not None and abs(days(a['s'], r['date'])) <= w for r, _ in pts):
                        c_ = f"同期 AE「{a['t']}」（{a['s']}）可能对应，但检验页未关联"
                        if c_ not in ctx:                # 多条 aeMatch 命中同一 AE 时只列一次（ext 夹具 21029 曾重复）
                            ctx.append(c_)
        P = [r for r, _ in pts]
        anycs = any(r.get('clin') == 2 for r in P)
        mg = max([r.get('grade') or 0 for r in P] + [0])
        has_ae = any(l[0] == 'AE' and l[4] for l in links)    # 关联编号在 AE/病史页不存在的不算已关联
        has_mh = any(l[0] == 'MH' and l[4] for l in links)
        unassessed = all(r.get('clin') is None for r in P)
        # mm4：研究者填写的 CS 原因（reason：disease 研究疾病 / link 病史·不良事件 / other 其他）。
        # 全部 CS 点都归因研究疾病且无关联 → DIS（研究疾病可解释，不发 query，可见）；其中给药后较基线恶化 → DISW（D21：仍须评估 AE）。
        # 原因选「病史/不良事件」但未关联编号 → 仍按 CSX（事实即「未关联」），上下文注明数据缺失。
        cs_pts = [r for r in P if r.get('clin') == 2]
        dis_only = bool(cs_pts) and not links and all(ext_rules.disease_attr(C, r) for r in cs_pts)   # 原因选项或备注归因研究疾病
        if anycs and dis_only:
            # 用户 2026-10-27：归因研究疾病不算「未关联」；只有较基线明显加重、且未记录「研究疾病加重」类 AE 才作为风险
            t_base = float(C.cfg['thresholds'].get('base', 0.3))
            wf = (next((w for w in (worse_vs_base(r, b, t_base) for r in cs_pts if r['post']) if w), None) if b else None) or \
                next((w for w in map(ext_rules.stated_worse, cs_pts) if w), None)      # 研究者备注写明加重：研究者判定优先
            dae = disease_ae(sid, mid, cs_pts) if wf else []
            risk = 'DISW' if wf and not dae else 'DIS'
            ctx.append('研究者归因：研究疾病' + (f'；给药后较基线加重（{wf}）' if wf else '；基线缺失，无法判断是否加重' if not b else '；较基线未明显加重') +
                       (f"；已记录研究疾病加重 AE「{dae[0]['t']}」（{dae[0]['s']}，未关联，提示关联）{ext_rules.onset_note(C, mid, dae[0], cs_pts)}" if dae else
                        '；未见覆盖该期间的研究疾病加重类 AE' if wf else ''))
        elif anycs:
            risk = 'AE' if has_ae else 'MH' if has_mh else 'CSX'
            # mm4：关联按组汇总会掩盖单点——某次 CS 结果自身未关联，且不在本组已关联 AE/MH 的持续期间内 → 仍按 CSX
            if risk in ('AE', 'MH'):
                ev = [x for l in links if l[4] for x in (C.ae_by[sid] if l[0] == 'AE' else C.mh_by[sid]) if str(x['n']) == str(l[3])]

                def _cover(r):
                    d = r.get('date')
                    return not is_full_date(d) or any((not is_full_date(x.get('s')) or x['s'] <= d) and
                                                      (not is_full_date(x.get('e')) or x['e'] >= d) for x in ev)
                orphan = [r for r in cs_pts if not r.get('links') and not _cover(r)]
                if orphan:
                    risk = 'CSX'
                    ctx.append('CS 结果未关联且不在已关联事件期间：' + '、'.join(f"{r.get('visit')}（{r.get('date')}）" for r in orphan[:3]))
            ibg = next((bb for a, bb in (C.A.get('indicationBackground') or []) if re.search(a, mid)), None) if risk == 'CSX' else None
            if ibg:
                nm = re.sub(r'（医学常识）$', '', str(ibg).split('：')[0])
                if b is None:
                    ctx.append(f'研究疾病表现（{nm}）；基线缺失，无法判断是否较基线加重')
                else:
                    wf = next((w for w in (worse_vs_base(r, b, float(C.cfg['thresholds'].get('base', 0.3))) for r in cs_pts if r['post']) if w), None)
                    dae = disease_ae(sid, mid, cs_pts) if wf else []
                    if wf and dae:
                        risk = 'DIS'
                        ctx.append(f"研究疾病表现（{nm}）较基线加重（{wf}），已记录研究疾病加重 AE「{dae[0]['t']}」（{dae[0]['s']}，未关联，提示关联）"
                                   f"{ext_rules.onset_note(C, mid, dae[0], cs_pts)}")
                    elif wf:
                        ctx.append(f'研究疾病表现（{nm}），但较基线进一步加重：{wf}')
                    else:                                # 用户 2026-10-27：疾病本身的表现、较基线没有进一步加重 → 不作为风险
                        risk = 'DIS'
                        ctx.append(f'研究疾病表现（{nm}）：较基线未进一步加重，按疾病表现处理（不发 query）')
            t_base = float(C.cfg['thresholds'].get('base', 0.3))
            if risk == 'CSX' and not any(c.startswith('同期 AE') for c in ctx) and all(ext_rules.judgment_only(C, r, rows, t_base) for r in cs_pts):
                risk = 'CSI'                             # 用户 2026-10-27：相近数值一次 NCS 一次 CS 属判定不一致（另发一致性 query），不按潜在 AE 漏记；有同期疑似 AE 时仍请关联
                ctx.append('CS 与相近结果的 NCS 判定不一致：另发「临床意义判定不一致」query，不按潜在 AE 漏记处理')
            if risk == 'CSX' and any('link' in (r.get('reason') or '') for r in cs_pts):
                ctx.append('原因选择「病史/不良事件」但未关联编号')
            if risk == 'CSX' and any('disease' in (r.get('reason') or '') for r in cs_pts):
                ctx.append('部分 CS 点归因研究疾病')
        elif mg >= 2:
            # 表单没有临床意义字段（如体重）时不是「未评价」：单列一层，请研究者评估是否需记录 AE（D001 QC：体重 2 级曾要求补一个不存在的字段）
            risk = 'AE' if has_ae else ('NA2' if C.metric[mid].get('hasClin') else 'G2NF') if unassessed else 'NCS2'
        elif any(r.get('clin') is None and r.get('oor') for r in P) and C.metric[mid].get('hasClin'):
            # mm4：给药后超出参考范围但未评价临床意义（该表单有临床意义字段）→ 请研究者评价（临床意义决定是否需记 AE）
            risk = 'NA'
        else:
            risk = 'AE' if has_ae else 'NCS'
        if unassessed and risk != 'AE' and C.metric[mid].get('hasClin'):   # 表单没有临床意义字段时不写「未评价」
            ctx.append('临床意义未评价')
        if risk in ('MH', 'NCS2', 'NA', 'NA2'):   # mm4：方案/IB 列出的研究疾病表现 → 审阅时可见（CSX/DIS 已在上方判定）
            ibg = next((b for a, b in (C.A.get('indicationBackground') or []) if re.search(a, mid)), None)
            if ibg:
                ctx.append('可能为研究疾病表现：' + re.sub(r'（医学常识）$', '', str(ibg).split('：')[0]))
        if not C.G.has(C.cmap.get(mid)):
            ctx.append(f'无{C.GL}数值条目：不能仅凭数值分级')
        elif C.metric[mid].get('unitIssue'):
            ctx.append(C.metric[mid]['unitIssue'])
        if b is None:
            ctx.append('基线缺失')
        elif C.btype.get((sid, mid)) == '替代':
            ctx.append(f"基线回退：规定基线缺失，改用首剂前最近有效值（{b.get('visit')}）")
        if len({r.get('unit') for r in rows if r.get('unit')}) > 1:
            ctx.append('单位不一致：单位/换算待核')
        if risk == 'MH':
            # mm4：「加重」采用 D14/D19 口径——分级升高，或超出参考范围且同向较基线变化 ≥T_base；
            # 仅临床意义由 NCS 变 CS（判定波动）不算加重，避免把病史延续的判定差异全部变成 query
            t_base = float(C.cfg['thresholds'].get('base', 0.3))

            dz_mh = bool(dz) and any(l[0] == 'MH' and dz.search(l[1] or '') for l in links)
            cs_ = [r for r in P if r.get('clin') == 2]
            wf = next((w for w in (worse_vs_base(r, b, t_base) or ext_rules.qual_worse(r, b) or (dz_mh and ext_rules.stated_worse(r)) for r in cs_) if w), None)
            undet = None if wf else ('基线缺失，无法判断是否加重' if not b else
                                     '描述性结果，无法自动判断是否加重' if all(r.get('value') is None and ext_rules.qual_level(r.get('raw')) is None for r in cs_) else None)
            dae = disease_ae(sid, mid, [r for r in P if r.get('clin') == 2]) if wf and dz_mh else []
            mhn = '、'.join(l[1] for l in links if l[0] == 'MH')
            # 用户 2026-10-28：已关联病史＝研究者已作判定；是否加重由系统判断——未加重不作风险（MHL），加重才提示/发 query（MH）
            if undet:                                    # 系统判断不了时不归「未加重」：单列提示，由医学监察员看原始记录
                risk = 'MHU'
                ctx.append(f'{undet}：已关联病史「{mhn}」')
            elif not wf:
                risk = 'MHL'
                ctx.append(f'已关联病史「{mhn}」，较基线未明显加重（病史延续）')
            if risk == 'MHL' and any(c.startswith('同期 AE') for c in ctx):   # 用户 2026-10-28：只做提醒，不作为风险
                ctx.append('提醒：同期另有可能对应的 AE 未关联，可请研究者确认是否关联（不作为风险）')
            elif dae:
                risk = 'MHL'
                ctx.append(f"已关联研究疾病病史，较基线加重（{wf}），加重已记录为 AE「{dae[0]['t']}」（{dae[0]['s']}），请关联"
                           f"{ext_rules.onset_note(C, mid, dae[0], [r for r in P if r.get('clin') == 2])}")
            else:
                ctx.append(f'较基线加重（{wf}）：仅关联病史「{mhn}」，未见对应 AE')
        if risk in ('CSX', 'MH', 'MHU', 'NCS2', 'NA', 'NA2', 'G2NF', 'DISW'):   # IB/方案列明风险的检验表现只在需关注的层提示
            ctx += ib_lab_tags(C, mid, C.metric[mid]['label'], P)
        for l in links:
            if not l[4]:
                ctx.append(f'关联对象不存在：{l[0]}+{l[3]}')
        f0 = P[0]
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'test': C.metric[mid]['label'], 'mid': mid, 'grp': f0.get('group') or '',
            'pr': {'CSX': 4, 'MH': 3, 'NCS2': 3, 'NA2': 3, 'G2NF': 3, 'DISW': 3, 'NA': 3, 'MHU': 2}.get(risk, 1),
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None, r.get('wb') or ''] for r in P],   # p[10]=偏离比例（仅 REL/MHX-T 填值）；p[11]=归属工作簿（PR-8 行级归属）
            'rel': [l[:4] for l in links], 'ctx': ctx, 'q': [], 'fid': [], 'cro': '', 'mg': mg, 'risk': risk,
            'wb': f0.get('wb') or '',
            'qkey': f"lab|{sid}|{risk}|{wb_sheet(C, f0.get('sheet'))}|{mid}|{f0.get('visit') or ''}"})
    C.labrows.sort(key=lambda g: (-g['pr'], g['sid'], g['test']))


# ----------------------------------------------------------------------------- M14 REL 双阈值候选（PR-4 数据面）
def thr_eff(C, mid):
    """有效阈值（per_metric 覆盖＝直接替换；metricThreshold 收紧＝min(所选,收紧值)，两参数各自）。"""
    TH = C.cfg['thresholds']
    pm = (TH.get('per_metric') or {}).get(mid, {})
    dev = float(pm.get('dev', TH['dev']))
    base = float(pm.get('base', TH['base']))
    for T in C.mthr:
        if T.get('metric') and re.search(T['metric'], mid):
            if T.get('dev') is not None:
                dev = min(dev, float(T['dev']))
            if T.get('base') is not None:
                base = min(base, float(T['base']))
    return dev, base


def rel_candidates(C):
    """M14 REL：给药后超出参考范围且偏离 ≥T_dev 且同向较基线变化 ≥T_base 的候选（pr2，不自动发 query）。
    构建按最低档（默认 20%；per_metric/metricThreshold 更低时取更低）写全量候选并逐点携带 dev（pts[10]）；
    页面按所选 T_dev/T_base 即时重分类（kz.js），不重新构建。范围内变化不产生候选（dev=0）；
    基线已异常但 Δ<T_base 者不满足同向变化条件、自然排除。同一 (sid,mid) 已有 pr≥3 条目时不重复列 REL 行，
    只把双阈值事实写进该条目 ctx（03 §1）。cfg.relChange.metrics 保留为指标限定（旧「相对变化补充筛查」由本规则取代）。"""
    doms = set(C.A.get('labDomains', ['lab', 'vs', 'ecg']))
    rcre = rx((C.cfg.get('relChange') or {}).get('metrics'))
    by_key = {(g['sid'], g.get('mid')): g for g in C.labrows}
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop or mid.split(':')[0] not in doms or (rcre and not rcre.search(mid)):
            continue
        dev_f, base_f = thr_eff(C, mid)
        dev_f, base_f = min(0.20, dev_f), min(0.20, base_f)      # 最低档候选地板：项目收紧低于 20% 时取收紧值
        mdir = ext_rules.metric_dir(mid)
        cand = []
        for r in rows:
            if not r['post'] or r.get('value') is None or not r.get('dev') or r.get('pct') is None:
                continue
            if r['dev'] < dev_f:
                continue
            hi_e = ext_rules.ref_hi(r)
            above = hi_e is not None and r['value'] > hi_e
            below = r.get('lo') is not None and r['value'] < r['lo']
            if mdir == 'up' and not above:
                continue
            if mdir == 'down' and not below:
                continue
            if (above and r['pct'] >= base_f * 100) or (below and -r['pct'] >= base_f * 100):
                cand.append(r)
        if not cand:
            continue
        b = rows[0]['base']
        exist = by_key.get((sid, mid))
        if exist is not None and (exist.get('pr') or 0) >= 3:
            for r in cand:                                       # 同一源行已有 pr≥3：只作上下文
                exist['ctx'].append(f"双阈值：{r.get('visit')} 偏离参考范围 {r['dev']:.0%}，较基线 {r['pct']:+.0f}%")
            continue
        worst = max(cand, key=lambda r: r['dev'])
        # 用户 2026-10-28：较基线显著变化必须区分是否已关联 AE/病史，避免把已关联的也当成「未关联」
        links = []
        for r in cand:
            for l in resolve_links(C, sid, r.get('links') or []):
                if l[:2] not in [x[:2] for x in links]:
                    links.append(l)
        er = (exist or {}).get('risk')
        bind = 'AE' if any(l[0] == 'AE' for l in links) or er == 'AE' else 'MH' if any(l[0] == 'MH' for l in links) or er == 'MHL' \
            else 'DIS' if er == 'DIS' else 'none'
        if exist is not None and not links:
            links = [x + [True] for x in (exist.get('rel') or [])]
        cl = {r.get('clin') for r in cand}
        judg = 'CS' if 2 in cl else 'NA' if None in cl else 'NCS' if 1 in cl else 'N'
        bctx = {'AE': '已关联AE：该变化已有对应 AE 记录', 'MH': '已关联病史：病史延续，供参考', 'DIS': '研究者归因研究疾病，供参考'}.get(bind) or \
            {'NCS': '未关联AE/病史，研究者判定NCS：较基线变化明显，请结合临床判断是否需记录AE', 'NA': '未关联AE/病史，未评价临床意义',
             'N': '未关联AE/病史，研究者判定正常', 'CS': '未关联AE/病史，研究者判定CS'}[judg]
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': '较基线显著变化且超出参考范围', 'test': C.metric[mid]['label'], 'mid': mid,
            'grp': cand[0].get('group') or '', 'pr': 2,
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None if r.get('dev') is None else round(r['dev'], 4), r.get('wb') or ''] for r in cand],
            'rel': [l[:4] for l in links], 'bind': bind, 'judg': judg, 'ctx': [bctx],
            'q': [], 'fid': [], 'cro': '', 'mg': max([r.get('grade') or 0 for r in cand] + [0]), 'risk': 'REL',
            'qkey': f"lab|{sid}|REL|{wb_sheet(C, worst.get('sheet'))}|{mid}|{worst.get('visit') or ''}"})
    C.labrows.sort(key=lambda g: (-g['pr'], g['sid'], g['test']))


# ----------------------------------------------------------------------------- rule-based signals ("others")
def ev_sh(C, sh, wb=''):
    """PR-8: evidence sheet reference — unique per-workbook id 'wb:sheet' (owning workbook known),
    else deterministic wb_sheet() resolution (first owning id in _source order)."""
    sh = str(sh or '')
    if not sh:
        return ''
    if wb and f"{wb}:{sh}" in (C.src.get('sheets') or {}):
        return f"{wb}:{sh}"
    return wb_sheet(C, sh)


def add_other(C, sid, cat, pr, summ, v=None, d=None, sh='', row=None, test='', clin=None, rel=None, ctx=None, risk=None, rule=None, lane=None, level=None, bkey=None, wb=''):
    s = C.subj[sid]
    o = {'sid': sid, 'site': s['site'], 'cat': cat, 'pr': pr, 'sum': summ, 'v': v or '', 'd': d or '', 'sh': sh, 'row': row, 'test': test,
         'clin': clin, 'rel': rel or [], 'ctx': ctx or [], 'q': [], 'fid': [], 'cro': '', 'risk': risk or '', '_rule': rule or {},
         'wb': wb or '', 'qkey': oth_qkey(C, sid, cat, sh, v, d, test, rel, rule, bkey)}
    C.others.append(o)
    if lane:
        C.tl[sid].setdefault(lane, []).append([d, summ, level if level is not None else (2 if pr >= 4 else 1 if pr >= 3 else 0), (rule or {}).get('symbol', 'diamond'), test])
    return o


def threshold_rules(C):
    """analysis.thresholdRules: protocol-defined numeric triggers (AESI/AE/stopping/eligibility-like) evaluated per finding."""
    for R in C.A.get('thresholdRules', []):
        mre = re.compile(R['metric'])
        are = rx(R.get('expectAE'))
        vis = set(R.get('visits') or [])
        seen = set()
        for (sid, mid), rows in C.F.items():
            if sid not in C.pop or not mre.search(mid):
                continue
            for r in rows:
                if R.get('post', True) and not r['post']:
                    continue
                if vis and r.get('visit') not in vis:
                    continue
                on = R.get('on', 'val')
                x = {'val': r.get('value'), 'chg': r.get('chg'), 'pct': r.get('pct'),
                     'uln': (r['value'] / r['hi']) if r.get('value') is not None and r.get('hi') else None,
                     'lln': (r['value'] / r['lo']) if r.get('value') is not None and r.get('lo') else None,
                     'grade': r.get('grade')}.get(on)                    # mm4：方案按 CTCAE 级别定义的阈值（如 3 级血细胞减少）
                if not cmp(R.get('op', '>='), x, R['v']):
                    continue
                if R.get('once') and (sid, R['id']) in seen:
                    continue
                seen.add((sid, R['id']))
                rel, ctx, pr, risk = [], [], R.get('pr', 3), ''
                if are:
                    hit = [a for a in C.ae_by[sid] if are.search(a['t']) and (days(a['s'], r['date']) is None or abs(days(a['s'], r['date'])) <= R.get('window', 30))]
                    if hit:
                        rel = [['AE', a['t'], a['s'], a['n']] for a in hit]
                        risk = 'AE'
                        if R.get('aesi') and not any(a['aesi'] for a in hit):
                            ctx.append('已记录 AE 但 AESI 未勾选')
                        else:
                            pr = min(pr, 2)
                    else:
                        ctx.append('未见对应 AE 记录')
                b = r.get('base') or {}
                summ = fill(R.get('sum', '{test} {value} {unit}（{visit} {date}）达到方案阈值 {thr}'), test=C.metric[mid]['label'], value=r.get('raw'),
                            unit=r.get('unit') or '', visit=r.get('visit'), date=r.get('date'), thr=R.get('label', f"{R.get('op', '>=')}{R['v']}"),
                            base=b.get('raw'), chg=r.get('chg'), pct=None if r.get('pct') is None else round(r['pct'], 1), uln=r.get('hi'), lln=r.get('lo'))
                add_other(C, sid, R['cat'], pr, summ, r.get('visit'), r.get('date'), r['sheet'], r['row'], C.metric[mid]['label'], r.get('clin'), rel, ctx, risk, R,
                          R.get('lane'), R.get('level'), bkey=f"{C.metric[mid]['label']}|{r.get('visit') or ''}|{r.get('date') or ''}", wb=r.get('wb') or '')


def combo_rules(C):
    """analysis.comboRules: multi-analyte criteria on the same/near date (e.g. Hy's law: ALT/AST ≥3×ULN AND TBIL ≥2×ULN AND NOT ALP ≥2×ULN).
    {id, name, cat, pr, all:[{metric, on, op, v}], none:[...], window: days (0 = same date), aesi, expectAE, aeWindow, sum, ask, once(true)}"""
    def val(r, on):
        v = r.get('value')
        if v is None:
            return None
        return {'val': v, 'chg': r.get('chg'), 'pct': r.get('pct'), 'uln': v / r['hi'] if r.get('hi') else None, 'lln': v / r['lo'] if r.get('lo') else None,
                'grade': r.get('grade')}.get(on or 'val')
    for R in C.A.get('comboRules', []):
        conds = [dict(c, _re=re.compile(c['metric'])) for c in R['all']]
        nots = [dict(c, _re=re.compile(c['metric'])) for c in R.get('none', [])]
        w = R.get('window', 0)
        are = rx(R.get('expectAE'))
        for sid in sorted(C.pop):
            rows = [r for (s2, mid), rs in C.F.items() if s2 == sid for r in rs if r['post'] and is_full_date(r.get('date'))]
            hits0 = [r for r in rows if conds[0]['_re'].search(r['mid']) and cmp(conds[0].get('op', '>='), val(r, conds[0].get('on')), conds[0]['v'])]
            for r0 in hits0:
                near = [r for r in rows if abs(days(r0['date'], r['date']) or 0) <= w]
                parts = [r0]
                for c in conds[1:]:
                    m = next((r for r in near if c['_re'].search(r['mid']) and cmp(c.get('op', '>='), val(r, c.get('on')), c['v'])), None)
                    if m is None:
                        break
                    parts.append(m)
                else:
                    if any(c['_re'].search(r['mid']) and cmp(c.get('op', '>='), val(r, c.get('on')), c['v']) for c in nots for r in near):
                        continue
                    rel, ctx, pr, risk = [], [], R.get('pr', 4), ''
                    if are:
                        hit = [a for a in C.ae_by[sid] if are.search(a['t'] + ' ' + a.get('pt', '')) and (days(a['s'], r0['date']) is None or abs(days(a['s'], r0['date'])) <= R.get('aeWindow', 30))]
                        if hit:
                            rel, risk = [['AE', a['t'], a['s'], a['n']] for a in hit], 'AE'
                            if R.get('aesi') and not any(a['aesi'] for a in hit):
                                ctx.append('已记录 AE 但 AESI 未勾选')
                            else:
                                pr = min(pr, 2)
                        else:
                            ctx.append('未见对应 AE 记录')
                    det = '；'.join(f"{C.metric[p['mid']]['label']} {p.get('raw')} {p.get('unit') or ''}".strip() + (f"（{p['value'] / p['hi']:.1f}×ULN）" if p.get('hi') and p.get('value') is not None else '') for p in parts)
                    summ = fill(R.get('sum', '{name}：{detail}（{visit} {date}）'), name=R.get('name', R['id']), detail=det, visit=r0.get('visit'), date=r0['date'])
                    add_other(C, sid, R.get('cat', '阈值规则核对'), pr, summ, r0.get('visit'), r0['date'], r0['sheet'], r0['row'], C.metric[r0['mid']]['label'],
                              r0.get('clin'), rel, ctx, risk, R, R.get('lane'), R.get('level'),
                              bkey=f"{C.metric[r0['mid']]['label']}|{r0.get('visit') or ''}|{r0['date']}", wb=r0.get('wb') or '')
                    if R.get('once', True):
                        break


def ae_checks(C):
    on = set(C.A.get('aeChecks', ['predose_related', 'grade_vs_lab', 'cm_flag', 'cm_missing', 'aesi_terms', 'aesi_unmatched', 'duplicate']))
    lab_by_ae = defaultdict(list)
    for (sid, mid), rows in C.F.items():
        for r in rows:
            for l in r.get('links') or []:
                if l[0] == 'AE':
                    lab_by_ae[(sid, str(l[3]))].append(r)
    for a in C.aes:
        sid = a['sid']
        if sid not in C.pop:
            continue
        if 'predose_related' in on and a['pre'] and a['_rel']:
            add_other(C, sid, 'AE给药前事件相关性核对', 3, f"AE「{a['t']}」开始于首剂（{a['fd']}）前 {a['s']}，相关性记为「{a['rel']}」", None, a['s'], a['sh'], a['row'], a['t'],
                      rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'grade_vs_lab' in on:
            rs = [r for r in lab_by_ae[(sid, str(a['n']))] if r.get('grade')]
            gi = grade_int(a['g']) or 0
            mx = max(rs, key=lambda r: r['grade']) if rs else None
            if mx and mx['grade'] > gi:
                add_other(C, sid, 'AE分级与检验等级核对', 3, f"AE「{a['t']}」记 {a['g']}，关联检验 {mx['test']} {mx.get('raw')} {mx.get('unit') or ''}（{mx.get('date')}）达 {C.GL} {mx['grade']} 级（{mx['gterm']}）",
                          mx.get('visit'), mx.get('date'), mx['sheet'], mx['row'], mx['test'], mx.get('clin'), [['AE', a['t'], a['s'], a['n']]], risk='AE')
        if 'cm_flag' in on and re.search(r'^否|^N', a['cm'] or ''):
            cms = [c for c in C.cm_by[sid] if c['wk'] == 'AE' and (a['t'] and a['t'] in c['why'] or re.search(rf'\b{a["n"]}\b', c['why']))]
            if cms:
                add_other(C, sid, 'AE合并用药标记核对', 2, f"AE「{a['t']}」记「是否有合并用药=否」，但 CM「{cms[0]['t']}」用药原因指向该 AE", None, a['s'], a['sh'], a['row'], a['t'],
                          rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'cm_missing' in on and re.search(r'^是|^Y', a['cm'] or '') and C.cm_by[sid]:
            # mm4：AE 记「有合并用药」，但合并用药页未见引用该 AE（AE 编号字段或用药原因指向该 AE）
            ref = [c for c in C.cm_by[sid] if re.search(rf'(?<!\d){re.escape(str(a["n"]))}(?!\d)', c.get('aeno') or '')
                   or (a['t'] and a['t'] in (c['why'] or '')) or (c['wk'] == 'AE' and re.search(rf'(?<!\d){re.escape(str(a["n"]))}(?!\d)', c['why'] or ''))]
            if not ref and any(c.get('aeno') or c['wk'] for c in C.cm_by[sid]):
                add_other(C, sid, 'AE合并用药记录核对', 3, f"AE「{a['t']}」（{a['s']}）记「是否有合并用药=是」，合并用药页未见引用该 AE 的记录", None, a['s'], a['sh'], a['row'], a['t'],
                          rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'aesi_terms' in on and a['_aesi_term'] and not a['aesi'] and not a['pre']:
            add_other(C, sid, 'AESI标记核对', 3, f"AE「{a['t']}」符合方案 AESI 定义（{'、'.join(a['_aesi_def'])}），但「是否AESI」未勾选", None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
    termdefs = [d for d in C.aesiDefs if d['_t'] or d['_soc']]
    if 'aesi_unmatched' in on and termdefs and len(termdefs) == len(C.aesiDefs) and not any(R.get('aesi') for R in C.A.get('thresholdRules', []) + C.A.get('comboRules', [])):
        for a in C.aes:  # flagged AESI but matches none of the protocol's (purely term-based) AESI definitions
            if a['sid'] in C.pop and a['aesi'] and not a['_aesi_term']:
                add_other(C, a['sid'], 'AESI标记核对', 2, f"AE「{a['t']}」勾选为 AESI，但不符合方案列出的 AESI 定义（{'、'.join(d.get('name') or d.get('id') for d in termdefs)}）",
                          None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
    for RR in C.A.get('reportRules', []):  # {"flag": "serious"|"aesi", "days": 1, "from": "aware"|"start", "label": "SAE 24h"}
        key = {'serious': 'sae', 'aesi': 'aesi'}.get(RR.get('flag'), RR.get('flag'))
        for a in C.aes:
            if a['sid'] not in C.pop or not a.get(key):
                continue
            t0 = a.get('aware') if RR.get('from', 'aware') == 'aware' and is_full_date(a.get('aware')) else a['s']
            dd = days(a.get('rpt'), t0) if is_full_date(a.get('rpt')) and is_full_date(t0) else None
            if dd is None:
                if RR.get('requireDate'):
                    add_other(C, a['sid'], 'AE报告时限核对', 2, f"{RR.get('label', key)}：AE「{a['t']}」缺少报告日期", None, a['s'], a['sh'], a['row'], a['t'], risk='AE', wb=a.get('wb') or '')
                continue
            if dd > RR.get('days', 1):
                add_other(C, a['sid'], 'AE报告时限核对', RR.get('pr', 3), f"{RR.get('label', key)}：AE「{a['t']}」{'获知' if t0 == a.get('aware') else '发生'}于 {t0}，报告于 {a['rpt']}（{dd} 天，方案要求 ≤{RR.get('days', 1)} 天）",
                          None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
    if 'duplicate' in on:
        for sid, L in C.ae_by.items():
            for i, x in enumerate(L):
                for y in L[i + 1:]:
                    if x['t'] == y['t'] and x['s'] and y['s'] and (not x['e'] or y['s'] <= x['e']) and (not y['e'] or x['s'] <= y['e']):
                        add_other(C, sid, 'AE重复/同义记录核对', 2, f"同一术语「{x['t']}」两条记录时间重叠（#{x['n']} {x['s']}~{x['e'] or '持续'} / #{y['n']} {y['s']}~{y['e'] or '持续'}）",
                                  None, y['s'], y['sh'], y['row'], y['t'], rel=[['AE', x['t'], x['s'], x['n']], ['AE', y['t'], y['s'], y['n']]], risk='AE')


def range_checks(C):
    """mm4：参考范围缺失——同一实验室指标多数记录有参考范围，而该记录数值存在但上下限均缺失（无法判异常与分级）。
    受试者×指标一条（首条为证据，其余访视进上下文）；同一中心同一指标 ≥3 例缺失 → 中心系统性问题，转中心沟通提示（pr2，不逐例发 query）。"""
    if C.A.get('rangeCheck') is False:
        return
    miss = defaultdict(list)                    # (sid, mid) -> rows
    stats = {}
    for mid, m in C.metric.items():
        if m['domain'] != 'lab':
            continue
        rows = [r for (sid, mm), rs in C.F.items() if mm == mid and sid in C.pop for r in rs if r.get('value') is not None]
        if len(rows) < 5:
            continue
        has = sum(1 for r in rows if r.get('lo') is not None or r.get('hi') is not None)
        if has < 0.8 * len(rows):
            continue
        stats[mid] = (has, len(rows))
        for r in rows:
            if r.get('lo') is None and r.get('hi') is None:
                miss[(r['sid'], mid)].append(r)
    site_n = Counter((C.subj[sid]['site'], mid) for (sid, mid) in miss)
    for (sid, mid), rows in sorted(miss.items()):
        r, m = rows[0], C.metric[mid]
        systemic = site_n[(C.subj[sid]['site'], mid)] >= 3
        ctx = [f"另有 {len(rows) - 1} 次未填：" + '、'.join(str(x.get('visit')) for x in rows[1:5])] if len(rows) > 1 else []
        if systemic:
            ctx.append(f"中心系统性未填（本中心 {site_n[(C.subj[sid]['site'], mid)]} 例）：建议中心层面沟通，不逐例发 query")
        add_other(C, sid, '参考范围缺失核对', 2 if systemic else 3,
                  f"{r.get('visit')}（{r.get('date')}）{m['label']} {r.get('raw')} {r.get('unit') or ''} 未填写参考范围（同指标 {stats[mid][0]}/{stats[mid][1]} 条记录有范围）",
                  r.get('visit'), r.get('date'), r['sheet'], r['row'], m['label'], r.get('clin'), ctx=ctx,
                  rule={'ask': '请补充该结果的参考范围（上下限），并据此核对临床意义评价。'},
                  bkey=f"{m['label']}|range", wb=r.get('wb') or '')


def overlap(c, a, b):
    s, e = c['s'] or '0000', (c['e'] or '9999') if not c['ong'] else '9999'
    return s <= (b or '9999') and e >= (a or '0000')


_TOPICAL = re.compile(r'外用|局部|皮肤|软膏|乳膏|霜|凝胶|洗剂|搽剂|酊|贴|滴眼|滴鼻|吸入|喷雾|topical|cream|ointment|gel|lotion', re.I)
_SYSTEMIC = re.compile(r'系统|全身|口服|静脉|注射|systemic', re.I)


def cm_checks(C):
    rescue = (C.A.get('pd') or {}).get('rescue') or {}
    rescue_re = re.compile(r'补救|rescue', re.I)
    for P in C.A.get('prohibited', []):  # {"name","re","window":[daysBeforeFd, 'ld'|daysAfterFd], "pr"}
        pre = re.compile(P['re'], re.I)
        systemic_only = bool(_SYSTEMIC.search(P.get('name') or '')) and not _TOPICAL.search(P.get('name') or '')
        for sid in C.pop:
            s = C.subj[sid]
            if not s['fd']:
                continue
            w0 = P.get('daysBefore', 0)
            a = (dt.date.fromisoformat(s['fd']) - dt.timedelta(days=w0)).isoformat()
            b = (dt.date.fromisoformat(s['ld']) + dt.timedelta(days=P.get('daysAfter', 0))).isoformat() if is_full_date(s['ld']) else s['lo']
            for c in C.cm_by[sid]:
                if pre.search(c['t']) and overlap(c, a, b):
                    # 「系统治疗」类禁用药不匹配外用/局部给药；按方案作为补救治疗使用的由补救规则（CM-02/03）核查，不按禁用药报
                    if systemic_only and (_TOPICAL.search(c.get('rt') or '') or _TOPICAL.search(c['t'])):
                        continue
                    if rescue and rescue_re.search(c.get('why') or '') and (not is_full_date(c['s']) or c['s'] >= s['fd']):
                        continue
                    add_other(C, sid, P.get('cat', '禁限用药核对'), P.get('pr', 4),
                              f"CM「{c['t']}」（{c['s'] or '?'}~{'持续' if c['ong'] else c['e'] or '?'}）属于{P['name']}，与{('首剂前 %d 天至' % w0) if w0 else ''}治疗期重叠；用药原因：{c['why'] or '—'}",
                              None, c['s'], c['sh'], c['row'], c['t'], ctx=[P.get('note', '')] if P.get('note') else [],
                              bkey=f"{c['t']}|{c['s']}", wb=c.get('wb') or '')
    for W in C.A.get('washout', []):  # {"name","re","days","ref":"icf"|"fd"}
        pre = re.compile(W['re'], re.I)
        for sid in C.pop:
            s = C.subj[sid]
            ref = s.get({'rand': 'rand_d'}.get(W.get('ref', 'fd'), W.get('ref', 'fd')))
            if not is_full_date(ref):
                continue
            a = (dt.date.fromisoformat(ref) - dt.timedelta(days=W['days'])).isoformat()
            for c in C.cm_by[sid]:
                if pre.search(c['t']) and (c['ong'] or (is_full_date(c['e']) and c['e'] >= a)) and (not is_full_date(c['s']) or c['s'] <= ref):
                    add_other(C, sid, W.get('cat', '入排洗脱用药核对'), W.get('pr', 3),
                              f"CM「{c['t']}」末次 {c['e'] or '持续'}，距{ {'icf': '知情', 'rand': '随机'}.get(W.get('ref'), '首剂')}（{ref}）不足 {W['days']} 天洗脱期（{W['name']}）",
                              None, c['e'] or c['s'], c['sh'], c['row'], c['t'], bkey=f"{c['t']}|{c['s']}", wb=c.get('wb') or '')


# 常见单位换算（判定单位 → 记录单位，记录值 ÷ 系数 = 判定单位值）；不在表内且单位不同 → 不判（单位待核，不产生信号）
UNIT_FAC = {('g/dl', 'g/l'): 10, ('mg/dl', 'mg/l'): 10, ('g/l', 'g/dl'): 0.1, ('miu/ml', 'iu/l'): 1, ('iu/l', 'miu/ml'): 1,
            ('miu/ml', 'miu/ml'): 1, ('mmol/l', 'mmol/l'): 1, ('×10^9/l', '10^9/l'): 1, ('10^9/l', '×10^9/l'): 1}


def _unorm(u):
    return str(u or '').strip().lower().replace(' ', '').replace('μ', 'u').replace('µ', 'u')


def _elig_x(E, r):
    if E.get('re'):                                      # 定性（阳性等）：取原值文本
        return r.get('raw') if r.get('raw') not in (None, '') else None
    on = E.get('on', 'val')
    v = r.get('value')
    if on == 'val' and v is not None and E.get('unit'):
        eu, ru = _unorm(E['unit']), _unorm(r.get('unit'))
        if ru and eu != ru:
            f = UNIT_FAC.get((eu, ru))
            if f is None:
                return None                              # 单位不可换算 → 不判
            v = v / f
    return {'val': v, 'uln': (r['value'] / r['hi']) if r.get('value') is not None and r.get('hi') else None,
            'lln': (r['value'] / r['lo']) if r.get('value') is not None and r.get('lo') else None}.get(on)


def _elig_bad(E, x):
    if E.get('re'):
        return bool(re.search(E['re'], str(x or ''), re.I)) and not re.search(r'阴性|negative|未检出', str(x or ''), re.I)
    return cmp(E['op'], x, E['v'])


def _elig_pool(C, sid, rows, E):
    """入组判定集合：入组（随机，无随机日期时首剂）前的测量；`visits` 限定访视，未写时取 SoA 中首剂访视之前的计划访视
    ＋计划外（筛选期复查常记为计划外）；`window` 天数限定距入组日的窗口。"""
    s = C.subj[sid]
    cut = s.get('rand_d') if is_full_date(s.get('rand_d')) else s.get('fd')
    vis = set(E.get('visits') or [])
    d1 = (C.cfg.get('visits') or {}).get('d1')
    pre_vis = set(C.VIS[:C.VIS.index(d1)]) if d1 in C.VIS else None
    lo_d = (dt.date.fromisoformat(cut) - dt.timedelta(days=int(E['window']))).isoformat() if E.get('window') and is_full_date(cut) else None
    out = []
    for r in rows:
        if r['post'] or _elig_x(E, r) is None:
            continue
        d = r.get('date')
        if is_full_date(cut) and is_full_date(d) and (d > cut or (lo_d and d < lo_d)):
            continue
        v = r.get('visit')
        if vis and v not in vis:
            continue
        if not vis and pre_vis is not None and v not in pre_vis and v not in C.UNS:
            continue
        out.append(r)
    return out


def eligibility_checks(C):
    """入排数值核对（受试者×标准一条）。判定值按 `pick`：last（默认，入组前末次有效测量——方案允许复查时以复查值为准）/
    first（首次筛选值）/ any（任一测量不符即提示，方案明确不允许复查时用）。其余不符测量写入上下文，不另成信号。"""
    for E in C.A.get('eligibility', []):  # {"id","metric","visits":[..],"op","v","text","pr","on","pick","window","kind"}
        mre = re.compile(E['metric'])
        pick = E.get('pick', 'last')
        if E.get('re') and pick == 'last':
            pick = 'any'                                 # 定性阳性：任一筛选期阳性即提示（复查阴性见上下文）
        kind = {'inclusion': '入选标准', 'exclusion': '排除标准'}.get(E.get('kind'), '入排标准')
        for (sid, mid), rows in C.F.items():
            if sid not in C.pop or not mre.search(mid):
                continue
            pool = _elig_pool(C, sid, rows, E)
            if not pool:
                continue
            bad = [r for r in pool if _elig_bad(E, _elig_x(E, r))]
            r = pool[-1] if pick == 'last' else pool[0] if pick == 'first' else (bad[0] if bad else None)
            if r is None or r not in bad:
                continue
            lab = C.metric[mid]['label']
            ctx = [E.get('id', '')] if E.get('id') else []
            others = [x for x in bad if x is not r]
            if others:
                ctx.append('另有不符测量：' + '、'.join(f"{x.get('visit')} {x.get('raw')}" for x in others[:4]))
            if E.get('exc'):
                ctx.append('例外条款：' + str(E['exc']))
            if len(pool) > 1:
                ctx.append(f"判定值＝{'入组前末次测量' if pick == 'last' else '首次筛选测量' if pick == 'first' else '任一测量'}（共 {len(pool)} 次）")
            add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4),
                      f"入组前 {lab} {r.get('raw')} {r.get('unit') or ''}（{r.get('visit')} {r.get('date')}）对照{kind}「{E['text']}」不符，但已随机/给药",
                      r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx,
                      bkey=f"{lab}|{r.get('visit') or ''}|{r.get('date') or ''}", wb=r.get('wb') or '')   # qkey 沿用旧口径（类别＋判定记录），存量 MMQ 身份不漂移
    for E in C.A.get('eligibilitySubject', []):  # {"field":"age","op","v","text"}
        for sid in C.pop:
            v = C.subj[sid].get(E['field'])
            if cmp(E['op'], v, E['v']):
                add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4), f"{E.get('label', E['field'])} = {fmt(v) if isinstance(v, float) else v}，不符合入选/排除「{E['text']}」", None, C.subj[sid].get('icf'),
                          C.subj[sid].get('sheet', ''), C.subj[sid].get('row'), bkey=f"{E['field']}|{E.get('id') or ''}")


def visit_window_checks(C):
    W = C.A.get('visitWindows', {})  # {"W2": [15, 3, 3]}  target study day, minus, plus
    for v in C.visits:
        sid = v['sid']
        if sid not in C.pop or v.get('visit') not in W:
            continue
        spec = W[v['visit']]
        if isinstance(spec, dict):
            t, mi, pl, anc = spec.get('target'), spec.get('minus', 0), spec.get('plus', 0), spec.get('anchor', 'fd')
        else:
            (t, mi, pl), anc = spec[:3], 'fd'
        s = C.subj[sid]
        if anc == 'fd':
            sd, lab = study_day(v.get('date'), s['fd']), 'D'
        else:  # days since anchor (rand / icf / another visit's actual date), anchor = day 0
            ad = s.get({'rand': 'rand_d', 'icf': 'icf', 'ld': 'ld'}.get(anc, '')) if anc in ('rand', 'icf', 'ld') else next((x.get('date') for x in C.visits if x['sid'] == sid and x.get('visit') == anc), None)
            sd, lab = (days(v.get('date'), ad) if is_full_date(ad) and is_full_date(v.get('date')) else None), f'{anc}+'
        if sd is not None and (sd < t - mi or sd > t + pl):
            add_other(C, sid, '访视超窗核对', 2, f"{v['visit']} 实际 {v['date']}（{lab}{sd}），方案窗 {lab}{t}{'−%d' % mi}/+{pl}", v['visit'], v['date'], v['sheet'], v['row'], wb=v.get('wb') or '')


def pd_reconcile(C):
    """Event-level matching of signals against the PD listing (same subject, ±window days, category keyword)."""
    if not C.pd:
        return
    cats = C.A.get('pdCats', {'禁限用药核对': '用药|禁', '入排洗脱用药核对': '入排|洗脱|用药', '入排标准核对': '入排|入选|排除', '访视超窗核对': '窗|访视'})
    for o in C.others:
        if o['cat'] not in cats:
            continue
        kw = re.compile(cats[o['cat']])
        hit = [p for p in C.pd if p['sid'] == o['sid'] and kw.search(f"{p.get('cat', '')}{p.get('desc', '')}") and
               (not o['d'] or not is_full_date(p.get('date')) or abs(days(p['date'], o['d']) or 0) <= C.A.get('pdWindow', 45))]
        if hit:
            o['ctx'].append(f"PD 已记录：{hit[0].get('desc') or hit[0].get('cat')}")
            o['pr'] = min(o['pr'], 2)
        else:
            o['ctx'].append('PD listing 未见对应记录')


# ----------------------------------------------------------------------------- queries
QT = {  # 默认 query 措辞：写给 CRC，一句话＝异常点＋冲突点＋建议（不写日期：query 已定位到 listing 行）。可用 analysis.queryTemplates 覆盖
    'CSX': ('CS未关联AE/MH', '{btxt}{visit}访视{test}{move}{raw}{unit}（参考范围 {rng}{gtxt}），判定为CS，但未关联AE或病史，',
            '请核实是否需记录AE，或补充病史并关联。'),
    'MH': ('CS仅关联病史·加重核对', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判定为CS，仅关联病史「{mh}」，未见对应AE，',
           '请评估是否为给药后加重、需记录AE。'),
    'CSX_DIS': ('CS未关联·研究疾病表现较基线加重', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判定为CS，该指标异常可见于{bg}，但较基线明显加重且未记录AE，',
                '请评估是否需记录AE。'),
    'CSX_AE': ('CS未关联·同期疑似AE', '{visit}访视{test}为{raw}{unit}，判定为CS，同期已记录{cand}，但该检验未关联，',
               '请确认是否为同一事件并完成关联。'),
    'NCS2': ('NCS但达分级≥2级', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级）判定为NCS，',
             '请核实临床意义判定。'),
    'NA': ('超出参考范围·未评价临床意义', '{visit}访视{test}为{raw}{unit}，超出参考范围（{rng}），未评价临床意义，',
           '请补充临床意义评价。'),
    'DISW': ('CS归因研究疾病·给药后加重', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判定为CS并归因研究疾病，但未记录研究疾病加重AE，',
             '请评估是否需记录AE。'),
    'G2NF': ('达分级≥2级·表单无临床意义评价', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级），该表单没有临床意义评价，',
             '请评估是否需记录AE。'),
    'NA2': ('未评价临床意义·达分级≥2级', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级），未评价临床意义，',
            '请补充临床意义评价，并评估是否需记录AE。'),
}


def ext_match(C, sid, sheet, text):
    """Check overlap with external (CRO) queries for the same subject/form → (status, cro text)."""
    names = {sheet} if sheet else set()
    if sheet:
        names |= {C.cfg.get('labGroups', {}).get(sheet), C.A.get('formNames', {}).get(sheet)}
        names |= C.sheet_groups.get(sheet, set())
        names.discard(None)
        names.discard('')

    def same_form(form):
        form = str(form or '')
        return not sheet or not form or any(n in form or form in n for n in names)
    xs = [q for q in C.extq if q.get('sid') == sid and same_form(q.get('form'))]
    def toks(x):
        x = str(x)
        for a, b in C.A.get('synonyms', [['ALT', '丙氨酸氨基转移酶'], ['AST', '天门冬氨酸氨基转移酶'], ['TBIL', '总胆红素'], ['QTc', 'QTcF']]):
            x = x.replace(a, b)
        han = re.findall(r'[\u4e00-\u9fa5]+', x)
        bi = {h[i:i + 2] for h in han for i in range(len(h) - 1)}
        nums = set(re.findall(r'\d+(?:\.\d+)?', x))
        return bi, nums
    stop = set(C.A.get('dedupStop', ['请核', '核实', '确认', '是否', '研究', '研究者', '判定', '记录', '需要', '请确']))
    b0, n0 = toks(text)
    b0 -= stop
    for q in xs:
        t = str(q.get('text') or '')
        b1, n1 = toks(t)
        b1 -= stop
        ov = len(b0 & b1) / max(1, min(len(b0), len(b1)))
        num = {n for n in n0 & n1 if len(n) >= 2 and not re.fullmatch(r'20\d\d', n)}
        if (num and ov >= C.A.get('dedupMinOverlapNum', 0.2)) or ov >= C.A.get('dedupMinOverlap', 0.45):
            conflict = rx(C.A.get('conflictRe', r'无需|不需要|不用|请删除|删除该'))
            return ('冲突澄清' if conflict and conflict.search(t) else '同主题已查重'), t
    return '未见同问', ''


def build_queries(C):
    C.sheet_groups = defaultdict(set)
    for f in C.findings:
        if f.get('group'):
            C.sheet_groups[f['sheet']].add(f['group'])
    T = dict(QT)
    T.update({k: tuple(v) for k, v in C.A.get('queryTemplates', {}).items()})
    risks = list(C.A.get('queryRisks', ['CSX', 'MH', 'NCS2', 'NA2', 'DISW', 'NA'])) + ['G2NF']
    Q = []
    common = defaultdict(list)

    def new_q(sid, cat, sh, row, v, d, test, fact, ask, ev, src, qkey='', card=None):
        # PR-8: evidence rows and the query sheet column use the per-workbook unique id ('wb:sheet')
        # so same-name sheets in different workbooks never share attribution; display keeps the id
        # (front-end filter chips / source review show 'wb:sheet'-style traceability).
        src_wb = (src or {}).get('wb') if isinstance(src, dict) else ''
        sh_id = ev_sh(C, sh, src_wb)
        same = next((q for q in Q if q['sid'] == sid and q['sh'] == sh_id and row is not None and q['row'] == row), None)
        if same and C.A.get('mergeSameCell', True):  # one EDC cell → one query; append the extra fact/ask
            same['parts'] += [['另：' + fact, 0], [ask, 1]]
            same['text'] = ''.join(x[0] for x in same['parts'])
            same['_cards'].append(card or {'问题': cat, '事实': fact, '建议': ask})
            same['cat2'] = same.get('cat2', []) + [cat]
            src['q'].append(same['id'])
            return same
        st, cro = ext_match(C, sid, sh, fact + ask)
        if st == '同主题已查重' and C.A.get('skipDuplicates', False):
            return None
        ev = [[ev_sh(C, e[0], src_wb)] + list(e[1:]) for e in ev]
        q = {'id': f'Q{len(Q) + 1:03d}', 'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'sh': sh_id, 'row': row, 'v': v or '', 'd': d or '', 'test': test or '',
             'text': fact + ask, 'parts': [[fact, 0], [ask, 1]], 'ev': ev, 'cro': st, 'flags': [], '_cro': cro, 'qkey': qkey,
             '_cards': [card or {'问题': cat, '事实': fact, '建议': ask}]}
        if ask and ask not in common[cat]:
            common[cat].append(ask)
        Q.append(q)
        src['q'].append(q['id'])
        if cro:
            src['cro'] = cro
        return q

    ind_bg = [(re.compile(a), str(b or '')) for a, b in (C.A.get('indicationBackground') or [])]
    for g in C.labrows:
        if g['risk'] not in risks:
            continue
        cat, ft, ask = T[g['risk']]
        cand = [c for c in g['ctx'] if c.startswith('同期 AE')]
        bg = next((b for rx, b in ind_bg if rx.search(g.get('mid') or '')), None) if g['risk'] == 'CSX' else None
        if g['risk'] == 'CSX' and cand:  # a plausible AE exists but the finding is not linked → ask to link instead of "report AE"
            cat, ft, ask = T.get('CSX_AE', T['CSX'])
            ft = ft.replace('{cand}', '、'.join(re.sub(r'可能对应，但检验页未关联', '', c).replace('同期 ', '') for c in cand))
        elif bg:                         # mm4：研究疾病表现且较基线进一步加重（未加重的已归 DIS，不发 query）
            cat, ft, ask = T.get('CSX_DIS', T['CSX'])
            ft = ft.replace('{bg}', re.sub(r'[↑↓]|（医学常识）$', '', bg.split('：')[0]))
        P = [p for p in g['pts'] if (g['risk'] in ('NCS2', 'NA2', 'G2NF') and (p[4] or 0) >= 2) or (g['risk'] not in ('NCS2', 'NA2', 'G2NF') and p[5] == 2)] or g['pts']
        if g['risk'] in ('MH', 'DISW') or bg:          # 加重类：以较基线变化最大的那次为主，数值与「较基线」必须是同一个点（D001 QC：曾写成 0.68 较 0.60 升高 63%）
            P = sorted(P, key=lambda x: -abs(x[6] or 0))
        p = P[0]
        f = next((r for r in C.F[(g['sid'], g['mid'])] if r['sheet'] == p[7] and r['row'] == p[8]), {})
        mh = '、'.join(l[1] for l in g['rel'] if l[0] == 'MH')
        lo_, hi_ = f.get('lo'), f.get('hi')
        rng = f"{fmt(lo_)}–{fmt(hi_)}" if lo_ is not None and hi_ is not None else f"≤{fmt(hi_)}" if hi_ is not None else f"≥{fmt(lo_)}" if lo_ is not None else '未提供'
        b_ = g['base'] or []
        bv, cv = _num(b_[1] if b_ else None), _num(p[2])
        btxt = f"基线{b_[1]}{p[3]}{'（正常）' if len(b_) > 3 and b_[3] == 0 else ''}，" if b_ and b_[1] not in (None, '') else ''
        move = '升高至' if bv is not None and cv is not None and cv > bv else '下降至' if bv is not None and cv is not None and cv < bv else '为'
        wf = next((m.group(1) for c in g['ctx'] for m in [re.search(r'较基线(?:进一步)?加重[（：]([^）；]+)', c)] if m), '较基线明显加重')
        if p[6] is not None and re.search(r'较基线(升高|降低)', wf):   # 百分比按所写的这一次计算
            wf = f"较基线{'升高' if p[6] > 0 else '降低'} {abs(p[6]):.0f}%"
        fact = fill(ft, visit=p[0], date=p[1], test=g['test'], raw=p[2], unit=p[3], lo=fmt(f.get('lo')) if f.get('lo') is not None else '—',
                    hi=fmt(f.get('hi')) if f.get('hi') is not None else '—', gtxt=f"，{C.GL} {p[4]}级" if p[4] else '', grade=p[4], gterm=f.get('gterm', ''), rng=rng, gl=C.GL,
                    mh=mh, bvis=b_[0] if b_ else None, braw=b_[1] if b_ else '—', btxt=btxt, move=move, wf=wf)
        if len(P) > 1:                                   # 同类异常其余访视：放在建议前，句子仍以「，」接建议
            fact = fact.rstrip('，') + f"（另有 {len(P) - 1} 次同类异常：{'、'.join(str(x[0]) for x in P[1:4])}{'等' if len(P) > 4 else ''}），"
        row_wb = (p[11] if len(p) > 11 else '') or g.get('wb') or ''
        g['wb'] = row_wb                             # PR-8：证据行归属＝被选行（CS/阈值行）的工作簿（原位回写）
        qk = g.get('qkey', '')
        if row_wb and qk.count('|') >= 4:
            parts = qk.split('|')
            parts[3] = f"{row_wb}:{p[7]}"            # qkey 的 wb:sheet 段与被选行一致
            qk = '|'.join(parts)
        card = {'问题': {'CSX': '判CS但未关联AE或病史', 'MH': '判CS且只关联病史，系统判定较基线加重，未见对应AE', 'NCS2': '数值达CTCAE≥2级但研究者判NCS',
                       'NA': '超出参考范围但未评价临床意义', 'NA2': '数值达CTCAE≥2级但未评价临床意义', 'G2NF': '数值达CTCAE≥2级，该表单没有临床意义评价',
                       'DISW': '研究者归因研究疾病，但较基线明显加重且未记录研究疾病加重AE'}.get(g['risk'], cat),
                '指标': g['test'], '访视': p[0], '数值': f"{p[2]}{p[3] or ''}", '参考范围': rng}
        if cand:
            card['问题'], card['同期已记录AE'] = '判CS未关联检验，同期已有可能对应的AE', '、'.join(re.sub(r'可能对应，但检验页未关联', '', c).replace('同期 ', '') for c in cand)
        if bg:
            card['问题'], card['研究疾病表现'] = '该指标异常可见于研究疾病，但较基线明显加重且未记录AE', re.sub(r'[↑↓]|（医学常识）$', '', bg.split('：')[0])
        if b_ and b_[1] not in (None, ''):
            card['基线'] = f"{b_[1]}{p[3] or ''}" + ('（正常）' if len(b_) > 3 and b_[3] == 0 else '')
        if p[4]:
            card['CTCAE'] = f"{p[4]}级"
        card['研究者判定'] = {2: 'CS', 1: 'NCS', 0: '正常'}.get(p[5], '未评价')
        if g['risk'] in ('MH', 'CSX_DIS', 'DISW') or bg:
            card['较基线'] = wf
        if mh:
            card['已关联病史'] = mh
        if f.get('desc'):
            card['研究者备注'] = str(f['desc'])[:40]
        if len(P) > 1:
            card['其他同类异常访视'] = '、'.join(str(x[0]) for x in P[1:4])
        card['建议动作'] = ask
        new_q(g['sid'], cat, p[7], p[8], p[0], p[1], g['test'], fact, ask, [[x[7], x[8], x[0], g['test']] for x in P], g, qk, card)
    for o in C.others:
        R = o['_rule']
        if o['pr'] < C.A.get('queryMinPr', 3) or R.get('query') is False:
            continue
        ask = R.get('ask') or C.A.get('askByCat', {}).get(o['cat']) or '请核实并更正，或提供医学说明。'
        new_q(o['sid'], o['cat'], o['sh'], o['row'], o['v'], o['d'], o['test'], o['sum'].rstrip('。；，') + '，', ask, [[o['sh'], o['row'], o['v'], o['test']]], o, o.get('qkey', ''),
              {'问题': o['cat'], '事实': o['sum'].rstrip('。；，'), **({'指标': o['test']} if o.get('test') else {}), **({'访视': o['v']} if o.get('v') else {}), '建议动作': ask})
    for m in C.S.get('queries_manual', []) or []:  # MM-written queries: {sid, cat, sh, row, v, d, test, fact, ask}
        if m.get('sid') in C.subj:
            new_q(m['sid'], m['cat'], m.get('sh', ''), m.get('row'), m.get('v'), m.get('d'), m.get('test'), m['fact'], m.get('ask', ''),
                  [[m.get('sh', ''), m.get('row'), m.get('v', ''), m.get('test', '')]], {'q': [], 'cro': ''},
                  f"man|{m['sid']}|{m['cat']}|{wb_sheet(C, m.get('sh', ''))}|{m.get('v', '')}|{m.get('d', '')}|{m.get('test', '')}")
    # 工作台用模型按事实卡撰写的句子（analysis.queryTexts：{qkey: {h: 卡片哈希, text}}）；卡片变了就不用旧句子，回落程序措辞。
    # 同一 qkey 在不同阈值档位的卡片不同时，其余档位的句子存于「qkey#哈希」
    QT_ = C.A.get('queryTexts') or {}
    for q in Q:
        q['card_h'] = hashlib.sha1(json.dumps(q['_cards'], ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        hit = QT_.get(q.get('qkey') or q['id'])
        if not (hit and hit.get('h') == q['card_h']):
            hit = QT_.get(f"{q.get('qkey') or q['id']}#{q['card_h']}")
        if hit and hit.get('h') == q['card_h'] and hit.get('text'):
            q['text'], q['parts'], q['writer'] = hit['text'], [[hit['text'], 0]], 'model'
    for q in Q:                                          # 事实卡自检：基线/数值/较基线百分比必须互相吻合（模型照卡写，错数字会直接进句子）
        for c in q['_cards']:
            m = re.search(r'(升高|降低)\s*(\d+)%', str(c.get('较基线') or ''))
            b, v = _num(re.sub(r'[^\d.\-].*$', '', str(c.get('基线') or ''))), _num(re.sub(r'[^\d.\-].*$', '', str(c.get('数值') or '')))
            if m and b and v is not None and abs(abs((v - b) / b * 100) - int(m.group(2))) > 1.5:
                print(f"WARN  事实卡数值不一致 {q['id']}：基线 {c.get('基线')} 数值 {c.get('数值')} {c.get('较基线')}", file=sys.stderr)
    C.queries = Q
    C.qcommon = dict(common)


# ----------------------------------------------------------------------------- consistency / centers
def build_cons(C):
    tol = C.A.get('consTol', 0.05)
    by = defaultdict(list)
    for (sid, mid), rows in C.F.items():
        if sid not in C.pop:
            continue
        for r in rows:
            if r['post'] and r.get('value') is not None and r.get('clin') in (1, 2) and C.isAgg(r.get('visit')):
                d = 'H' if r.get('hi') is not None and r['value'] > r['hi'] else 'L' if r.get('lo') is not None and r['value'] < r['lo'] else ''
                if d:
                    by[(C.subj[sid]['site'], mid, r.get('unit'), r.get('lo'), r.get('hi'), d)].append(r)
    C.cons = []
    qrows = {(q['sh'], q['row']) for q in C.queries}
    for (site, mid, *_), rs in by.items():
        cs = [r for r in rs if r['clin'] == 2]
        ncs = [r for r in rs if r['clin'] == 1]
        used = set()
        for a in cs:
            best = None
            for b in ncs:
                if b['sid'] == a['sid'] or b['sid'] in used:
                    continue
                if abs(a['value'] - b['value']) <= tol * max(abs(a['value']), 1e-9):
                    if b['value'] == a['value'] or (abs(b['value'] - a['value']) <= abs((best or {'value': 1e18})['value'] - a['value'])):
                        best = b
            if not best:
                continue
            used.add(best['sid'])
            b = best
            st = '已有问题覆盖' if (a['sheet'], a['row']) in qrows or (b['sheet'], b['row']) in qrows else '需核实'
            side = lambda r: [r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', '异常有临床意义' if r['clin'] == 2 else '异常无临床意义',
                              f"{fmt(r.get('lo'))}–{fmt(r.get('hi'))}", r['sheet'], r['row']]
            C.cons.append({'id': f'C{len(C.cons) + 1:03d}', 'site': site, 'test': C.metric[mid]['label'], 'a': a['sid'], 'b': b['sid'],
                           'diff': f"同中心同指标，数值 {a.get('raw')} vs {b.get('raw')} {a.get('unit') or ''}（相差 ≤{int(tol * 100)}%），一例判 CS、一例判 NCS",
                           'st': st, 'why': '同一中心对相近数值的临床意义判定尺度不一致；先核对症状/复查/处置差异，再决定是否质疑。跨例比较只作提示，不以多数判定作为医学标准。',
                           'av': side(a), 'bv': side(b)})


def build_centers(C):
    cen = {}
    for sid, s in C.subj.items():
        c = cen.setdefault(s['site'], {'site': s['site'], 'name': s.get('center') or s['site'], 'n': 0, 'dosed': 0, 'ae': 0, 'aesub': 0, 'csx': 0, 'mhx': 0,
                                       'ncs2': 0, 'labrows': 0, 'q': 0, 'cro': 0, 'aesi': 0, 'g2': 0})
        c['n'] += 1
        if sid in C.pop:
            c['dosed'] += 1
            post = [a for a in C.ae_by[sid] if not a['pre']]
            c['ae'] += len(post)
            c['aesub'] += bool(post)
            c['aesi'] += sum(a['aesi'] for a in post)
            c['g2'] += sum((grade_int(a['g']) or 0) >= 2 for a in post)
    for g in C.labrows:
        c = cen[g['site']]
        if g['risk'] != 'REL':                  # REL 为双阈值候选（pr2），不计入「异常行」负荷
            c['labrows'] += 1
        c['csx'] += g['risk'] == 'CSX'
        c['mhx'] += g['risk'] == 'MH'
        c['ncs2'] += g['risk'] == 'NCS2'
    for q in C.queries:
        cen[q['site']]['q'] += 1
    for x in C.extq:
        s = C.subj.get(x.get('sid'))
        if s:
            cen[s['site']]['cro'] += 1
    C.centers = sorted(cen.values(), key=lambda c: c['site'])


# ----------------------------------------------------------------------------- SoA completeness
def build_soa(C):
    visited = defaultdict(set)
    for v in C.visits:
        if v['sid'] in C.pop and v.get('visit'):
            visited[v['visit']].add(v['sid'])
    cols = [v for v in C.VIS if visited.get(v) and C.isAgg(v)]
    recs = defaultdict(lambda: defaultdict(lambda: [set(), set()]))  # 项目 -> visit -> [done, no]
    names, sheet2grp = {}, {}
    for f in C.findings:
        if f['sid'] not in C.pop or not f.get('visit'):
            continue
        # mm4：按「组」合并同一评估项目的多个 sheet（如按中心拆分的 血常规_1/_2），否则拆表的另一半会被误判为缺失
        sh = f.get('group') or f['sheet']
        names.setdefault(sh, f.get('group') or sh)
        sheet2grp.setdefault(f['sheet'], sh)
        k = 1 if str(f.get('done') or '').startswith('否') else 0
        recs[sh][f['visit']][k].add(f['sid'])
    for e in C.efficacy:
        if e['sid'] in C.pop and e.get('visit'):
            names.setdefault(e['sheet'], e.get('metric') or e['sheet'])
            recs[e['sheet']][e['visit']][0].add(e['sid'])
    spec = C.A.get('soa')  # [{"name","sheet","visits":[..],"cond":bool}]
    if not spec:
        spec = []
        for sh, by in recs.items():
            exp = [v for v in cols if len(by[v][0] | by[v][1]) >= 0.5 * len(visited[v])]
            spec.append({'name': names[sh], 'sheet': sh, 'visits': exp, 'cond': False})
    out = []
    for sp in spec:
        by = recs.get(sp['sheet']) or recs.get(sheet2grp.get(sp['sheet']), {})   # 方案 SoA 可写 sheet 名或组名
        cells = {}
        for v in cols:
            n = visited[v]
            done = (by.get(v) or [set(), set()])[0] & n
            no = (by.get(v) or [set(), set()])[1] & n - done
            if v in sp['visits']:
                miss = n - done - no
                cells[v] = [len(n), len(done), len(no), len(miss), sorted(miss), sorted(no), 0]
            elif done:
                cells[v] = [len(n), len(done), 0, 0, [], [], 1]
        out.append({'name': sp['name'], 'sheet': sp['sheet'], 'exp': sp['visits'], 'cond': sp.get('cond', False), 'cells': cells})
    if spec and any(s.get('cond') for s in spec):
        C.S.setdefault('study', {}).setdefault('soaCond', [s['name'] for s in spec if s.get('cond')])
    C.soa, C.soacols = out, cols


# ----------------------------------------------------------------------------- trend (KZT)
def build_trend(C):
    sids = sorted(C.subj)
    idx = {s: i for i, s in enumerate(sids)}
    subjects = [[s, C.subj[s]['site'], C.subj[s]['center'], 1 if s in C.pop else 0, C.subj[s]['status']] for s in sids]
    metrics, obs, base, qtests, qobs = [], {}, {}, [], {}
    bl = C.cfg.get('baseline', {})
    for mid, m in sorted(C.metric.items(), key=lambda kv: (kv[1]['domain'], kv[1]['group'], kv[0])):
        rows = [r for (sid, mm), rs in C.F.items() if mm == mid for r in rs]
        if m['n'] >= max(1, m['nq']):
            dom = m['domain']
            metrics.append({'id': mid, 'label': m['label'], 'domain': dom, 'group': m['group'], 'note': '',
                            'units': [[u, n] for u, n in m['units'].most_common() if u or n],
                            'baseline': baseline_desc(C, mid)})
            o = []
            for r in rows:
                if r.get('value') is None:
                    continue
                sid = r['sid']
                sd = days(r.get('date'), C.subj[sid]['fd'])
                o.append([idx[sid], r.get('date'), sd, r['value'], r.get('clin'), C.vi(r.get('visit')), r['sheet'], r['row'], 1, 1 if r['isb'] else 0,
                          None if r['chg'] is None else round(r['chg'], 4), None if r['pct'] is None else round(r['pct'], 2), r.get('lo'), r.get('hi'),
                          r.get('raw'), r.get('unit'), 1 if r['post'] else 0, r.get('tpt') or '', r.get('time') or '',
                          None if r.get('dev') is None else round(r['dev'], 4)])
            obs[mid] = o
            b = {}
            for (sid, mm), rs in C.F.items():
                if mm == mid and rs and rs[0]['base'] is not None:
                    x = rs[0]['base']
                    b[idx[sid]] = [x.get('date'), x.get('value'), x.get('unit'), '规定' if x.get('visit') == bl.get(m['domain']) else '替代', x['sheet'], x['row']]
            base[mid] = b
        else:
            qtests.append(m['label'])
            qobs[m['label']] = [[idx[r['sid']], r.get('date'), C.vi(r.get('visit')), r.get('raw')] for r in rows if r.get('raw')]
    C.KZT = {'meta': {'visits': C.VIS}, 'subjects': subjects, 'centers': [[c['site'], c['name']] for c in C.centers], 'metrics': metrics,
             'obs': obs, 'base': base, 'pending': [], 'qual': {'tests': qtests, 'obs': qobs}}
    C.sidx = idx


# ----------------------------------------------------------------------------- efficacy
def eff_num(v):
    """量表取值 → 数值：数字原样；「4=重度」「6分」「43.8」取开头数字；纯文字（如「不是」）→ None。"""
    if isinstance(v, (int, float)):
        return v
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)', str(v or ''))
    return float(m.group(1)) if m else None


def eff_magnitude(C):
    """mm4：有效性指标中检验/检查来源的测量值，同一受试者某次与本人其余访视中位数相差 ≥10 倍 → 疑似单位/录入错误，发 query
    （用户 2026-10-27 确认转 query）；量表不查（改善到接近 0 属正常）。结果同时进有效性页异常列表。"""
    C.effmag = []
    for m in C.A.get('efficacy') or []:
        if m.get('derive') or str(m.get('src', '')).startswith('eff:'):
            continue
        for sid in sorted(C.pop):
            vm = {}
            for r in sorted(C.F.get((sid, m['src']), []), key=lambda r: (C.vi(r.get('visit')), r.get('date') or '')):
                if r.get('value') is None or (m.get('visits') and r.get('visit') not in m['visits']):
                    continue
                if r.get('visit') not in vm or (m.get('agg') == 'max' and r['value'] > vm[r['visit']]['value']):
                    vm[r.get('visit')] = r
            for v, r in vm.items():
                rest = sorted(x['value'] for w, x in vm.items() if w != v and x['value'] > 0)
                if r['value'] > 0 and len(rest) >= 2 and not 0.1 < r['value'] / rest[len(rest) // 2] < 10:
                    t_ = f"{m['label']} {fmt(r['value'])}{m.get('unit', '')}（{v}），本人其余访视中位数 {fmt(rest[len(rest) // 2])}"
                    C.effmag.append({'sid': sid, 'site': C.subj[sid]['site'], 'k': f"{m['label']}量级异常", 'c': 'org', 'v': v, 't': t_,
                                     'st': '核对单位或录入（疑似数量级错误）'})
                    add_other(C, sid, '有效性数据量级异常', 3, f"{v}（{r.get('date')}）{t_}，相差 10 倍以上", v, r.get('date'), r['sheet'], r['row'],
                              m['label'], rule={'id': 'EFF-MAG', 'ask': '疑似单位或录入错误，请核对源文件并更正；如数值无误，请说明原因。'},
                              bkey=f"{m['src']}|mag|{v}", wb=r.get('wb') or '')


def build_eff(C):
    M = C.A.get('efficacy', [])
    data = {}
    by = defaultdict(list)  # (sid, src) -> [(visit,date,value,raw)]
    for e in C.efficacy:
        by[(e['sid'], 'eff:' + str(e.get('metric')))].append((e.get('visit'), e.get('date'), eff_num(e.get('value')), e.get('value')))
    for (sid, mid), rs in C.F.items():
        for r in rs:
            by[(sid, mid)].append((r.get('visit'), r.get('date'), r.get('value'), r.get('raw')))
    C.effsub = defaultdict(dict)
    for m in M:
        src = m['src']
        for sid in sorted(C.pop):  # deterministic eff.data order (set iteration varies per process)
            rs = [x for x in by.get((sid, src), []) if x[2] is not None]
            if not rs:
                continue
            vm = {}
            for v, d, x, raw in sorted(rs, key=lambda t: (C.vi(t[0]), t[1] or '')):
                if m.get('agg') == 'max' and v in vm and x > vm[v][1]:
                    vm[v] = (d, x, raw)                      # mm4：终点取「最大的…」时同访视多条记录取最大值
                else:
                    vm.setdefault(v, (d, x, raw))
            bv = vm.get(m.get('baseVisit'), (None, None, None))[1]
            out = {}
            for v, (d, x, raw) in vm.items():
                if m.get('derive') == 'chg':
                    y = None if bv is None or v == m.get('baseVisit') else x - bv
                elif m.get('derive') == 'pct':
                    y = None if not bv else (0.0 if v == m.get('baseVisit') else (x - bv) / abs(bv) * 100)
                else:
                    y = x
                if y is not None and (not m.get('visits') or v in m['visits']):
                    out[v] = round(y, 3)
            if out:
                data.setdefault(sid, {'sid': sid, 'site': C.subj[sid]['site'], 'v': {}})['v'][m['id']] = out
                C.effsub[sid][m['id']] = [[v, vm[v][0], out[v], vm[v][2]] for v in sorted(out, key=C.vi)]
    anomalies = []
    for R in C.A.get('effRules', []):  # {"metric","op","v","label","cls","st","visits":[..]}
        for sid, e in data.items():
            for v, y in e['v'].get(R['metric'], {}).items():
                if R.get('visits') and v not in R['visits']:
                    continue
                if cmp(R['op'], y, R['v']):
                    m = next(x for x in M if x['id'] == R['metric'])
                    anomalies.append({'sid': sid, 'site': e['site'], 'k': R['label'], 'c': R.get('cls', 'org'), 'v': v,
                                      't': f"{m['label']} {fmt(y)}{m.get('unit', '')}（{v}）", 'st': R.get('st', '核对源数据/测量'), 'qcat': R.get('qcat', [])})
    anomalies += getattr(C, 'effmag', [])
    for m in M:  # key-visit pending: visit happened, value missing
        kv = m.get('keyVisit')
        if not kv or m.get('pending') is False:
            continue
        had = {v['sid'] for v in C.visits if v.get('visit') == kv}
        for sid in had & C.pop:
            if kv not in data.get(sid, {'v': {}})['v'].get(m['id'], {}):
                if C.cfg.get('dataStage') == 'daily':  # 滚动录入阶段：只提示「未见记录」，不当作缺失
                    anomalies.append({'sid': sid, 'site': C.subj[sid]['site'], 'k': f'{kv} {m["label"]}未见记录', 'c': '', 'v': kv,
                                      't': f'{kv} 访视已有记录，但暂未见 {m["label"]}（数据仍在录入中）', 'st': '后续数据更新后复核'})
                else:
                    anomalies.append({'sid': sid, 'site': C.subj[sid]['site'], 'k': f'{kv} {m["label"]}缺失', 'c': '', 'v': kv, 't': f'{kv} 访视已发生，但未见 {m["label"]} 数据', 'st': '核对是否未录入/未评估'})
    C.KZeff = {'metrics': [{k: v for k, v in m.items() if k not in ('src', 'derive', 'baseVisit')} | {'note': m.get('note', '')} for m in M],
               'data': list(data.values()), 'anomalies': anomalies, 'rulesText': C.A.get('effRulesText', ''),
               'notes': C.A.get('effNotes') or []}   # mm4：未生成/未对上的原因（宿主按方案终点×listing 生成）


# ----------------------------------------------------------------------------- subject files
def build_subject_files(C, out):
    doms = {'lab': 'labs', 'vs': 'vs', 'ecg': 'ecg'}
    vis_by = defaultdict(list)
    for v in C.visits:
        vis_by[v['sid']].append([v.get('visit'), v.get('visit'), v.get('date'), v['row']])
    ex_by = defaultdict(list)
    for e in C.exposure:
        ex_by[e['sid']].append({'s': e.get('start'), 'e': e.get('end'), 'n': e.get('dose') or '', 'pause': e.get('pause') or '', 'row': e['row'], 'v': e.get('visit') or ''})
    pr_by = defaultdict(lambda: {'sur': [], 'pr': []})
    for p in C.proc:
        k = 'sur' if re.search('手术', str(p.get('kind') or '手术')) else 'pr'
        pr_by[p['sid']][k].append({'t': p.get('term') or '', 'd': p.get('date') or '', 's': p.get('date') or '', 'why': p.get('why') or ''})
    for sid, s in C.subj.items():
        d = {'id': sid, 'site': s['site'], 'center': s['center'], 'status': s['status'], 'rand': s.get('rand') or '', 'strat': s.get('strat') or '',
             'icf': s.get('icf') or '', 'fd': s['fd'] or '', 'ld': s['ld'] or '', 'lo': s['lo'] or '', 'age': s.get('age'), 'bmi': s.get('bmi'),
             'ht': s.get('ht'), 'wt': s.get('wt'), 'eth': s.get('eth') or '',
             'eot': {'d': s.get('eot_d'), 'why': s.get('eot_why') or ''} if s.get('eot_d') else None,
             'eos': {'d': s.get('eos_d'), 'done': s.get('eos_done') or '', 'why': s.get('eos_why') or ''} if s.get('eos_d') or s.get('eos_done') else None,
             'visits': sorted(vis_by[sid], key=lambda x: (x[2] or '', C.vi(x[0]))), 'ae': [{k: v for k, v in a.items() if not k.startswith('_')} for a in C.ae_by[sid]],
             'mh': C.mh_by[sid], 'cm': C.cm_by[sid], 'ec': ex_by[sid], 'sur': pr_by[sid]['sur'], 'pr': pr_by[sid]['pr'], 'labs': {}, 'vs': {}, 'ecg': {},
             'ext': [], 'eff': C.effsub.get(sid, {}), 'tl': [{'lane': k, 'pts': v} for k, v in C.tl.get(sid, {}).items()]}
        extg = defaultdict(list)
        for (s2, mid), rows in C.F.items():
            if s2 != sid:
                continue
            dom = mid.split(':')[0]
            if dom in doms:
                d[doms[dom]][C.metric[mid]['label']] = [[r.get('date'), r.get('visit'), r.get('value'), r.get('raw'), r.get('unit') or '', r.get('lo'), r.get('hi'),
                                                        r.get('clin'), r.get('desc') or '', r['sheet'], r['row'], r.get('tpt') or '', r.get('time') or '', 1 if r.get('isb') else 0] for r in rows]
            else:
                extg[rows[0].get('group') or dom].extend(rows)
        for g, rows in extg.items():
            rows.sort(key=lambda r: (r.get('date') or '', r['test']))
            tests = list(dict.fromkeys(r['test'] for r in rows))
            vis = list(dict.fromkeys(r.get('visit') for r in rows))
            def pc(r):
                if r['pct'] is None:
                    return ['基线', ''] if r['isb'] else ''
                c = 'red' if abs(r['pct']) >= C.A.get('extFlagPct', 50) else ''
                return [f"{r['pct']:+.1f}%", c]
            d['ext'].append({'title': g, 'note': '较基线变化 = 相对规定基线', 'cols': ['项目', '访视', '日期', '结果', '较基线'], 'numFrom': 3,
                             'rows': [[r['test'], [r.get('visit'), 'blu'], r.get('date'), f"{r.get('raw') or ''} {r.get('unit') or ''}".strip(), pc(r)] for r in rows],
                             'chart': {'x': vis, 'series': [{'name': t, 'data': [next((r.get('value') for r in rows if r['test'] == t and r.get('visit') == v), None) for v in vis]} for t in tests[:4]]}
                             if any(r.get('value') is not None for r in rows) else None})
        Path(out, 's').mkdir(parents=True, exist_ok=True)
        Path(out, 's', f'{sid}.js').write_text('KZ_SUB(' + json.dumps(d, ensure_ascii=False, separators=(',', ':'), default=str) + ');', encoding='utf-8')


# ----------------------------------------------------------------------------- evidence rows (KZX.ex)
def build_ex(C):
    import openpyxl
    sheets = C.src.get('sheets', {})
    wbs = {}
    need = defaultdict(set)
    for q in C.queries:
        for e in q['ev']:
            if e[0] in sheets and e[1]:
                need[e[0]].add(e[1])
    pd_items = ((C.pdd or {}).get('potential') or []) + ((C.pdd or {}).get('confirmed') or [])
    for it in pd_items:                                  # mm4：方案偏离抽屉的源行原文
        for e in it.get('src') or []:
            sh = ev_sh(C, e[0]) if e[0] else ''
            if sh in sheets and e[1]:
                need[sh].add(e[1])
    rows = {}
    for sh, rs in need.items():
        meta = sheets[sh]
        path = C.src['workbooks'][meta['wb']]
        wb = wbs.get(path) or openpyxl.load_workbook(path, read_only=True, data_only=True)
        wbs[path] = wb
        ws = wb[meta['sheet']]   # PR-8: sheets keyed by unique id — open by plain sheet name
        labels = None
        for i, r in enumerate(ws.iter_rows(values_only=True), start=1):
            if i == meta['label_row']:
                labels = [str(x) if x is not None else f'col{j + 1}' for j, x in enumerate(r)]
            if i in rs and labels:
                rows[(sh, i)] = {labels[j]: ('' if v is None else str(v)[:120]) for j, v in enumerate(r) if j < len(labels) and v not in (None, '')}
    ex = {}
    for q in C.queries:
        rr = [{'sh': e[0], 'row': e[1], 'f': rows[(e[0], e[1])], 'hl': [h for h in sheets.get(e[0], {}).get('hl', []) if h in rows[(e[0], e[1])]]}
              for e in q['ev'] if (e[0], e[1]) in rows]
        if rr:
            ex[q['id']] = {'q': q['id'], 'sid': q['sid'], 'rows': rr[:6], 'cro': [{'sheet': x.get('form') or '', 'row': x.get('row'), 'text': x.get('text') or ''}
                                                                                    for x in C.extq if x.get('sid') == q['sid'] and q['_cro'] and x.get('text') == q['_cro']]}
    pdex = {}
    for it in pd_items:
        rr = []
        for e in it.get('src') or []:
            sh = ev_sh(C, e[0]) if e[0] else ''
            if (sh, e[1]) in rows:
                rr.append({'sh': sh, 'row': e[1], 'lab': e[2] if len(e) > 2 else '', 'f': rows[(sh, e[1])],
                           'hl': [h for h in sheets.get(sh, {}).get('hl', []) if h in rows[(sh, e[1])]]})
        if rr:
            pdex[it['id']] = rr[:6]
    return ex, pdex


# ----------------------------------------------------------------------------- defaults for taxonomy / review / methods / todo
BUILTIN_METHODS = [
    ('M01', 'CS 未关联 AE/MH', '检验/VS/ECG 页结果、参考范围、临床意义、动态关联字段', '给药后新发或加重的异常被判 CS，但关联字段为空 → 漏报 AE 风险最高', '漏报 AE', '发 query：请评估记录 AE 或补充病史并关联'),
    ('M02', 'CS 仅关联病史', '同上 + 病史页', '仅关联 MH 时比较给药后与规定基线的等级/数值，加重者提示应记 AE', '以病史替代 AE', '较基线加重者发 query；同级者仅提示'),
    ('M03', 'NCS 但 {GL} ≥2 级', '数值 + {GL} 数值条目', '数值达 ≥2 级仍判 NCS 时请研究者说明依据；无 {GL} 数值条目者不自动分级', '判定尺度偏松', '发 query：说明依据或更正'),
    ('M04', '基线定义', '方案规定的基线（指定访视、首次给药或随机前最近一次、或多次均值，可按指标分别规定）', '规定基线缺失时按规则回退（默认首剂前最近有效值）并注明「替代基线」', '基线错配', '仅提示，不单独发 query'),
    ('M05', '同中心判定一致性', '同中心同指标同单位/范围/方向，数值相差 ≤5%', '一例 CS 一例 NCS 时提示判定尺度不一致；不以多数判定作为标准', '中心判定偏差', '先核对症状/复查/处置差异'),
    ('M06', '方案阈值专项', '方案规定的 AE/AESI/停药/回看阈值', '方案原文定义的 AE/AESI/停药/回看阈值逐点比对，并核对是否有对应 AE/AESI 记录', '漏报 AESI', '按方案要求的严重程度决定是否发质疑'),
    ('M07', 'AE 记录质量', 'AE 页', '给药前事件相关性、AE 等级 vs 关联检验 {GL} 等级、合并用药标记、AESI 标记、同术语重叠记录', '记录不一致', '发 query 或提示'),
    ('M08', '禁限用药 / 洗脱期', 'CM 页 + 方案禁用药清单', '按方案禁用药名单匹配药名＋用药时段与首剂前窗口/治疗期重叠；洗脱期按知情/首剂回推', '方案偏离', '发 query 并核对 PD listing'),
    ('M09', '入排关键数值', '筛选期检验/人口学', '筛选期数值符合排除标准但已随机/给药', '入组不合格', '优先核实'),
    ('M10', '访视窗', '访视页日期', '研究日 = 访视日 − 首剂日 + 1；按方案窗判断', '超窗', '提示 / 核对 PD'),
    ('M11', '中心偏离', '中心层面汇总（不含计划外/提前退出访视）', '漏斗图 ±2SE 需关注 / ±3SE 明显偏离；n<2 不判', '中心系统性偏差', '中心层面沟通，不对个例发 query'),
    ('M13', '多指标组合规则', '方案规定的组合判定标准（如 Hy’s law）', '方案定义的组合标准（如 Hy’s law：ALT/AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN）同日/窗口内同时满足', '漏报 AESI/SAE', '按方案要求的严重程度决定是否发质疑'),
    ('M14', 'AE/SAE/AESI 报告时限', 'AE 页（获知/报告日期）＋方案规定的报告时限', '报告日期 − 获知（或发生）日期 > 方案时限', '报告延迟', '发 query 或提示'),
    ('M12', '有效性数据合理性', '方案终点对应的 EDC 量表/检验/检查', '按方案终点定义派生（绝对值/较基线/百分比），离群与关键访视缺失提示；盲态下不分组', '终点数据质量', '核对源数据/测量'),
    ('M15', '方案偏离·执行层面', '知情同意记录、访视日期、SoA 各评估、给药记录（日期/时刻/途径/空腹/数量）、样本采集时刻', '按方案访视窗与锚点、SoA、给药与样本时点、知情时序逐受试者推断潜在偏离（程序早于知情、未再次知情、访视超窗/缺失、评估缺失/未做、访视内顺序、给药前样本晚于给药、依从性、停药后给药）；关键访视/关键评估升级为重要；方案未给出参数或 listing 缺字段的检查不执行，并写明原因', '方案执行偏离', '发 query 或交 CRA 核实；属实录入 PD log'),
    ('M16', '方案偏离·科学层面', '入排数值、合并用药与禁用清单、检验异常与 AE/病史、停药阈值、SAE 报告日期', '入排不符仍入组（入组前末次有效值）、洗脱期不足、禁用药、潜在 AE 漏记（CS 未关联 AE 或病史加重）、SAE/AESI 报告超时、达停药标准未停药；重要＝可能显著影响受试者权益/安全/福祉或关键数据可靠性（ICH E3 Q&A R1；E6(R3)）', '入组/用药/安全报告偏离', '按分级：重要优先核实；潜在 AE 漏记先发 query'),
    ('M17', '已记录 PD 比对与分级', 'PD listing（类别、描述、日期、严重程度）', '原文类别归一到统一分类，严重/轻微/根据实际情况判定 → 重要/一般/待判定；与潜在 PD 按同受试者、同类别、日期 ±窗口逐事件比对：已记录 / 未见记录', 'PD 漏录、分级不一致', '未见记录的潜在 PD 交 CRA 核实后补录'),
]


# 审阅要点各专项域的判读路径与核查方法（旧版所有域共用「方案原文→阈值/窗口/药名」一条路径，检验记录质量挂到入排/访视方法卡）
DOMAIN_FLOW = {
    '方案阈值专项': ([['方案原文', '方案规定的阈值/组合标准'], ['逐点比对', '达到阈值的检验结果'], ['对应记录', '是否已记录 AE/AESI'], ['处理', '按严重程度发质疑或提示']], ['M06', 'M13']),
    '合并用药': ([['方案禁用清单', '药名与禁用时段'], ['用药记录', '用药起止与首剂/治疗期是否重叠'], ['用药原因', '是否有对应病史/AE'], ['处理', '发质疑并核对方案偏离']], ['M08']),
    '入排/访视': ([['方案入排与访视窗', '数值条件、访视目标日与窗口'], ['逐受试者比对', '入组前末次值、实际访视日'], ['处理', '核实入组资格/超窗原因']], ['M09', 'M10']),
    '检验记录质量': ([['记录完整性', '参考范围、单位、临床意义是否填写'], ['判定一致性', '相近结果的临床意义判定是否一致'], ['处理', '请中心补充或统一判定']], ['M05']),
    '检验异常·绑定核查': ([['关联字段', '检验记录关联的 AE/病史是否存在、是否对应'], ['时间与方向', '异常与关联事件的时间、升降方向'], ['处理', '请核实关联或补充记录']], ['M01', 'M02']),
}


def calibers(C):
    """研究依据页「关键口径」（study.calibers，未手写时由配置推导）：[[主题, 采用口径, 状态, 规则id, 说明]]。
    状态：方案规定（规则库有对应原文）/ 口径裁定（study.consensus）/ 待确认（unres 点名）/ 默认采用（方案未规定，按 skill 默认）。"""
    ST = C.S.setdefault('study', {})
    if ST.get('calibers'):
        return
    A, cfg, R = C.A, C.cfg, C.S.get('rules') or []
    unres = ' '.join(str(u) for u in (C.S.get('unres') or []))

    def rid(pat):
        return next((r['id'] for r in R if re.search(pat, f"{r.get('id', '')} {r.get('dom', '')} {r.get('st', '')}", re.I)), '')

    def row(topic, val, pat, note='', key=None, configured=True):
        r = rid(pat) if pat else ''
        # 有方案规则但口径未落到配置（例如方案未写基线取值方法）→ 待确认，而不是把 skill 默认值标成「方案规定」
        stt = '待确认' if re.search(key or topic, unres) or (r and not configured) else ('方案规定' if r else ('项目约定' if configured else '报告默认做法'))
        return [topic, val, stt, r, note]
    rows = []
    pop = {'dosed': '已给药受试者（至少一次给药）', 'randomized': '已随机受试者', 'all': '全部筛选受试者'}.get(A.get('population', 'dosed'), A.get('population'))
    rows.append(row('分析人群', pop, r'人群|分析集|population', '筛选失败只在列表中展示', configured='population' in A))
    bl = '；'.join(b.get('label') or f"{b.get('match')}：{ {'visit': '指定访视', 'lastPre': '首剂前最近有效值', 'mean': '多次均值'}.get(b.get('method'), b.get('method'))}"
                  + (f"（{'/'.join(b.get('visits') or [])}）" if b.get('visits') else '') for b in (cfg.get('baselineRules') or []))
    if not bl and cfg.get('baseline'):
        bl = '；'.join(f"{k}：{v}" for k, v in cfg['baseline'].items() if not k.endswith('Tpt') and k != 'labLabel')
    rows.append(row('基线定义', bl or '首次给药前最近一次有效值（报告默认）', r'^R-BL-|^R-BASE-|基线定义|基线 *[=：]', '规定的基线缺失时用首次给药前最近一次有效值替代，并标「替代基线」', configured=bool(bl)))
    rows.append(row('分级标准', C.GL, r'CTCAE|分级标准|毒性分级', '无数值条目或单位不可换算的指标不自动分级'))
    ap = A.get('aePeriod') or {}
    ref = {'ld': '末次给药', 'fd': '首次给药', 'eos_d': '研究结束访视', 'lo': '末次观察'}
    rows.append(row('AE 收集期', (f"至{ref.get(ap.get('ref'), ap.get('ref'))}" + (f"后 {ap.get('days')} 天" if ap.get('days') else '')) if ap else '方案未规定（全程）', r'收集期|AE.{0,6}收集|TEAE', '收集期后的检验异常不生成漏报风险', configured=bool(ap)))
    te = A.get('teae') or {}
    rows.append(row('TEAE 定义', f"首剂后至{ref.get(te.get('ref'), te.get('ref'))}后 {te.get('days')} 天内发生或加重" if te else '首剂后发生或加重', r'TEAE|治疗期间出现', '', configured=bool(te)))
    rr = '；'.join(x.get('label') or f"{x.get('flag')} {x.get('days')} 天" for x in (A.get('reportRules') or []))
    rows.append(row('报告时限', rr or '方案未规定', r'24\s*小时|报告时限|获知后', '', configured=bool(rr)))
    bd = cfg.get('blind') or {}
    rows.append(row('盲态', (bd.get('tag') or '盲态') + '：不展示分组与分组对比' if bd.get('on') else '非盲', r'双盲|盲法|设盲', ''))
    W = A.get('visitWindows') or {}
    anc = sorted({(w.get('anchor', 'fd') if isinstance(w, dict) else 'fd') for w in W.values()})
    an = {'fd': '首剂', 'rand': '随机', 'icf': '知情同意', 'ld': '末次给药'}
    rows.append(row('访视窗锚点', f"{len(W)} 个访视；锚点：{'、'.join(an.get(a, '前一访视 ' + a) for a in anc)}" if W else '未配置访视窗', r'^R-VW|访视窗|时间窗', '', configured=bool(W)))
    rows.append(['计划外 / 提前退出访视', '不纳入汇总、中心统计与访视均值；个例页保留并标注', '报告默认做法', '', '避免计划外复查拉偏访视均值'])
    TH = cfg.get('thresholds') or {}
    rows.append(['较基线显著变化', f"超出参考范围 ≥{float(TH.get('dev', .3)):.0%} 且较基线同向变化 ≥{float(TH.get('base', .3)):.0%}（AE/MH 风险页可切换 20%/30%/50%）", '报告默认做法', '', '已关联 AE/病史的单独标注，未关联的才计入需关注'])
    dp = ST.get('diseaseProgressionNotAE') or {}
    if dp:
        rows.append(['研究疾病进展不作 AE', '已确认' if dp.get('confirmed') else '方案有条款，待确认', '方案规定' if dp.get('confirmed') else '待确认', '', dp.get('quote', '')[:60]])
    for c in ST.get('consensus') or []:
        rows.append([c[0], c[2], '口径裁定', c[4] if len(c) > 4 else '', c[1]])
    ST['calibers'] = rows


def defaults(C):
    cfg = C.cfg
    tax = cfg.setdefault('taxonomy', {})
    if not tax.get('domains'):
        cats = list(dict.fromkeys(o['cat'] for o in C.others))
        grp = defaultdict(list)
        for c in cats:
            k = ('不良事件记录' if c.startswith('AE') or 'AESI' in c else '合并用药' if '用药' in c else '入排/访视' if re.search('入排|访视', c)
                 else '检验异常·绑定核查' if re.search(r'CS|关联|研究疾病|病史', c) else '检验记录质量' if re.search(r'参考范围|定性|未评价|判定不一致|量级异常', c) else '方案阈值专项')
            grp[k].append(c)
        col = {'方案阈值专项': 'red', '不良事件记录': 'org', '合并用药': 'brn', '入排/访视': 'blu', '检验异常·绑定核查': 'org', '检验记录质量': ''}
        tax['domains'] = [[k, v, col.get(k, '')] for k, v in grp.items()] + [['检验异常', list(dict.fromkeys(QT[k][0] for k in QT)), 'org']]
    meths = C.S.get('methods') or [{'id': m[0], 'domain': m[1].replace('{GL}', C.GL), 'data': m[2].replace('{GL}', C.GL), 'principle': m[3].replace('{GL}', C.GL),
                                    'risk': m[4], 'action': m[5], 'source': '报告内置核查方法'} for m in BUILTIN_METHODS]
    # 双阈值方法学卡（F-THR-7：方法学页写入当前 T_dev/T_base；选择器档位变化时以顶栏/信息条为准）
    TH = C.cfg['thresholds']
    _pm = TH.get('per_metric') or {}
    _tight = '；'.join(f"{t2.get('metric')}→dev {float(t2['dev']):.0%}" for t2 in C.mthr if t2.get('dev') is not None) + \
             ''.join(f"；{t2.get('metric')}→base {float(t2['base']):.0%}" for t2 in C.mthr if t2.get('base') is not None)
    meths.insert(0, {'id': 'M-THR', 'domain': '较基线显著变化',
                     'data': '检验、生命体征、心电图数值：超出参考范围的幅度，以及与基线相比的同向变化',
                     'principle': (f"给药后超出参考范围 ≥{float(TH['dev']):.0%} 且较基线同向变化 ≥{float(TH['base']):.0%} 时列为「较基线显著变化」"
                                   "（阈值可在 AE/MH 风险页切换 20%/30%/50%）；在参考范围内的变化不计；已关联 AE/病史的单独标注，只有未关联的计入需关注"
                                   + (f"；{len(_pm)} 项指标使用本研究单独设定的阈值" if _pm else "")
                                   + (f"；本研究对部分指标收紧阈值：{_tight}" if C.mthr else "")),
                     'risk': '漏检显著变化', 'action': '仅提示，不自动发质疑；由医学监察员结合临床判断',
                     'source': '报告内置核查方法'})
    C.methods = meths
    if C.S.get('review'):
        C.review = C.S['review']
    else:
        qby = defaultdict(list)
        for q in C.queries:
            qby[q['cat']].append(q['id'])
        def ex_for(cats, n=3):
            out = []
            for c in cats:
                for qid in qby.get(c, [])[:n]:
                    out.append([qid, c, ''])
            return out[:4]
        lr = lambda k: sum(g['risk'] == k for g in C.labrows)
        low = [c for c in C.centers if c['dosed'] >= 2 and c['ae'] / c['dosed'] <= 0.5]
        aecats = [d for d in tax['domains'] if d[0] == '不良事件记录']
        C.review = [
            {'k': 'ae', 't': '不良事件', 'sh': sorted({a['sh'] for a in C.aes})[:3], 'ib': [k for k in list(C.aesum)[:3]],
             'f': ['术语', '开始/结束日期', '严重程度', '与研究药物关系', 'AESI / SAE', '措施 · 转归', '合并用药'],
             'flow': [['首剂日期', '暴露页首次实际给药'], ['归类', '给药前 / TEAE / 病史'], ['等级对照', f'同期检验 {C.GL} 等级'], ['处置一致', 'CM / 措施 / 转归']],
             'ab': {'个体': [['AE 记录核对', 'org', f"{sum(1 for o in C.others if o['cat'] in (aecats[0][1] if aecats else []))} 条信号"]],
                    '中心': [['AE/给药比', 'red', '≤0.5 例次/人：' + ('、'.join(f"{c['site']}（{c['dosed']}人/{c['ae']}次）" for c in low) or '无')]],
                    '全局': [['AE 谱', 'blu', '、'.join(f"{k} {v['n']}" for k, v in list(C.aesum.items())[:5])]]},
             'ex': ex_for(aecats[0][1] if aecats else []), 'm': ['M07'], 'r': [], 'todo': [], 'go': [['safety.html#tab=ae', 'AE 明细'], ['timeline.html', '时间线']]},
            {'k': 'lab', 't': '检验→AE/MH', 'sh': sorted({g['pts'][0][7] for g in C.labrows})[:4], 'ib': [],
             'f': ['结果 · 单位 · 参考范围', '临床意义评价（CS/NCS）', '异常描述', '病史/不良事件关联'],
             'flow': [['规定基线', '按方案基线定义（指定访视/首剂前最近/多次均值）；缺失时按规则回退'], ['数值等级', C.GL + '（基线异常按基线倍数）'], ['CS/NCS', '与数值、症状、处置对照'], ['关联对象', '同一疾病、时间吻合'], ['加重判断', '仅关联病史者比较基线']],
             'ab': {'个体': [['CS·未关联', 'solid-red', f"{lr('CSX')} 行"], ['CS·仅MH·较基线加重', 'org', f"{lr('MH')} 行"], ['NCS·≥2级', 'yel', f"{lr('NCS2')} 行"]] + ([['未评价·≥2级', 'yel', f"{lr('NA2')} 行"]] if lr('NA2') else []),
                    '中心': [['同值异判', 'yel', f"{len(C.cons)} 组比较，{sum(c['st'] == '需核实' for c in C.cons)} 组需核实"]],
                    '全局': [['相对变化', 'line', f'无 {C.GL} 数值条目的指标仅作筛查，不改写 NCS']]},
             'ex': ex_for(list(dict.fromkeys(QT[k][0] for k in QT))), 'm': ['M01', 'M02', 'M03', 'M04', 'M05'], 'r': [], 'todo': [], 'go': [['safety.html#tab=lab', '待核异常明细'], ['objective.html', '检验趋势']]}]
        for d in tax['domains']:
            if d[0] in ('不良事件记录', '检验异常'):
                continue
            n = sum(o['cat'] in d[1] for o in C.others)
            C.review.append({'k': 'd' + str(len(C.review)), 't': d[0], 'sh': sorted({o['sh'] for o in C.others if o['cat'] in d[1] and o['sh']})[:4], 'ib': [], 'f': d[1],
                             'flow': DOMAIN_FLOW.get(d[0], DOMAIN_FLOW['方案阈值专项'])[0],
                             'ab': {'个体': [[c, 'org', f"{sum(o['cat'] == c for o in C.others)} 条"] for c in d[1]]}, 'ex': ex_for(d[1]),
                             'm': DOMAIN_FLOW.get(d[0], DOMAIN_FLOW['方案阈值专项'])[1], 'r': [], 'todo': [],
                             'go': [['safety.html#tab=oth', f'专项核查 {n} 条']]})
        P = C.pdd or {}
        if P:
            pot, conf = P.get('potential') or [], P.get('confirmed') or []
            tx = {x[0]: x for x in P.get('taxonomy') or []}
            cc = Counter(x['cat'] for x in pot)
            dosed = Counter(C.subj[s]['site'] for s in C.pop)
            rate = sorted(((sum(1 for x in pot if x['site'] == s) / n, s) for s, n in dosed.items() if n), reverse=True)[:3]
            exs = [x for x in pot if x['grade'] == '重要'][:2] + [x for x in pot if x['layer'] == '执行' and x['grade'] != '重要'][:2]
            C.review.append({'k': 'pd', 't': '方案偏离', 'sh': sorted({s[0] for x in pot + conf for s in (x.get('src') or []) if s and s[0]})[:4], 'ib': [],
                             'f': ['知情日期/版本', '访视日期', 'SoA 评估', '给药日期/时刻/剂量', '样本采集时刻', '合并用药', '入排数值', 'PD listing'],
                             'flow': [['方案参数', '访视窗与锚点、SoA、给药/样本时点、禁用药、入排'], ['逐受试者推断', '执行层面＋科学层面规则'], ['分级', '重要 / 待判定 / 一般，附依据'],
                                      ['逐事件比对', 'PD listing：已记录 / 未见记录'], ['处理', '发 query / CRA 核实 / 录入 PD']],
                             'ab': {'个体': [[tx.get(c, [c, c])[1], 'red' if any(x['grade'] == '重要' and x['cat'] == c for x in pot) else 'org', f"{n} 条"] for c, n in cc.most_common(6)],
                                    '中心': [['每例潜在 PD', 'org', '、'.join(f"{s}（{r:.2f}）" for r, s in rate) or '无']],
                                    '全局': [['已记录 vs 潜在', 'blu', f"已记录 {len(conf)}；潜在 {len(pot)}（未见记录 {sum(1 for x in pot if x['status'] == '未见记录')}）"]]},
                             'ex': [['pd:' + x['id'], x['title'], ''] for x in exs], 'm': ['M15', 'M16', 'M17'], 'r': [], 'todo': [],
                             'go': [['deviations.html', '方案偏离'], ['deviations.html#tab=rules', '检查规则与覆盖']]})
        if C.KZeff['metrics']:
            C.review.append({'k': 'eff', 't': '有效性', 'sh': sorted({e['sheet'] for e in C.efficacy})[:4], 'ib': [], 'f': [m['label'] for m in C.KZeff['metrics']],
                             'flow': [['终点定义', '方案原文派生'], ['基线', m.get('baseVisit', '') if (m := (C.A.get('efficacy') or [{}])[0]) else ''], ['合理性', '离群 / 缺失'], ['盲态', '不分组']],
                             'ab': {'个体': [[a, 'org', f"{n} 条"] for a, n in Counter(x['k'] for x in C.KZeff['anomalies']).items()]}, 'ex': [], 'm': ['M12'], 'r': [], 'todo': [],
                             'go': [['efficacy.html', '有效性趋势']]})
    if not C.S.get('todo'):
        C.todo = [['CS·未关联', 'solid-red', f"{sum(g['risk'] == 'CSX' for g in C.labrows)} 行判CS但未关联AE/MH", 'safety.html#tab=lab&risk=CSX'],
                  ['优先核实', 'red', f"{sum(o['pr'] == 4 for o in C.others)} 条专项信号优先核实", 'safety.html#tab=oth'],
                  ['AESI', 'red', f"{sum(a['aesi'] for a in C.aes if not a['pre'])} 例次 AESI", 'safety.html#tab=ae&aesi=1'],
                  ['一致性', 'grn', f"同中心判定对照 {len(C.cons)} 组：需核实 {sum(c['st'] == '需核实' for c in C.cons)}", 'safety.html#tab=cons'],
                  ['质疑', 'org', f"{len(C.queries)} 条医学质疑已写入交付表格", 'queries.html']]
        an = Counter(x['k'] for x in C.KZeff['anomalies'])
        if an:
            C.todo.insert(4, ['有效性', 'blu', '；'.join(f'{k} {v}' for k, v in an.most_common(2)), 'efficacy.html'])
        pot = (C.pdd or {}).get('potential') or []
        if pot:
            C.todo.insert(1, ['方案偏离', 'red', f"潜在 PD {len(pot)} 条：重要 {sum(1 for x in pot if x['grade'] == '重要')}，未见记录 {sum(1 for x in pot if x['status'] == '未见记录')}", 'deviations.html'])
    else:
        C.todo = C.S['todo']
    if getattr(C, 'todo_hint', ''):                 # 扩展规则词表缺失 → 待办区提示（D-P5-2 fail-visible，不覆盖默认）
        C.todo.append(['词表', 'yel', C.todo_hint, 'methods.html'])


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', required=True)
    ap.add_argument('--norm', required=True)
    ap.add_argument('--out', required=True, help='site data dir, e.g. out/site/data')
    ap.add_argument('--audit', default=None, help='dir for analysis json (default: <out>/../../analysis)')
    a = ap.parse_args()
    C = load(a.study, a.norm)
    KZ, csb_candidates = analyze(C)
    out = Path(a.out)
    aud = Path(a.audit) if a.audit else out.parent.parent / 'analysis'
    KZ['cfg']['thrTiers'] = tier_variants(a, KZ, out, aud)
    write_outputs(C, KZ, csb_candidates, out, aud)


# 用户 2026-10-28：阈值切换后整份报告（各页列表、计数、质疑、潜在 PD）都要跟着变。T_base 影响构建期分层（较基线加重/研究疾病加重/
# 判定不一致等）及其质疑与潜在 PD，页面无法即时重算，故构建时每档各算一遍；页面按所选档位载入（assets/kz-tier.js）。
THR_TIERS = (0.2, 0.3, 0.5)
TIER_KEYS = ('labrows', 'others', 'queries', 'subs', 'pd', 'centers', 'cons')   # 随 T_base 变化的数据；todo/unres 由工作台追加，不覆盖


def tier_variants(a, KZ, out, aud):
    """非默认档各重跑一遍分析；只写与默认档不同的键（core.b20.js 等），查询事实卡另存 query_cards.b20.json 供工作台撰写。"""
    b0 = float(KZ['cfg']['thresholds'].get('base', 0.3))
    files = {}
    for tb in THR_TIERS:
        if abs(tb - b0) < 1e-9:
            continue
        C = load(a.study, a.norm)
        C.cfg['thresholds']['base'] = tb
        V, _ = analyze(C)
        diff = {k: V[k] for k in TIER_KEYS if V.get(k) != KZ.get(k)}
        diff['meta'] = {'qs': V['meta']['qs']}
        name = f'core.b{round(tb * 100)}.js'
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / name).write_text(f'window.KZV={{"{tb}":' + json.dumps(diff, ensure_ascii=False, separators=(',', ':'), default=str) + '};',
                                      encoding='utf-8')
        files[str(tb)] = name
        dump_json(query_cards(C), Path(aud) / f'query_cards.b{round(tb * 100)}.json')
        print(f"tier T_base={tb:.0%}: queries {len(V['queries'])} · labrows {len(V['labrows'])} · pd {len((V.get('pd') or {}).get('potential') or [])}")
    return files


def query_cards(C):
    return [{'qkey': q.get('qkey') or q['id'], 'id': q['id'], 'cat': q['cat'], 'h': q['card_h'], 'cards': q['_cards'], 'text': q['text'],
             'writer': q.get('writer', 'template')} for q in C.queries]   # 交工作台撰写（模型只措辞，不判定）


def analyze(C):
    """全部分析（确定性）：返回 (KZ, csb_candidates)。不写文件。"""
    C.others, C.tl = [], defaultdict(dict)
    mt = {}
    for T in C.mthr:                                   # 收紧映射（供前端 K.thrOf 折叠；quote 不进页面数据）
        if not T.get('metric'):
            continue
        for mid in C.metric:
            if re.search(T['metric'], mid):
                e = mt.setdefault(mid, {})
                if T.get('dev') is not None:
                    e['dev'] = min(e.get('dev', 1), float(T['dev']))
                if T.get('base') is not None:
                    e['base'] = min(e.get('base', 1), float(T['base']))
    C.cfg['metricTight'] = mt
    build_subjects(C)
    build_events(C)
    ae_summary(C)
    build_findings(C)
    build_labrows(C)
    rel_candidates(C)
    threshold_rules(C)
    combo_rules(C)
    ae_checks(C)
    cm_checks(C)
    eligibility_checks(C)
    range_checks(C)
    visit_window_checks(C)
    pd_reconcile(C)
    csb_candidates = ext_rules.run(C)                    # M13–M23 确定性＋日期序＋CSB 候选（PR-5）
    C.others.sort(key=lambda o: (-o['pr'], o['cat'], o['sid'], o['d']))
    eff_magnitude(C)
    build_queries(C)
    build_cons(C)
    build_centers(C)
    build_soa(C)
    calibers(C)
    pd_rules.run(C)                                      # mm4：方案偏离（已记录 PD 归一＋潜在 PD＋分级＋比对）→ KZ.pd
    build_trend(C)
    build_eff(C)
    defaults(C)
    S = C.subj
    stc = Counter(s['status'] for s in S.values())
    subs = []
    for sid, s in S.items():
        ae = [x for x in C.ae_by[sid] if x['te']]
        subs.append([sid, s['site'], s['status'], s.get('rand') or '', s['fd'] or '', s.get('age'), s.get('bmi'), len(ae), max([grade_int(x['g']) or 0 for x in ae] + [0]),
                     sum(x['sae'] for x in ae), sum(x['aesi'] for x in ae), sum(x['_rel'] for x in ae), len(C.mh_by[sid]), len(C.cm_by[sid]),
                     sum(q['sid'] == sid for q in C.queries), sum(x.get('sid') == sid for x in C.extq), s.get('icf') or '', s['lo'] or '', s.get('strat') or '', s['ld'] or '', s.get('grp')])
    alld = [d for d in (f.get('date') for f in C.findings) if is_full_date(d)]
    cutoff = C.cfg.get('study', {}).get('cutoff') or (max(alld) if alld else '')
    ibtag = C.S.get('ibtag') or {}
    sn = dict(C.A.get('formNames') or {})
    for f in C.findings:
        sn.setdefault(f.get('sheet'), f.get('group') or '')
    for dom, nm in (('ae', '不良事件'), ('mh', '病史'), ('cm', '合并用药'), ('exposure', '给药记录'), ('visits', '访视')):
        for r in getattr(C, dom):
            sn.setdefault(r.get('sheet'), nm)
    C.cfg['sheetNames'] = {k: v for k, v in sn.items() if k and v and v != k}
    KZ = {'cfg': C.cfg, 'meta': {'cutoff': cutoff, 'qs': len(C.queries), 'counts': {k: len(getattr(C, k)) for k in ('subjects', 'visits', 'exposure', 'ae', 'mh', 'cm', 'findings', 'efficacy', 'pd', 'extq')},
                                 'status': dict(stc), 'n': len(S), 'centers': len(C.centers), 'dosed': len(C.pop), 'built': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
                                 'sources': C.cfg.get('footer', {}).get('left', '')},
          'subs': subs, 'centers': C.centers, 'aes': [{k: v for k, v in x.items() if not k.startswith('_') and k != 'sh'} for x in C.aes if x['sid'] in C.pop],
          'aesum': C.aesum, 'aecat': list(C.aesum), 'ibtag': ibtag, 'labrows': [{k: v for k, v in g.items() if k != 'mid' or g.get('risk') == 'REL'} for g in C.labrows],
          'others': [{k: v for k, v in o.items() if not k.startswith('_')} for o in C.others],
          'queries': [{k: v for k, v in q.items() if not k.startswith('_')} for q in C.queries], 'qcommon': C.qcommon,
          'cro': [[x.get('form') or '', x.get('row') or '', x.get('sid') or '', x.get('visit') or '', x.get('text') or ''] for x in C.extq],
          'cons': C.cons, 'rules': C.S.get('rules') or [], 'unres': C.S.get('unres') or [], 'methods': C.methods, 'eff': C.KZeff, 'effissues': [], 'v8': [],
          'tgroup': {}, 'study': C.S.get('study') or {}, 'review': C.review, 'todo': C.todo, 'pd': C.pdd,
          # mm4 研究依据页：方案规则的只读视图（编译后的可执行口径，供「监查规则」按领域展示；不含任何受试者数据）
          'basis': {k: C.A.get(k) for k in ('visitWindows', 'eligibility', 'eligibilitySubject', 'prohibited', 'washout', 'aesi', 'reportRules',
                                             'thresholdRules', 'comboRules', 'indicationBackground', 'cmProtocolRequired', 'pd', 'effRulesText') if C.A.get(k)}}
    return KZ, csb_candidates


def write_outputs(C, KZ, csb_candidates, out, aud):
    S = C.subj
    js_write(out / 'core.js', 'KZ', KZ)
    js_write(out / 'trend.js', 'KZT', C.KZT)
    ex, pdex = build_ex(C)
    js_write(out / 'extra.js', 'KZX', {'soa': C.soa, 'soacols': C.soacols, 'ex': ex, 'pdex': pdex})
    js_write(out / 'grading.js', 'KZG', {'label': C.GL, 'system': C.G.t.get('system'), 'version': C.G.t.get('version'), 'source': C.G.t.get('source', ''),
                                         'items': {k: v for k, v in C.G.items.items() if k in set(C.cmap.values())}, 'map': C.cmap, 'fac': C.fac})
    build_subject_files(C, out)
    dump_json(KZ['queries'], aud / 'queries.json')
    dump_json(query_cards(C), aud / 'query_cards.json')
    dump_json(KZ['labrows'], aud / 'labrows.json')
    dump_json(KZ['others'], aud / 'others.json')
    dump_json(C.cons, aud / 'cons.json')
    dump_json(csb_candidates, aud / 'csb_candidates.json')
    gmap = [{'metric': mid, 'label': m['label'], 'domain': m['domain'], 'code': C.cmap.get(mid) or '', 'unit': m.get('gunit', ''), 'factor': C.fac.get(mid),
             'issue': m.get('unitIssue', ''), 'n': m['n'], 'baseline': dict(m.get('btype', {}))} for mid, m in sorted(C.metric.items())]
    dump_json({'grading': C.GL, 'table': str(ctcae.table_path(C.cfg, C.dir)), 'metrics': gmap}, aud / 'grading_map.json')
    dump_json({'source': C.src, 'n_subjects': len(S), 'dosed': len(C.pop), 'grading': C.GL,
               'graded': sum(1 for g in gmap if g['code'] and g['factor'] is not None), 'unitIssues': [g for g in gmap if g['issue']]}, aud / 'run.json')
    print(f"grading {C.GL} · graded metrics {sum(1 for g in gmap if g['code'] and g['factor'] is not None)} · unit issues {sum(1 for g in gmap if g['issue'])}")
    print(f"subjects {len(S)} · pop {len(C.pop)} · AE {len(C.aes)} · labrows {len(C.labrows)} · others {len(C.others)} · queries {len(C.queries)} · cons {len(C.cons)} · metrics {len(C.KZT['metrics'])}")


if __name__ == '__main__':
    main()
