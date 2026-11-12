"""Verify actual historical record relationships, never execute or mint the old owner."""
import ast
import hashlib
import json
from pathlib import Path,PureWindowsPath
import sys

sys.dont_write_bytecode=True
REPO=Path('/workspace/newrouge');sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_codec as codec
OUT=Path(__file__).absolute().parent
B3=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
B4=Path('/workspace/newrouge-recovery-data/batch04-94761e6c/data')
received=json.loads((OUT/'batch04-verification.json').read_bytes())
resolved=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-12/MINIMAL_SUPPLEMENT.json').read_bytes())['already_resolved']
files={r['original_task_relative_path']:Path(r['data_path']) for r in received['files']}
files.update({name:Path(row['path']) for name,row in resolved.items()})
pins=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())['original_fixed_inputs']
verified=[]
for row in pins:
 p=files[row['task_relative_path']]
 with p.open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
 assert h==row['expected_raw_sha256']
 verified.append({'task_relative_path':row['task_relative_path'],'path':str(p),'bytes':p.stat().st_size,'sha256':h})
assert len(verified)==15
P='logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/'
S='logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/'
def load(name):return codec.strict_json_loads(files[name].read_bytes())
config_name='logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json'
config=load(config_name);start=load(P+'reader-held-started.json');terminal=load(P+'reader-held-terminal.json')
stop=load(P+'stop.json');supervisor=load(S+'result.json')
assert config['operation_id']=='NativeV15Origin02' and config['request_ref']=='logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-02/request.json'
assert config['request_sha256']=='30b0c44c35000f5814f879266592c4d0bd3139b830dd3d782ad54448d4993413'
assert config['actual_counts']['source']==885
assert config['source_commit']=='680e4f7d2ddfd67d4b9eaa411f290fb9120a8a45'
assert config['source_overlay_sha256']=='b6d4a56b25117fa42915f510615e60e21a653fbb37572aa1346428d0aef83b33'
assert supervisor['transport_complete'] is True and supervisor['terminal_known'] is True
assert supervisor['actual_original_held_child_exit_code']==1 and supervisor['child_pid']==8468
assert supervisor['original_program_and_control_pins_unchanged'] is True and supervisor['automatic_retry'] is False
assert start['pid']==32180 and start['birth_filetime']==134387081439910300
assert start['Popen_audit'] is True and start['CreateProcess_audit'] is True and start['identity_error'] is None
rows=terminal['children'];assert len(rows)==1
for key in ('pid','held_handle','birth_filetime','image','identity_error','Popen_audit','CreateProcess_audit'):assert rows[0][key]==start[key]
assert type(rows[0]['actual_original_held_OS_exit'])is int and rows[0]['actual_original_held_OS_exit']==0
assert rows[0]['exit_known'] is True and terminal['original_transport_returned_normally'] is True
job=terminal['Job_observations']
assert job['assign_success']==1 and job['last_active']==0 and job['zero_observed'] is True
assert job['close_success']==1 and job['errors']==[]
assert stop['passed'] is False and stop['original_owner_returncode']==2 and stop['reader_calls']==1
assert stop['operation_id']=='NativeV15Origin02' and stop['model_calls']==0
assert stop['paid_or_unknown']==80 and stop['guard_occupancy']==178 and stop['campaign_limit']==290 and stop['released']==0
blocks=stop['blocked_actions'];assert len(blocks)==2
missing=PureWindowsPath(config['target'])/'docs/planning/b-route/plans/plan-735858d844794547bfe433abfabb3bbd/1.json'
assert blocks[0]['role']=='read outside fixed or authenticated positive closure'
assert PureWindowsPath(blocks[0]['value'])==missing
assert blocks[1]['event']=='open' and blocks[1]['type']=='Denied'
H='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
binding=codec.strict_json_loads((B3/'data/target/logs/ci/b-route-retained-executions'/H/'binding.json').read_bytes())
cap=codec.strict_json_loads((B3/'data/target/logs/ci/b-route-origin-captures'/H/'capsule.json').read_bytes())
e=binding['execution'];assert e['old_reader_exit']==0 and e['old_worker_exit']==1 and e['execution_reused'] is True and e['new_native_executions']==0
assert e['raw_pins']=={row['task_relative_path']:row['expected_raw_sha256'] for row in pins}
assert e['original_parent_source_epoch']['source_manifest_raw_sha256']==hashlib.sha256(files[config_name].read_bytes()).hexdigest()
# Reconstruct the original request as DATA using recorded strings, never current paths.
request={'source_root':e['execution_epoch']['source_root'],'source_commit':e['execution_epoch']['source_commit'],
 'artifact_root':cap['origin_identity']['path'],'planner':'mvg','run_id':'m4','expected_run_raw_digest':config['run_digest'],
 'expected_handoff_ref':{'path':'logs/ci/mvg-planning/m4/handoff.json','schema_version':'newrouge.b-route-planning-handoff.v1',
 'raw_digest':'sha256:caea69f6af1d0c7e34f1e098979e38065832e35d8de9219c664f6166d3707cbf'},
 'dependency_paths':config['parent_import_paths'][2:],'reader_path':e['execution_epoch']['reader_path'],
 'reader_raw_digest':e['execution_epoch']['reader_raw_digest']}
