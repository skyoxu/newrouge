"""Pure publication products for the shared B commit owner.

These drafts allocate nothing and grant no authorization. With root=None they
use only supplied bytes; an explicit root uses the existing safe read-only
record closure owner. The outer owner must revalidate
native eligibility/authority, hold the shared leases, persist the complete
intent, verify actual targets, journal the catalog bytes, and publish last.
Full external proof checks deliberately remain enabled here; this is not the
future committed-reader API for clones lacking local proof logs.
"""
from copy import deepcopy
import json

import _b_route_codec as codec
import _b_route_records as records
import _planning_apply_journal as journal


def _require(condition, expected, actual, code=codec.ReasonCode.CONFLICT):
    if not condition:
        raise codec.CodecError(codec.Diagnostic(code, codec.Stage.CONTENT,
            expected=expected, actual=actual))


def _checked(value, path):
    result = records.validate_record(value, path=path)
    if not result.ok:
        raise codec.CodecError(result.diagnostic)
    return value


def serialized(value):
    """Use the exact existing frozen target serializer, without normalization."""
    codec.validate_json_value(value)
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _candidate_bytes(candidates, path, *, root=None):
    if path not in candidates and root is not None:
        # An unrelated plan-only operation retains actual published governance.
        # Use the same contained original-byte resolver as bundle validation;
        # no supplied payload is manufactured for a file outside its targets.
        return records._Bytes({}, root).read(path)
    _require(path in candidates and type(candidates[path]) is bytes,
             'required original candidate bytes', path, codec.ReasonCode.UNRESOLVED_REFERENCE)
    return candidates[path]


def reference(path, raw):
    result = records.validate_record(raw, path=path)
    if not result.ok:
        raise codec.CodecError(result.diagnostic)
    value = codec.strict_json_loads(raw)
    return {'path': path, 'schema_version': value['schema_version'],
        'entity_id': result.entity_id, 'revision': result.revision,
        'digest': codec.raw_digest(raw), 'verification_mode': 'raw', 'codec_version': None}


def _head_selections(current_catalog, receipt, *, frozen=None):
    """Retain each existing head; only target identities authorize replacement."""
    before = {} if current_catalog is None else {
        row['scope_id']: row for row in current_catalog['scope_heads']}
    targets = {row['path'].casefold() for row in receipt['targets']}
    replacements = {}
    for field in ('plan_refs', 'binding_refs'):
        refs = [ref for ref in receipt[field] if ref['path'].casefold() in targets]
        replacements[field] = {ref['entity_id']: ref for ref in refs}
        _require(len(replacements[field]) == len(refs),
                 'one target revision per family and identity', field)
    compensation = frozen is not None and frozen.get('producer') == 'compensation'
    task_comp = frozen is not None and frozen.get('producer') in ('task_compilation', 'chapter4_binding')
    shared_container_scopes = set()
    if task_comp:
        import _b_route_operation_scope
        shared_container_scopes = set(_b_route_operation_scope.resource_scopes(target_paths=[
            records.BASE + 'policy.v1.json',
            records.BASE + 'task-origins.v1.json',
            '.taskmaster/tasks/tasks.json',
            '.taskmaster/tasks/tasks_back.json',
            '.taskmaster/tasks/tasks_gameplay.json',
        ]))
    heads = []
    for scope in receipt['scopes']:
        previous = before.get(scope)
        if task_comp:
            if scope in shared_container_scopes:
                heads.append({'scope_id': scope, 'plan_refs': [], 'binding_refs': []})
                continue
            if scope.startswith('task:'):
                tid = int(scope.split(':', 1)[1])
                mapped_plan_ids = {
                    t['after_payload']['plan_id']
                    for t in frozen['targets']
                    if t['schema_version'] == 'newrouge.b-route-binding.v1'
                    and any(m['task_id'] == tid for m in t['after_payload']['task_mappings'])
                }
                target_binding_plan_ids = set(replacements['binding_refs'])
                kept_bindings = [
                    ref for ref in (previous['binding_refs'] if previous is not None else [])
                    if ref['entity_id'] not in target_binding_plan_ids
                ]
                added_bindings = [
                    replacements['binding_refs'][pid]
                    for pid in sorted(mapped_plan_ids)
                    if pid in replacements['binding_refs']
                ]
                heads.append({
                    'scope_id': scope,
                    'plan_refs': deepcopy(previous['plan_refs']) if previous is not None else [],
                    'binding_refs': deepcopy(kept_bindings + added_bindings),
                })
                continue
            if scope.startswith('file:') and previous is None:
                heads.append({
                    'scope_id': scope,
                    'plan_refs': [],
                    'binding_refs': deepcopy(list(replacements['binding_refs'].values())),
                })
                continue
        head = {'scope_id': scope}
        for field in ('plan_refs', 'binding_refs'):
            if compensation:
                # Compensation keeps its separately authorized retained selection.
                refs = receipt[field]
            elif previous is None:
                refs = list(replacements[field].values())
            else:
                existing_ids = {ref['entity_id'] for ref in previous[field]}
                refs = [replacements[field].get(ref['entity_id'], ref) for ref in previous[field]]
                if field == 'binding_refs':
                    previous_plan_ids = {ref['entity_id'] for ref in previous['plan_refs']}
                    is_resource_scope = scope.startswith((
                        'file:', 'task:', 'plan:', 'flow:', 'requirement:', 'command:', 'state:',
                    ))
                    for entity_id, ref in replacements[field].items():
                        if entity_id not in existing_ids and (entity_id in previous_plan_ids or is_resource_scope):
                            refs.append(ref)
            head[field] = deepcopy(refs)
        heads.append(head)
    return heads


