"""Turn trend signals and configured primitives into focused app-search seeds."""
from __future__ import annotations


def expand_seeds(topics: list[str], primitives: list[str], limit: int = 100) -> list[str]:
    seeds: list[str] = []
    for topic in topics:
        clean = " ".join(topic.split()).strip()
        if not clean:
            continue
        seeds.append(clean)
        for primitive in primitives:
            if primitive.lower() not in clean.lower():
                seeds.append(f"{clean} {primitive}")
    return list(dict.fromkeys(seeds))[:limit]


def topics_from_routes(routes: list[dict]) -> list[str]:
    topics = []
    for route in routes:
        payload = route.get("payload", {})
        topics.extend([payload.get("topic", ""), *payload.get("related_queries", [])])
    return [topic for topic in dict.fromkeys(topics) if topic]
