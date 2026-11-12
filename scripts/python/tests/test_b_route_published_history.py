"""Focused publication/profile refusal tests; fixtures grant no actual authority."""
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace
from copy import deepcopy
import json
import shutil

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_published_history as published
import _b_route_qualified_history_host_v3 as original
import _b_route_qualified_compensation_review_v2 as review
import _b_route_compensation_review_profiles as profiles
import _planning_apply_journal as journal


class PublishedHistoryBoundaryTests(TestCase):
    def test_saved_proof_reference_must_match_its_actual_profile_version(self):
        import _b_route_adoption_review as owner
        request = {'operation_id': 'DATA'}
        subject = {'schema_version': profiles.PUBLISHED.name('subject'), 'operation_id': 'DATA',
                   'policy_identity': 'sha256:' + '1' * 64, 'request': dict(request)}
        proof = {key: 'synthetic-data' for key in ('materials_digest','roles_digest','presentation_digest',
                    'historical_auth_digest','request_raw_digest')}
        proof.update(schema_version=profiles.PUBLISHED.name('proof'), operation_id='DATA',
            subject_digest=codec.canonical_digest(subject),policy_identity=subject['policy_identity'],
            mode=profiles.PUBLISHED.mode,evidence={},files=[],claim=profiles.PUBLISHED.claim,
            delivery=profiles.PUBLISHED.name('delivery'))
        raw = owner.raw(proof)
        for version in (profiles.ORIGINAL, profiles.PUBLISHED):
            ref = {'path':owner.location('DATA')+'/review.json','schema_version':version.name('proof'),
                   'raw_digest':codec.raw_digest(raw)}
            with self.subTest(version=version.version), \
                 patch.object(owner,'path',return_value=SimpleNamespace(read_bytes=lambda:raw)), \
                 patch.object(review,'read_subject',return_value=subject), \
                 patch.object(review,'_inputs',return_value=SimpleNamespace(refs=[])) as inputs, \
                 patch.object(review,'_complete',return_value='synthetic-data'):
                if version is profiles.ORIGINAL:
                    with self.assertRaises(codec.CodecError):
                        review._verify_saved(Path('DATA'),{**request,'host_review_ref':ref})
                    inputs.assert_not_called()
                else:
                    review._verify_saved(Path('DATA'),{**request,'host_review_ref':ref})
                    inputs.assert_called_once()

    def test_published_profile_is_explicit_immutable_and_distinct(self):
        self.assertIs(profiles.PUBLISHED, profiles.select('delivery', profiles.PUBLISHED.name('delivery')))
        self.assertIs(profiles.ORIGINAL, profiles.select('delivery', profiles.ORIGINAL.name('delivery')))
        self.assertNotEqual(profiles.PUBLISHED.claim, profiles.ORIGINAL.claim)
        with self.assertRaises(FrozenInstanceError):
            profiles.PUBLISHED.version = 2
        with self.assertRaises(ValueError):
            profiles.select('delivery', profiles.PUBLISHED.name('delivery') + '.unknown')

    def test_neither_history_factory_accepts_a_saved_dictionary_as_a_token(self):
        with self.assertRaises(codec.CodecError):
            published.PublishedHistoryVerification(object(), None, None, None, None, None, None, None, None, None)
        with self.assertRaises(ValueError):
            original.AuthenticatedHistory(object(), {'approved': True})

    def test_complete_phase_and_reserved_row_without_publication_never_read_old_proof(self):
        operation = {'schema_version': 'newrouge.b-route-adoption-operation.v2', 'operation_id': 'DATA', 'state': 'reserved'}
        with patch.object(journal, 'read_operation', return_value=operation), \
             patch.object(codec, 'read_reference_bytes', return_value=b'{}') as read, \
             patch.object(commit, 'validate_local', return_value={'phase': 'complete'}), \
             patch.object(commit, 'terminal_valid', return_value=False), \
             patch.object(commit, '_publication_proven') as current, \
             patch.object(original, 'authenticate') as old:
            with self.assertRaises(codec.CodecError):
                published.verify(Path('DATA-NOT-A-REAL-ROOT'), 'DATA')
        self.assertEqual(1, read.call_count)
        current.assert_not_called()
        old.assert_not_called()

    def test_historical_terminal_does_not_substitute_for_current_formal_chain(self):
        operation = {'schema_version': 'newrouge.b-route-adoption-operation.v2', 'operation_id': 'DATA'}
        with patch.object(journal, 'read_operation', return_value=operation), \
             patch.object(codec, 'read_reference_bytes', return_value=b'{}') as read, \
             patch.object(commit, 'validate_local', return_value={'phase': 'complete'}), \
             patch.object(commit, 'terminal_valid', return_value=True), \
             patch.object(commit, '_publication_proven', return_value=False), \
             patch.object(original, 'authenticate') as old:
            with self.assertRaises(codec.CodecError):
                published.verify(Path('DATA-NOT-A-REAL-ROOT'), 'DATA')
        self.assertEqual(1, read.call_count)
        old.assert_not_called()

    def test_saved_current_before_requires_verified_scope_not_a_caller_dict(self):
        with self.assertRaises(codec.CodecError):
            published._saved_current_before(Path('DATA'), {}, {'approved': True})

    def test_private_reference_profile_cannot_be_changed_without_owner_binding(self):
        # No historical bytes are supplied: the conflicting version is refused
        # before a caller dictionary can become a saved owner capability.
        meta = {'schema_version': profiles.PUBLISHED.name('private-file') + '.unknown',
            'owner_operation_id': 'DATA', 'owner_subject_digest': 'sha256:' + '1' * 64,
            'owner_auth_digest': 'sha256:' + '2' * 64, 'kind': 'review_support',
            'role': 'host:proof', 'raw_digest': 'sha256:' + '3' * 64, 'raw_bytes': 1}
        with patch.object(review, 'history') as history:
            with self.assertRaises(ValueError):
                review.resolve_private_file(Path('DATA'), 'logs/ci/proof.json', meta)
        history.assert_not_called()


