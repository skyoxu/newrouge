"""Real owned-FS recovery preparation/CAS/locks, explicitly synthetic eligibility.

Only original native proof, literal Root controls and transition construction
are fake boundaries. The real prepare, retained-shape checks, snapshots, native
coordinator byte lock and durable xb/fsync/replace publication execute. No native
admission, model, synthesis dispatch, subprocess, actual Nx or Root controller.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_mvg_synthesis_recovery as recovery
import _b_route_execution_transition as transition
from _mvg_capability_checkpoint import coordinator_lock
from test_b_route_mvg_synthesis_recovery import make_prefix

OWNED_TEMP = Path("C:/Windows/TEMP") if os.name == "nt" else Path("/tmp")


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


class RecoveryPrepareFSTests(unittest.TestCase):
    def setUp(self):
        self.allocated_name = "mp19_" + uuid.uuid4().hex[:8]
        self.root = OWNED_TEMP / self.allocated_name
        self.root.mkdir(exist_ok=False)
        self.addCleanup(self.cleanup_owned)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.process = self.stack.enter_context(patch.object(subprocess, "Popen", side_effect=AssertionError("no native/model subprocess")))
        self.network = self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("no network")))
        self.run = self.root / recovery.RUN_REF
        self.run.mkdir(parents=True)
        self.append_path = self.run / recovery.WORKSPACE / "capability-append/append-ledger.json"
        self.home = self.run / "recovery" / recovery.NAMESPACE
        self.state, self.append = make_prefix()
        self.state["b_route_execution_transition"] = {"schema_version": "synthetic.original-source-epoch.v1",
            "transition_digest": recovery.codec.canonical_digest({"synthetic": "original source identity"})}
        self.state["b_route_execution_history"] = {"synthetic-old-history": {"retained": "original bytes"}}
        self.append.update(accepted={"synthetic": "original readonly seed"}, binding="original-synthetic-input-binding")
        self.drafts = [
            {"stage": "batch", "ordinal": 1, "content": {"synthetic": "exact retained batch"}},
            {"stage": "synthesis", "ordinal": 2, "content": {"synthetic": "exact rejected original synthesis"}}]
        self.bindings = [{"synthetic_original_binding": 6}, {"synthetic_original_binding": 7}]
        self.rejection = {"json_pointer": recovery.REJECTION_POINTER, "source_path": "docs/synthetic.md",
            "observed_raw_digest": "sha256:short", "expected_raw_digest": "sha256:" + "b" * 64,
            "structural_observations": [{"entity_id": "profile-to-harness", "formal_business_finding": False}]}
        self.next_transition = {"schema_version": recovery.MVG_EPOCH_SCHEMA,
            "transition_digest": recovery.codec.canonical_digest({"synthetic": "new source identity, no admission"})}
        self.observation = {"schema_version": recovery.SCHEMA + ".root-terminal-observation",
            "synthetic_eligibility": "not an actual OS exit or Root receipt", "released": 0}
        self.old_run_raw, self.old_append_raw = raw(self.state), raw(self.append)
        self.write(self.run / "run.json", self.old_run_raw)
        self.write(self.append_path, self.old_append_raw)
        self.write(self.run / "model-execution.json", raw({"synthetic_original_projection": "all seven calls retained"}))
        self.write(self.run / "candidates/candidate-2/lineage-execution.json", raw({"synthetic_original_projection": "two calls retained"}))
        for prefix in recovery._SEALED:
            (self.run / prefix).mkdir(parents=True, exist_ok=True)
        self.c1_path = self.run / "candidates/candidate-1/original-admission.json"
        self.write(self.c1_path, raw({"synthetic_original_admission": "candidate-1", "paid": 5}))
        for number, (draft, binding) in enumerate(zip(self.drafts, self.bindings), 1):
            base = self.run / recovery.WORKSPACE / f"capability-append/c{number}"
            self.write(base / "canonical-draft.json", raw(draft))
            self.write(base / "execution-binding.json", raw(binding))
        self.write(self.run / "analysis-input/original-input.json", raw({"synthetic": "preserve original complete input"}))
        # Use the actual owner to create its original one-byte lock file.
        with coordinator_lock(self.run):
            pass
        self.original_files = self.file_bytes()
        self.control_calls = 0
        self.control_lock = threading.Lock()
        self.verify_hook = None
        self.control_hook = None
        self.proof = self.stack.enter_context(patch.object(recovery, "_verify_original", side_effect=self.fake_original_proof))
        self.controls = self.stack.enter_context(patch.object(recovery, "_root_controls", side_effect=self.fake_root_controls))
        self.epoch = self.stack.enter_context(patch.object(transition, "build_mvg_synthesis_transition", return_value=deepcopy(self.next_transition)))
        # These constants name only these owned synthetic preimages, not actual m4.
        self.stack.enter_context(patch.object(recovery, "ORIGINAL_RUN_DIGEST", recovery.codec.raw_digest(self.old_run_raw)))
        self.stack.enter_context(patch.object(recovery, "ORIGINAL_APPEND_DIGEST", recovery.codec.raw_digest(self.old_append_raw)))
        self.arguments = {"original_source_root": self.root / "synthetic-original-source", "current_commit": "e" * 40,
            "prior_source_root": self.root / "synthetic-prior-source", "prior_commit": recovery.PRIOR_COMMIT,
            "expected_run_digest": recovery.codec.raw_digest(self.old_run_raw),
            "expected_append_digest": recovery.codec.raw_digest(self.old_append_raw), "root_terminal_observation": deepcopy(self.observation)}

    def cleanup_owned(self):
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None)
        failures = getattr(result, "failures", []) + getattr(result, "errors", [])
        failed = getattr(outcome, "success", True) is False or any(
            case is self or getattr(case, "test_case", None) is self for case, _ in failures)
        if failed:
            print("Retained failed owned recovery fixture: " + str(self.root))
            return
        target = self.root.resolve(strict=True)
        info = self.root.lstat()
        if target.parent != OWNED_TEMP.resolve(strict=True) or target.name != self.allocated_name or self.root.name != self.allocated_name:
            raise AssertionError("Cleanup escaped exact allocated TEMP child")
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AssertionError("Cleanup root is not the original plain directory")
        shutil.rmtree(target)

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def file_bytes(self):
        return {p.relative_to(self.run).as_posix(): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}

    def fake_original_proof(self, root, run, state, append):
        """Explicit upstream eligibility seam; never native/protocol acceptance."""
        self.assertEqual(Path(root), self.root)
        self.assertEqual(Path(run), self.run)
        self.assertEqual(state, self.state)
        self.assertEqual(append, self.append)
        if self.verify_hook is not None:
            self.verify_hook()
        return ({"synthetic": "original frozen proof placeholder"}, deepcopy(self.drafts),
                deepcopy(self.bindings), deepcopy(self.rejection))

    def fake_root_controls(self, root, observation=None):
        self.assertEqual(Path(root), self.root)
        if observation is not None:
            self.assertEqual(observation, self.observation)
        with self.control_lock:
            self.control_calls += 1
            ordinal = self.control_calls
        if self.control_hook is not None:
            self.control_hook(ordinal)
        return deepcopy(self.observation)

    def prepare(self):
        return recovery.prepare(self.root, self.run, **self.arguments)

    def assert_retained_accounting(self, state, append):
        self.assertEqual(state["capability_selection"]["calls"], self.state["capability_selection"]["calls"])
        self.assertEqual(state["capability_selection"]["total_invocations"], 7)
        self.assertEqual(state["capability_selection"]["lineage_invocations"], self.state["capability_selection"]["lineage_invocations"])
        self.assertEqual(state["active_elapsed_seconds"], self.state["active_elapsed_seconds"])
        self.assertEqual(state["b_route_campaign_funding"], self.state["b_route_campaign_funding"])
        self.assertEqual(state["b_route_campaign_funding"]["released"], 0)
        self.assertEqual(state["capability_selection"]["current"]["admissions"]["candidate-1"],
                         self.state["capability_selection"]["current"]["admissions"]["candidate-1"])
        self.assertEqual(append["total_invocations"], 2)
        self.assertEqual(append["calls"], self.append["calls"])
        self.assertEqual(append["current"], self.append["current"])
        self.assertEqual((self.run / "candidates/candidate-1/original-admission.json").read_bytes(),
                         self.original_files["candidates/candidate-1/original-admission.json"])
        self.assertFalse((self.home / "synthesis-claim.json").exists())
        self.process.assert_not_called()
        self.network.assert_not_called()

    def assert_original_archives(self):
        record_raw = (self.home / "record.json").read_bytes()
        record = recovery.codec.strict_json_loads(record_raw)
        self.assertEqual(recovery.image_bytes(record["previous_run"]), self.old_run_raw)
        self.assertEqual(recovery.image_bytes(record["previous_append"]), self.old_append_raw)
        self.assertEqual(record["retained_global_calls"], 7)
        self.assertEqual(record["retained_local_calls"], 2)
        self.assertEqual(record["next_global_call"], 8)
        self.assertEqual(record["next_local_call"], 3)
        self.assertEqual(record["maximum_new_synthesis_attempts"], 1)
        self.assertEqual(record["released"], 0)
        self.assertEqual(record["batch_draft_ref"], recovery.WORKSPACE + "/capability-append/c1/canonical-draft.json")
        self.assertEqual(record["batch_draft_digest"], recovery.codec.canonical_digest(self.drafts[0]))
        self.assertEqual(record["rejected_synthesis_draft_digest"], recovery.codec.canonical_digest(self.drafts[1]))
        claim = recovery.codec.strict_json_loads((self.home / "claim.json").read_bytes())
        self.assertEqual(claim, {"schema_version": recovery.SCHEMA, "record_digest": recovery.codec.raw_digest(record_raw),
            "retained_global_calls": 7, "retained_local_calls": 2})
        for name, image in record["mutable_preimages"].items():
            self.assertEqual(recovery.image_bytes(image), self.original_files[name])
        for name, digest in record["immutable"]["files"].items():
            self.assertEqual(digest, recovery.codec.raw_digest(self.original_files[name]))
            self.assertEqual((self.run / name).read_bytes(), self.original_files[name])
        return record

    def test_real_fs_publication_keeps_seven_two_calls_c1_and_permanent_metadata(self):
        result = self.prepare()
        self.assertEqual(result["status"], "mvg-synthesis-recovery-prepared")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["retained_logical_calls"], 7)
        self.assertEqual(result["next_dispatch"], "m4:dispatch:8")
        self.assertEqual(result["released"], 0)
        state = recovery.read(self.run, "run.json")
        append = recovery.read(self.append_path.parent, self.append_path.name)
        self.assert_retained_accounting(state, append)
        record = self.assert_original_archives()
        self.assertEqual(set(p.name for p in self.home.iterdir()), {"claim.json", "record.json", "committed.json"})
        self.assertEqual(recovery.read(self.home, "committed.json"), {"record_digest": result["record"]["record_digest"],
            "transition_digest": self.next_transition["transition_digest"]})
        self.assertEqual(record["history"][self.state["b_route_execution_transition"]["transition_digest"]], self.state["b_route_execution_transition"])
        self.assertEqual(state[recovery.REFERENCE], result["record"])
        self.assertEqual(state["b_route_execution_transition"], self.next_transition)
        self.assertEqual(append["execution_errors"][-1]["original_errors"], self.append["errors"])
        self.assertEqual(append["errors"], [])
        self.assertEqual(self.proof.call_count, 1)
        self.assertEqual(self.epoch.call_count, 1)

    def test_two_threads_real_native_lock_allow_only_one_publisher(self):
        entered, proceed, loser_finished = threading.Event(), threading.Event(), threading.Event()
        start = threading.Barrier(3)
        results, errors = [], []
        mutex = threading.Lock()
        def hold_qualification():
            entered.set()
            if not proceed.wait(8):
                raise AssertionError("Test failed to release original locked verification")
        self.verify_hook = hold_qualification
        def worker():
            try:
                start.wait(timeout=8)
                value = self.prepare()
                with mutex: results.append(value)
            except BaseException as error:
                with mutex: errors.append(error)
                loser_finished.set()
        workers = [threading.Thread(target=worker, name="owned-prepare-" + str(i), daemon=True) for i in (1, 2)]
        for thread in workers: thread.start()
        try:
            start.wait(timeout=8)
            self.assertTrue(entered.wait(8), "No preparer acquired the genuine first coordinator lock")
            self.assertTrue(loser_finished.wait(8), "Second preparer was not excluded by the genuine OS lock")
        finally:
            proceed.set()
            for thread in workers: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in workers), "Owned worker still running")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertIn("capability_coordinator_busy", str(errors[0]))
        self.assertEqual(self.proof.call_count, 1)
        self.assertEqual(self.epoch.call_count, 1)
        self.assert_original_archives()
        self.assert_retained_accounting(recovery.read(self.run, "run.json"), recovery.read(self.append_path.parent, self.append_path.name))
        published = self.file_bytes()
        with self.assertRaisesRegex(ValueError, "recovery_namespace_occupied"):
            self.prepare()
        self.assertEqual(self.file_bytes(), published)
        self.assertEqual(self.proof.call_count, 1)

    def test_partial_publication_retains_claim_record_preimages_and_refuses_reentry(self):
        original_durable = recovery._durable
        for boundary in ("run", "committed"):
            with self.subTest(boundary=boundary):
                # Independent owned subfixture for each fault, never remove a claim.
                original_run, original_append, original_home = self.run, self.append_path, self.home
                if boundary == "committed":
                    # A second complete fixture uses another project child; the
                    # first partial transaction stays untouched until cleanup.
                    self.run = self.root / "second" / recovery.RUN_REF
                    self.run.mkdir(parents=True)
                    for name, data in self.original_files.items():
                        self.write(self.run / name, data)
                    self.append_path = self.run / recovery.WORKSPACE / "capability-append/append-ledger.json"
                    self.home = self.run / "recovery" / recovery.NAMESPACE
                project = self.root if boundary == "run" else self.root / "second"
                attempts = []
                def fault(path, value, *, exclusive=False):
                    attempts.append(Path(path))
                    if (boundary == "run" and Path(path) == self.run / "run.json") or \
                       (boundary == "committed" and Path(path) == self.home / "committed.json"):
                        raise OSError("injected stop before " + boundary + " durable write")
                    return original_durable(path, value, exclusive=exclusive)
                # Adapt only the explicit upstream root qualification seam to
                # the second isolated project, keeping all owner FS paths real.
                def controls(root, observation=None):
                    self.assertEqual(Path(root), project)
                    return deepcopy(self.observation)
                def proof(root, run, state, append):
                    self.assertEqual(Path(root), project)
                    self.assertEqual(state, self.state); self.assertEqual(append, self.append)
                    return ({"synthetic": "proof boundary"}, deepcopy(self.drafts), deepcopy(self.bindings), deepcopy(self.rejection))
                try:
                    with patch.object(recovery, "_durable", side_effect=fault), \
                         patch.object(recovery, "_root_controls", side_effect=controls), \
                         patch.object(recovery, "_verify_original", side_effect=proof) as verifier:
                        with self.assertRaisesRegex(OSError, "injected stop before " + boundary):
                            recovery.prepare(project, self.run, **self.arguments)
                        self.assertEqual(set(p.name for p in self.home.iterdir()), {"claim.json", "record.json"})
                        self.assert_original_archives()
                        state = recovery.read(self.run, "run.json")
                        append = recovery.read(self.append_path.parent, self.append_path.name)
                        self.assert_retained_accounting(state, append)
                        self.assertEqual(append["status"], "generating")
                        if boundary == "run":
                            self.assertEqual((self.run / "run.json").read_bytes(), self.old_run_raw)
                        else:
                            self.assertIn(recovery.REFERENCE, state)
                        partial = self.file_bytes(); count = len(attempts)
                        with self.assertRaisesRegex(ValueError, "recovery_namespace_occupied"):
                            recovery.prepare(project, self.run, **self.arguments)
                        self.assertEqual(self.file_bytes(), partial)
                        self.assertEqual(len(attempts), count)
                        self.assertEqual(verifier.call_count, 1)
                finally:
                    self.run, self.append_path, self.home = original_run, original_append, original_home

    def test_validation_and_closing_cas_drift_refuse_before_new_namespace(self):
        for boundary in ("verification", "closing"):
            with self.subTest(boundary=boundary):
                self.write(self.run / "run.json", self.old_run_raw)
                self.write(self.append_path, self.old_append_raw)
                self.control_calls = 0
                self.verify_hook = None; self.control_hook = None
                if boundary == "verification":
                    self.verify_hook = lambda: self.append_path.write_bytes(self.old_append_raw + b" ")
                    expected = "original_changed_during_verification"
                else:
                    def closing(ordinal):
                        if ordinal == 2:
                            (self.run / "run.json").write_bytes(self.old_run_raw + b" ")
                    self.control_hook = closing
                    expected = "preparation_closing_changed"
                with patch.object(recovery, "_durable", wraps=recovery._durable) as durable:
                    with self.assertRaisesRegex(ValueError, expected):
                        self.prepare()
                    durable.assert_not_called()
                self.assertFalse(self.home.exists())
                self.assertFalse((self.run / "recovery").exists())
                self.assert_retained_accounting(recovery.read(self.run, "run.json"), recovery.read(self.append_path.parent, self.append_path.name))
                changed = self.append_path if boundary == "verification" else self.run / "run.json"
                self.assertEqual(changed.read_bytes(), (self.old_append_raw if boundary == "verification" else self.old_run_raw) + b" ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
