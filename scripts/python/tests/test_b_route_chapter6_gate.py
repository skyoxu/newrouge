"""Deterministic tests for Story 3.8 unified Chapter 6 execution gate, scope leases, and write guards.

Covers every row of the Story 3.8 I/O & Edge-Case Matrix (CLI_DIRECT, BYPASS_BLK,
SCOPE_LOCK, LOCAL_QUAL, STOPLOSS), using setUpClass base-fixture caching for fast execution.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
REPO_ROOT = SCRIPTS_PY.parents[1]
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(SCRIPTS_SC / "build"), str(SCRIPTS_PY / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_operation_scope as op_scope
import _b_route_protection as protection
import _b_route_records as records
import _b_route_task_resolver as task_resolver
from _mvg_capability_checkpoint import coordinator_lock
import _mvg_obligations as mvg_obligations
import apply_chapter7_status_patch as ch7_patch
import check_b_route_chapter6_gate as ch6_gate_cli
import dev_cli
import dev_cli_builders
import run_single_task_chapter6_lane as ch6_lane
import run_single_task_light_lane as light_lane
import update_task_test_refs_from_acceptance_refs as test_refs_sync

from test_b_route_chapter5_readiness import (
    _build_b_route_base_repo,
    _encoded,
    _put,
    _put_json,
)


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


def _decisions_for_task(mode: str = "flow", *, task_id: int = 101, include_planned: bool = True) -> dict:
    overlay_rel = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"
    if mode == "nonflow":
        return {
            "authority_decisions": [
                {"authority_ref": overlay_rel, "status": "compatible", "rationale": "Overlay matches non-flow scope."},
                {"authority_ref": "ADR-0004", "status": "compatible", "rationale": "Contracts remain BCL-only."},
            ],
            "acceptance_links": [
                {
                    "acceptance_index": 1,
                    "requirement_ids": ["REQ-NONFLOW-1"],
                    "authority_refs": [overlay_rel, "ADR-0004", "docs/testing/nonflow-checklist.md"],
                    "test_refs": ["docs/testing/nonflow-checklist.md"],
                }
            ],
            "dependency_decisions": [],
            "overlap_decisions": [],
            "findings": [],
        }
    if task_id == 201:
        return {
            "authority_decisions": [
                {"authority_ref": overlay_rel, "status": "compatible", "rationale": "Overlay matches unrelated plan scope."},
                {"authority_ref": "ADR-0004", "status": "compatible", "rationale": "Contracts remain BCL-only."},
            ],
            "acceptance_links": [
                {
                    "acceptance_index": 1,
                    "requirement_ids": ["REQ-OTHER-1"],
                    "authority_refs": [overlay_rel],
                    "test_refs": ["Game.Core.Tests/Other/OtherTests.cs"],
                }
            ],
            "dependency_decisions": [],
            "overlap_decisions": [],
            "findings": [],
        }
    if task_id == 103:
        return {
            "authority_decisions": [
                {"authority_ref": overlay_rel, "status": "compatible", "rationale": "Overlay matches integration owner scope."},
                {"authority_ref": "ADR-0004", "status": "compatible", "rationale": "Contracts remain BCL-only."},
            ],
            "acceptance_links": [
                {
                    "acceptance_index": 1,
                    "requirement_ids": ["REQ-REWARD-1"],
                    "authority_refs": [overlay_rel, "ADR-0004"],
                    "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
                }
            ],
            "dependency_decisions": [
                {
                    "dependency_id": 101,
                    "action": "keep",
                    "relation": "producer_consumer",
                    "dependency_reason": "Producer supplies locked reward offer.",
                    "dependency_evidence": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"],
                },
                {
                    "dependency_id": 102,
                    "action": "keep",
                    "relation": "producer_consumer",
                    "dependency_reason": "Consumer handles reward choice return.",
                    "dependency_evidence": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"],
                },
            ],
            "overlap_decisions": [],
            "findings": [],
        }
    # Task 101 flow
    acc_links = [
        {
            "acceptance_index": 1,
            "requirement_ids": ["REQ-REWARD-1"],
            "authority_refs": [overlay_rel, "ADR-0004", "core.reward.offered"],
            "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
        }
    ]
    if include_planned:
        acc_links.append(
            {
                "acceptance_index": 2,
                "requirement_ids": ["REQ-REWARD-1"],
                "authority_refs": [overlay_rel, "ADR-0004", "core.reward.offered"],
                "test_refs": ["Game.Core.Tests/Reward/PlannedRewardEdgeTests.cs"],
            }
        )
    return {
        "authority_decisions": [
            {"authority_ref": overlay_rel, "status": "compatible", "rationale": "Overlay matches reward producer scope."},
            {"authority_ref": "ADR-0004", "status": "compatible", "rationale": "Contracts remain BCL-only."},
            {"authority_ref": "core.reward.offered", "status": "compatible", "rationale": "Event contract declared in EventTypes.cs."},
            {
                "authority_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                "status": "compatible",
                "rationale": "Production command contract matches Stage-4 binding.",
            },
        ],
        "acceptance_links": acc_links,
        "dependency_decisions": [],
        "overlap_decisions": [],
        "findings": [],
    }


def _reconcile_task_ready(root: Path, task_id: int, *, mode: str = "flow", include_planned: bool = True) -> dict:
    dec_rel = f"logs/ci/chapter5/decisions-task-{task_id}.json"
    _put_json(root, dec_rel, _decisions_for_task(mode=mode, task_id=task_id, include_planned=include_planned))
    res = ch5_b.reconcile_b_route_chapter5(
        root,
        task_id=task_id,
        decisions=dec_rel,
        write_artifacts=True,
    )
    assert res["ok"], f"Fixture Chapter 5 reconciliation failed for task {task_id}: {res}"
    return res


def _build_explicit_not_enabled_a_repo(root: Path) -> None:
    """Create a pure explicit_not_enabled_a repo with Accepted ADR-0040 AND static b-route schemas/**."""
    adr_src = REPO_ROOT / task_resolver.ADR_0040
    _put(root, task_resolver.ADR_0040, adr_src.read_bytes())
    # Include static committed schemas under docs/planning/b-route/schemas/** to verify exclusion!
    schemas_src = REPO_ROOT / "docs/planning/b-route/schemas"
    for schema_file in sorted(schemas_src.glob("*.json")):
        _put(root, f"docs/planning/b-route/schemas/{schema_file.name}", schema_file.read_bytes())
    _put(root, "Game.Core.Tests/LegacyATests.cs", "public class LegacyATests {}\n")
    _put_json(
        root,
        ".taskmaster/tasks/tasks.json",
        {
            "master": {
                "tasks": [
                    {
                        "id": 11,
                        "title": "Legacy A task",
                        "status": "in-progress",
                        "dependencies": [],
                        "details": "Legacy A implementation.",
                    }
                ]
            }
        },
    )
    _put_json(
        root,
        ".taskmaster/tasks/tasks_back.json",
        [
            {
                "id": "NG-0011",
                "taskmaster_id": 11,
                "title": "Legacy A task",
                "status": "in-progress",
                "depends_on": [],
                "acceptance": ["Legacy behavior works. Refs: Game.Core.Tests/LegacyATests.cs"],
                "test_refs": ["Game.Core.Tests/LegacyATests.cs"],
            }
        ],
    )
    _put_json(root, ".taskmaster/tasks/tasks_gameplay.json", [])


def _build_frozen_a_repo(root: Path) -> dict:
    """Create a repo with B governance + frozen A task 1 verified against genuine Story 1.5 policy.frozen_a_refs."""
    import importlib
    import chapter5_semantic_reconciliation as ch5
    import test_b_route_task_resolver as resolver_tests

    inv_mod = importlib.import_module("test_b_route_inventory")
    inv_fixture = inv_mod.InventoryTests(methodName="runTest")
    inv_fixture.setUp()
    try:
        inv_root = inv_fixture.root
        epics = inv_fixture.epics
        master = inv_fixture.load(task_resolver.TRIPLET["master"])
        frozen_ids = sorted(t["id"] for t in master["master"]["tasks"])
        frozen_tid = frozen_ids[0]

        # Capture a genuine Story 1.5 protection snapshot under logs/ci/...
        capture = protection.collect_protection(inv_root, epics)
        assert capture.snapshot["stable"], capture.snapshot["diagnostics"]
        snap_rel_dir = "logs/ci/2026-11-23/b-route-protection/frozen-baseline"
        snap_dir = inv_root / snap_rel_dir
        snap_dir.mkdir(parents=True, exist_ok=False)
        protection.write_capture(snap_dir, capture)
        snap_rel = f"{snap_rel_dir}/snapshot.json"
        snap_raw = (inv_root / snap_rel).read_bytes()

        # Lock frozen Task IDs via chapter3-task-scope.json.
        scope_doc = {
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": task_resolver.TRIPLET["master"],
            "expected_master_task_count": len(frozen_ids),
            "allowed_numeric_task_ids": frozen_ids,
        }
        builder = resolver_tests.ResolverRepoBuilder(inv_root)
        scope_raw = builder.put_json(task_resolver.CHAPTER3_TASK_SCOPE, scope_doc)

        # Add one B-route task & commit B governance bundle pinning frozen_a_refs.
        next_tid = max(frozen_ids) + 1
        master["master"]["tasks"].append(
            {"id": next_tid, "title": "New B Task", "status": "pending", "dependencies": []}
        )
        back = inv_fixture.load(task_resolver.TRIPLET["back"])
        back.append(
            {"id": f"NG-{next_tid:04d}", "taskmaster_id": next_tid, "title": "New B Task", "status": "pending"}
        )
        inv_fixture.dump(task_resolver.TRIPLET["master"], master)
        inv_fixture.dump(task_resolver.TRIPLET["back"], back)

        src = builder.write_sources_and_proof(use_log_proof=True)
        plan_path = "docs/planning/b-route/plans/plan-b/1.json"
        plan_doc = resolver_tests._build_plan_doc(
            plan_id="plan-b",
            revision=1,
            source_manifest_ref=src["manifest_ref"],
            source_ledger_ref=src["ledger_ref"],
            source_revision=src["source_revision"],
            source_manifest_digest=src["source_manifest_digest"],
            proof_ref=src["proof_ref"],
            requirements=[
                {
                    "requirement_id": "REQ-B-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "B task requirement.",
                    "non_task_sinks": [],
                }
            ],
            flows=[resolver_tests._make_flow("flow-b", ["REQ-B-1"])],
            commands=[],
            states=[],
            logical_references=[],
            requirement_verification=[
                {
                    "requirement_id": "REQ-B-1",
                    "disposition": "flow",
                    "flow_id": "flow-b",
                    "rationale": "B flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            requirement_route_memberships=[
                {"requirement_id": "REQ-B-1", "flow_id": "flow-b", "observable_role": "primary"}
            ],
            requirement_evidence=[],
            evidence_source_refs=[],
        )
        plan_raw = builder.put_json(plan_path, plan_doc)
        plan_ref = resolver_tests._typed_ref(plan_path, "newrouge.b-route-plan.v1", "plan-b", 1, plan_raw)

        binding_path = "docs/planning/b-route/bindings/plan-b/1.json"
        binding_doc = resolver_tests._build_binding_doc(
            plan_id="plan-b",
            binding_revision=1,
            plan_ref=plan_ref,
            stage="3C",
            task_mappings=[
                {
                    "task_id": next_tid,
                    "view_refs": [{"view": "back", "business_id": f"NG-{next_tid:04d}"}],
                    "requirement_ids": ["REQ-B-1"],
                    "flow_ids": ["flow-b"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": [],
                }
            ],
            obligations=[],
        )
        binding_raw = builder.put_json(binding_path, binding_doc)
        binding_ref = resolver_tests._typed_ref(binding_path, "newrouge.b-route-binding.v1", "plan-b", 1, binding_raw)

        frozen_a_refs = [
            resolver_tests._owned_ref("frozen_a_inventory", snap_rel, [(snap_rel, snap_raw)]),
            resolver_tests._owned_ref(
                "authority",
                task_resolver.CHAPTER3_TASK_SCOPE,
                [(task_resolver.CHAPTER3_TASK_SCOPE, scope_raw)],
            ),
        ]
        authority_pins = [
            (src["manifest_rel"], src["manifest_raw"]),
            (src["ledger_rel"], src["ledger_raw"]),
            (src["proof_rel"], src["proof_raw"]),
            (snap_rel, snap_raw),
        ]
        builder.commit_bundle(
            operation_id="op-frozen-a-001",
            plans=[(plan_path, plan_doc)],
            bindings=[(binding_path, binding_doc)],
            origins_tasks=[
                {
                    "task_id": next_tid,
                    "source_refs": [src["source_owned"]],
                    "plan_refs": [plan_ref],
                    "binding_refs": [binding_ref],
                }
            ],
            frozen_a_refs=frozen_a_refs,
            allowed_a_operations=["implement", "resume", "route"],
            a_write_allowed=True,
            authority_pins=authority_pins,
            scope_map={"scope-b": ([plan_path], [binding_path])},
        )

        # Create legacy A Chapter 5 readiness artifacts for frozen_tid so ch5.load_task_readiness succeeds.
        source_rel = "docs/source.md"
        src_text = (inv_root / source_rel).read_text(encoding="utf-8")
        src_sha = ch5._sha_text(src_text)
        raw_slice = src_text.rstrip()
        sm_path = inv_root / ch5.DEFAULT_SOURCE_MANIFEST
        sl_path = inv_root / ch5.DEFAULT_SOURCE_LEDGER
        sem_path = inv_root / ch5.DEFAULT_CH3_SEMANTICS
        sm_doc = {
            "schema_version": "chapter3.source-manifest.v1",
            "source_revision": "legacy-a-rev-1",
            "manifest_sha256": "sha256:" + src_sha,
            "block_count": 1,
            "sources": [
                {
                    "path": source_rel,
                    "sha256": "sha256:" + src_sha,
                    "source_type": "markdown",
                    "block_count": 1,
                }
            ],
        }
        _put_json(inv_root, ch5.DEFAULT_SOURCE_MANIFEST.as_posix(), sm_doc)
        sl_doc = {
            "schema_version": "newrouge.source-blocks.v1",
            "source_revision": "legacy-a-rev-1",
            "source_manifest_sha256": "sha256:" + src_sha,
            "blocks": [
                {
                    "block_id": "BLK-A-1",
                    "source_path": source_rel,
                    "line_start": 1,
                    "line_end": len(src_text.splitlines()),
                    "raw_text": raw_slice,
                    "content_hash": "sha256:" + ch5._sha_text(raw_slice),
                    "source_sha256": "sha256:" + src_sha,
                }
            ],
        }
        _put_json(inv_root, ch5.DEFAULT_SOURCE_LEDGER.as_posix(), sl_doc)
        _put_json(
            inv_root,
            ch5.DEFAULT_CH3_SEMANTICS.as_posix(),
            {"schema_version": "newrouge.semantic-requirements.v1", "source_revision": "legacy-a-rev-1", "requirements": []},
        )
        cache_key = ch5.build_cache_key(
            sm_path,
            sl_path,
            sm_doc,
            parser_revision=ch5.PARSER_REVISION,
            extractor_revision=ch5.EXTRACTOR_REVISION,
        )
        snap_id = "EXB-" + ch5._canonical_sha(cache_key)[:20].upper()
        snap_doc = {
            "schema_version": ch5.SNAPSHOT_SCHEMA,
            "status": "complete",
            "source_revision": "legacy-a-rev-1",
            "cache_key": cache_key,
            "extraction_b_snapshot_id": snap_id,
            "items": [],
        }
        _put_json(inv_root, ch5.DEFAULT_EXTRACTION_SNAPSHOT.as_posix(), snap_doc)

        task_rows = ch5._load_task_rows(inv_root)
        task_bundle = ch5._task_bundle(task_rows, str(frozen_tid))
        auth_scope, auth_errs = ch5.build_task_authority_scope(inv_root, task_bundle)
        assert not auth_errs, f"Frozen A authority scope errors: {auth_errs}"
        auth_rec: list[dict] = []
        fp = ch5.build_chapter5_input_fingerprint(
            inv_root,
            manifest_path=sm_path,
            ledger_path=sl_path,
            snapshot=snap_doc,
            semantics_path=sem_path,
            task=task_bundle,
            authority_scope=auth_scope,
            authority_reconciliation=auth_rec,
        )
        rec_doc = {
            "schema_version": ch5.RECONCILIATION_SCHEMA,
            "task_id": str(frozen_tid),
            "source_revision": "legacy-a-rev-1",
            "cache_key": cache_key,
            "extraction_b_snapshot_id": snap_id,
            "authority_scope": auth_scope,
            "authority_reconciliation": auth_rec,
            "input_fingerprint": fp,
            "summary": {"blocking": 0},
            "findings": [],
        }
        rec_rel = (ch5.DEFAULT_RECONCILIATION_DIR / f"task-{frozen_tid}.json").as_posix()
        _put_json(inv_root, rec_rel, rec_doc)
        rdy_doc = {
            "schema_version": ch5.READINESS_SCHEMA,
            "task_id": str(frozen_tid),
            "readiness": "READY",
            "closure_allowed": True,
            "source_revision": "legacy-a-rev-1",
            "cache_key": cache_key,
            "extraction_b_snapshot_id": snap_id,
            "reconciliation_sha256": "sha256:" + ch5._canonical_sha(rec_doc),
            "input_fingerprint": fp,
        }
        _put_json(inv_root, (ch5.DEFAULT_READINESS_DIR / f"task-{frozen_tid}.json").as_posix(), rdy_doc)

        shutil.copytree(inv_root, root)
        return {"task_id": frozen_tid, "snap_rel": snap_rel, "source_rel": source_rel}
    finally:
        inv_fixture.tearDown()


class Chapter6GateTests(unittest.TestCase):
    _cache_dir: tempfile.TemporaryDirectory
    _flow_base: Path
    _nonflow_base: Path
    _done_reverify_base: Path
    _frozen_a_base: Path
    _explicit_a_base: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls._cache_dir = tempfile.TemporaryDirectory(prefix="ch6-gate-base-")
        base = Path(cls._cache_dir.name)

        cls._flow_base = base / "flow"
        _build_b_route_base_repo(cls._flow_base, mode="flow")
        _reconcile_task_ready(cls._flow_base, 101, mode="flow")
        _reconcile_task_ready(cls._flow_base, 103, mode="flow")
        _reconcile_task_ready(cls._flow_base, 201, mode="flow")

        cls._nonflow_base = base / "nonflow"
        _build_b_route_base_repo(cls._nonflow_base, mode="nonflow", include_planned=False)
        _reconcile_task_ready(cls._nonflow_base, 101, mode="nonflow", include_planned=False)

        cls._done_reverify_base = base / "done_reverify"
        _build_b_route_base_repo(cls._done_reverify_base, mode="flow", task101_status="done", include_planned=True)
        _reconcile_task_ready(cls._done_reverify_base, 101, mode="flow", include_planned=True)

        cls._frozen_a_base = base / "frozen_a"
        cls._frozen_a_info = _build_frozen_a_repo(cls._frozen_a_base)

        cls._explicit_a_base = base / "explicit_a"
        _build_explicit_not_enabled_a_repo(cls._explicit_a_base)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cache_dir.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ch6-gate-test-")
        self.tmp_root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clone(self, src: Path, name: str = "repo") -> Path:
        dst = self.tmp_root / name
        shutil.copytree(src, dst)
        return dst

    def _assert_valid_diagnostics(self, res: dict) -> None:
        diags = res.get("diagnostics") or []
        self.assertTrue(diags, f"expected diagnostics in blocked result: {res}")
        for d in diags:
            self.assertEqual(set(d.keys()), DIAGNOSTIC_KEYS)
        self.assertIn(res.get("return_stage"), ("3A", "3B", "3C", "4", "5"))
        self.assertFalse(res.get("runtime_verified"))
        self.assertFalse(res.get("default_b_enabled"))

    # ------------------------------------------------------------------
    # 1. CLI_DIRECT
    # ------------------------------------------------------------------

    def test_cli_direct_valid_flow_nonflow_and_integration_owner_parity(self) -> None:
        flow_root = self._clone(self._flow_base, "flow")
        for tid in (101, 103):
            gate_res = ch6_gate.evaluate_chapter6_gate(flow_root, tid, consumer="test")
            self.assertTrue(gate_res["ok"], gate_res)
            self.assertEqual(gate_res["route"], "B")
            self.assertFalse(gate_res["self_done_required"])
            self.assertFalse(gate_res["runtime_verified"])
            self.assertFalse(gate_res["default_b_enabled"])
            self.assertFalse(gate_res["uses_global_writer_lock"])

            # CLI parity via check_b_route_chapter6_gate.main (zero write)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = ch6_gate_cli.main(["--root", str(flow_root), "--task-id", str(tid)])
            self.assertEqual(rc, 0)
            cli_payload = json.loads(buf.getvalue())
            self.assertTrue(cli_payload["ok"])
            self.assertEqual(cli_payload["route"], "B")
            self.assertEqual(cli_payload["input_set_digest"], gate_res["input_set_digest"])
            self.assertFalse(cli_payload["runtime_verified"])
            self.assertFalse(cli_payload["default_b_enabled"])

            # _mvg_obligations parity (NEVER returns legacy trace-less "current" on B!)
            obl_ok, obl_reason, obl_detail = mvg_obligations.check_task_obligations(flow_root, str(tid))
            self.assertTrue(obl_ok, obl_reason)
            self.assertEqual(obl_reason, "b_route_gate_current")
            self.assertEqual(obl_detail["route"], "B")
            self.assertFalse(obl_detail["runtime_verified"])

        # run_single_task_chapter6_lane --self-check parity + dev_cli builder --execution-plan-signal
        out_dir = flow_root / "logs/ci/ch6-self-check-101"
        with (
            patch.object(ch6_lane, "_repo_root", return_value=flow_root),
            patch.object(
                sys,
                "argv",
                [
                    "run_single_task_chapter6_lane.py",
                    "--task-id",
                    "101",
                    "--out-dir",
                    str(out_dir),
                    "--execution-plan-signal",
                    "workflow_control_plane",
                    "--self-check",
                ],
            ),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 0)
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["b_route_gate"]["route"], "B")
        self.assertFalse(summary["runtime_verified"])
        self.assertFalse(summary["default_b_enabled"])

        # dev_cli parser & builder forward --execution-plan-signal cleanly.
        parser = dev_cli.build_parser()
        parsed = parser.parse_args(
            [
                "run-single-task-chapter6",
                "--task-id",
                "101",
                "--execution-plan-signal",
                "sig-a",
                "--execution-plan-signal",
                "sig-b",
                "--self-check",
            ]
        )
        built_cmd = dev_cli_builders.build_run_single_task_chapter6_cmd(parsed)
        self.assertIn("--execution-plan-signal", built_cmd)
        self.assertEqual(built_cmd.count("--execution-plan-signal"), 2)

        # Valid zero-MVG-impact non-Flow Task 101
        nonflow_root = self._clone(self._nonflow_base, "nonflow")
        nf_gate = ch6_gate.evaluate_chapter6_gate(nonflow_root, 101, consumer="test")
        self.assertTrue(nf_gate["ok"], nf_gate)
        self.assertEqual(nf_gate["route"], "B")
        self.assertEqual(nf_gate["stage5_summary"]["mode"], "non_flow")
        self.assertFalse(nf_gate["runtime_verified"])
        obl_ok, obl_reason, _ = mvg_obligations.check_task_obligations(nonflow_root, "101")
        self.assertTrue(obl_ok, obl_reason)
        self.assertEqual(obl_reason, "b_route_gate_current")

    def test_cli_direct_old_done_surfaces_reverification(self) -> None:
        done_root = self._clone(self._done_reverify_base, "done_reverify")
        gate_res = ch6_gate.evaluate_chapter6_gate(done_root, 101, consumer="test")
        self.assertTrue(gate_res["ok"], gate_res)
        self.assertTrue(gate_res["requires_chapter6_reverification"])
        self.assertFalse(gate_res["old_done_covers_new_obligations"])
        self.assertFalse(gate_res["runtime_verified"])
        obl_ok, obl_reason, obl_detail = mvg_obligations.check_task_obligations(done_root, "101")
        self.assertTrue(obl_ok, obl_reason)
        self.assertTrue(obl_detail["b_route_gate"]["requires_chapter6_reverification"])

    def test_cli_direct_frozen_a_and_explicit_not_enabled_a_with_schemas(self) -> None:
        # Pure explicit_not_enabled_a repo WITH static docs/planning/b-route/schemas/*.json present!
        exp_root = self._clone(self._explicit_a_base, "explicit_a")
        presence = ch6_gate.detect_b_route_presence(exp_root, 11)
        self.assertFalse(presence["has_b_traces"])
        gate_res = ch6_gate.evaluate_chapter6_gate(exp_root, 11, consumer="test")
        self.assertTrue(gate_res["ok"], gate_res)
        self.assertEqual(gate_res["route"], "explicit_not_enabled_a")
        self.assertTrue(gate_res["legacy_a_passthrough"])
        self.assertFalse(gate_res["runtime_verified"])
        self.assertFalse(gate_res["default_b_enabled"])
        # Guarded execution must NOT pollute pure A repo with b-route-operations locks!
        with ch6_gate.guarded_chapter6_execution(exp_root, 11, consumer="test") as h:
            self.assertTrue(h.legacy_a_passthrough)
            h.revalidate_boundary("step-a")
        self.assertFalse((exp_root / op_scope.STORE).exists())

        # Frozen A task inside policy.frozen_a_refs succeeds; tampering blocks!
        fa_root = self._clone(self._frozen_a_base, "frozen_a")
        fa_tid = self._frozen_a_info["task_id"]
        fa_src = self._frozen_a_info["source_rel"]
        fa_res = ch6_gate.evaluate_chapter6_gate(fa_root, fa_tid, operation="implement", consumer="test")
        self.assertTrue(fa_res["ok"], fa_res)
        self.assertEqual(fa_res["route"], "A")
        self.assertFalse(fa_res["legacy_a_passthrough"])
        self.assertFalse(fa_res["runtime_verified"])
        # _mvg_obligations also passes cleanly on frozen A!
        fa_obl_ok, fa_obl_reason, fa_obl_detail = mvg_obligations.check_task_obligations(fa_root, str(fa_tid))
        self.assertTrue(fa_obl_ok, fa_obl_reason)
        self.assertEqual(fa_obl_reason, "current")
        self.assertEqual(fa_obl_detail["route"], "A")
        self.assertFalse(fa_obl_detail["runtime_verified"])
        # Tamper frozen A source doc -> must block before side effects!
        _put(fa_root, fa_src, "# Tampered Legacy A Source\n")
        fa_tampered = ch6_gate.evaluate_chapter6_gate(fa_root, fa_tid, operation="implement", consumer="test")
        self.assertFalse(fa_tampered["ok"])
        self._assert_valid_diagnostics(fa_tampered)

    # ------------------------------------------------------------------
    # 2. BYPASS_BLK
    # ------------------------------------------------------------------

    def test_bypass_blk_tamper_missing_deleted_na_and_non_ascii(self) -> None:
        # 2a. Non-ASCII superscript digit "¹" rejected unconditionally across entrypoints!
        flow_root = self._clone(self._flow_base, "non_ascii")
        bad_tid = "\u00b9"  # superscript 1: str.isdigit() is True in Python!
        self.assertTrue(bad_tid.isdigit())
        res_na_id = ch6_gate.evaluate_chapter6_gate(flow_root, bad_tid)
        self.assertFalse(res_na_id["ok"])
        self.assertEqual(res_na_id["reason_code"], codec.ReasonCode.INVALID_ARGUMENT.value)
        self._assert_valid_diagnostics(res_na_id)
        obl_ok, obl_reason, _ = mvg_obligations.check_task_obligations(flow_root, bad_tid)
        self.assertFalse(obl_ok)
        self.assertIn("invalid_argument", obl_reason)

        # 2b. Deleted MVG manifest -> blocks across gate, _mvg_obligations, and lane with identical code/stage!
        del_m_root = self._clone(self._flow_base, "del_manifest")
        (del_m_root / "docs/testing/mvg/reward-baseline.json").unlink()
        g_del = ch6_gate.evaluate_chapter6_gate(del_m_root, 101)
        self.assertFalse(g_del["ok"])
        self._assert_valid_diagnostics(g_del)
        self.assertEqual(g_del["return_stage"], "5")
        obl_ok, obl_reason, obl_detail = mvg_obligations.check_task_obligations(del_m_root, "101")
        self.assertFalse(obl_ok)
        self.assertEqual(obl_detail["reason_code"], g_del["reason_code"])
        self.assertEqual(obl_detail["return_stage"], g_del["return_stage"])

        # 2c. Deleted B governance file (policy.v1.json) -> NEVER falls back to legacy A!
        del_pol_root = self._clone(self._flow_base, "del_policy")
        (del_pol_root / records.BASE / "policy.v1.json").unlink()
        g_pol = ch6_gate.evaluate_chapter6_gate(del_pol_root, 101)
        self.assertFalse(g_pol["ok"])
        self.assertEqual(g_pol["route"], "blocked")
        self.assertEqual(g_pol["reason_code"], codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value)
        self._assert_valid_diagnostics(g_pol)
        obl_ok, _, obl_detail = mvg_obligations.check_task_obligations(del_pol_root, "101")
        self.assertFalse(obl_ok)
        self.assertEqual(obl_detail["reason_code"], g_pol["reason_code"])

        # 2d. Freeform mvg:N/A label added to Task -> blocks with return_stage="5"!
        na_root = self._clone(self._flow_base, "na_label")
        back = json.loads((na_root / ".taskmaster/tasks/tasks_back.json").read_text(encoding="utf-8"))
        back[0]["labels"] = ["mvg:N/A"]
        _put_json(na_root, ".taskmaster/tasks/tasks_back.json", back)
        g_na = ch6_gate.evaluate_chapter6_gate(na_root, 101)
        self.assertFalse(g_na["ok"])
        self._assert_valid_diagnostics(g_na)

        # 2e. Source drift -> return_stage="3A"
        src_root = self._clone(self._flow_base, "src_drift")
        _put(src_root, "sources/reward-gdd.md", "# Drifted GDD content\n")
        g_src = ch6_gate.evaluate_chapter6_gate(src_root, 101)
        self.assertFalse(g_src["ok"])
        self.assertEqual(g_src["return_stage"], "3A")
        self._assert_valid_diagnostics(g_src)

        # 2f. Deleted readiness -> return_stage="5"
        rdy_root = self._clone(self._flow_base, "del_readiness")
        (rdy_root / "logs/ci/chapter5/readiness/task-101.json").unlink()
        g_rdy = ch6_gate.evaluate_chapter6_gate(rdy_root, 101)
        self.assertFalse(g_rdy["ok"])
        self.assertEqual(g_rdy["return_stage"], "5")
        self._assert_valid_diagnostics(g_rdy)

    def test_bypass_blk_all_internal_scripts_block_before_model_or_write(self) -> None:
        blocked_root = self._clone(self._flow_base, "blocked_scripts")
        (blocked_root / "docs/testing/mvg/reward-baseline.json").unlink()
        expected_gate = ch6_gate.evaluate_chapter6_gate(blocked_root, 101)
        self.assertFalse(expected_gate["ok"])
        exp_code = expected_gate["reason_code"]
        exp_stage = expected_gate["return_stage"]

        # 1. check_tdd_execution_plan.py
        import check_tdd_execution_plan as c_tdd_plan

        buf = io.StringIO()
        with (
            patch.object(c_tdd_plan, "repo_root", return_value=blocked_root),
            patch.object(c_tdd_plan, "resolve_triplet", side_effect=AssertionError("must block before resolve_triplet")),
            patch.object(sys, "argv", ["check_tdd_execution_plan.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = c_tdd_plan.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 2. llm_generate_tests_from_acceptance_refs.py
        import llm_generate_tests_from_acceptance_refs as gen_tests

        buf = io.StringIO()
        with (
            patch.object(gen_tests, "repo_root", return_value=blocked_root),
            patch.object(gen_tests, "_run_codex_exec", side_effect=AssertionError("must block before LLM")),
            patch.object(gen_tests, "run_cmd", side_effect=AssertionError("must block before subprocess")),
            patch.object(sys, "argv", ["llm_generate_tests_from_acceptance_refs.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = gen_tests.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 3. scripts/sc/build/tdd.py
        import importlib.util

        tdd_spec = importlib.util.spec_from_file_location("sc_build_tdd_under_test", SCRIPTS_SC / "build/tdd.py")
        tdd_mod = importlib.util.module_from_spec(tdd_spec)
        tdd_spec.loader.exec_module(tdd_mod)
        buf = io.StringIO()
        with (
            patch.object(tdd_mod, "repo_root", return_value=blocked_root),
            patch.object(tdd_mod, "ensure_red_test_exists", side_effect=AssertionError("must block before file write")),
            patch.object(tdd_mod, "run_dotnet_test_filtered", side_effect=AssertionError("must block before test")),
            patch.object(sys, "argv", ["tdd.py", "--stage", "red", "--task-id", "101", "--generate-red-test"]),
            patch("sys.stdout", buf),
        ):
            rc = tdd_mod.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 4. scripts/sc/run_review_pipeline.py
        import run_review_pipeline as rev_pipe

        buf = io.StringIO()
        with (
            patch.object(rev_pipe, "repo_root", return_value=blocked_root),
            patch.object(rev_pipe, "_run_step", side_effect=AssertionError("must block before steps")),
            patch.object(sys, "argv", ["run_review_pipeline.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = rev_pipe.main()
        self.assertEqual(rc, 12)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 5. scripts/sc/llm_review_needs_fix_fast.py
        import llm_review_needs_fix_fast as nf_fast

        buf = io.StringIO()
        with (
            patch.object(nf_fast, "repo_root", return_value=blocked_root),
            patch.object(nf_fast, "run_step", side_effect=AssertionError("must block before steps")),
            patch.object(sys, "argv", ["llm_review_needs_fix_fast.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = nf_fast.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 6. scripts/sc/_llm_review_engine.py
        import _llm_review_engine as llm_eng

        buf = io.StringIO()
        with (
            patch.object(llm_eng, "repo_root", return_value=blocked_root),
            patch.object(llm_eng, "run_codex_exec", side_effect=AssertionError("must block before LLM")),
            patch.object(sys, "argv", ["llm_review.py", "--task-id", "101", "--uncommitted"]),
            patch("sys.stdout", buf),
        ):
            rc = llm_eng.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 7. scripts/sc/acceptance_check.py (must NOT call git checkout on B-route repo AND must block!)
        import acceptance_check as acc_chk

        buf = io.StringIO()
        with (
            patch.object(acc_chk, "repo_root", return_value=blocked_root),
            patch.object(acc_chk.subprocess, "run", side_effect=AssertionError("must NEVER run git checkout on B repo")),
            patch.object(acc_chk, "run_registry_steps", side_effect=AssertionError("must block before steps")),
            patch.object(sys, "argv", ["acceptance_check.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = acc_chk.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 8. scripts/sc/test.py
        import importlib.util as _iu

        sc_test_spec = _iu.spec_from_file_location("sc_test_under_test", SCRIPTS_SC / "test.py")
        sc_test_mod = _iu.module_from_spec(sc_test_spec)
        sc_test_spec.loader.exec_module(sc_test_mod)
        buf = io.StringIO()
        with (
            patch.object(sc_test_mod, "repo_root", return_value=blocked_root),
            patch.object(sc_test_mod, "run_unit", side_effect=AssertionError("must block before unit tests")),
            patch.object(sys, "argv", ["test.py", "--type", "unit", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            rc = sc_test_mod.main()
        self.assertEqual(rc, 2)
        self.assertIn(f"reason_code={exp_code}", buf.getvalue())
        self.assertIn(f"return_stage={exp_stage}", buf.getvalue())

        # 9. update_task_test_refs_from_acceptance_refs.py: unchanged -> zero write; changed on B -> blocks CONFLICT/3C!
        flow_ok_root = self._clone(self._flow_base, "test_refs_guard")
        back_path = flow_ok_root / ".taskmaster/tasks/tasks_back.json"
        back_data = json.loads(back_path.read_text(encoding="utf-8"))
        # First set test_refs to already match acceptance Refs -> zero write!
        back_data[0]["test_refs"] = [
            "Game.Core.Tests/Reward/RewardFlowTests.cs",
            "Game.Core.Tests/Reward/PlannedRewardEdgeTests.cs",
        ]
        _put_json(flow_ok_root, ".taskmaster/tasks/tasks_back.json", back_data)
        before_bytes = back_path.read_bytes()
        with (
            patch.object(test_refs_sync, "repo_root", return_value=flow_ok_root),
            patch.object(test_refs_sync, "write_json", side_effect=AssertionError("unchanged must perform zero disk writes")),
            patch.object(sys, "argv", ["update_task_test_refs_from_acceptance_refs.py", "--task-id", "101", "--write"]),
        ):
            rc = test_refs_sync.main()
        self.assertEqual(rc, 0)
        self.assertEqual(back_path.read_bytes(), before_bytes)

        # Now test changed=True on B task -> blocks with CONFLICT, return_stage="3C" before writing!
        back_data[0]["test_refs"] = []
        _put_json(flow_ok_root, ".taskmaster/tasks/tasks_back.json", back_data)
        before_empty_bytes = back_path.read_bytes()
        buf = io.StringIO()
        with (
            patch.object(test_refs_sync, "repo_root", return_value=flow_ok_root),
            patch.object(sys, "argv", ["update_task_test_refs_from_acceptance_refs.py", "--task-id", "101", "--write"]),
            patch("sys.stdout", buf),
        ):
            rc = test_refs_sync.main()
        self.assertEqual(rc, 2)
        self.assertIn("reason_code=conflict", buf.getvalue())
        self.assertIn("return_stage=3C", buf.getvalue())
        self.assertEqual(back_path.read_bytes(), before_empty_bytes)

        # 10. run_single_task_light_lane.py blocks legacy 5.1 light lane on B-route AND B-blocked Tasks!
        for target_root in (flow_ok_root, blocked_root):
            buf = io.StringIO()
            with (
                patch.object(light_lane, "_repo_root", return_value=target_root),
                patch.object(light_lane, "_run_step", side_effect=AssertionError("must block before light lane steps")),
                patch.object(sys, "argv", ["run_single_task_light_lane.py", "--task-ids", "101"]),
                patch("sys.stdout", buf),
            ):
                rc = light_lane.main()
            self.assertEqual(rc, 2)
            self.assertIn("BLOCKED legacy 5.1 light lane", buf.getvalue())

        # 11. dev_cli.py run-acceptance-preflight, chapter6-knowledge, publish-chapter6-semantics block on B-blocked!
        for cli_argv in (
            ["run-acceptance-preflight", "--task-id", "101"],
            ["chapter6-knowledge", "--repo-root", str(blocked_root), "--task-id", "101"],
            [
                "publish-chapter6-semantics",
                "--repo-root",
                str(blocked_root),
                "--task-id",
                "101",
                "--candidate-sha256",
                "a" * 64,
                "--reviewed-by",
                "rev",
                "--review-note",
                "note",
            ],
        ):
            buf = io.StringIO()
            prev_cwd = os.getcwd()
            try:
                os.chdir(blocked_root)
                with (
                    patch.object(dev_cli, "REPO_ROOT", blocked_root),
                    patch.object(dev_cli, "run", side_effect=AssertionError("must block before subprocess")),
                    patch("sys.stdout", buf),
                ):
                    rc = dev_cli.main(cli_argv)
            finally:
                os.chdir(prev_cwd)
            self.assertEqual(rc, 2)
            self.assertIn(exp_code, buf.getvalue())

    # ------------------------------------------------------------------
    # 3. SCOPE_LOCK
    # ------------------------------------------------------------------

    def test_scope_lock_no_global_writer_concurrent_unrelated_and_verified_child_reentrancy(self) -> None:
        flow_root = self._clone(self._flow_base, "scope_lock")
        writer_dir = flow_root / op_scope.STORE / "locks" / "scopes" / op_scope._hash(op_scope.WRITER_SCOPE)
        writer_dir.mkdir(parents=True, exist_ok=True)

        with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="parent") as parent_handle:
            self.assertFalse(parent_handle.uses_global_writer_lock)
            self.assertFalse(parent_handle.inherited_lease)
            self.assertIsNotNone(parent_handle.lease_receipt_path)

            # 1. writer:planning MUST NOT be held!
            with coordinator_lock(writer_dir):
                pass

            # 2. Unrelated Task 201 (plan-other) MUST acquire its own business-scope lease concurrently!
            # Clear env lease vars temporarily to simulate an independent sibling process on Task 201.
            saved_p = os.environ.pop(ch6_gate.ENV_LEASE_PATH, None)
            saved_s = os.environ.pop(ch6_gate.ENV_LEASE_SECRET, None)
            try:
                with ch6_gate.guarded_chapter6_execution(flow_root, 201, consumer="sibling") as sibling_handle:
                    self.assertFalse(sibling_handle.uses_global_writer_lock)
                    self.assertEqual(sibling_handle.task_id, 201)
                    sibling_handle.revalidate_boundary("sibling_step")
            finally:
                if saved_p is not None:
                    os.environ[ch6_gate.ENV_LEASE_PATH] = saved_p
                if saved_s is not None:
                    os.environ[ch6_gate.ENV_LEASE_SECRET] = saved_s

            # 3. Real child subprocess inherits verified parent lease WITHOUT Windows msvcrt self-deadlock!
            child_code = (
                "import json, sys\n"
                "import _b_route_chapter6_gate as g\n"
                f"root = {str(flow_root)!r}\n"
                "with g.guarded_chapter6_execution(root, 101, consumer='child_subproc') as h:\n"
                "    res = h.revalidate_boundary('child_step')\n"
                "    print(json.dumps({'ok': res['ok'], 'inherited': h.inherited_lease, 'global': h.uses_global_writer_lock}))\n"
            )
            child_env = {**os.environ, "PYTHONPATH": str(SCRIPTS_PY), "PYTHONDONTWRITEBYTECODE": "1"}
            proc = subprocess.run(
                [sys.executable, "-B", "-c", child_code],
                cwd=str(flow_root),
                env=child_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, f"child failed: stdout={proc.stdout} stderr={proc.stderr}")
            child_payload = json.loads(proc.stdout.strip())
            self.assertTrue(child_payload["ok"])
            self.assertTrue(child_payload["inherited"])
            self.assertFalse(child_payload["global"])

        # After parent exits, receipt file is cleaned up and env vars restored!
        self.assertIsNone(os.environ.get(ch6_gate.ENV_LEASE_PATH))
        self.assertIsNone(os.environ.get(ch6_gate.ENV_LEASE_SECRET))
        lease_dir = flow_root / ch6_gate.LEASE_DIR
        if lease_dir.is_dir():
            self.assertEqual(list(lease_dir.glob("*.json")), [])

    def test_scope_lock_rejects_spoofed_env_and_unlocked_receipt(self) -> None:
        flow_root = self._clone(self._flow_base, "spoof")
        live_iset = input_set.resolve_input_set(flow_root, 101)
        # Create lock dirs WITHOUT holding the OS lock!
        for sid in live_iset["scope_ids"]:
            sdir = flow_root / op_scope.STORE / "locks" / "scopes" / op_scope._hash(sid)
            sdir.mkdir(parents=True, exist_ok=True)
        forged_secret = "f" * 64
        forged_rel = f"{ch6_gate.LEASE_DIR}/task-101-forged.json"
        _put_json(
            flow_root,
            forged_rel,
            {
                "schema_version": ch6_gate.LEASE_RECEIPT_SCHEMA,
                "lease_id": "forged",
                "owner_pid": os.getpid(),
                "root_resolved": str(flow_root.resolve()),
                "task_id": 101,
                "route": "B",
                "scope_ids": list(live_iset["scope_ids"]),
                "input_set_digest": live_iset["input_set_digest"],
                "applicable_set_digest": live_iset.get("applicable_set_digest"),
                "secret_sha256": hashlib.sha256(forged_secret.encode("utf-8")).hexdigest(),
                "runtime_verified": False,
                "default_b_enabled": False,
            },
        )
        # Case 1: Unlocked OS byte lock -> rejected fail-closed!
        with patch.dict(
            os.environ,
            {ch6_gate.ENV_LEASE_PATH: forged_rel, ch6_gate.ENV_LEASE_SECRET: forged_secret},
        ):
            with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx:
                with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="spoof_test"):
                    pass
            self.assertEqual(ctx.exception.gate_result["reason_code"], codec.ReasonCode.CONFLICT.value)

        # Case 2: Wrong secret while OS lock IS held -> rejected fail-closed!
        with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="real_parent") as parent_h:
            with patch.dict(
                os.environ,
                {
                    ch6_gate.ENV_LEASE_PATH: str(parent_h.lease_receipt_path),
                    ch6_gate.ENV_LEASE_SECRET: "wrong-secret",
                },
            ):
                with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx:
                    with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="spoof_secret"):
                        pass
                self.assertEqual(ctx.exception.gate_result["reason_code"], codec.ReasonCode.CONFLICT.value)

        # Case 3: Path traversal outside logs/ci/b-route-chapter6-leases/ -> rejected UNSAFE_PATH!
        with patch.dict(
            os.environ,
            {ch6_gate.ENV_LEASE_PATH: "../outside.json", ch6_gate.ENV_LEASE_SECRET: forged_secret},
        ):
            with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx:
                with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="spoof_path"):
                    pass
            self.assertEqual(ctx.exception.gate_result["reason_code"], codec.ReasonCode.UNSAFE_PATH.value)

    def test_scope_lock_mid_run_drift_and_pending_stop_before_side_effects(self) -> None:
        # Case 1: Mid-run overlay edit -> revalidate_boundary stops with INPUT_STALE & return_stage="4"
        drift_root = self._clone(self._flow_base, "mid_drift")
        out_dir = drift_root / "logs/ci/mid-drift-events"
        with ch6_gate.guarded_chapter6_execution(drift_root, 101, consumer="lane", out_dir=out_dir) as handle:
            _put(
                drift_root,
                "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "---\nPRD-ID: PRD-NEWROUGE-GAME-0001\nTitle: Reward\nStatus: Draft\nADRs: [ADR-0004]\n---\n\n# Reward Overlay Drifted\nRefers to ADR-0004.\n",
            )
            with self.assertRaises(ch6_gate.Chapter6GateBlockedError) as ctx:
                handle.revalidate_boundary("before_red_first", model_invocation=True)
            self.assertEqual(ctx.exception.gate_result["reason_code"], codec.ReasonCode.INPUT_STALE.value)
            self.assertEqual(ctx.exception.gate_result["return_stage"], "4")
        events_file = out_dir / "chapter6-gate-events.jsonl"
        self.assertTrue(events_file.is_file())
        ev_rows = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(row["event_kind"] == "boundary_drift_stopped" for row in ev_rows))

        # Case 2: Mid-run new capability-apply.pending.json stops run_single_task_chapter6_lane BEFORE step runs!
        pend_root = self._clone(self._flow_base, "mid_pending")
        pend_out = pend_root / "logs/ci/ch6-mid-pending"
        calls: list[str] = []

        def _fake_json_step(*_args, name, cmd):
            if name == "chapter6-route-initial":
                # Inject pending marker right after initial route, BEFORE check-tdd-plan runs!
                _put_json(pend_root, op_scope.CAP_PENDING, {"run_id": "cap-run-1", "journal_path": "logs/ci/capability-planning/cap-run-1/apply-journal.json"})
            return {"name": name, "rc": 0, "cmd": cmd}, ({} if name == "resume-task" else ch6_lane._fresh_start_route_payload())

        def _fake_plain_step(*_args, name, cmd):
            calls.append(name)
            return {"name": name, "rc": 0, "cmd": cmd}

        with (
            patch.object(ch6_lane, "_repo_root", return_value=pend_root),
            patch.object(ch6_lane, "_run_json_step", side_effect=_fake_json_step),
            patch.object(ch6_lane, "_run_plain_step", side_effect=_fake_plain_step),
            patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--out-dir", str(pend_out)]),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])  # Zero side-effect steps executed!
        summary = json.loads((pend_out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["blocked_by"], "b_route_chapter6_gate")
        self.assertFalse(summary["runtime_verified"])
        self.assertFalse(summary["default_b_enabled"])

    def test_protected_status_write_preserves_projection_and_input_set_digest(self) -> None:
        flow_root = self._clone(self._flow_base, "status_write")
        before_iset = input_set.resolve_input_set(flow_root, 101)
        self.assertTrue(before_iset["ok"])

        res = ch6_gate.write_taskmaster_status_guarded(flow_root, 101, "done", sync_views=False)
        self.assertTrue(res["ok"])
        self.assertEqual(res["from_status"], "in-progress")
        self.assertEqual(res["to_status"], "done")
        self.assertTrue(res["definition_projection_preserved"])
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])

        # InputSet digest MUST remain 100% invariant when only status changes!
        after_iset = input_set.resolve_input_set(flow_root, 101)
        self.assertTrue(after_iset["ok"])
        self.assertEqual(after_iset["input_set_digest"], before_iset["input_set_digest"])

        # apply_chapter7_status_patch routes non-dry-run B-route updates through write_taskmaster_status_guarded!
        patch_path = flow_root / "logs/ci/ch7-patch.json"
        _put_json(
            flow_root,
            "logs/ci/ch7-patch.json",
            {
                "operations": [
                    {
                        "path": str(flow_root / ".taskmaster/tasks/tasks.json"),
                        "view": "tasks_json",
                        "task_id": 101,
                        "from_status": "done",
                        "to_status": "in-progress",
                    }
                ]
            },
        )
        rc, patch_res = ch7_patch.apply_patch_contract(patch_path=patch_path, dry_run=False)
        self.assertEqual(rc, 0)
        self.assertTrue(patch_res["results"][0]["guarded_write"])
        self.assertTrue(patch_res["results"][0]["definition_projection_preserved"])
        after_patch_iset = input_set.resolve_input_set(flow_root, 101)
        self.assertEqual(after_patch_iset["input_set_digest"], before_iset["input_set_digest"])

    # ------------------------------------------------------------------
    # 4. LOCAL_QUAL
    # ------------------------------------------------------------------

    def test_local_qual_p1_floor_no_full_mvg_no_false_green_and_runtime_verified_false(self) -> None:
        flow_root = self._clone(self._flow_base, "local_qual")
        out_p0 = flow_root / "logs/ci/ch6-p0"
        with (
            patch.object(ch6_lane, "_repo_root", return_value=flow_root),
            patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--fix-through", "P0", "--out-dir", str(out_p0)]),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 2)
        p0_summary = json.loads((out_p0 / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(p0_summary["stop_reason"], "invalid_fix_through")
        self.assertFalse(p0_summary["runtime_verified"])

        # Mocked full local Chapter 6 run (TDD + review + needs-fix-fast + local-hard-checks)
        out_run = flow_root / "logs/ci/ch6-local-run"
        recorded_cmds: list[tuple[str, list[str]]] = []

        def _fake_json_step(*_args, name, cmd):
            recorded_cmds.append((name, list(cmd)))
            if name == "resume-task":
                return {"name": name, "rc": 0, "cmd": cmd}, {}
            if name == "chapter6-route-initial":
                return {"name": name, "rc": 0, "cmd": cmd}, ch6_lane._fresh_start_route_payload()
            if name == "chapter6-route-post-review":
                return {"name": name, "rc": 0, "cmd": cmd}, {"preferred_lane": "run-6.8", "chapter6_next_action": "needs-fix-fast"}
            if name == "chapter6-route-post-needs-fix":
                return {"name": name, "rc": 0, "cmd": cmd}, {"preferred_lane": "continue", "chapter6_next_action": "continue"}
            return {"name": name, "rc": 0, "cmd": cmd}, {"status": "ok"}

        def _fake_plain_step(*_args, name, cmd):
            recorded_cmds.append((name, list(cmd)))
            return {"name": name, "rc": 0, "cmd": cmd}

        with (
            patch.object(ch6_lane, "_repo_root", return_value=flow_root),
            patch.object(ch6_lane, "_run_json_step", side_effect=_fake_json_step),
            patch.object(ch6_lane, "_run_plain_step", side_effect=_fake_plain_step),
            patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--out-dir", str(out_run)]),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 0)
        summary = json.loads((out_run / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertFalse(summary["runtime_verified"])
        self.assertFalse(summary["default_b_enabled"])

        # Must NEVER invoke full MVG or implicit global Knowledge refresh!
        all_cmd_strings = [" ".join(c) for _, c in recorded_cmds]
        self.assertFalse(any("run_mvg_acceptance" in s or "run-mvg-acceptance" in s for s in all_cmd_strings))
        self.assertFalse(any("refresh-knowledge" in s or "refresh_chapter_knowledge" in s or "project-health-scan" in s for s in all_cmd_strings))
        lh_cmds = [c for name, c in recorded_cmds if name == "local-hard-checks"]
        self.assertEqual(len(lh_cmds), 1)
        self.assertIn("--skip-project-health", lh_cmds[0])

        # Verify rework & execution events persisted in chapter6-gate-events.jsonl!
        ev_rows = [json.loads(line) for line in (out_run / "chapter6-gate-events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        kinds = {r["event_kind"] for r in ev_rows}
        self.assertIn("execution", kinds)
        self.assertIn("rework", kinds)
        for row in ev_rows:
            self.assertFalse(row["runtime_verified"])
            self.assertFalse(row["default_b_enabled"])

        # Verify build/tdd rejects planned / empty / skipped false-green reports!
        import importlib.util

        tdd_spec = importlib.util.spec_from_file_location("sc_build_tdd_fg", SCRIPTS_SC / "build/tdd.py")
        tdd_mod = importlib.util.module_from_spec(tdd_spec)
        tdd_spec.loader.exec_module(tdd_mod)
        self.assertTrue(tdd_mod._is_false_green_step({}))
        self.assertTrue(tdd_mod._is_false_green_step({"status": "planned", "rc": 0}))
        self.assertTrue(tdd_mod._is_false_green_step({"status": "skipped", "rc": 0}))
        self.assertTrue(tdd_mod._is_false_green_step({"status": "ok", "reason": "planned-only", "rc": 0}))
        self.assertFalse(tdd_mod._is_false_green_step({"status": "ok", "rc": 0}))

    # ------------------------------------------------------------------
    # 5. STOPLOSS
    # ------------------------------------------------------------------

    def test_stoploss_preserves_rerun_guard_budget_history_and_zero_knowledge_refresh(self) -> None:
        flow_root = self._clone(self._flow_base, "stoploss")
        # Plant existing durable marathon-state.json / budget history artifact!
        marathon_rel = "logs/ci/2026-11-24/sc-review-pipeline-task-101-run1/marathon-state.json"
        marathon_payload = {
            "task_id": "101",
            "run_id": "run1",
            "resume_count": 3,
            "diagnostics": {
                "rerun_guard": {"kind": "repeat_deterministic_failure", "blocked": True},
                "llm_retry_stop_loss": {"triggered": True},
                "sc_test_retry_stop_loss": {"triggered": True},
                "waste_signals": {"count": 2},
            },
        }
        marathon_bytes = _put_json(flow_root, marathon_rel, marathon_payload)

        # Case 1: Stop-loss route (rerun_guard) blocks blind 6.7 rerun AND preserves marathon history!
        out_sl = flow_root / "logs/ci/ch6-stoploss"
        sl_route = {
            "preferred_lane": "fix-deterministic",
            "run_id": "run1",
            "latest_reason": "rerun_blocked:repeat_deterministic_failure",
            "blocked_by": "rerun_guard",
            "chapter6_next_action": "fix-and-resume",
            "forbidden_commands": [],
        }

        def _fake_sl_json(*_args, name, cmd):
            return {"name": name, "rc": 0, "cmd": cmd}, ({} if name == "resume-task" else sl_route)

        with (
            patch.object(ch6_lane, "_repo_root", return_value=flow_root),
            patch.object(ch6_lane, "_run_json_step", side_effect=_fake_sl_json),
            patch.object(ch6_lane, "_run_plain_step", side_effect=AssertionError("rerun_guard must block blind 6.7")),
            patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--out-dir", str(out_sl)]),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 1)
        self.assertEqual((flow_root / marathon_rel).read_bytes(), marathon_bytes)

        # Case 2: Upstream definition gap (source drift -> return_stage="3A") blocks cleanly while preserving history!
        _put(flow_root, "sources/reward-gdd.md", "# Upstream definition gap\n")
        out_gap = flow_root / "logs/ci/ch6-def-gap"
        with (
            patch.object(ch6_lane, "_repo_root", return_value=flow_root),
            patch.object(sys, "argv", ["run_single_task_chapter6_lane.py", "--task-id", "101", "--out-dir", str(out_gap)]),
        ):
            rc = ch6_lane.main()
        self.assertEqual(rc, 2)
        gap_summary = json.loads((out_gap / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(gap_summary["status"], "blocked")
        self.assertEqual(gap_summary["return_stage"], "3A")
        self.assertFalse(gap_summary["runtime_verified"])
        self.assertFalse(gap_summary["default_b_enabled"])
        # Durable marathon/budget history untouched!
        self.assertEqual((flow_root / marathon_rel).read_bytes(), marathon_bytes)
        # Blocked gate event recorded!
        ev_rows = [json.loads(line) for line in (out_gap / "chapter6-gate-events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(r["event_kind"] == "blocked_gate" and r["return_stage"] == "3A" for r in ev_rows))
        # Zero Knowledge refresh artifacts created!
        self.assertFalse((flow_root / "logs/ci/project-health").exists())

    def test_cli_zero_write_and_report_output(self) -> None:
        flow_root = self._clone(self._flow_base, "cli_report")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = ch6_gate_cli.main(
                [
                    "--root",
                    str(flow_root),
                    "--task-id",
                    "101",
                    "--report",
                    "logs/ci/ch6-gate-report.json",
                ]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["report_path"], "logs/ci/ch6-gate-report.json")
        self.assertTrue((flow_root / "logs/ci/ch6-gate-report.json").is_file())
        self.assertFalse(payload["runtime_verified"])
        self.assertFalse(payload["default_b_enabled"])

    # ------------------------------------------------------------------
    # 6. Step 4 Patch Hardening (P-01 .. P-07)
    # ------------------------------------------------------------------

    def test_p01_status_write_reentrancy_target_views_and_patch_fault_tolerance(self) -> None:
        flow_root = self._clone(self._flow_base, "p01_reentry")
        gp_path = flow_root / ".taskmaster/tasks/tasks_gameplay.json"
        gp_before = gp_path.read_bytes()
        before_iset = input_set.resolve_input_set(flow_root, 101)
        self.assertTrue(before_iset["ok"])

        # Same-process AND child-process reentrancy inside guarded_chapter6_execution without msvcrt self-deadlock.
        with ch6_gate.guarded_chapter6_execution(flow_root, 101, consumer="p01_parent"):
            res = ch6_gate.write_taskmaster_status_guarded(
                flow_root,
                101,
                "done",
                sync_views=True,
                target_views=("back",),
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["target_views"], ["back"])
            self.assertEqual(gp_path.read_bytes(), gp_before)
            back_rows = json.loads((flow_root / ".taskmaster/tasks/tasks_back.json").read_text(encoding="utf-8"))
            self.assertEqual(next(r["status"] for r in back_rows if r["taskmaster_id"] == 101), "done")

            child_code = (
                "import json\n"
                "import _b_route_chapter6_gate as g\n"
                f"res = g.write_taskmaster_status_guarded({str(flow_root)!r}, 101, 'in-progress', sync_views=False)\n"
                "print(json.dumps(res))\n"
            )
            child_env = {**os.environ, "PYTHONPATH": str(SCRIPTS_PY), "PYTHONDONTWRITEBYTECODE": "1"}
            proc = subprocess.run(
                [sys.executable, "-B", "-c", child_code],
                cwd=str(flow_root),
                env=child_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, f"child status write failed: {proc.stdout} {proc.stderr}")
            child_res = json.loads(proc.stdout.strip())
            self.assertTrue(child_res["ok"])
            self.assertEqual(child_res["to_status"], "in-progress")

        after_iset = input_set.resolve_input_set(flow_root, 101)
        self.assertEqual(after_iset["input_set_digest"], before_iset["input_set_digest"])

        # Plant task 101 in tasks_gameplay.json and prove view=tasks_back syncs ONLY tasks.json + tasks_back.json!
        _put_json(
            flow_root,
            ".taskmaster/tasks/tasks_gameplay.json",
            [{"id": "GM-0101", "taskmaster_id": 101, "title": "Reward producer task", "status": "in-progress"}],
        )
        gp_planted_before = gp_path.read_bytes()
        patch_back = flow_root / "logs/ci/p01-patch-back.json"
        _put_json(
            flow_root,
            "logs/ci/p01-patch-back.json",
            {
                "operations": [
                    {
                        "path": str(flow_root / ".taskmaster/tasks/tasks_back.json"),
                        "view": "tasks_back",
                        "task_id": 101,
                        "from_status": "in-progress",
                        "to_status": "done",
                    }
                ]
            },
        )
        rc, res_back = ch7_patch.apply_patch_contract(patch_path=patch_back, dry_run=False)
        self.assertEqual(rc, 0, res_back)
        self.assertEqual(gp_path.read_bytes(), gp_planted_before)

        # Invalid status ("review" not in MASTER_STATES) and non-int task_id return structured errors (no crash!).
        patch_bad = flow_root / "logs/ci/p01-patch-bad.json"
        _put_json(
            flow_root,
            "logs/ci/p01-patch-bad.json",
            {
                "operations": [
                    {
                        "path": str(flow_root / ".taskmaster/tasks/tasks.json"),
                        "view": "tasks_json",
                        "task_id": 101,
                        "from_status": "done",
                        "to_status": "review",
                    },
                    {
                        "path": str(flow_root / ".taskmaster/tasks/tasks.json"),
                        "view": "tasks_json",
                        "task_id": "not-a-number",
                        "from_status": "done",
                        "to_status": "in-progress",
                    },
                ]
            },
        )
        rc_bad, res_bad = ch7_patch.apply_patch_contract(patch_path=patch_bad, dry_run=False)
        self.assertEqual(rc_bad, 1)
        self.assertFalse(res_bad["results"][0]["applied"])
        self.assertEqual(res_bad["results"][0]["reason_code"], codec.ReasonCode.INVALID_ENUM.value)
        self.assertFalse(res_bad["results"][0]["runtime_verified"])
        self.assertFalse(res_bad["results"][1]["applied"])
        self.assertEqual(res_bad["results"][1]["error"], "invalid_task_id")

        # Pending capability apply blocks BOTH write_taskmaster_status_guarded and apply_chapter7_status_patch (dry & live).
        _put_json(
            flow_root,
            op_scope.CAP_PENDING,
            {"run_id": "cap-p01", "journal_path": "logs/ci/capability-planning/cap-p01/apply-journal.json"},
        )
        with self.assertRaises(codec.CodecError) as ctx:
            ch6_gate.write_taskmaster_status_guarded(flow_root, 101, "in-progress")
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.CONFLICT)
        for dry_flag in (True, False):
            rc_p, res_p = ch7_patch.apply_patch_contract(patch_path=patch_back, dry_run=dry_flag)
            self.assertEqual(rc_p, 1)
            self.assertFalse(res_p["results"][0]["applied"])
            self.assertTrue(res_p["results"][0]["guarded_write"])
            self.assertEqual(res_p["results"][0]["reason_code"], codec.ReasonCode.CONFLICT.value)
            self.assertFalse(res_p["results"][0]["runtime_verified"])
            self.assertFalse(res_p["results"][0]["default_b_enabled"])

    def test_p02_mixed_flow_other_verification_and_deferred_only_nonflow(self) -> None:
        # 1. Mixed plan (flow + other_verification): missing other_verification_refs MUST block even when manifest_refs exist!
        flow_root = self._clone(self._flow_base, "p02_mixed")
        origin_flow = task_resolver.resolve_task_origin(flow_root, 101)
        self.assertTrue(origin_flow["ok"])
        bundle = ch5_b._load_plan_and_binding_bundle(flow_root, origin_flow)
        loaded_plans, loaded_bindings, sealed_digests, views, master_tasks, back_by_tid, gameplay_by_tid = bundle

        mixed_plans = copy.deepcopy(loaded_plans)
        pref, praw, pdoc = mixed_plans["plan-reward"]
        pdoc["requirement_verification"].append(
            {
                "requirement_id": "REQ-MIXED-OV",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Deterministic static audit alongside the gameplay flow.",
                "sink_id": "SINK-MIXED",
                "verification_ref": "docs/testing/nonflow-checklist.md",
                "authority_ref": None,
                "evidence_ids": [],
            }
        )
        pdoc["applicability"].append(
            {
                "requirement_id": "REQ-MIXED-OV",
                "disposition": "other_verification",
                "rationale": "Deterministic static audit alongside the gameplay flow.",
                "other_verification_refs": [],
            }
        )
        mixed_plans["plan-reward"] = (pref, praw, pdoc)
        mixed_bundle = (mixed_plans, loaded_bindings, sealed_digests, views, master_tasks, back_by_tid, gameplay_by_tid)
        with patch.object(ch5_b, "_load_plan_and_binding_bundle", return_value=mixed_bundle):
            with self.assertRaises(codec.CodecError) as ctx:
                ch6_gate._validate_stage5_bindings_for_gate(flow_root, 101, origin_flow)
            self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.MISSING_REQUIRED_FIELD)

        # Providing a valid live other_verification_ref makes the mixed plan pass cleanly!
        ov_raw = (flow_root / "docs/testing/nonflow-checklist.md").read_bytes()
        pdoc["applicability"][-1]["other_verification_refs"] = [
            {
                "owner": "other_verification",
                "ref": "docs/testing/nonflow-checklist.md",
                "files": [{"path": "docs/testing/nonflow-checklist.md", "raw_digest": codec.raw_digest(ov_raw)}],
            }
        ]
        with patch.object(ch5_b, "_load_plan_and_binding_bundle", return_value=mixed_bundle):
            s5_summary, _ = ch6_gate._validate_stage5_bindings_for_gate(flow_root, 101, origin_flow)
        self.assertTrue(s5_summary["has_flow_obligations"])
        self.assertTrue(s5_summary["has_non_flow_obligations"])
        self.assertEqual(s5_summary["mode"], "mixed")

        # 2. Legal deferred-only zero-MVG-impact non-Flow plan passes with substantive rationale and blocks if rationale is blank!
        nf_root = self._clone(self._nonflow_base, "p02_deferred")
        origin_nf = task_resolver.resolve_task_origin(nf_root, 101)
        self.assertTrue(origin_nf["ok"])
        nf_bundle = ch5_b._load_plan_and_binding_bundle(nf_root, origin_nf)
        nf_plans, nf_bindings, nf_sealed, nf_views, nf_master, nf_back, nf_game = nf_bundle
        def_plans = copy.deepcopy(nf_plans)
        npref, npraw, npdoc = def_plans["plan-reward"]
        npdoc["requirement_verification"] = [
            {
                "requirement_id": "REQ-NONFLOW-1",
                "disposition": "deferred",
                "flow_id": None,
                "rationale": "Explicitly deferred to Milestone 2 polish phase after core loop freeze.",
                "sink_id": "SINK-DEFER",
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            }
        ]
        npdoc["applicability"] = [
            {
                "requirement_id": "REQ-NONFLOW-1",
                "disposition": "deferred",
                "rationale": "Explicitly deferred to Milestone 2 polish phase after core loop freeze.",
                "other_verification_refs": [],
            }
        ]
        def_plans["plan-reward"] = (npref, npraw, npdoc)
        def_bundle = (def_plans, nf_bindings, nf_sealed, nf_views, nf_master, nf_back, nf_game)
        with patch.object(ch5_b, "_load_plan_and_binding_bundle", return_value=def_bundle):
            def_summary, _ = ch6_gate._validate_stage5_bindings_for_gate(nf_root, 101, origin_nf)
        self.assertEqual(def_summary["mode"], "non_flow")
        self.assertTrue(def_summary["has_non_flow_obligations"])

        # Empty rationale on deferred-only plan must fail closed!
        npdoc["requirement_verification"][0]["rationale"] = ""
        npdoc["applicability"][0]["rationale"] = ""
        with patch.object(ch5_b, "_load_plan_and_binding_bundle", return_value=def_bundle):
            with self.assertRaises(codec.CodecError) as ctx:
                ch6_gate._validate_stage5_bindings_for_gate(nf_root, 101, origin_nf)
            self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

    def test_p03_scope_mode_zero_lease_receipts_probe_zero_mutation_and_snapshot_drift_stage(self) -> None:
        flow_root = self._clone(self._flow_base, "p03_scope")
        # Clear any pre-existing lock dirs created during setUpClass reconciliation before probing!
        shutil.rmtree(flow_root / op_scope.STORE, ignore_errors=True)
        # 1. _probe_scope_lock_is_held on unlocked scope creates ZERO lock dirs/files!
        self.assertFalse(ch6_gate._probe_scope_lock_is_held(flow_root, "task:101"))
        self.assertFalse((flow_root / op_scope.STORE).exists())

        # 2. evaluate_chapter6_gate(lock_mode="scope") creates ZERO lease receipts under logs/ci/b-route-chapter6-leases!
        snap_before = input_set.resolve_input_set(flow_root, 101)
        self.assertTrue(snap_before["ok"])
        res_scope = ch6_gate.evaluate_chapter6_gate(flow_root, 101, lock_mode="scope", consumer="p03_test")
        self.assertTrue(res_scope["ok"], res_scope)
        self.assertEqual(res_scope["lock_mode"], "scope")
        self.assertFalse((flow_root / ch6_gate.LEASE_DIR).exists())

        # 3. Exact return_stage preservation on snapshot drift under lock_mode="scope" (overlay edit -> return_stage="4")!
        _put(
            flow_root,
            "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
            "---\nPRD-ID: PRD-NEWROUGE-GAME-0001\nTitle: Reward\nStatus: Draft\nADRs: [ADR-0004]\n---\n\n# Drifted Overlay\n",
        )
        res_drift = ch6_gate.evaluate_chapter6_gate(
            flow_root,
            101,
            expected_input_set_digest=snap_before["input_set_digest"],
            expected_input_set_snapshot=snap_before,
            lock_mode="scope",
            consumer="p03_drift",
        )
        self.assertFalse(res_drift["ok"])
        self.assertEqual(res_drift["reason_code"], codec.ReasonCode.INPUT_STALE.value)
        self.assertEqual(res_drift["return_stage"], "4")
        self.assertFalse((flow_root / ch6_gate.LEASE_DIR).exists())

        # 4. explicit_not_enabled_a under lock_mode="scope" creates ZERO lock dirs!
        exp_root = self._clone(self._explicit_a_base, "p03_exp_a")
        exp_res = ch6_gate.evaluate_chapter6_gate(exp_root, 11, lock_mode="scope", consumer="p03_exp")
        self.assertTrue(exp_res["ok"])
        self.assertEqual(exp_res["route"], "explicit_not_enabled_a")
        self.assertEqual(exp_res["lock_mode"], "scope")
        self.assertFalse((exp_root / op_scope.STORE).exists())

    def test_p04_test_refs_sync_blocks_b_and_frozen_a_zero_write_unchanged_and_non_ascii(self) -> None:
        import update_task_test_refs as uttr

        # 1. guard_task_test_refs_sync handles non-ASCII task_id cleanly without raising!
        flow_root = self._clone(self._flow_base, "p04_b")
        g_bad = ch6_gate.guard_task_test_refs_sync(flow_root, "\u00b9", changed=True)
        self.assertFalse(g_bad["ok"])
        self.assertFalse(g_bad["allow_write"])
        self.assertEqual(g_bad["reason_code"], codec.ReasonCode.INVALID_ARGUMENT.value)

        # 2. guard_task_test_refs_sync blocks changed=True on BOTH B-route AND frozen-A tasks!
        fa_root = self._clone(self._frozen_a_base, "p04_fa")
        fa_tid = self._frozen_a_info["task_id"]
        g_fa = ch6_gate.guard_task_test_refs_sync(fa_root, fa_tid, changed=True)
        self.assertFalse(g_fa["ok"])
        self.assertFalse(g_fa["allow_write"])
        self.assertEqual(g_fa["route"], "A")
        self.assertEqual(g_fa["reason_code"], codec.ReasonCode.CONFLICT.value)
        self.assertEqual(g_fa["return_stage"], "3C")

        # 3. update_task_test_refs.py: unchanged -> zero disk writes; changed on B/frozen-A -> rc=2; non-ASCII -> rc=2!
        _put_json(
            flow_root,
            ".taskmaster/tasks/tasks_gameplay.json",
            [{"id": "GM-0101", "taskmaster_id": 101, "title": "Reward producer task", "status": "in-progress", "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"]}],
        )
        back_path = flow_root / ".taskmaster/tasks/tasks_back.json"
        back_data = json.loads(back_path.read_text(encoding="utf-8"))
        back_data[0]["test_refs"] = ["Game.Core.Tests/Reward/RewardFlowTests.cs"]
        _put_json(flow_root, ".taskmaster/tasks/tasks_back.json", back_data)
        with (
            patch.object(uttr, "repo_root", return_value=flow_root),
            patch.object(uttr, "write_json", side_effect=AssertionError("unchanged must not write")),
            patch.object(sys, "argv", ["update_task_test_refs.py", "--task-id", "101", "--add", "Game.Core.Tests/Reward/RewardFlowTests.cs", "--write"]),
        ):
            self.assertEqual(uttr.main(), 0)

        before_bytes = back_path.read_bytes()
        buf = io.StringIO()
        with (
            patch.object(uttr, "repo_root", return_value=flow_root),
            patch.object(sys, "argv", ["update_task_test_refs.py", "--task-id", "101", "--add", "Game.Core.Tests/Reward/NewTest.cs", "--write"]),
            patch("sys.stdout", buf),
        ):
            rc = uttr.main()
        self.assertEqual(rc, 2)
        self.assertIn("reason_code=conflict", buf.getvalue())
        self.assertEqual(back_path.read_bytes(), before_bytes)

        with (
            patch.object(uttr, "repo_root", return_value=flow_root),
            patch.object(sys, "argv", ["update_task_test_refs.py", "--task-id", "\u00b9", "--write"]),
        ):
            self.assertEqual(uttr.main(), 2)

    def test_p05_p06_p07_direct_scripts_mid_round_drift_zero_mkdir_and_cli_metrics(self) -> None:
        import chapter6_knowledge
        import llm_generate_red_test as gen_red
        import llm_review_needs_fix_fast as nf_fast
        import importlib.util as _iu

        blocked_root = self._clone(self._flow_base, "p05_blocked")
        (blocked_root / "docs/testing/mvg/reward-baseline.json").unlink()

        # P-05a: Direct chapter6_knowledge.run blocks on B-blocked with zero writes!
        k_res = chapter6_knowledge.run(blocked_root, "101")
        self.assertEqual(k_res["status"], "blocked_by_b_route_gate")
        self.assertEqual(k_res["global_refresh"], "not_performed")
        self.assertFalse(k_res["runtime_verified"])
        self.assertFalse(k_res["default_b_enabled"])
        self.assertFalse((blocked_root / "logs/ci/chapter6-knowledge/task-101").exists())

        # P-05b: Direct llm_generate_red_test.py blocks before ci_dir or LLM!
        buf = io.StringIO()
        with (
            patch.object(gen_red, "repo_root", return_value=blocked_root),
            patch.object(gen_red, "ci_dir", side_effect=AssertionError("must block before ci_dir")),
            patch.object(gen_red, "_run_codex_exec", side_effect=AssertionError("must block before LLM")),
            patch.object(sys, "argv", ["llm_generate_red_test.py", "--task-id", "101"]),
            patch("sys.stdout", buf),
        ):
            self.assertEqual(gen_red.main(), 2)
        self.assertIn("BLOCKED by b-route-chapter6-gate", buf.getvalue())

        # P-05c: dev_cli run-acceptance-preflight with blank --task-id blocks on B repo!
        buf = io.StringIO()
        with (
            patch.object(dev_cli, "REPO_ROOT", blocked_root),
            patch.object(dev_cli, "run", side_effect=AssertionError("must block before subprocess")),
            patch("sys.stdout", buf),
        ):
            self.assertEqual(dev_cli.main(["run-acceptance-preflight"]), 2)
        self.assertIn("task_id_required_on_b_route_repository", buf.getvalue())

        # P-06: llm_review_needs_fix_fast.py mid-round drift aborts before LLM round!
        flow_root = self._clone(self._flow_base, "p06_drift")
        nf_out = flow_root / "logs/ci/nf-mid-drift"

        def _drift_on_det_step(*_args, **_kwargs):
            # Trigger mid-run drift right after deterministic step completes, before LLM round 1!
            _put(flow_root, "sources/reward-gdd.md", "# Mid-round drifted GDD\n")
            return {"name": "pipeline-deterministic", "status": "ok", "rc": 0}

        buf = io.StringIO()
        with (
            patch.object(nf_fast, "repo_root", return_value=flow_root),
            patch.object(nf_fast, "ci_dir", return_value=nf_out),
            patch.object(nf_fast, "try_skip_when_latest_pipeline_already_clean", return_value=None),
            patch.object(nf_fast, "try_stop_when_latest_llm_unknown_without_anchor_fix", return_value=None),
            patch.object(nf_fast, "_run_chapter6_route_preflight", return_value={}),
            patch.object(nf_fast, "resolve_deterministic_execution_plan", return_value={"mode": "full-pipeline", "cmd": ["py"], "change_scope": {}}),
            patch.object(nf_fast, "try_reuse_latest_deterministic_step", return_value=None),
            patch.object(nf_fast, "run_step", side_effect=_drift_on_det_step),
            patch.object(sys, "argv", ["llm_review_needs_fix_fast.py", "--task-id", "101", "--max-rounds", "1"]),
            patch("sys.stdout", buf),
        ):
            rc_nf = nf_fast.main()
        self.assertEqual(rc_nf, 2)
        self.assertIn("BLOCKED by b-route-chapter6-gate", buf.getvalue())

        # P-07a: build/tdd.py pre-gate zero mkdir when blocked or --task-id omitted on B repo!
        tdd_spec = _iu.spec_from_file_location("sc_build_tdd_p07", SCRIPTS_SC / "build/tdd.py")
        tdd_mod = _iu.module_from_spec(tdd_spec)
        tdd_spec.loader.exec_module(tdd_mod)
        for tdd_argv in (
            ["tdd.py", "--stage", "red", "--task-id", "101"],
            ["tdd.py", "--stage", "red"],
            ["tdd.py", "--stage", "red", "--task-id", " 101 "],
        ):
            with (
                patch.object(tdd_mod, "repo_root", return_value=blocked_root),
                patch.object(tdd_mod, "ci_dir", side_effect=AssertionError("must block before ci_dir mkdir")),
                patch.object(sys, "argv", tdd_argv),
            ):
                self.assertEqual(tdd_mod.main(), 2)

        # P-07b: scripts/sc/test.py rejects whitespace --task-id "   " with rc=2!
        sc_test_spec = _iu.spec_from_file_location("sc_test_p07", SCRIPTS_SC / "test.py")
        sc_test_mod = _iu.module_from_spec(sc_test_spec)
        sc_test_spec.loader.exec_module(sc_test_mod)
        with (
            patch.object(sc_test_mod, "repo_root", return_value=blocked_root),
            patch.object(sc_test_mod, "ci_dir", side_effect=AssertionError("must block before ci_dir")),
            patch.object(sys, "argv", ["test.py", "--type", "unit", "--task-id", "   "]),
        ):
            self.assertEqual(sc_test_mod.main(), 2)

        # P-07c: check_b_route_chapter6_gate.py reports active_elapsed_seconds < 60 AND exits rc=2 on bad digest!
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc_cli = ch6_gate_cli.main(
                [
                    "--root",
                    str(flow_root),
                    "--task-id",
                    "101",
                    "--expected-input-set-digest",
                    "not-a-sha256",
                ]
            )
        self.assertEqual(rc_cli, 2)
        cli_bad = json.loads(buf.getvalue())
        self.assertEqual(cli_bad["reason_code"], codec.ReasonCode.INVALID_DIGEST.value)
        self.assertLess(cli_bad["metrics"]["active_elapsed_seconds"], 60.0)

        # P-07d: check_b_route_chapter6_gate.py invalid task-id also reports active_elapsed_seconds < 60!
        buf2 = io.StringIO()
        with patch("sys.stdout", buf2):
            rc_cli2 = ch6_gate_cli.main(["--root", str(flow_root), "--task-id", "\u00b9"])
        self.assertEqual(rc_cli2, 2)
        cli_bad2 = json.loads(buf2.getvalue())
        self.assertLess(cli_bad2["metrics"]["active_elapsed_seconds"], 60.0)


if __name__ == "__main__":
    unittest.main()
