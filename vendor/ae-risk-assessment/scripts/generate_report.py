#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive HTML Report Generator for AE Underreporting Risk Assessment.
Produces a single self-contained HTML file with filtering, navigation, and tabbed centers.
"""
import html as html_mod
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def e(x):
    """HTML-escape a value."""
    if x is None:
        return "-"
    if isinstance(x, (int, float)):
        return str(x)
    return html_mod.escape(str(x), quote=True)


def norm(s):
    if s is None:
        return ""
    return str(s).strip()


def fmt_num(x):
    if x is None:
        return "-"
    if isinstance(x, float):
        if abs(x) >= 100:
            return f"{x:.0f}"
        return f"{x:.2f}".rstrip("0").rstrip(".")
    return str(x)


def risk_label(r):
    return {"high": "高风险", "medium": "关注", "low": "低风险", "info": "提示"}.get(r, r)


def risk_class(r):
    return {"high": "red", "medium": "yellow", "low": "green", "info": "blue"}.get(r, "none")


def risk_badge_class(r):
    return {"high": "danger", "medium": "warn", "low": "ok", "info": "info"}.get(r, "neutral")


def compact_visit(v):
    """Shorten visit name for display. Handles 数据节 format like '筛选/导入期V1（D-7~D-1）'."""
    s = norm(v)
    # Special cases: keep the main label, not the parenthetical
    if "提前退出" in s:
        return "提前退出"
    if "计划外" in s:
        return "计划外访视"
    if "筛选" in s:
        # Extract V{n} portion: "筛选/导入期V1（D-7~D-1）" → "V1"
        m = re.search(r"V(\d+)", s)
        if m:
            return f"筛选V{m.group(1)}"
        return "筛选"
    # Extract parenthetical content (e.g. "D29±1d" from "双盲治疗期V5（D29±1d）")
    m = re.search(r"（([^）]+)）", s)
    if m:
        return m.group(1)
    s = s.replace("双盲治疗期-", "").replace("开放治疗期-", "")
    # Extract V{n} from remaining
    m = re.search(r"V(\d+)", s)
    if m:
        return m.group(0)
    if len(s) > 20:
        return s[:20] + "..."
    return s


def chip_list(items, empty_text, field="term"):
    """Generate HTML chips for AE/MH items."""
    if not items:
        return f'<span class="empty">{e(empty_text)}</span>'
    chips = []
    for obj in items:
        term = obj.get(field, "")
        extra = obj.get("severity") or obj.get("relationship") or ""
        if extra:
            chips.append(f'<span class="chip">{e(term)} <small>({e(extra)})</small></span>')
        else:
            chips.append(f'<span class="chip">{e(term)}</span>')
    return "".join(chips)


def visit_label(p):
    """Build visit label: compact visit name + V{n} sub-label.
    Only shows V{n} when extracted from visit name AND not already in compacted name."""
    v = compact_visit(p.get("visit", ""))
    vp = p.get("visit_point", "")
    # Show V{n} only when it exists AND is not already part of the compacted name
    if vp and vp not in v:
        return f"{v}<br><small>{e(vp)}</small>"
    return v

def item_table(item):
    """Generate the data table for a single subject-test item."""
    visit_rows = item.get("all_visits", [])
    if not visit_rows:
        visit_rows = item.get("post", [])

    rows_html = []
    for p in visit_rows:
        val_cls = ""
        if p.get("direction") == "高":
            val_cls = "v-hi"
        elif p.get("direction") == "低":
            val_cls = "v-lo"

        row_cls = ""
        if p.get("phase") in ("baseline", "screening"):
            row_cls = "baseline-row"

        cs_raw = p.get("cs") or "正常"
        if "无临床意义" in cs_raw or "NCS" in norm(cs_raw):
            cs_html = '<span class="ncs">NCS</span>'
        elif "有临床意义" in cs_raw or norm(cs_raw).strip().upper() == "CS":
            cs_html = '<span class="cs">CS</span>'
        else:
            cs_html = e(cs_raw)

        pct = "-"
        if p.get("pct_change") is not None:
            pct = f"{p['pct_change']:+.1f}%"

        grade_html = "-"
        if p.get("grade"):
            grade_html = f'<span class="ctcae-badge">{e(str(p["grade"]) + "级")}</span>'

        desc = p.get("desc") or "-"
        ref_range = ""
        if p.get("lo") is not None or p.get("hi") is not None:
            ref_range = f"{fmt_num(p.get('lo'))} - {fmt_num(p.get('hi'))}"

        direction_arrow = ""
        if p.get("direction") == "高":
            direction_arrow = "↑"
        elif p.get("direction") == "低":
            direction_arrow = "↓"

        # Date format: "2025-08-12" → "08-12" (month-day only for compactness)
        date_str = p.get("date") or "-"
        if date_str and len(date_str) >= 10:
            date_str = date_str[5:10]  # Extract MM-DD

        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td>{visit_label(p)}</td>'
            f'<td class="date-cell">{e(date_str)}</td>'
            f'<td class="{val_cls}">{fmt_num(p.get("result"))}</td>'
            f'<td>{e(p.get("unit", ""))}</td>'
            f'<td>{e(ref_range)}</td>'
            f'<td>{direction_arrow}</td>'
            f'<td>{grade_html}</td>'
            f'<td>{cs_html}</td>'
            f'<td class="desc-cell">{e(desc)}</td>'
            f'<td>{pct}</td>'
            f'</tr>'
        )

    return (
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        '<th>访视</th><th>日期</th><th>结果</th><th>单位</th><th>参考范围</th><th>方向</th>'
        '<th>CTCAE</th><th>临床意义</th><th>临床意义解释</th><th>较基线变化</th>'
        '</tr></thead><tbody>' + "".join(rows_html) + "</tbody></table></div>"
    )


def item_card(item):
    """Generate HTML card for a single risk item."""
    rc = risk_class(item["risk"])
    badges = [
        f'<span class="badge badge-{risk_badge_class(item["risk"])}">{risk_label(item["risk"])}</span>'
    ]
    if item.get("new_ab_count"):
        badges.append(f'<span class="badge badge-warn">新发异常 x{item["new_ab_count"]}</span>')
    if item.get("ctcae_upgrade_count"):
        badges.append(f'<span class="badge badge-danger">CTCAE升级 x{item["ctcae_upgrade_count"]}</span>')
    if item.get("ae"):
        badges.append('<span class="badge badge-ok">有AE解释</span>')
    elif item.get("mh"):
        badges.append('<span class="badge badge-info">有MH解释</span>')
    else:
        badges.append('<span class="badge badge-danger">无AE/MH解释</span>')

    flags = []
    if item.get("clin_sig_count"):
        flags.append(f'<span class="flag flag-alert">CS/显著异常 x{item["clin_sig_count"]}</span>')
    if item.get("ncs_count"):
        flags.append(f'<span class="flag flag-warn">NCS x{item["ncs_count"]}</span>')
    if item.get("no_eval_count"):
        flags.append(f'<span class="flag flag-danger">未评价 x{item["no_eval_count"]}</span>')
    threshold_count = item.get("baseline_change_threshold_count", item.get("baseline_change_10pct_count"))
    threshold_pct = item.get("baseline_change_threshold_pct", 10)
    if threshold_count:
        flags.append(f'<span class="flag flag-info">基线变化≥{e(threshold_pct)}% x{threshold_count}</span>')
    if item.get("rule_note"):
        flags.append(f'<span class="flag flag-info">{e(item["rule_note"])}</span>')
    flags.append(f'<span class="flag flag-info">{e(item.get("explain_eval", ""))}</span>')

    # Build AE/MH/CM info boxes
    group_badge = ""
    group = item.get("group", "")
    if group:
        group_cls = "badge-info" if "试验" in group else "badge-neutral"
        group_badge = f'<span class="badge {group_cls}">{e(group)}</span>'

    return f"""