class PublishedRecoveryBeforeTests(TestCase):
    def test_repair_proof_before_view_retains_real_task_history_and_rejects_unknown_bytes(self):
        from _b_route_compensation_review_repair import PROOF
        self.test_real_formal_before_view_survives_owned_origins_after_and_rejects_unknown_bytes(proof_version=PROOF)

    def test_real_formal_before_view_survives_owned_origins_after_and_rejects_unknown_bytes(self,proof_version=None):
        """Actual formal/Task bytes; synthetic upstream bookkeeping, no model proof.

        This isolates the before-view helper from provider/tokenizer admission.
        It neither changes capacity checks nor creates a history handle.
        """
        import base64
        import tempfile
        import _b_route_adoption as adoption
        import _b_route_adoption_review as owner
        import _b_route_compensation as compensation
        import _b_route_commit_projection as projection
        import _b_route_records as records
        from test_b_route_records import MatrixFixture, encoded
        root = Path(tempfile.mkdtemp(prefix='published-before-data-'))
        self.addCleanup(shutil.rmtree,root)
        matrix = MatrixFixture();matrix.add_binding()
        files = matrix.render()
        for name,data in files.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        join=matrix.join()
        join.master['master']['tasks'][0].update(status='done',acceptance=['Keep acceptance'],history=[{'action':'completed'}])
        for rows in (join.back,join.gameplay):
            rows[0]['status']='done'
        for role,name in adoption.TRIPLET.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded(getattr(join,role)))
        task_bytes={name:(root/name).read_bytes() for name in adoption.TRIPLET.values()}
        receipt_path=records.BASE+'commits/'+matrix.operation_id+'.json'
        receipt=codec.strict_json_loads(files[receipt_path])
        catalog=codec.strict_json_loads(files[records.CATALOG_PATH]);head=catalog['scope_heads'][0]
        plan_ref=head['plan_refs'][0]
        original={'schema_version':'newrouge.b-route-adoption-operation.v1','operation_id':matrix.operation_id,
            'request_raw_digest':codec.raw_digest(b'synthetic original request'),
            'frozen_digest':receipt['operation_digest'],
            'frozen':{'scope_ids':receipt['scopes'],'allocations':{'plan_id':plan_ref['entity_id'],
                'plan_revision':plan_ref['revision'],'binding_revision':head['binding_refs'][0]['revision']},
                'targets':[{'path':row['path'],'schema_version':codec.strict_json_loads(files[row['path']])['schema_version'],
                    'before_raw_digest':None,'after_raw_digest':row['after_digest'],'verification_mode':'immutable_bytes',
                    'after_payload':codec.strict_json_loads(files[row['path']])}
                           for row in receipt['targets']]}}
        op_path=root/journal._operation_ref(original['operation_id']);op_path.parent.mkdir(parents=True,exist_ok=True)
        op_path.write_bytes(owner.raw(original))
        request={'schema_version':journal.COMPENSATION_REQUEST,'producer':'compensation',
            'operation_id':'COMP-context','compensates':compensation.relation_for(original),
            'selection':{'plan_ref':plan_ref,'binding_ref':head['binding_refs'][0]},
            'reason':'Synthetic local exact owned-before test'}
        with patch.object(journal,'operation_inventory',return_value=[original]), \
             patch.object(compensation,'_original_review',return_value=([],[])):
            snapshot,frozen=compensation.build(root,request)
        subject={'schema_version':profiles.PUBLISHED.name('subject'),'operation_id':'COMP-context',
            'preview':frozen,'current_files':{name:base64.b64encode(snapshot.read(name)).decode('ascii')
                for name,pin in list(snapshot.files.items()) if pin is not None},'private_files':{}}
        proof={'schema_version':proof_version or profiles.PUBLISHED.name('proof'),
            'subject_digest':codec.canonical_digest(subject),'files':[]}
        proof_raw=owner.raw(proof)
        ref={'path':owner.location('COMP-context')+'/review.json','schema_version':proof['schema_version'],
             'raw_digest':codec.raw_digest(proof_raw)}
        consumer_frozen=deepcopy(frozen);consumer_frozen['request']={**deepcopy(request),'host_review_ref':ref}
        consumer_frozen['authority_refs']=sorted([*consumer_frozen['authority_refs'],ref],key=lambda row:row['path'])
        consumer={'schema_version':journal.COMPENSATION_SCHEMA,'operation_id':'COMP-context',
            'frozen':consumer_frozen,'frozen_digest':codec.canonical_digest(consumer_frozen)}
        before_files={row['path']:base64.b64encode(files[row['path']]).decode('ascii')
            if row['before_raw_digest'] is not None else None for row in frozen['targets']}
        before_files[records.CATALOG_PATH]=base64.b64encode(files[records.CATALOG_PATH]).decode('ascii')
        intent={'phase':'applied','before_files':before_files,
            'catalog_before':before_files[records.CATALOG_PATH],'catalog_after':None}
        original_intent={'phase':'complete','catalog_after_digest':codec.raw_digest(files[records.CATALOG_PATH]),
            'publication_base':None,'receipt':receipt}
        context=review._SavedInputs(review._MINT,root,subject,{},proof,[],{},None)
        # Materialize precisely the actual proposed effects. The old catalog
        # remains before, so its origins reference is now temporarily stale.
        for row in frozen['targets']:
            path=root/row['path'];path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(projection.serialized(row['after_payload']))
        with self.assertRaises(codec.CodecError):
            records.published_bundle(root,task_join=join)
        actual_read=codec.read_reference_bytes
        def read(current_root,name):
            return proof_raw if name==ref['path'] else actual_read(current_root,name)
        def local(current_root,operation):
            return intent if operation['operation_id']=='COMP-context' else original_intent
        with patch.object(codec,'read_reference_bytes',side_effect=read), \
             patch.object(commit,'validate_local',side_effect=local), \
             patch.object(journal,'operation_inventory',return_value=[original,consumer]), \
             patch.object(journal,'read_operation',return_value=consumer):
            published._saved_current_before(root,original,context)
            origins=root/(records.BASE+'task-origins.v1.json');exact_after=origins.read_bytes()
            origins.write_bytes(exact_after+b' ')
            with self.assertRaises(codec.CodecError):
                published._saved_current_before(root,original,context)
            origins.write_bytes(exact_after)
        self.assertEqual(files[records.CATALOG_PATH],(root/records.CATALOG_PATH).read_bytes())
        self.assertEqual('applied',intent['phase'])
        self.assertEqual(task_bytes,{name:(root/name).read_bytes() for name in adoption.TRIPLET.values()})
