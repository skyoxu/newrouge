"""Deterministic tests for run_chapter7_backlog_gap.py (legacy, --slice/--flow-id, and B-route UI reuse)."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

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

import _b_route_codec as codec
import _b_route_input_set as input_set
import dev_cli_builders
import run_chapter7_backlog_gap as backlog_gap

from test_b_route_chapter5_readiness import _build_b_route_base_repo, _put, _put_json
from test_b_route_chapter7_slice import (
    _PROFILE_JSON,
    _VALID_ADAPTER_CS,
    _VALID_CS_CORE_TEST,
    _VALID_GDUNIT_TEST,
    _VALID_TSCN,
    _reconcile_slice_task,
)


class Chapter7BacklogGapTests(unittest.TestCase):
    """Covers legacy backlog-gap analysis, --slice/--flow-id filtering, stopword/coverage reuse, and fail-closed B-route."""

    _tmp_base: Path
    _b_tpl: Path
    _t101_iset: str
    _gd_sha: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_base = Path(tempfile.mkdtemp(prefix="ch7_backlog_gap_"))
        cls._b_tpl = cls._tmp_base / "b_tpl"
        cls._b_tpl.mkdir(parents=True, exist_ok=True)
        _build_b_route_base_repo(
            cls._b_tpl,
            mode="flow",
            binding_stage="5",
            include_planned=False,
            task101_status="done",
            task102_status="in-progress",
            task103_status="pending",
        )
        _put(cls._b_tpl, "Game.Core.Tests/Reward/RewardFlowTests.cs", _VALID_CS_CORE_TEST)
        _put(cls._b_tpl, "Game.Godot/Scenes/UI/RewardScene.tscn", _VALID_TSCN)
        _put(cls._b_tpl, "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs", _VALID_ADAPTER_CS)
        gd_raw = _put(cls._b_tpl, "Tests.Godot/tests/UI/test_reward_scene_input.gd", _VALID_GDUNIT_TEST)
        cls._gd_sha = codec.raw_digest(gd_raw)
        _put_json(cls._b_tpl, "docs/workflows/chapter7-profile.json", _PROFILE_JSON)
        for tid in (101, 102, 103):
            _reconcile_slice_task(cls._b_tpl, task_id=tid, mode="flow", include_planned=False)
        cls._t101_iset = str(input_set.resolve_input_set(cls._b_tpl, 101)["input_set_digest"])

        _put(
            cls._b_tpl,
            "docs/design/gdd.md",
            (
                "# GDD\n\n"
                "Current build still needs reward confirm panel feedback readout for players.\n"
                "Current build still needs unrelated leaderboard achievements dialog for players.\n"
            ),
        )
        _put(
            cls._b_tpl,
            "docs/design/epics.md",
            (
                "## Epic 1: Reward Flow\n"
                "- As a player, I can confirm a reward offer on the reward screen.\n"
                "## Epic 2: Achievements\n"
                "- As a player, I can browse global achievements leaderboard panel.\n"
            ),
        )
        _put(
            cls._b_tpl,
            "logs/analysis/dup.md",
            "# Dup Audit\n\n## High-overlap clusters\n### Cluster R: Reward screen wiring\n",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp_base, ignore_errors=True)

    def _valid_ev_doc(self) -> dict:
        return {
            "evidence": [
                {
                    "task_id": 101,
                    "flow_id": "flow-reward-select",
                    "binding_ref": "docs/planning/b-route/bindings/plan-reward/1.json",
                    "obligation_id": "OBL-REWARD-CONFIRM-FEEDBACK",
                    "requirement_ids": ["REQ-REWARD-1"],
                    "evidence_kind": "gdunit_engine_input",
                    "input_set_digest": self._t101_iset,
                    "test_path": "Tests.Godot/tests/UI/test_reward_scene_input.gd",
                    "test_sha256": self._gd_sha,
                    "tests": 2,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                    "state": "passed",
                    "real_engine_input": True,
                }
            ]
        }

    def test_slice_filter_and_b_route_verified_ui_reuse_prevent_synonymous_tasks(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="gap_case_", dir=str(self._tmp_base)))
        shutil.copytree(self._b_tpl, root, dirs_exist_ok=True)
        ev_rel = "logs/ci/ch6-reward-ui-evidence.json"
        _put_json(root, ev_rel, self._valid_ev_doc())
        out_json = root / "logs" / "ci" / "gap-summary.json"
        rc = backlog_gap.main(
            [
                "--repo-root",
                str(root),
                "--design-doc-path",
                "docs/design/gdd.md",
                "--epics-doc-path",
                "docs/design/epics.md",
                "--duplicate-audit-path",
                "logs/analysis/dup.md",
                "--slice",
                "reward_flow",
                "--flow-id",
                "flow-reward-select",
                "--ui-evidence",
                ev_rel,
                "--out-json",
                str(out_json),
            ]
        )
        self.assertEqual(rc, 0)
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual(payload["input_contract"]["target_slices"], ["reward_flow"])
        self.assertEqual(payload["input_contract"]["target_flow_id"], "flow-reward-select")
        self.assertEqual(payload["story_count"], 1)
        self.assertEqual(payload["design_gap_signal_count"], 1)
        self.assertEqual(payload["candidate_task_gaps"], [])
        self.assertFalse(payload["recommendation"]["should_create_tasks"])
        self.assertIn("b_route_reuse_summary", payload)
        self.assertTrue(payload["b_route_reuse_summary"]["slice_ok"])
        self.assertEqual(payload["b_route_reuse_summary"]["reused_obligation_count"], 1)
        self.assertEqual(payload["b_route_reuse_summary"]["global_knowledge_refresh"], "not_performed")

    def test_stopword_filtering_and_failed_slice_do_not_falsely_suppress_gaps(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="gap_strict_", dir=str(self._tmp_base)))
        shutil.copytree(self._b_tpl, root, dirs_exist_ok=True)
        ev_rel = "logs/ci/ch6-reward-ui-evidence.json"
        ev_doc = self._valid_ev_doc()
        ev_doc["evidence"][0]["obligation_id"] = "OBL-CONFIRM-ANCHOR-99"
        _put_json(root, ev_rel, ev_doc)
        # Genuine uncovered gap sharing only generic UI/scene words ("scene", "panel", "feedback", "input") MUST NOT be suppressed!
        anchor_sig = (
            "Current build still needs OBL-CONFIRM-ANCHOR-99 confirmbutton statuslabel modal tooltip readout."
        )
        unrelated_sig = (
            "Current build still needs audio equalizer mixer scene panel input feedback statuslabel readout."
        )
        _put(
            root,
            "docs/design/gdd.md",
            f"# GDD\n\n{unrelated_sig}\n{anchor_sig}\n",
        )
        _put(
            root,
            "docs/design/epics.md",
            "## Epic 1: Reward Flow\n- As a player, I can tune audio equalizer mixer on the reward screen.\n",
        )
        res = backlog_gap.analyze(
            repo_root=root,
            tasks_json_path=Path(".taskmaster/tasks/tasks.json"),
            tasks_back_path=Path(".taskmaster/tasks/tasks_back.json"),
            tasks_gameplay_path=Path(".taskmaster/tasks/tasks_gameplay.json"),
            design_doc_path=Path("docs/design/gdd.md"),
            epics_doc_path=Path("docs/design/epics.md"),
            duplicate_audit_path=Path("logs/analysis/dup.md"),
            delivery_profile="fast-ship",
            slices=["reward_flow"],
            flow_id="flow-reward-select",
            ui_evidence=ev_rel,
        )
        by_sig = {m["signal"]: m["bucket"] for m in res["design_gap_mappings"]}
        # Exact obligation anchor matches verified B-route UI; unrelated audio equalizer mixer remains uncovered!
        self.assertEqual(by_sig[anchor_sig], "covered-by-verified-b-route-ui")
        self.assertEqual(by_sig[unrelated_sig], "not-clearly-covered")

        # When slice evaluation fails (broken adapter), reuse MUST NOT suppress even exact-anchor gaps!
        _put(
            root,
            "Game.Godot/Scripts/Reward/RewardScreenAdapter.cs",
            "using Godot; public partial class RewardScreenAdapter : Control { public override void _Ready() { GetNode<Button>(\"Missing\"); } }\n",
        )
        res_bad = backlog_gap.analyze(
            repo_root=root,
            tasks_json_path=Path(".taskmaster/tasks/tasks.json"),
            tasks_back_path=Path(".taskmaster/tasks/tasks_back.json"),
            tasks_gameplay_path=Path(".taskmaster/tasks/tasks_gameplay.json"),
            design_doc_path=Path("docs/design/gdd.md"),
            epics_doc_path=Path("docs/design/epics.md"),
            duplicate_audit_path=Path("logs/analysis/dup.md"),
            delivery_profile="fast-ship",
            slices=["reward_flow"],
            flow_id="flow-reward-select",
            ui_evidence=ev_rel,
        )
        self.assertFalse(res_bad["b_route_reuse_summary"]["slice_ok"])
        self.assertEqual(res_bad["b_route_reuse_summary"]["reused_obligation_count"], 0)
        by_sig_bad = {m["signal"]: m["bucket"] for m in res_bad["design_gap_mappings"]}
        self.assertEqual(by_sig_bad[anchor_sig], "not-clearly-covered")

    def test_builder_forwards_slice_and_flow_id(self) -> None:
        ns = types.SimpleNamespace(
            repo_root=".",
            delivery_profile="fast-ship",
            tasks_json_path="",
            tasks_back_path="",
            tasks_gameplay_path="",
            design_doc_path="docs/design/gdd.md",
            epics_doc_path="docs/design/epics.md",
            duplicate_audit_path="logs/analysis/dup.md",
            slice=["reward_flow"],
            flow_id="flow-reward-select",
            chapter7_profile_path="docs/workflows/chapter7-profile.json",
            ui_evidence="logs/ci/ev.json",
            out_json="",
            self_check=False,
        )
        cmd = dev_cli_builders.build_run_chapter7_backlog_gap_cmd(ns)
        self.assertIn("--slice", cmd)
        self.assertIn("reward_flow", cmd)
        self.assertIn("--flow-id", cmd)
        self.assertIn("flow-reward-select", cmd)


if __name__ == "__main__":
    unittest.main()
