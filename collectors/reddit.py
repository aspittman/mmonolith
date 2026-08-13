"""Read public Reddit search RSS; no login, scraping, or anti-bot bypass."""
from __future__ import annotations

import html
import re
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests

from collectors.base import BaseCollector, Observation


class RedditRSSCollector(BaseCollector):
    name = "reddit"

    def __init__(self, queries: list[str], limit: int, user_agent: str):
        self.queries, self.limit, self.user_agent = queries, limit, user_agent

    def collect(self) -> list[Observation]:
        results: dict[str, Observation] = {}
        for query in self.queries:
            url = f"https://www.reddit.com/search.rss?q={quote_plus(query)}&sort=new&t=month"
            response = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=20)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            namespace = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", namespace)[: self.limit]:
                title = entry.findtext("atom:title", default="", namespaces=namespace)
                link_node = entry.find("atom:link", namespace)
                link = link_node.get("href", "") if link_node is not None else ""
                source_id = entry.findtext("atom:id", default="", namespaces=namespace)
                source_id = source_id or Observation.stable_id(self.name, title, link)
                summary = entry.findtext("atom:content", default="", namespaces=namespace)
                summary = summary or entry.findtext("atom:summary", default="", namespaces=namespace)
                body = re.sub(r"<[^>]+>", " ", summary)
                results[source_id] = Observation(
                    source=self.name, source_id=source_id,
                    title=html.unescape(title),
                    description=html.unescape(re.sub(r"\s+", " ", body)).strip(),
                    url=link,
                    posted_at=entry.findtext("atom:published", default="", namespaces=namespace)
                    or entry.findtext("atom:updated", default="", namespaces=namespace),
                )
        return list(results.values())
