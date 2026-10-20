#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main orchestration script for AE Risk Assessment Skill.
Usage: python main.py <listing.xlsx> <ctcae.pdf> [options]
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from parse_listing import parse_listing
from parse_ctcae import parse_ctcae_pdf, build_ctcae_index, CTCAE_V5_MAPPING
from assess_risk import (
    apply_project_rules,
    assess_risk,
    load_project_rules,
    run_assessment,
)
from generate_report import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="临床试验实验室检查异常AE漏报风险核查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("listing", help="Data Listing Excel文件路径 (.xlsx)")
    parser.add_argument("--ctcae", "-c", help="CTCAE分级PDF文件路径 (可选，默认使用内置v5.0映射)")
    parser.add_argument("--ctcae-version", default="5.0", help="CTCAE版本号 (默认5.0)")
    parser.add_argument("--group-table", "-g", help="受试者分组表Excel文件路径 (可选)")
    parser.add_argument("--threshold", "-t", type=int, default=None,
                        help="非CTCAE指标的异常判定阈值%%；未指定时使用项目规则或默认20")
    parser.add_argument("--rules", help="项目规则JSON文件（可选，见references/project-rules.md）")
    parser.add_argument("--title", default="实验室检查异常AE漏报风险核查报告",
                        help="报告标题")
    parser.add_argument("--project", default="", help="项目名称")
    parser.add_argument("--output", "-o", default="output", help="输出目录 (默认./output)")
    parser.add_argument("--prev-report", help="既往HTML报告路径 (用于增量构建)")
    parser.add_argument("--baseline-rule", default="auto",
                        choices=["auto", "d1", "screening", "last-screening-or-d1"],
                        help="基线定义规则 (默认auto)")
    args = parser.parse_args()

    # Create output directory
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AE漏报风险核查 — 临床试验实验室检查异常评估")
    print("=" * 60)

    # Step 1: Parse Data Listing
    print("\n[1/4] 解析Data Listing...")
    listing_path = Path(args.listing)
    if not listing_path.exists():
        print(f"错误：找不到文件 {args.listing}")
        sys.exit(1)

    parsed_data = parse_listing(str(listing_path))
    project_rules = load_project_rules(args.rules)

    # Parse the group table before applying an explicit population scope.
    groups = {}
    if args.group_table:
        from parse_listing import parse_group_table
        groups = parse_group_table(args.group_table)
        print(f"  ✓ 分组信息: {len(groups)} 受试者")

    parsed_data = apply_project_rules(parsed_data, project_rules, groups)
    effective_threshold = args.threshold
    if effective_threshold is None:
        effective_threshold = project_rules.get("non_ctcae_threshold_pct", 20)
    try:
        effective_threshold = float(effective_threshold)
    except (TypeError, ValueError):
        effective_threshold = 20.0
    parsed_path = out_dir / "parsed_data.json"
    parsed_path.write_text(
        json.dumps(parsed_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"  ✓ 解析完成: {parsed_data['stats']}")
    for w in parsed_data.get("warnings", []):
        print(f"  ⚠ {w}")

    # Step 2: Parse CTCAE
    print(f"\n[2/4] 加载CTCAE {args.ctcae_version}分级标准...")
    if args.ctcae:
        ctcae = parse_ctcae_pdf(args.ctcae, args.ctcae_version)
        ctcae_mapping = ctcae.get("mapping", CTCAE_V5_MAPPING)
    else:
        ctcae_mapping = CTCAE_V5_MAPPING

    ctcae_index = build_ctcae_index(parsed_data["test_names"], ctcae_mapping)
    tests_with = sum(1 for v in ctcae_index.values() if v.get("has_grades"))
    tests_without = sum(1 for v in ctcae_index.values() if not v.get("has_grades"))
    tests_unknown = sum(1 for v in ctcae_index.values() if v.get("unknown"))
    print(f"  ✓ CTCAE覆盖: {tests_with} 项 | 无CTCAE分级: {tests_without} 项 | 未确认: {tests_unknown} 项")

    # Step 3: Risk Assessment
    print(f"\n[3/4] 执行风险分析 (非CTCAE指标阈值: {effective_threshold:g}%)...")
    results = assess_risk(
        parsed_data, ctcae_index, effective_threshold, groups, project_rules
    )

    # Build output dict
    assessment = {
        "results": results,
        "stats": {},
        "ctcae_index": ctcae_index,
        "non_ctcae_threshold": effective_threshold,
        "project_rules": project_rules,
        "rules_path": str(Path(args.rules).resolve()) if args.rules else "",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "test_names": parsed_data["test_names"],
        "test_sources": parsed_data.get("test_sources", {}),
    }
    for center, tests in results.items():
        all_items = [it for items in tests.values() for it in items]
        assessment["stats"][center] = {
            "high": sum(1 for it in all_items if it["risk"] == "high"),
            "medium": sum(1 for it in all_items if it["risk"] == "medium"),
            "low": sum(1 for it in all_items if it["risk"] == "low"),
            "info": sum(1 for it in all_items if it["risk"] == "info"),
            "subjects": len(set(it["subj"] for it in all_items)),
            "total": len(all_items),
        }

    assessment_path = out_dir / "assessment.json"
    assessment_path.write_text(
        json.dumps(assessment, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    total = {"high": 0, "medium": 0, "low": 0, "total": 0}
    for s in assessment["stats"].values():
        for k in ("high", "medium", "low", "total"):
            total[k] += s.get(k, 0)
    print(f"  ✓ 风险分析完成: 总{total['total']}项 (高{total['high']} / 中{total['medium']} / 低{total['low']})")

    # Step 4: Generate HTML Report
    print(f"\n[4/4] 生成交互式HTML报告...")
    report_path = out_dir / f"AE漏报风险核查报告_{args.project or 'project'}_{datetime.now().strftime('%Y%m%d')}.html"
    generate_report(
        str(assessment_path),
        str(report_path),
        args.title,
        args.project,
        str(listing_path.name),
    )
    print(f"  ✓ HTML报告: {report_path}")
    print(f"\n{'=' * 60}")
    print("全部完成。输出文件:")
    print(f"  解析数据: {parsed_path}")
    print(f"  分析结果: {assessment_path}")
    print(f"  HTML报告: {report_path}")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
