#!/usr/bin/env python3
"""Medical-monitoring analysis engine: tidy tables (normalize_listing.py) + study.json → front-end data contract.

Usage: python3 mm_build.py --study work/study.json --norm work/norm --out out/site/data

Outputs  data/core.js  (window.KZ)   data/trend.js (window.KZT)   data/extra.js (window.KZX)   data/s/<sid>.js (KZ_SUB)
         ../../analysis/*.json  (labrows/others/queries … for audit and for export_queries.py)
See references/data-contract.md for every field, references/analysis-rules.md for the rules implemented here.
"""
import argparse
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import ctcae
import ext_rules
from common import days, dump_json, fmt, is_full_date, load_json, quantile, study_day

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


def wb_sheet(C, sheet):
    """Workbook-qualified sheet name (business-key scope): same-name sheets in different workbooks stay distinct.
    Sheet alias -> owning workbook alias via normalize _source.json sheets[<sheet>].wb."""
    sheet = str(sheet or '')
    if not sheet:
        return ''
    wb = ((C.src.get('sheets') or {}).get(sheet) or {}).get('wb') or ''
    return f"{wb}:{sheet}" if wb else sheet


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
    C.mdir = C.A.get('metricDir') or {}        # {metricRe: 'up'|'down'} 单向不利指标
    C.mthr = C.A.get('metricThreshold') or []  # 项目收紧：有效值=min(所选,收紧值)，两参数各自（须带方案/IB 原文）
    C.G = ctcae.load(C.cfg, C.dir)  # grading system/version from the protocol (cfg.grading or cfg.ctcaeVersion) — never defaulted
    C.cfg['ctcaeVersion'] = C.G.label
    C.GL = C.G.label
    N = Path(norm_p)
    C.src = load_json(N / '_source.json', {})
    for dom in ('subjects', 'visits', 'exposure', 'ae', 'mh', 'cm', 'proc', 'findings', 'efficacy', 'pd', 'extq', 'groups'):
        setattr(C, dom, load_json(N / f'{dom}.json', []) or [])
    vis = C.cfg.setdefault('visits', {})
    C.VIS = vis.get('order') or sorted({f['visit'] for f in C.findings if f.get('visit')})
    vis['order'] = C.VIS
    C.UNS = set(vis.get('unsched', ['USV']))
    C.ET = set(vis.get('early', ['ET']))
    C.isAgg = lambda v: v not in C.UNS and v not in C.ET
    C.vi = lambda v: C.VIS.index(v) if v in C.VIS else len(C.VIS)
    return C


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
        e = sorted([x for x in ex[sid] if is_full_date(x.get('start'))], key=lambda x: x['start'])
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
            r = s.get(spec.get('ref', 'ld')) or s.get('ld') or s.get('fd')
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
               'cm': a.get('cm') or '', 'wd': a.get('withdraw') or '', 'row': a['row'], 'sh': a['sheet'], 'sid': sid, 'site': s['site'], 'fd': s['fd'] or '',
               'pre': bool(s['fd'] and is_full_date(a.get('start')) and a['start'] < s['fd']), '_rel': related,
               '_aesi_term': bool(aesi_hit), '_aesi_def': aesi_hit, 'pt': a.get('pt') or '', 'soc': a.get('soc') or '',
               'rpt': a.get('rpt') or '', 'aware': a.get('aware') or ''}
        rec['te'] = (not rec['pre']) and bool(s['fd']) and (not C.teEnd.get(sid) or not is_full_date(rec['s']) or rec['s'] <= C.teEnd[sid])
        C.ae_by[sid].append(rec)
        C.aes.append(rec)
    C.mh_by = defaultdict(list)
    for m in C.mh:
        C.mh_by[m['sid']].append({'n': m.get('no') or len(C.mh_by[m['sid']]) + 1, 't': m.get('term') or '', 's': m.get('start') or '',
                                  'e': m.get('end') or '', 'ong': '是' if m.get('ongoing') else '否', 'row': m['row'], 'sh': m['sheet']})
    C.cm_by = defaultdict(list)
    for c in C.cm:
        ind = c.get('indication') or ''
        wk = c.get('ind_kind') or ('AE' if re.search(r'^AE|不良事件', ind) else 'MH' if re.search(r'^MH|病史', ind) else '')
        C.cm_by[c['sid']].append({'n': c.get('no') or len(C.cm_by[c['sid']]) + 1, 't': c.get('term') or '', 's': c.get('start') or '',
                                  'e': c.get('end') or '', 'ong': bool(c.get('ongoing')), 'dose': c.get('dose') or '', 'fq': c.get('freq') or '',
                                  'rt': c.get('route') or '', 'why': ind, 'wk': wk, 'row': c['row'], 'sh': c['sheet'], 'f': ''})


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


