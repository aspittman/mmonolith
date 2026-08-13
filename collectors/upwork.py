"""Compliant Upwork collector based on a user-provided CSV export."""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from collectors.base import BaseCollector, Observation


def _first(row: dict[str, str], *names: str) -> str:
    lowered = {str(k).strip().lower(): (v or "").strip() for k, v in row.items()}
    return next((lowered[n.lower()] for n in names if lowered.get(n.lower())), "")


def _money(value: str) -> float | None:
    match = re.search(r"[\d,]+(?:\.\d+)?", value or "")
    return float(match.group(0).replace(",", "")) if match else None


def _date(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).isoformat()
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return datetime.now(timezone.utc).isoformat()


class UpworkCSVCollector(BaseCollector):
    name = "upwork"

    def __init__(self, path: Path):
        self.path = path

    def collect(self) -> list[Observation]:
        if not self.path.exists():
            return []
        observations: list[Observation] = []
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                title = _first(row, "title", "job title")
                if not title:
                    continue
                url = _first(row, "url", "job url", "link")
                raw_budget = _first(row, "budget", "fixed price")
                budget_min = _money(_first(row, "budget_min", "min budget", "hourly min"))
                budget_max = _money(_first(row, "budget_max", "max budget", "hourly max"))
                if budget_min is None and budget_max is None:
                    budget_min = budget_max = _money(raw_budget)
                budget_type = _first(row, "budget_type", "job type").lower()
                if "hour" in budget_type:
                    budget_type = "hourly"
                elif "fixed" in budget_type or raw_budget:
                    budget_type = "fixed"
                else:
                    budget_type = "unknown"
                source_id = _first(row, "source_id", "job id", "id") or Observation.stable_id(self.name, title, url)
                observations.append(Observation(
                    source=self.name, source_id=source_id, title=title,
                    description=_first(row, "description", "job description"), url=url,
                    posted_at=_date(_first(row, "posted_at", "posted", "date")),
                    budget_min=budget_min, budget_max=budget_max, budget_type=budget_type,
                    location=_first(row, "location", "client location") or None,
                ))
        return observations

