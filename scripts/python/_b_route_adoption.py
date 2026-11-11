"""Freeze reviewed adoption operations; never apply or publish formal records."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from functools import wraps
import hashlib
import json
from pathlib import Path
import stat
import string
from types import ModuleType
import uuid

import _b_route_codec as codec
import _b_route_sources as sources
import _planning_apply_journal as journal

PLAN = 'newrouge.b-route-plan.v1'
BINDING = 'newrouge.b-route-binding.v1'
CATALOG = 'docs/planning/b-route/catalog.v1.json'
TRIPLET = {'master': '.taskmaster/tasks/tasks.json',
           'back': '.taskmaster/tasks/tasks_back.json',
           'gameplay': '.taskmaster/tasks/tasks_gameplay.json'}
FLAGS = {'formal_adoption': False, 'readiness': False, 'runtime_verified': False}


def fail(reason, expected, actual, operation_id=None, resume_ref=None):
    raise codec.CodecError(codec.Diagnostic(reason, codec.Stage.BUNDLE,
        operation_id, expected, actual, resume_ref))


def require(value, expected, actual, reason=codec.ReasonCode.IDENTITY_UNPROVABLE):
    if not value:
        fail(reason, expected, actual)


def operation_ref(operation_id):
    codec.validate_business_id(operation_id)
    key = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()
    return 'logs/ci/b-route-operations/operations/' + key + '/operation.json'


def safe_path(root, name):
    codec.validate_reference_path(name)
    require(not any(p.lower() in {'.codex', '.aws', '.ssh', 'sessions', 'credentials'}
                    for p in name.split('/')), 'project evidence path', name,
            codec.ReasonCode.UNSAFE_PATH)
    return sources.checked_path(Path(root).resolve(), name)


@contextmanager
def _frozen_native_reader():
    """Execute the checked reader source, never an import or bytecode cache."""
    source_root = Path(__file__).absolute().parents[2]
    relative = 'scripts/python/_b_route_frozen_native_reader.py'
    path = sources.checked_path(source_root, relative)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            'single plain native reader source', relative, codec.ReasonCode.UNSAFE_PATH)
    raw = path.read_bytes()
    identity = (info.st_dev, info.st_ino)
    def unchanged():
        current = sources.checked_path(source_root, relative)
        current_info = current.lstat()
        require(stat.S_ISREG(current_info.st_mode) and current_info.st_nlink == 1
                and (current_info.st_dev, current_info.st_ino) == identity and current.read_bytes() == raw,
                'same checked native reader source bytes and file', relative, codec.ReasonCode.INPUT_STALE)
    reader = ModuleType('_b_route_frozen_native_reader_parent_source')
    reader.__file__ = str(path)
    reader.__package__ = ''
    try:
        exec(compile(raw, str(path), 'exec'), reader.__dict__)
        unchanged()
        reader._adoption_source_digest = codec.raw_digest(raw)
        yield reader
    finally:
        unchanged()


def _reader_capture_source(reader, capture):
    require(type(capture) is dict and type(capture.get('source_identity')) is dict
            and capture['source_identity'].get('reader_raw_digest') == reader._adoption_source_digest,
            'capture bound to executed reader source', 'reader source identity changed', codec.ReasonCode.INPUT_STALE)


class Snapshot:
    """Hash the exact observed closure; recheck it at the persistence boundary."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}
        self.directories = {}
        self.handoff = None
        self.prepared = None
        self.protection = None
        self.committed = []
        self.catalog = None
        self.tasks = {}
        self.task_payloads = {}
        self.proof_paths = set()
        self.metadata_locks = {}
        self.native_capture = None
        self._qualified_history_handles = []

    def read(self, name, *, optional=False):
        path = safe_path(self.root, name)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            if not optional:
                fail(codec.ReasonCode.FILE_NOT_FOUND, 'existing original evidence', name)
            raw = None
        digest = codec.raw_digest(raw) if raw is not None else None
        require(name not in self.files or self.files[name] == digest,
                'stable observed input', name, codec.ReasonCode.INPUT_STALE)
        self.files[name] = digest
        return raw

    def ref(self, ref):
        require(type(ref) is dict and set(ref) == {'path', 'schema_version', 'raw_digest'},
                'complete raw-bound reference', ref, codec.ReasonCode.INVALID_REFERENCE)
        raw = self.read(ref['path'])
        require(codec.raw_digest(raw) == ref['raw_digest'], ref['raw_digest'], ref['path'],
                codec.ReasonCode.DIGEST_MISMATCH)
        if ref['schema_version'] == 'raw.bytes.v1':
            return raw
        value = codec.strict_json_loads(raw)
        require(type(value) is dict and value.get('schema_version') == ref['schema_version'],
                ref['schema_version'], ref['path'], codec.ReasonCode.SCHEMA_MISMATCH)
        return value

    def tree(self, name):
        root = safe_path(self.root, name)
        found = []
        if root.exists():
            require(root.is_dir(), 'directory', name, codec.ReasonCode.INVALID_TYPE)
            for path in sorted(root.rglob('*')):
                require(not path.is_symlink() and not (getattr(path.lstat(), 'st_file_attributes', 0) & 0x400),
                        'plain proof path', str(path), codec.ReasonCode.UNSAFE_PATH)
                if path.is_file():
                    relative = path.relative_to(self.root).as_posix()
                    if path.name == 'capability-coordinator.lock':
                        info = path.lstat()
                        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == 1,
                                'plain native coordinator byte lock', relative, codec.ReasonCode.UNSAFE_PATH)
                        self.metadata_locks[relative] = (info.st_dev, info.st_ino)
                    else:
                        self.read(relative)
                    found.append(relative)
        self.directories[name] = found
        return found

    def verify(self):
        for handle in self._qualified_history_handles:
            handle.recheck()
        if self.native_capture is not None:
            with _frozen_native_reader() as reader:
                _reader_capture_source(reader, self.native_capture)
                reader.verify_capture(self.root, self.native_capture)
        for name, identity in self.metadata_locks.items():
            info = safe_path(self.root, name).lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == 1
                    and (info.st_dev, info.st_ino) == identity,
                    'same native coordinator metadata file', name, codec.ReasonCode.INPUT_STALE)
        for name, expected in list(self.files.items()):
            path = safe_path(self.root, name)
            require(not path.exists() or path.is_file(), 'original regular file or absence', name,
                    codec.ReasonCode.INPUT_STALE)
            raw = path.read_bytes() if path.is_file() else None
            require((codec.raw_digest(raw) if raw is not None else None) == expected,
                    expected, name, codec.ReasonCode.INPUT_STALE)
        for name, expected in list(self.directories.items()):
            root = safe_path(self.root, name)
            actual = []
            if root.exists():
                for path in sorted(root.rglob('*')):
                    require(not path.is_symlink() and not (getattr(path.lstat(), 'st_file_attributes', 0) & 0x400),
                            'plain proof path', str(path), codec.ReasonCode.UNSAFE_PATH)
                    if path.is_file():
                        actual.append(path.relative_to(self.root).as_posix())
            require(actual == expected, expected, name, codec.ReasonCode.INPUT_STALE)


