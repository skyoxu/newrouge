"""Reviewed existing-semantics compensation producer, using the shared commit.

No native candidate is fabricated and no model is dispatched here. A selection
must come from a receipt-proven formal revision; changing planning meaning
beyond those bytes belongs to the original adoption entry point.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import base64

import _b_route_codec as codec
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_commit_projection as projection
import _b_route_records as records
import _planning_apply_journal as journal
import _b_route_compensation_review_profiles as profiles

REQUEST = journal.COMPENSATION_REQUEST
SUBJECT = 'newrouge.b-route-compensation-review-subject.v2'
SEMANTICS = review.SHARED
FLAGS = {**adoption.FLAGS, 'default_b_enabled': False}


def require(condition, expected, actual, code=codec.ReasonCode.CONFLICT):
    adoption.require(condition, expected, actual, code)


def is_request(request):
    return request.get('schema_version') == REQUEST


def relation_for(operation):
    return {'operation_id': operation['operation_id'], 'frozen_digest': operation['frozen_digest'],
        'request_raw_digest': operation['request_raw_digest'],
        'effects_digest': codec.canonical_digest(operation['frozen']['targets'])}


def validate_relation(frozen, inventory):
    """Check exact original claim and full old scope, without active recursion."""
    journal._operation_schema(frozen, 'Frozen')
    request = frozen['request']
    require(is_request(request) and frozen['producer'] == 'compensation', 'explicit v2 producer', request)
    relation = request['compensates']
    require(request['operation_id'] != relation['operation_id'], 'new compensation ID', request['operation_id'])
    original = next((row for row in inventory if row['operation_id'] == relation['operation_id']), None)
    require(original is not None and relation == relation_for(original),
            'exact original ID/raw request/frozen/effects', relation, codec.ReasonCode.INPUT_STALE)
    require(frozen['compensation']['relation'] == relation
            and frozen['compensation']['old_scope_ids'] == original['frozen']['scope_ids']
            and set(original['frozen']['scope_ids']) <= set(frozen['scope_ids'])
            and set(frozen['compensation']['current_scope_ids']) <= set(frozen['scope_ids']),
            'reviewed complete old/current/new scope union', request['operation_id'])
    return original


def _authorized_claim(root, operation_id, frozen):
    """Only the independently reviewed exact relation may join one old claim."""
    require(operation_id == frozen['request']['operation_id'], 'same compensation owner', operation_id)
    inventory = journal.operation_inventory(root)
    original = validate_relation(frozen, inventory)
    subject, support = review.verify_saved(root, frozen['request'])
    expected = deepcopy(subject['preview'])
    expected['request'] = deepcopy(frozen['request'])
    expected['authority_refs'] = sorted([*expected['authority_refs'], *support], key=lambda row: row['path'])
    require(codec.canonical_digest(expected) == codec.canonical_digest(frozen),
            'exact reviewed compensation, support and current-before', operation_id, codec.ReasonCode.INPUT_STALE)
    for row in inventory:
        if row['schema_version'] == journal.COMPENSATION_SCHEMA and row['operation_id'] != operation_id:
            require(row['frozen']['request']['compensates']['operation_id'] != original['operation_id'],
                    'one durable successor for the original claim', original['operation_id'])
    return original, subject, inventory


def authorize_claim(root, operation_id, frozen):
    """Preserve the original direct-claim API; no global terminal is changed."""
    return _authorized_claim(root, operation_id, frozen)[0]['operation_id']


def authorize_pending_claims(root, operation_id, frozen, *, pending_operations=()):
    """Scoped recovery permission, never a terminal or inventory rewrite.

    An exact owned after-image can temporarily make the old catalog unreadable.
    Only this reviewed operation's intact before-view and real publication chain
    can retain its published ancestor/resolved claims while it finishes.
    """
    original, subject, inventory = _authorized_claim(root, operation_id, frozen)
    allowed = {original['operation_id']}
    if all(type(row) is dict and row.get('operation_id') in (operation_id, original['operation_id'])
           for row in pending_operations):
        return frozenset(allowed)
    import _b_route_commit as commit
    current = next((row for row in inventory if row['operation_id'] == operation_id), None)
    if current is None:
        return frozenset(allowed)
    require(current['frozen'] == frozen, 'same persisted reviewed recovery owner', operation_id,
            codec.ReasonCode.INPUT_STALE)
    intent = commit.validate_local(root, current)
    if intent is None:
        return frozenset(allowed)
    # Read-only, under complete business scopes and outside metadata/WRITER.
    # Unknown owned bytes, source drift and unrelated catalog changes still fail.
    verify_observations(root, current, intent, facts=commit._VerifiedFacts())
    catalog_raw = commit._decode(intent['catalog_before'])
    require(catalog_raw is not None
            and codec.raw_digest(catalog_raw) == frozen['compensation']['current_catalog_digest']
            and base64.b64decode(subject['current_files'][records.CATALOG_PATH], validate=True) == catalog_raw,
            'exact independently reviewed catalog-before anchor', operation_id, codec.ReasonCode.INPUT_STALE)
    candidates = {records.CATALOG_PATH: catalog_raw}
    for target in frozen['targets']:
        before = commit._decode(intent['before_files'][target['path']])
        if before is not None:
            require(codec.raw_digest(before) == target['before_raw_digest']
                    and base64.b64decode(subject['current_files'][target['path']], validate=True) == before,
                    'reviewed before image only for this exact owned target', target['path'],
                    codec.ReasonCode.INPUT_STALE)
            candidates[target['path']] = before
    # This is a read-only historical view, not publication of these bytes and
    # not permission to accept an arbitrary unreadable current catalog.
    bundle = records._PublishedBundle(candidates, root, records.CATALOG_PATH, None,
        adoption._task_context(adoption.Snapshot(root)))
    catalog = bundle.load(records.CATALOG_PATH)
    bundle.select(catalog, frozen['compensation']['current_scope_ids'])
    bundle.expand()
    bundle.relationships(catalog)
    bundle.bytes.stable()
    require(bundle.selected_scopes == frozen['compensation']['current_scope_ids']
            and codec.canonical_digest(bundle.semantic_frame) == frozen['compensation']['current_frame_digest'],
            'complete same reviewed formal scope/frame', operation_id, codec.ReasonCode.INPUT_STALE)
    intents = {row['operation_id']: commit.validate_local(root, row) for row in inventory}
    publications = []
    for row in inventory:
        saved = intents[row['operation_id']]
        if saved is None or saved['phase'] not in ('publishing', 'published', 'complete'):
            continue
        receipt = commit._read(root, commit._receipt_path(row), optional=True)
        if receipt == projection.serialized(saved['receipt']):
            publications.append((saved['catalog_after_digest'],
                                 commit._digest(commit._decode(saved['publication_base']))))
    def published_ancestor(row):
        saved = intents[row['operation_id']]
        if (saved is None or saved['phase'] != 'complete'
                or commit._read(root, commit._paths(row['operation_id'])[1], optional=True) is not None):
            return False
        require(commit._read(root, commit._receipt_path(row), optional=True)
                == projection.serialized(saved['receipt']),
                'actual immutable published ancestor receipt', row['operation_id'])
        observed = {codec.raw_digest(catalog_raw)}
        while saved['catalog_after_digest'] not in observed:
            expanded = observed | {before for after, before in publications if after in observed}
            if expanded == observed:
                return False
            observed = expanded
        return True
    current = original
    seen = set()
    while True:
        identity = current['operation_id']
        require(identity not in seen, 'acyclic exact compensation ancestry', identity)
        seen.add(identity)
        require(set(current['frozen']['scope_ids']) <= set(frozen['scope_ids']),
                'ancestor scope wholly inside reviewed recovery scope', identity)
        published = published_ancestor(current)
        if published:
            allowed.add(identity)
        if current['schema_version'] != journal.COMPENSATION_SCHEMA:
            break
        parent = validate_relation(current['frozen'], inventory)
        if published:
            checked, ancestor_subject, again = _authorized_claim(root, identity, current['frozen'])
            require(again == inventory and checked == parent
                    and ancestor_subject['original_operation'] == parent
                    and ancestor_subject['original_effects'] == parent['frozen']['targets'],
                    'published ancestor resolved this exact reviewed original claim', identity,
                    codec.ReasonCode.INPUT_STALE)
            allowed.add(parent['operation_id'])
        current = parent
    return frozenset(allowed)



def _unique_refs(rows):
    return sorted({codec.canonical_digest(row): row for row in rows}.values(), key=lambda row: row['path'])


def _original_review(snapshot, operation, *, profile=profiles.ORIGINAL):
    """Bind immutable original review bytes, without replaying stale authority.

    The new review is independent of both the original native producer and
    host review. Mutable original run/source freshness is not an exemption or
    a prerequisite for compensating the exact stale claim.
    """
    from _b_route_qualified_compensation_dispatch import for_operation
    if profile is profiles.PUBLISHED:
        import _b_route_published_compensation_review as qualified
    else:
        qualified=for_operation(operation)
    if qualified.selected(operation):
        return qualified.original_review(snapshot, operation)
    request = operation['frozen']['request']
    ref = request.get('host_review_ref')
    require(type(ref) is dict, 'original independently reviewed operation identity', operation['operation_id'])
    # Re-prove the saved version's original exact request/runtime evidence.
    # This does not re-admit stale native authority or call a model.
    review.verify_saved(snapshot.root, request)
    proof = snapshot.ref(ref)
    subject_path = review.location(operation['operation_id']) + '/subject.json'
    subject_raw = snapshot.read(subject_path)
    subject = codec.strict_json_loads(subject_raw)
    require(proof.get('operation_id') == operation['operation_id']
            and proof.get('subject_digest') == codec.canonical_digest(subject)
            and subject.get('operation_id') == operation['operation_id']
            and subject.get('request') == review.request_body(request),
            'complete original raw review subject and request', operation['operation_id'])
    for support in proof['files']:
        snapshot.ref(support)
    expected = deepcopy(subject['preview'])
    expected['request'] = request
    expected['authority_refs'] = sorted([*expected['authority_refs'], ref, *proof['files']], key=lambda row: row['path'])
    require(codec.canonical_digest(expected) == operation['frozen_digest'],
            'original reviewed frozen effects and authority identities', operation['operation_id'])
    qualified.consider_legacy_authorities(snapshot, subject)
    threads = set(subject['native_threads'])
    if type(proof.get('evidence')) is dict and type(proof['evidence'].get('thread_id')) is str:
        threads.add(proof['evidence']['thread_id'])
    return sorted(threads), list(subject['native_turns'])


def _formal(snapshot, bundle, ref):
    value = bundle.reference(ref)
    require(ref['path'] in bundle.records, 'actual formal reference', ref['path'])
    snapshot.read(ref['path'])
    return deepcopy(value)


def _proven_selection(bundle, ref):
    """An orphan matching a schema is not a previously published semantic source."""
    value = bundle.reference(ref)
    raw = bundle.bytes.read(ref['path'])
    proven = any(record['schema_version'] == 'newrouge.b-route-commit.v1' and any(
        row['path'] == ref['path'] and row['after_digest'] == codec.raw_digest(raw)
        and row['verification_mode'] == 'immutable_bytes' for row in record['targets'])
        for record in bundle.records.values())
    require(proven, 'selection sealed by the actual formal receipt chain; use adoption for new meaning', ref['path'])
    return deepcopy(value)


def _preserve_plan(current, selected, original):
    """Choose existing fields, preserving cumulative IDs and later edits."""
    def meaning(value):
        value = deepcopy(value)
        for child in records._walk(value):
            if child.get('owner_plan_id') == current['plan_id'] and 'owner_revision' in child:
                child['owner_revision'] = None
        return value
    for field in SEMANTICS:
        if meaning(current[field]) != meaning(selected[field]):
            require(original is not None and meaning(current[field]) == meaning(original[field]),
                    'later legitimate edits preserved; select current semantics or use adoption', field,
                    codec.ReasonCode.INPUT_STALE)
    for field, key in (('requirements', 'requirement_id'),):
        require({row[key] for row in current[field]} <= {row[key] for row in selected[field]},
                'cumulative Requirement IDs retained', field)
    for family in ('flows', 'commands', 'states'):
        require({row['id'] for row in current['definitions'][family]}
                <= {row['id'] for row in selected['definitions'][family]},
                'cumulative definition identities retained', family)
    for field in ('requirement_evidence', 'evidence_source_refs'):
        require(all(row in selected[field] for row in current[field]), 'cumulative evidence retained', field)


def build(root, request, *, allocations=None, review_profile=profiles.ORIGINAL):
    """Read actual current formal bytes and derive the whole preview and scope."""
    root = Path(root).absolute()
    journal.validate_operation_request(request)
    inventory = journal.operation_inventory(root)
    original = next((row for row in inventory if row['operation_id'] == request['compensates']['operation_id']), None)
    require(original is not None and relation_for(original) == request['compensates']
            and request['operation_id'] != original['operation_id'], 'new ID bound to exact original claim', request['compensates'])
    snapshot = adoption.Snapshot(root)
    snapshot.review_profile = review_profile
    snapshot.compensation_threads, snapshot.compensation_turns = _original_review(snapshot, original,profile=review_profile)
    task_join = adoption._task_context(snapshot)
    catalog_raw = snapshot.read(records.CATALOG_PATH)
    bundle = records._PublishedBundle({records.CATALOG_PATH: catalog_raw}, root, records.CATALOG_PATH, None, task_join)
    catalog = bundle.load(records.CATALOG_PATH)
    plan_id = original['frozen']['allocations']['plan_id']
    seeds = [head['scope_id'] for head in catalog['scope_heads']
             if any(ref['entity_id'] == plan_id for ref in head['plan_refs'] + head['binding_refs'])]
    require(seeds, 'existing formally published plan for compensation; use original adoption otherwise', plan_id)
    bundle.select(catalog, seeds)
    bundle.expand()
    bundle.relationships(catalog)
    bundle.bytes.stable()
    # Historical semantics need their own actual publication evidence, not
    # merely a schema-valid orphan or an old file referenced by a caller.
    graph = journal.operation_state_graph(root)
    for operation in graph['operations']:
        if operation['operation_id'] not in graph['terminals']:
            continue
        receipt_path = records.BASE + 'commits/' + operation['operation_id'] + '.json'
        raw = codec.read_reference_bytes(root, receipt_path)
        require(raw == projection.serialized(graph['intents'][operation['operation_id']]['receipt']),
                'actual immutable historical publication receipt', receipt_path)
        bundle.load(receipt_path)
    bundle.expand()
    snapshot.catalog = deepcopy(catalog)
    current_refs = _unique_refs([ref for head in bundle.semantic_frame['heads'] for ref in head['plan_refs']])
    binding_refs = _unique_refs([ref for head in bundle.semantic_frame['heads'] for ref in head['binding_refs']])
    current_plans = [ref for ref in current_refs if ref['entity_id'] == plan_id]
    current_bindings = [ref for ref in binding_refs if ref['entity_id'] == plan_id]
    require(len(current_plans) == 1 and len(current_bindings) <= 1, 'one current revision per affected plan/binding', plan_id)
    current_ref = current_plans[0]
    current = _formal(snapshot, bundle, current_ref)
    selected_ref = request['selection']['plan_ref']
    require(selected_ref['entity_id'] == plan_id and selected_ref['path'] in bundle.records,
            'same plan and actual current formal-chain selection', selected_ref['path'])
    selected = _proven_selection(bundle, selected_ref)
    # A new receipt must seal the inherited source/proof locators itself.
    # Read and pin their actual original bytes; do not copy a caller's digest
    # or waive candidate source validation because the plan was once published.
    for child in records._walk(selected):
        if set(child) == {'owner', 'ref', 'files'}:
            for pin in child['files']:
                data = snapshot.read(pin['path'])
                require(codec.raw_digest(data) == pin['raw_digest'],
                        'actual unchanged inherited formal source/proof bytes', pin['path'], codec.ReasonCode.INPUT_STALE)
    old_plan = next((row['after_payload'] for row in original['frozen']['targets']
                     if row['schema_version'] == adoption.PLAN), None)
    _preserve_plan(current, selected, old_plan)
    selected_binding_ref = request['selection']['binding_ref']
    require(bool(current_bindings) == (selected_binding_ref is not None),
            'retain all current B Task bindings and origins', selected_binding_ref)
    current_binding = selected_binding = None
    if current_bindings:
        current_binding = _formal(snapshot, bundle, current_bindings[0])
        require(selected_binding_ref['entity_id'] == plan_id and selected_binding_ref['path'] in bundle.records,
                'existing same-plan formal binding selection', selected_binding_ref)
        selected_binding = _proven_selection(bundle, selected_binding_ref)
        require({row['task_id'] for row in current_binding['task_mappings']}
                == {row['task_id'] for row in selected_binding['task_mappings']},
                'preserved current Task domain; use adoption for new Task handoff', selected_binding_ref['path'])
        # Status/Acceptance/history stay in the existing Task owner; mappings,
        # cumulative responsibilities and implementation obligations cannot drop.
        for field in ('task_mappings', 'implementation_objects', 'obligations', 'parts'):
            require(all(row in selected_binding[field] for row in current_binding[field]),
                    'retain every current B Task mapping/history/obligation', field)
        for field in set(current_binding) - {'binding_revision', 'plan_ref'}:
            if current_binding[field] != selected_binding[field]:
                old_binding = next((row['after_payload'] for row in original['frozen']['targets']
                                    if row['schema_version'] == adoption.BINDING), None)
                require(old_binding is not None and old_binding[field] == current_binding[field],
                        'preserve later binding edits', field, codec.ReasonCode.INPUT_STALE)
    # All observed formal records are exact byte sources, including historical
    # selection receipts. They are never overwritten by this producer.
    for name in bundle.bytes.observed:
        snapshot.read(name)
    for path, value in bundle.records.items():
        snapshot.committed.append((path, deepcopy(value)))
    for directory in ('plans', 'bindings', 'commits'):
        snapshot.tree(records.BASE + directory)
    old_raw = snapshot.read(journal._operation_ref(original['operation_id']))
    require(codec.strict_json_loads(old_raw) == original, 'same original raw operation', original['operation_id'])
    task_ids = {row['task_id'] for row in bundle.semantic_frame['task_index']}
    if not task_ids:
        for name in adoption.TRIPLET.values():
            snapshot.files.pop(name, None)
    all_plans = {ref['entity_id'] for ref in current_refs}
    plan_revisions = [value['revision'] for _, value in snapshot.committed
                      if value['schema_version'] == adoption.PLAN and value['plan_id'] == plan_id]
    binding_revisions = [value['binding_revision'] for _, value in snapshot.committed
                         if value['schema_version'] == adoption.BINDING and value['plan_id'] == plan_id]
    for operation in inventory:
        claim = operation['frozen']['allocations']
        if claim['plan_id'] == plan_id and operation['operation_id'] != request['operation_id']:
            plan_revisions.append(claim['plan_revision'])
            if claim['binding_revision'] is not None:
                binding_revisions.append(claim['binding_revision'])
    proposed = {'plan_id': plan_id, 'plan_revision': max(plan_revisions) + 1,
        'binding_revision': max(binding_revisions) + 1 if current_binding else None,
        'requirements': {row['requirement_id']: row['requirement_id'] for row in selected['requirements']},
        'flows': {row['id']: row['id'] for row in selected['definitions']['flows']},
        'task_definitions': {str(key): snapshot.tasks[key] for key in sorted(task_ids)}}
    require(allocations is None or allocations == proposed, 'unchanged reviewed public allocation claim', proposed,
            codec.ReasonCode.INPUT_STALE)
    plan = deepcopy(selected)
    plan['revision'] = proposed['plan_revision']
    plan['lineage'] = {'previous_plan_ref': current_ref,
        'change_summary': 'Reviewed compensation ' + request['operation_id'] + ': ' + request['reason'],
        'identity_alignment': [{'kind': kind, 'previous_id': row['id'], 'current_id': row['id'],
            'rationale': 'Retained existing formal identity during reviewed compensation'}
            for kind, family in (('flow', 'flows'), ('command', 'commands'), ('state', 'states'))
            for row in current['definitions'][family]]}
    # Existing self references must track the new immutable owner revision.
    for child in records._walk(plan):
        if child.get('owner_plan_id') == plan_id and 'owner_revision' in child:
            child['owner_revision'] = plan['revision']
    targets = []
    def target(payload):
        path = records._managed_path(payload)
        raw = projection.serialized(payload)
        checked = records.validate_record(raw, path=path)
        if not checked.ok:
            raise codec.CodecError(checked.diagnostic)
        before = snapshot.read(path, optional=True)
        require(before is None or payload['schema_version'] == 'newrouge.b-route-origins.v1',
                'fresh immutable revision path', path)
        targets.append({'path': path, 'schema_version': payload['schema_version'],
            'before_raw_digest': None if before is None else codec.raw_digest(before),
            'after_payload': payload, 'after_raw_digest': codec.raw_digest(raw), 'verification_mode': 'immutable_bytes'})
        return projection.reference(path, raw)
    new_plan_ref = target(plan)
    new_binding_ref = None
    if selected_binding is not None:
        new_plan_ref = adoption.adopted_plan_ref(targets[0])
        binding = deepcopy(selected_binding)
        binding['binding_revision'] = proposed['binding_revision']
        binding['plan_ref'] = new_plan_ref
        new_binding_ref = target(binding)
    origins = deepcopy(bundle.reference(catalog['origins_ref']))
    snapshot.read(catalog['origins_ref']['path'])
    if new_binding_ref is not None:
        origins['revision'] += 1
        for row in origins['tasks']:
            row['plan_refs'] = [new_plan_ref if ref['entity_id'] == plan_id else ref for ref in row['plan_refs']]
            row['binding_refs'] = [new_binding_ref if ref['entity_id'] == plan_id else ref for ref in row['binding_refs']]
        target(origins)
    from _b_route_operation_scope import resource_scopes
    definitions = [value['definitions'] for _, value in snapshot.committed if value['schema_version'] == adoption.PLAN]
    scope_ids = sorted(set(original['frozen']['scope_ids']) | set(bundle.selected_scopes) | set(resource_scopes(
        target_paths=[row['path'] for row in targets] + (list(adoption.TRIPLET.values()) if task_ids else []),
        plan_ids=all_plans,
        requirement_ids={row['requirement_id'] for _, value in snapshot.committed if value['schema_version'] == adoption.PLAN
                         for row in value['requirements']},
        flow_ids={row['id'] for defs in definitions for row in defs['flows']}, task_ids=task_ids,
        command_ids={row['id'] for defs in definitions for row in defs['commands']},
        state_ids={row['id'] for defs in definitions for row in defs['states']})))
    task_docs = {name: records.task_document_digest(name, snapshot.read(name))
                 for name in adoption.TRIPLET.values() if task_ids and snapshot.files.get(name) is not None}
    task_raw = {name: snapshot.files[name] for name in task_docs}
    # Keep raw Task bytes in the review subject; receipt consumption uses the
    # established Task projection so lawful status progress stays possible.
    excluded = {row['path'] for row in targets} | set(adoption.TRIPLET.values())
    authority = [{'path': name, 'schema_version': 'raw.bytes.v1', 'raw_digest': digest}
        for name, digest in sorted(snapshot.files.items()) if digest is not None and name not in excluded]
    frozen = {'producer': 'compensation', 'request': deepcopy(request), 'allocations': proposed,
        'scope_ids': scope_ids, 'authority_refs': authority, 'targets': targets,
        'compensation': {'relation': deepcopy(request['compensates']), 'current_catalog_digest': codec.raw_digest(catalog_raw),
            'current_frame_digest': codec.canonical_digest(bundle.semantic_frame),
            'old_scope_ids': original['frozen']['scope_ids'], 'current_scope_ids': bundle.selected_scopes,
            'source_plan_ref': selected_ref, 'source_binding_ref': selected_binding_ref,
            'retained_plan_refs': [ref for ref in current_refs if ref['entity_id'] != plan_id],
            'retained_binding_refs': [ref for ref in binding_refs if ref['entity_id'] != plan_id],
            'task_document_digests': task_docs, 'task_raw_digests': task_raw}}
    validate_relation(frozen, inventory)
    snapshot.verify()
    return snapshot, frozen


def make_subject(snapshot, request, frozen):
    old = journal.read_operation(snapshot.root, operation_id=request['compensates']['operation_id'])
    from _b_route_qualified_compensation_dispatch import for_snapshot
    qualified=for_snapshot(snapshot,original=old)
    QUALIFIED_SUBJECT=qualified.SUBJECT
    is_qualified = qualified.family_for_snapshot(snapshot)
    if is_qualified:
        current_files, private_files = qualified.capture_files(snapshot, original=old)
    else:
        current_files = {name: base64.b64encode(snapshot.read(name)).decode('ascii')
                         for name, digest in list(snapshot.files.items()) if digest is not None}
    value = {'schema_version': QUALIFIED_SUBJECT if is_qualified else SUBJECT,
        'producer': 'compensation', 'operation_id': request['operation_id'],
        'request': review.request_body(request), 'preview': deepcopy(frozen), 'policy_identity': review.policy_identity(),
        'original_operation': deepcopy(old), 'original_effects': deepcopy(old['frozen']['targets']),
        'current_files': current_files,
        'task_definitions': {str(key): item for key, item in snapshot.task_payloads.items()
                             if str(key) in frozen['allocations']['task_definitions']},
        'native_threads': snapshot.compensation_threads, 'native_turns': snapshot.compensation_turns}
    if is_qualified:
        value['private_files'] = private_files
    return value


def _persist_review(root, subject, artifacts):
    operation_id = subject['operation_id']
    home = review.location(operation_id)
    for name, data in artifacts.items():
        review.write_once(root, home + '/' + name, data)
    value = {'status': 'review_prepared', 'operation_id': operation_id, 'subject_ref': home + '/subject.json',
        'subject_digest': codec.canonical_digest(subject), 'workspace': home + '/w',
        'machine_preservation': None, 'semantic_execution_required': True, 'model_dispatched': False,
        'runner_command': review.runner_command(root, operation_id),
        'required_environment': {'NEWROGUE_CODEX_REASONING_EFFORT': 'high'},
        'execution_capture_ref': home + '/execution.json', **FLAGS}

    from _b_route_qualified_compensation_dispatch import for_subject
    qualified=for_subject(subject)
    QSUBJECT,QDELIVERY,QCLAIM=qualified.SUBJECT,qualified.DELIVERY,qualified.CLAIM
    if subject['schema_version'] == QSUBJECT:
        value.update(subject_schema=QSUBJECT, review_delivery=QDELIVERY, review_claim=QCLAIM)
    return value


def _review_preview_body(root, request, *, seal=False, delivery=None, segmented_preflight=False,segmented_action=None,model_request_budget=None):
    from _b_route_operation_scope import business_guard, writer_boundary
    require(not seal or delivery is None, 'saved delivery inferred only during review completion', delivery)
    require(not segmented_preflight or (not seal and delivery==profiles.PUBLISHED.name('delivery')),
            'explicit published-history offline segmented preflight',delivery)
    root = Path(root).absolute()
    saved_path = review.path(root, review.location(request['operation_id']) + '/subject.json')
    saved = review.read_subject(root, request['operation_id']) if saved_path.exists() else None
    profile = profiles.subject(saved) if saved and saved['schema_version'] in (profiles.ORIGINAL.name('subject'),profiles.PUBLISHED.name('subject')) else profiles.ORIGINAL
    if saved is None and delivery == profiles.PUBLISHED.name('delivery'):
        profile = profiles.PUBLISHED
    snapshot, frozen = build(root, request, allocations=saved['preview']['allocations'] if saved else None,review_profile=profile)
    with business_guard(root, frozen['scope_ids'], operation_id=request['operation_id'], review_only=True):
        snapshot, checked = build(root, request, allocations=frozen['allocations'],review_profile=profile)
        require(checked == frozen, 'same compensation preview under complete business scopes', request['operation_id'])
        subject = make_subject(snapshot, request, frozen)
        require(saved is None or saved == subject, 'unchanged complete review subject', request['operation_id'],
                codec.ReasonCode.INPUT_STALE)
        if seal:
            require(saved is not None, 'original independent review subject', request['operation_id'])
            # Full protocol replay happens outside metadata/WRITER.
            proof = review.produce_proof(root, request['operation_id'])
            for ref in proof['files']:
                snapshot.ref(ref)
        from _b_route_qualified_compensation_dispatch import for_subject
        qualified=for_subject(subject)
        if subject['schema_version'] == qualified.SUBJECT:
            require(seal or delivery == qualified.DELIVERY,
                    'explicit qualified delivery selection for actual qualified ancestry', delivery)
        else:
            require(delivery not in ('newrouge.b-route-qualified-compensation-review-delivery.v1',
                                    'newrouge.b-route-qualified-compensation-review-delivery.v2'),
                    'legacy ancestry retains legacy v3/v4 delivery', delivery)
        if segmented_preflight:
            # No business review is prepared/sealed and no old one-turn proof is
            # emitted. The adapter saves its own offline plan and input archive.
            import _b_route_compensation_segments as segments
            derived=qualified.model_packet(root,subject)
            result=segments.prepare(root,derived)
            snapshot.verify()
            return result
        if segmented_action is not None:
            from _b_route_compensation_segmented_execution import prepare as segment_prepare,execute as segment_execute
            require(segmented_action in ('prepare','execute','resume') and not seal
                and subject['schema_version']==profiles.PUBLISHED.name('subject'),
                'explicit published-history segmented execution action',segmented_action)
            derived=qualified.model_packet(root,subject)
            result=(segment_prepare(root,derived) if segmented_action=='prepare' else
                segment_execute(root,subject['operation_id'],publication_only=segmented_action=='resume',derived=derived,model_request_budget=model_request_budget))
            snapshot.verify()
            return result
        artifacts = None if seal else review.review_artifacts(root, subject, delivery=delivery)
        qualified.bind_action(snapshot)
        policy, pins = review.policy_observations()
        require(policy == subject['policy_identity'], 'same materials/decoder policy', request['operation_id'], codec.ReasonCode.INPUT_STALE)
        def unchanged():
            snapshot.verify()
            from _b_route_frozen_native_reader import _safe
            require(all(codec.raw_digest(_safe(Path(name)).read_bytes()) == digest for name, digest in pins.items()),
                    'same checked review policy resources at short boundary', request['operation_id'], codec.ReasonCode.INPUT_STALE)
        with writer_boundary(root, recheck=unchanged):
            if seal:
                value = {'status': 'reviewed', 'host_review_ref': review.seal(root, request['operation_id'], proof), **FLAGS}
                if subject['schema_version'] == qualified.SUBJECT:
                    value.update(subject_schema=qualified.SUBJECT, review_delivery=qualified.DELIVERY, review_claim=qualified.CLAIM)
                    from _b_route_compensation_segmented_execution import PROOF as SEGMENTED_PROOF,DELIVERY as SEGMENTED_DELIVERY
                    if proof['schema_version']==SEGMENTED_PROOF:value['review_delivery']=SEGMENTED_DELIVERY
                return value
            return _persist_review(root, subject, artifacts)


def _run_body(root, operation_id, request_raw, *, reserve_only=False):
    from _b_route_operation_scope import business_guard, writer_boundary
    root = Path(root).absolute()
    request = journal.validate_operation_request(request_raw)
    require(request['operation_id'] == operation_id, 'exact compensation owner', operation_id)
    existing = next((row for row in journal.operation_inventory(root) if row['operation_id'] == operation_id), None)
    require(not reserve_only or existing is not None, 'original prepared compensation', operation_id)
    if existing:
        require(existing['request_digest'] == codec.canonical_digest(request), 'same ID and complete request', operation_id)
        request = existing['frozen']['request']
        request_raw = base64.b64decode(existing['request_raw_base64'], validate=True)
    subject, support = review.verify_saved(root, request)
    profile = profiles.subject(subject) if subject['schema_version'] in (profiles.ORIGINAL.name('subject'),profiles.PUBLISHED.name('subject')) else profiles.ORIGINAL
    snapshot, frozen = build(root, review.request_body(request), allocations=subject['preview']['allocations'],review_profile=profile)
    require(make_subject(snapshot, review.request_body(request), frozen) == subject,
            'complete current-before, original effects and independent review', operation_id, codec.ReasonCode.INPUT_STALE)
    import _b_route_qualified_compensation_dispatch as qualified
    qualified.bind_action(snapshot)
    frozen['request'] = deepcopy(request)
    for ref in support:
        snapshot.ref(ref)
    frozen['authority_refs'] = sorted([*frozen['authority_refs'], *support], key=lambda row: row['path'])
    require(existing is None or existing['frozen'] == frozen, 'unchanged original frozen compensation', operation_id)
    with business_guard(root, frozen['scope_ids'], operation_id=operation_id, compensation_frozen=frozen):
        snapshot.verify()
        current = journal.operation_inventory(root)
        adoption.validate_operations(current)
        # Do complete inventory/proof checking before acquiring global writer.
        captured = {journal._operation_ref(row['operation_id']): codec.read_reference_bytes(root,
            journal._operation_ref(row['operation_id'])) for row in current}
        index = journal.OPERATION_STORE + '/pending.json'
        index_path = journal._operation_path(root, index)
        index_raw = index_path.read_bytes() if index_path.exists() else None
        value = ({**existing, 'state': 'reserved' if reserve_only else existing['state']} if existing else
                 journal.draft_operation(root, request_raw=request_raw, frozen=frozen))
        def unchanged():
            snapshot.verify()
            require(all(codec.read_reference_bytes(root, name) == raw for name, raw in captured.items())
                    and (index_path.read_bytes() if index_path.exists() else None) == index_raw,
                    'same complete operation/index allocation claim at short boundary', operation_id, codec.ReasonCode.INPUT_STALE)
        with writer_boundary(root, recheck=unchanged):
            if existing != value:
                journal._operation_write(root, value, current, verify=False)
        require(journal.read_operation(root, operation_id=operation_id) == value,
                'complete persisted operation/index after short write', operation_id)
        return {**adoption._result(value), 'producer': 'compensation', **FLAGS}


@contextmanager
def _commit_context_body(root, *, operation_id):
    envelope = journal.read_operation(root, operation_id=operation_id)
    require(envelope['state'] == 'reserved', 'reserved reviewed compensation', operation_id)
    request = envelope['frozen']['request']
    subject, support = review.verify_saved(root, request)
    profile = profiles.subject(subject) if subject['schema_version'] in (profiles.ORIGINAL.name('subject'),profiles.PUBLISHED.name('subject')) else profiles.ORIGINAL
    snapshot, frozen = build(root, review.request_body(request), allocations=envelope['frozen']['allocations'],review_profile=profile)
    require(make_subject(snapshot, review.request_body(request), frozen) == subject,
            'same current formal chain and reviewed compensation', operation_id, codec.ReasonCode.INPUT_STALE)
    import _b_route_qualified_compensation_dispatch as qualified
    qualified.bind_action(snapshot)
    frozen['request'] = request
    for ref in support:
        snapshot.ref(ref)
    frozen['authority_refs'] = sorted([*frozen['authority_refs'], *support], key=lambda row: row['path'])
    require(frozen == envelope['frozen'], 'original complete frozen compensation', operation_id)
    yield snapshot, envelope


def verify_observations(root, envelope, intent, *, facts, published=False):
    """Replay saved current-before and permit only this owner's exact effects."""
    from _b_route_commit import _read, _decode, _digest, _catalog_frame
    subject = review.read_subject(root, envelope['operation_id'])
    require(subject['schema_version'] in (SUBJECT,profiles.ORIGINAL.name('subject'),profiles.PUBLISHED.name('subject')) and subject['policy_identity'] == intent['policy_identity'],
            'current compensation rules and original reviewed subject', envelope['operation_id'], codec.ReasonCode.INPUT_STALE)
    expected = deepcopy(subject['preview'])
    expected['request'] = envelope['frozen']['request']
    proof_ref = expected['request']['host_review_ref']
    proof = codec.strict_json_loads(_read(root, proof_ref['path']))
    expected['authority_refs'] = sorted([*expected['authority_refs'], proof_ref, *proof['files']], key=lambda row: row['path'])
    require(codec.canonical_digest(expected) == envelope['frozen_digest'],
            'exact reviewed compensation and support closure', envelope['operation_id'])
    require(codec.raw_digest(_decode(intent['catalog_before'])) == envelope['frozen']['compensation']['current_catalog_digest'],
            'reviewed original current catalog image', envelope['operation_id'])
    permitted = {row['path']: {row['before_raw_digest'], row['after_raw_digest']} for row in envelope['frozen']['targets']}
    if subject['schema_version'] in (profiles.ORIGINAL.name('subject'),profiles.PUBLISHED.name('subject')):
        from _b_route_qualified_compensation_review_v2 import restore_captured_files, _inputs
        context = _inputs(root,subject,proof=proof) if subject['schema_version'] == profiles.PUBLISHED.name('subject') else None
        captured = restore_captured_files(root, subject,context=context)
    else:
        captured = {name: base64.b64decode(encoded,validate=True) for name,encoded in subject['current_files'].items()}
    for name, data in captured.items():
        if name == records.CATALOG_PATH:
            continue
        actual = _digest(_read(root, name, optional=True))
        require(actual in permitted.get(name, {codec.raw_digest(data)}),
                'unchanged reviewed source/current-before or owned exact effect', name, codec.ReasonCode.INPUT_STALE)
        facts.file(str(root / name), actual)
    for ref in envelope['frozen']['authority_refs']:
        if ref['path'] != records.CATALOG_PATH:
            actual = _digest(_read(root, ref['path'], optional=True))
            require(actual in permitted.get(ref['path'], {ref['raw_digest']}),
                    ref['raw_digest'], ref['path'], codec.ReasonCode.INPUT_STALE)
            facts.file(str(root / ref['path']), actual)
    for target in envelope['frozen']['targets']:
        checked = journal.classify_frozen_target(root, target)
        facts.file(str(root / target['path']), checked['actual_raw_digest'])
    actual_catalog = _read(root, records.CATALOG_PATH)
    expected_catalog = _decode(intent['catalog_after']) if published else _decode(intent['catalog_before'])
    if actual_catalog not in (_decode(intent['catalog_before']), _decode(intent['catalog_after'])):
        require(_catalog_frame(root, envelope, actual_catalog, intent['before_files'])
                == _catalog_frame(root, envelope, expected_catalog, intent['before_files']),
                'unchanged related formal chain after unrelated publication', records.CATALOG_PATH, codec.ReasonCode.INPUT_STALE)
    require(_catalog_frame(root, envelope, _decode(intent['catalog_before']), intent['before_files'],
                           origins_raw=_decode(intent['origins_before'])) == intent['catalog_frame'],
            'exact original current-before frame', envelope['operation_id'])
    facts.file(str(root / records.CATALOG_PATH), _digest(actual_catalog))


