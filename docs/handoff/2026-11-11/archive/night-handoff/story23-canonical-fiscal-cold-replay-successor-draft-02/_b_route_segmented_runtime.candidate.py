"""Fresh segmented host authority; never a retrofit or formal-adoption proof.

The complete original 3A input is verified and frozen on the host. Only the
shared per-request renderer applies model capacity limits. Source contracts
must themselves be original independently audited material, not model-extracted
or caller-approved substitutes. No function dispatches a model here.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import weakref

import _b_route_codec as codec
import _b_route_sources as sources
import _b_route_planning_input as planning
import _mvg_capability_recovery as recovery

RUN = 'newrouge.b-route-segmented-planning-run.v1'
FISCAL_RUN = 'newrouge.b-route-segmented-planning-run.fiscal-v2'
FISCAL_BORN = 'newrouge.b-route-segmented-born.fiscal-v2'
FISCAL_NATIVE_RUN = 'newrouge.b-route-segmented-native-run.fiscal-v2'
HOST = 'newrouge.b-route-segmented-host-input.v1'
CATALOG = 'newrouge.b-route-segmented-source-contract.v1'
SOURCE = 'newrouge.b-route-segmented-source-authority.v1'
PLAN_AUTHORITY = 'newrouge.b-route-segmented-plan-authority.v1'
CAMPAIGN = 'story25'
PROFILE = {'capability': ('3b-capabilities-v1', 96, 2), 'mvg': ('3b-mvg-v1', 192, 3)}
_SEAL = object()
_ACTIVE = ContextVar('segmented_runtime_action', default=None)
_SOURCES = weakref.WeakKeyDictionary()
_TRANSPORTS = weakref.WeakKeyDictionary()
_PLAN_AUTHORITIES = weakref.WeakKeyDictionary()


def _core():
    import _b_route_segmented_workflow as core
    return core


def require(value, reason):
    if not value:
        raise _core().SegmentedBlocked('segmented_runtime:' + reason)


def closed(value, keys, reason):
    require(type(value) is dict and set(value) == set(keys), reason)


def role(path):
    codec.validate_reference_path(path)
    require(not any(p.casefold() in {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions', 'credentials', 'auth'}
                    or p.casefold().startswith('.env') for p in path.split('/'))
        and Path(path).name.casefold() not in {'auth.json', 'credentials.json', 'credentials.toml', 'id_rsa', 'id_ed25519'},
        'sensitive_role_before_io')
    return path


def reference(value):
    closed(value, ('path', 'schema_version', 'raw_digest'), 'closed_reference')
    role(value['path'])
    require(type(value['schema_version']) is str and bool(value['schema_version'])
        and type(value['raw_digest']) is str and re.fullmatch('sha256:[0-9a-f]{64}', value['raw_digest']), 'typed_raw_reference')
    return deepcopy(value)


def path(root, name, *, missing=False):
    role(name)
    root = Path(root).absolute()
    target = root.joinpath(*name.split('/'))
    require(target.is_relative_to(root), 'contained_path')
    for item in reversed((target, *target.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            require(missing, 'missing_path:' + name)
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'no_reparse')
        require(stat.S_ISDIR(info.st_mode) or (item == target and stat.S_ISREG(info.st_mode) and info.st_nlink == 1), 'plain_single_link')
    return target


def raw(root, name):
    return path(root, name).read_bytes()


def value(root, name):
    return codec.strict_json_loads(raw(root, name))


def wire(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def ref_for(name, schema, data):
    return {'path': name, 'schema_version': schema, 'raw_digest': codec.raw_digest(data)}


def read_ref(obs, ref):
    ref = reference(ref)
    data = obs.read(ref['path'])
    require(codec.raw_digest(data) == ref['raw_digest'], 'reference_raw_changed')
    result = codec.strict_json_loads(data)
    require(type(result) is dict and result.get('schema_version') == ref['schema_version'], 'reference_schema')
    return data, result


def policy_identity():
    from _b_route_schema_resources import identity
    directory = Path(__file__).absolute().parent
    names = ('_b_route_segmented_runtime.py', '_b_route_segmented_workflow.py', '_b_route_segmented_requests.py',
        '_b_route_segmented_plan.py', 'plan_segmented.py', '_b_route_compact_literal.py',
        '_b_route_segmented_response_wire.py',
        '_b_route_segmented_journal.py', '_b_route_segmented_candidates.py', '_b_route_planning_input.py',
        '_b_route_source_audit.py', '_b_route_sources.py', '_b_route_inventory.py', '_b_route_codec.py',
        '_b_route_execution_transition.py', '_b_route_selector_recovery.py', '_planning_skill_common.py',
        '_capability_input_integrity.py', '_mvg_evidence_transport.py',
        '_mvg_capability_recovery.py', '_mvg_capability_checkpoint.py', '_planning_apply_journal.py',
        '_planning_execution_binding.py', '_codex_app_server.py', 'codex_isolated_model_runner.py',
        'openai_isolated_model_runner.py', '_b_route_schema_resources.py')
    model_files = {name: codec.raw_digest((directory.parents[1] / name).read_bytes()) for name in _DESCRIBE_NAMES}
    return {'source_root': str(directory.parents[1]), 'python': sys.version,
        'files': {name: codec.raw_digest((directory / name).read_bytes()) for name in names},
        'model_source_files': model_files, 'schemas': identity(auxiliary=True)}


def _configured_store(root):
    expected = Path(root).absolute() / 'logs/ci/mvg-recovery'
    configured = os.environ.get('SC_MVG_RECOVERY_ROOT')
    require(configured is None or Path(configured).absolute() == expected, 'foreign_registry_before_owner_io')
    return expected


_PRESERVED_COMMIT = '988022094381c2b190b30c7702ed77aadda3805a'
_DESCRIBE_NAMES = ('scripts/python/codex_isolated_model_runner.py', 'scripts/python/openai_isolated_model_runner.py',
    'scripts/python/_planning_skill_common.py', 'scripts/python/_codex_app_server.py',
    'scripts/python/_model_response_identity.py', 'scripts/python/_capability_task_evidence.py',
    'scripts/python/_capability_input_integrity.py', 'scripts/sc/_llm_backend.py')
_SOURCE_BOOT = r'''
import hashlib,importlib.machinery,pathlib,stat,sys
def source_bytes(p):
 p=pathlib.Path(p).absolute()
 if p.is_relative_to(OWNER):
  for a in reversed((p,*p.parents)):
   i=a.lstat()
   if stat.S_ISLNK(i.st_mode) or getattr(i,'st_file_attributes',0)&0x400:raise PermissionError('source_reparse')
  i=p.lstat()
  if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1:raise PermissionError('source_plain_file')
 data=p.read_bytes()
 if p.is_relative_to(OWNER) and 'sha256:'+hashlib.sha256(data).hexdigest()!=PINS.get(p.relative_to(OWNER).as_posix()):raise RuntimeError('original_source_changed')
 return data
class Source(importlib.machinery.SourceFileLoader):
 def get_code(self,name):
  p=pathlib.Path(self.path).absolute(); data=source_bytes(p)
  return self.source_to_code(data,str(p))
class Finder:
 def find_spec(self,name,path=None,target=None):
  found=importlib.machinery.PathFinder.find_spec(name,path,target)
  if found is None:return None
  if isinstance(found.loader,importlib.machinery.SourcelessFileLoader):raise ImportError('sourceless_forbidden')
  if isinstance(found.loader,importlib.machinery.SourceFileLoader):
   found.loader=Source(name,found.origin);return found
  return None
sys.meta_path.insert(0,Finder());sys.dont_write_bytecode=True
'''
_BRIDGE = r'''
import base64,hashlib,json,os,pathlib,stat,subprocess,sys
q=json.loads(sys.stdin.buffer.read().decode('utf-8'))
OWNER=pathlib.Path(q['owner']);PINS=q['pins'];ROOT=pathlib.Path(q['root'])
exec(q['source_boot'],globals())
def role(p):
 p=pathlib.Path(p)
 if any(x.casefold() in {'.codex','.aws','.ssh','sessions','archived_sessions','credentials','auth'} or x.casefold().startswith('.env') for x in p.parts) or p.name.casefold() in {'auth.json','credentials.json','credentials.toml','id_rsa','id_ed25519'}:raise PermissionError('sensitive_io')
def guard(event,args):
 if event.startswith('socket.') or event in {'os.system','os.startfile','os.exec','os.spawn','pty.spawn'}:raise PermissionError('offline_only')
 if event in {'os.mkdir','os.remove','os.rmdir','os.rename','os.link','os.symlink','os.truncate','os.chmod','os.chown','os.utime','shutil.copyfile','shutil.rmtree'}:raise PermissionError('read_only')
 if event in {'os.listdir','os.scandir'} and args and isinstance(args[0],(str,bytes,os.PathLike)):role(os.fsdecode(args[0]))
 if event=='open':
  mode,flags=args[1] or '',args[2] or 0
  if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC):raise PermissionError('read_only')
  if isinstance(args[0],(str,bytes,os.PathLike)):role(os.fsdecode(args[0]))
 if event=='subprocess.Popen':
  command=args[1]
  if not any((isinstance(command,(list,tuple)) and list(command)==v) or (type(command)is str and command==subprocess.list2cmdline(v)) for v in COMMANDS):raise PermissionError('unknown_metadata_process')
def describe_command():
 pins={name:PINS[name] for name in q['describe_names']}
 script=str(OWNER/'scripts/python/codex_isolated_model_runner.py')
 code='import pathlib,sys,hashlib,os\nOWNER=pathlib.Path('+repr(str(OWNER))+');PINS='+repr(pins)+'\n'+q['source_boot']
 code+='\ndef guard(e,a):\n if e.startswith("socket.") or e in {"subprocess.Popen","os.system","os.startfile","os.exec","os.spawn","pty.spawn","os.mkdir","os.remove","os.rename","os.rmdir","os.link","os.symlink","os.truncate","os.chmod","os.chown","os.utime","shutil.copyfile","shutil.rmtree"}: raise PermissionError("describe_read_only")\n if e=="open":\n  if (isinstance(a[1],str) and any(c in a[1] for c in "wax+")) or (a[2] or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC): raise PermissionError("describe_read_only")\n  if isinstance(a[0],(str,bytes,os.PathLike)):\n   p=pathlib.Path(os.fsdecode(a[0])); parts={v.casefold() for v in p.parts}\n   if parts&{".codex",".aws",".ssh","sessions","archived_sessions","credentials","auth"} or any(v.startswith(".env") for v in parts) or p.name.casefold() in {"auth.json","credentials.json","credentials.toml","id_rsa","id_ed25519"}: raise PermissionError("describe_sensitive_io")\nsys.addaudithook(guard)\n'
 code+='sys.path[:0]='+repr([str(OWNER/'scripts/python'),str(OWNER/'scripts/sc')])+'\nsys.argv=['+repr(script)+',"--describe"]\n'
 code+='p=pathlib.Path('+repr(script)+');data=source_bytes(p)\nexec(compile(data,str(p),"exec"),{"__name__":"__main__","__file__":str(p),"__package__":None})\n'
 code+='for name,expected in PINS.items():\n assert "sha256:"+hashlib.sha256(source_bytes(OWNER/name)).hexdigest()==expected,"describe_source_drift"\n'
 return [sys.executable,'-I','-S','-B','-c',code]
descriptor=describe_command();runner=str(OWNER/'scripts/python/codex_isolated_model_runner.py')
logical=[[sys.executable,runner,'--describe'],[sys.executable,'-B',runner,'--describe']]
COMMANDS=[descriptor,[q['git'],'-C',str(ROOT),'rev-parse','HEAD']]
prior=subprocess.Popen
def launch(command,*a,**kw):
 if kw.get('shell') or 'executable' in kw:raise PermissionError('metadata_override')
 if isinstance(command,(list,tuple)) and list(command) in logical:command=descriptor
 if isinstance(command,(list,tuple)) and list(command)==['git','-C',str(ROOT),'rev-parse','HEAD']:command=[q['git'],'-C',str(ROOT),'rev-parse','HEAD']
 return prior(command,*a,**kw)
subprocess.Popen=launch;sys.addaudithook(guard)
sys.path[:0]=[str(OWNER/'scripts/python'),str(OWNER/'scripts/sc'),*q['dependencies']]
import _b_route_sources as sources,_b_route_planning_input as planning
for module in (sources,planning):
 if pathlib.Path(module.__file__).absolute()!=OWNER/'scripts/python'/(module.__name__+'.py'):raise RuntimeError('original_module_origin')
if q['mode']=='rules':result=planning.rules_identity(ROOT)
else:
 obs=sources.Observations(ROOT)
 contract=planning.read_contract(obs,q['planning_contract'])
 import _b_route_source_audit as audit
 audit.verify_current_proof(obs,contract['audit_ref'],scope_id=contract['scope']['scope_id'])
 audit_files={k:base64.b64encode(v).decode('ascii') if v is not None else None for k,v in obs.files.items()}
 inputs=planning.assemble(obs,q['planning_contract']);obs.verify()
 result={'inputs':inputs,'audit_files':audit_files,
  'files':{k:base64.b64encode(v).decode('ascii') if v is not None else None for k,v in obs.files.items()},
  'globs':[{'patterns':list(k),'result':v} for k,v in obs.globs.items()]}
print(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')))
'''


def _preserved_owner(root, contract):
    # This unverified metadata selects a named verifier only. The selected
    # original verifier must still validate the entire real proof/currentness.
    audit_ref = role(contract['audit_ref'])
    identity_name = Path(audit_ref).parent.as_posix() + '/identity.json'
    identity = value(root, identity_name)
    tools = identity.get('tools', {})
    task = Path(__file__).absolute().parents[3]
    expected = task / 'r5/scripts/python/_b_route_source_audit.py'
    if str(expected) in tools or expected.as_posix() in tools:
        return task / 'r5'
    # Relative keys mean source and artifact root were the same. A current
    # source proof may be validated locally; unknown absolute owners are not
    # silently aliased to the new source directory.
    current = Path(__file__).absolute().with_name('_b_route_source_audit.py')
    require('scripts/python/_b_route_source_audit.py' in tools or str(current) in tools or current.as_posix() in tools,
        'unsupported_original_3a_source_owner')
    return None


def _original_assemble(root, planning_contract, owner, *, mode='assemble'):
    from _b_route_execution_transition import _source_manifest
    before = _source_manifest(owner, _PRESERVED_COMMIT)
    task = owner.parent
    deps = [str(task / 'story22-tokenizer-deps'),
        r'C:\Users\Administrator\Documents\Codex\2026-11-04\task-2\python-env\Lib\site-packages',
        r'C:\Program Files\Python312\Lib\site-packages']
    import shutil
    git = shutil.which('git')
    require(git is not None, 'git_metadata_unavailable')
    request = {'root': str(Path(root).absolute()), 'owner': str(owner), 'planning_contract': planning_contract,
        'pins': {name: row['raw_digest'] for name, row in before.items()}, 'dependencies': deps,
        'describe_names': list(_DESCRIBE_NAMES), 'git': git, 'mode': mode, 'source_boot': _SOURCE_BOOT}
    completed = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', _BRIDGE], input=wire(request),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(owner), timeout=1800, check=False,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(completed.returncode == 0, 'original_3a_assembly_failed:' + completed.stderr.decode('utf-8', errors='replace')[-1600:])
    require(_source_manifest(owner, _PRESERVED_COMMIT) == before, 'original_3a_verifier_source_changed')
    return codec.strict_json_loads(completed.stdout), {'root': str(owner), 'commit': _PRESERVED_COMMIT, 'manifest': before}


def _block_span(block, original):
    text = original.decode('utf-8', errors='strict')
    if 'source_char_start' in block or 'source_char_end_exclusive' in block:
        start, end = block.get('source_char_start'), block.get('source_char_end_exclusive')
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), 'original_block_character_span')
        return len(text[:start].encode('utf-8')), len(text[:end].encode('utf-8'))
    first, last = block['line_start'], block['line_end']
    lines = text.splitlines(keepends=True)
    require(type(first) is int and type(last) is int and 1 <= first <= last <= len(lines), 'original_block_line_span')
    return len(''.join(lines[:first - 1]).encode('utf-8')), len(''.join(lines[:last]).encode('utf-8'))


def _turns(audit_files):
    """Only original 3A validation observations, before caller contexts are read."""
    turns = set()
    for name, data in audit_files.items():
        if data is None or not name.startswith('logs/ci/') or not name.endswith('/receipt.json'):
            continue
        base = name[:-len('receipt.json')]
        if base + 'execution.json' not in audit_files or base + 'workspace/output.json' not in audit_files:
            continue
        receipt = codec.strict_json_loads(data)
        if receipt.get('schema_version') != 'newrouge.isolated-model-runner-receipt.v1':
            continue
        evidence = receipt.get('model_identity_evidence')
        require(type(evidence) is list and bool(evidence), 'actual_3a_turn_evidence')
        for row in evidence:
            require(type(row) is dict and all(type(row.get(k)) is str and bool(row[k]) for k in ('thread_id', 'turn_id')),
                'unknown_3a_thread_or_turn')
            turns.add((row['thread_id'], row['turn_id']))
    require(bool(turns), 'original_3a_thread_identity_unavailable')
    return [{'thread_id': thread, 'turn_id': turn} for thread, turn in sorted(turns)]


def _catalog(obs, inputs, catalog_ref, run_id, planner):
    core = _core()
    data, catalog = read_ref(obs, catalog_ref)
    require(catalog_ref['schema_version'] == CATALOG, 'source_contract_version')
    closed(catalog, ('schema_version', 'planner', 'scope', 'materials', 'candidates', 'dimensions',
        'obligations', 'dependency_edges', 'final_required_segments'), 'closed_original_source_contract')
    require(catalog['schema_version'] == CATALOG and catalog['planner'] == planner
        and catalog['scope'] == inputs['contract']['scope'], 'source_contract_scope')
    audited = {row['path']: row['raw_digest'] for row in inputs['source_inventory']}
    require(audited.get(catalog_ref['path']) == codec.raw_digest(data), 'source_contract_must_be_actual_independently_audited_original')
    business = {row['path']: row for row in inputs['evidence']}
    require(catalog_ref['path'] in business, 'source_contract_in_actual_scope')
    declarations = deepcopy(catalog['materials'])
    require(type(declarations) is list and all(type(row) is dict for row in declarations), 'material_declarations')
    require({row.get('path') for row in declarations} == set(business) - {catalog_ref['path']}
        and len(declarations) == len(business) - 1, 'complete_original_business_material_domain')
    globals_ = {row['path'] for row in inputs['constraints'] if 'text' in row}
    for row in declarations:
        role(row['path'])
        require(row['path'] not in globals_ or row['role'] == 'global', 'original_constraints_are_indivisible_globals')
    require(all(c['material_ids'] == [] for c in catalog['candidates'])
        and len(catalog['candidates']) == PROFILE[planner][2], 'fresh_candidate_ids_before_generation')
    own_id = 'segmented-source-contract'
    require(all(row.get('material_id') != own_id for row in declarations), 'reserved_source_contract_material_id')
    declarations.append({'material_id': own_id, 'path': catalog_ref['path'], 'version': CATALOG,
        'role': 'global', 'candidate_label': None, 'boundaries': [0, len(data)]})
    manifest = core.freeze_manifest(obs.root, run_id=run_id, materials=declarations,
        candidates=catalog['candidates'], final_required_segments=[*catalog['final_required_segments'], own_id + '.0'])
    # Preserve the real 3A ledger independently of extraction/model self-report.
    # Every original source block contributes an owner-derived preservation
    # obligation for each overlapping complete raw segment. This does not claim
    # that those spans alone settle cross-segment semantic relationships.
    obligations = deepcopy(catalog['obligations'])
    existing = {row['obligation_id'] for row in obligations}
    materials = {m['material_id']: m for m in manifest['materials']}
    blocks = [b for b in inputs['global_proof']['ledger']['blocks'] if b['source_path'] in business]
    for block in blocks:
        original = obs.read(block['source_path'])
        require(codec.raw_digest(original) == business[block['source_path']]['sha256'], 'actual_original_block_source')
        lo, hi = _block_span(block, original)
        pieces = [s for s in manifest['segments'] if materials[s['material_id']]['path'] == block['source_path']
                  and s['start'] < hi and s['end'] > lo]
        require(bool(pieces), 'complete_block_segment_coverage')
        for segment in pieces:
            oid = 'original-block-' + hashlib.sha256((block['block_id'] + ':' + segment['segment_id']).encode()).hexdigest()
            require(oid not in existing, 'source_obligation_collision')
            obligations.append({'obligation_id': oid, 'kind': 'preservation', 'segment_ids': [segment['segment_id']], 'dependency_ids': []})
            existing.add(oid)
    require(bool(blocks), 'qualified_original_semantic_ledger_required')
    return {'manifest': manifest, 'dimensions': deepcopy(catalog['dimensions']), 'obligations': obligations,
        'dependency_edges': sorted(deepcopy(catalog['dependency_edges'])), 'original_contract': catalog,
        'original_ledger_blocks': deepcopy(blocks), 'planning_scope': deepcopy(inputs['contract']['scope'])}


@dataclass(frozen=True, eq=False)
class _SourceCapture(Mapping):
    _seal: object
    # Mapping supplies value equality and disables hashing. Issued authority
    # tokens must instead remain distinct identities in the weak issuer table.
    __hash__ = object.__hash__
    __eq__ = object.__eq__

    def _facts(self):
        require(self in _SOURCES, 'source_capture_was_not_issued_by_actual_owner')
        return _SOURCES[self]

    @property
    def _root(self):
        return self._facts()['root']

    @property
    def _files(self):
        return dict(self._facts()['files'])

    @property
    def _globs(self):
        return codec.strict_json_loads(self._facts()['globs'])

    @property
    def _policy(self):
        return codec.strict_json_loads(self._facts()['policy'])

    def __getitem__(self, key):
        if key == 'byte_store':
            return {name: data for name, data in self._facts()['files'] if data is not None}
        return codec.strict_json_loads(self._facts()['data'])[key]

    def __iter__(self):
        return iter([*codec.strict_json_loads(self._facts()['data']), 'byte_store'])

    def __len__(self):
        return len(codec.strict_json_loads(self._facts()['data'])) + 1


def capture_source(root, *, run_id, planner, planning_contract, semantic_catalog_ref=None):
    """Actual full host qualification; no monolithic final-input measurement."""
    root = Path(root).absolute()
    _configured_store(root)
    require(planner in PROFILE, 'planner')
    codec.validate_business_id(run_id)
    require(run_id not in {'c4', 'm4'}, 'no_old_run_retrofit')
    role(planning_contract)
    semantic_catalog_ref = reference(semantic_catalog_ref) if semantic_catalog_ref is not None else None
    obs = sources.Observations(root)
    # Obtain the original receipt observation domain before contexts are read.
    contract = planning.read_contract(obs, planning_contract)
    for row in contract['constraints'] + contract['contexts']:
        role(row['path'])
    role(contract['audit_ref'])
    original_owner = _preserved_owner(root, contract)
    if original_owner is None:
        from _b_route_source_audit import verify_current_proof
        verify_current_proof(obs, contract['audit_ref'], scope_id=contract['scope']['scope_id'])
        upstream_turns = _turns(dict(obs.files))
        inputs = planning.assemble(obs, planning_contract)
        verifier = {'root': str(Path(__file__).absolute().parents[2]), 'commit': None, 'mode': 'current-source-owner'}
    else:
        assembled, verifier = _original_assemble(root, planning_contract, original_owner)
        inputs = assembled['inputs']
        upstream_turns = _turns({p: base64.b64decode(b, validate=True) if b is not None else None
                                 for p, b in assembled['audit_files'].items()})
        for name, encoded in assembled['files'].items():
            role(name)
            expected = base64.b64decode(encoded, validate=True) if encoded is not None else None
            require(obs.read(name, optional=expected is None) == expected, 'original_owner_complete_observation_changed')
        for watch in assembled['globs']:
            require(obs.watch(watch['patterns']) == watch['result'], 'original_owner_complete_membership_changed')
    domain = (_catalog(obs, inputs, semantic_catalog_ref, run_id, planner) if semantic_catalog_ref is not None
              else _derived_catalog(obs, inputs, run_id, planner))
    require(inputs['global_proof']['identity'].get('expected_reasoning_effort') == 'high', 'original_qualified_3a_high_evidence_required')
    source_identity = {'schema_version': SOURCE, 'planning_contract_ref': planning_contract,
        'semantic_catalog_ref': semantic_catalog_ref, 'scope': deepcopy(inputs['contract']['scope']),
        'source_catalog': domain, 'upstream_turns': upstream_turns,
        'audit_verifier_source': verifier, 'dependencies': deepcopy(inputs['dependencies'])}
    frozen = {'schema_version': HOST, 'inputs': inputs}
    frozen['input_identity'] = codec.canonical_digest(frozen)
    result = {'frozen': frozen, 'source_identity': source_identity,
        'run_id': run_id, 'planner': planner, 'policy_identity': policy_identity(), 'domain': domain}
    token = _SourceCapture(_SEAL)
    _SOURCES[token] = {'root': root, 'data': wire(result), 'files': tuple(obs.files.items()),
        'globs': wire([[list(p), v] for p, v in obs.globs.items()]), 'policy': wire(result['policy_identity'])}
    verify_candidate_context(root, token)
    return token


def verify_candidate_context(root, token):
    require(type(token) is _SourceCapture and token._seal is _SEAL and token._root == Path(root).absolute(), 'original_source_capture_required')
    require(token._policy == policy_identity(), 'current_source_policy_changed')
    obs = sources.Observations(token._root)
    for name, before in token._files.items():
        role(name)
        require(obs.read(name, optional=before is None) == before, 'current_original_raw_or_absence_changed')
    for patterns, before in token._globs:
        require(obs.watch(patterns) == before, 'current_original_membership_changed')
    verifier = token['source_identity']['audit_verifier_source']
    if verifier.get('mode') == 'current-source-owner':
        rules = planning.rules_identity(token._root)
    else:
        rules, now = _original_assemble(token._root, token['source_identity']['planning_contract_ref'], Path(verifier['root']), mode='rules')
        require(now == verifier, 'original_verifier_source_identity_changed')
    require(rules == token['frozen']['inputs']['dependencies']['rules'], 'original_planning_source_rules_changed')


def _validate_plan_source(plan, source):
    _core().validate_plan(plan)
    domain = source['domain']
    require(plan['run_id'] == source['run_id'] and plan['planner'] == source['planner']
        and all(codec.canonical_digest(plan[key]) == codec.canonical_digest(domain[key])
                for key in ('manifest', 'dimensions', 'obligations', 'dependency_edges')),
        'plan_must_use_complete_actual_owner_source_domain')
    if plan['candidate_contract'] is not None:
        require(plan['candidate_contract']['source_input_identity'] == source['frozen']['input_identity'],
            'candidate_contract_must_bind_actual_host_input')


def _homes(root, planner, run_id):
    require(planner in PROFILE, 'planner')
    codec.validate_business_id(run_id)
    prefix = 'mvg' if planner == 'mvg' else 'capability'
    return path(root, 'logs/ci/' + prefix + '-planning/' + run_id, missing=True)


def _write_new(root, name, data):
    target = path(root, name, missing=True)
    require(target.parent.is_dir(), 'owned_parent_required')
    with target.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


# Funding, birth publication, current epoch and the original native time pools
# are implemented below; all public witness construction stays in this owner.

INDEX = 'newrouge.b-route-segmented-run-index.v1'


def _index(registry):
    result = registry.get('segmented_runs', {'schema_version': INDEX, 'campaign': CAMPAIGN, 'runs': []})
    closed(result, ('schema_version', 'campaign', 'runs'), 'closed_original_registry_segmented_metadata')
    require(result['schema_version'] == INDEX and result['campaign'] == CAMPAIGN and type(result['runs']) is list, 'registry_segmented_version')
    seen = set()
    for row in result['runs']:
        closed(row, ('run_path', 'born_ref', 'planner', 'epoch', 'head'), 'closed_index_entry')
        role(row['run_path'])
        reference(row['born_ref'])
        require(row['run_path'] not in seen and row['planner'] in PROFILE and type(row['epoch']) is int and row['epoch'] >= 0,
            'unique_original_index_run')
        _head(row['head'])
        seen.add(row['run_path'])
    return deepcopy(result)


def _head(head):
    closed(head, ('journal_ref', 'claim_ref', 'claim_raw_digest', 'native_run_after_digest'), 'closed_immutable_ledger_head')
    role(head['journal_ref'])
    role(head['claim_ref'])
    require(head['journal_ref'].startswith('logs/ci/mvg-recovery/activity/segmented-journals/'), 'original_journal_head_namespace')
    require(all(type(head[k]) is str and re.fullmatch('sha256:[0-9a-f]{64}', head[k]) for k in
                ('claim_raw_digest', 'native_run_after_digest')), 'head_actual_raw_digests')


def with_ledger_head(root, registry, run_dir, plan, witness, *, journal_ref, claim_ref, claim_raw_digest, run_after_digest):
    """Pure original-registry metadata update, never fee authority or IO.

    B's original journal must independently verify the permanent claim and
    actual after-image. Its raw digest deliberately does not hash the journal
    that contains the registry after-image, avoiding a self-reference cycle.
    """
    result = deepcopy(registry)
    index = _index(result)
    run_path = (Path(run_dir).absolute() / 'run.json').relative_to(Path(root).absolute()).as_posix()
    require(witness['run_path'] == run_path and witness['plan_digest'] == plan['plan_digest']
        and witness['registry_epoch'] == registry['epoch'], 'same_original_run_epoch_for_head')
    rows = [r for r in index['runs'] if r['run_path'] == run_path]
    require(len(rows) == 1 and rows[0]['epoch'] == registry['epoch'] and rows[0]['planner'] == plan['planner']
        and rows[0]['born_ref'] == witness['born_ref'], 'existing_same_born_index_only')
    head = {'journal_ref': journal_ref, 'claim_ref': claim_ref, 'claim_raw_digest': claim_raw_digest,
            'native_run_after_digest': run_after_digest}
    _head(head)
    require(claim_ref.startswith(str(Path(run_path).parent.as_posix()) + '/'), 'claim_in_original_run')
    rows[0]['head'] = head
    result['segmented_runs'] = index
    return result


def _derived_catalog(obs, inputs, run_id, planner):
    """Conservative real-3A denominator without a newly invented source file.

    Where the original audit has no qualified dependency partition, the whole
    semantic domain is required rather than guessed separable. Large indivisible
    requests then block at the real renderer; no summary is called lossless.
    """
    core = _core()
    business = {row['path']: row for row in inputs['evidence']}
    require(bool(business), 'complete_qualified_original_business_source_required')
    global_paths = {r['path'] for r in inputs['constraints'] if 'text' in r}
    declarations = []
    for name, row in business.items():
        role(name)
        data = obs.read(name)
        require(codec.raw_digest(data) == row['sha256'], 'original_business_raw')
        mid = 'source-' + hashlib.sha256(name.encode()).hexdigest()[:24]
        declarations.append({'material_id': mid, 'path': name, 'version': row['sha256'],
            'role': 'global' if name in global_paths else 'source', 'candidate_label': None, 'boundaries': [0, len(data)]})
    candidates = [{'label': chr(65 + n), 'candidate_id': 'candidate-' + str(n + 1), 'material_ids': []}
                  for n in range(PROFILE[planner][2])]
    manifest = core.freeze_manifest(obs.root, run_id=run_id, materials=declarations, candidates=candidates)
    all_ids = [s['segment_id'] for s in manifest['segments']]
    context_id = 'whole-qualified-original-context'
    obligations = [{'obligation_id': context_id, 'kind': 'preservation', 'segment_ids': all_ids, 'dependency_ids': []}]
    material = {m['material_id']: m for m in manifest['materials']}
    blocks = [b for b in inputs['global_proof']['ledger']['blocks'] if b['source_path'] in business]
    require(bool(blocks), 'actual_3a_ledger_denominator')
    for block in blocks:
        segments = [s['segment_id'] for s in manifest['segments'] if material[s['material_id']]['path'] == block['source_path']]
        require(bool(segments), 'original_block_not_in_frozen_source')
        obligations.append({'obligation_id': 'original-' + block['block_id'], 'kind': 'preservation',
            'segment_ids': segments, 'dependency_ids': [context_id]})
    for segment in manifest['segments']:
        obligations.append({'obligation_id': 'raw-span-' + segment['segment_id'], 'kind': 'preservation',
            'segment_ids': [segment['segment_id']], 'dependency_ids': [context_id]})
    return {'manifest': manifest, 'dimensions': ['source-fidelity', 'journey-coherence', 'handoff-integrity',
        'verification-feasibility', 'cumulative-impact'], 'obligations': obligations,
        'dependency_edges': sorted([[row['obligation_id'], context_id] for row in obligations[1:]]),
        'original_contract': None, 'original_ledger_blocks': deepcopy(blocks),
        'original_semantic_objects': deepcopy(inputs['global_proof']['proposals']),
        'planning_scope': deepcopy(inputs['contract']['scope']), 'partition_mode': 'whole-qualified-semantic-domain'}


_OLD_CAP = 'logs/ci/capability-planning/c4'
_OLD_MVG = 'logs/ci/mvg-planning/m4'
_V9 = 'logs/ci/2026-11-06/story25-path-recovery'
_CAP_ANCHOR = _V9 + '/host-resume-v11/post-capability-v16/cap-anchor.json'
_CAP_ANCHOR_SHA = 'sha256:68e3575be5edce9b595299442d869daab01b9aeb1e70705d643b37f46d550a37'


def _tree_pins(root, reference, obs):
    directory = path(root, reference)
    files, dirs = {}, []
    def walk(parent):
        for target in sorted(parent.iterdir()):
            name = target.relative_to(root).as_posix()
            path(root, name)
            if target.is_dir():
                dirs.append(name)
                walk(target)
            elif target.name == 'capability-coordinator.lock' and target.parent == directory:
                require(target.stat().st_size == 1, 'original_run_lock_shape')
            else:
                files[name] = codec.raw_digest(obs.read(name))
    walk(directory)
    return {'run_ref': reference, 'files': files}, dirs


@dataclass(frozen=True, eq=False)
class _CampaignCapture:
    root: Path
    obs: object
    cap_rows: tuple
    mvg_rows: tuple
    mvg_capture: object
    task_pins: dict
    cap_manifest: dict
    cap_directories: tuple
    base_global: int
    seal: object


def _capture_campaign(root):
    """Actual fixed old authority, not caller-supplied initial quota numbers."""
    import _b_route_selector_recovery as selector
    root = Path(root).absolute()
    task = Path(__file__).absolute().parents[3]
    require(root == task / 'nx', 'this_campaign_artifact_root')
    obs = sources.Observations(root)
    anchor_raw = obs.read(_CAP_ANCHOR)
    require(codec.raw_digest(anchor_raw) == _CAP_ANCHOR_SHA, 'actual_root_pinned_cap_historical_os0_anchor')
    anchor = codec.strict_json_loads(anchor_raw)
    require(anchor['schema_version'] == 'newrouge.story25-post-capability.v16.cap-anchor'
        and anchor['qualified'] is True and anchor['released'] == 0, 'historical_fee_fact_not_current_cap_adoption')
    v11 = _V9 + '/host-resume-v11'
    controls = {'terminal': v11 + '/native-stages/capability/terminal.json',
        'claim': v11 + '/native-stages/capability/claim.json', 'prepared': v11 + '/prepared-record.json',
        'prepare_claim': v11 + '/prepare-claim.json', 'root9_prepared': _V9 + '/prepared-record.json',
        'original_claim': _V9 + '/native-stages/capability/claim.json',
        'native_return': v11 + '/native-stages/capability/native-return.json',
        'supervisor_spec': v11 + '/supervisor-launch.json', 'supervisor_receipt': v11 + '/supervisor/exit.json',
        'supervisor_started': v11 + '/supervisor/started.json', 'supervisor_claim': v11 + '/supervisor/claim.json',
        'child_stdout': v11 + '/supervisor/child-stdout.txt', 'child_stderr': v11 + '/supervisor/child-stderr.txt'}
    require(set(anchor['pins']) == set(controls) and all(codec.raw_digest(obs.read(name)) == anchor['pins'][key]
        for key, name in controls.items()), 'complete_original_cap_os_control_bytes')
    receipt = codec.strict_json_loads(obs.files[controls['supervisor_receipt']])
    observation = anchor['trusted_executor_root_observation']
    require(type(receipt['os_exit_code']) is int and receipt['os_exit_code'] == 0
        and receipt['exit_source'] == 'held_subprocess_handle_wait' and receipt['source_pins_unchanged'] is True
        and observation['supervisor_receipt_sha256'] == anchor['pins']['supervisor_receipt']
        and observation['cap_terminal_sha256'] == anchor['pins']['terminal']
        and observation['cap_claim_sha256'] == anchor['pins']['claim'], 'retained_actual_held_os0_fact')
    task_pins = {}
    cap_manifest, cap_directories = _tree_pins(root, _OLD_CAP, obs)
    require(cap_manifest == anchor['native_manifest'], 'exact_actual_cap_native_snapshot')
    cap = codec.strict_json_loads(obs.files[_OLD_CAP + '/run.json'])
    cap_calls = cap['capability_selection']['calls']
    require(type(anchor['native_count']) is int and len(cap_calls) == anchor['native_count']
        == cap['capability_selection']['total_invocations'], 'actual_retained_cap_profile_calls')
    retained = selector.capture_retained_selector(root)
    mvg = obs.json(_OLD_MVG + '/run.json')
    selector.verify_retained_selector_capture(root, retained, current_state=mvg)
    funding = mvg['b_route_campaign_funding']
    require(funding['campaign_limit'] == 290 and funding['released'] == funding['subsequent_full_reservation'] == 0
        and type(funding['paid_or_unknown_before_run']) is int and funding['paid_or_unknown_before_run'] >= len(cap_calls),
        'actual_original_global_liabilities')
    result = _CampaignCapture(root, obs, tuple(deepcopy(cap_calls)), tuple(deepcopy(mvg['capability_selection']['calls'])),
        retained, task_pins, cap_manifest, tuple(cap_directories), funding['paid_or_unknown_before_run'], _SEAL)
    _close_campaign(result)
    return result


def _close_campaign(capture):
    import _b_route_selector_recovery as selector
    require(type(capture) is _CampaignCapture and capture.seal is _SEAL, 'actual_campaign_capture')
    task = Path(__file__).absolute().parents[3]
    require(all(codec.raw_digest(path(task, Path(name).relative_to(task).as_posix()).read_bytes()) == digest
                for name, digest in capture.task_pins.items()), 'current_original_campaign_controls')
    capture.obs.verify()
    current, dirs = _tree_pins(capture.root, _OLD_CAP, sources.Observations(capture.root))
    require(current == capture.cap_manifest and tuple(dirs) == capture.cap_directories, 'original_cap_membership_changed')
    selector.verify_retained_selector_capture(capture.root, capture.mvg_capture,
        current_state=value(capture.root, _OLD_MVG + '/run.json'))


def _registry_entries(root):
    """Original current registry and its original clear archives; no new index."""
    _configured_store(root)
    store = 'logs/ci/mvg-recovery'
    current = recovery.registry(Path(root))
    snapshots = []
    for epoch in range(current['epoch']):
        name = store + '/clears/epoch-' + str(epoch) + '.json'
        previous = value(root, name)
        require(previous['schema_version'] == recovery.SCHEMA and previous['epoch'] == epoch, 'complete_original_clear_history')
        snapshots.append(previous)
    snapshots.append(current)
    result = {}
    for snapshot in snapshots:
        for entry in _index(snapshot)['runs']:
            require(entry['epoch'] == snapshot['epoch'], 'original_index_epoch')
            require(entry['run_path'] not in result, 'run_cannot_reopen_under_new_epoch')
            result[entry['run_path']] = entry
    return current, result


def _fixed_recovery_store(root, binding, epoch):
    """Original resolved store identity, with a role gate before any path IO."""
    closed(binding, ('store', 'epoch'), 'closed_original_recovery_store')
    require(type(binding['epoch']) is int and binding['epoch'] == epoch, 'original_recovery_store_epoch')
    require(type(binding['store']) is str, 'fixed_original_recovery_store_role')
    recorded = Path(binding['store'])
    expected = _configured_store(root)
    # Windows Path equality accepts casing/separator differences emitted by
    # the original owner, without resolving any caller-selected foreign path.
    require(recorded.is_absolute() and '..' not in recorded.parts and recorded == expected,
        'fixed_original_recovery_store_role')
    checked = path(Path(root).absolute(), expected.relative_to(Path(root).absolute()).as_posix())
    require(checked.is_dir(), 'fixed_original_recovery_store_directory')
    canonical = recovery.store_root(Path(root).absolute(), {'recovery': binding})
    require(canonical == checked.resolve(), 'fixed_original_recovery_store_identity')
    path(Path(root).absolute(), expected.relative_to(Path(root).absolute()).as_posix())
    return canonical


def _history(root, entry, state):
    import _b_route_segmented_journal as journal
    run_dir = path(root, entry['run_path']).parent
    _fixed_recovery_store(root, state.get('recovery'), entry['epoch'])
    require(state.get('planner') == entry['planner'] and state.get('segmented_born_ref') == entry['born_ref'],
        'same_registered_profile_birth_and_historical_epoch')
    plan = value(root, run_dir.relative_to(root).as_posix() + '/b/plan.json')
    _core().validate_plan(plan)
    obs = sources.Observations(root)
    _birth(root, run_dir, state, plan, obs)
    obs.verify()
    history = journal.inspect_native_history(root, run_dir, state)
    head = entry['head']
    require(codec.raw_digest(raw(root, head['claim_ref'])) == head['claim_raw_digest'], 'monotonic_original_claim_head')
    actual_digest = codec.raw_digest(raw(root, entry['run_path']))
    if actual_digest != head['native_run_after_digest']:
        require(any(view['target_path'] == entry['run_path'] and view['actual_relation'] == 'after'
            and view['before_digest'] == head['native_run_after_digest'] and view['after_digest'] == actual_digest
            for view in history.get('pending_native_views', [])), 'native_ledger_highwater_changed')
    known = [*history['reservations'], *history.get('completions', [])]
    known_head = any(row['journal_ref'] == head['journal_ref'] and row['claim_ref'] == head['claim_ref']
            and row['claim_raw_digest'] == head['claim_raw_digest'] and row['run_after_digest'] == head['native_run_after_digest']
            for row in known)
    if not known_head:
        claim = value(root, head['claim_ref'])
        require(claim.get('schema_version') == 'newrouge.b-route-segmented-birth-claim.v1'
            and head['claim_ref'] == Path(entry['run_path']).parent.as_posix() + '/b/claim.json'
            and claim['born_ref'] == entry['born_ref'] and claim['native_after_digest'] == head['native_run_after_digest']
            and claim['journal_ref'] == head['journal_ref'], 'actual_zero_birth_head')
    return history


def _rows_lineages(row):
    if 'lineage_ids' in row:
        require(type(row['lineage_ids']) is list and len(set(row['lineage_ids'])) == len(row['lineage_ids'])
            and all(type(x) is str and x for x in row['lineage_ids']), 'actual_request_lineages')
        return row['lineage_ids']
    return [row['candidate']] if row.get('candidate') else []


def _funding(root, planner, run_dir, campaign):
    _close_campaign(campaign)
    registry, entries = _registry_entries(root)
    own = (Path(run_dir).absolute() / 'run.json').relative_to(root).as_posix()
    rows = list(campaign.cap_rows if planner == 'capability' else campaign.mvg_rows)
    total_other = 0
    evidence = []
    pending = []
    for name, entry in entries.items():
        state = value(root, name)
        require(state.get('schema_version') in (RUN, FISCAL_RUN) and state.get('segmented_campaign') == CAMPAIGN, 'registered_same_campaign_run')
        history = _history(root, entry, state)
        pending.extend(history['pending_publications'])
        if name == own:
            continue
        calls = state['capability_selection']['calls']
        require(type(state['capability_selection']['total_invocations']) is int
            and len(calls) == state['capability_selection']['total_invocations'], 'actual_sibling_charge_count')
        charged = history.get('charged_or_pending_calls', len(calls))
        require(type(charged) is int and charged >= len(calls), 'original_pending_encumbrance_count')
        total_other += charged
        if entry['planner'] == planner:
            rows.extend(deepcopy(calls))
            rows.extend(deepcopy(row['row']) for row in history['reservations'] if row['row']['number'] > len(calls))
        evidence.append(ref_for(name, state['schema_version'], raw(root, name)))
    lineages = {}
    for row in rows:
        for lineage in _rows_lineages(row):
            lineages[lineage] = lineages.get(lineage, 0) + 1
    before = campaign.base_global + len(campaign.mvg_rows) + total_other
    require(before >= 78 and before <= 290 and len(rows) <= PROFILE[planner][1], 'retained_actual_campaign_or_profile_exhausted')
    funding = {'schema_version': 'newrouge.story25-native-funding.v1', 'paid_or_unknown_before_run': before,
        'campaign_limit': 290, 'subsequent_full_reservation': 0, 'maximum_native_charges': 290 - before,
        'released': 0, 'retained_profile_calls': len(rows), 'retained_lineage_calls': lineages,
        'pending_encumbrances': list({r['journal_ref']: r for r in pending}.values()),
        'profile_evidence': [ref_for(_OLD_CAP + '/run.json', campaign.obs.json(_OLD_CAP + '/run.json')['schema_version'],
            campaign.obs.files[_OLD_CAP + '/run.json']), ref_for(_OLD_MVG + '/run.json', campaign.obs.json(_OLD_MVG + '/run.json')['schema_version'],
            campaign.obs.files[_OLD_MVG + '/run.json']), *evidence]}
    return funding, rows, registry, entries


def _activity(row):
    outcome, request = row.get('outcome') or {}, row.get('request_identity') or {}
    elapsed = outcome.get('active_elapsed_seconds')
    if elapsed is None:
        elapsed = request.get('timeout_sec')
    require(type(elapsed) in {int, float} and math.isfinite(elapsed) and elapsed >= 0,
        'unknown_model_time_requires_original_requested_timeout')
    return elapsed


def _retained_time(rows):
    total, lineages = 0, {}
    for row in rows:
        elapsed = _activity(row)
        total += elapsed
        for lineage in _rows_lineages(row):
            lineages[lineage] = lineages.get(lineage, 0) + elapsed
    return {'total_active_seconds': total, 'lineage_active_seconds': lineages}


def _metadata_members(root, relative, pattern):
    directory = path(root, relative, missing=True)
    if not directory.exists():
        return None
    require(directory.is_dir(), 'original_preplan_metadata_directory')
    result = []
    for item in sorted(directory.iterdir()):
        name = item.relative_to(root).as_posix()
        checked = path(root, name)
        require(checked.is_file() and re.fullmatch(pattern, item.name), 'original_preplan_metadata_member')
        result.append(name)
    return result


def _plan_authority_observations(root, registry, entries):
    """Pin the real pre-plan index, clear chain and original publication files."""
    obs = sources.Observations(root)
    obs.read('logs/ci/mvg-recovery/registry.json', optional=True)
    for epoch in range(registry['epoch']):
        obs.read('logs/ci/mvg-recovery/clears/epoch-' + str(epoch) + '.json')
    for name in entries:
        obs.read(name)
    directories = {
        'logs/ci/mvg-recovery/clears': r'epoch-[0-9]+\.json',
        'logs/ci/mvg-recovery/activity/segmented-journals': r'[0-9a-f]{24}-[0-9]{3}-(born|init|reserve|complete|fail|finalize)\.json'}
    memberships = {name: _metadata_members(root, name, pattern) for name, pattern in directories.items()}
    for name in memberships['logs/ci/mvg-recovery/clears'] or []:
        obs.read(name)
    for name in memberships['logs/ci/mvg-recovery/activity/segmented-journals'] or []:
        role(name)
        publication = codec.strict_json_loads(obs.read(name))
        require(publication.get('schema_version') == 'newrouge.planning-apply-journal.v1'
            and publication.get('status') in {'pending', 'complete'}, 'original_preplan_publication_shape')
        require(publication['status'] == 'complete', 'preplan_pending_original_publication_requires_resume')
        for entry in publication['entries']:
            role(entry['path'])
            obs.read(entry['path'], optional=True)
    return obs, tuple((name, directories[name], members) for name, members in memberships.items())


def _verify_plan_pins(issued):
    issued['observations'].verify()
    for name, pattern, members in issued['memberships']:
        require(_metadata_members(issued['root'], name, pattern) == members, 'preplan_original_metadata_membership_changed')


def _plan_authority_facts(root, run, source, campaign):
    funding, rows, registry, entries = _funding(root, source['planner'], run, campaign)
    result = {'schema_version': PLAN_AUTHORITY, 'run_id': source['run_id'], 'planner': source['planner'],
        'source_input_identity': source['frozen']['input_identity'], 'domain': source['domain'],
        'funding': funding, 'retained_time': _retained_time(rows), 'registry_epoch': registry['epoch'],
        'source_policy': source._policy}
    result['authority_digest'] = codec.canonical_digest(result)
    return result, registry, entries


@dataclass(frozen=True, eq=False)
class _PlanAuthority(Mapping):
    seal: object
    __hash__ = object.__hash__
    __eq__ = object.__eq__

    def _facts(self):
        require(self in _PLAN_AUTHORITIES, 'plan_authority_not_issued_by_actual_owner')
        return _PLAN_AUTHORITIES[self]

    def __getitem__(self, key):
        return codec.strict_json_loads(self._facts()['data'])[key]

    def __iter__(self):
        return iter(codec.strict_json_loads(self._facts()['data']))

    def __len__(self):
        return len(codec.strict_json_loads(self._facts()['data']))


def capture_plan_authority(root, *, run_id, planner, planning_contract, semantic_catalog_ref=None):
    """Actual source and current campaign facts before any plan/born exists.

    The returned issued object is not execution/admission permission. A saved
    plan is data; prepare_run independently captures these authorities again.
    """
    root = Path(root).absolute()
    run = _homes(root, planner, run_id)
    require(not os.path.lexists(run), 'preplan_requires_fresh_namespace')
    source = capture_source(root, run_id=run_id, planner=planner, planning_contract=planning_contract,
        semantic_catalog_ref=semantic_catalog_ref)
    campaign = _capture_campaign(root)
    facts, registry, entries = _plan_authority_facts(root, run, source, campaign)
    obs, memberships = _plan_authority_observations(root, registry, entries)
    token = _PlanAuthority(_SEAL)
    _PLAN_AUTHORITIES[token] = {'root': root, 'run': run, 'source': source, 'campaign': campaign,
        'observations': obs, 'memberships': memberships, 'data': wire(facts)}
    verify_plan_authority(root, token)
    return token


def verify_plan_authority(root, authority):
    """Fresh close of issued source/raw/membership/epoch/fees; no dict approval."""
    require(type(authority) is _PlanAuthority and authority.seal is _SEAL
        and authority in _PLAN_AUTHORITIES, 'genuine_preplan_authority_required')
    issued = authority._facts()
    require(issued['root'] == Path(root).absolute() and not os.path.lexists(issued['run']), 'same_fresh_preplan_namespace')
    verify_candidate_context(root, issued['source'])
    _close_campaign(issued['campaign'])
    _verify_plan_pins(issued)
    facts, _, _ = _plan_authority_facts(issued['root'], issued['run'], issued['source'], issued['campaign'])
    require(codec.canonical_digest(facts) == codec.canonical_digest(codec.strict_json_loads(issued['data'])),
        'preplan_actual_source_funding_time_or_epoch_changed')
    _verify_plan_pins(issued)
    verify_candidate_context(root, issued['source'])
    _close_campaign(issued['campaign'])
    return deepcopy(facts)


def _model_bootstrap(source):
    owner = Path(source._policy['source_root'])
    task = Path(__file__).absolute().parents[3]
    dependencies = [str(task / 'story22-tokenizer-deps'),
        r'C:\Users\Administrator\Documents\Codex\2026-11-04\task-2\python-env\Lib\site-packages',
        r'C:\Program Files\Python312\Lib\site-packages']
    runner = str(owner / 'scripts/python/codex_isolated_model_runner.py')
    code = ('import pathlib,sys\nOWNER=pathlib.Path(' + repr(str(owner)) + ');PINS='
        + repr(source._policy['model_source_files']) + '\n' + _SOURCE_BOOT)
    code += '\nsys.path[:0]=' + repr([str(owner / 'scripts/python'), str(owner / 'scripts/sc'), *dependencies]) + '\n'
    code += 'p=pathlib.Path(' + repr(runner) + ');data=source_bytes(p)\nsys.argv=[str(p),*sys.argv[1:]]\n'
    code += 'exec(compile(data,str(p),"exec"),{"__name__":"__main__","__file__":str(p),"__package__":None})\n'
    return code


@dataclass(frozen=True, eq=False)
class _RunnerTransport(Mapping):
    seal: object
    __hash__ = object.__hash__
    __eq__ = object.__eq__

    def _data(self):
        require(self in _TRANSPORTS and _TRANSPORTS[self]['closed'], 'original_closed_runner_transport')
        return codec.strict_json_loads(_TRANSPORTS[self]['data'])

    def __getitem__(self, key):
        return self._data()[key]

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())


@contextmanager
def _source_runner_scope(root, runner, source):
    verify_candidate_context(root, source)
    expected = Path(source._policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py'
    require(Path(runner).absolute() == expected, 'exact_source_bound_official_runner')
    token = _RunnerTransport(_SEAL)
    facts = {'source': source, 'launches': [], 'closed': False, 'data': None}
    _TRANSPORTS[token] = facts
    bootstrap = _model_bootstrap(source)
    prior = subprocess.Popen
    def launch(command, *args, **kwargs):
        require(type(command) in {list, tuple} and all(type(x) is str for x in command)
            and not kwargs.get('shell') and 'executable' not in kwargs, 'source_runner_explicit_argv')
        logical = list(command)
        require(logical[:3] == [sys.executable, '-B', str(expected)] and len(logical) >= 4
            and not facts['launches'], 'one_exact_official_runner_launch')
        actual = [sys.executable, '-I', '-S', '-B', '-c', bootstrap, *logical[3:]]
        require(len(subprocess.list2cmdline(actual)) < 30000, 'bounded_source_runner_commandline')
        record = {'logical_argv': logical, 'transport_argv': actual,
            'source_pins': deepcopy(source._policy['model_source_files']),
            'bootstrap_raw_digest': codec.raw_digest(bootstrap.encode('utf-8')), 'child_pid': None}
        facts['launches'].append(record)
        child = prior(actual, *args, **kwargs)
        record['child_pid'] = child.pid
        return child
    try:
        subprocess.Popen = launch
        yield token
    finally:
        subprocess.Popen = prior
        # Restore before original source/current metadata children may spawn.
        verify_candidate_context(root, source)
        require(len(facts['launches']) == 1 and type(facts['launches'][0]['child_pid']) is int, 'actual_runner_started_once')
        facts['data'] = wire({'schema_version': 'newrouge.b-route-segmented-runner-transport.v1', **facts['launches'][0]})
        facts['launches'] = []
        facts['closed'] = True


def source_only_runner(root, runner):
    active = _ACTIVE.get()
    require(active is not None and active['root'] == Path(root).absolute(), 'verified_action_before_runner')
    return _source_runner_scope(root, runner, active['source'])


def verify_runner_transport(root, token, *, logical_command):
    require(type(token) is _RunnerTransport and token.seal is _SEAL and token in _TRANSPORTS and _TRANSPORTS[token]['closed'],
        'original_closed_runner_transport_token')
    verify_candidate_context(root, _TRANSPORTS[token]['source'])
    data = token._data()
    require(data['logical_argv'] == list(logical_command) and type(data['child_pid']) is int and data['child_pid'] > 0,
        'actual_transport_matches_original_logical_command')
    return data


def replay_runner_transport(root, provenance, *, logical_command):
    """Cold replay of the host-captured actual transport; never an OS0 factory."""
    active = _ACTIVE.get()
    require(active is not None, 'fresh_action_before_transport_replay')
    closed(provenance, ('schema_version', 'logical_argv', 'transport_argv', 'source_pins', 'bootstrap_raw_digest', 'child_pid'),
        'closed_actual_runner_transport')
    source = active['source']
    verify_candidate_context(root, source)
    code = _model_bootstrap(source)
    expected_runner = Path(source._policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py'
    logical = list(logical_command)
    require(logical[:3] == [sys.executable, '-B', str(expected_runner)]
        and provenance['schema_version'] == 'newrouge.b-route-segmented-runner-transport.v1'
        and provenance['logical_argv'] == logical
        and provenance['transport_argv'] == [sys.executable, '-I', '-S', '-B', '-c', code, *logical[3:]]
        and provenance['source_pins'] == source._policy['model_source_files']
        and provenance['bootstrap_raw_digest'] == codec.raw_digest(code.encode('utf-8'))
        and type(provenance['child_pid']) is int and provenance['child_pid'] > 0, 'exact_original_source_transport_replay')


def _run_identity(source, plan, description):
    profile, limit, _ = PROFILE[plan['planner']]
    candidates = source['domain']['manifest']['candidates']
    # Original native budget slots are stable across new run IDs/business IDs.
    lineages = {row['label']: 'candidate-' + str(n + 1) for n, row in enumerate(candidates)}
    runner = Path(source._policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py'
    return {'schema_version': 'newrouge.b-route-segmented-runtime-identity.v1',
        'protocol': _core().PROTOCOL, 'plan_digest': plan['plan_digest'], 'native_profile_budget_source': profile,
        'source_policy': source._policy, 'host_input_identity': source['frozen']['input_identity'],
        'candidate_lineages': lineages, 'original_candidates': deepcopy(candidates),
        'runner': {'path': str(runner), 'raw_digest': codec.raw_digest(runner.read_bytes()), 'description': deepcopy(description)},
        'limits': {'native_requests': limit, 'candidate_requests': 64, 'final_input_tokens': 70000,
            'context_tokens': 96000, 'capability_candidate_seconds': 2700, 'capability_synthesis_seconds': 1200,
            'capability_total_seconds': 13500, 'mvg_invocation_seconds': 1800}}


def _describe(root, source):
    from _planning_skill_common import inspect_isolated_runner
    runner = Path(source._policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py'
    with _source_runner_scope(root, runner, source):
        description = inspect_isolated_runner(runner, suppress_bytecode=True)
    require(description.get('requested_reasoning_effort') == 'high' and description.get('model_tools') == []
        and description.get('tool_access_scope') == 'none' and description.get('fresh_session_per_invocation') is True
        and description.get('can_read_outside_workspace') is False and description.get('filesystem_scope') == 'prompt_only'
        and description.get('supports_input_preflight') is True and description.get('supports_request_budget') is True,
        'original_official_high_fresh_no_tools_runner')
    return description


def _prepare_run_v1(root, *, run_id, planner, plan, planning_contract, semantic_catalog_ref=None):
    """Create one genuine fresh versioned run, not an old descriptor or opt-in flag.

    Qualification is complete before namespace creation. The initial immutable
    archive has zero calls and no born_ref; born hashes that archive; only then
    does run.json refer to born. This is a directed hash graph, not a fixed point.
    """
    root = Path(root).absolute()
    require(run_id not in {'c4', 'm4'} and plan.get('run_id') == run_id and plan.get('planner') == planner, 'fresh_declared_run_only')
    run = _homes(root, planner, run_id)
    require(not os.path.lexists(run), 'new_run_namespace_already_exists')
    authority = capture_plan_authority(root, run_id=run_id, planner=planner, planning_contract=planning_contract,
        semantic_catalog_ref=semantic_catalog_ref)
    authority_facts = verify_plan_authority(root, authority)
    issued = authority._facts()
    source, campaign = issued['source'], issued['campaign']
    _validate_plan_source(plan, source)
    description = _describe(root, source)
    runtime_identity = _run_identity(source, plan, description)
    funding, _rows, registry, entries = _funding(root, planner, run, campaign)
    require(codec.canonical_digest(funding) == codec.canonical_digest(authority_facts['funding']), 'preplan_funding_before_preparation')
    require(not funding['pending_encumbrances'], 'pending_original_publication_before_new_birth')
    require(len(plan['nodes']) <= min(PROFILE[planner][1] - funding['retained_profile_calls'],
            290 - funding['paid_or_unknown_before_run']), 'whole_plan_must_fit_actual_remaining_original_budgets')
    for lineage in runtime_identity['candidate_lineages'].values():
        expected = sum(node['phase'] != 'selection' and lineage in
            {runtime_identity['candidate_lineages'][label] for label in node['candidate_labels']} for node in plan['nodes'])
        require(expected + funding['retained_lineage_calls'].get(lineage, 0) <= 64, 'whole_plan_original_lineage_budget')
    epoch_request = os.environ.get('SC_MVG_RECOVERY_EPOCH')
    require(epoch_request is None or re.fullmatch('[0-9]+', epoch_request) and int(epoch_request) == registry['epoch'], 'original_current_epoch_before_birth')
    host_name = run.relative_to(root).as_posix() + '/b/host.json'
    host = {'schema_version': HOST, 'frozen': source['frozen'], 'source_identity': source['source_identity'],
        'source_request': {'run_id': run_id, 'planner': planner, 'planning_contract': planning_contract,
                           'semantic_catalog_ref': semantic_catalog_ref},
        'observations': [{'path': p, 'raw_base64': base64.b64encode(b).decode('ascii') if b is not None else None}
                         for p, b in source._files.items()],
        'globs': source._globs, 'policy_identity': source._policy}
    host_ref = ref_for(host_name, HOST, wire(host))
    source_identity = {**source['source_identity'], 'host_ref': host_ref}
    base = run.relative_to(root).as_posix()
    initial = {'schema_version': RUN, 'protocol': _core().PROTOCOL, 'input_stage': '3b', 'run_id': run_id,
        'planner': planner, 'segmented_campaign': CAMPAIGN, 'segmented_plan_digest': plan['plan_digest'],
        'segmented_host_ref': host_ref, 'runtime_identity': runtime_identity, 'source_identity': source_identity,
        'native_profile': PROFILE[planner][0], 'mvg.run_invocation_limit': PROFILE[planner][1],
        'checkpoint_strategy': recovery.CHECKPOINT_STRATEGY, 'active_elapsed_seconds': 0,
        'b_route_campaign_funding': deepcopy(funding),
        'capability_selection': {'total_invocations': 0, 'calls': [], 'lineage_invocations': {
            lineage: 0 for lineage in runtime_identity['candidate_lineages'].values()},
            'selected': [], 'current': None, 'terminal': False},
        'phase': 'segmented-prepared', 'selection_status': 'segmented-unselected',
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False}
    import _b_route_segmented_journal as journal
    from _mvg_capability_checkpoint import coordinator_lock
    with recovery.operation_lock(root):
        require(codec.canonical_digest(verify_plan_authority(root, authority)) == codec.canonical_digest(authority_facts),
            'preplan_authority_at_birth_cas')
        verify_candidate_context(root, source)
        now_funding, _rows, current, _entries = _funding(root, planner, run, campaign)
        require(now_funding == funding and current['epoch'] == registry['epoch'] and not os.path.lexists(run), 'birth_currentness_cas')
        run.parent.mkdir(parents=True, exist_ok=True)
        run.mkdir(exist_ok=False)
        with coordinator_lock(run):
            recovery.bind_epoch(root, initial)
            initial_ref = ref_for(base + '/b/initial-run.json', RUN, wire(initial))
            born = {'schema_version': _core().BORN, 'protocol': _core().PROTOCOL, 'plan_digest': plan['plan_digest'],
                'run_id': run_id, 'initial_run_ref': initial_ref, 'initial_calls': 0, 'native_profile': PROFILE[planner][0],
                'source_identity': source_identity, 'runtime_identity': runtime_identity}
            born_ref = ref_for(base + '/b/born.json', _core().BORN, wire(born))
            state = {**initial, 'segmented_born_ref': born_ref}
            actual_after = codec.raw_digest(wire(state))
            stem = hashlib.sha256((str(run.resolve()) + '\0' + plan['plan_digest']).encode()).hexdigest()[:24]
            journal_ref = 'logs/ci/mvg-recovery/activity/segmented-journals/' + stem + '-000-born.json'
            claim_name = base + '/b/claim.json'
            claim = {'schema_version': 'newrouge.b-route-segmented-birth-claim.v1', 'run_path': base + '/run.json',
                'born_ref': born_ref, 'native_after_digest': actual_after, 'journal_ref': journal_ref}
            entry = {'run_path': base + '/run.json', 'born_ref': born_ref, 'planner': planner,
                'epoch': initial['recovery']['epoch'], 'head': {'journal_ref': journal_ref, 'claim_ref': claim_name,
                    'claim_raw_digest': codec.raw_digest(wire(claim)), 'native_run_after_digest': actual_after}}
            with coordinator_lock(_configured_store(root)):
                registry = recovery.registry(root)
                recovery.assert_epoch(root, state, value=registry)
                index = _index(registry)
                require(all(row['run_path'] != entry['run_path'] for row in index['runs']), 'born_index_cannot_replace_run')
                index['runs'].append(entry)
                after_registry = {**registry, 'segmented_runs': index}
                verify_candidate_context(root, source)
                _close_campaign(campaign)
                journal.publish_born(root, run, files={run / 'b/initial-run.json': initial,
                    run / 'b/born.json': born, run / 'b/host.json': host, run / 'b/plan.json': deepcopy(plan),
                    run / 'b/claim.json': claim, run / 'run.json': state}, registry_after=after_registry)
    verify_candidate_context(root, source)
    require(raw(root, base + '/run.json') == wire(state), 'born_publication_exact')
    return {'status': 'segmented-run-prepared', 'run_ref': base + '/run.json', 'born_ref': born_ref,
        'host_ref': host_ref, 'plan_digest': plan['plan_digest'], 'logical_calls': 0,
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False}

def prepare_run(root, *, run_id, planner, plan, planning_contract, semantic_catalog_ref=None, schedule_grant=None):
    if schedule_grant is None:
        return _prepare_run_v1(root, run_id=run_id, planner=planner, plan=plan,
            planning_contract=planning_contract, semantic_catalog_ref=semantic_catalog_ref)
    return _prepare_run_fiscal(root, run_id=run_id, planner=planner, plan=plan,
        planning_contract=planning_contract, semantic_catalog_ref=semantic_catalog_ref, schedule_grant=schedule_grant)

def _prepare_run_fiscal(root, *, run_id, planner, plan, planning_contract, semantic_catalog_ref=None, schedule_grant=None):
    """Create one genuine fresh versioned run, not an old descriptor or opt-in flag.

    Qualification is complete before namespace creation. The initial immutable
    archive has zero calls and no born_ref; born hashes that archive; only then
    does run.json refer to born. This is a directed hash graph, not a fixed point.
    """
    root = Path(root).absolute()
    require(run_id not in {'c4', 'm4'} and plan.get('run_id') == run_id and plan.get('planner') == planner, 'fresh_declared_run_only')
    run = _homes(root, planner, run_id)
    require(not os.path.lexists(run), 'new_run_namespace_already_exists')
    import _b_route_segmented_funding as funding_owner
    funding_owner.require_schedule_grant(schedule_grant)
    authority = schedule_grant.retained_plan_authority()
    bound_source = authority._facts()['source']['source_identity']
    require(bound_source['planning_contract_ref'] == planning_contract
            and bound_source['semantic_catalog_ref'] == semantic_catalog_ref, 'same_bound_native_source_request')
    authority_facts = verify_plan_authority(root, authority)
    issued = authority._facts()
    source, campaign = issued['source'], issued['campaign']
    _validate_plan_source(plan, source)
    description = _describe(root, source)
    runtime_identity = _run_identity(source, plan, description)
    funding, _rows, registry, entries = _funding(root, planner, run, campaign)
    require(codec.canonical_digest(funding) == codec.canonical_digest(authority_facts['funding']), 'preplan_funding_before_preparation')
    require(not funding['pending_encumbrances'], 'pending_original_publication_before_new_birth')
    require(len(plan['nodes']) <= min(PROFILE[planner][1] - funding['retained_profile_calls'],
            290 - funding['paid_or_unknown_before_run']), 'whole_plan_must_fit_actual_remaining_original_budgets')
    for lineage in runtime_identity['candidate_lineages'].values():
        expected = sum(node['phase'] != 'selection' and lineage in
            {runtime_identity['candidate_lineages'][label] for label in node['candidate_labels']} for node in plan['nodes'])
        require(expected + funding['retained_lineage_calls'].get(lineage, 0) <= 64, 'whole_plan_original_lineage_budget')
    epoch_request = os.environ.get('SC_MVG_RECOVERY_EPOCH')
    require(epoch_request is None or re.fullmatch('[0-9]+', epoch_request) and int(epoch_request) == registry['epoch'], 'original_current_epoch_before_birth')
    original_funding = deepcopy(funding)
    funding, financial_claim = schedule_grant.before_birth(root, plan, funding, runtime_identity)
    host_name = run.relative_to(root).as_posix() + '/b/host.json'
    host = {'schema_version': HOST, 'frozen': source['frozen'], 'source_identity': source['source_identity'],
        'source_request': {'run_id': run_id, 'planner': planner, 'planning_contract': planning_contract,
                           'semantic_catalog_ref': semantic_catalog_ref},
        'observations': [{'path': p, 'raw_base64': base64.b64encode(b).decode('ascii') if b is not None else None}
                         for p, b in source._files.items()],
        'globs': source._globs, 'policy_identity': source._policy}
    host_ref = ref_for(host_name, HOST, wire(host))
    source_identity = {**source['source_identity'], 'host_ref': host_ref}
    base = run.relative_to(root).as_posix()
    initial = {'schema_version': FISCAL_RUN, 'protocol': _core().PROTOCOL, 'input_stage': '3b', 'run_id': run_id,
        'planner': planner, 'segmented_campaign': CAMPAIGN, 'segmented_plan_digest': plan['plan_digest'],
        'segmented_host_ref': host_ref, 'runtime_identity': runtime_identity, 'source_identity': source_identity,
        'native_profile': PROFILE[planner][0], 'mvg.run_invocation_limit': PROFILE[planner][1],
        'checkpoint_strategy': recovery.CHECKPOINT_STRATEGY, 'active_elapsed_seconds': 0,
        'b_route_campaign_funding': deepcopy(funding),
        'capability_selection': {'total_invocations': 0, 'calls': [], 'lineage_invocations': {
            lineage: 0 for lineage in runtime_identity['candidate_lineages'].values()},
            'selected': [], 'current': None, 'terminal': False},
        'phase': 'segmented-prepared', 'selection_status': 'segmented-unselected',
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False,
        'segmented_fiscal_claim': financial_claim}
    import _b_route_segmented_journal as journal
    from _mvg_capability_checkpoint import coordinator_lock
    with recovery.operation_lock(root):
        require(codec.canonical_digest(verify_plan_authority(root, authority)) == codec.canonical_digest(authority_facts),
            'preplan_authority_at_birth_cas')
        verify_candidate_context(root, source)
        now_funding, _rows, current, _entries = _funding(root, planner, run, campaign)
        require(now_funding == original_funding and current['epoch'] == registry['epoch'] and not os.path.lexists(run), 'birth_currentness_cas')
        require(schedule_grant.before_birth(root, plan, now_funding, runtime_identity) == (funding, financial_claim),
                'financial_outside_vs_own_birth_cas')
        run.parent.mkdir(parents=True, exist_ok=True)
        run.mkdir(exist_ok=False)
        with coordinator_lock(run):
            recovery.bind_epoch(root, initial)
            initial_ref = ref_for(base + '/b/initial-run.json', FISCAL_RUN, wire(initial))
            born = {'schema_version': FISCAL_BORN, 'protocol': _core().PROTOCOL, 'plan_digest': plan['plan_digest'],
                'run_id': run_id, 'initial_run_ref': initial_ref, 'initial_calls': 0, 'native_profile': PROFILE[planner][0],
                'source_identity': source_identity, 'runtime_identity': runtime_identity,
                'segmented_fiscal_claim': financial_claim}
            born_ref = ref_for(base + '/b/born.json', FISCAL_BORN, wire(born))
            state = {**initial, 'segmented_born_ref': born_ref}
            actual_after = codec.raw_digest(wire(state))
            stem = hashlib.sha256((str(run.resolve()) + '\0' + plan['plan_digest']).encode()).hexdigest()[:24]
            journal_ref = 'logs/ci/mvg-recovery/activity/segmented-journals/' + stem + '-000-born.json'
            claim_name = base + '/b/claim.json'
            claim = {'schema_version': 'newrouge.b-route-segmented-birth-claim.v1', 'run_path': base + '/run.json',
                'born_ref': born_ref, 'native_after_digest': actual_after, 'journal_ref': journal_ref}
            entry = {'run_path': base + '/run.json', 'born_ref': born_ref, 'planner': planner,
                'epoch': initial['recovery']['epoch'], 'head': {'journal_ref': journal_ref, 'claim_ref': claim_name,
                    'claim_raw_digest': codec.raw_digest(wire(claim)), 'native_run_after_digest': actual_after}}
            with coordinator_lock(_configured_store(root)):
                registry = recovery.registry(root)
                recovery.assert_epoch(root, state, value=registry)
                index = _index(registry)
                require(all(row['run_path'] != entry['run_path'] for row in index['runs']), 'born_index_cannot_replace_run')
                index['runs'].append(entry)
                after_registry = {**registry, 'segmented_runs': index}
                verify_candidate_context(root, source)
                _close_campaign(campaign)
                journal.publish_born(root, run, files={run / 'b/initial-run.json': initial,
                    run / 'b/born.json': born, run / 'b/host.json': host, run / 'b/plan.json': deepcopy(plan),
                    run / 'b/claim.json': claim, run / 'run.json': state}, registry_after=after_registry)
    verify_candidate_context(root, source)
    require(raw(root, base + '/run.json') == wire(state), 'born_publication_exact')
    return {'status': 'segmented-run-prepared', 'run_ref': base + '/run.json', 'born_ref': born_ref,
        'host_ref': host_ref, 'plan_digest': plan['plan_digest'], 'logical_calls': 0,
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False}


def _birth_v1(root, run, state, plan, obs):
    """Recheck the immutable directed birth alongside legitimate paid progress."""
    base = run.relative_to(root).as_posix()
    require(state.get('schema_version') == RUN and state.get('run_id') == plan['run_id']
        and state.get('planner') == plan['planner'] and state.get('segmented_plan_digest') == plan['plan_digest']
        and state.get('segmented_campaign') == CAMPAIGN and state.get('protocol') == _core().PROTOCOL,
        'actual_segmented_birth_required')
    require(reference(state['segmented_born_ref'])['path'] == base + '/b/born.json'
        and state['segmented_born_ref']['schema_version'] == _core().BORN, 'exact_original_born_locator')
    _, born = read_ref(obs, state['segmented_born_ref'])
    closed(born, ('schema_version', 'protocol', 'plan_digest', 'run_id', 'initial_run_ref', 'initial_calls',
        'native_profile', 'source_identity', 'runtime_identity'), 'closed_original_born')
    require(born['schema_version'] == _core().BORN and born['run_id'] == plan['run_id']
        and born['plan_digest'] == plan['plan_digest'] and born['protocol'] == _core().PROTOCOL
        and born['native_profile'] == PROFILE[plan['planner']][0]
        and type(born['initial_calls']) is int and born['initial_calls'] == 0, 'actual_born_identity')
    require(reference(born['initial_run_ref'])['path'] == base + '/b/initial-run.json'
        and born['initial_run_ref']['schema_version'] == RUN, 'exact_original_initial_locator')
    _, initial = read_ref(obs, born['initial_run_ref'])
    require(initial['schema_version'] == RUN and initial['capability_selection']['calls'] == []
        and type(initial['capability_selection']['total_invocations']) is int
        and initial['capability_selection']['total_invocations'] == 0 and 'segmented_born_ref' not in initial
        and state['runtime_identity'] == initial['runtime_identity'] == born['runtime_identity']
        and state['source_identity'] == initial['source_identity'] == born['source_identity'], 'immutable_zero_call_directed_birth')
    mutable = {'capability_selection', 'active_elapsed_seconds', 'segmented_born_ref'}
    require(codec.canonical_digest({k: v for k, v in state.items() if k not in mutable})
        == codec.canonical_digest({k: v for k, v in initial.items() if k not in mutable}), 'immutable_born_controls_changed')
    ledger_mutable = {'calls', 'total_invocations', 'lineage_invocations'}
    require(codec.canonical_digest({k: v for k, v in state['capability_selection'].items() if k not in ledger_mutable})
        == codec.canonical_digest({k: v for k, v in initial['capability_selection'].items() if k not in ledger_mutable}),
        'segmented_ledger_does_not_grant_native_selected')
    require(reference(state['segmented_host_ref'])['path'] == base + '/b/host.json'
        and state['segmented_host_ref']['schema_version'] == HOST
        and state['source_identity']['host_ref'] == state['segmented_host_ref'], 'original_host_ref_binding')
    return initial

def _birth(root, run, state, plan, obs):
    if state.get('schema_version') == FISCAL_RUN:
        return _birth_fiscal(root, run, state, plan, obs)
    require('segmented_fiscal_claim' not in state, 'mixed_old_native_financial_family')
    return _birth_v1(root, run, state, plan, obs)

def _birth_fiscal(root, run, state, plan, obs):
    """Recheck the immutable directed birth alongside legitimate paid progress."""
    base = run.relative_to(root).as_posix()
    require(state.get('schema_version') == FISCAL_RUN and state.get('run_id') == plan['run_id']
        and state.get('planner') == plan['planner'] and state.get('segmented_plan_digest') == plan['plan_digest']
        and state.get('segmented_campaign') == CAMPAIGN and state.get('protocol') == _core().PROTOCOL,
        'actual_segmented_birth_required')
    require(reference(state['segmented_born_ref'])['path'] == base + '/b/born.json'
        and state['segmented_born_ref']['schema_version'] == FISCAL_BORN, 'exact_original_born_locator')
    _, born = read_ref(obs, state['segmented_born_ref'])
    closed(born, ('schema_version', 'protocol', 'plan_digest', 'run_id', 'initial_run_ref', 'initial_calls',
        'native_profile', 'source_identity', 'runtime_identity', 'segmented_fiscal_claim'), 'closed_original_born')
    require(born['schema_version'] == FISCAL_BORN and born['run_id'] == plan['run_id']
        and born['plan_digest'] == plan['plan_digest'] and born['protocol'] == _core().PROTOCOL
        and born['native_profile'] == PROFILE[plan['planner']][0]
        and type(born['initial_calls']) is int and born['initial_calls'] == 0, 'actual_born_identity')
    require(reference(born['initial_run_ref'])['path'] == base + '/b/initial-run.json'
        and born['initial_run_ref']['schema_version'] == FISCAL_RUN, 'exact_original_initial_locator')
    _, initial = read_ref(obs, born['initial_run_ref'])
    require(initial['schema_version'] == FISCAL_RUN and initial['capability_selection']['calls'] == []
        and type(initial['capability_selection']['total_invocations']) is int
        and initial['capability_selection']['total_invocations'] == 0 and 'segmented_born_ref' not in initial
        and state['runtime_identity'] == initial['runtime_identity'] == born['runtime_identity']
        and state['source_identity'] == initial['source_identity'] == born['source_identity'], 'immutable_zero_call_directed_birth')
    mutable = {'capability_selection', 'active_elapsed_seconds', 'segmented_born_ref'}
    require(codec.canonical_digest({k: v for k, v in state.items() if k not in mutable})
        == codec.canonical_digest({k: v for k, v in initial.items() if k not in mutable}), 'immutable_born_controls_changed')
    ledger_mutable = {'calls', 'total_invocations', 'lineage_invocations'}
    require(codec.canonical_digest({k: v for k, v in state['capability_selection'].items() if k not in ledger_mutable})
        == codec.canonical_digest({k: v for k, v in initial['capability_selection'].items() if k not in ledger_mutable}),
        'segmented_ledger_does_not_grant_native_selected')
    require(reference(state['segmented_host_ref'])['path'] == base + '/b/host.json'
        and state['segmented_host_ref']['schema_version'] == HOST
        and state['source_identity']['host_ref'] == state['segmented_host_ref'], 'original_host_ref_binding')
    import _b_route_segmented_funding as funding_owner
    require(born['segmented_fiscal_claim'] == initial['segmented_fiscal_claim']
            == state['segmented_fiscal_claim'] == funding_owner.financial_birth_reference(root, plan),
            'genuine_original_financial_claim_bound_birth')
    return initial


def _load_source_for_run(root, run, plan):
    state = value(root, run.relative_to(root).as_posix() + '/run.json')
    obs = sources.Observations(root)
    _birth(root, run, state, plan, obs)
    _, host = read_ref(obs, state['segmented_host_ref'])
    closed(host, ('schema_version', 'frozen', 'source_identity', 'source_request', 'observations', 'globs', 'policy_identity'),
        'closed_original_host_archive')
    require(host['schema_version'] == HOST and host['policy_identity'] == policy_identity(), 'current_segmented_host_policy')
    source = capture_source(root, **host['source_request'])
    _validate_plan_source(plan, source)
    require(source['frozen'] == host['frozen'] and source['source_identity'] == host['source_identity'], 'actual_original_host_source_reproduced')
    expected = [{'path': p, 'raw_base64': base64.b64encode(b).decode('ascii') if b is not None else None}
                for p, b in source._files.items()]
    require(expected == host['observations'] and source._globs == host['globs'], 'complete_original_host_observation_archive')
    obs.verify()
    return source


@contextmanager
def verified_run(root, run_dir, plan):
    """Fresh full qualification before locks; action-local facts, never saved approval."""
    root, run = Path(root).absolute(), Path(run_dir).absolute()
    require(_ACTIVE.get() is None, 'no_nested_or_cross_run_action_capture')
    require(run == _homes(root, plan['planner'], plan['run_id']), 'exact_original_run_path')
    source = _load_source_for_run(root, run, plan)
    campaign = _capture_campaign(root)
    token = _ACTIVE.set({'root': root, 'run': run, 'plan': deepcopy(plan), 'source': source, 'campaign': campaign})
    try:
        yield
        verify_candidate_context(root, source)
        _close_campaign(campaign)
    finally:
        _ACTIVE.reset(token)


def _active(root, run, plan):
    active = _ACTIVE.get()
    require(active is not None and active['root'] == Path(root).absolute() and active['run'] == Path(run).absolute()
        and codec.canonical_digest(active['plan']) == codec.canonical_digest(plan), 'genuine_action_context_before_metadata_locks')
    verify_candidate_context(root, active['source'])
    return active


def candidate_context(root, run_dir, plan):
    active = _active(root, run_dir, plan)
    return active['source']


def excluded_turns(root, run_dir, plan):
    source = _active(root, run_dir, plan)['source']
    return deepcopy(source['source_identity']['upstream_turns'])


def assert_paid_reservation(root, plan, node, reservation):
    """Observe one real permanent native charge, never a result/dispatch grant.

    This is a direct fresh assertion, not a verifier of a caller-provided paid
    witness. It intentionally uses only B's metadata reader plus original index
    and journal history, never session.snapshot or a core result replay.
    """
    import _b_route_segmented_journal as journal
    root = Path(root).absolute()
    run = _homes(root, plan['planner'], plan['run_id'])
    active = _active(root, run, plan)
    _close_campaign(active['campaign'])
    require(type(node) is dict and type(node.get('ordinal')) is int
        and 0 <= node['ordinal'] < len(plan['nodes'])
        and codec.canonical_digest(node) == codec.canonical_digest(plan['nodes'][node['ordinal']]),
        'paid_exact_original_plan_node')
    require(type(reservation) is dict and 'outcome' not in reservation, 'paid_original_reservation_without_later_outcome')
    obs = sources.Observations(root)
    name = (run / 'run.json').relative_to(root).as_posix()
    state = obs.json(name)
    registry = obs.json('logs/ci/mvg-recovery/registry.json')
    current, entries = _registry_entries(root)
    require(codec.canonical_digest(registry) == codec.canonical_digest(current)
        and name in entries and entries[name]['epoch'] == current['epoch'] == state['recovery']['epoch']
        and entries[name]['born_ref'] == state['segmented_born_ref'], 'paid_current_registered_birth_epoch')
    recovery.assert_epoch(root, state, value=current)
    _history(root, entries[name], state)
    paid_rows = [row for row in state['capability_selection']['calls']
                 if row.get('reservation_id') == reservation.get('reservation_id')]
    require(len(paid_rows) == 1
        and codec.canonical_digest({k: v for k, v in paid_rows[0].items() if k != 'outcome'}) == codec.canonical_digest(reservation),
        'paid_original_row_missing_or_caller_changed')
    observed = journal.inspect_reservation_metadata(root, run, plan=plan, node=node, reservation=reservation)
    require(observed['run_ref'] == name and observed['run_raw_digest'] == codec.raw_digest(obs.files[name])
        and codec.canonical_digest(observed['original_reservation']) == codec.canonical_digest(reservation),
        'paid_actual_original_native_reservation')
    actual = observed['actual_row']
    require(codec.canonical_digest({k: v for k, v in actual.items() if k != 'outcome'}) == codec.canonical_digest(reservation),
        'paid_native_row_only_appends_original_outcome')
    workspace_role = (run / 'q' / ('n' + str(node['ordinal'])) / 'm').relative_to(root).as_posix()
    expected_workspace = str(path(root, workspace_role).resolve())
    identity = reservation.get('request_identity')
    mapping = state['runtime_identity']['candidate_lineages']
    lineages = [] if node['phase'] == 'selection' else sorted({mapping[label] for label in node['candidate_labels']})
    require(type(identity) is dict and identity.get('protocol') == plan['protocol']
        and identity.get('plan_digest') == plan['plan_digest'] and identity.get('node_id') == node['node_id']
        and identity.get('phase') == node['phase'] and observed['workspace'] == expected_workspace
        and reservation.get('workspace') == expected_workspace and reservation.get('run_id') == plan['run_id']
        and reservation.get('phase') == node['phase'] and reservation.get('candidate_labels') == node['candidate_labels']
        and reservation.get('lineage_ids') == lineages
        and reservation.get('candidate') == (lineages[0] if len(lineages) == 1 else None)
        and codec.canonical_digest(reservation.get('model_identity')) == codec.canonical_digest(state['runtime_identity'])
        and observed['claim']['registry_epoch'] == current['epoch'], 'paid_exact_phase_request_workspace_runtime')
    require(observed['claim_ref']['path'] == (run / 'q' / ('n' + str(node['ordinal'])) / 'claim.json').relative_to(root).as_posix()
        and observed['aux_ref']['path'] == (run / 'q/state.json').relative_to(root).as_posix()
        and observed['head_ref']['path'] == 'logs/ci/mvg-recovery/activity/segmented-active.json',
        'paid_original_claim_aux_head_locators')
    for ref in (observed['claim_ref'], observed['aux_ref'], observed['head_ref']):
        read_ref(obs, ref)
    require(observed['claim_ref']['raw_digest'] == codec.raw_digest(obs.files[observed['claim_ref']['path']])
        and observed['aux_ref']['raw_digest'] == codec.raw_digest(obs.files[observed['aux_ref']['path']])
        and observed['head_ref']['raw_digest'] == codec.raw_digest(obs.files[observed['head_ref']['path']]),
        'paid_metadata_raw_pins')
    # Close the full original metadata prefix again without result/protocol
    # recursion; all relevant authoritative files must remain the same bytes.
    _history(root, entries[name], state)
    obs.verify()
    verify_candidate_context(root, active['source'])
    _close_campaign(active['campaign'])
    obs.verify()
    result = {'schema_version': ('newrouge.b-route-segmented-paid-reservation.fiscal-v2'
            if state['schema_version'] == FISCAL_RUN else 'newrouge.b-route-segmented-paid-reservation.v1'),
        'protocol': plan['protocol'], 'plan_digest': plan['plan_digest'], 'node_id': node['node_id'],
        'reservation_id': reservation['reservation_id'], 'number': reservation['number'],
        'run_ref': ref_for(name, state['schema_version'], obs.files[name]),
        'registry_ref': ref_for('logs/ci/mvg-recovery/registry.json', recovery.SCHEMA,
            obs.files['logs/ci/mvg-recovery/registry.json']),
        'registry_epoch': current['epoch'], 'claim_ref': deepcopy(observed['claim_ref']),
        'aux_ref': deepcopy(observed['aux_ref']), 'head_ref': deepcopy(observed['head_ref']),
        'reservation_digest': codec.canonical_digest(reservation), 'actual_row_digest': codec.canonical_digest(actual),
        'publication': 'encumbered', 'released': 0}
    result['witness_digest'] = codec.canonical_digest(result)
    return result


def _segmented_run_contract_v1(root, state, run_dir, *, plan_digest, protocol):
    """Fresh native budget/source witness only for a genuinely born new run."""
    root, run = Path(root).absolute(), Path(run_dir).absolute()
    require(state.get('schema_version') == RUN and state.get('run_id') not in {'c4', 'm4'}, 'legacy_or_flag_only_run_rejected')
    active = _ACTIVE.get()
    require(active is not None, 'full_verified_run_capture_before_metadata_locks')
    plan = active['plan']
    require(plan_digest == plan['plan_digest'] and protocol == _core().PROTOCOL, 'same_original_plan_protocol')
    active = _active(root, run, plan)
    name = (run / 'run.json').relative_to(root).as_posix()
    require(codec.canonical_digest(value(root, name)) == codec.canonical_digest(state), 'actual_live_native_state')
    obs = sources.Observations(root)
    _birth(root, run, state, plan, obs)
    obs.verify()
    funding, _rows, registry, entries = _funding(root, plan['planner'], run, active['campaign'])
    require(name in entries and entries[name]['epoch'] == registry['epoch'] == state['recovery']['epoch'], 'current_original_epoch_and_index')
    require(entries[name]['born_ref'] == state['segmented_born_ref'], 'actual_registered_birth')
    recovery.assert_epoch(root, state, value=registry)
    require(state['runtime_identity']['source_policy'] == policy_identity()
        and state['runtime_identity']['host_input_identity'] == active['source']['frozen']['input_identity'], 'actual_current_runtime_source')
    declared = state['b_route_campaign_funding']
    require(funding['paid_or_unknown_before_run'] >= declared['paid_or_unknown_before_run']
        and funding['retained_profile_calls'] >= declared['retained_profile_calls'], 'no_released_retained_liabilities')
    return {'schema_version': _core().NATIVE_RUN, 'protocol': protocol, 'plan_digest': plan_digest,
        'run_id': plan['run_id'], 'planner': plan['planner'], 'run_path': name, 'run_raw_digest': codec.raw_digest(raw(root, name)),
        'born_ref': deepcopy(state['segmented_born_ref']), 'native_profile': PROFILE[plan['planner']][0],
        'registry_store': str(_configured_store(root)), 'registry_epoch': registry['epoch'],
        'source_identity': deepcopy(state['source_identity']), 'runtime_identity': deepcopy(state['runtime_identity']),
        'funding': funding, 'candidate_lineages': deepcopy(state['runtime_identity']['candidate_lineages']),
        'native_limit': PROFILE[plan['planner']][1]}

def segmented_run_contract(root, state, run_dir, *, plan_digest, protocol):
    if state.get('schema_version') == FISCAL_RUN:
        return _segmented_run_contract_fiscal(root, state, run_dir, plan_digest=plan_digest, protocol=protocol)
    require('segmented_fiscal_claim' not in state, 'mixed_old_native_financial_family')
    return _segmented_run_contract_v1(root, state, run_dir, plan_digest=plan_digest, protocol=protocol)

def _segmented_run_contract_fiscal(root, state, run_dir, *, plan_digest, protocol):
    """Fresh native budget/source witness only for a genuinely born new run."""
    root, run = Path(root).absolute(), Path(run_dir).absolute()
    require(state.get('schema_version') == FISCAL_RUN and state.get('run_id') not in {'c4', 'm4'}, 'legacy_or_flag_only_run_rejected')
    active = _ACTIVE.get()
    require(active is not None, 'full_verified_run_capture_before_metadata_locks')
    plan = active['plan']
    require(plan_digest == plan['plan_digest'] and protocol == _core().PROTOCOL, 'same_original_plan_protocol')
    active = _active(root, run, plan)
    name = (run / 'run.json').relative_to(root).as_posix()
    require(codec.canonical_digest(value(root, name)) == codec.canonical_digest(state), 'actual_live_native_state')
    obs = sources.Observations(root)
    _birth(root, run, state, plan, obs)
    obs.verify()
    funding, _rows, registry, entries = _funding(root, plan['planner'], run, active['campaign'])
    require(name in entries and entries[name]['epoch'] == registry['epoch'] == state['recovery']['epoch'], 'current_original_epoch_and_index')
    require(entries[name]['born_ref'] == state['segmented_born_ref'], 'actual_registered_birth')
    recovery.assert_epoch(root, state, value=registry)
    require(state['runtime_identity']['source_policy'] == policy_identity()
        and state['runtime_identity']['host_input_identity'] == active['source']['frozen']['input_identity'], 'actual_current_runtime_source')
    import _b_route_segmented_funding as funding_owner
    funding = funding_owner.current_fiscal_funding(funding)
    declared = state['b_route_campaign_funding']
    require(funding['paid_or_unknown_before_run'] >= declared['paid_or_unknown_before_run']
        and funding['retained_profile_calls'] >= declared['retained_profile_calls'], 'no_released_retained_liabilities')
    return {'schema_version': FISCAL_NATIVE_RUN, 'protocol': protocol, 'plan_digest': plan_digest,
        'run_id': plan['run_id'], 'planner': plan['planner'], 'run_path': name, 'run_raw_digest': codec.raw_digest(raw(root, name)),
        'born_ref': deepcopy(state['segmented_born_ref']), 'native_profile': PROFILE[plan['planner']][0],
        'registry_store': str(_configured_store(root)), 'registry_epoch': registry['epoch'],
        'source_identity': deepcopy(state['source_identity']), 'runtime_identity': deepcopy(state['runtime_identity']),
        'funding': funding, 'candidate_lineages': deepcopy(state['runtime_identity']['candidate_lineages']),
        'native_limit': PROFILE[plan['planner']][1]}


def request_timeout(root, run_dir, state, plan, node, witness):
    active = _active(root, run_dir, plan)
    actual = segmented_run_contract(root, state, run_dir, plan_digest=plan['plan_digest'], protocol=_core().PROTOCOL)
    require(codec.canonical_digest(actual) == codec.canonical_digest(witness), 'fresh_timeout_budget_witness')
    funding, retained, _registry, _entries = _funding(Path(root).absolute(), plan['planner'], Path(run_dir).absolute(), active['campaign'])
    if plan['planner'] == 'mvg':
        return 1800
    rows = [*retained, *state['capability_selection']['calls']]
    remaining = 13500 - sum(_activity(row) for row in rows)
    supports = state['runtime_identity']['runner']['description'].get('supports_synthesis_budget') is True
    maximum = 1200 if node['phase'] == 'synthesis' and supports else 2700
    mapping = state['runtime_identity']['candidate_lineages']
    lineages = [] if node['phase'] == 'selection' else [mapping[label] for label in node['candidate_labels']]
    for lineage in lineages:
        spent = sum(_activity(row) for row in rows if lineage in _rows_lineages(row))
        remaining = min(remaining, 2700 + (1200 if supports else 0) - spent)
    timeout = math.floor(min(maximum, remaining))
    require(timeout >= 1, 'original_active_time_pool_exhausted')
    return timeout


# Finite-schedule fiscal hooks. Called only by the original source-bound Root
# issuer and the original native Session/workflow frames; no public dict mint.
def _financial_issuer(owner):
    import _b_route_segmented_funding as funding
    funding.require_original_owner(owner)
    require(owner.owners['runtime'] is sys.modules[__name__], 'actual_financial_runtime_owner')
    return funding


def _financial_frame(session, method, **values):
    import _b_route_segmented_journal as journal
    require(type(session) is journal._Session and session._seal is journal._SEAL,
            'actual_original_financial_session')
    fn = getattr(journal._Session, method)
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code is fn.__code__ and frame.f_globals is journal.__dict__:
            require(frame.f_locals.get('self') is session
                    and all(frame.f_locals.get(k) is v for k, v in values.items()),
                    'same_original_native_financial_frame_values')
            session._live()
            return frame
        frame = frame.f_back
    raise ValueError('original_native_financial_frame_required')


def merge_outside_liabilities(root_paid, root_guard, native, new_sibling_charges):
    """Pure DATA arithmetic; only original owners make these values authoritative."""
    values = (root_paid, root_guard, native['paid_or_unknown_before_run'],
              native['subsequent_full_reservation'], new_sibling_charges)
    require(all(type(v) is int and v >= 0 for v in values), 'original_financial_integer_counts')
    # Original _funding excludes own and computes legacy paid + new sibling
    # charges. U06 already holds that legacy graph and its H1/H2/H3 liabilities;
    # only those newly registered native sibling charges are added once.
    require(new_sibling_charges <= native['paid_or_unknown_before_run']
            and native['paid_or_unknown_before_run'] - new_sibling_charges <= root_paid,
            'same_retained_original_native_coverage')
    require(native['subsequent_full_reservation'] == 0, 'original_unmerged_native_funding_family')
    paid = root_paid + new_sibling_charges
    guard = root_guard + new_sibling_charges
    require(0 <= root_paid <= root_guard <= 290 and paid <= guard <= 290,
            'original_overlapping_liability_bounds')
    return paid, guard


def _financial_claim_from_facts(owner, facts, plan, identity, campaign):
    # Internal construction only; the public preclaim/archive entrypoints obtain
    # facts through their original owner. Its DATA return cannot mint a grant.
    description = identity['runner']['description']
    root_paid, root_guard = owner._outside()
    native = facts['funding']
    require(not native['pending_encumbrances'], 'original_pending_before_financial_claim')
    # These views overlap. Preserve original occupied liabilities without adding
    # paid to guard or adding the native run's own rows a second time.
    native_legacy_paid = campaign.base_global + len(campaign.mvg_rows)
    new_sibling_charges = native['paid_or_unknown_before_run'] - native_legacy_paid
    paid, guard = merge_outside_liabilities(root_paid, root_guard, native, new_sibling_charges)
    b = owner.c['binding']
    require(b['run_id'] == plan['run_id'] and b['planner'] == plan['planner']
            and b['epoch'] == facts['registry_epoch']
            and b['source_policy_digest'] == codec.canonical_digest(facts['source_policy']),
            'actual_config_plan_epoch_policy')
    labels = [r['label'] for r in plan['manifest']['candidates']]
    retained = facts['retained_time']
    # Native time is taken from its real fact shape; this hook does not reset it.
    require(set(retained) == {'total_active_seconds', 'lineage_active_seconds'},
            'original_retained_time_shape')
    from _capability_input_integrity import configured_input_limit
    claim = {'schema_version': owner.prefix.CLAIM, 'kind': 'claim',
        'allocation_id': plan['plan_digest'],
        'binding': {'root': str(owner.root), 'source_root': str(owner.source),
            'run_id': plan['run_id'], 'planner': plan['planner'], 'profile': PROFILE[plan['planner']][0],
            'epoch': facts['registry_epoch'], 'plan_digest': plan['plan_digest'],
            'source_input_identity': facts['source_input_identity'],
            'source_policy_digest': codec.canonical_digest(facts['source_policy']),
            'request_policy_digest': codec.canonical_digest(owner.owners['workflow'].policy_identity(owner.root)),
            'runtime_identity_digest': codec.canonical_digest(identity)},
        'nodes': deepcopy(plan['nodes']), 'node_catalog_digest': codec.canonical_digest(plan['nodes']),
        'candidate_labels': labels, 'candidate_lineages': identity['candidate_lineages'],
        'hold': len(plan['nodes']), 'base_paid_or_unknown': paid, 'outside_guard': guard,
        'guard_occupancy': guard + len(plan['nodes']), 'campaign_limit': 290, 'released': 0,
        'retained_profile_calls': native['retained_profile_calls'],
        'retained_lineage_calls': deepcopy(native['retained_lineage_calls']),
        'time_policy': {'supports_synthesis_budget': description.get('supports_synthesis_budget') is True,
            'retained_total_active_seconds': retained['total_active_seconds'],
            'retained_lineage_active_seconds': deepcopy(retained['lineage_active_seconds'])},
        'context_limit': min(96000, configured_input_limit())}
    owner.prefix._claim(claim)
    return claim, {'outside_root_budget': (root_paid, root_guard),
                   'original_native_funding': deepcopy(native), 'runtime_identity': identity,
                   'native_legacy_paid': native_legacy_paid, 'new_sibling_charges': new_sibling_charges}


def financial_preclaim(owner, authority, plan):
    _financial_issuer(owner)
    facts = verify_plan_authority(owner.root, authority)
    issued = authority._facts()
    _validate_plan_source(plan, issued['source'])
    owner.owners['workflow'].validate_plan(plan)
    owner.owners['planner']._limits(facts, plan['nodes'])
    description = _describe(owner.root, issued['source'])
    identity = _run_identity(issued['source'], plan, description)
    claim, native_state = _financial_claim_from_facts(owner, facts, plan, identity, issued['campaign'])
    require(verify_plan_authority(owner.root, authority) == facts
            and owner._outside() == native_state['outside_root_budget'],
            'financial_preclaim_current_source_and_outside')
    return claim, native_state

def financial_current(owner, native_state):
    _financial_issuer(owner)
    facade = _financial_issuer(owner)
    if not facade.in_archive_scope(owner):
        owner.store._held()
    snapshot = owner.store._fresh_snapshot()
    rows = [owner.h.parse(row['raw']) for name, row in sorted(snapshot['members'].items()) if name != 'STOP.json']
    intents = [row['event'] for row in rows if row['event']['kind'] == 'intent']
    run = _homes(owner.root, owner.plan['planner'], owner.plan['run_id'])
    if not os.path.lexists(run):
        require(not intents, 'native_missing_with_retained_financial_intent')
        verify_plan_authority(owner.root, owner.authority)
        return []
    # Outside a workflow action (e.g. final lease close), use the ORIGINAL
    # full readonly owner action. One bounded re-entry: verified_run installs
    # _ACTIVE before the recursive collection; this never dispatches/reserves.
    if _ACTIVE.get() is None:
        with verified_run(owner.root, run, owner.plan):
            return financial_current(owner, native_state)
    active = _active(owner.root, run, owner.plan)
    state = value(owner.root, (run / 'run.json').relative_to(owner.root).as_posix())
    obs = sources.Observations(owner.root)
    _birth(owner.root, run, state, owner.plan, obs)
    obs.verify()
    registry, entries = _registry_entries(owner.root)
    name = (run / 'run.json').relative_to(owner.root).as_posix()
    require(name in entries and registry['epoch'] == owner.store._claim()['binding']['epoch'],
            'same_actual_financial_native_registered_epoch')
    _history(owner.root, entries[name], state)
    observations = []
    calls = state['capability_selection']['calls']
    for event in intents:
        name = event['native_claim_ref']['path']
        claim_path = path(owner.root, name)
        claim_raw = raw(owner.root, name) if os.path.lexists(claim_path) else None
        matches = [row for row in calls if row['reservation_id'] == event['reservation_id']]
        require(len(matches) <= 1, 'actual_native_reservation_unique')
        outcome = matches[0].get('outcome') if matches else None
        result_digest = None
        if outcome is not None:
            result_name = str(Path(name).parent.as_posix()) + '/result.json'
            result = value(owner.root, result_name)
            result_digest = result['result_digest']
            require(outcome['segmented_result_digest'] == result_digest, 'actual_native_result_digest')
        observations.append({'node_id': event['node_id'], 'claim_path': name, 'claim_raw': claim_raw,
            'outcome_raw': owner.prefix.canonical(outcome) if outcome is not None else None,
            'verified_result_digest': result_digest})
    verify_candidate_context(owner.root, active['source'])
    return observations


def financial_reservation(owner, session, node, reservation, claim, claim_path, before):
    _financial_issuer(owner)
    frame = _financial_frame(session, 'reserve', node=node, reservation=reservation, claim=claim, claim_path=claim_path)
    require(session.root == owner.root and session.plan == owner.plan
            and before['facts']['prefix_disposition'] == 'open-settled-prefix', 'same_settled_financial_native_plan')
    from _capability_input_integrity import configured_input_limit
    measured = reservation['request_identity']['input_measurement']
    require(measured['input_token_estimate'] + reservation['request_identity']['output_reserve']
            <= min(96000, configured_input_limit(), owner.store._claim()['context_limit']),
            'original_current_capacity_before_financial_intent')
    ordinal = before['facts']['intent_count']
    require(node == owner.plan['nodes'][ordinal] and reservation['number'] == ordinal + 1,
            'actual_next_original_native_reservation')
    import _b_route_segmented_journal as journal
    native_raw = journal._json_bytes(claim)
    claim_ref = {'path': claim_path.relative_to(owner.root).as_posix(),
                 'schema_version': journal.CLAIM, 'raw_digest': codec.raw_digest(native_raw)}
    financial = owner.store._claim()
    event = {'schema_version': owner.prefix.INTENT, 'kind': 'intent', 'allocation_id': financial['allocation_id'],
        'node_id': node['node_id'], 'ordinal': ordinal, 'reservation_id': reservation['reservation_id'],
        'paid_or_unknown': financial['base_paid_or_unknown'] + ordinal + 1,
        'guard_occupancy': financial['guard_occupancy'], 'hold': financial['hold'], 'released': 0,
        'node_digest': codec.canonical_digest(node), 'reservation': deepcopy(reservation),
        'reservation_digest': codec.canonical_digest(reservation),
        'request_identity_digest': codec.canonical_digest(reservation['request_identity']), 'native_claim_ref': claim_ref}
    after_native = [*before['native'], {'node_id': node['node_id'], 'claim_path': claim_ref['path'],
        'claim_raw': None, 'outcome_raw': None, 'verified_result_digest': None}]
    return event, after_native


def financial_persisted(owner, session, reservation):
    _financial_issuer(owner)
    import _b_route_segmented_journal as journal
    workflow = _core()
    require(type(session) is journal._Session and session._seal is journal._SEAL
            and session.root == owner.root and session.plan == owner.plan, 'same_original_paid_session')
    frame = sys._getframe(1)
    found = False
    while frame is not None:
        reserve = (frame.f_code is journal._Session.reserve.__code__ and frame.f_globals is journal.__dict__
                   and frame.f_locals.get('self') is session)
        dispatch = (frame.f_code is workflow._execute_verified.__code__ and frame.f_globals is workflow.__dict__
                    and frame.f_locals.get('session') is session)
        if (reserve or dispatch) and frame.f_locals.get('reservation') is reservation:
            found = True
            break
        frame = frame.f_back
    require(found, 'original_reserve_or_dispatch_frame_before_paid_node')
    session._live()
    state, witness, _budget = session._fresh()
    require(state['schema_version'] == FISCAL_RUN and state['runtime_identity'] == owner.native_state['runtime_identity'],
            'actual_fiscal_birth_before_paid_dispatch')
    snapshot = owner.store._fresh_snapshot()
    rows = [owner.h.parse(row['raw']) for name, row in sorted(snapshot['members'].items()) if name != 'STOP.json']
    require(rows[-1]['event'].get('kind') == 'intent'
            and rows[-1]['event']['reservation'] == reservation, 'exact_unsettled_financial_intent')
    observations = financial_current(owner, owner.native_state)
    require(observations[-1]['claim_raw'] is not None and observations[-1]['outcome_raw'] is None,
            'genuine_native_persisted_not_already_completed')
    from _capability_input_integrity import configured_input_limit
    request = reservation['request_identity']
    measurement = request['input_measurement']
    require(measurement['input_token_estimate'] + request['output_reserve']
            <= min(96000, configured_input_limit(), owner.store._claim()['context_limit']),
            'original_current_configured_input_output_total')
    return None


def financial_outcome(owner, session, reservation, verified_result, before):
    _financial_issuer(owner)
    _financial_frame(session, 'complete', reservation=reservation, verified_result=verified_result)
    node = owner.plan['nodes'][before['facts']['intent_count'] - 1]
    value = _core().validate_verified_result(owner.plan, node, reservation, verified_result)
    actual = before['native'][-1]
    require(actual['outcome_raw'] is not None and actual['verified_result_digest'] == value['result_digest'],
            'real_native_completed_result_before_financial_outcome')
    rows = [owner.h.parse(row['raw']) for name, row in sorted(before['snapshot']['members'].items()) if name != 'STOP.json']
    previous = rows[-1]
    require(previous['event']['kind'] == 'intent' and previous['event']['reservation'] == reservation,
            'exact_original_pending_intent')
    financial = owner.store._claim()
    return {'schema_version': owner.prefix.OUTCOME, 'kind': 'outcome', 'allocation_id': financial['allocation_id'],
        'node_id': node['node_id'], 'ordinal': node['ordinal'], 'reservation_id': reservation['reservation_id'],
        'paid_or_unknown': financial['base_paid_or_unknown'] + before['facts']['intent_count'],
        'guard_occupancy': financial['guard_occupancy'], 'hold': financial['hold'], 'released': 0,
        'intent_row_sha256': previous['sha256'], 'native_outcome_digest': codec.raw_digest(actual['outcome_raw']),
        'verified_result_digest': value['result_digest']}


def financial_birth(owner, root, plan, native_funding, runtime_identity):
    _financial_issuer(owner)
    owner.store._held()
    require(Path(root).absolute() == owner.root and plan == owner.plan
            and runtime_identity == owner.native_state['runtime_identity']
            and native_funding == owner.native_state['original_native_funding'],
            'exact_preclaim_native_birth_facts')
    require(verify_plan_authority(owner.root, owner.authority)['funding'] == native_funding,
            'original_fresh_authority_at_financial_birth')
    require(owner._outside() == owner.native_state['outside_root_budget'], 'outside_funding_at_birth')
    claim = owner.store._claim()
    declared = deepcopy(native_funding)
    declared.update(paid_or_unknown_before_run=claim['base_paid_or_unknown'],
                    subsequent_full_reservation=290 - claim['base_paid_or_unknown'] - claim['hold'],
                    maximum_native_charges=claim['hold'])
    require(len(plan['nodes']) <= declared['maximum_native_charges'], 'original_full_schedule_at_birth')
    return declared, financial_reference(owner, root, plan)


def financial_reference(owner, root, plan):
    _financial_issuer(owner)
    owner.store._held()
    require(Path(root).absolute() == owner.root and plan == owner.plan, 'same_financial_birth_source_plan')
    snapshot = owner.store._fresh_snapshot()
    first = snapshot['members']['000001.json']
    require(owner.h.parse(first['raw'])['event'] == owner.store._claim(), 'actual_financial_claim_bytes')
    return {'schema_version': 'task.segmented-schedule-native-birth-support.v1',
        'config': {'path': str(owner.config_path), 'sha256': owner.config_sha},
        'claim': {'path': str(owner.store.ledger / '000001.json'), 'sha256': first['sha256']},
        'plan_digest': plan['plan_digest'], 'allocation_id': owner.store._claim()['allocation_id'],
        'hold': len(plan['nodes']), 'released': 0}


def financial_funding(owner, native_funding):
    _financial_issuer(owner)
    owner.store._held()
    require(owner._outside() == owner.native_state['outside_root_budget']
            and native_funding == owner.native_state['original_native_funding'],
            'outside_vs_own_native_financial_currentness')
    claim = owner.store._claim()
    merged = deepcopy(native_funding)
    merged.update(paid_or_unknown_before_run=claim['base_paid_or_unknown'],
                  subsequent_full_reservation=290 - claim['base_paid_or_unknown'] - claim['hold'],
                  maximum_native_charges=claim['hold'])
    return merged


def financial_archive_reference(owner, root, plan):
    facade = _financial_issuer(owner)
    require(facade.in_archive_scope(owner) and Path(root).absolute() == owner.root and plan == owner.plan,
            'actual_archive_birth_reference_scope')
    snapshot = owner.store._fresh_snapshot()
    first = snapshot['members']['000001.json']
    require(owner.h.parse(first['raw'])['event'] == owner.store._claim(), 'actual_archived_financial_claim_bytes')
    return {'schema_version': 'task.segmented-schedule-native-birth-support.v1',
        'config': {'path': str(owner.config_path), 'sha256': owner.config_sha},
        'claim': {'path': str(owner.store.ledger / '000001.json'), 'sha256': first['sha256']},
        'plan_digest': plan['plan_digest'], 'allocation_id': owner.store._claim()['allocation_id'],
        'hold': len(plan['nodes']), 'released': 0}


def financial_archive_funding(owner, native_funding):
    facade = _financial_issuer(owner)
    require(facade.in_archive_scope(owner), 'actual_archive_funding_scope')
    active = _active(owner.root, _homes(owner.root, owner.plan['planner'], owner.plan['run_id']), owner.plan)
    campaign = active['campaign']
    legacy_paid = campaign.base_global + len(campaign.mvg_rows)
    root_paid, root_guard = owner._outside()
    paid, guard = merge_outside_liabilities(root_paid, root_guard, native_funding,
                                          native_funding['paid_or_unknown_before_run'] - legacy_paid)
    claim = owner.store._claim()
    require(paid >= claim['base_paid_or_unknown'] and guard >= claim['outside_guard'],
            'archive_never_releases_old_financial_liabilities')
    merged = deepcopy(native_funding)
    require(guard + claim['hold'] <= 290, 'existing_full_hold_still_reserved')
    merged.update(paid_or_unknown_before_run=paid, subsequent_full_reservation=290-paid-claim['hold'],
                  maximum_native_charges=claim['hold'])
    return merged


def financial_archive(owner, run):
    facade = _financial_issuer(owner)
    require(facade.in_archive_scope(owner), 'actual_original_archive_inspection')
    import _b_route_segmented_journal as journal
    before = owner.store._fresh_snapshot()
    if not os.path.lexists(run):
        stopped = os.path.lexists(owner.store.ledger / 'STOP.json')
        inspected = owner.store.inspect_readonly(native_observations=[],
                    expected_state='retained-stop' if stopped else 'open-prefix', expected_snapshot=before)
        return {**inspected,'native':[],'native_state':None,'verified_results':{},
                'native_blocked':{'reason':'native_birth_not_published','may_redispatch':False},
                'same_original_claim_at_current_source':False,'native_birth_present':False,
                'archive_replay_verified':False,'dispatch_authorized':False,'released':0}
    state = value(owner.root, (run / 'run.json').relative_to(owner.root).as_posix())
    require(state['schema_version'] == FISCAL_RUN, 'archive_explicit_fiscal_family')
    with verified_run(owner.root, run, owner.plan):
        active = _active(owner.root, run, owner.plan)
        source, campaign = active['source'], active['campaign']
        _validate_plan_source(owner.plan, source)
        obs = sources.Observations(owner.root)
        initial = _birth(owner.root, run, state, owner.plan, obs)
        obs.verify()
        identity = _run_identity(source, owner.plan, initial['runtime_identity']['runner']['description'])
        require(identity == initial['runtime_identity'], 'original_archived_runtime_identity')
        facts, _registry, entries = _plan_authority_facts(owner.root, run, source, campaign)
        rebuilt, native_state = _financial_claim_from_facts(owner, facts, owner.plan, identity, campaign)
        rebuilt['context_limit'] = owner.store._claim()['context_limit']
        native = financial_current(owner, native_state)
        stopped = os.path.lexists(owner.store.ledger / 'STOP.json')
        inspected = owner.store.inspect_readonly(native_observations=native,
                    expected_state='retained-stop' if stopped else 'open-prefix', expected_snapshot=before)
        name = (run / 'run.json').relative_to(owner.root).as_posix()
        history = _history(owner.root, entries[name], state)
        completed, blocked = [], None
        if history['pending_publications']:
            blocked = {'reason':'pending_original_publication','may_redispatch':False}
        elif (run/'q/state.json').is_file() and (run/'q/plan.json').is_file():
            with journal.open_workflow(owner.root, run_dir=run, plan=owner.plan, read_only=True) as session:
                current = session.snapshot()  # ORIGINAL stored-result replay factory.
                completed, blocked = current['completed'], current['blocked']
        elif state['capability_selection']['calls'] == [] and not os.path.lexists(run/'q'):
            # Genuine published zero-call birth before workflow initialization.
            _core().require_segmented_run(owner.root, run, state, owner.plan)
        else:
            blocked = {'reason':'partial_original_workflow_metadata','may_redispatch':False}
        verified = {row['node_id']: row for row in completed}
        require(set(inspected['facts']['completed_node_ids']) <= set(verified),
                'financial_outcomes_require_actual_native_result_replay')
        require(owner.store._fresh_snapshot() == before, 'archive_final_complete_prefix_closure')
        return {**inspected, 'native':native, 'native_state':native_state,
                'verified_results':verified, 'native_blocked':blocked,
                'same_original_claim_at_current_source':rebuilt == owner.store._claim(),
                'native_birth_present':True, 'archive_replay_verified':True,
                'dispatch_authorized':False, 'released':0}


def financial_reconcile_outcome(owner, replay):
    facade = _financial_issuer(owner)
    require(facade.in_archive_scope(owner), 'actual_reconcile_archive_scope')
    owner.store._held()
    module = facade._module()
    fn = module.RootSegmentedIssuer.reconcile_completed_intent
    frame = sys._getframe(1)
    require(frame.f_code is fn.__code__ and frame.f_globals is module.__dict__
            and frame.f_locals.get('self') is owner, 'original_fiscal_reconcile_frame')
    import _b_route_segmented_journal as journal
    from _mvg_capability_checkpoint import coordinator_lock
    run = _homes(owner.root, owner.plan['planner'], owner.plan['run_id'])
    with verified_run(owner.root, run, owner.plan):
        state = value(owner.root, (run/'run.json').relative_to(owner.root).as_posix())
        with recovery.operation_lock(owner.root, state), coordinator_lock(run):
            require(owner.store._fresh_snapshot() == replay['snapshot'], 'reconcile_exact_existing_prefix_CAS')
            native = financial_current(owner, replay['native_state'])
            # Original readonly session reconstructs the real VerifiedResult;
            # native complete() and model invocation are never called here.
            with journal.open_workflow(owner.root, run_dir=run, plan=owner.plan, read_only=True) as session:
                actual = session.snapshot()
            require(actual['blocked'] is None, 'reconcile_native_publication_must_be_closed')
            rows = [owner.h.parse(row['raw']) for name,row in sorted(replay['snapshot']['members'].items()) if name!='STOP.json']
            last = rows[-1]
            event = last['event']
            require(event['kind']=='intent', 'reconcile_only_existing_intent')
            matches = [row for row in actual['completed'] if row['node_id']==event['node_id']]
            require(len(matches)==1 and matches[0]['reservation']==event['reservation'], 'reconcile_actual_completed_reservation')
            result = matches[0]['verified_result']
            node = owner.plan['nodes'][event['ordinal']]
            value_result = _core().validate_verified_result(owner.plan,node,event['reservation'],result)
            require(native[-1]['outcome_raw'] is not None
                    and native[-1]['verified_result_digest']==value_result['result_digest'], 'reconcile_genuine_native_result')
            claim = owner.store._claim()
            outcome = {'schema_version':owner.prefix.OUTCOME,'kind':'outcome','allocation_id':claim['allocation_id'],
                'node_id':event['node_id'],'ordinal':event['ordinal'],'reservation_id':event['reservation_id'],
                'paid_or_unknown':claim['base_paid_or_unknown']+replay['facts']['intent_count'],
                'guard_occupancy':claim['guard_occupancy'],'hold':claim['hold'],'released':0,
                'intent_row_sha256':last['sha256'],'native_outcome_digest':codec.raw_digest(native[-1]['outcome_raw']),
                'verified_result_digest':value_result['result_digest']}
            return owner.store.append_event(outcome,native_before=native,native_after=native,
                                             expected_snapshot=replay['snapshot'])


def financial_repair_birth(owner, run, planning_contract, semantic_catalog_ref=None):
    """Finish ONLY the exact original zero-call born publication, never apply a new claim."""
    facade = _financial_issuer(owner)
    require(facade.in_archive_scope(owner), 'actual_zero_model_birth_repair_scope')
    owner.store._held()
    source = capture_source(owner.root,run_id=owner.plan['run_id'],planner=owner.plan['planner'],
                            planning_contract=planning_contract,semantic_catalog_ref=semantic_catalog_ref)
    _validate_plan_source(owner.plan,source)
    import _b_route_segmented_journal as journal
    from _mvg_capability_checkpoint import coordinator_lock
    from functools import partial
    store = _configured_store(owner.root)
    stem = hashlib.sha256((str(run.resolve()) + '\0' + owner.plan['plan_digest']).encode()).hexdigest()[:24]
    name = 'logs/ci/mvg-recovery/activity/segmented-journals/' + stem + '-000-born.json'
    publication = value(owner.root,name)
    require(publication.get('schema_version')=='newrouge.planning-apply-journal.v1'
            and publication.get('status') in ('pending','complete'), 'original_named_birth_publication')
    metadata = publication['result']
    base = run.relative_to(owner.root).as_posix()
    require(metadata['schema_version']==journal.TX and metadata['verb']=='born'
            and metadata['run_path']==base+'/run.json' and metadata['run_id']==owner.plan['run_id']
            and metadata['plan_digest']==owner.plan['plan_digest'], 'same_original_birth_publication_identity')
    entries = publication['entries']
    expected = {base+'/run.json',base+'/b/initial-run.json',base+'/b/born.json',base+'/b/host.json',
                base+'/b/plan.json',base+'/b/claim.json','logs/ci/mvg-recovery/registry.json'}
    require(len(entries)==len(expected) and {e['path'] for e in entries}==expected, 'original_finite_birth_write_set')
    payload = {e['path']:e['payload'] for e in entries}
    initial = payload[base+'/b/initial-run.json']
    born = payload[base+'/b/born.json']
    host = payload[base+'/b/host.json']
    require(initial['schema_version']==FISCAL_RUN and initial['capability_selection']['calls']==[]
            and type(initial['capability_selection']['total_invocations']) is int
            and initial['capability_selection']['total_invocations']==0
            and born['schema_version']==FISCAL_BORN and born['initial_calls']==0
            and payload[base+'/run.json']['capability_selection']['calls']==[]
            and payload[base+'/b/plan.json']==owner.plan, 'repair_only_original_zero_call_birth')
    require(initial['segmented_fiscal_claim']==born['segmented_fiscal_claim']
            ==payload[base+'/run.json']['segmented_fiscal_claim']
            ==financial_archive_reference(owner,owner.root,owner.plan), 'repair_original_financial_birth_binding')
    financial_claim = owner.store._claim()
    durable = financial_claim['binding']
    declared = initial['b_route_campaign_funding']
    require(codec.canonical_digest(initial['runtime_identity']) == durable['runtime_identity_digest']
            and source['frozen']['input_identity'] == durable['source_input_identity']
            and codec.canonical_digest(source._policy) == durable['source_policy_digest']
            and initial['native_profile'] == durable['profile']
            and initial['run_id'] == durable['run_id'] and initial['planner'] == durable['planner']
            and declared['paid_or_unknown_before_run'] == financial_claim['base_paid_or_unknown']
            and declared['maximum_native_charges'] == financial_claim['hold']
            and declared['subsequent_full_reservation'] == 290-financial_claim['base_paid_or_unknown']-financial_claim['hold']
            and declared['retained_profile_calls'] == financial_claim['retained_profile_calls']
            and declared['retained_lineage_calls'] == financial_claim['retained_lineage_calls'],
            'repair_existing_source_native_identity_and_scope_bindings')
    require(host['frozen']==source['frozen'] and host['source_identity']==source['source_identity']
            and host['policy_identity']==source._policy and host['globs']==source._globs
            and host['observations']==[{'path':p,'raw_base64':base64.b64encode(b).decode('ascii') if b is not None else None}
                                      for p,b in source._files.items()], 'repair_original_complete_current_source')
    snapshot = owner.store.inspect_readonly(native_observations=[],expected_state='open-prefix')
    require(snapshot['facts']['intent_count']==0, 'no_paid_intent_before_zero_call_repair')
    with recovery.operation_lock(owner.root,initial), coordinator_lock(run), coordinator_lock(store):
        owner._paid_owners()
        verify_candidate_context(owner.root,source)
        require(owner.store._fresh_snapshot()==snapshot['snapshot'], 'repair_same_existing_financial_claim')
        actual = value(owner.root,name)
        require(actual==publication, 'same_original_publication_before_resume')
        # Original before/after images, target identities and payload hashes are
        # validated by the existing journal. No copied recovery implementation.
        journal.resume_journal(owner.root,path(owner.root,name),partial(journal._original_writer,owner.root))
        verify_candidate_context(owner.root,source)
        require(value(owner.root,name)['status']=='complete', 'original_birth_publication_closed')
    return {'native_birth_publication_repaired':True,'model_calls':0,'new_financial_intents':0,'released':0}


def financial_dispatch_contract(owner, session, reservation):
    _financial_issuer(owner)
    # The original workflow frame and Session/_fresh checks remain actual.
    # A serialized observation cannot be supplied back as a grant or lease.
    financial_persisted(owner,session,reservation)
    from _planning_skill_common import _runner_prefix
    runner = Path(owner.native_state['runtime_identity']['runner']['path'])
    workspace = Path(reservation['workspace'])
    q = reservation['request_identity']
    command = [*_runner_prefix(runner,suppress_bytecode=True),'--workspace',str(workspace),
               '--prompt-file',str(workspace/'prompt.txt'),'--output',str(workspace/'output.json'),
               '--timeout-sec',str(reservation['timeout_sec']),'--output-schema',str(workspace/'output-schema.json'),
               '--model-request-budget','1']
    first = owner.store._fresh_snapshot()['members']['000001.json']
    return {'schema_version':'task.Root-segmented-current-paid-node.v1',
        'allocation_id':owner.store._claim()['allocation_id'],'claim_raw_sha256':first['sha256'],
        'run_id':owner.plan['run_id'],'plan_digest':owner.plan['plan_digest'],
        'node_id':q['node_id'],'reservation_id':reservation['reservation_id'],
        'logical_command':command,'workspace':str(workspace),
        'execution_log':str(workspace.parent/(workspace.name+'-execution.json')),
        'timeout_sec':reservation['timeout_sec'],'wall_timeout_sec':reservation['timeout_sec']+30,
        'model_request_budget':1,'request_identity':deepcopy(q),
        'configured_reasoning_effort':'high','model_identity_evidence':'pending-original-runtime-replay',
        'transport_scope':'original-source-only-runner-logical-argv-not-actual-RPC',
        'grant_serializable':False,'released':0}
