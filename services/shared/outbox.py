"""Durable exact-payload retry scoped by service, organization and run key."""
import json
import sqlite3
from pathlib import Path


class Outbox:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS service_publications(service_id TEXT, organization_id TEXT, run_key TEXT, payload TEXT NOT NULL, record_id TEXT, PRIMARY KEY(service_id,organization_id,run_key))')

    def get(self, service, org, key):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT payload,record_id FROM service_publications WHERE service_id=? AND organization_id=? AND run_key=?', (service, org, key)).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def save(self, service, org, key, payload):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR IGNORE INTO service_publications VALUES(?,?,?,?,NULL)', (service, org, key, json.dumps(payload, allow_nan=False)))
        return self.get(service, org, key)[0]

    def acknowledge(self, service, org, key, record_id):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE service_publications SET record_id=? WHERE service_id=? AND organization_id=? AND run_key=?', (record_id, service, org, key))
