"""Declarative toxicity grading (CTCAE v5.0 / v6.0 / custom) — evaluator shared with templates/site/assets/ctcae.js.

Tables live in scripts/grading/<system>_v<version>.json (or any JSON file given in cfg.grading.file) and are emitted to the
report as data/grading.js so the front-end grades with exactly the same rules.

Table schema
  {"system","version","label","source","units":{CODE:{"_std":"g/L","g/dl":10,...}},"ratio":[codes graded only by ×ULN/×LLN/×baseline],
   "items":{CODE:[{"term","zh","dir":"H|L","when":"baseNormal|baseAbnormal"?,"note"?,
                   "absolute"?: true,
                   "steps":[{"by":"val|xuln|xlln|xbase|chg|pct|duln","op":">|>=|<|<=","v":number|"ULN"|"LLN"|"BASE","g":1-4,"and":[step...]?}]}]}}
Grade of a criterion = max g of satisfied steps; overall = max over criteria. Steps that need a baseline (xbase/chg/pct/BASE) are skipped
when no baseline is available or the value *is* the baseline. Only numeric criteria belong in a table — grades that need symptoms,
intervention or clinical consequence must not be auto-graded.

API
  G = load(cfg, study_dir)      cfg = study.json cfg; reads cfg.grading {system, version, file, overrides} or legacy cfg.ctcaeVersion
  G.has(code) · G.grade(code, v, lln, uln, base=None, is_base=False) -> (g, zh_term, dir) | None · G.factor(code, unit) -> float | None
  automap(metrics, G, overrides) -> {metric_id: code}
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent / 'grading'


def parse_version(s):
    """'CTCAE v5.0' / 'ctcae 5' / 'v6' / '5.0' → ('CTCAE', '5.0'); unknown systems keep their name."""
    if not s:
        return None, None
    s = str(s).strip()
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    ver = m.group(1) if m else None
    if ver and '.' not in ver:
        ver += '.0'
    sysname = re.sub(r'[\s_-]*v?\d+(\.\d+)*.*$', '', s, flags=re.I).strip() or 'CTCAE'
    return sysname.upper() if sysname.upper() == 'CTCAE' else sysname, ver


def norm_unit(u):
    if u is None:
        return ''
    s = str(u).strip().lower().replace('μ', 'µ').replace('u/l', 'u/l').replace(' ', '')
    s = s.replace('×', '').replace('x10', '10').replace('*10', '10^').replace('e9', '^9').replace('e3', '^3')
    s = s.replace('10^^', '10^').replace('10^9/l', '10^9/l')
    return s


class Grader:
    def __init__(self, table):
        self.t = table
        self.items = table.get('items', {})
        self.units = {k: {norm_unit(u) if u != '_std' else '_std': f for u, f in v.items()} for k, v in table.get('units', {}).items()}
        self.ratio = set(table.get('ratio', []))
        self.label = table.get('label') or f"{table.get('system', 'CTCAE')} v{table.get('version', '')}"

    def has(self, code):
        return bool(code) and code in self.items

    def factor(self, code, unit):
        """Multiplier converting `unit` to the table's standard unit; 1 for ratio-graded codes; None = unknown unit (do not grade)."""
        if code in self.ratio or code not in self.units:
            return 1.0
        u = norm_unit(unit)
        if not u:
            return 1.0  # unit not recorded: assume standard unit (flagged by caller)
        tab = self.units[code]
        if u in tab:
            return float(tab[u])
        std = norm_unit(tab.get('_std'))
        return 1.0 if u == std else None

    @staticmethod
    def _x(by, v, l, u, b):
        try:
            return {'val': v, 'xuln': v / u if u else None, 'xlln': v / l if l else None, 'xbase': v / b if b else None,
                    'chg': v - b if b is not None else None, 'pct': (v - b) / abs(b) * 100 if b else None,
                    'duln': v - u if u is not None else None}[by]
        except (TypeError, ZeroDivisionError):
            return None

    def _ok(self, st, v, l, u, b):
        by = st.get('by', 'val')
        x = self._x(by, v, l, u, b)
        thr = st.get('v')
        thr = {'ULN': u, 'LLN': l, 'BASE': b}.get(thr, thr) if isinstance(thr, str) else thr
        if x is None or thr is None:
            return False
        op = st.get('op', '>')
        ok = {'>': x > thr, '>=': x >= thr, '<': x < thr, '<=': x <= thr}[op]
        return ok and all(self._ok(a, v, l, u, b) for a in st.get('and', []))

    def grade(self, code, v, lln=None, uln=None, base=None, is_base=False):
        crit = self.items.get(code)
        if not crit or v is None:
            return None
        b = None if is_base else base
        best = (0, '', '')
        for c in crit:
            d = c.get('dir', 'H')
            ab = b is not None and ((d == 'H' and uln is not None and b > uln) or (d == 'L' and lln is not None and b < lln))
            if c.get('when') == 'baseAbnormal' and not ab:
                continue
            if c.get('when') == 'baseNormal' and ab:
                continue
            if c.get('absolute'):
                pass  # absolute thresholds (e.g. TG, INR, QTc) apply regardless of the lab's reference range
            elif d == 'H' and uln is not None and v <= uln and not ab and not any(s.get('by') in ('chg', 'pct') for s in c['steps']):
                continue
            elif d == 'L' and lln is not None and v >= lln and not any(s.get('by') in ('chg', 'pct', 'xlln') for s in c['steps']):
                continue
            g = max([s['g'] for s in c['steps'] if self._ok(s, v, lln, uln, b)] + [0])
            if g > best[0]:
                best = (g, c.get('zh') or c.get('term', ''), d)
        return best


