from devspace_domain_research.niche_config import NICHE_CONFIG

VOWELS = "aeiou"

BUYER_ACTION_WORDS = [
    "pros", "pro", "experts", "expert", "quotes", "quote",
    "help", "broker", "service", "services", "near", "local",
    "best", "top", "fast", "trusted", "affordable", "rates",
]

LOW_TRUST_TOKENS = [
    "bet", "vip", "slot", "casino", "888", "777", "apk", "mod",
    "eth", "crypto", "nft", "hack", "cheat", "gamble",
]

TRADEMARK_RISK_TERMS = [
    "google", "youtube", "facebook", "instagram", "apple",
    "microsoft", "openai", "chatgpt", "tesla", "amazon",
    "netflix", "spotify", "tiktok", "adobe", "paypal",
    "stripe", "shopify", "uber", "airbnb",
]

RARE_LETTERS = set("qxzjv")


def base_name(domain: str) -> str:
    return domain.split(".")[0].lower().strip()


def tld(domain: str) -> str:
    parts = domain.lower().strip().split(".")
    return parts[-1] if len(parts) > 1 else ""


def has_numbers(name: str) -> bool:
    return any(c.isdigit() for c in name)


def has_hyphen(name: str) -> bool:
    return "-" in name


def vowel_ratio(name: str) -> float:
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c in VOWELS) / len(letters)


def has_trademark_risk(name: str) -> bool:
    return any(term in name for term in TRADEMARK_RISK_TERMS)


def low_trust_token_count(name: str) -> int:
    return sum(1 for token in LOW_TRUST_TOKENS if token in name)


def money_niche_hits(name: str, niche: str) -> list[str]:
    config = NICHE_CONFIG.get(niche, {})
    money_terms = config.get("money_terms", {})
    return [term for term in money_terms if term in name]


def action_word_hits(name: str) -> list[str]:
    return [term for term in BUYER_ACTION_WORDS if term in name]


def has_obvious_buyer(name: str, niche: str) -> bool:
    return len(money_niche_hits(name, niche)) > 0


def looks_like_gibberish(name: str) -> bool:
    vr = vowel_ratio(name)
    rare_count = sum(1 for c in name if c in RARE_LETTERS)

    if len(name) <= 6 and vr < 0.28:
        return True

    if len(name) <= 8 and rare_count >= 3:
        return True

    return False


def length_score(name: str) -> int:
    length = len(name)

    if length <= 6:
        return 4
    if length <= 10:
        return 10
    if length <= 14:
        return 8
    if length <= 18:
        return -5
    if length <= 22:
        return -18

    return -35


def money_niche_score(name: str, niche: str) -> int:
    config = NICHE_CONFIG.get(niche, {})
    money_terms = config.get("money_terms", {})

    hits = money_niche_hits(name, niche)

    if not hits:
        return 0

    best = max(money_terms[h] for h in hits)
    extra = min(12, (len(hits) - 1) * 6)

    return best + extra


def buyer_pattern_score(name: str, niche: str) -> int:
    score = 0
    niche_hits = money_niche_hits(name, niche)
    action_hits = action_word_hits(name)

    if niche_hits:
        score += 20

    if niche_hits and action_hits:
        score += 25

    if "near" in name and niche_hits:
        score += 12

    if any(w in name for w in ["best", "top", "trusted"]) and niche_hits:
        score += 10

    if any(w in name for w in ["broker", "quotes", "rates"]) and niche_hits:
        score += 16

    return score


def formatting_score(name: str) -> int:
    score = 0

    score -= 16 if has_hyphen(name) else -6
    score -= 30 if has_numbers(name) else -6

    return score


def trust_penalty(name: str) -> int:
    penalty = 0

    penalty -= low_trust_token_count(name) * 25

    if looks_like_gibberish(name):
        penalty -= 45

    return penalty


def readability_score(name: str) -> int:
    vr = vowel_ratio(name)

    score = 8 if 0.30 <= vr <= 0.62 else -8

    if vr < 0.22:
        score -= 14

    if len(name) > 18:
        score -= 8

    return score


def score_brand(domain: str, niche: str) -> int:
    name = base_name(domain)

    if has_trademark_risk(name):
        return -150

    score = 0
    score += money_niche_score(name, niche)
    score += buyer_pattern_score(name, niche)
    score += length_score(name)
    score += formatting_score(name)
    score += readability_score(name)
    score += trust_penalty(name)

    if not has_obvious_buyer(name, niche):
        score = min(score, 45)

    if tld(domain) != "com":
        score -= 20

    return score