def _task_context(snapshot):
    from _b_route_records import TaskJoinContext
    from _b_route_protection import task_definition_projection
    raws = {name: snapshot.read(path, optional=True) for name, path in TRIPLET.items()}
    if all(raw is None for raw in raws.values()):
        return TaskJoinContext({'master': {'tasks': []}}, [], [])
    require(all(raw is not None for raw in raws.values()), 'complete Task join triplet', list(raws))
    documents = {name: codec.strict_json_loads(raw) for name, raw in raws.items()}
    context = TaskJoinContext(**documents)
    tasks, _ = context.indexes()
    for task_id, task in tasks.items():
        definition = {'master': task_definition_projection(task), 'back': [], 'gameplay': []}
        for name in ('back', 'gameplay'):
            definition[name] = [task_definition_projection(row) for row in documents[name]
                                if row['taskmaster_id'] == task_id]
        snapshot.tasks[task_id] = codec.canonical_digest(definition)
        snapshot.task_payloads[task_id] = definition
    return context


def _committed(snapshot):
    import _b_route_records as records
    snapshot.committed, snapshot.tasks, snapshot.task_payloads, snapshot.catalog = [], {}, {}, None
    task_context = _task_context(snapshot)
    raw = snapshot.read(CATALOG, optional=True)
    files = []
    for directory in ('docs/planning/b-route/plans', 'docs/planning/b-route/bindings'):
        files.extend(snapshot.tree(directory))
    if raw is None:
        require(not files, 'catalog anchoring any existing planning revisions', files,
                codec.ReasonCode.UNPUBLISHED)
        return
    result = records.validate_bundle({}, root=snapshot.root, task_join=task_context)
    if not result.ok:
        raise codec.CodecError(result.diagnostic)
    snapshot.catalog = codec.strict_json_loads(raw)
    for path in ('docs/planning/b-route/policy.v1.json', 'docs/planning/b-route/task-origins.v1.json'):
        snapshot.read(path)
    snapshot.tree('docs/planning/b-route/commits')
    for path in files:
        value = codec.strict_json_loads(snapshot.read(path))
        result = records.validate_record(value, path=path)
        if not result.ok:
            raise codec.CodecError(result.diagnostic)
        require(value['schema_version'] in {PLAN, BINDING}, 'planning revision', path)
        snapshot.committed.append((path, value))


@contextmanager
def capture_completed(root, material, review_ref):
    """Original candidate eligibility; host review is a distinct _run boundary."""
    if 'origin_profile' in material:
        from _b_route_qualified_origin import capture_target
        with capture_target(root, material, review_ref) as snapshot:
            yield snapshot
        return
    import _b_route_planning_runtime as runtime
    import _b_route_planning_input as planning
    import _b_route_protection as protection
    from _mvg_capability_checkpoint import coordinator_lock
    from _mvg_capability_recovery import operation_lock
    snapshot = Snapshot(root)
    run = runtime.run_location(snapshot.root, material['planner'], material['run_id'])
    state_raw = snapshot.read((run / 'run.json').relative_to(snapshot.root).as_posix())
    state = codec.strict_json_loads(state_raw)
    require(runtime.enabled(state) and state.get('selection_status') == 'selected',
            'complete selected 3B run', state.get('selection_status'), codec.ReasonCode.UNPUBLISHED)
    require(state.get('run_id') == material['run_id'] and
            runtime.descriptor(state)['planner'] == material['planner'] and state.get('input_stage') == '3b',
            'exact original run/planner/input-stage binding', material['run_id'])
    require(state.get('schema_version') in {runtime.RUN, runtime.CONTINUATION_RUN},
            'known native run version', state.get('schema_version'), codec.ReasonCode.SCHEMA_MISMATCH)
    recovery = state.get('recovery', {}).get('store')
    expected_store = (snapshot.root / 'logs/ci/mvg-recovery').resolve()
    require(type(recovery) is str and Path(recovery).resolve() == expected_store and expected_store.is_dir(),
            'original project-local recovery namespace', recovery, codec.ReasonCode.UNSAFE_PATH)
    with operation_lock(snapshot.root, state):
        with coordinator_lock(run):
            if state['schema_version'] == runtime.CONTINUATION_RUN:
                with _frozen_native_reader() as reader:
                    snapshot.native_capture = reader.capture_completed(snapshot.root, planner=material['planner'],
                        run_id=material['run_id'], state_raw=state_raw, expected_handoff_ref=material['handoff_ref'])
                    _reader_capture_source(reader, snapshot.native_capture)
                snapshot.handoff = deepcopy(snapshot.native_capture['handoff'])
                snapshot.prepared = deepcopy(snapshot.native_capture['prepared'])
            else:
                runtime.validate_input(snapshot.root, run, state)
                snapshot.handoff = runtime.handoff(snapshot.root, run, state)
                snapshot.prepared = planning.load_prepared(snapshot.root, snapshot.handoff['original_prepared_ref'])
            supplied = snapshot.ref(material['handoff_ref'])
            require(codec.canonical_digest(supplied) == codec.canonical_digest(snapshot.handoff),
                    'exact current native handoff', material['handoff_ref']['path'])
            expected_handoff = (run / 'handoff.json').relative_to(snapshot.root).as_posix()
            require(material['handoff_ref']['path'] == expected_handoff,
                    expected_handoff, material['handoff_ref']['path'])
            review = snapshot.ref(review_ref)
            require(review_ref['path'] == state['selected_admission_review']['path'] and
                    codec.canonical_digest(review) == codec.canonical_digest(snapshot.handoff['admission']),
                    'original independently verified selected admission', review_ref['path'])
            snapshot.tree(run.relative_to(snapshot.root).as_posix())
            snapshot.tree(str(Path(snapshot.handoff['original_prepared_ref']).parent).replace('\\', '/'))
            for path in snapshot.prepared['inputs']['dependencies']['files']:
                snapshot.read(path, optional=True)
        # Protection is an original archive, never a declaration granting writes.
        snapshot.ref(material['protection_ref'])
        result = protection.verify_protection(snapshot.root, material['protection_ref']['path'])
        require(result['ok'] and result.get('capture_complete') is True,
                'complete verified original protection archive', result)
        snapshot.protection = codec.strict_json_loads(snapshot.read(material['protection_ref']['path']))
        snapshot.tree(str(Path(material['protection_ref']['path']).parent).replace('\\', '/'))
        for ref in material['authority_refs'] + material['lineage_refs']:
            snapshot.ref(ref)
        snapshot.proof_paths = set(snapshot.files)
        _committed(snapshot)
        snapshot.verify()
        yield snapshot


