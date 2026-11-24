"""Deterministic tests for Story 3.11 B-route target-slice Chapter 7 UI closure and evidence reuse.

Covers all 5 Story 3.11 matrix scenarios (SLICE_SCOPE, EVIDENCE_REUSE, HONEST_WIRING,
GOV_GAP_PATCH, HANDOFF_NOKCP), live evaluate_chapter6_gate enforcement (no precomputed shortcuts),
Story 3.1 change-intents validation, run_chapter7_ui_wiring multi-slice & artifact-manifest
validation, apply_chapter7_status_patch all-view mature-done protection, recursive .tscn
instancing, and CLI / dev_cli / dev_cli_builders wiring using setUpClass fixture caching.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
for _p in (str(SCRIPTS_PY), str(SCRIPTS_SC), str(SCRIPTS_PY / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter7_slice as ch7_slice
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_preflight as preflight
import _b_route_task_preview as task_preview
import apply_chapter7_status_patch as status_patch
import check_b_route_chapter7_slice as slice_cli
import dev_cli
import dev_cli_builders
import run_chapter7_ui_wiring as ch7_wiring

from test_b_route_chapter5_readiness import (
    _build_b_route_base_repo,
    _put,
    _put_json,
    _typed_ref,
)
from test_b_route_chapter6_gate import (
    DIAGNOSTIC_KEYS,
    _reconcile_task_ready,
)


def _reconcile_slice_task(root: Path, task_id: int, *, mode: str = "flow", include_planned: bool = False) -> dict:
    if task_id != 102:
        return _reconcile_task_ready(root, task_id=task_id, mode=mode, include_planned=include_planned)
    overlay_rel = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"
    dec_rel = "logs/ci/chapter5/decisions-task-102.json"
    _put_json(
        root,
        dec_rel,
        {
            "authority_decisions": [
                {"authority_ref": overlay_rel, "status": "compatible", "rationale": "Overlay matches reward consumer scope."},
                {"authority_ref": "ADR-0004", "status": "compatible", "rationale": "Contracts remain BCL-only."},
                {"authority_ref": "core.reward.offered", "status": "compatible", "rationale": "Event contract declared in EventTypes.cs."},
                {
                    "authority_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                    "status": "compatible",
                    "rationale": "Production command contract matches Stage-4 binding.",
                },
            ],
            "acceptance_links": [
                {
                    "acceptance_index": 1,
                    "requirement_ids": ["REQ-REWARD-1"],
                    "authority_refs": [overlay_rel, "ADR-0004", "core.reward.offered"],
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
                }
            ],
            "overlap_decisions": [],
            "findings": [],
        },
    )
    res = ch5_b.reconcile_b_route_chapter5(
        root,
        task_id=102,
        decisions=dec_rel,
        write_artifacts=True,
    )
    assert res["ok"], f"Fixture Chapter 5 reconciliation failed for task 102: {res}"
    return res


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            snap[p.relative_to(root).as_posix()] = p.read_bytes()
    return snap


def _reseal_plan_and_catalog(root: Path, *, plan_doc: dict | None = None, binding_doc: dict | None = None) -> None:
    """Re-seal plan/binding/origins/commit-receipt/catalog digests after a fixture mutation so live gates pass cleanly."""
    plan_rel = "docs/planning/b-route/plans/plan-reward/1.json"
    bind_rel = "docs/planning/b-route/bindings/plan-reward/1.json"
    origins_rel = "docs/planning/b-route/task-origins.v1.json"
    commit_rel = "docs/planning/b-route/commits/OP-INIT-001.json"
    catalog_rel = "docs/planning/b-route/catalog.v1.json"

    pdoc = plan_doc if plan_doc is not None else json.loads((root / plan_rel).read_text(encoding="utf-8"))
    bdoc = binding_doc if binding_doc is not None else json.loads((root / bind_rel).read_text(encoding="utf-8"))

    praw = _put_json(root, plan_rel, pdoc)
    pref = _typed_ref(plan_rel, "newrouge.b-route-plan.v1", "plan-reward", 1, praw)
    bdoc["plan_ref"] = pref
    braw = _put_json(root, bind_rel, bdoc)
    bref = _typed_ref(bind_rel, "newrouge.b-route-binding.v1", "plan-reward", 1, braw)

    odoc = json.loads((root / origins_rel).read_text(encoding="utf-8"))
    for row in odoc.get("tasks") or []:
        for i, pr in enumerate(row.get("plan_refs") or []):
            if pr.get("path") == plan_rel:
                row["plan_refs"][i] = pref
        for i, br in enumerate(row.get("binding_refs") or []):
            if br.get("path") == bind_rel:
                row["binding_refs"][i] = bref
    oraw = _put_json(root, origins_rel, odoc)

    commit_ref = None
    commit_path = root / commit_rel
    if commit_path.is_file():
        cm_doc = json.loads(commit_path.read_text(encoding="utf-8"))
        raw_by_rel = {plan_rel: praw, bind_rel: braw, origins_rel: oraw}
        for tgt in cm_doc.get("targets") or []:
            tpath = tgt.get("path")
            if tpath in raw_by_rel:
                dg = codec.raw_digest(raw_by_rel[tpath])
                tgt["after_digest"] = dg
                tgt["projection_digest"] = dg
        for i, pr in enumerate(cm_doc.get("plan_refs") or []):
            if pr.get("path") == plan_rel:
                cm_doc["plan_refs"][i] = pref
        for i, br in enumerate(cm_doc.get("binding_refs") or []):
            if br.get("path") == bind_rel:
                cm_doc["binding_refs"][i] = bref
        for rd in cm_doc.get("resolved_definitions") or []:
            if isinstance(rd.get("plan_ref"), dict) and rd["plan_ref"].get("path") == plan_rel:
                rd["plan_ref"] = pref
        cm_raw = _put_json(root, commit_rel, cm_doc)
        commit_ref = _typed_ref(
            commit_rel,
            str(cm_doc.get("schema_version") or "newrouge.b-route-commit.v1"),
            str(cm_doc.get("operation_id") or "OP-INIT-001"),
            int(cm_doc.get("revision") or 1),
            cm_raw,
        )

    cdoc = json.loads((root / catalog_rel).read_text(encoding="utf-8"))
    old_oref = cdoc.get("origins_ref") if isinstance(cdoc.get("origins_ref"), dict) else {}
    oref = _typed_ref(
        origins_rel,
        str(old_oref.get("schema_version") or "newrouge.b-route-origins.v1"),
        str(old_oref.get("entity_id") or "task-origins"),
        int(old_oref.get("revision") or 1),
        oraw,
    )
    cdoc["origins_ref"] = oref
    for head in cdoc.get("scope_heads") or []:
        for i, pr in enumerate(head.get("plan_refs") or []):
            if pr.get("path") == plan_rel:
                head["plan_refs"][i] = pref
        for i, br in enumerate(head.get("binding_refs") or []):
            if br.get("path") == bind_rel:
                head["binding_refs"][i] = bref
        if commit_ref is not None and isinstance(head.get("receipt_ref"), dict) and head["receipt_ref"].get("path") == commit_rel:
            head["receipt_ref"] = commit_ref
    for downer in cdoc.get("definition_owners") or []:
        if isinstance(downer.get("plan_ref"), dict) and downer["plan_ref"].get("path") == plan_rel:
            downer["plan_ref"] = pref
    for trow in cdoc.get("task_index") or []:
        for i, pr in enumerate(trow.get("plan_refs") or []):
            if pr.get("path") == plan_rel:
                trow["plan_refs"][i] = pref
        for i, br in enumerate(trow.get("binding_refs") or []):
            if br.get("path") == bind_rel:
                trow["binding_refs"][i] = bref
    _put_json(root, catalog_rel, cdoc)


_VALID_TSCN = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://Game.Godot/Scripts/Reward/RewardScreenAdapter.cs" id="1_script"]

[sub_resource type="Animation" id="Animation_fade"]
length = 0.25

[node name="RewardScene" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
offset_left = 16.0
offset_top = 12.0
theme_override_constants/margin_left = 8
script = ExtResource("1_script")

[node name="VBox" type="VBoxContainer" parent="."]
custom_minimum_size = Vector2(320, 180)
size_flags_horizontal = 3

[node name="ConfirmButton" type="Button" parent="VBox"]
unique_name_in_owner = true
text = "Confirm"

[node name="StatusLabel" type="Label" parent="VBox"]
text = "Ready"

[node name="AnimPlayer" type="AnimationPlayer" parent="."]

[connection signal="pressed" from="VBox/ConfirmButton" to="." method="OnConfirmPressed"]
"""

