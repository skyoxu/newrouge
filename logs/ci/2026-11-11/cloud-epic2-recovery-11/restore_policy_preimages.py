"""Restore exact pinned text preimages as DATA; no source installation or execution."""
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path('/workspace/newrouge')
OUT=Path(__file__).absolute().parent
DEST=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/policy-preimages-reconstructed')
DEST.mkdir(exist_ok=False)
REF='origin/migration/newrogue-20261111/r56-frozen-story27'
source_report=json.loads((OUT/'actual-policy-control-closure.json').read_bytes())
attrs=subprocess.check_output(['git','show',f'{REF}:.gitattributes'],cwd=REPO)
assert b'*.json    text eol=crlf' in attrs and b'scripts/** text eol=lf' in attrs
rows=[]
for row in source_report['source_schema_checks']:
 name=row['relative_path']
 raw=subprocess.check_output(['git','show',f'{REF}:{name}'],cwd=REPO)
 rule='exact_git_blob'
 candidate=raw
 if hashlib.sha256(raw).hexdigest()!=row['recorded_Host3_sha256']:
  assert name.startswith('docs/planning/b-route/schemas/') and name.endswith('.json')
  candidate=raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
  rule='git_attributes_CRLF_text_preimage'
 assert hashlib.sha256(candidate).hexdigest()==row['recorded_Host3_sha256'],name
 path=DEST/name
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_bytes(candidate)
 rows.append({'relative_path':name,'snapshot_git_blob':subprocess.check_output(['git','rev-parse',f'{REF}:{name}'],cwd=REPO,text=True).strip(),
  'snapshot_blob_sha256':hashlib.sha256(raw).hexdigest(),'preimage_rule':rule,'restored_raw_sha256':hashlib.sha256(candidate).hexdigest(),
  'recorded_Host3_sha256':row['recorded_Host3_sha256'],'matches_recorded_raw_pin':True})
report={'schema':'newrouge.original-policy-text-preimages.v1','source_snapshot':source_report['original_R56_source_snapshot'],
 'output_data_directory':str(DEST),'original_source_attributes_sha256':hashlib.sha256(attrs).hexdigest(),
 'matched_policy_preimages':len(rows),'exact_git_blobs':sum(x['preimage_rule']=='exact_git_blob' for x in rows),
 'CRLF_reconstructions':sum(x['preimage_rule']=='git_attributes_CRLF_text_preimage' for x in rows),'files':rows,
 'qualification':'Reconstructed DATA bytes match independently recorded historical source pins. Not an original filesystem copy, owner installation, old-code execution, original policy reconstruction or authentication grant.',
 'old_code_executed':False,'authority_installed':False,'original_policy_reconstructed':False,'new_authority_granted':False}
(OUT/'policy-preimages-restoration.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('output_data_directory','matched_policy_preimages','exact_git_blobs','CRLF_reconstructions','qualification')},indent=2))
