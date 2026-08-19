"""Watch/discovery orchestration, bounded expansion, persistence, and routing."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import config as root_config

from .analyzer import analyze_family, qualifies
from .config import TrendsConfig
from .families import group_families
from .models import AttentionPoint, GeoInterest, ProviderTrend, RelatedQuery
from .providers import DataForSEOProvider, ManualJSONProvider, TrendProvider
from .reporting import build_report, write_report
from .storage import TrendsStorage


@dataclass
class TrendsRun:
    report: dict
    report_path: str
    run_id: int | None


def _deserialize(raw: dict) -> ProviderTrend:
    return ProviderTrend(topic=raw["topic"], source=raw["source"],
                         history=[AttentionPoint(**p) for p in raw.get("history", [])],
                         related_queries=[RelatedQuery(**q) for q in raw.get("related_queries", [])],
                         geo_interest=[GeoInterest(**g) for g in raw.get("geo_interest", [])],
                         category=raw.get("category", ""), competition_level=raw.get("competition_level"),
                         competition_velocity=raw.get("competition_velocity"), sample_size=raw.get("sample_size"),
                         metadata=raw.get("metadata", {}))


class TrendsService:
    def __init__(self, settings: TrendsConfig | None = None,
                 providers: list[TrendProvider] | None = None,
                 storage: TrendsStorage | None = None):
        self.settings = settings or TrendsConfig.from_env()
        if providers is not None:
            self.providers = providers
        elif self.settings.dataforseo_login and self.settings.dataforseo_password:
            self.providers = [DataForSEOProvider(self.settings.dataforseo_login,
                self.settings.dataforseo_password, self.settings.service_keywords,
                self.settings.dataforseo_location_code, self.settings.dataforseo_language_code,
                self.settings.provider_timeout_seconds)]
        else:
            self.providers = [ManualJSONProvider(self.settings.fixture_path)]
        self.storage = storage or TrendsStorage(root_config.DATABASE_PATH)
        self.logger = logging.getLogger("trends")

    def _fetch(self, provider: TrendProvider, run_id: int, now: str, cadence: str) -> tuple[list[ProviderTrend], list[dict]]:
        cfg = self.settings
        cache_key = f"{provider.name}:{cadence}:{','.join(cfg.countries)}:{','.join(cfg.watch_topics)}"
        cached = self.storage.cached(cache_key, cfg.cache_ttl_hours) if cfg.historical_tracking else None
        if cached is not None:
            return [_deserialize(item) for item in cached], []
        records, failures = [], []
        try:
            if cfg.watch_mode_enabled:
                records.extend(provider.fetch_history(cfg.watch_topics, cfg.countries,
                    {"short": cfg.short_window, "medium": cfg.medium_window, "long": cfg.long_window}))
            # Daily discovery is cheap; weekly/monthly also refresh watched history above.
            if cfg.discovery_mode_enabled:
                records.extend(provider.fetch_trending(cfg.countries, cfg.categories, cfg.max_discovery_topics))
            # Exact duplicates can occur when a watched fixture is also discoverable.
            unique = {(r.source, r.topic.lower()): provider.normalize(r) for r in records}
            records = list(unique.values())
            if cfg.historical_tracking:
                self.storage.cache(cache_key, [asdict(record) for record in records], now)
        except Exception as exc:
            self.logger.exception("trend provider failed: %s", provider.name)
            failure = {"provider": provider.name, "error": str(exc), "failed_at": now}
            failures.append(failure)
            if cfg.historical_tracking:
                self.storage.save_failure(run_id, provider.name, str(exc), now)
        return records, failures

    def _expand(self, provider: TrendProvider, seeds: list[ProviderTrend]) -> list[ProviderTrend]:
        """Evidence-led expansion only: rising provider queries above the configured signal."""
        cfg = self.settings
        if cfg.max_expansion_depth <= 0:
            return []
        children, frontier = [], seeds
        visited = {seed.topic.lower() for seed in seeds}
        for _depth in range(cfg.max_expansion_depth):
            candidates = []
            for seed in frontier:
                rising = sorted((query for query in seed.related_queries if query.rising and
                                 query.value >= cfg.minimum_child_signal), key=lambda q: q.value, reverse=True)
                candidates.extend(query.query for query in rising[:cfg.max_children_per_topic])
            candidates = [candidate for candidate in dict.fromkeys(candidates)
                          if candidate.lower() not in visited]
            candidates = candidates[:max(0, cfg.max_discovery_topics - len(children))]
            if not candidates:
                break
            visited.update(candidate.lower() for candidate in candidates)
            try:
                frontier = provider.fetch_history(candidates, cfg.countries,
                    {"short": cfg.short_window, "medium": cfg.medium_window, "long": cfg.long_window})
                children.extend(frontier)
            except Exception as exc:
                self.logger.warning("bounded expansion failed for %s: %s", provider.name, exc)
                break
        return children

    def run(self, cadence: str = "weekly") -> TrendsRun:
        if cadence not in {"daily", "weekly", "monthly"}:
            raise ValueError("cadence must be daily, weekly, or monthly")
        cfg = self.settings
        now = datetime.now(timezone.utc).isoformat()
        run_id = None
        if cfg.historical_tracking:
            self.storage.initialize()
            mode = "+".join(name for name, enabled in (("WATCH_MODE", cfg.watch_mode_enabled),
                                                        ("DISCOVERY_MODE", cfg.discovery_mode_enabled)) if enabled)
            run_id = self.storage.start_run(cadence, mode or "NONE", len(self.providers), now)
        all_records, failures = [], []
        for provider in self.providers:
            records, provider_failures = self._fetch(provider, run_id or 0, now, cadence)
            all_records.extend(records)
            failures.extend(provider_failures)
            # Expansion runs weekly/monthly, never recursively beyond the configured first useful layer.
            if cfg.discovery_mode_enabled and cadence != "daily" and cfg.max_expansion_depth > 0:
                all_records.extend(self._expand(provider, records))
        signals = [analyze_family(group, cfg) for group in group_families(all_records)]
        signals = sorted((signal for signal in signals if qualifies(signal, cfg)),
                         key=lambda signal: (signal.demand_opportunity_score or signal.commercial_trend_score,
                                             signal.trend_confidence_score), reverse=True)
        transitions = []
        if cfg.historical_tracking and run_id is not None:
            geo = {record.topic.lower().strip(): [asdict(item) for item in record.geo_interest]
                   for record in all_records}
            transitions = self.storage.save_signals(run_id, signals, now, geo)
        demo_data = all(provider.name == "manual_json" for provider in self.providers)
        report = build_report(signals, [provider.name for provider in self.providers], cadence, transitions,
                              failures, demo_data=demo_data)
        path = write_report(report, cfg.output_dir)
        return TrendsRun(report, str(path), run_id)
