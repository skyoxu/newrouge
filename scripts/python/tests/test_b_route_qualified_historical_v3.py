"""Self-contained DATA/negative API tests; never real native/semantic authority.

No legacy test imports, file fixture, prepare, counter, child or model seam.
The one genuine v3-history acceptance is separately pending real proof3 + Root epoch.
"""
from copy import deepcopy
import unittest
import argparse
import b_route_adoption as public_cli
import json
import base64
from pathlib import Path
from fixtures.codex_app_server_protocol import protocol as transcript, encoded
import _codex_app_server as transport
from _planning_execution_binding import receipt_from, validate_execution
import _b_route_codec as codec
import _b_route_adoption as adoption
import _b_route_qualified_historical_v3_protocol as protocol
import _b_route_qualified_history_host_v3 as host
import _b_route_qualified_public_history_v2 as public


def data():
    request={'schema_version':'newrouge.b-route-adoption-request.v2','operation_id':'DATA-ONLY',
             'review_profile':protocol.PROFILE,'material':{'fixture':'data-only'},
             'review_ref':{'fixture':'data-only'}}
    epoch={'source_root':'data-only-r22','source_commit':'data-only',
           'reader_path':'data-only-original-r52-reader','reader_raw_digest':'sha256:'+'1'*64}
    execution={'execution_epoch':epoch,'execution_reused':True,'new_native_executions':0,
               'raw_pins':{'data-only':'sha256:'+'2'*64},'whole_original_transport_fact':'data-only'}
    capsule={'native_capture':{'source_identity':deepcopy(epoch)},
             'target_identity':{'path':'data-only-target','device':1,'inode':2},
             'source':{'path':'data-only.txt','text':'complete data only','raw_digest':'sha256:'+'3'*64}}
    subject={'schema_version':protocol.SUBJECT,'request':deepcopy(request),'origin_capsule':capsule,
             'policy_identity':'sha256:'+'4'*64,'target_dependencies':{'data-only.txt':'sha256:'+'3'*64}}
    value={'schema_version':protocol.BINDING,'operation_id':'DATA-ONLY','target_root':'data-only-target',
        'request_ref':'data-only/request.json','request_raw_digest':'sha256:'+'5'*64,
        'request_body_digest':codec.canonical_digest(request),'material':deepcopy(request['material']),
        'review_ref':deepcopy(request['review_ref']),'execution':deepcopy(execution),
        'origin_capsule_digest':codec.canonical_digest(capsule),
        'target_authority':{'identity':deepcopy(capsule['target_identity']),'source':deepcopy(capsule['source']),
                            'files':deepcopy(subject['target_dependencies']),'directories':{'data-only-dir':[]}},
        'consumer_source_root':'data-only-r56','consumer_rule':'sha256:'+'6'*64,
        'consumer_policy_identity':subject['policy_identity'],'formal_adoption':False,
        'readiness':False,'runtime_verified':False}
    kwargs={'operation_id':'DATA-ONLY','target_root':'data-only-target','request_ref':'data-only/request.json',
        'request_raw_digest':'sha256:'+'5'*64,'request':request,'subject':subject,
        'consumer_root':'data-only-r56','consumer_rule':'sha256:'+'6'*64,'execution':execution}
    return value,kwargs


