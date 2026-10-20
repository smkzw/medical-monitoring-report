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

DOMAIN_RE = [  # (domain, sheet-name/label regex)
    ('subjects', r'^(DM|人口学|受试者信息|筛选|知情|ENR|RAND|随机)'), ('subjects', r'^(DS|完成|结束|退出|EOS|EOT|研究总结)'),
    ('visits', r'^(SV|访视日期|访视)'),
    # findings before exposure so ECG/ECHO are not caught by ^EC; any non lab/vs/ecg findings domain becomes a generic 专项检查 group
    ('findings:ecg', r'^(EG|ECG|心电图|12导联)'),
    ('findings:img', r'^(IMG|MI|RAD|影像|超声|B超|彩超|ECHO|超声心动|CT|MRI|核磁|X线|胸片|内镜|胃镜|肠镜|PET)'),
    ('findings:pe', r'^(PE|体格检查|查体)'),
    ('findings:exam', r'^(OE|OP|眼科|肺功能|PFT|妇科|乳腺|骨密度|DXA|Holter|动态心电|EEG|脑电|肌电|听力|皮肤科)'),
    ('exposure', r'^(EC(?![GH])|EX|给药|研究药物|用药记录|服药|DA|药物发放)'),
    ('ae', r'^(AE|不良事件)'), ('mh', r'^(MH|病史|既往史|现病史)'), ('cm', r'^(CM|合并用药|既往用药|伴随用药)'), ('proc', r'^(PR|手术|操作|非药物治疗)'),
    ('findings:lab', r'^(LB|血常规|血生化|生化|尿常规|凝血|实验室|甲功|血脂|肝功|肾功|电解质|妊娠|HEMA|CHEM|URIN|COAG)'),
    ('findings:vs', r'^(VS|生命体征)'),
    ('efficacy', r'^(QS|EFF|RS|TU|TR|量表|评分|疗效|有效性|问卷|日记)'), ('pd', r'^(DV|PD|方案偏离|偏离)'), ('extq', r'(质疑|QUERY|Query|query|^CROQ|^DCF|^EDCQ)'),
    ('pk', r'^(PK|PC|药代|血药浓度|采样)'), ('ada', r'^(ADA|IS|免疫原性|抗药抗体)'),
]
FIELD_SYN = {  # normalized field → variable/label patterns (first match wins)
    'sid': [r'^(SUBJID|USUBJID|SUBJECT|受试者(编号|号|代码)?|筛选号|病例号)$'], 'site': [r'^(SITEID|SITENO|中心(编号|号)?)$'], 'center': [r'^(SITENAME|中心名称|研究中心)$'],
    'visit': [r'^(VISIT|VISITNAME|FOLDERNAME|访视(名称)?|访视阶段)$'], 'date': [r'(DAT|DTC|日期)$'], 'tpt': [r'(TPT|时间点)$'],
    'icf': [r'(ICFDAT|知情同意.*日期)'], 'eot_d': [r'(EOTDAT|DSSTDAT|治疗结束.*日期|退出.*日期)'], 'eot_why': [r'(EOTREAS|DSDECOD|DSTERM|退出原因|终止原因|未完成原因)'], 'eos_d': [r'(EOSDAT|研究结束.*日期)'], 'eos_done': [r'(EOSCOMP|是否完成)'], 'eos_why': [r'(EOSREAS|研究结束原因)'], 'age': [r'^(AGE|年龄)'], 'sex': [r'^(SEX|性别)'], 'rand': [r'(RANDNO|随机号)'], 'ht': [r'(HEIGHT|身高)'], 'wt': [r'^(WEIGHT|体重)'],
    'term': [r'(AETERM|MHTERM|CMTRT|PRTRT|DVTERM|名称$|术语|偏离描述|事件描述)'], 'start': [r'(STDAT|STDTC|开始日期|起始日期)'], 'end': [r'(ENDAT|ENDTC|结束日期|停止日期)'],
    'ongoing': [r'(ONGO|是否持续|仍在)'], 'grade': [r'(TOXGR|SEV|严重程度|分级|CTCAE)'], 'serious': [r'^(AESER|是否SAE|是否.*严重不良事件|严重不良事件)$', r'(AESER|是否SAE)'],
    'pt': [r'(AEDECOD|AEPT|首选术语|^PT(名称)?$)'], 'soc': [r'(AESOC|AEBODSYS|系统器官分类|^SOC)'], 'llt': [r'(AELLT|低位语|^LLT)'],
    'aware': [r'(AWARE|获知日期|知晓日期)'], 'rpt': [r'(RPTDAT|SAERPT|报告日期|上报日期)'], 'aesi': [r'(AESI|特别关注)'],
    'rel': [r'(AEREL|与研究药物.*关|相关性|因果)'], 'action': [r'(AEACN|采取.*措施|对研究药物.*措施)'], 'outcome': [r'(AEOUT|转归)'],
    'dose': [r'(DOSE$|DOSTXT|剂量$|单次剂量)'], 'freq': [r'(FRQ|FREQ|频次|频率)'], 'route': [r'(ROUTE|途径)'], 'indication': [r'(INDC|用药原因|适应症)'],
    'test': [r'^(LBTEST|VSTEST|EGTEST|QSTEST|检查项(目)?|项目名称|指标)$'], 'value': [r'(ORRES$|STRESN|结果$|测量值|检测值)'], 'unit': [r'(ORRESU|STRESU|单位)'],
    'lo': [r'(NRLO|下限)'], 'hi': [r'(NRHI|上限)'], 'clin': [r'(CLSIG|临床意义)'], 'link': [r'(病史/不良事件|关联|LINK)'], 'desc': [r'(异常描述|DESC)'],
    'cat': [r'(DVCAT|偏离(类别|分类))'], 'text': [r'(质疑内容|QUERYTEXT|TEXT)'], 'form': [r'^(FORM|表单|CRF页)'],
}
DOMAIN_FIELDS = {'subjects': ['sid', 'site', 'center', 'icf', 'age', 'sex', 'ht', 'wt', 'rand', 'eot_d', 'eot_why', 'eos_d', 'eos_done', 'eos_why'], 'visits': ['sid', 'visit', 'date'],
                 'exposure': ['sid', 'visit', 'start', 'end', 'dose'], 'ae': ['sid', 'term', 'pt', 'soc', 'llt', 'start', 'end', 'grade', 'serious', 'aesi', 'rel', 'action', 'outcome', 'aware', 'rpt'],
                 'mh': ['sid', 'term', 'start', 'end', 'ongoing'], 'cm': ['sid', 'term', 'start', 'end', 'ongoing', 'dose', 'freq', 'route', 'indication'],
                 'proc': ['sid', 'term', 'start', 'end'], 'findings': ['sid', 'visit', 'date', 'tpt', 'test', 'value', 'unit', 'lo', 'hi', 'clin', 'desc', 'link'],
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


def guess(names, field):
    for pat in FIELD_SYN.get(field, []):
        for i, (lab, var) in enumerate(names):
            if (var and re.search(pat, var)) or (lab and re.search(pat, lab)):
                return var or lab
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
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        inv.append(f'## {alias} · {Path(path).name}\n\n| 表 | 识别 | 表头行 | 行数 | 受试者列 | 布局 | 主要变量 |\n|---|---|---|---|---|---|---|')
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            lr, vr, ds = header_rows(rows)
            labels = [str(x).strip() if x is not None else '' for x in rows[lr - 1]]
            vars_ = [str(x).strip() if x is not None else '' for x in rows[vr - 1]] if vr else [''] * len(labels)
            names = list(zip(labels + [''] * (len(vars_) - len(labels)), vars_ + [''] * (len(labels) - len(vars_))))
            data = [r for r in rows[ds - 1:] if any(c not in (None, '') for c in r)]
            dom = next((d for d, rx in DOMAIN_RE if re.search(rx, ws.title) or re.search(rx, labels[0] if labels else '')), None)
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
        m = re.search(r'(筛选|Screen)', v) and 'SCR' or re.search(r'第\s*1\s*天|D1\b|Day\s*1\b', v) and 'D1' or re.search(r'计划外|Unsch|USV', v, re.I) and 'USV' or \
            re.search(r'提前|ET\b|退出', v) and 'ET' or re.search(r'安全随访|随访期|Follow', v, re.I) and 'FU' or re.search(r'治疗结束|EOT\b', v) and 'EOT' or (re.search(r'第\s*(\d+)\s*周', v) and 'W' + re.search(r'第\s*(\d+)\s*周', v).group(1)) or \
            (re.search(r'(?:V|访视)\s*(\d+)', v) and 'V' + re.search(r'(?:V|访视)\s*(\d+)', v).group(1)) or v
        vm[v] = m
        if m == v:
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
        dm = next((v for (al, sh), v in sid_sets.items() if re.search(DOMAIN_RE[0][1], sh)), None)
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
