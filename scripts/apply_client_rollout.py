"""Apply the reviewed staged files, refusing to overwrite concurrent changes."""
import hashlib
import json
import shutil
from pathlib import Path

stage = Path('/tmp/client-rollout')
base = Path('/home/aaron/MyBotz')
manifest = json.loads((stage/'manifest.json').read_text())
for relative, expected in manifest.items():
    target = base/relative
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if actual != expected:
        raise RuntimeError('Source changed since staging: ' + relative)
for relative in manifest:
    target = base/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage/relative, target)
print(json.dumps({'applied_files': len(manifest)}))
