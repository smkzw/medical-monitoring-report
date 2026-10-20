"""Shared helpers for the medical-monitoring engine."""
import datetime as _dt
import json
import math
import re
from pathlib import Path

DATE_RE = re.compile(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})')


def load_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding='utf-8'))


def dump_json(obj, p):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


def norm_date(v):
    """→ 'YYYY-MM-DD' | partial raw string | None. Partial dates (UK/UNK) are kept raw and never imputed."""
    if v is None or v == '':
        return None
    if isinstance(v, _dt.datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, _dt.date):
        return v.isoformat()
    s = str(v).strip()
    m = DATE_RE.search(s)
    if m:
        y, mo, d = m.groups()
        try:
            return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return s
    return s or None


def is_full_date(s):
    return isinstance(s, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', s) is not None


def days(a, b):
    """a - b in days (None when either is not a full date)."""
    if not (is_full_date(a) and is_full_date(b)):
        return None
    return (_dt.date.fromisoformat(a) - _dt.date.fromisoformat(b)).days


def study_day(d, fd):
    x = days(d, fd)
    return None if x is None else (x + 1 if x >= 0 else x)


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).strip().replace(',', '')
    if re.fullmatch(r'[-+]?\d+(\.\d+)?([eE][-+]?\d+)?', s):
        return float(s)
    m = re.fullmatch(r'[<>≤≥]=?\s*([-+]?\d+(\.\d+)?)', s)
    if m:  # censored values: keep the bound but caller sees raw
        return float(m.group(1))
    return None


def yes(v):
    if v is None:
        return False
    return str(v).strip().lower() in ('是', 'y', 'yes', '1', 'true', '有', '√')


def fmt(x, nd=2):
    if x is None:
        return '—'
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f'{x:.{nd}f}'.rstrip('0').rstrip('.')


def quantile(a, q):
    a = sorted(a)
    if not a:
        return None
    p = (len(a) - 1) * q
    lo = math.floor(p)
    hi = math.ceil(p)
    return a[lo] + (a[hi] - a[lo]) * (p - lo)


CLIN_DEFAULT = [(r'无临床意义|NCS|not\s*clinically', 1), (r'有临床意义|^CS$|clinically\s*significant', 2), (r'正常|normal|^N$', 0)]


def clin_code(v, patterns=None):
    if v is None or str(v).strip() == '':
        return None
    s = str(v).strip()
    for pat, code in (patterns or CLIN_DEFAULT):
        if re.search(pat, s, re.I):
            return code
    return None


LINK_RE = re.compile(r'(AE|MH)\s*[+＋_\-]\s*(\d+)\s*[+＋_\-]?\s*(.*)', re.I)


def parse_links(v):
    """Dynamic link text such as 'AE+1+头痛' / 'MH+4+贫血' (multiple separated by ; , 、 or newline)."""
    out = []
    if not v:
        return out
    for part in re.split(r'[;；,，、\n]+', str(v)):
        m = LINK_RE.search(part.strip())
        if m:
            out.append([m.group(1).upper(), m.group(3).strip(), None, int(m.group(2))])
    return out
