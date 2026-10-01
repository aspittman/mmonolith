import math
import statistics


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def weighted_median(pairs: list[tuple[float, float]]) -> float:
    pairs = sorted(pairs)
    total = sum(weight for _, weight in pairs)
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= total / 2:
            return value
    return pairs[-1][0] if pairs else 0.0


def estimate_valuation(comparables: list[dict], config=None, quality_adjustment=1.0) -> dict:
    config = config or {}
    minimum = int(config.get("minimum_comparable_count", 3))
    high_count = int(config.get("high_confidence_comparable_count", 8))
    if len(comparables) < minimum:
        return {"estimated_low": None, "estimated_mid": None, "estimated_high": None, "valuation_confidence": "unavailable" if not comparables else "low", "supporting_comparable_count": len(comparables), "strong_comparable_count": sum(c["similarity_score"] >= .7 for c in comparables), "valuation_method": "insufficient comparable evidence"}
    prices = [float(item["sale_price"]) for item in comparables]
    pairs = [(float(item["sale_price"]), max(.01, float(item["adjusted_comparable_weight"]))) for item in comparables]
    low_p, high_p = config.get("valuation_percentiles", [0.25, 0.75])
    low = percentile(prices, float(low_p))
    high = percentile(prices, float(high_p))
    mid = weighted_median(pairs)
    strong = sum(item["similarity_score"] >= .7 for item in comparables)
    confidence = "high" if len(comparables) >= high_count and strong >= max(3, high_count // 2) else "medium"
    adjustment = max(.65, min(1.35, quality_adjustment))
    return {"estimated_low": round(low * adjustment, 2), "estimated_mid": round(mid * adjustment, 2), "estimated_high": round(high * adjustment, 2), "valuation_confidence": confidence, "supporting_comparable_count": len(comparables), "strong_comparable_count": strong, "valuation_method": "weighted median with comparable 25th/75th percentiles"}


def estimated_profit(valuation: dict, config=None, acquisition_cost=0.0) -> dict:
    config = config or {}
    mid = valuation.get("estimated_mid")
    if mid is None:
        return {"expected_net_value": None, "estimated_cost": None, "method": "unavailable"}
    commission = float(config.get("marketplace_commission_rate", .15))
    renewals = float(config.get("annual_renewal_cost", 12)) * float(config.get("expected_holding_years", 2))
    outreach = float(config.get("expected_outreach_cost", 0))
    escrow = float(config.get("escrow_fee", 0))
    negotiation = float(config.get("expected_negotiation_discount", .1))
    probability = float(config.get("estimated_sale_probability", .12))
    net_sale = mid * (1 - negotiation) * (1 - commission) - escrow
    costs = float(acquisition_cost or 0) + renewals + outreach
    return {"expected_net_value": round(probability * net_sale - costs, 2), "estimated_cost": round(costs, 2), "expected_net_sale_price": round(net_sale, 2), "sale_probability_assumption": probability, "method": "configured probability estimate; not a forecast"}
