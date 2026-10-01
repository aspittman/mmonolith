from devspace_domain_research.config import CITY_TERMS, STATE_TERMS
from devspace_domain_research.grammar import analyze_grammar, generate_from_grammar
from devspace_domain_research.niche_config import NICHE_CONFIG


def generate_domains_for_niche(niche: str, limit: int | None = None, market_sales=None, grammar_report=None, minimum_grammar_support=2) -> list[dict]:
    if niche not in NICHE_CONFIG:
        raise ValueError(f"Unknown domain merchant niche: {niche}")

    config = NICHE_CONFIG[niche]
    patterns = config["patterns"]

    report = grammar_report or (analyze_grammar(market_sales, niche) if market_sales else None)
    candidates = generate_from_grammar(
        report or {}, niche,
        sold_domains=[sale.get("domain") for sale in (market_sales or [])],
        limit=limit or 250,
        minimum_support=minimum_grammar_support,
    )

    locations = STATE_TERMS + CITY_TERMS
    prefixes = ["top", "best", "fast", "local"]

    for pattern in patterns:
        candidates.append({
            "domain": f"{pattern}.com",
            "source": "generated_base",
            "niche": niche,
        })

        for prefix in prefixes:
            candidates.append({
                "domain": f"{prefix}{pattern}.com",
                "source": "generated_prefix",
                "niche": niche,
            })

        for location in locations:
            candidates.append({
                "domain": f"{location}{pattern}.com",
                "source": "generated_local",
                "niche": niche,
            })

    seen = set()
    deduped = []

    for item in candidates:
        domain = item["domain"]

        if domain in seen:
            continue

        seen.add(domain)
        deduped.append(item)

    if limit:
        return deduped[:limit]

    return deduped
