#!/usr/bin/env python3
"""Generate a synthetic EDC listing workbook (row1 Chinese labels, row2 variable names, data from row3) for an
illustrative Phase II study, so the whole pipeline can be exercised end-to-end without real data.

python3 make_demo.py --out examples/demo   → DEMO_EDC_listing.xlsx (+ mapping.json / study.json already in that folder)
All subjects, sites and values are fictitious.
"""
import argparse
import datetime as dt
import random
from pathlib import Path

import openpyxl

R = random.Random(20260101)
SIGNAL = {'01002', '01003', '01004', '01005', '01006', '01007', '01008', '02002', '02003', '02004', '02005', '03001', '03002', '03003', '03004', '04001', '04002', '04003', '05001', '05002'}
SITES = [('01', '示例医院A'), ('02', '示例医院B'), ('03', '示例医院C'), ('04', '示例医院D'), ('05', '示例医院E')]
VIS = [('V1', '筛选期', -14), ('D1', '第1天', 0), ('W2', '第2周', 14), ('W4', '第4周', 28), ('W8', '第8周', 56), ('W12', '第12周', 84), ('FU', '安全随访', 112)]
LABS = [  # test, unit, lo, hi, mean, sd, sheet-group
    ('血红蛋白', 'g/L', 115, 150, 128, 9), ('白细胞计数', '10^9/L', 3.5, 9.5, 6.2, 1.3), ('血小板计数', '10^9/L', 125, 350, 230, 45),
    ('丙氨酸氨基转移酶', 'U/L', 7, 40, 20, 7), ('天门冬氨酸氨基转移酶', 'U/L', 13, 35, 21, 6), ('总胆红素', 'umol/L', 3.4, 20.5, 10, 3.5),
    ('肌酐', 'umol/L', 41, 81, 60, 9), ('钾', 'mmol/L', 3.5, 5.3, 4.2, 0.3), ('钠', 'mmol/L', 137, 147, 141, 2), ('甘油三酯', 'mmol/L', 0, 1.7, 1.2, 0.4),
    ('尿酸', 'umol/L', 155, 357, 280, 50)]


def d(x):
    return x.isoformat()


