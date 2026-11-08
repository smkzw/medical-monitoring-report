"""V5 监察扩展（用户 2026-10-31 晚：临床监察与总览全面推进）。全部确定性、只读已映射的 listing 字段，由 mm_build.analyze 调用。

- visit_due / upcoming：按方案访视窗（首剂锚点）推算截至数据截止应完成的访视、逾期/超窗，以及未来 14 天应到访视（原在前端 p-monitor 计算，移到后端供 KRI 共用）。
- freshness：各中心最近一条记录日期 → 数据新鲜度。followup：每例随访人日（热力图按暴露时间算期望数）。
- kri：中心 × 关键风险指标（KRI）与研究层面数值，研究层面容忍限度（QTL）三档默认值（经验值，需研究团队确认）。
- ctq：关键数据（关键访视 / 关键评估 / 停药相关指标）标记，行动项加权用。
- lab_shift：范围内明显变化（肌酐 KDIGO 幅度、QTcF 较基线 >60 ms、血红蛋白降 ≥20 g/L）与持续变化趋势预警（提示，不发质疑）。
- cred：数据可信度（中心层面）：末位数字偏好、多次访视数值完全相同、中心基线均值偏离、同日多名受试者生命体征完全相同。
口径见 references/analysis-rules.md §19。
"""
import datetime as _dt
import math
import re
import statistics
from collections import Counter, defaultdict

import ext_rules
from common import days, dshow, fmt, is_full_date

ENDED = ('完成试验', '提前退出', '筛选失败')


def _add(d, n):
    return (_dt.date.fromisoformat(d) + _dt.timedelta(days=n)).isoformat()


def _win(s):
    if isinstance(s, (list, tuple)):
        return (s[0] if s else None), (s[1] if len(s) > 1 else 0) or 0, (s[2] if len(s) > 2 else 0) or 0
    return s.get('target'), s.get('minus') or 0, s.get('plus') or 0


def _end(s):
    xs = [d for d in (s.get('eos_d'), s.get('eot_d')) if is_full_date(d)]
    return min(xs) if xs else ''


def bh(ps):
    """Benjamini–Hochberg 校正后的 q 值（与输入同序；None 原样返回）。"""
    idx = sorted((i for i, p in enumerate(ps) if p is not None), key=lambda i: ps[i])
    q, m, run = [None] * len(ps), len(idx), 1.0
    for r in range(m - 1, -1, -1):
        i = idx[r]
        run = min(run, ps[i] * m / (r + 1))
        q[i] = run
    return q


def binom_upper(x, n, p):
    """P(X ≥ x)，X~Binomial(n,p)。"""
    if x <= 0:
        return 1.0
    if x > n:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    tot = 0.0
    for k in range(x, n + 1):
        tot += math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq)
    return min(1.0, tot)


def pois_upper(o, e):
    """P(X ≥ o)，X~Poisson(e)。"""
    if o <= 0:
        return 1.0
    if e <= 0:
        return 0.0
    term, cdf = math.exp(-e), 0.0
    for k in range(o):
        cdf += term
        term *= e / (k + 1)
    return max(0.0, min(1.0, 1 - cdf))


def norm_two(z):
    return math.erfc(abs(z) / math.sqrt(2))


def crit_items(C):
    """方案关键评估（analysis.pd.criticalItems 正则）→ (正则, 数据中实际匹配到的指标名)。方案写法与 listing 名称常差一个后缀
    （「EASI评分」↔「EASI得分」）：原样匹配不到时去掉 评分/得分/总分/分数/评估 后缀再匹配。"""
    pat = (C.A.get('pd') or {}).get('criticalItems')
    if not pat:
        return None, []
    names = {str(r.get('metric') or '') for r in C.efficacy} | {str(f.get('test') or '') for f in C.findings}
    for p in (pat, re.sub(r'(评分|得分|总分|分数|评估)', '', pat)):
        try:
            rx_ = re.compile(p)
        except re.error:
            continue
        hit = sorted(n for n in names if n and rx_.search(n))
        if hit:
            return rx_, hit
    return re.compile(pat), []


def planned_n(C):
    st = C.S.get('study') or {}
    for v in (st.get('planned'), (C.cfg.get('study') or {}).get('planned')):
        try:
            if v:
                return int(v)
        except (TypeError, ValueError):
            pass
    for f in ((st.get('design') or {}).get('facts') or []):
        if len(f) >= 2 and re.search(r'计划(例数|入组|样本)', str(f[0])):
            m = re.search(r'\d+', str(f[1]))
            if m:
                return int(m.group())
    return None


# ----------------------------------------------------------------------------- 访视推算 / 新鲜度 / 随访人日
def visit_alias(C, W):
    """V6 方案访视键 → 数据访视代码（审阅者 2026-11-02：D002 方案 V5–V9 对数据 W2–W18 → 616/616 假逾期；
    SAR 方案 V6/V7 在数据里都记成 FU → 342/345 假逾期）。数据驱动、不靠命名：方案键在数据里零记录时，
    找「该代码的记录落在本方案访视窗内的比例」最高的数据代码（≥30%、≥3 条）作别名；对不上的方案键判「未映射」。
    只有数据里确有方案键以外的访视代码（排除计划外/提前退出）时才做对齐——否则零记录就是没做，照常判逾期。
    → (alias {方案键: 数据代码}, unmapped [方案键])"""
    sd = defaultdict(list)
    for v in C.visits:
        s = C.subj.get(v.get('sid')) or {}
        if v.get('visit') and is_full_date(v.get('date')) and is_full_date(s.get('fd')):
            sd[v['visit']].append(days(v['date'], s['fd']) + 1)
    vc = (getattr(C, 'cfg', None) or {}).get('visits') or {}
    skip = set(vc.get('unsched') or ['USV']) | set(vc.get('early') or ['ET'])
    foreign = [c for c, ds in sd.items() if c not in W and c not in skip and len(ds) >= 3]
    alias, unmapped = {}, []
    if not foreign:
        return alias, unmapped                                 # 数据访视代码都在方案键内 → 无命名不一致证据，零记录照常判逾期
    for pv, spec in W.items():
        if pv in sd:
            continue
        t, mi, pl = _win(spec)
        if t is None:
            continue
        best, share = None, 0.0
        for code in foreign:                                   # 本身就是方案访视键的代码不借给别的访视
            ds = sd[code]
            sh = sum(t - mi <= d <= t + pl for d in ds) / len(ds)
            if sh > share:
                best, share = code, sh
        if best and share >= 0.3:
            alias[pv] = best
        else:
            unmapped.append(pv)
    return alias, unmapped


