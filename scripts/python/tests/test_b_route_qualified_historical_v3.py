"""Self-contained DATA/negative API tests; never real native/semantic authority.

No legacy test imports, prepare, counter, fabricated child result or model seam.
Installation tests supply config bytes only and require no reader release.
The one genuine v3-history acceptance is separately pending real proof3 + Root epoch.
"""
from copy import deepcopy
import unittest
import argparse
import b_route_adoption as public_cli
import json
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from fixtures.codex_app_server_protocol import protocol as transcript, encoded
import _codex_app_server as transport
from _planning_execution_binding import receipt_from, validate_execution
import _b_route_codec as codec
import _b_route_adoption as adoption
import _b_route_qualified_historical_v3_protocol as protocol
import _b_route_qualified_history_host_v3 as host
import _b_route_qualified_public_history_v2 as public


class HistoricalV3OwnerInstallationTests(unittest.TestCase):
    def template(self):
        return {'schema_version': 'newrouge.b-route-qualified-historical-owner-authority.v2',
            'original_owner_root': None, 'source_schema_pins': None, 'python_version': None,
            'python_executable': None, 'python_executable_raw_digest': None,
            'scope': 'Fixture: installation input only',
            'dependency_authority': 'Fixture: existing managed dependency owner',
            'producer_reader': None}

    def test_uninstalled_template_reports_dependency_without_releasing_reader(self):
        raw = json.dumps(self.template()).encode('utf-8')
        with mock.patch.object(host, '_safe', return_value=SimpleNamespace(read_bytes=lambda: raw)), \
                mock.patch.object(host, 'run_reader') as reader:
            with self.assertRaises(codec.CodecError) as caught:
                host.authenticate(Path('DATA-ONLY-NOT-READ'), 'DATA-ONLY')
        diagnostic = caught.exception.diagnostic
        self.assertEqual(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, diagnostic.reason_code)
        self.assertEqual('DATA-ONLY', diagnostic.entity_id)
        self.assertEqual(str(Path(host.__file__).absolute().with_name(
            'qualified-historical-owner-authority.v2.json')), diagnostic.resume_ref)
        self.assertEqual(sorted(['original_owner_root', 'source_schema_pins', 'python_version',
            'python_executable', 'python_executable_raw_digest', 'producer_reader']),
            diagnostic.actual['missing_installation_fields'])
        self.assertIs(diagnostic.actual['historical_evidence_checked'], False)
        reader.assert_not_called()

    def test_mixed_or_invalid_owner_is_not_reported_as_uninstalled_template(self):
        for case in ('unknown-schema', 'extra-key', 'mixed-input', 'wrong-nonnull-owner'):
            value = self.template()
            if case == 'unknown-schema': value['schema_version'] += '.unknown'
            elif case == 'extra-key': value['extra'] = None
            elif case == 'mixed-input': value['python_executable_raw_digest'] = 'wrong'
            else:
                value.update(original_owner_root='wrong-owner', source_schema_pins={'wrong': 'wrong'},
                    python_version='wrong', python_executable='wrong', python_executable_raw_digest='wrong')
            raw = json.dumps(value).encode('utf-8')
            with self.subTest(case=case), \
                    mock.patch.object(host, '_safe', return_value=SimpleNamespace(read_bytes=lambda: raw)), \
                    mock.patch.object(host, 'run_reader') as reader:
                with self.assertRaises(ValueError) as caught:
                    host.authenticate(Path('DATA-ONLY-NOT-READ'), 'DATA-ONLY')
                self.assertIs(type(caught.exception), ValueError)
                reader.assert_not_called()


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


def saved_review_fixture():
    """A deliberately synthetic bundle that must never grant owner authority."""
    import hashlib
    workspace, prompt, schema, output, execution = offline_protocol_data()
    execution['command'] = ['historical-python', 'historical-runner', '--workspace', workspace.as_posix()]
    request = {'schema_version': 'newrouge.b-route-adoption-request.v2', 'operation_id': 'DATA-ONLY',
               'review_profile': protocol.PROFILE}
    subject = {'schema_version': protocol.SUBJECT, 'operation_id': 'DATA-ONLY', 'request': request,
        'policy_identity': 'sha256:' + '4' * 64, 'preview': {'authority_refs': []}, 'native_threads': []}
    raw = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    runtime = receipt_from(execution)['model_identity_evidence'][0]
    proof = {'schema_version': protocol.PROOF, 'operation_id': 'DATA-ONLY',
        'subject_digest': codec.canonical_digest(subject), 'policy_identity': subject['policy_identity'],
        'mode': 'semantic', 'evidence': {'thread_id': runtime['thread_id'], 'turn_id': runtime['turn_id'],
            'protocol_digest': runtime['protocol_sha256'], 'runtime_configuration': {'model': runtime['model'],
                'provider': runtime['model_provider'], 'reasoning_effort': 'high'},
            'provider_actual_model': 'unknown', 'physical_requests': 'unknown'}, 'files': []}
    buffers = {'subject.json': raw(subject), 'w/prompt.txt': b'Fixture original prompt',
        'w/schema.json': raw(schema), 'request.txt': prompt.encode('utf-8'),
        'execution.json': raw(execution), 'w/output.json': output, 'review.json': raw(proof)}
    operation = {'schema_version': 'newrouge.b-route-adoption-operation.v2', 'operation_id': 'DATA-ONLY'}
    return rebind_saved_review_fixture(operation, buffers)


