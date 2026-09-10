import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ProjectHealthKnowledgeUiTests(unittest.TestCase):
    def test_configuration_is_split_into_four_named_sections(self):
        html = (ROOT / 'scripts/python/project_health_knowledge.html').read_text(encoding='utf-8')
        for element_id in ('config-source-paths', 'config-gdd-paths', 'config-task-scene-bindings',
                           'config-query-aliases', 'config-advanced'):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('任务场景人工映射', html)

    def test_javascript_round_trips_categorized_configuration(self):
        script = (ROOT / 'scripts/python/project_health_knowledge.js').read_text(encoding='utf-8')
        self.assertIn('function renderConfigEditor(config)', script)
        self.assertIn('function collectConfigEditor()', script)
        for key in ('source_paths', 'gdd_paths', 'task_scene_bindings', 'query_aliases'):
            self.assertIn(key, script)

    def test_configuration_opens_in_a_modal_dialog(self):
        html = (ROOT / 'scripts/python/project_health_knowledge.html').read_text(encoding='utf-8')
        script = (ROOT / 'scripts/python/project_health_knowledge.js').read_text(encoding='utf-8')

        self.assertIn('id="open-config"', html)
        self.assertIn('<dialog id="config-dialog"', html)
        self.assertIn('id="close-config"', html)
        self.assertIn("el('open-config').onclick=()=>el('config-dialog').showModal();", script)
        self.assertIn("el('close-config').onclick=()=>el('config-dialog').close();", script)

    def test_source_configuration_lists_reasons_before_suggested_paths(self):
        html = (ROOT / 'scripts/python/project_health_knowledge.html').read_text(encoding='utf-8')
        script = (ROOT / 'scripts/python/project_health_knowledge.js').read_text(encoding='utf-8')

        self.assertIn('id="config-source-requirements"', html)
        self.assertIn('任一项都可以留空', html)
        self.assertIn('const sourcePathRequirements = [', script)
        self.assertIn('function renderSourcePathRequirements(config={})', script)
        self.assertLess(script.index("reason.textContent=item.reason"), script.index("input.dataset.sourceKey=item.key"))
        self.assertIn("input.dataset.sourceKey=item.key", script)
        self.assertIn('source_path_bindings', script)


if __name__ == '__main__':
    unittest.main()
