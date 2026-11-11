"""Offline component drafts. Mock seams never constitute native acceptance.

No original nx/R22 evidence, CLI, process or model is accessed by these tests.
Root alone executes after freezing the actual selected source/test set.
"""
from contextlib import nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import _b_route_adoption as adoption
import _b_route_adoption_projection as projection
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_qualified_origin as origin
import _planning_apply_journal as journal


class QualifiedOriginComponentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='nr29-', dir=os.environ.get('ADOPTION_TEST_TEMP')))
        self.target, self.donor = self.root / 'target', self.root / 'neutral-origin'
        self.target.mkdir()
        self.donor.mkdir()
        self.data = b'Neutral synthetic component rule.\n'
        self.digest = codec.raw_digest(self.data)
        self.registration = {'schema_version': 'chapter3.source-set.v1',
            'active_patterns': [origin.SOURCE], 'active_sources': [origin.SOURCE], 'retirements': []}
        self.put(origin.SOURCE, self.data)
        self.put(origin.SOURCE_SET, self.registration)
        self.addCleanup(self.finish)

    def finish(self):
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        bad = result is None or any(t is self or getattr(t, 'test_case', None) is self
            for group in (result.errors, result.failures) for t, _ in group)
        if not bad:
            # Exact owned fixture only; failures retain their original scene.
            if self.root.name.startswith('nr29-') and self.root.is_dir() and not self.root.is_symlink():
                shutil.rmtree(self.root)

    def put(self, name, value):
        p = self.target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value if isinstance(value, bytes) else
            (json.dumps(value, indent=2) + '\n').encode())

    def target_source(self, root=None):
        with patch.object(origin, 'ORIGIN', self.donor), patch.object(origin, 'SOURCE_DIGEST', self.digest):
            return origin.target_source(adoption.Snapshot(root or self.target))

    def subject(self):
        # Deliberately minimal renderer-only fixture, not a planning/native proof.
        content = {'statement': self.data.decode().strip(), 'candidate_id': 'proposal:neutral',
            'requirements': [{'requirement_id': 'proposal:neutral'}],
            'definitions': {'flows': [], 'commands': [], 'states': []},
            'evidence_source_refs': [{'owner': 'implementation_reference', 'ref': origin.SOURCE,
                'files': [{'path': origin.SOURCE, 'raw_digest': self.digest}]}]}
        capsule = {'operation_id': 'OP-neutral', 'profile': origin.PROFILE,
            'source': {'path': origin.SOURCE, 'raw_digest': self.digest, 'text': self.data.decode()},
            'proposal': {'content': deepcopy(content)}, 'native_capture': {'result_digest': 'sha256:' + '1' * 64},
            'prepared_identity': {'input_identity': 'sha256:' + '2' * 64},
            'target_identity': {'path': str(self.target)}, 'source_set_digest': 'sha256:' + '3' * 64}
        return {'schema_version': origin.SUBJECT, 'operation_id': 'OP-neutral',
            'origin_capsule': capsule, 'native_content': content, 'policy_identity': 'sha256:' + '4' * 64,
            'task_definitions': {}, 'related_records': {}, 'affected_catalog': None, 'authority_files': [],
            'prepared': {'opaque_private_history': 'CANARY-REAL-133-TASKS'},
            'protection': {'private_machine_history': 'CANARY-ACCEPTANCE-HISTORY'},
            'target_before_files': [], 'preview': {'allocations': {
                'plan_id': 'PLAN-' + '0' * 12 + '4' + '0' * 3 + '8' + '0' * 15,
                'plan_revision': 1, 'binding_revision': None,
                'requirements': {'proposal:neutral': 'RQ-' + '0' * 12 + '4' + '0' * 3 + '8' + '0' * 15},
                'flows': {}, 'task_definitions': {}}, 'targets': []},
            'request': {'material': {'handoff_ref': {'path': origin.capsule_path('OP-neutral')},
                'identity_alignment': {'plan': {'mode': 'new'}, 'binding': {'mode': 'none'},
                    'requirements': [], 'flows': [], 'tasks': []}}}}

    def render(self, subject):
        # Only the content-schema seam is neutral here; privacy checks are real.
        with patch.object(origin, 'SOURCE_DIGEST', self.digest), patch.object(projection, '_validate_content') as schema:
            value = origin.public_subject(subject)
            schema.assert_called_once_with(subject['native_content'])
            return value

    def test_unknown_profile_stops_before_original_path_access(self):
        with self.assertRaises(codec.CodecError):
            origin.fixed_origin('caller-selected-root')

    def test_foreign_installation_cannot_rebase_trusted_Task(self):
        with patch.object(origin, '__file__', str(self.target / 'a.py')):
            with self.assertRaises(codec.CodecError):
                origin.fixed_origin()

    def test_request_version_detection_does_not_upgrade_v1(self):
        self.assertFalse(origin.is_request({'schema_version': 'newrouge.b-route-adoption-request.v1'}))
        self.assertTrue(origin.is_request({'schema_version': origin.REQUEST}))

    def test_capsule_location_is_operation_bound(self):
        self.assertEqual(origin.capsule_path('OP-a'), origin.capsule_path('OP-a'))
        self.assertNotEqual(origin.capsule_path('OP-a'), origin.capsule_path('OP-b'))

    def test_capsule_location_rejects_traversal(self):
        # Business IDs are opaque; path-like text must never become a locator.
        identities = ('../other', r'..\other', 'C:/other')
        paths = [origin.capsule_path(value) for value in identities]
        self.assertEqual(len(identities), len(set(paths)))
        for value, path in zip(identities, paths):
            with self.subTest(opaque_id=value):
                self.assertRegex(path, r'\Alogs/ci/b-route-origin-captures/[0-9a-f]{64}/capsule\.json\Z')
                codec.validate_reference_path(path)
                self.assertNotIn('..', path.split('/'))
        for invalid in ('', ' ', ' OP-other', 'OP-other ', None, 0, False, [], {}):
            with self.subTest(invalid_id=invalid), self.assertRaises(codec.CodecError):
                origin.capsule_path(invalid)

    def test_target_source_requires_complete_identical_registered_bytes(self):
        identity, source = self.target_source()
        self.assertEqual(str(self.target.resolve()), identity['path'])
        self.assertEqual(self.digest, source['raw_digest'])

    def test_changed_target_source_is_not_same_case(self):
        self.put(origin.SOURCE, b'Changed')
        with self.assertRaises(codec.CodecError):
            self.target_source()

    def test_extra_registered_source_is_not_silently_ignored(self):
        self.registration['active_sources'].append('docs/private.md')
        self.put(origin.SOURCE_SET, self.registration)
        with self.assertRaises(codec.CodecError):
            self.target_source()

    def test_partial_Task_triplet_is_rejected(self):
        self.put(adoption.TRIPLET['master'], {'master': {'tasks': []}})
        with self.assertRaises(codec.CodecError):
            self.target_source()

    def test_populated_target_Task_is_rejected_without_importing_it(self):
        self.put(adoption.TRIPLET['master'], {'master': {'tasks': [{'id': 1}]}})
        self.put(adoption.TRIPLET['back'], [])
        self.put(adoption.TRIPLET['gameplay'], [])
        with self.assertRaises(codec.CodecError):
            self.target_source()

    def test_origin_and_target_cannot_alias(self):
        with patch.object(origin, 'ORIGIN', self.target):
            with self.assertRaises(codec.CodecError):
                origin.target_source(adoption.Snapshot(self.target))

    def test_model_frame_excludes_private_machine_payload_canaries(self):
        visible = self.render(self.subject())
        raw = json.dumps(visible)
        self.assertNotIn('CANARY-REAL', raw)
        self.assertNotIn('CANARY-ACCEPTANCE', raw)
        self.assertEqual(self.data.decode(), visible['source']['text'])

    def test_private_subject_change_is_still_digest_bound(self):
        subject = self.subject()
        before = self.render(subject)['private_subject_digest']
        subject['prepared']['opaque_private_history'] = 'DIFFERENT-PRIVATE-CANARY'
        self.assertNotEqual(before, self.render(subject)['private_subject_digest'])

    def test_extra_authority_payload_blocks_model_rendering(self):
        subject = self.subject()
        subject['authority_files'] = [{'text': 'CANARY-PRIVATE'}]
        with self.assertRaises(codec.CodecError):
            self.render(subject)

    def test_unknown_host_rationale_cannot_enter_model_as_metadata(self):
        subject = self.subject()
        subject['request']['material']['identity_alignment']['requirements'] = [
            {'candidate_id': 'proposal:neutral', 'mode': 'allocate', 'rationale': 'CANARY-PRIVATE'}]
        with self.assertRaises(codec.CodecError):
            self.render(subject)

    def test_selected_semantics_cannot_be_replaced_in_model_lane(self):
        subject = self.subject()
        subject['native_content']['statement'] = 'Changed'
        with self.assertRaises(codec.CodecError):
            self.render(subject)

    def test_foreign_source_reference_blocks_rendering(self):
        subject = self.subject()
        subject['native_content']['evidence_source_refs'][0]['files'][0]['path'] = 'private/Acceptance.json'
        subject['origin_capsule']['proposal']['content'] = deepcopy(subject['native_content'])
        with self.assertRaises(codec.CodecError):
            self.render(subject)

    def test_foreign_operation_capsule_blocks_rendering(self):
        subject = self.subject()
        subject['origin_capsule']['operation_id'] = 'OP-other'
        with self.assertRaises(codec.CodecError):
            self.render(subject)

    def test_new_contract_cannot_inherit_mechanical_review_approval(self):
        subject = self.subject()
        self.assertIsNone(review.machine_mode(subject))
        self.assertIn('artifact_target_separation', review.obligations(subject))
        self.assertEqual('newrouge.b-route-adoption-review-verdict.v2',
                         review.verdict_schema(subject)['properties']['schema_version']['const'])

    def test_malformed_capsule_is_rejected_before_trusted_origin_IO(self):
        with self.assertRaises(codec.CodecError):
            origin.verify_capsule(self.target, {'schema_version': origin.CAPSULE})

    def test_neutral_capsule_persistence_is_exclusive_not_native_evidence(self):
        value = {'schema_version': 'synthetic.storage-only.v1', 'operation_id': 'OP-store', 'source_support': {}}
        with patch.object(origin, 'activity', return_value=nullcontext()), \
             patch.object(origin, 'capture_value', return_value=(value, None)), \
             patch.object(origin, 'verify_capsule'):
            first = origin.prepare_origin(self.target, operation_id='OP-store')
            second = origin.prepare_origin(self.target, operation_id='OP-store')
        self.assertEqual(first, second)
        self.assertFalse(first['formal_story29_acceptance'])
        self.assertEqual(0, first['model_dispatches'])

    def test_partial_old_capsule_is_never_overwritten(self):
        path = origin.capsule_path('OP-store')
        self.put(path, b'{partial')
        value = {'schema_version': 'synthetic.storage-only.v1', 'operation_id': 'OP-store', 'source_support': {}}
        with patch.object(origin, 'activity', return_value=nullcontext()), \
             patch.object(origin, 'capture_value', return_value=(value, None)), \
             patch.object(origin, 'verify_capsule'):
            with self.assertRaises(codec.CodecError):
                origin.prepare_origin(self.target, operation_id='OP-store')
        self.assertEqual(b'{partial', (self.target / path).read_bytes())

    def test_neutral_source_support_is_copied_as_exact_bytes(self):
        name = 'logs/neutral/source-manifest.json'
        raw = b'{"synthetic":true}\n'
        source = self.donor / name
        source.parent.mkdir(parents=True)
        source.write_bytes(raw)
        value = {'schema_version': 'synthetic.storage-only.v1', 'operation_id': 'OP-support',
                 'source_support': {name: codec.raw_digest(raw)}}
        with patch.object(origin, 'ORIGIN', self.donor), \
             patch.object(origin, 'activity', return_value=nullcontext()), \
             patch.object(origin, 'capture_value', return_value=(value, None)), \
             patch.object(origin, 'verify_capsule'):
            origin.prepare_origin(self.target, operation_id='OP-support')
        self.assertEqual(raw, (self.target / name).read_bytes())

    def test_conflicting_neutral_source_support_is_never_replaced(self):
        name = 'logs/neutral/source-manifest.json'
        raw = b'{"synthetic":true}\n'
        source = self.donor / name
        source.parent.mkdir(parents=True)
        source.write_bytes(raw)
        self.put(name, b'{partial')
        value = {'schema_version': 'synthetic.storage-only.v1', 'operation_id': 'OP-support',
                 'source_support': {name: codec.raw_digest(raw)}}
        with patch.object(origin, 'ORIGIN', self.donor), \
             patch.object(origin, 'activity', return_value=nullcontext()), \
             patch.object(origin, 'capture_value', return_value=(value, None)), \
             patch.object(origin, 'verify_capsule'):
            with self.assertRaises(codec.CodecError):
                origin.prepare_origin(self.target, operation_id='OP-support')
        self.assertEqual(b'{partial', (self.target / name).read_bytes())

    def request_fixture(self, version=2):
        ref = {'path': 'logs/fixture.json', 'schema_version': 'raw.bytes.v1',
               'raw_digest': 'sha256:' + '0' * 64}
        material = {'planner': 'mvg', 'run_id': 'm4', 'handoff_ref': deepcopy(ref),
            'protection_ref': deepcopy(ref), 'authority_refs': [], 'lineage_refs': [],
            'identity_alignment': {'plan': {'mode': 'new'}, 'binding': {'mode': 'none'},
                                  'requirements': [], 'flows': [], 'tasks': []},
            'target_templates': [{}]}
        if version == 2:
            material['origin_profile'] = origin.PROFILE
        return {'schema_version': 'newrouge.b-route-adoption-request.v' + str(version),
                'operation_id': 'OP-schema', 'material': material, 'review_ref': deepcopy(ref)}

    def test_v2_request_accepts_only_explicit_origin_profile_schema(self):
        value = self.request_fixture()
        self.assertEqual(value, journal.validate_operation_request(value))

    def test_v2_request_cannot_trust_a_caller_origin_root(self):
        value = self.request_fixture()
        value['material']['origin_root'] = str(self.donor)
        with self.assertRaises(codec.CodecError):
            journal.validate_operation_request(value)

    def test_v1_request_interface_remains_valid_without_origin_profile(self):
        value = self.request_fixture(1)
        self.assertEqual(value, journal.validate_operation_request(value))

    def test_v1_request_cannot_smuggle_v2_origin_semantics(self):
        value = self.request_fixture(1)
        value['material']['origin_profile'] = origin.PROFILE
        with self.assertRaises(codec.CodecError):
            journal.validate_operation_request(value)


