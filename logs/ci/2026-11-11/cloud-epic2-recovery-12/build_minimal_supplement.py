"""One bounded original-side collection manifest; no collection or remote mutation."""
import hashlib
import json
from pathlib import Path,PureWindowsPath

REPO=Path('/workspace/newrouge');OUT=Path(__file__).absolute().parent
BASE=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
index=json.loads((BASE/'transport/FILE_INDEX.json').read_bytes())
root=PureWindowsPath(index['root_map']['task'])
fixed=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())['original_fixed_inputs']
reconstructed=json.loads((OUT/'native-output-reconstruction.json').read_bytes())['results']
host=json.loads((OUT/'recovered-host-source.json').read_bytes())
resolved={x['task_relative_path']:{'path':x['derived_path'],'sha256':x['actual_sha256'],'bytes':x['actual_bytes'],'kind':'source-defined exact-byte reconstruction'} for x in reconstructed if x['exact_original_raw_match']}
resolved[host['original_task_relative_path']]={'path':host['available_data_path'],'sha256':host['sha256'],'bytes':host['bytes'],'kind':'exact preserved Git blob'}
rows=[]
for row in fixed:
 rel=row['task_relative_path']
 if rel in resolved:continue
 if rel.endswith('atomic-review-prepare-seal-01/config.json'):
  point='_original_controls:182 -> _fixed_json:156; _original_controls:188-205'
  purpose='Original closed source885 config, parent/prerequisite pins, historical request/source epoch and exact original dependency input contract.'
 elif rel.endswith('/reader-stderr.bin'):
  point='_execution:244-248'
  purpose='Original stderr bytes and raw identity alongside exact stdout/archive; cannot regenerate diagnostic timing or replace with new output.'
 elif rel.endswith('/reader-held-started.json'):
  point='_original_controls:183-187; _execution:212,220-222'
  purpose='Original held reader PID/birth/image/handle and Popen/CreateProcess observations.'
 elif rel.endswith('/reader-held-terminal.json'):
  point='_original_controls:183-187; _execution:213,223-231'
  purpose='Original exact held reader OS0, matching start identity, Job empty/closed observations; original execution identity is not inferred from data output.'
 elif rel.endswith('/stop.json'):
  point='_original_controls:183-187; _execution:214,232-241'
  purpose='Preserve original owner OS2/zero-model failure, charged facts and exact blocked boundary; do not replay or rewrite failure.'
 elif rel.endswith('supervision-01/result.json'):
  point='_original_controls:183-187; _execution:215-219'
  purpose='Original supervision completion/known terminal and retained failed worker OS1/source-control observations.'
 else:
  point='_original_controls:183-187'
  purpose='Required original control source/manifest/start/terminal raw pin closes the selected archived execution contract; not a fresh execution or general Story requirement.'
 rows.append({'original_task_relative_path':rel,'original_absolute_path':str(root/rel),
  'read_source':'frozen R56 scripts/python/_b_route_retained_execution.py', 'read_point':point,
  'expected_sha256':row['expected_raw_sha256'],'expected_bytes':None,
  'size_status':'Not recorded in selected fixed source/index/decoded references; measure original bytes during collection, never infer zero.',
  'why_this_route_needs_it':purpose,'cloud_status':'Not mapped by FILE_INDEX; no indexed raw match; no exact bytes found in19 selected original records and32 decoded carriers.'})
