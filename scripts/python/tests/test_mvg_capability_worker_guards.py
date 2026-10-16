"""Narrow coordinator boundary tests without invoking a model or full planner."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_worker as worker
from _mvg_capability_checkpoint import coordinator_lock
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json


class WorkerBoundaryTests(unittest.TestCase):
    @unittest.skipUnless(worker.os.name == "nt", "Windows Job Object assignment contract")
    def test_lifetime_assignment_failure_never_releases_dispatch_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = Mock(pid=48293)
            process.poll.return_value = None
            with patch("_mvg_worker_lifetime.WindowsWorkerJob") as job, \
                 patch.object(worker.subprocess, "Popen", return_value=process), \
                 patch.object(worker.subprocess, "run"):
                job.return_value.assign.side_effect = OSError("Fixture Job Object assignment denied")
                with self.assertRaisesRegex(OSError, "assignment denied"):
                    worker.run_candidate(root / "lifecycle", {"workspace": str(root)},
                        reserve=Mock(), cost_budget=Mock(), outcome=Mock())
                process.stdin.write.assert_not_called()
                job.return_value.close.assert_called_once()
                process.wait.assert_called_once_with(timeout=10)

    def test_tampered_child_artifact_is_rejected_before_parent_admission_or_rank(self):
        for target in ("proposal.json", "admission-review.json", "admission-execution.json"):
            with self.subTest(artifact=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace = root / "candidate"
                workspace.mkdir()
                state_path = root / "run.json"
                atomic_json(state_path, {"selected": ["previous-commit"], "accepted_sha256": "unchanged"})
                committed_bytes = state_path.read_bytes()
                data = {"workspace": str(workspace)}
                process = Mock(pid=48291, returncode=0)
                process.poll.return_value = 0

                def finished_child(*args, **kwargs):
                    job_dir = root / "lifecycle"
                    artifacts = {}
                    for name in ("proposal.json", "admission-review.json", "admission-execution.json"):
                        atomic_json(workspace / name, {"original": name})
                        artifacts[name] = file_sha(workspace / name)
                    atomic_json(job_dir / "result.json", {"schema_version": worker.SCHEMA,
                        "identity": canonical_sha(data), "pid": process.pid, "status": "admitted",
                        "total_invocations": 2, "artifacts": artifacts})
                    # Child reported its original hashes, then the disk artifact
                    # changed before the parent crossed its trust boundary.
                    atomic_json(workspace / target, {"tampered": True})
                    return process

                with patch("_mvg_worker_lifetime.WindowsWorkerJob"), \
                     patch.object(worker.subprocess, "Popen", side_effect=finished_child), \
                     patch("_mvg_capability_selection.candidate_artifacts") as admission, \
                     patch("plan_mvg.run_isolated_model") as rank:
                    with self.assertRaisesRegex(ValueError, "candidate_worker_artifacts_changed"):
                        result = worker.run_candidate(root / "lifecycle", data,
                            reserve=Mock(), cost_budget=Mock(), outcome=Mock())
                        admission(result)
                        rank()
                    admission.assert_not_called()
                    rank.assert_not_called()
                self.assertEqual(committed_bytes, state_path.read_bytes())
                self.assertTrue((root / "lifecycle/process.json").is_file())
                self.assertTrue((root / "lifecycle/worker.log").is_file())

    def test_interrupted_parent_terminates_windows_child_tree_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "candidate"
            workspace.mkdir()
            process = Mock(pid=48292)
            # The first poll interrupts the coordinator; finally observes the
            # still-active child and executes the actual cleanup branch.
            process.poll.side_effect = [KeyboardInterrupt("Fixture parent interrupted"), None]
            with patch("_mvg_worker_lifetime.WindowsWorkerJob"), \
                 patch.object(worker.subprocess, "Popen", return_value=process), \
                 patch.object(worker.subprocess, "run") as terminate:
                with self.assertRaises(KeyboardInterrupt), coordinator_lock(root):
                    worker.run_candidate(root / "lifecycle", {"workspace": str(workspace)},
                        reserve=Mock(), cost_budget=Mock(), outcome=Mock())
                if worker.os.name == "nt":
                    terminate.assert_called_once()
                    self.assertEqual(["taskkill", "/PID", "48292", "/T", "/F"], terminate.call_args.args[0])
                    self.assertFalse(terminate.call_args.kwargs["check"])
                else:
                    process.kill.assert_called_once()
                process.wait.assert_called_once_with(timeout=10)
            # OS byte lock and worker log descriptor must both be released.
            with coordinator_lock(root):
                self.assertEqual(48292, load_json(root / "lifecycle/process.json")["pid"])
            with (root / "lifecycle/worker.log").open("a", encoding="utf-8") as log:
                log.write("Cleanup complete\n")


if __name__ == "__main__":
    unittest.main()
