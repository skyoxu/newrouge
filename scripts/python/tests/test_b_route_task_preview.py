"""Deterministic tests for Story 3.1 read-only 3C task-change preview.

Covers every row of the Story 3.1 I/O & Edge-Case Matrix (HAPPY/ZERO, M2M,
NON_FLOW, MATURE, GAP_DRIFT), fresh subprocess CLI exit codes 0/1/2 without -B,
zero target file mutation, and zero __pycache__/.pyc generation.
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
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPTS_PY = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_PY.parents[1]
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_codec as codec
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_records as records
import _b_route_sources as sources
import _b_route_task_preview as preview
import account_b_route_sources as sources_cli
import dev_cli
import dev_cli_builders


_CACHED_3A_PROOFS: dict[bool, tuple[tempfile.TemporaryDirectory[str], Path, dict[str, bytes], dict]] = {}


def _get_cached_3a_proof(synthetic: bool) -> tuple[Path, dict[str, bytes], dict]:
    if synthetic not in _CACHED_3A_PROOFS:
        fx = PreviewFixture()
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
    return work_root, base_files, copy.deepcopy(audit_info)


def tearDownModule() -> None:
    for work_tmp, _work_root, _base_files, _audit in _CACHED_3A_PROOFS.values():
        work_tmp.cleanup()
    _CACHED_3A_PROOFS.clear()


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


def _four_parts(
    *,
    domain: bool = True,
    adapter: bool = True,
    binding: bool = True,
    scene: bool = False,
) -> list[dict]:
    specs = [
        ("domain_rules", domain, "Core deterministic reward rules."),
        ("csharp_adapter", adapter, "Thin C# adapter forwarding commands."),
        ("binding", binding, "Resource and event binding contracts."),
        ("scene", scene, "Godot scene wiring for reward display."),
    ]
    out = []
    for kind, applicable, desc in specs:
        out.append(
            {
                "kind": kind,
                "applicability": "applicable" if applicable else "not_applicable",
                "rationale": desc if applicable else f"{kind} is not needed for this flow.",
                "responsibilities": [desc] if applicable else [],
            }
        )
    return out


class PreviewFixture:
    """Self-contained temporary repository with real 3A proof, 3B committed bundle, and triplet."""

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
        # 1. Authoritative source doc + source-set
        self.put(
            "docs/gdd/reward.md",
            "# Reward Loop\n\n## Reward Selection\nPlayer picks one reward and returns to map.\n\n"
            "## Governance Audit\nAudit reward invariants via static verification.\n\n"
            "## Future Modding\nDeferred future modding hook.\n",
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
        # 2. Local offline runner fixture (synthetic=False simulates verified model receipt locally)
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

        # 3. Run real 3A prepare
        with contextlib.redirect_stdout(io.StringIO()):
            rc_prep = sources_cli.main(
                [
                    "--stage",
                    "prepare",
                    "--root",
                    str(self.root),
                    "--run-id",
                    "run3a",
                    "--scope-id",
                    self.scope_id,
                    "--attempt-id",
                    "prep1",
                    "--source-set",
                    "docs/workflows/chapter3-source-set.json",
                ]
            )
        assert rc_prep == 0, f"3A prepare failed: rc={rc_prep}"
        date_str = dt.datetime.now(dt.timezone.utc).date().isoformat()
        prep_dir = f"logs/ci/{date_str}/b-route-sources/run3a/prep1/prepare"
        prepared_ref = f"{prep_dir}/prepared.json"
        ledger = self.read_json(f"{prep_dir}/source-blocks.json")
        manifest = self.read_json(f"{prep_dir}/source-manifest.json")
        blocks = ledger["blocks"]
        assert len(blocks) >= 1

        # 4. Run real 3A account using the prepared candidate.json template
        cand = self.read_json(f"{prep_dir}/candidate.json")
        all_ids = [row["block_id"] for row in cand["block_results"]]
        for row in cand["block_results"]:
            row["delivery_potential"] = True
            row.update(
                disposition="atomized",
                atoms=[
                    {
                        "proposal_id": "proposal:reward-order",
                        "kind": "functional",
                        "statement": "Preserve reward order and invariants.",
                        "source_block_ids": all_ids,
                        "acceptance_intent": "Selecting a reward preserves the displayed ordering.",
                        "prior_requirement_ids": [],
                        "non_task_sinks": ["sink:static-audit"],
                    }
                ],
            )
        for row in cand["batch_summaries"]:
            row["output_accounted_count"] = row["input_block_count"]
        cand_path = "logs/ci/3a-inputs/account-candidate.json"
        self.put_json(cand_path, cand)
        with contextlib.redirect_stdout(io.StringIO()):
            rc_acc = sources_cli.main(
                [
                    "--stage",
                    "account",
                    "--root",
                    str(self.root),
                    "--run-id",
                    "run3a",
                    "--scope-id",
                    self.scope_id,
                    "--attempt-id",
                    "acc1",
                    "--prepared",
                    prepared_ref,
                    "--candidate",
                    cand_path,
                ]
            )
        assert rc_acc == 0, f"3A account failed: rc={rc_acc}"
        accounted_report_ref = f"logs/ci/{date_str}/b-route-sources/run3a/acc1/account/report.json"

        # 5. Run real 3A audit
        with contextlib.redirect_stdout(io.StringIO()):
            rc_aud = sources_cli.main(
                [
                    "--stage",
                    "audit",
                    "--root",
                    str(self.root),
                    "--run-id",
                    "run3a-audit",
                    "--scope-id",
                    self.scope_id,
                    "--attempt-id",
                    "aud1",
                    "--accounted",
                    accounted_report_ref,
                    "--runner",
                    "runner.py",
                    "--expected-model",
                    expected_model,
                    "--request-budget",
                    "4",
                    "--active-budget-seconds",
                    "600",
                    "--timeout-seconds",
                    "120",
                ]
            )
        assert rc_aud == 0, f"3A audit failed: rc={rc_aud}"
        audit_report_ref = f"logs/ci/{date_str}/b-route-source-audit/run3a-audit/aud1/report.json"

        return {
            "audit_ref": audit_report_ref,
            "manifest_path": f"{prep_dir}/source-manifest.json",
            "ledger_path": f"{prep_dir}/source-blocks.json",
            "manifest": manifest,
            "ledger": ledger,
            "blocks": blocks,
        }

    def populate_from_cached_3a(self, *, synthetic: bool = False) -> dict:
        work_root, base_files, audit_info = _get_cached_3a_proof(synthetic)
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
        return audit_info

    def write_triplet(
        self,
        *,
        master_tasks: list[dict],
        back_tasks: list[dict],
        gameplay_tasks: list[dict],
    ) -> None:
        self.put_json(".taskmaster/tasks/tasks.json", {"master": {"tasks": master_tasks}})
        self.put_json(".taskmaster/tasks/tasks_back.json", back_tasks)
        self.put_json(".taskmaster/tasks/tasks_gameplay.json", gameplay_tasks)

    def write_committed_3b(
        self,
        audit_info: dict,
        *,
        requirements: list[dict],
        flows: list[dict],
        commands: list[dict] | None = None,
        states: list[dict] | None = None,
        requirement_verification: list[dict],
        requirement_route_memberships: list[dict],
        requirement_evidence: list[dict] | None = None,
        evidence_source_refs: list[dict] | None = None,
        applicability: list[dict],
        existing_binding: dict | None = None,
        origins_tasks: list[dict] | None = None,
        publish_plan_in_catalog: bool = True,
    ) -> dict:
        manifest_path = audit_info["manifest_path"]
        ledger_path = audit_info["ledger_path"]
        manifest_raw = (self.root / manifest_path).read_bytes()
        ledger_raw = (self.root / ledger_path).read_bytes()
        manifest = audit_info["manifest"]

        proof_raw = self.put_json("logs/ci/test-inputs/adoption-proof.json", {"proof": "adopted-3b"})
        adr_raw = self.put("docs/adr/ADR-0040-test.md", "# ADR-0040 Test\n")
        authority_raw = self.put("docs/workflows/authority-note.md", "# Authority Note\n")
        other_ver_raw = self.put("docs/workflows/other-ver-check.md", "# Static Audit Rule\n")

        coverage_table = [
            {k: v for k, v in row.items() if k != "evidence_ids"}
            for row in requirement_verification
        ]
        plan = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": self.plan_id,
            "revision": 1,
            "source_identity": {
                "manifest_ref": _owned_ref("source_manifest", manifest_path, [(manifest_path, manifest_raw)]),
                "ledger_ref": _owned_ref("source_ledger", ledger_path, [(ledger_path, ledger_raw)]),
                "source_revision": manifest["source_revision"],
                "source_manifest_digest": manifest["manifest_sha256"],
            },
            "requirements": requirements,
            "definitions": {
                "flows": flows,
                "commands": commands or [],
                "states": states or [],
            },
            "logical_references": [],
            "requirement_verification": requirement_verification,
            "requirement_route_memberships": requirement_route_memberships,
            "requirement_evidence": requirement_evidence or [],
            "evidence_source_refs": evidence_source_refs or [],
            "coverage_table": coverage_table,
            "applicability": applicability,
            "adoption_proof_refs": [
                _owned_ref("planning_proof", "logs/ci/test-inputs/adoption-proof.json", [("logs/ci/test-inputs/adoption-proof.json", proof_raw)])
            ],
            "lineage": {
                "previous_plan_ref": None,
                "change_summary": "Initial committed 3B plan for preview tests.",
                "identity_alignment": [],
            },
        }
        plan_path = f"docs/planning/b-route/plans/{self.plan_id}/1.json"
        plan_raw = self.put_json(plan_path, plan)
        plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", self.plan_id, 1, plan_raw)

        # Optional committed binding
        binding_refs = []
        binding_targets = []
        if existing_binding is not None:
            bdoc = copy.deepcopy(existing_binding)
            bdoc["plan_ref"] = copy.deepcopy(plan_ref)
            b_path = f"docs/planning/b-route/bindings/{self.plan_id}/{bdoc['binding_revision']}.json"
            b_raw = self.put_json(b_path, bdoc)
            b_ref = _typed_ref(b_path, "newrouge.b-route-binding.v1", self.plan_id, bdoc["binding_revision"], b_raw)
            binding_refs.append(b_ref)
            binding_targets.append((b_path, b_raw))

        policy = {
            "schema_version": "newrouge.b-route-policy.v1",
            "policy_id": "policy",
            "policy_revision": 1,
            "switch_boundary": {
                "default_route": "A",
                "a_write_allowed": True,
                "allowed_a_operations": ["chapter6"],
                "authority_refs": [
                    _owned_ref(
                        "authority",
                        "docs/workflows/authority-note.md",
                        [("docs/workflows/authority-note.md", authority_raw)],
                    )
                ],
            },
            "frozen_a_refs": [
                _owned_ref(
                    "frozen_a_inventory",
                    "docs/adr/ADR-0040-test.md",
                    [("docs/adr/ADR-0040-test.md", adr_raw)],
                )
            ],
        }
        policy_path = "docs/planning/b-route/policy.v1.json"
        policy_raw = self.put_json(policy_path, policy)
        policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy", 1, policy_raw)

        # Build origins and task_index strictly matching existing_binding if present
        origin_rows = []
        task_index = []
        if origins_tasks is not None:
            origin_rows = origins_tasks
        elif existing_binding is not None:
            src_refs = [plan["source_identity"]["manifest_ref"], plan["source_identity"]["ledger_ref"]]
            for m in existing_binding["task_mappings"]:
                tid = m["task_id"]
                origin_rows.append(
                    {
                        "task_id": tid,
                        "source_refs": copy.deepcopy(src_refs),
                        "plan_refs": [copy.deepcopy(plan_ref)],
                        "binding_refs": copy.deepcopy(binding_refs),
                    }
                )
                task_index.append(
                    {
                        "task_id": tid,
                        "plan_refs": [copy.deepcopy(plan_ref)],
                        "binding_refs": copy.deepcopy(binding_refs),
                    }
                )

        origins = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": origin_rows,
            "frozen_legacy_refs": [],
        }
        origins_path = "docs/planning/b-route/task-origins.v1.json"
        origins_raw = self.put_json(origins_path, origins)
        origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

        # Definition owners
        def_owners = []
        if publish_plan_in_catalog:
            for kind, plural in (("flow", "flows"), ("command", "commands"), ("state", "states")):
                for item in plan["definitions"][plural]:
                    def_owners.append({"kind": kind, "definition_id": item["id"], "plan_ref": copy.deepcopy(plan_ref)})

        published_plan_refs = [copy.deepcopy(plan_ref)] if publish_plan_in_catalog else []
        target_pairs = [(policy_path, policy_raw), (origins_path, origins_raw)]
        if publish_plan_in_catalog:
            target_pairs.append((plan_path, plan_raw))
        target_pairs.extend(binding_targets)

        receipt = {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": "OP-1",
            "revision": 1,
            "operation_digest": codec.canonical_digest({"op": "OP-1", "targets": [p for p, _ in target_pairs]}),
            "scopes": [self.scope_id],
            "authority": [
                {
                    "path": p,
                    "before_digest": codec.raw_digest(raw),
                    "after_digest": codec.raw_digest(raw),
                }
                for p, raw in [
                    ("docs/workflows/authority-note.md", authority_raw),
                    (manifest_path, manifest_raw),
                    (ledger_path, ledger_raw),
                    ("logs/ci/test-inputs/adoption-proof.json", proof_raw),
                ]
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
            "plan_refs": published_plan_refs,
            "binding_refs": copy.deepcopy(binding_refs),
            "resolved_definitions": [],
            "result": {
                "target_paths": [p for p, _ in target_pairs],
                "scope_ids": [self.scope_id],
            },
        }
        receipt_path = "docs/planning/b-route/commits/OP-1.json"
        receipt_raw = self.put_json(receipt_path, receipt)
        receipt_ref = _typed_ref(receipt_path, "newrouge.b-route-commit.v1", "OP-1", 1, receipt_raw)

        catalog = {
            "schema_version": "newrouge.b-route-catalog.v1",
            "catalog_id": "catalog",
            "revision": 1,
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "scope_heads": [
                {
                    "scope_id": self.scope_id,
                    "plan_refs": published_plan_refs,
                    "binding_refs": copy.deepcopy(binding_refs),
                    "receipt_ref": receipt_ref,
                }
            ],
            "definition_owners": def_owners,
            "task_index": task_index,
        }
        catalog_path = records.CATALOG_PATH
        self.put_json(catalog_path, catalog)

        return {
            "plan_path": plan_path,
            "plan_ref": plan_ref,
            "authority_raw": authority_raw,
            "other_ver_raw": other_ver_raw,
        }

    def build_base_flow(self, flow_id: str, req_ids: list[str], *, parts: list[dict] | None = None) -> dict:
        return {
            "id": flow_id,
            "requirement_ids": req_ids,
            "entry": f"enter:{flow_id}",
            "entry_condition": "player_won_combat",
            "success_end": "returned_to_map",
            "branches": [
                {"kind": "failure", "rationale": "Failure branch.", "description": "Abort cleanly."},
                {"kind": "cancel", "rationale": "Cancel branch.", "description": "Skip reward."},
                {"kind": "return", "rationale": "Return branch.", "description": "Return to map."},
            ],
            "handoffs": [
                {
                    "id": f"ho:{flow_id}",
                    "responsibility": "Deliver selected reward to run state.",
                    "state_uses": [],
                    "result": "reward_applied",
                }
            ],
            "state_owners": [],
            "parts": parts or _four_parts(domain=True, adapter=True, binding=True, scene=True),
            "observable_result": f"Flow {flow_id} completes deterministically.",
            "verification_targets": [f"test_{flow_id}_completes"],
            "loops": [],
        }


class TaskPreviewMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PreviewFixture()
        self._extra_fixtures: list[PreviewFixture] = []
        self._audit_info = self.fx.populate_from_cached_3a(synthetic=False)

    def tearDown(self) -> None:
        self.fx.cleanup()
        for extra in self._extra_fixtures:
            extra.cleanup()

    def _fresh_fixture(self, *, synthetic: bool = False) -> tuple[PreviewFixture, dict]:
        extra = PreviewFixture()
        self._extra_fixtures.append(extra)
        audit_info = extra.populate_from_cached_3a(synthetic=synthetic)
        self.fx = extra
        self._audit_info = audit_info
        return extra, audit_info

    def _standard_bundle(
        self,
        *,
        synthetic_3a: bool = False,
        master_tasks: list[dict] | None = None,
        back_tasks: list[dict] | None = None,
        gameplay_tasks: list[dict] | None = None,
        existing_binding: dict | None = None,
        origins_tasks: list[dict] | None = None,
        include_source_gap: bool = False,
        publish_plan: bool = True,
    ) -> tuple[dict, dict]:
        if synthetic_3a:
            _, audit_info = self._fresh_fixture(synthetic=True)
        else:
            audit_info = self._audit_info
        block_id = audit_info["blocks"][0]["block_id"]
        self.fx.write_triplet(
            master_tasks=master_tasks if master_tasks is not None else [],
            back_tasks=back_tasks if back_tasks is not None else [],
            gameplay_tasks=gameplay_tasks if gameplay_tasks is not None else [],
        )
        other_ver_raw = self.fx.put("docs/workflows/other-ver-check.md", "# Static Audit Rule\n")
        auth_raw = self.fx.put("docs/workflows/deferred-authority.md", "# Deferred Authority\n")
        other_ver_owned = _owned_ref(
            "other_verification",
            "docs/workflows/other-ver-check.md",
            [("docs/workflows/other-ver-check.md", other_ver_raw)],
        )
        auth_owned = _owned_ref(
            "authority",
            "docs/workflows/deferred-authority.md",
            [("docs/workflows/deferred-authority.md", auth_raw)],
        )

        requirements = [
            {
                "requirement_id": "REQ-1",
                "source_block_ids": [block_id],
                "acceptance_intent": "Player selects one reward and returns to map.",
                "non_task_sinks": [],
            },
            {
                "requirement_id": "REQ-2",
                "source_block_ids": [block_id],
                "acceptance_intent": "Static reward invariants check without fake flow.",
                "non_task_sinks": ["sink:static-audit"],
            },
            {
                "requirement_id": "REQ-3",
                "source_block_ids": [block_id],
                "acceptance_intent": "Future modding hook deferred to later milestone.",
                "non_task_sinks": [],
            },
        ]
        flows = [self.fx.build_base_flow("flow-reward", ["REQ-1"])]
        commands = [
            {
                "id": "cmd-claim-reward",
                "requirement_ids": ["REQ-1"],
                "responsibility": "Claim chosen reward.",
                "uses": [],
            }
        ]
        verifications = [
            {
                "requirement_id": "REQ-1",
                "disposition": "source_gap" if include_source_gap else "flow",
                "flow_id": None if include_source_gap else "flow-reward",
                "rationale": "Gap in source." if include_source_gap else "Verified via reward flow.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            },
            {
                "requirement_id": "REQ-2",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Verified by static audit rule without MVG flow.",
                "sink_id": "sink:static-audit",
                "verification_ref": "docs/workflows/other-ver-check.md",
                "authority_ref": None,
                "evidence_ids": [],
            },
            {
                "requirement_id": "REQ-3",
                "disposition": "deferred",
                "flow_id": None,
                "rationale": "Explicitly deferred by governance note.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": "docs/workflows/deferred-authority.md",
                "evidence_ids": [],
            },
        ]
        memberships = (
            []
            if include_source_gap
            else [{"requirement_id": "REQ-1", "flow_id": "flow-reward", "observable_role": "primary"}]
        )
        applicability = [
            {
                "requirement_id": "REQ-1",
                "disposition": "source_gap" if include_source_gap else "flow",
                "rationale": "Gap in source." if include_source_gap else "Verified via reward flow.",
                "other_verification_refs": [],
            },
            {
                "requirement_id": "REQ-2",
                "disposition": "other_verification",
                "rationale": "Verified by static audit rule without MVG flow.",
                "other_verification_refs": [other_ver_owned],
            },
            {
                "requirement_id": "REQ-3",
                "disposition": "deferred",
                "rationale": "Explicitly deferred by governance note.",
                "other_verification_refs": [],
            },
        ]
        b3 = self.fx.write_committed_3b(
            audit_info,
            requirements=requirements,
            flows=flows,
            commands=commands,
            requirement_verification=verifications,
            requirement_route_memberships=memberships,
            evidence_source_refs=[other_ver_owned, auth_owned],
            applicability=applicability,
            existing_binding=existing_binding,
            origins_tasks=origins_tasks,
            publish_plan_in_catalog=publish_plan,
        )
        return audit_info, b3

    # ------------------------------------------------------------------
    # Matrix Row 1: HAPPY / ZERO (AC-1, AC-4)
    # ------------------------------------------------------------------
    def test_happy_gap_creation_dual_outputs_and_no_permanent_ids(self) -> None:
        audit_info, _ = self._standard_bundle()
        before = self.fx.snapshot_targets()

        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertTrue(res["stable"])
        self.assertEqual(res["schema_version"], preview.SCHEMA)
        # All authorization flags strictly False
        self.assertEqual(res["authorization"], preview.AUTHORIZATION)
        self.assertTrue(all(v is False for v in res["authorization"].values()))
        self.assertFalse(res["permanent_task_ids_allocated"])
        self.assertFalse(res["old_done_satisfies_new_obligations"])

        # Real gap for flow-reward (gameplay) + other_verification REQ-2 (back); REQ-3 deferred NOT created
        gp_deltas = res["view_deltas"]["gameplay"]
        bk_deltas = res["view_deltas"]["back"]
        self.assertEqual(len(gp_deltas), 1, "Single flow must NOT be mechanically 4-split")
        self.assertEqual(gp_deltas[0]["action"], "create")
        self.assertIsNone(gp_deltas[0]["task_id"])
        self.assertTrue(gp_deltas[0]["candidate_key"].startswith("cand:"))
        self.assertEqual(gp_deltas[0]["flow_ids"], ["flow-reward"])
        self.assertEqual(
            gp_deltas[0]["part_kinds"],
            ["binding", "csharp_adapter", "domain_rules", "scene"],
        )

        # NON_FLOW checks: other_verification creates back task with no fake flow; deferred not executed
        self.assertEqual(len(bk_deltas), 1)
        self.assertEqual(bk_deltas[0]["action"], "create")
        self.assertIsNone(bk_deltas[0]["task_id"])
        self.assertEqual(bk_deltas[0]["flow_ids"], [])
        self.assertEqual(bk_deltas[0]["requirement_ids"], ["REQ-2"])
        self.assertEqual(bk_deltas[0]["roles"], ["integration_only_owner"])
        deferred = res["reuse_inventory"]["deferred_items"]
        self.assertEqual(len(deferred), 1)
        self.assertEqual(deferred[0]["requirement_id"], "REQ-3")
        self.assertFalse(deferred[0]["executing"])
        self.assertFalse(deferred[0]["satisfied"])

        # Dual isomorphic outputs for Story 3.2
        bp = res["binding_preview"]
        op = res["origins_preview"]
        self.assertEqual(bp["schema_version"], "newrouge.b-route-binding.v1")
        self.assertEqual(bp["stage"], "3C")
        self.assertEqual(op["schema_version"], "newrouge.b-route-origins.v1")
        self.assertTrue(res["schema_compatibility"]["binding_isomorphic_valid"])
        self.assertTrue(res["schema_compatibility"]["origins_isomorphic_valid"])

        # Deterministic preview_digest across repeated runs
        res2 = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertEqual(res["preview_digest"], res2["preview_digest"])
        # Zero byte mutation on all target files
        self.assertEqual(before, self.fx.snapshot_targets())

    def test_zero_gap_100_percent_reuse_emits_pure_reuse_and_direct_schema_valid_binding(self) -> None:
        master = [
            {"id": 10, "title": "Reward flow task", "status": "done"},
            {"id": 11, "title": "Static audit task", "status": "in-progress"},
        ]
        gameplay = [
            {
                "id": "GM-0010",
                "taskmaster_id": 10,
                "title": "Reward flow task",
                "status": "done",
                "requirement_ids": ["REQ-1"],
                "flow_ids": ["flow-reward"],
                "acceptance": ["Existing reward acceptance."],
            }
        ]
        back = [
            {
                "id": "NG-0011",
                "taskmaster_id": 11,
                "title": "Static audit task",
                "status": "in-progress",
                "requirement_ids": ["REQ-2"],
                "acceptance": ["Existing static audit acceptance."],
            }
        ]
        audit_info, _ = self._standard_bundle(
            master_tasks=master, back_tasks=back, gameplay_tasks=gameplay
        )
        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertTrue(res["reuse_inventory"]["all_reused"])
        self.assertEqual(res["reuse_inventory"]["gap_count"], 0)
        self.assertEqual(res["reuse_inventory"]["action_counts"]["create"], 0)
        self.assertEqual(res["reuse_inventory"]["action_counts"]["reuse"], 2)
        self.assertFalse(res["authorization"]["readiness"])

        # Direct schema validation with zero placeholder substitution!
        b_path = f"docs/planning/b-route/bindings/{self.fx.plan_id}/1.json"
        self.assertTrue(records.validate_record(res["binding_preview"], path=b_path).ok)
        self.assertTrue(
            records.validate_record(res["origins_preview"], path="docs/planning/b-route/task-origins.v1.json").ok
        )

    # ------------------------------------------------------------------
    # Matrix Row 2: M2M (AC-2)
    # ------------------------------------------------------------------
    def test_many_to_many_task_flow_single_disposition_and_integration_only_owner_no_fake_api(self) -> None:
        audit_info = self._audit_info
        block_id = audit_info["blocks"][0]["block_id"]
        # One shared requirement REQ-SHARED belongs to TWO flows (flow-a, flow-b)
        # Existing Task 20 (integration_only_owner) spans BOTH flows (M:N!)
        self.fx.write_triplet(
            master_tasks=[{"id": 20, "title": "Integration gate task", "status": "in-progress"}],
            back_tasks=[
                {
                    "id": "NG-0020",
                    "taskmaster_id": 20,
                    "title": "Integration gate task",
                    "status": "in-progress",
                    "requirement_ids": ["REQ-SHARED"],
                    "flow_ids": ["flow-a", "flow-b"],
                }
            ],
            gameplay_tasks=[],
        )
        ev_raw = self.fx.put_json(
            "docs/workflows/shared-ev.json",
            {"records": [{"evidence_id": "ev-1", "summary": "Shared evidence across both flows."}]},
        )
        ev_owned = _owned_ref(
            "verification_record",
            "docs/workflows/shared-ev.json#ev-1",
            [("docs/workflows/shared-ev.json", ev_raw)],
        )
        flow_a = self.fx.build_base_flow("flow-a", ["REQ-SHARED"])
        flow_b = self.fx.build_base_flow("flow-b", ["REQ-SHARED"])
        existing_binding = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": self.fx.plan_id,
            "binding_revision": 1,
            "plan_ref": None,
            "stage": "3C",
            "task_mappings": [
                {
                    "task_id": 20,
                    "view_refs": [{"view": "back", "business_id": "NG-0020"}],
                    "requirement_ids": ["REQ-SHARED"],
                    "flow_ids": ["flow-a", "flow-b"],
                    "part_kinds": ["binding"],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["obl:flow:flow-a", "obl:flow:flow-b"],
                }
            ],
            "parts": _four_parts(domain=True, adapter=True, binding=True, scene=True),
            "implementation_objects": [],
            "obligations": [
                {
                    "id": "obl:flow:flow-a",
                    "requirement_ids": ["REQ-SHARED"],
                    "flow_ids": ["flow-a"],
                    "test_ids": ["test_flow-a_completes"],
                    "responsibility": "Flow A",
                    "verification_refs": [],
                },
                {
                    "id": "obl:flow:flow-b",
                    "requirement_ids": ["REQ-SHARED"],
                    "flow_ids": ["flow-b"],
                    "test_ids": ["test_flow-b_completes"],
                    "responsibility": "Flow B",
                    "verification_refs": [],
                },
            ],
            "manifest_refs": [],
            "other_verification_refs": [],
        }
        self.fx.write_committed_3b(
            audit_info,
            requirements=[
                {
                    "requirement_id": "REQ-SHARED",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "Shared reward invariant across two flows.",
                    "non_task_sinks": [],
                }
            ],
            flows=[flow_a, flow_b],
            commands=[
                {
                    "id": "cmd-not-for-integration-owner",
                    "requirement_ids": ["REQ-SHARED"],
                    "responsibility": "Runtime command not owned by integration_only_owner.",
                    "uses": [],
                }
            ],
            requirement_verification=[
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "flow_id": "flow-a",
                    "rationale": "Single authoritative disposition.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": ["ev-1"],
                }
            ],
            requirement_route_memberships=[
                {"requirement_id": "REQ-SHARED", "flow_id": "flow-a", "observable_role": "primary"},
                {"requirement_id": "REQ-SHARED", "flow_id": "flow-b", "observable_role": "secondary"},
            ],
            requirement_evidence=[
                {
                    "requirement_id": "REQ-SHARED",
                    "evidence_id": "ev-1",
                    "kind": "verification_record",
                    "source_ref": "docs/workflows/shared-ev.json#ev-1",
                    "covered_behavior": "Shared evidence across both flows.",
                    "flow_ids": ["flow-a", "flow-b"],
                    "test_ids": ["test_shared"],
                }
            ],
            evidence_source_refs=[ev_owned],
            applicability=[
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "rationale": "Single authoritative disposition.",
                    "other_verification_refs": [],
                }
            ],
            existing_binding=existing_binding,
        )

        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        # Single authoritative disposition, 2 route memberships, 1 deduplicated shared evidence
        acct = res["requirement_accounting"]
        self.assertEqual(list(acct["authoritative_dispositions"].keys()), ["REQ-SHARED"])
        self.assertEqual(len(acct["route_memberships"]), 2)
        self.assertEqual(len(acct["shared_evidence"]), 1)
        # Task 20 keeps M:N mapping to BOTH flows without 4-splitting
        tm = res["binding_preview"]["task_mappings"]
        self.assertEqual(len(tm), 1)
        self.assertEqual(tm[0]["task_id"], 20)
        self.assertEqual(tm[0]["flow_ids"], ["flow-a", "flow-b"])
        self.assertEqual(tm[0]["roles"], ["integration_only_owner"])
        # integration_only_owner must NOT fabricate runtime command APIs
        self.assertEqual(res["binding_preview"]["implementation_objects"], [])
        self.assertFalse(res["reuse_inventory"]["fabricated_runtime_apis"])

    # ------------------------------------------------------------------
    # Matrix Row 4: MATURE (AC-1, AC-3)
    # ------------------------------------------------------------------
    def test_old_done_task_never_satisfies_new_requirement_or_flow_obligation(self) -> None:
        audit_info = self._audit_info
        block_id = audit_info["blocks"][0]["block_id"]
        # Mature Task 30 is DONE and historically covers ONLY REQ-OLD.
        self.fx.write_triplet(
            master_tasks=[{"id": 30, "title": "Old done reward task", "status": "done"}],
            back_tasks=[],
            gameplay_tasks=[
                {
                    "id": "GM-0030",
                    "taskmaster_id": 30,
                    "title": "Old done reward task",
                    "status": "done",
                    "requirement_ids": ["REQ-OLD"],
                    "acceptance": ["Old acceptance."],
                }
            ],
        )
        self.fx.write_committed_3b(
            audit_info,
            requirements=[
                {
                    "requirement_id": "REQ-OLD",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "Old reward behavior.",
                    "non_task_sinks": [],
                },
                {
                    "requirement_id": "REQ-NEW",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "New reward reroll behavior.",
                    "non_task_sinks": [],
                },
            ],
            flows=[
                self.fx.build_base_flow("flow-old", ["REQ-OLD"]),
                self.fx.build_base_flow("flow-new", ["REQ-NEW"]),
            ],
            requirement_verification=[
                {
                    "requirement_id": "REQ-OLD",
                    "disposition": "flow",
                    "flow_id": "flow-old",
                    "rationale": "Old flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                },
                {
                    "requirement_id": "REQ-NEW",
                    "disposition": "flow",
                    "flow_id": "flow-new",
                    "rationale": "New flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                },
            ],
            requirement_route_memberships=[
                {"requirement_id": "REQ-OLD", "flow_id": "flow-old", "observable_role": "primary"},
                {"requirement_id": "REQ-NEW", "flow_id": "flow-new", "observable_role": "primary"},
            ],
            applicability=[
                {"requirement_id": "REQ-OLD", "disposition": "flow", "rationale": "Old flow.", "other_verification_refs": []},
                {"requirement_id": "REQ-NEW", "disposition": "flow", "rationale": "New flow.", "other_verification_refs": []},
            ],
        )

        # 1) Automatic preview reuses Task 30 for flow-old and creates real gap for flow-new
        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        actions = {d["action"]: d for d in res["view_deltas"]["gameplay"]}
        self.assertIn("reuse", actions)
        self.assertEqual(actions["reuse"]["task_id"], 30)
        self.assertEqual(actions["reuse"]["status"], "done")
        self.assertIn("create", actions)
        self.assertEqual(actions["create"]["requirement_ids"], ["REQ-NEW"])
        self.assertIsNone(actions["create"]["task_id"])

        # 2) Explicit change-intent trying to reuse old DONE Task 30 to satisfy REQ-NEW MUST FAIL
        bad_ci = "logs/ci/test-inputs/bad-reuse-done.json"
        self.fx.put_json(
            bad_ci,
            {
                "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                "operations": [
                    {
                        "action": "reuse",
                        "view": "gameplay",
                        "task_id": 30,
                        "business_id": "GM-0030",
                        "requirement_ids": ["REQ-OLD", "REQ-NEW"],
                        "flow_ids": ["flow-old", "flow-new"],
                    }
                ],
            },
        )
        blocked = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
            change_intents_ref=bad_ci,
        )
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["diagnostics"][0]["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)

    def test_mature_update_split_merge_and_protections_against_overwrite_story_id_and_weakening(self) -> None:
        master = [
            {"id": 10, "title": "Reward flow task", "status": "done"},
            {"id": 11, "title": "Static audit task", "status": "in-progress"},
            {"id": 12, "title": "Extra mature task", "status": "done"},
        ]
        gameplay = [
            {
                "id": "GM-0010",
                "taskmaster_id": 10,
                "title": "Reward flow task",
                "status": "done",
                "requirement_ids": ["REQ-1"],
                "acceptance": ["Must keep original acceptance."],
                "history": ["2026-11-01 completed v1"],
            }
        ]
        back = [
            {
                "id": "NG-0011",
                "taskmaster_id": 11,
                "title": "Static audit task",
                "status": "in-progress",
                "requirement_ids": ["REQ-2"],
                "acceptance": ["Static audit acceptance."],
            },
            {
                "id": "NG-0012",
                "taskmaster_id": 12,
                "title": "Extra mature task",
                "status": "done",
                "requirement_ids": [],
                "acceptance": ["Legacy task."],
            },
        ]
        audit_info, _ = self._standard_bundle(master_tasks=master, back_tasks=back, gameplay_tasks=gameplay)
        block_id = audit_info["blocks"][0]["block_id"]

        # Baseline MVG manifest referencing flow-reward & task 10
        manifest_path = "docs/testing/mvg/reward-baseline.json"
        baseline_manifest = {
            "schema_version": "newrouge.mvg-manifest.v1",
            "coverage": {"mode": "critical", "excluded_claims": []},
            "flows": [
                {
                    "id": "flow-reward",
                    "outcome": "reward_claimed",
                    "requirement_ids": ["REQ-1"],
                    "task_ids": [10],
                    "test_ids": ["test_flow-reward_completes"],
                    "min_tests": 1,
                    "state": "implemented",
                    "evidence_level": "domain-integration",
                    "handoffs": [],
                }
            ],
            "tests": [{"id": "test_flow-reward_completes", "kind": "xunit", "state": "implemented"}],
        }
        self.fx.put_json(manifest_path, baseline_manifest)

        # Valid governed update + split + merge succeeds and preserves mature status/IDs/lineage
        valid_ci = "logs/ci/test-inputs/valid-mature-ops.json"
        self.fx.put_json(
            valid_ci,
            {
                "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                "operations": [
                    {
                        "action": "update",
                        "view": "gameplay",
                        "task_id": 10,
                        "business_id": "GM-0010",
                        "requirement_ids": ["REQ-1"],
                        "flow_ids": ["flow-reward"],
                        "scope": "Extend reward acceptance while preserving done status",
                        "source_diff_evidence": [{"block_id": block_id}],
                        "lineage": {"from_task_ids": [10], "to_task_ids": [10]},
                        "rationale": "Additive verification criteria from revised source.",
                        "proposed_fields": {
                            "acceptance": ["Must keep original acceptance.", "Added additive check."],
                            "history": ["2026-11-01 completed v1"],
                        },
                    },
                    {
                        "action": "merge",
                        "view": "back",
                        "source_task_ids": [11, 12],
                        "target_task_id": 11,
                        "requirement_ids": ["REQ-2"],
                        "flow_ids": [],
                        "roles": ["integration_only_owner"],
                        "scope": "Consolidate static audit back tasks into task 11",
                        "source_diff_evidence": [{"block_id": block_id}],
                        "lineage": {"from_task_ids": [11, 12], "to_task_ids": [11]},
                        "rationale": "Avoid redundant back audit tasks.",
                    },
                ],
            },
        )
        ok_res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
            manifest_ref=manifest_path,
            change_intents_ref=valid_ci,
        )
        self.assertTrue(ok_res["ok"], ok_res["diagnostics"])
        upd = ok_res["view_deltas"]["gameplay"][0]
        self.assertEqual(upd["action"], "update")
        self.assertEqual(upd["status"], "done")
        self.assertFalse(upd["old_done_satisfies_new_obligations"])
        self.assertTrue(upd["requires_new_verification"])

        # Negative mature protection cases: every single one MUST fail closed!
        negative_cases = [
            (
                "status_overwrite",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "business_id": "GM-0010",
                            "scope": "bad",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "attempt overwrite status",
                            "proposed_fields": {"status": "pending"},
                        }
                    ],
                },
                codec.ReasonCode.CONFLICT.value,
            ),
            (
                "story_id_as_task_id",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": "Story-3.1",
                            "scope": "bad",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": ["Story-3.1"]},
                            "rationale": "story id",
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "create_preallocated_task_id",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "create",
                            "view": "gameplay",
                            "task_id": 999,
                            "requirement_ids": ["REQ-1"],
                            "flow_ids": ["flow-reward"],
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "acceptance_weakening",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "business_id": "GM-0010",
                            "scope": "drop acceptance",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "dropping acceptance",
                            "proposed_fields": {"acceptance": []},
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "ungrounded_retire",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "retire",
                            "view": "gameplay",
                            "task_id": 10,
                            "business_id": "GM-0010",
                            "scope": "retire without authority",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10], "to_task_ids": []},
                            "rationale": "no authority ref",
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "mvg_baseline_weakening",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [],
                    "proposed_manifest": {
                        **copy.deepcopy(baseline_manifest),
                        "flows": [],
                    },
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
        ]
        for label, payload, expected_code in negative_cases:
            with self.subTest(case=label):
                ci_file = f"logs/ci/test-inputs/neg-{label}.json"
                self.fx.put_json(ci_file, payload)
                neg = preview.preview_task_changes(
                    self.fx.root,
                    plan_id=self.fx.plan_id,
                    scope_id=self.fx.scope_id,
                    audit_ref=audit_info["audit_ref"],
                    manifest_ref=manifest_path,
                    change_intents_ref=ci_file,
                )
                self.assertFalse(neg["ok"], f"{label} should have been blocked")
                self.assertEqual(neg["diagnostics"][0]["reason_code"], expected_code)
                self.assertEqual(
                    set(neg["diagnostics"][0].keys()),
                    {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"},
                )

    # ------------------------------------------------------------------
    # Matrix Row 5: GAP_DRIFT (AC-5)
    # ------------------------------------------------------------------
    def test_3a_synthetic_stale_and_source_mismatch_fail_closed_with_3a_diagnostic(self) -> None:
        # Case A: synthetic 3A proof (planning_eligible=False)
        audit_syn, _ = self._standard_bundle(synthetic_3a=True)
        res_syn = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_syn["audit_ref"],
        )
        self.assertFalse(res_syn["ok"])
        d0 = res_syn["diagnostics"][0]
        self.assertEqual(d0["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)
        self.assertEqual(d0["expected"]["owning_stage"], "3A")

        # Case B: real 3A proof, then mutate source doc -> stale 3A proof!
        self._fresh_fixture(synthetic=False)
        audit_ok, _ = self._standard_bundle(synthetic_3a=False)
        self.fx.put("docs/gdd/reward.md", "# Reward Loop\n\nEdited after 3A audit!\n")
        res_stale = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_ok["audit_ref"],
        )
        self.assertFalse(res_stale["ok"])
        self.assertEqual(res_stale["diagnostics"][0]["expected"]["owning_stage"], "3A")

    def test_3b_source_gap_and_unpublished_plan_fail_closed_with_3b_diagnostic(self) -> None:
        # Case A: source_gap in requirement_verification
        audit_info, _ = self._standard_bundle(include_source_gap=True)
        res_gap = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertFalse(res_gap["ok"])
        self.assertEqual(res_gap["diagnostics"][0]["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)
        self.assertEqual(res_gap["diagnostics"][0]["expected"]["owning_stage"], "3B")
        self.assertEqual(res_gap["diagnostics"][0]["entity_id"], "REQ-1")

        # Case B: unpublished plan_id
        self._fresh_fixture(synthetic=False)
        audit_unpub, _ = self._standard_bundle(publish_plan=False)
        res_unpub = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_unpub["audit_ref"],
        )
        self.assertFalse(res_unpub["ok"])
        self.assertEqual(res_unpub["diagnostics"][0]["reason_code"], codec.ReasonCode.UNPUBLISHED.value)
        self.assertEqual(res_unpub["diagnostics"][0]["expected"]["owning_stage"], "3B")

    def test_mid_run_concurrent_edit_drift_via_hook_sets_unstable(self) -> None:
        audit_info, _ = self._standard_bundle()

        def mutate_triplet() -> None:
            self.fx.put_json(
                ".taskmaster/tasks/tasks.json",
                {"master": {"tasks": [{"id": 99, "title": "Injected mid-run", "status": "pending"}]}},
            )

        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
            before_reread=mutate_triplet,
        )
        self.assertFalse(res["ok"])
        self.assertFalse(res["stable"])
        self.assertTrue(
            any(d["reason_code"] == codec.ReasonCode.FILE_CHANGED.value for d in res["diagnostics"]),
            res["diagnostics"],
        )

    # ------------------------------------------------------------------
    # Fresh Subprocess CLI 0 / 1 / 2 + Zero Mutation + Zero __pycache__
    # ------------------------------------------------------------------
    def test_cli_subprocess_exit_codes_0_1_2_zero_mutation_and_zero_pycache(self) -> None:
        audit_info, _ = self._standard_bundle()
        before = self.fx.snapshot_targets()

        # Verify dev_cli_builders helper rejects write/apply and emits expected command
        ns_ok = type(
            "Args",
            (),
            {
                "root": str(self.fx.root),
                "plan_id": self.fx.plan_id,
                "run_id": "builder-run",
                "audit_ref": audit_info["audit_ref"],
                "scope_id": self.fx.scope_id,
                "protection_ref": None,
                "manifest": None,
                "change_intents": None,
            },
        )()
        built_cmd = dev_cli_builders.build_b_route_task_preview_cmd(ns_ok)
        self.assertIn("--plan-id", built_cmd)
        self.assertNotIn("--write", built_cmd)
        self.assertNotIn("--apply", built_cmd)
        ns_bad = type("BadArgs", (), {"write": True})()
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_task_preview_cmd(ns_bad)

        # Subprocess environment intentionally WITHOUT PYTHONDONTWRITEBYTECODE and WITHOUT -B
        # to prove sys.dont_write_bytecode = True in the entrypoints prevents .pyc creation!
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = os.pathsep.join([str(SCRIPTS_PY), str(SCRIPTS_PY / "tests"), str(REPO_ROOT)])

        # 1) Exit code 0 via dev_cli.py b-route-task-preview
        cmd0 = [
            sys.executable,
            str(SCRIPTS_PY / "dev_cli.py"),
            "b-route-task-preview",
            "--root",
            str(self.fx.root),
            "--plan-id",
            self.fx.plan_id,
            "--scope-id",
            self.fx.scope_id,
            "--audit-ref",
            audit_info["audit_ref"],
            "--run-id",
            "cli-ok-001",
        ]
        p0 = subprocess.run(cmd0, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT), check=False)
        self.assertEqual(p0.returncode, 0, p0.stdout + p0.stderr)
        self.assertEqual(p0.stderr, "")
        lines0 = [ln for ln in p0.stdout.splitlines() if ln.strip()]
        self.assertEqual(len(lines0), 1, "CLI must emit a single JSON line to stdout")
        out0 = json.loads(lines0[0])
        self.assertTrue(out0["ok"])
        self.assertTrue(out0["stable"])
        self.assertTrue((self.fx.root / out0["report_path"]).is_file())
        self.assertEqual(before, self.fx.snapshot_targets())

        # 2) Exit code 2 on existing run-id collision (never overwrite existing run!)
        p2_dup = subprocess.run(cmd0, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT), check=False)
        self.assertEqual(p2_dup.returncode, 2, p2_dup.stdout + p2_dup.stderr)
        out2_dup = json.loads(p2_dup.stdout.strip())
        self.assertFalse(out2_dup["ok"])
        self.assertEqual(out2_dup["diagnostics"][0]["reason_code"], codec.ReasonCode.CONFLICT.value)

        # 3) Exit code 2 on unknown --apply flag (strictly read-only CLI)
        p2_arg = subprocess.run(
            [*cmd0[:-1], "cli-bad-arg", "--apply"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            check=False,
        )
        self.assertEqual(p2_arg.returncode, 2, p2_arg.stdout + p2_arg.stderr)
        out2_arg = json.loads(p2_arg.stdout.strip())
        self.assertEqual(out2_arg["diagnostics"][0]["reason_code"], codec.ReasonCode.INVALID_ARGUMENT.value)

        # 4) Exit code 1 on business block (unpublished plan_id) via direct entrypoint
        cmd1 = [
            sys.executable,
            str(SCRIPTS_PY / "preview_b_route_task_changes.py"),
            "--root",
            str(self.fx.root),
            "--plan-id",
            "missing-plan",
            "--scope-id",
            self.fx.scope_id,
            "--audit-ref",
            audit_info["audit_ref"],
            "--run-id",
            "cli-blocked-001",
        ]
        p1 = subprocess.run(cmd1, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT), check=False)
        self.assertEqual(p1.returncode, 1, p1.stdout + p1.stderr)
        out1 = json.loads(p1.stdout.strip())
        self.assertFalse(out1["ok"])
        self.assertEqual(out1["diagnostics"][0]["reason_code"], codec.ReasonCode.UNPUBLISHED.value)
        self.assertTrue((self.fx.root / out1["report_path"]).is_file())

        # Zero target mutation & zero __pycache__/.pyc in temp root and scripts/python
        self.assertEqual(before, self.fx.snapshot_targets())
        temp_pyc = [p for p in self.fx.root.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
        self.assertEqual(temp_pyc, [], f"Unexpected bytecode in temp root: {temp_pyc}")
        preview_pyc = [
            p
            for p in SCRIPTS_PY.rglob("*.pyc")
            if "task_preview" in p.name or "preview_b_route_task_changes" in p.name
        ]
        self.assertEqual(preview_pyc, [], f"Unexpected bytecode for preview modules: {preview_pyc}")

    # ------------------------------------------------------------------
    # Step 4 Review Regression Coverage (P1 - P6)
    # ------------------------------------------------------------------
    def test_valid_split_retire_merge_null_target_origins_cleanup_and_proposal_fields(self) -> None:
        master = [
            {"id": 40, "title": "Monolithic reward task", "status": "done"},
            {"id": 41, "title": "Retirable task", "status": "done"},
            {"id": 42, "title": "Merge source A", "status": "in-progress"},
            {"id": 43, "title": "Merge source B", "status": "done"},
        ]
        gameplay = [
            {
                "id": "GM-0040",
                "taskmaster_id": 40,
                "title": "Monolithic reward task",
                "status": "done",
                "requirement_ids": ["REQ-1"],
                "flow_ids": ["flow-reward"],
                "acceptance": ["Original reward acceptance."],
            },
            {
                "id": "GM-0041",
                "taskmaster_id": 41,
                "title": "Retirable task",
                "status": "done",
                "requirement_ids": ["REQ-1"],
                "acceptance": ["Retirable acceptance."],
            },
        ]
        back = [
            {
                "id": "NG-0042",
                "taskmaster_id": 42,
                "title": "Merge source A",
                "status": "in-progress",
                "requirement_ids": ["REQ-2"],
                "acceptance": ["Audit check A."],
            },
            {
                "id": "NG-0043",
                "taskmaster_id": 43,
                "title": "Merge source B",
                "status": "done",
                "requirement_ids": [],
                "acceptance": ["Audit check B."],
            },
        ]
        existing_binding = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": self.fx.plan_id,
            "binding_revision": 1,
            "plan_ref": None,
            "stage": "3C",
            "task_mappings": [
                {
                    "task_id": 40,
                    "view_refs": [{"view": "gameplay", "business_id": "GM-0040"}],
                    "requirement_ids": ["REQ-1"],
                    "flow_ids": ["flow-reward"],
                    "part_kinds": ["binding", "csharp_adapter", "domain_rules", "scene"],
                    "roles": ["producer"],
                    "obligation_ids": ["obl:flow:flow-reward"],
                },
                {
                    "task_id": 41,
                    "view_refs": [{"view": "gameplay", "business_id": "GM-0041"}],
                    "requirement_ids": ["REQ-1"],
                    "flow_ids": ["flow-reward"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": ["obl:flow:flow-reward"],
                },
                {
                    "task_id": 42,
                    "view_refs": [{"view": "back", "business_id": "NG-0042"}],
                    "requirement_ids": ["REQ-2"],
                    "flow_ids": [],
                    "part_kinds": [],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["obl:other:REQ-2"],
                },
                {
                    "task_id": 43,
                    "view_refs": [{"view": "back", "business_id": "NG-0043"}],
                    "requirement_ids": ["REQ-2"],
                    "flow_ids": [],
                    "part_kinds": [],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["obl:other:REQ-2"],
                },
            ],
            "parts": _four_parts(domain=True, adapter=True, binding=True, scene=True),
            "implementation_objects": [
                {
                    "id": "command:cmd-claim-reward",
                    "kind": "command",
                    "availability": "planned",
                    "responsible_task_ids": [40, 41],
                    "expected_type": "planned:command:cmd-claim-reward",
                    "lifecycle": "planned_for_chapter4_refinement",
                    "target_ref": None,
                    "later_checks": ["type", "compile", "binding"],
                }
            ],
            "obligations": [
                {
                    "id": "obl:flow:flow-reward",
                    "requirement_ids": ["REQ-1"],
                    "flow_ids": ["flow-reward"],
                    "test_ids": ["test_flow-reward_completes"],
                    "responsibility": "Reward flow.",
                    "verification_refs": [],
                },
                {
                    "id": "obl:other:REQ-2",
                    "requirement_ids": ["REQ-2"],
                    "flow_ids": [],
                    "test_ids": [],
                    "responsibility": "Static audit.",
                    "verification_refs": [],
                },
            ],
            "manifest_refs": [],
            "other_verification_refs": [],
        }
        audit_info, _ = self._standard_bundle(
            master_tasks=master,
            back_tasks=back,
            gameplay_tasks=gameplay,
            existing_binding=existing_binding,
        )
        block_id = audit_info["blocks"][0]["block_id"]
        self.fx.put("docs/workflows/retire-authority.md", "# Reviewed Retire Authority\n")

        ci_path = "logs/ci/test-inputs/valid-split-retire-merge-null.json"
        self.fx.put_json(
            ci_path,
            {
                "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                "operations": [
                    {
                        "action": "split",
                        "view": "gameplay",
                        "source_task_id": 40,
                        "scope": "Split monolithic reward task into domain and adapter candidates",
                        "source_diff_evidence": [{"block_id": block_id}],
                        "lineage": {"from_task_ids": [40]},
                        "rationale": "Separate domain rules and scene adapter cleanly.",
                        "targets": [
                            {
                                "view": "gameplay",
                                "candidate_key": "cand:reward-split-domain",
                                "requirement_ids": ["REQ-1"],
                                "flow_ids": ["flow-reward"],
                                "part_kinds": ["domain_rules", "binding"],
                                "roles": ["producer"],
                            },
                            {
                                "view": "gameplay",
                                "candidate_key": "cand:reward-split-scene",
                                "requirement_ids": ["REQ-1"],
                                "flow_ids": ["flow-reward"],
                                "part_kinds": ["csharp_adapter", "scene"],
                                "roles": ["producer"],
                            },
                        ],
                    },
                    {
                        "action": "retire",
                        "view": "gameplay",
                        "task_id": 41,
                        "business_id": "GM-0041",
                        "scope": "Retire redundant task 41 with reviewed authority",
                        "source_diff_evidence": [{"block_id": block_id}],
                        "lineage": {"from_task_ids": [41], "to_task_ids": []},
                        "rationale": "Superseded by split targets.",
                        "authority_ref": "docs/workflows/retire-authority.md",
                    },
                    {
                        "action": "merge",
                        "view": "back",
                        "source_task_ids": [42, 43],
                        "target_task_id": None,
                        "candidate_key": "cand:back-merged-audit",
                        "requirement_ids": ["REQ-2"],
                        "flow_ids": [],
                        "roles": ["integration_only_owner"],
                        "scope": "Merge back audit tasks into a fresh candidate",
                        "source_diff_evidence": [{"block_id": block_id}],
                        "lineage": {"from_task_ids": [42, 43]},
                        "rationale": "Consolidate static audit tasks into one candidate.",
                    },
                ],
            },
        )
        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
            change_intents_ref=ci_path,
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        # Verify origins_preview dropped retired(41), split-source(40), and merge-absorbed(42, 43)!
        origin_existing_tids = [r["task_id"] for r in res["origins_preview"]["tasks"] if r["task_id"] is not None]
        self.assertEqual(origin_existing_tids, [])
        origin_ckeys = sorted(r["candidate_key"] for r in res["origins_preview"]["tasks"] if r["task_id"] is None)
        self.assertEqual(
            origin_ckeys,
            ["cand:back-merged-audit", "cand:reward-split-domain", "cand:reward-split-scene"],
        )
        # Verify implementation_objects excluded retired(41) & split-source(40) from responsible_task_ids
        impl_objs = res["binding_preview"]["implementation_objects"]
        self.assertEqual(len(impl_objs), 1)
        self.assertEqual(impl_objs[0]["responsible_task_ids"], [])
        self.assertEqual(
            impl_objs[0]["responsible_candidate_keys"],
            ["cand:reward-split-domain", "cand:reward-split-scene"],
        )
        # Verify normalized proposal fields (P5): topic, plan_ref, semantic_review_tier, acceptance with Refs:
        split_deltas = [d for d in res["view_deltas"]["gameplay"] if d["action"] == "split"]
        self.assertEqual(len(split_deltas), 2)
        for d in split_deltas:
            self.assertTrue(d.get("topic"))
            self.assertEqual(d.get("semantic_review_tier"), "targeted")
            self.assertEqual(d["plan_ref"]["entity_id"], self.fx.plan_id)
            self.assertTrue(any("Refs:" in acc and "Player selects one reward" in acc for acc in d["acceptance"]))
        # Verify merge(target_task_id=None) preserves source_statuses & source_business_ids in lineage
        merge_deltas = [d for d in res["view_deltas"]["back"] if d["action"] == "merge"]
        self.assertEqual(len(merge_deltas), 1)
        self.assertIsNone(merge_deltas[0]["task_id"])
        self.assertEqual(merge_deltas[0]["candidate_key"], "cand:back-merged-audit")
        self.assertEqual(merge_deltas[0]["lineage"]["source_statuses"], {"42": "in-progress", "43": "done"})
        # Verify authority_ref was observed for drift re-read
        obs_paths = {row["path"] for row in res["observations"]}
        self.assertIn("docs/workflows/retire-authority.md", obs_paths)

    def test_change_intents_dedup_collisions_mvg_weakening_and_source_evidence_guards(self) -> None:
        master = [
            {"id": 10, "title": "Reward flow task", "status": "done"},
            {"id": 11, "title": "Static audit task", "status": "in-progress"},
            {"id": 12, "title": "Extra mature task", "status": "done"},
        ]
        gameplay = [
            {
                "id": "GM-0010",
                "taskmaster_id": 10,
                "title": "Reward flow task",
                "status": "done",
                "requirement_ids": ["REQ-1"],
                "flow_ids": ["flow-reward"],
                "acceptance": ["Keep acceptance 10."],
            }
        ]
        back = [
            {
                "id": "NG-0011",
                "taskmaster_id": 11,
                "title": "Static audit task",
                "status": "in-progress",
                "requirement_ids": ["REQ-2"],
                "acceptance": ["Keep acceptance 11."],
            },
            {
                "id": "NG-0012",
                "taskmaster_id": 12,
                "title": "Extra mature task",
                "status": "done",
                "requirement_ids": [],
                "acceptance": ["Keep acceptance 12."],
                "history": ["2026-11-01 completed 12"],
            },
        ]
        audit_info, _ = self._standard_bundle(master_tasks=master, back_tasks=back, gameplay_tasks=gameplay)
        block_id = audit_info["blocks"][0]["block_id"]
        manifest_path = "docs/testing/mvg/reward-baseline.json"
        self.fx.put_json(
            manifest_path,
            {
                "schema_version": "newrouge.mvg-manifest.v1",
                "coverage": {"mode": "critical", "excluded_claims": []},
                "flows": [
                    {
                        "id": "flow-reward",
                        "outcome": "reward_claimed",
                        "requirement_ids": ["REQ-1"],
                        "task_ids": [10],
                        "test_ids": ["test_flow-reward_completes"],
                        "min_tests": 1,
                        "state": "implemented",
                        "evidence_level": "domain-integration",
                        "handoffs": [],
                    }
                ],
                "tests": [{"id": "test_flow-reward_completes", "kind": "xunit", "state": "implemented"}],
            },
        )

        cases = [
            (
                "duplicate_seen_target_split_and_update",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                        },
                        {
                            "action": "split",
                            "view": "gameplay",
                            "source_task_id": 10,
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                            "targets": [
                                {"requirement_ids": ["REQ-1"], "flow_ids": ["flow-reward"]},
                                {"requirement_ids": ["REQ-1"], "flow_ids": ["flow-reward"]},
                            ],
                        },
                    ],
                },
                codec.ReasonCode.CONFLICT.value,
            ),
            (
                "duplicate_seen_target_merge_overlap",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "reuse",
                            "view": "back",
                            "task_id": 11,
                        },
                        {
                            "action": "merge",
                            "view": "back",
                            "source_task_ids": [11, 12],
                            "target_task_id": 11,
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [11, 12]},
                            "rationale": "r",
                        },
                    ],
                },
                codec.ReasonCode.CONFLICT.value,
            ),
            (
                "colliding_candidate_key_across_create_and_merge",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "create",
                            "view": "back",
                            "candidate_key": "cand:dup-key",
                            "requirement_ids": ["REQ-2"],
                        },
                        {
                            "action": "merge",
                            "view": "back",
                            "source_task_ids": [11, 12],
                            "target_task_id": None,
                            "candidate_key": "cand:dup-key",
                            "requirement_ids": ["REQ-2"],
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [11, 12]},
                            "rationale": "r",
                        },
                    ],
                },
                codec.ReasonCode.CONFLICT.value,
            ),
            (
                "colliding_business_id_with_existing_task",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "create",
                            "view": "gameplay",
                            "candidate_key": "cand:unique-key",
                            "proposed_business_id": "GM-0010",
                            "requirement_ids": ["REQ-1"],
                            "flow_ids": ["flow-reward"],
                        }
                    ],
                },
                codec.ReasonCode.CONFLICT.value,
            ),
            (
                "unknown_flow_id_no_keyerror",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "flow_ids": ["flow-nonexistent"],
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                        }
                    ],
                },
                codec.ReasonCode.UNRESOLVED_REFERENCE.value,
            ),
            (
                "empty_dict_source_diff_evidence_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "scope": "s",
                            "source_diff_evidence": [{}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                        }
                    ],
                },
                codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
            ),
            (
                "unanchored_string_source_diff_evidence_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "scope": "s",
                            "source_diff_evidence": ["unanchored free text"],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                        }
                    ],
                },
                codec.ReasonCode.UNRESOLVED_REFERENCE.value,
            ),
            (
                "retire_missing_authority_ref_file_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "retire",
                            "view": "back",
                            "task_id": 12,
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [12]},
                            "rationale": "r",
                            "authority_ref": "docs/workflows/does-not-exist.md",
                        }
                    ],
                },
                codec.ReasonCode.FILE_NOT_FOUND.value,
            ),
            (
                "merge_drops_non_target_source_history_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "merge",
                            "view": "back",
                            "source_task_ids": [11, 12],
                            "target_task_id": 11,
                            "requirement_ids": ["REQ-2"],
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [11, 12]},
                            "rationale": "r",
                            "proposed_fields": {"history": []},
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "split_drops_mvg_baseline_flow_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "split",
                            "view": "gameplay",
                            "source_task_id": 10,
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                            "targets": [
                                {"candidate_key": "cand:s1", "requirement_ids": ["REQ-2"], "flow_ids": []},
                                {"candidate_key": "cand:s2", "requirement_ids": ["REQ-2"], "flow_ids": []},
                            ],
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
            (
                "update_drops_mvg_baseline_flow_rejected",
                {
                    "schema_version": preview.CHANGE_INTENTS_SCHEMA,
                    "operations": [
                        {
                            "action": "update",
                            "view": "gameplay",
                            "task_id": 10,
                            "requirement_ids": ["REQ-2"],
                            "flow_ids": [],
                            "scope": "s",
                            "source_diff_evidence": [{"block_id": block_id}],
                            "lineage": {"from_task_ids": [10]},
                            "rationale": "r",
                        }
                    ],
                },
                codec.ReasonCode.SEMANTIC_ERROR.value,
            ),
        ]
        for label, payload, expected_code in cases:
            with self.subTest(case=label):
                ci_file = f"logs/ci/test-inputs/p2-{label}.json"
                self.fx.put_json(ci_file, payload)
                res = preview.preview_task_changes(
                    self.fx.root,
                    plan_id=self.fx.plan_id,
                    scope_id=self.fx.scope_id,
                    audit_ref=audit_info["audit_ref"],
                    manifest_ref=manifest_path,
                    change_intents_ref=ci_file,
                )
                self.assertFalse(res["ok"], f"{label} should fail closed")
                self.assertEqual(res["diagnostics"][0]["reason_code"], expected_code, res["diagnostics"])

    def test_auto_reuse_old_done_expanded_flow_partial_impl_and_cross_plan_shared_flow(self) -> None:
        audit_info = self._audit_info
        block_id = audit_info["blocks"][0]["block_id"]

        # 1) Old DONE task with flow_ids=["flow-expanded"] & only REQ-OLD MUST NOT satisfy REQ-NEW!
        #    And partial implementation task covering REQ-OLD MUST NOT be classified as integration_only_owner!
        self.fx.write_triplet(
            master_tasks=[{"id": 50, "title": "Old done partial reward", "status": "done"}],
            back_tasks=[],
            gameplay_tasks=[
                {
                    "id": "GM-0050",
                    "taskmaster_id": 50,
                    "title": "Old done partial reward",
                    "status": "done",
                    "requirement_ids": ["REQ-OLD"],
                    "flow_ids": ["flow-expanded"],
                    "part_kinds": ["domain_rules"],
                }
            ],
        )
        self.fx.write_committed_3b(
            audit_info,
            requirements=[
                {
                    "requirement_id": "REQ-OLD",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "Old reward rule.",
                    "non_task_sinks": [],
                },
                {
                    "requirement_id": "REQ-NEW",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "New reward reroll rule.",
                    "non_task_sinks": [],
                },
            ],
            flows=[self.fx.build_base_flow("flow-expanded", ["REQ-OLD", "REQ-NEW"])],
            commands=[
                {
                    "id": "cmd-old-reward",
                    "requirement_ids": ["REQ-OLD"],
                    "responsibility": "Execute old reward command.",
                    "uses": [],
                }
            ],
            requirement_verification=[
                {
                    "requirement_id": "REQ-OLD",
                    "disposition": "flow",
                    "flow_id": "flow-expanded",
                    "rationale": "Covered by expanded flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                },
                {
                    "requirement_id": "REQ-NEW",
                    "disposition": "flow",
                    "flow_id": "flow-expanded",
                    "rationale": "Newly introduced requirement in expanded flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                },
            ],
            requirement_route_memberships=[
                {"requirement_id": "REQ-OLD", "flow_id": "flow-expanded", "observable_role": "primary"},
                {"requirement_id": "REQ-NEW", "flow_id": "flow-expanded", "observable_role": "secondary"},
            ],
            applicability=[
                {"requirement_id": "REQ-OLD", "disposition": "flow", "rationale": "Covered by expanded flow.", "other_verification_refs": []},
                {"requirement_id": "REQ-NEW", "disposition": "flow", "rationale": "Newly introduced requirement in expanded flow.", "other_verification_refs": []},
            ],
        )
        res = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(res["ok"], res["diagnostics"])
        reused = [d for d in res["view_deltas"]["gameplay"] if d["action"] == "reuse"]
        created = [d for d in res["view_deltas"]["gameplay"] if d["action"] == "create"]
        self.assertEqual(len(reused), 1)
        self.assertEqual(reused[0]["task_id"], 50)
        self.assertEqual(reused[0]["roles"], ["producer"], "Partial implementation task must NOT be integration_only_owner")
        self.assertEqual(len(created), 1, "Old done task must NOT suppress gap creation for REQ-NEW")
        self.assertEqual(created[0]["requirement_ids"], ["REQ-NEW"])
        # Planned implementation_object for cmd-old-reward MUST be emitted for partial implementation Task 50!
        impl_ids = {obj["id"]: obj for obj in res["binding_preview"]["implementation_objects"]}
        self.assertIn("command:cmd-old-reward", impl_ids)
        self.assertIn(50, impl_ids["command:cmd-old-reward"]["responsible_task_ids"])

        # 2) Cross-plan shared Flow via catalog.definition_owners (owner plan defines flow-shared, consumer plan references it)
        self._fresh_fixture(synthetic=False)
        audit_info = self._audit_info
        block_id = audit_info["blocks"][0]["block_id"]
        manifest_path = audit_info["manifest_path"]
        ledger_path = audit_info["ledger_path"]
        manifest_raw = (self.fx.root / manifest_path).read_bytes()
        ledger_raw = (self.fx.root / ledger_path).read_bytes()
        manifest = audit_info["manifest"]
        self.fx.write_triplet(master_tasks=[], back_tasks=[], gameplay_tasks=[])

        proof_raw = self.fx.put_json("logs/ci/test-inputs/adoption-proof.json", {"proof": "adopted-3b"})
        adr_raw = self.fx.put("docs/adr/ADR-0040-test.md", "# ADR-0040 Test\n")
        authority_raw = self.fx.put("docs/workflows/authority-note.md", "# Authority Note\n")
        src_identity = {
            "manifest_ref": _owned_ref("source_manifest", manifest_path, [(manifest_path, manifest_raw)]),
            "ledger_ref": _owned_ref("source_ledger", ledger_path, [(ledger_path, ledger_raw)]),
            "source_revision": manifest["source_revision"],
            "source_manifest_digest": manifest["manifest_sha256"],
        }
        proof_owned = _owned_ref(
            "planning_proof",
            "logs/ci/test-inputs/adoption-proof.json",
            [("logs/ci/test-inputs/adoption-proof.json", proof_raw)],
        )
        owner_plan = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "owner-plan",
            "revision": 1,
            "source_identity": copy.deepcopy(src_identity),
            "requirements": [
                {
                    "requirement_id": "REQ-SHARED",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "Shared reward flow behavior.",
                    "non_task_sinks": [],
                }
            ],
            "definitions": {
                "flows": [self.fx.build_base_flow("flow-shared", ["REQ-SHARED"])],
                "commands": [],
                "states": [],
            },
            "logical_references": [],
            "requirement_verification": [
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "flow_id": "flow-shared",
                    "rationale": "Owned by owner-plan.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            "requirement_route_memberships": [
                {"requirement_id": "REQ-SHARED", "flow_id": "flow-shared", "observable_role": "primary"}
            ],
            "requirement_evidence": [],
            "evidence_source_refs": [],
            "coverage_table": [
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "flow_id": "flow-shared",
                    "rationale": "Owned by owner-plan.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                }
            ],
            "applicability": [
                {"requirement_id": "REQ-SHARED", "disposition": "flow", "rationale": "Owned by owner-plan.", "other_verification_refs": []}
            ],
            "adoption_proof_refs": [copy.deepcopy(proof_owned)],
            "lineage": {"previous_plan_ref": None, "change_summary": "Owner plan.", "identity_alignment": []},
        }
        owner_plan_path = "docs/planning/b-route/plans/owner-plan/1.json"
        owner_plan_raw = self.fx.put_json(owner_plan_path, owner_plan)
        owner_plan_ref = _typed_ref(owner_plan_path, "newrouge.b-route-plan.v1", "owner-plan", 1, owner_plan_raw)

        consumer_plan = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "consumer-plan",
            "revision": 1,
            "source_identity": copy.deepcopy(src_identity),
            "requirements": [
                {
                    "requirement_id": "REQ-SHARED",
                    "source_block_ids": [block_id],
                    "acceptance_intent": "Consumer verifies shared flow.",
                    "non_task_sinks": [],
                }
            ],
            "definitions": {"flows": [], "commands": [], "states": []},
            "logical_references": [
                {
                    "kind": "flow",
                    "definition_id": "flow-shared",
                    "owner_plan_id": "owner-plan",
                    "owner_revision": 1,
                }
            ],
            "requirement_verification": [
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "flow_id": "flow-shared",
                    "rationale": "Consumes external shared flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            "requirement_route_memberships": [
                {"requirement_id": "REQ-SHARED", "flow_id": "flow-shared", "observable_role": "primary"}
            ],
            "requirement_evidence": [],
            "evidence_source_refs": [],
            "coverage_table": [
                {
                    "requirement_id": "REQ-SHARED",
                    "disposition": "flow",
                    "flow_id": "flow-shared",
                    "rationale": "Consumes external shared flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                }
            ],
            "applicability": [
                {"requirement_id": "REQ-SHARED", "disposition": "flow", "rationale": "Consumes external shared flow.", "other_verification_refs": []}
            ],
            "adoption_proof_refs": [copy.deepcopy(proof_owned)],
            "lineage": {"previous_plan_ref": None, "change_summary": "Consumer plan.", "identity_alignment": []},
        }
        consumer_plan_path = "docs/planning/b-route/plans/consumer-plan/1.json"
        consumer_plan_raw = self.fx.put_json(consumer_plan_path, consumer_plan)
        consumer_plan_ref = _typed_ref(consumer_plan_path, "newrouge.b-route-plan.v1", "consumer-plan", 1, consumer_plan_raw)

        policy_path = "docs/planning/b-route/policy.v1.json"
        policy_raw = self.fx.put_json(
            policy_path,
            {
                "schema_version": "newrouge.b-route-policy.v1",
                "policy_id": "policy",
                "policy_revision": 1,
                "switch_boundary": {
                    "default_route": "A",
                    "a_write_allowed": True,
                    "allowed_a_operations": ["chapter6"],
                    "authority_refs": [_owned_ref("authority", "docs/workflows/authority-note.md", [("docs/workflows/authority-note.md", authority_raw)])],
                },
                "frozen_a_refs": [_owned_ref("frozen_a_inventory", "docs/adr/ADR-0040-test.md", [("docs/adr/ADR-0040-test.md", adr_raw)])],
            },
        )
        policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy", 1, policy_raw)
        origins_path = "docs/planning/b-route/task-origins.v1.json"
        origins_raw = self.fx.put_json(
            origins_path,
            {
                "schema_version": "newrouge.b-route-origins.v1",
                "origins_id": "task-origins",
                "revision": 1,
                "tasks": [],
                "frozen_legacy_refs": [],
            },
        )
        origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)
        def_owners = [{"kind": "flow", "definition_id": "flow-shared", "plan_ref": copy.deepcopy(owner_plan_ref)}]
        target_pairs = [
            (policy_path, policy_raw),
            (origins_path, origins_raw),
            (owner_plan_path, owner_plan_raw),
            (consumer_plan_path, consumer_plan_raw),
        ]
        receipt_path = "docs/planning/b-route/commits/OP-SHARED.json"
        receipt_raw = self.fx.put_json(
            receipt_path,
            {
                "schema_version": "newrouge.b-route-commit.v1",
                "operation_id": "OP-SHARED",
                "revision": 1,
                "operation_digest": codec.canonical_digest({"op": "OP-SHARED"}),
                "scopes": [self.fx.scope_id],
                "authority": [
                    {"path": p, "before_digest": codec.raw_digest(r), "after_digest": codec.raw_digest(r)}
                    for p, r in [
                        ("docs/workflows/authority-note.md", authority_raw),
                        (manifest_path, manifest_raw),
                        (ledger_path, ledger_raw),
                        ("logs/ci/test-inputs/adoption-proof.json", proof_raw),
                    ]
                ],
                "targets": [
                    {
                        "path": p,
                        "before_digest": None,
                        "after_digest": codec.raw_digest(r),
                        "verification_mode": "immutable_bytes",
                        "codec_version": None,
                        "projection_digest": codec.raw_digest(r),
                    }
                    for p, r in target_pairs
                ],
                "plan_refs": [copy.deepcopy(owner_plan_ref), copy.deepcopy(consumer_plan_ref)],
                "binding_refs": [],
                "resolved_definitions": copy.deepcopy(def_owners),
                "result": {"target_paths": [p for p, _ in target_pairs], "scope_ids": [self.fx.scope_id]},
            },
        )
        receipt_ref = _typed_ref(receipt_path, "newrouge.b-route-commit.v1", "OP-SHARED", 1, receipt_raw)
        self.fx.put_json(
            records.CATALOG_PATH,
            {
                "schema_version": "newrouge.b-route-catalog.v1",
                "catalog_id": "catalog",
                "revision": 1,
                "policy_ref": policy_ref,
                "origins_ref": origins_ref,
                "scope_heads": [
                    {
                        "scope_id": self.fx.scope_id,
                        "plan_refs": [owner_plan_ref, consumer_plan_ref],
                        "binding_refs": [],
                        "receipt_ref": receipt_ref,
                    }
                ],
                "definition_owners": def_owners,
                "task_index": [],
            },
        )
        shared_res = preview.preview_task_changes(
            self.fx.root,
            plan_id="consumer-plan",
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
        )
        self.assertTrue(shared_res["ok"], shared_res["diagnostics"])
        self.assertEqual(shared_res["reuse_inventory"]["flow_count"], 1)
        self.assertEqual(shared_res["reuse_inventory"]["flows"][0]["id"], "flow-shared")
        self.assertEqual(shared_res["view_deltas"]["gameplay"][0]["flow_ids"], ["flow-shared"])

    def test_protection_ref_valid_invalid_incomplete_3a_missing_source_id_run_id_and_builder(self) -> None:
        audit_info, _ = self._standard_bundle()

        # 1) dev_cli_builders optional flags, None/empty rejection, and dev_cli parser func default
        ns_full = type(
            "Args",
            (),
            {
                "root": str(self.fx.root),
                "plan_id": self.fx.plan_id,
                "run_id": "run-opt",
                "audit_ref": audit_info["audit_ref"],
                "scope_id": self.fx.scope_id,
                "protection_ref": "docs/planning/b-route/prot.json",
                "manifest": "docs/testing/mvg/base.json",
                "change_intents": "logs/ci/test-inputs/ci.json",
            },
        )()
        built_full = dev_cli_builders.build_b_route_task_preview_cmd(ns_full)
        self.assertIn("--protection-ref", built_full)
        self.assertIn("--manifest", built_full)
        self.assertIn("--change-intents", built_full)
        for missing_attr in ("root", "plan_id", "run_id", "audit_ref", "scope_id"):
            with self.subTest(missing=missing_attr):
                attrs = {
                    "root": str(self.fx.root),
                    "plan_id": self.fx.plan_id,
                    "run_id": "run-opt",
                    "audit_ref": audit_info["audit_ref"],
                    "scope_id": self.fx.scope_id,
                }
                attrs[missing_attr] = None
                with self.assertRaises(ValueError):
                    dev_cli_builders.build_b_route_task_preview_cmd(type("Bad", (), attrs)())
        parsed = dev_cli.build_parser().parse_args(
            [
                "b-route-task-preview",
                "--root",
                str(self.fx.root),
                "--plan-id",
                self.fx.plan_id,
                "--run-id",
                "run-parser",
                "--audit-ref",
                audit_info["audit_ref"],
                "--scope-id",
                self.fx.scope_id,
            ]
        )
        self.assertIs(parsed.func, dev_cli.cmd_b_route_task_preview)

        # 2) Windows reserved device names rejected by create_run_directory
        for reserved in ("CON", "nul", "COM1", "LPT9"):
            with self.subTest(reserved=reserved), self.assertRaises(codec.CodecError) as caught:
                preview.create_run_directory(self.fx.root, reserved)
            self.assertEqual(caught.exception.diagnostic.reason_code, codec.ReasonCode.INVALID_ARGUMENT)

        # 3) --protection-ref: invalid schema, incomplete capture_complete=False, and valid capture_complete=True
        bad_prot = "logs/ci/test-inputs/bad-prot.json"
        self.fx.put_json(bad_prot, {"schema_version": "unknown.v0"})
        res_bad_prot = preview.preview_task_changes(
            self.fx.root,
            plan_id=self.fx.plan_id,
            scope_id=self.fx.scope_id,
            audit_ref=audit_info["audit_ref"],
            protection_ref=bad_prot,
        )
        self.assertFalse(res_bad_prot["ok"])
        self.assertEqual(res_bad_prot["diagnostics"][0]["reason_code"], codec.ReasonCode.UNKNOWN_SCHEMA.value)

        snap_dir = "logs/ci/test-inputs/prot-snap"
        raw_bytes = b'{"ok":true}\n'
        raw_sha = codec.raw_digest(raw_bytes)
        raw_rel = f"raw/{raw_sha[7:]}.bin"
        self.fx.put(f"{snap_dir}/{raw_rel}", raw_bytes)
        inv_raw = self.fx.put_json(f"{snap_dir}/inventory.json", {"schema_version": "test"})
        snap_path = f"{snap_dir}/snapshot.json"
        self.fx.put_json(
            snap_path,
            {
                "schema_version": protection.SCHEMA,
                "inventory": {"raw_digest": codec.raw_digest(inv_raw)},
                "raw_files": [{"path": "docs/gdd/reward.md", "exists": True, "artifact": raw_rel, "raw_digest": raw_sha}],
                "capture_complete": True,
            },
        )
        with patch.object(
            preview.protection,
            "verify_protection",
            return_value={
                "ok": True,
                "snapshot_digest": "sha256:" + "a" * 64,
                "capture_complete": False,
                "unresolved_inventory_diagnostics": [{"code": "missing-input"}],
            },
        ):
            res_inc = preview.preview_task_changes(
                self.fx.root,
                plan_id=self.fx.plan_id,
                scope_id=self.fx.scope_id,
                audit_ref=audit_info["audit_ref"],
                protection_ref=snap_path,
            )
            self.assertFalse(res_inc["ok"])
            self.assertEqual(res_inc["diagnostics"][0]["reason_code"], codec.ReasonCode.IDENTITY_UNPROVABLE.value)

        with patch.object(
            preview.protection,
            "verify_protection",
            return_value={
                "ok": True,
                "snapshot_digest": "sha256:" + "b" * 64,
                "capture_complete": True,
                "unresolved_inventory_diagnostics": [],
            },
        ):
            res_ok_prot = preview.preview_task_changes(
                self.fx.root,
                plan_id=self.fx.plan_id,
                scope_id=self.fx.scope_id,
                audit_ref=audit_info["audit_ref"],
                protection_ref=snap_path,
            )
            self.assertTrue(res_ok_prot["ok"], res_ok_prot["diagnostics"])
            self.assertTrue(res_ok_prot["protection"]["capture_complete"])
            obs_paths = {row["path"] for row in res_ok_prot["observations"]}
            self.assertIn(f"{snap_dir}/{raw_rel}", obs_paths)

        # 4) Missing source_identity file after 3B load -> owning_stage="3A" (P4)
        missing_ledger_path = audit_info["ledger_path"]
        real_read = preview.preflight.Observations.read

        def fail_on_ledger(obs_self, source, *, optional=False):
            if source == missing_ledger_path:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.FILE_NOT_FOUND,
                        codec.Stage.PATH,
                        source,
                        {"path": source, "value": "existing ledger"},
                        {"path": source, "value": "missing"},
                        source,
                    )
                )
            return real_read(obs_self, source, optional=optional)

        with patch.object(preview.preflight.Observations, "read", fail_on_ledger):
            res_3a = preview.preview_task_changes(
                self.fx.root,
                plan_id=self.fx.plan_id,
                scope_id=self.fx.scope_id,
                audit_ref=audit_info["audit_ref"],
            )
        self.assertFalse(res_3a["ok"])
        self.assertEqual(res_3a["diagnostics"][0]["expected"]["owning_stage"], "3A")

        # 5) Fail-closed when origins_preview schema validation fails (P1)
        bad_origin_res = records.RecordValidation(
            False,
            codec.Diagnostic(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                codec.Stage.SCHEMA,
                "task-origins",
                "valid origins",
                "invalid origins",
                "docs/planning/b-route/task-origins.v1.json",
            ),
        )
        real_validate = preview.records.validate_record

        def fail_origins_only(data, *, path=None):
            if path and path.endswith("task-origins.v1.json"):
                return bad_origin_res
            return real_validate(data, path=path)

        with patch.object(preview.records, "validate_record", fail_origins_only):
            res_bad_orig = preview.preview_task_changes(
                self.fx.root,
                plan_id=self.fx.plan_id,
                scope_id=self.fx.scope_id,
                audit_ref=audit_info["audit_ref"],
            )
        self.assertFalse(res_bad_orig["ok"])
        self.assertEqual(
            res_bad_orig["diagnostics"][0]["reason_code"],
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED.value,
        )


if __name__ == "__main__":
    unittest.main()
