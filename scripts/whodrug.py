"""WHODrug 对照（药名 → ATC 代码）。授权词典数据不进本仓库：与 MedDRA 同样按本地路径加载——
环境变量 MM_WHODRUG（对照表 JSON 路径）或默认 ~/.mm3/whodrug/whodrug_atc.json；文件不存在时查询一律返回空（行为与无词典时相同）。

对照表格式（由工作台 tools/whodrug_build.py 从授权数据生成）：
  {"version": "...", "names": {规范化药名: [ATC 代码…]}, "atc": {代码: 名称}}
药名为物质/商品名（中文与英文）；合并用药原文按「完整命中 → 最长物质名子串」查到物质，再按剂型关键词收窄 ATC 途径组
（「地塞米松磷酸钠注射液」→ 地塞米松的 H02，而不是 D07/S01）。项目数据自带 ATC 编码时优先用编码（调用方处理）。"""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

_TBL = None
_KEYS = None

_FORM_GROUPS = [   # 剂型关键词 → 保留的 ATC 途径组（命中多组时取并集）
    (re.compile(r'乳膏|软膏|霜|凝胶|洗剂|搽剂|酊|涂剂|外用|贴剂|溶液.{0,2}外|擦剂'), ('D', 'M02', 'C05')),
    (re.compile(r'滴眼|眼膏|眼用|眼液'), ('S01', 'S03')),
    (re.compile(r'鼻喷|鼻用|滴鼻|鼻雾|喷鼻|鼻腔'), ('R01',)),
    (re.compile(r'吸入|气雾|粉雾|雾化'), ('R03',)),
    (re.compile(r'滴耳'), ('S02', 'S03')),
]
_SYSTEMIC_FORM = re.compile(r'片|胶囊|注射|针|口服|颗粒|丸|散|冲剂|糖浆|混悬液|静滴|输液|肠溶|缓释')
_NONSYS = ('D', 'S01', 'S02', 'S03', 'R01', 'R03', 'M02', 'C05', 'A01')


def _norm(s):
    return re.sub(r'[\s·・,，;；()（）\[\]【】"“”\'’]+', '', str(s or '')).lower()


_NH = None
_NH_W = None
_NH_T = None


def _load_nhsa():
    """国家医保药品目录对照（公开文件解析，与 WHODrug 表同目录）：west 中文通用名 → ATC；tcm 中成药名 → 类别码。"""
    global _NH, _NH_W, _NH_T
    if _NH is not None:
        return _NH
    p = os.environ.get('MM_NHSA') or str(Path.home() / '.mm3' / 'whodrug' / 'nhsa_catalog.json')
    try:
        _NH = json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        _NH = {}
    _NH_W = sorted(((_norm(k), v) for k, v in (_NH.get('west') or {}).items() if len(_norm(k)) >= 2), key=lambda x: -len(x[0]))
    _NH_T = sorted(((_norm(k), v) for k, v in (_NH.get('tcm') or {}).items() if len(_norm(k)) >= 3), key=lambda x: -len(x[0]))
    return _NH


_TCM_FORMS = re.compile(r'(片|胶囊|软胶囊|颗粒|丸|散|膏|口服液|合剂|糖浆|酊|贴|栓|滴丸|喷雾剂|洗剂|搽剂|乳膏|软膏|凝胶|丹|茶|露)$')


@lru_cache(maxsize=20000)
def tcm_for(term) -> list:
    """中成药识别：药名（或去剂型后的药名主体）命中国家医保目录中成药部分 → 类别码列表；查不到 → []。"""
    _load_nhsa()
    t = _norm(term)
    if not t or not _NH_T:
        return []
    for k, v in _NH_T:
        if k == t or (k in t and len(k) >= 4):
            return list(v)
    stem = _TCM_FORMS.sub('', t)
    for k, v in _NH_T:
        if len(stem) >= 3 and _TCM_FORMS.sub('', k) == stem:
            return list(v)
    return []


def tcm_cat_names(code) -> list:
    """中成药类别码 → 本级及各上级类别名（ZA06E → 平喘剂、化痰、止咳、平喘剂、…），医保目录无类别表时 []。"""
    cats = (_load_nhsa() or {}).get('cats') or {}
    c, out = str(code or ''), []
    while c:
        if c in cats:
            out.append(str(cats[c]))
        c = c[:-1] if len(c) > 2 else ''
    return out


def _load():
    global _TBL, _KEYS
    if _TBL is not None:
        return _TBL
    p = os.environ.get('MM_WHODRUG') or str(Path.home() / '.mm3' / 'whodrug' / 'whodrug_atc.json')
    try:
        _TBL = json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        _TBL = {}
    names = _TBL.get('names') or {}
    _KEYS = sorted((k for k in names if len(k) >= 2), key=len, reverse=True)
    return _TBL


def available() -> bool:
    return bool((_load() or {}).get('names'))


@lru_cache(maxsize=20000)
def atc_for(term, route='') -> list:
    """合并用药原文（＋途径原文）→ ATC 代码列表；对照表不可用或查不到 → []。"""
    T = _load()
    names = T.get('names') or {}
    t = _norm(term)
    if not t:
        return []
    codes = names.get(t)
    if not codes:
        # 复方/并列成分（「卤米松/三氯生」「咪康唑氯倍他索乳膏」）：取全部互不重叠的物质名（由长到短贪心），ATC 取并集——
        # 只取最长一个会丢成分（曾只认三氯生、丢卤米松）
        used = [False] * len(t)
        acc: list = []
        for k in _KEYS:
            i = t.find(k)
            while i >= 0:
                if not any(used[i:i + len(k)]):
                    for j in range(i, i + len(k)):
                        used[j] = True
                    acc += names.get(k) or []
                    break
                i = t.find(k, i + 1)
            if all(used):
                break
        codes = list(dict.fromkeys(acc))
    if not codes:
        _load_nhsa()                       # WHODrug 未收的中文通用名写法：退到国家医保目录西药部分
        codes = next((list(v) for k, v in (_NH_W or []) if k in t), [])
    if not codes:
        return []
    txt = f"{term} {route}"
    keep = [g for rx, gs in _FORM_GROUPS if rx.search(txt) for g in gs]
    if keep:
        sel = [c for c in codes if c.startswith(tuple(keep))]
        return sel or list(codes)
    if _SYSTEMIC_FORM.search(txt):
        sel = [c for c in codes if not c.startswith(_NONSYS)]
        return sel or list(codes)
    return list(codes)


def atc_hit(prefixes, codes) -> bool:
    """条目 ATC 前缀与记录 ATC 代码是否命中（任一代码以任一前缀开头）。"""
    if not prefixes or not codes:
        return False
    pf = tuple(prefixes)
    return any(str(c).startswith(pf) for c in codes)
