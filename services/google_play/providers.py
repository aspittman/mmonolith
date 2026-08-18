"""Replaceable data providers; no anti-bot scraping is performed here."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from .models import AppRecord, NicheResearch, Review


class GooglePlayProvider(ABC):
    name: str

    @abstractmethod
    def discover(self, countries: list[str], review_limit: int) -> list[NicheResearch]:
        """Return provider-neutral research records."""


class JSONFixtureProvider(GooglePlayProvider):
    """Credential-free adapter for authorized/manual/third-party JSON exports."""
    name = "json_fixture"

    def __init__(self, path: Path):
        self.path = path

    def discover(self, countries: list[str], review_limit: int) -> list[NicheResearch]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        output = []
        for raw_niche in payload.get("niches", []):
            apps = []
            for raw_app in raw_niche.get("apps", []):
                reviews = [Review(**r) for r in raw_app.pop("reviews", [])[:review_limit]]
                apps.append(AppRecord(**raw_app, reviews=reviews))
            output.append(NicheResearch(**{**raw_niche, "apps": apps}))
        return output


class PlayConsoleProvider(GooglePlayProvider):
    """Future first-party performance/search-term adapter boundary."""
    name = "play_console"

    def discover(self, countries: list[str], review_limit: int) -> list[NicheResearch]:
        raise NotImplementedError("Connect an authorized Google Play Console export/API here")
