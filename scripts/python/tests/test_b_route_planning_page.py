"""Story 4.7 stage-true B-route planning page: Task-free 3A/3B, gated 3C/Chapter 6, prefix/budget honesty.

These tests prove the page/CLI/direct-service contract only; they are not Godot gameplay or Reward
pilot evidence (ui_contract_only_not_godot_gameplay is always true, runtime_verified always false).
"""

from __future__ import annotations

import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))
sys.path.insert(0, str(ROOT / "scripts/python/tests"))

import _b_route_knowledge_projection as projection  # noqa: E402
import _b_route_planning_page as page  # noqa: E402
import query_b_route_planning_page as cli  # noqa: E402
from test_b_route_knowledge_projection import CATALOG, Repo  # noqa: E402

PYTHON = sys.executable
DIAGNOSTIC_FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
SOURCE_SET = "docs/workflows/chapter3-source-set.json"
REGISTRY = "logs/ci/mvg-recovery/registry.json"
POINTERS = ("knowledge/indexes/current.json", "knowledge/indexes/last-known-good.json",
            "logs/ci/project-health-knowledge/latest.json", "logs/ci/project-health-knowledge/runtime/latest.json")


class Recorder:
    """Command runner stub that records argv without starting any model or planner."""

    def __init__(self, code: int = 0, payload: dict | None = None, effect=None):
        self.calls: list[list[str]] = []
        self.code = code
        self.payload = payload if payload is not None else {"status": "ok", "diagnostics": []}
        self.effect = effect

    def __call__(self, argv, cwd, timeout):
        self.calls.append(list(argv))
        if self.effect:
            self.effect()
        return self.code, json.dumps(self.payload), ""


class PageTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="story47-")
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.repo = Repo(self.root)
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("SC_MVG_RECOVERY_ROOT", None)
        os.environ.pop("SC_MVG_RECOVERY_EPOCH", None)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    # -- fixtures -----------------------------------------------------------
    def seed_sources(self):
        self.repo.write("docs/gdd/source.md", "# Rule\n\nKeep the reward order.\n")
        self.repo.write(SOURCE_SET, {"schema_version": "chapter3.source-set.v1",
                                     "active_patterns": ["docs/gdd/source.md"],
                                     "active_sources": ["docs/gdd/source.md"], "retirements": []})
        self.repo.write("knowledge/policies/source-exclusions.v1.json",
                        (ROOT / "knowledge/policies/source-exclusions.v1.json").read_bytes())

    def seed_3a_report(self):
        self.repo.write("logs/ci/2026-11-26/b-route-source-audit/run-a/attempt-1/report.json",
                        {"schema_version": "newrouge.b-route-source-audit.v1", "planning_eligible": True,
                         "execution_complete": True, "independent_audit": True, "evidence_class": "real_model",
                         "semantic_blockers": [], "formal_adoption": False, "diagnostics": []})

    def seed_pointers(self):
        for rel in POINTERS:
            self.repo.write(rel, {"pointer": rel})

    def seed_runs(self):
        self.repo.write(REGISTRY, {"schema_version": "newrouge.mvg-completed-registry.v1", "epoch": 1,
                                   "entries": [], "revoked": ["tx-rev"]})

        def run(run_id, *, epoch=1, tx="tx-ok", **extra):
            state = {"phase": "generate", "input_stage": "3b", "recovery": {"epoch": epoch},
                     "planning_runtime": {"profile": "mvg_3b", "prepared_ref": "logs/ci/b-route-planning-input/r0/prepared.json"},
                     "capability_selection": {"selected": [{"checkpoint": {"transaction_id": tx}}], "total": 3,
                                              "total_invocations": 3},
                     "mvg": {"run_invocation_limit": 10},
                     "candidate_attempts": {"c1": {}, "c2": {"final_meta": {"sha": "x"}}},
                     "request_budget": {"limit": 10, "used": 3}, "repair_attempts": 1}
            state.update(extra)
            return self.repo.write(f"logs/ci/mvg-planning/{run_id}/run.json", state)

        raw_ok = run("run-ok")
        run("run-budget", selection_block_reason="run_blocked_budget_exhausted")
        run("run-epoch", epoch=0)
        run("run-revoked", tx="tx-rev")
        return raw_ok

    # -- helpers ------------------------------------------------------------
    def state(self, **kwargs):
        kwargs.setdefault("mode", "workspace_preview")
        return page.inspect_planning_page_state(self.root, **kwargs)

    def execute(self, request, runner=None):
        return page.execute_planning_page_action(self.root, request, command_runner=runner)

    def assert_six(self, diagnostic):
        self.assertEqual(DIAGNOSTIC_FIELDS, set(diagnostic))
        self.assertIn(diagnostic["reason_code"], {c.value for c in page.codec.ReasonCode})

    def assert_honest(self, payload):
        self.assertIs(True, payload["ui_contract_only_not_godot_gameplay"])
        self.assertIs(False, payload["runtime_verified"])

    def tree(self, include_logs=True):
        result = {}
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_file() and not rel.startswith(".git/") and (include_logs or not rel.startswith("logs/")):
                result[rel] = path.read_bytes()
        return result


