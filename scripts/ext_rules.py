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


_WEAK = re.compile(r'^[±]|弱阳|微量|trace', re.I)
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
    missing = [k for k, v in (('mhMatch', C.mhMatch), ('cmIndicationMap', C.cmInd), ('indicationBackground', C.indBg)) if not v]
    if missing:
        C.todo_hint = (f"词表未配置：{'、'.join(missing)}"
                       "（M13 病史漏记、M17 用药适应症、CSB 研究疾病线索 未启用——对应规则零命中，不猜医学对应关系）")


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
        wb = ((C.src.get('sheets') or {}).get(worst.get('sheet')) or {}).get('wb', '')
        wbs = f"{wb}:{worst['sheet']}" if wb else (worst.get('sheet') or '')
        C.labrows.append({
            'sid': sid, 'site': C.subj[sid]['site'], 'cat': '疑似病史漏记（首剂前偏离）', 'test': C.metric[mid]['label'], 'mid': mid,
            'grp': pre[0].get('group') or '', 'pr': 2,
            'base': [b.get('visit'), b.get('raw'), b.get('unit') or '', b.get('clin')] if b else None,
            'pts': [[r.get('visit'), r.get('date'), r.get('raw'), r.get('unit') or '', r.get('grade'), r.get('clin'),
                     None if r.get('pct') is None else round(r['pct'], 1), r['sheet'], r['row'], r.get('desc') or '',
                     None if r.get('dev') is None else round(r['dev'], 4)] for r in pre],
            'rel': [], 'ctx': ctx or ['首剂前偏离且病史未记录；CS 部分由 M23 核查绑定'],
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
                        ctx=['弱阳性最高提示（pr1）；研究者判 CS 者走 M01'],
                        rule={'ask': '请结合复测与临床判断是否需关注。'}, bkey=f"{mid}|{r.get('visit')}|{r.get('date')}")
            elif lv == 2 and base_lv == 0 and (r.get('clin') or 0) != 2:
                add_ext(C, sid, '定性结果核对', 'M16-NEW', 3,
                        f"{r.get('visit')}（{r.get('date')}）{test}「{r.get('raw')}」，该指标基线（首剂前最近一次）为阴性",
                        r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                        ctx=['定性新发异常（基线阴性 → ≥+）；判 CS 者由 M01/M23 分层'],
                        rule={'ask': '请评估该新发定性异常的临床意义，必要时复测。'}, bkey=f"{mid}|{r.get('visit')}|{r.get('date')}")


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
                    rule={'ask': '请确认是否需补充记录。'}, bkey=f"{c.get('n') or c['t']}|{c['s']}")


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
                    bkey=f"{mid}|{r.get('visit')}|{r.get('date')}")


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
                    rule={'ask': '请核实并补充或更正。'}, bkey=f"{e.get('start')}|{why}")
        for a in C.ae_by[sid]:                          # ② AE 措施=停药/暂停但给药记录无中断
            if not act_re.search(str(a.get('act') or '')):
                continue
            if any(act_re.search(str(e.get('pause') or '')) and near(e.get('start'), a.get('s')) for e in exp):
                continue
            add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                    f"AE「{a['t']}」（{a['s']}）采取措施「{a['act']}」，给药记录未见同期（±{w} 天）中断/暂停",
                    None, a['s'], a['sh'], a['row'], a['t'],
                    rule={'ask': '请核实给药记录与 AE 措施是否一致。'}, bkey=f"{a.get('n')}|{a['s']}")


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
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}")
        elif (not a['sae']) and crit.strip():
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」（{a['s']}）勾选了 SAE 标准（{crit}），但 SAE=否",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}")
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
                    rule={'ask': '请核实死亡日期与研究结束信息。'}, bkey=f"{a.get('n')}|死亡日期")
        later = [x.get('start') for x in C.exposure if x['sid'] == sid and is_full_date(x.get('start')) and x['start'] > d]
        later += [x.get('date') for x in C.visits if x['sid'] == sid and is_full_date(x.get('date')) and x['date'] > d]
        later += [r.get('date') for (s2, mid), rs in C.F.items() if s2 == sid for r in rs
                  if is_full_date(r.get('date')) and r['date'] > d]
        if later:
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」转归「死亡」（{d}），其后仍有给药/访视/检验记录：{'、'.join(sorted(set(later))[:4])}",
                    None, d, a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实死亡日期或后续记录。'}, bkey=f"{a.get('n')}|死亡后活动")


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
                        ctx=['检验走势与 AE 转归不一致（pr2 提示，可转 query）'],
                        rule={'query': False, 'ask': '请评估是否需更新 AE 转归或补充随访检验。'},
                        bkey=f"{a.get('n')}|{C.metric[w0['mid']]['label']}")
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
                        ctx=['异常未恢复且 AE 未结束（pr2 提示）'],
                        rule={'query': False, 'ask': '请确认随访安排或更新 AE 转归。'},
                        bkey=f"{a.get('n')}|{C.metric[r0['mid']]['label']}|未恢复")