def visit_due(C, cutoff):
    """→ (due, upcoming)。due 行 [sid, site, 访视, 窗起, 窗止, 实际日期, 状态 overdue|out|ok, 实际研究日, 目标日, −窗, +窗]；
    upcoming 行 [sid, site, 访视, 窗起, 窗止, 目标日期]（未来 14 天内窗口开启或在窗、受试者未结束）。
    V6：方案键经 visit_alias 对齐到数据代码；同一代码下多条记录（如 V6/V7 都记 FU）按访视目标日先后，各取最接近目标日、
    尚未被占用的一条；「未映射」的方案访视不推算（不计逾期，原因写入 ops.visitUnmapped）。"""
    W = C.A.get('visitWindows') or {}
    alias, unmapped = visit_alias(C, W)
    C._visit_alias, C._visit_unmapped = alias, unmapped
    rec = defaultdict(lambda: defaultdict(list))
    syswin = {}
    for v in C.visits:
        if v.get('visit') and is_full_date(v.get('date')):
            rec[v['sid']][v['visit']].append(v['date'])
            if is_full_date(v.get('win_lo')) and is_full_date(v.get('win_hi')):     # V6：EDC 系统计划窗（同 visit_window_checks 口径）
                syswin[(v['sid'], v['visit'], v['date'])] = (str(v['win_lo'])[:10], str(v['win_hi'])[:10])
    missed = {(v['sid'], v.get('visit')) for v in getattr(C, 'visits_missed', [])}   # EDC 访视页记为「未进行」的访视
    arm_skip = arm_specific_visits(C, rec)
    if arm_skip:
        C._visit_arm = [f"{v}（{a}{'' if str(a).endswith('组') else '组'}无该访视）" for v, a in sorted(arm_skip)]
    order = sorted((k for k in W if k not in unmapped), key=lambda k: (_win(W[k])[0] is None, _win(W[k])[0] or 0))
    horizon = _add(cutoff, 14) if is_full_date(cutoff) else ''
    due, up = [], []
    for sid, s in C.subj.items():
        fd = s.get('fd')
        if not is_full_date(fd):
            continue
        e = _end(s)
        stop = _stop(s)
        taken = set()
        for v in order:
            spec = W[v]
            t, mi, pl = _win(spec)
            if t is None:
                continue
            ad, base = _anchor(s, spec, rec[sid], alias)
            if not is_full_date(ad):
                continue                                       # 锚点未发生（如末次给药锚定而仍在治疗）→ 不推算
            lo, hi = _add(ad, t - base - mi), _add(ad, t - base + pl)
            code = v if v in rec[sid] or v not in alias else alias[v]
            if (code, s.get('grp')) in arm_skip:
                continue                                       # 组别专属访视（见上）
            pool = [d for d in rec[sid].get(code, []) if (code, d) not in taken]
            got = min(pool, key=lambda d: abs(days(d, ad) + base - t)) if pool else ''
            if got and code != v and not (lo <= got <= hi) and len(rec[sid].get(code, [])) > 1:
                got = ''                                       # 别名代码有多条时，窗外的那条属于别的访视，不硬配
            if got:
                taken.add((code, got))
            if not got:
                st_ = (s.get('eos_d') if is_full_date(s.get('eos_d')) else '') if base == 0 and isinstance(spec, dict) and spec.get('anchor') == 'ld' else stop
                if st_ and st_ <= hi:
                    continue                                   # V6（CRA）：访视窗关闭前已退出/结束研究 → 不算逾期
                if _GONE.search(str(s.get('eos_why') or '')) or _GONE.search(str(s.get('eot_why') or '')):
                    continue                                   # V6 运营审阅：失访/拒绝随访/撤回知情已有记录 → 不是「逾期待追」
                if not cutoff or hi >= cutoff:
                    if horizon and not e and s.get('status') not in ENDED and lo <= horizon:
                        up.append([sid, s['site'], v, lo, hi, _add(ad, t - base)])
                    continue
            sd = days(got, ad) + base if is_full_date(got) else None
            st = 'overdue' if not got else ('out' if sd is not None and (sd < t - mi or sd > t + pl) else 'ok')
            sw = syswin.get((sid, code, got)) if got else None
            if sw:                                             # 有 EDC 系统窗：窗与超窗判定以它为准
                lo, hi = sw
                st = 'ok' if lo <= got <= hi else 'out'
            # 第 12 列：逾期且 EDC 已记为未进行（不是「没录入」，是「确认没做」——CRA 不用再追录入，转方案偏离/缺失核实）
            due.append([sid, s['site'], v, lo, hi, got, st, sd, t, mi, pl, 1 if not got and ((sid, v) in missed or (sid, code) in missed) else 0])
    return due, up


def arm_specific_visits(C, rec=None):
    """组别专属访视（V6，MY008 运营审阅：D21「仅限依库珠单抗组」，另一组 34 人全报逾期）：有分组时按数据判——
    某访视在一组已给药者中有记录 ≥50%、在另一组（≥5 人）为 0 → {(访视代码, 组别)}：该组不推算逾期/缺失。
    盲态构建无分组 → 空集（不据此推断分组）。rec：{sid: {访视: [日期]}}，缺省按 C.visits 统计。结果缓存在 C 上。"""
    if getattr(C, '_arm_skip', None) is not None:
        return C._arm_skip
    if rec is None:
        rec = defaultdict(dict)
        for v in C.visits:
            if v.get('visit'):
                rec[v['sid']].setdefault(v['visit'], []).append(v.get('date'))
    arms = defaultdict(list)
    for sid_, s_ in C.subj.items():
        if s_.get('grp') and is_full_date(s_.get('fd')):
            arms[s_['grp']].append(sid_)
    out = set()
    if len(arms) >= 2:
        for code_ in {v for x in rec for v in rec[x]}:
            cov = {a: sum(1 for x in ids if code_ in rec.get(x, {})) / len(ids) for a, ids in arms.items()}
            if max(cov.values()) >= .5:
                out |= {(code_, a) for a, ids in arms.items() if cov[a] == 0 and len(ids) >= 5}
    C._arm_skip = out
    return out


