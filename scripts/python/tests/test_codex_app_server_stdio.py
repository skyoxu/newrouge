"""Exercise actual process pipes; these fixtures never start a provider request."""
import json
import base64
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import _codex_app_server as transport


class AppServerStdioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.home=self.root/'metadata';self.home.mkdir()
        (self.home/'models_cache.json').write_text(json.dumps({'models':[{'slug':'fixture-model'}]}),encoding='utf-8')
        self.cwd=self.root/'empty';self.cwd.mkdir()
        self.methods=self.root/'methods.jsonl'
        self.child=Path(__file__).parent/'fixtures/codex_app_server_stdio_child.py'

    def command(self,mode):
        return [sys.executable,'-I','-S','-B',str(self.child),mode,str(self.methods)]

    def call(self,mode,**kwargs):
        requested = kwargs.pop('requested_reasoning_effort',
            os.environ.get('NEWROGUE_CODEX_REASONING_EFFORT', 'high'))
        environment = {'CODEX_HOME':str(self.home)}
        if requested is not None:
            environment['NEWROGUE_CODEX_REASONING_EFFORT'] = requested
        with patch.dict(os.environ,environment), \
             patch.object(transport,'command',side_effect=lambda *_:self.command(mode)):
            if requested is None:
                os.environ.pop('NEWROGUE_CODEX_REASONING_EFFORT', None)
            return transport.run_request('synthetic-child',cwd=self.cwd,prompt=kwargs.pop('prompt','complete input'),
                schema={'type':'object'},timeout_sec=kwargs.pop('timeout_sec',5),**kwargs)

    def observed(self):
        return [json.loads(line)['method'] for line in self.methods.read_text(encoding='utf-8').splitlines()]

    def test_real_pipes_complete_one_bound_synthetic_turn(self):
        output,proof=self.call('success')
        self.assertEqual('{"status":"ok"}',output)
        self.assertEqual('fixture-model',proof['model'])
        self.assertEqual(1,self.observed().count('turn/start'))
        self.assertFalse(proof['provider_identity_verified'])

    def test_optional_high_thread_config_and_live_mismatch_precede_turn(self):
        with patch.dict(os.environ, {'NEWROGUE_CODEX_REASONING_EFFORT':'high'}):
            output, proof = self.call('reasoning_high')
            self.assertEqual('{"status":"ok"}', output)
            self.assertEqual(proof['requested_reasoning_effort'], 'high')
            self.assertEqual(proof['runtime_reasoning_effort'], 'high')
            rows = [json.loads(line) for line in base64.b64decode(proof['protocol_jsonl_base64']).decode().splitlines()]
            request = next(row['message'] for row in rows if row['direction']=='client' and row['message'].get('method')=='thread/start')
            self.assertEqual(request['params']['config']['model_reasoning_effort'], 'high')
            self.assertEqual(request['params']['sandbox'], 'read-only')
            self.assertTrue(request['params']['ephemeral'])
            self.assertEqual(request['params']['dynamicTools'], [])
            self.assertIs(request['params']['config']['features']['shell_tool'], False)
            self.assertEqual(self.observed().count('turn/start'), 1)
            for mode in ('reasoning_medium', 'reasoning_missing', 'reasoning_low'):
                self.methods.unlink()
                with self.assertRaisesRegex(ValueError, 'requested_reasoning_effort_mismatch'):
                    self.call(mode)
                self.assertIn('thread/start', self.observed())
                self.assertNotIn('turn/start', self.observed())

    def test_invalid_reasoning_environment_rejected_before_child_or_workspace_write(self):
        for value in ('', 'medium', 'low', 'HIGH'):
            with patch.dict(os.environ, {'NEWROGUE_CODEX_REASONING_EFFORT':value}), \
                 patch.object(transport.subprocess, 'Popen', side_effect=AssertionError('No child')):
                with self.assertRaisesRegex(ValueError, 'unsupported_requested_reasoning_effort'):
                    self.call('success')
        self.assertFalse(self.methods.exists())
        self.assertFalse((self.cwd/'no-tools-model-catalog.json').exists())

    def test_live_mcp_inventory_blocks_before_any_turn_start(self):
        for mode in ['bad_mcp','partial_mcp']:
            with self.subTest(mode=mode):
                self.methods.unlink(missing_ok=True)
                with self.assertRaisesRegex(ValueError,'mcp_tools_available'):
                    self.call(mode)
                self.assertIn('thread/start',self.observed())
                self.assertNotIn('turn/start',self.observed())

    def test_live_server_tool_request_is_not_serviced(self):
        with self.assertRaisesRegex(ValueError,'server_tool_or_auth_request'):
            self.call('host_request')
        self.assertEqual(1,self.observed().count('turn/start'))

    def test_first_actual_max_output_error_is_journaled_and_owned_child_reaped_promptly(self):
        original = subprocess.Popen
        unrelated = original([sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(30)'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for mode in ('max_output_message', 'max_output_details', 'max_output_rpc'):
                with self.subTest(mode=mode):
                    processes = []
                    def launch(command, *args, **kwargs):
                        proc = original(command, *args, **kwargs)
                        if str(self.child) in command:
                            processes.append(proc)
                        return proc
                    journal = self.root / (mode + '.jsonl')
                    started = time.monotonic()
                    with patch.object(transport.subprocess, 'Popen', side_effect=launch):
                        with self.assertRaisesRegex(ValueError, 'codex_app_server_max_output_tokens'):
                            self.call(mode, timeout_sec=15, journal_path=journal)
                    self.assertLess(time.monotonic() - started, 5, 'Must stop before the original turn timeout')
                    self.assertEqual(len(processes), 1)
                    self.assertIsNotNone(processes[0].poll(), 'Original cleanup must reap its owned process')
                    self.assertIsNone(unrelated.poll(), 'An unrelated process must remain untouched')
                    rows = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
                    errors = [r['message'] for r in rows if r['direction'] == 'server' and
                              (r['message'].get('method') == 'error' or 'error' in r['message'])]
                    self.assertEqual(len(errors), 1)
                    self.assertIn('max_output_tokens', json.dumps(errors[0]))
                    self.assertTrue(journal.with_suffix('.stderr.txt').is_file())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)

    def test_existing_legacy_transient_success_and_unrelated_max_output_text_remain_accepted(self):
        # A v2 method=error still fails strict replay; this is the historical legacy path.
        output, proof = self.call('legacy_transient')
        self.assertEqual(output, '{"status":"ok"}')
        rows = [json.loads(line) for line in base64.b64decode(proof['protocol_jsonl_base64']).decode().splitlines()]
        self.assertTrue(any(row['message'].get('method') == 'codex/event/error' for row in rows))
        self.assertEqual(self.observed().count('turn/start'), 1)

    def test_stalled_stdin_write_honors_deadline_and_reaps_only_own_child(self):
        processes=[];finished=queue.Queue();original=subprocess.Popen
        def launch(*args,**kwargs):
            proc=original(*args,**kwargs);processes.append(proc);return proc
        def run():
            try:self.call('stall',prompt='x'*(512*1024),timeout_sec=2)
            except BaseException as error:finished.put(error)
            else:finished.put(None)
        started=time.monotonic()
        with patch.object(transport.subprocess,'Popen',side_effect=launch):
            worker=threading.Thread(target=run,daemon=True);worker.start()
            try:
                error=finished.get(timeout=4)
            except queue.Empty:
                error=AssertionError('Input writer exceeded its deadline')
            finally:
                exited_before_fallback=bool(processes) and all(proc.poll() is not None for proc in processes)
                for proc in processes:
                    if proc.poll() is None:proc.kill()
                worker.join(timeout=3)
        self.assertIsInstance(error,TimeoutError)
        self.assertTrue(exited_before_fallback,'Transport must reap its child before test fallback cleanup')
        self.assertLess(time.monotonic()-started,4)
        self.assertEqual('mcpServerStatus/list',self.observed()[-1])
        self.assertTrue(processes and all(proc.poll() is not None for proc in processes))

    def test_noisy_child_cannot_queue_more_than_transcript_limit(self):
        original_queue=queue.Queue;original_loads=json.loads;peaks=[]
        class ObservedQueue(original_queue):
            def _put(self,item):
                super()._put(item)
                peaks.append(sum(len(value.encode('utf-8')) for value in self.queue if isinstance(value,str)))
        def slow_consumer(value,*args,**kwargs):
            if isinstance(value,str) and '"fixture/noise"' in value:time.sleep(0.5)
            return original_loads(value,*args,**kwargs)
        with patch.object(transport,'MAX_TRANSCRIPT_BYTES',32768), \
             patch.object(transport.queue,'Queue',ObservedQueue), \
             patch.object(transport.json,'loads',side_effect=slow_consumer):
            with self.assertRaisesRegex(ValueError,'transcript_too_large'):
                self.call('flood')
        self.assertLessEqual(max(peaks),32768)
        self.assertNotIn('turn/start',self.observed())

    def test_completed_turn_drains_large_shutdown_tail_before_waiting_for_exit(self):
        journal = self.root / 'tail.jsonl'
        with patch.dict(os.environ, {'NEWROGUE_CODEX_REASONING_EFFORT':'high'}):
            output, proof = self.call('tail_backpressure', timeout_sec=3, journal_path=journal)
        self.assertEqual(output, '{"status":"ok"}')
        self.assertEqual(proof['runtime_reasoning_effort'], 'high')
        raw = base64.b64decode(proof['protocol_jsonl_base64'])
        self.assertEqual(journal.read_text(encoding='utf-8').encode('utf-8'), raw)
        rows = [json.loads(line) for line in raw.splitlines()]
        tails = [row['message']['params'] for row in rows
                 if row['message'].get('method') == 'fixture/shutdown']
        self.assertEqual([tail['sequence'] for tail in tails], list(range(128)))
        self.assertGreater(sum(len(tail['padding']) for tail in tails), 1024 * 1024 - 1)
        self.assertEqual(rows[-1]['message']['params']['sequence'], 127)
        self.assertEqual(self.observed().count('turn/start'), 1)

    def test_large_shutdown_tail_cannot_hide_late_error_tool_or_reroute(self):
        for mode, reason in (('tail_error', 'execution_error'),
                             ('tail_tool', 'model_tools_observed'),
                             ('tail_reroute', 'runtime_configuration_changed'),
                             ('tail_max_output', 'max_output_tokens'),
                             ('tail_nonzero', 'process_failed')):
            with self.subTest(mode=mode):
                self.methods.unlink(missing_ok=True)
                journal = self.root / (mode + '.jsonl')
                with self.assertRaisesRegex(ValueError, reason):
                    self.call(mode, timeout_sec=3, journal_path=journal)
                rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
                self.assertTrue(any(row['message'].get('method') == 'turn/completed' for row in rows))
                tails = [row for row in rows if row['message'].get('method') == 'fixture/shutdown']
                self.assertEqual(len(tails), 128)
                self.assertEqual(self.observed().count('turn/start'), 1)

    def test_completed_turn_requires_eof_and_exit_within_original_deadline(self):
        original = subprocess.Popen
        for mode in ('tail_no_exit', 'tail_deadline'):
            with self.subTest(mode=mode):
                self.methods.unlink(missing_ok=True)
                processes = []
                def launch(command, *args, **kwargs):
                    proc = original(command, *args, **kwargs)
                    if str(self.child) in command:
                        processes.append(proc)
                    return proc
                journal = self.root / (mode + '.jsonl')
                timeout_sec = 2 if mode == 'tail_deadline' else 1
                started = time.monotonic()
                with patch.object(transport.subprocess, 'Popen', side_effect=launch):
                    with self.assertRaises(TimeoutError) as stopped:
                        self.call(mode, timeout_sec=timeout_sec, journal_path=journal)
                self.assertLess(time.monotonic() - started, timeout_sec + 0.8,
                                'Shutdown must not receive a fresh request timeout')
                self.assertIn('output did not close' if mode == 'tail_deadline' else
                              'did not exit after completed turn', str(stopped.exception))
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll(), 'Failed shutdown must reap its owned child')
                rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
                self.assertTrue(any(row['message'].get('method') == 'turn/completed' for row in rows))
                self.assertEqual(self.observed().count('turn/start'), 1)

    def test_clean_slow_exit_uses_remaining_request_budget_without_ten_second_cap(self):
        output, proof = self.call('tail_slow_exit', timeout_sec=13)
        self.assertEqual(output, '{"status":"ok"}')
        self.assertEqual(proof['model'], 'fixture-model')
        self.assertEqual(self.observed().count('turn/start'), 1)
