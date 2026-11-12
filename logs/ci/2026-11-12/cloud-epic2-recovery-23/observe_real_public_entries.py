"""Fresh-process observations of actual publication; no execution or replay."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys
import time

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
OLD = REPO / 'logs/ci/2026-11-12/cloud-epic2-recovery-22'
formal = json.loads((OLD / 'publication-artifact-manifest.json').read_bytes())
def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in formal}

before = hashes()
assert before == {name: value['sha256'] for name,value in formal.items()}
cases = [
    ('fresh-direct-compensation-read', 'scripts/python/b_route_adoption.py', 'read', 'NativeV15Origin03Compensation01', True),
    ('fresh-dev-original-resolution-read', 'scripts/python/dev_cli.py', 'read', 'NativeV15Origin03', True),
    ('fresh-dev-compensation-recovery-inspect', 'scripts/python/dev_cli.py', 'recover-inspect', 'NativeV15Origin03Compensation01', False),
]
results = []
for name, entry, stage, operation, context in cases:
    command = [sys.executable, '-B', str(REPO / entry)]
    if entry.endswith('dev_cli.py'):
        command.append('b-route-adoption')
    command += ['--root', str(ROOT), '--stage', stage, '--operation-id', operation]
    if context:
        command.append('--context')
    started = time.monotonic()
    with (OUT / (name + '.json')).open('xb') as stdout, (OUT / (name + '.stderr')).open('xb') as stderr:
        process = subprocess.Popen(command, cwd='/tmp', stdout=stdout, stderr=stderr)
        print(json.dumps({'case':name,'pid':process.pid,'model_dispatch':False}), flush=True)
        code = process.wait()
    # dev-cli may append its command trace after the child JSON object.
    payload, decoded_end = json.JSONDecoder().raw_decode((OUT / (name + '.json')).read_text())
    row = {'case':name,'command':command,'cwd':'/tmp','exit_code':code,
           'elapsed_seconds':time.monotonic()-started,'output':name+'.json'}
    results.append(row)
    (OUT/'public-entry-progress.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(row), flush=True)
    if stage == 'read' and operation.endswith('Compensation01'):
        assert code == 0 and payload['formal_adoption'] is True
        assert payload['context']['operation_id'] == operation
        assert payload['context']['plan_refs'][0]['revision'] == 2
        assert payload['context']['receipt_ref'] == json.loads((OLD/'public-compensation-read.json').read_bytes())['context']['receipt_ref']
        assert payload['readiness'] is False and payload['runtime_verified'] is False and payload['default_b_enabled'] is False
    assert hashes() == before, 'A public observation changed retained business artifacts'
report = {'cases':results,'protected10_artifacts_unchanged':True,'new_model_calls':0,
          'business_transitions':0,'apply_or_recover_replayed':False,
          'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(OUT/'real-public-entry-observations.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
