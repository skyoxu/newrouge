"""Execute the topology frontend regression against committed semantic data."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class TopologyFrontendTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for frontend tests')
    def test_node_kind_filters_and_links(self):
        result = subprocess.run(
            ['node', str(ROOT / 'scripts/python/tests/js/test_topology_node_kinds.cjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for frontend tests')
    def test_planning_buttons_refresh_data_and_keep_compact_results(self):
        result = subprocess.run(
            ['node', str(ROOT / 'scripts/python/tests/js/test_knowledge_planning.cjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for frontend tests')
    def test_b_route_planning_page_stage_true_ui_contract(self):
        result = subprocess.run(
            ['node', str(ROOT / 'scripts/python/tests/js/test_b_route_planning_page_ui.cjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
