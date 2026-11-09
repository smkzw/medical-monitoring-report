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
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ctcae
import bind
import ext_rules
import monitor_v5
import raw_export
import pd_rules
from common import ae_action, cn_quotes, cs_plain, days, dose_state, dshow, dump_json, fmt, is_dosing, parse_links, is_full_date, load_json, move_word, not_done, open_workbook_lenient, pii_column, quantile, redact_row, result_state, state_meets, study_day, yes, zero_dose

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


def _dose_num(v):
    """剂量文本 → 数值（「900 mg」「600mg」「0.5 g」按原单位取数；不含数字或含多个数字 → None）。"""
    nums = re.findall(r'\d+(?:\.\d+)?', str(v or ''))
    return float(nums[0]) if len(nums) == 1 else None


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
                'icf', 'sample', 'dispense', 'ie'):   # mm4：知情同意记录 / 样本采集 / 发药回收（可选域）；V6：入排标准页
        setattr(C, dom, load_json(N / f'{dom}.json', []) or [])
    # V6 运营审阅（RUX S10001 W8 等 5 个访视 SV「访视是否发生=否」被当成已完成，生成 45 条「已完成访视但缺少评估」）：
    # 访视页记录为未发生的访视不算已完成访视——不进访视完成/超窗/SoA 完成度，按缺失访视处理（留在 C.visits_missed 供展示）
    C.visits_missed = [v for v in C.visits if not_done(v.get('done'))]
    if C.visits_missed:
        C.visits = [v for v in C.visits if v not in C.visits_missed]
    # V6 医学审阅（RUX P0010：开放期 IGA=0 按方案停药，01-20 的「研究药物发放」被当成给药报「终止治疗后仍有给药」）：
    # 受试者有实际给药/医嘱记录时，发放/回收（药物清点）类表单不参与首末次给药与给药连续性判定，移入 dispense 域
    _disp = re.compile(r'发放|回收|分发|返还|退还|清点|dispens|return|accountab', re.I)
    adm = {e['sid'] for e in C.exposure if not _disp.search(str(e.get('sheet') or ''))}
    moved = [e for e in C.exposure if _disp.search(str(e.get('sheet') or '')) and e['sid'] in adm]
    if moved:
        C.exposure = [e for e in C.exposure if not (_disp.search(str(e.get('sheet') or '')) and e['sid'] in adm)]
        C.dispense = list(getattr(C, 'dispense', []) or []) + moved
    # 表单中文名：EDC 目录页 ＜ study.json analysis.formNames；分组名缺省（等于表单代码）时用中文名，避免页面出现「OTH」
    C.A['formNames'] = {**(C.src.get('formNames') or {}), **(C.A.get('formNames') or {})}
    for f in C.findings:
        if f.get('sheet') in C.A['formNames'] and f.get('group') in (None, '', f.get('sheet')):
            f['group'] = C.A['formNames'][f['sheet']]
    align_visit_codes(C)
    vis = C.cfg.setdefault('visits', {})
    C.VIS = complete_visit_order(C, vis.get('order') or [])
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


def complete_visit_order(C, order):
    """数据里出现、配置访视顺序里没有的访视名补进顺序（MY008：配置 V1–V17、数据 D84…；不在顺序里的访视全部落到同一个
    「未知」序号，检验趋势/安全性概览/有效性图整片空白）。补入的按典型研究日（相对受试者最早记录日的中位天数）排序；
    计划外/提前退出类排最后；配置里有但数据中没有的访视保留在原位置之后。数据访视都在配置里时顺序不变。"""
    recs = [r for dom in ('visits', 'findings', 'efficacy') for r in getattr(C, dom) if r.get('visit') and is_full_date(r.get('date'))]
    data_vis = {r['visit'] for dom in ('visits', 'findings', 'efficacy') for r in getattr(C, dom) if r.get('visit')}
    if not order:
        order = sorted(data_vis)
    extra = [v for v in data_vis if v not in order]
    if not extra:
        return order
    first = {}
    for r in recs:
        if r['sid'] not in first or r['date'] < first[r['sid']]:
            first[r['sid']] = r['date']
    offs = defaultdict(list)
    for r in recs:
        offs[r['visit']].append(days(r['date'], first[r['sid']]) or 0)
    tail_rx = re.compile(r'计划外|^USV|unsched|提前|退出|^ET$|early', re.I)
    keyed = [v for v in list(order) + extra if v in data_vis and offs.get(v) and not tail_rx.search(v)]
    keyed.sort(key=lambda v: statistics.median(offs[v]))
    tail = [v for v in list(order) + extra if v in data_vis and v not in keyed]
    return keyed + tail + [v for v in order if v not in data_vis]


def align_visit_codes(C):
    """mm4：方案写「V6/W4/D29」、EDC 导出写「W4/D29V6」——同一组访视标记（字母＋数字）视为同一访视，把配置里的访视代码改写成
    listing 实际写法（visitWindows、visits.order/d1/unsched/early、soa、pd 关键访视与顺序规则）。只在 listing 中恰有一个同组标记时改写。"""
    L = {r.get('visit') for dom in ('visits', 'findings', 'efficacy', 'exposure') for r in getattr(C, dom) if r.get('visit')}
    by = defaultdict(set)
    for v in L:
        if _vkey(v):
            by[_vkey(v)].add(v)
    amap = {}
    # V6（MY008：方案访视 V1–V17、listing 访视名「D-56至D-14」「D21」，同表另有访视代码列 VISTOID）：数据自带「访视代码↔访视名」
    # 一一对应时直接按它改写配置（排序、访视窗、SoA、逾期推算都对上）
    pairs, inv = defaultdict(set), defaultdict(set)
    for dom in ('visits', 'findings', 'efficacy'):
        for r in getattr(C, dom):
            vc, vn = str(r.get('vcode') or '').strip(), r.get('visit')
            if vc and vn:
                pairs[vc].add(vn)
                inv[vn].add(vc)
    vmap = {k: next(iter(v)) for k, v in pairs.items() if len(v) == 1 and len(inv[next(iter(v))]) == 1}
    # 编号体系可能错位（MY008：EDC 的 V10 起与方案 V10 不是同一访视，D84 被配上方案 D70 的窗 → 超窗 22→414）：
    # 访视名自带研究日（D84）且方案该代码有目标日时，两者须在窗内（至少 ±7 天）才采用这对配对
    W0 = C.A.get('visitWindows') if isinstance(C.A.get('visitWindows'), dict) else {}
    for k in list(vmap):
        spec = W0.get(k)
        dm = re.findall(r'D\s*(-?\d+)', str(vmap[k]))
        if spec is None or not dm:
            continue
        t, mi, pl = (spec.get('target'), spec.get('minus', 0), spec.get('plus', 0)) if isinstance(spec, dict) else (list(spec) + [0, 0, 0])[:3]
        if t is not None and abs(int(dm[-1]) - int(t)) > max(7, int(mi or 0), int(pl or 0)):
            vmap.pop(k)

    def m(c):
        if c in L or not isinstance(c, str):
            return c
        if c in vmap:
            amap[c] = vmap[c]
            return vmap[c]
        k = _vkey(c)
        hit = by.get(k) or {v for kk, vs in by.items() if k and k < kk for v in vs}   # 精确同组，其次唯一的超集（V9/W18 ↔ W18/D127V9）
        if k and not hit:                                 # V6：再其次唯一的子集（方案「V5/W2/D15」↔ 数据只写「W2」；D002 616/616 假逾期）
            hit = {v for kk, vs in by.items() if kk and kk < k for v in vs}
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
    for e in C.A.get('efficacy') or []:                   # V6：有效性终点的访视（基线/关键访视/限定访视）同样改写——D002 8 项终点全空的根因
        for k in ('baseVisit', 'keyVisit'):
            if e.get(k):
                e[k] = m(e[k])
        if isinstance(e.get('visits'), list):
            e['visits'] = [m(x) for x in e['visits']]
    for R in C.A.get('effRules') or []:
        if isinstance(R.get('visits'), list):
            R['visits'] = [m(x) for x in R['visits']]
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
        # V6 运营审阅（RUX）：「是否提前结束研究/治疗」与「是否完成」问法相反；提前结束治疗日期优先作治疗结束日
        s = dict(s)
        if s.get('eos_early') not in (None, '') and s.get('eos_done') in (None, ''):
            s['eos_done'] = '否' if yes(s['eos_early']) else '是'
        if is_full_date(s.get('eot_early_d')):
            s['eot_d'] = s['eot_early_d']
        if yes(s.get('eot_early')) and not s.get('eot_why'):
            s['eot_why'] = '提前结束治疗'
        e = sorted([x for x in ex[sid] if is_full_date(x.get('start')) and is_dosing(x)], key=lambda x: x['start'])   # 0 剂量与暂停/停药区间不算首/末次给药
        fd = e[0]['start'] if e else s.get('fd')
        ld = max([x.get('end') or x['start'] for x in e if is_full_date(x.get('end') or x['start'])], default=None) if e else s.get('ld')
        st = s.get('status')
        if not st:
            st = '筛选失败' if not fd and not s.get('rand') else ('完成试验' if str(s.get('eos_done')) in ('是', 'Y') else
                                                                 '提前退出' if s.get('eos_d') else '治疗结束' if s.get('eot_d') else '已入组')
        g = groups.get(sid, {})
        # V6 运营审阅（RUX：监查页「提前退出 0」而 KRI 12/192）：EDC 受试者状态对所有出组者都写「完成试验」，
        # 提前退出以治疗/研究结束页的原因为准（与 KRI 同一判定 monitor_v5._early_wd）；EDC 原状态留在 edc_status
        eos_done_ = re.match(r'^\s*(是|Y|Yes|完成)', str(s.get('eos_done') or ''), re.I)
        if st not in ('筛选失败',) and fd and monitor_v5._early_wd(dict(s, status=st)) and st != '提前退出' and not eos_done_:
            # SAR 第 8 轮运营审阅：EDC 写「脱落」时临床监查页（只认「提前退出」）恒为 0、总览却是 4——已给药者的提前出组状态统一为
            # 「提前退出」，EDC 原文保留在 edc_status。D001 运营审阅：只是提前终止治疗、研究结束页记「完成」或仍在随访的不算退出研究
            only_tx = not monitor_v5._EARLY.search(str(st)) and not s.get('eos_d')
            s = dict(s, edc_status=st)
            st = '提前终止治疗' if only_tx else '提前退出'
        elif fd or s.get('rand'):
            if not re.search(r'完成|结束|退出|脱落|终止|死亡|失访|撤回|筛选|提前', str(st)) and st != '已入组':
                s = dict(s, edc_status=st)
                st = '已入组'            # D001：EDC 写「已随机」，临床监查/中心画像「在组」只认「已入组」→ 0（实为 60 例）
        C.subj[sid] = dict(s, fd=fd, ld=ld, status=st, lo=lastobs.get(sid) or ld or fd,
                           strat=s.get('strat') or g.get('strat'), grp=arm_name(s.get('grp') or g.get('grp')),
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
_UNK = r'(?:UK|UN|NK|NA|XX|\?\?|00|未知)'


def partial_date(s):
    """部分日期归一到已知精度：「2025-01-UK」→「2025-01」，「2025-UK-UK」→「2025」，完整日期原样；不可解析 → ''。"""
    m = re.match(rf'^\s*(\d{{4}})(?:[-/.](\d{{1,2}}|{_UNK}))?(?:[-/.](\d{{1,2}}|{_UNK}))?\s*$', str(s or ''), re.I)
    if not m:
        return ''
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if not mo or not mo.isdigit() or mo == '00':
        return y
    if not d or not d.isdigit() or d == '00':
        return f'{y}-{int(mo):02d}'
    return f'{y}-{int(mo):02d}-{int(d):02d}'


def _pre_dose(start, fd):
    """V6 R13：首剂前判定按开始日期的实际精度比较（2025-03 vs 首剂 2025-04-02 → 首剂前；同月/同年 → 不能判首剂前，按 TEAE）。
    审阅修正（CRA）：「2025-01-UK」类写法先归一到已知精度再比。"""
    st = partial_date(start)
    if not fd or not st:
        return False
    return st < str(fd)[:len(st)]


def no_usable(recs):
    """V6：记录编号列可用＝同一受试者内基本不重复（RUX「记录号」多为 0 是重复记录序号，不是 AE 编号；D002「记录号」才是）。
    重复率 >20% → 不用，回落按受试者内顺序编号。"""
    seen, dup, n = set(), 0, 0
    for r in recs:
        no = r.get('no')
        if no in (None, ''):
            continue
        n += 1
        k = (r.get('sid'), str(no))
        dup += k in seen
        seen.add(k)
    return n > 0 and dup / n <= 0.2


_AESI_QUAL = re.compile(r'显著|明显|严重|重度|显著性|marked|severe', re.I)


def build_events(C):
    use_ae_no, use_mh_no = no_usable(C.ae), no_usable(C.mh)
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
            # F09（RUX 深审）：分桶单一来源——带 MedDRA SOC 列的记录以 SOC 列为准（实测 2 例 catmap 错桶）；
            # 无 SOC 时仍走 catmap → 原文术语回退。（mm5 审阅 S9 复核后保留此口径：SOC 是正式编码；AE 自带 IB 标签 a.ib，
            # 不依赖 ibtag 的类别键）
            cat = a.get('soc') or next((b for p, b in catmap if p.search(txt)), None) or term
        gi = grade_int(gtxt(a.get('grade'))) or 0
        aesi_all = [d for d in C.aesiDefs if ((d['_t'] and d['_t'].search(txt)) or (d['_soc'] and d['_soc'].search(str(a.get('soc') or ''))))
                    and gi >= d.get('minGrade', 0)]
        # 定义带程度限定（「ALT显著增高」）而编译没给分级/检验界值：术语命中只是「可能符合」，不据此断言「符合定义未勾选」
        # （审阅者 2026-11-09，SAR：方案界值 ALT>5×ULN，ALT 1–2×ULN 的 AE 曾 9 条全部判符合）
        maybe_ = [d for d in aesi_all if _AESI_QUAL.search(str(d.get('name') or '')) and not d.get('minGrade') and not d.get('labCond')]
        aesi_hit = [d.get('name') or d.get('id') for d in aesi_all if d not in maybe_]
        rel = a.get('rel') or ''
        related = bool(relre and relre.search(rel)) and not (unrel and unrel.search(rel))
        rec = {'n': (a.get('no') if use_ae_no else None) or len(C.ae_by[sid]) + 1, 't': term, 'c': cat, 's': a.get('start') or '', 'e': a.get('end') or '',
               'g': gtxt(a.get('grade')), 'sae': bool(a.get('serious')), 'aesi': bool(a.get('aesi')),
               'dili': yes(a.get('dili')) if isinstance(a.get('dili'), str) else bool(a.get('dili')), 'rel': rel or '—', 'act': a.get('action') or '—', 'out': a.get('outcome') or '—',
               # wd：只有「是」才算导致退出（「否」曾是真值 → AE 列表几乎全部标「退出治疗」，MY008/SAR/D001）
               'cm': a.get('cm') or '', 'wd': '是' if yes(a.get('withdraw')) else '', 'row': a['row'], 'sh': a['sheet'], 'wb': a.get('wb') or '', 'sid': sid, 'site': s['site'], 'fd': s['fd'] or '',
               'pre': _pre_dose(a.get('start'), s['fd']), '_rel': related,
               '_aesi_term': bool(aesi_all), '_aesi_def': aesi_hit, 'pt': a.get('pt') or '', 'soc': a.get('soc') or '',
               'rpt': a.get('rpt') or '', 'aware': a.get('aware') or '', 'sae_crit': a.get('sae_crit') or '',
               'gchg': a.get('gchg') or ''}
        rec['te'] = (not rec['pre']) and bool(s['fd']) and (not C.teEnd.get(sid) or not is_full_date(rec['s']) or rec['s'] <= C.teEnd[sid])
        # V6 R13：开始日期缺失/无法解析（如 D002「是」）→ TEAE 判定待定：暂按 TEAE 计（不漏报，常见 SAP 最坏情形口径），并发日期核对
        _ps = partial_date(rec['s'])
        # 待定＝开始日期不可解析，或只知道与首剂同月/同年（无法判先后）；月份晚于首剂月等可判的不算待定（CRA 审阅：20/23 实可判）
        rec['te_pending'] = bool(s['fd']) and (not _ps or (len(_ps) < 10 and str(s['fd'])[:len(_ps)] == _ps))
        rec['ib'] = ib_match(C, rec)
        C.ae_by[sid].append(rec)
        C.aes.append(rec)
    C.mh_by = defaultdict(list)
    for m in C.mh:
        C.mh_by[m['sid']].append({'n': (m.get('no') if use_mh_no else None) or len(C.mh_by[m['sid']]) + 1, 't': m.get('term') or '', 's': m.get('start') or '',
                                  'e': m.get('end') or '', 'ong': '是' if m.get('ongoing') else '否', 'row': m['row'], 'sh': m['sheet'], 'wb': m.get('wb') or ''})
    C.cm_by = defaultdict(list)
    for c in C.cm:
        ind = c.get('indication') or ''
        wk = c.get('ind_kind') or ('AE' if re.search(r'^AE|不良事件', ind) else 'MH' if re.search(r'^MH|病史', ind) else '')
        C.cm_by[c['sid']].append({'n': c.get('no') or len(C.cm_by[c['sid']]) + 1, 't': c.get('term') or '', 's': c.get('start') or '',
                                  'e': c.get('end') or '', 'ong': bool(c.get('ongoing')), 'dose': c.get('dose') or '', 'fq': c.get('freq') or '',
                                  'rt': c.get('route') or '', 'why': ind, 'wk': wk, 'row': c['row'], 'sh': c['sheet'], 'wb': c.get('wb') or '', 'f': '',
                                  'aeno': str(c.get('aeno') or '')})
    build_events_dup(C)


def build_events_dup(C):
    """F08（RUX 深审）：重复 AE 记录指纹（同受试者＋同术语/PT＋同开始日期，EDC 修订版整行重复导出实测成对/三联）。
    全组成员标 dup_n/dup_rows，第 2 份起标 dup（逐记录质疑只按组首发生，AE 谱按去重计数）；C.ae_dup 供标记 query。
    F-D（IMP-03）：抽成独立函数——例次/等级/SAE 等一切计数口径统一按「第 2 份起不计」去重（subs 聚合、KRI、todo）。"""
    C.ae_dup = []
    by_fp = defaultdict(list)
    for a in C.aes:
        # mm5 审阅（S5）：指纹含结束日期/等级/SAE——同日肺炎 1 级与 3 级 SAE 是两条不同记录，不能把后者当重复去掉
        fp = (a['sid'], a.get('pt') or a['t'], a['s'], a.get('e') or '', str(a.get('g') or ''), bool(a.get('sae')))
        if is_full_date(a['s']):
            by_fp[fp].append(a)
    for fp, grp in by_fp.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda x: x.get('row') or 0)
        # V6 医学审阅（RUX S01017 肝功能异常 2→3→1 级、S01029 SAE 肺炎 2→3 级）：「严重程度有变化」的子记录（同一事件拆多行、
        # 主字段相同、EDC「严重程度是否变化」标为是）不是重复录入——同一事件只计一次，但不发「重复记录核对」。
        # 工程审阅：只认该标志；记录号各不相同不能当证据（同一 AE 录两次，记录号本来就不同）
        if any(re.match(r'^\s*(是|Y|Yes|1)\s*$', str(x.get('gchg') or ''), re.I) for x in grp):
            for x in grp:
                x['dup_n'], x['dup_rows'], x['dup_kind'] = len(grp), [y.get('row') for y in grp], 'sub'
            for x in grp[1:]:
                x['dup'] = True
            continue
        C.ae_dup.append({'sid': fp[0], 'term': grp[0]['t'], 'start': fp[2], 'rows': [x.get('row') for x in grp], 'recs': grp})
        for x in grp:
            x['dup_n'] = len(grp)
            x['dup_rows'] = [y.get('row') for y in grp]
        for x in grp[1:]:
            x['dup'] = True


_AE_NO_SOC_NOTE = '（未按器官系统——MedDRA 不可用）'


def ae_summary(C):
    post = [a for a in C.aes if a['sid'] in C.pop and a['te'] and not a.get('dup')]   # F08：重复记录成员不计入谱
    # mm4 知识层降级兜底（试用实证：无字典时 AE 谱按原文术语分 123 组刷屏）：无 soc 且类别落在原文术语上的比例
    # >80%（含完全无字典）时，不按原文术语逐条分组，改按 IB 风险类别（rec['ib'] 首标签）分组＋超出前 20 归「其他」，
    # 组名注明降级；AE 记录类别同步改写（安全页类别 chips 与总览 AE 谱同一口径）。
    # 已配置 aeCatMap（用户口径）或带 soc 的类别不算原文术语：比例达标即维持原行为。
    if post and sum(1 for a in post if not a.get('soc') and a.get('c') == a.get('t')) > 0.8 * len(post):
        C.aesum = _ae_summary_by_ib(post)
        return
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


def _ib_cat(tag):
    """IB 标签「重要性·风险名（同SOC/同类非严重）」→ 风险名（mm5 审阅 S8：旧版取「·」前的重要性分级，AE 谱塌缩成 2–4 桶）。"""
    return re.sub(r'[（(][^）)]*[）)]$', '', str(tag).split('·', 1)[-1]).strip()


def _ae_summary_by_ib(post):
    """无字典兜底分组：IB 风险类别（首标签）＋其他；组数 >20 时保留前 19 类、其余并入「其他」；组名带降级注明。"""
    cats = defaultdict(lambda: {'n': 0, 's': set(), 'g2': 0, 'rel': 0, 'aesi': 0, 'terms': Counter()})
    by_cat = Counter(_ib_cat(a['ib'][0]) for a in post if a.get('ib'))
    keep = {k for k, _ in by_cat.most_common(19)}
    for a in post:
        k0 = _ib_cat(a['ib'][0]) if a.get('ib') else ''
        name = (k0 if k0 in keep else '其他') + _AE_NO_SOC_NOTE
        a['c'] = name
        c = cats[name]
        c['n'] += 1
        c['s'].add(a['sid'])
        c['g2'] += (grade_int(a['g']) or 0) >= 2
        c['rel'] += a['_rel']
        c['aesi'] += a['aesi']
        c['terms'][a['t']] += 1
    return {k: {'n': v['n'], 's': len(v['s']), 'g2': v['g2'], 'rel': v['rel'], 'aesi': v['aesi'], 'terms': [t for t, _ in v['terms'].most_common()]}
            for k, v in sorted(cats.items(), key=lambda kv: -kv[1]['n'])}


# ----------------------------------------------------------------------------- findings
# IB/方案列明的产品风险（analysis.expectedAE，工作台从 IB 风险表编译）：AE 按术语/PT 匹配，按 SOC 匹配的标「同类」；检验按风险的检验表现匹配
LAB_ALIAS = {'CK': '肌酸激酶|CK|CPK', 'CPK': '肌酸激酶|CK|CPK', 'HGB': '(?<!糖化)血红蛋白|Hb|HGB', 'HB': '(?<!糖化)血红蛋白|Hb|HGB', 'WBC': '白细胞', 'NEUT': '中性粒细胞',
             'ANC': '中性粒细胞', 'LYM': '淋巴细胞', 'LYMPH': '淋巴细胞', 'PLT': '血小板', 'ALT': '丙氨酸氨基转移酶|ALT', 'AST': '天门冬氨酸氨基转移酶|天冬氨酸|AST',
             'TBIL': '总胆红素', 'TG': '甘油三酯', 'TC': '总胆固醇', 'LDL': '低密度脂蛋白', 'CREA': '肌酐', 'QTCF': 'QTc'}


# V6 医学审阅（RUX 带状疱疹×2、卡波西水痘样疹未被提示，IB 列有「局部免疫抑制效应（皮肤感染）」）：风险名常把临床表现写在括注里，
# 且一个风险对应一族 AE 术语——按医学常识的事件族扩展（不含研究特定词）
_RISK_FAMILY = [
    (r'皮肤感染', r'疱疹|带状|水痘|卡波西|真菌|癣|毛囊炎|疖|痈|脓疱|蜂窝织炎|丹毒|疣|皮肤感染|传染性软疣'),
    (r'感染', r'感染|疱疹|带状|水痘|真菌|癣|毛囊炎|蜂窝织炎|脓肿|肺炎|结核|败血|脓毒'),
    (r'皮肤(恶性)?肿瘤|非黑色素瘤|皮肤癌', r'基底细胞癌|鳞状细胞癌|黑色素瘤|皮肤癌|皮肤恶性'),
    (r'恶性肿瘤|恶性肿|淋巴瘤', r'癌|恶性|肉瘤|淋巴瘤|白血病|黑色素瘤'),
    (r'血栓|栓塞', r'血栓|栓塞|梗死|梗塞|卒中|中风'),
    (r'心血管|心脏不良|MACE', r'心肌梗|心衰|心力衰竭|卒中|梗死|心源性'),
    (r'过敏|超敏', r'过敏|超敏|荨麻疹|血管性水肿'),
    # V6 第二轮医学审阅（RUX「血细胞计数下降（血小板、白细胞、红细胞降低）」：中性粒细胞/淋巴细胞计数降低、红细胞计数降低、贫血均未标）
    (r'血细胞|全血细胞|骨髓抑制', r'(中性粒|粒|白|淋巴|红|全血)细胞.{0,4}(减少|降低|下降|减低)|血小板.{0,4}(减少|降低|下降|减低)|'
                              r'贫血|血红蛋白.{0,4}(减少|降低|下降|减低)|骨髓抑制'),
]
_DIR_DN, _DIR_UP = r'减少|降低|下降|减低', r'升高|增多|增高|增加'


def _risk_family(full):
    return next((rx_ for fam, rx_ in _RISK_FAMILY if re.search(fam, full)), None)