# --------------------------------------------------------------------------- 日期序（S45 收口，D-P5-14）
def date_order(C):
    def bad(s, e):
        return is_full_date(s) and is_full_date(e) and s > e

    for a in C.aes:
        if a['sid'] in C.pop and bad(a.get('s'), a.get('e')):
            add_ext(C, a['sid'], '日期完整性核对', 'DATEORD', 3,
                    f"AE「{a['t']}」开始日期 {a['s']} 晚于结束日期 {a['e']}",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实并更正起止日期。'}, bkey=f"{a.get('n')}|{a['s']}|{a['e']}")
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
                    rule={'ask': '请核实并更正起止日期。'}, bkey=f"{e['start']}|{e['end']}")


# --------------------------------------------------------------------------- M23 CSB 确定性＋候选
def _worsening(r, t_base):
    """步骤 4 确定性恶化（与 review/csb.py deterministic_worsening 同口径）。返回 (known, value, flags)。"""
    if not r['post']:
        return True, False, ['给药前（不适用）']
    b = r.get('base')
    if not b:
        return True, True, ['基线缺失（按新发处理）']
    flags = []
    bg, cg = b.get('grade') or 0, r.get('grade') or 0
    if cg > bg:
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
        if g['risk'] in ('CSX', 'MH', 'CSX_AE', 'AE'):
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
            if link:
                pool = C.ae_by[sid] if link[0] == 'AE' else C.mh_by[sid]
                ev = next((x for x in pool if str(x['n']) == str(link[3])), None)
                if ev is None:                           # 步骤 1′：关联对象不存在
                    binding['link'] = {'type': link[0], 'no': link[3], 'term': link[1], 'exists': False, 'match': None}
                    page = '不良事件页' if link[0] == 'AE' else '病史页'
                    emit = ('LINK', {'type': link[0], 'no': link[3], 'term': link[1]},
                            f"，关联字段为 {link[3]}，{page}未见该编号记录")
                else:
                    # 对应性：词表有该指标的条目 → 术语是否在其中（True/False）；无条目 → None（无法判断，步骤 5 Q3）
                    if link[0] == 'AE':
                        terms = [re.compile(b) for a, b, w in (C.A.get('aeMatch') or []) if re.compile(a).search(mid)]
                    else:
                        terms = [tre for mre, tre in C.mhMatch if mre.search(mid)]
                    match = (any(t.search(ev.get('t') or '') for t in terms) if terms else None)
                    binding['link'] = {'type': link[0], 'no': link[3], 'term': ev.get('t', ''), 'exists': True, 'match': match}
                    if match is False:                   # 词表确认不对应 → LINK
                        emit = ('LINK', {'type': link[0], 'no': link[3], 'term': ev.get('t', '')},
                                f"，关联{'不良事件' if link[0] == 'AE' else '病史'} {link[3]}「{ev.get('t', '')}」")
                    elif match is True:
                        if link[0] == 'AE':
                            continue                     # 步骤 1：关联 AE → 通过（等级一致性 M07 核）
                        if not r['post'] or (known and not worse):
                            continue                     # 关联病史、给药前或未恶化 → 通过
                        if known and worse:              # 给药后恶化 → MH 加重 query
                            emit = ('MH', ev, None)
            if emit is None and not link:
                maes = []
                for mre, are, w in ae_match_rows(C, mid):   # 步骤 2：匹配 AE
                    for a in C.ae_by[sid]:
                        if are.search(a['t']) and a.get('s') and r.get('date') and days(a['s'], r['date']) is not None \
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
                            emit = ('CSW', mmhs[0], f"；病史 {mmhs[0]['no']}「{mmhs[0]['term']}」存在，但给药后较基线恶化")
            dh = disease_hint(C, mid)
            if emit is None and r['post'] and known and worse and not (exempt and dh):
                emit = ('CSW' if _base_abn(r) else 'CSX', None, None)   # 步骤 4：确定性恶化直接 query（D19/D21）
            if emit is not None:
                _csb_query(C, r, emit[0], emit[1], emit[2], flags)
            else:
                candidates.append(_candidate(C, r, binding, known, worse, flags, dh))
    return candidates


