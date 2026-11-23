"""Deterministic tests for Story 3.6 Stage-5 MVG obligations or legal other_verification binding.

Covers every row of the Story 3.6 I/O & Edge-Case Matrix (FLOW_BIND, NONFLOW_OK,
IMPACT_EXP, ROLE_DEP, DEDUP_RET), STAGE4_OBL_PREFIX preservation (no false
return_stage="4"), non-catalog & out_of_scope_future Flow handling without
MAPPING_MISMATCH, update_mvg_baseline delta + public-sync-journal crash/recover,
multi-plan shared-Task preservation, Story 2.8 compensation compatibility,
clean-clone extract_stage5_semantics (zero logs/), schema isolation, policy
anchoring, CLI/dev_cli/builder wiring, and zero __pycache__ generation.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_PY.parents[1]
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_adoption as adoption
import _b_route_adoption_review as adoption_review
import _b_route_chapter4_binding as ch4
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_compensation as compensation
import _b_route_input_set as input_set
import _b_route_operation_scope as op_scope
import _b_route_records as records
import _b_route_schema_resources as schema_resources
import _b_route_stage5_obligations as s5
import _b_route_task_resolver as task_resolver
import _mvg_manifest as mvg_manifest
import _planning_apply_journal as journal
import bind_b_route_stage5_obligations as s5_cli
import dev_cli_builders
import update_mvg_baseline


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


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


def _four_parts() -> list[dict]:
    return [
        {
            "kind": "domain_rules",
            "applicability": "applicable",
            "rationale": "Core deterministic domain rules.",
            "responsibilities": ["Core deterministic domain rules."],
        },
        {
            "kind": "csharp_adapter",
            "applicability": "not_applicable",
            "rationale": "Headless domain-only scope with no Godot adapter required.",
            "responsibilities": [],
        },
        {
            "kind": "binding",
            "applicability": "not_applicable",
            "rationale": "No Godot UI control bindings required.",
            "responsibilities": [],
        },
        {
            "kind": "scene",
            "applicability": "not_applicable",
            "rationale": "Headless domain-only scope with no Godot scene or UI obligation.",
            "responsibilities": [],
        },
    ]


class Stage5RepoFixture:
    """Isolated schema-validated B-route repo with committed 3B plan, Stage-4 binding, and MVG manifests."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.plan_id = "plan-reward"
        self.other_plan_id = "plan-combat"
        self.scope_id = "scope-reward"
        self.other_scope_id = "scope-combat"

    def cleanup(self) -> None:
        self._tmp.cleanup()

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

    def snapshot_tree(self, prefixes: tuple[str, ...]) -> dict[str, bytes]:
        snap: dict[str, bytes] = {}
        for prefix in prefixes:
            base = self.root / prefix
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    snap[p.relative_to(self.root).as_posix()] = p.read_bytes()
        return snap

    def build_committed_stage4(
        self,
        *,
        mode: str = "flow",  # "flow" | "nonflow" | "role_dep"
        prior_stage: str = "4",
        include_other_plan: bool = True,
        task101_status: str = "in-progress",
        task102_status: str = "pending",
        task103_status: str = "pending",
        source_gap: bool = False,
        nonflow_na_label: bool = False,
        nonflow_empty_rationale: bool = False,
        task101_deps: list[int] | None = None,
        task102_deps: list[int] | None = None,
        planned_test: bool = False,
        include_legacy_cumulative_flow: bool = False,
        self_lock_owner_in_manifest: bool = False,
        nonflow_acceptance_ref: str | None = None,
        task101_test_refs: list[str] | None = None,
    ) -> dict[str, object]:
        # 1. Sources & proofs.
        src_gdd = self.put("sources/reward-gdd.md", "# Reward Flow\n\nSelect reward and return to map.\n")
        source_entries = [{"path": "sources/reward-gdd.md", "source_type": "markdown", "sha256": codec.raw_digest(src_gdd)}]
        manifest_digest = codec.canonical_digest(source_entries)
        source_revision = "source-set:" + manifest_digest[7:31]
        src_manifest_raw = self.put_json(
            "sources/source-manifest.json",
            {
                "schema_version": "chapter3.source-manifest.v1",
                "source_revision": source_revision,
                "manifest_sha256": manifest_digest,
                "sources": source_entries,
            },
        )
        src_ledger_raw = self.put_json(
            "sources/source-blocks.json",
            {
                "schema_version": "newrouge.source-blocks.v1",
                "source_revision": source_revision,
                "source_manifest_sha256": manifest_digest,
                "blocks": [
                    {"block_id": "BLK-REWARD-1", "source_path": "sources/reward-gdd.md"},
                    {"block_id": "BLK-COMBAT-1", "source_path": "sources/reward-gdd.md"},
                    {"block_id": "BLK-TOOL-1", "source_path": "sources/reward-gdd.md"},
                ],
            },
        )
        proof_raw = self.put_json("evidence/admission-proof.json", {"selected_candidate": "cand-1"})
        other_verif_raw = self.put("docs/testing/nonflow-audit-checklist.md", "# Non-Flow Verification\n\nDeterministic static audit checklist.\n")
        retire_spec_raw = self.put("docs/adr/ADR-9999-retire-spec.md", "# ADR-9999\n\nReviewed specification authorizing obligation retirement.\n")

        # 2. Contracts, source files, tests, and overlay.
        self.put(
            "Game.Core/Contracts/EventTypes.cs",
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>Canonical events.</summary>\n"
            "public static class EventTypes\n{\n"
            '    public const string RewardOffered = "core.reward.offered";\n'
            "}\n",
        )
        cmd_raw = self.put(
            "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            "using System;\n\nnamespace Game.Core.Contracts.Reward;\n\n"
            "/// <summary>Select reward command.</summary>\n"
            "public sealed record SelectRewardCommand(string RunId, int OptionIndex);\n",
        )
        self.put("Game.Core/Services/RewardService.cs", "namespace Game.Core.Services;\npublic sealed class RewardService {}\n")
        self.put("Game.Core/Services/CombatService.cs", "namespace Game.Core.Services;\npublic sealed class CombatService {}\n")
        self.put("docs/workflows/standalone-tool.md", "# Standalone Tool Doc\n\nNo gameplay flow impact.\n")
        self.put("Game.Core.Tests/Reward/RewardFlowTests.cs", "public class RewardFlowTests {}\n")
        self.put("Game.Core.Tests/Reward/RewardExtraTests.cs", "public class RewardExtraTests {}\n")
        self.put("Game.Core.Tests/Combat/CombatFlowTests.cs", "public class CombatFlowTests {}\n")
        self.put("Game.Core.Tests/Legacy/LegacyMapTests.cs", "public class LegacyMapTests {}\n")
        self.put(
            "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
            "---\nPRD-ID: PRD-NEWROUGE-GAME-0001\nTitle: Reward\nStatus: Draft\nADRs: []\n---\n\n# Reward Overlay\n",
        )

        # 3. Taskmaster triplet (Tasks 101, 102, and optional 103 dedicated integration_only_owner).
        t101_deps = list(task101_deps or [])
        t102_deps = list(task102_deps if task102_deps is not None else ([101] if mode == "role_dep" else []))
        master_tasks = [
            {
                "id": 101,
                "title": "Reward producer task",
                "status": task101_status,
                "dependencies": t101_deps,
                "details": "Labels: mvg:N/A\nProducer task details." if nonflow_na_label else "Producer task details.",
                "contractRefs": ["core.reward.offered"] if mode != "nonflow" else [],
                "overlay": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "testStrategy": "xUnit domain tests",
            },
            {
                "id": 102,
                "title": "Reward consumer task",
                "status": task102_status,
                "dependencies": t102_deps,
                "details": "Consumer task details.",
                "contractRefs": ["core.reward.offered"] if mode != "nonflow" else [],
                "overlay": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "testStrategy": "xUnit domain tests",
            },
        ]
        t101_acc_ref = (
            nonflow_acceptance_ref
            if nonflow_acceptance_ref is not None
            else (
                "docs/testing/nonflow-audit-checklist.md"
                if mode == "nonflow"
                else "Game.Core.Tests/Reward/RewardFlowTests.cs"
            )
        )
        back_rows = [
            {
                "id": "NG-0101",
                "taskmaster_id": 101,
                "title": "Reward producer task",
                "status": task101_status,
                "depends_on": [f"NG-0{d}" for d in t101_deps] if t101_deps else [],
                "acceptance": [f"Produce reward offer. Refs: {t101_acc_ref}"],
                "contractRefs": ["core.reward.offered"] if mode != "nonflow" else [],
                "overlay_refs": ["docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"],
                **({"test_refs": list(task101_test_refs)} if task101_test_refs else {}),
            },
            {
                "id": "NG-0102",
                "taskmaster_id": 102,
                "title": "Reward consumer task",
                "status": task102_status,
                "depends_on": [f"NG-0{d}" for d in t102_deps] if t102_deps else [],
                "acceptance": ["Consume reward offer. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs"],
                "contractRefs": ["core.reward.offered"] if mode != "nonflow" else [],
                "overlay_refs": ["docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"],
            },
        ]
        if mode == "role_dep":
            master_tasks.append(
                {
                    "id": 103,
                    "title": "Reward integration verification owner",
                    "status": task103_status,
                    "dependencies": [101, 102],
                    "details": "Integration-only verification owner; no runtime API required.",
                    "contractRefs": [],
                    "overlay": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                    "testStrategy": "MVG integration verification",
                }
            )
            back_rows.append(
                {
                    "id": "NG-0103",
                    "taskmaster_id": 103,
                    "title": "Reward integration verification owner",
                    "status": task103_status,
                    "depends_on": ["NG-0101", "NG-0102"],
                    "acceptance": ["Verify reward handoff integration. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs"],
                    "contractRefs": [],
                    "overlay_refs": ["docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"],
                }
            )
        self.put_json(".taskmaster/tasks/tasks.json", {"master": {"tasks": master_tasks}})
        self.put_json(".taskmaster/tasks/tasks_back.json", back_rows)
        self.put_json(".taskmaster/tasks/tasks_gameplay.json", [])

        # 4. MVG manifest(s).
        owner_tid = 103 if mode == "role_dep" else 101
        flow_task_ids = [101, 102, 103] if mode == "role_dep" else [101, 102]
        blockers = []
        if task101_status != "done":
            blockers.append(101)
        if task102_status != "done":
            blockers.append(102)
        if self_lock_owner_in_manifest and mode == "role_dep":
            blockers.append(103)

        manifest_flows = [
            {
                "id": "flow-reward-select",
                "task_ids": flow_task_ids,
                "outcome": "Player selects reward and returns to map.",
                "source_paths": ["Game.Core/Services/RewardService.cs"],
                "test_ids": ["test-reward-flow"],
                "handoffs": [
                    {
                        "producer_task": 101,
                        "consumer_task": 102,
                        "owner_task": owner_tid,
                        "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                        "behavior": "SelectRewardCommand hands locked reward choice to map return.",
                        "test_ids": ["test-reward-flow"],
                    }
                ],
            }
        ]
        manifest_tests = [
            {
                "id": "test-reward-flow",
                "kind": "dotnet",
                "evidence_level": "domain-integration",
                "path": "Game.Core.Tests/Reward/RewardFlowTests.cs",
                "selector": "RewardFlowTests",
                "state": "planned" if planned_test else "implemented",
                "min_tests": 1,
            }
        ]
        if include_legacy_cumulative_flow:
            manifest_flows.append(
                {
                    "id": "flow-legacy-map",
                    "task_ids": [101, 102],
                    "outcome": "Existing cumulative map navigation regression flow.",
                    "source_paths": ["Game.Core/Services/CombatService.cs"],
                    "test_ids": ["test-legacy-map"],
                    "handoffs": [
                        {
                            "producer_task": 101,
                            "consumer_task": 102,
                            "owner_task": 101,
                            "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                            "behavior": "Map return continuity regression check.",
                            "test_ids": ["test-legacy-map"],
                        }
                    ],
                }
            )
            manifest_tests.append(
                {
                    "id": "test-legacy-map",
                    "kind": "dotnet",
                    "evidence_level": "domain-integration",
                    "path": "Game.Core.Tests/Legacy/LegacyMapTests.cs",
                    "selector": "LegacyMapTests",
                    "state": "implemented",
                    "min_tests": 1,
                }
            )

        mvg_manifest_doc = {
            "schema_version": mvg_manifest.SCHEMA,
            "mvg_id": "mvg-reward-baseline",
            "coverage": {
                "mode": "critical" if len(manifest_flows) >= 2 else "pilot",
                "scope_id": "reward-scope",
                "required_flow_ids": [f["id"] for f in manifest_flows],
                "blocking_task_ids": sorted(blockers),
                "excluded_claims": ["Manual animation polish verified separately."],
            },
            "flows": manifest_flows,
            "tests": manifest_tests,
        }
        mvg_manifest_path = "docs/testing/mvg/reward-baseline.json"
        mvg_manifest_raw = self.put_json(mvg_manifest_path, mvg_manifest_doc)

        # 5. Formal B-route records: policy, plans, stage-4 bindings, origins, commit receipt, catalog.
        policy_doc = {
            "schema_version": "newrouge.b-route-policy.v1",
            "policy_id": "policy-main",
            "policy_revision": 1,
            "switch_boundary": {
                "default_route": "A",
                "a_write_allowed": True,
                "allowed_a_operations": ["resume-task"],
                "authority_refs": [],
            },
            "frozen_a_refs": [],
        }
        policy_path = records.BASE + "policy.v1.json"
        policy_raw = self.put_json(policy_path, policy_doc)
        policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy-main", 1, policy_raw)

        src_manifest_owned = _owned_ref("source_manifest", "sources/source-manifest.json", [("sources/source-manifest.json", src_manifest_raw)])
        src_ledger_owned = _owned_ref("source_ledger", "sources/source-blocks.json", [("sources/source-blocks.json", src_ledger_raw)])
        proof_owned = _owned_ref("planning_proof", "evidence/admission-proof.json", [("evidence/admission-proof.json", proof_raw)])
        other_verif_owned = _owned_ref(
            "other_verification",
            "docs/testing/nonflow-audit-checklist.md",
            [("docs/testing/nonflow-audit-checklist.md", other_verif_raw)],
        )
        cmd_owned = _owned_ref(
            "contract",
            "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", cmd_raw)],
        )

        # Primary plan (plan-reward).
        if mode == "nonflow":
            rat = "N/A" if nonflow_empty_rationale else "Deterministic documentation/tooling rule verified by static audit checklist with zero gameplay Flow impact."
            disp_kind = "source_gap" if source_gap else "other_verification"
            verif_row = (
                {
                    "requirement_id": "REQ-TOOL-1",
                    "disposition": "source_gap",
                    "flow_id": None,
                    "rationale": "Unresolved source gap.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
                if source_gap
                else {
                    "requirement_id": "REQ-TOOL-1",
                    "disposition": "other_verification",
                    "flow_id": None,
                    "rationale": rat,
                    "sink_id": "SINK-DOC-AUDIT",
                    "verification_ref": "docs/testing/nonflow-audit-checklist.md",
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            )
            app_row = {
                "requirement_id": "REQ-TOOL-1",
                "disposition": disp_kind,
                "rationale": "Unresolved source gap." if source_gap else rat,
                "other_verification_refs": [] if source_gap else [other_verif_owned],
            }
            plan_doc = {
                "schema_version": "newrouge.b-route-plan.v1",
                "plan_id": self.plan_id,
                "revision": 1,
                "lineage": {
                    "previous_plan_ref": None,
                    "change_summary": "Initial 3B non-flow plan adoption.",
                    "identity_alignment": [],
                },
                "source_identity": {
                    "source_revision": source_revision,
                    "source_manifest_digest": manifest_digest,
                    "manifest_ref": src_manifest_owned,
                    "ledger_ref": src_ledger_owned,
                },
                "adoption_proof_refs": [proof_owned],
                "requirements": [
                    {
                        "requirement_id": "REQ-TOOL-1",
                        "source_block_ids": ["BLK-TOOL-1"],
                        "acceptance_intent": "Standalone deterministic audit check.",
                        "non_task_sinks": ["SINK-DOC-AUDIT"],
                    }
                ],
                "definitions": {"flows": [], "commands": [], "states": []},
                "logical_references": [],
                "requirement_verification": [verif_row],
                "requirement_route_memberships": [],
                "requirement_evidence": [],
                "evidence_source_refs": [] if source_gap else [other_verif_owned],
                "coverage_table": [{k: v for k, v in verif_row.items() if k != "evidence_ids"}],
                "applicability": [app_row],
            }
            s4_obl_meta = {"stage": "4", "task_ids": [101], "test_ids": []}
            prior_binding_doc = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": self.plan_id,
                "binding_revision": 1,
                "plan_ref": {},
                "stage": prior_stage,
                "task_mappings": [
                    {
                        "task_id": 101,
                        "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                        "requirement_ids": ["REQ-TOOL-1"],
                        "flow_ids": [],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "obligation_ids": ["OBL-TOOL-1"],
                    }
                ],
                "parts": _four_parts(),
                "implementation_objects": [],
                "obligations": [
                    {
                        "id": "OBL-TOOL-1",
                        "requirement_ids": ["REQ-TOOL-1"],
                        "flow_ids": [],
                        "test_ids": [],
                        "responsibility": f"Verify non-flow checklist. | {ch4.STAGE4_OBL_PREFIX}{ch4._compact_json(s4_obl_meta)}",
                        "verification_refs": [] if source_gap else [other_verif_owned],
                    }
                ],
                "manifest_refs": [],
                "other_verification_refs": [] if source_gap else [other_verif_owned],
            }
        else:
            # Flow or Role-Dep plan.
            verif_row = {
                "requirement_id": "REQ-REWARD-1",
                "disposition": "flow",
                "flow_id": "flow-reward-select",
                "rationale": "Verified by reward selection MVG flow.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": ["EV-REWARD-1"],
            }
            plan_doc = {
                "schema_version": "newrouge.b-route-plan.v1",
                "plan_id": self.plan_id,
                "revision": 1,
                "lineage": {
                    "previous_plan_ref": None,
                    "change_summary": "Initial 3B reward plan adoption.",
                    "identity_alignment": [],
                },
                "source_identity": {
                    "source_revision": source_revision,
                    "source_manifest_digest": manifest_digest,
                    "manifest_ref": src_manifest_owned,
                    "ledger_ref": src_ledger_owned,
                },
                "adoption_proof_refs": [proof_owned],
                "requirements": [
                    {
                        "requirement_id": "REQ-REWARD-1",
                        "source_block_ids": ["BLK-REWARD-1"],
                        "acceptance_intent": "Player selects one locked reward option and returns to map.",
                        "non_task_sinks": [],
                    }
                ],
                "definitions": {
                    "flows": [
                        {
                            "id": "flow-reward-select",
                            "requirement_ids": ["REQ-REWARD-1"],
                            "entry": "RewardScreen.Enter",
                            "entry_condition": "Combat victory offers locked rewards.",
                            "success_end": "MapScreen.Return",
                            "branches": [
                                {"kind": "failure", "rationale": "Reject invalid choice.", "description": "Keep reward screen open."},
                                {"kind": "cancel", "rationale": "Allow skip reward.", "description": "Close without granting card."},
                                {"kind": "return", "rationale": "Return to map node.", "description": "Navigate back to map."},
                            ],
                            "handoffs": [],
                            "state_owners": [
                                {
                                    "kind": "state",
                                    "definition_id": "state-reward-offer",
                                    "owner_plan_id": self.plan_id,
                                    "owner_revision": 1,
                                }
                            ],
                            "parts": _four_parts(),
                            "observable_result": "Deterministic reward choice applied and returned to map.",
                            "verification_targets": ["RewardFlowTests"],
                            "loops": [],
                        }
                    ],
                    "commands": [
                        {
                            "id": "cmd-select-reward",
                            "requirement_ids": ["REQ-REWARD-1"],
                            "responsibility": "Select reward option command.",
                            "uses": [
                                {
                                    "kind": "state",
                                    "definition_id": "state-reward-offer",
                                    "owner_plan_id": self.plan_id,
                                    "owner_revision": 1,
                                }
                            ],
                        }
                    ],
                    "states": [
                        {
                            "id": "state-reward-offer",
                            "requirement_ids": ["REQ-REWARD-1"],
                            "responsibility": "Locked reward offer read-only state.",
                            "uses": [],
                        }
                    ],
                },
                "logical_references": [],
                "requirement_verification": [verif_row],
                "requirement_route_memberships": [
                    {
                        "requirement_id": "REQ-REWARD-1",
                        "flow_id": "flow-reward-select",
                        "observable_role": "Observe reward selection and map return.",
                    }
                ],
                "requirement_evidence": [
                    {
                        "requirement_id": "REQ-REWARD-1",
                        "evidence_id": "EV-REWARD-1",
                        "kind": "implementation_reference",
                        "source_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                        "covered_behavior": "Locked reward selection command contract.",
                        "flow_ids": ["flow-reward-select"],
                        "test_ids": ["test-reward-flow"],
                    }
                ],
                "evidence_source_refs": [cmd_owned],
                "coverage_table": [{k: v for k, v in verif_row.items() if k != "evidence_ids"}],
                "applicability": [
                    {
                        "requirement_id": "REQ-REWARD-1",
                        "disposition": "flow",
                        "rationale": "Verified by reward selection MVG flow.",
                        "other_verification_refs": [],
                    }
                ],
            }
            s4_obl_meta = {"stage": "4", "task_ids": flow_task_ids, "test_ids": ["test-reward-flow"]}
            cmd_lifecycle = f"{ch4.STAGE4_LIFECYCLE_PREFIX}" + ch4._compact_json(
                {
                    "owner": "RewardService",
                    "preconditions": ["offer locked"],
                    "postconditions": ["reward granted"],
                    "invariants": ["single pick"],
                    "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                }
            )
            t_mappings = [
                {
                    "task_id": 101,
                    "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": ["OBL-REWARD-1"],
                },
                {
                    "task_id": 102,
                    "view_refs": [{"view": "back", "business_id": "NG-0102"}],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["consumer"],
                    "obligation_ids": ["OBL-REWARD-1"],
                },
            ]
            if mode == "role_dep":
                t_mappings.append(
                    {
                        "task_id": 103,
                        "view_refs": [{"view": "back", "business_id": "NG-0103"}],
                        "requirement_ids": [],
                        "flow_ids": ["flow-reward-select"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["integration_only_owner"],
                        "obligation_ids": ["OBL-REWARD-1"],
                    }
                )
            prior_binding_doc = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": self.plan_id,
                "binding_revision": 1,
                "plan_ref": {},
                "stage": prior_stage,
                "task_mappings": t_mappings,
                "parts": _four_parts(),
                "implementation_objects": [
                    {
                        "id": "cmd-select-reward",
                        "kind": "command",
                        "availability": "existing",
                        "responsible_task_ids": [101],
                        "expected_type": "SelectRewardCommand",
                        "lifecycle": cmd_lifecycle,
                        "target_ref": cmd_owned,
                        "later_checks": ["type", "compile"],
                    }
                ],
                "obligations": [
                    {
                        "id": "OBL-REWARD-1",
                        "requirement_ids": ["REQ-REWARD-1"],
                        "flow_ids": ["flow-reward-select"],
                        "test_ids": ["test-reward-flow"],
                        "responsibility": f"Verify reward flow handoff. | {ch4.STAGE4_OBL_PREFIX}{ch4._compact_json(s4_obl_meta)}",
                        "verification_refs": [],
                    }
                ],
                "manifest_refs": [],
                "other_verification_refs": [],
            }

        plan_path = records.BASE + f"plans/{self.plan_id}/1.json"
        plan_raw = self.put_json(plan_path, plan_doc)
        plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", self.plan_id, 1, plan_raw)
        prior_binding_doc["plan_ref"] = plan_ref
        prior_binding_path = records.BASE + f"bindings/{self.plan_id}/1.json"
        prior_binding_raw = self.put_json(prior_binding_path, prior_binding_doc)
        prior_binding_ref = _typed_ref(prior_binding_path, "newrouge.b-route-binding.v1", self.plan_id, 1, prior_binding_raw)

        # Optional sibling plan sharing Task 101 to test multi-plan preservation.
        plan_refs = [plan_ref]
        binding_refs = [prior_binding_ref]
        scope_heads = []
        def_owners = []
        for plural, kind in (("flows", "flow"), ("commands", "command"), ("states", "state")):
            for d in plan_doc["definitions"][plural]:
                def_owners.append({"kind": kind, "definition_id": d["id"], "plan_ref": plan_ref})

        other_plan_ref = None
        other_binding_ref = None
        if include_other_plan:
            c_verif = {
                "requirement_id": "REQ-COMBAT-1",
                "disposition": "flow",
                "flow_id": "flow-combat-finish",
                "rationale": "Combat finish flow.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": ["EV-COMBAT-1"],
            }
            other_plan_doc = {
                "schema_version": "newrouge.b-route-plan.v1",
                "plan_id": self.other_plan_id,
                "revision": 1,
                "lineage": {
                    "previous_plan_ref": None,
                    "change_summary": "Initial 3B combat plan adoption.",
                    "identity_alignment": [],
                },
                "source_identity": {
                    "source_revision": source_revision,
                    "source_manifest_digest": manifest_digest,
                    "manifest_ref": src_manifest_owned,
                    "ledger_ref": src_ledger_owned,
                },
                "adoption_proof_refs": [proof_owned],
                "requirements": [
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "source_block_ids": ["BLK-COMBAT-1"],
                        "acceptance_intent": "Combat completes cleanly.",
                        "non_task_sinks": [],
                    }
                ],
                "definitions": {
                    "flows": [
                        {
                            "id": "flow-combat-finish",
                            "requirement_ids": ["REQ-COMBAT-1"],
                            "entry": "Combat.Start",
                            "entry_condition": "Combat encounter begins.",
                            "success_end": "Combat.Victory",
                            "branches": [
                                {"kind": "failure", "rationale": "Player defeated.", "description": "Game over screen."},
                                {"kind": "cancel", "rationale": "Abandon run.", "description": "Return to main menu."},
                                {"kind": "return", "rationale": "Victory transition.", "description": "Proceed to reward offer."},
                            ],
                            "handoffs": [],
                            "state_owners": [],
                            "parts": _four_parts(),
                            "observable_result": "Combat ends and offers rewards.",
                            "verification_targets": ["CombatFlowTests"],
                            "loops": [],
                        }
                    ],
                    "commands": [],
                    "states": [],
                },
                "logical_references": [],
                "requirement_verification": [c_verif],
                "requirement_route_memberships": [
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "flow_id": "flow-combat-finish",
                        "observable_role": "Observe combat completion.",
                    }
                ],
                "requirement_evidence": [
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "evidence_id": "EV-COMBAT-1",
                        "kind": "implementation_reference",
                        "source_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                        "covered_behavior": "Combat finish transition contract.",
                        "flow_ids": ["flow-combat-finish"],
                        "test_ids": ["test-reward-flow"],
                    }
                ],
                "evidence_source_refs": [cmd_owned],
                "coverage_table": [{k: v for k, v in c_verif.items() if k != "evidence_ids"}],
                "applicability": [
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "disposition": "flow",
                        "rationale": "Combat finish flow.",
                        "other_verification_refs": [],
                    }
                ],
            }
            other_plan_path = records.BASE + f"plans/{self.other_plan_id}/1.json"
            other_plan_raw = self.put_json(other_plan_path, other_plan_doc)
            other_plan_ref = _typed_ref(other_plan_path, "newrouge.b-route-plan.v1", self.other_plan_id, 1, other_plan_raw)
            other_binding_doc = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": self.other_plan_id,
                "binding_revision": 1,
                "plan_ref": other_plan_ref,
                "stage": "4",
                "task_mappings": [
                    {
                        "task_id": 101,
                        "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                        "requirement_ids": ["REQ-COMBAT-1"],
                        "flow_ids": ["flow-combat-finish"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "obligation_ids": ["OBL-COMBAT-1"],
                    }
                ],
                "parts": _four_parts(),
                "implementation_objects": [],
                "obligations": [
                    {
                        "id": "OBL-COMBAT-1",
                        "requirement_ids": ["REQ-COMBAT-1"],
                        "flow_ids": ["flow-combat-finish"],
                        "test_ids": [],
                        "responsibility": "Combat finish handoff.",
                        "verification_refs": [],
                    }
                ],
                "manifest_refs": [],
                "other_verification_refs": [],
            }
            other_binding_path = records.BASE + f"bindings/{self.other_plan_id}/1.json"
            other_binding_raw = self.put_json(other_binding_path, other_binding_doc)
            other_binding_ref = _typed_ref(other_binding_path, "newrouge.b-route-binding.v1", self.other_plan_id, 1, other_binding_raw)
            plan_refs.append(other_plan_ref)
            binding_refs.append(other_binding_ref)
            def_owners.append({"kind": "flow", "definition_id": "flow-combat-finish", "plan_ref": other_plan_ref})

        # Task origins & task_index.
        task_index_map: dict[int, dict] = {}
        for bref, bdoc in [(prior_binding_ref, prior_binding_doc)] + (
            [(other_binding_ref, other_binding_doc)] if include_other_plan else []
        ):
            for m in bdoc["task_mappings"]:
                row = task_index_map.setdefault(m["task_id"], {"task_id": m["task_id"], "plan_refs": [], "binding_refs": []})
                if bdoc["plan_ref"] not in row["plan_refs"]:
                    row["plan_refs"].append(bdoc["plan_ref"])
                if bref not in row["binding_refs"]:
                    row["binding_refs"].append(bref)

        origins_doc = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": [
                {
                    "task_id": tid,
                    "source_refs": [src_manifest_owned],
                    "plan_refs": row["plan_refs"],
                    "binding_refs": row["binding_refs"],
                }
                for tid, row in sorted(task_index_map.items())
            ],
            "frozen_legacy_refs": [],
        }
        origins_path = records.BASE + "task-origins.v1.json"
        origins_raw = self.put_json(origins_path, origins_doc)
        origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

        # Bootstrap commit receipt + catalog.
        boot_op_id = "OP-BOOT-STAGE4"
        boot_targets = [
            {"path": policy_path, "before_digest": None, "after_digest": codec.raw_digest(policy_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(policy_raw)},
            {"path": origins_path, "before_digest": None, "after_digest": codec.raw_digest(origins_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(origins_raw)},
            {"path": plan_path, "before_digest": None, "after_digest": codec.raw_digest(plan_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(plan_raw)},
            {"path": prior_binding_path, "before_digest": None, "after_digest": codec.raw_digest(prior_binding_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(prior_binding_raw)},
        ]
        boot_scopes = [self.scope_id]
        if include_other_plan:
            boot_targets.extend([
                {"path": other_plan_path, "before_digest": None, "after_digest": codec.raw_digest(other_plan_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(other_plan_raw)},
                {"path": other_binding_path, "before_digest": None, "after_digest": codec.raw_digest(other_binding_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(other_binding_raw)},
            ])
            boot_scopes.append(self.other_scope_id)

        resolved_defs = (
            [{"kind": "state", "definition_id": "state-reward-offer", "plan_ref": plan_ref}]
            if mode != "nonflow"
            else []
        )
        receipt_doc = {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": boot_op_id,
            "revision": 1,
            "operation_digest": codec.canonical_digest({"boot": boot_op_id}),
            "scopes": sorted(boot_scopes),
            "authority": [],
            "targets": boot_targets,
            "plan_refs": plan_refs,
            "binding_refs": binding_refs,
            "resolved_definitions": resolved_defs,
            "result": {"target_paths": [t["path"] for t in boot_targets], "scope_ids": sorted(boot_scopes)},
        }
        receipt_path = records.BASE + f"commits/{boot_op_id}.json"
        receipt_raw = self.put_json(receipt_path, receipt_doc)
        receipt_ref = _typed_ref(receipt_path, "newrouge.b-route-commit.v1", boot_op_id, 1, receipt_raw)

        scope_heads.append(
            {"scope_id": self.scope_id, "plan_refs": [plan_ref], "binding_refs": [prior_binding_ref], "receipt_ref": receipt_ref}
        )
        if include_other_plan:
            scope_heads.append(
                {"scope_id": self.other_scope_id, "plan_refs": [other_plan_ref], "binding_refs": [other_binding_ref], "receipt_ref": receipt_ref}
            )

        catalog_doc = {
            "schema_version": "newrouge.b-route-catalog.v1",
            "catalog_id": "catalog",
            "revision": 1,
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "scope_heads": scope_heads,
            "definition_owners": sorted(def_owners, key=lambda r: (r["kind"], r["definition_id"])),
            "task_index": [task_index_map[k] for k in sorted(task_index_map)],
        }
        catalog_raw = self.put_json(records.CATALOG_PATH, catalog_doc)

        return {
            "mvg_manifest_path": mvg_manifest_path,
            "mvg_manifest_raw": mvg_manifest_raw,
            "mvg_manifest_doc": mvg_manifest_doc,
            "mvg_manifest_ref": _owned_ref("manifest", mvg_manifest_path, [(mvg_manifest_path, mvg_manifest_raw)]),
            "other_verif_ref": other_verif_owned,
            "retire_spec_path": "docs/adr/ADR-9999-retire-spec.md",
            "retire_spec_raw": retire_spec_raw,
            "plan_ref": plan_ref,
            "prior_binding_ref": prior_binding_ref,
            "other_plan_ref": other_plan_ref,
            "other_binding_ref": other_binding_ref,
            "catalog_raw": catalog_raw,
        }


def _run_full_lifecycle(fx: Stage5RepoFixture, op_id: str, request_doc: dict, *, include_preview: bool = True) -> dict:
    req_rel = f"logs/ci/test-requests/{op_id}.json"
    fx.put_json(req_rel, request_doc)
    prev = s5.preview(fx.root, operation_id=op_id, request_ref=req_rel) if include_preview else None
    prep = s5.prepare(fx.root, operation_id=op_id, request_ref=req_rel)
    res = s5.reserve(fx.root, operation_id=op_id)
    insp = s5.inspect(fx.root, operation_id=op_id)
    applied = commit.execute(fx.root, operation_id=op_id, stage="apply")
    verified = commit.execute(fx.root, operation_id=op_id, stage="verify")
    published = commit.execute(fx.root, operation_id=op_id, stage="publish")
    out = {
        "prepare": prep,
        "reserve": res,
        "inspect": insp,
        "apply": applied,
        "verify": verified,
        "publish": published,
    }
    if prev is not None:
        out["preview"] = prev
    return out


class Stage5ObligationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Stage5RepoFixture()

    def tearDown(self) -> None:
        self.fx.cleanup()

    def _flow_request(self, op_id: str, assets: dict, *, extra_obligations=None, manifest_deltas=None) -> dict:
        obls = [
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
        ]
        if extra_obligations:
            obls.extend(extra_obligations)
        req = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_id,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [copy.deepcopy(assets["mvg_manifest_ref"])],
            "other_verification_refs": [],
            "obligations": obls,
        }
        if manifest_deltas is not None:
            req["manifest_deltas"] = manifest_deltas
        return req

    # ------------------------------------------------------------------
    # Matrix Row 1: FLOW_BIND (happy path, delta+public-sync+recover, errors)
    # ------------------------------------------------------------------

    def test_flow_bind_full_lifecycle_conserves_stage4_and_multiplan_without_false_stage4_drift(self) -> None:
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=True)
        # Capture Story 3.5 baseline BEFORE Stage 5 (at Stage 4).
        baseline_101 = input_set.resolve_input_set(self.fx.root, 101)
        self.assertTrue(baseline_101["ok"])

        op_id = "OP-S5-FLOW-001"
        req = self._flow_request(op_id, assets)
        req_rel = f"logs/ci/test-requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        # Preview must be 100% pure read-only zero-write on repo planning/task files.
        before_snap = self.fx.snapshot_tree(("docs/planning/b-route", ".taskmaster", "docs/testing/mvg"))
        prev = s5.preview(self.fx.root, operation_id=op_id, request_ref=req_rel)
        after_prev_snap = self.fx.snapshot_tree(("docs/planning/b-route", ".taskmaster", "docs/testing/mvg"))
        self.assertEqual(before_snap, after_prev_snap)
        self.assertEqual(prev["status"], "previewed")
        self.assertFalse(prev["readiness"])
        self.assertFalse(prev["runtime_verified"])
        self.assertFalse(prev["default_b_enabled"])
        self.assertIn("101", prev["task_input_set_digests"])

        # Run full lifecycle to publish.
        results = _run_full_lifecycle(self.fx, op_id, req)
        self.assertTrue(results["publish"]["published"])
        for stage_res in results.values():
            self.assertFalse(stage_res["readiness"])
            self.assertFalse(stage_res["runtime_verified"])
            self.assertFalse(stage_res["default_b_enabled"])

        # Published binding has stage="5", revision=2, preserves STAGE4_OBL_PREFIX and multi-plan origins.
        b2_path = f"docs/planning/b-route/bindings/{self.fx.plan_id}/2.json"
        b2 = self.fx.read_json(b2_path)
        self.assertEqual(b2["stage"], "5")
        self.assertEqual(b2["binding_revision"], 2)
        self.assertEqual(len(b2["manifest_refs"]), 1)
        self.assertIn(s5.STAGE5_OBL_PREFIX, b2["obligations"][0]["responsibility"])
        self.assertIn(ch4.STAGE4_OBL_PREFIX, b2["obligations"][0]["responsibility"])
        self.assertNotIn('"status"', json.dumps(b2))

        origins = self.fx.read_json("docs/planning/b-route/task-origins.v1.json")
        row101 = next(r for r in origins["tasks"] if r["task_id"] == 101)
        plan_ids_101 = {r["entity_id"] for r in row101["plan_refs"]}
        binding_ids_101 = {(r["entity_id"], r["revision"]) for r in row101["binding_refs"]}
        self.assertEqual(plan_ids_101, {self.fx.plan_id, self.fx.other_plan_id})
        self.assertEqual(binding_ids_101, {(self.fx.plan_id, 2), (self.fx.other_plan_id, 1)})

        # Story 3.5 comparison from Stage-4 baseline -> Stage-5 must report return_stage="5", NEVER "4"!
        after_101 = input_set.resolve_input_set(self.fx.root, 101, baseline=baseline_101)
        self.assertTrue(after_101["valid_input_set"])
        self.assertEqual(after_101["freshness"]["return_stage"], "5")
        inv_cats = {row["category"] for row in after_101["freshness"]["invalidated_items"]}
        self.assertNotIn("stage4_semantics", inv_cats)
        self.assertNotIn("binding_3c_mappings", inv_cats)

        # Clean-clone extract_stage5_semantics works after deleting logs/ completely!
        shutil.rmtree(self.fx.root / "logs")
        plan_doc = self.fx.read_json(assets["plan_ref"]["path"])
        clean_sem = s5.extract_stage5_semantics(plan_doc, b2)
        self.assertEqual(clean_sem["stage"], "5")
        self.assertFalse(clean_sem["reverification_summary"]["status_copied_into_authority"])

    def test_flow_bind_with_update_mvg_baseline_delta_public_sync_and_crash_recovery(self) -> None:
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=False)
        before_doc = assets["mvg_manifest_doc"]
        delta = {
            "schema_version": update_mvg_baseline.DELTA_SCHEMA,
            "expected_manifest_sha256": update_mvg_baseline._canonical_sha(before_doc),
            "change_plan_sha256": "sha256:" + "a" * 64,
            "test_operations": [
                {
                    "id": "test-reward-extra",
                    "action": "add",
                    "reason": "Add second integration test for reward flow.",
                    "value": {
                        "id": "test-reward-extra",
                        "kind": "dotnet",
                        "evidence_level": "domain-integration",
                        "path": "Game.Core.Tests/Reward/RewardExtraTests.cs",
                        "selector": "RewardExtraTests",
                        "state": "implemented",
                        "min_tests": 1,
                    },
                }
            ],
            "flow_operations": [
                {
                    "id": "flow-reward-select",
                    "action": "update",
                    "reason": "Bind new extra test to reward flow.",
                    "field_updates": {"test_ids": ["test-reward-flow", "test-reward-extra"]},
                }
            ],
        }
        expected_after_doc = update_mvg_baseline.apply_delta(before_doc, delta, root=self.fx.root, validate_final=False)
        expected_after_raw = (json.dumps(expected_after_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        post_delta_mref = _owned_ref("manifest", assets["mvg_manifest_path"], [(assets["mvg_manifest_path"], expected_after_raw)])

        op_id = "OP-S5-DELTA-001"
        req = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_id,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [post_delta_mref],
            "other_verification_refs": [],
            "manifest_deltas": [{"manifest_path": assets["mvg_manifest_path"], "delta": delta}],
            "obligations": [
                {
                    "id": "OBL-REWARD-1",
                    "task_ids": [101, 102],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow", "test-reward-extra"],
                    "category": "current_new",
                    "responsibility": "Verify reward flow handoff with added test.",
                    "verification_refs": [post_delta_mref],
                }
            ],
        }
        req_rel = f"logs/ci/test-requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        s5.prepare(self.fx.root, operation_id=op_id, request_ref=req_rel)
        s5.reserve(self.fx.root, operation_id=op_id)

        # Simulate crash right after public-sync writes the new manifest (before commit.json is created).
        def _crash_after_sync(name: str) -> None:
            if name == "public_sync_applied_durable":
                raise RuntimeError("simulated power loss after manifest sync")

        with patch.object(s5, "_checkpoint", side_effect=_crash_after_sync):
            with self.assertRaises(codec.CodecError):
                commit.execute(self.fx.root, operation_id=op_id, stage="apply")

        # While public-sync.pending.json exists, Story 3.3 resolve_task_origin MUST conservatively block!
        origin_during_pending = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertEqual(origin_during_pending["route"], "blocked")
        self.assertEqual(origin_during_pending["diagnostics"][0]["reason_code"], codec.ReasonCode.PENDING.value)

        # recover-inspect must report public_sync_applied_pre_commit and next_stage="apply".
        inspected = commit.inspect_recovery(self.fx.root, operation_id=op_id)
        self.assertEqual(inspected["physical_state"], "public_sync_applied_pre_commit")
        self.assertEqual(inspected["next_stage"], "apply")

        # recover rolls forward cleanly to published and cleans public-sync.pending.json!
        recovered = commit.recover(self.fx.root, operation_id=op_id)
        self.assertTrue(recovered["published"])
        pub_j_rel, pub_p_rel = s5.public_sync_paths(op_id)
        self.assertFalse((self.fx.root / pub_p_rel).exists())
        self.assertEqual(self.fx.read_json(pub_j_rel)["phase"], "complete")
        self.assertEqual(self.fx.read_json(assets["mvg_manifest_path"])["tests"][-1]["id"], "test-reward-extra")

        # After recovery, Story 3.3 and Story 3.5 both pass cleanly!
        origin_after = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertEqual(origin_after["route"], "B")
        iset_after = input_set.resolve_input_set(self.fx.root, 101)
        self.assertTrue(iset_after["ok"])

    def test_flow_bind_blocks_missing_stale_wrong_manifest_omitted_test_and_stage4_skip(self) -> None:
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=False)

        # 1. Missing manifest on Flow plan -> blocked.
        req_missing = self._flow_request("OP-S5-NO-MAN", assets)
        req_missing["manifest_refs"] = []
        req_missing["obligations"][0]["verification_refs"] = []
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_missing)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # 2. Stale / wrong raw_digest in manifest_ref -> blocked.
        req_stale = self._flow_request("OP-S5-STALE-MAN", assets)
        req_stale["manifest_refs"][0]["files"][0]["raw_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_stale)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.DIGEST_MISMATCH)

        # 3. Wrong expected_manifest_sha256 -> blocked.
        req_wrong_sha = self._flow_request("OP-S5-WRONG-SHA", assets)
        req_wrong_sha["expected_manifest_sha256"] = {assets["mvg_manifest_path"]: "sha256:" + "f" * 64}
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_wrong_sha)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.DIGEST_MISMATCH)

        # 4. Omitted Flow test -> blocked.
        req_omit_test = self._flow_request("OP-S5-OMIT-TEST", assets)
        req_omit_test["obligations"][0]["test_ids"] = []
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_omit_test)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # 5. Skipping Stage 4 (prior_stage="3C") -> blocked with return_stage="4".
        fx3c = Stage5RepoFixture()
        try:
            assets3c = fx3c.build_committed_stage4(mode="flow", prior_stage="3C", include_other_plan=False)
            req3c = {
                "schema_version": s5.REQUEST_SCHEMA,
                "producer": s5.PRODUCER,
                "operation_id": "OP-S5-SKIP-S4",
                "plan_id": fx3c.plan_id,
                "scope_id": fx3c.scope_id,
                "manifest_refs": [assets3c["mvg_manifest_ref"]],
                "other_verification_refs": [],
                "obligations": [
                    {
                        "id": "OBL-REWARD-1",
                        "task_ids": [101, 102],
                        "requirement_ids": ["REQ-REWARD-1"],
                        "flow_ids": ["flow-reward-select"],
                        "test_ids": ["test-reward-flow"],
                        "category": "current_new",
                        "responsibility": "Verify reward flow.",
                        "verification_refs": [assets3c["mvg_manifest_ref"]],
                    }
                ],
            }
            with self.assertRaises(codec.CodecError) as ctx:
                s5.build(fx3c.root, req3c)
            self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)
            self.assertEqual(s5.extract_mismatch_attribution(ctx.exception.diagnostic.to_dict())["return_stage"], "4")
        finally:
            fx3c.cleanup()

    # ------------------------------------------------------------------
    # Matrix Row 2: NONFLOW_OK (legal exemption + label/empty/N/A/source_gap blocks)
    # ------------------------------------------------------------------

    def test_nonflow_ok_exempts_fake_flow_and_manifest_with_real_other_verification(self) -> None:
        assets = self.fx.build_committed_stage4(mode="nonflow", include_other_plan=False)
        op_id = "OP-S5-NONFLOW-001"
        req = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_id,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [],
            "other_verification_refs": [assets["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["docs/workflows/standalone-tool.md"],
                "touched_contracts": [],
                "touched_tests": [],
                "touched_consumer_chains": [],
                "reverse_impact_known": True,
                "unknown_impact_reason": None,
                "cumulative_manifest_refs": [assets["mvg_manifest_ref"]],
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [assets["other_verif_ref"]],
                    "exemption_basis": "3b_applicability",
                    "exemption_rationale": "3B adopted other_verification with zero gameplay Flow impact.",
                }
            ],
        }
        results = _run_full_lifecycle(self.fx, op_id, req)
        self.assertTrue(results["publish"]["published"])
        b2 = self.fx.read_json(f"docs/planning/b-route/bindings/{self.fx.plan_id}/2.json")
        self.assertEqual(b2["stage"], "5")
        self.assertEqual(b2["manifest_refs"], [])
        self.assertEqual(len(b2["other_verification_refs"]), 1)
        iset = input_set.resolve_input_set(self.fx.root, 101)
        self.assertTrue(iset["ok"])

    def test_nonflow_blocks_label_na_empty_deleted_evidence_and_source_gap(self) -> None:
        # 1. Label exemption basis -> blocked.
        assets = self.fx.build_committed_stage4(mode="nonflow", include_other_plan=False)
        req_label = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-S5-NF-LABEL",
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [],
            "other_verification_refs": [assets["other_verif_ref"]],
            "impact_analysis": {"reverse_impact_known": True, "touched_paths": ["docs/workflows/standalone-tool.md"]},
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [assets["other_verif_ref"]],
                    "exemption_basis": "label",
                }
            ],
        }
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_label)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # 2. N/A rationale -> blocked.
        req_na = copy.deepcopy(req_label)
        req_na["obligations"][0]["exemption_basis"] = "3b_applicability"
        req_na["obligations"][0]["exemption_rationale"] = "N/A"
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_na)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # 3. Deleting other_verification_refs -> blocked.
        req_del = copy.deepcopy(req_label)
        req_del["other_verification_refs"] = []
        req_del["obligations"][0]["exemption_basis"] = "3b_applicability"
        req_del["obligations"][0]["verification_refs"] = []
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_del)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # 4. Taskmaster free-form N/A label -> blocked.
        fx_lbl = Stage5RepoFixture()
        try:
            a_lbl = fx_lbl.build_committed_stage4(mode="nonflow", include_other_plan=False, nonflow_na_label=True)
            req_t = copy.deepcopy(req_label)
            req_t["other_verification_refs"] = [a_lbl["other_verif_ref"]]
            req_t["obligations"][0]["verification_refs"] = [a_lbl["other_verif_ref"]]
            req_t["obligations"][0]["exemption_basis"] = "3b_applicability"
            with self.assertRaises(codec.CodecError) as ctx:
                s5.build(fx_lbl.root, req_t)
            self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)
        finally:
            fx_lbl.cleanup()

        # 5. source_gap -> blocked.
        fx_gap = Stage5RepoFixture()
        try:
            a_gap = fx_gap.build_committed_stage4(mode="nonflow", include_other_plan=False, source_gap=True)
            req_g = copy.deepcopy(req_label)
            req_g["other_verification_refs"] = [a_gap["other_verif_ref"]]
            req_g["obligations"][0]["verification_refs"] = [a_gap["other_verif_ref"]]
            req_g["obligations"][0]["exemption_basis"] = "3b_applicability"
            with self.assertRaises(codec.CodecError) as ctx:
                s5.build(fx_gap.root, req_g)
            self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)
        finally:
            fx_gap.cleanup()

    # ------------------------------------------------------------------
    # Matrix Row 3: IMPACT_EXP (touches flow, unknown conservative expansion, 3 categories, blocks)
    # ------------------------------------------------------------------

    def test_impact_exp_nonflow_touching_flow_and_unknown_conservative_expansion_three_categories(self) -> None:
        # Non-flow plan with cumulative manifest containing TWO non-catalog flows (flow-reward-select & flow-legacy-map).
        assets = self.fx.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            include_legacy_cumulative_flow=True,
        )
        # Case A: non-Flow touches flow-legacy-map source_path -> MUST bind regression & keep non-catalog flow in STAGE5_OBL_PREFIX (zero MAPPING_MISMATCH!).
        op_touch = "OP-S5-IMP-TOUCH"
        req_touch = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_touch,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [assets["mvg_manifest_ref"]],
            "other_verification_refs": [assets["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["Game.Core/Services/CombatService.cs"],
                "reverse_impact_known": True,
                "cumulative_manifest_refs": [assets["mvg_manifest_ref"]],
                "future_obligations": [
                    {
                        "flow_id": "flow-future-shop",
                        "reason": "Future shop integration deferred to next milestone.",
                        "force_implement_now": False,
                    }
                ],
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [assets["other_verif_ref"]],
                },
                {
                    "id": "OBL-REG-LEGACY",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": ["flow-legacy-map"],
                    "test_ids": ["test-legacy-map"],
                    "category": "existing_required",
                    "responsibility": "Regression check for touched legacy map flow.",
                    "verification_refs": [assets["mvg_manifest_ref"]],
                },
            ],
        }
        results = _run_full_lifecycle(self.fx, op_touch, req_touch)
        self.assertTrue(results["publish"]["published"])
        sem = results["preview"]["stage5_semantics"]
        self.assertEqual(sem["impact_mode"], "non_flow_touches_flow_regression")
        self.assertEqual(len(sem["impact_classification"]["existing_required"]), 1)
        self.assertEqual(len(sem["impact_classification"]["current_new"]), 1)
        self.assertEqual(len(sem["impact_classification"]["out_of_scope_future"]), 1)
        # Non-catalog flow-legacy-map was NOT placed in formal obligation.flow_ids (preventing MAPPING_MISMATCH)
        # and IS recorded in stage5_meta.non_catalog_flow_ids + test_ids + manifest_refs!
        b2 = self.fx.read_json(f"docs/planning/b-route/bindings/{self.fx.plan_id}/2.json")
        reg_obl = next(o for o in b2["obligations"] if o["id"] == "OBL-REG-LEGACY")
        self.assertEqual(reg_obl["flow_ids"], [])
        self.assertEqual(reg_obl["test_ids"], ["test-legacy-map"])
        _, meta = s5._parse_stage5_obl_meta(reg_obl["responsibility"])
        self.assertEqual(meta["non_catalog_flow_ids"], ["flow-legacy-map"])

        # Case B: unknown reverse impact -> MUST expand to ALL cumulative flows & tests; narrowing blocks!
        req_unknown_narrow = copy.deepcopy(req_touch)
        req_unknown_narrow["operation_id"] = "OP-S5-IMP-NARROW"
        req_unknown_narrow["impact_analysis"]["reverse_impact_known"] = False
        req_unknown_narrow["impact_analysis"]["unknown_impact_reason"] = "Shared utility call graph unknown"
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_unknown_narrow)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Expanding to full cumulative scope (both flow-reward-select & flow-legacy-map) succeeds!
        req_unknown_full = copy.deepcopy(req_unknown_narrow)
        req_unknown_full["operation_id"] = "OP-S5-IMP-FULL"
        req_unknown_full["obligations"].append(
            {
                "id": "OBL-REG-REWARD",
                "task_ids": [101],
                "requirement_ids": ["REQ-TOOL-1"],
                "flow_ids": ["flow-reward-select"],
                "test_ids": ["test-reward-flow"],
                "category": "existing_required",
                "responsibility": "Conservative cumulative expansion for reward flow.",
                "verification_refs": [assets["mvg_manifest_ref"]],
            }
        )
        _snap, _frz, full_sem = s5.build(self.fx.root, req_unknown_full)
        self.assertEqual(full_sem["impact_mode"], "conservative_full_cumulative_expansion")

        # Case C: force_implement_now=True on out_of_scope_future -> blocked!
        req_force_future = copy.deepcopy(req_unknown_full)
        req_force_future["impact_analysis"]["future_obligations"][0]["force_implement_now"] = True
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_force_future)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Case D: omitting cumulative_manifest_refs while a repo MVG manifest exists STILL auto-discovers and blocks;
        # when NO repo MVG manifest exists at all, reverse_impact_known=False blocks with IDENTITY_UNPROVABLE!
        req_unprovable = copy.deepcopy(req_touch)
        req_unprovable["manifest_refs"] = []
        req_unprovable["impact_analysis"] = {"reverse_impact_known": False, "unknown_impact_reason": "unknown"}
        req_unprovable["obligations"] = [req_touch["obligations"][0]]
        with self.assertRaises(codec.CodecError) as ctx_auto:
            s5.build(self.fx.root, req_unprovable)
        self.assertEqual(ctx_auto.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # Now test true absence of any MVG manifest in repo -> IDENTITY_UNPROVABLE.
        fx_no_mvg = Stage5RepoFixture()
        try:
            a_no_mvg = fx_no_mvg.build_committed_stage4(mode="nonflow", include_other_plan=False)
            (fx_no_mvg.root / a_no_mvg["mvg_manifest_path"]).unlink()
            req_no_mvg = copy.deepcopy(req_unprovable)
            req_no_mvg["other_verification_refs"] = [a_no_mvg["other_verif_ref"]]
            req_no_mvg["obligations"][0]["verification_refs"] = [a_no_mvg["other_verif_ref"]]
            with self.assertRaises(codec.CodecError) as ctx_unp:
                s5.build(fx_no_mvg.root, req_no_mvg)
            self.assertEqual(ctx_unp.exception.diagnostic.reason_code, codec.ReasonCode.IDENTITY_UNPROVABLE)
        finally:
            fx_no_mvg.cleanup()

    # ------------------------------------------------------------------
    # Matrix Row 4: ROLE_DEP (3 roles + non-done/planned legal; erase dep / self-lock / missing def block)
    # ------------------------------------------------------------------

    def test_role_dep_three_roles_planned_and_nondone_legal_without_self_lock(self) -> None:
        assets = self.fx.build_committed_stage4(
            mode="role_dep",
            include_other_plan=False,
            task101_status="in-progress",
            task102_status="pending",
            task103_status="pending",
            planned_test=True,
        )
        op_id = "OP-S5-ROLE-001"
        req = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_id,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [assets["mvg_manifest_ref"]],
            "other_verification_refs": [],
            "role_handoff_checks": {
                "declared_prerequisites": {"102": [101], "103": [101, 102]},
                "require_self_done": False,
                "require_integration_owner_api": False,
            },
            "obligations": [
                {
                    "id": "OBL-REWARD-1",
                    "task_ids": [101, 102, 103],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow"],
                    "category": "current_new",
                    "responsibility": "Verify reward flow across producer, consumer, and integration_only_owner.",
                    "verification_refs": [assets["mvg_manifest_ref"]],
                }
            ],
        }
        results = _run_full_lifecycle(self.fx, op_id, req)
        self.assertTrue(results["publish"]["published"])
        dep_sum = results["preview"]["stage5_semantics"]["dependency_summary"]
        self.assertFalse(dep_sum["103"]["self_done_required"])
        self.assertTrue(dep_sum["103"]["non_done_dependencies_legal"])
        self.assertEqual(dep_sum["103"]["non_done_dependency_ids"], [101, 102])

        # Error 1: Erasing prerequisite dependency -> blocked.
        req_erase = copy.deepcopy(req)
        req_erase["operation_id"] = "OP-S5-ROLE-ERASE"
        req_erase["role_handoff_checks"]["declared_prerequisites"] = {"103": [101]}  # dropped 102!
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_erase)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.MAPPING_MISMATCH)

        # Error 2: Self-lock (require_self_done=True) -> blocked.
        req_selflock = copy.deepcopy(req)
        req_selflock["role_handoff_checks"]["require_self_done"] = True
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_selflock)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.DIGEST_CYCLE)

        # Error 3: Dedicated integration_only_owner self-locked in manifest blocking_task_ids -> blocked.
        fx_sl = Stage5RepoFixture()
        try:
            a_sl = fx_sl.build_committed_stage4(
                mode="role_dep",
                include_other_plan=False,
                self_lock_owner_in_manifest=True,
            )
            req_sl = copy.deepcopy(req)
            req_sl["manifest_refs"] = [a_sl["mvg_manifest_ref"]]
            req_sl["obligations"][0]["verification_refs"] = [a_sl["mvg_manifest_ref"]]
            with self.assertRaises(codec.CodecError) as ctx:
                s5.build(fx_sl.root, req_sl)
            self.assertIn(
                ctx.exception.diagnostic.reason_code,
                (codec.ReasonCode.SCHEMA_VALIDATION_FAILED, codec.ReasonCode.DIGEST_CYCLE),
            )
        finally:
            fx_sl.cleanup()

        # Error 4: Missing definition (deleted contract_ref) -> blocked.
        (self.fx.root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs").unlink()
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req)
        self.assertIn(
            ctx.exception.diagnostic.reason_code,
            (codec.ReasonCode.FILE_NOT_FOUND, codec.ReasonCode.UNRESOLVED_REFERENCE, codec.ReasonCode.SCHEMA_VALIDATION_FAILED),
        )

    # ------------------------------------------------------------------
    # Matrix Row 5: DEDUP_RET (dedup, old done reverification, reviewed retire, blocks)
    # ------------------------------------------------------------------

    def test_dedup_ret_old_done_reverification_reviewed_retirement_and_blocks(self) -> None:
        # Task 101 is ALREADY "done", manifest has a planned test, and Stage 5 adds a new obligation!
        assets = self.fx.build_committed_stage4(
            mode="flow",
            include_other_plan=False,
            task101_status="done",
            task102_status="done",
            planned_test=True,
        )
        op_id = "OP-S5-DEDUP-001"
        req = self._flow_request(
            op_id,
            assets,
            extra_obligations=[
                {
                    "id": "OBL-REWARD-NEW",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow"],
                    "category": "current_new",
                    "responsibility": "Additional Stage-5 verification check on shared requirement.",
                    "verification_refs": [assets["mvg_manifest_ref"]],
                }
            ],
        )
        req["reported_counts"] = {"unique_requirements": 1, "unique_routes": 1, "unique_tests": 1, "unique_evidence": 1}

        results = _run_full_lifecycle(self.fx, op_id, req)
        self.assertTrue(results["publish"]["published"])
        sem = results["preview"]["stage5_semantics"]
        # Shared requirement/route/test counted ONCE (no double counting).
        self.assertEqual(sem["deduplication"]["unique_requirement_count"], 1)
        self.assertEqual(sem["deduplication"]["unique_route_count"], 1)
        self.assertEqual(sem["deduplication"]["unique_test_count"], 1)
        self.assertFalse(sem["deduplication"]["double_counting_detected"])
        # Old done Task 101 MUST be marked requires_reverification=True without copying status into formal binding!
        t101_rev = next(r for r in sem["reverification_summary"]["tasks"] if r["task_id"] == 101)
        self.assertTrue(t101_rev["is_old_done"])
        self.assertTrue(t101_rev["requires_reverification"])
        self.assertFalse(t101_rev["old_done_covers_new_obligations"])
        b2 = self.fx.read_json(f"docs/planning/b-route/bindings/{self.fx.plan_id}/2.json")
        self.assertNotIn('"status"', json.dumps(b2))

        # Error 1: Double-counting reported_counts -> blocked.
        req_dbl = copy.deepcopy(req)
        req_dbl["operation_id"] = "OP-S5-DBL"
        req_dbl["reported_counts"] = {"unique_requirements": 2}
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_dbl)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.MAPPING_MISMATCH)

        # Error 2: Old done attempting skip_reverification=True -> blocked.
        req_skip = copy.deepcopy(req)
        req_skip["operation_id"] = "OP-S5-SKIP-REV"
        req_skip["obligations"][1]["skip_reverification"] = True
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_skip)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Error 3: Unreviewed retirement of OBL-REWARD-NEW -> blocked!
        req_unrev_retire = self._flow_request("OP-S5-UNREV-RET", assets)
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_unrev_retire)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Error 4: Pending (non-reviewed) authority_review -> blocked!
        req_pending_ret = copy.deepcopy(req_unrev_retire)
        req_pending_ret["obligation_retirements"] = [
            {
                "target_id": "OBL-REWARD-NEW",
                "kind": "retire_obligation",
                "authority_ref": assets["retire_spec_path"],
                "authority_review": {"status": "pending", "rationale": "Not reviewed yet."},
            }
        ]
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_pending_ret)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Success: Reviewed specification authority_ref permits retirement of OBL-REWARD-NEW!
        req_rev_ret = copy.deepcopy(req_unrev_retire)
        req_rev_ret["operation_id"] = "OP-S5-REV-RET"
        req_rev_ret["obligation_retirements"] = [
            {
                "target_id": "OBL-REWARD-NEW",
                "kind": "retire_obligation",
                "authority_ref": assets["retire_spec_path"],
                "authority_review": {
                    "status": "reviewed",
                    "rationale": "Duplicate obligation retired per ADR-9999 after consolidation into OBL-REWARD-1.",
                },
            }
        ]
        ret_res = _run_full_lifecycle(self.fx, "OP-S5-REV-RET", req_rev_ret)
        self.assertTrue(ret_res["publish"]["published"])
        self.assertEqual(len(ret_res["preview"]["stage5_semantics"]["retirements_applied"]), 1)

        # Error 5: Legacy capability-apply.pending.json blocks Stage-5 binding with PENDING!
        cap_payload = {"schema_version": "newrouge.capabilities.v1", "capabilities": []}
        cap_raw = _encoded(cap_payload)
        jrel = "logs/ci/capability-planning/run-legacy/apply-journal.json"
        self.fx.put_json(
            jrel,
            {
                "schema_version": "newrouge.planning-apply-journal.v1",
                "status": "pending",
                "authority_inputs": {},
                "entries": [
                    {
                        "path": "docs/planning/semantic-topology/capabilities.v1.json",
                        "before_sha256": None,
                        "before_base64": None,
                        "after_sha256": codec.raw_digest(cap_raw),
                        "payload": cap_payload,
                    }
                ],
                "result": {"status": "pending"},
            },
        )
        self.fx.put_json(op_scope.CAP_PENDING, {"run_id": "run-legacy", "journal_path": jrel})
        with self.assertRaises(codec.CodecError) as ctx:
            s5.build(self.fx.root, req_rev_ret)
        self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.PENDING)

    # ------------------------------------------------------------------
    # Integration: Story 2.8 Compensation, Schema Isolation, Policy Anchor, CLI & Zero-Pycache
    # ------------------------------------------------------------------

    def test_compensation_compatibility_schema_isolation_policy_anchor_and_cli(self) -> None:
        # 1. Schema isolation: 7 FORMAL untouched; stage5-obligations-operation ONLY in AUXILIARY.
        self.assertEqual(
            schema_resources.FORMAL,
            ("common", "policy", "plan", "binding", "origins", "commit", "catalog"),
        )
        self.assertIn("stage5-obligations-operation", schema_resources.AUXILIARY)
        self.assertNotIn("stage5-obligations-operation", schema_resources.FORMAL)

        # 2. Policy anchoring includes _b_route_stage5_obligations.py.
        _ident, pinned_files = adoption_review.policy_observations()
        self.assertTrue(any(p.endswith("_b_route_stage5_obligations.py") for p in pinned_files))

        # 3. Publish Stage-5 binding via CLI (all 10 stages including read) & verify compensation relation_for.
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=False)
        op_id = "OP-S5-CLI-001"
        req = self._flow_request(op_id, assets)
        req_rel = f"logs/ci/test-requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        for stage_args in (
            ["--stage", "preview", "--request", req_rel],
            ["--stage", "prepare", "--request", req_rel],
            ["--stage", "reserve"],
            ["--stage", "inspect"],
            ["--stage", "apply"],
            ["--stage", "verify"],
            ["--stage", "publish"],
            ["--stage", "read"],
            ["--stage", "recover-inspect"],
        ):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(REPO_ROOT / "scripts/python/dev_cli.py"),
                    "b-route-stage5-obligations",
                    "--root",
                    str(self.fx.root),
                    "--operation-id",
                    op_id,
                    *stage_args,
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"stage={stage_args} stderr={proc.stderr} stdout={proc.stdout}")
            payload = json.loads(proc.stdout.strip())
            self.assertFalse(payload["readiness"])
            self.assertFalse(payload["runtime_verified"])
            self.assertFalse(payload["default_b_enabled"])
            if stage_args[1] == "read":
                self.assertEqual(len(payload["stage5_semantics"]), 1)
                self.assertEqual(payload["stage5_semantics"][0]["stage"], "5")

        # Verify Story 2.8 compensation relation_for & validate_operation compatibility on persisted Stage-5 op.
        op_env = journal.read_operation(self.fx.root, operation_id=op_id)
        rel = compensation.relation_for(op_env)
        self.assertEqual(rel["operation_id"], op_id)
        self.assertEqual(rel["frozen_digest"], op_env["frozen_digest"])

        # Verify dev_cli_builders.build_b_route_stage5_obligations_cmd and --help.
        class _Args:
            root = "."
            stage = "preview"
            operation_id = "OP-TEST"
            request = "logs/ci/req.json"

        cmd = dev_cli_builders.build_b_route_stage5_obligations_cmd(_Args())
        self.assertIn("bind_b_route_stage5_obligations.py", cmd[2])
        self.assertIn("--request", cmd)

        help_proc = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "scripts/python/dev_cli.py"), "b-route-stage5-obligations", "--help"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("--stage", help_proc.stdout)

        # Verify event audit log written for state-advancing stages.
        ev_log = self.fx.root / s5.EVENTS_BASE / op_id / "events.jsonl"
        self.assertTrue(ev_log.is_file())
        events = [json.loads(line) for line in ev_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(e["stage"] == "publish" for e in events))
        self.assertTrue(all(not e["readiness"] and not e["runtime_verified"] and not e["default_b_enabled"] for e in events))

    # ------------------------------------------------------------------
    # Step 4 Adversarial Review Patch Verification (P-01 .. P-06)
    # ------------------------------------------------------------------

    def test_p01_unconditional_na_label_and_mixed_impacted_nonflow_enforcement(self) -> None:
        # 1. Task mvg:N/A label MUST block even on a Flow plan (requires_mvg_manifest=True).
        fx_flow_lbl = Stage5RepoFixture()
        self.addCleanup(fx_flow_lbl.cleanup)
        a_fl = fx_flow_lbl.build_committed_stage4(mode="flow", include_other_plan=False, nonflow_na_label=True)
        req_fl = self._flow_request("OP-P01-FLOW-LBL", a_fl)
        with self.assertRaises(codec.CodecError) as ctx_fl:
            s5.build(fx_flow_lbl.root, req_fl)
        self.assertEqual(ctx_fl.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # 2. Task mvg:N/A label and N/A 3B rationale MUST block on an impacted non-Flow plan
        #    (non_flow_touches_flow_regression where requires_mvg_manifest=True).
        fx_imp_na = Stage5RepoFixture()
        self.addCleanup(fx_imp_na.cleanup)
        a_imp = fx_imp_na.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            include_legacy_cumulative_flow=True,
            nonflow_empty_rationale=True,
        )
        req_imp_na = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P01-IMP-NA",
            "plan_id": fx_imp_na.plan_id,
            "scope_id": fx_imp_na.scope_id,
            "manifest_refs": [a_imp["mvg_manifest_ref"]],
            "other_verification_refs": [a_imp["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["Game.Core/Services/CombatService.cs"],
                "reverse_impact_known": True,
                "cumulative_manifest_refs": [a_imp["mvg_manifest_ref"]],
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [a_imp["other_verif_ref"]],
                },
                {
                    "id": "OBL-REG-LEGACY",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": ["flow-legacy-map"],
                    "test_ids": ["test-legacy-map"],
                    "category": "existing_required",
                    "responsibility": "Regression check for legacy map flow.",
                    "verification_refs": [a_imp["mvg_manifest_ref"]],
                },
            ],
        }
        with self.assertRaises(codec.CodecError) as ctx_imp_na:
            s5.build(fx_imp_na.root, req_imp_na)
        self.assertEqual(ctx_imp_na.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)
        self.assertEqual(s5.extract_mismatch_attribution(ctx_imp_na.exception.diagnostic.to_dict())["return_stage"], "3B")

        # 3. Impacted non-Flow plan: dropping 3B other_verification_ref or leaving REQ-TOOL-1 without
        #    genuine other_verification/authority ref on obligations MUST block!
        fx_imp_ok = Stage5RepoFixture()
        self.addCleanup(fx_imp_ok.cleanup)
        a_ok = fx_imp_ok.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            include_legacy_cumulative_flow=True,
        )
        req_imp_no_ov = copy.deepcopy(req_imp_na)
        req_imp_no_ov["operation_id"] = "OP-P01-IMP-NO-OV"
        req_imp_no_ov["manifest_refs"] = [a_ok["mvg_manifest_ref"]]
        req_imp_no_ov["other_verification_refs"] = []
        req_imp_no_ov["impact_analysis"]["cumulative_manifest_refs"] = [a_ok["mvg_manifest_ref"]]
        req_imp_no_ov["obligations"][0]["verification_refs"] = []
        req_imp_no_ov["obligations"][1]["verification_refs"] = [a_ok["mvg_manifest_ref"]]
        with self.assertRaises(codec.CodecError) as ctx_no_ov:
            s5.build(fx_imp_ok.root, req_imp_no_ov)
        self.assertEqual(ctx_no_ov.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # Even if obligation carries an unrelated authority ref, dropping the 3B other_verification ref
        # without reviewed retirement MUST block at Step 11!
        auth_ref = _owned_ref("authority", a_ok["retire_spec_path"], [(a_ok["retire_spec_path"], a_ok["retire_spec_raw"])])
        req_imp_swap_auth = copy.deepcopy(req_imp_no_ov)
        req_imp_swap_auth["other_verification_refs"] = [auth_ref]
        req_imp_swap_auth["obligations"][0]["verification_refs"] = [auth_ref]
        with self.assertRaises(codec.CodecError) as ctx_swap:
            s5.build(fx_imp_ok.root, req_imp_swap_auth)
        self.assertEqual(ctx_swap.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

    def test_p02_repo_manifest_autodiscovery_refs_extraction_and_flow_chains_parity(self) -> None:
        # 1. Omitting cumulative_manifest_refs cannot bypass repo MVG manifest auto-discovery
        #    when a non-Flow task touches a Flow via acceptance[] Refs: or test_refs!
        fx_refs = Stage5RepoFixture()
        self.addCleanup(fx_refs.cleanup)
        a_refs = fx_refs.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            nonflow_acceptance_ref="Game.Core.Tests/Reward/RewardFlowTests.cs",
        )
        req_refs_omit = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P02-REFS-OMIT",
            "plan_id": fx_refs.plan_id,
            "scope_id": fx_refs.scope_id,
            "manifest_refs": [],
            "other_verification_refs": [a_refs["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["docs/workflows/standalone-tool.md"],
                "reverse_impact_known": True,
                # Intentionally omit cumulative_manifest_refs!
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [a_refs["other_verif_ref"]],
                }
            ],
        }
        with self.assertRaises(codec.CodecError) as ctx_refs:
            s5.build(fx_refs.root, req_refs_omit)
        self.assertEqual(ctx_refs.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # Same check via test_refs (with clean non-Flow acceptance Refs:)
        fx_trefs = Stage5RepoFixture()
        self.addCleanup(fx_trefs.cleanup)
        a_trefs = fx_trefs.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            task101_test_refs=["Game.Core.Tests/Reward/RewardFlowTests.cs"],
        )
        req_trefs = copy.deepcopy(req_refs_omit)
        req_trefs["operation_id"] = "OP-P02-TREFS-OMIT"
        req_trefs["other_verification_refs"] = [a_trefs["other_verif_ref"]]
        req_trefs["obligations"][0]["verification_refs"] = [a_trefs["other_verif_ref"]]
        with self.assertRaises(codec.CodecError) as ctx_trefs:
            s5.build(fx_trefs.root, req_trefs)
        self.assertEqual(ctx_trefs.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

        # 2. Flow-plan touched_consumer_chains parity: matches edge["contract_ref"] AND rejects unmatched chain entries!
        fx_fc = Stage5RepoFixture()
        self.addCleanup(fx_fc.cleanup)
        a_fc = fx_fc.build_committed_stage4(
            mode="flow",
            include_other_plan=False,
            include_legacy_cumulative_flow=True,
        )
        # Touching SelectRewardCommand.cs via touched_consumer_chains hits flow-legacy-map too -> omitting it blocks!
        req_fc_chain = self._flow_request("OP-P02-FLOW-CHAIN", a_fc)
        req_fc_chain["impact_analysis"] = {
            "touched_consumer_chains": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"],
            "reverse_impact_known": True,
        }
        with self.assertRaises(codec.CodecError) as ctx_chain_hit:
            s5.build(fx_fc.root, req_fc_chain)
        self.assertEqual(ctx_chain_hit.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Unmatched touched_consumer_chains entry on Flow plan MUST fail closed with UNRESOLVED_REFERENCE!
        req_fc_bad_chain = self._flow_request("OP-P02-BAD-CHAIN", a_fc)
        req_fc_bad_chain["impact_analysis"] = {
            "touched_consumer_chains": ["flow-reward-select", "chain-does-not-exist"],
            "reverse_impact_known": True,
        }
        with self.assertRaises(codec.CodecError) as ctx_bad_chain:
            s5.build(fx_fc.root, req_fc_bad_chain)
        self.assertEqual(ctx_bad_chain.exception.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

    def test_p03_prior_stage5_flows_task_obl_conservation_skip_reverification_and_nonlog_retire(self) -> None:
        # 1. Stage-5 -> Stage-5 re-bind with non-catalog flow & future flow:
        #    unchanged non-catalog flow does NOT trigger false is_new_obl, while unreviewed removal blocks!
        fx_nf = Stage5RepoFixture()
        self.addCleanup(fx_nf.cleanup)
        a_nf = fx_nf.build_committed_stage4(
            mode="nonflow",
            include_other_plan=False,
            include_legacy_cumulative_flow=True,
            task101_status="done",
        )
        req1 = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P03-S5-V1",
            "plan_id": fx_nf.plan_id,
            "scope_id": fx_nf.scope_id,
            "manifest_refs": [a_nf["mvg_manifest_ref"]],
            "other_verification_refs": [a_nf["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["Game.Core/Services/CombatService.cs"],
                "reverse_impact_known": True,
                "cumulative_manifest_refs": [a_nf["mvg_manifest_ref"]],
                "future_obligations": [{"flow_id": "flow-future-shop", "reason": "Deferred to next milestone."}],
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "existing_required",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [a_nf["other_verif_ref"]],
                },
                {
                    "id": "OBL-REG-LEGACY",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": ["flow-legacy-map"],
                    "test_ids": ["test-legacy-map"],
                    "category": "existing_required",
                    "responsibility": "Regression check for legacy map flow.",
                    "verification_refs": [a_nf["mvg_manifest_ref"]],
                },
            ],
        }
        res1 = _run_full_lifecycle(fx_nf, "OP-P03-S5-V1", req1, include_preview=False)
        self.assertTrue(res1["publish"]["published"])

        # Re-bind with exact same non-catalog flow & existing_required -> is_new_obl is False!
        req2 = copy.deepcopy(req1)
        req2["operation_id"] = "OP-P03-S5-V2"
        req2["obligations"][1]["skip_reverification"] = True
        _snap2, _frz2, sem2 = s5.build(fx_nf.root, req2)
        reg2 = next(o for o in sem2["obligations"] if o["id"] == "OBL-REG-LEGACY")
        self.assertFalse(reg2["stage5_meta"]["has_new_obligation"])

        # Dropping flow-legacy-map from OBL-REG-LEGACY without retirement MUST block at Step 11 (remove_flow)!
        req_drop_nc = copy.deepcopy(req2)
        req_drop_nc["operation_id"] = "OP-P03-DROP-NC"
        req_drop_nc["impact_analysis"]["touched_paths"] = ["docs/workflows/standalone-tool.md"]
        req_drop_nc["obligations"][1]["flow_ids"] = []
        req_drop_nc["obligations"][1]["verification_refs"] = [a_nf["mvg_manifest_ref"], a_nf["other_verif_ref"]]
        with self.assertRaises(codec.CodecError) as ctx_nc:
            s5.build(fx_nf.root, req_drop_nc)
        self.assertEqual(ctx_nc.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # 2. Per-Task obligation conservation, newly_assigned_task_ids, skip_reverification, & non-log authority_ref!
        fx_f = Stage5RepoFixture()
        self.addCleanup(fx_f.cleanup)
        a_f = fx_f.build_committed_stage4(
            mode="flow",
            include_other_plan=False,
            task101_status="done",
            task102_status="done",
        )
        # First publish Stage-5 with OBL-REWARD-1 on [101, 102] and OBL-REWARD-EXTRA on [101] ONLY.
        req_f1 = self._flow_request(
            "OP-P03-FLOW-V1",
            a_f,
            extra_obligations=[
                {
                    "id": "OBL-REWARD-EXTRA",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow"],
                    "category": "existing_required",
                    "responsibility": "Extra reward check initially only on Task 101.",
                    "verification_refs": [a_f["mvg_manifest_ref"]],
                }
            ],
        )
        req_f1["obligations"][0]["category"] = "existing_required"
        self.assertTrue(_run_full_lifecycle(fx_f, "OP-P03-FLOW-V1", req_f1, include_preview=False)["publish"]["published"])

        # Re-assign existing unchanged OBL-REWARD-EXTRA to done Task 102:
        # - skip_reverification=True MUST block on Task 102!
        req_reassign_skip = copy.deepcopy(req_f1)
        req_reassign_skip["operation_id"] = "OP-P03-REASSIGN-SKIP"
        req_reassign_skip["obligations"][1]["task_ids"] = [101, 102]
        req_reassign_skip["obligations"][1]["skip_reverification"] = True
        with self.assertRaises(codec.CodecError) as ctx_ra:
            s5.build(fx_f.root, req_reassign_skip)
        self.assertEqual(ctx_ra.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # - Without skip_reverification, Task 102 gets newly_assigned_task_ids=[102] and requires_reverification=True
        #   while Task 101 (unchanged) has requires_reverification=False!
        req_reassign_ok = copy.deepcopy(req_reassign_skip)
        req_reassign_ok["operation_id"] = "OP-P03-REASSIGN-OK"
        req_reassign_ok["obligations"][1]["skip_reverification"] = False
        res_ra = _run_full_lifecycle(fx_f, "OP-P03-REASSIGN-OK", req_reassign_ok, include_preview=False)
        self.assertTrue(res_ra["publish"]["published"])
        sem_ra = res_ra["prepare"]["stage5_semantics"]
        t101_r = next(r for r in sem_ra["reverification_summary"]["tasks"] if r["task_id"] == 101)
        t102_r = next(r for r in sem_ra["reverification_summary"]["tasks"] if r["task_id"] == 102)
        self.assertFalse(t101_r["requires_reverification"])
        self.assertTrue(t102_r["requires_reverification"])

        # Dropping OBL-REWARD-EXTRA from Task 102 without remove_task_obligation MUST block!
        req_drop_task_obl = copy.deepcopy(req_f1)
        req_drop_task_obl["operation_id"] = "OP-P03-DROP-TOBL"
        with self.assertRaises(codec.CodecError) as ctx_dt:
            s5.build(fx_f.root, req_drop_task_obl)
        self.assertEqual(ctx_dt.exception.diagnostic.reason_code, codec.ReasonCode.SEMANTIC_ERROR)

        # Reject logs/ path in retirement authority_ref!
        fx_f.put("logs/ci/fake-retire.md", "# Not a formal spec\n")
        req_log_ret = copy.deepcopy(req_drop_task_obl)
        req_log_ret["operation_id"] = "OP-P03-LOG-RET"
        req_log_ret["obligation_retirements"] = [
            {
                "target_id": "102:OBL-REWARD-EXTRA",
                "kind": "remove_task_obligation",
                "obligation_id": "OBL-REWARD-EXTRA",
                "authority_ref": "logs/ci/fake-retire.md",
                "authority_review": {"status": "reviewed", "rationale": "Attempted log-only retirement."},
            }
        ]
        with self.assertRaises(codec.CodecError) as ctx_lret:
            s5.build(fx_f.root, req_log_ret)
        self.assertEqual(ctx_lret.exception.diagnostic.reason_code, codec.ReasonCode.UNSAFE_PATH)

        # Reviewed non-log ADR retirement with remove_task_obligation succeeds AND records OwnedRef + retired_items
        # cleanly verifiable on a clean clone after deleting logs/!
        req_good_ret = copy.deepcopy(req_drop_task_obl)
        req_good_ret["operation_id"] = "OP-P03-GOOD-RET"
        req_good_ret["obligation_retirements"] = [
            {
                "target_id": "102:OBL-REWARD-EXTRA",
                "kind": "remove_task_obligation",
                "obligation_id": "OBL-REWARD-EXTRA",
                "authority_ref": a_f["retire_spec_path"],
                "authority_review": {
                    "status": "reviewed",
                    "rationale": "Task 102 no longer owns OBL-REWARD-EXTRA per ADR-9999.",
                },
            }
        ]
        res_ret = _run_full_lifecycle(fx_f, "OP-P03-GOOD-RET", req_good_ret, include_preview=False)
        self.assertTrue(res_ret["publish"]["published"])
        b_ret = fx_f.read_json(f"docs/planning/b-route/bindings/{fx_f.plan_id}/4.json")
        self.assertTrue(
            any(r["owner"] == "authority" and r["ref"] == a_f["retire_spec_path"] for r in b_ret["other_verification_refs"])
        )
        shutil.rmtree(fx_f.root / "logs")
        clean_sem = s5.extract_stage5_semantics(fx_f.read_json(a_f["plan_ref"]["path"]), b_ret)
        self.assertEqual(len(clean_sem["retired_items"]), 1)
        self.assertEqual(clean_sem["retired_items"][0]["kind"], "remove_task_obligation")
        self.assertEqual(clean_sem["retired_items"][0]["authority_ref"], a_f["retire_spec_path"])

    def test_p04_cli_foreign_operation_guard_and_read_manifest_verification(self) -> None:
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=False)
        op_id = "OP-P04-CLI-001"
        req = self._flow_request(op_id, assets)
        res = _run_full_lifecycle(self.fx, op_id, req, include_preview=False)
        self.assertTrue(res["publish"]["published"])

        # 1. Create a foreign (3B adoption OPERATION_SCHEMA) operation in the journal store and verify CLI rejects it
        #    across apply/verify/publish/recover-inspect/recover/read with SCHEMA_MISMATCH!
        foreign_op_id = "OP-P04-FOREIGN-3B"
        s5_env = journal.read_operation(self.fx.root, operation_id=op_id)
        foreign_env = copy.deepcopy(s5_env)
        foreign_env["schema_version"] = journal.OPERATION_SCHEMA
        foreign_env["operation_id"] = foreign_op_id
        foreign_path = self.fx.root / journal._operation_ref(foreign_op_id)
        foreign_path.parent.mkdir(parents=True, exist_ok=True)
        foreign_path.write_bytes(_encoded(foreign_env))

        import io
        import contextlib

        def _call_s5_cli(argv: list[str]) -> tuple[int, dict]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = s5_cli.main(["--root", str(self.fx.root), *argv])
            return rc, json.loads(buf.getvalue().strip())

        with patch.object(journal, "operation_inventory", return_value=[s5_env, foreign_env]):
            for stg in ("apply", "verify", "publish", "recover-inspect", "recover", "read"):
                rc_f, out_f = _call_s5_cli(["--stage", stg, "--operation-id", foreign_op_id])
                self.assertEqual(rc_f, 1, f"stage={stg} out={out_f}")
                self.assertEqual(out_f["diagnostics"][0]["reason_code"], codec.ReasonCode.SCHEMA_MISMATCH.value)
        foreign_path.unlink()
        foreign_path.parent.rmdir()

        # 2. Tamper with bound MVG manifest on disk after publish -> --stage read MUST fail closed with DIGEST_MISMATCH!
        m_disk = self.fx.root / assets["mvg_manifest_path"]
        m_disk.write_bytes(m_disk.read_bytes() + b"\n")
        rc_tamp, out_tamp = _call_s5_cli(["--stage", "read", "--operation-id", op_id])
        self.assertEqual(rc_tamp, 1, out_tamp)
        self.assertEqual(out_tamp["diagnostics"][0]["reason_code"], codec.ReasonCode.DIGEST_MISMATCH.value)

    def test_p05_input_set_candidate_overlay_precedence_noncatalog_flows_and_stage5_attribution(self) -> None:
        # 1. candidate_overlay precedence: alphabetically earlier committed plan-combat shares Task 101
        #    and binds old pre-delta reward-baseline.json (containing both flow-reward-select and flow-combat-finish);
        #    candidate Stage-5 plan-reward applies delta via manifest_deltas!
        fx_ov = Stage5RepoFixture()
        self.addCleanup(fx_ov.cleanup)
        a_ov = fx_ov.build_committed_stage4(mode="flow", include_other_plan=True)
        # Extend reward-baseline.json to also include flow-combat-finish so plan-combat validly binds it!
        fx_ov.put(
            "Game.Core/Contracts/Combat/FinishCombatCommand.cs",
            "namespace Game.Core.Contracts.Combat;\npublic sealed record FinishCombatCommand(string RunId);\n",
        )
        shared_m_doc = copy.deepcopy(a_ov["mvg_manifest_doc"])
        shared_m_doc["coverage"]["mode"] = "critical"
        shared_m_doc["coverage"]["required_flow_ids"] = ["flow-reward-select", "flow-combat-finish"]
        shared_m_doc["flows"].append(
            {
                "id": "flow-combat-finish",
                "task_ids": [101],
                "outcome": "Combat ends cleanly and offers rewards.",
                "source_paths": ["Game.Core/Services/CombatService.cs"],
                "test_ids": ["test-combat-flow"],
                "handoffs": [
                    {
                        "producer_task": 101,
                        "consumer_task": 101,
                        "owner_task": 101,
                        "contract_ref": "Game.Core/Contracts/Combat/FinishCombatCommand.cs",
                        "behavior": "Combat victory transitions to reward selection.",
                        "test_ids": ["test-combat-flow"],
                    }
                ],
            }
        )
        shared_m_doc["tests"].append(
            {
                "id": "test-combat-flow",
                "kind": "dotnet",
                "evidence_level": "domain-integration",
                "path": "Game.Core.Tests/Combat/CombatFlowTests.cs",
                "selector": "CombatFlowTests",
                "state": "implemented",
                "min_tests": 1,
            }
        )
        shared_m_raw = fx_ov.put_json(a_ov["mvg_manifest_path"], shared_m_doc)
        shared_m_ref = _owned_ref("manifest", a_ov["mvg_manifest_path"], [(a_ov["mvg_manifest_path"], shared_m_raw)])
        # Bind the pre-delta shared manifest onto committed plan-combat (which sorts BEFORE plan-reward!)
        combat_b_rel = a_ov["other_binding_ref"]["path"]
        combat_b = fx_ov.read_json(combat_b_rel)
        combat_b["manifest_refs"] = [shared_m_ref]
        combat_b_raw = fx_ov.put_json(combat_b_rel, combat_b)
        combat_b_ref = _typed_ref(combat_b_rel, "newrouge.b-route-binding.v1", fx_ov.other_plan_id, 1, combat_b_raw)
        origins_doc = fx_ov.read_json("docs/planning/b-route/task-origins.v1.json")
        for trow in origins_doc["tasks"]:
            trow["binding_refs"] = [combat_b_ref if r["entity_id"] == fx_ov.other_plan_id else r for r in trow["binding_refs"]]
        origins_raw = fx_ov.put_json("docs/planning/b-route/task-origins.v1.json", origins_doc)
        origins_ref = _typed_ref("docs/planning/b-route/task-origins.v1.json", "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)
        rec_rel = "docs/planning/b-route/commits/OP-BOOT-STAGE4.json"
        rec_doc = fx_ov.read_json(rec_rel)
        for tgt in rec_doc["targets"]:
            if tgt["path"] == combat_b_rel:
                tgt["after_digest"] = tgt["projection_digest"] = codec.raw_digest(combat_b_raw)
            elif tgt["path"] == "docs/planning/b-route/task-origins.v1.json":
                tgt["after_digest"] = tgt["projection_digest"] = codec.raw_digest(origins_raw)
        rec_doc["binding_refs"] = [combat_b_ref if r["entity_id"] == fx_ov.other_plan_id else r for r in rec_doc["binding_refs"]]
        rec_raw = fx_ov.put_json(rec_rel, rec_doc)
        rec_ref = _typed_ref(rec_rel, "newrouge.b-route-commit.v1", "OP-BOOT-STAGE4", 1, rec_raw)
        cat_doc = fx_ov.read_json(records.CATALOG_PATH)
        cat_doc["origins_ref"] = origins_ref
        for head in cat_doc["scope_heads"]:
            head["receipt_ref"] = rec_ref
            head["binding_refs"] = [combat_b_ref if r["entity_id"] == fx_ov.other_plan_id else r for r in head["binding_refs"]]
        for tidx in cat_doc["task_index"]:
            tidx["binding_refs"] = [combat_b_ref if r["entity_id"] == fx_ov.other_plan_id else r for r in tidx["binding_refs"]]
        fx_ov.put_json(records.CATALOG_PATH, cat_doc)

        # Now apply a delta adding test-reward-extra on plan-reward (alphabetically AFTER plan-combat!).
        delta = {
            "schema_version": update_mvg_baseline.DELTA_SCHEMA,
            "expected_manifest_sha256": update_mvg_baseline._canonical_sha(shared_m_doc),
            "change_plan_sha256": "sha256:" + "b" * 64,
            "test_operations": [
                {
                    "id": "test-reward-extra",
                    "action": "add",
                    "reason": "Add second test under shared manifest.",
                    "value": {
                        "id": "test-reward-extra",
                        "kind": "dotnet",
                        "evidence_level": "domain-integration",
                        "path": "Game.Core.Tests/Reward/RewardExtraTests.cs",
                        "selector": "RewardExtraTests",
                        "state": "implemented",
                        "min_tests": 1,
                    },
                }
            ],
            "flow_operations": [
                {
                    "id": "flow-reward-select",
                    "action": "update",
                    "reason": "Bind extra test.",
                    "field_updates": {"test_ids": ["test-reward-flow", "test-reward-extra"]},
                }
            ],
        }
        after_doc = update_mvg_baseline.apply_delta(shared_m_doc, delta, root=fx_ov.root, validate_final=False)
        after_raw = (json.dumps(after_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        post_mref = _owned_ref("manifest", a_ov["mvg_manifest_path"], [(a_ov["mvg_manifest_path"], after_raw)])
        req_ov = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P05-OVERLAY",
            "plan_id": fx_ov.plan_id,
            "scope_id": fx_ov.scope_id,
            "manifest_refs": [post_mref],
            "other_verification_refs": [],
            "manifest_deltas": [{"manifest_path": a_ov["mvg_manifest_path"], "delta": delta}],
            "obligations": [
                {
                    "id": "OBL-REWARD-1",
                    "task_ids": [101, 102],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow", "test-reward-extra"],
                    "category": "current_new",
                    "responsibility": "Verify reward flow with delta.",
                    "verification_refs": [post_mref],
                }
            ],
        }
        # Direct resolve_input_set proves candidate_overlay took precedence over alphabetically earlier committed plan-combat!
        cand_b = copy.deepcopy(fx_ov.read_json(a_ov["prior_binding_ref"]["path"]))
        cand_b["stage"] = "5"
        cand_b["binding_revision"] = 2
        cand_b["manifest_refs"] = [post_mref]
        cand_b["obligations"][0]["test_ids"] = ["test-reward-flow", "test-reward-extra"]
        cand_b["obligations"][0]["verification_refs"] = [post_mref]
        cand_b_path = f"docs/planning/b-route/bindings/{fx_ov.plan_id}/2.json"
        cand_b_raw = _encoded(cand_b)
        res_ov = input_set.resolve_input_set(
            fx_ov.root,
            101,
            candidate_binding=cand_b_path,
            candidate_overlay={cand_b_path: cand_b_raw, a_ov["mvg_manifest_path"]: after_raw},
        )
        self.assertTrue(res_ov["ok"], res_ov["diagnostics"])
        self.assertTrue(res_ov["valid_input_set"], res_ov["diagnostics"])
        mvg_items = [i for i in res_ov["items"] if i["category"] == "mvg_manifest" and i["locator"] == a_ov["mvg_manifest_path"]]
        self.assertEqual(len(mvg_items), 1)
        self.assertEqual(mvg_items[0]["raw_digest"], codec.raw_digest(after_raw))
        self.assertFalse(mvg_items[0]["committed"])
        # Mutating the shared manifest in place via s5.build while committed plan-combat still pins the old raw_digest
        # must fail closed during published-bundle catalog validation (DIGEST_MISMATCH).
        with self.assertRaises(codec.CodecError) as ctx_ov:
            s5.build(fx_ov.root, req_ov)
        self.assertEqual(ctx_ov.exception.diagnostic.reason_code, codec.ReasonCode.DIGEST_MISMATCH)

        # 2. STAGE5_OBL_PREFIX non_catalog_flow_ids in input_set AND return_stage == "5" on BOTH
        #    Stage-5 flow_peer_task addition (with cross-plan Stage-4 binding on peer!) AND removal (Flow retirement)!
        fx_nc = Stage5RepoFixture()
        self.addCleanup(fx_nc.cleanup)
        a_nc = fx_nc.build_committed_stage4(
            mode="nonflow",
            include_other_plan=True,
            include_legacy_cumulative_flow=True,
        )
        # Put SelectRewardCommand.cs on sibling plan-combat's Stage-4 implementation_objects so input_set already
        # observes SelectRewardCommand.cs in extra_contract_refs before baseline AND after retirement (without
        # adding it to Task 101's own contractRefs, which would keep flow-reward-select/flow-legacy-map impacted).
        cb_rel = a_nc["other_binding_ref"]["path"]
        cb_doc = fx_nc.read_json(cb_rel)
        cmd_raw_nc = (fx_nc.root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs").read_bytes()
        cmd_owned_nc = _owned_ref(
            "contract",
            "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", cmd_raw_nc)],
        )
        cb_doc["implementation_objects"].append(
            {
                "id": "cmd-combat-reward-handoff",
                "kind": "command",
                "availability": "existing",
                "responsible_task_ids": [101],
                "expected_type": "SelectRewardCommand",
                "lifecycle": "Combat victory hands off to reward selection.",
                "target_ref": cmd_owned_nc,
                "later_checks": ["type"],
            }
        )
        cb_doc["task_mappings"].append(
            {
                "task_id": 102,
                "view_refs": [{"view": "back", "business_id": "NG-0102"}],
                "requirement_ids": ["REQ-COMBAT-1"],
                "flow_ids": ["flow-combat-finish"],
                "part_kinds": ["domain_rules"],
                "roles": ["consumer"],
                "obligation_ids": ["OBL-COMBAT-1"],
            }
        )
        cb_raw = fx_nc.put_json(cb_rel, cb_doc)
        cb_ref = _typed_ref(cb_rel, "newrouge.b-route-binding.v1", fx_nc.other_plan_id, 1, cb_raw)
        orig_nc = fx_nc.read_json("docs/planning/b-route/task-origins.v1.json")
        for trow in orig_nc["tasks"]:
            trow["binding_refs"] = [cb_ref if r["entity_id"] == fx_nc.other_plan_id else r for r in trow["binding_refs"]]
        orig_nc["tasks"].append(
            {
                "task_id": 102,
                "source_refs": copy.deepcopy(orig_nc["tasks"][0]["source_refs"]),
                "plan_refs": [a_nc["other_plan_ref"]],
                "binding_refs": [cb_ref],
            }
        )
        orig_nc_raw = fx_nc.put_json("docs/planning/b-route/task-origins.v1.json", orig_nc)
        orig_nc_ref = _typed_ref("docs/planning/b-route/task-origins.v1.json", "newrouge.b-route-origins.v1", "task-origins", 1, orig_nc_raw)
        rec_nc_rel = "docs/planning/b-route/commits/OP-BOOT-STAGE4.json"
        rec_nc = fx_nc.read_json(rec_nc_rel)
        for tgt in rec_nc["targets"]:
            if tgt["path"] == cb_rel:
                tgt["after_digest"] = tgt["projection_digest"] = codec.raw_digest(cb_raw)
            elif tgt["path"] == "docs/planning/b-route/task-origins.v1.json":
                tgt["after_digest"] = tgt["projection_digest"] = codec.raw_digest(orig_nc_raw)
        rec_nc["binding_refs"] = [cb_ref if r["entity_id"] == fx_nc.other_plan_id else r for r in rec_nc["binding_refs"]]
        rec_nc_raw = fx_nc.put_json(rec_nc_rel, rec_nc)
        rec_nc_ref = _typed_ref(rec_nc_rel, "newrouge.b-route-commit.v1", "OP-BOOT-STAGE4", 1, rec_nc_raw)
        cat_nc = fx_nc.read_json(records.CATALOG_PATH)
        cat_nc["origins_ref"] = orig_nc_ref
        for head in cat_nc["scope_heads"]:
            head["receipt_ref"] = rec_nc_ref
            head["binding_refs"] = [cb_ref if r["entity_id"] == fx_nc.other_plan_id else r for r in head["binding_refs"]]
        for tidx in cat_nc["task_index"]:
            tidx["binding_refs"] = [cb_ref if r["entity_id"] == fx_nc.other_plan_id else r for r in tidx["binding_refs"]]
        cat_nc["task_index"].append({"task_id": 102, "plan_refs": [a_nc["other_plan_ref"]], "binding_refs": [cb_ref]})
        fx_nc.put_json(records.CATALOG_PATH, cat_nc)

        # Baseline BEFORE Stage-5 non-catalog Flow binding (Task 101 has no flow_peer_task 102 yet).
        base_before_flow = input_set.resolve_input_set(fx_nc.root, 101)
        self.assertTrue(base_before_flow["ok"], base_before_flow["diagnostics"])
        self.assertFalse(any(i["locator"] == "flow_peer:task:102" for i in base_before_flow["items"]))

        # Publish Stage-5 binding adding non-catalog flow-legacy-map (introduces flow_peer:task:102)!
        req_add_nc = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P05-ADD-NC",
            "plan_id": fx_nc.plan_id,
            "scope_id": fx_nc.scope_id,
            "manifest_refs": [a_nc["mvg_manifest_ref"]],
            "other_verification_refs": [a_nc["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["Game.Core/Services/CombatService.cs"],
                "reverse_impact_known": True,
                "cumulative_manifest_refs": [a_nc["mvg_manifest_ref"]],
            },
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "current_new",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [a_nc["other_verif_ref"]],
                },
                {
                    "id": "OBL-REG-LEGACY",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": ["flow-legacy-map"],
                    "test_ids": ["test-legacy-map"],
                    "category": "existing_required",
                    "responsibility": "Regression check for legacy map flow.",
                    "verification_refs": [a_nc["mvg_manifest_ref"]],
                },
            ],
        }
        self.assertTrue(_run_full_lifecycle(fx_nc, "OP-P05-ADD-NC", req_add_nc, include_preview=False)["publish"]["published"])
        after_add_flow = input_set.resolve_input_set(fx_nc.root, 101, baseline=base_before_flow)
        self.assertTrue(after_add_flow["valid_input_set"])
        self.assertTrue(any(i["locator"] == "flow_peer:task:102" for i in after_add_flow["items"]))
        self.assertEqual(after_add_flow["freshness"]["return_stage"], "5", after_add_flow["freshness"]["invalidated_items"])

        # Now retire OBL-REG-LEGACY + remove_manifest_ref via reviewed ADR (removing flow_peer:task:102) -> return_stage == "5"!
        base_with_flow = input_set.resolve_input_set(fx_nc.root, 101)
        self.assertTrue(base_with_flow["ok"])
        req_ret_nc = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P05-RET-NC",
            "plan_id": fx_nc.plan_id,
            "scope_id": fx_nc.scope_id,
            "manifest_refs": [],
            "other_verification_refs": [a_nc["other_verif_ref"]],
            "impact_analysis": {
                "touched_paths": ["docs/workflows/standalone-tool.md"],
                "reverse_impact_known": True,
            },
            "obligation_retirements": [
                {
                    "target_id": "OBL-REG-LEGACY",
                    "kind": "retire_obligation",
                    "authority_ref": a_nc["retire_spec_path"],
                    "authority_review": {"status": "reviewed", "rationale": "Legacy flow regression retired per ADR-9999."},
                },
                {
                    "target_id": a_nc["mvg_manifest_path"],
                    "kind": "remove_manifest_ref",
                    "authority_ref": a_nc["retire_spec_path"],
                    "authority_review": {"status": "reviewed", "rationale": "Manifest ref removed after regression retirement."},
                },
            ],
            "obligations": [
                {
                    "id": "OBL-TOOL-1",
                    "task_ids": [101],
                    "requirement_ids": ["REQ-TOOL-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "category": "existing_required",
                    "responsibility": "Verify non-flow checklist.",
                    "verification_refs": [a_nc["other_verif_ref"]],
                }
            ],
        }
        self.assertTrue(_run_full_lifecycle(fx_nc, "OP-P05-RET-NC", req_ret_nc, include_preview=False)["publish"]["published"])
        after_ret_flow = input_set.resolve_input_set(fx_nc.root, 101, baseline=base_with_flow)
        self.assertTrue(after_ret_flow["valid_input_set"])
        self.assertFalse(any(i["locator"] == "flow_peer:task:102" for i in after_ret_flow["items"]))
        self.assertEqual(after_ret_flow["freshness"]["return_stage"], "5", after_ret_flow["freshness"]["invalidated_items"])

        # 3. Stage-4 -> Stage-5 reviewed retirement of an obligation carrying STAGE4_OBL_PREFIX
        #    MUST report return_stage == "5" (NOT "4")!
        fx_s4r = Stage5RepoFixture()
        self.addCleanup(fx_s4r.cleanup)
        a_s4r = fx_s4r.build_committed_stage4(mode="flow", include_other_plan=False)
        base_s4 = input_set.resolve_input_set(fx_s4r.root, 101)
        self.assertTrue(base_s4["ok"])
        req_ret_s4 = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": "OP-P05-RET-S4OBL",
            "plan_id": fx_s4r.plan_id,
            "scope_id": fx_s4r.scope_id,
            "manifest_refs": [a_s4r["mvg_manifest_ref"]],
            "other_verification_refs": [],
            "obligation_retirements": [
                {
                    "target_id": "OBL-REWARD-1",
                    "kind": "retire_obligation",
                    "authority_ref": a_s4r["retire_spec_path"],
                    "authority_review": {"status": "reviewed", "rationale": "Replaced OBL-REWARD-1 with OBL-REWARD-V2 per ADR-9999."},
                }
            ],
            "obligations": [
                {
                    "id": "OBL-REWARD-V2",
                    "task_ids": [101, 102],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow"],
                    "category": "current_new",
                    "responsibility": "Consolidated Stage-5 reward verification.",
                    "verification_refs": [a_s4r["mvg_manifest_ref"]],
                }
            ],
        }
        self.assertTrue(_run_full_lifecycle(fx_s4r, "OP-P05-RET-S4OBL", req_ret_s4, include_preview=False)["publish"]["published"])
        after_s4_ret = input_set.resolve_input_set(fx_s4r.root, 101, baseline=base_s4)
        self.assertTrue(after_s4_ret["valid_input_set"])
        self.assertEqual(after_s4_ret["freshness"]["return_stage"], "5", after_s4_ret["freshness"]["invalidated_items"])

    def test_p06_validate_operations_compensation_build_policy_and_ci_filters(self) -> None:
        # 1. Policy observations pin _mvg_manifest.py and update_mvg_baseline.py; CI workflow includes both.
        _ident, pinned_files = adoption_review.policy_observations()
        self.assertTrue(any(p.endswith("_mvg_manifest.py") for p in pinned_files))
        self.assertTrue(any(p.endswith("update_mvg_baseline.py") for p in pinned_files))
        wf_text = (REPO_ROOT / ".github/workflows/b-route-runtime-deterministic.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/python/_mvg_manifest.py", wf_text)
        self.assertIn("scripts/python/update_mvg_baseline.py", wf_text)

        # 2. adoption.validate_operations(journal.operation_inventory(root)) on a Stage-5 op WITH public_sync_entries!
        assets = self.fx.build_committed_stage4(mode="flow", include_other_plan=False)
        # Align OP-BOOT-STAGE4 receipt with a real frozen 3B operation so step 3 can verify Story 2.8
        # compensation.build(...) against an unbroken formal receipt chain retaining the Stage-5 binding.
        import base64
        import _b_route_commit_projection as projection

        orig_3b_id = "OP-BOOT-STAGE4"
        policy_path = records.BASE + "policy.v1.json"
        origins_path = records.BASE + "task-origins.v1.json"
        plan_path = assets["plan_ref"]["path"]
        prior_b_path = assets["prior_binding_ref"]["path"]
        policy_doc = self.fx.read_json(policy_path)
        origins_doc = self.fx.read_json(origins_path)
        plan_doc = self.fx.read_json(plan_path)
        prior_b_doc = self.fx.read_json(prior_b_path)
        dummy_ref = {
            "path": policy_path,
            "schema_version": "newrouge.b-route-policy.v1",
            "raw_digest": codec.raw_digest((self.fx.root / policy_path).read_bytes()),
        }
        orig_3b_req = {
            "schema_version": "newrouge.b-route-adoption-request.v1",
            "operation_id": orig_3b_id,
            "material": {
                "planner": "capabilities",
                "run_id": "RUN-3B-ORIG-001",
                "handoff_ref": dummy_ref,
                "protection_ref": dummy_ref,
                "authority_refs": [],
                "identity_alignment": {
                    "plan": {"plan_id": self.fx.plan_id},
                    "binding": {},
                    "requirements": [],
                    "flows": [],
                    "tasks": [],
                },
                "target_templates": [{"path": plan_path}],
                "lineage_refs": [],
            },
            "review_ref": dummy_ref,
        }
        orig_3b_req_raw = _encoded(orig_3b_req)
        orig_3b_frozen = {
            "request": orig_3b_req,
            "allocations": {
                "plan_id": self.fx.plan_id,
                "plan_revision": 1,
                "binding_revision": 1,
                "requirements": {"REQ-REWARD-1": "REQ-REWARD-1"},
                "flows": {"flow-reward-select": "flow-reward-select"},
                "task_definitions": {},
            },
            "scope_ids": [self.fx.scope_id],
            "authority_refs": [],
            "targets": [
                {
                    "path": policy_path,
                    "schema_version": "newrouge.b-route-policy.v1",
                    "before_raw_digest": None,
                    "after_payload": policy_doc,
                    "after_raw_digest": codec.raw_digest((self.fx.root / policy_path).read_bytes()),
                    "verification_mode": "immutable_bytes",
                },
                {
                    "path": origins_path,
                    "schema_version": "newrouge.b-route-origins.v1",
                    "before_raw_digest": None,
                    "after_payload": origins_doc,
                    "after_raw_digest": codec.raw_digest((self.fx.root / origins_path).read_bytes()),
                    "verification_mode": "immutable_bytes",
                },
                {
                    "path": plan_path,
                    "schema_version": adoption.PLAN,
                    "before_raw_digest": None,
                    "after_payload": plan_doc,
                    "after_raw_digest": codec.raw_digest((self.fx.root / plan_path).read_bytes()),
                    "verification_mode": "immutable_bytes",
                },
                {
                    "path": prior_b_path,
                    "schema_version": adoption.BINDING,
                    "before_raw_digest": None,
                    "after_payload": prior_b_doc,
                    "after_raw_digest": codec.raw_digest((self.fx.root / prior_b_path).read_bytes()),
                    "verification_mode": "immutable_bytes",
                },
            ],
        }
        orig_3b_env = {
            "schema_version": journal.OPERATION_SCHEMA,
            "codec_version": codec.CODEC_VERSION,
            "operation_id": orig_3b_id,
            "state": "reserved",
            "request_raw_base64": base64.b64encode(orig_3b_req_raw).decode("ascii"),
            "request_raw_digest": codec.raw_digest(orig_3b_req_raw),
            "request_digest": codec.canonical_digest(orig_3b_req),
            "frozen": orig_3b_frozen,
            "frozen_digest": codec.canonical_digest(orig_3b_frozen),
        }
        boot_receipt_rel = records.BASE + f"commits/{orig_3b_id}.json"
        old_boot_receipt = self.fx.read_json(boot_receipt_rel)
        orig_3b_receipt = projection.receipt_for_frozen(
            operation_id=orig_3b_id,
            frozen=orig_3b_frozen,
            resolved_definitions=old_boot_receipt["resolved_definitions"],
            catalog_before=None,
        )
        orig_3b_receipt_raw = projection.serialized(orig_3b_receipt)
        (self.fx.root / boot_receipt_rel).write_bytes(orig_3b_receipt_raw)
        orig_3b_receipt_ref = projection.reference(boot_receipt_rel, orig_3b_receipt_raw)
        cat_rev1 = self.fx.read_json(records.CATALOG_PATH)
        for head in cat_rev1["scope_heads"]:
            head["receipt_ref"] = orig_3b_receipt_ref
        cat_rev1_raw = self.fx.put_json(records.CATALOG_PATH, cat_rev1)
        orig_3b_intent = commit._seal(
            {
                "schema_version": commit.SCHEMA,
                "operation_id": orig_3b_id,
                "frozen_digest": orig_3b_env["frozen_digest"],
                "policy_identity": _ident,
                "phase": "complete",
                "before_files": {
                    policy_path: None,
                    origins_path: None,
                    plan_path: None,
                    prior_b_path: None,
                    records.CATALOG_PATH: None,
                },
                "files": {},
                "directories": {},
                "trees": {},
                "receipt": orig_3b_receipt,
                "catalog_before": None,
                "catalog_after": base64.b64encode(cat_rev1_raw).decode("ascii"),
                "publication_base": None,
                "catalog_attempts": [],
                "catalog_frame": None,
                "origins_before": None,
            }
        )

        before_doc = assets["mvg_manifest_doc"]
        delta = {
            "schema_version": update_mvg_baseline.DELTA_SCHEMA,
            "expected_manifest_sha256": update_mvg_baseline._canonical_sha(before_doc),
            "change_plan_sha256": "sha256:" + "c" * 64,
            "test_operations": [
                {
                    "id": "test-reward-extra",
                    "action": "add",
                    "reason": "Add second test for validate_operations coverage.",
                    "value": {
                        "id": "test-reward-extra",
                        "kind": "dotnet",
                        "evidence_level": "domain-integration",
                        "path": "Game.Core.Tests/Reward/RewardExtraTests.cs",
                        "selector": "RewardExtraTests",
                        "state": "implemented",
                        "min_tests": 1,
                    },
                }
            ],
            "flow_operations": [
                {
                    "id": "flow-reward-select",
                    "action": "update",
                    "reason": "Bind second test.",
                    "field_updates": {"test_ids": ["test-reward-flow", "test-reward-extra"]},
                }
            ],
        }
        after_doc = update_mvg_baseline.apply_delta(before_doc, delta, root=self.fx.root, validate_final=False)
        after_raw = (json.dumps(after_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        post_mref = _owned_ref("manifest", assets["mvg_manifest_path"], [(assets["mvg_manifest_path"], after_raw)])
        op_s5 = "OP-P06-SYNC-VAL"
        req_s5 = {
            "schema_version": s5.REQUEST_SCHEMA,
            "producer": s5.PRODUCER,
            "operation_id": op_s5,
            "plan_id": self.fx.plan_id,
            "scope_id": self.fx.scope_id,
            "manifest_refs": [post_mref],
            "other_verification_refs": [],
            "manifest_deltas": [{"manifest_path": assets["mvg_manifest_path"], "delta": delta}],
            "obligations": [
                {
                    "id": "OBL-REWARD-1",
                    "task_ids": [101, 102],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow", "test-reward-extra"],
                    "category": "current_new",
                    "responsibility": "Verify reward flow with public sync.",
                    "verification_refs": [post_mref],
                }
            ],
        }
        res_s5 = _run_full_lifecycle(self.fx, op_s5, req_s5, include_preview=False)
        self.assertTrue(res_s5["publish"]["published"])
        inv = journal.operation_inventory(self.fx.root)
        self.assertEqual(len(inv[0]["frozen"]["binding_meta"]["public_sync_entries"]), 1)
        adoption.validate_operations(inv)

        # Stripping a public_sync file scope must fail validate_operations with PENDING!
        bad_inv = copy.deepcopy(inv)
        pub_scope = op_scope.resource_scopes(target_paths=[assets["mvg_manifest_path"]])[0]
        bad_inv[0]["frozen"]["scope_ids"] = [s for s in bad_inv[0]["frozen"]["scope_ids"] if s != pub_scope]
        with self.assertRaises(codec.CodecError) as ctx_v:
            adoption.validate_operations(bad_inv)
        self.assertEqual(ctx_v.exception.diagnostic.reason_code, codec.ReasonCode.PENDING)

        # 3. Story 2.8 compensation.build(...) on a repo with a committed stage="5" binding when
        #    compensating an earlier 3B adoption operation retains/advances the stage="5" binding_ref!
        s5_b_path = f"docs/planning/b-route/bindings/{self.fx.plan_id}/2.json"
        s5_b_raw = (self.fx.root / s5_b_path).read_bytes()
        s5_b_ref = _typed_ref(s5_b_path, "newrouge.b-route-binding.v1", self.fx.plan_id, 2, s5_b_raw)

        orig_3b_path = self.fx.root / journal._operation_ref(orig_3b_id)
        orig_3b_path.parent.mkdir(parents=True, exist_ok=True)
        orig_3b_path.write_bytes(_encoded(orig_3b_env))
        orig_3b_intent_path = self.fx.root / commit._paths(orig_3b_id)[0]
        orig_3b_intent_path.parent.mkdir(parents=True, exist_ok=True)
        orig_3b_intent_path.write_bytes(_encoded(orig_3b_intent))

        comp_req = {
            "schema_version": compensation.REQUEST,
            "producer": "compensation",
            "operation_id": "OP-COMP-S5-001",
            "compensates": compensation.relation_for(orig_3b_env),
            "selection": {
                "plan_ref": assets["plan_ref"],
                "binding_ref": s5_b_ref,
            },
            "reason": "Compensate 3B adoption while retaining committed Stage-5 obligations binding.",
        }
        full_inv = [*inv, orig_3b_env]
        with (
            patch.object(journal, "operation_inventory", return_value=full_inv),
            patch.object(compensation, "_original_review", return_value=([], [])),
        ):
            _snap_c, comp_frozen = compensation.build(self.fx.root, comp_req)
        self.assertEqual(comp_frozen["producer"], "compensation")
        self.assertEqual(comp_frozen["allocations"]["plan_revision"], 2)
        self.assertEqual(comp_frozen["allocations"]["binding_revision"], 3)
        comp_binding_tgt = next(t for t in comp_frozen["targets"] if t["schema_version"] == adoption.BINDING)
        self.assertEqual(comp_binding_tgt["after_payload"]["stage"], "5")
        self.assertEqual(comp_binding_tgt["after_payload"]["binding_revision"], 3)
        self.assertEqual(comp_binding_tgt["after_payload"]["plan_ref"]["revision"], 2)
        self.assertEqual([m["task_id"] for m in comp_binding_tgt["after_payload"]["task_mappings"]], [101, 102])


if __name__ == "__main__":
    unittest.main()
