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
# 关联字段的通用写法（EDC 厂商各异）：'AE+1+头痛'、'MH+4+贫血'、'病史-3 - 贫血 - 2020-01-01'、'不良事件-2 - 头痛 - 2026-03-01'、
# 'AE 3'、'MH#2'；多条以 ; , 、 换行 或连续空格分隔。类型 → AE / MH / CM。
LINK_START = re.compile(r'(?<![A-Za-z一-鿿])(AE|MH|CM|不良事件|既往病史|既往史|病史|合并用药)\s*[+＋_\-－#＃：:]?\s*(\d+)', re.I)
LINK_TYPE = {'ae': 'AE', '不良事件': 'AE', 'mh': 'MH', '病史': 'MH', '既往病史': 'MH', '既往史': 'MH', 'cm': 'CM', '合并用药': 'CM'}
_LINK_DATE_TAIL = re.compile(r'[\s\-－]+(\d{4}|uk|UK|UNK)[-/.]([\dA-Za-z]{1,3})[-/.]([\dA-Za-z]{1,3})\s*$')


def parse_links(v, link_re=None):
    """关联字段 → [[类型, 术语, None, 编号]]。`link_re`（mapping 级覆盖）为含命名组 type/no/term 的正则，按 finditer 取全部。"""
    out = []
    if not v:
        return out
    s = str(v)
    if link_re:
        for m in re.finditer(link_re, s):
            g = m.groupdict()
            t = LINK_TYPE.get(str(g.get('type') or '').lower(), str(g.get('type') or '').upper())
            no = g.get('no')
            out.append([t, (g.get('term') or '').strip(), None, int(no) if no and str(no).isdigit() else no])
        return out
    starts = list(LINK_START.finditer(s))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(s)
        tail = re.split(r'[;；,，、\n]', s[m.end():end])[0]
        tail = _LINK_DATE_TAIL.sub('', tail.rstrip()).strip(' +＋-－_:：')
        out.append([LINK_TYPE.get(m.group(1).lower(), m.group(1).upper()), tail.strip(), None, int(m.group(2))])
    return out