QT_CSB_ASK = {
    'LINK': '请核实关联是否正确。',
    'CSX_AE': ('请确认两者是否为同一事件；如是，请在该记录的关联字段中关联该 AE（如表单无关联字段，'
               '请在异常描述中注明 AE 编号）；如否，请评估是否需另行记录不良事件。'),
    'MH': '请评估给药后是否较基线加重；如属加重，请记录为不良事件并关联。',
    'CSW': '请确认是否需记录为不良事件；如已记录，请完成关联。',
    'CSX': ('请核实该异常是否应记录为不良事件；如判断为既往疾病延续，请在病史中补充并关联；'
            '如判定有误请更正临床意义评价。'),
}
CSB_PR = {'CSW': 4, 'CSX': 4, 'CSX_AE': 4, 'MH': 3, 'LINK': 3}
CSB_CAT = {'LINK': '关联不对应（CSB）', 'CSX_AE': 'CS未关联·同期疑似AE', 'MH': 'CS仅关联病史·加重核对',
           'CSW': 'CS较基线加重·请确认AE', 'CSX': 'CS未关联AE/MH'}


def _csb_query(C, r, kind, rec, extra, flags):
    cs = '研究者判定「异常有临床意义」'
    if kind == 'MH':
        b = r.get('base') or {}
        fact = (f"{r.get('visit')}（{r.get('date')}）{C.metric[r['mid']]['label']} "
                f"{_val(_raw_or_val(r), r.get('unit'))}，{cs}，仅关联病史「{(rec or {}).get('t', '')}」；"
                f"基线（{b.get('visit', '')}）为 {_val(b.get('value'), b.get('unit') or r.get('unit'))}。")
    else:
        head = _head(C, r)
        if kind == 'LINK':
            fact = f"{head}，{cs}{extra or ''}。"
        elif kind == 'CSX_AE':
            fact = f"{head}，{cs}；同期已记录 AE「{(rec or {}).get('term', '')}」（{(rec or {}).get('start', '')}），但该检查记录未关联。"
        else:
            b = r.get('base')
            if b and (b.get('value') is not None or b.get('raw')):
                base_txt = f"；基线 {b.get('visit')}（{b.get('date')}）{_val(b.get('value') if b.get('value') is not None else b.get('raw'), b.get('unit') or r.get('unit'))}"
            elif kind == 'CSW':
                base_txt = '；基线未见有效记录'
            else:
                base_txt = ''
            fact = f"{head}，{cs}{extra or ''}{base_txt}。"
    add_ext(C, r['sid'], CSB_CAT[kind], kind, CSB_PR[kind], fact.rstrip('。'),
            r.get('visit'), r.get('date'), r['sheet'], r['row'], C.metric[r['mid']]['label'],
            ctx=flags, rule={'ask': QT_CSB_ASK[kind]},
            bkey=f"{r['mid']}|{r.get('visit')}|{r.get('date')}")


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
def add_ext(C, sid, cat, risk, pr, summ, v, d, sh, row, test='', rel=None, ctx=None, rule=None, bkey=None):
    from mm_build import add_other        # 复用 mm_build 的 others 通道（qkey/时间线一致；延迟导入避免环）
    return add_other(C, sid, cat, pr, summ, v, d, sh, row, test, None, rel or [], ctx or [], risk,
                     {'id': risk, **(rule or {})}, None, None, bkey)


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
    cands = m23_csb(C)
    C.labrows.sort(key=lambda g: (-g['pr'], g['sid'], g['test']))
    return cands                                    # 词表未配置提示由 defaults() 追加到 todo（不覆盖默认待办）