_EARLY = re.compile(r'提前|退出|脱落|中止|终止|失访|撤回')
_GONE = re.compile(r'失访|拒绝|撤回|撤销知情|退出研究|死亡')


def _stop(s):
    """受试者实际离开研究的日期：研究结束日；提前退出者无研究结束日时取治疗结束日。完成治疗、进入随访的不算离开。"""
    xs = [s['eos_d']] if is_full_date(s.get('eos_d')) else []
    if is_full_date(s.get('eot_d')) and _early_wd(s):     # 提前终止治疗（状态或治疗结束原因判定）：其后的治疗期访视不再应做
        xs.append(s['eot_d'])                              # （末次给药锚定的随访访视另按锚点推算，不受此限）
    if not xs and (_EARLY.search(str(s.get('status') or '')) or s.get('status') == '完成试验') and is_full_date(s.get('lo')):
        xs.append(s['lo'])                                 # 已出组但无结束页日期（D001「中止退出」无日期）→ 末次观察日
    return min(xs) if xs else ''


def _anchor(s, spec, rec_sid, alias):
    """V6（CRA 审阅 2026-11-02：RUX W28、D002 W18 方案按末次给药锚定，旧实现一律按首剂推算 → 88/97 假超窗）。
    → (锚点日期, 记日基数)。首剂锚定沿用 D1 记法（目标日 t ＝ 首剂 + t−1）；其余锚点按「锚点后第 t 天」。
    末次给药锚定只在治疗已结束（有治疗结束日或已出组）时成立。"""
    anc = spec.get('anchor', 'fd') if isinstance(spec, dict) else 'fd'
    if anc == 'fd':
        return s.get('fd'), 1
    if anc == 'ld':
        done = is_full_date(s.get('eot_d')) or is_full_date(s.get('eos_d')) or s.get('status') in ENDED
        return (s.get('ld') if done else ''), 0
    if anc in ('rand', 'icf'):
        return s.get({'rand': 'rand_d', 'icf': 'icf'}[anc]), 0
    code = anc if anc in rec_sid else alias.get(anc, anc)        # 锚定另一访视的实际日期
    ds = sorted(rec_sid.get(code) or [])
    return (ds[0] if ds else ''), 0


_DONE_WHY = re.compile(r'完成|按方案|方案规定|规定的治疗|治疗周期结束|疗程结束')


def _early_wd(s):
    """V6（PM 审阅 2026-11-02）：提前退出＝状态写明提前/退出/脱落/中止，或有治疗结束日且原因不是「完成方案规定的治疗」。
    D002 19 例「治疗结束·参与者完成方案规定的治疗」曾被误计（17.2% 超限），SAR「脱落」曾漏计（0/175）。"""
    st = str(s.get('status') or '')
    if _EARLY.search(st):
        return True
    why = str(s.get('eot_why') or '')
    return bool(s.get('eot_d') and why and not _DONE_WHY.search(why))


_PENDING = re.compile(r'请核实|待判定|待核实|需经治疗|请提供|无法判断|不可得')


def _pd_firm(p):
    return p.get('grade') != '待判定' and not _PENDING.search(str(p.get('fact') or ''))


def gap_check(C, add_other):
    """V6（CRA 审阅 2026-11-02：D001 某例 D3 发生 SAE 后再无访视、无治疗/研究结束页，52 天无任何信号）：
    在研受试者末次记录距数据截止超过 max(42 天, 2×研究访视间隔中位数)、且无研究结束记录 → 访视中断核对（日常阶段同样提示）。"""
    alld = [s.get('lo') for s in C.subj.values() if is_full_date(s.get('lo'))]
    cut = (C.cfg.get('study') or {}).get('cutoff') or (max(alld) if alld else '')
    if not is_full_date(cut):
        return
    gaps = []
    byv = defaultdict(list)
    for v in C.visits:
        if is_full_date(v.get('date')):
            byv[v['sid']].append(v['date'])
    for ds in byv.values():
        ds = sorted(set(ds))
        gaps += [days(b, a) for a, b in zip(ds, ds[1:]) if days(b, a)]
    thr = max(42, 2 * statistics.median(gaps)) if gaps else 42
    for sid in sorted(C.pop):
        s = C.subj[sid]
        if is_full_date(s.get('eos_d')) or s.get('status') in ENDED or _EARLY.search(str(s.get('status') or '')) or not is_full_date(s.get('lo')):
            continue
        g = days(cut, s['lo'])
        if g is None or g <= thr:
            continue
        sae = [a for a in (getattr(C, 'ae_by', None) or {}).get(sid, []) if a.get('sae')]
        add_other(C, sid, '访视中断核对', 3,
                  f"末次记录 {s['lo']}，距数据截止 {g} 天（超过 {int(thr)} 天），未见治疗结束/研究结束记录"
                  + (f"；此前有 SAE「{sae[-1]['t']}」（{sae[-1]['s']}）" if sae else ''),
                  None, s['lo'], s.get('sheet', ''), s.get('row'), '',
                  ctx=['在研受试者长时间无任何记录：可能失访、已退出未录入，或访视未录入'],
                  rule={'ask': '请确认受试者当前状态（是否失访/退出），并补录后续访视或治疗结束、研究结束页。'},
                  bkey=f"gap|{sid}")


def freshness(C, cutoff):
    """{site: [最近记录日期, 距数据截止天数, 在研受试者数]}（晚于数据截止的日期视为录入错误，不计）。"""
    last = defaultdict(str)
    for dom in ('visits', 'exposure', 'ae', 'findings', 'efficacy', 'cm'):
        for r in getattr(C, dom, None) or []:
            s = C.subj.get(r.get('sid'))
            if not s:
                continue
            for k in ('date', 'start', 'end'):
                d = r.get(k)
                if is_full_date(d) and (not cutoff or d <= cutoff) and d > last[s['site']]:
                    last[s['site']] = d
    active = Counter(s['site'] for s in C.subj.values() if s.get('fd') and not _end(s) and s.get('status') not in ENDED)
    return {site: [d, days(cutoff, d) if cutoff else None, active.get(site, 0)] for site, d in sorted(last.items())}


