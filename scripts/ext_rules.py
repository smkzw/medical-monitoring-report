#!/usr/bin/env python3
"""扩展规则（M13–M23 确定性部分，03 §3）：由 mm_build.py 调用（`ext_rules.run(C)` → CSB 候选列表）。

M13 MHX-T 首剂前疑似病史漏记（非 CS 部分）——labrows 候选（pr2，不自动发 query）；
M15 血压默认上限（listing 未给范围时 SBP 139 / DBP 89，仅用于偏离计算）；
M16 定性弱阳性/基线阴性后新发；M17 CM-IND 用药适应症未记录；M18 PREG 妊娠阳性；
M19 AE-EX 给药一致性（±aeExWindow 天，默认 7）；M20 AE-SAE 死亡一致性；M21 AE-COURSE 转归与走势；
M23 CSB 步骤 1/1′/2/3/4 确定性 query（LINK / CSX_AE / MH 加重 / CSW / CSX，经 others 通道统一
merge/CRO 查重/qkey）＋步骤 5 候选导出（供工作台 review/csb.py::explain_cs，字段见其模块 docstring）；
日期序完整性（AE/CM/给药 起止倒置 → DATEORD，S45 收口）。

口径（03 为准）：
- 词表键缺失（mhMatch / cmIndicationMap / indicationBackground）→ 对应规则零命中，
  todo 列「词表未配置」（不猜医学对应关系，fail-visible）；
- M23 步骤 4 的 T_base 用构建配置（cfg.thresholds.base，默认 0.3，与 review/csb.py 默认一致）；
  页面阈值选择器只驱动风险项（REL/MHX-T）即时重分类，不改变已生成 query；
- D21：方案「研究疾病预期进展不作 AE」条款经确认（study.diseaseProgressionNotAE.confirmed=true 且有原文）
  时，有研究疾病线索（indicationBackground 命中）的步骤 4 确定性恶化不直接发 query，转步骤 5 候选交 A5R5。
"""
from __future__ import annotations

import re
from collections import defaultdict

from common import days, fmt, is_full_date

BP_DEFAULT_HI = {'收缩压': 139, '舒张压': 89}      # M15：listing 未给范围时的默认上限（与 skill demo 一致）


def bp_default_hi(f):
    """M15：vs 域收缩压/舒张压无上限时用默认上限（仅用于偏离计算，不改写行数据）。"""
    if f.get('domain') == 'vs' and f.get('hi') is None:
        return BP_DEFAULT_HI.get(str(f.get('test') or ''))
    return None


def ref_hi(r):
    return r.get('hi') if r.get('hi') is not None else bp_default_hi(r)


def dev_of(r):
    """行级偏离比例（M15 血压默认上限优先）。mm_build.build_findings 用同口径写 r['dev']。"""
    v, lo, hi = r.get('value'), r.get('lo'), ref_hi(r)
    if v is None or (lo is None and hi is None):
        return None
    if hi is not None and v > hi:
        return (v - hi) / abs(hi) if hi else None
    if lo is not None and v < lo:
        return (lo - v) / abs(lo) if lo else None
    return 0.0


_WEAK = re.compile(r'±|\+\s*/?\s*-|弱阳|微量|trace', re.I)      # mm4：「+-」「+/-」「10（+-）」也是 ±
_POS = re.compile(r'阳|[＋+]')


def qual_level(raw):
    """定性强度：0 阴性/正常；1 ±/弱阳性/微量；2 ≥「+」；None 无法判断。"""
    s = str(raw or '').strip()
    if not s:
        return None
    if _WEAK.search(s):
        return 1
    if _POS.search(s):
        return 2
    if re.search(r'阴|正常|neg', s, re.I):
        return 0
    return None


def _fmt_range(lo, hi):
    if lo is not None and hi is not None:
        return f"{fmt(lo)}–{fmt(hi)}"
    if hi is not None:
        return f"≤{fmt(hi)}"
    if lo is not None:
        return f"≥{fmt(lo)}"
    return '未提供'


def _val(v, unit):
    u = str(unit or '').strip()
    u = ('×' + u) if u.startswith('10^') else u
    if isinstance(v, bool) or v is None:
        return '（未填写）'
    if isinstance(v, (int, float)):
        x = fmt(v) if isinstance(v, float) else str(v)
        return f"{x} {u}".strip()
    return f"「{v}」"


def _raw_or_val(r):
    return r.get('raw') if r.get('value') is None else r.get('value')


def _head(C, r):
    gtxt = f"；{C.GL} {r.get('grade')} 级" if r.get('grade') else ''
    rng = f"（参考范围 {_fmt_range(r.get('lo'), r.get('hi'))}{gtxt}）" if (r.get('lo') is not None or r.get('hi') is not None) else ''
    return f"{r.get('visit', '')}（{r.get('date', '')}）{C.metric[r['mid']]['label']} {_val(_raw_or_val(r), r.get('unit'))}{rng}"


# --------------------------------------------------------------------------- 词表
def _load_lists(C):
    A = C.A
    C.mhMatch = [(re.compile(a), re.compile(b)) for a, b in (A.get('mhMatch') or [])]
    C.cmInd = [(re.compile(a), re.compile(b)) for a, b in (A.get('cmIndicationMap') or [])]
    C.indBg = [(re.compile(a), str(b or '')) for a, b in (A.get('indicationBackground') or [])]
    C.cmProto = [re.compile(p, re.I) for p in (A.get('cmProtocolRequired') or [])]
    NEED = {'mhMatch': ('检验指标↔病史对应表', '异常是否已有病史解释'), 'cmIndicationMap': ('合并用药↔用药原因对应表', '用药原因未在病史/AE 中记录'),
            'indicationBackground': ('研究疾病常见检查表现', '异常是否属研究疾病表现')}
    missing = [k for k, v in (('mhMatch', C.mhMatch), ('cmIndicationMap', C.cmInd), ('indicationBackground', C.indBg)) if not v]
    if missing:                                     # 只列真正缺的项，说清楚因此少核查了什么
        C.todo_hint = '未提供' + '；'.join(f"{NEED[k][0]}：本次未核查「{NEED[k][1]}」" for k in missing)


def mh_terms_hit(C, mid, mh_list):
    return any(mre.search(mid) and tre.search(m.get('t') or '') for mre, tre in C.mhMatch for m in mh_list)


def ae_match_rows(C, mid):
    return [(re.compile(a), re.compile(b), w) for a, b, w in (C.A.get('aeMatch') or []) if re.search(a, mid)]


