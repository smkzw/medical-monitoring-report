#!/usr/bin/env python3
"""方案偏离（PD）引擎（mm4）：已记录 PD 归一＋潜在 PD 识别（执行层面 / 科学层面）＋分级＋逐事件比对。

由 mm_build.py 在全部信号生成之后调用（`pd_rules.run(C)` → C.pdd，写入 KZ.pd）。

口径（详见 references/protocol-deviation.md）：
- **PD**：任何对方案（含方案引用的手册/程序）的偏离（ICH E6(R3) 术语表）；**重要 PD**：可能显著影响参与者权益、
  安全或福祉，或显著影响关键数据完整性/准确性/可靠性的 PD 子集（ICH E3 Q&A R1；E6(R3)）。
- **已记录 PD**：PD listing 中的事件；**潜在 PD**：本引擎从数据推出、待 CRA/研究者核实的候选——**不是 PD 结论**。
- 分级三档：重要 / 一般 / 待判定（需医学或现场判断）；每条给出依据（why），可被 analysis.pd.grades 按规则覆盖。
- 处理建议三类：发 query（数据可澄清）/ CRA 核实（需源文件）/ 录入 PD（数据已足以确认）。
- 所有阈值、窗口、关键访视、允许的 ICF 前检查、依从性范围等都来自 study.json（方案抽取编译），代码不写任何研究取值；
  缺配置的检查不运行，并在 KZ.pd.rules 中标「未配置」（可见，不猜）。
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict

import ext_rules
from monitor_v5 import crit_items
from common import ae_action, days, dose_state, dshow, fmt, is_dosing, is_full_date, not_done, yes, zero_dose

# (分类码, 名称, 层面, 说明, CDISC DVCAT（SDTM CT C225352；与 TransCelerate 7 类一一对应）)
TAXONOMY = [
    ('ICF', '知情同意', '执行', '知情同意的获取、时序、版本与再次知情', 'INFORMED CONSENT/ASSENT'),
    ('ELIG', '入组资格', '科学', '不符合入选或符合排除仍入组（含洗脱期不足）', 'INCLUSION/EXCLUSION'),
    ('RAND', '随机与盲态', '执行', '随机时序、未随机即给药、盲态维护', 'STUDY INTERVENTION'),
    ('VIS', '访视计划', '执行', '访视超窗、计划访视缺失', 'TRIAL PROCEDURES'),
    ('ASMT', '评估与检查', '执行', 'SoA 规定评估缺失或未做、评估超窗、访视内先后顺序', 'TRIAL PROCEDURES'),
    ('IP', '研究药物与给药', '执行', '剂量/途径/频次/空腹、依从性、停药后仍给药', 'STUDY INTERVENTION'),
    ('SAMP', '样本采集', '执行', 'PK/PD 等样本的采集时点与给药时序', 'TRIAL PROCEDURES'),
    ('CM', '合并用药', '科学', '禁用/限用药、补救治疗的使用条件', 'PROHIBITED CONCOMITANT INTERVENTION'),
    ('SAFE', '安全性记录与报告', '科学', '潜在 AE 漏记、SAE/AESI 报告时限', 'SAFETY REPORTING'),
    ('WD', '退出与停药', '科学', '达到停药/退出标准未执行', 'DISCONTINUATION'),
    ('OTH', '其他', '—', '未归入以上类别', ''),
]
TAX = {t[0]: t for t in TAXONOMY}
# 已记录 PD 的类别归一（PD listing 文本 → 分类码）；顺序即优先级。可由 analysis.pd.catMap 前置覆盖。
CAT_RE = [
    # V6（PM 审阅 2026-11-02：SAR 151 条超窗记录因描述里写「知情日期 …」被归 ICF）：只认知情本身出问题的措辞，不认背景交代
    ('ICF', r'(知情|同意书|ICF).{0,8}(未|晚|延迟|迟|版本|漏|错|重新|过期|缺|不全|不规范)|(未|漏|延迟|错误|重复)签(署|字)|(先于|早于)知情|知情(同意)?前|签署前'),
    ('ELIG', r'入选|排除|入排|入组标准|资格|洗脱'),
    # H9（第 3 轮 SAR，35/317 错类）：「随机与盲态」只认真正的随机/揭盲操作——背景交代（「于某日随机」「随机后超窗」）
    # 不归随机类；未随机即给药/重新随机/随机号错误/揭盲/破盲/盲态破坏才是
    ('RAND', r'揭盲|破盲|盲态|非盲|未(经)?随机.{0,6}(给药|用药|入组|治疗)|(给药|用药|治疗).{0,6}(先于|早于)随机|重新随机|随机.{0,4}(错误|失误|异常)|随机(号|表|编码|名单).{0,4}(错|重复|泄露|泄盲|不匹配)|随机(提前|延迟|超窗)|错误随机|分层(因素|信息|错误|.{0,6}(错|不一致|不符|有误))'),   # 分层错误归随机类（审阅者 2026-11-09：H9 收窄时漏掉）
    ('SAMP', r'样本|采血|血样|PK|药代|采样'),
    # H9：「背景药物/背景用药/背景治疗」是合并用药类记录（描述常带「未做检查」字样，修前被评估检查抢先）
    ('CM', r'合并用药|合并治疗|禁用|禁止使用|限用|补救|背景用(药|治疗)|背景药物'),
    ('IP', r'给药|服药|用药错误|剂量|依从|发放|回收|药物管理|超温|过期|补服|漏服|研究药物|试验用药'),
    ('SAFE', r'SAE|严重不良|报告|妊娠|不良事件|\bAE\b'),
    ('WD', r'退出|终止|停药|撤回'),
    ('VIS', r'超窗|访视窗|时间窗|访视.{0,4}(缺失|未进行|未完成|遗漏)'),
    ('ASMT', r'漏做|未做|缺失|未进行|未完成|遗漏|检查|评估|量表|心电图|实验室'),
]
GRADE_STD = [(r'严重|重要|重大|重度|major|important|critical', '重要'), (r'轻微|轻度|一般|次要|minor|non', '一般')]   # SAR 记录表「轻度/重度」
# 既有引擎信号 → PD 分类（others.cat / labrows.risk）
SIG_CAT = {'入排标准核对': ('ELIG', 'ELIG-01'), '入排洗脱用药核对': ('ELIG', 'ELIG-02'), '禁限用药核对': ('CM', 'CM-01'),
           '访视超窗核对': ('VIS', 'VIS-01')}
# 方案「可沿用既往结果」条目常写检测品牌/英文名，listing 写中文通用名：按同一检测的常见写法扩展（医学同义，非研究特判）
PRE_ICF_SYN = [(r'结核|QuantiFERON|T-?SPOT|IGRA|干扰素释放', r'γ-?干扰素释放|干扰素释放试验|IGRA|QuantiFERON|T-?SPOT|结核感染T细胞')]
ICF_TIP = ('数据层面无法区分该检查是为本研究而做，还是参与者常规诊疗中已做、按方案可沿用的结果。'
           '请 CRA 核对源文件（检查申请/医嘱时间、是否为常规诊疗）：属方案允许沿用的既往结果则不构成偏离。')


_IMG = r'X\s*[片线光]|CT|胸片|影像|MRI|磁共振|超声|B超|DR'


def _pre_icf_rx(item):
    ext = [b for a, b in PRE_ICF_SYN if re.search(a, item, re.I)]
    if re.search(_IMG, item, re.I):
        # 影像类：按部位＋影像方式比（MY008「胸部正侧位X片|胸部CT」↔ 表单「胸部影像学检查」）
        site = re.search(r'胸|腹|头颅|颅脑|心脏|肺|肝|肾|盆腔|乳腺|甲状腺|骨', item)
        ext.append(f"{site.group(0)}[^|]{{0,8}}(?:{_IMG})" if site else f"(?:{_IMG})")
    return re.compile('|'.join([f'(?:{item})'] + [f'(?i:{x})' for x in ext]))


# 未执行的原因（用户 2026-10-28：写清是方案没写、listing 缺字段，还是阶段不判定，不能只写「未配置」）。
# 页面用语（K22）：数据导出表写「数据表」，不写 listing。
REASON = {
    'ICF-02': {'unconfigured': '方案正文未给出知情同意书各版本的生效日期及是否需再签（属伦理/版本管理信息），补充版本表后可执行',
               'no-data': '数据表中没有知情同意书版本记录'},
    'VIS-01': {'unconfigured': '方案中未找到可用的访视窗'},
    'VIS-02': {'unconfigured': '方案中未找到访视窗，或方案访视名称与数据表对不上', 'stage-off': '日常监查阶段数据仍在录入，「无记录」不等于访视缺失'},
    'ASMT-01': {'unconfigured': '方案流程表（SoA）的评估项目尚未与 EDC 表单建立对应，暂不判定「应做未做」（SoA 完成度矩阵照常展示）',
                'no-data': '数据表中没有可与访视比对的评估记录', 'stage-off': '日常监查阶段数据仍在录入，「无记录」不等于未做'},
    'ASMT-02': {'unconfigured': '方案流程表（SoA）的评估项目尚未与 EDC 表单建立对应', 'no-data': '数据表中没有「是否进行」类记录'},
    'ASMT-03': {'unconfigured': '方案未规定访视内评估的先后顺序，或数据表没有评估时刻'},
    'IP-01': {'unconfigured': '方案中未找到可核对的给药途径、频次或剂量'},
    'IP-03': {'unconfigured': '方案中未找到依从性计算方法与允许范围'},
    'IP-04': {'unconfigured': '方案未要求空腹给药，或给药记录中没有「是否空腹」字段'},
    'SAMP-01': {'no-data': '数据表中没有样本采集时刻或给药时刻'}, 'SAMP-02': {'no-data': '数据表中没有样本采集时刻或给药时刻'},
    'CM-02': {'unconfigured': '方案未规定补救治疗最早可用时间'}, 'CM-03': {'unconfigured': '方案未规定使用补救治疗后须停用研究药物，或未列出须停药的补救药物'},
    'SAFE-02': {'no-data': 'AE 记录表没有获知日期/报告日期，无法判断报告是否超时'},
    'ELIG-01': {'unconfigured': '方案入排标准中没有可用数据核对的数值条件'},
}
LAB_PD = {'CSX': '研究者判 CS 但未关联 AE/病史', 'DISW': '归因研究疾病但给药后较基线加重', 'MH': '仅关联病史且较基线加重'}

# 规则目录：id → (类别, 标题, 默认分级, 处理, 依据/逻辑, 所需数据)；DVDECOD 见 RULE_DV（CDISC C225353，用于对接 PD log / SDTM DV）
RULES = {
    'ICF-01': ('ICF', '研究程序早于知情同意', '重要', 'CRA 核实', '任何研究程序（访视/检查/给药/采样）日期早于知情同意签署日期；排除方案允许的 ICF 前既往检查结果（analysis.pd.preIcfAllowed）', '知情日期＋各程序日期'),
    'ICF-02': ('ICF', '方案修订后未再次知情', '重要', 'CRA 核实', '新版知情同意生效且要求再签后参与者仍在研，但无新版签署记录（analysis.pd.icfVersions）', '知情记录（版本/日期）＋版本生效表'),
    'RAND-01': ('RAND', '首次给药早于随机', '重要', 'CRA 核实', '首剂日期早于随机日期', '随机日期＋给药记录'),
    'RAND-02': ('RAND', '未随机即给药', '重要', '录入 PD', '有研究药物给药记录但无随机号/随机日期，或状态为筛选失败', '随机信息＋给药记录'),
    'ELIG-01': ('ELIG', '入组时检查值不符合入排标准', '重要', '录入 PD', '入组前末次有效测量（或方案指定判定值）对照入排标准不符，但已随机/给药', '筛选期检验/体征/人口学'),
    'ELIG-02': ('ELIG', '洗脱期不足', '重要', 'CRA 核实', '方案要求入组前停用的药物在洗脱窗口内仍在使用', '合并用药起止日期'),
    'VIS-01': ('VIS', '访视超窗', '一般', 'CRA 核实', '实际访视日期不在方案窗口内（锚点按方案：首剂/随机/前一访视/末次给药）；关键访视（主要终点访视）超窗升级为重要', '访视日期＋首剂/锚点'),
    'VIS-02': ('VIS', '计划访视缺失', '一般', 'CRA 核实', '访视窗口已在数据截止前关闭、参与者仍在研，但无该访视记录；关键访视缺失升级为重要', '访视日期＋状态/结束日期'),
    'ASMT-01': ('ASMT', '已完成访视但缺少方案规定的评估', '一般', '发 query', '参与者已完成该访视，但 SoA 要求的评估无任何记录；关键评估（主要终点/安全监测）升级为重要', 'SoA＋各评估表'),
    'ASMT-02': ('ASMT', '方案规定的评估记录为“未做”', '待判定', 'CRA 核实', '评估记录为「未查/未做」：是否属方案允许情形需结合原因判断', '各评估表的「是否进行」'),
    'ASMT-03': ('ASMT', '同次访视检查顺序不符合方案', '一般', 'CRA 核实', '方案要求在 A 之前完成的评估，记录时刻晚于 A（如量表/生命体征须在给药前）', '评估时刻＋给药时刻'),
    'IP-01': ('IP', '给药途径/频次/剂量与方案不符', '待判定', '发 query', '给药记录的途径、频次或剂量与方案规定不一致（analysis.pd.dosing）', '给药记录'),
    'IP-02': ('IP', '终止治疗后仍有给药', '重要', 'CRA 核实', '治疗结束/研究结束/妊娠阳性/停药阈值触发之后仍有研究药物给药记录', '给药＋治疗结束/妊娠/阈值'),
    'IP-03': ('IP', '依从性超出方案范围', '重要', 'CRA 核实', '按方案公式计算的依从性超出规定范围（analysis.pd.compliance）', '给药/发放回收数量'),
    'IP-04': ('IP', '未按要求空腹给药', '一般', 'CRA 核实', '方案要求空腹服药，给药记录为非空腹', '给药记录（是否空腹）'),
    'SAMP-01': ('SAMP', '给药前样本晚于给药', '重要', 'CRA 核实', '标注为给药前的样本，采集时刻晚于当次给药时刻（PK 谷浓度不可用）', '样本采集时刻＋给药时刻'),
    'SAMP-02': ('SAMP', '样本采集超出时间窗', '一般', 'CRA 核实', '给药后样本偏离计划时点超过允许窗口，或给药前样本早于「给药前 N 小时内」（analysis.pd.sample.windows / windowMin）', '样本采集时刻＋给药时刻'),
    'CM-01': ('CM', '使用方案禁用药物', '待判定', '发 query', '禁用药与方案禁用期重叠；影响主要终点或安全的类别（analysis.prohibited[].important）为重要', '合并用药＋禁用清单'),
    'CM-02': ('CM', '补救治疗早于允许时间', '重要', 'CRA 核实', '补救治疗开始日早于方案允许的最早研究日（analysis.pd.rescue.earliestDay）', '合并用药（补救）＋首剂'),
    'CM-03': ('CM', '补救治疗后未按要求停药', '重要', 'CRA 核实', '方案要求使用（系统）补救后永久停药，但其后仍有研究药物给药', '合并用药＋给药'),
    'SAFE-01': ('SAFE', '检验/检查异常可能需记录为 AE', '待判定', '发 query', '给药后新发或加重、研究者判有临床意义的异常未关联 AE（或仅关联病史且加重）；经确认未记录 AE 方构成 PD，严重/≥3 级/AESI 者重要', '检验/检查＋AE/病史'),
    'SAFE-02': ('SAFE', 'SAE/AESI 报告超时', '重要', 'CRA 核实', '报告日期 − 获知日期 > 方案时限', 'AE（获知/报告日期）'),
    'SAFE-03': ('SAFE', '达到方案需记录 AE 的标准但未见 AE 记录', '待判定', '发 query', '达到方案规定需记录 AE/AESI 的阈值，但时间窗内未见对应 AE', '检验/检查＋AE'),
    'WD-01': ('WD', '已达方案停药标准仍继续用药', '重要', 'CRA 核实', '方案规定的永久停药标准触发后仍有给药', '检验＋给药'),
    'WD-02': ('WD', '已达方案中断标准但未见暂停给药', '待判定', 'CRA 核实', '方案规定需中断研究药物的检验标准触发后 7 天内未见暂停/停药记录（给药记录或 AE 措施），其后仍有给药；部分方案限于研究者判断与研究药物相关时', '检验＋给药＋AE'),
}
RULE_DV = {'ICF-01': 'INFORMED CONSENT SIGNED/DATED AFTER STUDY PROCEDURES INITIATED',
    'ICF-02': 'INFORMED CONSENT NOT SIGNED/DATED PER LOCAL REGULATORY GUIDELINES',
    'RAND-01': 'RANDOMIZATION ERROR',
    'RAND-02': 'RANDOMIZATION ERROR',
    'ELIG-01': 'SUBJECT ENROLLED BUT INCLUSION CRITERIA NOT MET / EXCLUSION CRITERIA MET',
    'ELIG-02': 'SUBJECT ENROLLED BUT EXCLUSION CRITERIA MET',
    'VIS-01': 'VISIT PERFORMED OUTSIDE THE TIMING WINDOW',
    'VIS-02': 'VISIT NOT PERFORMED',
    'ASMT-01': 'ASSESSMENT NOT PERFORMED',
    'ASMT-02': 'ASSESSMENT NOT PERFORMED',
    'ASMT-03': 'ASSESSMENT PERFORMED OUT OF SEQUENCE',
    'IP-01': 'INCORRECT DOSAGE REGIMEN / ROUTE FOR THE STUDY INTERVENTION',
    'IP-02': 'SUBJECT MET STUDY INTERVENTION WITHDRAWAL CRITERIA BUT WAS NOT WITHDRAWN',
    'IP-03': 'NON-COMPLIANCE WITH STUDY INTERVENTION',
    'IP-04': 'INCORRECT DOSAGE REGIMEN FOR THE STUDY INTERVENTION',
    'SAMP-01': 'ASSESSMENT PERFORMED OUT OF SEQUENCE',
    'SAMP-02': 'ASSESSMENT PERFORMED OUTSIDE OF TIMING WINDOW',
    'CM-01': 'USE OF PROHIBITED MEDICATION',
    'CM-02': 'INCORRECT DOSAGE REGIMEN FOR THE BACKGROUND MEDICATION/RESCUE MEDICATION',
    'CM-03': 'SUBJECT MET STUDY INTERVENTION WITHDRAWAL CRITERIA BUT WAS NOT WITHDRAWN',
    'SAFE-01': '（潜在）ADVERSE EVENT(S) NOT REPORTED',
    'SAFE-02': 'SERIOUS ADVERSE EVENT(S) REPORTED LATE',
    'SAFE-03': '（潜在）ADVERSE EVENT(S) NOT REPORTED',
    'WD-01': 'SUBJECT MET STUDY INTERVENTION WITHDRAWAL CRITERIA BUT WAS NOT WITHDRAWN',
    'WD-02': 'SUBJECT MET STUDY INTERVENTION INTERRUPTION CRITERIA BUT WAS NOT INTERRUPTED'}
# 只能由源文件核查/外部系统确认的 PD（页面如实标注「需 SDV」，不从 listing 推断）
NOT_DETECTABLE = [
    ('ICF', '知情同意书原件是否存在、签名/日期/时间要素是否完整、执行人是否获授权、版本是否经伦理批准'),
    ('IP', '药物运输、接收、储存温度（超温）、有效期、药物编号是否正确、发放回收清点与销毁'),
    ('RAND', '随机系统中的分层值与药号分配、紧急揭盲记录'),
    ('SAFE', 'SAE/妊娠的获知时间与报告提交时间（数据表无获知/报告日期时）'),
    ('ASMT', '访视内操作细节：静息时长、空腹采血、采血与生命体征/心电图的先后（无时刻字段时）'),
    ('SAMP', '样本处理、离心、分装、冷链运输与储存'),
    ('ELIG', '需研究者判断或源文件支持的入排条件（如「研究者认为不适合」）'),
    ('OTH', '伦理规范执行、参与者隐私保护'),
]


def _d(s):
    return dt.date.fromisoformat(s) if is_full_date(s) else None


def _dt(d, t):
    """日期＋时刻 → datetime；时刻不可解析（UK:UK、全角冒号已归一）→ None。"""
    if not is_full_date(d) or not t:
        return None
    m = re.match(r'^\s*(\d{1,2})[:：](\d{2})', str(t))
    if not m:
        return None
    try:
        return dt.datetime.fromisoformat(d).replace(hour=int(m.group(1)), minute=int(m.group(2)))
    except ValueError:
        return None


_HIST_FORM = re.compile(r'诊断|既往|病史|发病史|疾病史|history|diagnos', re.I)


def _sh(r, sheet_key='sheet'):
    """证据 sheet 引用：带工作簿别名时用唯一 id「wb:sheet」（同名 sheet 跨工作簿不混淆）。"""
    sh = r.get(sheet_key) or ''
    return f"{r['wb']}:{sh}" if r.get('wb') and sh and ':' not in sh else sh


def _last_dose(e):
    """给药记录的末次日期（区间型记录取结束日期，单次记录取开始日期）。"""
    return e.get('end') if is_full_date(e.get('end')) else e.get('start')


def _grade_std(s):
    s = str(s or '')
    for pat, g in GRADE_STD:
        if re.search(pat, s, re.I):
            return g
    return '待判定' if s else ''


def _classify(text, extra=None):
    for code, pat in (extra or []) + CAT_RE:
        if re.search(pat, text or '', re.I):
            return code
    return 'OTH'


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


class _PD:
    def __init__(self, C):
        self.C = C
        self.P = (C.A.get('pd') or {})
        self.items = []
        self.ran = {}             # rule id → 'ran' | 'unconfigured' | 'no-data'
        self.cutoff = C.S.get('cutoff') or (C.cfg.get('cutoff')) or max(
            [r.get('date') or '' for r in C.visits if is_full_date(r.get('date'))] + [''])
        crit = self.P.get('criticalVisits') or []
        self.crit_visits = set(crit)
        # 数据阶段（工作台入口选择）：daily 日常监查（滚动录入）/ prelock 锁库前全量 / cfdi 锁库后核查前；缺省按全量
        self.stage = C.cfg.get('dataStage') or 'prelock'
        self.crit_items = crit_items(C)[0]       # V5：与 KRI 同一容错匹配（方案「EASI评分」↔ 数据「EASI得分」），否则关键评估缺失永不升级为重要

    def add(self, rule, sid, fact, *, date=None, visit=None, src=None, grade=None, why='', sig=None, action=None, ctx=None, tip=''):
        cat, title, g0, act0, _, _ = RULES[rule]
        # 分级优先级：个案判定（关键访视升级、例外条款降为待判定等）> 本研究 PD 界定表（analysis.pd.grades）> 规则默认
        pg = (self.P.get('grades') or {}).get(rule)
        g = grade or pg or g0
        if not grade and pg:
            basis = '本研究 PD 界定表：' + ((self.P.get('gradeBasis') or {}).get(rule) or pg)
            why = f'{why}；{basis}' if why and not why.startswith('规则默认') else basis
        s = self.C.subj.get(sid) or {}
        it = {'id': '', 'sid': sid, 'site': s.get('site', ''), 'cat': cat, 'layer': TAX[cat][2], 'rule': rule, 'title': title,
              'dv': RULE_DV.get(rule, ''),
              'fact': fact, 'date': date or '', 'visit': visit or '', 'grade': g, 'why': why or ('规则默认分级：' + g0),
              'action': action or act0, 'src': src or [], 'sig': sig, 'ctx': ctx or [], 'status': '', 'matched': '', 'tip': tip}
        self.items.append(it)
        return it

    # ------------------------------------------------------------------ 来自既有信号（科学层面为主）
    def from_signals(self):
        C = self.C
        imp_cm = [re.compile(p['re'], re.I) for p in (C.A.get('prohibited') or []) if p.get('important') and p.get('re')]
        for i, o in enumerate(C.others):
            hit = SIG_CAT.get(o['cat'])
            rule = hit[1] if hit else None
            if not rule and re.search(r'报告|时限', o['cat']) and re.search(r'SAE|AESI|报告', o.get('sum', '')):
                rule = 'SAFE-02'
            if not rule and o.get('_rule', {}).get('expectAE') and '未见对应 AE' in ' '.join(o.get('ctx') or []) + o.get('sum', '') \
                    and not o['_rule'].get('partial') and o['_rule'].get('query') is not False:
                rule = 'SAFE-03'      # 复合定义的单项（MY008 LDH>1.5×ULN 只是突破性溶血定义的一半，133 条假偏离）只作提示，不判偏离
            if not rule:
                continue
            grade, why = None, ''
            if rule == 'VIS-01' and o.get('v') in self.crit_visits:
                grade, why = '重要', f"{o.get('v')} 为关键访视（主要终点/关键评估）：超窗可能影响主要终点评估"
            if rule == 'CM-01' and any(rx.search(o.get('test') or '') for rx in imp_cm):
                grade, why = '重要', '该禁用药类别被方案列为影响疗效评价或安全的药物（可构成主要终点伴发事件）'
            if rule.startswith('ELIG'):
                st = o.get('_elig', 'violated')
                if st in ('exception_met', 'premise_unmet'):
                    continue                             # V6（用户审阅 RUX 第 9 条）：例外已满足/前提不成立 → 不构成偏离（信号仍作提示）
                why = '入组资格不符：参与者不应暴露于研究药物，且影响分析人群（ICH E3 Q&A 列举的典型重要偏离）'
                if st == 'undetermined':
                    grade, why = '待判定', '方案该标准带前提或例外条款，现有数据无法判定是否满足，需核实后再确定是否构成偏离'
            o['pd'] = rule
            self.add(rule, o['sid'], o['sum'], date=o.get('d'), visit=o.get('v'), src=[[_sh(o, 'sh'), o['row'], o.get('test') or '']],
                     grade=grade, why=why, sig=['oth', i, o.get('qkey', '')], ctx=list(o.get('ctx') or []))
        for i, g in enumerate(C.labrows):
            if g['risk'] not in LAB_PD:
                continue
            pts = [p for p in g['pts'] if p[5] == 2] or g['pts']
            # V6 第 2 轮 MY008（G2②）：引用点与分级同一时点——就所引用的那一次取值＋取级（此前首点数值配全程最高级，3/10 条错位）
            p = max(pts, key=lambda x: (x[4] or 0, abs(x[6] or 0)))
            gmax = p[4] or 0
            grade, why = None, '潜在：经研究者确认应记录而未记录 AE 方构成 PD'
            if gmax >= 3:
                grade, why = '重要', f"数值已达 {C.GL} {gmax} 级：若确认未记录 AE，属可能影响安全性评价的重要偏离"
            g['pd'] = 'SAFE-01'
            # H7（第 3 轮 SAR）：附注与所引时点同源——ctx 里带「较基线…%」的括注按所引点 p 自己的涨幅重写
            # （构建端 ctx 的涨幅来自首个加重点，可能与引用点不同访视：引用 V1 数值配 V2 涨幅，SAR 实证）
            ctx = list(g.get('ctx') or [])[:4]
            if p[6] is not None:
                own = f"较基线{'升高' if p[6] > 0 else '降低'} {abs(p[6]):.0f}%（所引 {p[0]} 时点）"
                ctx = [re.sub(r'（[^（）]*较基线[^（）)]*%）', f'（{own}）', c) if ('较基线' in c and '%' in c) else c for c in ctx]
            self.add('SAFE-01', g['sid'], f"{p[0]}（{p[1]}）{g['test']} {p[2]} {p[3]}：{LAB_PD[g['risk']]}",
                     date=p[1], visit=p[0], src=[[(f"{x[11]}:{x[7]}" if len(x) > 11 and x[11] else x[7]), x[8], g['test']] for x in pts[:4]], grade=grade, why=why,
                     sig=['lab', i, g.get('qkey', '')], action='发 query', ctx=ctx)
        if not any(a.get('aware') or a.get('rpt') for a in C.aes):
            self.ran.setdefault('SAFE-02', 'no-data')      # AE listing 无获知/报告日期：不能判报告是否超时
        if not C.A.get('visitWindows'):
            self.ran.setdefault('VIS-01', 'unconfigured')
        for c in ('ELIG-01', 'ELIG-02', 'CM-01', 'VIS-01', 'SAFE-01', 'SAFE-02', 'SAFE-03'):
            self.ran.setdefault(c, 'ran')

    # ------------------------------------------------------------------ 知情同意 / 随机
    def icf(self):
        C, P = self.C, self.P
        allow = [(_pre_icf_rx(a['item']), a.get('ref', 'icf'), int(a.get('days', 0))) for a in (P.get('preIcfAllowed') or []) if a.get('item')]
        self.ran['ICF-01'] = 'ran'
        for sid in sorted(C.pop):
            s = C.subj[sid]
            icf = s.get('icf')
            if not is_full_date(icf):
                continue
            early = []
            for v in C.visits:
                if v['sid'] == sid and is_full_date(v.get('date')) and v['date'] < icf:
                    early.append((v['date'], f"访视 {v.get('visit')}", _sh(v), v['row']))
            for f in C.findings:
                if f['sid'] != sid or not is_full_date(f.get('date')) or f['date'] >= icf:
                    continue
                if _HIST_FORM.search(f"{f.get('group') or ''}|{(C.A.get('formNames') or {}).get(f['sheet'], '')}|{f['sheet']}"):
                    continue          # 疾病诊断/既往史表记录的是既往诊疗结果，不是研究程序（MY008 2019 年 Ham 试验）
                tag = f"{f.get('group') or f['sheet']}|{f['test']}|{(C.A.get('formNames') or {}).get(f['sheet'], '')}|{f['sheet']}"
                ok, out_win = False, None
                for rx, ref, n in allow:
                    if rx.search(tag):
                        rd = s.get('fd') if ref == 'fd' else icf
                        if is_full_date(rd) and (days(rd, f['date']) or 0) <= n:
                            ok = True
                            break
                        anchor = '首剂' if ref == 'fd' else '知情'
                        out_win = f"方案允许沿用{anchor}前 {n} 天内的结果，该记录距{anchor} {days(rd, f['date']) if is_full_date(rd) else '?'} 天"
                if not ok:
                    early.append((f['date'], f"{f.get('group') or f['sheet']}·{f['test']}", _sh(f), f['row'], out_win))
            for e in C.exposure:
                if e['sid'] == sid and is_full_date(e.get('start')) and e['start'] < icf:
                    early.append((e['start'], '研究药物给药', _sh(e), e['row']))
            if early:
                early.sort()
                d0 = early[0]
                rs = yes(s.get('rescreen')) or bool(s.get('prev_sid'))
                g_rs = '待判定' if rs else None           # 重复筛选：早于本次知情的记录可能来自首次筛选（方案允许范围内沿用不构成偏离）
                kinds = sorted({x[1].split('·')[0] for x in early})
                days_ = sorted({x[0] for x in early})
                win = next((x[4] for x in early if len(x) > 4 and x[4]), None)
                self.add('ICF-01', sid, f"知情同意签署 {icf}，但 {d0[0]} 已有{d0[1]}；早于知情的记录共 {len(early)} 条，涉及 {'、'.join(kinds[:4])}{'等' if len(kinds) > 4 else ''}（{len(days_)} 个日期）"
                         + (f"；{win}" if win else ''), tip=ICF_TIP,
                         date=d0[0], src=[[x[2], x[3], x[1]] for x in early[:4]],
                         grade=g_rs, why=(f"重复筛选（首次筛选编号 {s.get('prev_sid') or '未填'}）：核实早于本次知情的记录是否为首次筛选所做、"
                                          "且沿用符合方案；否则按知情同意偏离处理") if rs else
                         '知情同意先于任何研究程序是参与者权益保护的基本要求（GCP）；核实是否为方案允许的既往常规诊疗结果')
        vers = P.get('icfVersions') or []
        icfs = getattr(C, 'icf', []) or []
        if vers and icfs:
            self.ran['ICF-02'] = 'ran'
            by = defaultdict(list)
            for r in icfs:
                by[r['sid']].append(r)
            for v in vers:
                if not v.get('reconsent') or not is_full_date(v.get('effective')):
                    continue
                for sid in sorted(C.pop):
                    s = C.subj[sid]
                    end = s.get('eos_d') or s.get('lo')
                    if not is_full_date(end) or end <= v['effective']:
                        continue
                    if not any(str(r.get('ver') or '').strip() == str(v['ver']) or (is_full_date(r.get('date')) and r['date'] >= v['effective'])
                               for r in by.get(sid, [])):
                        last = sorted(by.get(sid, []), key=lambda r: r.get('date') or '')
                        dn = ext_rules.daily_open(C, sid)
                        self.add('ICF-02', sid, f"知情同意 {v['ver']} 版 {v['effective']} 生效且要求再签，参与者其后仍在研（至 {end}），未见新版签署记录"
                                 + (f"（最近签署 {last[-1].get('ver') or '?'} 版 {dshow(last[-1].get('date'))}）" if last else ''),
                                 date=v['effective'], src=[[_sh(r), r['row'], '知情同意'] for r in last[-1:]],
                                 **({'grade': '待判定', 'why': ext_rules.DAILY_NOTE + '：新版签署记录可能尚未录入'} if dn else {}))
        else:
            self.ran['ICF-02'] = 'unconfigured' if not vers else 'no-data'
        self.ran['RAND-01'] = self.ran['RAND-02'] = 'ran'
        for sid in sorted(C.dosed):
            s = C.subj[sid]
            rd = s.get('rand_d')
            if is_full_date(rd) and is_full_date(s.get('fd')) and s['fd'] < rd:
                e = next((x for x in C.exposure if x['sid'] == sid and x.get('start') == s['fd']), {})
                self.add('RAND-01', sid, f"首次给药 {s['fd']} 早于随机日期 {rd}", date=s['fd'], src=[[_sh(e), e.get('row'), '给药']])
            # 「无随机信息」只在方案为随机研究（analysis.pd.requireRand）时才判，单臂/开放研究不会误报
            if (s.get('status') == '筛选失败') or (P.get('requireRand') and not rd and not s.get('rand')):
                # 证据指针取「有 start 的研究药物行」（SAR 深审 F3：首行可能是无日期的滥用史/占位行 → 溯源错表）
                e = next((x for x in C.exposure if x['sid'] == sid and x.get('start') == s['fd']),
                         next((x for x in C.exposure if x['sid'] == sid and is_full_date(x.get('start'))), {}))
                self.add('RAND-02', sid, f"状态为「{s.get('status')}」/无随机信息，但有研究药物给药记录（{s.get('fd')}）", date=s.get('fd'),
                         src=[[_sh(e), e.get('row'), '给药']])

    # ------------------------------------------------------------------ 访视缺失
    def missed_visits(self):
        C = self.C
        if self.stage == 'daily':                       # 用户 2026-10-28：滚动录入阶段 listing 不一定最新，「无记录」不等于缺失
            self.ran['VIS-02'] = 'stage-off'
            return
        W = C.A.get('visitWindows') or {}
        if not W:
            self.ran['VIS-02'] = 'unconfigured'
            return
        have = defaultdict(set)
        for v in C.visits:
            if v.get('visit'):
                have[v['sid']].add(v['visit'])
        seen = set().union(*have.values()) if have else set()
        if sum(1 for k in W if k in seen) * 2 < len(W):
            self.ran['VIS-02'] = 'unconfigured'           # 方案访视代码与 listing 对不上（半数以上未出现）：不推断缺失
            return
        self.ran['VIS-02'] = 'ran'
        if not is_full_date(self.cutoff):
            return
        from monitor_v5 import arm_specific_visits
        arm_skip = arm_specific_visits(C)
        for sid in sorted(C.dosed):
            s = C.subj[sid]
            et_d = min((v['date'] for v in C.visits if v['sid'] == sid and v.get('visit') in C.ET and is_full_date(v.get('date'))), default=None)
            # 研究结束日期 / （可选）治疗结束日期 / 提前退出访视日期：之后不再期待计划访视
            stop = min([d for d in (s.get('eos_d'), s.get('eot_d') if self.P.get('stopAtEot') else None, et_d) if is_full_date(d)] or [self.cutoff])
            for vis, spec in W.items():
                if vis in have[sid] or (vis, s.get('grp')) in arm_skip:
                    continue                              # 组别专属访视（monitor_v5.arm_specific_visits）：该组不期待
                if isinstance(spec, dict):
                    t, plus, anc = spec.get('target'), spec.get('plus', 0), spec.get('anchor', 'fd')
                else:
                    (t, _, plus), anc = spec[:3], 'fd'
                if anc == 'fd':
                    base = s.get('fd')
                    close = (_d(base) + dt.timedelta(days=int(t) - 1 + int(plus))) if _d(base) and t is not None else None
                elif anc in ('ld',):
                    base = s.get('ld')
                    close = (_d(base) + dt.timedelta(days=int(t) + int(plus))) if _d(base) and t is not None else None
                else:
                    continue                              # 前一访视锚点：依赖前一访视实际日期，缺失链式判断交 CRA
                if not close or close.isoformat() >= stop or close.isoformat() >= self.cutoff:
                    continue
                crit = vis in self.crit_visits
                self.add('VIS-02', sid, f"{vis} 窗口已于 {close.isoformat()} 关闭，参与者其后仍在研，未见该访视记录",
                         date=close.isoformat(), visit=vis, grade='重要' if crit else None,
                         why=(f'{vis} 为关键访视：缺失影响主要终点/关键安全评估' if crit else '规则默认分级：一般（随之缺失的检查不另报）'),
                         src=[])

    # ------------------------------------------------------------------ 评估缺失 / 未做（基于 SoA 完成度）
    def assessments(self):
        C = self.C
        if not getattr(C, 'soa', None):
            self.ran['ASMT-01'] = self.ran['ASMT-02'] = 'no-data'
            return
        proto = bool(C.A.get('soa'))
        if not proto:
            # SoA 未由方案配置时，「应做项目」只能由数据推断——拆表、条件性检查、复用既往结果都会造成大量假缺失，
            # 不生成评估缺失类潜在 PD（SoA 完成度矩阵照常展示供人工判断）
            self.ran['ASMT-01'] = self.ran['ASMT-02'] = 'unconfigured'
            return
        self.ran['ASMT-01'] = 'stage-off' if self.stage == 'daily' else 'ran'   # 滚动录入阶段不判「无记录」；明确记录为未做（ASMT-02）照常
        self.ran['ASMT-02'] = 'ran'
        for row in C.soa:
            name = row['name']
            crit = bool(self.crit_items and self.crit_items.search(name))
            for vis, cell in row['cells'].items():
                if cell[6] or vis not in row['exp'] or row.get('judge') is False or (len(cell) > 7 and cell[7]):
                    continue                     # V6：不判缺失的项目（必要时/部分参与者）与合理性守卫压下的格子不逐人生成
                for sid in (cell[4] if self.stage != 'daily' else []):
                    if sid not in C.pop:
                        continue
                    self.add('ASMT-01', sid, f"{vis} 已完成访视，但未见「{name}」记录" + ('' if proto else '（按本研究多数参与者的完成情况推断为该访视应做项目）'),
                             visit=vis, grade='重要' if crit else None,
                             why=('关键评估缺失（主要终点/安全监测）' if crit else ('规则默认分级：一般' + ('' if proto else '；SoA 未由方案配置，期望项目为数据推断，置信度较低'))),
                             src=[], ctx=[] if proto else ['SoA 推断'])
                for sid in cell[5]:
                    if sid not in C.pop:
                        continue
                    self.add('ASMT-02', sid, f"{vis}「{name}」记录为未查/未做", visit=vis,
                             grade='重要' if crit else None, why='关键评估未做' if crit else '是否属方案允许情形（如条件性检查、可复用既往结果）需结合原因判断')

    # ------------------------------------------------------------------ 访视内先后顺序（需时刻）
    def order(self):
        C, rules = self.C, self.P.get('order') or []
        if not rules:
            self.ran['ASMT-03'] = 'unconfigured'
            return
        self.ran['ASMT-03'] = 'ran'
        dose_t = defaultdict(list)
        for e in C.exposure:
            t = _dt(e.get('start'), e.get('time'))
            if t:
                dose_t[e['sid']].append((t, e))
        seen = {}
        for R in rules:
            bre = re.compile(R['before'])
            after = R.get('after', 'dose')
            are = None if after == 'dose' else re.compile(after)
            vis = set(R.get('visits') or [])
            tre = re.compile(R['tptRe']) if R.get('tptRe') else None
            for f in C.findings + [dict(x, test=x.get('metric'), group=x.get('metric')) for x in C.efficacy]:
                if f['sid'] not in C.pop or (vis and f.get('visit') not in vis):
                    continue
                if tre and not tre.search(str(f.get('tpt') or '')):
                    continue
                if not bre.search(f"{f.get('group') or ''}|{f.get('test') or ''}|{f.get('sheet') or ''}"):
                    continue
                tf = _dt(f.get('date'), f.get('time'))
                if not tf:
                    continue
                if are is None:
                    same = [(t, e) for t, e in dose_t.get(f['sid'], []) if t.date() == tf.date()]
                    if same and min(same, key=lambda x: x[0])[0] < tf:
                        t0, e0 = min(same, key=lambda x: x[0])
                        key = (f['sid'], f.get('sheet'), f.get('row'))
                        if key in seen:                     # 宽表一行多指标（如生命体征）只算一次偏离
                            seen[key]['fact'] = seen[key]['fact'].replace('记录时刻', f"/{f.get('test')} 记录时刻", 1)
                            continue
                        seen[key] = self.add('ASMT-03', f['sid'], f"{f.get('visit')}（{f.get('date')}）{f.get('group') or ''}·{f.get('test')} 记录时刻 {tf.strftime('%H:%M')}，晚于当日给药 {t0.strftime('%H:%M')}；方案要求{R.get('label') or '在给药前完成'}",
                                             date=f.get('date'), visit=f.get('visit'), src=[[_sh(f), f['row'], f.get('test') or ''], [_sh(e0), e0['row'], '给药']],
                                             grade=R.get('grade'), why=R.get('why') or '')

    # ------------------------------------------------------------------ 给药
    def dosing(self):
        C, P = self.C, self.P
        self.ran['IP-02'] = 'ran'
        preg = defaultdict(list)
        for o in C.others:
            if o.get('_preg_pos'):                       # V6 R1：只认结构化妊娠检验阳性（描述文本命中不级联判偏离）
                preg[o['sid']].append(o['_preg_pos'])
        stop_hit = defaultdict(list)
        for o in C.others:
            if o.get('_rule', {}).get('stop') and is_full_date(o.get('d')):
                stop_hit[o['sid']].append((o['d'], o))
        self.ran['WD-01'] = 'ran' if any(R.get('stop') for R in C.A.get('thresholdRules') or []) else 'unconfigured'
        for sid in sorted(C.dosed):
            s = C.subj[sid]
            ex = sorted([e for e in C.exposure if e['sid'] == sid and is_full_date(e.get('start'))], key=lambda e: e['start'])
            ends = [(s.get('eot_d'), '治疗结束'), (s.get('eos_d'), '研究结束')] + [(d, '妊娠试验阳性') for d in sorted(preg.get(sid, []))[:1]]
            for d, why in ends:
                if not is_full_date(d):
                    continue
                late = [e for e in ex if (_last_dose(e) or '') > d and is_dosing(e) and not str(e.get('dose') or '').strip() in ('0', '0.0')]
                if late:
                    e = late[0]
                    self.add('IP-02', sid, f"{why}日期 {d}，给药记录至 {_last_dose(e)}（{e['start']} 起）", date=_last_dose(e),
                             src=[[_sh(e), e['row'], '给药']], why='终止治疗后继续暴露于研究药物，可能影响参与者安全（重要偏离）')
                    break
            for d, o in sorted(stop_hit.get(sid, []), key=lambda x: x[0])[:1]:   # 按达标日期排序（元组含 dict，显式 key 防比较崩溃）
                late = [e for e in ex if (_last_dose(e) or '') > d and is_dosing(e)]
                if not late:
                    continue
                e = late[0]
                lab = o['_rule'].get('label') or o['cat']
                # V6（RUX 审阅第 11 条）：达标前后已暂停给药（医嘱调整「暂停用药」区间覆盖达标日附近）、之后又恢复——
                # 不是「给药持续」；按方案停药是否以「复查确认」为前提，列为待判定并请提供复测确认情况（用户裁定 11＝A）
                pause = next((x for x in ex if dose_state(x) in ('paused', 'withdrawn') and days(x.get('start'), d) is not None
                              and -3 <= days(x['start'], d) <= 7), None)        # 注意 0 天（同日暂停）不能被当成假值
                if pause is not None:
                    pe = _last_dose(pause) if pause.get('end') else pause['start']
                    self.add('WD-01', sid, f"{o.get('test')} {o.get('v') or ''}（{d}）达到方案停药标准（{lab}），{pause['start']} 起已暂停给药"
                                           f"{('至 ' + pe) if pe and pe != pause['start'] else ''}，{e['start']} 恢复给药",
                             date=e['start'], src=[[_sh(o, 'sh'), o['row'], o.get('test') or ''], [_sh(pause), pause['row'], '暂停给药'],
                                                   [_sh(e), e['row'], '恢复给药']],
                             grade='待判定', why='达标后已暂停给药并恢复：方案停药是否以复查确认为前提、恢复前复测是否已低于标准，需核实')
                    continue
                # 给药表没有暂停记录、但同期 AE 的研究药物措施是暂停/停药（与 WD-02、阈值「已处理」同口径）→ 同样不是「给药持续」
                aei = next((a for a in C.ae_by.get(sid, []) if ae_action(a.get('act')) in ('interrupted', 'withdrawn') and is_full_date(a.get('s'))
                            and -3 <= days(a['s'], d) <= 7), None)
                if aei is not None:
                    self.add('WD-01', sid, f"{o.get('test')} {o.get('v') or ''}（{d}）达到方案停药标准（{lab}），同期 AE“{aei['t']}”（{aei['s']}）"
                                           f"措施为{aei.get('act')}，给药记录至 {_last_dose(late[-1])}",
                             date=d, src=[[_sh(o, 'sh'), o['row'], o.get('test') or ''], [_sh(aei, 'sh'), aei.get('row'), 'AE 措施'],
                                          [_sh(e), e['row'], '恢复给药']],
                             grade='待判定', why='AE 记录显示已暂停研究药物，但给药表未记暂停区间：请核对给药记录与 AE 措施是否一致、恢复前是否复查确认')
                    continue
                self.add('WD-01', sid, f"{o.get('test')} {o.get('v') or ''}（{d}）达到方案停药标准（{lab}），给药记录持续至 {_last_dose(e)}",
                         date=_last_dose(e), src=[[_sh(o, 'sh'), o['row'], o.get('test') or ''], [_sh(e), e['row'], '给药']],
                         grade='待判定' if o['_rule'].get('stopCond') else None,
                         why=('方案停药标准带前提（' + o['_rule']['stopCond'] + '…）：需核实前提是否满足') if o['_rule'].get('stopCond') else '')
        # V6 医学审阅（RUX S01017 W16 ALT 3.1×ULN 31 天后才暂停、S17003 NEU 1.35 未暂停，偏离清单无此类规则）：中断标准未执行
        irs = [o for o in C.others if 'interrupt' in (o.get('_rule', {}).get('acts') or []) and not o['_rule'].get('stop') and is_full_date(o.get('d'))]
        self.ran['WD-02'] = 'ran' if any('interrupt' in (R.get('acts') or []) for R in C.A.get('thresholdRules') or []) else 'unconfigured'
        seen_wd2 = set()
        for o in sorted(irs, key=lambda x: (x['sid'], x['d'])):
            sid, d = o['sid'], o['d']
            key = (sid, o['_rule'].get('id') or o['_rule'].get('label'))
            if sid not in C.dosed or key in seen_wd2:
                continue
            ex = [e for e in C.exposure if e['sid'] == sid and is_full_date(e.get('start'))]
            paused = any(dose_state(e) in ('paused', 'withdrawn') and days(e['start'], d) is not None and -1 <= days(e['start'], d) <= 7 for e in ex)
            ae_int = any(ae_action(a.get('act')) in ('interrupted', 'withdrawn') and is_full_date(a.get('s')) and abs(days(a["s"], d)) <= 7
                         for a in C.ae_by.get(sid, []))
            later = [e for e in ex if is_dosing(e) and (_last_dose(e) or '') > (d[:10] if d else '') and (days(_last_dose(e), d) or 0) > 7]
            if paused or ae_int or not later:
                continue
            seen_wd2.add(key)
            lab = o['_rule'].get('label') or o['cat']
            self.add('WD-02', sid, f"{o.get('test')} {o.get('v') or ''}（{d}）达到方案中断标准（{lab}），其后 7 天内未见暂停给药记录，给药持续至 {_last_dose(later[-1])}",
                     date=d, src=[[_sh(o, 'sh'), o['row'], o.get('test') or ''], [_sh(later[0]), later[0]['row'], '给药']], grade='待判定',
                     why='方案要求达此标准时中断研究药物；是否以研究者判断与研究药物相关为前提、是否已复查确认，需结合源文件核实')
        dz = P.get('dosing') or {}
        if dz:
            self.ran['IP-01'] = 'ran'
            for e in C.exposure:
                if e['sid'] not in C.dosed:
                    continue
                bad = []
                for k, lab in (('route', '途径'), ('freq', '频次')):
                    want = dz.get(k)
                    got = str(e.get(k) or '').strip()
                    if want and got and not re.search(want, got, re.I):
                        bad.append(f"{lab}「{got}」（方案：{dz.get(k + 'Label') or want}）")
                if bad:
                    self.add('IP-01', e['sid'], f"{dshow(e.get('start'))} 给药记录 " + '；'.join(bad), date=e.get('start'), visit=e.get('visit'),
                             src=[[_sh(e), e['row'], '给药']])
        else:
            self.ran['IP-01'] = 'unconfigured'
        if P.get('fasting'):
            self.ran['IP-04'] = 'ran'
            for e in C.exposure:
                if e['sid'] in C.dosed and re.search(r'^(否|N|no)$', str(e.get('fast') or '').strip(), re.I):
                    self.add('IP-04', e['sid'], f"{dshow(e.get('start'))} 给药记录为非空腹（方案要求空腹服药）", date=e.get('start'), visit=e.get('visit'),
                             src=[[_sh(e), e['row'], '给药']])
        else:
            self.ran['IP-04'] = 'unconfigured'
        cp = P.get('compliance') or {}
        if cp and cp.get('perDay'):
            self.ran['IP-03'] = 'ran'
            lo, hi, per = float(cp.get('lo', 80)), float(cp.get('hi', 120)), float(cp['perDay'])
            min_days = int(cp.get('minDays', 14))
            for sid in sorted(C.dosed):
                eot = C.subj.get(sid, {}).get('eot_d')
                ex = [e for e in C.exposure if e['sid'] == sid and is_full_date(e.get('start')) and
                      (e.get('qty') not in (None, '') or _num(e.get('dose_plan'))) and not (is_full_date(eot) and e['start'] > eot)]
                if not ex:
                    continue
                tot_d = tot_q = 0
                for e in ex:
                    end = e.get('end') if is_full_date(e.get('end')) else e['start']
                    n = (days(end, e['start']) or 0) + 1
                    try:
                        if e.get('qty') not in (None, ''):
                            q = float(e['qty'])
                        else:
                            # 剂量制（每日计划剂量 / 每日实际剂量 ± 漏服、多服总剂量）→ 折算成「应服单位」
                            plan = _num(e.get('dose_plan'))
                            act = _num(e.get('dose_act'))
                            act = plan if act is None else act
                            miss = 0 if act == 0 else (_num(e.get('miss_qty')) or 0)
                            q = max(0.0, (act * n - miss + (_num(e.get('extra_qty')) or 0)) / plan * per)
                    except (TypeError, ValueError, ZeroDivisionError):
                        continue
                    tot_d += n
                    tot_q += q
                if tot_d < min_days:
                    continue
                pct = tot_q / (tot_d * per) * 100 if tot_d else None
                if pct is not None and (pct < lo or pct > hi):
                    dn = ext_rules.daily_open(C, sid)
                    self.add('IP-03', sid, f"累计给药 {tot_d} 天、实际 {fmt(tot_q)}（应 {fmt(tot_d * per)}），依从性 {pct:.0f}%，超出方案范围 {fmt(lo)}%–{fmt(hi)}%",
                             src=[[_sh(ex[0]), ex[0]['row'], '给药']], date=ex[-1].get('end') or ex[-1].get('start'),
                             **({'grade': '待判定', 'why': ext_rules.DAILY_NOTE + '：给药/发药回收记录可能尚未录全'} if dn else {}))
        else:
            self.ran['IP-03'] = 'unconfigured'

    # ------------------------------------------------------------------ 样本采集
    def samples(self):
        C, P = self.C, self.P
        sm = getattr(C, 'sample', []) or []
        if not sm:
            self.ran['SAMP-01'] = self.ran['SAMP-02'] = 'no-data'
            return
        self.ran['SAMP-01'] = self.ran['SAMP-02'] = 'ran'
        pre = re.compile((P.get('sample') or {}).get('preRe') or r'给药前|服药前|pre-?dose|谷')
        win = (P.get('sample') or {}).get('windowMin')
        wins = (P.get('sample') or {}).get('windows') or []
        dose_t = defaultdict(list)
        for e in C.exposure:
            t = _dt(e.get('start'), e.get('time'))
            if t:
                dose_t[e['sid']].append(t)
        samp2 = {}                                     # K10：同一采血时刻的多管（如 PC/PD 各一管）只报一条，事实列样本类型

        def add_samp2(r, tail, src):
            key = (r['sid'], r.get('visit'), r.get('date'), r.get('tpt'), r.get('time'))
            e = samp2.get(key)
            sh = r.get('sheet') or ''
            if e is None:
                samp2[key] = {'sid': r['sid'], 'visit': r.get('visit'), 'date': r.get('date'),
                              'head': f"{r.get('visit')}（{r.get('date')}）{r.get('tpt') or ''}",
                              'tail': tail, 'src': list(src), 'sheets': [sh] if sh else []}
            else:
                e['src'] += [s for s in src if s not in e['src']]
                if sh and sh not in e['sheets']:
                    e['sheets'].append(sh)

        for r in sm:
            if r['sid'] not in C.pop or not_done(r.get('done')):
                continue
            ts = _dt(r.get('date'), r.get('time'))
            td = _dt(r.get('dose_date') or r.get('date'), r.get('dose_time')) if r.get('dose_time') else \
                next((t for t in sorted(dose_t.get(r['sid'], []), reverse=False) if ts and t.date() == ts.date()), None)
            if not ts or not td:
                continue
            tpt = str(r.get('tpt') or '')
            src = [[_sh(r), r['row'], tpt or '样本']]
            kind = f"（{r.get('sheet')}）" if r.get('sheet') else ''
            if pre.search(tpt):
                lim = re.search(r'前\s*(\d+(?:\.\d+)?)\s*(h|小时|min|分钟)\s*内', tpt, re.I)
                if ts > td and ts.date() == td.date():
                    self.add('SAMP-01', r['sid'], f"{r.get('visit')}（{r.get('date')}）{tpt}{kind} 样本采集 {ts.strftime('%H:%M')}，晚于当次给药 {td.strftime('%H:%M')}",
                             date=r.get('date'), visit=r.get('visit'), src=src)
                elif lim and ts <= td and (td - ts).total_seconds() / 60 > float(lim.group(1)) * (60 if lim.group(2).lower() in ('h', '小时') else 1):
                    add_samp2(r, f" 样本于给药前 {(td - ts).total_seconds() / 60:.0f} 分钟采集，早于方案窗口", src)
                continue
            m = re.search(r'(\d+(?:\.\d+)?)\s*(h|小时|hr|min|分钟)', tpt, re.I)
            own = re.search(r'[±＋+]\s*(\d+(?:\.\d+)?)\s*(h|小时|hr|min|分钟)', tpt, re.I)   # 时点标签自带窗口（「4h±30min」）优先
            if m and (win is not None or own or wins):
                nominal = float(m.group(1)) * (60 if m.group(2).lower() in ('h', '小时', 'hr') else 1)
                actual = (ts - td).total_seconds() / 60
                if own:
                    w = float(own.group(1)) * (60 if own.group(2).lower() in ('h', '小时', 'hr') else 1)
                elif wins:                                # 方案按「访视 × 计划时点」规定的窗口
                    w = next((x['w'] for x in wins if x.get('visit') == r.get('visit') and abs(x['nom'] - nominal) < 1e-6), None)
                    if w is None:
                        continue                          # 该访视/时点方案未给窗口：不推断
                else:
                    w = float(win.get(m.group(0), win.get('default', 0))) if isinstance(win, dict) else float(win)
                if w and abs(actual - nominal) > w:
                    add_samp2(r, f" 样本实际于给药后 {actual:.0f} 分钟采集（计划 {nominal:.0f}±{w:.0f} 分钟）", src)
        for e in samp2.values():
            kind = f"（{'/'.join(e['sheets'])}）" if e['sheets'] else ''
            self.add('SAMP-02', e['sid'], e['head'] + kind + e['tail'], date=e['date'], visit=e['visit'], src=e['src'])

    # ------------------------------------------------------------------ 补救治疗
    def rescue(self):
        C, R = self.C, (self.P.get('rescue') or {})
        if not R.get('re'):
            self.ran['CM-02'] = self.ran['CM-03'] = 'unconfigured'
            return
        rx = re.compile(R['re'], re.I)
        self.ran['CM-02'] = 'ran' if R.get('earliestDay') else 'unconfigured'
        self.ran['CM-03'] = 'ran' if R.get('stopRequired') and R.get('stopRe') else 'unconfigured'   # 未列出须停药的补救药物时不执行（否则外用补救也会被判）
        for sid in sorted(C.dosed):
            s = C.subj[sid]
            for c in C.cm_by[sid]:
                if not (rx.search(c['t']) or rx.search(c.get('why') or '') or re.search(r'补救|挽救|rescue', c.get('why') or '', re.I)) \
                        or not is_full_date(c['s']) or not is_full_date(s.get('fd')):
                    continue
                sd = (days(c['s'], s['fd']) or 0) + 1
                if R.get('earliestDay') and 0 < sd < int(R['earliestDay']):
                    self.add('CM-02', sid, f"补救治疗「{c['t']}」于研究日 D{sd}（{c['s']}）开始，早于方案允许的 D{R['earliestDay']}",
                             date=c['s'], src=[[_sh(c, 'sh'), c['row'], c['t']]])
                if R.get('stopRequired') and R.get('stopRe') and re.search(R['stopRe'], f"{c['t']}|{c.get('rt') or ''}", re.I):
                    late = [e for e in C.exposure if e['sid'] == sid and (_last_dose(e) or '') > c['s']]
                    if late:
                        self.add('CM-03', sid, f"补救治疗「{c['t']}」{c['s']} 开始，方案要求其后永久停用研究药物，但给药记录持续至 {_last_dose(late[0])}",
                                 date=_last_dose(late[0]), src=[[_sh(c, 'sh'), c['row'], c['t']], [_sh(late[0]), late[0]['row'], '给药']])

    # ------------------------------------------------------------------ 已记录 PD 归一与比对
    def confirmed(self):
        C, P = self.C, self.P
        extra = [(c, p) for p, c in (P.get('catMap') or [])]
        out = []
        for i, p in enumerate(C.pd):
            # SAR 第 8 轮运营审阅：描述里交代背景（「…于 2025.9.10 随机，V5 超窗 12 天」）会让「随机」先命中 → 159 条错归「随机与盲态」、
            # 40 条已登记超窗与潜在超窗对不上。先按记录表自带的类别/子类判，判不出再看描述
            code = _classify(f"{p.get('cat') or ''} {p.get('sub') or ''}", extra)
            if code == 'OTH':
                code = _classify(f"{p.get('cat') or ''} {p.get('sub') or ''} {p.get('desc') or ''}", extra)
            s = C.subj.get(p['sid']) or {}
            out.append({'id': f"PD{i + 1:03d}", 'sid': p['sid'], 'site': s.get('site', p.get('site') or ''), 'cat': code,
                        'layer': TAX[code][2], 'rawCat': p.get('cat') or '', 'sub': p.get('sub') or '', 'desc': p.get('desc') or '',
                        'date': p.get('date') or '', 'grade': _grade_std(p.get('grade')) or '', 'rawGrade': p.get('grade') or '',
                        'status': p.get('status') or '', 'visit': p.get('visit') or '', 'src': [[_sh(p), p['row'], '方案偏离记录']], 'matched': []})
        win = int(C.A.get('pdWindow', P.get('window', 30)))
        for it in self.items:
            if not C.pd:
                it['status'] = '无 PD 记录可比对'
                continue
            best = None
            for c in out:
                if c['sid'] != it['sid'] or c['cat'] != it['cat']:
                    continue
                dd = days(c['date'], it['date']) if is_full_date(c['date']) and is_full_date(it['date']) else None
                if dd is None or abs(dd) <= win:
                    if best is None or (dd is not None and abs(dd) < best[0]):
                        best = (abs(dd) if dd is not None else 999, c)
            if best is None and it.get('visit'):
                # 兜底：同参与者、同访视、日期相差 ≤3 天（类别口径不同也视为同一事件）
                for c in out:
                    dd = days(c['date'], it['date']) if is_full_date(c['date']) and is_full_date(it['date']) else None
                    if c['sid'] == it['sid'] and c.get('visit') and c['visit'] == it['visit'] and dd is not None and abs(dd) <= 3:
                        best = (abs(dd), c)
                        break
            if best:
                it['status'], it['matched'] = '已记录', best[1]['id']
                best[1]['matched'].append(it['rule'])
            else:
                it['status'] = '未见记录'
        return out


def run(C):
    """→ KZ.pd 数据面。PD listing 缺失时潜在 PD 照常识别，状态标「无 PD 记录可比对」。"""
    if (C.A.get('pd') or {}).get('enabled') is False:
        C.pdd = None
        return None
    E = _PD(C)
    E.from_signals()
    E.icf()
    E.missed_visits()
    E.assessments()
    E.order()
    E.dosing()
    E.samples()
    E.rescue()
    conf = E.confirmed()
    order = {g: i for i, g in enumerate(['重要', '待判定', '一般'])}
    E.items.sort(key=lambda x: (order.get(x['grade'], 9), x['cat'], x['sid'], x['date']))
    for n, it in enumerate(E.items, 1):
        it['id'] = f"P{n:04d}"
        if it['sig']:
            kind, idx = it['sig'][0], it['sig'][1]
            (C.others if kind == 'oth' else C.labrows)[idx].setdefault('pdId', it['id'])
    by_site = defaultdict(Counter)
    for it in E.items:
        by_site[it['site']][it['cat']] += 1
    rules = [{'id': rid, 'cat': r[0], 'title': r[1], 'grade': (E.P.get('grades') or {}).get(rid) or r[2], 'action': r[3], 'dv': RULE_DV.get(rid, ''),
              'logic': re.sub(r'（analysis\.[^）]*）', '', r[4]), 'cfg': '；'.join(re.findall(r'analysis\.[\w.\[\]]+', r[4])), 'data': r[5], 'state': E.ran.get(rid, 'unconfigured'), 'reason': (REASON.get(rid) or {}).get(E.ran.get(rid, 'unconfigured'), ''),
              'n': sum(1 for x in E.items if x['rule'] == rid)} for rid, r in RULES.items()]
    C.pdd = {'taxonomy': [list(t) for t in TAXONOMY], 'potential': E.items, 'confirmed': conf, 'rules': rules,
             'notDetectable': [list(x) for x in NOT_DETECTABLE], 'cutoff': E.cutoff, 'hasListing': bool(C.pd),
             'sites': {k: dict(v) for k, v in by_site.items()},
             'critical': {'visits': sorted(E.crit_visits), 'items': E.P.get('criticalItems') or ''}}
    return C.pdd
