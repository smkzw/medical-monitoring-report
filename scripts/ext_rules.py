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

from common import days, dshow, fmt, is_dosing, is_full_date, move_word

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
    return f"{r.get('visit', '')}（{dshow(r.get('date'))}）{C.metric[r['mid']]['label']} {_val(_raw_or_val(r), r.get('unit'))}{rng}"


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


_DOM_AE = {   # V6（MM/CRA 审阅 2026-11-02）：心电图/生命体征整份判定（「总体评价」行）没有指标级 aeMatch → 按域给 AE 术语族
    'ecg': r'心电图|心律|心率|心动|窦性|QT|PR间期|QRS|传导|阻滞|ST段|T波|ST-T|早搏|期前收缩|房颤|房扑|心肌',
    'vs': r'血压|高血压|低血压|心率|心动|发热|体温|呼吸|脉搏',
}


# V6（MM 审阅 2026-11-02：AE/MH 同义词未用——ALT 备注「肝酶升高AE」、D002 红细胞指数类质疑 16/35 有贫血病史）：
# 检验指标族 ↔ AE/病史术语族（医学常识层，项目 aeMatch/mhMatch 优先；只用于「同期疑似对应 / 病史可解释」判断与同事件比对）
LAB_EVENT_FAMILY = [
    (r'ALT|AST|GGT|ALP|转氨酶|转肽酶|碱性磷酸酶|胆红素|TBIL|DBIL', r'肝|转氨酶|胆红素|黄疸|胆汁淤积'),
    (r'血红蛋白|Hb\b|HGB|红细胞(计数|压积)|RBC|HCT|MCV|MCH|红细胞体积|红细胞血红蛋白|网织红|铁蛋白|血清铁|转铁', r'贫血|血红蛋白|缺铁|失血|出血'),
    (r'中性粒|NEUT|ANC|白细胞计数|WBC|粒细胞', r'中性粒|白细胞|粒细胞|骨髓抑制'),
    (r'淋巴细胞', r'淋巴细胞'),
    (r'血小板|PLT', r'血小板'),
    (r'嗜酸', r'嗜酸'),
    (r'肌酐|Cr\b|CREA|尿素|BUN|eGFR|肾小球滤过', r'肾|肌酐|尿素'),
    (r'肌酸激酶|CK\b|CPK|肌红蛋白', r'肌酸激酶|CK|横纹肌|肌炎|肌痛|肌损伤'),
    (r'葡萄糖|血糖|GLU|HbA1c|糖化', r'血糖|糖尿病|糖耐量'),
    (r'甘油三酯|TG\b|胆固醇|CHOL|LDL|HDL', r'血脂|脂血症|甘油三酯|胆固醇'),
    (r'钾|(?<![A-Za-z])K\b', r'钾'), (r'钠|(?<![A-Za-z])Na\b', r'钠'), (r'钙|(?<![A-Za-z])Ca\b', r'钙'), (r'镁', r'镁'),   # 不让「CK」「HbA1c」误入
    (r'淀粉酶|脂肪酶', r'胰|淀粉酶|脂肪酶'),
    (r'尿酸', r'尿酸|痛风'),
    (r'尿蛋白', r'蛋白尿|肾'), (r'尿潜血|尿红细胞|隐血', r'血尿'), (r'尿白细胞|白细胞酯酶', r'尿路感染|泌尿'),
    (r'TSH|FT3|FT4|甲状腺', r'甲状腺'),
    (r'QT', r'QT'), (r'骨密度', r'骨量|骨密度|骨质疏松'),
    (r'收缩压|舒张压|血压', r'血压'), (r'心率|脉搏', r'心动|心率'), (r'体温', r'发热|体温'), (r'体重', r'体重'),
]


def family_terms(mid):
    """指标 → AE/病史术语族正则列表（按指标名命中）。"""
    lab = str(mid).split(':', 1)[-1]
    return [re.compile(e) for l, e in LAB_EVENT_FAMILY if re.search(l, lab, re.I)]


def ae_match_rows(C, mid):
    rows = [(re.compile(a), re.compile(b), w) for a, b, w in (C.A.get('aeMatch') or []) if re.search(a, mid)]
    dom = str(mid).split(':')[0]
    if not rows and dom in _DOM_AE and '总体评价' in str(mid):
        rows = [(re.compile('.'), re.compile(_DOM_AE[dom]), 0)]
    if not rows:
        rows = [(re.compile('.'), e, 0) for e in family_terms(mid)]
    return rows


def desc_ae_match(C, sid, r):
    """研究者描述（「窦性心动过缓」「ST-T 改变」）与同期 AE 术语互相包含 → 视为同期疑似对应（只用于提示关联，不自动关联）。"""
    d = re.sub(r'\s', '', str(r.get('desc') or (r.get('raw') if r.get('value') is None else '') or ''))
    if len(d) < 2 or not is_full_date(r.get('date')):
        return []
    out = []
    for a in C.ae_by[sid]:
        t_ = re.sub(r'[（(].*$', '', str(a.get('t') or '')).strip()
        if len(t_) >= 2 and (t_ in d or (len(d) <= 12 and d in t_)) and ae_covers(a, r['date']):
            out.append({'no': a['n'], 'term': a['t'], 'start': a['s'], 'match': True})
    return out


_SPECIMEN = re.compile(r'鼻(分泌物|涂片|黏膜|拭子)?|痰|尿|粪|大便|脑脊液|关节液|胸水|腹水|皮损|阴道分泌物|白带')