<div class="subject-card br-{rc}" id="{e(item['subj'] + '_' + item['test'])}" data-subj="{e(item['subj'])}" data-risk="{e(item['risk'])}" data-test="{e(item['test'])}">
  <div class="s-head"><span class="s-id">{e(item['subj'])} / {e(item['test'].split('（')[0])}</span>{group_badge}<div class="s-badges">{''.join(badges)}</div></div>
  <div class="flag-strip">{''.join(flags)}</div>
  <div class="info-row">
    <div class="info-box"><h4>相关AE</h4>{chip_list(item.get('ae'), '无相关AE')}</div>
    <div class="info-box"><h4>相关病史(MH)</h4>{chip_list(item.get('mh'), '无相关病史')}</div>
    <div class="info-box"><h4>基线信息</h4><span class="chip">{e(item.get('bl', {}).get('visit', ''))} / {fmt_num(item.get('bl', {}).get('result'))} {e(item.get('bl', {}).get('unit', ''))}</span></div>
    <div class="info-box"><h4>基线状态</h4><span class="chip">{e(item.get('bl_status', ''))}</span></div>
  </div>
  <div class="cs-note"><strong>判读：</strong>{e(item.get('explain_eval', ''))}</div>
  {item_table(item)}
</div>"""


def nav_id(site_idx, name):
    return re.sub(r"\W+", "_", f"{site_idx}_{name}")


def build_html(assessment_data, title="实验室检查异常AE漏报风险核查报告",
               project_name="", data_source=""):
    """Build the complete interactive HTML report."""
    results = assessment_data["results"]
    stats = assessment_data["stats"]
    ctcae_index = assessment_data.get("ctcae_index", {})
    test_names = assessment_data.get("test_names", [])
    test_sources = assessment_data.get("test_sources", {})

    # Group indicators by source type
    indicator_groups = defaultdict(list)
    for test in test_names:
        source = test_sources.get(test, "其他")
        cat_name = {
            "LB_HEM": "血常规/血生化",
            "LB_CHEM": "血生化",
            "LB_URI": "尿常规",
            "LB_OTHER": "其他实验室",
            "VS": "生命体征",
            "EG": "心电图",
            "HW": "体重/体格",
        }.get(source, "其他")

        # Check if indicator has data
        has_data = False
        for site_results in results.values():
            if test in site_results and site_results[test]:
                has_data = True
                break
        if has_data:
            indicator_groups[cat_name].append(test)

    site_names = sorted(results.keys())
    body_sites = []
    tabs = []

    for site_idx, site in enumerate(site_names):
        active = " active" if site_idx == 0 else ""
        tabs.append(f'<div class="site-tab{active}" onclick="switchSite(\'site{site_idx}\')">{e(site)}</div>')

        site_results = results.get(site, {})
        all_items = [it for items in site_results.values() for it in items]
        stat = Counter(it["risk"] for it in all_items)
        subjects = sorted(set(it["subj"] for it in all_items))
        subject_options = "".join(
            f'<option value="{e(s)}">{e(s)}</option>' for s in subjects
        )

        # Build navigation and sections
        nav_groups = []
        sections = []

        for group_name, group_tests in indicator_groups.items():
            links = []
            group_sections = []
            for test_name in group_tests:
                items = site_results.get(test_name, [])
                if not items:
                    continue
                iid = nav_id(site_idx, test_name)
                short_name = test_name.split("（")[0].split("(")[0].strip()
                links.append(
                    f'<button class="nav-link" id="navlink_{iid}" onclick="showIndicator(\'{site_idx}\',\'{iid}\')" '
                    f'title="{e(test_name)}">{e(short_name)} <span>({len(items)})</span></button>'
                )

                risk_blocks = []
                for r in ["high", "medium", "low", "info"]:
                    subset = [it for it in items if it["risk"] == r]
                    if not subset:
                        continue
                    if r == "high":
                        title = f"高风险（需重点核查）（{len(subset)}项）"
                    elif r == "medium":
                        title = f"关注（需补充说明/确认）（{len(subset)}项）"
                    elif r == "low":
                        title = f"低风险（已有合理解释）（{len(subset)}项）"
                    else:
                        title = f"提示（按项目规则仅供核对）（{len(subset)}项）"
                    risk_blocks.append(
                        f'<div class="risk-section h2-{risk_class(r)}"><h2>{title}</h2>'
                        f'{"".join(item_card(it) for it in subset)}</div>'
                    )

                counts = Counter(it["risk"] for it in items)
                group_sections.append(
                    f'<div class="indicator-section" id="ind_{iid}">'
                    f'<h4>{e(test_name)} | 共{len(items)}项（高{counts["high"]} / 中{counts["medium"]} / 低{counts["low"]} / 提示{counts["info"]}）</h4>'
                    f'{"".join(risk_blocks)}</div>'
                )

            if links:
                nav_groups.append(
                    f'<div class="nav-group"><span class="nav-group-label">{e(group_name)}</span>'
                    f'{"".join(links)}</div>'
                )
                sections.append(
                    f'<div class="indicator-group-title">{e(group_name)}</div>'
                    f'{"".join(group_sections)}'
                )

        total = sum(stat.values())
        body_sites.append(f"""