class HistoricalV3AdapterDataTests(unittest.TestCase):
    def test_original2_and_explicit3_route_as_distinct_families(self):
        request={'schema_version':'newrouge.b-route-adoption-request.v2',
                 'host_review_ref':{'schema_version':'newrouge.b-route-adoption-review-proof.v2'}}
        operation={'schema_version':'newrouge.b-route-adoption-operation.v2','frozen':{'request':request}}
        self.assertEqual('v2',protocol.family(operation))
        request['review_profile']=protocol.PROFILE;request['host_review_ref']['schema_version']=protocol.PROOF
        self.assertEqual('v3',protocol.family(operation))

    def test_unknown_mixed_missing_and_null_profile_never_downgrade(self):
        for profile,proof in ((None,protocol.PROOF),(protocol.PROFILE,'newrouge.b-route-adoption-review-proof.v2'),
                              (protocol.PROFILE,'newrouge.b-route-adoption-review-proof.v99')):
            with self.subTest(profile=profile,proof=proof):
                request={'schema_version':'newrouge.b-route-adoption-request.v2',
                         'host_review_ref':{'schema_version':proof}}
                if profile is not None:request['review_profile']=profile
                with self.assertRaises(ValueError):protocol.family({'schema_version':
                    'newrouge.b-route-adoption-operation.v2','frozen':{'request':request}})
        request={'schema_version':'newrouge.b-route-adoption-request.v2','review_profile':None,
                 'host_review_ref':{'schema_version':'newrouge.b-route-adoption-review-proof.v2'}}
        with self.assertRaises(ValueError):protocol.family({'schema_version':
            'newrouge.b-route-adoption-operation.v2','frozen':{'request':request}})

    def test_complete_binding2_is_only_data_not_an_opaque_proof(self):
        value,kwargs=data()
        self.assertIs(value,protocol.check_retained(value,**kwargs))
        with self.assertRaises(ValueError):host.AuthenticatedHistory(object(),value)
        with self.assertRaises(ValueError):public._checked(None,None,value)

    def test_missing_unknown_or_old_binding_schema_rejected(self):
        for change in ('missing','unknown','old'):
            value,kwargs=data()
            if change=='missing':del value['consumer_source_root']
            elif change=='unknown':value['extra']='not allowed'
            else:value['schema_version']='newrouge.b-route-retained-native-execution-binding.v1'
            with self.subTest(change=change),self.assertRaises(ValueError):protocol.check_retained(value,**kwargs)

    def test_consumer_rule_policy_and_actual_path_drift_rejected(self):
        for name in ('consumer_source_root','consumer_rule','consumer_policy_identity'):
            value,kwargs=data();value[name]='changed-or-old-r52'
            with self.subTest(name=name),self.assertRaises(ValueError):protocol.check_retained(value,**kwargs)

    def test_whole_producer_execution_and_reader_identity_drift_rejected(self):
        for change in ('reader','other-fact','pins'):
            value,kwargs=data()
            if change=='reader':value['execution']['execution_epoch']['reader_path']='current-r56-is-not-original-r52'
            elif change=='other-fact':value['execution']['whole_original_transport_fact']='changed'
            else:value['execution']['raw_pins']['data-only']='sha256:'+'0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):protocol.check_retained(value,**kwargs)

    def test_original_request_capsule_and_target_dependency_drift_rejected(self):
        for name in ('request_raw_digest','request_body_digest','origin_capsule_digest','target-file'):
            value,kwargs=data()
            if name=='target-file':value['target_authority']['files']['unbound.txt']='sha256:'+'7'*64
            else:value[name]='sha256:'+'0'*64
            with self.subTest(name=name),self.assertRaises(ValueError):protocol.check_retained(value,**kwargs)

    def test_history_cannot_add_grants_or_replace_strict_boolean_flags(self):
        for name in ('formal_adoption','readiness','runtime_verified'):
            for bad in (True,0):
                value,kwargs=data();value[name]=bad
                with self.subTest(name=name,bad=bad),self.assertRaises(ValueError):protocol.check_retained(value,**kwargs)


def offline_protocol_data():
    """Pure fixture bytes, not a child receipt or actual native/model qualification."""
    workspace=Path('offline-historical-v3-data-workspace')
    prompt='COMPLETE fixture-only serialized model input, including wrapper and outputSchema identity'
    schema={'type':'object','additionalProperties':False,'properties':{'schema_version':
        {'const':'newrouge.b-route-adoption-review-verdict.v3'},'value':{'const':'complete data'}},
        'required':['schema_version','value']}
    output=json.dumps({'schema_version':'newrouge.b-route-adoption-review-verdict.v3','value':'complete data'},separators=(',',':'))
    rows=transcript(workspace,prompt=prompt,output=output,schema=schema,provider='openai')
    for row in rows:
        message=row['message']
        if row['direction']=='client' and message.get('method')=='thread/start':
            message['params']['config']['model_reasoning_effort']='high'
    text,proof=transport.replay(encoded(rows))
    receipt={'schema_version':'newrouge.isolated-model-runner-receipt.v1','model':proof['model'],
        'model_provider':proof['model_provider'],'model_identity':'openai/'+proof['model'],
        'model_identity_source':transport.SOURCE,'model_identity_scope':'runtime_configuration',
        'evidence_policy':transport.POLICY,'runtime_identity_verified':True,'model_identity_verified':False,
        'provider_identity_verified':False,'provider_reported_model':None,'provider_dispatch_count':'unknown',
        'model_identity_evidence':[proof],'model_tools':[],'request_count_observable':True,
        'model_request_count':1,'runner_invocations':1,'workspace':workspace.as_posix(),'output_chars':len(text)}
    stdout=json.dumps(receipt)+'\n'
    execution={'status':'completed','returncode':0,'runner_dispatch_count':1,'active_elapsed_seconds':1.0,
               'stdout':stdout,'stdout_base64':base64.b64encode(stdout.encode()).decode()}
    return workspace,prompt,schema,text.encode(),execution