def score_resale_likelihood(domain: str, niche: str, brand_score: int) -> int:
    name = base_name(domain)

    if has_trademark_risk(name):
        return 0

    score = 5

    if has_obvious_buyer(name, niche):
        score += 35
    else:
        score -= 15

    score += max(0, min(35, int(brand_score * 0.35)))

    if action_word_hits(name) and money_niche_hits(name, niche):
        score += 12

    if 8 <= len(name) <= 18:
        score += 8
    elif len(name) > 22:
        score -= 15

    if has_hyphen(name):
        score -= 8

    if has_numbers(name):
        score -= 20

    if low_trust_token_count(name) > 0:
        score -= 35

    if tld(domain) != "com":
        score -= 20

    return max(0, min(100, score))


def estimate_domain_price(domain: str, resale_score: int) -> dict:
    name = base_name(domain)

    if has_trademark_risk(name) or low_trust_token_count(name) > 0:
        return {
            "low_price": 0,
            "target_price": 0,
            "stretch_price": 0,
        }

    if resale_score >= 80:
        low, target, stretch = 199, 599, 1299
    elif resale_score >= 65:
        low, target, stretch = 99, 349, 799
    elif resale_score >= 50:
        low, target, stretch = 49, 199, 499
    elif resale_score >= 35:
        low, target, stretch = 0, 99, 249
    else:
        low, target, stretch = 0, 49, 149

    return {
        "low_price": low,
        "target_price": target,
        "stretch_price": stretch,
    }


def domain_category(domain: str, niche: str) -> str:
    name = base_name(domain)

    if has_trademark_risk(name):
        return "TRADEMARK_RISK"

    if low_trust_token_count(name) > 0:
        return "LOW_TRUST"

    if money_niche_hits(name, niche) and action_word_hits(name):
        return "MONEY_NICHE_WITH_BUYER_PATTERN"

    if money_niche_hits(name, niche):
        return "MONEY_NICHE"

    if looks_like_gibberish(name):
        return "GIBBERISH"

    return "GENERAL_REVIEW"


def score_domain(domain: str, niche: str, market_sales=None, market_config=None, signals=None, acquisition_cost=0.0, candidate_context=None) -> dict:
    name = base_name(domain)

    brand_score = score_brand(domain, niche)
    seo_score = 0
    final_score = brand_score

    resale_likelihood = score_resale_likelihood(
        domain=domain,
        niche=niche,
        brand_score=brand_score,
    )

    pricing = estimate_domain_price(
        domain=domain,
        resale_score=resale_likelihood,
    )

    result = {
        "domain": domain,
        "niche": niche,
        "brand_score": brand_score,
        "seo_score": seo_score,
        "score": final_score,
        "resale_likelihood_score": resale_likelihood,
        "low_price": pricing["low_price"],
        "target_price": pricing["target_price"],
        "stretch_price": pricing["stretch_price"],
        "trademark_risk": has_trademark_risk(name),
        "obvious_buyer": has_obvious_buyer(name, niche),
        "buyer_terms": money_niche_hits(name, niche),
        "action_terms": action_word_hits(name),
        "category": domain_category(domain, niche),
        "name_quality_score": resale_likelihood,
        "commercial_intent_score": min(100, (65 if has_obvious_buyer(name, niche) else 0) + (25 if action_word_hits(name) else 0) + (10 if tld(domain) == "com" else 0)),
        "grammar_evidence_score": (candidate_context or {}).get("grammar_evidence_score"),
    }

    if market_config and market_config.get("market_data_enabled"):
        from devspace_domain_research.market_scoring import score_market_evidence
        result.update(score_market_evidence(result, market_sales or [], market_config, signals, acquisition_cost))
    elif market_config is not None:
        from devspace_domain_research.market_scoring import unavailable_market_evidence
        result.update(unavailable_market_evidence(result))

    expected_value = (result.get("estimated_profit") or {}).get("expected_net_value")
    required_margin = float((market_config or {}).get("minimum_expected_margin", 100))
    result["acquisition_economics_score"] = None if expected_value is None else max(0, min(100, round(50 + 50 * float(expected_value) / max(required_margin, 1))))
    result["risk_score"] = max(0, 100 - int(result.get("risk_penalties") or 0) - (100 if result.get("trademark_risk") else 0))

    return result
