#!/usr/bin/env python3
"""mm4 通用能力回归（关联字段写法、同名列引用、CS 原因、入排判定值）。运行：python3 scripts/test_mm4.py"""
import re
import sys
from collections import defaultdict
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import parse_links, parse_typed_links  # noqa: E402


class LinkGrammar(unittest.TestCase):
    def test_dash_style_and_typed_columns(self):
        self.assertEqual(parse_links('MH-4-血脂异常-2026-05-18'), [['MH', '血脂异常', None, 4]])
        self.assertEqual(parse_typed_links('002>PR间期缩短>2026-04-28$003>ST段改变>2026-05-01', 'AE'),
                         [['AE', 'PR间期缩短', None, 2], ['AE', 'ST段改变', None, 3]])
        self.assertEqual(parse_typed_links('001>高血压>2023-04-UK', 'MH'), [['MH', '高血压', None, 1]])
        self.assertEqual(parse_typed_links('3', 'MH'), [['MH', '', None, 3]])

    def test_label_var_header_reference(self):
        from normalize_listing import col_index
        labels = ['受试者编号', '不良事件名称(AETERM)', '开始日期（AESTDAT）']
        self.assertEqual(col_index('AETERM', labels, [''] * 3), 1)
        self.assertEqual(col_index('不良事件名称', labels, [''] * 3), 1)
        self.assertEqual(col_index('AESTDAT', labels, [''] * 3), 2)

    def test_plus_style(self):
        self.assertEqual(parse_links('AE+1+头痛'), [['AE', '头痛', None, 1]])
        self.assertEqual(parse_links('MH+4+贫血；AE+2+皮疹'), [['MH', '贫血', None, 4], ['AE', '皮疹', None, 2]])

    def test_dropdown_style(self):
        self.assertEqual(parse_links('病史-3 - 缺铁性贫血 - 2020-01-01'), [['MH', '缺铁性贫血', None, 3]])
        self.assertEqual(parse_links('不良事件-2 - 转氨酶升高 - 2026-03-01'), [['AE', '转氨酶升高', None, 2]])

    def test_multi_space_separated(self):
        v = '病史-1 - 贫血 - 2019-uk-uk    不良事件-5 - 血红蛋白降低 - 2026-05-02'
        self.assertEqual(parse_links(v), [['MH', '贫血', None, 1], ['AE', '血红蛋白降低', None, 5]])

    def test_no_link(self):
        self.assertEqual(parse_links('研究疾病'), [])
        self.assertEqual(parse_links(None), [])

    def test_custom_regex(self):
        rx = r'(?P<type>AE|MH)(?P<no>\d+):(?P<term>[^|]+)'
        self.assertEqual(parse_links('AE3:头晕|MH1:高血压', rx), [['AE', '头晕', None, 3], ['MH', '高血压', None, 1]])

    def test_paren_style(self):
        """SAR 实测写法（SH/VS/USV/EG/PE/NE/PT/MO/CM/PR 共 426+ 非空关联单元格全部此格式）：「AE (5) 术语」。修前返回 []（红）。"""
        self.assertEqual(parse_links('AE (5) PR间期缩短'), [['AE', 'PR间期缩短', None, 5]])
        self.assertEqual(parse_links('MH (3) 阻生牙'), [['MH', '阻生牙', None, 3]])
        self.assertEqual(parse_typed_links('MH (3) 阻生牙', 'MH'), [['MH', '阻生牙', None, 3]])
        self.assertEqual(parse_links('MH (4) 贫血；AE (2) 皮疹'),
                         [['MH', '贫血', None, 4], ['AE', '皮疹', None, 2]])
        self.assertEqual(parse_links('AE（5）湿疹样皮炎'), [['AE', '湿疹样皮炎', None, 5]])   # 全角括号
        self.assertEqual(parse_links('AE (5)'), [['AE', '', None, 5]])                        # 无术语

    def test_paren_style_keeps_term_parens(self):
        """编号后的右括号只剥开头：术语自带括号（头痛(重度)）不得被吃掉。"""
        self.assertEqual(parse_links('AE (5) 头痛(重度)'), [['AE', '头痛(重度)', None, 5]])


class DomainGuards(unittest.TestCase):
    """SAR 深审 F2/F3：RAN 表名（无 D）此前不命中 ^RAND → 随机信息整表丢失；
    DAH（药物滥用史）/EX1–EX7（背景治疗日志）此前全被吞进 exposure → 安全集虚增、首剂日期可取自背景治疗。"""
    def test_ran_sheet_is_subjects(self):
        import re
        from inspect_listing import DOMAIN_RE
        hit = [d for d, rx in DOMAIN_RE if re.search(rx, 'RAN')]
        self.assertEqual(hit[0], 'subjects')

    def test_subject_rand_status_fields(self):
        from inspect_listing import DOMAIN_FIELDS, FIELD_SYN, SYS_META, guess
        self.assertIn('rand_d', DOMAIN_FIELDS['subjects'])
        self.assertIn('status', DOMAIN_FIELDS['subjects'])
        self.assertEqual(SYS_META.get('受试者状态'), 'status')
        names = [('受试者编号', 'SUBJID'), ('是否筛选成功并随机', 'RANYN'), ('随机日期', 'RANDAT'),
                 ('随机号', 'RANNUM'), ('受试者状态', '受试者状态')]
        self.assertEqual(guess(names, 'rand_d'), 'RANDAT')
        self.assertEqual(guess(names, 'rand'), 'RANNUM')
        self.assertEqual(guess(names, 'status'), '受试者状态')      # pd_rules 口径：status==「筛选失败」
        self.assertIsNone(guess(names, 'term'))                     # 系统列仍然不当业务字段
        self.assertEqual(guess([('是否筛选成功并随机', 'RANYN')], 'status'), 'RANYN')

    def test_exposure_guards(self):
        from inspect_listing import refine_exposure
        self.assertEqual(refine_exposure('exposure', 'DAH', '是否有药物滥用史(DAHYN) 药物名称(DAHTERM) 开始日期(DAHSTDAT)'), 'cm')
        self.assertEqual(refine_exposure('exposure', 'EX1', '给药时间点(EXTPT1) 是否进行背景治疗(EXYN1) 给药日期(EXDAT1) 给药剂量(EXDOSE1) 其他剂量，请说明(EXDOSEO1)'), 'cm')
        self.assertEqual(refine_exposure('exposure', 'EX', '是否给药(EXYN) 理论给药体积(EXPDOSE) 实际给药体积(EXDOSE) 给药日期(EXDAT)'), 'exposure')
        self.assertEqual(refine_exposure('exposure', 'EC', '研究药物名称(ECTRT) 给药开始日期(ECSTDAT)'), 'exposure')
        self.assertEqual(refine_exposure('cm', 'CM', '药物名称(CMTRT)'), 'cm')   # 非 exposure 域不动


class WorseningRule(unittest.TestCase):
    """用户 2026-10-27：0 级 → 1 级不单独算加重，须同时超出范围且同向较基线 ≥T_base。"""
    def test_grade_up(self):
        from ext_rules import grade_up
        self.assertFalse(grade_up(0, 1))
        self.assertTrue(grade_up(0, 2))
        self.assertTrue(grade_up(1, 2))
        self.assertFalse(grade_up(2, 2))
        self.assertFalse(grade_up(1, 2, 98, 100))          # 跨界值但只变 2%：测量波动
        self.assertTrue(grade_up(1, 2, 85, 100))

    def test_worse_vs_base(self):
        from mm_build import worse_vs_base
        b = {'grade': 0, 'value': 5.11}
        small = {'grade': 1, 'value': 5.54, 'hi': 5.2, 'lo': 0, 'oor': True}           # 0→1 级、+8%：不算
        self.assertIsNone(worse_vs_base(small, b, 0.3))
        big = {'grade': 1, 'value': 6.8, 'hi': 5.2, 'lo': 0, 'oor': True}              # 0→1 级、+33%：算
        self.assertIn('较基线升高', worse_vs_base(big, b, 0.3))
        self.assertIn('等级', worse_vs_base({'grade': 2, 'value': 5.6, 'hi': 5.2, 'oor': True}, {'grade': 1, 'value': 5.0}, 0.3))
        # 跨分级界值但只变 1.8%（5.5→5.6）：测量波动，不算加重（V6 第二轮医学审阅）
        self.assertIsNone(worse_vs_base({'grade': 2, 'value': 5.6, 'hi': 5.2, 'oor': True}, {'grade': 1, 'value': 5.5}, 0.3))
        self.assertIsNone(worse_vs_base({'grade': 0, 'value': 0.9, 'hi': 0.52, 'oor': True}, {'grade': 0, 'value': 0.8}, 0.3))  # 基线已高、+12%


class DiseaseRelatedCS(unittest.TestCase):
    """用户 2026-10-27：归因研究疾病的 CS，只有较基线明显加重且同期没有「研究疾病加重」AE 才是风险。"""
    def test_disease_ae_window_and_terms(self):
        from types import SimpleNamespace
        from ext_rules import disease_ae, disease_kw
        C = SimpleNamespace(A={'indicationBackground': [['EOS', '嗜酸性粒细胞升高：特应性皮炎常见表现']]},
                            S={'study': {'design': {'facts': [['适应症', '中重度特应性皮炎']]}}},
                            ae_by={'S1': [{'t': '特应性皮炎加重', 's': '2026-05-20'}, {'t': '头痛', 's': '2026-05-18'},
                                          {'t': '特应性皮炎', 's': '2026-07-30'}]})
        dz = disease_kw(C)
        self.assertTrue(dz.search('特应性皮炎加重') and dz.search('嗜酸性粒细胞增多'))
        hit = disease_ae(C, 'S1', '嗜酸性粒细胞', [{'date': '2026-05-25'}])
        self.assertEqual([a['t'] for a in hit], ['特应性皮炎加重'])                 # 头痛不算；AE 持续期间覆盖异常日期才算
        self.assertEqual(disease_ae(C, 'S1', '嗜酸性粒细胞', [{'date': '2026-05-15'}]), [])   # 异常早于 AE 起始：不算（不用 ±N 天窗口）
        C.ae_by['S2'] = [{'t': '白细胞减少', 's': '2026-05-10'}, {'t': '嗜酸性粒细胞减少', 's': '2026-05-10'}, {'t': '嗜酸性粒细胞增多', 's': '2026-05-12', 'e': '2026-06-01'}]
        C.metric = {'EOS%': {'label': '嗜酸性粒细胞百分比'}}
        pts = [{'date': '2026-05-15', 'value': 16.5, 'hi': 8}]
        hit = disease_ae(C, 'S2', 'EOS%', pts)
        self.assertEqual([a['t'] for a in hit], ['嗜酸性粒细胞增多'])               # 方向相反、其他细胞类型都不算
        from ext_rules import onset_note
        self.assertIn('首次异常检验日期 2026-05-15', onset_note(C, 'EOS%', hit[0], pts))   # 以检验异常为表现的 AE，起始应为首次异常日期

    def test_attribution_and_stated_worsening_in_remarks(self):
        from types import SimpleNamespace
        from ext_rules import disease_attr, stated_worse, ae_covers
        C = SimpleNamespace(A={'diseaseTerms': ['AD']}, S={'study': {'design': {'facts': [['适应症', '中度至重度特应性皮炎患者']]}}})
        self.assertTrue(disease_attr(C, {'desc': 'CS，与AD相关'}))
        self.assertTrue(disease_attr(C, {'desc': '与研究疾病有关'}))
        self.assertTrue(disease_attr(C, {'reason': 'disease'}))
        self.assertFalse(disease_attr(C, {'desc': '急性上呼吸道感染相关'}))
        self.assertFalse(disease_attr(C, {'desc': 'ADHD'}))
        # V6（E2E 第 4 轮 SAR）：适应症带病程限定词，备注写核心病名 / 英文缩写在全称之后
        C2 = SimpleNamespace(A={'diseaseTerms': ['SAR']}, S={'study': {'design': {'facts': [['适应症', '季节性过敏性鼻炎（Seasonal Allergic Rhinitis，SAR）患者']]}}})
        self.assertTrue(disease_attr(C2, {'desc': '双侧鼻腔黏膜苍白水肿（CS,与过敏性鼻炎相关）'}))
        self.assertTrue(disease_attr(C2, {'desc': '眼部发红，流泪CS，与SAR相关'}))
        self.assertFalse(disease_attr(C2, {'desc': '急性鼻窦炎相关'}))
        C3 = SimpleNamespace(A={'indication': '慢性荨麻疹'}, S={})              # 设计要点缺失时用 analysis.indication
        self.assertTrue(disease_attr(C3, {'desc': '与荨麻疹相关'}))
        self.assertTrue(stated_worse({'desc': 'AD加重相关'}))
        self.assertTrue(stated_worse({'reason_raw': '与研究疾病加重有关'}))
        self.assertIsNone(stated_worse({'desc': '皮损未见加重'}))
        self.assertTrue(ae_covers({'s': '2026-07-uk', 'e': ''}, '2026-07-21'))
        self.assertFalse(ae_covers({'s': '2026-05-01', 'e': '2026-05-10'}, '2026-05-21'))


class ClinConsistency(unittest.TestCase):
    """用户 2026-10-27：同一受试者相同/相近结果一次判 NCS、一次判 CS → 风险（query），不作 PD。"""
    def test_judgment_only_follows_directional_rule(self):
        """mm5：只有「更差（或相等）者判 NCS、更轻者判 CS」才属改判（一致性 query 覆盖）；CS 更差时不降级，仍走 CS 未关联。"""
        from types import SimpleNamespace
        from ext_rules import judgment_only
        C = SimpleNamespace(A={})
        b = {'value': 320, 'hi': 250, 'lo': 120, 'clin': 2, 'post': True, 'unit': 'U/L', 'base': {'value': 315, 'grade': 0}}
        worse_ncs = {'value': 330, 'hi': 250, 'lo': 120, 'clin': 1, 'post': True, 'unit': 'U/L'}
        lighter_ncs = {'value': 319, 'hi': 250, 'lo': 120, 'clin': 1, 'post': True, 'unit': 'U/L'}
        self.assertTrue(judgment_only(C, b, [worse_ncs, b], 0.3))
        self.assertTrue(judgment_only(C, b, [dict(worse_ncs, value=320), b], 0.3))       # 数值相等异判
        self.assertFalse(judgment_only(C, b, [lighter_ncs, b], 0.3))                     # CS 更差：不是改判
        self.assertFalse(judgment_only(C, b, [dict(worse_ncs, post=False), b], 0.3))     # 不同给药阶段不可比
        self.assertFalse(judgment_only(C, dict(b, base={'value': 100, 'grade': 0}), [worse_ncs, b], 0.3))   # 较基线加重


class Batch6(unittest.TestCase):
    """用户 2026-10-28：知情前可沿用结果的同义词、EDC 目录页表单名、表单无临床意义字段。"""
    def test_pre_icf_synonyms(self):
        from pd_rules import _pre_icf_rx
        rx = _pre_icf_rx(r'结核|QuantiFERON\-TB|T\-SPOT\.TB')
        self.assertTrue(rx.search('LBTUB|γ-干扰素释放试验|LBTUB'))
        self.assertFalse(_pre_icf_rx('胸部CT').search('糖化血红蛋白'))

    def test_form_names_from_toc(self):
        import openpyxl
        from normalize_listing import Book, form_names
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'edc.xlsx'
            wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'TOC'
            ws.append(['Sheet名称（表单编号）', '表单名称']); ws.append(['LBCH', '血生化']); ws.append(['OTH', '其他检查']); ws.append(['XX', '不存在的表'])
            wb.create_sheet('LBCH'); wb.create_sheet('OTH'); wb.save(p)
            self.assertEqual(form_names(Book(str(p))), {'LBCH': '血生化', 'OTH': '其他检查'})


class ReviewFindings(unittest.TestCase):
    """第六批代码审查发现：加重判断的边界、备注否定、IB 匹配范围。"""
    def test_worse_vs_base_edges(self):
        from ext_rules import worse_vs_base, qual_worse
        self.assertIsNone(worse_vs_base({'grade': 2, 'value': 5}, None, 0.3))                    # 基线缺失不虚构「0→2 级」
        self.assertIn('基线为 0', worse_vs_base({'value': 199.68, 'hi': 0.05}, {'value': 0.0, 'grade': 0}, 0.3))
        sbp = {'value': 175, 'test': '收缩压', 'mid': 'vs:收缩压'}
        w = worse_vs_base(sbp, {'value': 129, 'grade': 0}, 0.3)
        self.assertTrue(w is None or '升高' in w)                                             # 有默认上限时按上限比较（无上限时不报错）
        self.assertIn('阴性→2+', qual_worse({'raw': '2+'}, {'raw': '阴性'}))

    def test_disease_attr_negation_and_stated_worse(self):
        from types import SimpleNamespace
        from ext_rules import disease_attr, stated_worse
        C = SimpleNamespace(A={'diseaseTerms': ['AD']}, S={'study': {'design': {'facts': [['适应症', '中度至重度特应性皮炎患者']]}}})
        for s in ('与AD无关', '与研究疾病无关', '排除AD', '考虑与AD无关，上感所致', 'AD治疗药物相关'):
            self.assertFalse(disease_attr(C, {'desc': s}), s)
        self.assertTrue(disease_attr(C, {'desc': '与AD相关'}))
        self.assertTrue(stated_worse({'desc': '皮疹控制不佳加重'}))
        self.assertIsNone(stated_worse({'desc': '不考虑AD加重'}))

    def test_ib_match_serious_and_direction(self):
        from types import SimpleNamespace
        from mm_build import ib_match
        C = SimpleNamespace(A={'expectedAE': [{'term': '严重感染', 'label': 'IB重要潜在风险', 're': '', 'pt': '感染', 'soc': '感染及侵染类疾病', 'labs': []},
                                              {'term': '中性粒细胞计数减少', 'label': '类效应（方案列明）', 're': '', 'pt': '', 'soc': '', 'labs': []}]})
        self.assertEqual(ib_match(C, {'t': '上呼吸道感染', 'pt': '上呼吸道感染', 'soc': '感染及侵染类疾病', 'sae': False, 'g': '1级'}),
                         [])                                                     # 非严重感染不标（用户 2026-10-28）
        self.assertEqual(ib_match(C, {'t': '严重感染', 'pt': '感染', 'soc': '感染及侵染类疾病', 'sae': True, 'g': '3级'}), ['IB重要潜在风险·严重感染'])
        self.assertEqual(ib_match(C, {'t': '中性粒细胞计数升高', 'pt': '', 'soc': '各类检查', 'sae': False, 'g': '1级'}), [])
        self.assertEqual(ib_match(C, {'t': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'sae': False, 'g': '3级'}), ['IB重要潜在风险·严重感染'])   # V6 事件族直接命中


class QualLevel(unittest.TestCase):
    def test_plus_minus_spellings_are_weak(self):
        from ext_rules import qual_level
        for s in ('±', '+-', '+/-', '10（+-）', '+-（0.15）', '弱阳性', '微量'):
            self.assertEqual(qual_level(s), 1, s)
        for s in ('+', '2+', '25（1+）', '500+++', '阳性'):
            self.assertEqual(qual_level(s), 2, s)
        self.assertEqual(qual_level('阴性'), 0)


import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _load_kz(html):
    t = (Path(html) / 'data' / 'core.js').read_text(encoding='utf-8')
    return json.loads(t[t.index('=') + 1:].rstrip().rstrip(';'))


class DemoBuild(unittest.TestCase):
    """端到端：演示数据（全部虚构）植入的执行层面/科学层面 PD 用例各检出一次，契约校验 0 错误。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='mm4demo_'))
        ex = cls.tmp / 'ex'
        py = sys.executable
        subprocess.run([py, str(ROOT / 'scripts/make_demo.py'), '--out', str(ex)], check=True, capture_output=True)
        for f in (ROOT / 'examples/demo').glob('*.json'):
            shutil.copy(f, ex / f.name)
        subprocess.run([py, str(ROOT / 'scripts/normalize_listing.py'), str(ex / 'mapping.json'), '--out', str(cls.tmp / 'norm')], check=True, capture_output=True)
        subprocess.run([py, str(ROOT / 'scripts/build_site.py'), '--study', str(ex / 'study.json'), '--norm', str(cls.tmp / 'norm'),
                        '--out', str(cls.tmp / 'out'), '--no-xlsx'], check=True, capture_output=True)
        cls.v = subprocess.run([py, str(ROOT / 'scripts/validate_contract.py'), str(cls.tmp / 'out/HTML'), '--source-check'], capture_output=True, text=True)
        cls.KZ = _load_kz(cls.tmp / 'out/HTML')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_contract(self):
        self.assertEqual(self.v.returncode, 0, self.v.stdout[-800:])

    def test_planted_pd_cases(self):
        from collections import Counter
        pot = self.KZ['pd']['potential']
        by = Counter((p['rule'], p['sid']) for p in pot)
        for rule, sid in [('ICF-01', '02006'), ('ICF-02', '01005'), ('IP-02', '03005'), ('IP-03', '02007'), ('IP-04', '04004'),
                          ('SAMP-01', '01001'), ('SAMP-02', '03007'), ('VIS-02', '03006'), ('ASMT-01', '01007'), ('ASMT-03', '05002'),
                          ('CM-02', '04005'), ('WD-01', '03001'), ('ELIG-01', '02003'), ('ELIG-02', '05001')]:
            self.assertEqual(by[(rule, sid)], 1, f'{rule} {sid}')
        # 未植入的执行层面规则不应在其他受试者上命中（噪音）
        for rule in ('ICF-01', 'ICF-02', 'IP-02', 'IP-03', 'IP-04', 'SAMP-01', 'SAMP-02', 'VIS-02', 'ASMT-01', 'ASMT-03', 'CM-02', 'WD-01'):
            self.assertEqual(sum(1 for p in pot if p['rule'] == rule), 1, rule)

    def test_possible_ae_pd_listed_aside(self):
        # 用户 2026-11-12：「可能需记录 AE」（SAFE-01/03）单列，不进潜在 PD 合计
        pd = self.KZ['pd']
        self.assertFalse([p for p in pd['potential'] if p['rule'] in ('SAFE-01', 'SAFE-03')])
        self.assertTrue(all(p['rule'] in ('SAFE-01', 'SAFE-03') and p['id'].startswith('S') for p in pd.get('aside', [])))

    def test_unscheduled_visits_flagged_for_aggregate_views(self):
        # 用户 2026-11-11：中心/全试验汇总不展示计划外访视——配置写回识别结果，前端 K.isAgg 同口径；未规范的写法按名称识别
        vis = self.KZ['cfg']['visits']
        self.assertIn('USV', vis['unsched'])
        self.assertIn('ET', vis['early'])
        import mm_build
        for v in ('计划外访视1', '非计划访视', 'UNS2', 'USV'):
            self.assertTrue(mm_build._UNS_ANY.search(v), v)
        for v in ('V3', 'W12', 'SCR', '计划访视'):
            self.assertFalse(mm_build._UNS_ANY.search(v), v)
        self.assertTrue(mm_build._ET_ANY.search('提前终止访视'))

    def test_viral_reactivation_hbsag_seroreversion(self):
        # D001 测试第四轮（2026-11-11）：给药后乙肝表面抗原阴转阳 → 高优先级「乙肝病毒再激活核查」；DNA「<30」两次都未检出不报
        import mm_build
        from types import SimpleNamespace as NS
        def r(v, raw, post, d, vis, t='乙肝表面抗原'):
            return {'test': t, 'value': v, 'raw': raw, 'hi': 0.08 if t == '乙肝表面抗原' else 30, 'unit': 'IU/ml', 'post': post,
                    'date': d, 'visit': vis, 'sheet': 'LB', 'row': 1, 'wb': ''}
        C = NS(F={('S1', 'lab:HBsAg'): [r(0.0, '0.00', False, '2026-06-26', 'SCR'), r(199.68, '199.68', True, '2026-08-24', 'USV')],
                  ('S1', 'lab:DNA'): [r(None, '<30', False, '2026-06-26', 'SCR', 'HBV-DNA'), r(None, '<30.00', True, '2026-08-26', 'USV', 'HBV-DNA')],
                  ('S2', 'lab:HBsAg'): [r(0.0, '0.00', False, '2026-06-26', 'SCR'), r(0.01, '0.01', True, '2026-08-24', 'W8')]},
               pop={'S1', 'S2'}, subj={'S1': {'site': '01'}, 'S2': {'site': '01'}}, others=[], vi=lambda v: 0,
               mh_by={'S1': [{'t': '乙型肝炎'}]}, sheet_meta={}, src={})
        mm_build.viral_reactivation(C)
        self.assertEqual([(o['sid'], o['cat'], o['pr']) for o in C.others], [('S1', '乙肝病毒再激活核查', 4)])
        self.assertIn('由给药前阴性', C.others[0]['sum'])
        self.assertIn('乙型肝炎', C.others[0]['sum'])

    def test_event_driven_visit_not_aggregated(self):
        # 用户 2026-11-13（RUX EOT 6 人、D68–D161 夹在 W12/W16 之间）：事件触发型访视并入提前退出类，不进汇总
        import mm_build
        from types import SimpleNamespace as NS
        subj = {f'S{i}': {'fd': '2026-01-01'} for i in range(20)}
        vis = [{'sid': f'S{i}', 'visit': v, 'date': d} for i in range(20) for v, d in (('W4', '2026-01-29'), ('W12', '2026-03-26'))]
        vis += [{'sid': 'S1', 'visit': 'EOT', 'date': '2026-03-10'}, {'sid': 'S2', 'visit': 'EOT', 'date': '2026-05-20'}]
        vis += [{'sid': f'S{i}', 'visit': 'EOS', 'date': '2026-06-01'} for i in range(20)]       # 人人都做的研究结束访视不受影响
        C = NS(A={'visitWindows': {'W4': [29, 3, 3], 'W12': [85, 3, 3]}}, cfg={'visits': {}}, pop=set(subj), subj=subj,
               visits=vis, findings=[], UNS={'USV'}, ET={'ET'}, VIS=['W4', 'EOT', 'W12', 'EOS'])
        mm_build.event_visits(C)
        self.assertIn('EOT', C.ET)
        self.assertNotIn('EOS', C.ET)
        self.assertEqual(C.VIS[-1], 'EOT')

    def test_odd_visit_target_flagged_not_changed(self):
        # 用户 2026-11-12：D001 方案 W12 写 D84，其余周访视为周数×7+1 → 按原文判定、给出规律目标日供提示
        import monitor_v5
        W = {'W2': [15, 3, 3], 'W4': [29, 3, 3], 'W8': [57, 3, 3], 'W12': [84, 3, 3], 'W16': [113, 3, 3]}
        self.assertEqual(monitor_v5.odd_visit_targets(W), {'W12': (84, 85)})
        self.assertEqual(monitor_v5.odd_visit_targets({'W2': [14, 3, 3], 'W4': [28, 3, 3], 'W8': [56, 3, 3]}), {})   # 统一按周数×7 的方案不提示

    def test_d1_falls_back_to_first_dose_visit(self):
        # D002/SAR：方案首剂访视代码（V4/V2）只在日记表出现，访视/检验/给药表写 D1 → 取给药记录首剂访视
        import mm_build
        from types import SimpleNamespace as NS
        C = NS(visits=[{'sid': 'a', 'visit': 'SCR'}, {'sid': 'a', 'visit': 'D1'}], findings=[{'sid': 'a', 'visit': 'W2'}],
               exposure=[{'sid': 'a', 'visit': 'W2', 'start': '2026-02-01'}, {'sid': 'a', 'visit': 'D1', 'start': '2026-01-01'},
                         {'sid': 'b', 'visit': 'D1', 'start': '2026-01-03'}])
        v = {'d1': 'V4'}
        mm_build._fix_d1(C, v)
        self.assertEqual(v['d1'], 'D1')
        v = {'d1': 'SCR'}                                  # 配置代码在主表里存在 → 不动
        mm_build._fix_d1(C, v)
        self.assertEqual(v['d1'], 'SCR')

    def test_confirmed_matching(self):
        conf = {c['sid']: c for c in self.KZ['pd']['confirmed']}
        self.assertEqual(conf['02007']['grade'], '重要')
        self.assertIn('IP-03', conf['02007']['matched'])
        self.assertIn('VIS-01', conf['04002']['matched'])
        self.assertEqual(conf['02001']['matched'], [])          # 现场核查类偏离：数据规则不覆盖

    def test_eligibility_one_signal_per_subject_criterion(self):
        el = [o for o in self.KZ['others'] if o['cat'] == '入排标准核对']
        keys = [(o['sid'], o['qkey']) for o in el]
        self.assertEqual(len(keys), len(set(keys)))

    def test_pages_and_nav(self):
        html = self.tmp / 'out/HTML'
        self.assertTrue((html / 'deviations.html').is_file())
        kz = (html / 'assets/kz.js').read_text(encoding='utf-8')
        self.assertIn("['deviations.html','方案偏离']", kz)
        self.assertNotIn("methods.html", kz)                         # V5：审阅要点与方法页取消
        self.assertFalse((html / 'methods.html').exists())
        self.assertTrue((html / 'center.html').is_file())
        for f in html.glob('*.html'):
            self.assertIn('assets/kz5.js', f.read_text(encoding='utf-8'), f.name)
        self.assertTrue(any(t.get('k') == 'pd' for t in self.KZ['review']))
        self.assertTrue(self.KZ['study'].get('calibers'))

    def test_drilldown_fields_in_subject_files(self):
        """用户 2026-10-30 裁定：参与者资料页 CS 项点开必须有链接信息——demo 受试者文件行 17 位，
        且三种形态可追溯：研究疾病归因（02004 甘油三酯）、AE 关联（02002 ALT）、CS 未关联（04001 ALT）。"""
        def sub(sid):
            raw = (self.tmp / 'out/HTML/data/s' / f'{sid}.js').read_text(encoding='utf-8')
            return json.loads(raw[len('KZ_SUB('):-2])
        r8 = next(r for r in sub('02004')['labs']['甘油三酯'] if r[1] == 'W8')
        self.assertEqual(len(r8), 20)                     # mm5：再扩 [17] 分级、[18] 较基线%、[19] 疑似录入错误
        self.assertEqual(r8[14], 'disease')
        r = next(r for r in sub('02002')['labs']['丙氨酸氨基转移酶'] if r[1] == 'W4')
        self.assertEqual(r[14], 'AE')
        self.assertIn('AE 丙氨酸氨基转移酶升高·', r[16])
        self.assertEqual(r[15], '与该不良事件有关，同一异常已按关联字段记录')
        r = next(r for r in sub('04001')['labs']['丙氨酸氨基转移酶'] if r[1] == 'W8')
        self.assertEqual(r[7], 2)
        self.assertEqual(r[14], '')                      # CS 未关联：前端显示「未关联」灰字
        ps = (self.tmp / 'out/HTML/assets/p-subjects.js').read_text(encoding='utf-8')
        self.assertIn('K.judgeCell(r,id)', ps)           # 钻取表已接「判定与关联」列

    def test_wording_no_internal_codes(self):
        """K22：审阅要点/核查方法/判读背景不露内部编号与英文域名（入排标准编号、PD listing、CM 页、VS/ECG）。"""
        import re
        blob = json.dumps(self.KZ['methods'] + self.KZ['review'], ensure_ascii=False)
        for bad in ('PD listing', 'CM 页', 'VS/ECG', 'CM / 措施', 'listing 缺字段', ' vs '):
            self.assertNotIn(bad, blob, bad)
        el = [o for o in self.KZ['others'] if o['cat'] == '入排标准核对']
        self.assertTrue(el, '演示数据应含入排标准核对信号')
        for o in el:
            for c in o['ctx']:
                self.assertFalse(re.match(r'^IE-[IE]\d+$', c), f'判读背景不应露内部编号：{c}')
                self.assertNotIn('PD listing', c, c)
        for g in self.KZ['labrows']:
            for c in g['ctx']:
                self.assertNotRegex(c, r'关联对象不存在：(AE|MH)\+', c)
        # 专项信号正文（参与者抽屉的信号框）：合并用药写「合并用药「药名」」，不写 EDC 域名 CM
        cm_sums = [o['sum'] for o in self.KZ['others'] if 'CM「' in (o.get('sum') or '')]
        self.assertEqual(cm_sums, [], cm_sums)
        self.assertTrue(any('合并用药“' in (o.get('sum') or '') for o in self.KZ['others']), '演示数据应含合并用药类信号（输出端已统一中文引号）')
        # 判定一致性（同中心/同受试者，mm4 方向性口径）：对照句不写英文「vs」
        self.assertTrue(self.KZ.get('cons'), '演示数据应含判定一致性对照')
        for c in self.KZ['cons']:
            self.assertNotIn(' vs ', c['diff'] + c['why'], c['diff'])
        # 方案偏离页「检查规则与覆盖」的未执行原因、「只能经源文件核查」清单：写「数据表」，不写 listing
        pd_blob = json.dumps(self.KZ['pd']['rules'] + self.KZ['pd']['notDetectable'], ensure_ascii=False)
        self.assertNotIn('listing', pd_blob, '规则未执行原因/不可判定清单残留 listing')


class Wording(unittest.TestCase):
    def test_elig_label(self):
        from mm_build import _elig_label
        self.assertEqual(_elig_label('IE-I4'), '入选标准 4')
        self.assertEqual(_elig_label('IE-E15'), '排除标准 15')
        self.assertEqual(_elig_label('排除标准 3'), '排除标准 3')
        self.assertEqual(_elig_label(''), '')

    def test_templates_no_internal_words(self):
        """K22：页面模板里的固定文案（不经数据面）——参与者页标签/矩阵分组、审阅要点副标题、方案偏离页说明。"""
        A = ROOT / 'templates/site/assets'
        for f, bads in {'p-subjects.js': ("'ECG'", '生命体征/ECG'),
                        'p-deviations.js': ('listing 不含所需信息',), 'p-timeline.js': ('ECG/VS',), 'p-index.js': ('listing 首列',)}.items():
            t = (A / f).read_text(encoding='utf-8')
            for bad in bads:
                self.assertNotIn(bad, t, f'{f} 残留「{bad}」')


class M19MissingDate(unittest.TestCase):
    """K95：M19 AE/给药核对里缺失日期渲染为「无日期」，不得出现 None 占位
    （validate_contract 会拦「unresolved placeholder/None in text」，实证 D001 Q136「W2（None）」）。"""

    def test_exposure_without_start_date(self):
        from types import SimpleNamespace
        from ext_rules import m19_ae_ex
        C = SimpleNamespace(A={}, pop={'S1'}, subj={'S1': {'site': '01'}}, src={'sheets': {}}, others=[],
                            exposure=[{'sid': 'S1', 'visit': 'W2', 'start': None, 'pause': '因不良事件暂停给药',
                                       'sheet': '给药', 'row': 3}],
                            ae_by={'S1': []})
        m19_ae_ex(C)
        self.assertEqual(len(C.others), 1)
        self.assertIn('无日期', C.others[0]['sum'])
        self.assertNotIn('None', C.others[0]['sum'])

    def test_ae_without_start_date(self):
        from types import SimpleNamespace
        from ext_rules import m19_ae_ex
        C = SimpleNamespace(A={}, pop={'S1'}, subj={'S1': {'site': '01'}}, src={'sheets': {}}, others=[],
                            exposure=[],
                            ae_by={'S1': [{'t': '皮疹', 's': None, 'act': '暂停用药', 'n': 1, 'sh': 'AE', 'row': 2}]})
        m19_ae_ex(C)
        self.assertEqual(len(C.others), 1)
        self.assertIn('无日期', C.others[0]['sum'])
        self.assertNotIn('None', C.others[0]['sum'])


class AeMatchPeriodCoverage(unittest.TestCase):
    """用户裁定（PLAN §15.1，2026-10-28）：「同期疑似 AE」的 aeMatch 时间口径统一改为 AE 期间覆盖检验日期
    （与第七批 AE 时间口径同因同策），废弃 ±w 天经验窗口；仍只作上下文与「请关联」用途。"""

    MET = 'lab:丙氨酸氨基转移酶'

    @staticmethod
    def _ae(n, t, s, e=''):
        return {'n': n, 't': t, 's': s, 'e': e, 'sh': 'AE', 'row': n}

    def test_build_labrows_ctx_uses_ae_period_not_window(self):
        from types import SimpleNamespace
        import ctcae
        from mm_build import build_labrows
        row = {'sid': 'S1', 'post': True, 'clin': 2, 'value': 88, 'lo': 9, 'hi': 50, 'unit': 'U/L',
               'visit': 'V2', 'date': '2026-06-20', 'sheet': '检验', 'row': 5, 'wb': 'edc', 'base': None,
               'grade': 0, 'links': [], 'reason': None, 'desc': '', 'group': '血生化'}
        C = SimpleNamespace(
            A={'aeMatch': [[self.MET.split(':')[1], '肝功能', 14]], 'labDomains': ['lab', 'vs', 'ecg']},
            S={'study': {'design': {'facts': []}}}, cfg={'thresholds': {'base': 0.3}},
            F={('S1', self.MET): [row]}, pop={'S1'}, subj={'S1': {'site': '01'}}, src={'sheets': {}},
            metric={self.MET: {'label': '丙氨酸氨基转移酶', 'n': 1, 'nq': 0, 'hasClin': True}},
            aeEnd={}, mh_by={'S1': []},
            ae_by={'S1': [
                self._ae(1, '肝功能异常·窗内虚构', '2026-06-25', '2026-06-30'),   # 距检验 5 天（±14 窗内），但期间不覆盖 06-20
                self._ae(2, '肝功能异常·窗外虚构', '2026-05-01'),                 # 距检验 50 天（窗外），但持续期间覆盖 06-20
            ]},
            G=ctcae.load({'grading': {'version': '5.0'}}), cmap={}, labrows=[])
        C.GL = C.G.label
        build_labrows(C)
        ctx = ' '.join(C.labrows[0]['ctx'])
        self.assertIn('肝功能异常·窗外虚构', ctx)          # 窗外但期间覆盖 → 列出
        self.assertNotIn('肝功能异常·窗内虚构', ctx)       # 窗内但期间不覆盖 → 不再列

    def test_csb_step2_uses_ae_period_not_window(self):
        from types import SimpleNamespace
        from ext_rules import m23_csb
        row = {'sid': 'S1', 'mid': self.MET, 'post': True, 'clin': 2, 'value': 30, 'lo': None, 'hi': None,
               'unit': 'U/L', 'visit': 'V2', 'date': '2026-06-20', 'sheet': '检验', 'row': 5, 'wb': 'edc',
               'base': {'value': 30, 'clin': 1, 'grade': 0}, 'grade': 0, 'links': [], 'reason': None,
               'desc': '', 'raw': '30'}
        C = SimpleNamespace(
            A={'aeMatch': [[self.MET.split(':')[1], '肝功能', 14]]},
            S={'study': {'design': {'facts': []}}}, cfg={'thresholds': {'base': 0.3}},
            F={('S1', self.MET): [row]}, subj={'S1': {'site': '01'}}, pop={'S1'},
            metric={self.MET: {'label': '丙氨酸氨基转移酶'}},
            src={'sheets': {}}, others=[], labrows=[], mhMatch=[], indBg=[],
            mh_by={'S1': []},
            ae_by={'S1': [
                self._ae(1, '肝功能异常·窗内虚构', '2026-06-25', '2026-06-30'),
                self._ae(2, '肝功能异常·窗外虚构', '2026-05-01'),
            ]})
        m23_csb(C)
        sums = ' '.join(o['sum'] for o in C.others)
        self.assertIn('肝功能异常·窗外虚构', sums)          # 期间覆盖 → CSX_AE「请关联」
        self.assertNotIn('肝功能异常·窗内虚构', sums)       # 期间不覆盖 → 不再作同期疑似


class ClinNotDone(unittest.TestCase):
    """K11：临床意义取值「未查/未做/未检」由 clin_map 映射为 'ND' → normalize 置未完成标记（done=否），
    不作为结果、不落「未评价」（避免日后有值无判定时误入「超出参考范围·未评价」，实证 D001 PE「未查」剩 1 题问卷）。"""

    def test_nd_clin_row_marked_not_done(self):
        import tempfile
        import openpyxl
        from normalize_listing import Book, findings
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'pe.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'PE'
            ws.append(['受试者编号', '访视', '检查日期', '检查项', '检查结果', '临床意义', '如异常，请详述'])
            ws.append(['S1', '筛选期', '2026-05-01', '一般情况', '正常', '正常', ''])
            ws.append(['S1', '筛选期', '2026-05-01', '淋巴结', '未查', '未查', ''])
            ws.append(['S2', '筛选期', '2026-05-02', '皮肤/黏膜', '未见异常', '异常有临床意义', '虚构皮损描述'])
            wb.save(p)
            M = {'workbooks': {'edc': str(p)},
                 'clin_map': [['异常无临床意义', 1], ['异常有临床意义', 2], ['正常', 0], ['未查', 'ND']],
                 'domains': {}}
            spec = {'wb': 'edc', 'sheet': 'PE', 'domain': 'pe', 'group': '体格检查', 'label_row': 1, 'var_row': 0,
                    'data_start': 2,
                    'cols': {'sid': '受试者编号', 'visit': '访视', 'date': '检查日期', 'test': '检查项',
                             'value': '检查结果', 'clin': '临床意义', 'desc': '如异常，请详述'}}
            rows = findings(spec, {'edc': Book(str(p))}, M)
            nd = next(r for r in rows if r['test'] == '淋巴结')
            self.assertEqual(nd.get('done'), '否')                 # 未完成（SoA 计「未做」）
            self.assertIsNone(nd.get('clin'))                      # 不是「未评价」
            self.assertIsNone(nd.get('raw'))                       # 「未查」不是检查结果（不得入定性/基线分析）
            self.assertIsNone(nd.get('value'))
            ok = next(r for r in rows if r['test'] == '一般情况')
            self.assertEqual((ok.get('clin'), ok.get('raw'), ok.get('done')), (0, '正常', None))
            abn = next(r for r in rows if r['test'] == '皮肤/黏膜')
            self.assertEqual((abn.get('clin'), abn.get('desc')), (2, '虚构皮损描述'))


class MissingDateRenderingK95(unittest.TestCase):
    """K95 扩展：除 M19 外，其余把日期直接拼进事实/上下文文本的渲染点，日期缺失/空 → 「无日期」，不得出现 None。
    每处用虚构夹具构造无日期记录。"""

    @staticmethod
    def _ns(**kw):
        from types import SimpleNamespace
        return SimpleNamespace(**kw)

    @staticmethod
    def _rex(*pairs):
        import re
        return [(re.compile(a), re.compile(b)) for a, b in pairs]

    @staticmethod
    def _assert_nodate(testcase, text):
        testcase.assertIn('无日期', text)
        testcase.assertNotIn('None', text)

    def test_m13_ctx_cm_without_start(self):
        from ext_rules import m13_mhx_t
        row = {'sid': 'S1', 'mid': 'lab:ALT', 'post': False, 'clin': 1, 'value': 88, 'raw': '88', 'unit': 'U/L',
               'lo': 9, 'hi': 50, 'dev': 0.76, 'grade': 0, 'pct': None, 'visit': 'V1', 'date': None,
               'sheet': '检验', 'row': 5, 'wb': 'edc', 'links': [], 'group': '血生化', 'desc': '',
               'base': {'visit': 'V1', 'raw': '30', 'unit': 'U/L', 'clin': 0}}
        C = self._ns(A={'mhMatch': [['血红蛋白', '贫血']], 'labDomains': ['lab']},
                     cfg={'thresholds': {'dev': 0.3, 'base': 0.3, 'per_metric': {}}}, mthr=[], others=[],
                     F={('S1', 'lab:ALT'): [row]}, pop={'S1'}, subj={'S1': {'site': '01'}},
                     mhMatch=self._rex(('血红蛋白', '贫血'), ('ALT', '肝功能异常|肝损')), indBg=[], cmInd=self._rex(('保肝', '肝功能异常')),
                     mh_by={'S1': []}, cm_by={'S1': [{'t': '联苯双酯', 's': None, 'why': '肝功能异常', 'sh': 'CM', 'row': 2, 'wb': '', 'n': 1}]},
                     metric={'lab:ALT': {'label': '丙氨酸氨基转移酶'}}, src={'sheets': {}}, labrows=[])
        m13_mhx_t(C)
        ctx = ' '.join(C.labrows[0]['ctx'])
        self.assertIn('有对应用药', ctx)
        self._assert_nodate(self, ctx)

    def test_m17_cm_without_start(self):
        from ext_rules import m17_cm_ind
        C = self._ns(cmInd=self._rex(('保肝', '联苯双酯')), cmProto=[], pop={'S1'}, subj={'S1': {'site': '01', 'fd': '2026-05-01'}},
                     mh_by={'S1': []}, ae_by={'S1': []},
                     cm_by={'S1': [{'t': '联苯双酯', 's': None, 'sh': 'CM', 'row': 2, 'wb': '', 'n': 1, 'why': '保肝治疗'}]},
                     others=[], src={'sheets': {}})
        m17_cm_ind(C)
        self.assertEqual(len(C.others), 1)
        self._assert_nodate(self, C.others[0]['sum'])

    def test_m18_preg_row_without_date(self):
        from ext_rules import m18_preg
        row = {'sid': 'S1', 'mid': 'lab:尿HCG', 'post': False, 'clin': 2, 'raw': '阳性', 'value': None,
               'lo': None, 'hi': None, 'unit': '', 'grade': 0, 'pct': None, 'visit': 'V1', 'date': None,
               'sheet': '检验', 'row': 3, 'wb': '', 'links': [], 'desc': '', 'base': None}
        C = self._ns(pop={'S1'}, subj={'S1': {'site': '01'}}, F={('S1', 'lab:尿HCG'): [row]},
                     metric={'lab:尿HCG': {'label': '尿HCG'}}, others=[], src={'sheets': {}})
        m18_preg(C)
        self.assertEqual(len(C.others), 1)
        self._assert_nodate(self, C.others[0]['sum'])

    def test_m20_sae_without_start(self):
        from ext_rules import m20_ae_sae
        C = self._ns(pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}},
                     aes=[{'sid': 'S1', 't': '皮疹', 's': '', 'e': '', 'sae': True, 'sae_crit': '', 'sh': 'AE', 'row': 2, 'n': 1, 'wb': ''},
                          {'sid': 'S1', 't': '骨折', 's': '', 'e': '', 'sae': False, 'sae_crit': '住院', 'sh': 'AE', 'row': 3, 'n': 2, 'wb': ''}])
        m20_ae_sae(C)
        self.assertEqual(len(C.others), 2)
        for o in C.others:
            self._assert_nodate(self, o['sum'])

    def test_m20_unknown_criteria_not_reported_as_unchecked(self):
        """MGK 2026-11-14：表里没有可识别的 SAE 标准列（信息缺席）时不报「SAE 标准均未勾选」——37 条误报。"""
        from ext_rules import m20_ae_sae
        C = self._ns(pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}},
                     aes=[{'sid': 'S1', 't': '肺炎', 's': '2026-01-02', 'e': '', 'sae': True, 'sae_crit': '', 'sae_crit_known': False,
                           'sh': 'AE', 'row': 2, 'n': 1, 'wb': ''}])
        m20_ae_sae(C)
        self.assertEqual([o for o in C.others if '均未勾选' in o['sum']], [])

    def test_sdtm_sae_criteria_vars_recognized(self):
        """只有变量名表头（AESHOSP/AESDTH…）时按 SDTM 标准变量名认 SAE 标准。"""
        import normalize_listing as N
        self.assertTrue(N._SAE_CRIT_VAR.fullmatch('AESHOSP') and N._SAE_CRIT_VAR.fullmatch('AESDETH'))
        self.assertFalse(N._SAE_CRIT_VAR.fullmatch('AESER'))
        self.assertEqual(N._SAE_CRIT_NAME['HOSP'], '住院或延长住院')

    def test_m20_death_without_dates_no_nonsense_query(self):
        """转归死亡但起止日期均缺失：无死亡日期无法定义「其后」，不得发出「（），其后仍有记录」类事实。"""
        from ext_rules import m20_ae_sae
        C = self._ns(pop={'S1'}, subj={'S1': {'site': '01', 'eos_d': ''}}, others=[], src={'sheets': {}},
                     aes=[{'sid': 'S1', 't': '猝死', 's': '', 'e': '', 'out': '死亡', 'sae': True, 'sae_crit': '其他', 'sh': 'AE', 'row': 4, 'n': 3, 'wb': ''}],
                     exposure=[{'sid': 'S1', 'start': '2026-06-01'}], visits=[], F={})
        m20_ae_sae(C)
        self.assertEqual([o for o in C.others if '其后仍有' in o['sum']], [])
        for o in C.others:
            self.assertNotIn('（），其后', o['sum'])

    def test_m21_open_ae_without_start(self):
        from ext_rules import m21_ae_course
        row = {'sid': 'S1', 'mid': 'lab:PLT', 'post': True, 'clin': 1, 'value': 40, 'raw': '40', 'unit': '10^9/L',
               'lo': 100, 'hi': 300, 'grade': 0, 'pct': None, 'visit': 'V2', 'date': '2026-06-10',
               'sheet': '检验', 'row': 5, 'wb': 'edc', 'links': [['AE', '血小板减少', None, 3]], 'desc': '', 'base': None}
        C = self._ns(pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}}, cfg={}, visits=[],
                     F={('S1', 'lab:PLT'): [row]}, metric={'lab:PLT': {'label': '血小板计数'}},
                     aes=[{'sid': 'S1', 't': '血小板减少', 's': '', 'e': '', 'act': '停药', 'sh': 'AE', 'row': 6, 'n': 3, 'wb': ''}])
        m21_ae_course(C)
        self.assertEqual(len(C.others), 1)
        self._assert_nodate(self, C.others[0]['sum'])

    def test_threshold_rule_row_without_date(self):
        from mm_build import threshold_rules
        row = {'sid': 'S1', 'mid': 'lab:ALT', 'post': False, 'clin': None, 'value': 88, 'raw': '88', 'unit': 'U/L',
               'lo': 9, 'hi': 50, 'grade': 0, 'pct': None, 'visit': 'V1', 'date': None,
               'sheet': '检验', 'row': 5, 'wb': 'edc', 'links': [], 'base': None}
        R = {'id': 'TR-X', 'metric': 'ALT', 'cat': '方案阈值核对', 'op': '>=', 'v': 50, 'post': False,
             'sum': '{test} {value}（{visit} {date}）达到方案阈值 {thr}'}
        C = self._ns(A={'thresholdRules': [R]}, cfg={}, pop={'S1'}, subj={'S1': {'site': '01'}},
                     F={('S1', 'lab:ALT'): [row]}, metric={'lab:ALT': {'label': '丙氨酸氨基转移酶'}},
                     others=[], src={'sheets': {}})
        threshold_rules(C)
        self.assertEqual(len(C.others), 1)
        self._assert_nodate(self, C.others[0]['sum'])

    def test_grade_vs_lab_row_without_date(self):
        from mm_build import ae_checks
        row = {'sid': 'S1', 'mid': 'lab:HGB', 'test': '血红蛋白', 'grade': 2, 'gterm': '贫血', 'raw': '80', 'unit': 'g/L',
               'lo': 115, 'hi': 150, 'value': 80, 'clin': 1, 'date': None, 'visit': 'V2',
               'sheet': '检验', 'row': 9, 'wb': 'edc', 'links': [['AE', '贫血', None, 5]], 'pct': None, 'base': None, 'post': True}
        C = self._ns(A={'aeChecks': ['grade_vs_lab']}, pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}},
                     aesiDefs=[],
                     F={('S1', 'lab:HGB'): [row]}, GL='CTCAE 5.0',
                     aes=[{'sid': 'S1', 't': '贫血', 'g': '1级', 's': '2026-05-01', 'e': '', 'cm': '', 'act': '', 'out': '',
                           'rel': '', 'sh': 'AE', 'row': 8, 'n': 5, 'wb': '', 'pre': False, 'te': True, 'sae': False,
                           'aesi': False, '_rel': False, '_aesi_term': False, '_aesi_def': [], 'fd': '2026-05-01'}])
        ae_checks(C)
        hit = [o for o in C.others if o['cat'] == 'AE分级与检验等级核对']
        self.assertEqual(len(hit), 1)
        self._assert_nodate(self, hit[0]['sum'])

    def test_cm_missing_ae_without_start(self):
        from mm_build import ae_checks
        C = self._ns(A={'aeChecks': ['cm_missing']}, pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}},
                     aesiDefs=[], F={},
                     cm_by={'S1': [{'t': '止痛药', 'wk': 'AE', 'aeno': '', 'why': ''}]},
                     aes=[{'sid': 'S1', 't': '头痛', 'g': '1级', 's': '', 'e': '', 'cm': '是', 'act': '', 'out': '',
                           'rel': '', 'sh': 'AE', 'row': 8, 'n': 4, 'wb': '', 'pre': False, 'te': True, 'sae': False,
                           'aesi': False, '_rel': False, '_aesi_term': False, '_aesi_def': [], 'fd': '2026-05-01'}])
        ae_checks(C)
        hit = [o for o in C.others if o['cat'] == 'AE合并用药记录核对']
        self.assertEqual(len(hit), 1)
        self._assert_nodate(self, hit[0]['sum'])

    def test_range_check_row_without_date(self):
        from mm_build import range_checks

        def mk(i, **kw):
            return {'sid': 'S1', 'value': 3.0, 'raw': '3.0', 'lo': 2, 'hi': 4, 'date': f'2026-05-0{i}', 'visit': f'V{i}',
                    'sheet': '检验', 'row': i, 'wb': 'edc', 'clin': 1, 'test': '肌酐', 'mid': 'lab:肌酐', **kw}
        rows = [mk(i) for i in range(1, 6)] + [mk(6, lo=None, hi=None, date=None)]
        C = self._ns(A={}, pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}},
                     metric={'lab:肌酐': {'domain': 'lab', 'label': '肌酐'}}, F={('S1', 'lab:肌酐'): rows})
        range_checks(C)
        self.assertEqual(len(C.others), 1)
        self._assert_nodate(self, C.others[0]['sum'])

    def test_eligibility_row_without_date(self):
        from mm_build import eligibility_checks
        row = {'sid': 'S1', 'mid': 'lab:肌酐', 'post': False, 'value': 120, 'raw': '120', 'unit': '', 'lo': None, 'hi': None,
               'grade': 0, 'pct': None, 'visit': '筛选', 'date': None, 'sheet': '检验', 'row': 7, 'wb': 'edc',
               'clin': None, 'links': [], 'base': None, 'desc': ''}
        E = {'id': 'IE-E1', 'metric': '肌酐', 'op': '>=', 'v': 100, 'text': '虚构排除标准', 'kind': 'exclusion'}
        C = self._ns(A={'eligibility': [E]}, cfg={}, pop={'S1'}, VIS=[], UNS=set(), others=[], src={'sheets': {}},
                     subj={'S1': {'site': '01', 'fd': '2026-05-01', 'rand_d': ''}},
                     F={('S1', 'lab:肌酐'): [row]}, metric={'lab:肌酐': {'label': '肌酐'}})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self._assert_nodate(self, hit[0]['sum'])

    def test_eff_magnitude_row_without_date(self):
        from mm_build import eff_magnitude

        def mk(v, visit, date):
            return {'sid': 'S1', 'mid': 'lab:尿酸', 'value': v, 'raw': str(v), 'unit': 'umol/L', 'lo': None, 'hi': None,
                    'grade': 0, 'pct': None, 'visit': visit, 'date': date, 'sheet': '检验', 'row': len(visit),
                    'wb': 'edc', 'clin': 1, 'links': [], 'base': None, 'post': True}
        C = self._ns(A={'efficacy': [{'id': 'ua', 'label': '尿酸', 'src': 'lab:尿酸', 'unit': 'umol/L'}]},
                     pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}}, vi=lambda v: 0,
                     F={('S1', 'lab:尿酸'): [mk(500, 'V1', '2026-05-01'), mk(480, 'V2', '2026-06-01'), mk(510, 'V4', '2026-06-20'),
                                             mk(6000, 'V3', None)]})
        eff_magnitude(C)
        hit = [o for o in C.others if o['cat'] == '有效性数据量级异常']
        self.assertEqual(len(hit), 1)
        self._assert_nodate(self, hit[0]['sum'])

    def test_pd_icf02_signature_without_date(self):
        from pd_rules import _PD
        C = self._ns(A={'pd': {'icfVersions': [{'ver': 'v2.0', 'reconsent': True, 'effective': '2026-06-01'}]}},
                     S={}, cfg={}, pop={'S1'}, dosed=set(), visits=[],
                     subj={'S1': {'site': '01', 'eos_d': '2026-07-01'}},
                     icf=[{'sid': 'S1', 'ver': 'v1.0', 'date': None, 'row': 4, 'sheet': 'ICF', 'wb': 'edc'}])
        eng = _PD(C)
        eng.icf()
        hit = [i for i in eng.items if i['rule'] == 'ICF-02']
        self.assertEqual(len(hit), 1)
        self._assert_nodate(self, hit[0]['fact'])

    def test_pd_ip01_ip04_exposure_without_start(self):
        from pd_rules import _PD
        ex = {'sid': 'S1', 'start': None, 'route': '静脉', 'freq': '每日一次', 'fast': '否', 'row': 3, 'sheet': '给药', 'wb': 'edc'}
        C = self._ns(A={'pd': {'dosing': {'route': '口服', 'freq': '每日一次'}, 'fasting': True}}, S={}, cfg={},
                     pop={'S1'}, dosed={'S1'}, subj={'S1': {'site': '01'}}, visits=[], others=[], exposure=[ex])
        eng = _PD(C)
        eng.dosing()
        rules = {i['rule']: i['fact'] for i in eng.items}
        self.assertIn('IP-01', rules)
        self._assert_nodate(self, rules['IP-01'])
        self.assertIn('IP-04', rules)
        self._assert_nodate(self, rules['IP-04'])


class EligPremiseAndCompound(unittest.TestCase):
    """用户 2026-11-01 三裁定（运行侧）：①「经治疗」前提超标改发「请核实」，不直接判排除；
    ②总胆红素超标但直接胆红素占比<35% → 降为「按方案可接受」提示；≥35% 或不可得 → 照旧排除；
    ③HBsAg 阳性须同时 HBV-DNA≥1×10³ 才排除；DNA 低于阈值不发；DNA 不可得降为「请核实」。全部虚构夹具。"""

    @staticmethod
    def _ns(**kw):
        from types import SimpleNamespace
        return SimpleNamespace(**kw)

    @staticmethod
    def _row(mid, raw, value, visit='SCR', date='2026-06-01', **kw):
        return {'sid': 'S1', 'mid': mid, 'post': False, 'value': value, 'raw': raw, 'unit': '', 'lo': None, 'hi': None,
                'grade': 0, 'pct': None, 'visit': visit, 'date': date, 'sheet': '检验', 'row': 7, 'wb': 'edc',
                'clin': None, 'links': [], 'base': None, 'desc': '', **kw}

    def _C(self, E, rows_by_mid):
        return self._ns(A={'eligibility': [E]}, cfg={}, pop={'S1'}, VIS=[], UNS=set(), others=[], src={'sheets': {}},
                        subj={'S1': {'site': '01', 'fd': '2026-07-01', 'rand_d': '2026-07-01'}},
                        F={('S1', mid): rows for mid, rows in rows_by_mid.items()},
                        metric={mid: {'label': mid.split(':', 1)[1]} for mid in rows_by_mid})

    def test_treated_premise_issues_verify_not_exclusion(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E9', 'metric': r'^vs:(?:收缩压|SBP)', 'op': '>', 'v': 150, 'on': 'val', 'kind': 'exclusion',
             'text': '虚构：未控制的高血压（定义为经治疗收缩压>150）', 'premise': 'treated'}
        C = self._C(E, {'vs:收缩压': [self._row('vs:收缩压', '160', 160.0, unit='mmHg', visit='基线')]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)                                        # 仍有信号（不静默）
        # 用户 2026-11-04 裁定 9＝A：有病史/合并用药数据时自动判「经治疗」前提——无相关病史与用药 → 前提不成立、不构成排除
        self.assertIn('经治疗后仍超标', hit[0]['sum'])
        self.assertEqual(hit[0]['_elig'], 'premise_unmet')
        self.assertNotIn('降压', hit[0]['sum'])                            # 泛化守卫：文案不得写死病种（本条=高血压、他研究可为任何病种）
        self.assertNotIn('，但已随机/给药', hit[0]['sum'])
        from collections import defaultdict
        C.others = []
        C.mh_by = defaultdict(list, {list(C.pop)[0]: [{'t': '高血压'}]})        # 只有病史、无用药 → 请提供治疗情况（待判定）
        C.cm_by = defaultdict(list)
        eligibility_checks(C)
        o = [x for x in C.others if x['cat'] == '入排标准核对'][0]
        self.assertEqual(o['_elig'], 'undetermined')
        self.assertIn('请提供该参与者的相关治疗情况', o['sum'])
        C.others = []
        C.cm_by = defaultdict(list, {list(C.pop)[0]: [{'t': '氨氯地平', 'why': '高血压'}]})   # 有对应治疗用药仍超标 → 违反
        eligibility_checks(C)
        o = [x for x in C.others if x['cat'] == '入排标准核对'][0]
        self.assertEqual(o['_elig'], 'violated')

    def test_dbil_ratio_below_35_downgrades(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E24', 'metric': r'^lab:(?!.*(?:直接|间接|结合|DBIL|IBIL|尿))(?:(总胆红素|TBIL))', 'op': '>', 'v': 1.5,
             'on': 'uln', 'kind': 'exclusion', 'text': '虚构：总胆红素>1.5×ULN',
             'bili': {'metric': r'^lab:.*(?:直接胆红素|DBIL)', 'pct': 35.0}}
        tb = self._row('lab:总胆红素（TBIL）', '40', 40.0, unit='umol/L', hi=17.1)
        db = self._row('lab:直接胆红素（DBIL）', '8', 8.0, unit='umol/L')       # 占比 20%＜35%
        C = self._C(E, {'lab:总胆红素（TBIL）': [tb], 'lab:直接胆红素（DBIL）': [db]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('按方案可接受', hit[0]['sum'])                          # 修前判排除（红）
        self.assertIn('孤立性胆红素', hit[0]['sum'])
        self.assertNotIn('，但已随机/给药', hit[0]['sum'])
        self.assertLess(hit[0]['pr'], 4)                                     # 降为提示级

    def test_dbil_ratio_at_or_above_keeps_exclusion(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E24', 'metric': r'^lab:(?!.*(?:直接|间接|结合|DBIL|IBIL|尿))(?:(总胆红素|TBIL))', 'op': '>', 'v': 1.5,
             'on': 'uln', 'kind': 'exclusion', 'text': '虚构：总胆红素>1.5×ULN',
             'bili': {'metric': r'^lab:.*(?:直接胆红素|DBIL)', 'pct': 35.0}}
        tb = self._row('lab:总胆红素（TBIL）', '40', 40.0, unit='umol/L', hi=17.1)
        db = self._row('lab:直接胆红素（DBIL）', '20', 20.0, unit='umol/L')    # 占比 50%≥35%
        C = self._C(E, {'lab:总胆红素（TBIL）': [tb], 'lab:直接胆红素（DBIL）': [db]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('，但已随机/给药', hit[0]['sum'])

    def test_dbil_missing_keeps_exclusion(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E24', 'metric': r'^lab:(?!.*(?:直接|间接|结合|DBIL|IBIL|尿))(?:(总胆红素|TBIL))', 'op': '>', 'v': 1.5,
             'on': 'uln', 'kind': 'exclusion', 'text': '虚构：总胆红素>1.5×ULN',
             'bili': {'metric': r'^lab:.*(?:直接胆红素|DBIL)', 'pct': 35.0}}
        tb = self._row('lab:总胆红素（TBIL）', '40', 40.0, unit='umol/L', hi=17.1)
        C = self._C(E, {'lab:总胆红素（TBIL）': [tb]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('，但已随机/给药', hit[0]['sum'])

    def test_hbsag_positive_with_dna_below_threshold_not_flagged(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E14', 'metric': r'^lab:(?:乙肝表面抗原|乙型肝炎病毒表面抗原|HBsAg)', 're': r'阳性|\+|positive|检出',
             'op': 're', 'v': None, 'kind': 'exclusion', 'text': '虚构：HBsAg阳性且HBV-DNA≥1×10³',
             'gate': {'metric': r'^lab:.*(?:HBV.?DNA)', 'op': '>=', 'v': 1000.0, 'unit': '拷贝数/mL', 'label': 'HBV-DNA'}}
        hbsag = self._row('lab:乙肝表面抗原（HBsAg）', '阳性', None)
        dna = self._row('lab:乙肝病毒载量（HBV-DNA）', '5.0×10²', 500.0, unit='拷贝数/mL')
        C = self._C(E, {'lab:乙肝表面抗原（HBsAg）': [hbsag], 'lab:乙肝病毒载量（HBV-DNA）': [dna]})
        eligibility_checks(C)
        self.assertEqual([o for o in C.others if o['cat'] == '入排标准核对'], [])   # 修前判排除（红）

    def test_hbsag_positive_with_dna_above_threshold_keeps_exclusion(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E14', 'metric': r'^lab:(?:乙肝表面抗原|乙型肝炎病毒表面抗原|HBsAg)', 're': r'阳性|\+|positive|检出',
             'op': 're', 'v': None, 'kind': 'exclusion', 'text': '虚构：HBsAg阳性且HBV-DNA≥1×10³',
             'gate': {'metric': r'^lab:.*(?:HBV.?DNA)', 'op': '>=', 'v': 1000.0, 'unit': '拷贝数/mL', 'label': 'HBV-DNA'}}
        hbsag = self._row('lab:乙肝表面抗原（HBsAg）', '阳性', None)
        dna = self._row('lab:乙肝病毒载量（HBV-DNA）', '2.0×10³', 2000.0, unit='拷贝数/mL')
        C = self._C(E, {'lab:乙肝表面抗原（HBsAg）': [hbsag], 'lab:乙肝病毒载量（HBV-DNA）': [dna]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('，但已随机/给药', hit[0]['sum'])

    def test_hbsag_positive_without_dna_issues_verify(self):
        from mm_build import eligibility_checks
        E = {'id': 'IE-E14', 'metric': r'^lab:(?:乙肝表面抗原|乙型肝炎病毒表面抗原|HBsAg)', 're': r'阳性|\+|positive|检出',
             'op': 're', 'v': None, 'kind': 'exclusion', 'text': '虚构：HBsAg阳性且HBV-DNA≥1×10³',
             'gate': {'metric': r'^lab:.*(?:HBV.?DNA)', 'op': '>=', 'v': 1000.0, 'unit': '拷贝数/mL', 'label': 'HBV-DNA'}}
        hbsag = self._row('lab:乙肝表面抗原（HBsAg）', '阳性', None)
        C = self._C(E, {'lab:乙肝表面抗原（HBsAg）': [hbsag]})
        eligibility_checks(C)
        hit = [o for o in C.others if o['cat'] == '入排标准核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('请核实', hit[0]['sum'])
        self.assertIn('HBV-DNA', hit[0]['sum'])
        self.assertNotIn('，但已随机/给药', hit[0]['sum'])


class IbSocCodeSuffix(unittest.TestCase):
    """IB 风险条目 SOC/PT 名称带 MedDRA 编码尾缀（「心脏器官疾病（10007541）」「心脏器官疾病/10007541」）时
    与 EDC 侧纯名称比对应命中：编码尾缀剥离后再比较。"""

    @staticmethod
    def _C(entries):
        from types import SimpleNamespace
        return SimpleNamespace(A={'expectedAE': entries})

    def test_soc_fullwidth_and_halfwidth_code_hit(self):
        from mm_build import ib_match
        C = self._C([{'term': '心脏事件', 'label': 'IB重要风险', 're': '', 'pt': '', 'soc': '心脏器官疾病（10007541）', 'labs': []},
                     {'term': '肝性脑病', 'label': 'IB重要风险', 're': '', 'pt': '', 'soc': '肝脏疾病(10023855)', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '心肌梗死', 'pt': '心肌梗死', 'soc': '心脏器官疾病', 'sae': False, 'g': '3级'}),
                         ['IB重要风险·心脏事件（同SOC，严重/≥3级）'])
        self.assertEqual(ib_match(C, {'t': '肝昏迷', 'pt': '肝性脑病', 'soc': '肝脏疾病', 'sae': True, 'g': '2级'}),
                         ['IB重要风险·肝性脑病（同SOC，严重/≥3级）'])

    def test_soc_slash_style_still_hit(self):
        from mm_build import ib_match
        C = self._C([{'term': '心脏事件', 'label': 'IB重要风险', 're': '', 'pt': '', 'soc': '心脏器官疾病/10007541', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '心肌梗死', 'pt': '', 'soc': '心脏器官疾病', 'sae': True, 'g': '1级'}),
                         ['IB重要风险·心脏事件（同SOC，严重/≥3级）'])

    def test_pt_code_suffix_hit(self):
        """PT 名称带编码尾缀（IB 侧）与 EDC 纯 PT 相等判定应剥离后比较（term 与 AE 术语不同、仅 PT 相等时 PT 判定是唯一通路）。"""
        from mm_build import ib_match
        C = self._C([{'term': '血管性头痛风险', 'label': 'IB风险', 're': '', 'pt': '头痛（10019211）', 'soc': '', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '偶发头痛', 'pt': '头痛', 'soc': '', 'sae': False, 'g': '1级'}),
                         ['IB风险·血管性头痛风险'])


class SampleWindowDedup(unittest.TestCase):
    """K10：PK/PD 同一采血时刻两管各计一次 SAMP-02 → 按 (sid, visit, date, tpt, time) 去重合并，
    事实列出涉及的样本类型（实证 D001 PC/PD 成对出现应减半）。"""

    @staticmethod
    def _ctx(rows):
        from types import SimpleNamespace
        return SimpleNamespace(A={'pd': {'sample': {'windowMin': 30}}}, S={}, cfg={},
                               subj={'S1': {'site': '01'}}, visits=[], pop={'S1'},
                               exposure=[{'sid': 'S1', 'start': '2026-05-15', 'time': '09:00'}], sample=rows)

    def test_pk_pd_same_draw_merged_into_one_finding(self):
        from pd_rules import _PD
        pc = {'sid': 'S1', 'visit': 'W2', 'date': '2026-05-15', 'time': '12:10', 'tpt': '给药后2h',
              'sheet': 'PC', 'wb': 'edc', 'row': 97, 'done': ''}
        pd_ = dict(pc, sheet='PD', row=97)
        eng = _PD(self._ctx([pc, pd_]))
        eng.samples()
        items = [i for i in eng.items if i['rule'] == 'SAMP-02']
        self.assertEqual(len(items), 1)
        self.assertIn('（PC/PD）', items[0]['fact'])                 # 事实列出涉及的样本类型
        self.assertIn('计划 120±30 分钟', items[0]['fact'])
        self.assertEqual([s[0] for s in items[0]['src']], ['edc:PC', 'edc:PD'])

    def test_different_draw_times_stay_separate(self):
        from pd_rules import _PD
        pc = {'sid': 'S1', 'visit': 'W2', 'date': '2026-05-15', 'time': '12:10', 'tpt': '给药后2h',
              'sheet': 'PC', 'wb': 'edc', 'row': 97, 'done': ''}
        pd_ = dict(pc, sheet='PD', row=99, time='12:40')
        eng = _PD(self._ctx([pc, pd_]))
        eng.samples()
        items = [i for i in eng.items if i['rule'] == 'SAMP-02']
        self.assertEqual(len(items), 2)
        self.assertIn('（PC）', items[0]['fact'])                    # 单管事实写法不变（金标准快照口径）
        self.assertIn('（PD）', items[1]['fact'])


class MetricDirectionTable(unittest.TestCase):
    """方向表补条（2026-10-29 用户批准）：QT/PR 间期、凝血、AMH 判单向，铁代谢与生命体征判双向。
    both=显式条目、不限制（metric_dir 返回 None），不得误伤。"""

    @classmethod
    def setUpClass(cls):
        from ext_rules import set_metric_dir
        set_metric_dir(None)                             # 项目覆盖为空 → 纯默认表

    def test_qt_pr_intervals_up(self):
        from ext_rules import metric_dir
        for s in ('QT间期', 'QT', 'QTc', 'QTcF', 'QTcB', 'PR间期', 'P-R间期', '校正QT间期'):
            self.assertEqual(metric_dir(s), 'up', f'{s} 应判 up')

    def test_coagulation_up(self):
        from ext_rules import metric_dir
        for s in ('INR', '国际标准化比值', '凝血酶原时间', 'PT', '活化部分凝血活酶时间', 'APTT', '部分凝血活酶时间'):
            self.assertEqual(metric_dir(s), 'up', f'{s} 应判 up')

    def test_amh_down(self):
        from ext_rules import metric_dir
        for s in ('AMH', '抗缪勒管激素', '抗缪勒氏管激素', '抗苗勒管激素'):
            self.assertEqual(metric_dir(s), 'down', f'{s} 应判 down')

    def test_iron_and_vitals_both_unrestricted(self):
        from ext_rules import metric_dir
        for s in ('铁蛋白', '血清铁', '总铁结合力', '体温', '脉搏', '呼吸频率', '心率'):
            self.assertIsNone(metric_dir(s), f'{s} 应为 both＝不限制（返回 None）')

    def test_no_false_hits_and_old_rows_intact(self):
        from ext_rules import metric_dir
        self.assertEqual(metric_dir('HDL'), 'down')      # 旧条目回归：HDL 仍 down
        self.assertEqual(metric_dir('丙氨酸氨基转移酶'), 'up')
        self.assertIsNone(metric_dir('催乳素 PRL'))       # PR 词边界：PRL 不受 PR 条影响
        self.assertIsNone(metric_dir('白细胞计数'))        # 未收录指标不判方向（现状不变）


class IbUmbrellaDowngrade(unittest.TestCase):
    """IB 伞形条目降级（2026-10-29 用户裁定）：
    (a) 伞形判据＝风险术语去括号词与通用实验室词（检测/检查/异常/升高/降低/变化/实验室）后零剩余；
    (b) 伞形条目不走第③级「各类检查」类别兜底，保留第②级同 SOC（严重/≥3 级过滤不变）；
    (c) 伞形条目带 findings.analyte 时类别兜底允许，但要求 AE 术语与 analyte/label 共享实质词；
    (d) 非伞形条目类别兜底要求与 AE 术语共享 ≥2 字实质内容词。
    背景：D001 曾因「血液学检测异常→各类检查」链给 311 条 soc=各类检查 的 AE 全量打标签（AE 行 353/488 带标签）。"""

    @staticmethod
    def _C(entries):
        from types import SimpleNamespace
        return SimpleNamespace(A={'expectedAE': entries})

    def test_umbrella_judgement(self):
        from mm_build import _umbrella_term
        self.assertTrue(_umbrella_term('血液学检测异常'))
        self.assertTrue(_umbrella_term('实验室检查异常'))
        self.assertTrue(_umbrella_term('心电图检查异常'))
        self.assertFalse(_umbrella_term('中性粒细胞计数减少'))   # 剩「中性粒细胞…」实质词＝非伞形
        self.assertFalse(_umbrella_term('血压升高'))
        self.assertFalse(_umbrella_term('血脂异常'))

    def test_umbrella_without_analyte_blocked(self):
        """链1：伞形条目无 analyte → 类别兜底被拦（311 条噪音链回归闸；≥3 级也不放行）。"""
        from mm_build import ib_match
        C = self._C([{'term': '实验室检查异常', 'label': 'IB重要潜在风险', 're': '', 'pt': '', 'soc': '各类检查', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '肌酸激酶升高', 'pt': '肌酸激酶升高', 'soc': '各类检查', 'sae': False, 'g': '4级'}), [])

    def test_umbrella_with_analyte_matches_only_that_analyte(self):
        """链2：伞形条目带 analyte → 只兜 AE 术语共享该指标实质词的记录。"""
        from mm_build import ib_match
        C = self._C([{'term': '血液学检测异常', 'label': 'IB重要潜在风险', 're': '', 'pt': '', 'soc': '各类检查',
                      'labs': [['WBC', 'WBC、LYMPH计数及比率降低', 'low']]}])
        self.assertEqual(ib_match(C, {'t': '白细胞计数降低', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '2级'}),
                         ['IB重要潜在风险·血液学检测异常（各类检查，严重/≥3级）'])
        self.assertEqual(ib_match(C, {'t': '肌酸激酶升高', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '4级'}), [])

    def test_specific_entry_shared_stem_hits(self):
        """链3：非伞形具体条目与 AE 术语共享 ≥2 字实质词 → 类别兜底命中。"""
        from mm_build import ib_match
        C = self._C([{'term': '血小板减少', 'label': 'IB风险', 're': '', 'pt': '', 'soc': '各类检查', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '血小板计数降低', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '3级'}),
                         ['IB风险·血小板减少（各类检查，严重/≥3级）'])

    def test_specific_entry_without_shared_stem_blocked(self):
        """链4：非伞形具体条目与 AE 术语无共享实质词 → 被拦。"""
        from mm_build import ib_match
        C = self._C([{'term': '肝酶升高', 'label': 'IB风险', 're': '', 'pt': '', 'soc': '各类检查', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '肌酸激酶升高', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '3级'}), [])

    def test_same_soc_severe_unchanged(self):
        """回归守卫：第②级同 SOC（真实器官系统 SOC、严重/≥3 级过滤）不受伞形降级影响。"""
        from mm_build import ib_match
        C = self._C([{'term': '严重感染', 'label': 'IB重要潜在风险', 're': '', 'pt': '感染', 'soc': '感染及侵染类疾病', 'labs': []}])
        # V6：风险事件族（感染→肺炎等）使「肺炎」直接命中「严重感染」，同 SOC 兜底不再需要；严重/≥3 级过滤不变
        self.assertEqual(ib_match(C, {'t': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'sae': True, 'g': '2级'}),
                         ['IB重要潜在风险·严重感染'])
        self.assertEqual(ib_match(C, {'t': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'sae': False, 'g': '1级'}), [])

    def test_cell_suffix_no_false_share(self):
        """回归守卫：淋巴细胞×中性粒细胞不因「细胞」误共享（公共前缀锚定）。"""
        from mm_build import ib_match
        C = self._C([{'term': '淋巴细胞计数减少', 'label': 'IB风险', 're': '', 'pt': '', 'soc': '各类检查', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '中性粒细胞计数减少', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '3级'}), [])


class AeSpectrumNoMedDRA(unittest.TestCase):
    """MedDRA 不可用（AE 带 soc 比例 <20%，含完全无）→ AE 谱不再按原文术语逐条分组
    （试用实证：123 组刷屏），改为按 IB 风险类别分组＋超出前 20 归「其他」，
    组名注明「（未按器官系统——MedDRA 不可用）」，AE 记录类别同步改写（安全页类别 chips 同一口径）；
    有字典（soc 比例达标）行为不变。夹具全虚构。"""

    NOTE = '（未按器官系统——MedDRA 不可用）'
    OTHER = '其他' + NOTE

    @staticmethod
    def _C(aes):
        from types import SimpleNamespace
        return SimpleNamespace(pop={'S1'}, A={}, aes=aes)

    @staticmethod
    def _ae(t, soc='', ib=()):
        # c＝build_events 的类别口径：catmap 未命中 → soc，再退原文术语（与真实数据流一致）
        return {'sid': 'S1', 't': t, 'c': soc or t, 'g': '1级', 'sae': False, 'pt': '', 'soc': soc,
                'te': True, 'aesi': False, '_rel': False, 'ib': list(ib)}

    def test_no_soc_groups_by_ib_category_plus_other(self):
        from mm_build import ae_summary
        aes = [self._ae('血小板计数降低', ib=['IB重要潜在风险·血小板减少']) for _ in range(2)] + \
              [self._ae('中性粒细胞计数降低', ib=['IB重要潜在风险·中性粒细胞减少（同SOC）'])] + \
              [self._ae(t) for t in ('头痛', '头痛', '恶心', '恶心', '皮疹', '头晕', '乏力')]
        C = self._C(aes)
        ae_summary(C)
        self.assertLessEqual(len(C.aesum), 2 + 1)                     # 谱组数 ≤ IB 风险类别数 + 其他
        self.assertIn(self.OTHER, C.aesum)
        for k in C.aesum:
            self.assertIn(self.NOTE, k, k)
            self.assertFalse(k.startswith('IB重要潜在风险'), k)        # mm5 审阅 S8：按风险名分组，不按重要性分级
        ib_key = next(k for k in C.aesum if k.startswith('血小板减少'))
        self.assertEqual(C.aesum[ib_key]['n'], 2)
        self.assertTrue(any(k.startswith('中性粒细胞减少') for k in C.aesum))   # 「（同SOC）」后缀不另成一组
        self.assertEqual(C.aesum[self.OTHER]['n'], 7)                 # 无 IB 类别的原文术语全部归「其他」
        self.assertIn('头痛', C.aesum[self.OTHER]['terms'])
        for a in C.aes:                                               # AE 记录类别同步改写（安全页同一口径）
            self.assertIn(self.NOTE, a['c'])
            self.assertTrue(a['c'] != self.OTHER if a['ib'] else a['c'] == self.OTHER)

    def test_low_soc_ratio_still_fallback(self):
        from mm_build import ae_summary
        aes = [self._ae('头痛', soc='神经系统疾病')] + [self._ae(t) for t in ('皮疹', '恶心', '头晕', '乏力', '瘙痒', '咳嗽', '腹泻', '失眠', '心悸')]
        C = self._C(aes)                                              # 1/10 = 10% < 20% → 兜底
        ae_summary(C)
        self.assertEqual(list(C.aesum), [self.OTHER])
        for k in C.aesum:
            self.assertIn(self.NOTE, k)

    def test_with_soc_behavior_unchanged(self):
        from mm_build import ae_summary
        aes = [self._ae(t, soc='神经系统疾病') for t in ('头痛', '头晕', '失眠')] + \
              [self._ae(t, soc='胃肠疾病') for t in ('恶心', '腹泻')]
        C = self._C(aes)                                              # 5/5 全带 soc → 原行为：按类别（SOC）分组、无注明
        ae_summary(C)
        self.assertEqual(list(C.aesum), ['神经系统疾病', '胃肠疾病'])
        self.assertTrue(all(self.NOTE not in k for k in C.aesum))
        self.assertEqual([a['c'] for a in C.aes], ['神经系统疾病'] * 3 + ['胃肠疾病'] * 2)

    def test_boundary_exactly_20pct_unchanged(self):
        from mm_build import ae_summary
        aes = [self._ae('头痛', soc='神经系统疾病'), self._ae('头晕', soc='神经系统疾病')] + \
              [self._ae(t) for t in ('皮疹', '恶心', '头晕', '乏力', '瘙痒', '咳嗽', '腹泻', '失眠')]
        C = self._C(aes)                                              # 2/10 = 20%（未低于）→ 原行为
        ae_summary(C)
        self.assertTrue(all(self.NOTE not in k for k in C.aesum))

    def test_more_than_20_categories_capped(self):
        from mm_build import ae_summary
        aes = []
        for i in range(25):                                           # 25 个 IB 类别 → 前 19 ＋「其他」≤ 20 组
            aes += [self._ae(f'术语{i}甲', ib=[f'风险{i:02d}·术语{i}甲']), self._ae(f'术语{i}乙', ib=[f'风险{i:02d}·术语{i}乙'])]
        C = self._C(aes)
        ae_summary(C)
        self.assertLessEqual(len(C.aesum), 20)
        self.assertIn(self.OTHER, C.aesum)
        self.assertTrue(all(self.NOTE in k for k in C.aesum))


class KnowledgeStatePages(unittest.TestCase):
    """知识状态进数据面＋页面呈现（试用实证：AE 278/278 无器官归类、关联预判缺失，页面零提示——
    医生以为系统不会归类）。①构建后 KZ.knowledge＝study analysis.knowledge（键随数据面透传）；
    ②AE 谱兜底在真实构建链生效（演示数据全无 soc → 组名带注明）；③知识层呈现逻辑（研究依据页知识卡
    红/绿、总览警示条、query 页头提示、术语一致性按 PT 归并）为 kz.js 可单测纯函数（node 单测）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='mm4kn_'))
        ex = cls.tmp / 'ex'
        py = sys.executable
        subprocess.run([py, str(ROOT / 'scripts/make_demo.py'), '--out', str(ex)], check=True, capture_output=True)
        for f in (ROOT / 'examples/demo').glob('*.json'):
            shutil.copy(f, ex / f.name)
        S = json.loads((ex / 'study.json').read_text(encoding='utf-8'))
        S.setdefault('analysis', {})['knowledge'] = {'meddra_ok': False, 'meddra_version': '', 'ae_soc': 0,
                                                     'implausible': 0, 'plausible': 0, 'unknown': 0, 'degraded': True}
        S['analysis'].pop('aeCatMap', None)   # 试用实证场景＝无字典且无类别映射（有 aeCatMap 时维持用户口径，不兜底）
        (ex / 'study.json').write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding='utf-8')
        subprocess.run([py, str(ROOT / 'scripts/normalize_listing.py'), str(ex / 'mapping.json'), '--out', str(cls.tmp / 'norm')], check=True, capture_output=True)
        subprocess.run([py, str(ROOT / 'scripts/build_site.py'), '--study', str(ex / 'study.json'), '--norm', str(cls.tmp / 'norm'),
                        '--out', str(cls.tmp / 'out'), '--no-xlsx'], check=True, capture_output=True)
        cls.KZ = _load_kz(cls.tmp / 'out/HTML')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_knowledge_passthrough_to_data_plane(self):
        kn = self.KZ.get('knowledge')
        self.assertIsInstance(kn, dict)
        self.assertTrue(kn['degraded'])
        for k in ('meddra_ok', 'meddra_version', 'ae_soc', 'implausible', 'plausible', 'unknown'):
            self.assertIn(k, kn)

    def test_ae_spectrum_fallback_in_real_build(self):
        cat = self.KZ['aecat']
        self.assertTrue(cat, '演示构建应有 AE 谱组')
        self.assertLessEqual(len(cat), 21)
        note = '（未按器官系统——MedDRA 不可用）'
        for k in cat:
            self.assertIn(note, k)
        for a in self.KZ['aes']:
            if a['te']:                                               # 兜底只改写治疗期（与谱同口径）；首剂前行保留原类别
                self.assertIn(note, a['c'])

    def test_page_render_logic_node_unit(self):
        """kz.js 纯函数逻辑单测（node）：知识卡红/绿、警示条、query 页头提示、术语一致性按 PT 归并四态。"""
        r = subprocess.run(['node', str(ROOT / 'scripts/test_render_logic.js'), str(ROOT / 'templates/site/assets')],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, f'页面呈现逻辑单测失败：\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')


class DemoKnowledgeKeyAbsence(unittest.TestCase):
    """无 knowledge 键（旧构建）形态无扰：KZ 不出现 knowledge 键（golden/既有构建零扰动）。"""

    def test_demo_build_without_knowledge_key(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix='mm4nokn_'))
        try:
            ex = tmp / 'ex'
            py = sys.executable
            subprocess.run([py, str(ROOT / 'scripts/make_demo.py'), '--out', str(ex)], check=True, capture_output=True)
            for f in (ROOT / 'examples/demo').glob('*.json'):
                shutil.copy(f, ex / f.name)
            subprocess.run([py, str(ROOT / 'scripts/normalize_listing.py'), str(ex / 'mapping.json'), '--out', str(tmp / 'norm')], check=True, capture_output=True)
            subprocess.run([py, str(ROOT / 'scripts/build_site.py'), '--study', str(ex / 'study.json'), '--norm', str(tmp / 'norm'),
                            '--out', str(tmp / 'out'), '--no-xlsx'], check=True, capture_output=True)
            self.assertNotIn('knowledge', _load_kz(tmp / 'out/HTML'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DuplicateAePtLevel(unittest.TestCase):
    """用户裁定（2026-10-30，纠正旧口径）：AE 一致性核对以 MedDRA PT 为归并单位——
    风险＝同受试者＋时间重叠＋**不同 PT**（疑似重复记录或编码不一致，文案含两个 PT 名与原文写法）；
    同一 PT（含原文写法不同）视为同一 AE，不发；pt 缺失（字典降级）时该规则不运行（知识层降级状态可见）。
    旧口径「原文术语相等即发」废止：同 PT 两写法重叠（旧口径漏发）与同写法重叠（旧口径发）均不再发。"""

    @staticmethod
    def _ae(n, t, pt, s, e='', soc='各类检查'):
        return {'n': n, 't': t, 'pt': pt, 's': s, 'e': e, 'sh': 'AE', 'row': n, 'soc': soc}

    @staticmethod
    def _C(ae_by):
        from types import SimpleNamespace
        return SimpleNamespace(A={'aeChecks': ['duplicate']}, pop={'S1'}, subj={'S1': {'site': '01'}},
                               others=[], src={'sheets': {}}, F={}, aes=[], aesiDefs=[], ae_by=ae_by)

    def test_same_pt_two_spellings_overlap_not_flagged(self):
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, '甘油三酯升高', '高甘油三酯血症', '2026-05-01', '2026-05-10'),
                            self._ae(2, '甘油三酯高', '高甘油三酯血症', '2026-05-05')]})
        ae_checks(C)
        self.assertEqual([o for o in C.others if 'PT' in o['cat'] or '重复' in o['cat']], [])   # 同一 AE，不是风险

    def test_identical_term_overlap_no_longer_flagged(self):
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, '头痛', '头痛', '2026-02-05', '2026-02-09'),
                            self._ae(2, '头痛', '头痛', '2026-02-05', '2026-02-09')]})
        ae_checks(C)
        self.assertEqual(C.others, [])                                              # 旧 S31 口径废止

    def test_suspected_same_event_flagged_with_both_pt_names(self):
        """mm5 用户决定：同 SOC、术语相近（胆红素 ↔ 结合胆红素）、时间重叠 → 疑似同一事件重复记录或编码不一致。"""
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, '胆红素升高', '血胆红素升高', '2026-05-01', '2026-05-10'),
                            self._ae(2, '结合胆红素升高', '结合胆红素升高', '2026-05-05')]})
        ae_checks(C)
        hit = [o for o in C.others if o['cat'] == 'AE一致性核对（PT级）']
        self.assertEqual(len(hit), 1)
        self.assertIn('PT 级：血胆红素升高 vs 结合胆红素升高', hit[0]['sum'])
        self.assertIn('重复记录或编码不一致', hit[0]['sum'])

    def test_concurrent_different_events_not_flagged(self):
        """ALT 与 AST 同时升高、或不同 SOC 的并发 AE：是不同的 AE，不提示。"""
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, 'ALT升高', '丙氨酸氨基转移酶升高', '2026-05-01', '2026-05-10'),
                            self._ae(2, 'AST升高', '天门冬氨酸氨基转移酶升高', '2026-05-05'),
                            self._ae(3, '头痛', '头痛', '2026-05-06', soc='各类神经系统疾病')]})
        ae_checks(C)
        self.assertEqual([o for o in C.others if o['cat'] == 'AE一致性核对（PT级）'], [])

    def test_missing_pt_rule_does_not_run(self):
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, '皮疹', '', '2026-05-01', '2026-05-10'),
                            self._ae(2, '瘙痒', '', '2026-05-05')]})                # 字典降级：无 pt
        ae_checks(C)
        self.assertEqual(C.others, [])                                              # 不运行，不按原文术语冒充判定

    def test_non_overlapping_different_pt_not_flagged(self):
        from mm_build import ae_checks
        C = self._C({'S1': [self._ae(1, '上呼吸道感染', '上呼吸道感染', '2026-05-01', '2026-05-10'),
                            self._ae(2, '流行性感冒', '流行性感冒', '2026-06-01')]})   # 时间不重叠
        ae_checks(C)
        self.assertEqual(C.others, [])


class UnitSciNotation(unittest.TestCase):
    """单位科学计数归一（SAR 实测：norm 单位 ×10^9/L 4661、x10^9/L 1942、*10^9/L 331 混存；星号形态在复制/导出链
    被吞成「610^9/L」）：normalize 一处收口——运算符（大小写 x/X、全半角乘号、＊✕⨯ 及其与数字间的空格）统一为 ×，
    数字直接粘 10^（乘号已丢的成品形态）补 ×；裸 10^ 前缀口径保留。程序文案 raw+unit 无分隔拼接（CSX/MH/NA2 等
    模板 {raw}{unit}）因此自然正确——用例一并锁定。"""

    @staticmethod
    def _rows(units):
        import openpyxl
        from normalize_listing import Book, findings
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'PLT'
        ws.append(['受试者编号', '访视', '检查日期', '检查项', '检查结果', '单位'])
        for i, u in enumerate(units, 1):
            ws.append(['S1', f'V{i}', '2026-05-01', '血小板计数', '40', u])
        M = {'workbooks': {'edc': 'x'}, 'domains': {}}
        spec = {'wb': 'edc', 'sheet': 'PLT', 'domain': 'lab', 'group': '血常规', 'label_row': 1, 'var_row': 0, 'data_start': 2,
                'cols': {'sid': '受试者编号', 'visit': '访视', 'date': '检查日期', 'test': '检查项', 'value': '检查结果', 'unit': '单位'}}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'edc.xlsx'
            wb.save(p)
            return [r.get('unit') for r in findings(spec, {'edc': Book(str(p))}, M)]

    def test_operator_variants_unified(self):
        units = self._rows(['*10^9/L', 'x10^9/L', 'X10^9/L', '×10^9/L', '＊10^9/L', 'ｘ10^9/L', '✕10^9/L', 'x 10^9/L'])
        self.assertEqual(units, ['×10^9/L'] * len(units), units)
        self.assertEqual(self._rows(['3 * 10^9/L']), ['3×10^9/L'])       # 带系数写法：系数保留、运算符归 ×

    def test_digit_stuck_10caret_repaired(self):
        units = self._rows(['310^9/L', '4010^9/L'])
        self.assertEqual(units, ['3×10^9/L', '40×10^9/L'], units)

    def test_bare_prefix_and_plain_units_unchanged(self):
        self.assertEqual(self._rows(['10^9/L']), ['×10^9/L'])            # 既有裸前缀口径不破
        self.assertEqual(self._rows(['g/L', 'mmHg', '109/L']), ['g/L', 'mmHg', '109/L'])   # 无 10^ 迹象的单位不碰

    def test_program_text_splice_safe(self):
        """程序文案 raw+unit 无分隔拼接（{raw}{unit}）在归一后不产生「数字直接粘 10^」。"""
        import re
        for raw, unit in [('40', '×10^9/L'), ('6', '×10^9/L'), ('3', '3×10^9/L')]:
            text = f'{raw}{unit}'                                        # 与 mm_build CSX/MH/NA2 模板同一拼接形态
            self.assertFalse(re.search(r'\d10\^', text), text)
            self.assertIn('×10^', text)


def _cons_row(sid, val, clin, *, hi=None, lo=None, post=True, visit='V2', date='2026-05-01', unit='U/L',
              links=(), reason=None, sheet='LAB', row=1):
    """虚构检验行：clin 1=NCS、2=CS；links＝检验页关联编号（归因依据）；reason＝CS 原因码。"""
    return {'sid': sid, 'value': val, 'clin': clin, 'hi': hi, 'lo': lo, 'post': post, 'visit': visit,
            'date': date, 'raw': f'{val:g}', 'unit': unit, 'sheet': sheet, 'row': row,
            'links': list(links), 'reason': reason}


def _cons_C(rows, mid='lab:ALT', label='ALT', A=None):
    """build_cons 最小夹具：单指标、同中心 01、全部计划内访视。"""
    from types import SimpleNamespace
    from mm_build import build_cons
    F = {}
    for r in rows:
        F.setdefault((r['sid'], mid), []).append(r)
    C = SimpleNamespace(A=A or {}, F=F, queries=[], isAgg=lambda v: True,
                        metric={mid: {'id': mid, 'label': label}},
                        subj={s: {'site': '01'} for s in {r['sid'] for r in rows}},
                        pop={r['sid'] for r in rows})
    build_cons(C)
    return C


class ConsDirectionalRecore(unittest.TestCase):
    """判定一致性换芯＋同受试者版（用户 2026-10-30 三点修正终版；旧「±5% 相近即双向报」废止）：
    a. 判定维度（方向性）：可比对＝同受试者（新增）或同中心跨受试者（换芯）×同指标/单位/参考范围×
       同向异常（都超参考范围同向；一升一降不可比）×同给药阶段（给药前不与给药后比）——更差者
       （偏离参考边界更远，相对偏离度、无最小差阈值）判 NCS 而更轻者判 CS → 发；更差者判 CS → 不发；
       数值相等而判定不同 → 发（无更差方可定向，判定不同即不一致）。
    b. 归因维度（无方向不排序）：两条均 CS 且归因不同（AE/MH/研究疾病/未关联 任一不同）→ 发归因不一致。
    数据面 C.cons 带 scope（center/subject）与 kind（judg/att）。夹具全虚构。"""

    _r = staticmethod(_cons_row)
    _C = staticmethod(_cons_C)

    def test_center_worse_ncs_lighter_cs_flagged(self):
        C = self._C([self._r('S1', 50, 2, hi=40), self._r('S2', 80, 1, hi=40)])
        hit = [c for c in C.cons if c.get('scope') == 'center' and c.get('kind') == 'judg']
        self.assertEqual(len(hit), 1)
        self.assertEqual((hit[0]['a'], hit[0]['b']), ('S1', 'S2'))   # a＝更轻仍判 CS；b＝更差却判 NCS

    def test_center_worse_judged_cs_not_flagged(self):
        C = self._C([self._r('S1', 80, 2, hi=40), self._r('S2', 50, 1, hi=40)])
        self.assertEqual([c for c in C.cons if c.get('kind') == 'judg'], [])   # 更差者已判 CS：无风险

    def test_equal_value_different_judgment_flagged(self):
        C = self._C([self._r('S1', 60, 2, hi=40), self._r('S2', 60, 1, hi=40)])
        self.assertEqual(len([c for c in C.cons if c.get('kind') == 'judg']), 1)   # 数值相等判定不同 → 发

    def test_micro_gap_flagged_no_min_threshold(self):
        # V6（MM 审阅＋用户 2026-11-02「没做的一并做了」）：默认最小差值 5 个百分点（analysis.consMinDiff），0＝10-30 旧口径
        C = self._C([self._r('S1', 40.3, 2, hi=40), self._r('S2', 40.55, 1, hi=40)])
        self.assertEqual([c for c in C.cons if c.get('kind') == 'judg'], [])        # 0.6% 量级微差默认不发
        C = self._C([self._r('S1', 40.3, 2, hi=40), self._r('S2', 40.55, 1, hi=40)], A={'consMinDiff': 0})
        self.assertEqual(len([c for c in C.cons if c.get('kind') == 'judg']), 1)   # 配置为 0 时恢复旧口径

    def test_far_gap_still_flagged_tolerance_gate_abolished(self):
        C = self._C([self._r('S1', 42, 2, hi=40), self._r('S2', 100, 1, hi=40)])   # 相差远超旧 ±5% 门槛
        self.assertEqual(len([c for c in C.cons if c.get('kind') == 'judg']), 1)   # 方向性口径：仍发

    def test_opposite_directions_not_comparable(self):
        C = self._C([self._r('S1', 80, 2, hi=40), self._r('S2', 30, 1, lo=35)])    # 一升一降
        self.assertEqual(C.cons, [])

    def test_pre_vs_post_not_compared(self):
        C = self._C([self._r('S1', 80, 2, hi=40, post=True), self._r('S2', 90, 1, hi=40, post=False)])
        self.assertEqual(C.cons, [])                                 # 给药前不与给药后比
        C = self._C([self._r('S1', 60, 2, hi=40, post=False), self._r('S2', 80, 1, hi=40, post=False)])
        self.assertEqual(len([c for c in C.cons if c.get('kind') == 'judg']), 1)   # 同为给药前：可比

    def test_center_attribution_inconsistency(self):
        ae = {'type': 'AE', 'no': 1, 'term': '虚构AE'}
        C = self._C([self._r('S1', 60, 2, hi=40, links=[ae]), self._r('S2', 62, 2, hi=40)])
        hit = [c for c in C.cons if c.get('kind') == 'att']
        self.assertEqual(len(hit), 1)                                # 均 CS、归因不同（AE vs 未关联）
        self.assertIn('归因', hit[0]['diff'] + hit[0]['why'])

    def test_center_attribution_same_not_flagged(self):
        ae = {'type': 'AE', 'no': 1, 'term': '虚构AE'}
        C = self._C([self._r('S1', 60, 2, hi=40, links=[ae]), self._r('S2', 62, 2, hi=40, links=[ae])])
        self.assertEqual([c for c in C.cons if c.get('kind') == 'att'], [])        # 归因相同：不发

    def test_subject_scope_judgment_flagged(self):
        C = self._C([self._r('S1', 50, 2, hi=40, visit='V2', row=1),
                     self._r('S1', 80, 1, hi=40, visit='V3', row=2)])
        hit = [c for c in C.cons if c.get('scope') == 'subject' and c.get('kind') == 'judg']
        self.assertEqual(len(hit), 1)                                # 同受试者版（新增）

    def test_subject_scope_attribution_flagged(self):
        ae = {'type': 'AE', 'no': 1, 'term': '虚构AE'}
        C = self._C([self._r('S1', 55, 2, hi=40, visit='V2', row=1, links=[ae]),
                     self._r('S1', 58, 2, hi=40, visit='V3', row=2)])
        hit = [c for c in C.cons if c.get('scope') == 'subject' and c.get('kind') == 'att']
        self.assertEqual(len(hit), 1)                                # 同受试者两次 CS 归因不同


class ClinConsDirectionalQuery(unittest.TestCase):
    """「临床意义判定不一致」query 换芯（方向性＋归因维度，同受试者口径）：
    更差判 NCS、更轻判 CS → 发（文案含方向）；更差者判 CS → 不发；数值相同判定不同 → 发；
    两条均 CS 归因不同 → 发归因不一致。一升一降、给药前 vs 给药后 → 不可比不发。夹具全虚构。"""

    def _run(self, rows):
        from types import SimpleNamespace
        import ext_rules
        F = {}
        for r in rows:
            F.setdefault((r['sid'], 'lab:HGB'), []).append(r)
        C = SimpleNamespace(A={}, F=F, queries=[], isAgg=lambda v: True,
                            metric={'lab:HGB': {'id': 'lab:HGB', 'label': '血红蛋白'}},
                            subj={s: {'site': '01'} for s in {r['sid'] for r in rows}},
                            pop={r['sid'] for r in rows}, others=[], src={'sheets': {}})
        ext_rules.clin_consistency(C)
        return C

    @staticmethod
    def _q(C):
        return [o for o in C.others if o['cat'] == '临床意义判定不一致']

    def test_worse_ncs_lighter_cs_query(self):
        C = self._run([_cons_row('S1', 90, 2, hi=60, visit='V2', date='2026-05-01', row=1),
                       _cons_row('S1', 120, 1, hi=60, visit='V3', date='2026-06-01', row=2)])
        q = self._q(C)
        self.assertEqual(len(q), 1)
        self.assertIn('离正常范围更远', q[0]['sum'])                           # 方向性文案：更差者判 NCS

    def test_worse_judged_cs_no_query(self):
        C = self._run([_cons_row('S1', 120, 2, hi=60, visit='V2', row=1),
                       _cons_row('S1', 90, 1, hi=60, visit='V3', row=2)])
        self.assertEqual(self._q(C), [])                             # 更差者已判 CS：不发

    def test_equal_value_different_judgment_query(self):
        C = self._run([_cons_row('S1', 100, 2, hi=60, visit='V2', row=1),
                       _cons_row('S1', 100, 1, hi=60, visit='V3', row=2)])
        q = self._q(C)
        self.assertEqual(len(q), 1)
        self.assertIn('相同', q[0]['sum'])                           # 数值相同判定不同 → 发

    def test_attribution_differs_query(self):
        ae, mh = {'type': 'AE', 'no': 1, 'term': '虚构AE'}, {'type': 'MH', 'no': 2, 'term': '虚构病史'}
        C = self._run([_cons_row('S1', 95, 2, hi=60, visit='V2', row=1, links=[ae]),
                       _cons_row('S1', 96, 2, hi=60, visit='V3', row=2, links=[mh])])
        q = self._q(C)
        self.assertEqual(len(q), 1)
        self.assertIn('归因', q[0]['sum'])                           # 归因维度：AE vs MH

    def test_mh_then_ae_attribution_not_inconsistent(self):
        # V6 R7：先归因病史、后归因 AE（病史基础上加重记 AE）是正常记录方式
        ae, mh = {'type': 'AE', 'no': 1, 'term': '虚构AE'}, {'type': 'MH', 'no': 2, 'term': '虚构病史'}
        C = self._run([_cons_row('S1', 95, 2, hi=60, visit='V2', row=1, links=[mh], date='2026-04-01'),
                       _cons_row('S1', 96, 2, hi=60, visit='V3', row=2, links=[ae], date='2026-05-01')])
        self.assertEqual(self._q(C), [])

    def test_opposite_direction_no_query(self):
        C = self._run([_cons_row('S1', 120, 2, hi=60, visit='V2', row=1),
                       _cons_row('S1', 50, 1, lo=70, visit='V3', row=2)])
        self.assertEqual(self._q(C), [])                             # 一升一降不可比

    def test_pre_vs_post_no_query(self):
        C = self._run([_cons_row('S1', 120, 2, hi=60, visit='V2', row=1, post=True),
                       _cons_row('S1', 130, 1, hi=60, visit='V3', row=2, post=False)])
        self.assertEqual(self._q(C), [])                             # 给药前不与给药后比


class _SynthXlsx:
    """纯合成 xlsx 夹具（zipfile 手写 XML，零真实数据）：可注入非法 autoFilter 与截断 dimension。"""

    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    @classmethod
    def _col(cls, i):
        s, i = '', i + 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    @classmethod
    def _sheet_xml(cls, rows, dimension, autofilter):
        body = []
        for ri, r in enumerate(rows, 1):
            cells = ''.join(
                f'<c r="{cls._col(ci)}{ri}"><v>{v}</v></c>' if isinstance(v, (int, float))
                else f'<c r="{cls._col(ci)}{ri}" t="inlineStr"><is><t>{v}</t></is></c>'
                for ci, v in enumerate(r))
            body.append(f'<row r="{ri}">{cells}</row>')
        af = f'<autoFilter ref="{autofilter}"/>' if autofilter else ''
        return (f'<worksheet xmlns="{cls.NS}"><dimension ref="{dimension}"/>'
                f'<sheetData>{"".join(body)}</sheetData>{af}</worksheet>')

    @classmethod
    def build(cls, path, sheets):
        """sheets: [(sheet_name, dimension_ref, autofilter_ref|None, rows)]"""
        import zipfile
        overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1))
        ct = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              f'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              f'<Default Extension="xml" ContentType="application/xml"/>'
              f'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              f'{overrides}</Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')
        tags = ''.join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{9 + i}"/>' for i, (n, *_r) in enumerate(sheets, 1))
        wb = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<workbook xmlns="{cls.NS}" xmlns:r="{cls.RNS}"><sheets>{tags}</sheets></workbook>')
        wbr = ''.join(
            f'<Relationship Id="rId{9 + i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1))
        wbr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{wbr}</Relationships>')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', ct)
            z.writestr('_rels/.rels', rels)
            z.writestr('xl/workbook.xml', wb)
            z.writestr('xl/_rels/workbook.xml.rels', wbr)
            for i, (_n, dim, af, rows) in enumerate(sheets, 1):
                z.writestr(f'xl/worksheets/sheet{i}.xml', cls._sheet_xml(rows, dim, af))


class XlsxTaintTolerance(unittest.TestCase):
    """PLAN §21 P1：EDC 全量导出常带非法 autoFilter（ref="1:1"，65/66 表命中）＋截断 dimension（A1）——
    普通模式 load_workbook 抛 ValueError、read_only 静默每表只读声明行数（近空读）。
    xlsx 读取入口必须宁可慢也要读全：回退普通模式；普通模式仍抛错则 zipfile 副本剥离非法 autoFilter
    后再读，并留含表名与回退原因的日志。夹具全合成（zipfile 手写），不进仓库。"""

    ROWS = [['受试者编号', '不良事件名称', '开始日期'],
            ['SUBJID', 'AETERM', 'AESTDAT'],
            ['S001', '头痛', '2026-05-01'],
            ['S002', '恶心', '2026-05-02'],
            ['S001', '皮疹', '2026-05-03']]

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix='mm_test_xlsx_'))
        _SynthXlsx.build(cls.dir / 'tainted.xlsx', [('AE', 'A1:A1', '1:1', cls.ROWS)])       # 双伤
        _SynthXlsx.build(cls.dir / 'dim_only.xlsx', [('LBHEMA', 'A1:A1', None, cls.ROWS)])   # 仅维度截断
        _SynthXlsx.build(cls.dir / 'clean.xlsx', [('DM', 'A1:C5', 'A1:C1', cls.ROWS)])       # 正常（合法 AF＋真实维度）

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_fixture_reproduces_both_symptoms(self):
        """夹具自证（修前行为快照）：普通模式抛 ValueError；read_only 静默只读 1 行。"""
        import openpyxl
        with self.assertRaises(ValueError):
            openpyxl.load_workbook(self.dir / 'tainted.xlsx')
        wb = openpyxl.load_workbook(self.dir / 'tainted.xlsx', read_only=True, data_only=True)
        self.assertEqual(len(list(wb['AE'].iter_rows(values_only=True))), 1)
        wb.close()

    def test_non_xlsx_zip_not_crashing_taint(self):
        """zip 但非 xlsx（如 docx 误入工作簿位，判例 D002 CLI inspect 把方案 docx 一并喂入）：
        xlsx_taint 返回 []（交 openpyxl 报它自己的错），不得 KeyError 崩溃。"""
        import zipfile
        from common import xlsx_taint, open_workbook_lenient
        p = self.dir / 'notxlsx.zip'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
            z.writestr('word/document.xml', '<?xml version="1.0"?><document/>')
        self.assertEqual(xlsx_taint(p), [])                     # 修前 KeyError（红）
        with self.assertRaises(Exception) as cm:                # openpyxl 自己的报错（非 KeyError）
            open_workbook_lenient(p, read_only=True, data_only=True)
        self.assertNotIsInstance(cm.exception, KeyError)

    def test_tainted_reads_all_rows_with_fallback_log(self):
        from common import open_workbook_lenient
        notes = []
        wb, ns = open_workbook_lenient(self.dir / 'tainted.xlsx', log=notes.append)
        rows = list(wb['AE'].iter_rows(values_only=True))
        self.assertEqual(len(rows), 5)
        self.assertEqual([rows[2][0], rows[4][1]], ['S001', '皮疹'])
        blob = '\n'.join(notes + ns)
        self.assertIn('AE', blob)                      # 表名
        self.assertIn('回退', blob)                     # 回退原因可见
        wb.close()

    def test_truncated_dimension_only_reads_all(self):
        from common import open_workbook_lenient
        notes = []
        wb, ns = open_workbook_lenient(self.dir / 'dim_only.xlsx', log=notes.append)
        self.assertEqual(len(list(wb['LBHEMA'].iter_rows(values_only=True))), 5)
        blob = '\n'.join(notes + ns)
        self.assertIn('LBHEMA', blob)
        self.assertIn('回退', blob)
        wb.close()

    def test_clean_file_unaffected(self):
        """回归守卫：正常文件（合法 autoFilter A1:C1＋真实维度）零回退、read_only 照常。"""
        from common import open_workbook_lenient
        notes = []
        wb, ns = open_workbook_lenient(self.dir / 'clean.xlsx', log=notes.append)
        self.assertEqual(ns, [])
        self.assertEqual(notes, [])
        self.assertEqual(len(list(wb['DM'].iter_rows(values_only=True))), 5)
        wb.close()

    def test_normalize_listing_book_reads_all(self):
        """P1 主隐患路径：normalize_listing.Book 近空读 → 全量读。修前 data=0 行（红），修后 3 行。"""
        from normalize_listing import Book
        notes = []
        book = Book(str(self.dir / 'tainted.xlsx'), log=notes.append)
        labels, vars_, data = book.sheet('AE', 1, 2, 3)
        self.assertEqual(labels, ['受试者编号', '不良事件名称', '开始日期'])
        self.assertEqual(vars_, ['SUBJID', 'AETERM', 'AESTDAT'])
        self.assertEqual(len(data), 3)
        self.assertIn('AE', '\n'.join(notes))



class F02DescLinkForms(unittest.TestCase):
    """RUX 深审 F02：检验「异常有临床意义请说明」列的关联引用写法——编号型 MHn#术语 / MH#n / AEn#术语 / AEn（无#）
    此前 parse_links 已识别但术语带 #、且 desc 列从未参与解析；词目型「XX既往史」「与XX有关/相关」完全不识别
    → ~230 条「CS未关联」误报。六类写法与既有圆括号格式（AE (5) 术语）共存。夹具全虚构。"""

    def test_hash_term_stripped_in_numbered_forms(self):
        self.assertEqual(parse_links('MH3#血脂升高'), [['MH', '血脂升高', None, 3]])
        self.assertEqual(parse_links('AE2#恶心'), [['AE', '恶心', None, 2]])
        self.assertEqual(parse_links('MH＃4 高脂血症'), [['MH', '高脂血症', None, 4]])   # 全角＃
        self.assertEqual(parse_links('AE (5) 头痛'), [['AE', '头痛', None, 5]])          # 圆括号格式不破

    def test_numbered_forms_directly(self):
        self.assertEqual(parse_links('MH#3'), [['MH', '', None, 3]])
        self.assertEqual(parse_links('AE#3'), [['AE', '', None, 3]])
        self.assertEqual(parse_links('AE2'), [['AE', '', None, 2]])
        self.assertEqual(parse_links('MH12'), [['MH', '', None, 12]])

    def test_desc_term_links_history_noun(self):
        from common import parse_desc_links
        self.assertEqual(parse_desc_links('脂肪肝病史'), [['MH', '脂肪肝', None, None]])
        self.assertEqual(parse_desc_links('病史高脂血症'), [['MH', '高脂血症', None, None]])
        self.assertEqual(parse_desc_links('贫血既往史'), [['MH', '贫血', None, None]])

    def test_desc_term_links_related(self):
        from common import parse_desc_links
        self.assertEqual(parse_desc_links('与脂肪肝相关'), [['MH', '脂肪肝', None, None]])
        self.assertEqual(parse_desc_links('CS，与脂肪肝相关'), [['MH', '脂肪肝', None, None]])
        self.assertEqual(parse_desc_links('与"胆红素升高"既往史有关'), [['MH', '胆红素升高', None, None]])
        self.assertEqual(parse_desc_links('与既往史"胆红素升高"有关'), [['MH', '胆红素升高', None, None]])
        self.assertEqual(parse_desc_links('敏感；与疖肿AE相关'), [['AE', '疖肿', None, None]])
        self.assertEqual(parse_desc_links('与不良事件「皮疹」有关'), [['AE', '皮疹', None, None]])

    def test_desc_non_links_rejected(self):
        from common import parse_desc_links
        self.assertEqual(parse_desc_links('与病史相关'), [])          # 无词目：留「未关联」待澄清
        self.assertEqual(parse_desc_links('与AD相关'), [])            # 研究疾病缩写归 disease_attr，不造 MH 关联
        self.assertEqual(parse_desc_links('AD相关'), [])
        # 疾病指代带限定词（SAR/RUX 实测「CS与本研究疾病相关」曾整体被抽成词目，抢走研究疾病归因）
        self.assertEqual(parse_desc_links('与本研究疾病相关'), [])
        self.assertEqual(parse_desc_links('CS与本研究疾病相关'), [])
        self.assertEqual(parse_desc_links('与基础疾病有关'), [])
        self.assertEqual(parse_desc_links('与研究疾病加重有关'), [])
        self.assertEqual(parse_desc_links('与慢性阻塞性肺疾病相关'), [['MH', '慢性阻塞性肺疾病', None, None]])  # 具体病史词不受限
        # 尾部关键字吞并与原发病指代（RUX 实测「（AD病史相关）」「（CS，病史相关）」「与原发病AD相关」）
        self.assertEqual(parse_desc_links('肘窝苔藓化（AD病史相关）'), [])
        self.assertEqual(parse_desc_links('（CS，病史相关）'), [])
        self.assertEqual(parse_desc_links('与原发病AD相关'), [])
        self.assertEqual(parse_desc_links('既往史：剖腹产手术史'), [['MH', '剖腹产手术史', None, None]])  # 正常「…史」词目不受累
        self.assertEqual(parse_desc_links('NCS'), [])
        self.assertEqual(parse_desc_links('T-SPOT.TB试验'), [])
        self.assertEqual(parse_desc_links(''), [])

    def test_term_link_resolution_backfills_number(self):
        """词目型关联在 AE/MH 记录里对上术语 → 回填编号、视作已关联；对不上 → 保持未关联（l[4]=False）。"""
        from types import SimpleNamespace
        from mm_build import resolve_links
        C = SimpleNamespace(ae_by={'S1': [{'n': '3', 't': '皮疹', 's': '2026-01-01'}]},
                            mh_by={'S1': [{'n': '2', 't': '缺铁性贫血', 's': '2020-01-01'}]})
        out = resolve_links(C, 'S1', [['MH', '贫血', None, None], ['AE', '脂肪肝', None, None]])
        self.assertEqual(out[0], ['MH', '贫血', '2020-01-01', '2', True])     # 「贫血」⊂「缺铁性贫血」→ 回填 #2
        self.assertEqual(out[1][3], None) and self.assertFalse(out[1][4])     # 对不上：保持未关联

    def test_m23_unmatched_term_link_not_link_mismatch(self):
        """说明列词目型引用对不上记录：不发「关联的AE/病史不对应」，回到未关联口径（不出现编号 None）。"""
        from types import SimpleNamespace
        import ext_rules
        row = {'sid': 'S1', 'value': 90, 'clin': 2, 'hi': 60, 'lo': None, 'post': True, 'visit': 'V2',
               'date': '2026-05-01', 'raw': '90', 'unit': 'U/L', 'sheet': 'LAB', 'row': 3,
               'links': [['MH', '脂肪肝', None, None]], 'reason': None, 'mid': 'lab:ALT', 'base': None,
               'grade': 0, 'oor': True}
        C = SimpleNamespace(A={}, F={('S1', 'lab:ALT'): [row]}, metric={'lab:ALT': {'label': 'ALT'}},
                            subj={'S1': {'site': '01'}}, pop={'S1'}, others=[], src={'sheets': {},
                                                                                       'sheets_by_name': {}},
                            ae_by={'S1': []}, mh_by={'S1': []}, mhMatch=[], cfg={'thresholds': {'base': 0.3}},
                            S={'study': {}}, queries=[], isAgg=lambda v: True, extq=[], labrows=[],
                            indBg=[], aeEnd={}, ibtag={})
        ext_rules.m23_csb(C)
        self.assertEqual([o['sum'] for o in C.others if '不对应' in o['cat']], [])
        self.assertTrue(all('None' not in o['sum'] for o in C.others))

    def test_findings_desc_parsed_into_links(self):
        import tempfile
        import openpyxl
        from normalize_listing import Book, findings
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'lb.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'LB'
            ws.append(['受试者编号', '访视', '检查日期', '检查项', '检查结果', '临床意义', '异常有临床意义，请说明'])
            ws.append(['S1', '筛选期', '2026-05-01', '总胆红素', '27.9', '异常有临床意义', 'MH2'])
            ws.append(['S1', '筛选期', '2026-05-01', '直接胆红素', '8.5', '异常有临床意义', '与"胆红素升高"既往史有关'])
            ws.append(['S1', '筛选期', '2026-05-01', '白蛋白', '43', '异常无临床意义', ''])
            wb.save(p)
            M = {'workbooks': {'edc': str(p)},
                 'clin_map': [['异常无临床意义', 1], ['异常有临床意义', 2], ['正常', 0]],
                 'domains': {}}
            spec = {'wb': 'edc', 'sheet': 'LB', 'domain': 'lab', 'group': '血生化', 'label_row': 1, 'var_row': 0,
                    'data_start': 2,
                    'cols': {'sid': '受试者编号', 'visit': '访视', 'date': '检查日期', 'test': '检查项',
                             'value': '检查结果', 'clin': '临床意义', 'desc': '异常有临床意义，请说明'}}
            rows = findings(spec, {'edc': Book(str(p))}, M)
            by = {r['test']: r for r in rows}
            self.assertEqual(by['总胆红素']['links'], [['MH', '', None, 2]])            # 编号型来自 desc
            self.assertIn('link', by['总胆红素']['reason'] or '')                        # 原因码联动
            self.assertEqual(by['直接胆红素']['links'], [['MH', '胆红素升高', None, None]])  # 词目型来自 desc
            self.assertEqual(by['白蛋白']['links'], [])


class F01BoolFlagColumns(unittest.TestCase):
    """RUX 深审 F01①：UNS「计划外访视询问」整表是页面完成标志清单（0/1 勾选形态），「研究者整体评分」等
    列被指标正则采集为 IGA 评分。采集层通用判据：值域⊂{0,1,是,否} 且（列名含 是否/完成/勾选 或 同表多数
    测试列同为勾选形态）→ 非数值指标，不采集。夹具全虚构。"""

    @staticmethod
    def _run(tests, data, layout='wide'):
        import tempfile
        import openpyxl
        from normalize_listing import Book, findings
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'uns.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'UNS'
            ws.append(list(tests))
            for r in data:
                ws.append(r)
            wb.save(p)
            M = {'workbooks': {'edc': str(p)}, 'domains': {}}
            spec = {'wb': 'edc', 'sheet': 'UNS', 'domain': 'vs', 'group': 'UNS', 'label_row': 1, 'var_row': 0,
                    'data_start': 2, 'layout': layout}
            if layout == 'wide':
                spec['cols'] = {'sid': '受试者编号', 'visit': '访视名称'}
                spec['tests'] = tests_extra = {k: {'value': k} for k in tests[2:]}
            else:
                spec['cols'] = {'sid': '受试者编号', 'visit': '访视名称', 'test': '检查项', 'value': '检查结果'}
            return findings(spec, {'edc': Book(str(p))}, M)

    def test_uns_page_checklist_not_metrics(self):
        tests = ['受试者编号', '访视名称', '研究者整体评分', '受累体表面积', '湿疹评分', '身高采集', '拍照']
        rows = self._run(tests, [['S1', '计划外访视(2026-05-01)', 1, 0, 1, 0, 1]])
        self.assertEqual(rows, [])                                   # 整表完成标志：一列都不作指标

    def test_real_metric_among_flags_kept(self):
        tests = ['受试者编号', '访视名称', '体重', '拍照', '心电图采集']
        rows = self._run(tests, [['S1', 'V1', 62.5, 0, 1], ['S1', 'V2', 63.0, 0, 0]])
        self.assertEqual([r['test'] for r in rows], ['体重', '体重'])
        self.assertEqual(rows[0]['value'], 62.5)

    def test_label_hint_boolean_dropped_even_alone(self):
        tests = ['受试者编号', '访视名称', '体重', '是否完成IGA评估']
        rows = self._run(tests, [['S1', 'V1', 62.5, 1]])
        self.assertEqual([r['test'] for r in rows], ['体重'])        # 列名含「是否…」＋0/1 → 勾选列

    def test_long_layout_named_flag_dropped(self):
        tests = ['受试者编号', '访视名称', '检查项', '检查结果']
        rows = self._run(tests, [['S1', 'V1', '是否完成随访', 1], ['S1', 'V1', '尿酸', '424']],
                         layout='long')
        self.assertEqual([r['test'] for r in rows], ['尿酸'])

    def test_elig_pool_excludes_undated_unscheduled(self):
        """F01②：无日期的计划外访视行不入「入组前」池（入排评估池仅含筛选/基线与有日期的计划外复查）。"""
        from types import SimpleNamespace
        from mm_build import _elig_pool
        C = SimpleNamespace(subj={'S1': {'rand_d': '2026-06-01', 'fd': '2026-06-01'}}, cfg={}, VIS=[], UNS=set())

        def row(visit, date, val):
            return {'sid': 'S1', 'visit': visit, 'date': date, 'value': val, 'post': False}
        rows = [row('筛选期', '2026-05-20', 3), row('计划外访视(2024-08-20)', None, 0), row('计划外访视(2026-05-21)', '2026-05-21', 2)]
        pool = _elig_pool(C, 'S1', rows, {})
        self.assertEqual([r['value'] for r in pool], [3, 2])         # 无日期的计划外行不入池；有日期的复查保留


class F03SaeCheckbox(unittest.TestCase):
    """RUX 深审 F03：SAE 标准勾选列取 1/0 编码（0=未勾、1=勾选），按「是/否」字面校验时空判「均未勾选」。
    normalize 自动采集 SAE 标准勾选（致死/危及生命/住院/致残/先天异常/其他重要事件；「请说明」列不算），
    勾选域取值归一 1/是/true/Y→勾选；build 透传 sae_crit，M20 不再空判。夹具全虚构。"""

    def test_normalize_collects_sae_crit(self):
        import tempfile
        import openpyxl
        from normalize_listing import Book, read_spec
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'ae.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'AE'
            ws.append(['受试者编号', '访视名称', '不良事件名称', '是否为严重不良事件（SAE）？',
                       '导致死亡', '危及生命', '需要住院治疗或者延长住院时间', '先天性异常或者出生缺陷', '其他重要医学事件，请说明'])
            ws.append(['S1', '共同页', '肺炎', '是', 0, 0, 1, 0, ''])
            ws.append(['S1', '共同页', '骨折', '是', 0, 0, 0, 0, ''])
            wb.save(p)
            spec = {'wb': 'edc', 'sheet': 'AE', 'label_row': 1, 'var_row': 0, 'data_start': 2,
                    'cols': {'sid': '受试者编号', 'term': '访视名称', 'serious': '是否为严重不良事件（SAE）？'}}
            recs = [rec for rec, *_ in read_spec(spec, {'edc': Book(str(p))}, {'workbooks': {'edc': str(p)}, 'domains': {}})]
            self.assertEqual(recs[0].get('sae_crit'), '需要住院治疗或者延长住院时间')
            self.assertEqual(recs[1].get('sae_crit', ''), '')

    def test_m20_no_query_when_crit_checked(self):
        from types import SimpleNamespace
        from ext_rules import m20_ae_sae
        C = SimpleNamespace(pop={'S1'}, subj={'S1': {'site': '01', 'eos_d': ''}}, others=[], src={'sheets': {}}, F={},
                            exposure=[], visits=[],
                            aes=[{'sid': 'S1', 't': '肺炎', 's': '2026-05-01', 'e': '', 'sae': True, 'sae_crit': '住院',
                                  'sh': 'AE', 'row': 2, 'n': 1, 'wb': '', 'out': '好转'}])
        m20_ae_sae(C)
        self.assertEqual([o for o in C.others if 'SAE' in o['cat']], [])     # 勾选了住院标准：不再空判「均未勾选」

    def test_build_events_passes_sae_crit(self):
        from types import SimpleNamespace
        from mm_build import build_events
        C = SimpleNamespace(A={}, subj={'S1': {'site': '01', 'fd': '2026-05-01'}}, teEnd={},
                            ae=[{'sid': 'S1', 'term': '肺炎', 'pt': '肺炎', 'start': '2026-05-01', 'row': 2,
                                 'sheet': 'AE', 'serious': '是', 'sae_crit': '住院', 'rel': ''}], mh=[], cm=[])
        build_events(C)
        self.assertEqual(C.aes[0]['sae_crit'], '住院')
        self.assertTrue(C.aes[0]['sae'])


class F04AeBlankLogRows(unittest.TestCase):
    """RUX 深审 F04：AE 发生标志=否 的空白日志行（无术语/日期/等级；标志列名≠D001 的「是否发生不良事件」，
    如「有无不良事件」「是否发生不良事件？」）此前被计为 AE 并进 AE 谱伪桶。normalize 对 AE 域行：
    发生标志=否 且 真实术语列为空 → 跳过；标志=否但术语有值、或标志=是 → 保留。夹具全虚构。"""

    @staticmethod
    def _run(flag_label='是否发生不良事件？', rows=None, dom='ae'):
        import tempfile
        import openpyxl
        from normalize_listing import Book, read_spec
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'ae.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'AE'
            ws.append(['受试者编号', '访视名称', flag_label, '不良事件名称', '最早开始日期'])
            for r in (rows if rows is not None else
                      [['S1', '共同页', '否', '', ''], ['S2', '共同页', '是', '头痛', '2026-05-01'],
                       ['S3', '共同页', '否', '皮疹', '2026-05-02']]):
                ws.append(r)
            wb.save(p)
            spec = {'wb': 'edc', 'sheet': 'AE', 'label_row': 1, 'var_row': 0, 'data_start': 2,
                    'cols': {'sid': '受试者编号', 'term': '访视名称'}}
            M = {'workbooks': {'edc': str(p)}, 'domains': {}}
            return [rec for rec, *_ in read_spec(spec, {'edc': Book(str(p))}, M, dom)]

    def test_other_domains_not_skipped(self):
        """mm5 审阅修正：合并用药「是否因不良事件用药=否」、检验「是否记录为不良事件=否」是真实记录，不跳过。"""
        for dom in ('cm', None):
            recs = self._run(flag_label='是否因不良事件用药', rows=[['S1', '共同页', '否', '', '']], dom=dom)
            self.assertEqual([r['sid'] for r in recs], ['S1'], dom)

    def test_flag_no_blank_row_skipped(self):
        recs = self._run()
        self.assertEqual([r['sid'] for r in recs], ['S2', 'S3'])     # S1 空白日志行被跳过；S3 标志=否但有术语 → 保留

    def test_flag_label_variants(self):
        for lb in ('有无不良事件', '是否发生AE？', '是否发生不良事件'):
            recs = self._run(flag_label=lb, rows=[['S1', '共同页', '否', '', '']])
            self.assertEqual(recs, [], lb)                           # 列名变体同样识别


class Mm5LinkFixes(unittest.TestCase):
    """mm5 审阅 S4/S6/S7：空术语不恒命中、否定写法不作关联、回溯不到的词目不算已关联、归因维度用回溯后关联（全虚构）。"""
    def _C(self):
        from types import SimpleNamespace
        from collections import defaultdict
        mh = defaultdict(list)
        mh['S1'] = [{'n': 1, 't': '', 's': '2020-01-01'}, {'n': 2, 't': '高血压', 's': '2019-01-01'}]
        return SimpleNamespace(ae_by=defaultdict(list), mh_by=mh)

    def test_blank_history_term_never_matches(self):
        from mm_build import resolve_links, real_links
        C = self._C()
        out = resolve_links(C, 'S1', [['MH', '研究药物', None, None]])
        self.assertFalse(out[0][4])                                   # 旧版：'' in '研究药物' 恒真 → 误判已关联 MH#1
        self.assertEqual(real_links(out), [])
        ok = resolve_links(C, 'S1', [['MH', '高血压', None, None]])
        self.assertTrue(ok[0][4])
        self.assertEqual(ok[0][3], 2)

    def test_numbered_link_counts_even_if_missing(self):
        from mm_build import resolve_links, real_links
        out = resolve_links(self._C(), 'S1', [['AE', '头痛', None, 9]])
        self.assertEqual(len(real_links(out)), 1)                      # 填了编号但不存在：仍算研究者有关联（交 LINK 核对）

    def test_att_of_uses_resolved_links(self):
        from ext_rules import att_of
        r = {'links': [['MH', '饮食', None, None]], '_lk': [], 'reason': 'disease'}
        self.assertEqual(att_of(r), '研究疾病')
        self.assertEqual(att_of({'links': [['MH', '高血压', None, None]], '_lk': ['MH']}), 'MH')


class Mm5IbUmbrellaDirection(unittest.TestCase):
    """mm5 审阅 S11：IB 伞形条目按指标兜底时方向须一致（「白细胞降低」类风险不标到「白细胞升高」）。"""
    def test_direction(self):
        import re
        import mm_build
        from types import SimpleNamespace
        orig = mm_build._exp_list
        mm_build._exp_list = lambda C: [{'label': 'IB重要潜在风险', 'term': '血液学检测异常', 'pt': None, 're': None, '_re': None,
                                         'soc': '各类检查', '_labs': [(re.compile('白细胞'), 'low')]}]
        try:
            C = SimpleNamespace(A={}, S={})
            self.assertEqual(mm_build.ib_match(C, {'t': '白细胞计数升高', 'g': '3级', 'soc': '各类检查'}), [])
            self.assertEqual(len(mm_build.ib_match(C, {'t': '白细胞计数降低', 'g': '3级', 'soc': '各类检查'})), 1)
        finally:
            mm_build._exp_list = orig


class Mm5EntryErrors(unittest.TestCase):
    """mm5 疑似录入错误（用户 2026-10-31）：孤立尖峰＋约 10 的整数次幂倍 → 小数点错位；持续上升（真实变化）不报；
    等价单位写法（U/L＝IU/L）不报；尿沉渣计数不做倍数判断；同一点在医学风险层时风险行加提示（全虚构）。"""
    def _C(self, label, vals, units=None):
        from types import SimpleNamespace
        rows = [{'sid': 'S1', 'value': v, 'raw': str(v), 'unit': (units[i] if units else 'g/L'), 'visit': f'V{i + 1}',
                 'date': f'2026-0{1 + i // 9}-{10 + i % 9:02d}', 'sheet': 'LB', 'row': i + 2, 'wb': ''} for i, v in enumerate(vals)]
        return SimpleNamespace(A={}, F={('S1', 'lab:' + label): rows}, metric={'lab:' + label: {'label': label}},
                               subj={'S1': {'site': '01'}}, src={'sheets': {}}, labrows=[]), rows

    def test_decimal_shift_flagged(self):
        from mm_build import entry_errors
        C, rows = self._C('血红蛋白', [130, 128, 1290, 131, 127])
        entry_errors(C)
        self.assertEqual(len(C.entry), 1)
        self.assertIn('小数点错位', C.entry[0]['why'])
        self.assertEqual(rows[2]['_entry'], C.entry[0]['why'])

    def test_sustained_rise_not_flagged(self):
        from mm_build import entry_errors
        C, _ = self._C('丙氨酸氨基转移酶', [30, 32, 300, 420, 380])         # 连续升高（如药物性肝损伤）不是孤立尖峰
        entry_errors(C)
        self.assertEqual(C.entry, [])

    def test_equivalent_units_and_urine_skipped(self):
        from mm_build import entry_errors
        C, _ = self._C('肌酸激酶', [100, 110, 105, 98], units=['U/L', 'IU/L', 'U/L', 'U/L'])
        entry_errors(C)
        self.assertEqual(C.entry, [])
        C, _ = self._C('尿红细胞', [5, 6, 300, 4, 5])
        entry_errors(C)
        self.assertEqual(C.entry, [])


class F02bDiseaseTermLinks(unittest.TestCase):
    """F02 边界（用户 2026-10-27 口径：归因研究疾病不算「未关联」）：说明列词目若命中方案研究疾病词
    （analysis.diseaseTerms/适应症），不作 MH 关联——DIS/DISW 豁免不被词目链接抢走；具体病史词目保留。"""

    def test_disease_term_links_stripped(self):
        from types import SimpleNamespace
        from mm_build import _strip_disease_term_links
        C = SimpleNamespace(A={'diseaseTerms': ['特应性皮炎']}, S={'study': {'design': {'facts': [['适应症', '中重度特应性皮炎']]}}},
                            cfg={},
                            findings=[
                                {'links': [['MH', '特应性皮炎', None, None]]},      # 研究疾病词目 → 剥离
                                {'links': [['MH', '脂肪肝', None, None], ['MH', '特应性皮炎', None, None]]},  # 只剥疾病词目
                                {'links': [['AE', '头痛', None, 2]]},                # 编号链接不动
                                {'links': []},
                            ])
        _strip_disease_term_links(C)
        self.assertEqual(C.findings[0]['links'], [])
        self.assertEqual(C.findings[1]['links'], [['MH', '脂肪肝', None, None]])
        self.assertEqual(C.findings[2]['links'], [['AE', '头痛', None, 2]])
        self.assertEqual(C.cfg['diseaseTermLinksStripped'], 2)

    def test_no_disease_terms_noop(self):
        from types import SimpleNamespace
        from mm_build import _strip_disease_term_links
        C = SimpleNamespace(A={}, S={'study': {}}, findings=[{'links': [['MH', '脂肪肝', None, None]]}])
        _strip_disease_term_links(C)
        self.assertEqual(C.findings[0]['links'], [['MH', '脂肪肝', None, None]])   # 未配置研究疾病词：不动（可见不猜）


class F05AttributionDimension(unittest.TestCase):
    """RUX 深审 F05：判定一致性「归因维度」比对前核对 CS 侧行说明列关联引用——desc 解析出的关联
    （F02）参与 att_of；两条均 CS 且归因不同才成对（无方向不排序），正文呈现两侧归因。夹具全虚构。"""

    def test_att_of_uses_desc_links(self):
        from ext_rules import att_of
        self.assertEqual(att_of({'links': [['MH', '脂肪肝', None, None]]}), 'MH')
        self.assertEqual(att_of({'links': [['AE', '疖肿', None, None]]}), 'AE')
        self.assertEqual(att_of({'links': [], 'reason': 'disease'}), '研究疾病')
        self.assertEqual(att_of({'links': [], 'reason': None}), '未关联')

    def test_attribution_pairing(self):
        from ext_rules import cons_attribution
        cs = [_cons_row('S1', 90, 2, lo=115, links=[['MH', '贫血', None, 1]], row=1),
              _cons_row('S1', 92, 2, lo=115, links=[], row=2),
              _cons_row('S1', 94, 2, lo=115, links=[['MH', '贫血', None, 1]], row=3)]
        pairs = cons_attribution(cs, cross_subject=False)
        self.assertEqual(len(pairs), 1)
        a, b = pairs[0]
        self.assertEqual((a['row'], b['row']), (1, 2))               # 归因 MH vs 未关联；行 3 同归因不成对

    def test_clin_consistency_presents_both_attributions(self):
        from types import SimpleNamespace
        import ext_rules
        rows = [_cons_row('S1', 90, 2, lo=115, links=[['MH', '贫血', None, 1]], visit='V2', date='2026-05-01', row=1),
                _cons_row('S1', 95, 2, lo=115, links=[], visit='V3', date='2026-05-10', row=2)]   # V6：同受试者归因比较只看 14 天内
        F = {}
        for r in rows:
            F.setdefault((r['sid'], 'lab:HGB'), []).append(r)
        C = SimpleNamespace(A={}, F=F, metric={'lab:HGB': {'label': '血红蛋白'}},
                            subj={'S1': {'site': '01'}}, pop={'S1'}, others=[], src={'sheets': {}})
        ext_rules.clin_consistency(C)
        q = [o for o in C.others if o['cat'] == '临床意义判定不一致']
        self.assertEqual(len(q), 1)
        self.assertIn('关联病史', q[0]['sum'])
        self.assertIn('未关联任何记录', q[0]['sum'])


class F06CtcaeDirectionAndWording(unittest.TestCase):
    """RUX 深审 F06：①无对应 CTCAE 条目方向的指标不得标 CTCAE 等级——单一方向的「纯较基线变化」型条目只在指标名
    带相符方向词时映射；含增、减两个方向的条目（WEIGHT）原始测量也映射、按变化正负分级（mm5 审阅修正）；
    ②低于下限的值不再写「升高至」（相对基线方向≠偏离参考范围方向，分离表述）。夹具全虚构。"""

    def test_raw_weight_graded_by_change_direction(self):
        """mm5 审阅修正：WEIGHT 条目同时含 Weight gain（H）与 Weight loss（L），原始体重按较基线变化正负分别分级；
        单一方向的纯变化型条目仍要求指标名带方向词。"""
        import ctcae
        G = ctcae.load({'grading': {'version': '5.0'}})
        m = {'vs:体重': {'domain': 'vs', 'label': '体重', 'units': {'kg': 9}},
             'vs:体重增加': {'domain': 'vs', 'label': '体重增加', 'units': {}},
             'vs:体重减轻': {'domain': 'vs', 'label': '体重减轻', 'units': {}}}
        out = ctcae.automap(m, G, {})
        self.assertEqual(out.get('vs:体重'), 'WEIGHT')
        self.assertEqual(G.grade('WEIGHT', 70, None, None, 62)[:2], (2, '体重增加'))     # +12.9%
        self.assertEqual(G.grade('WEIGHT', 75.2, None, None, 84)[:2], (2, '体重减轻'))   # −10.5%
        self.assertEqual(out.get('vs:体重增加'), 'WEIGHT')
        self.assertEqual(out.get('vs:体重减轻'), 'WEIGHT')

    def test_range_anchored_mapping_unchanged(self):
        import ctcae
        G = ctcae.load({'grading': {'version': '5.0'}})
        out = ctcae.automap({'lab:血红蛋白': {'domain': 'lab', 'label': '血红蛋白', 'units': {'g/L': 9}}}, G, {})
        self.assertEqual(out.get('lab:血红蛋白'), 'HGB')              # 参考范围锚定型条目行为不变

    def test_move_word_separates_deviation_direction(self):
        from common import move_word
        self.assertEqual(move_word(80, 90, lo=115), '较基线回升至')   # 较基线上升但仍低于下限：禁「升高至」
        self.assertEqual(move_word(80, 90, lo=None), '升高至')
        self.assertEqual(move_word(80, 160, hi=150), '升高至')        # 超上限的正常「升高」措辞不动
        self.assertEqual(move_word(90, 80), '下降至')
        self.assertEqual(move_word(175, 165, hi=150), '较基线回降至') # 镜像：高于上限中回落仍超上限
        self.assertEqual(move_word(90, 90), '为')

    def test_csb_query_head_uses_move_word(self):
        from ext_rules import _csb_query
        from types import SimpleNamespace
        C = SimpleNamespace(pop={'S1'}, subj={'S1': {'site': '01'}}, metric={'lab:HGB': {'label': '血红蛋白'}},
                            others=[], src={'sheets': {}, 'sheets_by_name': {}}, A={}, extq=[], queries_manual=[])
        r = {'sid': 'S1', 'visit': 'V2', 'date': '2026-05-01', 'value': 90, 'raw': '90', 'unit': 'g/L',
             'base': {'value': 80}, 'lo': 115, 'hi': None, 'mid': 'lab:HGB', 'sheet': 'LAB', 'row': 3,
             'clin': 2, 'links': []}
        _csb_query(C, r, 'LINK', None, '', [])
        self.assertIn('较基线回升至', C.others[0]['sum'])
        self.assertNotIn('升高至', C.others[0]['sum'])


class F07ThresholdSameRowMerge(unittest.TestCase):
    """RUX 深审 F07：组合规则（ALT|AST）与单列规则命中同一检验行 → 合并为单段，不再逐规则重复
    「达到方案阈值」。跨 thresholdRules/comboRules 共享同行命中登记。夹具全虚构。"""

    @staticmethod
    def _row():
        return {'sid': 'S1', 'mid': 'lab:ALT', 'post': True, 'clin': None, 'value': 313, 'raw': '313', 'unit': 'U/L',
                'lo': 9, 'hi': 50, 'grade': 0, 'pct': None, 'visit': 'V2', 'date': '2026-05-01',
                'sheet': 'LBCHEM', 'row': 11, 'wb': 'edc', 'links': [], 'base': None}

    def test_two_threshold_rules_same_row_one_signal(self):
        from mm_build import threshold_rules
        from types import SimpleNamespace
        R1 = {'id': 'T-A3', 'metric': 'ALT', 'cat': '阈值规则核对', 'op': '>', 'v': 50, 'label': 'ALT > 3 ×ULN',
              'sum': '{test} {value}（{visit} {date}）达到方案阈值 {thr}'}
        R2 = {'id': 'T-A5', 'metric': 'ALT', 'cat': '阈值规则核对', 'op': '>', 'v': 250, 'label': 'ALT > 5 ×ULN',
              'sum': '{test} {value}（{visit} {date}）达到方案阈值 {thr}'}
        C = SimpleNamespace(A={'thresholdRules': [R1, R2]}, cfg={}, pop={'S1'}, subj={'S1': {'site': '01'}},
                            F={('S1', 'lab:ALT'): [self._row()]}, metric={'lab:ALT': {'label': 'ALT'}},
                            others=[], src={'sheets': {}})
        threshold_rules(C)
        self.assertEqual(len(C.others), 2)        # mm5 审阅修正：不同阈值（3×ULN 报告、5×ULN）是不同判据，各自出信号

    def test_same_criterion_twice_one_signal_and_stop_rule_kept(self):
        """方案不同章节重复抽出的同一判据只出一条；同值的停药规则（stop）是不同含义，保留（WD-01 依赖它）。"""
        from mm_build import threshold_rules
        from types import SimpleNamespace
        R1 = {'id': 'T-A5a', 'metric': 'ALT', 'cat': '阈值规则核对', 'op': '>', 'v': 250, 'label': 'ALT > 5 ×ULN'}
        R2 = dict(R1, id='T-A5b')
        R3 = dict(R1, id='T-STOP', stop=True)
        C = SimpleNamespace(A={'thresholdRules': [R1, R2, R3]}, cfg={}, pop={'S1'}, subj={'S1': {'site': '01'}},
                            F={('S1', 'lab:ALT'): [self._row()]}, metric={'lab:ALT': {'label': 'ALT'}},
                            others=[], src={'sheets': {}})
        threshold_rules(C)
        self.assertEqual(sorted(o['_rule']['id'] for o in C.others), ['T-A5a', 'T-STOP'])

    def test_combo_and_threshold_same_row_one_signal(self):
        from mm_build import threshold_rules, combo_rules
        from types import SimpleNamespace
        R = {'id': 'T-A5', 'metric': 'ALT', 'cat': '阈值规则核对', 'op': '>', 'v': 250, 'label': 'ALT > 5 ×ULN',
             'sum': '{test} {value}（{visit} {date}）达到方案阈值 {thr}'}
        CB = {'id': 'CB-1', 'name': 'ALT 重度升高', 'cat': '阈值规则核对', 'pr': 3,
              'all': [{'metric': 'ALT', 'on': 'val', 'op': '>', 'v': 250}]}
        C = SimpleNamespace(A={'thresholdRules': [R], 'comboRules': [CB]}, cfg={}, pop={'S1'},
                            subj={'S1': {'site': '01'}}, F={('S1', 'lab:ALT'): [self._row()]},
                            metric={'lab:ALT': {'label': 'ALT'}}, others=[], src={'sheets': {}})
        threshold_rules(C)
        combo_rules(C)
        self.assertEqual(len(C.others), 1)


class F08DuplicateAeRecords(unittest.TestCase):
    """RUX 深审 F08：同受试者同术语同开始日期成对/三联记录（EDC 修订版整行重复导出）——
    build_events 打指纹标记（dup_n/dup_rows/dup），AE 谱按去重计数，逐记录质疑只按组首发生，
    并对每组发一条「AE重复记录核对」标记。夹具全虚构。"""

    @staticmethod
    def _ae(row, no='4'):
        return {'sid': 'S1', 'term': '中性粒细胞计数降低', 'pt': '中性粒细胞计数降低', 'start': '2026-06-01',
                'end': '2026-06-10', 'grade': '2级', 'no': no, 'row': row, 'sheet': 'AE', 'serious': '否', 'rel': ''}

    def _C(self, aes):
        from types import SimpleNamespace
        return SimpleNamespace(A={}, subj={'S1': {'site': '01', 'fd': '2026-05-01'}}, teEnd={}, ae=aes, mh=[], cm=[])

    def test_build_events_marks_duplicates(self):
        from mm_build import build_events
        C = self._C([self._ae(15), self._ae(16), self._ae(17), dict(self._ae(18), term='头痛', pt='头痛', no='5', start='2026-07-01')])
        build_events(C)
        self.assertEqual(len(C.ae_dup), 1)
        grp = C.ae_dup[0]
        self.assertEqual(grp['rows'], [15, 16, 17])
        self.assertEqual(grp['recs'][0]['dup_n'], 3)
        self.assertFalse(grp['recs'][0].get('dup'))
        self.assertTrue(all(r.get('dup') for r in grp['recs'][1:]))
        self.assertEqual(len(C.ae_by['S1']), 4)                        # 记录池不删行（数据面保留全部行号可溯）
        self.assertEqual([g['term'] for g in C.ae_dup], ['中性粒细胞计数降低'])  # 头痛不入组

    def test_identical_but_different_start_not_duplicate(self):
        from mm_build import build_events
        C = self._C([self._ae(15), dict(self._ae(16), start='2026-07-01')])
        build_events(C)
        self.assertEqual(getattr(C, 'ae_dup', []), [])

    def test_different_grade_or_sae_not_duplicate(self):
        """mm5 审阅（S5）：同日同术语但等级/SAE/结束日期不同 → 两条独立记录，不去重。"""
        from mm_build import build_events
        for chg in ({'grade': '3级'}, {'serious': True}, {'end': '2026-06-20'}):
            C = self._C([dict(self._ae(15), serious=False), dict(self._ae(16), **{'serious': False, **chg})])   # normalize 后 serious 为布尔
            build_events(C)
            self.assertEqual(getattr(C, 'ae_dup', []), [], chg)

    def test_duplicate_marker_query_and_single_member_query(self):
        from mm_build import build_events, ae_checks
        C = self._C([self._ae(15), self._ae(16), self._ae(17)])
        C.A = {'aeChecks': ['duplicate']}
        build_events(C)
        C.pop, C.others, C.src, C.F, C.aesiDefs, C.cm_by = {'S1'}, [], {'sheets': {}}, {}, [], {'S1': []}
        ae_checks(C)
        dup = [o for o in C.others if o['cat'] == 'AE重复记录核对']
        self.assertEqual(len(dup), 1)
        self.assertIn('3 条', dup[0]['sum'])
        self.assertEqual(len(C.others), 1)                           # 同 PT 重复不发 PT 级质疑，仅此一条标记

    def test_m19_fires_once_per_group(self):
        from mm_build import build_events
        from ext_rules import m19_ae_ex
        from types import SimpleNamespace
        aes = [dict(self._ae(15), action='停药'), dict(self._ae(16), action='停药')]
        C = self._C(aes)
        build_events(C)
        C = SimpleNamespace(**{**C.__dict__, 'A': {}, 'pop': {'S1'}, 'others': [], 'src': {'sheets': {}}, 'F': {},
                               'exposure': []})
        m19_ae_ex(C)
        hit = [o for o in C.others if o['cat'] == 'AE与给药记录一致性核对']
        self.assertEqual(len(hit), 1)                                # 两份重复记录只按组首发生一次


class F09SocBucketPriority(unittest.TestCase):
    """RUX 深审 F09：AE 分桶单一来源——aeCatMap 命中类别与 MedDRA SOC 列不一致的行以 SOC 列为准
    （实测 2 例错桶）；无 SOC 的记录仍走 catmap→原文术语回退。夹具全虚构。"""

    def test_soc_column_wins_over_catmap(self):
        from types import SimpleNamespace
        from mm_build import build_events
        C = SimpleNamespace(A={'aeCatMap': [['肺炎', '皮肤及皮下组织类疾病'], ['头痛', '皮肤及皮下组织类疾病']]},
                            subj={'S1': {'site': '01', 'fd': '2026-05-01'}}, teEnd={},
                            ae=[{'sid': 'S1', 'term': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'start': '2026-05-01',
                                 'row': 2, 'sheet': 'AE', 'serious': '否', 'rel': ''},
                                {'sid': 'S1', 'term': '头痛', 'pt': '头痛', 'soc': '', 'start': '2026-05-02',
                                 'row': 3, 'sheet': 'AE', 'serious': '否', 'rel': ''}], mh=[], cm=[])
        build_events(C)
        self.assertEqual(C.aes[0]['c'], '感染及侵染类疾病')           # SOC 列为准
        self.assertEqual(C.aes[1]['c'], '皮肤及皮下组织类疾病')        # 无 SOC：catmap 回退不变


class F10MicroUnitCanonical(unittest.TestCase):
    """RUX 深审 F10：μ 两种写法归一（U+03BC 希腊 μ / U+00B5 微 μ）——normalize 单位一处收口，
    与 ×10^ 归一同点。夹具全虚构。"""

    @staticmethod
    def _row(units):
        import openpyxl
        import tempfile
        from normalize_listing import Book, findings
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'UA'
        ws.append(['受试者编号', '访视', '检查日期', '检查项', '检查结果', '单位'])
        for i, u in enumerate(units, 1):
            ws.append(['S1', f'V{i}', '2026-05-01', '尿酸', '424', u])
        M = {'workbooks': {'edc': 'x'}, 'domains': {}}
        spec = {'wb': 'edc', 'sheet': 'UA', 'domain': 'lab', 'group': '血生化', 'label_row': 1, 'var_row': 0,
                'data_start': 2,
                'cols': {'sid': '受试者编号', 'visit': '访视', 'date': '检查日期', 'test': '检查项',
                         'value': '检查结果', 'unit': '单位'}}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'edc.xlsx'
            wb.save(p)
            return [r.get('unit') for r in findings(spec, {'edc': Book(str(p))}, M)]

    def test_mu_variants_unified(self):
        greek, micro = '\u03bcmol/L', '\u00b5mol/L'                # U+03BC 希腊 μ / U+00B5 微符号
        self.assertNotEqual(greek, micro)
        self.assertEqual(self._row([greek]), [micro])               # F12⑤修正：数据层归一到 U+00B5（与分级表键一致，ext1 CSW 判定翻转路径实证 03BC 方向破坏键比较）；显示层 µ→μ 由前端 fmt 负责
        self.assertEqual(self._row([micro]), [micro])               # U+03BC → U+00B5
        self.assertEqual(self._row(['mg/dL', greek]), ['mg/dL', micro])   # 无 μ 迹象的单位不碰


class DrilldownFields(unittest.TestCase):
    """用户 2026-10-30 裁定：参与者资料页 CS 项点开必须有链接信息——钻取（受试者资料文件）检验行
    尾部扩位 [归因码, 原文说明≤60, 关联摘要]，既有 14 位不动（前端按索引安全读取）。
    归因码：AE/MH＝关联已回溯到真实记录；disease＝研究者归因研究疾病；NA＝超范围未评价；''＝无。"""

    @staticmethod
    def _C(ae=(), mh=()):
        from types import SimpleNamespace
        return SimpleNamespace(ae_by={'S1': list(ae)}, mh_by={'S1': list(mh)})

    def test_ae_link_summary(self):
        from mm_build import drill_fields
        C = self._C(ae=[{'n': 3, 't': '丙氨酸氨基转移酶升高', 's': '2026-06-10'}])
        r = {'clin': 2, 'links': [['AE', '丙氨酸氨基转移酶升高', None, 3]], 'reason': 'link',
             'reason_text': '与3号不良事件有关，请评估AE记录完整性；补充说明较长会被截断到六十字为止不再多留'}
        code, text, summ = drill_fields(C, 'S1', r)
        self.assertEqual(code, 'AE')
        self.assertLessEqual(len(text), 60)
        self.assertTrue(text.startswith('与3号不良事件有关'))
        self.assertEqual(summ, 'AE 丙氨酸氨基转移酶升高·2026-06-10')

    def test_mh_link_summary_no_date(self):
        from mm_build import drill_fields
        C = self._C(mh=[{'n': 1, 't': '贫血', 's': '2020-01-01'}])
        code, _, summ = drill_fields(C, 'S1', {'clin': 2, 'links': [['MH', '贫血', None, 1]], 'reason': 'link'})
        self.assertEqual(code, 'MH')
        self.assertEqual(summ, '病史 贫血·2020-01-01')

    def test_term_link_without_number_resolves(self):
        """F02 词目型（编号空）：按术语回溯到真实记录后照常出关联摘要。"""
        from mm_build import drill_fields
        C = self._C(mh=[{'n': 2, 't': '高脂血症', 's': ''}])
        code, _, summ = drill_fields(C, 'S1', {'clin': 2, 'links': [['MH', '高脂血症', None, None]]})
        self.assertEqual(code, 'MH')
        self.assertEqual(summ, '病史 高脂血症')

    def test_disease_reason_without_link(self):
        from mm_build import drill_fields
        code, _, summ = drill_fields(self._C(), 'S1', {'clin': 2, 'links': [], 'reason': 'disease',
                                                       'reason_text': '与研究疾病加重有关'})
        self.assertEqual(code, 'disease')
        self.assertEqual(summ, '')

    def test_na_out_of_range_unassessed(self):
        from mm_build import drill_fields
        code, _, _ = drill_fields(self._C(), 'S1', {'clin': None, 'value': 88, 'hi': 50, 'oor': True, 'links': []})
        self.assertEqual(code, 'NA')

    def test_plain_row_empty(self):
        from mm_build import drill_fields
        self.assertEqual(drill_fields(self._C(), 'S1', {'clin': 0, 'links': [], 'oor': False}), ['', '', ''])

    def test_unresolved_link_not_attributed(self):
        """关联编号在 AE/MH 记录中不存在：行级按未关联口径（不冒充已关联）。"""
        from mm_build import drill_fields
        code, _, summ = drill_fields(self._C(), 'S1', {'clin': 2, 'links': [['AE', '皮疹', None, 9]]})
        self.assertEqual(code, '')
        self.assertEqual(summ, '')

    def test_subject_file_rows_extend(self):
        """build_subject_files 接线：受试者资料文件里检验行 17 位，尾部 3 位为扩位字段。"""
        import json
        import tempfile
        from collections import defaultdict
        from types import SimpleNamespace
        from mm_build import build_subject_files
        row = {'sid': 'S1', 'date': '2026-06-20', 'visit': 'V2', 'value': 88, 'raw': '88', 'unit': 'U/L',
               'lo': 9, 'hi': 50, 'clin': 2, 'desc': '', 'sheet': 'LB', 'row': 5, 'tpt': '', 'time': '',
               'isb': False, 'post': True, 'pct': None, 'links': [['AE', '丙氨酸氨基转移酶升高', None, 1]],
               'reason': 'link', 'reason_text': '与1号AE有关', 'test': '丙氨酸氨基转移酶'}
        C = SimpleNamespace(
            visits=[], exposure=[], proc=[],
            subj={'S1': {'site': '01', 'center': '示例医院A', 'status': '随机化', 'rand': '', 'strat': '',
                         'icf': '2026-01-05', 'fd': '2026-06-01', 'ld': '', 'lo': '', 'age': 44, 'bmi': 23}},
            ae_by={'S1': [{'n': 1, 't': '丙氨酸氨基转移酶升高', 's': '2026-06-10', 'e': ''}]},
            mh_by={'S1': []}, cm_by={'S1': []}, effsub={}, tl={},
            A={'labDomains': ['lab'], 'extFlagPct': 50},
            F=defaultdict(list, {('S1', 'lab:丙氨酸氨基转移酶'): [row]}),
            metric={'lab:丙氨酸氨基转移酶': {'label': '丙氨酸氨基转移酶'}})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'data'
            build_subject_files(C, out)
            raw = (out / 's' / 'S1.js').read_text(encoding='utf-8')
            self.assertTrue(raw.startswith('KZ_SUB('))
            d = json.loads(raw[len('KZ_SUB('):-2])
            r0 = d['labs']['丙氨酸氨基转移酶'][0]
            self.assertEqual(len(r0), 20, f'既有 14 位＋扩位 3 位＋mm5 全程面板 3 位（得 {len(r0)}）')
            self.assertIsInstance(r0[19], str)                                       # 疑似录入错误说明（无则空串）
            self.assertEqual(r0[:14][7], 2)                       # 既有位不动：r[7]=clin
            self.assertEqual(r0[14], 'AE')
            self.assertEqual(r0[15], '与1号AE有关')
            self.assertIn('AE 丙氨酸氨基转移酶升高·2026-06-10', r0[16])


class V5Monitor(unittest.TestCase):
    """V5（用户 2026-10-31 晚）：统计工具、访视推算、关键评估名称容错、范围内明显变化与趋势预警、数据可信度、KRI（全虚构夹具）。"""

    def test_bh_and_tails(self):
        from monitor_v5 import bh, binom_upper, pois_upper
        q = bh([0.01, 0.04, 0.03, None, 0.5])
        self.assertAlmostEqual(q[0], 0.04)                       # 0.01×4/1，取后缀最小 → 0.04
        self.assertIsNone(q[3])
        self.assertAlmostEqual(pois_upper(0, 3.0), 1.0)
        self.assertAlmostEqual(pois_upper(1, 1.0), 1 - 2.718281828 ** -1, places=6)
        self.assertLess(binom_upper(40, 100, 0.2), 1e-4)
        self.assertGreater(binom_upper(20, 100, 0.2), 0.4)

    def _C(self):
        from types import SimpleNamespace
        subj = {'S1': {'site': '01', 'fd': '2026-01-01', 'status': '已入组', 'lo': '2026-03-01'},
                'S2': {'site': '01', 'fd': '2026-01-01', 'status': '提前退出', 'eos_d': '2026-01-10', 'lo': '2026-01-10'}}
        visits = [{'sid': 'S1', 'visit': 'W2', 'date': '2026-01-15'}, {'sid': 'S1', 'visit': 'W4', 'date': '2026-02-05'}]
        return SimpleNamespace(A={'visitWindows': {'W2': [15, 3, 3], 'W4': [29, 3, 3], 'W8': [57, 3, 3], 'W12': [84, 3, 3]}}, subj=subj, visits=visits,
                               pop={'S1', 'S2'}, S={}, cfg={}, efficacy=[], findings=[])

    def test_visit_due_and_upcoming(self):
        from monitor_v5 import visit_due
        due, up = visit_due(self._C(), '2026-03-20')
        st = {(d[0], d[2]): d[6] for d in due}
        self.assertEqual(st[('S1', 'W2')], 'ok')
        self.assertEqual(st[('S1', 'W4')], 'out')                 # D36，窗 29±3
        self.assertEqual(st[('S1', 'W8')], 'overdue')
        self.assertNotIn(('S2', 'W4'), st)                        # 结束于访视窗之前，不应完成
        self.assertEqual([u[2] for u in up], ['W12'])             # 窗 3/23–3/29，在未来 14 天内

    def test_followup_and_planned(self):
        from monitor_v5 import followup, planned_n
        C = self._C()
        fu = followup(C, '2026-03-20')
        self.assertEqual(fu['S1'], 79)                            # 在研：首剂 → 数据截止
        self.assertEqual(fu['S2'], 10)                            # 已结束：首剂 → 研究结束
        C.S = {'study': {'design': {'facts': [['计划例数', '160']]}}}
        self.assertEqual(planned_n(C), 160)

    def test_crit_items_suffix_tolerant(self):
        from types import SimpleNamespace
        from monitor_v5 import crit_items
        C = SimpleNamespace(A={'pd': {'criticalItems': 'EASI评分'}}, efficacy=[{'metric': 'EASI得分'}], findings=[])
        rx_, hit = crit_items(C)
        self.assertEqual(hit, ['EASI得分'])
        self.assertTrue(rx_.search('EASI得分'))

    def _lab(self, code, label, vals, base, unit='g/L', lo=None, hi=None, times=None):
        from types import SimpleNamespace
        import ctcae
        b = {'value': base, 'raw': str(base)}
        rows = [{'sid': 'S1', 'value': v, 'raw': str(v), 'unit': unit, 'lo': lo, 'hi': hi, 'visit': f'V{i + 1}', 'post': True, 'base': b,
                 'date': f'2026-02-{10 + i:02d}' if times else f'2026-0{2 + i}-10', 'time': (times[i] if times else None),
                 'sheet': 'LB', 'row': i + 2, 'wb': '', 'oor': (hi is not None and v > hi) or (lo is not None and v < lo), 'grade': 0} for i, v in enumerate(vals)]
        mid = 'lab:' + label
        C = SimpleNamespace(A={}, F={('S1', mid): rows}, metric={mid: {'label': label}}, cmap={mid: code} if code else {}, pop={'S1'},
                            cfg={'thresholds': {'base': 0.3}}, G=ctcae.load({'grading': {'version': '6.0'}}))
        out = []
        return C, out, (lambda C_, sid, cat, pr, summ, *a, **k: out.append((cat, pr, summ, a[7] if len(a) > 7 else None)))

    def test_in_range_hb_drop_and_creatinine(self):
        import monitor_v5
        C, out, add = self._lab('HGB', '血红蛋白', [150, 128], 152, lo=115, hi=175)
        monitor_v5.lab_shift(C, add)
        self.assertEqual([o[0] for o in out], ['范围内明显变化'])
        self.assertIn('下降 24 g/L', out[0][2])
        C, out, add = self._lab('CREAT', '肌酐', [60, 90], 58, unit='μmol/L', lo=45, hi=104, times=['08:00', '09:00'])
        monitor_v5.lab_shift(C, add)
        self.assertTrue(any('KDIGO' in o[3][0] for o in out))     # 次日 +30 μmol/L（≥26.5）且仍在范围内
        C, out, add = self._lab('CREAT', '肌酐', [60, 70], 58, unit='μmol/L', lo=45, hi=104, times=['08:00', '09:00'])
        monitor_v5.lab_shift(C, add)
        self.assertEqual(out, [])

    def test_trend_requires_three_unfavourable_steps(self):
        import ext_rules
        import monitor_v5
        ext_rules.set_metric_dir({})
        C, out, add = self._lab(None, '丙氨酸氨基转移酶', [12, 15, 19, 26], 11, unit='U/L', hi=40)
        monitor_v5.lab_shift(C, add)
        self.assertEqual([o[0] for o in out], ['持续变化趋势'])
        self.assertIn('连续 3 次升高', out[0][2])
        C, out, add = self._lab(None, '丙氨酸氨基转移酶', [12, 15, 19], 11, unit='U/L', hi=40)   # 只有 2 次变化
        monitor_v5.lab_shift(C, add)
        self.assertEqual(out, [])
        C, out, add = self._lab(None, '丙氨酸氨基转移酶', [12, 15, 19, 45], 11, unit='U/L', hi=40)  # 已超出参考范围：交给风险层
        monitor_v5.lab_shift(C, add)
        self.assertEqual(out, [])

    def test_cred_digit_preference_and_flat(self):
        from types import SimpleNamespace
        from collections import Counter
        from monitor_v5 import cred
        F, metric = {}, {}
        subj = {}
        for s in range(8):
            for site, vals in (('01', [120, 125, 130, 135, 140, 115]), ('02', [121, 127, 133, 138, 142, 117])):
                sid = f'{site}{s}'
                subj[sid] = {'site': site}
                for lab, off in (('收缩压', 0), ('心率', -50)):
                    mid = 'vs:' + lab
                    metric[mid] = {'label': lab, 'units': Counter({'mmHg': 1})}
                    F[(sid, mid)] = [{'value': v + off, 'raw': str(v + off), 'date': f'2026-01-{10 + i:02d}', 'unit': 'mmHg', 'base': None} for i, v in enumerate(vals)]
        F[('010', 'vs:心率')] = [{'value': 72, 'raw': '72', 'date': f'2026-01-{10 + i:02d}', 'unit': 'mmHg', 'base': None} for i in range(5)]
        out = cred(SimpleNamespace(F=F, metric=metric, subj=subj))
        self.assertLess(out['sites']['01']['dig'][2], 0.001)      # 01 全部末位 0/5
        self.assertGreater(out['sites']['02']['dig'][2], 0.05)
        self.assertEqual(out['sites']['01']['flat'][1], 1)
        self.assertEqual(out['flat'][0][:3], ['010', '01', '心率'])


class CredDynamicDomain(unittest.TestCase):
    """用户 2026-11-01：数据可信度按域动态选——vs＋pe 域全部数值型指标（这些域语义＝人工/设备直接测量），
    不再预设血压/心率/体重名单：呼吸/体温纳入末位数字统计；pe 域体重纳入 ≥4 次完全相同；
    同日相同泛化为「≥3 项测量全部相同」；研究没有的数据自然不显示。全部虚构夹具。"""

    @staticmethod
    def _cred(F, metric):
        from collections import Counter
        from types import SimpleNamespace
        import monitor_v5
        C = SimpleNamespace(subj={'S1': {'site': '01'}, 'S2': {'site': '01'}}, metric=metric, F=F)
        return monitor_v5.cred(C)

    @staticmethod
    def _row(raw, value, date='2026-06-01', visit='V1'):
        return {'sid': '', 'value': value, 'raw': raw, 'unit': '', 'date': date, 'visit': visit, 'post': False}

    @staticmethod
    def _metric(mid, unit, n):
        from collections import Counter
        return {m: {'label': m.split(':', 1)[1], 'units': Counter({unit: n})} for m in mid}

    def test_vs_breathing_temperature_enter_dig(self):
        rows = [self._row('16', 16.0), self._row('17', 17.0), self._row('18', 18.0), self._row('25', 25.0)]
        temp = [self._row('36', 36.0), self._row('37', 37.0)]
        F = {('S1', 'vs:呼吸频率'): rows, ('S1', 'vs:体温'): temp}
        out = self._cred(F, self._metric(['vs:呼吸频率', 'vs:体温'], '次/分', 4))
        self.assertEqual(out['sites']['01']['dig'][0], 6)                    # 修前只认血压/心率正则（红）

    def test_pe_weight_enter_flat(self):
        rows = [self._row('62', 62.0, date=f'2026-06-0{i}', visit=f'V{i}') for i in range(1, 5)]
        out = self._cred({('S1', 'pe:体重'): rows}, self._metric(['pe:体重'], 'kg', 4))
        self.assertEqual(out['sites']['01']['flat'][:2], [1, 1])             # 修前 dom=='vs' 限定不纳入（红）
        self.assertEqual(len(out['flat']), 1)

    def test_same_day_identical_vector_generalized(self):
        mids = ['vs:心率', 'vs:呼吸频率', 'vs:体温']
        F = {}
        for sid in ('S1', 'S2'):
            for mid, raw, v in zip(mids, ['70', '16', '36.5'], [70.0, 16.0, 36.5]):
                F[(sid, mid)] = [self._row(raw, v)]
        out = self._cred(F, self._metric(mids, '次/分', 1))
        self.assertEqual(len(out['dup']), 1)                                 # 修前只认收缩压/舒张压/心率三件套（红）
        self.assertEqual(out['dup'][0][2], ['S1', 'S2'])

    def test_no_vs_data_all_empty(self):
        out = self._cred({('S1', 'lab:肌酐'): [self._row('3.0', 3.0)]}, self._metric(['lab:肌酐'], 'umol/L', 1))
        s = out['sites']['01']
        self.assertEqual(s['dig'][0], 0)
        self.assertEqual(s['flat'][:2], [0, 0])
        self.assertEqual(s['shift'][:2], [0, 0])
        self.assertEqual(s['dup'], [0])

    def test_edc_metadata_columns_excluded(self):
        """EDC 元数据列（页面号/访视号/表单 OID 等）不是测量指标：不入末位数字/完全相同统计
        （2026-11-01 RUX 实测：页面号≈7 千条整数把末位数字占比顶到 19%）。"""
        rows = [self._row(str(i), float(i), date=f'2026-06-{i:02d}', visit=f'V{i}') for i in range(1, 11)]
        for mid in ('vs:页面号', 'vs:访视号', 'vs:表单OID'):
            out = self._cred({('S1', mid): rows}, self._metric([mid], '', 10))
            self.assertEqual(out['sites']['01']['dig'][0], 0, mid)
            self.assertEqual(out['sites']['01']['flat'][:2], [0, 0], mid)


class V5FixPemDenominator(unittest.TestCase):
    """V5 修复波：关键评估匹配失败（ci_hit 为空）时 pem 分母必须归零——修前 crit_rows 只看 criticalVisits/正则，
    页面「—」与「76/76」同显造成「主要终点全缺」误读（RUX002E2E 实测）。na 提示已存在，本修复只斩断误读来源。"""

    @staticmethod
    def _C(efficacy=()):
        from types import SimpleNamespace
        subj = {'S1': {'site': '01', 'fd': '2026-01-01', 'status': '已入组'}}
        due = [['S1', '01', 'W8', '2026-02-23', '2026-03-01', '2026-02-25', 'ok', 56, 57, 3, 3, 0]]
        return SimpleNamespace(
            A={'pd': {'criticalVisits': ['W8'], 'criticalItems': 'EASI评分'}, 'visitWindows': {'W8': [57, 3, 3]}},
            subj=subj, S=subj, pop={'S1'}, visits=[], efficacy=list(efficacy), findings=[],
            aes=[], queries=[], labrows=[], entry=[], pdd={'potential': [], 'rules': []},
            cfg={'study': {'planned': 10}, 'thresholds': {}},
            ops={'cutoff': '2026-03-05', 'ex': {}, 'due': due, 'fu': {'S1': 60}, 'fresh': {'01': ['2026-03-01', 4, 1]}})

    def test_ci_hit_empty_denominator_zero(self):
        """关键评估正则在数据中一个指标名都匹配不到：pem 分母归零（不再出现「n/n 全缺」误读）。"""
        from monitor_v5 import kri
        self.assertEqual(kri(self._C())['study']['pem'], [0, 0])

    def test_ci_hit_present_counts_normally(self):
        """对照组：数据中确有关键评估指标（名称差一个后缀的容错命中）→ pem 照常按关键访视计数。"""
        from monitor_v5 import kri
        C = self._C(efficacy=[{'sid': 'S1', 'metric': 'EASI得分', 'visit': 'W8', 'value': 8}])
        self.assertEqual(kri(C)['study']['pem'], [0, 1])

    def test_na_note_still_explains(self):
        """分母归零的同时保留「找不到对应指标」的 na 提示（口径不变：告诉用户为什么是「—」）。"""
        from monitor_v5 import kri
        self.assertIn('找不到对应指标', kri(self._C())['na']['pem'])


class V5FixUnitSlashEquiv(unittest.TestCase):
    """V5 修复波：单位等价写法归一缺「前导/尾随装饰斜杠」剥离——「/fL」与「fL」是同一单位，
    录入错误检测误报「单位不一致」（RUX002E2E 实测）。ucanon（mm_build.entry_errors 内）补 strip('/')。"""

    @staticmethod
    def _run(label, units, vals=(100, 110, 105, 98, 102)):
        from types import SimpleNamespace
        from mm_build import entry_errors
        rows = [{'sid': 'S1', 'value': v, 'raw': str(v), 'unit': units[i], 'visit': f'V{i + 1}',
                 'date': f'2026-01-{10 + i:02d}', 'sheet': 'LB', 'row': i + 2, 'wb': ''} for i, v in enumerate(vals)]
        C = SimpleNamespace(A={}, F={('S1', 'lab:' + label): rows}, metric={'lab:' + label: {'label': label}},
                            subj={'S1': {'site': '01'}}, src={'sheets': {}}, labrows=[])
        entry_errors(C)
        return C

    def test_leading_slash_is_same_unit(self):
        """多数「×10^9/L」、少数「/×10^9/L」（前导斜杠装饰写法）→ 不再误报单位不一致。"""
        C = self._run('血小板', ['×10^9/L', '/×10^9/L', '×10^9/L', '/×10^9/L', '×10^9/L'])
        self.assertEqual(C.entry, [])

    def test_trailing_slash_is_same_unit(self):
        """尾随斜杠同理：'U/L/' 与 'U/L' 等价。"""
        C = self._run('肌酸激酶', ['U/L', 'U/L/', 'U/L', 'U/L', 'U/L'])
        self.assertEqual(C.entry, [])

    def test_real_minority_unit_still_flagged(self):
        """守卫：真正不同的单位（多数 fL、一条 L）仍要报——装饰斜杠归一不得吞掉真单位差异。"""
        C = self._run('平均血小板体积', ['fL', 'fL', 'fL', 'fL', 'L'])
        self.assertEqual(len(C.entry), 1)
        self.assertIn('单位', C.entry[0]['why'])


class V5FixEfficacyWideTests(unittest.TestCase):
    """V5 修复波：efficacy 域宽表 tests 不被展开（normalize main() 只对 findings 走 findings() 展开，
    efficacy 走通用 read_spec）→ D001INC 量表列值全空、eff.metrics 空、KPI 缺失。修后与 findings 同构展开；
    窄表（const metric）照旧保留 metric 语义。夹具全合成（_SynthXlsx），不进仓库。"""

    ROWS = [['受试者', '访视名称', '靶皮损面积', '面积单位', '合计评分（系统生成）'],
            ['SUBJID', 'VISIT', 'TRTAREA', 'TRTAREA_UNIT', 'DLQI'],
            ['S001', 'W8', 12.5, 'cm2', ''],
            ['S001', 'W12', 9.0, 'cm2', ''],
            ['S002', 'W8', 20.0, 'cm2', '18']]

    @classmethod
    def setUpClass(cls):
        import json
        import shutil
        import subprocess
        import tempfile
        cls.dir = Path(tempfile.mkdtemp(prefix='mm_fix_eff_'))
        _SynthXlsx.build(cls.dir / 't.xlsx', [('TRT', 'A1:E5', None, cls.ROWS)])
        mapping = {'workbooks': {'edc': 't.xlsx'}, 'label_row': 1, 'var_row': 2, 'data_start': 3,
                   'domains': {'efficacy': [
                       {'wb': 'edc', 'sheet': 'TRT', 'cols': {'sid': 'SUBJID', 'visit': 'VISIT'},
                        'tests': {'靶皮损面积': {'value': 'TRTAREA', 'unit': 'TRTAREA_UNIT'}}},
                       {'wb': 'edc', 'sheet': 'TRT', 'cols': {'sid': '受试者', 'visit': '访视名称', 'value': '合计评分（系统生成）'},
                        'const': {'metric': '合计评分（系统生成）'}}]}}
        (cls.dir / 'mapping.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding='utf-8')
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/normalize_listing.py'), str(cls.dir / 'mapping.json'),
                            '--out', str(cls.dir / 'norm')], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]
        cls.eff = json.loads((cls.dir / 'norm/efficacy.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_wide_tests_expanded_values_present(self):
        """宽表逐测试列展开：值列非空（修前 efficacy 走 read_spec，tests 列全空、无 metric）。"""
        area = [r for r in self.eff if r.get('metric') == '靶皮损面积']
        self.assertEqual(len(area), 3)
        self.assertEqual(sorted(r['value'] for r in area), [9.0, 12.5, 20.0])
        self.assertTrue(all(r.get('unit') == 'cm2' for r in area))

    def test_metric_field_on_every_record(self):
        """每条 efficacy 记录带 metric（mm_build.build_eff 按 eff:<metric> 归组）：宽表取测试名，窄表取 const。"""
        self.assertEqual({r.get('metric') for r in self.eff}, {'靶皮损面积', '合计评分（系统生成）'})
        narrow = [r for r in self.eff if r.get('metric') == '合计评分（系统生成）']
        self.assertEqual(len(narrow), 1)
        self.assertEqual(narrow[0]['value'], 18.0)
        self.assertEqual(narrow[0]['sid'], 'S002')

    def test_domain_and_trace_intact(self):
        """域标记与源行追溯不丢：domain=efficacy、sheet/row 保留（下游 ev_sh / drill 定位用）。"""
        self.assertTrue(self.eff)
        self.assertTrue(all(r.get('domain') == 'efficacy' for r in self.eff))
        self.assertTrue(all(r.get('sheet') == 'TRT' and isinstance(r.get('row'), int) for r in self.eff))


class V5FixSmallBaseNoise(unittest.TestCase):
    """V5 修复波：EO/EO%/嗜碱/MO#/TBIL 等基线接近检测下限的指标，30% 百分比门槛噪音大（RUX 趋势信号约
    1/3 为噪音）。基线绝对值低于单位档小基数上限（×10^9/L、×10^12/L <0.5；μmol/L <10）时，趋势/幅度判据
    须同时满足绝对变化下限（≥0.3；≥3）；大基数指标的百分比判据不变。口径不变：仍是提示不发质疑。"""

    def test_abs_floor_by_unit(self):
        from monitor_v5 import abs_floor
        self.assertEqual(abs_floor(0.2, '×10^9/L'), 0.3)          # 小基数：要求同向变化 ≥0.3
        self.assertEqual(abs_floor(0.2, '/×10^9/L'), 0.3)         # 装饰斜杠写法同档
        self.assertIsNone(abs_floor(2.4, '×10^9/L'))              # 大基数：沿用百分比判据
        self.assertEqual(abs_floor(0.04, '×10^12/L'), 0.3)
        self.assertEqual(abs_floor(3.0, 'μmol/L'), 3.0)
        self.assertIsNone(abs_floor(58, 'μmol/L'))
        self.assertIsNone(abs_floor(150, 'g/L'))                  # 无档位单位不设限
        self.assertIsNone(abs_floor(None, '×10^9/L'))             # 基线缺失不设限

    @staticmethod
    def _lab(label, vals, base, unit, lo=None, hi=None):
        """趋势预警桩（与 V5Monitor._lab 同构，独立复制避免耦合）。"""
        from types import SimpleNamespace
        b = {'value': base, 'raw': str(base)}
        rows = [{'sid': 'S1', 'value': v, 'raw': str(v), 'unit': unit, 'lo': lo, 'hi': hi, 'visit': f'V{i + 1}',
                 'post': True, 'base': b, 'date': f'2026-0{2 + i}-10', 'time': None, 'sheet': 'LB', 'row': i + 2, 'wb': '',
                 'oor': (hi is not None and v > hi) or (lo is not None and v < lo), 'grade': 0} for i, v in enumerate(vals)]
        mid = 'lab:' + label
        C = SimpleNamespace(A={}, F={('S1', mid): rows}, metric={mid: {'label': label}}, cmap={}, pop={'S1'},
                            subj={'S1': {'site': '01'}}, labrows=[], others=[], cfg={'thresholds': {'base': 0.3}})
        out = []
        return C, out, (lambda C_, sid, cat, pr, summ, *a, **k: out.append((cat, pr, summ)))

    def test_trend_small_base_noise_filtered(self):
        """EO 0.05→0.12（+140%）：修前发「持续变化趋势」，修后绝对变化 0.07<0.3 不再发。"""
        import ext_rules
        import monitor_v5
        ext_rules.set_metric_dir({})
        C, out, add = self._lab('嗜酸性粒细胞', [0.06, 0.08, 0.10, 0.12], 0.05, '×10^9/L', hi=0.5)
        monitor_v5.lab_shift(C, add)
        self.assertEqual(out, [])

    def test_trend_small_base_real_change_kept(self):
        """同单位大变化（0.05→0.70，绝对 +0.65≥0.3）：趋势提示照常（判据只加噪音过滤，不砍真信号）。"""
        import ext_rules
        import monitor_v5
        ext_rules.set_metric_dir({})
        C, out, add = self._lab('嗜酸性粒细胞', [0.2, 0.3, 0.45, 0.7], 0.05, '×10^9/L', hi=1.0)
        monitor_v5.lab_shift(C, add)
        self.assertEqual([o[0] for o in out], ['持续变化趋势'])

    def test_trend_large_base_percent_judgement_unchanged(self):
        """大基数指标（基线 11 U/L）百分比判据零扰动（V5Monitor 既有行为回归）。"""
        import ext_rules
        import monitor_v5
        ext_rules.set_metric_dir({})
        C, out, add = self._lab('丙氨酸氨基转移酶', [12, 15, 19, 26], 11, 'U/L', hi=40)
        monitor_v5.lab_shift(C, add)
        self.assertEqual([o[0] for o in out], ['持续变化趋势'])

    @staticmethod
    def _rel_C(label, bv, post, lo, hi, unit):
        """REL 候选桩：行携带构建期已算好的 dev/pct（build_findings 口径），基线行 post=False。"""
        from types import SimpleNamespace
        b = {'value': bv, 'raw': str(bv), 'visit': 'D1', 'unit': unit}
        rows = [{'sid': 'S1', 'value': bv, 'raw': str(bv), 'unit': unit, 'lo': lo, 'hi': hi, 'visit': 'D1',
                 'post': False, 'base': b, 'date': '2026-01-10', 'sheet': 'LB', 'row': 2, 'wb': '',
                 'oor': False, 'grade': 0, 'clin': 0, 'dev': 0, 'pct': None, 'desc': '', 'links': []}]
        for i, v in enumerate(post):
            rows.append({'sid': 'S1', 'value': v, 'raw': str(v), 'unit': unit, 'lo': lo, 'hi': hi, 'visit': f'W{i + 2}',
                         'post': True, 'base': b, 'date': f'2026-02-{10 + i:02d}', 'sheet': 'LB', 'row': i + 3, 'wb': '',
                         'oor': v < lo or v > hi, 'grade': 0, 'clin': 0,
                         'dev': (lo - v) / lo if v < lo else ((v - hi) / hi if v > hi else 0),
                         'pct': (v - bv) / abs(bv) * 100, 'desc': '', 'links': []})
        mid = 'lab:' + label
        return SimpleNamespace(A={'labDomains': ['lab']}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, mthr=[],
                               F={(('S1', mid)): rows}, pop={'S1'}, subj={'S1': {'site': '01'}}, labrows=[],
                               src={'sheets': {}}, metric={mid: {'label': label}})

    def test_rel_small_base_filtered_and_large_kept(self):
        """幅度判据（较基线显著变化）：小基数（淋巴细胞绝对值 0.3→0.1，绝对变化 0.2<0.3）修后不成候选；
        大基数（1.5→0.6，绝对 0.9≥0.3）照常成候选——百分比门槛对大基数不变。"""
        from mm_build import rel_candidates
        import ext_rules
        ext_rules.set_metric_dir({})
        small = self._rel_C('淋巴细胞绝对值', 0.3, [0.1], lo=0.8, hi=4.0, unit='×10^9/L')
        rel_candidates(small)
        self.assertEqual([g for g in small.labrows if g['risk'] == 'REL'], [])
        large = self._rel_C('淋巴细胞绝对值', 1.5, [0.6], lo=0.8, hi=4.0, unit='×10^9/L')
        rel_candidates(large)
        self.assertEqual([g['risk'] for g in large.labrows], ['REL'])


class HIFixTermMetaGuard(unittest.TestCase):
    """F-A（双视角 IMP-01）：事件域 term 列不得被结构性元数据列（访视名称/页面名称）抢走。

    RUX 实证：AE/CM/MH 表 term 落到 VISIT（标签「访视名称」，日志页取值「共同页」）——报告事件名全表
    「共同页」。修后：具体变量名/事件名称列优先，通用「名称$」不吃 访视/页面/表单/中心 名称。夹具全虚构。"""

    def test_guess_term_skips_visit_and_page_name(self):
        from inspect_listing import guess
        names = [('访视名称', 'VISIT'), ('页面名称', 'FORMNM'), ('不良事件名称', 'AETERM')]
        self.assertEqual(guess(names, 'term'), 'AETERM')

    def test_guess_term_label_only_headers(self):
        from inspect_listing import guess
        names = [('访视名称', ''), ('合并用药名称', ''), ('页面名称', '')]
        self.assertEqual(guess(names, 'term'), '合并用药名称')

    def test_guess_visit_still_maps_visit_name(self):
        from inspect_listing import guess
        names = [('访视名称', 'VISIT'), ('不良事件名称', 'AETERM')]
        self.assertEqual(guess(names, 'visit'), 'VISIT')

    def test_sys_meta_page_columns_blocked(self):
        from inspect_listing import SYS_META, guess
        for lab in ('页面名称', '记录号', 'Flag', 'MM comment'):
            self.assertIn(lab, SYS_META, lab)
        self.assertIsNone(guess([('页面名称', 'FORMNM')], 'term'))


class HIFixTermStructGuardNormalize(unittest.TestCase):
    """第三轮 E2E（RUX 复审）：F-A 只守了映射草稿层——已确认落位的 mapping（陈旧/误确认件）里 term=VISIT 仍被
    normalize 盲信 → ae/cm/mh/proc 四域 term 全表「共同页」/「筛选期（D-28至D-1）」（RUX f6f42a6 实证）。
    修后：构建层对事件域 term 列做结构性元数据判定（与 F-A 同口径），命中则按 FIELD_SYN 重找真实术语列
    （CMTRT/MHTERM/PRTRT/AETERM 及名称类标签），找不到则置空（无术语列的表不是事件记录）。夹具全虚构。"""

    @staticmethod
    def _run(labels, vars_, rows, term_ref, dom):
        import tempfile
        import openpyxl
        from normalize_listing import Book, read_spec
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'T'
            ws.append(labels)
            ws.append(vars_)
            for r in rows:
                ws.append(r)
            wb.save(p)
            spec = {'wb': 'edc', 'sheet': 'T', 'cols': {'sid': 'SUBJID', 'term': term_ref, 'start': 'STDAT'}}
            M = {'workbooks': {'edc': str(p)}, 'domains': {}}
            return [rec for rec, *_ in read_spec(spec, {'edc': Book(str(p))}, M, dom)]

    def test_is_struct_col(self):
        from inspect_listing import is_struct_col
        for lab, var in (('访视名称', 'VISIT'), ('页面名称', 'FORMNM'), ('研究中心', 'SITENM'), ('中心编号', 'SITEID'),
                         ('受试者状态', 'SUBJSTA'), ('访视OID', 'VISTOID'), ('表单OID', 'FORMOID'), ('记录号', 'RECREP'),
                         ('', 'VISIT'), ('访视', '')):
            self.assertTrue(is_struct_col(lab, var), (lab, var))
        for lab, var in (('不良事件名称', 'AETERM'), ('药物名称', 'CMTRT'), ('疾病名称', 'MHTERM'), ('治疗名称', 'PRTRT'),
                         ('合并用药名称', ''), ('方案违背详述', ''), ('', 'AETERM')):
            self.assertFalse(is_struct_col(lab, var), (lab, var))

    def test_cm_mh_proc_term_visit_self_heals(self):
        labels = ['研究中心', '中心编号', '受试者', '访视名称', '页面名称', 'X名称', '开始日期']
        for dom, var, name in (('cm', 'CMTRT', '药物名称'), ('mh', 'MHTERM', '疾病名称'), ('proc', 'PRTRT', '治疗名称'),
                               ('ae', 'AETERM', '不良事件名称')):
            lb = list(labels)
            lb[5] = name
            vars_ = ['SITENM', 'SITEID', 'SUBJID', 'VISIT', 'FORMNM', var, 'STDAT']
            recs = self._run(lb, vars_, [['中心甲', '01', 'S1', '共同页', '既往用药 1', '虚构药甲', '2026-01-02'],
                                         ['中心甲', '01', 'S2', '筛选期', '既往用药 2', '虚构药乙', '2026-01-03']], 'VISIT', dom)
            self.assertEqual([r['term'] for r in recs], ['虚构药甲', '虚构药乙'], dom)   # 修前：['共同页', '筛选期']

    def test_label_only_term_ref_self_heals(self):
        """mapping 以中文标签引用（term=访视名称），无变量行 → 同样自愈到名称类术语列。"""
        labels = ['受试者编号', '访视名称', '合并用药名称', '开始日期']
        recs = self._run(labels, ['SUBJID', '', '', 'STDAT'],
                         [['S1', '共同页', '虚构药丙', '2026-02-01']], '访视名称', 'cm')
        self.assertEqual([r['term'] for r in recs], ['虚构药丙'])

    def test_no_real_term_column_blanks_term(self):
        """诊断勾选专表（无术语列）：term 不得退回结构性列——置空，由 main() 的空术语规则不纳入。"""
        labels = ['受试者', '访视名称', '页面名称', '是否符合诊断标准', '瘙痒症', '开始日期']
        vars_ = ['SUBJID', 'VISIT', 'FORMNM', 'MHTYN', 'MHTMACH1', 'STDAT']
        recs = self._run(labels, vars_, [['S1', '筛选期', '诊断', '是', '1', '2016-07-02']], 'VISIT', 'mh')
        self.assertEqual([r.get('term') for r in recs], [None])

    def test_non_event_domain_untouched(self):
        """非事件域（findings/subjects）不套该守卫：visit 列照常。"""
        from inspect_listing import is_struct_col
        self.assertTrue(is_struct_col('访视名称', 'VISIT'))
        labels = ['受试者', '访视名称', '检查项', '结果', '开始日期']
        vars_ = ['SUBJID', 'VISIT', 'LBTEST', 'LBORRES', 'STDAT']
        recs = self._run(labels, vars_, [['S1', '共同页', '白细胞', '5.1', '2026-01-01']], 'VISIT', None)
        self.assertEqual([r['term'] for r in recs], ['共同页'])     # dom=None：spec 原样


class HIFixEfficacySheetDomain(unittest.TestCase):
    """F-B（IMP-06/CRUX-02/EFF-RES-MAP）：量表/评分/指数类 sheet 与「总分」表头须判 efficacy 域。

    RUX 实证：IGA/EASI/SCORAD 表（表名带「评分/指数」但无锚定前缀）未识别、主要终点 IGA 无数据；
    SAR 实证：RES1/2/4/5 rTNSS/rTOSS 日记表（表名纯代码、表头带「总分」）未识别、有效性页整页空。"""

    def test_domain_re_matches_score_sheets(self):
        import inspect_listing as IL
        import re as _re
        for sh in ('IGA--研究者整体评分（IGA）', 'EASI--湿疹面积及严重程度指数评分（EASI）',
                   'SRA--特应性皮炎评分（SCORAD）-A-皮损面积', 'QLQ-C30生活质量问卷'):
            hit = next((d for d, rx in IL.DOMAIN_RE if _re.search(rx, sh)), None)
            self.assertEqual(hit, 'efficacy', sh)

    def test_domain_findings_not_hijacked(self):
        import inspect_listing as IL
        import re as _re
        for sh, want in (('LBHEMA--实验室检查-血常规', 'findings:lab'), ('VS--生命体征', 'findings:vs'),
                         ('PE--体格检查', 'findings:pe')):
            hit = next((d for d, rx in IL.DOMAIN_RE if _re.search(rx, sh)), None)
            self.assertEqual(hit, want, sh)

    def test_total_score_header_sign(self):
        """表名纯代码（RES1）但表头带「总分」→ efficacy（skill 草稿侧表头签名兜底）。"""
        import inspect_listing as IL
        dom = IL.sheet_domain_by_header('RES1', ['项目编号', '受试者编号', '评估日期(RESDAT)', 'rTNSS总分(RTNSSNUM)', 'rTOSS总分(RTOSSNUM)'])
        self.assertEqual(dom, 'efficacy')

    def test_total_score_header_negative(self):
        """检验/生命体征表头（无总分列）不被误判 efficacy。"""
        import inspect_listing as IL
        self.assertIsNone(IL.sheet_domain_by_header('LBX', ['受试者编号', '检验项目(LBTEST)', '结果(LBORRES)', '单位(LBORRESU)']))

    def test_pd_summary_sheet_header_sign(self):
        """F-H（SAR IMP-02）：CRO PD 记录表（sheet 名「总表」）表头带 方案违背详述/主分类 → pd 域，
        不再整表「未识别」而漏掉 317 条已记录 PD。"""
        import inspect_listing as IL
        dom = IL.sheet_domain_by_header('总表', ['中心号', '中心名称', '筛选号', '随机号', '访视号', '事件发生时间',
                                                'CRA发现时间', '方案违背详述', '方案违背\n主分类', '方案违背\n子分类'])
        self.assertEqual(dom, 'pd')

    def test_pd_term_prefers_detail_column(self):
        """PD 表 desc 取「方案违背详述」（详述$），不吃结构性列。"""
        from inspect_listing import guess
        names = [('中心名称', ''), ('事件发生时间', ''), ('方案违背详述', ''), ('方案违背\n主分类', '')]
        self.assertEqual(guess(names, 'term'), '方案违背详述')


class HIFixMicroPanelSplit(unittest.TestCase):
    """F-C（IMP-02）：微生物培养＋药敏 MIC 面板剥离检验异常核查。

    RUX 实证：一份「一般细菌培养」（CS）＋十余项药敏 MIC（<=0.25 等，高值列写 R>=4 断点文本）逐项判
    「CS 未关联异常」批量发质疑、标潜在 PD。修后：药敏行不入 labrows（不发质疑/不计 PD/不进风险），
    培养行保留并在上下文汇总药敏。夹具全虚构。"""

    def _mk(self, rows):
        import ext_rules
        ext_rules.set_metric_dir({})
        from types import SimpleNamespace
        from collections import defaultdict
        F = defaultdict(list)
        metric = {}
        findings = []
        for i, (test, raw, hi, desc) in enumerate(rows):
            mid = f'lab:{test}'
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = None
            try:
                hiv = float(hi)
            except (TypeError, ValueError):
                hiv = None
            r = {'sid': 'S1', 'mid': mid, 'post': True, 'clin': 2, 'value': val, 'raw': raw,
                 'lo': None, 'hi': hiv, 'unit': '', 'grade': 0, 'pct': None, 'visit': 'USV', 'date': '2026-05-01',
                 'sheet': 'LBO', 'row': 100 + i, 'wb': 'w', 'links': [], 'desc': desc, 'base': None,
                 'test': test, 'domain': 'lab', 'group': 'LBO'}
            F[('S1', mid)].append(r)
            findings.append(r)
            metric[mid] = {'id': mid, 'label': test, 'domain': 'lab', 'group': 'LBO', 'units': defaultdict(int),
                           'n': 1 if val is not None else 0, 'nq': 0 if val is not None else 1, 'hasClin': True}
        return SimpleNamespace(A={'labDomains': ['lab']}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, mthr=[],
                               F=dict(F), pop={'S1'}, subj={'S1': {'site': '01'}}, labrows=[],
                               src={'sheets': {}}, metric=metric, aeEnd={}, UNS={'USV'}, findings=findings, S={},
                               G=SimpleNamespace(has=lambda code: False), cmap={}, GL='CTCAE v5.0')

    def test_susceptibility_rows_excluded_culture_kept(self):
        from mm_build import build_labrows, micro_panel_mark
        rows = [('细菌培养', '金黄色葡萄球菌', None, 'CS'),
                ('药物A', '<=0.25', 'R>=4', '耐药；与感染AE相关'),
                ('药物B', '0.25', 'R>=4', '敏感；与感染AE相关'),
                ('药物C', '2', 'R>=8', '中介')]
        C = self._mk(rows)
        micro_panel_mark(C)
        build_labrows(C)
        # 药敏行全部剥离（不发 CS 质疑/不计潜在 PD）；培养行按既有定性口径走（数值门），不因药敏剥离而多发
        self.assertEqual([g['test'] for g in C.labrows], [])
        sus = [f for f in C.findings if f.get('_micro') == 'S']
        cul = [f for f in C.findings if f.get('_micro') == 'C']
        self.assertEqual(len(sus), 3)
        self.assertEqual(len(cul), 1)
        self.assertEqual(len(cul[0].get('_micro_sus') or []), 3)

    def test_plain_numeric_labs_unaffected(self):
        from mm_build import build_labrows, micro_panel_mark
        rows = [('尿酸', '516.00', '416.50', ''), ('白细胞', '8.91', '11.3', '')]
        C = self._mk(rows)
        micro_panel_mark(C)
        build_labrows(C)
        self.assertEqual(sorted(g['test'] for g in C.labrows), ['尿酸', '白细胞'])
        self.assertEqual([f for f in C.findings if f.get('_micro')], [])


class HIFixMicroDomainSplit(unittest.TestCase):
    """第三轮 E2E（RUX 复审）：F-C 只在 build_labrows 跳过 _micro='S'，而「CS未关联AE/MH」质疑另走 ext_rules.m23_csb
    （直接遍历 C.F 全部 clin=2 行，不看 _micro）→ 十余项药敏 MIC 仍逐条发质疑并把受试者顶上风险榜首（RUX f6f42a6
    Q164–Q172 实证：一般细菌培养＋万古霉素/克林霉素/利奈唑胺/庆大霉素…）。修后在源头分域：micro_panel_mark 先于
    build_findings，培养＋药敏行不进 C.F/C.metric（检验异常/CS/阈值/PD/风险/趋势链天然看不到），收入 C.micro 单独呈现；
    并补表名/组名命名形态判据（微生物/培养/药敏专表整表分域，不依赖同面板出现培养行）。夹具全虚构。"""

    @staticmethod
    def _row(i, test, raw, desc='', sheet='LBO', group='其他实验室检查', unit='', date='2026-05-01', clin=2):
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = None
        return {'sid': 'S1', 'sheet': sheet, 'group': group, 'domain': 'lab', 'test': test, 'value': val, 'raw': raw,
                'unit': unit, 'lo': None, 'hi': None, 'clin': clin, 'desc': desc, 'visit': 'USV', 'date': date,
                'row': 100 + i, 'wb': 'w', 'links': [], 'reason': None}

    def _C(self, findings):
        import ctcae
        from types import SimpleNamespace
        G = ctcae.load({'grading': {'version': '5.0'}})
        return SimpleNamespace(findings=findings, subj={'S1': {'site': '01', 'fd': '2026-01-01', 'ld': None}}, pop={'S1'},
                               A={}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, G=G, GL=G.label, UNS=set(), vi=lambda v: 0)

    def _panel(self):
        return [self._row(0, '一般细菌培养', '金黄色葡萄球菌', '与感染AE相关'),
                self._row(1, '药物甲', '<=0.25', '敏感；与感染AE相关'),
                self._row(2, '药物乙', '0.25', '耐药；与感染AE相关'),
                self._row(3, '药物丙', '2', '敏感；与感染AE相关'),
                self._row(4, '白细胞', '8.91', 'NA', unit='×10^9/L', clin=0),
                self._row(5, '尿酸', '516', '', unit='μmol/L')]

    def test_micro_rows_not_in_F_but_in_micro(self):
        from mm_build import build_findings, micro_panel_mark
        C = self._C(self._panel())
        micro_panel_mark(C)
        build_findings(C)
        mids = sorted(mid for _, mid in C.F)
        self.assertEqual(mids, ['lab:尿酸', 'lab:白细胞'])                # 培养与药敏都不进 C.F / C.metric
        self.assertNotIn('lab:药物甲', C.metric)
        self.assertEqual(sorted(f['test'] for f in C.micro), ['一般细菌培养', '药物丙', '药物乙', '药物甲'])
        self.assertEqual([f['_micro'] for f in C.micro if f['test'] == '一般细菌培养'], ['C'])

    def test_csb_sees_no_micro_rows(self):
        """m23_csb 只读 C.F —— 分域后对药敏/培养零发声（修前：每条 MIC 一条 CSX）。"""
        import ext_rules
        from mm_build import build_findings, micro_panel_mark
        C = self._C(self._panel())
        micro_panel_mark(C)
        build_findings(C)
        C.others, C.labrows, C.src, C.S, C.mhMatch, C.indBg, C.aeEnd = [], [], {'sheets': {}}, {'study': {}}, [], [], {}
        C.ae_by, C.mh_by = {'S1': []}, {'S1': []}
        ext_rules.m23_csb(C)
        self.assertEqual([o for o in C.others if o.get('test') in ('药物甲', '药物乙', '药物丙', '一般细菌培养')], [])

    def test_sheet_name_criterion_marks_whole_sheet(self):
        """微生物专表（表名/组名命名形态）整表分域——不依赖同面板出现「培养」行。"""
        from mm_build import micro_panel_mark
        rows = [self._row(0, '药物甲', '<=0.25', '敏感', sheet='LBMB', group='LBMB--微生物检查'),
                self._row(1, '药物乙', '4', '', sheet='LBMB', group='LBMB--微生物检查'),
                self._row(2, '涂片镜检', '见革兰阳性球菌', '', sheet='LBMB', group='LBMB--微生物检查'),
                self._row(3, '尿酸', '516', '', sheet='LBO', group='LBO--其他实验室检查')]
        C = self._C(rows)
        micro_panel_mark(C)
        self.assertEqual([f.get('_micro') for f in rows], ['S', 'S', 'C', None])
        for name in ('培养及药敏', 'MICRO', 'LB-Culture', '药物敏感试验'):
            C2 = self._C([self._row(0, '药物甲', '4', '', sheet=name, group=name)])
            micro_panel_mark(C2)
            self.assertEqual(C2.findings[0].get('_micro'), 'S', name)
        C3 = self._C([self._row(0, '尿酸', '516', '', sheet='LBCH', group='LBCH--血生化')])
        micro_panel_mark(C3)
        self.assertIsNone(C3.findings[0].get('_micro'))

    def test_kz_micro_and_subject_ext(self):
        """分域呈现：KZ.micro 紧凑行（受试者页/概况页用）＋受试者文件 ext 组「微生物培养与药敏」。"""
        from mm_build import micro_rows
        C = self._C(self._panel())
        from mm_build import build_findings, micro_panel_mark
        micro_panel_mark(C)
        build_findings(C)
        rows = micro_rows(C)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][:4], ['S1', '2026-05-01', 'USV', '一般细菌培养'])        # 培养行先于药敏
        self.assertEqual({r[6] for r in rows}, {'C', 'S'})


class HIFixAeDuplicateCounts(unittest.TestCase):
    """F-D（IMP-03）：完全重复 AE（同受试者同术语同起止）——指纹机制已有（F08），但例次/等级/SAE
    计数仍在虚增：subs 聚合、KRI ae/sae、todo AESI 例次须按去重口径；AE 明细重复行标 dup。夹具全虚构。"""

    def _C(self):
        from types import SimpleNamespace
        aes = [
            {'sid': 'S1', 't': '肺炎', 's': '2026-05-01', 'e': '2026-05-10', 'g': '3级', 'sae': True, 'aesi': True,
             'pre': False, 'te': True, '_rel': False, 'sh': 'AE', 'row': 2, 'n': 1, 'wb': '', 'c': '感染', 'soc': '',
             'pt': '肺炎', 'ib': []},
            {'sid': 'S1', 't': '肺炎', 's': '2026-05-01', 'e': '2026-05-10', 'g': '3级', 'sae': True, 'aesi': True,
             'pre': False, 'te': True, '_rel': False, 'sh': 'AE', 'row': 3, 'n': 1, 'wb': '', 'c': '感染', 'soc': '',
             'pt': '肺炎', 'ib': []},
            {'sid': 'S1', 't': '头痛', 's': '2026-05-02', 'e': '', 'g': '1级', 'sae': False, 'aesi': False,
             'pre': False, 'te': True, '_rel': False, 'sh': 'AE', 'row': 4, 'n': 2, 'wb': '', 'c': '神经系统', 'soc': '',
             'pt': '头痛', 'ib': []},
        ]
        return SimpleNamespace(A={}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, aes=aes, ae_by={'S1': aes},
                               pop={'S1'}, subj={'S1': {'site': '01', 'fd': '2026-05-01', 'status': '完成试验'}}, ae_dup=[],
                               labrows=[], queries=[], others=[], entry=[], pdd={'potential': [], 'rules': []},
                               ops={}, KZeff={'metrics': [], 'anomalies': []}, S={}, groups=[], exposure=[],
                               visits=[], efficacy=[], findings=[], centers=[], F={}), aes

    def test_fingerprint_marks_dup(self):
        from mm_build import build_events_dup
        C, aes = self._C()
        build_events_dup(C)
        self.assertTrue(aes[1].get('dup'))
        self.assertFalse(aes[0].get('dup'))
        self.assertEqual(aes[0].get('dup_n'), 2)

    def test_kri_teae_sae_dedup(self):
        import monitor_v5
        from mm_build import build_events_dup
        C, aes = self._C()
        build_events_dup(C)
        C.ops = {'cutoff': '2026-06-01', 'due': [], 'fu': {'S1': 30}, 'fresh': {}}
        k = monitor_v5.kri(C)
        self.assertEqual(k['study']['ae'], [2, 30])      # 肺炎（去重 1）＋头痛 1
        self.assertEqual(k['study']['sae'], [1, 30])


class HIFixSeverityLogic(unittest.TestCase):
    """F-E（IMP-04）：严重性逻辑核对——≥3 级 AE 未按 SAE 且 SAE 标准全未勾选须提示核实；
    gradeFloor（配置驱动，如分级标准某术语最低 N 级）低于下限疑编码/分级错误。夹具全虚构。"""

    def _C(self, A=None):
        from types import SimpleNamespace
        aes = [{'sid': 'S1', 't': '呼吸衰竭', 's': '2026-05-01', 'e': '', 'g': '3级', 'sae': False, 'sae_crit': '',
                'act': '暂停用药', 'pre': False, 'te': True, 'sh': 'AE', 'row': 2, 'n': 1, 'wb': '', 'cm': '',
                'out': '', 'rel': '', '_rel': False, '_aesi_term': False, '_aesi_def': [], 'fd': '2026-05-01',
                'pt': '呼吸衰竭', 'aesi': False}]
        return SimpleNamespace(A=A or {}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, aes=aes, ae_by={'S1': aes},
                               pop={'S1'}, subj={'S1': {'site': '01'}}, others=[], src={'sheets': {}}, aesiDefs=[], F={}), aes

    def test_grade3_not_sae_flagged(self):
        # V6 R5：严重程度≠严重性（ICH E2A）——单纯 3 级不提示；4 级、或 3 级且有住院/死亡记录才提示；化验定义事件不按此规则
        from mm_build import ae_checks
        C, _ = self._C()
        ae_checks(C)
        self.assertEqual([o for o in C.others if o['cat'] == 'AE严重性逻辑核对'], [])
        for upd in ({'g': '4级'}, {'out': '住院治疗中'}):
            C, aes = self._C()
            aes[0].update(upd)
            ae_checks(C)
            hit = [o for o in C.others if o['cat'] == 'AE严重性逻辑核对']
            self.assertEqual(len(hit), 1, upd)
            self.assertIn('呼吸衰竭', hit[0]['sum'])
        C, aes = self._C()
        aes[0].update(g='4级', t='中性粒细胞计数降低')
        ae_checks(C)
        self.assertEqual([o for o in C.others if o['cat'] == 'AE严重性逻辑核对'], [])

    def test_sae_or_low_grade_not_flagged(self):
        from mm_build import ae_checks
        C, aes = self._C()
        aes[0].update(sae=True, g='1级', act='')
        ae_checks(C)
        self.assertEqual([o for o in C.others if o['cat'] == 'AE严重性逻辑核对'], [])
        C2, aes2 = self._C()
        aes2[0].update(g='2级')
        ae_checks(C2)
        self.assertEqual([o for o in C2.others if o['cat'] == 'AE严重性逻辑核对'], [])

    def test_grade_floor_config(self):
        from mm_build import ae_checks
        C, aes = self._C({'aeChecks': ['grade_floor'], 'gradeFloor': [{'re': '衰竭', 'min': 2}]})
        aes[0].update(g='1级', sae=False, act='')
        ae_checks(C)
        hit = [o for o in C.others if o['cat'] == 'AE分级下限核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('至少 2 级', hit[0]['sum'])


class HIFixSoaPopulationAlt(unittest.TestCase):
    """F-F（CRUX-01）：SoA 替代量表（alt）机制——成人版/儿童版互为替代时按「量表家族」人群要求，
    不再对从未做该量表的人群批量判缺失（RUX CDLQI 1290 条误报）。夹具全虚构。"""

    def _C(self):
        from types import SimpleNamespace
        from collections import defaultdict
        sub = lambda sid: {'sid': sid, 'site': '01', 'visit': 'D1', 'sheet': '成表', 'row': 1, 'group': '成表'}
        # 成人 A 只做成表量表；儿童 B 只做儿表量表；C 两者都没做过（不在家族人群）
        findings = []
        for sid in ('A', 'B', 'B'):
            findings.append({'sid': sid, 'site': '01', 'visit': 'D1', 'sheet': '成表' if sid == 'A' else '儿表',
                             'row': len(findings) + 2, 'group': '成表' if sid == 'A' else '儿表', 'done': ''})
        visits = [{'sid': s, 'visit': 'D1', 'date': '2026-05-01'} for s in ('A', 'B', 'C')]
        return SimpleNamespace(
            A={'soa': [{'name': '生活质量-成人', 'sheet': '成表', 'visits': ['D1'], 'cond': False, 'alt': ['儿表']}]},
            pop={'A', 'B', 'C'}, subj={s: {'site': '01'} for s in 'ABC'},
            visits=visits, findings=findings, efficacy=[], VIS=['D1'], UNS=set(),
            isAgg=lambda v: True, S={})

    def test_alt_satisfies_and_population_limited(self):
        from mm_build import build_soa
        C = self._C()
        build_soa(C)
        row = next(r for r in C.soa if r['name'] == '生活质量-成人')
        cell = row['cells']['D1']
        self.assertEqual(cell[0], 2)                    # 人群＝做过家族任一量表的 A、B（C 不在）
        self.assertEqual(cell[3], 0)                    # B 由儿表替代满足 → 无缺失
        self.assertEqual(cell[4], [])

    def test_missing_when_family_member_lacks_visit(self):
        from mm_build import build_soa
        C = self._C()
        C.visits.append({'sid': 'B', 'visit': 'W2', 'date': '2026-05-15'})
        C.findings.append({'sid': 'A', 'site': '01', 'visit': 'W2', 'sheet': '成表', 'row': 9, 'group': '成表', 'done': ''})
        C.VIS = ['D1', 'W2']
        C.A['soa'][0]['visits'].append('W2')
        build_soa(C)
        row = next(r for r in C.soa if r['name'] == '生活质量-成人')
        cell = row['cells']['W2']
        self.assertEqual(cell[3], 1)
        self.assertEqual(cell[4], ['B'])                # B W2 既无成表也无儿表 → 缺失


class HIFixVisitIdentBeforeFold(unittest.TestCase):
    """F-G（SAR IMP-01）：带明确访视号（V6/V7/W28）的标签不得被「随访期→FU」融合——
    V6/V7 并成 FU 后 342/345 条访视窗全部失配成虚假逾期。夹具全虚构。"""

    def test_visit_code_numbered_fu_kept(self):
        from inspect_listing import visit_code
        self.assertEqual(visit_code('安全性随访期V6（D57±3d）', ['V6', 'V7']), 'V6')
        self.assertEqual(visit_code('安全性随访期V7（D85±3d）', ['V6', 'V7']), 'V7')
        self.assertEqual(visit_code('安全性随访-28W（D197+7天）', []), 'W28')
        self.assertEqual(visit_code('双盲治疗期-2W（D15±3天）', []), 'W2')

    def test_visit_code_keywords_unchanged(self):
        from inspect_listing import visit_code
        self.assertEqual(visit_code('安全性随访', []), 'FU')
        self.assertEqual(visit_code('治疗结束', []), 'EOT')
        self.assertEqual(visit_code('筛选期（D-28至D-1）', []), 'SCR')
        self.assertEqual(visit_code('计划外访视(2025-11-28)', []), 'USV')
        self.assertEqual(visit_code('双盲治疗期V2（D1）', ['D1']), 'D1')


class HIFixPregnancyEscalation(unittest.TestCase):
    """F-I（PREG-ESCALATION）：妊娠暴露升级——妊娠试验阳性之外，影像/描述性「宫内早孕」也须识别；
    按受试者合并为一条 pr4 妊娠暴露核查（结局随访、避孕依从），不再只按单条检验发常规质疑。夹具全虚构。"""

    def _C(self, rows):
        from types import SimpleNamespace
        from collections import defaultdict
        import ext_rules
        ext_rules.set_metric_dir({})
        F = defaultdict(list)
        metric = {}
        for i, (mid, test, raw, desc) in enumerate(rows):
            r = {'sid': 'S1', 'mid': mid, 'post': True, 'clin': 2, 'value': None, 'raw': raw, 'lo': None,
                 'hi': None, 'unit': '', 'grade': 0, 'pct': None, 'visit': 'USV', 'date': '2026-05-01',
                 'sheet': 'LB', 'row': 10 + i, 'wb': 'w', 'links': [], 'desc': desc, 'base': None,
                 'test': test, 'domain': 'lab', 'group': 'LB'}
            F[('S1', mid)].append(r)
            metric[mid] = {'id': mid, 'label': test, 'domain': 'lab', 'group': 'LB', 'units': defaultdict(int),
                           'n': 0, 'nq': 1}
        return SimpleNamespace(A={}, cfg={}, F=dict(F), pop={'S1'}, subj={'S1': {'site': '01'}}, others=[],
                               src={'sheets': {}}, metric=metric), None

    def test_positive_hcg_and_scan_consolidated(self):
        from ext_rules import m18_preg
        C, _ = self._C([('lab:血HCG', '血HCG', '阳性', ''),
                        ('exam:妇科彩超', '妇科彩超', '宫内早孕（孕约6+周）', '早孕CS')])
        m18_preg(C)
        hit = [o for o in C.others if o['cat'] == '妊娠暴露核查']
        self.assertEqual(len(hit), 1)
        self.assertIn('结局随访', hit[0]['sum'] + str(hit[0].get('why') or ''))

    def test_negative_preg_test_not_flagged(self):
        from ext_rules import m18_preg
        C, _ = self._C([('lab:血HCG', '血HCG', '阴性', '')])
        C.F[('S1', 'lab:血HCG')][0]['clin'] = None
        m18_preg(C)
        self.assertEqual([o for o in C.others if '妊娠' in o['cat']], [])


class HIFixEffMissingAction(unittest.TestCase):
    """F-J（IMP-06）：配置了的有效性终点指标在数据中完全无记录 → 升级为可见行动项（不是静默空页）。"""

    def test_missing_endpoint_becomes_action(self):
        from types import SimpleNamespace
        from collections import defaultdict
        from mm_build import build_eff
        M = [{'id': 'iga', 'label': 'IGA', 'src': 'eff:IGA得分', 'visits': ['D1', 'W8'], 'keyVisit': 'W8'}]
        C = SimpleNamespace(A={'efficacy': M}, cfg={}, pop={'S1'}, subj={'S1': {'site': '01'}},
                            efficacy=[], F={}, visits=[{'sid': 'S1', 'visit': 'W8'}],
                            effsub=defaultdict(dict), effmag=[], effRules=[], vi=lambda v: 0)
        build_eff(C)
        self.assertEqual([x['id'] for x in C.KZeff.get('missing', [])], ['iga'])
        self.assertTrue(any('IGA' in t[2] for t in getattr(C, 'todo', [])) or C.KZeff.get('missing'))


class R2FixPagePrefixedSheetDomain(unittest.TestCase):
    """R2-2（D002 E2E build ec34087 零信号定罪后的泛化修）：EDC 导出常见「(页号)表名」结构性前缀——
    DOMAIN_RE 的 ^锚定使 (59)不良事件/(48)研究药物给药/(7)人口统计学 全部未命中 → subjects/exposure 域
    从未进草稿 → norm 无 subjects/exposure → 分析人群 C.pop=0 → queries/others/受试者页全零
    （实测：D002 全簿 69 sheet 仅 4 个 PK 采血表靠表头签名识别，其余全部「—」）。
    修法＝域识别入口剥页号前缀（形态归一）＋参与者/人口统计通用命名变体；不写死任何研究表名。"""

    def test_page_prefixed_core_domains_detected(self):
        import inspect_listing as IL
        for sh, want in (('(59)不良事件', 'ae'), ('(9)病史', 'mh'), ('(60)合并用药', 'cm'),
                         ('(48)研究药物给药', 'exposure'), ('(7)人口统计学', 'subjects'),
                         ('(1)参与者信息', 'subjects'), ('(4)随机', 'subjects'),
                         ('(63)治疗结束页', 'subjects'), ('(66)研究结束页', 'subjects'),
                         ('(2)访视日期', 'visits'), ('(18)心电图单次', 'findings:ecg'),
                         ('(17)生命体征', 'findings:vs'), ('(14)体格检查_1', 'findings:pe'),
                         ('(29)实验室检查-血常规_1', 'findings:lab'),
                         ('(60)既往及合并用药', 'cm'), ('(61)既往及合并非药物治疗', 'proc'),
                         ('(10)个人史', 'mh'), ('(11)月经史', 'mh'), ('(12)孕产史', 'mh'),
                         ('(45)尿妊娠试验', 'findings:lab'), ('(55)骨密度检查DXA', 'findings:exam')):
            self.assertEqual(IL.domain_of_sheet(sh), want, sh)

    def test_page_prefix_forms(self):
        """页号前缀形态归一：半/全角括号页号、数字序号点/顿号/横线，剥后为空则保留原名。"""
        import inspect_listing as IL
        self.assertEqual(IL.strip_page_prefix('(59)不良事件'), '不良事件')
        self.assertEqual(IL.strip_page_prefix('（一）病史'), '病史')
        self.assertEqual(IL.strip_page_prefix('01.实验室检查'), '实验室检查')
        self.assertEqual(IL.strip_page_prefix('2、不良事件'), '不良事件')
        self.assertEqual(IL.strip_page_prefix('3-生命体征'), '生命体征')
        self.assertEqual(IL.strip_page_prefix('(1)'), '(1)')          # 纯页号不是前缀（原名保留）
        self.assertEqual(IL.strip_page_prefix('不良事件'), '不良事件')  # 无前缀不变

    def test_plain_and_first_label_paths_unchanged(self):
        """无前缀表名与首列标签兜底路径保持既有行为（LBHEMA/RES1 式不回归）。"""
        import inspect_listing as IL
        self.assertEqual(IL.domain_of_sheet('不良事件'), 'ae')
        self.assertEqual(IL.domain_of_sheet('LBHEMA--实验室检查-血常规'), 'findings:lab')
        self.assertEqual(IL.domain_of_sheet('RES1', 'rTNSS总分(RTNSSNUM)'), None)  # 总分签名走 sheet_domain_by_header，不在此判

    def test_dm_sid_set_check_uses_stripped_name(self):
        """DM 表选取（「受试者编号不在 DM」核查）同样剥页号前缀：(7)人口统计学 作为 DM 基准可被选中。"""
        import inspect_listing as IL
        import re as _re
        self.assertTrue(IL.is_subjects_sheet('(7)人口统计学'))
        self.assertTrue(IL.is_subjects_sheet('DM'))
        self.assertFalse(IL.is_subjects_sheet('(59)不良事件'))
        self.assertFalse(bool(_re.search(IL.DOMAIN_RE[0][1], '(7)人口统计学')))   # 修前：裸正则确实不命中（红证据锚点）


class R2FixEligibilitySubjectTypeGuard(unittest.TestCase):
    """R2-2 连带缺陷（D002 仿真实证）：eligibilitySubject 拿受试者字段原值对照数值阈值——
    文本型数值（'47'）或字段缺失（None）直接 TypeError 崩构建。此前 C.pop=0 时从未走到该分支
    （零信号掩盖了它）。修法＝不可数值化的取值不参与比较（跳过，不猜）。"""

    def _run(self, age):
        from types import SimpleNamespace
        from mm_build import eligibility_checks
        C = SimpleNamespace(pop={'S1'}, subj={'S1': {'age': age, 'site': '01'}},
                            A={'eligibilitySubject': [{'id': 'IE-I2', 'field': 'age', 'op': '<', 'v': 18.0,
                                                       'label': '年龄', 'text': '入选标准：年龄18~50周岁'}]},
                            others=[])
        eligibility_checks(C)
        return C.others

    def test_text_numeric_age_not_crashing(self):
        out = self._run('47')                     # 文本型数值：不崩、按 47 判定（≥18 不符的不发）
        self.assertEqual(out, [])

    def test_underage_text_age_flagged(self):
        out = self._run('16')                     # 文本型且确实不符 → 照发
        self.assertEqual(len(out), 1)
        self.assertIn('16', out[0]['sum'])

    def test_missing_field_skipped(self):
        self.assertEqual(self._run(None), [])     # 字段缺失：不可比较，跳过不崩

    def test_numeric_age_unchanged(self):
        self.assertEqual(self._run(47.0), [])     # 数值路径不回归
        self.assertEqual(len(self._run(16.0)), 1)


class F8UnifiedNumericParse(unittest.TestCase):
    """F8（RUX 第 12 条升级，R3）：文本→数值解析统一——「N分-中度」「重度（2）」内嵌分数/级别词、
    「<1*10^3」「1×10³」科学计数（上标丢失形态）、「<50」检测下限删失。修前四形态 value 全空/错值
    （「<1*10^3」const hi=1.0 丢 ×10³；「<50」被 to_num 读成 50 参与超上限比较）。夹具全虚构。"""

    def test_embedded_score_and_grade_word(self):
        from common import num_state
        self.assertEqual(num_state('3分-中度。可能有粉红色的红斑'), ('value', 3.0))
        self.assertEqual(num_state('中度（2）'), ('value', 2.0))
        self.assertEqual(num_state('重度（4）'), ('value', 4.0))
        self.assertEqual(num_state('2-中度'), ('value', 2.0))
        self.assertIsNone(num_state('轻度'))                       # 裸分级词不赋数值（审阅者 2026-11-09）
        self.assertIsNone(num_state('轻度升高说明'))          # 非裸分级词的描述文本不猜数值
        for q in ('1+', '2+', '4+', '±', '+++', '1 +'):
            self.assertIsNone(num_state(q), q)                # 半定量分级是定性强度不是数值（ext1 真值口径）

    def test_scientific_notation_forms(self):
        from common import num_state
        self.assertEqual(num_state('<1*10^3'), ('below', 1000.0))
        self.assertEqual(num_state('5.26×10^3'), ('value', 5260.0))
        self.assertEqual(num_state('<1×10³'), ('below', 1000.0))       # 上标丢失形态
        self.assertEqual(num_state('1.00E+02'), ('value', 100.0))
        self.assertEqual(num_state('<1.00E+02'), ('below', 100.0))

    def test_censored_bound_not_value(self):
        from common import num_state
        self.assertEqual(num_state('<50'), ('below', 50.0))            # 检测下限形态：删失，不作确切值
        self.assertEqual(num_state('阴性'), ('neg', None))

    def test_bound_magnitude_for_const_hi(self):
        from common import num_bound
        self.assertEqual(num_bound('<1*10^3 拷贝数/mL'), 1000.0)       # 修前 to_num → None / 1.0
        self.assertEqual(num_bound('≤40'), 40.0)
        self.assertEqual(num_bound(139), 139.0)

    def test_findings_parses_score_and_censored(self):
        import tempfile
        import openpyxl
        from normalize_listing import Book, findings
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'score.xlsx'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'SCORE'
            ws.append(['受试者编号', '访视', '评估日期', '得分', '结果单位'])
            ws.append(['S1', '筛选期', '2026-05-01', '3分-中度。虚构描述', '分'])
            ws.append(['S1', 'W2', '2026-06-01', '中度（2）', '分'])
            wb.save(p)
            M = {'workbooks': {'edc': str(p)}, 'clin_map': [['正常', 0]], 'domains': {}}
            spec = {'wb': 'edc', 'sheet': 'SCORE', 'domain': 'efficacy', 'group': '虚构量表', 'label_row': 1,
                    'var_row': 0, 'data_start': 2,
                    'cols': {'sid': '受试者编号', 'visit': '访视', 'date': '评估日期', 'test': '得分', 'value': '得分'},
                    'const': {'hi': '<1*10^3 拷贝数/mL'}}
            rows = findings(spec, {'edc': Book(str(p))}, M)
            self.assertEqual([r['value'] for r in rows], [3.0, 2.0])   # 修前全 None（主要终点趋势丢失）
            self.assertTrue(all(r['hi'] == 1000.0 for r in rows))      # 修前 const hi 为 None/1.0
            ws.append(['S2', '筛选期', '2026-05-02', '<50', '拷贝数/mL'])
            wb.save(p)
            rows2 = findings(spec, {'edc': Book(str(p))}, M)
            cen = next(r for r in rows2 if r['sid'] == 'S2')
            self.assertEqual((cen['value'], cen['raw']), (None, '<50'))   # 删失：不做确切值比较


class F1F2F3DrugClass(unittest.TestCase):
    """F1（非镇静抗组胺）/F2（吸入不入外用）/F3（单药类属措辞）——引擎判定侧。全部虚构药名/条款。"""

    @staticmethod
    def _C(prohibited=None, washout=None):
        from types import SimpleNamespace
        from collections import defaultdict
        import mm_build
        A = {}
        if prohibited is not None:
            A['prohibited'] = prohibited
        if washout is not None:
            A['washout'] = washout
        C = SimpleNamespace(A=A, pop={'S1'}, subj={'S1': {'fd': '2024-06-01', 'ld': '2024-12-01', 'lo': '', 'icf': '2024-05-20',
                                                           'site': '01'}},
                            cm_by=defaultdict(list), others=[], tl=defaultdict(dict), proc=[])
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        return C, orig, mm_build

    @staticmethod
    def _run(C, orig, mm_build):
        try:
            mm_build.cm_checks(C)
        finally:
            mm_build.oth_qkey = orig
        return [o['sum'] for o in C.others]

    def test_f1_nonsedating_exempt_from_sedating_clause(self):
        """F1：条款「镇静抗组胺药（允许使用非镇静抗组胺药）」——虚构药「某西替利嗪」（二代写法）修前命中、
        修后不命中；同条款「苯海拉明」（一代镇静）仍命中。"""
        C, orig, mb = self._C(prohibited=[{'name': '镇静抗组胺药', 'note': '例外：允许使用非镇静抗组胺药',
                                           're': '氯雷他定|西替利嗪|苯海拉明|氯苯那敏', 'pr': 4}])
        C.cm_by['S1'] = [{'t': '某西替利嗪片', 'rt': '口服', 's': '2024-07-01', 'e': '2024-07-02', 'ong': False,
                          'why': '虚构适应症', 'sh': 'CM', 'row': 1, 'wb': ''},
                         {'t': '苯海拉明片', 'rt': '口服', 's': '2024-07-01', 'e': '2024-07-02', 'ong': False,
                          'why': '虚构适应症', 'sh': 'CM', 'row': 2, 'wb': ''}]
        hit = self._run(C, orig, mb)
        self.assertTrue(any('苯海拉明' in h for h in hit), hit)                 # 一代镇静照常命中
        self.assertFalse(any('西替利嗪' in h for h in hit), hit)                # 二代非镇静不命中（修前命中，红）
        # 无「允许非镇静」措辞的镇静条款：两类都命中（不放宽）
        C2, orig2, mb2 = self._C(prohibited=[{'name': '镇静抗组胺药', 're': '氯雷他定|西替利嗪|苯海拉明', 'pr': 4}])
        C2.cm_by['S1'] = [dict(C.cm_by['S1'][0], row=9)]
        hit2 = self._run(C2, orig2, mb2)
        self.assertTrue(any('西替利嗪' in h for h in hit2), hit2)

    def test_f1_washout_honors_except_re(self):
        """F1：洗脱条目 exceptRe（编译层从条款原文「允许非镇静」生成的例外）同口径生效。"""
        C, orig, mb = self._C(washout=[{'name': '镇静抗组胺药', 're': '氯雷他定|西替利嗪|苯海拉明', 'days': 14, 'ref': 'fd',
                                        'exceptRe': '氯雷他定|西替利嗪'}])
        C.cm_by['S1'] = [{'t': '某氯雷他定片', 'rt': '口服', 's': '2024-05-25', 'e': '2024-05-28', 'ong': False, 'why': '',
                          'sh': 'CM', 'row': 1, 'wb': ''},
                         {'t': '苯海拉明片', 'rt': '口服', 's': '2024-05-25', 'e': '2024-05-28', 'ong': False, 'why': '',
                          'sh': 'CM', 'row': 2, 'wb': ''}]
        hit = [s for s in self._run(C, orig, mb) if '洗脱' in s]
        self.assertTrue(any('苯海拉明' in s for s in hit), hit)
        self.assertFalse(any('氯雷他定' in s for s in hit), hit)                # 修前 washout 不认 exceptRe（红）

    def test_f2_inhaled_not_topical_washout(self):
        """F2：吸入复方不入「外用疗法」洗脱（外用＝皮肤局部；吸入/鼻用/眼用/注射除外）。虚构「某吸入用复方」。"""
        C, orig, mb = self._C(washout=[{'name': '其他外用疗法', 're': '莫米松|布地奈德|某复方', 'days': 7, 'ref': 'fd',
                                        'route': 'topical'}])
        C.cm_by['S1'] = [{'t': '吸入用某复方混悬液', 'rt': '雾化吸入', 's': '2024-05-20', 'e': '2024-05-30', 'ong': False,
                          'why': '', 'sh': 'CM', 'row': 1, 'wb': ''},
                         {'t': '某莫米松乳膏', 'rt': '外用', 's': '2024-05-20', 'e': '2024-05-30', 'ong': False,
                          'why': '', 'sh': 'CM', 'row': 2, 'wb': ''}]
        hit = [s for s in self._run(C, orig, mb) if '洗脱' in s]
        self.assertTrue(any('莫米松乳膏' in s for s in hit), hit)               # 皮肤局部照常命中
        self.assertFalse(any('吸入' in s for s in hit), hit)                    # 修前吸入复方被套外用洗脱（红）
        # route 未写但名称含「外用」的洗脱条目同口径
        C2, orig2, mb2 = self._C(washout=[{'name': '外用疗法洗脱', 're': '莫米松|某复方', 'days': 7, 'ref': 'fd'}])
        C2.cm_by['S1'] = [dict(C.cm_by['S1'][0])]
        hit2 = [s for s in self._run(C2, orig2, mb2) if '洗脱' in s]
        self.assertFalse(any('吸入' in s for s in hit2), hit2)

    def test_f3_wording_lists_hit_classes_only(self):
        """F3：单药类属描述只列该药实际命中的类（顿号连接），无命中写「禁用类待核对」——不再贴整段禁用类清单。"""
        C, orig, mb = self._C(prohibited=[{'name': '类甲、类乙及类丙', 're': '某甲|某乙|某丙', 'pr': 4,
                                           'classes': [['类甲', '某甲'], ['类乙', '某乙']]}])
        C.cm_by['S1'] = [{'t': '某乙片', 'rt': '口服', 's': '2024-07-01', 'e': '2024-07-02', 'ong': False, 'why': '',
                          'sh': 'CM', 'row': 1, 'wb': ''},
                         {'t': '某丙片', 'rt': '口服', 's': '2024-07-01', 'e': '2024-07-02', 'ong': False, 'why': '',
                          'sh': 'CM', 'row': 2, 'wb': ''}]
        hit = [h for h in self._run(C, orig, mb) if '属于' in h]
        self.assertTrue(any('属于类乙' in h and '类甲' not in h and '类丙' not in h for h in hit), hit)   # 修前贴整段（红）
        self.assertTrue(any('禁用类待核对' in h for h in hit), hit)             # 某丙：classes 无命中
        # 无 classes 字段的旧配置：措辞回退条目名（不回归）
        C2, orig2, mb2 = self._C(prohibited=[{'name': '类甲', 're': '某甲', 'pr': 4}])
        C2.cm_by['S1'] = [dict(C.cm_by['S1'][0], t='某甲片')]
        hit2 = self._run(C2, orig2, mb2)
        self.assertTrue(any('属于类甲' in h for h in hit2), hit2)


class F9GateNumericAtom(unittest.TestCase):
    """F9①（E14 合取保持，引擎侧）：数值原子带 gate（要求「X 阳性」伴随）——X 不可得降为请核实，
    X 阴性不发；不再把「X阳性且 Y≥N」拆成 Y 单独成立的析取。虚构指标。"""

    @staticmethod
    def _run(dna_rows, hbsag_rows):
        from types import SimpleNamespace
        from collections import defaultdict
        import mm_build
        E = {'id': 'IE-E14', 'metric': r'^lab:.*虚构载量', 'op': '>=', 'v': 1000.0, 'on': 'val', 'kind': 'exclusion',
             'text': '排除标准 14：虚构抗原A阳性且虚构载量≥1×10^3拷贝数/mL', 'pick': 'any',
             'gate': {'metric': r'^lab:.*虚构抗原A', 'label': '虚构抗原A', 're': '阳性|\\+|检出'}}
        C = SimpleNamespace(A={'eligibility': [E]}, pop={'S1'},
                            subj={'S1': {'site': '01', 'rand_d': None, 'fd': '2026-01-10'}},
                            F=defaultdict(list), others=[], metric={'lab:虚构载量': {'label': '虚构载量'},
                                                                    'lab:虚构抗原A': {'label': '虚构抗原A'}},
                            src={'sheets': {}}, cfg={'visits': {}}, UNS=set(), VIS=[])
        for r in dna_rows:
            C.F[('S1', 'lab:虚构载量')].append(r)
        for r in hbsag_rows:
            C.F[('S1', 'lab:虚构抗原A')].append(r)
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        try:
            mm_build.eligibility_checks(C)
        finally:
            mm_build.oth_qkey = orig
        return C.others

    @staticmethod
    def _dna(v):
        return {'sid': 'S1', 'mid': 'lab:虚构载量', 'test': '虚构载量', 'visit': 'SCR', 'date': '2026-01-05', 'raw': str(v),
                'value': float(v), 'unit': '拷贝数/mL', 'lo': None, 'hi': None, 'clin': None, 'post': False,
                'sheet': 'LB', 'row': 3, 'wb': '', 'links': []}

    def test_numeric_gate_hold_and_release(self):
        # 伴随阳性不可得 → 请核实（undetermined），不直接判排除
        out = self._run([self._dna(5000)], [])
        self.assertEqual(len(out), 1)
        self.assertIn('请核实', out[0]['sum'])
        self.assertEqual(out[0].get('_elig'), 'undetermined')
        # 伴随阴性 → 不发（gate 不满足）
        self.assertEqual(self._run([self._dna(5000)], [{'sid': 'S1', 'mid': 'lab:虚构抗原A', 'test': '虚构抗原A',
                                                       'visit': 'SCR', 'date': '2026-01-05', 'raw': '阴性', 'value': None,
                                                       'unit': '', 'lo': None, 'hi': None, 'clin': None, 'post': False,
                                                       'sheet': 'LB', 'row': 4, 'wb': '', 'links': []}]), [])
        # 伴随阳性 → 判排除（violated）
        out3 = self._run([self._dna(5000)], [{'sid': 'S1', 'mid': 'lab:虚构抗原A', 'test': '虚构抗原A', 'visit': 'SCR',
                                              'date': '2026-01-05', 'raw': '阳性', 'value': None, 'unit': '', 'lo': None,
                                              'hi': None, 'clin': None, 'post': False, 'sheet': 'LB', 'row': 4, 'wb': '',
                                              'links': []}])
        self.assertEqual(len(out3), 1)
        self.assertEqual(out3[0].get('_elig'), 'violated')


class RuxWaveTemplateContract(unittest.TestCase):
    """V6 RUX 第 1 轮修复波（引擎模板契约）：F5 档位键回退、F6① 新鲜度如实、F7 交付说明、
    F10 构建缺口可见、F12 屏幕清理（前缀/页脚哈希/CS 页头/命令行文案/泳道截断）。"""

    A = ROOT / 'templates/site/assets'

    def test_f5_tier_key_fallback_not_global(self):
        t = (self.A / 'kz.js').read_text(encoding='utf-8')
        t2 = (self.A / 'kz-tier.js').read_text(encoding='utf-8')
        for name, txt in (('kz.js', t), ('kz-tier.js', t2)):
            self.assertIn("project||{}).id||(typeof location", txt, name)      # 回退项目 id/报告路径（非全局键）
            self.assertNotIn("code||'')", txt.replace("code||((window", "code||(("), name)
        self.assertIn("K.thrKey='kz.thr:'", t)

    def test_f6_index_freshness_no_unconditional_assert(self):
        t = (self.A / 'p-index.js').read_text(encoding='utf-8')
        self.assertNotIn("K.p('各中心数据均在 30 天内','grn')", t)             # 无条件断言禁用
        self.assertIn('无分中心新鲜度数据', t)
        self.assertIn('个中心 >30 天无新数据', t)

    def test_f7_delivery_reads_actual_file(self):
        t = (self.A / 'p-queries.js').read_text(encoding='utf-8')
        self.assertIn('href="../${K.esc((K.cfg().query||{}).file', t)          # 交付文件相对链接
        self.assertNotIn("||'申办方MM_query_首列版.xlsx'", t)                  # 不再硬编码首列版兜底

    def test_f10_gaps_visible_on_study_page(self):
        t = (self.A / 'p-study.js').read_text(encoding='utf-8')
        self.assertIn('构建缺口', t)
        self.assertIn('(window.KZS||{}).gaps', t)

    def test_f12_cleanup(self):
        kz = (self.A / 'kz.js').read_text(encoding='utf-8')
        self.assertNotIn('AI审阅·)(K.CATN', kz)                                # 前缀不再保留显示
        self.assertNotIn('>CS 待确认 ${pend}</a>', kz)                         # 页头红标移除
        self.assertIn("K.esc(b.buildId||'—')", (self.A / 'p-study.js').read_text(encoding='utf-8'))  # 版本一行进研究依据页
        k6 = (self.A / 'kz6.js').read_text(encoding='utf-8')
        self.assertNotIn('(d.cm||[]).slice(0,30)', k6)                         # 用药泳道不 30 截断
        ps = (self.A / 'p-safety.js').read_text(encoding='utf-8')
        self.assertIn('AESI 定义', ps)                                         # 安全性概览补 AESI 清单
        self.assertIn('转归为死亡的 AE', ps)                                   # 死亡 0 例明示


class V6Generalization(unittest.TestCase):
    """V6（审阅者 2026-11-02，四项目泛化复盘）：访视对齐、指标重绑、DILI 布尔、共用临床意义、参考范围按页合并、
    妊娠规则、受试者内稳定指标、部分日期首剂前判定、严重性。夹具全虚构。"""

    def _vis(self, W, visits, subj=None):
        from types import SimpleNamespace
        subj = subj or {f'S{i}': {'site': '01', 'fd': '2026-01-01', 'status': '已入组'} for i in range(1, 5)}
        return SimpleNamespace(A={'visitWindows': W}, subj=subj, visits=visits, pop=set(subj), S={}, cfg={}, efficacy=[], findings=[])

    def test_visit_alias_by_window_share(self):
        from monitor_v5 import _add, visit_due
        W = {'V5': [15, 3, 3], 'V6': [29, 3, 3], 'V9': [200, 5, 5]}
        vs = [{'sid': f'S{i}', 'visit': c, 'date': _add('2026-01-01', d - 1)} for i in range(1, 5) for c, d in (('W2', 15), ('W4', 30))]
        C = self._vis(W, vs)
        due, _ = visit_due(C, '2026-12-31')
        st = {(d[0], d[2]): d[6] for d in due}
        self.assertEqual(C._visit_alias, {'V5': 'W2', 'V6': 'W4'})
        self.assertEqual(C._visit_unmapped, ['V9'])               # 窗内没有任何数据代码 → 未映射，不推算逾期
        self.assertEqual(st[('S1', 'V5')], 'ok')
        self.assertEqual(st[('S1', 'V6')], 'ok')
        self.assertNotIn(('S1', 'V9'), st)

    def test_visit_alias_shared_code_assigns_nearest(self):
        from monitor_v5 import _add, visit_due
        W = {'V1': [1, 0, 0], 'V6': [60, 5, 5], 'V7': [90, 5, 5]}
        vs = []
        for i in range(1, 5):
            vs += [{'sid': f'S{i}', 'visit': 'V1', 'date': '2026-01-01'},
                   {'sid': f'S{i}', 'visit': 'FU', 'date': _add('2026-01-01', 59)},
                   {'sid': f'S{i}', 'visit': 'FU', 'date': _add('2026-01-01', 91)}]
        C = self._vis(W, vs)
        due, _ = visit_due(C, '2026-12-31')
        st = {(d[0], d[2]): (d[6], d[5]) for d in due}
        self.assertEqual(C._visit_alias.get('V6'), 'FU')
        self.assertEqual(st[('S1', 'V6')], ('ok', _add('2026-01-01', 59)))
        self.assertEqual(st[('S1', 'V7')][0], 'ok')               # 同一 FU 代码的第二条配给 V7，不判逾期
        self.assertEqual(st[('S1', 'V7')][1], _add('2026-01-01', 91))

    def test_zero_record_without_mismatch_still_overdue(self):
        from monitor_v5 import visit_due
        C = self._vis({'W2': [15, 3, 3], 'W8': [57, 3, 3]},
                      [{'sid': f'S{i}', 'visit': 'W2', 'date': '2026-01-15'} for i in range(1, 5)])
        due, _ = visit_due(C, '2026-06-01')
        self.assertEqual(C._visit_unmapped, [])
        self.assertTrue(any(d[2] == 'W8' and d[6] == 'overdue' for d in due))

    def test_rebind_bracket_abbreviation(self):
        import bind
        metrics = {'lab:丙氨酸基转移酶（ALT）': {'label': '丙氨酸基转移酶（ALT）'}, 'lab:AST/ALT比值': {'label': 'AST/ALT比值'}}
        new, hits = bind.rebind_one(r'^lab:(?:丙氨酸氨基转移酶|(ALT|SGPT|GPT)\b)', metrics)
        self.assertEqual(hits, ['lab:丙氨酸基转移酶（ALT）'])
        self.assertTrue(re.search(new, 'lab:丙氨酸基转移酶（ALT）'))
        self.assertEqual(bind.rebind_one(r'^lab:AST', metrics), (None, []))   # 原正则有命中 → 不动
        new, hits = bind.rebind_one(r'^vs:收缩压', {'lab:收缩压': {'label': '收缩压'}})
        self.assertEqual(hits, ['lab:收缩压'])

    def test_rebind_eff_by_name_core(self):
        from types import SimpleNamespace
        import bind
        C = SimpleNamespace(A={'efficacy': [{'id': 'p', 'label': 'PGI-C总分', 'src': 'eff:PGI-C总分'},
                                            {'id': 'h', 'label': 'Hb', 'src': 'lab:血红蛋白'}]},
                            efficacy=[{'metric': 'PGI-C量表总得分'}, {'metric': 'NRS量表总得分'}],
                            metric={'lab:血红蛋白（Hb）': {'label': '血红蛋白（Hb）'}, 'lab:平均红细胞血红蛋白含量（MCH）': {}})
        notes = []
        bind.rebind_eff(C, notes)
        self.assertEqual(C.A['efficacy'][0]['src'], 'eff:PGI-C量表总得分')
        self.assertEqual(C.A['efficacy'][1]['src'], 'lab:血红蛋白（Hb）')
        self.assertEqual(len(notes), 2)

    def test_pct_loss_rule_direction(self):
        from mm_build import pct_rule_norm
        self.assertEqual(pct_rule_norm({'on': 'pct', 'op': '>', 'v': 5.0, 'label': '骨密度丢失 > 5'}), ('<', -5.0))
        self.assertEqual(pct_rule_norm({'on': 'pct', 'op': '>', 'v': 20.0, 'label': '体重增加 > 20'}), ('>', 20.0))
        self.assertEqual(pct_rule_norm({'on': 'pct', 'op': '<', 'v': -5.0, 'label': '骨密度丢失'}), ('<', -5.0))   # 已编译为负值不再翻转

    def test_dili_yes_parsing(self):
        from common import yes
        self.assertFalse(yes('否'))
        self.assertTrue(yes('是'))

    def test_shared_clin_becomes_record_level(self):
        from normalize_listing import _record_level_clin
        items = [{'test': '心率', 'value': '72', 'clin': 2, '_clin_col': 'c', 'link': 'AE1'},
                 {'test': 'QTcF', 'value': '480', 'hi': '450', 'clin': 2, '_clin_col': 'c', 'link': 'AE1'},
                 {'test': 'PR', 'value': '160', 'clin': 2, '_clin_col': 'c'}]
        out = _record_level_clin(items, {'sheet': 'ECG'})
        by = {x['test']: x for x in out}
        self.assertEqual(by['QTcF']['clin'], 2)                   # 超范围的参数承载判定
        self.assertIsNone(by['心率']['clin'])
        self.assertIsNone(by['PR']['clin'])
        self.assertNotIn('link', by['心率'])
        items = [{'test': '心率', 'value': '72', 'clin': 2, '_clin_col': 'c'}, {'test': 'PR', 'value': '160', 'clin': 2, '_clin_col': 'c'}]
        out = _record_level_clin(items, {'sheet': 'ECG', 'group': '12导联心电图'})
        rec = [x for x in out if x['test'].endswith('总体评价')]
        self.assertEqual(len(rec), 1)                             # 无参数可判异常 → 一条总体评价
        self.assertEqual(rec[0]['clin'], 2)
        self.assertTrue(all('_clin_col' not in x for x in out))

    def _C(self, F=None, metric=None, subj=None):
        from types import SimpleNamespace
        subj = subj or {'S1': {'site': '01', 'fd': '2026-02-01'}}
        return SimpleNamespace(A={}, cfg={'thresholds': {'dev': 0.3, 'base': 0.3}}, F=F or {}, metric=metric or {}, pop=set(subj),
                               subj=subj, others=[], src={'sheets': {}}, aes=[], ae_by={}, aesiDefs=[], tl=defaultdict(dict))

    def test_range_missing_merged_per_page(self):
        from mm_build import range_checks
        F, metric = {}, {}
        for k in range(3):
            mid = f'lab:T{k}'
            metric[mid] = {'domain': 'lab', 'label': f'T{k}'}
            F[('S1', mid)] = [{'sid': 'S1', 'value': 1.0, 'raw': '1', 'lo': None, 'hi': None, 'sheet': 'LB', 'row': 2, 'date': '2026-03-01', 'visit': 'V2'}]
            for j in range(2, 8):
                F[(f'S{j}', mid)] = [{'sid': f'S{j}', 'value': 1.0, 'raw': '1', 'lo': 0, 'hi': 2, 'sheet': 'LB', 'row': 2, 'date': '2026-03-01'}]
        subj = {f'S{j}': {'site': '01', 'fd': '2026-02-01'} for j in range(1, 8)}
        C = self._C(F, metric, subj)
        range_checks(C)
        hit = [o for o in C.others if o['cat'] == '参考范围缺失核对']
        self.assertEqual(len(hit), 1)                             # 同一张化验单 3 项 → 一条
        self.assertIn('3 项', hit[0]['sum'])

    def test_range_missing_merged_across_visits(self):
        """MGK：同一参与者同一表单每次访视都漏填范围 → 合并为一条、列出访视（原先按访视拆成十几条）。"""
        from mm_build import range_checks
        F, metric = {}, {}
        for k in range(2):
            mid = f'lab:T{k}'
            metric[mid] = {'domain': 'lab', 'label': f'T{k}'}
            F[('S1', mid)] = [{'sid': 'S1', 'value': 1.0, 'raw': '1', 'lo': None, 'hi': None, 'sheet': 'LB', 'row': 2 + v,
                               'date': f'2026-0{3 + v}-01', 'visit': f'V{2 + v}'} for v in range(3)]
            for j in range(2, 22):                                # 同指标 ≥80% 记录有范围才判「漏填」
                F[(f'S{j}', mid)] = [{'sid': f'S{j}', 'value': 1.0, 'raw': '1', 'lo': 0, 'hi': 2, 'sheet': 'LB', 'row': 2, 'date': '2026-03-01'}]
        subj = {f'S{j}': {'site': '01', 'fd': '2026-02-01'} for j in range(1, 22)}
        C = self._C(F, metric, subj)
        range_checks(C)
        hit = [o for o in C.others if o['cat'] == '参考范围缺失核对']
        self.assertEqual(len(hit), 1)
        self.assertIn('共 3 次访视（V2、V3、V4）', hit[0]['sum'])

    def test_pregnancy_range_text_and_pre_dose(self):
        import ext_rules
        metric = {'lab:尿妊娠试验': {'label': '尿妊娠试验'}, 'lab:hCG参考区间': {'label': 'hCG参考区间'}}
        row = lambda **k: {'sheet': 'LB', 'row': 2, 'visit': 'V1', **k}
        F = {('S1', 'lab:hCG参考区间'): [row(raw='非孕期<5；早孕期 1000-50000', date='2026-03-01')],
             ('S1', 'lab:尿妊娠试验'): [row(raw='阳性', date='2026-01-20'), row(raw='阴性', date='2026-03-01')]}
        C = self._C(F, metric)
        ext_rules.m18_preg(C)
        cats = [o['cat'] for o in C.others]
        self.assertNotIn('妊娠暴露核查', cats)                      # 参考区间文本、首剂前阳性都不是研究期间妊娠暴露
        self.assertEqual(cats, ['入排标准核对'])
        F[('S1', 'lab:尿妊娠试验')].append(row(raw='阳性', date='2026-04-01'))
        C = self._C(F, metric)
        ext_rules.m18_preg(C)
        o = next(o for o in C.others if o['cat'] == '妊娠暴露核查')
        self.assertEqual(o.get('_preg_pos'), '2026-04-01')        # 结构化阳性才供 IP-02 级联

    def test_stable_metric_excluded_from_cred(self):
        from monitor_v5 import stable_metrics
        F = {}
        for i in range(6):
            F[(f'S{i}', 'vs:身高')] = [{'value': 170.0}, {'value': 170.0}, {'value': 170.0}]
            F[(f'S{i}', 'vs:收缩压')] = [{'value': 120.0 + i}, {'value': 118.0}, {'value': 125.0}]
        from types import SimpleNamespace
        self.assertEqual(stable_metrics(SimpleNamespace(F=F)), {'vs:身高'})

    def test_eff_sheet_candidates(self):
        from mm_build import eff_sheet_candidates
        self.assertEqual(eff_sheet_candidates('月经失血量（MBL）', ['(51)月经周期及出血情况', '(12)生命体征']), ['(51)月经周期及出血情况'])
        self.assertEqual(eff_sheet_candidates('总分', ['量表总分', '评分记录']), [])     # 只有通用词 → 不给候选

    def test_qualitative_merged_per_metric(self):
        import ext_rules
        rows = [{'raw': '阴性', 'post': False, 'value': None, 'sheet': 'U', 'row': 1, 'visit': 'V1', 'date': '2026-02-01'}] + \
               [{'raw': '++', 'post': True, 'value': None, 'sheet': 'U', 'row': k, 'visit': f'V{k}', 'date': f'2026-0{k}-01'} for k in (3, 4, 5)]
        C = self._C({('S1', 'lab:尿蛋白'): rows}, {'lab:尿蛋白': {'label': '尿蛋白'}})
        ext_rules.m16_qual(C)
        hit = [o for o in C.others if o['cat'] == '定性结果核对']
        self.assertEqual(len(hit), 1)                             # 三个访视 → 一条
        self.assertIn('共 3 次', hit[0]['sum'])

    def test_disease_worsening_abs_floor(self):
        from ext_rules import worse_vs_base
        r = {'value': 0.65, 'hi': 0.5, 'unit': '×10^9/L', 'mid': 'lab:嗜酸性粒细胞计数'}
        b = {'value': 0.4}
        self.assertIsNotNone(worse_vs_base(r, b, 0.3))           # 一般口径：相对 62%
        self.assertIsNone(worse_vs_base(r, b, 0.3, disease=True)) # 研究疾病表现：绝对变化 0.25 < 0.3 不算明显加重
        self.assertIsNotNone(worse_vs_base(dict(r, value=0.8), b, 0.3, disease=True))

    def test_threshold_query_asks_protocol_action(self):
        # 用户 2026-11-02（问法 B）：阈值类质疑按方案规定的处理来问，不问「请核实并更正」；措辞固定用程序模板
        from mm_build import threshold_ask
        # 2026-11-04 审阅第 21 条：写方案规定的处理（复查时限/中断/停药），不写「达到方案阈值」、不重复两遍
        o = {'cat': '阈值规则核对', 'test': '丙氨酸氨基转移酶（ALT）'}
        a = threshold_ask({'metric': 'ALT', 'v': 5, 'on': 'uln', 'stop': True, 'acts': ['stop'], 'stopCond': '如果确认…'}, o)
        self.assertIn('确认后停用研究药物', a)
        self.assertIn("Hy's law", a)
        self.assertIn('核对同期总胆红素', a)
        # D001 测试第四轮：胆红素行核对同期转氨酶（不再要求「核对同期总胆红素」）
        b = threshold_ask({'metric': 'TBIL', 'v': 2, 'on': 'uln', 'acts': ['aesi']}, {'cat': '阈值规则核对', 'test': '总胆红素（TBIL）'})
        self.assertIn('核对同期转氨酶', b)
        self.assertNotIn('核对同期总胆红素', b)
        self.assertNotIn('更正', a)
        self.assertNotIn('阈值', a)
        a = threshold_ask({'metric': 'ANC', 'v': 1.5, 'acts': ['retest', 'interrupt'], 'retestH': 48}, {'cat': '阈值规则核对', 'test': '中性粒细胞计数'})
        self.assertEqual(a, '方案规定此时需在 48 小时内复查确认，并中断研究药物，请确认复查结果及研究药物处理情况。')
        self.assertIn('AESI', threshold_ask({'metric': 'QTcF', 'v': 500, 'aesi': True}, {'cat': '阈值规则核对', 'test': 'QTcF'}))
        self.assertEqual(threshold_ask({'metric': 'X', 'v': 1}, {'cat': '入排标准核对'}), '')
        from mm_build import thr_label, thr_rhs
        self.assertEqual(thr_label({'acts': ['retest', 'interrupt']}), '达到方案中断给药标准')
        self.assertEqual(thr_rhs({'label': '中性粒细胞计数ANC < 1.5 ×10^9/L', 'op': '<', 'v': 1.5}), '低于 1.5×10^9/L')

    def test_ctcae_v6_corrections_vs_official(self):
        # 2026-11-02 对照 NCI DCTD《CTCAE v6.0》Clean Copy 核对：血小板减少 4 级 <10×10^9/L；
        # ALT/AST 基线已异常时 3 级 >2.0、4 级 >4.0 倍基线；CPK increased 在 v6.0 已删除（表中不应有 CK）
        import json
        t = json.loads((Path(__file__).parent / 'grading' / 'ctcae_v6.0.json').read_text(encoding='utf-8'))
        g4 = next(s for s in t['items']['PLT'][0]['steps'] if s['g'] == 4)
        self.assertEqual(g4['v'], 10)
        for k in ('ALT', 'AST'):
            ab = next(c for c in t['items'][k] if c.get('when') == 'baseAbnormal')
            self.assertEqual({s['g']: s['v'] for s in ab['steps']}[3], 2.0)
            self.assertEqual({s['g']: s['v'] for s in ab['steps']}[4], 4.0)
        self.assertNotIn('CK', t['items'])

    def test_disease_background_specimen(self):
        from ext_rules import bg_applies
        note = '可见于鼻分泌物涂片嗜酸性粒细胞增多'
        self.assertFalse(bg_applies(note, 'lab:嗜酸性粒细胞计数（EOS#）', '血常规'))   # 外周血不套用鼻涂片背景
        self.assertTrue(bg_applies(note, 'exam:鼻分泌物涂片嗜酸性粒细胞', '鼻涂片'))
        self.assertTrue(bg_applies('研究疾病常见贫血', 'lab:血红蛋白', '血常规'))        # 未写标本照常适用

    def test_panel_level_cs_kept_on_abnormal_rows(self):
        from mm_build import panel_level_clin
        rows = {('S1', f'lab:{t}'): [{'sid': 'S1', 'sheet': 'WBC', 'date': '2026-03-01', 'clin': 2, 'raw': raw, 'value': None, 'oor': False}]
                for t, raw in (('霉菌', '阳性'), ('滴虫', '阴性'), ('线索细胞', '阴性'), ('清洁度', 'Ⅱ'))}
        C = self._C(rows, {k[1]: {'label': k[1]} for k in rows})
        panel_level_clin(C)
        cl = {k[1]: v[0]['clin'] for k, v in C.F.items()}
        self.assertEqual(cl['lab:霉菌'], 2)                                       # 整份 CS 只留在阳性行
        self.assertIsNone(cl['lab:滴虫'])
        self.assertTrue(all(v[0].get('_panel') for v in C.F.values()))

    def test_negative_result_judged_cs_is_entry_check(self):
        import ext_rules
        r = {'sid': 'S1', 'raw': '未见', 'value': None, 'clin': 2, 'post': True, 'visit': 'W4', 'date': '2026-03-01',
             'sheet': 'LB', 'row': 5, 'links': [], 'base': None, 'mid': 'lab:滴虫'}
        C = self._C({('S1', 'lab:滴虫'): [r]}, {'lab:滴虫': {'label': '滴虫'}})
        C.labrows, C.S, C.indBg, C.mhMatch = [], {}, [], []
        C.cfg['thresholds'] = {'dev': 0.3, 'base': 0.3}
        ext_rules.m23_csb(C)
        self.assertEqual([o['risk'] for o in C.others], ['M16-NEGCS'])           # 录入核对，不按 CS 未关联追 AE

    def test_partial_start_pre_dose(self):
        from mm_build import _pre_dose
        self.assertTrue(_pre_dose('2026-01', '2026-02-03'))
        self.assertFalse(_pre_dose('2026-02', '2026-02-03'))      # 同月不能判首剂前 → 按 TEAE（最坏情形）
        self.assertFalse(_pre_dose('是', '2026-02-03'))
        self.assertTrue(_pre_dose('2026-01-30', '2026-02-03'))


class IeFailReasonTests(unittest.TestCase):
    """V6 用户审阅 RUX 第 4 条：筛败原因取入排标准页（两种页面形态）。夹具虚构。"""

    def test_summary_and_per_criterion_layouts(self):
        from types import SimpleNamespace
        import mm_build as M
        C = SimpleNamespace(ie=[{'sid': 'A1', 'met': '否', 'ie_cat': '排除标准', 'crit': '05'},
                                {'sid': 'A1', 'met': '否', 'ie_cat': '入选标准', 'crit': '4'},
                                {'sid': 'A2', 'met': '是', 'ie_cat': '', 'crit': ''}])
        self.assertEqual(M.ie_fail_reasons(C), {'A1': '排除标准 5、入选标准 4'})
        C = SimpleNamespace(ie=[{'sid': 'B1', 'met': 'Y', 'ie_cat': 'INCLUSION', 'crit': 'IN01'},
                                {'sid': 'B1', 'met': 'N', 'ie_cat': 'EXCLUSION', 'crit': 'EX02'},
                                {'sid': 'B2', 'met': 'Y', 'ie_cat': 'EXCLUSION', 'crit': 'EX03'},
                                {'sid': 'B3', 'met': 'N', 'ie_cat': 'INCLUSION', 'crit': 'IN02'}])
        self.assertEqual(M.ie_fail_reasons(C), {'B2': '排除标准 EX03', 'B3': '入选标准 IN02'})


class ProtectiveAntibodyTests(unittest.TestCase):
    """E2E 第 6 轮 RUX：保护性抗体（HBsAb/抗-HBs）阳性不作首剂前疑似病史漏记；表面抗原、核心抗体照常。"""

    def test_pattern(self):
        import ext_rules as E
        self.assertTrue(E.PROTECTIVE_AB.search('乙肝表面抗体（HBsAb）'))
        self.assertTrue(E.PROTECTIVE_AB.search('抗-HBs'))
        self.assertFalse(E.PROTECTIVE_AB.search('乙肝表面抗原（HBsAg）'))
        self.assertFalse(E.PROTECTIVE_AB.search('乙肝核心抗体（HBcAb）'))


class BlindRawLayerTests(unittest.TestCase):
    """V6 工程审阅 P0：盲态构建原始数据层不导出分组列（表头或取值形态识别；RUX 无表头「列8」带治疗组/安慰剂组）。夹具虚构。"""

    def test_arm_column(self):
        from raw_export import arm_column
        self.assertTrue(arm_column('列8', ['A药治疗组', '安慰剂组', 'A药治疗组', '']))
        self.assertTrue(arm_column('组别', ['1', '2']))
        self.assertTrue(arm_column('随机分组', ['X']))
        self.assertTrue(arm_column('列3', ['高剂量', '低剂量'], extra=['高剂量', '低剂量']))
        self.assertFalse(arm_column('药物名称', ['AK120注射液/安慰剂', '布洛芬', '氯雷他定', '头孢']))
        self.assertFalse(arm_column('GROUPID', ['301', '302']))

    def test_blind_sheet_with_arm_dropped_whole(self):
        # SAR 第 8 轮：分组表按组别排序，原始行号即可还原分组 → 盲态整表不导出，剔除记录不含分组用语
        import openpyxl
        import tempfile
        from types import SimpleNamespace
        from raw_export import export_raw
        with tempfile.TemporaryDirectory() as td:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'GROUP'
            ws.append(['受试者', '治疗组'])
            for i, g in enumerate(['安慰剂组', '安慰剂组', '试验组', '试验组']):
                ws.append([f'S{i + 1}', g])
            ws2 = wb.create_sheet('AE')
            ws2.append(['受试者', '不良事件名称'])
            ws2.append(['S1', '头痛'])
            f = Path(td) / 'g.xlsx'
            wb.save(f)
            C = SimpleNamespace(subj={f'S{i}': {} for i in range(1, 5)}, src={'workbooks': {'edc': str(f)}, 'sheets': {}},
                                cfg={'blind': {'on': True}})
            idx = export_raw(C, Path(td) / 'out')
            self.assertNotIn('edc:GROUP', idx['sheets'])
            self.assertIn('edc:AE', idx['sheets'])
            self.assertFalse(any('治疗组' in d or '安慰剂' in d for d in idx['dropped']))


class IbRiskFamilyTests(unittest.TestCase):
    """V6 医学审阅：IB 风险名括注里的临床表现＋事件族参与匹配（RUX 带状疱疹/卡波西水痘样疹 ↔ 局部免疫抑制效应（皮肤感染））。"""

    def test_family(self):
        from mm_build import risk_term_re
        r = risk_term_re('局部免疫抑制效应（皮肤感染）')
        self.assertTrue(r.search('颈部带状疱疹') and r.search('卡波西水痘样疹'))
        self.assertFalse(r.search('上呼吸道感染'))                         # 皮肤感染族不扩到呼吸道
        self.assertTrue(risk_term_re('皮肤恶性肿瘤').search('基底细胞癌'))
        self.assertFalse(risk_term_re('皮肤恶性肿瘤').search('肺癌'))


class WorseRangeChangeTests(unittest.TestCase):
    """V6 医学审阅：前后参考范围不同时按 ×ULN 比较是否加重（RUX S13007 上限 20.5→26.0）。"""

    def test_uln_ratio(self):
        from ext_rules import worse_vs_base
        b = {'value': 25.0, 'hi': 20.5, 'lo': 0}
        self.assertIsNone(worse_vs_base({'value': 31.7, 'hi': 26.0, 'lo': 0}, b, 0.3))       # ×ULN 1.22 → 1.22，不加重
        self.assertTrue(worse_vs_base({'value': 45.0, 'hi': 26.0, 'lo': 0}, b, 0.3))         # ×ULN 1.22 → 1.73，加重


class AttributionNearTests(unittest.TestCase):
    """V6 医学审阅：同一受试者相隔较远（不同时期）的归因不同不算归因不一致。"""

    def test_far_apart_not_paired(self):
        from ext_rules import cons_attribution
        a = {'sid': 'S1', 'date': '2026-05-01', 'links': [['AE', 'x', None, 1]], 'reason': ''}
        b = {'sid': 'S1', 'date': '2026-08-01', 'links': [], 'reason': ''}
        self.assertEqual(cons_attribution([a, b], False), [])
        b2 = dict(b, date='2026-05-08')
        self.assertEqual(len(cons_attribution([a, b2], False)), 1)


class Eng2Tests(unittest.TestCase):
    """V6 第二轮工程审阅：AE 子记录只认标志、未做口径统一、EDC 计划窗日期规范化、目录页判定。"""
    def test_ae_dup_needs_flag(self):
        from types import SimpleNamespace
        from mm_build import build_events_dup
        a = {'sid': 'S1', 't': '肺炎', 'pt': '肺炎', 's': '2026-01-02', 'e': '', 'g': '2', 'sae': False}
        C = SimpleNamespace(aes=[{**a, 'row': 3, 'gchg': ''}, {**a, 'row': 4, 'gchg': ''}])
        build_events_dup(C)
        self.assertEqual(len(C.ae_dup), 1)                 # 同一 AE 录两次（记录号自然不同）仍是重复
        C = SimpleNamespace(aes=[{**a, 'row': 3, 'gchg': '是'}, {**a, 'row': 4, 'gchg': ''}])
        build_events_dup(C)
        self.assertEqual((len(C.ae_dup), C.aes[1].get('dup_kind')), (0, 'sub'))

    def test_not_done(self):
        from common import not_done
        for v in ('否', '否（未进行）', 'N', 'No', 'Not done', '未进行', '未查'):
            self.assertTrue(not_done(v), v)
        for v in ('是', '', None, 'NA', 'Normal', '正常'):
            self.assertFalse(not_done(v), v)

    def test_window_dates_normalized(self):
        from normalize_listing import conv
        import datetime as dt
        self.assertEqual(conv('win_lo', dt.datetime(2024, 7, 9), {}), '2024-07-09')
        self.assertEqual(conv('win_hi', '2024/07/09', {}), '2024-07-09')

    def test_thr_handled_same_day(self):
        from types import SimpleNamespace
        from mm_build import thr_handled
        R = {'acts': ['retest', 'interrupt'], 'retestH': 48}
        r = {'date': '2024-07-30', 'row': 5, 'value': 1.24}
        rows = [r, {'date': '2024-07-31', 'row': 6, 'value': 1.57, 'raw': '1.57'}]
        C = SimpleNamespace(exposure=[], ae_by={'S1': [{'t': '中性粒细胞计数降低', 's': '2024-07-30', 'act': '暂时停用后又恢复研究药物'}]})
        self.assertTrue(thr_handled(C, 'S1', r, R, rows))     # 同日 AE 暂停（0 天）不能被当成「未处理」
        C = SimpleNamespace(exposure=[{'sid': 'S1', 'start': '2024-07-30', 'pause': '暂停用药'}], ae_by={})
        self.assertTrue(thr_handled(C, 'S1', r, R, rows))

    def test_within_pre_tolerance(self):
        from ext_rules import worse_vs_base, pre_values
        rows = [{'post': False, 'value': 35.02}, {'post': False, 'value': 26.61}]
        b = {'value': 26.61, 'grade': 0, 'hi': 21}
        r = {'value': 36.78, 'hi': 21, 'grade': 0, 'mid': 'LB:总胆红素'}
        self.assertTrue(worse_vs_base(r, b, 0.3))                         # 只比基线：+38% 判加重
        self.assertIsNone(worse_vs_base(r, b, 0.3, pre=pre_values(rows)))  # 筛选期已到 35.02：+5% 在波动内
        self.assertTrue(worse_vs_base({**r, 'value': 45.0}, b, 0.3, pre=pre_values(rows)))

    def test_csb_multi_link_and_mh_text(self):
        from types import SimpleNamespace
        from collections import defaultdict
        import ext_rules
        ae = defaultdict(list, {'S1': [{'n': 3, 't': '腹痛', 's': '2024-01-01'}, {'n': 4, 't': '肝功能异常', 's': '2024-01-01'}]})
        mh = defaultdict(list, {'S1': [{'n': 3, 't': '不完全性右束支传导阻滞', 's': '2020-01-01', 'e': '', 'ong': '是'}]})
        C = SimpleNamespace(ae_by=ae, mh_by=mh, A={'aeMatch': [['ALT', '肝', 30]]}, mhMatch=[])
        r = {'sheet': 'LB', 'row': 2, 'date': '2024-01-05'}
        links = [['AE', '', None, 3], ['AE', '', None, 4]]
        best = max(links, key=lambda l: ext_rules._link_rank(C, 'S1', 'LB:ALT', r, l))
        self.assertEqual(best[3], 4)                           # 第二个关联才对应：取对应的那个
        ecg = {'desc': '右束支传导阻滞', 'value': None, 'date': '2024-01-05'}
        self.assertEqual([m['no'] for m in ext_rules.desc_mh_match(C, 'S1', ecg)], [3])

    def test_arm_specific_visits(self):
        from types import SimpleNamespace
        from monitor_v5 import arm_specific_visits
        subj = {f'A{i}': {'grp': 'A组', 'fd': '2024-01-01'} for i in range(6)}
        subj.update({f'B{i}': {'grp': 'B组', 'fd': '2024-01-01'} for i in range(6)})
        visits = [{'sid': f'A{i}', 'visit': 'D21', 'date': '2024-01-21'} for i in range(5)] + \
                 [{'sid': s, 'visit': 'D28', 'date': '2024-01-28'} for s in subj]
        C = SimpleNamespace(subj=subj, visits=visits)
        self.assertEqual(arm_specific_visits(C), {('D21', 'B组')})
        C2 = SimpleNamespace(subj={k: {**v, 'grp': None} for k, v in subj.items()}, visits=visits)
        self.assertEqual(arm_specific_visits(C2), set())        # 盲态（无分组）不推断

    def test_pow10_and_elig_units(self):
        from mm_build import _elig_x
        E = {'on': 'val', 'unit': '×10^9/L', 'op': '<', 'v': 100}
        self.assertEqual(_elig_x(E, {'value': 0.15, 'unit': '×10^12/L'}), 150.0)
        self.assertIsNone(_elig_x(E, {'value': 8.0, 'unit': '', 'test': '网织红细胞计数百分比'}))

    def test_align_by_visit_code_column(self):
        from types import SimpleNamespace
        from mm_build import align_visit_codes
        vis = [{'sid': 'S1', 'visit': 'D-3至D-1', 'vcode': 'V2'}, {'sid': 'S1', 'visit': 'D21', 'vcode': 'V6'}]
        C = SimpleNamespace(visits=vis, findings=[], efficacy=[], exposure=[], cfg={'visits': {'order': ['V1', 'V2', 'V6']}},
                            A={'visitWindows': {'V6': {'target': 21}}})
        align_visit_codes(C)
        self.assertEqual(C.cfg['visits']['order'], ['V1', 'D-3至D-1', 'D21'])
        self.assertIn('D21', C.A['visitWindows'])

    def test_disease_direction_and_gate(self):
        from types import SimpleNamespace
        from ext_rules import worse_vs_base, disease_dir
        C = SimpleNamespace(A={'indicationBackground': [['^lab:.*网织红细胞', '网织红细胞计数代偿性增高↑：溶血后代偿']]})
        self.assertEqual(disease_dir(C, 'lab:网织红细胞计数百分比'), 'high')
        b = {'value': 6.76, 'hi': 2.0, 'grade': 0}
        down = {'value': 3.0, 'hi': 2.0, 'grade': 0, 'mid': 'lab:网织红细胞计数百分比'}
        up = {'value': 12.0, 'hi': 2.0, 'grade': 0, 'mid': 'lab:网织红细胞计数百分比'}
        self.assertIsNone(worse_vs_base(down, b, 0.3, disease=True, ddir='high'))    # 下降＝好转，不算加重
        self.assertTrue(worse_vs_base(up, b, 0.3, disease=True, ddir='high'))
        from mm_build import disease_gate
        C2 = SimpleNamespace(metric={'lab:N': {'gcode': 'ANC'}, 'lab:R': {}})
        pts = [{'post': True, 'grade': 2, 'value': 1.2}]
        self.assertFalse(disease_gate(C2, 'lab:N', pts, {'grade': 2, 'value': 1.4})[0])   # 有分级、2 级未上升 → 清单
        self.assertTrue(disease_gate(C2, 'lab:N', [{'post': True, 'grade': 3, 'value': 0.8}], {'grade': 2, 'value': 1.4})[0])
        self.assertTrue(disease_gate(C2, 'lab:R', pts, None)[0])                          # 无分级 → 发（≥30% 已满足）

    def test_pct_wording_uses_raw_change(self):
        from ext_rules import worse_vs_base
        w = worse_vs_base({'value': 4.87, 'hi': 4.8, 'grade': 0, 'mid': 'lab:甘油三酯'}, {'value': 4.04, 'hi': 5.2, 'grade': 0}, 0.2)
        self.assertTrue(w.startswith('较基线升高 21%'), w)                                # D002 Q039：原值升高 21%，不能写 30%

    def test_prohibited_route_and_unknown_end(self):
        from types import SimpleNamespace
        from collections import defaultdict
        import mm_build
        C = SimpleNamespace(A={'prohibited': [{'name': '系统性皮质类固醇', 're': '甲泼尼龙|布地奈德|倍氯米松', 'route': 'systemic'},
                                              {'name': '外用皮质类固醇', 're': '莫米松|布地奈德', 'route': 'topical'}]},
                            pop={'S1'}, subj={'S1': {'fd': '2024-06-01', 'ld': '2024-12-01', 'lo': '', 'icf': '2024-05-20', 'site': '01'}},
                            cm_by=defaultdict(list), others=[], tl=defaultdict(dict), proc=[])
        cm = lambda t, rt, s_, e, ong=False: {'t': t, 'rt': rt, 's': s_, 'e': e, 'ong': ong, 'why': '', 'sh': 'CM', 'row': 1, 'wb': ''}
        C.cm_by['S1'] = [cm('注射用甲泼尼龙', '静脉滴注', '2024-07-01', '2024-07-02'), cm('吸入用布地奈德混悬液', '吸入', '2024-07-01', '2024-07-01'),
                         cm('丙酸倍氯米松鼻气雾剂', '', '2024-07-01', '2024-07-05'), cm('糠酸莫米松乳膏', '外用', '2018-01-01', 'uk-uk-uk')]
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        try:
            mm_build.cm_checks(C)
        finally:
            mm_build.oth_qkey = orig
        hit = [o['sum'] for o in C.others if o['cat'] == '禁限用药核对']
        self.assertEqual(len(hit), 1, hit)
        self.assertIn('甲泼尼龙', hit[0])
        self.assertTrue(any(o['cat'] == '用药日期核对' for o in C.others))

    def test_undated_procedure_and_rescue_and_dz_boundary(self):
        """审阅 2026-11-10：无日期手术史不报禁用操作；月份日期按可能日判；「挽救」同「补救」；研究疾病缩写按词边界。"""
        from types import SimpleNamespace
        from collections import defaultdict
        import re as _re
        import mm_build
        C = SimpleNamespace(A={'prohibited': [{'name': '造血干细胞移植', 're': '移植'}], 'diseaseTerms': ['SAR']},
                            pop={'S1'}, subj={'S1': {'fd': '2024-06-01', 'ld': '2024-12-01', 'lo': '', 'icf': '2024-05-20', 'site': '01'}},
                            cm_by=defaultdict(list), others=[], tl=defaultdict(dict),
                            proc=[{'sid': 'S1', 'term': '肾移植', 'date': '', 'kind': '手术史', 'sheet': '既往手术史', 'row': 1},
                                  {'sid': 'S1', 'term': '骨髓移植', 'date': '2023-04', 'sheet': '操作', 'row': 2},
                                  {'sid': 'S1', 'term': '干细胞移植', 'date': '2024-08', 'sheet': '操作', 'row': 3},
                                  {'sid': 'S1', 'term': '异体移植', 'date': '', 'sheet': '操作', 'row': 4}])
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        try:
            mm_build.cm_checks(C)
        finally:
            mm_build.oth_qkey = orig
        hit = [(o['pr'], o['sum']) for o in C.others if o['cat'] == '禁限用药核对']
        self.assertEqual([x for x in hit if x[0] >= 3 and '干细胞移植' in x[1]].__len__(), 1, hit)   # 2024-08 在首剂后 → 报
        self.assertFalse(any('肾移植' in x[1] or '骨髓移植' in x[1] for x in hit), hit)           # 手术史无日期、2023 年 → 不报
        self.assertTrue(any(x[0] == 2 and '异体移植' in x[1] for x in hit), hit)                 # 操作表无日期 → 只提示
        self.assertTrue(_re.search(mm_build.RESCUE_WHY, '挽救治疗'))
        rx = _re.compile(mm_build._dz_alt('SAR'))
        self.assertIsNone(rx.search('SARS-CoV-2感染'))
        self.assertTrue(rx.search('SAR加重'))
        self.assertTrue(mm_build._AESI_QUAL.search('伴有临床症状的低血糖'))
        from ext_rules import disease_kw
        C2 = SimpleNamespace(A={'diseaseWorseTerms': ['SAR']}, S={})
        self.assertIsNone(disease_kw(C2).search('SARS-CoV-2感染'))

    def test_history_attribution_and_procedure(self):
        """用户 2026-11-11：CS 说明归因既往手术——手术史（proc）有记录 → 视为已解释；没有记录 → 「疑似病史漏记·说明已归因」，不按漏报 AE。"""
        from types import SimpleNamespace
        import ext_rules as X
        r = {'sid': 'S1', 'desc': '腹部可见一长约10cm瘢痕，CS，与剖宫产手术史相关', 'date': '2025-09-01', 'value': None}
        C = SimpleNamespace(proc=[{'sid': 'S1', 'term': '剖腹产术', 'no': '1'}], mh_by={'S1': []})
        hit = X.desc_mh_match(C, 'S1', r)
        self.assertTrue(hit and hit[0]['kind'] == 'PR', hit)
        self.assertEqual(X.proc_match(SimpleNamespace(proc=[{'sid': 'S1', 'term': '阑尾切除术'}]), 'S1', r), [])
        self.assertIn('剖宫产手术史', X.hx_attr(r))
        self.assertEqual(X.hx_attr({'desc': '无手术史，新发皮疹'}), '')
        self.assertIn('陈旧', X.hx_attr({'desc': '左膝陈旧性瘢痕'}))
        self.assertEqual(X.hx_attr({'desc': '既往皮损全部消退，存在部分炎症后色素沉着（NCS），左背部红斑水疱结痂（CS，带状疱疹相关）'}), '')
        self.assertEqual(X.hx_attr({'desc': '两上肺肺气肿改变，请结合临床病史（CS）'}), '')
        self.assertIn('阑尾切除术后', X.hx_attr({'desc': '右下腹瘢痕（CS，阑尾切除术后）'}))
        self.assertEqual(X.hx_attr({'desc': '按方案要求加做HBV-DNA，与AE及病史均无关'}), '')

    def test_pd_def_table_grades(self):
        """申办方方案偏离界定表优先（用户 2026-11-11）：子分类对上规则 → 按表定分级并注明依据；分两档的个案升级引用影响较大档。"""
        import pd_rules as P
        rows = [{'cat': 'F. 访视计划', 'no': '1', 'text': '访视超出可允许的时间窗', 'sev': '根据实际情况判定'},
                {'cat': 'F. 访视计划', 'no': '2', 'text': '访视缺失，且对参与者的安全性及主要疗效评估产生显著影响', 'sev': '严重'},
                {'cat': 'F. 访视计划', 'no': '3', 'text': '访视缺失，但对参与者的安全性及主要疗效评估无显著影响', 'sev': '轻微'},
                {'cat': 'C. 试验用药物', 'no': '10', 'text': '用药依从性＜80%或＞120%', 'sev': '严重'},
                {'cat': 'J. 伦理', 'no': '1', 'text': '未按照试验方案的伦理规范要求执行', 'sev': '严重'}]
        g, basis, hi, unused = P.def_grades({'rows': rows})
        self.assertEqual(g['VIS-01'], '待判定')
        self.assertEqual(g['VIS-02'], '一般')
        self.assertEqual(hi['VIS-02'][0], '重要')
        self.assertEqual(g['IP-03'], '重要')
        self.assertIn('F.1', basis['VIS-01'])
        self.assertNotIn('ICF-01', g)
        self.assertEqual([r['cat'] for r in unused], ['J. 伦理'])

    def test_link_verdict_for_other_record_ignored(self):
        """宿主预判针对的是另一条记录（编号口径不同）时不用；同一记录照用。"""
        from types import SimpleNamespace
        from ext_rules import _link_match
        C = SimpleNamespace(A={'linkVerdicts': {'w:LB|5': {'v': 'implausible', 'term': '花粉过敏', 'why': 'x'}}}, mhMatch=[])
        r = {'wb': 'w', 'sheet': 'LB', 'row': 5}
        self.assertIsNone(_link_match(C, r, 'lab:GLU', 'MH', {'t': '高血糖症'})[0])
        self.assertFalse(_link_match(C, r, 'lab:GLU', 'MH', {'t': '花粉过敏'})[0])

    def test_labeled_links_dose_and_plausible(self):
        from common import parse_typed_links
        self.assertEqual(parse_typed_links('序号：4-不良事件名称：白细胞降低-开始日期：2024-11-21；序号：5-不良事件名称：D-二聚体升高-开始日期：2025-01-02；', 'AE'),
                         [['AE', '白细胞降低', None, 4], ['AE', 'D-二聚体升高', None, 5]])
        from mm_build import _dose_num, implausible
        self.assertEqual((_dose_num('900 mg'), _dose_num('900'), _dose_num('其他')), (900.0, 900.0, None))
        self.assertTrue(implausible({'value': 26.5, 'raw': '26.5', 'unit': 'fl'}, '平均红细胞体积'))
        self.assertFalse(implausible({'value': 88, 'raw': '88', 'unit': 'fl'}, '平均红细胞体积'))

    def test_icf_allowed_and_history_form(self):
        from types import SimpleNamespace
        import pd_rules
        C = SimpleNamespace(pop={'S1'}, subj={'S1': {'icf': '2024-10-01', 'fd': '2024-10-20', 'site': '01'}}, visits=[], exposure=[],
                            findings=[{'sid': 'S1', 'date': '2024-09-10', 'group': '影像检查', 'test': '胸部X线', 'sheet': 'MO', 'row': 2},
                                      {'sid': 'S1', 'date': '2019-08-07', 'group': 'PNH疾病诊断', 'test': 'Ham试验', 'sheet': 'LB', 'row': 3}],
                            A={'formNames': {}, 'pd': {'preIcfAllowed': [{'item': '影像', 'days': 90, 'ref': 'icf'}]}}, icf=[],
                            S={'cutoff': '2025-01-01'}, cfg={}, dosed={'S1'})
        E = pd_rules._PD(C)
        E.icf()                                          # 曾因 tag 未定义而崩溃（MY008 第 9 轮构建失败）
        self.assertFalse([p for p in E.items if p.get('rule') == 'ICF-01'])

    def test_chg_uln_and_base_condition(self):
        from mm_build import thr_rhs
        self.assertEqual(thr_rhs({'on': 'chg_uln', 'op': '>=', 'v': 1.0}), '较基线升高达到 1×ULN')

    def test_catalog_header_only_needs_two(self):
        from normalize_listing import catalog_map
        names = {'AE', 'SAE', 'LB1', 'TOC'}
        sae = [('受试者', '关联表单', '表单名称'), ('S1', 'AE', '不良事件')]
        self.assertEqual(catalog_map({'SAE': sae}, names), {})          # 单行 SAE 报告不是目录
        toc = [('代码', '名称'), ('AE', '不良事件')]
        self.assertEqual(catalog_map({'TOC': toc}, names), {'AE': '不良事件'})
        dn = [('Database_Version', 'SAS_Dataset_Name', 'Form_OID', 'Form_Name')] + \
            [(v, c, c, n) for v in ('V3.1', 'V3.0') for c, n in (('AE', '不良事件'), ('LB1', '血常规'))]
        self.assertEqual(catalog_map({'DOMAIN_NAME': dn}, names | {'DOMAIN_NAME'}), {'AE': '不良事件', 'LB1': '血常规'})   # MGK：按 CRF 版本重复列出


class DiseaseDirectionFromExtraction(unittest.TestCase):
    """审阅者 2026-11-09：疾病不利方向只取方案/IB 抽取（disease_dir），不按指标名硬名单反转（撤回 G1）。
    用户 2026-11-05 口径：PNH 网织红细胞下降＝好转，升高（溶血代偿）＝加重；血红蛋白抽取方向 ↓ 时升高不算加重。"""

    def test_direction_follows_extraction(self):
        from ext_rules import worse_vs_base
        b = {'value': 2.0, 'grade': 0}
        up = {'value': 6.0, 'hi': 2.5, 'grade': 0, 'clin': 2, 'mid': 'lab:网织红细胞百分比', 'unit': '%'}
        self.assertIn('较基线升高', worse_vs_base(up, b, 0.3, disease=True, ddir='high') or '')
        hb = {'value': 125.0, 'lo': 130, 'hi': 175, 'grade': 0, 'clin': 2, 'mid': 'lab:血红蛋白', 'unit': 'g/L'}
        self.assertIsNone(worse_vs_base(hb, {'value': 80.0, 'grade': 2}, 0.3, disease=True, ddir='low'))

class V6Round2GradingTextSource(unittest.TestCase):
    """G2（MY008R2 R7×2）：分级文案取值源统一。
    ①质疑文案里的「分级变化」（等级 X→Y）必须与判定同一输入——就所选点用自己的基线（含本表基线/每行 base）取级，
      不得拿组内首行基线拼「0→3 级」（抽屉全程表显示基线已 3 级）；
    ②PD（SAFE-01）文案引用的数值与标注分级必须来自同一时点（引用点即取最高级那次）。"""

    MET = 'lab:某计数指标'

    @staticmethod
    def _row(visit, date, value, grade, post, sheet, row, base, clin=0, reason=None, hi=120):
        return {'sid': 'S1', 'post': post, 'clin': clin, 'value': value, 'raw': str(value), 'lo': None, 'hi': hi,
                'unit': '×10^9/L', 'visit': visit, 'date': date, 'sheet': sheet, 'row': row, 'wb': 'edc',
                'grade': grade, 'links': [], 'reason': reason, 'desc': '', 'group': '血常规', 'base': base,
                'pct': None, 'mid': V6Round2GradingTextSource.MET}

    def test_query_text_no_fabricated_zero_to_three(self):
        """红测①：虚构受试者基线已 3 级（本表基线）、当前仍 3 级、数值升高 46% 触发 DISW——
        文案不得出现「0→3」（修前以组内首行基线〔0 级〕拼等级变化）。"""
        from types import SimpleNamespace
        import ctcae
        from mm_build import build_labrows, build_queries
        # 检验A（首行所在表）：基线 0 级——组内首行的 base；检验B：本表自己的基线已 3 级
        a_base = self._row('V1', '2026-01-02', 100.0, 0, False, '检验A', 2, None)
        a_base['base'] = a_base
        b_base = self._row('V1', '2026-01-03', 100.0, 3, False, '检验B', 2, None)
        b_base['base'] = b_base
        b_post = self._row('V3', '2026-02-01', 146.0, 3, True, '检验B', 6, b_base, clin=2, reason='disease')
        b_post['pct'] = 46.0
        C = SimpleNamespace(
            A={'aeMatch': [], 'labDomains': ['lab', 'vs', 'ecg'],
               'indicationBackground': [[self.MET.split(':')[1], '某计数指标↑：研究疾病常见表现']]},
            S={'study': {'design': {'facts': []}}}, cfg={'thresholds': {'base': 0.3}},
            F={('S1', self.MET): [a_base, b_base, b_post]}, pop={'S1'},
            subj={'S1': {'site': '01'}}, src={'sheets': {}},
            metric={self.MET: {'label': '某计数指标', 'n': 3, 'nq': 0, 'hasClin': True}},
            aeEnd={}, mh_by={'S1': []}, ae_by={'S1': []}, btype={}, others=[], findings=[], extq=[],
            G=ctcae.load({'grading': {'version': '5.0'}}), cmap={}, labrows=[])
        C.GL = C.G.label
        build_labrows(C)
        self.assertTrue(any(g['risk'] == 'DISW' for g in C.labrows), C.labrows)
        build_queries(C)
        txt = ' '.join(q['text'] for q in C.queries)
        self.assertNotIn('0→3', txt, txt)
        self.assertIn('较基线升高', txt)                       # 加重事实仍在（数值路径），只是不虚构分级起点

    def test_pd_text_same_timepoint_value_and_grade(self):
        """红测②：SAFE-01 引用点与分级同一时点——首点 1 级、次点 3 级时，事实须引用 3 级那次。"""
        import pd_rules
        from types import SimpleNamespace
        g = {'sid': 'S1', 'site': '01', 'cat': '治疗后新发/加重检验异常', 'test': '某指标', 'mid': 'lab:某指标',
             'grp': '', 'pr': 4,
             'base': ['V1', '50', 'g/L', 0],
             'pts': [['V2', '2026-02-01', '80', 'g/L', 1, 2, 60.0, '检验', 5, '', None, ''],
                     ['V4', '2026-03-01', '30', 'g/L', 3, 2, -40.0, '检验', 9, '', None, '']],
             'rel': [], 'ctx': [], 'q': [], 'fid': [], 'cro': '', 'mg': 3, 'risk': 'CSX', '_aecov': [],
             'wb': '', 'qkey': 'lab|S1|CSX|检验|lab:某指标|V2'}
        C = SimpleNamespace(A={}, S={'study': {}}, cfg={}, subj={'S1': {'site': '01'}}, pop={'S1'},
                            visits=[], efficacy=[], findings=[], others=[], aes=[],
                            cmap={}, GL='CTCAE v5.0', labrows=[g],
                            vi=lambda v: 0, UNS=set(), G=None)
        E = pd_rules._PD(C)
        E.from_signals()
        items = [i for i in E.items if i['rule'] == 'SAFE-01']
        self.assertTrue(items)
        it = items[0]
        self.assertIn('30', it['fact'])                     # 引用 3 级那次的数值
        self.assertIn('V4', it['fact'])
        self.assertIn('3 级', it['why'])                    # 分级与所引用点同时点
        self.assertNotIn('80 g/L', it['fact'])              # 不再引用 1 级首点的数值配 3 级说明


class V6Round2TransfusionContext(unittest.TestCase):
    """G3②（MY008R2 R8）：有输血依赖的方案中，血红蛋白短期跳升（≥30 g/L / 7 天）附输血语境提示
    （方案在入排/主要终点/补救规则引用输血 → 短期跳升可能来自红细胞输注而非疾病变化）。"""

    MET = 'lab:血红蛋白（虚构）'

    def test_hb_short_jump_gets_transfusion_context(self):
        from types import SimpleNamespace
        import ctcae
        from mm_build import build_labrows
        base = {'sid': 'S1', 'post': False, 'clin': 0, 'value': 80.0, 'raw': '80', 'lo': 110, 'hi': 160,
                'unit': 'g/L', 'visit': 'V1', 'date': '2026-01-02', 'sheet': '检验', 'row': 2, 'wb': 'edc',
                'grade': 0, 'links': [], 'reason': None, 'desc': '', 'group': '血常规', 'base': None, 'mid': self.MET}
        base['base'] = base

        def post(visit, date, value, row):
            return {'sid': 'S1', 'post': True, 'clin': 2, 'value': value, 'raw': str(value), 'lo': 110, 'hi': 160,
                    'unit': 'g/L', 'visit': visit, 'date': date, 'sheet': '检验', 'row': row, 'wb': 'edc',
                    'grade': 0, 'links': [], 'reason': None, 'desc': '', 'group': '血常规', 'base': base,
                    'pct': (value - 80.0) / 80 * 100, 'mid': self.MET}
        rows = [base, post('V2', '2026-02-01', 82.0, 5), post('V3', '2026-02-04', 120.0, 6)]   # 3 天 +38 g/L
        C = SimpleNamespace(
            A={'aeMatch': [], 'labDomains': ['lab', 'vs', 'ecg']},
            S={'study': {'design': {'facts': []},
                         'criteria': [{'no': 'E5', 'kind': 'exclusion', 'text': '筛选前 3 个月内有红细胞输注史者不得入组'}]}},
            cfg={'thresholds': {'base': 0.3}},
            F={('S1', self.MET): rows}, pop={'S1'},
            subj={'S1': {'site': '01'}}, src={'sheets': {}},
            metric={self.MET: {'label': '血红蛋白（虚构）', 'n': 3, 'nq': 0, 'hasClin': True}},
            aeEnd={}, mh_by={'S1': []}, ae_by={'S1': []}, btype={},
            G=ctcae.load({'grading': {'version': '5.0'}}), cmap={}, labrows=[])
        C.GL = C.G.label
        build_labrows(C)
        ctx = ' '.join(C.labrows[0]['ctx']) if C.labrows else ''
        self.assertIn('输血', ctx, ctx)
        self.assertIn('短期', ctx)

    def test_no_transfusion_note_without_protocol_dependency(self):
        """对照：方案不引用输血时不附输血语境（同数据形态）。"""
        from types import SimpleNamespace
        import ctcae
        from mm_build import build_labrows
        base = {'sid': 'S1', 'post': False, 'clin': 0, 'value': 80.0, 'raw': '80', 'lo': 110, 'hi': 160,
                'unit': 'g/L', 'visit': 'V1', 'date': '2026-01-02', 'sheet': '检验', 'row': 2, 'wb': 'edc',
                'grade': 0, 'links': [], 'reason': None, 'desc': '', 'group': '血常规', 'base': None, 'mid': self.MET}
        base['base'] = base

        def post(visit, date, value, row):
            return {'sid': 'S1', 'post': True, 'clin': 2, 'value': value, 'raw': str(value), 'lo': 110, 'hi': 160,
                    'unit': 'g/L', 'visit': visit, 'date': date, 'sheet': '检验', 'row': row, 'wb': 'edc',
                    'grade': 0, 'links': [], 'reason': None, 'desc': '', 'group': '血常规', 'base': base,
                    'pct': (value - 80.0) / 80 * 100, 'mid': self.MET}
        rows = [base, post('V2', '2026-02-01', 82.0, 5), post('V3', '2026-02-04', 120.0, 6)]
        C = SimpleNamespace(
            A={'aeMatch': [], 'labDomains': ['lab', 'vs', 'ecg']},
            S={'study': {'design': {'facts': []}, 'criteria': []}},
            cfg={'thresholds': {'base': 0.3}},
            F={('S1', self.MET): rows}, pop={'S1'},
            subj={'S1': {'site': '01'}}, src={'sheets': {}},
            metric={self.MET: {'label': '血红蛋白（虚构）', 'n': 3, 'nq': 0, 'hasClin': True}},
            aeEnd={}, mh_by={'S1': []}, ae_by={'S1': []}, btype={},
            G=ctcae.load({'grading': {'version': '5.0'}}), cmap={}, labrows=[])
        C.GL = C.G.label
        build_labrows(C)
        ctx = ' '.join(C.labrows[0]['ctx']) if C.labrows else ''
        self.assertNotIn('输血', ctx, ctx)


class V6Round2KriPemConsistency(unittest.TestCase):
    """G4（MY008R2 R6）：总览 KRI「主要终点缺失」与有效性页同一判定——criticalItems 绑定失败时，
    有效性页若已按终点配置生成趋势，KRI 不再写「找不到对应指标」（两处取同一判定结果）。"""

    @staticmethod
    def _C(efficacy_cfg=(), efficacy_rows=()):
        from types import SimpleNamespace
        subj = {'S1': {'site': '01', 'fd': '2026-01-01', 'status': '已入组'}}
        due = [['S1', '01', 'W8', '2026-02-23', '2026-03-01', '2026-02-25', 'ok', 56, 57, 3, 3, 0]]
        return SimpleNamespace(
            A={'pd': {'criticalVisits': ['W8'], 'criticalItems': '某无关评分'},
               'efficacy': list(efficacy_cfg), 'visitWindows': {'W8': [57, 3, 3]}},
            subj=subj, S=subj, pop={'S1'}, visits=[], efficacy=list(efficacy_rows), findings=[],
            aes=[], queries=[], labrows=[], entry=[], pdd={'potential': [], 'rules': []},
            cfg={'study': {'planned': 10}, 'thresholds': {}},
            ops={'cutoff': '2026-03-05', 'ex': {}, 'due': due, 'fu': {'S1': 60}, 'fresh': {'01': ['2026-03-01', 4, 1]}})

    def test_kri_not_found_only_when_eff_also_empty(self):
        """红测：criticalItems 匹配不到检验/量表指标名，但终点配置已按 eff: 源生成数据 → na 不得写「找不到」。"""
        from monitor_v5 import kri
        C = self._C(efficacy_cfg=[{'id': 'pe1', 'src': 'eff:虚构量表', 'label': '虚构量表总评'}],
                    efficacy_rows=[{'sid': 'S1', 'metric': '虚构量表', 'visit': 'W8', 'value': 5}])
        na = kri(C)['na']
        self.assertIn('pem', na)
        self.assertNotIn('找不到', na['pem'], na['pem'])

    def test_kri_not_found_kept_when_eff_empty(self):
        """对照：有效性侧也无数据 → 保留「找不到对应指标」（口径不变）。"""
        from monitor_v5 import kri
        na = kri(self._C())['na']
        self.assertIn('找不到', na['pem'])


class Sar3H3EngineTests(unittest.TestCase):
    """第 3 轮 SAR H3①②（引擎侧）：定性（阳性）判定统一走 result_state——删失界/低于检测限类写法不是阳性；
    「+」正则不得吃科学计数 E+（「小于 5.0E+1」为删失界）。夹具全虚构。"""

    def test_result_state_detection_limit_and_chinese_censored(self):
        from common import result_state
        self.assertEqual(result_state('小于 5.0E+1'), ('below', 50.0))       # 修前不识别（红）
        self.assertEqual(result_state('低于检出限'), ('below', None))         # 修前不识别（红）
        self.assertEqual(result_state('<检测下限'), ('below', None))          # 既有口径不回归
        self.assertEqual(result_state('低于检测下限'), ('below', None))

    def test_elig_qualitative_below_limit_not_positive(self):
        from mm_build import _elig_bad
        old_re = '阳性|\\+|reactive|positive|检出'          # 旧构建已编译进规则的正则（含裸 \+）
        E = {'re': old_re}
        for raw in ('小于 5.0E+1', '<5.0E+1', '低于检出限', '<检测下限', '阴性', '(-)'):
            self.assertFalse(_elig_bad(E, raw), raw)                          # 修前 E+/检出限 判阳性（红）
        for raw in ('阳性', '+', '1+', '弱阳性', 'reactive'):
            self.assertTrue(_elig_bad(E, raw), raw)                           # 真阳性照常命中

    def test_gate_companion_below_limit_not_positive(self):
        from types import SimpleNamespace
        from collections import defaultdict
        import mm_build
        for raw, want in (('低于检出限', False), ('小于 5.0E+1', False), ('阳性', True)):
            C = SimpleNamespace(F=defaultdict(list), metric={'lab:伴随指标': {'label': '伴随指标'}})
            C.F[('S1', 'lab:伴随指标')].append(
                {'sid': 'S1', 'mid': 'lab:伴随指标', 'test': '伴随指标', 'visit': 'SCR', 'date': '2026-01-05',
                 'raw': raw, 'value': None, 'unit': '', 'lo': None, 'hi': None, 'clin': None, 'post': False,
                 'sheet': 'LB', 'row': 4, 'wb': '', 'links': []})
            g = {'metric': '伴随指标', 'label': '伴随指标', 're': '阳性|\\+|reactive|positive|检出'}
            r = {'sid': 'S1', 'mid': 'lab:主指标', 'test': '主指标', 'visit': 'SCR', 'date': '2026-01-05',
                 'raw': '5000', 'value': 5000.0, 'unit': '拷贝数/mL', 'lo': None, 'hi': None, 'clin': None,
                 'post': False, 'sheet': 'LB', 'row': 3, 'wb': '', 'desc': '', 'links': []}
            self.assertEqual(mm_build._gate_ok(C, 'S1', g, r), want, raw)     # 修前检出限/E+ 判 gate 满足（红）


class Sar3H1PrivacyOutletTests(unittest.TestCase):
    """第 3 轮 SAR H1（R10，最重）：隐私列判定收口为 common.pii_column 一处，三出口共用——
    原始数据层（raw_export）已有过滤，质疑/偏离抽屉的原始行摘录（build_ex → extra.js KZX.ex/pdex 的 f 字段）
    修前透传「姓名缩写」等隐私列。虚构工作簿与摘录数据。"""

    def _ctx(self, td):
        from types import SimpleNamespace
        from openpyxl import Workbook
        p = Path(td) / 'edc.xlsx'
        wb = Workbook()
        ws = wb.active
        ws.title = 'LB'
        ws.append(['受试者编号', '姓名缩写', '研究者姓名', '电话', '结果'])   # 隐私列：缩写/姓名/电话
        ws.append(['01001', 'ZMS', '某研究者', '13800000000', '88'])
        ws.append(['01001', 'ZMS', '某研究者', '13800000000', '102'])
        wb.save(p)
        sheets = {'edc:LB': {'wb': 'edc', 'sheet': 'LB', 'label_row': 1, 'hl': ['结果']}}
        C = SimpleNamespace(src={'sheets': sheets, 'workbooks': {'edc': str(p)}},
                            queries=[{'id': 'Q001', 'sid': '01001', 'ev': [['edc:LB', 2]], '_cro': ''}],
                            pdd={'potential': [], 'confirmed': [{'id': 'PD1', 'src': [['edc:LB', 3, '结果']]}]},
                            extq=[])
        return C

    def test_build_ex_filters_privacy_columns(self):
        import tempfile
        import mm_build
        from common import pii_column
        with tempfile.TemporaryDirectory() as td:
            C = self._ctx(td)
            ex, pdex = mm_build.build_ex(C)
            f = ex['Q001']['rows'][0]['f']
            self.assertNotIn('姓名缩写', f)                                  # 修前透传（红）
            self.assertNotIn('研究者姓名', f)
            self.assertNotIn('电话', f)
            self.assertIn('结果', f)                                          # 业务列照常摘录
            pf = pdex['PD1'][0]['f']
            self.assertNotIn('姓名缩写', pf)                                  # 偏离抽屉同口径（红）
            self.assertIn('结果', pf)

    def test_pii_column_shared_with_raw_export(self):
        """收口：raw_export 与 build_ex 用同一判定函数（raw_export 既有行为不回归）。"""
        import raw_export
        from common import pii_column
        for lab in ('姓名缩写', '受试者姓名', '身份证号', '联系电话', '家庭住址', 'Email', 'Initials'):
            self.assertTrue(pii_column(lab), lab)
            self.assertTrue(raw_export.pii_column is pii_column)              # 同一函数（红：raw_export 原用本地 PII）
        for lab in ('结果', '受试者编号', '访视', '临床意义'):
            self.assertFalse(pii_column(lab), lab)


class Sar3H4IeCheckTagTruthTests(unittest.TestCase):
    """第 3 轮 SAR H4（R8）：入排页「数据核查」绿色只能由真实编译产物回填——标了『可数据核对』但未编译出
    核查引擎条目的降级为灰色「需人工」并列入构建缺口清单（不再仅凭标记显示绿色）。"""

    A = ROOT / 'templates/site/assets'

    def test_green_requires_compiled_rule(self):
        t = (self.A / 'p-study.js').read_text(encoding='utf-8')
        self.assertNotIn("ck==='data'||e?", t.replace(' ', ''))          # 修前：标记即绿（红）
        self.assertIn('需人工', t)                                       # 未编译的降级标签
        self.assertIn('未编译', t)                                       # 缺口清单条目类型
        self.assertIn(")==='data'&&!coded(c.text)", t.replace(' ', ''))   # 未编译判定按真实编译产物回填（coded）


class Sar3H5AesiCaliberTests(unittest.TestCase):
    """第 3 轮 SAR H5：AESI 口径统一——总览（EDC 已标记）与安全页（勾选∪定义命中）两种口径无标签；
    统一双口径「已标记 X / 符合定义待核实 Y」，两页显示时明确标注。虚构记录。"""

    def test_aesi_caliber_dual_counts(self):
        from types import SimpleNamespace
        import mm_build
        aes = [{'sid': 'S1', 'te': True, 'aesi': True, '_aesi_term': True, '_aesi_def': ['A'], 't': '已标且符合定义'},
               {'sid': 'S1', 'te': True, 'aesi': False, '_aesi_term': True, '_aesi_def': ['A'], 't': '符合定义未标'},
               {'sid': 'S2', 'te': True, 'aesi': False, '_aesi_term': True, '_aesi_def': ['A'], 't': '符合定义未标'},
               {'sid': 'S2', 'te': True, 'aesi': False, '_aesi_term': True, '_aesi_def': [], 't': '程度限定定义仅术语命中（可能符合，不计）'},
               {'sid': 'S2', 'te': True, 'aesi': False, '_aesi_term': False, '_aesi_def': [], 't': '无关'}]
        C = SimpleNamespace(aes=aes, pop={'S1', 'S2'})
        cal = mm_build.aesi_caliber(C)
        self.assertEqual(cal['marked'], 1)                                   # 修前无此函数（红）
        self.assertEqual(cal['defHit'], 2)                                   # 符合定义且未标（待核实）

    def test_pages_render_dual_caliber_labels(self):
        A = ROOT / 'templates/site/assets'
        idx = (A / 'p-index.js').read_text(encoding='utf-8')
        pro = (A / 'profile.js').read_text(encoding='utf-8')
        self.assertIn('符合定义待核实', idx)                                  # 修前总览只写「AESI N」无口径标签（红）
        self.assertIn('已标', idx)
        self.assertIn('符合定义待核实', pro)                                  # 修前安全概况行＝勾选∪定义命中混一口径（红）
        self.assertIn('EDC 已标', pro)


class Sar3H6QueryMergeCountTests(unittest.TestCase):
    """第 3 轮 SAR H6：同格质疑合并不静默——合并条目带 merged 计数（含被并入条数），
    KZ.meta.qsSignals＝信号总数、qs＝条目数；页头/清单有合并时加脚注。虚构信号。"""

    def _C(self):
        from types import SimpleNamespace
        from collections import defaultdict

        def o(row, sum_):
            return {'sid': 'S1', 'cat': '妊娠暴露核查', 'pr': 4, 'sum': sum_, 'v': 'SCR', 'd': '2026-01-05',
                    'sh': 'edc:LB', 'row': row, 'test': '虚构指标', 'clin': None, 'qkey': f'k{row}',
                    '_rule': {}, 'rel': [], 'ctx': [], 'q': [], 'cro': ''}
        return SimpleNamespace(A={}, cfg={'thresholds': {}}, findings=[], sheet_groups=defaultdict(set),
                               labrows=[], extq=[], S={}, queries=None, qcommon=None, src={'sheets': {}, 'workbooks': {}},
                               others=[o(3, '虚构事实甲，'), o(3, '虚构事实乙，')],   # 同 sid/同表/同行 → 合并
                               subj={'S1': {'site': '01'}})

    def test_same_cell_merge_keeps_count(self):
        import mm_build
        C = self._C()
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        try:
            mm_build.build_queries(C)
        finally:
            mm_build.oth_qkey = orig
        self.assertEqual(len(C.queries), 1)                                  # 同格合并为一条（既有行为）
        q = C.queries[0]
        self.assertEqual(q.get('merged'), 2)                                 # 修前无 merged 计数（红）——2 条信号并入 1 条
        self.assertIn('另：', q['text'])                                     # 被并入条目正文保留（既有行为）

    def test_page_renders_merge_footnote(self):
        t = (ROOT / 'templates/site/assets/p-queries.js').read_text(encoding='utf-8')
        self.assertIn('qsMerged', t)                                         # 修前页头无合并脚注（红）
        w = Path('/Users/smkzw/Documents/康哲项目资料/AI/医学经理工作台/implementation/workbench/mm3/mm3/lifecycle/workbook.py')
        if w.is_file():
            self.assertIn('merged', w.read_text(encoding='utf-8'))           # 工作簿清单 note 同口径脚注


class Sar3H7PdAnnotationVisitAlignTests(unittest.TestCase):
    """第 3 轮 SAR H7（R7）：PD 附注（ctx 里的「较基线…%」涨幅）与所引用的时点取自同一条记录——
    修前引用访视 A 的数值，配访视 B 的涨幅百分比。虚构检验组。"""

    def test_pd_annotation_uses_cited_point_percentage(self):
        from types import SimpleNamespace
        from collections import defaultdict
        import pd_rules
        # pts 元素位序（build_labrows）：0=visit 1=date 2=raw 3=unit 4=grade 5=clin 6=pct 7=sheet 8=row
        pts = [('V2', '2026-02-01', '102', 'U/L', 2, 2, 200.0, 'LB', 9, '', '', ''),
               ('V1', '2026-01-05', '88', 'U/L', 3, 2, 50.0, 'LB', 3, '', '', '')]
        g = {'risk': 'CSX', 'sid': 'S1', 'mid': 'lab:虚构指标', 'test': '虚构指标',
             'pts': pts, 'qkey': '',
             'ctx': ['研究者归因：研究疾病；给药后较基线加重（较基线升高 200%）']}   # 200% 来自 V2
        C = SimpleNamespace(A={'pd': {}}, S={}, cfg={}, subj={'S1': {'site': '01'}}, pop={'S1'},
                            others=[], labrows=[g], ae_by={'S1': []}, aes=[], GL='CTCAE',
                            F=defaultdict(list), visits=[], dosed=set())
        C.cfg['cutoff'] = '2026-03-01'
        pd = pd_rules._PD(C)
        pd.from_signals()
        it = next(i for i in pd.items if i['rule'] == 'SAFE-01')
        self.assertIn('V1', it['fact'])                                      # 引用点＝等级最高者（G2② 既有）
        joined = ' '.join(it['ctx'])
        self.assertNotIn('200%', joined)                                     # 修前附注带另一访视的 200%（红）
        self.assertIn('50%', joined)                                         # 附注涨幅与所引 V1 时点同源（修后）


class Sar3H9PdClassifyTests(unittest.TestCase):
    """第 3 轮 SAR H9：已记录 PD 归类（35/317 错类）——「背景药物」类记录不归「评估检查」（描述常带
    「未做检查」字样）；「随机与盲态」只认真正的随机/揭盲操作（背景交代「于某日随机」不归随机类）。虚构描述。"""

    def test_background_medication_not_assessment(self):
        from pd_rules import _classify
        for txt in ('其他 背景药物 随机前因病情需要开始背景用药某虚构片剂，期间未进行实验室检查评估',
                    '合并用药 背景治疗：使用背景药物某虚构胶囊',
                    '其他 使用背景用药某虚构药片'):
            self.assertEqual(_classify(txt), 'CM', txt)                     # 修前归 ASMT/OTH（红）

    def test_random_narrative_not_rand(self):
        from pd_rules import _classify
        # 背景交代「于某日随机」不是随机类偏离 → 按超窗/访视归类（修前 RAND 先命中，红）
        self.assertEqual(_classify('访视超窗 该受试者于 2025-09-10 随机，V5 访视超窗 12 天'), 'VIS')
        # 真正的随机/盲态操作照常归 RAND
        for txt in ('随机与盲态 未经随机即给予研究药物', '随机与盲态 数据管理员误揭盲', '随机与盲态 盲态破坏',
                    '随机与盲态 重新随机', '随机与盲态 随机号分配错误'):
            self.assertEqual(_classify(txt), 'RAND', txt)
        self.assertEqual(_classify('访视超窗 随机后 V5 超窗'), 'VIS')       # 「随机后」为时间状语，不是操作


class Sar3H10CroTextVisibleKeyTests(unittest.TestCase):
    """第 3 轮 SAR H10：CRO 查重原文以可见键 croText 进 queries.json——_cro 下划线键被 KZ 输出层剥离，
    工作簿「CRO 查重」列全空。虚构 CRO 质疑。"""

    def test_query_carries_visible_cro_text(self):
        from types import SimpleNamespace
        from collections import defaultdict
        import mm_build
        o = {'sid': 'S1', 'cat': '妊娠暴露核查', 'pr': 4, 'sum': '虚构指标升高明显请核实，', 'v': 'SCR',
             'd': '2026-01-05', 'sh': 'edc:LB', 'row': 3, 'test': '虚构指标', 'clin': None, 'qkey': 'k1',
             '_rule': {}, 'rel': [], 'ctx': [], 'q': [], 'cro': ''}
        C = SimpleNamespace(A={}, cfg={'thresholds': {}}, findings=[], sheet_groups=defaultdict(set),
                            labrows=[], S={}, queries=None, qcommon=None, src={'sheets': {}, 'workbooks': {}},
                            subj={'S1': {'site': '01'}},
                            extq=[{'sid': 'S1', 'form': 'edc:LB', 'text': '虚构指标升高明显，请核实原因'}],
                            others=[o])
        orig = mm_build.oth_qkey
        mm_build.oth_qkey = lambda *a, **k: ''
        try:
            mm_build.build_queries(C)
        finally:
            mm_build.oth_qkey = orig
        q = C.queries[0]
        self.assertEqual(q['cro'], '同主题已查重')                            # CRO 查重命中（既有）
        self.assertTrue(q.get('croText'))                                    # 修前原文只存 _cro（下划线键被输出层剥离）（红）



class ReviewerFix20261109(unittest.TestCase):
    """审阅者 2026-11-09 对第 1–3 轮修复波的回归修正（虚构取值）。"""

    def test_signed_numbers_and_unit_multiplier(self):
        from common import num_state
        self.assertEqual(num_state('-2.5'), ('value', -2.5))            # 带符号文本数值不得丢
        self.assertEqual(num_state('+1.5'), ('value', 1.5))
        self.assertEqual(num_state('9.5×10^9/L'), ('value', 9.5))       # ×10^9/L 是单位不是数量级
        self.assertEqual(num_state('12×10^12/L'), ('value', 12.0))
        self.assertEqual(num_state('<1*10^3'), ('below', 1000.0))       # 拷贝数写法仍按数量级
        self.assertEqual(num_state('5.26×10^3'), ('value', 5260.0))

    def test_bare_grade_words_not_numbers(self):
        from common import num_state
        self.assertIsNone(num_state('中度'))                            # 分值随量表而异，不猜
        self.assertEqual(num_state('3分-中度'), ('value', 3.0))
        self.assertIsNone(num_state('1+'))

    def test_pii_columns(self):
        from common import pii_column
        for c in ('SUBJ_INITIALS', 'SubjectInitials', '姓名缩写', '受试者缩写', '联系电话'):
            self.assertTrue(pii_column(c), c)
        for c in ('Init Dose', '中心缩写', '检验项目缩写', '研究药物名称'):
            self.assertFalse(pii_column(c), c)

    def test_censored_value_not_asserted_positive(self):
        """竞争法试剂高值＝阴性：「>2.70 Index」不得据删失符号断言阳性（审阅者 2026-11-09 回放实证）。"""
        from mm_build import _elig_bad
        E = {'re': r'阳性|\+|检出'}
        self.assertFalse(_elig_bad(E, '>2.70'))
        self.assertFalse(_elig_bad(E, '<1.0E+02'))
        self.assertTrue(_elig_bad(E, '阳性'))

    def test_stratification_errors_are_randomisation_pd(self):
        import re
        import pd_rules
        rx = dict(pd_rules.CAT_RE)['RAND']
        self.assertTrue(re.search(rx, '受试者分层因素错误'))
        self.assertFalse(re.search(rx, '于某日随机后访视超窗'))

    def test_qualified_aesi_term_only_is_not_definite(self):
        """「ALT显著增高」类定义无分级/界值：术语命中不断言「符合定义未勾选」（审阅者 2026-11-09，SAR 9 条全误报）。"""
        from mm_build import _AESI_QUAL
        self.assertTrue(_AESI_QUAL.search('ALT显著增高'))
        self.assertFalse(_AESI_QUAL.search('角膜炎'))

    def test_disease_not_ae_clause_changes_disw_wording(self):
        """用户 2026-11-09：方案有「研究疾病相关异常除非较预期更严重否则不作为 AE」时，DISW 问「是否较预期病情更严重」。"""
        from types import SimpleNamespace
        from mm_build import disease_not_ae
        self.assertTrue(disease_not_ae(SimpleNamespace(A={'diseaseNotAEClause': {'quote': '…'}})))
        self.assertFalse(disease_not_ae(SimpleNamespace(A={})))
        src = open(__file__.replace('test_mm4.py', 'mm_build.py'), encoding='utf-8').read()
        self.assertIn('是否较预期病情更严重', src)

    def test_disease_no_direction_no_numeric_worsening(self):
        """归因研究疾病且无疾病方向/通用方向（铁蛋白双向、补体 C3）：不凭数值判加重；有通用方向的（尿红细胞 ↑）照判。"""
        from ext_rules import worse_vs_base, set_metric_dir
        set_metric_dir(None)
        b = {'value': 100.0, 'grade': 0}
        for mid in ('lab:铁蛋白', 'lab:补体C3水平'):
            r = {'value': 400.0, 'hi': 300, 'grade': 0, 'clin': 2, 'mid': mid, 'unit': 'x'}
            self.assertIsNone(worse_vs_base(r, b, 0.3, disease=True, ddir=None), mid)
        r = {'value': 50.0, 'hi': 5, 'grade': 0, 'clin': 2, 'mid': 'lab:尿红细胞', 'unit': '/ul'}
        self.assertIn('较基线升高', worse_vs_base(r, {'value': 10.0, 'grade': 0}, 0.3, disease=True, ddir=None) or '')

    def test_redact_row_masks_initials_in_free_text(self):
        """同一行隐私列取值（姓名缩写）夹在自由文本里同样打码；短缩写/非整词不误伤（审阅者 2026-11-09）。"""
        from common import redact_row
        labels = ['受试者编号', '姓名缩写', 'PD 详述']
        out = redact_row(labels, ['01001', 'HLSH', '受试者HLSH 于访视超窗；HLSHX 非整词'])
        self.assertEqual(out[2], '受试者＊＊ 于访视超窗；HLSHX 非整词')
        self.assertEqual(redact_row(labels, ['01001', 'LT', 'LT 升高'])[2], 'LT 升高')
        self.assertEqual(redact_row(['编号', 'PD 详述'], ['1', '受试者BAYI，筛选号 03005'])[1], '受试者＊＊，筛选号 03005')   # 本行无缩写列
        self.assertEqual(redact_row(['编号', '说明'], ['1', '受试者ALT升高；患者CRP 升高'])[1], '受试者ALT升高；患者CRP 升高')   # 检验缩写不误伤

    def test_serology_positivity_by_reference_range(self):
        """定量报告的定性指标按本行参考范围判阳：上限型 >250（hi 0.05）阳性；竞争法 >2.70（lo 1.0）阴性；无范围不猜。"""
        from mm_build import _ref_positive, _elig_bad_r
        self.assertTrue(_ref_positive({'raw': '>250.00', 'hi': 0.05}))
        self.assertFalse(_ref_positive({'raw': '>2.70', 'lo': 1.0}))
        self.assertTrue(_ref_positive({'raw': '0.35', 'lo': 1.0}))
        self.assertFalse(_ref_positive({'raw': '<0.05', 'hi': 0.05}))
        self.assertIsNone(_ref_positive({'raw': '>2.70'}))
        self.assertTrue(_elig_bad_r({'re': '阳性|\\+'}, {'raw': '>250.00', 'hi': 0.05}))
        self.assertFalse(_elig_bad_r({'re': '阳性|\\+'}, {'raw': '>2.70', 'lo': 1.0}))

    def test_transfusion_checks(self):
        """有输血记录的研究：Hb 从输血区间 14 天上升 ≥20 g/L 且期间无输血 → 提示；疗效区间（≥80）回升不提示；无输血记录的研究不触发。"""
        from types import SimpleNamespace
        import mm_build
        got = []
        orig = mm_build.add_other
        mm_build.add_other = lambda C, sid, cat, pr, summ, *a, **k: got.append((sid, cat, summ))
        try:
            def C_(proc):
                F = {('S1', 'lab:血红蛋白'): [
                    {'post': True, 'value': 55.0, 'date': '2026-01-01', 'unit': 'g/L'},
                    {'post': True, 'value': 95.0, 'date': '2026-01-15', 'unit': 'g/L'},
                    {'post': True, 'value': 125.0, 'date': '2026-01-29', 'unit': 'g/L'}]}
                return SimpleNamespace(proc=proc, cm_by={'S1': []}, pop={'S1'}, subj={'S1': {'icf': '2025-12-01'}},
                                       F=F, metric={'lab:血红蛋白': {'label': '血红蛋白'}})
            mm_build.transfusion_checks(C_([{'sid': 'S1', 'term': '悬浮红细胞输注', 'date': '2025-06-01', 'sheet': 'TR', 'row': 2}]))
            self.assertEqual([g[1] for g in got], ['输血记录核对'])          # 55→95 提示；95→125 不提示
            got.clear()
            mm_build.transfusion_checks(C_([]))
            self.assertEqual(got, [])                                       # 研究不采集输血：不触发
        finally:
            mm_build.add_other = orig

    def test_hcg_low_values_not_pregnancy(self):
        """hCG 0.66 mIU/mL（本地参考上限 0.6）不是妊娠证据；15808 是。"""
        from ext_rules import _hcg_low
        self.assertTrue(_hcg_low({'value': 0.66, 'unit': 'mIU/mL', 'hi': 0.6, 'clin': 1}))
        self.assertTrue(_hcg_low({'value': 12.0, 'unit': 'mIU/mL', 'clin': 1}))
        self.assertFalse(_hcg_low({'value': 12.0, 'unit': 'mIU/mL', 'clin': 2}))
        self.assertFalse(_hcg_low({'value': 15808.0, 'unit': 'mIU/ml', 'clin': 2}))

    def test_disposition_ae_withdraw_vs_completed(self):
        """AE 记导致退出、研究结束页记完成 → 处置一致性提示；未完成的不提示。"""
        from types import SimpleNamespace
        import mm_build
        got = []
        orig = mm_build.add_other
        mm_build.add_other = lambda C, sid, cat, pr, summ, *a, **k: got.append((sid, cat))
        try:
            ae = {'sid': 'S1', 'wd': '是', 't': '贫血', 's': '2026-01-05', 'sh': 'AE', 'row': 3, 'n': 1}
            C = SimpleNamespace(aes=[ae, dict(ae, sid='S2')], pop={'S1', 'S2'},
                                subj={'S1': {'eos_done': '是'}, 'S2': {'eos_done': '否'}})
            mm_build.disposition_checks(C)
            self.assertEqual(got, [('S1', '处置与AE一致性核对')])
        finally:
            mm_build.add_other = orig

    def test_below_limit_variants(self):
        """「低出检出限」（笔误）「检出限以下」都是低于检测下限，不得被「检出」阳性正则命中。"""
        from common import result_state
        from mm_build import _elig_bad
        for t in ('低出检出限', '低于检出限', '检出限以下', '<检测下限'):
            self.assertEqual(result_state(t), ('below', None), t)
            self.assertFalse(_elig_bad({'re': '阳性|检出'}, t), t)

    def test_whodrug_lookup_and_atc_match(self):
        """本地 WHODrug 对照（虚构迷你表）：最长物质名子串＋剂型收窄途径组；条目与记录都有 ATC 时按 ATC 判。"""
        import importlib
        import json
        import os
        import tempfile
        import whodrug
        tbl = {"names": {"地塞米松": ["D07AB", "H02AB", "S01BA"], "地塞米松磷酸钠": ["H02AB", "S01BA"], "糠酸莫米松": ["D07AC", "R01AD", "R03BA"]}}
        p = os.path.join(tempfile.mkdtemp(), "w.json")
        open(p, "w", encoding="utf-8").write(json.dumps(tbl, ensure_ascii=False))
        os.environ["MM_WHODRUG"] = p
        try:
            importlib.reload(whodrug)
            self.assertEqual(whodrug.atc_for("地塞米松磷酸钠注射液"), ["H02AB"])
            self.assertEqual(whodrug.atc_for("糠酸莫米松乳膏"), ["D07AC"])
            self.assertEqual(whodrug.atc_for("糠酸莫米松鼻喷雾剂"), ["R01AD"])
            self.assertEqual(whodrug.atc_for("虚构药"), [])
            from mm_build import _drug_hit, _atc_decided
            import re as _re
            c = {"t": "糠酸莫米松鼻喷雾剂", "atc": ["R01AD"]}
            P = {"atc": ["D07"], "re": "莫米松"}
            self.assertTrue(_drug_hit(P, c, _re.compile("莫米松")))          # 药名命中照旧（ATC 不否决）……
            self.assertFalse(_atc_decided(P, c))                              # ……途径仍由文本守卫排除鼻用
            c2 = {"t": "某虚构商品名乳膏", "atc": ["D07AC"]}
            self.assertTrue(_drug_hit(P, c2, _re.compile("莫米松")))         # 药名认不出的商品名：ATC 补上
            self.assertTrue(_atc_decided(P, c2))                              # 只由 ATC 命中 → 途径以 ATC 为准
            c3 = {"t": "某虚构商品名", "atc": ["D07AC", "R03BA"], "atc_src": "lookup"}
            self.assertFalse(_drug_hit(P, c3, _re.compile("莫米松")))        # 对照跨解剖大类（途径不明）→ 不凭 ATC 断言
            c3["atc_src"] = "edc"
            self.assertTrue(_drug_hit(P, c3, _re.compile("莫米松")))         # 申办方逐条编码照常可信
        finally:
            os.environ.pop("MM_WHODRUG", None)
            importlib.reload(whodrug)

    def test_tcm_specialty_and_ib_term_match(self):
        """「治疗AR的中药」只认对口专科（ZF）；内科类（ZA）要用药原因写的是该病；IB 预期不良反应要术语对得上。"""
        from types import SimpleNamespace
        from mm_build import _tcm_off_target, _same_event
        C = SimpleNamespace(A={'diseaseTerms': ['过敏性鼻炎']})
        P = {'forDisease': '过敏性鼻炎', 're': '中药'}
        self.assertFalse(_tcm_off_target(P, {'t': '通窍鼻炎片', 'tcm': ['ZF02'], 'why': ''}, C))
        self.assertTrue(_tcm_off_target(P, {'t': '小建中片', 'tcm': ['ZA05A'], 'why': '胃痛'}, C))
        self.assertFalse(_tcm_off_target(P, {'t': '玉屏风颗粒', 'tcm': ['ZA01D'], 'why': '过敏性鼻炎'}, C))
        C2 = SimpleNamespace(A={'diseaseTerms': ['SAR']})        # 研究疾病只写缩写（SAR）也要认出耳鼻喉专科
        self.assertTrue(_tcm_off_target({'name': '治疗AR的中药（全身性中药制剂）', 're': '中药'}, {'t': '小建中片', 'tcm': ['ZA05A'], 'why': ''}, C2))
        self.assertTrue(_same_event({'t': '上呼吸道感染'}, '预期不良反应·上呼吸道感染'))
        self.assertFalse(_same_event({'t': '尿路感染'}, '预期不良反应·上呼吸道感染'))

    def test_tcm_effect_class_by_nhsa_category(self):
        """「具有平喘作用的中药」按医保目录中成药类别名判：平喘剂/化痰止咳平喘剂算，鼻病、解表剂不算（MGK 2026-11-14）。"""
        from types import SimpleNamespace
        from unittest import mock
        import mm_build, whodrug
        cats = {'ZA': '内科用药', 'ZA06': '化痰、止咳、平喘剂', 'ZA06E': '平喘剂', 'ZA01': '解表剂', 'ZA01A': '辛温解表剂',
                'ZF': '耳鼻喉科用药', 'ZF02': '鼻病'}
        C = SimpleNamespace(A={'diseaseTerms': ['哮喘']})
        P = {'name': '具有平喘作用的中药', 're': '中药|中成药'}
        with mock.patch.object(whodrug, '_load_nhsa', lambda: {'cats': cats}):
            self.assertFalse(mm_build._tcm_off_target(P, {'t': '桂龙咳喘宁胶囊', 'tcm': ['ZA06E'], 'why': ''}, C))
            self.assertTrue(mm_build._tcm_off_target(P, {'t': '鼻窦炎口服液', 'tcm': ['ZF02'], 'why': ''}, C))
            self.assertTrue(mm_build._tcm_off_target(P, {'t': '感冒清热颗粒', 'tcm': ['ZA01A'], 'why': ''}, C))

    def test_prohibited_exception_ask(self):
        from mm_build import _exc_ask
        r = _exc_ask({'note': '例外：控制重度哮喘急性发作和哮喘失控除外；因治疗…不作为禁用药物报告'}, {'why': ''})
        self.assertIn('是否用于控制重度哮喘急性发作和哮喘失控', r['rule']['ask'])
        self.assertEqual(_exc_ask({'note': '例外：外用药除外'}, {'why': ''}), {})
        self.assertEqual(_exc_ask({'note': '例外：控制急性发作除外'}, {'why': '急性发作'}), {})

    def test_latest_possible_partial_date(self):
        """部分停药日期按最晚可能日判洗脱：2022-10-uk 早于窗口即满足，不追问。"""
        from mm_build import _latest_date
        self.assertEqual(_latest_date('2025-07-uk'), '2025-07-31')
        self.assertEqual(_latest_date('2024-12-UK'), '2024-12-31')
        self.assertEqual(_latest_date('2023-uk-uk'), '2023-12-31')
        self.assertEqual(_latest_date(''), '9999-12-31')


if __name__ == '__main__':
    unittest.main(verbosity=1)
