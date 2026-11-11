"""Windows process composition: real pending inventory + locks + public reserve.

Only native eligibility is a synthetic seam. Neither process dispatches a model.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import _b_route_adoption as adoption
import _b_route_codec as codec
import _planning_apply_journal as journal
import test_b_route_adoption as composition


class AdoptionProcessCompositionTests(unittest.TestCase):
    def test_real_inventory_and_two_windows_processes_exclude_reserve_then_allow_it_after_release(self):
        self.assertEqual('nt', os.name, 'This required test is a native Windows process test')
        fx = composition.AdoptionCompositionTests('test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target')
        fx.setUp()
        prepared = fx.prepare()
        operation = fx.root / prepared['resume_ref']
        before = operation.read_bytes()
        child = Path(__file__).parent / 'fixtures/adoption_scope_process.py'
        dependencies = [value for value in sys.path if 'site-packages' in value or 'story22-tokenizer-deps' in value]
        process = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(child), str(fx.root.resolve()),
            'OP-one', json.dumps(dependencies)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            ready_lines = queue.Queue()
            reader = threading.Thread(target=lambda: ready_lines.put(process.stdout.readline()), daemon=True)
            reader.start()
            line = ready_lines.get(timeout=15)
            self.assertTrue(line, 'Owned holder must reach real scope boundary')
            ready = json.loads(line)
            self.assertEqual('holding', ready['status'])
            self.assertEqual(1, ready['inventory_count'])
            self.assertEqual(prepared['frozen_digest'], ready['frozen_digest'])
            self.assertEqual(prepared['scope_ids'], ready['scopes'])
            with patch.object(adoption, 'capture_completed', fx.synthetic_capture), self.assertRaises(codec.CodecError) as caught:
                adoption.reserve(fx.root, operation_id='OP-one')
            self.assertEqual(codec.ReasonCode.CONFLICT, caught.exception.diagnostic.reason_code)
            self.assertEqual(before, operation.read_bytes())
            self.assertEqual('prepared', journal.read_operation(fx.root, operation_id='OP-one')['state'])
            stdout, stderr = process.communicate('\n', timeout=15)
            self.assertEqual(0, process.returncode, stderr)
            self.assertEqual('released', json.loads(stdout)['status'])
            with patch.object(adoption, 'capture_completed', fx.synthetic_capture):
                result = adoption.reserve(fx.root, operation_id='OP-one')
            self.assertEqual('reserved', result['state'])
            self.assertEqual(prepared['frozen_digest'], result['frozen_digest'])
            self.assertEqual(1, len(journal.operation_inventory(fx.root)))
            self.assertFalse((fx.root / 'docs/planning/b-route').exists())
            self.assertTrue(all(result[key] is False for key in adoption.FLAGS))
        finally:
            if process.poll() is None:
                process.kill()  # only the exact process object created by this fixture
            process.communicate(timeout=15)


if __name__ == '__main__':
    unittest.main(verbosity=2)
