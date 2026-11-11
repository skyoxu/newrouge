"""One source-defined DATA reconstruction; exact original pins decide usability."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
REPO=Path('/workspace/newrouge');sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_codec as codec
BASE=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
DATA=BASE/'data';OUT=Path(__file__).absolute().parent
DEST=BASE/'work/reconstructed-producer-output'
DEST.mkdir(exist_ok=False)
index=json.loads((BASE/'transport/FILE_INDEX.json').read_bytes())
indexed={r['archive_path']:r for r in index['original_files']}
observed=[]
def read(name):
 row=indexed[name];raw=(DATA/name).read_bytes()
 assert len(raw)==row['size_bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
 observed.append({'archive_path':name,'bytes':len(raw),'sha256':row['sha256']})
 return raw
h='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
cap=json.loads(read(f'target/logs/ci/b-route-origin-captures/{h}/capsule.json'))
partial=cap['native_capture']
origin=cap['origin_identity']['path'].replace('\\','/').replace('//','/')
handoff_raw=read('nx/logs/ci/mvg-planning/m4/handoff.json')
assert 'sha256:'+hashlib.sha256(handoff_raw).hexdigest()==partial['files'][cap['origin_identity']['path']+'\\logs\\ci\\mvg-planning\\m4\\handoff.json']
handoff=json.loads(handoff_raw)
del handoff_raw
prepared=json.loads(read('nx/'+handoff['original_prepared_ref']))
assert codec.canonical_digest(prepared)==cap['prepared_identity']['canonical_digest']
# Exact dictionary field order from the preserved R52 _capture_request source.
native={'schema_version':partial['schema_version'],'handoff':handoff,'prepared':prepared,
 'run_identity':partial['run_identity'],'source_identity':partial['source_identity'],
 'files':partial['files'],'directories':partial['directories']}
def encode(value,**kwargs):
 return json.JSONEncoder(allow_nan=False,**kwargs).iterencode(value)
canonical=hashlib.sha256()
for text in encode(native,ensure_ascii=False,sort_keys=True,separators=(',',':')):canonical.update(text.encode('utf-8'))
assert 'sha256:'+canonical.hexdigest()==partial['result_digest']
native['result_digest']=partial['result_digest']
fixed=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())['original_fixed_inputs']
pins={r['task_relative_path']:r['expected_raw_sha256'] for r in fixed}
prefix='logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/'
forms=[{'name':'reader-stdout.bin','expected_bytes':178321214,'newline':b'\r\n',
 'options':{'ensure_ascii':True,'separators':(',',':')},
 'basis':'Preserved R52 _main print(json.dumps(result, ensure_ascii=True, separators=comma/colon, allow_nan=False)); original Windows stdout newline'},
 {'name':'actual-native-capture.json','expected_bytes':180700910,'newline':b'\n',
 'options':{'ensure_ascii':False,'indent':2},
 'basis':'Referenced host raw_json: ensure_ascii=False, indent=2, allow_nan=False, one LF, binary write_new'}]
results=[]
for form in forms:
 path=DEST/(form['name']+'.candidate')
 hasher=hashlib.sha256();size=0
 with path.open('xb') as stream:
  for text in encode(native,**form['options']):
   raw=text.encode('utf-8');stream.write(raw);hasher.update(raw);size+=len(raw)
  stream.write(form['newline']);hasher.update(form['newline']);size+=len(form['newline'])
 expected=pins[prefix+form['name']]
 matches=size==form['expected_bytes'] and hasher.hexdigest()==expected
 if matches:path=path.rename(DEST/form['name'])
 results.append({'task_relative_path':prefix+form['name'],'derived_path':str(path),'expected_bytes':form['expected_bytes'],
  'actual_bytes':size,'expected_sha256':expected,'actual_sha256':hasher.hexdigest(),'exact_original_raw_match':matches,
  'source_rule':form['basis'],'reconstruction_attempts':1})
report={'schema':'newrouge.source-defined-native-output-reconstruction.v1','inputs':observed,
 'native_result_digest_matches_recorded_capsule':True,'results':results,
 'qualification':'Derived byte candidates only; exact original size/hash match required before use. No old reader, Guard, driver, native or model executed. Does not prove original held process/Job identity or grant authority.',
 'old_code_executed':False,'new_model_calls':0,'authority_granted':False}
(OUT/'native-output-reconstruction.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'native_result_digest_matches_recorded_capsule':True,'results':results},indent=2))
