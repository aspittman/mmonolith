"""Conservative duplicate reduction and trend-family grouping."""
from __future__ import annotations

import re

from .models import ProviderTrend

STOP = {"a", "an", "the", "for", "to", "of", "best", "near", "me", "pricing", "price",
        "software", "app", "tool", "service", "services", "solution", "reviews"}


def term_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in STOP}


def normalized_topic(value: str) -> str:
    tokens = term_tokens(value)
    aliases = {"answering": "receptionist", "apps": "app", "tools": "tool"}
    return " ".join(sorted(aliases.get(token, token) for token in tokens))


def similarity(left: str, right: str) -> float:
    a, b = term_tokens(left), term_tokens(right)
    if not a or not b:
        return 0.0
    overlap = len(a & b) / len(a | b)
    containment = len(a & b) / min(len(a), len(b))
    return max(overlap, containment * .9)


def group_families(records: list[ProviderTrend], threshold: float = .62) -> list[list[ProviderTrend]]:
    groups: list[list[ProviderTrend]] = []
    for record in records:
        target = next((group for group in groups
                       if any(similarity(record.topic, member.topic) >= threshold for member in group)), None)
        if target is None:
            groups.append([record])
        else:
            target.append(record)
    return groups


def family_name(records: list[ProviderTrend]) -> str:
    # Prefer the shortest descriptive topic; longer members tend to be intent branches.
    return min((record.topic for record in records), key=lambda value: (len(term_tokens(value)), len(value)))