def table_path(cfg, study_dir=None):
    gcfg = cfg.get('grading') or {}
    if gcfg.get('file'):
        p = Path(gcfg['file'])
        return p if p.is_absolute() else Path(study_dir or '.') / p
    sysname, ver = (gcfg.get('system') or 'CTCAE'), gcfg.get('version')
    if not ver:
        s2, ver = parse_version(cfg.get('ctcaeVersion'))
        sysname = s2 or sysname
    if not ver:
        raise SystemExit('grading: 未指定分级标准版本（cfg.grading.version 或 cfg.ctcaeVersion）。请从方案中抽取（如 CTCAE v5.0），不得默认。')
    p = HERE / f"{sysname.lower()}_v{ver}.json"
    if not p.exists():
        avail = ', '.join(x.stem for x in HERE.glob('*_v*.json'))
        raise SystemExit(f'grading: 未内置 {sysname} v{ver}（已内置：{avail}）。请用 ctcae_import.py 或手写表并通过 cfg.grading.file 指定。')
    return p


def load(cfg, study_dir=None):
    t = json.loads(Path(table_path(cfg, study_dir)).read_text(encoding='utf-8'))
    ov = (cfg.get('grading') or {}).get('overrides') or {}
    for code, crit in ov.items():  # protocol-specific modifications (e.g. protocol toxicity table replaces an item)
        if crit is None:
            t['items'].pop(code, None)
        else:
            t['items'][code] = crit
    if (cfg.get('grading') or {}).get('label'):
        t['label'] = cfg['grading']['label']
    return Grader(t)


def automap(metrics, G, overrides=None):
    """metrics: {metric_id: {'label','domain','units':Counter}} → {metric_id: code}. overrides (cfg.ctcaeMap) win; '' disables."""
    an = json.loads((HERE / 'analytes.json').read_text(encoding='utf-8'))
    out, overrides = {}, overrides or {}
    for mid, m in metrics.items():
        if mid in overrides:
            if overrides[mid]:
                out[mid] = overrides[mid]
            continue
        dom, label = m.get('domain'), m.get('label') or mid.split(':', 1)[-1]
        units = [u for u in (m.get('units') or {}) if u]
        if any(re.search(r'%|百分比', u) for u in units):
            continue
        for code, (d, inc, exc) in an.items():
            if d != dom or not G.has(code):
                continue
            if re.search(inc, label, re.I) and not (exc and re.search(exc, label, re.I)):
                out[mid] = code
                break
    return out


if __name__ == '__main__':
    for ver in ('5.0', '6.0'):
        G = load({'grading': {'version': ver}})
        assert G.grade('ALT', 130, None, 40, 20)[0] == 2, ver
        assert G.grade('QTCF', 490, None, None, 420)[0] == 3, ver
        assert G.grade('HGB', 85, 115, 150)[0] == 2, ver
        assert G.grade('ALT', 30, None, 40, 20)[0] == 0, ver
        assert G.factor('HGB', 'g/dL') == 10 and G.factor('PLT', '10^3/µL') == 1 and G.factor('PLT', '/mm3') == 0.001
        assert G.factor('NA', 'foo') is None
    G5, G6 = load({'ctcaeVersion': 'CTCAE v5.0'}), load({'ctcaeVersion': 'CTCAE v6.0'})
    assert G5.grade('ANC', 1.2, 2.0, 7.0)[0] == 2 and G6.grade('ANC', 1.2, 2.0, 7.0)[0] == 1  # v5 vs v6 neutrophil cut-offs
    assert G5.grade('ALT', 70, None, 40, 45)[0] == 1 and G6.grade('ALT', 50, None, 40, 45)[0] == 1 and G5.grade('ALT', 50, None, 40, 45)[0] == 0
    assert G5.grade('EOS', 0.8, 0, 0.5, 0.9)[0] == 0 and G5.grade('EOS', 0.8, 0, 0.5, 0.3)[0] == 1
    assert G5.grade('QTCF', 455, None, 460)[0] == 1 and G5.grade('TG', 2.0, None, 2.3)[0] == 1
    print('ctcae ok', G5.label, G6.label)
