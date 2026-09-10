import json
import tempfile
import unittest
from pathlib import Path
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

if __name__ == '__main__':
    unittest.main()
