"""Centralized strategic thresholds for the trends service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import config as root_config


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass
class TrendsConfig:
    enabled: bool = False
    watch_mode_enabled: bool = True
    discovery_mode_enabled: bool = True
    countries: list[str] = field(default_factory=lambda: ["US"])
    regions: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    watch_topics: list[str] = field(default_factory=lambda: [
        "microgreens", "domain investing", "website optimization", "AI receptionist",
        "contractor software", "mobile detailing software", "Google Play development",
    ])
    short_window: int = 30
    medium_window: int = 180
    long_window: int = 1825
    minimum_attention_score: float = 35
    minimum_commercial_trend_score: float = 40
    minimum_confidence: float = 25
    maximum_event_spike_probability: float = 85
    max_discovery_topics: int = 50
    max_related_queries: int = 20
    max_expansion_depth: int = 2
    max_children_per_topic: int = 8
    minimum_child_signal: float = 30
    route_to_services: bool = True
    historical_tracking: bool = True
    route_score_threshold: float = 70
    route_confidence_threshold: float = 55
    cache_ttl_hours: int = 24
    provider_timeout_seconds: int = 20
    provider_retries: int = 2
    fixture_path: Path = root_config.BASE_DIR / "data/raw/trends.example.json"
    output_dir: Path = root_config.BASE_DIR / "data/processed/trends"

    @classmethod
    def from_env(cls) -> "TrendsConfig":
        defaults = cls()
        return cls(
            enabled=_bool("TRENDS_ENABLED", False),
            watch_mode_enabled=_bool("TRENDS_WATCH_MODE_ENABLED", True),
            discovery_mode_enabled=_bool("TRENDS_DISCOVERY_MODE_ENABLED", True),
            countries=_list("TRENDS_COUNTRIES", "US"),
            regions=_list("TRENDS_REGIONS", ""),
            categories=_list("TRENDS_CATEGORIES", ""),
            watch_topics=_list("TRENDS_WATCH_TOPICS", ",".join(defaults.watch_topics)),
            short_window=int(os.getenv("TRENDS_SHORT_WINDOW", "30")),
            medium_window=int(os.getenv("TRENDS_MEDIUM_WINDOW", "180")),
            long_window=int(os.getenv("TRENDS_LONG_WINDOW", "1825")),
            minimum_attention_score=float(os.getenv("TRENDS_MIN_ATTENTION_SCORE", "35")),
            minimum_commercial_trend_score=float(os.getenv("TRENDS_MIN_COMMERCIAL_SCORE", "40")),
            minimum_confidence=float(os.getenv("TRENDS_MIN_CONFIDENCE", "25")),
            maximum_event_spike_probability=float(os.getenv("TRENDS_MAX_EVENT_SPIKE", "85")),
            max_discovery_topics=int(os.getenv("TRENDS_MAX_DISCOVERY_TOPICS", "50")),
            max_related_queries=int(os.getenv("TRENDS_MAX_RELATED_QUERIES", "20")),
            max_expansion_depth=int(os.getenv("TRENDS_MAX_EXPANSION_DEPTH", "2")),
            max_children_per_topic=int(os.getenv("TRENDS_MAX_CHILDREN", "8")),
            minimum_child_signal=float(os.getenv("TRENDS_MIN_CHILD_SIGNAL", "30")),
            route_to_services=_bool("TRENDS_ROUTE_TO_SERVICES", True),
            historical_tracking=_bool("TRENDS_HISTORICAL_TRACKING", True),
            route_score_threshold=float(os.getenv("TRENDS_ROUTE_SCORE", "70")),
            route_confidence_threshold=float(os.getenv("TRENDS_ROUTE_CONFIDENCE", "55")),
            cache_ttl_hours=int(os.getenv("TRENDS_CACHE_TTL_HOURS", "24")),
            provider_timeout_seconds=int(os.getenv("TRENDS_PROVIDER_TIMEOUT", "20")),
            provider_retries=int(os.getenv("TRENDS_PROVIDER_RETRIES", "2")),
            fixture_path=Path(os.getenv("TRENDS_FIXTURE_PATH", str(defaults.fixture_path))),
            output_dir=Path(os.getenv("TRENDS_OUTPUT_DIR", str(defaults.output_dir))),
        )
