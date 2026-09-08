import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
import chapter6_knowledge

class Chapter6KnowledgeTests(unittest.TestCase):
    def test_failure_is_explicit_and_stops_at_failing_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = chapter6_knowledge.run(root, '18')
            self.assertEqual(result['status'], 'knowledge_capture_failed')
            self.assertEqual(result['stop_step'], 1)

if __name__ == '__main__':
    unittest.main()
