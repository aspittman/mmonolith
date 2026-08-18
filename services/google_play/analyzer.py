"""Turn provider records into explainable, ranked opportunities."""
from __future__ import annotations

from .config import GooglePlayConfig
from .models import NicheResearch, Opportunity
from .reviews import cluster_reviews
from .scoring import (build_complexity_score, competition_strength_score, confidence_score,
                      demand_score, dissatisfaction_score, maintenance_gap_score, recommendation)


def _monetization(n: NicheResearch) -> float:
    if not n.apps: return 0.0
    paid = sum(bool(a.price) or bool(a.in_app_purchases) or bool(a.subscription) or bool(a.advertising) for a in n.apps)
    business_bonus = 20 if n.commercial_users else 0
    return round(min(100, paid / len(n.apps) * 75 + business_bonus), 1)


def analyze_niche(n: NicheResearch, cfg: GooglePlayConfig) -> Opportunity:
    demand = demand_score(n)
    dissatisfaction = dissatisfaction_score(n)
    competition = competition_strength_score(n)
    complexity = build_complexity_score(n.complexity_signals)
    maintenance = maintenance_gap_score(n, cfg.stale_after_days)
    monetization = _monetization(n)
    relevance = [a.search_relevance for a in n.apps if a.search_relevance is not None]
    market_gap = round(100 - (sum(relevance) / len(relevance) * 100), 1) if relevance else 50.0
    vertical = round(n.vertical_specificity * 100, 1)
    reviews = [r for a in n.apps for r in a.reviews]
    clusters = cluster_reviews(reviews)
    confidence = confidence_score(n)
    # Demand gates the upside: absence of competition is not useful without adoption evidence.
    quality = (.24 * demand + .18 * dissatisfaction + .14 * market_gap + .12 * monetization +
               .09 * maintenance + .09 * vertical + .08 * (100 - competition) + .06 * (100 - complexity))
    score = round(min(100, quality * (.55 + .45 * demand / 100)), 1)
    if maintenance >= 60 and demand >= 45: pattern = "PROVEN_BUT_ABANDONED"
    elif dissatisfaction >= 50 and demand >= 45: pattern = "PROVEN_BUT_HATED"
    elif market_gap >= 55: pattern = "SEARCH_DEMAND_WEAK_RESULTS"
    elif any(c["theme"] in {"complexity", "pricing"} for c in clusters): pattern = "OVERSIZED_SOFTWARE"
    else: pattern = "GENERAL_GAP"
    top_features = [c["theme"] for c in clusters[:4]] or ["focused core workflow", "simple export"]
    competitors = [{"app_name": a.app_name, "package_name": a.package_name, "rating": a.rating,
                    "rating_count": a.rating_count, "install_estimate": a.install_estimate,
                    "last_updated": a.last_updated, "source": a.source,
                    "evidence_type": a.evidence_type} for a in n.apps]
    risk = "Established polished competitors" if competition >= 60 else "Demand evidence may not convert into paid adoption"
    return Opportunity(n.niche, n.primary_keyword, score, confidence, demand, dissatisfaction, competition,
                       monetization, complexity, market_gap, maintenance, vertical, pattern,
                       recommendation(score, confidence, complexity, competition), clusters, competitors,
                       {"competitor_count": len(n.apps), "related_keywords": n.related_keywords,
                        "search_interest": n.search_interest, "data_labels": ["measured", "estimated", "inferred"]},
                       top_features, f"A simpler {n.niche.lower()} for focused professional workflows.", risk)


def normalized_niche_key(value: str) -> str:
    stop = {"app", "tool", "software", "for", "the", "a", "an"}
    return " ".join(sorted(w for w in ''.join(c if c.isalnum() else ' ' for c in value.lower()).split() if w not in stop))


def analyze_all(niches: list[NicheResearch], cfg: GooglePlayConfig) -> list[Opportunity]:
    best: dict[str, Opportunity] = {}
    for niche in niches:
        if cfg.categories and not any(a.category in cfg.categories for a in niche.apps):
            continue
        meaningful = any((a.rating_count or 0) >= cfg.minimum_rating_count or
                         (a.install_estimate or 0) >= cfg.minimum_install_estimate for a in niche.apps)
        if not meaningful:
            continue
        candidate = analyze_niche(niche, cfg)
        key = normalized_niche_key(niche.niche)
        if key not in best or candidate.google_play_score > best[key].google_play_score:
            best[key] = candidate
    candidates = [c for c in best.values() if c.google_play_score >= cfg.minimum_google_play_score
                  and c.confidence_score >= cfg.minimum_confidence
                  and c.competition_strength_score <= cfg.max_competition_strength
                  and c.build_complexity_score <= cfg.max_build_complexity]
    return sorted(candidates, key=lambda c: (c.google_play_score, c.confidence_score), reverse=True)[:cfg.max_results_per_run]