_VALID_ADAPTER_CS = """using Godot;

namespace Game.Godot.Scripts.Reward;

public partial class RewardScreenAdapter : Control
{
    private Button _confirmButton;
    private Label _statusLabel;

    public override void _Ready()
    {
        _confirmButton = GetNode<Button>("%ConfirmButton");
        _statusLabel = GetNode<Label>("VBox/StatusLabel");
    }

    public void OnConfirmPressed()
    {
        _statusLabel.Text = "Confirmed";
    }
}
"""

_VALID_GDUNIT_TEST = """extends GdUnitTestSuite

func test_reward_confirm_real_input() -> void:
    var scene = auto_free(load("res://Game.Godot/Scenes/UI/RewardScene.tscn").instantiate())
    add_child(scene)
    var btn = scene.get_node("%ConfirmButton")
    btn.emit_signal("pressed")
    assert_str(scene.get_node("VBox/StatusLabel").text).is_equal("Confirmed")
"""

_VALID_CS_CORE_TEST = """using Xunit;
public class RewardFlowTests
{
    [Fact]
    public void SelectsRewardDeterministically()
    {
        Assert.True(true);
    }
}
"""

_PROFILE_JSON = {
    "bucket_order": ["reward_flow", "unrelated_combat"],
    "fallback_bucket": "reward_flow",
    "surface_aliases": {},
    "buckets": {
        "reward_flow": {
            "feature_task_ids": [101, 102, 103],
            "slice_title": "Reward Offer, Confirm, And Return Flow",
            "screen_group": "Reward Offer And Confirm Surfaces",
            "audience": "player-facing",
            "ui_entry": "Reward Scene / Offer Choice / Return Path",
            "player_action": "Click one reward offer and press Confirm or Skip to return to map",
            "system_response": "Render locked offers, confirmation state, and route-owned return feedback",
            "suggested_surfaces": ["RewardScene", "ConfirmButton", "StatusLabel"],
            "section_headings": ["### 6.1.6 Reward Offer And Confirm Surfaces"],
            "scene_rel_path": "Game.Godot/Scenes/UI/RewardScene.tscn",
            "closure_task_ids": [],
            "wiring_task_id": 0,
            "screen_state": {
                "entry_state": "Show reward offers on combat victory.",
                "interaction_state": "Select reward and click Confirm.",
                "failure_state": "Show refusal feedback.",
                "recovery_exit": "Return to owned map boundary.",
            },
        },
        "unrelated_combat": {
            "feature_task_ids": [201],
            "slice_title": "Unrelated Pending Combat Slice",
            "screen_group": "Combat Surfaces",
            "audience": "player-facing",
            "ui_entry": "CombatHud",
            "player_action": "Play card",
            "system_response": "Resolve damage",
            "suggested_surfaces": ["CombatHud"],
            "section_headings": [],
            "scene_rel_path": "",
            "closure_task_ids": [],
            "wiring_task_id": 0,
        },
    },
}

_SINGLE_TASK_PROFILE_JSON = {
    **_PROFILE_JSON,
    "buckets": {
        "reward_flow": {
            **_PROFILE_JSON["buckets"]["reward_flow"],
            "feature_task_ids": [101],
        },
        "unrelated_combat": _PROFILE_JSON["buckets"]["unrelated_combat"],
    },
}


