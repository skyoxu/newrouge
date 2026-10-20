"""Bounded cumulative synthesis must consume every analysis without truncation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openai_isolated_model_runner as api
import plan_capabilities as planning
import codex_isolated_model_runner as codex
from _capability_input_integrity import measure_request
from _planning_skill_common import atomic_json


class CapabilityStagedSynthesisTests(unittest.TestCase):
    def test_review_synthesis_keeps_review_contract_instead_of_generating_candidate(self):
        text = api._staged_synthesis_request(original_prompt=planning.REVIEW_PROMPT,
            base='anonymous candidates', batch_outputs=[('one', '{}')],
            previous={'source_fidelity_findings': ['Prior gap']}, stage=2, stage_count=2,
            review=True)
        self.assertIn('complete review report', text)
        self.assertIn('Prior gap', text)
        self.assertNotIn('Synthesize the final Capability candidate now', text)
        self.assertNotIn('Return a complete candidate', text)

    def test_review_draft_rejects_candidate_shaped_output(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / 'candidates').mkdir()
            with self.assertRaisesRegex(ValueError, 'invalid_review_schema'):
                api._validate_synthesis_draft('{"capabilities":[]}', workspace=workspace,
                    schema_path=None, token_limit=4000, byte_limit=100000)

    def test_byte_heavy_analyses_are_partitioned_even_when_tokens_fit(self):
        plan = api._synthesis_plan('fixed context',
            analysis_budgets=[('a', 100), ('b', 100), ('c', 100)],
            analysis_bytes={'a': 8000, 'b': 8000, 'c': 8000},
            max_bytes=20000, max_input_tokens=96000, reserved_tokens=100)
        self.assertEqual('staged', plan['mode'])
        self.assertEqual(['a', 'b', 'c'],
            [label for stage in plan['stages'] for label in stage['labels']])
        self.assertGreater(len(plan['stages']), 1)

    def plan(self, budgets):
        return api._synthesis_plan('fixed context', analysis_budgets=budgets,
            max_bytes=1048576, max_input_tokens=20000, reserved_tokens=4000)

    def test_small_input_keeps_one_synthesis(self):
        plan = self.plan([('first', 4096)])
        self.assertEqual('single', plan['mode'])
        self.assertEqual([['first']], [stage['labels'] for stage in plan['stages']])

    def test_complete_source_output_can_exceed_estimate_and_replan_synthesis(self):
        # An estimate must not reject a schema-valid complete response.
        value = {'source_block_analyses': [
            {'source_block_id': f'SB-{index}', 'summary': f'Outcome {index} ' +
             ''.join(f'{(index * 7919 + part * 104729) % 65536:04x}' for part in range(160)),
             'boundary_signals': ['owner boundary']} for index in range(54)],
            'requirement_analyses': []}
        packed, actual_tokens = api._admit_analysis_for_synthesis(
            value, max_bytes=1048576, max_input_tokens=96000)
        self.assertGreater(actual_tokens, 4096)
        self.assertEqual(value['source_block_analyses'][0]['summary'],
                         dict(zip(packed['source_block_analyses']['columns'],
                                  packed['source_block_analyses']['rows'][0]))['summary'])
        plan = api._synthesis_plan('fixed context',
            analysis_budgets=[('batch-001', actual_tokens)], max_bytes=1048576,
            max_input_tokens=96000, reserved_tokens=16000)
        self.assertEqual(['batch-001'], plan['stages'][0]['labels'])

    def test_single_analysis_exceeding_real_context_remains_blocked(self):
        with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
            api._admit_analysis_for_synthesis({'rows': ['large ' * 1000]},
                max_bytes=1048576, max_input_tokens=100)

    def test_real_failed_source_batch_is_accepted_without_loss(self):
        root = Path(__file__).resolve().parents[3]
        old = root / 'logs/ci/capability-planning/capability-codex-real-20261020-budget-01'
        workspace = old / 'isolated-workspaces/candidate-1/attempt-1'
        output = workspace / 'batch-analyses/batch-002.json'
        payload_path = workspace / 'analysis-input/model-batches/batch-002.json'
        if not output.is_file() or not payload_path.is_file():
            self.skipTest('Local real-model failure evidence is unavailable')
        value = json.loads(output.read_text(encoding='utf-8'))
        payload = json.loads(payload_path.read_text(encoding='utf-8'))
        validated = api._validate_batch_analysis(value, payload, {})
        packed, tokens = api._admit_analysis_for_synthesis(validated,
            max_bytes=1048576, max_input_tokens=96000)
        self.assertGreater(tokens, api._analysis_output_budget(payload))
        self.assertEqual(len(payload['blocks']),
                         len(packed['source_block_analyses']['rows']))
        self.assertEqual(len(payload['requirements']),
                         len(packed['requirement_analyses']['rows']))

    def test_codex_budget_contract_reserves_remaining_dispatches(self):
        runner = codex.description()
        state = {'budget': {'request_limit': 96, 'model_requests_observed': 48,
            'model_requests_reserved': 0}}
        self.assertEqual(48, planning._attempt_request_allowance(state, runner))
        self.assertTrue(runner['supports_request_budget'])
        self.assertEqual('exact_per_runner_invocation', runner['request_accounting'])

    def test_large_aggregate_is_partitioned_with_exact_batch_conservation(self):
        budgets = [(f'batch-{i}', 4096) for i in range(10)]
        plan = self.plan(budgets)
        self.assertEqual('staged', plan['mode'])
        self.assertGreater(len(plan['stages']), 1)
        self.assertEqual([label for label, _ in budgets],
                         [label for stage in plan['stages'] for label in stage['labels']])
        for stage in plan['stages']:
            report = stage['capacity']
            self.assertLessEqual(report['input_token_estimate']
                                 + report['reserved_continuation_tokens'], 20000)

    def test_single_oversized_analysis_is_rejected_before_dispatch(self):
        with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
            self.plan([('oversized', 19000)])

    def test_duplicate_batch_labels_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.plan([('same', 4096), ('same', 4096)])

    def test_staged_request_preserves_full_current_evidence_and_previous_draft(self):
        draft = {'marker': 'previous full draft', 'nested': ['not truncated']}
        output = json.dumps({'task_view_analyses': [{'marker': 'complete new evidence'}]})
        text = api._staged_synthesis_request(original_prompt='original', base='base',
            batch_outputs=[('task-1', output)], previous=draft, stage=2, stage_count=3)
        self.assertIn('complete new evidence', text)
        self.assertIn('previous full draft', text)
        self.assertIn('not truncated', text)
        self.assertIn('original', text)

    def test_bad_intermediate_json_stops_before_next_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'synthesis_draft_invalid'):
                api._validate_synthesis_draft('not JSON', workspace=Path(directory),
                    schema_path=None, token_limit=4000, byte_limit=100000)

    def test_formal_draft_rejects_missing_authoritative_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            ledger = {'blocks': [{'block_id': 'SB-1'}]}
            semantics = {'requirements': [{'requirement_id': 'RQ-1',
                'status': 'active', 'delivery_relevant': True}]}
            atomic_json(workspace / 'analysis-input/source-blocks.v1.json', ledger)
            atomic_json(workspace / 'analysis-input/semantic-requirements.v1.json', semantics)
            atomic_json(workspace / 'analysis-input/analysis-index.json',
                {'analysis_identity_sha256': 'sha256:fixture'})
            schema = workspace / 'candidate-schema.json'
            atomic_json(schema, planning.candidate_output_schema(ledger, semantics))
            candidate = {'schema_version': planning.CANDIDATE_SCHEMA,
                'analysis_identity_sha256': 'sha256:fixture', 'capabilities': [],
                'ungrouped_requirements': [], 'multi_membership_rationales': [],
                'source_accounting': {'0': {'disposition': 'unassigned',
                    'capability_ids': [], 'rationale': 'pending later synthesis evidence'}},
                'questions': [], 'generation_notes': []}
            with self.assertRaisesRegex(ValueError, 'delivery_requirements_unaccounted'):
                api._validate_synthesis_draft(json.dumps(candidate), workspace=workspace,
                    schema_path=schema, token_limit=4000, byte_limit=100000)
            candidate['ungrouped_requirements'] = [{'requirement_id': 'RQ-1',
                'reason': 'pending later synthesis evidence'}]
            self.assertEqual(candidate, api._validate_synthesis_draft(json.dumps(candidate),
                workspace=workspace, schema_path=schema, token_limit=4000, byte_limit=100000))

    def execute(self, directory, dispatch, analyses=None):
        analyses = analyses or [(f'batch-{i}', json.dumps({'evidence': f'FULL_EVIDENCE_{i}'})) for i in range(10)]
        plan = self.plan([(label, 4096) for label, _ in analyses])
        output = Path(directory) / 'final.json'
        api._execute_synthesis_plan(plan=plan, analyses=analyses, original_prompt='original',
            base='base', checklist='all IDs', workspace=Path(directory), output_path=output,
            schema_path=None, output_tokens=4000,
            measured=lambda text, reserve: measure_request(text, max_bytes=1048576,
                max_input_tokens=20000, reserved_tokens=reserve),
            dispatch=dispatch, event=lambda *args: None)
        return plan, output

    def test_every_stage_passes_complete_previous_draft_and_publishes_only_final(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            def dispatch(text, target):
                self.assertFalse((Path(directory) / 'final.json').exists())
                if sent:
                    self.assertIn(f'RESULT_{len(sent)}', text)
                sent.append(text)
                return json.dumps({'result': f'RESULT_{len(sent)}'})
            plan, output = self.execute(directory, dispatch)
            self.assertEqual(len(plan['stages']), len(sent))
            for index in range(10):
                self.assertEqual(1, sum(f'FULL_EVIDENCE_{index}' in text for text in sent))
            self.assertEqual(f'RESULT_{len(sent)}', json.loads(output.read_text())['result'])
            receipts = sorted((Path(directory) / 'synthesis-stages').glob('*.receipt.json'))
            last = json.loads(receipts[-1].read_text())
            self.assertEqual([f'batch-{i}' for i in range(10)], last['consumed_labels'])
            self.assertTrue(last['eligible_for_selection'])

    def test_invalid_stage_blocks_next_call_and_preserves_existing_final(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'final.json'
            output.write_text('{"old":"preserved"}')
            def dispatch(text, target):
                calls.append(text)
                return 'invalid JSON'
            with self.assertRaisesRegex(ValueError, 'synthesis_draft_invalid'):
                self.execute(directory, dispatch)
            self.assertEqual(1, len(calls))
            self.assertEqual({'old': 'preserved'}, json.loads(output.read_text()))

    def test_actual_late_request_overflow_blocks_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(api, '_staged_synthesis_request', return_value='oversized ' * 30000):
                dispatch = unittest.mock.Mock()
                with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                    # Precomputed plan; test actual transport gate independently.
                    api._execute_synthesis_plan(plan={'mode':'staged', 'draft_byte_limit':100000,
                        'stages':[{'labels':['one']}]}, analyses=[('one','{}')], original_prompt='',
                        base='', checklist='', workspace=Path(directory), output_path=Path(directory)/'out.json',
                        schema_path=None, output_tokens=4000,
                        measured=lambda text, reserve: measure_request(text, max_bytes=1048576,
                            max_input_tokens=20000, reserved_tokens=reserve),
                        dispatch=dispatch, event=lambda *args: None)
                dispatch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
