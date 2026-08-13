"""Write machine-readable reports and render the terminal summary."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def write_reports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest_market_report.json"
    csv_path = output_dir / "latest_market_report.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = ["category", "requests_7d", "requests_previous_7d", "requests_30d",
              "weekly_growth_pct", "monthly_growth_pct", "average_budget", "median_budget",
              "demand_score", "opportunity_score", "confidence", "source_count"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for service in report["services"]:
            writer.writerow({field: service.get(field) for field in fields})
    return json_path, csv_path


def terminal_summary(report: dict) -> str:
    lines = ["MARKET DEMAND REPORT", ""]
    if not report["services"]:
        lines.append("No request observations are available for the selected periods.")
    for number, service in enumerate(report["services"][:10], 1):
        label = service["category"].replace("_", " ").title()
        trend = "unknown" if service["weekly_growth_pct"] is None else f"{service['weekly_growth_pct']:+.1f}%"
        budget = "unknown" if service["median_budget"] is None else f"${service['median_budget']:,.0f}"
        lines.extend([f"{number}. {label}", f"   Demand: {service['demand_score']:.1f}/100",
                      f"   Trend: {trend}", f"   Median Budget: {budget}",
                      f"   Confidence: {service['confidence']:.1f}/100", ""])
    growing = sorted(report["technologies"],
                     key=lambda x: (x["weekly_growth_pct"] is not None, x["weekly_growth_pct"] or -999,
                                    x["mentions_7d"]), reverse=True)
    lines.append("FASTEST GROWING TECHNOLOGIES")
    if not growing:
        lines.append("No technology mentions are available yet.")
    for number, tech in enumerate(growing[:5], 1):
        trend = "unknown" if tech["weekly_growth_pct"] is None else f"{tech['weekly_growth_pct']:+.1f}%"
        lines.append(f"{number}. {tech['technology']} ({trend}, {tech['mentions_7d']} mentions)")
    return "\n".join(lines)

