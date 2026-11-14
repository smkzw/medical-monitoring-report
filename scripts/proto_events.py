"""方案事件（PLAN §17.20，2026-11-14）：方案规定的逐条事件记录（哮喘急性发作、哮喘控制不佳、复发、出血发作…），不限病种。

数据：norm/events.json（mapping 域 events：sid, type, start, end, ongoing, treat, hosp, period, link_cm, link_ae, desc …）。
产出：
- C.pev（全部事件）、C.pev_by[sid]（个例时间线/清单）；
- summarize() → KZ.pev：各事件类型的事件数、发生人数、暴露人年、年化发生率（全试验/各中心；盲态不分组）、按月计数、
  住院/急诊次数、与方案终点的对应；方案事件型终点找不到数据来源 → missing（可见，不静默）；
- in_event_window()：合并用药是否在方案事件期间（全身激素「控制急性发作除外」类例外按发作期自动判定）；
- checks()：事件需住院/急诊治疗但未见同期 SAE → 一致性核对（封闭式问法）。
"""
import re
from collections import Counter, defaultdict

from common import days, is_full_date, yes

_HOSP = re.compile(r'住院')
_ER = re.compile(r'急诊')
_PRE = re.compile(r'既往|筛选前|筛选期|导入期|入组前|基线前')
_EVENT_EP = re.compile(r'事件|发作|发生率|复发|次数')
_YN = re.compile(r'(是|否|有|无|Y|N|Yes|No|1|0|√)?', re.I)


def _bigrams(s):
    s = re.sub(r'[^一-鿿A-Za-z0-9]', '', str(s or ''))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _close(a, b, k=3):
    """两段中文描述是否指同一类事件：共享 ≥k 个二字组（「重度哮喘急性发作记录」~「重度哮喘急性发作事件的年化发生率」）。"""
    return len(_bigrams(a) & _bigrams(b)) >= k


def build(C):
    C.pev, C.pev_by = [], defaultdict(list)
    for i, r in enumerate(getattr(C, 'events', []) or []):
        sid = str(r.get('sid') or '').strip()
        if not sid or sid not in C.subj:
            continue
        treat = ' '.join(str(r.get(k) or '') for k in ('treat', 'hosp', 'desc'))
        s = r.get('start') or ''
        fd = C.subj[sid].get('fd') or ''
        pre = bool(_PRE.search(str(r.get('period') or '') + str(r.get('type') or ''))) or \
            (is_full_date(s) and is_full_date(fd) and s < fd)
        t = str(r.get('type') or '').strip()
        if not t or _YN.fullmatch(t):                 # 事件名缺省或取到勾选值 → 表单中文名（「#1-日期」实例后缀去掉）
            t = re.sub(r'\s*#.*$', '', str(((getattr(C, 'A', None) or {}).get('formNames') or {}).get(r.get('sheet')) or '')) or str(r.get('sheet') or '方案事件')
        sub = str(r.get('sub') or '').strip()
        e = {'n': r.get('no') or i + 1, 't': t, 'sub': '' if _YN.fullmatch(sub) else sub, 's': s, 'e': r.get('end') or '',
             'ong': yes(r.get('ongoing')) if r.get('ongoing') not in (None, '') else False,
             'treat': str(r.get('treat') or ''), 'hosp': bool(_HOSP.search(treat)) or yes(r.get('hosp')) is True,
             'er': bool(_ER.search(treat)), 'period': str(r.get('period') or ''), 'pre': pre,
             'cm': str(r.get('link_cm') or ''), 'ae': str(r.get('link_ae') or ''),
             'row': r.get('row'), 'sh': r.get('sheet') or '', 'wb': r.get('wb') or ''}
        C.pev.append(dict(e, sid=sid))
        C.pev_by[sid].append(e)
    for v in C.pev_by.values():
        v.sort(key=lambda x: x['s'] or '9999')