def followup(C, cutoff):
    """{sid: 随访人日}：首剂 → 研究结束（无则在研者到数据截止、已结束者到最后观察日），不超过数据截止。"""
    fu = {}
    for sid in sorted(C.pop):                                # 按受试者号遍历：输出字节级可复现（集合顺序随哈希种子变）
        s = C.subj[sid]
        fd = s.get('fd')
        if not is_full_date(fd):
            continue
        e = s.get('eos_d') if is_full_date(s.get('eos_d')) else ''
        if not e:
            e = (s.get('lo') or s.get('ld') or fd) if s.get('status') in ENDED or _end(s) else (cutoff or s.get('lo') or fd)
        if cutoff and e > cutoff:
            e = cutoff
        fu[sid] = max(1, (days(e, fd) or 0) + 1)
    return fu


# ----------------------------------------------------------------------------- KRI / QTL
# 键, 名称, 组, 单位, 不利方向, 研究层面容忍限度 (严格, 标准, 宽松)（None＝只作 KRI）, 口径
KRI_DEFS = [
    ('sf', '筛选失败率', '入组', '%', 'high', None, '筛选失败 / 筛选'),
    ('wd', '提前退出率', '入组', '%', 'high', (10, 15, 20), '提前退出或提前终止治疗 / 给药'),
    ('ovd', '访视逾期率', '执行', '%', 'high', None, '逾期未见记录 / 应完成访视（日常监查阶段含尚未录入）'),
    ('oow', '访视超窗率', '执行', '%', 'high', (5, 10, 15), '超窗 / 已完成访视'),
    ('ipd', '重要潜在方案偏离', '执行', '%', 'high', (5, 10, 15), '有重要潜在方案偏离的受试者 / 给药'),
    ('elig', '入排不符仍入组', '执行', '%', 'high', (1, 2, 5), '入排类潜在偏离的受试者 / 给药'),
    ('icf', '知情同意问题', '执行', '%', 'high', (0, 1, 3), '知情类潜在偏离的受试者 / 筛选'),
    ('comp', '依从性不符', '执行', '%', 'high', (5, 10, 15), '依从性超出方案范围的受试者 / 给药（方案无依从性公式时按有漏服记录的受试者）'),
    ('pem', '主要终点缺失', '数据', '%', 'high', (3, 5, 10), '关键访视已完成但关键评估无记录 / 已完成的关键访视'),
    ('ae', 'TEAE 报告率', '安全', '/100人月', 'low', None, 'TEAE 例次 / 随访人月 ×100（偏低提示可能漏报）'),
    ('sae', 'SAE 报告率', '安全', '/100人月', 'both', None, 'SAE 例次 / 随访人月 ×100'),
    ('late', 'SAE/AESI 报告超时', '安全', '%', 'high', (0, 5, 10), '报告超时 / SAE 与 AESI 例次'),
    ('csx', 'CS 未关联（检验）', '安全', '/例', 'high', None, '检验风险层：判 CS 未关联 AE/病史（受试者×指标，一个指标多次只计一次）/ 给药。专项（心电图/生命体征整份判定等）与质疑另计'),
    ('q', '申办方质疑', '数据', '/例', 'high', None, '申办方医学质疑 / 给药'),
    ('ent', '疑似录入错误', '数据', '/千条', 'high', None, '疑似录入错误 / 数值型检验检查记录 ×1000'),
    ('fresh', '数据新鲜度', '数据', '天', 'high', None, '数据截止 − 最近一条记录日期（研究层面取各中心中位数）'),
]
QTL_TIERS = [['strict', '严格'], ['std', '标准'], ['loose', '宽松']]


def _eff_trend_present(C) -> bool:
    """有效性页是否已按终点配置生成趋势（与 build_eff 同一判定源：终点配置的 src 在数据中有数值行）。
    G4：KRI「主要终点缺失」与有效性页取同一判定——criticalItems 匹配不到指标名时，先看有效性侧是否真有数据。"""
    srcs = {str(m.get('src')) for m in (C.A.get('efficacy') or []) if m.get('src')}
    if not srcs:
        return False
    for e in C.efficacy:
        if 'eff:' + str(e.get('metric')) in srcs and (e.get('value') not in (None, '') or e.get('raw') not in (None, '')):
            return True
    F = getattr(C, 'F', None)
    if F:
        for (sid, mid), rows in F.items():
            if mid in srcs and any(r.get('value') is not None for r in rows):
                return True
    return False