class Chapter7SliceTests(unittest.TestCase):
    """Covers SLICE_SCOPE, EVIDENCE_REUSE, HONEST_WIRING, GOV_GAP_PATCH, HANDOFF_NOKCP, and P-01..P-08."""

    _tmp_base: Path
    _flow_tpl: Path
    _nonflow_tpl: Path
    _flow_t101_iset: str
    _flow_gd_test_sha: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_base = Path(tempfile.mkdtemp(prefix="b_route_ch7_slice_"))

        # Template 1: Committed Flow B-route repo with valid scene, adapter, tests, and unrelated pending Task 201.
        cls._flow_tpl = cls._tmp_base / "flow_tpl"
        cls._flow_tpl.mkdir(parents=True, exist_ok=True)
        _build_b_route_base_repo(
            cls._flow_tpl,
            mode="flow",
            binding_stage="5",
            include_planned=False,
            task101_status="done",
            task102_status="in-progress",
            task103_status="pending",
        )
        _put(cls._flow_tpl, "Game.Core.Tests/Reward/RewardFlowTests.cs", _VALID_CS_CORE_TEST)
        _put(cls._flow_tpl, "Game.Godot/Scenes/UI/RewardScene.tscn", _VALID_TSCN)
        _put(cls._flow_tpl, "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs", _VALID_ADAPTER_CS)
        gd_raw = _put(cls._flow_tpl, "Tests.Godot/tests/UI/test_reward_scene_input.gd", _VALID_GDUNIT_TEST)
        cls._flow_gd_test_sha = codec.raw_digest(gd_raw)
        _put_json(cls._flow_tpl, "docs/workflows/chapter7-profile.json", _PROFILE_JSON)
        _put_json(cls._flow_tpl, "docs/workflows/chapter7-single-profile.json", _SINGLE_TASK_PROFILE_JSON)

        # Include an unrelated empty test ("OtherTests.cs" has zero [Fact]s!) in a second cumulative MVG flow
        # (sealed cleanly) to verify P-05 target-Flow filtering never fails or flags unrelated cumulative flows.
        mdoc_rel = "docs/testing/mvg/reward-baseline.json"
        mdoc = json.loads((cls._flow_tpl / mdoc_rel).read_text(encoding="utf-8"))
        mdoc["coverage"]["required_flow_ids"].append("flow-other-unrelated")
        mdoc["coverage"]["blocking_task_ids"] = sorted({*mdoc["coverage"]["blocking_task_ids"], 201})
        mdoc["flows"].append(
            {
                "id": "flow-other-unrelated",
                "task_ids": [201],
                "outcome": "Unrelated other flow in cumulative MVG manifest.",
                "source_paths": ["Game.Core/Services/OtherService.cs"],
                "test_ids": ["test-unrelated-other-flow"],
                "handoffs": [
                    {
                        "producer_task": 201,
                        "consumer_task": 201,
                        "owner_task": 201,
                        "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                        "behavior": "Unrelated other flow handoff.",
                        "test_ids": ["test-unrelated-other-flow"],
                    }
                ],
            }
        )
        mdoc["tests"].append(
            {
                "id": "test-unrelated-other-flow",
                "kind": "dotnet",
                "evidence_level": "domain-integration",
                "path": "Game.Core.Tests/Other/OtherTests.cs",
                "selector": "OtherTests",
                "state": "implemented",
                "min_tests": 1,
            }
        )
        mraw = _put_json(cls._flow_tpl, mdoc_rel, mdoc)
        mdigest = codec.raw_digest(mraw)
        bdoc_init = json.loads((cls._flow_tpl / "docs/planning/b-route/bindings/plan-reward/1.json").read_text(encoding="utf-8"))
        for mref in bdoc_init.get("manifest_refs") or []:
            for mf in mref.get("files") or []:
                if mf.get("path") == mdoc_rel:
                    mf["raw_digest"] = mdigest
        for obl in bdoc_init.get("obligations") or []:
            obl["responsibility"] = str(obl.get("responsibility") or "").replace(
                '"out_of_scope_future_flow_ids":[]',
                '"out_of_scope_future_flow_ids":["flow-other-unrelated"]',
            )
            for vref in obl.get("verification_refs") or []:
                for vf in vref.get("files") or []:
                    if vf.get("path") == mdoc_rel:
                        vf["raw_digest"] = mdigest
        _reseal_plan_and_catalog(cls._flow_tpl, binding_doc=bdoc_init)

        # Reconcile tasks 101, 102, 103 in target slice; intentionally leave unrelated Task 201 pending & unreconciled!
        r101 = _reconcile_slice_task(cls._flow_tpl, task_id=101, mode="flow", include_planned=False)
        for tid in (102, 103):
            _reconcile_slice_task(cls._flow_tpl, task_id=tid, mode="flow", include_planned=False)
        cls._flow_t101_iset = str(r101["input_set_digest"])

        # Template 2: Committed non-Flow / non-UI repo with live adoption_proof_refs & other_verification_refs.
        cls._nonflow_tpl = cls._tmp_base / "nonflow_tpl"
        cls._nonflow_tpl.mkdir(parents=True, exist_ok=True)
        _build_b_route_base_repo(
            cls._nonflow_tpl,
            mode="nonflow",
            binding_stage="5",
            include_planned=False,
            task101_status="in-progress",
        )
        _reconcile_task_ready(cls._nonflow_tpl, task_id=101, mode="nonflow", include_planned=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp_base, ignore_errors=True)

    def _clone_flow(self) -> Path:
        dest = Path(tempfile.mkdtemp(prefix="case_flow_", dir=str(self._tmp_base)))
        shutil.copytree(self._flow_tpl, dest, dirs_exist_ok=True)
        return dest

    def _clone_nonflow(self) -> Path:
        dest = Path(tempfile.mkdtemp(prefix="case_nonflow_", dir=str(self._tmp_base)))
        shutil.copytree(self._nonflow_tpl, dest, dirs_exist_ok=True)
        return dest

    def _valid_evidence_record(self, *, iset_digest: str | None = None, test_sha: str | None = None) -> dict:
        return {
            "task_id": 101,
            "flow_id": "flow-reward-select",
            "binding_ref": "docs/planning/b-route/bindings/plan-reward/1.json",
            "binding_revision": 1,
            "obligation_id": "OBL-UI-REWARD-INPUT",
            "evidence_kind": "gdunit_engine_input",
            "input_set_digest": iset_digest or self._flow_t101_iset,
            "test_path": "Tests.Godot/tests/UI/test_reward_scene_input.gd",
            "test_sha256": test_sha or self._flow_gd_test_sha,
            "tests": 2,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "state": "passed",
            "real_engine_input": True,
        }

    def _assert_traceable_items(self, items: list[dict]) -> None:
        for item in items:
            for key in ("item_id", "category", "status", "binding_ref", "task_id", "flow_id", "evidence_ref"):
                self.assertIn(key, item)
            self.assertIsInstance(item["binding_ref"], str, f"binding_ref must be non-null str: {item}")
            self.assertTrue(item["binding_ref"].strip(), f"binding_ref must be non-empty: {item}")
            self.assertIsInstance(item["evidence_ref"], dict, f"evidence_ref must be non-null dict: {item}")
            self.assertTrue(item["evidence_ref"].get("path"), f"evidence_ref.path missing: {item}")
            self.assertTrue(
                str(item["evidence_ref"].get("raw_digest") or "").startswith("sha256:"),
                f"evidence_ref.raw_digest must start with sha256:: {item}",
            )

    # ------------------------------------------------------------------
    # AC-1: SLICE_SCOPE
    # ------------------------------------------------------------------
    def test_ac1_slice_scope_evaluates_target_slice_without_waiting_for_whole_game_zero_writes(self) -> None:
        root = self._clone_flow()
        before = _tree_snapshot(root)
        res = ch7_slice.evaluate_chapter7_slice(
            root,
            flow_id="flow-reward-select",
            slice_name="reward_flow",
            ui_evidence={"evidence": [self._valid_evidence_record()]},
        )
        self.assertEqual(_tree_snapshot(root), before)
        self.assertTrue(res["ok"])
        self.assertEqual(res["ui_applicability"], "applicable")
        self.assertEqual(res["target_task_ids"], [101, 102, 103])
        self.assertNotIn(201, res["target_task_ids"])
        self.assertTrue(res["declared_ui_obligations"]["scene_entry"])
        self.assertTrue(res["declared_ui_obligations"]["return_path"])
        self.assertTrue(res["declared_ui_obligations"]["real_engine_input"])
        self.assertTrue(res["declared_ui_obligations"]["feedback"])
        self.assertEqual(set(res["declared_ui_obligations"]["four_part_bindings"].keys()), {"domain_rules", "csharp_adapter", "binding", "scene"})
        self.assertEqual(res["global_knowledge_refresh"], "not_performed")
        self.assertFalse(res["runtime_verified"])
        self.assertFalse(res["default_b_enabled"])
        self.assertFalse(res["flow_all_required_obligations_completed"])
        self._assert_traceable_items(res["verified_items"])
        self._assert_traceable_items(res["pending_items"])
        self._assert_traceable_items(res["manual_items"])
        self._assert_traceable_items(res["blocked_items"])
        # P-05: Cumulative MVG manifest unrelated flow/test is filtered out; implemented bound test stays pending!
        self.assertTrue(any(p["category"] == "unexecuted_bound_test" for p in res["pending_items"]))
        self.assertFalse(any("unrelated" in p["item_id"] for p in res["pending_items"] + res["blocked_items"]))

    def test_ac1_legal_non_ui_scope_returns_not_applicable_with_proof(self) -> None:
        root = self._clone_nonflow()
        before = _tree_snapshot(root)
        res = ch7_slice.evaluate_chapter7_slice(root, task_ids=[101])
        self.assertEqual(_tree_snapshot(root), before)
        self.assertTrue(res["ok"])
        self.assertEqual(res["ui_applicability"], "not_applicable")
        self.assertEqual(res["reason"], "ui_not_applicable_with_committed_proof")
        self.assertTrue(res["non_ui_proof"]["adoption_proof_refs"])
        self.assertTrue(res["non_ui_proof"]["other_verification_refs"])
        self.assertEqual(res["pending_items"], [])
        self.assertEqual(res["blocked_items"], [])
        self._assert_traceable_items(res["verified_items"])

        # Tampering the non-UI proof file must fail digest verification & never return not_applicable!
        _put(root, "docs/testing/nonflow-checklist.md", "# Tampered checklist\n")
        res_tampered = ch7_slice.evaluate_chapter7_slice(root, task_ids=[101])
        self.assertFalse(res_tampered["ok"])
        self.assertNotEqual(res_tampered["ui_applicability"], "not_applicable")

    def test_ac1_undeclared_blank_ui_fields_fail_closed_never_auto_skip(self) -> None:
        root = self._clone_flow()
        blank_profile = json.loads((root / "docs/workflows/chapter7-single-profile.json").read_text(encoding="utf-8"))
        blank_profile["buckets"]["reward_flow"]["player_action"] = ""
        _put_json(root, "docs/workflows/chapter7-single-profile.json", blank_profile)

        res = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["ui_applicability"], "applicable")
        self.assertEqual(res["reason_code"], codec.ReasonCode.MISSING_REQUIRED_FIELD.value)
        self.assertIn(res["return_stage"], ("3B", "4"))
        self.assertTrue(any(item["category"] == "ui_declaration" for item in res["blocked_items"]))
        self._assert_traceable_items(res["blocked_items"])

    def test_p04_generic_flow_fields_and_default_profile_never_mask_blank_ui_and_zero_task_flow_blocks(self) -> None:
        # 1. Task/Flow without --slice (and no explicit Flow.ui) cannot use generic entry/success_end/observable_result!
        res_no_slice = ch7_slice.evaluate_chapter7_slice(self._flow_tpl, task_ids=[101])
        self.assertFalse(res_no_slice["ok"])
        self.assertEqual(res_no_slice["reason_code"], codec.ReasonCode.MISSING_REQUIRED_FIELD.value)
        self.assertTrue(any(item["category"] == "ui_declaration" for item in res_no_slice["blocked_items"]))

        # 2. Removing repo chapter7-profile.json & passing --slice unclassified cannot use built-in placeholders!
        root = self._clone_flow()
        (root / "docs/workflows/chapter7-profile.json").unlink()
        res_default = ch7_slice.evaluate_chapter7_slice(root, slice_name="unclassified", task_ids=[101])
        self.assertFalse(res_default["ok"])
        self.assertEqual(res_default["reason_code"], codec.ReasonCode.MISSING_REQUIRED_FIELD.value)

        # 3. B-route UI Flow with zero mapped tasks fails closed!
        root_zero = self._clone_flow()
        bdoc = json.loads((root_zero / "docs/planning/b-route/bindings/plan-reward/1.json").read_text(encoding="utf-8"))
        for tm in bdoc["task_mappings"]:
            tm["flow_ids"] = []
        _reseal_plan_and_catalog(root_zero, binding_doc=bdoc)
        res_zero = ch7_slice.evaluate_chapter7_slice(root_zero, flow_id="flow-reward-select")
        self.assertFalse(res_zero["ok"])
        self.assertEqual(res_zero["target_task_ids"], [])
        self.assertTrue(any(b["item_id"].startswith("blocked:flow-zero-tasks:") for b in res_zero["blocked_items"]))

    # ------------------------------------------------------------------
    # AC-2: EVIDENCE_REUSE & P-01 / P-05
    # ------------------------------------------------------------------
    def test_ac2_reuses_matching_chapter6_engine_input_and_rejects_stale_static_method_call(self) -> None:
        root = self._flow_tpl
        valid = self._valid_evidence_record()
        stale = self._valid_evidence_record(iset_digest="sha256:" + "0" * 64)
        wrong_sha = self._valid_evidence_record(test_sha="sha256:" + "1" * 64)
        static_only = {**self._valid_evidence_record(), "evidence_kind": "static_wiring"}
        method_only = {
            **self._valid_evidence_record(),
            "evidence_kind": "method_call_only",
            "test_path": "Game.Core.Tests/Reward/RewardFlowTests.cs",
        }
        wrong_cond = {**self._valid_evidence_record(), "condition": "unrelated_profile_condition"}
        wrong_rev = {**self._valid_evidence_record(), "binding_revision": 99}
        missing_flag = {k: v for k, v in self._valid_evidence_record().items() if k != "real_engine_input"}
        traversal_path = {
            **self._valid_evidence_record(),
            "test_path": "Tests.Godot/../Game.Core.Tests/Reward/RewardFlowTests.cs",
        }

        res = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            delivery_profile="fast-ship",
            ui_evidence={
                "evidence": [
                    valid,
                    stale,
                    wrong_sha,
                    static_only,
                    method_only,
                    wrong_cond,
                    wrong_rev,
                    missing_flag,
                    traversal_path,
                ]
            },
        )
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["reused_ui_obligations"]), 1)
        rev = res["reused_ui_obligations"][0]
        self.assertEqual(rev["task_id"], 101)
        self.assertEqual(rev["flow_id"], "flow-reward-select")
        self.assertEqual(rev["binding_ref"], "docs/planning/b-route/bindings/plan-reward/1.json")
        self.assertTrue(rev["test_identity_matched"])
        self.assertTrue(rev["reused_from_chapter6"])
        self.assertEqual(len(res["rejected_evidence"]), 8)
        reasons = {r["reason"] for r in res["rejected_evidence"]}
        self.assertIn("stale_input_set_digest", reasons)
        self.assertIn("test_identity_mismatch", reasons)
        self.assertIn("static_wiring_cannot_satisfy_real_engine_input", reasons)
        self.assertIn("method_call_only_cannot_satisfy_real_engine_input", reasons)
        self.assertIn("mismatched_execution_condition", reasons)
        self.assertIn("mismatched_binding_revision", reasons)
        self.assertIn("real_engine_input_not_exercised", reasons)
        self.assertIn("unsafe_or_missing_test_path", reasons)

        # Without valid engine-input evidence, static_wiring alone keeps real_engine_input pending!
        res_static_only = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            ui_evidence={"evidence": [static_only, method_only]},
        )
        self.assertEqual(res_static_only["reused_ui_obligations"], [])
        self.assertTrue(any(p["category"] == "real_engine_input" and p["status"] == "pending" for p in res_static_only["pending_items"]))
        self._assert_traceable_items(res_static_only["pending_items"])

    def test_p01_p05_evidence_dir_errors_bool_counts_failed_runtime_and_early_tamper(self) -> None:
        root = self._flow_tpl

        # 1. Non-existent --evidence-dir fails closed with file_not_found.
        res_missing_dir = ch7_slice.evaluate_chapter7_slice(
            root,
            flow_id="flow-reward-select",
            slice_name="reward_flow",
            evidence_dir="logs/ci/does-not-exist",
        )
        self.assertFalse(res_missing_dir["ok"])
        self.assertEqual(res_missing_dir["reason_code"], codec.ReasonCode.FILE_NOT_FOUND.value)

        # 2. File passed as --evidence-dir fails closed with invalid_argument.
        res_file_dir = ch7_slice.evaluate_chapter7_slice(
            root,
            flow_id="flow-reward-select",
            slice_name="reward_flow",
            evidence_dir="docs/workflows/chapter7-profile.json",
        )
        self.assertFalse(res_file_dir["ok"])
        self.assertEqual(res_file_dir["reason_code"], codec.ReasonCode.INVALID_ARGUMENT.value)

        # 3. Boolean tests=True and failed/skipped runtime evidence block closure (status="failed", ok=False).
        bool_rec = {**self._valid_evidence_record(), "tests": True}
        failed_rec = {**self._valid_evidence_record(), "state": "failed", "failures": 1}
        skipped_rec = {**self._valid_evidence_record(), "skipped": 1}
        res_fail_rt = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            ui_evidence={"evidence": [bool_rec, failed_rec, skipped_rec]},
        )
        self.assertFalse(res_fail_rt["ok"])
        failed_blocks = [b for b in res_fail_rt["blocked_items"] if b["category"] == "runtime_evidence_failed"]
        self.assertEqual(len(failed_blocks), 3)
        self.assertTrue(all(b["status"] == "failed" for b in failed_blocks))
        self._assert_traceable_items(failed_blocks)
        self.assertFalse(any("unrelated" in p["item_id"] for p in res_fail_rt["pending_items"] + res_fail_rt["blocked_items"]))

        # 4. Early anti-tamper guard fires even on non-UI (not_applicable) repos!
        res_nf_tamper = ch7_slice.evaluate_chapter7_slice(
            self._nonflow_tpl,
            task_ids=[101],
            gap_input={"direct_triplet_write": True},
        )
        self.assertFalse(res_nf_tamper["ok"])
        self.assertNotEqual(res_nf_tamper["ui_applicability"], "not_applicable")
        self.assertTrue(any(b["category"] == "governed_gap_protection" for b in res_nf_tamper["blocked_items"]))

    # ------------------------------------------------------------------
    # AC-3: HONEST_WIRING & P-06
    # ------------------------------------------------------------------
    def test_ac3_detects_broken_node_signal_type_and_lifecycle_mismatches(self) -> None:
        root = self._clone_flow()
        broken_cs = """using Godot;
public partial class RewardScreenAdapter : Control
{
    public RewardScreenAdapter()
    {
        var early = GetNode<Button>("%ConfirmButton");
    }
    public override void _Ready()
    {
        var missing = GetNode<Button>("VBox/MissingButton");
        var wrongType = GetNode<Button>("VBox/StatusLabel");
        var noBareFallback = GetNode<Label>("StatusLabel");
    }
}
"""
        _put(root, "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs", broken_cs)
        res = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
        )
        self.assertFalse(res["ok"])
        self.assertFalse(res["wiring_inspection"]["wiring_static_ok"])
        kinds = {f["failure_kind"] for f in res["wiring_inspection"]["findings"]}
        self.assertIn("broken_node_binding", kinds)
        self.assertIn("object_type_mismatch", kinds)
        self.assertIn("lifecycle_mismatch", kinds)
        self.assertIn("broken_signal_binding", kinds)
        # Bare-name anywhere-in-tree fallback removed: StatusLabel under VBox must NOT resolve as "StatusLabel"!
        broken_nodes = {f["node_path"] for f in res["wiring_inspection"]["findings"] if f["failure_kind"] == "broken_node_binding"}
        self.assertIn("StatusLabel", broken_nodes)
        self.assertTrue(len(res["manual_items"]) >= 1)
        self.assertTrue(all(m["status"] == "manual_pending" for m in res["manual_items"]))
        self.assertFalse(res["flow_all_required_obligations_completed"])
        self._assert_traceable_items(res["blocked_items"])
        self._assert_traceable_items(res["manual_items"])

    def test_p06_recursive_tscn_instances_comments_owner_relative_and_cs_compat(self) -> None:
        root = self._clone_flow()
        child_tscn = """[gd_scene format=3]

[node name="OfferCard" type="Control"]

[node name="PickButton" type="Button" parent="."]
text = "Pick"
"""
        _put(root, "Game.Godot/Scenes/UI/OfferCard.tscn", child_tscn)
        parent_tscn = """[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://Game.Godot/Scripts/Reward/RewardScreenAdapter.cs" id="1_script"]
[ext_resource type="PackedScene" path="res://Game.Godot/Scenes/UI/OfferCard.tscn" id="2_card"]
[ext_resource type="Script" path="res://Game.Godot/Scripts/Reward/CustomConfirmButton.cs" id="3_btn"]

[node name="RewardScene" type="Control"]
script = ExtResource("1_script")

[node name="VBox" type="VBoxContainer" parent="."]

[node name="ConfirmButton" type="Button" parent="VBox"]
unique_name_in_owner = true
script = ExtResource("3_btn")

[node name="StatusLabel" type="Label" parent="VBox"]

[node name="SlotA" parent="VBox" instance=ExtResource("2_card")]

[node name="SfxPlayer" type="AudioStreamPlayer" parent="."]

[connection signal="pressed" from="VBox/ConfirmButton" to="." method="OnConfirmPressed"]
[connection signal="pressed" from="VBox/SlotA/PickButton" to="VBox/StatusLabel" method="hide"]
"""
        _put(root, "Game.Godot/Scenes/UI/RewardScene.tscn", parent_tscn)
        _put(
            root,
            "Game.Godot/Scripts/Reward/CustomConfirmButton.cs",
            """using Godot;
public partial class CustomConfirmButton : Button
{
    public override void _Ready()
    {
        var sibling = GetNode<Label>("../StatusLabel");
    }
}
""",
        )
        _put(
            root,
            "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs",
            """using Godot;
public partial class RewardScreenAdapter : Control
{
    public override void _Ready()
    {
        // Commented fake binding must be ignored: GetNode<Button>("VBox/DoesNotExist")
        var note = "GetNode<Button>(\\"Fake\\")";
        var btn = GetNode<CustomConfirmButton>("%ConfirmButton");
        var pick = GetNode<Button>("VBox/SlotA/PickButton");
        var anyNode = GetNode<Node>("SfxPlayer");
        btn.QueueFree();
        if (false) QueueFree();
    }

    void OnConfirmPressed()
    {
    }
}
""",
        )
        res = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
        )
        self.assertTrue(res["ok"], f"Expected P-06 valid recursive/relative scene wiring to pass: {res['wiring_inspection']}")
        self.assertTrue(res["wiring_inspection"]["wiring_static_ok"])

        # Removing the instanced child scene must fail honestly!
        (root / "Game.Godot/Scenes/UI/OfferCard.tscn").unlink()
        wiring_missing = ch7_slice.inspect_scene_and_adapter_wiring(
            root,
            scene_paths=["Game.Godot/Scenes/UI/RewardScene.tscn"],
            adapter_paths=["Game.Godot/Scripts/Reward/RewardScreenAdapter.cs"],
            binding_objects=[],
        )
        self.assertFalse(wiring_missing["wiring_static_ok"])
        self.assertTrue(any(f["failure_kind"] in ("missing_instanced_scene", "broken_scene_instance", "missing_scene_file") or "OfferCard" in str(f.get("message", "")) for f in wiring_missing["findings"]))

    def test_ac3_planned_stays_pending_and_skipped_or_empty_tests_fail(self) -> None:
        # Planned test in MVG manifest stays pending AND skipped implemented test fails closed (with live Chapter 5 reconciliation!).
        root_planned = Path(tempfile.mkdtemp(prefix="case_planned_", dir=str(self._tmp_base)))
        _build_b_route_base_repo(root_planned, mode="flow", binding_stage="5", include_planned=True)
        _put(
            root_planned,
            "Game.Core.Tests/Reward/RewardFlowTests.cs",
            'using Xunit;\npublic class RewardFlowTests { [Fact(Skip="disabled")] public void T() {} }\n',
        )
        _put(root_planned, "Game.Godot/Scenes/UI/RewardScene.tscn", _VALID_TSCN)
        _put(root_planned, "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs", _VALID_ADAPTER_CS)
        _put_json(root_planned, "docs/workflows/chapter7-single-profile.json", _SINGLE_TASK_PROFILE_JSON)
        _reconcile_slice_task(root_planned, task_id=101, mode="flow", include_planned=True)
        res_p = ch7_slice.evaluate_chapter7_slice(
            root_planned,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            task_ids=[101],
        )
        self.assertFalse(res_p["ok"])
        self.assertTrue(any(p["category"] == "planned_test_obligation" and p["status"] == "pending" for p in res_p["pending_items"]))
        self.assertTrue(any(b["category"] == "test_evidence_integrity" and b["status"] == "failed" for b in res_p["blocked_items"]))
        self._assert_traceable_items(res_p["pending_items"])
        self._assert_traceable_items(res_p["blocked_items"])

        # Commented-out [Fact] and GDScript do_skip( checks via _inspect_test_file_integrity:
        _put(root_planned, "Game.Core.Tests/Reward/CommentedOnly.cs", "// [Fact]\npublic class C {}\n")
        self.assertEqual(ch7_slice._inspect_test_file_integrity(root_planned, "Game.Core.Tests/Reward/CommentedOnly.cs")["status"], "empty")
        _put(root_planned, "Tests.Godot/tests/UI/test_do_skip.gd", "extends GdUnitTestSuite\nfunc test_x():\n    do_skip(true)\n")
        self.assertEqual(ch7_slice._inspect_test_file_integrity(root_planned, "Tests.Godot/tests/UI/test_do_skip.gd")["status"], "skipped")
        _put(root_planned, "Game.Core.Tests/Reward/IgnoreUntil.cs", "[IgnoreUntil(\"2027\")]\n[Fact]\npublic void X() {}\n")
        self.assertEqual(ch7_slice._inspect_test_file_integrity(root_planned, "Game.Core.Tests/Reward/IgnoreUntil.cs")["status"], "skipped")

    # ------------------------------------------------------------------
    # AC-4: GOV_GAP_PATCH & P-02 / P-07
    # ------------------------------------------------------------------
    def test_ac4_governed_gap_routing_deltas_story31_compat_synonymous_reject_and_tscn_guard(self) -> None:
        root = self._clone_flow()
        # Add committed uncovered requirement REQ-REWARD-2 to plan-reward so Story 3.1 validator accepts create delta!
        pdoc = json.loads((root / "docs/planning/b-route/plans/plan-reward/1.json").read_text(encoding="utf-8"))
        verif_r2 = {
            "requirement_id": "REQ-REWARD-2",
            "disposition": "flow",
            "flow_id": "flow-reward-select",
            "rationale": "Verified in reward selection flow.",
            "sink_id": None,
            "verification_ref": None,
            "authority_ref": None,
            "evidence_ids": ["EV-REWARD-2"],
        }
        pdoc["requirements"].append(
            {
                "requirement_id": "REQ-REWARD-2",
                "source_block_ids": ["BLK-REWARD-1"],
                "acceptance_intent": "Render relic synergy tooltip panel on reward screen.",
                "non_task_sinks": [],
            }
        )
        pdoc["definitions"]["flows"][0]["requirement_ids"].append("REQ-REWARD-2")
        pdoc["requirement_verification"].append(verif_r2)
        pdoc["requirement_route_memberships"].append(
            {
                "requirement_id": "REQ-REWARD-2",
                "flow_id": "flow-reward-select",
                "observable_role": "Observe relic synergy tooltip panel on reward screen.",
            }
        )
        pdoc["requirement_evidence"].append(
            {
                "requirement_id": "REQ-REWARD-2",
                "evidence_id": "EV-REWARD-2",
                "kind": "implementation_reference",
                "source_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                "covered_behavior": "Relic synergy tooltip panel readout on reward screen.",
                "flow_ids": ["flow-reward-select"],
                "test_ids": ["test-reward-flow"],
            }
        )
        pdoc["coverage_table"].append({k: v for k, v in verif_r2.items() if k != "evidence_ids"})
        pdoc["applicability"].append(
            {
                "requirement_id": "REQ-REWARD-2",
                "disposition": "flow",
                "rationale": verif_r2["rationale"],
                "other_verification_refs": [],
            }
        )
        _reseal_plan_and_catalog(root, plan_doc=pdoc)
        _reconcile_slice_task(root, task_id=101, mode="flow", include_planned=False)

        # 1. Definition/contract gap routes to owning_stage="4" + genuine UI gap produces Story 3.1 "operations" delta.
        res_gap = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            task_ids=[101],
            gap_input={
                "changed_paths": ["Game.Core/Contracts/Reward/SelectRewardCommand.cs"],
                "gap_categories": ["production_contract"],
                "missing_ui_tasks": [
                    {
                        "title": "Add relic synergy tooltip panel for reward screen",
                        "view": "gameplay",
                        "requirement_ids": ["REQ-REWARD-2"],
                        "rationale": "New tooltip requirement not covered by existing tasks.",
                    }
                ],
            },
        )
        self.assertFalse(res_gap["ok"])
        self.assertEqual(res_gap["governed_gap_routing"][0]["owning_stage"], "4")
        deltas = res_gap["proposed_governed_deltas"]
        self.assertIsNotNone(deltas)
        self.assertEqual(deltas["schema_version"], ch7_slice.DELTA_CANDIDATE_SCHEMA)
        self.assertIn("operations", deltas)
        self.assertNotIn("intents", deltas)
        self.assertEqual(len(deltas["operations"]), 1)
        self.assertIsNone(deltas["operations"][0]["task_id"])
        self.assertEqual(deltas["operations"][0]["action"], "create")
        self.assertFalse(deltas["task_triplet_written"])
        self.assertFalse(deltas["permanent_ids_allocated"])
        self.assertTrue(res_gap["native_scene_manual_regions_preserved"])

        # Validate emitted delta directly with Story 3.1 _b_route_task_preview._validate_change_intents!
        delta_rel = "logs/ci/test-governed-delta.json"
        _put_json(root, delta_rel, deltas)
        obs = preflight.Observations(root)
        triplet = task_preview._load_triplet(obs)
        flows_by_id = {f["id"]: f for f in pdoc["definitions"]["flows"]}
        validated_ci = task_preview._validate_change_intents(
            obs,
            delta_rel,
            plan=pdoc,
            flows_by_id=flows_by_id,
            triplet=triplet,
            manifest_info=None,
            ledger_blocks={"BLK-REWARD-1": {}},
        )
        self.assertIsNotNone(validated_ci)

        # 2. Synonymous duplicate (including intra-batch & tasks_back), permanent ID, direct write, clear done,
        # and clobbering .tscn manual regions (including Animation sub_resource body & layout_mode!) -> all blocked!
        edited_anim_tscn = _VALID_TSCN.replace("length = 0.25", "length = 1.50").replace("layout_mode = 3\n", "")
        res_bad = ch7_slice.evaluate_chapter7_slice(
            root,
            slice_name="reward_flow",
            profile_path="docs/workflows/chapter7-single-profile.json",
            task_ids=[101],
            gap_input={
                "direct_triplet_write": True,
                "clear_done_status": True,
                "allocate_permanent_id": True,
                "missing_ui_tasks": [
                    {
                        "title": "Reward producer task",
                        "flow_ids": ["flow-reward-select"],
                        "requirement_ids": ["REQ-REWARD-1"],
                    },
                    {
                        "title": "Forge permanent id task",
                        "action": "create",
                        "task_id": 999,
                        "requirement_ids": ["REQ-REWARD-2"],
                    },
                    {
                        "title": "Add relic synergy tooltip panel for reward screen",
                        "requirement_ids": ["REQ-REWARD-2"],
                    },
                    {
                        "title": "Add relic synergy tooltip panel for reward screen",
                        "requirement_ids": ["REQ-REWARD-2"],
                    },
                ],
                "proposed_scene_patches": {
                    "Game.Godot/Scenes/UI/RewardScene.tscn": edited_anim_tscn,
                },
            },
        )
        self.assertFalse(res_bad["ok"])
        self.assertFalse(res_bad["native_scene_manual_regions_preserved"])
        cats = {b["category"] for b in res_bad["blocked_items"]}
        self.assertIn("native_scene_manual_region", cats)
        self.assertIn("governed_gap_protection", cats)
        self.assertIn("synonymous_duplicate_task", cats)
        self.assertTrue(any(b["item_id"] == "blocked:permanent-id-allocation" for b in res_bad["blocked_items"]))
        self._assert_traceable_items(res_bad["blocked_items"])

    def test_ac4_apply_chapter7_status_patch_forbids_clearing_mature_done_across_all_views(self) -> None:
        root = self._clone_flow()
        tasks_json = root / ".taskmaster" / "tasks" / "tasks.json"
        tasks_back = root / ".taskmaster" / "tasks" / "tasks_back.json"
        # Also test "completed" status on task 102 in tasks_back.json while tasks.json says in-progress!
        back_rows = json.loads(tasks_back.read_text(encoding="utf-8"))
        for row in back_rows:
            if row.get("taskmaster_id") == 102:
                row["status"] = "completed"
        _put_json(root, ".taskmaster/tasks/tasks_back.json", back_rows)

        before_bytes = tasks_json.read_bytes()
        patch_file = root / "logs" / "ci" / "patch.json"
        _put_json(
            root,
            "logs/ci/patch.json",
            {
                "schema_version": 1,
                "contract_type": "chapter7-task-status-patch",
                "status": "ok",
                "operation_count": 2,
                "operations": [
                    {
                        "op": "replace-task-status",
                        "path": str(tasks_json.resolve()).replace("\\", "/"),
                        "view": "tasks_json",
                        "task_id": 101,
                        "task_ref": "T101",
                        "from_status": "done",
                        "to_status": "pending",
                    },
                    {
                        "op": "replace-task-status",
                        "path": str(tasks_json.resolve()).replace("\\", "/"),
                        "view": "tasks_json",
                        "task_id": 102,
                        "task_ref": "T102",
                        "from_status": "in-progress",
                        "to_status": "pending",
                    },
                ],
            },
        )
        for dry_run in (True, False):
            rc, payload = status_patch.apply_patch_contract(
                patch_path=patch_file, dry_run=dry_run, repo_root=root
            )
            self.assertEqual(rc, 1)
            self.assertEqual(payload["status"], "fail")
            for op_res in payload["results"]:
                self.assertFalse(op_res["applied"])
                self.assertEqual(op_res["reason_code"], "conflict")
                self.assertEqual(op_res["error"], "cannot_clear_mature_done_status")
                self.assertTrue(op_res["done_status_preserved"])
        self.assertEqual(tasks_json.read_bytes(), before_bytes)

    def test_ac4_p03_run_chapter7_ui_wiring_multislice_no_whole_game_fallback_and_manifest(self) -> None:
        root = self._clone_flow()
        before_tasks = (root / ".taskmaster" / "tasks" / "tasks.json").read_bytes()
        # Even when docs/gdd/ui-gdd-flow.md already exists AND --write-doc is passed, B-route --slice MUST NOT fall through!
        _put(root, "docs/gdd/ui-gdd-flow.md", "# Existing UI GDD\n")
        out_slice = root / "logs" / "ci" / "slice-wiring-summary.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ch7_wiring.main(
                [
                    "--repo-root",
                    str(root),
                    "--slice",
                    "reward_flow",
                    "--flow-id",
                    "flow-reward-select",
                    "--write-doc",
                    "--out-json",
                    str(out_slice),
                ]
            )
        self.assertEqual(rc, 0)
        summary = json.loads(out_slice.read_text(encoding="utf-8"))
        self.assertTrue(summary["b_route_slice_only"])
        self.assertEqual(summary["global_knowledge_refresh"], "not_performed")
        self.assertFalse(summary["task_triplet_written"])
        self.assertEqual(summary["b_route_chapter7_slice"]["target_task_ids"], [101, 102, 103])
        self.assertTrue(Path(summary["artifact_manifest"]).is_file())
        manifest_val = json.loads(Path(summary["artifact_manifest_validation"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest_val["status"], "ok")
        self.assertNotIn("collect", [s["name"] for s in summary["steps"]])

        # Multi-slice with a failing second slice MUST NOT drop norm_slices[1:] and MUST return non-zero!
        out_multi = root / "logs" / "ci" / "multi-slice-summary.json"
        buf_m = io.StringIO()
        with redirect_stdout(buf_m):
            rc_m = ch7_wiring.main(
                [
                    "--repo-root",
                    str(root),
                    "--chapter7-profile-path",
                    "docs/workflows/chapter7-single-profile.json",
                    "--slice",
                    "reward_flow",
                    "--slice",
                    "nonexistent_slice",
                    "--out-json",
                    str(out_multi),
                ]
            )
        self.assertEqual(rc_m, 1)
        summary_m = json.loads(out_multi.read_text(encoding="utf-8"))
        self.assertEqual(summary_m["status"], "fail")
        self.assertEqual(len(summary_m["b_route_chapter7_slice"]["per_slice_results"]), 2)

        # --create-tasks on B-route repo returns rc=2 governed delta candidate with "operations" and validates manifest!
        out_create = root / "logs" / "ci" / "slice-create-summary.json"
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = ch7_wiring.main(
                [
                    "--repo-root",
                    str(root),
                    "--chapter7-profile-path",
                    "docs/workflows/chapter7-single-profile.json",
                    "--slice",
                    "reward_flow",
                    "--create-tasks",
                    "--out-json",
                    str(out_create),
                ]
            )
        self.assertEqual(rc2, 2)
        summary2 = json.loads(out_create.read_text(encoding="utf-8"))
        self.assertEqual(summary2["status"], "blocked")
        self.assertFalse(summary2["task_triplet_written"])
        delta_doc = json.loads(Path(summary2["governed_task_delta_candidate"]).read_text(encoding="utf-8"))
        self.assertIn("operations", delta_doc)
        self.assertNotIn("intents", delta_doc)
        self.assertEqual((root / ".taskmaster" / "tasks" / "tasks.json").read_bytes(), before_tasks)

    # ------------------------------------------------------------------
    # AC-5: HANDOFF_NOKCP + CLI / dev_cli / builder wiring + Exclusive write_report
    # ------------------------------------------------------------------
    def test_ac5_handoff_traceability_exclusive_report_write_and_dev_cli_wiring(self) -> None:
        root = self._clone_flow()
        ev_rel = "logs/ci/ch6-ui-evidence.json"
        _put_json(root, ev_rel, {"evidence": [self._valid_evidence_record()]})
        before = _tree_snapshot(root)

        # 1. Zero-write CLI run via dev_cli.main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dev_cli.main(
                [
                    "b-route-chapter7-slice",
                    "--root",
                    str(root),
                    "--flow-id",
                    "flow-reward-select",
                    "--slice",
                    "reward_flow",
                    "--ui-evidence",
                    ev_rel,
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(_tree_snapshot(root), before)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["schema_version"], ch7_slice.SCHEMA)
        self.assertEqual(payload["handoff"]["schema_version"], ch7_slice.HANDOFF_SCHEMA)
        self.assertIsNone(payload["report_path"])
        self.assertTrue(payload["downstream_flow_obligations_preserved"])
        self.assertTrue(payload["cumulative_milestone_obligations_preserved"])
        self.assertFalse(payload["flow_completed"])
        self.assertFalse(payload["cumulative_milestone_completed"])
        self.assertEqual(payload["global_knowledge_refresh"], "not_performed")
        self._assert_traceable_items(payload["verified_items"])
        self._assert_traceable_items(payload["pending_items"])
        self._assert_traceable_items(payload["manual_items"])
        self._assert_traceable_items(payload["blocked_items"])

        # 2. Explicit --report sets report_path BEFORE writing; second write to same path fails with CONFLICT!
        report_rel = "logs/ci/2026-11-24/slice-report.json"
        buf_rep = io.StringIO()
        with redirect_stdout(buf_rep):
            rc_rep = slice_cli.main(
                [
                    "--root",
                    str(root),
                    "--profile",
                    "docs/workflows/chapter7-single-profile.json",
                    "--slice",
                    "reward_flow",
                    "--ui-evidence",
                    ev_rel,
                    "--report",
                    report_rel,
                ]
            )
        self.assertEqual(rc_rep, 0)
        on_disk = json.loads((root / report_rel).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["report_path"], report_rel)
        self.assertFalse(on_disk["runtime_verified"])
        self.assertFalse(on_disk["default_b_enabled"])

        # Second --report to existing file MUST fail closed (rc=2, handoff present in blocked payload)!
        buf_dup = io.StringIO()
        with redirect_stdout(buf_dup):
            rc_dup = slice_cli.main(
                [
                    "--root",
                    str(root),
                    "--flow-id",
                    "flow-reward-select",
                    "--slice",
                    "reward_flow",
                    "--ui-evidence",
                    ev_rel,
                    "--report",
                    report_rel,
                ]
            )
        self.assertEqual(rc_dup, 2)
        dup_payload = json.loads(buf_dup.getvalue())
        self.assertEqual(dup_payload["reason_code"], codec.ReasonCode.CONFLICT.value)
        self.assertEqual(dup_payload["handoff"]["schema_version"], ch7_slice.HANDOFF_SCHEMA)

        # 3. Builder rejects --write/--apply and forwards flags accurately.
        ns = types.SimpleNamespace(
            root=".",
            flow_id="flow-reward-select",
            slice="reward_flow",
            task_id=["101"],
            profile=None,
            evidence_dir=None,
            ui_evidence=ev_rel,
            gap_input=None,
            operation=None,
            report=report_rel,
        )
        cmd = dev_cli_builders.build_b_route_chapter7_slice_cmd(ns)
        self.assertIn("--flow-id", cmd)
        self.assertIn("--slice", cmd)
        self.assertIn("--report", cmd)
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_chapter7_slice_cmd(types.SimpleNamespace(root=".", flow_id="f", write=True))


if __name__ == "__main__":
    unittest.main()