class HistoricalV3OfflineProtocolDataTests(unittest.TestCase):
    def test_original_binder_replays_complete_high_data_without_provider_identity_claim(self):
        workspace,prompt,schema,output,execution=offline_protocol_data()
        receipt=receipt_from(execution)
        validate_execution(workspace,execution,receipt,'auto',output,prompt=prompt,schema=schema,
                           require_runtime=True,expected_reasoning_effort='high')
        self.assertIs(receipt['provider_identity_verified'],False)
        self.assertIsNone(receipt['provider_reported_model'])
        self.assertEqual('unknown',receipt['provider_dispatch_count'])
        with self.assertRaises(ValueError):host.AuthenticatedHistory(object(),receipt)

    def test_original_binder_rejects_complete_input_schema_output_and_runtime_drift(self):
        for kind in ('input','schema','output','runtime','provider-claim'):
            workspace,prompt,schema,output,execution=offline_protocol_data()
            if kind=='input':prompt+=' omitted-or-changed'
            elif kind=='schema':schema=deepcopy(schema);schema['required']=['schema_version']
            elif kind=='output':output+=b' '
            else:
                receipt=receipt_from(execution)
                if kind=='runtime':receipt['model_identity_evidence'][0]['runtime_reasoning_effort']='low'
                else:receipt['provider_identity_verified']=True
                stdout=json.dumps(receipt)+'\n';execution['stdout']=stdout
                execution['stdout_base64']=base64.b64encode(stdout.encode()).decode()
            expected_error=ValueError if kind in ('input','schema') else codec.CodecError
            with self.subTest(kind=kind),self.assertRaises(expected_error) as caught:
                validate_execution(workspace,execution,receipt_from(execution),'auto',output,
                    prompt=prompt,schema=schema,require_runtime=True,expected_reasoning_effort='high')
            if kind in ('input','schema'):
                self.assertIs(type(caught.exception),ValueError)
                reason='input_mismatch' if kind=='input' else 'output_schema_mismatch'
                self.assertEqual('codex_app_server_'+reason,str(caught.exception))


class HistoricalV3PublicDataTests(unittest.TestCase):
    def test_missing_or_private_protection_fields_never_form_a_public_view(self):
        for value in ({},{'private_raw_base64':'never a public semantic field'}):
            with self.subTest(value=value),self.assertRaises(ValueError):public._validate_protection_view(value)

    def test_genuine_history_handle_cannot_be_replaced_by_complete_looking_public_dict(self):
        value={'schema_version':public.PUBLICS[1],'native_content':{'complete':'DATA ONLY'}}
        with self.assertRaises(ValueError):public._checked(None,None,value)


class HistoricalV3VersionPairTests(unittest.TestCase):
    def test_original_private_public_versions_are_paired_without_upgrade(self):
        for version in (2,3):
            protocol.check_subject_family('newrouge.b-route-adoption-review-subject.v'+str(version),
                                          'newrouge.b-route-adoption-model-subject.v'+str(version))
        for private,visible in ((2,3),(3,2),(3,99),(99,3)):
            with self.subTest(private=private,visible=visible),self.assertRaises(ValueError):
                protocol.check_subject_family('newrouge.b-route-adoption-review-subject.v'+str(private),
                                              'newrouge.b-route-adoption-model-subject.v'+str(visible))


class HistoricalV3PublicSelectorTests(unittest.TestCase):
    def test_public_delivery2_is_explicit_and_legacy_default_choices_remain(self):
        for delivery in (None,'newrouge.b-route-compensation-review-delivery.v3',
                'newrouge.b-route-compensation-review-delivery.v4',
                'newrouge.b-route-qualified-compensation-review-delivery.v1',
                'newrouge.b-route-qualified-compensation-review-delivery.v2'):
            parser=argparse.ArgumentParser();public_cli.register_arguments(parser)
            args=['--stage','review-prepare','--operation-id','DATA-ONLY','--request','logs/ci/data-only.json']
            if delivery is not None:args+=['--compensation-review-delivery',delivery]
            with self.subTest(delivery=delivery):
                parsed=parser.parse_args(args)
                self.assertEqual(delivery,parsed.compensation_review_delivery)


