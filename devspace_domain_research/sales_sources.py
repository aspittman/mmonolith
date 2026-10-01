import csv
import json
import re
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from devspace_domain_research.market_data import normalize_sale, parse_date


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def mapped_value(row: dict, field: str, configured: dict, aliases: dict):
    headers = {normalized_header(key): value for key, value in row.items()}
    candidates = []
    if configured.get(field):
        candidates.append(configured[field])
    candidates.extend(aliases.get(field, []))
    for candidate in candidates:
        key = normalized_header(candidate)
        if key in headers and headers[key] not in (None, ""):
            return headers[key]
    return None


class SalesSourceAdapter(ABC):
    source_name = "unknown"
    aliases = {}

    def __init__(self, path, column_mapping=None):
        self.path = Path(path)
        self.column_mapping = column_mapping or {}

    @abstractmethod
    def rows(self) -> list[dict]:
        raise NotImplementedError

    def transform(self, row: dict) -> dict:
        return {
            field: mapped_value(row, field, self.column_mapping, self.aliases)
            for field in self.aliases
        }

    def source_reference(self, record: dict) -> dict:
        return {"source_name": self.source_name, "source_url": record.get("source_url")}

    def load(self) -> dict:
        if not self.path.exists():
            return {"records": [], "quarantined": [], "error": f"{self.source_name} file missing: {self.path}"}
        try:
            rows = self.rows()
        except Exception as exc:
            return {"records": [], "quarantined": [], "error": f"{self.source_name} file unreadable: {exc}"}
        records, quarantined = [], []
        for index, row in enumerate(rows, start=2):
            transformed = self.transform(row)
            record, flags = normalize_sale(transformed)
            if record:
                record["source_record"] = dict(row)
                record["sources"] = [self.source_reference(record)]
                records.append(record)
            else:
                quarantined.append({"source_name": self.source_name, "row": index, "record": row, "flags": flags})
        return {"records": records, "quarantined": quarantined, "error": None}


class NameBioCsvImporter(SalesSourceAdapter):
    source_name = "namebio"
    aliases = {
        "domain": ["domain", "domain name", "name"],
        "sale_price": ["price", "sale price", "amount", "sold price"],
        "currency": ["currency", "currency code"],
        "sale_date": ["date", "sale date", "sold date"],
        "marketplace": ["venue", "marketplace", "platform"],
        "transaction_type": ["transaction type", "sale status"],
        "sale_type": ["type", "sale type"],
        "source_url": ["source url", "url", "report url"],
        "niche": ["niche", "category", "industry"],
    }

    def rows(self) -> list[dict]:
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def transform(self, row: dict) -> dict:
        result = super().transform(row)
        # NameBio export "type" may describe venue/sale mechanics, not whether a
        # transaction completed. Use an explicit mapped transaction column only.
        result["transaction_type"] = result.get("transaction_type") or "reported_sale"
        result["currency"] = result.get("currency") or "USD"
        result.update({"source_name": self.source_name, "source_quality": "tier_2", "verified": False, "source_role": "broad_comparables"})
        return result


class DNJournalImporter(SalesSourceAdapter):
    source_name = "dnjournal"
    aliases = {
        "domain": ["domain", "domain name", "name"],
        "sale_price": ["price", "sale price", "amount", "sold for"],
        "currency": ["currency", "currency code"],
        "sale_date": ["date", "sale date", "report date"],
        "marketplace": ["marketplace or broker", "marketplace", "broker", "venue"],
        "source_url": ["report url", "source url", "url"],
        "reporting_period": ["reporting period", "period", "chart period"],
        "verification_status": ["verification status", "status", "sale status"],
        "transaction_type": ["transaction type", "record type", "type"],
        "niche": ["niche", "category", "industry"],
    }

    def rows(self) -> list[dict]:
        if self.path.suffix.lower() == ".json":
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else payload.get("sales", payload.get("records", []))
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def transform(self, row: dict) -> dict:
        result = super().transform(row)
        status = str(result.pop("verification_status", "") or "").strip().lower().replace(" ", "_")
        transaction = str(result.get("transaction_type") or "").strip().lower().replace(" ", "_")
        if transaction not in {"verified_reported_sale", "reported_sale", "historical_chart_entry", "asking_price", "unknown"}:
            transaction = "verified_reported_sale" if status in {"verified", "verified_reported_sale"} else "reported_sale"
        result["transaction_type"] = transaction or "reported_sale"
        result["currency"] = result.get("currency") or "USD"
        verified = status in {"verified", "verified_reported_sale", "confirmed"} or transaction == "verified_reported_sale"
        result.update({"source_name": self.source_name, "source_quality": "tier_1" if verified else "tier_2", "verified": verified, "verification_status": status or None, "source_role": "validation_and_notable_sales"})
        return result

    def source_reference(self, record: dict) -> dict:
        return {
            "source_name": self.source_name,
            "source_url": record.get("source_url"),
            "reporting_period": record.get("reporting_period"),
            "verification_status": record.get("verification_status"),
            "transaction_type": record.get("transaction_type"),
        }


def _same_marketplace(left: dict, right: dict) -> bool:
    first = normalized_header(left.get("marketplace"))
    second = normalized_header(right.get("marketplace"))
    return not first or not second or first == second


def same_transaction(left: dict, right: dict, date_tolerance_days=14) -> bool:
    if left.get("domain") != right.get("domain") or left.get("currency") != right.get("currency"):
        return False
    if abs(float(left.get("sale_price", 0)) - float(right.get("sale_price", 0))) > .01:
        return False
    left_date, right_date = parse_date(left.get("sale_date")), parse_date(right.get("sale_date"))
    return bool(left_date and right_date and abs((left_date - right_date).days) <= int(date_tolerance_days) and _same_marketplace(left, right))


def canonicalize_sales(records: list[dict], date_tolerance_days=14) -> dict:
    canonical = []
    merged_count = 0
    for incoming in records:
        match = next((record for record in canonical if same_transaction(record, incoming, date_tolerance_days)), None)
        if not match:
            copy = dict(incoming)
            copy["sources"] = list(incoming.get("sources") or [{"source_name": incoming.get("source_name"), "source_url": incoming.get("source_url")}])
            copy["source_confidence"] = "medium" if copy.get("source_quality") in {"tier_1", "tier_2"} else "low"
            canonical.append(copy)
            continue
        merged_count += 1
        known = {(item.get("source_name"), item.get("source_url")) for item in match["sources"]}
        for source in incoming.get("sources") or []:
            if (source.get("source_name"), source.get("source_url")) not in known:
                match["sources"].append(source)
        source_count = len({item.get("source_name") for item in match["sources"]})
        if source_count >= 2:
            match["source_confidence"] = "high"
            match["source_quality"] = "tier_1"
        match["verified"] = bool(match.get("verified") or incoming.get("verified"))
        match["validation_flags"] = sorted(set((match.get("validation_flags") or []) + (incoming.get("validation_flags") or [])))
        match["corroborating_source_count"] = source_count
    return {"records": canonical, "merged_duplicates": merged_count}
