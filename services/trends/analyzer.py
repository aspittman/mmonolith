"""Convert provider observations into explainable commercial trend signals."""
from __future__ import annotations

import math
from statistics import mean

from .analytics import (clamp, commercial_intent_score, confidence_score, event_spike_probability,
                        geographic_spread, horizon, points_within, scores, trend_stage)
from .config import TrendsConfig
from .families import family_name
from .models import ProviderTrend, Recommendation, TrendSignal

RELEVANCE = {"app", "software", "saas", "website", "domain", "automation", "business", "service",
             "lead", "crm", "api", "digital", "contractor", "plumber", "dentist", "estimate",
             "calculator", "platform", "developer", "development", "tool", "local", "b2b"}
UNSAFE = {"porn", "adult", "casino", "gambling", "weapon", "drugs", "hack account", "stolen"}
NOISE = {"celebrity", "scandal", "score", "election", "meme", "breaking news"}


def market_relevance(topic: str, related: list[str], commercial: float) -> float:
    text = " ".join([topic, *related]).lower()
    hits = sum(term in text for term in RELEVANCE)
    # Exceptional commercial evidence can surface a genuinely new market.
    return round(clamp(20 + min(55, hits * 9) + .25 * commercial), 1)


def _agreement(values: list[float]) -> float:
    if len(values) < 2:
        return .55
    signs = [1 if value > 3 else -1 if value < -3 else 0 for value in values]
    majority = max(signs.count(-1), signs.count(0), signs.count(1))
    return majority / len(signs)


def _second_order(classified: list[dict]) -> str:
    order = ["INFORMATIONAL", "PROBLEM_AWARE", "SOLUTION_AWARE", "VERTICAL_SPECIFIC",
             "COMMERCIAL", "TRANSACTIONAL"]
    rising = [item["intent"] for item in classified if item["rising"]]
    present = [intent for intent in order if intent in rising]
    if not present:
        return "NO_CONFIRMED_SHIFT"
    if any(intent in present for intent in {"COMMERCIAL", "TRANSACTIONAL", "VERTICAL_SPECIFIC"}):
        return "GENERAL → VERTICAL → COMMERCIAL" if "VERTICAL_SPECIFIC" in present else "GENERAL → COMMERCIAL"
    return "INFORMATIONAL → PROBLEM_AWARE" if "PROBLEM_AWARE" in present else present[-1]


def _routes(topic: str, score: float, confidence: float, cfg: TrendsConfig) -> list[str]:
    if not cfg.route_to_services or score < cfg.route_score_threshold or confidence < cfg.route_confidence_threshold:
        return []
    text = topic.lower()
    routes = ["service_intelligence", "domain_intelligence"]
    if any(term in text for term in ("app", "software", "tool", "calculator", "platform", "ai")):
        routes.insert(0, "google_play")
    return routes


def _demand_metrics(primary: ProviderTrend, commercial: float, momentum: float,
                    confidence: float) -> tuple[float | None, float | None, float | None, float, float]:
    """Keep absolute keyword demand separate from normalized attention indexes."""
    metadata = primary.metadata
    volume = metadata.get("search_volume")
    cpc = metadata.get("average_cpc")
    paid_competition = metadata.get("paid_competition_index")
    if volume is None:
        return None, None, None, commercial, round(.70 * commercial + .30 * momentum, 1)
    volume_score = clamp(22 * math.log10(max(float(volume), 1)))
    cpc_score = clamp(20 * float(cpc or 0))
    advertiser_signal = clamp(float(paid_competition or 0))
    buyer_intent = clamp(.50 * commercial + .30 * cpc_score + .20 * advertiser_signal)
    opportunity = clamp(.32 * volume_score + .34 * buyer_intent + .20 * momentum + .14 * confidence)
    return float(volume), float(cpc or 0), float(paid_competition or 0), round(buyer_intent, 1), round(opportunity, 1)


