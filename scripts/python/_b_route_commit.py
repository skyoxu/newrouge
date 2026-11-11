"""One shared apply/verify/catalog-last owner. No dispatch or automatic recovery."""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from copy import deepcopy
import base64
import os
from pathlib import Path
import uuid

import _b_route_codec as codec
import _b_route_records as records
import _b_route_commit_projection as projection
import _planning_apply_journal as journal
from _b_route_operation_scope import business_guard, writer_boundary
from _planning_skill_common import atomic_json_temp_path, atomic_json_win32_paths_fit

SCHEMA = 'newrouge.b-route-commit-intent.v1'
PHASES = ('intent', 'applied', 'verified', 'publishing', 'published', 'complete')
SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'docs/planning/b-route/schemas/commit-intent.schema.json'
FLAGS = {'readiness': False, 'runtime_verified': False, 'default_b_enabled': False}
_BOUNDARY = ContextVar('b_route_commit_boundary', default=None)


def _fail(expected, actual, code=codec.ReasonCode.CONFLICT, resume=None):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.BUNDLE,
        expected=expected, actual=actual, resume_ref=resume))


def _require(condition, expected, actual, code=codec.ReasonCode.CONFLICT):
    if not condition:
        _fail(expected, actual, code)


def _encode(raw):
    return None if raw is None else base64.b64encode(raw).decode('ascii')


def _decode(value):
    if value is None:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        _fail('complete original bytes', 'invalid base64', codec.ReasonCode.INVALID_JSON)


def _digest(raw):
    return None if raw is None else codec.raw_digest(raw)


def _paths(operation_id):
    home = journal._operation_ref(operation_id).rsplit('/', 1)[0]
    return home + '/commit.json', home + '/commit.pending.json'


def _read(root, relative, *, optional=False):
    path = journal._operation_path(root, relative)
    if optional and not path.exists():
        return None
    return codec.read_reference_bytes(root, relative)


def _schema(value):
    import _b_route_schema_resources as schemas
    document = codec.strict_json_loads(SCHEMA_PATH.read_bytes())
    validator = schemas.validator('newrouge.b-route-plan.v1').evolve(schema=document)
    errors = sorted(validator.iter_errors(value), key=lambda item: str(list(item.path)))
    _require(not errors, 'closed versioned commit intent', 'schema mismatch', codec.ReasonCode.SCHEMA_MISMATCH)


def _seal(value):
    value = deepcopy(value)
    value['catalog_after_digest'] = _digest(_decode(value['catalog_after']))
    value['intent_digest'] = codec.canonical_digest({key: item for key, item in value.items() if key != 'intent_digest'})
    _schema(value)
    return value


def validate_local(root, envelope):
    """Validate optional local commit metadata without erasing operation history."""
    intent_ref, pending_ref = _paths(envelope['operation_id'])
    raw = _read(root, intent_ref, optional=True)
    pending = _read(root, pending_ref, optional=True)
    expected_marker = {'schema_version': SCHEMA + '.pending', 'operation_id': envelope['operation_id'],
                       'frozen_digest': envelope['frozen_digest']}
    if pending is not None:
        _require(codec.strict_json_loads(pending) == expected_marker, 'exact owned pending marker', pending_ref)
    if raw is None:
        return None
    value = codec.strict_json_loads(raw)
    _schema(value)
    _require(value == _seal(value) and value['operation_id'] == envelope['operation_id']
             and value['frozen_digest'] == envelope['frozen_digest'], 'original operation-bound intent', intent_ref)
    frozen = envelope['frozen']
    _require(value['receipt']['operation_digest'] == envelope['frozen_digest']
             and value['receipt']['operation_id'] == envelope['operation_id'], 'receipt bound to complete frozen request', intent_ref)
    target_names = {row['path'] for row in frozen['targets']}
    _require(set(value['before_files']) == target_names | {records.CATALOG_PATH}, 'complete original before images', intent_ref)
    for target in frozen['targets']:
        _require(_digest(_decode(value['before_files'][target['path']])) == target['before_raw_digest'],
                 'original target before bytes', target['path'])
    _require(value['catalog_before'] == value['before_files'][records.CATALOG_PATH], 'same original catalog image', intent_ref)
    expected = projection.receipt_for_frozen(operation_id=envelope['operation_id'], frozen=frozen,
        resolved_definitions=value['receipt']['resolved_definitions'],
        catalog_before=_decode(value['catalog_before']))
    _require(expected == value['receipt'], 'exact original receipt draft', intent_ref)
    if value['catalog_after'] is not None:
        catalog_raw = _decode(value['catalog_after'])
        checked = records.validate_record(catalog_raw, path=records.CATALOG_PATH)
        if not checked.ok:
            raise codec.CodecError(checked.diagnostic)
        catalog = codec.strict_json_loads(catalog_raw)
        old = _decode(value['publication_base'])
        revision = 1 if old is None else codec.strict_json_loads(old)['revision'] + 1
        _require(catalog['revision'] == revision, 'one catalog revision per publication', intent_ref)
        heads = {row['scope_id']: row for row in catalog['scope_heads']}
        ref = projection.reference(records.BASE + 'commits/' + envelope['operation_id'] + '.json',
                                   projection.serialized(value['receipt']))
        _require(all(key in heads and heads[key]['receipt_ref'] == ref for key in frozen['scope_ids']),
                 'all frozen scopes select one receipt', intent_ref)
    _require(value['phase'] not in ('publishing', 'published', 'complete') or value['catalog_after'] is not None,
             'durable catalog payload before publication', intent_ref)
    return value


def _checkpoint(name):
    """Fault-test seam only; no environment switch or production skip path."""