def risk_term_re(term):
    """IB 风险名 → AE 术语正则：风险名本体＋括注里的临床表现＋事件族。"""
    t = str(term or '')
    core = re.sub(r'^(严重|重要|重度)|[（(].*?[)）]', '', t).strip()
    paren = [x.strip() for x in re.findall(r'[（(]([^）)]+)[）)]', t) for x in re.split(r'[、，,/]', x) if len(x.strip()) >= 2]
    # 括注项「红细胞降低」要能命中「红细胞计数降低」：主语与升降词之间容许 ≤4 字；括注项没写方向（「血小板」）时继承风险名的方向
    cdir = _DIR_DN if re.search(_DIR_DN, core) else _DIR_UP if re.search(_DIR_UP, core) else None
    alts = []
    for x in [core] + paren:
        if len(x) < 2:
            continue
        m = re.match(rf'(.+?)({_DIR_DN}|{_DIR_UP})$', x)
        alts.append(re.escape(m.group(1)) + '.{0,4}' + m.group(2) if m else
                    (re.escape(x) + '.{0,4}(' + cdir + ')' if cdir and x != core else re.escape(x)))
    fam = _risk_family(' '.join([core] + paren))
    if fam:
        alts.append(fam)
    return re.compile('|'.join(alts)) if alts else None


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
            t_ = str(e.get('term') or '')
            # 风险已有明确事件族（皮肤感染/皮肤恶性肿瘤/过敏…）→ 不再按 SOC 兜底（第二轮医学审阅：升结肠良性肿瘤被标「皮肤恶性肿瘤」、
            # 过敏反应被标「局部免疫抑制效应（皮肤感染）」，都只因同 SOC）
            fam = _risk_family(' '.join([t_] + re.findall(r'[（(]([^）)]+)[）)]', t_)))
            C._exp.append({**e, '_re': risk_term_re(t_), '_labs': labs, '_fam': bool(fam)})
    return C._exp


def _code_suffix_strip(s):
    """剥名称尾部的 MedDRA 编码尾缀：「心脏器官疾病/10007541」「心脏器官疾病（10007541）」「心脏器官疾病(10007541)」→「心脏器官疾病」。
    IB 风险表用编码尾缀、EDC 用纯名称，剥后才能比对（否则同 SOC 匹配恒不命中）。"""
    return re.sub(r'[/／]\d+$|[（(]\d+[）)]$', '', str(s or '').strip()).strip()


_UMBRELLA_GEN = re.compile(r'检测|检查|异常|升高|降低|变化|实验室')   # 通用实验室词（2026-10-29 用户裁定口径）
_ORGAN_HEADS = ('血液学', '检验学', '心电图', '影像学', '生命体征')   # 器官/系统学前缀词


def _stem_content(term):
    """风险术语的实质内容：去括号词与通用实验室词后的剩余（伞形判据与共享词判定共用）。"""
    return _UMBRELLA_GEN.sub('', re.sub(r'[（(].*?[）)]', '', str(term or '')))


def _umbrella_term(term):
    """伞形判据（2026-10-29 用户裁定）：实质内容剥去器官/系统学前缀词后零剩余 → 伞形条目（只泛指某类检查，不指具体事件）。
    「血液学检测异常」「实验室检查异常」＝伞形；「中性粒细胞计数减少」剩「中性粒细胞…」＝非伞形。"""
    s = _stem_content(term)
    n = None
    while n != len(s):                               # 循环剥前缀词（「心电图检查」类多词前缀）
        n = len(s)
        for w in _ORGAN_HEADS:
            if s.startswith(w):
                s = s[len(w):]
    return not s


def _share_stem(a, b):
    """两术语共享 ≥2 字实质内容词（第③级类别兜底门槛）：实质内容公共前缀 ≥2 字；
    前缀锚定避免「淋巴细胞×中性粒细胞」因共同后缀「细胞」误共享。"""
    sa, sb = _stem_content(a), _stem_content(b)
    n = 0
    for x, y in zip(sa, sb):
        if x != y:
            break
        n += 1
    return n >= 2


def _dir_ok(d, term):
    """IB 指标方向（high/low）与 AE 术语方向不矛盾：「白细胞降低」类风险不标到「白细胞升高」上。"""
    if d == 'high':
        return not re.search(r'减少|降低|下降|减低', term)
    if d == 'low':
        return not re.search(r'升高|增多|增高|增加', term)
    return True


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
        hit = (e.get('pt') and _code_suffix_strip(rec.get('pt')) == _code_suffix_strip(e['pt'])) or (e['_re'] and e['_re'].search(rec['t']))
        if hit and serious_only and not severe:      # 用户 2026-10-28：「严重感染」类风险点只认严重或 ≥3 级的 AE
            continue
        if hit:
            out.append(name)
        elif severe and rec.get('soc') and not e.get('_fam'):
            socs = [_code_suffix_strip(s) for s in re.split(r'[；;]', e.get('soc') or '') if s.strip()]
            if rec['soc'] in [s for s in socs if not s.startswith('各类检查')]:
                out.append(name + '（同SOC，严重/≥3级）')       # 第②级：真实同 SOC，严重/≥3 级过滤不变（伞形/非伞形一致）
            elif rec['soc'] in socs and (
                    (e['_labs'] and any(rx_.search(rec['t']) and _dir_ok(d, rec['t']) for rx_, d in e['_labs']))    # 第③级·伞形（用户 2026-10-29）：带 analyte 且 AE 术语与指标共享实质词；mm5 审阅 S11：方向一致
                    or (not _umbrella_term(term) and _share_stem(term, rec['t']))):        # 第③级·非伞形：风险术语与 AE 术语共享 ≥2 字实质内容词
                out.append(name + '（各类检查，严重/≥3级）')      # 伞形无 analyte、具体条目无共享词 → 均不放行（D001「血液学检测异常→各类检查」311 条噪音链回归闸）
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


_POW10 = re.compile(r'^×10\^(\d+)/L$')


def pow10_harmonize(C):
    """同一指标混用 ×10^9/L 与 ×10^12/L（MY008 网织红细胞绝对计数：本地 0.1523×10^12/L、中心 152×10^9/L）→ 换算到该指标
    最常用的量级（数值、参考范围、原值文本一并换算；原单位记在 unit_orig）。否则较基线变化算出「升高 294%」这类假数。"""
    for mid, m in C.metric.items():
        exps = Counter()
        for u, n in m['units'].items():
            mm = _POW10.match(str(u or ''))
            if mm:
                exps[int(mm.group(1))] += n
        if len(exps) < 2:
            continue
        e0 = exps.most_common(1)[0][0]
        u0 = f'×10^{e0}/L'
        for (sid, mid2), rows in C.F.items():
            if mid2 != mid:
                continue
            for r in rows:
                mm = _POW10.match(str(r.get('unit') or ''))
                if not mm or int(mm.group(1)) == e0:
                    continue
                k = 10 ** (int(mm.group(1)) - e0)
                for key in ('value', 'lo', 'hi'):
                    if isinstance(r.get(key), (int, float)):
                        r[key] = round(r[key] * k, 6)
                if isinstance(r.get('value'), (int, float)):
                    r['raw'] = fmt(r['value'], 4)
                r['unit_orig'], r['unit'] = r['unit'], u0
        m['units'] = Counter({(u0 if _POW10.match(str(u or '')) else u): 0 for u in m['units']})
        for (sid, mid2), rows in C.F.items():
            if mid2 == mid:
                for r in rows:
                    m['units'][r.get('unit') or ''] += 1


def build_findings(C):
    """Attach metric id, post flag, baseline, Δ, Δ%, toxicity grade (cfg.grading) to every finding."""
    conv = C.A.get('unitConv', {})  # {"lab:血红蛋白": {"g/dL": 10}} — overrides the grading table's unit factors
    qualre = rx(C.A.get('qualTestRe'))
    C.F = defaultdict(list)  # (sid, mid) -> rows
    C.metric = {}
    C.micro = []             # 第三轮：微生物培养/药敏行（micro_panel_mark 已标 _micro）分域——不进 C.F/C.metric，单独呈现
    for f in C.findings:
        if f['sid'] not in C.subj:
            continue
        if f.get('_micro'):
            C.micro.append(f)
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
    pow10_harmonize(C)
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
        # V6（MY008 医学审阅：同名指标本地/中心实验室两张表，S03001 LB1 5.70% 拿 LB8 的 8.21% 作基线）：
        # 同一受试者同一指标来自多张表时，每行优先用本表自己的基线（本表无给药前有效值才用合并基线）
        by_sh = defaultdict(list)
        for r in rows:
            by_sh[r.get('sheet')].append(r)
        sh_base = {}
        if len(by_sh) > 1:
            for sh, rs in by_sh.items():
                bb, _ = pick_baseline(C, sid, mid, rs, rules)
                if bb is not None:
                    sh_base[sh] = bb
        # 审阅者 2026-11-09（MY008 复审：本地/中心两表并行，LB8 无给药前值时借 LB1 基线，参考范围/方法不同，43 行比较失真）：
        # 本表无基线时，只借「只有给药前记录」的表（筛选期专表）的基线；对方表给药后也有数据＝并行检测来源，不跨表比较
        post_sh = {sh for sh, rs in by_sh.items() if any(x.get('post') for x in rs)} if len(by_sh) > 1 else set()
        for r in rows:
            sh_ = r.get('sheet')
            if sh_ in sh_base:
                r['base'] = sh_base[sh_]
            elif b is not None and len(by_sh) > 1 and b.get('sheet') != sh_ and b.get('sheet') in post_sh:
                r['base'] = None
            else:
                r['base'] = b
            rb = r['base']
            r['isb'] = r is rb or (rb is not None and rb.get('_of') is not None and r in rb['_of'])
            u = r.get('unit') or ''
            fac = conv.get(mid, {}).get(u) if u in conv.get(mid, {}) else (C.G.factor(code, u) if code else 1)
            v, bv = r.get('value'), (rb or {}).get('value')
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
            if not xs:
                # 方案写访视类别（「筛选期」）、数据写具体名（MY008「D-56至D-14」）：按访视类别（筛选/提前退出/计划外）匹配
                cls = next((rx_ for rx_ in _VCLASS if rx_.search(str(v))), None)
                xs = [r for r in cand if cls and cls.search(str(r.get('visit') or '')) and (not tre or tre.search(str(r.get('tpt') or '')))] if cls else []
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


def panel_level_clin(C):
    """V6（复核 D002 阴道分泌物：同一份化验单 5 行全判 CS，含「滴虫 阴性」——是整份判定逐行重复，不是逐项判定）。
    长表同受试者×同表单×同日期 ≥3 行且全部判 CS 时：判定只留在异常行（超出参考范围/分级 ≥1/定性阳性），其余行置未评价并标 _panel；
    一行都判不出异常时保持原样（交研究者判定，不猜）。宽表共用临床意义列另由 normalize._record_level_clin 处理。"""
    grp = defaultdict(list)
    for (sid, _mid), rows in C.F.items():
        for r in rows:
            if r.get('clin') is not None and r.get('date'):
                grp[(sid, r.get('sheet'), r.get('date'))].append(r)
    for rs in grp.values():
        if len(rs) < 3 or any(r.get('clin') != 2 for r in rs):
            continue
        abn = [r for r in rs if r.get('oor') or (r.get('grade') or 0) >= 1 or
               (r.get('value') is None and (ext_rules.qual_level(r.get('raw')) or 0) > 0)]
        for r in rs:
            r['_panel'] = True
            if abn and r not in abn:
                r['clin'] = None


def finding_abn(r):
    return (r.get('clin') in (1, 2)) or (r.get('grade') or 0) >= 1 or r.get('oor')


def resolve_links(C, sid, links):
    out = []
    for kind, term, _, no in links:
        pool = C.ae_by[sid] if kind == 'AE' else C.mh_by[sid]
        ev = next((x for x in pool if str(x['n']) == str(no)), None)
        # V6（审阅者 2026-11-02，D002 34/34 假「关联不对应」）：编号对不上（导出编号口径与记录序号不同）但术语能唯一回溯 → 按术语认关联
        if ev is None and (term or '').strip():
            # F02 词目型（说明列「与XX有关/XX既往史」）：按术语回溯到具体记录并回填编号；对不上保持未关联
            t = re.sub(r'[（(].*$', '', term.strip())

            def _same(xt, t=t):                      # mm5 审阅（S4）：空术语记录不得「恒命中」；两边至少 2 字
                xt = (xt or '').strip()
                return bool(t and xt and min(len(t), len(xt)) >= 2 and (t in xt or xt in t))
            ev = next((x for x in pool if _same(x.get('t'))), None)
            if ev is None and no is None and kind in ('AE', 'MH'):
                # V6（用户审阅 RUX 第 10 条）：说明列只写术语时类型是猜的（默认 MH）——「与白细胞计数降低有关」实为 AE，另一池也找
                alt = C.mh_by[sid] if kind == 'AE' else C.ae_by[sid]
                ev = next((x for x in alt if _same(x.get('t'))), None)
                if ev is not None:
                    kind = 'MH' if kind == 'AE' else 'AE'
            no = ev['n'] if ev is not None else no            # 术语也回溯不到：保留研究者填的编号（交 LINK 核对）
        # 关联单元格只写了编号（「MH#1」「AE 3」）时显示记录本身的术语——编号原样露给中心看不懂（第二轮医学审阅 Q020）
        code_only = not (term or '').strip() or re.fullmatch(r'(AE|MH|病史|不良事件)?\s*[#＃(（]?\s*\d+\s*[)）]?', term.strip(), re.I)
        out.append([kind, (ev or {}).get('t') if ev is not None and code_only else (term or (ev or {}).get('t', '')), (ev or {}).get('s', ''), no, bool(ev)])
    return out


def real_links(links):
    """resolve_links 结果中算作「研究者已关联」的：回溯到真实记录，或研究者填了编号（编号不存在另由 LINK 核对）。
    说明列抽出、但回溯不到任何记录的词目不算关联（mm5 审阅 S6：否则丢研究疾病豁免、掩盖未关联）。"""
    return [l for l in links if l[4] or l[3] is not None]


_DT_NEG_AFTER = re.compile(r'^[^，。；,;]{0,6}?(?:无关|不相关|无明显相关|非.{0,2}所致)')
_DT_NEG_BEFORE = re.compile(r'(?:排除|否认|除外|不考虑|并非|非)\s*$')


def desc_term_links(C):
    """说明列兜底关联（V6，用户审阅 RUX 第 10 条：80 条「判 CS 未关联」里 79 条说明列已写关联）：
    CS 行没有回溯得到的关联、也不是研究疾病归因时，用**该受试者本人**的 AE/病史术语去匹配说明文本
    （「CS肝酶升高AE」「高脂血症」「贫血相关」）；否定写法不算。命中写入 links（编号取回溯到的记录），来源可追溯。"""
    for (sid, _mid), rows in C.F.items():
        pools = [('AE', C.ae_by.get(sid) or []), ('MH', C.mh_by.get(sid) or [])]
        if not any(p for _, p in pools):
            continue
        for r in rows:
            if r.get('clin') != 2:
                continue
            txt = ' '.join(str(r.get(k) or '') for k in ('desc', 'reason_text', 'reason_raw')).strip()
            if not txt or real_links(resolve_links(C, sid, r.get('links') or [])) or ext_rules.disease_attr(C, r):
                continue
            hit = None
            for kind, _t, _s, no in parse_links(txt):           # 编号写法（「与MH01相关」「AE[3]」）：normalize 旧版未抽到时在此补
                pool = dict(pools).get(kind) or []
                x = next((x for x in pool if str(x['n']) == str(no)), None)
                if x is not None:
                    hit = [kind, x.get('t') or '', None, x['n']]
                    break
            for kind, pool in ([] if hit else pools):
                for x in sorted(pool, key=lambda x: -len(x.get('t') or '')):
                    t = re.sub(r'[（(].*$', '', str(x.get('t') or '')).strip()
                    i = txt.find(t) if len(t) >= 2 else -1
                    if i < 0 or _DT_NEG_BEFORE.search(txt[max(0, i - 4):i]) or _DT_NEG_AFTER.search(txt[i + len(t):]):
                        continue
                    hit = [kind, t, None, x['n']]
                    break
                if hit:
                    break
            if hit:
                r['links'] = (r.get('links') or []) + [hit]
                r['_lsrc'] = 'desc-term'


def annotate_links(C):
    """每个检验点记下回溯后的关联类型（_lk），供判定一致性的归因维度使用（mm5 审阅 S7：att_of 不再看原始词目）。"""
    for (sid, _mid), rows in C.F.items():
        for r in rows:
            if r.get('links'):
                r['_lk'] = [l[0] for l in real_links(resolve_links(C, sid, r['links']))]


def drill_fields(C, sid, r):
    """mm4 钻取行扩位（用户 2026-10-30 裁定：参与者资料页 CS 项点开必须有链接信息）：
    返回 [归因码, 原文说明截断 60 字, 关联摘要]，追加在检验行尾部——既有 14 位不动（前端按索引安全读取）。
    归因码：AE/MH＝关联回溯到真实记录；disease＝研究者归因研究疾病；NA＝超范围未评价；''＝无（CS 行前端显示「未关联」）。
    关联摘要：「AE 术语·开始日期」/「病史 术语」，多条 、 分隔；编号在 AE/MH 记录中不存在的按未关联口径（不冒充已关联）。"""
    links = resolve_links(C, sid, r.get('links') or [])
    ok = [l for l in links if l[4]]
    if ok:
        code = 'AE' if any(l[0] == 'AE' for l in ok) else 'MH'
    elif 'disease' in str(r.get('reason') or ''):
        code = 'disease'
    elif r.get('clin') is None and r.get('oor'):
        code = 'NA'
    else:
        code = ''
    summ = '；'.join(f"{'病史' if l[0] == 'MH' else 'AE'} {l[1]}{'·' + l[2] if l[2] else ''}" for l in ok)   # 「；」分隔（术语本身可能含「、」）
    return [code, str(r.get('reason_text') or '')[:60], summ]


worse_vs_base = ext_rules.worse_vs_base
disease_kw = ext_rules.disease_kw


def _strip_disease_term_links(C):
    """F02 边界（用户 2026-10-27 口径：归因研究疾病不算「未关联」）：说明列词目若命中方案研究疾病词
    （analysis.diseaseTerms/适应症），不作 MH 关联——「与特应性皮炎相关」在特应性皮炎研究里是研究疾病
    归因，词目链接会把 DIS/DISW 豁免误路由成 CSX（RUX 实测 405 行）。编号链接与具体病史词目不动。"""
    try:
        dz = ext_rules.disease_kw(C)
    except Exception:
        return
    if not dz:
        return
    n = 0
    for f in C.findings:
        ls = f.get('links')
        if not ls:
            continue
        keep = [l for l in ls if not (l[3] is None and l[1] and dz.search(l[1]))]
        if len(keep) != len(ls):
            f['links'] = keep
            n += len(ls) - len(keep)
    if n:
        cfg = getattr(C, 'cfg', None)
        if isinstance(cfg, dict):
            cfg['diseaseTermLinksStripped'] = n


# ----------------------------------------------------------------------------- 微生物培养/药敏面板（IMP-02）
_MICRO_TEST_RX = re.compile(r'培养|涂片|镜检|染色|鉴定')
_MICRO_INTERP_RX = re.compile(r'敏感|耐药|中介|抑菌圈', re.I)
_MICRO_MIC_RX = re.compile(r'^\s*[<>=≤≥]\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*$')   # <=0.25 / >=8 / <=0.5/9.5
_MICRO_BREAK_RX = re.compile(r'^\s*[SIR]\s*[<>=≤≥]\s*\d', re.I)                          # 高/低值列写断点文本 R>=4
# 第三轮 E2E（RUX 复审）：微生物专表的命名形态（表名/组名）——整表分域，不依赖同面板出现培养行。
_MICRO_SHEET_RX = re.compile(r'微生物|培养|药敏|药物敏感|细菌学|真菌学|Microbio|Culture|Suscept|(?<![A-Za-z])MICRO?(?![A-Za-z])', re.I)


def micro_panel_mark(C):
    """F-C（IMP-02）：微生物培养＋药敏面板识别（同一受试者·同表单·同日期的组合）。
    培养类检查行（检查名 培养/涂片/镜检/染色/鉴定）标 _micro='C'；同面板内满足药敏形态的行标 _micro='S'：
    ① MIC 比较值（<=0.25、>=8、<=0.5/9.5）且无单位，或 ② lo/hi 写 S/R 断点文本（R>=4），或 ③ 描述写敏感/耐药/中介。
    第三轮：表名/组名命中微生物命名形态的专表整表分域（培养类名→C，其余→S）。
    药敏是判读型结果不是数值异常——须先于 build_findings 调用：带 _micro 的行不进 C.F/C.metric（检验异常/CS/阈值/PD/
    风险/趋势链天然看不到），收入 C.micro 单独呈现。纯数值且无判读/断点信号的行不判（如 CRP '<10' 带单位、裸数值 0.25）。"""
    panels = defaultdict(list)
    for f in C.findings:
        if _MICRO_SHEET_RX.search(f"{f.get('sheet') or ''} {f.get('group') or ''}"):
            f['_micro'] = 'C' if _MICRO_TEST_RX.search(str(f.get('test') or '')) else 'S'
            continue
        panels[(f.get('sid'), f.get('sheet'), f.get('date'))].append(f)
    for rows in panels.values():
        if not any(_MICRO_TEST_RX.search(str(r.get('test') or '')) for r in rows):
            continue
        sus = []
        for r in rows:
            if _MICRO_TEST_RX.search(str(r.get('test') or '')):
                r.setdefault('_micro', 'C')
                continue
            mic = bool(_MICRO_MIC_RX.match(str(r.get('raw') or ''))) and not str(r.get('unit') or '').strip()
            brk = any(_MICRO_BREAK_RX.match(str(r.get(k) or '')) for k in ('hi', 'lo'))
            interp = bool(_MICRO_INTERP_RX.search(str(r.get('desc') or '')))
            if mic or brk or interp:
                r['_micro'] = 'S'
                sus.append(r)
        if sus:
            for r in rows:
                if r.get('_micro') == 'C':
                    r['_micro_sus'] = sus


def micro_rows(C):
    """KZ.micro（分域呈现，给药者）：[sid, 日期, 访视, 项目, 结果原文, 判读/说明, C|S, sheet, row]；同受试者同日培养行在前。"""
    out = [[f['sid'], f.get('date') or '', f.get('visit') or '', f.get('test') or '', '' if f.get('raw') is None else str(f.get('raw')),
            f.get('desc') or '', f.get('_micro'), f.get('sheet') or '', f.get('row')]
           for f in getattr(C, 'micro', []) if f['sid'] in C.pop]
    out.sort(key=lambda r: (r[0], r[1], 0 if r[6] == 'C' else 1, r[8] or 0))
    return out


# 生理可能范围（通用医学常识；只拦明显录错的值，如平均红细胞容积 26.5 fl、红细胞比容 96%）
_PLAUSIBLE = [(re.compile(r'平均红细胞(体积|容积)|MCV', re.I), 'fl', 50, 150), (re.compile(r'红细胞比容|红细胞压积|HCT', re.I), '%', 10, 75),
              (re.compile(r'红细胞比容|红细胞压积|HCT', re.I), 'l/l', 0.1, 0.75), (re.compile(r'平均红细胞血红蛋白浓度|MCHC', re.I), 'g/l', 200, 450),
              (re.compile(r'平均红细胞血红蛋白(含)?量|MCH(?!C)', re.I), 'pg', 15, 50)]


def implausible(r, label):
    """数值落在生理不可能区间（单位须对上）→ 返回说明，否则空串。"""
    v, u = r.get('value'), str(r.get('unit') or '').lower().replace(' ', '')
    if not isinstance(v, (int, float)):
        return ''
    for rx_, uu, lo, hi in _PLAUSIBLE:
        if rx_.search(label) and u == uu and not (lo <= v <= hi):
            return f"{label} {r.get('raw')} {r.get('unit') or ''} 超出生理可能范围（{lo}–{hi} {r.get('unit')}），疑似录入错误"
    return ''


# ----------------------------------------------------------------------------- 输血语境（G3②，通用措辞形态）
# 输血类措辞（「输血前检查/输血前八项」是感染筛查，不是输血依赖；单写「输注」多为静脉给药，不算）
_TRANSFUSION_RX = re.compile(r'输血(?!前)|红细胞输注|输注(?:浓缩|悬浮|洗涤|去白)?(?:红细胞|血小板|血浆|全血)|血小板输注|血浆输注|血液输注')
# 全血血红蛋白/比容（排除糖化/平均红细胞/游离/尿血红蛋白——审阅者 2026-11-09：曾命中糖化血红蛋白）
_HB_RX = re.compile(r'(?<!化)(?<!胞)(?<!离)(?<!尿)血红蛋白(?!尿)|(?<![A-Za-z])HG[BO](?![A-Za-z])|(?<![A-Za-z])HB(?![A-Za-z0-9])|红细胞比容|红细胞压积|血细胞比容|(?<![A-Za-z])HCT(?![A-Za-z])')


