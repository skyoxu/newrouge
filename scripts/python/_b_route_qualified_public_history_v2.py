"""New disclosure adapter DRAFT; independent of legacy Packet1/v1-v4.

Only actual owned-worker AuthenticatedHistory grants a private carrier mapping.
The new public view is COMPLETE under the original positive disclosure boundary;
it never claims to reconstruct the old private subject from model-visible data.
"""
from copy import deepcopy
import json
import re
import base64
from pathlib import Path
import _b_route_codec as codec
from _b_route_qualified_historical_v3_protocol import check_subject_family
import _b_route_qualified_history_host as host2
import _b_route_qualified_history_host_v3 as host3
import _b_route_published_history as published
from _b_route_compensation_review_profiles import OLD_CLAIM, PUBLISHED_CLAIM

FRAME = 'newrouge.b-route-qualified-public-history-frame.v2'
OPERATION_VIEW = 'newrouge.b-route-qualified-public-operation-view.v2'
MAPPING = 'newrouge.b-route-qualified-public-carrier-mapping.v2'
CLAIM = 'complete_original_versioned_owner_public_semantics_with_exact_private_historical_auth'
ADOPTION = 'newrouge.b-route-adoption-operation.v2'
PUBLICS = ('newrouge.b-route-adoption-model-subject.v2','newrouge.b-route-adoption-model-subject.v3')
QUALIFIED_SUBJECT = 'newrouge.b-route-qualified-compensation-review-subject.v2'
PROFILE = 'r22-m4-nx-original.v1'
SOURCE = 'docs/testing/story-2-5-controlled-acceptance/exclusive-resolution-v15.md'
SOURCE_DIGEST = 'sha256:7e5e1fe8aeb5937c70caa16aea2a9e1784a429c70c30a4f7f4d66601f1880061'


def descriptor(claim):
    need(claim in (OLD_CLAIM, PUBLISHED_CLAIM), 'known explicit public history claim')
    version = 'v2' if claim == OLD_CLAIM else 'v3'
    return ('newrouge.b-route-qualified-public-history-frame.' + version,
            'newrouge.b-route-qualified-public-operation-view.' + version,
            'newrouge.b-route-qualified-public-carrier-mapping.' + version)


def _claim(authentication):
    return PUBLISHED_CLAIM if type(authentication) is published.PublishedHistoryVerification else CLAIM


def need(ok, expected):
    if not ok:
        raise ValueError(expected)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _checked(root, operation, authentication):
    if type(authentication) is published.PublishedHistoryVerification:
        authentication.checked_original(root, operation)
        b, p = authentication.binding(), authentication.public_subject()
        need(b['schema_version'] == published.SCHEMA and b['original_owner_executed_now'] is False
             and p['private_subject_digest'] == b['private_subject_digest']
             and codec.canonical_digest(p) == b['public_subject_digest'], 'actual published history DATA result')
        return b, p
    need(type(authentication) in (host2.AuthenticatedHistory,host3.AuthenticatedHistory),
         'opaque genuine held-worker token only')
    if type(authentication) is host2.AuthenticatedHistory:
        from _b_route_qualified_public_history import _checked as original_checked
    else:
        original_checked = _checked_v3
    b,p=original_checked(root,operation,authentication)
    check_subject_family(b['subject_schema'],p['schema_version'])
    return b, p


def operation_view(root, operation, authentication):
    b, public = _checked(root, operation, authentication)
    claim = _claim(authentication)
    _, operation_schema, _ = descriptor(claim)
    # Every semantic value below comes from actual original public_subject.
    # Original request/frozen/effects/private proof bytes remain authenticated
    # host evidence; their digests are technical identities, not semantic text.
    return {'schema_version': operation_schema, 'claim': claim,
        'operation_id': public['operation_id'], 'operation_raw_digest': b['operation_raw_digest'],
        'frozen_digest': b['frozen_digest'], 'request_raw_digest': b['request_raw_digest'],
        'private_subject_digest': b['private_subject_digest'], 'public_subject_digest': b['public_subject_digest'],
        'identity_alignment': deepcopy(public['identity_alignment']),
        'allocations': deepcopy(public['allocations']), 'target_before_files': deepcopy(public['target_before_files']),
        'targets': deepcopy(public['targets'])}


