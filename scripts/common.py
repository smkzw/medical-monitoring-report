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


def zero_dose(e):
    """给药记录的实际剂量/数量明确为 0（暂停或停药后的占位区间）→ 不算给药。"""
    for k in ('dose_act', 'qty'):
        v = e.get(k)
        if v not in (None, ''):
            try:
                return float(str(v).strip()) == 0
            except ValueError:
                return False
    return False


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


def dshow(d):
    """K95：日期占位渲染——缺失/空值 → 「无日期」（查询文本不得出现 None 占位，validate_contract 会拦）。"""
    s = '' if d is None else str(d).strip()
    return s or '无日期'


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
    for pat, code in list(patterns or []) + CLIN_DEFAULT:   # 项目映射优先，匹配不到时回退通用写法（「异常，无临床意义」「NCS」等）
        if re.search(pat, s, re.I):
            return code
    return None


LINK_RE = re.compile(r'(AE|MH)\s*[+＋_\-]\s*(\d+)\s*[+＋_\-]?\s*(.*)', re.I)
# 关联字段的通用写法（EDC 厂商各异）：'AE+1+头痛'、'MH+4+贫血'、'病史-3 - 贫血 - 2020-01-01'、'不良事件-2 - 头痛 - 2026-03-01'、
# 'AE 3'、'MH#2'；多条以 ; , 、 换行 或连续空格分隔。类型 → AE / MH / CM。
LINK_START = re.compile(r'(?<![A-Za-z一-鿿])(AE|MH|CM|不良事件|既往病史|既往史|病史|合并用药)\s*[+＋_\-－#＃：:]?\s*(\d+)', re.I)
LINK_TYPE = {'ae': 'AE', '不良事件': 'AE', 'mh': 'MH', '病史': 'MH', '既往病史': 'MH', '既往史': 'MH', 'cm': 'CM', '合并用药': 'CM'}
_LINK_DATE_TAIL = re.compile(r'[\s\-－]+(\d{4}|uk|UK|UNK)[-/.]([\dA-Za-z]{1,3})[-/.]([\dA-Za-z]{1,3})\s*$')


_TYPED_ITEM = re.compile(r'^\s*0*(\d+)\s*(?:[>＞\-－]\s*(.*?))?\s*$')


def parse_typed_links(v, typ):
    """关联类型由列决定（病史编号列 / AE 编号列），取值只有「编号>术语>日期」或编号本身 → [[typ, 术语, None, 编号]]。
    取值自带类型前缀（MH-4-…）时按 parse_links 解析。"""
    if not v:
        return []
    s = str(v)
    if LINK_START.search(s):
        return parse_links(s)
    out = []
    for part in re.split(r'[;；,，、\n$|]|\s{2,}', s):          # 多条关联常见分隔：；，、换行 $ |
        part = _LINK_DATE_TAIL.sub('', re.sub(r'[>＞]\s*[\dA-Za-z]{2,4}[-/.][\dA-Za-z]{1,3}[-/.][\dA-Za-z]{1,3}\s*$', '', part.strip()))
        m = _TYPED_ITEM.match(part)
        if m:
            out.append([typ, (m.group(2) or '').strip(' >＞-－'), None, int(m.group(1))])
    return out


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


# ---------------------------------------------------------------- xlsx 容错读取（PLAN §21 P1）
# EDC 全量导出的 xlsx 常带非法 autoFilter（ref="1:1" 之类纯行号区间，实测 65/66 表命中）＋被截断的
# dimension 声明（如 A1）：普通模式 load_workbook 直接抛 ValueError；read_only 按声明截界，静默每表
# 只读 1 行（近空读）。xlsx 读取入口统一走 open_workbook_lenient：干净文件照旧原样加载（零行为变化）；
# 带伤文件宁可慢也要读全——回退普通模式全量解析，普通模式仍因非法 autoFilter 抛错时，先 zipfile
# 副本剥离非法 autoFilter／截断 dimension 后再读。源文件永不改动，副本落在系统临时目录。
_A1_REF = re.compile(r'[A-Z]{1,3}[0-9]{1,7}(?::[A-Z]{1,3}[0-9]{1,7})?$')
_SHEET_PART = re.compile(r'xl/worksheets/[^/]+\.xml$')


def _xml_attrs(tag):
    return dict(re.findall(r'([A-Za-z0-9:._-]+)="([^"]*)"', tag))


def _xlsx_sheet_names(z):
    """sheet XML 部件名 → 表名（workbook.xml + 其 rels 解析，属性顺序无关）。"""
    import html
    rels = {}
    if 'xl/_rels/workbook.xml.rels' in z.namelist():
        for m in re.finditer(r'<Relationship\b[^>]*>', z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'ignore')):
            a = _xml_attrs(m.group(0))
            t = a.get('Target', '')
            t = t.lstrip('/') if t.startswith('/') else ('xl/' + t)
            rels[a.get('Id', '')] = t
    out = {}
    for m in re.finditer(r'<sheet\b[^>]*>', z.read('xl/workbook.xml').decode('utf-8', 'ignore')):
        a = _xml_attrs(m.group(0))
        out[rels.get(a.get('r:id', ''), '?')] = html.unescape(a.get('name', '?'))
    return out


