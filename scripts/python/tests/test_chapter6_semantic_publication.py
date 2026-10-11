"""Task-local semantic candidates require reviewed, source-bound publication."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _planning_skill_common import atomic_json, file_sha, load_json
import chapter6_semantic_publication as publication


class SemanticPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        atomic_json(self.root / '.taskmaster/tasks/tasks.json', {'master': {'tasks': [{'id': 18}]}})
        atomic_json(self.root / 'Game.Core/Data/cards.json', {'cost': 1})
        script = self.root / 'Game.Godot/Scripts/UI.gd'
        script.parent.mkdir(parents=True)
        script.write_text('load("Game.Core/Data/cards.json")\n', encoding='utf-8')
        self.entries = [{'task_id': '18', 'id': 'config:18:cards', 'kind': 'config',
                         'path': 'Game.Core/Data/cards.json',
                         'parameters': [{'pointer': '/cost', 'value': 1, 'line': 2}],
                         'readers': [{'reader': 'Game.Godot/Scripts/UI.gd', 'line': 1}]}]
        atomic_json(self.root / 'docs/knowledge/generated/task-resource-links.json', {'generated': self.entries})
        self.candidate = self.root / 'logs/ci/chapter6-knowledge/task-18/semantic-candidate.json'
        self.output = self.root / 'docs/knowledge/generated/task-18-semantic.json'
        self.payload = {'status': 'verified', 'task_id': '18',
                        'generated_by': 'llm-assisted-semantic-analysis',
                        'generated_at_utc': '2026-10-10T00:00:00+00:00', 'coverage': {'scope': 'partial'},
                        'input_identity': publication.prepare_identity(self.root, '18', self.entries),
                        'entries': [{'path': self.entries[0]['path'], 'explanation': 'Card cost data.',
                                     'parameters': [{'pointer': '/cost', 'meaning': 'Energy cost'}], 'bindings': []}]}
        atomic_json(self.candidate, self.payload)

    def publish(self, **kwargs):
        return publication.publish(self.root, '18', candidate_sha256=file_sha(self.candidate),
                                   reviewed_by='fixture-reviewer', review_note='Checked resource meanings.', **kwargs)

    def state(self):
        return {'revision': 'directory:fixture', 'sources': {
            path: (self.root / path).read_text(encoding='utf-8')
            for path in self.payload['input_identity']['source_hashes']}}

    def test_preview_does_not_publish_and_confirm_binds_reviewed_candidate(self):
        self.assertEqual('preview', self.publish(confirm=False)['status'])
        self.assertFalse(self.output.exists())
        result = self.publish(confirm=True)
        self.assertEqual('published', result['status'])
        saved = load_json(self.output)
        self.assertEqual(file_sha(self.candidate), saved['publication']['candidate_sha256'])
        self.assertEqual('fixture-reviewer', saved['publication']['reviewed_by'])
        self.assertEqual(1, saved['entries'][0]['parameters'][0]['value'])
        self.assertTrue((self.root / result['evidence_path']).is_file())
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertEqual('current', info['freshness'])
        self.assertEqual('partial', info['scope'])
        self.assertEqual('Card cost data.', semantic['entries'][0]['explanation'])

    def test_unreviewed_candidate_hash_or_changed_sources_never_overwrite(self):
        self.publish(confirm=True)
        before = self.output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'candidate_hash_mismatch'):
            publication.publish(self.root, '18', candidate_sha256='sha256:wrong',
                                reviewed_by='fixture', review_note='Reviewed', confirm=True)
        (self.root / 'Game.Godot/Scripts/UI.gd').write_text('changed\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            self.publish(confirm=True)
        self.assertEqual(before, self.output.read_bytes())

    def test_snapshot_drift_hides_published_model_suggestions(self):
        self.publish(confirm=True)
        state = self.state()
        state['sources']['Game.Core/Data/cards.json'] = '{"cost": 2}'
        semantic, info = publication.load_for_navigation(self.root, '18', state)
        self.assertIsNone(semantic)
        self.assertEqual('stale', info['freshness'])
        self.assertIn('Game.Core/Data/cards.json', info['changed_paths'])

    def test_legacy_descriptions_remain_visible_with_unknown_freshness(self):
        atomic_json(self.output, {'status': 'verified', 'task_id': '18', 'entries': self.payload['entries']})
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertIsNotNone(semantic)
        self.assertEqual('legacy_unbound', info['freshness'])

    def test_generation_candidate_requires_identity_real_task_and_nonempty_explanations(self):
        for field, value in [('task_id', '19'), ('status', 'unverified'), ('input_identity', None),
                             ('entries', []), ('entries', [{'path': self.entries[0]['path']}])]:
            with self.subTest(field=field, value=value):
                atomic_json(self.candidate, {**self.payload, field: value})
                with self.assertRaises(ValueError):
                    self.publish(confirm=True)
                self.assertFalse(self.output.exists())

    def test_changed_task_resource_mapping_blocks_publication(self):
        changed = [dict(self.entries[0], role='Changed ownership')]
        atomic_json(self.root / 'docs/knowledge/generated/task-resource-links.json', {'generated': changed})
        with self.assertRaisesRegex(ValueError, 'resource_mapping_changed'):
            self.publish(confirm=True)

    def test_capture_generates_bound_candidate_without_automatic_publication(self):
        import chapter6_knowledge
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/sc'))
        def model(**kwargs):
            atomic_json(kwargs['output_last_message'], self.payload['entries'])
            return 0, '', ['fixture-model']
        with patch('_llm_backend.run_llm_exec', side_effect=model):
            result = chapter6_knowledge._semantic_enrich(self.root, '18', 'codex-cli', self.candidate.parent)
        saved = load_json(self.candidate)
        self.assertEqual('verified', result['status'])
        self.assertEqual(self.payload['input_identity'], saved['input_identity'])
        self.assertEqual('partial', saved['coverage']['scope'])
        self.assertEqual(1, saved['coverage']['described_resources'])
        self.assertTrue(saved['generated_at_utc'])
        self.assertFalse(self.output.exists())
        self.assertEqual('published', self.publish(confirm=True)['status'])

    def test_published_description_edits_invalidate_review_receipt(self):
        self.publish(confirm=True)
        payload = load_json(self.output)
        payload['entries'][0]['explanation'] = 'Unreviewed replacement'
        atomic_json(self.output, payload)
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertIsNone(semantic)
        self.assertEqual('invalid', info['freshness'])

    def test_cli_preview_confirm_and_rejection(self):
        cli = Path(__file__).resolve().parents[1] / 'dev_cli.py'
        command = [sys.executable, str(cli), 'publish-chapter6-semantics', '--repo-root', str(self.root),
                   '--task-id', '18', '--candidate-sha256', file_sha(self.candidate),
                   '--reviewed-by', 'fixture', '--review-note', 'Checked source meanings']
        preview = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, preview.returncode, preview.stderr)
        self.assertEqual('preview', json.loads(preview.stdout)['status'])
        self.assertFalse(self.output.exists())
        confirmed = subprocess.run(command + ['--confirm'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, confirmed.returncode, confirmed.stderr)
        self.assertEqual('published', json.loads(confirmed.stdout)['status'])
        self.candidate.write_text('{}', encoding='utf-8')
        rejected = subprocess.run(command + ['--confirm'], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(0, rejected.returncode)
        self.assertEqual('candidate_hash_mismatch', json.loads(rejected.stdout)['error'])

    def test_task_navigation_uses_reviewed_notes_and_suppresses_stale_notes(self):
        from project_health_knowledge import attach_published_semantics
        self.publish(confirm=True)
        def navigation():
            return {'configs': [{'path': self.entries[0]['path'], 'fields': [{'pointer': '/cost'}],
                                 'focused_fields': []}], 'assets': [], 'scenes': []}
        nav = navigation()
        attach_published_semantics(self.root, '18', nav, self.state())
        self.assertEqual('current', nav['semantic_publication']['freshness'])
        self.assertEqual('Card cost data.', nav['configs'][0]['semantic']['explanation'])
        state = self.state()
        state['sources']['Game.Core/Data/cards.json'] = '{"cost": 2}'
        nav = navigation()
        attach_published_semantics(self.root, '18', nav, state)
        self.assertEqual('stale', nav['semantic_publication']['freshness'])
        self.assertNotIn('semantic', nav['configs'][0])

    def test_failed_validation_and_source_drift_never_become_verified(self):
        import chapter6_knowledge
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/sc'))
        def invalid(**kwargs):
            atomic_json(kwargs['output_last_message'], [{'path': 'unknown.json'}])
            return 0, '', []
        with patch('_llm_backend.run_llm_exec', side_effect=invalid), patch('chapter6_knowledge.time.sleep'):
            result = chapter6_knowledge._semantic_enrich(self.root, '18', 'codex-cli', self.candidate.parent)
        self.assertEqual('unverified', result['status'])
        self.assertEqual('unverified', load_json(self.candidate)['status'])
        def drift(**kwargs):
            atomic_json(kwargs['output_last_message'], self.payload['entries'])
            atomic_json(self.root / self.entries[0]['path'], {'cost': 2})
            return 0, '', []
        with patch('_llm_backend.run_llm_exec', side_effect=drift):
            result = chapter6_knowledge._semantic_enrich(self.root, '18', 'codex-cli', self.candidate.parent)
        self.assertEqual('unverified', result['status'])
        self.assertIn('changed', load_json(self.candidate)['error'])

    def test_partial_coverage_reports_omitted_assets_and_truncated_parameters(self):
        import chapter6_knowledge
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/sc'))
        entries = [{**self.entries[0], 'parameters': [{'pointer': '/cost', 'value': 1}] * 81}]
        for index in range(13):
            path = f'Game.Godot/Assets/{index}.png'
            image = self.root / path
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b'fixture-image')
            entries.append({'task_id': '18', 'id': str(index), 'path': path, 'kind': 'asset'})
        atomic_json(self.root / 'docs/knowledge/generated/task-resource-links.json', {'generated': entries})
        def model(**kwargs):
            atomic_json(kwargs['output_last_message'], self.payload['entries'] + [
                {'path': entries[1]['path'], 'explanation': 'Card illustration'}])
            return 0, '', []
        with patch('_llm_backend.run_llm_exec', side_effect=model):
            result = chapter6_knowledge._semantic_enrich(self.root, '18', 'codex-cli', self.candidate.parent)
        self.assertEqual('verified', result['status'])
        coverage = load_json(self.candidate)['coverage']
        self.assertEqual((14, 13, 2), (coverage['available_resources'], coverage['supplied_resources'],
                                      coverage['described_resources']))
        self.assertEqual([entries[-1]['path']], coverage['omitted_resource_paths'])
        self.assertEqual([entries[0]['path']], coverage['truncated_resource_paths'])

    def test_malformed_or_partially_bound_notes_fail_closed_without_breaking_navigation(self):
        for payload in ([1], {'input_identity': {}}, {'publication': {}}):
            with self.subTest(payload=payload):
                atomic_json(self.output, payload)
                semantic, info = publication.load_for_navigation(self.root, '18', self.state())
                self.assertIsNone(semantic)
                self.assertEqual('invalid', info['freshness'])
        self.output.write_text('{invalid', encoding='utf-8')
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertIsNone(semantic)
        self.assertEqual('invalid', info['freshness'])

    def test_failed_publication_keeps_previous_reviewed_notes_usable(self):
        self.publish(confirm=True)
        before = self.output.read_bytes()
        original_write = publication.atomic_json
        def fail_output(path, payload):
            if path == self.output:
                raise OSError('fixture output write failure')
            return original_write(path, payload)
        with patch.object(publication, 'atomic_json', side_effect=fail_output):
            with self.assertRaises(OSError):
                self.publish(confirm=True)
        self.assertEqual(before, self.output.read_bytes())
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertIsNotNone(semantic)
        self.assertEqual('current', info['freshness'])

    def test_receipt_write_failure_never_replaces_previous_notes(self):
        self.publish(confirm=True)
        before = self.output.read_bytes()
        original_write = publication.atomic_json
        def fail_receipt(path, payload):
            if 'publications' in path.parts:
                raise OSError('fixture receipt write failure')
            return original_write(path, payload)
        with patch.object(publication, 'atomic_json', side_effect=fail_receipt):
            with self.assertRaises(OSError):
                self.publish(confirm=True)
        self.assertEqual(before, self.output.read_bytes())
        semantic, info = publication.load_for_navigation(self.root, '18', self.state())
        self.assertIsNotNone(semantic)
        self.assertEqual('current', info['freshness'])


if __name__ == '__main__':
    unittest.main()
