from devspace_domain_research.niche_config import NICHE_CONFIG
from devspace_domain_research.scorer import (
    BUYER_ACTION_WORDS,
    action_word_hits,
    base_name,
    domain_category,
    money_niche_hits,
)


POSITIVE_RESPONSE_STATUSES = {
    "positive",
    "interested",
    "offer",
    "buy",
    "buying",
    "accepted",
}

NEGATIVE_RESPONSE_STATUSES = {
    "negative",
    "not_interested",
    "not interested",
    "unsubscribe",
    "rejected",
}


def clean(value) -> str:
    return str(value or "").strip().lower()


def as_float(value, default=0.0) -> float:
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).replace("$", "").replace(",", "").strip()

    if not value:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def as_int(value, default=0) -> int:
    try:
        return int(as_float(value, default=default))
    except (TypeError, ValueError):
        return default


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    return clean(value) in {"1", "true", "yes", "y", "positive", "interested"}


def iter_rows(payload) -> list[dict]:
    if not payload:
        return []

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in [
        "domains",
        "performance",
        "items",
        "signals",
        "results",
        "rows",
        "data",
    ]:
        rows = payload.get(key)

        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]

    return []


def metadata(row: dict) -> dict:
    value = row.get("metadata") or row.get("metadata_json") or {}
    return value if isinstance(value, dict) else {}


def value_from(row: dict, *names, default=None):
    row_metadata = metadata(row)

    for name in names:
        if row.get(name) is not None:
            return row.get(name)

        if row_metadata.get(name) is not None:
            return row_metadata.get(name)

    return default


def row_domain(row: dict) -> str:
    company = row.get("company") if isinstance(row.get("company"), dict) else {}

    return clean(
        value_from(row, "domain")
        or company.get("domain")
        or company.get("name")
        or row.get("name")
    )


def row_category(row: dict, niche: str | None) -> str | None:
    category = value_from(row, "category")

    if category:
        return str(category)

    domain = row_domain(row)

    if domain and niche in NICHE_CONFIG:
        return domain_category(domain, niche)

    return None


def row_terms(row: dict, niche: str | None) -> set[str]:
    terms = set()

    domain = row_domain(row)

    if domain and niche in NICHE_CONFIG:
        terms.update(money_niche_hits(base_name(domain), niche))
        terms.update(action_word_hits(base_name(domain)))

    for name in ["buyer_terms", "action_terms", "terms"]:
        value = value_from(row, name)

        if isinstance(value, list):
            terms.update(clean(item) for item in value if item)
        elif value:
            terms.update(clean(item) for item in str(value).split(",") if item)

    return {term for term in terms if term}


def row_score(row: dict) -> int:
    outcome = clean(value_from(row, "outcome", "status"))
    response_status = clean(value_from(row, "response_status"))
    score = 0

    if outcome == "sold":
        score += 35
    elif outcome == "purchased":
        score += 6
    elif outcome == "listed":
        score += 3
    elif outcome in {"expired", "dropped", "failed"}:
        score -= 12

    if response_status in POSITIVE_RESPONSE_STATUSES:
        score += 22
    elif response_status in NEGATIVE_RESPONSE_STATUSES:
        score -= 18
    elif response_status == "replied":
        score += 8

    if as_bool(value_from(row, "purchase_intent")):
        score += 18

    offer_amount = as_float(value_from(row, "offer_amount"))
    sale_price = as_float(value_from(row, "sale_price"))
    gross_profit = as_float(value_from(row, "gross_profit"))

    if offer_amount:
        score += min(20, int(offer_amount / 50))

    if sale_price:
        score += min(25, int(sale_price / 100))

    if gross_profit:
        score += max(-25, min(25, int(gross_profit / 50)))

    positive_responses = as_int(value_from(row, "positive_responses"))
    negative_responses = as_int(value_from(row, "negative_responses"))
    replies = as_int(value_from(row, "replies", "reply_count"))
    sent = as_int(value_from(row, "sent", "sent_count", "outreach_count"))

    score += positive_responses * 10
    score -= negative_responses * 8
    score += min(12, replies * 3)

    if sent >= 10 and replies == 0 and positive_responses == 0:
        score -= 8

    return score


def summarize_performance(payload, niche: str | None = None) -> dict:
    summary = {
        "domain_scores": {},
        "term_scores": {},
        "category_scores": {},
        "niche_score": 0,
        "rows": 0,
    }

    for row in iter_rows(payload):
        score = row_score(row)

        if score == 0:
            continue

        summary["rows"] += 1
        domain = row_domain(row)

        if domain:
            summary["domain_scores"][domain] = (
                summary["domain_scores"].get(domain, 0) + score
            )

        category = row_category(row, niche)

        if category:
            summary["category_scores"][category] = (
                summary["category_scores"].get(category, 0) + int(score * 0.45)
            )

        for term in row_terms(row, niche):
            summary["term_scores"][term] = (
                summary["term_scores"].get(term, 0) + int(score * 0.5)
            )

        row_niche = clean(value_from(row, "niche", "industry"))

        if niche and row_niche == clean(niche):
            summary["niche_score"] += int(score * 0.2)

    return summary


def bounded_adjustment(value: int) -> int:
    return max(-30, min(35, value))


def apply_performance_adjustments(result: dict, summary: dict | None) -> dict:
    if not summary or not summary.get("rows"):
        result["performance_score_adjustment"] = 0
        result["performance_reasons"] = []
        return result

    domain = clean(result.get("domain"))
    category = result.get("category")
    adjustment = 0
    reasons = []

    domain_adjustment = int(summary["domain_scores"].get(domain, 0) * 0.7)

    if domain_adjustment:
        adjustment += domain_adjustment
        reasons.append(f"domain history {domain_adjustment:+d}")

    category_adjustment = int(summary["category_scores"].get(category, 0) * 0.2)

    if category_adjustment:
        adjustment += category_adjustment
        reasons.append(f"category history {category_adjustment:+d}")

    term_adjustment = 0

    result_terms = (result.get("buyer_terms") or []) + (result.get("action_terms") or [])

    for term in set(result_terms):
        term_adjustment += int(summary["term_scores"].get(term, 0) * 0.15)

    term_adjustment = max(-18, min(22, term_adjustment))

    if term_adjustment:
        adjustment += term_adjustment
        reasons.append(f"term history {term_adjustment:+d}")

    niche_adjustment = max(-8, min(10, int(summary.get("niche_score", 0) * 0.05)))

    if niche_adjustment:
        adjustment += niche_adjustment
        reasons.append(f"niche history {niche_adjustment:+d}")

    adjustment = bounded_adjustment(adjustment)
    result["performance_score_adjustment"] = adjustment
    result["performance_reasons"] = reasons
    result["score"] = result["score"] + adjustment
    result["resale_likelihood_score"] = max(
        0,
        min(100, result["resale_likelihood_score"] + int(adjustment * 0.6)),
    )

    return result