def bg_applies(note, mid, sheet=''):
    """V6（MM 审阅：SAR 外周血嗜酸性粒细胞 33 条套用「可见于鼻分泌物涂片嗜酸性粒细胞增多」）：
    研究疾病背景写明了标本（鼻涂片/痰/尿…）时，只套用到同标本的指标；指标名与表单名都不含该标本 → 不适用。"""
    sp = {m.group(0)[:1] if m.group(0).startswith('鼻') else m.group(0) for m in _SPECIMEN.finditer(str(note or ''))}
    if not sp:
        return True
    where = f"{mid}|{sheet}"
    return any(s in where for s in sp)


def disease_hint(C, mid, sheet=''):
    for mre, note in C.indBg:
        if mre.search(mid) and bg_applies(note, mid, sheet):
            return note or '研究疾病常见表现'
    return None


# --------------------------------------------------------------------------- M13 MHX-T
PROTECTIVE_AB = re.compile(r'表面抗体|HBsAb|抗-?HBs(?!Ag)|anti-?HBs(?!Ag)', re.I)


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
        if PROTECTIVE_AB.search(C.metric[mid]['label']):     # 保护性抗体阳性＝免疫（接种/既往感染已愈），不是需记病史的异常（E2E 第 6 轮 RUX：HBsAb 阳性被提示病史漏记）
            continue
        dev_t = float((thr.get('per_metric') or {}).get(mid, {}).get('dev', thr['dev']))
        for T in C.mthr:
            if T.get('metric') and re.search(T['metric'], mid) and T.get('dev') is not None:
                dev_t = min(dev_t, float(T['dev']))
        floor = min(0.20, dev_t)
        d_ = metric_dir(mid)
        pre = [r for r in rows
               if not r['post'] and r.get('clin') in (1, None)
               and not (d_ == 'up' and r.get('value') is not None and r.get('lo') is not None and r['value'] < r['lo'])
               and not (d_ == 'down' and r.get('value') is not None and ref_hi(r) is not None and r['value'] > ref_hi(r))
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
            ctx.append(f"有对应用药：{cm_hit[0]['t']}（{dshow(cm_hit[0].get('s'))} 起，用药原因「{cm_hit[0]['why']}」）")
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
    """定性结果：弱阳性提示（M16）、基线阴性后新发阳性（M16-NEW）。
    V6 R8（审阅者 2026-11-02）：同受试者同指标同类情况按访视逐条拆单 → 合并为一条（首次为证据，其余访视进上下文）。"""
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop or _PREG.search(mid) or all(r.get('value') is not None for r in rows):
            continue                                   # 只看定性（无数值）指标；妊娠类定性由 M18 处理
        pre_lv = [qual_level(r.get('raw')) for r in rows if not r['post']]
        base_lv = next((x for x in reversed(pre_lv) if x is not None), 0)
        test = C.metric[mid]['label']
        weak, new = [], []
        for r in rows:
            if not r['post']:
                continue
            lv = qual_level(r.get('raw'))
            if lv is None:
                continue
            if lv == 1 and (r.get('clin') or 0) != 2:
                weak.append(r)
            elif lv == 2 and base_lv == 0 and (r.get('clin') or 0) != 2:
                new.append(r)

        def more(rs):
            return [f"另有 {len(rs) - 1} 次：" + '、'.join(f"{x.get('visit')}（{x.get('date')}）「{x.get('raw')}」" for x in rs[1:5])
                    + ('…' if len(rs) > 5 else '')] if len(rs) > 1 else []
        if weak:
            r = weak[0]
            add_ext(C, sid, '定性结果核对', 'M16', 1,
                    f"{r.get('visit')}（{r.get('date')}）{test}「{r.get('raw')}」（±/弱阳性/微量）" + (f"，共 {len(weak)} 次" if len(weak) > 1 else ''),
                    r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                    ctx=['弱阳性，仅作提示（研究者判为有临床意义的另按「CS 未关联」核查）'] + more(weak),
                    rule={'ask': '请结合复测与临床判断是否需关注。'}, bkey=f"{mid}|weak", wb=r.get('wb') or '')
        if new:
            # 研究者判定优先：已评价为正常/NCS 的新发定性异常只作提示（pr1，不发 query）；有未评价的才请研究者评价（pr3）
            un = [x for x in new if x.get('clin') not in (0, 1)]
            r = (un or new)[0]
            assessed = not un
            add_ext(C, sid, '定性结果核对', 'M16-NEW', 1 if assessed else 3,
                    f"{r.get('visit')}（{r.get('date')}）{test}「{r.get('raw')}」，该指标基线（首剂前最近一次）为阴性"
                    + (f"，给药后共 {len(new)} 次阳性" if len(new) > 1 else ''),
                    r.get('visit'), r.get('date'), r['sheet'], r['row'], test,
                    ctx=['定性结果新出现阳性（基线阴性 → ≥+）'] + more([r] + [x for x in new if x is not r]) +
                        (['研究者已评价为' + ('正常' if r.get('clin') == 0 else '异常无临床意义') + '（研究者判定优先，仅提示）'] if assessed else []),
                    rule={'ask': '请评估该新发定性异常的临床意义，必要时复测。'}, bkey=f"{mid}|new", wb=r.get('wb') or '')


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
                    f"合并用药「{c['t']}」（{dshow(c.get('s'))} 起，用药原因「{why}」），{where}均未见「{why}」相关记录",
                    None, c['s'], c['sh'], c['row'], c['t'],
                    ctx=['首剂前开始 → 核对病史' if ask_hist else '首剂后开始 → 核对不良事件'],
                    rule={'ask': '请确认是否需补充记录。'}, bkey=f"{c.get('n') or c['t']}|{c['s']}", wb=c.get('wb') or '')


