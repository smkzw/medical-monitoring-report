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


# H1（第 3 轮 SAR，R10）：隐私列判定收口一处——三出口共用（原始数据层 raw_export、质疑/偏离抽屉摘录
# mm_build.build_ex、工作台工作簿导出同口径复写）。受试者/研究者身份与联系方式列不进任何交付面。
# 审阅者 2026-11-09：「initials」按子串认（SUBJ_INITIALS / SubjectInitials 曾漏剔）；不认「Init」（Init Dose 误剔）；
# 「缩写」排除中心/项目/检验/单位/药物缩写这类非身份列
PII_COL_RX = re.compile(r'姓名|(?<!中心)(?<!项目)(?<!检验)(?<!单位)(?<!药物)(?<!名称)缩写|initials|身份证|证件号|电话|手机|住址|家庭地址|联系方式|邮箱|e-?mail|出生日期|出生年月|生日|birth\s*date|date\s*of\s*birth|\bDOB\b|BRTHDAT', re.I)   # 完整出生日期属身份识别信息（年龄由映射另算）


def pii_column(label):
    """列名是否为隐私列（受试者/研究者 姓名·缩写·证件·电话·住址·联系方式）。"""
    return bool(PII_COL_RX.search(str(label or '')))


def redact_row(labels, row):
    """同一行里隐私列的取值（受试者姓名缩写、姓名）在其他单元格的自由文本中出现时打码（审阅者 2026-11-09，SAR：PD 详述
    「受试者HLSH…」29 处）。拉丁缩写只认 ≥3 字母的整词（避免误伤 LT/AE 类缩写），中文姓名按 ≥2 字子串。返回新列表。"""
    vals = []
    for j, lb in enumerate(labels or []):
        if j < len(row) and pii_column(lb):
            v = str(row[j] or '').strip()
            if re.fullmatch(r'[A-Za-z]{3,6}', v) or re.fullmatch(r'[\u4e00-\u9fff]{2,4}', v):
                vals.append(v)
    if not vals:
        return list(row)
    pats = [re.compile(rf'(?<![A-Za-z]){re.escape(v)}(?![A-Za-z])', re.I) if v.isascii() else re.compile(re.escape(v)) for v in vals]
    out = []
    for j, c in enumerate(row):
        if isinstance(c, str) and not (j < len(labels or []) and pii_column(labels[j])):
            for p_ in pats:
                c = p_.sub('＊＊', c)
        out.append(c)
    return out


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


# 带符号数值（碱剩余/心电轴/较基线变化「-2.5」曾丢值）；「×10^9/L」这类紧跟「/」的乘方是单位不是数量级（曾把 9.5×10^9/L 放大 10⁹ 倍）
_NUM_SCI = re.compile(r'^(<=|<|>=|>)?([+-]?[0-9]+(?:\.[0-9]+)?)(?:[eE]([+-]?\d+)|[*×xX]10\^?([+-]?\d+)(?![\d/]))?')

# 上标丢失形态（复制/导出链吞掉 ^ 的成品写法「10³」）：统一还原为十进制指数再进 _NUM_SCI
_SUP_MAP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻', '0123456789+-')

# 内嵌分数/级别词（量表值域写法，F8）：「3分-中度…」显式分值优先；「中度（2）」「2-中度」数字带在括号/连字符处取数字；
_SCORE_PREFIX = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*分(?!钟)')
_GRADE_PAREN = re.compile(r'(轻度|中度|重度)[^\d（）()]{0,4}[（(]\s*(\d+)(?:\s*级)?\s*[)）]')
_NUM_GRADE = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[-－~～]\s*(?:轻度|中度|重度)')


def _score_state(s):
    m = _SCORE_PREFIX.match(s)
    if m:
        return ('value', float(m.group(1)))
    m = _GRADE_PAREN.search(s)
    if m:
        return ('value', float(m.group(2)))
    m = _NUM_GRADE.match(s)
    if m:
        return ('value', float(m.group(1)))
    return None                    # 裸分级词（「中度」）不赋数值：分值随量表而异（IGA 0–4 中度＝3），猜数会编出主要终点