def in_event_window(C, sid, c, text, before=3, after=7):
    """合并用药 c 是否在与 text（方案例外原文）同类的方案事件期间（开始前 before 天至结束后 after 天）内；返回事件或 None。"""
    s = c.get('s') or ''
    if not is_full_date(s):
        return None
    for ev in (getattr(C, 'pev_by', None) or {}).get(sid, []):
        if not _close(ev['t'], text, 2) or not is_full_date(ev['s']):
            continue
        end = ev['e'] if is_full_date(ev['e']) else (ev['s'] if not ev['ong'] else '9999-12-31')
        d0 = days(s, ev['s'])
        if d0 is not None and d0 >= -before and (end == '9999-12-31' or (days(s, end) or 0) <= after):
            return ev
    return None


def checks(C, add_other):
    """事件需住院/急诊治疗（研究期间），同期（±7 天）未见严重不良事件记录 → 一致性核对。"""
    for ev in C.pev:
        if ev['pre'] or not ev['hosp'] or ev['sid'] not in C.pop or not is_full_date(ev['s']):
            continue
        sae = [a for a in C.ae_by.get(ev['sid'], []) if a.get('sae') and is_full_date(a.get('s')) and abs(days(a['s'], ev['s']) or 99) <= 7]
        if sae:
            continue
        add_other(C, ev['sid'], '方案事件与SAE一致性核对', 3,
                  f"{ev['t']}（{ev['s']} 起）处理方式为「{ev['treat'] or '住院'}」，同期（±7 天）未见严重不良事件记录",
                  None, ev['s'], ev['sh'], ev['row'], ev['t'],
                  rule={'ask': f"请确认该次{ev['t']}是否需按严重不良事件报告；如已报告，请关联对应的不良事件记录。"},
                  bkey=f"pev|{ev['n']}|{ev['s']}", wb=ev['wb'])


def summarize(C, cutoff, fu):
    """KZ.pev：fu＝{sid: 随访人日}（monitor_v5.followup 同口径：首剂 → 研究结束/数据截止）。"""
    eps = [e for e in ((C.S.get('study') or {}).get('endpoints') or []) if isinstance(e, (list, tuple)) and len(e) > 1]
    types = []
    for t in sorted({e['t'] for e in C.pev}):
        evs = [e for e in C.pev if e['t'] == t and e['sid'] in C.pop and not e['pre']]
        pre = [e for e in C.pev if e['t'] == t and e['pre']]
        py = sum(fu.values()) / 365.25 if fu else 0
        by_site = defaultdict(list)
        for e in evs:
            by_site[C.subj[e['sid']]['site']].append(e)
        site_py = defaultdict(float)
        for sid, d in fu.items():
            site_py[C.subj[sid]['site']] += d / 365.25
        centers = [{'site': st, 'n': len(by_site.get(st, [])), 'subj': len({e['sid'] for e in by_site.get(st, [])}),
                    'py': round(site_py[st], 1), 'rate': round(len(by_site.get(st, [])) / site_py[st], 2) if site_py[st] else None}
                   for st in sorted(site_py)]
        months = Counter(e['s'][:7] for e in evs if is_full_date(e['s']))
        ep = [[k, x] for k, x in eps if _close(t, x)]
        types.append({'type': t, 'n': len(evs), 'subj': len({e['sid'] for e in evs}), 'py': round(py, 1),
                      'rate': round(len(evs) / py, 2) if py else None,
                      'hosp': sum(e['hosp'] for e in evs), 'er': sum(e['er'] for e in evs),
                      'ongoing': sum(1 for e in evs if e['ong']), 'pre': len(pre), 'preSubj': len({e['sid'] for e in pre}),
                      'centers': centers, 'months': sorted(months.items()), 'endpoints': ep})
    have = [t['type'] for t in types]
    missing = [[k, x] for k, x in eps if _EVENT_EP.search(str(x)) and not any(_close(h, x) for h in have)]
    rows = [[e['sid'], C.subj[e['sid']]['site'], e['t'], e['s'], e['e'], 1 if e['ong'] else 0, e['treat'], 1 if e['hosp'] else 0,
             1 if e['pre'] else 0, e['period'], e.get('sub') or ''] for e in C.pev if e['sid'] in C.subj]
    return {'types': types, 'rows': rows, 'missing': missing, 'cutoff': cutoff,
            'cols': ['参与者', '中心', '事件类型', '开始', '结束', '持续', '处理方式', '住院', '研究前', '阶段', '亚型']}