def receipt_for_frozen(*, operation_id, frozen, resolved_definitions, catalog_before=None, target_overrides=None):
    """Draft a receipt bound to the complete frozen identity; never claim verified.

The current 2.6 target contract supports immutable formal records. Task
compilation targets bind triplet containers via task_definition_projection and
immutable formal records via immutable_bytes.
"""
    journal._operation_schema(frozen, 'Frozen')
    _require(operation_id == frozen['request']['operation_id'],
             'original frozen operation ID', operation_id)
    path = records.BASE + f'commits/{operation_id}.json'
    # Validate the formal FileId before interpreting or serializing any target.
    skeleton = {'schema_version': 'newrouge.b-route-commit.v1',
        'operation_id': operation_id, 'revision': 1,
        'operation_digest': codec.canonical_digest(frozen), 'scopes': frozen['scope_ids'],
        'authority': [], 'targets': [], 'plan_refs': [], 'binding_refs': [],
        'resolved_definitions': deepcopy(resolved_definitions),
        'result': {'target_paths': [], 'scope_ids': frozen['scope_ids']}}
    _checked(skeleton, path)
    _require(frozen['scope_ids'] == sorted(set(frozen['scope_ids'])),
             'sorted distinct complete frozen scopes', frozen['scope_ids'])
    for scope in frozen['scope_ids']:
        codec.validate_business_id(scope)
    triplet_paths = {
        '.taskmaster/tasks/tasks.json',
        '.taskmaster/tasks/tasks_back.json',
        '.taskmaster/tasks/tasks_gameplay.json',
    }
    overrides = target_overrides or {}
    seen = set()
    for target in frozen['targets']:
        name = target['path']
        codec.validate_reference_path(name)
        _require(name.casefold() not in seen, 'distinct target paths', name)
        seen.add(name.casefold())
        _require(name.casefold() not in (path.casefold(), records.CATALOG_PATH.casefold()) and
                 not name.casefold().startswith((records.BASE + 'commits/').casefold()),
                 'ordinary targets excluding receipt/catalog', name, codec.ReasonCode.DIGEST_CYCLE)
        if target['verification_mode'] == 'task_definition_projection':
            _require(frozen.get('producer') in ('task_compilation', 'chapter4_binding'),
                     'immutable formal targets in this owner slice', target['verification_mode'])
            _require(name.casefold() in triplet_paths,
                     'actual Task triplet path for projection target', name, codec.ReasonCode.INVALID_REFERENCE)
            _require(target.get('codec_version') == records.PROJECTION_CODEC,
                     records.PROJECTION_CODEC, target.get('codec_version'), codec.ReasonCode.UNKNOWN_CODEC_VERSION)
            raw = serialized(target['after_payload'])
            _require(codec.raw_digest(raw) == target['after_raw_digest'],
                     target['after_raw_digest'], name, codec.ReasonCode.DIGEST_MISMATCH)
            projected = records.task_document_digest(name, raw)
            _require(projected == target['after_projection_digest'],
                     target['after_projection_digest'], projected, codec.ReasonCode.DIGEST_MISMATCH)
            override = overrides.get(name)
            if override is not None:
                _require(override.get('projection_digest') == target['after_projection_digest'],
                         target['after_projection_digest'], override.get('projection_digest'),
                         codec.ReasonCode.DIGEST_MISMATCH)
                before_digest = override['before_digest']
                after_digest = override['after_digest']
                projection_digest = override['projection_digest']
            else:
                before_digest = target['before_raw_digest']
                after_digest = target['after_raw_digest']
                projection_digest = target['after_projection_digest']
            skeleton['targets'].append({'path': name, 'before_digest': before_digest,
                'after_digest': after_digest, 'verification_mode': 'task_definition_projection',
                'codec_version': records.PROJECTION_CODEC, 'projection_digest': projection_digest})
            skeleton['result']['target_paths'].append(name)
            continue
        _require(target['verification_mode'] == 'immutable_bytes',
                 'immutable formal targets in this owner slice', target['verification_mode'])
        _checked(target['after_payload'], name)
        _require(target['schema_version'] == target['after_payload']['schema_version'],
                 'matching target schema identity', name, codec.ReasonCode.SCHEMA_MISMATCH)
        raw = serialized(target['after_payload'])
        _require(codec.raw_digest(raw) == target['after_raw_digest'],
                 target['after_raw_digest'], name, codec.ReasonCode.DIGEST_MISMATCH)
        skeleton['targets'].append({'path': name, 'before_digest': target['before_raw_digest'],
            'after_digest': target['after_raw_digest'], 'verification_mode': 'immutable_bytes',
            'codec_version': None, 'projection_digest': target['after_raw_digest']})
        skeleton['result']['target_paths'].append(name)
        family = target['schema_version']
        if family in ('newrouge.b-route-plan.v1', 'newrouge.b-route-binding.v1'):
            ref = reference(name, raw)
            if family.endswith('-plan.v1') and frozen.get('producer') == 'compensation':
                linked = [row['after_payload']['plan_ref'] for row in frozen['targets']
                    if row['schema_version'] == 'newrouge.b-route-binding.v1'
                    and row['after_payload']['plan_ref']['path'] == name]
                if linked:
                    from _b_route_adoption import adopted_plan_ref
                    _require(all(row == adopted_plan_ref(target) for row in linked),
                             'exact same-batch canonical binding plan identity', name)
                    ref = deepcopy(linked[0])
            skeleton['plan_refs' if family.endswith('-plan.v1') else 'binding_refs'].append(ref)
    seen = set()
    targets = {row['path'].casefold(): row for row in skeleton['targets']}
    for ref in frozen['authority_refs']:
        name = ref['path']
        codec.validate_reference_path(name)
        _require(name.casefold() not in seen, 'distinct authority paths', name)
        seen.add(name.casefold())
        _require(name.casefold() != path.casefold(), 'no receipt authority cycle', name,
                 codec.ReasonCode.DIGEST_CYCLE)
        row = targets.get(name.casefold())
        _require(row is None or row['before_digest'] == ref['raw_digest'],
                 'same authority/target before image', name)
        skeleton['authority'].append({'path': name, 'before_digest': ref['raw_digest'],
            'after_digest': row['after_digest'] if row else
                (None if name.casefold() == records.CATALOG_PATH.casefold() else ref['raw_digest'])})
    if frozen.get('producer') == 'compensation':
        compensation = frozen['compensation']
        for field in ('plan_refs', 'binding_refs'):
            skeleton[field].extend(deepcopy(compensation['retained_' + field]))
        for name, digest in compensation['task_document_digests'].items():
            raw_digest = compensation['task_raw_digests'][name]
            skeleton['targets'].append({'path': name, 'before_digest': raw_digest,
                'after_digest': raw_digest, 'verification_mode': 'task_definition_projection',
                'codec_version': records.PROJECTION_CODEC, 'projection_digest': digest})
            skeleton['result']['target_paths'].append(name)
    if catalog_before is not None and frozen.get('producer') != 'compensation':
        _require(type(catalog_before) is bytes, 'original catalog before bytes', type(catalog_before).__name__)
        _checked(catalog_before, records.CATALOG_PATH)
        before = codec.strict_json_loads(catalog_before)
        for head in _head_selections(before, skeleton, frozen=frozen):
            for field in ('plan_refs', 'binding_refs'):
                for ref in head[field]:
                    if ref not in skeleton[field]:
                        skeleton[field].append(ref)
    return deepcopy(_checked(skeleton, path))


