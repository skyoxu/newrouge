"""Real owned Windows Job/pipe regressions plus deterministic failure controls.

All children are neutral fixture readers/verifiers. No original native verifier,
model, API, taskkill or process inventory is invoked. Owned TEMP sites are retained.
"""
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent / 'sc')]
import _b_route_reader_lifetime as lifetime
from _mvg_capability_checkpoint import coordinator_lock

FIXTURE = Path(__file__).parent / 'fixtures/reader_lifecycle.py'


def command(role, root):
    program = ('import runpy,sys;sys.argv=[' + repr(str(FIXTURE)) + ',' + repr(role) + ',' + repr(str(root)) + '];'
               'runpy.run_path(' + repr(str(FIXTURE)) + ',run_name="__main__")')
    return [sys.executable, '-I', '-S', '-B', '-c', lifetime.GATE + program]


class PipeOwnershipTests(unittest.TestCase):
    def test_close_only_errors_remain_failures_and_delivered_bytes_survive(self):
        class FailsClose(io.BytesIO):
            def close(self):
                if not getattr(self, 'close_failed', False):
                    self.close_failed = True
                    raise OSError('owned stream close failed')
                super().close()
        process = SimpleNamespace(stdout=FailsClose(b'observed stdout'), stderr=FailsClose(b'observed stderr'),
                                  stdin=FailsClose())
        pipes = lifetime._Pipes(process)
        pipes._read('stdout')
        pipes._read('stderr')
        pipes._write(b'start\nrequest')
        self.assertEqual(b'observed stdout', pipes.data('stdout'))
        self.assertEqual(b'observed stderr', pipes.data('stderr'))
        self.assertEqual(3, len(pipes.errors))
        for stream in (process.stdout, process.stderr, process.stdin):
            stream.close()

    def test_failed_worker_start_closes_only_unowned_buffers(self):
        process = SimpleNamespace(stdout=io.BytesIO(), stderr=io.BytesIO(), stdin=io.BytesIO())
        pipes = lifetime._Pipes(process)
        with patch.object(threading.Thread, 'start', side_effect=RuntimeError('cannot start owned writer')):
            with self.assertRaises(RuntimeError):
                pipes.release(b'request')
        pipes.close_unowned()
        self.assertTrue(all(getattr(process, name).closed for name in ('stdin', 'stdout', 'stderr')))