def kri(C):
    cut = C.ops.get('cutoff') or ''
    S = C.subj
    sites = sorted({s['site'] for s in S.values()})
    dosed = [sid for sid in sorted(C.pop) if S[sid].get('fd')]
    pd = (C.pdd or {}).get('potential') or []
    ran = {r['id']: r.get('state') for r in (C.pdd or {}).get('rules') or []}
    # V6（PM 审阅 2026-11-02）：容忍限度分子只计「事实已成立」的潜在偏离；文案本身写着请核实/待判定/需经治疗后仍超标
    # 的（例外条款待查、删失值、待判定）单列为「待核实」，不进分子（RUX 入排 13.5% 三档全超，多数为待核实）
    firm = [p for p in pd if _pd_firm(p)]
    by_rule = defaultdict(set)
    for p in firm:
        by_rule[p['rule']].add(p['sid'])
    imp = {p['sid'] for p in firm if p.get('grade') == '重要'}
    C.ops['kriPending'] = {'ipd': len({p['sid'] for p in pd if p.get('grade') == '重要'} - imp),
                           'elig': len({p['sid'] for p in pd if str(p.get('rule', '')).startswith('ELIG')} - {p['sid'] for p in firm if str(p.get('rule', '')).startswith('ELIG')})}
    elig = set().union(*[v for k, v in by_rule.items() if k.startswith('ELIG')]) if by_rule else set()
    icf = set().union(*[v for k, v in by_rule.items() if k.startswith('ICF')]) if by_rule else set()
    ex = C.ops.get('ex') or {}
    comp = by_rule.get('IP-03', set()) if ran.get('IP-03') == 'ran' else {sid for sid, x in ex.items() if x.get('miss')}
    due = C.ops.get('due') or []
    P = C.A.get('pd') or {}
    cv, (ci, ci_hit) = set(P.get('criticalVisits') or []), crit_items(C)
    have = defaultdict(set)
    if ci:
        for r in list(C.efficacy) + list(C.findings):
            if ci.search(str(r.get('metric') or r.get('test') or '')) and (r.get('value') not in (None, '') or r.get('raw') not in (None, '')):
                have[r['sid']].add(r.get('visit'))
    crit_rows = [d for d in due if d[2] in cv and d[5]] if cv and ci and ci_hit else []
    if C.cfg.get('dataStage') == 'daily' and is_full_date(cut):   # V6 R9：日常监查截止前 N 天内才完成的关键访视可能尚未录入，不计缺失
        grace = int(C.A.get('entryGraceDays', 14))
        crit_rows = [d for d in crit_rows if not is_full_date(d[5]) or days(cut, d[5]) > grace]   # ci_hit 空＝正则匹配失败，pem 分母必须归零（否则全为「无评估」→「n/n 全缺」误读；na 已提示原因）
    fu = C.ops.get('fu') or {}
    te = [a for a in C.aes if a['sid'] in C.pop and a.get('te') and not a.get('dup')]   # F-D：完全重复记录（第 2 份起）不计数
    nnum = Counter(S[f['sid']]['site'] for f in C.findings if f['sid'] in S and isinstance(f.get('value'), (int, float))
                   and str(f.get('mid') or '').split(':')[0] in ('lab', 'vs', 'ecg'))
    fresh = C.ops.get('fresh') or {}
    na = {}
    if not cv or not ci:
        na['pem'] = '方案关键访视（analysis.pd.criticalVisits）或关键评估（criticalItems）未配置'
    elif not ci_hit:
        # G4：criticalItems 绑定失败时与有效性页同一判定——终点配置已生成趋势则说明数据在、只是指标名未匹配上，
        # 不再断言「找不到」（实证：KRI 显「—（找不到指标）」而有效性页正常生成趋势）；两侧都空才写找不到。
        na['pem'] = (f"关键评估「{P.get('criticalItems')}」在数据中找不到对应指标" if not _eff_trend_present(C)
                     else f"关键评估「{P.get('criticalItems')}」未匹配到访视/量表指标名，无法按访视核算缺失；"
                          f"有效性页已按终点配置生成趋势（见 efficacy.html）")
    if not any(k.startswith('ELIG') and v == 'ran' for k, v in ran.items()):
        na['elig'] = '入排数值条件未配置'
    if not any(k.startswith('ICF') and v == 'ran' for k, v in ran.items()):
        na['icf'] = '知情同意核查未执行'
    if ran.get('SAFE-02') != 'ran':
        na['late'] = 'AE 表无获知/报告日期'
    if ran.get('IP-03') != 'ran' and not any('miss' in x for x in ex.values()):
        na['comp'] = '依从性无法测算（方案无依从性公式、给药记录也无漏服/剂量字段）'   # V6（PM）：不再显示 0% 限度内
    if not (C.A.get('visitWindows')):
        na['ovd'] = na['oow'] = '方案访视窗未配置'
    elif not due and C.ops.get('visitUnmapped'):
        na['ovd'] = na['oow'] = f"方案访视（{'、'.join(C.ops['visitUnmapped'][:6])}）在数据中找不到对应访视代码"

    def calc(ids):
        ids = set(ids)
        ds = [x for x in dosed if x in ids]
        sv = [d for d in due if d[0] in ids]
        got = [d for d in sv if d[5]]
        cr = [d for d in crit_rows if d[0] in ids]
        fud = sum(fu.get(x, 0) for x in ds)
        te_ = [a for a in te if a['sid'] in ids]
        ssa = [a for a in te_ if a.get('sae') or a.get('aesi')]
        wd = [x for x in ds if _early_wd(S[x])]
        site_set = {S[x]['site'] for x in ids}
        return {
            'sf': [sum(S[x]['status'] == '筛选失败' for x in ids), len(ids)],
            'wd': [len(wd), len(ds)],
            'ovd': [sum(d[6] == 'overdue' for d in sv), len(sv)],
            'oow': [sum(d[6] == 'out' for d in got), len(got)],
            'ipd': [len(imp & set(ds)), len(ds)],
            'elig': [len(elig & set(ds)), len(ds)],
            'icf': [len(icf & ids), len(ids)],
            'comp': [len(comp & set(ds)), len(ds)],
            'pem': [sum(d[2] not in have.get(d[0], set()) for d in cr), len(cr)],
            'ae': [len(te_), fud],
            'sae': [sum(1 for a in te_ if a.get('sae')), fud],
            'late': [sum(1 for p in pd if p['rule'] == 'SAFE-02' and p['sid'] in ids), len(ssa)],
            'csx': [sum(1 for g in C.labrows if g['sid'] in ids and g['risk'] == 'CSX'), len(ds)],
            'q': [sum(1 for q in C.queries if q['sid'] in ids), len(ds)],
            'ent': [sum(1 for e in C.entry if e['sid'] in ids), sum(nnum.get(s, 0) for s in site_set)],
        }
    out_sites = {}
    for site in sites:
        ids = [sid for sid, s in S.items() if s['site'] == site]
        v = calc(ids)
        f = fresh.get(site)
        v['fresh'] = [f[1], 1] if f and f[1] is not None and f[2] else [None, 1]
        out_sites[site] = v
    study = calc(list(S))
    fr = [f[1] for f in fresh.values() if f[1] is not None and f[2]]
    study['fresh'] = [statistics.median(fr) if fr else None, 1]
    defs = [{'k': k, 'l': l, 'g': g, 'u': u, 'dir': d, 'qtl': list(q) if q else None, 'note': n} for k, l, g, u, d, q, n in KRI_DEFS]
    # F6②（V6 RUX）：提前退出率分子＝「提前退出或提前终止治疗」，与受试者状态分布的「提前退出」不是一套口径——
    # 脚注写明「另 N 例仅提前终止治疗（未退出研究）」，两套数字可互推，不再无脚注并存（实证 12/192 vs 状态分布 8）。
    wd_def = next((d for d in defs if d['k'] == 'wd'), None)
    if wd_def is not None:
        wd_ids = {x for x in dosed if _early_wd(S[x])}
        exit_only = {x for x in wd_ids if re.search(r'退出|脱落|失访|撤回', str(S[x].get('status') or ''))}
        term_only = len(wd_ids) - len(exit_only)
        if term_only:
            wd_def['note'] += f"；其中另 {term_only} 例仅提前终止治疗（未退出研究，仍在随访），未计入状态分布的「提前退出」"
    return {'defs': defs, 'tiers': QTL_TIERS, 'tierDefault': 'std', 'study': study, 'sites': out_sites, 'na': na,
            'pem': {'visits': sorted(cv), 'items': ci_hit},
            'source': '容忍限度为经验默认值，需研究团队确认（ICH E6(R3) §3.10.1.3 要求申办方预设可接受范围）'}


