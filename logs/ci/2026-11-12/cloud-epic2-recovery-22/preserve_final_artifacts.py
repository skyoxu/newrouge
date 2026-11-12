"""Preserve exact public and terminal artifacts without invoking domain owners."""
from pathlib import Path
import hashlib
import json

OUT = Path(__file__).resolve().parent
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
KEY = 'f1a3f32d5599f72cc20517a2f05b4ec5ad9acc8ca1331b727aee3fa8f99df864'
read = json.loads((OUT / 'public-compensation-read.json').read_bytes())
refs = list(read['formal_paths']) + [
    f'logs/ci/b-route-operations/operations/{KEY}/operation.json',
    f'logs/ci/b-route-operations/operations/{KEY}/commit.json',
    'logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.with-reviewed-repair.json',
]
manifest = {}
for name in refs:
    raw = (ROOT / name).read_bytes()
    target = OUT / 'published-artifacts' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == raw
    else:
        with target.open('xb') as stream:
            stream.write(raw)
    manifest[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
(OUT / 'publication-artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'files': len(manifest), 'bytes': sum(v['bytes'] for v in manifest.values())}))
