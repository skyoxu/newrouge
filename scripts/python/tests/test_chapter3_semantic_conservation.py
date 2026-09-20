#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "scripts" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import audit_task_candidate_coverage as coverage_mod
import build_source_ledger as ledger_mod
import enrich_task_candidates as enrich_mod
import normalize_task_intents as intents_mod
import project_semantics_from_sources as projection_mod
import refresh_chapter_knowledge as refresh_mod
import validate_semantic_conservation as conservation_mod
from _semantic_topology import load_workspace_topology


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Chapter3SemanticConservationTests(unittest.TestCase):
    def test_full_ledger_keeps_chinese_and_long_blocks_before_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gdd = root / "docs/gdd/game.md"
            gdd.parent.mkdir(parents=True)
            long_text = "长文本" * 800
            gdd.write_text(
                "# 商店规则\n\n"
                "商店不得升级卡牌，但可以移除诅咒。\n\n"
                "| 行为 | 规则 |\n| --- | --- |\n| Continue | 失败时必须阻断 |\n\n"
                + long_text + "\n",
                encoding="utf-8",
            )
            manifest, ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "init", explicit=True
            )
            raw = "\n".join(str(row["raw_text"]) for row in ledger["blocks"])
            self.assertIn("商店不得升级卡牌", raw)
            self.assertIn("失败时必须阻断", raw)
            self.assertIn(long_text, raw)
            self.assertEqual(manifest["block_count"], len(ledger["blocks"]))
            self.assertTrue(any(row["block_type"] == "table_row" for row in ledger["blocks"]))
            self.assertTrue(any(row["requirement_like_hint"] for row in ledger["blocks"]))

    def test_default_source_discovery_includes_optional_bmad_gdd_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_gdd = root / "docs/gdd/game.md"
            docs_gdd.parent.mkdir(parents=True)
            docs_gdd.write_text("Docs GDD rule.\n", encoding="utf-8")
            bmad_gdd = root / "_bmad-output/gdd.md"
            bmad_gdd.parent.mkdir(parents=True)
            bmad_gdd.write_text("BMAD GDD rule.\n", encoding="utf-8")
            args = type("Args", (), {
                "prd_path": [], "gdd_path": [], "epics_path": [],
                "stories_path": [], "source_glob": [],
            })()
            patterns, explicit = ledger_mod.collect_patterns(root, args)
            manifest, ledger = ledger_mod.build_ledger(
                root, patterns, "init", explicit=explicit
            )
            paths = {row["path"] for row in manifest["sources"]}
            self.assertIn("docs/gdd/game.md", paths)
            self.assertIn("_bmad-output/gdd.md", paths)
            raw = "\n".join(row["raw_text"] for row in ledger["blocks"])
            self.assertIn("BMAD GDD rule.", raw)

    def test_declared_missing_source_is_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "matched no supported files"):
                ledger_mod.build_ledger(root, ["docs/gdd/missing.md"], "init", explicit=True)

    def test_add_mode_reports_changed_and_unchanged_stable_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gdd = root / "docs/gdd/game.md"
            gdd.parent.mkdir(parents=True)
            gdd.write_text("# H\n\nA paragraph.\n\nB paragraph.\n", encoding="utf-8")
            _manifest, first = ledger_mod.build_ledger(root, ["docs/gdd/*.md"], "init", explicit=True)
            gdd.write_text("# H\n\nA paragraph changed.\n\nB paragraph.\n", encoding="utf-8")
            _manifest, second = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "add", explicit=True, previous_ledger=first
            )
            self.assertGreaterEqual(len(second["delta"]["changed"]), 1)
            self.assertGreaterEqual(len(second["delta"]["unchanged"]), 1)

    def test_add_mode_preserves_unchanged_ids_when_block_is_inserted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gdd = root / "docs/gdd/game.md"
            gdd.parent.mkdir(parents=True)
            gdd.write_text("# H\n\nA paragraph.\n\nB paragraph.\n", encoding="utf-8")
            _manifest, first = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "init", explicit=True
            )
            old_by_text = {
                row["raw_text"]: row["block_id"]
                for row in first["blocks"]
                if row["block_type"] == "paragraph"
            }
            gdd.write_text(
                "# H\n\nInserted paragraph.\n\nA paragraph.\n\nB paragraph.\n",
                encoding="utf-8",
            )
            _manifest, second = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "add", explicit=True, previous_ledger=first
            )
            new_by_text = {
                row["raw_text"]: row["block_id"]
                for row in second["blocks"]
                if row["block_type"] == "paragraph"
            }
            self.assertEqual(old_by_text["A paragraph."], new_by_text["A paragraph."])
            self.assertEqual(old_by_text["B paragraph."], new_by_text["B paragraph."])
            self.assertIn(new_by_text["A paragraph."], second["delta"]["unchanged"])
            self.assertIn(new_by_text["B paragraph."], second["delta"]["unchanged"])
            self.assertEqual(1, len(second["delta"]["added"]))
            self.assertEqual([], second["delta"]["removed"])

    def test_add_mode_reuses_only_hash_stable_reviewed_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gdd = root / "docs/gdd/game.md"
            gdd.parent.mkdir(parents=True)
            gdd.write_text("# H\n\nA paragraph.\n\nB paragraph.\n", encoding="utf-8")
            _manifest, first_ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "init", explicit=True
            )
            _index, first_candidate = projection_mod.prepare(
                first_ledger, 40, root / "batches-first"
            )
            for row in first_candidate["block_results"]:
                row.update({
                    "atoms": [],
                    "disposition": "context",
                    "delivery_potential": False,
                    "review_status": "reviewed",
                })
            for summary in first_candidate["batch_summaries"]:
                summary["output_accounted_count"] = summary["input_block_count"]

            gdd.write_text(
                "# H\n\nInserted paragraph.\n\nA paragraph.\n\nB paragraph.\n",
                encoding="utf-8",
            )
            _manifest, second_ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "add", explicit=True,
                previous_ledger=first_ledger,
            )
            index, second_candidate = projection_mod.prepare(
                second_ledger, 40, root / "batches-second",
                previous_candidate=first_candidate,
            )
            by_text = {
                block["raw_text"]: block["block_id"]
                for block in second_ledger["blocks"]
                if block["block_type"] == "paragraph"
            }
            results = {
                row["block_id"]: row for row in second_candidate["block_results"]
            }
            self.assertEqual(
                "reused_unchanged", results[by_text["A paragraph."]]["review_status"]
            )
            self.assertEqual(
                "reused_unchanged", results[by_text["B paragraph."]]["review_status"]
            )
            inserted = results[by_text["Inserted paragraph."]]
            self.assertEqual("review_required", inserted["review_status"])
            self.assertIsNone(inserted["delivery_potential"])
            self.assertIn(
                by_text["Inserted paragraph."],
                second_candidate["reuse_summary"]["review_required_blocks"],
            )
            self.assertEqual(
                len(second_candidate["reuse_summary"]["reused_blocks"]),
                sum(row["reused_accounted_count"] for row in second_candidate["batch_summaries"]),
            )
            self.assertEqual(
                index["source_block_count"],
                len(second_candidate["block_results"]),
            )

    def test_add_mode_cross_block_semantics_stale_when_any_source_block_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gdd = root / "docs/gdd/game.md"
            gdd.parent.mkdir(parents=True)
            gdd.write_text("# H\n\nA rule.\n\nB rule.\n", encoding="utf-8")
            _manifest, first_ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "init", explicit=True
            )
            _index, first_candidate = projection_mod.prepare(
                first_ledger, 40, root / "batches-first"
            )
            paragraphs = [
                row for row in first_ledger["blocks"]
                if row["block_type"] == "paragraph"
            ]
            a_id, b_id = paragraphs[0]["block_id"], paragraphs[1]["block_id"]
            for row in first_candidate["block_results"]:
                if row["block_id"] == a_id:
                    row.update({
                        "atoms": [{
                            "kind": "FR",
                            "statement": "A and B form one rule.",
                            "source_block_ids": [a_id, b_id],
                        }],
                        "disposition": "",
                        "delivery_potential": True,
                        "review_status": "reviewed",
                    })
                else:
                    row.update({
                        "atoms": [],
                        "disposition": "context",
                        "delivery_potential": False,
                        "review_status": "reviewed",
                    })
            for summary in first_candidate["batch_summaries"]:
                summary["output_accounted_count"] = summary["input_block_count"]

            gdd.write_text("# H\n\nA rule.\n\nB rule changed.\n", encoding="utf-8")
            _manifest, second_ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/*.md"], "add", explicit=True,
                previous_ledger=first_ledger,
            )
            _index, second_candidate = projection_mod.prepare(
                second_ledger, 40, root / "batches-second",
                previous_candidate=first_candidate,
            )
            result = next(
                row for row in second_candidate["block_results"]
                if row["block_id"] == a_id
            )
            self.assertEqual("review_required", result["review_status"])
            self.assertEqual([], result["atoms"])

    def test_projection_batches_account_for_every_source_block(self) -> None:
        ledger = {
            "source_revision": "source-set:test",
            "blocks": [
                {
                    "block_id": f"SB-{idx}",
                    "source_path": "docs/gdd/a.md",
                    "line_start": idx,
                    "line_end": idx,
                    "raw_text": f"rule {idx}",
                    "requirement_like_hint": idx % 2 == 0,
                }
                for idx in range(1, 8)
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            index, candidate = projection_mod.prepare(ledger, 3, Path(tmp))
        self.assertEqual(3, index["batch_count"])
        self.assertEqual(7, index["source_block_count"])
        self.assertEqual(7, len(candidate["block_results"]))
        self.assertEqual(
            {row["block_id"] for row in ledger["blocks"]},
            {row["block_id"] for row in candidate["block_results"]},
        )
        self.assertTrue(all(row["output_accounted_count"] == 0 for row in candidate["batch_summaries"]))
        self.assertTrue(all(row["disposition"] == "" for row in candidate["block_results"]))
        self.assertTrue(all(row["delivery_potential"] is None for row in candidate["block_results"]))

    def test_projection_compile_rejects_unreviewed_blocks_and_requires_batch_accounting(self) -> None:
        ledger = {
            "source_revision": "source-set:test",
            "source_manifest_sha256": "sha256:" + "1" * 64,
            "blocks": [{
                "block_id": "SB-1",
                "source_path": "docs/gdd/a.md",
                "line_start": 1,
                "line_end": 1,
                "raw_text": "升级为同一张卡的升级态。",
                "content_hash": "sha256:" + "2" * 64,
                "source_sha256": "3" * 64,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            index, candidate = projection_mod.prepare(ledger, 40, Path(tmp), 24000)
        with self.assertRaisesRegex(ValueError, "output_accounted_count"):
            projection_mod.compile_projection(ledger, index, candidate)

        candidate["batch_summaries"][0]["output_accounted_count"] = 1
        candidate["block_results"][0].update({
            "disposition": "context",
            "delivery_potential": False,
        })
        semantics, capabilities, _edges = projection_mod.compile_projection(ledger, index, candidate)
        self.assertEqual("context", semantics["source_accounting"][0]["disposition"])
        self.assertEqual([], capabilities["capabilities"])

    def test_projection_batch_budget_never_truncates_oversized_block(self) -> None:
        ledger = {
            "source_revision": "source-set:test",
            "blocks": [{
                "block_id": "SB-LONG",
                "source_path": "docs/gdd/a.md",
                "line_start": 1,
                "line_end": 1,
                "raw_text": "长" * 2000,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "do not truncate it silently"):
                projection_mod.prepare(ledger, 40, Path(tmp), 1000)

    def test_projection_conservation_blocks_delivery_potential_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/gdd/a.md"
            source.parent.mkdir(parents=True)
            source.write_text("商店不得升级卡牌。\n", encoding="utf-8")
            _manifest, ledger = ledger_mod.build_ledger(root, ["docs/gdd/a.md"], "init", explicit=True)
            block = ledger["blocks"][0]
            semantics = {
                "schema_version": "newrouge.semantic-requirements.v1",
                "source_revision": ledger["source_revision"],
                "source_manifest_sha256": ledger["source_manifest_sha256"],
                "source_accounting": [{
                    "block_id": block["block_id"],
                    "batch_id": "BATCH-0001",
                    "requirement_ids": [],
                    "disposition": "unresolved",
                    "delivery_potential": True,
                    "decision": None,
                }],
                "requirements": [],
            }
            report, _edges = conservation_mod.validate(root, ledger, semantics, "projection")
            self.assertEqual("blocked", report["status"])
            self.assertEqual(1, report["blocking_counts"]["unresolved_delivery_potential"])

            semantics["source_accounting"][0]["decision"] = {
                "owner": "game-design",
                "reason": "Explicitly classified as context after review.",
                "resolved_disposition": "context",
            }
            report, _edges = conservation_mod.validate(root, ledger, semantics, "projection")
            self.assertEqual("passed", report["status"])

    def test_projection_blocks_stale_semantic_binding_and_duplicate_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/gdd/a.md"
            source.parent.mkdir(parents=True)
            source.write_text("规则。\n", encoding="utf-8")
            _manifest, ledger = ledger_mod.build_ledger(
                root, ["docs/gdd/a.md"], "init", explicit=True
            )
            block_id = ledger["blocks"][0]["block_id"]
            accounting = {
                "block_id": block_id,
                "batch_id": "BATCH-0001",
                "requirement_ids": [],
                "disposition": "context",
                "delivery_potential": False,
                "decision": None,
            }
            semantics = {
                "schema_version": "newrouge.semantic-requirements.v1",
                "source_revision": "source-set:stale",
                "source_manifest_sha256": "sha256:" + "0" * 64,
                "source_accounting": [accounting, dict(accounting)],
                "requirements": [],
            }
            report, _edges = conservation_mod.validate(
                root, ledger, semantics, "projection"
            )
            self.assertEqual("blocked", report["status"])
            self.assertEqual(2, report["blocking_counts"]["binding_mismatches"])
            self.assertEqual(1, report["blocking_counts"]["duplicate_accounting_blocks"])

    def test_missing_p1_waiver_never_bypasses_semantic_or_p0_blockers(self) -> None:
        semantic_blocked = {
            "coverage_model": "semantic-sink",
            "missing_blocking": [{
                "requirement_id": "FR-1",
                "priority": "P1",
                "coverage_status": "missing",
            }],
            "invalid_task_semantic_refs": [],
            "legacy_p0_p1_packaging": {
                "missing": [{
                    "requirement_id": "LEGACY-P1",
                    "priority": "P1",
                }]
            },
        }
        remaining = coverage_mod.blocking_after_p1_waiver(semantic_blocked)
        self.assertTrue(any(row["kind"] == "semantic_sink" for row in remaining))

        packaging_only_p1 = {
            "coverage_model": "semantic-sink",
            "missing_blocking": [],
            "invalid_task_semantic_refs": [],
            "legacy_p0_p1_packaging": {
                "missing": [{"requirement_id": "LEGACY-P1", "priority": "P1"}]
            },
        }
        self.assertEqual([], coverage_mod.blocking_after_p1_waiver(packaging_only_p1))

        packaging_p0 = {
            "coverage_model": "semantic-sink",
            "missing_blocking": [],
            "invalid_task_semantic_refs": [],
            "legacy_p0_p1_packaging": {
                "missing": [{"requirement_id": "LEGACY-P0", "priority": "P0"}]
            },
        }
        remaining = coverage_mod.blocking_after_p1_waiver(packaging_p0)
        self.assertEqual("legacy_packaging", remaining[0]["kind"])

    def test_coverage_blocks_stale_existing_task_mapping_until_reconciled(self) -> None:
        semantics = {
            "schema_version": "newrouge.semantic-requirements.v1",
            "source_accounting": [],
            "requirements": [{
                "requirement_id": "FR-NEW",
                "kind": "functional",
                "statement": "Current rule.",
                "source_block_ids": ["SB-1"],
                "delivery_relevant": True,
                "sink_policy": "task_or_global_constraint",
                "status": "active",
            }],
        }
        candidates = {"candidates": [{
            "id": "T1",
            "semantic_refs": ["FR-NEW"],
            "requirement_ids": ["FR-NEW"],
        }]}
        stale_task = [{"id": "OLD", "semantic_refs": ["FR-REMOVED"]}]
        report = coverage_mod.audit(semantics, candidates, None, stale_task)
        self.assertEqual("blocked", report["status"])
        self.assertEqual("OLD", report["stale_existing_task_mappings"][0]["task_id"])

        reconciled_task = [{"id": "T1", "semantic_refs": ["FR-REMOVED"]}]
        report = coverage_mod.audit(semantics, candidates, None, reconciled_task)
        self.assertEqual([], report["stale_existing_task_mappings"])
        self.assertEqual("ok", report["status"])

    def test_closure_requires_delivery_sink_and_accepts_task_sink(self) -> None:
        semantics = {
            "requirements": [{
                "requirement_id": "FR-1",
                "kind": "functional",
                "statement": "Shop cannot upgrade cards.",
                "source_block_ids": ["SB-1"],
                "delivery_relevant": True,
                "sink_policy": "task_or_global_constraint",
                "status": "active",
            }]
        }
        closure, _edges = conservation_mod.closure_checks(semantics, {"candidates": []})
        self.assertEqual(1, len(closure["orphan_delivery_requirements"]))

        candidates = {"candidates": [{
            "id": "T1",
            "semantic_refs": ["FR-1"],
            "capability_refs": [],
            "complexity_score": 5,
        }]}
        closure, edges = conservation_mod.closure_checks(semantics, candidates)
        self.assertEqual([], closure["orphan_delivery_requirements"])
        self.assertTrue(any(edge["target_id"] == "T1" for edge in edges))

    def test_semantic_intent_keeps_capability_and_provisional_dependency(self) -> None:
        semantics = {
            "requirements": [
                {
                    "requirement_id": "FR-1",
                    "kind": "functional",
                    "statement": "Shop cannot upgrade cards.",
                    "source_block_ids": ["SB-1"],
                    "delivery_relevant": True,
                    "sink_policy": "task_or_global_constraint",
                    "status": "active",
                    "priority": "P1",
                },
                {
                    "requirement_id": "FR-2",
                    "kind": "functional",
                    "statement": "Curse can be removed.",
                    "source_block_ids": ["SB-2"],
                    "delivery_relevant": True,
                    "sink_policy": "task_or_global_constraint",
                    "status": "active",
                    "priority": "P1",
                },
            ]
        }
        blocks = {"blocks": [
            {"block_id": "SB-1", "source_path": "docs/gdd/a.md", "line_start": 1},
            {"block_id": "SB-2", "source_path": "docs/gdd/a.md", "line_start": 2},
        ]}
        capabilities = {"capabilities": [{
            "capability_id": "CAP-SHOP",
            "title": "Shop rules",
            "requirement_ids": ["FR-1", "FR-2"],
        }]}
        anchors = intents_mod.semantic_to_anchors(semantics, blocks, capabilities)
        result = intents_mod.build_intents(
            {"schema": "chapter3.validated-semantics.v1", "anchors": anchors},
            "init", "TST", 1, "compact",
        )
        self.assertEqual(2, result["intent_count"])
        self.assertTrue(all(row["capability_refs"] == ["CAP-SHOP"] for row in result["intents"]))
        self.assertTrue(all(row["semantic_refs"] for row in result["intents"]))
        self.assertTrue(any(row["depends_on"] for row in result["intents"]))
        self.assertTrue(all(row["dependency_status"] == "provisional" for row in result["intents"]))

    def test_enrichment_emits_file_overlap_as_advisory_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Game.Core/combat_damage.cs"
            path.parent.mkdir(parents=True)
            path.write_text("class CombatDamage {}\n", encoding="utf-8")
            candidates = {"candidates": [
                {"id": "T1", "title": "Combat damage rule", "description": "combat damage", "labels": [], "requirement_ids": ["FR-1"]},
                {"id": "T2", "title": "Combat damage calculation", "description": "combat damage", "labels": [], "requirement_ids": ["FR-2"]},
            ]}
            result = enrich_mod.enrich(root, candidates)
            by_id = {row["id"]: row for row in result["candidates"]}
            self.assertEqual("medium", by_id["T1"]["file_churn_signal"])
            self.assertTrue(by_id["T1"]["implementation_overlap_candidates"])
            self.assertEqual("medium", by_id["T2"]["file_churn_signal"])

    def _refresh_fixture(self, root: Path, status: str) -> dict[str, Path]:
        source = root / "docs/gdd/a.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("Shop cannot upgrade cards.\n", encoding="utf-8")
        source_sha = ledger_mod.sha256_text(source.read_text(encoding="utf-8"))
        block = {
            "block_id": "SB-1",
            "source_path": "docs/gdd/a.md",
            "source_sha256": source_sha,
            "heading_path": [],
            "block_type": "paragraph",
            "ordinal": 1,
            "line_start": 1,
            "line_end": 1,
            "content_hash": "sha256:" + ledger_mod.sha256_text("Shop cannot upgrade cards."),
            "raw_text": "Shop cannot upgrade cards.",
        }
        paths = {
            "manifest": root / "logs/ci/task-generation/source-manifest.v1.json",
            "ledger": root / "logs/ci/task-generation/source-blocks.v1.json",
            "semantics": root / "logs/ci/task-generation/semantic-requirements.v1.json",
            "capabilities": root / "logs/ci/task-generation/capabilities.v1.json",
            "edges": root / "logs/ci/task-generation/topology-edges.v1.json",
            "candidates": root / "logs/ci/task-generation/task-candidates.enriched.json",
            "report": root / "logs/ci/task-generation/semantic-conservation-report.json",
        }
        write_json(paths["manifest"], {
            "schema_version": "chapter3.source-manifest.v1",
            "source_revision": "source-set:test",
            "manifest_sha256": "sha256:" + "1" * 64,
            "repository_revision": "a" * 40,
        })
        write_json(paths["ledger"], {
            "schema_version": "newrouge.source-blocks.v1",
            "source_revision": "source-set:test",
            "source_manifest_sha256": "sha256:" + "1" * 64,
            "blocks": [block],
        })
        write_json(paths["semantics"], {
            "schema_version": "newrouge.semantic-requirements.v1",
            "source_revision": "source-set:test",
            "source_accounting": [{
                "block_id": "SB-1", "disposition": "atomized",
                "requirement_ids": ["FR-1"], "delivery_potential": True,
            }],
            "requirements": [{
                "requirement_id": "FR-1",
                "kind": "functional",
                "statement": "Shop cannot upgrade cards.",
                "source_block_ids": ["SB-1"],
                "delivery_relevant": True,
                "capability_ids": [],
                "sink_policy": "task_or_global_constraint",
                "status": "active",
            }],
        })
        write_json(paths["capabilities"], {
            "schema_version": "newrouge.capabilities.v1",
            "capabilities": [],
        })
        write_json(paths["edges"], {
            "schema_version": "newrouge.topology-edges.v1",
            "edges": [{
                "source_type": "requirement", "source_id": "FR-1",
                "target_type": "task", "target_id": "T1",
                "relation": "implemented_by",
            }],
        })
        write_json(paths["candidates"], {"candidates": [{
            "id": "T1", "title": "Shop rule", "status": "pending",
            "semantic_refs": ["FR-1"], "capability_refs": [],
        }]})
        write_json(paths["report"], {
            "schema_version": "chapter3.semantic-conservation-report.v1",
            "status": status,
            "blocking_counts": {} if status == "passed" else {"orphan_delivery_requirements": 1},
        })
        return paths

    def test_passed_closure_promotes_planning_topology_with_repository_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._refresh_fixture(root, "passed")
            summary = refresh_mod.run(
                root,
                source="chapter3",
                trigger_run_id="run-promote",
                refresh_local=True,
                write_planning=True,
                publish_if_eligible=False,
                triplet_status="passed",
                source_manifest_path=paths["manifest"],
                ledger_path=paths["ledger"],
                semantics_path=paths["semantics"],
                capabilities_path=paths["capabilities"],
                edges_path=paths["edges"],
                candidates_path=paths["candidates"],
                report_path=paths["report"],
            )
            self.assertTrue(summary["closure_passed"])
            self.assertEqual("written", summary["planning_artifact_status"])
            manifest_path = root / "docs/planning/semantic-topology/topology-manifest.v1.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("a" * 40, manifest["repository_revision"])
            self.assertEqual("source-set:test", manifest["source_revision"])
            self.assertTrue(manifest["artifacts"])

            write_json(paths["report"], {
                "schema_version": "chapter3.semantic-conservation-report.v1",
                "status": "blocked",
                "blocking_counts": {"orphan_delivery_requirements": 1},
            })
            summary = refresh_mod.run(
                root,
                source="chapter3",
                trigger_run_id="run-blocked-promote",
                refresh_local=True,
                write_planning=True,
                publish_if_eligible=False,
                triplet_status="blocked",
                source_manifest_path=paths["manifest"],
                ledger_path=paths["ledger"],
                semantics_path=paths["semantics"],
                capabilities_path=paths["capabilities"],
                edges_path=paths["edges"],
                candidates_path=paths["candidates"],
                report_path=paths["report"],
            )
            self.assertFalse(summary["closure_passed"])
            self.assertEqual("blocked_by_closure", summary["planning_artifact_status"])

    def test_failed_closure_never_attempts_canonical_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._refresh_fixture(root, "blocked")
            with patch.object(
                refresh_mod,
                "maybe_publish",
                side_effect=AssertionError("publication must not run before closure passes"),
            ):
                summary = refresh_mod.run(
                    root,
                    source="chapter3",
                    trigger_run_id="run-blocked-publish",
                    refresh_local=True,
                    write_planning=False,
                    publish_if_eligible=True,
                    triplet_status="blocked",
                    source_manifest_path=paths["manifest"],
                    ledger_path=paths["ledger"],
                    semantics_path=paths["semantics"],
                    capabilities_path=paths["capabilities"],
                    edges_path=paths["edges"],
                    candidates_path=paths["candidates"],
                    report_path=paths["report"],
                )
            self.assertFalse(summary["closure_passed"])
            self.assertEqual("deferred", summary["publication_status"])
            self.assertEqual("closure_not_passed", summary["publication_reason"])

    def test_failed_attempt_does_not_overwrite_latest_successful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._refresh_fixture(root, "passed")
            summary = refresh_mod.run(
                root,
                source="chapter3",
                trigger_run_id="run-pass",
                refresh_local=True,
                write_planning=False,
                publish_if_eligible=False,
                triplet_status="passed",
                source_manifest_path=paths["manifest"],
                ledger_path=paths["ledger"],
                semantics_path=paths["semantics"],
                capabilities_path=paths["capabilities"],
                edges_path=paths["edges"],
                candidates_path=paths["candidates"],
                report_path=paths["report"],
            )
            self.assertTrue(summary["closure_passed"])
            stable_before = (root / refresh_mod.STABLE_PATH).read_text(encoding="utf-8")

            write_json(paths["report"], {
                "schema_version": "chapter3.semantic-conservation-report.v1",
                "status": "blocked",
                "blocking_counts": {"orphan_delivery_requirements": 1},
            })
            summary = refresh_mod.run(
                root,
                source="chapter3",
                trigger_run_id="run-fail",
                refresh_local=True,
                write_planning=False,
                publish_if_eligible=False,
                triplet_status="blocked",
                source_manifest_path=paths["manifest"],
                ledger_path=paths["ledger"],
                semantics_path=paths["semantics"],
                capabilities_path=paths["capabilities"],
                edges_path=paths["edges"],
                candidates_path=paths["candidates"],
                report_path=paths["report"],
            )
            self.assertFalse(summary["closure_passed"])
            self.assertEqual(stable_before, (root / refresh_mod.STABLE_PATH).read_text(encoding="utf-8"))
            attempt = load_workspace_topology(root, "attempt")
            stable = load_workspace_topology(root, "stable")
            self.assertEqual("run-fail", attempt["identity"]["trigger_run_id"])
            self.assertEqual("run-pass", stable["identity"]["trigger_run_id"])
            self.assertFalse((root / "knowledge").exists())


if __name__ == "__main__":
    unittest.main()