def build_labrows(C):
    doms = set(C.A.get('labDomains', ['lab', 'vs', 'ecg']))
    match = [(re.compile(a), re.compile(b), w) for a, b, w in C.A.get('aeMatch', [])]  # [metricRe, aeTermRe, ±days]
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
        # inferred AE (no dynamic link but a plausible AE exists in time window) → context only, never auto-links
        for mre, are, w in match:
            if mre.search(mid):
                for a in C.ae_by[sid]:
                    if are.search(a['t']) and any(days(a['s'], r['date']) is not None and abs(days(a['s'], r['date'])) <= w for r, _ in pts):
                        ctx.append(f"同期 AE「{a['t']}」（{a['s']}）可能对应，但检验页未关联")
        P = [r for r, _ in pts]
        anycs = any(r.get('clin') == 2 for r in P)
        mg = max([r.get('grade') or 0 for r in P] + [0])
        has_ae = any(l[0] == 'AE' for l in links)
        has_mh = any(l[0] == 'MH' for l in links)
        unassessed = all(r.get('clin') is None for r in P)
        if anycs:
            risk = 'AE' if has_ae else 'MH' if has_mh else 'CSX'
        elif mg >= 2:
            risk = 'AE' if has_ae else 'NA2' if unassessed else 'NCS2'
        else:
            risk = 'AE' if has_ae else 'NCS'
        if unassessed and risk != 'AE':
            ctx.append('临床意义未评价')
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
            worse = any((r.get('grade') or 0) > bg or (r.get('clin') or 0) > bc for r in P)
            ctx.append('较基线加重：需判断是否给药后加重（AE）' if worse else '与基线同级：病史延续可能')
        for l in links:
            if not l[4]:
                ctx.append(f'关联对象不存在：{l[0]}+{l[3]}')
        f0 = P[0]
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'test': C.metric[mid]['label'], 'mid': mid, 'grp': f0.get('group') or '',
            'pr': {'CSX': 4, 'MH': 3, 'NCS2': 3, 'NA2': 3}.get(risk, 1),
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or ''] for r in P],
            'rel': [l[:4] for l in links], 'ctx': ctx, 'q': [], 'fid': [], 'cro': '', 'mg': mg, 'risk': risk,
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
        mdir = next((d for mre, d in C.mdir.items() if re.search(mre, mid)), None)
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
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': '较基线显著变化且超出参考范围', 'test': C.metric[mid]['label'], 'mid': mid,
            'grp': cand[0].get('group') or '', 'pr': 2,
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None if r.get('dev') is None else round(r['dev'], 4)] for r in cand],
            'rel': [], 'ctx': [f"双阈值候选：偏离上下限 ≥{dev_f:.0%} 且同向较基线变化 ≥{base_f:.0%}（按当前所选阈值即时重分类）"],
            'q': [], 'fid': [], 'cro': '', 'mg': max([r.get('grade') or 0 for r in cand] + [0]), 'risk': 'REL',
            'qkey': f"lab|{sid}|REL|{wb_sheet(C, worst.get('sheet'))}|{mid}|{worst.get('visit') or ''}"})
    C.labrows.sort(key=lambda g: (-g['pr'], g['sid'], g['test']))


# ----------------------------------------------------------------------------- rule-based signals ("others")
def add_other(C, sid, cat, pr, summ, v=None, d=None, sh='', row=None, test='', clin=None, rel=None, ctx=None, risk=None, rule=None, lane=None, level=None, bkey=None):
    s = C.subj[sid]
    o = {'sid': sid, 'site': s['site'], 'cat': cat, 'pr': pr, 'sum': summ, 'v': v or '', 'd': d or '', 'sh': sh, 'row': row, 'test': test,
         'clin': clin, 'rel': rel or [], 'ctx': ctx or [], 'q': [], 'fid': [], 'cro': '', 'risk': risk or '', '_rule': rule or {},
         'qkey': oth_qkey(C, sid, cat, sh, v, d, test, rel, rule, bkey)}
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
                     'lln': (r['value'] / r['lo']) if r.get('value') is not None and r.get('lo') else None}.get(on)
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
                          R.get('lane'), R.get('level'), bkey=f"{C.metric[mid]['label']}|{r.get('visit') or ''}|{r.get('date') or ''}")


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
                              bkey=f"{C.metric[r0['mid']]['label']}|{r0.get('visit') or ''}|{r0['date']}")
                    if R.get('once', True):
                        break


