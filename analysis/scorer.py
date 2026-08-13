"""Transparent demand, opportunity, and evidence-confidence formulas."""
from __future__ import annotations

import math

import config

SPECIALIZATION = {
    "API_INTEGRATION": .85, "CRM_INTEGRATION": .90, "PAYMENT_INTEGRATION": .85,
    "AI_INTEGRATION": .90, "AUTOMATION": .85, "SECURITY": .90, "DATABASE": .80,
    "ACCESSIBILITY": .80, "SEO_TECHNICAL": .70, "CUSTOM_WEB_APP": .80,
    "PERFORMANCE_OPTIMIZATION": .65, "FORM_EMAIL_FIXES": .55, "BOOKING_SYSTEM": .70,
    "ECOMMERCE": .60, "WORDPRESS": .40, "WEBSITE_REPAIR": .45,
    "WEBSITE_REDESIGN": .35, "WEBSITE_DESIGN": .30, "OTHER": .20,
}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def demand_score(*, count: int, max_count: int, growth_pct: float | None,
                 median_budget: float | None, max_budget: float, sources: int,
                 recent_share: float) -> float:
    factors = {
        "volume": math.log1p(count) / math.log1p(max(max_count, 1)),
        "growth": .5 if growth_pct is None else clamp((growth_pct + 100) / 300),
        "budget": 0.0 if median_budget is None else math.log1p(median_budget) / math.log1p(max(max_budget, 1)),
        "recency": clamp(recent_share),
        "sources": clamp(sources / 3),
    }
    weights = {
        "volume": config.DEMAND_WEIGHT_VOLUME, "growth": config.DEMAND_WEIGHT_GROWTH,
        "budget": config.DEMAND_WEIGHT_BUDGET, "recency": config.DEMAND_WEIGHT_RECENCY,
        "sources": config.DEMAND_WEIGHT_SOURCE_DIVERSITY,
    }
    total_weight = sum(weights.values()) or 1
    return round(100 * sum(factors[k] * weights[k] for k in factors) / total_weight, 1)


def confidence_score(count_30d: int, sources: int, budget_samples: int) -> float:
    evidence = clamp(count_30d / max(config.MIN_OBSERVATIONS_FOR_HIGH_CONFIDENCE, 1))
    diversity = clamp(sources / 3)
    budget_coverage = clamp(budget_samples / max(count_30d, 1))
    return round(100 * (.65 * evidence + .25 * diversity + .10 * budget_coverage), 1)


def opportunity_score(category: str, demand: float, median_budget: float | None,
                      max_budget: float, growth_pct: float | None) -> float:
    budget = 0.0 if median_budget is None else math.log1p(median_budget) / math.log1p(max(max_budget, 1))
    growth = .5 if growth_pct is None else clamp((growth_pct + 100) / 300)
    # Competition is intentionally absent until a trustworthy measurement exists.
    return round(clamp(.45 * demand / 100 + .20 * budget + .20 * growth +
                       .15 * SPECIALIZATION.get(category, .3)) * 100, 1)