def xlsx_taint(path):
    """只读快扫 xlsx 底层 XML（一次 zipfile 扫描，不动源文件），返回 [(表名, kind, 明细)]。
    kind='autoFilter'：ref 非 A1 式区间（如 "1:1"）——普通模式读取必抛 ValueError；
    kind='dimension'：声明终止行 < 实际最大行——read_only 按声明截界，静默近空读。
    干净文件返回 []（空表、无 dimension 声明均不误报）。非 zip 文件返回 []（交由 openpyxl 报它自己的错）。"""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = _xlsx_sheet_names(z)
            out = []
            for n in z.namelist():
                if not _SHEET_PART.fullmatch(n):
                    continue
                x = z.read(n).decode('utf-8', 'ignore')
                sheet = names.get(n, n)
                for m in re.finditer(r'<autoFilter\b[^>]*>', x):
                    ref = _xml_attrs(m.group(0)).get('ref')
                    if ref and not _A1_REF.fullmatch(ref):
                        out.append((sheet, 'autoFilter', f'非法 autoFilter ref="{ref}"'))
                        break
                dm = re.search(r'<dimension\b[^>]*>', x)
                ref = _xml_attrs(dm.group(0)).get('ref', '') if dm else ''
                declared = int(re.search(r'(\d+)\D*$', ref).group(1)) if re.search(r'\d', ref) else None
                rs = [int(v) for v in re.findall(r'<row r="(\d+)"', x)]
                actual = max(rs + [len(re.findall(r'<row\b', x))])
                if declared is not None and actual > declared:
                    out.append((sheet, 'dimension', f'dimension 声明只到第 {declared} 行，实际 ≥{actual} 行'))
            return out
    except zipfile.BadZipFile:
        return []


def sanitize_xlsx_copy(path):
    """带伤 xlsx → 临时只读副本（系统临时目录，进程退出时清理；源文件不动）：
    剥离非法 autoFilter 元素（自闭合与成对两种写法）＋去掉 <dimension> 声明（普通模式按实际单元格重算维度）。
    其余 zip 部件逐字节保留。返回副本路径。"""
    import atexit
    import os
    import tempfile
    import zipfile
    fd, tmp = tempfile.mkstemp(prefix='mm_sanitized_', suffix='.xlsx')
    os.close(fd)
    atexit.register(lambda p=tmp: os.path.exists(p) and os.remove(p))

    def drop_af(m):
        tag = m.group(0)
        head = re.match(r'<autoFilter\b[^>]*>', tag)
        ref = _xml_attrs(head.group(0)).get('ref') if head else None
        return '' if (ref and not _A1_REF.fullmatch(ref)) else tag

    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if _SHEET_PART.fullmatch(it.filename):
                x = data.decode('utf-8')
                x = re.sub(r'<autoFilter\b[^>]*/>', drop_af, x)
                x = re.sub(r'<autoFilter\b[^>]*>.*?</autoFilter>', drop_af, x, flags=re.S)
                x = re.sub(r'<dimension\b[^>]*/>', '', x)      # 截断声明一并剥离，普通模式按实际重算
                data = x.encode('utf-8')
            zout.writestr(it, data)
    return tmp


def open_workbook_lenient(path, read_only=True, data_only=True, log=None):
    """xlsx 读取入口（normalize_listing / inspect_listing / mm_build / validate_contract / export_queries 共用）。
    干净文件按调用方 read_only 原样加载，零行为变化；带伤文件（xlsx_taint 非空）宁可慢也要读全：
    read_only 对这类文件会静默近空读，一律回退普通模式全量解析；含非法 autoFilter 时普通模式必抛错，
    直接走剥离副本。返回 (workbook, notes)；notes 每条含表名清单与回退原因，并逐条回调 log。"""
    import openpyxl
    taint = xlsx_taint(path)
    if not taint:
        return openpyxl.load_workbook(path, read_only=read_only, data_only=data_only), []
    af = [s for s, k, _d in taint if k == 'autoFilter']
    dim = [(s, d) for s, k, d in taint if k == 'dimension']

    def shown(xs):
        return '、'.join(xs[:8]) + (f' 等 {len(xs)} 张表' if len(xs) > 8 else '')

    notes = []
    if af:
        notes.append(f'检测到非法 autoFilter（{shown(af)}）→ 经剥离副本全量读取（宁可慢也要读全）')
    if dim:
        notes.append(f'dimension 声明截断（{shown([f"{s}：{d}" for s, d in dim])}）→ read_only 会静默少读，回退普通模式全量读取')
    wb = None
    if not af:                                             # 仅维度截断：普通模式可直读原文件
        try:
            wb = openpyxl.load_workbook(path, read_only=False, data_only=data_only)
        except Exception:
            wb = None
    if wb is None:
        wb = openpyxl.load_workbook(sanitize_xlsx_copy(path), read_only=False, data_only=data_only)
    for n in notes:
        if log:
            log(n)
    return wb, notes
