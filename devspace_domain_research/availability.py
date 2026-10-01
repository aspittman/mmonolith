import csv
import json
from pathlib import Path

from devspace_domain_research.domain_features import normalize_domain


KNOWN_STATUSES = {"available", "unavailable", "premium", "unknown"}


class AvailabilityChecker:
    provider_name = "unconfigured"

    def check(self, domains: list[str]) -> dict[str, dict]:
        return {normalize_domain(domain): {"status": "unknown", "provider": self.provider_name} for domain in domains}


class StaticFileAvailabilityChecker(AvailabilityChecker):
    provider_name = "static_file"

    def __init__(self, path):
        self.path = Path(path)

    def _rows(self):
        if self.path.suffix.lower() == ".json":
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else payload.get("domains", payload.get("records", []))
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def check(self, domains: list[str]) -> dict[str, dict]:
        wanted = {normalize_domain(domain) for domain in domains}
        results = super().check(domains)
        if not self.path.exists():
            return results
        for row in self._rows():
            domain = normalize_domain(row.get("domain") or row.get("Domain"))
            if domain not in wanted:
                continue
            status = str(row.get("status") or row.get("availability") or "unknown").strip().lower()
            results[domain] = {
                "status": status if status in KNOWN_STATUSES else "unknown",
                "provider": self.provider_name,
                "checked_at": row.get("checked_at") or row.get("date"),
                "acquisition_price": row.get("acquisition_price") if row.get("acquisition_price") is not None else row.get("price"),
                "renewal_price": row.get("renewal_price"),
                "currency": row.get("currency"),
            }
        return results


def configured_checker(config=None) -> AvailabilityChecker:
    settings = (config or {}).get("availability") or {}
    if not settings.get("enabled"):
        return AvailabilityChecker()
    if settings.get("provider") == "static_file" and settings.get("path"):
        return StaticFileAvailabilityChecker(settings["path"])
    return AvailabilityChecker()
