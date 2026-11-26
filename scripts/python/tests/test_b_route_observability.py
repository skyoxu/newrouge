"""Comprehensive deterministic tests for Story 4.8 B-route process observability & unified diagnostics."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path

import _b_route_codec as codec
import _b_route_observability as obs
import _b_route_planning_page as planning_page
import query_b_route_observability as cli
from _b_route_evidence_reuse import append_deduplicated_event
from _project_health_http import handler_factory


ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class BRouteObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _junction_or_skip(self, link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=target.is_dir())
            return
        except OSError:
            if os.name == "nt" and target.is_dir():
                proc = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0 and os.path.lexists(link):
                    return
            self.skipTest("symlink/junction creation not permitted")

    # ------------------------------------------------------------------
    # AC-1: 5-axis aggregation, raw evidence backlinks & strict single-counting
    # ------------------------------------------------------------------
    def test_ac1_five_axis_aggregation_dedup_retries_and_dispatch_correlation(self) -> None:
        # 3A source audit
        sha_3a = _write_json(
            self.root / "logs/ci/2026-11-26/b-route-source-audit/run-3a-1/attempt-1/report.json",
            {
                "schema_version": "newrouge.b-route-sources-report.v1",
                "run_id": "run-3a-1",
                "scope_id": "scope-alpha",
                "stage": "audit",
                "attempt_id": "attempt-1",
                "status": "ok",
                "planning_eligible": True,
                "active_elapsed_seconds": 12.5,
                "runner": "codex-isolated",
            },
        )
        # 3B planning run with 2 reservations, 1 worker projection, and 1 actual dispatch receipt
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-1/run.json",
            {
                "run_id": "run-3b-1",
                "scope_id": "scope-alpha",
                "selection_status": "in_progress",
                "request_budget": 16,
                "logical_reserved_calls": 2,
                "reservations": [
                    {"number": 1, "request_identity": "req-001"},
                    {"number": 2, "request_identity": "req-002"},
                ],
                "started_at": "2026-11-26T00:00:00+00:00",
                "finished_at": "2026-11-26T01:00:00+00:00",
            },
        )
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-1/candidates/candidate-1/projection.json",
            {"number": 1, "request_identity": "req-001", "candidate_id": "cand-1"},
        )
        sha_disp = _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-1/dispatch-receipts/dispatch-1.json",
            {
                "number": 1,
                "request_identity": "req-001",
                "status": "ok",
                "runner": "isolated-worker",
                "active_elapsed_seconds": 18.0,
            },
        )
        # 3C preview + Ch6 retry attempts (attempt=1 failed, attempt=2 ok) + Flow receipts with duplicate test execution
        _write_json(
            self.root / "logs/ci/b-route-task-preview/run-3c-1/report.json",
            {
                "schema_version": "newrouge.b-route-task-preview.v1",
                "run_id": "run-3c-1",
                "scope_id": "scope-alpha",
                "status": "ok",
                "active_elapsed_seconds": 3.0,
            },
        )
        _write_json(
            self.root / "logs/ci/mvg-acceptance/mvg-run-1/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "mvg-run-1",
                "scope_id": "scope-alpha",
                "flow_id": "FLOW-ALPHA",
                "snapshot_digest": "sha256:snap1",
                "status": "passed",
                "build_artifacts": {
                    "dotnet_build": {"executed": True, "reused": False},
                    "godot_prewarm": {"executed": False, "reused": True, "reused_from_run_id": "mvg-run-0"},
                },
                "executed_tests": [
                    {"id": "T1", "selector": "Game.Core.Tests.Alpha", "status": "passed", "reused": False},
                ],
                "metrics": {"observed_elapsed_seconds": 5.0, "observed_dispatches": 1, "reserved_dispatches": 1},
            },
        )
        _write_json(
            self.root / "logs/ci/mvg-acceptance/mvg-run-2/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "mvg-run-2",
                "scope_id": "scope-alpha",
                "flow_id": "FLOW-ALPHA",
                "snapshot_digest": "sha256:snap1",
                "status": "passed",
                "build_artifacts": {
                    "dotnet_build": {"executed": False, "reused": True, "reused_from_run_id": "mvg-run-1"},
                    "godot_prewarm": {"executed": True, "reused": False},
                },
                "executed_tests": [
                    {"id": "T1", "selector": "Game.Core.Tests.Alpha", "status": "passed", "reused": False},
                ],
                "metrics": {"observed_elapsed_seconds": 4.0, "observed_dispatches": 1, "reserved_dispatches": 1},
            },
        )

        # Explicit JSONL with duplicate event_id (different recorded_at) AND two distinct retries (attempt=1, attempt=2)
        ev_file = self.root / "logs/ci/events/stage-events.jsonl"
        ev_file.parent.mkdir(parents=True, exist_ok=True)
        dup_base = {
            "event_type": "completion_verdict_evaluated",
            "level": "flow",
            "run_id": "verdict-1",
            "flow_id": "FLOW-ALPHA",
            "attempt": 1,
            "ok": True,
            "verdict_status": "passed",
            "active_elapsed_seconds": 2.0,
        }
        lines = [
            json.dumps({**dup_base, "recorded_at": "2026-11-26T01:00:00Z"}),
            json.dumps({**dup_base, "recorded_at": "2026-11-26T01:05:00Z"}),  # exact duplicate canonical event_id
            json.dumps({**dup_base, "attempt": 2, "recorded_at": "2026-11-26T01:10:00Z"}),  # distinct retry attempt
        ]
        ev_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = obs.build_b_route_observability_report(
            self.root,
            events_logs=["logs/ci/events/stage-events.jsonl"],
        )
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(obs.SCHEMA_VERSION, report["schema_version"])
        self.assertEqual(1, report["deduplicated_duplicate_events_count"])
        self.assertTrue(report["retry_attempts_preserved"])

        # Both verdict attempt=1 and attempt=2 are present, duplicate attempt=1 counted once
        verdict_events = [e for e in report["events"] if e["event_type"] == "completion_verdict_evaluated"]
        self.assertEqual(2, len(verdict_events))
        self.assertEqual({1, 2}, {e["attempt"] for e in verdict_events})

        # Coordinator reservation + worker projection + dispatch-1.json = 1 dispatch (NOT 2 or 3!)
        # Plus 2 mvg-acceptance observed_dispatches = 3 total; req-002 is reserved_only_not_dispatched = 1.
        tc = report["timing_and_cost_summary"]
        self.assertTrue(tc["coordinator_reservation_plus_worker_plus_dispatch_deduplicated"])
        corr_3b = [c for c in tc["correlated_dispatches"] if c["run_id"] == "run-3b-1"]
        disp1 = next(c for c in corr_3b if c["dispatch_key"] == "req-001")
        disp2 = next(c for c in corr_3b if c["dispatch_key"] == "req-002")
        self.assertEqual(1, disp1["counted_as"])
        self.assertTrue(disp1["dispatched"])
        self.assertEqual(3, len(disp1["correlated_sources"]))
        self.assertEqual(sha_disp, disp1["original_locator"]["sha256"])
        self.assertEqual(0, disp2["counted_as"])
        self.assertFalse(disp2["dispatched"])
        self.assertEqual(3, tc["observed_actual_dispatches"])
        self.assertEqual(1, tc["reserved_only_not_dispatched"])

        # Raw evidence backlink matches actual file sha256
        ev_3a = next(e for e in report["events"] if e["stage"] == "3A")
        self.assertEqual(sha_3a, ev_3a["original_locator"]["sha256"])

        # 5-axis indexing present
        axes = report["axes"]
        self.assertIn("run-3a-1", axes["by_operation_or_run_id"])
        self.assertIn("scope-alpha", axes["by_scope_or_flow_id"])
        self.assertIn("3A", axes["by_stage"])
        self.assertIn("3B", axes["by_stage"])
        self.assertIn("3C", axes["by_stage"])
        self.assertIn("flow_verify", axes["by_stage"])
        self.assertIn("attempt-1", axes["by_attempt"])
        self.assertEqual(len(report["events"]), len(axes["by_event_id"]))

        # Build/prewarm counts & duplicate fresh test execution detection
        self.assertEqual(
            {"dotnet_build_executed": 1, "dotnet_build_reused": 1, "godot_prewarm_executed": 1, "godot_prewarm_reused": 1},
            report["build_prewarm_summary"],
        )
        self.assertEqual(1, len(report["duplicate_test_executions"]))
        self.assertEqual("Game.Core.Tests.Alpha", report["duplicate_test_executions"][0]["selector"])
        self.assertEqual(2, report["duplicate_test_executions"][0]["fresh_execution_count"])

    # ------------------------------------------------------------------
    # AC-2: Observed vs paused wall-clock vs reserved vs "unknown", baselines & zero gates
    # ------------------------------------------------------------------
    def test_ac2_observed_vs_paused_reserved_unknown_baselines_and_zero_gates(self) -> None:
        _write_json(
            self.root / "logs/ci/mvg-planning/run-timing/run.json",
            {
                "run_id": "run-timing",
                "scope_id": "scope-t",
                "request_budget": 64,
                "logical_reserved_calls": 5,
                "started_at": "2026-11-26T00:00:00+00:00",
                "finished_at": "2026-11-26T01:00:00+00:00",  # 3600s paused wall-clock
                "estimated_tokens_in": 12000,
                "estimated_tokens_out": 3000,
                "estimated_cost_usd": 0.45,
                "obligation_ids": ["OB-1", "OB-2"],
            },
        )
        for idx, dur in ((1, 12.5), (2, 20.0), (3, 10.0)):
            _write_json(
                self.root / f"logs/ci/mvg-planning/run-timing/dispatch-receipts/dispatch-{idx}.json",
                {"number": idx, "request_identity": f"r-{idx}", "status": "ok", "active_elapsed_seconds": dur},
            )

        # Case 1: No baseline supplied -> unknown, never fabricated
        rep_no_base = obs.build_b_route_observability_report(self.root, run_id="run-timing")
        self.assertTrue(rep_no_base["ok"])
        tc = rep_no_base["timing_and_cost_summary"]
        self.assertEqual(42.5, tc["observed_active_elapsed_seconds"])
        self.assertEqual(3600.0, tc["paused_or_wall_clock_seconds"])
        self.assertFalse(tc["paused_wall_clock_is_active_elapsed"])
        self.assertEqual(64, tc["reserved_request_budget"])
        self.assertEqual(3, tc["observed_actual_dispatches"])
        self.assertEqual(2, tc["reserved_only_not_dispatched"])
        self.assertTrue(tc["model_estimated_metrics"]["estimated_not_billed"])
        self.assertEqual("unknown", tc["billed_cost"])
        self.assertFalse(tc["billed_cost_verified"])

        # Unmeasured run.json event must report "unknown" (never 0.0!)
        run_ev = next(e for e in rep_no_base["events"] if e["event_type"] == "mvg-planning_run")
        self.assertEqual("unknown", run_ev["observed_active_elapsed_seconds"])
        self.assertEqual(1, tc["unmeasured_event_count"])

        # Missing baseline -> unknown, never fabricated
        bc = rep_no_base["baseline_comparison"]
        self.assertFalse(bc["available"])
        self.assertFalse(bc["comparable"])
        self.assertEqual("unknown", bc["status"])
        self.assertEqual("no_comparable_baseline_supplied", bc["reason"])

        # Zero speed/cost/2h/task-count/man-hour gates
        gt = rep_no_base["governance_thresholds"]
        self.assertEqual(
            {
                "speedup_gate_enforced": False,
                "cost_reduction_gate_enforced": False,
                "two_hour_wall_clock_gate_enforced": False,
                "fixed_task_count_gate_enforced": False,
                "man_hour_gate_enforced": False,
            },
            gt,
        )

        # Case 2: Mismatched baseline scope/obligations -> comparable=False
        _write_json(
            self.root / "logs/ci/baselines/mismatch.json",
            {
                "schema_version": obs.SCHEMA_VERSION,
                "scope_id": "scope-OTHER",
                "obligation_ids": ["OB-9"],
                "timing_and_cost_summary": {"observed_active_elapsed_seconds": 100.0, "observed_actual_dispatches": 10},
            },
        )
        rep_mis = obs.build_b_route_observability_report(
            self.root, run_id="run-timing", baseline_ref="logs/ci/baselines/mismatch.json",
        )
        self.assertFalse(rep_mis["baseline_comparison"]["comparable"])
        self.assertEqual("not_comparable", rep_mis["baseline_comparison"]["status"])

        # Case 3a: Matching denominator but incomplete active elapsed -> elapsed delta MUST remain "unknown"
        _write_json(
            self.root / "logs/ci/baselines/match.json",
            {
                "schema_version": obs.SCHEMA_VERSION,
                "scope_id": "scope-t",
                "obligation_ids": ["OB-1", "OB-2"],
                "timing_and_cost_summary": {
                    "observed_active_elapsed_seconds": 50.0,
                    "overall_active_elapsed_complete": True,
                    "observed_actual_dispatches": 5,
                },
            },
        )
        rep_match_partial = obs.build_b_route_observability_report(
            self.root, run_id="run-timing", baseline_ref="logs/ci/baselines/match.json",
        )
        self.assertTrue(rep_match_partial["baseline_comparison"]["comparable"])
        self.assertFalse(rep_match_partial["baseline_comparison"]["is_gate"])
        self.assertEqual("unknown", rep_match_partial["baseline_comparison"]["factual_deltas"]["observed_active_elapsed_seconds_delta"])
        self.assertEqual(-2, rep_match_partial["baseline_comparison"]["factual_deltas"]["observed_actual_dispatches_delta"])

        # Case 3b: Both current and baseline have overall_active_elapsed_complete == True -> numeric delta (-7.5)
        _write_json(
            self.root / "logs/ci/mvg-planning/run-timing-complete/run.json",
            {
                "run_id": "run-timing-complete",
                "scope_id": "scope-t",
                "active_elapsed_seconds": 42.5,  # roll-up must NOT double-count dispatch receipts!
                "obligation_ids": ["OB-1", "OB-2"],
            },
        )
        for idx, dur in ((1, 12.5), (2, 20.0), (3, 10.0)):
            _write_json(
                self.root / f"logs/ci/mvg-planning/run-timing-complete/dispatch-receipts/dispatch-{idx}.json",
                {"number": idx, "request_identity": f"rc-{idx}", "status": "ok", "active_elapsed_seconds": dur},
            )
        rep_match = obs.build_b_route_observability_report(
            self.root, run_id="run-timing-complete", baseline_ref="logs/ci/baselines/match.json",
        )
        self.assertTrue(rep_match["timing_and_cost_summary"]["overall_active_elapsed_complete"])
        self.assertEqual(42.5, rep_match["timing_and_cost_summary"]["observed_active_elapsed_seconds"])
        self.assertTrue(rep_match["baseline_comparison"]["comparable"])
        self.assertFalse(rep_match["baseline_comparison"]["is_gate"])
        self.assertEqual(-7.5, rep_match["baseline_comparison"]["factual_deltas"]["observed_active_elapsed_seconds_delta"])
        self.assertEqual(-2, rep_match["baseline_comparison"]["factual_deltas"]["observed_actual_dispatches_delta"])

    # ------------------------------------------------------------------
    # AC-3: Unified ReasonCode & 6-field Diagnostic without reinterpretation or masking
    # ------------------------------------------------------------------
    def test_ac3_unified_diagnostics_no_reinterpretation_and_no_category_masking(self) -> None:
        # 1. Run with coexisting budget_exhausted + execution_fault + semantic_error + missing_governance + drift + pending + conflict
        _write_json(
            self.root / "logs/ci/b-route-defect-routing/run-diag/report.json",
            {
                "schema_version": "newrouge.b-route-defect-routing.v1",
                "run_id": "run-diag",
                "status": "blocked",
                "budget_exhausted": True,
                "execution_fault": {"exit_code": 137, "reason": "runner_crash"},
                "semantic_error": {"missing_invariant": "INV-1"},
                "diagnostics": [
                    {"reason_code": "required_governance_missing", "stage": "target", "entity_id": "gov-1", "expected": "catalog", "actual": None, "resume_ref": None},
                    {"reason_code": "input_stale", "stage": "reference", "entity_id": "in-1", "expected": "shaA", "actual": "shaB", "resume_ref": "logs/ci/in.json"},
                    {"reason_code": "pending", "stage": "target", "entity_id": "op-1", "expected": "complete", "actual": "pending", "resume_ref": "logs/ci/op.json"},
                    {"reason_code": "conflict", "stage": "content", "entity_id": "c-1", "expected": "no conflict", "actual": "overlap", "resume_ref": None},
                    {"reason_code": "dependency_unavailable", "stage": "target", "entity_id": "runner-1", "expected": "exit 0", "actual": {"exit_code": 1}, "resume_ref": None},
                ],
            },
        )
        # 2. Unknown schema_version artifact
        _write_json(
            self.root / "logs/ci/b-route-task-preview/run-ver/report.json",
            {"schema_version": "newrouge.future-unknown.v99", "run_id": "run-ver", "status": "ok"},
        )
        # 3. Corrupt JSON file (never silently skipped!)
        corrupt = self.root / "logs/ci/b-route-chapter4-binding/run-bad/report.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("{broken json", encoding="utf-8")

        report = obs.build_b_route_observability_report(self.root)
        self.assertFalse(report["ok"])  # corrupt_reference & unknown_version fail closed

        # All 9 categories present and preserved simultaneously (budget never masked by semantic/execution_fault!)
        self.assertEqual(set(obs.DIAGNOSTIC_CATEGORIES), set(report["categories_present"]))
        # Every diagnostic has the exact 6 codec fields and uses ONLY valid ReasonCode / Stage enum members
        valid_reasons = {r.value for r in codec.ReasonCode}
        valid_stages = {s.value for s in codec.Stage} | {None}
        for d in report["diagnostics"]:
            for key in ("reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"):
                self.assertIn(key, d)
            self.assertIn(d["reason_code"], valid_reasons)
            self.assertIn(d["stage"], valid_stages)
            self.assertIn(d["diagnostic_category"], obs.DIAGNOSTIC_CATEGORIES)
            # Execution fault must NEVER be reclassified as semantic_error
            if d["diagnostic_category"] == "execution_fault":
                self.assertNotEqual("semantic_error", d["reason_code"])

        # Corrupt JSON & unknown schema both surfaced in data_gaps
        gap_kinds = {g["kind"] for g in report["data_gaps"]}
        self.assertIn("corrupt_json", gap_kinds)
        self.assertIn("unknown_schema_version", gap_kinds)

    # ------------------------------------------------------------------
    # AC-4: Strict separation of the 3 reuse classes, timestamp preservation & zero writes
    # ------------------------------------------------------------------
    def test_ac4_three_reuse_classes_disjoint_original_timestamp_preserved_and_zero_writes(self) -> None:
        # Protected pointers to assert zero mutation
        ptr_file = self.root / "knowledge/indexes/current.json"
        ptr_sha_before = _write_json(ptr_file, {"pointer": "v1"})

        # Class 1: Story 2.9 planning adoption reuse (adopted + revoked)
        _write_json(
            self.root / "logs/ci/mvg-recovery/registry.json",
            {
                "epoch": 1,
                "revoked": ["tx-revoked"],
                "entries": [
                    {"epoch": 1, "run_id": "plan-src-1", "transaction_id": "tx-good", "capability_id": "CAP-1", "ancestry": ["tx-good"]},
                    {"epoch": 1, "run_id": "plan-src-2", "transaction_id": "tx-revoked", "capability_id": "CAP-2", "ancestry": ["tx-revoked"]},
                ],
            },
        )
        # Class 2: Apply journal idempotent no-op (target file matches after_sha256)
        target_sha = _write_json(self.root / "docs/planning/b-route/sample.json", {"k": "v"})
        _write_json(
            self.root / "logs/ci/b-route-operations/op-noop-1.json",
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "operation_id": "op-noop-1",
                "status": "complete",
                "entries": [{"path": "docs/planning/b-route/sample.json", "after_sha256": target_sha}],
            },
        )
        # Class 3: Story 4.4 runtime build/prewarm + shared test evidence reuse
        orig_ts = "2026-11-20T01:02:03+00:00"
        reusing_ts = "2026-11-26T09:00:00+00:00"
        _write_json(
            self.root / "logs/ci/mvg-acceptance/run-reuse-2/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "run-reuse-2",
                "scope_id": "scope-r",
                "snapshot_digest": "sha256:snapR",
                "status": "passed",
                "generated_at": reusing_ts,
                "finished_at": reusing_ts,
                "build_artifacts": {
                    "dotnet_build": {"reused": True, "reused_from_run_id": "run-reuse-1", "original_executed_at": orig_ts},
                    "godot_prewarm": {"reused": True, "reused_from_run_id": "run-reuse-1", "original_executed_at": orig_ts},
                },
                "executed_tests": [
                    {
                        "id": "TEST-SHARED",
                        "selector": "Game.Core.Tests.Shared",
                        "status": "passed",
                        "reused": True,
                        "reused_from_run_id": "run-reuse-1",
                        "original_executed_at": orig_ts,
                    },
                ],
                "reuse_rejections": [
                    {"kind": "shared_test_evidence", "test_id": "TEST-DRIFT", "reused_from_run_id": "run-old", "reason": "snapshot_mismatch"},
                ],
                "metrics": {"observed_elapsed_seconds": 1.2, "observed_dispatches": 0, "reserved_dispatches": 1},
            },
        )

        before_files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        report = obs.build_b_route_observability_report(self.root)
        after_files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(before_files, after_files, "Read-only observability must not create or mutate any files")
        self.assertEqual(ptr_sha_before, "sha256:" + hashlib.sha256(ptr_file.read_bytes()).hexdigest())
        self.assertFalse(report["implicit_global_refresh_performed"])

        rb = report["reuse_breakdown"]
        self.assertFalse(rb["cross_class_proof_allowed"])
        self.assertEqual(2, rb["counts"]["planning_adoption_reuse"])
        self.assertEqual({"adopted", "revoked"}, {x["decision"] for x in rb["planning_adoption_reuse"]})
        self.assertEqual(1, rb["counts"]["apply_idempotent_noop"])
        self.assertEqual("idempotent_noop", rb["apply_idempotent_noop"][0]["decision"])
        self.assertEqual(4, rb["counts"]["runtime_build_and_test_reuse"])

        # Shared test item preserves original_executed_at verbatim (NEVER refreshed to reusing_ts!)
        shared_test = next(x for x in rb["runtime_build_and_test_reuse"] if x["kind"] == "shared_test_evidence" and x["decision"] == "reused")
        self.assertEqual(orig_ts, shared_test["original_executed_at"])
        self.assertNotEqual(reusing_ts, shared_test["original_executed_at"])

    # ------------------------------------------------------------------
    # AC-5: Stop-loss, no-progress retries, rework returns & 5 non-offsettable regressions
    # ------------------------------------------------------------------
    def test_ac5_stop_loss_no_progress_retries_and_rework_returns(self) -> None:
        # Ch6 runs with rerun_guard, llm_retry_stop_loss, sc_test_retry_stop_loss, waste_signals, and no-progress retry
        _write_json(
            self.root / "logs/ci/2026-11-26/sc-review-pipeline-task-42-a1/summary.json",
            {
                "run_id": "ch6-a1",
                "task_id": 42,
                "attempt": 1,
                "status": "fail",
                "failed_step": "sc-test",
                "reason": "rerun_blocked:deterministic_fail",
                "issue_count": 3,
                "active_elapsed_seconds": 10.0,
                "diagnostics": {
                    "rerun_guard": {"blocked": True},
                    "llm_retry_stop_loss": {"triggered": True},
                    "sc_test_retry_stop_loss": {"triggered": True},
                    "waste_signals": ["engine_after_unit_fail"],
                },
            },
        )
        _write_json(
            self.root / "logs/ci/2026-11-26/sc-review-pipeline-task-42-a2/summary.json",
            {
                "run_id": "ch6-a2",
                "task_id": 42,
                "attempt": 2,
                "status": "fail",
                "failed_step": "sc-test",
                "reason": "rerun_blocked:deterministic_fail",
                "issue_count": 3,
                "active_elapsed_seconds": 9.0,
            },
        )
        # Rework return
        _write_json(
            self.root / "logs/ci/b-route-defect-routing/rework-1/report.json",
            {
                "schema_version": "newrouge.b-route-defect-routing.v1",
                "run_id": "rework-1",
                "task_id": 42,
                "status": "blocked",
                "defect_class": "contract_definition_change",
                "return_stage": "4",
                "reason_code": "mapping_mismatch",
                "active_elapsed_seconds": 1.0,
            },
        )

        report = obs.build_b_route_observability_report(self.root)
        sl = report["stop_loss_signals"]
        self.assertGreaterEqual(len(sl["rerun_guard"]), 1)
        self.assertGreaterEqual(len(sl["llm_retry_stop_loss"]), 1)
        self.assertGreaterEqual(len(sl["sc_test_retry_stop_loss"]), 1)
        self.assertGreaterEqual(len(sl["waste_signals"]), 1)
        self.assertEqual(1, len(sl["no_progress_retries"]))
        self.assertEqual("42", sl["no_progress_retries"][0]["entity_id"])
        self.assertEqual(1, len(report["rework_returns"]))
        self.assertEqual("4", report["rework_returns"][0]["return_stage"])
        self.assertEqual("contract_definition_change", report["rework_returns"][0]["defect_class"])

    def test_ac5_each_of_five_quality_floor_regressions_blocks_despite_fast_zero_dispatch_metrics(self) -> None:
        cases = (
            ("source_omission", {"source_omission": True, "omissions": ["SRC-9"]}),
            ("mature_identity_drift", {"mature_identity_drift": True, "overwritten_task_ids": [12]}),
            ("unverified_obligation", {"unverified_obligation": True, "coverage_summary": {"not_run_blocking_count": 1}}),
            ("failure_reclassification", {"failure_reclassification": True, "reclassified_failed_flows": ["FLOW-OLD"]}),
            ("premature_out_of_scope_implementation", {"premature_out_of_scope_implementation": True, "premature_out_of_scope_flows": ["FLOW-FUTURE"]}),
        )
        for kind, extra in cases:
            with self.subTest(regression=kind):
                sub_root = Path(self.temp.name) / f"qf_{kind}"
                sub_root.mkdir(parents=True, exist_ok=True)
                verdict_rel = f"logs/ci/verdicts/{kind}.json"
                _write_json(
                    sub_root / verdict_rel,
                    {
                        "schema_version": "newrouge.b-route-completion-verdict.v1",
                        "run_id": f"fast-{kind}",
                        "flow_id": "FLOW-FAST",
                        "status": "passed",
                        "active_elapsed_seconds": 0.1,  # ultra-fast, 0 dispatches!
                        **extra,
                    },
                )
                rep = obs.build_b_route_observability_report(sub_root, verdict_or_scope_refs=[verdict_rel])
                self.assertFalse(rep["ok"], f"{kind} must fail closed")
                self.assertTrue(rep["quality_floor"]["violated"])
                self.assertFalse(rep["quality_floor"]["process_metrics_can_offset"])
                self.assertTrue(rep["quality_floor"]["checks"][kind])

                # CLI must exit 2
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--root", str(sub_root), "--verdict-ref", verdict_rel])
                self.assertEqual(2, code)

    # ------------------------------------------------------------------
    # Planning Page --events-log hook, CLI mutation guard, HTTP parity & Windows junction guard
    # ------------------------------------------------------------------
    def test_planning_page_events_log_hook_feeds_observability(self) -> None:
        _write_json(self.root / "docs/workflows/chapter3-source-set.json", {"sources": ["docs/prd/a.md"]})
        (self.root / "docs/prd").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/prd/a.md").write_text("# PRD\n", encoding="utf-8")

        ev_rel = "logs/ci/obs-page/page-events.jsonl"
        res = planning_page.execute_planning_page_action(
            self.root,
            {"action": "inspect", "mode": "workspace_preview", "scope_id": "scope-page"},
            events_log=ev_rel,
        )
        self.assertEqual(ev_rel, res.get("events_log_path"))
        self.assertTrue((self.root / ev_rel).is_file())

        report = obs.build_b_route_observability_report(self.root, events_logs=[ev_rel])
        self.assertTrue(report["ok"], report["diagnostics"])
        page_events = [e for e in report["events"] if e["event_type"] == "b_route_page_stage_action"]
        self.assertEqual(1, len(page_events))
        self.assertIsInstance(page_events[0]["observed_active_elapsed_seconds"], float)

    def test_cli_forbids_mutation_flags_and_dev_cli_help(self) -> None:
        for flag in cli.FORBIDDEN_MUTATION_FLAGS:
            with self.subTest(flag=flag):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["--root", str(self.root), flag])
                self.assertEqual(2, code)
                payload = json.loads(buf.getvalue())
                self.assertFalse(payload["ok"])
                self.assertEqual("conflict", payload["reason_code"])

        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/python/dev_cli.py"), "b-route-observability", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("--events-log", proc.stdout)
        self.assertIn("--baseline-ref", proc.stdout)

    def test_http_endpoint_parity_and_validation(self) -> None:
        _write_json(
            self.root / "logs/ci/b-route-task-preview/http-1/report.json",
            {
                "schema_version": "newrouge.b-route-task-preview.v1",
                "run_id": "http-1",
                "scope_id": "scope-http",
                "status": "ok",
                "active_elapsed_seconds": 3.5,
            },
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            # Valid GET
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/knowledge/b-route-observability?run_id=http-1") as resp:
                self.assertEqual(200, resp.status)
                data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertEqual(obs.SCHEMA_VERSION, data["schema_version"])
            self.assertEqual(3.5, data["timing_and_cost_summary"]["observed_active_elapsed_seconds"])

            # Unknown / blank / duplicate params rejected with 422
            for bad_qs in ("bogus=1", "run_id=", "run_id=a&run_id=b", "strict=maybe"):
                with self.subTest(qs=bad_qs):
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/knowledge/b-route-observability?{bad_qs}")
                    self.assertEqual(422, ctx.exception.code)
        finally:
            server.shutdown()
            server.server_close()

    def test_windows_junction_rejected_for_report_and_events_log(self) -> None:
        outside = Path(self.temp.name) / "outside_dir"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "ev.jsonl").write_text("{}\n", encoding="utf-8")
        link = self.root / "logs/ci/linked_obs"
        self._junction_or_skip(link, outside)

        # --report through junction rejected with unsafe_path
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--root", str(self.root), "--report", "logs/ci/linked_obs/report.json"])
        self.assertEqual(2, code)
        self.assertEqual("unsafe_path", json.loads(buf.getvalue())["diagnostics"][0]["reason_code"])
        self.assertFalse((outside / "report.json").exists())

        # --events-log through junction rejected with unsafe_path
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            code2 = cli.main(["--root", str(self.root), "--events-log", "logs/ci/linked_obs/ev.jsonl"])
        self.assertEqual(2, code2)
        self.assertEqual("unsafe_path", json.loads(buf2.getvalue())["diagnostics"][0]["reason_code"])

    # ------------------------------------------------------------------
    # Step 4 Fix-Through Hardening Tests (P-01 .. P-09)
    # ------------------------------------------------------------------
    def test_p03_real_3b_capability_selection_calls_reserved_status_and_3a_runner_dispatch_count(self) -> None:
        # 3A report using runner_dispatch_count
        _write_json(
            self.root / "logs/ci/2026-11-26/b-route-source-audit/run-3a-real/attempt-1/report.json",
            {
                "schema_version": "newrouge.b-route-source-audit.v1",
                "run_id": "run-3a-real",
                "scope_id": "scope-real",
                "stage": "audit",
                "status": "ok",
                "planning_eligible": True,
                "runner_dispatch_count": 2,
                "active_elapsed_seconds": 6.0,
            },
        )
        # Real 3B run.json with capability_selection.calls (dict request_identity + reservation_id + status=="reserved")
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-real/run.json",
            {
                "schema_version": "newrouge.mvg-planning-run.v1",
                "run_id": "run-3b-real",
                "scope_id": "scope-real",
                "mvg.run_invocation_limit": 192,
                "active_elapsed_seconds": 15.0,  # roll-up must NOT double-count dispatch-1!
                "capability_selection": {
                    "total_invocations": 2,
                    "calls": [
                        {
                            "number": 1,
                            "phase": "candidate",
                            "candidate": "A",
                            "reservation_id": "run-3b-real:dispatch:1",
                            "status": "reserved",
                            "request_identity": {"phase": "candidate", "timeout_sec": 300, "request_sha256": "sha256:req1"},
                        },
                        {
                            "number": 2,
                            "phase": "candidate",
                            "candidate": "B",
                            "reservation_id": "run-3b-real:dispatch:2",
                            "status": "reserved",
                            "request_identity": {"phase": "candidate", "timeout_sec": 300, "request_sha256": "sha256:req2"},
                        },
                    ],
                },
            },
        )
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-real/candidates/A-r1/lineage-execution.json",
            {"candidate": "A", "lineage": "A-r1", "model_invocation_count": 1, "reservation_ids": ["run-3b-real:dispatch:1"]},
        )
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-real/dispatch-receipts/dispatch-1.json",
            {
                "number": 1,
                "reservation_id": "run-3b-real:dispatch:1",
                "request_identity": {"phase": "candidate", "timeout_sec": 300, "request_sha256": "sha256:req1"},
                "status": "completed",
                "active_elapsed_seconds": 15.0,
            },
        )
        # Stub dispatch-2 still status=="reserved" without outcome -> MUST be reserved_only_not_dispatched!
        _write_json(
            self.root / "logs/ci/mvg-planning/run-3b-real/dispatch-receipts/dispatch-2.json",
            {
                "number": 2,
                "reservation_id": "run-3b-real:dispatch:2",
                "request_identity": {"phase": "candidate", "timeout_sec": 300, "request_sha256": "sha256:req2"},
                "status": "reserved",
            },
        )
        rep = obs.build_b_route_observability_report(self.root)
        self.assertTrue(rep["ok"], rep["diagnostics"])
        tc = rep["timing_and_cost_summary"]
        self.assertEqual(192, tc["reserved_request_budget"])
        # 2 from 3A runner_dispatch_count + 1 actual 3B dispatch = 3 (dispatch-2 is reserved-only!)
        self.assertEqual(3, tc["observed_actual_dispatches"])
        self.assertEqual(1, tc["reserved_only_not_dispatched"])
        # 6.0 (3A) + 15.0 (dispatch-1) = 21.0 (NOT 36.0!)
        self.assertEqual(21.0, tc["observed_active_elapsed_seconds"])
        d1 = next(c for c in tc["correlated_dispatches"] if c["dispatch_key"] == "run-3b-real:dispatch:1")
        d2 = next(c for c in tc["correlated_dispatches"] if c["dispatch_key"] == "run-3b-real:dispatch:2")
        self.assertEqual(1, d1["counted_as"])
        self.assertTrue(d1["dispatched"])
        self.assertEqual(3, len(d1["correlated_sources"]))  # run.json + lineage-execution.json + dispatch-1.json
        self.assertEqual(0, d2["counted_as"])
        self.assertFalse(d2["dispatched"])

    def test_p07_cross_class_reuse_and_timestamp_tampering_emit_conflict(self) -> None:
        # Case A: cross-class planning adoption supplied as runtime test reuse
        sub_a = Path(self.temp.name) / "cross_class"
        sub_a.mkdir(parents=True, exist_ok=True)
        _write_json(
            sub_a / "logs/ci/mvg-acceptance/run-cross/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "run-cross",
                "scope_id": "scope-c",
                "snapshot_digest": "sha256:snapC",
                "status": "passed",
                "generated_at": "2026-11-26T10:00:00+00:00",
                "executed_tests": [
                    {
                        "id": "T-CROSS",
                        "selector": "Game.Core.Tests.Cross",
                        "reused": True,
                        "source_class": "planning_adoption_reuse",
                        "reused_from": "logs/ci/mvg-recovery/registry.json",
                        "original_executed_at": "2026-11-20T00:00:00+00:00",
                    },
                ],
                "metrics": {"observed_elapsed_seconds": 1.0, "observed_dispatches": 0},
            },
        )
        rep_a = obs.build_b_route_observability_report(sub_a)
        self.assertFalse(rep_a["ok"])
        self.assertIn("conflict", [d["reason_code"] for d in rep_a["diagnostics"]])

        # Case B: reused runtime test missing original_executed_at
        sub_b = Path(self.temp.name) / "missing_ts"
        sub_b.mkdir(parents=True, exist_ok=True)
        _write_json(
            sub_b / "logs/ci/mvg-acceptance/run-nots/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "run-nots",
                "scope_id": "scope-c",
                "snapshot_digest": "sha256:snapC",
                "status": "passed",
                "executed_tests": [
                    {"id": "T-NOTS", "selector": "Game.Core.Tests.NoTs", "reused": True, "reused_from_run_id": "run-old"},
                ],
                "metrics": {"observed_elapsed_seconds": 1.0, "observed_dispatches": 0},
            },
        )
        rep_b = obs.build_b_route_observability_report(sub_b)
        self.assertFalse(rep_b["ok"])
        self.assertFalse(rep_b["reuse_breakdown"]["original_timestamps_preserved"])
        self.assertIn("conflict", [d["reason_code"] for d in rep_b["diagnostics"]])

        # Case C: reused runtime test refreshes original_executed_at to reusing run's timestamp
        sub_c = Path(self.temp.name) / "refreshed_ts"
        sub_c.mkdir(parents=True, exist_ok=True)
        now_ts = "2026-11-26T12:00:00+00:00"
        _write_json(
            sub_c / "logs/ci/mvg-acceptance/run-refresh/coverage-receipt.json",
            {
                "schema_version": "newrouge.b-route-execution-receipt.v1",
                "run_id": "run-refresh",
                "scope_id": "scope-c",
                "snapshot_digest": "sha256:snapC",
                "status": "passed",
                "finished_at": now_ts,
                "executed_tests": [
                    {
                        "id": "T-REF",
                        "selector": "Game.Core.Tests.Ref",
                        "reused": True,
                        "reused_from_run_id": "run-old",
                        "original_executed_at": now_ts,
                    },
                ],
                "metrics": {"observed_elapsed_seconds": 1.0, "observed_dispatches": 0},
            },
        )
        rep_c = obs.build_b_route_observability_report(sub_c)
        self.assertFalse(rep_c["ok"])
        self.assertFalse(rep_c["reuse_breakdown"]["original_timestamps_preserved"])
        self.assertIn("conflict", [d["reason_code"] for d in rep_c["diagnostics"]])

    def test_p01_ancestor_junction_broken_junction_and_reserved_write_guards(self) -> None:
        # 1. Ancestor junction at logs/ci (works on Windows without admin via mklink /J -> skipped=0!)
        sub_anc = Path(self.temp.name) / "anc_junc"
        sub_anc.mkdir(parents=True, exist_ok=True)
        outside = Path(self.temp.name) / "outside_ci"
        outside.mkdir(parents=True, exist_ok=True)
        _write_json(outside / "b-route-task-preview/r1/report.json", {"run_id": "r1", "status": "ok"})
        self._junction_or_skip(sub_anc / "logs/ci", outside)
        rep_anc = obs.build_b_route_observability_report(sub_anc)
        self.assertFalse(rep_anc["ok"])
        self.assertIn("unsafe_path", [d["reason_code"] for d in rep_anc["diagnostics"]])

        # 2. Broken junction under logs/ci/b-route-source-audit (create target, junction, then remove target -> broken reparse point!)
        sub_brk = Path(self.temp.name) / "broken_junc"
        sub_brk.mkdir(parents=True, exist_ok=True)
        ephemeral = Path(self.temp.name) / "ephemeral_target"
        ephemeral.mkdir(parents=True, exist_ok=True)
        brk_link = sub_brk / "logs/ci/b-route-source-audit/broken-run"
        self._junction_or_skip(brk_link, ephemeral)
        ephemeral.rmdir()
        rep_brk = obs.build_b_route_observability_report(sub_brk)
        self.assertFalse(rep_brk["ok"])
        self.assertIn("unsafe_path", [d["reason_code"] for d in rep_brk["diagnostics"]])

        # 3. Reserved producer prefixes & dated producer subtrees rejected for both report and events_log
        for bad_report in (
            "logs/ci/b-route-sources/r.json",
            "logs/ci/b-route-task-compilation/r.json",
            "logs/ci/2026-11-26/b-route-source-audit/r.json",
            "logs/ci/2026-11-26/sc-review-pipeline-task-7/r.json",
        ):
            with self.subTest(bad_report=bad_report):
                with self.assertRaises(codec.CodecError) as ctx:
                    obs.write_observability_report(self.root, bad_report, {"ok": True})
                self.assertEqual(codec.ReasonCode.UNSAFE_PATH, ctx.exception.diagnostic.reason_code)
                with self.assertRaises(codec.CodecError) as ctx2:
                    planning_page.write_page_report(self.root, bad_report, {"ok": True})
                self.assertEqual(codec.ReasonCode.UNSAFE_PATH, ctx2.exception.diagnostic.reason_code)

        # 4. Planning page events_log rejects dated producer subtree cleanly
        res_bad_ev = planning_page.execute_planning_page_action(
            self.root,
            {"action": "inspect", "mode": "workspace_preview"},
            events_log="logs/ci/2026-11-26/b-route-task-compilation/events.jsonl",
        )
        self.assertFalse(res_bad_ev["ok"])
        self.assertEqual("unsafe_path", res_bad_ev["diagnostics"][0]["reason_code"])

    def test_p05_bool_as_int_immunity_and_zero_preservation(self) -> None:
        _write_json(
            self.root / "logs/ci/b-route-task-preview/zero-run/report.json",
            {
                "schema_version": "newrouge.b-route-task-preview.v1",
                "run_id": "zero-run",
                "scope_id": "scope-z",
                "status": "ok",
                "active_elapsed_seconds": 0.0,
                "wall_clock_seconds": 0.0,
                "omission_count": True,  # bool MUST NOT coerce to 1 or trigger source_omission!
                "actual_dispatch_count": True,  # bool MUST NOT coerce to 1!
                "estimated_tokens_in": 0,
                "estimated_tokens_out": True,
            },
        )
        rep = obs.build_b_route_observability_report(self.root, run_id="zero-run")
        self.assertTrue(rep["ok"], rep["diagnostics"])
        self.assertFalse(rep["quality_floor"]["violated"])
        tc = rep["timing_and_cost_summary"]
        self.assertEqual(0.0, tc["observed_active_elapsed_seconds"])
        self.assertEqual(0.0, tc["paused_or_wall_clock_seconds"])
        self.assertEqual(0, tc["observed_actual_dispatches"])
        self.assertEqual(0, tc["model_estimated_metrics"]["estimated_tokens_in"])

    def test_p02_p04_p06_p07_baseline_cur_scope_none_dup_verdict_ref_task_comp_jsonl_and_diag_categories(self) -> None:
        # 1. Duplicate --verdict-ref single-counting + per-event duplicate_test_executions + task-compilation events.jsonl
        r1_rel = "logs/ci/mvg-acceptance/dup-r1/coverage-receipt.json"
        r2_rel = "logs/ci/mvg-acceptance/dup-r2/coverage-receipt.json"
        for rel_p, rid in ((r1_rel, "dup-r1"), (r2_rel, "dup-r2")):
            _write_json(
                self.root / rel_p,
                {
                    "schema_version": "newrouge.b-route-execution-receipt.v1",
                    "run_id": rid,
                    "scope_id": "scope-d",
                    "flow_id": "FLOW-D",
                    "snapshot_digest": "sha256:snapD",
                    "status": "passed",
                    "build_artifacts": {"dotnet_build": {"executed": True, "reused": False}},
                    "executed_tests": [{"id": "T-D", "selector": "Game.Core.Tests.Dup", "reused": False}],
                    "metrics": {"observed_elapsed_seconds": 2.0, "observed_dispatches": 1},
                },
            )
        tc_ev = self.root / "logs/ci/b-route-task-compilation/op-tc-1/events.jsonl"
        tc_ev.parent.mkdir(parents=True, exist_ok=True)
        tc_ev.write_text(
            json.dumps({
                "schema_version": "newrouge.b-route-task-compilation-event.v1",
                "operation_id": "op-tc-1",
                "scope_id": "scope-d",
                "event_type": "task_compiled",
                "status": "ok",
                "active_elapsed_seconds": 1.0,
            }) + "\n",
            encoding="utf-8",
        )
        rep = obs.build_b_route_observability_report(
            self.root,
            verdict_or_scope_refs=[r1_rel, r1_rel],  # duplicated + already under mvg-acceptance!
        )
        self.assertTrue(rep["ok"], rep["diagnostics"])
        self.assertEqual(2, rep["build_prewarm_summary"]["dotnet_build_executed"])
        self.assertEqual(2, rep["timing_and_cost_summary"]["observed_actual_dispatches"])
        self.assertIn("3C", rep["axes"]["by_stage"])
        mvg_events = [e for e in rep["events"] if e["event_type"] == "mvg_coverage_receipt"]
        self.assertEqual(2, len(mvg_events))
        self.assertTrue(all(len(e["duplicate_test_executions"]) == 1 for e in mvg_events))

        # 2. cur_scope=None (multi-scope repo) -> baseline MUST be comparable=False!
        _write_json(
            self.root / "logs/ci/b-route-task-preview/other-scope/report.json",
            {"schema_version": "newrouge.b-route-task-preview.v1", "run_id": "other-scope", "scope_id": "scope-OTHER", "status": "ok"},
        )
        _write_json(
            self.root / "logs/ci/baselines/base-d.json",
            {
                "schema_version": obs.SCHEMA_VERSION,
                "scope_id": "scope-d",
                "obligation_ids": ["OB-1"],
                "timing_and_cost_summary": {"observed_active_elapsed_seconds": 5.0, "overall_active_elapsed_complete": True, "observed_actual_dispatches": 1},
            },
        )
        rep_noscope = obs.build_b_route_observability_report(self.root, baseline_ref="logs/ci/baselines/base-d.json")
        self.assertFalse(rep_noscope["baseline_comparison"]["comparable"])
        self.assertIn("current_missing_single_scope_or_flow", rep_noscope["baseline_comparison"]["mismatch_details"])

        # 3. Unknown baseline schema fails closed with unknown_schema
        _write_json(self.root / "logs/ci/baselines/bad-schema.json", {"schema_version": "newrouge.unknown.v99", "scope_id": "scope-d"})
        rep_bad_base = obs.build_b_route_observability_report(self.root, baseline_ref="logs/ci/baselines/bad-schema.json")
        self.assertFalse(rep_bad_base["ok"])
        self.assertIn("unknown_schema", [d["reason_code"] for d in rep_bad_base["diagnostics"]])

        # 4. Disk fake diagnostic_category ignored; digest_mismatch -> drift_or_stale; invalid_json -> corrupt_reference
        norm_dm = obs.normalize_unified_diagnostic({
            "reason_code": "digest_mismatch",
            "stage": "reference",
            "entity_id": "e1",
            "expected": "sha1",
            "actual": "sha2",
            "resume_ref": None,
            "diagnostic_category": "semantic",  # spoofed from disk!
        })
        self.assertEqual("drift_or_stale", norm_dm["diagnostic_category"])
        norm_ij = obs.normalize_unified_diagnostic({
            "reason_code": "invalid_json",
            "stage": "decode",
            "entity_id": "e2",
            "expected": "json",
            "actual": "bad",
            "resume_ref": None,
            "diagnostic_category": "semantic",  # spoofed from disk!
        })
        self.assertEqual("corrupt_reference", norm_ij["diagnostic_category"])

    def test_p08_quality_floor_3a_310_45_keys(self) -> None:
        cases = (
            ("3a_semantic_blockers", "source_omission", {"semantic_blockers": ["BLK-1"]}),
            ("3a_unaccounted_blocks", "source_omission", {"unaccounted_blocks": ["SRC-BLK-2"]}),
            ("3a_omitted_requirements", "source_omission", {"omitted_requirements": ["REQ-9"]}),
            ("310_na_exemption", "failure_reclassification", {"na_exemption": ["free_text_na"]}),
            ("310_status_tampering", "failure_reclassification", {"status_tampering": True}),
            ("310_acceptance_weakening", "unverified_obligation", {"acceptance_weakening": ["acc-1"]}),
            ("310_test_deletion", "unverified_obligation", {"test_deletion": ["TestA.cs"]}),
            ("45_evidence_tier_violations", "unverified_obligation", {"evidence_tier_violations": ["static_as_engine"]}),
            ("45_skipped_tests", "unverified_obligation", {"skipped_tests": [{"test_id": "T1"}]}),
            ("45_missing_flow_obligations", "unverified_obligation", {"missing_flow_obligations": {"FLOW-1": ["OB-1"]}}),
            ("45_cross_snapshot_splicing", "unverified_obligation", {"cross_snapshot_splicing_detected": True}),
            ("45_forced_premature_future", "premature_out_of_scope_implementation", {"forced_premature_future_implementation": True}),
        )
        for label, expected_kind, extra in cases:
            with self.subTest(case=label):
                sub = Path(self.temp.name) / f"p08_{label}"
                sub.mkdir(parents=True, exist_ok=True)
                vrel = f"logs/ci/verdicts/{label}.json"
                _write_json(
                    sub / vrel,
                    {
                        "schema_version": "newrouge.b-route-completion-verdict.v1",
                        "run_id": f"r-{label}",
                        "flow_id": "FLOW-P08",
                        "status": "passed",
                        "active_elapsed_seconds": 0.1,
                        **extra,
                    },
                )
                rep = obs.build_b_route_observability_report(sub, verdict_or_scope_refs=[vrel])
                self.assertFalse(rep["ok"], f"{label} must block")
                self.assertTrue(rep["quality_floor"]["checks"][expected_kind], f"{label} -> {expected_kind}")


if __name__ == "__main__":
    unittest.main()
