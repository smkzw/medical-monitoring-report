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
                     mhMatch=[('血红蛋白', '贫血')], indBg=[], cmInd=self._rex(('保肝', '联苯双酯')),
                     mh_by={'S1': []}, cm_by={'S1': [{'t': '联苯双酯', 's': None, 'why': '保肝治疗', 'sh': 'CM', 'row': 2, 'wb': '', 'n': 1}]},
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
        self.assertEqual(ib_match(C, {'t': '肺炎', 'pt': '肺炎', 'soc': '感染及侵染类疾病', 'sae': True, 'g': '2级'}),
                         ['IB重要潜在风险·严重感染（同SOC，严重/≥3级）'])

    def test_cell_suffix_no_false_share(self):
        """回归守卫：淋巴细胞×中性粒细胞不因「细胞」误共享（公共前缀锚定）。"""
        from mm_build import ib_match
        C = self._C([{'term': '淋巴细胞计数减少', 'label': 'IB风险', 're': '', 'pt': '', 'soc': '各类检查', 'labs': []}])
        self.assertEqual(ib_match(C, {'t': '中性粒细胞计数减少', 'pt': '', 'soc': '各类检查', 'sae': True, 'g': '3级'}), [])


if __name__ == '__main__':
    unittest.main(verbosity=1)