def frame(root, operation, authentication):
    b, public = _checked(root, operation, authentication)
    claim = _claim(authentication)
    frame_schema, _, _ = descriptor(claim)
    return {'schema_version': frame_schema, 'claim': claim, 'operation_id': operation['operation_id'],
        'private_subject_digest': b['private_subject_digest'],
        'public_subject_digest': b['public_subject_digest'],
        'historical_auth_digest': codec.canonical_digest(b),
        'operation_view': operation_view(root, operation, authentication),
        'semantic_fields': public}


def _plan_adoption_proof_use(record, locator):
    """Classify an already validated plan locator; never grant history authority."""
    import _b_route_records as records
    return (record.get('schema_version') == 'newrouge.b-route-plan.v1'
            and locator in record.get('adoption_proof_refs', [])
            and not any(value == locator for value in records._walk(
                {key: value for key, value in record.items() if key != 'adoption_proof_refs'})))


def capsule_mapping(root, operation, authentication, locator, *, carrier_bytes, source_record, current_subject, frame_context=None):
    """Map exact native fragments and original plan proof anchors, not private text.

    Complete native semantics come from public.native_content. origin_admission
    is opaque proof and remains host-only. The original plan's bare capsule
    adoption proof is also host-only, only when it has no other use in that plan.
    Other full/unknown capsule aliases fail.
    Preserve locator raw pins and exact source/owner/ref/file provenance; this
    is an auxiliary disclosure adapter, not a change to the formal game schema.
    """
    b, public = _checked(root, operation, authentication)
    claim = _claim(authentication)
    _, _, mapping_schema = descriptor(claim)
    need(type(locator) is dict and set(locator) == {'owner','ref','files'}
         and locator['owner'] == 'planning_proof', 'registered typed original proof owner')
    need(type(current_subject) is dict and current_subject.get('schema_version') in (QUALIFIED_SUBJECT,'newrouge.b-route-qualified-compensation-review-subject.v3','newrouge.b-route-qualified-compensation-review-subject.v1','newrouge.b-route-compensation-review-subject.v2')
         and current_subject.get('producer') == 'compensation'
         and type(current_subject.get('original_operation')) is dict
         and current_subject['request']['compensates']['operation_id']
             == current_subject['original_operation']['operation_id'],
         'actual current qualified owner frame and direct original relation')
    frame_digest = codec.canonical_digest(current_subject)
    codec.validate_reference_path(source_record)
    import _b_route_records as records
    from _b_route_qualified_compensation_review_v2 import captured_source
    record_bytes = captured_source(root,current_subject,source_record,frame_context)
    checked = records.validate_record(record_bytes, path=source_record)
    need(checked.ok, 'actual registered current semantic source record')
    record = codec.strict_json_loads(record_bytes)
    need(any(type(row) is dict and set(row) == {'owner','ref','files'}
             and codec.canonical_digest(row) == codec.canonical_digest(locator)
             for row in records._walk(record)), 'locator actually belongs to that current source record')
    captured = current_subject['current_files']
    need(source_record in captured
         and base64.b64decode(captured[source_record], validate=True) == record_bytes,
         'source record exact bytes belong to the actual complete current private frame')
    cap_ref = operation['frozen']['request']['material']['handoff_ref']
    path = cap_ref['path']
    if path in captured:
        captured_carrier=base64.b64decode(captured[path],validate=True)
    else:
        from _b_route_qualified_compensation_review_v2 import resolve_private_file
        need(path in current_subject.get('private_files',{}),'complete actual factored private carrier')
        captured_carrier=resolve_private_file(root,path,current_subject['private_files'][path])[0]
    need(captured_carrier==carrier_bytes,'exact private carrier belongs to the same actual current owner frame')
    need(locator['files'] == [{'path': path, 'raw_digest': cap_ref['raw_digest']}]
         and codec.raw_digest(carrier_bytes) == cap_ref['raw_digest'] == b['capsule_raw_digest']
         and codec.strict_json_loads(carrier_bytes) == authentication._capsule,
         'exact original authenticated private carrier bytes and pin')
    refs = {path + '#/proposal/content': ('semantic:qualified_native_content', '/native_content'),
            path + '#/origin_admission': ('host:qualified_origin_proof', None)}
    if locator['ref'] == path:
        need(_plan_adoption_proof_use(record, locator),
             'bare original capsule is only a plan adoption proof with no semantic reuse')
        role, public_pointer = 'host:qualified_origin_proof', None
    else:
        need(locator['ref'] in refs, 'explicit public semantic fragment or opaque proof; no full capsule alias')
        role, public_pointer = refs[locator['ref']]
    document = None
    if public_pointer is not None:
        document_bytes = raw(public['native_content'])
        document = {'raw_digest': codec.raw_digest(document_bytes), 'raw_bytes': len(document_bytes),
                    'text': document_bytes.decode('utf-8')}
    return {'schema_version': mapping_schema, 'claim': claim, 'frame_digest': frame_digest,
        'historical_subject_digest': b['private_subject_digest'], 'historical_public_digest': b['public_subject_digest'],
        'historical_auth_digest': codec.canonical_digest(b), 'candidate_digest':
            codec.canonical_digest(public['native_content']), 'carrier_path': path,
        'carrier_raw_digest': codec.raw_digest(carrier_bytes), 'carrier_raw_bytes': len(carrier_bytes),
        'owner': locator['owner'], 'ref': locator['ref'], 'source_record': source_record,
        'source_record_raw_digest': codec.raw_digest(record_bytes),
        'public_pointer': public_pointer, 'role': role, 'document': document}


