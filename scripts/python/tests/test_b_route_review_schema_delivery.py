"""Offline worker boundary: compact review schema without changing its values."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _b_route_planning_runtime as runtime
import _mvg_capability_worker as worker
import plan_mvg
from _planning_skill_common import file_sha


class SchemaDeliveryTests(unittest.TestCase):
    def test_real_worker_writes_compact_only_for_indexed_review_before_dispatch(self):
        class Captured(BaseException):
            pass
        temporary = tempfile.TemporaryDirectory(prefix='nr25-schema-', dir=r'C:\Windows\TEMP')
        root = Path(temporary.name).resolve()
        self.assertEqual(root.parent, Path(r'C:\Windows\TEMP').resolve())
        try:
            runner = root/'dummy-runner.py'
            runner.write_text('# Offline fixture. Never executed.\n', encoding='utf8')
            config = {'runner': str(runner), 'runner_sha256': file_sha(runner)}
            for name, marker, compact in [('indexed', runtime.INDEXED_REVIEW, True),
                                          ('legacy', runtime.REVIEW, False)]:
                schema = {'type': 'object', 'properties': {'schema_version': {'type': 'string', 'const': marker},
                    'literal': {'type': 'string', 'description': 'Unicode \u00e9 and literal \\n retained'}},
                    'required': ['schema_version', 'literal'], 'additionalProperties': False}
                target = root/name
                with patch.object(runtime, 'descriptor', return_value={}), \
                     patch.object(plan_mvg, '_validate_input_freshness', side_effect=Captured()):
                    invoke = worker.runner_invoke(root, root, {'input_stage': '3b'}, target, config, None)
                    with self.assertRaises(Captured):
                        invoke('Complete offline prompt.', 4, output_name='r.json',
                            output_schema_path=target/'output-schema.json', output_schema=schema)
                path = target/'llm-sandbox/attempt-4/r/output-schema.json'
                expected = (json.dumps(schema, ensure_ascii=False,
                    **({'separators': (',', ':')} if compact else {'indent': 2}))+'\n').encode('utf8')
                self.assertEqual(path.read_bytes(), expected)
                self.assertEqual(json.loads(path.read_bytes()), schema)
                self.assertFalse((path.parent/'r.json').exists())
                self.assertFalse(any(target.rglob('*.tmp')))
        finally:
            temporary.cleanup()


if __name__ == '__main__':
    unittest.main()