# ----------------------------------------------------------------------------- 关键数据（CtQ）
def ctq(C):
    """给检验风险行、专项信号、疑似录入错误、潜在 PD 标 ctq＝原因（关键访视 / 关键评估 / 停药相关指标）。"""
    P = C.A.get('pd') or {}
    cv = set(P.get('criticalVisits') or [])
    ci = crit_items(C)[0]
    stop = [re.compile(R['metric']) for R in C.A.get('thresholdRules', []) if R.get('stop') and R.get('metric')]

    def why(test='', visits=(), mid=''):
        w = []
        if cv and any(v in cv for v in visits if v):
            w.append('关键访视')
        if ci and test and ci.search(test):
            w.append('关键评估')
        mids = [mid] if mid else [f'{d}:{test}' for d in ('lab', 'vs', 'ecg')] if test else []
        if stop and any(r.search(m) for r in stop for m in mids):
            w.append('停药相关指标')
        return '、'.join(w)
    for g in C.labrows:
        w = why(g.get('test') or '', (), g.get('mid') or '')            # 检验异常是否关键看指标本身，不看发生在哪次访视
        if w:
            g['ctq'] = w
    for o in C.others:
        w = why(o.get('test') or '', [o.get('v')] if re.search('访视', o.get('cat') or '') else ())
        if w:
            o['ctq'] = w
    for e in C.entry:
        w = why(e.get('test') or '')
        if w:
            e['ctq'] = w
    for p in (C.pdd or {}).get('potential') or []:
        w = why(next((s[2] for s in p.get('src') or [] if len(s) > 2 and s[2]), ''), [p.get('visit')])
        if w:
            p['ctq'] = w


# ----------------------------------------------------------------------------- 范围内明显变化 / 趋势预警
# 小基数指标的绝对变化下限（单位档：正则, 小基数基线上限, 绝对变化下限）。EO/嗜碱/MO#/TBIL 等基线接近
# 检测下限的指标，30% 百分比门槛噪音大（RUX 趋势信号约 1/3 为噪音）：基线绝对值低于该档上限时，
# 趋势/幅度判据要求同向变化同时达到绝对下限；大基数指标（基线 ≥上限）百分比判据不变。只收噪音，不改口径（提示不发质疑）。
_ABS_FLOOR = [
    (re.compile(r'10\s*[\^*×x]?9\s*/\s*l', re.I), 0.5, 0.3),    # ×10^9/L（含 /×10^9/L 装饰斜杠）：基线 <0.5 → 变化 ≥0.3
    (re.compile(r'10\s*[\^*×x]?12\s*/\s*l', re.I), 0.5, 0.3),   # ×10^12/L：基线 <0.5 → 变化 ≥0.3
    (re.compile(r'[uµ]mol\s*/\s*l', re.I), 10.0, 3.0),          # µmol/L（TBIL 等）：基线 <10 → 变化 ≥3
]


def abs_floor(bv, unit):
    """小基数指标的绝对变化下限（None＝沿用百分比判据）。bv／unit 任一缺失或 bv≤0 时不设限。"""
    if not isinstance(bv, (int, float)) or bv <= 0:
        return None
    u = str(unit or '').replace('µ', 'u').replace('μ', 'u').lower()
    for rx_, bmax, amin in _ABS_FLOOR:
        if rx_.search(u):
            return amin if bv < bmax else None
    return None


def _cr_abs(unit):
    u = re.sub(r'\s', '', str(unit or '')).lower().replace('µ', 'u').replace('μ', 'u')
    return 0.3 if 'mg/dl' in u else 26.5 if 'umol/l' in u else None


def _in_range(r):
    v = r.get('value')
    return isinstance(v, (int, float)) and not r.get('oor') and not (r.get('grade') or 0)


def _hours(a, b):
    """b − a 的小时数；没有时刻时按日期差（同日/次日视为 ≤48 小时）。"""
    d = days(b.get('date'), a.get('date'))
    if d is None:
        return None
    ta, tb = str(a.get('time') or ''), str(b.get('time') or '')
    m1, m2 = re.match(r'(\d{1,2}):(\d{2})', ta), re.match(r'(\d{1,2}):(\d{2})', tb)
    if m1 and m2:
        return d * 24 + (int(m2.group(1)) - int(m1.group(1))) + (int(m2.group(2)) - int(m1.group(2))) / 60
    return d * 24 if d <= 1 else d * 24 + 24


