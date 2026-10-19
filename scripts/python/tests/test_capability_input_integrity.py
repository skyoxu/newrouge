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
        self.refresh_analysis_index()

    def parts(self):
        self.refresh_analysis_index()
        return api.batched_workspace_parts(self.root, prompt_path=self.prompt, output_path=self.output)

    def refresh_analysis_index(self):
        files = {}
        for path in sorted(self.analysis.rglob('*')):
            if path.is_file() and path.name != 'analysis-index.json':
                files[path.relative_to(self.analysis).as_posix()] = file_sha(path)
        payload = {'schema_version': 'newrouge.planning-analysis-input.v1', 'files': files}
        payload['analysis_identity_sha256'] = integrity.canonical_sha(payload)
        atomic_json(self.analysis / 'analysis-index.json', payload)

    @staticmethod
    def batch_fixture_payload(batch):
        return {
            'schema_version': 'newrouge.capability-batch-analysis.v1',
            'batch_index': batch['batch_index'],
            'source_block_analyses': [
                {'source_block_id': row['block_id'], 'summary': 'summary',
                 'boundary_signals': ['signal'], 'evidence_quotes': [row['raw_text'][:20]]}
                for row in batch['blocks']],
            'requirement_analyses': [
                {'requirement_id': row['requirement_id'], 'intent': 'intent',
                 'user_outcome': 'outcome', 'boundary_signals': ['signal'],
                 'source_block_ids': row['source_block_ids']}
                for row in batch['requirements']],
            'task_view_analyses': [],
        }

    def test_codex_transport_limit_matches_cli_character_cap(self):
        self.assertEqual(1 * 1024 * 1024, integrity.CODEX_MAX_TURN_BYTES)

    def invoke(self):
        self.refresh_analysis_index()
        self.codex_inputs = []
        def fake_exec(command, **kwargs):
            self.codex_inputs.append(kwargs['input'])
            output_arg = command[command.index('--output-last-message') + 1]
            output_path = Path(output_arg)
            schema_arg = command.index('--output-schema') + 1 if '--output-schema' in command else None
            if schema_arg is not None:
                schema = load_json(Path(command[schema_arg]), {})
                batch_index = int((schema.get('properties', {}).get('batch_index', {}).get('enum') or [1])[0])
                batch = load_json(self.analysis / self.index['batches'][batch_index - 1]['path'])
                payload = self.batch_fixture_payload(batch)
                is_task_batch = schema.get('properties', {}).get('source_block_analyses', {}).get('minItems') == 0
                if is_task_batch:
                    payload['batch_index'] = batch_index
                    payload['source_block_analyses'] = []
                    payload['requirement_analyses'] = []
                view_rows, _ = codex.api.task_view_batch_rows(self.root, self.index)
                task_groups = (
                    {path: rows for chunk in integrity.task_view_payload_chunks(self.root)
                     for path, rows in chunk.items()}
                    if is_task_batch else {}
                )
                for task_path, rows in (task_groups if is_task_batch else {}).items():
                    for task in rows:
                        refs = sorted(codex.api._task_view_refs(task))
                        payload['task_view_analyses'].append({
                            'task_view_key': f"{task_path}#{task.get('taskmaster_id', task.get('id', ''))}",
                            'task_intent': 'fixture intent',
                            'acceptance_signals': ['acceptance analyzed'],
                            'verification_signals': ['verification analyzed'],
                            'requirement_refs': refs,
                        })
                atomic_json(output_path, payload)
            else:
                atomic_json(output_path, {'fixture': True})
            return subprocess.CompletedProcess(command, 0, stdout='')
        with patch.object(codex, '_codex_executable', return_value='fixture-codex'), \
             patch.object(codex.subprocess, 'run', side_effect=fake_exec) as executor, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            codex.run(self.args)
        sent = "\n\n".join(call.kwargs['input'] for call in executor.call_args_list)
        return sent, json.loads(stdout.getvalue())

    def test_task_acceptance_and_descriptions_reach_exact_sent_payload(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'FULL_DESCRIPTION_END',
             'acceptance': ['MANDATORY_ACCEPTANCE_END'], 'test_refs': ['verification.gd']}])
        sent, receipt = self.invoke()
        self.assertIn('FULL_DESCRIPTION_END', sent)
        self.assertIn('MANDATORY_ACCEPTANCE_END', sent)
        self.assertIn('verification.gd', sent)
        source_inputs = [value for value in self.codex_inputs
                         if '===== COMPLETE TASK-VIEW ROWS =====' not in value]
        task_inputs = [value for value in self.codex_inputs
                       if '===== COMPLETE TASK-VIEW ROWS =====' in value]
        self.assertTrue(source_inputs)
        self.assertTrue(task_inputs)
        self.assertTrue(all('FULL_DESCRIPTION_END' not in value for value in source_inputs))
        self.assertTrue(all('MANDATORY_ACCEPTANCE_END' not in value for value in source_inputs))
        self.assertTrue(any('FULL_DESCRIPTION_END' in value for value in task_inputs))
        self.assertTrue(any('MANDATORY_ACCEPTANCE_END' in value for value in task_inputs))
        self.assertIn('task_view_analyses', self.codex_inputs[-1])
        synthesis = self.codex_inputs[-1]
        marker = '===== BATCH ANALYSIS: task-views-001 =====\n'
        analysis = json.loads(synthesis.split(marker, 1)[1].split('\n===== END BATCH ANALYSIS:', 1)[0])
        table = analysis['task_view_analyses']
        decoded = [dict(zip(table['columns'], row, strict=True)) for row in table['rows']]
        self.assertEqual([{'task_view_key': 'task-views/tasks_gameplay.json#7',
                           'task_intent': 'fixture intent',
                           'acceptance_signals': ['acceptance analyzed'],
                           'verification_signals': ['verification analyzed'],
                           'requirement_refs': []}], decoded)
        self.assertNotIn('FULL_DESCRIPTION_END', self.codex_inputs[-1])
        self.assertEqual(receipt['input_integrity']['batch_count'] + 1,
                         receipt['runner_invocations'])
        self.assertTrue(receipt['input_integrity']['requests'])
        self.assertEqual(1, receipt['input_integrity']['task_view_coverage']['views'][
            'analysis-input/task-views/tasks_gameplay.json']['row_count'])

    def test_task_views_are_separate_even_when_small(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'TASK_ONLY',
             'semantic_refs': ['RQ-1'], 'acceptance': ['ACCEPTANCE_ONLY'],
             'test_refs': ['verification.gd']}])
        self.refresh_analysis_index()
        sent, _ = self.invoke()
        source_inputs = [value for value in self.codex_inputs
                         if '===== COMPLETE TASK-VIEW ROWS =====' not in value]
        task_inputs = [value for value in self.codex_inputs
                       if '===== COMPLETE TASK-VIEW ROWS =====' in value]
        self.assertTrue(all('TASK_ONLY' not in value for value in source_inputs))
        self.assertTrue(any('TASK_ONLY' in value for value in task_inputs))

    def test_task_views_are_partitioned_without_field_loss(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'description': 'TASK_A_FULL', 'acceptance': ['AC_A'],
             'semantic_refs': ['RQ-1'], 'test_refs': ['TEST_A'], 'custom': {'keep': True}},
            {'taskmaster_id': 8, 'description': 'TASK_CROSS_FULL', 'acceptance': ['AC_CROSS'],
             'requirement_ids': ['RQ-1', 'RQ-2'], 'test_refs': ['TEST_CROSS']},
            {'taskmaster_id': 9, 'description': 'TASK_UNBOUND_FULL', 'acceptance': ['AC_UNBOUND'],
             'test_refs': ['TEST_UNBOUND']},
        ])
        base, batches = self.parts()
        self.assertNotIn('TASK_A_FULL', base)
        self.assertNotIn('TASK_CROSS_FULL', base)
        self.assertTrue(all('TASK_A_FULL' not in section for _, section in batches))
        self.assertTrue(all('TASK_CROSS_FULL' not in section for _, section in batches))
        self.assertTrue(all('TASK_UNBOUND_FULL' not in section for _, section in batches))
        task_chunks = integrity.task_view_payload_chunks(self.root)
        task_text = '\n'.join(json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))
                               for chunk in task_chunks)
        for marker in ('TASK_A_FULL', 'TASK_CROSS_FULL', 'TASK_UNBOUND_FULL',
                       'AC_A', 'AC_CROSS', 'TEST_CROSS', 'TEST_UNBOUND',
                       '"custom":{"keep":true}'):
            self.assertIn(marker, task_text)
        self.assertEqual(1, task_text.count('TASK_CROSS_FULL'))

    def test_large_task_views_are_split_into_complete_size_bounded_chunks(self):
        rows = [
            {"taskmaster_id": str(index), "description": "task " + ("x" * 2400),
             "acceptance": ["accept " + str(index)], "semantic_refs": ["RQ-1"]}
            for index in range(25)
        ]
        atomic_json(self.analysis / "task-views/tasks_gameplay.json", rows)
        self.refresh_analysis_index()
        chunks = integrity.task_view_payload_chunks(self.root, char_budget=10000)
        self.assertGreater(len(chunks), 1)
        actual = [row["taskmaster_id"] for chunk in chunks for part in chunk.values() for row in part]
        self.assertEqual([str(index) for index in range(25)], actual)
        for chunk in chunks:
            size = sum(len(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                       for part in chunk.values() for row in part)
            self.assertLessEqual(size, 10000)

    def test_task_view_unknown_requirement_reference_fails_closed(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'description': 'TASK', 'semantic_refs': ['RQ-UNKNOWN']}])
        self.refresh_analysis_index()
        with self.assertRaisesRegex(ValueError, 'unknown_task_requirement_ref'):
            api.task_view_batch_rows(self.root, self.index)

    def test_task_view_duplicate_identity_fails_closed(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'semantic_refs': ['RQ-1']},
            {'taskmaster_id': 7, 'semantic_refs': ['RQ-2']}])
        self.refresh_analysis_index()
        with self.assertRaisesRegex(ValueError, 'duplicate_task_view_id'):
            api.task_view_batch_rows(self.root, self.index)

    def test_cancelled_task_views_are_excluded_from_model_batches(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'status': 'cancelled', 'semantic_refs': ['RQ-1'],
             'ui_wiring_candidate': {'scope_task_ids': [1, 11, 14]},
             'title': 'Historical task'},
            {'taskmaster_id': 8, 'status': 'done', 'semantic_refs': ['RQ-2'],
             'title': 'Active task'},
        ])
        self.refresh_analysis_index()
        chunks = integrity.task_view_payload_chunks(self.root)
        serialized = json.dumps(chunks, ensure_ascii=False)
        self.assertNotIn('Historical task', serialized)
        self.assertNotIn('scope_task_ids', serialized)
        self.assertIn('Active task', serialized)
        _, coverage = api.task_view_batch_rows(self.root, self.index)
        view = next(iter(coverage['views'].values()))
        self.assertEqual(1, view['active_row_count'])
        self.assertEqual(1, view['excluded_cancelled_row_count'])

    def test_master_task_status_is_authoritative_over_stale_view_status(self):
        atomic_json(self.analysis / 'task-master.json', {
            'master': {'tasks': [
                {'taskmaster_id': 7, 'status': 'cancelled'},
                {'taskmaster_id': 8, 'status': 'done'},
            ]}
        })
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'status': 'done', 'semantic_refs': ['RQ-1'], 'title': 'Stale active view'},
            {'taskmaster_id': 8, 'status': 'cancelled', 'semantic_refs': ['RQ-2'], 'title': 'Stale cancelled view'},
        ])
        self.refresh_analysis_index()
        serialized = json.dumps(integrity.task_view_payload_chunks(self.root), ensure_ascii=False)
        self.assertNotIn('Stale active view', serialized)
        self.assertIn('Stale cancelled view', serialized)

    def test_task_missing_from_master_is_excluded_and_audited_as_orphaned(self):
        atomic_json(self.analysis / 'task-master.json', {
            'master': {'tasks': [{'taskmaster_id': 7, 'status': 'done'}]}
        })
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'status': 'done', 'description': 'Known task', 'semantic_refs': ['RQ-1']},
            {'taskmaster_id': 99, 'status': 'done', 'description': 'Orphan task', 'semantic_refs': ['RQ-2']},
        ])
        self.refresh_analysis_index()
        serialized = json.dumps(integrity.task_view_payload_chunks(self.root), ensure_ascii=False)
        self.assertIn('Known task', serialized)
        self.assertNotIn('Orphan task', serialized)
        _, coverage = api.task_view_batch_rows(self.root, self.index)
        view = next(iter(coverage['views'].values()))
        self.assertEqual(1, view['excluded_orphaned_row_count'])

    def test_retired_rows_are_not_counted_as_cancelled(self):
        atomic_json(self.analysis / 'task-master.json', {
            'master': {'tasks': [
                {'taskmaster_id': 7, 'status': 'retired'},
                {'taskmaster_id': 8, 'status': 'cancelled'},
            ]}
        })
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'Retired task', 'semantic_refs': ['RQ-1']},
            {'taskmaster_id': 8, 'description': 'Cancelled task', 'semantic_refs': ['RQ-2']},
        ])
        self.refresh_analysis_index()
        _, coverage = api.task_view_batch_rows(self.root, self.index)
        view = next(iter(coverage['views'].values()))
        self.assertEqual(2, view['excluded_inactive_row_count'])
        self.assertEqual(1, view['excluded_cancelled_row_count'])

    def test_task_requirement_refs_are_bound_from_authoritative_view_not_model(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'status': 'done', 'description': 'Authoritative task',
             'acceptance': ['Acceptance'], 'test_refs': ['test_ref.gd'], 'semantic_refs': []}])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        path = next(iter(task_rows))
        task = task_rows[path][0]
        payload = {'schema_version': 'newrouge.capability-batch-analysis.v1', 'batch_index': 1,
                   'source_block_analyses': [], 'requirement_analyses': [],
                   'task_view_analyses': [{
                       'task_view_key': f'{path}#{task["taskmaster_id"]}',
                       'task_intent': 'Model summary', 'acceptance_signals': ['Accepted'],
                       'verification_signals': ['Verified'], 'requirement_refs': ['RQ-1']} ]}
        result = api._validate_batch_analysis(payload,
            {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
             'blocks': [], 'requirements': []}, task_rows)
        self.assertEqual([], result['task_view_analyses'][0]['requirement_refs'])

    def test_unexpected_and_duplicate_task_analysis_rows_are_reconciled_from_authority(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'status': 'done', 'description': 'Authoritative task 7',
             'acceptance': ['Acceptance 7'], 'test_refs': ['test7.gd'], 'semantic_refs': ['RQ-1']},
            {'taskmaster_id': 8, 'status': 'done', 'description': 'Authoritative task 8',
             'acceptance': ['Acceptance 8'], 'test_refs': ['test8.gd'], 'semantic_refs': ['RQ-2']}])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        path = next(iter(task_rows))
        first = task_rows[path][0]
        output_row = {'task_view_key': f'{path}#{first["taskmaster_id"]}',
                      'task_intent': 'Model summary', 'acceptance_signals': ['Accepted'],
                      'verification_signals': ['Verified'], 'requirement_refs': ['RQ-1']}
        payload = {'schema_version': 'newrouge.capability-batch-analysis.v1', 'batch_index': 1,
                   'source_block_analyses': [], 'requirement_analyses': [],
                   'task_view_analyses': [output_row, {**output_row, 'task_view_key': f'{path}#8'}, dict(output_row), {
                       **output_row, 'task_view_key': f'{path}#999'}]}
        result = api._validate_batch_analysis(payload,
            {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
             'blocks': [], 'requirements': []}, task_rows)
        keys = [row['task_view_key'] for row in result['task_view_analyses']]
        self.assertEqual([f'{path}#7', f'{path}#8'], keys)
        self.assertEqual('RQ-2', result['task_view_analyses'][1]['requirement_refs'][0])
        audit = result['_task_view_reconciliation']
        self.assertEqual([f'{path}#999'], audit['ignored_unknown_task_rows'])
        self.assertEqual([f'{path}#7'], audit['ignored_duplicate_task_rows'])

    def test_task_view_singular_requirement_ref_is_preserved(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'requirement_ref': 'RQ-2', 'description': 'SINGULAR_REF'}])
        self.refresh_analysis_index()
        selected, _ = api.task_view_batch_rows(self.root, self.index)
        self.assertNotIn('SINGULAR_REF', json.dumps(selected[0], ensure_ascii=False))
        self.assertIn('SINGULAR_REF', json.dumps(selected[1], ensure_ascii=False))

    def test_cross_batch_task_schema_allows_complete_requirement_refs(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'requirement_ids': ['RQ-1', 'RQ-2'], 'description': 'CROSS'}])
        self.refresh_analysis_index()
        rows, _ = api.task_view_batch_rows(self.root, self.index)
        schema = api._batch_analysis_schema(
            load_json(self.analysis / self.index['batches'][0]['path']), rows[0])
        refs_schema = schema['properties']['task_view_analyses']['items']['properties']['requirement_refs']['items']
        self.assertEqual(['RQ-1', 'RQ-2'], refs_schema['enum'])

    def test_nested_task_views_are_rejected_as_unprepared(self):
        atomic_json(self.analysis / 'task-views/nested/tasks_back.json', [
            {'taskmaster_id': 17, 'description': 'NESTED_TASK_FULL', 'semantic_refs': ['RQ-2']}])
        with self.assertRaisesRegex(ValueError, 'nested_task_view_unsupported'):
            api.task_view_batch_rows(self.root, self.index)

    def test_quote_matching_accepts_model_whitespace_normalization(self):
        raw = 'Acceptance and test evidence remain\nin the two task views.'
        normalized = 'Acceptance and test evidence remain in the two task views.'
        self.assertTrue(api._quote_matches_source(normalized, raw))

    def test_batch_analysis_reconciles_missing_rows_and_binds_quotes_to_source(self):
        batch = load_json(self.analysis / self.index['batches'][0]['path'])
        value = self.batch_fixture_payload(batch)
        value['source_block_analyses'][0].pop('evidence_quotes')
        # Source Block identity coverage remains a hard gate.
        reconciled = api._validate_batch_analysis(value, batch)
        expected_ids = [str(row['block_id']) for row in batch['blocks']]
        self.assertEqual(expected_ids, [row['source_block_id'] for row in reconciled['source_block_analyses']])
        self.assertTrue(reconciled['source_block_analyses'][0]['evidence_quotes'])
        self.assertIn(batch['blocks'][0]['raw_text'][:40], reconciled['source_block_analyses'][0]['evidence_quotes'][0])

    def test_task_analysis_rejects_missing_rows_from_authoritative_task_view(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'title': 'Task title', 'description': 'Authoritative intent',
             'acceptance': ['Authoritative acceptance'], 'test_refs': ['test_ref.gd'],
             'semantic_refs': ['RQ-1']}])
        self.refresh_analysis_index()
        chunks = integrity.task_view_payload_chunks(self.root)
        task_rows = chunks[0]
        payload = {'schema_version': 'newrouge.capability-batch-analysis.v1', 'batch_index': 1,
                   'source_block_analyses': [], 'requirement_analyses': [],
                   'task_view_analyses': []}
        key = next(path for path in task_rows)
        row = task_rows[key][0]
        payload['task_view_analyses'] = [{
            'task_view_key': f'{key}#{row["taskmaster_id"]}',
            'task_intent': 'model intent', 'acceptance_signals': ['model acceptance'],
            'verification_signals': ['model verification'], 'requirement_refs': ['RQ-1']}]
        # A second authoritative row is intentionally omitted from the model output.
        row2 = dict(row, taskmaster_id=8, description='Second authoritative intent')
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [row, row2])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        batch = {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
                 'blocks': [], 'requirements': []}
        with self.assertRaisesRegex(ValueError, 'capability_batch_analysis_task_view_coverage_missing'):
            api._validate_batch_analysis(payload, batch, task_rows)
        payload['task_view_analyses'] = []
        with self.assertRaisesRegex(ValueError, 'capability_batch_analysis_task_view_coverage_missing'):
            api._validate_batch_analysis(payload, batch, task_rows)
        import jsonschema
        schema = api._batch_analysis_schema(batch, task_rows)
        self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(payload)))

    def test_long_authoritative_task_intent_is_preserved_outside_bounded_summary(self):
        long_description = 'FULL_AUTHORITATIVE_INTENT_' + ('x' * 1400)
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'title': 'Short task title',
             'description': long_description, 'semantic_refs': ['RQ-1']}])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        path = next(iter(task_rows))
        payload = {'schema_version': 'newrouge.capability-batch-analysis.v1', 'batch_index': 1,
                   'source_block_analyses': [], 'requirement_analyses': [],
                   'task_view_analyses': [{'task_view_key': f'{path}#7',
                       'task_intent': '', 'acceptance_signals': ['accepted'],
                       'verification_signals': ['verified'], 'requirement_refs': []}]}
        result = api._validate_batch_analysis(payload,
            {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
             'blocks': [], 'requirements': []}, task_rows)
        row = result['task_view_analyses'][0]
        self.assertLessEqual(len(row['task_intent']), 1200)
        self.assertEqual(long_description, row['task_intent_source'])

    def test_task_row_reconciliation_audit_is_not_forwarded_to_synthesis_payload(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'Known', 'semantic_refs': ['RQ-1']}])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        path = next(iter(task_rows))
        payload = {'schema_version': 'newrouge.capability-batch-analysis.v1', 'batch_index': 1,
                   'source_block_analyses': [], 'requirement_analyses': [],
                   'task_view_analyses': [
                       {'task_view_key': f'{path}#7', 'task_intent': 'known',
                        'acceptance_signals': ['accepted'], 'verification_signals': ['verified'],
                        'requirement_refs': []},
                       {'task_view_key': f'{path}#999', 'task_intent': 'unknown',
                        'acceptance_signals': ['accepted'], 'verification_signals': ['verified'],
                        'requirement_refs': []}]}
        result = api._validate_batch_analysis(payload,
            {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
             'blocks': [], 'requirements': []}, task_rows)
        audit = api._take_task_view_reconciliation(result)
        self.assertEqual([f'{path}#999'], audit['ignored_unknown_task_rows'])
        self.assertNotIn('_task_view_reconciliation', result)

    def test_task_batch_discards_mixed_source_and_requirement_rows(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'Authoritative task',
             'acceptance': ['Acceptance'], 'test_refs': ['test_ref.gd'],
             'semantic_refs': ['RQ-1']}])
        self.refresh_analysis_index()
        task_rows = integrity.task_view_payload_chunks(self.root)[0]
        path = next(iter(task_rows))
        task = task_rows[path][0]
        payload = {
            'schema_version': 'newrouge.capability-batch-analysis.v1',
            'batch_index': 1,
            'source_block_analyses': [],
            'requirement_analyses': [{
                'requirement_id': 'RQ-1', 'intent': 'wrong channel',
                'user_outcome': 'wrong channel', 'boundary_signals': [],
                'source_block_ids': [],
            }],
            'task_view_analyses': [{
                'task_view_key': f'{path}#{task["taskmaster_id"]}',
                'task_intent': 'model task', 'acceptance_signals': ['accepted'],
                'verification_signals': ['verified'], 'requirement_refs': ['RQ-1'],
            }],
        }
        result = api._validate_batch_analysis(payload,
            {'schema_version': 'newrouge.capability-model-batch.v1', 'batch_index': 1,
             'blocks': [], 'requirements': []}, task_rows)
        self.assertEqual([], result['requirement_analyses'])
        self.assertEqual(1, len(result['task_view_analyses']))

    def test_large_task_views_are_not_replayed_in_every_batch(self):
        atomic_json(self.analysis / 'task-views/tasks_back.json', [
            {'taskmaster_id': 7, 'description': 'A' * 50000, 'semantic_refs': ['RQ-1'],
             'acceptance': ['AC_A']},
            {'taskmaster_id': 8, 'description': 'B' * 50000, 'semantic_refs': ['RQ-2'],
             'acceptance': ['AC_B']},
        ])
        base, batches = self.parts()
        self.assertNotIn('A' * 1000, base)
        self.assertNotIn('B' * 1000, base)
        task_chunks = integrity.task_view_payload_chunks(self.root)
        self.assertEqual(2, len(task_chunks))
        task_text = json.dumps(task_chunks[0], ensure_ascii=False, separators=(',', ':'))
        all_task_text = ''.join(json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))
                                for chunk in task_chunks)
        self.assertIn('A' * 1000, all_task_text)
        self.assertIn('B' * 1000, all_task_text)
        self.assertTrue(all('A' * 1000 not in section for _, section in batches))
        self.assertTrue(all('B' * 1000 not in section for _, section in batches))

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

    def test_codex_character_limit_is_checked_before_any_invocation(self):
        self.args.max_bytes = 4 * 1024 * 1024
        self.prompt.write_text('x' * (integrity.CODEX_MAX_TURN_BYTES + 1), encoding='utf-8')
        with patch.object(codex, '_codex_executable') as executable, \
             patch.object(codex.subprocess, 'run') as executor:
            with self.assertRaisesRegex(ValueError, 'complete_request_chars'):
                codex.run(self.args)
        executable.assert_not_called()
        executor.assert_not_called()
        report = load_json(self.root / 'runner-input-integrity.json')
        self.assertFalse(report['model_invoked'])

    def test_oversized_synthesis_capacity_blocks_before_first_codex_call(self):
        self.refresh_analysis_index()
        original = api._synthesis_request
        def oversized_synthesis(**kwargs):
            return original(**kwargs) + ('x' * (integrity.CODEX_MAX_TURN_BYTES + 1))
        with patch.object(api, '_synthesis_request', side_effect=oversized_synthesis), \
             patch.object(codex, '_codex_executable') as executable, \
             patch.object(codex.subprocess, 'run') as executor:
            with self.assertRaisesRegex(ValueError, 'runner_input_too_large'):
                codex.run(self.args)
        executable.assert_not_called()
        executor.assert_not_called()
        report = load_json(self.root / 'runner-input-integrity.json')
        self.assertEqual('blocked', report['status'])
        self.assertFalse(report['model_invoked'])
        self.assertIn('complete_request_chars', report['error'])
        self.assertIn('coverage', report)

    def test_non_ascii_token_budget_is_checked_before_starting_codex(self):
        self.refresh_analysis_index()
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

    def test_api_batches_are_independent_and_synthesis_excludes_raw_source(self):
        atomic_json(self.analysis / 'task-views/tasks_gameplay.json', [
            {'taskmaster_id': 7, 'description': 'SYNTHESIS_TASK_CONTEXT',
             'acceptance': ['SYNTHESIS_ACCEPTANCE_CONTEXT']}])
        batches = [load_json(self.analysis / row['path']) for row in self.index['batches']]
        responses = []

        def model(**kwargs):
            responses.append(kwargs)
            if len(responses) <= len(batches):
                batch = batches[len(responses) - 1]
                blocks = batch['blocks']
                requirements = batch['requirements']
                payload = self.batch_fixture_payload(batch)
                return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed',
                                       output_text=json.dumps(payload))
            if '===== COMPLETE TASK-VIEW ROWS =====' in responses[-1]['prompt']:
                payload = {
                    'schema_version': 'newrouge.capability-batch-analysis.v1',
                    'batch_index': 1,
                    'source_block_analyses': [], 'requirement_analyses': [],
                    'task_view_analyses': [],
                }
                for chunk in integrity.task_view_payload_chunks(self.root):
                    for task_path, rows in chunk.items():
                        for task in rows:
                            payload['task_view_analyses'].append({
                                'task_view_key': f"{task_path}#{task.get('taskmaster_id', task.get('id', ''))}",
                                'task_intent': 'fixture intent',
                                'acceptance_signals': ['acceptance analyzed'],
                                'verification_signals': ['verification analyzed'],
                                'requirement_refs': sorted(api._task_view_refs(task)),
                            })
                return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed',
                                       output_text=json.dumps(payload))
            return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed', output_text='{}')

        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=model):
            self.refresh_analysis_index()
            receipt = api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                output_path=self.output, timeout_sec=180, max_bytes=8 * 1024 * 1024,
                max_input_tokens=40000)

        self.assertEqual(len(batches) + 2, receipt['model_request_count'])
        self.assertTrue(all(call.get('previous_response_id') is None for call in responses))
        for index, batch in enumerate(batches):
            expected_text = batch['blocks'][0]['raw_text']
            self.assertIn(expected_text, responses[index]['prompt'])
            for other in batches:
                if other is not batch:
                    self.assertNotIn(other['blocks'][0]['raw_text'], responses[index]['prompt'])
            self.assertIsNone(responses[index].get('previous_response_id'))
        final_prompt = responses[-1]['prompt']
        self.assertNotIn('SYNTHESIS_TASK_CONTEXT', responses[0]['prompt'])
        self.assertNotIn('SYNTHESIS_ACCEPTANCE_CONTEXT', responses[0]['prompt'])
        self.assertIn('SYNTHESIS_TASK_CONTEXT', responses[len(batches)]['prompt'])
        self.assertIn('SYNTHESIS_ACCEPTANCE_CONTEXT', responses[len(batches)]['prompt'])
        self.assertIn('task_view_analyses', final_prompt)
        self.assertNotIn('SYNTHESIS_TASK_CONTEXT', final_prompt)
        self.assertNotIn('SYNTHESIS_ACCEPTANCE_CONTEXT', final_prompt)
        for batch in batches:
            for block in batch['blocks']:
                self.assertNotIn(block['raw_text'], final_prompt)
        task_chunk_count = len(integrity.task_view_payload_chunks(self.root))
        self.assertEqual(len(batches) + task_chunk_count + 2, len(receipt['input_integrity']))

    def test_batched_requests_use_independent_contexts_and_bounded_final_input(self):
        """Each source batch is a fresh request; final synthesis receives model outputs only."""
        responses = []
        batches = [load_json(self.analysis / row['path']) for row in self.index['batches']]

        def model(**kwargs):
            responses.append(kwargs)
            if len(responses) <= len(batches):
                batch = batches[len(responses) - 1]
                payload = self.batch_fixture_payload(batch)
                output_text = json.dumps(payload)
            else:
                output_text = '{}'
            return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed', output_text=output_text)

        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=model):
            self.refresh_analysis_index()
            receipt = api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                output_path=self.output, timeout_sec=30, max_bytes=8 * 1024 * 1024,
                max_input_tokens=30000)

        self.assertEqual(len(batches) + 1, receipt['model_request_count'])
        self.assertTrue(all(call.get('previous_response_id') is None for call in responses))
        for index, batch in enumerate(batches):
            for block in batch['blocks']:
                self.assertIn(block['raw_text'], responses[index]['prompt'])
            self.assertIsNone(responses[index].get('previous_response_id'))
        for batch in batches:
            for block in batch['blocks']:
                self.assertNotIn(block['raw_text'], responses[-1]['prompt'])
        self.assertEqual(len(batches) + 2, len(receipt['input_integrity']))

    def test_batch_validation_retries_only_failed_batch_and_records_attempts(self):
        """A malformed batch is retried locally; accepted batches are not replayed."""
        responses = []
        batches = [load_json(self.analysis / row['path']) for row in self.index['batches']]

        def model(**kwargs):
            responses.append(kwargs)
            # First source batch returns a deterministic coverage error. The
            # correction request then returns the valid first batch. The next
            # source batch and final synthesis each run once.
            if len(responses) == 1:
                value = self.batch_fixture_payload(batches[0])
                value['requirement_analyses'] = []
            elif len(responses) == 2:
                value = self.batch_fixture_payload(batches[0])
            elif len(responses) == 3:
                value = self.batch_fixture_payload(batches[1])
            else:
                value = {}
            return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed',
                                   output_text=json.dumps(value))

        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=model):
            self.refresh_analysis_index()
            receipt = api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                output_path=self.output, timeout_sec=30, max_bytes=8 * 1024 * 1024,
                max_input_tokens=30000)

        self.assertEqual(len(batches) + 2, receipt['model_request_count'])
        self.assertEqual('accepted', receipt['batch_attempts'][0]['status'])
        self.assertEqual(2, receipt['batch_attempts'][0]['attempts'])
        self.assertEqual('batch_validation', receipt['batch_attempts'][0]['retry_errors'][0]['error_type'])
        self.assertEqual('accepted', receipt['batch_attempts'][1]['status'])
        self.assertEqual(1, receipt['batch_attempts'][1]['attempts'])
        first_raw = batches[0]['blocks'][0]['raw_text']
        self.assertIn(first_raw, responses[0]['prompt'])
        self.assertIn(first_raw, responses[1]['prompt'])
        self.assertIn('BATCH CORRECTION RETRY', responses[1]['prompt'])
        second_raw = batches[1]['blocks'][0]['raw_text']
        self.assertIn(second_raw, responses[2]['prompt'])
        self.assertNotIn(second_raw, responses[0]['prompt'])

    def test_batch_retry_exhaustion_persists_failure_audit(self):
        def rejected(**kwargs):
            raise RuntimeError('runner_transport: fixture failure')
        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=rejected):
            self.refresh_analysis_index()
            with self.assertRaisesRegex(ValueError, 'retry_exhausted:batch-001'):
                api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                    output_path=self.output, timeout_sec=30, max_bytes=8 * 1024 * 1024,
                    max_input_tokens=30000)
        report = load_json(self.root / 'runner-input-integrity.json')
        self.assertEqual('failed', report['status'])
        self.assertEqual('runner_transport', report['error_type'])
        self.assertEqual('failed', report['batch_attempts'][0]['status'])
        self.assertEqual('runner_transport', report['batch_attempts'][0]['error_type'])

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

    def test_batch_analysis_schema_bounds_synthesis_reservation(self):
        batch = load_json(self.analysis / self.index['batches'][0]['path'])
        schema = api._batch_analysis_schema(batch)
        properties = schema['properties']
        self.assertEqual(len(batch['blocks']), properties['source_block_analyses']['minItems'])
        self.assertEqual(len(batch['blocks']), properties['source_block_analyses']['maxItems'])
        block_properties = properties['source_block_analyses']['items']['properties']
        self.assertIn('maxLength', block_properties['summary'])
        self.assertIn('maxItems', block_properties['boundary_signals'])
        self.assertNotIn('evidence_quotes', block_properties)
        requirement_properties = properties['requirement_analyses']['items']['properties']
        self.assertIn('maxLength', requirement_properties['intent'])
        self.assertIn('maxLength', requirement_properties['user_outcome'])

    def test_synthesis_reservation_respects_actual_batch_response_budget(self):
        report = api._synthesis_capacity_report('fixed synthesis context',
            analysis_budgets=[('batch-001', 8192), ('task-views-001', 3072)],
            max_bytes=8 * 1024 * 1024, max_input_tokens=96000, reserved_tokens=16000)
        self.assertGreaterEqual(report['input_token_estimate'], 8192 + 3072)
        self.assertEqual(report['analysis_output_token_allowance'], 8192 + 3072)
        with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
            api._synthesis_capacity_report('fixed synthesis context',
                analysis_budgets=[('batch-001', 90000)],
                max_bytes=8 * 1024 * 1024, max_input_tokens=96000, reserved_tokens=16000)

    def test_synthesis_analysis_tables_preserve_every_field_and_value(self):
        value = self.batch_fixture_payload(load_json(self.analysis / self.index['batches'][0]['path']))
        value['source_block_analyses'][0]['additional_evidence'] = {'nested': ['full text', None]}
        value['task_view_analyses'] = [{'task_view_key': 'views#1', 'task_intent': '全文',
            'acceptance_signals': ['one', 'two'], 'verification_signals': ['test.cs'],
            'requirement_refs': ['RQ-1']}]
        packed = api._pack_analysis_tables(value)
        for field in ('source_block_analyses', 'requirement_analyses', 'task_view_analyses'):
            table = packed[field]
            decoded = [dict(zip(table['columns'], row, strict=True)) for row in table['rows']]
            self.assertEqual(value[field], decoded)
        self.assertEqual(value['schema_version'], packed['schema_version'])

    def test_synthesis_base_drops_preparation_only_analysis_index_metadata(self):
        index = {'analysis_identity_sha256': 'sha256:test', 'files': {'tasks.json': 'sha256:tasks'},
                 'authority_inputs': {'path': 'preparation-only-marker'},
                 'blinding_transformations': ['preparation-only-marker']}
        base = ('===== FILE: analysis-input/analysis-index.json =====\n' + json.dumps(index)
                + '\n===== END FILE: analysis-input/analysis-index.json =====\n'
                '===== FILE: analysis-input/readiness-summary.json =====\n{"formal_ready":true,"tasks":[{"task_id":"1","readiness_sha256":"x","readiness_path":"path","future_evidence":"kept"}]}\n'
                '===== END FILE: analysis-input/readiness-summary.json =====\n'
                '===== FILE: analysis-input/task-master.json =====\n{"master":{}}\n'
                '===== END FILE: analysis-input/task-master.json =====\nFULL_READINESS')
        result = api._synthesis_base(base)
        self.assertIn('analysis-index.json', result)
        self.assertIn('sha256:test', result)
        self.assertIn('sha256:tasks', result)
        self.assertIn('FULL_READINESS', result)
        self.assertNotIn('preparation-only-marker', result)
        self.assertNotIn('readiness_sha256', result)
        self.assertIn('"master":{}', result)
        self.assertIn('"future_evidence":"kept"', result)
        self.assertIn('"readiness_path":"path"', result)

    def test_api_happy_path_receipt_covers_batches_and_original_text(self):
        responses = []
        def model(**kwargs):
            responses.append(kwargs)
            if len(responses) <= 2:
                batch = load_json(self.analysis / self.index['batches'][len(responses) - 1]['path'])
                output = json.dumps(self.batch_fixture_payload(batch))
            else:
                output = '{}'
            return SimpleNamespace(id=f'fixture-{len(responses)}', status='completed', output_text=output)
        with patch.object(api, '_openai_client', return_value=object()), \
             patch.object(api, '_response', side_effect=model):
            self.refresh_analysis_index()
            receipt = api._run_batched_session(workspace=self.root, prompt_path=self.prompt,
                output_path=self.output, timeout_sec=120, max_bytes=8 * 1024 * 1024)
        self.assertEqual(3, receipt['model_request_count'])
        self.assertEqual(2, receipt['input_coverage']['batch_count'])
        self.assertEqual(['SB-1', 'SB-2'], receipt['input_coverage']['source_block_ids'])
        self.assertEqual(['RQ-1', 'RQ-2'], receipt['input_coverage']['requirement_ids'])
        self.assertIn(self.ledger['blocks'][0]['raw_text'], responses[0]['prompt'])
        self.assertEqual(8192, responses[0]['max_output_tokens'])
        self.assertEqual(32000, responses[-1]['max_output_tokens'])

    def test_multiple_batches_require_explicit_runner_support_before_dispatch(self):
        import plan_capabilities as planner
        for advertised in (None, False, "true"):
            with self.subTest(advertised=advertised):
                state = {'formal_ready': True, 'model_batch_count': 1, 'task_view_chunk_count': 1}
                info = {} if advertised is None else {'supports_batched_session': advertised}
                with patch.object(planner, '_load_run', return_value=(self.root / 'run.json', state)), \
                     patch.object(planner, '_recover_interrupted_attempts'), \
                     patch.object(planner, 'inspect_isolated_runner', return_value=info), \
                     patch.object(planner, 'run_isolated_model') as model:
                    with self.assertRaisesRegex(ValueError, 'supports_batched_session=true'):
                        planner.generate(self.root, run_id='fixture', runner=Path(codex.__file__), timeout_sec=30)
                    model.assert_not_called()

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
        self.refresh_analysis_index()
        self.args.preflight = True
        with patch.object(codex, '_codex_executable') as executable, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(0, codex.run(self.args))
        executable.assert_not_called()
        self.assertFalse(json.loads(stdout.getvalue())['model_invoked'])

    def test_copilot_one_batch_context_is_checked_before_authentication(self):
        _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.requirements, char_budget=10000)
        self.refresh_analysis_index()
        self.args.max_input_tokens = 100
        with patch.object(copilot.shutil, 'which') as executable:
            with self.assertRaisesRegex(ValueError, 'runner_context_budget_exceeded'):
                copilot.run(self.args)
        executable.assert_not_called()

    def test_sent_text_and_receipt_remain_identical_after_preflight(self):
        self.refresh_analysis_index()
        self.args.preflight = True
        with contextlib.redirect_stdout(io.StringIO()):
            codex.run(self.args)
        self.args.preflight = False
        sent, receipt = self.invoke()
        self.assertNotIn('FILE: runner-input-integrity.json', sent)
        self.assertEqual(receipt['input_integrity']['requests'],
                         load_json(self.root / 'runner-input-integrity.json')['requests'])

    def test_preflight_and_execution_request_identity_ignores_generated_batch_files(self):
        self.refresh_analysis_index()
        self.args.preflight = True
        with patch.object(codex, '_codex_executable') as executable, contextlib.redirect_stdout(io.StringIO()):
            codex.run(self.args)
            before = load_json(self.root / 'runner-input-integrity.json')
            self.args.preflight = False
            self.invoke()
            after = load_json(self.root / 'runner-input-integrity.json')
        executable.assert_not_called()
        self.assertEqual(before['requests'], after['requests'][:len(before['requests'])])


if __name__ == '__main__':
    unittest.main()
