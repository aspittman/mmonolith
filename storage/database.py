"""SQLite persistence. Raw observations remain local; only aggregates leave the bot."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator

from collectors.base import Observation


def normalize_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    posted_at TEXT NOT NULL,
                    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    budget_min REAL,
                    budget_max REAL,
                    budget_type TEXT NOT NULL DEFAULT 'unknown',
                    service_category TEXT NOT NULL DEFAULT 'OTHER',
                    technologies TEXT NOT NULL DEFAULT '[]',
                    pain_points TEXT NOT NULL DEFAULT '[]',
                    location TEXT,
                    observation_type TEXT NOT NULL DEFAULT 'request',
                    source_metric REAL,
                    UNIQUE(source, source_id)
                );
                CREATE INDEX IF NOT EXISTS idx_observations_posted ON observations(posted_at);
                CREATE INDEX IF NOT EXISTS idx_observations_category ON observations(service_category);
                CREATE TABLE IF NOT EXISTS report_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    report_json TEXT NOT NULL
                );
            """)

    def save_observations(self, observations: list[Observation]) -> tuple[int, int]:
        inserted = duplicates = 0
        with self.connect() as db:
            for item in observations:
                cursor = db.execute("""
                    INSERT OR IGNORE INTO observations
                    (source, source_id, title, description, url, posted_at, budget_min, budget_max,
                     budget_type, service_category, technologies, pain_points, location,
                     observation_type, source_metric)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.source, item.source_id, item.title, item.description, item.url,
                    normalize_date(item.posted_at), item.budget_min, item.budget_max,
                    item.budget_type, item.service_category, json.dumps(item.technologies),
                    json.dumps(item.pain_points), item.location, item.observation_type, item.source_metric,
                ))
                if cursor.rowcount:
                    inserted += 1
                else:
                    duplicates += 1
        return inserted, duplicates

    def fetch_observations(self, since: datetime) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM observations WHERE posted_at >= ? ORDER BY posted_at DESC",
                (since.astimezone(timezone.utc).isoformat(),),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["technologies"] = json.loads(item["technologies"])
            item["pain_points"] = json.loads(item["pain_points"])
            output.append(item)
        return output

    def save_report(self, report: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO report_history (generated_at, report_json) VALUES (?, ?)",
                       (report["generated_at"], json.dumps(report)))

