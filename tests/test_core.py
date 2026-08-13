from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analysis.classifier import classify_service
from analysis.demand_analyzer import analyze
from analysis.pain_point_extractor import extract_pain_points
from analysis.technology_extractor import extract_technologies
from collectors.base import Observation
from crm.client import CRMClient
from storage.database import Database


class CoreTests(unittest.TestCase):
    def test_business_classification_and_separate_technology(self):
        title = "Connect Stripe payments to our existing WordPress site"
        self.assertEqual(classify_service(title, "Checkout currently fails"), "PAYMENT_INTEGRATION")
        self.assertEqual(extract_technologies(title, ""), ["Stripe", "WordPress"])
        self.assertIn("needs payment system", extract_pain_points(title, "payment integration needed"))

    def test_deduplication_and_aggregate_only_crm_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            db.initialize()
            now = datetime.now(timezone.utc)
            item = Observation(source="upwork", source_id="1", title="Stripe integration",
                               posted_at=now.isoformat(), service_category="PAYMENT_INTEGRATION",
                               technologies=["Stripe"], pain_points=["needs payment system"],
                               budget_min=500, budget_max=700)
            self.assertEqual(db.save_observations([item, item]), (1, 1))
            report = analyze(db.fetch_observations(now - timedelta(days=61)), now + timedelta(seconds=1))
            self.assertEqual(report["services"][0]["requests_7d"], 1)
            payload = CRMClient.build_payload(report)
            rendered = str(payload)
            self.assertNotIn("Stripe integration", rendered)
            self.assertNotIn("description", rendered)
            self.assertNotIn("url", rendered)


if __name__ == "__main__":
    unittest.main()