def _write(root, relative, raw):
    """Only the short physical replacement holds original metadata/WRITER."""
    from _b_route_operation_scope import writer_boundary
    observed = _read(root, relative, optional=True)
    boundary = _BOUNDARY.get()
    def recheck():
        _require(_read(root, relative, optional=True) == observed,
                 'same target at atomic replacement boundary', relative, codec.ReasonCode.INPUT_STALE)
        if boundary is not None:
            boundary()
    with writer_boundary(root, recheck=recheck):
        _replace(root, relative, raw)
        if boundary is not None:
            boundary.facts[str(root / relative)] = codec.raw_digest(raw)
            for name, members in boundary.directories.items():
                directory = Path(name)
                if root / relative != directory and (root / relative).is_relative_to(directory):
                    members.add((root / relative).relative_to(directory).parts[0])
            for name, members in boundary.trees.items():
                if (root / relative).is_relative_to(root / name):
                    members.add(relative)


def _replace(root, relative, raw):
    """Flush complete bytes before one atomic replacement; never repair others."""
    path = journal._operation_path(root, relative)
    journal._operation_no_reparse(path)
    if os.name == 'nt':
        _require(atomic_json_win32_paths_fit(path), 'Win32 commit path capacity', relative,
                 codec.ReasonCode.UNSAFE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    journal._operation_no_reparse(path)
    temporary = atomic_json_temp_path(path, uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Shared leases exclude managed writers. Arbitrary external editors
        # are not a database transaction; the caller rechecks before this call.
        os.replace(temporary, path)
        with path.open('r+b') as stream:
            os.fsync(stream.fileno())
    finally:
        if temporary.exists():
            temporary.unlink()
    _require(_read(root, relative) == raw, 'unchanged replaced bytes', relative)


def _save(root, intent, phase=None, **changes):
    if phase is not None:
        _require(PHASES.index(phase) >= PHASES.index(intent['phase']), 'monotonic commit lifecycle', phase)
    value = _seal({**intent, **changes, 'phase': phase or intent['phase']})
    _write(root, _paths(value['operation_id'])[0], projection.serialized(value))
    return value


def _task_join(root):
    import _b_route_adoption as adoption
    return adoption._task_context(adoption.Snapshot(root))


def _receipt_path(envelope):
    return records.BASE + 'commits/' + envelope['operation_id'] + '.json'


def _candidates(root, envelope):
    return {row['path']: projection.serialized(row['after_payload']) for row in envelope['frozen']['targets']}


def _draft(root, envelope, catalog_before):
    frozen = envelope['frozen']
    candidates = _candidates(root, envelope)
    bundle = records._Bundle(candidates, root, records.CATALOG_PATH, None, _task_join(root))
    owners = {} if catalog_before is None else {(row['kind'], row['definition_id']): row
        for row in codec.strict_json_loads(catalog_before)['definition_owners']}
    plan_ids = {row['after_payload']['plan_id'] for row in frozen['targets']
                if row['schema_version'] == 'newrouge.b-route-plan.v1'}
    owners = {key: row for key, row in owners.items() if row['plan_ref']['entity_id'] not in plan_ids}
    receipt = projection.receipt_for_frozen(operation_id=envelope['operation_id'], frozen=frozen,
        resolved_definitions=[], catalog_before=catalog_before)
    for ref in receipt['plan_refs']:
        plan = bundle.reference(ref)
        for plural, kind in (('flows', 'flow'), ('commands', 'command'), ('states', 'state')):
            for row in plan['definitions'][plural]:
                key = kind, row['id']
                owner = {'kind': kind, 'definition_id': row['id'], 'plan_ref': ref}
                _require(key not in owners or owners[key] == owner, 'one definition owner', list(key))
                owners[key] = owner
    resolved = bundle.closure(receipt['plan_refs'], receipt['binding_refs'], owners, _receipt_path(envelope))
    return projection.receipt_for_frozen(operation_id=envelope['operation_id'], frozen=frozen,
        resolved_definitions=[resolved[key] for key in sorted(resolved)], catalog_before=catalog_before)


def _observations(root, snapshot):
    files = {str(root / name): value for name, value in snapshot.files.items()}
    directories = {}
    if snapshot.native_capture is not None:
        for name, value in snapshot.native_capture['files'].items():
            _require(name not in files or files[name] == value, 'one observed source image', name)
            files[name] = value
        directories = deepcopy(snapshot.native_capture['directories'])
    return files, directories, deepcopy(snapshot.directories)


def _catalog_frame(root, envelope, raw, before_files, *, origins_raw=None):
    if raw is None:
        return None
    from _b_route_operation_scope import resource_scopes
    catalog = codec.strict_json_loads(raw)
    checked = records.validate_record(raw, path=records.CATALOG_PATH)
    if not checked.ok:
        raise codec.CodecError(checked.diagnostic)
    scopes = set(envelope['frozen']['scope_ids'])
    ids = {ref['entity_id'] for head in catalog['scope_heads'] for family in ('plan_refs', 'binding_refs')
           for ref in head[family] if set(resource_scopes(plan_ids=[ref['entity_id']])) & scopes}
    ids.add(envelope['frozen']['allocations']['plan_id'])
    tasks = {int(key) for key in envelope['frozen']['allocations']['task_definitions']}
    rows = [row for row in catalog['task_index'] if row['task_id'] in tasks
            or ids & {ref['entity_id'] for ref in row['plan_refs']}]
    tasks.update(row['task_id'] for row in rows)
    origin_ref = catalog['origins_ref']
    supplied_origin = origins_raw is not None
    if origins_raw is None:
        origins_raw = _read(root, origin_ref['path'])
    # Our own unpublished governance replacement is interpreted against its
    # retained exact before image; no foreign edit receives this exception.
    if not supplied_origin and origin_ref['path'] in before_files:
        original = _decode(before_files[origin_ref['path']])
        if original is not None and codec.raw_digest(original) == origin_ref['digest']:
            origins_raw = original
    origins = codec.strict_json_loads(origins_raw)
    identity = codec.TypedReference.from_value(origin_ref)
    checked = records.validate_record(origins_raw, path=origin_ref['path'])
    if not checked.ok:
        raise codec.CodecError(checked.diagnostic)
    _require(codec._record_identity(origins) == (identity.schema_version, identity.entity_id, identity.revision),
             'exact original origins identity', origin_ref['path'])
    expected_digest = codec.raw_digest(origins_raw) if origin_ref['verification_mode'] == 'raw' else codec.canonical_digest(origins)
    _require(expected_digest == origin_ref['digest'], 'exact current origins reference', origin_ref['path'])
    return {'policy_ref': catalog['policy_ref'],
        'heads': [head for head in catalog['scope_heads'] if head['scope_id'] in scopes or any(
            ref['entity_id'] in ids for family in ('plan_refs', 'binding_refs') for ref in head[family])],
        'owners': [row for row in catalog['definition_owners'] if row['plan_ref']['entity_id'] in ids],
        'tasks': rows, 'origins': [row for row in origins['tasks'] if row['task_id'] in tasks]}


def _owned_paths(root, envelope):
    return {str(root / name) for name in [records.CATALOG_PATH, _receipt_path(envelope),
        *_paths(envelope['operation_id']), *(row['path'] for row in envelope['frozen']['targets'])]}


def _verify_observations(root, envelope, intent, *, published=False, initial=False):
    facts = _VerifiedFacts()
    _validated_policy_facts(intent, facts)
    if envelope['schema_version'] == journal.COMPENSATION_SCHEMA:
        import _b_route_compensation as compensation
        compensation.verify_observations(root, envelope, intent, facts=facts, published=published)
        _validated_local_facts(root, envelope, intent, facts, initial=initial)
        _capture_boundary(root, envelope, intent, facts)
        return
    import _b_route_adoption_review as review
    from _b_route_frozen_native_reader import _safe
    _require(intent['policy_identity'] == review.policy_identity(), 'same reviewed current rules', 'policy changed', codec.ReasonCode.INPUT_STALE)
    # Full semantic/protocol replay belongs to execute/commit_context before
    # metadata acquisition. Here recheck the exact source-bound subject and
    # every frozen support byte at each side-effect boundary.
    subject = review.read_subject(root, envelope['operation_id'])
    reviewed = deepcopy(subject['preview'])
    reviewed['request'] = deepcopy(envelope['frozen']['request'])
    review_ref = envelope['frozen']['request']['host_review_ref']
    review_proof = codec.strict_json_loads(_read(root, review_ref['path']))
    reviewed['authority_refs'] = sorted([*reviewed['authority_refs'], review_ref,
                                        *review_proof['files']], key=lambda row: row['path'])
    _require(codec.canonical_digest(reviewed) == envelope['frozen_digest'],
             'exact independently reviewed frozen request and support closure',
             envelope['operation_id'], codec.ReasonCode.INPUT_STALE)
    affected = subject['affected_catalog']
    expected_frame = None
    if affected is not None:
        origins = codec.strict_json_loads(_decode(intent['origins_before']))
        ids = {int(key) for key in subject['task_definitions']}
        expected_frame = {'policy_ref': affected['policy_ref'], 'heads': affected['scope_heads'],
            'owners': affected['definition_owners'], 'tasks': affected['task_index'],
            'origins': [row for row in origins['tasks'] if row['task_id'] in ids]}
    else:
        _require(intent['catalog_before'] is None and intent['origins_before'] is None,
                 'genuinely absent original bootstrap catalog', envelope['operation_id'])
    original_frame = _catalog_frame(root, envelope, _decode(intent['catalog_before']), intent['before_files'],
                                   origins_raw=_decode(intent['origins_before']))
    _require(intent['catalog_frame'] == original_frame == expected_frame,
             'exact original independently reviewed affected catalog frame', envelope['operation_id'])
    required_files = {str(root / row['path']): row['raw_digest'] for row in envelope['frozen']['authority_refs']}
    required_files.update({str(root / name): expected for name, expected in
        subject['prepared']['inputs']['dependencies']['files'].items()})
    native = subject.get('native_capture')
    if native is not None:
        required_files.update(native['files'])
        _require(all(intent['directories'].get(name) == members for name, members in native['directories'].items()),
                 'complete original reviewed native directory closure', envelope['operation_id'])
    _require(all(name in intent['files'] and intent['files'][name] == expected
                 for name, expected in required_files.items()),
             'complete original reviewed source and authority closure', envelope['operation_id'])
    import _b_route_adoption as adoption
    current_tasks = adoption.Snapshot(root)
    adoption._task_context(current_tasks)
    _require(all(current_tasks.task_payloads.get(int(key)) == value for key, value in subject['task_definitions'].items()),
             'unchanged related Task definitions and joined identities', envelope['operation_id'], codec.ReasonCode.INPUT_STALE)
    # Complete qualification is performed before the first formal write. From
    # then on only this exact operation's recorded before/after transitions are
    # allowed; no older summary or caller flag substitutes for its closure.
    permitted = {str(root / row['path']): {row['before_raw_digest'], row['after_raw_digest']}
                 for row in envelope['frozen']['targets']}
    permitted[str(root / records.CATALOG_PATH)] = {_digest(_decode(intent['catalog_before']))}
    if intent['catalog_after'] is not None:
        permitted[str(root / records.CATALOG_PATH)].add(_digest(_decode(intent['catalog_after'])))
    for name, expected in intent['files'].items():
        if name == str(root / records.CATALOG_PATH):
            continue
        path = _safe(Path(name), missing=True)
        actual = _digest(path.read_bytes() if path.is_file() else None)
        _require(actual in permitted.get(name, {expected}), 'unchanged source/authority or exact owned target image', name,
                 codec.ReasonCode.INPUT_STALE)
        facts.file(name, actual)
    owned = _owned_paths(root, envelope)
    expected_frame = (_catalog_frame(root, envelope, _decode(intent['catalog_after']), intent['before_files'])
                      if published else intent['catalog_frame'])
    current_catalog = _read(root, records.CATALOG_PATH, optional=True)
    if current_catalog is not None and current_catalog not in (
            _decode(intent['catalog_before']), _decode(intent['catalog_after'])):
        _require(_catalog_frame(root, envelope, current_catalog, intent['before_files']) == expected_frame,
                 'unchanged affected scope before admitting unrelated formal additions', records.CATALOG_PATH)
        committed = records.published_bundle(root, catalog_raw=current_catalog, task_join=_task_join(root))
        owned.update(str(root / name) for name in committed['formal_paths'] if name.startswith(tuple(
            records.BASE + family + '/' for family in ('plans', 'bindings', 'commits'))))
    for name, expected in intent['directories'].items():
        path = _safe(Path(name), directory=True)
        actual = {item.name for item in path.iterdir()}
        additions = {Path(child).relative_to(path).parts[0] for child in owned
                     if Path(child).is_relative_to(path) and Path(child) != path}
        _require(set(expected) <= actual and actual - set(expected) <= additions,
                 'same directory membership plus exact owned additions', name, codec.ReasonCode.INPUT_STALE)
        facts.directories[name] = actual
    for name, expected in intent['trees'].items():
        path = journal._operation_path(root, name)
        actual = set()
        if path.exists():
            for child in path.rglob('*'):
                journal._operation_no_reparse(child)
                if child.is_file():
                    actual.add(child.relative_to(root).as_posix())
        extra = {Path(child).relative_to(root).as_posix() for child in owned}
        _require(set(expected) <= actual and actual - set(expected) <= extra,
                 'same observed tree plus exact owned additions', name, codec.ReasonCode.INPUT_STALE)
        facts.trees[name] = actual
    for target in envelope['frozen']['targets']:
        checked = journal.classify_frozen_target(root, target)
        facts.file(str(root / target['path']), checked['actual_raw_digest'])
    for ref in envelope['frozen']['authority_refs']:
        if ref['path'] == records.CATALOG_PATH:
            continue
        name = str(root / ref['path'])
        actual = _digest(_read(root, ref['path']))
        _require(actual in permitted.get(name, {ref['raw_digest']}), 'original authority binding', ref['path'], codec.ReasonCode.INPUT_STALE)
        facts.file(name, actual)
    current = _read(root, records.CATALOG_PATH, optional=True)
    if intent['catalog_after'] is None or current != _decode(intent['catalog_after']):
        _require(_catalog_frame(root, envelope, current, intent['before_files']) == expected_frame,
                 'same affected catalog semantics; unrelated publication may advance', records.CATALOG_PATH,
                 codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / records.CATALOG_PATH), _digest(current))
    _validated_local_facts(root, envelope, intent, facts, initial=initial)
    _capture_boundary(root, envelope, intent, facts)


class _VerifiedFacts:
    """Only a digest from the same read that passed its owning check enters."""
    def __init__(self):
        self.files = {}
        self.directories = {}
        self.trees = {}

    def file(self, name, digest):
        _require(name not in self.files or self.files[name] == digest,
                 'one unchanged validated observation', name, codec.ReasonCode.INPUT_STALE)
        self.files[name] = digest


def _validated_policy_facts(intent, facts):
    """Use the original policy owner's digest and its same-read resource pins."""
    import _b_route_adoption_review as review
    identity, files = review.policy_observations()
    _require(identity == intent['policy_identity'], 'same reviewed current rules',
             'policy changed', codec.ReasonCode.INPUT_STALE)
    for name, digest in files.items():
        facts.file(name, digest)


def _validated_local_facts(root, envelope, intent, facts, *, initial=False):
    """Validate and pin operation/index and owned metadata before WRITER."""
    inventory = journal.operation_inventory(root)
    operation_ref = journal._operation_ref(envelope['operation_id'])
    operation_raw = _read(root, operation_ref)
    _require(codec.strict_json_loads(operation_raw) == envelope,
             'same original operation at validation boundary', operation_ref, codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / operation_ref), codec.raw_digest(operation_raw))
    index_ref = journal.OPERATION_STORE + '/pending.json'
    index_raw = _read(root, index_ref)
    index = codec.strict_json_loads(index_raw)
    journal._operation_schema(index, 'Pending')
    expected_index = {'schema_version': journal.PENDING_SCHEMA,
                      'operations': [journal._operation_index_row(row) for row in inventory]}
    _require(index == expected_index, 'same complete validated operation/index pair', index_ref,
             codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / index_ref), codec.raw_digest(index_raw))
    intent_ref, marker_ref = _paths(envelope['operation_id'])
    current_intent = _read(root, intent_ref, optional=True)
    _require((current_intent is None if initial else
              current_intent is not None and codec.strict_json_loads(current_intent) == intent),
             'original validated intent or initial absence', intent_ref, codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / intent_ref), _digest(current_intent))
    marker = _read(root, marker_ref, optional=True)
    expected_marker = {'schema_version': SCHEMA + '.pending', 'operation_id': envelope['operation_id'],
                       'frozen_digest': envelope['frozen_digest']}
    _require(marker is None or codec.strict_json_loads(marker) == expected_marker,
             'exact owned pending marker or original absence', marker_ref, codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / marker_ref), _digest(marker))
    receipt = _read(root, _receipt_path(envelope), optional=True)
    _require(receipt is None or receipt == projection.serialized(intent['receipt']),
             'immutable validated receipt or original absence', _receipt_path(envelope), codec.ReasonCode.INPUT_STALE)
    facts.file(str(root / _receipt_path(envelope)), _digest(receipt))