class StageTrueGateTests(PageTestBase):
    """AC-1 STAGE_3AB: Task-free 3A/3B, real 3C and Chapter 6 prerequisites."""

    def test_no_task_no_readiness_enables_3a_3b_while_3c_and_chapter6_block(self):
        self.seed_sources()
        self.seed_3a_report()
        self.assertFalse((self.root / ".taskmaster").exists())
        state = self.state()
        gates = state["stage_gates"]
        self.assertEqual(page.SCHEMA_VERSION, state["schema_version"])
        for key in ("stage_3a_sources", "stage_3b_planning"):
            self.assertTrue(gates[key]["allowed"], gates[key]["diagnostics"])
            self.assertFalse(gates[key]["requires_tasks"])
            self.assertFalse(gates[key]["requires_chapter5_readiness"])
            self.assertFalse(gates[key]["allow_unready_permitted"])
            self.assertFalse(gates[key]["draft_permitted"])
        self.assertEqual(list(page.SOURCE_STAGES), gates["stage_3a_sources"]["cli_stages"])
        self.assertFalse(gates["stage_3c_tasks"]["allowed"])
        self.assertEqual("required_governance_missing", gates["stage_3c_tasks"]["diagnostics"][-1]["reason_code"])
        self.assertFalse(gates["stage_6_implement"]["allowed"])
        self.assertEqual("missing_required_field", gates["stage_6_implement"]["diagnostics"][0]["reason_code"])
        for gate in gates.values():
            for diagnostic in gate["diagnostics"]:
                self.assert_six(diagnostic)
        self.assert_honest(state)

    def test_3b_requires_accepted_3a_evidence_and_blocks_without_delegation(self):
        self.seed_sources()
        # Unaudited 3A account report must NOT unlock stage_3b_planning.
        self.repo.write("logs/ci/2026-11-26/b-route-sources/run-acct/attempt-1/account/report.json",
                        {"schema_version": "newrouge.b-route-sources-report.v1", "accounting_complete": True,
                         "planning_eligible": True, "formal_adoption": False, "diagnostics": []})
        state = self.state()
        self.assertFalse(state["stage_gates"]["stage_3b_planning"]["allowed"])
        self.assertEqual(1, state["stage_gates"]["stage_3b_planning"]["evidence"]["reports_found"])
        self.assertEqual([], state["stage_gates"]["stage_3b_planning"]["evidence"]["accepted_3a_reports"])
        recorder = Recorder()
        result = self.execute({"action": "3b_capability", "invocation_mode": "new",
                               "planning_contract": "docs/workflows/chapter3-source-set.json"}, recorder)
        self.assertFalse(result["ok"])
        self.assertEqual("required_governance_missing", result["reason_code"])
        self.assertEqual([], recorder.calls)
        self.assertEqual(state["stage_gates"]["stage_3b_planning"]["diagnostics"][-1]["reason_code"],
                         result["diagnostics"][-1]["reason_code"])
        # Real 3A independent audit report with planning_eligible=True unlocks stage_3b_planning.
        self.seed_3a_report()
        unlocked = self.state()
        self.assertTrue(unlocked["stage_gates"]["stage_3b_planning"]["allowed"])

    def test_real_3a_prepare_succeeds_without_tasks_or_readiness(self):
        self.seed_sources()
        result = self.execute({"action": "3a_sources", "stage": "prepare", "run_id": "run-a",
                               "scope_id": "scope-1", "attempt_id": "a1"})
        self.assertTrue(result["ok"], result["diagnostics"])
        self.assertEqual(0, result["delegate_exit_code"])
        self.assertEqual("newrouge.b-route-sources-report.v1", result["delegate_result"]["schema_version"])
        self.assertFalse(result["delegate_result"]["formal_adoption"])
        self.assertIn("--source-set", result["delegate"]["argv"])
        self.assertFalse((self.root / ".taskmaster").exists())
        self.assertFalse(result["recommendation_only"])
        self.assert_honest(result)
        # Real 3A audit supports AUDIT_ARGUMENTS with positive int validation.
        recorder = Recorder()
        audit_res = self.execute({
            "action": "3a_sources", "stage": "audit", "run_id": "run-a", "scope_id": "scope-1",
            "accounted": SOURCE_SET, "completed_extraction_ref": SOURCE_SET, "expected_model": "gpt-5",
            "request_budget": 12, "active_budget_seconds": 300, "timeout_seconds": 120,
            "citation_guidance": "full-block", "runner": "scripts/python/account_b_route_sources.py",
        }, recorder)
        self.assertTrue(audit_res["ok"], audit_res["diagnostics"])
        argv = recorder.calls[0]
        for flag, val in (("--expected-model", "gpt-5"), ("--request-budget", "12"),
                          ("--active-budget-seconds", "300"), ("--timeout-seconds", "120"),
                          ("--citation-guidance", "full-block"), ("--completed-extraction-ref", SOURCE_SET)):
            self.assertEqual([flag, val], argv[argv.index(flag):argv.index(flag) + 2])

    def test_3b_new_uses_input_stage_3b_fresh_run_and_never_draft(self):
        self.seed_sources()
        self.seed_3a_report()
        contract = "logs/ci/contracts/c1.json"
        prepared = "logs/ci/b-route-planning-input/r0/prepared.json"
        self.repo.write(contract, {"schema_version": "test"})
        self.repo.write(prepared, {"schema_version": "test"})
        # Missing planning_contract on prepare is rejected.
        missing = self.execute({"action": "3b_capability", "invocation_mode": "new", "stage": "prepare"}, Recorder())
        self.assertFalse(missing["ok"])
        self.assertEqual("missing_required_field", missing["reason_code"])
        for action, script in (("3b_capability", "plan_capabilities.py"), ("3b_mvg", "plan_mvg.py")):
            recorder = Recorder()
            result = self.execute({"action": action, "invocation_mode": "new", "stage": "prepare",
                                   "planning_contract": contract}, recorder)
            self.assertTrue(result["ok"], result["diagnostics"])
            argv = recorder.calls[0]
            self.assertTrue(argv[2].endswith(script))
            self.assertEqual(["--input-stage", "3b"], argv[argv.index("--input-stage"):argv.index("--input-stage") + 2])
            self.assertEqual(["--planning-contract", contract],
                             argv[argv.index("--planning-contract"):argv.index("--planning-contract") + 2])
            self.assertIn("prepare", argv)
            self.assertTrue(result["run_id"].startswith("page-3b-"))
            for forbidden in ("--allow-unready-draft", "--task-id"):
                self.assertNotIn(forbidden, argv)
        # Initial new generate creates run.json from prepared_ref + planning_profile.
        gen_rec = Recorder()
        gen_res = self.execute({"action": "3b_mvg", "invocation_mode": "new", "stage": "generate",
                                "run_id": "run-gen-fresh", "prepared_ref": prepared, "planning_profile": "mvg_3b"},
                               gen_rec)
        self.assertTrue(gen_res["ok"], gen_res["diagnostics"])
        g_argv = gen_rec.calls[0]
        self.assertIn("generate", g_argv)
        self.assertEqual(["--prepared-ref", prepared], g_argv[g_argv.index("--prepared-ref"):g_argv.index("--prepared-ref") + 2])
        self.assertEqual(["--planning-profile", "mvg_3b"],
                         g_argv[g_argv.index("--planning-profile"):g_argv.index("--planning-profile") + 2])
        # Existing b-route-planning-input/<run_id> blocks new prepare.
        self.repo.write("logs/ci/b-route-planning-input/run-prep-used/prepared.json", {"x": 1})
        prep_clash = self.execute({"action": "3b_capability", "invocation_mode": "new", "stage": "prepare",
                                   "run_id": "run-prep-used", "planning_contract": contract}, Recorder())
        self.assertFalse(prep_clash["ok"])
        self.assertEqual("conflict", prep_clash["reason_code"])
        # Existing planner run dir blocks both new prepare and new generate.
        self.repo.write("logs/ci/capability-planning/run-used/run.json", {"phase": "generate"})
        recorder = Recorder()
        reused = self.execute({"action": "3b_capability", "invocation_mode": "new", "run_id": "run-used",
                               "planning_contract": contract}, recorder)
        self.assertFalse(reused["ok"])
        self.assertEqual("conflict", reused["reason_code"])
        self.assertEqual([], recorder.calls)
        reused_gen = self.execute({"action": "3b_capability", "invocation_mode": "new", "stage": "generate",
                                   "run_id": "run-used", "prepared_ref": prepared, "planning_profile": "capability_3b"},
                                  recorder)
        self.assertFalse(reused_gen["ok"])
        self.assertEqual("conflict", reused_gen["reason_code"])
        self.assertEqual([], recorder.calls)

    def test_bypass_and_malformed_requests_are_rejected_with_six_field_diagnostics(self):
        self.seed_sources()
        cases = [({"action": "3a_sources", key: True}, "conflict") for key in (
            "allow_unready", "draft", "skip_gate", "reset_budget", "switch_task_origin", "set_task_route",
            "delete_b_origin", "summary_override", "forged_resume_command", "cached_readiness", "skip_live_gate")]
        cases += [
            ({"action": "chapter6", "sub_action": "gate", "task_id": True}, "invalid_type"),
            ({"action": "3a_sources", "stage": "audit", "run_id": "r", "scope_id": "s", "request_budget": True},
             "invalid_type"),
            ({"action": "3a_sources", "stage": "audit", "run_id": "r", "scope_id": "s", "request_budget": 0},
             "invalid_argument"),
            ({"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-ok", "request_budget": 99}, "conflict"),
            ({"action": "inspect", "run_id": "   "}, "invalid_argument"),
            ({"action": "3c_task_preview", "audit_ref": "../outside.json"}, "unsafe_path"),
            ({"action": "3c_task_preview", "audit_ref": "logs\\ci\\x.json"}, "unsafe_path"),
            ({"action": "inspect", "bogus": 1}, "unknown_field"),
            ({"action": "inspect", "schema_version": "newrouge.b-route-planning-page.v9"}, "unknown_schema"),
            ({"action": "teleport"}, "invalid_enum"),
            ({"action": "inspect", "mode": "workspace"}, "invalid_enum"),
            ({"action": "inspect", "task_id": float("nan")}, "non_finite_number"),
            ({"action": "inspect", "recommendation_only": 1}, "invalid_type"),
            ({"action": "inspect", "recommendation_only": False}, "invalid_argument"),
            ({"action": "3a_sources", "stage": "prepare", "run_id": "r", "scope_id": "s",
              "recommendation_only": True}, "conflict"),
        ]
        for request, code in cases:
            with self.subTest(request=request):
                result = self.execute(request, Recorder())
                self.assertFalse(result["ok"])
                self.assertEqual(code, result["reason_code"], result["diagnostics"])
                self.assert_six(result["diagnostics"][0])
                self.assert_honest(result)


