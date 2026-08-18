"""Provider-aware time-series, intent, confidence, and lifecycle analysis."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from statistics import mean, pstdev

from .models import AttentionPoint, HorizonMetrics, SearchIntent, TrendStage


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _values(points: list[AttentionPoint]) -> list[float]:
    return [max(0.0, float(p.value)) for p in points]


def normalized_changes(values: list[float]) -> list[float]:
    """Percent-like changes safe for relative indexes and zero baselines."""
    changes = []
    for previous, current in zip(values, values[1:]):
        # Symmetric percent change is comparable across provider index scales and bounded.
        denominator = max((abs(previous) + abs(current)) / 2, 1.0)
        changes.append(100 * (current - previous) / denominator)
    return changes


def attention_velocity(points: list[AttentionPoint]) -> float:
    changes = normalized_changes(_values(points))
    if not changes:
        return 0.0
    recent = changes[-min(3, len(changes)):]
    # Convert the useful -100..100 range to a signed momentum score.
    return round(max(-100, min(100, mean(recent) * 2)), 1)


def attention_acceleration(points: list[AttentionPoint]) -> float:
    changes = normalized_changes(_values(points))
    if len(changes) < 2:
        return 0.0
    accelerations = [b - a for a, b in zip(changes, changes[1:])]
    return round(max(-100, min(100, mean(accelerations[-3:]) * 3)), 1)


def volatility_score(points: list[AttentionPoint]) -> float:
    values = _values(points)
    if len(values) < 2 or mean(values) <= 0:
        return 0.0
    coefficient = pstdev(values) / mean(values)
    changes = normalized_changes(values)
    change_noise = pstdev(changes) / 100 if len(changes) > 1 else 0
    return round(clamp(100 * (.65 * min(1, coefficient) + .35 * min(1, change_noise))), 1)


def persistence_score(points: list[AttentionPoint]) -> float:
    values = _values(points)
    if len(values) < 3:
        return 0.0
    changes = normalized_changes(values)
    positive = sum(change > 0 for change in changes) / len(changes)
    longest = current = 0
    for change in changes:
        current = current + 1 if change > 0 else 0
        longest = max(longest, current)
    streak = longest / len(changes)
    half = max(1, len(values) // 2)
    baseline = mean(values[:half])
    recent = mean(values[-half:])
    elevation = clamp(50 + 100 * (recent - baseline) / max(baseline, 1)) / 100
    smoothness = 1 - volatility_score(points) / 100
    duration = min(1, len(values) / 8)
    return round(clamp(100 * (.30 * positive + .25 * streak + .20 * elevation +
                              .15 * smoothness + .10 * duration)), 1)


def event_spike_probability(points: list[AttentionPoint], commercial_intent: float = 0,
                            medium_persistence: float | None = None) -> float:
    values = _values(points)
    if len(values) < 3:
        return 35.0
    peak_index = values.index(max(values))
    others = values[:peak_index] + values[peak_index + 1:]
    baseline = mean(others) if others else 0
    magnitude = clamp((max(values) / max(baseline, 1) - 1) * 40)
    post_peak = values[peak_index + 1:]
    collapse = 0.0
    if post_peak:
        collapse = clamp((max(values) - post_peak[-1]) / max(max(values), 1) * 120)
    isolated = 100 if 0 < peak_index < len(values) - 1 else 35
    persistence_penalty = 100 - (medium_persistence if medium_persistence is not None else persistence_score(points))
    probability = (.34 * magnitude + .24 * collapse + .14 * isolated +
                   .18 * persistence_penalty + .10 * (100 - commercial_intent))
    return round(clamp(probability), 1)


def horizon(points: list[AttentionPoint]) -> HorizonMetrics:
    values = _values(points)
    return HorizonMetrics(
        attention_level=round(mean(values[-3:]), 1) if values else 0.0,
        velocity=attention_velocity(points), acceleration=attention_acceleration(points),
        persistence=persistence_score(points), volatility=volatility_score(points), periods=len(points),
    )


def points_within(points: list[AttentionPoint], days: int) -> list[AttentionPoint]:
    dated = []
    for point in points:
        try:
            timestamp = datetime.fromisoformat(point.timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            dated.append((timestamp, point))
        except ValueError:
            pass
    if not dated:
        return points
    newest = max(timestamp for timestamp, _ in dated)
    selected = [point for timestamp, point in dated if (newest - timestamp).days <= days]
    # Sparse imports still need enough points for derivatives.
    return selected if len(selected) >= 3 else points[-min(len(points), 5):]


COMMERCIAL = {"software", "app", "tool", "service", "pricing", "cost", "best", "reviews",
              "alternative", "company", "provider", "business", "subscription", "quote",
              "estimate", "calculator", "platform", "api", "automation", "crm", "solution"}
TRANSACTIONAL = {"buy", "pricing", "price", "quote", "near me", "subscription", "hire", "demo"}
PROBLEMS = {"how to", "fix", "problem", "help", "improve", "reduce", "replace"}
VERTICALS = {"contractor", "contractors", "dentist", "dentists", "plumber", "plumbers", "roofer",
             "roofing", "landscaping", "electrician", "detailing", "small business", "restaurant",
             "lawyer", "realtor", "hvac", "clinic", "salon"}


def classify_search_intent(query: str) -> SearchIntent:
    text = re.sub(r"\s+", " ", query.lower()).strip()
    if any(term in text for term in TRANSACTIONAL):
        return SearchIntent.TRANSACTIONAL
    if any(term in text for term in VERTICALS) or re.search(r"\bfor\s+[a-z]", text):
        return SearchIntent.VERTICAL_SPECIFIC
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in COMMERCIAL):
        return SearchIntent.COMMERCIAL
    if any(term in text for term in PROBLEMS):
        return SearchIntent.PROBLEM_AWARE
    if any(term in text for term in {"solution", "provider", "service", "alternative"}):
        return SearchIntent.SOLUTION_AWARE
    return SearchIntent.INFORMATIONAL


def commercial_intent_score(topic: str, related: list[tuple[str, float, bool]]) -> tuple[float, list[dict]]:
    classified = []
    weighted_total = weighted_commercial = 0.0
    intent_weight = {SearchIntent.INFORMATIONAL: 0, SearchIntent.PROBLEM_AWARE: .25,
                     SearchIntent.SOLUTION_AWARE: .55, SearchIntent.COMMERCIAL: .75,
                     SearchIntent.VERTICAL_SPECIFIC: .82, SearchIntent.TRANSACTIONAL: 1.0}
    for query, value, rising in related:
        intent = classify_search_intent(query)
        weight = max(float(value), 1) * (1.35 if rising else 1)
        weighted_total += weight
        weighted_commercial += weight * intent_weight[intent]
        classified.append({"query": query, "value": value, "rising": rising, "intent": intent.value})
    base = intent_weight[classify_search_intent(topic)] * 100
    contextual = 100 * weighted_commercial / weighted_total if weighted_total else base
    rising_commercial = sum(item["rising"] and item["intent"] in {
        "COMMERCIAL", "TRANSACTIONAL", "VERTICAL_SPECIFIC"} for item in classified)
    bonus = min(20, rising_commercial * 4)
    # Related behavior is the stronger second-order signal; the root query is context,
    # not a veto when users are demonstrably moving toward vertical/transactional terms.
    return round(clamp(.10 * base + .90 * contextual + bonus), 1), classified


def trend_stage(level: float, velocity: float, acceleration: float, persistence: float,
                volatility: float, spike: float, competition: float, periods: int) -> str:
    if periods < 3:
        return TrendStage.INSUFFICIENT_DATA.value
    if spike >= 85 or (spike >= 70 and persistence < 45):
        return TrendStage.EVENT_SPIKE.value
    if velocity <= -12 and persistence < 55:
        return TrendStage.DECLINING.value
    if level >= 75 and abs(velocity) < 10 and competition >= 70:
        return TrendStage.SATURATED.value
    if level >= 65 and abs(velocity) < 12:
        return TrendStage.MAINSTREAM.value
    if velocity >= 35 and acceleration >= 12 and persistence >= 45:
        return TrendStage.BREAKOUT.value
    if velocity >= 15 and acceleration >= 5 and persistence >= 50:
        return TrendStage.ACCELERATING.value
    if velocity >= 8 and persistence >= 55:
        return TrendStage.EMERGING.value
    return TrendStage.DISCOVERY.value


def trend_transition(previous: str | None, current: str) -> dict | None:
    if not previous or previous == current:
        return None
    return {"previous": previous, "current": current, "changed": True}


def scores(level: float, velocity: float, acceleration: float, persistence: float,
           volatility: float, geo: float, commercial: float, relevance: float,
           competition: float, spike: float) -> tuple[float, float]:
    positive_velocity = clamp(50 + velocity / 2)
    positive_acceleration = clamp(50 + acceleration / 2)
    attention = clamp(.18 * level + .25 * positive_velocity + .18 * positive_acceleration +
                      .24 * persistence + .15 * geo - .08 * volatility)
    commercial_score = clamp(.17 * positive_velocity + .13 * positive_acceleration +
                             .19 * persistence + .22 * commercial + .10 * geo + .14 * relevance +
                             .05 * level - .08 * volatility - .08 * competition - .10 * spike)
    return round(attention, 1), round(commercial_score, 1)


def confidence_score(periods: int, providers: int, completeness: float, horizon_agreement: float,
                     provider_agreement: float, persistence: float, volatility: float,
                     sample_size: int | None = None) -> float:
    history = min(1, periods / 24)
    diversity = min(1, providers / 3)
    sample = min(1, (sample_size or periods) / 100)
    return round(clamp(100 * (.24 * history + .20 * diversity + .16 * completeness +
                              .14 * horizon_agreement + .12 * provider_agreement +
                              .10 * persistence / 100 + .04 * sample) *
                       (1 - .25 * volatility / 100)), 1)


def geographic_spread(values: list[float]) -> float:
    active = [value for value in values if value > 0]
    if not active:
        return 0.0
    breadth = min(1, len(active) / 10)
    balance = 1 - min(1, pstdev(active) / max(mean(active), 1)) if len(active) > 1 else .25
    return round(clamp(100 * (.7 * breadth + .3 * balance)), 1)