def catalog_for_receipt(*, current_catalog, receipt, candidates, task_join=None, root=None, frozen=None):
    """Build a complete candidate from a verified fresh snapshot, retaining others.

All inputs are copied. Existing affected scopes retain their own selections,
replacing only target plan/binding identities; new scopes select target refs.
Structural/current-source/external proof validation remains with
the existing bundle owner, including binding-only heads and exact Task reverse
mapping. This result grants neither native admission nor permission to publish.
    The caller must first verify the original current chain against its original
    images. Recomputing derived rows here is not permission to repair a corrupt
    original catalog or waive related pending/authority checks.
"""
    candidates = deepcopy(candidates)
    if frozen is not None and frozen.get('producer') == 'compensation':
        records.validate_compensation_sources(frozen, candidates=candidates, root=root, task_join=task_join)
    path = records.BASE + f"commits/{receipt['operation_id']}.json"
    _checked(receipt, path)
    raw = serialized(receipt)
    existing = candidates.get(path)
    _require(existing is None or existing == raw, 'immutable original receipt bytes', path)
    candidates[path] = raw
    if current_catalog is None:
        _require(records.CATALOG_PATH not in candidates, 'genuinely absent bootstrap catalog',
                 records.CATALOG_PATH)
        catalog = {'schema_version': 'newrouge.b-route-catalog.v1', 'catalog_id': 'catalog',
            'revision': 1, 'policy_ref': reference(records.BASE + 'policy.v1.json',
                _candidate_bytes(candidates, records.BASE + 'policy.v1.json')),
            'origins_ref': reference(records.BASE + 'task-origins.v1.json',
                _candidate_bytes(candidates, records.BASE + 'task-origins.v1.json')),
            'scope_heads': [], 'definition_owners': [], 'task_index': []}
    else:
        _checked(current_catalog, records.CATALOG_PATH)
        _require(type(current_catalog) is bytes and candidates.get(records.CATALOG_PATH) == current_catalog,
                 'exact supplied current catalog snapshot bytes', records.CATALOG_PATH,
                 codec.ReasonCode.INPUT_STALE)
        current_catalog = codec.strict_json_loads(current_catalog)
        _require(len({h['scope_id'] for h in current_catalog['scope_heads']}) ==
                 len(current_catalog['scope_heads']), 'distinct existing scope heads', 'duplicate')
        catalog = deepcopy(current_catalog)
        catalog['revision'] += 1
        for field, name in [('policy_ref', 'policy.v1.json'), ('origins_ref', 'task-origins.v1.json')]:
            catalog[field] = reference(records.BASE + name,
                _candidate_bytes(candidates, records.BASE + name, root=root))
    selected = set(receipt['scopes'])
    _require(selected == set(receipt['result']['scope_ids']) and selected,
             'complete nonempty receipt scopes', receipt['result']['scope_ids'])
    heads = _head_selections(current_catalog, receipt, frozen=frozen)
    for head in heads:
        for field in ('plan_refs', 'binding_refs'):
            _require(all(ref in receipt[field] for ref in head[field]),
                     'head selection fixed in original receipt draft', head['scope_id'])
        head['receipt_ref'] = reference(path, raw)
    catalog['scope_heads'] = [h for h in catalog['scope_heads'] if h['scope_id'] not in selected]
    catalog['scope_heads'].extend(heads)
    candidates[records.CATALOG_PATH] = serialized(catalog)
    bundle = records._Bundle(candidates, root, records.CATALOG_PATH, None, task_join)
    plans, bindings = {}, {}
    for h in catalog['scope_heads']:
        for ref in h['plan_refs']:
            plans[codec.canonical_digest(ref)] = ref
        for ref in h['binding_refs']:
            bindings[codec.canonical_digest(ref)] = ref
            pref = bundle.reference(ref)['plan_ref']
            plans[codec.canonical_digest(pref)] = pref
    owners, tasks = {}, {}
    for ref in plans.values():
        plan = bundle.reference(ref)
        for plural, kind in [('flows', 'flow'), ('commands', 'command'), ('states', 'state')]:
            for definition in plan['definitions'][plural]:
                key = kind, definition['id']
                owner = {'kind': kind, 'definition_id': definition['id'], 'plan_ref': ref}
                _require(key not in owners or owners[key] == owner, 'one current definition owner',
                         list(key), codec.ReasonCode.DUPLICATE_OWNER)
                owners[key] = owner
    for ref in bindings.values():
        binding = bundle.reference(ref)
        for mapping in binding['task_mappings']:
            row = tasks.setdefault(mapping['task_id'], {'task_id': mapping['task_id'],
                'plan_refs': [], 'binding_refs': []})
            for field, value in [('plan_refs', binding['plan_ref']), ('binding_refs', ref)]:
                if value not in row[field]:
                    row[field].append(value)
    catalog['definition_owners'] = [owners[k] for k in sorted(owners)]
    catalog['task_index'] = [tasks[k] for k in sorted(tasks)]
    candidates[records.CATALOG_PATH] = serialized(catalog)
    validation = records.validate_bundle(candidates, root=root, task_join=task_join)
    if not validation.ok:
        raise codec.CodecError(validation.diagnostic)
    return deepcopy(catalog)