@unittest.skipUnless(os.name == 'nt', 'Windows Job and held-handle contract')
class WindowsReaderLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='newrouge-reader-lifetime-'))
        self.environment = {**os.environ, 'BR_READER_FIXTURE_RECEIVER': str(os.getpid())}
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.TerminateProcess.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.held = []
        self.addCleanup(self.close_owned_handles)

    def close_owned_handles(self):
        for handle in self.held:
            if self.api.WaitForSingleObject(handle, 0) == 258:
                # Assertion failure fallback targets only a transferred actual
                # handle to this test's child, never a remembered descendant PID.
                self.api.TerminateProcess(handle, 2)
                self.api.WaitForSingleObject(handle, 5000)
            self.api.CloseHandle(handle)

    def verifier_handle(self):
        path = self.root / 'verifier-handle'
        self.assertTrue(path.is_file(), 'Verifier handle transfer must precede the exercised deadline')
        handle = int(path.read_text(encoding='ascii'))
        self.held.append(handle)
        return handle

    def run_reader(self, role, *, timeout=10):
        return lifetime.run_reader(command(role, self.root), input=b'unchanged canonical fixture request',
            cwd=self.root, env=self.environment, timeout=timeout)

    def lock_probe(self):
        result = subprocess.run([sys.executable, '-I', '-S', '-B', str(FIXTURE), 'lock-probe', str(self.root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
        return result.stdout.strip()

    def test_real_normal_reader_and_verifier_finish_with_separate_exact_pipes_and_empty_job(self):
        observed = []
        active = lifetime.ReaderJob.active
        def accounting(job):
            count = active(job)
            observed.append(count)
            return count
        with patch.object(lifetime.ReaderJob, 'active', accounting):
            result = self.run_reader('normal')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b'reader-stdout\n', result.stdout)
        self.assertEqual(b'reader-stderr\n', result.stderr)
        self.assertEqual(0, observed[-1])
        self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 0))

    def test_real_timeout_reaps_verifier_before_original_lock_release_and_preserves_sentinel(self):
        sentinel = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'import time;time.sleep(60)'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with coordinator_lock(self.root):
                started = time.monotonic()
                with self.assertRaises(lifetime.ReaderTransportError) as caught:
                    self.run_reader('slow', timeout=2)
                error = caught.exception
                self.assertEqual(('timeout', 'confirmed_empty'), (error.outcome, error.cleanup))
                self.assertLess(time.monotonic() - started, 2 + lifetime.CLEANUP_TIMEOUT + 2)
                self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 0))
                self.assertEqual(b'busy', self.lock_probe())
                self.assertIsNone(sentinel.poll())
            self.assertEqual(b'acquired', self.lock_probe())
            self.assertEqual(b'reader-stdout\n', error.stdout)
            self.assertEqual(b'reader-stderr\n', error.stderr)
        finally:
            sentinel.terminate()
            sentinel.communicate(timeout=10)

    def test_real_reader_exit_first_with_descendant_holding_pipe_has_bounded_cleanup(self):
        started = time.monotonic()
        with self.assertRaises(lifetime.ReaderTransportError) as caught:
            self.run_reader('exit-first', timeout=10)
        self.assertEqual('descendants_after_reader_exit', caught.exception.outcome)
        self.assertEqual('confirmed_empty', caught.exception.cleanup)
        self.assertLess(time.monotonic() - started, lifetime.CLEANUP_TIMEOUT + 3)
        self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 0))
        self.assertEqual(b'reader-stdout\n', caught.exception.stdout)

    def test_assignment_failure_or_unreleased_stdin_never_enters_fixture(self):
        with patch.object(lifetime.ReaderJob, 'assign', side_effect=OSError('synthetic assignment refused')):
            with self.assertRaises(lifetime.ReaderTransportError) as caught:
                self.run_reader('slow')
        self.assertEqual('transport_failure', caught.exception.outcome)
        self.assertEqual('confirmed_empty', caught.exception.cleanup)
        self.assertFalse((self.root / 'gate-released').exists())
        self.assertFalse((self.root / 'verifier-handle').exists())
        # A real gate also rejects EOF without importing the fixture.
        result = subprocess.run(command('normal', self.root), input=b'', stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=10, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.root / 'gate-released').exists())

    def test_real_parent_death_closes_sole_job_handle_and_terminates_held_verifier(self):
        program = ('import sys,os;sys.path[:0]=' + repr([str(SCRIPTS), str(SCRIPTS.parent / 'sc')]) + ';'
            'import _b_route_reader_lifetime as l;'
            'l.run_reader(' + repr(command('slow', self.root)) + ',input=b"request",cwd=' + repr(str(self.root)) +
            ',env=dict(os.environ),timeout=60)')
        parent = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', program],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.environment,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 15
            while not (self.root / 'verifier-handle').is_file() and time.monotonic() < deadline:
                self.assertIsNone(parent.poll(), 'Owned lifetime supervisor exited before handle transfer')
                time.sleep(.01)
            handle = self.verifier_handle()
            self.assertEqual(258, self.api.WaitForSingleObject(handle, 0))
            parent.terminate()  # exact Popen-held supervisor handle only
            parent.communicate(timeout=10)
            self.assertEqual(0, self.api.WaitForSingleObject(handle, 5000))
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.communicate(timeout=10)

    def test_accounting_failure_never_manufactures_known_empty_or_accepts_result(self):
        with patch.object(lifetime.ReaderJob, 'active', side_effect=OSError('accounting unavailable')):
            with self.assertRaises(lifetime.ReaderTransportError) as caught:
                self.run_reader('normal')
        self.assertEqual('unconfirmed', caught.exception.cleanup)
        self.assertEqual('cleanup_unconfirmed', caught.exception.outcome)
        self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 5000))

    def test_writer_start_failure_keeps_gate_closed_and_closes_parent_owned_stdin(self):
        original = threading.Thread.start
        recorded = []
        popen = subprocess.Popen
        def launch(*args, **kwargs):
            process = popen(*args, **kwargs)
            recorded.append(process)
            return process
        def start(worker):
            if worker.name == 'b-route-reader-stdin':
                raise RuntimeError('cannot start owned writer')
            return original(worker)
        with patch.object(threading.Thread, 'start', start), patch.object(lifetime.subprocess, 'Popen', launch):
            with self.assertRaises(lifetime.ReaderTransportError):
                self.run_reader('normal')
        self.assertFalse((self.root / 'gate-released').exists())
        self.assertTrue(recorded[0].stdin.closed)
        self.assertIsNotNone(recorded[0].poll())

    def test_job_setup_failure_starts_no_unowned_child(self):
        with patch.object(lifetime, 'ReaderJob', side_effect=OSError('Job setup refused')), \
                patch.object(lifetime.subprocess, 'Popen') as launch:
            with self.assertRaises(lifetime.ReaderTransportError) as caught:
                self.run_reader('normal')
        launch.assert_not_called()
        self.assertEqual('unconfirmed', caught.exception.cleanup)
        self.assertFalse((self.root / 'gate-released').exists())

    def test_cancellation_keeps_original_exception_after_owned_cleanup(self):
        interruption = KeyboardInterrupt('synthetic owner cancellation')
        with patch.object(lifetime.ReaderJob, 'assign', side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_reader('normal')
        self.assertIs(interruption, caught.exception)
        self.assertIn('reader_owned_cleanup:confirmed_empty', caught.exception.__notes__)
        self.assertFalse((self.root / 'gate-released').exists())

    def test_job_termination_failure_is_unconfirmed_and_last_handle_remains_backstop(self):
        with patch.object(lifetime.ReaderJob, 'terminate', side_effect=OSError('termination unavailable')), \
                patch.object(lifetime, 'CLEANUP_TIMEOUT', .5):
            with self.assertRaises(lifetime.ReaderTransportError) as caught:
                self.run_reader('slow', timeout=2)
        self.assertEqual(('timeout', 'unconfirmed'), (caught.exception.outcome, caught.exception.cleanup))
        self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 5000))

    def test_close_and_pipe_stop_errors_never_turn_into_accepted_results(self):
        close = lifetime.ReaderJob.close
        stop = lifetime._stop_owned_pipe_workers
        def failed_close(job):
            close(job)
            raise OSError('Job close failure observation')
        def failed_stop(*args, **kwargs):
            stop(*args, **kwargs)
            raise RuntimeError('owned IO stop failure observation')
        for owner, name, replacement in ((lifetime.ReaderJob, 'close', failed_close),
                                          (lifetime, '_stop_owned_pipe_workers', failed_stop)):
            with self.subTest(failure=name), patch.object(owner, name, replacement):
                with self.assertRaises(lifetime.ReaderTransportError) as caught:
                    self.run_reader('normal')
                self.assertEqual('unconfirmed', caught.exception.cleanup)
                self.assertEqual('cleanup_unconfirmed', caught.exception.outcome)
                self.assertEqual(0, self.api.WaitForSingleObject(self.verifier_handle(), 0))


if __name__ == '__main__':
    unittest.main()
