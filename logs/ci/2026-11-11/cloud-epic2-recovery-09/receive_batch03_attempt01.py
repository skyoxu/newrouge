"""Receive the fixed public transport as data, without importing archive code."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

COMMIT = '05f5fbf98d8727aae1837cd4d19e58d3ee70aec0'
PREFIX = 'logs/migration/2026-11-11/recovery-batch03/'
REPO = Path('/workspace/newrouge')
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
REPORT = REPO / 'logs/ci/2026-11-11/cloud-epic2-recovery-09/batch03-verification.json'
ROOT.mkdir(parents=True, exist_ok=False)
transport = ROOT / 'transport'
transport.mkdir()
objects = []

def receive(name):
    raw = subprocess.check_output(['git', 'show', f'{COMMIT}:{PREFIX}{name}'], cwd=REPO)
    (transport / name).write_bytes(raw)
    objects.append({'path': PREFIX + name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'git_blob': subprocess.check_output(['git','rev-parse',f'{COMMIT}:{PREFIX}{name}'],cwd=REPO,text=True).strip()})
    return raw

for name in ('README.md', 'MANIFEST.json', 'MISSING_AND_SCOPE.json', 'FILE_INDEX.json'):
    receive(name)
manifest = json.loads((transport/'MANIFEST.json').read_bytes())
index = json.loads((transport/'FILE_INDEX.json').read_bytes())
archive = ROOT / manifest['archive']['assembled_filename']
with archive.open('xb') as out:
    for part in manifest['archive']['parts_in_order']:
        raw = receive(part['path'])
        assert len(raw) == part['bytes'], part['path']
        assert hashlib.sha256(raw).hexdigest() == part['sha256'], part['path']
        out.write(raw)
assert archive.stat().st_size == manifest['archive']['bytes']
assert hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() == manifest['archive']['sha256']
originals = index['original_files']
derived = index['derived_files']
assert len(originals) == manifest['original_files']
assert len(derived) == manifest['derived_files']
entries = originals + derived
by_path = {e['archive_path']: e for e in entries}
assert len(by_path) == len(entries) == index['included_file_count']
data = ROOT/'data'
data.mkdir()
verified = []
with zipfile.ZipFile(archive) as z:
    files = [i for i in z.infolist() if not i.is_dir()]
    assert len(files) == len(by_path)
    assert {i.filename for i in files} == set(by_path)
    for info in files:
        rel = PurePosixPath(info.filename)
        assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in info.filename
        assert not stat.S_ISLNK(info.external_attr >> 16)
        e = by_path[info.filename]
        expected_size = e.get('size_bytes', e.get('bytes'))
        assert info.file_size == expected_size, info.filename
        dest = data.joinpath(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with z.open(info) as src, dest.open('xb') as out:
            while block := src.read(1024*1024):
                digest.update(block)
                out.write(block)
        assert digest.hexdigest() == e['sha256'], info.filename
        verified.append({'archive_path': info.filename, 'bytes': expected_size, 'sha256': digest.hexdigest()})
assert sum(e['size_bytes'] for e in originals) == manifest['original_bytes'] == index['original_bytes_total']
report = {'transport_commit': COMMIT, 'source_head_before': 'a77e8bbe55135995393f628af1791696abcbab4c',
          'data_directory': str(data), 'transport_objects': objects,
          'archive': manifest['archive'], 'original_files_verified': len(originals),
          'original_bytes_verified': manifest['original_bytes'], 'derived_files_verified': len(derived),
          'verified_files': verified, 'source_overwritten': False, 'archive_code_executed': False,
          'model_calls': 0, 'financial_transitions': 0, 'original_operation_replayed': False,
          'qualification': 'Transport and indexed bytes only; no Story, native or provider acceptance.'}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:report[k] for k in ('data_directory','original_files_verified','original_bytes_verified','derived_files_verified','qualification')}))