def transfusion_refs(C) -> list:
    """方案对输血信息的依赖处：入排标准/终点/补救规则引用输血类措辞（返回去重文本；零依赖返回空）。"""
    st = ((C.S or {}).get('study') or {})
    texts = [str(c.get('text') or '') for c in (st.get('criteria') or []) if isinstance(c, dict)]
    texts += [str(e[1]) for e in (st.get('endpoints') or []) if isinstance(e, (list, tuple)) and len(e) > 1]
    r_ = ((C.A or {}).get('pd') or {}).get('rescue') or {}
    if isinstance(r_, dict):
        texts += [str(r_.get('name') or ''), str(r_.get('stopName') or '')]
    out, seen = [], set()
    for t in texts:
        k = t[:60]
        if t and _TRANSFUSION_RX.search(t) and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def hb_short_jump_note(C, mid, rows) -> str:
    """血红蛋白/红细胞比容短期跳升（≤7 天升高 ≥30 g/L〔g/dL 单位按 ≥3〕）且有输血依赖的方案 → 输血语境提示。"""
    if not transfusion_refs(C) or not _HB_RX.search(str(mid)):
        return ''
    thr = 3.0 if re.search(r'g\s*/\s*dl', str((rows[0].get('unit') if rows else '') or ''), re.I) else 30.0
    pts = sorted((r for r in rows if isinstance(r.get('value'), (int, float)) and is_full_date(r.get('date'))),
                 key=lambda r: r['date'])
    for a, b_ in zip(pts, pts[1:]):
        if 0 <= days(b_['date'], a['date']) <= 7 and (b_['value'] - a['value']) >= thr:
            return (f"短期跳升：{b_.get('visit')}访视较{a.get('visit')}访视（{days(b_['date'], a['date'])} 天内）升高 "
                    f"{fmt(b_['value'] - a['value'])} {b_.get('unit') or ''}——如受试者近期有红细胞输注，请结合输血记录判读（方案依赖输血信息）")
    return ''


def disease_gate(C, mid, pts, b):
    """研究疾病归因异常已判「较基线加重」后是否发质疑（用户 2026-11-05）：有 CTCAE 分级的指标只在最差 ≥3 级或分级上升
    （同 ext_rules.grade_up：已 ≥1 级再升级或升到 ≥2 级、且变化 ≥5%）时发；其余列「研究疾病指标波动」清单。无分级的指标 → 发（≥T_base 已满足）。
    返回 (是否发质疑, 说明)。"""
    if not C.metric[mid].get('gcode'):
        return True, ''
    post = [r for r in pts if r.get('post')]
    worst = max(post, key=lambda r: r.get('grade') or 0, default=None)
    mg, bg = (worst or {}).get('grade') or 0, (b or {}).get('grade') or 0
    if mg >= 3:
        return True, f'达 {mg} 级'
    if worst and ext_rules.grade_up(bg, mg, worst.get('value'), (b or {}).get('value')):
        return True, f'分级 {bg}→{mg} 级'
    return False, f'最差 {mg} 级、分级未上升：列入研究疾病指标波动清单（不发质疑）'


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
        pre_v = ext_rules.pre_values(rows)                # 给药前数值：所有「较基线加重」判定按给药前波动容差（ext_rules.within_pre）
        bg = (b or {}).get('grade') or 0
        bc = (b or {}).get('clin') or 0
        pts, cat = [], '治疗后新发/加重检验异常'
        for r in rows:
            if r.get('_micro') == 'S':
                continue          # F-C（IMP-02）：药敏 MIC 行是判读结果，不作数值异常核查（不发质疑/不计 PD/风险）
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
        for r, _ in pts:                                   # F-C：培养行汇总同面板药敏（明细挂上下文，不另发质疑）
            sus = r.get('_micro_sus')
            if sus:
                res = '；'.join(f"{s.get('test')} {s.get('raw')}{('，' + str(s.get('desc'))) if s.get('desc') else ''}" for s in sus[:12])
                ctx.append(f"同日药敏 {len(sus)} 项（{res}{'…' if len(sus) > 12 else ''}）——判读型结果，不另作数值异常核查")
                break
        opp = ext_rules.opposite_dir([r for r, _ in pts])   # mm4：方向相反的 AE 不算同期疑似（嗜酸性粒细胞升高 ≠「白细胞减少」）
        # inferred AE (no dynamic link but a plausible AE exists) → context only, never auto-links
        # 用户裁定（PLAN §15.1，2026-10-28）：时间口径＝AE 持续期间覆盖检验日期（ae_covers，与第七批 AE 时间口径同因同策），
        # 废弃 ±w 天经验窗口（aeMatch 第三元素保留以兼容配置契约，不再参与判定）
        aecov = set()                                      # 同期 AE 实际覆盖的检验日期（质疑要引用被覆盖的那一次，MY008 S04005：D7 引用 3 个月后的上感）
        for mre, are, w in match:
            if mre.search(mid):
                for a in C.ae_by[sid]:
                    cov_ = {r['date'] for r, _ in pts if is_full_date(r['date']) and ext_rules.ae_covers(a, r['date'])}
                    aecov |= cov_ if (are.search(a['t']) and not opp.search(a['t'])) else set()
                    if are.search(a['t']) and not opp.search(a['t']) and cov_:
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
        dis_only = bool(cs_pts) and not real_links(links) and all(ext_rules.disease_attr(C, r) for r in cs_pts)   # 原因选项或备注归因研究疾病
        bad_ = next((w for w in (implausible(r, C.metric[mid]['label']) for r in cs_pts) if w), '') if anycs else ''
        if bad_:
            risk = 'ENT'                                  # 第 8 轮医学复审 Q177/Q206：录错的值不该按「请评估 AE」追问——走录入核对
            ctx.append(bad_)
        elif anycs and dis_only:
            # 用户 2026-10-27：归因研究疾病不算「未关联」；只有较基线明显加重、且未记录「研究疾病加重」类 AE 才作为风险
            t_base = float(C.cfg['thresholds'].get('base', 0.3))
            ddir = ext_rules.disease_dir(C, mid, P[0].get('sheet', '') if P else '')
            wsys = next((w for w in (worse_vs_base(r, (r['base'] if 'base' in r else b), t_base, disease=True, pre=pre_v, ddir=ddir) for r in cs_pts if r['post']) if w), None) if b else None
            wst = None if wsys else next((w for w in map(ext_rules.stated_worse, cs_pts) if w), None)   # 研究者备注写明加重：研究者判定优先
            wf = wsys or wst
            dae = disease_ae(sid, mid, cs_pts) if wf else []
            risk = 'DISW' if wf and not dae else 'DIS'
            if risk == 'DISW' and wsys:
                gq, gwhy = disease_gate(C, mid, cs_pts, b)
                if not gq:
                    risk = 'DISL'
                    ctx.append(gwhy)
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
                orphan = [r for r in cs_pts if not real_links(resolve_links(C, sid, r.get('links') or [])) and not _cover(r)]
                if orphan:
                    risk = 'CSX'
                    ctx.append('CS 结果未关联且不在已关联事件期间：' + '、'.join(f"{r.get('visit')}（{r.get('date')}）" for r in orphan[:3]))
            if risk == 'CSX' and not real_links(links):
                mh_ = ext_rules.mh_explains(C, sid, mid, cs_pts)
                if mh_ is not None:
                    t_base_ = float(C.cfg['thresholds'].get('base', 0.3))
                    wf_ = next((w for w in (worse_vs_base(r, (r['base'] if 'base' in r else b), t_base_, pre=pre_v) for r in cs_pts if r['post']) if w), None) if b else None
                    if not wf_ and b:
                        risk = 'MHL'                     # 病史延续：不作风险，提示可补关联（与 CSB 步骤 3「病史可解释」同口径）
                        ctx.append(f"未关联，但病史「{mh_['t']}」覆盖该期间，较基线未明显加重（病史延续，可请研究者补关联）")
                    else:
                        ctx.append(f"病史有「{mh_['t']}」" + (f"，但给药后较基线加重（{wf_}）" if wf_ else "，基线缺失无法判断是否加重") + "，检验页未关联")
            ibg = next((bb for a, bb in (C.A.get('indicationBackground') or []) if re.search(a, mid)
                        and ext_rules.bg_applies(bb, mid, P[0].get('sheet', '') if P else '')), None) if risk == 'CSX' else None
            if ibg:
                nm = re.sub(r'（医学常识）$', '', str(ibg).split('：')[0])
                if b is None:
                    ctx.append(f'研究疾病表现（{nm}）；基线缺失，无法判断是否较基线加重')
                else:
                    ddir = ext_rules.disease_dir(C, mid, P[0].get('sheet', '') if P else '')
                    wf = next((w for w in (worse_vs_base(r, (r['base'] if 'base' in r else b), float(C.cfg['thresholds'].get('base', 0.3)), disease=True, pre=pre_v, ddir=ddir) for r in cs_pts if r['post']) if w), None)
                    dae = disease_ae(sid, mid, cs_pts) if wf else []
                    if wf and dae:
                        risk = 'DIS'
                        ctx.append(f"研究疾病表现（{nm}）较基线加重（{wf}），已记录研究疾病加重 AE「{dae[0]['t']}」（{dae[0]['s']}，未关联，提示关联）"
                                   f"{ext_rules.onset_note(C, mid, dae[0], cs_pts)}")
                    elif wf:
                        ctx.append(f'研究疾病表现（{nm}），但较基线进一步加重：{wf}')
                        gq, gwhy = disease_gate(C, mid, cs_pts, b)
                        if not gq:
                            risk = 'DISL'
                            ctx.append(gwhy)
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
            if risk == 'G2NF' and any(c.startswith('同期 AE') for c in ctx):
                # 第二轮医学审阅（RUX Q016/Q061/Q062：体重 2 级「同期已记录 AE“体重增加”，请评估是否需记录 AE」自相矛盾）：
                # 表单既无临床意义字段也无关联字段，同期已有对应 AE → 已处理，不发质疑
                risk = 'AE'
                ctx.append('该表单没有临床意义评价与关联字段，同期已记录对应 AE（不发质疑）')
        elif any(r.get('clin') is None and r.get('oor') for r in P) and C.metric[mid].get('hasClin'):
            # mm4：给药后超出参考范围但未评价临床意义（该表单有临床意义字段）→ 请研究者评价（临床意义决定是否需记 AE）
            risk = 'NA'
        else:
            risk = 'AE' if has_ae else 'NCS'
        if unassessed and risk != 'AE' and C.metric[mid].get('hasClin'):   # 表单没有临床意义字段时不写「未评价」
            ctx.append('临床意义未评价')
        if risk in ('MH', 'NCS2', 'NA', 'NA2'):   # mm4：方案/IB 列出的研究疾病表现 → 审阅时可见（CSX/DIS 已在上方判定）
            ibg = next((b for a, b in (C.A.get('indicationBackground') or []) if re.search(a, mid)
                        and ext_rules.bg_applies(b, mid, P[0].get('sheet', '') if P else '')), None)
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
            wf = next((w for w in (worse_vs_base(r, (r['base'] if 'base' in r else b), t_base, pre=pre_v) or ext_rules.qual_worse(r, b) or (dz_mh and ext_rules.stated_worse(r)) for r in cs_) if w), None)
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
            # 第二轮医学审阅：下面两句只在确有加重（wf）时写——此前 else 挂在「同期 AE 提醒」上，未加重的 125 行同时出现
            # 「较基线加重（None）」与「较基线未明显加重」
            if wf and dae:
                risk = 'MHL'
                ctx.append(f"已关联研究疾病病史，较基线加重（{wf}），加重已记录为 AE「{dae[0]['t']}」（{dae[0]['s']}），请关联"
                           f"{ext_rules.onset_note(C, mid, dae[0], [r for r in P if r.get('clin') == 2])}")
            elif wf:
                ctx.append(f'较基线加重（{wf}）：仅关联病史「{mhn}」，未见对应 AE')
        if risk in ('CSX', 'MH', 'MHU', 'NCS2', 'NA', 'NA2', 'G2NF', 'DISW'):   # IB/方案列明风险的检验表现只在需关注的层提示
            ctx += ib_lab_tags(C, mid, C.metric[mid]['label'], P)
        for l in links:
            if not l[4] and l[3] is not None:
                kind_ = 'AE' if l[0] == 'AE' else '病史'
                ctx.append(f'关联的{kind_}编号 {l[3]} 在{kind_}记录中不存在')   # 词目型（l[3] None）不提示编号，行保持未关联口径
        jn = hb_short_jump_note(C, mid, rows)               # G3②：输血依赖方案中 Hb/比容短期跳升的输血语境提示
        if jn:
            ctx.append(jn)
        f0 = P[0]
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'test': C.metric[mid]['label'], 'mid': mid, 'grp': f0.get('group') or '',
            'pr': {'CSX': 4, 'MH': 3, 'NCS2': 3, 'NA2': 3, 'G2NF': 3, 'DISW': 3, 'NA': 3, 'MHU': 2}.get(risk, 1),
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None, r.get('wb') or ''] for r in P],   # p[10]=偏离比例（仅 REL/MHX-T 填值）；p[11]=归属工作簿（PR-8 行级归属）
            'rel': [l[:4] for l in links], 'ctx': ctx, 'q': [], 'fid': [], 'cro': '', 'mg': mg, 'risk': risk, '_aecov': sorted(aecov),
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
        b = rows[0]['base']
        bv = b.get('value') if isinstance(b, dict) else None          # 小基数绝对变化下限的基线（monitor_v5.abs_floor）
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
            if not ((above and r['pct'] >= base_f * 100) or (below and -r['pct'] >= base_f * 100)):
                continue
            af = monitor_v5.abs_floor(bv, r.get('unit') or (b or {}).get('unit') if isinstance(b, dict) else r.get('unit'))
            if af is not None:                                         # af 非 None ⇒ bv 必为数值
                dlt = (r['value'] - bv) if above else (bv - r['value'])  # 同向变化量（绝对值）
                if dlt < af:
                    continue                                           # 小基数（基线接近检测下限）：百分比 30% 门槛噪音，须同时满足绝对下限
            cand.append(r)
        if not cand:
            continue
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


def _thr_hit(C, r, sig):
    """F07（RUX 深审）：同一判据（方案不同章节重复抽出的同一阈值）命中同一检验行只保留先配置的一条。
    mm5 审阅修正：去重键含判据本身（sig＝比较方式/阈值/是否停药/类别，组合规则为规则 id）——不同含义的规则
    （ALT≥3×ULN 报告 与 ALT≥5×ULN 停药、Hy's law）各自出信号，否则停药规则与 WD-01 永不触发。返回 True 表示已登记。"""
    seen = getattr(C, '_thr_seen', None)
    if seen is None:
        seen = C._thr_seen = set()
    k = (r['sid'], r.get('wb') or '', r.get('sheet') or '', r.get('row'), r.get('mid'), sig)
    # V6（MY008：本地/中心实验室同日同指标各出一条，231 对重复）：同受试者同指标同日同判据只出一条
    kd = (r['sid'], 'day', str(r.get('date') or '')[:10], r.get('mid'), sig) if is_full_date(r.get('date')) else None
    if k in seen or (kd and kd in seen):
        return True
    seen.add(k)
    if kd:
        seen.add(kd)
    return False


_LOSS_RX = re.compile(r'丢失|下降|减少|降低|减低|loss|decrease', re.I)
_SCORE_RX = re.compile(r'Z\s*值|T\s*值|Z-?score|T-?score|SDS', re.I)


def pct_rule_norm(R):
    """V6（审阅者 2026-11-02，D002「骨密度丢失 >5%」把 Z 值 0.1→0.5 当丢失 400%：250 条假阳性）：
    较基线百分比规则的语义归一——标签写「丢失/下降/减少」而阈值写成正数 → 按下降判（pct ≤ −v）。返回 (op, v)。"""
    op, v = R.get('op', '>='), R['v']
    if R.get('on') in ('pct', 'chg') and _LOSS_RX.search(str(R.get('label') or R.get('expectAE') or '')) and op in ('>', '>=', '≥') and v > 0:
        return ('<' if op == '>' else '<='), -v
    return op, v


_LIVER_RX = re.compile(r'ALT|AST|转氨酶|谷丙|谷草|胆红素|TBIL', re.I)


_ACT_RANK = {'stop': 3, 'interrupt': 2, 'retest': 1}


def thr_level(R):
    """阈值规则的处理级别（同一检验格多档命中只取最高档写质疑）：停药 3 > 中断 2 > 复查 1 > 其他 0。"""
    acts = set(R.get('acts') or []) | ({'stop'} if R.get('stop') else set())
    return max([_ACT_RANK.get(a, 0) for a in acts] + [0])


def thr_label(R):
    """面向研究者的类别名（替代「达到方案阈值」）：按方案规定的处理动作命名。"""
    acts = set(R.get('acts') or []) | ({'stop'} if R.get('stop') else set())
    if 'stop' in acts:
        return '达到方案停药标准'
    if 'interrupt' in acts:
        return '达到方案中断给药标准'
    if 'retest' in acts:
        return '达到方案复查标准'
    if R.get('aesi'):
        return '达到方案 AESI 标准'
    if R.get('expectAE') or acts & {'record_ae', 'report'}:
        return '达到方案需记录 AE 的标准'
    return '达到方案规定的检查值标准'


def thr_rhs(R):
    """规则的判据右侧：「ALT/AST > 5 ×ULN」→「超过 5×ULN」，「ANC < 1.5 ×10^9/L」→「低于 1.5×10^9/L」，CTCAE 级别 →「达到 CTCAE 3 级」。"""
    if R.get('on') == 'grade':
        return f"达到 CTCAE {int(R['v'])} 级"
    if R.get('on') == 'chg_uln':
        return f"较基线升高{'超过' if R.get('op') == '>' else '达到'} {fmt(R.get('v'))}×ULN"
    lab = str(R.get('label') or '')
    m = re.search(r'(?:>=|<=|≥|≤|>|<)\s*(.+)$', lab)
    rhs = (m.group(1) if m else fmt(R.get('v'))).replace(' ×', '×').strip()
    op = R.get('op', '>=')
    return {'>': '超过', '>=': '达到', '<': '低于', '<=': '不高于'}.get(op, '达到') + ' ' + rhs


def threshold_ask(R, o):
    """用户 2026-11-02（问法 B）＋ 2026-11-04 审阅第 21 条：阈值类质疑不再写「达到方案阈值」，也不重复说两遍——
    「方案规定此时需在 48 小时内复查确认，并中断研究药物，请确认复查结果及研究药物处理情况」；处理动作取自方案（编译带 acts/retestH）。"""
    if not (R.get('metric') and R.get('v') is not None and o.get('cat') == '阈值规则核对'):
        return ''
    acts = list(R.get('acts') or []) + (['stop'] if R.get('stop') and 'stop' not in (R.get('acts') or []) else [])
    need, ask = [], []
    if 'retest' in acts:
        need.append(f"在 {R['retestH']} 小时内复查确认" if R.get('retestH') else '复查确认')
        ask.append('复查结果')
    if 'interrupt' in acts:
        need.append('中断研究药物')
    if 'stop' in acts:
        need.append(('确认后' if R.get('stopCond') else '') + '停用研究药物')
    if 'interrupt' in acts or 'stop' in acts:
        ask.append('研究药物处理情况')
    if R.get('aesi'):
        need.append('按 AESI 记录并在规定时限内报告')
        ask.append('是否已按 AESI 记录并报告')
    elif R.get('expectAE') or set(acts) & {'record_ae', 'report'}:
        need.append('记录为 AE')
        ask.append('是否已记录 AE')
    if not ask:
        ask.append('复查与评估情况')
    tail = "，并核对同期总胆红素以评估是否符合 Hy's law" if (R.get('on') == 'uln' and _LIVER_RX.search(str(o.get('test') or ''))) else ''
    return (f"方案规定此时需{'，并'.join(need)}，" if need else '') + f"请确认{'及'.join(ask)}{tail}。"


