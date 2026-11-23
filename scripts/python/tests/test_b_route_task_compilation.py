"""Deterministic tests for Story 3.2 governed 3C triplet compilation and binding.

Covers every row of the Story 3.2 I/O & Edge-Case Matrix (HAPPY, SHARED, LIVE,
RECOVER, BLOCK), nine-stage CLI, schema AUXILIARY isolation, two-phase live
status merge, receipt succession, crash recovery, noop replay, and zero
__pycache__/.pyc generation.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import contextlib
import copy
import datetime as dt
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_PY.parents[1]
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_records as records
import _b_route_schema_resources as schema_resources
import _b_route_task_compilation as compilation
import _b_route_task_preview as task_preview
import _planning_apply_journal as journal
import account_b_route_sources as sources_cli
import compile_b_route_tasks as compile_cli
import dev_cli
import dev_cli_builders
import preview_b_route_task_changes as preview_cli


_CACHED_3A_PROOFS: dict[bool, tuple[tempfile.TemporaryDirectory[str], Path, dict[str, bytes], dict]] = {}


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _typed_ref(path: str, schema_version: str, entity_id: str, revision: int, raw: bytes) -> dict:
    return {
        "path": path,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.raw_digest(raw),
        "verification_mode": "raw",
        "codec_version": None,
    }


def _owned_ref(owner: str, ref: str, files: list[tuple[str, bytes]]) -> dict:
    return {
        "owner": owner,
        "ref": ref,
        "files": [{"path": p, "raw_digest": codec.raw_digest(raw)} for p, raw in files],
    }


def _raw_ref(path: str, schema_version: str, raw: bytes) -> dict:
    return {
        "path": path,
        "schema_version": schema_version,
        "raw_digest": codec.raw_digest(raw),
    }


def _four_parts(*, domain: bool = True, adapter: bool = True, binding: bool = True, scene: bool = False) -> list[dict]:
    specs = [
        ("domain_rules", domain, "Core deterministic reward rules."),
        ("csharp_adapter", adapter, "Thin C# adapter forwarding commands."),
        ("binding", binding, "Resource and event binding contracts."),
        ("scene", scene, "Godot scene wiring for reward display."),
    ]
    return [
        {
            "kind": kind,
            "applicability": "applicable" if applicable else "not_applicable",
            "rationale": desc if applicable else f"{kind} is not needed for this flow.",
            "responsibilities": [desc] if applicable else [],
        }
        for kind, applicable, desc in specs
    ]


class CompilationFixture:
    """Self-contained temporary repository with real 3A proof, 3B committed bundle, 3.1 preview, and triplet."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._owns_tmp = True
        self.root = Path(self._tmp.name).resolve()
        self.scope_id = "scope-reward"
        self.plan_id = "reward-plan"
        self.run_counter = 0

    def cleanup(self) -> None:
        if self._owns_tmp:
            self._tmp.cleanup()
            self._owns_tmp = False

    def put(self, rel: str, data: bytes | str) -> bytes:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return raw

    def put_json(self, rel: str, value: object) -> bytes:
        return self.put(rel, _encoded(value))

    def read_json(self, rel: str) -> object:
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def snapshot_targets(self) -> dict[str, bytes]:
        snap: dict[str, bytes] = {}
        for folder in (".taskmaster", "docs"):
            base = self.root / folder
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    snap[p.relative_to(self.root).as_posix()] = p.read_bytes()
        return snap

    def setup_3a_proof(self, *, synthetic: bool = False) -> dict:
        self.put(
            "docs/gdd/reward.md",
            "# Reward Loop\n\n## Reward Selection\nPlayer picks one reward and returns to map.\n\n"
            "## Governance Audit\nAudit reward invariants via static verification.\n\n"
            "## Secondary Plan\nSecondary cross-plan combat handoff.\n",
        )
        self.put_json(
            "docs/workflows/chapter3-source-set.json",
            {
                "schema_version": "chapter3.source-set.v1",
                "active_patterns": ["docs/gdd/reward.md"],
                "active_sources": ["docs/gdd/reward.md"],
                "retirements": [],
            },
        )
        src_runner = (SCRIPTS_PY / "tests/fixtures/b_route_audit_synthetic_runner.py").read_text(encoding="utf-8")
        runner_code = src_runner.replace("CODE_ROOT = None", "CODE_ROOT = " + repr(str(SCRIPTS_PY)))
        if not synthetic:
            runner_code = runner_code.replace('"synthetic": True', '"synthetic": False')
            runner_code = runner_code.replace(
                'MODEL = "synthetic/source-audit-v1"',
                'MODEL = "test-fixture/verified-model-v1"',
            )
        self.put("runner.py", runner_code)
        expected_model = "synthetic/source-audit-v1" if synthetic else "test-fixture/verified-model-v1"

        with contextlib.redirect_stdout(io.StringIO()):
            rc_prep = sources_cli.main([
                "--stage", "prepare",
                "--root", str(self.root),
                "--run-id", "run3a",
                "--scope-id", self.scope_id,
                "--attempt-id", "prep1",
                "--source-set", "docs/workflows/chapter3-source-set.json",
            ])
        assert rc_prep == 0, f"3A prepare failed: rc={rc_prep}"
        date_str = dt.datetime.now(dt.timezone.utc).date().isoformat()
        prep_dir = f"logs/ci/{date_str}/b-route-sources/run3a/prep1/prepare"
        prepared_ref = f"{prep_dir}/prepared.json"
        ledger = self.read_json(f"{prep_dir}/source-blocks.json")
        manifest = self.read_json(f"{prep_dir}/source-manifest.json")
        blocks = ledger["blocks"]

        cand = self.read_json(f"{prep_dir}/candidate.json")
        all_ids = [row["block_id"] for row in cand["block_results"]]
        for row in cand["block_results"]:
            row["delivery_potential"] = True
            row.update(
                disposition="atomized",
                atoms=[{
                    "proposal_id": "proposal:reward-order",
                    "kind": "functional",
                    "statement": "Preserve reward order and invariants.",
                    "source_block_ids": all_ids,
                    "acceptance_intent": "Selecting a reward preserves the displayed ordering.",
                    "prior_requirement_ids": [],
                    "non_task_sinks": ["sink:static-audit"],
                }],
            )
        for row in cand["batch_summaries"]:
            row["output_accounted_count"] = row["input_block_count"]
        cand_path = "logs/ci/3a-inputs/account-candidate.json"
        self.put_json(cand_path, cand)
        with contextlib.redirect_stdout(io.StringIO()):
            rc_acc = sources_cli.main([
                "--stage", "account",
                "--root", str(self.root),
                "--run-id", "run3a",
                "--scope-id", self.scope_id,
                "--attempt-id", "acc1",
                "--prepared", prepared_ref,
                "--candidate", cand_path,
            ])
        assert rc_acc == 0, f"3A account failed: rc={rc_acc}"
        accounted_report_ref = f"logs/ci/{date_str}/b-route-sources/run3a/acc1/account/report.json"

        with contextlib.redirect_stdout(io.StringIO()):
            rc_aud = sources_cli.main([
                "--stage", "audit",
                "--root", str(self.root),
                "--run-id", "run3a-audit",
                "--scope-id", self.scope_id,
                "--attempt-id", "aud1",
                "--accounted", accounted_report_ref,
                "--runner", "runner.py",
                "--expected-model", expected_model,
                "--request-budget", "4",
                "--active-budget-seconds", "600",
                "--timeout-seconds", "120",
            ])
        assert rc_aud == 0, f"3A audit failed: rc={rc_aud}"
        audit_report_ref = f"logs/ci/{date_str}/b-route-source-audit/run3a-audit/aud1/report.json"

        # Also create a second-scope 3A audit proof for cross-plan SHARED tests.
        with contextlib.redirect_stdout(io.StringIO()):
            rc_prep_b = sources_cli.main([
                "--stage", "prepare",
                "--root", str(self.root),
                "--run-id", "run3a-b",
                "--scope-id", "scope-combat",
                "--attempt-id", "prep1",
                "--source-set", "docs/workflows/chapter3-source-set.json",
            ])
        assert rc_prep_b == 0
        prep_dir_b = f"logs/ci/{date_str}/b-route-sources/run3a-b/prep1/prepare"
        cand_b = self.read_json(f"{prep_dir_b}/candidate.json")
        all_ids_b = [row["block_id"] for row in cand_b["block_results"]]
        for row in cand_b["block_results"]:
            row["delivery_potential"] = True
            row.update(
                disposition="atomized",
                atoms=[{
                    "proposal_id": "proposal:combat-handoff",
                    "kind": "functional",
                    "statement": "Preserve combat handoff invariants.",
                    "source_block_ids": all_ids_b,
                    "acceptance_intent": "Combat handoff transitions deterministically.",
                    "prior_requirement_ids": [],
                    "non_task_sinks": ["sink:static-audit"],
                }],
            )
        for row in cand_b["batch_summaries"]:
            row["output_accounted_count"] = row["input_block_count"]
        cand_b_path = "logs/ci/3a-inputs/account-candidate-b.json"
        self.put_json(cand_b_path, cand_b)
        with contextlib.redirect_stdout(io.StringIO()):
            rc_acc_b = sources_cli.main([
                "--stage", "account",
                "--root", str(self.root),
                "--run-id", "run3a-b",
                "--scope-id", "scope-combat",
                "--attempt-id", "acc1",
                "--prepared", f"{prep_dir_b}/prepared.json",
                "--candidate", cand_b_path,
            ])
        assert rc_acc_b == 0
        with contextlib.redirect_stdout(io.StringIO()):
            rc_aud_b = sources_cli.main([
                "--stage", "audit",
                "--root", str(self.root),
                "--run-id", "run3a-audit-b",
                "--scope-id", "scope-combat",
                "--attempt-id", "aud1",
                "--accounted", f"logs/ci/{date_str}/b-route-sources/run3a-b/acc1/account/report.json",
                "--runner", "runner.py",
                "--expected-model", expected_model,
                "--request-budget", "4",
                "--active-budget-seconds", "600",
                "--timeout-seconds", "120",
            ])
        assert rc_aud_b == 0
        audit_report_ref_b = f"logs/ci/{date_str}/b-route-source-audit/run3a-audit-b/aud1/report.json"

        return {
            "audit_ref": audit_report_ref,
            "manifest_path": f"{prep_dir}/source-manifest.json",
            "ledger_path": f"{prep_dir}/source-blocks.json",
            "manifest": manifest,
            "ledger": ledger,
            "blocks": blocks,
            "audit_ref_b": audit_report_ref_b,
            "manifest_path_b": f"{prep_dir_b}/source-manifest.json",
            "ledger_path_b": f"{prep_dir_b}/source-blocks.json",
            "manifest_b": self.read_json(f"{prep_dir_b}/source-manifest.json"),
            "ledger_b": self.read_json(f"{prep_dir_b}/source-blocks.json"),
        }

    def populate_from_cached_3a(self, *, synthetic: bool = False) -> dict:
        if synthetic not in _CACHED_3A_PROOFS:
            fx = CompilationFixture()
            audit_info = fx.setup_3a_proof(synthetic=synthetic)
            work_tmp = fx._tmp
            work_root = fx.root
            fx._owns_tmp = False
            base_files = {
                p.relative_to(work_root).as_posix(): p.read_bytes()
                for p in sorted(work_root.rglob("*"))
                if p.is_file()
            }
            _CACHED_3A_PROOFS[synthetic] = (work_tmp, work_root, base_files, audit_info)
        _work_tmp, work_root, base_files, audit_info = _CACHED_3A_PROOFS[synthetic]
        if self._owns_tmp:
            self._tmp.cleanup()
            self._owns_tmp = False
        self.root = work_root
        for path in sorted(work_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file() or path.is_symlink():
                rel = path.relative_to(work_root).as_posix()
                if rel not in base_files:
                    path.unlink()
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        for rel, raw in base_files.items():
            target = work_root / rel
            if not target.is_file() or target.read_bytes() != raw:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        return copy.deepcopy(audit_info)

    def write_triplet(self, *, master_tasks: list[dict], back_tasks: list[dict], gameplay_tasks: list[dict]) -> None:
        self.put_json(".taskmaster/tasks/tasks.json", {"master": {"tasks": master_tasks}})
        self.put_json(".taskmaster/tasks/tasks_back.json", back_tasks)
        self.put_json(".taskmaster/tasks/tasks_gameplay.json", gameplay_tasks)

    def write_committed_3b_single_or_dual(self, audit_info: dict, *, dual: bool = False) -> dict:
        block_ids = [b["block_id"] for b in audit_info["blocks"]]
        manifest_path = audit_info["manifest_path"]
        ledger_path = audit_info["ledger_path"]
        manifest_raw = (self.root / manifest_path).read_bytes()
        ledger_raw = (self.root / ledger_path).read_bytes()
        manifest = audit_info["manifest"]

        proof_raw = self.put_json("logs/ci/test-inputs/adoption-proof.json", {"proof": "adopted-3b"})
        adr_raw = self.put("docs/adr/ADR-0040-test.md", "# ADR-0040 Test\n")
        authority_raw = self.put("docs/workflows/authority-note.md", "# Authority Note\n")
        other_ver_raw = self.put("docs/workflows/other-ver-check.md", "# Static Audit Rule\n")

        other_ver_owned = _owned_ref(
            "other_verification",
            "docs/workflows/other-ver-check.md",
            [("docs/workflows/other-ver-check.md", other_ver_raw)],
        )

        req_ver_a = [
            {
                "requirement_id": "RQ-REWARD-1",
                "disposition": "flow",
                "flow_id": "FLOW-REWARD",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "rationale": "Verified by reward return flow.",
                "evidence_ids": [],
            },
            {
                "requirement_id": "RQ-AUDIT-1",
                "disposition": "other_verification",
                "flow_id": None,
                "sink_id": "sink:static-audit",
                "verification_ref": "docs/workflows/other-ver-check.md",
                "authority_ref": None,
                "rationale": "Static audit without fake flow.",
                "evidence_ids": [],
            },
        ]
        plan_a = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": self.plan_id,
            "revision": 1,
            "source_identity": {
                "manifest_ref": _owned_ref("source_manifest", manifest_path, [(manifest_path, manifest_raw)]),
                "ledger_ref": _owned_ref("source_ledger", ledger_path, [(ledger_path, ledger_raw)]),
                "source_revision": manifest["source_revision"],
                "source_manifest_digest": manifest["manifest_sha256"],
            },
            "requirements": [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "source_block_ids": block_ids,
                    "acceptance_intent": "Reward selection returns to map deterministically.",
                    "non_task_sinks": [],
                },
                {
                    "requirement_id": "RQ-AUDIT-1",
                    "source_block_ids": block_ids,
                    "acceptance_intent": "Static reward governance invariants pass.",
                    "non_task_sinks": ["sink:static-audit"],
                },
            ],
            "definitions": {
                "flows": [
                    {
                        "id": "FLOW-REWARD",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "entry": "combat_win",
                        "entry_condition": "player_won_combat",
                        "success_end": "map_ready",
                        "branches": [
                            {"kind": "failure", "rationale": "Failure branch.", "description": "Abort cleanly."},
                            {"kind": "cancel", "rationale": "Cancel branch.", "description": "Skip reward."},
                            {"kind": "return", "rationale": "Return branch.", "description": "Return to map."},
                        ],
                        "handoffs": [
                            {
                                "id": "ho:FLOW-REWARD",
                                "responsibility": "Deliver selected reward to run state.",
                                "state_uses": [],
                                "result": "reward_applied",
                            }
                        ],
                        "state_owners": [],
                        "parts": _four_parts(domain=True, adapter=True, binding=True, scene=False),
                        "observable_result": "Reward flow returns deterministically to map.",
                        "verification_targets": ["mvg:combat-reward-return"],
                        "loops": [],
                    }
                ],
                "commands": [
                    {
                        "id": "CMD-SELECT-REWARD",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "responsibility": "Select reward",
                        "uses": [],
                    }
                ],
                "states": [
                    {
                        "id": "STATE-REWARD-OFFER",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "responsibility": "Read-only reward offer",
                        "uses": [],
                    }
                ],
            },
            "logical_references": [],
            "requirement_verification": req_ver_a,
            "requirement_route_memberships": [
                {"requirement_id": "RQ-REWARD-1", "flow_id": "FLOW-REWARD", "observable_role": "primary"}
            ],
            "requirement_evidence": [],
            "evidence_source_refs": [
                copy.deepcopy(other_ver_owned),
            ],
            "coverage_table": [{k: v for k, v in r.items() if k != "evidence_ids"} for r in req_ver_a],
            "applicability": [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "disposition": "flow",
                    "rationale": "Verified by reward return flow.",
                    "other_verification_refs": [],
                },
                {
                    "requirement_id": "RQ-AUDIT-1",
                    "disposition": "other_verification",
                    "rationale": "Static audit without fake flow.",
                    "other_verification_refs": [copy.deepcopy(other_ver_owned)],
                },
            ],
            "adoption_proof_refs": [
                _owned_ref("planning_proof", "logs/ci/test-inputs/adoption-proof.json", [("logs/ci/test-inputs/adoption-proof.json", proof_raw)])
            ],
            "lineage": {"previous_plan_ref": None, "change_summary": "Initial 3B plan A.", "identity_alignment": []},
        }
        plan_a_path = f"docs/planning/b-route/plans/{self.plan_id}/1.json"
        plan_a_raw = self.put_json(plan_a_path, plan_a)
        plan_a_ref = _typed_ref(plan_a_path, "newrouge.b-route-plan.v1", self.plan_id, 1, plan_a_raw)

        policy = {
            "schema_version": "newrouge.b-route-policy.v1",
            "policy_id": "policy",
            "policy_revision": 1,
            "switch_boundary": {
                "default_route": "A",
                "a_write_allowed": True,
                "allowed_a_operations": ["chapter6"],
                "authority_refs": [
                    _owned_ref("authority", "docs/workflows/authority-note.md", [("docs/workflows/authority-note.md", authority_raw)])
                ],
            },
            "frozen_a_refs": [
                _owned_ref("frozen_a_inventory", "docs/adr/ADR-0040-test.md", [("docs/adr/ADR-0040-test.md", adr_raw)])
            ],
        }
        policy_path = "docs/planning/b-route/policy.v1.json"
        policy_raw = self.put_json(policy_path, policy)
        policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy", 1, policy_raw)

        origins = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": [],
            "frozen_legacy_refs": [
                _owned_ref("frozen_a_inventory", "docs/adr/ADR-0040-test.md", [("docs/adr/ADR-0040-test.md", adr_raw)])
            ],
        }
        origins_path = "docs/planning/b-route/task-origins.v1.json"
        origins_raw = self.put_json(origins_path, origins)
        origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

        def_owners = [
            {"kind": "flow", "definition_id": "FLOW-REWARD", "plan_ref": copy.deepcopy(plan_a_ref)},
            {"kind": "command", "definition_id": "CMD-SELECT-REWARD", "plan_ref": copy.deepcopy(plan_a_ref)},
            {"kind": "state", "definition_id": "STATE-REWARD-OFFER", "plan_ref": copy.deepcopy(plan_a_ref)},
        ]
        target_pairs = [(policy_path, policy_raw), (origins_path, origins_raw), (plan_a_path, plan_a_raw)]
        auth_pairs = [
            ("docs/workflows/authority-note.md", authority_raw),
            ("docs/workflows/other-ver-check.md", other_ver_raw),
            ("docs/adr/ADR-0040-test.md", adr_raw),
            (manifest_path, manifest_raw),
            (ledger_path, ledger_raw),
            ("logs/ci/test-inputs/adoption-proof.json", proof_raw),
        ]
        plan_refs_all = [copy.deepcopy(plan_a_ref)]
        scopes_all = [self.scope_id]

        plan_b_ref = None
        if dual:
            manifest_b_path = audit_info["manifest_path_b"]
            ledger_b_path = audit_info["ledger_path_b"]
            manifest_b_raw = (self.root / manifest_b_path).read_bytes()
            ledger_b_raw = (self.root / ledger_b_path).read_bytes()
            manifest_b = audit_info["manifest_b"]
            blocks_b = [b["block_id"] for b in audit_info["ledger_b"]["blocks"]]
            req_ver_b = [
                {
                    "requirement_id": "RQ-COMBAT-1",
                    "disposition": "flow",
                    "flow_id": "FLOW-COMBAT",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "rationale": "Verified by combat handoff flow.",
                    "evidence_ids": [],
                }
            ]
            plan_b = {
                "schema_version": "newrouge.b-route-plan.v1",
                "plan_id": "combat-plan",
                "revision": 1,
                "source_identity": {
                    "manifest_ref": _owned_ref("source_manifest", manifest_b_path, [(manifest_b_path, manifest_b_raw)]),
                    "ledger_ref": _owned_ref("source_ledger", ledger_b_path, [(ledger_b_path, ledger_b_raw)]),
                    "source_revision": manifest_b["source_revision"],
                    "source_manifest_digest": manifest_b["manifest_sha256"],
                },
                "requirements": [
                    {
                        "requirement_id": "RQ-COMBAT-1",
                        "source_block_ids": blocks_b,
                        "acceptance_intent": "Combat handoff transitions to reward screen.",
                        "non_task_sinks": [],
                    }
                ],
                "definitions": {
                    "flows": [
                        {
                            "id": "FLOW-COMBAT",
                            "requirement_ids": ["RQ-COMBAT-1"],
                            "entry": "combat_start",
                            "entry_condition": "player_entered_combat",
                            "success_end": "combat_win",
                            "branches": [
                                {"kind": "failure", "rationale": "Defeat branch.", "description": "End run cleanly."},
                                {"kind": "cancel", "rationale": "Retreat branch.", "description": "Exit combat."},
                                {"kind": "return", "rationale": "Return branch.", "description": "Proceed to reward."},
                            ],
                            "handoffs": [
                                {
                                    "id": "ho:FLOW-COMBAT",
                                    "responsibility": "Hand off combat victory to reward screen.",
                                    "state_uses": [],
                                    "result": "combat_victory_recorded",
                                }
                            ],
                            "state_owners": [],
                            "parts": _four_parts(domain=True, adapter=True, binding=False, scene=False),
                            "observable_result": "Combat victory transitions cleanly to reward screen.",
                            "verification_targets": ["mvg:combat-reward-return"],
                            "loops": [],
                        }
                    ],
                    "commands": [],
                    "states": [],
                },
                "logical_references": [],
                "requirement_verification": req_ver_b,
                "requirement_route_memberships": [
                    {"requirement_id": "RQ-COMBAT-1", "flow_id": "FLOW-COMBAT", "observable_role": "primary"}
                ],
                "requirement_evidence": [],
                "evidence_source_refs": [],
                "coverage_table": [{k: v for k, v in r.items() if k != "evidence_ids"} for r in req_ver_b],
                "applicability": [
                    {
                        "requirement_id": "RQ-COMBAT-1",
                        "disposition": "flow",
                        "rationale": "Verified by combat handoff flow.",
                        "other_verification_refs": [],
                    }
                ],
                "adoption_proof_refs": [
                    _owned_ref("planning_proof", "logs/ci/test-inputs/adoption-proof.json", [("logs/ci/test-inputs/adoption-proof.json", proof_raw)])
                ],
                "lineage": {"previous_plan_ref": None, "change_summary": "Initial 3B plan B.", "identity_alignment": []},
            }
            plan_b_path = "docs/planning/b-route/plans/combat-plan/1.json"
            plan_b_raw = self.put_json(plan_b_path, plan_b)
            plan_b_ref = _typed_ref(plan_b_path, "newrouge.b-route-plan.v1", "combat-plan", 1, plan_b_raw)
            def_owners.append({"kind": "flow", "definition_id": "FLOW-COMBAT", "plan_ref": copy.deepcopy(plan_b_ref)})
            target_pairs.append((plan_b_path, plan_b_raw))
            auth_pairs.extend([(manifest_b_path, manifest_b_raw), (ledger_b_path, ledger_b_raw)])
            plan_refs_all.append(copy.deepcopy(plan_b_ref))
            scopes_all.append("scope-combat")

        receipt = {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": "OP-3B-INIT",
            "revision": 1,
            "operation_digest": codec.canonical_digest({"op": "OP-3B-INIT", "targets": [p for p, _ in target_pairs]}),
            "scopes": scopes_all,
            "authority": [
                {"path": p, "before_digest": codec.raw_digest(raw), "after_digest": codec.raw_digest(raw)}
                for p, raw in auth_pairs
            ],
            "targets": [
                {
                    "path": p,
                    "before_digest": None,
                    "after_digest": codec.raw_digest(raw),
                    "verification_mode": "immutable_bytes",
                    "codec_version": None,
                    "projection_digest": codec.raw_digest(raw),
                }
                for p, raw in target_pairs
            ],
            "plan_refs": plan_refs_all,
            "binding_refs": [],
            "resolved_definitions": [],
            "result": {"target_paths": [p for p, _ in target_pairs], "scope_ids": scopes_all},
        }
        receipt_path = "docs/planning/b-route/commits/OP-3B-INIT.json"
        receipt_raw = self.put_json(receipt_path, receipt)
        receipt_ref = _typed_ref(receipt_path, "newrouge.b-route-commit.v1", "OP-3B-INIT", 1, receipt_raw)

        scope_heads = [
            {
                "scope_id": self.scope_id,
                "plan_refs": [copy.deepcopy(plan_a_ref)],
                "binding_refs": [],
                "receipt_ref": copy.deepcopy(receipt_ref),
            }
        ]
        if dual and plan_b_ref is not None:
            scope_heads.append({
                "scope_id": "scope-combat",
                "plan_refs": [copy.deepcopy(plan_b_ref)],
                "binding_refs": [],
                "receipt_ref": copy.deepcopy(receipt_ref),
            })

        catalog = {
            "schema_version": "newrouge.b-route-catalog.v1",
            "catalog_id": "catalog",
            "revision": 1,
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "scope_heads": scope_heads,
            "definition_owners": def_owners,
            "task_index": [],
        }
        self.put_json("docs/planning/b-route/catalog.v1.json", catalog)
        return {"plan_a_ref": plan_a_ref, "plan_b_ref": plan_b_ref}

    def run_preview(
        self,
        *,
        plan_id: str,
        scope_id: str,
        audit_ref: str,
        manifest_ref: str | None = None,
        change_intents_ref: str | None = None,
    ) -> tuple[int, dict]:
        self.run_counter += 1
        argv = [
            "--root", str(self.root),
            "--plan-id", plan_id,
            "--scope-id", scope_id,
            "--audit-ref", audit_ref,
            "--run-id", f"prev-{self.run_counter}",
        ]
        if manifest_ref is not None:
            argv += ["--manifest", manifest_ref]
        if change_intents_ref is not None:
            argv += ["--change-intents", change_intents_ref]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = preview_cli.main(argv)
        return rc, json.loads(buf.getvalue())

    def write_request(
        self,
        rel_path: str,
        *,
        operation_id: str,
        plan_id: str,
        scope_id: str,
        audit_ref: str,
        preview_report_path: str,
        manifest_ref: str | None = None,
        change_intents_ref: str | None = None,
    ) -> str:
        audit_raw = (self.root / audit_ref).read_bytes()
        audit_doc = json.loads(audit_raw.decode("utf-8"))
        prev_raw = (self.root / preview_report_path).read_bytes()
        req: dict = {
            "schema_version": compilation.REQUEST_SCHEMA,
            "producer": compilation.PRODUCER,
            "operation_id": operation_id,
            "plan_id": plan_id,
            "scope_id": scope_id,
            "audit_ref": _raw_ref(audit_ref, audit_doc["schema_version"], audit_raw),
            "preview_ref": _raw_ref(preview_report_path, task_preview.SCHEMA, prev_raw),
        }
        if manifest_ref is not None:
            m_raw = (self.root / manifest_ref).read_bytes()
            m_doc = json.loads(m_raw.decode("utf-8"))
            req["manifest_ref"] = _raw_ref(manifest_ref, m_doc.get("schema_version", "raw.bytes.v1"), m_raw)
        if change_intents_ref is not None:
            ci_raw = (self.root / change_intents_ref).read_bytes()
            req["change_intents_ref"] = _raw_ref(change_intents_ref, task_preview.CHANGE_INTENTS_SCHEMA, ci_raw)
        self.put_json(rel_path, req)
        return rel_path

    def run_compile(self, *, stage: str, operation_id: str, request_ref: str | None = None) -> tuple[int, dict]:
        argv = ["--root", str(self.root), "--stage", stage, "--operation-id", operation_id]
        if request_ref is not None:
            argv += ["--request", request_ref]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = compile_cli.main(argv)
        return rc, json.loads(buf.getvalue())