def disease_hint(C, mid):
    for mre, note in C.indBg:
        if mre.search(mid):
            return note or '研究疾病常见表现'
    return None


# --------------------------------------------------------------------------- M13 MHX-T
def m13_mhx_t(C):
    """首剂前 NCS/未评价且偏离 ≥T_dev（或 ≥2 级/定性 ≥+）且病史未记录 → MHX-T 候选（pr2，不发 query）。
    排除：CS（归 M23）、研究疾病表现（indicationBackground）、已触发 M09 入排核查的同一数值、检验页已关联病史。
    支持证据（ctx）：首剂前 ≥2 次满足或首剂后同向持续 → 持续异常；cmIndicationMap 对应用药 → 有对应用药。"""
    if not C.mhMatch:
        return
    doms = set(C.A.get('labDomains', ['lab', 'vs', 'ecg']))
    thr = C.cfg['thresholds']
    elig_rows = {(o['sid'], o.get('sh'), o.get('row')) for o in C.others if o.get('cat') == '入排标准核对'}
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop or mid.split(':')[0] not in doms:
            continue
        dev_t = float((thr.get('per_metric') or {}).get(mid, {}).get('dev', thr['dev']))
        for T in C.mthr:
            if T.get('metric') and re.search(T['metric'], mid) and T.get('dev') is not None:
                dev_t = min(dev_t, float(T['dev']))
        floor = min(0.20, dev_t)
        pre = [r for r in rows
               if not r['post'] and r.get('clin') in (1, None)
               and ((r.get('dev') or 0) >= floor or (r.get('grade') or 0) >= 2
                    or (r.get('value') is None and (qual_level(r.get('raw')) or 0) >= 2))
               and (sid, r['sheet'], r['row']) not in elig_rows
               and not any(l[0] == 'MH' for l in (r.get('links') or []))]
        if not pre or mh_terms_hit(C, mid, C.mh_by[sid]) or disease_hint(C, mid):
            continue
        worst = max(pre, key=lambda r: (r.get('dev') or 0, r.get('grade') or 0))
        ctx = []
        if len(pre) >= 2:
            ctx.append('持续异常：首剂前 ≥2 次满足')
        wv, whi = worst.get('value'), ref_hi(worst)
        w_above = whi is not None and wv is not None and wv > whi
        if any(r.get('dev') and r['post'] and ((ref_hi(r) is not None and r['value'] > ref_hi(r)) == w_above) for r in rows):
            ctx.append('首剂后同向异常持续')
        cm_hit = [c for c in C.cm_by[sid]
                  if any(ire.search(c.get('why') or '') and tre.search(c.get('t') or '') for ire, tre in C.cmInd)]
        if cm_hit:
            ctx.append(f"有对应用药：{cm_hit[0]['t']}（{cm_hit[0]['s']} 起，用药原因「{cm_hit[0]['why']}」）")
        b = rows[0]['base']
        from mm_build import wb_sheet          # PR-8：唯一 id 解析（旧名键控查不到 → 未限定）
        wbs = wb_sheet(C, worst.get('sheet'))
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': '疑似病史漏记（首剂前偏离）', 'test': C.metric[mid]['label'], 'mid': mid,
            'grp': pre[0].get('group') or '', 'pr': 2,
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None if r.get('dev') is None else round(r['dev'], 4), r.get('wb') or ''] for r in pre],
            'rel': [], 'ctx': ctx or ['首剂前已超出参考范围，病史未记录'],
            'q': [], 'fid': [], 'cro': '', 'mg': max([r.get('grade') or 0 for r in pre] + [0]), 'risk': 'MHX-T',
            'qkey': f"lab|{sid}|MHX-T|{wbs}|{mid}|{worst.get('visit') or ''}"})


# --------------------------------------------------------------------------- M16 定性
_PREG = re.compile(r'妊娠|怀孕|hcg|pregn', re.I)


def m16_qual(C):
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop or _PREG.search(mid) or all(r.get('value') is not None for r in rows):
            continue                                   # 只看定性（无数值）指标；妊娠类定性由 M18 处理
        pre_lv = [qual_level(r.get('raw')) for r in rows if not r['post']]
        base_lv = next((x for x in reversed(pre_lv) if x is not None), 0)
        test = C.metric[mid]['label']
        for r in rows:
            if not r['post']:
                continue
            lv = qual_level(r.get('raw'))
            if lv is None:
                continue
            if lv == 1 and (r.get('clin') or 0) != 2:
                add_ext(C, sid, '定性结果核对', 'M16', 1,
                        f"{r.get('visit')}（{r.get('date')}）{test}「{r.get('raw')}」（±/弱阳性/微量）",
                        r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                        ctx=['弱阳性，仅作提示（研究者判为有临床意义的另按「CS 未关联」核查）'],
                        rule={'ask': '请结合复测与临床判断是否需关注。'}, bkey=f"{mid}|{r.get('visit')}|{r.get('date')}", wb=r.get('wb') or '')
            elif lv == 2 and base_lv == 0 and (r.get('clin') or 0) != 2:
                # 研究者判定优先：已评价为正常/NCS 的新发定性异常只作提示（pr1，不发 query）；未评价才请研究者评价（pr3）
                assessed = r.get('clin') in (0, 1)
                add_ext(C, sid, '定性结果核对', 'M16-NEW', 1 if assessed else 3,
                        f"{r.get('visit')}（{r.get('date')}）{test}「{r.get('raw')}」，该指标基线（首剂前最近一次）为阴性",
                        r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                        ctx=['定性结果新出现阳性（基线阴性 → ≥+）'] +
                            (['研究者已评价为' + ('正常' if r.get('clin') == 0 else '异常无临床意义') + '（研究者判定优先，仅提示）'] if assessed else []),
                        rule={'ask': '请评估该新发定性异常的临床意义，必要时复测。'}, bkey=f"{mid}|{r.get('visit')}|{r.get('date')}", wb=r.get('wb') or '')