def _shape(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), keys, label,
            codec.ReasonCode.UNKNOWN_FIELD)


def validate_allocations(value):
    """Interpret the service's host claim without Python bool/int coercion."""
    import _b_route_schema_resources as schemas
    _shape(value, ('plan_id', 'plan_revision', 'binding_revision', 'requirements', 'flows', 'task_definitions'),
           'host allocations')
    codec.validate_business_id(value['plan_id'])
    codec._positive_integer(value['plan_revision'], codec.Stage.CONTENT)
    if value['binding_revision'] is not None:
        codec._positive_integer(value['binding_revision'], codec.Stage.CONTENT)
    for kind in ('requirements', 'flows'):
        require(type(value[kind]) is dict, 'complete typed identity map', kind, codec.ReasonCode.INVALID_TYPE)
        for candidate, stable in value[kind].items():
            codec.validate_business_id(candidate)
            codec.validate_business_id(stable)
        require(len(set(value[kind].values())) == len(value[kind]), 'one-to-one identity mapping', kind)
    require(type(value['task_definitions']) is dict, 'joined Task definition claims', 'task_definitions')
    validator = schemas.validator(PLAN).evolve(schema={'$ref': 'newrouge.b-route-common.v1#/$defs/Digest'})
    for task_id, digest in value['task_definitions'].items():
        require(type(task_id) is str and task_id.isascii() and task_id.isdecimal()
                and str(codec.validate_task_id(int(task_id))) == task_id,
                'canonical existing Task ID key', task_id, codec.ReasonCode.INVALID_TYPE)
        require(validator.is_valid(digest), 'shared strict digest', task_id, codec.ReasonCode.INVALID_DIGEST)


def validate_operations(operations):
    """Unknown business claims cannot silently influence new allocation or scope."""
    import _b_route_records as records
    from _b_route_operation_scope import resource_scopes
    for operation in operations:
        frozen = operation['frozen']
        if operation['schema_version'] == journal.COMPENSATION_SCHEMA:
            import _b_route_compensation as compensation
            journal._operation_schema(frozen, 'Frozen')
            if any(row['operation_id'] == frozen['request']['compensates']['operation_id'] for row in operations):
                compensation.validate_relation(frozen, operations)
        allocation = frozen['allocations']
        validate_allocations(allocation)
        definitions = {'commands': [], 'states': []}
        plan_count = 0
        for target in frozen['targets']:
            payload = target['after_payload']
            checked = records.validate_record(payload, path=target['path'])
            if not checked.ok:
                raise codec.CodecError(checked.diagnostic)
            require(payload['schema_version'] == target['schema_version'], 'known exact target schema', target['path'])
            if payload['schema_version'] == PLAN:
                plan_count += 1
                require(payload['plan_id'] == allocation['plan_id'] and
                        type(payload['revision']) is int and payload['revision'] == allocation['plan_revision'],
                        'typed plan allocation reflected in target', operation['operation_id'])
                require(_ids(payload, 'requirements') == set(allocation['requirements'].values()) and
                        _ids(payload, 'flows') == set(allocation['flows'].values()),
                        'complete allocated definition projection', operation['operation_id'])
                definitions = payload['definitions']
        require(plan_count == 1, 'one plan projection for an adoption operation', operation['operation_id'])
        validate_binding_targets(allocation, frozen['targets'])
        minimum = resource_scopes(target_paths=[row['path'] for row in frozen['targets']],
            plan_ids=[allocation['plan_id']],
            requirement_ids=set(allocation['requirements']) | set(allocation['requirements'].values()),
            flow_ids=allocation['flows'].values(), task_ids=[int(k) for k in allocation['task_definitions']],
            command_ids=[row['id'] for row in definitions['commands']],
            state_ids=[row['id'] for row in definitions['states']])
        require(set(minimum) <= set(frozen['scope_ids']), 'complete owned resource scope', operation['operation_id'],
                codec.ReasonCode.PENDING)


def _ids(content, kind):
    rows = content['requirements'] if kind == 'requirements' else content['definitions']['flows']
    key = 'requirement_id' if kind == 'requirements' else 'id'
    return {row[key] for row in rows}


def _current_plan_refs(snapshot):
    heads = (snapshot.catalog or {}).get('scope_heads', [])
    result = {ref['path'] for head in heads for ref in head['plan_refs']}
    records = dict(snapshot.committed)
    for head in heads:
        for ref in head['binding_refs']:
            binding = records.get(ref['path'])
            require(type(binding) is dict and binding.get('schema_version') == BINDING,
                    'verified current binding record', ref['path'], codec.ReasonCode.INPUT_STALE)
            # Binding revisions are independent from the referenced plan revision.
            result.add(binding['plan_ref']['path'])
    return result


def new_identity(prefix):
    return prefix + uuid.uuid4().hex


