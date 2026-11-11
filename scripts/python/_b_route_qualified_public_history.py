"""New disclosure adapter DRAFT; independent of legacy Packet1/v1-v4.

Only actual owned-worker AuthenticatedHistory grants a private carrier mapping.
The new public view is COMPLETE under the original positive disclosure boundary;
it never claims to reconstruct the old private subject from model-visible data.
"""
from copy import deepcopy
import json
import base64
from pathlib import Path
import _b_route_codec as codec
from _b_route_qualified_history_host import AuthenticatedHistory

FRAME = 'newrouge.b-route-qualified-public-history-frame.v1'
OPERATION_VIEW = 'newrouge.b-route-qualified-public-operation-view.v1'
MAPPING = 'newrouge.b-route-qualified-public-carrier-mapping.v1'
CLAIM = 'complete_original_owner_public_semantics_with_exact_private_historical_auth'
ADOPTION = 'newrouge.b-route-adoption-operation.v2'
PUBLIC = 'newrouge.b-route-adoption-model-subject.v2'
QUALIFIED_SUBJECT = 'newrouge.b-route-qualified-compensation-review-subject.v1'
PROFILE = 'r22-m4-nx-original.v1'
SOURCE = 'docs/testing/story-2-5-controlled-acceptance/exclusive-resolution-v15.md'
SOURCE_DIGEST = 'sha256:7e5e1fe8aeb5937c70caa16aea2a9e1784a429c70c30a4f7f4d66601f1880061'


def need(ok, expected):
    if not ok:
        raise ValueError(expected)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _checked(root, operation, authentication):
    need(type(authentication) is AuthenticatedHistory, 'opaque actual owned historical verifier result')
    authentication.checked_original(root, operation)
    b, p = authentication.binding(), authentication.public_subject()
    need(b['schema_version'] == 'newrouge.b-route-qualified-historical-auth.v1'
         and operation['schema_version'] == ADOPTION and p['schema_version'] == PUBLIC
         and p['operation_id'] == b['operation_id'] == operation['operation_id']
         and p['private_subject_digest'] == b['private_subject_digest']
         and codec.canonical_digest(p) == b['public_subject_digest']
         and codec.raw_digest(raw(p)) == b['public_subject_raw_digest'],
         'original actual public/private/candidate/frame identity closure')
    return b, p


def operation_view(root, operation, authentication):
    b, public = _checked(root, operation, authentication)
    # Every semantic value below comes from actual original public_subject.
    # Original request/frozen/effects/private proof bytes remain authenticated
    # host evidence; their digests are technical identities, not semantic text.
    return {'schema_version': OPERATION_VIEW, 'claim': CLAIM,
        'operation_id': public['operation_id'], 'operation_raw_digest': b['operation_raw_digest'],
        'frozen_digest': b['frozen_digest'], 'request_raw_digest': b['request_raw_digest'],
        'private_subject_digest': b['private_subject_digest'], 'public_subject_digest': b['public_subject_digest'],
        'identity_alignment': deepcopy(public['identity_alignment']),
        'allocations': deepcopy(public['allocations']), 'target_before_files': deepcopy(public['target_before_files']),
        'targets': deepcopy(public['targets'])}


def frame(root, operation, authentication):
    b, public = _checked(root, operation, authentication)
    return {'schema_version': FRAME, 'claim': CLAIM, 'operation_id': operation['operation_id'],
        'private_subject_digest': b['private_subject_digest'],
        'public_subject_digest': b['public_subject_digest'],
        'historical_auth_digest': codec.canonical_digest(b),
        'operation_view': operation_view(root, operation, authentication),
        'semantic_fields': public}


def capsule_mapping(root, operation, authentication, locator, *, carrier_bytes, source_record, current_subject, frame_context=None):
    """Map exact typed capsule fragments, never the whole private capsule.

    Complete native semantics come from public.native_content. origin_admission
    is opaque proof and remains host-only. Full/unknown capsule aliases fail.
    Preserve locator raw pins and exact source/owner/ref/file provenance; this
    is an auxiliary disclosure adapter, not a change to the formal game schema.
    """
    b, public = _checked(root, operation, authentication)
    need(type(locator) is dict and set(locator) == {'owner','ref','files'}
         and locator['owner'] == 'planning_proof', 'registered typed original proof owner')
    need(type(current_subject) is dict and current_subject.get('schema_version') in (QUALIFIED_SUBJECT,'newrouge.b-route-compensation-review-subject.v2')
         and current_subject.get('producer') == 'compensation'
         and type(current_subject.get('original_operation')) is dict
         and current_subject['request']['compensates']['operation_id']
             == current_subject['original_operation']['operation_id'],
         'actual current qualified owner frame and direct original relation')
    frame_digest = codec.canonical_digest(current_subject)
    codec.validate_reference_path(source_record)
    import _b_route_records as records
    from _b_route_qualified_compensation_review import captured_source
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
        from _b_route_qualified_compensation_review import resolve_private_file
        need(path in current_subject.get('private_files',{}),'complete actual factored private carrier')
        captured_carrier=resolve_private_file(root,path,current_subject['private_files'][path])[0]
    need(captured_carrier==carrier_bytes,'exact private carrier belongs to the same actual current owner frame')
    need(locator['files'] == [{'path': path, 'raw_digest': cap_ref['raw_digest']}]
         and codec.raw_digest(carrier_bytes) == cap_ref['raw_digest'] == b['capsule_raw_digest']
         and codec.strict_json_loads(carrier_bytes) == authentication._capsule,
         'exact original authenticated private carrier bytes and pin')
    refs = {path + '#/proposal/content': ('semantic:qualified_native_content', '/native_content'),
            path + '#/origin_admission': ('host:qualified_origin_proof', None)}
    need(locator['ref'] in refs, 'explicit public semantic fragment or opaque proof; no full capsule alias')
    role, public_pointer = refs[locator['ref']]
    document = None
    if public_pointer is not None:
        document_bytes = raw(public['native_content'])
        document = {'raw_digest': codec.raw_digest(document_bytes), 'raw_bytes': len(document_bytes),
                    'text': document_bytes.decode('utf-8')}
    return {'schema_version': MAPPING, 'claim': CLAIM, 'frame_digest': frame_digest,
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
    p, op = value['semantic_fields'], value['operation_view']
    need(value['schema_version'] == FRAME and value['claim'] == CLAIM and p['schema_version'] == PUBLIC
         and value['operation_id'] == p['operation_id']
         and value['private_subject_digest'] == p['private_subject_digest']
         and value['public_subject_digest'] == codec.canonical_digest(p), 'exact explicit public frame identity')
    need(type(op) is dict and set(op) == {'schema_version','claim','operation_id','operation_raw_digest',
        'frozen_digest','request_raw_digest','private_subject_digest','public_subject_digest','identity_alignment',
        'allocations','target_before_files','targets'} and op['schema_version'] == OPERATION_VIEW
        and op['claim'] == CLAIM and op['operation_id'] == p['operation_id']
        and op['private_subject_digest'] == value['private_subject_digest']
        and op['public_subject_digest'] == value['public_subject_digest'], 'closed exact public operation view')
    for name in ('identity_alignment','allocations','target_before_files','targets'):
        need(raw(op[name]) == raw(p[name]), 'complete type-exact public operation semantics, without omission')
    need(set(p) == {'schema_version','operation_id','private_subject_digest','policy_identity','source',
        'native_content','identity_alignment','allocations','target_before_files','targets','origin_binding',
        'target_binding','disclosure'}, 'original closed public subject fields')
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
    return value