# --------------------------------------------------------------------------- M17 CM-IND
def m17_cm_ind(C):
    if not C.cmInd:
        return
    prevent = re.compile(r'预防')
    for sid in sorted(C.pop):
        mh_t = [m.get('t') or '' for m in C.mh_by[sid]]
        ae_t = [a.get('t') or '' for a in C.ae_by[sid]]
        for c in C.cm_by[sid]:
            why = c.get('why') or ''
            if not why or prevent.search(why) or any(pre.search(c.get('t') or '') for pre in C.cmProto):
                continue
            hit = [tre for ire, tre in C.cmInd if ire.search(why)]
            if not hit:
                continue
            if any(any(tre.search(x) for x in mh_t + ae_t) for tre in hit):
                continue                               # 病史或 AE 已有对应记录
            fd = C.subj[sid]['fd']
            ask_hist = not fd or not is_full_date(c.get('s')) or c['s'] <= fd
            where = '病史页' if ask_hist else '病史页及不良事件页'
            add_ext(C, sid, '用药适应症核对', 'M17', 3,
                    f"合并用药「{c['t']}」（{c['s'] or '?'} 起，用药原因「{why}」），{where}均未见「{why}」相关记录",
                    None, c['s'], c['sh'], c['row'], c['t'],
                    ctx=['首剂前开始 → 核对病史' if ask_hist else '首剂后开始 → 核对不良事件'],
                    rule={'ask': '请确认是否需补充记录。'}, bkey=f"{c.get('n') or c['t']}|{c['s']}", wb=c.get('wb') or '')


# --------------------------------------------------------------------------- M18 PREG
def m18_preg(C):
    pre = re.compile(r'妊娠|怀孕|hcg|pregn', re.I)
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop or not pre.search(mid):
            continue
        test = C.metric[mid]['label']
        for r in rows:
            pos = (r.get('clin') == 2) or bool(r.get('raw') and re.search(r'阳', str(r.get('raw')))) or \
                   (r.get('value') is not None and r.get('hi') is not None and r['value'] > r['hi'])
            if not pos:
                continue
            vtxt = _raw_or_val(r)
            vshow = f"「{vtxt}」" if not isinstance(vtxt, (int, float)) else f"{_val(vtxt, r.get('unit'))}（超参考范围）"
            add_ext(C, sid, '妊娠检测核对', 'M18', 4,
                    f"{r.get('visit')}（{r.get('date')}）{test}{vshow}",
                    r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                    rule={'ask': '请确认是否为妊娠事件，并按方案要求完成妊娠报告与随访；如为误录，请更正。'},
                    bkey=f"{mid}|{r.get('visit')}|{r.get('date')}", wb=r.get('wb') or '')


# --------------------------------------------------------------------------- M19 AE-EX
def m19_ae_ex(C):
    w = C.A.get('aeExWindow', 7)
    ae_re = re.compile(r'不良事件|AE')
    act_re = re.compile(r'暂停|停药|停用|中断|pause|stop|hold', re.I)

    def near(d1, d2):
        return d1 and d2 and days(d1, d2) is not None and abs(days(d1, d2)) <= w

    for sid in sorted(C.pop):
        exp = [e for e in C.exposure if e['sid'] == sid]
        for e in exp:                                   # ① 给药中断（原因=不良事件）±w 天无对应措施的 AE
            why = str(e.get('pause') or '')
            if not act_re.search(why) or not ae_re.search(why):
                continue
            if any(act_re.search(str(a.get('act') or '')) and near(a.get('s'), e.get('start')) for a in C.ae_by[sid]):
                continue
            add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                    f"给药记录 {e.get('visit') or ''}（{e.get('start')}）「{why}」，不良事件页未见同期（±{w} 天）采取措施为暂停/停药的记录",
                    e.get('visit'), e.get('start'), e.get('sheet', ''), e.get('row'), '',
                    rule={'ask': '请核实并补充或更正。'}, bkey=f"{e.get('start')}|{why}", wb=e.get('wb') or '')
        # 给药记录里的「中断」：暂停原因文本、剂量为 0 的给药区间、相邻区间之间的空档；永久停药看末次给药日期
        stops = [e.get('start') for e in exp if act_re.search(str(e.get('pause') or '')) or
                 any(str(e.get(k)).strip() in ('0', '0.0') for k in ('dose_act', 'qty') if e.get(k) not in (None, ''))]
        iv = sorted((e['start'], e.get('end') or e['start']) for e in exp if is_full_date(e.get('start')))
        stops += [prev[1] for prev, nxt in zip(iv, iv[1:]) if is_full_date(prev[1]) and (days(nxt[0], prev[1]) or 0) > 1]
        last = max((x[1] for x in iv if is_full_date(x[1])), default=None)
        for a in C.ae_by[sid]:                          # ② AE 措施=停药/暂停但给药记录无中断
            if not act_re.search(str(a.get('act') or '')):
                continue
            if any(near(d, a.get('s')) for d in stops) or (re.search(r'永久|停药|停用', str(a.get('act'))) and near(last, a.get('s'))):
                continue
            add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                    f"AE「{a['t']}」（{a['s']}）采取措施「{a['act']}」，给药记录未见同期（±{w} 天）中断/暂停",
                    None, a['s'], a['sh'], a['row'], a['t'],
                    rule={'ask': '请核实给药记录与 AE 措施是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')


# --------------------------------------------------------------------------- M20 AE-SAE
def m20_ae_sae(C):
    for a in C.aes:
        sid = a['sid']
        if sid not in C.pop:
            continue
        crit = str(a.get('sae_crit') or '')
        if a['sae'] and not crit.strip():
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」（{a['s']}）SAE=是，但 SAE 标准（致死/危及生命/住院/致残/先天异常/其他重要事件）均未勾选",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')
        elif (not a['sae']) and crit.strip():
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」（{a['s']}）勾选了 SAE 标准（{crit}），但 SAE=否",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')
    deaths = {}
    for a in C.aes:
        if a['sid'] in C.pop and re.search(r'死亡', str(a.get('out') or '')):
            deaths.setdefault(a['sid'], []).append(a)
    for sid, lst in deaths.items():
        a = min(lst, key=lambda x: (x.get('e') or x.get('s') or '9999'))
        d = a.get('e') or a.get('s')
        s = C.subj[sid]
        if s.get('eos_d') and is_full_date(s['eos_d']) and is_full_date(d) and s['eos_d'] != d:
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」转归「死亡」（{d}），研究结束日期 {s['eos_d']}（原因「{s.get('eos_why') or ''}」）不一致",
                    None, d, a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实死亡日期与研究结束信息。'}, bkey=f"{a.get('n')}|死亡日期", wb=a.get('wb') or '')
        later = [x.get('start') for x in C.exposure if x['sid'] == sid and is_full_date(x.get('start')) and x['start'] > d]
        later += [x.get('date') for x in C.visits if x['sid'] == sid and is_full_date(x.get('date')) and x['date'] > d]
        later += [r.get('date') for (s2, mid), rs in C.F.items() if s2 == sid for r in rs
                  if is_full_date(r.get('date')) and r['date'] > d]
        if later:
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」转归「死亡」（{d}），其后仍有给药/访视/检验记录：{'、'.join(sorted(set(later))[:4])}",
                    None, d, a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实死亡日期或后续记录。'}, bkey=f"{a.get('n')}|死亡后活动", wb=a.get('wb') or '')


