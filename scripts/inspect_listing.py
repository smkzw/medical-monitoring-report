#!/usr/bin/env python3
"""Phase 0/2 helper: inventory listing workbooks and draft a mapping.json for normalize_listing.py.

python3 inspect_listing.py edc=EDC.xlsx [pd=PD.xlsx lab=central_lab.xlsx ...] --out work/
  → work/inventory.md       sheet-by-sheet: header rows, variables, rows, subject column, guessed domain, layout
  → work/mapping.draft.json draft mapping (domains + column guesses + visit labels found); REVIEW before use
  → work/precheck.md        blocker / confirm / hint list to settle with the user before building

Heuristics only: every guess is marked in the draft ("_guess": true) and must be confirmed by the MM.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

from common import open_workbook_lenient

DOMAIN_RE = [  # (domain, sheet-name/label regex)
    # R2-2：参与者/人口统计为通用 CRF 命名变体（受试者/参与者两系术语、人口学/人口统计学）；
    # 治疗结束页/研究结束页为 DS 类完成状态页通用表名。
    ('subjects', r'^(DM|人口学|人口统计|受试者信息|参与者信息|筛选|知情|ENR|RAND|RAN\b|随机)'), ('subjects', r'^(DS|完成|结束|退出|EOS|EOT|研究总结|治疗结束|研究结束)'),
    ('visits', r'^(SV|访视日期|访视)'),
    # findings before exposure so ECG/ECHO are not caught by ^EC; any non lab/vs/ecg findings domain becomes a generic 专项检查 group
    ('findings:ecg', r'^(EG|ECG|心电图|12导联)'),
    ('findings:img', r'^(IMG|MI|RAD|影像|超声|B超|彩超|ECHO|超声心动|CT|MRI|核磁|X线|胸片|内镜|胃镜|肠镜|PET)'),
    ('findings:pe', r'^(PE|体格检查|查体)'),
    ('findings:exam', r'^(OE|OP|眼科|肺功能|PFT|妇科|乳腺|骨密度|DXA|Holter|动态心电|EEG|脑电|肌电|听力|皮肤科)'),
    # DA/DAH 由 refine_exposure 守卫改归 cm（滥用史不是研究药物给药；保留 DA 供给药记录表名命中）
    ('exposure', r'^(EC(?![GH])|EX|给药|研究药物|用药记录|服药|DA|药物发放)'),
    ('ae', r'^(AE|不良事件)'), ('mh', r'^(MH|病史|既往史|现病史|个人史|月经史|孕产史)'), ('cm', r'^(CM|合并用药|既往(及)?合并用药|既往用药|伴随用药)'), ('proc', r'^(PR|手术|操作|非药物治疗|既往(及)?合并非药物治疗)'),
    ('findings:lab', r'^(LB|血常规|血生化|生化|尿常规|凝血|实验室|甲功|血脂|肝功|肾功|电解质|妊娠|尿妊娠|HEMA|CHEM|URIN|COAG)'),
    ('findings:vs', r'^(VS|生命体征)'),
    ('efficacy', r'^(QS|EFF|RS|TU|TR|量表|评分|疗效|有效性|问卷|日记)|量表|问卷|评定|生活质量|印象变化|PGI|NRS|VAS|QO-?L|评分|指数'), ('pd', r'^(DV|PD|方案偏离|偏离|违背)'), ('extq', r'(质疑|QUERY|Query|query|^CROQ|^DCF|^EDCQ)'),
    ('pk', r'^(PK|PC|药代|血药浓度|采样)'), ('ada', r'^(ADA|IS|免疫原性|抗药抗体)'),
]

# R2-2（D002 E2E build ec34087 零信号定罪）：EDC 导出常见「(页号)表名」结构性前缀——DOMAIN_RE 的 ^锚定
# 在 (59)不良事件/(48)研究药物给药/(7)人口统计学 上全部未命中 → subjects/exposure 域从未进草稿 →
# norm 无 subjects/exposure → 分析人群为空 → queries/others/受试者页全零。域识别入口先剥页号前缀
# （形态归一：半/全角括号页号、数字序号点/顿号/横线/下划线；纯页号不是前缀）。
_PAGE_PREFIX = re.compile(r'^\s*(?:[（(]\s*[0-9一二三四五六七八九十]+\s*[)）]|'
                          r'[0-9]+\s*[.．、,，\-—_]|[一二三四五六七八九十]+\s*[、.．])\s*')


def strip_page_prefix(name):
    """剥表名结构性页号前缀；剥后为空（纯页号）或无前缀时原样返回。"""
    s = str(name or '').strip()
    t = _PAGE_PREFIX.sub('', s)
    return t or s


def domain_of_sheet(title, first_label=''):
    """sheet 域识别（页号前缀容错）：原名 → 剥前缀名 → 首列标签（原/剥）依次试 DOMAIN_RE，首个命中域。"""
    for cand in (str(title or '').strip(), strip_page_prefix(title), str(first_label or '').strip(),
                 strip_page_prefix(first_label)):
        if not cand:
            continue
        d = next((dom for dom, rx in DOMAIN_RE if re.search(rx, cand)), None)
        if d:
            return d
    return None


def is_subjects_sheet(title, first_label=''):
    """DM 类受试者基准表判定（「受试者编号不在 DM」核查用）——与 domain_of_sheet 同容错。"""
    for cand in (str(title or '').strip(), strip_page_prefix(title), str(first_label or '').strip()):
        if cand and re.search(DOMAIN_RE[0][1], cand):
            return True
    return False
FIELD_SYN = {  # normalized field → variable/label patterns (first match wins)
    'sid': [r'^(SUBJID|USUBJID|SUBJECT|受试者(编号|号|代码)?|参与者(编号|号)|筛选号|病例号|Participant ID|Subject ID)$'], 'site': [r'^(SITEID|SITENO|中心(编号|号)?)$'], 'center': [r'^(SITENAME|中心名称|研究中心)$'],
    'visit': [r'^(VISIT|VISITNAME|FOLDERNAME|访视(名称)?|访视阶段)$', r'^(数据节|FOLDER)$'], 'date': [r'(DAT|DTC|日期)$'], 'tpt': [r'(TPT|时间点)$'],
    'time': [r'(TIM|TIME|时间)$'],
    'icf': [r'^(DSICDAT|ICFDAT)$', r'知情同意书?签署日期'], 'rescreen': [r'(RSCRYN|是否.{0,3}重复筛选|是否.{0,3}重新筛选)'], 'prev_sid': [r'(首次筛选.{0,6}编号|DSSUBJID)'], 'eot_d': [r'(EOTDAT|末次(给药|服药)日期|治疗结束.*日期|终止治疗.*日期)'], 'eot_why': [r'(EOTREAS|终止治疗.*原因|治疗结束.*原因)', r'(DSDECOD|DSTERM|退出原因|终止原因|未完成原因)'],
    'eos_d': [r'(EOSDAT|DSSTDAT|研究结束.*日期|完成/?退出日期|退出(研究|试验)?日期)'], 'eos_done': [r'(EOSCOMP|DSCOMYN|是否完成)'], 'eos_why': [r'(EOSREAS|DSREAS|研究结束原因|未完成.*原因)'], 'age': [r'^(AGE|年龄)'], 'sex': [r'^(SEX|性别)'], 'rand': [r'(RANDNO|RANNUM|随机号)'], 'rand_d': [r'(RANDAT|随机日期)'], 'status': [r'^(受试者状态)$', r'(RANYN|是否筛选成功并随机)'], 'ht': [r'(HEIGHT|身高)'], 'wt': [r'^(WEIGHT|体重)'],
    # F-A：具体变量/事件名称列先于通用「名称$」——访视名称/页面名称是结构性元数据，不是事件术语
    #（RUX 实证：term 落到 VISIT 后 AE/CM/MH 全表「共同页」）；lookbehind 挡住 访视/页面/表单/中心/研究 名称。
    'term': [r'(AETERM|MHTERM|CMTRT|PRTRT|DVTERM|术语|事件名|药名|通用名|不良事件名称|事件名称|偏离描述|事件描述|详述$)',
             r'(?<!访视)(?<!页面)(?<!表单)(?<!中心)(?<!研究)名称$'], 'start': [r'(STDAT|STDTC|开始日期|起始日期)'], 'end': [r'(ENDAT|ENDTC|结束日期|停止日期)'],
    'ongoing': [r'(ONGO|是否持续|仍在)'], 'grade': [r'(TOXGR|SEV|严重程度|分级|CTCAE)'], 'serious': [r'^(AESERYN|是否SAE)$', r'^是否(为)?严重不良事件', r'^(AESER|严重不良事件)$', r'(AESER|是否SAE)'], 'fast': [r'(FAST$|是否.{0,4}空腹)'],
    'pt': [r'(AEDECOD|AEPT|首选术语|^PT(名称)?$)'], 'soc': [r'(AESOC|AEBODSYS|系统器官分类|^SOC)'], 'llt': [r'(AELLT|低位语|^LLT)'],
    'aware': [r'(AWARE|获知日期|知晓日期)'], 'rpt': [r'(RPTDAT|SAERPT|报告日期|上报日期)'], 'aesi': [r'(AESI|特别关注)'],
    'rel': [r'(AEREL|与研究药物.*关|相关性|因果)'], 'action': [r'(AEACN|采取.*措施|对研究药物.*措施)'], 'outcome': [r'(AEOUT|转归)'],
    'dose_plan': [r'(PDOSE$|计划.{0,4}剂量)'], 'dose_act': [r'(ADOSE$|实际.{0,4}剂量)'], 'miss_qty': [r'(LMNUM$|漏服.{0,4}剂量)'],
    'extra_qty': [r'(MMNUM$|多服.{0,4}剂量)'], 'dose': [r'(DOSE$|DOSTXT|剂量$|单次剂量)'], 'freq': [r'(FRQ|FREQ|频次|频率)'], 'route': [r'(ROUTE|途径)'], 'indication': [r'(INDC|用药原因|适应症)'],
    'test': [r'^(LBTEST|VSTEST|EGTEST|QSTEST|检查项(目)?|项目名称|指标|(实验室)?指标名称)$'], 'value': [r'(ORRES$|STRESN|结果$|测量值|检测值)'], 'unit': [r'(ORRESU|STRESU|单位)'],
    'lo': [r'(NRLO|下限)'], 'hi': [r'(NRHI|上限)'], 'clin': [r'(CLSIG|临床意义|临床评估)'], 'link': [r'(病史/不良事件|关联|LINK|^动态链接$)'], 'desc': [r'(异常描述|DESC)'],
    'link_mh': [r'(MHNO$|相关(既往)?病史)'], 'link_ae': [r'(AENO$|相关不良事件)'], 'reason_disease': [r'与研究疾病相关'],
    'cat': [r'(DVCAT|偏离(类别|分类))'], 'text': [r'(质疑内容|QUERYTEXT|TEXT)'], 'form': [r'^(FORM|表单|CRF页)'],
}
DOMAIN_FIELDS = {'subjects': ['sid', 'site', 'center', 'icf', 'rescreen', 'prev_sid', 'age', 'sex', 'ht', 'wt', 'rand', 'rand_d', 'status', 'eot_d', 'eot_why', 'eos_d', 'eos_done', 'eos_why'], 'visits': ['sid', 'visit', 'date'],
                 'exposure': ['sid', 'visit', 'start', 'end', 'dose_plan', 'dose_act', 'miss_qty', 'extra_qty', 'dose', 'time', 'fast'], 'ae': ['sid', 'term', 'pt', 'soc', 'llt', 'start', 'end', 'grade', 'serious', 'aesi', 'rel', 'action', 'outcome', 'aware', 'rpt'],
                 'mh': ['sid', 'term', 'start', 'end', 'ongoing'], 'cm': ['sid', 'term', 'start', 'end', 'ongoing', 'dose', 'freq', 'route', 'indication'],
                 'proc': ['sid', 'term', 'start', 'end'], 'findings': ['sid', 'visit', 'date', 'time', 'tpt', 'test', 'value', 'unit', 'lo', 'hi', 'clin', 'desc', 'link',
                                                                    'link_mh', 'link_ae', 'reason_disease'], 'sample': ['sid', 'visit', 'tpt', 'date', 'time'],
                 'efficacy': ['sid', 'visit', 'date', 'test', 'value'], 'pd': ['sid', 'cat', 'term', 'date'], 'extq': ['sid', 'form', 'visit', 'text'],
                 'pk': ['sid', 'visit', 'date', 'tpt', 'value'], 'ada': ['sid', 'visit', 'date', 'value']}


def header_rows(rows):
    """Return (label_row, var_row, data_start) — detects the common EDC layout row1 Chinese labels + row2 variable names."""
    def kind(r):
        cells = [str(c).strip() for c in r if c not in (None, '')]
        if not cells:
            return 'empty', 0
        han = sum(bool(re.search(r'[\u4e00-\u9fa5]', c)) for c in cells) / len(cells)
        var = sum(bool(re.fullmatch(r'[A-Z][A-Z0-9_]{1,19}', c)) for c in cells) / len(cells)
        return ('label' if han > .5 else 'var' if var > .6 else 'data'), len(cells)
    k = [kind(r)[0] for r in rows[:6]]
    if len(k) > 1 and k[0] == 'label' and k[1] == 'var':
        return 1, 2, 3
    if k and k[0] == 'var' and len(k) > 1 and k[1] == 'label':
        return 2, 1, 3
    return 1, 0, 2


# EDC 导出的系统元数据列（每张表都有、不是业务内容）：只允许映射到指定字段，其余字段一律跳过
#（否则「试验中心名称」会被当成 AE 术语、「最后修改时间」当成采样时刻、「Instance顺序号」当成记录编号）。
# 「受试者状态」放行给 subjects.status（筛选失败/完成试验，pd_rules RAND-02 口径；它只在 subjects 域字段表中，别域天然收不到）
# F-A 补：另一类 EDC 导出（D002/RUX 式）的 页面名称/记录号/研究中心/中心编号/Flag/MM comment 同为结构性元数据
#（「页面名称」值如「不良事件 1-头痛-2024-06-25」更不能被 名称$ 当成术语）。
SYS_META = {'项目编号': None, '表单编号': None, '姓名缩写': None, '受试者状态': 'status', 'Instance顺序号': None, '数据块': None,
            'Block顺序号': None, '数据页': None, '最后修改时间': None, '行号': None, '数据节': 'visit', '试验中心编号': 'site',
            '试验中心名称': 'center', '动态链接': 'link',
            '页面名称': None, '记录号': None, '研究中心': 'center', '中心编号': 'site', 'Flag': None, 'MM comment': None}
LABEL_VAR = re.compile(r'(.+?)\s*[（(]([A-Z][A-Z0-9_]{1,19})[)）]')

# 结构性元数据列的可判定形式（第三轮 E2E，RUX 复审）：访视/页面/表单/中心/受试者状态/OID/序号——EDC 每张表都带，
# 绝不是事件术语。F-A 只守了草稿层 guess()；已确认落位的 mapping（陈旧/误确认件）里 term=VISIT 仍被 normalize
# 盲信 → ae/cm/mh/proc 四域 term 全表「共同页」。normalize 构建层用本判定守卫 term 列，命中即按 guess() 重找。
_STRUCT_LABEL_RX = re.compile(r'^(访视|页面|表单|数据节|数据页|数据块|研究中心|试验中心|中心(编号|名称|号)|受试者状态|记录号|行号|页码|Instance|Block)')
_STRUCT_VAR_RX = re.compile(r'(VISIT\w*|FOLDER\w*|FORM(NM|OID|REP|NAME)?|VIST(OID|REP)|SITE(ID|NM|NAME|NO)|SUBJSTA|RECREP|PAGE\w*|INSTANCE\w*)', re.I)


def is_struct_col(label, var=''):
    """该列是否为结构性元数据列（访视名称/页面名称/研究中心/受试者状态/OID/序号…）——绝不能作事件术语。"""
    lab, v = str(label or '').strip(), str(var or '').strip()
    return lab in SYS_META or bool(_STRUCT_LABEL_RX.search(lab)) or bool(_STRUCT_VAR_RX.fullmatch(v))

# exposure 候选校正（SAR 深审 F3）：药物滥用史表与背景治疗日志不是研究药物给药——吞进 exposure 会虚增
# 安全集（dosed）、首剂/给药日期可能取自背景治疗行。背景判定仅在无未编号研究药物列时收窄。
_ABUSE_RX = re.compile(r'滥用史|[Aa]buse')
_BKG_RX = re.compile(r'背景治疗|背景用药|EXYN\d')
_STUDY_RX = re.compile(r'EXYN(?![A-Za-z0-9_])|EXDOSE(?![A-Za-z0-9_])|EXDAT(?![A-Za-z0-9_])|EXSTDAT|实际给药|首次给药')


def refine_exposure(dom, sheet, hdr):
    """exposure 候选 → 滥用史表（DAH/滥用史/Abuse）与背景治疗日志（EXYN1/背景治疗）改归 cm（背景用药/用药史）。
    非 exposure 域原样返回；EX 主表（EXYN/EXDOSE/EXDAT/实际给药 等未编号研究药物列）保持 exposure。"""
    if dom != 'exposure':
        return dom
    if _ABUSE_RX.search(hdr) or re.match(r'DAH\d*$', sheet or '', re.I):
        return 'cm'
    if _BKG_RX.search(hdr) and not _STUDY_RX.search(hdr):
        return 'cm'
    return dom


def split_label(lab, var):
    """单行表头「不良事件名称(AETERM)」→（不良事件名称, AETERM）；已有变量名行时不拆。"""
    m = LABEL_VAR.fullmatch(lab or '') if not var else None
    return (m.group(1), m.group(2)) if m else (lab, var)


def guess(names, field):
    for pat in FIELD_SYN.get(field, []):
        for i, (lab, var) in enumerate(names):
            if lab in SYS_META and SYS_META[lab] != field:
                continue
            if (var and re.search(pat, var)) or (lab and re.search(pat, lab)):
                return var or lab
    return None


_TOTAL_SCORE_RX = re.compile(r'总分|总得分|总评分|总百分比分|totalscore', re.I)
_PD_HDR_RX = re.compile(r'方案违背(详述|主分类|子分类)|偏离(详述|描述)|DVTERM|DVCAT', re.I)


def sheet_domain_by_header(sheet, labels):
    """表头签名兜底（F-B/F-H）：表名纯代码或中性名（RES1/总表 式）时按表头判域。
    量表必有「总分」汇总列（检验/生命体征表没有）→ efficacy；PD 记录表必有「方案违背详述/主分类」列 → pd。
    判不出返回 None（不猜其他域）。"""
    for lab in labels or []:
        base = re.sub(r'[（(][^）)]*[）)]\s*$', '', str(lab or '').strip())
        if base and _PD_HDR_RX.search(base):
            return 'pd'
        if base and _TOTAL_SCORE_RX.search(base):
            return 'efficacy'
    return None


# 访视归一（F-G）：带明确访视号（V6/W28/D15…）的标签优先于融合型兜底（FU/EOT）。
# SAR 实证：「安全性随访期V6/V7」都并成 FU 后，V6、V7 访视窗全部失配 → 342/345 条虚假逾期。
VISIT_RULES = [
    (r'筛选|Screen', 'SCR'), (r'第\s*1\s*天|D1\b|Day\s*1\b', 'D1'),
    (r'计划外|Unsch|USV', 'USV'), (r'提前|ET\b|退出', 'ET'),
    (r'安全(性)?随访|随访期|Follow', 'FU'), (r'治疗结束|EOT\b', 'EOT'),
]
_VIS_TAIL_BRACKET = re.compile(r'[（(][^）)]*[）)]\s*$')
_VIS_IDENT = [re.compile(r'第\s*(\d+)\s*周'),
              re.compile(r'(?<![A-Za-z0-9])([DWMV])\s*(\d+)(?![A-Za-z0-9])'),
              re.compile(r'(?<![A-Za-z0-9])(\d+)\s*([DWMV])(?![A-Za-z0-9])')]


def _visit_ident(v):
    """标签主干（去掉尾部括号窗说明）里的明确访视号：第2周→W2、V6/D15→原样、2W→W2。取第一个命中的标记。"""
    s = _VIS_TAIL_BRACKET.sub('', str(v or '').strip())
    for i, rx in enumerate(_VIS_IDENT):
        m = rx.search(s)
        if not m:
            continue
        if i == 0:
            return 'W' + m.group(1)
        a, b = m.group(1), m.group(2)
        return (a if a.isalpha() else b) + (b if a.isalpha() else a)
    return None


def visit_code(v, soa=()):
    """访视标签 → 标准访视代码（visit_map 生成用）。顺序：方案表精确命中 → 具体关键词（筛选/D1/计划外/提前退出）
    → 融合型关键词（随访→FU、治疗结束→EOT）在标签自带明确访视号时让位 → 访视号 → 其余兜底。"""
    v = str(v or '').strip()
    if v in soa:
        return v
    ident = _visit_ident(v)
    for pat, code in VISIT_RULES:
        if not re.search(pat, v, re.I):
            continue
        if code in ('FU', 'EOT') and ident:
            # 方案表明确用融合码时从方案；否则访视号（V6/W28）保信息量，不与兄弟访视并码
            return code if (soa and code in soa and ident not in soa) else ident
        return code
    if ident:
        return ident
    m = re.search(r'第\s*(\d+)\s*周', v)
    if m:
        return 'W' + m.group(1)
    m = re.fullmatch(r'\s*(W|D|V|M)\s*(\d+)\s*', v, re.I)
    if m:
        return m.group(1).upper() + m.group(2)
    m = re.search(r'(?:V|访视)\s*(\d+)', v)
    if m:
        return 'V' + m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('books', nargs='+', help='alias=path.xlsx')
    ap.add_argument('--out', default='work')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    inv, draft, pre = [], {'workbooks': {}, 'label_row': 1, 'var_row': 2, 'data_start': 3, 'visit_map': {}, 'clin_map': [], 'domains': defaultdict(list)}, []
    visits, clins, sid_sets = Counter(), Counter(), {}
    for spec in a.books:
        alias, path = spec.split('=', 1) if '=' in spec else (Path(spec).stem[:8], spec)
        draft['workbooks'][alias] = str(Path(path).resolve())
        wb, notes = open_workbook_lenient(path, read_only=True, data_only=True)
        inv.append(f'## {alias} · {Path(path).name}\n\n| 表 | 识别 | 表头行 | 行数 | 受试者列 | 布局 | 主要变量 |\n|---|---|---|---|---|---|---|')
        inv.extend(f'> ! {n}' for n in notes)    # PLAN §21 P1：带伤文件回退提示（表名+原因）留在 inventory 可见
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            lr, vr, ds = header_rows(rows)
            labels = [str(x).strip() if x is not None else '' for x in rows[lr - 1]]
            vars_ = [str(x).strip() if x is not None else '' for x in rows[vr - 1]] if vr else [''] * len(labels)
            names = [split_label(a, b) for a, b in zip(labels + [''] * (len(vars_) - len(labels)), vars_ + [''] * (len(labels) - len(vars_)))]
            data = [r for r in rows[ds - 1:] if any(c not in (None, '') for c in r)]
            hdr = ' '.join(labels)
            dom = domain_of_sheet(ws.title, labels[0] if labels else '')   # R2-2：页号前缀容错（(59)不良事件 式）
            if dom is None:
                dom = sheet_domain_by_header(ws.title, labels)   # F-B：表名纯代码时按「总分」表头签名判 efficacy
            dom = refine_exposure(dom, ws.title, hdr)        # F3：滥用史/背景治疗日志不是研究药物给药
            if dom == 'pd' and not re.search(r'偏离|违背|deviation|DVTERM|DVCAT', hdr, re.I):
                dom = None                                   # 表名 PD 但不是方案偏离（如药效学 PD 样本）
            if dom in (None, 'pk', 'pd') and re.search(r'采血|采样|样本采集', hdr) and re.search(r'时间点|TPT|(采血|采样)时间', hdr) and not re.search(r'结果|浓度|ORRES|偏离|违背', hdr):
                dom = 'sample'                               # 只有计划时间点/实际采集时刻、没有结果 → 样本采集记录（PD 执行层面核查用）
            sidc = guess(names, 'sid')
            testc = guess(names, 'test')
            lay = 'long' if testc else 'wide'
            if sidc:
                i = [n[1] or n[0] for n in names].index(sidc)
                sid_sets[(alias, ws.title)] = {str(r[i]).strip() for r in data if i < len(r) and r[i] not in (None, '')}
            for f in ('visit',):
                c = guess(names, f)
                if c:
                    i = [n[1] or n[0] for n in names].index(c)
                    visits.update(str(r[i]).strip() for r in data if i < len(r) and r[i] not in (None, ''))
            cc = guess(names, 'clin')
            if cc:
                i = [n[1] or n[0] for n in names].index(cc)
                clins.update(str(r[i]).strip() for r in data if i < len(r) and r[i] not in (None, ''))
            inv.append(f"| {ws.title} | {dom or '—'} | {lr}/{vr or '-'}→{ds} | {len(data)} | {sidc or '**未识别**'} | {lay if dom and dom.startswith(('findings', 'efficacy')) else ''} | "
                       f"{'、'.join((n[1] or n[0]) for n in names[:14] if n[0] or n[1])} |")
            if not dom:
                pre.append(['提示', f'{alias}/{ws.title} 未识别领域（{len(data)} 行），如需纳入请在 mapping 中指定'])
                continue
            if not sidc:
                pre.append(['阻断', f'{alias}/{ws.title} 未识别受试者编号列'])
            base = dom.split(':')[0]
            fields = DOMAIN_FIELDS['findings' if base == 'findings' else base]
            spec_ = {'wb': alias, 'sheet': ws.title, '_guess': True}
            if (lr, vr, ds) != (1, 2, 3):
                spec_.update({'label_row': lr, 'var_row': vr, 'data_start': ds})
            cols = {f: guess(names, f) for f in fields}
            if base in ('pd',):
                cols['desc'] = cols.pop('term', None)
            if base in ('efficacy',):
                cols['metric'] = cols.pop('test', None)
            spec_['cols'] = {k: v for k, v in cols.items() if v}
            if base == 'findings':
                spec_.update({'domain': dom.split(':')[1], 'group': labels[0] if False else ws.title, 'layout': lay})
                if lay == 'wide':
                    spec_['tests'] = {}
                    pre.append(['需确认', f'{alias}/{ws.title} 为宽表（每列一个检查项），请在 tests 中列出 指标→值列/单位/临床意义列'])
                for k in ('value', 'clin') if lay == 'long' else ():
                    if not cols.get(k):
                        pre.append(['需确认', f'{alias}/{ws.title} 未识别 {k} 列'])
            miss = [f for f in ('start', 'term') if f in fields and not cols.get(f) and base in ('ae', 'mh', 'cm')]
            if miss:
                pre.append(['需确认', f'{alias}/{ws.title} 未识别 {miss}'])
            draft['domains'][base if base != 'pk' and base != 'ada' else 'findings'].append(spec_ if base not in ('pk', 'ada') else {**spec_, 'domain': base, 'layout': 'long'})
    vm = {}
    for v, n in visits.most_common():
        m = visit_code(v)
        vm[v] = m if m is not None else v
        if m is None:
            pre.append(['需确认', f'访视「{v}」未能自动映射为标准访视代码，请在 visit_map 中确认'])
    draft['visit_map'] = vm
    cm = []
    for c, _ in clins.most_common():
        cm.append([c, 2 if re.search(r'有临床意义|CS\b|异常有', c) and not re.search(r'无临床意义|NCS', c) else 1 if re.search(r'无临床意义|NCS|异常无', c) else 0 if re.search(r'正常|未见异常|NORMAL', c, re.I) else None])
    draft['clin_map'] = [x for x in cm if x[1] is not None]
    for c in [x[0] for x in cm if x[1] is None]:
        pre.append(['需确认', f'临床意义取值「{c}」未能映射为 0/1/2（正常/NCS/CS）'])
    if not draft['domains'].get('subjects'):
        pre.append(['阻断', '未识别人口学/受试者表（DM），无法确定受试者范围'])
    if not draft['domains'].get('exposure'):
        pre.append(['阻断', '未识别给药/暴露表：首剂日期无法确定（基线、TEAE、研究日均依赖首剂）'])
    if not draft['domains'].get('pd'):
        pre.append(['提示', '未提供 PD listing：入排/禁用药/超窗信号无法与已记录偏离逐事件比对'])
    if sid_sets:
        allsid = set().union(*sid_sets.values())
        dm = next((v for (al, sh), v in sid_sets.items() if is_subjects_sheet(sh)), None)   # R2-2：(7)人口统计学 式页号前缀同样可作 DM 基准
        if dm:
            extra = allsid - dm
            if extra:
                pre.append(['需确认', f'{len(extra)} 个受试者编号出现在其他表但不在 DM：{sorted(extra)[:8]}…'])
    pre += [['需确认', '分析人群：全部受试者 / 已随机 / 已给药（默认 已给药）'], ['需确认', '计划外访视（USV）是否纳入访视汇总（默认 不纳入，仅个体审阅）'],
            ['需确认', '基线定义（从方案抽取）：各指标以哪次访视/时间点为基线；或首剂/随机前最近一次（是否含计划外）；或多次测量均值（如三联 ECG）'],
            ['需确认', '分级标准及版本（从方案抽取，不得默认）：CTCAE v5.0 / v6.0 / 方案自定义 / 其他（如 FDA 2007 毒性分级、DAIDS）'],
            ['需确认', 'AE 收集期与 TEAE 定义：如 ICF 后/首剂后起、末次给药后 N 天止'],
            ['需确认', 'AESI 定义（从方案/IB 抽取）：术语/PT/SOC 列表、实验室组合标准（如 Hy’s law）、最低级别、特殊情况（妊娠、过量等）'],
            ['需确认', 'SAE/AESI 报告时限（如获知后 24 小时）——需 listing 含获知/报告日期才可核对'],
            ['需确认', '是否盲态：盲态下不得展示分组及可揭示分组的有效性对比']]
    draft['domains'] = dict(draft['domains'])
    (out / 'mapping.draft.json').write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'inventory.md').write_text('# 输入清单（自动盘点）\n\n' + '\n'.join(inv) + f"\n\n## 访视标签（{len(vm)}）\n\n" +
                                      '\n'.join(f'- {k} → {v}' for k, v in vm.items()) + '\n', encoding='utf-8')
    order = {'阻断': 0, '需确认': 1, '提示': 2}
    (out / 'precheck.md').write_text('# 预检结果\n\n' + '\n'.join(f'- **{a}** {b}' for a, b in sorted(pre, key=lambda x: order[x[0]])) + '\n', encoding='utf-8')
    print(f"sheets: {sum(len(v) for v in draft['domains'].values())} mapped · visits {len(vm)} · precheck {Counter(p[0] for p in pre)}")


if __name__ == '__main__':
    main()
