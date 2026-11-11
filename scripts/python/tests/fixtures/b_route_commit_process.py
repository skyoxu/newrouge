"""Fixed owned-TEMP process boundary for commit crash/restart tests only."""
import json
import os
from pathlib import Path
import sys
from contextlib import contextmanager
from copy import deepcopy

root = Path(sys.argv[1]).resolve()
allowed = Path(os.environ['ADOPTION_TEST_TEMP']).resolve()
if not root.is_relative_to(allowed) or root == allowed:
    raise SystemExit('Synthetic fixture must be inside owned TEMP')
for current in (root, *root.parents):
    info = current.lstat()
    if current.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise SystemExit('Synthetic fixture requires plain TEMP ancestors')
if (root / '.synthetic-story27-fixture').read_bytes() != b'owned synthetic commit fixture\n':
    raise SystemExit('Synthetic fixture marker is required')
mode = sys.argv[2]
if mode not in {'apply', 'verify', 'publish', 'read', 'recover', 'recover-inspect',
                 'crash-after-target', 'crash-after-catalog', 'compensate-crash-after-target',
                 'compensate-recover', 'resolved-inspect'}:
    raise SystemExit('Unsupported fixed synthetic fixture mode')
scripts = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(scripts), str(scripts.parent / 'sc'), *json.loads(sys.argv[3])]
import _b_route_commit as commit
import _b_route_codec as codec
import _b_route_adoption as adoption
import _b_route_adoption_review as review


@contextmanager
def synthetic_capture(repository, material, review_ref):
    """The sole replaced owner: no actual native verifier or model is invoked.

    Reconstruct only the explicit reviewed synthetic fixture, retaining actual
    source reads, frozen request checks, records, leases and every commit write.
    No qualification result or production environment switch is synthesized.
    """
    if Path(repository).resolve() != root or material['run_id'] != 'one':
        raise RuntimeError('Unexpected synthetic capture subject')
    subject = review.read_subject(root, 'OP-one')
    if 'native_capture' in subject:
        raise RuntimeError('Actual native capture is forbidden in this fixture')
    run = codec.strict_json_loads((root / 'logs/ci/mvg-planning/one/run.json').read_bytes())
    if run['schema_version'] != 'synthetic.native-lock-fixture.v1':
        raise RuntimeError('Explicit synthetic native-lock state is required')
    snapshot = adoption.Snapshot(root)
    for name, expected in subject['prepared']['inputs']['dependencies']['files'].items():
        data = snapshot.read(name, optional=expected is None)
        actual = None if data is None else codec.raw_digest(data)
        if actual != expected:
            raise RuntimeError('Changed synthetic prepared dependency')
    for reference in (material['handoff_ref'], material['protection_ref'], review_ref):
        snapshot.ref(reference)
    snapshot.handoff = snapshot.ref(material['handoff_ref'])
    snapshot.prepared = deepcopy(subject['prepared'])
    snapshot.protection = deepcopy(subject['protection'])
    snapshot.proof_paths = set(snapshot.files)
    adoption._committed(snapshot)
    yield snapshot

def checkpoint(name):
    if ((mode == 'crash-after-target' and name == 'after_target:0')
            or (mode == 'compensate-crash-after-target' and name == 'after_target:0')
            or (mode == 'crash-after-catalog' and name == 'catalog_replaced')):
        os._exit(73)

commit._checkpoint = checkpoint
adoption.capture_completed = synthetic_capture
try:
    if mode == 'read':
        result = commit.read_committed(root)
    elif mode == 'recover':
        result = commit.recover(root, operation_id='OP-one')
    elif mode == 'recover-inspect':
        result = commit.inspect_recovery(root, operation_id='OP-one')
    elif mode == 'compensate-crash-after-target':
        result = commit.execute(root, operation_id='COMP-one', stage='apply')
    elif mode == 'compensate-recover':
        result = commit.recover(root, operation_id='COMP-one')
    elif mode == 'resolved-inspect':
        result = commit.inspect_recovery(root, operation_id='OP-one')
    else:
        stage = 'apply' if mode == 'crash-after-target' else 'publish' if mode == 'crash-after-catalog' else mode
        result = commit.execute(root, operation_id='OP-one', stage=stage)
    print(json.dumps(result))
except codec.CodecError as error:
    print(json.dumps({'status': 'blocked', 'diagnostic': error.diagnostic.to_dict()}))
    raise SystemExit(2)
