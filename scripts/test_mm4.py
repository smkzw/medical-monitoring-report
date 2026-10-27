#!/usr/bin/env python3
"""mm4 通用能力回归（关联字段写法、同名列引用、CS 原因、入排判定值）。运行：python3 scripts/test_mm4.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import parse_links  # noqa: E402


class LinkGrammar(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main(verbosity=1)