def rebind_saved_review_fixture(operation, buffers, *, reverse_support=False):
    import hashlib
    raw = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    home = 'logs/ci/b-route-adoption-reviews/' + hashlib.sha256(b'DATA-ONLY').hexdigest()
    proof = codec.strict_json_loads(buffers['review.json'])
    proof['files'] = [{'path': home + '/' + name, 'schema_version': 'raw.bytes.v1',
        'raw_digest': codec.raw_digest(buffers[name])} for name in protocol.SAVED_SUPPORT]
    if reverse_support: proof['files'].reverse()
    buffers['review.json'] = raw(proof)
    ref = {'path': home + '/review.json', 'schema_version': protocol.PROOF,
           'raw_digest': codec.raw_digest(buffers['review.json'])}
    subject = codec.strict_json_loads(buffers['subject.json'])
    request = {**subject['request'], 'host_review_ref': ref}
    frozen = deepcopy(subject['preview']); frozen['request'] = request
    frozen['authority_refs'] = sorted([*frozen['authority_refs'], ref, *proof['files']], key=lambda row: row['path'])
    request_raw = raw(request)
    operation.update(request_raw_base64=base64.b64encode(request_raw).decode('ascii'),
        request_raw_digest=codec.raw_digest(request_raw), request_digest=codec.canonical_digest(request),
        frozen=frozen, frozen_digest=codec.canonical_digest(frozen))
    return operation, buffers


class HistoricalV3SavedReviewDataTests(unittest.TestCase):
    def test_consistent_synthetic_data_cannot_authenticate_owner_or_grant_compensation(self):
        operation, buffers = saved_review_fixture()
        report = protocol.check_saved_review_bindings(operation, buffers)
        self.assertIs(report['saved_schema_and_protocol_replayed'], True)
        for key in ('original_policy_reconstructed', 'original_owner_execution_authenticated',
                    'original_native_execution_authenticated', 'new_authority_granted', 'eligible_for_compensation'):
            self.assertIs(report[key], False)
        with self.assertRaises(ValueError): host.AuthenticatedHistory(object(), report)

    def test_rehashed_output_drift_is_rejected_by_full_protocol_replay(self):
        operation, buffers = saved_review_fixture()
        buffers['w/output.json'] += b' '
        rebind_saved_review_fixture(operation, buffers)
        with self.assertRaises(ValueError): protocol.check_saved_review_bindings(operation, buffers)

    def test_complete_support_order_and_recorded_workspace_are_checked(self):
        for case in ('order', 'workspace'):
            operation, buffers = saved_review_fixture()
            if case == 'workspace':
                execution = codec.strict_json_loads(buffers['execution.json'])
                execution['command'][-1] = 'changed-workspace'
                buffers['execution.json'] = json.dumps(execution).encode('utf-8')
            rebind_saved_review_fixture(operation, buffers, reverse_support=case == 'order')
            with self.subTest(case=case), self.assertRaises(ValueError):
                protocol.check_saved_review_bindings(operation, buffers)

    def test_unsealed_request_cannot_replace_the_embedded_sealed_operation_request(self):
        operation, buffers = saved_review_fixture()
        unsealed = codec.strict_json_loads(buffers['subject.json'])['request']
        raw = json.dumps(unsealed).encode('utf-8')
        operation.update(request_raw_base64=base64.b64encode(raw).decode('ascii'),
            request_raw_digest=codec.raw_digest(raw), request_digest=codec.canonical_digest(unsealed))
        with self.assertRaises(ValueError): protocol.check_saved_review_bindings(operation, buffers)


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


