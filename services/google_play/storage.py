"""Historical snapshots in the existing SQLite database file."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
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
                    provider TEXT NOT NULL, candidate_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS google_play_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
                    niche_key TEXT NOT NULL, captured_at TEXT NOT NULL,
                    score REAL NOT NULL, confidence REAL NOT NULL, snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES google_play_search_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_google_play_snapshot_niche
                    ON google_play_snapshots(niche_key, captured_at);
            """)

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

    def history(self, niche: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT captured_at, score, confidence, snapshot_json FROM google_play_snapshots "
                              "WHERE niche_key=? ORDER BY captured_at", (niche.lower().strip(),)).fetchall()
        return [{"captured_at": r[0], "score": r[1], "confidence": r[2], "snapshot": json.loads(r[3])} for r in rows]
