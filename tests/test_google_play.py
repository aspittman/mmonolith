from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.google_play.analyzer import analyze_all, analyze_niche, normalized_niche_key
from services.google_play.config import GooglePlayConfig
from services.google_play.discovery import expand_seeds, topics_from_routes
from services.google_play.models import AppRecord, NicheResearch, Opportunity, Review
from services.google_play.pipeline import GooglePlayService
from services.google_play.providers import GooglePlayProvider
from services.google_play.reviews import cluster_reviews
from services.google_play.scoring import (build_complexity_score, competition_strength_score,
                                           confidence_score, demand_score, recommendation)
from services.google_play.storage import GooglePlayStorage


def niche(**overrides) -> NicheResearch:
    app = AppRecord(package_name="x", app_name="Trade Tool", niche="Roofer estimate", keyword="roofer estimate",
                    rating=3.5, rating_count=5000, review_count=5000, install_estimate=100000,
                    subscription=True, last_updated=(datetime.now(timezone.utc) - timedelta(days=800)).isoformat(),
                    search_relevance=.35, reviews=[
                        Review("1", "Too expensive and too complicated; PDF export fails", 1),
                        Review("2", "CSV export is broken and the app crashes", 2),
                    ])
    values = dict(niche="Roofer estimate app", primary_keyword="roofer estimate", apps=[app],
                  search_interest=70, commercial_users=True, vertical_specificity=.9,
                  complexity_signals=[], source_count=2)
    values.update(overrides)
    return NicheResearch(**values)


class GooglePlayTests(unittest.TestCase):
    def test_review_clustering_extracts_themes_and_frequency(self):
        clusters = cluster_reviews(niche().apps[0].reviews)
        export = next(c for c in clusters if c["theme"] == "export problems")
        self.assertEqual(export["mentions"], 2)
        self.assertEqual(export["negative_review_percentage"], 100.0)

    def test_demand_and_competition_classification(self):
        self.assertGreater(demand_score(niche()), 45)
        strong = niche(apps=[AppRecord("a", "Leader", "x", "x", rating=4.8, rating_count=50000,
                                             install_estimate=5000000) for _ in range(3)])
        self.assertGreater(competition_strength_score(strong), competition_strength_score(niche()))

    def test_build_complexity(self):
        self.assertLess(build_complexity_score([]), build_complexity_score(["backend", "gps", "regulated"]))

    def test_recommendation_assignment(self):
        self.assertEqual(recommendation(80, 80, 30, 40), "STRONG_CANDIDATE")
        self.assertEqual(recommendation(70, 70, 90, 20), "REJECT")

    def test_confidence_increases_with_evidence(self):
        thin = niche(apps=[], source_count=1)
        self.assertGreater(confidence_score(niche()), confidence_score(thin))

    def test_scoring_and_duplicate_niche_detection(self):
        cfg = GooglePlayConfig(minimum_google_play_score=0, minimum_confidence=0)
        result = analyze_niche(niche(), cfg)
        self.assertGreater(result.google_play_score, 0)
        self.assertNotEqual(result.google_play_score, result.confidence_score)
        duplicate = niche(niche="Roofer estimate tool")
        self.assertEqual(normalized_niche_key(niche().niche), normalized_niche_key(duplicate.niche))
        self.assertEqual(len(analyze_all([niche(), duplicate], cfg)), 1)

    def test_historical_snapshots_append(self):
        cfg = GooglePlayConfig(minimum_google_play_score=0, minimum_confidence=0)
        candidate = analyze_niche(niche(), cfg)
        with tempfile.TemporaryDirectory() as directory:
            storage = GooglePlayStorage(Path(directory) / "db.sqlite3")
            storage.initialize()
            storage.save_run("fixture", [candidate], "2026-01-01T00:00:00+00:00")
            storage.save_run("fixture", [candidate], "2026-02-01T00:00:00+00:00")
            self.assertEqual(len(storage.history(candidate.niche)), 2)

    def test_seed_expansion_uses_trend_routes(self):
        routes = [{"payload": {"topic": "roof inspection", "related_queries": ["roof quote"]}}]
        seeds = expand_seeds(topics_from_routes(routes), ["calculator", "tracker"])
        self.assertIn("roof inspection calculator", seeds)
        self.assertIn("roof quote tracker", seeds)

    def test_pipeline_persists_accepted_and_rejected_research(self):
        class Provider(GooglePlayProvider):
            name = "test"
            def discover(self, countries, review_limit, seeds=None):
                return [niche(), niche(niche="No evidence", apps=[], search_interest=0)]
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "db.sqlite3"
            cfg = GooglePlayConfig(output_dir=Path(directory), historical_tracking=True,
                minimum_google_play_score=45, minimum_confidence=35,
                consume_trend_routes=False, cache_ttl_hours=0)
            run = GooglePlayService(cfg, Provider(), GooglePlayStorage(db_path)).run()
            self.assertEqual(run.report["researched_count"], 2)
            import sqlite3, json
            with sqlite3.connect(db_path) as db:
                rows = db.execute("SELECT accepted, rejection_reasons_json FROM google_play_research_snapshots ORDER BY id").fetchall()
            self.assertEqual([row[0] for row in rows], [1, 0])
            self.assertIn("score_below_gate", json.loads(rows[1][1]))

    def test_pipeline_retries_and_records_failure(self):
        class Broken(GooglePlayProvider):
            name = "broken"
            def discover(self, countries, review_limit, seeds=None):
                raise TimeoutError("temporary provider failure")
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "db.sqlite3"
            cfg = GooglePlayConfig(output_dir=Path(directory), historical_tracking=True,
                consume_trend_routes=False, provider_retries=1, cache_ttl_hours=0)
            storage = GooglePlayStorage(db_path)
            with self.assertRaises(RuntimeError):
                GooglePlayService(cfg, Broken(), storage).run()
            import sqlite3
            with sqlite3.connect(db_path) as db:
                failures = db.execute("SELECT provider, error FROM google_play_provider_failures").fetchall()
            self.assertEqual(failures[0][0], "broken")

    def test_pipeline_consumes_and_completes_trend_route(self):
        class Provider(GooglePlayProvider):
            name = "route_test"
            def discover(self, countries, review_limit, seeds=None):
                self.seeds = seeds
                return [niche()]
        with tempfile.TemporaryDirectory() as directory:
            import json, sqlite3
            from services.trends.storage import TrendsStorage
            db_path = Path(directory) / "db.sqlite3"
            trend_storage = TrendsStorage(db_path)
            trend_storage.initialize()
            with sqlite3.connect(db_path) as db:
                db.execute("INSERT INTO trend_routes (signal_id, destination, created_at, payload_json) VALUES (?, ?, ?, ?)",
                           (1, "google_play", "2026-08-01T00:00:00+00:00",
                            json.dumps({"topic": "roofer workflow", "related_queries": ["roof estimate"]})))
            provider = Provider()
            cfg = GooglePlayConfig(output_dir=Path(directory), historical_tracking=False,
                consume_trend_routes=True, cache_ttl_hours=0)
            GooglePlayService(cfg, provider, GooglePlayStorage(db_path)).run()
            self.assertIn("roofer workflow calculator", provider.seeds)
            with sqlite3.connect(db_path) as db:
                status = db.execute("SELECT status FROM trend_routes").fetchone()[0]
            self.assertEqual(status, "complete")


if __name__ == "__main__":
    unittest.main()
