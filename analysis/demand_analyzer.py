"""Aggregate local observations into decision-oriented market intelligence."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median

import config
from analysis.classifier import SERVICE_CATEGORIES
from analysis.scorer import confidence_score, demand_score, opportunity_score
from analysis.trend_analyzer import growth, in_window, windows


def _budget(item: dict) -> float | None:
    values = [v for v in (item.get("budget_min"), item.get("budget_max")) if v is not None]
    return mean(values) if values else None


def analyze(observations: list[dict], generated_at: datetime | None = None) -> dict:
    now = generated_at or datetime.now(timezone.utc)
    periods = windows(now, config.DAYS_SHORT, config.DAYS_LONG)
    # Search-interest signals are reported separately and never counted as paid requests.
    requests = [o for o in observations if o.get("observation_type") == "request"]
    by_category = defaultdict(list)
    for item in requests:
        by_category[item["service_category"]].append(item)

    pre_metrics: dict[str, dict] = {}
    for category in SERVICE_CATEGORIES:
        items = by_category[category]
        counts = {name: sum(in_window(i, *bounds) for i in items) for name, bounds in periods.items()}
        current_30 = [i for i in items if in_window(i, *periods["current_30d"])]
        current_7 = [i for i in items if in_window(i, *periods["current_7d"])]
        budgets = [_budget(i) for i in current_30]
        budgets = [b for b in budgets if b is not None]
        pre_metrics[category] = {
            "items": items, "current_7": current_7, "current_30": current_30, "counts": counts,
            "budgets": budgets, "median": median(budgets) if budgets else None,
            "average": mean(budgets) if budgets else None,
        }

    max_count = max((m["counts"]["current_7d"] for m in pre_metrics.values()), default=1)
    max_budget = max((m["median"] or 0 for m in pre_metrics.values()), default=1) or 1
    total_7 = sum(m["counts"]["current_7d"] for m in pre_metrics.values())
    services = []
    for category, m in pre_metrics.items():
        c = m["counts"]
        if not any(c.values()):
            continue
        weekly = growth(c["current_7d"], c["previous_7d"])
        monthly = growth(c["current_30d"], c["previous_30d"])
        sources = sorted({i["source"] for i in m["current_30"]})
        recent_share = c["current_7d"] / max(c["current_30d"], 1)
        demand = demand_score(count=c["current_7d"], max_count=max_count, growth_pct=weekly,
                              median_budget=m["median"], max_budget=max_budget,
                              sources=len(sources), recent_share=recent_share)
        tech = Counter(t for i in m["current_30"] for t in i["technologies"])
        pains = Counter(p for i in m["current_30"] for p in i["pain_points"])
        services.append({
            "category": category, "requests_7d": c["current_7d"],
            "requests_previous_7d": c["previous_7d"], "requests_30d": c["current_30d"],
            "requests_previous_30d": c["previous_30d"],
            "percentage_of_demand_7d": round(c["current_7d"] / total_7 * 100, 1) if total_7 else 0.0,
            "weekly_growth_pct": weekly, "monthly_growth_pct": monthly,
            "average_budget": round(m["average"], 2) if m["average"] is not None else None,
            "median_budget": round(m["median"], 2) if m["median"] is not None else None,
            "budget_sample_count": len(m["budgets"]), "sources_represented": sources,
            "source_count": len(sources), "demand_score": demand,
            "opportunity_score": opportunity_score(category, demand, m["median"], max_budget, weekly),
            "confidence": confidence_score(c["current_30d"], len(sources), len(m["budgets"])),
            "top_technologies": [{"technology": k, "mentions": v} for k, v in tech.most_common(5)],
            "top_pain_points": [{"pain_point": k, "mentions": v} for k, v in pains.most_common(5)],
        })
    services.sort(key=lambda x: (x["demand_score"], x["requests_7d"]), reverse=True)

    technologies = []
    all_tech = {t for i in requests for t in i["technologies"]}
    for tech in all_tech:
        current = sum(tech in i["technologies"] and in_window(i, *periods["current_7d"]) for i in requests)
        previous = sum(tech in i["technologies"] and in_window(i, *periods["previous_7d"]) for i in requests)
        month = sum(tech in i["technologies"] and in_window(i, *periods["current_30d"]) for i in requests)
        technologies.append({"technology": tech, "mentions_7d": current,
                             "mentions_previous_7d": previous, "mentions_30d": month,
                             "weekly_growth_pct": growth(current, previous)})
    technologies.sort(key=lambda x: (x["mentions_7d"], x["weekly_growth_pct"] or 0), reverse=True)

    trends = [o for o in observations if o.get("observation_type") == "search_interest" and
              in_window(o, now - timedelta(days=config.DAYS_SHORT), now)]
    return {
        "generated_at": now.isoformat(),
        "periods": {"short_days": config.DAYS_SHORT, "long_days": config.DAYS_LONG},
        "methodology": {
            "request_counts_exclude_search_interest": True,
            "budget_null_means_unavailable": True,
            "growth_pct_100_with_zero_baseline_means_new_demand": True,
            "competition_data": "unknown",
        },
        "services": services, "technologies": technologies,
        "search_interest": [{"keyword": o["title"], "relative_interest": o["source_metric"],
                             "source": o["source"]} for o in trends],
    }

