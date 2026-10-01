import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date
from itertools import product
from pathlib import Path

from devspace_domain_research.config import CITY_TERMS, STATE_TERMS
from devspace_domain_research.domain_features import normalize_domain
from devspace_domain_research.niche_config import NICHE_CONFIG
from devspace_domain_research.valuation import percentile


GRAMMAR_LEXICON = {
    "geo": STATE_TERMS + CITY_TERMS,
    "speed": ["fast", "quick", "rapid", "instant", "express", "speedy", "same day", "sameday"],
    "authority": ["expert", "experts", "pro", "pros", "advisor", "advisors", "broker", "brokers", "specialist", "specialists"],
    "service": ["help", "quote", "quotes", "rate", "rates", "service", "services", "solution", "solutions", "center", "hub"],
    "consumer_need": ["home", "auto", "car", "business", "personal", "student", "emergency", "debt", "cash", "credit"],
    "loan_subtype": ["title", "payday", "bridge", "hardmoney", "construction", "commercial", "private", "equity"],
    "modifier": ["best", "top", "local", "trusted", "affordable", "smart", "easy", "direct", "online", "prime"],
}


def _domain_parts(domain: str) -> tuple[str, str]:
    normalized = normalize_domain(domain)
    if "." not in normalized:
        return normalized, "com"
    return tuple(normalized.rsplit(".", 1))


def _token_vocabulary(niche: str) -> list[tuple[str, str]]:
    vocabulary = []
    for term in NICHE_CONFIG[niche]["money_terms"]:
        vocabulary.append((term, "niche_keyword"))
    for category, terms in GRAMMAR_LEXICON.items():
        vocabulary.extend((term.replace(" ", ""), category) for term in terms)
    return sorted(set(vocabulary), key=lambda item: (-len(item[0]), item[0]))


def parse_domain_grammar(domain: str, niche: str) -> dict:
    if niche not in NICHE_CONFIG:
        raise ValueError(f"Unknown domain merchant niche: {niche}")
    name, extension = _domain_parts(domain)
    vocabulary = _token_vocabulary(niche)
    tokens, slots = [], []
    cursor = 0
    while cursor < len(name):
        match = next(((term, category) for term, category in vocabulary if name.startswith(term, cursor)), None)
        if match:
            term, category = match
            tokens.append(term)
            slots.append(category)
            cursor += len(term)
            continue
        end = cursor + 1
        while end < len(name) and not any(name.startswith(term, end) for term, _ in vocabulary):
            end += 1
        tokens.append(name[cursor:end])
        slots.append("brandable")
        cursor = end
    template = " + ".join(f"<{slot}>" for slot in slots) + " + <extension>"
    return {"domain": normalize_domain(domain), "second_level": name, "extension": extension, "tokens": tokens, "slots": slots, "template": template}


def load_control_domains(path) -> dict:
    if not path:
        return {"records": [], "error": None}
    source = Path(path)
    if not source.exists():
        return {"records": [], "error": f"control data missing: {source}"}
    try:
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("domains", payload.get("records", []))
        else:
            with source.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
    except Exception as exc:
        return {"records": [], "error": f"control data unreadable: {exc}"}
    records = []
    for row in rows:
        domain = normalize_domain(row.get("domain") or row.get("Domain"))
        if domain and "." in domain:
            outcome = str(row.get("outcome") or row.get("status") or "unsold").strip().lower()
            records.append({**row, "domain": domain, "outcome": outcome})
    return {"records": records, "error": None}


