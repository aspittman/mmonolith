from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.trends.analytics import (attention_acceleration, attention_velocity,
    classify_search_intent, commercial_intent_score, confidence_score,
    event_spike_probability, persistence_score, scores, trend_stage,
    trend_transition, volatility_score)
from services.trends.config import TrendsConfig
from services.trends.families import group_families, normalized_topic
from services.trends.models import (AttentionPoint, ProviderTrend, Recommendation,
                                    SearchIntent)
from services.trends.pipeline import TrendsService
from services.trends.providers import ManualJSONProvider, TrendProvider
from services.trends.storage import TrendsStorage


def points(values: list[float]) -> list[AttentionPoint]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [AttentionPoint((start + timedelta(days=7 * index)).isoformat(), value)
            for index, value in enumerate(values)]


class BrokenProvider(TrendProvider):
    name = "broken"
    def fetch_trending(self, countries, categories, limit):
        raise TimeoutError("provider timeout")
    def fetch_history(self, topics, countries, windows):
        raise TimeoutError("provider timeout")


class TrendsTests(unittest.TestCase):
    def test_velocity_distinguishes_growth_decline_and_stagnation(self):
        self.assertGreater(attention_velocity(points([10, 12, 14, 16, 18])), 0)
        self.assertLess(attention_velocity(points([90, 75, 60, 45, 30])), 0)
        self.assertLess(abs(attention_velocity(points([90, 91, 89, 90, 91]))), 5)

    def test_acceleration_is_stronger_for_accelerating_growth(self):
        steady = attention_acceleration(points([10, 12, 14, 16, 18]))
        accelerating = attention_acceleration(points([10, 11, 16, 27, 45]))
        self.assertGreater(accelerating, steady)

    def test_persistence_rewards_sustained_growth(self):
        steady = persistence_score(points([10, 14, 20, 29, 38, 47]))
        spike = persistence_score(points([10, 15, 100, 4]))
        self.assertGreater(steady, spike)

    def test_volatility_and_event_spike_detection(self):
        stable = points([90, 91, 89, 90, 91])
        spike = points([10, 12, 100, 9])
        self.assertGreater(volatility_score(spike), volatility_score(stable))
        self.assertGreater(event_spike_probability(spike, 3, 15), 75)

    def test_stage_classification(self):
        self.assertEqual(trend_stage(20, 24, 12, 75, 20, 5, 30, 10), "ACCELERATING")
        self.assertEqual(trend_stage(20, 90, -20, 60, 90, 90, 10, 4), "EVENT_SPIKE")
        self.assertEqual(trend_stage(40, -30, -10, 30, 20, 5, 40, 8), "DECLINING")
        self.assertEqual(trend_stage(90, 1, 0, 70, 5, 5, 90, 12), "SATURATED")

    def test_second_order_commercial_intent(self):
        score, related = commercial_intent_score("AI agents", [
            ("what are AI agents", 100, False), ("AI receptionist for plumbers", 80, True),
            ("AI receptionist pricing", 75, True), ("AI receptionist software", 70, True)])
        self.assertGreater(score, 65)
        self.assertIn("TRANSACTIONAL", {item["intent"] for item in related})
        self.assertEqual(classify_search_intent("CRM for dentists"), SearchIntent.VERTICAL_SPECIFIC)

    def test_commercial_score_is_separate_and_penalizes_spikes(self):
        attention, commercial = scores(90, 90, 60, 10, 95, 10, 3, 5, 20, 98)
        self.assertGreater(attention, commercial)
        good = scores(55, 35, 20, 90, 10, 70, 95, 90, 35, 5)[1]
        self.assertGreater(good, commercial)

    def test_confidence_increases_with_evidence(self):
        thin = confidence_score(3, 1, .25, .4, .4, 25, 70, 3)
        strong = confidence_score(30, 3, 1, 1, 1, 85, 10, 200)
        self.assertGreater(strong, thin)

    def test_family_grouping_and_duplicate_normalization(self):
        records = [ProviderTrend("AI receptionist", "a", points([1, 2, 3])),
                   ProviderTrend("AI receptionist pricing", "b", points([1, 3, 5])),
                   ProviderTrend("microgreens", "a", points([1, 2, 3]))]
        groups = group_families(records)
        self.assertEqual(sorted(len(group) for group in groups), [1, 2])
        self.assertEqual(normalized_topic("Roofer estimate app"), normalized_topic("roofer estimate software"))

    def test_state_transition(self):
        self.assertIsNone(trend_transition("EMERGING", "EMERGING"))
        self.assertEqual(trend_transition("EMERGING", "ACCELERATING")["current"], "ACCELERATING")

    def test_pipeline_routes_qualified_signal_and_persists_history(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = TrendsStorage(Path(directory) / "test.sqlite3")
            cfg = TrendsConfig(fixture_path=Path("data/raw/trends.example.json"),
                output_dir=Path(directory), minimum_attention_score=0,
                minimum_commercial_trend_score=0, minimum_confidence=0,
                route_score_threshold=55, route_confidence_threshold=40, cache_ttl_hours=0)
            run = TrendsService(cfg, [ManualJSONProvider(cfg.fixture_path)], storage).run("weekly")
            ai = next(signal for signal in run.report["signals"] if signal["topic"].startswith("AI receptionist"))
            celebrity = next(signal for signal in run.report["signals"] if signal["topic"].startswith("Celebrity"))
            self.assertEqual(ai["recommendation"], Recommendation.ROUTE_TO_SERVICES.value)
            self.assertIn("google_play", ai["routes"])
            self.assertEqual(celebrity["recommendation"], Recommendation.IGNORE.value)
            routes = storage.pending_routes("google_play")
            self.assertEqual(routes[0]["payload"]["topic"], ai["topic"])
            self.assertEqual(len(storage.history(ai["topic"])), 1)

    def test_provider_failure_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = TrendsConfig(output_dir=Path(directory), historical_tracking=True,
                               minimum_attention_score=0, minimum_commercial_trend_score=0,
                               minimum_confidence=0)
            run = TrendsService(cfg, [BrokenProvider()],
                                TrendsStorage(Path(directory) / "test.sqlite3")).run()
            self.assertEqual(run.report["signals"], [])
            self.assertEqual(run.report["provider_failures"][0]["provider"], "broken")


if __name__ == "__main__":
    unittest.main()
