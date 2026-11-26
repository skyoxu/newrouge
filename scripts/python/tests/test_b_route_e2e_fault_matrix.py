"""Story 4.10 end-to-end Windows fault, shared-change, evidence authenticity,
cross-surface parity, and Epic 4 -> Epic 5 handoff tests (AC-1..AC-6).

All tests execute natively on Windows with skipped=0 (no mock OS exceptions
masquerading as real Windows lock or process termination evidence).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_PY = ROOT / "scripts" / "python"
SCRIPTS_SC = ROOT / "scripts" / "sc"
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_codec as codec  # noqa: E402
import _b_route_e2e_fault_matrix as e2e_matrix  # noqa: E402
import dev_cli  # noqa: E402
import dev_cli_builders  # noqa: E402
import verify_b_route_e2e_fault_matrix as e2e_cli  # noqa: E402


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


class BRouteE2EFaultMatrixTests(unittest.TestCase):
    """AC-1..AC-6 end-to-end verification under real Windows faults and shared changes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cli_report_rel = f"logs/ci/2026-11-26/e2e-cli-selftest-{os.getpid()}.json"
        cls._cli_report_path = ROOT / cls._cli_report_rel
        if cls._cli_report_path.exists():
            cls._cli_report_path.unlink()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cls._cli_rc = e2e_cli.main(["--root", str(ROOT), "--report", cls._cli_report_rel])
        cls._cli_stdout = buf.getvalue()
        cls._full_result = json.loads(cls._cli_stdout)
        cls._cli_disk_payload = (
            json.loads(cls._cli_report_path.read_text(encoding="utf-8"))
            if cls._cli_report_path.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if cls._cli_report_path.exists():
                cls._cli_report_path.unlink()
        except OSError:
            pass

    def _assert_exact_six_key_diag(self, diag: object) -> None:
        self.assertIsInstance(diag, dict)
        self.assertEqual(DIAGNOSTIC_KEYS, set(diag.keys()), diag)
        self.assertIn(diag["reason_code"], {c.value for c in codec.ReasonCode})

    def test_ac1_real_windows_locks_child_exit_six_stages_post_edits_and_same_id_conflict(self) -> None:
        ac1 = self._full_result["windows_fault_injection_matrix"]
        self.assertTrue(ac1["ok"], ac1)
        self.assertEqual("passed", ac1["status"])

        pe = ac1["platform_evidence"]
        self.assertEqual("nt", pe["os_name"])
        self.assertTrue(pe["used_real_windows_msvcrt_lock"])
        self.assertTrue(pe["used_real_child_process_termination"])
        self.assertIs(False, pe["mock_os_exception_claimed_as_windows_proof"])
        self.assertGreaterEqual(len(ac1["untested_windows_boundaries"]), 4)

        lc = ac1["windows_lock_contention"]
        self.assertTrue(lc["ok"])
        self.assertTrue(lc["contention_blocked"])
        self.assertTrue(lc["release_after_taskkill"])
        self._assert_exact_six_key_diag(lc["diagnostic"])

        stages = ac1["stages"]
        self.assertEqual({"prepare", "reserve", "apply", "verify", "publish", "recover"}, set(stages.keys()))
        for name, info in stages.items():
            with self.subTest(stage=name):
                self.assertTrue(info["ok"], info)
                self.assertTrue(info["live_task_statuses_preserved"])

        self.assertTrue(stages["prepare"]["mid_prepare_hook_reached"])
        self.assertTrue(stages["prepare"]["same_id_replay_ok"])
        self.assertTrue(stages["prepare"]["same_id_mutated_conflict"])
        self.assertTrue(stages["reserve"]["mid_reserve_hook_reached"])
        self.assertTrue(stages["reserve"]["reserve_idempotent_replay_ok"])
        for st_name in ("apply", "verify", "publish", "recover"):
            with self.subTest(partial_block_stage=st_name):
                self.assertTrue(stages[st_name]["page_pending_nonempty"], stages[st_name])
                self.assertTrue(stages[st_name]["page_action_blocked_partial"], stages[st_name])
                self.assertTrue(stages[st_name]["chapter6_gate_blocked_partial"], stages[st_name])
        self.assertTrue(stages["apply"]["readers_blocked_partial"])
        self.assertTrue(stages["apply"]["projection_saw_pending"])
        self.assertTrue(stages["apply"]["post_edit_preserved"])
        self.assertTrue(stages["verify"]["receipt_not_publication"])
        self.assertTrue(stages["verify"]["corrupt_journal_blocked_no_silent_repair"])
        self.assertTrue(stages["publish"]["uncleaned_pending_blocked_consumption"])
        self.assertTrue(stages["publish"]["catalog_bytes_preserved_across_cleanup"])
        self.assertTrue(stages["recover"]["idempotent_noop"])
        self.assertTrue(stages["recover"]["noop_bytes_unchanged"])
        self.assertTrue(stages["recover"]["post_complete_same_id_mutated_conflict"])

    def test_ac2_shared_task_multi_scope_drift_legacy_pending_anti_bypass_and_nonflow_integration_owner(self) -> None:
        ac2 = self._full_result["shared_task_and_scope_drift_matrix"]
        self.assertTrue(ac2["ok"], ac2)
        self.assertEqual("passed", ac2["status"])
        self.assertNotEqual(ac2["applicable_set_digest_before"], ac2["applicable_set_digest_after"])
        self.assertEqual(["plan-s1", "plan-s2"], ac2["plans_for_shared_task_after"])

        checks = ac2["checks"]
        self.assertTrue(checks["initial_readiness_tasks_101_and_301_ok"])
        self.assertTrue(checks["applicable_set_digest_expanded"])
        self.assertTrue(checks["all_entrypoints_consistent_block"])
        self.assertTrue(checks["unrelated_scope3_unaffected"])
        self.assertTrue(checks["source_drift_isolated_to_affected_scope"])
        self.assertTrue(checks["legacy_pending_blocked_and_original_contract_preserved"])
        self.assertTrue(checks["non_flow_positive_ok"])
        self.assertTrue(checks["non_flow_negative_blocked"])
        self.assertTrue(checks["integration_owner_positive_non_self_locking"])
        self.assertTrue(checks["integration_owner_negative_blocked"])

        anti = checks["anti_bypass"]
        self.assertTrue(anti["delete_origins_blocked_never_legacy_a"])
        self.assertTrue(anti["delete_manifest_blocked"])
        self.assertTrue(anti["delete_commit_trace_blocked_never_legacy_a"])
        self.assertTrue(anti["fake_na_never_bypasses"])
        self.assertTrue(anti["delete_pending_marker_never_bypasses"])

    def test_ac3_shared_change_flow_a_failure_and_out_of_scope_flow_b_moving_in_scope(self) -> None:
        ac3 = self._full_result["shared_change_flow_ab_evolution_matrix"]
        self.assertTrue(ac3["ok"], ac3)
        self.assertEqual("passed", ac3["status"])
        checks = ac3["checks"]
        self.assertTrue(checks["both_flow_a_and_flow_b_impacted"])
        self.assertTrue(checks["phase1_buckets_existing_a_and_future_b"])
        self.assertTrue(checks["phase1_flow_a_launch_failure_blocked"])
        self.assertTrue(checks["phase1_flow_a_failure_blocks_runner_and_verdict"])
        self.assertTrue(checks["failed_flow_reclassification_to_planned_rejected"])
        self.assertTrue(checks["older_manifest_hiding_flow_a_rejected"])
        self.assertTrue(checks["phase1_flow_a_fixed_passes_protocol_while_b_stays_future"])
        self.assertTrue(checks["phase2_flow_b_moves_to_current_new"])
        self.assertTrue(checks["phase2_incomplete_flow_b_blocks_completion"])

    def test_ac4_multi_flow_shared_test_isolation_cross_snapshot_rejection_and_authenticity_tiers(self) -> None:
        ac4 = self._full_result["shared_evidence_and_authenticity_matrix"]
        self.assertTrue(ac4["ok"], ac4)
        self.assertEqual("passed", ac4["status"])
        checks = ac4["checks"]
        self.assertTrue(checks["shared_test_executed_once_across_flows"])
        self.assertTrue(checks["per_test_isolated_dirs_zero_leak"])
        self.assertTrue(checks["same_snapshot_reuse_preserves_original_executed_at"])
        self.assertTrue(checks["cross_snapshot_splicing_rejected"])
        self.assertTrue(checks["empty_report_rejected"])
        self.assertTrue(checks["skipped_test_rejected"])
        self.assertTrue(checks["scene_method_without_input_event_rejected"])
        self.assertTrue(checks["fortest_backdoor_rejected"])
        self.assertTrue(checks["missing_manual_independent_signoff_rejected"])
        self.assertTrue(checks["protocol_fixture_honest_runtime_verified_false"])
        self.assertTrue(checks["single_flow_bounded_scope_not_full_mvg"])

    def test_ac5_page_knowledge_observability_parity_epoch_reopen_zero_pointer_mutation_and_non_offsetting_metrics(self) -> None:
        ac5 = self._full_result["page_knowledge_observability_parity_matrix"]
        self.assertTrue(ac5["ok"], ac5)
        self.assertEqual("passed", ac5["status"])
        checks = ac5["checks"]
        self.assertTrue(checks["snapshot_identity_and_reopen_consistent_across_surfaces"])
        self.assertTrue(checks["revoked_epoch_and_reopen_never_resurrect"])
        self.assertTrue(checks["preview_and_attempt_leave_pointers_and_main_byte_identical"])
        self.assertTrue(checks["zero_implicit_global_knowledge_refresh"])
        self.assertTrue(checks["unknown_vs_measured_separated_and_quality_floor_non_offsetting"])

    def test_ac6_epic5_handoff_cli_confinement_and_windows_junction_rejection(self) -> None:
        self.assertEqual(0, self._cli_rc, self._full_result.get("diagnostics"))
        self.assertEqual(self._full_result, self._cli_disk_payload)

        full = self._full_result
        self.assertEqual(e2e_matrix.SCHEMA_VERSION, full["schema_version"])
        self.assertTrue(full["ok"], full.get("diagnostics"))
        self.assertTrue(full["epic4_capabilities_verified"])
        self.assertTrue(full["consumer_alignment_summary"]["ok"])
        self.assertEqual("ok", full["consumer_alignment_summary"]["reason_code"])

        handoff = full["epic5_handoff_readiness_report"]
        self.assertTrue(handoff["epic4_capabilities_verified"])
        self.assertIn("consumer_coverage", handoff)
        self.assertIn("migration_readiness", handoff)
        self.assertIn("scope_evidence_summary", handoff)
        self.assertIn("windows_fault_summary", handoff)
        self.assertTrue(handoff["consumer_coverage"]["epic4_alignment_ready"])
        self.assertIs(False, handoff["migration_readiness"]["switch_ready_now"])
        self.assertTrue(handoff["scope_evidence_summary"]["cross_snapshot_splicing_rejected"])
        self.assertTrue(handoff["windows_fault_summary"]["ok"])
        self.assertIs(True, handoff["protocol_fixture_is_not_reward_gameplay_acceptance"])
        self.assertIs(False, handoff["runtime_verified"])
        self.assertIs(False, handoff["default_b_enabled"])
        self.assertIs(False, handoff["a_write_compatibility_retired"])
        self.assertIs(False, handoff["second_state_machine_created"])
        self.assertIs(False, handoff["implicit_global_refresh_performed"])
        self.assertIs(False, handoff["mock_os_exception_claimed_as_windows_proof"])
        self.assertEqual(
            {
                "reward_production_csharp_thin_adapter_and_controlled_command",
                "reward_dual_path_real_windows_godot_csharp_evidence",
                "conditional_default_b_switch_for_new_requirements",
                "independent_a_exit_gate_and_actual_revocation",
            },
            {g["gate_id"] for g in handoff["epic5_deferred_gates"]},
        )
        for ac_key in ("AC-1", "AC-2", "AC-3", "AC-4", "AC-5", "AC-6"):
            self.assertEqual("passed", handoff["ac_status"][ac_key])
        for loc in handoff["evidence_locators"]:
            self.assertTrue(loc["exists"], loc)
            self.assertEqual(64, len(loc["sha256"]))

        # --skip-fault-harness MUST fail closed (exit 2, ok=False, epic4_capabilities_verified=False, exact 6-key diag)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_skip = dev_cli.main(["b-route-e2e-matrix", "--root", str(ROOT), "--skip-fault-harness"])
        self.assertEqual(2, rc_skip)
        skip_payload = json.loads(buf.getvalue())
        self.assertFalse(skip_payload["ok"])
        self.assertFalse(skip_payload["epic4_capabilities_verified"])
        self.assertTrue(skip_payload["diagnostics"])
        for d in skip_payload["diagnostics"]:
            self._assert_exact_six_key_diag(d)

        # Unknown CLI flag MUST fail closed with exit 2 and INVALID_ARGUMENT exact 6-key diagnostic
        buf_unk = io.StringIO()
        with contextlib.redirect_stdout(buf_unk):
            rc_unk = e2e_cli.main(["--root", str(ROOT), "--unknown-bogus-flag"])
        self.assertEqual(2, rc_unk)
        unk_payload = json.loads(buf_unk.getvalue())
        self.assertFalse(unk_payload["ok"])
        self.assertEqual(codec.ReasonCode.INVALID_ARGUMENT.value, unk_payload["reason_code"])
        for d in unk_payload["diagnostics"]:
            self._assert_exact_six_key_diag(d)

        # All 10 forbidden mutation flags MUST fail closed with exit 2 and CONFLICT via BOTH dev_cli.main and e2e_cli.main
        self.assertEqual(10, len(e2e_cli.FORBIDDEN_MUTATION_FLAGS))
        for flag in e2e_cli.FORBIDDEN_MUTATION_FLAGS:
            with self.subTest(entrypoint="e2e_cli", flag=flag):
                buf_f = io.StringIO()
                with contextlib.redirect_stdout(buf_f):
                    rc_f = e2e_cli.main(["--root", str(ROOT), flag])
                self.assertEqual(2, rc_f)
                f_payload = json.loads(buf_f.getvalue())
                self.assertFalse(f_payload["ok"])
                self.assertEqual(codec.ReasonCode.CONFLICT.value, f_payload["reason_code"])
                for d in f_payload["diagnostics"]:
                    self._assert_exact_six_key_diag(d)
            with self.subTest(entrypoint="dev_cli", flag=flag):
                buf_d = io.StringIO()
                with contextlib.redirect_stdout(buf_d):
                    rc_d = dev_cli.main(["b-route-e2e-matrix", "--root", str(ROOT), flag])
                self.assertEqual(2, rc_d)
                d_payload = json.loads(buf_d.getvalue())
                self.assertFalse(d_payload["ok"])
                self.assertEqual(codec.ReasonCode.CONFLICT.value, d_payload["reason_code"])
                for d in d_payload["diagnostics"]:
                    self._assert_exact_six_key_diag(d)

        # Builder parity & forbidden flag enforcement
        ns_ok = type("Args", (), {"root": str(ROOT), "skip_fault_harness": True, "report": "logs/ci/2026-11-26/e2e-probe.json"})()
        cmd = dev_cli_builders.build_b_route_e2e_matrix_cmd(ns_ok)
        self.assertIn("verify_b_route_e2e_fault_matrix.py", cmd[2])
        self.assertIn("--skip-fault-harness", cmd)
        self.assertIn("--report", cmd)
        ns_bad = type("Args", (), {"root": str(ROOT), "apply": True})()
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_e2e_matrix_cmd(ns_bad)

        # Reserved report prefixes, existing report CONFLICT, and Windows mklink /J rejections (--root & --report)
        with tempfile.TemporaryDirectory(prefix="nr410-cli-") as tmp_str:
            tmp = Path(tmp_str).resolve()
            (tmp / "logs/ci/2026-11-26").mkdir(parents=True, exist_ok=True)
            existing = tmp / "logs/ci/2026-11-26/already-exists.json"
            existing.write_text("{}\n", encoding="utf-8")

            # Existing --report rejected via CLI with exit 2 and CONFLICT
            buf_ov = io.StringIO()
            with contextlib.redirect_stdout(buf_ov):
                rc_ov = e2e_cli.main([
                    "--root", str(tmp),
                    "--skip-fault-harness",
                    "--report", "logs/ci/2026-11-26/already-exists.json",
                ])
            self.assertEqual(2, rc_ov)
            ov_payload = json.loads(buf_ov.getvalue())
            self.assertFalse(ov_payload["ok"])
            self.assertEqual(codec.ReasonCode.CONFLICT.value, ov_payload["reason_code"])
            for d in ov_payload["diagnostics"]:
                self._assert_exact_six_key_diag(d)

            # Expanded reserved prefixes rejected with UNSAFE_PATH
            for bad_rel in (
                "logs/ci/b-route-operations/bad.json",
                "logs/ci/b-route-chapter6-leases/bad.json",
                "logs/ci/b-route-chapter6-gate/bad.json",
                "logs/ci/b-route-adoption-reviews/bad.json",
                "logs/ci/b-route-compensation-segments/bad.json",
                "logs/ci/2026-11-26/b-route-candidate-check/bad.json",
            ):
                with self.subTest(reserved_report=bad_rel):
                    with self.assertRaises(codec.CodecError) as res_err:
                        e2e_matrix.validate_e2e_report_path(tmp, bad_rel)
                    self.assertEqual(codec.ReasonCode.UNSAFE_PATH, res_err.exception.diagnostic.reason_code)
                    self._assert_exact_six_key_diag(res_err.exception.diagnostic.to_dict())

            # Real Windows directory junction rejection on --report ancestor AND on --root itself
            outside = tmp / "outside_target"
            outside.mkdir()
            junc_parent = tmp / "logs/ci/junc_parent"
            junc_root = tmp / "junc_root"
            proc_junc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junc_parent), str(outside)],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(0, proc_junc.returncode, proc_junc.stderr)
            proc_jroot = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junc_root), str(outside)],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(0, proc_jroot.returncode, proc_jroot.stderr)
            try:
                buf_j = io.StringIO()
                with contextlib.redirect_stdout(buf_j):
                    rc_j = e2e_cli.main([
                        "--root", str(tmp),
                        "--skip-fault-harness",
                        "--report", "logs/ci/junc_parent/escape.json",
                    ])
                self.assertEqual(2, rc_j)
                j_payload = json.loads(buf_j.getvalue())
                self.assertFalse(j_payload["ok"])
                self.assertEqual(codec.ReasonCode.UNSAFE_PATH.value, j_payload["reason_code"])
                for d in j_payload["diagnostics"]:
                    self._assert_exact_six_key_diag(d)
                self.assertFalse((outside / "escape.json").exists())

                buf_jr = io.StringIO()
                with contextlib.redirect_stdout(buf_jr):
                    rc_jr = e2e_cli.main([
                        "--root", str(junc_root),
                        "--skip-fault-harness",
                    ])
                self.assertEqual(2, rc_jr)
                jr_payload = json.loads(buf_jr.getvalue())
                self.assertFalse(jr_payload["ok"])
                self.assertEqual(codec.ReasonCode.UNSAFE_PATH.value, jr_payload["reason_code"])
                for d in jr_payload["diagnostics"]:
                    self._assert_exact_six_key_diag(d)
            finally:
                for jp in (junc_parent, junc_root):
                    subprocess.run(
                        ["cmd", "/c", "rmdir", str(jp)],
                        capture_output=True,
                        timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )


if __name__ == "__main__":
    unittest.main()
