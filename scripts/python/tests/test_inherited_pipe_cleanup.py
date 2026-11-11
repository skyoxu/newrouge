"""Owned synthetic descendants only; no model, authentication, or network access."""
from pathlib import Path
import contextlib
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
FIXTURE = Path(__file__).parent / 'fixtures/codex_app_server_stdio_child.py'


@contextlib.contextmanager
def case_directory():
    temporary_root = Path(tempfile.gettempdir()).resolve()
    root = Path(tempfile.mkdtemp(prefix='hp-', dir=temporary_root)).resolve()
    assert root.parent == temporary_root
    # Preserve every controlled fixture and its signal/identity evidence.
    yield root


def worker(kind, root):
    import _codex_app_server as transport
    import _planning_skill_common as common
    log = root / 'methods.jsonl'
    workspace = root / 'workspace'
    workspace.mkdir()
    metadata = root / 'metadata'
    metadata.mkdir()
    (metadata / 'models_cache.json').write_text(json.dumps({'models': [{'slug': 'fixture-model'}]}))
    prompt = workspace / 'prompt.txt'
    prompt.write_text('synthetic', encoding='utf-8')
    started = time.monotonic()
    try:
        if kind == 'transport':
            command = [sys.executable, '-I', '-S', '-B', str(FIXTURE), 'tail_inherited_exit', str(log)]
            with patch.dict(os.environ, {'CODEX_HOME': str(metadata), 'NEWROGUE_CODEX_REASONING_EFFORT': 'high'}), \
                 patch.object(transport, 'command', return_value=command):
                transport.run_request('synthetic', cwd=workspace, prompt='synthetic',
                    schema={'type': 'object'}, timeout_sec=1, journal_path=root / 'journal.jsonl')
        else:
            command = [sys.executable, '-I', '-S', '-B', str(FIXTURE), 'outer_inherited_exit', str(log)]
            with patch.object(common, '_runner_prefix', return_value=command):
                common.run_isolated_model(FIXTURE, workspace=workspace, prompt_path=prompt,
                    output_path=workspace / 'output.json', timeout_sec=1, wall_timeout_sec=1,
                    execution_log=root / 'execution.json')
    except BaseException as error:
        result = {'kind': kind, 'type': type(error).__name__, 'detail': str(error),
                  'elapsed': time.monotonic() - started, 'success_receipt': False}
    else:
        result = {'kind': kind, 'type': 'unexpected-success', 'elapsed': time.monotonic() - started,
                  'success_receipt': True}
    print(json.dumps(result), flush=True)


@unittest.skipUnless(os.name == 'nt', 'Windows owned-pipe cancellation contract')
class InheritedPipeCleanupTests(unittest.TestCase):
    def test_outer_natural_exit_preserves_exact_bytes_and_receipt(self):
        import _planning_skill_common as common
        with case_directory() as root:
            command = [sys.executable, '-I', '-S', '-B', str(FIXTURE), 'outer_exact_exit', str(root / 'methods.jsonl')]
            prompt = root / 'prompt.txt'
            prompt.write_text('synthetic', encoding='utf-8')
            with patch.object(common, '_runner_prefix', return_value=command):
                receipt = common.run_isolated_model(FIXTURE, workspace=root, prompt_path=prompt,
                    output_path=root / 'output.json', timeout_sec=1, wall_timeout_sec=1,
                    execution_log=root / 'execution.json')
            self.assertEqual(receipt, {'synthetic': True})
            execution = json.loads((root / 'execution.json').read_text())
            self.assertEqual(execution['status'], 'completed')
            self.assertEqual(execution['returncode'], 0)
            self.assertEqual(base64.b64decode(execution['stdout_base64']), 'prefix \u03c0\r\n{"synthetic":true}\r\n'.encode('utf-8'))

    def test_outer_text_capture_preserves_universal_newlines(self):
        import _planning_skill_common as common
        with case_directory() as root:
            command = [sys.executable, '-I', '-S', '-B', str(FIXTURE), 'outer_exact_exit',
                str(root / 'methods.jsonl'), '--output', str(root / 'output.json')]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as proc:
                capture = common._WindowsRunnerOutput(proc)
                stdout, stderr = capture.communicate(1)
                self.assertEqual(stdout, 'prefix \u03c0\n{"synthetic":true}\n')
                self.assertIsNone(stderr)
                capture.worker.join(timeout=0.5)
                self.assertFalse(capture.worker.is_alive())

    def test_exited_parent_inherited_pipes_have_bounded_failure_cleanup(self):
        evidence = []
        for kind in ('transport', 'outer'):
            with self.subTest(kind=kind), case_directory() as root:
                command = [sys.executable, '-I', '-S', '-B', __file__, '--worker', kind, str(root)]
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                forced_signal = False
                try:
                    try:
                        proc.wait(timeout=2.5)
                    except subprocess.TimeoutExpired:
                        forced_signal = True
                    finally:
                        # A unique test-local signal, never a broad PID/tree termination.
                        (root / 'methods.holder-exit').touch()
                    stdout, stderr = proc.communicate(timeout=5)
                    limit = time.monotonic() + 2
                    while not (root / 'methods.holder-done').exists() and time.monotonic() < limit:
                        time.sleep(0.02)
                    identity = json.loads((root / 'methods.holder-pid.json').read_text())
                    self.assertEqual((root / 'methods.holder-done').read_text(), str(identity['pid']))
                    self.assertEqual(proc.returncode, 0, stderr)
                    result = json.loads(stdout)
                    result['supervisor_had_to_release_pipe_holder'] = forced_signal
                    evidence.append(result)
                    (root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                    print(json.dumps(result), flush=True)
                    self.assertFalse(result['success_receipt'])
                    self.assertEqual(result['type'], 'TimeoutError', result)
                    if kind == 'outer':
                        execution = json.loads((root / 'execution.json').read_text())
                        self.assertEqual(execution['status'], 'timeout')
                        self.assertEqual(base64.b64decode(execution['stdout_base64']), b'captured prefix \xcf\x80\xff\r\n')
                        self.assertFalse((root / 'workspace/output.json').exists())
                    else:
                        rows = [json.loads(line) for line in (root / 'journal.jsonl').read_text().splitlines()]
                        runtime = next(row['message']['result'] for row in rows
                            if row['direction'] == 'server' and row['message'].get('id') == 2)
                        self.assertEqual(runtime['reasoningEffort'], 'high')
                    self.assertFalse(forced_signal, result)
                    self.assertLess(result['elapsed'], 2.3, result)
                finally:
                    (root / 'methods.holder-exit').touch()
                    if proc.poll() is None:
                        # Only our original Popen handle, never an inferred or reused PID.
                        proc.kill()
                    proc.communicate(timeout=5)
                    proc.stdout.close()
                    proc.stderr.close()
        print(json.dumps({'synthetic_only': True, 'cases': evidence}), flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--worker']:
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        unittest.main()