def sheet(wb, name, labels, vars_, rows):
    ws = wb.create_sheet(name)
    ws.append(labels)
    ws.append(vars_)
    for r in rows:
        ws.append(r)
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='examples/demo')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    DM, DS, SV, EC, AE, MH, CM, LB, VS, EG, EF, PD, CQ = ([] for _ in range(13))
    subjects = []
    for si, (site, name) in enumerate(SITES):
        for k in range(1, 9 if si < 4 else 4):
            sid = f'{site}{k:03d}'
            icf = dt.date(2026, 1, 5) + dt.timedelta(days=R.randint(0, 120))
            sf = R.random() < 0.12
            if sid in SIGNAL:
                sf = False
            elif sid in ('02008', '04008'):
                sf = True
            subjects.append((sid, site, name, icf, sf))
    for sid, site, name, icf, sf in subjects:
        age = R.randint(22, 62)
        if sid == '02003':
            age = 17  # eligibility signal
        ht, wt = R.randint(150, 182), R.randint(48, 90)
        DM.append([sid, site, name, d(icf), age, '女' if R.random() < .5 else '男', ht, wt, round(wt / (ht / 100) ** 2, 1), '汉族', '' if sf else f'R{sid}',
                   '' if sf else ('是' if R.random() < .3 else '否')])
        fd = icf + dt.timedelta(days=14)
        ncomp = 6 if R.random() > 0.12 else R.randint(2, 5)
        vis = VIS[:1] if sf else VIS[:ncomp + 1]
        if not sf and sid in ('01002', '03004'):
            vis = vis + [('USV', '计划外访视', 40)]
        dates = {}
        for v, lab, day in vis:
            jitter = 0 if v in ('V1', 'D1') else R.randint(-2, 2)
            if sid == '04002' and v == 'W4':
                jitter = 9  # window signal
            dd = fd + dt.timedelta(days=day + jitter) if v != 'V1' else icf + dt.timedelta(days=1)
            dates[v] = dd
            SV.append([sid, lab, d(dd)])
        if sf:
            DS.append([sid, '', '', '', '否', '筛选失败'])
            continue
        last = max(dates.values())
        ld = min(last, fd + dt.timedelta(days=84))
        early = ncomp < 6
        EC.append([sid, '第1天', d(fd), d(ld), '10 mg QD', ''])
        DS.append([sid, d(ld), '提前停药：受试者撤回' if early else '完成治疗', d(last), '否' if early else '是', '受试者撤回知情同意' if early else ''])
        # MH
        mh = []
        if R.random() < .35:
            mh.append(('高血压', '2019-03-01', '是'))
        if sid in ('01004', '03002'):
            mh.append(('贫血', '2024-05-01', '是'))
        if R.random() < .2:
            mh.append(('高甘油三酯血症', '2023-01-01', '是'))
        for i, (t, s, o) in enumerate(mh, 1):
            MH.append([sid, i, t, s, '', o])
        # AEs
        ae = []
        for _ in range(R.choice([0, 0, 1, 1, 2, 3])):
            t = R.choice(['头痛', '恶心', '腹泻', '乏力', '上呼吸道感染', '皮疹', '头晕'])
            s = fd + dt.timedelta(days=R.randint(1, 80))
            if s > ld:
                continue
            ae.append([t, d(s), d(s + dt.timedelta(days=R.randint(1, 10))), R.choice(['1级', '1级', '2级']), '否', '否', R.choice(['可能有关', '可能无关', '肯定无关']), '剂量不变', '痊愈', '否'])
        if sid == '01003':
            ae.append(['头痛', d(fd - dt.timedelta(days=3)), d(fd + dt.timedelta(days=2)), '1级', '否', '否', '可能有关', '剂量不变', '痊愈', '否'])
        if sid == '02002':
            ae.append(['丙氨酸氨基转移酶升高', d(fd + dt.timedelta(days=28)), '', '1级', '否', '否', '可能有关', '剂量不变', '未痊愈', '否'])
        if sid == '03001':
            ae.append(['心电图QT间期延长', d(fd + dt.timedelta(days=56)), d(fd + dt.timedelta(days=60)), '2级', '否', '否', '可能有关', '剂量不变', '痊愈', '否'])
        if sid == '01005':
            ae.append(['皮疹', d(fd + dt.timedelta(days=20)), d(fd + dt.timedelta(days=30)), '2级', '否', '否', '可能有关', '剂量不变', '痊愈', '否'])
        for i, x in enumerate(ae, 1):
            AE.append([sid, i] + x)
        # CM
        cms = []
        for i, (t, s, o) in enumerate(mh, 1):
            if t == '高血压':
                cms.append(['氨氯地平', s, '', '是', '5 mg', 'QD', '口服', f'MH+{i}+高血压'])
        for i, x in enumerate(ae, 1):
            if x[0] == '皮疹':
                cms.append(['氯雷他定', x[1], x[2], '否', '10 mg', 'QD', '口服', f'AE+{i}+皮疹'])
        if sid == '01006':
            cms.append(['克拉霉素', d(fd + dt.timedelta(days=30)), d(fd + dt.timedelta(days=37)), '否', '250 mg', 'BID', '口服', '肺部感染'])
        if sid == '05001':
            cms.append(['泼尼松', d(fd - dt.timedelta(days=20)), d(fd - dt.timedelta(days=10)), '否', '10 mg', 'QD', '口服', '关节痛'])
        for i, x in enumerate(cms, 1):
            CM.append([sid, i] + x)
        # labs
        for v, (dd) in dates.items():
            if v == 'W2':
                pass
            for test, unit, lo, hi, mu, sd in LABS:
                x = R.gauss(mu, sd)
                post = v not in ('V1',)
                clin, link, desc = '', '', ''
                if test == '血红蛋白' and sid in ('01004', '03002') and post and v in ('W8', 'W12'):
                    x = 92
                    clin, link = '异常有临床意义', 'MH+%d+贫血' % (len(mh))
                if test == '丙氨酸氨基转移酶' and sid == '02002' and v == 'W4':
                    x = 135
                    clin, link = '异常有临床意义', 'AE+%d+丙氨酸氨基转移酶升高' % len(ae)
                if test == '丙氨酸氨基转移酶' and sid == '04001' and v == 'W8':
                    x = 88
                    clin = '异常有临床意义'
                if test == '血小板计数' and sid == '01007' and v == 'W4':
                    x = 68
                    clin = '异常无临床意义'
                if test == '钾' and sid == '03003' and v == 'W12':
                    x = 2.9
                    clin = '异常有临床意义'
                if test == '甘油三酯' and sid in ('02004', '02005') and v == 'W8':
                    x = 2.4 if sid == '02004' else 2.45
                    clin = '异常有临床意义' if sid == '02004' else '异常无临床意义'
                x = round(max(x, lo * 0.75 if lo else 0.1), 1 if unit != 'mmol/L' else 2)
                if not clin:
                    clin = '正常' if lo <= x <= hi else '异常无临床意义'
                LB.append([sid, dict((a, b) for a, b, _ in VIS).get(v, '计划外访视'), d(dd), test, x, unit, lo, hi, clin, desc, link])
        # VS / ECG
        for v, dd in dates.items():
            for tpt in (['给药前', '给药后2h'] if v == 'D1' else ['']):
                sbp, dbp, hr = R.randint(105, 138), R.randint(65, 88), R.randint(60, 92)
                qt = R.randint(395, 445)
                if sid == '03001' and v == 'W8':
                    qt = 506
                if sid == '01008' and v == 'W4':
                    qt = 474
                if sid == '04003' and v == 'W12':
                    sbp = 168
                VS.append([sid, dict((a, b) for a, b, _ in VIS).get(v, '计划外访视'), d(dd), tpt, sbp, '正常' if sbp < 140 else '异常无临床意义', dbp, '正常', hr, '正常', wt + R.randint(-2, 2)])
                EG.append([sid, dict((a, b) for a, b, _ in VIS).get(v, '计划外访视'), d(dd), tpt, hr, qt, '正常' if qt < 450 else '异常有临床意义' if qt > 500 else '异常无临床意义'])
        # efficacy: symptom score 0-40 (lower better), PGI-C at W12
        b = R.randint(18, 32)
        for v, dd in dates.items():
            if v in ('D1', 'W4', 'W8', 'W12'):
                k = {'D1': 0, 'W4': .15, 'W8': .3, 'W12': .4}[v]
                sc = round(b * (1 - k) + R.gauss(0, 2.5))
                if sid == '05002' and v == 'W8':
                    sc = 88  # implausible
                EF.append([sid, dict((a, b2) for a, b2, _ in VIS)[v], d(dd), '症状评分', sc])
                if v == 'W12':
                    EF.append([sid, '第12周', d(dd), 'PGI-C', R.choice([1, 2, 2, 3, 3, 4, 5])])
        if sid == '01006':
            PD.append([sid, '合并用药', '治疗期使用强效CYP3A抑制剂克拉霉素', d(fd + dt.timedelta(days=31))])
        if sid == '04001':
            CQ.append(['实验室检查', 0, sid, '第8周', '请确认 ALT 88 U/L 判定为异常有临床意义，是否需要记录不良事件'])
    sheet(wb, 'DM', ['受试者编号', '中心编号', '中心名称', '知情同意日期', '年龄', '性别', '身高(cm)', '体重(kg)', 'BMI', '民族', '随机号', '分层因素'],
          ['SUBJID', 'SITEID', 'SITENAME', 'ICFDAT', 'AGE', 'SEX', 'HEIGHT', 'WEIGHT', 'BMI', 'ETHNIC', 'RANDNO', 'STRAT'], DM)
    sheet(wb, 'DS', ['受试者编号', '末次给药日期', '治疗结束原因', '研究结束日期', '是否完成研究', '提前退出原因'], ['SUBJID', 'EOTDAT', 'EOTREAS', 'EOSDAT', 'EOSCOMP', 'EOSREAS'], DS)
    sheet(wb, 'SV', ['受试者编号', '访视名称', '访视日期'], ['SUBJID', 'VISIT', 'SVDAT'], SV)
    sheet(wb, 'EC', ['受试者编号', '访视名称', '首次给药日期', '末次给药日期', '剂量', '暂停'], ['SUBJID', 'VISIT', 'ECSTDAT', 'ECENDAT', 'ECDOSE', 'ECPAUSE'], EC)
    sheet(wb, 'AE', ['受试者编号', 'AE编号', '不良事件名称', '开始日期', '结束日期', '严重程度', '是否SAE', '是否AESI', '与研究药物关系', '采取措施', '转归', '是否有合并用药'],
          ['SUBJID', 'AENO', 'AETERM', 'AESTDAT', 'AEENDAT', 'AETOXGR', 'AESER', 'AESI', 'AEREL', 'AEACN', 'AEOUT', 'AECM'], AE)
    sheet(wb, 'MH', ['受试者编号', '病史编号', '病史名称', '开始日期', '结束日期', '是否持续'], ['SUBJID', 'MHNO', 'MHTERM', 'MHSTDAT', 'MHENDAT', 'MHONGO'], MH)
    sheet(wb, 'CM', ['受试者编号', '用药编号', '药物名称', '开始日期', '结束日期', '是否持续', '剂量', '频次', '途径', '用药原因'],
          ['SUBJID', 'CMNO', 'CMTRT', 'CMSTDAT', 'CMENDAT', 'CMONGO', 'CMDOSE', 'CMFREQ', 'CMROUTE', 'CMINDC'], CM)
    sheet(wb, 'LB', ['受试者编号', '访视名称', '采样日期', '检查项', '结果', '单位', '参考范围下限', '参考范围上限', '临床意义评价', '异常描述', '病史/不良事件请选择'],
          ['SUBJID', 'VISIT', 'LBDAT', 'LBTEST', 'LBORRES', 'LBORRESU', 'LBORNRLO', 'LBORNRHI', 'LBCLSIG', 'LBDESC', 'LBLINK'], LB)
    sheet(wb, 'VS', ['受试者编号', '访视名称', '检查日期', '时间点', '收缩压', '收缩压临床意义', '舒张压', '舒张压临床意义', '脉搏', '脉搏临床意义', '体重'],
          ['SUBJID', 'VISIT', 'VSDAT', 'VSTPT', 'SYSBP', 'SYSCS', 'DIABP', 'DIACS', 'PULSE', 'PULSECS', 'WEIGHT'], VS)
    sheet(wb, 'EG', ['受试者编号', '访视名称', '检查日期', '时间点', '心率', 'QTcF', '心电图临床意义'], ['SUBJID', 'VISIT', 'EGDAT', 'EGTPT', 'EGHR', 'QTCF', 'EGCLSIG'], EG)
    sheet(wb, 'EFF', ['受试者编号', '访视名称', '评估日期', '量表', '得分'], ['SUBJID', 'VISIT', 'QSDAT', 'QSTEST', 'QSORRES'], EF)
    p = out / 'DEMO_EDC_listing.xlsx'
    wb.save(p)
    w2 = openpyxl.Workbook()
    w2.remove(w2.active)
    sheet(w2, 'PD', ['受试者编号', '偏离类别', '偏离描述', '发生日期'], ['SUBJID', 'DVCAT', 'DVTERM', 'DVDAT'], PD)
    sheet(w2, 'CROQ', ['表单', '行', '受试者编号', '访视', '质疑内容'], ['FORM', 'ROW', 'SUBJID', 'VISIT', 'TEXT'], CQ)
    w2.save(out / 'DEMO_PD_and_CRO_queries.xlsx')
    print('wrote', p, len(subjects), 'subjects')


if __name__ == '__main__':
    main()
