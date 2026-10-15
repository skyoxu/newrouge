"""Offline public-entrypoint coverage for checkpoint-bound apply recovery."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _planning_apply_journal as journal
import plan_mvg
import test_mvg_capability_append as append_fixture
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, text_sha


class CheckpointJournalTests(unittest.TestCase):
    def exercise(self):
        append_fixture.CapabilityAppendTests().exercise_public_generation(coordinator_case="apply-replay")

    def test_pending_journal_rejects_changed_or_deleted_checkpoint_authority_before_target_writes(self):
        for mutation in ("payload", "deleted-payload", "state-pointer", "protocol-delete",
                         "missing-binding", "missing-binding-protocol-delete", "receipt"):
            with self.subTest(mutation=mutation):
                original = journal.create_journal
                observed = []

                def create(root, path, targets, *args, **kwargs):
                    before = {target: file_sha(target) if target.is_file() else None for target in targets}
                    result = original(root, path, targets, *args, **kwargs)
                    state_path = path.parent / "run.json"
                    state = load_json(state_path)
                    step = state["capability_selection"]["selected"][0]
                    payload_path = path.parent / step["checkpoint"]["path"]
                    if mutation == "payload":
                        payload = load_json(payload_path)
                        payload["accepted"]["notes"].append("changed-after-journal")
                        atomic_json(payload_path, payload)
                    elif mutation == "deleted-payload":
                        payload_path.unlink()
                    elif mutation == "state-pointer":
                        step["checkpoint"]["payload_sha256"] = "sha256:changed"
                        atomic_json(state_path, state)
                    elif mutation == "protocol-delete":
                        state.pop("checkpoint_strategy")
                        state.pop("checkpoint_schema_version")
                        atomic_json(state_path, state)
                    elif mutation.startswith("missing-binding"):
                        changed = deepcopy(result)
                        changed["result"].pop("_mvg_checkpoint_binding")
                        atomic_json(path, changed)
                        if mutation.endswith("protocol-delete"):
                            state.pop("checkpoint_strategy")
                            state.pop("checkpoint_schema_version")
                            atomic_json(state_path, state)
                    else:
                        receipt = path.parent / step["receipt_path"]
                        changed = load_json(receipt)
                        changed["attempt"] = 100
                        atomic_json(receipt, changed)
                    observed.append((path, before))
                    return result

                with patch.object(journal, "create_journal", side_effect=create):
                    # The fixture owns and removes its temporary checkout, so
                    # inspect target hashes while unwinding the rejected apply.
                    original_apply = plan_mvg.apply

                    def apply(*args, **kwargs):
                        try:
                            return original_apply(*args, **kwargs)
                        except ValueError:
                            for journal_path, before in observed:
                                self.assertEqual("pending", load_json(journal_path)["status"])
                                for target, expected in before.items():
                                    self.assertEqual(expected, file_sha(target) if target.is_file() else None)
                            raise

                    with patch.object(plan_mvg, "apply", side_effect=apply), \
                         self.assertRaisesRegex(ValueError, "checkpoint journal (evidence|binding)"):
                        self.exercise()
                self.assertEqual(1, len(observed))

    def test_completed_journal_rejects_checkpoint_tampering_on_replay(self):
        original = journal.resume_journal
        observed = []

        def resume(root, path, writer):
            result = original(root, path, writer)
            self.assertEqual("complete", load_json(path)["status"])
            state = load_json(path.parent / "run.json")
            pointer = state["capability_selection"]["selected"][0]["checkpoint"]
            payload_path = path.parent / pointer["path"]
            payload = load_json(payload_path)
            payload["accepted"]["notes"].append("changed-after-complete")
            atomic_json(payload_path, payload)
            observed.append(True)
            return result

        with patch.object(journal, "resume_journal", side_effect=resume), \
             self.assertRaisesRegex(ValueError, "checkpoint journal evidence changed"):
            self.exercise()
        self.assertEqual([True], observed, "Replay must reject drift before reentering the journal writer")

    def test_completed_replay_preserves_mutable_handoff_bindings_and_public_result(self):
        original = journal.resume_journal
        calls = []

        def resume(root, path, writer):
            result = original(root, path, writer)
            self.assertIn("_mvg_checkpoint_binding", result)
            trace_path = root / result["trace_path"]
            trace = load_json(trace_path)
            trace["handoff_bindings"] = {"fixture-task": {"status": "valid"}}
            atomic_json(trace_path, trace)
            calls.append(True)
            return result

        original_apply = plan_mvg.apply

        def apply(*args, **kwargs):
            result = original_apply(*args, **kwargs)
            self.assertNotIn("_mvg_checkpoint_binding", result)
            return result

        with patch.object(journal, "resume_journal", side_effect=resume), \
             patch.object(plan_mvg, "apply", side_effect=apply):
            self.exercise()
        self.assertEqual(2, len(calls))

    def test_pending_accounting_matrix_blocks_all_writes_and_recovers_partial_targets(self):
        original_create = journal.create_journal
        observed = []

        def create(root, path, targets, *args, **kwargs):
            result = original_create(root, path, targets, *args, **kwargs)
            before = {target: target.read_bytes() if target.is_file() else None for target in targets}
            for mutation in ('missing-authority', 'duplicate-route', 'unknown-evidence', 'unprepared-evidence',
                             'malformed-accounting', 'scope', 'manifest', 'extra-target', 'authority-deleted',
                             'mutable-authority', 'trace-protocol-delete', 'trace-verification-delete',
                             'trace-evidence-delete', 'proposal-protocol-delete', 'proposal-verification-delete',
                             'proposal-evidence-delete', 'result-readiness-delete', 'result-tasks-delete',
                             'owner-task', 'owner-capability', 'owner-flow', 'deferred-authority'):
                with self.subTest(mutation=mutation):
                    changed = deepcopy(result)
                    trace = next(row for row in changed['entries'] if row['path'] == result['result']['trace_path'])
                    payload = trace['payload']
                    proposal_path = path.parent / 'proposal.json'
                    original_proposal = proposal_path.read_bytes()
                    if mutation == 'missing-authority':
                        payload['requirement_verification'] = []
                    elif mutation.startswith('owner-'):
                        field = {'owner-task': 'task_id', 'owner-capability': 'capability_ref', 'owner-flow': 'flow_id'}[mutation]
                        for owner in (payload['coverage_table'][0], payload['requirement_verification'][0]):
                            owner[field] = 999 if field == 'task_id' else 'unknown'
                    elif mutation == 'deferred-authority':
                        for owner in (payload['coverage_table'][0], payload['requirement_verification'][0]):
                            owner.update(disposition='deferred', flow_id=None, authority_ref='docs/unprepared.md',
                                         authority_review={'status': 'reviewed', 'rationale': 'Claimed authority'})
                    elif mutation == 'duplicate-route':
                        payload['requirement_route_memberships'].append(deepcopy(payload['requirement_route_memberships'][0]))
                    elif mutation == 'malformed-accounting':
                        payload['requirement_verification'] = None
                    elif mutation in ('unknown-evidence', 'unprepared-evidence'):
                        payload['requirement_evidence'][0]['source_ref'] = 'docs/unprepared.json'
                        if mutation == 'unknown-evidence':
                            payload['requirement_evidence'][0]['requirement_id'] = 'unknown'
                    elif mutation == 'scope':
                        payload['requirement_evidence'][0]['test_ids'] = ['unknown-test']
                    elif mutation == 'manifest':
                        next(row for row in changed['entries'] if row is not trace)['payload']['mvg_id'] = 'changed'
                    elif mutation == 'extra-target':
                        changed['entries'].append({**deepcopy(trace), 'path': 'docs/unexpected.json'})
                    elif mutation == 'mutable-authority':
                        trace['mutable_json_keys_after_complete'] = ['requirement_verification']
                    elif mutation.startswith(('trace-', 'proposal-')):
                        field = {'protocol': 'requirement_accounting_protocol', 'verification': 'requirement_verification',
                                 'evidence': 'requirement_evidence'}[mutation.split('-')[1]]
                        if mutation.startswith('trace-'):
                            payload.pop(field)
                        else:
                            changed_proposal = load_json(proposal_path); changed_proposal.pop(field)
                            atomic_json(proposal_path, changed_proposal)
                    elif mutation.startswith('result-'):
                        changed['result'].pop('post_apply_task_readiness' if 'readiness' in mutation else 'handoff_review_required_tasks')
                    else:
                        changed['authority_inputs'] = {}
                    for row in changed['entries']:
                        import json
                        row['after_sha256'] = text_sha(json.dumps(row['payload'], ensure_ascii=False, indent=2) + '\n')
                    atomic_json(path, changed)
                    digest = file_sha(path)
                    with patch.object(journal, 'resume_journal', side_effect=AssertionError('Unexpected target writer')) as resume:
                        with self.assertRaisesRegex(ValueError, 'journal (accounting|evidence)') as rejected:
                            plan_mvg.apply(root, run_id='fixture', confirm=True)
                        if mutation.startswith('owner-'):
                            self.assertIn('coverage_flow_membership_invalid:FR-a', str(rejected.exception))
                        elif mutation == 'deferred-authority':
                            self.assertIn('coverage_deferral_unreviewed:FR-a', str(rejected.exception))
                        resume.assert_not_called()
                    proposal_path.write_bytes(original_proposal)
                    self.assertEqual(digest, file_sha(path))
                    for target, data in before.items():
                        self.assertEqual(data, target.read_bytes() if target.is_file() else None)
            atomic_json(path, result)
            # Model a process crash after the first target was already written.
            first = result['entries'][0]
            atomic_json(root / first['path'], first['payload'])
            observed.append(True)
            return result

        with patch.object(journal, 'create_journal', side_effect=create):
            append_fixture.CapabilityAppendTests().exercise_public_generation(
                coordinator_case='apply-replay', multi_route=True, accounting_evidence=True)
        self.assertEqual([True], observed)

    def test_legacy_completed_public_replay_keeps_original_hashes_counts_and_read_routes(self):
        from test_mvg_requirement_routes import fixture
        from _mvg_requirement_accounting import accounting_summary, project_accounting
        from _mvg_requirement_routes import project_routes
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); run = root / plan_mvg.DEFAULT_RUN_ROOT / 'legacy'
            prepared = run / 'analysis-input'
            proposal = fixture(); proposal.pop('requirement_route_memberships')
            proposal.update(schema_version=plan_mvg.PROPOSAL_SCHEMA,
                            planning_status='ready_for_validation', gaps=[])
            proposal['coverage_table'][0]['original_owner'] = {'task_id': 7}
            proposal['coverage_table'].append({'requirement_id': 'RQ-2', 'disposition': 'other_verification',
                'sink_id': 'historical-review', 'rationale': 'Original evidence',
                'verification_ref': 'docs/testing/old-proof.json#original'})
            source = {'evidence_id': 'original', 'status': 'passed', 'requirement_ids': ['RQ-2'], 'flow_ids': [], 'test_ids': [],
                      'covered_behavior': 'Original evidence'}
            atomic_json(root / 'docs/testing/old-proof.json', source)
            snapshots = {'semantic-requirements.v1.json': {'requirements': [
                {'requirement_id': rid, 'non_task_sinks': [{'id': 'historical-review'}]} for rid in ('RQ-1', 'RQ-2')]},
                'capabilities.v1.json': {'capabilities': [{'capability_id': 'CAP-A', 'requirement_ids': ['RQ-1', 'RQ-2']}]},
                'references/docs/testing/old-proof.json': source}
            for name, value in snapshots.items():
                atomic_json(prepared / name, value)
            index = {'files': {name: file_sha(prepared / name) for name in snapshots},
                     'authority_inputs': {'docs/testing/old-proof.json': file_sha(root / 'docs/testing/old-proof.json')}}
            identity = canonical_sha(index); index['analysis_identity_sha256'] = identity
            atomic_json(prepared / 'analysis-index.json', index)
            proposal['analysis_identity_sha256'] = identity
            atomic_json(run / 'proposal.json', proposal)
            state = {'schema_version': plan_mvg.RUN_SCHEMA, 'run_id': 'legacy',
                     'analysis_identity_sha256': identity, 'manifest_path': 'docs/testing/mvg/legacy.json'}
            atomic_json(run / 'run.json', state)
            review = {'schema_version': 'newrouge.mvg-semantic-review.v1', 'analysis_identity_sha256': identity,
                'proposal_sha256': canonical_sha(proposal), 'verdict': 'approved', 'findings': [],
                'requirement_reviews': [{**row, 'verdict': 'covered' if row['disposition'] == 'flow' else 'other_verification'}
                                        for row in proposal['coverage_table']],
                'flow_reviews': [{'flow_id': flow['id'], 'verdict': 'sound', 'rationale': 'Original review'}
                                 for flow in proposal['manifest_candidate']['flows']]}
            execution = {'analysis_identity_sha256': identity, 'proposal_sha256': canonical_sha(proposal),
                'semantic_review_sha256': canonical_sha(review), 'runner_info': {
                    'schema_version': 'newrouge.isolated-model-runner.v1', 'filesystem_scope': 'workspace_only',
                    'fresh_session_per_invocation': True, 'can_read_outside_workspace': False,
                    'model': 'fixture', 'model_tools': []}, 'receipt': {'model': 'fixture', 'model_tools': []}}
            atomic_json(run / 'semantic-review.json', review)
            atomic_json(run / 'semantic-review-execution.json', execution)
            manifest = proposal['manifest_candidate']
            digest = text_sha(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            trace_ref = (plan_mvg.FORMAL_TRACE_ROOT / 'legacy.json').as_posix()
            trace = {**deepcopy(proposal), 'applied_manifest_candidate': manifest,
                     'applied_manifest_path': state['manifest_path'], 'applied_manifest_sha256': digest}
            result = {'status': 'applied', 'manifest_path': state['manifest_path'], 'manifest_sha256': digest,
                      'trace_path': trace_ref, 'post_apply_task_readiness': [], 'handoff_review_required_tasks': []}
            path = run / 'apply-journal.json'
            journal.create_journal(root, path, {root / trace_ref: trace, root / state['manifest_path']: manifest},
                                   index['authority_inputs'], result)
            journal.resume_journal(root, path, atomic_json)
            immutable = [path, run / 'proposal.json', run / 'semantic-review.json', root / trace_ref]
            before = {item: file_sha(item) for item in immutable}
            reader = lambda ref: (root / ref).read_text(encoding='utf-8')
            valid_keys = {('RQ-2', 'legacy-verification')}
            original_counts = accounting_summary(project_accounting(proposal, read_text=reader), valid_evidence_keys=valid_keys)
            self.assertEqual(1, original_counts['satisfied_count'])
            with patch.object(plan_mvg, 'run_isolated_model') as model:
                self.assertEqual(result, plan_mvg.apply(root, run_id='legacy', confirm=True))
                self.assertEqual(result, plan_mvg.apply(root, run_id='legacy', confirm=True))
                model.assert_not_called()
            read_view = project_accounting(project_routes(load_json(root / trace_ref)), read_text=reader)
            self.assertEqual(original_counts, accounting_summary(read_view, valid_evidence_keys=valid_keys))
            self.assertEqual(proposal['coverage_table'], read_view['coverage_table'])
            self.assertEqual('flow-a', read_view['requirement_route_memberships'][0]['flow_id'])
            self.assertEqual('docs/testing/old-proof.json#original', read_view['requirement_evidence'][0]['source_ref'])
            self.assertEqual(before, {item: file_sha(item) for item in immutable})
            for mutation, expected_error in (('draft', 'planning_status_not_ready'),
                                             ('gaps', 'unresolved_planning_gaps'),
                                             ('source_gap', 'requirement_source_gap:RQ-1')):
                changed = deepcopy(proposal)
                if mutation == 'draft':
                    changed['planning_status'] = 'draft'
                elif mutation == 'gaps':
                    changed['gaps'] = ['Unresolved source']
                else:
                    changed['coverage_table'][0].update(disposition='source_gap', flow_id=None)
                atomic_json(run / 'proposal.json', changed)
                with patch.object(journal, 'resume_journal') as resume:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        plan_mvg.apply(root, run_id='legacy', confirm=True)
                    resume.assert_not_called()
                atomic_json(run / 'proposal.json', proposal)
            self.assertEqual(before, {item: file_sha(item) for item in immutable})


if __name__ == "__main__":
    unittest.main()