def thr_handled(C, sid, r, R, rows):
    """阈值规则要求的处理（复查 / 中断或停药）在记录中是否都已见到：都见到 → 返回说明；缺任一项 → None（照常发质疑）。
    复查＝同指标在命中后 ≤（复查时限天数＋1）天内另有一次测量；中断/停药＝命中前 1 天至后 7 天内有暂停/停药的给药记录，
    或同期 AE 的研究药物措施为暂停/停药。"""
    acts = set(R.get('acts') or []) | ({'stop'} if R.get('stop') else set())
    need = acts & {'retest', 'interrupt', 'stop'}
    if not need or not is_full_date(r.get('date')):
        return None
    done = []
    if 'retest' in need:
        lim = int(-(-float(R.get('retestH') or 48) // 24)) + 1
        rt = [x for x in rows if x is not r and is_full_date(x.get('date')) and 0 <= (days(x['date'], r['date']) or 0) <= lim
              and (x.get('date'), x.get('row')) != (r.get('date'), r.get('row')) and x.get('value') is not None]
        rt = [x for x in rt if days(x['date'], r['date']) > 0 or (x.get('time') and r.get('time') and x['time'] > r['time'])]
        if not rt:
            return None
        done.append(f"{rt[0]['date']} 已复查（{rt[0].get('raw')} {rt[0].get('unit') or ''}）".replace(' ）', '）'))
    if need & {'interrupt', 'stop'}:
        # 同日＝0 天：不能写 `days(...) or 99`（0 为假 → 99，RUX S01003 当天暂停/当天录 AE 被判「未处理」）
        ex = [e for e in (getattr(C, 'exposure', None) or []) if e.get('sid') == sid and dose_state(e) in ('paused', 'withdrawn') and is_full_date(e.get('start'))
              and -1 <= days(e['start'], r['date']) <= 7]
        ae = [a for a in (getattr(C, 'ae_by', None) or {}).get(sid, []) if ae_action(a.get('act')) in ('interrupted', 'withdrawn') and is_full_date(a.get('s'))
              and abs(days(a['s'], r['date'])) <= 7]
        if not ex and not ae:
            return None
        done.append(f"{ex[0]['start']} 起暂停/停用研究药物" if ex else f"AE“{ae[0]['t']}”（{ae[0]['s']}）对研究药物采取了暂停/停药措施")
    return '；'.join(done)


def threshold_rules(C):
    """analysis.thresholdRules: protocol-defined numeric triggers (AESI/AE/stopping/eligibility-like) evaluated per finding.
    不同阈值（3×ULN 报告、5×ULN 停药）是不同判据，各自出信号（mm5 审阅修正口径，V6 不改）；只修文案里漏出的正则写法。"""
    for R in C.A.get('thresholdRules', []):
        mre = re.compile(R['metric'])
        r_op, r_v = pct_rule_norm(R)
        are = rx(R.get('expectAE'))
        vis = set(R.get('visits') or [])
        seen = set()
        for (sid, mid), rows in C.F.items():
            if sid not in C.pop or not mre.search(mid):
                continue
            if R.get('on') == 'pct' and _SCORE_RX.search(C.metric[mid]['label']):
                continue                                 # Z/T 值可正可负、近 0，百分比变化无意义（骨密度规则只看 g/cm² 等测量值）
            for r in rows:
                if R.get('post', True) and not r['post']:
                    continue
                if vis and r.get('visit') not in vis:
                    continue
                on = R.get('on', 'val')
                b_ = r.get('base') or {}
                if R.get('baseCond') and isinstance(b_.get('value'), (int, float)):
                    b_abn = (b_.get('hi') is not None and b_['value'] > b_['hi']) or (b_.get('lo') is not None and b_['value'] < b_['lo'])
                    if (R['baseCond'] == 'abn') != bool(b_abn):
                        continue                         # 方案只对「基线异常/基线正常」一类受试者适用该阈值
                x = {'val': r.get('value'), 'chg': r.get('chg'), 'pct': r.get('pct'),
                     'chg_uln': (r['chg'] / r['hi']) if r.get('chg') is not None and r.get('hi') else None,
                     'uln': (r['value'] / r['hi']) if r.get('value') is not None and r.get('hi') else None,
                     'lln': (r['value'] / r['lo']) if r.get('value') is not None and r.get('lo') else None,
                     'grade': r.get('grade')}.get(on)                    # mm4：方案按 CTCAE 级别定义的阈值（如 3 级血细胞减少）
                if not cmp(r_op, x, r_v):
                    continue
                if on == 'pct' and not ((r.get('base') or {}).get('value') or 0) > 0:
                    continue                             # 基线 ≤0 时百分比变化无定义
                if R.get('once') and (sid, R['id']) in seen:
                    continue
                seen.add((sid, R['id']))
                if _thr_hit(C, r, ('thr', R.get('on', 'val'), R.get('op', '>='), R['v'], bool(R.get('stop')), R.get('cat'))):
                    continue
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
                if R.get('partial'):
                    risk = 'PART'
                    ctx.append('方案定义为复合条件（' + str(R['partial'])[:60] + '…），单项达标只作提示，不构成该事件')
                hd = thr_handled(C, sid, r, R, rows)
                if hd:                                   # V6 医学审阅（RUX S01003/S01007 NEU<1.5 均已当天暂停、次日复查并录 AE，仍被要求「确认复查与处理」）
                    pr = min(pr, 1)                      # 记录显示已按方案处理 → 只作提示，不发质疑
                    ctx.append('记录显示已按方案处理：' + hd)
                thr_l = thr_rhs(R) if not R.get('sum') else str(R.get('label', f"{R.get('op', '>=')}{R['v']}")).replace('|', '/')
                b = r.get('base') or {}
                # V6（用户审阅 RUX 第 21 条）：不写「达到方案阈值」——写清检查值相对方案标准的关系（「低于 1.5×10^9/L」）
                dflt = '{visit}访视（{date}）{test} 由基线 {base} 升至 {value} {unit}，{thr}' if R.get('on') == 'chg_uln' else '{visit}访视（{date}）{test} {value} {unit}，{thr}'
                summ = fill(R.get('sum', dflt), test=C.metric[mid]['label'], value=r.get('raw'),
                            unit=r.get('unit') or '', visit=r.get('visit'), date=dshow(r.get('date')), thr=thr_l,
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
                    c0 = conds[0]                 # 单条件、无排除条件的组合规则与单列阈值是同一判据
                    sig = (('thr', c0.get('on') or 'val', c0.get('op', '>='), c0['v'], bool(R.get('stop')), R.get('cat', '阈值规则核对'))
                           if len(conds) == 1 and not nots else ('combo', R.get('id') or R.get('name')))
                    if _thr_hit(C, r0, sig):
                        continue                  # F07：同一组合规则重复配置时只出一条（不影响其余行与其他规则）
                    summ = fill(R.get('sum', '{name}：{detail}（{visit} {date}）'), name=R.get('name', R['id']), detail=det, visit=r0.get('visit'), date=r0['date'])
                    add_other(C, sid, R.get('cat', '阈值规则核对'), pr, summ, r0.get('visit'), r0['date'], r0['sheet'], r0['row'], C.metric[r0['mid']]['label'],
                              r0.get('clin'), rel, ctx, risk, R, R.get('lane'), R.get('level'),
                              bkey=f"{C.metric[r0['mid']]['label']}|{r0.get('visit') or ''}|{r0['date']}", wb=r0.get('wb') or '')
                    if R.get('once', True):
                        break


_GEN_BG = {'升高', '降低', '增高', '减少', '异常', '增加', '下降', '检查', '计数', '水平', '指标', '数值'}


def _bigrams(s):
    s = re.sub(r'[（(].*?[)）]|\s', '', str(s or ''))
    return {s[i:i + 2] for i in range(len(s) - 1)} - _GEN_BG


def ae_lab_same(C, a, r):
    """AE 与检验是否同一事件：项目 aeMatch（指标正则→AE 术语正则）命中，或 CTCAE 条目名/指标名与 AE 术语有共同实义双字。"""
    mid = r.get('mid') or ''
    for x in C.A.get('aeMatch') or []:
        try:
            if re.search(x[0], mid) and re.search(x[1], a.get('t') or ''):
                return True
        except re.error:
            continue
    at = _bigrams(a.get('t')) | _bigrams(a.get('pt'))
    return bool(at & (_bigrams(r.get('gterm')) | _bigrams(r.get('test'))))


def ae_checks(C):
    on = set(C.A.get('aeChecks', ['predose_related', 'grade_vs_lab', 'cm_flag', 'cm_missing', 'aesi_terms', 'aesi_unmatched',
                                  'duplicate', 'severity_logic', 'grade_floor']))
    lab_by_ae = defaultdict(list)
    for (sid, mid), rows in C.F.items():
        for r in rows:
            for l in r.get('links') or []:
                if l[0] == 'AE':
                    lab_by_ae[(sid, str(l[3]))].append(r)
    for a in C.aes:
        sid = a['sid']
        if sid not in C.pop or a.get('dup'):      # F08：重复记录成员（第 2 份起）不逐条发质疑，组首已覆盖同一事实
            continue
        if 'predose_related' in on and a['pre'] and a['_rel']:
            add_other(C, sid, 'AE给药前事件相关性核对', 3, f"AE「{a['t']}」开始于首剂（{a['fd']}）前 {a['s']}，相关性记为「{a['rel']}」", None, a['s'], a['sh'], a['row'], a['t'],
                      rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'grade_vs_lab' in on:
            # V6（MM 审阅：「肝酶升高」AE 拿去比中性粒细胞等级）：只比与该 AE 同一事件的检验（aeMatch 命中或 CTCAE 条目/指标名与 AE 术语同词）
            rs = [r for r in lab_by_ae[(sid, str(a['n']))] if r.get('grade') and ae_lab_same(C, a, r)]
            gi = grade_int(a['g']) or 0
            mx = max(rs, key=lambda r: r['grade']) if rs else None
            if mx and mx['grade'] > gi:
                add_other(C, sid, 'AE分级与检验等级核对', 3, f"AE「{a['t']}」记 {a['g']}，关联检验 {mx['test']} {mx.get('raw')} {mx.get('unit') or ''}（{dshow(mx.get('date'))}）达 {C.GL} {mx['grade']} 级（{mx['gterm']}）",
                          mx.get('visit'), mx.get('date'), mx['sheet'], mx['row'], mx['test'], mx.get('clin'), [['AE', a['t'], a['s'], a['n']]], risk='AE')
        if 'cm_flag' in on and re.search(r'^否|^N', a['cm'] or ''):
            cms = [c for c in C.cm_by[sid] if c['wk'] == 'AE' and (a['t'] and a['t'] in c['why'] or re.search(rf'\b{a["n"]}\b', c['why']))]
            if cms:
                add_other(C, sid, 'AE合并用药标记核对', 2, f"AE「{a['t']}」记「是否有合并用药=否」，但合并用药「{cms[0]['t']}」用药原因指向该 AE", None, a['s'], a['sh'], a['row'], a['t'],
                          rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'cm_missing' in on and re.search(r'^是|^Y', a['cm'] or '') and C.cm_by[sid]:
            # mm4：AE 记「有合并用药」，但合并用药页未见引用该 AE（AE 编号字段或用药原因指向该 AE）
            ref = [c for c in C.cm_by[sid] if re.search(rf'(?<!\d){re.escape(str(a["n"]))}(?!\d)', c.get('aeno') or '')
                   or (a['t'] and a['t'] in (c['why'] or '')) or (c['wk'] == 'AE' and re.search(rf'(?<!\d){re.escape(str(a["n"]))}(?!\d)', c['why'] or ''))]
            if not ref and any(c.get('aeno') or c['wk'] for c in C.cm_by[sid]):
                add_other(C, sid, 'AE合并用药记录核对', 3, f"AE「{a['t']}」（{dshow(a['s'])}）记「是否有合并用药=是」，合并用药页未见引用该 AE 的记录", None, a['s'], a['sh'], a['row'], a['t'],
                          rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'aesi_terms' in on and a['_aesi_def'] and not a['aesi'] and not a['pre']:
            add_other(C, sid, 'AESI标记核对', 3, f"AE「{a['t']}」符合方案 AESI 定义（{'、'.join(a['_aesi_def'])}），但「是否AESI」未勾选", None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE')
        if 'severity_logic' in on:
            # F-E（IMP-04）：高级别（默认 ≥3 级）AE 未按 SAE 且 SAE 标准全未勾选 → 内部矛盾，请核实严重性判定
            #（不作 SAE 违规断言——是否构成 SAE 由研究者/方案定义；已停药/暂停者在文案中带出）。
            # V6 R5（审阅者 2026-11-02）：严重程度（分级）≠ 严重性（seriousness，ICH E2A）——3 级本身不构成 SAE。
            # 只在有矛盾证据时提示：≥4 级（危及生命属严重性标准）；或 3 级且结局/处理/原文含 住院/死亡/危及生命。
            # 实验室定义的事件（SOC 为各类检查、或术语为「XX 升高/降低」）不按此规则（3–4 级化验异常常不构成 SAE）。
            gi2 = grade_int(a['g']) or 0
            ev = ' '.join(str(a.get(k) or '') for k in ('out', 'act', 't', 'sae_crit'))
            lab_ev = bool(re.search(r'各类检查|Investigations', str(a.get('soc') or ''), re.I)
                          or re.search(r'(升高|降低|增高|减少|下降|异常|增加)$', str(a['t'] or '')))
            hosp = bool(re.search(r'住院|死亡|致死|危及生命', ev))
            floor = int(C.A.get('severeGradeNosae', 4))
            if (not lab_ev and (gi2 >= floor or (gi2 == floor - 1 and hosp)) and not a['sae']
                    and not str(a.get('sae_crit') or '').strip()):
                stopw = '，且对研究用药已停药/暂停' if re.search(r'停|暂停|终止', str(a.get('act') or '')) else ''
                why = '有住院/死亡相关记录' if hosp and gi2 < floor else f'记 {a["g"]}（达危及生命级别）'
                add_other(C, sid, 'AE严重性逻辑核对', 3,
                          f"AE「{a['t']}」{why}，但未按 SAE（SAE 标准均未勾选）{stopw}——请核实严重性判定",
                          None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
        if 'grade_floor' in on:
            # F-E（IMP-04）：gradeFloor（配置驱动，如分级标准中「X 衰竭」类术语最低 2 级）——低于下限疑编码/分级错误。
            # 术语→最低级别属标准/方案知识，由 rules 层编译进 analysis.gradeFloor（{re, min, label}），脚本只放通用机制。
            for R in C.A.get('gradeFloor') or []:
                if not R.get('re') or not R.get('min'):
                    continue
                gi3 = grade_int(a['g']) or 0
                if gi3 and gi3 < int(R['min']) and re.search(R['re'], ' '.join(x for x in (a['t'], a.get('pt') or '') if x)):
                    add_other(C, sid, 'AE分级下限核对', 3,
                              f"AE「{a['t']}」记 {a['g']}，但分级标准中「{R.get('label') or R['re']}」类术语至少 {R['min']} 级——疑编码或分级错误，请核实",
                              None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]], risk='AE', wb=a.get('wb') or '')
                    break
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
        for g in getattr(C, 'ae_dup', None) or []:      # F08：成对/三联记录标记——每组一条，证据指向全部重复行
            if g['sid'] not in C.pop:
                continue
            rows = '、'.join(_ae_ref(x) for x in g['recs'])     # V6 措辞排查：不写「#2（行 12）」，行号已在证据定位里
            add_other(C, g['sid'], 'AE重复记录核对', 2, f"同一受试者“{g['term']}”同一开始日期（{g['start']}）记录了 {len(g['recs'])} 条 AE（{rows}），请核实是否重复录入或修订未归并",
                      None, g['start'], g['recs'][0]['sh'], g['recs'][0]['row'], g['term'],
                      rel=[['AE', x['t'], x['s'], x['n']] for x in g['recs']], risk='AE',
                      wb=g['recs'][0].get('wb') or '')
        for sid, L in C.ae_by.items():
            for i, x in enumerate(L):
                for y in L[i + 1:]:
                    if not (x['s'] and y['s'] and (not x['e'] or y['s'] <= x['e']) and (not y['e'] or x['s'] <= y['e'])):
                        continue
                    # mm4 用户裁定（2026-10-30）：风险＝同一临床事实（同受试者、时间重叠）下记录了**不同 PT** 的 AE
                    # （疑似重复记录或编码不一致）；同一 PT（含原文写法不同）视为同一 AE，不发；
                    # pt 缺失（字典降级）时本规则不运行（知识层降级状态在研究依据页可见）。
                    if not x.get('pt') or not y.get('pt') or x['pt'] == y['pt']:
                        continue
                    # mm5 用户决定（2026-10-31）：只留疑似同一事件——同 SOC 且术语相近（同一指标/事件词的上下位或升降写法）；
                    # ALT 与 AST、CK 与 LDH 这类同期并发的不同 AE 不提示
                    if not (x.get('soc') and x.get('soc') == y.get('soc') and (_ae_similar(x['pt'], y['pt']) or _ae_similar(x['t'], y['t']))):
                        continue
                    add_other(C, sid, 'AE一致性核对（PT级）', 2, f"同一受试者同期记录了不同 AE（PT 级：{x['pt']} vs {y['pt']}）："
                              f"“{x['t']}”（{_ae_ref(x, True)}）与“{y['t']}”（{_ae_ref(y, True)}），请核实是否重复记录或编码不一致",
                              None, y['s'], y['sh'], y['row'], y['t'], rel=[['AE', x['t'], x['s'], x['n']], ['AE', y['t'], y['s'], y['n']]], risk='AE')


def _ae_ref(x, span=False):
    """AE 的中心可读定位：有可用编号写「AE 2」，否则写起止日期（EDC 记录号不可用时不露 #0）。"""
    n = str(x.get('n') if x.get('n') is not None else '').strip()
    d = f"{x.get('s') or ''}~{x.get('e') or '持续'}"
    if n and n not in ('0', 'None'):
        return f"AE {n}，{d}" if span else f"AE {n}"
    return d


_AE_DIR_WORDS = re.compile(r'升高|降低|增高|减低|增加|减少|增多|异常|阳性|升|降|偏高|偏低|计数|水平|值')
_AE_PREFIX = re.compile(r'^(?:血清|血浆|血|尿|全血)')


def _ae_core(s):
    """AE 术语核心词：去掉方向词与标本前缀（「血胆红素升高」→「胆红素」，「结合胆红素升高」→「结合胆红素」）。"""
    return _AE_PREFIX.sub('', _AE_DIR_WORDS.sub('', str(s or '')).strip())


def _ae_similar(a, b):
    """两个 AE 术语是否疑似同一事件：核心词一方包含另一方（至少 2 字）。"""
    x, y = _ae_core(a), _ae_core(b)
    return bool(x and y and min(len(x), len(y)) >= 2 and (x in y or y in x))


def _corroborated(C, sid, r):
    """尖峰有旁证＝同日同表单另有 ≥2 项超出参考范围，或该日处于某条 AE 的持续期内 → 不按录入错误提示。"""
    d, sh = r.get('date'), r.get('sheet')
    if not is_full_date(d):
        return False
    n = 0
    for (s2, _m), rows in C.F.items():
        if s2 != sid:
            continue
        for x in rows:
            if x is not r and x.get('date') == d and x.get('sheet') == sh and finding_abn(x):
                n += 1
                if n >= 2:
                    return True
    return any(ext_rules.ae_covers(a, d) for a in (getattr(C, 'ae_by', None) or {}).get(sid, []))


def entry_errors(C):
    """mm5 疑似录入错误（用户 2026-10-31：某指标多次都在 50 上下、突然一次 500 多 → 很可能小数点/单位录错）。
    只看检验/生命体征/心电图数值（有效性另有「有效性数据量级异常」）。判据（同受试者同指标、该指标 ≥4 个数值）：
    ①孤立尖峰——前后相邻两次都在本人其余结果中位数的 2 倍以内（持续上升的真实变化如药物性肝损伤不算）；
    ②与本人其余结果中位数之比约为 10 的整数次幂（±15%，疑似小数点错位）或 ≥20 倍/≤1/20（疑似录入或单位错误）。
    另：单位与本人该指标多数记录（≥3 条）不同 → 单位不一致。只作数据质量提示（临床监察页），不发医学质疑；
    该点若也进了医学风险层，风险行上下文标「可能为录入错误，请先核对源数据」，避免对录入错误发医学质疑。"""
    import math
    C.entry = []
    skip = re.compile(C.A.get('entryCheckExclude') or r'尿.*(白细胞|红细胞|隐血|潜血|管型|上皮|细菌|结晶|酵母)|隐血|潜血')   # 尿沉渣计数天然大幅波动

    def ucanon(u):                                       # 等价单位写法视为相同（U/L＝IU/L，×10^9/L＝10^9/L，µ＝μ＝u，前导/尾随装饰斜杠：/fL＝fL/＝fL）
        u = re.sub(r'\s|×|\*', '', str(u or '')).lower().replace('µ', 'u').replace('μ', 'u').replace('秒', 's').strip('/')
        u = {'ng/ml': 'ug/l', 'ug/ml': 'mg/l', 'pg/ml': 'ng/l', 'mmol/l': 'mmol/l', 'meq/l': 'mmol/l'}.get(u, u)   # 数值等价的单位写法（铁蛋白 ug/L＝ng/mL）
        return '' if u in ('na', 'n/a', '/', '-', '—', '无', '') else re.sub(r'^iu', 'u', u).replace('/iu', '/u')
    series = []
    for (sid, mid), rows in C.F.items():
        if mid.split(':')[0] not in ('lab', 'vs', 'ecg') or skip.search(C.metric[mid]['label']):
            continue
        # MY008 第 8 轮运营复审：本地/中心实验室两张表的同名指标（网织红中心记小数 0.108、本地记百分数 10.8%）合成一条序列 →
        # 互判对方「疑似小数点错位」约 50 条。按表单分开比较（同一检测来源内部才可比）
        by_sh = defaultdict(list)
        for r in rows:
            by_sh[r.get('sheet')].append(r)
        series += [(sid, mid, rs) for rs in by_sh.values()]
    for sid, mid, rows in series:
        num = [r for r in sorted(rows, key=lambda r: (r.get('date') or '', r.get('time') or '', r.get('row') or 0))
               if isinstance(r.get('value'), (int, float)) and r['value'] > 0]
        units = Counter(ucanon(r.get('unit')) for r in num if ucanon(r.get('unit')))
        mu, mn = (units.most_common(1) or [('', 0)])[0]
        for i, r in enumerate(num):
            why = ''
            if len(num) >= 4:
                others = [x['value'] for j, x in enumerate(num) if j != i]
                med = statistics.median(others)
                ratio = r['value'] / med if med > 0 else None
                if ratio and (ratio >= 8 or ratio <= 1 / 8):
                    k = round(math.log10(ratio))
                    near_pow = k != 0 and abs(math.log10(ratio) - k) <= math.log10(1.15)
                    nb = [num[j]['value'] for j in (i - 1, i + 1) if 0 <= j < len(num)]
                    isolated = bool(nb) and all(0.5 <= v / med <= 2 for v in nb)
                    if isolated and near_pow:
                        why = (f"约为本人其余结果的 {10 ** k} 倍" if k > 0 else f"仅约为本人其余结果的 1/{10 ** -k}") + "，疑似小数点错位"
                    elif isolated and (ratio >= 20 or ratio <= 1 / 20):
                        why = (f"为本人其余结果中位数（{fmt(med)}）的 {fmt(ratio, 0)} 倍" if ratio >= 1 else
                               f"仅为本人其余结果中位数（{fmt(med)}）的 1/{fmt(1 / ratio, 0)}") + "，疑似录入或单位错误"
            if why and '单位' not in why and _corroborated(C, sid, r):
                why = ''                                 # V6（MM 审阅：CK 14.5×ULN 同日 AST 升高、同期 AE → 更像真实损伤，不当录入错误）
            if not why and mn >= 3 and ucanon(r.get('unit')) and ucanon(r['unit']) != mu:
                mu_raw = next((str(x.get('unit')) for x in num if ucanon(x.get('unit')) == mu), mu)
                why = f"单位「{r['unit']}」与本人其余记录（「{mu_raw}」）不同，请核对单位与数值"
            if why:
                r['_entry'] = why
                C.entry.append({'sid': sid, 'site': C.subj[sid]['site'], 'test': C.metric[mid]['label'], 'visit': r.get('visit') or '',
                                'date': r.get('date') or '', 'raw': r.get('raw'), 'unit': r.get('unit') or '', 'why': why,
                                'sh': ev_sh(C, r.get('sheet'), r.get('wb') or ''), 'row': r.get('row')})
    for g in C.labrows:                                  # 同一点也在医学风险层：先核对源数据，避免对录入错误发医学质疑
        hit = [x for x in C.F.get((g['sid'], g.get('mid')), []) if x.get('_entry') and any(p[7] == x.get('sheet') and p[8] == x.get('row') for p in g['pts'])]
        if hit:
            g['ctx'].append(f"可能为录入错误，请先核对源数据：{hit[0].get('visit')} {hit[0].get('raw')} {hit[0].get('unit') or ''}（{hit[0]['_entry']}）")


def build_ops(C):
    """mm5 临床监察数据块（KZ.ops，前端「临床监察」页）：受试者里程碑、访视记录、方案访视窗、给药依从摘要、知情版本、疑似录入错误。
    全部来自已映射的 listing 字段；EDC 录入/核查时间戳 listing 中没有，录入及时性与 SDV 进度不做。"""
    vis = defaultdict(list)
    first = {}
    for v in C.visits:
        if v.get('visit'):
            vis[v['sid']].append([v['visit'], v.get('date') or ''])
        d = v.get('date')
        if is_full_date(d) and (v['sid'] not in first or d < first[v['sid']]):
            first[v['sid']] = d
    ex = defaultdict(lambda: {'n': 0, 'miss': 0, 'pause': 0, 'fast': 0, 'devi': 0})
    for e in C.exposure:
        x = ex[e['sid']]
        x['n'] += 1
        x['miss'] += bool(e.get('miss_qty') not in (None, '', 0, '0')) or zero_dose(e)
        x['pause'] += bool(str(e.get('pause') or '').strip() and not re.match(r'^(否|无|N|No)$', str(e.get('pause')).strip(), re.I))
        x['fast'] += bool(re.match(r'^(否|未空腹|N|No)$', str(e.get('fast') or '').strip(), re.I))
        # MY008 第 8 轮运营审阅：计划「900 mg」vs 实际「900」按文本比较 → 496 条假剂量偏离。按数值比较（单位写法不计），任一方不是数值不判
        dp, da = _dose_num(e.get('dose_plan')), _dose_num(e.get('dose_act'))
        x['devi'] += bool(dp is not None and da is not None and abs(dp - da) > 1e-9 * max(1, abs(dp)))
    icf = defaultdict(list)
    for r in C.icf:
        icf[r['sid']].append([str(r.get('ver') or ''), r.get('date') or ''])
    subs = []
    sfw = ie_fail_reasons(C)
    for sid, s in C.subj.items():
        subs.append([sid, s['site'], s['status'], s.get('icf') or '', first.get(sid, ''), s.get('rand') or '', s.get('rand_d') or '',
                     s['fd'] or '', s['ld'] or '', s.get('eot_d') or '', s.get('eot_why') or '', s.get('eos_d') or '', s.get('eos_why') or '',
                     1 if str(s.get('rescreen') or '').strip() in ('是', 'Y', '1', 'True', 'true') else 0, s.get('prev_sid') or '',
                     sfw.get(sid, '') or (sf_fallback(C, sid, s) if s['status'] == '筛选失败' else '')])
    alld = [d for d in (f.get('date') for f in C.findings) if is_full_date(d)]
    C.ops = {'subs': subs, 'vis': dict(vis), 'win': C.A.get('visitWindows') or {}, 'planned': (C.S.get('study') or {}).get('planned'),
             'cutoff': C.cfg.get('study', {}).get('cutoff') or (max(alld) if alld else ''), 'stage': C.cfg.get('dataStage') or '',
             'ex': {k: v for k, v in ex.items()}, 'icf': dict(icf), 'entry': C.entry,
             'fields': ['id', 'site', 'status', 'icf', 'first', 'rand', 'rand_d', 'fd', 'ld', 'eot_d', 'eot_why', 'eos_d', 'eos_why', 'rescreen', 'prev', 'sf_why']}


def _ie_label(r):
    cat = str(r.get('ie_cat') or '')
    kind = '排除标准' if re.search(r'排除|EX', cat, re.I) else '入选标准' if re.search(r'入选|IN', cat, re.I) else '入排标准'
    no = re.sub(r'^0+(?=\d)', '', str(r.get('crit') or '').strip())
    return f"{kind} {no}".strip()


def arm_name(g):
    """分组名归一：去掉随机系统导出的组名尾缀标记（RUX 受试者报表「磷酸芦可替尼乳膏治疗组Y / 安慰剂组N」——Y/N 含义待项目确认，
    不拆成四组）。"""
    if g in (None, ''):
        return g
    return re.sub(r'(组|arm|group)\s*[YN]$', r'\1', str(g).strip(), flags=re.I)


def ie_fail_reasons(C):
    """入排标准页（ie 域）：不满足的标准 → {sid: '排除标准 5、入选标准 4'}（筛选失败原因；V6 用户审阅 RUX 第 4 条：49 名筛败者原因全显示「未注明」）。"""
    rows = getattr(C, 'ie', []) or []
    yes = lambda r: bool(re.match(r'^(是|Y|Yes|满足|符合)', str(r.get('met') or '').strip(), re.I))
    no = lambda r: bool(re.match(r'^(否|N|No|不满足|不符合)', str(r.get('met') or '').strip(), re.I))
    # 两种页面形态：① 总问「是否满足全部入选且不符合任何排除」＋否时填不满足的标准（RUX）；
    # ② 逐条标准一行（CDISC IE：排除标准「是」＝符合排除＝不合格）。「是」的行也填了标准编号 → ②
    # ③ 反问形态（D001「是否有不符合的入选标准或符合的排除标准？」）：「是」＝有违反，后填违反条款——62 例曾被判「满足全部标准」
    neg_q = lambda r: bool(re.search(r'是否(有|存在).{0,6}(不符合|不满足|违反)|是否(有|存在).{0,10}符合的?排除', str(r.get('met_q') or '')))
    per_crit = any(yes(r) and r.get('crit') and not neg_q(r) for r in rows)
    out = defaultdict(list)
    for r in rows:
        exc = _ie_label(r).startswith('排除')
        bad = yes(r) if neg_q(r) else (yes(r) if exc else no(r)) if per_crit else no(r)
        if bad and (r.get('crit') or r.get('ie_cat')):
            lab = _ie_label(r)
            if lab not in out[r['sid']]:
                out[r['sid']].append(lab)
    return {k: '、'.join(v) for k, v in out.items()}


def sf_fallback(C, sid, s):
    """筛败原因的兜底（V6 运营审阅：入排页记「满足全部标准」的 7 例显示「未注明」）：筛选结束/研究结束页原因 → 入排页全部满足的矛盾提示。"""
    why = str(s.get('eos_why') or s.get('eot_why') or '').strip()
    if why:
        return why
    rows = [r for r in (getattr(C, 'ie', []) or []) if r.get('sid') == sid]
    if rows and not any(re.search(r'是否(有|存在).{0,6}(不符合|不满足|违反)|符合的?排除', str(r.get('met_q') or '')) for r in rows) and \
            all(re.match(r'^(是|Y|Yes|满足|符合)', str(r.get('met') or '').strip(), re.I) for r in rows):
        return '入排页记录满足全部标准，筛败原因未记录（请核对）'
    return ''


def ie_checks(C):
    """入排标准页记录「不满足」但已随机/给药 → 入排核对信号（判定状态 violated，生成入组资格偏离）。"""
    for sid, why in sorted(ie_fail_reasons(C).items()):
        if sid not in C.pop:
            continue
        r = next(x for x in C.ie if x['sid'] == sid)
        o = add_other(C, sid, '入排标准核对', 4, f"入排标准页记录不满足{why}，但已随机/给药", r.get('visit'), r.get('date') or C.subj[sid].get('icf'),
                      r.get('sheet', ''), r.get('row'), bkey=f"ie|{why}", wb=r.get('wb') or '')
        o['_elig'] = 'violated'


def range_checks(C):
    """mm4：参考范围缺失——同一实验室指标多数记录有参考范围，而该记录数值存在但上下限均缺失（无法判异常与分级）。
    V6：受试者×表单×日期一条（同页各指标进上下文）；同一中心同一表单 ≥3 例缺失 → 中心系统性问题，转中心沟通提示（pr2，不逐例发 query）。"""
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
    # V6 R4（审阅者 2026-11-02，四项目复盘：同一张化验单漏填范围被按指标拆成十几条 query）：
    # 按（受试者，表单，日期）合并为一条——CRC 是按一张化验单补范围的；同中心同表单 ≥3 例 → 中心系统性问题
    page = defaultdict(list)
    for (sid, mid), rows in miss.items():
        for r in rows:
            page[(sid, r['sheet'], r.get('date') or '')].append((mid, r))
    site_n = Counter()
    for sh_site in {(C.subj[sid]['site'], sh, sid) for (sid, sh, _) in page}:
        site_n[sh_site[:2]] += 1
    for (sid, sh, d), items in sorted(page.items()):
        items.sort(key=lambda x: x[1].get('row') or 0)
        r = items[0][1]
        labs = list(dict.fromkeys(C.metric[mid]['label'] for mid, _ in items))
        n_site = site_n[(C.subj[sid]['site'], sh)]
        systemic = n_site >= 3
        ctx = [f"同页未填范围的指标：{'、'.join(labs[:12])}{'…' if len(labs) > 12 else ''}"] if len(labs) > 1 else []
        if systemic:
            ctx.append(f"中心系统性未填（本中心本表单 {n_site} 例）：建议中心层面沟通，不逐例发 query")
        mid0 = items[0][0]
        add_other(C, sid, '参考范围缺失核对', 2 if systemic else 3,
                  f"{r.get('visit')}（{dshow(r.get('date'))}）{sh} 有 {len(labs)} 项结果未填写参考范围"
                  f"（如 {C.metric[mid0]['label']} {r.get('raw')} {r.get('unit') or ''}；同指标 {stats[mid0][0]}/{stats[mid0][1]} 条记录有范围）",
                  r.get('visit'), r.get('date'), r['sheet'], r['row'], '、'.join(labs[:3]), r.get('clin'), ctx=ctx,
                  rule={'ask': '请补充该页检验结果的参考范围（上下限），并据此核对临床意义评价。'},
                  bkey=f"{sh}|{d}|range", wb=r.get('wb') or '')


def overlap(c, a, b):
    s, e = c['s'] or '0000', (c['e'] or '9999') if not c['ong'] else '9999'
    return s <= (b or '9999') and e >= (a or '0000')


_TOPICAL = re.compile(r'外用|外涂|涂抹|涂擦|外搽|外敷|局部|皮肤|软膏|乳膏|霜|凝胶|洗剂|搽剂|酊|贴|滴眼|滴鼻|吸入|喷雾|topical|cream|ointment|gel|lotion', re.I)
_SYSTEMIC = re.compile(r'系统|全身|口服|静脉|注射|systemic', re.I)
_NONDERMAL = re.compile(r'吸入|雾化|气雾|喷鼻|鼻喷|滴鼻|鼻用|鼻.{0,2}喷雾|滴眼|眼用|眼膏|滴耳|inhal|nasal|ophthalm', re.I)
# F2：外用（皮肤局部）排除口径——比 _NONDERMAL 多含注射/静脉/口服（非皮肤给药都不算外用；
# 注意不得改 _NONDERMAL 本身：系统性条目靠它放行吸入/鼻用局部药，注射是全身给药）。
_NONSKIN = re.compile(r'吸入|雾化|粉吸入|气雾|喷鼻|鼻喷|滴鼻|鼻用|鼻.{0,2}喷雾|滴眼|眼用|眼膏|滴耳|注射|静脉|肌注|皮下注射|口服|inhal|nasal|ophthalm|inject', re.I)

# F1（通用药理词典条目，非项目特判）：二代非镇静抗组胺（通用名级）。条款写「镇静抗组胺药」且同条允许/可使用
# 非镇静类时（RUX 实证：依巴斯汀等被「镇静抗组胺药」条款整体扫入，方案原文明确允许非镇静类），该子类不算
# 本条款的禁用/洗脱对象；一代镇静类（氯苯那敏/苯海拉明/异丙嗪/酮替芬/赛庚啶等）照常命中。
_NONSEDATING_AH = re.compile(r'西替利嗪|左西替利嗪|氯雷他定|地氯雷他定|非索非那定|依巴斯汀|卢帕他定|比拉斯汀|奥洛他定|阿伐斯汀'
                             r'|咪唑斯汀|依美斯汀|左卡巴斯汀|氮[卓䓬]斯汀', re.I)
_ALLOW_NONSEDATING = re.compile(r'(允许|可以?使用|可用|但可|不受限制)[^。；]{0,24}非镇静|非镇静[^。；]{0,16}(允许|可以?使用|可用)')


def _nonsedating_exempt(P):
    """该禁用/洗脱条款是否「镇静抗组胺…（允许/可使用非镇静…）」形态：是则非镇静子类不命中本条款。"""
    t = ' '.join(str(P.get(k) or '') for k in ('name', 'note', 'cond'))
    return bool(re.search(r'(?<!非)镇静抗组胺', t) and _ALLOW_NONSEDATING.search(t))


def _cls_txt(P, c):
    """F3：药物类属描述收口——只列该药实际命中的类（classes＝[[类名, 成员正则], …]，顿号连接），
    无命中写「禁用类待核对」；条目无 classes（旧配置/单一类名）回退条目名，不贴整段禁用类清单。"""
    cl = P.get('classes')
    if not cl:
        return P.get('name', '')
    hit = [nm for nm, rxx in cl if rxx and re.search(rxx, f"{c.get('rt') or ''} {c.get('t') or ''}", re.I)]
    return '、'.join(hit) if hit else '禁用类待核对'


def _not_topical_cm(c):
    """F2：该合并用药记录不是皮肤局部给药（吸入/雾化/粉吸入/气雾/鼻用/眼用/注射等）——「外用疗法」类不套。"""
    loc_ = f"{c.get('rt') or ''} {c.get('t') or ''}"
    return (not (_TOPICAL.search(c.get('rt') or '') or _TOPICAL.search(c['t']))) or _NONSKIN.search(loc_)


def restricted_checks(C):
    """限用药（analysis.restricted：须筛选前稳定剂量使用 ≥N 天、研究期间不得新加/停用）。V6（MY008 医学审阅：疗效期新起泼尼松、
    铁剂、艾多沙班，停用雄激素/抗凝药全未提示）：首剂后新开始、或在治疗期内停用 → 提示核实（是否符合方案、是否需记偏离）；
    首剂前开始但距首剂不足 N 天 → 稳定期不足。"""
    rescue_re_r = re.compile(r'补救|rescue', re.I)
    rst_seen = set()                                 # 同一条用药只归一条限用规则
    for R in C.A.get('restricted') or []:
        rx_ = re.compile(R['re'], re.I)
        n = R.get('stableDays')
        for sid in sorted(C.pop):
            s = C.subj[sid]
            if not is_full_date(s.get('fd')):
                continue
            end_tx = s.get('ld') if is_full_date(s.get('ld')) else (s.get('lo') or '')
            hits = defaultdict(list)                  # 同一药物多条记录（减量/逐段录入）合并为一条：按药名归组
            for c in C.cm_by[sid]:
                if not rx_.search(c['t']):
                    continue
                loc_ = f"{c.get('rt') or ''} {c['t']}"
                if rescue_re_r.search(c.get('why') or ''):
                    continue                          # 方案补救治疗由补救规则核查（D001 第 4 周后外用激素补救曾被套进限用药）
                if R.get('route') == 'local' and not re.search(r'吸入|雾化|气雾|喷鼻|鼻喷|滴鼻|鼻用|鼻.{0,2}喷雾', loc_):
                    continue
                if R.get('route') == 'eye' and not re.search(r'滴眼|眼用|眼膏|眼凝胶|眼部', loc_):
                    continue
                if (sid, c['sh'], c['row'], c['t']) in rst_seen:
                    continue
                if R.get('route') == 'systemic' and (_TOPICAL.search(loc_) or _NONDERMAL.search(loc_)):
                    continue                          # 「全身用糖皮质激素」不含外用/吸入/鼻用/眼用（与禁用药同口径）
                if R.get('route') == 'topical' and (not _TOPICAL.search(loc_) or _NONDERMAL.search(loc_)):
                    continue
                why = ''
                if is_full_date(c['s']) and c['s'] > s['fd'] and (not end_tx or c['s'] <= end_tx):
                    why = f"首剂（{s['fd']}）后才开始使用"
                elif R.get('noStop', True) and is_full_date(c['e']) and s['fd'] <= c['e'] < (end_tx or '9999') and not c['ong']:
                    why = f"治疗期内（{c['e']}）停用"           # 方案允许增减（如激素）时不核查停用
                elif n and is_full_date(c['s']) and c['s'] <= s['fd'] and (days(s['fd'], c['s']) or 0) < n:
                    why = f"首剂前仅使用 {days(s['fd'], c['s'])} 天（方案要求稳定使用 ≥{n} 天）"
                if why:
                    rst_seen.add((sid, c['sh'], c['row'], c['t']))
                    hits[re.sub(r'[（(].*$', '', c['t']).strip()].append((c, why))
            for t_, xs in hits.items():
                c, why = sorted(xs, key=lambda x: x[0]['s'] or x[0]['e'] or '')[0]
                more = f"（另有 {len(xs) - 1} 条同药记录）" if len(xs) > 1 else ''
                rs_ = c['why'] if c['why'] and not re.fullmatch(r'[√✓✔☑是1]', str(c['why']).strip()) else ''
                add_other(C, sid, R.get('cat', '限用药核对'), R.get('pr', 3),
                          f"限用药「{c['t']}」（{c['s'] or '?'}~{'持续' if c['ong'] else c['e'] or '?'}）{why}{more}" + (f"；用药原因：{rs_}" if rs_ else ''),
                          None, c['s'] or c['e'], c['sh'], c['row'], c['t'], ctx=[f"方案：{R.get('cond')}"] if R.get('cond') else [],
                          rule={'ask': '请核实该用药是否符合方案对限用药的要求（稳定剂量、研究期间不新加/不停用）；如不符合，请评估是否记录方案偏离。'},
                          bkey=f"{t_}|rst", wb=c.get('wb') or '')


_TRANSF_RX = re.compile(r'输血|红细胞(悬液|输注)|悬浮红|洗涤红|去白(细胞)?红|浓缩红|全血输注|血小板输注|血浆输注|transfusion', re.I)
_HGB_RX = re.compile(r'(?<!化)(?<!胞)(?<!离)(?<!尿)血红蛋白(?!尿)|(?<![A-Za-z])HG?B(?![A-Za-z0-9])|Hemoglobin', re.I)   # 只认血红蛋白（不含比容）


def transfusion_checks(C):
    """审阅者 2026-11-09（MY008 血液科复审：S01004 Hb 14 天内 50→96 g/L 无输血记录、S02006 输血日期缺失）：
    研究采集了输血记录（操作/合并用药里至少一条输血）时才启用——①给药后 Hb 从输血区间（<80 g/L）起，相邻两次 ≤21 天上升
    ≥20 g/L（2 g/dL），期间（前次前 3 天至本次）无输血记录 → 请核实是否漏记输血；②研究期间输血记录缺少完整日期 → 请补充。
    非血液学研究（无输血记录）不触发。"""
    tr = defaultdict(list)
    for p_ in list(getattr(C, 'proc', []) or []) + [dict(c, term=c.get('t'), date=c.get('s')) for v in C.cm_by.values() for c in v]:
        if _TRANSF_RX.search(str(p_.get('term') or '')):
            tr[p_.get('sid')].append(p_)
    if not tr:
        return
    for sid, recs in tr.items():
        if sid not in C.pop:
            continue
        icf = str(C.subj.get(sid, {}).get('icf') or C.subj.get(sid, {}).get('fd') or '')
        for p_ in recs:
            d0 = str(p_.get('date') or p_.get('start') or '')
            pre_study = bool(re.match(r'\d{4}-\d{2}', d0)) and is_full_date(icf) and d0[:7] < icf[:7]
            if not is_full_date(d0) and p_.get('sheet') and not pre_study:      # 知情前的既往输血史写部分日期属常态，不追
                add_other(C, sid, '输血记录核对', 3, f"研究期间输血记录「{p_.get('term')}」缺少完整日期（{d0 or '未填'}）——输血日期影响输血相关终点与 Hb 解读",
                          None, d0, p_.get('sheet'), p_.get('row'), p_.get('term') or '', bkey=f"trdate|{p_.get('row')}", wb=p_.get('wb') or '',
                          rule={'ask': '请补充完整输血日期。'})
    for (sid, mid), rows in C.F.items():
        if sid not in C.pop or not _HGB_RX.search(C.metric.get(mid, {}).get('label') or mid):
            continue
        pts = [r for r in rows if r.get('post') and isinstance(r.get('value'), (int, float)) and is_full_date(r.get('date'))]
        dates = [str(p_.get('date') or p_.get('start') or '') for p_ in tr.get(sid, [])]
        for a, b_ in zip(pts, pts[1:]):
            gap = days(b_['date'], a['date'])
            u = str(b_.get('unit') or '').lower()
            step, trig = (2.0, 8.0) if 'dl' in u else (20.0, 80.0)
            # 只从输血区间（前值 <80 g/L）起算：疗效显著的研究（补体抑制剂）Hb 快速回升本是药效，不作输血线索
            if gap is None or gap > 21 or gap < 0 or a['value'] >= trig or (b_['value'] - a['value']) < step:
                continue
            lo_ = (dt.date.fromisoformat(a['date']) - dt.timedelta(days=3)).isoformat()
            if any(is_full_date(d) and lo_ <= d <= b_['date'] for d in dates):
                continue
            add_other(C, sid, '输血记录核对', 3,
                      f"{C.metric.get(mid, {}).get('label') or '血红蛋白'} {dshow(a['date'])} {fmt(a['value'])} → {dshow(b_['date'])} {fmt(b_['value'])} {b_.get('unit') or ''}"
                      f"（{gap} 天上升 {fmt(b_['value'] - a['value'])}），期间未见输血记录",
                      b_.get('visit'), b_['date'], b_.get('sheet'), b_.get('row'), b_.get('test') or '', bkey=f"hbjump|{b_['date']}", wb=b_.get('wb') or '',
                      rule={'ask': '请核实是否有输血未录入；如无输血，请说明 Hb 回升原因。'})


def cm_checks(C):
    rescue = (C.A.get('pd') or {}).get('rescue') or {}
    rescue_re = re.compile(r'补救|rescue', re.I)
    cm_seen = set()
    for P in C.A.get('prohibited', []):  # {"name","re","window":[daysBeforeFd, 'ld'|daysAfterFd], "pr"}
        pre = re.compile(P['re'], re.I)
        systemic_only = P.get('route') == 'systemic' or (not P.get('route') and bool(_SYSTEMIC.search(P.get('name') or '')) and not _TOPICAL.search(P.get('name') or ''))
        topical_only = P.get('route') == 'topical'          # 「外用皮质类固醇」：只认外用/局部给药的记录（静脉激素归系统性条目）
        local_only = P.get('route') == 'local'              # 「吸入性/鼻用」：只认吸入、鼻喷等（SAR 外用乳膏、口服不算）
        exc_re = re.compile(P['exceptRe'], re.I) if P.get('exceptRe') else None
        exc_mh = re.compile(P['exceptMH'], re.I) if P.get('exceptMH') else None
        nonsed_ok = _nonsedating_exempt(P)                  # F1：「镇静抗组胺（允许非镇静）」条款不扫二代非镇静
        # 适应症限定：方案疾病名（forDisease）＋研究疾病同义词（diseaseTerms，如 特应性皮炎/AD）＋「研究疾病」
        for_dz = re.compile('|'.join([P['forDisease']] + [re.escape(str(t)) for t in (C.A.get('diseaseTerms') or []) if t] + ['研究疾病', '原发病']),
                            re.I) if P.get('forDisease') else None
        for sid in sorted(C.pop):
            s = C.subj[sid]
            if not s['fd']:
                continue
            w0 = P.get('daysBefore', 0)
            # 禁用期锚点（方案「随机至研究结束」→ fromAnchor=rand, toAnchor=eos）；缺省沿用首剂至末次给药
            a0 = {'rand': s.get('rand_d'), 'icf': s.get('icf'), 'fd': s['fd']}.get(P.get('fromAnchor') or 'fd') or s['fd']
            a0 = a0 if is_full_date(a0) else s['fd']
            a = (dt.date.fromisoformat(a0) - dt.timedelta(days=w0)).isoformat()
            e0 = {'eos': s.get('eos_d') or s.get('lo'), 'eot': s.get('eot_d') or s.get('ld'), 'ld': s.get('ld')}.get(P.get('toAnchor') or 'ld')
            b = (dt.date.fromisoformat(e0) + dt.timedelta(days=P.get('daysAfter', 0))).isoformat() if is_full_date(e0) else (s.get('eos_d') or s['lo'])
            for c in C.cm_by[sid]:
                if pre.search(c['t']) and overlap(c, a, b):
                    # 「系统治疗」类禁用药不匹配外用/局部给药；按方案作为补救治疗使用的由补救规则（CM-02/03）核查，不按禁用药报
                    if systemic_only and (_TOPICAL.search(c.get('rt') or '') or _TOPICAL.search(c['t']) or _NONDERMAL.search(f"{c.get('rt') or ''} {c['t']}")):
                        continue                 # 眼用/吸入/鼻用等局部给药不是系统性用药
                    unk_end = not c['ong'] and not is_full_date(c['e']) and is_full_date(c['s']) and c['s'] < (s.get('icf') or s['fd'])
                    if local_only and not _NONDERMAL.search(f"{c.get('rt') or ''} {c['t']}"):
                        continue
                    if nonsed_ok and _NONSEDATING_AH.search(c['t']):
                        continue                 # F1：允许非镇静的镇静抗组胺条款不命中二代非镇静子类
                    if exc_re and exc_re.search(c['t']):
                        continue                 # 方案点名除外（SAR 背景药糠酸莫米松）
                    if for_dz and (c.get('why') or '').strip() and not for_dz.search(c['why']):
                        continue                 # 「治疗AD的口服中药」：写明用于其他疾病（月经不调）的不判（审阅者 2026-11-09）
                    if exc_mh and (exc_mh.search(c.get('why') or '') or any(exc_mh.search(m.get('t') or '') for m in C.mh_by.get(sid, []))):
                        continue                 # 以病史为条件的允许（SAR：合并哮喘者允许稳定剂量吸入激素；用药原因写「哮喘」同样算）
                    if topical_only and _not_topical_cm(c):
                        continue                 # F2：「外用」＝皮肤局部；吸入/雾化/鼻用/眼用/注射不属于（RUX 方案明确允许吸入型糖皮质激素）
                    if rescue and rescue_re.search(c.get('why') or '') and (not is_full_date(c['s']) or c['s'] >= s['fd']):
                        continue
                    if (sid, c['sh'], c['row'], c['t']) in cm_seen:
                        continue                 # 同一条用药落在两个重叠类别（白三烯受体拮抗剂 / 白三烯调节剂）只报一次
                    cm_seen.add((sid, c['sh'], c['row'], c['t']))
                    if unk_end:
                        uk = getattr(C, '_unkend_seen', None) or set()
                        C._unkend_seen = uk
                        if (sid, c['sh'], c['row']) in uk:
                            continue
                        uk.add((sid, c['sh'], c['row']))
                        # 入组前开始、停药日期未知且未标持续（RUX：2014–2019 年的既往外用激素，结束「uk」）：不能据此判与治疗期重叠——
                        # 只请核实停药日期（低优先级、不进偏离）
                        add_other(C, sid, '用药日期核对', 2,
                                  f"合并用药「{c['t']}」（{c['s']}~停药日期未知）属于{_cls_txt(P, c)}，未标持续，请核实停药日期是否在首剂（{s['fd']}）之前",
                                  None, c['s'], c['sh'], c['row'], c['t'], bkey=f"{c['t']}|{c['s']}|unkend", wb=c.get('wb') or '')
                        continue
                    # 审阅者 2026-11-09（RUX：禁用期按方案「研究期间」到研究结束，文案却一律写「与治疗期重叠」，末次给药后随访期用药读起来像误报）
                    win = (f"{({'rand': '随机', 'icf': '知情', 'fd': '首剂'}).get(P.get('fromAnchor') or 'fd')}{('前 %d 天' % w0) if w0 else ''}至"
                           f"{({'eos': '研究结束', 'eot': '治疗结束', 'ld': '末次给药'}).get(P.get('toAnchor') or 'ld')}")
                    fu = is_full_date(c['s']) and is_full_date(s.get('ld')) and c['s'] > s['ld']
                    add_other(C, sid, P.get('cat', '禁限用药核对'), P.get('pr', 4),
                              f"合并用药「{c['t']}」（{c['s'] or '?'}~{'持续' if c['ong'] else c['e'] or '?'}）属于{_cls_txt(P, c)}，在方案禁用期（{win}）内使用"
                              f"{'（末次给药 ' + s['ld'] + ' 之后的随访期）' if fu else ''}；用药原因：{c['why'] or '—'}",
                              None, c['s'], c['sh'], c['row'], c['t'], ctx=[P.get('note', '')] if P.get('note') else [],
                              bkey=f"{c['t']}|{c['s']}", wb=c.get('wb') or '')
        for pr_ in [x for x in getattr(C, 'proc', []) if x.get('sid') in C.pop]:    # 禁用的治疗/操作（造血干细胞移植等）也核对操作记录
            s = C.subj[pr_['sid']]
            d0 = str(pr_.get('date') or pr_.get('start') or '')
            if s['fd'] and pre.search(str(pr_.get('term') or '')) and (not is_full_date(d0) or d0 >= s['fd']):
                add_other(C, pr_['sid'], P.get('cat', '禁限用药核对'), P.get('pr', 4),
                          f"治疗/操作「{pr_.get('term')}」（{d0 or '?'}）属于方案禁止的{P['name']}", None, d0, pr_.get('sheet'), pr_.get('row'),
                          pr_.get('term') or '', bkey=f"{pr_.get('term')}|{d0}", wb=pr_.get('wb') or '')
    restricted_checks(C)
    for W in C.A.get('washout', []):  # {"name","re","days","ref":"icf"|"fd"}
        pre = re.compile(W['re'], re.I)
        # V6 医学审阅（RUX P0007：他克莫司软膏为外用，适用 1 周洗脱，却按系统性免疫抑制剂 4 周报重要偏离）：与禁用药同口径——
        # 「系统性」洗脱条目不匹配外用/局部给药（外用另有条目时由外用条目核查）
        sys_only = bool(re.search(r'系统|全身|口服|中(草)?药|中成药', W.get('name') or '')) and not _TOPICAL.search(W.get('name') or '')
        # F2：「外用疗法」类洗脱只认皮肤局部给药——吸入/雾化复方（含激素成员字面）不入外用类
        top_only = W.get('route') == 'topical' or (not W.get('route') and bool(_TOPICAL.search(W.get('name') or ''))
                                                   and not _SYSTEMIC.search(W.get('name') or ''))
        exc_re = re.compile(W['exceptRe'], re.I) if W.get('exceptRe') else None
        nonsed_ok = _nonsedating_exempt(W)                  # F1：洗脱条款同样认「允许非镇静」
        for sid in sorted(C.pop):
            s = C.subj[sid]
            ref = s.get({'rand': 'rand_d'}.get(W.get('ref', 'fd'), W.get('ref', 'fd')))
            if not is_full_date(ref):
                continue
            a = (dt.date.fromisoformat(ref) - dt.timedelta(days=W['days'])).isoformat()
            for c in C.cm_by[sid]:
                if sys_only and (_TOPICAL.search(c.get('rt') or '') or _TOPICAL.search(c['t'])):
                    continue
                if top_only and _not_topical_cm(c):
                    continue                 # F2：外用＝皮肤局部；吸入/鼻用/眼用/注射复方不按外用洗脱核查
                if nonsed_ok and _NONSEDATING_AH.search(c['t']):
                    continue                 # F1：允许非镇静的镇静抗组胺洗脱条款不命中二代非镇静子类
                if exc_re and exc_re.search(c['t']):
                    continue                 # F1：洗脱条目点名除外（编译层从条款原文生成，与禁用药同口径）
                if pre.search(c['t']) and not c['ong'] and not is_full_date(c['e']) and is_full_date(c['s']) and c['s'] <= ref:
                    # 审阅者 2026-11-09（RUX：9 例 36 条既往外用激素/TCI 停药日期「uk」，洗脱是否满足无从判断却无任何提示）
                    uk = getattr(C, '_unkend_seen', None) or set()
                    C._unkend_seen = uk
                    if (sid, c['sh'], c['row']) not in uk:
                        uk.add((sid, c['sh'], c['row']))
                        add_other(C, sid, '用药日期核对', 2,
                                  f"合并用药「{c['t']}」（{c['s']}~停药日期未知）属于{_cls_txt(W, c)}，方案要求{ {'icf': '知情', 'rand': '随机'}.get(W.get('ref'), '首剂')}前停用 {W['days']} 天，请核实停药日期",
                                  None, c['s'], c['sh'], c['row'], c['t'], bkey=f"{c['t']}|{c['s']}|unkend", wb=c.get('wb') or '')
                    continue
                # 末次用药距参照日恰好 N 天＝洗脱期已满（D001 间隔正好 14/28 天曾判「不足」）：只算严格晚于窗口起点的
                if pre.search(c['t']) and (c['ong'] or (is_full_date(c['e']) and c['e'] > a)) and (not is_full_date(c['s']) or c['s'] <= ref):
                    add_other(C, sid, W.get('cat', '入排洗脱用药核对'), W.get('pr', 3),
                              f"合并用药「{c['t']}」末次 {c['e'] or '持续'}，距{ {'icf': '知情', 'rand': '随机'}.get(W.get('ref'), '首剂')}（{ref}）不足 {W['days']} 天洗脱期（{_cls_txt(W, c)}）",
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
        if not ru and re.search(r'%|百分|比率|比例', str(r.get('test') or '')) and '%' not in eu:
            return None                                  # V6（MY008 S06003）：单位空、检查名写明百分比 → 不与绝对计数阈值比
        if ru and eu != ru:
            pe, pr_ = re.fullmatch(r'×?10\^(\d+)/l', eu), re.fullmatch(r'×?10\^(\d+)/l', ru)
            f = 10 ** (int(pe.group(1)) - int(pr_.group(1))) if pe and pr_ else UNIT_FAC.get((eu, ru))
            if f is None:
                return None                              # 单位不可换算 → 不判
            v = v / f
    return {'val': v, 'uln': (r['value'] / r['hi']) if r.get('value') is not None and r.get('hi') else None,
            'lln': (r['value'] / r['lo']) if r.get('value') is not None and r.get('lo') else None}.get(on)


def _elig_bad(E, x):
    if E.get('re'):
        # H3①②（第 3 轮 SAR）：定性判定统一先看 result_state——删失界/低于检测限/阴性类写法不是阳性
        # （旧编译规则的「\+」会吃科学计数 E+、「检出」会吃「低于检出限」）；真阳性写法再走正则
        st = result_state(x)
        if st is not None and st[0] in ('below', 'above', 'neg'):
            return False                 # 删失写法的阳/阴取决于试剂判定方向（竞争法 HBcAb 高值＝阴性）——须按本行参考范围判，见交接挂账
        return bool(re.search(E['re'], str(x or ''), re.I)) and not re.search(r'阴性|negative|未检出', str(x or ''), re.I)
    return cmp(E['op'], x, E['v'])


_COND_QUAL = re.compile(r'^(?:有临床意义或)?(?:未控制的|未经控制的|有临床意义的|活动性|未经治疗的)?')


def _premise_treated(C, sid, E):
    """「经治疗后仍超标方构成排除」前提（用户 2026-11-04 裁定 9＝A：有病史/合并用药数据时自动判）：
    violated＝有对应合并用药（经治疗仍超标）；undetermined＝只有病史没有用药记录；premise_unmet＝两者都没有。
    条件名取标准原文里超标指标所属的疾病（「未控制的高血压（定义为经治疗收缩压>150…）」→ 高血压）。"""
    txt = str(E.get('text') or '')
    m = re.search(r'(?:未控制的|未经控制的)([\u4e00-\u9fff]{2,8}?)(?:[（(]|，|,|；|定义)', txt)
    cond = m.group(1) if m else None
    if not cond:
        return 'undetermined'
    cm = [c for c in (getattr(C, 'cm_by', None) or {}).get(sid, []) if cond in (c.get('why') or '') or cond in (c.get('t') or '')]
    if cm:
        return 'violated'
    mh = [x for x in (getattr(C, 'mh_by', None) or {}).get(sid, []) if cond in (x.get('t') or '')]
    return 'undetermined' if mh else 'premise_unmet'


def _exc_state(C, sid, E, r):
    """方案例外条款（「青少年碱性磷酸酶>1.5×ULN 且具有临床意义者」）逐条判：只认提到本指标的分句；分句带人群限定
    （青少年/儿童/<18 岁 / 成人）而受试者不在该人群 → 例外不适用；在该人群且要求「具有临床意义」→ 研究者判 NCS 时例外成立。
    返回 exception_met / violated / undetermined；没有适用分句 → None（照常判）。"""
    exc = str(E.get('exc') or '')
    if not exc:
        return None
    lab = C.metric.get(r.get('mid') or '', {}).get('label') or r.get('test') or ''
    names = [n for n in re.split(r'[（()）\s/]+', lab) if len(n) >= 2]
    for cl in re.split(r'[；;。]', exc):
        if not cl.strip() or not any(n in cl for n in names) or re.search(r'胆红素', cl) and not re.search(r'胆红素', lab):
            continue
        age = C.subj[sid].get('age')
        try:
            age = float(age)
        except (TypeError, ValueError):
            age = None
        kid = re.search(r'青少年|儿童|未成年|<\s*18|18\s*岁以下', cl)
        adult = re.search(r'成人|成年|≥\s*18', cl)
        if kid or adult:
            if age is None:
                return 'undetermined'
            if (kid and age >= 18) or (adult and age < 18):
                return 'violated'           # 例外只对另一人群
        if re.search(r'具有临床意义|有临床意义', cl):
            return 'exception_met' if r.get('clin') in (0, 1) else 'violated' if r.get('clin') == 2 else 'undetermined'
        return 'undetermined'
    return None


def _ref_positive(r):
    """定量报告的定性指标（乙肝表面抗原 >250 IU/mL、竞争法核心抗体 COI）：按本行参考范围判阳性——结果落在正常范围外＝阳性。
    正常范围只给上限（<0.05）→ 高于上限阳性；只给下限（竞争法「>1.0」）→ 低于下限阳性。无参考范围 → None（不猜）。
    审阅者 2026-11-09：删失符号本身不决定阴阳（竞争法高值＝阴性），曾两头出错（判阴漏报 / 判阳误报）。"""
    st = result_state(r.get('raw'))
    if st is None or st[0] not in ('value', 'below', 'above') or st[1] is None:
        return None
    v, lo, hi = st[1], r.get('lo'), r.get('hi')
    if isinstance(hi, (int, float)):
        if st[0] == 'below':
            return False if v <= hi else None
        return v > hi
    if isinstance(lo, (int, float)):
        if st[0] == 'above':
            return False if v >= lo else None
        return v < lo
    return None


def _elig_bad_r(E, r):
    """V6：删失/定性写法（「<50」被 to_num 读成 50）按结果状态判；其余沿用数值比较。"""
    if E.get('re'):
        rp = _ref_positive(r)
        if rp is not None:
            return rp and not re.search(r'阴性|negative|未检出', str(r.get('raw') or ''), re.I)
    if not E.get('re') and E.get('on') in (None, 'val'):
        st = result_state(r.get('raw'))
        if st is not None and st[0] in ('below', 'above', 'neg'):
            return state_meets(E['op'], E.get('v'), st) is True
    return _elig_bad(E, _elig_x(E, r))


_UNS_NAME_RX = re.compile(r'计划外|unsched|^USV$', re.I)


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
        # F01②（RUX 深审）：无日期的计划外访视行不入「入组前」池——EDC 页完成标志清单（0/1）无日期，
        # 套用筛选期入选标准产生全量误报；有日期的计划外复查（筛选期复查常记计划外）照旧参与。
        if d is None and _UNS_NAME_RX.search(str(v or '')):
            continue
        out.append(r)
    return out


_OP_REL = {'>': '超过', '>=': '达到', '≥': '达到', '<': '低于', '<=': '不高于', '≤': '不高于'}


_OP_CN = {'>': '＞', '>=': '≥', '<': '＜', '<=': '≤', '==': '＝'}


def _elig_subj_txt(E, v):
    """受试者字段类入排（年龄等）：「年龄 16，不符合入选标准：年龄18~50周岁」。"""
    t = str(E.get('text') or '')
    t = t if re.match(r'^(入选|排除)标准', t) else f"入排标准“{t}”"
    return f"{E.get('label', E['field'])} {fmt(v) if isinstance(v, float) else v}，不符合{t}"


def _elig_rel(E, r):
    return _OP_REL.get(str(E.get('op') or ''), '不符合')


def _elig_thr(E, r):
    """命中的子条件阈值写法：1.5×ULN / 90 g/L。"""
    on, v = E.get('on', 'val'), E.get('v')
    if v is None:
        return '范围'
    if on in ('uln', 'lln'):
        return f"{fmt(v)}×{on.upper()}"
    return f"{fmt(v)} {E.get('unit') or r.get('unit') or ''}".strip()


def _elig_label(eid):
    """入排标准编号的可读写法：IE-I4 → 入选标准 4、IE-E7 → 排除标准 7；其他写法原样返回。"""
    m = re.match(r'^IE-([IE])(\d+)$', str(eid or ''))
    return f"{'入选' if m.group(1) == 'I' else '排除'}标准 {m.group(2)}" if m else str(eid or '')


def _elig_cite(E, kind):
    """质疑里引用入排标准：Word 自动编号不在文本里，抽取编号常与方案不符（RUX「排除标准24」实为第 5 条）——
    引用改为「类别＋原文开头」，编号只在原文自带编号时保留（审阅者 2026-11-09）。"""
    t = re.sub(r'\s+', '', str(E.get('text') or ''))
    lab = _elig_label(E.get('id')).replace(' ', '') if E.get('id') else kind
    head = re.match(r'^[（(]?[0-9]{1,2}(\.[0-9]{1,2})*[)）.、]', t)
    if not t:
        return lab
    kind_ = '入选标准' if str(E.get('id') or '').startswith('IE-I') or kind == '入选标准' else '排除标准' if str(E.get('id') or '').startswith('IE-E') or kind == '排除标准' else kind
    short = t[:26] + ('…' if len(t) > 26 else '')
    return f"{kind_}「{short}」" if not head else f"{kind_} {head.group(0).strip('（()）.、')}「{short}」"


def _near_val(C, sid, mre, r):
    """同受试者、指标匹配 mre、距判定记录最近日期（同表单优先）的数值结果行；无 → None。
    用户 2026-11-01 裁定：复合条件/例外的伴随值按「同 sheet/同受试者/最近日期」取。"""
    d0 = r.get('date')
    if not is_full_date(d0):
        return None
    cand = [x for (s2, mid), rows in C.F.items() if s2 == sid and mre.search(mid) for x in rows
            if (isinstance(x.get('value'), (int, float)) or result_state(x.get('raw')) is not None) and is_full_date(x.get('date'))]
    if not cand:
        return None
    same = [x for x in cand if x.get('sheet') == r.get('sheet')]
    return min(same or cand, key=lambda x: (abs(days(x['date'], d0) or 0), x['date']))


_NEG_TXT = r'[^，。；,;]{0,6}?(?:[（(]\s*[-－]\s*[)）]|阴性|未检出|低于(?:检测)?下限|[<＜])'


def _gate_ok(C, sid, G, r):
    """复合排除的伴随条件（E14 型 gate）：None=伴随指标不可得；True/False=是否满足。
    V6（用户审阅 RUX 第 12 条）：伴随结果统一按 result_state 判（「<50」「＜检测下限」「阴性」「<1*10^3」都是低于阈值）；
    结构化结果取不到时，读触发行的说明列（「NCS，乙肝DNA（－）」）里对伴随指标的否定写法——只用于判「不满足」。"""
    x = _near_val(C, sid, re.compile(G['metric']), r)
    if x is None:
        txt = ' '.join(str(r.get(k) or '') for k in ('desc', 'reason_text', 'reason_raw'))
        kw = G.get('kw') or G['metric']
        return False if txt and re.search(f'(?:{kw}){_NEG_TXT}', txt, re.I) else None
    if G.get('re'):
        rp = _ref_positive(x)                 # 有参考范围时按范围判阴阳（与入排主条件同口径）
        if rp is not None:
            return rp
        t = str(x.get('raw') or '')
        # H3①②：伴随阳性同样先看 result_state（删失界/低于检测限不是阳性；旧编译正则的 \+ 会吃 E+）
        st = result_state(t)
        if st is not None and st[0] in ('below', 'above', 'neg'):
            return False                 # 删失写法的阳/阴取决于试剂判定方向（竞争法 HBcAb 高值＝阴性）——须按本行参考范围判，见交接挂账
        return bool(re.search(G['re'], t, re.I)) and not re.search(r'阴性|negative|未检出', t, re.I)
    st = result_state(x.get('raw')) if not isinstance(x.get('value'), (int, float)) or re.match(r'\s*[<＜>＞≤≥]', str(x.get('raw') or '')) \
        else ('value', float(x['value']))
    return state_meets(G.get('op', '>='), G.get('v'), st)


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
            bad = [r for r in pool if _elig_bad_r(E, r)]
            r = pool[-1] if pick == 'last' else pool[0] if pick == 'first' else (bad[0] if bad else None)
            if r is None or r not in bad:
                continue
            lab = C.metric[mid]['label']
            ctx = [_elig_label(E['id'])] if E.get('id') else []      # 「IE-E7」→「排除标准 7」：不露内部标准编号
            others = [x for x in bad if x is not r]
            if others:
                ctx.append('另有不符测量：' + '、'.join(f"{x.get('visit')} {x.get('raw')}" for x in others[:4]))
            if E.get('exc'):
                ctx.append('例外条款：' + str(E['exc']))
            if len(pool) > 1:
                ctx.append(f"判定值＝{'入组前末次测量' if pick == 'last' else '首次筛选测量' if pick == 'first' else '任一测量'}（共 {len(pool)} 次）")
            # V6 措辞排查：只引用命中的子条件（此前整段标准原文塞进引号再截断，ALP 信号引用了「AST或ALT…」）；原文进判读背景
            det = f"入组前 {lab} {r.get('raw')} {r.get('unit') or ''}（{r.get('visit')} {dshow(r.get('date'))}）".replace(' （', '（')
            crit = _elig_cite(E, kind)
            hit = f"，为{crit}规定的排除情形" if E.get('re') else f"，{_elig_rel(E, r)}{crit}规定的{_elig_thr(E, r)}"
            if E.get('text'):
                ctx.append('标准原文：' + str(E['text'])[:160])
            bkey = f"{lab}|{r.get('visit') or ''}|{r.get('date') or ''}"   # qkey 沿用旧口径（类别＋判定记录），存量 MMQ 身份不漂移
            # ---- 用户 2026-11-01 三裁定：复合前提/例外不机械判排除 ----
            # V6（用户审阅 RUX 第 9 条）：信号带判定状态 _elig（violated/exception_met/premise_unmet/undetermined），
            # 方案偏离只对 violated 生成、undetermined 列「待判定」，例外已满足/前提不成立只作提示
            if E.get('gate'):                                        # ③「X 阳性且 Y…」（F9①：Y 数值侧同样带 gate）：Y 未满足不发；不可得降为请核实
                g = _gate_ok(C, sid, E['gate'], r)
                if g is False:
                    continue
                if g is None:
                    gl = E['gate'].get('label') or '伴随条件'
                    gv = (f"{gl} 阳性" if E['gate'].get('re') else
                          f"{gl} {_OP_CN.get(E['gate'].get('op', ''), E['gate'].get('op', ''))}{fmt(E['gate']['v'])} {E['gate'].get('unit') or ''}".rstrip()
                          if E['gate'].get('v') is not None else gl)
                    o = add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4),
                                  f"{det}，{crit}要求同时 {gv} 才排除，未见同期 {gl} 结果，请核实",
                                  r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
                    o['_elig'] = 'undetermined'
                    continue
            if E.get('bili'):                                        # ②「直接胆红素<35% 可接受」：占比达标降为提示
                dv = _near_val(C, sid, re.compile(E['bili']['metric']), r)
                tv = r.get('value')
                if dv is not None and tv:
                    pct = dv['value'] / tv * 100
                    lim = E['bili'].get('pct', 35)
                    if pct < lim:
                        o = add_other(C, sid, E.get('cat', '入排标准核对'), 2,
                                      f"{det}{hit}，但直接胆红素占比 {pct:.0f}%＜{lim:.0f}%，孤立性胆红素升高按方案可接受",
                                      r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
                        o['_elig'] = 'exception_met'
                        continue
            if E.get('premise') == 'treated':                        # ①「经治疗仍超标才排除」：按病史/合并用药判前提
                st = _premise_treated(C, sid, E)
                if st == 'premise_unmet':
                    o = add_other(C, sid, E.get('cat', '入排标准核对'), 2,
                                  f"{det}{hit}，但未见相关病史或治疗用药记录，“经治疗后仍超标”的排除前提不成立，按方案不构成排除，供核实",
                                  r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
                    o['_elig'] = 'premise_unmet'
                    continue
                if st == 'undetermined':
                    o = add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4),
                                  f"{det}{hit}，方案要求经治疗后仍超标方构成排除，受试者有相关病史但未见治疗用药记录，请提供该受试者的相关治疗情况",
                                  r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
                    o['_elig'] = 'undetermined'
                    continue
            ex = _exc_state(C, sid, E, r)
            if ex == 'exception_met':
                o = add_other(C, sid, E.get('cat', '入排标准核对'), 2,
                              f"{det}{hit}，但符合方案例外情形，按方案不构成排除",
                              r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
                o['_elig'] = 'exception_met'
                continue
            o = add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4),
                          f"{det}{hit}，但已随机/给药",
                          r.get('visit'), r.get('date'), r['sheet'], r['row'], lab, r.get('clin'), ctx=ctx, bkey=bkey, wb=r.get('wb') or '')
            o['_elig'] = 'undetermined' if ex == 'undetermined' else 'violated'
            if ex == 'violated':
                ctx.append('方案例外条款不适用于该受试者')
    for E in C.A.get('eligibilitySubject', []):  # {"field":"age","op","v","text"}
        for sid in sorted(C.pop):
            v = C.subj[sid].get(E['field'])
            if isinstance(v, str):
                # R2-2（D002 仿真定罪连带）：受试者字段可能是文本型数值（'47'）——按数值参与比较；
                # 不可数值化的文本（空串/区间写法）不比较（cmp 对 None 已跳过，此处同口径不猜）。
                try:
                    v = float(v.strip())
                except ValueError:
                    continue
            if cmp(E['op'], v, E['v']):
                add_other(C, sid, E.get('cat', '入排标准核对'), E.get('pr', 4), _elig_subj_txt(E, v), None, C.subj[sid].get('icf'),
                          C.subj[sid].get('sheet', ''), C.subj[sid].get('row'), bkey=f"{E['field']}|{E.get('id') or ''}")


def visit_window_checks(C):
    W = C.A.get('visitWindows', {})  # {"W2": [15, 3, 3]}  target study day, minus, plus
    # V6（CRA 审阅：D002 别名对齐后的 17 条超窗没进信号层）：数据访视代码经 visit_alias 唯一对应到方案键时按方案窗判
    alias, _um = monitor_v5.visit_alias(C, W) if W else ({}, [])
    inv = defaultdict(list)
    for k_, c_ in alias.items():
        inv[c_].append(k_)
    for v in C.visits:
        sid = v['sid']
        # V6 运营审阅（RUX W28 60 条与 EDC 判定不一致）：访视页有 EDC 系统生成的计划最早/最晚日期时以它为准（中心实际执行的窗口），
        # 方案推算只在没有系统窗时使用
        lo_s, hi_s = v.get('win_lo'), v.get('win_hi')
        if sid in C.pop and is_full_date(lo_s) and is_full_date(hi_s) and is_full_date(v.get('date')):
            if not (str(lo_s)[:10] <= str(v['date'])[:10] <= str(hi_s)[:10]):
                add_other(C, sid, '访视超窗核对', 2, f"{v['visit']} 实际 {v['date']}，EDC 计划窗 {str(lo_s)[:10]} ~ {str(hi_s)[:10]}",
                          v['visit'], v['date'], v['sheet'], v['row'], wb=v.get('wb') or '')
            continue
        key = v.get('visit') if v.get('visit') in W else (inv[v.get('visit')][0] if len(inv.get(v.get('visit')) or []) == 1 else None)
        if sid not in C.pop or key is None:
            continue
        spec = W[key]
        if isinstance(spec, dict):
            t, mi, pl, anc = spec.get('target'), spec.get('minus', 0), spec.get('plus', 0), spec.get('anchor', 'fd')
        else:
            (t, mi, pl), anc = spec[:3], 'fd'
        s = C.subj[sid]
        if anc == 'fd':
            sd, lab = study_day(v.get('date'), s['fd']), 'D'
        else:  # days since anchor (rand / icf / another visit's actual date), anchor = day 0
            ad = s.get({'rand': 'rand_d', 'icf': 'icf', 'ld': 'ld'}.get(anc, '')) if anc in ('rand', 'icf', 'ld') else next((x.get('date') for x in C.visits if x['sid'] == sid and x.get('visit') == anc), None)
            sd, lab = (days(v.get('date'), ad) if is_full_date(ad) and is_full_date(v.get('date')) else None), \
                {'ld': '末次给药后第', 'rand': '随机后第', 'icf': '知情后第'}.get(anc, f'{anc} 后第')
        if sd is not None and (sd < t - mi or sd > t + pl):
            if lab == 'D':
                at, win = f"D{sd}", f"D{t}{'−%d' % mi}/+{pl}"
            else:   # V6 审阅：「末次给药后第12」缺「天」
                at, win = f"{lab} {sd} 天", f"{lab} {t} 天（−{mi}/+{pl} 天）"
            add_other(C, sid, '访视超窗核对', 2, f"{v['visit']} 实际 {v['date']}（{at}），方案窗 {win}", v['visit'], v['date'], v['sheet'], v['row'], wb=v.get('wb') or '')


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
            o['ctx'].append('方案偏离记录表未见对应记录')


def disease_not_ae(C) -> bool:
    """方案是否规定「研究疾病相关异常/进展除非较预期更严重否则不作为 AE」（analysis.diseaseNotAEClause，PM5＋确定性正则双通道）。"""
    return bool(C.A.get('diseaseNotAEClause'))


# ----------------------------------------------------------------------------- queries
QT = {  # 默认 query 措辞：写给 CRC，一句话＝异常点＋冲突点＋建议（不写日期：query 已定位到 listing 行）。可用 analysis.queryTemplates 覆盖
    'CSX': ('CS未关联AE/MH', '{btxt}{visit}访视{test}{move}{raw}{unit}（参考范围 {rng}{gtxt}），判为有临床意义，但未关联AE或病史，',
            '请核实是否需记录AE，或补充病史并关联。'),
    'MH': ('CS仅关联病史·加重核对', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判为有临床意义，仅关联病史“{mh}”，未见对应AE，',
           '请评估是否为给药后加重、需记录AE。'),
    'CSX_DIS': ('CS未关联·研究疾病表现较基线加重', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判为有临床意义，该指标异常可见于{bg}，但较基线明显加重且未记录AE，',
                '请评估是否需记录AE。'),
    'CSX_AE': ('CS未关联·同期疑似AE', '{visit}访视{test}为{raw}{unit}，判为有临床意义，同期已记录{cand}，但该检验未关联，',
               '请确认是否为同一事件；如是，请在检验页关联该AE（表单无关联字段时在说明中注明AE编号）。'),   # V6 医学审阅：本 CRF 无独立关联字段时「完成关联」无从操作
    'NCS2': ('NCS但达分级≥2级', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级），判为无临床意义，',
             '请核实临床意义判定。'),
    'NA': ('超出参考范围·未评价临床意义', '{visit}访视{test}为{raw}{unit}，超出参考范围（{rng}），未评价临床意义，',
           '请补充临床意义评价。'),
    'DISW': ('CS归因研究疾病·给药后加重', '{btxt}{visit}访视{test}{move}{raw}{unit}（{wf}），判为有临床意义并归因研究疾病，但未记录研究疾病加重AE，',
             '请评估是否需记录AE。'),
    'G2NF': ('达分级≥2级·表单无临床意义评价', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级），该表单没有临床意义评价，',
             '请评估是否需记录AE。'),
    'NA2': ('未评价临床意义·达分级≥2级', '{btxt}{visit}访视{test}{move}{raw}{unit}（{gl} {grade}级），未评价临床意义，',
            '请补充临床意义评价，并评估是否需记录AE。'),
}


def ext_match(C, sid, sheet, text):
    """Check overlap with external (CRO) queries for the same subject/form → (status, cro text)."""
    if not C.extq:
        return '未提供 CRO 质疑', ''            # SAR 运营审阅：没有外部质疑数据时不能写「未见同问」（像是比对过）
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


def aesi_caliber(C):
    """H5（第 3 轮 SAR）：AESI 双口径——已标记（EDC 勾选）与符合定义待核实（方案定义命中但未勾选）。
    总览/安全页两页同源取数（此前总览用已标数、安全概况用勾选∪定义命中并集，两种口径无标签）。"""
    aes = [x for x in C.aes if x['sid'] in C.pop and x.get('te') and not x.get('dup')]   # 与总览/概况同口径（TEAE、去重复导出）
    return {'marked': sum(1 for x in aes if x.get('aesi')),
            'defHit': sum(1 for x in aes if x.get('_aesi_def') and not x.get('aesi'))}


def build_queries(C):
    C.sheet_groups = defaultdict(set)
    for f in C.findings:
        if f.get('group'):
            C.sheet_groups[f['sheet']].add(f['group'])
    T = dict(QT)
    if disease_not_ae(C):
        # 用户 2026-11-09：方案规定「研究疾病相关异常除非较预期更严重否则不作为 AE」时，问法改为「是否较预期病情更严重」，照常发
        T['DISW'] = (QT['DISW'][0], QT['DISW'][1].replace('但未记录研究疾病加重AE，', '较基线加重，'),
                     '方案规定研究疾病相关异常除非较预期病情更严重否则不作为AE：请评估该异常是否较预期病情更严重；如是，请记录为AE并关联。')
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
            same['merged'] = same.get('merged', 1) + 1     # H6（第 3 轮 SAR）：合并不静默——条目携带并入信号数（页头/清单脚注）
            src['q'].append(same['id'])
            return same
        st, cro = ext_match(C, sid, sh, fact + ask)
        if st == '同主题已查重' and C.A.get('skipDuplicates', False):
            return None
        ev = [[ev_sh(C, e[0], src_wb)] + list(e[1:]) for e in ev]
        q = {'id': f'Q{len(Q) + 1:03d}', 'sid': sid, 'site': C.subj[sid]['site'], 'cat': cat, 'sh': sh_id, 'row': row, 'v': v or '', 'd': d or '', 'test': test or '',
             'text': fact + ask, 'parts': [[fact, 0], [ask, 1]], 'ev': ev, 'cro': st, 'flags': [], '_cro': cro,
             'croText': (cro or '')[:200], 'qkey': qkey,      # H10：CRO 原文以可见键输出（_cro 下划线键被 KZ 输出层剥离，工作簿 CRO 查重列全空）
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
        bg = next((b for rx, b in ind_bg if rx.search(g.get('mid') or '') and ext_rules.bg_applies(b, g.get('mid') or '', g.get('grp') or '')), None) if g['risk'] == 'CSX' else None
        if g['risk'] == 'CSX' and cand:  # a plausible AE exists but the finding is not linked → ask to link instead of "report AE"
            cat, ft, ask = T.get('CSX_AE', T['CSX'])
            ft = ft.replace('{cand}', '、'.join(re.sub(r'可能对应，但检验页未关联', '', c).replace('同期 ', '') for c in cand))
        elif bg:                         # mm4：研究疾病表现且较基线进一步加重（未加重的已归 DIS，不发 query）
            cat, ft, ask = T.get('CSX_DIS', T['CSX'])
            ft = ft.replace('{bg}', re.sub(r'[↑↓]|（医学常识）$', '', bg.split('：')[0]))
        P = [p for p in g['pts'] if (g['risk'] in ('NCS2', 'NA2', 'G2NF') and (p[4] or 0) >= 2) or (g['risk'] not in ('NCS2', 'NA2', 'G2NF') and p[5] == 2)] or g['pts']
        if cand and g.get('_aecov'):
            P = sorted(P, key=lambda p: p[1] not in g['_aecov'])   # 有同期 AE 时，质疑写 AE 期间内的那次异常
        wf_pt = None
        if g['risk'] in ('MH', 'DISW') or bg:          # 加重类：以较基线变化最大的那次为主，数值与「较基线」必须是同一个点（D001 QC：曾写成 0.68 较 0.60 升高 63%）
            P = sorted(P, key=lambda x: -abs(x[6] or 0))
            # V6 医学审阅（RUX Q007：W24 1.69 写成「较基线 1.51 加重 1→2 级」，2 级其实来自 W4 1.44）：
            # 加重说明必须就所写的这一个点重新计算，并优先写真正满足「加重」的那次（等级高者优先，其次变化幅度）
            # V6 第 2 轮 MY008（G2①）：重算与判定同一输入——基线取该点自己的 base（本表基线/每行 base），
            # 疾病归因类同样带 disease/ddir；不得拿组内首行基线拼「0→3 级」（抽屉全程表显示基线已 3 级）
            rows_ = C.F[(g['sid'], g['mid'])]
            b0 = next((r.get('base') for r in rows_ if r.get('base')), None)
            dis_ = g['risk'] == 'DISW' or bool(bg)
            ddir_ = ext_rules.disease_dir(C, g.get('mid') or '', g.get('grp') or '') if dis_ else None
            sc = []
            for x in P:
                fx = next((r for r in rows_ if r['sheet'] == x[7] and r['row'] == x[8]), None)
                w_ = fx and ((fx['base'] if 'base' in fx else b0)) and (worse_vs_base(fx, (fx['base'] if 'base' in fx else b0), float(C.cfg['thresholds'].get('base', 0.3)),
                                                                     disease=dis_, pre=ext_rules.pre_values(rows_), ddir=ddir_)
                                                            or (ext_rules.qual_worse(fx, (fx['base'] if 'base' in fx else b0)) if not dis_ else None))
                if w_:
                    sc.append(((fx.get('grade') or 0), abs(x[6] or 0), x, w_))
            if sc:
                sc.sort(key=lambda t: (-t[0], -t[1]))
                P = [sc[0][2]] + [x for x in P if x is not sc[0][2]]
                wf_pt = sc[0][3]
        p = P[0]
        f = next((r for r in C.F[(g['sid'], g['mid'])] if r['sheet'] == p[7] and r['row'] == p[8]), {})
        mh = '、'.join(l[1] for l in g['rel'] if l[0] == 'MH')
        lo_, hi_ = f.get('lo'), f.get('hi')
        rng = f"{fmt(lo_)}–{fmt(hi_)}" if lo_ is not None and hi_ is not None else f"≤{fmt(hi_)}" if hi_ is not None else f"≥{fmt(lo_)}" if lo_ is not None else '未提供'
        b_ = g['base'] or []
        bv, cv = _num(b_[1] if b_ else None), _num(p[2])
        btxt = f"基线{b_[1]}{p[3]}{'（正常）' if len(b_) > 3 and b_[3] == 0 else ''}，" if b_ and b_[1] not in (None, '') else ''
        move = move_word(bv, cv, f.get('lo'), f.get('hi'))   # F06：低于下限不写「升高至」（偏离方向与基线方向分离表述）
        wf = next((m.group(1) for c in g['ctx'] for m in [re.search(r'较基线(?:进一步)?加重[（：]([^）；]+)', c)] if m), '较基线明显加重')
        if wf_pt:
            wf = wf_pt
        elif p[6] is not None and re.search(r'较基线(升高|降低)', wf):   # 百分比按所写的这一次计算
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
        card = {'问题': {'CSX': '判为有临床意义但未关联AE或病史', 'MH': '判为有临床意义且只关联病史，较基线加重，未见对应AE', 'NCS2': '数值达CTCAE≥2级但研究者判为无临床意义',
                       'NA': '超出参考范围但未评价临床意义', 'NA2': '数值达CTCAE≥2级但未评价临床意义', 'G2NF': '数值达CTCAE≥2级，该表单没有临床意义评价',
                       'DISW': '研究者归因研究疾病，但较基线明显加重且未记录研究疾病加重AE'}.get(g['risk'], cat),
                '指标': g['test'], '访视': p[0], '数值': f"{p[2]}{p[3] or ''}", '参考范围': rng}
        if cand:
            # 「判为有临床意义」只对 CS 类成立；NCS≥2级/未评价≥2级有同期 AE 时问的是判定/评价本身（第二轮医学审阅措辞排查）
            card['问题'] = {'NCS2': '数值达CTCAE≥2级但判为无临床意义，同期已记录可能对应的AE',
                          'NA2': '数值达CTCAE≥2级但未评价临床意义，同期已记录可能对应的AE'}.get(g['risk'], '判为有临床意义但检验未关联，同期已有可能对应的AE')
            card['同期已记录AE'] = '、'.join(re.sub(r'可能对应，但检验页未关联', '', c).replace('同期 ', '') for c in cand)
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
    # 同一检验格命中多档阈值（ALT>3×ULN 复查/中断 与 >5×ULN 停药）：只就最高档发一条质疑，不再「另：」整句重复
    top_thr = {}
    for o in C.others:
        if o['cat'] == '阈值规则核对' and o['_rule'].get('metric'):
            k = (o['sid'], o['sh'], o['row'])
            if k not in top_thr or thr_level(o['_rule']) > thr_level(top_thr[k]['_rule']):
                top_thr[k] = o
    for o in C.others:
        R = o['_rule']
        if o['pr'] < C.A.get('queryMinPr', 3) or R.get('query') is False:
            continue
        if o['cat'] == '阈值规则核对' and R.get('metric') and top_thr.get((o['sid'], o['sh'], o['row'])) is not o:
            continue
        thr = threshold_ask(R, o) if not R.get('ask') else ''
        ask = R.get('ask') or thr or C.A.get('askByCat', {}).get(o['cat']) or '请核实并更正，或提供医学说明。'
        n0 = len(Q)
        qq = new_q(o['sid'], o['cat'], o['sh'], o['row'], o['v'], o['d'], o['test'], o['sum'].rstrip('。；，') + '。' if thr else o['sum'].rstrip('。；，') + '，',
                   ask, [[o['sh'], o['row'], o['v'], o['test']]], o, o.get('qkey', ''),
                   {'问题': thr_label(R) if thr else o['cat'], '事实': o['sum'].rstrip('。；，'), **({'指标': o['test']} if o.get('test') else {}),
                    **({'访视': o['v']} if o.get('v') else {}), '建议动作': ask})
        if thr and qq and len(Q) > n0:
            qq['fixed'] = True                           # 用户 2026-11-02：新建的阈值类质疑措辞固定用程序模板；并入既有质疑时不锁对方的模型措辞
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
        if hit and hit.get('h') == q['card_h'] and hit.get('text') and not q.get('fixed'):
            q['text'], q['parts'], q['writer'] = hit['text'], [[hit['text'], 0]], 'model'
    for q in Q:                                          # 事实卡自检：基线/数值/较基线百分比必须互相吻合（模型照卡写，错数字会直接进句子）
        for c in q['_cards']:
            m = re.search(r'(升高|降低)\s*(\d+)%', str(c.get('较基线') or ''))
            b, v = _num(re.sub(r'[^\d.\-].*$', '', str(c.get('基线') or ''))), _num(re.sub(r'[^\d.\-].*$', '', str(c.get('数值') or '')))
            if m and b and v is not None and abs(abs((v - b) / b * 100) - int(m.group(2))) > 1.5:
                print(f"WARN  事实卡数值不一致 {q['id']}：基线 {c.get('基线')} 数值 {c.get('数值')} {c.get('较基线')}", file=sys.stderr)
    for q in Q:                                          # 输出端统一中文引号（事实卡不动，卡片哈希与已写句子复用不受影响）
        q['text'] = cs_plain(cn_quotes(q['text']))
        q['parts'] = [[cs_plain(cn_quotes(x[0]))] + list(x[1:]) for x in q['parts']]
    C.queries = Q
    C.qcommon = dict(common)
    C.qMerged = sum(q.get('merged', 1) - 1 for q in Q)     # H6：被同格合并掉的信号条数（总信号数＝len(Q)+qMerged）


# ----------------------------------------------------------------------------- consistency / centers
def build_cons(C):
    """判定一致性数据面（用户 2026-10-30 终版：同中心换芯＋同受试者版新增；旧 ±5%「相近即双向报」废止）。
    可比对＝同受试者（scope=subject）或同中心跨受试者（scope=center）×同指标/单位/参考范围×同向异常
    （都超参考范围同向；一升一降不可比）×同给药阶段（给药前不与给药后比）。两维度（ext_rules 同一出处）：
    a. 判定维度（kind=judg，方向性）：更差者（偏离参考边界更远，相对偏离度、无最小差阈值）判 NCS 而更轻者判 CS → 发；
       数值相等而判定不同 → 发（无更差方可定向）；更差者判 CS → 不发。
    b. 归因维度（kind=att，无方向不排序）：两条均 CS 且归因不同（AE/MH/研究疾病/未关联 任一不同）→ 发。
    同受试者维度的不一致已由 ext_rules.clin_consistency 发质疑——质疑面已覆盖的标「已有问题覆盖」；
    跨例比较只作提示，不以多数判定作为医学标准。"""
    C.cons = []
    qrows = {(q['sh'], q['row']) for q in C.queries}

    def side(r):
        att = ext_rules.att_of(r) if r['clin'] == 2 else ''
        return [r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', '异常有临床意义' if r['clin'] == 2 else '异常无临床意义',
                f"{fmt(r.get('lo'))}–{fmt(r.get('hi'))}", r['sheet'], r['row'], f'归因{att}' if att else '']

    def emit(scope, site, sid, mid, kind, d, a, b, equal):
        lab = C.metric[mid]['label']
        va = f"{a.get('visit')}访视 {a.get('raw')}{a.get('unit') or ''}"
        vb = f"{b.get('visit')}访视 {b.get('raw')}{b.get('unit') or ''}"
        st = '已有问题覆盖' if (a['sheet'], a['row']) in qrows or (b['sheet'], b['row']) in qrows else '需核实'
        if kind == 'att':
            diff = (f"{'同一受试者' if scope == 'subject' else '同中心'}{lab}相似结果均判为有临床意义但归因不同："
                    f"{va} {ext_rules.att_cn(a)}，{vb} {ext_rules.att_cn(b)}")
            why = ('同一受试者' if scope == 'subject' else '同一中心') + \
                  '对相似结果给出不同医学解释（CS 归因 AE/病史/研究疾病/未关联 不一致）；先核对两次异常的症状/处置与关联记录差异，再决定是否质疑。'
        elif equal:
            diff = f"{'同一受试者' if scope == 'subject' else '同中心'}{lab}数值相同（{va} 与 {vb}），一次判为有临床意义、一次判为无临床意义"
            why = ('相同数值的判定不同即不一致（无更差方可定向）；' if scope == 'subject' else
                   '同一中心对相同数值分别判 CS 与 NCS——判定尺度不一致；') + \
                  '先核对症状/复查/处置差异，再决定是否质疑。跨例比较只作提示，不以多数判定作为医学标准。'
        else:
            diff = (f"{'同一受试者' if scope == 'subject' else '同中心'}{lab}同向异常：{vb}（离正常范围更远，"
                    f"偏离 {ext_rules.cons_dev(b, d):.0%}）判为无临床意义，{va}（偏离 {ext_rules.cons_dev(a, d):.0%}）却判为有临床意义")
            why = ('同一受试者' if scope == 'subject' else '同一中心') + \
                  '对同向异常的判定尺度不一致：偏离参考边界更远者判 NCS、较轻者判 CS；先核对症状/复查/处置差异，再决定是否质疑。跨例比较只作提示，不以多数判定作为医学标准。'
        o = {'id': f'C{len(C.cons) + 1:03d}', 'scope': scope, 'kind': kind, 'site': site, 'test': lab,
             'a': a['sid'], 'b': b['sid'], 'diff': diff, 'st': st, 'why': why, 'av': side(a), 'bv': side(b)}
        if scope == 'subject':
            o['sid'] = sid
        C.cons.append(o)

    groups = defaultdict(list)          # (scope键, mid, unit, lo, hi, 方向, 给药阶段) → 行；同向异常同阶段才可比
    for (sid, mid), rows in C.F.items():
        if sid not in C.pop:
            continue
        for r in rows:
            if r.get('value') is not None and r.get('clin') in (1, 2) and C.isAgg(r.get('visit')):
                d = 'H' if r.get('hi') is not None and r['value'] > r['hi'] else 'L' if r.get('lo') is not None and r['value'] < r['lo'] else ''
                if d:
                    k = (mid, r.get('unit'), r.get('lo'), r.get('hi'), d, bool(r.get('post')))
                    groups[('center', C.subj[sid]['site']) + k].append(r)
                    groups[('subject', sid) + k].append(r)
    for (scope, skey, mid, unit, lo, hi, d, post), rs in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        cs = [r for r in rs if r['clin'] == 2]
        ncs = [r for r in rs if r['clin'] == 1]
        for a, b, equal in ext_rules.cons_witnesses(cs, ncs, d, cross_subject=scope == 'center', min_diff=float(C.A.get('consMinDiff', 0.05))):
            emit(scope, skey if scope == 'center' else C.subj[skey]['site'], skey, mid, 'judg', d, a, b, equal)
        for a, b in ext_rules.cons_attribution(cs, cross_subject=scope == 'center'):
            emit(scope, skey if scope == 'center' else C.subj[skey]['site'], skey, mid, 'att', d, a, b, False)


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
    rdates = defaultdict(lambda: defaultdict(set))                    # 项目 -> sid -> {记录日期}（「可沿用首剂前 N 天结果」用）
    names, sheet2grp = {}, {}
    for f in C.findings:
        if f['sid'] not in C.pop or not f.get('visit'):
            continue
        # mm4：按「组」合并同一评估项目的多个 sheet（如按中心拆分的 血常规_1/_2），否则拆表的另一半会被误判为缺失
        sh = f.get('group') or f['sheet']
        names.setdefault(sh, f.get('group') or sh)
        sheet2grp.setdefault(f['sheet'], sh)
        k = 1 if not_done(f.get('done')) else 0
        recs[sh][f['visit']][k].add(f['sid'])
        if not k and is_full_date(f.get('date')):
            rdates[sh][f['sid']].add(f['date'])
    for e in C.efficacy:
        if e['sid'] in C.pop and e.get('visit'):
            names.setdefault(e['sheet'], e.get('metric') or e['sheet'])
            recs[e['sheet']][e['visit']][0].add(e['sid'])
            if is_full_date(e.get('date')):
                rdates[e['sheet']][e['sid']].add(e['date'])
    spec = C.A.get('soa')  # [{"name","sheet","visits":[..],"cond":bool}]
    if not spec:
        spec = []
        for sh, by in recs.items():
            exp = [v for v in cols if len(by[v][0] | by[v][1]) >= 0.5 * len(visited[v])]
            spec.append({'name': names[sh], 'sheet': sh, 'visits': exp, 'cond': False})
    d1 = ((getattr(C, 'cfg', None) or {}).get('visits') or {}).get('d1') or 'D1'
    first = [v for v in cols if v != d1][:1] if d1 in cols and cols.index(d1) > 0 else []
    pre_vis = {d1, *first} | {v for v in cols if re.search(r'^(SCR|筛选|V0)', str(v), re.I)}
    out, guard = [], []
    for sp in spec:
        # F-F（CRUX-01）：alt＝替代量表（成人版/儿童版等同一家族的互换表单）。带 alt 时：
        # ① 应做人群＝做过本表或任一替代表（任一访视有记录）的受试者——从未做过家族任一表者不在该表人群
        #（成人不做儿童量表，反之亦然），不再全人群判缺失；② 某访视由本表或替代表任一完成即算完成。
        alts = [a for a in (sp.get('alt') or []) if a]
        members = [sp['sheet']] + alts
        bys = [recs.get(m) or recs.get(sheet2grp.get(m), {}) for m in members]   # 方案 SoA 可写 sheet 名或组名
        pop = set()
        if alts:
            for b in bys:
                for d0, n0 in b.values():
                    pop |= d0 | n0
        ap = sp.get('applies') or {}
        elig = _soa_applicable(C, ap, bys)                # V6（用户审阅 RUX 第 7 条）：逐人适用（性别/育龄代理/年龄段）
        judge = ap.get('judge', True)                     # 必要时/部分受试者/条件无法解析 → 只展示不判缺失
        reuse = ap.get('reuse_days')
        dts = defaultdict(set)
        for m in members:
            for sid0, ds in (rdates.get(m) or rdates.get(sheet2grp.get(m), {})).items():
                dts[sid0] |= ds
        cells = {}
        for v in cols:
            n = visited[v] & elig if elig is not None else visited[v]
            if alts:
                n = n & pop
            done = set().union(*[((b.get(v) or (set(), set()))[0] & n) for b in bys]) if bys else set()
            no = set().union(*[((b.get(v) or (set(), set()))[1] & n) for b in bys]) - done if bys else set()
            if v in sp['visits']:
                miss = n - done - no
                if reuse and v in pre_vis:                # 「可接受首次给药前 N 天内结果」：该期间有记录即算完成
                    miss = {x for x in miss if not _reused(C, x, dts.get(x), reuse)}
                if not judge:
                    miss = set()
                cells[v] = [len(n), len(done), len(no), len(miss), sorted(miss), sorted(no), 0, 0]
                if judge and len(n) >= 10 and len(miss) >= 0.3 * len(n):
                    g = _soa_guard_cell(C, sp['name'], v, n, miss)
                    if g is not None:
                        cells[v][7] = 1           # 合理性守卫：大面积缺失＝对应/适用条件疑似有误 → 不逐人判
                        guard.append(g)
            elif done:
                cells[v] = [len(n), len(done), 0, 0, [], [], 1, 0]
        out.append({'name': sp['name'], 'sheet': sp['sheet'], 'exp': sp['visits'], 'cond': sp.get('cond', False),
                    **({'alt': alts} if alts else {}), **({'judge': False} if not judge else {}),
                    **({'applies': ap} if ap else {}), 'cells': cells})
    if spec and any(s.get('cond') for s in spec):
        C.S.setdefault('study', {}).setdefault('soaCond', [s['name'] for s in spec if s.get('cond')])
    C.soa, C.soacols, C.soaGuard = out, cols, guard


def _soa_applicable(C, ap, bys):
    """适用人群（None＝全部到访者）。sex：F/M；wocbp：女性且任一访视做过本项目（无育龄字段时的代理，用户裁定 8＝A）；
    age：[下限, 上限)（岁，基线年龄）。"""
    if not ap or not any(k in ap for k in ('sex', 'wocbp', 'age')):
        return None
    did = set()
    for b in bys:
        for d0, n0 in b.values():
            did |= d0 | n0
    out = set()
    for sid in C.pop:
        s = C.subj[sid]
        sx = str(s.get('sex') or '')
        female = bool(re.search(r'女|^F', sx, re.I))
        male = bool(re.search(r'男|^M', sx, re.I))
        if ap.get('sex') == 'F' and not female:
            continue
        if ap.get('sex') == 'M' and not male:
            continue
        if ap.get('wocbp') and not (female and sid in did):
            continue
        rng = ap.get('age')
        if rng:
            try:
                a = float(s.get('age'))
            except (TypeError, ValueError):
                a = None
            if a is None or (rng[0] is not None and a < rng[0]) or (rng[1] is not None and a >= rng[1]):
                continue
        out.add(sid)
    return out


def _reused(C, sid, dates, n):
    fd = C.subj[sid].get('fd')
    if not dates or not is_full_date(fd):
        return False
    return any(days(fd, d) is not None and 0 <= days(fd, d) <= n for d in dates)   # 同日（0 天）有效


def _soa_guard_cell(C, name, vis, n, miss):
    """SoA 合理性守卫（用户裁定 7＝A）：某评估在某访视 ≥30% 受试者缺失（且 ≥10 人）——几乎总是对应关系或适用条件有误
    （男性被要求妊娠试验、成人被要求儿童量表、首剂前 N 天结果可沿用未抽出），不逐人发质疑，改为一条系统提示并附分布；
    缺失集中于单一中心（≥80%）时不压——那可能是该中心真实的系统性漏做，照常判。返回提示 dict 或 None（不压）。"""
    by_site = Counter(C.subj[x]['site'] for x in miss)
    if by_site and by_site.most_common(1)[0][1] >= 0.8 * len(miss) and len(by_site) < len({C.subj[x]['site'] for x in n}):
        return None
    sex = Counter(('女' if re.search(r'女|^F', str(C.subj[x].get('sex') or ''), re.I) else '男' if re.search(r'男|^M', str(C.subj[x].get('sex') or ''), re.I) else '未知') for x in miss)
    def band(x):
        try:
            a = float(C.subj[x].get('age'))
        except (TypeError, ValueError):
            return '未知'
        return '<18 岁' if a < 18 else '18–64 岁' if a < 65 else '≥65 岁'
    ages = Counter(band(x) for x in miss)
    hint = []
    n_sex = {('女' if re.search(r'女|^F', str(C.subj[x].get('sex') or ''), re.I) else '男') for x in n}
    n_age = {band(x) for x in n}
    for lab, cnt, pool in (('性别', sex, n_sex), ('年龄', ages, n_age)):
        k, v = cnt.most_common(1)[0]
        if len(pool) > 1 and v >= 0.9 * len(miss) and k != '未知':      # 应做人群本身只有一种（已按性别限定）时不提示
            hint.append(f"缺失者 {v / len(miss):.0%} 为{k}，可能缺少按{lab}的适用条件")
    return {'name': name, 'visit': vis, 'n': len(n), 'miss': len(miss), 'pct': round(len(miss) / len(n), 3),
            'sex': dict(sex), 'age': dict(ages), 'site': dict(by_site.most_common(5)), 'hint': '；'.join(hint)}


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
                    add_other(C, sid, '有效性数据量级异常', 3, f"{v}（{dshow(r.get('date'))}）{t_}，相差 10 倍以上", v, r.get('date'), r['sheet'], r['row'],
                              m['label'], rule={'id': 'EFF-MAG', 'ask': '疑似单位或录入错误，请核对源文件并更正；如数值无误，请说明原因。'},
                              bkey=f"{m['src']}|mag|{v}", wb=r.get('wb') or '')


def build_eff(C):
    M = C.A.get('efficacy', [])
    data = {}
    by = defaultdict(list)  # (sid, src) -> [(visit,date,value,raw)]
    for e in C.efficacy:
        val = e.get('value') if e.get('value') not in (None, '') else e.get('raw')   # V6：「3=中度」类编码量表（IGA）数值在 raw
        by[(e['sid'], 'eff:' + str(e.get('metric')))].append((e.get('visit'), e.get('date'), eff_num(val), val))
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
               'notes': C.A.get('effNotes') or [],   # mm4：未生成/未对上的原因（宿主按方案终点×listing 生成）
               # F-J（IMP-06）：配置了的有效性终点指标在 listing 中完全无记录 → 显式行动项（不静默空页）
               'missing': [{'id': m['id'], 'label': m.get('label') or m['id'], 'src': m.get('src'),
                            'note': '终点配置了该指标，但 listing 中无任何对应记录——请核查量表表是否已映射/指标名是否一致',
                            'cands': eff_sheet_candidates(m.get('label') or m['id'], (getattr(C, 'src', None) or {}).get('unmapped') or [])}
                           for m in M if not any(m['id'] in (d.get('v') or {}) for d in data.values())]}


_EFF_GENERIC_BIGRAM = {'评分', '量表', '情况', '检查', '指数', '总分', '变化', '基线', '记录', '评估', '程度', '问卷', '日记', '结果'}


def eff_sheet_candidates(label, sheets, k=3):
    """V6 B4（审阅者 2026-11-02，D002 主要终点 MBL 在「(51)月经周期及出血情况」表、未被映射 → 有效性页空）：
    终点无数据时，在未映射的表名里找可能的来源（括注缩写命中，或去掉通用词后有共同的中文双字）。只作提示，不自动绑定。"""
    lab = str(label or '')
    abbr = [x.upper() for x in re.findall(r'[A-Za-z][A-Za-z0-9\-]{1,9}', lab)]
    base = re.sub(r'[（(].*?[)）]', '', lab)
    bg = {base[i:i + 2] for i in range(len(base) - 1)} - _EFF_GENERIC_BIGRAM
    bg = {b for b in bg if re.fullmatch(r'[\u4e00-\u9fff]{2}', b)}
    out = []
    for s in sheets:
        nm = re.sub(r'^[（(]\s*\d+\s*[)）]|^\d+[.、\-]', '', str(s)).strip()
        sc = 2 * any(a in nm.upper() for a in abbr) + sum(b in nm for b in bg)
        if sc:
            out.append((sc, s))
    return [s for _, s in sorted(out, key=lambda x: -x[0])[:k]]


# ----------------------------------------------------------------------------- subject files
def build_subject_files(C, out):
    doms = {'lab': 'labs', 'vs': 'vs', 'ecg': 'ecg'}
    vis_by = defaultdict(list)
    for v in C.visits:
        vis_by[v['sid']].append([v.get('visit'), v.get('visit'), v.get('date'), v['row'], v.get('sheet') or '', v.get('wb') or ''])   # V6：时间线事件下钻原始行
    ex_by = defaultdict(list)
    for e in C.exposure:
        ex_by[e['sid']].append({'s': e.get('start'), 'e': e.get('end'), 'n': e.get('dose') or '', 'pause': e.get('pause') or '', 'row': e['row'], 'v': e.get('visit') or '',
                                'sh': e.get('sheet') or '', 'wb': e.get('wb') or ''})
    pr_by = defaultdict(lambda: {'sur': [], 'pr': []})
    for p in C.proc:
        k = 'sur' if re.search('手术', str(p.get('kind') or '手术')) else 'pr'
        d_ = p.get('date') or p.get('start') or ''          # MY008：输血记录日期在 start，受试者页 153 条输血日期全空
        pr_by[p['sid']][k].append({'t': p.get('term') or '', 'd': d_, 's': d_, 'why': p.get('why') or p.get('indication') or ''})
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
                # mm4 钻取行扩位（drill_fields）：既有 14 位不动，尾部追加 [归因码, 原文说明, 关联摘要]
                d[doms[dom]][C.metric[mid]['label']] = [[r.get('date'), r.get('visit'), r.get('value'), r.get('raw'), r.get('unit') or '', r.get('lo'), r.get('hi'),
                                                        r.get('clin'), r.get('desc') or '', r['sheet'], r['row'], r.get('tpt') or '', r.get('time') or '', 1 if r.get('isb') else 0]
                                                        + drill_fields(C, sid, r)
                                                        # mm5 全程数据面板：[17] 分级、[18] 较基线 %、[19] 疑似录入错误说明（既有 0–16 位不动）
                                                        + [r.get('grade'), None if r.get('pct') is None else round(r['pct'], 1), r.get('_entry') or '']
                                                        for r in rows]
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
        mic = [r for r in getattr(C, 'micro', []) if r['sid'] == sid]     # 第三轮：微生物培养/药敏分域呈现（判读型，不进异常核查）
        if mic:
            mic.sort(key=lambda r: (r.get('date') or '', 0 if r.get('_micro') == 'C' else 1, r.get('row') or 0))
            d['ext'].append({'title': '微生物培养与药敏', 'note': '判读型结果（培养/涂片/药敏 MIC），单独呈现，不进入检验异常与质疑链',
                             'cols': ['项目', '访视', '日期', '结果', '判读/说明'], 'numFrom': 99,
                             'rows': [[[r.get('test') or '', 'org'] if r.get('_micro') == 'C' else (r.get('test') or ''), [r.get('visit'), 'blu'], r.get('date'),
                                       '' if r.get('raw') is None else str(r.get('raw')), r.get('desc') or ''] for r in mic], 'chart': None})
        Path(out, 's').mkdir(parents=True, exist_ok=True)
        Path(out, 's', f'{sid}.js').write_text('KZ_SUB(' + json.dumps(d, ensure_ascii=False, separators=(',', ':'), default=str) + ');', encoding='utf-8')


# ----------------------------------------------------------------------------- evidence rows (KZX.ex)
def build_ex(C):
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
        wb = wbs.get(path) or open_workbook_lenient(path)[0]   # mm5：带伤 EDC 导出（截断 dimension）也读全
        wbs[path] = wb
        ws = wb[meta['sheet']]   # PR-8: sheets keyed by unique id — open by plain sheet name
        labels = None
        for i, r in enumerate(ws.iter_rows(values_only=True), start=1):
            if i == meta['label_row']:
                labels = [str(x) if x is not None else f'col{j + 1}' for j, x in enumerate(r)]
            if i in rs and labels:
                # H1（第 3 轮 SAR，R10）：摘录出口与原始数据层同一隐私列判定（common.pii_column）——
                # 「姓名缩写/研究者姓名/电话…」列不进质疑/偏离抽屉的原文摘录（≤14 字段全显时同样过滤）
                r = redact_row(labels, list(r))                    # 自由文本里夹带的本行姓名缩写同样打码
                rows[(sh, i)] = {labels[j]: ('' if v is None else str(v)[:120]) for j, v in enumerate(r)
                                 if j < len(labels) and v not in (None, '') and not pii_column(labels[j])}
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
    ('M01', 'CS 未关联 AE/MH', '检验/生命体征/心电图页结果、参考范围、临床意义、关联字段', '给药后新发或加重的异常被判 CS，但关联字段为空 → 漏报 AE 风险最高', '漏报 AE', '发 query：请评估记录 AE 或补充病史并关联'),
    ('M02', 'CS 仅关联病史', '同上 + 病史页', '仅关联 MH 时比较给药后与规定基线的等级/数值，加重者提示应记 AE', '以病史替代 AE', '较基线加重者发 query；同级者仅提示'),
    ('M03', 'NCS 但 {GL} ≥2 级', '数值 + {GL} 数值条目', '数值达 ≥2 级仍判 NCS 时请研究者说明依据；无 {GL} 数值条目者不自动分级', '判定尺度偏松', '发 query：说明依据或更正'),
    ('M04', '基线定义', '方案规定的基线（指定访视、首次给药或随机前最近一次、或多次均值，可按指标分别规定）', '规定基线缺失时按规则回退（默认首剂前最近有效值）并注明「替代基线」', '基线错配', '仅提示，不单独发 query'),
    ('M05', '同中心判定一致性', '同中心同指标同单位/范围/同向异常/同给药阶段', '偏离更远（或数值相等）者判 NCS、更轻者判 CS 时提示判定尺度不一致；更差者判 CS 不提示；不以多数判定作为标准', '中心判定偏差', '先核对症状/复查/处置差异'),
    ('M06', '方案阈值专项', '方案规定的 AE/AESI/停药/回看阈值', '方案原文定义的 AE/AESI/停药/回看阈值逐点比对，并核对是否有对应 AE/AESI 记录', '漏报 AESI', '按方案要求的严重程度决定是否发质疑'),
    ('M07', 'AE 记录质量', 'AE 页', '给药前事件相关性、AE 等级与关联检验 {GL} 等级对照、合并用药标记、AESI 标记、同术语重叠记录', '记录不一致', '发 query 或提示'),
    ('M08', '禁限用药 / 洗脱期', '合并用药页 + 方案禁用药清单', '按方案禁用药名单匹配药名＋用药时段与首剂前窗口/治疗期重叠；洗脱期按知情/首剂回推', '方案偏离', '发 query 并核对方案偏离记录表'),
    ('M09', '入排关键数值', '筛选期检验/人口学', '筛选期数值符合排除标准但已随机/给药', '入组不合格', '优先核实'),
    ('M10', '访视窗', '访视页日期', '研究日 = 访视日 − 首剂日 + 1；按方案窗判断', '超窗', '提示 / 核对 PD'),
    ('M11', '中心偏离', '中心层面汇总（不含计划外/提前退出访视）', '漏斗图 ±2SE 需关注 / ±3SE 明显偏离；n<2 不判', '中心系统性偏差', '中心层面沟通，不对个例发 query'),
    ('M13', '多指标组合规则', '方案规定的组合判定标准（如 Hy’s law）', '方案定义的组合标准（如 Hy’s law：ALT/AST ≥3×ULN 且 TBIL ≥2×ULN 且 ALP <2×ULN）同日/窗口内同时满足', '漏报 AESI/SAE', '按方案要求的严重程度决定是否发质疑'),
    ('M14', 'AE/SAE/AESI 报告时限', 'AE 页（获知/报告日期）＋方案规定的报告时限', '报告日期 − 获知（或发生）日期 > 方案时限', '报告延迟', '发 query 或提示'),
    ('M12', '有效性数据合理性', '方案终点对应的 EDC 量表/检验/检查', '按方案终点定义派生（绝对值/较基线/百分比），离群与关键访视缺失提示；盲态下不分组', '终点数据质量', '核对源数据/测量'),
    ('M15', '方案偏离·执行层面', '知情同意记录、访视日期、SoA 各评估、给药记录（日期/时刻/途径/空腹/数量）、样本采集时刻', '按方案访视窗与锚点、SoA、给药与样本时点、知情时序逐受试者推断潜在偏离（程序早于知情、未再次知情、访视超窗/缺失、评估缺失/未做、访视内顺序、给药前样本晚于给药、依从性、停药后给药）；关键访视/关键评估升级为重要；方案未给出参数或数据表缺字段的检查不执行，并写明原因', '方案执行偏离', '发 query 或交 CRA 核实；属实录入方案偏离记录表'),
    ('M16', '方案偏离·科学层面', '入排数值、合并用药与禁用清单、检验异常与 AE/病史、停药阈值、SAE 报告日期', '入排不符仍入组（入组前末次有效值）、洗脱期不足、禁用药、潜在 AE 漏记（CS 未关联 AE 或病史加重）、SAE/AESI 报告超时、达停药标准未停药；重要＝可能显著影响受试者权益/安全/福祉或关键数据可靠性（ICH E3 Q&A R1；E6(R3)）', '入组/用药/安全报告偏离', '按分级：重要优先核实；潜在 AE 漏记先发 query'),
    ('M17', '已记录 PD 比对与分级', '方案偏离记录表（类别、描述、日期、严重程度）', '原文类别归一到统一分类，严重/轻微/根据实际情况判定 → 重要/一般/待判定；与潜在 PD 按同受试者、同类别、日期 ±窗口逐事件比对：已记录 / 未见记录', 'PD 漏录、分级不一致', '未见记录的潜在 PD 交 CRA 核实后补录'),
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
            k = ('检验变化预警' if c in ('范围内明显变化', '持续变化趋势') else '不良事件记录' if c.startswith('AE') or 'AESI' in c else '合并用药' if '用药' in c else '入排/访视' if re.search('入排|访视', c)
                 else '检验异常·绑定核查' if re.search(r'CS|关联|研究疾病|病史', c) else '检验记录质量' if re.search(r'参考范围|定性|未评价|判定不一致|量级异常', c) else '方案阈值专项')
            grp[k].append(c)
        col = {'检验变化预警': 'yel', '方案阈值专项': 'red', '不良事件记录': 'org', '合并用药': 'brn', '入排/访视': 'blu', '检验异常·绑定核查': 'org', '检验记录质量': ''}
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
             'flow': [['首剂日期', '暴露页首次实际给药'], ['归类', '给药前 / TEAE / 病史'], ['等级对照', f'同期检验 {C.GL} 等级'], ['处置一致', '合并用药 / 措施 / 转归']],
             'ab': {'个体': [['AE 记录核对', 'org', f"{sum(1 for o in C.others if o['cat'] in (aecats[0][1] if aecats else []))} 条信号"]],
                    '中心': [['AE/给药比', 'red', '≤0.5 例次/人：' + ('、'.join(f"{c['site']}（{c['dosed']}人/{c['ae']}次）" for c in low) or '无')]],
                    '全局': [['AE 谱', 'blu', '、'.join(f"{k} {v['n']}" for k, v in list(C.aesum.items())[:5])]]},
             'ex': ex_for(aecats[0][1] if aecats else []), 'm': ['M07'], 'r': [], 'todo': [], 'go': [['safety.html#tab=ae', 'AE 明细'], ['timeline.html', '时间线']]},
            {'k': 'lab', 't': '检验→AE/MH', 'sh': sorted({g['pts'][0][7] for g in C.labrows})[:4], 'ib': [],
             'f': ['结果 · 单位 · 参考范围', '临床意义评价（CS/NCS）', '异常描述', '病史/不良事件关联'],
             'flow': [['规定基线', '按方案基线定义（指定访视/首剂前最近/多次均值）；缺失时按规则回退'], ['数值等级', C.GL + '（基线异常按基线倍数）'], ['CS/NCS', '与数值、症状、处置对照'], ['关联对象', '同一疾病、时间吻合'], ['加重判断', '仅关联病史者比较基线']],
             'ab': {'个体': [['CS·未关联', 'solid-red', f"{lr('CSX')} 行"], ['CS·仅MH·较基线加重', 'org', f"{lr('MH')} 行"], ['NCS·≥2级', 'yel', f"{lr('NCS2')} 行"]] + ([['未评价·≥2级', 'yel', f"{lr('NA2')} 行"]] if lr('NA2') else []),
                    '中心': [['同值异判', 'yel', f"{sum(1 for c in C.cons if c['scope'] == 'center')} 组同中心对照，{sum(1 for c in C.cons if c['scope'] == 'center' and c['st'] == '需核实')} 组需核实"]],
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
                             'f': ['知情日期/版本', '访视日期', 'SoA 评估', '给药日期/时刻/剂量', '样本采集时刻', '合并用药', '入排数值', '方案偏离记录表'],
                             'flow': [['方案参数', '访视窗与锚点、SoA、给药/样本时点、禁用药、入排'], ['逐受试者推断', '执行层面＋科学层面规则'], ['分级', '重要 / 待判定 / 一般，附依据'],
                                      ['逐事件比对', '方案偏离记录表：已记录 / 未见记录'], ['处理', '发 query / CRA 核实 / 录入 PD']],
                             'ab': {'个体': [[tx.get(c, [c, c])[1], 'red' if any(x['grade'] == '重要' and x['cat'] == c for x in pot) else 'org', f"{n} 条"] for c, n in cc.most_common(6)],
                                    '中心': [['每例潜在 PD', 'org', '、'.join(f"{s}（{r:.2f}）" for r, s in rate) or '无']],
                                    '全局': [['已记录 / 潜在', 'blu', f"已记录 {len(conf)}；潜在 {len(pot)}（未见记录 {sum(1 for x in pot if x['status'] == '未见记录')}）"]]},
                             'ex': [['pd:' + x['id'], x['title'], ''] for x in exs], 'm': ['M15', 'M16', 'M17'], 'r': [], 'todo': [],
                             'go': [['deviations.html', '方案偏离'], ['deviations.html#tab=rules', '检查规则与覆盖']]})
        if C.KZeff['metrics']:
            C.review.append({'k': 'eff', 't': '有效性', 'sh': sorted({e['sheet'] for e in C.efficacy})[:4], 'ib': [], 'f': [m['label'] for m in C.KZeff['metrics']],
                             'flow': [['终点定义', '方案原文派生'], ['基线', m.get('baseVisit', '') if (m := (C.A.get('efficacy') or [{}])[0]) else ''], ['合理性', '离群 / 缺失'], ['盲态', '不分组']],
                             'ab': {'个体': [[a, 'org', f"{n} 条"] for a, n in Counter(x['k'] for x in C.KZeff['anomalies']).items()]}, 'ex': [], 'm': ['M12'], 'r': [], 'todo': [],
                             'go': [['efficacy.html', '有效性趋势']]})
    if not C.S.get('todo'):
        # V6（用户审阅 RUX 第 1 条、裁定 2）：报告不再有「待办」——风险计数已在总览风险数据与风险排名里；
        # 这里只留系统提示（构建/映射/词表这类需要人处理配置的事），显示在研究依据页底部
        C.todo = []
        miss_eff = (C.KZeff or {}).get('missing') or []
        if miss_eff:
            C.todo.append(['终点缺失', 'solid-red',
                           f"{len(miss_eff)} 项终点指标无数据：{'、'.join(x['label'] for x in miss_eff[:3])}"
                           f"{'…' if len(miss_eff) > 3 else ''}（核查量表映射/指标名）", 'efficacy.html'])
    else:
        C.todo = C.S['todo']
    if getattr(C, 'todo_hint', ''):                 # 扩展规则词表缺失 → 待办区提示（D-P5-2 fail-visible，不覆盖默认）
        C.todo.append(['词表', 'yel', C.todo_hint, 'study.html'])


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
    X = dict(zip(('ex', 'pdex'), build_ex(C)))
    KZ['cfg']['thrTiers'] = tier_variants(a, KZ, X, out, aud)
    write_outputs(C, KZ, X, csb_candidates, out, aud)


# 用户 2026-10-28：阈值切换后整份报告（各页列表、计数、质疑、潜在 PD）都要跟着变。T_base 影响构建期分层（较基线加重/研究疾病加重/
# 判定不一致等）及其质疑与潜在 PD，页面无法即时重算，故构建时每档各算一遍；页面按所选档位载入（assets/kz-tier.js）。
THR_TIERS = (0.2, 0.3, 0.5)
TIER_KEYS = ('labrows', 'others', 'queries', 'subs', 'pd', 'centers', 'cons', 'review', 'methods', 'kri')   # 随 T_base 变化的数据
# 质疑/潜在 PD 按顺序编号，档位不同编号会位移：按编号索引的原文（extra.js 的 ex/pdex）随档位一起替换（X）。
# todo 由工作台在构建后追加条目：档位只替换 skill 生成的前 todoBase 条，追加的保留（kz.js 合并）；unres 只由工作台写，不随档位。


def tier_variants(a, KZ, X, out, aud):
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
        if V.get('todo') != KZ.get('todo'):
            diff['todo'], diff['todoBase'] = V.get('todo') or [], len(KZ.get('todo') or [])
        XV = dict(zip(('ex', 'pdex'), build_ex(C)))
        if XV != X:
            diff['X'] = {k: XV[k] for k in XV if XV[k] != X.get(k)}
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
             'writer': q.get('writer', 'template'), **({'fixed': True} if q.get('fixed') else {})} for q in C.queries]   # 交工作台撰写（模型只措辞，不判定）


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
    micro_panel_mark(C)                                  # F-C＋第三轮：微生物培养/药敏先分域（build_findings 不收入 C.F）
    build_findings(C)
    panel_level_clin(C)                                  # V6：长表同一份化验单逐行重复的整份 CS 判定 → 只留在异常行
    bind.rebind(C)                                       # V6：规则指标正则零命中 → 按括注缩写/域别名重绑（说明进 KZ.bind）
    _strip_disease_term_links(C)                         # F02 边界：研究疾病词目不作 MH 关联（先于一切关联消费方）
    desc_term_links(C)                                   # V6：说明列写了本人 AE/病史术语即算关联（只匹配本人记录）
    annotate_links(C)                                    # 回溯后的关联类型（判定一致性归因维度用）
    build_labrows(C)
    rel_candidates(C)
    entry_errors(C)                                      # mm5 疑似录入错误（数据质量提示，不发 query）
    monitor_v5.lab_shift(C, add_other)                   # V5 范围内明显变化＋持续变化趋势（提示，不发 query）
    threshold_rules(C)
    combo_rules(C)
    ae_checks(C)
    cm_checks(C)
    transfusion_checks(C)                                # 审阅者 2026-11-09：Hb 短期大幅上升无输血记录、输血记录缺日期
    eligibility_checks(C)
    ie_checks(C)                                         # V6：入排标准页不满足但已入组
    range_checks(C)
    visit_window_checks(C)
    monitor_v5.gap_check(C, add_other)                   # V6：在研受试者长时间无记录（失访/未录入）
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
    build_ops(C)                                         # mm5 临床监察数据块 → KZ.ops
    monitor_v5.finalize(C)                               # V5 访视推算/新鲜度/随访人日/KRI/CtQ/数据可信度
    build_trend(C)
    build_eff(C)
    defaults(C)
    S = C.subj
    stc = Counter(s['status'] for s in S.values())
    subs = []
    for sid, s in S.items():
        ae = [x for x in C.ae_by[sid] if x['te'] and not x.get('dup')]   # F-D：完全重复记录（第 2 份起）不计数
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
    KZ = {'cfg': C.cfg, 'meta': {'cutoff': cutoff, 'qs': len(C.queries), 'qsSignals': len(C.queries) + getattr(C, 'qMerged', 0),
                                 'qsMerged': getattr(C, 'qMerged', 0),
                                 'counts': {k: len(getattr(C, k)) for k in ('subjects', 'visits', 'exposure', 'ae', 'mh', 'cm', 'findings', 'efficacy', 'pd', 'extq')},
                                 'status': dict(stc), 'n': len(S), 'centers': len(C.centers), 'dosed': len(C.pop), 'built': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
                                 'sources': C.cfg.get('footer', {}).get('left', '')},
          'subs': subs, 'centers': C.centers, 'aes': [{**{k: v for k, v in x.items() if not k.startswith('_') and k != 'sh'}, 'rl': bool(x.get('_rel')), 'ak': ae_action(x.get('act')),
                   'aesi': bool(x.get('aesi') or x.get('_aesi_def')),
                   'aesiM': bool(x.get('aesi')), 'aesiD': bool(x.get('_aesi_def')) and not x.get('aesi')} for x in C.aes if x['sid'] in C.pop],   # rl＝TRAE；ak＝措施分类；aesi＝勾选 ∪ 方案定义命中；aesiM/aesiD＝双口径（H5：已标/符合定义待核实）
          'aesiCal': aesi_caliber(C),
          'aesum': C.aesum, 'aecat': list(C.aesum), 'ibtag': ibtag, 'labrows': [{k: v for k, v in g.items() if (k != 'mid' or g.get('risk') == 'REL') and k != '_aecov'} for g in C.labrows],
          'others': [{**{k: (cn_quotes(v) if k == 'sum' else v) for k, v in o.items() if not k.startswith('_')},
                      **({'cl': thr_label(o['_rule'])} if o['cat'] == '阈值规则核对' and (o.get('_rule') or {}).get('metric') else {})}
                     for o in C.others],                 # cl＝面向研究者的类别名（阈值类按方案处理动作命名；内部 cat 不变以保持质疑身份稳定）
          'queries': [{k: v for k, v in q.items() if not k.startswith('_')} for q in C.queries], 'qcommon': C.qcommon,
          'cro': [[x.get('form') or '', x.get('row') or '', x.get('sid') or '', x.get('visit') or '', x.get('text') or ''] for x in C.extq],
          'cons': C.cons, 'rules': C.S.get('rules') or [], 'unres': C.S.get('unres') or [], 'methods': C.methods, 'eff': C.KZeff, 'effissues': [], 'v8': [],
          'tgroup': {}, 'study': C.S.get('study') or {}, 'review': C.review, 'todo': C.todo, 'pd': C.pdd, 'ops': C.ops, 'kri': C.kri, 'cred': C.cred, 'bind': {'notes': getattr(C, 'bind_notes', [])},
          # mm5 安全性概况（三级 Profile）：病史与合并用药明细（仅给药者；术语原文）
          'mhcm': {'mh': [[sid, m.get('t') or '', 1 if m.get('ong') == '是' else 0] for sid in sorted(C.pop) for m in C.mh_by[sid]],
                   'cm': [[sid, c.get('t') or '', c.get('s') or '', c.get('e') or '', 1 if c.get('ong') else 0, c.get('ind') or c.get('why') or '']
                          for sid in sorted(C.pop) for c in C.cm_by[sid]]},
          # 第三轮：微生物培养/药敏分域（判读型结果，不进检验异常/CS/阈值链）——[sid, 日期, 访视, 项目, 结果, 判读/说明, C|S, sheet, row]
          'micro': micro_rows(C),
          # mm4 研究依据页：方案规则的只读视图（编译后的可执行口径，供「监查规则」按领域展示；不含任何受试者数据）
          'basis': {k: C.A.get(k) for k in ('visitWindows', 'eligibility', 'eligibilitySubject', 'prohibited', 'washout', 'aesi', 'reportRules',
                                             'thresholdRules', 'comboRules', 'indicationBackground', 'cmProtocolRequired', 'pd', 'effRulesText') if C.A.get(k)}}
    if C.A.get('knowledge'):
        KZ['knowledge'] = C.A['knowledge']    # mm4：知识状态进数据面（工作台 S2.5/kb_inject 写入 analysis.knowledge；无键＝旧构建形态无扰）
    return KZ, csb_candidates


def write_outputs(C, KZ, X, csb_candidates, out, aud):
    S = C.subj
    js_write(out / 'core.js', 'KZ', KZ)
    js_write(out / 'trend.js', 'KZT', C.KZT)
    js_write(out / 'extra.js', 'KZX', {'soa': C.soa, 'soacols': C.soacols, 'soaGuard': getattr(C, 'soaGuard', []), 'ex': X['ex'], 'pdex': X['pdex']})
    js_write(out / 'grading.js', 'KZG', {'label': C.GL, 'system': C.G.t.get('system'), 'version': C.G.t.get('version'), 'source': C.G.t.get('source', ''),
                                         'items': {k: v for k, v in C.G.items.items() if k in set(C.cmap.values())}, 'map': C.cmap, 'fac': C.fac})
    build_subject_files(C, out)
    raw_export.export_raw(C, out)                        # V6：原始数据层（data/r/<sid>.js＋rawidx.js，证据抽屉/原始数据页就地查看）
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
