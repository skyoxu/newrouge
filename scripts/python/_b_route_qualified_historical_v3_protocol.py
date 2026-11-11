"""Closed DATA predicates shared by the real history worker and cold reader.

These functions issue no history/Action token and never authenticate a caller
native dictionary. The worker supplies only same-read original checked bytes.
Offline saved-review checks return DATA observations only, never owner authority.
"""
import _b_route_codec as codec

PROFILE = 'expanded-semantics.v3'
SUBJECT = 'newrouge.b-route-adoption-review-subject.v3'
PROOF = 'newrouge.b-route-adoption-review-proof.v3'
PUBLIC = 'newrouge.b-route-adoption-model-subject.v3'
BINDING = 'newrouge.b-route-retained-native-execution-binding.v2'


def need(value, message):
    if not value:
        raise ValueError(message)


def family(operation):
    """Data routing only; authenticate() separately reads the actual journal."""
    need(type(operation) is dict and operation.get('schema_version') ==
         'newrouge.b-route-adoption-operation.v2', 'known original adoption operation')
    request = operation['frozen']['request']
    need(request.get('schema_version') == 'newrouge.b-route-adoption-request.v2',
         'exact original adoption request')
    proof = request.get('host_review_ref', {}).get('schema_version')
    if proof == PROOF:
        need(request.get('review_profile') == PROFILE, 'proof3 requires explicit profile3')
        return 'v3'
    need(proof == 'newrouge.b-route-adoption-review-proof.v2'
         and 'review_profile' not in request, 'old proof2 stays original profile-less v2; unknown/mixed rejected')
    return 'v2'


def check_retained(value, *, operation_id, target_root, request_ref, request_raw_digest,
                   request, subject, consumer_root, consumer_rule, execution):
    """Schema/binding predicate only, never an archive or native authenticator."""
    need(type(value) is dict and set(value) == {
        'schema_version','operation_id','target_root','request_ref','request_raw_digest',
        'request_body_digest','material','review_ref','execution','origin_capsule_digest',
        'target_authority','consumer_source_root','consumer_rule','consumer_policy_identity',
        'formal_adoption','readiness','runtime_verified'}, 'closed historical binding2')
    need(value['schema_version']==BINDING and value['operation_id']==operation_id
         and value['target_root']==target_root and value['request_ref']==request_ref
         and value['request_raw_digest']==request_raw_digest, 'same actual operation/target/original request raw')
    need(subject['schema_version']==SUBJECT and request.get('review_profile')==PROFILE
         and 'host_review_ref' not in request and subject['request']==request,
         'original unsealed profile3 request, not an old ticket upgrade')
    need(value['request_body_digest']==codec.canonical_digest(request)
         and value['material']==request['material'] and value['review_ref']==request['review_ref']
         and value['origin_capsule_digest']==codec.canonical_digest(subject['origin_capsule']),
         'whole actual request/material/capsule binding')
    need(value['consumer_source_root']==consumer_root and value['consumer_rule']==consumer_rule
         and value['consumer_policy_identity']==subject['policy_identity'],
         'actual R56 v3 source/policy consumer identity')
    need(codec.canonical_digest(value['execution'])==codec.canonical_digest(execution)
         and execution['execution_epoch']==subject['origin_capsule']['native_capture']['source_identity']
         and execution['execution_reused'] is True
         and type(execution['new_native_executions']) is int and execution['new_native_executions']==0,
         'whole genuine producer archive/held execution, not just matching epoch labels')
    need(all(value[k] is False for k in ('formal_adoption','readiness','runtime_verified')),
         'historical execution has no adoption/readiness/runtime grant')
    target = value['target_authority']
    need(type(target) is dict and set(target)=={'identity','source','files','directories'}
         and target['identity']==subject['origin_capsule']['target_identity']
         and target['source']==subject['origin_capsule']['source']
         and type(target['files']) is dict and type(target['directories']) is dict,
         'closed original target authority observation')
    need(all(name in subject['target_dependencies'] and subject['target_dependencies'][name]==pin
             for name,pin in target['files'].items()), 'original target files included in runtime-bound private subject')
    for name, members in target['directories'].items():
        codec.validate_reference_path(name)
        need(type(members) is list and all(type(row) is str for row in members)
             and len(members)==len(set(members)), 'closed historical directory observation, never fresh membership')
        for member in members:codec.validate_reference_path(member)
    return value


def check_subject_family(private_schema, public_schema):
    need((private_schema,public_schema) in {
        ('newrouge.b-route-adoption-review-subject.v2','newrouge.b-route-adoption-model-subject.v2'),
        ('newrouge.b-route-adoption-review-subject.v3','newrouge.b-route-adoption-model-subject.v3')},
        'exact original private/public version pair; no relabelled/mixed old ticket')


SAVED_SUPPORT = ('subject.json', 'w/prompt.txt', 'w/schema.json', 'request.txt',
                 'execution.json', 'w/output.json')


