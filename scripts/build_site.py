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
        _stamp_query_file(html, out)
    print('built', html)


def _stamp_query_file(html: Path, out: Path):
    """F7（V6 RUX）：交付说明的文件名从实际产物读取——export_queries 写完工作簿后，把真实文件名
    回写进已构建报告 data/core.js 的 cfg.query.file（页面不再依赖「首列版」硬编码兜底；工作台分列版
    工作簿由宿主在生命周期层同样回写，首列版/分列版联动）。"""
    import json
    cands = sorted(out.glob('*申办方MM_query*.xlsx'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        return
    p = html / 'data' / 'core.js'
    try:
        t = p.read_text(encoding='utf-8')
        i = t.index('window.KZ=') + len('window.KZ=')
        obj = json.loads(t[i:].rstrip().rstrip(';'))
        cfg = obj.setdefault('cfg', {})
        q = dict(cfg.get('query') or {})
        q['file'] = cands[0].name
        cfg['query'] = q
        p.write_text('window.KZ=' + json.dumps(obj, ensure_ascii=False, separators=(',', ':'), default=str) + ';',
                     encoding='utf-8')
    except (OSError, ValueError):
        pass


if __name__ == '__main__':
    main()