def validate_frame(value):
    """Cold data validation only; consuming owner must rederive from real auth.

    This reader does not mint an authenticated handle or authorize consumption.
    Exact packet comparison against a fresh genuine host derivation is mandatory.
    """
    need(type(value) is dict and set(value) == {'schema_version','claim','operation_id',
        'private_subject_digest','public_subject_digest','historical_auth_digest','operation_view','semantic_fields'},
        'closed qualified public frame')
    claim = value['claim']
    frame_schema, operation_schema, _ = descriptor(claim)
    p, op = value['semantic_fields'], value['operation_view']
    need(value['schema_version'] == frame_schema and value['claim'] == claim and p['schema_version'] in PUBLICS
         and value['operation_id'] == p['operation_id']
         and value['private_subject_digest'] == p['private_subject_digest']
         and value['public_subject_digest'] == codec.canonical_digest(p), 'exact explicit public frame identity')
    need(type(op) is dict and set(op) == {'schema_version','claim','operation_id','operation_raw_digest',
        'frozen_digest','request_raw_digest','private_subject_digest','public_subject_digest','identity_alignment',
        'allocations','target_before_files','targets'} and op['schema_version'] == operation_schema
        and op['claim'] == claim and op['operation_id'] == p['operation_id']
        and op['private_subject_digest'] == value['private_subject_digest']
        and op['public_subject_digest'] == value['public_subject_digest'], 'closed exact public operation view')
    for name in ('identity_alignment','allocations','target_before_files','targets'):
        need(raw(op[name]) == raw(p[name]), 'complete type-exact public operation semantics, without omission')
    validate_public_subject(p)
    return value


def validate_public_subject(p):
    """Closed semantic DATA only; never authenticates an owner or execution."""
    extras={'plan_storage','review_scope','origin_evidence_role','current_selection'} if p['schema_version']==PUBLICS[1] else set()
    need(set(p) == {'schema_version','operation_id','private_subject_digest','policy_identity','source',
        'native_content','identity_alignment','allocations','target_before_files','targets','origin_binding',
        'target_binding','disclosure'}|extras, 'original closed public subject fields')
    for name, keys in (
        ('source', {'path','raw_digest','text'}),
        ('origin_binding', {'profile','capture_digest','prepared_identity'}),
        ('target_binding', {'identity','source_set_digest','protection_digest','task_count','catalog_before'}),
        ('disclosure', {'complete_source','complete_candidate','complete_targets',
                        'opaque_proof_is_machine_verified_not_model_evidence'})):
        need(type(p[name]) is dict and set(p[name]) == keys, 'original closed public nested fields')
    need(type(p['origin_binding']['prepared_identity']) is dict
         and set(p['origin_binding']['prepared_identity']) == {'input_identity','canonical_digest'}
         and type(p['target_binding']['identity']) is dict
         and set(p['target_binding']['identity']) == {'path','device','inode'}
         and type(p['target_binding']['task_count']) is int
         and p['target_binding']['task_count'] == 0 and p['target_binding']['catalog_before'] is None
         and p['disclosure']['opaque_proof_is_machine_verified_not_model_evidence'] is True,
         'original exact public technical binding schema')
    need(p['origin_binding']['profile'] == PROFILE and p['source']['path'] == SOURCE
         and p['source']['raw_digest'] == SOURCE_DIGEST, 'known original qualified profile/source; no new profile')
    need(codec.raw_digest(p['source']['text'].encode('utf-8')) == p['source']['raw_digest']
        == p['disclosure']['complete_source']
        and codec.canonical_digest(p['native_content']) == p['disclosure']['complete_candidate']
        and codec.canonical_digest(p['targets']) == p['disclosure']['complete_targets'],
        'complete original source/candidate/targets, never digest substitutes')
    if p['schema_version']==PUBLICS[1]:_validate_v3_fields(p)
    return p