def check_saved_review_bindings(operation, buffers):
    """Replay supplied review bytes without authenticating their owner or origin.

    A self-consistent fabricated bundle can pass these DATA checks. No opaque
    handle is issued, and this result cannot replace authenticate/verify_capture.
    Original policy/renderer/native eligibility remain separate obligations.
    """
    import base64
    from copy import deepcopy
    import hashlib
    from pathlib import Path, PureWindowsPath
    import jsonschema
    from _planning_execution_binding import receipt_from, validate_execution

    need(family(operation) == 'v3', 'explicit original proof3 family')
    need(set(buffers) == {*SAVED_SUPPORT, 'review.json'}
         and all(type(value) is bytes for value in buffers.values()), 'complete exact saved review buffers')
    operation_id = codec.validate_business_id(operation['operation_id'])
    home = 'logs/ci/b-route-adoption-reviews/' + hashlib.sha256(operation_id.encode('utf-8')).hexdigest()
    request_raw = base64.b64decode(operation['request_raw_base64'], validate=True)
    request = codec.strict_json_loads(request_raw)
    need(codec.raw_digest(request_raw) == operation['request_raw_digest']
         and codec.canonical_digest(request) == operation['request_digest']
         and request == operation['frozen']['request'], 'exact embedded sealed operation request')
    ref = request['host_review_ref']
    need(ref == {'path': home + '/review.json', 'schema_version': PROOF,
                 'raw_digest': codec.raw_digest(buffers['review.json'])}, 'original proof raw reference')
    proof = codec.strict_json_loads(buffers['review.json'])
    subject = codec.strict_json_loads(buffers['subject.json'])
    need(set(proof) == {'schema_version', 'operation_id', 'subject_digest', 'policy_identity',
                       'mode', 'evidence', 'files'}, 'closed original saved proof data')
    need(proof['schema_version'] == PROOF and subject['schema_version'] == SUBJECT
         and proof['operation_id'] == subject['operation_id'] == operation_id
         and proof['subject_digest'] == codec.canonical_digest(subject)
         and proof['policy_identity'] == subject['policy_identity']
         and proof['mode'] == 'semantic'
         and subject['request'] == {key: value for key, value in request.items() if key != 'host_review_ref'},
         'same original subject, request and recorded policy identity')
    refs = [{'path': home + '/' + name, 'schema_version': 'raw.bytes.v1',
             'raw_digest': codec.raw_digest(buffers[name])} for name in SAVED_SUPPORT]
    need(proof['files'] == refs, 'complete original ordered support raw bindings')
    frozen = deepcopy(subject['preview'])
    frozen['request'] = request
    frozen['authority_refs'] = sorted([*frozen['authority_refs'], ref, *refs], key=lambda row: row['path'])
    need(codec.canonical_digest(frozen) == operation['frozen_digest']
         == codec.canonical_digest(operation['frozen']), 'complete original frozen preview and support')
    execution = codec.strict_json_loads(buffers['execution.json'])
    receipt = receipt_from(execution)
    command = execution['command']
    need(type(command) is list and command.count('--workspace') == 1, 'one recorded historical workspace argument')
    historical_workspace = PureWindowsPath(command[command.index('--workspace') + 1]).as_posix()
    need(receipt['workspace'] == historical_workspace, 'recorded command/receipt workspace correspondence')
    schema = codec.strict_json_loads(buffers['w/schema.json'])
    output = codec.strict_json_loads(buffers['w/output.json'])
    jsonschema.Draft202012Validator(schema).validate(output)
    validate_execution(Path(historical_workspace), execution, receipt, 'auto', buffers['w/output.json'],
        prompt=buffers['request.txt'].decode('utf-8'), schema=schema,
        require_runtime=True, expected_reasoning_effort='high')
    runtime = receipt['model_identity_evidence'][0]
    need(runtime['model_provider'] == 'openai' and runtime['thread_id'] not in subject['native_threads'],
         'recorded independent official runtime configuration')
    evidence = {'thread_id': runtime['thread_id'], 'turn_id': runtime['turn_id'],
        'protocol_digest': runtime['protocol_sha256'], 'runtime_configuration': {
            'model': runtime['model'], 'provider': runtime['model_provider'], 'reasoning_effort': 'high'},
        'provider_actual_model': 'unknown', 'physical_requests': 'unknown'}
    need(codec.canonical_digest(evidence) == codec.canonical_digest(proof['evidence']),
         'complete saved proof/runtime data correspondence')
    return {'schema_version': 'newrouge.b-route-saved-review-bindings-data.v1',
        'operation_id': operation_id, 'subject_digest': proof['subject_digest'],
        'frozen_digest': operation['frozen_digest'], 'recorded_policy_identity': proof['policy_identity'],
        'support_raw_bindings_checked': True, 'saved_schema_and_protocol_replayed': True,
        'recorded_verdict': output.get('verdict'), 'historical_workspace': historical_workspace,
        'original_policy_reconstructed': False, 'original_owner_execution_authenticated': False,
        'original_native_execution_authenticated': False, 'new_authority_granted': False,
        'eligible_for_compensation': False}
