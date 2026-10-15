"""Offline acceptance for authoritative Requirement and shared evidence accounting."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import argparse
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _mvg_requirement_accounting import (VERIFICATION, EVIDENCE, PROTOCOL, PROTOCOL_FIELD,
    accounting_errors, accounting_summary, project_accounting, prepared_evidence_validation,
    source_record_errors, freeze_accounting_sources, trace_evidence_validation, protocol_errors)
from _mvg_capability_append import merge_append, preservation_errors
from _mvg_capability_generation import append_output_schema, review_projection, seed_proposal
from _planning_skill_common import atomic_json, file_sha, canonical_sha
from scripts.python.tests.test_mvg_requirement_routes import fixture
import plan_mvg


def proposal():
    result = project_accounting(fixture())
    result[PROTOCOL_FIELD] = PROTOCOL
    result[VERIFICATION][0]['evidence_ids'] = ['shared']
    result[EVIDENCE] = [{'requirement_id': 'RQ-1', 'evidence_id': 'shared',
        'kind': 'verification_record', 'source_ref': 'docs/testing/proof.md#shared',
        'covered_behavior': 'Recover accepted state', 'flow_ids': ['flow-a', 'flow-b'], 'test_ids': []}]
    return result


class RequirementAccountingTests(unittest.TestCase):
    def prepared(self, root, value):
        prepared = root / 'prepared'
        evidence = value[EVIDENCE][0]
        record = {'evidence_id': 'shared', 'requirement_ids': ['RQ-1'], 'status': 'passed',
            'covered_behavior': evidence['covered_behavior'], 'flow_ids': evidence['flow_ids'], 'test_ids': []}
        text = 'Reviewed verification record.\n```json\n' + json.dumps(record) + '\n```\n'
        for path in (root / 'docs/testing/proof.md', prepared / 'references/docs/testing/proof.md'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        atomic_json(prepared / 'analysis-index.json', {'files': {
            'references/docs/testing/proof.md': file_sha(prepared / 'references/docs/testing/proof.md')},
            'authority_inputs': {'docs/testing/proof.md': file_sha(root / 'docs/testing/proof.md')},
            PROTOCOL_FIELD: PROTOCOL})
        return prepared

    def test_shared_evidence_counts_once_and_requires_every_route(self):
        value = proposal()
        self.assertEqual([], accounting_errors(value, {'RQ-1'}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); prepared = self.prepared(root, value)
            errors, valid = prepared_evidence_validation(root, value, prepared)
            self.assertEqual([], errors)
            result = accounting_summary(value, valid_evidence_keys=valid)
            self.assertEqual((1, 1, 1), (result['accounted_count'], result['satisfied_count'], result['evidence_count']))
            value[EVIDENCE][0]['flow_ids'] = ['flow-a']
            self.assertEqual(0, accounting_summary(value, valid_evidence_keys=valid)['satisfied_count'])
            value[VERIFICATION][0]['evidence_ids'] = []
            self.assertTrue(any('unreferenced' in error for error in accounting_errors(value, {'RQ-1'})))
            self.assertEqual(0, accounting_summary(value, valid_evidence_keys=valid)['satisfied_count'])

    def test_four_dispositions_and_implementation_never_grant_runtime(self):
        for disposition in ('flow', 'other_verification', 'deferred', 'source_gap'):
            value = proposal()
            value['coverage_table'][0]['disposition'] = disposition
            value[VERIFICATION][0]['disposition'] = disposition
            result = accounting_summary(value, valid_evidence_keys={('RQ-1', 'shared')})
            self.assertEqual(1, result['accounted_count'])
            self.assertEqual(int(disposition in {'flow', 'other_verification'}), result['satisfied_count'])
            self.assertEqual(disposition != 'source_gap', result['planning_complete'])
            self.assertNotIn('runtime_verified', result)
        value[EVIDENCE][0]['kind'] = 'implementation_reference'
        self.assertEqual(0, accounting_summary(value, valid_evidence_keys={('RQ-1', 'shared')})['satisfied_count'])

    def test_bad_evidence_is_located_before_admission(self):
        for field, body, expected in ((EVIDENCE, None, 'not_array'), (VERIFICATION, None, 'not_array'),
                ('duplicate', None, 'duplicate'), ('requirement_id', 'unknown', 'unknown_requirement'),
                ('covered_behavior', '', 'covered_behavior_missing'), ('flow_ids', ['unknown'], 'scope_invalid'),
                ('test_ids', ['unknown'], 'scope_invalid'), ('kind', 'invented', 'kind_invalid')):
            value = proposal()
            if field in {EVIDENCE, VERIFICATION}:
                value[field] = body
            elif field == 'duplicate':
                value[EVIDENCE].append(deepcopy(value[EVIDENCE][0]))
            else:
                value[EVIDENCE][0][field] = body
            self.assertTrue(any(expected in error for error in accounting_errors(value, {'RQ-1'})), field)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = proposal(); prepared = self.prepared(root, value)
            value[EVIDENCE][0]['source_ref'] = 'docs/unknown.md'
            self.assertIn('not_prepared', ';'.join(prepared_evidence_validation(root, value, prepared)[0]))
            value = proposal()
            (prepared / 'references/docs/testing/proof.md').write_text('changed', encoding='utf-8')
            self.assertIn('source_drift', ';'.join(prepared_evidence_validation(root, value, prepared)[0]))

    def test_legacy_hash_authority_fragment_preserved_without_invented_pass(self):
        value = fixture(); value.pop('requirement_route_memberships')
        value['coverage_table'][0].update(disposition='other_verification', verification_ref='docs/proof.md#original',
            authority_metadata={'original': True})
        before = deepcopy(value); digest = canonical_sha(value)
        projected = project_accounting(value)
        self.assertEqual(before, value); self.assertEqual(digest, canonical_sha(value))
        self.assertEqual(value['coverage_table'], projected['coverage_table'])
        self.assertEqual(value['coverage_table'][0], {key: body for key, body in projected[VERIFICATION][0].items() if key != 'evidence_ids'})
        self.assertEqual('docs/proof.md#original', projected[EVIDENCE][0]['source_ref'])
        self.assertEqual(0, accounting_summary(projected)['satisfied_count'])
        self.assertEqual('implementation_reference', projected[EVIDENCE][0]['kind'])

    def test_cumulative_evidence_preserves_authority_and_review_closure(self):
        base = project_accounting(fixture())
        delta = {VERIFICATION: [], EVIDENCE: proposal()[EVIDENCE]}
        combined = merge_append(base, delta, {'new_requirement_ids': []})
        self.assertEqual([], preservation_errors(base, combined))
        self.assertEqual(['shared'], combined[VERIFICATION][0]['evidence_ids'])
        self.assertEqual([], accounting_errors(combined, {'RQ-1'}))
        projected, required = review_projection({'requirement_ids': [], 'cumulative_requirement_ids': ['RQ-1']}, base, combined)
        self.assertEqual({'flow-a', 'flow-b'}, {row['id'] for row in projected['manifest_candidate']['flows']})
        self.assertEqual({'RQ-1'}, required)
        self.assertEqual(combined[EVIDENCE], projected[EVIDENCE])
        with self.assertRaisesRegex(ValueError, 'already_accepted'):
            merge_append(combined, {EVIDENCE: [{**proposal()[EVIDENCE][0], 'covered_behavior': 'Changed'}]})
        changed = deepcopy(combined); changed[VERIFICATION][0]['rationale'] = 'Changed'
        self.assertTrue(preservation_errors(combined, changed))

    def test_trace_sources_are_frozen_and_summary_knowledge_is_descriptive(self):
        from _project_health_mvg_versions import attach_planning_routes
        value = proposal()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); prepared = self.prepared(root, value)
            value.update(freeze_accounting_sources(value, prepared))
            reader = lambda ref: (root / ref).read_bytes()
            self.assertEqual([], trace_evidence_validation(value, read_source=reader)[0])
            target = {}
            self.assertTrue(attach_planning_routes(target, value, {'kind': 'formal_planning_trace'},
                requirement_ids={'RQ-1'}, applied_manifest=value['manifest_candidate'], read_source=reader))
            self.assertEqual(1, target['requirement_accounting']['satisfied_count'])
            self.assertNotIn('runtime_verified', target)
            value['requirement_accounting_sources']['docs/testing/proof.md']['text'] = 'forged'
            from _planning_skill_common import text_sha
            value['requirement_accounting_sources']['docs/testing/proof.md']['sha256'] = text_sha('forged')
            self.assertTrue(trace_evidence_validation(value, read_source=reader)[0])

    def test_record_scope_malformed_and_runtime_receipt_rejected(self):
        row = proposal()[EVIDENCE][0]
        for mutation in ({'flow_ids': [None]}, {'test_ids': None}, {'requirement_ids': None}):
            record = {'status': 'passed', 'requirement_ids': ['RQ-1'], 'covered_behavior': row['covered_behavior'],
                      'flow_ids': row['flow_ids'], 'test_ids': []}
            record.update(mutation)
            self.assertTrue(source_record_errors(row, json.dumps({'records': [record]}), {}))
        row['kind'] = 'runtime_acceptance'
        self.assertTrue(source_record_errors(row, json.dumps({'runtime_verified': True, 'status': 'passed'}), {}))
        row['kind'] = 'unknown'
        self.assertTrue(source_record_errors(row, '{}', {}))

    def test_protocol_forbids_field_deletion(self):
        self.assertEqual(2, len(protocol_errors({PROTOCOL_FIELD: PROTOCOL}, {})))
        self.assertTrue(protocol_errors({PROTOCOL_FIELD: 'unknown'}))
        from _mvg_requirement_routes import trace_errors
        value = proposal()
        self.assertEqual([], trace_errors(value, value['manifest_candidate'], {'RQ-1'}))
        for field in (VERIFICATION, EVIDENCE, PROTOCOL_FIELD):
            changed = deepcopy(value); changed.pop(field)
            self.assertTrue(trace_errors(changed, value['manifest_candidate'], {'RQ-1'}), field)
        value[VERIFICATION] = []; value[EVIDENCE] = []
        self.assertIn('requirement_verification_missing:RQ-1', accounting_errors(value, {'RQ-1'}, complete=False))

    def test_flowless_existing_owner_and_evidence_remain_in_review_projection(self):
        base = proposal()
        base['manifest_candidate']['flows'] = []; base['requirement_route_memberships'] = []
        owner = base['coverage_table'][0]
        owner.update(disposition='other_verification', flow_id=None, sink_id='review-sink',
                     verification_ref='docs/testing/proof.md#shared')
        base[VERIFICATION] = [{**deepcopy(owner), 'evidence_ids': []}]; base[EVIDENCE] = []
        evidence = {**proposal()[EVIDENCE][0], 'flow_ids': []}
        combined = merge_append(base, {EVIDENCE: [evidence]})
        projected, required = review_projection({'requirement_ids': [], 'cumulative_requirement_ids': ['RQ-1']}, base, combined)
        self.assertEqual({'RQ-1'}, required)
        self.assertEqual([owner], projected['coverage_table'])
        self.assertEqual(combined[VERIFICATION], projected[VERIFICATION])
        self.assertEqual([evidence], projected[EVIDENCE])

    def test_legacy_reference_does_not_block_appended_authoritative_proof(self):
        value = proposal()
        reference = {**value[EVIDENCE][0], 'evidence_id': 'legacy-reference', 'kind': 'implementation_reference'}
        value[EVIDENCE].insert(0, reference)
        value[VERIFICATION][0]['evidence_ids'].insert(0, 'legacy-reference')
        self.assertEqual(1, accounting_summary(value, valid_evidence_keys={('RQ-1', 'shared')})['satisfied_count'])
        value[EVIDENCE].pop(); value[VERIFICATION][0]['evidence_ids'].pop()
        self.assertEqual(0, accounting_summary(value, valid_evidence_keys={('RQ-1', 'legacy-reference')})['satisfied_count'])

    def test_malformed_accounting_routes_and_merge_have_diagnostics(self):
        from _mvg_requirement_routes import route_errors
        for key, body in (('disposition', []), ('evidence_ids', [None]), ('evidence_ids', None)):
            value = proposal(); value[VERIFICATION][0][key] = body
            self.assertTrue(accounting_errors(value, {'RQ-1'}), (key, body))
            self.assertTrue(preservation_errors(value, proposal()))
        for field in ('requirement_id', 'flow_id'):
            for body in ([], {}):
                value = proposal(); value['requirement_route_memberships'][0][field] = body
                self.assertTrue(route_errors(value, {'RQ-1'}))
        for family in ('flows', 'tests'):
            value = proposal(); value['manifest_candidate'][family] = [{'id': []}]
            self.assertTrue(accounting_errors(value, {'RQ-1'}))
        for field in (VERIFICATION, EVIDENCE, 'coverage_table', 'tests', 'flows'):
            for body in (None, [None]):
                with self.assertRaises(ValueError, msg=(field, body)):
                    merge_append(proposal(), {field: body})
                with self.assertRaises(ValueError, msg=(field, body)):
                    plan_mvg.merge_planning_segments(proposal(), [{field: body}])

    def test_canonical_sources_normalize_line_endings_and_bom_but_reject_invalid_bytes(self):
        from _mvg_requirement_accounting import source_path
        from _project_health_mvg_versions import attach_planning_routes
        for ref in ('C:/docs/proof.md', '/docs/proof.md', './docs/proof.md', 'docs/../proof.md',
                    'docs\\proof.md', 'docs//proof.md'):
            with self.assertRaises(ValueError):
                source_path(ref)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = proposal(); prepared = self.prepared(root, value)
            value.update(freeze_accounting_sources(value, prepared))
            stored = deepcopy(value['requirement_accounting_sources'])
            path = root / 'docs/testing/proof.md'; original = path.read_bytes().replace(b'\r\n', b'\n')
            for actual in (original.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + original):
                path.write_bytes(actual)
                self.assertEqual([], prepared_evidence_validation(root, value, prepared)[0])
                self.assertEqual([], trace_evidence_validation(value, read_source=lambda ref: (root / ref).read_bytes())[0])
                self.assertEqual(stored, value['requirement_accounting_sources'])
            path.write_bytes(b'\xff\xfe')
            self.assertTrue(prepared_evidence_validation(root, value, prepared)[0])
            target = {}
            self.assertTrue(attach_planning_routes(target, value, {}, requirement_ids={'RQ-1'},
                applied_manifest=value['manifest_candidate'], read_source=lambda ref: (root / ref).read_bytes()))
            self.assertEqual(0, target['requirement_accounting']['satisfied_count'])
            self.assertTrue(target['requirement_accounting']['evidence_errors'])

    def test_append_source_gap_blocks_first_attempt_and_preserves_accepted_predecessor(self):
        from _mvg_capability_append import run_capability_append
        from _mvg_capability_generation import machine_validation_issues
        from unittest.mock import Mock
        seed = proposal(); scopes = [{'capability_id': cid, 'new_requirement_ids': [],
            'requirement_ids': ['RQ-1'], 'cumulative_requirement_ids': ['RQ-1']} for cid in ('CAP-A', 'CAP-B', 'CAP-C')]
        seen = []
        def propose(scope, accepted, previous, issue, context, call):
            seen.append((scope['capability_id'], canonical_sha(accepted))); call('generate')
            return {'notes': [scope['capability_id']]}
        def machine(scope, accepted, candidate):
            return machine_validation_issues({'errors': [], 'formal_blockers':
                ['requirement_source_gap:RQ-1'] if scope['capability_id'] == 'CAP-B' else []}, scope, candidate)
        def semantic(scope, accepted, candidate, call, context):
            call('semantic'); return {'issues': [], 'proof': {}, 'execution': {}}
        final = Mock(return_value=[])
        with tempfile.TemporaryDirectory() as directory:
            ledger = run_capability_append(Path(directory), scopes=scopes, seed=seed, identity='fixture',
                propose=propose, machine=machine, semantic=semantic, final_machine=final)
            self.assertEqual('blocked', ledger['status']); self.assertEqual(['CAP-A'], ledger['completed'])
            self.assertEqual(['CAP-A', 'CAP-B'], [row[0] for row in seen])
            self.assertEqual(3, ledger['total_invocations']); final.assert_not_called()
            self.assertEqual(ledger['records'][0]['proposal_sha256'], seen[1][1])
            self.assertEqual(seen[1][1], canonical_sha(ledger['accepted']))
            self.assertEqual(canonical_sha(seed), ledger['records'][0]['base_sha256'])

    def test_legacy_passed_fragment_prepare_seed_conserves_owner_hash_and_evidence(self):
        from scripts.python.tests.test_mvg_input_envelope import InputEnvelopeTests
        from _mvg_manifest import manifest_sha256
        from _planning_skill_common import load_json
        case = InputEnvelopeTests(); case.setUp(); self.addCleanup(case.doCleanups)
        root = case.root
        rid, flow_rid = [row['requirement_id'] for row in load_json(root / plan_mvg.SEMANTICS)['requirements']]
        legacy = fixture(); legacy.pop('requirement_route_memberships')
        for flow in legacy['manifest_candidate']['flows']:
            flow['requirement_ids'] = [flow_rid]
        ref = 'docs/testing/legacy-record.json'
        owner = {'requirement_id': rid, 'disposition': 'other_verification', 'sink_id': 'historical-review',
                 'rationale': 'Reviewed legacy behavior', 'verification_ref': ref + '#actual',
                 'original_owner': {'task_id': 7}}
        flow_owner = {**legacy['coverage_table'][0], 'requirement_id': flow_rid}
        legacy['coverage_table'] = [owner, flow_owner]
        record = {'records': [{'evidence_id': 'actual', 'requirement_ids': [rid], 'status': 'passed',
                  'covered_behavior': owner['rationale'], 'flow_ids': [], 'test_ids': []}]}
        atomic_json(root / ref, record)
        manifest_ref = 'docs/testing/mvg/envelope.json'
        atomic_json(root / manifest_ref, legacy['manifest_candidate'])
        trace_ref = 'docs/testing/mvg/planning/legacy.json'
        trace = {**deepcopy(legacy), 'applied_manifest_path': manifest_ref,
                 'applied_manifest_sha256': manifest_sha256((root / manifest_ref).read_bytes())}
        atomic_json(root / trace_ref, trace)
        hashes = {path: file_sha(root / path) for path in (ref, manifest_ref, trace_ref)}
        state = case.prepare(evidence_refs=[ref + '#actual'])
        prepared = case.run / 'analysis-input'; seed = seed_proposal(state, prepared)
        self.assertEqual(legacy['coverage_table'], seed['coverage_table'])
        self.assertEqual(owner, {key: value for key, value in seed[VERIFICATION][0].items() if key != 'evidence_ids'})
        self.assertEqual(ref + '#actual', seed[EVIDENCE][0]['source_ref'])
        self.assertEqual('verification_record', seed[EVIDENCE][0]['kind'])
        errors, valid = prepared_evidence_validation(root, seed, prepared)
        self.assertEqual([], errors)
        self.assertEqual(1, accounting_summary(seed, valid_evidence_keys=valid)['satisfied_count'])
        self.assertEqual(hashes, {path: file_sha(root / path) for path in hashes})
        self.assertNotIn(PROTOCOL_FIELD, load_json(root / trace_ref))

    def test_runtime_acceptance_formal_receipt_positive_and_revision_binding(self):
        from run_mvg_acceptance import register_arguments, run
        from _mvg_manifest import manifest_sha256
        from _planning_skill_common import load_json
        from _mvg_requirement_accounting import runtime_paths
        for mode in ('commit', 'workspace'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); value = proposal(); manifest = value['manifest_candidate']
                manifest['tests'] = []
                ref = 'docs/testing/mvg/current.json'
                target = root / ref; target.parent.mkdir(parents=True)
                # Different whitespace deliberately defeats reserialization hashing.
                target.write_text(json.dumps(manifest, separators=(', ', ': ')) + '\n', encoding='utf-8')
                for args in (('init', '-b', 'main'), ('config', 'user.email', 'fixture@example.invalid'),
                             ('config', 'user.name', 'Fixture'), ('add', '.'), ('commit', '-m', 'Fixture')):
                    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
                parser = argparse.ArgumentParser(); register_arguments(parser)
                args = parser.parse_args(['--manifest', ref, '--mode', 'run', '--snapshot', mode])
                with patch('run_mvg_acceptance.validate_manifest', return_value=[]), \
                     patch('run_mvg_acceptance.recommend', return_value={}), \
                     patch('run_mvg_acceptance.execute_test', return_value={'status': 'passed'}):
                    self.assertEqual(0, run(args, root))
                summary_path = next(root.glob('logs/ci/mvg-acceptance/*/summary.json'))
                summary = load_json(summary_path)
                self.assertEqual(manifest_sha256(target.read_bytes()), summary['manifest_sha256'])
                row = {**value[EVIDENCE][0], 'kind': 'runtime_acceptance',
                       'source_ref': summary_path.relative_to(root).as_posix()}
                value[EVIDENCE] = [row]
                reader = lambda path: (root / path).read_bytes()
                self.assertEqual([], source_record_errors(row, summary_path.read_text(encoding='utf-8'),
                                                          manifest, read_source=reader, expected_manifest_path=ref))
                prepared = root / 'prepared'
                refs = [row['source_ref'], *runtime_paths(row['source_ref'], summary)]
                files, authority = {}, {}
                for path in refs:
                    copied = prepared / 'references' / path; copied.parent.mkdir(parents=True, exist_ok=True)
                    copied.write_bytes((root / path).read_bytes())
                    files['references/' + path] = file_sha(copied)
                    authority[path] = file_sha(root / path)
                atomic_json(prepared / 'analysis-index.json', {'files': files, 'authority_inputs': authority,
                    'input_envelope': {'predecessor': {'path': ref, 'status': 'absent'}}})
                self.assertEqual([], prepared_evidence_validation(root, value, prepared)[0])
                value.update(freeze_accounting_sources(value, prepared))
                value['applied_manifest_path'] = ref
                self.assertEqual([], trace_evidence_validation(value, read_source=reader)[0])
                for field, changed in (('source_revision', 'wrong'), ('snapshot_digest', '0' * 64),
                                       ('manifest_sha256', 'sha256:wrong'), ('base_commit', 'not-a-commit')):
                    bad = {**summary, field: changed}
                    self.assertTrue(source_record_errors(row, json.dumps(bad), manifest,
                        read_source=reader, expected_manifest_path=ref), field)
                self.assertTrue(source_record_errors(row, json.dumps(summary), manifest,
                    read_source=reader, expected_manifest_path='docs/testing/mvg/other.json'))
                self.assertTrue(source_record_errors(row, json.dumps(summary), manifest,
                    read_source=lambda path: None, expected_manifest_path=ref))
                input_ref = runtime_paths(row['source_ref'], summary)[0]
                self.assertTrue(source_record_errors(row, json.dumps(summary), manifest,
                    read_source=lambda path: b'[]' if path == input_ref else reader(path), expected_manifest_path=ref))
                self.assertTrue(source_record_errors(row, json.dumps(summary), manifest, read_source=None))

    def test_real_proposal_gate_and_append_schema_accept_four_dispositions(self):
        from scripts.python.tests.test_mvg_input_envelope import InputEnvelopeTests
        from _planning_skill_common import load_json
        import jsonschema
        case = InputEnvelopeTests(); case.setUp(); self.addCleanup(case.doCleanups)
        root = case.root; state = case.prepare(); prepared = case.run / 'analysis-input'
        semantics = load_json(prepared / 'semantic-requirements.v1.json')
        rid = semantics['requirements'][0]['requirement_id']
        semantics['requirements'][0]['non_task_sinks'] = [{'id': 'review-sink'}]
        atomic_json(prepared / 'semantic-requirements.v1.json', semantics)
        ref = 'docs/testing/verification.md'
        for path in (root / ref, prepared / 'references' / ref):
            atomic_json(path, {'status': 'reviewed'})
        index = load_json(prepared / 'analysis-index.json')
        index['files']['references/' + ref] = file_sha(root / ref)
        index['authority_inputs'][ref] = file_sha(root / ref)
        atomic_json(prepared / 'analysis-index.json', index)
        cid = load_json(prepared / 'capabilities.v1.json')['capabilities'][0]['capability_id']
        base = seed_proposal(state, prepared)
        scope = {'capability_id': cid, 'new_requirement_ids': [rid], 'cumulative_requirement_ids': [rid]}
        schema = append_output_schema(state, scope, base, prepared)
        for disposition in ('flow', 'other_verification', 'deferred', 'source_gap'):
            value = project_accounting(fixture())
            value.update(schema_version=plan_mvg.PROPOSAL_SCHEMA, analysis_identity_sha256=state['analysis_identity_sha256'],
                         planning_status='ready_for_validation', gaps=[])
            value['manifest_candidate']['tests'] = []
            for flow in value['manifest_candidate']['flows']:
                flow.update(requirement_ids=[rid], capability_refs=[cid])
            for row in value['requirement_route_memberships']:
                row['requirement_id'] = rid
            owner = {'requirement_id': rid, 'capability_ref': cid, 'task_id': 7, 'disposition': disposition,
                'rationale': 'Reviewed behavior', 'flow_id': 'flow-a' if disposition == 'flow' else None,
                'sink_id': 'review-sink' if disposition == 'other_verification' else None,
                'verification_ref': ref if disposition == 'other_verification' else None,
                'authority_ref': ref if disposition == 'deferred' else None,
                'authority_review': {'status': 'reviewed', 'rationale': 'Authorized'} if disposition == 'deferred' else None}
            value['coverage_table'] = [owner]; value[VERIFICATION] = [{**owner, 'evidence_ids': []}]
            for key, rows in (('coverage_table', [owner]), (VERIFICATION, value[VERIFICATION])):
                jsonschema.validate(rows, schema['properties'][key])
            with patch.object(plan_mvg, 'validate_manifest', return_value=[]):
                result = plan_mvg.validate_proposal(root, state, value, append_requirement_ids={rid})
            self.assertEqual([], result['errors'], (disposition, result))
            self.assertEqual(disposition != 'source_gap', result['formal_applicable'])
            if disposition == 'source_gap':
                self.assertIn('requirement_source_gap:' + rid, result['formal_blockers'])

    def test_public_generate_checkpoint_trace_next_seed(self):
        from scripts.python.tests.test_mvg_capability_append import CapabilityAppendTests
        CapabilityAppendTests().exercise_public_generation(multi_route=True, coordinator_case='apply-replay',
                                                          accounting_evidence=True)

    def test_public_review_rejects_accounting_matrix_without_model_calls(self):
        from test_mvg_planning_contract import MvgPlanningContractTests
        from _mvg_requirement_routes import project_routes
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root, run, state, value = MvgPlanningContractTests().admission_fixture(temp.name)
        base = project_accounting(project_routes(value))
        base.pop('requirement_routes_projection', None)
        rid = 'R1'
        self.assertEqual([], plan_mvg.candidate_admission_errors(root, state, base))
        expected = {'missing-authority': 'requirement_verification_missing:R1',
            'duplicate-authority': 'requirement_verification_duplicate:R1',
            'duplicate-route': 'requirement_route_pair_duplicate:R1:flow-a',
            'unknown-evidence': 'requirement_evidence_unknown_requirement:',
            'unprepared-evidence': 'requirement_evidence_not_prepared:',
            'bad-flow-test': 'unknown or empty test coverage', 'orphan-test': 'not assigned to a flow',
            'null-coverage': 'requirement_accounting_coverage_not_array',
            'bad-manifest-key': 'requirement_accounting_object_key_invalid:',
            'bad-owner-task': 'coverage_flow_membership_invalid:R1',
            'bad-owner-capability': 'coverage_flow_membership_invalid:R1',
            'bad-owner-flow': 'coverage_flow_membership_invalid:R1'}
        for mutation in expected:
            with self.subTest(mutation=mutation):
                value = deepcopy(base)
                if mutation == 'missing-authority':
                    value[VERIFICATION] = []
                elif mutation == 'duplicate-authority':
                    value[VERIFICATION].append(deepcopy(value[VERIFICATION][0]))
                elif mutation == 'duplicate-route':
                    value['requirement_route_memberships'].append(deepcopy(value['requirement_route_memberships'][0]))
                elif mutation in ('unknown-evidence', 'unprepared-evidence'):
                    value[VERIFICATION][0]['evidence_ids'] = ['proof']
                    value[EVIDENCE] = [{**proposal()[EVIDENCE][0], 'evidence_id': 'proof',
                        'requirement_id': 'unknown' if mutation == 'unknown-evidence' else rid,
                        'flow_ids': ['flow-a']}]
                elif mutation == 'bad-flow-test':
                    value['manifest_candidate']['flows'][0]['test_ids'] = ['unknown-test']
                elif mutation == 'orphan-test':
                    from _mvg_requirement_accounting import boundary_errors
                    value['manifest_candidate']['tests'].append({**value['manifest_candidate']['tests'][0], 'id': 'orphan-test'})
                    self.assertIn('requirement_accounting_test_flow_missing:orphan-test',
                                  boundary_errors(value, {rid}))
                elif mutation == 'null-coverage':
                    value['coverage_table'] = None
                elif mutation.startswith('bad-owner'):
                    field = {'bad-owner-task': 'task_id', 'bad-owner-capability': 'capability_ref', 'bad-owner-flow': 'flow_id'}[mutation]
                    for row in (value['coverage_table'][0], value[VERIFICATION][0]):
                        row[field] = 999 if field == 'task_id' else 'unknown'
                else:
                    value['manifest_candidate']['flows'][0]['id'] = []
                atomic_json(run / 'proposal.json', value)
                with patch.object(plan_mvg, 'run_isolated_model') as model, \
                     patch.object(plan_mvg, 'inspect_isolated_runner') as inspect:
                    errors = plan_mvg.candidate_admission_errors(root, state, value)
                    self.assertIn(expected[mutation], ';'.join(row['code'] for row in errors))
                    with self.assertRaises(ValueError):
                        plan_mvg.review(root, run_id='contract', runner=Path('unused'), timeout_sec=1)
                    with self.assertRaisesRegex(ValueError, 'accounting admission blocked'):
                        plan_mvg.run_admission_semantic_gate(root, state, value, run / 'unused',
                            runner=None, timeout_sec=1, invoke=model)
                    model.assert_not_called(); inspect.assert_not_called()

    def test_proof_rejects_invalid_prefix_even_when_final_accounting_is_valid(self):
        from _mvg_capability_generation import admission_proof, append_proof_errors
        from _mvg_planning_review import semantic_review_errors
        state = {'analysis_identity_sha256': 'fixture'}
        seed = {'manifest_candidate': {'flows': [], 'tests': []}, 'coverage_table': [],
                'tests': [], 'entrypoints': [], 'notes': [], VERIFICATION: [], EVIDENCE: [],
                'requirement_route_memberships': []}
        scopes = [{'capability_id': cid, 'requirement_ids': ['RQ-1'],
                   'new_requirement_ids': ['RQ-1'] if cid == 'CAP-A' else [],
                   'cumulative_requirement_ids': ['RQ-1']} for cid in ('CAP-A', 'CAP-B')]
        owner = deepcopy(fixture()['coverage_table'][0])
        deltas = [{'flows': fixture()['manifest_candidate']['flows'], 'coverage_table': [owner],
                   VERIFICATION: [{**owner, 'evidence_ids': []}], EVIDENCE: [],
                   'requirement_route_memberships': fixture()['requirement_route_memberships'][:1]},
                  {'requirement_route_memberships': fixture()['requirement_route_memberships'][1:]}]
        records, accepted = [], deepcopy(seed)
        for scope, delta in zip(scopes, deltas):
            revised = merge_append(accepted, delta, scope)
            record = {'scope': scope, 'base_sha256': canonical_sha(accepted),
                      'proposal_sha256': canonical_sha(revised), 'delta': delta, 'proof': {}, 'execution': {}}
            record['record_sha256'] = canonical_sha(record); records.append(record); accepted = revised
        self.assertEqual([], accounting_errors(accepted, {'RQ-1'}))
        from _mvg_requirement_routes import route_errors
        self.assertEqual([], route_errors(accepted, {'RQ-1'}))
        proof = admission_proof(state, seed, scopes, records, accepted)
        before = canonical_sha(proof)
        errors = semantic_review_errors(state, accepted, proof, {'requirements': [{'requirement_id': 'RQ-1'}]})
        self.assertIn('capability_admission_prefix:CAP-A:requirement_route_pair_missing:RQ-1:flow-b', errors)
        self.assertEqual(before, canonical_sha(proof))
        for malformed in ({'scopes': [None]}, {'records': [None]}, {'seed': {'coverage_table': None}}):
            value = {**proof, **malformed}
            self.assertTrue(append_proof_errors(state, accepted, value, {'requirements': [{'requirement_id': 'RQ-1'}]}))
        delta = {**deltas[0], 'requirement_route_memberships': fixture()['requirement_route_memberships']}
        final = merge_append(seed, delta, scopes[0])
        for malformed in ([1], 'invalid', {'required_requirement_ids': [{}], 'review': {}}):
            record = {**records[0], 'delta': delta, 'proposal_sha256': canonical_sha(final), 'proof': malformed}
            record.pop('record_sha256'); record['record_sha256'] = canonical_sha(record)
            value = admission_proof(state, seed, scopes[:1], [record], final)
            self.assertIn('capability_admission_record_shape_invalid:CAP-A',
                append_proof_errors(state, final, value, {'requirements': [{'requirement_id': 'RQ-1'}]}))
        from _mvg_capability_generation import review_projection
        projection, required = review_projection(scopes[0], seed, final)
        review = {'schema_version': 'newrouge.mvg-semantic-review.v1',
                  'analysis_identity_sha256': 'fixture', 'proposal_sha256': canonical_sha(projection),
                  'verdict': 'approved', 'findings': [],
                  'requirement_reviews': [{'requirement_id': 'RQ-1', 'verdict': 'covered', 'rationale': 'Accepted'}],
                  'flow_reviews': [{'flow_id': fid, 'verdict': 'sound', 'rationale': 'Accepted'}
                                   for fid in ('flow-a', 'flow-b')]}
        bound = {'projection': projection, 'required_requirement_ids': sorted(required), 'review': review}
        for execution in ({'receipt': ['invalid']}, {'runner_info': ['invalid']}, {'receipt': 'invalid'},
                          {'receipt': []}, {'runner_info': None}):
            record = {**records[0], 'delta': delta, 'proposal_sha256': canonical_sha(final),
                      'proof': bound, 'execution': execution}
            record.pop('record_sha256'); record['record_sha256'] = canonical_sha(record)
            value = admission_proof(state, seed, scopes[:1], [record], final)
            errors = append_proof_errors(state, final, value, {'requirements': [{'requirement_id': 'RQ-1'}]})
            self.assertTrue(any(error.startswith('capability_admission_record_invalid:CAP-A:') for error in errors), errors)

    def test_coverage_projection_retains_future_flow_tests_with_explicit_owner(self):
        from _mvg_requirement_accounting import boundary_errors
        value = project_accounting(fixture())
        value['manifest_candidate']['flows'] = value['manifest_candidate']['flows'][:1]
        value['requirement_route_memberships'] = value['requirement_route_memberships'][:1]
        value['manifest_candidate']['tests'] = [{'id': 'future', 'flow_id': 'flow-b'}]
        self.assertEqual([], boundary_errors(value, {'RQ-1'}, check_test_links=False))
        self.assertIn('requirement_accounting_test_flow_mismatch:future:flow-b', boundary_errors(value, {'RQ-1'}))


if __name__ == '__main__':
    unittest.main()
