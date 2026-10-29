#!/usr/bin/env python3
"""mm4 通用能力回归（关联字段写法、同名列引用、CS 原因、入排判定值）。运行：python3 scripts/test_mm4.py"""
import sys
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


class WorseningRule(unittest.TestCase):
    """用户 2026-10-27：0 级 → 1 级不单独算加重，须同时超出范围且同向较基线 ≥T_base。"""
    def test_grade_up(self):
        from ext_rules import grade_up
        self.assertFalse(grade_up(0, 1))
        self.assertTrue(grade_up(0, 2))
        self.assertTrue(grade_up(1, 2))
        self.assertFalse(grade_up(2, 2))

    def test_worse_vs_base(self):
        from mm_build import worse_vs_base
        b = {'grade': 0, 'value': 5.11}
        small = {'grade': 1, 'value': 5.54, 'hi': 5.2, 'lo': 0, 'oor': True}           # 0→1 级、+8%：不算
        self.assertIsNone(worse_vs_base(small, b, 0.3))
        big = {'grade': 1, 'value': 6.8, 'hi': 5.2, 'lo': 0, 'oor': True}              # 0→1 级、+33%：算
        self.assertIn('较基线升高', worse_vs_base(big, b, 0.3))
        self.assertIn('等级', worse_vs_base({'grade': 2, 'value': 5.6, 'hi': 5.2, 'oor': True}, {'grade': 1, 'value': 5.5}, 0.3))
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
        self.assertTrue(stated_worse({'desc': 'AD加重相关'}))
        self.assertTrue(stated_worse({'reason_raw': '与研究疾病加重有关'}))
        self.assertIsNone(stated_worse({'desc': '皮损未见加重'}))
        self.assertTrue(ae_covers({'s': '2026-07-uk', 'e': ''}, '2026-07-21'))
        self.assertFalse(ae_covers({'s': '2026-05-01', 'e': '2026-05-10'}, '2026-05-21'))


class ClinConsistency(unittest.TestCase):
    """用户 2026-10-27：同一受试者相同/相近结果一次判 NCS、一次判 CS → 风险（query），不作 PD。"""
    def test_same_level(self):
        from types import SimpleNamespace
        from ext_rules import same_level, judgment_only
        C = SimpleNamespace(A={})
        a = {'value': 319, 'hi': 250, 'lo': 120, 'clin': 1}
        self.assertTrue(same_level(C, a, {'value': 320, 'hi': 250, 'lo': 120}))
        self.assertFalse(same_level(C, a, {'value': 400, 'hi': 250, 'lo': 120}))        # 相差 >10%
        self.assertFalse(same_level(C, {'value': 151, 'clin': 1}, {'value': 152}))       # 无参考范围（心电图间期）不比较
        self.assertTrue(same_level(C, {'raw': '3+', 'clin': 1}, {'raw': '3+'}))
        self.assertFalse(same_level(C, {'raw': '1+', 'clin': 1}, {'raw': '3+'}))
        b = {'value': 320, 'hi': 250, 'lo': 120, 'clin': 2, 'post': True, 'base': {'value': 315, 'grade': 0}}
        self.assertTrue(judgment_only(C, b, [a, b], 0.3))                             # 只是改判，不按潜在 AE 漏记


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
        self.assertEqual(ib_match(C, {'t': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'sae': False, 'g': '3级'}), ['IB重要潜在风险·严重感染（同SOC，严重/≥3级）'])


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
        self.assertNotIn("['methods.html','审阅要点']]", kz)
        self.assertTrue(any(t.get('k') == 'pd' for t in self.KZ['review']))
        self.assertTrue(self.KZ['study'].get('calibers'))

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
        self.assertTrue(any('合并用药「' in (o.get('sum') or '') for o in self.KZ['others']), '演示数据应含合并用药类信号')
        # 同中心判定一致性：对照句不写英文「vs」
        self.assertTrue(self.KZ.get('cons'), '演示数据应含同中心判定对照')
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
        for f, bads in {'p-subjects.js': ("'ECG'", '生命体征/ECG'), 'p-methods.js': ('真实 listing',),
                        'p-deviations.js': ('listing 不含所需信息',), 'p-timeline.js': ('ECG/VS',), 'p-index.js': ('listing 首列',)}.items():
            t = (A / f).read_text(encoding='utf-8')
            for bad in bads:
                self.assertNotIn(bad, t, f'{f} 残留「{bad}」')
        # 审阅要点实例卡的外部质疑行：证据位置经 K.loc 显示中文表单名（V4.1：证据位置显示中文表单名）
        self.assertNotIn("P(c.sheet.replace(/^\\(\\d+\\)/,''),'sq')} 行${c.row}", (A / 'p-methods.js').read_text(encoding='utf-8'))


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


if __name__ == '__main__':
    unittest.main(verbosity=1)
