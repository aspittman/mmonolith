"""Normalized Google Play opportunity and confidence scoring."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import NicheResearch


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def demand_score(niche: NicheResearch) -> float:
    installs = sum(a.install_estimate or 0 for a in niche.apps)
    reviews = sum(a.review_count or a.rating_count or 0 for a in niche.apps)
    adopted = sum((a.install_estimate or 0) >= 1_000 or (a.rating_count or 0) >= 100 for a in niche.apps)
    install_signal = min(1, math.log10(installs + 1) / 6)
    review_signal = min(1, math.log10(reviews + 1) / 5)
    breadth = min(1, adopted / 3)
    if niche.monthly_search_volume is not None:
        search = min(1, math.log10(niche.monthly_search_volume + 1) / 5)
    else:
        search = .5 if niche.search_interest is None else min(1, niche.search_interest / 100)
    return round(100 * (.40 * install_signal + .25 * review_signal + .20 * breadth + .15 * search), 1)


def dissatisfaction_score(niche: NicheResearch) -> float:
    weighted_bad = total = 0
    negative_reviews = review_total = 0
    for app in niche.apps:
        count = app.rating_count or app.review_count or 1
        if app.rating is not None:
            weighted_bad += max(0, (4.5 - app.rating) / 2.5) * count
            total += count
        negative_reviews += sum(r.rating <= 3 for r in app.reviews)
        review_total += len(app.reviews)
    rating_pain = weighted_bad / max(total, 1)
    sampled_pain = negative_reviews / max(review_total, 1)
    return round(clamp(100 * (.65 * rating_pain + .35 * sampled_pain)), 1)


def competition_strength_score(niche: NicheResearch) -> float:
    leaders = [a for a in niche.apps if (a.install_estimate or 0) >= 100_000 and (a.rating or 0) >= 4.3]
    polish = sum((a.rating or 0) >= 4.4 and (a.rating_count or 0) >= 1_000 for a in niche.apps)
    brand = min(1, sum(a.install_estimate or 0 for a in leaders) / 5_000_000)
    return round(clamp(100 * (.45 * min(1, len(leaders) / 3) + .35 * min(1, polish / 3) + .20 * brand)), 1)


COMPLEXITY_WEIGHTS = {
    "backend": 14, "authentication": 8, "payments": 7, "gps": 12, "camera": 5,
    "ocr": 12, "ai": 14, "cloud_sync": 12, "integrations": 12, "real_time": 16,
    "regulated": 25, "sensitive_data": 15, "network_effects": 35, "marketplace": 30,
}


def build_complexity_score(signals: list[str]) -> float:
    return round(clamp(12 + sum(COMPLEXITY_WEIGHTS.get(s, 4) for s in set(signals))), 1)


def confidence_score(niche: NicheResearch) -> float:
    fields = []
    for app in niche.apps:
        fields.extend([app.rating, app.rating_count, app.install_estimate, app.last_updated])
    completeness = sum(v is not None for v in fields) / max(len(fields), 1)
    review_samples = sum(len(a.reviews) for a in niche.apps)
    evidence = min(1, len(niche.apps) / 5) * .35 + min(1, review_samples / 25) * .30
    diversity = min(1, niche.source_count / 3) * .20
    history = .15 if any(a.last_updated for a in niche.apps) else 0
    return round(clamp(100 * (evidence + diversity + history) * (.65 + .35 * completeness)), 1)


def maintenance_gap_score(niche: NicheResearch, stale_days: int = 365) -> float:
    now = datetime.now(timezone.utc)
    stale_weight = adoption = 0
    for app in niche.apps:
        weight = math.log1p(app.install_estimate or app.rating_count or 0)
        adoption += weight
        try:
            updated = datetime.fromisoformat((app.last_updated or "").replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if (now - updated).days >= stale_days:
                stale_weight += weight
        except ValueError:
            pass
    return round(clamp(100 * stale_weight / max(adoption, 1)), 1)


def recommendation(score: float, confidence: float, complexity: float, competition: float) -> str:
    if complexity >= 85 or (score < 35 and confidence >= 50): return "REJECT"
    if score >= 75 and confidence >= 65 and complexity <= 65 and competition <= 75: return "STRONG_CANDIDATE"
    if score >= 60 and confidence >= 45: return "INVESTIGATE"
    if score >= 45 or confidence < 45: return "WATCH"
    return "WEAK"
