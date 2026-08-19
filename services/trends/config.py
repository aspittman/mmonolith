"""Centralized strategic thresholds for the trends service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import config as root_config


DEFAULT_SERVICE_KEYWORDS: dict[str, list[str]] = {
    "new websites": ["hire web developer", "website development company", "small business website cost", "website designer pricing"],
    "website redesign": ["website redesign service", "website redesign company", "website redesign cost", "hire website designer"],
    "ecommerce development": ["ecommerce development company", "hire ecommerce developer", "shopify developer", "ecommerce website cost"],
    "website repair and performance": ["website repair service", "wordpress help", "website speed optimization service", "fix broken website"],
    "API integrations": ["API integration services", "hire API developer", "custom API integration", "API integration company"],
    "CRM integrations": ["CRM integration services", "salesforce integration consultant", "hubspot integration services", "CRM consultant"],
    "payment integrations": ["payment gateway integration service", "stripe integration developer", "payment integration company", "hire stripe developer"],
    "business automation": ["business automation services", "workflow automation consultant", "zapier consultant", "business process automation company"],
    "AI chatbot and receptionist": ["AI chatbot development company", "AI receptionist pricing", "AI chatbot for business", "hire AI developer"],
    "mobile applications": ["mobile app development company", "hire app developer", "mobile app development cost", "custom app developer"],
    "SEO and online visibility": ["SEO services", "hire SEO consultant", "SEO agency pricing", "small business SEO company"],
    "booking and lead systems": ["online booking system for business", "lead generation system", "appointment scheduling software", "custom booking system"],
}


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
    watch_topics: list[str] = field(default_factory=lambda: list(DEFAULT_SERVICE_KEYWORDS))
    service_keywords: dict[str, list[str]] = field(
        default_factory=lambda: {name: list(keywords) for name, keywords in DEFAULT_SERVICE_KEYWORDS.items()})
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    dataforseo_location_code: int = 2840
    dataforseo_language_code: str = "en"
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
            service_keywords=defaults.service_keywords,
            dataforseo_login=os.getenv("DATAFORSEO_LOGIN", "").strip(),
            dataforseo_password=os.getenv("DATAFORSEO_PASSWORD", "").strip(),
            dataforseo_location_code=int(os.getenv("DATAFORSEO_LOCATION_CODE", "2840")),
            dataforseo_language_code=os.getenv("DATAFORSEO_LANGUAGE_CODE", "en").strip(),
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
