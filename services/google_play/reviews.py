"""Explainable complaint-theme extraction, not generic sentiment."""
from __future__ import annotations

import re
from collections import defaultdict

from .models import Review

THEMES = {
    "crashes": (r"crash", r"freez", r"won't open", r"stops working"),
    "ads": (r"too many ads?", r"intrusive ads?", r"ad after"),
    "pricing": (r"too expensive", r"overpriced", r"subscription", r"paywall"),
    "data loss": (r"lost (?:my )?data", r"deleted my", r"data (?:is )?gone"),
    "export problems": (r"export", r"csv", r"pdf"),
    "synchronization": (r"sync", r"cloud backup"),
    "complexity": (r"too complicated", r"confusing", r"bloated", r"too many features"),
    "gps reliability": (r"gps", r"missed (?:a )?trip", r"mileage.*wrong"),
    "notifications": (r"notification", r"reminder.*(?:not|doesn't)"),
    "account required": (r"account required", r"forced.*sign", r"must.*login"),
    "support": (r"no response", r"customer support", r"support.*(?:bad|poor)"),
}


def cluster_reviews(reviews: list[Review]) -> list[dict]:
    negative = [r for r in reviews if r.rating <= 3]
    matches: dict[str, list[str]] = defaultdict(list)
    for review in negative:
        text = review.text.lower()
        for theme, patterns in THEMES.items():
            if any(re.search(pattern, text) for pattern in patterns):
                matches[theme].append(review.text)
    clusters = [{
        "theme": theme,
        "mentions": len(examples),
        "negative_review_percentage": round(len(examples) / max(len(negative), 1) * 100, 1),
        "examples": examples[:3],
    } for theme, examples in matches.items()]
    return sorted(clusters, key=lambda x: x["mentions"], reverse=True)
