"""Deterministic tests for Story 3.9 live Chapter 6 recovery and route revalidation.

Covers all 5 Story 3.9 matrix scenarios (REC_READONLY, STALE_PEND, STATUS_HEAD,
MID_DRIFT, BUDGET_REOPEN) plus top-level legacy journal scanning and mid-read drift
in _b_route_task_resolver, using setUpClass fixture caching for fast execution.
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
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
REPO_ROOT = SCRIPTS_PY.parents[1]
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(SCRIPTS_SC / "build"), str(SCRIPTS_PY / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_rec
import _b_route_codec as codec
import _b_route_operation_scope as op_scope
import _b_route_task_resolver as task_resolver
from _mvg_capability_checkpoint import coordinator_lock
import chapter6_route
import inspect_run
import resume_task

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


def _create_pipeline_run(
    root: Path,
    task_id: int,
    run_id: str,
    *,
    date_str: str = "2026-11-24",
    status: str = "ok",
    reason: str = "pipeline_clean",
    failed_step: str = "",
    diagnostics: dict | None = None,
    write_latest: bool = True,
    write_active_task: bool = True,
    mismatched_active_latest: bool = False,
    low_priority_review: bool = False,
    max_step_retries: int | None = None,
    step_attempts: int = 1,
) -> Path:
    out_dir = root / "logs" / "ci" / date_str / f"sc-review-pipeline-task-{task_id}-{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    diag_map = dict(diagnostics or {})
    summary_payload = {
        "cmd": "sc-review-pipeline",
        "task_id": str(task_id),
        "requested_run_id": run_id,
        "run_id": run_id,
        "allow_overwrite": False,
        "force_new_run_id": False,
        "status": status,
        "reason": reason,
        "run_type": "full",
        "reuse_mode": "none",
        "steps": [
            {
                "name": "sc-test",
                "cmd": ["py", "-3", "scripts/sc/test.py"],
                "rc": 1 if failed_step == "sc-test" else 0,
                "status": "fail" if failed_step == "sc-test" else "ok",
                "log": str(out_dir / "sc-test.log"),
            },
            {
                "name": "sc-acceptance-check",
                "cmd": ["py", "-3", "scripts/sc/acceptance_check.py"],
                "rc": 0,
                "status": "ok",
                "log": str(out_dir / "sc-acceptance-check.log"),
            },
            {
                "name": "sc-llm-review",
                "cmd": ["py", "-3", "scripts/sc/llm_review.py"],
                "rc": 0,
                "status": "ok",
                "log": str(out_dir / "sc-llm-review.log"),
            },
        ],
        "started_at_utc": f"{date_str}T00:00:00+00:00",
        "finished_at_utc": f"{date_str}T00:01:00+00:00",
        "elapsed_sec": 60,
        "diagnostics": diag_map,
    }
    _put_json(root, out_dir.relative_to(root).as_posix() + "/summary.json", summary_payload)
    _put_json(
        root,
        out_dir.relative_to(root).as_posix() + "/execution-context.json",
        {
            "cmd": "sc-review-pipeline",
            "task_id": str(task_id),
            "run_id": run_id,
            "status": status,
            "failed_step": failed_step,
            "delivery_profile": "fast-ship",
            "security_profile": "host-safe",
            "diagnostics": diag_map,
            "git": {"head": "deadbeef", "status_short": []},
        },
    )
    _put_json(
        root,
        out_dir.relative_to(root).as_posix() + "/repair-guide.json",
        {
            "status": "not-needed" if status == "ok" else "needs-fix",
            "task_id": str(task_id),
            "summary_status": status,
            "failed_step": failed_step,
            "recommendations": [],
        },
    )
    (out_dir / "repair-guide.md").write_text("# repair\n", encoding="utf-8")
    (out_dir / "run-events.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "ts": f"{date_str}T00:01:00Z",
                "event": "run_completed",
                "task_id": str(task_id),
                "run_id": run_id,
                "delivery_profile": "fast-ship",
                "security_profile": "host-safe",
                "step_name": None,
                "status": status,
                "details": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if max_step_retries is not None:
        _put_json(
            root,
            out_dir.relative_to(root).as_posix() + "/marathon-state.json",
            {
                "task_id": str(task_id),
                "run_id": run_id,
                "status": "stopped" if status != "ok" else "ok",
                "stop_reason": reason,
                "max_step_retries": max_step_retries,
                "resume_count": 1,
                "diagnostics": diag_map,
                "steps": {
                    failed_step or "sc-test": {
                        "status": status,
                        "attempt_count": step_attempts,
                    }
                },
            },
        )
    if low_priority_review:
        _put_json(
            root,
            out_dir.relative_to(root).as_posix() + "/agent-review.json",
            {
                "review_verdict": "needs-fix",
                "findings": [
                    {
                        "finding_id": "llm-p2-1",
                        "severity": "medium",
                        "category": "llm-review",
                        "owner_step": "sc-llm-review",
                        "message": "Minor style suggestion.",
                    }
                ],
            },
        )
        _put_json(
            root,
            out_dir.relative_to(root).as_posix() + "/llm-review-low-priority-findings.json",
            {
                "findings": [
                    {
                        "finding_id": "llm-p2-1",
                        "severity": "P2",
                        "agent": "code-reviewer",
                        "message": "Minor style suggestion.",
                        "source_path": "Game.Core/Reward/Service.cs",
                    }
                ]
            },
        )
    latest_rel = f"logs/ci/{date_str}/sc-review-pipeline-task-{task_id}/latest.json"
    if write_latest:
        _put_json(
            root,
            latest_rel,
            {
                "task_id": str(task_id),
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "latest_out_dir": str(out_dir),
                "summary_path": str(out_dir / "summary.json"),
                "execution_context_path": str(out_dir / "execution-context.json"),
                "repair_guide_json_path": str(out_dir / "repair-guide.json"),
                "repair_guide_md_path": str(out_dir / "repair-guide.md"),
                "run_events_path": str(out_dir / "run-events.jsonl"),
            },
        )
    if write_active_task:
        reported_latest = (
            f"logs/ci/2026-11-20/sc-review-pipeline-task-{task_id}/latest.json"
            if mismatched_active_latest
            else latest_rel
        )
        _put_json(
            root,
            f"logs/ci/active-tasks/task-{task_id}.active.json",
            {
                "task_id": str(task_id),
                "run_id": run_id,
                "status": "ok",
                "recommended_action": "continue",
                "recommended_action_why": "Cached active task says ready/ok.",
                "paths": {"latest_json": reported_latest, "out_dir": str(out_dir)},
            },
        )
    return out_dir


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    for item in sorted(root.rglob("*")):
        if item.is_file():
            snap[item.relative_to(root).as_posix()] = item.read_bytes()
    return snap


class BRouteChapter6RecoveryTests(unittest.TestCase):
    _cache_dir: tempfile.TemporaryDirectory | None = None
    _b_ready_base: Path
    _b_dep_ready_base: Path
    _explicit_a_base: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls._cache_dir = tempfile.TemporaryDirectory(prefix="story39-cache-")
        cache = Path(cls._cache_dir.name)

        # 1. Ready B-route repo (task 101 flow ready, task 103 with keep deps 101+102)
        cls._b_ready_base = cache / "b_ready"
        cls._b_ready_base.mkdir()
        _build_b_route_base_repo(cls._b_ready_base, mode="flow")
        _reconcile_task_ready(cls._b_ready_base, 101, mode="flow")

        # 2. Ready B-route repo where task 101 & 102 are done so task 103 is eligible
        cls._b_dep_ready_base = cache / "b_dep_ready"
        shutil.copytree(cls._b_ready_base, cls._b_dep_ready_base)
        master_p = cls._b_dep_ready_base / ".taskmaster/tasks/tasks.json"
        mdoc = json.loads(master_p.read_text(encoding="utf-8"))
        for row in mdoc["master"]["tasks"]:
            if row["id"] in (101, 102):
                row["status"] = "done"
            elif row["id"] == 103:
                row["status"] = "in-progress"
        master_p.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        _reconcile_task_ready(cls._b_dep_ready_base, 103, mode="flow")

        # 3. Pure explicit_not_enabled_a repo
        cls._explicit_a_base = cache / "explicit_a"
        cls._explicit_a_base.mkdir()
        _build_explicit_not_enabled_a_repo(cls._explicit_a_base)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._cache_dir is not None:
            cls._cache_dir.cleanup()

    def _clone(self, src: Path) -> Path:
        td = tempfile.TemporaryDirectory(prefix="story39-case-")
        self.addCleanup(td.cleanup)
        dst = Path(td.name) / "repo"
        shutil.copytree(src, dst)
        return dst

    # ------------------------------------------------------------------
    # Scenario 1: REC_READONLY
    # ------------------------------------------------------------------
    def test_01_rec_readonly_zero_write_and_never_trusts_cached_ready(self) -> None:
        root = self._clone(self._b_ready_base)
        _create_pipeline_run(
            root,
            101,
            "run-101-a",
            status="ok",
            mismatched_active_latest=True,
            low_priority_review=True,
        )
        before = _snapshot_tree(root)

        # resume-task --recommendation-only MUST NOT repair active-task or write out-json/out-md!
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = resume_task.main(
                [
                    "--repo-root",
                    str(root),
                    "--task-id",
                    "101",
                    "--recommendation-only",
                    "--recommendation-format",
                    "json",
                    "--out-json",
                    "logs/ci/should-not-exist.json",
                    "--out-md",
                    "logs/ci/should-not-exist.md",
                ]
            )
        self.assertEqual(0, rc)
        self.assertEqual(before, _snapshot_tree(root))

        # chapter6-route --recommendation-only --record-residual MUST NOT write docs/technical-debt.md or out-json!
        stdout2 = io.StringIO()
        with redirect_stdout(stdout2):
            rc2 = chapter6_route.main(
                [
                    "--repo-root",
                    str(root),
                    "--task-id",
                    "101",
                    "--recommendation-only",
                    "--recommendation-format",
                    "json",
                    "--record-residual",
                    "--out-json",
                    "logs/ci/route-should-not-exist.json",
                ]
            )
        self.assertEqual(0, rc2)
        self.assertEqual(before.get("docs/technical-debt.md"), _snapshot_tree(root).get("docs/technical-debt.md"))
        self.assertEqual(before, _snapshot_tree(root))

        # inspect-run --recommendation-only MUST NOT write out-json, and attaches live b_route_recovery.
        stdout3 = io.StringIO()
        with redirect_stdout(stdout3):
            rc3 = inspect_run.inspect_run_artifacts(repo_root=root, kind="pipeline", task_id="101")
        self.assertEqual(0, rc3[0])
        self.assertIn("b_route_recovery", rc3[1])
        self.assertFalse(rc3[1]["runtime_verified"])
        self.assertFalse(rc3[1]["default_b_enabled"])
        self.assertEqual(before, _snapshot_tree(root))

        # Now drift a live contract file while keeping cached summary/active-task status="ok"!
        contract = root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs"
        contract.write_text(contract.read_text(encoding="utf-8") + "// drifted\n", encoding="utf-8")
        res = ch6_rec.evaluate_chapter6_recovery(root, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res["ok"])
        self.assertFalse(res["execution_allowed"])
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])
        self.assertEqual("4", res["return_stage"])
        self.assertTrue(res["diagnostics"])
        self.assertEqual(DIAGNOSTIC_KEYS, set(res["diagnostics"][0].keys()))

        # resume-task and chapter6-route MUST block fail-closed despite cached ok!
        r_rc, r_payload = resume_task.build_resume_payload(
            repo_root=root, task_id="101", latest="", run_id="", recommendation_only=True
        )
        self.assertEqual(2, r_rc)
        self.assertEqual("blocked-by-b-route-gate", r_payload["recommended_action"])
        self.assertEqual("", r_payload["recommended_command"])
        self.assertEqual("4", r_payload["return_stage"])

        c_rc, c_payload = chapter6_route.route_chapter6(
            repo_root=root, task_id="101", recommendation_only=True
        )
        self.assertEqual(3, c_rc)
        self.assertEqual("blocked-by-b-route-gate", c_payload["preferred_lane"])
        self.assertFalse(c_payload["execution_allowed"])
        self.assertEqual("4", c_payload["return_stage"])

    def test_02_explicit_not_enabled_a_passthrough_zero_write_and_invalid_task_id(self) -> None:
        root = self._clone(self._explicit_a_base)
        before = _snapshot_tree(root)
        res = ch6_rec.evaluate_chapter6_recovery(root, 11, operation="resume", recommendation_only=True)
        self.assertTrue(res["ok"])
        self.assertTrue(res["legacy_a_passthrough"])
        self.assertEqual("explicit_not_enabled_a", res["route"])
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])
        self.assertEqual(before, _snapshot_tree(root))

        # Non-ASCII superscript digit must fail closed with invalid_argument + 6-field Diagnostic.
        bad = ch6_rec.evaluate_chapter6_recovery(root, "\u00b9", operation="resume", recommendation_only=True)
        self.assertFalse(bad["ok"])
        self.assertEqual("invalid_argument", bad["reason_code"])
        self.assertFalse(bad["runtime_verified"])
        self.assertFalse(bad["default_b_enabled"])
        self.assertEqual(DIAGNOSTIC_KEYS, set(bad["diagnostics"][0].keys()))

    # ------------------------------------------------------------------
    # Scenario 2: STALE_PEND
    # ------------------------------------------------------------------
    def test_03_stale_pend_capability_marker_legacy_journal_and_old_done_reverify(self) -> None:
        # 2a. Pending capability-apply.pending.json with valid Epic 2 legacy journal blocks with original resume_ref.
        root = self._clone(self._b_ready_base)
        target_rel = "docs/planning/semantic-topology/capabilities.v1.json"
        cap_payload = {"schema_version": "newrouge.capabilities.v1", "capabilities": []}
        cap_after = codec.raw_digest((json.dumps(cap_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        _put(root, target_rel, (json.dumps(cap_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        _put_json(
            root,
            "logs/ci/capability-planning/run-cap-1/run.json",
            {
                "schema_version": "newrouge.capability-planning-run.v1",
                "run_id": "run-cap-1",
                "phase": "applying",
            },
        )
        j_rel = "logs/ci/capability-planning/run-cap-1/apply-journal.json"
        _put_json(
            root,
            j_rel,
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "status": "pending",
                "authority_inputs": {},
                "entries": [
                    {
                        "path": target_rel,
                        "before_sha256": None,
                        "before_base64": None,
                        "after_sha256": cap_after,
                        "payload": cap_payload,
                    }
                ],
                "result": {},
            },
        )
        _put_json(
            root,
            op_scope.CAP_PENDING,
            {"run_id": "run-cap-1", "journal_path": j_rel},
        )
        res = ch6_rec.evaluate_chapter6_recovery(root, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res["ok"])
        self.assertEqual("pending", res["reason_code"])
        self.assertEqual(j_rel, res["resume_ref"])
        self.assertEqual("plan_capabilities.apply", res["pending_check"]["legacy_routes"][0]["owner_api"])
        self.assertEqual(DIAGNOSTIC_KEYS, set(res["diagnostics"][0].keys()))

        # 2b. Damaged capability-apply.pending.json fails closed with 6-field Diagnostic.
        (root / op_scope.CAP_PENDING).write_text("null\n", encoding="utf-8")
        res_dmg = ch6_rec.evaluate_chapter6_recovery(root, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res_dmg["ok"])
        self.assertEqual("identity_unprovable", res_dmg["reason_code"])
        self.assertEqual(op_scope.CAP_PENDING, res_dmg["resume_ref"])

        # 2c. Old done Task with new obligations surfaces requires_chapter6_reverification=True (never masked).
        root_done = self._clone(self._b_ready_base)
        mp = root_done / ".taskmaster/tasks/tasks.json"
        mdoc = json.loads(mp.read_text(encoding="utf-8"))
        for row in mdoc["master"]["tasks"]:
            if row["id"] == 101:
                row["status"] = "done"
        mp.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        res_done = ch6_rec.evaluate_chapter6_recovery(root_done, 101, operation="resume", recommendation_only=True)
        self.assertTrue(res_done["ok"])
        self.assertTrue(res_done["requires_chapter6_reverification"])
        self.assertFalse(res_done["old_done_covers_new_obligations"])

    # ------------------------------------------------------------------
    # Scenario 3: STATUS_HEAD
    # ------------------------------------------------------------------
    def test_04_status_head_allows_status_only_and_blocks_reverted_dependency(self) -> None:
        root = self._clone(self._b_dep_ready_base)
        # Freeze baseline while Task 103 is in-progress (NOT done!) and deps 101/102 are done.
        out_dir = _create_pipeline_run(root, 103, "run-103-a", status="ok")
        res0 = ch6_rec.evaluate_chapter6_recovery(root, 103, operation="resume", recommendation_only=True)
        self.assertTrue(res0["ok"], res0)
        self.assertFalse(res0["self_done_required"])
        ch6_rec.write_recovery_input_set(root, out_dir, res0)

        # Advance only an unrelated task's status AND move current task 103 from in-progress -> pending (not done!).
        mp = root / ".taskmaster/tasks/tasks.json"
        mdoc = json.loads(mp.read_text(encoding="utf-8"))
        for row in mdoc["master"]["tasks"]:
            if row["id"] == 103:
                row["status"] = "pending"
            elif row["id"] == 201:
                row["status"] = "done"
        mp.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        # Also create an unrelated file / simulate HEAD move outside task 103's InputSet.
        _put(root, "docs/notes/unrelated-head-change.md", "unrelated\n")

        res1 = ch6_rec.evaluate_chapter6_recovery(root, 103, run_dir=out_dir, operation="resume", recommendation_only=True)
        self.assertTrue(res1["ok"], res1)
        self.assertEqual(res0["input_set_digest"], res1["input_set_digest"])

        # Now dynamically revert required keep dependency 101 from done -> in-progress: MUST block!
        for row in mdoc["master"]["tasks"]:
            if row["id"] == 101:
                row["status"] = "in-progress"
        mp.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")

        res_dep = ch6_rec.evaluate_chapter6_recovery(root, 103, run_dir=out_dir, operation="resume", recommendation_only=True)
        self.assertFalse(res_dep["ok"])
        self.assertEqual("conflict", res_dep["reason_code"])
        self.assertEqual("3C", res_dep["return_stage"])
        self.assertIn("dependency_not_done:101", res_dep["reason"])

        # Restore dependency 101 -> done: immediately eligible again without regenerating anything!
        for row in mdoc["master"]["tasks"]:
            if row["id"] == 101:
                row["status"] = "done"
        mp.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        res_ok = ch6_rec.evaluate_chapter6_recovery(root, 103, run_dir=out_dir, operation="resume", recommendation_only=True)
        self.assertTrue(res_ok["ok"], res_ok)

    # ------------------------------------------------------------------
    # Scenario 4: MID_DRIFT
    # ------------------------------------------------------------------
    def test_05_mid_drift_locks_frozen_baseline_and_preserves_post_edits(self) -> None:
        root = self._clone(self._b_ready_base)
        out_dir = _create_pipeline_run(root, 101, "run-101-mid", status="ok")

        # 4a. guarded_chapter6_recovery holds business scope locks, NEVER writer:planning, and writes recovery-input-set.json.
        with ch6_rec.guarded_chapter6_recovery(root, 101, out_dir=out_dir, operation="resume", consumer="test") as handle:
            self.assertFalse(handle.uses_global_writer_lock)
            self.assertTrue((out_dir / ch6_rec.RECOVERY_INPUT_SET_FILENAME).is_file())
            # Verify global writer:planning is NOT held!
            writer_dir = root / op_scope.STORE / "locks/scopes" / op_scope._hash(op_scope.WRITER_SCOPE)
            writer_dir.mkdir(parents=True, exist_ok=True)
            with coordinator_lock(writer_dir):
                pass
            # Child reentrancy using parent lease receipt must succeed!
            with ch6_rec.guarded_chapter6_recovery(root, 101, run_dir=out_dir, operation="resume", consumer="child") as child:
                self.assertTrue(child.inherited_lease)

            # Mid-recovery drift: mutate contract before next boundary -> revalidate_boundary aborts!
            contract = root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs"
            contract.write_text(contract.read_text(encoding="utf-8") + "// mid-drift\n", encoding="utf-8")
            with self.assertRaises(ch6_rec.Chapter6RecoveryBlockedError) as ctx:
                handle.revalidate_boundary("sc-llm-review", model_invocation=True)
            self.assertEqual("4", ctx.exception.recovery_result["return_stage"])

        # 4b. Prior run frozen baseline mismatch (simulated binding replacement / new plan join) blocks resuming that run.
        root2 = self._clone(self._b_ready_base)
        out_dir2 = _create_pipeline_run(root2, 101, "run-101-old-plan", status="ok")
        res_live = ch6_rec.evaluate_chapter6_recovery(root2, 101, operation="resume", recommendation_only=True)
        self.assertTrue(res_live["ok"])
        frozen_p = ch6_rec.write_recovery_input_set(root2, out_dir2, res_live)
        fdoc = json.loads(frozen_p.read_text(encoding="utf-8"))
        fdoc["applicable_set_digest"] = "sha256:" + ("0" * 64)
        fdoc["scope_ids"] = sorted(set(fdoc["scope_ids"]) | {"plan:PLAN-EXTRA-JOIN"})
        frozen_p.write_text(json.dumps(fdoc, indent=2) + "\n", encoding="utf-8")

        res_join = ch6_rec.evaluate_chapter6_recovery(root2, 101, run_dir=out_dir2, operation="resume", recommendation_only=True)
        self.assertFalse(res_join["ok"])
        self.assertEqual("input_stale", res_join["reason_code"])
        self.assertEqual("3C", res_join["return_stage"])

        # 4c. Post-edit preservation on unfinished legacy journal: live bytes differ from before/after -> halt & preserve!
        root3 = self._clone(self._b_ready_base)
        target_rel = "docs/planning/semantic-topology/capabilities.v1.json"
        planned_payload = {"schema_version": "newrouge.capabilities.v1", "capabilities": [{"id": "CAP-1"}]}
        planned_after = codec.raw_digest((json.dumps(planned_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        user_bytes = b'{"user_post_edit": true}\n'
        _put(root3, target_rel, user_bytes)
        _put_json(
            root3,
            "logs/ci/capability-planning/run-postedit/run.json",
            {
                "schema_version": "newrouge.capability-planning-run.v1",
                "run_id": "run-postedit",
                "phase": "applying",
            },
        )
        j_rel = "logs/ci/capability-planning/run-postedit/apply-journal.json"
        _put_json(
            root3,
            j_rel,
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "status": "pending",
                "authority_inputs": {},
                "entries": [
                    {
                        "path": target_rel,
                        "before_sha256": None,
                        "before_base64": None,
                        "after_sha256": planned_after,
                        "payload": planned_payload,
                    }
                ],
                "result": {},
            },
        )
        res_pe = ch6_rec.evaluate_chapter6_recovery(root3, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res_pe["ok"])
        self.assertEqual("conflict", res_pe["reason_code"])
        self.assertEqual(j_rel, res_pe["resume_ref"])
        self.assertTrue(res_pe["post_edit_preserved"])
        self.assertEqual(user_bytes, (root3 / target_rel).read_bytes())

    # ------------------------------------------------------------------
    # Scenario 5: BUDGET_REOPEN
    # ------------------------------------------------------------------
    def test_06_budget_reopen_survives_deleted_markers_new_run_and_knowledge_rebuild(self) -> None:
        root = self._clone(self._b_ready_base)
        _put(root, "Game.Core/Reward/Service.cs", "public class Service { public int V => 1; }\n")
        # Record a stopped run with rerun_guard & sc_test_retry_stop_loss.
        stopped_dir = _create_pipeline_run(
            root,
            101,
            "run-101-stopped",
            date_str="2026-11-23",
            status="fail",
            reason="rerun_blocked:repeat_deterministic_failure",
            failed_step="sc-test",
            diagnostics={
                "rerun_guard": {"kind": "repeat_deterministic_failure", "blocked": True},
                "sc_test_retry_stop_loss": {"triggered": True},
            },
            max_step_retries=1,
            step_attempts=2,
        )
        res_base = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="resume", recommendation_only=True, enforce_durable_stop_loss=False
        )
        ch6_rec.write_recovery_input_set(root, stopped_dir, res_base)

        # Attempt to whitewash: delete active-task, delete latest.json, rebuild Knowledge, open a fresh run_id!
        (root / "logs/ci/active-tasks/task-101.active.json").unlink()
        (root / "logs/ci/2026-11-23/sc-review-pipeline-task-101/latest.json").unlink()
        _put_json(root, "logs/ci/project-health-knowledge/latest.json", {"rebuilt": True})
        _put(root, "docs/knowledge/index.md", "# Rebuilt Knowledge\n")

        # Durable scan MUST still detect active stop-loss across all date dirs!
        signals = ch6_rec.scan_durable_recovery_signals(root, 101)
        self.assertTrue(signals["has_active_stop_loss"])
        self.assertEqual("rerun_guard", signals["blocked_by"])
        self.assertFalse(signals["source_changed_since_last_stop"])

        # Execution-mode recovery (even with new run_id / fresh operation) MUST block until product source is fixed!
        res_exec = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="fresh", recommendation_only=False, consumer="run_review_pipeline"
        )
        self.assertFalse(res_exec["ok"])
        self.assertTrue(res_exec["stop_loss_active"])
        self.assertEqual("rerun_guard", res_exec["stop_loss_blocked_by"])

        # resume_task STILL finds the durable run and preserves blocked_by after latest.json/active-task deletion!
        _, resume_payload = resume_task.build_resume_payload(
            repo_root=root, task_id="101", latest="", run_id="", recommendation_only=True
        )
        self.assertEqual("rerun_guard", resume_payload["chapter6_hints"]["blocked_by"])

        # Now actually fix the product source file: stop-loss clears cleanly!
        _put(root, "Game.Core/Reward/Service.cs", "public class Service { public int V => 2; }\n")
        res_fixed = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="fresh", recommendation_only=False, consumer="run_review_pipeline"
        )
        self.assertTrue(res_fixed["ok"], res_fixed)

        # Story 2.9 epoch bump & reopen revocation MUST block even after marker deletion and new run_id!
        _put_json(
            root,
            "logs/ci/mvg-recovery/registry.json",
            {
                "schema_version": "newrouge.mvg-completed-registry.v1",
                "epoch": 2,
                "entries": [],
                "revoked": [],
            },
        )
        res_epoch = ch6_rec.evaluate_chapter6_recovery(
            root, 101, run_dir=stopped_dir, operation="resume", recommendation_only=True
        )
        self.assertFalse(res_epoch["ok"])
        self.assertEqual("input_stale", res_epoch["reason_code"])
        self.assertEqual("3B", res_epoch["return_stage"])

        # Durable reopen record blocks even WITHOUT passing stopped_dir (new lineage)!
        _put_json(
            root,
            "logs/ci/b-route-reopen/reopen-task-101.json",
            {
                "status": "reopened",
                "reopened": True,
                "task_id": 101,
                "epoch": 2,
            },
        )
        res_reopen = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="fresh", recommendation_only=False
        )
        self.assertFalse(res_reopen["ok"])
        self.assertEqual("conflict", res_reopen["reason_code"])
        self.assertEqual("3B", res_reopen["return_stage"])

    # ------------------------------------------------------------------
    # Task Resolver 97k-file fix & mid-read drift check
    # ------------------------------------------------------------------
    def test_07_task_resolver_skips_nested_mvg_files_and_catches_journal_drift(self) -> None:
        root = self._clone(self._explicit_a_base)
        # Create deeply nested Plane-B candidate/chunk files under logs/ci/mvg-planning/run-deep/
        deep_dir = root / "logs/ci/mvg-planning/run-deep/chunks/sub/nested"
        deep_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(25):
            (deep_dir / f"chunk-{idx}.json").write_text('{"chunk": true}\n', encoding="utf-8")

        res_clean = task_resolver.resolve_task_origin(root, 11)
        self.assertTrue(res_clean["ok"], res_clean)
        self.assertTrue(res_clean["stable"])
        self.assertEqual("explicit_not_enabled_a", res_clean["route"])

        # Mutate ONLY a deeply nested chunk file during before_reread: must NOT fail (skipped!).
        def _mutate_deep() -> None:
            (deep_dir / "chunk-0.json").write_text('{"chunk": false}\n', encoding="utf-8")

        res_deep_ok = task_resolver.resolve_task_origin(root, 11, before_reread=_mutate_deep)
        self.assertTrue(res_deep_ok["ok"], res_deep_ok)
        self.assertTrue(res_deep_ok["stable"])

        # Add a top-level apply-journal.json during before_reread: MUST trigger FILE_CHANGED (stable=False)!
        def _inject_journal() -> None:
            _put_json(
                root,
                "logs/ci/mvg-planning/run-deep/apply-journal.json",
                {"schema_version": "newrouge.planning-apply-journal.v1", "state": "applying"},
            )

        res_drift = task_resolver.resolve_task_origin(root, 11, before_reread=_inject_journal)
        self.assertFalse(res_drift["ok"])
        self.assertFalse(res_drift["stable"])
        self.assertEqual("blocked", res_drift["route"])
        self.assertTrue(
            any(d.get("reason_code") == codec.ReasonCode.FILE_CHANGED.value for d in res_drift["diagnostics"]),
            res_drift["diagnostics"],
        )

    # ------------------------------------------------------------------
    # Step 4 P-01..P-05 regression coverage
    # ------------------------------------------------------------------
    def test_08_pipeline_and_needs_fix_cli_union_lease_pre_sidecar_and_fork_baseline(self) -> None:
        import llm_review_needs_fix_fast
        import run_review_pipeline

        root = self._clone(self._b_ready_base)
        _put(root, "Game.Core/Reward/Service.cs", "public class Service { public int V => 1; }\n")
        stopped_dir = _create_pipeline_run(
            root,
            101,
            "run-101-cli-stop",
            date_str="2026-11-23",
            status="fail",
            reason="step_failed:sc-test",
            failed_step="sc-test",
            diagnostics={"sc_test_retry_stop_loss": {"triggered": True}},
            max_step_retries=1,
            step_attempts=2,
        )
        res_base = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="resume", recommendation_only=True, enforce_durable_stop_loss=False
        )
        ch6_rec.write_recovery_input_set(root, stopped_dir, res_base)

        # Delete latest.json & active-task to test anti-whitewash on fresh run_review_pipeline & needs-fix-fast --final-pass.
        (root / "logs/ci/2026-11-23/sc-review-pipeline-task-101/latest.json").unlink()
        (root / "logs/ci/active-tasks/task-101.active.json").unlink()
        before_fresh = _snapshot_tree(root)

        # 8a. Fresh run_review_pipeline MUST block (rc=12) BEFORE allocating out_dir or writing ANY sidecar!
        stdout_fresh = io.StringIO()
        with (
            patch.object(run_review_pipeline, "repo_root", return_value=root),
            patch.object(sys, "argv", ["run_review_pipeline.py", "--task-id", "101", "--run-id", "fresh-blocked-run"]),
            redirect_stdout(stdout_fresh),
        ):
            rc_fresh = run_review_pipeline.main()
        self.assertEqual(12, rc_fresh, stdout_fresh.getvalue())
        self.assertIn("BLOCKED by b-route-chapter6-recovery", stdout_fresh.getvalue())
        self.assertEqual(before_fresh, _snapshot_tree(root))

        # 8b. llm_review_needs_fix_fast --final-pass MUST block (rc=2) on durable sc_test_retry_stop_loss with ZERO out_dir created!
        stdout_nff = io.StringIO()
        with (
            patch.object(llm_review_needs_fix_fast, "repo_root", return_value=root),
            patch.object(llm_review_needs_fix_fast, "ci_dir", side_effect=AssertionError("ci_dir must not be called when blocked")),
            patch.object(sys, "argv", ["llm_review_needs_fix_fast.py", "--task-id", "101", "--final-pass"]),
            redirect_stdout(stdout_nff),
        ):
            rc_nff = llm_review_needs_fix_fast.main()
        self.assertEqual(2, rc_nff, stdout_nff.getvalue())
        self.assertIn("BLOCKED by b-route-chapter6-recovery", stdout_nff.getvalue())
        self.assertEqual(before_fresh, _snapshot_tree(root))

        # 8c. run_review_pipeline --fork with drifted source_out_dir frozen baseline MUST block (rc=12) before allocating out_dir!
        root_fork = self._clone(self._b_ready_base)
        src_dir = _create_pipeline_run(root_fork, 101, "run-101-src", date_str="2026-11-24", status="ok")
        res_src = ch6_rec.evaluate_chapter6_recovery(root_fork, 101, operation="resume", recommendation_only=True)
        fp_src = ch6_rec.write_recovery_input_set(root_fork, src_dir, res_src)
        fdoc = json.loads(fp_src.read_text(encoding="utf-8"))
        fdoc["applicable_set_digest"] = "sha256:" + ("a" * 64)
        fp_src.write_text(json.dumps(fdoc, indent=2) + "\n", encoding="utf-8")
        before_fork = _snapshot_tree(root_fork)

        stdout_fork = io.StringIO()
        with (
            patch.object(run_review_pipeline, "repo_root", return_value=root_fork),
            patch.object(run_review_pipeline, "_load_source_run", return_value=(src_dir, json.loads((src_dir / "summary.json").read_text(encoding="utf-8")), {})),
            patch.object(sys, "argv", ["run_review_pipeline.py", "--task-id", "101", "--fork", "--run-id", "forked-blocked"]),
            redirect_stdout(stdout_fork),
        ):
            rc_fork = run_review_pipeline.main()
        self.assertEqual(12, rc_fork, stdout_fork.getvalue())
        self.assertIn("BLOCKED by b-route-chapter6-recovery", stdout_fork.getvalue())
        self.assertEqual(before_fork, _snapshot_tree(root_fork))

        # 8d. run_review_pipeline --resume enters guarded_chapter6_recovery, writes recovery-input-set.json
        # with input_set_snapshot, and aborts mid-run (rc=12, return_stage=4) on contract drift before execute_steps!
        root_res = self._clone(self._b_ready_base)
        res_dir = _create_pipeline_run(root_res, 101, "run-101-res", date_str="2026-11-24", status="fail", failed_step="sc-llm-review")
        res_summary = json.loads((res_dir / "summary.json").read_text(encoding="utf-8"))
        res_marathon = {
            "task_id": "101",
            "run_id": "run-101-res",
            "requested_run_id": "run-101-res",
            "status": "fail",
            "resume_count": 1,
            "max_step_retries": 2,
            "steps": {},
            "diagnostics": {},
        }
        (res_dir / "marathon-state.json").write_text(json.dumps(res_marathon, indent=2) + "\n", encoding="utf-8")
        contract_file = root_res / "Game.Core/Contracts/Reward/SelectRewardCommand.cs"

        def _drift_contract_during_preflight(**_kwargs: object) -> None:
            # Verify recovery-input-set.json WITH input_set_snapshot was written inside the union lease!
            frozen_doc = json.loads((res_dir / ch6_rec.RECOVERY_INPUT_SET_FILENAME).read_text(encoding="utf-8"))
            self.assertIsInstance(frozen_doc.get("input_set_snapshot"), dict)
            self.assertTrue(os.environ.get(ch6_gate.ENV_LEASE_PATH))
            contract_file.write_text(contract_file.read_text(encoding="utf-8") + "// mid-run drift\n", encoding="utf-8")
            return None

        import _active_task_sidecar
        import _marathon_state
        import _pipeline_helpers

        stdout_res = io.StringIO()
        with (
            patch.object(run_review_pipeline, "repo_root", return_value=root_res),
            patch.object(_pipeline_helpers, "repo_root", return_value=root_res),
            patch.object(_marathon_state, "repo_root", return_value=root_res),
            patch.object(_active_task_sidecar, "repo_root", return_value=root_res),
            patch.object(run_review_pipeline, "_load_source_run", return_value=(res_dir, res_summary, res_marathon)),
            patch.object(run_review_pipeline, "_run_acceptance_preflight", side_effect=_drift_contract_during_preflight),
            patch.object(run_review_pipeline.PipelineSession, "execute_steps", side_effect=AssertionError("execute_steps must not run after drift")),
            patch.object(sys, "argv", ["run_review_pipeline.py", "--task-id", "101", "--resume", "--allow-full-rerun"]),
            redirect_stdout(stdout_res),
        ):
            rc_res = run_review_pipeline.main()
        self.assertEqual(12, rc_res, stdout_res.getvalue())
        self.assertIn("return_stage=4", stdout_res.getvalue())

    def test_09_durable_signal_reset_on_passing_ok_and_product_tree_fingerprint_scope(self) -> None:
        root = self._clone(self._b_ready_base)
        _put(root, "Game.Core/Reward/Service.cs", "public class Service { public int V => 1; }\n")
        _put(root, "Scenes/Reward.tscn", "[gd_scene format=3]\n")

        # Two consecutive deterministic failures + rerun_guard, followed by a clean passing ok run.
        _create_pipeline_run(
            root,
            101,
            "run-fail-1",
            date_str="2026-11-22",
            status="fail",
            reason="step_failed:sc-test",
            failed_step="sc-test",
            max_step_retries=1,
            step_attempts=2,
        )
        stopped_dir = _create_pipeline_run(
            root,
            101,
            "run-fail-2",
            date_str="2026-11-23",
            status="fail",
            reason="rerun_blocked:repeat_deterministic_failure",
            failed_step="sc-test",
            diagnostics={"rerun_guard": {"kind": "repeat_deterministic_failure", "blocked": True}},
            max_step_retries=1,
            step_attempts=2,
        )
        res_base = ch6_rec.evaluate_chapter6_recovery(
            root, 101, operation="resume", recommendation_only=True, enforce_durable_stop_loss=False
        )
        ch6_rec.write_recovery_input_set(root, stopped_dir, res_base)

        sig_before = ch6_rec.scan_durable_recovery_signals(root, 101)
        self.assertTrue(sig_before["has_active_stop_loss"])
        self.assertEqual(2, sig_before["failed_runs"])
        self.assertEqual(2, sig_before["consecutive_failures"])

        # Editing harness scripts/python/ or scripts/sc/ MUST NOT clear source_changed_since_last_stop!
        _put(root, "scripts/python/harness_only_change.py", "# harness edit\n")
        _put(root, "scripts/sc/harness_only_sc.py", "# sc edit\n")
        sig_harness = ch6_rec.scan_durable_recovery_signals(root, 101)
        self.assertFalse(sig_harness["source_changed_since_last_stop"])
        self.assertTrue(sig_harness["has_active_stop_loss"])

        # Editing a Godot scene (.tscn) DOES count as a product source change!
        _put(root, "Scenes/Reward.tscn", "[gd_scene format=3]\n[node name=\"Reward\" type=\"Control\"]\n")
        sig_scene = ch6_rec.scan_durable_recovery_signals(root, 101)
        self.assertTrue(sig_scene["source_changed_since_last_stop"])
        self.assertFalse(sig_scene["has_active_stop_loss"])

        # Restore scene to original so stop-loss would still be active without a passing ok run, then add passing ok run!
        _put(root, "Scenes/Reward.tscn", "[gd_scene format=3]\n")
        self.assertTrue(ch6_rec.scan_durable_recovery_signals(root, 101)["has_active_stop_loss"])

        _create_pipeline_run(
            root,
            101,
            "run-ok-3",
            date_str="2026-11-24",
            status="ok",
            reason="pipeline_clean",
            max_step_retries=1,
            step_attempts=1,
        )
        sig_after_ok = ch6_rec.scan_durable_recovery_signals(root, 101)
        self.assertFalse(sig_after_ok["has_active_stop_loss"])
        self.assertEqual(0, sig_after_ok["consecutive_failures"])
        self.assertEqual([], sig_after_ok["active_stop_loss_signals"])
        # Historical cumulative counts remain intact!
        self.assertEqual(2, sig_after_ok["failed_runs"])
        self.assertGreaterEqual(sig_after_ok["total_step_retries"], 5)
        self.assertGreaterEqual(sig_after_ok["total_resume_count"], 3)

    def test_10_corrupt_baseline_strict_compare_reopen_without_rundir_and_journal_checks(self) -> None:
        # 10a. Corrupt recovery-input-set.json fails closed with CONFLICT (never falls back to None).
        root = self._clone(self._b_ready_base)
        run_dir = _create_pipeline_run(root, 101, "run-corrupt", status="ok")
        (run_dir / ch6_rec.RECOVERY_INPUT_SET_FILENAME).write_text("{corrupt json", encoding="utf-8")
        res_corrupt = ch6_rec.evaluate_chapter6_recovery(root, 101, run_dir=run_dir, operation="resume", recommendation_only=True)
        self.assertFalse(res_corrupt["ok"])
        self.assertEqual("conflict", res_corrupt["reason_code"])
        self.assertEqual("5", res_corrupt["return_stage"])
        self.assertTrue(str(res_corrupt["resume_ref"]).endswith(ch6_rec.RECOVERY_INPUT_SET_FILENAME))

        # 10b. Strict _compare_run_baseline_to_live catches A-to-B (None vs digest) and empty-to-nonempty sets!
        live_gate = ch6_gate.evaluate_chapter6_gate(root, 101, operation="resume", consumer="test", lock_mode="none")
        self.assertTrue(live_gate["ok"])
        cmp_a_to_b = ch6_rec._compare_run_baseline_to_live(
            tid=101,
            run_baseline={"input_set_digest": None, "applicable_set_digest": None, "scope_ids": [], "binding_revisions": {}},
            gate_res=live_gate,
            live_iset=None,
        )
        self.assertFalse(cmp_a_to_b["ok"])
        self.assertEqual("input_stale", cmp_a_to_b["reason_code"])
        self.assertEqual("3C", cmp_a_to_b["return_stage"])

        # 10c. Story 2.9 epoch bump blocks EVEN with run_dir=None (via durable prior baseline epoch)!
        root_ep = self._clone(self._b_ready_base)
        ep_dir = _create_pipeline_run(root_ep, 101, "run-ep-0", date_str="2026-11-23", status="ok")
        res_ep0 = ch6_rec.evaluate_chapter6_recovery(root_ep, 101, operation="resume", recommendation_only=True)
        ch6_rec.write_recovery_input_set(root_ep, ep_dir, res_ep0)
        _put_json(
            root_ep,
            "logs/ci/mvg-recovery/registry.json",
            {"schema_version": "newrouge.mvg-completed-registry.v1", "epoch": 3, "entries": [], "revoked": []},
        )
        res_ep_none = ch6_rec.evaluate_chapter6_recovery(root_ep, 101, run_dir=None, operation="fresh", recommendation_only=True)
        self.assertFalse(res_ep_none["ok"])
        self.assertEqual("input_stale", res_ep_none["reason_code"])
        self.assertEqual("3B", res_ep_none["return_stage"])

        # 10d. Story 2.9 adoption_proof_refs pointing to reopened run.json blocks with return_stage=3B even with run_dir=None!
        root_proof = self._clone(self._b_ready_base)
        live_g = ch6_gate.evaluate_chapter6_gate(root_proof, 101, operation="resume", consumer="test", lock_mode="none")
        # Inject a reopened run.json under an adoption_proof_ref referenced by the stage5 binding or plan.
        proof_rel = "logs/ci/mvg-planning/run-reopened-proof/run.json"
        _put_json(root_proof, proof_rel, {"run_id": "run-reopened-proof", "reopened": True, "status": "reopened"})
        self.assertTrue(live_g["binding_refs"])
        binding_path = root_proof / live_g["binding_refs"][0]["path"]
        bdoc = json.loads(binding_path.read_text(encoding="utf-8"))
        bdoc["adoption_proof_refs"] = [proof_rel]
        binding_path.write_text(json.dumps(bdoc, indent=2) + "\n", encoding="utf-8")
        # Re-check via _check_epoch_and_reopen_revocations directly (since mutating binding also changes digest).
        reopen_proof = ch6_rec._check_epoch_and_reopen_revocations(root_proof, 101, gate_res=live_g, run_baseline=None)
        self.assertFalse(reopen_proof["ok"])
        self.assertEqual("conflict", reopen_proof["reason_code"])
        self.assertEqual("3B", reopen_proof["return_stage"])
        self.assertEqual(proof_rel, reopen_proof["resume_ref"])

        # 10e. Multiple legacy_recovery_routes: 2nd route with deleted target file (before_sha256 non-None) blocks CONFLICT!
        import base64

        root_j = self._clone(self._b_ready_base)
        j1_rel = "logs/ci/capability-planning/run-j1/apply-journal.json"
        j2_rel = "logs/ci/mvg-planning/run-j2/apply-journal.json"
        cap_target = "docs/planning/semantic-topology/capabilities.v1.json"
        cap_payload = {"schema_version": "newrouge.capabilities.v1", "capabilities": []}
        cap_bytes = (json.dumps(cap_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _put(root_j, cap_target, cap_bytes)
        _put_json(
            root_j,
            "logs/ci/capability-planning/run-j1/run.json",
            {"schema_version": "newrouge.capability-planning-run.v1", "run_id": "run-j1", "phase": "applying"},
        )
        _put_json(
            root_j,
            j1_rel,
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "status": "pending",
                "authority_inputs": {},
                "entries": [
                    {
                        "path": cap_target,
                        "before_sha256": None,
                        "before_base64": None,
                        "after_sha256": codec.raw_digest(cap_bytes),
                        "payload": cap_payload,
                    }
                ],
                "result": {},
            },
        )
        mvg_before = b'{"schema_version": "old"}\n'
        mvg_payload = {"schema_version": "new"}
        mvg_after = codec.raw_digest((json.dumps(mvg_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        _put_json(
            root_j,
            "logs/ci/mvg-planning/run-j2/run.json",
            {"schema_version": "newrouge.mvg-planning-run.v1", "run_id": "run-j2", "phase": "applying"},
        )
        _put_json(
            root_j,
            j2_rel,
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "status": "pending",
                "authority_inputs": {},
                "entries": [
                    {
                        "path": "docs/testing/mvg/deleted-by-user.json",
                        "before_sha256": codec.raw_digest(mvg_before),
                        "before_base64": base64.b64encode(mvg_before).decode("ascii"),
                        "after_sha256": mvg_after,
                        "payload": mvg_payload,
                    }
                ],
                "result": {},
            },
        )
        res_multi_j = ch6_rec.evaluate_chapter6_recovery(root_j, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res_multi_j["ok"])
        self.assertEqual("conflict", res_multi_j["reason_code"])
        self.assertEqual(j2_rel, res_multi_j["resume_ref"])
        self.assertTrue(res_multi_j["post_edit_preserved"])

        # 10f. Cancelled task in tasks.json is rejected fail-closed.
        root_can = self._clone(self._b_ready_base)
        mp = root_can / ".taskmaster/tasks/tasks.json"
        mdoc = json.loads(mp.read_text(encoding="utf-8"))
        for row in mdoc["master"]["tasks"]:
            if row["id"] == 101:
                row["status"] = "cancelled"
        mp.write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        res_can = ch6_rec.evaluate_chapter6_recovery(root_can, 101, operation="resume", recommendation_only=True)
        self.assertFalse(res_can["ok"])
        self.assertEqual("conflict", res_can["reason_code"])
        self.assertEqual("3C", res_can["return_stage"])
        self.assertIn("task_status_ineligible:cancelled", res_can["reason"])

    def test_11_chapter6_route_latest_without_task_id_stop_loss_routing_and_compact_block_fields(self) -> None:
        # 11a. chapter6_route --latest <path> WITHOUT --task-id enforces live B-route revalidation!
        root = self._clone(self._b_ready_base)
        _create_pipeline_run(root, 101, "run-101-latest-only", status="ok")
        latest_rel = "logs/ci/2026-11-24/sc-review-pipeline-task-101/latest.json"
        # Drift live contract while latest.json still says ok.
        contract = root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs"
        contract.write_text(contract.read_text(encoding="utf-8") + "// latest-only drift\n", encoding="utf-8")

        stdout_r = io.StringIO()
        with redirect_stdout(stdout_r):
            rc_r = chapter6_route.main(
                [
                    "--repo-root",
                    str(root),
                    "--latest",
                    latest_rel,
                    "--recommendation-only",
                    "--recommendation-format",
                    "json",
                ]
            )
        self.assertEqual(3, rc_r)
        compact_r = json.loads(stdout_r.getvalue())
        self.assertEqual("blocked-by-b-route-gate", compact_r["preferred_lane"])
        self.assertEqual("4", compact_r["return_stage"])
        self.assertIn("reason_code", compact_r)
        self.assertIn("resume_ref", compact_r)

        # resume_task --recommendation-only on blocked B-route returns rc=2 and includes reason_code/return_stage/resume_ref!
        stdout_rt = io.StringIO()
        with redirect_stdout(stdout_rt):
            rc_rt = resume_task.main(
                [
                    "--repo-root",
                    str(root),
                    "--task-id",
                    "101",
                    "--recommendation-only",
                    "--recommendation-format",
                    "json",
                ]
            )
        self.assertEqual(2, rc_rt)
        compact_rt = json.loads(stdout_rt.getvalue())
        self.assertEqual("blocked-by-b-route-gate", compact_rt["recommended_action"])
        self.assertEqual("4", compact_rt["return_stage"])
        self.assertIn("reason_code", compact_rt)
        self.assertIn("resume_ref", compact_rt)

        # 11b. Non-recommendation-only resume_task & chapter6_route preserve stop-loss routing (NOT Stage-5 gate block)!
        root_sl = self._clone(self._b_ready_base)
        _put(root_sl, "Game.Core/Reward/Service.cs", "public class Service { public int V => 1; }\n")
        _create_pipeline_run(
            root_sl,
            101,
            "run-101-sl-det",
            status="fail",
            reason="step_failed:sc-test",
            failed_step="sc-test",
            diagnostics={"sc_test_retry_stop_loss": {"blocked": True, "step_name": "sc-test"}},
        )
        rc_sl_det, route_sl_det = chapter6_route.route_chapter6(
            repo_root=root_sl, task_id="101", recommendation_only=False
        )
        self.assertEqual(0, rc_sl_det, route_sl_det)
        self.assertEqual("fix-deterministic", route_sl_det["preferred_lane"])
        self.assertEqual("sc_test_retry_stop_loss", route_sl_det["blocked_by"])
        self.assertTrue(route_sl_det["b_route_recovery"]["ok"])
        self.assertTrue(route_sl_det["b_route_recovery"]["stop_loss_active"])

        # llm_retry_stop_loss with reviewer anchor hit routes to run-6.8 (NOT blocked-by-b-route-gate)!
        root_llm = self._clone(self._b_ready_base)
        _put(root_llm, "Game.Core/Reward/Service.cs", "public class Service { public int V => 1; }\n")
        _create_pipeline_run(
            root_llm,
            101,
            "run-101-sl-llm",
            status="fail",
            reason="review_needs_fix",
            failed_step="",
            diagnostics={"llm_retry_stop_loss": {"blocked": True, "step_name": "sc-llm-review", "deterministic_ok": True}},
        )
        with patch.object(
            chapter6_route,
            "_derive_change_scope",
            return_value={"changed_paths": ["docs/architecture/overlays/PRD-1/08/overview.md"]},
        ):
            rc_sl_llm, route_sl_llm = chapter6_route.route_chapter6(
                repo_root=root_llm, task_id="101", recommendation_only=False
            )
        self.assertEqual(0, rc_sl_llm, route_sl_llm)
        self.assertEqual("run-6.8", route_sl_llm["preferred_lane"])
        self.assertFalse(route_sl_llm["full_67_recommended"])

    def test_12_inspect_run_recommendation_only_zero_write_and_blocked_b_route_and_non_ascii_tid(self) -> None:
        root = self._clone(self._b_ready_base)
        _create_pipeline_run(root, 101, "run-101-insp", status="ok")
        before = _snapshot_tree(root)

        # 12a. inspect_run.main with --recommendation-only --out-json creates ZERO files on disk!
        stdout_ok = io.StringIO()
        with redirect_stdout(stdout_ok):
            rc_ok = inspect_run.main(
                [
                    "--repo-root",
                    str(root),
                    "--kind",
                    "pipeline",
                    "--task-id",
                    "101",
                    "--recommendation-only",
                    "--recommendation-format",
                    "json",
                    "--out-json",
                    "logs/ci/inspect-must-not-exist.json",
                ]
            )
        self.assertEqual(0, rc_ok)
        self.assertFalse((root / "logs/ci/inspect-must-not-exist.json").exists())
        self.assertEqual(before, _snapshot_tree(root))

        # 12b. Deleting the MVG manifest on a cached ok B-route run makes inspect_run return rc=1 & blocked-by-b-route-gate!
        manifests = list((root / "docs/testing/mvg").glob("*.json"))
        self.assertTrue(manifests)
        for m in manifests:
            m.unlink()
        rc_blk, insp_blk = inspect_run.inspect_run_artifacts(repo_root=root, kind="pipeline", task_id="101")
        self.assertEqual(1, rc_blk)
        self.assertEqual("fail", insp_blk["status"])
        self.assertEqual("b-route-gate-blocked", insp_blk["failure"]["code"])
        self.assertEqual("blocked-by-b-route-gate", insp_blk["recommended_action"])
        self.assertEqual("5", insp_blk["return_stage"])
        self.assertFalse(insp_blk["runtime_verified"])
        self.assertFalse(insp_blk["default_b_enabled"])

        # 12c. Non-ASCII task_id in a B-route repo fails closed in inspect_run (never skipped!).
        root_bad = self._clone(self._b_ready_base)
        out_bad = root_bad / "logs/ci/2026-11-24/sc-review-pipeline-task-bad-r1"
        out_bad.mkdir(parents=True, exist_ok=True)
        latest_bad = root_bad / "logs/ci/2026-11-24/sc-review-pipeline-task-bad/latest.json"
        _put_json(
            root_bad,
            latest_bad.relative_to(root_bad).as_posix(),
            {
                "task_id": "\u00b9",
                "run_id": "r1",
                "status": "ok",
                "latest_out_dir": str(out_bad),
            },
        )
        rc_na, insp_na = inspect_run.inspect_run_artifacts(
            repo_root=root_bad,
            latest=latest_bad.relative_to(root_bad).as_posix(),
            kind="pipeline",
        )
        self.assertEqual(1, rc_na)
        self.assertEqual("blocked-by-b-route-gate", insp_na["recommended_action"])
        self.assertEqual("invalid_argument", insp_na["reason_code"])
        self.assertFalse(insp_na["runtime_verified"])
        self.assertFalse(insp_na["default_b_enabled"])


if __name__ == "__main__":
    unittest.main()
