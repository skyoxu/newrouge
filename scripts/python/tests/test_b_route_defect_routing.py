"""Deterministic tests for Story 3.10 B-route defect routing, anti-disguise guard, delta governance, and reporting.

Covers all 5 Story 3.10 matrix scenarios (IMPL_REUSE, DEF_RETURN, DELTA_GOV, RECUR_BUDGET,
REPORT_FLOOR), CLI / dev_cli / builder end-to-end behavior, and Chapter 6 consumer wiring
(resume_task, chapter6_route, run_single_task_chapter6_lane), using setUpClass fixture
caching for fast deterministic execution.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
REPO_ROOT = SCRIPTS_PY.parents[1]
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(SCRIPTS_SC / "build"), str(SCRIPTS_PY / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_rec
import _b_route_codec as codec
import _b_route_defect_routing as defect_routing
import chapter6_route
import check_b_route_defect_routing as defect_cli
import dev_cli
import dev_cli_builders
import resume_task
import run_review_pipeline
import run_single_task_chapter6_lane as ch6_lane

from test_b_route_chapter5_readiness import (
    _build_b_route_base_repo,
    _put,
    _put_json,
)
from test_b_route_chapter6_gate import (
    DIAGNOSTIC_KEYS,
    _build_explicit_not_enabled_a_repo,
    _reconcile_task_ready,
)
from test_b_route_chapter6_recovery import _create_pipeline_run


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            snap[p.relative_to(root).as_posix()] = p.read_bytes()
    return snap


class DefectRoutingTests(unittest.TestCase):
    """Covers IMPL_REUSE, DEF_RETURN, DELTA_GOV, RECUR_BUDGET, REPORT_FLOOR, CLI, and consumers."""

    _tmp_base: Path
    _b_ready_template: Path
    _a_only_template: Path
    _b_ready_recovery: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_base = Path(tempfile.mkdtemp(prefix="b_route_defect_routing_"))
        cls._b_ready_template = cls._tmp_base / "b_ready_tpl"
        cls._b_ready_template.mkdir(parents=True, exist_ok=True)
        _build_b_route_base_repo(cls._b_ready_template, mode="flow", binding_stage="5", include_planned=True)
        _reconcile_task_ready(cls._b_ready_template, task_id=101, mode="flow", include_planned=True)
        cls._b_ready_recovery = ch6_rec.evaluate_chapter6_recovery(
            cls._b_ready_template,
            101,
            operation="defect_routing",
            recommendation_only=True,
            consumer="b_route_defect_routing",
            lock_mode="none",
        )

        cls._a_only_template = cls._tmp_base / "a_only_tpl"
        cls._a_only_template.mkdir(parents=True, exist_ok=True)
        _build_explicit_not_enabled_a_repo(cls._a_only_template)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp_base, ignore_errors=True)

    def _clone_b_ready(self) -> Path:
        dest = Path(tempfile.mkdtemp(prefix="case_b_", dir=str(self._tmp_base)))
        shutil.copytree(self._b_ready_template, dest, dirs_exist_ok=True)
        return dest

    def _clone_a_only(self) -> Path:
        dest = Path(tempfile.mkdtemp(prefix="case_a_", dir=str(self._tmp_base)))
        shutil.copytree(self._a_only_template, dest, dirs_exist_ok=True)
        return dest

    def _assert_valid_diagnostics(self, diags: list[dict]) -> None:
        self.assertTrue(len(diags) >= 1)
        for diag in diags:
            self.assertEqual(set(diag.keys()), DIAGNOSTIC_KEYS)
            self.assertIn(diag["reason_code"], {rc.value for rc in codec.ReasonCode})

    # ------------------------------------------------------------------
    # AC-1: IMPL_REUSE
    # ------------------------------------------------------------------
    def test_ac1_impl_reuse_pure_implementation_admitted_zero_writes(self) -> None:
        root = self._clone_b_ready()
        before = _tree_snapshot(root)
        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={
                "changed_paths": [
                    "Game.Core/Services/RewardService.cs",
                    "Game.Core.Tests/Reward/RewardFlowTests.cs",
                ],
                "gap_categories": ["pure_implementation"],
            },
        )
        self.assertEqual(_tree_snapshot(root), before)
        self.assertTrue(res["ok"])
        self.assertEqual(res["defect_class"], "pure_implementation")
        self.assertEqual(res["action"], "local_repair")
        self.assertTrue(res["local_repair_allowed"])
        self.assertFalse(res["reruns_3a_3b"])
        self.assertIsNone(res["owning_stage"])
        self.assertTrue(res["plan_refs"])
        self.assertTrue(res["binding_refs"])
        self.assertIn("flow-reward-select", res["applicable_flow_closure"])
        self.assertTrue(str(res["input_set_digest"]).startswith("sha256:"))
        self.assertTrue(res["readiness_path"])
        self.assertTrue(res["required_local_self_checks"])
        self.assertIn("Game.Core.Tests/Reward/RewardFlowTests.cs", res["required_applicable_regressions"])
        self.assertIn("Pure implementation defect", res["classification_rationale"])
        self.assertTrue(res["upstream_reuse"]["upstream_reused"])
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])
        self.assertFalse(res["flow_completed"])
        self.assertFalse(res["cumulative_milestone_completed"])

    def test_ac1_blocks_skip_readiness_skip_regressions_and_blind_3a_3b_rerun(self) -> None:
        root = self._b_ready_template
        for flag, expected_reason in (
            ("skip_readiness", "cannot_skip_chapter5_readiness"),
            ("skip_regressions", "cannot_skip_applicable_regressions"),
            ("force_rerun_3a_3b", "blind_3a_3b_rerun_forbidden_for_pure_impl"),
        ):
            with self.subTest(flag=flag):
                res = defect_routing.evaluate_defect_routing(
                    root,
                    101,
                    defect_input={
                        "changed_paths": ["Game.Core/Services/RewardService.cs"],
                        flag: True,
                    },
                    recovery_result=self._b_ready_recovery,
                )
                self.assertFalse(res["ok"])
                self.assertFalse(res["local_repair_allowed"])
                self.assertFalse(res["reruns_3a_3b"])
                self.assertEqual(res["reason"], expected_reason)
                self._assert_valid_diagnostics(res["diagnostics"])

    def test_ac1_blocks_pure_impl_when_chapter5_readiness_missing(self) -> None:
        root = self._clone_b_ready()
        rdy = root / "logs/ci/chapter5/readiness/task-101.json"
        if rdy.is_file():
            rdy.unlink()
        latest_rdy = root / "logs/ci/chapter5/readiness/latest.json"
        if latest_rdy.is_file():
            latest_rdy.unlink()
        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={"changed_paths": ["Game.Core/Services/RewardService.cs"]},
        )
        self.assertFalse(res["ok"])
        self.assertFalse(res["local_repair_allowed"])
        self.assertEqual(res["return_stage"], "5")
        self.assertEqual(res["action"], "return_to_owning_stage")
        self.assertIsNotNone(res["governed_handoff"])
        self.assertEqual(res["governed_handoff"]["owning_stage"], "5")
        self._assert_valid_diagnostics(res["diagnostics"])

    # ------------------------------------------------------------------
    # AC-2: DEF_RETURN & Anti-Disguise Guards
    # ------------------------------------------------------------------
    def test_ac2_definition_and_contract_changes_return_exact_owning_stage(self) -> None:
        root = self._b_ready_template
        cases = [
            ({"changed_paths": ["sources/reward-gdd.md"]}, "3A", "b-route-sources"),
            ({"gap_categories": ["state_ownership"]}, "3B", "b-route-adoption"),
            ({"gap_categories": ["non_flow_applicability"]}, "3B", "b-route-adoption"),
            ({"gap_categories": ["task_mapping"]}, "3C", "b-route-task-preview"),
            ({"changed_paths": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"]}, "4", "b-route-chapter4-binding"),
            ({"changed_paths": ["docs/adr/ADR-0004-event-bus-and-contracts.md"]}, "4", "b-route-chapter4-binding"),
            ({"changed_paths": ["docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"]}, "4", "b-route-chapter4-binding"),
            ({"changed_paths": ["docs/testing/mvg/reward-baseline.json"]}, "5", "b-route-chapter5-readiness"),
        ]
        for defect_in, expected_stage, expected_cmd_token in cases:
            with self.subTest(defect_in=defect_in):
                res = defect_routing.evaluate_defect_routing(
                    root, 101, defect_input=defect_in, recovery_result=self._b_ready_recovery
                )
                self.assertFalse(res["ok"])
                self.assertFalse(res["local_repair_allowed"])
                self.assertEqual(res["defect_class"], "definition_or_contract_change")
                self.assertEqual(res["owning_stage"], expected_stage)
                self.assertEqual(res["return_stage"], expected_stage)
                self.assertEqual(res["action"], "return_to_owning_stage")
                handoff = res["governed_handoff"]
                self.assertEqual(handoff["schema_version"], defect_routing.DEFECT_REPORT_SCHEMA)
                self.assertEqual(handoff["owning_stage"], expected_stage)
                self.assertIn(expected_cmd_token, handoff["entrypoint_command"])
                self.assertFalse(handoff["auto_reruns_upstream"])
                self._assert_valid_diagnostics(res["diagnostics"])

    def test_ac2_anti_disguise_rejects_weakened_acceptance_na_done_flip_deleted_and_skipped_tests_and_mvg_weakening(self) -> None:
        # 1. Weakened acceptance / removed Refs:
        root = self._b_ready_template
        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={
                "proposed_task_edits": {
                    "acceptance": ["Produce reward offer without test ref."],
                }
            },
            recovery_result=self._b_ready_recovery,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["defect_class"], "disguised_definition_change")
        self.assertIn("acceptance_weakened_or_deleted", res["governed_handoff"]["disguise_violations"])
        self._assert_valid_diagnostics(res["diagnostics"])

        # 2. Free-text N/A / mvg_applicable=false / flow_applicable=false
        res_na = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={
                "proposed_task_edits": {
                    "mvg_applicable": False,
                    "labels": ["mvg:N/A"],
                }
            },
            recovery_result=self._b_ready_recovery,
        )
        self.assertFalse(res_na["ok"])
        self.assertEqual(res_na["defect_class"], "disguised_definition_change")
        self.assertIn("free_text_na_exemption", res_na["governed_handoff"]["disguise_violations"])
        self.assertEqual(res_na["diagnostics"][0]["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)

        # 3. Illegal status flip to done while failing
        res_done = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={
                "local_verification": {"status": "failed"},
                "proposed_task_edits": {"status": "done"},
            },
            recovery_result=self._b_ready_recovery,
        )
        self.assertFalse(res_done["ok"])
        self.assertEqual(res_done["defect_class"], "disguised_definition_change")
        self.assertIn("illegal_status_done_flip", res_done["governed_handoff"]["disguise_violations"])

        # 4. Deleted bound test file (real live disk mutation)
        root_del = self._clone_b_ready()
        (root_del / "Game.Core.Tests/Reward/RewardFlowTests.cs").unlink()
        res_del = defect_routing.evaluate_defect_routing(root_del, 101, recovery_result=self._b_ready_recovery)
        self.assertFalse(res_del["ok"])
        self.assertEqual(res_del["defect_class"], "disguised_definition_change")
        self.assertIn("bound_test_deleted", res_del["governed_handoff"]["disguise_violations"])

        # 5. [Fact(Skip=...)] on bound test file (real live disk mutation)
        root_skip = self._clone_b_ready()
        _put(
            root_skip,
            "Game.Core.Tests/Reward/RewardFlowTests.cs",
            'public class RewardFlowTests { [Fact(Skip = "temporary")] public void Works() {} }\n',
        )
        res_skip = defect_routing.evaluate_defect_routing(root_skip, 101, recovery_result=self._b_ready_recovery)
        self.assertFalse(res_skip["ok"])
        self.assertEqual(res_skip["defect_class"], "disguised_definition_change")
        self.assertIn("bound_test_skipped_or_disabled", res_skip["governed_handoff"]["disguise_violations"])

        # 6. Weakening cumulative MVG manifest (_weakens_baseline)
        manifest = json.loads((root / "docs/testing/mvg/reward-baseline.json").read_text(encoding="utf-8"))
        weakened = json.loads(json.dumps(manifest))
        weakened["tests"][0]["min_tests"] = 0
        weakened["flows"][0]["test_ids"] = []
        res_mvg = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={"proposed_manifest": weakened},
            recovery_result=self._b_ready_recovery,
        )
        self.assertFalse(res_mvg["ok"])
        self.assertEqual(res_mvg["defect_class"], "disguised_definition_change")
        self.assertIn("mvg_manifest_weakened", res_mvg["governed_handoff"]["disguise_violations"])

    # ------------------------------------------------------------------
    # AC-3: DELTA_GOV
    # ------------------------------------------------------------------
    def test_ac3_delta_governance_accepts_genuine_gap_without_writing_triplet(self) -> None:
        root = self._clone_b_ready()
        before = _tree_snapshot(root)
        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            delta_intents={
                "plan_id": "plan-reward",
                "scope_id": "reward-scope",
                "audit_ref": "logs/ci/b-route-source-audit/latest.json",
                "source_or_definition_changed": True,
                "deltas": [
                    {
                        "action": "create",
                        "view": "back",
                        "title": "Persist deterministic reward reroll audit trail",
                        "flow_ids": ["flow-reward-select"],
                        "new_requirement_ids": ["REQ-REWARD-REROLL-AUDIT-2"],
                        "part_kinds": ["domain_rules"],
                        "role": "producer",
                        "responsibilities": ["Record deterministic reward reroll seed transitions for replay auditing."],
                    }
                ],
            },
            recovery_result=self._b_ready_recovery,
        )
        # Strictly zero writes!
        self.assertEqual(_tree_snapshot(root), before)
        self.assertFalse(res["local_repair_allowed"])
        self.assertEqual(res["owning_stage"], "3C")
        dg = res["delta_governance"]
        self.assertTrue(dg["ok"])
        self.assertFalse(dg["task_triplet_written"])
        self.assertFalse(dg["permanent_task_ids_allocated"])
        self.assertFalse(dg["old_done_covers_new_obligations"])
        self.assertTrue(dg["requires_chapter6_reverification"])
        self.assertEqual(len(dg["accepted_deltas"]), 1)
        self.assertTrue(dg["accepted_deltas"][0]["candidate_key"].startswith("cand:"))
        self.assertIsNone(dg["accepted_deltas"][0]["permanent_task_id"])
        self.assertIn(101, dg["invalidated_readiness_tasks"])
        self.assertIn(102, dg["invalidated_readiness_tasks"])
        self.assertTrue(any("b-route-task-preview" in cmd for cmd in dg["governance_handoff_commands"]))
        self.assertTrue(any("b-route-task-compile" in cmd for cmd in dg["governance_handoff_commands"]))

    def test_ac3_delta_governance_blocks_synonymous_duplicate_direct_write_and_old_done_masking(self) -> None:
        root = self._clone_b_ready()

        # 1. Synonymous duplicate repair task
        dup = defect_routing.validate_repair_task_delta(
            root,
            101,
            {
                "deltas": [
                    {
                        "action": "create",
                        "view": "back",
                        "title": "Fix bug in reward producer task",
                        "flow_ids": ["flow-reward-select"],
                        "requirement_ids": ["REQ-REWARD-1"],
                        "part_kinds": ["domain_rules"],
                        "role": "producer",
                        "responsibilities": ["Fix reward offer producer defect."],
                    }
                ]
            },
        )
        self.assertFalse(dup["ok"])
        self.assertTrue(dup["synonymous_duplicates_blocked"])
        self.assertEqual(dup["diagnostics"][0]["reason_code"], codec.ReasonCode.DUPLICATE_OWNER.value)
        self._assert_valid_diagnostics(dup["diagnostics"])

        # 2. Direct triplet write / permanent ID allocation / old done covering new obligations
        bad = defect_routing.validate_repair_task_delta(
            root,
            101,
            {
                "direct_triplet_write": True,
                "allocate_permanent_id": True,
                "deltas": [
                    {
                        "action": "update",
                        "task_id": 101,
                        "use_old_done_for_new_obligations": True,
                        "responsibilities": ["New obligation covered by old done."],
                    }
                ],
            },
        )
        self.assertFalse(bad["ok"])
        self.assertFalse(bad["task_triplet_written"])
        self.assertFalse(bad["old_done_covers_new_obligations"])
        self.assertTrue(bad["requires_chapter6_reverification"])
        self._assert_valid_diagnostics(bad["diagnostics"])

    # ------------------------------------------------------------------
    # AC-4: RECUR_BUDGET
    # ------------------------------------------------------------------
    def test_ac4_recurrence_pinpointing_upstream_reuse_and_anti_masking(self) -> None:
        root = self._clone_b_ready()
        _create_pipeline_run(
            root,
            101,
            "run-rec-1",
            date_str="2026-11-23",
            status="fail",
            reason="deterministic_test_failure",
            failed_step="sc-test",
            max_step_retries=1,
            step_attempts=2,
            diagnostics={"rerun_guard": {"blocked": True, "reason": "repeat_deterministic_failure"}},
        )
        _create_pipeline_run(
            root,
            101,
            "run-rec-2",
            date_str="2026-11-24",
            status="fail",
            reason="deterministic_test_failure",
            failed_step="sc-test",
            max_step_retries=1,
            step_attempts=2,
            diagnostics={"rerun_guard": {"blocked": True, "reason": "repeat_deterministic_failure"}},
        )

        # Unrelated task status change in tasks.json (task 201 pending -> in-progress) must NOT invalidate task 101 upstream!
        tasks_doc = json.loads((root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        for row in tasks_doc["master"]["tasks"]:
            if int(row["id"]) == 201:
                row["status"] = "in-progress"
        _put_json(root, ".taskmaster/tasks/tasks.json", tasks_doc)

        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            defect_input={"changed_paths": ["Game.Core/Services/RewardService.cs"]},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["upstream_reuse"]["upstream_reused"])
        self.assertFalse(res["reruns_3a_3b"])
        rec = res["recurrence_analysis"]
        self.assertTrue(rec["recurrence_detected"])
        self.assertGreaterEqual(rec["recurrence_count"], 2)
        self.assertEqual(rec["recurring_failure_signature"], "sc-test|deterministic_test_failure")
        self.assertEqual(rec["durable_failed_runs"], 2)
        self.assertGreaterEqual(rec["cumulative_step_retries"], 4)
        self.assertTrue(rec["budget_preserved"])
        self.assertTrue(rec["rerun_guard_active"])
        self.assertTrue(rec["candidate_generation_masking_blocked"])
        self.assertEqual(rec["global_knowledge_refresh"], "forbidden")
        self.assertEqual(rec["return_stage"], "6")
        self.assertFalse(res["flow_completed"])
        self.assertFalse(res["cumulative_milestone_completed"])

        # Anti-masking & anti-impersonation flags must block!
        for flag in (
            "request_candidate_regeneration",
            "request_global_knowledge_refresh",
            "claim_flow_completed",
            "claim_cumulative_milestone_completed",
        ):
            with self.subTest(flag=flag):
                blocked = defect_routing.evaluate_defect_routing(
                    root, 101, defect_input={flag: True}, recovery_result=self._b_ready_recovery
                )
                self.assertFalse(blocked["ok"])
                self.assertFalse(blocked["local_repair_allowed"])
                self._assert_valid_diagnostics(blocked["diagnostics"])

    # ------------------------------------------------------------------
    # AC-5: REPORT_FLOOR
    # ------------------------------------------------------------------
    def test_ac5_honest_verification_breakdown_p1_floor_and_telemetry(self) -> None:
        root = self._clone_b_ready()
        run_dir = _create_pipeline_run(
            root,
            101,
            "run-p1-check",
            status="ok",
            reason="pipeline_clean",
            low_priority_review=True,
        )
        res = defect_routing.evaluate_defect_routing(
            root,
            101,
            run_dir=run_dir,
            fix_through="P1",
            defect_input={
                "changed_paths": ["Game.Core/Services/RewardService.cs"],
                "local_verification": {
                    "status": "passed",
                    "executed_tests": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
                },
                "review_findings": [
                    {"finding_id": "rev-p1-1", "severity": "P1", "status": "open", "message": "Null guard missing."},
                    {"finding_id": "rev-p2-1", "severity": "P2", "status": "open", "message": "Naming polish."},
                ],
            },
        )
        self.assertTrue(res["ok"])
        vb = res["verification_breakdown"]
        self.assertEqual(vb["local_verification"]["status"], "passed")
        self.assertEqual(vb["runtime_verification"]["status"], "pending")
        self.assertFalse(vb["runtime_verification"]["runtime_verified"])
        self.assertEqual(vb["manual_obligations"]["status"], "pending")
        self.assertIn("Manual animation polish verified separately.", vb["manual_obligations"]["items"])
        inc_kinds = {item["kind"] for item in vb["incomplete_obligations"]}
        self.assertIn("planned_test", inc_kinds)
        self.assertIn("runtime_mvg_verification", inc_kinds)
        self.assertIn("manual_obligation", inc_kinds)

        nf = res["needs_fix_policy"]
        self.assertEqual(nf["fix_through"], "P1")
        self.assertTrue(nf["p1_floor_enforced"])
        self.assertTrue(nf["has_blocking_findings"])
        self.assertEqual(nf["must_fix_blocking_findings"][0]["severity"], "P1")
        self.assertTrue(any(f["severity"] == "P2" for f in nf["deferrable_findings"]))

        metrics = res["metrics"]
        self.assertGreaterEqual(metrics["active_elapsed_seconds"], 0.0)
        self.assertEqual(metrics["model_invocation_count"], 0)
        self.assertGreaterEqual(metrics["durable_model_invocation_count"], 1)
        self.assertGreater(metrics["reused_upstream_artifacts"], 0)
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])

        # Reject P0 below P1 must-fix floor!
        res_p0 = defect_routing.evaluate_defect_routing(
            root, 101, fix_through="P0", recovery_result=self._b_ready_recovery
        )
        self.assertFalse(res_p0["ok"])
        self.assertEqual(res_p0["reason"], "fix_through_below_p1_floor")
        self.assertEqual(res_p0["diagnostics"][0]["reason_code"], codec.ReasonCode.INVALID_ENUM.value)

        # Reject claiming runtime_verified=True
        res_rt = defect_routing.evaluate_defect_routing(
            root, 101, defect_input={"claim_runtime_verified": True}, recovery_result=self._b_ready_recovery
        )
        self.assertFalse(res_rt["ok"])
        self.assertFalse(res_rt["runtime_verified"])

    # ------------------------------------------------------------------
    # CLI, Builder, & Chapter 6 Consumer Wiring
    # ------------------------------------------------------------------
    def test_cli_builder_and_report_writing_end_to_end(self) -> None:
        root = self._clone_b_ready()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dev_cli.main(["b-route-defect-routing", "--root", str(root), "--task-id", "101"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["schema_version"], defect_routing.SCHEMA)
        self.assertEqual(payload["defect_class"], "pure_implementation")
        self.assertFalse(payload["runtime_verified"])
        self.assertFalse(payload["default_b_enabled"])

        # Write report to new logs/ci path
        report_rel = "logs/ci/2026-11-24/defect-routing-101.json"
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = defect_cli.main(["--root", str(root), "--task-id", "101", "--report", report_rel])
        self.assertEqual(rc2, 0)
        self.assertTrue((root / report_rel).is_file())

        # Reject unsafe report path outside logs/ci
        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = defect_cli.main(["--root", str(root), "--task-id", "101", "--report", "docs/bad.json"])
        self.assertEqual(rc3, 2)

        # Builder rejects write/apply flags
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_defect_routing_cmd(
                types.SimpleNamespace(root=".", task_id="101", write=True, apply=False)
            )
        cmd = dev_cli_builders.build_b_route_defect_routing_cmd(
            types.SimpleNamespace(
                root=".",
                task_id="101",
                run_dir=None,
                defect_input=None,
                delta_intents=None,
                fix_through="P1",
                report=None,
            )
        )
        self.assertIn("--task-id", cmd)
        self.assertIn("101", cmd)

    def test_chapter6_consumers_attach_defect_routing_on_b_and_preserve_explicit_a(self) -> None:
        # 1. B-route task: resume_task & chapter6_route attach b_route_defect_routing; contract edit routes to owning stage 4!
        root_b = self._clone_b_ready()
        run_dir = _create_pipeline_run(root_b, 101, "run-c6-1", status="fail", reason="step_failed", failed_step="sc-test")
        # Inject changed contract path into execution-context.json
        ctx_path = run_dir / "execution-context.json"
        ctx_doc = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx_doc["changed_paths"] = ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"]
        ctx_path.write_text(json.dumps(ctx_doc, indent=2) + "\n", encoding="utf-8")

        _rc_res, res_payload = resume_task.build_resume_payload(
            repo_root=root_b,
            task_id="101",
            latest="",
            run_id="",
            recommendation_only=True,
        )
        self.assertIn("b_route_defect_routing", res_payload)
        self.assertEqual(res_payload["b_route_defect_routing"]["owning_stage"], "4")
        self.assertFalse(res_payload["b_route_defect_routing"]["local_repair_allowed"])

        rc_route, route_payload = chapter6_route.route_chapter6(
            repo_root=root_b,
            task_id="101",
            recommendation_only=True,
        )
        self.assertEqual(rc_route, 3)
        self.assertEqual(route_payload["preferred_lane"], "return-to-owning-stage")
        self.assertEqual(route_payload["blocked_by"], "b_route_defect_routing")
        self.assertEqual(route_payload["return_stage"], "4")
        self.assertFalse(route_payload["execution_allowed"])
        self.assertIn("b-route-chapter4-binding", route_payload["recommended_command"])

        # 2. Pure explicit_not_enabled_a repo stays zero-write and does not attach B-only fields
        root_a = self._clone_a_only()
        _create_pipeline_run(root_a, 11, "run-a-1", status="ok", reason="pipeline_clean")
        before_a = _tree_snapshot(root_a)
        rc_a, payload_a = resume_task.build_resume_payload(
            repo_root=root_a,
            task_id="11",
            latest="",
            run_id="",
            recommendation_only=True,
        )
        self.assertEqual(rc_a, 0)
        self.assertNotIn("b_route_defect_routing", payload_a)
        self.assertEqual(_tree_snapshot(root_a), before_a)

    # ------------------------------------------------------------------
    # Step 4 Patch Regressions (P-01 .. P-06)
    # ------------------------------------------------------------------
    def test_p01_p02_norm_rel_binding_stage_path_containment_and_report_path_on_disk(self) -> None:
        root = self._clone_b_ready()

        # P-01: _norm_rel preserves leading dots (never strips "." from .taskmaster / .github)
        self.assertEqual(defect_routing._norm_rel(".taskmaster/tasks/tasks.json"), ".taskmaster/tasks/tasks.json")
        self.assertEqual(defect_routing._norm_rel("./.taskmaster/docs//prd.txt"), ".taskmaster/docs/prd.txt")
        self.assertEqual(defect_routing._norm_rel(".github/workflows/ci.yml"), ".github/workflows/ci.yml")
        self.assertEqual(defect_routing._classify_path(".taskmaster/tasks/tasks.json"), ("definition", "3C"))
        self.assertEqual(defect_routing._classify_path(".taskmaster/docs/prd.txt"), ("definition", "3A"))
        self.assertEqual(defect_routing._classify_path(".github/workflows/ci.yml"), ("pure_implementation", "6"))

        # P-01: binding stage classification inspects actual binding stage (3C / 4 / 5)
        for stg in ("3C", "4", "5"):
            brel = f"docs/planning/b-route/bindings/stage-{stg.lower()}-sample.json"
            _put_json(root, brel, {"schema_version": "newrouge.b-route-binding.v1", "stage": stg})
            self.assertEqual(defect_routing._classify_path(brel, root_path=root), ("definition", stg))
            (root / brel).unlink()

        # P-02: absolute path outside root_path rejected with UNSAFE_PATH for defect_input, delta_intents, and run_dir
        outside_dir = Path(tempfile.mkdtemp(prefix="outside_p02_", dir=str(self._tmp_base)))
        outside_json = outside_dir / "escape.json"
        outside_json.write_text('{"changed_paths": []}\n', encoding="utf-8")
        res_out_di = defect_routing.evaluate_defect_routing(root, 101, defect_input=str(outside_json))
        self.assertFalse(res_out_di["ok"])
        self.assertEqual(res_out_di["reason_code"], codec.ReasonCode.UNSAFE_PATH.value)

        res_out_rd = defect_routing.evaluate_defect_routing(root, 101, run_dir=str(outside_dir))
        self.assertFalse(res_out_rd["ok"])
        self.assertEqual(res_out_rd["reason_code"], codec.ReasonCode.UNSAFE_PATH.value)

        # P-02: --report writes non-null report_path inside JSON on disk
        report_rel = "logs/ci/2026-11-24/defect-routing-p02-101.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = defect_cli.main(["--root", str(root), "--task-id", "101", "--report", report_rel])
        self.assertEqual(rc, 0)
        disk_payload = json.loads((root / report_rel).read_text(encoding="utf-8"))
        self.assertEqual(disk_payload["report_path"], report_rel)
        stdout_payload = json.loads(buf.getvalue())
        self.assertEqual(stdout_payload["report_path"], report_rel)

    def test_p03_nonflow_manifest_scoping_dual_view_and_advanced_skip_or_gutted_tests(self) -> None:
        # 1. Non-Flow task with empty manifest_paths must NOT inherit unrelated docs/testing/mvg/*.json tests
        root_nf = Path(tempfile.mkdtemp(prefix="case_nf_", dir=str(self._tmp_base)))
        _build_b_route_base_repo(root_nf, mode="nonflow", binding_stage="5", include_planned=False)
        _reconcile_task_ready(root_nf, task_id=101, mode="nonflow", include_planned=False)
        res_nf = defect_routing.evaluate_defect_routing(
            root_nf,
            101,
            defect_input={"changed_paths": ["Game.Core/Services/RewardService.cs"]},
        )
        self.assertTrue(res_nf["ok"])
        self.assertEqual(res_nf["applicable_flow_closure"], [])
        self.assertNotIn("Game.Core.Tests/Reward/RewardFlowTests.cs", res_nf["required_applicable_regressions"])
        self.assertIn("docs/testing/nonflow-checklist.md", res_nf["required_applicable_regressions"])

        # 2. Dual-view (back + gameplay) catches acceptance weakening on gameplay_task
        root_dv = self._clone_b_ready()
        gp_rows = [
            {
                "id": "GM-0101",
                "taskmaster_id": 101,
                "title": "Reward producer gameplay view",
                "status": "in-progress",
                "acceptance": [
                    "Display locked reward card cleanly. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs",
                ],
                "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
            }
        ]
        _put_json(root_dv, ".taskmaster/tasks/tasks_gameplay.json", gp_rows)
        res_dv = defect_routing.evaluate_defect_routing(
            root_dv,
            101,
            defect_input={
                "proposed_task_edits": {
                    "view": "gameplay",
                    "acceptance": ["Weakened gameplay acceptance without ref."],
                }
            },
            recovery_result=self._b_ready_recovery,
        )
        self.assertFalse(res_dv["ok"])
        self.assertEqual(res_dv["defect_class"], "disguised_definition_change")
        self.assertIn("acceptance_weakened_or_deleted", res_dv["governed_handoff"]["disguise_violations"])
        self.assertEqual(res_dv["diagnostics"][0]["resume_ref"], ".taskmaster/tasks/tasks_gameplay.json")

        # 3. Stacked [Theory, Fact(Skip="...")], Assert.Skip(...), #if false, and gutted empty test files
        sabotage_cases = [
            ("stacked_skip", 'public class RewardFlowTests { [Theory, Fact(Skip = "bypass")] public void T() {} }\n', "bound_test_skipped_or_disabled"),
            ("assert_skip", 'public class RewardFlowTests { [Fact] public void T() { Assert.Skip("later"); } }\n', "bound_test_skipped_or_disabled"),
            ("if_false", '#if false\npublic class RewardFlowTests { [Fact] public void T() {} }\n#endif\n', "bound_test_skipped_or_disabled"),
            ("gutted_empty", "   \n// removed all tests\n", "bound_test_gutted_or_empty"),
            ("gutted_xunit", "using Xunit;\npublic class RewardFlowTests {}\n", "bound_test_gutted_or_empty"),
        ]
        for label, content, expected_kind in sabotage_cases:
            with self.subTest(sabotage=label):
                root_s = self._clone_b_ready()
                _put(root_s, "Game.Core.Tests/Reward/RewardFlowTests.cs", content)
                res_s = defect_routing.evaluate_defect_routing(root_s, 101, recovery_result=self._b_ready_recovery)
                self.assertFalse(res_s["ok"])
                self.assertEqual(res_s["defect_class"], "disguised_definition_change")
                self.assertIn(expected_kind, res_s["governed_handoff"]["disguise_violations"])

    def test_p04_create_delta_stuffing_existing_req_into_new_requirement_ids_still_blocked(self) -> None:
        root = self._clone_b_ready()
        # Even with gate_res=None, catalog + active bindings populate REQ-REWARD-1 on task 101!
        dup = defect_routing.validate_repair_task_delta(
            root,
            101,
            {
                "operations": [
                    {
                        "action": "create",
                        "view": "back",
                        "title": "Reward producer follow-up",
                        "flow_ids": ["flow-reward-select"],
                        "new_requirement_ids": ["REQ-REWARD-1"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "responsibilities": ["Re-implement existing reward producer requirement."],
                    }
                ]
            },
        )
        self.assertFalse(dup["ok"])
        self.assertTrue(dup["synonymous_duplicates_blocked"])
        self.assertEqual(dup["diagnostics"][0]["reason_code"], codec.ReasonCode.DUPLICATE_OWNER.value)

    def test_p05_ok_run_clears_stale_history_and_must_fix_findings_enter_incomplete_obligations(self) -> None:
        root = self._clone_b_ready()
        # Earlier failed run touched a contract file and had an open P1 finding
        fail_dir = _create_pipeline_run(
            root,
            101,
            "run-p05-fail",
            date_str="2026-11-23",
            status="fail",
            reason="step_failed",
            failed_step="sc-test",
        )
        fail_ctx = json.loads((fail_dir / "execution-context.json").read_text(encoding="utf-8"))
        fail_ctx["changed_paths"] = ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"]
        (fail_dir / "execution-context.json").write_text(json.dumps(fail_ctx, indent=2) + "\n", encoding="utf-8")
        (fail_dir / "agent-review.json").write_text(
            json.dumps({"findings": [{"finding_id": "old-p1", "severity": "P1", "status": "open", "message": "Old issue"}]}),
            encoding="utf-8",
        )

        # Later clean ok run has no changed contract paths and no open findings
        ok_dir = _create_pipeline_run(
            root,
            101,
            "run-p05-ok",
            date_str="2026-11-24",
            status="ok",
            reason="pipeline_clean",
        )
        res_clean = defect_routing.evaluate_defect_routing(
            root,
            101,
            run_dir=ok_dir,
            defect_input={"changed_paths": ["Game.Core/Services/RewardService.cs"]},
        )
        self.assertTrue(res_clean["ok"])
        self.assertTrue(res_clean["local_repair_allowed"])
        self.assertEqual(res_clean["needs_fix_policy"]["must_fix_blocking_findings"], [])

        # Passing an open P1 finding must appear in incomplete_obligations
        res_p1 = defect_routing.evaluate_defect_routing(
            root,
            101,
            run_dir=ok_dir,
            fix_through="P1",
            defect_input={
                "changed_paths": ["Game.Core/Services/RewardService.cs"],
                "review_findings": [
                    {"finding_id": "p1-must-fix", "severity": "P1", "status": "open", "message": "Must fix before close."}
                ],
            },
        )
        inc = res_p1["verification_breakdown"]["incomplete_obligations"]
        self.assertTrue(
            any(
                item.get("kind") == "needs_fix_blocking_finding"
                and item.get("finding_id") == "p1-must-fix"
                and item.get("status") == "blocked"
                for item in inc
            )
        )

        # build_chapter6_handoff_summary includes complete handoff fields
        handoff_sum = defect_routing.build_chapter6_handoff_summary(root, 101, run_dir=ok_dir)
        for key in (
            "plan_refs",
            "binding_refs",
            "applicable_flow_ids",
            "readiness_path",
            "required_local_self_checks",
            "required_applicable_regressions",
            "upstream_reuse",
            "verification_breakdown",
            "delta_governance",
            "return_stage",
            "resume_ref",
        ):
            self.assertIn(key, handoff_sum)

    def test_p06_end_to_end_consumers_block_skip_attribute_fail_closed(self) -> None:
        root = self._clone_b_ready()
        _create_pipeline_run(
            root,
            101,
            "run-p06-1",
            status="ok",
            reason="pipeline_clean",
            low_priority_review=True,
        )
        # Plant [Fact(Skip="bypass")] on bound test file
        _put(
            root,
            "Game.Core.Tests/Reward/RewardFlowTests.cs",
            'public class RewardFlowTests { [Fact(Skip = "bypass")] public void Works() {} }\n',
        )
        debt_path = root / "docs" / "technical-debt.md"
        debt_before = debt_path.read_bytes()

        # 1. resume_task blocks with rc=2 and return-to-owning-stage + compact fields
        rc_res, res_payload = resume_task.build_resume_payload(
            repo_root=root,
            task_id="101",
            latest="",
            run_id="",
            recommendation_only=True,
        )
        self.assertEqual(rc_res, 2)
        self.assertEqual(res_payload["recommended_action"], "return-to-owning-stage")
        self.assertEqual(res_payload["blocked_by"], "b_route_defect_routing")
        self.assertFalse(res_payload["execution_allowed"])
        self.assertEqual(res_payload["return_stage"], "5")
        self.assertEqual(res_payload["resume_ref"], "Game.Core.Tests/Reward/RewardFlowTests.cs")
        compact_res = resume_task._compact_recommendation_payload(res_payload)
        self.assertEqual(compact_res["return_stage"], "5")
        self.assertEqual(compact_res["resume_ref"], "Game.Core.Tests/Reward/RewardFlowTests.cs")
        self.assertIn("reason_code", compact_res)

        # 2. chapter6_route blocks with rc=3, zero write to technical-debt.md, compact JSON includes 3 fields
        rc_route, route_payload = chapter6_route.route_chapter6(
            repo_root=root,
            task_id="101",
            record_residual=True,
            recommendation_only=False,
        )
        self.assertEqual(rc_route, 3)
        self.assertEqual(route_payload["blocked_by"], "b_route_defect_routing")
        self.assertEqual(route_payload["preferred_lane"], "return-to-owning-stage")
        self.assertFalse(route_payload["execution_allowed"])
        self.assertEqual(debt_path.read_bytes(), debt_before)
        compact_route = chapter6_route._compact_payload(route_payload)
        self.assertEqual(compact_route["return_stage"], "5")
        self.assertEqual(compact_route["resume_ref"], "Game.Core.Tests/Reward/RewardFlowTests.cs")
        self.assertIn("reason_code", compact_route)
        self.assertTrue(any("--resume" in c for c in route_payload["forbidden_commands"]))
        self.assertTrue(any("--fork" in c for c in route_payload["forbidden_commands"]))

        # 3. run_single_task_chapter6_lane.main() blocks with rc=2 before any step dispatch
        lane_out = root / "logs" / "ci" / "2026-11-24" / "lane-p06-blocked"
        with (
            mock.patch.object(ch6_lane, "_repo_root", return_value=root),
            mock.patch.object(ch6_lane, "_run_cmd", side_effect=AssertionError("steps must not run when blocked")),
            mock.patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--out-dir", str(lane_out)]),
        ):
            buf_lane = io.StringIO()
            with redirect_stdout(buf_lane):
                rc_lane = ch6_lane.main()
        self.assertEqual(rc_lane, 2)
        self.assertIn("stop=b_route_defect_routing:", buf_lane.getvalue())
        lane_summary = json.loads((lane_out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(lane_summary["blocked_by"], "b_route_defect_routing")
        self.assertEqual(lane_summary["steps"], [])

        # 4. run_review_pipeline.py blocks fail-closed before executing steps
        import _active_task_sidecar
        import _marathon_state
        import _pipeline_helpers

        with (
            mock.patch.object(run_review_pipeline, "repo_root", return_value=root),
            mock.patch.object(_pipeline_helpers, "repo_root", return_value=root),
            mock.patch.object(_marathon_state, "repo_root", return_value=root),
            mock.patch.object(_active_task_sidecar, "repo_root", return_value=root),
            mock.patch.object(run_review_pipeline, "current_git_fingerprint", return_value={"head": "abc", "status_short": []}),
            mock.patch.object(run_review_pipeline, "_run_step", side_effect=AssertionError("review steps must not run when blocked")),
            mock.patch.object(sys, "argv", ["run_review_pipeline.py", "--task-id", "101", "--resume"]),
        ):
            buf_rev = io.StringIO()
            with redirect_stdout(buf_rev):
                rc_rev = run_review_pipeline.main()
        self.assertEqual(rc_rev, 12)
        self.assertIn("BLOCKED by b-route-defect-routing", buf_rev.getvalue())


if __name__ == "__main__":
    unittest.main()
