"""Provider-neutral Google Play records and scored opportunities."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Review:
    review_id: str
    text: str
    rating: int
    date: str | None = None
    source: str = "unknown"


@dataclass
class AppRecord:
    package_name: str
    app_name: str
    niche: str
    keyword: str
    developer: str = ""
    play_url: str = ""
    category: str = ""
    rating: float | None = None
    rating_count: int | None = None
    review_count: int | None = None
    install_estimate: int | None = None
    price: float | None = None
    currency: str | None = None
    in_app_purchases: bool | None = None
    subscription: bool | None = None
    advertising: bool | None = None
    last_updated: str | None = None
    description: str = ""
    features: list[str] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    source: str = "unknown"
    evidence_type: str = "measured"  # measured, estimated, or inferred
    search_relevance: float | None = None


@dataclass
class NicheResearch:
    niche: str
    primary_keyword: str
    apps: list[AppRecord]
    related_keywords: list[str] = field(default_factory=list)
    search_interest: float | None = None
    commercial_users: bool = False
    vertical_specificity: float = 0.5
    complexity_signals: list[str] = field(default_factory=list)
    source_count: int = 1
    country: str = "US"
    collected_at: str | None = None
    monthly_search_volume: int | None = None
    average_cpc: float | None = None
    acquisition_difficulty: float | None = None
    policy_risks: list[str] = field(default_factory=list)


@dataclass
class Opportunity:
    niche: str
    primary_keyword: str
    google_play_score: float
    confidence_score: float
    demand_score: float
    dissatisfaction_score: float
    competition_strength_score: float
    monetization_score: float
    build_complexity_score: float
    market_gap_score: float
    maintenance_gap_score: float
    vertical_specificity_score: float
    pattern: str
    recommendation: str
    complaint_clusters: list[dict[str, Any]]
    competitors: list[dict[str, Any]]
    evidence: dict[str, Any]
    recommended_mvp: list[str]
    positioning: str
    primary_risk: str
    validation_experiment: str = "Interview five target users and test a paid landing-page offer."
    excluded_features: list[str] = field(default_factory=list)
    monetization_hypothesis: str = "Paid download or simple subscription; validate before building."
    policy_risks: list[str] = field(default_factory=list)
    source_freshness: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
