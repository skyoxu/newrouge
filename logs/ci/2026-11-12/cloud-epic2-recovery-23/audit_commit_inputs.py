"""Audit exact intended worktree and decoded protocol bytes before committing."""
from pathlib import Path
import base64
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
INITIAL = {
    'docs/handoff/2026-11-11/archive/uncommitted-r22/_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/docs/workflows/mvg-integration-acceptance.md',
    'workflow.md',
}
def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)

patterns = {
    'openai_key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}',
    'jwt': rb'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
    'credential_json_value': rb'"(?:access_token|refresh_token|id_token|client_secret)"\s*:\s*"[^"\s]{16,}"',
    'github_token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'bearer_value': rb'(?i)\bBearer\s+[A-Za-z0-9_+=./-]{25,}',
    'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'aws_access_key': rb'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',
}
issues = []
decoded_count = 0
def scan(raw, name, *, depth=0):
    global decoded_count
    for kind, pattern in patterns.items():
        if re.search(pattern, raw):
            issues.append({'path': name, 'category': kind, 'decoded_depth': depth})
    if depth >= 3:
        return
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if isinstance(item, str) and ('base64' in key.lower() or key.lower().endswith('_b64')):
                    try:
                        decoded = base64.b64decode(item, validate=True)
                    except (ValueError, UnicodeError):
                        continue
                    decoded_count += 1
                    scan(decoded, name + ':' + key, depth=depth+1)
                elif isinstance(item, (dict, list)):
                    pending.append(item)
        elif isinstance(current, list):
            pending.extend(x for x in current if isinstance(x, (dict, list)))

names = [p.decode() for p in git('diff', '--name-only', '-z').split(b'\0') if p]
assert git('diff', '--cached', '--name-only') == b''
assert set(INITIAL).issubset(names)
for name in INITIAL:
    assert (REPO / name).read_bytes() == git('show', 'HEAD:' + name)
owned = sorted(set(names) - INITIAL)
identities = {}
for name in owned:
    p = REPO / name
    assert p.is_file() and not p.is_symlink()
    assert p.name != 'auth.json'
    raw = p.read_bytes()
    scan(raw, name)
    identities[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
remote = git('remote', 'get-url', 'origin').decode().strip()
parsed = urlsplit(remote)
assert not parsed.username and not parsed.password, 'Credential-bearing remote URL must not be published'
assert remote == 'https://github.com/skyoxu/newrouge.git'
report = {'branch': git('branch', '--show-current').decode().strip(),
          'HEAD': git('rev-parse', 'HEAD').decode().strip(),
          'origin': remote, 'preexisting4_raw_bytes_match_HEAD': True,
          'excluded_from_commit': sorted(INITIAL), 'intended_files': len(owned),
          'decoded_protocol_buffers_scanned': decoded_count, 'sensitive_patterns': issues,
          'secret_files_read': False, 'identities': identities}
report_name=sys.argv[1] if len(sys.argv)>1 else 'commit-input-audit.json'
assert re.fullmatch(r'[a-z0-9-]+\.json',report_name)
target=OUT/report_name
assert not target.exists(), 'An earlier audit must not be overwritten'
target.write_text(json.dumps(report, indent=2) + '\n')
assert not issues, 'Sensitive content requires review; values deliberately omitted'
assert report['branch'] == 'build/cloud-epic2-recovery-20261111'
print(json.dumps({k:v for k,v in report.items() if k != 'identities'},indent=2))