def analyze_family(records: list[ProviderTrend], cfg: TrendsConfig) -> TrendSignal:
    primary = max(records, key=lambda record: len(record.history))
    horizons = {
        "short": horizon(points_within(primary.history, cfg.short_window)),
        "medium": horizon(points_within(primary.history, cfg.medium_window)),
        "long": horizon(points_within(primary.history, cfg.long_window)),
    }
    related_raw = []
    seen = set()
    for record in records:
        for query in record.related_queries[:cfg.max_related_queries]:
            if query.query.lower() not in seen:
                seen.add(query.query.lower())
                related_raw.append((query.query, query.value, query.rising))
    commercial, classified = commercial_intent_score(primary.topic, related_raw)
    geo_values = [geo.value for record in records for geo in record.geo_interest]
    geo = geographic_spread(geo_values)
    # A country-targeted keyword request has known scope but cannot claim regional
    # breadth. Treat it as neutral so an online service is not penalized for the
    # deliberate absence of Google Maps/local-market data.
    if not geo_values and primary.metadata.get("index_is_absolute_volume"):
        geo = 50.0
    medium = horizons["medium"]
    spike = event_spike_probability(points_within(primary.history, cfg.short_window),
                                    commercial, medium.persistence)
    competition_values = [r.competition_level for r in records if r.competition_level is not None]
    competition = round(mean(competition_values), 1) if competition_values else 50.0
    competition_velocities = [r.competition_velocity for r in records if r.competition_velocity is not None]
    competition_velocity = round(mean(competition_velocities), 1) if competition_velocities else None
    level = medium.attention_level
    velocity = round(.50 * horizons["short"].velocity + .35 * medium.velocity + .15 * horizons["long"].velocity, 1)
    acceleration = round(.55 * horizons["short"].acceleration + .30 * medium.acceleration +
                         .15 * horizons["long"].acceleration, 1)
    persistence = round(.25 * horizons["short"].persistence + .45 * medium.persistence +
                        .30 * horizons["long"].persistence, 1)
    volatility = round(.55 * horizons["short"].volatility + .30 * medium.volatility +
                       .15 * horizons["long"].volatility, 1)
    relevance = market_relevance(primary.topic, [query[0] for query in related_raw], commercial)
    attention, commercial_score = scores(level, velocity, acceleration, persistence, volatility, geo,
                                         commercial, relevance, competition, spike)
    providers = sorted({record.source for record in records})
    completeness = mean([bool(primary.history), bool(related_raw), bool(primary.geo_interest),
                         primary.competition_level is not None])
    confidence = confidence_score(len(primary.history), len(providers), completeness,
                                  _agreement([m.velocity for m in horizons.values()]),
                                  _agreement([horizon(r.history).velocity for r in records]), persistence,
                                  volatility, primary.sample_size)
    stage = trend_stage(level, velocity, acceleration, persistence, volatility, spike, competition,
                        len(primary.history))
    volume, average_cpc, paid_competition, buyer_intent, demand_opportunity = _demand_metrics(
        primary, commercial, commercial_score, confidence)
    routing_score = demand_opportunity if volume is not None else commercial_score
    routes = _routes(primary.topic, routing_score, confidence, cfg)
    unsafe = any(term in primary.topic.lower() for term in UNSAFE)
    obvious_noise = any(term in primary.topic.lower() for term in NOISE)
    if unsafe or spike > cfg.maximum_event_spike_probability or (obvious_noise and commercial < 45):
        recommendation = Recommendation.IGNORE.value
        routes = []
    elif routing_score >= 85 and confidence >= 75 and routes:
        recommendation = Recommendation.HIGH_PRIORITY.value
    elif routes:
        recommendation = Recommendation.ROUTE_TO_SERVICES.value
    elif routing_score >= 58 and confidence >= 40:
        recommendation = Recommendation.INVESTIGATE.value
    else:
        recommendation = Recommendation.WATCH.value
    reason = (f"{stage.title()} demand: velocity {velocity:+.1f}, acceleration {acceleration:+.1f}, "
              f"persistence {persistence:.1f}; buyer intent is {buyer_intent:.1f}." +
              (f" Keyword-family volume is {volume:.0f}/month with ${average_cpc:.2f} average CPC."
               if volume is not None else " Absolute search volume is unavailable."))
    return TrendSignal(
        topic=primary.topic, family_name=family_name(records),
        member_terms=sorted({r.topic for r in records} | {q[0] for q in related_raw}),
        sources=providers, source_confirmation="MULTI_SOURCE_SIGNAL" if len(providers) > 1 else
        ("GOOGLE_ONLY_SIGNAL" if providers == ["google_trends"] else "SINGLE_SOURCE_SIGNAL"),
        metrics_by_horizon=horizons, attention_level=level, attention_velocity=velocity,
        attention_acceleration=acceleration, persistence_score=persistence,
        volatility_score=volatility, geographic_spread_score=geo,
        commercial_intent_score=commercial, competition_score=competition,
        competition_velocity=competition_velocity, event_spike_probability=spike,
        trend_confidence_score=confidence, attention_score=attention,
        commercial_trend_score=commercial_score, market_relevance_score=relevance, stage=stage,
        recommendation=recommendation, related_queries=classified,
        second_order_shift=_second_order(classified), routes=routes, reason=reason,
        evidence={"data_labels": sorted({p.evidence_type for r in records for p in r.history}),
                  "index_is_absolute_volume": bool(primary.metadata.get("index_is_absolute_volume")),
                  "period_count": len(primary.history),
                  "competition_gap": round(velocity - competition_velocity, 1)
                  if competition_velocity is not None else None,
                  "live_data": bool(primary.metadata.get("live_data")),
                  "absolute_demand_available": volume is not None},
        search_volume=volume, average_cpc=average_cpc, paid_competition_index=paid_competition,
        buyer_intent_score=buyer_intent, demand_opportunity_score=demand_opportunity,
    )


def qualifies(signal: TrendSignal, cfg: TrendsConfig) -> bool:
    return signal.recommendation == Recommendation.IGNORE.value or (
        signal.attention_score >= cfg.minimum_attention_score and
        signal.commercial_trend_score >= cfg.minimum_commercial_trend_score and
        signal.trend_confidence_score >= cfg.minimum_confidence)
