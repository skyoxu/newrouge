"""Offline recovery contracts; assembly seams never represent real admission."""
from copy import deepcopy
import contextlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import b_route_worker_recovery as recovery
import _b_route_planning_runtime as runtime
import _mvg_capability_selection as selection
from _planning_skill_common import atomic_json, canonical_sha, file_sha
import test_b_route_planning_runtime as existing_fixture


class WorkerRecoveryTests(unittest.TestCase):
    setUp = existing_fixture.RuntimeTests.setUp
    create = existing_fixture.RuntimeTests.create
    bound_call = existing_fixture.ReviewFixTests.bound_call

    def make_run(self, *, unknown=True, complete=False):
        run, state = self.create(run_id="recovery")
        scope = runtime.scopes(state, run / "analysis-input")[0]
        seed = runtime.seed(state, run / "analysis-input")
        state["runner_configuration"] = {"offline_assembly_only": True}
        workspace = selection.scope_workspace(run, "candidate-1", 0, 1)
        sandbox = workspace / "capability-append/c1/llm-sandbox/attempt-1/r"
        sandbox.mkdir(parents=True)
        (sandbox / "prompt.txt").write_text("offline fixture", encoding="utf-8")
        request = {"workspace": sandbox.relative_to(run).as_posix(), "output_path": (sandbox / "r.json").relative_to(run).as_posix(),
            "input_files": {"prompt.txt": file_sha(sandbox / "prompt.txt")}}
        request["request_sha256"] = canonical_sha(request)
        row = {"number": 1, "run_id": state["run_id"], "reservation_id": state["run_id"] + ":dispatch:1",
            "status": "reserved", "phase": "generate", "candidate": "candidate-1", "generation": 1,
            "execution": 1, "lineage": "candidate-1-r1", "capability_id": scope["capability_id"],
            "request_identity": request, "reserved_at_utc": "offline-fixture"}
        if not unknown:
            row["outcome"] = {"status": "completed", "offline_assembly_only": True}
        state["capability_selection"] = {
            "binding": canonical_sha({"strategy": selection.STRATEGY, "scopes": [scope], "seed": seed}),
            "order": [scope["capability_id"]], "selected": [], "accepted_sha256": canonical_sha(seed),
            "checkpoint_head": None, "total_invocations": 1, "calls": [row],
            "lineage_invocations": {"candidate-1": 1, "candidate-2": 0, "candidate-3": 0},
            "current": {"order_index": 0, "capability_id": scope["capability_id"], "base_sha256": canonical_sha(seed),
                        "admissions": {}, "execution": 1, "selection_attempts": []}}
        state.update(selection_status="pending", phase="generating-capability", candidate_admissions={}, candidate_attempts={})
        atomic_json(run / "run.json", state)
        private = deepcopy(state)
        private["capability_selection"]["current"] = None
        private.update(runtime_slot="candidate-1", runtime_execution=1)
        data = {"root": str(self.root), "run_dir": str(run), "workspace": str(workspace), "state": private,
                "scope_index": 0, "accepted_seed": seed, "selected_records": [], "runner": state["runner_configuration"]}
        identity = canonical_sha(data)
        life = workspace / "lifecycle"
        atomic_json(life / "job.json", {"schema_version": "newrouge.mvg-capability-worker.v1", "identity": identity, "input": data})
        atomic_json(life / "process.json", {"pid": 123456789, "identity": identity})
        atomic_json(life / "mailbox/1.request.json", {"identity": identity, "sequence": 1, "kind": "reserve"})
        atomic_json(life / "mailbox/1.response.json", {"identity": identity, "sequence": 1,
            "value": {k: v for k, v in row.items() if k != "outcome"}})
        if complete:
            names = ("proposal.json", "admission-review.json", "admission-execution.json")
            for name in names:
                atomic_json(workspace / name, {"explicit_offline_assembly": True})
            atomic_json(life / "result.json", {"schema_version": "newrouge.mvg-capability-worker.v1", "identity": identity,
                "pid": 123456789, "status": "admitted", "total_invocations": 1, "errors": [],
                "artifacts": {name: file_sha(workspace / name) for name in names}})
        (run / "capability-coordinator.lock").write_bytes(b"0")
        return run, state, life

    def owners(self):
        # Portable fixture roots do not contain deployed Python owners. Only this
        # origin check is replaced; production has no corresponding switch.
        return patch.object(recovery, "_check_owners")

    def assembly(self):
        stack = contextlib.ExitStack()
        stack.enter_context(self.owners())
        stack.enter_context(patch.object(recovery, "process_absent", return_value=True))
        stack.enter_context(patch.object(selection, "verified_prefix", return_value=None))
        stack.enter_context(patch.object(selection, "candidate_artifacts", return_value=({"explicit_offline_assembly": True}, {}, {})))
        stack.enter_context(patch("plan_mvg.validate_proposal", return_value={"offline_assembly_only": True}))
        return stack

    def test_unknown_missing_completion_is_blocked_and_byte_preserved(self):
        run, state, _ = self.make_run()
        before = recovery.manifest(run)
        with self.owners(), patch.object(recovery, "process_absent", return_value=True), \
             patch.object(selection, "verified_prefix", side_effect=AssertionError("No post-unknown continuation")):
            report, proposed = recovery.plan(self.root, run_id="recovery")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["reason"], "dispatch_outcome_unknown")
        self.assertEqual(proposed, state)
        self.assertEqual(report["logical_reservations"], 1)
        self.assertEqual(recovery.manifest(run), before)
        self.assertEqual(report["released_reservations"], 0)

    def test_blocked_apply_does_not_write_or_release_reservation(self):
        run, _, _ = self.make_run()
        with self.owners(), patch.object(recovery, "process_absent", return_value=True):
            report, _ = recovery.plan(self.root, run_id="recovery")
            before = recovery.manifest(run)
            with self.assertRaisesRegex(ValueError, "blocked_no_publication"):
                recovery.apply(self.root, run_id="recovery", expected_plan=report["plan_identity"])
        self.assertEqual(recovery.manifest(run), before)

    def test_live_or_reused_pid_blocks_without_touching_process(self):
        run, _, _ = self.make_run()
        before = recovery.manifest(run)
        with self.owners(), patch.object(recovery, "process_absent", return_value=False):
            report, _ = recovery.plan(self.root, run_id="recovery")
        self.assertIn("worker_pid_live_or_unobservable", [row["reason"] for row in report["blockers"]])
        self.assertEqual(recovery.manifest(run), before)

    def test_foreign_module_origins_are_rejected(self):
        run, _, _ = self.make_run()
        before = recovery.manifest(run)
        with self.assertRaisesRegex(ValueError, "original_module_origin_required"):
            recovery.plan(self.root, run_id="recovery")
        self.assertEqual(recovery.manifest(run), before)

    def test_foreign_cached_transitive_owner_is_rejected(self):
        import _planning_skill_common as common
        deployed_root = Path(runtime.__file__).resolve().parents[2]
        with patch.object(common, "__file__", str(self.root / "foreign/_planning_skill_common.py")):
            with self.assertRaisesRegex(ValueError, "original_import_cache_required"):
                recovery._check_owners(deployed_root)

    def test_changed_reserved_input_is_rejected_even_when_unknown(self):
        run, state, _ = self.make_run()
        prompt = run / state["capability_selection"]["calls"][0]["request_identity"]["workspace"] / "prompt.txt"
        prompt.write_text("changed fixture", encoding="utf-8")
        before = recovery.manifest(run)
        with self.owners(), patch.object(recovery, "process_absent", return_value=True):
            with self.assertRaisesRegex(ValueError, "dispatch_inputs_changed"):
                recovery.plan(self.root, run_id="recovery")
        self.assertEqual(recovery.manifest(run), before)

    def test_job_tampering_is_rejected_before_outcome_or_admission(self):
        run, _, life = self.make_run()
        value = recovery._load(life / "job.json")
        value["input"]["workspace"] += "-different"
        atomic_json(life / "job.json", value)
        with self.owners(), self.assertRaisesRegex(ValueError, "job_identity_changed"):
            recovery.plan(self.root, run_id="recovery")

    def test_capability_profile_cannot_release_conservative_time(self):
        run, _ = self.create("3b-capabilities-v1", run_id="cap-recovery")
        before = recovery.manifest(run)
        with self.owners(), self.assertRaisesRegex(ValueError, "mvg_only_no_time_refund"):
            recovery.plan(self.root, run_id="cap-recovery", planner="capabilities")
        self.assertEqual(recovery.manifest(run), before)

    def test_completed_dispatch_without_original_worker_result_is_still_blocked(self):
        run, _, _ = self.make_run(unknown=False)
        before = recovery.manifest(run)
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None):
            report, _ = recovery.plan(self.root, run_id="recovery")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["reason"], "original_worker_result_missing")
        self.assertEqual(recovery.manifest(run), before)

    def test_complete_assembly_reuses_lifecycle_and_publication_is_idempotent(self):
        run, original, life = self.make_run(unknown=False, complete=True)
        before = recovery.manifest(run)
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None), \
             patch("subprocess.Popen", side_effect=AssertionError("No worker or model may start")):
            report, proposed = recovery.plan(self.root, run_id="recovery")
            self.assertEqual(report["status"], "ready")
            self.assertEqual(recovery.manifest(run), before)
            published = recovery.apply(self.root, run_id="recovery", expected_plan=report["plan_identity"])
            self.assertEqual(published["status"], "published")
            self.assertEqual(recovery._load(run / "run.json"), proposed)
            self.assertEqual(proposed["capability_selection"]["calls"], original["capability_selection"]["calls"])
            self.assertEqual(proposed["active_elapsed_seconds"], original["active_elapsed_seconds"])
            for name, digest in before.items():
                if name != "run.json":
                    self.assertEqual(file_sha(run / name), digest)
            again, _ = recovery.plan(self.root, run_id="recovery")
            self.assertEqual(again["status"], "no-op")
            unchanged = recovery.manifest(run)
            recovery.apply(self.root, run_id="recovery", expected_plan=again["plan_identity"])
            self.assertEqual(recovery.manifest(run), unchanged)
            self.assertTrue(life.is_dir())

    def test_stale_plan_rejected_before_publication(self):
        run, _, life = self.make_run(unknown=False, complete=True)
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None):
            report, _ = recovery.plan(self.root, run_id="recovery")
            (life / "late-original.log").write_bytes(b"late")
            before = recovery.manifest(run)
            with self.assertRaisesRegex(ValueError, "plan_changed"):
                recovery.apply(self.root, run_id="recovery", expected_plan=report["plan_identity"])
        self.assertEqual(recovery.manifest(run), before)

    def test_result_identity_and_artifact_tampering_fail_closed(self):
        run, _, life = self.make_run(unknown=False, complete=True)
        result = recovery._load(life / "result.json")
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None):
            result["identity"] = "changed"
            atomic_json(life / "result.json", result)
            with self.assertRaisesRegex(ValueError, "result_identity_changed"):
                recovery.plan(self.root, run_id="recovery")
            result["identity"] = recovery._load(life / "job.json")["identity"]
            atomic_json(life / "result.json", result)
            (life.parent / "proposal.json").write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "result_artifacts_changed"):
                recovery.plan(self.root, run_id="recovery")

    def test_original_protocol_binding_is_required_for_outcome_recovery(self):
        run, state = self.create(run_id="binding-recovery")
        binding, row = self.bound_call(run, state)
        outcome = row.pop("outcome")
        original = deepcopy(row)
        worker = {"requests": {1: {"kind": "reserve"}, 2: {"kind": "outcome", "reservation_id": row["reservation_id"], "outcome": outcome}},
                  "responses": {1: {"value": deepcopy(row)}}}
        before = recovery.manifest(run)
        self.assertEqual(recovery.completed_outcome(run, row, worker), outcome)
        self.assertEqual(row, original)
        self.assertEqual(recovery.manifest(run), before)
        output = Path(binding["output_path"])
        output.write_bytes(output.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            recovery.completed_outcome(run, row, worker)

    def test_missing_ack_duplicate_and_failed_outcome_never_become_completed(self):
        row = {"reservation_id": "test:dispatch:1"}
        worker = {"requests": {1: {"kind": "reserve"}, 2: {"kind": "outcome", "reservation_id": row["reservation_id"], "outcome": {"status": "failed"}}},
                  "responses": {1: {"value": deepcopy(row)}}}
        self.assertIsNone(recovery.completed_outcome(Path("unused"), row, worker))
        worker["responses"] = {}
        with self.assertRaisesRegex(ValueError, "acknowledgment_missing"):
            recovery.completed_outcome(Path("unused"), row, worker)
        worker["requests"][3] = deepcopy(worker["requests"][2])
        with self.assertRaisesRegex(ValueError, "duplicate_outcome"):
            recovery.completed_outcome(Path("unused"), row, worker)

    def test_publication_interruption_distinguishes_exact_pre_post_and_third_state(self):
        run, _, _ = self.make_run(unknown=False, complete=True)
        actual_write = recovery.atomic_json
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None):
            report, proposed = recovery.plan(self.root, run_id="recovery")
            original = (run / "run.json").read_bytes()
            def interrupt_before_commit(path, value):
                if path == run / "run.json":
                    raise OSError("offline interruption before atomic commit")
                return actual_write(path, value)
            with patch.object(recovery, "atomic_json", side_effect=interrupt_before_commit):
                with self.assertRaisesRegex(OSError, "offline interruption"):
                    recovery.apply(self.root, run_id="recovery", expected_plan=report["plan_identity"])
            self.assertEqual((run / "run.json").read_bytes(), original)
            self.assertEqual(recovery.publication_status(self.root, run_id="recovery", plan_identity=report["plan_identity"])["status"], "not_committed")
            # Simulate the exact originally sealed atomic commit, then an exec
            # transport loss before the publisher's return became observable.
            actual_write(run / "run.json", proposed)
            before = recovery.manifest(run)
            self.assertEqual(recovery.publication_status(self.root, run_id="recovery", plan_identity=report["plan_identity"])["status"], "committed")
            self.assertEqual(recovery.manifest(run), before)
            (run / "run.json").write_bytes((run / "run.json").read_bytes() + b" ")
            before = recovery.manifest(run)
            self.assertEqual(recovery.publication_status(self.root, run_id="recovery", plan_identity=report["plan_identity"])["status"], "unknown_third_state")
            self.assertEqual(recovery.manifest(run), before)

    def test_budget_and_original_reservation_changes_are_not_projections(self):
        _, original, _ = self.make_run()
        changes = [lambda s: s.update(active_elapsed_seconds=-1),
                   lambda s: s.update(**{"mvg.run_invocation_limit": 193}),
                   lambda s: s["capability_selection"].update(total_invocations=0),
                   lambda s: s["capability_selection"]["lineage_invocations"].update({"candidate-1": 0}),
                   lambda s: s["capability_selection"]["calls"][0].update(execution=2),
                   lambda s: s["capability_selection"]["current"].update(execution=2)]
        for mutate in changes:
            changed = deepcopy(original)
            mutate(changed)
            with self.assertRaises(ValueError):
                recovery.budget_invariants(original, changed)

    def test_candidate_validation_failure_cannot_publish_worker_self_report(self):
        run, _, _ = self.make_run(unknown=False, complete=True)
        before = recovery.manifest(run)
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None), \
             patch.object(selection, "candidate_artifacts", side_effect=ValueError("offline independent proof invalid")):
            with self.assertRaisesRegex(ValueError, "independent proof invalid"):
                recovery.plan(self.root, run_id="recovery")
        self.assertEqual(recovery.manifest(run), before)

    def test_rehashed_job_cannot_move_scope_or_slot(self):
        run, _, life = self.make_run()
        job = recovery._load(life / "job.json")
        job["input"]["state"]["runtime_slot"] = "candidate-2"
        job["identity"] = canonical_sha(job["input"])
        atomic_json(life / "job.json", job)
        with self.owners(), self.assertRaisesRegex(ValueError, "job_slot_changed"):
            recovery.plan(self.root, run_id="recovery")

    def test_native_busy_lock_cannot_publish(self):
        run, _, _ = self.make_run(unknown=False, complete=True)
        from _mvg_capability_checkpoint import coordinator_lock
        with self.assembly(), patch.object(runtime, "verify_reserved_call", return_value=None):
            report, _ = recovery.plan(self.root, run_id="recovery")
            before = recovery.manifest(run)
            with coordinator_lock(run), self.assertRaises((ValueError, PermissionError)):
                recovery.apply(self.root, run_id="recovery", expected_plan=report["plan_identity"])
            self.assertEqual(recovery.manifest(run), before)

    @unittest.skipUnless(os.name == "nt", "Windows process identity contract")
    def test_real_current_windows_pid_is_never_declared_absent(self):
        self.assertFalse(recovery.process_absent(os.getpid()))