authority={'original_task_relative_path':'r62/scripts/python/qualified-historical-owner-authority.v2.json',
 'original_absolute_path':str(root/'r62/scripts/python/qualified-historical-owner-authority.v2.json'),
 'preferred_field':'/python_version','expected_sha256':None,'expected_bytes':None,
 'read_source':'original R56 _b_route_adoption_review.py:80 policy_identity; current _b_route_qualified_historical_auth_v3.py:80-83',
 'purpose':'Actual full original sys.version input is needed to reconstruct recorded policy identity1012db...; numeric version/current Python cannot substitute.',
 'sensitivity':'Project owner/source/interpreter descriptor, not credentials or OpenAI auth.json. Preserve screened original bytes if present; no password/token/key/session files.',
 'status':'Original populated uncommitted resource explicitly excluded by initial migration; current public template is null; selected structured encodings yield no full build string.',
 'alternative_if_original_record_unavailable':{'artifact':'new python-policy-input-observation.json, explicitly a current metadata observation, never a fake historical file',
  'interpreter_path':r'C:\Program Files\Python312\python.exe',
  'required_original_executable_sha256':'4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a',
  'pin_source':'batch03 task/story29-host3-allocation-Root-01/config.json#/binding/runtime_files/6',
  'bounded_action':'Only if needed, obtain sys.version with this exact hash-matching system interpreter in isolated/no-site metadata mode (-I -S); no project import/driver/model/ledger. Record timestamp, actual executable path/hash and complete sys.version.',
  'acceptance_limit':'Cloud must reconstruct and match the old recorded policy digest using actual51 source/schema preimages. A new observation alone proves neither an old execution nor installed authority. If executable hash differs, report the mismatch; do not substitute.'}}
conditional={'reason':'Avoid another round trip after reading the actually missing config. These are exact downstream reads in the same existing function, not recursive history/software collection.',
 'source':'frozen R56 _b_route_retained_execution.py:196-205',
 'only_follow':['config.parent_pins path/digest entries','config.prerequisite_pins path/digest entries'],
 'explicit_old_owner_files':[{'original_task_relative_path':'logs/ci/2026-11-09/story27-r52-retained-execution-admission-01/old-owner-sources/'+n,
  'expected_sha256_from_config':'/source_files/scripts~1python~1'+n,'expected_bytes':None} for n in ('_b_route_qualified_origin.py','_b_route_adoption_review.py')],
 'pruning':'Use cloud-available-raw-pins.json and original path/roles to avoid retransmitting exact already available data. Raw equality alone does not substitute an owner, namespace, budget grant or execution claim.',
 'do_not_expand':['All source_files885 entries','Entire Task/.git/home','Software environments/packages/credentials','Optional historical directories and diagnostic attachments'],
 'missing':'Record exact unresolved original path/digest/reference field once; do not execute code to regenerate it or sanitize into a fake original.'}
source_scope=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-11/actual-policy-control-closure.json').read_bytes())
source_preimages=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-11/policy-preimages-restoration.json').read_bytes())
source_pin=next(r['restored_raw_sha256'] for r in source_preimages['files'] if r['relative_path']=='scripts/python/_b_route_retained_execution.py')
report={'schema':'newrouge.bounded-recovery-minimal-supplement.v1','original_task_root':str(root),
 'read_source_snapshot':source_scope['original_R56_source_snapshot'],
 'read_source_relative_path':'scripts/python/_b_route_retained_execution.py','read_source_raw_sha256':source_pin,
 'fixed_producer_inputs_total':15,'already_resolved':resolved,'required_remaining_producer_inputs':rows,
 'full_python_policy_input':authority,'conditional_same_config_closure':conditional,
 'scope':'Only NativeV15Origin03 consumption of retained original NativeV15Origin02/R52 archive and original policy reconstruction. Not Epic-wide prerequisites.',
 'handoff':'Parent coordinates the already authorized one-time original-side static screened handoff to migration/newrogue-20261111/recovery-batch01-public. No original-side development, old driver/native/model/unknown replay, accounting transition, main merge or Fast.',
 'do_not_resend':'Two exact derived large outputs and82k host source are resolved; batch03 and51 policy preimages remain available. Preserve originals, failures, privacy exclusions and STOP.'}
(OUT/'MINIMAL_SUPPLEMENT.json').write_text(json.dumps(report,indent=2)+'\n')
# Availability list for pruning only, not a new authority registry.
available=[{'path':r['archive_path'],'sha256':r['sha256'],'bytes':r.get('size_bytes',r.get('bytes')),'kind':'verified batch03 data'} for r in index['original_files']+index['derived_files']]
p=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-11/policy-preimages-restoration.json').read_bytes())
for r in p['files']:
 path=Path(p['output_data_directory'])/r['relative_path']
 available.append({'path':str(path),'sha256':r['restored_raw_sha256'],'bytes':path.stat().st_size,'kind':'exact restored policy preimage'})
