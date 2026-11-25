"""Deterministic tests for Story 3.12 page shared gate, five-entrypoint parity, Windows concurrency, and Epic 3->4 handoff.

Covers all 5 Story 3.12 ACs (PAGE_SHARED_GATE, PARITY_APPLICABLE, TAMPER_BEFORE_FX,
WIN_CONCURRENCY, EPIC3_HANDOFF), live loopback POST /api/knowledge/b-route +
/api/knowledge/runtime + /api/knowledge/mvg-run pre-effect gates, direct underlying
modules without special-case branches, real _b_route_commit.recover terminal replay
no-op, cross-process Windows msvcrt union-scope contention, and CLI/builder exclusive
report contracts using setUpClass cached fixtures for fast execution.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import concurrent.futures
from contextlib import redirect_stdout
import copy
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
REPO_ROOT = SCRIPTS_PY.parents[1]
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(SCRIPTS_PY / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_rec
import _b_route_codec as codec
import _b_route_entrypoint_parity as parity
import _b_route_input_set as input_set
import _b_route_operation_scope as op_scope
import _b_route_records as records
import _b_route_stage5_obligations as s5
import _planning_apply_journal as journal
import _project_health_http as ph_http
import check_b_route_entrypoint_parity as parity_cli
import dev_cli
import dev_cli_builders
import project_health_runtime as ph_runtime

from test_b_route_chapter5_readiness import (
    _build_b_route_base_repo,
    _put,
    _put_json,
    _stage5_resp,
    _typed_ref,
)
from test_b_route_chapter6_gate import (
    _build_explicit_not_enabled_a_repo,
    _build_frozen_a_repo,
    _decisions_for_task,
    _reconcile_task_ready,
)
from test_b_route_chapter7_slice import _reseal_plan_and_catalog
from test_b_route_stage5_obligations import Stage5RepoFixture, _run_full_lifecycle


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | bytes | str | None = None,
) -> tuple[int, dict]:
    if body is None:
        data = None
    elif isinstance(body, bytes):
        data = body
    elif isinstance(body, str):
        data = body.encode("utf-8")
    else:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def _snapshot_all_entries(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            out[rel + "/"] = "dir"
        elif p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _add_second_plan_sharing_task101(root: Path) -> None:
    """Commit a second schema-valid plan into catalog + task-origins sharing Task 101 so applicable_set_digest changes."""
    other_plan_rel = "docs/planning/b-route/plans/plan-other/1.json"
    other_bind_rel = "docs/planning/b-route/bindings/plan-other/1.json"
    plan2_rel = "docs/planning/b-route/plans/plan-shared-extra/1.json"
    bind2_rel = "docs/planning/b-route/bindings/plan-shared-extra/1.json"

    other_plan = json.loads((root / other_plan_rel).read_text(encoding="utf-8"))
    other_bind = json.loads((root / other_bind_rel).read_text(encoding="utf-8"))

    plan2 = json.loads(json.dumps(other_plan))
    plan2["plan_id"] = "plan-shared-extra"
    plan2["lineage"]["change_summary"] = "Second committed plan sharing Task 101."
    for req in plan2.get("requirements") or []:
        req["requirement_id"] = "REQ-SHARED-EXTRA-1"
    for row in plan2.get("requirement_verification") or []:
        row["requirement_id"] = "REQ-SHARED-EXTRA-1"
    for row in plan2.get("coverage_table") or []:
        row["requirement_id"] = "REQ-SHARED-EXTRA-1"
    for row in plan2.get("applicability") or []:
        row["requirement_id"] = "REQ-SHARED-EXTRA-1"
    plan2_raw = _put_json(root, plan2_rel, plan2)
    plan2_ref = _typed_ref(plan2_rel, "newrouge.b-route-plan.v1", "plan-shared-extra", 1, plan2_raw)

    bind2 = json.loads(json.dumps(other_bind))
    bind2["plan_id"] = "plan-shared-extra"
    bind2["plan_ref"] = plan2_ref
    bind2["stage"] = "5"
    bind2["task_mappings"] = [
        {
            "task_id": 101,
            "view_refs": [{"view": "back", "business_id": "NG-0101"}],
            "requirement_ids": ["REQ-SHARED-EXTRA-1"],
            "flow_ids": [],
            "part_kinds": ["domain_rules"],
            "roles": ["producer"],
            "obligation_ids": ["OBL-SHARED-EXTRA-1"],
        }
    ]
    for obl in bind2.get("obligations") or []:
        obl["id"] = "OBL-SHARED-EXTRA-1"
        obl["requirement_ids"] = ["REQ-SHARED-EXTRA-1"]
        obl["responsibility"] = _stage5_resp(
            "Shared extra non-flow verification.",
            {
                "stage": "5",
                "category": "current_new",
                "task_ids": [101],
                "newly_assigned_task_ids": [],
                "manifest_flow_ids": [],
                "non_catalog_flow_ids": [],
                "out_of_scope_future_flow_ids": [],
                "planned_test_ids": [],
                "has_new_obligation": False,
                "requires_reverification_on_done": False,
                "dedup_key": "plan-shared-extra:OBL-SHARED-EXTRA-1",
            },
            {"stage": "4", "task_ids": [101], "test_ids": []},
        )
    bind2_raw = _put_json(root, bind2_rel, bind2)
    bind2_ref = _typed_ref(bind2_rel, "newrouge.b-route-binding.v1", "plan-shared-extra", 1, bind2_raw)

    origins_rel = "docs/planning/b-route/task-origins.v1.json"
    origins = json.loads((root / origins_rel).read_text(encoding="utf-8"))
    for row in origins.get("tasks") or []:
        if int(row.get("task_id", -1)) == 101:
            row["plan_refs"] = list(row.get("plan_refs") or []) + [plan2_ref]
            row["binding_refs"] = list(row.get("binding_refs") or []) + [bind2_ref]
    origins_raw = _put_json(root, origins_rel, origins)
    origins_dg = codec.raw_digest(origins_raw)

    commit1_rel = "docs/planning/b-route/commits/OP-INIT-001.json"
    commit1_doc = json.loads((root / commit1_rel).read_text(encoding="utf-8"))
    for tgt in commit1_doc.get("targets") or []:
        if tgt.get("path") == origins_rel:
            tgt["after_digest"] = origins_dg
            tgt["projection_digest"] = origins_dg
    commit1_raw = _put_json(root, commit1_rel, commit1_doc)
    commit1_ref = _typed_ref(commit1_rel, "newrouge.b-route-commit.v1", "OP-INIT-001", 1, commit1_raw)

    catalog_rel = "docs/planning/b-route/catalog.v1.json"
    catalog = json.loads((root / catalog_rel).read_text(encoding="utf-8"))
    old_oref = catalog["origins_ref"]
    catalog["origins_ref"] = _typed_ref(
        origins_rel,
        old_oref["schema_version"],
        old_oref["entity_id"],
        int(old_oref["revision"]),
        origins_raw,
    )
    for sh in catalog.get("scope_heads") or []:
        if isinstance(sh.get("receipt_ref"), dict) and sh["receipt_ref"].get("path") == commit1_rel:
            sh["receipt_ref"] = commit1_ref
    commit2_rel = "docs/planning/b-route/commits/OP-EXTRA-002.json"
    plan2_dg = codec.raw_digest(plan2_raw)
    bind2_dg = codec.raw_digest(bind2_raw)
    commit2_doc = {
        "schema_version": "newrouge.b-route-commit.v1",
        "operation_id": "OP-EXTRA-002",
        "revision": 1,
        "operation_digest": codec.canonical_digest({"op": "OP-EXTRA-002", "plan_id": "plan-shared-extra"}),
        "scopes": ["scope-shared-extra"],
        "authority": list(commit1_doc.get("authority") or []),
        "targets": [
            {
                "path": plan2_rel,
                "before_digest": None,
                "after_digest": plan2_dg,
                "verification_mode": "immutable_bytes",
                "codec_version": None,
                "projection_digest": plan2_dg,
            },
            {
                "path": bind2_rel,
                "before_digest": None,
                "after_digest": bind2_dg,
                "verification_mode": "immutable_bytes",
                "codec_version": None,
                "projection_digest": bind2_dg,
            },
        ],
        "plan_refs": [plan2_ref],
        "binding_refs": [bind2_ref],
        "resolved_definitions": [],
        "result": {
            "target_paths": [plan2_rel, bind2_rel],
            "scope_ids": ["scope-shared-extra"],
        },
    }
    commit2_raw = _put_json(root, commit2_rel, commit2_doc)
    commit2_ref = _typed_ref(commit2_rel, "newrouge.b-route-commit.v1", "OP-EXTRA-002", 1, commit2_raw)
    catalog.setdefault("scope_heads", []).append(
        {
            "scope_id": "scope-shared-extra",
            "plan_refs": [plan2_ref],
            "binding_refs": [bind2_ref],
            "receipt_ref": commit2_ref,
        }
    )
    for trow in catalog.get("task_index") or []:
        if int(trow.get("task_id", -1)) == 101:
            trow["plan_refs"] = list(trow.get("plan_refs") or []) + [plan2_ref]
            trow["binding_refs"] = list(trow.get("binding_refs") or []) + [bind2_ref]
    _put_json(root, catalog_rel, catalog)


def _seed_fake_knowledge_scan_and_pointers(root: Path, task_id: int = 101) -> dict[str, bytes]:
    """Seed publication pointers + spoofed latest.json claiming task is ready/eligible."""
    pointer_data: dict[str, bytes] = {}
    pointer_data["docs/knowledge/published/current.json"] = _put_json(
        root,
        "docs/knowledge/published/current.json",
        {"publication_id": "pub-current-001", "revision": "a" * 40},
    )
    pointer_data["docs/knowledge/published/last-known-good.json"] = _put_json(
        root,
        "docs/knowledge/published/last-known-good.json",
        {"publication_id": "pub-lkg-001", "revision": "b" * 40},
    )
    pointer_data["logs/ci/project-health-knowledge/latest.json"] = _put_json(
        root,
        "logs/ci/project-health-knowledge/latest.json",
        {
            "revision": "c" * 40,
            "tasks": [
                {
                    "task": {"id": task_id, "status": "done", "ready": True},
                    "godot": {"scenes": [{"scene": "Scenes/Reward.tscn"}]},
                }
            ],
            "sources": {
                ".taskmaster/tasks/tasks_gameplay.json": json.dumps(
                    [
                        {
                            "taskmaster_id": task_id,
                            "title": "Spoofed Ready Task",
                            "test_refs": ["Tests.Godot/tests/Reward/test_stale_deleted.gd"],
                        }
                    ]
                ),
                "Tests.Godot/tests/Reward/test_stale_deleted.gd": "extends GdUnitTestSuite\n",
            },
            "mvg_overview": {
                "revision": "c" * 40,
                "manifests": [{"path": "docs/testing/mvg/reward-baseline.json", "tests": []}],
            },
        },
    )
    pointer_data["logs/ci/project-health-knowledge/runtime/latest.json"] = _put_json(
        root,
        "logs/ci/project-health-knowledge/runtime/latest.json",
        {"schema_version": "newrouge.project-health-runtime-index.v1", "source_revision": "c" * 40, "tasks": []},
    )
    return pointer_data


def _eval_parity_worker(repo_str: str, tid: int) -> dict:
    return parity.evaluate_entrypoint_parity(Path(repo_str), task_id=tid)


def _eval_ac3_case_worker(case: str, repo_str: str, tid: int) -> dict:
    """Evaluate all 5 public entrypoints AND direct underlying scripts WITHOUT any special-case branches."""
    repo = Path(repo_str)
    res = parity.evaluate_entrypoint_parity(repo, task_id=tid)
    direct_checks = dict((res.get("entrypoints") or {}).get("direct", {}).get("direct_consumers") or {})
    rt_gate = parity.enforce_runtime_task_gate(repo, [tid], mode="main")
    return {"case": case, "parity": res, "direct_checks": direct_checks, "rt_gate": rt_gate}


class EntrypointParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = Path(tempfile.mkdtemp(prefix="nr_story312_"))
        cls._flow_base = cls._tmp / "flow_base"
        cls._flow_base.mkdir()
        _build_b_route_base_repo(cls._flow_base, mode="flow", include_planned=False, task101_status="in-progress")
        _reconcile_task_ready(cls._flow_base, 101, mode="flow", include_planned=False)
        _reconcile_task_ready(cls._flow_base, 103, mode="flow", include_planned=False)
        _reconcile_task_ready(cls._flow_base, 201, mode="flow", include_planned=False)

        cls._nonflow_base = cls._tmp / "nonflow_base"
        cls._nonflow_base.mkdir()
        _build_b_route_base_repo(cls._nonflow_base, mode="nonflow", include_planned=False, task101_status="in-progress")
        unused_mvg = cls._nonflow_base / "docs/testing/mvg/reward-baseline.json"
        if unused_mvg.exists():
            unused_mvg.unlink()
        _reconcile_task_ready(cls._nonflow_base, 101, mode="nonflow", include_planned=False)

        cls._explicit_a_base = cls._tmp / "explicit_a_base"
        cls._explicit_a_base.mkdir()
        _build_explicit_not_enabled_a_repo(cls._explicit_a_base)

        cls._frozen_a_base = cls._tmp / "frozen_a_base"
        cls._frozen_a_info = _build_frozen_a_repo(cls._frozen_a_base)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _clone(self, src: Path, label: str) -> Path:
        dst = Path(tempfile.mkdtemp(prefix=f"s312_{label}_", dir=str(self._tmp)))
        shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return dst

    # ------------------------------------------------------------------
    # AC-1: PAGE_SHARED_GATE (Loopback HTTP + Runtime + MVG + Zero-Publish)
    # ------------------------------------------------------------------

    def test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish(self) -> None:
        repo = self._clone(self._flow_base, "ac1_http")
        pointers = _seed_fake_knowledge_scan_and_pointers(repo, task_id=101)

        server = ThreadingHTTPServer(("127.0.0.1", 0), ph_http.handler_factory(repo))
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{port}"
            host_hdr = f"127.0.0.1:{port}"
            status, sess = _http_json(f"{base_url}/api/knowledge/session", headers={"Host": host_hdr})
            self.assertEqual(status, 200)
            token = sess["token"]
            auth_headers = {
                "Host": host_hdr,
                "Origin": base_url,
                "X-Project-Health-Token": token,
                "Content-Type": "application/json",
            }

            # 1. Missing token is rejected with 403.
            code_unauth, _ = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers={"Host": host_hdr, "Origin": base_url, "Content-Type": "application/json"},
                body={"action": "gate", "task_id": 101},
            )
            self.assertEqual(code_unauth, 403)

            # 2. Duplicate JSON keys & non-boolean preview/recommendation_only fail closed with 422!
            code_dup, payload_dup = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers=auth_headers,
                body=b'{"action":"execute","task_id":101,"preview":true,"preview":false}',
            )
            self.assertEqual(code_dup, 422)
            self.assertFalse(payload_dup["ok"])

            for bad_field, bad_val in (("preview", "false"), ("recommendation_only", "false")):
                code_bad_bool, payload_bad_bool = _http_json(
                    f"{base_url}/api/knowledge/b-route",
                    method="POST",
                    headers=auth_headers,
                    body={"action": "execute", "task_id": 101, bad_field: bad_val},
                )
                self.assertEqual(code_bad_bool, 422)
                self.assertFalse(payload_bad_bool["ok"])
                self.assertEqual(payload_bad_bool["reason_code"], "invalid_type")

            # 3. mode="main", preview=True AND mode="workspace" preserve all publication pointers (zero-publish).
            code_main_prev, payload_main_prev = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers=auth_headers,
                body={"action": "execute", "task_id": 101, "mode": "main", "preview": True},
            )
            self.assertEqual(code_main_prev, 200, payload_main_prev)
            self.assertTrue(payload_main_prev["ok"])
            self.assertTrue(payload_main_prev["preview"])
            self.assertFalse(payload_main_prev["lease_acquired"])
            self.assertTrue(payload_main_prev["publication_pointers_preserved"])

            for action in ("gate", "execute", "resume", "route"):
                code, payload = _http_json(
                    f"{base_url}/api/knowledge/b-route",
                    method="POST",
                    headers=auth_headers,
                    body={
                        "action": action,
                        "task_id": 101,
                        "mode": "workspace",
                        "preview": action == "gate",
                        "recommendation_only": action == "gate",
                        "cached_readiness": {"ready": True},
                        "cached_input_set_digest": "sha256:" + ("0" * 64),
                        "cached_status": "done",
                    },
                )
                self.assertEqual(code, 200, f"{action}: {payload}")
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["admitted"])
                self.assertEqual(payload["route"], "B")
                self.assertTrue(payload["live_authority_enforced"])
                self.assertTrue(payload["cache_authorization_rejected"])
                self.assertIn("cached_readiness", payload["ignored_cache_fields"])
                self.assertTrue(payload["publication_pointers_preserved"])
                self.assertFalse(payload["flow_completed"])
                self.assertFalse(payload["runtime_verified"])
                self.assertFalse(payload["default_b_enabled"])
                if action in ("execute", "resume", "route"):
                    self.assertTrue(payload["lease_acquired"])
                    self.assertFalse(payload["uses_global_writer_lock"])

            # 4. Explicit cache/snapshot bypass attempt fails closed with 422 CONFLICT.
            code_bypass, payload_bypass = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers=auth_headers,
                body={"action": "execute", "task_id": 101, "skip_live_gate": True, "trust_latest_json": True},
            )
            self.assertEqual(code_bypass, 422)
            self.assertFalse(payload_bypass["ok"])
            self.assertEqual(payload_bypass["reason_code"], "conflict")

            # 5. action="execute" blocks on durable stop_loss (rerun_guard) BEFORE execution!
            sl_dir = "logs/ci/2026-11-24/sc-review-pipeline-task-101-runsl1"
            _put_json(
                repo,
                f"{sl_dir}/summary.json",
                {
                    "task_id": "101",
                    "run_id": "runsl1",
                    "status": "fail",
                    "reason": "rerun_blocked:repeat_deterministic_failure",
                    "failed_step": "sc-test",
                },
            )
            _put_json(
                repo,
                f"{sl_dir}/marathon-state.json",
                {
                    "task_id": "101",
                    "run_id": "runsl1",
                    "status": "stopped",
                    "diagnostics": {"rerun_guard": {"kind": "repeat_deterministic_failure", "blocked": True}},
                },
            )
            # Freeze product_tree_digest so durable stop_loss sees zero source fix since stop.
            prod_fp = ch6_rec._product_tree_fingerprint(repo)
            _put_json(
                repo,
                f"{sl_dir}/{ch6_rec.RECOVERY_INPUT_SET_FILENAME}",
                {
                    "schema_version": ch6_rec.RECOVERY_INPUT_SET_SCHEMA,
                    "task_id": 101,
                    "route": "B",
                    "input_set_digest": payload_main_prev["input_set_digest"],
                    "applicable_set_digest": payload_main_prev["applicable_set_digest"],
                    "scope_ids": payload_main_prev["scope_ids"],
                    "product_tree_digest": prod_fp["digest"],
                    "recovery_epoch": 0,
                    "runtime_verified": False,
                    "default_b_enabled": False,
                },
            )
            code_sl, payload_sl = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers=auth_headers,
                body={"action": "execute", "task_id": 101, "mode": "workspace", "preview": False, "recommendation_only": False},
            )
            self.assertEqual(code_sl, 422, payload_sl)
            self.assertFalse(payload_sl["ok"])
            self.assertFalse(payload_sl["admitted"])
            self.assertFalse(payload_sl["lease_acquired"])
            shutil.rmtree(repo / sl_dir, ignore_errors=True)

            # 6. action="execute" blocks on disguised_definition_change (Story 3.10 anti-disguise)!
            disg_dir = "logs/ci/2026-11-24/sc-review-pipeline-task-101-rundisg"
            _put_json(
                repo,
                f"{disg_dir}/summary.json",
                {"task_id": "101", "run_id": "rundisg", "status": "ok", "reason": "ok"},
            )
            _put_json(
                repo,
                f"{disg_dir}/execution-context.json",
                {"changed_paths": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"]},
            )
            _put_json(
                repo,
                f"{disg_dir}/agent-review.json",
                {
                    "review_verdict": "needs-fix",
                    "findings": [
                        {
                            "finding_id": "F-DISG-1",
                            "severity": "P1",
                            "category": "acceptance-refs",
                            "owner_step": "sc-acceptance-check",
                            "source_path": ".taskmaster/tasks/tasks_back.json",
                            "message": "Acceptance Refs weakened with mvg:N/A bypass attempt.",
                        }
                    ],
                },
            )
            code_disg, payload_disg = _http_json(
                f"{base_url}/api/knowledge/b-route",
                method="POST",
                headers=auth_headers,
                body={
                    "action": "execute",
                    "task_id": 101,
                    "run_id": "rundisg",
                    "mode": "workspace",
                    "preview": False,
                    "recommendation_only": False,
                },
            )
            self.assertEqual(code_disg, 422, payload_disg)
            self.assertFalse(payload_disg["ok"])
            self.assertEqual(payload_disg["blocked_by"], "b_route_defect_routing")
            shutil.rmtree(repo / disg_dir, ignore_errors=True)

            # 7. Tamper binding on disk -> POST /api/knowledge/b-route, /api/knowledge/runtime, AND /api/knowledge/mvg-run ALL return 422!
            (repo / "docs/planning/b-route/bindings/plan-reward/1.json").unlink()
            with patch.dict(os.environ, {"GODOT_BIN": "fake-godot.exe"}, clear=False):
                code_tamper, payload_tamper = _http_json(
                    f"{base_url}/api/knowledge/b-route",
                    method="POST",
                    headers=auth_headers,
                    body={"action": "execute", "task_id": 101, "mode": "workspace", "cached_readiness": {"ready": True}},
                )
                self.assertEqual(code_tamper, 422)
                self.assertFalse(payload_tamper["ok"])
                self.assertEqual(payload_tamper["blocked_by"], "b_route_chapter6_gate")

                # Remove latest.json completely to prove /api/knowledge/mvg-run & /api/knowledge/runtime enforce live B-gate BEFORE latest.json!
                (repo / "logs/ci/project-health-knowledge/latest.json").unlink()
                code_mvg_http, payload_mvg_http = _http_json(
                    f"{base_url}/api/knowledge/mvg-run",
                    method="POST",
                    headers=auth_headers,
                    body={"revision": "c" * 40, "manifest": "docs/testing/mvg/reward-baseline.json"},
                )
                self.assertEqual(code_mvg_http, 422, payload_mvg_http)
                self.assertFalse(payload_mvg_http["ok"])
                self.assertEqual(payload_mvg_http["blocked_by"], "b_route_chapter6_gate")

                code_rt_http, payload_rt_http = _http_json(
                    f"{base_url}/api/knowledge/runtime",
                    method="POST",
                    headers=auth_headers,
                    body={"all_gameplay": True, "mode": "workspace"},
                )
                self.assertEqual(code_rt_http, 422, payload_rt_http)
                self.assertEqual(payload_rt_http["blocked_by"], "b_route_chapter6_gate")
        finally:
            server.shutdown()
            server.server_close()

        # Verify ALL remaining publication pointers stayed byte-identical!
        for rel, expected_raw in pointers.items():
            if rel == "logs/ci/project-health-knowledge/latest.json":
                continue
            self.assertEqual((repo / rel).read_bytes(), expected_raw, f"Publication pointer mutated: {rel}")

    def test_ac1_rogue_runner_mutating_publication_pointer_in_workspace_preview_is_blocked(self) -> None:
        repo = self._clone(self._flow_base, "ac1_rogue")
        _seed_fake_knowledge_scan_and_pointers(repo, task_id=101)

        def _rogue_runner(_ctx: dict, _handle) -> dict:
            _put_json(repo, "docs/knowledge/published/current.json", {"publication_id": "hijacked"})
            return {"status": "mutated"}

        res = parity.handle_page_b_route_trigger(
            repo,
            {"action": "execute", "task_id": 101, "mode": "workspace", "preview": False, "recommendation_only": False},
            execute_runner=_rogue_runner,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason_code"], "conflict")
        self.assertFalse(res["publication_pointers_preserved"])
        self.assertIn("docs/knowledge/published/current.json", res["mutated_publication_pointers"])

    def test_ac1_project_health_runtime_discovers_live_workspace_refs_without_latest_json_and_blocks_tamper(self) -> None:
        # 1. Live workspace discovery without latest.json ignores stale refs and runs live Tests.Godot/ ref under lease!
        ws_repo = self._clone(self._flow_base, "ac1_ws_live")
        live_gd_rel = "Tests.Godot/tests/Reward/test_live_reward.gd"
        _put(ws_repo, live_gd_rel, "extends Node\n")
        _put_json(
            ws_repo,
            ".taskmaster/tasks/tasks_gameplay.json",
            [{"id": "GM-0101", "taskmaster_id": 101, "title": "Reward task", "status": "in-progress", "test_refs": [live_gd_rel]}],
        )
        # Reconcile Task 101 after updating tasks_gameplay.json so InputSet matches live triplet!
        _reconcile_task_ready(ws_repo, 101, mode="flow", include_planned=False)
        self.assertFalse((ws_repo / "logs/ci/project-health-knowledge/latest.json").exists())

        seen_refs: list[list[str]] = []

        def _fake_run_task(run_root: Path, task: dict, godot_bin: str, timeout: int, source_revision: str) -> dict:
            seen_refs.append(list(task.get("runtime_test_refs") or []))
            # Prove OS scope lock IS held during _run_task!
            self.assertIsNotNone(os.environ.get(ch6_gate.ENV_LEASE_PATH))
            return {
                "task_id": "101",
                "source_revision": source_revision,
                "test_refs": list(task.get("runtime_test_refs") or []),
                "scenes": [],
                "status": "passed",
                "reason": None,
                "started_at": "s",
                "finished_at": "f",
                "evidence_path": "logs/ci/project-health-knowledge/runtime/task-101.json",
                "exit_code": 0,
                "runtime_verified": False,
            }

        with (
            patch.object(ph_runtime, "prepare_snapshot", return_value={"source_revision": "workspace:live", "files": {}}),
            patch.object(ph_runtime, "_run_task", side_effect=_fake_run_task),
        ):
            ws_res = ph_runtime.verify(ws_repo, "fake-godot.exe", 30, all_gameplay=True, mode="workspace")
        self.assertEqual(seen_refs, [[live_gd_rel]])
        self.assertTrue(ws_res["tasks"][0]["workspace_verified"])
        self.assertFalse(ws_res["tasks"][0]["runtime_verified"])

        # 2. Tamper bound MVG manifest while spoofed latest.json claims ready -> blocks pre-snapshot!
        repo = self._clone(self._flow_base, "ac1_runtime")
        _seed_fake_knowledge_scan_and_pointers(repo, task_id=101)
        (repo / "docs/testing/mvg/reward-baseline.json").unlink()

        with patch.object(ph_runtime, "prepare_snapshot") as mock_snap, \
                patch.object(ph_runtime, "_run_task") as mock_run:
            with self.assertRaises(ph_runtime.RuntimeGateBlockedError) as ctx:
                ph_runtime.verify(repo, "fake-godot.exe", 60, task_id="101", mode="workspace")
            self.assertEqual(mock_snap.call_count, 0)
            self.assertEqual(mock_run.call_count, 0)
            self.assertEqual(ctx.exception.payload["blocked_by"], "b_route_chapter6_gate")
            self.assertEqual(ctx.exception.payload["return_stage"], "5")

        # 3. run_mvg_manifest rejects pre-effect BEFORE git or latest.json checks, and holds scope lease when admitted!
        with patch.object(ph_http.subprocess, "run", side_effect=AssertionError("must block before subprocess")) as mock_sub:
            code, mvg_payload = ph_http.run_mvg_manifest(repo, "not-even-40-hex", "fake-godot.exe", "docs/testing/mvg/reward-baseline.json")
        self.assertEqual(code, 422)
        self.assertFalse(mvg_payload["ok"])
        self.assertEqual(mvg_payload["reason_code"], "file_not_found")
        self.assertEqual(mock_sub.call_count, 0)

    # ------------------------------------------------------------------
    # AC-2: PARITY_APPLICABLE (Four legal scopes + multi-hop transitive deps across all 5 entrypoints)
    # ------------------------------------------------------------------

    def test_ac2_five_entrypoint_parity_across_flow_nonflow_integration_owner_multihop_and_frozen_or_explicit_a(self) -> None:
        flow_repo = self._clone(self._flow_base, "ac2_flow")
        nonflow_repo = self._clone(self._nonflow_base, "ac2_nonflow")

        integ_repo = self._clone(self._flow_base, "ac2_integ")
        mdoc = json.loads((integ_repo / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        for row in mdoc["master"]["tasks"]:
            if int(row["id"]) in (101, 102):
                row["status"] = "done"
        _put_json(integ_repo, ".taskmaster/tasks/tasks.json", mdoc)

        # Multi-hop transitive chain: Task 103 -> [101 (done), 102 (done)] -> 201 (in-progress): must block across ALL 5 entrypoints!
        multihop_blk_repo = self._clone(self._flow_base, "ac2_multihop_blk")
        mdoc_mh = json.loads((multihop_blk_repo / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        for row in mdoc_mh["master"]["tasks"]:
            if int(row["id"]) == 101:
                row["status"] = "done"
            elif int(row["id"]) == 102:
                row["status"] = "done"
                row["dependencies"] = [201]
            elif int(row["id"]) == 201:
                row["status"] = "in-progress"
        _put_json(multihop_blk_repo, ".taskmaster/tasks/tasks.json", mdoc_mh)
        _reconcile_task_ready(multihop_blk_repo, 103, mode="flow", include_planned=False)

        exp_a_repo = self._clone(self._explicit_a_base, "ac2_exp_a")
        frozen_repo = self._clone(self._frozen_a_base, "ac2_frozen_a")
        frozen_tid = self._frozen_a_info["task_id"]

        with concurrent.futures.ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 6)) as pool:
            f_flow = pool.submit(_eval_parity_worker, str(flow_repo), 101)
            f_nonflow = pool.submit(_eval_parity_worker, str(nonflow_repo), 101)
            f_integ = pool.submit(_eval_parity_worker, str(integ_repo), 103)
            f_mh_blk = pool.submit(_eval_parity_worker, str(multihop_blk_repo), 103)
            f_exp_a = pool.submit(_eval_parity_worker, str(exp_a_repo), 11)
            f_frozen = pool.submit(_eval_parity_worker, str(frozen_repo), frozen_tid)

            r_flow = f_flow.result()
            r_nonflow = f_nonflow.result()
            r_integ = f_integ.result()
            r_mh_blocked = f_mh_blk.result()
            r_exp_a = f_exp_a.result()
            r_frozen = f_frozen.result()

        self.assertTrue(r_flow["ok"], r_flow["mismatches"])
        self.assertTrue(r_flow["parity_ok"])
        self.assertEqual(r_flow["route"], "B")
        self.assertTrue(r_flow["admitted"])
        self.assertFalse(r_flow["flow_completed"])
        self.assertFalse(r_flow["default_b_enabled"])
        self.assertFalse(r_flow["self_done_required"])
        self.assertEqual(set(r_flow["entrypoints"].keys()), {"cli", "direct", "resume", "route", "page"})

        self.assertTrue(r_nonflow["ok"], r_nonflow["mismatches"])
        self.assertTrue(r_nonflow["parity_ok"])
        self.assertEqual(r_nonflow["route"], "B")
        self.assertTrue(r_nonflow["admitted"])
        self.assertFalse((nonflow_repo / "docs/testing/mvg/reward-baseline.json").exists())
        for ep in r_nonflow["entrypoints"].values():
            self.assertFalse(ep["fabricated_manifest"])
            self.assertFalse(ep["fabricated_business_api"])

        self.assertTrue(r_integ["ok"], r_integ["mismatches"])
        self.assertTrue(r_integ["parity_ok"])
        self.assertEqual(r_integ["route"], "B")
        self.assertTrue(r_integ["admitted"])
        self.assertFalse(r_integ["self_done_required"])

        # 2-hop transitive dependency 101 incomplete -> ALL 5 entrypoints block Task 103 consistently!
        self.assertTrue(r_mh_blocked["parity_ok"], r_mh_blocked["mismatches"])
        self.assertFalse(r_mh_blocked["admitted"])
        self.assertEqual(r_mh_blocked["public_reason_code"], "conflict")
        self.assertEqual(r_mh_blocked["return_stage"], "3C")

        self.assertTrue(r_exp_a["ok"], r_exp_a["mismatches"])
        self.assertTrue(r_exp_a["parity_ok"])
        self.assertEqual(r_exp_a["route"], "explicit_not_enabled_a")
        self.assertTrue(r_exp_a["admitted"])

        self.assertTrue(r_frozen["ok"], r_frozen["mismatches"])
        self.assertTrue(r_frozen["parity_ok"], r_frozen["mismatches"])
        self.assertEqual(r_frozen["route"], "A")
        self.assertTrue(r_frozen["admitted"])

    # ------------------------------------------------------------------
    # AC-3: TAMPER_BEFORE_FX (11 counterexamples across public & direct modules, zero special cases)
    # ------------------------------------------------------------------

    def test_ac3_all_tamper_counterexamples_block_consistently_across_public_and_direct_entrypoints(self) -> None:
        cases = (
            "delete_origins",
            "delete_manifest",
            "blank_nonflow_rationale",
            "damaged_journal",
            "cap_pending_marker",
            "legacy_mvg_apply_journal",
            "hashed_operation_corruption",
            "severed_binding",
            "new_plan_shared_task",
            "unknown_origin_legacy_pending",
            "explicit_unknown_origin_row",
        )
        staged: list[tuple[str, str, int]] = []
        for case in cases:
            if case == "blank_nonflow_rationale":
                repo = self._clone(self._nonflow_base, f"ac3_{case}")
                plan_p = repo / "docs/planning/b-route/plans/plan-reward/1.json"
                pdoc = json.loads(plan_p.read_text(encoding="utf-8"))
                pdoc["requirement_verification"][0]["rationale"] = "   "
                _reseal_plan_and_catalog(repo, plan_doc=pdoc)
                tid = 101
            else:
                repo = self._clone(self._flow_base, f"ac3_{case}")
                tid = 101
                if case == "delete_origins":
                    (repo / "docs/planning/b-route/task-origins.v1.json").unlink()
                elif case == "delete_manifest":
                    (repo / "docs/testing/mvg/reward-baseline.json").unlink()
                elif case == "damaged_journal":
                    _put(repo, "logs/ci/b-route-operations/OP-BROKEN/apply-journal.json", "{not-valid-json")
                elif case == "cap_pending_marker":
                    cap_j_rel = "logs/ci/capability-planning/cap-run-1/apply-journal.json"
                    _put_json(repo, "logs/ci/capability-planning/cap-run-1/run.json", {"run_id": "cap-run-1", "status": "applying"})
                    _put_json(
                        repo,
                        cap_j_rel,
                        {
                            "schema_version": "newrouge.planning-apply-journal.v1",
                            "kind": "capabilities",
                            "run_id": "cap-run-1",
                            "status": "in_progress",
                            "authority_inputs": {},
                            "entries": [],
                            "result": {},
                        },
                    )
                    _put_json(repo, op_scope.CAP_PENDING, {"run_id": "cap-run-1", "journal_path": cap_j_rel})
                elif case == "legacy_mvg_apply_journal":
                    _put(repo, "logs/ci/mvg-planning/mvg-run-1/apply-journal.json", "{corrupt-mvg-journal")
                elif case == "hashed_operation_corruption":
                    op_rel = journal._operation_ref("OP-HASH-CORRUPT")
                    _put(repo, op_rel, "{corrupt-hashed-operation")
                elif case == "severed_binding":
                    (repo / "docs/planning/b-route/bindings/plan-reward/1.json").unlink()
                elif case == "new_plan_shared_task":
                    _add_second_plan_sharing_task101(repo)
                elif case == "unknown_origin_legacy_pending":
                    master_p = repo / ".taskmaster/tasks/tasks.json"
                    mdoc = json.loads(master_p.read_text(encoding="utf-8"))
                    mdoc["master"]["tasks"].append(
                        {"id": 999, "title": "Legacy pending task", "status": "pending", "dependencies": []}
                    )
                    _put_json(repo, ".taskmaster/tasks/tasks.json", mdoc)
                    tid = 999
                elif case == "explicit_unknown_origin_row":
                    origins_p = repo / "docs/planning/b-route/task-origins.v1.json"
                    odoc = json.loads(origins_p.read_text(encoding="utf-8"))
                    for row in odoc.get("tasks") or []:
                        if int(row.get("task_id", -1)) == 101:
                            row["origin"] = "unknown"
                    _put_json(repo, "docs/planning/b-route/task-origins.v1.json", odoc)
            staged.append((case, str(repo), tid))

        with concurrent.futures.ProcessPoolExecutor(max_workers=min(11, os.cpu_count() or 8)) as pool:
            futs = [pool.submit(_eval_ac3_case_worker, c, r, t) for c, r, t in staged]
            outcomes = [f.result() for f in futs]

        for out in outcomes:
            case = out["case"]
            res = out["parity"]
            with self.subTest(case=case):
                self.assertTrue(res["parity_ok"], f"{case} mismatches: {res['mismatches']}")
                self.assertFalse(res["admitted"], f"{case} unexpectedly admitted: {res}")
                self.assertTrue(res["readiness_invalidated"], f"{case} did not invalidate readiness")
                self.assertNotEqual(res["route"], "explicit_not_enabled_a", f"{case} fell back to legacy A!")
                if case in ("unknown_origin_legacy_pending", "explicit_unknown_origin_row"):
                    self.assertEqual(res["route"], "blocked")

                expected_rc = res["public_reason_code"]
                for consumer_name, ok_flag in out["direct_checks"].items():
                    self.assertFalse(ok_flag, f"{case}/{consumer_name} bypassed gate!")
                rt_gate = out["rt_gate"]
                self.assertFalse(rt_gate["ok"])
                self.assertEqual(rt_gate["public_reason_code"], expected_rc)

                if case == "explicit_unknown_origin_row":
                    mvg_gate = parity.enforce_mvg_manifest_gate(Path(dict((c, r) for c, r, _ in staged)[case]), "docs/testing/mvg/reward-baseline.json")
                    self.assertFalse(mvg_gate["ok"])

    # ------------------------------------------------------------------
    # AC-4: WIN_CONCURRENCY (Real _b_route_commit replay no-op, raw preimage stop, projection reuse, zero-write union scope & msvcrt contention)
    # ------------------------------------------------------------------

    def test_ac4_windows_real_commit_replay_noop_preimage_conflict_projection_reuse_and_cross_process_lease_contention(self) -> None:
        # 1. Real _b_route_commit terminal operation + Task 101 status advanced to "done" -> b_route_commit.recover no-op!
        s5_fx = Stage5RepoFixture()
        try:
            assets = s5_fx.build_committed_stage4(mode="flow", include_other_plan=False)
            op_id = "OP-S5-REAL-DONE-001"
            req_doc = {
                "schema_version": s5.REQUEST_SCHEMA,
                "producer": s5.PRODUCER,
                "operation_id": op_id,
                "plan_id": s5_fx.plan_id,
                "scope_id": s5_fx.scope_id,
                "manifest_refs": [copy.deepcopy(assets["mvg_manifest_ref"])],
                "other_verification_refs": [],
                "obligations": [
                    {
                        "id": "OBL-REWARD-1",
                        "task_ids": [101, 102],
                        "requirement_ids": ["REQ-REWARD-1"],
                        "flow_ids": ["flow-reward-select"],
                        "test_ids": ["test-reward-flow"],
                        "category": "current_new",
                        "responsibility": "Verify reward flow handoff.",
                        "verification_refs": [copy.deepcopy(assets["mvg_manifest_ref"])],
                    }
                ],
            }
            _run_full_lifecycle(s5_fx, op_id, req_doc, include_preview=False)
            # Advance Task 101 status in tasks.json to "done" AFTER operation completed!
            mdoc = s5_fx.read_json(".taskmaster/tasks/tasks.json")
            for row in mdoc["master"]["tasks"]:
                if int(row["id"]) == 101:
                    row["status"] = "done"
            master_done_bytes = s5_fx.put_json(".taskmaster/tasks/tasks.json", mdoc)

            comp = parity.verify_completed_apply_status_preservation(s5_fx.root, operation_id=op_id, task_id=101)
            self.assertTrue(comp["ok"], comp)
            self.assertEqual(comp["replay_mode"], "b_route_commit.recover")
            self.assertTrue(comp["noop"])
            self.assertTrue(comp["preserves_live_status"])
            self.assertFalse(comp["overwrites_status"])
            self.assertEqual(comp["live_status"], "done")
            self.assertEqual((s5_fx.root / ".taskmaster/tasks/tasks.json").read_bytes(), master_done_bytes)

            # Completed operation MUST be rejected by verify_incomplete_apply_raw_preimage_guard!
            not_inc = parity.verify_incomplete_apply_raw_preimage_guard(s5_fx.root, operation_id=op_id)
            self.assertFalse(not_inc["ok"])
            self.assertEqual(not_inc["reason_code"], "conflict")
        finally:
            s5_fx.cleanup()

        # 2. Incomplete in_progress apply: raw byte drift AND newly-created-file conflict both halt with CONFLICT!
        repo2 = self._clone(self._flow_base, "ac4_incomplete")
        orig_raw = (repo2 / ".taskmaster/tasks/tasks.json").read_bytes()
        _put_json(
            repo2,
            "logs/ci/b-route-operations/OP-WIP-002/apply-journal.json",
            {
                "operation_id": "OP-WIP-002",
                "state": "in_progress",
                "targets": [
                    {
                        "path": ".taskmaster/tasks/tasks.json",
                        "before_raw_digest": codec.raw_digest(orig_raw),
                        "after_raw_digest": "sha256:" + ("2" * 64),
                    },
                    {
                        "path": "docs/planning/b-route/bindings/plan-reward/99.json",
                        "before_raw_digest": None,
                        "after_raw_digest": None,
                    },
                ],
            },
        )
        # Create unexpected file at newly-created target path AND edit tasks.json raw bytes!
        unexpected_raw = _put_json(repo2, "docs/planning/b-route/bindings/plan-reward/99.json", {"rogue": True})
        mdoc2 = json.loads(orig_raw.decode("utf-8"))
        mdoc2["master"]["tasks"][0]["status"] = "done"
        edited_raw = _put_json(repo2, ".taskmaster/tasks/tasks.json", mdoc2)
        guard = parity.verify_incomplete_apply_raw_preimage_guard(repo2, operation_id="OP-WIP-002")
        self.assertFalse(guard["ok"])
        self.assertTrue(guard["conflict_detected"])
        self.assertEqual(guard["reason_code"], "conflict")
        self.assertEqual(len(guard["conflicts"]), 2)
        self.assertTrue(guard["post_edit_preserved"])
        self.assertFalse(guard["mutated"])
        self.assertEqual((repo2 / ".taskmaster/tasks/tasks.json").read_bytes(), edited_raw)
        self.assertEqual((repo2 / "docs/planning/b-route/bindings/plan-reward/99.json").read_bytes(), unexpected_raw)

        # 3. Relevant Task definition projection drift invalidates InputSet (3C) vs irrelevant metadata reuse!
        repo3 = self._clone(self._flow_base, "ac4_projection")
        baseline = input_set.resolve_input_set(repo3, 101)
        self.assertTrue(baseline["ok"])
        mdoc3 = json.loads((repo3 / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        for row in mdoc3["master"]["tasks"]:
            if int(row["id"]) == 201:
                row["status"] = "done"
        _put_json(repo3, ".taskmaster/tasks/tasks.json", mdoc3)
        reuse_res = parity.verify_projection_vs_irrelevant_change(repo3, task_id=101, baseline_input_set=baseline)
        self.assertTrue(reuse_res["ok"])
        self.assertTrue(reuse_res["input_set_reusable"])
        self.assertFalse(reuse_res["projection_changed"])
        self.assertEqual(reuse_res["baseline_input_set_digest"], reuse_res["live_input_set_digest"])

        for row in mdoc3["master"]["tasks"]:
            if int(row["id"]) == 101:
                row["title"] = "Changed producer definition title"
        _put_json(repo3, ".taskmaster/tasks/tasks.json", mdoc3)
        drift_res = parity.verify_projection_vs_irrelevant_change(repo3, task_id=101, baseline_input_set=baseline)
        self.assertFalse(drift_res["input_set_reusable"])
        self.assertTrue(drift_res["projection_changed"])
        self.assertEqual(drift_res["return_stage"], "3C")

        # 4. Shared Task multi-plan union scope: zero-write verifier, non-substring task_id=1010 isolation,
        #    marker-deletion non-bypass, AND real cross-process Windows msvcrt lease contention!
        repo4 = self._clone(self._flow_base, "ac4_union")
        _add_second_plan_sharing_task101(repo4)
        dec_shared = _decisions_for_task(mode="flow", task_id=101, include_planned=False)
        dec_shared["authority_decisions"].append(
            {
                "authority_ref": "docs/testing/nonflow-checklist.md",
                "status": "compatible",
                "rationale": "Shared extra non-flow verification checklist.",
            }
        )
        dec_shared["acceptance_links"][0]["requirement_ids"] = ["REQ-REWARD-1", "REQ-SHARED-EXTRA-1"]
        dec_shared["acceptance_links"][0]["authority_refs"].append("docs/testing/nonflow-checklist.md")
        dec_shared_rel = "logs/ci/chapter5/decisions-task-101.json"
        _put_json(repo4, dec_shared_rel, dec_shared)
        rec4 = ch5_b.reconcile_b_route_chapter5(repo4, task_id=101, decisions=dec_shared_rel, write_artifacts=True)
        self.assertTrue(rec4["ok"], f"Shared multi-plan Chapter 5 reconciliation failed: {rec4}")
        # Remove any lock dirs created during reconciliation so we prove strictly ZERO disk writes!
        shutil.rmtree(repo4 / op_scope.STORE, ignore_errors=True)

        # Unrelated pending journal for Task 1010 ("101" is a substring of "1010"!) must NOT falsely block Task 101!
        _put_json(
            repo4,
            "logs/ci/b-route-stage5-obligations/OP-UNRELATED-1010/public-sync-journal.json",
            {
                "operation_id": "OP-UNRELATED-1010",
                "state": "in_progress",
                "plan_id": "plan-1010",
                "scope_ids": ["plan:plan-1010", "task:1010"],
                "task_ids": [1010],
            },
        )

        snap_before = _snapshot_all_entries(repo4)
        union_ok = parity.verify_shared_task_union_scope_and_pending_guard(repo4, task_id=101)
        snap_after = _snapshot_all_entries(repo4)
        self.assertEqual(snap_before, snap_after, "Read-only union scope verifier created or modified files on disk!")
        self.assertTrue(union_ok["ok"], union_ok)
        self.assertTrue(union_ok["union_scope_fully_locked"])
        expected_plan_scopes = op_scope.resource_scopes(plan_ids=["plan-reward", "plan-shared-extra"])
        for ps in expected_plan_scopes:
            self.assertIn(ps, union_ok["locked_scope_ids"])
        self.assertEqual(set(union_ok["plan_ids"]), {"plan-reward", "plan-shared-extra"})
        self.assertFalse(union_ok["uses_global_writer_lock"])

        # Real cross-process Windows msvcrt contention on ONE scope of the shared union blocks both verifier and leases!
        contended_scope = sorted(expected_plan_scopes)[-1]
        holder_code = (
            "import sys\n"
            "import _b_route_operation_scope as op_scope\n"
            f"with op_scope.business_guard({str(repo4)!r}, [{contended_scope!r}], review_only=True):\n"
            "    sys.stdout.write('LOCKED\\n')\n"
            "    sys.stdout.flush()\n"
            "    sys.stdin.readline()\n"
        )
        child_env = {**os.environ, "PYTHONPATH": str(SCRIPTS_PY), "PYTHONDONTWRITEBYTECODE": "1"}
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", holder_code],
            cwd=str(repo4),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert holder.stdout is not None
            ready_line = holder.stdout.readline().strip()
            self.assertEqual(ready_line, "LOCKED")

            contended_res = parity.verify_shared_task_union_scope_and_pending_guard(repo4, task_id=101)
            self.assertFalse(contended_res["ok"])
            self.assertEqual(contended_res["reason_code"], "conflict")

            with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx_ch6:
                with parity.acquire_chapter6_gate_lease(repo4, 101, consumer="contention_test"):
                    pass
            self.assertEqual(ctx_ch6.exception.gate_result["reason_code"], "conflict")

            rt_gate_pre = parity.enforce_runtime_task_gate(repo4, [101], mode="workspace")
            self.assertTrue(rt_gate_pre["ok"], rt_gate_pre)
            with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx_rt:
                with parity.acquire_runtime_scope_leases(repo4, rt_gate_pre, consumer="rt_contention_test"):
                    pass
            self.assertEqual(ctx_rt.exception.gate_result["reason_code"], "conflict")
        finally:
            if holder.stdin is not None:
                try:
                    holder.stdin.write("release\n")
                    holder.stdin.flush()
                except OSError:
                    pass
            holder.communicate(timeout=30)

        # Once sibling releases, multi-task runtime lease + ENV_LEASE_* reentrancy succeed without deadlock!
        rt_gate_multi = parity.enforce_runtime_task_gate(repo4, [101, 201], mode="workspace")
        self.assertTrue(rt_gate_multi["ok"], rt_gate_multi)
        with parity.acquire_runtime_scope_leases(repo4, rt_gate_multi, consumer="parent_rt") as outer_lease:
            self.assertTrue(outer_lease["lease_acquired"])
            self.assertFalse(outer_lease["inherited_lease"])
            with parity.acquire_runtime_scope_leases(repo4, rt_gate_multi, consumer="reentrant_rt") as inner_lease:
                self.assertTrue(inner_lease["lease_acquired"])
                self.assertTrue(inner_lease["inherited_lease"])
            for tid_check in (101, 201):
                child_g = ch6_gate.enforce_internal_script_gate(repo4, tid_check, consumer="sc-test")
                self.assertTrue(child_g["ok"], child_g)

        # Create ephemeral marker + unresolved overlapping journal, then DELETE ephemeral marker -> still blocked!
        ephemeral_marker = repo4 / op_scope.CAP_PENDING
        _put_json(repo4, op_scope.CAP_PENDING, {"run_id": "cap-ephem", "journal_path": "logs/ci/capability-planning/cap-ephem/apply-journal.json"})
        _put_json(
            repo4,
            "logs/ci/b-route-stage5-obligations/OP-UNRES-003/public-sync-journal.json",
            {"operation_id": "OP-UNRES-003", "state": "in_progress", "plan_id": "plan-shared-extra", "task_ids": [101]},
        )
        ephemeral_marker.unlink()
        union_blocked = parity.verify_shared_task_union_scope_and_pending_guard(repo4, task_id=101)
        self.assertFalse(union_blocked["ok"])
        self.assertEqual(union_blocked["reason_code"], "pending")
        self.assertTrue(union_blocked["marker_deletion_bypass_blocked"])
        self.assertTrue(union_blocked["unresolved_pending"])

    # ------------------------------------------------------------------
    # AC-5: EPIC3_HANDOFF & CLI / Builder Exclusive Report Contracts
    # ------------------------------------------------------------------

    def test_ac5_epic3_to_epic4_handoff_negative_controls_and_cli_exclusive_report_contracts(self) -> None:
        # 1. Full REPO_ROOT handoff dynamically verifies all 21 consumers, CLI commands, and doc anchors.
        handoff = parity.build_epic3_to_epic4_handoff(REPO_ROOT)
        self.assertTrue(
            handoff["ok"],
            f"Missing items: consumers={handoff['missing_consumers']} cli={handoff['missing_cli']} docs={handoff['missing_docs']}",
        )
        self.assertEqual(handoff["schema_version"], parity.EPIC3_HANDOFF_SCHEMA)
        self.assertEqual(handoff["epic"], "epic-3")
        self.assertEqual(handoff["next_epic"], "epic-4")
        self.assertTrue(all(handoff["delivered_epic3_capabilities"].values()))
        self.assertEqual(
            handoff["unimplemented_epic4_epic5_capabilities"],
            {
                "selective_verification_scope_runner": False,
                "complete_b_route_knowledge_progress_display": False,
                "reward_slice_end_to_end_pilot_executed": False,
                "full_repository_b_migration_completed": False,
                "cumulative_full_mvg_runtime_verified": False,
            },
        )
        self.assertFalse(handoff["flow_completed"])
        self.assertFalse(handoff["runtime_verified"])
        self.assertFalse(handoff["default_b_enabled"])
        self.assertFalse(handoff["claims_full_migration"])
        self.assertFalse(handoff["claims_cumulative_full_mvg"])

        # 2. Handoff with explicit task_ids=[101] populates per_task_parity, live_artifact_digests, and traceable_event_refs;
        #    and negative control on missing doc/consumer flips delivered capability & ok to False!
        handoff_repo = self._clone(self._flow_base, "ac5_handoff_tasks")
        for rel in (*parity.EPIC3_CONSUMERS, "scripts/python/dev_cli.py", *parity.EPIC3_OWNING_DOCS):
            src_file = REPO_ROOT / rel
            if src_file.is_file():
                _put(handoff_repo, rel, src_file.read_text(encoding="utf-8"))
        ch6_gate.record_chapter6_gate_event(
            handoff_repo,
            task_id=101,
            consumer="test_ac5",
            event_kind="execution",
            gate_result={"ok": True, "task_id": 101, "route": "B"},
        )
        handoff_with_tasks = parity.build_epic3_to_epic4_handoff(handoff_repo, task_ids=[101])
        self.assertTrue(handoff_with_tasks["ok"], handoff_with_tasks["diagnostics"])
        self.assertEqual(handoff_with_tasks["metrics"]["evaluated_task_count"], 1)
        self.assertIn(records.CATALOG_PATH, handoff_with_tasks["live_artifact_digests"])
        self.assertGreaterEqual(len(handoff_with_tasks["traceable_event_refs"]), 2)

        # Negative control: strip /api/knowledge/b-route anchor from owning doc -> flips capability & ok to False!
        _put(handoff_repo, "docs/workflows/project-health-knowledge.md", "# Stripped doc without endpoint anchor\n")
        handoff_neg = parity.build_epic3_to_epic4_handoff(handoff_repo)
        self.assertFalse(handoff_neg["ok"])
        self.assertFalse(handoff_neg["delivered_epic3_capabilities"]["page_and_five_entrypoint_parity"])
        self.assertTrue(handoff_neg["missing_docs"])

        # 3. CLI zero-write default, exclusive --report / --handoff-report creation, collision & backslash rejection!
        repo = self._clone(self._explicit_a_base, "ac5_cli")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dev_cli.main(["b-route-entrypoint-parity", "--root", str(repo), "--task-id", "11"])
        self.assertEqual(rc, 0)
        cli_out = json.loads(buf.getvalue())
        self.assertTrue(cli_out["ok"])
        self.assertIsNone(cli_out["report_path"])

        report_repo = self._clone(self._explicit_a_base, "ac5_report")
        report_rel = "logs/ci/2026-11-24/parity-report.json"
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = parity_cli.main(["--root", str(report_repo), "--task-id", "11", "--report", report_rel])
        self.assertEqual(rc2, 0)
        written = json.loads((report_repo / report_rel).read_text(encoding="utf-8"))
        self.assertEqual(written["report_path"], report_rel)

        # Existing report path rejected with CONFLICT (rc=2).
        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            rc3 = parity_cli.main(["--root", str(report_repo), "--task-id", "11", "--report", report_rel])
        self.assertEqual(rc3, 2)
        self.assertEqual(json.loads(buf3.getvalue())["reason_code"], "conflict")

        # Colliding --report and --handoff-report (case-insensitive on Windows) rejected BEFORE writing!
        collide_rel_a = "logs/ci/2026-11-24/Collide-Out.json"
        collide_rel_b = "logs/ci/2026-11-24/collide-out.json"
        buf_col = io.StringIO()
        with redirect_stdout(buf_col):
            rc_col = parity_cli.main(
                [
                    "--root",
                    str(report_repo),
                    "--task-id",
                    "11",
                    "--epic3-handoff",
                    "--report",
                    collide_rel_a,
                    "--handoff-report",
                    collide_rel_b,
                ]
            )
        self.assertEqual(rc_col, 2)
        self.assertEqual(json.loads(buf_col.getvalue())["reason_code"], "conflict")
        self.assertFalse((report_repo / collide_rel_a).exists())

        # Backslash or "./" alias in --report rejected upfront with UNSAFE_PATH (rc=2)!
        for bad_rep in (r"logs\ci\2026-11-24\backslash.json", "./logs/ci/2026-11-24/dot.json"):
            buf_bad = io.StringIO()
            with redirect_stdout(buf_bad):
                rc_bad = parity_cli.main(["--root", str(report_repo), "--task-id", "11", "--report", bad_rep])
            self.assertEqual(rc_bad, 2)
            self.assertEqual(json.loads(buf_bad.getvalue())["reason_code"], "unsafe_path")

        # Builder rejects write/apply flags.
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_entrypoint_parity_cmd(
                types.SimpleNamespace(root=".", task_id=["101"], epic3_handoff=False, write=True)
            )
        cmd = dev_cli_builders.build_b_route_entrypoint_parity_cmd(
            types.SimpleNamespace(root=".", task_id=["101"], epic3_handoff=True, operation=None, report=None, handoff_report=None)
        )
        self.assertIn("--epic3-handoff", cmd)
        self.assertIn("--task-id", cmd)


if __name__ == "__main__":
    unittest.main()