def propose_allocations(snapshot, alignment, operations, existing=None):
    """Propose opaque values; only the checked persistence callback assigns them."""
    _shape(alignment, ('plan', 'binding', 'requirements', 'flows', 'tasks'), 'identity_alignment')
    old_claims = [row['frozen']['allocations'] for row in operations
                  if existing is None or row['operation_id'] != existing['operation_id']]
    plan = alignment['plan']
    require(type(plan) is dict and plan.get('mode') in {'new', 'reuse'}, 'plan alignment', plan)
    if plan['mode'] == 'new':
        _shape(plan, ('mode',), 'plan')
        plan_id = existing['frozen']['allocations']['plan_id'] if existing else new_identity('PLAN-')
        require(not any(v.get('plan_id') == plan_id for _, v in snapshot.committed) and
                not any(v.get('plan_id') == plan_id for v in old_claims), 'unused new plan ID', plan_id,
                codec.ReasonCode.CONFLICT)
    else:
        _shape(plan, ('mode', 'plan_ref'), 'plan')
        prior = snapshot.ref(plan['plan_ref'])
        require(prior.get('schema_version') == PLAN and plan['plan_ref']['path'] in _current_plan_refs(snapshot),
                'currently published plan lineage', plan['plan_ref']['path'], codec.ReasonCode.UNPUBLISHED)
        require(plan['plan_ref']['path'] in snapshot.prepared['inputs']['dependencies']['files'],
                'prior plan in independently reviewed prepared input', plan['plan_ref']['path'])
        plan_id = prior['plan_id']
    codec.validate_business_id(plan_id)
    maximum = max([0] + [v['revision'] for _, v in snapshot.committed
        if v.get('schema_version') == PLAN and v['plan_id'] == plan_id] +
        [v['plan_revision'] for v in old_claims if v.get('plan_id') == plan_id])
    result = {'plan_id': plan_id, 'plan_revision': maximum + 1, 'binding_revision': None,
              'requirements': {}, 'flows': {}, 'task_definitions': {}}
    for kind, prefix in (('requirements', 'RQ-'), ('flows', 'FLOW-')):
        rows = alignment[kind]
        require(type(rows) is list and len({row.get('candidate_id') for row in rows if type(row) is dict}) == len(rows),
                'unique explicit identity correspondences', kind)
        require({row['candidate_id'] for row in rows} == _ids(snapshot.handoff['proposal']['content'], kind),
                'complete candidate identity denominator', kind)
        for row in rows:
            candidate_id = codec.validate_business_id(row['candidate_id'])
            require(type(row.get('rationale')) is str and bool(row['rationale'].strip()), 'reviewed identity rationale', candidate_id)
            if row.get('mode') == 'allocate':
                _shape(row, ('candidate_id', 'mode', 'rationale'), candidate_id)
                value = existing['frozen']['allocations'][kind][candidate_id] if existing else new_identity(prefix)
                occupied = [p['requirement_id'] for _, v in snapshot.committed if v['schema_version'] == PLAN for p in v['requirements']] if kind == 'requirements' else [p['id'] for _, v in snapshot.committed if v['schema_version'] == PLAN for p in v['definitions']['flows']]
                occupied += [x for claim in old_claims for x in claim.get(kind, {}).values()]
                require(value not in occupied, 'unused allocated definition ID', value, codec.ReasonCode.CONFLICT)
            else:
                _shape(row, ('candidate_id', 'mode', 'rationale', 'stable_id', 'evidence_ref'), candidate_id)
                require(row['mode'] == 'reuse', 'allocate or explicit reuse', row['mode'])
                value = codec.validate_business_id(row['stable_id'])
                evidence = snapshot.ref(row['evidence_ref'])
                if evidence.get('schema_version') == PLAN:
                    require(row['evidence_ref']['path'] in _current_plan_refs(snapshot) and value in _ids(evidence, kind),
                            'currently published aligned definition', value)
                    if kind == 'flows':
                        require(evidence['plan_id'] == plan_id,
                                'same Flow definition owner; external definitions remain references', value,
                                codec.ReasonCode.DUPLICATE_OWNER)
                else:
                    require(kind == 'requirements' and value == candidate_id and
                            row['evidence_ref']['path'] in snapshot.prepared['inputs']['dependencies']['files'],
                            'source-owned Requirement in verified prepared closure', value)
            result[kind][candidate_id] = value
        require(len(set(result[kind].values())) == len(result[kind]), 'one-to-one identity alignment', kind)
    binding = alignment['binding']
    require(type(binding) is dict and binding.get('mode') in {'none', 'new', 'revise'}, 'binding alignment', binding)
    if binding['mode'] == 'none':
        _shape(binding, ('mode',), 'binding')
    else:
        if binding['mode'] == 'revise':
            _shape(binding, ('mode', 'binding_ref'), 'binding')
            previous = snapshot.ref(binding['binding_ref'])
            require(previous.get('schema_version') == BINDING and previous['plan_ref']['entity_id'] == plan_id,
                    'binding lineage for same plan', binding)
            current_bindings = {ref['path'] for head in (snapshot.catalog or {}).get('scope_heads', [])
                                for ref in head['binding_refs']}
            require(binding['binding_ref']['path'] in current_bindings and
                    binding['binding_ref']['path'] in snapshot.prepared['inputs']['dependencies']['files'],
                    'current independently reviewed binding lineage', binding['binding_ref']['path'],
                    codec.ReasonCode.UNPUBLISHED)
        else:
            _shape(binding, ('mode',), 'binding')
            require(not any(v['schema_version'] == BINDING and v['plan_ref']['entity_id'] == plan_id
                            for _, v in snapshot.committed),
                    'explicit lineage when revising an existing binding', plan_id)
        revisions = [v['binding_revision'] for _, v in snapshot.committed
                     if v['schema_version'] == BINDING and v['plan_ref']['entity_id'] == plan_id]
        revisions += [v['binding_revision'] for v in old_claims
                      if v.get('plan_id') == plan_id and v.get('binding_revision') is not None]
        result['binding_revision'] = max([0] + revisions) + 1
    require(type(alignment['tasks']) is list, 'explicit existing Task join list', alignment['tasks'])
    for row in alignment['tasks']:
        _shape(row, ('task_id',), 'task alignment')
        task_id = codec.validate_task_id(row['task_id'])
        require(task_id in snapshot.tasks, 'existing joined Task ID', task_id)
        protected = {entry['task_id']: entry['definition_digest'] for entry in snapshot.protection['tasks']}
        require(protected.get(task_id) == snapshot.tasks[task_id],
                'unchanged protected relevant Task definition/history', task_id, codec.ReasonCode.INPUT_STALE)
        require(str(task_id) not in result['task_definitions'], 'unique Task mapping', task_id)
        result['task_definitions'][str(task_id)] = snapshot.tasks[task_id]
    if existing:
        require(codec.canonical_digest(result) == codec.canonical_digest(existing['frozen']['allocations']),
                'original frozen allocations and definitions', result,
                codec.ReasonCode.INPUT_STALE)
    return result


