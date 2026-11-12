"""Inspect preservation inputs without executing project code or exposing matches."""
from pathlib import Path
import base64
import datetime
import hashlib
import json
import re
import subprocess
import sys

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
ROOTS = [
    'logs/ci/2026-11-12/cloud-epic2-recovery-25',
    'logs/ci/2026-11-12/b-route-source-audit/cloud-singlecap-audit-20261112',
    'logs/ci/2026-11-12/b-route-planning-input/sc25',
]
INITIAL = [
    'docs/handoff/2026-11-11/archive/uncommitted-r22/_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml',
    'docs/handoff/2026-11-11/archive/uncommitted-r60/docs/workflows/mvg-integration-acceptance.md',
    'workflow.md',
]
patterns = {
    'openai_key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}',
    'jwt': rb'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
    'credential_json_value': rb'"(?:access_token|refresh_token|id_token|client_secret|password)"\s*:\s*"[^"\s]{16,}"',
    'github_token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'bearer_value': rb'(?i)\bBearer\s+[A-Za-z0-9_+=./-]{25,}',
    'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'aws_access_key': rb'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',
    'signed_url': rb'(?i)[?&](?:X-Amz-Signature|X-Goog-Signature|sig|token)=[A-Za-z0-9%_+/=-]{20,}',
}
email_pattern = rb'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'
account_keys = {'email', 'account_id', 'accountid', 'chatgpt_account_id', 'user_email', 'user_id', 'userid'}
issues = []
privacy = []
decoded_count = 0

def scan(raw, name, depth=0):
    global decoded_count
    for category, pattern in patterns.items():
        if re.search(pattern, raw):
            issues.append({'path': name, 'category': category, 'decoded_depth': depth})
    emails = set(re.findall(email_pattern, raw))
    if emails:
        privacy.append({'path': name, 'category': 'email_candidates', 'count': len(emails),
                        'fingerprints': sorted(hashlib.sha256(x.lower()).hexdigest() for x in emails)})
    if depth >= 4:
        return
    values = []
    try:
        values.append(json.loads(raw))
    except (ValueError, UnicodeError):
        for line in raw.splitlines():
            if line.startswith((b'{', b'[')):
                try:
                    values.append(json.loads(line))
                except (ValueError, UnicodeError):
                    pass
    while values:
        value = values.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in account_keys and item not in (None, '', [], {}):
                    privacy.append({'path': name, 'category': 'nonempty_account_identity_field',
                                    'field': key, 'decoded_depth': depth})
                if isinstance(item, str) and ('base64' in key.lower() or key.lower().endswith('_b64')):
                    try:
                        decoded = base64.b64decode(item, validate=True)
                    except (ValueError, UnicodeError):
                        continue
                    decoded_count += 1
                    scan(decoded, name + ':' + key, depth + 1)
                elif isinstance(item, (dict, list)):
                    values.append(item)
        elif isinstance(value, list):
            values.extend(x for x in value if isinstance(x, (dict, list)))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)

names = set()
for root in ROOTS:
    names.update(str(p.relative_to(REPO)) for p in (REPO / root).rglob('*') if p.is_file())
names.update(x.decode() for x in git('diff', '--name-only', '-z', 'HEAD').split(b'\0') if x)
names.update(x.decode() for x in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x)
names.difference_update(INITIAL)
for name in INITIAL:
    assert (REPO / name).read_bytes() == git('show', '0c4d16c1:' + name)
branch = git('branch', '--show-current').decode().strip()
assert branch == 'build/cloud-epic2-recovery-20261111'
assert git('remote', 'get-url', 'origin').decode().strip() == 'https://github.com/skyoxu/newrouge.git'
identities = {}
for name in sorted(names):
    p = REPO / name
    assert p.is_file() and not p.is_symlink()
    assert p.name not in {'auth.json', '.env', 'credentials', 'id_rsa', 'id_ed25519'}
    raw = p.read_bytes()
    scan(raw, name)
    identities[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
report = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'branch': branch, 'HEAD': git('rev-parse', 'HEAD').decode().strip(),
          'scope': 'Uncommitted preservation inputs only; no private authentication files or environment values read',
          'excluded_preexisting_raw_unchanged': INITIAL,
          'files': len(identities), 'total_bytes': sum(x['bytes'] for x in identities.values()),
          'decoded_protocol_buffers_scanned': decoded_count,
          'sensitive_pattern_matches': issues, 'privacy_candidates': privacy, 'identities': identities}
filename = sys.argv[1]
assert re.fullmatch(r'[a-z0-9-]+\.json', filename)
with (OUT / filename).open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps({k: v for k, v in report.items() if k != 'identities'}, indent=2))
assert not issues, 'Potential sensitive content requires review; matching values deliberately omitted'
