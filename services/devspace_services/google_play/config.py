"""Configuration isolated from the existing demand service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import config as root_config


def _boolean(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class GooglePlayConfig:
    enabled: bool = False
    countries: list[str] = field(default_factory=lambda: ["US"])
    categories: list[str] = field(default_factory=list)
    minimum_rating_count: int = 50
    minimum_install_estimate: int = 1_000
    max_competition_strength: float = 80
    max_build_complexity: float = 70
    minimum_confidence: float = 35
    minimum_google_play_score: float = 45
    max_results_per_run: int = 10
    review_sample_size: int = 200
    historical_tracking: bool = True
    stale_after_days: int = 365
    provider: str = "fixture"
    provider_url: str = ""
    provider_api_key: str = ""
    provider_timeout: int = 20
    provider_retries: int = 2
    cache_ttl_hours: int = 24
    consume_trend_routes: bool = True
    max_route_seeds: int = 25
    seed_terms: list[str] = field(default_factory=lambda: [
        "calculator", "estimator", "tracker", "log", "manager"
    ])
    discovery_topics: list[str] = field(default_factory=lambda: [
        "home service", "field service", "self employed", "small business", "hobby"
    ])
    fixture_path: Path = root_config.BASE_DIR / "data/raw/google_play.example.json"
    output_dir: Path = root_config.BASE_DIR / "data/processed/google_play"

    @classmethod
    def from_env(cls) -> "GooglePlayConfig":
        default_fixture = root_config.BASE_DIR / "data/raw/google_play.example.json"
        default_output = root_config.BASE_DIR / "data/processed/google_play"
        return cls(
            enabled=_boolean("GOOGLE_PLAY_ENABLED", False),
            countries=[x.strip() for x in os.getenv("GOOGLE_PLAY_COUNTRIES", "US").split(",") if x.strip()],
            categories=[x.strip() for x in os.getenv("GOOGLE_PLAY_CATEGORIES", "").split(",") if x.strip()],
            minimum_rating_count=int(os.getenv("GOOGLE_PLAY_MIN_RATING_COUNT", "50")),
            minimum_install_estimate=int(os.getenv("GOOGLE_PLAY_MIN_INSTALL_ESTIMATE", "1000")),
            max_competition_strength=float(os.getenv("GOOGLE_PLAY_MAX_COMPETITION", "80")),
            max_build_complexity=float(os.getenv("GOOGLE_PLAY_MAX_BUILD_COMPLEXITY", "70")),
            minimum_confidence=float(os.getenv("GOOGLE_PLAY_MIN_CONFIDENCE", "35")),
            minimum_google_play_score=float(os.getenv("GOOGLE_PLAY_MIN_SCORE", "45")),
            max_results_per_run=int(os.getenv("GOOGLE_PLAY_MAX_RESULTS", "10")),
            review_sample_size=int(os.getenv("GOOGLE_PLAY_REVIEW_SAMPLE_SIZE", "200")),
            historical_tracking=_boolean("GOOGLE_PLAY_HISTORICAL_TRACKING", True),
            stale_after_days=int(os.getenv("GOOGLE_PLAY_STALE_AFTER_DAYS", "365")),
            provider=os.getenv("GOOGLE_PLAY_PROVIDER", "fixture").strip().lower(),
            provider_url=os.getenv("GOOGLE_PLAY_PROVIDER_URL", "").strip(),
            provider_api_key=os.getenv("GOOGLE_PLAY_PROVIDER_API_KEY", "").strip(),
            provider_timeout=int(os.getenv("GOOGLE_PLAY_PROVIDER_TIMEOUT", "20")),
            provider_retries=int(os.getenv("GOOGLE_PLAY_PROVIDER_RETRIES", "2")),
            cache_ttl_hours=int(os.getenv("GOOGLE_PLAY_CACHE_TTL_HOURS", "24")),
            consume_trend_routes=_boolean("GOOGLE_PLAY_CONSUME_TREND_ROUTES", True),
            max_route_seeds=int(os.getenv("GOOGLE_PLAY_MAX_ROUTE_SEEDS", "25")),
            seed_terms=[x.strip() for x in os.getenv(
                "GOOGLE_PLAY_SEED_TERMS", "calculator,estimator,tracker,log,manager"
            ).split(",") if x.strip()],
            discovery_topics=[x.strip() for x in os.getenv(
                "GOOGLE_PLAY_DISCOVERY_TOPICS",
                "home service,field service,self employed,small business,hobby"
            ).split(",") if x.strip()],
            fixture_path=Path(os.getenv("GOOGLE_PLAY_FIXTURE_PATH", str(default_fixture))),
            output_dir=Path(os.getenv("GOOGLE_PLAY_OUTPUT_DIR", str(default_output))),
        )