def _capture_boundary(root, envelope, intent, verified):
    """Install already validated reads; never promote a new current value.

    A foreign catalog advance fails stale at the short boundary. The next
    explicit call recomputes the projection after releasing global protection.
    """
    facts = dict(verified.files)
    directories = deepcopy(verified.directories)
    trees = deepcopy(verified.trees)
    def compare():
        from _b_route_frozen_native_reader import _safe
        for name, expected in facts.items():
            path = _safe(Path(name), missing=True)
            actual = _digest(path.read_bytes() if path.is_file() else None)
            _require(actual == expected, expected, {'path': name, 'raw_digest': actual}, codec.ReasonCode.INPUT_STALE)
        for name, expected in directories.items():
            path = _safe(Path(name), directory=True)
            _require({item.name for item in path.iterdir()} == expected,
                     'same validated directory members', name, codec.ReasonCode.INPUT_STALE)
        for name, expected in trees.items():
            path = journal._operation_path(root, name)
            actual = set()
            if path.exists():
                for child in path.rglob('*'):
                    journal._operation_no_reparse(child)
                    if child.is_file():
                        actual.add(child.relative_to(root).as_posix())
            _require(actual == expected, 'same validated tree members', name, codec.ReasonCode.INPUT_STALE)
    compare.facts = facts
    compare.directories = directories
    compare.trees = trees
    _BOUNDARY.set(compare)


