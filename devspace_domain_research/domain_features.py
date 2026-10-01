import re
from urllib.parse import urlparse

from devspace_domain_research.config import CITY_TERMS, STATE_TERMS
from devspace_domain_research.niche_config import NICHE_CONFIG


COMMON_PREFIXES = ("best", "top", "fast", "local", "trusted", "affordable")
COMMON_SUFFIXES = ("pros", "pro", "experts", "expert", "quotes", "rates", "help", "services")


def normalize_domain(value: str) -> str:
    raw = str(value or "").strip().lower()
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or parsed.path.split("/", 1)[0]
    host = host.rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _known_terms() -> list[str]:
    terms = set(STATE_TERMS + CITY_TERMS)
    for config in NICHE_CONFIG.values():
        terms.update(config.get("money_terms", {}))
    terms.update(COMMON_PREFIXES)
    terms.update(COMMON_SUFFIXES)
    return sorted(terms, key=lambda item: (-len(item), item))


def segment_name(name: str) -> list[str]:
    explicit = [part for part in re.split(r"[-_\s]+", name) if part]
    if len(explicit) > 1:
        return explicit
    remaining = explicit[0] if explicit else name
    words = []
    while remaining:
        match = next((term for term in _known_terms() if remaining.startswith(term)), None)
        if match:
            words.append(match)
            remaining = remaining[len(match):]
        else:
            unknown = re.match(r"^[a-z0-9]+?(?=" + "|".join(map(re.escape, _known_terms())) + r"|$)", remaining)
            token = unknown.group(0) if unknown and unknown.group(0) else remaining
            words.append(token)
            remaining = remaining[len(token):]
    return [word for word in words if word]


def infer_niche(name: str) -> str | None:
    matches = []
    for niche, config in NICHE_CONFIG.items():
        hits = [term for term in config.get("money_terms", {}) if term in name]
        if hits:
            matches.append((max(len(term) for term in hits), niche))
    return max(matches)[1] if matches else None


def extract_domain_features(domain: str, niche: str | None = None) -> dict:
    normalized = normalize_domain(domain)
    parts = normalized.rsplit(".", 1)
    name = parts[0] if len(parts) == 2 else normalized
    extension = parts[1] if len(parts) == 2 else ""
    words = segment_name(name)
    geo_terms = [term for term in STATE_TERMS + CITY_TERMS if term in name]
    detected_niche = niche or infer_niche(name)
    niche_terms = list(NICHE_CONFIG.get(detected_niche or "", {}).get("money_terms", {}))
    keywords = [term for term in niche_terms if term in name]
    prefixes = [term for term in COMMON_PREFIXES if name.startswith(term)]
    suffixes = [term for term in COMMON_SUFFIXES if name.endswith(term)]
    return {
        "domain": normalized,
        "second_level": name,
        "extension": extension,
        "words": words,
        "word_count": len(words),
        "character_count": len(name),
        "has_hyphen": "-" in name,
        "has_number": any(character.isdigit() for character in name),
        "geo_terms": geo_terms,
        "has_geo_pattern": bool(geo_terms),
        "niche": detected_niche,
        "keywords": keywords,
        "prefixes": prefixes,
        "suffixes": suffixes,
        "commercial_terms": sorted(set(prefixes + suffixes)),
        "brandable": not ("-" in name or any(character.isdigit() for character in name)) and 5 <= len(name) <= 18,
        "plural": any(word.endswith("s") for word in words),
    }
