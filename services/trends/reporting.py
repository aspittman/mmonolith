"""Structured JSON and compact human-readable trend intelligence reports."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import TrendSignal


def build_report(signals: list[TrendSignal], providers: list[str], cadence: str,
                 transitions: list[dict] | None = None, failures: list[dict] | None = None) -> dict:
    return {"service": "trends", "generated_at": datetime.now(timezone.utc).isoformat(),
            "cadence": cadence, "providers": providers, "signals": [s.as_dict() for s in signals],
            "transitions": transitions or [], "provider_failures": failures or []}


def write_report(report: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "latest_trends_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _band(value: float) -> str:
    if value >= 80: return "VERY HIGH"
    if value >= 60: return "HIGH"
    if value >= 40: return "MEDIUM"
    if value >= 20: return "LOW"
    return "VERY LOW"


def terminal_report(report: dict) -> str:
    lines = ["=" * 60, "MMONOLITH TREND INTELLIGENCE", "=" * 60, ""]
    if not report["signals"]:
        lines.append("No signals met the configured attention, commercial, and confidence gates.")
    for index, signal in enumerate(report["signals"], 1):
        h = signal["metrics_by_horizon"]
        lines.extend([
            f"{index}. {signal['topic']}", "", f"Stage: {signal['stage']}",
            f"Attention Score: {signal['attention_score']:.1f}",
            f"Commercial Trend Score: {signal['commercial_trend_score']:.1f}",
            f"Confidence: {signal['trend_confidence_score']:.1f}",
            f"Short / Medium / Long Velocity: {h['short']['velocity']:+.1f} / {h['medium']['velocity']:+.1f} / {h['long']['velocity']:+.1f}",
            f"Acceleration: {_band(max(0, signal['attention_acceleration']))}",
            f"Persistence: {_band(signal['persistence_score'])}",
            f"Commercial Intent: {_band(signal['commercial_intent_score'])}",
            f"Geographic Spread: {_band(signal['geographic_spread_score'])}",
            f"Competition: {_band(signal['competition_score'])}",
            f"Event Spike Probability: {_band(signal['event_spike_probability'])}",
            f"Second-Order Search Shift: {signal['second_order_shift']}",
        ])
        queries = [query["query"] for query in signal["related_queries"][:5]]
        if queries:
            lines.append("Related searches: " + ", ".join(queries))
        lines.extend([f"Recommendation: {signal['recommendation']}", f"Reason: {signal['reason']}",
                      f"Suggested routing: {', '.join(signal['routes']) or 'none'}", "-" * 60])
    if report.get("transitions"):
        lines.extend(["", "TREND TRANSITIONS"])
        for transition in report["transitions"]:
            lines.append(f"{transition['topic']}: {transition['previous']} → {transition['current']}")
    if report.get("provider_failures"):
        lines.append(f"Provider failures isolated: {len(report['provider_failures'])}")
    return "\n".join(lines)
