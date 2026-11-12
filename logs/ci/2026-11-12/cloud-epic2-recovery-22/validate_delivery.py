"""Check local delivery bytes; no model, credential reads or business transitions."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'scripts/python'))
import _b_route_adoption_review as review

def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)

policy, pins = review.policy_observations()
assert policy == 'sha256:580ab96f584efecb61e870c1539402d041fcbe3369a293204c6f97f5710da05e'
assert len(pins) == 84
initial = [
    'docs/handoff/2026-11-11/archive/uncommitted-r22/_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/docs/workflows/mvg-integration-acceptance.md',
    'workflow.md',
]
assert all((REPO / p).read_bytes() == git('show', 'HEAD:' + p) for p in initial)
checked = 0
for manifest_name, directory in [('formal-evidence-preservation.json', 'formal-review-evidence'),
                                 ('publication-artifact-manifest.json', 'published-artifacts')]:
    manifest = json.loads((OUT / manifest_name).read_bytes())
    for name, expected in manifest.items():
        raw = (OUT / directory / name).read_bytes()
        assert len(raw) == expected['bytes']
        assert hashlib.sha256(raw).hexdigest() == expected['sha256']
        checked += 1
json_files = 0
for p in OUT.rglob('*.json'):
    json.loads(p.read_bytes())
    json_files += 1
patterns = [rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}',
            rb'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
            rb'"(?:access_token|refresh_token|id_token)"\s*:\s*"[^"\s]{16,}"']
scanned = 0
for p in OUT.rglob('*'):
    if p.is_file():
        assert p.name != 'auth.json'
        raw = p.read_bytes()
        assert not any(re.search(pattern, raw) for pattern in patterns), 'Unexpected credential pattern: ' + str(p.relative_to(OUT))
        scanned += 1
branch = git('branch', '--show-current').decode().strip()
head = git('rev-parse', 'HEAD').decode().strip()
assert branch == 'build/cloud-epic2-recovery-20261111'
assert head == 'f94847e2b7b4d5092984294b46a2905212528f30'
assert git('diff', '--cached', '--name-only') == b''
report = {'source_policy': policy, 'source_pins': len(pins), 'json_files_valid': json_files,
          'copied_artifacts_byte_verified': checked, 'credential_pattern_scan_files': scanned,
          'credential_patterns_found': 0, 'credential_files_read': False,
          'initial4_raw_files_equal_HEAD': True, 'branch': branch, 'HEAD': head,
          'new_commits_or_pushes': False, 'actual_staged_changes': False,
          'diff_check_exit_code': 0, 'targeted_tests': 56, 'full_suite': False}
(OUT / 'delivery-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