def validate_lineage(payload, alignment, allocations, prior):
    rows = payload['lineage']['identity_alignment']
    if prior is None:
        require(not rows, 'no historical correspondence for a new plan', rows)
        return
    old = {kind: {row['id'] for row in prior['definitions'][plural]}
           for kind, plural in (('flow', 'flows'), ('command', 'commands'), ('state', 'states'))}
    current = {kind: {row['id'] for row in payload['definitions'][plural]}
               for kind, plural in (('flow', 'flows'), ('command', 'commands'), ('state', 'states'))}
    previous_seen, current_seen = set(), set()
    flow_alignment = {allocations['flows'][row['candidate_id']]: row for row in alignment['flows']}
    for row in rows:
        kind, previous_id, current_id = row['kind'], row['previous_id'], row['current_id']
        require(kind in old and previous_id in old[kind] and current_id in current[kind],
                'real previous and projected current typed definition', row)
        require((kind, previous_id) not in previous_seen and (kind, current_id) not in current_seen,
                'one-to-one explicit lineage', row)
        previous_seen.add((kind, previous_id)); current_seen.add((kind, current_id))
        if kind == 'flow':
            mapping = flow_alignment[current_id]
            require(row['rationale'] == mapping['rationale'] and
                    (mapping['mode'] != 'reuse' or previous_id == mapping['stable_id']),
                    'same reviewed Flow correspondence and rationale', row)
        else:
            require(previous_id == current_id, 'stable command/state identity; no inferred rename', row)
    retained = {(kind, identity) for kind in old for identity in old[kind] & current[kind]}
    require(retained <= previous_seen & current_seen, 'complete retained-definition lineage', sorted(retained))
    for kind, identity in retained:
        require(any(row['kind'] == kind and row['previous_id'] == identity and row['current_id'] == identity
                    for row in rows), 'retained identity cannot be swapped in lineage', [kind, identity])


def adopted_plan_ref(target):
    payload = target['after_payload']
    return {'path': target['path'], 'schema_version': PLAN, 'entity_id': payload['plan_id'],
            'revision': payload['revision'], 'digest': codec.canonical_digest(payload),
            'verification_mode': 'canonical', 'codec_version': codec.CODEC_VERSION}


def validate_binding_targets(allocations, targets):
    plans = [row for row in targets if row['schema_version'] == PLAN]
    bindings = [row for row in targets if row['schema_version'] == BINDING]
    require(len(plans) == 1, 'one exact adopted plan projection', len(plans))
    require(len(bindings) == int(allocations['binding_revision'] is not None),
            'one complete binding target iff a binding revision is reserved', len(bindings))
    for row in bindings:
        binding = row['after_payload']
        require(binding['plan_id'] == allocations['plan_id'] and
                type(binding['binding_revision']) is int and binding['binding_revision'] == allocations['binding_revision']
                and codec.canonical_digest(binding['plan_ref']) == codec.canonical_digest(adopted_plan_ref(plans[0])),
                'exact same-batch canonical plan reference and independent binding identity', row['path'])


def _render(value, allocations, plan_ref=None):
    scalars = {k: allocations[k] for k in ('plan_id', 'plan_revision', 'binding_revision')}
    scalars.update({'requirement:' + k: v for k, v in allocations['requirements'].items()})
    scalars.update({'flow:' + k: v for k, v in allocations['flows'].items()})
    if type(value) is dict and set(value) == {'$allocation'}:
        require(value['$allocation'] in scalars and scalars[value['$allocation']] is not None,
                'known frozen allocation placeholder', value)
        return scalars[value['$allocation']]
    if type(value) is dict and set(value) == {'$adopted_plan_ref'}:
        require(value['$adopted_plan_ref'] is True and plan_ref is not None,
                'host-derived same-batch plan reference', value)
        return deepcopy(plan_ref)
    if type(value) is dict:
        return {k: _render(v, allocations, plan_ref) for k, v in value.items()}
    if type(value) is list:
        return [_render(v, allocations, plan_ref) for v in value]
    return deepcopy(value)


def _target_path(template, allocations):
    """Only literal text and the original three simple allocation fields."""
    allowed = {'plan_id', 'plan_revision', 'binding_revision'}
    require(type(template) is str, 'target path template string', type(template).__name__,
            codec.ReasonCode.INVALID_REFERENCE)
    try:
        # Parse before formatting: reject attribute/index access, conversions and
        # format widths before they can raise or allocate attacker-sized output.
        for _literal, field, specification, conversion in string.Formatter().parse(template):
            require(field is None or field in allowed and not specification and conversion is None,
                    'simple known allocation field', field, codec.ReasonCode.INVALID_REFERENCE)
        return template.format_map({key: allocations[key] for key in allowed})
    except (KeyError, ValueError, TypeError):
        fail(codec.ReasonCode.INVALID_REFERENCE, 'known target path allocation', template)


