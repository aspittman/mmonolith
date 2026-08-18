from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.google_play.analyzer import analyze_all, analyze_niche, normalized_niche_key
from services.google_play.config import GooglePlayConfig
from services.google_play.models import AppRecord, NicheResearch, Opportunity, Review
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


if __name__ == "__main__":
    unittest.main()