class HistoricalV3FreshOwnerBoundaryTests(unittest.TestCase):
    def test_r55_cannot_mislabel_a_fresh_v2_review_as_expanded3_before_capture(self):
        request={'schema_version':'newrouge.b-route-adoption-request.v2','operation_id':'DATA-ONLY',
                 'review_profile':'expanded-semantics.v3'}
        # The original early guard executes before inventory, locks, Snapshot,
        # target I/O or native/model capture. This is a rejection, no authority.
        with self.assertRaises(codec.CodecError) as caught:
            adoption._review_preview(Path('DATA-ONLY-NOT-READ'),request)
        self.assertEqual('fresh expanded-semantics.v3 review belongs to real R56 owner; R55 historical consumption is separate',
                         caught.exception.diagnostic.expected)


class HistoricalPlanProofRoleDataTests(unittest.TestCase):
    """Locator role DATA only; no fake history, native or public prepare grant."""

    def locators(self):
        path = 'logs/ci/data-only/capsule.json'
        proof = {'owner': 'planning_proof', 'ref': path,
                 'files': [{'path': path, 'raw_digest': 'sha256:' + '1' * 64}]}
        native = {**deepcopy(proof), 'ref': path + '#/proposal/content'}
        return proof, native

    def test_original_plan_proof_anchor_keeps_the_explicit_native_fragment(self):
        proof, native = self.locators()
        for fields in ((('adoption_proof_refs', [proof]), ('native_candidate_ref', native)),
                       (('native_candidate_ref', native), ('adoption_proof_refs', [proof]))):
            record = {'schema_version': 'newrouge.b-route-plan.v1', **dict(fields)}
            with self.subTest(order=list(record)):
                self.assertTrue(public._plan_adoption_proof_use(record, proof))
                self.assertFalse(public._plan_adoption_proof_use(record, native))
                self.assertEqual(native, record['native_candidate_ref'])

    def test_proof_anchor_cannot_hide_the_same_locator_in_semantic_fields(self):
        proof, native = self.locators()
        for field, value in (('native_candidate_ref', proof),
                             ('evidence_source_refs', [proof]),
                             ('source_identity', {'nested': deepcopy(proof)})):
            record = {'schema_version': 'newrouge.b-route-plan.v1',
                      'adoption_proof_refs': [proof], 'native_candidate_ref': native, field: value}
            with self.subTest(field=field):
                self.assertFalse(public._plan_adoption_proof_use(record, proof))

    def test_other_records_and_nonproof_locations_do_not_gain_the_exception(self):
        proof, native = self.locators()
        for record in ({'schema_version': 'newrouge.b-route-binding.v1', 'adoption_proof_refs': [proof]},
                       {'schema_version': 'newrouge.b-route-plan.v1', 'native_candidate_ref': proof},
                       {'schema_version': 'newrouge.b-route-plan.v1', 'adoption_proof_refs': [native]},
                       {'schema_version': 'newrouge.b-route-plan.v1', 'nested': {'adoption_proof_refs': [proof]}}):
            with self.subTest(record=record):
                self.assertFalse(public._plan_adoption_proof_use(record, proof))

    def test_bare_and_unknown_opaque_mappings_still_fail_cold_validation(self):
        import _b_route_qualified_compensation_materials_v2 as materials
        digest = 'sha256:' + '2' * 64
        path = 'logs/ci/data-only/capsule.json'
        source = 'docs/planning/b-route/plans/DATA-ONLY/1.json'
        for suffix in ('#/origin_admission', '', '#/unknown'):
            mapping = {name: digest for name in ('frame_digest', 'historical_subject_digest',
                'historical_public_digest', 'historical_auth_digest', 'candidate_digest',
                'carrier_raw_digest', 'source_record_raw_digest')}
            mapping.update(schema_version=public.MAPPING, claim=materials.CLAIM,
                carrier_path=path, carrier_raw_bytes=1, owner='planning_proof', ref=path + suffix,
                source_record=source, public_pointer=None, role='host:qualified_origin_proof',
                kind='qualified_opaque')
            row = {'path': path, 'raw_digest': digest, 'raw_bytes': 1, 'owner_uses': [
                {'owner': 'planning_proof', 'ref': path + suffix, 'source': source,
                 'subject_digest': digest}]}
            with self.subTest(suffix=suffix):
                if suffix == '#/origin_admission':
                    materials._validate_mapping(mapping, row, None)
                else:
                    with self.assertRaises(ValueError):
                        materials._validate_mapping(mapping, row, None)