class PrefixAndResumeTests(PageTestBase):
    """AC-2 PREFIX_RESUME: committed prefix, uncommitted candidates, budget and revocation."""

    def test_prefix_candidates_budget_and_revocations_are_reported_honestly(self):
        self.seed_sources()
        self.seed_runs()
        # Add archived clear transaction and terminal run to verify P-03 coordinator accuracy.
        self.repo.write("logs/ci/mvg-recovery/clears/epoch-0.json",
                        {"schema_version": "newrouge.mvg-completed-registry.v1", "epoch": 0,
                         "entries": [{"transaction_id": "tx-arch"}], "revoked": []})
        self.repo.write("logs/ci/mvg-planning/run-archived/run.json",
                        {"phase": "generate", "input_stage": "3b", "recovery": {"epoch": 1},
                         "capability_selection": {"selected": [{"checkpoint": {"transaction_id": "tx-arch"}}],
                                                  "order": ["CAP-1", "CAP-2"], "total_invocations": 1},
                         "mvg": {"run_invocation_limit": 5}})
        self.repo.write("logs/ci/capability-planning/run-terminal/run.json",
                        {"phase": "generate", "input_stage": "3b", "terminal": True,
                         "capability_selection": {"generated": [{"id": "c1"}], "order": ["CAP-1", "CAP-2"],
                                                  "total_invocations": 5},
                         "mvg": {"run_invocation_limit": 5}})
        state = self.state()
        self.assertEqual("partial_planning", state["planning_completeness"])
        progress = state["coordinator_progress"]
        prefix = progress["committed_prefix"]
        self.assertTrue(prefix["partial_planning"])
        self.assertFalse(prefix["planning_complete"])
        self.assertFalse(prefix["runtime_verified"])
        self.assertEqual({"candidate_in_progress", "candidate_uncommitted"},
                         {c["status"] for c in progress["candidate_states"]})
        self.assertTrue(all(c["adopted"] is False and c["planning_complete"] is False
                            for c in progress["candidate_states"]))
        self.assertTrue(progress["budget_summary"]["budget_exhausted"])
        self.assertIn("run-budget", progress["budget_summary"]["exhausted_runs"])
        self.assertIn("run-terminal", progress["budget_summary"]["exhausted_runs"])
        revoked = {r["run_id"]: r for r in progress["revoked_runs"] if r["kind"] == "planner_run"}
        self.assertEqual({"run-epoch", "run-revoked", "run-archived"}, set(revoked))
        self.assertTrue(all(r["recoverable"] is False and r["revoked"] is True for r in revoked.values()))
        self.assertIn("epoch_invalidated", revoked["run-epoch"]["reasons"])
        self.assertIn("transaction_revoked", revoked["run-revoked"]["reasons"])
        self.assertIn("transaction_archived_by_clear", revoked["run-archived"]["reasons"])
        recoverable = [r["run_id"] for r in progress["recoverable_operations"] if r["kind"] == "planner_run"]
        self.assertEqual(["run-ok"], recoverable)
        for run in progress["planner_runs"]:
            if run.get("diagnostic"):
                self.assert_six(run["diagnostic"])

    def test_resume_keeps_budget_and_blocks_exhausted_or_revoked_runs(self):
        self.seed_sources()
        raw_ok = self.seed_runs()
        self.repo.write("logs/ci/b-route-planning-input/r0/prepared.json", {"ok": True})
        recorder = Recorder()
        result = self.execute({"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-ok"}, recorder)
        self.assertTrue(result["ok"], result["diagnostics"])
        argv = recorder.calls[0]
        self.assertEqual(["status", "--run-id", "run-ok", "--input-stage", "3b"], argv[argv.index("status"):argv.index("status") + 5])
        # Auto-hydrated prepared_ref and planning_profile from run.json.
        self.assertEqual(["--prepared-ref", "logs/ci/b-route-planning-input/r0/prepared.json"],
                         argv[argv.index("--prepared-ref"):argv.index("--prepared-ref") + 2])
        self.assertEqual(["--planning-profile", "mvg_3b"],
                         argv[argv.index("--planning-profile"):argv.index("--planning-profile") + 2])
        for forbidden in ("prepare", "--request-limit", "--run-invocation-limit", "--allow-unready-draft", "--request-budget"):
            self.assertNotIn(forbidden, argv)
        self.assertTrue(result["delegate"]["budget_preserved"])
        self.assertEqual(raw_ok, (self.root / "logs/ci/mvg-planning/run-ok/run.json").read_bytes())
        # Supplying mismatched planning_profile on resume is rejected with conflict.
        mismatch = self.execute({"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-ok",
                                 "planning_profile": "other_profile"}, Recorder())
        self.assertFalse(mismatch["ok"])
        self.assertEqual("conflict", mismatch["reason_code"])
        # Active reopen marker revokes resume.
        self.repo.write("logs/ci/b-route-reopen/reopen-global.json",
                        {"status": "reopened", "reopened": True, "global": True})
        reopen_blocked = self.execute({"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-ok"}, Recorder())
        self.assertFalse(reopen_blocked["ok"])
        self.assertEqual("conflict", reopen_blocked["reason_code"])
        (self.root / "logs/ci/b-route-reopen/reopen-global.json").unlink()
        for run_id, code in (("run-budget", "budget_exhausted"), ("run-epoch", "input_stale"),
                             ("run-revoked", "conflict"), ("run-missing", "file_not_found")):
            with self.subTest(run_id=run_id):
                recorder = Recorder()
                blocked = self.execute({"action": "3b_mvg", "invocation_mode": "resume", "run_id": run_id}, recorder)
                self.assertFalse(blocked["ok"])
                self.assertEqual(code, blocked["reason_code"])
                self.assertEqual([], recorder.calls)
                self.assert_six(blocked["diagnostics"][0])
        prepare = self.execute({"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-ok",
                                "stage": "prepare"}, Recorder())
        self.assertEqual("invalid_enum", prepare["reason_code"])