def build_frozen(snapshot, request, allocations):
    import _b_route_records as records
    from _b_route_adoption_projection import project_content
    from _b_route_operation_scope import resource_scopes
    targets = []
    expected_content = project_content(snapshot.handoff['proposal']['content'], allocations)
    plan_targets = 0
    templates = request['material']['target_templates']
    for template in templates:
        _shape(template, ('path_template', 'schema_version', 'before_raw_digest', 'after_payload', 'verification_mode'), 'target')
    # Resolve the immutable plan before deriving any binding reference. The
    # original request order is retained in the resulting frozen target array.
    derived_plan_ref, indexed_targets = None, {}
    for index, template in sorted(enumerate(templates), key=lambda pair: pair[1]['schema_version'] != PLAN):
        path = _target_path(template['path_template'], allocations)
        codec.validate_reference_path(path)
        require(path.startswith('docs/planning/b-route/'), 'formal planning record target only', path)
        payload = _render(template['after_payload'], allocations, derived_plan_ref)
        result = records.validate_record(payload, path=path)
        if not result.ok:
            raise codec.CodecError(result.diagnostic)
        require(payload['schema_version'] == template['schema_version'] and
                template['verification_mode'] == 'immutable_bytes', 'immutable formal record payload', path)
        before = snapshot.read(path, optional=True)
        require((codec.raw_digest(before) if before is not None else None) == template['before_raw_digest'],
                template['before_raw_digest'], path, codec.ReasonCode.INPUT_STALE)
        if payload['schema_version'] in {PLAN, BINDING}:
            require(before is None, 'new immutable planning revision path', path, codec.ReasonCode.CONFLICT)
        if payload['schema_version'] == PLAN:
            plan_targets += 1
            require(payload['plan_id'] == allocations['plan_id'] and payload['revision'] == allocations['plan_revision'],
                    'host-allocated plan identity', path)
            for field in ('source_identity', 'requirements', 'definitions', 'logical_references',
                          'requirement_verification', 'requirement_route_memberships', 'requirement_evidence',
                          'evidence_source_refs', 'coverage_table', 'applicability'):
                require(codec.canonical_digest(payload[field]) == codec.canonical_digest(expected_content[field]),
                        'exact independently admitted candidate projection', field)
            native_ref = {'owner': 'planning_proof',
                'ref': request['material']['handoff_ref']['path'] + '#/proposal/content',
                'files': [{'path': request['material']['handoff_ref']['path'],
                           'raw_digest': request['material']['handoff_ref']['raw_digest']}]}
            require(codec.canonical_digest(payload.get('native_candidate_ref')) == codec.canonical_digest(native_ref),
                    'complete original admitted native candidate reference', path)
            previous = request['material']['identity_alignment']['plan'].get('plan_ref')
            require(payload['lineage']['previous_plan_ref'] is None if previous is None else
                    payload['lineage']['previous_plan_ref']['path'] == previous['path'],
                    'explicit immutable replan lineage', path)
            if previous is not None:
                verified = codec.verify_reference(snapshot.root, payload['lineage']['previous_plan_ref'])
                if not verified.ok:
                    raise codec.CodecError(verified.diagnostic)
            validate_lineage(payload, request['material']['identity_alignment'], allocations,
                             snapshot.ref(previous) if previous is not None else None)
            from _b_route_record_owners import resolve_owned_ref
            anchored = False
            for proof in payload['adoption_proof_refs']:
                resolve_owned_ref(proof, read_bytes=snapshot.read, contract_sources=lambda: {})
                if proof['ref'] == request['review_ref']['path']:
                    anchored = any(row['path'] == request['review_ref']['path'] and
                        row['raw_digest'] == request['review_ref']['raw_digest'] for row in proof['files'])
            require(anchored, 'actual selected independent admission in plan proof closure', path)
        if payload['schema_version'] == BINDING:
            require(payload['binding_revision'] == allocations['binding_revision'] and
                    payload['plan_ref']['entity_id'] == allocations['plan_id'], 'separate frozen binding revision', path)
            require(payload['plan_ref']['revision'] == allocations['plan_revision'],
                    'binding references its separately allocated plan revision', path)
            for mapping in payload['task_mappings']:
                task_id = codec.validate_task_id(mapping['task_id'])
                require(str(task_id) in allocations['task_definitions'],
                        'every binding Task explicitly joined and protected', task_id)
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        targets.append({'path': path, 'schema_version': template['schema_version'],
            'before_raw_digest': template['before_raw_digest'], 'after_payload': payload,
            'after_raw_digest': codec.raw_digest(raw), 'verification_mode': template['verification_mode']})
        indexed_targets[index] = targets[-1]
        if payload['schema_version'] == PLAN:
            derived_plan_ref = adopted_plan_ref(targets[-1])
    targets = [indexed_targets[index] for index in range(len(templates))]
    require(plan_targets == 1, 'one exact adopted plan projection', plan_targets)
    validate_binding_targets(allocations, targets)
    if 'origin_profile' in request['material']:
        from _b_route_qualified_origin import check_bootstrap_targets
        check_bootstrap_targets(targets, allocations)
    plan_ids = {allocations['plan_id']}
    task_ids = {int(value) for value in allocations['task_definitions']}
    explicit_paths = {request['review_ref']['path']}
    for kind in ('requirements', 'flows'):
        for row in request['material']['identity_alignment'][kind]:
            if row['mode'] == 'reuse':
                ref = row['evidence_ref']
                explicit_paths.add(ref['path'])
                value = snapshot.ref(ref)
                if value.get('schema_version') == PLAN:
                    plan_ids.add(value['plan_id'])
    for key in ('plan_ref', 'binding_ref'):
        for alignment in (request['material']['identity_alignment']['plan'],
                          request['material']['identity_alignment']['binding']):
            if key in alignment:
                explicit_paths.add(alignment[key]['path'])
    def dependency_plans(value):
        if type(value) is dict:
            if value.get('schema_version') == PLAN and value.get('path') in _current_plan_refs(snapshot):
                plan_ids.add(codec.validate_business_id(value['entity_id']))
            for child in value.values():
                dependency_plans(child)
        elif type(value) is list:
            for child in value:
                dependency_plans(child)
    dependency_plans(snapshot.handoff['proposal']['content'].get('selected_dependencies', []))
    definitions = expected_content['definitions']
    for family, kind in (('commands', 'command'), ('states', 'state')):
        for definition in definitions[family]:
            for owner in (snapshot.catalog or {}).get('definition_owners', []):
                if owner['kind'] == kind and owner['definition_id'] == definition['id']:
                    require(owner['plan_ref']['entity_id'] == allocations['plan_id'] and
                            owner['plan_ref']['path'] in snapshot.prepared['inputs']['dependencies']['files'],
                            'original independently reviewed current definition owner', definition['id'],
                            codec.ReasonCode.DUPLICATE_OWNER)
                    plan_ids.add(owner['plan_ref']['entity_id'])
    # Shared Task membership expands to current and new plan sets, transitively.
    for _ in range(len((snapshot.catalog or {}).get('task_index', [])) + 1):
        old = (set(plan_ids), set(task_ids))
        for row in (snapshot.catalog or {}).get('task_index', []):
            related = {ref['entity_id'] for ref in row['plan_refs']}
            if row['task_id'] in task_ids or related & plan_ids:
                task_ids.add(row['task_id']); plan_ids.update(related)
        if old == (plan_ids, task_ids):
            break
    protected_tasks = {row['task_id']: row['definition_digest'] for row in snapshot.protection['tasks']}
    for task_id in task_ids:
        require(task_id in snapshot.tasks and protected_tasks.get(task_id) == snapshot.tasks[task_id],
                'unchanged protected definition/history for every transitive Task scope', task_id,
                codec.ReasonCode.INPUT_STALE)
    scopes = list(resource_scopes(target_paths=[row['path'] for row in targets],
        plan_ids=plan_ids, requirement_ids=set(allocations['requirements']) | set(allocations['requirements'].values()),
        flow_ids=allocations['flows'].values(), task_ids=task_ids,
        command_ids=[row['id'] for row in definitions['commands']],
        state_ids=[row['id'] for row in definitions['states']]))
    # A revision replaces all already-published heads for its affected plans,
    # including old file-resource scopes. Freeze them before host review; the
    # commit owner must not invent extra publication scopes after reservation.
    scopes = sorted(set(scopes) | {head['scope_id'] for head in (snapshot.catalog or {}).get('scope_heads', [])
        if any(ref['entity_id'] in plan_ids for family in ('plan_refs', 'binding_refs') for ref in head[family])})
    authority = [{'path': path, 'schema_version': 'raw.bytes.v1', 'raw_digest': digest}
        for path, digest in sorted(snapshot.files.items())
        if digest is not None and path in snapshot.proof_paths | explicit_paths
        and path not in {t['path'] for t in targets}]
    return {'request': request, 'allocations': allocations, 'scope_ids': scopes,
            'authority_refs': authority, 'targets': targets}


def _result(envelope):
    return {'operation_id': envelope['operation_id'], 'state': envelope['state'],
        'scope_ids': envelope['frozen']['scope_ids'], 'request_digest': envelope['request_digest'],
        'frozen_digest': envelope['frozen_digest'], 'allocations': envelope['frozen']['allocations'],
        'resume_ref': operation_ref(envelope['operation_id']), 'diagnostics': [], **FLAGS}


