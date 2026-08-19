"""Data contracts for trend providers, analysis, families, and routing."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TrendStage(str, Enum):
    DISCOVERY = "DISCOVERY"
    EMERGING = "EMERGING"
    ACCELERATING = "ACCELERATING"
    BREAKOUT = "BREAKOUT"
    MAINSTREAM = "MAINSTREAM"
    SATURATED = "SATURATED"
    DECLINING = "DECLINING"
    EVENT_SPIKE = "EVENT_SPIKE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SearchIntent(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    PROBLEM_AWARE = "PROBLEM_AWARE"
    SOLUTION_AWARE = "SOLUTION_AWARE"
    COMMERCIAL = "COMMERCIAL"
    TRANSACTIONAL = "TRANSACTIONAL"
    VERTICAL_SPECIFIC = "VERTICAL_SPECIFIC"


class Recommendation(str, Enum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    INVESTIGATE = "INVESTIGATE"
    ROUTE_TO_SERVICES = "ROUTE_TO_SERVICES"
    HIGH_PRIORITY = "HIGH_PRIORITY"


@dataclass
class AttentionPoint:
    timestamp: str
    value: float
    # Google Trends and similar indexes are normalized, not absolute volume.
    evidence_type: str = "normalized"  # measured, normalized, estimated, inferred


@dataclass
class RelatedQuery:
    query: str
    value: float = 0.0
    rising: bool = False
    evidence_type: str = "measured"


@dataclass
class GeoInterest:
    location: str
    value: float
    level: str = "region"
    evidence_type: str = "normalized"


@dataclass
class ProviderTrend:
    topic: str
    source: str
    history: list[AttentionPoint]
    related_queries: list[RelatedQuery] = field(default_factory=list)
    geo_interest: list[GeoInterest] = field(default_factory=list)
    category: str = ""
    competition_level: float | None = None
    competition_velocity: float | None = None
    sample_size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HorizonMetrics:
    attention_level: float
    velocity: float
    acceleration: float
    persistence: float
    volatility: float
    periods: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrendSignal:
    topic: str
    family_name: str
    member_terms: list[str]
    sources: list[str]
    source_confirmation: str
    metrics_by_horizon: dict[str, HorizonMetrics]
    attention_level: float
    attention_velocity: float
    attention_acceleration: float
    persistence_score: float
    volatility_score: float
    geographic_spread_score: float
    commercial_intent_score: float
    competition_score: float
    competition_velocity: float | None
    event_spike_probability: float
    trend_confidence_score: float
    attention_score: float
    commercial_trend_score: float
    market_relevance_score: float
    stage: str
    recommendation: str
    related_queries: list[dict[str, Any]]
    second_order_shift: str
    routes: list[str]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    search_volume: float | None = None
    average_cpc: float | None = None
    paid_competition_index: float | None = None
    buyer_intent_score: float | None = None
    demand_opportunity_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = data["trend_confidence_score"]
        return data