def _initial(root, envelope, snapshot):
    snapshot.verify()
    before = {row['path']: _encode(_read(root, row['path'], optional=True)) for row in envelope['frozen']['targets']}
    before[records.CATALOG_PATH] = _encode(_read(root, records.CATALOG_PATH, optional=True))
    if before[records.CATALOG_PATH] is not None:
        records.published_bundle(root, task_join=_task_join(root))
    receipt = _draft(root, envelope, _decode(before[records.CATALOG_PATH]))
    origins_before = None
    if before[records.CATALOG_PATH] is not None:
        original_catalog = codec.strict_json_loads(_decode(before[records.CATALOG_PATH]))
        origins_before = _encode(_read(root, original_catalog['origins_ref']['path']))
    candidates = _candidates(root, envelope)
    if before[records.CATALOG_PATH] is not None:
        candidates[records.CATALOG_PATH] = _decode(before[records.CATALOG_PATH])
    # Validate the complete future bundle while all originals are still intact;
    # verify later repeats it against the actually written targets.
    projection.catalog_for_receipt(current_catalog=_decode(before[records.CATALOG_PATH]),
        receipt=receipt, candidates=candidates, task_join=_task_join(root), root=root, frozen=envelope['frozen'])
    files, directories, trees = _observations(root, snapshot)
    import _b_route_adoption_review as review
    value = _seal({'schema_version': SCHEMA, 'operation_id': envelope['operation_id'],
        'frozen_digest': envelope['frozen_digest'], 'policy_identity': review.policy_identity(),
        'phase': 'intent', 'before_files': before, 'files': files, 'directories': directories, 'trees': trees,
        'receipt': receipt, 'catalog_before': before[records.CATALOG_PATH], 'catalog_after': None,
        'origins_before': origins_before,
        'publication_base': before[records.CATALOG_PATH], 'catalog_attempts': [], 'catalog_after_digest': None,
        'catalog_frame': _catalog_frame(root, envelope, _decode(before[records.CATALOG_PATH]), before)})
    _verify_observations(root, envelope, value, initial=True)
    marker = {'schema_version': SCHEMA + '.pending', 'operation_id': envelope['operation_id'],
              'frozen_digest': envelope['frozen_digest']}
    _write(root, _paths(envelope['operation_id'])[1], projection.serialized(marker))
    _checkpoint('pending_durable')
    value = _save(root, value)
    _checkpoint('intent_durable')
    return value