class CompletedProofRecoveryTests(unittest.TestCase):
    """Full original proof validators; synthetic protocol and worker envelope only."""
    setUp = existing_fixture.RuntimeTests.setUp
    create = existing_fixture.CompactWireTests.create

    @unittest.skipUnless(os.name == "nt", "Native Windows recovery contract")
    def test_complete_proof_recovered_then_native_coordinator_skips_old_lifecycle(self):
        import _mvg_capability_worker as worker
        actual_generate = selection.generate_append
        captured = {}
        def interrupt_after_completed_append(root, state, workspace, **kwargs):
            private = deepcopy(state)
            private["capability_selection"]["current"] = None
            data = {"root": str(root.resolve()), "run_dir": str(runtime.run_location(root, "mvg", state["run_id"]).resolve()),
                "workspace": str(workspace.resolve()), "state": private, "scope_index": kwargs["scope_index"],
                "accepted_seed": deepcopy(kwargs["accepted_seed"]), "selected_records": deepcopy(kwargs["selected_records"]),
                "runner": deepcopy(state["runner_configuration"])}
            result = actual_generate(root, state, workspace, **kwargs)
            captured.update(data=data, result=result)
            raise KeyboardInterrupt("offline completed first worker before coordinator admission publication")
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high",
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            with patch.object(selection, "generate_append", side_effect=interrupt_after_completed_append):
                with self.assertRaisesRegex(KeyboardInterrupt, "completed first worker"):
                    existing_fixture.CompactWireTests.complete_offline_transport_coordinator(self, "3b-mvg-v1", complete_wire=True)
            data, result = captured["data"], captured["result"]
            run = Path(data["run_dir"])
            workspace = Path(data["workspace"])
            self.assertEqual(result["status"], "admitted")
            # Only the outer worker envelope is synthetic: original machine,
            # semantic, reservation, protocol and binding validators stay live.
            identity = canonical_sha(data)
            life = workspace / "lifecycle"
            atomic_json(life / "job.json", {"schema_version": worker.SCHEMA, "identity": identity, "input": data})
            atomic_json(life / "process.json", {"identity": identity, "pid": 123456789})
            (life / "mailbox").mkdir()
            names = ("proposal.json", "admission-review.json", "admission-execution.json")
            atomic_json(life / "result.json", {"schema_version": worker.SCHEMA, "identity": identity, "pid": 123456789,
                "status": result["status"], "total_invocations": result["total_invocations"], "errors": result.get("errors", []),
                "artifacts": {name: file_sha(workspace / name) for name in names}})
            # Model a lost coordinator projection in this disposable fixture:
            # retain all three charges, original completed protocol/host/binding,
            # canonical drafts and worker result; only one parent outcome is
            # absent. Mailbox/worker envelopes are explicitly synthetic data.
            interrupted = recovery._load(run / "run.json")
            unknown = interrupted["capability_selection"]["calls"][0]
            original_outcome = unknown.pop("outcome")
            atomic_json(life / "mailbox/1.request.json", {"identity": identity, "sequence": 1, "kind": "reserve"})
            atomic_json(life / "mailbox/1.response.json", {"identity": identity, "sequence": 1, "value": deepcopy(unknown)})
            atomic_json(life / "mailbox/2.request.json", {"identity": identity, "sequence": 2, "kind": "outcome",
                "reservation_id": unknown["reservation_id"], "outcome": original_outcome})
            atomic_json(run / "run.json", interrupted)
            (run / "capability-coordinator.lock").write_bytes(b"0")
            before = recovery.manifest(run)
            with patch.object(recovery, "_check_owners"):
                report, _ = recovery.plan(self.root, run_id="runtime")
                self.assertEqual(report["status"], "ready")
                self.assertEqual(report["recovered_admissions"], ["candidate-1"])
                self.assertEqual(report["recovered_completion_ids"], [unknown["reservation_id"]])
                self.assertEqual(recovery.manifest(run), before)
                recovery.apply(self.root, run_id="runtime", expected_plan=report["plan_identity"])
            restored = recovery._load(run / "run.json")
            self.assertEqual(restored["capability_selection"]["total_invocations"], 3)
            self.assertEqual(restored["capability_selection"]["calls"], recovery._load(run / "model-execution.json")["capability_selection"]["calls"])
            old_lifecycle = {p.relative_to(life).as_posix(): file_sha(p) for p in life.rglob("*") if p.is_file()}
            def no_new_worker(job_dir, *args, **kwargs):
                self.assertEqual(job_dir, selection.scope_workspace(run, "candidate-2", 0, 1) / "lifecycle")
                raise KeyboardInterrupt("offline stop before next worker")
            with patch.object(worker, "run_candidate", side_effect=no_new_worker):
                with self.assertRaisesRegex(KeyboardInterrupt, "before next worker"):
                    selection.generate_selected_capabilities(self.root, run, restored, backend="offline-transport",
                        invoke_factory=None, selector_factory=None, worker_config=data["runner"])
            self.assertEqual(restored["capability_selection"]["total_invocations"], 3)
            self.assertEqual({p.relative_to(life).as_posix(): file_sha(p) for p in life.rglob("*") if p.is_file()}, old_lifecycle)


if __name__ == "__main__":
    unittest.main()
