"""One shared apply/verify/catalog-last owner. No dispatch or automatic recovery."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import base64
import os
from pathlib import Path
import uuid

import _b_route_codec as codec
import _b_route_records as records
import _b_route_commit_projection as projection
import _planning_apply_journal as journal
from _b_route_operation_scope import scope_guard

SCHEMA = 'newrouge.b-route-commit-intent.v1'
PHASES = ('intent', 'applied', 'verified', 'publishing', 'published', 'complete')
SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'docs/planning/b-route/schemas/commit-intent.schema.json'
FLAGS = {'readiness': False, 'runtime_verified': False, 'default_b_enabled': False}


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
        resolved_definitions=value['receipt']['resolved_definitions'])
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
    """Flush complete bytes before one atomic replacement; never repair others."""
    path = journal._operation_path(root, relative)
    journal._operation_no_reparse(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    journal._operation_no_reparse(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.commit-tmp')
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
    receipt = projection.receipt_for_frozen(operation_id=envelope['operation_id'], frozen=frozen, resolved_definitions=[])
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
        resolved_definitions=[resolved[key] for key in sorted(resolved)])


def _observations(root, snapshot):
    files = {str(root / name): value for name, value in snapshot.files.items()}
    directories = {}
    if snapshot.native_capture is not None:
        for name, value in snapshot.native_capture['files'].items():
            _require(name not in files or files[name] == value, 'one observed source image', name)
            files[name] = value
        directories = deepcopy(snapshot.native_capture['directories'])
    if hasattr(snapshot, 'origin_capsule'):
        capsule = snapshot.origin_capsule
        for name, expected in {**capsule['native_capture']['files'], **capsule['qualification_files']}.items():
            _require(name not in files or files[name] == expected, 'one original origin image', name)
            files[name] = expected
        directories.update(deepcopy(capsule['native_capture']['directories']))
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


def _verify_observations(root, envelope, intent):
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
    dual = subject.get('schema_version') in {'newrouge.b-route-adoption-review-subject.v2', 'newrouge.b-route-adoption-review-subject.v3'}
    dependencies = subject['target_dependencies'] if dual else subject['prepared']['inputs']['dependencies']['files']
    required_files.update({str(root / name): expected for name, expected in dependencies.items()})
    if dual:
        from _b_route_qualified_origin import verify_capsule
        capsule = subject['origin_capsule']
        verify_capsule(root, capsule)
        required_files.update(capsule['qualification_files'])
        required_files.update(capsule['native_capture']['files'])
        _require(all(intent['directories'].get(name) == members for name, members in
            capsule['native_capture']['directories'].items()), 'complete original origin directory closure', envelope['operation_id'])
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
    owned = _owned_paths(root, envelope)
    current_catalog = _read(root, records.CATALOG_PATH, optional=True)
    if current_catalog is not None and current_catalog not in (
            _decode(intent['catalog_before']), _decode(intent['catalog_after'])):
        _require(_catalog_frame(root, envelope, current_catalog, intent['before_files']) == intent['catalog_frame'],
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
    for target in envelope['frozen']['targets']:
        journal.classify_frozen_target(root, target)
    for ref in envelope['frozen']['authority_refs']:
        if ref['path'] == records.CATALOG_PATH:
            continue
        name = str(root / ref['path'])
        actual = _digest(_read(root, ref['path']))
        _require(actual in permitted.get(name, {ref['raw_digest']}), 'original authority binding', ref['path'], codec.ReasonCode.INPUT_STALE)
    current = _read(root, records.CATALOG_PATH, optional=True)
    if intent['catalog_after'] is None or current != _decode(intent['catalog_after']):
        _require(_catalog_frame(root, envelope, current, intent['before_files']) == intent['catalog_frame'],
                 'same affected catalog semantics; unrelated publication may advance', records.CATALOG_PATH,
                 codec.ReasonCode.INPUT_STALE)


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
        receipt=receipt, candidates=candidates, task_join=_task_join(root), root=root)
    files, directories, trees = _observations(root, snapshot)
    import _b_route_adoption_review as review
    value = _seal({'schema_version': SCHEMA, 'operation_id': envelope['operation_id'],
        'frozen_digest': envelope['frozen_digest'], 'policy_identity': review.policy_identity(),
        'phase': 'intent', 'before_files': before, 'files': files, 'directories': directories, 'trees': trees,
        'receipt': receipt, 'catalog_before': before[records.CATALOG_PATH], 'catalog_after': None,
        'origins_before': origins_before,
        'publication_base': before[records.CATALOG_PATH], 'catalog_attempts': [], 'catalog_after_digest': None,
        'catalog_frame': _catalog_frame(root, envelope, _decode(before[records.CATALOG_PATH]), before)})
    _verify_observations(root, envelope, value)
    marker = {'schema_version': SCHEMA + '.pending', 'operation_id': envelope['operation_id'],
              'frozen_digest': envelope['frozen_digest']}
    _write(root, _paths(envelope['operation_id'])[1], projection.serialized(marker))
    _checkpoint('pending_durable')
    value = _save(root, value)
    _checkpoint('intent_durable')
    return value


def terminal_valid(root, envelope, intent=None):
    """Prove explicit terminal state and actual formal chain, never disappearance."""
    intent = validate_local(root, envelope) if intent is None else intent
    if intent is None or intent['phase'] != 'complete':
        return False
    if _read(root, _paths(envelope['operation_id'])[1], optional=True) is not None:
        return False
    _require(_read(root, _receipt_path(envelope)) == projection.serialized(intent['receipt']),
             'unchanged published receipt', envelope['operation_id'])
    current = _read(root, records.CATALOG_PATH)
    records.published_bundle(root, catalog_raw=current,
        scope_ids=envelope['frozen']['scope_ids'], task_join=_task_join(root))
    # A complete phase plus an unrelated valid current chain cannot prove this
    # operation was ever published. Follow only saved publication
    # images back from the actual catalog. This also retains terminal history
    # after later legitimate revisions replace this operation's scope heads.
    required = intent['catalog_after_digest']
    observed = {_digest(current)}
    publications = []
    for item in journal.operation_inventory(root):
        saved = validate_local(root, item)
        if saved is None or saved['phase'] not in ('publishing', 'published', 'complete'):
            continue
        # A successor's pending cleanup still blocks its own operation. Its
        # catalog can nevertheless prove an older operation's publication;
        # otherwise that older claim would prevent the explicit cleanup.
        if _read(root, _receipt_path(item), optional=True) != projection.serialized(saved['receipt']):
            continue
        publications.append((saved['catalog_after_digest'], _digest(_decode(saved['publication_base']))))
    while required not in observed:
        expanded = observed | {before for after, before in publications if after in observed}
        if expanded == observed:
            return False
        observed = expanded
    _require(_read(root, records.CATALOG_PATH) == current,
             'same catalog throughout terminal proof', records.CATALOG_PATH, codec.ReasonCode.INPUT_STALE)
    return True


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
        return _result(envelope, intent, published=True, noop=True)
    if intent['phase'] == 'complete':
        _require(stage == 'publish', 'explicit publish to finish pending cleanup', 'pending terminal cleanup', codec.ReasonCode.PENDING)
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
        receipt=intent['receipt'], candidates=candidates, task_join=_task_join(root), root=root)
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
    marker = journal._operation_path(root, _paths(envelope['operation_id'])[1])
    marker.unlink()  # A cleanup failure retains the marker and continues blocking readers.
    _require(terminal_valid(root, envelope), 'complete published terminal proof', envelope['operation_id'])
    return _result(envelope, intent, published=True)


def execute(root, *, operation_id, stage):
    _require(stage in ('apply', 'verify', 'publish'), 'apply|verify|publish', stage, codec.ReasonCode.INVALID_ARGUMENT)
    root = Path(root).absolute()
    try:
        envelope = journal.read_operation(root, operation_id=operation_id)
        _require(envelope['state'] == 'reserved', 'original reserved operation', operation_id)
        intent = validate_local(root, envelope)
        if intent is None:
            _require(stage == 'apply', 'apply creates initial durable intent', stage, codec.ReasonCode.UNPUBLISHED)
            import _b_route_adoption as adoption
            with adoption.commit_context(root, operation_id=operation_id) as (snapshot, checked):
                _require(checked == envelope, 'same reserved operation', operation_id)
                with scope_guard(root, envelope['frozen']['scope_ids'], operation_id=operation_id,
                                 prepare_under_lease=lambda: _initial(root, envelope, snapshot)) as intent:
                    return _step(root, envelope, intent, stage)
        unfinished = intent['phase'] != 'complete' or _read(root, _paths(operation_id)[1], optional=True) is not None
        if unfinished:
            import _b_route_adoption_review as review
            review.verify_saved(root, envelope['frozen']['request'])
        with _original_activity(root, envelope) if unfinished else nullcontext():
            with scope_guard(root, envelope['frozen']['scope_ids'], operation_id=operation_id,
                             prepare_under_lease=lambda: _verify_local(root, envelope, intent)):
                return _step(root, envelope, intent, stage)
    except codec.CodecError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        _fail('complete safe commit step; retained evidence', type(error).__name__,
              resume=_paths(operation_id)[0])


def _verify_local(root, envelope, intent):
    _require(journal.read_operation(root, operation_id=envelope['operation_id']) == envelope
             and validate_local(root, envelope) == intent, 'unchanged operation and intent under lease', envelope['operation_id'])


def read_committed(root, *, scope_ids=None):
    """Protected formal consumption; local proof logs are not clone prerequisites.

    Coordination may initialize ordinary local lock metadata. Formal files are
    never written, repaired or classified from optional trace existence.
    """
    root = Path(root).absolute()
    try:
        before = _read(root, records.CATALOG_PATH)
        initial = records.published_bundle(root, catalog_raw=before, scope_ids=scope_ids, task_join=_task_join(root))
        with scope_guard(root, initial['scope_ids'], prepare_under_lease=lambda: None):
            _require(_read(root, records.CATALOG_PATH) == before, 'same catalog under protection', records.CATALOG_PATH,
                     codec.ReasonCode.INPUT_STALE)
            result = records.published_bundle(root, catalog_raw=before, scope_ids=scope_ids, task_join=_task_join(root))
            _checkpoint('reader_before_catalog_close')
            _require(_read(root, records.CATALOG_PATH) == before, 'same catalog before and after relevant read',
                     records.CATALOG_PATH, codec.ReasonCode.INPUT_STALE)
            return {'status': 'committed', 'formal_adoption': True, **result, **FLAGS}
    except codec.CodecError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        _fail('complete readable committed chain', type(error).__name__, codec.ReasonCode.UNPUBLISHED)