# --------------------------------------------------------------------------- M18 PREG
_PREG_RANGE_RX = re.compile(r'(?:非孕|未孕|早孕|孕早|中孕|孕中|晚孕|孕晚|绝经)期?\s*[:：]?\s*[<>≤≥]?\s*\d|参考(?:区间|范围|值)', re.I)
_NEG_RX = re.compile(r'阴性|未见|未孕|非孕|否认|无妊娠|negative', re.I)


def m18_preg(C):
    """F-I（PREG-ESCALATION）：妊娠暴露升级为专项核查。证据源两路：
    ① 妊娠类定性指标（检查名含 妊娠/怀孕/HCG/pregn）阳性（CS／「阳」／超上限）；
    ② 影像/描述性发现（妇科超声等）原文或描述含 宫内(早)孕/早孕/妊娠囊/宫内妊娠/怀孕。
    同一受试者合并为一条 pr4「妊娠暴露核查」——妊娠暴露属必须优先追踪的安全性事项（结局随访、避孕依从核查），
    不逐条发常规 CS 质疑；阴性/未孕结果不触发。"""
    pre = re.compile(r'妊娠|怀孕|hcg|pregn', re.I)
    desc_pre = re.compile(r'宫内(?:早)?孕|早孕|妊娠囊|宫内妊娠|怀孕|pregnan', re.I)
    by_sub, pre_dose = {}, {}
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop:
            continue
        test = (C.metric.get(mid) or {}).get('label') or mid
        fd = (C.subj.get(sid) or {}).get('fd')
        for r in rows:
            raw = str(r.get('raw') or '')
            pos = bool(pre.search(mid)) and ((r.get('clin') == 2) or (bool(raw) and bool(re.search(r'阳', raw)) and not _NEG_RX.search(raw)) or
                                             (r.get('value') is not None and r.get('hi') is not None and r['value'] > r['hi']))
            txt = ' '.join(str(r.get(k) or '') for k in ('raw', 'desc'))
            scan = bool(desc_pre.search(txt)) and not _PREG_RANGE_RX.search(txt) and not _NEG_RX.search(txt) \
                and (bool(pre.search(mid)) or mid.split(':')[0] not in ('lab', 'vs', 'ecg'))   # V6（CRA）：血常规行的备注不作妊娠证据
            if not (pos or scan):
                continue
            # V6 R1：首剂前（筛选期）阳性属入排问题，不是研究期间妊娠暴露；日期不全的仍按研究期间（保守，不漏）
            d = r.get('date')
            tgt = pre_dose if is_full_date(d) and is_full_date(fd) and d < fd else by_sub
            tgt.setdefault(sid, []).append((test, r, pos))
    for sid, ev in sorted(by_sub.items()):
        r0 = min((r for _, r, _ in ev), key=lambda r: str(r.get('date') or '9999'))
        evs = '；'.join(f"{t}「{str(r.get('raw') or r.get('value') or '')[:24]}」（{dshow(r.get('date'))}）"
                        for t, r, _ in ev[:4])
        o = add_ext(C, sid, '妊娠暴露核查', 'M18', 4,
                    f"研究期间发现妊娠证据：{evs}{'…' if len(ev) > 4 else ''}。妊娠暴露须优先追踪（结局随访、避孕依从核查）",
                    r0.get('visit'), r0.get('date'), r0['sheet'], r0['row'], '妊娠',
                    rule={'ask': '请确认是否为妊娠事件，并按方案要求完成妊娠报告、结局随访与避孕依从核查；如为误录，请更正。'},
                    bkey=f"preg|{sid}", wb=r0.get('wb') or '')
        # 结构化阳性（妊娠检验阳性）才可作停药触发证据（IP-02）；仅描述文本命中的只作核查，不级联判偏离
        st = [r for _, r, p_ in ev if p_ and is_full_date(r.get('date'))]
        if isinstance(o, dict) and st:
            o['_preg_pos'] = min(r['date'] for r in st)
    for sid, ev in sorted(pre_dose.items()):
        r0 = min((r for _, r, _ in ev), key=lambda r: str(r.get('date') or '9999'))
        add_ext(C, sid, '入排标准核对', 'M18', 3,
                f"首剂前妊娠检测/描述提示阳性：{ev[0][0]}「{str(r0.get('raw') or r0.get('value') or '')[:24]}」（{dshow(r0.get('date'))}），"
                f"首剂 {dshow((C.subj.get(sid) or {}).get('fd'))}",
                r0.get('visit'), r0.get('date'), r0['sheet'], r0['row'], '妊娠',
                rule={'ask': '首剂前妊娠检测结果提示阳性，请核实受试者是否符合入组标准、是否已复测排除；如为误录，请更正。'},
                bkey=f"preg-pre|{sid}", wb=r0.get('wb') or '')


