"""Append-only trend history, transitions, failures, cache, and route queue."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analytics import trend_transition
from .models import TrendSignal


class TrendsStorage:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trend_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
                    completed_at TEXT, cadence TEXT NOT NULL, mode TEXT NOT NULL,
                    provider_count INTEGER NOT NULL, signal_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE IF NOT EXISTS trend_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, topic_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_families (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, family_key TEXT NOT NULL UNIQUE,
                    family_name TEXT NOT NULL, root_topic TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_family_members (
                    family_id INTEGER NOT NULL, member_term TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL, UNIQUE(family_id, member_term),
                    FOREIGN KEY(family_id) REFERENCES trend_families(id)
                );
                CREATE TABLE IF NOT EXISTS trend_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source_name TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL DEFAULT 'provider'
                );
                CREATE TABLE IF NOT EXISTS trend_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, topic_id INTEGER NOT NULL,
                    family_id INTEGER NOT NULL, captured_at TEXT NOT NULL, attention_level REAL NOT NULL,
                    velocity REAL NOT NULL, acceleration REAL NOT NULL, persistence REAL NOT NULL,
                    volatility REAL NOT NULL, commercial_intent REAL NOT NULL, competition REAL NOT NULL,
                    geographic_spread REAL NOT NULL, event_spike_probability REAL NOT NULL,
                    attention_score REAL NOT NULL, commercial_trend_score REAL NOT NULL,
                    confidence REAL NOT NULL, trend_stage TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES trend_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_trend_snapshots_topic_time
                    ON trend_snapshots(topic_id, captured_at);
                CREATE TABLE IF NOT EXISTS trend_source_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, topic_id INTEGER NOT NULL,
                    source_id INTEGER NOT NULL, captured_at TEXT NOT NULL, evidence_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_related_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL, query TEXT NOT NULL,
                    intent TEXT NOT NULL, value REAL NOT NULL, rising INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_geo_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL,
                    location TEXT NOT NULL, level TEXT NOT NULL, interest REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL,
                    recommendation TEXT NOT NULL, reason TEXT NOT NULL, transition_json TEXT
                );
                CREATE TABLE IF NOT EXISTS trend_routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER NOT NULL,
                    destination TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL, payload_json TEXT NOT NULL,
                    UNIQUE(signal_id, destination)
                );
                CREATE TABLE IF NOT EXISTS trend_provider_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
                    provider TEXT NOT NULL, failed_at TEXT NOT NULL, error TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trend_provider_cache (
                    cache_key TEXT PRIMARY KEY, cached_at TEXT NOT NULL, payload_json TEXT NOT NULL
                );
            """)

    def start_run(self, cadence: str, mode: str, provider_count: int, at: str) -> int:
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("INSERT INTO trend_runs (started_at, cadence, mode, provider_count) VALUES (?, ?, ?, ?)",
                                (at, cadence, mode, provider_count))
            return int(cursor.lastrowid)

    def save_failure(self, run_id: int, provider: str, error: str, at: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO trend_provider_failures (run_id, provider, failed_at, error) VALUES (?, ?, ?, ?)",
                       (run_id, provider, at, error[:1000]))

    def previous_stage(self, topic_key: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("""SELECT s.trend_stage FROM trend_snapshots s JOIN trend_topics t ON t.id=s.topic_id
                WHERE t.topic_key=? ORDER BY s.captured_at DESC, s.id DESC LIMIT 1""", (topic_key,)).fetchone()
        return row[0] if row else None

    def save_signals(self, run_id: int, signals: list[TrendSignal], captured_at: str,
                     geo_by_topic: dict[str, list[dict]] | None = None) -> list[dict]:
        transitions = []
        with sqlite3.connect(self.path) as db:
            for signal in signals:
                topic_key = signal.topic.lower().strip()
                previous = db.execute("""SELECT s.trend_stage FROM trend_snapshots s JOIN trend_topics t ON t.id=s.topic_id
                    WHERE t.topic_key=? ORDER BY s.captured_at DESC, s.id DESC LIMIT 1""", (topic_key,)).fetchone()
                transition = trend_transition(previous[0] if previous else None, signal.stage)
                db.execute("""INSERT INTO trend_topics (topic_key, display_name, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(topic_key) DO UPDATE SET
                    display_name=excluded.display_name, last_seen_at=excluded.last_seen_at""",
                    (topic_key, signal.topic, captured_at, captured_at))
                topic_id = db.execute("SELECT id FROM trend_topics WHERE topic_key=?", (topic_key,)).fetchone()[0]
                family_key = signal.family_name.lower().strip()
                db.execute("""INSERT INTO trend_families (family_key, family_name, root_topic, updated_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(family_key) DO UPDATE SET
                    family_name=excluded.family_name, root_topic=excluded.root_topic, updated_at=excluded.updated_at""",
                    (family_key, signal.family_name, signal.topic, captured_at))
                family_id = db.execute("SELECT id FROM trend_families WHERE family_key=?", (family_key,)).fetchone()[0]
                for member in signal.member_terms:
                    db.execute("INSERT OR IGNORE INTO trend_family_members (family_id, member_term, first_seen_at) VALUES (?, ?, ?)",
                               (family_id, member, captured_at))
                payload = signal.as_dict()
                cursor = db.execute("""INSERT INTO trend_snapshots
                    (run_id, topic_id, family_id, captured_at, attention_level, velocity, acceleration,
                     persistence, volatility, commercial_intent, competition, geographic_spread,
                     event_spike_probability, attention_score, commercial_trend_score, confidence,
                     trend_stage, snapshot_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_id, topic_id, family_id, captured_at, signal.attention_level,
                     signal.attention_velocity, signal.attention_acceleration, signal.persistence_score,
                     signal.volatility_score, signal.commercial_intent_score, signal.competition_score,
                     signal.geographic_spread_score, signal.event_spike_probability, signal.attention_score,
                     signal.commercial_trend_score, signal.trend_confidence_score, signal.stage,
                     json.dumps(payload)))
                snapshot_id = int(cursor.lastrowid)
                for source in signal.sources:
                    db.execute("INSERT OR IGNORE INTO trend_sources (source_name) VALUES (?)", (source,))
                    source_id = db.execute("SELECT id FROM trend_sources WHERE source_name=?", (source,)).fetchone()[0]
                    db.execute("INSERT INTO trend_source_snapshots (run_id, topic_id, source_id, captured_at, evidence_json) VALUES (?, ?, ?, ?, ?)",
                               (run_id, topic_id, source_id, captured_at, json.dumps(signal.evidence)))
                for query in signal.related_queries:
                    db.execute("INSERT INTO trend_related_queries (snapshot_id, query, intent, value, rising) VALUES (?, ?, ?, ?, ?)",
                               (snapshot_id, query["query"], query["intent"], query["value"], int(query["rising"])))
                for geo in (geo_by_topic or {}).get(topic_key, []):
                    db.execute("INSERT INTO trend_geo_snapshots (snapshot_id, location, level, interest) VALUES (?, ?, ?, ?)",
                               (snapshot_id, geo["location"], geo.get("level", "region"), geo["value"]))
                cursor = db.execute("INSERT INTO trend_signals (snapshot_id, recommendation, reason, transition_json) VALUES (?, ?, ?, ?)",
                                    (snapshot_id, signal.recommendation, signal.reason,
                                     json.dumps(transition) if transition else None))
                signal_id = int(cursor.lastrowid)
                for route in signal.routes:
                    route_payload = {"source_service": "trends", "trend_signal_id": signal_id,
                                     "topic": signal.topic, "family_name": signal.family_name,
                                     "stage": signal.stage, "attention_score": signal.attention_score,
                                     "commercial_trend_score": signal.commercial_trend_score,
                                     "confidence": signal.trend_confidence_score,
                                     "related_queries": [q["query"] for q in signal.related_queries[:10]]}
                    db.execute("INSERT OR IGNORE INTO trend_routes (signal_id, destination, created_at, payload_json) VALUES (?, ?, ?, ?)",
                               (signal_id, route, captured_at, json.dumps(route_payload)))
                if transition:
                    transitions.append({"topic": signal.topic, **transition,
                                        "commercial_trend_score": signal.commercial_trend_score,
                                        "confidence": signal.trend_confidence_score,
                                        "primary_driver": signal.reason})
            db.execute("UPDATE trend_runs SET completed_at=?, signal_count=?, status='complete' WHERE id=?",
                       (captured_at, len(signals), run_id))
        return transitions

    def cached(self, key: str, ttl_hours: int) -> list[dict] | None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload_json FROM trend_provider_cache WHERE cache_key=? AND cached_at>=?",
                             (key, cutoff)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, payload: list[dict], at: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT INTO trend_provider_cache (cache_key, cached_at, payload_json) VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET cached_at=excluded.cached_at, payload_json=excluded.payload_json""",
                       (key, at, json.dumps(payload)))

    def pending_routes(self, destination: str | None = None) -> list[dict]:
        query = "SELECT id, destination, status, payload_json FROM trend_routes WHERE status='pending'"
        params: tuple = ()
        if destination:
            query += " AND destination=?"
            params = (destination,)
        with sqlite3.connect(self.path) as db:
            rows = db.execute(query + " ORDER BY id", params).fetchall()
        return [{"route_id": row[0], "destination": row[1], "status": row[2],
                 "payload": json.loads(row[3])} for row in rows]

    def history(self, topic: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("""SELECT s.captured_at, s.trend_stage, s.snapshot_json
                FROM trend_snapshots s JOIN trend_topics t ON t.id=s.topic_id
                WHERE t.topic_key=? ORDER BY s.captured_at, s.id""", (topic.lower().strip(),)).fetchall()
        return [{"captured_at": row[0], "stage": row[1], "snapshot": json.loads(row[2])} for row in rows]
