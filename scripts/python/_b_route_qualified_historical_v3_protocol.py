"""Closed DATA predicates shared by the real history worker and cold reader.

These functions issue no history/Action token and never authenticate a caller
native dictionary. The worker supplies only same-read original checked bytes.
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
