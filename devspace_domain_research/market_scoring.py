from datetime import date
import statistics

from devspace_domain_research.comparable_sales import rank_comparables
from devspace_domain_research.valuation import estimate_valuation, estimated_profit


DEFAULT_WEIGHTS = {
    "quality": 0.35,
    "comparable_sales": 0.20,
    "market": 0.12,
    "liquidity": 0.12,
    "buyer_market": 0.13,
    "timing": 0.08,
}


def _clamp(value) -> int:
    return max(0, min(100, round(value)))


def _signal_rows(signals) -> list[dict]:
    if isinstance(signals, list):
        return [item for item in signals if isinstance(item, dict)]
    if isinstance(signals, dict):
        for key in ("buyers", "companies", "signals", "items", "domains"):
            if isinstance(signals.get(key), list):
                return [item for item in signals[key] if isinstance(item, dict)]
    return []


def score_market_evidence(result: dict, sales: list[dict], config=None, signals=None, acquisition_cost=0.0, today=None) -> dict:
    config = config or {}
    today = today or date.today()
    comparables = rank_comparables(result["domain"], sales, config, result.get("niche"), today)
    minimum = int(config.get("minimum_comparable_count", 3))
    strong = [item for item in comparables if item["similarity_score"] >= .7]
    close = [item for item in comparables if item["similarity_score"] >= .55]
    comparable_score = _clamp(min(45, len(close) * 8) + min(30, len(strong) * 10) + (statistics.mean([c["adjusted_comparable_weight"] for c in comparables]) * 25 if comparables else 0))
    window = int(config.get("sales_trend_window_days", 730))
    recent = [item for item in comparables if (today - date.fromisoformat(item["sale_date"])).days <= window]
    marketplaces = {item.get("marketplace") for item in recent if item.get("marketplace")}
    prices = [item["sale_price"] for item in comparables]
    outlier_penalty = 0
    if len(prices) >= 3 and max(prices) > statistics.median(prices) * 10:
        outlier_penalty = 15
    market_score = _clamp(min(55, len(recent) * 8) + min(25, len(marketplaces) * 8) + (20 if len(recent) >= len(comparables) / 2 and comparables else 0) - outlier_penalty)
    liquidity_window = int(config.get("liquidity_window_days", 1095))
    liquid = [item for item in comparables if (today - date.fromisoformat(item["sale_date"])).days <= liquidity_window]
    unique_sales = {item["comparable_domain"] for item in liquid}
    liquidity_score = _clamp(min(70, len(unique_sales) * 9) + (15 if len(unique_sales) >= 4 else 0) + (15 if prices and statistics.median(prices) <= 10000 else 0))
    buyer_rows = _signal_rows(signals)
    active_buyers = [row for row in buyer_rows if str(row.get("active", "true")).lower() not in {"false", "0", "closed"}]
    decision_makers = [row for row in active_buyers if row.get("email") or row.get("contact") or row.get("title")]
    buyer_score = _clamp(min(65, len(active_buyers) * 5) + min(35, len(decision_makers) * 7)) if buyer_rows else None
    timing_rows = [row for row in buyer_rows if any(row.get(key) for key in ("funding", "hiring", "expansion", "launch", "recent_activity"))]
    timing_score = _clamp(len(timing_rows) * 15) if buyer_rows else None
    quality = _clamp(result.get("resale_likelihood_score", 0))
    valuation = estimate_valuation(comparables, config, quality_adjustment=.75 + quality / 200)
    profit = estimated_profit(valuation, config, acquisition_cost)
    risks = []
    penalties = 0
    if len(comparables) < minimum:
        risks.append("Comparable evidence is unavailable or below the configured minimum."); penalties += 10
    if comparables and not strong:
        risks.append("No strong structural comparable was found."); penalties += 6
    if outlier_penalty:
        risks.append("Comparable prices include an extreme outlier; robust statistics were used."); penalties += outlier_penalty
    if buyer_rows and not active_buyers:
        risks.append("No active plausible buyer was identified."); penalties += 12
    if float(acquisition_cost or 0) > float(config.get("maximum_purchase_price", 250)):
        risks.append("Acquisition cost exceeds the configured maximum purchase price."); penalties += 20
    margin = profit.get("expected_net_value")
    if margin is not None and margin < float(config.get("minimum_expected_margin", 100)):
        risks.append("Estimated net value is below the configured margin of safety."); penalties += 15
    weights = {**DEFAULT_WEIGHTS, **(config.get("component_score_weights") or {})}
    enabled = {"quality": quality, "comparable_sales": comparable_score, "market": market_score, "liquidity": liquidity_score}
    if buyer_score is not None:
        enabled["buyer_market"] = buyer_score
    if timing_score is not None:
        enabled["timing"] = timing_score
    total_weight = sum(float(weights[key]) for key in enabled)
    investment = _clamp(sum(enabled[key] * float(weights[key]) for key in enabled) / max(total_weight, .01) - penalties)
    reasons = []
    if comparables:
        reasons.append(f"{len(comparables)} eligible comparable sales were found; {len(strong)} are strong matches.")
        reasons.append(f"The comparable median is {statistics.median(prices):,.0f} {comparables[0]['currency']}.")
    if active_buyers:
        reasons.append(f"{len(active_buyers)} active plausible buyers were supplied by current signals.")
    confidence = valuation["valuation_confidence"]
    buy = int(config.get("minimum_buy_score", 75))
    review = int(config.get("minimum_review_score", 55))
    if not comparables:
        recommendation = "insufficient_data"
    elif investment >= buy and len(comparables) >= minimum:
        recommendation = "strong_buy" if investment >= min(90, buy + 10) else "buy"
    elif investment >= review:
        recommendation = "watch"
    else:
        recommendation = "reject"
    return {
        "market_data_status": "available" if comparables else "unavailable",
        "quality_score": quality, "comparable_sales_score": comparable_score,
        "market_score": market_score, "liquidity_score": liquidity_score,
        "buyer_market_score": buyer_score, "timing_score": timing_score,
        "investment_score": investment, "risk_penalties": penalties,
        "market_confidence": confidence, "recommendation": recommendation,
        "market_reasons": reasons, "market_risks": risks,
        "top_comparables": comparables[:int(config.get("display_comparable_count", 5))],
        "estimated_resale": valuation, "estimated_profit": profit,
        "score_formula": {"weights": weights, "available_components": list(enabled), "penalties": penalties},
        "buyer_market_size": len(active_buyers),
    }


def unavailable_market_evidence(result: dict) -> dict:
    return {
        "market_data_status": "unavailable", "quality_score": _clamp(result.get("resale_likelihood_score", 0)),
        "comparable_sales_score": None, "market_score": None, "liquidity_score": None,
        "buyer_market_score": None, "timing_score": None, "investment_score": None,
        "risk_penalties": 0, "market_confidence": "unavailable", "recommendation": None,
        "market_reasons": [], "market_risks": ["Historical market data is disabled or unavailable."],
        "top_comparables": [], "estimated_resale": {"estimated_low": None, "estimated_mid": None, "estimated_high": None, "valuation_confidence": "unavailable", "supporting_comparable_count": 0, "strong_comparable_count": 0, "valuation_method": "unavailable"},
        "estimated_profit": {"expected_net_value": None, "estimated_cost": None, "method": "unavailable"},
        "buyer_market_size": 0,
    }