class CurrentSourceSetRoleDataTests(unittest.TestCase):
    """Current/historical role DATA only, never an authenticated history."""

    def data(self, current_value=None):
        original = {'schema_version': 'chapter3.source-set.v1', 'active_patterns': [public.SOURCE],
                    'active_sources': [public.SOURCE], 'retirements': []}
        original_raw = public.raw(original)
        current_raw = public.raw(original if current_value is None else current_value)
        name = 'docs/workflows/chapter3-source-set.json'
        receipt = 'docs/planning/b-route/commits/DATA-ONLY.json'
        digest = codec.raw_digest(current_raw)
        frames = {'DATA-ONLY': {'subject_schema': 'newrouge.b-route-adoption-review-subject.v3',
            'operation_id': 'DATA-ONLY', 'semantic_fields': {'schema_version': public.PUBLICS[1],
            'review_scope': {'source_set': {'path': name, 'raw_digest': codec.raw_digest(original_raw),
                                          'value': original}}}}}
        preview = {'scope_ids': ['scope'], 'authority_refs': [
            {'path': name, 'schema_version': 'raw.bytes.v1', 'raw_digest': digest}]}
        import _b_route_records as records
        formal = {records.CATALOG_PATH: {'scope_heads': [
            {'scope_id': 'scope', 'receipt_ref': {'path': receipt}}]},
            receipt: {'schema_version': 'newrouge.b-route-commit.v1', 'authority': [
                {'path': name, 'before_digest': digest, 'after_digest': digest}]}}
        self.assertIn(formal[receipt]['schema_version'], codec.SCHEMA_IDENTITY_REGISTRY)
        return name, receipt, frames, preview, formal, {name: current_raw}

    def uses(self, frames, preview, formal, files):
        import _b_route_qualified_compensation_materials_v2 as materials
        self.charges = []
        return materials._current_source_set_uses(frames, preview, formal, files,
            lambda amount, phase: self.charges.append((amount, phase)))

    def test_complete_current_source_set_is_semantic_with_original_and_current_provenance(self):
        name, receipt, frames, preview, formal, files = self.data()
        before = dict(files)
        files['docs/unproven-source-set.json'] = files[name]
        result = self.uses(frames, preview, formal, files)
        from _b_route_adoption_review import location
        self.assertEqual(result, [(name, 'newrouge.b-route-adoption-review-subject.v3',
            location('DATA-ONLY') + '/subject.json#/registered_source_set', receipt)])
        self.assertEqual(files[name], before[name])
        self.assertTrue(self.charges)

    def test_consistent_current_bytes_are_not_replaced_with_the_historical_value(self):
        current = {'schema_version': 'chapter3.source-set.v1', 'active_patterns': [public.SOURCE, 'docs/new.md'],
                   'active_sources': [public.SOURCE, 'docs/new.md'], 'retirements': []}
        name, receipt, frames, preview, formal, files = self.data(current)
        # Consistent current DATA is not a new producer admission. The real
        # caller still needs the original current bundle and opaque history.
        expected = files[name]
        self.assertNotEqual(codec.raw_digest(expected),
                            frames['DATA-ONLY']['semantic_fields']['review_scope']['source_set']['raw_digest'])
        self.assertEqual(len(self.uses(frames, preview, formal, files)), 1)
        self.assertEqual(files[name], expected)
        self.assertEqual(codec.strict_json_loads(files[name]), current)

    def test_missing_or_changed_current_raw_cannot_inherit_the_role(self):
        for mutation in ('missing', 'changed'):
            name, _receipt, frames, preview, formal, files = self.data()
            if mutation == 'missing':
                del files[name]
            else:
                files[name] += b' '
            with self.subTest(mutation=mutation), self.assertRaises(codec.CodecError):
                self.uses(frames, preview, formal, files)

    def test_unbound_authority_unrelated_scope_and_other_owner_versions_do_not_grant_roles(self):
        for mutation in ('no-preview', 'wrong-receipt', 'unrelated', 'private-version', 'public-version'):
            _name, receipt, frames, preview, formal, files = self.data()
            if mutation == 'no-preview':
                preview['authority_refs'] = []
            elif mutation == 'wrong-receipt':
                formal[receipt]['authority'][0]['after_digest'] = 'sha256:' + '0' * 64
            elif mutation == 'unrelated':
                preview['scope_ids'] = ['other']
            elif mutation == 'private-version':
                frames['DATA-ONLY']['subject_schema'] = 'newrouge.b-route-adoption-review-subject.v2'
            else:
                frames['DATA-ONLY']['semantic_fields']['schema_version'] = public.PUBLICS[0]
            with self.subTest(mutation=mutation):
                self.assertEqual(self.uses(frames, preview, formal, files), [])
