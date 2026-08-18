"""Replaceable trend sources with failure-isolated provider boundaries."""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .models import AttentionPoint, GeoInterest, ProviderTrend, RelatedQuery


class TrendProvider(ABC):
    name: str

    @abstractmethod
    def fetch_trending(self, countries: list[str], categories: list[str], limit: int) -> list[ProviderTrend]:
        """Discover evidence-backed topics not already on a watch list."""

    @abstractmethod
    def fetch_history(self, topics: list[str], countries: list[str], windows: dict[str, int]) -> list[ProviderTrend]:
        """Fetch appendable time-series history for explicitly watched topics."""

    def fetch_related_queries(self, topic: str, limit: int) -> list[RelatedQuery]:
        return []

    def fetch_geo_interest(self, topic: str, countries: list[str]) -> list[GeoInterest]:
        return []

    def normalize(self, trend: ProviderTrend) -> ProviderTrend:
        """Provider-specific conversion; retain evidence labels and relative scale."""
        return trend


class ManualJSONProvider(TrendProvider):
    """Credential-free provider for manual, authorized, or test data imports."""
    name = "manual_json"

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("trends", [])

    def _convert(self, raw: dict) -> ProviderTrend:
        return ProviderTrend(
            topic=raw["topic"], source=raw.get("source", self.name),
            history=[AttentionPoint(**point) for point in raw.get("history", [])],
            related_queries=[RelatedQuery(**query) for query in raw.get("related_queries", [])],
            geo_interest=[GeoInterest(**geo) for geo in raw.get("geo_interest", [])],
            category=raw.get("category", ""), competition_level=raw.get("competition_level"),
            competition_velocity=raw.get("competition_velocity"), sample_size=raw.get("sample_size"),
            metadata={**raw.get("metadata", {}), "mode": raw.get("mode", "both")},
        )

    def fetch_trending(self, countries: list[str], categories: list[str], limit: int) -> list[ProviderTrend]:
        records = [self._convert(raw) for raw in self._load()
                   if raw.get("mode", "both") in {"discovery", "both"}]
        if categories:
            records = [record for record in records if record.category in categories]
        return records[:limit]

    def fetch_history(self, topics: list[str], countries: list[str], windows: dict[str, int]) -> list[ProviderTrend]:
        wanted = {topic.lower() for topic in topics}
        return [self._convert(raw) for raw in self._load()
                if raw["topic"].lower() in wanted or raw.get("mode", "both") == "watch"]


class ManualCSVProvider(TrendProvider):
    """Future CSV import boundary; JSON is preferred for nested related/geo data."""
    name = "manual_csv"

    def fetch_trending(self, countries: list[str], categories: list[str], limit: int) -> list[ProviderTrend]:
        raise NotImplementedError("Map an authorized CSV export to ProviderTrend records")

    def fetch_history(self, topics: list[str], countries: list[str], windows: dict[str, int]) -> list[ProviderTrend]:
        raise NotImplementedError("Map an authorized CSV export to ProviderTrend records")


class GoogleTrendsProvider(TrendProvider):
    """Optional pytrends adapter; unofficial and therefore isolated and conservative."""
    name = "google_trends"

    def __init__(self, timeout: int = 20, retries: int = 2, request_delay: float = 1.0):
        self.timeout, self.retries, self.request_delay = timeout, retries, request_delay
        self.logger = logging.getLogger("trends.provider.google")

    def _client(self):
        from pytrends.request import TrendReq
        return TrendReq(hl="en-US", tz=360, timeout=(5, self.timeout), retries=0)

    def fetch_trending(self, countries: list[str], categories: list[str], limit: int) -> list[ProviderTrend]:
        # There is no supported official discovery endpoint in this integration. Rising
        # related queries from watched seeds perform bounded, evidence-led expansion.
        return []

    def fetch_history(self, topics: list[str], countries: list[str], windows: dict[str, int]) -> list[ProviderTrend]:
        output = []
        geo = countries[0] if countries else ""
        for offset in range(0, len(topics), 5):
            batch = topics[offset:offset + 5]
            for attempt in range(self.retries + 1):
                try:
                    client = self._client()
                    client.build_payload(batch, timeframe="today 5-y", geo=geo)
                    frame = client.interest_over_time()
                    if frame.empty:
                        break
                    for topic in batch:
                        points = [AttentionPoint(str(index.to_pydatetime().isoformat()), float(value), "normalized")
                                  for index, value in frame[topic].items()]
                        output.append(ProviderTrend(topic=topic, source=self.name, history=points,
                                                    related_queries=self._related(client, topic),
                                                    geo_interest=self._geo(client, topic),
                                                    metadata={"index_is_absolute_volume": False}))
                    break
                except Exception as exc:
                    if attempt >= self.retries:
                        self.logger.warning("Google Trends batch failed after retries: %s", exc)
                    else:
                        time.sleep(min(2 ** attempt, 4))
            time.sleep(self.request_delay)
        return output

    def _related(self, client, topic: str) -> list[RelatedQuery]:
        try:
            data = client.related_queries().get(topic) or {}
            output = []
            for kind in ("rising", "top"):
                frame = data.get(kind)
                if frame is None:
                    continue
                output.extend(RelatedQuery(str(row["query"]), float(row["value"]), kind == "rising", "normalized")
                              for _, row in frame.head(20).iterrows())
            return output
        except Exception:
            return []

    def _geo(self, client, topic: str) -> list[GeoInterest]:
        try:
            frame = client.interest_by_region(resolution="REGION", inc_low_vol=True)
            return [GeoInterest(str(index), float(row[topic]), "region", "normalized")
                    for index, row in frame.iterrows() if float(row[topic]) > 0]
        except Exception:
            return []

    def fetch_related_queries(self, topic: str, limit: int) -> list[RelatedQuery]:
        records = self.fetch_history([topic], [""], {"long": 1825})
        return records[0].related_queries[:limit] if records else []

    def fetch_geo_interest(self, topic: str, countries: list[str]) -> list[GeoInterest]:
        records = self.fetch_history([topic], countries, {"long": 1825})
        return records[0].geo_interest if records else []
