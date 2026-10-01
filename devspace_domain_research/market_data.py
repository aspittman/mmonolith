import json
import csv
import math
from datetime import date, datetime
from pathlib import Path

from devspace_domain_research.domain_features import extract_domain_features, normalize_domain


VALUATION_TRANSACTION_TYPES = {"confirmed_sale", "verified_reported_sale", "reported_sale", "historical_chart_entry", "auction_result"}
SOURCE_TIERS = {"tier_1": 1.0, "tier_2": 0.8, "tier_3": 0.45, "tier_4": 0.1}


def parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_price(value) -> float | None:
    try:
        price = float(str(value).replace("$", "").replace(",", "").strip())
        return price if math.isfinite(price) and price > 0 else None
    except (TypeError, ValueError):
        return None


def source_quality(value) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return text if text in SOURCE_TIERS else "tier_4"


def sale_identity(record: dict) -> str:
    return "|".join((record["domain"], record["sale_date"], str(record["sale_price"]), record["currency"], record.get("source_name", "")))


def normalize_sale(row: dict) -> tuple[dict | None, list[str]]:
    flags = []
    domain = normalize_domain(row.get("domain"))
    sale_date = parse_date(row.get("sale_date"))
    price = parse_price(row.get("sale_price"))
    currency = str(row.get("currency") or "").strip().upper()
    transaction_type = str(row.get("transaction_type") or "unknown").strip().lower()
    source_name = str(row.get("source_name") or "").strip()
    if not domain or "." not in domain:
        flags.append("invalid_domain")
    if not sale_date:
        flags.append("invalid_date")
    if not price:
        flags.append("invalid_price")
    if not currency:
        flags.append("missing_currency")
    if not source_name:
        flags.append("missing_source")
    if transaction_type == "asking_price":
        flags.append("asking_price_excluded")
    if price and price >= 10_000_000:
        flags.append("suspicious_extreme_price")
    if any(flag in flags for flag in ("invalid_domain", "invalid_date", "invalid_price", "missing_currency")):
        return None, flags
    features = extract_domain_features(domain, row.get("niche") or None)
    record = {
        **dict(row),
        **features,
        "domain": domain,
        "sale_price": price,
        "currency": currency,
        "sale_date": sale_date.isoformat(),
        "marketplace": str(row.get("marketplace") or "").strip(),
        "source_name": source_name,
        "source_url": str(row.get("source_url") or "").strip() or None,
        "verified": str(row.get("verified") or "").lower() in {"1", "true", "yes"},
        "source_quality": source_quality(row.get("source_quality")),
        "transaction_type": transaction_type,
        "validation_flags": flags,
        "imported_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }
    return record, flags


def load_sales(path) -> dict:
    source = Path(path)
    if not source.exists():
        return {"records": [], "quarantined": [], "duplicates": 0, "error": f"sales data missing: {source}"}
    try:
        if source.suffix.lower() == ".json":
            raw = json.loads(source.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else raw.get("sales", [])
        else:
            with source.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
    except Exception as exc:
        return {"records": [], "quarantined": [], "duplicates": 0, "error": f"sales data unreadable: {exc}"}
    records, quarantined, seen = [], [], set()
    duplicates = 0
    for index, row in enumerate(rows, start=2):
        if not isinstance(row, dict):
            quarantined.append({"row": index, "record": row, "flags": ["invalid_record"]})
            continue
        record, flags = normalize_sale(row)
        if not record:
            quarantined.append({"row": index, "record": row, "flags": flags})
            continue
        identity = sale_identity(record)
        if identity in seen:
            duplicates += 1
            quarantined.append({"row": index, "record": row, "flags": ["duplicate"]})
            continue
        seen.add(identity)
        records.append(record)
    return {"records": records, "quarantined": quarantined, "duplicates": duplicates, "error": None}


def valuation_eligible(record: dict, currency: str = "USD", minimum_tier: int = 3) -> bool:
    return (
        record.get("transaction_type") in VALUATION_TRANSACTION_TYPES
        and record.get("currency") == currency
        and int(record.get("source_quality", "tier_4").split("_")[-1]) <= minimum_tier
    )