def _publication_proven(root, envelope, intent, *, graph=None, historical=False):
    """Prove publication lineage; only completed history omits current freshness."""
    if intent is None or intent['phase'] not in ('publishing', 'published', 'complete'):
        return False
    current = _read(root, records.CATALOG_PATH, optional=True) if graph is None else graph['catalog_raw']
    if current is None:
        return False
    receipt_raw = (_read(root, _receipt_path(envelope)) if graph is None else graph['local_bytes'][_receipt_path(envelope)])
    _require(receipt_raw == projection.serialized(intent['receipt']),
             'unchanged published receipt', envelope['operation_id'])
    # A complete phase plus an unrelated valid current chain cannot prove this
    # operation was ever published. Follow only saved publication
    # images back from the actual catalog. This also retains terminal history
    # after later legitimate revisions replace this operation's scope heads.
    required = intent['catalog_after_digest']
    observed = {_digest(current)}
    publications = []
    inventory = journal.operation_inventory(root) if graph is None else graph['operations']
    for item in inventory:
        saved = validate_local(root, item) if graph is None else graph['intents'][item['operation_id']]
        if saved is None or saved['phase'] not in ('publishing', 'published', 'complete'):
            continue
        # A successor's pending cleanup still blocks its own operation. Its
        # catalog can nevertheless prove an older operation's publication;
        # otherwise that older claim would prevent the explicit cleanup.
        saved_receipt = (_read(root, _receipt_path(item), optional=True) if graph is None
                         else graph['local_bytes'][_receipt_path(item)])
        if saved_receipt != projection.serialized(saved['receipt']):
            continue
        publications.append((saved['catalog_after_digest'], _digest(_decode(saved['publication_base']))))
    while required not in observed:
        expanded = observed | {before for after, before in publications if after in observed}
        if expanded == observed:
            return False
        observed = expanded
    try:
        if historical:
            records._publication_history(root, catalog_raw=current,
                receipt_ref=projection.reference(_receipt_path(envelope), receipt_raw))
        else:
            records.published_bundle(root, catalog_raw=current,
                scope_ids=envelope['frozen']['scope_ids'], task_join=_task_join(root))
    except codec.CodecError:
        # Missing or damaged formal evidence proves no terminal. Current
        # consumption also retains its independent freshness requirement.
        return False
    _require(_read(root, records.CATALOG_PATH) == current,
             'same catalog throughout terminal proof', records.CATALOG_PATH, codec.ReasonCode.INPUT_STALE)
    return True


def terminal_valid(root, envelope, intent=None, *, graph=None):
    """Prove completed publication history, independently of current consumption."""
    intent = validate_local(root, envelope) if intent is None else intent
    return (intent is not None and intent['phase'] == 'complete'
        and _read(root, _paths(envelope['operation_id'])[1], optional=True) is None
        and _publication_proven(root, envelope, intent, graph=graph, historical=True))