<div class="site-content{active}" id="site{site_idx}"><div class="container">
<div class="summary-grid">
  <div class="stat-card c-red"><div class="num">{stat['high']}</div><div class="label">高风险</div></div>
  <div class="stat-card c-orange"><div class="num">{stat['medium']}</div><div class="label">关注项</div></div>
  <div class="stat-card c-blue"><div class="num">{stat['low']}</div><div class="label">低风险</div></div>
  <div class="stat-card c-info"><div class="num">{stat['info']}</div><div class="label">提示项</div></div>
  <div class="stat-card"><div class="num">{len(subjects)}</div><div class="label">异常受试者</div></div>
  <div class="stat-card"><div class="num">{total}</div><div class="label">总项次</div></div>
</div>
<div class="legend">
  <b>判定原则：</b>基线正常/异常+基线后出现异常或CTCAE升级判定为风险项。临床意义解释已关联AE/MH且可解释异常者列为低风险；关联但解释不足者列为关注；无解释/未评价异常列为高风险。
</div>
<div class="filter-panel" id="filter{site_idx}">
  <div class="filter-title">快速筛选</div>
  <label>受试者
    <select id="subjectFilter{site_idx}" onchange="applyQuickFilter('{site_idx}')">
      <option value="">全部受试者</option>
      {subject_options}
    </select>
  </label>
  <button class="filter-btn" data-mode="high" onclick="setFilterMode('{site_idx}','high')">高风险</button>
  <button class="filter-btn" data-mode="medium" onclick="setFilterMode('{site_idx}','medium')">关注</button>
  <button class="filter-btn" data-mode="low" onclick="setFilterMode('{site_idx}','low')">低风险</button>
  <button class="filter-btn" data-mode="info" onclick="setFilterMode('{site_idx}','info')">提示</button>
  <button class="filter-btn" data-mode="subject" onclick="setFilterMode('{site_idx}','subject')">受试者全部异常</button>
  <button class="filter-btn ghost" onclick="clearQuickFilter('{site_idx}')">清除筛选</button>
  <span class="filter-status" id="filterStatus{site_idx}"></span>