# --------------------------------------------------------------------------- M21 AE-COURSE
def _ae_labs(C, sid, no, term):
    """该 AE 关联（link 指向，或 aeMatch 指标×该 AE 术语）的检验行。"""
    out, seen = [], set()
    for (s2, mid), rows in sorted(C.F.items()):
        if s2 != sid:
            continue
        for r in rows:
            key = (r['sheet'], r['row'])
            if key in seen:
                continue
            if any(l[0] == 'AE' and str(l[3]) == str(no) for l in (r.get('links') or [])) or \
                    (term and any(are.search(term) for mre, are, w in ae_match_rows(C, mid))):
                seen.add(key)
                out.append(r)
    return out


def m21_ae_course(C):
    for a in C.aes:
        sid = a['sid']
        if sid not in C.pop:
            continue
        labs = _ae_labs(C, sid, a['n'], a['t'])
        if a.get('e'):                                  # ① AE 已结束，关联检验结束后仍异常/加重
            worse = [r for r in labs if is_full_date(r.get('date')) and r['date'] > a['e']
                     and (r.get('grade') or 0) >= 2 and (r.get('clin') or 0) >= 1]
            if worse:
                w0 = max(worse, key=lambda r: (r.get('grade') or 0, r.get('date') or ''))
                add_ext(C, sid, 'AE转归与检验走势核对', 'M21', 2,
                        f"AE「{a['t']}」已结束（{a['e']}），关联检验 {C.metric[w0['mid']]['label']} 在结束后仍异常"
                        f"（{w0.get('visit')}（{w0.get('date')}）{_val(_raw_or_val(w0), w0.get('unit'))}，{C.GL} {w0.get('grade')} 级）",
                        w0.get('visit'), w0.get('date'), w0['sheet'], w0['row'], C.metric[w0['mid']]['label'],
                        rel=[['AE', a['t'], a['s'], a['n']]],
                        ctx=['检验走势与 AE 转归不一致（提示，必要时可发质疑）'],
                        rule={'query': False, 'ask': '请评估是否需更新 AE 转归或补充随访检验。'},
                        bkey=f"{a.get('n')}|{C.metric[w0['mid']]['label']}", wb=w0.get('wb') or '')
        else:                                           # ② 末次访视异常未恢复、AE 未结束且无随访安排
            last_d = max((v.get('date') or '' for v in C.visits if v['sid'] == sid), default='')
            open_abn = [r for r in labs if (r.get('clin') or 0) >= 1 and r.get('date') and (not last_d or r['date'] >= last_d)]
            if open_abn:
                r0 = open_abn[-1]
                add_ext(C, sid, 'AE转归与检验走势核对', 'M21', 2,
                        f"AE「{a['t']}」（{a['s']} 起，未结束），末次访视（{last_d or '—'}）关联检验 "
                        f"{C.metric[r0['mid']]['label']} 仍异常、未见随访安排",
                        None, last_d, a['sh'], a['row'], C.metric[r0['mid']]['label'],
                        rel=[['AE', a['t'], a['s'], a['n']]],
                        ctx=['异常未恢复且 AE 未结束（提示）'],
                        rule={'query': False, 'ask': '请确认随访安排或更新 AE 转归。'},
                        bkey=f"{a.get('n')}|{C.metric[r0['mid']]['label']}|未恢复", wb=a.get('wb') or '')


