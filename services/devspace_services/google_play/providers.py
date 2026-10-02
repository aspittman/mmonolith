"""Replaceable data providers; no anti-bot scraping is performed here."""
from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from .models import AppRecord, NicheResearch, Review


def niches_from_payload(payload: dict, review_limit: int) -> list[NicheResearch]:
    if not isinstance(payload.get("niches"), list):
        raise ValueError("provider payload must contain a niches list")
    output = []
    for raw_niche in payload["niches"]:
        apps = []
        for raw_value in raw_niche.get("apps", []):
            raw_app = dict(raw_value)
            reviews = [Review(**r) for r in raw_app.pop("reviews", [])[:review_limit]]
            apps.append(AppRecord(**raw_app, reviews=reviews))
        output.append(NicheResearch(**{**raw_niche, "apps": apps}))
    return output


class GooglePlayProvider(ABC):
    name: str

    @abstractmethod
    def discover(self, countries: list[str], review_limit: int,
                 seeds: list[str] | None = None) -> list[NicheResearch]:
        """Return provider-neutral research records."""


class JSONFixtureProvider(GooglePlayProvider):
    """Credential-free adapter for authorized/manual/third-party JSON exports."""
    name = "json_fixture"

    def __init__(self, path: Path):
        self.path = path

    def discover(self, countries: list[str], review_limit: int,
                 seeds: list[str] | None = None) -> list[NicheResearch]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        output = niches_from_payload(payload, review_limit)
        if not seeds:
            return output
        wanted = {word.lower() for seed in seeds for word in seed.split() if len(word) > 2}
        matched = [n for n in output if wanted.intersection(
            f"{n.niche} {n.primary_keyword} {' '.join(n.related_keywords)}".lower().split())]
        return matched or output


class AuthorizedHTTPProvider(GooglePlayProvider):
    """Adapter for a licensed/internal market-research endpoint.

    POSTs provider-neutral seeds and expects the same ``{"niches": [...]}``
    schema accepted by JSONFixtureProvider. It does not scrape Google Play.
    """
    name = "authorized_http"

    def __init__(self, url: str, api_key: str = "", timeout: int = 20):
        if not url:
            raise ValueError("GOOGLE_PLAY_PROVIDER_URL is required for the http provider")
        self.url, self.api_key, self.timeout = url, api_key, timeout

    def discover(self, countries: list[str], review_limit: int,
                 seeds: list[str] | None = None) -> list[NicheResearch]:
        body = json.dumps({"countries": countries, "review_limit": review_limit,
                           "seeds": seeds or []}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return niches_from_payload(payload, review_limit)


class PlayConsoleProvider(GooglePlayProvider):
    """Future first-party performance/search-term adapter boundary."""
    name = "play_console"

    def discover(self, countries: list[str], review_limit: int,
                 seeds: list[str] | None = None) -> list[NicheResearch]:
        raise NotImplementedError("Connect an authorized Google Play Console export/API here")
