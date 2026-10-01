import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path


def stable_snapshot_id(kind: str, domain: str, subject: str = "", timestamp: str | None = None) -> str:
    timestamp = timestamp or datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    value = f"{kind}|{domain.lower()}|{subject.lower()}|{timestamp}"
    return sha256(value.encode("utf-8")).hexdigest()[:24]


def append_snapshot(path, payload: dict) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    snapshot_id = payload.get("score_snapshot_id") or stable_snapshot_id(payload.get("snapshot_type", "score"), payload.get("domain", ""), payload.get("subject_id", ""), timestamp)
    row = {**payload, "score_snapshot_id": snapshot_id, "scored_at": timestamp}
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return snapshot_id