def public(function):
    @wraps(function)
    def checked(root, *, operation_id, **kwargs):
        try:
            return function(root, operation_id=operation_id, **kwargs)
        except codec.CodecError as error:
            diagnostic = error.diagnostic
            if diagnostic.entity_id is None and type(operation_id) is str:
                diagnostic = replace(diagnostic, entity_id=operation_id)
            raise codec.CodecError(diagnostic) from error
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
            details = getattr(error, 'reader_diagnostic', None)
            if type(details) is not dict or details.get('schema_version') != 'newrouge.b-route-reader-failure.v1':
                details = type(error).__name__
            fail(codec.ReasonCode.IDENTITY_UNPROVABLE, 'complete current adoption evidence',
                 details, operation_id)
    return checked


def _run(root, operation_id, request_raw, *, reserve_only=False):
    from _b_route_operation_scope import initialize_lock_namespace, scope_guard
    import _b_route_adoption_review as host_review
    root = Path(root).resolve()
    codec.validate_business_id(operation_id)
    request = journal.validate_operation_request(request_raw)
    if request['schema_version'] == journal.COMPENSATION_REQUEST:
        import _b_route_compensation as compensation
        return compensation.run(root, operation_id, request_raw, reserve_only=reserve_only)
    require(request['operation_id'] == operation_id, operation_id, request['operation_id'], codec.ReasonCode.CONFLICT)
    inventory = journal.operation_inventory(root)
    validate_operations(inventory)
    existing = next((row for row in inventory if row['operation_id'] == operation_id), None)
    if existing:
        require(existing['request_digest'] == codec.canonical_digest(request),
                'same ID and complete request', operation_id, codec.ReasonCode.CONFLICT)
        # Canonical-equivalent request formatting must not change the original
        # target serializer's object order or any frozen after bytes.
        request = existing['frozen']['request']
        request_raw = base64.b64decode(existing['request_raw_base64'], validate=True)
    require(not reserve_only or existing is not None, 'original prepared operation', operation_id,
            codec.ReasonCode.FILE_NOT_FOUND)
    if 'host_review_ref' not in request and 'origin_profile' not in request['material']:
        # Preserve the useful native pending diagnostic without acquiring any
        # activity lease. A selected marker never substitutes for host review.
        import _b_route_planning_runtime as runtime
        run = runtime.run_location(root, request['material']['planner'], request['material']['run_id'])
        state_path = safe_path(root, (run / 'run.json').relative_to(root).as_posix())
        if state_path.is_file():
            state = codec.strict_json_loads(state_path.read_bytes())
            require(state.get('selection_status') == 'selected', 'complete selected 3B run',
                    state.get('selection_status'), codec.ReasonCode.UNPUBLISHED)
    subject, review_refs = host_review.verify_saved(root, request)
    # Use the reviewed serializer order, preserving frozen after-byte identities
    # under a canonical-equivalent request reformat.
    request = {**subject['request'], 'host_review_ref': request['host_review_ref']}
    initialize_lock_namespace(root)
    with capture_completed(root, request['material'], request['review_ref']) as snapshot:
        proposal = existing or {'operation_id': operation_id, 'frozen': {'allocations': subject['preview']['allocations']}}
        allocations = propose_allocations(snapshot, request['material']['identity_alignment'], inventory, proposal)
        frozen = build_frozen(snapshot, request, allocations)
        require(codec.canonical_digest(host_review.make_subject(snapshot, request, frozen)) == codec.canonical_digest(subject),
                'current native proof, request, preview and host review', operation_id, codec.ReasonCode.INPUT_STALE)
        original_frozen = deepcopy(frozen)
        host_review.bind_review_support(snapshot, review_refs, operation_id)
        frozen['authority_refs'] = sorted([*frozen['authority_refs'], *review_refs], key=lambda row: row['path'])
        if existing:
            # References and targets belong to the original immutable operation.
            require(codec.canonical_digest(frozen) == codec.canonical_digest(existing['frozen']),
                    'unchanged frozen operation and proof closure', operation_id,
                    codec.ReasonCode.INPUT_STALE)
        def persist():
            _committed(snapshot)
            current = journal.operation_inventory(root)
            validate_operations(current)
            # UUIDs above are proposals, not durable assignments. Recheck the
            # complete claim under the acquired lease before persisting it.
            proposal = existing or {'operation_id': operation_id, 'frozen': {'allocations': allocations}}
            checked = propose_allocations(snapshot, request['material']['identity_alignment'], current, proposal)
            require(codec.canonical_digest(checked) == codec.canonical_digest(allocations),
                    'same proposed allocations under lease', checked, codec.ReasonCode.INPUT_STALE)
            require(codec.canonical_digest(host_review.make_subject(snapshot, request, original_frozen))
                    == codec.canonical_digest(subject), 'same reviewed context under lease', operation_id,
                    codec.ReasonCode.INPUT_STALE)
            snapshot.verify()
            for row in journal.active_operation_inventory(root):
                require(row['operation_id'] == operation_id or not
                        (set(row['frozen']['scope_ids']) & set(frozen['scope_ids'])),
                        'no overlapping durable pending operation', row['operation_id'], codec.ReasonCode.PENDING)
            prepared = journal.prepare_operation(root, operation_id=operation_id,
                request_raw=request_raw, frozen=frozen)
            return journal.reserve_operation(root, operation_id=operation_id) if reserve_only else prepared
        with scope_guard(root, frozen['scope_ids'], prepare_under_lease=persist, operation_id=operation_id) as envelope:
            return _result(envelope)