def ae_checks(C):
    on = set(C.A.get('aeChecks', ['predose_related', 'grade_vs_lab', 'cm_flag', 'aesi_terms', 'aesi_unmatched', 'duplicate']))
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
                      rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
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
                          rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
        if 'aesi_terms' in on and a['_aesi_term'] and not a['aesi'] and not a['pre']:
            add_other(C, sid, 'AESI标记核对', 3, f"AE「{a['t']}」符合方案 AESI 定义（{'、'.join(a['_aesi_def'])}），但「是否AESI」未勾选", None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
    termdefs = [d for d in C.aesiDefs if d['_t'] or d['_soc']]
    if 'aesi_unmatched' in on and termdefs and len(termdefs) == len(C.aesiDefs) and not any(R.get('aesi') for R in C.A.get('thresholdRules', []) + C.A.get('comboRules', [])):
        for a in C.aes:  # flagged AESI but matches none of the protocol's (purely term-based) AESI definitions
            if a['sid'] in C.pop and a['aesi'] and not a['_aesi_term']:
                add_other(C, a['sid'], 'AESI标记核对', 2, f"AE「{a['t']}」勾选为 AESI，但不符合方案列出的 AESI 定义（{'、'.join(d.get('name') or d.get('id') for d in termdefs)}）",
                          None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
    for RR in C.A.get('reportRules', []):  # {"flag": "serious"|"aesi", "days": 1, "from": "aware"|"start", "label": "SAE 24h"}
        key = {'serious': 'sae', 'aesi': 'aesi'}.get(RR.get('flag'), RR.get('flag'))
        for a in C.aes:
            if a['sid'] not in C.pop or not a.get(key):
                continue
            t0 = a.get('aware') if RR.get('from', 'aware') == 'aware' and is_full_date(a.get('aware')) else a['s']
            dd = days(a.get('rpt'), t0) if is_full_date(a.get('rpt')) and is_full_date(t0) else None
            if dd is None:
                if RR.get('requireDate'):
                    add_other(C, a['sid'], 'AE报告时限核对', 2, f"{RR.get('label', key)}：AE「{a['t']}」缺少报告日期", None, a['s'], a['sh'], a['row'], a['t'], risk='AE')
                continue
            if dd > RR.get('days', 1):
                add_other(C, a['sid'], 'AE报告时限核对', RR.get('pr', 3), f"{RR.get('label', key)}：AE「{a['t']}」{'获知' if t0 == a.get('aware') else '发生'}于 {t0}，报告于 {a['rpt']}（{dd} 天，方案要求 ≤{RR.get('days', 1)} 天）",
                          None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
    if 'duplicate' in on:
        for sid, L in C.ae_by.items():
            for i, x in enumerate(L):
                for y in L[i + 1:]:
                    if x['t'] == y['t'] and x['s'] and y['s'] and (not x['e'] or y['s'] <= x['e']) and (not y['e'] or x['s'] <= y['e']):
                        add_other(C, sid, 'AE重复/同义记录核对', 2, f"同一术语「{x['t']}」两条记录时间重叠（#{x['n']} {x['s']}~{x['e'] or '持续'} / #{y['n']} {y['s']}~{y['e'] or '持续'}）",
                                  None, y['s'], y['sh'], y['row'], y['t'], rel=[['AE', x['t'], x['s'], x['n']], ['AE', y['t'], y['s'], y['n']]], risk='AE')


def overlap(c, a, b):
    s, e = c['s'] or '0000', (c['e'] or '9999') if not c['ong'] else '9999'
    return s <= (b or '9999') and e >= (a or '0000')


def cm_checks(C):
    for P in C.A.get('prohibited', []):  # {"name","re","window":[daysBeforeFd, 'ld'|daysAfterFd], "pr"}
        pre = re.compile(P['re'], re.I)
        for sid in C.pop:
            s = C.subj[sid]
            if not s['fd']:
                continue
            w0 = P.get('daysBefore', 0)
            a = (dt.date.fromisoformat(s['fd']) - dt.timedelta(days=w0)).isoformat()
            b = (dt.date.fromisoformat(s['ld']) + dt.timedelta(days=P.get('daysAfter', 0))).isoformat() if is_full_date(s['ld']) else s['lo']
            for c in C.cm_by[sid]:
                if pre.search(c['t']) and overlap(c, a, b):
                    add_other(C, sid, P.get('cat', '禁限用药核对'), P.get('pr', 4),
                              f"CM「{c['t']}」（{c['s'] or '?'}~{'持续' if c['ong'] else c['e'] or '?'}）属于{P['name']}，与{('首剂前 %d 天至' % w0) if w0 else ''}治疗期重叠；用药原因：{c['why'] or '—'}",
                              None, c['s'], c['sh'], c['row'], c['t'], ctx=[P.get('note', '')] if P.get('note') else [],
                              bkey=f"{c['t']}|{c['s']}")
    for W in C.A.get('washout', []):  # {"name","re","days","ref":"icf"|"fd"}
        pre = re.compile(W['re'], re.I)
        for sid in C.pop:
            s = C.subj[sid]
            ref = s.get(W.get('ref', 'fd'))
            if not is_full_date(ref):
                continue
            a = (dt.date.fromisoformat(ref) - dt.timedelta(days=W['days'])).isoformat()
            for c in C.cm_by[sid]:
                if pre.search(c['t']) and (c['ong'] or (is_full_date(c['e']) and c['e'] >= a)) and (not is_full_date(c['s']) or c['s'] <= ref):
                    add_other(C, sid, W.get('cat', '入排洗脱用药核对'), W.get('pr', 3),
                              f"CM「{c['t']}」末次 {c['e'] or '持续'}，距{'知情' if W.get('ref') == 'icf' else '首剂'}（{ref}）不足 {W['days']} 天洗脱期（{W['name']}）",
                              None, c['e'] or c['s'], c['sh'], c['row'], c['t'], bkey=f"{c['t']}|{c['s']}")


def eligibility_checks(C):
    for E in C.A.get('eligibility', []):  # {"id","metric","visits":[..],"op","v","text","pr"}
        mre = re.compile(E['metric'])
        vis = set(E.get('visits') or [])
        for (sid, mid), rows in C.F.items():
            if sid not in C.pop or not mre.search(mid):
                continue
            for r in rows:
                if r['post'] or (vis and r.get('visit') not in vis):
                    continue
                on = E.get('on', 'val')
                x = {'val': r.get('value'), 'uln': (r['value'] / r['hi']) if r.get('value') is not None and r.get('hi') else None}.get(on)
                if cmp(E['op'], x, E['v']):
                    add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4),
                              f"筛选期 {C.metric[mid]['label']} {r.get('raw')} {r.get('unit') or ''}（{r.get('visit')} {r.get('date')}）符合排除标准「{E['text']}」，但已随机/给药",
                              r.get('visit'), r.get('date'), r['sheet'], r['row'], C.metric[mid]['label'], r.get('clin'), ctx=[E.get('id', '')],
                              bkey=f"{C.metric[mid]['label']}|{r.get('visit') or ''}|{r.get('date') or ''}")
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
            ad = s.get({'rand': 'rand_d', 'icf': 'icf'}.get(anc, '')) if anc in ('rand', 'icf') else next((x.get('date') for x in C.visits if x['sid'] == sid and x.get('visit') == anc), None)
            sd, lab = (days(v.get('date'), ad) if is_full_date(ad) and is_full_date(v.get('date')) else None), f'{anc}+'
        if sd is not None and (sd < t - mi or sd > t + pl):
            add_other(C, sid, '访视超窗核对', 2, f"{v['visit']} 实际 {v['date']}（{lab}{sd}），方案窗 {lab}{t}{'−%d' % mi}/+{pl}", v['visit'], v['date'], v['sheet'], v['row'])


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
QT = {  # default query wording (Chinese, fact first, then the ask). Override in study.json analysis.queryTemplates
    'CSX': ('CS未关联AE/MH', '{visit}（{date}）{test} {raw} {unit}（参考范围 {rng}{gtxt}），研究者判定「异常有临床意义」，但未关联不良事件或病史。',
            '请核实该异常是否应记录为不良事件；如判断为既往疾病延续，请在病史中补充并关联；如判定有误请更正临床意义评价。'),
    'MH': ('CS仅关联病史·加重核对', '{visit}（{date}）{test} {raw} {unit}，研究者判定「异常有临床意义」，仅关联病史「{mh}」；基线（{bvis}）为 {braw}{unit}。',
           '请评估给药后是否较基线加重；如属加重，请记录为不良事件并关联。'),
    'CSX_AE': ('CS未关联·同期疑似AE', '{visit}（{date}）{test} {raw} {unit}（参考范围 {rng}{gtxt}），研究者判定「异常有临床意义」；同期已记录 {cand}，但该检查记录未关联。',
               '请确认两者是否为同一事件；如是，请在该记录的关联字段中关联该 AE（如表单无关联字段，请在异常描述中注明 AE 编号）；如否，请评估是否需另行记录不良事件。'),
    'NCS2': ('NCS但达分级≥2级', '{visit}（{date}）{test} {raw} {unit}，按 {gl} 数值达 {grade} 级（{gterm}），研究者判定「异常无临床意义」。',
             '请说明判定依据（如复查结果、标本因素）或更正临床意义评价；如判定有临床意义，请评估是否需记录 AE。'),
    'NA2': ('未评价临床意义·达分级≥2级', '{visit}（{date}）{test} {raw} {unit}（参考范围 {rng}），按 {gl} 数值达 {grade} 级（{gterm}），该结果未见研究者临床意义评价。',
            '请评估该结果的临床意义；如判定有临床意义，请评估是否需记录 AE 并关联。'),
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
    risks = C.A.get('queryRisks', ['CSX', 'MH', 'NCS2', 'NA2'])
    Q = []
    common = defaultdict(list)

    def new_q(sid, cat, sh, row, v, d, test, fact, ask, ev, src, qkey=''):
        same = next((q for q in Q if q['sid'] == sid and q['sh'] == sh and row is not None and q['row'] == row), None)
        if same and C.A.get('mergeSameCell', True):  # one EDC cell → one query; append the extra fact/ask
            same['parts'] += [['另：' + fact, 0], [ask, 1]]
            same['text'] = ''.join(x[0] for x in same['parts'])
            same['cat2'] = same.get('cat2', []) + [cat]
            src['q'].append(same['id'])
            return same
        st, cro = ext_match(C, sid, sh, fact + ask)
        if st == '同主题已查重' and C.A.get('skipDuplicates', False):
            return None
        q = {'id': f'Q{len(Q) + 1:03d}', 'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'sh': sh, 'row': row, 'v': v or '', 'd': d or '', 'test': test or '',
             'text': fact + ask, 'parts': [[fact, 0], [ask, 1]], 'ev': ev, 'cro': st, 'flags': [], '_cro': cro, 'qkey': qkey}
        if ask and ask not in common[cat]:
            common[cat].append(ask)
        Q.append(q)
        src['q'].append(q['id'])
        if cro:
            src['cro'] = cro
        return q

    for g in C.labrows:
        if g['risk'] not in risks:
            continue
        if g['risk'] == 'MH' and not any('较基线加重' in c for c in g['ctx']):
            continue
        cat, ft, ask = T[g['risk']]
        cand = [c for c in g['ctx'] if c.startswith('同期 AE')]
        if g['risk'] == 'CSX' and cand:  # a plausible AE exists but the finding is not linked → ask to link instead of "report AE"
            cat, ft, ask = T.get('CSX_AE', T['CSX'])
            ft = ft.replace('{cand}', '；'.join(re.sub(r'可能对应，但检验页未关联', '', c).replace('同期 ', '') for c in cand))
        P = [p for p in g['pts'] if (g['risk'] in ('NCS2', 'NA2') and (p[4] or 0) >= 2) or (g['risk'] not in ('NCS2', 'NA2') and p[5] == 2)] or g['pts']
        p = P[0]
        f = next((r for r in C.F[(g['sid'], g['mid'])] if r['sheet'] == p[7] and r['row'] == p[8]), {})
        mh = '、'.join(l[1] for l in g['rel'] if l[0] == 'MH')
        lo_, hi_ = f.get('lo'), f.get('hi')
        rng = f"{fmt(lo_)}–{fmt(hi_)}" if lo_ is not None and hi_ is not None else f"≤{fmt(hi_)}" if hi_ is not None else f"≥{fmt(lo_)}" if lo_ is not None else '未提供'
        fact = fill(ft, visit=p[0], date=p[1], test=g['test'], raw=p[2], unit=p[3], lo=fmt(f.get('lo')) if f.get('lo') is not None else '—',
                    hi=fmt(f.get('hi')) if f.get('hi') is not None else '—', gtxt=f"，{C.GL} {p[4]} 级" if p[4] else '', grade=p[4], gterm=f.get('gterm', ''), rng=rng, gl=C.GL,
                    mh=mh, bvis=(g['base'] or [None])[0], braw=(g['base'] or [None, '—'])[1])
        if len(P) > 1:
            fact += f"（同类异常另有 {len(P) - 1} 次：{'、'.join(str(x[0]) for x in P[1:4])}{'…' if len(P) > 4 else ''}）"
        new_q(g['sid'], cat, p[7], p[8], p[0], p[1], g['test'], fact, ask, [[x[7], x[8], x[0], g['test']] for x in P], g, g.get('qkey', ''))
    for o in C.others:
        R = o['_rule']
        if o['pr'] < C.A.get('queryMinPr', 3) or R.get('query') is False:
            continue
        ask = R.get('ask') or C.A.get('askByCat', {}).get(o['cat']) or '请核实并更正，或提供医学说明。'
        new_q(o['sid'], o['cat'], o['sh'], o['row'], o['v'], o['d'], o['test'], o['sum'] + '。', ask, [[o['sh'], o['row'], o['v'], o['test']]], o, o.get('qkey', ''))
    for m in C.S.get('queries_manual', []) or []:  # MM-written queries: {sid, cat, sh, row, v, d, test, fact, ask}
        if m.get('sid') in C.subj:
            new_q(m['sid'], m['cat'], m.get('sh', ''), m.get('row'), m.get('v'), m.get('d'), m.get('test'), m['fact'], m.get('ask', ''),
                  [[m.get('sh', ''), m.get('row'), m.get('v', ''), m.get('test', '')]], {'q': [], 'cro': ''},
                  f"man|{m['sid']}|{m['cat']}|{wb_sheet(C, m.get('sh', ''))}|{m.get('v', '')}|{m.get('d', '')}|{m.get('test', '')}")
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
    recs = defaultdict(lambda: defaultdict(lambda: [set(), set()]))  # sheet -> visit -> [done, no]
    names = {}
    for f in C.findings:
        if f['sid'] not in C.pop or not f.get('visit'):
            continue
        sh = f['sheet']
        names.setdefault(sh, f.get('group') or sh)
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
        by = recs.get(sp['sheet'], {})
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
def build_eff(C):
    M = C.A.get('efficacy', [])
    data = {}
    by = defaultdict(list)  # (sid, src) -> [(visit,date,value,raw)]
    for e in C.efficacy:
        by[(e['sid'], 'eff:' + str(e.get('metric')))].append((e.get('visit'), e.get('date'), e.get('value') if isinstance(e.get('value'), (int, float)) else None, e.get('value')))
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
    for m in M:  # key-visit pending: visit happened, value missing
        kv = m.get('keyVisit')
        if not kv or m.get('pending') is False:
            continue
        had = {v['sid'] for v in C.visits if v.get('visit') == kv}
        for sid in had & C.pop:
            if kv not in data.get(sid, {'v': {}})['v'].get(m['id'], {}):
                anomalies.append({'sid': sid, 'site': C.subj[sid]['site'], 'k': f'{kv} {m["label"]}缺失', 'c': '', 'v': kv, 't': f'{kv} 访视已发生，但未见 {m["label"]} 数据', 'st': '核对是否未录入/未评估'})
    C.KZeff = {'metrics': [{k: v for k, v in m.items() if k not in ('src', 'derive', 'baseVisit')} | {'note': m.get('note', '')} for m in M],
               'data': list(data.values()), 'anomalies': anomalies, 'rulesText': C.A.get('effRulesText', '')}


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
    rows = {}
    for sh, rs in need.items():
        meta = sheets[sh]
        path = C.src['workbooks'][meta['wb']]
        wb = wbs.get(path) or openpyxl.load_workbook(path, read_only=True, data_only=True)
        wbs[path] = wb
        ws = wb[sh]
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
    return ex


# ----------------------------------------------------------------------------- defaults for taxonomy / review / methods / todo
BUILTIN_METHODS = [
    ('M01', 'CS 未关联 AE/MH', '检验/VS/ECG 页结果、参考范围、临床意义、动态关联字段', '给药后新发或加重的异常被判 CS，但关联字段为空 → 漏报 AE 风险最高', '漏报 AE', '发 query：请评估记录 AE 或补充病史并关联'),
    ('M02', 'CS 仅关联病史', '同上 + 病史页', '仅关联 MH 时比较给药后与规定基线的等级/数值，加重者提示应记 AE', '以病史替代 AE', '较基线加重者发 query；同级者仅提示'),
    ('M03', 'NCS 但 {GL} ≥2 级', '数值 + {GL} 数值条目', '数值达 ≥2 级仍判 NCS 时请研究者说明依据；无 {GL} 数值条目者不自动分级', '判定尺度偏松', '发 query：说明依据或更正'),
    ('M04', '基线定义', '方案规定基线（cfg.baselineRules：指定访视/首剂或随机前最近/多次均值，可按指标分别定义）', '规定基线缺失时按规则回退（默认首剂前最近有效值）并注明「替代基线」', '基线错配', '仅提示，不单独发 query'),
    ('M05', '同中心判定一致性', '同中心同指标同单位/范围/方向，数值相差 ≤5%', '一例 CS 一例 NCS 时提示判定尺度不一致；不以多数判定作为标准', '中心判定偏差', '先核对症状/复查/处置差异'),
    ('M06', '方案阈值专项', 'analysis.thresholdRules', '方案原文定义的 AE/AESI/停药/回看阈值逐点比对，并核对是否有对应 AE/AESI 记录', '漏报 AESI', '按规则 pr 决定是否发 query'),
    ('M07', 'AE 记录质量', 'AE 页', '给药前事件相关性、AE 等级 vs 关联检验 {GL} 等级、合并用药标记、AESI 标记、同术语重叠记录', '记录不一致', '发 query 或提示'),
    ('M08', '禁限用药 / 洗脱期', 'CM 页 + 方案禁用药清单', '药名正则匹配 + 用药时段与首剂前窗口/治疗期重叠；洗脱期按知情/首剂回推', '方案偏离', '发 query 并核对 PD listing'),
    ('M09', '入排关键数值', '筛选期检验/人口学', '筛选期数值符合排除标准但已随机/给药', '入组不合格', '优先核实'),
    ('M10', '访视窗', '访视页日期', '研究日 = 访视日 − 首剂日 + 1；按方案窗判断', '超窗', '提示 / 核对 PD'),
    ('M11', '中心偏离', '中心层面汇总（不含计划外/提前退出访视）', '漏斗图 ±2SE 需关注 / ±3SE 明显偏离；n<2 不判', '中心系统性偏差', '中心层面沟通，不对个例发 query'),
    ('M13', '多指标组合规则', 'analysis.comboRules', '方案定义的组合标准（如 Hy’s law：ALT/AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN）同日/窗口内同时满足', '漏报 AESI/SAE', '按规则 pr 决定是否发 query'),
    ('M14', 'AE/SAE/AESI 报告时限', 'AE 页（获知/报告日期）+ analysis.reportRules', '报告日期 − 获知（或发生）日期 > 方案时限', '报告延迟', '发 query 或提示'),
    ('M12', '有效性数据合理性', 'analysis.efficacy / effRules', '按方案终点定义派生（绝对值/较基线/百分比），离群与关键访视缺失提示；盲态下不分组', '终点数据质量', '核对源数据/测量'),
]


def defaults(C):
    cfg = C.cfg
    tax = cfg.setdefault('taxonomy', {})
    if not tax.get('domains'):
        cats = list(dict.fromkeys(o['cat'] for o in C.others))
        grp = defaultdict(list)
        for c in cats:
            k = '不良事件记录' if c.startswith('AE') or 'AESI' in c else '合并用药' if '用药' in c else '入排/访视' if re.search('入排|访视', c) else '方案阈值专项'
            grp[k].append(c)
        col = {'方案阈值专项': 'red', '不良事件记录': 'org', '合并用药': 'brn', '入排/访视': 'blu'}
        tax['domains'] = [[k, v, col.get(k, '')] for k, v in grp.items()] + [['检验异常', list(dict.fromkeys(QT[k][0] for k in QT)), 'org']]
    meths = C.S.get('methods') or [{'id': m[0], 'domain': m[1].replace('{GL}', C.GL), 'data': m[2].replace('{GL}', C.GL), 'principle': m[3].replace('{GL}', C.GL),
                                    'risk': m[4], 'action': m[5], 'source': '引擎内置规则'} for m in BUILTIN_METHODS]
    # 双阈值方法学卡（F-THR-7：方法学页写入当前 T_dev/T_base；选择器档位变化时以顶栏/信息条为准）
    TH = C.cfg['thresholds']
    _pm = TH.get('per_metric') or {}
    _tight = '；'.join(f"{t2.get('metric')}→dev {float(t2['dev']):.0%}" for t2 in C.mthr if t2.get('dev') is not None) + \
             ''.join(f"；{t2.get('metric')}→base {float(t2['base']):.0%}" for t2 in C.mthr if t2.get('base') is not None)
    meths.insert(0, {'id': 'M-THR', 'domain': '双阈值风险判定（T_dev / T_base）',
                     'data': '检验/VS/ECG 数值行：偏离参考范围比例（高于上限 (x−ULN)/ULN、低于下限 (LLN−x)/LLN）＋同向较基线变化 |x−基线|/|基线|',
                     'principle': (f"给药后超出参考范围且偏离 ≥T_dev（构建配置 {float(TH['dev']):.0%}）且同向较基线变化 "
                                   f"≥T_base（构建配置 {float(TH['base']):.0%}）→ REL 风险项（pr2，不自动发 query，可转 query）；"
                                   "范围内变化不论较基线变化多大都不计风险（明细可见 Δ%）；超出范围但 Δ<T_base（基线已异常）不算新风险；"
                                   "同一源行已有 pr≥3 条目时 REL 只作该条目上下文"
                                   + (f"；按指标覆盖 per_metric：{len(_pm)} 项" if _pm else "")
                                   + (f"；项目收紧 metricThreshold：{_tight}（有效值=min(所选,收紧值)）" if C.mthr else "")
                                   + (f"；单向不利指标 metricDir：{len(C.mdir)} 项" if C.mdir else "")),
                     'risk': '漏检显著变化', 'action': '构建按最低档 20% 写全量候选，页面按所选 T_dev/T_base 即时重分类（不重新构建）',
                     'source': '引擎内置规则（双阈值）'})
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
             'ab': {'个体': [['CS·未关联', 'solid-red', f"{lr('CSX')} 行"], ['CS·仅MH', 'org', f"{lr('MH')} 行"], ['NCS·≥2级', 'yel', f"{lr('NCS2')} 行"]] + ([['未评价·≥2级', 'yel', f"{lr('NA2')} 行"]] if lr('NA2') else []),
                    '中心': [['同值异判', 'yel', f"{len(C.cons)} 组比较，{sum(c['st'] == '需核实' for c in C.cons)} 组需核实"]],
                    '全局': [['相对变化', 'line', f'无 {C.GL} 数值条目的指标仅作筛查，不改写 NCS']]},
             'ex': ex_for(list(dict.fromkeys(QT[k][0] for k in QT))), 'm': ['M01', 'M02', 'M03', 'M04', 'M05'], 'r': [], 'todo': [], 'go': [['safety.html#tab=lab', '待核异常明细'], ['objective.html', '检验趋势']]}]
        for d in tax['domains']:
            if d[0] in ('不良事件记录', '检验异常'):
                continue
            n = sum(o['cat'] in d[1] for o in C.others)
            C.review.append({'k': 'd' + str(len(C.review)), 't': d[0], 'sh': sorted({o['sh'] for o in C.others if o['cat'] in d[1] and o['sh']})[:4], 'ib': [], 'f': d[1],
                             'flow': [['方案原文', '规则库定位'], ['逐点比对', '阈值/窗口/药名'], ['对应记录', 'AE / AESI / PD'], ['处理', '按优先级发 query 或提示']],
                             'ab': {'个体': [[c, 'org', f"{sum(o['cat'] == c for o in C.others)} 条"] for c in d[1]]}, 'ex': ex_for(d[1]),
                             'm': ['M06'] if d[0] == '方案阈值专项' else ['M08'] if d[0] == '合并用药' else ['M09', 'M10'], 'r': [], 'todo': [],
                             'go': [['safety.html#tab=oth', f'专项核查 {n} 条']]})
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
                  ['质疑', 'org', f"{len(C.queries)} 条已写入 listing 首列", 'queries.html']]
        an = Counter(x['k'] for x in C.KZeff['anomalies'])
        if an:
            C.todo.insert(4, ['有效性', 'blu', '；'.join(f'{k} {v}' for k, v in an.most_common(2)), 'efficacy.html'])
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
    visit_window_checks(C)
    pd_reconcile(C)
    csb_candidates = ext_rules.run(C)                    # M13–M23 确定性＋日期序＋CSB 候选（PR-5）
    C.others.sort(key=lambda o: (-o['pr'], o['cat'], o['sid'], o['d']))
    build_queries(C)
    build_cons(C)
    build_centers(C)
    build_soa(C)
    build_trend(C)
    build_eff(C)
    defaults(C)
    out = Path(a.out)
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
    KZ = {'cfg': C.cfg, 'meta': {'cutoff': cutoff, 'qs': len(C.queries), 'counts': {k: len(getattr(C, k)) for k in ('subjects', 'visits', 'exposure', 'ae', 'mh', 'cm', 'findings', 'efficacy', 'pd', 'extq')},
                                 'status': dict(stc), 'n': len(S), 'centers': len(C.centers), 'dosed': len(C.pop), 'built': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
                                 'sources': C.cfg.get('footer', {}).get('left', '')},
          'subs': subs, 'centers': C.centers, 'aes': [{k: v for k, v in x.items() if not k.startswith('_') and k != 'sh'} for x in C.aes if x['sid'] in C.pop],
          'aesum': C.aesum, 'aecat': list(C.aesum), 'ibtag': ibtag, 'labrows': [{k: v for k, v in g.items() if k != 'mid' or g.get('risk') == 'REL'} for g in C.labrows],
          'others': [{k: v for k, v in o.items() if not k.startswith('_')} for o in C.others],
          'queries': [{k: v for k, v in q.items() if not k.startswith('_')} for q in C.queries], 'qcommon': C.qcommon,
          'cro': [[x.get('form') or '', x.get('row') or '', x.get('sid') or '', x.get('visit') or '', x.get('text') or ''] for x in C.extq],
          'cons': C.cons, 'rules': C.S.get('rules') or [], 'unres': C.S.get('unres') or [], 'methods': C.methods, 'eff': C.KZeff, 'effissues': [], 'v8': [],
          'tgroup': {}, 'study': C.S.get('study') or {}, 'review': C.review, 'todo': C.todo}
    js_write(out / 'core.js', 'KZ', KZ)
    js_write(out / 'trend.js', 'KZT', C.KZT)
    js_write(out / 'extra.js', 'KZX', {'soa': C.soa, 'soacols': C.soacols, 'ex': build_ex(C)})
    js_write(out / 'grading.js', 'KZG', {'label': C.GL, 'system': C.G.t.get('system'), 'version': C.G.t.get('version'), 'source': C.G.t.get('source', ''),
                                         'items': {k: v for k, v in C.G.items.items() if k in set(C.cmap.values())}, 'map': C.cmap, 'fac': C.fac})
    build_subject_files(C, out)
    aud = Path(a.audit) if a.audit else out.parent.parent / 'analysis'
    dump_json(KZ['queries'], aud / 'queries.json')
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
