"""JSON output and readable ranked report; CSV is already available elsewhere."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Opportunity


def build_report(candidates: list[Opportunity], provider: str, researched_count: int | None = None,
                 seeds: list[str] | None = None, failures: list[dict] | None = None) -> dict:
    return {"service": "google_play", "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider, "demo_data": provider == "json_fixture",
            "researched_count": researched_count if researched_count is not None else len(candidates),
            "seed_count": len(seeds or []), "seeds": seeds or [],
            "provider_failures": failures or [], "candidates": [c.as_dict() for c in candidates]}


def write_report(report: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "latest_google_play_report.json"
    rendered = json.dumps(report, indent=2)
    path.write_text(rendered, encoding="utf-8")
    stamp = report["generated_at"].replace(":", "-").replace("+", "_")
    (output_dir / f"google_play_report_{stamp}.json").write_text(rendered, encoding="utf-8")
    return path


def terminal_report(report: dict) -> str:
    lines = ["=" * 60, "GOOGLE PLAY MARKET INTELLIGENCE", "=" * 60, ""]
    lines.append(f"Provider: {report['provider']} | Researched: {report.get('researched_count', 0)}"
                 f" | Demo data: {report.get('demo_data', False)}")
    lines.append("")
    if not report["candidates"]:
        lines.append("No candidates met the configured quality and confidence gates.")
    for index, c in enumerate(report["candidates"], 1):
        lines.extend([
            f"{index}. {c['niche']}",
            f"Score: {c['google_play_score']:.1f} | Confidence: {c['confidence_score']:.1f}",
            f"Pattern: {c['pattern']}",
            f"Demand: {c['demand_score']:.1f} | Competition: {c['competition_strength_score']:.1f}",
            f"Dissatisfaction: {c['dissatisfaction_score']:.1f} | Build complexity: {c['build_complexity_score']:.1f}",
            f"Recommendation: {c['recommendation']}",
            "-" * 60,
        ])
    return "\n".join(lines)