</div>
<div class="quick-results" id="quickResults{site_idx}" style="display:none"></div>
<div class="indicator-nav" id="nav{site_idx}"><h3>指标导航（点击筛选）</h3>{"".join(nav_groups)}</div>
{"".join(sections)}
</div></div>""")

    # Extract CTCAE version info
    ctcae_version = "v5.0"
    ctcae_info = ""
    # Count tests with/without CTCAE
    tests_with = sum(1 for v in ctcae_index.values() if v.get("has_grades"))
    tests_without = len(ctcae_index) - tests_with

    generated = assessment_data.get("generated", datetime.now().strftime("%Y-%m-%d %H:%M"))

    n_sites = len(site_names)
    js_site_count = n_sites

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f6f8;color:#1a1a2e;line-height:1.55}}
.header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:20px 32px}}
.header h1{{font-size:20px;font-weight:700}}
.header p{{opacity:.78;font-size:12px;margin-top:3px}}
.site-tabs{{display:flex;background:white;border-bottom:2px solid #e0e0e0;position:sticky;top:0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.05);overflow-x:auto}}
.site-tab{{padding:11px 22px;cursor:pointer;font-weight:600;font-size:12px;color:#7f8c8d;border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap}}
.site-tab:hover,.site-tab.active{{color:#FF9900;border-bottom-color:#FF9900}}
.site-content{{display:none}}
.site-content.active{{display:block}}
.container{{max-width:1600px;margin:0 auto;padding:14px 18px}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:14px}}
.stat-card{{background:white;border-radius:6px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.05);text-align:center}}
.stat-card .num{{font-size:24px;font-weight:800}}
.stat-card .label{{font-size:10px;color:#7f8c8d;margin-top:2px}}
.c-red .num{{color:#e74c3c}}
.c-orange .num{{color:#FF9900}}
.c-blue .num{{color:#2471a3}}
.c-info .num{{color:#5f7f99}}
.legend,.indicator-nav,.filter-panel,.quick-results{{background:white;border-radius:6px;padding:10px 14px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.05);font-size:11.5px;border-left:3px solid #FF9900}}
.legend b{{color:#e74c3c}}
.indicator-nav h3{{font-size:12px;margin-bottom:6px;color:#2c3e50}}
.filter-panel{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-left-color:#2471a3}}
.filter-title{{font-weight:800;color:#16213e;margin-right:4px}}
.filter-panel label{{font-size:11px;color:#5d6d7e;font-weight:700}}
.filter-panel select{{margin-left:5px;padding:5px 8px;border:1px solid #d5dbdb;border-radius:4px;background:#fff;color:#1a1a2e;font-weight:700}}
.filter-btn{{padding:5px 11px;border-radius:4px;border:1px solid #d5dbdb;background:#f4f6f8;color:#5d6d7e;cursor:pointer;font-size:11px;font-weight:700}}
.filter-btn:hover,.filter-btn.active{{background:#FF9900;color:white;border-color:#FF9900}}
.filter-btn.jak{{border-color:#e74c3c;color:#e74c3c}}
.filter-btn.ghost{{background:transparent;color:#7f8c8d;border:1px solid #d5dbdb}}
.filter-status{{margin-left:8px;color:#FF9900;font-weight:700;font-size:11px}}
.nav-group{{margin-bottom:4px}}
.nav-group-label{{display:inline-block;background:#1a1a2e;color:white;padding:3px 8px;border-radius:3px;font-size:10px;font-weight:700;margin:4px 6px 4px 0}}
.nav-link{{display:inline-block;padding:4px 10px;margin:2px 4px 2px 0;border-radius:3px;border:1px solid #e0e0e0;cursor:pointer;font-size:11px;background:#f4f6f8;color:#2c3e50}}
.nav-link:hover,.nav-link.active{{background:#FF9900;color:white;border-color:#FF9900}}
.nav-link span{{color:#7f8c8d;font-size:10px}}
.indicator-group-title{{font-size:13px;font-weight:800;color:#16213e;margin:14px 0 4px;padding:4px 0;border-bottom:2px solid #FF9900}}
.indicator-section{{display:none}}
.indicator-section.active{{display:block}}
.indicator-section h4{{font-size:13px;font-weight:700;color:#2c3e50;margin:6px 0;padding:4px 10px;background:white;border-radius:4px}}
.risk-section{{margin-bottom:8px}}
.risk-section h2{{font-size:11px;font-weight:700;padding:6px 10px;border-radius:4px;margin-bottom:6px}}
.h2-red h2{{background:#ffeaea;color:#c0392b;border-left:3px solid #e74c3c}}
.h2-yellow h2{{background:#fff8e1;color:#e65100;border-left:3px solid #FF9900}}
.h2-green h2{{background:#e8f5e9;color:#2e7d32;border-left:3px solid #27ae60}}
.h2-blue h2{{background:#eef3f7;color:#496b85;border-left:3px solid #7b9bb4}}
.subject-card{{background:white;border-radius:6px;padding:10px 14px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,.05);border-left:3px solid #ccc}}
.br-red{{border-left-color:#e74c3c}}
.br-yellow{{border-left-color:#FF9900}}
.br-green{{border-left-color:#27ae60}}
.br-blue{{border-left-color:#7b9bb4}}
.s-head{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}}
.s-id{{font-weight:800;font-size:14px;color:#16213e}}
.s-badges{{display:flex;gap:4px;flex-wrap:wrap}}
.badge{{display:inline-block;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:700}}
.badge-danger{{background:#ffeaea;color:#c0392b}}
.badge-warn{{background:#fff8e1;color:#e65100}}
.badge-ok{{background:#e8f5e9;color:#2e7d32}}
.badge-info{{background:#e3f2fd;color:#1565c0}}
.badge-neutral{{background:#f5f5f5;color:#616161}}
.badge-jak{{background:#fce4ec;color:#c62828}}
.flag-strip{{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0}}
.flag{{display:inline-block;padding:2px 6px;border-radius:2px;font-size:10px;font-weight:600}}
.flag-alert{{background:#ffebee;color:#c62828}}
.flag-warn{{background:#fff3e0;color:#e65100}}
.flag-danger{{background:#ffcdd2;color:#b71c1c}}
.flag-info{{background:#e8eaf6;color:#283593}}
.flag-jak{{background:#fce4ec;color:#880e4f}}
.info-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px;margin:6px 0}}
.info-box{{background:#f8f9fa;border-radius:4px;padding:6px 8px}}
.info-box h4{{font-size:10px;color:#7f8c8d;margin-bottom:2px}}
.chip{{display:inline-block;background:#e8eaf6;padding:2px 6px;border-radius:3px;font-size:10px;margin:1px 2px 1px 0;color:#283593}}
.empty{{color:#bdc3c7;font-style:italic;font-size:10px}}
.cs-note{{font-size:10px;padding:4px 8px;background:#f4f6f8;border-radius:4px;margin:4px 0;color:#5d6d7e}}
.cs-note strong{{color:#2c3e50}}
.cs-note.muted{{color:#95a5a6}}
.tbl-wrap{{overflow-x:auto;margin-top:4px}}
.tbl{{width:100%;border-collapse:collapse;font-size:10px}}
.tbl th{{background:#1a1a2e;color:white;padding:5px 6px;text-align:left;white-space:nowrap;font-weight:600}}
.tbl td{{padding:4px 6px;border-bottom:1px solid #f0f0f0}}
.tbl tr:hover{{background:#f4f6f8}}
.baseline-row{{background:#e3f2fd}}
.v-hi{{color:#e74c3c;font-weight:700}}
.v-lo{{color:#2471a3;font-weight:700}}
.cs,.ncs,.ctcae-badge{{display:inline-block;padding:1px 5px;border-radius:2px;font-size:9px;font-weight:700}}
.cs{{background:#ffebee;color:#c62828}}
.ncs{{background:#e3f2fd;color:#1565c0}}
.ctcae-badge{{background:#f3e5f5;color:#6a1b9a}}
.desc-cell{{max-width:200px;font-size:9px;color:#5d6d7e;word-break:break-word}}
.date-cell{{font-size:9px;color:#7f8c8d;white-space:nowrap}}
.cfdi-cell{{max-width:300px;font-size:9px;color:#5d6d7e;word-break:break-word}}
.footer{{text-align:center;padding:20px;color:#bdc3c7;font-size:11px;border-top:1px solid #e0e0e0;margin-top:20px}}
</style>
</head>
<body>
<div class="header">
  <h1>{e(title)}</h1>
  <p>筛选/基线至基线后异常变化 | CTCAE {e(ctcae_version)} | 非CTCAE指标阈值≥{e(str(assessment_data.get('non_ctcae_threshold', 20)))}%</p>
  {f'<p>{e(project_name)}</p>' if project_name else ''}
  <p>CTCAE覆盖指标: {tests_with} 项 | 无CTCAE分级指标: {tests_without} 项</p>
  <p>生成日期：{e(generated)} | 数据来源：{e(data_source)}</p>
</div>
<div class="site-tabs">{"".join(tabs)}</div>
{"".join(body_sites)}
<div class="footer">AE漏报风险核查报告 — 基于Data Listing自动生成 | CTCAE {ctcae_version}</div>
<script>
function switchSite(id){{document.querySelectorAll('.site-tab').forEach((t,i)=>t.classList.toggle('active','site'+i===id));document.querySelectorAll('.site-content').forEach(c=>c.classList.toggle('active',c.id===id));}}
function showIndicator(siteIdx,iid){{document.querySelectorAll('#site'+siteIdx+' .indicator-section').forEach(s=>s.classList.remove('active'));document.querySelectorAll('#nav'+siteIdx+' .nav-link').forEach(b=>b.classList.remove('active'));var sec=document.getElementById('ind_'+iid);if(sec)sec.classList.add('active');var btn=document.getElementById('navlink_'+iid);if(btn)btn.classList.add('active');if(sec)sec.scrollIntoView({{behavior:'smooth',block:'start'}});}}
var filterModes={{}};
function setFilterMode(siteIdx,mode){{filterModes[siteIdx]=mode;document.querySelectorAll('#filter'+siteIdx+' .filter-btn').forEach(function(b){{b.classList.toggle('active',b.dataset.mode===mode);}});applyQuickFilter(siteIdx);}}
function clearQuickFilter(siteIdx){{filterModes[siteIdx]='';var sel=document.getElementById('subjectFilter'+siteIdx);if(sel)sel.value='';document.querySelectorAll('#filter'+siteIdx+' .filter-btn').forEach(function(b){{b.classList.remove('active');}});var out=document.getElementById('quickResults'+siteIdx);if(out){{out.innerHTML='';out.style.display='none';}}var status=document.getElementById('filterStatus'+siteIdx);if(status)status.textContent='';}}
function applyQuickFilter(siteIdx){{var mode=filterModes[siteIdx]||'';var subj=(document.getElementById('subjectFilter'+siteIdx)||{{value:''}}).value;var cards=[].slice.call(document.querySelectorAll('#site'+siteIdx+' .indicator-section .subject-card'));var matches=cards.filter(function(card){{if(subj&&card.dataset.subj!==subj)return false;if(mode==='high'&&card.dataset.risk!=='high')return false;if(mode==='medium'&&card.dataset.risk!=='medium')return false;if(mode==='low'&&card.dataset.risk!=='low')return false;if(mode==='info'&&card.dataset.risk!=='info')return false;if(mode==='subject'&&!subj)return false;return true;}});var out=document.getElementById('quickResults'+siteIdx);var status=document.getElementById('filterStatus'+siteIdx);document.querySelectorAll('#filter'+siteIdx+' .filter-btn').forEach(function(b){{b.classList.toggle('active',b.dataset.mode===mode);}});if(!out)return;if(!mode||(!subj&&mode==='subject')){{out.innerHTML='';out.style.display='none';if(status)status.textContent='';return;}}var title=(subj?subj+' / ':'')+(mode==='high'?'高风险':mode==='medium'?'关注':mode==='low'?'低风险':mode==='info'?'提示':'全部异常');out.innerHTML='<h3>'+title+'（'+matches.length+'项）</h3>';if(matches.length===0){{out.innerHTML+='<div class="cs-note muted">未检索到匹配项。</div>';}}else{{matches.forEach(function(card){{var clone=card.cloneNode(true);clone.removeAttribute('id');out.appendChild(clone);}});}}out.style.display='block';if(status)status.textContent='当前显示 '+matches.length+' 项';out.scrollIntoView({{behavior:'smooth',block:'start'}});}}
document.addEventListener('DOMContentLoaded',function(){{for(let i=0;i<{js_site_count};i++){{let first=document.querySelector('#site'+i+' .indicator-section');if(first){{first.classList.add('active');let id=first.id.replace('ind_','');let btn=document.getElementById('navlink_'+id);if(btn)btn.classList.add('active');}}}}}});
</script>
</body></html>"""


def generate_report(assessment_path, output_path, title="实验室检查异常AE漏报风险核查报告",
                    project_name="", data_source=""):
    """Generate the HTML report from assessment JSON."""
    assessment = json.loads(Path(assessment_path).read_text(encoding="utf-8"))
    html_content = build_html(assessment, title, project_name, data_source)
    Path(output_path).write_text(html_content, encoding="utf-8")
    print(f"Report saved to {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_report.py <assessment.json> <output.html> [title] [project_name] [data_source]")
        sys.exit(1)

    generate_report(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else "实验室检查异常AE漏报风险核查报告",
        sys.argv[4] if len(sys.argv) > 4 else "",
        sys.argv[5] if len(sys.argv) > 5 else "",
    )
