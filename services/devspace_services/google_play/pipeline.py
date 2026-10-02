"""Orchestration entry point for the independent service."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
import time
import hashlib
import json

import config as root_config

from .analyzer import analyze_all, analyze_niche
from .config import GooglePlayConfig
from .discovery import expand_seeds, topics_from_routes
from .providers import (AuthorizedHTTPProvider, GooglePlayProvider, JSONFixtureProvider,
                        niches_from_payload)
from .reporting import build_report, write_report
from .storage import GooglePlayStorage


@dataclass
class GooglePlayRun:
    report: dict
    report_path: str
    run_id: int | None


class GooglePlayService:
    def __init__(self, settings: GooglePlayConfig | None = None,
                 provider: GooglePlayProvider | None = None,
                 storage: GooglePlayStorage | None = None):
        self.settings = settings or GooglePlayConfig.from_env()
        if provider:
            self.provider = provider
        elif self.settings.provider == "http":
            self.provider = AuthorizedHTTPProvider(self.settings.provider_url,
                self.settings.provider_api_key, self.settings.provider_timeout)
        else:
            self.provider = JSONFixtureProvider(self.settings.fixture_path)
        self.storage = storage or GooglePlayStorage(root_config.DATABASE_PATH)

    def _routes(self) -> tuple[list[dict], object | None]:
        if not self.settings.consume_trend_routes:
            return [], None
        try:
            from services.trends.storage import TrendsStorage
            route_storage = TrendsStorage(self.storage.path)
            route_storage.initialize()
            routes = route_storage.pending_routes("google_play")[:self.settings.max_route_seeds]
            return routes, route_storage
        except Exception as exc:
            logging.getLogger("google_play").warning("unable to read trend routes: %s", exc)
            return [], None

    def _discover(self, seeds: list[str]) -> list:
        cache_key = hashlib.sha256(json.dumps({"provider": self.provider.name,
            "countries": self.settings.countries, "seeds": seeds}, sort_keys=True).encode()).hexdigest()
        cached = self.storage.cached(cache_key, self.settings.cache_ttl_hours)
        if cached is not None:
            return niches_from_payload(cached, self.settings.review_sample_size)
        error = None
        for attempt in range(self.settings.provider_retries + 1):
            try:
                try:
                    records = self.provider.discover(self.settings.countries,
                                                     self.settings.review_sample_size, seeds)
                except TypeError as exc:
                    # Preserve compatibility with existing two-argument provider adapters.
                    if "positional" not in str(exc): raise
                    records = self.provider.discover(self.settings.countries,
                                                     self.settings.review_sample_size)
                self.storage.cache(cache_key, {"niches": [asdict(n) for n in records]},
                                   datetime.now(timezone.utc).isoformat())
                return records
            except Exception as exc:
                error = exc
                if attempt < self.settings.provider_retries:
                    time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"{self.provider.name} failed after retries: {error}")

    def run(self) -> GooglePlayRun:
        now = datetime.now(timezone.utc).isoformat()
        self.storage.initialize()
        routes, route_storage = self._routes()
        for route in routes:
            if route_storage: route_storage.mark_route(route["route_id"], "processing")
        topics = [*self.settings.discovery_topics, *topics_from_routes(routes)]
        seeds = expand_seeds(topics, self.settings.seed_terms)
        try:
            niches = self._discover(seeds)
        except Exception as exc:
            self.storage.save_failure(self.provider.name, str(exc), now)
            for route in routes:
                if route_storage: route_storage.mark_route(route["route_id"], "failed")
            raise
        candidates = analyze_all(niches, self.settings)
        accepted = {c.niche.lower().strip() for c in candidates}
        research = []
        for niche in niches:
            result = analyze_niche(niche, self.settings)
            reasons = []
            if result.google_play_score < self.settings.minimum_google_play_score: reasons.append("score_below_gate")
            if result.confidence_score < self.settings.minimum_confidence: reasons.append("confidence_below_gate")
            if result.competition_strength_score > self.settings.max_competition_strength: reasons.append("competition_above_ceiling")
            if result.build_complexity_score > self.settings.max_build_complexity: reasons.append("complexity_above_ceiling")
            research.append({"niche": niche.niche, "accepted": niche.niche.lower().strip() in accepted,
                             "rejection_reasons": reasons, "input": asdict(niche),
                             "analysis": result.as_dict()})
        report = build_report(candidates, self.provider.name, researched_count=len(niches),
                              seeds=seeds, failures=[])
        path = write_report(report, self.settings.output_dir)
        run_id = None
        if self.settings.historical_tracking:
            run_id = self.storage.save_run(self.provider.name, candidates, report["generated_at"])
            self.storage.save_research(run_id, research, report["generated_at"])
        for route in routes:
            if route_storage: route_storage.mark_route(route["route_id"], "complete")
        return GooglePlayRun(report, str(path), run_id)
