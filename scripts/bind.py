"""V6 口径↔数据指标重绑（审阅者 2026-11-02，四项目复盘）：方案编译出的指标正则在数据里零命中时，按指标名的常见写法
差异重绑，避免阈值/入排/组合规则对整个指标静默失效。

已证实的落空形态（只读复盘）：
- 词典把缩写锚在开头（`^lab:(?:丙氨酸氨基转移酶|(ALT|SGPT|GPT)\\b)`），数据写「丙氨酸基转移酶（ALT）」——中文名少一字、缩写在括注里；
- 写死域前缀：血压以 `lab:收缩压` 入库（`^vs:` 落空）、QTcF 以 `exam:` 入库（`^ecg:` 落空）。

重绑只在原正则**一个指标都匹配不上**时发生：对每个数据指标试 原 mid、「规则域:括注缩写」「规则域:去括注名」「数据域:…」等变体；
命中则把规则改写成精确的 `^(?:mid…)$`，并记下说明（KZ.study.bindNotes，研究依据页可见）。原正则有命中的不动。
"""
import re

_BRACKET = re.compile(r'[（(]([^（）()]+)[)）]')


def label_variants(label):
    """指标名的可比写法：原文、括注内容（缩写/英文名）、去括注主干。"""
    s = str(label or '').strip()
    inner = [x.strip() for x in _BRACKET.findall(s) if x.strip()]
    base = _BRACKET.sub('', s).strip()
    return [x for x in dict.fromkeys([s] + inner + [base]) if x]


def _variants(mid, label, pattern):
    dom = mid.split(':', 1)[0]
    m = re.match(r'\^\(?\??:?(\w+)\)?:', pattern or '')
    doms = list(dict.fromkeys([dom] + ([m.group(1)] if m and m.group(1) != 'w' else [])))
    return list(dict.fromkeys([mid] + [f'{d}:{x}' for d in doms for x in label_variants(label)]))


def rebind_one(pattern, metrics):
    """→ (新正则或 None, 命中的 mid 列表)。原正则有命中返回 (None, [])。"""
    try:
        rx = re.compile(pattern)
    except (re.error, TypeError):
        return None, []
    if any(rx.search(mid) for mid in metrics):
        return None, []
    hits = [mid for mid, m in metrics.items() if any(rx.search(v) for v in _variants(mid, m.get('label') or mid.split(':', 1)[-1], pattern))]
    if not hits:
        return None, []
    return '^(?:' + '|'.join(re.escape(h) for h in hits) + ')$', hits


_CORE_TAIL = re.compile(r'(量表|问卷|评分表)?(总得分|总分|得分|评分|分数|分值)$')


def name_core(name):
    """量表/指标名的可比核心：去括注、空白、尾部「量表总得分/总分/评分」（PGI-C总分 ≡ PGI-C量表总得分）。"""
    s = re.sub(r'\s+', '', _BRACKET.sub('', str(name or '')))
    return _CORE_TAIL.sub('', s).upper()


def rebind_eff(C, notes):
    """有效性终点的 src（「eff:PGI-C总分」「lab:血红蛋白（Hb）」）在数据中不存在时，按名称核心唯一匹配重绑。"""
    effn = {str(e.get('metric')) for e in getattr(C, 'efficacy', None) or [] if e.get('metric')}
    have = {f'eff:{n}' for n in effn} | set(getattr(C, 'metric', None) or {})
    for m in C.A.get('efficacy') or []:
        src = m.get('src')
        if not src or src in have or ':' not in src:
            continue
        dom, nm = src.split(':', 1)
        core = name_core(nm)
        if not core:
            continue
        cands = sorted({h for h in have if h.split(':', 1)[0] == dom and name_core(h.split(':', 1)[1]) == core})
        if not cands:                                      # 再试括注缩写/去括注主干（lab:血红蛋白 ↔ lab:血红蛋白（Hb））
            vs = {name_core(x) for x in label_variants(nm)}
            cands = sorted({h for h in have if h.split(':', 1)[0] == dom
                            and vs & {name_core(x) for x in label_variants(h.split(':', 1)[1])}})
        if len(cands) == 1:
            notes.append(f"有效性终点「{m.get('label') or nm}」：数据中无「{nm}」，已按名称核心对齐到「{cands[0].split(':', 1)[1]}」")
            m['src'] = cands[0]


def rebind(C):
    """改写 C.A 中各规则的指标正则（原地）＋ C.mthr；返回说明列表（同时存 C.bind_notes）。"""
    notes = []

    def fix(holder, key, where):
        if not isinstance(holder, dict) or not holder.get(key):
            return
        new, hits = rebind_one(holder[key], C.metric)
        if new:
            notes.append(f"{where}：原指标正则在数据中零命中，已按括注缩写/域别名重绑到 "
                         + '、'.join(C.metric[h]['label'] for h in hits[:4]) + ('…' if len(hits) > 4 else ''))
            holder[key] = new
    for R in C.A.get('thresholdRules') or []:
        fix(R, 'metric', f"阈值规则「{R.get('label') or R.get('id') or ''}」")
    for R in C.A.get('comboRules') or []:
        for c in (R.get('all') or []) + (R.get('none') or []):
            fix(c, 'metric', f"组合规则「{R.get('label') or R.get('id') or ''}」")
    for E in C.A.get('eligibility') or []:
        fix(E, 'metric', f"入排「{E.get('id') or E.get('text', '')[:20]}」")
        fix(E.get('gate'), 'metric', f"入排「{E.get('id') or ''}」伴随条件")
        fix(E.get('bili'), 'metric', f"入排「{E.get('id') or ''}」胆红素例外")
    for T in getattr(C, 'mthr', None) or []:
        fix(T, 'metric', '方案收紧阈值')
    rebind_eff(C, notes)
    C.bind_notes = notes
    return notes
