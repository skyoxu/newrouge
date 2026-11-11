"""Reconcile transport originals with existing identities; issue no authority."""
import base64
import hashlib
import json
from pathlib import Path
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
DATA=ROOT/'data'
OUT=Path('/workspace/newrouge/logs/ci/2026-11-11/cloud-epic2-recovery-09')
def load(rel):return json.loads((DATA/rel).read_bytes())
def digest(raw):return 'sha256:'+hashlib.sha256(raw).hexdigest()
index=json.loads((ROOT/'transport/FILE_INDEX.json').read_bytes())
key='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
operation=load(f'target/logs/ci/b-route-operations/operations/{key}/operation.json')
commit=load(f'target/logs/ci/b-route-operations/operations/{key}/commit.json')
binding=load(f'target/logs/ci/b-route-retained-executions/{key}/binding.json')
requests={k:{'archive_path':v['archive_path'],'actual_raw_digest':digest((DATA/v['archive_path']).read_bytes())} for k,v in index['request_versions'].items() if type(v) is dict}
assert len(set(v['actual_raw_digest'] for v in requests.values()))==3
assert base64.b64decode(operation['request_raw_base64'],validate=True)==(DATA/requests['reserved_operation_request']['archive_path']).read_bytes()
assert requests['reserved_operation_request']['actual_raw_digest']==operation['request_raw_digest']
assert requests['binding_referenced_existing_request']['actual_raw_digest']==binding['request_raw_digest']
comp=load(requests['compensation_request']['archive_path'])
assert comp['compensates']['request_raw_digest']==operation['request_raw_digest']
assert comp['compensates']['frozen_digest']==operation['frozen_digest']
actual_targets=[]
for row in operation['frozen']['targets']:
 actual=digest((DATA/'target'/row['path']).read_bytes())
 actual_targets.append({'path':row['path'],'actual':actual,'matches_after':actual==row['after_raw_digest'],'matches_before':actual==row['before_raw_digest']})
assert all(v['matches_after'] for v in actual_targets)
assert digest((DATA/'target/docs/planning/b-route/catalog.v1.json').read_bytes())==commit['catalog_after_digest']

pins=json.loads(Path('/workspace/newrouge/logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())
pin_results=[]
for row in pins['original_fixed_inputs']:
 p=DATA/'task'/row['task_relative_path']
 actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
 pin_results.append({'path':str(p.relative_to(DATA)),'expected':row['expected_raw_sha256'],'actual':actual,'matches':actual==row['expected_raw_sha256']})

run=load('nx/logs/ci/mvg-planning/m4/run.json')
registry=load('nx/logs/ci/mvg-recovery/registry.json')
prepared=run['planning_runtime']['prepared_ref']
history={}
for n in (1,2,3):
 rel=f'task/story29-host{n}-allocation-Root-01'
 config_raw=(DATA/rel/'config.json').read_bytes();config=json.loads(config_raw)
 rows=[json.loads(p.read_bytes()) for p in sorted((DATA/rel/'ledger').glob('[0-9]*.json'))]
 previous=None
 for seq,row in enumerate(rows,1):
  assert row['sequence']==seq and row['previous']==previous
  previous=row['sha256']
 assert rows[0]['event']['config_sha256']==hashlib.sha256(config_raw).hexdigest()
 history[f'Host{n}']={'config_raw_digest':digest(config_raw),'sequences':len(rows),'previous_links_consistent':True,
   'events':[row['event']['kind'] for row in rows], 'STOP_exists':(DATA/rel/'ledger/STOP.json').exists(),
   'last_paid_or_unknown':rows[-1]['event'].get('paid_or_unknown'),
   'last_guard_occupancy':rows[-1]['event']['guard_occupancy'],'released':rows[-1]['event']['released'],
   'config_base':config['base'],'meaning':'Historical records only, no current grant, physical billing or release claim.'}

report={'transport_commit':'05f5fbf98d8727aae1837cd4d19e58d3ee70aec0','requests':requests,
 'operation':{'id':operation['operation_id'],'stored_state':operation['state'],'commit_phase':commit['phase'],
  'marker_exists':(DATA/f'target/logs/ci/b-route-operations/operations/{key}/commit.pending.json').exists(),
  'targets':actual_targets,'catalog_matches_commit_after':True},
 'original_fixed_producer_pins':pin_results,'matched_fixed_producer_pins':sum(v['matches'] for v in pin_results),
 'original_fixed_producer_pin_scope':'Top-level Task-relative files only. Encoded historical containers are not searched by this selector. These rows are not declared missing proof, a published-read prerequisite, or the observed prepare failure.',
 'm4':{'phase':run['phase'],'selection_status':run['selection_status'],'checkpoint_strategy':run['checkpoint_strategy'],
  'completed_registry_epoch':registry['epoch'],'completed_registry_entries':len(registry['entries']),
  'prepared_ref':prepared,'prepared_ref_present':(DATA/'nx'/prepared).is_file(),
  'interpretation':'Selected native handoff/checkpoint exists; no registered cross-run completed unit is present. Do not auto-register or relabel intermediate state as Story2.9 adoption.'},
 'fiscal_history':history,'unit_Root02_replaced':False,'new_model_calls':0,'state_transitions':0,
 'qualification':'Static reconciliation and original-byte linkage only, not native authority, current funding or Story acceptance.'}
(OUT/'actual-state-reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'requests':requests,'matched_fixed_producer_pins':report['matched_fixed_producer_pins'],'m4':report['m4'],'fiscal_history':history},indent=2))