def lab_shift(C, add_other):
    """两类提示信号（pr＝2，不发质疑）：范围内明显变化、持续变化趋势。add_other 由 mm_build 传入（避免循环导入）。"""
    tb = float((C.cfg.get('thresholds') or {}).get('base', 0.3))
    skip = re.compile(C.A.get('entryCheckExclude') or r'尿.*(白细胞|红细胞|隐血|潜血|管型|上皮|细菌|结晶|酵母)|隐血|潜血')
    conv = C.A.get('unitConv', {})
    for (sid, mid), rows in C.F.items():
        if sid not in C.pop or mid.split(':')[0] not in ('lab', 'vs', 'ecg'):
            continue
        label = C.metric[mid]['label']
        if skip.search(label):
            continue
        code = C.cmap.get(mid)
        post = [r for r in rows if r.get('post') and isinstance(r.get('value'), (int, float)) and not r.get('_entry')]
        b = next((r.get('base') for r in rows if r.get('base')), None)
        bv = (b or {}).get('value') if isinstance((b or {}).get('value'), (int, float)) else None

        def emit(r, summ, crit):
            add_other(C, sid, '范围内明显变化', 2, summ, r.get('visit'), r.get('date'), r.get('sheet'), r.get('row'), label, r.get('clin'),
                      None, [crit], '', {'query': False}, bkey=f"{label}|{crit[:12]}|{r.get('visit') or ''}|{r.get('date') or ''}", wb=r.get('wb') or '')
        if code == 'CREAT':
            done = False
            for a, r in zip(post, post[1:]):
                h, thr = _hours(a, r), _cr_abs(r.get('unit') or a.get('unit'))
                if thr and h is not None and h <= 48 and r['value'] - a['value'] >= thr and _in_range(r):
                    emit(r, f"{label} {r.get('visit') or ''} {r.get('raw')} {r.get('unit') or ''}，较前次（{a.get('visit') or dshow(a.get('date'))} {a.get('raw')}）"
                            f"升高 {fmt(r['value'] - a['value'])}（48 小时内），仍在参考范围内",
                         '参照 KDIGO 2012 急性肾损伤标准：48 小时内升高 ≥0.3 mg/dL（26.5 µmol/L）')
                    done = True
                    break
            if not done and bv:
                r = next((x for x in post if x['value'] >= 1.5 * bv and _in_range(x)), None)
                if r:
                    emit(r, f"{label} {r.get('visit') or ''} {r.get('raw')} {r.get('unit') or ''}，为基线（{b.get('raw')}）的 {r['value'] / bv:.1f} 倍，仍在参考范围内",
                         '参照 KDIGO 2012 急性肾损伤幅度：较基线 ≥1.5 倍（标准要求 7 天内，试验采样间隔通常更长，仅作提示）')
        elif code == 'HGB' and bv:
            def fac(x):
                u = x.get('unit') or ''
                return conv.get(mid, {}).get(u) if u in conv.get(mid, {}) else C.G.factor('HGB', u)
            r = next((x for x in post if fac(x) and (bv - x['value']) * fac(x) >= 20 and _in_range(x)), None)
            if r:
                emit(r, f"{label} {r.get('visit') or ''} {r.get('raw')} {r.get('unit') or ''}，较基线（{b.get('raw')}）下降 {fmt((bv - r['value']) * fac(r))} g/L，仍在参考范围内",
                     '参照 ISTH 大出血判据中的血红蛋白降幅（≥20 g/L）')
        elif code == 'QTCF' and bv:
            r = next((x for x in post if x['value'] - bv > 60 and _in_range(x)), None)
            if r:
                emit(r, f"{label} {r.get('visit') or ''} {r.get('raw')} {r.get('unit') or 'ms'}，较基线（{b.get('raw')}）增加 {fmt(r['value'] - bv)} ms，尚未达异常分级",
                     '参照 ICH E14：QTc 较基线增加 >60 ms')
        # 趋势预警：朝不利方向连续 3 次变化、累计较基线 ≥T_base，且给药后全部结果仍在参考范围内
        d = ext_rules.metric_dir(mid) or ext_rules.metric_dir(label)
        if d not in ('up', 'down') or not bv or len(post) < 3 or not all(_in_range(x) for x in post):
            continue
        sg = 1 if d == 'up' else -1
        run = 1                                                # 末端连续不利变化的取值个数
        for a, r in zip(post, post[1:]):
            run = run + 1 if (r['value'] - a['value']) * sg > 0 else 1
        last, first = post[-1], post[-run]
        pct = (last['value'] - bv) / abs(bv) * 100
        p0 = (last['value'] - first['value']) / abs(first['value']) * 100 if first['value'] else 0
        af = abs_floor(bv, last.get('unit') or b.get('unit'))
        if run >= 4 and pct * sg >= tb * 100 and p0 * sg >= tb * 100 and (af is None or (last['value'] - bv) * sg >= af):
            seq = ' → '.join(str(x.get('raw')) for x in post[-run:])
            add_other(C, sid, '持续变化趋势', 2,
                      f"{label} 连续 {run - 1} 次{'升高' if d == 'up' else '下降'}（{seq} {last.get('unit') or ''}），末次较基线（{b.get('raw')}）{pct:+.0f}%，仍在参考范围内",
                      last.get('visit'), last.get('date'), last.get('sheet'), last.get('row'), label, last.get('clin'), None,
                      [f'趋势预警：朝不利方向连续变化、累计较基线 ≥{tb:.0%}，尚未超出参考范围'], '', {'query': False},
                      bkey=f"{label}|趋势", wb=last.get('wb') or '')


# ----------------------------------------------------------------------------- 数据可信度
_META_RX = re.compile(r'页面号|访视号|访视OID|表单OID|页码|行号|记录号|序号|数据页|Instance|_UNIT$', re.I)


def stable_metrics(C, share=0.6):
    """V6 R12（审阅者 2026-11-02，构建 Agent 复盘：身高在 SAR 产生假「全程不变」）：按数据形态、不列名单——
    vs/pe 数值指标中，≥2 次测量的受试者里有 ≥60% 全程取值相同（且 ≥5 人可评）→ 该指标本身在受试者内稳定，
    「全程不变」不是可疑信号。"""
    tot, same = Counter(), Counter()
    for (sid, mid), rows in C.F.items():
        if mid.split(':')[0] not in ('vs', 'pe'):
            continue
        vals = [r['value'] for r in rows if isinstance(r.get('value'), (int, float))]
        if len(vals) >= 2:
            tot[mid] += 1
            same[mid] += len(set(vals)) == 1
    return {m for m, n in tot.items() if n >= 5 and same[m] / n >= share}


