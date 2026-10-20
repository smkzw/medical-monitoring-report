#!/usr/bin/env python3
"""One-shot build: normalized tables + study.json → out/HTML (9-page report) + query workbook.

python3 build_site.py --study work/study.json --norm work/norm --out out [--echarts path/to/echarts.min.js] [--no-xlsx]

ECharts ≥ 6 is required (axis breaks). Resolution order: --echarts, $ECHARTS_JS, a cached copy in
~/.cache/mm-report/echarts.min.js, then download from jsDelivr / unpkg (echarts@6).
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = HERE.parent / 'templates' / 'site'
URLS = ['https://cdn.jsdelivr.net/npm/echarts@6/dist/echarts.min.js', 'https://unpkg.com/echarts@6/dist/echarts.min.js']


def get_echarts(explicit):
    for p in [explicit, os.environ.get('ECHARTS_JS'), str(Path.home() / '.cache/mm-report/echarts.min.js')]:
        if p and Path(p).is_file() and Path(p).stat().st_size > 500_000:
            return Path(p)
    cache = Path.home() / '.cache/mm-report/echarts.min.js'
    cache.parent.mkdir(parents=True, exist_ok=True)
    for u in URLS:
        try:
            with urllib.request.urlopen(u, timeout=60) as r:
                b = r.read()
            if len(b) > 500_000:
                cache.write_bytes(b)
                return cache
        except Exception as e:  # noqa
            print('  echarts download failed:', u, e)
    sys.exit('ECharts not found: pass --echarts /path/echarts.min.js (v6+)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', required=True)
    ap.add_argument('--norm', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--echarts')
    ap.add_argument('--no-xlsx', action='store_true')
    a = ap.parse_args()
    import json
    S = json.loads(Path(a.study).read_text(encoding='utf-8'))
    out = Path(a.out)
    html = out / 'HTML'
    if html.exists():
        shutil.rmtree(html)
    shutil.copytree(TPL, html)
    short = S.get('cfg', {}).get('study', {}).get('short', '临床研究')
    for f in html.glob('*.html'):
        f.write_text(f.read_text(encoding='utf-8').replace('{{SHORT}}', short), encoding='utf-8')
    logo = S.get('cfg', {}).get('brand', {}).get('logoFile')
    if logo:
        shutil.copy(Path(a.study).parent / logo, html / 'assets' / Path(logo).name)
        S['cfg']['brand']['logo'] = 'assets/' + Path(logo).name
    shutil.copy(get_echarts(a.echarts), html / 'assets' / 'echarts.min.js')
    r = subprocess.run([sys.executable, str(HERE / 'mm_build.py'), '--study', a.study, '--norm', a.norm, '--out', str(html / 'data'), '--audit', str(out / 'analysis')])
    if r.returncode:
        sys.exit(r.returncode)
    if not a.no_xlsx:
        r = subprocess.run([sys.executable, str(HERE / 'export_queries.py'), '--norm', a.norm, '--queries', str(out / 'analysis' / 'queries.json'), '--out', str(out)])
        if r.returncode:
            sys.exit(r.returncode)
    print('built', html)


if __name__ == '__main__':
    main()
