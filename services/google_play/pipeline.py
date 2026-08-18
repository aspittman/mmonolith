"""Orchestration entry point for the independent service."""
from __future__ import annotations

from dataclasses import dataclass

import config as root_config

from .analyzer import analyze_all
from .config import GooglePlayConfig
from .providers import GooglePlayProvider, JSONFixtureProvider
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
        self.provider = provider or JSONFixtureProvider(self.settings.fixture_path)
        self.storage = storage or GooglePlayStorage(root_config.DATABASE_PATH)

    def run(self) -> GooglePlayRun:
        niches = self.provider.discover(self.settings.countries, self.settings.review_sample_size)
        candidates = analyze_all(niches, self.settings)
        report = build_report(candidates, self.provider.name)
        path = write_report(report, self.settings.output_dir)
        run_id = None
        if self.settings.historical_tracking:
            self.storage.initialize()
            run_id = self.storage.save_run(self.provider.name, candidates, report["generated_at"])
        return GooglePlayRun(report, str(path), run_id)
