"""Replaceable trend sources with failure-isolated provider boundaries."""
from __future__ import annotations

import json
import logging
import time
import base64
import urllib.request
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
                if raw["topic"].lower() in wanted]


class DataForSEOProvider(TrendProvider):
    """Pay-as-you-go Google Ads keyword metrics grouped into services people can buy."""
    name = "dataforseo_google_ads"
    endpoint = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"

    def __init__(self, login: str, password: str, service_keywords: dict[str, list[str]],
                 location_code: int = 2840, language_code: str = "en", timeout: int = 20):
        if not login or not password:
            raise ValueError("DataForSEO login and password are required")
        self.login, self.password = login, password
        self.service_keywords = service_keywords
        self.location_code, self.language_code, self.timeout = location_code, language_code, timeout

    def _request(self, keywords: list[str]) -> list[dict]:
        payload = json.dumps([{"keywords": keywords, "location_code": self.location_code,
                               "language_code": self.language_code}]).encode("utf-8")
        token = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        request = urllib.request.Request(self.endpoint, data=payload, method="POST",
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        if int(body.get("status_code", 0)) >= 40000:
            raise RuntimeError(body.get("status_message", "DataForSEO request failed"))
        tasks = body.get("tasks") or []
        if not tasks or int(tasks[0].get("status_code", 0)) >= 40000:
            message = tasks[0].get("status_message") if tasks else "missing task response"
            raise RuntimeError(f"DataForSEO request failed: {message}")
        return tasks[0].get("result") or []

    def fetch_history(self, topics: list[str], countries: list[str], windows: dict[str, int]) -> list[ProviderTrend]:
        selected = {name: keywords for name, keywords in self.service_keywords.items()
                    if not topics or name.lower() in {topic.lower() for topic in topics}}
        keywords = list(dict.fromkeys(keyword for values in selected.values() for keyword in values))
        rows = self._request(keywords) if keywords else []
        by_keyword = {str(row.get("keyword", "")).lower(): row for row in rows}
        output = []
        for service, terms in selected.items():
            matched = [by_keyword[term.lower()] for term in terms if term.lower() in by_keyword]
            months = sorted({(int(item["year"]), int(item["month"]))
                             for row in matched for item in (row.get("monthly_searches") or [])})
            history = []
            for year, month in months:
                total = sum(float(item.get("search_volume") or 0) for row in matched
                            for item in (row.get("monthly_searches") or [])
                            if int(item["year"]) == year and int(item["month"]) == month)
                history.append(AttentionPoint(f"{year:04d}-{month:02d}-01T00:00:00+00:00", total, "estimated"))
            volume = sum(float(row.get("search_volume") or 0) for row in matched)
            weighted_cpc = (sum(float(row.get("cpc") or 0) * float(row.get("search_volume") or 0)
                                for row in matched) / volume) if volume else 0.0
            weighted_competition = (sum(float(row.get("competition_index") or 0) *
                                        float(row.get("search_volume") or 0) for row in matched) / volume) if volume else 0.0
            related = [RelatedQuery(str(row.get("keyword")), float(row.get("search_volume") or 0),
                                    False, "estimated") for row in matched]
            output.append(ProviderTrend(service, self.name, history, related_queries=related,
                category="online services", competition_level=weighted_competition,
                sample_size=len(matched), metadata={"search_volume": volume,
                    "average_cpc": round(weighted_cpc, 2), "paid_competition_index": round(weighted_competition, 1),
                    "index_is_absolute_volume": True, "live_data": True,
                    "keywords_requested": len(terms), "keywords_returned": len(matched)}))
        return output

    def fetch_trending(self, countries: list[str], categories: list[str], limit: int) -> list[ProviderTrend]:
        # Discovery is deliberately bounded to configured sellable services. Keyword
        # expansion can be added through the separate keyword-ideas endpoint later.
        return []


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
