#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "scripts" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Chapter3TaskGenerationTests(unittest.TestCase):
    def test_requirement_extraction_should_skip_reference_only_blocks(self) -> None:
        mod = _load_module("extract_requirement_anchors_for_noise_test", "scripts/python/extract_requirement_anchors.py")

        self.assertFalse(mod.is_requirement_like("- docs/gdd/ui-gdd-flow.md ADR-Refs:"))
        self.assertFalse(mod.is_requirement_like("- Game.Core.Tests/Tasks/Task1WindowsPlatformGateTests.cs"))
        self.assertFalse(mod.is_requirement_like("- T42 `Independent performance gates workflow`"))
        self.assertTrue(mod.is_requirement_like("- Startup smoke must verify all required autoloads load without startup errors."))

    def test_task_intents_should_split_large_source_groups_by_topic_and_size(self) -> None:
        mod = _load_module("normalize_task_intents_for_split_test", "scripts/python/normalize_task_intents.py")
        anchors = []
        for idx in range(1, 13):
            anchors.append(
                {
                    "requirement_id": f"REQ-COMBAT-{idx:04d}",
                    "source_path": "docs/gdd/ui-gdd-flow.md",
                    "line": idx,
                    "kind": "gdd",
                    "priority": "P1",
                    "text": f"Combat enemy attack damage targeting requirement {idx} must be implemented.",
                    "refs": [],
                }
            )
        for idx in range(1, 5):
            anchors.append(
                {
                    "requirement_id": f"REQ-UI-{idx:04d}",
                    "source_path": "docs/gdd/ui-gdd-flow.md",
                    "line": 100 + idx,
                    "kind": "gdd",
                    "priority": "P2",
                    "text": f"UI HUD surface display requirement {idx} should be implemented.",
                    "refs": [],
                }
            )

        result = mod.build_intents(
            {
                "schema": "task-generation.requirements-index.v1",
                "anchors": anchors,
            },
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=5,
            split_profile="compact",
        )

        self.assertEqual("task-generation.task-intents.v1", result["schema"])
        self.assertEqual(16, result["source_anchor_count"])
        self.assertEqual(4, result["intent_count"])
        self.assertEqual(
            sorted(anchor["requirement_id"] for anchor in anchors),
            sorted(rid for intent in result["intents"] for rid in intent["requirement_ids"]),
        )
        self.assertLessEqual(max(intent["covered_anchor_count"] for intent in result["intents"]), 5)
        self.assertIn("combat-loop", {intent["topic"] for intent in result["intents"]})
        self.assertIn("ui-hud", {intent["topic"] for intent in result["intents"]})
        self.assertTrue(any(intent["title"].startswith("Implement ") for intent in result["intents"]))
        self.assertTrue(any(intent["title"].startswith("Create ") for intent in result["intents"]))
        self.assertTrue(any("Red:" in " ".join(intent["test_strategy"]) for intent in result["intents"]))
        self.assertTrue(any(intent["depends_on"] for intent in result["intents"]))

    def test_task_intent_titles_should_deprioritize_traceability_noise(self) -> None:
        mod = _load_module("normalize_task_intents_for_title_noise_test", "scripts/python/normalize_task_intents.py")
        result = mod.build_intents(
            {
                "schema": "task-generation.requirements-index.v1",
                "anchors": [
                    {
                        "requirement_id": "REQ-NOISE-0001",
                        "source_path": "docs/gdd/a.md",
                        "line": 1,
                        "kind": "gdd",
                        "priority": "P2",
                        "text": "- ADR-0033 Test-Refs: Default save slot must gate Continue by valid metadata.",
                        "refs": [],
                    },
                    {
                        "requirement_id": "REQ-NOISE-0002",
                        "source_path": "docs/gdd/a.md",
                        "line": 2,
                        "kind": "gdd",
                        "priority": "P2",
                        "text": "- Default save slot must gate Continue by valid metadata.",
                        "refs": [],
                    },
                ],
            },
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
        )

        title = result["intents"][0]["title"].lower()
        self.assertIn("save", title)
        self.assertNotIn("test", title)
        self.assertNotIn("adr", title)

    def test_task_intent_titles_should_fallback_to_source_name_not_generic_topic(self) -> None:
        mod = _load_module("normalize_task_intents_for_source_fallback_test", "scripts/python/normalize_task_intents.py")
        result = mod.build_intents(
            {
                "schema": "task-generation.requirements-index.v1",
                "anchors": [
                    {
                        "requirement_id": "REQ-SOURCE-0001",
                        "source_path": "docs/gdd/m1-playable-setup.md",
                        "line": 1,
                        "kind": "acceptance",
                        "priority": "P2",
                        "text": "- ADR-0033 Test-Refs: tests must pass.",
                        "refs": [],
                    },
                ],
            },
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
        )

        title = result["intents"][0]["title"].lower()
        self.assertIn("playable", title)
        self.assertNotEqual("add test coverage for testing", title)

    def test_balanced_split_profile_should_split_gameplay_groups_more_finely_than_compact(self) -> None:
        mod = _load_module("normalize_task_intents_for_profile_test", "scripts/python/normalize_task_intents.py")
        anchors = [
            {
                "requirement_id": f"REQ-RUN-{idx:04d}",
                "source_path": "docs/gdd/run-loop.md",
                "line": idx,
                "kind": "gdd",
                "priority": "P2",
                "text": f"Run state turn cycle win lose terminal behavior requirement {idx} must be implemented.",
                "refs": [],
            }
            for idx in range(1, 9)
        ]

        compact = mod.build_intents(
            {"schema": "task-generation.requirements-index.v1", "anchors": anchors},
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
            split_profile="compact",
        )
        balanced = mod.build_intents(
            {"schema": "task-generation.requirements-index.v1", "anchors": anchors},
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
            split_profile="balanced",
        )

        self.assertEqual(2, compact["intent_count"])
        self.assertEqual(2, balanced["intent_count"])
        self.assertTrue(all(intent.get("complexity_score", 0) <= 7 for intent in compact["intents"]))
        self.assertEqual(
            sorted(anchor["requirement_id"] for anchor in anchors),
            sorted(rid for intent in compact["intents"] for rid in intent["requirement_ids"]),
        )
        self.assertEqual(
            sorted(anchor["requirement_id"] for anchor in anchors),
            sorted(rid for intent in balanced["intents"] for rid in intent["requirement_ids"]),
        )

    def test_split_titles_should_put_part_number_before_shared_focus(self) -> None:
        mod = _load_module("normalize_task_intents_for_title_part_test", "scripts/python/normalize_task_intents.py")
        anchors = [
            {
                "requirement_id": f"REQ-GATE-{idx:04d}",
                "source_path": "docs/gdd/audit.md",
                "line": idx,
                "kind": "gdd",
                "priority": "P2",
                "text": f"Validation gate closure deterministic state requirement {idx} must be visible.",
                "refs": [],
            }
            for idx in range(1, 9)
        ]

        result = mod.build_intents(
            {"schema": "task-generation.requirements-index.v1", "anchors": anchors},
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
            split_profile="balanced",
        )

        titles = [intent["title"] for intent in result["intents"]]
        self.assertTrue(any("part 1 validation" in title.lower() for title in titles))
        self.assertTrue(any("part 2 validation" in title.lower() for title in titles))

    def test_duplicate_titles_should_be_disambiguated_with_source_focus(self) -> None:
        mod = _load_module("normalize_task_intents_for_title_disambiguation_test", "scripts/python/normalize_task_intents.py")
        anchors = [
            {
                "requirement_id": "REQ-COPY-0001",
                "source_path": "docs/prd/narrative-style-guide.md",
                "line": 10,
                "kind": "prd",
                "priority": "P2",
                "text": "Screen specs must define visible copy.",
                "refs": [],
            },
            {
                "requirement_id": "REQ-COPY-0002",
                "source_path": "docs/prd/playtest-script.md",
                "line": 10,
                "kind": "prd",
                "priority": "P2",
                "text": "Screen specs must define visible copy.",
                "refs": [],
            },
        ]

        result = mod.build_intents(
            {"schema": "task-generation.requirements-index.v1", "anchors": anchors},
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
            split_profile="balanced",
        )

        titles = [intent["title"] for intent in result["intents"]]
        self.assertEqual(len(titles), len(set(titles)))

    def test_duplicate_single_source_titles_should_get_line_qualifier(self) -> None:
        mod = _load_module("normalize_task_intents_for_line_disambiguation_test", "scripts/python/normalize_task_intents.py")
        anchors = [
            {
                "requirement_id": "REQ-LINE-0001",
                "source_path": "docs/prd/main-prd.md",
                "line": 13,
                "kind": "requirement",
                "priority": "P2",
                "text": "The product name must be visible.",
                "refs": [],
            },
            {
                "requirement_id": "REQ-LINE-0002",
                "source_path": "docs/prd/main-prd.md",
                "line": 147,
                "kind": "prd",
                "priority": "P2",
                "text": "The product name must be visible.",
                "refs": [],
            },
        ]

        result = mod.build_intents(
            {"schema": "task-generation.requirements-index.v1", "anchors": anchors},
            mode="init",
            id_prefix="TST",
            max_anchors_per_intent=8,
            split_profile="balanced",
        )

        titles = [intent["title"] for intent in result["intents"]]
        self.assertTrue(any("line 13" in title for title in titles))
        self.assertTrue(any("line 147" in title for title in titles))

    def test_intent_titles_should_collapse_repeated_adjacent_words(self) -> None:
        mod = _load_module("normalize_task_intents_for_repeated_word_test", "scripts/python/normalize_task_intents.py")

        self.assertEqual("Implement newrouge", mod.intent_title("newrouge-0001", "newrouge"))
        self.assertEqual("Document playable setup", mod.collapse_repeated_words("Document playable setup playable setup"))

    def test_add_mode_should_reuse_intent_ids_and_skip_existing_task_ids(self) -> None:
        mod = _load_module("normalize_task_intents_for_incremental_id_test", "scripts/python/normalize_task_intents.py")
        previous = {
            "schema": "task-generation.task-intents.v1",
            "intents": [
                {
                    "id": "INT-0007",
                    "intent_key": "gdd:core:gameplay:combat-loop:combat:1",
                }
            ],
        }
        index = {
            "schema": "task-generation.requirements-index.v1",
            "anchors": [
                {
                    "requirement_id": "REQ-COMBAT-0001",
                    "source_path": "docs/gdd/combat.md",
                    "line": 1,
                    "kind": "gdd",
                    "priority": "P1",
                    "text": "Combat enemy attack damage targeting must be implemented.",
                    "refs": [],
                },
                {
                    "requirement_id": "REQ-UI-0001",
                    "source_path": "docs/gdd/ui.md",
                    "line": 1,
                    "kind": "gdd",
                    "priority": "P2",
                    "text": "UI HUD display must be implemented.",
                    "refs": [],
                },
            ],
        }
        first = mod.build_intents(
            index,
            mode="add",
            id_prefix="INT",
            max_anchors_per_intent=8,
            reserved_ids={"INT-0001", "INT-0002"},
            previous_intents=previous,
        )
        by_topic = {row["topic"]: row for row in first["intents"]}
        self.assertEqual("INT-0007", by_topic["combat-loop"]["id"])
        self.assertEqual("INT-0003", by_topic["ui-hud"]["id"])

        reordered = {
            **index,
            "anchors": list(reversed(index["anchors"])),
        }
        second = mod.build_intents(
            reordered,
            mode="add",
            id_prefix="INT",
            max_anchors_per_intent=8,
            reserved_ids={"INT-0001", "INT-0002"},
            previous_intents=first,
        )
        second_by_topic = {row["topic"]: row for row in second["intents"]}
        self.assertEqual(by_topic["combat-loop"]["id"], second_by_topic["combat-loop"]["id"])
        self.assertEqual(by_topic["ui-hud"]["id"], second_by_topic["ui-hud"]["id"])

    def test_triplet_change_plan_should_preserve_mature_fields_and_block_implicit_overwrite(self) -> None:
        mod = _load_module("compile_task_triplet_for_incremental_test", "scripts/python/compile_task_triplet.py")
        existing = [{
            "id": "INT-0001",
            "status": "done",
            "acceptance": ["Keep acceptance"],
            "semantic_review_tier": "full",
            "subtasks": [{"id": "s1", "status": "done"}],
        }]
        candidate = {
            "id": "INT-0001",
            "title": "Updated title",
            "status": "pending",
            "acceptance": [],
        }
        unchanged, operations, conflicts = mod.build_change_plan(existing, [candidate], "back")
        self.assertEqual(["INT-0001"], conflicts)
        self.assertEqual("done", unchanged[0]["status"])
        self.assertEqual(["Keep acceptance"], unchanged[0]["acceptance"])
        self.assertEqual("blocked", operations[0]["action"])

        explicit = dict(candidate, change_action="update", field_updates={"title": "Reviewed title"})
        updated, operations, conflicts = mod.build_change_plan(existing, [explicit], "back")
        self.assertEqual([], conflicts)
        self.assertEqual("Reviewed title", updated[0]["title"])
        self.assertEqual("done", updated[0]["status"])
        self.assertEqual(["Keep acceptance"], updated[0]["acceptance"])
        self.assertEqual([{"id": "s1", "status": "done"}], updated[0]["subtasks"])
        self.assertEqual("update", operations[0]["action"])

    def test_master_merge_preserves_subtasks_and_cross_view_conflicts_fail_closed(self) -> None:
        mod = _load_module("build_taskmaster_tasks_for_lossless_test", "scripts/python/build_taskmaster_tasks.py")
        existing = {
            "id": 6,
            "title": "Old",
            "status": "done",
            "subtasks": [{"id": 1, "status": "done"}],
            "future_extension": {"keep": True},
        }
        merged = mod.merge_master_fields(existing, {"id": 6, "title": "New", "status": "done"})
        self.assertEqual("New", merged["title"])
        self.assertEqual(existing["subtasks"], merged["subtasks"])
        self.assertEqual({"keep": True}, merged["future_extension"])
        with self.assertRaisesRegex(ValueError, "conflicting cross-view field"):
            mod._merge_view_task(
                {"id": "GM-1", "taskmaster_id": 6, "status": "done"},
                {"id": "GM-1", "taskmaster_id": 7, "status": "done"},
                "GM-1",
            )

        compatible = mod.merge_numeric_view_group([
            {
                "id": "NG-6",
                "taskmaster_id": 6,
                "status": "done",
                "acceptance": ["Backbone acceptance"],
                "overlay_refs": ["docs/back.md"],
            },
            {
                "id": "GM-6",
                "taskmaster_id": 6,
                "status": "done",
                "acceptance": ["Gameplay acceptance"],
                "overlay_refs": ["docs/game.md"],
            },
        ], 6)
        self.assertEqual(["Backbone acceptance", "Gameplay acceptance"], compatible["acceptance"])
        self.assertEqual(["docs/back.md", "docs/game.md"], compatible["overlay_refs"])
        self.assertEqual(["NG-6", "GM-6"], compatible["source_view_ids"])
        with self.assertRaisesRegex(ValueError, "conflicting cross-view field"):
            mod.merge_numeric_view_group([
                {"id": "NG-6", "taskmaster_id": 6, "status": "done", "title": "Backbone"},
                {"id": "GM-6", "taskmaster_id": 6, "status": "done", "title": "Different gameplay title"},
            ], 6)

    def test_candidate_generation_should_prefer_task_intents_when_present(self) -> None:
        mod = _load_module("generate_task_candidates_for_intent_test", "scripts/python/generate_task_candidates_from_sources.py")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "logs" / "ci" / "task-generation"
            out_dir.mkdir(parents=True)
            (out_dir / "requirements.index.json").write_text(
                json.dumps(
                    {
                        "schema": "task-generation.requirements-index.v1",
                        "anchors": [
                            {
                                "requirement_id": "REQ-OLD-0001",
                                "source_path": "docs/prd/a.md",
                                "line": 1,
                                "kind": "prd",
                                "priority": "P2",
                                "text": "Old source grouping should not be used.",
                                "refs": [],
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (out_dir / "task-intents.normalized.json").write_text(
                json.dumps(
                    {
                        "schema": "task-generation.task-intents.v1",
                        "intents": [
                            {
                                "id": "INT-0001",
                                "title": "Implement combat loop",
                                "description": "Combat loop intent.",
                                "details": ["Do combat work."],
                                "priority": "P1",
                                "layer": "core",
                                "owner": "gameplay",
                                "labels": ["combat-loop"],
                                "requirement_ids": ["REQ-NEW-0001", "REQ-NEW-0002"],
                                "source_refs": ["docs/gdd/a.md:10", "docs/gdd/a.md:11"],
                                "covered_anchor_count": 2,
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            rc = mod.main(["--repo-root", str(root), "--mode", "init", "--id-prefix", "GEN"])
            payload = json.loads((out_dir / "task-candidates.normalized.json").read_text(encoding="utf-8"))

        self.assertEqual(0, rc)
        self.assertEqual("task-generation.task-intents.v1", payload["source_schema"])
        self.assertEqual(1, payload["candidate_count"])
        self.assertEqual("INT-0001", payload["candidates"][0]["id"])
        self.assertEqual(["REQ-NEW-0001", "REQ-NEW-0002"], payload["candidates"][0]["requirement_ids"])

    def test_task_intent_quality_audit_should_report_generic_and_noisy_titles(self) -> None:
        mod = _load_module("audit_task_intents_quality_test", "scripts/python/audit_task_intents_quality.py")
        result = mod.audit(
            {
                "schema": "task-generation.task-intents.v1",
                "intents": [
                    {
                        "id": "INT-0001",
                        "title": "Add test coverage for testing",
                        "covered_anchor_count": 2,
                        "requirement_ids": ["REQ-1"],
                        "source_refs": ["docs/gdd/a.md:1"],
                    },
                    {
                        "id": "INT-0002",
                        "title": "Implement tasks.json refs",
                        "covered_anchor_count": 9,
                        "requirement_ids": [],
                        "source_refs": [],
                    },
                ],
            },
            max_anchors_per_intent=8,
        )

        self.assertEqual("review", result["status"])
        self.assertEqual(2, result["issue_count"])
        self.assertIn("generic_title", result["issue_counts"])
        self.assertIn("metadata_noise_in_title", result["issue_counts"])
        self.assertIn("too_many_anchors", result["issue_counts"])
        self.assertIn("missing_traceability", result["issue_counts"])

    def test_task_intent_quality_audit_should_not_merge_distinct_chinese_titles(self) -> None:
        mod = _load_module("audit_task_intents_quality_cjk_distinct_test", "scripts/python/audit_task_intents_quality.py")
        result = mod.audit(
            {
                "schema": "task-generation.task-intents.v1",
                "intents": [
                    {
                        "id": "INT-CJK-0001",
                        "title": "实现战斗节奏",
                        "covered_anchor_count": 2,
                        "requirement_ids": ["FR-COMBAT-1"],
                        "source_refs": ["docs/gdd/game.md:10"],
                    },
                    {
                        "id": "INT-CJK-0002",
                        "title": "实现商店规则",
                        "covered_anchor_count": 2,
                        "requirement_ids": ["FR-SHOP-1"],
                        "source_refs": ["docs/gdd/game.md:30"],
                    },
                ],
            },
            max_anchors_per_intent=8,
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual(0, result["issue_count"])
        self.assertNotIn("near_duplicate_title_prefix", result["issue_counts"])

    def test_task_intent_quality_audit_should_still_flag_duplicate_chinese_titles(self) -> None:
        mod = _load_module("audit_task_intents_quality_cjk_duplicate_test", "scripts/python/audit_task_intents_quality.py")
        result = mod.audit(
            {
                "schema": "task-generation.task-intents.v1",
                "intents": [
                    {
                        "id": "INT-CJK-0001",
                        "title": "实现战斗节奏",
                        "covered_anchor_count": 1,
                        "requirement_ids": ["FR-COMBAT-1"],
                        "source_refs": ["docs/gdd/game.md:10"],
                    },
                    {
                        "id": "INT-CJK-0002",
                        "title": "实现战斗节奏",
                        "covered_anchor_count": 1,
                        "requirement_ids": ["FR-COMBAT-2"],
                        "source_refs": ["docs/gdd/game.md:20"],
                    },
                ],
            },
            max_anchors_per_intent=8,
        )

        self.assertEqual("review", result["status"])
        self.assertEqual(2, result["issue_count"])
        self.assertEqual(2, result["issue_counts"]["near_duplicate_title_prefix"])

    def test_task_title_keys_preserve_mixed_unicode_and_chinese_part_focus(self) -> None:
        normalize = _load_module("normalize_task_intents_mixed_unicode_key_test", "scripts/python/normalize_task_intents.py")
        audit = _load_module("audit_task_intents_quality_mixed_unicode_key_test", "scripts/python/audit_task_intents_quality.py")

        self.assertNotEqual(
            normalize.title_key("实现UI战斗界面"),
            normalize.title_key("实现UI商店界面"),
        )
        self.assertNotEqual(
            normalize.title_key("实现第1部分：战斗规则"),
            normalize.title_key("实现第1部分：商店规则"),
        )
        self.assertNotEqual(
            audit.title_key("实现UI战斗界面"),
            audit.title_key("实现UI商店界面"),
        )
        self.assertNotEqual(
            audit.title_key("实现第1部分：战斗规则"),
            audit.title_key("实现第1部分：商店规则"),
        )

    def test_task_intent_quality_audit_should_treat_part_numbers_as_disambiguators(self) -> None:
        mod = _load_module("audit_task_intents_quality_part_key_test", "scripts/python/audit_task_intents_quality.py")
        result = mod.audit(
            {
                "schema": "task-generation.task-intents.v1",
                "intents": [
                    {
                        "id": "INT-0001",
                        "title": "Validate gdd part 1 closure deterministic draft state missing",
                        "covered_anchor_count": 4,
                        "requirement_ids": ["REQ-1"],
                        "source_refs": ["docs/gdd/a.md:1"],
                    },
                    {
                        "id": "INT-0002",
                        "title": "Validate gdd part 4 closure deterministic draft state missing",
                        "covered_anchor_count": 4,
                        "requirement_ids": ["REQ-2"],
                        "source_refs": ["docs/gdd/a.md:4"],
                    },
                ],
            },
            max_anchors_per_intent=8,
        )

        self.assertEqual("ok", result["status"])

    def test_regression_check_should_filter_back_only_and_post_ch3_tasks(self) -> None:
        mod = _load_module("run_chapter3_regression_check_test", "scripts/python/run_chapter3_regression_check.py")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_dir = root / ".taskmaster" / "tasks"
            task_dir.mkdir(parents=True)
            (task_dir / "tasks.json").write_text(
                json.dumps(
                    {
                        "master": {
                            "tasks": [
                                {"id": 1, "title": "Shared gameplay task", "labels": []},
                                {"id": 2, "title": "Back only task", "labels": []},
                                {"id": 3, "title": "Wire UI: Chapter 7 task", "labels": ["chapter7-ui"]},
                            ]
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "tasks_back.json").write_text(
                json.dumps(
                    [
                        {"id": "B-1", "taskmaster_id": 1, "title": "Shared gameplay task"},
                        {"id": "B-2", "taskmaster_id": 2, "title": "Back only task"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "tasks_gameplay.json").write_text(
                json.dumps([{"id": "G-1", "taskmaster_id": 1, "title": "Shared gameplay task"}]) + "\n",
                encoding="utf-8",
            )

            filtered = mod.filtered_tasks_json(root)

        self.assertEqual([1], [task["id"] for task in filtered])


if __name__ == "__main__":
    unittest.main()
