"""Bounded DATA search along named actual references; no directory traversal/code execution."""
import base64
import collections
import hashlib
import json
from pathlib import Path
import re

REPO=Path('/workspace/newrouge')
BASE=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
DATA=BASE/'data'
OUT=Path(__file__).absolute().parent
INDEX=json.loads((BASE/'transport/FILE_INDEX.json').read_bytes())
BY_PATH={row['archive_path']:row for row in INDEX['original_files']}
FIXED=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())['original_fixed_inputs']
TARGETS={row['expected_raw_sha256']:row['task_relative_path'] for row in FIXED}
NAMES={row['task_relative_path'] for row in FIXED}
H='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
OLD='3dc54cb21d1795b05d440e10bab6d8a9bc9d36311979ac190a7f33cc8b0d2c03'
seeds=[f'target/logs/ci/b-route-operations/operations/{H}/operation.json',
 f'target/logs/ci/b-route-operations/operations/{H}/commit.json',
 f'target/logs/ci/b-route-retained-executions/{H}/binding.json',
 f'target/logs/ci/b-route-origin-captures/{H}/capsule.json',
 f'target/logs/ci/b-route-adoption-reviews/{H}/subject.json',
 f'target/logs/ci/b-route-adoption-reviews/{H}/execution.json',
 f'target/logs/ci/b-route-adoption-reviews/{OLD}/subject.json',
 f'target/logs/ci/b-route-adoption-reviews/{OLD}/execution.json',
 f'target/logs/ci/b-route-origin-captures/{OLD}/capsule.json',
 'task/story29-host3-allocation-Root-01/config.json',
 'task/story29-host3-allocation-Root-01/Root-authority.json',
 'task/logs/ci/2026-11-09/story29-host1-retained-runtime-Root-01/runtime.json',
 'task/logs/ci/2026-11-09/story27-r52-retained-review-prepare-02/result.json',
 'task/logs/ci/2026-11-09/story27-r56-zero03-review-prepare-02/result.json',
 'task/logs/ci/2026-11-09/story27-r52-public-review-prepare-seal-01/config.json',
 'target/logs/ci/2026-11-09/b-route-protection/v15-r56-origin03-capture-01/snapshot.json',
 'target/logs/ci/2026-11-09/b-route-protection/v15-r56-origin03-capture-01/inventory.json',
 'nx/logs/ci/mvg-planning/m4/recovery/m1/record.json',
 'nx/logs/ci/mvg-planning/m4/recovery/s1/record.json']
report={'scope':'Explicit original03/producer02 operation, retained binding, capsules/reviews, linked Host3/config/runtime, protection and actual m1/s1 reference records only. No directory walk, unlinked historical expansion or arbitrary model-text evaluation.',
 'analysis_limits':{'encoded_depth':4,'decoded_bytes_per_carrier':32*1024*1024,'total_decoded_bytes':128*1024*1024},
 'seed_files':[],'decoded_carriers':[],'decoded_blobs':[],'exact_required_raw_matches':[], 'python_version_values':[],
 'required_pin_metadata':[], 'declared_sizes':[], 'limits_or_parse_omissions':[],
 'historical_code_executed':False,'model_calls':0,'authority_granted':False}
queue=collections.deque();seen=set();decoded_total=0
version_text=re.compile(r'(?<![0-9A-Za-z])\d+\.\d+\.\d+\s+\([^\r\n)]{1,500}\)\s+\[[^\r\n\]]{1,180}\]')

def digest(raw):return hashlib.sha256(raw).hexdigest()
def candidate(raw,origin):
 h=digest(raw)
 if h in TARGETS: report['exact_required_raw_matches'].append({'task_relative_path':TARGETS[h],'raw_sha256':h,'bytes':len(raw),'source':origin})

def enqueue(raw,origin,depth,kind):
 global decoded_total
 h=digest(raw);candidate(raw,origin)
 if h in seen:return
 if depth>4 or len(raw)>32*1024*1024 or depth and decoded_total+len(raw)>128*1024*1024:
  report['limits_or_parse_omissions'].append({'source':origin,'reason':'bounded_analysis_limit','bytes':len(raw),'depth':depth});return
 seen.add(h)
 if depth:
  decoded_total+=len(raw)
  report['decoded_blobs'].append({'source':origin,'sha256':h,'bytes':len(raw),'depth':depth})
  try:text=raw.decode('utf-8')
  except UnicodeError:text=None
  if text is not None:
   for match in version_text.finditer(text):
    report['python_version_values'].append({'source':origin,'value':match.group(),
        'complete_build_string':True,'decoded_text_span':[match.start(),match.end()]})
 try: value=json.loads(raw)
 except (ValueError,UnicodeError):
  lines=raw.splitlines()
  if not lines or len(lines)>20000 or not all(line.lstrip().startswith(b'{') for line in lines if line.strip()):return
  try:value=[json.loads(line) for line in lines if line.strip()]
  except (ValueError,UnicodeError):return
  kind+='->JSONL'
 if depth:report['decoded_carriers'].append({'source':origin,'raw_sha256':h,'bytes':len(raw),'depth':depth,'kind':kind})
 queue.append((value,origin,depth))