def tearDownModule() -> None:
    for work_tmp, _work_root, _base_files, _audit in _CACHED_3A_PROOFS.values():
        work_tmp.cleanup()
    _CACHED_3A_PROOFS.clear()


class TaskCompilationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = CompilationFixture()
        self.audit_info = self.fx.populate_from_cached_3a(synthetic=False)
        self.fx.write_triplet(
            master_tasks=[
                {
                    "id": 10,
                    "title": "Existing Mature Task",
                    "description": "Mature task already in progress",
                    "status": "pending",
                    "priority": "medium",
                    "dependencies": [],
                    "subtasks": [{"id": 1, "title": "Subtask A", "status": "pending"}],
                }
            ],
            back_tasks=[
                {
                    "id": "NG-0010",
                    "taskmaster_id": 10,
                    "taskmaster_exported": True,
                    "title": "Existing Mature Task",
                    "description": "Mature task already in progress",
                    "status": "pending",
                    "priority": "P2",
                    "layer": "adapter",
                    "owner": "architecture",
                    "requirement_ids": ["RQ-LEGACY-1"],
                    "semantic_refs": ["RQ-LEGACY-1"],
                    "source_refs": ["docs/gdd/reward.md:1"],
                    "acceptance": ["Legacy acceptance Refs: docs/gdd/reward.md:1"],
                    "evidence_refs": [],
                    "labels": ["back"],
                    "semantic_review_tier": "targeted",
                    "subtasks": [{"id": 1, "title": "Subtask A", "status": "pending"}],
                }
            ],
            gameplay_tasks=[],
        )

    def tearDown(self) -> None:
        self.fx.cleanup()

    def test_schema_registration_keeps_formal_untouched_and_registers_auxiliary(self) -> None:
        self.assertEqual(
            ("common", "policy", "plan", "binding", "origins", "commit", "catalog"),
            schema_resources.FORMAL,
        )
        self.assertIn("task-compilation-operation", schema_resources.AUXILIARY)
        self.assertNotIn("task-compilation-operation", schema_resources.FORMAL)
        val = schema_resources.validator(compilation.OPERATION_SCHEMA, auxiliary=True)
        self.assertIsNotNone(val)
        with self.assertRaises(codec.CodecError):
            schema_resources.validator(compilation.OPERATION_SCHEMA, auxiliary=False)

    def test_happy_nine_stage_lifecycle_catalog_last_and_direct_edit_blocked(self) -> None:
        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=False)
        rc_prev, prev = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_prev, prev)
        req_path = self.fx.write_request(
            "logs/ci/test-inputs/req-happy.json",
            operation_id="OP-3C-HAPPY",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev["report_path"],
        )
        before_targets = self.fx.snapshot_targets()

        # 1. prepare: allocates permanent taskmaster_id (max+1 = 11, 12) + NG/GM, zero target writes.
        rc_p, res_p = self.fx.run_compile(stage="prepare", operation_id="OP-3C-HAPPY", request_ref=req_path)
        self.assertEqual(0, rc_p, res_p)
        self.assertEqual("prepared", res_p["state"])
        self.assertEqual(before_targets, self.fx.snapshot_targets())
        self.assertFalse(res_p["readiness"])
        self.assertFalse(res_p["runtime_verified"])
        self.assertFalse(res_p["default_b_enabled"])
        self.assertTrue(res_p["chapter4_5_required"])
        self.assertFalse(res_p["chapter6_authorized"])
        allocs = res_p["allocations"]["task_ids"]
        self.assertEqual(2, len(allocs))
        tids = sorted(v["taskmaster_id"] for v in allocs.values())
        self.assertEqual([11, 12], tids)
        bids = {v["business_id"] for v in allocs.values()}
        self.assertTrue(any(b.startswith("GM-") for b in bids))
        self.assertTrue(any(b.startswith("NG-") for b in bids))

        # 2. inspect (read-only)
        rc_i, res_i = self.fx.run_compile(stage="inspect", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_i, res_i)
        self.assertEqual("inspected", res_i["status"])
        self.assertEqual(before_targets, self.fx.snapshot_targets())

        # 3. reserve: freezes state without re-allocating or writing targets
        rc_r, res_r = self.fx.run_compile(stage="reserve", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_r, res_r)
        self.assertEqual("reserved", res_r["state"])
        self.assertEqual(allocs, res_r["allocations"]["task_ids"])
        self.assertEqual(before_targets, self.fx.snapshot_targets())

        # 4. apply: writes triplet/binding/origins, catalog.v1.json MUST NOT be updated yet!
        catalog_before = (self.fx.root / records.CATALOG_PATH).read_bytes()
        rc_a, res_a = self.fx.run_compile(stage="apply", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_a, res_a)
        self.assertEqual("applied", res_a["state"])
        self.assertFalse(res_a["published"])
        self.assertEqual(catalog_before, (self.fx.root / records.CATALOG_PATH).read_bytes())

        # 5. verify: writes immutable receipt, catalog.v1.json STILL not pushed!
        rc_v, res_v = self.fx.run_compile(stage="verify", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_v, res_v)
        self.assertEqual("verified", res_v["state"])
        self.assertTrue((self.fx.root / "docs/planning/b-route/commits/OP-3C-HAPPY.json").is_file())
        self.assertEqual(catalog_before, (self.fx.root / records.CATALOG_PATH).read_bytes())

        # read AFTER verify and BEFORE publish MUST fail closed with UNPUBLISHED!
        rc_rd_unpub, res_rd_unpub = self.fx.run_compile(stage="read", operation_id="OP-3C-HAPPY")
        self.assertEqual(2, rc_rd_unpub, res_rd_unpub)
        self.assertEqual(codec.ReasonCode.UNPUBLISHED.value, res_rd_unpub["diagnostics"][0]["reason_code"])

        # 6. publish: pushes catalog.v1.json LAST and completes!
        rc_pub, res_pub = self.fx.run_compile(stage="publish", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_pub, res_pub)
        self.assertTrue(res_pub["published"])
        self.assertEqual("complete", res_pub["state"])
        self.assertFalse(res_pub["readiness"])
        self.assertFalse(res_pub["runtime_verified"])
        self.assertFalse(res_pub["default_b_enabled"])
        self.assertNotEqual(catalog_before, (self.fx.root / records.CATALOG_PATH).read_bytes())

        # Cross-producer adoption.validate_operations MUST accept published task_compilation operations!
        adoption.validate_operations(journal.operation_inventory(self.fx.root))

        # Idempotent prepare and reserve replay with identical request MUST succeed after publish!
        rc_p_rep, res_p_rep = self.fx.run_compile(stage="prepare", operation_id="OP-3C-HAPPY", request_ref=req_path)
        self.assertEqual(0, rc_p_rep, res_p_rep)
        self.assertEqual(res_p["frozen_digest"], res_p_rep["frozen_digest"])
        rc_r_rep, res_r_rep = self.fx.run_compile(stage="reserve", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_r_rep, res_r_rep)
        self.assertEqual("reserved", res_r_rep["state"])

        # Verify triplet has semantic_review_tier, backlinks, and strict TaskJoinContext.
        master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        back = self.fx.read_json(".taskmaster/tasks/tasks_back.json")
        gameplay = self.fx.read_json(".taskmaster/tasks/tasks_gameplay.json")
        records.TaskJoinContext(master=master, back=back, gameplay=gameplay).indexes()
        for row in back + gameplay:
            self.assertIn("semantic_review_tier", row)
            self.assertTrue(any("Refs:" in acc for acc in row["acceptance"]))

        # Verify origins & catalog contain NO task status, preserve policy default_route=A and frozen_legacy_refs.
        origins = self.fx.read_json("docs/planning/b-route/task-origins.v1.json")
        self.assertTrue(origins["frozen_legacy_refs"])
        for row in origins["tasks"]:
            self.assertNotIn("status", row)
        policy = self.fx.read_json("docs/planning/b-route/policy.v1.json")
        self.assertEqual("A", policy["switch_boundary"]["default_route"])
        binding = self.fx.read_json("docs/planning/b-route/bindings/reward-plan/1.json")
        self.assertEqual("3C", binding["stage"])

        # Verify audit events written under logs/ci/b-route-task-compilation/<op>/events.jsonl.
        events_path = self.fx.root / "logs/ci/b-route-task-compilation/OP-3C-HAPPY/events.jsonl"
        self.assertTrue(events_path.is_file())
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        stages_logged = [e["stage"] for e in events]
        for expected_stage in ("prepare", "reserve", "apply", "verify", "publish"):
            self.assertIn(expected_stage, stages_logged)

        # 7. read succeeds
        rc_rd, res_rd = self.fx.run_compile(stage="read", operation_id="OP-3C-HAPPY")
        self.assertEqual(0, rc_rd, res_rd)
        self.assertEqual("committed", res_rd["status"])

        # Direct ungoverned edit to tasks.json MUST block read!
        tampered = copy.deepcopy(master)
        tampered["master"]["tasks"][0]["title"] = "Directly Tampered Title"
        self.fx.put_json(".taskmaster/tasks/tasks.json", tampered)
        rc_bad, res_bad = self.fx.run_compile(stage="read", operation_id="OP-3C-HAPPY")
        self.assertEqual(2, rc_bad)
        self.assertEqual("blocked", res_bad["status"])
        self.assertEqual(codec.ReasonCode.INPUT_STALE.value, res_bad["diagnostics"][0]["reason_code"])

    def test_shared_cross_plan_receipt_succession_preserves_old_plan_and_blocks_collision(self) -> None:
        # Mature NG-0010 historically covers RQ-COMBAT-1 so combat-plan can legally action=="reuse" it.
        back_seed = self.fx.read_json(".taskmaster/tasks/tasks_back.json")
        back_seed[0]["requirement_ids"] = ["RQ-LEGACY-1", "RQ-COMBAT-1"]
        back_seed[0]["semantic_refs"] = ["RQ-LEGACY-1", "RQ-COMBAT-1"]
        self.fx.put_json(".taskmaster/tasks/tasks_back.json", back_seed)

        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=True)

        # Compile Plan A (reward-plan) -> creates Tasks 11, 12.
        rc_pa, prev_a = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_pa, prev_a)
        req_a = self.fx.write_request(
            "logs/ci/test-inputs/req-a.json",
            operation_id="OP-PLAN-A",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev_a["report_path"],
        )
        for st in ("prepare", "reserve", "apply", "verify", "publish"):
            rc, out = self.fx.run_compile(stage=st, operation_id="OP-PLAN-A", request_ref=req_a if st == "prepare" else None)
            self.assertEqual(0, rc, out)

        # Compile Plan B (combat-plan) sharing Task 11 (via update) + creating a new Task 13 via change-intents!
        # Find the gameplay task ID created by Plan A so Plan B can share it in the same view.
        gp_rows = self.fx.read_json(".taskmaster/tasks/tasks_gameplay.json")
        shared_tid = gp_rows[0]["taskmaster_id"]
        shared_bid = gp_rows[0]["id"]
        intents_b = {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "combat-plan",
            "operations": [
                {
                    "action": "update",
                    "task_id": shared_tid,
                    "view": "gameplay",
                    "business_id": shared_bid,
                    "requirement_ids": ["RQ-COMBAT-1"],
                    "flow_ids": ["FLOW-COMBAT"],
                    "part_kinds": ["domain_rules", "csharp_adapter"],
                    "roles": ["producer"],
                    "scope": {"plan_id": "combat-plan", "target": "shared-handoff"},
                    "source_diff_evidence": ["docs/gdd/reward.md:7"],
                    "lineage": {"from_plan": "reward-plan", "to_plan": "combat-plan"},
                    "rationale": "Share gameplay handoff task across reward-plan and combat-plan.",
                },
                {
                    "action": "reuse",
                    "task_id": 10,
                    "view": "back",
                    "business_id": "NG-0010",
                    "requirement_ids": ["RQ-COMBAT-1"],
                    "flow_ids": ["FLOW-COMBAT"],
                    "part_kinds": ["csharp_adapter"],
                    "roles": ["consumer"],
                    "rationale": "Reuse mature NG-0010 under combat-plan with additive backlinks.",
                },
            ],
        }
        ci_b_path = "logs/ci/test-inputs/intents-b.json"
        self.fx.put_json(ci_b_path, intents_b)
        rc_pb, prev_b = self.fx.run_preview(
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            change_intents_ref=ci_b_path,
        )
        self.assertEqual(0, rc_pb, prev_b)
        req_b = self.fx.write_request(
            "logs/ci/test-inputs/req-b.json",
            operation_id="OP-PLAN-B",
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            preview_report_path=prev_b["report_path"],
            change_intents_ref=ci_b_path,
        )
        for st in ("prepare", "reserve", "apply", "verify", "publish"):
            rc, out = self.fx.run_compile(stage=st, operation_id="OP-PLAN-B", request_ref=req_b if st == "prepare" else None)
            self.assertEqual(0, rc, out)

        # Verify shared Task origins merged across Plan A & Plan B and task_index complete.
        origins = self.fx.read_json("docs/planning/b-route/task-origins.v1.json")
        catalog = self.fx.read_json("docs/planning/b-route/catalog.v1.json")
        shared_origin = next(r for r in origins["tasks"] if r["task_id"] == shared_tid)
        self.assertEqual({"reward-plan", "combat-plan"}, {p["entity_id"] for p in shared_origin["plan_refs"]})
        self.assertEqual({"reward-plan", "combat-plan"}, {b["entity_id"] for b in shared_origin["binding_refs"]})
        shared_idx = next(r for r in catalog["task_index"] if r["task_id"] == shared_tid)
        self.assertEqual({"reward-plan", "combat-plan"}, {p["entity_id"] for p in shared_idx["plan_refs"]})

        # Verify action=="reuse" on mature NG-0010 added combat-plan evidence_refs/source_refs backlinks.
        back_after_b = self.fx.read_json(".taskmaster/tasks/tasks_back.json")
        reused_ng10 = next(r for r in back_after_b if r["id"] == "NG-0010")
        self.assertIn("docs/planning/b-route/bindings/combat-plan/1.json", reused_ng10["evidence_refs"])
        self.assertIn("docs/planning/b-route/plans/combat-plan/1.json", reused_ng10["source_refs"])
        self.assertIn("RQ-COMBAT-1", reused_ng10["requirement_ids"])

        # CRITICAL: New receipt OP-PLAN-B succeeded the triplet projection; Plan A read MUST still succeed!
        rc_read_a, out_read_a = self.fx.run_compile(stage="read", operation_id="OP-PLAN-A")
        self.assertEqual(0, rc_read_a, out_read_a)
        rc_read_b, out_read_b = self.fx.run_compile(stage="read", operation_id="OP-PLAN-B")
        self.assertEqual(0, rc_read_b, out_read_b)

        # Mutating an exclusive Plan A task on disk after OP-PLAN-B publishes MUST fail closed in read_committed!
        clean_master_bytes = (self.fx.root / ".taskmaster/tasks/tasks.json").read_bytes()
        clean_gameplay_bytes = (self.fx.root / ".taskmaster/tasks/tasks_gameplay.json").read_bytes()
        exclusive_tids = [
            r["task_id"]
            for r in origins["tasks"]
            if {p["entity_id"] for p in r["plan_refs"]} == {"reward-plan"}
        ]
        self.assertTrue(exclusive_tids)
        tampered_master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        for row in tampered_master["master"]["tasks"]:
            if row["id"] == exclusive_tids[0]:
                row["title"] = "Tampered Exclusive Plan A Title"
        self.fx.put_json(".taskmaster/tasks/tasks.json", tampered_master)
        with self.assertRaises(codec.CodecError) as ctx_excl:
            commit.read_committed(self.fx.root, scope_ids=["scope-reward"])
        self.assertEqual(codec.ReasonCode.INPUT_STALE, ctx_excl.exception.diagnostic.reason_code)
        self.fx.put(".taskmaster/tasks/tasks.json", clean_master_bytes)

        # Mutating Plan A's evidence_refs on the shared gameplay task MUST also fail closed in read_committed!
        tampered_gp = self.fx.read_json(".taskmaster/tasks/tasks_gameplay.json")
        for row in tampered_gp:
            if row["taskmaster_id"] == shared_tid:
                row["evidence_refs"] = [r for r in row.get("evidence_refs", []) if "reward-plan" not in r]
        self.fx.put_json(".taskmaster/tasks/tasks_gameplay.json", tampered_gp)
        with self.assertRaises(codec.CodecError) as ctx_shared:
            commit.read_committed(self.fx.root, scope_ids=["scope-reward"])
        self.assertIn(
            ctx_shared.exception.diagnostic.reason_code,
            {codec.ReasonCode.INPUT_STALE, codec.ReasonCode.MAPPING_MISMATCH},
        )
        self.fx.put(".taskmaster/tasks/tasks_gameplay.json", clean_gameplay_bytes)
        restored = commit.read_committed(self.fx.root, scope_ids=["scope-reward"])
        self.assertEqual("committed", restored["status"])

        # Business ID collision MUST fail with CONFLICT!
        collide_intents = {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "combat-plan",
            "operations": [
                {
                    "action": "create",
                    "view": "back",
                    "proposed_business_id": "NG-0010",
                    "requirement_ids": ["RQ-COMBAT-1"],
                    "flow_ids": ["FLOW-COMBAT"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "rationale": "Attempt colliding business ID",
                }
            ],
        }
        ci_col_path = "logs/ci/test-inputs/intents-collide.json"
        self.fx.put_json(ci_col_path, collide_intents)
        rc_pc, prev_c = self.fx.run_preview(
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            change_intents_ref=ci_col_path,
        )
        # Either 3.1 preview blocks the collision or 3.2 compilation blocks with CONFLICT.
        if rc_pc == 0:
            req_c = self.fx.write_request(
                "logs/ci/test-inputs/req-collide.json",
                operation_id="OP-COLLIDE",
                plan_id="combat-plan",
                scope_id="scope-combat",
                audit_ref=self.audit_info["audit_ref_b"],
                preview_report_path=prev_c["report_path"],
                change_intents_ref=ci_col_path,
            )
            rc_col, out_col = self.fx.run_compile(stage="prepare", operation_id="OP-COLLIDE", request_ref=req_c)
            self.assertEqual(2, rc_col)
            self.assertEqual(codec.ReasonCode.CONFLICT.value, out_col["diagnostics"][0]["reason_code"])
        else:
            self.assertEqual(1, rc_pc)
            self.assertEqual(codec.ReasonCode.CONFLICT.value, prev_c["diagnostics"][0]["reason_code"])

    def test_live_status_merged_before_commit_freeze_and_blocked_after_freeze_or_def_change(self) -> None:
        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=False)
        rc_prev, prev = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_prev, prev)
        req_path = self.fx.write_request(
            "logs/ci/test-inputs/req-live.json",
            operation_id="OP-3C-LIVE",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev["report_path"],
        )
        rc_p, _ = self.fx.run_compile(stage="prepare", operation_id="OP-3C-LIVE", request_ref=req_path)
        self.assertEqual(0, rc_p)

        # Advance live Task 10 status BETWEEN prepare and reserve -> reserve MUST succeed!
        master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        master["master"]["tasks"][0]["status"] = "in-progress"
        self.fx.put_json(".taskmaster/tasks/tasks.json", master)
        back = self.fx.read_json(".taskmaster/tasks/tasks_back.json")
        back[0]["status"] = "in-progress"
        self.fx.put_json(".taskmaster/tasks/tasks_back.json", back)

        rc_r, res_r = self.fx.run_compile(stage="reserve", operation_id="OP-3C-LIVE")
        self.assertEqual(0, rc_r, res_r)

        # Advance live subtask status again BETWEEN reserve and apply (before commit.json exists)!
        master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        master["master"]["tasks"][0]["subtasks"][0]["status"] = "done"
        self.fx.put_json(".taskmaster/tasks/tasks.json", master)
        back = self.fx.read_json(".taskmaster/tasks/tasks_back.json")
        back[0]["subtasks"][0]["status"] = "done"
        self.fx.put_json(".taskmaster/tasks/tasks_back.json", back)

        # apply MUST accept lawful live status advance, merge BOTH changes into applied triplet, and seal into commit.json!
        rc_a, res_a = self.fx.run_compile(stage="apply", operation_id="OP-3C-LIVE")
        self.assertEqual(0, rc_a, res_a)
        after_master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        t10 = next(r for r in after_master["master"]["tasks"] if r["id"] == 10)
        self.assertEqual("in-progress", t10["status"])
        self.assertEqual("done", t10["subtasks"][0]["status"])

        # After commit.json is frozen, changing EVEN status MUST block verify/publish!
        after_master_mod = copy.deepcopy(after_master)
        after_master_mod["master"]["tasks"][0]["status"] = "done"
        self.fx.put_json(".taskmaster/tasks/tasks.json", after_master_mod)
        rc_v_blocked, res_v_blocked = self.fx.run_compile(stage="verify", operation_id="OP-3C-LIVE")
        self.assertEqual(2, rc_v_blocked)
        self.assertIn(res_v_blocked["diagnostics"][0]["reason_code"], {
            codec.ReasonCode.CONFLICT.value, codec.ReasonCode.INPUT_STALE.value,
        })

        # Restore exact sealed bytes -> verify and publish succeed, preserving merged live status!
        self.fx.put_json(".taskmaster/tasks/tasks.json", after_master)
        rc_v, _ = self.fx.run_compile(stage="verify", operation_id="OP-3C-LIVE")
        self.assertEqual(0, rc_v)
        rc_pub, res_pub = self.fx.run_compile(stage="publish", operation_id="OP-3C-LIVE")
        self.assertEqual(0, rc_pub, res_pub)
        final_master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        final_t10 = next(r for r in final_master["master"]["tasks"] if r["id"] == 10)
        self.assertEqual("in-progress", final_t10["status"])
        self.assertEqual("done", final_t10["subtasks"][0]["status"])

        # Definition change BEFORE apply MUST block!
        self.fx.populate_from_cached_3a(synthetic=False)
        self.setUp()
        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=False)
        rc_prev2, prev2 = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_prev2)
        req2 = self.fx.write_request(
            "logs/ci/test-inputs/req-def-drift.json",
            operation_id="OP-DEF-DRIFT",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev2["report_path"],
        )
        self.assertEqual(0, self.fx.run_compile(stage="prepare", operation_id="OP-DEF-DRIFT", request_ref=req2)[0])
        self.assertEqual(0, self.fx.run_compile(stage="reserve", operation_id="OP-DEF-DRIFT")[0])
        m2 = self.fx.read_json(".taskmaster/tasks/tasks.json")
        m2["master"]["tasks"][0]["title"] = "Changed Definition Title"
        self.fx.put_json(".taskmaster/tasks/tasks.json", m2)
        rc_drift, out_drift = self.fx.run_compile(stage="apply", operation_id="OP-DEF-DRIFT")
        self.assertEqual(2, rc_drift)
        self.assertEqual("blocked", out_drift["status"])

    def test_recover_roll_forward_noop_replay_and_different_content_conflict(self) -> None:
        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=True)
        rc_prev, prev = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_prev)
        req_path = self.fx.write_request(
            "logs/ci/test-inputs/req-rec.json",
            operation_id="OP-3C-REC",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev["report_path"],
        )
        self.assertEqual(0, self.fx.run_compile(stage="prepare", operation_id="OP-3C-REC", request_ref=req_path)[0])
        self.assertEqual(0, self.fx.run_compile(stage="reserve", operation_id="OP-3C-REC")[0])

        # Inject crash mid-apply after writing target 1 (partial physical state).
        def fail_mid_apply(label: str) -> None:
            if label == "after_target:1":
                raise OSError("synthetic crash mid-apply")

        with patch.object(commit, "_checkpoint", side_effect=fail_mid_apply):
            rc_crash, out_crash = self.fx.run_compile(stage="apply", operation_id="OP-3C-REC")
        self.assertEqual(2, rc_crash, out_crash)

        # recover-inspect reports partial state and next_stage='apply' (read-only).
        rc_ri, out_ri = self.fx.run_compile(stage="recover-inspect", operation_id="OP-3C-REC")
        self.assertEqual(0, rc_ri, out_ri)
        self.assertEqual("partial", out_ri["physical_state"])
        self.assertEqual("apply", out_ri["next_stage"])

        # recover rolls forward cleanly to published=True, state='complete'!
        rc_rec, out_rec = self.fx.run_compile(stage="recover", operation_id="OP-3C-REC")
        self.assertEqual(0, rc_rec, out_rec)
        self.assertTrue(out_rec["published"])
        self.assertEqual("complete", out_rec["state"])

        # Advance live status AFTER completion AND add another task via Plan B -> replay OP-3C-REC MUST return noop=True!
        master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        master["master"]["tasks"][0]["status"] = "done"
        self.fx.put_json(".taskmaster/tasks/tasks.json", master)

        # Capture scope-reward committed bundle BEFORE unrelated OP-3C-REC-B publishes!
        before_reward = commit.read_committed(self.fx.root, scope_ids=["scope-reward"])

        rc_pb, prev_b = self.fx.run_preview(
            plan_id="combat-plan", scope_id="scope-combat", audit_ref=self.audit_info["audit_ref_b"]
        )
        self.assertEqual(0, rc_pb, prev_b)
        req_b = self.fx.write_request(
            "logs/ci/test-inputs/req-rec-b.json",
            operation_id="OP-3C-REC-B",
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            preview_report_path=prev_b["report_path"],
        )
        for st in ("prepare", "reserve", "apply", "verify", "publish"):
            rc_s, out_s = self.fx.run_compile(stage=st, operation_id="OP-3C-REC-B", request_ref=req_b if st == "prepare" else None)
            self.assertEqual(0, rc_s, out_s)

        # Scope isolation (P-03): unrelated OP-3C-REC-B MUST NOT alter scope-reward's scope_ids or input_set_digest!
        after_reward = commit.read_committed(self.fx.root, scope_ids=["scope-reward"])
        self.assertEqual(before_reward["scope_ids"], after_reward["scope_ids"])
        self.assertEqual(before_reward["input_set_digest"], after_reward["input_set_digest"])

        # Replay completed OP-3C-REC via publish AND recover -> noop=True, live status preserved, Plan B task tolerated!
        rc_noop, out_noop = self.fx.run_compile(stage="publish", operation_id="OP-3C-REC")
        self.assertEqual(0, rc_noop, out_noop)
        self.assertTrue(out_noop["noop"])
        self.assertTrue(out_noop["published"])
        rc_noop2, out_noop2 = self.fx.run_compile(stage="recover", operation_id="OP-3C-REC")
        self.assertEqual(0, rc_noop2, out_noop2)
        self.assertTrue(out_noop2["noop"])
        final_master = self.fx.read_json(".taskmaster/tasks/tasks.json")
        self.assertEqual("done", next(r for r in final_master["master"]["tasks"] if r["id"] == 10)["status"])
        self.assertGreaterEqual(len(final_master["master"]["tasks"]), 4)

        # Same operation_id with different request content MUST fail with CONFLICT!
        diff_req = copy.deepcopy(self.fx.read_json(req_path))
        diff_req["reason"] = "Different content for same operation_id"
        diff_path = "logs/ci/test-inputs/req-rec-diff.json"
        self.fx.put_json(diff_path, diff_req)
        rc_diff, out_diff = self.fx.run_compile(stage="prepare", operation_id="OP-3C-REC", request_ref=diff_path)
        self.assertEqual(2, rc_diff)
        self.assertEqual(codec.ReasonCode.CONFLICT.value, out_diff["diagnostics"][0]["reason_code"])

        # Concurrent unapplied prepare: claim NG-0099 on reward-plan, verify second op reserves disjoint taskmaster_id
        # and fails with CONFLICT if proposing NG-0099 already claimed by the unapplied prepared op!
        ci_claim_a = "logs/ci/test-inputs/intents-claim-a.json"
        self.fx.put_json(ci_claim_a, {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "reward-plan",
            "operations": [{
                "action": "create",
                "view": "back",
                "proposed_business_id": "NG-0099",
                "requirement_ids": ["RQ-REWARD-1"],
                "flow_ids": ["FLOW-REWARD"],
                "part_kinds": ["binding"],
                "roles": ["producer"],
                "rationale": "Claim NG-0099 in unapplied prepared operation.",
            }],
        })
        rc_ca, prev_ca = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"], change_intents_ref=ci_claim_a,
        )
        self.assertEqual(0, rc_ca, prev_ca)
        req_ca = self.fx.write_request(
            "logs/ci/test-inputs/req-claim-a.json",
            operation_id="OP-CONC-A",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev_ca["report_path"],
            change_intents_ref=ci_claim_a,
        )
        rc_pa, out_pa = self.fx.run_compile(stage="prepare", operation_id="OP-CONC-A", request_ref=req_ca)
        self.assertEqual(0, rc_pa, out_pa)
        tids_a = {v["taskmaster_id"] for v in out_pa["allocations"]["task_ids"].values()}
        bids_a = {v["business_id"] for v in out_pa["allocations"]["task_ids"].values()}
        self.assertIn("NG-0099", bids_a)

        # Second operation on disjoint scope-combat proposing NG-0099 MUST fail with CONFLICT!
        ci_claim_col = "logs/ci/test-inputs/intents-claim-col.json"
        self.fx.put_json(ci_claim_col, {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "combat-plan",
            "operations": [{
                "action": "create",
                "view": "back",
                "proposed_business_id": "NG-0099",
                "requirement_ids": ["RQ-COMBAT-1"],
                "flow_ids": ["FLOW-COMBAT"],
                "part_kinds": ["csharp_adapter"],
                "roles": ["producer"],
                "rationale": "Collide with unapplied prepared NG-0099.",
            }],
        })
        rc_ccol, prev_ccol = self.fx.run_preview(
            plan_id="combat-plan", scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"], change_intents_ref=ci_claim_col,
        )
        self.assertEqual(0, rc_ccol, prev_ccol)
        req_ccol = self.fx.write_request(
            "logs/ci/test-inputs/req-claim-col.json",
            operation_id="OP-CONC-COL",
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            preview_report_path=prev_ccol["report_path"],
            change_intents_ref=ci_claim_col,
        )
        rc_pcol, out_pcol = self.fx.run_compile(stage="prepare", operation_id="OP-CONC-COL", request_ref=req_ccol)
        self.assertEqual(2, rc_pcol, out_pcol)
        self.assertEqual(codec.ReasonCode.CONFLICT.value, out_pcol["diagnostics"][0]["reason_code"])

        # Second operation proposing fresh NG-0100 reserves strictly disjoint taskmaster_id(s)!
        ci_claim_b = "logs/ci/test-inputs/intents-claim-b.json"
        self.fx.put_json(ci_claim_b, {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "combat-plan",
            "operations": [{
                "action": "create",
                "view": "back",
                "proposed_business_id": "NG-0100",
                "requirement_ids": ["RQ-COMBAT-1"],
                "flow_ids": ["FLOW-COMBAT"],
                "part_kinds": ["csharp_adapter"],
                "roles": ["producer"],
                "rationale": "Reserve disjoint taskmaster_id alongside unapplied OP-CONC-A.",
            }],
        })
        rc_cb, prev_cb = self.fx.run_preview(
            plan_id="combat-plan", scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"], change_intents_ref=ci_claim_b,
        )
        self.assertEqual(0, rc_cb, prev_cb)
        req_cb_path = self.fx.write_request(
            "logs/ci/test-inputs/req-claim-b.json",
            operation_id="OP-CONC-B",
            plan_id="combat-plan",
            scope_id="scope-combat",
            audit_ref=self.audit_info["audit_ref_b"],
            preview_report_path=prev_cb["report_path"],
            change_intents_ref=ci_claim_b,
        )
        _snap_b, frozen_b = compilation.build(self.fx.root, self.fx.read_json(req_cb_path))
        tids_b = {v["taskmaster_id"] for v in frozen_b["allocations"]["task_ids"].values()}
        self.assertTrue(tids_a.isdisjoint(tids_b))
        self.assertIn("NG-0100", {v["business_id"] for v in frozen_b["allocations"]["task_ids"].values()})

    def test_block_corrupt_preview_legacy_pending_frozen_a_scope_and_manifest_weakening(self) -> None:
        self.fx.write_committed_3b_single_or_dual(self.audit_info, dual=False)
        rc_prev, prev = self.fx.run_preview(
            plan_id="reward-plan", scope_id="scope-reward", audit_ref=self.audit_info["audit_ref"]
        )
        self.assertEqual(0, rc_prev)
        before_targets = self.fx.snapshot_targets()

        # 1. Corrupted / ok=False preview blocks with 6-field diagnostic and zero writes.
        bad_prev = copy.deepcopy(prev)
        bad_prev["ok"] = False
        bad_prev_path = "logs/ci/test-inputs/bad-preview.json"
        self.fx.put_json(bad_prev_path, bad_prev)
        req_bad = self.fx.write_request(
            "logs/ci/test-inputs/req-bad.json",
            operation_id="OP-BAD-PREV",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=bad_prev_path,
        )
        rc_b1, out_b1 = self.fx.run_compile(stage="prepare", operation_id="OP-BAD-PREV", request_ref=req_bad)
        self.assertEqual(2, rc_b1)
        self.assertEqual(before_targets, self.fx.snapshot_targets())
        diag = out_b1["diagnostics"][0]
        self.assertEqual(
            {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"},
            set(diag.keys()),
        )

        # 2. Legacy capability-apply.pending.json blocks with PENDING and zero writes!
        pending_path = "docs/planning/semantic-topology/capability-apply.pending.json"
        self.fx.put_json(pending_path, {"run_id": "cap-old", "journal_path": "logs/ci/capability-planning/cap-old/apply-journal.json"})
        self.fx.put_json("logs/ci/capability-planning/cap-old/run.json", {
            "schema_version": "newrouge.capability-planning-run.v1",
            "run_id": "cap-old",
            "phase": "prepared",
            "applied": False,
        })
        journal.create_journal(
            self.fx.root,
            self.fx.root / "logs/ci/capability-planning/cap-old/apply-journal.json",
            {self.fx.root / "docs/planning/semantic-topology/capabilities.v1.json": {"v": 1}},
            {},
            {"status": "applied"},
        )
        req_ok = self.fx.write_request(
            "logs/ci/test-inputs/req-pending.json",
            operation_id="OP-PENDING-BLK",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev["report_path"],
        )
        rc_b2, out_b2 = self.fx.run_compile(stage="prepare", operation_id="OP-PENDING-BLK", request_ref=req_ok)
        self.assertEqual(2, rc_b2)
        self.assertEqual(codec.ReasonCode.PENDING.value, out_b2["diagnostics"][0]["reason_code"])
        # Remove legacy pending artifacts for next sub-check.
        (self.fx.root / pending_path).unlink()
        (self.fx.root / "logs/ci/capability-planning/cap-old/apply-journal.json").unlink()

        # 3. Frozen legacy A chapter3-task-scope.json blocks creating new task IDs and stays untouched!
        scope_cfg_path = "docs/workflows/chapter3-task-scope.json"
        scope_cfg = {
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": ".taskmaster/tasks/tasks.json",
            "allowed_numeric_task_ids": [10],
            "expected_master_task_count": 1,
        }
        scope_raw = self.fx.put_json(scope_cfg_path, scope_cfg)
        req_scope = self.fx.write_request(
            "logs/ci/test-inputs/req-scope.json",
            operation_id="OP-SCOPE-BLK",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev["report_path"],
        )
        rc_b3, out_b3 = self.fx.run_compile(stage="prepare", operation_id="OP-SCOPE-BLK", request_ref=req_scope)
        self.assertEqual(2, rc_b3)
        self.assertEqual(codec.ReasonCode.CONFLICT.value, out_b3["diagnostics"][0]["reason_code"])
        self.assertEqual(scope_cfg_path, out_b3["diagnostics"][0]["resume_ref"])
        self.assertEqual(scope_raw, (self.fx.root / scope_cfg_path).read_bytes())
        (self.fx.root / scope_cfg_path).unlink()

        # 4. Manifest baseline weakening (or ungrounded retire) blocks before write and preserves manifest!
        manifest_path = "docs/testing/mvg/combat-reward-return.json"
        manifest_doc = {
            "schema_version": "mvg.manifest.v1",
            "flows": [
                {
                    "id": "FLOW-REWARD",
                    "task_ids": [10],
                    "requirement_ids": ["RQ-REWARD-1"],
                    "source_paths": ["docs/gdd/reward.md"],
                    "handoffs": [],
                }
            ],
            "tests": [],
        }
        manifest_raw = self.fx.put_json(manifest_path, manifest_doc)
        weak_intents = {
            "schema_version": task_preview.CHANGE_INTENTS_SCHEMA,
            "plan_id": "reward-plan",
            "operations": [
                {
                    "action": "retire",
                    "task_id": 10,
                    "view": "back",
                    "business_id": "NG-0010",
                    "scope": {"target": "retire"},
                    "source_diff_evidence": ["docs/gdd/reward.md:1"],
                    "lineage": {"reason": "ungrounded"},
                    "rationale": "Retire without authority while weakening manifest",
                }
            ],
            "proposed_manifest": {"schema_version": "mvg.manifest.v1", "flows": [], "tests": []},
        }
        ci_weak = "logs/ci/test-inputs/intents-weak.json"
        self.fx.put_json(ci_weak, weak_intents)
        rc_pw, prev_w = self.fx.run_preview(
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            manifest_ref=manifest_path,
            change_intents_ref=ci_weak,
        )
        self.assertEqual(1, rc_pw)
        req_w = self.fx.write_request(
            "logs/ci/test-inputs/req-weak.json",
            operation_id="OP-WEAK-BLK",
            plan_id="reward-plan",
            scope_id="scope-reward",
            audit_ref=self.audit_info["audit_ref"],
            preview_report_path=prev_w["report_path"],
            manifest_ref=manifest_path,
            change_intents_ref=ci_weak,
        )
        rc_b4, out_b4 = self.fx.run_compile(stage="prepare", operation_id="OP-WEAK-BLK", request_ref=req_w)
        self.assertEqual(2, rc_b4)
        self.assertEqual(manifest_raw, (self.fx.root / manifest_path).read_bytes())

    def test_dev_cli_builder_help_and_zero_bytecode_subprocess(self) -> None:
        parser = dev_cli.build_parser()
        parsed = parser.parse_args([
            "b-route-task-compile",
            "--root", str(self.fx.root),
            "--stage", "prepare",
            "--operation-id", "OP-CLI-1",
            "--request", "logs/ci/req.json",
        ])
        cmd = dev_cli_builders.build_b_route_task_compile_cmd(parsed)
        self.assertIn("--stage", cmd)
        self.assertIn("prepare", cmd)
        self.assertIn("--request", cmd)

        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_PY / "dev_cli.py"), "b-route-task-compile", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        for stage in compile_cli.STAGES:
            self.assertIn(stage, proc.stdout)

        # Verify zero __pycache__/.pyc under scripts/ after invoking without -B.
        bytecode = [
            p for p in (REPO_ROOT / "scripts").rglob("*")
            if p.name == "__pycache__" or p.suffix == ".pyc"
        ]
        self.assertEqual([], bytecode)


if __name__ == "__main__":
    unittest.main()
