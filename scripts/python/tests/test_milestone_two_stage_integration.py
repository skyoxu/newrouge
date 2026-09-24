"""T26: real workflow stages around a deterministic subprocess runtime fixture.

The only substituted boundary is the engine test adapter. Its child executes
assertions and emits a report; production snapshot, manifest, report parsing,
readiness and evidence consumers run normally. This is not Godot game evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts/python"))
sys.path.insert(0, str(REPO / "scripts/sc"))
import build_source_ledger as sources
import compile_task_triplet as compiler
import build_taskmaster_tasks as exporter
import chapter5_semantic_reconciliation as chapter5
import milestone_incremental_handoff as handoffs
import update_mvg_baseline as baseline
import run_mvg_acceptance as mvg
from _mvg_execution import run_child, read_test_evidence
from _overlay_generator_markdown_patch import apply_scaffold_update_to_existing_markdown


def save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


CHILD = '''import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
rules = json.loads(Path("rules.json").read_text())
test_id, selector, report = sys.argv[1:]
failure = ""
try:
    if test_id == "old-reward":
        assert rules["reward"] == 10, "old combat reward changed"
        assert rules["return_map"], "old return path broken"
    else:
        assert rules["shop"] and rules["return_map"], "shop return path missing"
except AssertionError as error:
    failure = str(error)
doc = ET.Element("TestRun")
result = ET.SubElement(doc, "UnitTestResult", testName=selector + ".Behavior", outcome="Failed" if failure else "Passed")
if failure:
    ET.SubElement(result, "Message").text = failure
ET.ElementTree(doc).write(report, encoding="utf-8")
raise SystemExit(1 if failure else 0)
'''


def execute_fixture(root, test, out, godot_bin, deadline, env=None, *, prewarm=True):
    out.mkdir(parents=True)
    command = [sys.executable, str(root / "fixture_test.py"), test["id"], test["selector"], str(out / "results.trx")]
    rc = run_child(command, root, out / "console.log", deadline - time.monotonic(), env)
    evidence = read_test_evidence(out, "dotnet", test["selector"], test["min_tests"])
    return {"id": test["id"], "status": "passed" if rc == 0 and evidence["passed"] else "failed",
            "exit_code": rc, "command": command, "evidence": evidence}


class MilestoneTwoStageIntegrationTests(unittest.TestCase):
    def test_two_stage_increment_preserves_baseline_and_blocks_old_regression_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()

            def commit(message):
                git("add", ".")
                git("commit", "-qm", message)

            def export(ids):
                with patch.object(exporter, "ROOT", root), patch.object(exporter, "TASKMASTER_TASKS_FILE", root / ".taskmaster/tasks/tasks.json"):
                    exporter.build_taskmaster_tasks(SimpleNamespace(
                        tasks_files=[".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"],
                        ids=ids, ids_file="", tag="master", allow_legacy_t2_default=False))

            def run_manifest():
                parser = argparse.ArgumentParser()
                mvg.register_arguments(parser)
                args = parser.parse_args(["--manifest", "docs/testing/mvg/current.json", "--mode", "run", "--snapshot", "commit"])
                before = set((root / "logs/ci/mvg-acceptance").glob("*/summary.json"))
                with patch.object(mvg, "execute_test", side_effect=execute_fixture):
                    rc = mvg.run(args, root)
                created = set((root / "logs/ci/mvg-acceptance").glob("*/summary.json")) - before
                self.assertEqual(1, len(created))
                path = created.pop()
                return rc, path, read(path)

            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.com")
            (root / ".gitignore").write_text("logs/\n__pycache__/\n", encoding="utf-8")
            gdd = root / "docs/gdd/combat.md"
            gdd.parent.mkdir(parents=True)
            gdd.write_text("# Combat\n\nCombat rewards return to map.\n", encoding="utf-8")
            save(root / "docs/workflows/chapter3-source-set.json", {
                "schema_version": "chapter3.source-set.v1", "active_patterns": ["docs/gdd/**/*.md"],
                "active_sources": ["docs/gdd/combat.md"], "retirements": []})
            source_args = ["--repo-root", str(root), "--mode", "add", "--write-source-set"]
            self.assertEqual(0, sources.main(source_args))
            initial_ledger = read(root / chapter5.DEFAULT_SOURCE_LEDGER)
            overlay = root / "docs/architecture/overlays/PRD/08/reward.md"
            overlay.parent.mkdir(parents=True)
            overlay.write_text("# Rewards\n\n## Rules\n\nKeep combat rewards unchanged.\n\n- Return to map\n", encoding="utf-8")
            unrelated = overlay.parent / "unrelated.md"
            unrelated.write_bytes(b"# Unrelated\n\nKeep exactly.\n")
            unrelated_bytes = unrelated.read_bytes()
            contract = root / "Game.Core/Contracts/RewardEvents.cs"
            contract.parent.mkdir(parents=True)
            contract.write_text('public static class RewardEvents { public const string Claimed = "core.reward.claimed"; }\n', encoding="utf-8")
            for name in ("RewardTests", "ShopTests"):
                path = root / f"Game.Core.Tests/{name}.cs"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("// Runtime selectors for the deterministic harness fixture.\n", encoding="utf-8")
            old = {"id": "GM-1", "taskmaster_id": 1, "title": "Combat reward", "status": "done",
                   "semantic_refs": ["FR-COMBAT"], "acceptance": ["Combat rewards return to map. Refs: Game.Core.Tests/RewardTests.cs"],
                   "test_refs": ["Game.Core.Tests/RewardTests.cs"], "contractRefs": ["core.reward.claimed"],
                   "overlay_refs": [overlay.relative_to(root).as_posix()], "depends_on": []}
            save(root / ".taskmaster/tasks/tasks_gameplay.json", [old])
            save(root / ".taskmaster/tasks/tasks_back.json", [{**old, "id": "NG-1", "status": "pending"}])
            protected = [{"id": 1, "status": "done", "title": "Combat reward", "subtasks": [{"id": 1, "status": "done"}], "future_extension": {"retain": True}}]
            save(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": protected}})
            save(root / "rules.json", {"reward": 10, "return_map": True, "shop": False})
            (root / "fixture_test.py").write_text(CHILD, encoding="utf-8")

            def flow(name, test_id, task):
                return {"id": name, "outcome": "Rewards return to map", "task_ids": [task],
                        "source_paths": ["rules.json"], "test_ids": [test_id], "handoffs": [{
                            "producer_task": task, "consumer_task": task, "owner_task": task,
                            "contract_ref": "Game.Core/Contracts/RewardEvents.cs", "behavior": "Return to map", "test_ids": [test_id]}]}

            def test_spec(test_id, name, state="implemented"):
                return {"id": test_id, "kind": "dotnet", "state": state, "evidence_level": "domain-integration",
                        "path": f"Game.Core.Tests/{name}.cs", "selector": f"Game.Core.Tests.{name}", "min_tests": 1}

            manifest_path = root / "docs/testing/mvg/current.json"
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture", "coverage": {
                "mode": "pilot", "scope_id": "two-stage-fixture", "required_flow_ids": ["combat-reward-map"],
                "blocking_task_ids": [], "excluded_claims": ["Harness fixture only; not Godot gameplay or human acceptance."]},
                "flows": [flow("combat-reward-map", "old-reward", 1)], "tests": [test_spec("old-reward", "RewardTests")]}
            save(manifest_path, manifest)
            commit("stage one baseline")
            self.assertEqual(0, run_manifest()[0])

            # Stage two changes the shared contract, reuses the old task and adds one owner.
            (gdd.parent / "shop.md").write_text("# Shop\n\nShop rewards return to map.\n", encoding="utf-8")
            self.assertEqual(0, sources.main(source_args))
            ledger = read(root / chapter5.DEFAULT_SOURCE_LEDGER)
            self.assertTrue(set(initial_ledger["delta"]["added"]) <= set(ledger["delta"]["unchanged"]))
            candidate = {"id": "GM-2", "owner": "gameplay", "title": "Shop reward", "semantic_refs": ["FR-SHOP"],
                         "acceptance": ["Shop rewards return to map. Refs: Game.Core.Tests/ShopTests.cs"],
                         "test_refs": ["Game.Core.Tests/ShopTests.cs"], "contractRefs": ["core.reward.claimed"],
                         "overlay_refs": [overlay.relative_to(root).as_posix()], "depends_on": ["GM-1"], "change_action": "create"}
            save(root / "logs/candidates.json", {"candidates": [{"id": "GM-1", "owner": "gameplay", "change_action": "reuse"}, candidate]})
            save(root / "logs/coverage.json", {"status": "ok"})
            args = ["compile_task_triplet.py", "--repo-root", str(root), "--candidates", "logs/candidates.json", "--coverage", "logs/coverage.json"]
            with patch.object(sys, "argv", args):
                self.assertEqual(0, compiler.main())
            with patch.object(sys, "argv", args + ["--write"]):
                self.assertEqual(0, compiler.main())
            export(["NG-1", "GM-1", "GM-2"])
            master = read(root / ".taskmaster/tasks/tasks.json")["master"]["tasks"]
            self.assertEqual("done", master[0]["status"])
            self.assertEqual(protected[0]["subtasks"], master[0]["subtasks"])
            self.assertEqual(protected[0]["future_extension"], master[0]["future_extension"])
            self.assertEqual([1, 2], [row["id"] for row in master])
            patched = apply_scaffold_update_to_existing_markdown(current_markdown=overlay.read_text(), scaffold_update={
                "strict_incremental_patch": True, "sections": [{"heading": "Rules", "bullets": ["Shop uses the same map return"]}]})
            overlay.write_text(patched, encoding="utf-8")
            self.assertIn("Keep combat rewards unchanged.", patched)
            self.assertEqual(unrelated_bytes, unrelated.read_bytes())
            contract.write_text(contract.read_text() + "// Shop reuses the same reward event without changing combat semantics.\n", encoding="utf-8")

            self._prepare_chapter5(root, ledger)
            readiness = chapter5.readiness_path_for_task(root, "2")
            plan_path = root / "logs/milestone-plan.json"
            save(plan_path, {"schema_version": handoffs.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": ledger["source_revision"]}, "changes": [{
                    "change_id": "shop-extension", "action": "extend", "target_task_id": "1", "owner_task_id": "2",
                    "reason": "Shop reuses the reward handoff and must preserve the combat return path.",
                    "requirement_ids": ["FR-COMBAT", "FR-SHOP"],
                    "impact": {"tasks": ["1", "2"], "contracts": ["core.reward.claimed"]},
                    "verification": {"required_regressions": ["old-reward", "new-shop"], "planned_tests": ["new-shop"]}}]})
            handoff = handoffs.build_task_handoff(root, plan_path=plan_path, task_id="2", readiness_path=readiness)
            handoff_path = root / "logs/handoff.json"
            save(handoff_path, handoff)
            self.assertTrue(handoffs.validate_task_handoff(root, handoff_path, "2")[0])
            self.assertFalse(handoffs.validate_milestone_regressions(root, handoff, None)[0])

            delta = {"schema_version": baseline.DELTA_SCHEMA, "expected_manifest_sha256": baseline._canonical_sha(manifest),
                     "change_plan_sha256": handoffs._file_sha(plan_path),
                     "flow_operations": [{"id": "shop-reward-map", "action": "add", "reason": "Reviewed new handoff", "value": flow("shop-reward-map", "new-shop", 2)}],
                     "test_operations": [{"id": "new-shop", "action": "add", "reason": "New combination", "value": test_spec("new-shop", "ShopTests", "planned")}],
                     "coverage_updates": {"mode": "critical", "required_flow_ids": ["combat-reward-map", "shop-reward-map"], "blocking_task_ids": [2]}}
            cumulative = baseline.apply_delta(manifest, delta)
            save(manifest_path, cumulative)
            commit("stage two planned")
            self.assertNotEqual(0, run_manifest()[0])

            # Explicit lifecycle completion belongs to implementation, never to export.
            for row in master:
                if row["id"] == 2:
                    row["status"] = "done"
            save(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": master}})
            cumulative["coverage"]["blocking_task_ids"] = []
            cumulative["tests"][1]["state"] = "implemented"
            cumulative["tests"].reverse()  # New test passes before the old regression fails.
            save(manifest_path, cumulative)
            save(root / "rules.json", {"reward": 11, "return_map": True, "shop": True})
            commit("stage two with deliberate old regression")
            rc, failed_path, failed = run_manifest()
            self.assertNotEqual(0, rc)
            self.assertEqual([("new-shop", "passed"), ("old-reward", "failed")], [(step["id"], step["status"]) for step in failed["steps"]])
            self.assertFalse(handoffs.validate_milestone_regressions(root, handoff, failed_path)[0])
            save(root / "rules.json", {"reward": 10, "return_map": True, "shop": True})
            commit("stage two corrected")
            rc, passed_path, passed = run_manifest()
            self.assertEqual(0, rc)
            self.assertEqual({"old-reward", "new-shop"}, {step["id"] for step in passed["steps"]})
            self.assertEqual((True, "ok"), handoffs.validate_milestone_regressions(root, handoff, passed_path))

            # Replaying the already-applied preview must not add or mutate tasks.
            triplet = [root / ".taskmaster/tasks" / name for name in ("tasks.json", "tasks_back.json", "tasks_gameplay.json")]
            previous_bytes = {path: path.read_bytes() for path in triplet}
            with patch.object(sys, "argv", args + ["--write"]), self.assertRaises(SystemExit):
                compiler.main()
            self.assertEqual(previous_bytes, {path: path.read_bytes() for path in triplet})
            self.assertEqual(unrelated_bytes, unrelated.read_bytes())
            self.assertEqual("", git("status", "--porcelain"))

    def _prepare_chapter5(self, root, ledger):
        manifest_path = root / chapter5.DEFAULT_SOURCE_MANIFEST
        ledger_path = root / chapter5.DEFAULT_SOURCE_LEDGER
        candidate_path = root / chapter5.DEFAULT_EXTRACTION_CANDIDATE
        snapshot_path = root / chapter5.DEFAULT_EXTRACTION_SNAPSHOT
        chapter5.prepare_extraction_b(root, manifest_path=manifest_path, ledger_path=ledger_path,
                                     candidate_path=candidate_path, snapshot_path=snapshot_path)
        candidate = read(candidate_path)
        requirements = []
        for row in candidate["block_results"]:
            text = row["raw_source"]
            rid = "FR-COMBAT" if "Combat rewards" in text else "FR-SHOP" if "Shop rewards" in text else ""
            row.update(review_status="reviewed", delivery_potential=bool(rid), disposition="" if rid else "context", obligations=[])
            if rid:
                statement = "Combat rewards return to map." if rid == "FR-COMBAT" else "Shop rewards return to map."
                row["obligations"] = [{"statement": statement, "kind": "functional", "priority": "P1", "delivery_relevant": True, "source_block_ids": [row["block_id"]]}]
                requirements.append({"requirement_id": rid, "kind": "functional", "statement": statement,
                    "source_block_ids": [row["block_id"]], "delivery_relevant": True, "status": "active", "priority": "P1", "non_task_sinks": []})
        save(candidate_path, candidate)
        snapshot = chapter5.compile_extraction_b(root, manifest_path=manifest_path, ledger_path=ledger_path,
                                                 candidate_path=candidate_path, snapshot_path=snapshot_path)
        self.assertEqual("complete", snapshot["status"])
        semantics_path = root / chapter5.DEFAULT_CH3_SEMANTICS
        save(semantics_path, {"schema_version": "newrouge.semantic-requirements.v1", "source_revision": ledger["source_revision"],
                             "source_manifest_sha256": ledger["source_manifest_sha256"], "source_accounting": [], "requirements": requirements})
        decisions_path = root / "logs/chapter5-decisions.json"
        save(decisions_path, {"allow_concerns": True, "match_decisions": [{
            "obligation_id": row["obligation_id"], "chapter3_requirement_ids": ["FR-COMBAT" if "Combat" in row["statement"] else "FR-SHOP"],
            "status": "equivalent", "rationale": "Explicit fixture review confirms the same behavior."} for row in snapshot["semantic_inventory"]],
            "authority_decisions": [{"authority_ref": "core.reward.claimed", "status": "compatible", "rationale": "Both producers retain the map return contract."}],
            "dependency_decisions": [{"dependency_id": "GM-1", "action": "keep", "relation": "contract",
                "dependency_reason": "Shop consumes the existing reward-to-map contract.", "dependency_evidence": ["core.reward.claimed"]}],
            "acceptance_links": [{"acceptance_index": 1, "requirement_ids": ["FR-SHOP"], "test_refs": ["Game.Core.Tests/ShopTests.cs"], "authority_refs": ["core.reward.claimed"]}]})
        _, ready = chapter5.reconcile(root, task_id="2", snapshot_path=snapshot_path, semantics_path=semantics_path,
            decisions_path=decisions_path, out_path=chapter5.reconciliation_path_for_task(root, "2"),
            readiness_path=chapter5.readiness_path_for_task(root, "2"))
        self.assertTrue(ready["closure_allowed"], ready)
        ok, _, reason = chapter5.load_task_readiness(root, "2")
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
