"""Small offline scheduling and host-cleanup controls; no model or child launch."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _planning_skill_common as common
import _codex_app_server as app


class ManualWorker:
    def __init__(self, *, target=None, **kwargs):
        self.target = target
        self.alive = False
        self.joins = []
    def start(self):
        self.alive = True
    def is_alive(self):
        return self.alive
    def join(self, timeout):
        self.joins.append(timeout)


class HostCleanupTests(unittest.TestCase):
    def test_completed_read_survives_stop_before_next_read(self):
        reads, closes = [], []
        capture = None
        class Stream:
            encoding = None
            def read1(self, size):
                reads.append(size)
                if len(reads) != 1:
                    raise AssertionError("stop must prevent another read")
                capture.stopping.set()
                return b"partial\xff\r\n"
            def close(self):
                closes.append("owner")
        proc = SimpleNamespace(stdout=Stream())
        with patch.object(common.threading, "Thread", ManualWorker):
            capture = common._WindowsRunnerOutput(proc)
        capture._read()
        self.assertEqual(capture.output, b"partial\xff\r\n")
        self.assertEqual(capture.parts, [b"partial\xff\r\n"])
        self.assertEqual(reads, [65536])
        self.assertEqual(closes, ["owner"])
        self.assertTrue(capture.done.is_set())

    def test_cancel_missed_between_reads_is_repeated_until_exit(self):
        clock, cancels = [0.0], []
        stopping = threading.Event()
        worker = ManualWorker()
        worker.start()
        def join(timeout):
            worker.joins.append(timeout)
            clock[0] += timeout  # First cancellation found no pending IO.
        worker.join = join
        def cancel(workers):
            self.assertIs(workers[0], worker)
            self.assertTrue(stopping.is_set())
            cancels.append(len(cancels))
            if worker.joins:  # Worker entered IO after the first cancellation.
                worker.alive = False
        with patch.object(common, "_cancel_owned_pipe_io", cancel), patch.object(
                common.time, "monotonic", lambda: clock[0]):
            common._stop_owned_pipe_workers([worker], stopping)
        self.assertEqual(len(cancels), 2)
        self.assertFalse(worker.is_alive())
        self.assertLessEqual(clock[0], 0.5)

    def test_unacknowledged_stop_is_bounded_and_never_closes_stream(self):
        clock = [0.0]
        worker = ManualWorker()
        worker.start()
        def join(timeout):
            clock[0] += timeout
        worker.join = join
        with patch.object(common, "_cancel_owned_pipe_io"), patch.object(
                common.time, "monotonic", lambda: clock[0]):
            with self.assertRaisesRegex(RuntimeError, "did not acknowledge stop"):
                common._stop_owned_pipe_workers([worker], threading.Event())
        self.assertLessEqual(clock[0], 0.500001)

    def test_cancellation_failure_still_attempts_exit_handshake(self):
        worker = ManualWorker()
        worker.start()
        def join(timeout):
            worker.joins.append(timeout)
            worker.alive = False
        worker.join = join
        with patch.object(common, "_cancel_owned_pipe_io", side_effect=OSError("cancel-control")):
            with self.assertRaisesRegex(RuntimeError, "cancel-control"):
                common._stop_owned_pipe_workers([worker], threading.Event())
        self.assertEqual(len(worker.joins), 1)
        self.assertFalse(worker.is_alive())

    def test_primary_exception_and_raw_journal_survive_multiple_cleanup_failures(self):
        calls = []
        class BadStream:
            closed = False
            def __init__(self, name):
                self.name = name
            def close(self):
                calls.append(self.name)
                raise OSError(self.name + "-control")
        proc = SimpleNamespace(poll=lambda: None, wait=lambda timeout: 0,
            **{key: BadStream(key) for key in ("stdin", "stdout", "stderr")})
        primary = TimeoutError("original-timeout-control")
        def terminate(proc):
            calls.append("terminate")
            raise OSError("terminate-control")
        def stop(workers, stopping):
            calls.append("pipe_stop")
            raise RuntimeError("stop-control")
        journal = BadStream("journal")
        with tempfile.TemporaryDirectory(prefix="hc-") as name:
            path = Path(name) / "p.jsonl"
            raw = b'{"original":"protocol"}\n'
            path.write_bytes(raw)
            try:
                try:
                    raise primary
                finally:
                    app._cleanup_request(proc, [], threading.Event(), journal, path, ["actual stderr\n"],
                        primary_error=sys.exc_info()[1], terminate=terminate, stop_workers=stop)
            except TimeoutError as caught:
                self.assertIs(caught, primary)
            else:
                self.fail("original error was lost")
            self.assertEqual(calls, ["terminate", "pipe_stop", "stdin", "stdout", "stderr", "journal"])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.with_suffix(".stderr.txt").read_text(encoding="utf-8"), "actual stderr\n")
            diagnostic = json.loads(path.with_suffix(".host-cleanup.json").read_text(encoding="utf-8"))
            self.assertEqual(diagnostic["source"], "host_cleanup")
            self.assertFalse(diagnostic["model_success"])
            self.assertEqual(diagnostic["primary_error"]["type"], "TimeoutError")
            self.assertEqual(len(diagnostic["failures"]), 6)
            self.assertTrue(primary.__notes__[0].startswith("host_cleanup: "))

    def test_live_owned_worker_prevents_coordinator_stream_close(self):
        closed = []
        worker = ManualWorker()
        worker.start()
        stream = SimpleNamespace(closed=False, close=lambda: closed.append("unsafe"))
        proc = SimpleNamespace(poll=lambda: 0, wait=lambda timeout: 0, stdin=stream, stdout=stream, stderr=stream)
        primary = ValueError("original-protocol-control")
        app._cleanup_request(proc, [worker], threading.Event(), None, None, [], primary_error=primary,
            terminate=lambda proc: self.fail("already exited"), stop_workers=lambda *args: None)
        self.assertEqual(closed, [])
        self.assertIn("OwnedWorkerStillAlive", primary.__notes__[0])

    def test_successful_protocol_with_cleanup_failure_still_fails_host(self):
        stream = SimpleNamespace(closed=True)
        proc = SimpleNamespace(poll=lambda: 0, wait=lambda timeout: 0, stdin=stream, stdout=stream, stderr=stream)
        with self.assertRaisesRegex(RuntimeError, "host cleanup failed") as caught:
            app._cleanup_request(proc, [], threading.Event(), None, None, [], primary_error=None,
                terminate=lambda proc: None, stop_workers=lambda *args: (_ for _ in ()).throw(OSError("host-control")))
        self.assertIn("host_cleanup", caught.exception.__notes__[0])

    def test_stderr_and_sidecar_failures_preserve_primary_and_attempt_journal(self):
        closed = []
        stream = SimpleNamespace(closed=True)
        proc = SimpleNamespace(poll=lambda: 0, wait=lambda timeout: 0, stdin=stream, stdout=stream, stderr=stream)
        journal = SimpleNamespace(close=lambda: closed.append("journal"))
        primary = ValueError("primary-control")
        with tempfile.TemporaryDirectory(prefix="hc-") as name:
            path = Path(name) / "p.jsonl"
            # Existing sidecar is immutable; failure is itself attached to primary.
            path.with_suffix(".host-cleanup.json").write_bytes(b"previous-host-control")
            with patch.object(Path, "write_text", side_effect=OSError("stderr-save-control")):
                app._cleanup_request(proc, [], threading.Event(), journal, path, ["child"],
                    primary_error=primary, terminate=lambda proc: None, stop_workers=lambda *args: None)
            self.assertEqual(path.with_suffix(".host-cleanup.json").read_bytes(), b"previous-host-control")
        self.assertEqual(closed, ["journal"])
        self.assertIn("stderr_save", primary.__notes__[0])
        self.assertIn("host_diagnostic_save", primary.__notes__[0])


if __name__ == "__main__":
    unittest.main()
