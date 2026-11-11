"""Focused host failure controls; synthetic processes only, never model calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _planning_skill_common as common
import _mvg_capability_worker as worker
import _mvg_worker_lifetime as lifetime


class HostCleanupTests(unittest.TestCase):
    def run_common(self, capture, proc, *, log_error=None):
        with tempfile.TemporaryDirectory(prefix="hc3-") as directory:
            root = Path(directory)
            with patch.object(common, "os", SimpleNamespace(name="nt")), patch.object(
                    common.subprocess, "Popen", return_value=proc), patch.object(
                    common, "_WindowsRunnerOutput", return_value=capture), patch.object(
                    common, "_terminate_process_tree"), patch.object(
                    common, "atomic_json", side_effect=log_error):
                return common.run_isolated_model(root / "runner.exe", workspace=root,
                    prompt_path=root / "prompt.txt", output_path=root / "output.json",
                    timeout_sec=1, wall_timeout_sec=1, execution_log=root / "host.json")

    def test_timeout_log_failure_keeps_timeout_cause_partial_bytes_and_cleanup_notes(self):
        primary = subprocess.TimeoutExpired(["owned-runner"], 1, output=b"prior")
        capture = SimpleNamespace(parts=[b"partial\xff"],
            communicate=lambda timeout: (_ for _ in ()).throw(primary),
            cancel=lambda: (_ for _ in ()).throw(OSError("cancel-control")))
        proc = SimpleNamespace(returncode=None,
            wait=lambda timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired("reap", timeout)))
        with self.assertRaises(TimeoutError) as caught:
            self.run_common(capture, proc, log_error=OSError("log-control"))
        self.assertIs(caught.exception.__cause__, primary)
        self.assertIn("partial", str(caught.exception))
        notes = "\n".join(caught.exception.__notes__)
        self.assertIn("execution_log", notes)
        self.assertIn("cancel-control", notes)
        self.assertIn("reap", notes)

    def test_interrupt_log_failure_preserves_original_exception_object(self):
        primary = KeyboardInterrupt("original-interrupt")
        capture = SimpleNamespace(parts=[],
            communicate=lambda timeout: (_ for _ in ()).throw(primary), cancel=lambda: b"captured")
        proc = SimpleNamespace(returncode=-1, wait=lambda timeout: -1)
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_common(capture, proc, log_error=OSError("log-control"))
        self.assertIs(caught.exception, primary)
        self.assertIn("execution_log", primary.__notes__[0])

    def test_launch_log_failure_preserves_launch_error_and_zero_dispatch(self):
        primary = OSError("launch-control")
        records = []
        def failed_log(path, value):
            records.append(value)
            raise OSError("log-control")
        with tempfile.TemporaryDirectory(prefix="hc3-") as directory:
            root = Path(directory)
            with patch.object(common.subprocess, "Popen", side_effect=primary), patch.object(
                    common, "atomic_json", failed_log), self.assertRaises(OSError) as caught:
                common.run_isolated_model(root / "runner.exe", workspace=root,
                    prompt_path=root / "prompt.txt", output_path=root / "output.json",
                    timeout_sec=1, execution_log=root / "host.json")
        self.assertIs(caught.exception, primary)
        self.assertEqual(records[0]["runner_dispatch_count"], 0)
        self.assertIn("host_execution_log_failed", primary.__notes__[0])

    def test_success_log_failure_still_fails(self):
        capture = SimpleNamespace(communicate=lambda timeout: (b"{}\n", None))
        proc = SimpleNamespace(returncode=0)
        with self.assertRaisesRegex(OSError, "log-control"):
            self.run_common(capture, proc, log_error=OSError("log-control"))

    def test_worker_cleanup_attempts_every_owned_stage_and_preserves_primary(self):
        calls, saved = [], []
        def fail(stage):
            calls.append(stage)
            raise OSError(stage + "-control")
        proc = SimpleNamespace(pid=123, stdin=SimpleNamespace(close=lambda: fail("stdin")),
            poll=lambda: None, kill=lambda: fail("kill"), wait=lambda timeout: fail("wait"))
        job = SimpleNamespace(close=lambda: fail("job"))
        primary = ValueError("original-machine-control")
        with patch.object(worker, "os", SimpleNamespace(name="nt")), patch.object(
                worker.subprocess, "run", side_effect=lambda *args, **kwargs: fail("taskkill")), patch.object(
                worker, "atomic_json", side_effect=lambda path, value: saved.append(value)):
            worker._cleanup_candidate(proc, job, Path("owned-case"), 0, primary_error=primary)
        self.assertEqual(calls, ["stdin", "taskkill", "kill", "job", "wait"])
        self.assertEqual(saved[0]["pid"], proc.pid)
        self.assertEqual(saved[0]["primary_error"]["detail"], str(primary))
        diagnostic = json.loads(primary.__notes__[0].split(": ", 1)[1])
        self.assertEqual([row["stage"] for row in diagnostic["failures"]],
            ["stdin_close", "taskkill", "kill", "job_close", "wait"])

    def test_worker_cleanup_without_primary_fails_and_diagnostic_failure_is_visible(self):
        proc = SimpleNamespace(pid=123, stdin=SimpleNamespace(close=lambda: None),
            poll=lambda: 0, wait=lambda timeout: 0)
        job = SimpleNamespace(close=lambda: (_ for _ in ()).throw(OSError("job-control")))
        with patch.object(worker, "atomic_json", side_effect=OSError("log-control")), self.assertRaisesRegex(
                RuntimeError, "candidate_worker_cleanup_failed") as caught:
            worker._cleanup_candidate(proc, job, Path("owned-case"), 0, primary_error=None)
        self.assertIn("job_close", caught.exception.__notes__[0])
        self.assertIn("diagnostic_save", caught.exception.__notes__[0])

    def test_worker_cleanup_deadline_is_shared_across_taskkill_and_reap(self):
        clock, waits, timeouts = [0.0], [], []
        proc = SimpleNamespace(pid=123, stdin=SimpleNamespace(close=lambda: None),
            poll=lambda: None, kill=lambda: None, wait=lambda timeout: waits.append(timeout))
        def taskkill(*args, **kwargs):
            timeouts.append(kwargs["timeout"])
            clock[0] = 10.0
            return SimpleNamespace(returncode=0)
        with patch.object(worker, "os", SimpleNamespace(name="nt")), patch.object(
                worker.time, "monotonic", side_effect=lambda: clock[0]), patch.object(
                worker.subprocess, "run", taskkill):
            worker._cleanup_candidate(proc, None, Path("owned-case"), 0, primary_error=None)
        self.assertEqual(timeouts, [10.0])
        self.assertEqual(waits, [0])

    def test_lifetime_close_failure_preserves_primary_and_success_path_still_fails(self):
        primary = ValueError("original-worker-control")
        job = SimpleNamespace(close=lambda: (_ for _ in ()).throw(OSError("job-control")))
        with patch.object(lifetime, "os", SimpleNamespace(name="nt")), patch.object(
                lifetime, "WindowsWorkerJob", return_value=job):
            with self.assertRaises(ValueError) as caught:
                with lifetime.worker_lifetime():
                    raise primary
            self.assertIs(caught.exception, primary)
            self.assertIn("worker_job_cleanup_failed", primary.__notes__[0])
            with self.assertRaisesRegex(OSError, "job-control"):
                with lifetime.worker_lifetime():
                    pass

    def test_job_close_failure_retains_owned_handle_for_retry(self):
        job = object.__new__(lifetime.WindowsWorkerJob)
        job.handle = 123
        job.api = SimpleNamespace(CloseHandle=lambda handle: False)
        with patch.object(lifetime.ctypes, "get_last_error", return_value=5, create=True), patch.object(
                lifetime.ctypes, "WinError", side_effect=lambda code: OSError("close-control:" + str(code)), create=True):
            with self.assertRaisesRegex(OSError, "close-control:5"):
                job.close()
        self.assertEqual(job.handle, 123)
        job.api.CloseHandle = lambda handle: True
        job.close()
        self.assertIsNone(job.handle)

    def test_job_setup_failure_is_not_replaced_by_close_failure(self):
        api = SimpleNamespace(CreateJobObjectW=lambda *args: 123,
            SetInformationJobObject=lambda *args: False,
            AssignProcessToJobObject=lambda *args: True, CloseHandle=lambda *args: False)
        with patch.object(lifetime.ctypes, "WinDLL", return_value=api, create=True), patch.object(
                lifetime.ctypes, "get_last_error", side_effect=[5, 6], create=True), patch.object(
                lifetime.ctypes, "WinError", side_effect=lambda code: OSError("job-control:" + str(code)), create=True):
            with self.assertRaisesRegex(OSError, "job-control:5") as caught:
                lifetime.WindowsWorkerJob()
        self.assertIn("job-control:6", caught.exception.__notes__[0])


if __name__ == "__main__":
    unittest.main()
