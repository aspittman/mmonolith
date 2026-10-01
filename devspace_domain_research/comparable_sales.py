from datetime import date

from devspace_domain_research.domain_features import extract_domain_features
from devspace_domain_research.market_data import SOURCE_TIERS, parse_date, valuation_eligible


def _overlap(left, right) -> set:
    return set(left or []) & set(right or [])


def rank_comparables(domain: str, sales: list[dict], config=None, niche=None, today=None) -> list[dict]:
    config = config or {}
    candidate = extract_domain_features(domain, niche)
    today = today or date.today()
    max_age = int(config.get("comparable_max_age_days", 1825))
    minimum = float(config.get("minimum_comparable_similarity", 0.45))
    tier = int(config.get("minimum_source_quality_tier", 3))
    results = []
    for sale in sales:
        if sale.get("domain") == candidate["domain"] or not valuation_eligible(sale, config.get("valuation_currency", "USD"), tier):
            continue
        features = sale if sale.get("extension") is not None else extract_domain_features(sale["domain"], sale.get("niche"))
        factors, differences, score = [], [], 0.0
        if features.get("extension") == candidate["extension"]:
            score += 0.20; factors.append("same extension")
        else: differences.append("different extension")
        if candidate.get("niche") and features.get("niche") == candidate["niche"]:
            score += 0.22; factors.append("same niche")
        keyword_overlap = _overlap(candidate["keywords"], features.get("keywords"))
        if keyword_overlap:
            score += min(0.22, 0.12 + 0.05 * len(keyword_overlap)); factors.append("shared keyword: " + ", ".join(sorted(keyword_overlap)))
        if candidate["word_count"] == features.get("word_count"):
            score += 0.10; factors.append("same word count")
        length_difference = abs(candidate["character_count"] - int(features.get("character_count") or 0))
        if length_difference <= 3:
            score += 0.08; factors.append("similar length")
        if candidate["has_geo_pattern"] and features.get("has_geo_pattern"):
            score += 0.10; factors.append("same geographic pattern")
        if _overlap(candidate["prefixes"], features.get("prefixes")):
            score += 0.05; factors.append("same prefix")
        if _overlap(candidate["suffixes"], features.get("suffixes")):
            score += 0.08; factors.append("same suffix")
        if candidate["brandable"] == features.get("brandable"):
            score += 0.04; factors.append("similar brandability")
        score = min(1.0, score)
        if score < minimum:
            continue
        sold = parse_date(sale.get("sale_date"))
        age = max(0, (today - sold).days) if sold else max_age * 2
        recency_weight = max(0.2, 1 - age / max(max_age * 1.25, 1))
        quality_weight = (config.get("source_quality_weights") or SOURCE_TIERS).get(sale.get("source_quality"), 0.1)
        adjusted = score * recency_weight * quality_weight
        results.append({
            "candidate_domain": candidate["domain"], "comparable_domain": sale["domain"],
            "similarity_score": round(score, 4), "sale_price": sale["sale_price"],
            "currency": sale["currency"], "sale_date": sale["sale_date"], "marketplace": sale.get("marketplace"),
            "source_name": sale.get("source_name"), "source_url": sale.get("source_url"),
            "matching_factors": factors, "difference_factors": differences,
            "recency_weight": round(recency_weight, 4), "source_quality_weight": quality_weight,
            "adjusted_comparable_weight": round(adjusted, 4),
        })
    return sorted(results, key=lambda item: (item["adjusted_comparable_weight"], item["similarity_score"]), reverse=True)[:int(config.get("maximum_comparables", 20))]
