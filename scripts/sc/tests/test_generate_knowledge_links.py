import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
import generate_knowledge_links as links

class GenerateKnowledgeLinksTests(unittest.TestCase):
    def test_task_filter_limits_navigation_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest = root / 'logs/ci/project-health-knowledge/latest.json'
            latest.parent.mkdir(parents=True)
            latest.write_text(json.dumps({'revision': 'a' * 40, 'tasks': [
                {'task': {'id': 18}, 'mappings': [], 'godot': {}},
                {'task': {'id': 115}, 'mappings': [], 'godot': {}}]}), encoding='utf-8')
            seen = []
            links.build_navigation = lambda item, state: (seen.append(str(item['task']['id'])) or {'configs': [], 'assets': [], 'scenes': [], 'code': []})
            links.generate(root, {'18'})
            self.assertEqual(seen, ['18'])

    def test_write_task_refs_updates_only_selected_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest = root / 'logs/ci/project-health-knowledge/latest.json'
            latest.parent.mkdir(parents=True)
            latest.write_text(json.dumps({'revision': 'a' * 40, 'tasks': [
                {'task': {'id': 18}, 'mappings': [], 'godot': {}},
                {'task': {'id': 115}, 'mappings': [], 'godot': {}}]}), encoding='utf-8')
            task_file = root / '.taskmaster/tasks/tasks_gameplay.json'; task_file.parent.mkdir(parents=True)
            task_file.write_text(json.dumps([{'taskmaster_id': 18}, {'taskmaster_id': 115, 'knowledge_entry_ids': ['old']}]), encoding='utf-8')
            links.build_navigation = lambda item, state: {'configs': [], 'assets': [], 'scenes': [], 'code': []}
            links.generate(root, {'18'}, True)
            rows = json.loads(task_file.read_text(encoding='utf-8'))
            self.assertEqual(rows[0]['knowledge_entry_ids'], [])
            self.assertEqual(rows[1]['knowledge_entry_ids'], ['old'])


    def test_full_rebuild_replaces_stale_catalog_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest = root / 'logs/ci/project-health-knowledge/latest.json'
            latest.parent.mkdir(parents=True)
            latest.write_text(json.dumps({
                'revision': 'a' * 40,
                'tasks': [{'task': {'id': 192, 'title': 'Main Menu', 'test_refs': []}}],
            }), encoding='utf-8')
            catalog = root / 'docs/knowledge/catalog/knowledge-catalog.json'
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps({
                'schema_version': '1.0',
                'project': 'newrouge',
                'entries': [{'id': 'scene:115:Reward', 'task_id': '115', 'path': 'Reward.tscn'}],
                'last_scan_revision': None,
            }), encoding='utf-8')
            navigation = {
                'configs': [{'path': 'Game.Core/Data/newrouge.json', 'focus': 'core'}],
                'assets': [], 'scenes': [], 'code': [],
            }
            with mock.patch.object(links, 'base_dir', return_value=latest.parent), \
                    mock.patch.object(links, 'build_navigation', return_value=navigation):
                result = links.generate(root)
            self.assertEqual(result['entries'], 1)
            rebuilt = json.loads(catalog.read_text(encoding='utf-8'))
            self.assertEqual([entry['task_id'] for entry in rebuilt['entries']], ['192'])
            self.assertNotIn('Reward', json.dumps(rebuilt))

    def test_cli_without_task_ids_requests_full_rebuild(self):
        with mock.patch.object(links, 'generate', return_value={'status': 'ok'}) as generate:
            self.assertEqual(links.main([]), 0)
        self.assertIsNone(generate.call_args.args[1])

if __name__ == '__main__':
    unittest.main()
