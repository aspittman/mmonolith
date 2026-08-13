"""Send cleaned market intelligence using the existing DevSpace bot auth pattern."""
from __future__ import annotations

import requests


class CRMClient:
    def __init__(self, base_url: str, api_secret: str, endpoint: str, timeout: int = 30):
        if not base_url or not api_secret:
            raise ValueError("CRM_BASE_URL and BOT_API_SECRET are required for CRM sync")
        self.url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        self.api_secret = api_secret
        self.timeout = timeout

    @staticmethod
    def build_payload(report: dict) -> dict:
        # DATA LEAVING BOT: only aggregate intelligence. Titles, descriptions, URLs,
        # and individual source records are intentionally never included.
        return {
            "generated_at": report["generated_at"],
            "periods": report["periods"],
            "services": [{
                key: service.get(key) for key in (
                    "category", "requests_7d", "requests_previous_7d", "requests_30d",
                    "requests_previous_30d", "percentage_of_demand_7d", "weekly_growth_pct",
                    "monthly_growth_pct", "average_budget", "median_budget", "budget_sample_count",
                    "demand_score", "opportunity_score", "confidence", "top_technologies",
                    "top_pain_points", "sources_represented",
                )
            } for service in report["services"]],
            "technologies": report["technologies"],
        }

    def sync(self, report: dict) -> dict:
        response = requests.post(
            self.url, json=self.build_payload(report),
            headers={"Authorization": f"Bearer {self.api_secret}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        if not response.content:
            return {"ok": True, "status_code": response.status_code}
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            return {"ok": True, "status_code": response.status_code}

