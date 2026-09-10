import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from init_knowledge_catalog import initialize

class InitKnowledgeCatalogTests(unittest.TestCase):
    def test_initialize_is_idempotent_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = initialize(root, validate=True)
            self.assertEqual(first['status'], 'ok')
            second = initialize(root, validate=True)
            self.assertEqual(second['created'], [])
            self.assertEqual(len(second['skipped']), 8)
            catalog = json.loads((root / 'docs/knowledge/catalog/knowledge-catalog.json').read_text(encoding='utf-8'))
            self.assertEqual(catalog['project'], 'newrouge')

if __name__ == '__main__':
    unittest.main()