class QualifiedOriginReviewCompositionTests(unittest.TestCase):
    """Real public storage/review/journal owners; native and execution are neutral seams."""
    def setUp(self):
        import test_b_route_adoption as composition
        self.fx = composition.AdoptionCompositionTests(
            'test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target')
        self.fx.setUp()
        self.root = self.fx.root
        self.addCleanup(self.finish)
        self.request = deepcopy(self.fx.request)
        fixture, self.content = self.fx.cases['one']
        self.fixture = fixture
        # Reconstruct the pinned LF fixture from a Windows CRLF checkout.
        # The unchanged digest assertion still rejects every other byte change.
        source = (Path(origin.__file__).resolve().parents[2] / origin.SOURCE).read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(origin.SOURCE_DIGEST, codec.raw_digest(source))
        local_source = self.root / origin.SOURCE
        local_source.parent.mkdir(parents=True, exist_ok=True)
        local_source.write_bytes(source)
        self.content['evidence_source_refs'] = [{'owner': 'implementation_reference', 'ref': origin.SOURCE,
            'files': [{'path': origin.SOURCE, 'raw_digest': origin.SOURCE_DIGEST}]}]
        rid = self.content['requirements'][0]['requirement_id']
        fid = self.content['definitions']['flows'][0]['id']
        self.content['requirement_evidence'] = [{'requirement_id': rid, 'evidence_id': 'EV-neutral',
            'kind': 'implementation_reference', 'source_ref': origin.SOURCE,
            'covered_behavior': 'Neutral component composition only', 'flow_ids': [fid], 'test_ids': []}]
        self.content['requirement_verification'][0]['evidence_ids'] = ['EV-neutral']
        self.capsule = {'schema_version': origin.CAPSULE, 'operation_id': 'OP-one', 'profile': origin.PROFILE,
            'origin_identity': {'path': str(self.root / 'neutral-origin')},
            'target_identity': {'path': str(self.root)}, 'qualification_files': {},
            'source_set_digest': 'sha256:' + '1' * 64,
            'source': {'path': origin.SOURCE, 'raw_digest': origin.SOURCE_DIGEST, 'text': source.decode()},
            'source_support': {}, 'proposal': {'content': deepcopy(self.content)},
            'origin_admission': {'synthetic': True},
            'native_capture': {'files': {}, 'directories': {}, 'result_digest': 'sha256:' + '2' * 64},
            'prepared_identity': {'input_identity': 'sha256:' + '3' * 64}}
        cap_path = origin.capsule_path('OP-one')
        self.write(cap_path, self.capsule)
        self.cap_ref = {'path': cap_path, 'schema_version': origin.CAPSULE,
                        'raw_digest': codec.raw_digest((self.root / cap_path).read_bytes())}
        placeholder = {'plan_id': 'PLAN-TEMPLATE', 'plan_revision': 123,
                       'requirements': {rid: 'RQ-TEMPLATE'}, 'flows': {fid: 'FLOW-TEMPLATE'}}
        projected = projection.project_content(self.content, placeholder)
        payload = self.request['material']['target_templates'][0]['after_payload']
        payload.update(projected)
        payload['lineage']['change_summary'] = origin.RATIONALE
        payload['adoption_proof_refs'] = [{'owner': 'planning_proof', 'ref': cap_path,
            'files': [{'path': cap_path, 'raw_digest': self.cap_ref['raw_digest']}]}]
        payload['native_candidate_ref'] = {'owner': 'planning_proof', 'ref': cap_path + '#/proposal/content',
            'files': [{'path': cap_path, 'raw_digest': self.cap_ref['raw_digest']}]}
        def template(value, key=None):
            if isinstance(value, dict):
                return {k: template(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [template(v, key) for v in value]
            labels = {'PLAN-TEMPLATE': 'plan_id', 'RQ-TEMPLATE': 'requirement:' + rid,
                      'FLOW-TEMPLATE': 'flow:' + fid}
            if isinstance(value, str) and value in labels:
                return {'$allocation': labels[value]}
            if key in ('revision', 'owner_revision') and value == 123:
                return {'$allocation': 'plan_revision'}
            return value
        self.request['material']['target_templates'][0]['after_payload'] = template(payload)
        self.request.update(schema_version=origin.REQUEST, review_ref=deepcopy(self.cap_ref))
        self.request['material'].update(origin_profile=origin.PROFILE, run_id='m4',
                                        handoff_ref=deepcopy(self.cap_ref))
        self.write(origin.SOURCE_SET, {'schema_version': 'chapter3.source-set.v1',
            'active_patterns': [origin.SOURCE], 'active_sources': [origin.SOURCE], 'retirements': []})
        for path, payload in origin.bootstrap_records().items():
            self.request['material']['target_templates'].append({'path_template': path,
                'schema_version': payload['schema_version'], 'before_raw_digest': None,
                'after_payload': payload, 'verification_mode': 'immutable_bytes'})
        for family in ('requirements', 'flows'):
            for row in self.request['material']['identity_alignment'][family]:
                row['rationale'] = origin.RATIONALE

    def finish(self):
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        bad = result is None or any(t is self or getattr(t, 'test_case', None) is self
            for group in (result.errors, result.failures) for t, _ in group)
        if not bad and self.root.name.startswith('nr26-') and not self.root.is_symlink():
            shutil.rmtree(self.root)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(review.raw(value))

    def native_capture(self, root, material, review_ref):
        from contextlib import contextmanager
        @contextmanager
        def captured():
            snapshot = adoption.Snapshot(root)
            for name in self.fixture.artifacts:
                snapshot.read(name)
            snapshot.ref(self.cap_ref)
            snapshot.read(origin.SOURCE)
            snapshot.read(origin.SOURCE_SET)
            snapshot.handoff = {'proposal': {'content': deepcopy(self.content)}}
            snapshot.prepared = {'inputs': {'dependencies': {'files': dict(snapshot.files)}}}
            snapshot.protection = {'tasks': []}
            snapshot.origin_capsule = deepcopy(self.capsule)
            snapshot.proof_paths = set(snapshot.files)
            adoption._committed(snapshot)
            yield snapshot
        return captured()

    def semantic_execution(self, root, subject):
        # Execution/provider authenticity alone is synthetic. Verdict/schema and
        # all public stage persistence, support hashes and leases remain real.
        home = review.location('OP-one')
        review.check_verdict(subject, codec.strict_json_loads((self.root / home / 'w/output.json').read_bytes()))
        return {'synthetic_execution_only': True}

    def seams(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(adoption, 'capture_completed', self.native_capture))
        stack.enter_context(patch.object(origin, 'verify_capsule', return_value={'synthetic_native_only': True}))
        stack.enter_context(patch.object(origin, 'activity', side_effect=lambda *args: nullcontext()))
        semantic = stack.enter_context(patch.object(review, 'verify_semantic', side_effect=self.semantic_execution))
        return stack, semantic

    def prepare_review(self):
        return adoption.prepare_review(self.root, operation_id='OP-one',
                                       request_ref=self.fx.request_ref(self.request))

    def execution_fixture(self):
        subject = review.read_subject(self.root, 'OP-one')
        verdict = {'schema_version': review.verdict_schema(subject)['properties']['schema_version']['const'],
            'subject_digest': codec.canonical_digest(subject), 'verdict': 'approved', 'findings': [],
            'checks': [{'id': name, 'verdict': 'approved', 'rationale': 'Neutral composition fixture'}
                       for name in review.obligations(subject)]}
        self.write(review.location('OP-one') + '/w/output.json', verdict)
        self.write(review.location('OP-one') + '/execution.json', {'synthetic_execution_only': True})

    def test_public_review_complete_prepare_reserve_keeps_body_and_support_lanes_stable(self):
        stack, semantic = self.seams()
        with stack:
            first = self.prepare_review()
            self.assertTrue(first['semantic_execution_required'])
            subject_path = self.root / review.location('OP-one') / 'subject.json'
            original = subject_path.read_bytes()
            self.execution_fixture()
            self.request['host_review_ref'] = adoption.complete_review(self.root, operation_id='OP-one')['host_review_ref']
            prepared = adoption.prepare(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))
            reserved = adoption.reserve(self.root, operation_id='OP-one')
            self.assertEqual('prepared', prepared['state'])
            self.assertEqual('reserved', reserved['state'])
            self.assertEqual(original, subject_path.read_bytes())
            self.assertGreater(semantic.call_count, 0)
            subject = codec.strict_json_loads(original)
            self.assertFalse(any(name.startswith(review.location('OP-one') + '/')
                                 for name in subject['target_dependencies']))
            envelope = journal.read_operation(self.root, operation_id='OP-one')
            support = {row['path'] for row in envelope['frozen']['authority_refs']}
            self.assertTrue({review.location('OP-one') + '/' + name for name in
                             [*review.support_names('semantic'), 'review.json']} <= support)

    def test_review_support_tamper_still_blocks_reserve_without_changing_prepared_bytes(self):
        stack, _ = self.seams()
        with stack:
            self.prepare_review()
            self.execution_fixture()
            self.request['host_review_ref'] = adoption.complete_review(self.root, operation_id='OP-one')['host_review_ref']
            prepared = adoption.prepare(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))
            path = self.root / prepared['resume_ref']
            original = path.read_bytes()
            (self.root / review.location('OP-one') / 'w/prompt.txt').write_bytes(b'Tampered neutral support')
            with self.assertRaises(codec.CodecError):
                adoption.reserve(self.root, operation_id='OP-one')
            self.assertEqual(original, path.read_bytes())

    def test_saved_subject_unclassified_allocation_is_rejected_before_semantic_execution(self):
        stack, semantic = self.seams()
        with stack:
            self.prepare_review()
            path = self.root / review.location('OP-one') / 'subject.json'
            baseline = codec.strict_json_loads(path.read_bytes())
            old = baseline['preview']['allocations']['plan_id']
            def replace(value, before, after):
                if isinstance(value, dict): return {k: replace(v, before, after) for k, v in value.items()}
                if isinstance(value, list): return [replace(v, before, after) for v in value]
                return value.replace(before, after) if isinstance(value, str) else value
            cases = [('plan', replace(baseline, old, 'PLAN-PRIVATE-CANARY'))]
            for family, prefix in (('requirements', 'RQ-'), ('flows', 'FLOW-')):
                identity = next(iter(baseline['preview']['allocations'][family].values()))
                cases.append((family, replace(baseline, identity, prefix + 'PRIVATE-CANARY')))
            bad_path = deepcopy(baseline)
            bad_path['preview']['targets'][0]['path'] = 'docs/planning/b-route/plans/PRIVATE-CANARY/1.json'
            cases.append(('target_path', bad_path))
            bad_keys = deepcopy(baseline)
            mapping = bad_keys['preview']['allocations']['requirements']
            mapping['FOREIGN-NATIVE-KEY'] = mapping.pop(next(iter(mapping)))
            cases.append(('native_key_denominator', bad_keys))
            cases.append(('UUID_version', replace(baseline, old, old[:17] + '3' + old[18:])))
            for label, subject in cases:
                path.write_bytes(review.raw(subject))
                with self.subTest(case=label), self.assertRaises(codec.CodecError):
                    self.prepare_review()
            semantic.assert_not_called()
            self.assertEqual([], journal.operation_inventory(self.root))

    def test_unclassified_new_dependency_after_body_freeze_is_not_silently_dropped(self):
        stack, _ = self.seams()
        with stack, self.native_capture(self.root, self.request['material'], self.request['review_ref']) as snapshot:
            allocations = adoption.propose_allocations(snapshot, self.request['material']['identity_alignment'], [])
            frozen = adoption.build_frozen(snapshot, self.request, allocations)
            review.make_subject(snapshot, self.request, frozen)
            self.write('neutral-extra.json', {'synthetic': True})
            snapshot.read('neutral-extra.json')
            with self.assertRaises(codec.CodecError):
                review.make_subject(snapshot, self.request, frozen)

    def reviewed_reservation(self):
        self.prepare_review()
        self.execution_fixture()
        self.request['host_review_ref'] = adoption.complete_review(
            self.root, operation_id='OP-one')['host_review_ref']
        adoption.prepare(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))
        adoption.reserve(self.root, operation_id='OP-one')
        return journal.read_operation(self.root, operation_id='OP-one')

    def test_public_bootstrap_review_through_catalog_read_uses_real_commit_projection(self):
        import _b_route_commit as commit
        import _b_route_records as records
        from _b_route_operation_scope import resource_scopes
        stack, semantic = self.seams()
        with stack:
            envelope = self.reviewed_reservation()
            targets = envelope['frozen']['targets']
            governance = origin.bootstrap_records()
            self.assertEqual(3, len(targets))
            self.assertTrue(set(resource_scopes(target_paths=governance)) <= set(envelope['frozen']['scope_ids']))
            subject_raw = (self.root / review.location('OP-one') / 'subject.json').read_bytes()
            subject = review.read_subject(self.root, 'OP-one')
            visible = origin.public_subject(subject)
            self.assertEqual(targets, visible['targets'])
            self.assertTrue(all(row['raw_base64'] is None and row['text'] is None
                                for row in visible['target_before_files']))
            self.assertTrue(all(not (self.root / row['path']).exists() for row in targets))
            applied = commit.execute(self.root, operation_id='OP-one', stage='apply')
            self.assertFalse(applied['formal_adoption'])
            self.assertFalse((self.root / records.CATALOG_PATH).exists())
            intent = commit.validate_local(self.root, envelope)
            self.assertEqual({row['path'] for row in targets}, set(intent['before_files']) - {records.CATALOG_PATH})
            for row in targets:
                self.assertIsNone(intent['files'][str(self.root / row['path'])])
                self.assertEqual(row['after_raw_digest'], codec.raw_digest((self.root / row['path']).read_bytes()))
            self.assertEqual(envelope['frozen']['scope_ids'], intent['receipt']['scopes'])
            self.assertEqual({row['path'] for row in envelope['frozen']['authority_refs']},
                             {row['path'] for row in intent['receipt']['authority']})
            self.assertFalse(commit.execute(self.root, operation_id='OP-one', stage='verify')['formal_adoption'])
            self.assertTrue(commit.execute(self.root, operation_id='OP-one', stage='publish')['formal_adoption'])
            committed = commit.read_committed(self.root)
            self.assertTrue(committed['formal_adoption'])
            self.assertFalse(committed['default_b_enabled'])
            self.assertFalse(committed['readiness'])
            self.assertFalse(committed['runtime_verified'])
            catalog = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
            self.assertEqual([], catalog['task_index'])
            self.assertEqual([], journal.active_operation_inventory(self.root))
            self.assertEqual(subject_raw, (self.root / review.location('OP-one') / 'subject.json').read_bytes())
            for path, payload in governance.items():
                self.assertEqual(payload, codec.strict_json_loads((self.root / path).read_bytes()))
            self.assertTrue(commit.execute(self.root, operation_id='OP-one', stage='publish')['noop'])
            self.assertGreater(semantic.call_count, 0)

    def test_published_bootstrap_clone_reads_without_local_review_or_capsule_logs(self):
        import _b_route_commit as commit
        import _b_route_records as records
        stack, _ = self.seams()
        with stack:
            self.reviewed_reservation()
            for stage in ('apply', 'verify', 'publish'):
                commit.execute(self.root, operation_id='OP-one', stage=stage)
        clone = Path(tempfile.mkdtemp(prefix='nr29-clone-', dir=os.environ.get('ADOPTION_TEST_TEMP')))
        # A failed clone remains inspectable. The copied evidence is neutral;
        # original qualification, semantic execution and capsule logs are absent.
        for name in ('docs', 'sources', 'evidence'):
            shutil.copytree(self.root / name, clone / name)
        self.assertFalse((clone / 'logs').exists())
        before = {p.relative_to(clone).as_posix(): p.read_bytes() for p in
                  (clone / records.BASE).rglob('*') if p.is_file()}
        result = commit.read_committed(clone)
        self.assertTrue(result['formal_adoption'])
        self.assertFalse(result['default_b_enabled'])
        self.assertFalse(result['runtime_verified'])
        self.assertFalse(records.validate_bundle({}, root=clone).ok)
        self.assertEqual(before, {p.relative_to(clone).as_posix(): p.read_bytes() for p in
                         (clone / records.BASE).rglob('*') if p.is_file()})
        if clone.name.startswith('nr29-clone-') and not clone.is_symlink():
            shutil.rmtree(clone)

    def test_bootstrap_missing_duplicate_extra_and_changed_governance_block_before_review_storage(self):
        baseline = deepcopy(self.request)
        templates = baseline['material']['target_templates']
        cases = []
        for index in (1, 2):
            changed = deepcopy(baseline)
            changed['material']['target_templates'].pop(index)
            cases.append(('missing_' + str(index), changed))
        duplicate = deepcopy(baseline)
        duplicate['material']['target_templates'].append(deepcopy(templates[1]))
        cases.append(('duplicate_policy', duplicate))
        extra = deepcopy(baseline)
        row = deepcopy(templates[1]); row['path_template'] = 'docs/planning/b-route/extra.json'
        extra['material']['target_templates'].append(row)
        cases.append(('extra_target', extra))
        for label, index, field, value in (
                ('B_activation', 1, 'switch_boundary', {'default_route': 'B', 'a_write_allowed': False,
                    'allowed_a_operations': [], 'authority_refs': []}),
                ('policy_identity', 1, 'policy_id', 'PRIVATE-CANARY'),
                ('policy_revision', 1, 'policy_revision', 2),
                ('Task_origins', 2, 'tasks', [{'task_id': 133}]),
                ('legacy_authority', 2, 'frozen_legacy_refs', [{'private': 'CANARY'}])):
            changed = deepcopy(baseline)
            changed['material']['target_templates'][index]['after_payload'][field] = value
            cases.append((label, changed))
        stack, semantic = self.seams()
        with stack:
            for label, request in cases:
                with self.subTest(case=label), self.assertRaises(codec.CodecError):
                    adoption.prepare_review(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(request))
                self.assertEqual([], journal.operation_inventory(self.root))
                self.assertFalse((self.root / review.location('OP-one') / 'subject.json').exists())
            semantic.assert_not_called()

    def test_saved_bootstrap_governance_cannot_be_laundered_before_semantic_execution(self):
        stack, semantic = self.seams()
        with stack:
            self.prepare_review()
            path = self.root / review.location('OP-one') / 'subject.json'
            baseline = codec.strict_json_loads(path.read_bytes())
            for index, field, value in ((1, 'policy_id', 'PRIVATE-CANARY'),
                                        (2, 'origins_id', 'PRIVATE-CANARY')):
                subject = deepcopy(baseline)
                subject['preview']['targets'][index]['after_payload'][field] = value
                path.write_bytes(review.raw(subject))
                with self.subTest(target=index), self.assertRaises(codec.CodecError):
                    review.read_subject(self.root, 'OP-one')
            semantic.assert_not_called()

    def test_applied_bootstrap_governance_edit_blocks_verify_and_preserves_edit(self):
        import _b_route_commit as commit
        import _b_route_records as records
        stack, _ = self.seams()
        with stack:
            self.reviewed_reservation()
            commit.execute(self.root, operation_id='OP-one', stage='apply')
            path = self.root / 'docs/planning/b-route/policy.v1.json'
            before = path.read_bytes()
            edited = codec.strict_json_loads(before)
            edited['switch_boundary']['default_route'] = 'B'
            path.write_bytes(review.raw(edited))
            with self.assertRaises(codec.CodecError):
                commit.execute(self.root, operation_id='OP-one', stage='verify')
            self.assertEqual(review.raw(edited), path.read_bytes())
            self.assertFalse((self.root / records.CATALOG_PATH).exists())
            path.write_bytes(before)
            commit.execute(self.root, operation_id='OP-one', stage='verify')
            commit.execute(self.root, operation_id='OP-one', stage='publish')