# --------------------------------------------------------------------------- 日期序（S45 收口，D-P5-14）
def date_order(C):
    def bad(s, e):
        return is_full_date(s) and is_full_date(e) and s > e

    for a in C.aes:
        if a['sid'] in C.pop and bad(a.get('s'), a.get('e')):
            add_ext(C, a['sid'], '日期完整性核对', 'DATEORD', 3,
                    f"AE「{a['t']}」开始日期 {a['s']} 晚于结束日期 {a['e']}",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实并更正起止日期。'}, bkey=f"{a.get('n')}|{a['s']}|{a['e']}", wb=a.get('wb') or '')
    for c in C.cm:
        if c['sid'] in C.subj and bad(c.get('start'), c.get('end')):
            add_ext(C, c['sid'], '日期完整性核对', 'DATEORD', 3,
                    f"合并用药「{c.get('term')}」开始日期 {c['start']} 晚于结束日期 {c['end']}",
                    None, c['start'], c.get('sheet', ''), c.get('row'), c.get('term'),
                    rule={'ask': '请核实并更正起止日期。'}, bkey=f"{c.get('no') or c.get('term')}|{c['start']}|{c['end']}")
    for e in C.exposure:
        if e['sid'] in C.subj and bad(e.get('start'), e.get('end')):
            add_ext(C, e['sid'], '日期完整性核对', 'DATEORD', 3,
                    f"给药记录{('（' + e['visit'] + '）') if e.get('visit') else ''}开始日期 {e['start']} 晚于结束日期 {e['end']}",
                    e.get('visit'), e['start'], e.get('sheet', ''), e.get('row'), '',
                    rule={'ask': '请核实并更正起止日期。'}, bkey=f"{e['start']}|{e['end']}", wb=e.get('wb') or '')


# --------------------------------------------------------------------------- M23 CSB 确定性＋候选
def grade_up(bg, cg):
    """按分级判加重：基线已 ≥1 级后再升级，或升到 ≥2 级。0 级 → 1 级不单独算（避免略超上限即判加重）。"""
    return (cg or 0) > (bg or 0) and ((bg or 0) >= 1 or (cg or 0) >= 2)


def worse_vs_base(r, b, t_base):
    """D14/D19 较基线加重：分级升高（0→1 级不单独算，见 grade_up），或超出范围且同向较基线变化 ≥T_base。
    返回说明文本或 None；仅临床意义 NCS→CS 的判定波动不算加重。"""
    if not b:                                        # 基线缺失：不虚构「0→2 级」，由调用方按「无法判断」处理
        return None
    if grade_up(b.get('grade'), r.get('grade')):
        return f"等级 {b.get('grade') or 0}→{r.get('grade')} 级"
    v, bv = r.get('value'), b.get('value')
    if v is None or bv is None:
        return None
    hi, lo = ref_hi(r), r.get('lo')                  # 血压无参考范围时用默认上限（与 REL/步骤 4 同口径）
    above, below = hi is not None and v > hi, lo is not None and v < lo
    if bv == 0:                                      # 基线为 0（如乙肝表面抗原 0→199.68）：现超出范围即视为加重
        return '基线为 0，现超出参考范围' if above else None
    pct = (v - bv) / abs(bv)
    if above and pct >= t_base:
        return f"较基线升高 {pct * 100:.0f}%"
    if below and -pct >= t_base:
        return f"较基线降低 {-pct * 100:.0f}%"
    return None


def qual_worse(r, b):
    """定性结果加重：阳性等级升高（阴性→阳性、±→+ 等）。"""
    if not b:
        return None
    lv, bl = qual_level(r.get('raw')), qual_level(b.get('raw'))
    return f"定性结果 {b.get('raw')}→{r.get('raw')}" if lv is not None and bl is not None and lv > bl else None


def _indication_names(C):
    ind = next((f[1] for f in ((C.S.get('study') or {}).get('design') or {}).get('facts') or [] if f[0] == '适应症'), '')
    return [p for p in re.split(r'[^\u4e00-\u9fff]+', re.sub(r'中度至重度|轻度|中度|重度|中重度|患者|伴有|成人|儿童|青少年|的|和|及', ' ', str(ind)))
            if len(p) >= 3]


def disease_kw(C):
    """研究疾病及其表现的关键词（方案适应症＋indicationBackground 名称），用于识别「研究疾病加重」类 AE 与研究疾病病史。"""
    kws = set(_indication_names(C))
    for _, b in C.A.get('indicationBackground') or []:
        nm = re.sub(r'[（(].*?[)）]|[↑↓]|（医学常识）', '', str(b).split('：')[0]).strip()
        nm = re.sub(r'^(外周血|血清|血)|(增多|升高|降低|减少|异常)$', '', nm)
        if len(nm) >= 2:
            kws.add(nm)
    return re.compile('|'.join(sorted(map(re.escape, kws), key=len, reverse=True))) if kws else None


def disease_name_re(C):
    """研究疾病名称（不含表现）：适应症＋方案缩写（analysis.diseaseTerms，如 AD）＋「研究疾病/原发病」。用于识别备注里的归因。"""
    if getattr(C, '_dz_name', None) is None:
        alt = ['研究疾病', '原发病', '原发疾病'] + [re.escape(n) for n in _indication_names(C)] + \
              [rf'(?<![A-Za-z]){re.escape(a)}(?![A-Za-z])' for a in C.A.get('diseaseTerms') or []]
        C._dz_name = re.compile('|'.join(alt))
    return C._dz_name


def _cs_text(r):
    return ' '.join(str(r.get(k) or '') for k in ('reason_raw', 'reason_text', 'desc'))


def disease_attr(C, r):
    """CS 归因研究疾病：原因选项为研究疾病，或备注写明与研究疾病相关（D001：「与AD相关」「研究疾病相关」多写在异常描述里）。
    否定写法（「与AD无关」「排除AD」「不考虑研究疾病」）与「AD 治疗药物相关」不算归因。"""
    if 'disease' in (r.get('reason') or ''):
        return True
    nm = disease_name_re(C).pattern
    neg = re.compile(rf"(?:{nm})[^，。；,;]{{0,4}}(?:无关|不相关)|(?:排除|不考虑|除外|并非|非)[^，。；,;]{{0,4}}(?:{nm})|(?:{nm})[^，。；,;]{{0,4}}(?:治疗|药物|用药)[^，。；,;]{{0,3}}相关")
    return bool(disease_name_re(C).search(neg.sub('', _cs_text(r))))


_WORSE_TXT = re.compile(r'加重|恶化|进展|加剧|复发')
_NOT_WORSE = re.compile(r'(?:未见?|无|并非|非|没有|不考虑|排除|除外)[^，。；,;]{0,6}(?:加重|恶化|进展|加剧|复发)')   # 不收单字「不」：「控制不佳加重」是加重


def stated_worse(r):
    """研究者在原因/备注里写明加重（「AD加重相关」「皮损较前加重」）：研究者判定优先，视为较基线加重。返回说明或 None。"""
    s = _NOT_WORSE.sub('', _cs_text(r))
    m = _WORSE_TXT.search(s)
    return f"研究者备注「{s[max(0, m.start() - 8):m.end() + 2].strip(' ，,。；;：:')}」" if m else None


def _dprefix(s):
    m = re.match(r'\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4}', str(s or ''))
    return m.group() if m else None


def ae_covers(a, d):
    """AE 持续期间覆盖日期 d（起始 ≤ d ≤ 结束；未结束视为持续；不完整日期按已知的年/年-月比较）。"""
    s, e = _dprefix(a.get('s')), _dprefix(a.get('e'))
    return bool(s) and s <= d[:len(s)] and (not e or d[:len(e)] <= e)


def _stem(C, mid):
    return re.sub(r'[（(].*$|百分比|计数|绝对值|浓度|含量', '', str(((getattr(C, 'metric', None) or {}).get(mid) or {}).get('label') or mid))


def onset_note(C, mid, a, pts):
    """以检验异常为主要表现的 AE（术语含指标名），起始日期应为检验首次异常日期；不一致时给出提示。"""
    ds = sorted(r['date'] for r in pts if is_full_date(r.get('date')))
    stem = _stem(C, mid)
    if ds and len(stem) >= 2 and stem in a['t'] and a.get('s') != ds[0]:
        return f"；AE 起始 {a.get('s') or '—'} 与首次异常检验日期 {ds[0]} 不一致，请核对"
    return ''


def opposite_dir(pts):
    """与这组检验异常方向相反的 AE 术语写法（升高的指标不对应「…减少/降低」）；方向不明时不排除任何术语。"""
    up = any(r.get('value') is not None and r.get('hi') is not None and r['value'] > r['hi'] for r in pts)
    down = any(r.get('value') is not None and r.get('lo') is not None and r['value'] < r['lo'] for r in pts)
    return re.compile('减少|降低|下降|减低|偏低' if up and not down else '增多|升高|增高|增加|偏高' if down and not up else '$^')


def disease_ae(C, sid, mid, pts, dz=None):
    """已记录的研究疾病加重类 AE：持续期间覆盖任一异常检验日期（ae_covers），术语含研究疾病/表现关键词或该指标名，且方向一致。
    不用固定时间窗（±N 天无法规或指导原则依据，用户 2026-10-27）；首剂前开始的 AE 不算。"""
    dz = dz if dz is not None else disease_kw(C)
    ds = [r['date'] for r in pts if is_full_date(r.get('date'))]
    if not ds:
        return []
    opp, stem = opposite_dir(pts), _stem(C, mid)
    return [a for a in C.ae_by[sid] if not a.get('pre') and not opp.search(a['t']) and any(ae_covers(a, d) for d in ds)
            and ((dz and dz.search(a['t'])) or (len(stem) >= 2 and stem in a['t']))]


def _comparable(r):
    if r.get('value') is not None:
        return 'n', r['value']
    if qual_level(r.get('raw')):                      # 定性阳性类（±/+/2+…）按写法比较；阴性/文本描述不比较
        return 'q', re.sub(r'\s', '', str(r.get('raw')))
    return None


def same_level(C, a, b):
    """两次结果相同或相近：数值相差 ≤ analysis.clinConsistTol（默认 10%）且同向超出参考范围；定性结果写法相同。
    无参考范围的数值（如心电图间期，临床意义评价的是整份心电图）不比较。"""
    ka, kb = _comparable(a), _comparable(b)
    if not ka or not kb or ka[0] != kb[0]:
        return False
    if ka[0] == 'q':
        return ka[1] == kb[1]

    def side(r):
        v = r['value']
        return 1 if r.get('hi') is not None and v > r['hi'] else -1 if r.get('lo') is not None and v < r['lo'] else 0
    x, y = ka[1], kb[1]
    return side(a) == side(b) != 0 and abs(x - y) <= float(C.A.get('clinConsistTol', 0.1)) * max(abs(x), abs(y))


def judgment_only(C, r, rows, t_base):
    """该 CS 点与同受试者同指标某次 NCS 判定数值相近、且较基线未加重：属判定不一致，不按「潜在 AE 漏记」处理（用户 2026-10-27）。"""
    return not worse_vs_base(r, r.get('base'), t_base) and any(a.get('clin') == 1 and same_level(C, a, r) for a in rows)


def clin_consistency(C):
    """同一受试者同一指标，相同/相近结果一次判 NCS、一次判 CS → 发 query（判定一致性；不构成方案偏离）。
    同一受试者同一表单合并为一条（D002：贫血受试者的 MCH/MCHC/MCV/Hb 常同时出现），锚定最近一次相关记录。"""
    by = defaultdict(list)
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop:
            continue
        pairs = [tuple(sorted((a, b), key=lambda x: x.get('date') or '')) for b in rows if b.get('clin') == 2
                 for a in rows if a.get('clin') == 1 and same_level(C, a, b)]
        if pairs:
            by[(sid, pairs[0][0]['sheet'])].append((mid, pairs))
    for (sid, sh), items in sorted(by.items()):
        def last(it):
            return max(x.get('date') or '' for p in it[1] for x in p)
        items.sort(key=last, reverse=True)
        mid, pairs = items[0]
        late = max((x for p in pairs for x in p), key=lambda x: x.get('date') or '')
        parts = []
        for m, ps in items[:3]:
            a, b = max(ps, key=lambda p: p[1].get('date') or '')
            parts.append(f"{C.metric[m]['label']}：" + '，'.join(
                f"{x.get('visit')}访视{_val(_raw_or_val(x), x.get('unit'))}判为{'CS' if x.get('clin') == 2 else 'NCS'}" for x in (a, b)))
        more = f"（另有 {len(items) - 3} 项同类情况）" if len(items) > 3 else ''
        add_ext(C, sid, '临床意义判定不一致', 'CLIN-INC', 3, '；'.join(parts) + f"，结果相近但判定不同{more}",
                late.get('visit'), late.get('date'), late['sheet'], late['row'], C.metric[mid]['label'],
                ctx=['判定一致性核对（不构成方案偏离）'],
                rule={'ask': '请核实并统一临床意义判定；如判为有临床意义，请评估是否需记录AE。'},
                bkey=f"{sh}|clin", wb=late.get('wb') or '')


def _worsening(r, t_base):
    """步骤 4 确定性恶化（与 review/csb.py deterministic_worsening 同口径）。返回 (known, value, flags)。"""
    if not r['post']:
        return True, False, ['给药前（不适用）']
    b = r.get('base')
    if not b:
        return True, True, ['基线缺失（按新发处理）']
    flags = []
    bg, cg = b.get('grade') or 0, r.get('grade') or 0
    if grade_up(bg, cg):                       # 0 级 → 1 级不单独算加重（须同时超出范围且同向较基线 ≥T_base，由下方数值规则判定；用户 2026-10-27 确认）
        flags.append(f"等级升高 {bg}→{cg} 级")
    if (r.get('clin') or 0) > (b.get('clin') or 0):
        flags.append('CS 新出现')
    v, bv = r.get('value'), b.get('value')
    if v is not None and bv not in (None, 0):
        hi, lo = ref_hi(r), r.get('lo')
        pct = (v - bv) / abs(bv)
        if hi is not None and v > hi and pct >= t_base:
            flags.append(f"较基线升高 {pct * 100:.0f}%")
        elif lo is not None and v < lo and -pct >= t_base:
            flags.append(f"较基线降低 {-pct * 100:.0f}%")
    if flags:
        return True, True, flags
    if v is not None:
        return True, False, []
    return False, None, ['文本型结果，恶化需据描述判断']


def _base_abn(r):
    b = r.get('base')
    if not b:
        return False
    if (b.get('clin') or 0) >= 1 or (b.get('grade') or 0) >= 1:
        return True
    v, lo, hi = b.get('value'), r.get('lo'), r.get('hi')
    if v is None:
        return False
    return (hi is not None and v > hi) or (lo is not None and v < lo)


def m23_csb(C):
    """步骤 1/1′/2/3/4 确定性 → 直接 query；其余 → 步骤 5 候选（交工作台 explain_cs）。"""
    t_base = float(C.cfg['thresholds'].get('base', 0.3))
    dp = (C.S.get('study') or {}).get('diseaseProgressionNotAE') or {}
    exempt = dp.get('confirmed') is True and str(dp.get('quote') or '').strip()
    handled = set()                                      # M01/M02 已产 query 或已判通过的 CS 行
    for g in C.labrows:
        if g['risk'] in ('CSX', 'MH', 'MHL', 'MHU', 'CSX_AE', 'AE', 'DIS', 'DISW', 'CSI'):
            for p in g['pts']:
                handled.add((g['sid'], p[7], p[8]))
    candidates, seen = [], set()
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.subj:
            continue
        for r in rows:
            if r.get('clin') != 2 or (sid, r['sheet'], r['row']) in handled or (sid, r['sheet'], r['row']) in seen:
                continue
            seen.add((sid, r['sheet'], r['row']))
            known, worse, flags = _worsening(r, t_base)
            binding = {'link': None, 'matched_ae': [], 'matched_mh': []}
            emit = None                                  # ('LINK'|'CSX_AE'|'MH'|'CSW'|'CSX', rec, extra)
            link = next((l for l in (r.get('links') or [])), None)
            if not link and disease_attr(C, r):
                # 用户 2026-10-27：归因研究疾病不算「未关联」。只有较基线明显加重（D14/D19，判定波动不算）且同期未见
                # 「研究疾病加重」类 AE 才作为风险；其余只作提示。方案进展条款已确认时交步骤 5 候选（D21）。
                wf = (worse_vs_base(r, r.get('base'), t_base) if r['post'] and r.get('base') else None) or (r['post'] and stated_worse(r))
                if not wf and r['post'] and r.get('value') is None and (r.get('base') or {}).get('clin') == 0:
                    wf = '基线正常，给药后新出现异常'           # 定性检查（体检/影像）：基线正常 → CS 视为明显异常；NCS→CS 判定波动不算
                if not wf or disease_ae(C, sid, mid, [r]):
                    continue
                if exempt:
                    candidates.append(_candidate(C, r, binding, known, worse, flags, disease_hint(C, mid) or '研究者归因研究疾病'))
                    continue
                _csb_query(C, r, 'CSW', None, f"并归因研究疾病，较基线明显加重（{wf}），但未记录研究疾病加重AE", flags)
                continue
            if link:
                pool = C.ae_by[sid] if link[0] == 'AE' else C.mh_by[sid]
                ev = next((x for x in pool if str(x['n']) == str(link[3])), None)
                if ev is None:                           # 步骤 1′：关联对象不存在
                    binding['link'] = {'type': link[0], 'no': link[3], 'term': link[1], 'exists': False, 'match': None}
                    page = '不良事件页' if link[0] == 'AE' else '病史页'
                    emit = ('LINK', {'type': link[0], 'no': link[3], 'term': link[1]},
                            f"，关联的{'AE' if link[0] == 'AE' else '病史'}编号 {link[3]} 在{page}中不存在")
                else:
                    # 对应性（noise 修正）：宿主预判 linkVerdicts（知识库：器官系统/方向/标本/时间）优先——
                    # implausible＝有正面反证 → LINK；plausible → 视同对应；unknown → 步骤 5 Q3。
                    # 无预判时词表命中 → 对应；词表未命中只说明词表未覆盖，不等于关联错误 → None（步骤 5），
                    # 仅 analysis.linkStrict=true 时沿用旧口径（未命中即 LINK）。
                    lv = (C.A.get('linkVerdicts') or {}).get(f"{r.get('wb') or ''}:{r['sheet']}|{r['row']}") or \
                         (C.A.get('linkVerdicts') or {}).get(f"{r['sheet']}|{r['row']}")
                    if lv:
                        match = {'implausible': False, 'plausible': True}.get(lv.get('v'))
                    else:
                        if link[0] == 'AE':
                            terms = [re.compile(b) for a, b, w in (C.A.get('aeMatch') or []) if re.compile(a).search(mid)]
                        else:
                            terms = [tre for mre, tre in C.mhMatch if mre.search(mid)]
                        hit = any(t.search(ev.get('t') or '') for t in terms) if terms else None
                        match = True if hit else (False if (hit is False and C.A.get('linkStrict')) else None)
                    binding['link'] = {'type': link[0], 'no': link[3], 'term': ev.get('t', ''), 'exists': True, 'match': match,
                                       'why': (lv or {}).get('why') or ''}
                    if match is False:                   # 词表确认不对应 → LINK
                        emit = ('LINK', {'type': link[0], 'no': link[3], 'term': ev.get('t', '')},
                                f"，关联的{'AE' if link[0] == 'AE' else '病史'}「{ev.get('t', '')}」与该异常不对应")
                    elif match is True:
                        if link[0] == 'AE':
                            continue                     # 步骤 1：关联 AE → 通过（等级一致性 M07 核）
                        if not r['post'] or (known and not worse):
                            continue                     # 关联病史、给药前或未恶化 → 通过
                        if known and worse:              # 给药后恶化 → MH 加重 query（研究疾病病史且已记录研究疾病加重 AE → 提示）
                            dz = disease_kw(C)
                            if dz and dz.search(ev.get('t') or '') and disease_ae(C, sid, mid, [r], dz):
                                continue
                            emit = ('MH', ev, None)
            if emit is None and not link:
                maes = []
                opp = opposite_dir([r])
                for mre, are, w in ae_match_rows(C, mid):   # 步骤 2：匹配 AE（方向相反的不算）
                    for a in C.ae_by[sid]:
                        if are.search(a['t']) and not opp.search(a['t']) and a.get('s') and r.get('date') and days(a['s'], r['date']) is not None \
                                and abs(days(a['s'], r['date'])) <= w:
                            maes.append({'no': a['n'], 'term': a['t'], 'start': a['s'], 'match': True})
                binding['matched_ae'] = maes[:4]
                if maes:
                    emit = ('CSX_AE', maes[0], None)
                else:
                    mmhs = []                            # 步骤 3：匹配 MH（时段覆盖）
                    for mre, tre in C.mhMatch:
                        if not mre.search(mid):
                            continue
                        for m in C.mh_by[sid]:
                            cover = (not m.get('start') or not r.get('date') or m['start'] <= r['date']) and \
                                    (m.get('ong') == '是' or not m.get('e') or not is_full_date(r['date']) or m['e'] >= r['date'])
                            if tre.search(m.get('t') or '') and cover:
                                mmhs.append({'no': m['n'], 'term': m['t'], 'start': m['s'], 'end': m['e'],
                                             'ongoing': m.get('ong') == '是', 'match': True})
                    binding['matched_mh'] = mmhs[:4]
                    if mmhs:
                        if not r['post'] or (known and not worse):
                            continue                     # 病史可解释 → 通过
                        if known and worse:
                            emit = ('CSW', mmhs[0], f"，病史有「{mmhs[0]['term']}」但给药后较基线加重，未见对应AE")
            dh = disease_hint(C, mid)
            if emit is None and not link and r['post'] and known and worse and not (exempt and dh) and not judgment_only(C, r, rows, t_base):
                emit = ('CSW' if _base_abn(r) else 'CSX', None, None)   # 步骤 4：确定性恶化直接 query（D19/D21）
            # 已关联且对象存在、对应性无法确定 → 步骤 5 候选（三问 Q3），不按「未关联」发 query（D002 QC：超声「其他异常」已关联病史/AE 曾被报 CS 未关联）
            if emit is not None:
                _csb_query(C, r, emit[0], emit[1], emit[2], flags)
            else:
                candidates.append(_candidate(C, r, binding, known, worse, flags, dh))
    return candidates


QT_CSB_ASK = {                                   # 写给 CRC：一句话建议
    'LINK': '请核实关联是否正确。',
    'CSX_AE': '请确认是否为同一事件并完成关联。',
    'MH': '请评估是否为给药后加重、需记录AE。',
    'CSW': '请评估是否需记录AE；如已记录，请完成关联。',
    'CSX': '请核实是否需记录AE，或补充病史并关联。',
}
CSB_PR = {'CSW': 4, 'CSX': 4, 'CSX_AE': 4, 'MH': 3, 'LINK': 3}
CSB_CAT = {'LINK': '关联的AE/病史不对应', 'CSX_AE': 'CS未关联·同期疑似AE', 'MH': 'CS仅关联病史·加重核对',
           'CSW': 'CS较基线加重·请确认AE', 'CSX': 'CS未关联AE/MH'}


def _obs(C, r):
    """检查结果的一句话描述：数值型「指标 数值单位」；体检/影像等定性记录用异常描述，不重复「异常有临床意义」字样。"""
    lab = C.metric[r['mid']]['label']
    if r.get('value') is not None:
        return f"{lab}{_val(_raw_or_val(r), r.get('unit'))}"
    raw, desc = str(r.get('raw') or ''), str(r.get('desc') or '').strip()
    if re.search(r'临床意义|^异常$|^正常$', raw):
        return f"{lab}异常" + (f"（{desc[:30]}{'…' if len(desc) > 30 else ''}）" if desc else '')
    return f"{lab}「{raw[:30]}」"


def _base_txt(r):
    b = r.get('base') or {}
    if b.get('value') is not None:
        return f"基线{_val(b.get('value'), b.get('unit') or r.get('unit'))}，"
    if b.get('clin') == 0 or re.search(r'^正常|未见异常', str(b.get('raw') or '')):
        return '基线正常，'
    return f"基线{str(b.get('raw'))[:20]}，" if b.get('raw') else ''


def _csb_query(C, r, kind, rec, extra, flags):
    head = f"{r.get('visit')}访视{_obs(C, r)}"
    if r.get('value') is not None and (r.get('base') or {}).get('value') is not None:
        bv, v = r['base']['value'], r['value']
        head = f"{r.get('visit')}访视{C.metric[r['mid']]['label']}{'升高至' if v > bv else '下降至' if v < bv else '为'}{_val(_raw_or_val(r), r.get('unit'))}"
    if kind == 'LINK':
        fact = f"{head}判定为CS{extra or ''}，"
    elif kind == 'CSX_AE':
        fact = f"{head}判定为CS，同期已记录AE「{(rec or {}).get('term', '')}」（{(rec or {}).get('start', '')}），但未关联，"
    elif kind == 'MH':
        fact = f"{_base_txt(r)}{head}判定为CS，仅关联病史「{(rec or {}).get('t', '')}」，较基线加重且未见对应AE，"
    elif kind == 'CSW':
        why = extra or ('（' + '、'.join(f for f in flags if not f.startswith('给药前'))[:40] + '）' if flags else '')
        fact = f"{_base_txt(r)}{head}判定为CS{why}，"
    else:
        fact = f"{_base_txt(r)}{head}判定为CS，但未关联AE或病史，"
    add_ext(C, r['sid'], CSB_CAT[kind], kind, CSB_PR[kind], fact.rstrip('，'),
            r.get('visit'), r.get('date'), r['sheet'], r['row'], C.metric[r['mid']]['label'],
            ctx=flags, rule={'ask': QT_CSB_ASK[kind]},
            bkey=f"{r['mid']}|{r.get('visit')}|{r.get('date')}", wb=r.get('wb') or '')


def _candidate(C, r, binding, known, worse, flags, dh):
    b = r.get('base')
    return {
        'ref': f"csb:{r['sid']}:{r['sheet']}:{r['row']}",
        'sid': r['sid'], 'domain': r['mid'].split(':')[0], 'test': r['mid'].split(':', 1)[1],
        'label': C.metric[r['mid']]['label'], 'visit': r.get('visit'), 'date': r.get('date'),
        'post': bool(r['post']), 'value': _raw_or_val(r) if r.get('value') is None else r.get('value'),
        'unit': r.get('unit'), 'lo': r.get('lo'), 'hi': r.get('hi'),
        'grade': r.get('grade'), 'gl': C.GL if r.get('grade') else None, 'clin': r.get('clin'), 'desc': r.get('desc') or '',
        'baseline': ({'visit': b.get('visit'), 'date': b.get('date'), 'value': b.get('value'),
                      'unit': b.get('unit'), 'grade': b.get('grade'), 'clin': b.get('clin'),
                      'desc': b.get('desc') or ''} if b else None),
        'worsening': {'known': known, 'value': worse, 'flags': flags},
        'binding': binding, 'disease_hint': dh, 'source': [r['sheet'], r['row']],
    }


# --------------------------------------------------------------------------- others 帮手
def add_ext(C, sid, cat, risk, pr, summ, v, d, sh, row, test='', rel=None, ctx=None, rule=None, bkey=None, wb=''):
    from mm_build import add_other        # 复用 mm_build 的 others 通道（qkey/时间线一致；延迟导入避免环）
    return add_other(C, sid, cat, pr, summ, v, d, sh, row, test, None, rel or [], ctx or [], risk,
                     {'id': risk, **(rule or {})}, None, None, bkey, wb)


def run(C):
    _load_lists(C)
    m13_mhx_t(C)
    m16_qual(C)
    m17_cm_ind(C)
    m18_preg(C)
    m19_ae_ex(C)
    m20_ae_sae(C)
    m21_ae_course(C)
    date_order(C)
    clin_consistency(C)
    cands = m23_csb(C)
    C.labrows.sort(key=lambda g: (-g['pr'], g['sid'], g['test']))
    return cands                                    # 词表未配置提示由 defaults() 追加到 todo（不覆盖默认待办）