class DiagnosticsAndRecoveryTests(PageTestBase):
    """AC-3 DIAG_RECOVERY: verbatim diagnostics, recommendation vs execution, 3.12 gate parity."""

    def test_inspect_is_strictly_zero_write_and_recommendation_only(self):
        self.seed_sources()
        self.seed_runs()
        self.seed_pointers()
        before = self.tree()
        result = self.execute({"action": "inspect", "mode": "workspace_preview"})
        self.assertTrue(result["recommendation_only"])
        self.assertEqual([], result["pointer_guard"]["mutated"])
        self.assertEqual(before, self.tree())
        self.assert_honest(result)

    def test_normalize_keeps_valid_diagnostics_verbatim_and_wraps_others(self):
        valid = {"reason_code": "pending", "stage": "target", "entity_id": "op-1", "expected": {"a": [1]},
                 "actual": "applying", "resume_ref": "logs/ci/b-route-operations/operations/op-1/journal.json"}
        self.assertEqual(valid, page.normalize_diagnostic(dict(valid)))
        wrapped = page.normalize_diagnostic({"reason": "budget exhausted"}, entity="run-1")
        self.assert_six(wrapped)
        self.assertEqual("conflict", wrapped["reason_code"])
        self.assertIn("budget exhausted", wrapped["actual"])

    def test_chapter6_uses_story_312_gate_with_identical_decisions(self):
        from _b_route_entrypoint_parity import handle_page_b_route_trigger
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        for task_id in (1, 2, 999):
            with self.subTest(task_id=task_id):
                direct = handle_page_b_route_trigger(self.root, {"action": "gate", "task_id": task_id,
                                                                 "mode": "workspace", "recommendation_only": True})
                result = self.execute({"action": "chapter6", "sub_action": "gate", "task_id": task_id,
                                       "mode": "attempt", "recommendation_only": True})
                self.assertTrue(result["recommendation_only"])
                self.assertEqual(bool(direct.get("ok")), result["ok"])
                self.assertEqual(direct.get("route"), result["route"])
                self.assertEqual([page.normalize_diagnostic(d) for d in direct.get("diagnostics") or []],
                                 result["diagnostics"][:len(direct.get("diagnostics") or [])])
                self.assert_honest(result)
        state = self.state()
        evidence = state["stage_gates"]["stage_6_implement"]["evidence"]
        self.assertGreaterEqual(evidence["non_flow_governed_requirements"], 1)
        self.assertFalse(evidence["non_flow_requires_flow_or_scene"])
        self.assertTrue(page.is_read_only_request(self.root, {"action": "chapter6", "sub_action": "gate", "task_id": 1}))
        self.assertFalse(page.is_read_only_request(self.root, {"action": "chapter6", "sub_action": "execute",
                                                               "task_id": 1, "recommendation_only": False}))
        self.assertFalse(page.is_read_only_request(self.root, {"action": "3a_sources", "stage": "prepare"}))

    def test_pending_journal_blocks_3c_and_surfaces_recoverable_operation(self):
        import hashlib
        self.seed_sources()
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.assertTrue(self.state()["stage_gates"]["stage_3c_tasks"]["allowed"])
        # 3c_task_compile prepare requires request_ref when 3C gate passes.
        no_req = self.execute({"action": "3c_task_compile", "stage": "prepare", "operation_id": "op-no-req"}, Recorder())
        self.assertFalse(no_req["ok"])
        self.assertEqual("missing_required_field", no_req["reason_code"])
        # 3c_task_preview forwards protection_ref and change_intents.
        self.repo.write("logs/ci/prot.json", {"ok": True})
        self.repo.write("logs/ci/intents.json", {"ok": True})
        prev_rec = Recorder()
        prev_res = self.execute({"action": "3c_task_preview", "plan_id": "p", "run_id": "r1",
                                 "audit_ref": SOURCE_SET, "scope_id": "scope-1",
                                 "protection_ref": "logs/ci/prot.json", "change_intents": "logs/ci/intents.json"},
                                prev_rec)
        self.assertTrue(prev_res["ok"], prev_res["diagnostics"])
        self.assertIn("--protection-ref", prev_rec.calls[0])
        self.assertIn("--change-intents", prev_rec.calls[0])
        # Adoption operation lookup uses sha256(operation_id) directory per _planning_apply_journal.py.
        op_hash = hashlib.sha256(b"op-1").hexdigest()
        hashed_dir = f"logs/ci/b-route-operations/operations/{op_hash}"
        self.repo.write(f"{hashed_dir}/operation.json", {"status": "applying", "operation_id": "op-1"})
        state = self.state(operation_id="op-1")
        gate = state["stage_gates"]["stage_3c_tasks"]
        self.assertFalse(gate["allowed"])
        self.assertIn("pending", {d["reason_code"] for d in gate["diagnostics"]})
        operation = next(r for r in state["coordinator_progress"]["recoverable_operations"]
                         if r["kind"] == "adoption_operation")
        self.assertTrue(operation["pending"])
        self.assertEqual("pending", operation["diagnostic"]["reason_code"])
        self.assertEqual(hashed_dir, operation["original_locator"])
        self.assertEqual(1, len(operation["journals"]))
        recorder = Recorder()
        blocked = self.execute({"action": "3c_task_compile", "stage": "prepare", "operation_id": "op-2",
                                "request_ref": SOURCE_SET}, recorder)
        self.assertFalse(blocked["ok"])
        self.assertEqual("pending", blocked["reason_code"])
        self.assertEqual([], recorder.calls)