def analyze_grammar(sales: list[dict], niche: str, controls=None, today=None) -> dict:
    today = today or date.today()
    controls = controls or []
    groups = defaultdict(list)
    for sale in sales:
        parsed = parse_domain_grammar(sale.get("domain", ""), niche)
        if "niche_keyword" in parsed["slots"]:
            groups[parsed["template"]].append((sale, parsed))
    negative_counts = Counter()
    for control in controls:
        parsed = parse_domain_grammar(control.get("domain", ""), niche)
        if "niche_keyword" in parsed["slots"] and control.get("outcome", "unsold") not in {"sold", "sale", "converted"}:
            negative_counts[parsed["template"]] += 1
    total_sales = sum(len(rows) for rows in groups.values())
    total_negatives = sum(negative_counts.values())
    baseline = total_sales / (total_sales + total_negatives) if total_negatives else None
    templates = []
    for template, rows in groups.items():
        prices = [float(sale.get("sale_price") or 0) for sale, _ in rows]
        recent = sum(1 for sale, _ in rows if sale.get("sale_date") and (today - date.fromisoformat(sale["sale_date"])).days <= 730)
        venues = sorted({sale.get("marketplace") for sale, _ in rows if sale.get("marketplace")})
        extensions = Counter(parsed["extension"] for _, parsed in rows)
        slot_values = defaultdict(Counter)
        for _, parsed in rows:
            for index, (slot, token) in enumerate(zip(parsed["slots"], parsed["tokens"])):
                slot_values[str(index)][token] += 1
        support = len(rows)
        negative = negative_counts[template]
        observed_rate = support / (support + negative) if negative else (1.0 if controls else None)
        lift = observed_rate / baseline if baseline and observed_rate is not None else None
        confidence = "high" if support >= 8 and len(venues) >= 2 else "medium" if support >= 3 else "low"
        specificity = sum(slot != "brandable" for slot in rows[0][1]["slots"]) / max(len(rows[0][1]["slots"]), 1)
        evidence_score = min(100, round(math.log2(1 + support) * 10 + specificity * 35 + min(len(venues), 3) * 5 + min(recent, 5) * 2 - (15 if negative > support else 0)))
        templates.append({
            "template": template,
            "slots": rows[0][1]["slots"],
            "sale_count": support,
            "median_price": round(statistics.median(prices), 2),
            "price_25th": round(percentile(prices, .25), 2),
            "price_75th": round(percentile(prices, .75), 2),
            "recent_sale_count": recent,
            "marketplaces": venues,
            "marketplace_count": len(venues),
            "extensions": dict(extensions),
            "typical_character_count": round(statistics.median(len(parsed["second_level"]) for _, parsed in rows)),
            "representative_sales": sorted(({"domain": sale["domain"], "price": sale.get("sale_price"), "date": sale.get("sale_date")} for sale, _ in rows), key=lambda item: float(item["price"] or 0), reverse=True)[:5],
            "slot_values": {position: dict(values.most_common()) for position, values in slot_values.items()},
            "negative_example_count": negative,
            "observed_positive_rate": round(observed_rate, 4) if observed_rate is not None else None,
            "observed_lift_vs_dataset": round(lift, 3) if lift is not None else None,
            "confidence": confidence,
            "evidence_score": evidence_score,
            "structural_specificity": round(specificity, 3),
        })
    templates.sort(key=lambda row: (-row["evidence_score"], -row["sale_count"], -row["median_price"], row["template"]))
    cohorts = {}
    for label, low, high in (("wholesale_100_1000", 100, 1000), ("retail_1000_5000", 1000, 5000), ("premium_5000_25000", 5000, 25000), ("above_25000", 25000, float("inf"))):
        cohort = [sale for sale in sales if low <= float(sale.get("sale_price") or 0) < high]
        cohorts[label] = {"sale_count": len(cohort), "median_price": round(statistics.median([float(sale["sale_price"]) for sale in cohort]), 2) if cohort else None}
    return {
        "niche": niche,
        "sale_count": len(sales),
        "classified_sale_count": total_sales,
        "control_count": len(controls),
        "baseline_observed_positive_rate": round(baseline, 4) if baseline is not None else None,
        "templates": templates,
        "price_cohorts": cohorts,
        "limitations": [
            "Sales-only data describes observed winners but does not estimate sell-through probability." if not controls else "Control comparisons are observational and depend on comparable sampling.",
            "Price-cohort conclusions are limited by the ranges present in the supplied export.",
        ],
    }


def generate_from_grammar(report: dict, niche: str, sold_domains=None, limit=250, minimum_support=2) -> list[dict]:
    from devspace_domain_research.scorer import (
        action_word_hits, has_obvious_buyer, has_trademark_risk,
        low_trust_token_count, score_brand, score_resale_likelihood,
    )

    sold = {normalize_domain(domain) for domain in (sold_domains or [])}
    configured = NICHE_CONFIG[niche]
    defaults = {
        "niche_keyword": list(configured["money_terms"]),
        **{category: [term.replace(" ", "") for term in terms] for category, terms in GRAMMAR_LEXICON.items()},
    }
    candidates, seen = [], set()
    brandable_stopwords = {"com", "net", "org", "www", "the"}

    def compatible(tokens, slots):
        for index, slot in enumerate(slots[:-1]):
            if slot != "niche_keyword" or slots[index + 1] != "service":
                continue
            keyword, service = tokens[index], tokens[index + 1]
            if service in {"rate", "rates", "quote", "quotes", "help"} and keyword not in {"loan", "mortgage", "refinance"}:
                return False
            if service in {"service", "services", "solution", "solutions"} and keyword == "loans":
                return False
        return True

    for grammar in report.get("templates", []):
        if grammar["sale_count"] < minimum_support:
            continue
        choices = []
        for index, slot in enumerate(grammar["slots"]):
            observed = list((grammar.get("slot_values", {}).get(str(index)) or {}).keys())
            choices.append((defaults.get(slot, []) + observed)[:8])
        extension = max(grammar.get("extensions", {"com": 1}), key=grammar.get("extensions", {"com": 1}).get)
        for tokens in product(*choices):
            if not compatible(tokens, grammar["slots"]):
                continue
            if any(slot == "brandable" and (not token.isalpha() or token in brandable_stopwords or len(token) < 2) for token, slot in zip(tokens, grammar["slots"])):
                continue
            domain = f"{''.join(tokens)}.{extension}"
            if domain in sold or domain in seen:
                continue
            seen.add(domain)
            second_level = domain.rsplit(".", 1)[0]
            brand_score = score_brand(domain, niche)
            name_quality = score_resale_likelihood(domain, niche, brand_score)
            if has_trademark_risk(second_level) or low_trust_token_count(second_level) or len(second_level) > 22:
                continue
            commercial = min(100, (65 if has_obvious_buyer(second_level, niche) else 0) + (25 if action_word_hits(second_level) else 0) + (10 if extension == "com" else 0))
            candidates.append({
                "domain": domain,
                "source": "grammar_generated",
                "niche": niche,
                "grammar_template": grammar["template"],
                "grammar_evidence_score": grammar["evidence_score"],
                "grammar_confidence": grammar["confidence"],
                "grammar_supporting_sales": grammar["sale_count"],
                "grammar_median_price": grammar["median_price"],
                "grammar_representative_sales": grammar["representative_sales"],
                "grammar_structural_specificity": grammar["structural_specificity"],
                "name_quality_score": name_quality,
                "commercial_intent_score": commercial,
                "generation_score": round(grammar["evidence_score"] * .35 + name_quality * .25 + commercial * .2 + grammar["structural_specificity"] * 20),
            })
    return sorted(candidates, key=lambda row: (-row["generation_score"], -row["grammar_evidence_score"], -row["name_quality_score"], row["domain"]))[:limit]
