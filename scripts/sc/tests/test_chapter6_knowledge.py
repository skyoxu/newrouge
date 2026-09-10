import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
import chapter6_knowledge

class Chapter6KnowledgeTests(unittest.TestCase):
    def test_semantic_parameters_must_match_exact_config_pointer(self):
        entries = [{'id': 'config:18:data.json', 'path': 'data.json', 'kind': 'config',
                    'parameters': [{'pointer': '/cards/0/cost', 'value': 1, 'line': 3}]}]
        valid, model, error = chapter6_knowledge._validate_semantic_entries(
            [{'path': 'data.json', 'parameters': [{'pointer': '/cards/0/damage', 'meaning': 'Damage'}]}], entries)
        self.assertFalse(valid)
        self.assertFalse(model)
        self.assertIn('Unknown parameter pointer', error)

    def test_semantic_parameters_preserve_verified_field_location(self):
        entries = [{'id': 'config:18:data.json', 'path': 'data.json', 'kind': 'config',
                    'parameters': [{'pointer': '/cards/0/cost', 'value': 1, 'line': 3}]}]
        valid, model, error = chapter6_knowledge._validate_semantic_entries(
            [{'path': 'data.json', 'explanation': 'Card data',
              'parameters': [{'key': '/cards/0/cost', 'meaning': 'Energy cost'}]}], entries)
        self.assertTrue(valid, error)
        self.assertEqual(model[0]['parameters'][0], {
            'pointer': '/cards/0/cost', 'meaning': 'Energy cost', 'value': 1, 'line': 3,
            'evidence_status': 'field_exists_semantic_inference'})

    def test_semantic_output_rejects_non_object_entries(self):
        valid, _, error = chapter6_knowledge._validate_semantic_entries(['bad'], [])
        self.assertFalse(valid)
        self.assertIn('array of objects', error)

    def test_semantic_prompt_only_includes_configs_and_prioritizes_numeric_fields(self):
        prompt_entries = chapter6_knowledge._semantic_prompt_entries([
            {'path': 'scene.tscn', 'kind': 'scene'},
            {'path': 'data.json', 'kind': 'config', 'parameters': [
                {'pointer': '/name', 'value': 'A', 'line': 1, 'kind': 'data_field'},
                {'pointer': '/cost', 'value': 2, 'line': 2, 'kind': 'numeric_parameter'},
            ]},
        ])
        self.assertEqual([entry['path'] for entry in prompt_entries], ['data.json'])
        self.assertEqual(prompt_entries[0]['available_parameters'][0]['pointer'], '/cost')

    def test_failure_is_explicit_and_stops_at_failing_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = chapter6_knowledge.run(root, '18')
            self.assertEqual(result['status'], 'knowledge_capture_failed')
            self.assertEqual(result['stop_step'], 1)

if __name__ == '__main__':
    unittest.main()
