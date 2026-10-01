"""Refresh expected hashes for changed staged files after an applied iteration."""
import hashlib
import json
from pathlib import Path

stage = Path('/tmp/client-rollout'); base = Path('/home/aaron/MyBotz')
manifest = {}
for repo in ('devspace-crm', 'decision_engine', 'devspace-one'):
    for file in (stage/repo).rglob('*'):
        if file.is_file():
            relative = file.relative_to(stage); target = base/relative
            if target.exists() and file.read_bytes() == target.read_bytes():
                continue
            manifest[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
(stage/'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'changed_staged_files': len(manifest)}))