class IdentityGuardTests(PageTestBase):
    """AC-4 IDENTITY_GUARD: Story 4.6 identity parity and zero pointer mutation."""

    def test_identity_matches_story_46_for_every_mode_without_pointer_mutation(self):
        self.seed_sources()
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.repo.commit_main()
        self.seed_pointers()
        for mode in projection.VALID_MODES:
            with self.subTest(mode=mode):
                before = page.snapshot_pointers(self.root)
                direct = projection.build_b_route_knowledge_projection(self.root, mode=mode)
                state = self.state(mode=mode)
                self.assertEqual(direct["provenance"], state["provenance"])
                self.assertEqual(direct["planning_completeness"], state["planning_completeness"])
                self.assertEqual(direct["status"], state["status"])
                self.assertEqual(mode == "main", state["provenance"]["is_main_fact"])
                result = self.execute({"action": "inspect", "mode": mode})
                self.assertEqual([], result["pointer_guard"]["mutated"])
                self.assertEqual(before, page.snapshot_pointers(self.root))
                self.assertFalse(result["implicit_global_refresh_performed"])
        # mode="main" reads committed source-set from refs/heads/main, ignoring dirty workspace edits.
        self.repo.write(SOURCE_SET, b"{broken-workspace-only")
        main_state = self.state(mode="main")
        ws_state = self.state(mode="workspace_preview")
        self.assertTrue(main_state["stage_gates"]["stage_3a_sources"]["allowed"])
        self.assertEqual("refs/heads/main", main_state["stage_gates"]["stage_3a_sources"]["evidence"]["snapshot_source"])
        self.assertFalse(ws_state["stage_gates"]["stage_3a_sources"]["allowed"])

    def test_delegate_that_mutates_pointers_is_rejected(self):
        self.seed_sources()
        self.seed_pointers()

        def mutate():
            self.repo.write("knowledge/indexes/current.json", {"pointer": "advanced"})

        result = self.execute({"action": "3a_sources", "stage": "prepare", "run_id": "r1", "scope_id": "s1"},
                              Recorder(effect=mutate))
        self.assertFalse(result["ok"])
        self.assertIn("knowledge/indexes/current.json", result["pointer_guard"]["mutated"])
        self.assertEqual("knowledge-pointers", result["diagnostics"][-1]["entity_id"])