def _result(envelope, intent, *, published=False, noop=False):
    return {'operation_id': envelope['operation_id'], 'state': intent['phase'],
        'scope_ids': envelope['frozen']['scope_ids'], 'frozen_digest': envelope['frozen_digest'],
        'resume_ref': _paths(envelope['operation_id'])[0], 'published': published, 'noop': noop,
        'formal_adoption': published, 'diagnostics': [], **FLAGS}


@contextmanager
def _original_activity(root, envelope):
    """Keep unfinished authority stable against original managed producers.

    Reuse the native activity/coordinator owners in their existing order. This
    acquires no new mutex and does not execute a verifier or dispatch work.
    """
    if envelope['schema_version'] == journal.COMPENSATION_SCHEMA:
        yield
        return
    from _b_route_planning_runtime import run_location
    from _mvg_capability_recovery import operation_lock
    from _mvg_capability_checkpoint import coordinator_lock
    material = envelope['frozen']['request']['material']
    if 'origin_profile' in material:
        from _b_route_qualified_origin import activity
        with activity(material['origin_profile']):
            yield
        return
    run = run_location(root, material['planner'], material['run_id'])
    state = codec.strict_json_loads(_read(root, (run / 'run.json').relative_to(root).as_posix()))
    store = root / 'logs/ci/mvg-recovery'
    _require(type(state.get('recovery', {}).get('store')) is str
             and Path(state['recovery']['store']).resolve() == store.resolve(), 'original local recovery owner', material['run_id'])
    with operation_lock(root, state), coordinator_lock(run):
        yield


def _step(root, envelope, intent, stage):
    if intent['phase'] == 'complete' and terminal_valid(root, envelope, intent):
        current = _read(root, records.CATALOG_PATH)
        import _b_route_adoption as adoption
        tasks = adoption.Snapshot(root)
        joined = adoption._task_context(tasks)
        records.published_bundle(root, catalog_raw=current,
            scope_ids=envelope['frozen']['scope_ids'], task_join=joined)
        tasks.verify()
        _require(_read(root, records.CATALOG_PATH) == current,
                 'same catalog throughout current terminal no-op', records.CATALOG_PATH,
                 codec.ReasonCode.INPUT_STALE)
        return _result(envelope, intent, published=True, noop=True)
    if intent['phase'] == 'complete':
        _require(stage == 'publish', 'explicit publish to finish pending cleanup', 'pending terminal cleanup', codec.ReasonCode.PENDING)
    if stage == 'publish' and _publication_proven(root, envelope, intent):
        _verify_observations(root, envelope, intent, published=True)
        for target in envelope['frozen']['targets']:
            _require(journal.classify_frozen_target(root, target)['state'] == 'after',
                     'actual published after targets before cleanup', target['path'])
        if PHASES.index(intent['phase']) < PHASES.index('published'):
            intent = _save(root, intent, 'published')
        _checkpoint('published_durable')
        if intent['phase'] != 'complete':
            intent = _save(root, intent, 'complete')
        _checkpoint('before_pending_cleanup')
        _cleanup_marker(root, envelope)
        _require(terminal_valid(root, envelope), 'complete published terminal proof', envelope['operation_id'])
        return _result(envelope, intent, published=True)
    _verify_observations(root, envelope, intent)
    if stage == 'apply':
        _require(intent['phase'] in ('intent', 'applied'), 'unpublished apply lifecycle', intent['phase'])
        for index, target in enumerate(envelope['frozen']['targets']):
            _verify_observations(root, envelope, intent)
            if journal.classify_frozen_target(root, target)['state'] == 'before':
                _checkpoint('before_target:' + str(index))
                # Recheck after the fault seam and directly before the write.
                _verify_observations(root, envelope, intent)
                if journal.classify_frozen_target(root, target)['state'] == 'before':
                    _write(root, target['path'], projection.serialized(target['after_payload']))
                _checkpoint('after_target:' + str(index))
        intent = _save(root, intent, 'applied')
        _checkpoint('applied_durable')
        return _result(envelope, intent)
    _require(intent['phase'] in ('applied', 'verified', 'publishing', 'published', 'complete'),
             'all targets applied before verification/publication', intent['phase'], codec.ReasonCode.UNPUBLISHED)
    for target in envelope['frozen']['targets']:
        _require(journal.classify_frozen_target(root, target)['state'] == 'after', 'all exact after images', target['path'])
    candidates = _candidates(root, envelope)
    current_catalog = _read(root, records.CATALOG_PATH, optional=True)
    already_published = intent['catalog_after'] is not None and current_catalog == _decode(intent['catalog_after'])
    publication_base = _decode(intent['publication_base']) if already_published else current_catalog
    if publication_base is not None:
        candidates[records.CATALOG_PATH] = publication_base
    catalog = projection.catalog_for_receipt(current_catalog=publication_base,
        receipt=intent['receipt'], candidates=candidates, task_join=_task_join(root), root=root, frozen=envelope['frozen'])
    catalog_raw = projection.serialized(catalog)
    if intent['catalog_after'] is not None and _decode(intent['catalog_after']) != catalog_raw:
        _require(not already_published and PHASES.index(intent['phase']) <= PHASES.index('publishing'),
                 'never replace an already-published intent', envelope['operation_id'])
        history = [*intent['catalog_attempts'], {'base': intent['publication_base'], 'after': intent['catalog_after']}]
        intent = _save(root, intent, publication_base=_encode(publication_base),
                       catalog_after=_encode(catalog_raw), catalog_attempts=history)
    receipt_raw = projection.serialized(intent['receipt'])
    receipt_before = _read(root, _receipt_path(envelope), optional=True)
    _require(receipt_before in (None, receipt_raw), 'immutable receipt path', _receipt_path(envelope))
    if receipt_before is None:
        _verify_observations(root, envelope, intent)
        _write(root, _receipt_path(envelope), receipt_raw)
    _checkpoint('receipt_durable')
    if intent['phase'] in ('applied', 'verified'):
        intent = _save(root, intent, 'verified', publication_base=_encode(publication_base), catalog_after=_encode(catalog_raw))
    _checkpoint('verified_durable')
    if stage == 'verify':
        return _result(envelope, intent)
    _require(stage == 'publish', 'known commit stage', stage)
    _verify_observations(root, envelope, intent)
    actual = _read(root, records.CATALOG_PATH, optional=True)
    _require(actual in (publication_base, catalog_raw), 'publication snapshot or exact owned catalog image', records.CATALOG_PATH)
    if intent['phase'] == 'verified':
        intent = _save(root, intent, 'publishing')
    _checkpoint('catalog_intent_durable')
    if actual != catalog_raw:
        _verify_observations(root, envelope, intent)
        _require(_read(root, records.CATALOG_PATH, optional=True) == publication_base,
                 'unchanged catalog at publication boundary', records.CATALOG_PATH)
        _write(root, records.CATALOG_PATH, catalog_raw)
    _checkpoint('catalog_replaced')
    records.published_bundle(root, catalog_raw=catalog_raw, task_join=_task_join(root))
    _require(_read(root, records.CATALOG_PATH) == catalog_raw, 'same catalog after formal chain verification', records.CATALOG_PATH)
    if PHASES.index(intent['phase']) < PHASES.index('published'):
        intent = _save(root, intent, 'published')
    _checkpoint('published_durable')
    intent = _save(root, intent, 'complete')
    _checkpoint('before_pending_cleanup')
    _cleanup_marker(root, envelope)
    _require(terminal_valid(root, envelope), 'complete published terminal proof', envelope['operation_id'])
    return _result(envelope, intent, published=True)