def prove_resolution(root, successor, original, graph):
    """Actual terminal evidence alone releases this exact immutable old claim."""
    validate_relation(successor['frozen'], graph['operations'])
    require(successor['operation_id'] in graph['terminals'], 'actual complete successor proof', successor['operation_id'])
    intent = graph['intents'][successor['operation_id']]
    subject, support = review.verify_saved(root, successor['frozen']['request'])
    expected = deepcopy(subject['preview'])
    expected['request'] = successor['frozen']['request']
    expected['authority_refs'] = sorted([*expected['authority_refs'], *support], key=lambda row: row['path'])
    require(expected == successor['frozen'], 'independently reviewed exact terminal compensation', successor['operation_id'])
    require(subject['original_operation'] == original and subject['original_effects'] == original['frozen']['targets'],
            'exact original immutable relation in terminal subject', original['operation_id'])
    # terminal_valid already proves receipt, publication chain and actual current
    # formal bundle. Do not replay old stale effects or require mutable old input.
    require(intent['receipt']['operation_digest'] == successor['frozen_digest'],
            'receipt sealed complete reviewed successor', successor['operation_id'])
    # Recheck selected immutable semantic sources. terminal_valid proves the
    # current formal Task projections; later legitimately published definitions
    # must not be compared forever with this historical operation's snapshot.
    candidates = {row['path']: projection.serialized(row['after_payload']) for row in successor['frozen']['targets']}
    records.validate_compensation_sources(successor['frozen'], candidates=candidates, root=root,
        task_join=adoption._task_context(adoption.Snapshot(root)), verify_tasks=False)


def review_preview(root, request, *, seal=False, delivery=None, segmented_preflight=False,segmented_action=None,model_request_budget=None):
    from _b_route_qualified_compensation_dispatch import action
    with action():
        return _review_preview_body(root, request, seal=seal, delivery=delivery,segmented_preflight=segmented_preflight,
                                   segmented_action=segmented_action,model_request_budget=model_request_budget)


def run(root, operation_id, request_raw, *, reserve_only=False):
    from _b_route_qualified_compensation_dispatch import action
    with action():
        return _run_body(root, operation_id, request_raw, reserve_only=reserve_only)


@contextmanager
def commit_context(root, *, operation_id):
    from _b_route_qualified_compensation_dispatch import action
    with action():
        with _commit_context_body(root, operation_id=operation_id) as value:
            yield value