INLINE = ('source_identity','requirements','definitions','logical_references','requirement_verification',
          'requirement_route_memberships','requirement_evidence','evidence_source_refs','coverage_table','applicability')
RETAINED = ('out_of_scope_requirement_ids','selected_dependencies','unresolved','implementation_objects')


def _validate_v3_fields(p):
    """Cold structural/meaning closure; exact fresh opaque-host rederivation is mandatory.

    This is not a replacement for the R56 positive renderer, policy, draft raw
    verification or actual original protocol replay performed by the worker.
    """
    store=p['plan_storage'];scope=p['review_scope'];selection=p['current_selection']
    need(type(store) is dict and set(store)=={'plan_path','plan_schema','inline_field_names',
         'native_candidate_ref','retained_native_fields','retained_fields_with_host_identity_interpretation',
         'formal_bundle_read_automatically_expands_native_fields',
         'complete_semantics_requires_available_verified_native_reference'}, 'closed v3 retained plan storage')
    plans=[t for t in p['targets'] if t['schema_version']=='newrouge.b-route-plan.v1']
    need(len(plans)==1 and store['plan_path']==plans[0]['path']
         and store['plan_schema']==plans[0]['schema_version'] and store['inline_field_names']==list(INLINE)
         and store['native_candidate_ref']==plans[0]['after_payload']['native_candidate_ref']
         and store['retained_native_fields']=={k:p['native_content'][k] for k in sorted(RETAINED)}
         and store['formal_bundle_read_automatically_expands_native_fields'] is False
         and store['complete_semantics_requires_available_verified_native_reference'] is True,
         'exact full retained semantics and real native locator; no invented formal read expansion')
    need(type(store['retained_fields_with_host_identity_interpretation']) is dict,
         'separate full derived mapping is data, exact owner rederivation remains required')
    need(type(scope) is dict and set(scope)=={'source_set','protection','supplied_authority_files',
         'supplied_host_lineage_refs','governance_effect_boundary',
         'empty_operation_list_has_no_implemented_deny_all_or_wildcard_interpretation'}
         and scope['supplied_authority_files']==[] and scope['supplied_host_lineage_refs']==[]
         and scope['governance_effect_boundary']=='recorded_policy_proposal_not_runtime_activation_or_A_qualification'
         and scope['empty_operation_list_has_no_implemented_deny_all_or_wildcard_interpretation'] is True,
         'complete positive protection/authority domains without new grants')
    source=scope['source_set']
    need(type(source) is dict and set(source)=={'path','raw_digest','value'}
         and source['path']=='docs/workflows/chapter3-source-set.json'
         and source['raw_digest']==p['target_binding']['source_set_digest']
         and source['value']=={'schema_version':'chapter3.source-set.v1','active_patterns':[SOURCE],
                              'active_sources':[SOURCE],'retirements':[]}, 'actual complete registered source-set view')
    need(p['origin_evidence_role']=={'opaque_proof_is_machine_verified_not_model_evidence':True,
         'model_must_review_complete_visible_source_candidate_and_target_semantics':True,
         'model_is_not_asked_to_authenticate_private_capture_hashes_or_authorize_writes':True}
         and all(type(v) is bool for v in p['origin_evidence_role'].values()),
         'complete declared host/model evidence responsibilities')
    need(type(selection) is dict and set(selection)=={'previous_formal_plan_ref','selected_design_history',
         'prior_draft_documents_supplied_in_full','native_draft_wording_is_preserved_not_verified_historical_approval',
         'semantic_dependency_on_unprovided_text_remains_blocking'}
         and selection['previous_formal_plan_ref']==plans[0]['after_payload']['lineage']['previous_plan_ref']
         and selection['prior_draft_documents_supplied_in_full'] is False
         and selection['native_draft_wording_is_preserved_not_verified_historical_approval'] is True
         and selection['semantic_dependency_on_unprovided_text_remains_blocking'] is True,
         'actual scoped positive historical draft view, not an unavailable-history exemption')
    positive_history(selection['selected_design_history'])
    _validate_protection_view(scope['protection'])
    need(scope['protection']['legacy_manifest_requirement']['governed_boundary']['root_real']==
         p['target_binding']['identity']['path'], 'original public protection has the same actual target identity')