def execute(root, *, operation_id, stage):
    _require(stage in ('apply', 'verify', 'publish'), 'apply|verify|publish', stage, codec.ReasonCode.INVALID_ARGUMENT)
    root = Path(root).absolute()
    boundary_token = _BOUNDARY.set(None)
    try:
        graph = journal.operation_state_graph(root)
        if operation_id in graph['resolved_by']:
            return _resolved_result(operation_id, graph['resolved_by'][operation_id])
        envelope = journal.read_operation(root, operation_id=operation_id)
        _require(envelope['state'] == 'reserved', 'original reserved operation', operation_id)
        intent = validate_local(root, envelope)
        if intent is None:
            _require(stage == 'apply', 'apply creates initial durable intent', stage, codec.ReasonCode.UNPUBLISHED)
            import _b_route_adoption as adoption
            with adoption.commit_context(root, operation_id=operation_id) as (snapshot, checked):
                _require(checked == envelope, 'same reserved operation', operation_id)
                with business_guard(root, envelope['frozen']['scope_ids'], operation_id=operation_id,
                        compensation_frozen=envelope['frozen'] if envelope['schema_version'] == journal.COMPENSATION_SCHEMA else None):
                    intent = _initial(root, envelope, snapshot)
                    return _step(root, envelope, intent, stage)
        unfinished = intent['phase'] != 'complete' or _read(root, _paths(operation_id)[1], optional=True) is not None
        if unfinished:
            import _b_route_adoption_review as review
            review.verify_saved(root, envelope['frozen']['request'])
        with _original_activity(root, envelope) if unfinished else nullcontext():
            with business_guard(root, envelope['frozen']['scope_ids'], operation_id=operation_id,
                    compensation_frozen=envelope['frozen'] if envelope['schema_version'] == journal.COMPENSATION_SCHEMA else None):
                _verify_local(root, envelope, intent)
                return _step(root, envelope, intent, stage)
    except codec.CodecError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        _fail('complete safe commit step; retained evidence', type(error).__name__,
              resume=_paths(operation_id)[0])
    finally:
        _BOUNDARY.reset(boundary_token)


def _verify_local(root, envelope, intent):
    _require(journal.read_operation(root, operation_id=envelope['operation_id']) == envelope
             and validate_local(root, envelope) == intent, 'unchanged operation and intent under lease', envelope['operation_id'])


def _cleanup_marker(root, envelope):
    marker = journal._operation_path(root, _paths(envelope['operation_id'])[1])
    expected = projection.serialized({'schema_version': SCHEMA + '.pending',
        'operation_id': envelope['operation_id'], 'frozen_digest': envelope['frozen_digest']})
    def check():
        boundary = _BOUNDARY.get()
        if boundary is not None:
            boundary()
        _require(not marker.exists() or marker.read_bytes() == expected,
                 'exact original marker before cleanup', _paths(envelope['operation_id'])[1])
    with writer_boundary(root, recheck=check):
        if marker.exists():
            marker.unlink()


