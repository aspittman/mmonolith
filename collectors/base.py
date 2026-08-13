"""Collector contract and normalized observation model."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Observation:
    source: str
    source_id: str
    title: str
    description: str = ""
    url: str = ""
    posted_at: str = field(default_factory=utc_now_iso)
    budget_min: float | None = None
    budget_max: float | None = None
    budget_type: str = "unknown"
    service_category: str = "OTHER"
    technologies: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    location: str | None = None
    # request = expressed buyer/problem demand; search_interest = Google Trends signal.
    observation_type: str = "request"
    source_metric: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def stable_id(source: str, title: str, url: str = "") -> str:
        text = f"{source}|{url}|{title.strip().lower()}"
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


class BaseCollector(ABC):
    name: str

    @abstractmethod
    def collect(self) -> list[Observation]:
        """Return normalized observations; do not write directly to storage."""

