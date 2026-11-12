"""Verify already published history as data, never execute the original owner.

The publication and saved evidence are the trust anchor for this explicit new
route. The result is neither AuthenticatedHistory nor approval of a new write.
Current compensation admission and a new independent review remain separate.
"""
from copy import deepcopy
from pathlib import Path
import base64
import json

import _b_route_codec as codec
import _planning_apply_journal as journal
from _b_route_qualified_historical_v3_protocol import SAVED_SUPPORT, check_saved_review_bindings

SCHEMA = 'newrouge.b-route-published-history-verification.v1'
_MINT = object()


def need(value, message):
    if not value:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,
            codec.Stage.BUNDLE, expected=message, actual='published history mismatch'))


def same(left, right):
    return json.dumps(left, ensure_ascii=False, separators=(',', ':'), allow_nan=False) == \
        json.dumps(right, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class PublishedHistoryVerification:
    """Same-read publication/data result, not an original execution identity."""
    __slots__ = ('_root', '_operation', '_operation_raw', '_files', '_roles', '_public', '_capsule', '_binding', '_pins')

    def __init__(self, key, root, operation, operation_raw, files, roles, public, capsule, binding, pins):
        need(key is _MINT, 'actual published history verifier result')
        self._root, self._operation, self._operation_raw = root, deepcopy(operation), operation_raw
        self._files, self._roles, self._public, self._capsule = files, roles, public, capsule
        self._binding, self._pins = binding, pins

    def identity(self): return self._binding['private_subject_digest']
    def binding(self): return deepcopy(self._binding)
    def public_subject(self): return deepcopy(self._public)
    def operation(self): return deepcopy(self._operation)
    def operation_raw(self): return self._operation_raw
    def files(self): return dict(self._files)
    def roles(self): return dict(self._roles)
    def subject(self):
        import _b_route_adoption_review as review
        return codec.strict_json_loads(self._files[review.location(self._operation['operation_id']) + '/subject.json'])

    def checked_original(self, root, operation):
        info = self._root.stat()
        need(self._binding['current_root_identity'] == {'path': str(self._root), 'device': info.st_dev, 'inode': info.st_ino}, 'same actual current filesystem root')
        need(Path(root).absolute() == self._root and same(operation, self._operation),
             'same current root and complete published operation')
        need(codec.read_reference_bytes(self._root, journal._operation_ref(operation['operation_id'])) == self._operation_raw,
             'unchanged original journal bytes')
        return self

    def recheck(self):
        import _b_route_adoption_review as review
        need(review.policy_identity() == self._binding['current_verifier_policy'], 'unchanged current published verifier policy')
        self.checked_original(self._root, self._operation)
        for name, pin in self._pins.items():
            need(codec.raw_digest(codec.read_reference_bytes(self._root, name)) == pin,
                 'unchanged published history support: ' + name)

    def retained_graphs(self): return [self._binding, self._public, self._capsule, self._operation, self._roles]
    def retained_buffers(self): return [self._operation_raw, *self._files.values()]


def _public_subject(subject, prompt):
    """Check the complete recorded public view against its sealed private data."""
    import _b_route_qualified_public_history_v2 as public
    from _b_route_adoption_projection import FIELDS, project_content
    split = prompt.find('\n{')
    need(split > 0, 'complete recorded public semantic JSON frame')
    value = codec.strict_json_loads(prompt[split + 1:].encode('utf-8'))
    cap = subject['origin_capsule']
    checks = {'operation_id': subject['operation_id'], 'private_subject_digest': codec.canonical_digest(subject),
        'policy_identity': subject['policy_identity'], 'source': cap['source'],
        'native_content': subject['native_content'], 'identity_alignment': subject['request']['material']['identity_alignment'],
        'allocations': subject['preview']['allocations'], 'target_before_files': subject['target_before_files'],
        'targets': subject['preview']['targets'],
        'origin_binding': {'profile': cap['profile'], 'capture_digest': cap['native_capture']['result_digest'],
                           'prepared_identity': cap['prepared_identity']},
        'target_binding': {'identity': cap['target_identity'], 'source_set_digest': cap['source_set_digest'],
            'protection_digest': codec.canonical_digest(subject['protection']), 'task_count': 0, 'catalog_before': None}}
    need(all(same(value[k], expected) for k, expected in checks.items()),
         'complete original public/private semantic correspondence')
    need(same(cap['proposal']['content'], subject['native_content']), 'whole recorded native proposal')
    need(not subject['task_definitions'] and not subject['related_records']
         and not subject['authority_files'] and subject['affected_catalog'] is None,
         'known published empty-Task historical family only')
    source = cap['source']
    need(codec.raw_digest(source['text'].encode('utf-8')) == source['raw_digest'], 'complete recorded source raw bytes')
    plans = [r for r in subject['preview']['targets'] if r['schema_version'] == 'newrouge.b-route-plan.v1']
    need(len(plans) == 1, 'one published original plan')
    ref = subject['request']['material']['handoff_ref']
    need(same(plans[0]['after_payload']['native_candidate_ref'], {'owner': 'planning_proof',
        'ref': ref['path'] + '#/proposal/content', 'files': [{'path': ref['path'], 'raw_digest': ref['raw_digest']}]}),
        'actual original complete native reference and capsule correspondence')
    projected = project_content(subject['native_content'], subject['preview']['allocations'])
    need(all(same(plans[0]['after_payload'][k], projected[k]) for k in FIELDS),
         'complete published plan/native identity interpretation')
    registered = subject['registered_source_set']
    source_raw = base64.b64decode(registered['raw_base64'], validate=True)
    need(codec.raw_digest(source_raw) == registered['raw_digest'] == cap['source_set_digest'], 'recorded SourceSet raw pin')
    need(same(value['review_scope']['source_set'], {'path': registered['path'],
        'raw_digest': registered['raw_digest'], 'value': codec.strict_json_loads(source_raw)}), 'whole recorded SourceSet view')
    protection = subject['protection']
    legacy = protection['legacy_manifest_requirement']
    boundary = {k: legacy['governed_boundary'][k] for k in ('root_real', 'head', 'anchors', 'reachable_commit_ids',
        'controls_absent', 'source_members', 'manifest_directory_exists', 'manifest_members', 'owner_records', 'original_raw_digests')}
    expected_protection = {'schema_version': protection['schema_version'], 'inventory': protection['inventory'],
        'protected_files': [{k: r[k] for k in ('path', 'exists', 'raw_digest', 'canonical_digest', 'size_bytes', 'roles')}
                            for r in protection['raw_files']],
        'triplet_documents': protection['triplet']['documents'], 'triplet_counts': protection['triplet']['counts'],
        'tasks': protection['tasks'], 'cumulative': protection['cumulative'], 'frozen_a': protection['frozen_a'],
        'historical_inventory': protection['historical_inventory'],
        'legacy_manifest_requirement': {**{k: legacy[k] for k in ('schema_version', 'state', 'reason', 'original_observation_digest')},
                                        'governed_boundary': boundary},
        'authorization': protection['authorization'], 'verification_limits': protection['verification_limits']}
    need(same(value['review_scope']['protection'], expected_protection), 'complete recorded public protection projection')
    need(same(value['current_selection']['selected_design_history'], subject['selected_design_history']),
         'complete saved selected-design history')
    from _b_route_adoption_projection import RETAINED_IN_NATIVE_PROOF, project_retained_fields
    plan = plans[0]['after_payload']
    expected = {'schema_version': public.PUBLICS[1], **checks,
        'disclosure': {'complete_source': source['raw_digest'],
            'complete_candidate': codec.canonical_digest(subject['native_content']),
            'complete_targets': codec.canonical_digest(subject['preview']['targets']),
            'opaque_proof_is_machine_verified_not_model_evidence': True},
        'plan_storage': {'plan_path': plans[0]['path'], 'plan_schema': plan['schema_version'],
            'inline_field_names': list(FIELDS), 'native_candidate_ref': plan['native_candidate_ref'],
            'retained_native_fields': {k: subject['native_content'][k] for k in sorted(RETAINED_IN_NATIVE_PROOF)},
            'retained_fields_with_host_identity_interpretation': project_retained_fields(subject['native_content'], subject['preview']['allocations']),
            'formal_bundle_read_automatically_expands_native_fields': False,
            'complete_semantics_requires_available_verified_native_reference': True},
        'review_scope': {'source_set': {'path': registered['path'], 'raw_digest': registered['raw_digest'],
                                      'value': codec.strict_json_loads(source_raw)},
            'protection': expected_protection, 'supplied_authority_files': [], 'supplied_host_lineage_refs': [],
            'governance_effect_boundary': 'recorded_policy_proposal_not_runtime_activation_or_A_qualification',
            'empty_operation_list_has_no_implemented_deny_all_or_wildcard_interpretation': True},
        'origin_evidence_role': {'opaque_proof_is_machine_verified_not_model_evidence': True,
            'model_must_review_complete_visible_source_candidate_and_target_semantics': True,
            'model_is_not_asked_to_authenticate_private_capture_hashes_or_authorize_writes': True},
        'current_selection': {'previous_formal_plan_ref': plan['lineage']['previous_plan_ref'],
            'selected_design_history': subject['selected_design_history'], 'prior_draft_documents_supplied_in_full': False,
            'native_draft_wording_is_preserved_not_verified_historical_approval': True,
            'semantic_dependency_on_unprovided_text_remains_blocking': True}}
    need(same(value, expected), 'independently rebuilt complete ordered recorded public semantics')
    public.validate_public_subject(value)
    return value


def verify(root, operation_id, *, context=None):
    """Read the actual published operation; no caller-supplied receipt or verdict."""
    import _b_route_adoption_review as review
    import _b_route_commit as commit
    import _b_route_commit_projection as projection
    import _b_route_records as records
    root = Path(root).absolute()
    operation = journal.read_operation(root, operation_id=operation_id)
    need(operation['schema_version'] == 'newrouge.b-route-adoption-operation.v2', 'published adoption family only')
    observed = {}
    def read(name):
        raw = codec.read_reference_bytes(root, name)
        need(name not in observed or observed[name] == raw, 'stable same-read historical support')
        observed[name] = raw
        return raw
    operation_raw = read(journal._operation_ref(operation_id))
    intent = commit.validate_local(root, operation)
    if context is not None:
        from _b_route_qualified_compensation_review_v2 import _SavedInputs
        need(type(context) is _SavedInputs, 'actual protocol-verified saved current scope')
    if not (commit.terminal_valid(root, operation, intent)
            and commit._publication_proven(root, operation, intent)):
        # Only this consumer's exact owned intermediate state may use its
        # independently reviewed before image. No old-auth failure fallback.
        _saved_current_before(root, operation, context)
    receipt_path = records.BASE + 'commits/' + operation_id + '.json'
    receipt_raw = read(receipt_path)
    need(receipt_raw == projection.serialized(intent['receipt']), 'exact operation-bound formal receipt')
    home = review.location(operation_id)
    buffers = {name: read(home + '/' + name) for name in (*SAVED_SUPPORT, 'review.json')}
    result = check_saved_review_bindings(operation, buffers)
    subject = codec.strict_json_loads(buffers['subject.json'])
    proof = codec.strict_json_loads(buffers['review.json'])
    need(all(any(r['path'] == ref['path'] and r['after_digest'] == ref['raw_digest'] for r in intent['receipt']['authority'])
             for ref in [operation['frozen']['request']['host_review_ref'], *proof['files']]),
         'all original proof/support identities sealed by actual publication')
    output = codec.strict_json_loads(buffers['w/output.json'])
    schema = codec.strict_json_loads(buffers['w/schema.json'])
    need(buffers['request.txt'] == review._runner_frame(buffers['w/prompt.txt'].decode('utf-8'), schema).encode('utf-8'),
         'exact saved complete public prompt/schema/runner request correspondence')
    denominator = schema['properties']['checks']['items']['properties']['id']['enum']
    required = sorted([*review.obligations(subject), 'original_origin_qualification', 'artifact_target_separation',
                       'target_source_equivalence', 'model_disclosure'])
    need(denominator == required, 'complete original version3 check denominator')
    expected_schema = review._legacy_verdict_schema(subject)
    expected_schema['properties']['schema_version']['const'] = 'newrouge.b-route-adoption-review-verdict.v3'
    expected_schema['properties']['checks'].update(minItems=len(required),maxItems=len(required))
    expected_schema['properties']['checks']['items']['properties']['id']['enum'] = required
    need(review.raw(expected_schema) == buffers['w/schema.json'], 'whole original recorded verdict schema bytes')
    rows = output['checks']
    need(len(rows) == len(denominator) == len({r['id'] for r in rows})
         and {r['id'] for r in rows} == set(denominator) and all(r['rationale'].strip() for r in rows)
         and output['verdict'] == 'approved' and output['findings'] == []
         and all(r['verdict'] == 'approved' for r in rows), 'complete recorded approved semantic review accounting')
    public = _public_subject(subject, buffers['w/prompt.txt'].decode('utf-8'))
    import hashlib
    from _b_route_qualified_historical_v3_protocol import check_retained
    retained_path = 'logs/ci/b-route-retained-executions/' + hashlib.sha256(operation_id.encode()).hexdigest() + '/binding.json'
    retained_raw = read(retained_path)
    need(codec.raw_digest(retained_raw) == subject['target_dependencies'][retained_path], 'exact operation-owned retained history bytes')
    retained = codec.strict_json_loads(retained_raw)
    unsealed_raw = read(retained['request_ref'])
    need(codec.raw_digest(unsealed_raw) == retained['request_raw_digest'], 'separate recorded unsealed request raw identity')
    unsealed = codec.strict_json_loads(unsealed_raw)
    check_retained(retained, operation_id=operation_id, target_root=subject['origin_capsule']['target_identity']['path'],
        request_ref=retained['request_ref'], request_raw_digest=codec.raw_digest(unsealed_raw), request=unsealed,
        subject=subject, consumer_root=retained['consumer_source_root'], consumer_rule=retained['consumer_rule'], execution=retained['execution'])
    need(same(retained['execution']['execution_epoch'], subject['origin_capsule']['native_capture']['source_identity'])
         and retained['execution']['old_reader_exit'] == 0 and retained['execution']['old_worker_exit'] == 1,
         'distinct recorded reader and outer-worker outcomes')
    cap_ref = operation['frozen']['request']['material']['handoff_ref']
    capsule_raw = read(cap_ref['path'])
    need(codec.raw_digest(capsule_raw) == cap_ref['raw_digest']
         and same(codec.strict_json_loads(capsule_raw), subject['origin_capsule']), 'whole original capsule raw binding')
    labels = {'subject.json': 'host:subject', 'w/prompt.txt': 'host:prompt', 'w/schema.json': 'host:schema',
        'request.txt': 'host:request', 'execution.json': 'host:execution', 'w/output.json': 'host:output', 'review.json': 'host:proof'}
    files = {home + '/' + name: data for name, data in buffers.items()}
    binding = {'schema_version': SCHEMA, 'claim': 'published_adoption_and_exact_saved_history_bytes',
        'review_profile': 'newrouge.b-route-qualified-compensation-review-subject.v3',
        'operation_id': operation_id, 'operation_raw_digest': codec.raw_digest(operation_raw),
        'frozen_digest': operation['frozen_digest'], 'request_raw_digest': operation['request_raw_digest'],
        'private_subject_digest': result['subject_digest'], 'subject_schema': subject['schema_version'],
        'public_subject_digest': codec.canonical_digest(public), 'public_subject_raw_digest': codec.raw_digest(review.raw(public)),
        'capsule_raw_digest': cap_ref['raw_digest'], 'original_runtime': proof['evidence'],
        'receipt_raw_digest': codec.raw_digest(receipt_raw), 'recorded_policy_identity': subject['policy_identity'],
        'current_verifier_policy': review.policy_identity(),
        'current_root_identity': {'path': str(root), 'device': root.stat().st_dev, 'inode': root.stat().st_ino},
        'original_owner_executed_now': False,
        'original_native_execution_authenticated_now': False, 'new_compensation_approved': False}
    pins = {name: codec.raw_digest(data) for name, data in observed.items()}
    handle = PublishedHistoryVerification(_MINT, root, operation, operation_raw, files,
        {home + '/' + name: role for name, role in labels.items()}, public, subject['origin_capsule'], binding, pins)
    handle.recheck()
    return handle


def _saved_current_before(root, operation, context):
    """Accept only a real consumer's reviewed preimage and exact owned effects."""
    from _b_route_qualified_compensation_review_v2 import _SavedInputs
    from _b_route_compensation_review_profiles import PUBLISHED
    import _b_route_adoption_review as review
    import _b_route_records as records
    import _b_route_adoption as adoption
    import _b_route_commit as commit
    import _b_route_commit_projection as projection
    need(type(context) is _SavedInputs and context.root == root
         and context.subject['schema_version'] == PUBLISHED.name('subject'), 'actual verified saved published-profile scope')
    subject = context.subject
    consumer = journal.read_operation(root, operation_id=subject['operation_id'])
    need(consumer['schema_version'] == journal.COMPENSATION_SCHEMA, 'actual original compensation consumer')
    intent = commit.validate_local(root, consumer)
    need(intent is not None, 'actual owned commit intent for saved-before recovery')
    proof_ref = consumer['frozen']['request']['host_review_ref']
    proof_raw = codec.read_reference_bytes(root, proof_ref['path'])
    proof = codec.strict_json_loads(proof_raw)
    from _b_route_compensation_segmented_execution import PROOF as SEGMENTED_PROOF
    need(proof_ref['schema_version'] == proof['schema_version'] and proof['schema_version'] in (PUBLISHED.name('proof'),SEGMENTED_PROOF)
         and codec.raw_digest(proof_raw) == proof_ref['raw_digest']
         and proof['subject_digest'] == codec.canonical_digest(subject)
         and context.proof is not None and same(proof, context.proof), 'actual exact saved new proof and context')
    expected = deepcopy(subject['preview'])
    expected['request'] = consumer['frozen']['request']
    expected['authority_refs'] = sorted([*expected['authority_refs'], proof_ref, *proof['files']],key=lambda row:row['path'])
    need(same(expected, consumer['frozen']) and codec.canonical_digest(expected) == consumer['frozen_digest'],
         'real consumer frozen effects and original reviewed current-before scope')
    captured = {name: base64.b64decode(value,validate=True) for name,value in subject['current_files'].items()}
    before = captured.get(records.CATALOG_PATH)
    need(before is not None and before == commit._decode(intent['catalog_before'])
         and codec.raw_digest(before) == expected['compensation']['current_catalog_digest'], 'exact actual reviewed catalog-before')
    permitted = {row['path']: {row['before_raw_digest'],row['after_raw_digest']} for row in expected['targets']}
    from _b_route_compensation import validate_relation
    validate_relation(expected,journal.operation_inventory(root))
    for target in expected['targets']:
        original_before = commit._decode(intent['before_files'][target['path']])
        need(commit._digest(original_before) == target['before_raw_digest']
             and (original_before is None or captured.get(target['path']) == original_before),
             'exact reviewed target before image: ' + target['path'])
    for name, raw in captured.items():
        if name == records.CATALOG_PATH:
            continue
        actual = commit._digest(commit._read(root,name,optional=True))
        need(actual in permitted.get(name,{codec.raw_digest(raw)}), 'unchanged source or exact owned before/after: ' + name)
    actual_catalog = commit._read(root,records.CATALOG_PATH)
    if actual_catalog not in (before,commit._decode(intent['catalog_after'])):
        need(commit._catalog_frame(root,consumer,actual_catalog,intent['before_files']) ==
             commit._catalog_frame(root,consumer,before,intent['before_files']), 'only unrelated legitimate catalog progress')
    original_intent = commit.validate_local(root,operation)
    need(original_intent is not None and original_intent['phase'] == 'complete'
         and commit._read(root,commit._paths(operation['operation_id'])[1],optional=True) is None,
         'complete original publication without original marker')
    receipt_path = commit._receipt_path(operation)
    receipt_raw = codec.read_reference_bytes(root,receipt_path)
    need(receipt_raw == projection.serialized(original_intent['receipt'])
         and commit._lineage_proven(root,operation,original_intent,before), 'actual original receipt and publication ancestry')
    # Reuse the formal owners over actual saved bytes; do not install them or
    # identify their historical paths/inodes as the current physical objects.
    join = records.TaskJoinContext(**{role: codec.strict_json_loads(captured[name])
        for role,name in adoption.TRIPLET.items()}) if all(name in captured for name in adoption.TRIPLET.values()) else adoption._task_context(adoption.Snapshot(root))
    bundle = records._PublishedBundle(captured,root,records.CATALOG_PATH,None,join)
    catalog = bundle.load(records.CATALOG_PATH)
    bundle.select(catalog,expected['compensation']['current_scope_ids'])
    bundle.expand();bundle.relationships(catalog);bundle.bytes.stable()
    need(bundle.selected_scopes == expected['compensation']['current_scope_ids']
         and codec.canonical_digest(bundle.semantic_frame) == expected['compensation']['current_frame_digest'],
         'complete independently reviewed current scope and semantic frame')
    history = records._PublicationHistory(captured,root,records.CATALOG_PATH,None,None)
    history.load(records.CATALOG_PATH)
    history.reference(projection.reference(receipt_path,receipt_raw))
    history.expand();history.relationships(catalog);history.bytes.stable()