def inspect_recovery(root, *, operation_id):
    """Read physical facts without creating locks, repairing logs or granting apply.

    Full saved proof replay runs before short writer leases. Initial admission
    remains execute/apply's responsibility; inspection never fabricates one.
    """
    root = Path(root).absolute()
    try:
        from _b_route_operation_scope import legacy_recovery_routes
        import _b_route_adoption_review as review
        routes = legacy_recovery_routes(root)
        graph = journal.operation_state_graph(root)
        if operation_id in graph['resolved_by']:
            return {**_resolved_result(operation_id, graph['resolved_by'][operation_id]),
                'physical_state': 'resolved_by_compensation', 'next_stage': None,
                'legacy_routes': routes, 'target_states': []}
        envelope = journal.read_operation(root, operation_id=operation_id)
        intent = validate_local(root, envelope)
        catalog = _read(root, records.CATALOG_PATH, optional=True)
        if terminal_valid(root, envelope, intent):
            physical, next_stage, targets = 'committed_noop', None, []
        else:
            _checkpoint('recovery_before_review')
            if intent is not None:
                review.verify_saved(root, envelope['frozen']['request'])
                published = _publication_proven(root, envelope, intent)
                _verify_observations(root, envelope, intent, published=published)
                receipt = _read(root, _receipt_path(envelope), optional=True)
                _require(receipt in (None, projection.serialized(intent['receipt'])),
                         'unchanged immutable recovery receipt', _receipt_path(envelope))
            else:
                published = False
                for ref in envelope['frozen']['authority_refs']:
                    _require(_digest(_read(root, ref['path'])) == ref['raw_digest'],
                             'unchanged original authority before initial admission', ref['path'], codec.ReasonCode.INPUT_STALE)
            targets = [journal.classify_frozen_target(root, row) for row in envelope['frozen']['targets']]
            before = sum(row['state'] == 'before' for row in targets)
            if intent is None:
                _require(before == len(targets), 'original before targets without durable intent', operation_id)
                physical, next_stage = 'untouched', 'apply'
            elif published:
                _require(before == 0, 'all published targets still after', operation_id)
                physical, next_stage = 'published_pending_cleanup', 'publish'
            else:
                physical = 'partial' if 0 < before < len(targets) else ('untouched' if before else 'targets_after_unpublished')
                if intent['phase'] == 'intent' or before:
                    _require(intent['phase'] in ('intent', 'applied'),
                             'before target only in unapplied lifecycle', intent['phase'])
                    next_stage = 'apply'
                elif intent['phase'] == 'applied':
                    next_stage = 'verify'
                else:
                    next_stage = 'publish'
            if envelope['state'] != 'reserved':
                next_stage = 'reserve'
        _checkpoint('recovery_inspected')
        if intent is not None and physical != 'committed_noop':
            _verify_observations(root, envelope, intent,
                                 published=physical == 'published_pending_cleanup')
        _require(journal.read_operation(root, operation_id=operation_id) == envelope
                 and validate_local(root, envelope) == intent
                 and _read(root, records.CATALOG_PATH, optional=True) == catalog
                 and legacy_recovery_routes(root) == routes,
                 'same operation/intent/catalog throughout inspection', operation_id, codec.ReasonCode.INPUT_STALE)
        return {'status': 'inspected', 'operation_id': operation_id,
            'state': None if intent is None else intent['phase'],
            'physical_state': physical, 'next_stage': next_stage, 'target_states': targets,
            'scope_ids': envelope['frozen']['scope_ids'], 'frozen_digest': envelope['frozen_digest'],
            'legacy_routes': routes, 'formal_adoption': False, 'diagnostics': [],
            'resume_ref': _paths(operation_id)[0] if intent is not None else journal._operation_ref(operation_id),
            'eligibility': 'facts only; execute rechecks original admission and leases', **FLAGS}
    except codec.CodecError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        _fail('complete unchanged recovery evidence', type(error).__name__, resume=_paths(operation_id)[0])


def recover(root, *, operation_id):
    """Advance only observed missing steps through the sole commit executor."""
    try:
        for _ in range(4):
            facts = inspect_recovery(root, operation_id=operation_id)
            if facts['physical_state'] == 'resolved_by_compensation':
                return facts
            if facts['legacy_routes']:
                _fail('resolve original legacy apply before B recovery', facts['legacy_routes'],
                      codec.ReasonCode.PENDING, resume=facts['legacy_routes'][0]['resume_ref'])
            if facts['physical_state'] == 'committed_noop':
                return execute(root, operation_id=operation_id, stage='publish')
            stage = facts['next_stage']
            _require(stage in ('apply', 'verify', 'publish'), 'original reserved operation before recovery',
                     stage, codec.ReasonCode.UNPUBLISHED)
            result = execute(root, operation_id=operation_id, stage=stage)
            if result['published']:
                return result
            _checkpoint('recovery_between_steps')
        _fail('bounded legal recovery stages', 'state did not converge', resume=_paths(operation_id)[0])
    except codec.CodecError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        _fail('complete safe recovery; original evidence retained', type(error).__name__, resume=_paths(operation_id)[0])


def read_committed(root, *, scope_ids=None):
    """Protected formal consumption; local proof logs are not clone prerequisites.

    Coordination may initialize ordinary local lock metadata. Formal files are
    never written, repaired or classified from optional trace existence.
    """
    root = Path(root).absolute()
    try:
        before = _read(root, records.CATALOG_PATH)
        initial = records.published_bundle(root, catalog_raw=before, scope_ids=scope_ids, task_join=_task_join(root), _protection=True)
        protection_scopes = initial.pop('_protection_scope_ids')
        with business_guard(root, protection_scopes):
            _require(_read(root, records.CATALOG_PATH) == before, 'same catalog under protection', records.CATALOG_PATH,
                     codec.ReasonCode.INPUT_STALE)
            import _b_route_adoption as adoption
            tasks = adoption.Snapshot(root)
            joined = adoption._task_context(tasks)
            result = records.published_bundle(root, catalog_raw=before, scope_ids=scope_ids, task_join=joined, _protection=True)
            _require(result.pop('_protection_scope_ids') == protection_scopes,
                     'same validated selected business resources under protection', records.CATALOG_PATH,
                     codec.ReasonCode.INPUT_STALE)
            _checkpoint('reader_before_catalog_close')
            tasks.verify()
            _require(_read(root, records.CATALOG_PATH) == before, 'same catalog before and after relevant read',
                     records.CATALOG_PATH, codec.ReasonCode.INPUT_STALE)
            return {'status': 'committed', 'formal_adoption': True, **result, **FLAGS}
    except codec.CodecError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        _fail('complete readable committed chain', type(error).__name__, codec.ReasonCode.UNPUBLISHED)


def _resolved_result(operation_id, successor):
    return {'operation_id': operation_id, 'state': 'resolved_by', 'resolved_by': successor,
        'status': 'resolved', 'published': False, 'noop': True, 'formal_adoption': False,
        'resume_ref': _paths(successor)[0], 'diagnostics': [], **FLAGS}