request_raw=json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
request_digest=codec.raw_digest(request_raw)
assert request_digest==e['request_digest']
# The unchanged reader's literal prefix is read as DATA, not compiled/executed.
reader_path=B3/'work/policy-preimages-reconstructed/scripts/python/_b_route_frozen_native_reader.py'
reader_raw=reader_path.read_bytes();assert codec.raw_digest(reader_raw)==e['execution_epoch']['reader_raw_digest']
reader_ast=ast.parse(reader_raw.decode('utf-8-sig'))
prefix=next(ast.literal_eval(n.value) for n in reader_ast.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_SOURCE_ONLY_BOOTSTRAP' for t in n.targets))
reader=e['execution_epoch']['reader_path'];pin=e['execution_epoch']['reader_raw_digest']
bootstrap=prefix+('\nimport hashlib,pathlib,types\n'+'p=pathlib.Path('+repr(reader)+')\n'+'source=p.read_bytes()\n'+
 "assert 'sha256:'+hashlib.sha256(source).hexdigest()=="+repr(pin)+", 'reader_source_changed_before_execution'\n"+
 "r=types.ModuleType('_b_route_frozen_native_reader')\n"+'r.__file__=str(p)\n'+"r.__dict__['_authenticated_reader_raw_digest']="+repr(pin)+'\n'+
 'sys.modules[r.__name__]=r\n'+"exec(compile(source,str(p),'exec'),r.__dict__)\n"+'r._main()\n')
gate="import sys\nif sys.stdin.buffer.readline() != b'start\\n': raise SystemExit(2)\n"
argv=[start['image'],'-X','dev','-I','-S','-B','-c',gate+bootstrap]
argv_digest=codec.canonical_digest(argv);assert argv_digest==e['argv_digest']
# Inventory only the exact existing cold-replay references; do not collect or waive them.
available=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-12/cloud-available-raw-pins.json').read_bytes())['files']+verified
by_hash={r['sha256']:r.get('path') for r in available}
conditional=[{'task_relative_path':name,'sha256':h,'available_data_path':by_hash.get(h),'read_site':'original R56 _original_controls:203-205'} for name,h in {**config['parent_pins'],**config['prerequisite_pins']}.items()]
report={'schema':'newrouge.recorded-producer-relations-data.v1','fixed_input_pins_verified':verified,
 'historical_producer_operation_id':'NativeV15Origin02','history_consumer_operation_id':'NativeV15Origin03',
 'recorded_reader_OS_exit':0,'recorded_parent_owner_OS_exit':2,'recorded_supervised_worker_OS_exit':1,
 'recorded_reader_start_terminal_Job_relations_checked':True,'recorded_config_source_request_relations_checked':True,
 'original_request_digest_reconstructed':request_digest,'original_argv_digest_reconstructed':argv_digest,
 'matches_retained_request_and_argv_digests':True,'historical_parent_failure_preserved':True,
 'conditional_old_cold_replay_references':conditional,'conditional_reference_count':len(conditional),
 'conditional_references_currently_resolved_by_raw_pin':sum(r['available_data_path'] is not None for r in conditional),
 'original_owner_execution_authenticated_in_cloud':False,'all_original_authentication_conditions_replayed':False,
 'new_authority_granted':False,'old_source_executed':False,'new_model_calls':0,'financial_writes':0,
 'qualification':'Recorded historical observation/data relationships and exact original request/argv identities only. No current Job, live old-owner identity or complete historical authentication handle is claimed. No conditional prerequisite is silently omitted or made Epic-wide.'}
(OUT/'recorded-producer-relations.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('recorded_reader_start_terminal_Job_relations_checked','original_request_digest_reconstructed','original_argv_digest_reconstructed','recorded_reader_OS_exit','recorded_parent_owner_OS_exit','recorded_supervised_worker_OS_exit','conditional_reference_count','conditional_references_currently_resolved_by_raw_pin','new_authority_granted')},indent=2))