def cred(C):
    """中心层面数据可信度信号（建议核对，不作结论）。→ {sites:{site:{dig,flat,shift,dup}}, flat:[…], dup:[…], shiftTop:{site:[…]}}
    用户 2026-11-01 裁定：按域动态选，不预设指标名单——vs＋pe 域（语义＝人工/设备直接测量）的全部数值型指标；
    研究没有的指标自然跳过，只显示该研究有的内容。同日相同泛化为「≥3 项测量全部相同」。"""
    S = C.subj
    sites = sorted({s['site'] for s in S.values()})
    dig = defaultdict(lambda: [0, 0])
    flat_e, flat_n, flat_items = Counter(), Counter(), []
    trip = defaultdict(dict)                                   # (site, date) → {sid: {mid: value}}
    base = defaultdict(dict)                                   # mid → {sid: 基线值}
    stable = stable_metrics(C)
    for (sid, mid), rows in C.F.items():
        if sid not in S:
            continue
        site, label, dom = S[sid]['site'], C.metric[mid]['label'], mid.split(':')[0]
        if dom not in ('vs', 'pe') or _META_RX.search(label):
            continue                                           # 检验多为各中心本地实验室，方法/单位差异天然存在；EDC 元数据列（页面号等）不是测量指标
        if mid in stable:
            continue                                           # V6 R12：受试者内天然不变的指标（如成人身高）不作「全程不变/同日相同」信号
        num = [r for r in rows if isinstance(r.get('value'), (int, float))]
        for r in num:
            raw = str(r.get('raw') if r.get('raw') is not None else '').strip()
            if re.fullmatch(r'\d{2,3}', raw):
                dig[site][0] += 1
                dig[site][1] += raw[-1] in '05'
            if is_full_date(r.get('date')):
                trip[(site, r['date'])].setdefault(sid, {})[mid] = r['value']
        if len(num) >= 4:
            flat_e[site] += 1
            if len({r['value'] for r in num}) == 1:
                flat_n[site] += 1
                flat_items.append([sid, site, label, str(num[0].get('raw')), len(num)])
        b = next((r.get('base') for r in rows if r.get('base')), None)
        mu_ = (C.metric[mid]['units'].most_common(1) or [('', 0)])[0][0]
        if b and isinstance(b.get('value'), (int, float)) and (b.get('unit') or '') == mu_:
            base[mid][sid] = b['value']
    out = {s: {} for s in sites}
    n_all, k_all = sum(v[0] for v in dig.values()), sum(v[1] for v in dig.values())
    ps = [(s, binom_upper(dig[s][1], dig[s][0], 0.2) if dig[s][0] >= 30 else None) for s in sites]
    for (s, p), q in zip(ps, bh([p for _, p in ps])):
        out[s]['dig'] = [dig[s][0], dig[s][1], p, q]
    rate = sum(flat_n.values()) / (sum(flat_e.values()) or 1)
    ps = [(s, pois_upper(flat_n[s], rate * flat_e[s]) if flat_e[s] else None) for s in sites]
    for (s, p), q in zip(ps, bh([p for _, p in ps])):
        out[s]['flat'] = [flat_e[s], flat_n[s], p, q]
    tests = []                                                 # (site, mid, z, n, 中心均值, 整体均值)
    for mid, vals in base.items():
        if len(vals) < 30:
            continue
        allv = list(vals.values())
        mu, sd = statistics.mean(allv), statistics.pstdev(allv)
        if not sd:
            continue
        bys = defaultdict(list)
        for sid, v in vals.items():
            bys[S[sid]['site']].append(v)
        for s, vs in bys.items():
            if len(vs) >= 3:
                tests.append((s, mid, (statistics.mean(vs) - mu) / (sd / math.sqrt(len(vs))), len(vs), statistics.mean(vs), mu))
    qs = bh([norm_two(t[2]) for t in tests])
    for s in sites:
        mine = [(t, q) for t, q in zip(tests, qs) if t[0] == s]
        atyp = sorted([(t, q) for t, q in mine if q is not None and q < 0.05], key=lambda x: -abs(x[0][2]))
        out[s]['shift'] = [len(mine), len(atyp), [[C.metric[t[1]]['label'], round(t[2], 1), t[3], fmt(t[4]), fmt(t[5])] for t, _ in atyp[:5]]]
    dup_items = []
    for (site, date), m in trip.items():
        full = {sid: tuple(sorted(x.items())) for sid, x in m.items() if len(x) >= 3}   # ≥3 项测量成向量，全同才比
        grp = defaultdict(list)
        for sid, t in full.items():
            grp[t].append(sid)
        for t, sids in grp.items():
            if len(sids) >= 2:
                dup_items.append([site, date, sorted(sids), '/'.join(fmt(v) for _, v in t)])
    dc = Counter(d[0] for d in dup_items)
    for s in sites:
        out[s]['dup'] = [dc.get(s, 0)]
    return {'sites': out, 'flat': flat_items[:300], 'dup': dup_items[:200], 'digAll': [n_all, k_all],
            'flatRate': rate, 'note': '参照 Venet 等 2012（Clin Trials 9(6):705–713）集中统计监查思路的简化版；只提示中心层面的异常模式，需结合源数据核对，不作结论'}


def finalize(C):
    """build_ops 之后调用：补齐 ops（due/upcoming/fresh/fu/planned）、KRI、CtQ、数据可信度。"""
    cut = C.ops.get('cutoff') or ''
    C.ops['due'], C.ops['upcoming'] = visit_due(C, cut)
    C.ops['visitAlias'], C.ops['visitUnmapped'] = getattr(C, '_visit_alias', {}), getattr(C, '_visit_unmapped', [])
    C.ops['visitArm'] = getattr(C, '_visit_arm', [])          # 组别专属访视（不推算逾期）
    C.ops['fresh'] = freshness(C, cut)
    C.ops['fu'] = followup(C, cut)
    C.ops['planned'] = C.ops.get('planned') or planned_n(C)
    C.ops['nnum'] = dict(Counter(C.subj[f['sid']]['site'] for f in C.findings if f['sid'] in C.subj and isinstance(f.get('value'), (int, float))
                                 and str(f.get('mid') or '').split(':')[0] in ('lab', 'vs', 'ecg')))
    ctq(C)
    C.kri = kri(C)
    C.cred = cred(C)