for r in resolved.values():available.append({'path':r['path'],'sha256':r['sha256'],'bytes':r['bytes'],'kind':r['kind']})
(OUT/'cloud-available-raw-pins.json').write_text(json.dumps({'purpose':'Collection deduplication only; no new registry/authority and no role or funding substitution.','files':available},indent=2)+'\n')
lines=['# One-time minimal supplement after bounded cloud resolution','',
 'Original Task root: `'+str(root)+'`. All relative paths below resolve under that root. No routine reapproval is requested; the parent coordinates the already authorized screened static handoff.','',
 '## Resolved: do not upload again','']
for name,r in resolved.items():lines+=['- `'+name+'`: '+str(r['bytes'])+' bytes, SHA256 `'+r['sha256']+'`; '+r['kind']+'.']
lines+=['','The two large outputs total359022124 bytes and match original size/hash exactly. The82k host source also matches; its working-tree CRLF form was the earlier mismatch, while its preserved Git blob is the required LF original. No execution identity was inferred.','',
 '## Remaining12 original producer/control files','',
 'Read points refer to frozen R56 `scripts/python/_b_route_retained_execution.py` (public snapshot55afde57c2898cf214eab136cb868815919828fd). Bytes are unknown for these12; collect their actual sizes with the original bytes.','',
 '| Original Task-relative path | Required SHA-256 | Actual read point |','| --- | --- | --- |']
for r in rows:lines+=['| `'+r['original_task_relative_path']+'` | `'+r['expected_sha256']+'` | '+r['read_point']+' |']
lines+=['','These files preserve original failed parent/owner outcomes and successful held reader completion. New output bytes cannot replace their start/terminal/Job observations. Per-file purposes and absolute paths are in MINIMAL_SUPPLEMENT.json.','',
 '## Original full Python policy input','',
 'Preferred existing original: `'+authority['original_absolute_path']+'`, field `/python_version`. Original populated-resource hash/size are unknown; never use the public null-template hash as its identity. This is project owner configuration, not a credential file. R56 policy_identity uses the complete sys.version at line80; auth binds it at lines80-83.','',
 'If that original record is unavailable, a bounded new observation from `C:\\Program Files\\Python312\\python.exe` may provide a candidate DATA input only if executable SHA256 is `4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a` (original Host3 config runtime_files/6). Use isolated/no-site system metadata only; record current timestamp/path/hash/full sys.version and label it as a new observation. Cloud will independently reconstruct the old policy digest. Do not import project code or claim this new record is historical execution proof. If the binary differs, report it.','',
 '## Same-config closure in this one pass','',
 'When the actual atomic config is found, follow only `parent_pins` and `prerequisite_pins` at source lines203-205, plus the two explicit old-owner files at196-199:','']
for r in conditional['explicit_old_owner_files']:lines+=['- `'+r['original_task_relative_path']+'`; original required digest comes from config `'+r['expected_sha256_from_config']+'`.']
lines+=['','Prune exact already available bytes using cloud-available-raw-pins.json; preserve each path/role/ref relationship. Do not expand all885 source files, software fingerprints or all history. Report missing/privacy-excluded originals once; do not regenerate or redact them into originals.','',
 '## Search scope and trust limit','',
 'Inspected19 explicitly referenced records and32 decoded carriers (16 parsed JSON/JSONL),12509934 decoded bytes, no depth/size omission. Original source/protection/review/retained/Host3/recovery references guided selection; no directory recursion, new download or whole archive scan. No exact remaining control bytes or complete Python build string were found in that bounded scope. The report does not claim to search arbitrary unreferenced opaque historical payloads.','',
 'All recovery is DATA only. No old reader/driver/model executed, no owner handle or compensation authority minted, and no failure/charge/STOP changed.']
(OUT/'MINIMAL_SUPPLEMENT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'remaining_producer_files':len(rows),'resolved_fixed_inputs':len(resolved),'python_input':'preferred original project descriptor or explicitly new hash-bound system metadata observation','available_pin_records':len(available)},indent=2))