# --------------------------------------------------------------------------- M19 AE-EX
def m19_ae_ex(C):
    w = C.A.get('aeExWindow', 7)
    ae_re = re.compile(r'不良事件|AE')
    act_re = re.compile(r'暂停|停药|停用|中断|pause|stop|hold', re.I)

    def near(d1, d2):
        return d1 and d2 and days(d1, d2) is not None and abs(days(d1, d2)) <= w

    # V6（CRA 审阅 2026-11-02）：给药数据只有发药/回收时间戳（无结束日、暂停原因、实际剂量）时测不出中断 → 不做 ②（改由 CRA 核日记卡）
    rich = sum(1 for e in C.exposure if e.get('end') or e.get('pause') or e.get('dose_act') not in (None, ''))
    assessable = not C.exposure or rich / len(C.exposure) >= 0.2      # RUX：31137 条中仅 13 条有结束日 → 不可测
    for sid in sorted(C.pop):
        exp = [e for e in C.exposure if e['sid'] == sid]
        for e in exp:                                   # ① 给药中断（原因=不良事件）±w 天无对应措施的 AE
            why = str(e.get('pause') or '')
            if not act_re.search(why) or not ae_re.search(why):
                continue
            if any(act_re.search(str(a.get('act') or '')) and near(a.get('s'), e.get('start')) for a in C.ae_by[sid]):
                continue
            add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                    f"给药记录 {e.get('visit') or ''}（{dshow(e.get('start'))}）「{why}」，不良事件页未见同期（±{w} 天）采取措施为暂停/停药的记录",
                    e.get('visit'), e.get('start'), e.get('sheet', ''), e.get('row'), '',
                    rule={'ask': '请核实并补充或更正。'}, bkey=f"{e.get('start')}|{why}", wb=e.get('wb') or '')
        # 给药记录里的「中断」：暂停原因文本、剂量为 0 的给药区间、相邻区间之间的空档；永久停药看末次给药日期
        stops = [e.get('start') for e in exp if act_re.search(str(e.get('pause') or '')) or
                 any(str(e.get(k)).strip() in ('0', '0.0') for k in ('dose_act', 'qty') if e.get(k) not in (None, ''))]
        iv = sorted((e['start'], e.get('end') or e['start']) for e in exp if is_full_date(e.get('start')) and is_dosing(e))   # 暂停区间不是给药区间（不能填平空档）
        stops += [prev[1] for prev, nxt in zip(iv, iv[1:]) if is_full_date(prev[1]) and (days(nxt[0], prev[1]) or 0) > 1]
        last = max((x[1] for x in iv if is_full_date(x[1])), default=None)
        for a in C.ae_by[sid]:                          # ② AE 措施=停药/暂停但给药记录无中断
            if a.get('dup') or not act_re.search(str(a.get('act') or '')):   # F08：重复记录成员不逐条发（组首覆盖）
                continue
            if re.search(r'永久', str(a.get('act'))) and is_full_date(a.get('s')):
                later = sorted(e['start'] for e in exp if is_full_date(e.get('start')) and (days(e['start'], a['s']) or 0) > w)
                if later:                               # V6（CRA）：永久停药后又恢复给药——点出真正的矛盾
                    add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                            f"AE「{a['t']}」（{dshow(a.get('s'))}）采取措施「{a['act']}」，但给药记录显示其后仍有给药（{dshow(later[0])} 起）",
                            None, a['s'], a['sh'], a['row'], a['t'],
                            rule={'ask': '请核实 AE 措施与给药记录：是否为永久停药，或给药记录有误。'}, bkey=f"{a.get('n')}|{a['s']}|resume", wb=a.get('wb') or '')
                    continue
            if not assessable:
                continue
            if any(near(d, a.get('s')) for d in stops) or (re.search(r'永久|停药|停用', str(a.get('act'))) and near(last, a.get('s'))):
                continue
            add_ext(C, sid, 'AE与给药记录一致性核对', 'M19', 3,
                    f"AE「{a['t']}」（{dshow(a.get('s'))}）采取措施「{a['act']}」，给药记录未见同期（±{w} 天）中断/暂停",
                    None, a['s'], a['sh'], a['row'], a['t'],
                    rule={'ask': '请核实给药记录与 AE 措施是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')


# --------------------------------------------------------------------------- M20 AE-SAE
def m20_ae_sae(C):
    for a in C.aes:
        sid = a['sid']
        if sid not in C.pop or a.get('dup'):      # F08：重复记录成员不逐条发（组首覆盖）
            continue
        crit = str(a.get('sae_crit') or '')
        if a['sae'] and not crit.strip():
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」（{dshow(a['s'])}）SAE=是，但 SAE 标准（致死/危及生命/住院/致残/先天异常/其他重要事件）均未勾选",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')
        elif (not a['sae']) and crit.strip():
            add_ext(C, sid, 'SAE与死亡一致性核对', 'M20', 4,
                    f"AE「{a['t']}」（{dshow(a['s'])}）勾选了 SAE 标准（{crit}），但 SAE=否",
                    None, a['s'], a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请核实 SAE 判定与标准勾选是否一致。'}, bkey=f"{a.get('n')}|{a['s']}", wb=a.get('wb') or '')
    deaths = {}
    for a in C.aes:
        if a['sid'] in C.pop and not a.get('dup') and re.search(r'死亡', str(a.get('out') or '')):
            deaths.setdefault(a['sid'], []).append(a)
    for sid, lst in deaths.items():
        a = min(lst, key=lambda x: (x.get('e') or x.get('s') or '9999'))
        d = a.get('e') or a.get('s')
        if not d:                                       # 死亡日期缺失：无法定义「其后」，不比对（避免空日期产生全量假「其后仍有记录」）
            continue
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
                dn = daily_open(C, sid)                  # 用户 2026-10-28：未出组的受试者在日常阶段降级为提示
                add_ext(C, sid, 'AE转归与检验走势核对', 'M21', 1 if dn else 2,
                        f"AE「{a['t']}」（{dshow(a['s'])} 起，未结束），末次访视（{last_d or '—'}）关联检验 "
                        f"{C.metric[r0['mid']]['label']} 仍异常、未见随访安排",
                        None, last_d, a['sh'], a['row'], C.metric[r0['mid']]['label'],
                        rel=[['AE', a['t'], a['s'], a['n']]],
                        ctx=['异常未恢复且 AE 未结束（提示）'] + ([DAILY_NOTE] if dn else []),
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
        if a['sid'] in C.pop and a.get('te_pending'):
            from mm_build import partial_date
            sd = '缺失' if not a.get('s') else (f"「{str(a['s'])[:12]}」只精确到{'月' if len(partial_date(a['s'])) == 7 else '年'}，与首剂（{a.get('fd')}）同期"
                                                if partial_date(a['s']) else '「' + str(a['s'])[:12] + '」无法解析')
            add_ext(C, a['sid'], '日期完整性核对', 'DATEORD', 3,
                    f"AE「{a['t']}」开始日期{sd}，无法判定是否为治疗期出现（TEAE，暂按 TEAE 计）",
                    None, None, a['sh'], a['row'], a['t'], rel=[['AE', a['t'], a['s'], a['n']]],
                    rule={'ask': '请补充或更正该 AE 的开始日期。'}, bkey=f"{a.get('n')}|start-unk", wb=a.get('wb') or '')
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
# 指标的不利方向（医学常识默认表；study.json analysis.metricDir 优先）。未列出的指标两个方向都算（血红蛋白、血小板、白细胞、电解质、体重等）
DIR_DEFAULT = [
    (r'高密度脂蛋白|HDL|白蛋白|ALB(?![A-Za-z])|总蛋白|前白蛋白|肾小球滤过|eGFR|网织红细胞血红蛋白', 'down'),
    (r'丙氨酸氨基转移酶|ALT(?![A-Za-z])|天门?冬氨酸氨基转移酶|AST(?![A-Za-z])|谷氨酰转[移肽]酶|GGT|碱性磷酸酶|ALP(?![A-Za-z])|胆红素|BIL(?![A-Za-z])|'
     r'肌酐|CREA|Cr(?![A-Za-z])|尿素|BUN|尿酸|甘油三酯|TG(?![A-Za-z])|总胆固醇|TC(?![A-Za-z])|低密度脂蛋白|LDL|肌酸激酶|肌酸磷酸激酶|CK(?![A-Za-z])|CPK|'
     r'乳酸脱氢酶|LDH|葡萄糖|GLU|糖化血红蛋白|HbA1c|C反应蛋白|CRP|血沉|ESR|淀粉酶|脂肪酶|D-?二聚体|纤维蛋白(原)?降解|IgE|嗜酸性粒细胞|'
     r'收缩压|舒张压|QTc|尿蛋白|尿糖|尿潜血|隐血|尿红细胞|尿白细胞|尿胆原|酮体|BNP|肌钙蛋白|肌红蛋白', 'up'),
    # 以下三行 2026-10-29 用户批准补条
    (r'(?:QT|P-?R)间期|(?<![A-Za-z])(?:QT|PR)(?![A-Za-z])', 'up'),              # 间期延长不利；含未校正 QT 写法（QTc 已在上条）
    (r'INR(?![A-Za-z])|国际标准化比值|凝血酶原时间|活化部分凝血活酶时间|部分凝血活酶时间|APTT|PTT|(?<![A-Za-z])PT(?![A-Za-z])', 'up'),   # 凝血延长不利
    (r'AMH(?![A-Za-z])|抗[缪苗]勒[氏]?管激素', 'down'),                          # AMH 降低不利
    (r'铁蛋白|血清铁|总铁结合力|体温|脉搏|呼吸频率|心率', 'both'),                # 缺铁与过载双向均异常、生命体征偏高偏低均异常——2026-10-29 用户批准维持双向
]
_MDIR: list = []


def set_metric_dir(user: dict | None):
    """构建开始时调用：项目配置（{正则: up|down|both}）在前，默认表在后。"""
    _MDIR[:] = [(re.compile(k), v) for k, v in (user or {}).items()] + [(re.compile(k), v) for k, v in DIR_DEFAULT]


def metric_dir(mid_or_label) -> str | None:
    s = str(mid_or_label or '')
    d = next((v for rx_, v in _MDIR if rx_.search(s)), None)
    return None if d in (None, 'both') else d


def daily_open(C, sid) -> bool:
    """日常监查阶段且受试者尚未出组（无研究结束日期、状态不是完成/退出/终止/死亡/失访）：后续数据可能尚未录入。"""
    s = C.subj.get(sid) or {}
    return C.cfg.get('dataStage') == 'daily' and not s.get('eos_d') and \
        not re.search(r'完成|退出|终止|死亡|失访|筛选失败|出组', str(s.get('status') or ''))


DAILY_NOTE = '受试者尚未出组，后续访视数据可能尚未录入（日常监查阶段仅作提示）'


def grade_up(bg, cg):
    """按分级判加重：基线已 ≥1 级后再升级，或升到 ≥2 级。0 级 → 1 级不单独算（避免略超上限即判加重）。"""
    return (cg or 0) > (bg or 0) and ((bg or 0) >= 1 or (cg or 0) >= 2)


def worse_vs_base(r, b, t_base, disease=False):
    """D14/D19 较基线加重：分级升高（0→1 级不单独算，见 grade_up），或超出范围且同向较基线变化 ≥T_base。
    返回说明文本或 None；仅临床意义 NCS→CS 的判定波动不算加重。
    V6 R3（审阅者 2026-11-02）：disease=True（研究疾病本身的表现，如嗜酸粒细胞）时，小基数指标的相对变化须同时达到
    绝对变化下限（monitor_v5.abs_floor，0.5→0.7 ×10^9/L 这类相对 40% 的波动不算「明显加重」）。"""
    if not b:                                        # 基线缺失：不虚构「0→2 级」，由调用方按「无法判断」处理
        return None
    if grade_up(b.get('grade'), r.get('grade')):
        return f"等级 {b.get('grade') or 0}→{r.get('grade')} 级"
    v, bv = r.get('value'), b.get('value')
    if v is None or bv is None:
        return None
    hi, lo = ref_hi(r), r.get('lo')                  # 血压无参考范围时用默认上限（与 REL/步骤 4 同口径）
    above, below = hi is not None and v > hi, lo is not None and v < lo
    d = metric_dir(r.get('mid'))                     # 只按不利方向判加重：HDL 升高、ALT 降低都不算
    above, below = above and d != 'down', below and d != 'up'
    if bv == 0:                                      # 基线为 0（如乙肝表面抗原 0→199.68）：现超出范围即视为加重
        return '基线为 0，现超出参考范围' if above else None
    pct = (v - bv) / abs(bv)
    if disease:
        from monitor_v5 import abs_floor
        fl = abs_floor(bv, r.get('unit'))
        if fl is not None and abs(v - bv) < fl:
            return None
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


_IND_QUAL = re.compile(r'^(?:季节性|常年性|持续性|间歇性|复发性|难治性|慢性|急性|原发性|继发性)+')


def _indication_names(C):
    ind = next((f[1] for f in ((C.S.get('study') or {}).get('design') or {}).get('facts') or [] if f[0] == '适应症'), '') \
        or (C.A.get('indication') or '')
    names = [p for p in re.split(r'[^\u4e00-\u9fff]+', re.sub(r'中度至重度|轻度|中度|重度|中重度|患者|伴有|成人|儿童|青少年|的|和|及', ' ', str(ind)))
             if len(p) >= 3]
    # V6（E2E 第 4 轮 SAR）：适应症写「季节性过敏性鼻炎」，研究者备注写「与过敏性鼻炎相关」——去掉病程/时相限定词的核心病名同样算研究疾病
    return names + [q for q in (_IND_QUAL.sub('', n) for n in names) if len(q) >= 3 and q not in names]


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


def _cons_key(r):
    """判定一致性可比组：同向异常 × 同给药阶段 × 同单位 × 同参考范围（与 clin_consistency 分组同口径）。"""
    if r.get('value') is None:
        return None
    d = 'H' if r.get('hi') is not None and r['value'] > r['hi'] else 'L' if r.get('lo') is not None and r['value'] < r['lo'] else ''
    return (d, bool(r.get('post')), r.get('unit'), r.get('lo'), r.get('hi')) if d else None


def judgment_only(C, r, rows, t_base):
    """该 CS 点只是改判（判定不一致 query 会覆盖），不按「潜在 AE 漏记」处理（用户 2026-10-27）：较基线未加重，
    且同受试者同指标同可比组里有一次偏离不小于它（更差或相等）却判 NCS 的记录——与 clin_consistency 新口径一致
    （mm5 审阅修正：旧版用 ±10% 双向相近，新算法不对「CS 更差」发一致性 query，导致这类 CS 两头都不发）。"""
    k = _cons_key(r)
    if not k or worse_vs_base(r, r.get('base'), t_base):
        return False
    dev = cons_dev(r, k[0])
    return any(a.get('clin') == 1 and _cons_key(a) == k and cons_dev(a, k[0]) >= dev for a in rows)


# ----------------------------------------------------------------------------- 判定一致性（用户 2026-10-30 终版：换芯＋同受试者版）
# 两维度：a. 判定维度（方向性）——可比对（同受试者/同中心跨受试者 × 同指标/单位/参考范围 × 同向异常 × 同给药阶段）
# 中更差者（偏离参考边界更远，相对偏离度、无最小差阈值）判 NCS 而更轻者判 CS → 发；更差者判 CS → 不发；
# 数值相等而判定不同 → 发（无更差方可定向，判定不同即不一致）。
# b. 归因维度（无方向不排序）——两条均 CS 且归因不同（AE/MH/研究疾病/未关联 任一不同）→ 发归因不一致。
# 旧「clinConsistTol ±10% / consTol ±5% 相近即双向报」口径废止。

def att_of(r):
    """CS 记录的归因（优先级 AE > MH > 研究疾病 > 未关联）：检验页关联编号优先，其次 CS 原因码（reason_map 归类）。
    links 兼容两种形态：parse_links 列表 ['AE', 术语, 日期, 编号] 与 dict {'type': 'AE', …}。"""
    ls = r['_lk'] if '_lk' in r else (r.get('links') or [])    # mm5 审阅（S7）：优先用回溯后的关联类型（mm_build.annotate_links）

    def typ(l):
        t = l[0] if isinstance(l, (list, tuple)) else (l.get('type') if isinstance(l, dict) else l)
        return str(t or '').upper()
    if any(typ(l) == 'AE' for l in ls):
        return 'AE'
    if any(typ(l) == 'MH' for l in ls):
        return 'MH'
    if 'disease' in (r.get('reason') or ''):
        return '研究疾病'
    return '未关联'


def cons_dev(r, d):
    """偏离参考边界的相对偏离度（可比组共享同一参考边界，组内直接可比；无最小差阈值——微差也算更差）。
    H=(v−hi)/|hi|、L=(lo−v)/|lo|；边界为 0 时退 |v−边界|/max(|v|,1e-9)（同为 0 边界的组内仍可比）。"""
    v = r['value']
    b = r.get('hi') if d == 'H' else r.get('lo')
    x = (v - b) if d == 'H' else (b - v)
    den = abs(b) if b else 0
    return x / den if den else x / max(abs(v), 1e-9)


def cons_witnesses(cs, ncs, d, cross_subject, min_diff=0.0):
    """判定维度配对：每个 CS 行锚定「偏离度不小于它」的最近一名 NCS 行（cross_subject 时要求不同受试者）。
    返回 [(a=CS 更轻, b=NCS 更差或相等, equal)]；equal＝偏离度相等（数值相等）→ 无更差方，判定不同即不一致。"""
    out, used = [], set()
    for a in cs:
        dev_a = cons_dev(a, d)
        # V6（MM 审阅 2026-11-02：12 条抽样约 8 条是 LDL 3.17/3.32 这类微小差异；用户「没做的一并做了」）：
        # 更差方须比 CS 方偏离参考边界多 ≥min_diff（相对偏离度，默认 0.05＝5 个百分点，analysis.consMinDiff 可调；0＝旧口径）；数值相等仍算
        cands = [b for b in ncs if id(b) not in used and (not cross_subject or b['sid'] != a['sid'])
                 and (cons_dev(b, d) == dev_a or cons_dev(b, d) >= dev_a + min_diff)]
        if not cands:
            continue
        b = min(cands, key=lambda r: (cons_dev(r, d), str(r.get('date') or ''), r.get('row') or 0))
        used.add(id(b))
        out.append((a, b, cons_dev(b, d) == dev_a))
    return out


def _mh_then_ae(a, b):
    """V6 R7（审阅者 2026-11-02）：同一受试者先归因病史、后来归因 AE（病史基础上加重记为 AE）是正常的记录方式，不算归因不一致。"""
    pa, pb = att_of(a), att_of(b)
    if {pa, pb} != {'MH', 'AE'}:
        return False
    mh, ae = (a, b) if pa == 'MH' else (b, a)
    return is_full_date(mh.get('date')) and is_full_date(ae.get('date')) and mh['date'] < ae['date']   # 先后不明/同日不豁免


def cons_attribution(cs, cross_subject):
    """归因维度配对：两条均 CS 且归因不同 → 一对（无方向不排序）；每行至多出现在一对中，取序稳定。"""
    out, used = [], set()
    for i, a in enumerate(cs):
        if id(a) in used:
            continue
        b = next((x for x in cs[i + 1:] if id(x) not in used and (not cross_subject or x['sid'] != a['sid'])
                  and att_of(x) != att_of(a) and not (not cross_subject and _mh_then_ae(a, x))), None)
        if b is None:
            continue
        used.add(id(a))
        used.add(id(b))
        out.append((a, b))
    return out


def _cons_text(C, mid, kind, d, a, b, equal):
    """单条判定/归因不一致的人话文案（方向性口径；质疑与一致性 tab 共用一出处）。"""
    lab = C.metric[mid]['label']
    va = f"{a.get('visit')}访视 {_val(_raw_or_val(a), a.get('unit'))}"
    vb = f"{b.get('visit')}访视 {_val(_raw_or_val(b), b.get('unit'))}"
    # V6 措辞排查：不写「更差者判轻」「归因AE/MH」「偏离参考边界10.3%」这类内部口径（偏离度仍是判定依据，只是不进正文）
    if kind == 'att':
        return f"{lab}：{va} 判为有临床意义并{att_cn(a)}，{vb} 判为有临床意义并{att_cn(b)}，相似结果的归因不同"
    if equal:
        return f"{lab}：{va} 与 {vb} 数值相同，一次判为有临床意义、一次判为无临床意义"
    return f"{lab}：{vb}（离正常范围更远）判为无临床意义，{va}（更接近正常）却判为有临床意义"


def att_cn(r):
    return {'AE': '关联不良事件', 'MH': '关联病史', '研究疾病': '归因研究疾病'}.get(att_of(r), '未关联任何记录')


def clin_consistency(C):
    """判定一致性·同受试者（用户 2026-10-30 终版换芯，方向性＋归因维度，见本文件「判定一致性」段头注释）。
    同一受试者同一表单合并为一条（D002：贫血受试者的 MCH/MCHC/MCV/Hb 常同时出现），锚定最近一次相关记录；
    不构成方案偏离。"""
    by = defaultdict(list)
    for (sid, mid), rows in sorted(C.F.items()):
        if sid not in C.pop:
            continue
        groups = defaultdict(list)
        for r in rows:
            if r.get('value') is None or r.get('clin') not in (1, 2):
                continue
            d = 'H' if r.get('hi') is not None and r['value'] > r['hi'] else 'L' if r.get('lo') is not None and r['value'] < r['lo'] else ''
            if d:
                groups[(d, bool(r.get('post')), r.get('unit'), r.get('lo'), r.get('hi'))].append(r)
        items = []
        for (d, *_), rs in groups.items():
            cs = [r for r in rs if r['clin'] == 2]
            ncs = [r for r in rs if r['clin'] == 1]
            for a, b, equal in cons_witnesses(cs, ncs, d, cross_subject=False, min_diff=float(C.A.get('consMinDiff', 0.05))):
                items.append(('judg', mid, d, a, b, equal))
            for a, b in cons_attribution(cs, cross_subject=False):
                items.append(('att', mid, d, a, b, False))
        if items:
            by[(sid, items[0][3]['sheet'])].append((mid, items))
    for (sid, sh), items in sorted(by.items()):
        def last(it):
            return max((x[3].get('date') or '') for m, lst in [it] for x in lst)
        items.sort(key=last, reverse=True)
        late = max((x[3] for m, lst in items for x in lst), key=lambda x: x.get('date') or '')
        parts = []
        for m, lst in items[:3]:
            for kind, mm, d, a, b, equal in lst[:2]:
                parts.append(_cons_text(C, m, kind, d, a, b, equal))
        total = sum(len(lst) for m, lst in items)
        more = f"（另有 {total - len(parts)} 项同类情况）" if total > len(parts) else ''
        kinds = {kind for m, lst in items[:3] for kind, *_ in lst[:2]}
        ask = ('请核实归因一致性：相似结果宜给出一致的医学解释；如异常与AE/病史相关，请在检验页关联记录。'
               if kinds == {'att'} else '请核实并统一临床意义判定；如判为有临床意义，请评估是否需记录AE。')
        add_ext(C, sid, '临床意义判定不一致', 'CLIN-INC', 3, '；'.join(parts) + more,
                late.get('visit'), late.get('date'), late['sheet'], late['row'], C.metric[items[0][0]]['label'],
                ctx=['判定一致性核对（不构成方案偏离）'],
                rule={'ask': ask},
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
    # V6（MM 审阅 2026-11-02：D002「CS较基线加重」9/9 假，尿潜血 3+→2+ 也算加重）：NCS→CS 判定翻转本身不是加重（另由判定一致性核对）
    v, bv = r.get('value'), b.get('value')
    if v is None and not flags:
        lv, bl = qual_level(r.get('raw')), qual_level(b.get('raw'))
        if lv is not None and bl is not None:
            return (True, True, [f"定性结果 {b.get('raw')}→{r.get('raw')}"]) if lv > bl else (True, False, [])
    if v is not None and bv not in (None, 0):
        hi, lo = ref_hi(r), r.get('lo')
        d = metric_dir(r.get('mid'))                 # 只按不利方向（与 worse_vs_base 同口径）
        hi, lo = (None if d == 'down' else hi), (None if d == 'up' else lo)
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


_NEG_RES = re.compile(r'阴性|未见|未检出|未发现|无|正常|-|－|—|neg(ative)?', re.I)


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
            if r.get('value') is None and not r.get('_panel') and _NEG_RES.fullmatch(str(r.get('raw') or '').strip()):
                # V6（MM 审阅：D002「未见滴虫」判 CS）：结果写阴性/未见却判有临床意义 → 多为录入或判定错位，发录入核对，不按「CS 未关联」追 AE
                add_ext(C, sid, '定性结果核对', 'M16-NEGCS', 3,
                        f"{r.get('visit')}（{r.get('date')}）{C.metric[mid]['label']}结果「{r.get('raw')}」，但临床意义判定为 CS",
                        r.get('visit'), r.get('date'), r['sheet'], r['row'], C.metric[mid]['label'],
                        rule={'ask': '结果为阴性/未见却判为有临床意义，请核实结果或临床意义判定是否录入有误。'},
                        bkey=f"{mid}|{r.get('visit')}|{r.get('date')}|negcs", wb=r.get('wb') or '')
                continue
            known, worse, flags = _worsening(r, t_base)
            binding = {'link': None, 'matched_ae': [], 'matched_mh': []}
            emit = None                                  # ('LINK'|'CSX_AE'|'MH'|'CSW'|'CSX', rec, extra)
            link = next((l for l in (r.get('links') or [])), None)
            if link is not None and link[3] is None:
                # F02 词目型（说明列写法）：按术语回溯到记录才算关联；对不上 → 回到未关联流程（不判「关联不对应」）
                pool = C.ae_by[sid] if link[0] == 'AE' else C.mh_by[sid]
                t = re.sub(r'[（(].*$', '', (link[1] or '').strip())
                ev = next((x for x in pool if t and (t in (x.get('t') or '') or (x.get('t') or '') in t)), None)
                link = [link[0], link[1], None, ev['n']] if ev is not None else None
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
                if ev is None and (link[1] or '').strip():   # V6：编号口径不同但术语能回溯 → 按术语认（同 mm_build.resolve_links）
                    t = re.sub(r'[（(].*$', '', link[1].strip())
                    ev = next((x for x in pool if t and len(t) >= 2 and (x.get('t') or '') and (t in x['t'] or x['t'] in t)), None)
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
                # 用户裁定（PLAN §15.1，2026-10-28）：时间口径＝AE 持续期间覆盖检验日期（ae_covers，与第七批同因同策），
                # 废弃 ±w 天经验窗口（aeMatch 第三元素保留以兼容配置契约，不再参与判定）
                for mre, are, w in ae_match_rows(C, mid):   # 步骤 2：匹配 AE（方向相反的不算）
                    for a in C.ae_by[sid]:
                        if are.search(a['t']) and not opp.search(a['t']) and is_full_date(r.get('date')) and ae_covers(a, r['date']):
                            maes.append({'no': a['n'], 'term': a['t'], 'start': a['s'], 'match': True})
                if not maes:
                    maes = desc_ae_match(C, sid, r)
                binding['matched_ae'] = maes[:4]
                if maes and re.search(r'AE|不良事件|已报|已记录', str(r.get('desc') or '')) and \
                        any(re.sub(r'[（(].*$', '', str(m['term'])).strip() in str(r.get('desc') or '') for m in maes):
                    continue                             # V6（MM：「肝酶升高AE」）：研究者备注已写明对应 AE 且同期存在 → 视为已说明，不发 query
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
            dh = disease_hint(C, mid, r.get('sheet', ''))
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
        mv = move_word(bv, v, r.get('lo'), r.get('hi'))   # F06：低于下限不写「升高至」（偏离方向与基线方向分离表述）
        head = f"{r.get('visit')}访视{C.metric[r['mid']]['label']}{mv}{_val(_raw_or_val(r), r.get('unit'))}"
    if kind == 'LINK':
        fact = f"{head}判为有临床意义{extra or ''}，"
    elif kind == 'CSX_AE':
        fact = f"{head}判为有临床意义，同期已记录AE“{(rec or {}).get('term', '')}”（{(rec or {}).get('start', '')}），但未关联，"
    elif kind == 'MH':
        fact = f"{_base_txt(r)}{head}判为有临床意义，仅关联病史“{(rec or {}).get('t', '')}”，较基线加重且未见对应AE，"
    elif kind == 'CSW':
        why = extra or ('（' + '、'.join(f for f in flags if not f.startswith('给药前'))[:40] + '）' if flags else '')
        fact = f"{_base_txt(r)}{head}判为有临床意义{why}，"
    else:
        fact = f"{_base_txt(r)}{head}判为有临床意义，但未关联AE或病史，"
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