class ParityHonestyTests(PageTestBase):
    """AC-5 PARITY_HONESTY: page HTTP, dev_cli and direct service share decisions."""

    def cli_run(self, request):
        proc = subprocess.run([PYTHON, "-B", str(ROOT / "scripts/python/dev_cli.py"), "b-route-planning-page",
                               "--root", str(self.root), "--request-json", json.dumps(request)],
                              capture_output=True, text=True, encoding="utf-8", timeout=600,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return proc.returncode, json.loads(proc.stdout)

    def test_three_way_parity_http_cli_direct(self):
        from _project_health_http import handler_factory
        self.seed_sources()
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        # Add task 3 as a legal non-Flow task (other_verification_refs) alongside B task 1 and frozen A task 2.
        tasks_doc = json.loads((self.root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        tasks_doc["master"]["tasks"].append({"id": 3, "title": "Non-flow ADR rule", "status": "pending",
                                             "dependencies": [], "details": "docs/adr/ADR-9000-fixture.md"})
        self.repo.write(".taskmaster/tasks/tasks.json", tasks_doc)
        self.seed_runs()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port

        def request(method, path, body=None, token=None, origin=True):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=600)
            headers = {}
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers.update({"Content-Type": "application/json", "Content-Length": str(len(data))})
            if origin:
                headers["Origin"] = f"http://127.0.0.1:{port}"
            if token:
                headers["X-Project-Health-Token"] = token
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            code, raw = response.status, response.read()
            connection.close()
            return code, json.loads(raw)

        try:
            token = request("GET", "/api/knowledge/session")[1]["token"]
            cases = [
                {"action": "inspect", "mode": "workspace_preview"},
                {"action": "3c_task_preview", "plan_id": "p", "run_id": "r", "scope_id": "s",
                 "audit_ref": SOURCE_SET},
                {"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-budget"},
                {"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-epoch"},
                {"action": "3a_sources", "stage": "prepare", "allow_unready": True},
                {"action": "3b_capability", "draft": True},
                {"action": "chapter6", "sub_action": "gate", "recommendation_only": True},
                {"action": "chapter6", "sub_action": "gate", "task_id": 1, "recommendation_only": True},
                {"action": "chapter6", "sub_action": "gate", "task_id": 2, "recommendation_only": True},
                {"action": "chapter6", "sub_action": "gate", "task_id": 3, "recommendation_only": True},
            ]
            for body in cases:
                with self.subTest(body=body):
                    direct = self.execute(body)
                    code, http_payload = request("POST", "/api/knowledge/b-route-planning", body, token)
                    exit_code, cli_payload = self.cli_run(body)
                    self.assertEqual(200 if direct["ok"] else 422, code)
                    self.assertEqual(0 if direct["ok"] else 2, exit_code)
                    for payload in (http_payload, cli_payload):
                        self.assertEqual(direct["ok"], payload["ok"])
                        self.assertEqual(direct["status"], payload["status"])
                        self.assertEqual(direct["reason_code"], payload["reason_code"])
                        self.assertEqual([d["reason_code"] for d in direct["diagnostics"]],
                                         [d["reason_code"] for d in payload["diagnostics"]])
                        if "route" in direct:
                            self.assertEqual(direct["route"], payload.get("route"))
                        self.assert_honest(payload)
                    if body["action"] == "inspect":
                        gates = {k: v["allowed"] for k, v in direct["state"]["stage_gates"].items()}
                        for payload in (http_payload, cli_payload):
                            self.assertEqual(gates, {k: v["allowed"] for k, v in payload["state"]["stage_gates"].items()})
            self.assertEqual(403, request("POST", "/api/knowledge/b-route-planning", {"action": "inspect"})[0])
            base = "/api/knowledge/b-route-planning"
            code, payload = request("GET", base + "?mode=workspace_preview")
            self.assertEqual(200, code)
            self.assertEqual(page.SCHEMA_VERSION, payload["schema_version"])
            self.assertEqual(self.state()["stage_gates"]["stage_3a_sources"]["allowed"],
                             payload["stage_gates"]["stage_3a_sources"]["allowed"])
            code_bad_mode, payload_bad_mode = request("GET", base + "?mode=bogus")
            self.assertEqual(400, code_bad_mode)
            self.assertEqual(page.SCHEMA_VERSION, payload_bad_mode["schema_version"])
            self.assertIs(True, payload_bad_mode["ui_contract_only_not_godot_gameplay"])
            self.assertEqual(page.INVARIANTS, payload_bad_mode["invariants"])
            self.assertEqual(400, request("GET", base + "?mode=main&mode=attempt")[0])
            for query in ("mode=main&task_id=", "mode=main&foo=1", "mode=main&run_id=a&run_id=b",
                          "mode=main&strict=yes", "mode=main&run_id=..%2Fx"):
                with self.subTest(query=query):
                    code, payload = request("GET", base + "?" + query)
                    self.assertEqual(422, code)
                    self.assertEqual(page.SCHEMA_VERSION, payload["schema_version"])
                    self.assertIs(True, payload["ui_contract_only_not_godot_gameplay"])
                    self.assertEqual(page.INVARIANTS, payload["invariants"])
                    self.assert_six(payload["diagnostics"][0])
            self.repo.write(CATALOG, b"{broken")
            code, payload = request("GET", base + "?mode=workspace_preview")
            self.assertEqual(200, code)
            self.assertFalse(payload["stage_gates"]["stage_3c_tasks"]["allowed"])
            self.assertEqual(422, request("GET", base + "?mode=workspace_preview&strict=1")[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_unknown_catalog_schema_blocks_3c_identically(self):
        self.seed_sources()
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        catalog = json.loads((self.root / CATALOG).read_text())
        catalog["schema_version"] = "newrouge.b-route-catalog.v999"
        self.repo.write(CATALOG, catalog)
        state = self.state()
        gate = state["stage_gates"]["stage_3c_tasks"]
        self.assertFalse(gate["allowed"])
        for diagnostic in gate["diagnostics"]:
            self.assert_six(diagnostic)
        body = {"action": "3c_task_compile", "stage": "prepare", "operation_id": "op-9", "request_ref": SOURCE_SET}
        direct = self.execute(body, Recorder())
        exit_code, cli_payload = self.cli_run(body)
        self.assertFalse(direct["ok"])
        self.assertEqual(2, exit_code)
        self.assertEqual(direct["reason_code"], cli_payload["reason_code"])

    def test_cli_report_confinement_and_help(self):
        self.seed_sources()
        for report in ("docs/report.json", "logs/ci/mvg-recovery/registry.json",
                       "logs/ci/project-health-knowledge/latest.json", "logs/ci/mvg-planning/x/report.json"):
            with self.subTest(report=report):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main(["--root", str(self.root), "--report", report])
                self.assertEqual(2, code)
                self.assert_six(json.loads(buffer.getvalue())["diagnostics"][0])
        self.assertFalse((self.root / "logs/ci/mvg-recovery/registry.json").exists())
        for argv in (["--allow-unready"], ["--draft"], ["--reset-budget"], ["--action", "bogus"]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.assertEqual(2, cli.main(["--root", str(self.root), *argv]))
            self.assert_six(json.loads(buffer.getvalue())["diagnostics"][0])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["--root", str(self.root), "--report", "logs/ci/page/report.json"])
        self.assertEqual(0, code, buffer.getvalue()[-2000:])
        self.assertTrue((self.root / "logs/ci/page/report.json").is_file())
        help_proc = subprocess.run([PYTHON, "-B", str(ROOT / "scripts/python/dev_cli.py"), "b-route-planning-page",
                                    "--help"], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(0, help_proc.returncode, help_proc.stderr)
        self.assertIn("--invocation-mode", help_proc.stdout)

    def _junction_or_skip(self, link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=target.is_dir())
            return
        except OSError:
            if os.name == "nt" and target.is_dir():
                proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                      capture_output=True, text=True, timeout=30)
                if proc.returncode == 0 and os.path.lexists(link):
                    return
            self.skipTest("symlink/junction creation not permitted")

    def test_report_symlink_is_rejected(self):
        self.seed_sources()
        outside_dir = Path(self.temp.name) / "outside_dir"
        outside_dir.mkdir(parents=True, exist_ok=True)
        link = self.root / "logs/ci/page"
        self._junction_or_skip(link, outside_dir)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["--root", str(self.root), "--report", "logs/ci/page/report.json"])
        self.assertEqual(2, code)
        self.assertEqual("unsafe_path", json.loads(buffer.getvalue())["diagnostics"][0]["reason_code"])
        self.assertEqual([], list(outside_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