for name in seeds:
 row=BY_PATH.get(name)
 if row is None:
  report['limits_or_parse_omissions'].append({'source':name,'reason':'seed_not_in_index'});continue
 raw=(DATA/name).read_bytes();assert len(raw)==row['size_bytes'] and digest(raw)==row['sha256']
 report['seed_files'].append({'archive_path':name,'bytes':len(raw),'sha256':digest(raw)})
 enqueue(raw,name+'#',0,'JSON')

full_version=re.compile(r'^\d+\.\d+\.\d+\s+\(.{1,500}\)\s+\[.{1,180}\]$',re.S)
def pointer(parent,key):return parent+'/'+str(key).replace('~','~0').replace('/','~1')
while queue:
 value,origin,depth=queue.popleft();stack=[(value,origin)]
 while stack:
  node,where=stack.pop()
  if type(node)is dict:
   declared={k:node.get(k) for k in ('path','source','reference','raw_digest','sha256','raw_sha256','byte_count','size_bytes','bytes','length') if k in node}
   pins=[(k,v.removeprefix('sha256:')) for k,v in node.items() if type(v)is str and v.removeprefix('sha256:') in TARGETS]
   for k,h in pins:
    report['required_pin_metadata'].append({'source':pointer(where,k),'task_relative_path':TARGETS[h],'sha256':h})
    if any(type(node.get(s))is int for s in ('byte_count','size_bytes','bytes','length')):
     report['declared_sizes'].append({'source':where,'task_relative_path':TARGETS[h],'record':declared})
   linked=bool(pins) or any(type(node.get(k))is str and node[k].replace('\\','/').endswith(n) for k in ('path','source','reference') for n in NAMES)
   for k,x in node.items():
    here=pointer(where,k)
    if type(x) in (dict,list):stack.append((x,here));continue
    if type(x)is not str:continue
    if full_version.fullmatch(x) or k in ('sys.version','sys_version','python_version','interpreter_version'):
     if len(x)<1024:report['python_version_values'].append({'source':here,'value':x,'complete_build_string':bool(full_version.fullmatch(x))})
    if k.endswith('_base64') or k=='base64' or k=='data' and node.get('encoding')=='base64':
     try:raw=base64.b64decode(x,validate=True)
     except (ValueError,UnicodeError):
      report['limits_or_parse_omissions'].append({'source':here,'reason':'invalid_declared_base64'});continue
     enqueue(raw,here+' -> base64#',depth+1,'base64')
    elif k=='stdout' and x.lstrip().startswith('{'):
     enqueue(x.encode('utf-8'),here+' -> captured-JSON#',depth+1,'captured-JSON')
    elif linked and k in ('text','raw','contents','content'):
     raw=x.encode('utf-8');candidate(raw,here+' -> UTF8')
     if x.lstrip().startswith(('{','[')):enqueue(raw,here+' -> declared-JSON#',depth+1,'declared-JSON')
  elif type(node)is list:
   for i,x in enumerate(node):
    if type(x) in (dict,list):stack.append((x,pointer(where,i)))
report['unique_parsed_carriers']=len(seen)
report['decoded_bytes_total']=decoded_total
report['interpretation']='Metadata pins locate expected evidence, not the evidence bytes. A DATA match would not authenticate prior process execution. No negative claim about every unreferenced/opaque historical payload.'
(OUT/'bounded-encoded-search.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'seed_files':len(report['seed_files']),'decoded_carriers':len(report['decoded_carriers']),
 'decoded_bytes_total':decoded_total,'required_raw_matches':report['exact_required_raw_matches'],
 'full_python_values':[x for x in report['python_version_values'] if x['complete_build_string']],
 'metadata_pin_hits':len(report['required_pin_metadata']),'sizes':report['declared_sizes'],
 'omissions':report['limits_or_parse_omissions']},indent=2))