def _checked_v3(root, operation, authentication):
    need(type(authentication) is host3.AuthenticatedHistory, 'opaque actual owned historical verifier result')
    authentication.checked_original(root, operation)
    b, p = authentication.binding(), authentication.public_subject()
    need(b['schema_version'] == 'newrouge.b-route-qualified-historical-auth.v2'
         and operation['schema_version'] == ADOPTION and p['schema_version'] == PUBLICS[1]
         and p['operation_id'] == b['operation_id'] == operation['operation_id']
         and p['private_subject_digest'] == b['private_subject_digest']
         and codec.canonical_digest(p) == b['public_subject_digest']
         and codec.raw_digest(raw(p)) == b['public_subject_raw_digest'],
         'original actual public/private/candidate/frame identity closure')
    return b, p


def require(ok, label):
    if not ok:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,
                                               codec.Stage.BUNDLE, expected=label, actual='blocked'))


def _digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'typed technical digest')
    return value


def _path(value):
    codec.validate_reference_path(value)
    require(not any(part.casefold() in {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions',
                'auth.json', 'credentials', 'credentials.json', 'credentials.toml'}
                or part.casefold().startswith('.env') for part in value.split('/')), 'no private disclosure locator')
    return value


def positive_history(value):
    require(set(value) == {'schema_version', 'document', 'drafts', 'final_draft_identity', 'fragments',
                'current_correspondence', 'scope'}
            and value['schema_version'] == 'newrouge.b-route-selected-design-history.v1', 'closed selected history view')
    require(set(value['document']) == {'origin_relative_path', 'raw_digest', 'raw_bytes', 'input_identity'},
            'only original proposal technical observation')
    from _b_route_qualified_origin import RUN
    require(value['document']['origin_relative_path'] == RUN + '/accepted-chain/proposal.json'
            and type(value['document']['raw_bytes']) is int and value['document']['raw_bytes'] > 0,
            'one positive original proposal locator')
    _path(value['document']['origin_relative_path']);_digest(value['document']['raw_digest'])
    _digest(value['document']['input_identity'])
    identities = []
    for index, row in enumerate(value['drafts']):
        require(set(row) == {'source_pointer', 'draft_identity', 'schema_version', 'input_identity', 'stage',
                    'ordinal', 'parent_draft_identities'}
                and row['source_pointer'] == '/provenance/draft_chain/' + str(index)
                and row['schema_version'] == 'newrouge.b-route-planning-draft.v1'
                and row['input_identity'] == value['document']['input_identity']
                and row['stage'] in {'batch', 'synthesis'}
                and row['ordinal'] == index + 1 and row['parent_draft_identities'] == identities,
                'complete ordered selected history identities')
        identities.append(_digest(row['draft_identity']))
    require(identities and identities[-1] == value['final_draft_identity'], 'exact final selected history identity')
    expected = ['/provenance/draft_chain/0/content/design_choices/selected_choices/0',
                '/provenance/draft_chain/0/content/design_choices/selected_choices/2',
                '/provenance/draft_chain/0/content/launch_message_profile']
    require(len(value['fragments']) == 3 and all(set(row) == {'source_pointer', 'value'}
            and row['source_pointer'] == pointer for row, pointer in zip(value['fragments'], expected)),
            'complete exact semantic profile/observer fragments')
    profile = value['fragments'][2]['value']
    require(set(profile) == {'name', 'version', 'owner', 'launch', 'launch_bindings', 'framing', 'messages',
                'ordering', 'independent_observations'}, 'no private profile carrier')
    require(set(profile['independent_observations']) == {'readUI', 'readJ', 'startup_identity'},
            'complete independent observation subtree')
    for message in profile['messages']:
        require({'channel', 'type', 'fields'} <= set(message) <= {'channel', 'type', 'fields', 'binding',
                    'op_values', 'phase_values', 'ui_values'} and message['channel'] in {'Q', 'C'},
                'positive selected wire-profile message, no protocol/capture carrier')
    require(set(value['current_correspondence']) == {'profile_command_pointer', 'observer_command_pointer',
                'final_content_equals_current_native'} and value['current_correspondence']['final_content_equals_current_native'] is True,
            'separate exact current correspondence, not historical approval')
    return deepcopy(value)


