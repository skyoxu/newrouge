"""Offline recovery contracts; mocked history is never real model acceptance."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_review_recovery as recovery
import _b_route_planning_runtime as runtime
import _mvg_capability_selection as selection
from _planning_skill_common import canonical_sha


class ReviewRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.gettempdir()
        self.temp = tempfile.TemporaryDirectory(prefix="brr-" + uuid.uuid4().hex[:8] + "-", dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / "logs/ci/capability-planning/test"
        self.run.mkdir(parents=True)
        self.workspace = self.run / "candidates/candidate-1/scope-1"
        self.append_path = self.workspace / "capability-append/append-ledger.json"
        desc = {"schema_version": runtime.PROFILE, "planner": "capabilities", "profile": "3b-capabilities-v1",
            "prepared_ref": "logs/fixture/prepared.json", "input_identity": canonical_sha("fixture-input"),
            "frozen_sha256": canonical_sha("fixture-frozen"), "rules": {"offline_fixture_only": True},
            "limits": runtime.profile_limits("3b-capabilities-v1"), "wire_delivery": runtime.wire.CURRENT_SCHEMA}
        calls = [{"number": n, "run_id": "test", "candidate": "candidate-1", "phase": phase,
                  "reservation_id": "test:dispatch:" + str(n), "reserved_at_utc": "fixture-" + str(n),
                  "generation": 1, "execution": 1, "lineage": "candidate-1-r1", "capability_id": "fixture-scope",
                  "outcome": {"status": "completed", "active_elapsed_seconds": seconds}}
                 for n, phase, seconds in [(1, "generate", 1.25), (2, "generate", 2.5), (3, "semantic", 3.75)]]
        admission = {"status": "blocked", "retryable": False, "workspace": self.workspace.relative_to(self.run).as_posix()}
        self.original = {"schema_version": runtime.RUN, "run_id": "test", "input_stage": "3b",
            "runtime_identity": canonical_sha(desc), "analysis_identity_sha256": desc["input_identity"],
            "planning_runtime": desc, "mvg.run_invocation_limit": 96, "active_elapsed_seconds": 8.5,
            "phase": "selection-blocked", "selection_status": "blocked",
            "selection_block_reason": "selection_blocked_insufficient_admitted_candidates",
            "capability_selection": {"calls": calls, "total_invocations": 3, "selected": [], "terminal": True,
                "lineage_invocations": {"candidate-1": 3, "candidate-2": 0}, "generation": 1,
                "current": {"order_index": 0, "execution": 1, "capability_id": "fixture-scope",
                            "admissions": {"candidate-1": admission}}}}
        self.append = {"status": "blocked", "records": [], "completed": [], "total_invocations": 3,
            "errors": [{"code": "append_execution_failure", "stage": "semantic", "error_type": "runner_execution_failed",
                        "detail": "b_route_independent_review_source_support_invalid"}],
            "current": {"proposal": None, "delta": None, "issue": None, "issues": [], "context": 1, "issue_attempts": {}}}
        self.transition = {"transition_digest": canonical_sha("fixture-transition")}
        self.funding = {"schema_version": "newrouge.story25-native-funding.v1", "paid_or_unknown_before_run": 55,
            "campaign_limit": 290, "subsequent_full_reservation": 192, "maximum_native_charges": 43, "released": 0}
        self.bindings = [{"offline_binding": "generation-1"}, {"offline_binding": "generation-2"},
                         {"offline_binding": "failed-review"}]
        self.put(self.run / "run.json", self.original)
        self.put(self.append_path, self.append)
        self.put(self.run / "model-execution.json", {"fixture_model_execution": True})
        self.put(self.run / "candidates/candidate-1/lineage-execution.json", {
            "candidate": "candidate-1", "lineage": "candidate-1-r1", "model_invocation_count": 3,
            "reservation_ids": [row["reservation_id"] for row in calls]})
        (self.run / "capability-coordinator.lock").write_bytes(b"0")
        (self.run / "original-artifact.bin").write_bytes(b"original immutable output\n")

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def tree(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def installed_record(self):
        state = deepcopy(self.original)
        state["schema_version"] = runtime.CONTINUATION_RUN
        state["b_route_execution_transition"] = deepcopy(self.transition)
        state["b_route_campaign_funding"] = deepcopy(self.funding)
        self.home = self.run / "recovery/review-1"
        self.record_path = self.home / "record.json"
        artifact = self.run / "original-artifact.bin"
        self.record = {"schema_version": recovery.SCHEMA, "run_id": "test",
            "run_ref": self.run.relative_to(self.root).as_posix(), "original_run": deepcopy(self.original),
            "original_append": deepcopy(self.append), "transition": deepcopy(self.transition),
            "campaign_funding": deepcopy(self.funding),
            "proposal_sha256": canonical_sha({"offline_proposal": "unchanged"}),
            "immutable_original_files": {"original-artifact.bin": recovery.codec.raw_digest(artifact.read_bytes())},
            "historical_generation_bindings": [canonical_sha(v) for v in self.bindings[:2]],
            "retained_failed_review_binding": canonical_sha(self.bindings[2]), "new_dispatch_ordinal": 4}
        self.put(self.record_path, self.record)
        identity = recovery.codec.raw_digest(self.record_path.read_bytes())
        state["b_route_review_recovery"] = {"schema_version": recovery.SCHEMA,
            "record_ref": self.record_path.relative_to(self.root).as_posix(), "record_digest": identity,
            "artifact_root": str(self.root)}
        self.put(self.home / "committed.json", {"record_digest": identity,
            "transition_digest": self.transition["transition_digest"]})
        return state

    def rewrite_fixture_record(self, state):
        self.put(self.record_path, self.record)
        identity = recovery.codec.raw_digest(self.record_path.read_bytes())
        state["b_route_review_recovery"]["record_digest"] = identity
        self.put(self.home / "committed.json", {"record_digest": identity,
            "transition_digest": state["b_route_execution_transition"]["transition_digest"]})

    def amendment_ready(self):
        state = self.installed_record()
        state.update(phase="selection-blocked", selection_status="blocked")
        append = deepcopy(self.append)
        append.update(status="generating", errors=[])
        append["current"]["proposal"] = {"offline_proposal": "unchanged"}
        self.put(self.append_path, append)
        self.put(self.run / "run.json", state)
        return state

    def stub_transition(self):
        module = types.ModuleType("_b_route_execution_transition")
        module.build_transition = Mock(return_value=deepcopy(self.transition))
        module.load_prepared = Mock(return_value={"input_identity": self.original["analysis_identity_sha256"]})
        module.verify_historical_generation = Mock(return_value={"fixture_history_verified": True})
        return module

    def worker_input_ready(self):
        state = self.amendment_ready()
        stub = self.stub_transition()
        stub.build_transition.return_value = {"transition_digest": canonical_sha("fixture-r6-amended")}
        with patch.dict(sys.modules, {"_b_route_execution_transition": stub}):
            recovery.amend_before_dispatch(self.root, self.run, original_source_root=self.root / "r5", current_commit="fixture-r6")
        state = json.loads((self.run / "run.json").read_bytes())
        state.update(phase="selection-blocked", selection_status="blocked", active_elapsed_seconds=25.5)
        state["capability_selection"]["terminal"] = True
        state["capability_selection"]["current"]["admissions"]["candidate-1"]["retryable"] = False
        append = json.loads(self.append_path.read_bytes())
        append.update(status="blocked", errors=[{"code": "append_input_preparation_failed", "detail": "semantic_error"}])
        append["current"].update(issue={"code": "append_semantic_execution_invalid", "path": "model"},
            issue_attempts={"append_semantic_execution_invalid@model": 1}, delta={"fixture": "unchanged-generation"})
        self.put(self.append_path, append)
        self.put(self.run / "run.json", state)
        worker = self.workspace / "lifecycle-review-recovery-1"
        private = deepcopy(state)
        private.update(runtime_slot="candidate-1", runtime_execution=1)
        private["capability_selection"]["current"] = None
        payload = {"root": str(self.root), "run_dir": str(self.run), "workspace": str(self.workspace),
            "state": private, "scope_index": 0, "selected_records": [], "accepted_seed": {}, "runner": {"fixture": True}}
        identity = canonical_sha(payload)
        self.put(worker / "job.json", {"schema_version": "newrouge.mvg-capability-worker.v1", "identity": identity, "input": payload})
        self.put(worker / "process.json", {"pid": 123456, "identity": identity})
        self.put(worker / "result.json", {"schema_version": "newrouge.mvg-capability-worker.v1", "identity": identity,
            "pid": 123456, "status": "blocked", "total_invocations": 3, "errors": deepcopy(append["errors"])})
        self.put(worker / "progress.json", {"status": "blocked", "total_invocations": 3})
        self.put(worker / "mailbox/1.request.json", {"identity": identity, "sequence": 1, "kind": "cost", "phase": "review", "known_evidence_calls": 1})
        self.put(worker / "mailbox/1.response.json", {"identity": identity, "sequence": 1, "value": {
            "remaining": {"run": 93, "lineage": 61}, "future": {"run": 3, "lineage": 0},
            "selector_calls": 1, "unknown_future_scope_estimate": {"run": 0, "lineage": 0}}})
        (worker / "worker.log").write_bytes(b"")
        stage = self.workspace / "capability-append/stage-costs/4-review.json"
        self.put(stage, {"schema_version": "newrouge.mvg-stage-cost.v1", "phase": "review", "status": "ready",
            "stage_dispatch_status": "not_dispatched", "remaining_calls": {"run": 93, "lineage": 61}})
        return state, append, worker, stage

    def test_worker_input_recovery_preserves_parent_worker_cost_calls_and_attempts(self):
        state, append, worker, stage = self.worker_input_ready()
        before = self.tree()
        stub = self.stub_transition()
        stub.build_transition.return_value = {"transition_digest": canonical_sha("fixture-r7")}
        with patch.dict(sys.modules, {"_b_route_execution_transition": stub}):
            report = recovery.resume_pre_dispatch_worker(self.root, self.run, self.root / "r5", "fixture-r7")
        resumed = json.loads((self.run / "run.json").read_bytes())
        record = recovery.validate_recovery(self.root, resumed)
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["worker_attempt"], 2)
        self.assertEqual(report["next_dispatch"], "test:dispatch:4")
        self.assertEqual(resumed["b_route_review_worker_attempt"], 2)
        self.assertEqual(resumed["capability_selection"]["calls"], state["capability_selection"]["calls"])
        self.assertEqual(resumed["capability_selection"]["lineage_invocations"], {"candidate-1": 3, "candidate-2": 0})
        self.assertEqual(resumed["active_elapsed_seconds"], 25.5)
        self.assertEqual(resumed["mvg.run_invocation_limit"], 96)
        restored = json.loads(self.append_path.read_bytes())
        self.assertEqual(restored, {**append, "status": "generating", "errors": []})
        self.assertEqual(record["worker_recovery"]["parent_ref"], state["b_route_review_recovery"])
        self.assertEqual(recovery._image_bytes(record["worker_recovery"]["previous_run"]), before[(self.run / "run.json").relative_to(self.root).as_posix()])
        self.assertEqual(recovery._image_bytes(record["worker_recovery"]["previous_append"]), before[self.append_path.relative_to(self.root).as_posix()])
        self.assertEqual(record["worker_recovery"]["worker_manifest"], recovery._worker_manifest(self.run, worker))
        self.assertEqual(record["worker_recovery"]["stage_cost"]["raw_digest"], recovery.codec.raw_digest(stage.read_bytes()))
        for name, data in before.items():
            if name not in {(self.run / "run.json").relative_to(self.root).as_posix(), self.append_path.relative_to(self.root).as_posix()}:
                self.assertEqual((self.root / name).read_bytes(), data)
        after = self.tree()
        with self.assertRaisesRegex(ValueError, "worker_already_recovered"):
            recovery.resume_pre_dispatch_worker(self.root, self.run, self.root / "r5", "fixture-r7")
        self.assertEqual(self.tree(), after)
        # A later real reservation remains permitted by the historical proof
        # validator, without weakening the preserved original prefix.
        resumed["capability_selection"]["calls"].append({"number": 4, "outcome": {"status": "completed"}})
        resumed["capability_selection"]["total_invocations"] = 4
        resumed["capability_selection"]["lineage_invocations"]["candidate-1"] = 4
        resumed["active_elapsed_seconds"] += 1
        recovery.validate_recovery(self.root, resumed)

    def test_worker_input_recovery_rejects_dispatch_unknown_reserve_or_unfinished_worker(self):
        for case in ("count4", "unknown", "sandbox", "worker_unfinished", "reserve", "outcome", "proposal", "stage"):
            with self.subTest(case=case), ReviewRecoveryTests("test_worker_input_recovery_preserves_parent_worker_cost_calls_and_attempts").fixture_context() as fixture:
                state, _append, worker, stage = fixture.worker_input_ready()
                if case == "count4":
                    state["capability_selection"]["calls"].append({"number": 4})
                    state["capability_selection"]["total_invocations"] = 4
                    state["capability_selection"]["lineage_invocations"]["candidate-1"] = 4
                    fixture.put(fixture.run / "run.json", state)
                elif case == "unknown":
                    state["capability_selection"]["calls"][2]["outcome"]["status"] = "unknown"
                    fixture.put(fixture.run / "run.json", state)
                elif case == "sandbox":
                    (fixture.workspace / "capability-append/c4").mkdir()
                elif case == "worker_unfinished":
                    (worker / "result.json").unlink()
                elif case in ("reserve", "outcome"):
                    request = json.loads((worker / "mailbox/1.request.json").read_bytes())
                    request["kind"] = case
                    fixture.put(worker / "mailbox/1.request.json", request)
                elif case == "proposal":
                    changed = json.loads(fixture.append_path.read_bytes())
                    changed["current"]["proposal"]["edited"] = True
                    fixture.put(fixture.append_path, changed)
                else:
                    value = json.loads(stage.read_bytes())
                    value["stage_dispatch_status"] = "dispatched"
                    fixture.put(stage, value)
                before = fixture.tree()
                stub = fixture.stub_transition()
                with patch.dict(sys.modules, {"_b_route_execution_transition": stub}), self.assertRaises((ValueError, OSError)):
                    recovery.resume_pre_dispatch_worker(fixture.root, fixture.run, fixture.root / "r5", "fixture-r7")
                self.assertEqual(fixture.tree(), before)
                stub.build_transition.assert_not_called()

    def test_worker_recovery_validation_checks_historical_parent_and_new_immutable_artifacts(self):
        for case in ("copy", "parent_transition", "parent_ref", "clock", "attempt", "worker_bytes", "cost_bytes", "parent_marker"):
            with self.subTest(case=case), ReviewRecoveryTests("test_worker_input_recovery_preserves_parent_worker_cost_calls_and_attempts").fixture_context() as fixture:
                state, _append, worker, stage = fixture.worker_input_ready()
                stub = fixture.stub_transition()
                stub.build_transition.return_value = {"transition_digest": canonical_sha("fixture-r7")}
                with patch.dict(sys.modules, {"_b_route_execution_transition": stub}):
                    recovery.resume_pre_dispatch_worker(fixture.root, fixture.run, fixture.root / "r5", "fixture-r7")
                current = json.loads((fixture.run / "run.json").read_bytes())
                path = fixture.root / current["b_route_review_recovery"]["record_ref"]
                record = json.loads(path.read_bytes())
                if case == "copy":
                    record["original_run"]["mvg.run_invocation_limit"] = 192
                elif case in ("parent_transition", "parent_ref"):
                    previous = json.loads(recovery._image_bytes(record["worker_recovery"]["previous_run"]))
                    if case == "parent_transition":
                        previous["b_route_execution_transition"] = deepcopy(current["b_route_execution_transition"])
                    else:
                        previous["b_route_review_recovery"] = deepcopy(current["b_route_review_recovery"])
                    record["worker_recovery"]["previous_run"] = recovery._image(json.dumps(previous).encode())
                elif case == "clock":
                    current["active_elapsed_seconds"] = 25.0
                elif case == "attempt":
                    current["b_route_review_worker_attempt"] = 1
                elif case == "worker_bytes":
                    (worker / "worker.log").write_bytes(b"later change")
                elif case == "cost_bytes":
                    stage.write_bytes(b"later stage cost")
                else:
                    parent = fixture.root / record["worker_recovery"]["parent_ref"]["record_ref"]
                    parent.with_name("committed.json").unlink()
                if case in ("copy", "parent_transition", "parent_ref"):
                    fixture.put(path, record)
                    identity = recovery.codec.raw_digest(path.read_bytes())
                    current["b_route_review_recovery"]["record_digest"] = identity
                    fixture.put(path.with_name("committed.json"), {"record_digest": identity,
                        "transition_digest": current["b_route_execution_transition"]["transition_digest"]})
                before = fixture.tree()
                with self.assertRaises((ValueError, OSError)):
                    recovery.validate_recovery(fixture.root, current)
                self.assertEqual(fixture.tree(), before)

    def fixture_context(self):
        from contextlib import contextmanager
        @contextmanager
        def fixture():
            self.setUp()
            try:
                yield self
            finally:
                self.doCleanups()
        return fixture()

    def test_validate_preserves_old_calls_times_and_allows_new_charged_call_without_writes(self):
        state = self.installed_record()
        before = self.tree()
        record = recovery.validate_recovery(self.root, state)
        self.assertEqual(record["original_run"], self.original)
        self.assertEqual(self.tree(), before)
        old_calls = deepcopy(state["capability_selection"]["calls"])
        ledger = state["capability_selection"]
        ledger["calls"].append({"number": 4, "phase": "semantic", "outcome": {"status": "completed", "active_elapsed_seconds": 2.0}})
        ledger["total_invocations"] = 4
        ledger["lineage_invocations"]["candidate-1"] = 4
        state["active_elapsed_seconds"] += 2.0
        recovery.validate_recovery(self.root, state)
        self.assertEqual(ledger["calls"][:3], old_calls)
        self.assertEqual(sum(r["outcome"]["active_elapsed_seconds"] for r in old_calls), 7.5)
        self.assertEqual(state["mvg.run_invocation_limit"], 96)
        self.assertEqual(self.tree(), before)

    def test_original_charge_identity_status_order_and_time_changes_are_rejected(self):
        original = self.installed_record()
        mutations = [
            lambda s: s["capability_selection"]["calls"][0]["outcome"].update(active_elapsed_seconds=0),
            lambda s: s["capability_selection"]["calls"][2]["outcome"].update(status="unknown"),
            lambda s: s["capability_selection"]["calls"][0].update(reservation_id="replacement:dispatch:1"),
            lambda s: s["capability_selection"]["calls"].reverse(),
            lambda s: s["capability_selection"].update(calls=s["capability_selection"]["calls"][1:]),
        ]
        before = self.tree()
        for mutate in mutations:
            state = deepcopy(original)
            mutate(state)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "original_charges_or_times_changed"):
                recovery.validate_recovery(self.root, state)
        self.assertEqual(self.tree(), before)

    def test_budget_runtime_and_elapsed_refunds_are_rejected(self):
        original = self.installed_record()
        mutations = [lambda s: s.update(runtime_identity=canonical_sha("different-runtime")),
                     lambda s: s["planning_runtime"]["limits"].update(request_limit=192),
                     lambda s: s.update({"mvg.run_invocation_limit": 192}),
                     lambda s: s.update(active_elapsed_seconds=0),
                     lambda s: s["capability_selection"].update(total_invocations=2),
                     lambda s: s["capability_selection"]["lineage_invocations"].update({"candidate-1": 2})]
        for mutate in mutations:
            state = deepcopy(original)
            mutate(state)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "budget_or_base_changed|refunded_charge"):
                recovery.validate_recovery(self.root, state)

    def test_campaign_funding_cannot_be_refunded_or_reallocated(self):
        original = self.installed_record()
        for key, value in [("paid_or_unknown_before_run", 54), ("maximum_native_charges", 44),
                           ("subsequent_full_reservation", 191), ("released", 1)]:
            state = deepcopy(original)
            state["b_route_campaign_funding"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "campaign_funding_changed"):
                recovery.validate_recovery(self.root, state)

    def test_immutable_old_output_tamper_is_rejected(self):
        state = self.installed_record()
        (self.run / "original-artifact.bin").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "original_file_changed"):
            recovery.validate_recovery(self.root, state)

    def test_absent_or_mismatched_committed_marker_stays_blocked_without_repair(self):
        state = self.installed_record()
        marker = self.home / "committed.json"
        marker.unlink()
        before = self.tree()
        with self.assertRaises(FileNotFoundError):
            recovery.validate_recovery(self.root, state)
        self.assertEqual(self.tree(), before)
        self.put(marker, {"record_digest": "wrong", "transition_digest": self.transition["transition_digest"]})
        with self.assertRaisesRegex(ValueError, "partial_transition"):
            recovery.validate_recovery(self.root, state)

    def test_new_payload_requires_exact_transition_digest(self):
        state = self.installed_record()
        for phase in ("generation", "independent_admission"):
            materials = {"phase": phase, "execution_source_transition": self.transition["transition_digest"]}
            recovery.validate_materials_transition(state, materials, {"new_binding": True})
            materials["execution_source_transition"] = canonical_sha("wrong")
            with self.assertRaisesRegex(ValueError, "new_call_missing_source_transition"):
                recovery.validate_materials_transition(state, materials, {"new_binding": True})
        with self.assertRaisesRegex(ValueError, "unexpected_source_transition"):
            recovery.validate_materials_transition({}, {"execution_source_transition": "extra"}, {})

    def test_legacy_generation_requires_pinned_binding_and_legacy_review_is_rejected(self):
        state = self.installed_record()
        for binding in self.bindings[:2]:
            recovery.validate_materials_transition(state, {"phase": "generation"}, binding)
        with self.assertRaisesRegex(ValueError, "unbound_legacy_execution"):
            recovery.validate_materials_transition(state, {"phase": "generation"}, {**self.bindings[0], "tampered": True})
        with self.assertRaisesRegex(ValueError, "legacy_review_cannot_be_reused"):
            recovery.validate_materials_transition(state, {"phase": "independent_admission"}, self.bindings[0])
        with self.assertRaisesRegex(ValueError, "unbound_legacy_execution"):
            recovery.validate_materials_transition(state, {"phase": "independent_admission"}, self.bindings[2])

    def test_verified_prefix_audits_retained_paid_review_without_allowing_admission_reuse(self):
        """The actual receipt caller and material gate run; protocol replay is a fixture."""
        from _planning_skill_common import _runner_prefix, file_sha
        import plan_mvg
        import base64
        state = self.installed_record()
        frozen = {"input_identity": state["analysis_identity_sha256"]}
        sandbox = self.run / "paid-review"
        sandbox.mkdir()
        prompt_path, schema_path, output_path = (sandbox / name for name in ["prompt.txt", "schema.json", "r.json"])
        schema = {"type": "object"}
        root_request = {"offline_complete_root": True}
        proposal = {"provenance": {"draft_chain": []}}
        materials = {"schema_version": runtime.PROFILE, "phase": "independent_admission", "root_request": root_request,
            "root_input_identity": frozen["input_identity"], "runtime_identity": state["runtime_identity"], "run_id": "test",
            "accepted_seed": {}, "proposal": proposal, "prior_candidate": None, "repair_issue": None,
            "lineage_context": 1, "wire_delivery": runtime.wire.CURRENT_SCHEMA, "slot": "candidate-1",
            "generation": 1, "execution": 1, "lineage_identity": canonical_sha("fixture-lineage"),
            "actual_output_schema": schema, "obligations": [], "qualified_sources": []}
        materials["materials_identity"] = canonical_sha(materials)
        instruction = "Use complete governed originals\nOFFLINE FIXTURE"
        prompt_path.write_text(instruction, encoding="utf-8")
        self.put(schema_path, schema)
        self.put(output_path, {"verdict": "approved", "findings": [], "fixture_protocol_only": True})
        runner = self.root / "runner.py"
        runner.write_text("# Never executed by this fixture.\n", encoding="utf-8")
        command = [*_runner_prefix(runner, suppress_bytecode=True), "--workspace", str(sandbox), "--prompt-file", str(prompt_path),
            "--output", str(output_path), "--timeout-sec", "5", "--output-schema", str(schema_path), "--model-request-budget", "1"]
        binding = {"workspace": str(sandbox), "prompt_path": str(prompt_path), "schema_path": str(schema_path),
            "output_path": str(output_path), "request_payload": "offline complete request", "measurement": {"fixture": True},
            "runner_info": {"model": "offline-fixture"}, "host_execution": {"active_elapsed_seconds": 3.75, "command": command},
            "receipt": {"model_identity_evidence": [{"protocol_jsonl_base64": base64.b64encode(b"").decode()}]}, "generated_outputs": {}}
        binding_path = self.run / "binding-3.json"
        self.put(binding_path, binding)
        request = {"workspace": sandbox.relative_to(self.run).as_posix(), "output_path": output_path.relative_to(self.run).as_posix(),
            "prompt_path": prompt_path.relative_to(self.run).as_posix(), "schema_path": schema_path.relative_to(self.run).as_posix(),
            "execution_binding_path": binding_path.relative_to(self.run).as_posix(),
            "input_files": {"prompt.txt": file_sha(prompt_path), "schema.json": file_sha(schema_path)},
            "actual_request_sha256": recovery.codec.raw_digest(binding["request_payload"].encode()), "measurement": binding["measurement"],
            "runner_info_sha256": canonical_sha(binding["runner_info"]), "wire_delivery": runtime.wire.CURRENT_SCHEMA,
            "runner_path": str(runner), "timeout_sec": 5,
            "runtime_identity": state["runtime_identity"], "planning_profile": "3b-capabilities-v1"}
        request["request_sha256"] = canonical_sha(request)
        calls = state["capability_selection"]["calls"]
        for row in calls[:2]:
            row["request_identity"] = {"runtime_identity": state["runtime_identity"], "planning_profile": "3b-capabilities-v1"}
        calls[2]["request_identity"] = request
        calls[2]["outcome"]["output_sha256"] = file_sha(output_path)
        self.record["retained_failed_review_binding"] = canonical_sha(binding)
        self.record["original_run"]["capability_selection"]["calls"] = deepcopy(calls)
        self.rewrite_fixture_record(state)
        scope, seed = {"capability_id": "fixture-scope"}, {}
        state["capability_selection"].update(binding=canonical_sha({"strategy": selection.STRATEGY, "scopes": [scope], "seed": seed}),
            order=["fixture-scope"], accepted_sha256=canonical_sha(seed))
        state["capability_selection"]["current"]["base_sha256"] = canonical_sha(seed)
        self.put(self.run / "run.json", state)
        self.put(self.run / "analysis-input/b-route-prepared.json", frozen)
        actual_verify = runtime.verify_reserved_call
        seen = []

        def audit(run, row):
            seen.append(row["number"])
            return actual_verify(run, row) if row["number"] == 3 else deepcopy(self.bindings[row["number"] - 1])

        before = self.tree()
        with ExitStack() as stack:
            stack.enter_context(patch.object(plan_mvg, "_validate_input_freshness"))
            stack.enter_context(patch.object(selection, "frozen_scopes", return_value=[scope]))
            stack.enter_context(patch.object(selection, "seed_proposal", return_value=seed))
            stack.enter_context(patch.object(runtime, "verify_reserved_call", side_effect=audit))
            stack.enter_context(patch.object(runtime, "verify_call", return_value=json.loads(output_path.read_bytes())))
            stack.enter_context(patch.object(runtime.wire, "read_prompt", return_value=materials))
            stack.enter_context(patch.object(runtime, "materials_prompt", return_value=instruction))
            stack.enter_context(patch.object(runtime, "request_attempt", return_value={"payload": json.dumps(root_request)}))
            stack.enter_context(patch.object(runtime, "obligations", return_value=[]))
            stack.enter_context(patch.object(runtime, "qualified_sources", return_value=[]))
            stack.enter_context(patch.object(runtime, "review_producer_schema", return_value=schema))
            verified = selection.verified_prefix(self.root, self.run, state, verify_history=False, recover_counters=False)
            self.assertEqual(verified, ([scope], seed, []))
            self.assertEqual(seen, [1, 2, 3])
            with self.assertRaisesRegex(ValueError, "unbound_legacy_execution"):
                runtime.bound_materials(binding, state, frozen)
            different = deepcopy(binding)
            different["request_payload"] += "tamper"
            with self.assertRaisesRegex(ValueError, "unbound_legacy_execution"):
                runtime.bound_materials(different, state, frozen, allow_failed_review=True)
        self.assertEqual(self.tree(), before)

    def test_source_amendment_keeps_prior_records_calls_times_and_is_once_only(self):
        state = self.amendment_ready()
        before = self.tree()
        stub = self.stub_transition()
        new_transition = {"transition_digest": canonical_sha("amended-source")}
        stub.build_transition.return_value = new_transition
        with patch.dict(sys.modules, {"_b_route_execution_transition": stub}):
            report = recovery.amend_before_dispatch(self.root, self.run,
                original_source_root=self.root / "frozen-r5", current_commit="amended-fixture-r6")
            self.assertEqual(report["retained_logical_calls"], 3)
            self.assertEqual(report["model_calls"], 0)
            amended = json.loads((self.run / "run.json").read_bytes())
            record = recovery.validate_recovery(self.root, amended)
            self.assertEqual(amended["capability_selection"]["calls"], state["capability_selection"]["calls"])
            self.assertEqual(amended["active_elapsed_seconds"], state["active_elapsed_seconds"])
            self.assertEqual(amended["mvg.run_invocation_limit"], 96)
            self.assertEqual(amended["b_route_campaign_funding"], self.funding)
            self.assertEqual(amended["b_route_execution_transition"], new_transition)
            self.assertTrue(amended["b_route_review_recovery"]["record_ref"].endswith("source-amendment-1/record.json"))
            import base64
            self.assertEqual(base64.b64decode(record["source_amendment"]["previous_run_bytes_base64"]),
                             before[(self.run / "run.json").relative_to(self.root).as_posix()])
            self.assertEqual(record["source_amendment"]["previous_record"], state["b_route_review_recovery"])
            self.assertEqual(record["source_amendment"]["new_dispatches_since_previous"], 0)
            for path in (self.home / "record.json", self.home / "committed.json"):
                self.assertEqual(path.read_bytes(), before[path.relative_to(self.root).as_posix()])
            after = self.tree()
            with self.assertRaisesRegex(ValueError, "source_already_amended"):
                recovery.amend_before_dispatch(self.root, self.run,
                    original_source_root=self.root / "frozen-r5", current_commit="another-fixture-r6")
            self.assertEqual(self.tree(), after)
        stub.build_transition.assert_called_once()

    def test_source_amendment_rejects_any_dispatch_unknown_worker_or_new_sandbox(self):
        for case in ("count4", "unknown", "worker", "sandbox"):
            state = self.amendment_ready()
            artifact = None
            if case == "count4":
                ledger = state["capability_selection"]
                ledger["calls"].append({"number": 4, "outcome": {"status": "completed"}})
                ledger["total_invocations"] = 4
                ledger["lineage_invocations"]["candidate-1"] = 4
            elif case == "unknown":
                state["capability_selection"]["calls"][2]["outcome"]["status"] = "unknown"
            elif case == "worker":
                artifact = self.workspace / "lifecycle-review-recovery-1"
                artifact.mkdir()
            else:
                artifact = self.workspace / "capability-append/c4"
                artifact.mkdir()
            self.put(self.run / "run.json", state)
            before = self.tree()
            stub = self.stub_transition()
            with self.subTest(case=case), patch.dict(sys.modules, {"_b_route_execution_transition": stub}), self.assertRaises(ValueError):
                recovery.amend_before_dispatch(self.root, self.run,
                    original_source_root=self.root / "frozen-r5", current_commit="fixture-r6")
            self.assertEqual(self.tree(), before)
            stub.build_transition.assert_not_called()
            if artifact:
                artifact.rmdir()

    def test_unknown_or_wrong_phase_prepare_fails_before_history_or_any_state_write(self):
        stub = self.stub_transition()
        for index, mutate in enumerate([
            lambda s: s["capability_selection"]["calls"][2]["outcome"].update(status="unknown"),
            lambda s: s["capability_selection"]["calls"][2].pop("outcome"),
            lambda s: s["capability_selection"]["calls"][2].update(phase="selection"),
            lambda s: s["capability_selection"]["calls"][0].update(candidate="candidate-2"),
        ]):
            state = deepcopy(self.original)
            mutate(state)
            self.put(self.run / "run.json", state)
            before = self.tree()
            with self.subTest(case=index), patch.dict(sys.modules, {"_b_route_execution_transition": stub}), \
                 self.assertRaisesRegex(ValueError, "unknown_or_wrong_stage"):
                recovery.prepare_known_review_retry(self.root, self.run,
                    original_source_root=self.root / "frozen-r5", current_commit="fixture-r6")
            self.assertEqual(self.tree(), before)
        stub.build_transition.assert_not_called()
        stub.verify_historical_generation.assert_not_called()

    def test_shared_native_profiles_times_and_nonexpanded_funded_timeout(self):
        self.assertEqual(runtime.profile_limits("3b-capabilities-v1"),
            {"request_limit": 96, "candidate_budget_sec": 2700, "synthesis_budget_sec": 1200, "total_budget_sec": 13500})
        self.assertEqual(runtime.profile_limits("3b-mvg-v1"), {"request_limit": 192})
        import plan_mvg
        self.assertEqual(plan_mvg.MVG_CANDIDATE_INVOCATION_LIMIT, 64)
        state = self.installed_record()
        before = deepcopy(state)
        self.assertEqual(selection.remaining_time(state), 13500 - 7.5)
        self.assertEqual(selection.remaining_time(state, "candidate-1"), 2700 - 7.5)
        self.assertEqual(selection.funded_timeout(state, "candidate-1", {"requested_timeout_sec": 2700}, deadline_remaining=12.9), 12)
        with self.assertRaisesRegex(ValueError, "cannot_fund_invocation"):
            selection.funded_timeout(state, "candidate-1", {"requested_timeout_sec": 2700}, deadline_remaining=0.9)
        self.assertEqual(state, before)

    def test_native_coordinator_reserve_keeps_96_and_64_limits_before_dispatch(self):
        """Exercise the actual reserve closure; no worker or model is launched."""
        import plan_mvg
        import _mvg_capability_worker as worker
        funded = {"b_route_campaign_funding": deepcopy(self.funding)}
        before_funding = deepcopy(funded)
        self.assertIsNone(selection.campaign_preflight(funded, 42))
        self.assertEqual(55 + 192 + self.funding["maximum_native_charges"], 290)
        with self.assertRaisesRegex(ValueError, "cannot_fund_complete_successor"):
            selection.campaign_preflight(funded, 43)
        self.assertEqual(funded, before_funding)
        for key, changed in [("released", 1), ("paid_or_unknown_before_run", 54),
                             ("maximum_native_charges", 44), ("subsequent_full_reservation", 191),
                             ("campaign_limit", 291), ("maximum_native_charges", True)]:
            invalid = deepcopy(funded)
            invalid["b_route_campaign_funding"][key] = changed
            with self.subTest(changed_field=key), self.assertRaisesRegex(ValueError, "campaign_funding_changed"):
                selection.campaign_preflight(invalid, 42)
        timed = deepcopy(self.original)
        for row, seconds in zip(timed["capability_selection"]["calls"],
                                [186.2970000000205, 429.9690000000119, 159.26500000001397]):
            row["outcome"]["active_elapsed_seconds"] = seconds
        timed["active_elapsed_seconds"] = 1053.1559999999881
        timed["runner_configuration"] = {"backend_info": {"supports_synthesis_budget": True}}
        before_time = deepcopy(timed)
        charged_time = sum(row["outcome"]["active_elapsed_seconds"] for row in timed["capability_selection"]["calls"])
        self.assertAlmostEqual(charged_time, 775.531)
        self.assertAlmostEqual(selection.remaining_time(timed), 13500 - charged_time)
        self.assertAlmostEqual(selection.remaining_time(timed, "candidate-1"), 3900 - charged_time)
        self.assertEqual(selection.funded_timeout(timed, "candidate-1", {"requested_timeout_sec": 2700, "synthesis": True}), 1200)
        self.assertEqual(selection.funded_timeout(timed, "candidate-1", {"requested_timeout_sec": 2700}, deadline_remaining=42.9), 42)
        self.assertEqual(timed, before_time)
        for name, total, lineage in [("run96", 96, 3), ("slot64", 3, 64), ("sponsor43", 43, 3), ("sponsor42", 42, 3)]:
            run = self.root / name
            (run / "analysis-input").mkdir(parents=True)
            state = deepcopy(self.original)
            state.pop("selection_block_reason")
            state.update(phase="prepared", selection_status="pending", candidate_attempts={}, candidate_admissions={})
            ledger = state["capability_selection"]
            ledger.update(terminal=False, total_invocations=total)
            ledger["lineage_invocations"]["candidate-1"] = lineage
            ledger["current"]["admissions"] = {}
            if name.startswith("sponsor"):
                state["b_route_campaign_funding"] = deepcopy(self.funding)
            before_calls = deepcopy(ledger["calls"])
            scope = {"capability_id": "fixture-scope", "cumulative_requirement_ids": []}
            attempts = []

            def attempt(_home, _payload, **kwargs):
                attempts.append("reserve")
                kwargs["reserve"]("semantic", request_identity={"requested_timeout_sec": 2700})
                if name == "sponsor42":
                    raise ValueError("offline_stop_after_verified_reservation")
                self.fail("Budget guard permitted an additional native reservation")

            with self.subTest(limit=name), ExitStack() as stack:
                stack.enter_context(patch.object(selection, "frozen_scopes", return_value=[scope]))
                stack.enter_context(patch.object(selection, "seed_proposal", return_value={}))
                stack.enter_context(patch.object(selection, "verified_prefix", return_value=([scope], {}, [])))
                stack.enter_context(patch.object(plan_mvg, "_validate_input_freshness"))
                stack.enter_context(patch.object(worker, "run_candidate", side_effect=attempt))
                with self.assertRaises(ValueError):
                    selection._generate_selected_capabilities(self.root, run, state, backend="offline-fixture",
                        invoke_factory=None, selector_factory=None, worker_config={})
            self.assertEqual(attempts, ["reserve"])
            reserved = int(name == "sponsor42")
            self.assertEqual(ledger["total_invocations"], total + reserved)
            self.assertEqual(ledger["lineage_invocations"]["candidate-1"], lineage + reserved)
            if reserved:
                self.assertEqual(ledger["calls"][:-1], before_calls)
                self.assertEqual(ledger["calls"][-1]["reservation_id"], "test:dispatch:43")
            else:
                self.assertEqual(ledger["calls"], before_calls)
            self.assertEqual(state["mvg.run_invocation_limit"], 96)

    def test_v2_transition_fence_is_rejected_by_frozen_r5_descriptor(self):
        state = self.installed_record()
        self.assertEqual(runtime.descriptor(state), state["planning_runtime"])
        wrong = deepcopy(state)
        wrong["schema_version"] = runtime.RUN
        with self.assertRaisesRegex(ValueError, "descriptor_invalid"):
            runtime.descriptor(wrong)
        wrong = deepcopy(state)
        wrong.pop("b_route_execution_transition")
        with self.assertRaisesRegex(ValueError, "descriptor_invalid"):
            runtime.descriptor(wrong)
        r5 = Path(__file__).resolve().parents[4] / "r5/scripts/python"
        code = "import json,sys;sys.path.insert(0,sys.argv[1]);import _b_route_planning_runtime as r\ns=json.loads(sys.argv[2])\ntry:r.descriptor(s)\nexcept ValueError:print('rejected')\nelse:raise AssertionError('R5 accepted v2')"
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code, str(r5), json.dumps(state)],
                                capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(result.stdout.strip(), "rejected")

    def test_prepare_assembly_preserves_failure_and_original_bytes_under_real_os_lock(self):
        """Only orchestration is tested; all historical proof services are mocked."""
        stub = self.stub_transition()
        drafts = [{"stage": "batch", "content": {"fixture": 1}}, {"stage": "synthesis", "content": {"fixture": 2}}]
        review = {"verdict": "approved", "findings": [], "checks": [{"verdict": "approved"}]}
        proposal = {"schema_version": runtime.candidate.SCHEMA, "input_stage": "3b",
            "input_identity": self.original["analysis_identity_sha256"],
            "provenance": {"kind": "model_draft", "declaration": "Complete original model draft chain; execution separately replayed",
                "upstream_model_history": "declared_model", "draft_chain": drafts, "final_draft_identity": recovery.codec.canonical_digest(drafts[-1])},
            "content": deepcopy(drafts[-1]["content"])}
        before = self.tree()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"_b_route_execution_transition": stub}))
            stack.enter_context(patch.object(runtime, "verify_reserved_call", side_effect=deepcopy(self.bindings)))
            stack.enter_context(patch.object(runtime, "verify_call", side_effect=[*deepcopy(drafts), deepcopy(review)]))
            stack.enter_context(patch.object(runtime, "decode_generation_carrier", side_effect=lambda value: value))
            stack.enter_context(patch.object(runtime.planning, "validate_draft_chain"))
            stack.enter_context(patch.object(runtime, "seed", return_value={"read_only_fixture_seed": True}))
            stack.enter_context(patch.object(runtime, "machine", return_value=[]))
            stack.enter_context(patch.object(runtime.wire, "read_prompt", return_value={"proposal": proposal}))
            stack.enter_context(patch.object(runtime, "review_issues", side_effect=ValueError("b_route_independent_review_source_support_invalid")))
            stack.enter_context(patch.object(runtime, "lineage_identity", return_value=canonical_sha("fixture-lineage")))
            prompt = self.run / "historical-review-prompt.txt"
            prompt.write_text("offline historical prompt", encoding="utf-8")
            self.bindings[2]["prompt_path"] = str(prompt)
            # side_effect values are copied above: point the mocked third binding
            # at an actual fixture prompt, never a production model artifact.
            runtime.verify_reserved_call.side_effect = deepcopy(self.bindings)
            report = recovery.prepare_known_review_retry(self.root, self.run,
                original_source_root=self.root / "frozen-r5", current_commit="fixture-r6")
        self.assertEqual(report["retained_logical_calls"], 3)
        self.assertEqual(report["next_dispatch"], "test:dispatch:4")
        self.assertEqual(report["model_calls"], 0)
        stub.verify_historical_generation.assert_called_once()
        state = json.loads((self.run / "run.json").read_bytes())
        record = recovery.validate_recovery(self.root, state)
        self.assertEqual(record["original_run"], self.original)
        self.assertEqual(record["original_append"], self.append)
        import base64
        for name, image in record["original_control_bytes"].items():
            data = base64.b64decode(image["bytes_base64"], validate=True)
            self.assertEqual(recovery.codec.raw_digest(data), image["raw_digest"])
            self.assertEqual(data, before[(self.run / name).relative_to(self.root).as_posix()])
        self.assertEqual(state["schema_version"], runtime.CONTINUATION_RUN)
        self.assertEqual(state["capability_selection"]["calls"], self.original["capability_selection"]["calls"])
        self.assertEqual(state["active_elapsed_seconds"], self.original["active_elapsed_seconds"])
        self.assertEqual(record["historical_generation_verification"], {"fixture_history_verified": True})
        after = self.tree()
        with patch.dict(sys.modules, {"_b_route_execution_transition": stub}), self.assertRaisesRegex(ValueError, "already_transitioned"):
            recovery.prepare_known_review_retry(self.root, self.run,
                original_source_root=self.root / "frozen-r5", current_commit="fixture-r6")
        self.assertEqual(self.tree(), after)
        for name, data in before.items():
            if name not in {(self.run / "run.json").relative_to(self.root).as_posix(), self.append_path.relative_to(self.root).as_posix()}:
                self.assertEqual((self.root / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