def _review_preview(root, request, *, seal=False, compensation_delivery=None):
    if request['schema_version'] == journal.COMPENSATION_REQUEST:
        import _b_route_compensation as compensation
        return compensation.review_preview(root, request, seal=seal, delivery=compensation_delivery)
    require(compensation_delivery is None, 'compensation-only delivery selection', compensation_delivery)
    require('review_profile' not in request, 'fresh expanded-semantics.v3 review belongs to real R56 owner; R55 historical consumption is separate', request.get('operation_id'))
    import _b_route_adoption_review as review
    from _b_route_operation_scope import initialize_lock_namespace, scope_guard
    operation_id = request['operation_id']
    inventory = journal.operation_inventory(root)
    validate_operations(inventory)
    subject_path = safe_path(root, review.location(operation_id) + '/subject.json')
    saved = review.read_subject(root, operation_id) if subject_path.exists() else None
    if saved:
        require(codec.canonical_digest(saved['request']) == codec.canonical_digest(review.request_body(request)),
                'same original review request', operation_id, codec.ReasonCode.CONFLICT)
        request = saved['request']
    require(not seal or saved is not None, 'existing complete review subject', operation_id,
            codec.ReasonCode.FILE_NOT_FOUND)
    initialize_lock_namespace(root)
    review.initialize_namespace(root)
    with capture_completed(root, request['material'], request['review_ref']) as snapshot:
        proposal = {'operation_id': operation_id, 'frozen': {'allocations': saved['preview']['allocations']}} if saved else None
        allocations = propose_allocations(snapshot, request['material']['identity_alignment'], inventory, proposal)
        frozen = build_frozen(snapshot, request, allocations)
        subject = review.make_subject(snapshot, request, frozen)
        require(saved is None or codec.canonical_digest(subject) == codec.canonical_digest(saved),
                'same current review subject and concrete preview', operation_id, codec.ReasonCode.INPUT_STALE)
        proof = review.produce_proof(root, operation_id) if seal else None
        if proof is not None:
            review.bind_review_support(snapshot, proof['files'], operation_id)
        def persist():
            _committed(snapshot)
            current = journal.operation_inventory(root)
            validate_operations(current)
            propose_allocations(snapshot, request['material']['identity_alignment'], current,
                                {'operation_id': operation_id, 'frozen': {'allocations': allocations}})
            require(codec.canonical_digest(review.make_subject(snapshot, request, frozen)) == codec.canonical_digest(subject),
                    'same review context under complete scopes', operation_id, codec.ReasonCode.INPUT_STALE)
            snapshot.verify()
            home = review.location(operation_id)
            for name, data in (('subject.json', review.raw(subject)), ('w/prompt.txt', review.prompt(subject).encode('utf-8')),
                               ('w/schema.json', review.raw(review.verdict_schema(subject))),
                               ('request.txt', review.request_payload(subject).encode('utf-8'))):
                review.write_once(root, home + '/' + name, data)
            if seal:
                return {'status': 'reviewed', 'host_review_ref': review.seal(root, operation_id, proof), **FLAGS}
            return {'status': 'review_prepared', 'operation_id': operation_id, 'subject_ref': home + '/subject.json',
                    'subject_digest': codec.canonical_digest(subject), 'workspace': home + '/w',
                    'machine_preservation': review.machine_mode(subject),
                    'semantic_execution_required': review.machine_mode(subject) is None,
                    'runner_command': review.runner_command(root, operation_id),
                    'required_environment': {'NEWROGUE_CODEX_REASONING_EFFORT': 'high'},
                    'execution_capture_ref': home + '/execution.json',
                    'model_dispatched': False, **FLAGS}
        with scope_guard(root, frozen['scope_ids'], prepare_under_lease=persist, operation_id=operation_id) as result:
            return result


@public
def prepare_review(root, *, operation_id, request_ref, compensation_delivery=None):
    root = Path(root).resolve()
    request = journal.validate_operation_request(safe_path(root, request_ref).read_bytes())
    require(request['operation_id'] == operation_id, operation_id, request['operation_id'], codec.ReasonCode.CONFLICT)
    require('host_review_ref' not in request, 'review source without a circular self reference', operation_id)
    return _review_preview(root, request, compensation_delivery=compensation_delivery)


@public
def complete_review(root, *, operation_id):
    import _b_route_adoption_review as review
    root = Path(root).resolve()
    subject = review.read_subject(root, operation_id)
    return _review_preview(root, subject['request'], seal=True)


@public
def prepare(root, *, operation_id, request_ref):
    root = Path(root).resolve()
    return _run(root, operation_id, safe_path(root, request_ref).read_bytes())


@public
def reserve(root, *, operation_id):
    envelope = journal.read_operation(Path(root).resolve(), operation_id=operation_id)
    return _run(root, operation_id, base64.b64decode(envelope['request_raw_base64'], validate=True), reserve_only=True)


@contextmanager
def commit_context(root, *, operation_id):
    """Fresh initial commit admission; later owned writes use its closed intent.

    This does not reserve again or reinterpret a partially applied operation as
    a new before-only adoption. All native locks retain their original owner.
    """
    import _b_route_adoption_review as review
    root = Path(root).resolve()
    envelope = journal.read_operation(root, operation_id=operation_id)
    if envelope['schema_version'] == journal.COMPENSATION_SCHEMA:
        import _b_route_compensation as compensation
        with compensation.commit_context(root, operation_id=operation_id) as captured:
            yield captured
        return
    require(envelope['state'] == 'reserved', 'reserved original operation', operation_id)
    validate_operations([envelope])
    request = envelope['frozen']['request']
    subject, support = review.verify_saved(root, request)
    with capture_completed(root, request['material'], request['review_ref']) as snapshot:
        frozen = build_frozen(snapshot, request, envelope['frozen']['allocations'])
        require(codec.canonical_digest(review.make_subject(snapshot, request, frozen))
                == codec.canonical_digest(subject), 'current complete reviewed commit context', operation_id,
                codec.ReasonCode.INPUT_STALE)
        review.bind_review_support(snapshot, support, operation_id)
        frozen['authority_refs'] = sorted([*frozen['authority_refs'], *support], key=lambda row: row['path'])
        require(codec.canonical_digest(frozen) == envelope['frozen_digest'],
                'unchanged reserved frozen operation', operation_id, codec.ReasonCode.INPUT_STALE)
        snapshot.verify()
        yield snapshot, envelope


@public
def inspect(root, *, operation_id):
    root = Path(root).resolve()
    envelope = journal.read_operation(root, operation_id=operation_id)
    validate_operations([envelope])
    snapshot = Snapshot(root)
    for ref in envelope['frozen']['authority_refs']:
        snapshot.ref(ref)
    differences = []
    for target in envelope['frozen']['targets']:
        current = snapshot.read(target['path'], optional=True)
        digest = codec.raw_digest(current) if current is not None else None
        differences.append({'path': target['path'], 'expected_before': target['before_raw_digest'],
            'actual': digest, 'frozen_after': target['after_raw_digest'],
            'matches_before': digest == target['before_raw_digest']})
    snapshot.verify()
    diagnostics = [codec.Diagnostic(codec.ReasonCode.INPUT_STALE, codec.Stage.TARGET,
        operation_id, row['expected_before'], row['actual'], operation_ref(operation_id)).to_dict()
        for row in differences if not row['matches_before']]
    return {**_result(envelope), 'target_differences': differences, 'diagnostics': diagnostics,
            'status': 'blocked' if diagnostics else 'inspected',
            'eligibility': 'not granted by inspect; reserve revalidates native current proof'}