_QUAL_GRADE = re.compile(r'^[±]|[+＋]{1,4}|\d{1,2}\s*[+＋]$')   # 半定量分级（尿蛋白 1+/2+、±、+++）：定性非数值


def num_state(raw):
    """统一文本→数值解析（F8，一处收口）：在 result_state（数值/科学计数/删失/定性）之上补内嵌分数/级别词形态。
    返回 (kind, v)：value / below / above / neg / pos；无法识别 → None。mapping 结果列、规则阈值、参考范围常量
    三处都从这里取值（「<50」是删失界不是确切值、「<1*10^3」「1×10³」都是 ×10³）。
    半定量分级「1+」「2+」「±」「+++」是定性强度不是数值（ext1 真值：定性指标不进数值链）——返回 None 交定性路径。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return None if (isinstance(raw, float) and math.isnan(raw)) else ('value', float(raw))
    s = str(raw).strip()
    if not s:
        return None
    if _QUAL_GRADE.fullmatch(s):
        return None
    st = _score_state(s)
    return st if st is not None else result_state(s)


def num_bound(raw):
    """范围/常量数值（lo/hi）解析（F8）：取数值幅度（含科学计数与全角/上标写法），删失符号不保留——
    「<1*10^3 拷贝数/mL」的 const hi＝1000（检测上限按 1000 判），分级词/定性不适用返回 None。"""
    st = num_state(raw)
    if st is None or st[0] in ('neg', 'pos'):
        return None
    return st[1]


def result_state(raw):
    """检验结果写法的统一语义（V6，RUX 审阅第 12 条：「＜检测下限」「<1*10^3」「阴性」「5.26×10^3」各处各解）：
    返回 (kind, v)：value（确切数值）/ below（低于上界 v；v=None 表示低于检测下限）/ above（高于下界 v）/
    neg（阴性/未检出类定性）/ pos（阳性类定性）；空或无法识别 → None。
    F8：科学计数补上标丢失形态（10³）与全角乘号；调用方有分级词形态时走 num_state。"""
    s = str(raw if raw is not None else '').strip()
    if not s:
        return None
    if isinstance(raw, (int, float)):
        return ('value', float(raw))
    t = (s.replace('＜', '<').replace('＞', '>').replace('≤', '<=').replace('≥', '>=').replace('×', '*')
         .replace('低于', '<').replace('小于', '<').replace('高于', '>').replace('大于', '>').replace('超过', '>')
         .replace(' ', '').replace(',', ''))
    # H3②（第 3 轮 SAR）：「低于检出限/<检出下限」与「检测/定量」同族的删失写法统一认 below
    if re.search(r'<(检测|定量|检出)?下?限|<?LLOQ|<?LOD|^ND$|BLQ|TND|不可测|未检出|未检测到|notdetected', t, re.I):
        return ('below', None)
    sup = t.translate(_SUP_MAP)
    m = _NUM_SCI.match(sup)
    if m:
        v = float(m.group(2)) * (10 ** int(m.group(3) or m.group(4) or 0))
        op = m.group(1)
        return ('below', v) if op in ('<', '<=') else ('above', v) if op in ('>', '>=') else ('value', v)
    if re.search(r'阴性|negative|^[-－]$|^[（(][-－][)）]$', t, re.I) and not re.search(r'阳性|positive', t, re.I):
        return ('neg', None)
    if re.search(r'阳性|positive|^\+', t, re.I):
        return ('pos', None)
    return None


def state_meets(op, v, st):
    """结果状态 st 是否满足「op v」（如 ≥ 2000）：True / False / None（无法判定，如删失上界高于阈值）。"""
    if st is None or v is None:
        return None
    kind, x = st
    v = float(v)
    ge = op in ('>=', '>', '≥')
    if kind == 'value':
        return {'>=': x >= v, '≥': x >= v, '>': x > v, '<=': x <= v, '≤': x <= v, '<': x < v}.get(op)
    if kind == 'below':
        if x is None or x <= v:
            return False if ge else True
        return None
    if kind == 'above':
        if x >= v:
            return True if ge else False
        return None
    if kind == 'neg':
        return False if ge else True
    return None


_PAUSE_RX = re.compile(r'暂停|中断|暂时停|停止|停用|停药|永久|撤药|终止|pause|interrupt|hold|stop|withdr', re.I)
_RESUME_RX = re.compile(r'重新|恢复|再次给药|继续用药|resum|restart|re-?start', re.I)
_REDUCE_RX = re.compile(r'减量|降低剂量|减少剂量|剂量下调|reduc', re.I)
_PERM_RX = re.compile(r'永久|撤药|终止|withdr|discontinu', re.I)


def cn_quotes(s):
    """面向中心的文字统一用中文双/单引号（用户审阅 RUX 第 20 条：「」『』不是质疑里常用的原生中文写法）。只在输出端调用：
    事实卡不改（卡片哈希不变，模型已写句子可继续复用）。"""
    if not isinstance(s, str):
        return s
    return s.replace('「', '“').replace('」', '”').replace('『', '‘').replace('』', '’')


_CS_PLAIN = [(re.compile(r'(判定?为|判定|评为|评估为|判)\s*NCS'), '判为无临床意义'), (re.compile(r'(判定?为|判定|评为|评估为|判)\s*CS'), '判为有临床意义')]


def cs_plain(s):
    """面向中心的质疑文字里，「判为CS / 判定为NCS / 判CS」统一写成「判为有/无临床意义」（V6 第 2 轮审阅：模型撰写的句子仍出现「判为CS」）。
    只改「判…CS/NCS」这种判定写法，类别名、「CS 异常」等不动；只在输出端调用（事实卡与模型缓存不受影响）。"""
    if not isinstance(s, str):
        return s
    for rx_, rep in _CS_PLAIN:
        s = rx_.sub(rep, s)
    return s


def ae_action(t):
    """AE 对研究药物采取的措施 → 受控分类（对齐 CDISC AEACN：DRUG WITHDRAWN / DRUG INTERRUPTED / DOSE REDUCED / DOSE NOT CHANGED / NOT APPLICABLE）：
    withdrawn（永久停药/终止）、interrupted（暂停/中断，含「暂时停用后又恢复」）、reduced（减量）、none（未采取措施/剂量不变）、na（不适用/未知）。
    V6（用户审阅 RUX 第 13 条：「暂时停用后又恢复研究药物」此前匹配不到「停药」，安全性概览显示 0）。"""
    s = str(t or '').strip()
    if not s or s in ('—', '-') or re.search(r'不适用|未知|NA$|N/A|unknown', s, re.I):
        return 'na'
    if re.search(r'永久|撤药|终止|停止(研究)?(用药|给药|治疗)(?!后)|withdr|discontinu', s, re.I) and not re.search(r'暂时|暂停|恢复', s):
        return 'withdrawn'
    if re.search(r'暂停|暂时停|中断|停(?:用|药)后.{0,6}恢复|interrupt|hold', s, re.I):
        return 'interrupted'
    if re.search(r'减量|减少剂量|剂量减少|剂量降低|降低剂量|reduc', s, re.I):
        return 'reduced'
    if re.search(r'未采取|无|剂量不变|未改变|not changed|none', s, re.I):
        return 'none'
    if re.search(r'停药|停用', s):
        return 'withdrawn'
    return 'na'


def dose_state(e):
    """给药记录的语义状态（V6，RUX 审阅第 11 条：医嘱调整表「暂停用药 01-27～02-19」曾被当成给药区间）：
    paused（暂停/中断）/ withdrawn（永久停药）/ resumed（恢复）/ reduced（减量）/ dosing（普通给药）。
    依据 mapping 的 pause 字段（调整类型/暂停原因）；「否/无」视为无调整。"""
    t = str(e.get('pause') or '').strip()
    if not t or re.fullmatch(r'否|无|N|No|NA|不适用', t, re.I):
        return 'dosing'
    if _RESUME_RX.search(t):
        return 'resumed'
    if _PERM_RX.search(t):
        return 'withdrawn'
    if _PAUSE_RX.search(t):
        return 'paused'
    if _REDUCE_RX.search(t):
        return 'reduced'
    return 'dosing'


def is_dosing(e):
    """该记录代表实际给药：剂量非 0，且不是暂停/永久停药区间（暂停区间的起止日期是「未给药」的时间段）。"""
    return not zero_dose(e) and dose_state(e) not in ('paused', 'withdrawn')


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


def not_done(v):
    """「是否进行/是否发生」字段记为未做：否、否（未进行）、N/No、未发生/未进行/未做/未查。全仓统一口径（工程审阅：原三处判法不一）。"""
    return bool(re.match(r'^\s*(否|N\b|No\b|Not\b|未发生|未进行|未做|未查|未检)', str(v or ''), re.I))


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


def move_word(bv, v, lo=None, hi=None):
    """F06：基线→当前的方向措辞。相对基线的升/降照写（升高至/下降至/为），但偏离方向与基线方向相反时分离表述：
    值仍低于下限不写「升高至」（检验语态里「升高」指超上限的高型异常）→「较基线回升至」；仍高于上限的回落
    同理「较基线回降至」。参考范围本身由模板的（参考范围 …）呈现，两向各自成立。"""
    if bv is None or v is None or v == bv:
        return '为'
    if v > bv:
        return '较基线回升至' if lo is not None and v < lo else '升高至'
    return '较基线回降至' if hi is not None and v > hi else '下降至'


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
# 'AE 3'、'MH#2'、'AE (5) 术语'（SAR 实测：SH/VS/USV/EG/PE 等 426+ 非空关联单元格全部圆括号格式）；
# 多条以 ; , 、 换行 或连续空格分隔。类型 → AE / MH / CM。
# V6（用户审阅 RUX 第 10 条）：「与MH01相关」「CS与AE02相关」——拉丁编号前紧挨汉字时此前被后顾排除；
# 中文类型词（病史/既往史…）仍要求前面不是汉字（「高血压病史10年」不是编号），且编号后不跟时长单位
LINK_START = re.compile(r'(?:(?<![A-Za-z])(AE|MH|CM)|(?<![A-Za-z一-鿿])(不良事件|既往病史|既往史|病史|合并用药))'
                        r'\s*[(（+＋_\-－#＃：:\[［]?\s*(\d+)(?![\d.]*\s*(?:年|月|周|天|日|岁|次))', re.I)
LINK_TYPE = {'ae': 'AE', '不良事件': 'AE', 'mh': 'MH', '病史': 'MH', '既往病史': 'MH', '既往史': 'MH', 'cm': 'CM', '合并用药': 'CM'}
_LINK_DATE_TAIL = re.compile(r'[\s\-－]+(\d{4}|uk|UK|UNK)[-/.]([\dA-Za-z]{1,3})[-/.]([\dA-Za-z]{1,3})\s*$')


_TYPED_ITEM = re.compile(r'^\s*0*(\d+)\s*(?:[>＞\-－]\s*(.*?))?\s*$')


_LABELED_ITEM = re.compile(r'(?:序号|编号|记录号|No\.?)\s*[:：]\s*(\d+)\s*[-－—,，\s]*(?:[^：:;；]{0,8}?(?:名称|术语)\s*[:：]\s*)'
                           r'(.+?)(?=\s*[-－—]?\s*(?:开始|结束|发生)?日期\s*[:：]|[;；\n]|$)', re.I)


def parse_typed_links(v, typ):
    """关联类型由列决定（病史编号列 / AE 编号列），取值只有「编号>术语>日期」或编号本身 → [[typ, 术语, None, 编号]]。
    取值自带类型前缀（MH-4-…）时按 parse_links 解析。"""
    if not v:
        return []
    s = str(v)
    lab = list(_LABELED_ITEM.finditer(s))
    if lab:
        # 标签式（MY008：「序号：4-不良事件名称：白细胞降低-开始日期：2024-11-21；」多条以；分隔）：类型由列决定
        return [[typ, m.group(2).strip(' -－'), None, int(m.group(1))] for m in lab]
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
        tail = re.sub(r'^[)）\]］\s#＃]+', '', tail)   # 圆括号格式「AE (5) 术语」剥开头右括号；「MH3#术语」剥井号（F02：术语不带 #，编号后的 # 是分隔符）
        tail = re.sub(r'^(?:相关|有关|所致)$', '', tail.strip(' +＋-－_:：'))    # 「与MH01相关」的「相关」不是术语
        t = m.group(1) or m.group(2)
        out.append([LINK_TYPE.get(t.lower(), t.upper()), tail.strip(), None, int(m.group(3))])
    return out


# 关联引用的词目型写法（RUX 深审 F02，检验「异常有临床意义请说明」列实测 1600+ 非空）：
# 「脂肪肝病史」「贫血既往史」（词目＋名词后缀）、「病史高脂血症」（名词前缀）、「与脂肪肝相关/有关」、
# 「与"胆红素升高"既往史有关」（名词可前置/后置夹注）、「与疖肿AE相关」（名词定类型为 AE）。
# 只做词目抽取，编号为空；引用是否真实存在由 build 层 resolve_links/att_of 按编号或词目回溯。
_LINK_TERM_CC = r'一-鿿A-Za-z0-9（）()／/·.\-'
_LINK_QO = '[「『"“]'
_LINK_QC = '[」』"”]'
_LINK_NOUN = r'(?:既往史|病史|不良事件|AE|MH)'
_LINK_RELATED = re.compile(
    f'[与跟同和]\\s*({_LINK_NOUN})?\\s*{_LINK_QO}?([{_LINK_TERM_CC}]{{2,20}}){_LINK_QC}?\\s*(?:的)?\\s*({_LINK_NOUN})?\\s*(?:有关|相关|所致|引起)')
_LINK_HIST_PRE = re.compile(
    f'(?:既往史|病史)\\s*[:：]?\\s*{_LINK_QO}?([{_LINK_TERM_CC}]{{2,20}}){_LINK_QC}?\\s*(?:有关|相关|所致|[，。；;,;]|$)')
_LINK_HIST_SUF = re.compile(
    f'{_LINK_QO}?([{_LINK_TERM_CC}]{{2,20}}){_LINK_QC}?\\s*(?:的)?\\s*既往史|{_LINK_QO}?([{_LINK_TERM_CC}]{{2,20}}){_LINK_QC}?\\s*(?:的)?\\s*病史(?![一-鿿])')
# 不作词目关联的引用：研究疾病指代（「与AD相关」等归 disease_attr 的研究疾病口径，不得造 MH 关联抢归因）
# 疾病指代带限定词的形态（「本研究疾病」「基础疾病」…）一并拦下——SAR/RUX 实测「CS与本研究疾病相关」
# 曾整体被抽成词目「本研究疾病」，抢走 disease_attr 的研究疾病归因（DIS/DISW 被误路由成 CSX）
_LINK_NOT_TERM = re.compile(r'^(?:研究疾病|疾病本身|原发病|本病|疾病|AD|既往史|病史|相关|有关)$|(?:研究|本|原发|基础|该|同)[一-鿿]{0,4}疾病|疾病本身|^原发?病|^原疾病'
                            # mm5 审阅（S6）：非疾病对象不作病史/AE 词目（「与研究药物相关」「与饮食有关」「否认病史」「溶血所致」）
                            r'|研究药物|试验药物|研究用药|^药物$|饮食|进食|运动|标本|溶血|采血|操作|检测方法|仪器|^否认|^无$|^既往无|^未见')
# 否定写法：「与高血压不相关」「与高血压无明显相关」「否认与高血压有关」「排除高血压所致」——不是关联
_LINK_NEG_TAIL = re.compile(r'(?:不|无|未|非|并非|没有)\s*(?:明显|直接|确切)?\s*(?:的)?\s*(?:有关|相关|关联|所致|引起)$')
_LINK_NEG_HEAD = re.compile(r'(?:否认|排除|除外|不考虑|非)\s*$')
_LINK_NO_CJK = re.compile(r'^[^一-鿿]+$')


def parse_desc_links(v):
    """「异常有临床意义请说明」等自由文本里的词目型关联 → [[类型, 术语, None, None]]（编号空，类型默认 MH，
    名词为 不良事件/AE 时为 AE）。纯拉丁短词（AD/RA 等适应症缩写）不抽——研究疾病归因走 disease_attr。"""
    if not v:
        return []
    s = str(v)
    out = []
    for m in _LINK_RELATED.finditer(s):
        if _LINK_NEG_TAIL.search(m.group(0)) or _LINK_NEG_HEAD.search(s[max(0, m.start() - 4):m.start()]) or \
                re.search(r'(?:不|无|未|非)$', m.group(2) or ''):
            continue                                       # mm5 审阅（S4）：否定写法不是关联
        pre, term, noun = m.group(1), m.group(2), m.group(3)
        nouns = [n for n in (pre, noun) if n]
        typ = 'AE' if any(n == '不良事件' or n.upper() == 'AE' for n in nouns) else 'MH'
        out.append((typ, term))
    for m in _LINK_HIST_SUF.finditer(s):
        if not _LINK_NEG_HEAD.search(s[max(0, m.start() - 4):m.start()]):
            out.append(('MH', m.group(1) or m.group(2)))
    for m in _LINK_HIST_PRE.finditer(s):
        if not _LINK_NEG_HEAD.search(s[max(0, m.start() - 4):m.start()]):
            out.append(('MH', m.group(1)))
    seen, res = set(), []
    for typ, term in out:
        term = (term or '').strip(' 　\'"“”' + '「」『』')
        # 尾部收口：剥闭括号与吞进来的尾关键字（「病史相关）」曾整段抽成词目「相关）」——RUX 实测 38 处）
        term = re.sub(r'[）)」』””]+$', '', term)
        term = re.sub(r'(?:相关|有关|所致)$', '', term).strip(' 　的，,；;')
        term = re.sub(r'[）)」』””]+$', '', term)
        # 术语把尾部类型名词一并吃掉时（「疖肿AE」「皮疹不良事件」）：剥名词、类型以名词为准
        for noun, t2 in (('不良事件', 'AE'), ('既往史', 'MH'), ('病史', 'MH')):
            if term.endswith(noun) and len(term) > len(noun):
                term, typ = term[:-len(noun)].strip(' 　的'), t2
                break
        if term.upper().endswith('AE') and len(term) > 2 and re.search(r'[一-鿿]AE$', term):
            term, typ = term[:-2], 'AE'
        elif term.upper().endswith('MH') and len(term) > 2 and re.search(r'[一-鿿]MH$', term):
            term, typ = term[:-2], 'MH'
        if not term or _LINK_NOT_TERM.match(term) or (_LINK_NO_CJK.match(term) and len(term) <= 5):
            continue
        if (typ, term) not in seen:
            seen.add((typ, term))
            res.append([typ, term, None, None])
    return res


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
    """sheet XML 部件名 → 表名（workbook.xml + 其 rels 解析，属性顺序无关）。
    非 xlsx 的 zip（如 docx）无 xl/workbook.xml → 返回 {}：taint 无从扫起返回 []，
    文件类型错误交由 openpyxl 报它自己的错（判例 D002 CLI inspect 误把方案 docx 喂入）。"""
    import html
    if 'xl/workbook.xml' not in z.namelist():
        return {}
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
