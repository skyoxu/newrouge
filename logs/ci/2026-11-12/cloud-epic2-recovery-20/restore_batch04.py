"""Receive the specifically authorized historical originals as isolated DATA."""
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import stat
import subprocess
import zipfile

REPO=Path('/workspace/newrouge');OUT=Path(__file__).absolute().parent
COMMIT='94761e6caca45061d36a260f6c3116cb83a56530'
PREFIX='logs/migration/2026-11-12/recovery-batch04/'
ROOT=Path('/workspace/newrouge-recovery-data/batch04-94761e6c')
ROOT.mkdir(exist_ok=False);transport=ROOT/'transport';transport.mkdir();data=ROOT/'data';data.mkdir()
objects=[]
for name in ('README.md','MANIFEST.json','history-files.zip'):
 raw=subprocess.check_output(['git','show',COMMIT+':'+PREFIX+name],cwd=REPO)
 (transport/name).write_bytes(raw)
 objects.append({'path':PREFIX+name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
  'git_blob':subprocess.check_output(['git','rev-parse',COMMIT+':'+PREFIX+name],cwd=REPO,text=True).strip()})
manifest=json.loads((transport/'MANIFEST.json').read_bytes());raw=(transport/'history-files.zip').read_bytes()
assert len(raw)==171350==manifest['archive']['size_bytes']
assert hashlib.sha256(raw).hexdigest()=='664e6f1ba102877d9fbcf5a3cf0536504a537d7740e4e0fcd7c2aa784d4b78ac'==manifest['archive']['sha256']
expected=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-12/MINIMAL_SUPPLEMENT.json').read_bytes())['required_remaining_producer_inputs']
expected={r['original_task_relative_path']:r['expected_sha256'] for r in expected}
files={r['archive_path']:r for r in manifest['files']}
assert set(files)==set(expected) and len(files)==12
verified=[]
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 names=[i.filename for i in z.infolist() if not i.is_dir()]
 assert len(names)==13 and set(names)==set(files)|{'FILE_INDEX.json'}
 embedded=json.loads(z.read('FILE_INDEX.json'))
 assert embedded['files']==manifest['files']
 for name,row in files.items():
  rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
  info=z.getinfo(name);assert not stat.S_ISLNK(info.external_attr>>16)
  content=z.read(name);h=hashlib.sha256(content).hexdigest()
  assert len(content)==row['size_bytes'] and h==row['sha256']==expected[name]
  path=data.joinpath(*rel.parts);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
  verified.append({'original_task_relative_path':name,'data_path':str(path),'bytes':len(content),'sha256':h})
 (transport/'FILE_INDEX.json').write_bytes(z.read('FILE_INDEX.json'))
assert sum(r['bytes'] for r in verified)==801947==manifest['original_bytes_total']
report={'transport_commit':COMMIT,'source_head_before':'f94847e2b7b4d5092984294b46a2905212528f30','transport_objects':objects,
 'data_directory':str(data),'archive_integrity_verified':True,'all12_independent_original_pins_verified':True,
 'original_files_verified':len(verified),'original_bytes_verified':801947,'files':verified,
 'old_code_executed':False,'owner_authentication_claimed':False,'new_authority_granted':False,
 'qualification':'Exact authorized transport/original byte receipt only; not an old-owner execution or current admission.'}
(OUT/'batch04-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('data_directory','archive_integrity_verified','all12_independent_original_pins_verified','original_bytes_verified','qualification')},indent=2))
