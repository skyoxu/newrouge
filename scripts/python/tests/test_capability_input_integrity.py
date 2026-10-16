"""Capability transport must preserve evidence and reject oversized inputs before model calls."""
from __future__ import annotations

import argparse
import contextlib
import io
import hashlib
import json
import subprocess
import sys
import os
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _planning_skill_common import _write_model_batches, atomic_json, file_sha, load_json
import codex_isolated_model_runner as codex
import copilot_isolated_model_runner as copilot
import openai_isolated_model_runner as api
import _capability_input_integrity as integrity


class CapabilityInputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.analysis = self.root / 'analysis-input'
        self.ledger = {'schema_version': 'newrouge.source-blocks.v1', 'blocks': [
            {'block_id': 'SB-1', 'raw_text': 'First outcome ' + 'a' * 650},
            {'block_id': 'SB-2', 'raw_text': 'Second outcome ' + 'b' * 650}]}
        self.requirements = {'schema_version': 'newrouge.semantic-requirements.v1', 'requirements': [
            {'requirement_id': 'RQ-1', 'source_block_ids': ['SB-1'], 'statement': 'Preserve the original request'},
            {'requirement_id': 'RQ-2', 'source_block_ids': ['SB-2'], 'statement': 'Report retryable failure'}]}
        atomic_json(self.analysis / 'source-blocks.v1.json', self.ledger)
        atomic_json(self.analysis / 'semantic-requirements.v1.json', self.requirements)
        self.index = _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.requirements, char_budget=1000)
        self.index_path = self.analysis / 'model-batches/batch-index.json'
        self.prompt = self.root / 'prompt.txt'
        self.prompt.write_text('Return complete JSON.', encoding='utf-8')
        self.output = self.root / 'candidate.json'
        self.args = argparse.Namespace(workspace=str(self.root), prompt_file=str(self.prompt),
            output=str(self.output), max_bytes=8 * 1024 * 1024, timeout_sec=30, output_schema='')

    def parts(self):
        return api.batched_workspace_parts(self.root, prompt_path=self.prompt, output_path=self.output)

    def test_codex_transport_limit_is_two_megabytes(self):
        self.assertEqual(2 * 1024 * 1024, integrity.CODEX_MAX_TURN_BYTES)

    def invoke(self):
        def fake_exec(command, **kwargs):
            atomic_json(self.output, {'fixture': True})
            return subprocess.CompletedProcess(command, 0, stdout='')
        with patch.object(codex, '_codex_executable', return_value='fixture-codex'), \
             patch.object(codex.subprocess, 'run', side_effect=fake_exec) as executor, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            codex.run(self.args)
        return executor.call_args.kwargs['input'], json.loads(stdout.getvalue())

    def test_task_acceptance_and_descriptions_reach_exact_sent_payload(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'FULL_DESCRIPTION_END',
             'acceptance': ['MANDATORY_ACCEPTANCE_END'], 'test_refs': ['verification.gd']}])
        sent, receipt = self.invoke()
        self.assertIn('FULL_DESCRIPTION_END', sent)
        self.assertIn('MANDATORY_ACCEPTANCE_END', sent)
        self.assertIn('verification.gd', sent)
        self.assertEqual('sha256:' + hashlib.sha256(sent.encode('utf-8')).hexdigest(),
                         receipt['input_integrity']['request_sha256'])
        self.assertTrue(receipt['input_integrity']['complete'])

    def test_batch_hash_drift_blocks_even_when_ids_are_unchanged(self):
        path = self.analysis / self.index['batches'][0]['path']
        row = load_json(path)
        row['blocks'][0]['raw_text'] = 'Shortened text'
        atomic_json(path, row)
        with self.assertRaisesRegex(ValueError, 'batch_hash_mismatch'):
            self.parts()

    def test_rehashed_batch_still_must_match_authoritative_body(self):
        path = self.analysis / self.index['batches'][0]['path']
        row = load_json(path)
        row['requirements'][0]['statement'] = 'Different meaning with the same ID'
        atomic_json(path, row)
        self.index['batches'][0]['sha256'] = file_sha(path)
        atomic_json(self.index_path, self.index)
        with self.assertRaisesRegex(ValueError, 'requirement_body_mismatch'):
            self.parts()

    def test_missing_entire_batch_is_not_hidden_by_matching_index_count(self):
        self.index['batches'].pop()
        self.index['batch_count'] = len(self.index['batches'])
        atomic_json(self.index_path, self.index)
        with self.assertRaisesRegex(ValueError, 'batch_sequence_mismatch|source_block_coverage_mismatch'):
            self.parts()

    def test_duplicate_source_blocks_are_rejected(self):
        first = load_json(self.analysis / self.index['batches'][0]['path'])
        path = self.analysis / self.index['batches'][1]['path']
        row = load_json(path)
        row['blocks'].append(first['blocks'][0])
        atomic_json(path, row)
        self.index['batches'][1].update(sha256=file_sha(path), block_ids=['SB-2', 'SB-1'])
        atomic_json(self.index_path, self.index)
        with self.assertRaisesRegex(ValueError, 'duplicate_source_block'):
            self.parts()

    def test_aggregate_size_is_checked_before_starting_codex(self):
        self.args.max_bytes = 1800
        with patch.object(codex, '_codex_executable') as executable, patch.object(codex.subprocess, 'run') as executor:
            with self.assertRaisesRegex(ValueError, 'runner_input_too_large'):
                codex.run(self.args)
        executable.assert_not_called()
        executor.assert_not_called()

    def test_non_ascii_token_budget_is_checked_before_starting_codex(self):
        self.prompt.write_text('Full evidence: ' + '\u96be\u5ea6' * 1000, encoding='utf-8')
        self.args.max_input_tokens = 1000
        with patch.object(codex, '_codex_executable') as executable:
            with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                codex.run(self.args)
        executable.assert_not_called()

    def test_nonbatch_final_payload_token_gate_blocks_all_transports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prompt = root / "prompt.txt"
            prompt.write_text("Small prompt.", encoding="utf-8")
            schema_path = root / "output-schema.json"
            atomic_json(schema_path, {"type": "object", "description": "schema evidence " * 1500})
            args = argparse.Namespace(workspace=str(root), prompt_file=str(prompt), output=str(root / "out.json"),
                max_bytes=100000, max_input_tokens=100, timeout_sec=1, output_schema=str(schema_path))
            for module, starter in ((codex, "_codex_executable"), (copilot.shutil, "which"), (api, "run_llm_exec")):
                runner = copilot if module is copilot.shutil else module
                with self.subTest(runner=runner.__name__), patch.object(module, starter) as start, \
                     patch.object(api, "inspect_llm_backend", return_value={"available": True}), \
                     patch.object(codex.subprocess, "run", side_effect=ValueError("Fixture model startup forbidden")):
                    with self.assertRaisesRegex(ValueError, "runner_context_budget_exceeded"):
                        runner.run(args)
                    start.assert_not_called()
                    report = load_json(root / "runner-input-integrity.json")
                    self.assertEqual("blocked", report["status"])
                    self.assertFalse(report["model_invoked"])
                    self.assertIn("schema evidence", schema_path.read_text(encoding="utf-8"))

    def test_nonbatch_preflight_excludes_its_report_and_counts_wrappers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prompt = root / "prompt.txt"
            prompt.write_text("Return JSON.", encoding="utf-8")
            output = root / "out.json"
            args = argparse.Namespace(workspace=str(root), prompt_file=str(prompt), output=str(output),
                max_bytes=10000, max_input_tokens=10000, timeout_sec=1, output_schema="", preflight=True)
            with patch.object(codex, "_codex_executable") as start, contextlib.redirect_stdout(io.StringIO()):
                codex.run(args)
                first = load_json(root / "runner-input-integrity.json")
                self.assertIsNotNone(first, "Final payload preflight must persist integrity")
                codex.run(args)
                second = load_json(root / "runner-input-integrity.json")
            start.assert_not_called()
            self.assertEqual(first["request_sha256"], second["request_sha256"])
            self.assertGreater(first["request_bytes"], len(prompt.read_bytes()))

    def test_batched_input_rejects_external_prompt(self):
        with tempfile.TemporaryDirectory() as outside:
            prompt = Path(outside) / 'prompt.txt'
            prompt.write_text('invalid boundary', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'prompt path must be inside workspace'):
                api.batched_workspace_parts(self.root, prompt_path=prompt, output_path=self.output)

    def test_api_cumulative_context_is_checked_before_client_creation(self):
        # Each request fits independently, but the transcript plus acknowledgements does not.
        with patch.object(api, '_openai_client') as client:
            with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                    output_path=self.output, timeout_sec=30, max_bytes=8 * 1024 * 1024,
                    max_input_tokens=9000)
        client.assert_not_called()

    def test_api_disables_truncation_and_bounds_acknowledgement_growth(self):
        request = unittest.mock.Mock()
        request.responses.create.return_value = SimpleNamespace(id='fixture-response')
        client = unittest.mock.Mock()
        client.with_options.return_value = request
        api._response(client=client, prompt='full text', previous_response_id=None,
                      timeout_sec=30, max_output_tokens=4096)
        kwargs = request.responses.create.call_args.kwargs
        self.assertEqual('disabled', kwargs['truncation'])
        self.assertEqual(4096, kwargs['max_output_tokens'])

    def test_api_happy_path_receipt_covers_batches_and_original_text(self):
        responses = []
        def model(**kwargs):
            responses.append(kwargs)
            return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed', output_text='{}')
        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=model):
            receipt = api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                output_path=self.output, timeout_sec=30, max_bytes=8 * 1024 * 1024)
        self.assertEqual(4, receipt['model_request_count'])
        self.assertEqual(2, receipt['input_coverage']['batch_count'])
        self.assertEqual(['SB-1', 'SB-2'], receipt['input_coverage']['source_block_ids'])
        self.assertEqual(['RQ-1', 'RQ-2'], receipt['input_coverage']['requirement_ids'])
        self.assertIn(self.ledger['blocks'][0]['raw_text'], responses[1]['prompt'])
        self.assertEqual(4096, responses[1]['max_output_tokens'])
        self.assertEqual(32768, responses[-1]['max_output_tokens'])

    def test_deterministic_input_error_stops_all_candidate_retries(self):
        import plan_capabilities as planner
        # Real independent fixture keeps readiness and task scope checks meaningful.
        from planning_acceptance_fixture import build_fixture
        from scripts.python.tests.test_planning_audit_repair import prepare_cap
        fixture = self.root / 'fixture'
        build_fixture(fixture)
        prepare_cap(fixture)
        runner = Path(codex.__file__)
        calls = []
        def rejected(*args, **kwargs):
            calls.append(kwargs['workspace'])
            raise RuntimeError('runner_input_too_large:fixture')
        info = {**codex.description(), 'supports_input_preflight': False}
        with patch.object(planner, 'inspect_isolated_runner', return_value=info), \
             patch.object(planner, 'run_isolated_model', side_effect=rejected):
            with self.assertRaisesRegex(ValueError, 'runner_input_too_large'):
                planner.generate(fixture, run_id='repair', runner=runner, timeout_sec=30)
        self.assertEqual(1, len(calls))
        state = load_json(fixture / 'logs/ci/capability-planning/repair/run.json')
        self.assertEqual('generation-blocked', state['phase'])
        self.assertEqual('runner_input_too_large', state['error_type'])

    def test_actual_planner_preflight_spends_no_model_attempts(self):
        import plan_capabilities as planner
        from planning_acceptance_fixture import build_fixture
        from scripts.python.tests.test_planning_audit_repair import prepare_cap
        fixture = self.root / 'fixture'
        build_fixture(fixture)
        prepare_cap(fixture)
        with patch.dict(os.environ, {'SC_CAPABILITY_MAX_INPUT_TOKENS': '100'}), \
             patch.object(planner, 'run_isolated_model') as invoke:
            with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                planner.generate(fixture, run_id='repair', runner=Path(codex.__file__), timeout_sec=30)
        invoke.assert_not_called()
        state = load_json(fixture / 'logs/ci/capability-planning/repair/run.json')
        self.assertEqual(0, state['budget']['runner_invocations'])
        self.assertEqual('runner_context_budget_exceeded', state['error_type'])

    def test_preflight_never_starts_model_even_for_valid_input(self):
        self.args.preflight = True
        with patch.object(codex, '_codex_executable') as executable, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(0, codex.run(self.args))
        executable.assert_not_called()
        self.assertFalse(json.loads(stdout.getvalue())['model_invoked'])

    def test_copilot_one_batch_context_is_checked_before_authentication(self):
        _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.requirements, char_budget=10000)
        self.args.max_input_tokens = 100
        with patch.object(copilot.shutil, 'which') as executable:
            with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                copilot.run(self.args)
        executable.assert_not_called()

    def test_sent_text_and_receipt_remain_identical_after_preflight(self):
        self.args.preflight = True
        with contextlib.redirect_stdout(io.StringIO()):
            codex.run(self.args)
        self.args.preflight = False
        sent, receipt = self.invoke()
        self.assertNotIn('FILE: runner-input-integrity.json', sent)
        self.assertEqual(receipt['input_integrity']['request_sha256'],
                         load_json(self.root / 'runner-input-integrity.json')['request_sha256'])


if __name__ == '__main__':
    unittest.main()