VERIFICATION_LIMITS = ['Read-only candidate, not a formal protection baseline or frozen-A policy.', 'Missing historical debug attachments remain unresolved observations, not operation prerequisites; old done never satisfies new obligations.', 'No committed reverse-governance proof is implemented; every Task candidate is blocked.', 'Double-read observations do not isolate against external concurrent writers.', 'Receipt target projections, policy bootstrap, journal and publication are not implemented.']


def _validate_protection_view(value):
    """Closed public metadata/literals only. Does not authenticate private bodies."""
    need(type(value) is dict and set(value)=={'schema_version','inventory','protected_files','triplet_documents',
         'triplet_counts','tasks','cumulative','frozen_a','historical_inventory','legacy_manifest_requirement',
         'authorization','verification_limits'}, 'closed complete public protection fields')
    need(value['schema_version']=='newrouge.b-route-protection-snapshot.v3','known original public protection schema')
    inventory=value['inventory']
    need(type(inventory) is dict and set(inventory)=={'artifact','raw_digest','content_identity','adoptable','diagnostics'}
         and inventory['adoptable'] is True and inventory['diagnostics']==[], 'actual admissible inventory metadata')
    _path(inventory['artifact']);_digest(inventory['raw_digest']);_digest(inventory['content_identity'])
    need(value['tasks']==[] and value['cumulative']==[] and value['historical_inventory'] is None
         and value['triplet_counts']=={'master':0,'back':0,'gameplay':0}
         and all(type(v) is int and v==0 for v in value['triplet_counts'].values())
         and value['triplet_documents']=={'master':{'master':{'tasks':[]}},'back':[],'gameplay':[]}
         and value['frozen_a']=={'task_set':'verified-empty','candidate_count':0,'candidates':[],
                               'classification_authorized':False}
         and type(value['frozen_a']['candidate_count']) is int
         and value['frozen_a']['classification_authorized'] is False, 'separate original empty domains')
    need(value['authorization']=={'formal_protection_baseline':False,'frozen_a':False,'write':False,
         'policy_bootstrap':False,'target_projection_verified':False}
         and all(type(v) is bool and v is False for v in value['authorization'].values())
         and value['verification_limits']==VERIFICATION_LIMITS, 'literal collector limits/false flags are not grants')
    seen=set()
    need(type(value['protected_files']) is list,'complete positive protected-file metadata list')
    for row in value['protected_files']:
        need(type(row) is dict and set(row)=={'path','exists','raw_digest','canonical_digest','size_bytes','roles'}
             and type(row['exists']) is bool and type(row['roles']) is list
             and all(type(role) is str and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}',role)
                     for role in row['roles']), 'closed public protected-file metadata; no private body')
        _path(row['path']);need(row['path'] not in seen,'unique protected-file metadata')
        seen.add(row['path'])
        if row['exists']:
            _digest(row['raw_digest']);need(type(row['size_bytes']) is int and row['size_bytes']>=0,'actual public file size')
        else:need(row['raw_digest'] is None and row['canonical_digest'] is None and row['size_bytes'] is None,
                  'explicit original absent protected file')
        if row['canonical_digest'] is not None:_digest(row['canonical_digest'])
    legacy=value['legacy_manifest_requirement']
    need(type(legacy) is dict and set(legacy)=={'schema_version','state','reason','original_observation_digest','governed_boundary'}
         and legacy['schema_version']=='newrouge.b-route-legacy-manifest-requirement.v3'
         and legacy['state']=='initially_absent' and legacy['reason']=='governed_originals',
         'same original public initial legacy observation')
    _digest(legacy['original_observation_digest'])
    boundary=legacy['governed_boundary']
    need(type(boundary) is dict and set(boundary)=={'root_real','head','anchors','reachable_commit_ids',
         'controls_absent','source_members','manifest_directory_exists','manifest_members','owner_records','original_raw_digests'}
         and boundary['source_members']==[SOURCE] and boundary['manifest_directory_exists'] is False
         and boundary['manifest_members']==[], 'complete explicit initial legacy namespace')
    for name,digest in boundary['original_raw_digests'].items():
        _path(name)
        if digest is not None:_digest(digest)
    for name in boundary['owner_records']:_path(name)
    return value
