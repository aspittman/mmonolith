"""Historical snapshots in the existing SQLite database file."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Opportunity


class GooglePlayStorage:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS google_play_search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL,
                    provider TEXT NOT NULL, candidate_count INTEGER NOT NULL,
                    researched_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'complete', error TEXT
                );
                CREATE TABLE IF NOT EXISTS google_play_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
                    niche_key TEXT NOT NULL, captured_at TEXT NOT NULL,
                    score REAL NOT NULL, confidence REAL NOT NULL, snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES google_play_search_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_google_play_snapshot_niche
                    ON google_play_snapshots(niche_key, captured_at);
                CREATE TABLE IF NOT EXISTS google_play_research_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
                    niche_key TEXT NOT NULL, captured_at TEXT NOT NULL,
                    accepted INTEGER NOT NULL, rejection_reasons_json TEXT NOT NULL,
                    research_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES google_play_search_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_google_play_research_niche
                    ON google_play_research_snapshots(niche_key, captured_at);
                CREATE TABLE IF NOT EXISTS google_play_provider_cache (
                    cache_key TEXT PRIMARY KEY, cached_at TEXT NOT NULL, payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS google_play_provider_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER,
                    provider TEXT NOT NULL, failed_at TEXT NOT NULL, error TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(google_play_search_runs)")}
            if "researched_count" not in columns:
                db.execute("ALTER TABLE google_play_search_runs ADD COLUMN researched_count INTEGER NOT NULL DEFAULT 0")
            if "status" not in columns:
                db.execute("ALTER TABLE google_play_search_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'")
            if "error" not in columns:
                db.execute("ALTER TABLE google_play_search_runs ADD COLUMN error TEXT")

    def save_run(self, provider: str, candidates: list[Opportunity], captured_at: str | None = None) -> int:
        timestamp = captured_at or datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("INSERT INTO google_play_search_runs (run_at, provider, candidate_count) VALUES (?, ?, ?)",
                                (timestamp, provider, len(candidates)))
            run_id = int(cursor.lastrowid)
            for candidate in candidates:
                db.execute("""INSERT INTO google_play_snapshots
                    (run_id, niche_key, captured_at, score, confidence, snapshot_json)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (run_id, candidate.niche.lower().strip(), timestamp, candidate.google_play_score,
                     candidate.confidence_score, json.dumps(candidate.as_dict())))
        return run_id

    def save_research(self, run_id: int, records: list[dict], captured_at: str) -> None:
        with sqlite3.connect(self.path) as db:
            for item in records:
                db.execute("""INSERT INTO google_play_research_snapshots
                    (run_id, niche_key, captured_at, accepted, rejection_reasons_json, research_json)
                    VALUES (?, ?, ?, ?, ?, ?)""", (run_id, item["niche"].lower().strip(), captured_at,
                    int(item["accepted"]), json.dumps(item["rejection_reasons"]), json.dumps(item)))
            db.execute("UPDATE google_play_search_runs SET researched_count=? WHERE id=?", (len(records), run_id))

    def save_failure(self, provider: str, error: str, captured_at: str, run_id: int | None = None) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO google_play_provider_failures (run_id, provider, failed_at, error) VALUES (?, ?, ?, ?)",
                       (run_id, provider, captured_at, error[:1000]))

    def cached(self, key: str, ttl_hours: int) -> dict | None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload_json FROM google_play_provider_cache WHERE cache_key=? AND cached_at>=?",
                             (key, cutoff)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, payload: dict, captured_at: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT INTO google_play_provider_cache (cache_key, cached_at, payload_json)
                VALUES (?, ?, ?) ON CONFLICT(cache_key) DO UPDATE SET
                cached_at=excluded.cached_at, payload_json=excluded.payload_json""",
                (key, captured_at, json.dumps(payload)))

    def history(self, niche: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT captured_at, score, confidence, snapshot_json FROM google_play_snapshots "
                              "WHERE niche_key=? ORDER BY captured_at", (niche.lower().strip(),)).fetchall()
        return [{"captured_at": r[0], "score": r[1], "confidence": r[2], "snapshot": json.loads(r[3])} for r in rows]
