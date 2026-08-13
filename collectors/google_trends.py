"""Optional Google Trends signal collector using the community pytrends client."""
from __future__ import annotations

from collectors.base import BaseCollector, Observation, utc_now_iso


class GoogleTrendsCollector(BaseCollector):
    name = "google_trends"

    def __init__(self, keywords: list[str], geo: str):
        self.keywords, self.geo = keywords, geo

    def collect(self) -> list[Observation]:
        from pytrends.request import TrendReq  # optional dependency, imported only when enabled

        client = TrendReq(hl="en-US", tz=360)
        results: list[Observation] = []
        # Google limits a comparison payload to five terms.
        for offset in range(0, len(self.keywords), 5):
            batch = self.keywords[offset:offset + 5]
            client.build_payload(batch, timeframe="today 3-m", geo=self.geo)
            frame = client.interest_over_time()
            if frame.empty:
                continue
            recent = frame.tail(7)
            for keyword in batch:
                value = float(recent[keyword].mean())
                results.append(Observation(
                    source=self.name,
                    source_id=f"{keyword.lower()}:{utc_now_iso()[:10]}",
                    title=keyword,
                    description=f"Google Trends relative search interest for {keyword}",
                    posted_at=utc_now_iso(), observation_type="search_interest", source_metric=value,
                ))
        return results

