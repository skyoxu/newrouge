#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
sys.path.insert(0, str(SC_DIR))

from _technical_debt import collect_low_priority_review_findings, collect_pipeline_low_priority_findings, update_technical_debt_register, write_low_priority_debt_artifacts  # noqa: E402


class ReviewTechnicalDebtTests(unittest.TestCase):
    def test_collect_low_priority_findings_should_keep_only_p2_to_p4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_md = root / "review-code-reviewer.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## P1",
                        "- P1 fix save corruption before merge",
                        "",
                        "## P2",
                        "- P2 trim duplicate helper in Scripts/Core/Foo.cs",
                        "- P3 rename brittle local variable in Scripts/Core/Bar.cs",
                        "",
                        "Verdict: Needs Fix",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            summary = {
                "results": [
                    {
                        "agent": "code-reviewer",
                        "status": "ok",
                        "details": {"verdict": "Needs Fix"},
                        "output_path": str(review_md),
                    }
                ]
            }

            findings = collect_low_priority_review_findings(summary=summary, root=root)

            severities = [item["severity"] for item in findings]
            self.assertEqual(["P2", "P3"], severities)
            self.assertTrue(all(item["agent"] == "code-reviewer" for item in findings))
            self.assertTrue(all("P1" not in item["message"] for item in findings))

    def test_update_register_should_preserve_unreviewed_existing_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc_path = root / "docs" / "technical-debt.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text(
                "\n".join(
                    [
                        "# Technical Debt Register",
                        "",
                        "<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                        "## Task 11",
                        "- latest_run_id: oldrun",
                        "",
                        "### P2",
                        "- stale item",
                        "",
                        "<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            findings = [
                {
                    "severity": "P2",
                    "agent": "architect-reviewer",
                    "message": "trim duplicate helper in Scripts/Core/Foo.cs",
                    "source_path": "logs/ci/2026-03-22/sc-llm-review-task-11/review-architect-reviewer.md",
                },
                {
                    "severity": "P4",
                    "agent": "code-reviewer",
                    "message": "consider simplifying local naming in Scripts/Core/Bar.cs",
                    "source_path": "logs/ci/2026-03-22/sc-llm-review-task-11/review-code-reviewer.md",
                },
            ]

            payload = update_technical_debt_register(
                doc_path=doc_path,
                task_id="11",
                run_id="newrun",
                findings=findings,
                delivery_profile="fast-ship",
            )

            text = doc_path.read_text(encoding="utf-8")
            self.assertEqual("updated", payload["status"])
            self.assertIn("## Task 11", text)
            self.assertIn("newrun", text)
            self.assertIn("trim duplicate helper", text)
            self.assertIn("consider simplifying local naming", text)
            self.assertIn("stale item", text)
            persisted = json.loads(json.dumps(payload, ensure_ascii=False))
            self.assertEqual("11", persisted["task_id"])

    def test_structured_review_contract_should_drive_debt_and_respect_fix_through(self) -> None:
        summary = {
            "results": [
                {
                    "agent": "code-reviewer",
                    "status": "ok",
                    "output_path": "logs/review-code-reviewer.md",
                    "details": {
                        "review_contract": {
                            "completion_status": "completed",
                            "lenses": [],
                            "findings": [
                                {
                                    "finding_id": "F-P2",
                                    "claim": "P2 deferred polish",
                                    "severity": "P2",
                                    "disposition": {"action": "defer", "rationale": "allowed below P1 floor"},
                                },
                                {
                                    "finding_id": "F-P3",
                                    "claim": "P3 deferred cleanup",
                                    "severity": "P3",
                                    "disposition": {"action": "defer", "rationale": "allowed"},
                                },
                                {
                                    "finding_id": "F-P4-FIX",
                                    "claim": "P4 chosen for immediate fix",
                                    "severity": "P4",
                                    "disposition": {"action": "fix", "rationale": "do now"},
                                },
                            ],
                        }
                    },
                }
            ]
        }

        p1 = collect_low_priority_review_findings(summary=summary, fix_through="P1")
        self.assertEqual(["F-P2", "F-P3"], [item["finding_id"] for item in p1])
        p2 = collect_low_priority_review_findings(summary=summary, fix_through="P2")
        self.assertEqual(["F-P3"], [item["finding_id"] for item in p2])
        self.assertNotIn("F-P4-FIX", [item["finding_id"] for item in p1 + p2])

    def test_structured_contract_should_not_fall_back_to_markdown_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_md = root / "review-code-reviewer.md"
            review_md.write_text("## P2\n- stale markdown-only finding\n", encoding="utf-8")
            summary = {
                "results": [
                    {
                        "agent": "code-reviewer",
                        "status": "ok",
                        "output_path": str(review_md),
                        "details": {
                            "review_contract": {
                                "completion_status": "completed",
                                "lenses": [],
                                "findings": [],
                            }
                        },
                    }
                ]
            }

            findings = collect_low_priority_review_findings(summary=summary, root=root)
            self.assertEqual([], findings)

    def test_pipeline_adapter_should_read_real_llm_child_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            child_dir = root / "child-artifacts" / "sc-llm-review"
            child_dir.mkdir(parents=True, exist_ok=True)
            review_md = child_dir / "review-code-reviewer.md"
            review_md.write_text("## P2\n- P2 keep this residual\n\nVerdict: Needs Fix\n", encoding="utf-8")
            child_summary = child_dir / "summary.json"
            child_summary.write_text(
                json.dumps({"status": "warn", "results": [{"agent": "code-reviewer", "status": "ok", "output_path": str(review_md), "details": {"verdict": "Needs Fix"}}]}),
                encoding="utf-8",
            )
            findings, reason = collect_pipeline_low_priority_findings(
                pipeline_summary={"steps": [{"name": "sc-llm-review", "status": "fail", "summary_file": str(child_summary)}]},
                root=root,
            )
            self.assertEqual("ok", reason)
            self.assertEqual(1, len(findings))
            self.assertEqual("P2", findings[0]["severity"])
            self.assertTrue(findings[0]["finding_id"])

    def test_explicit_reject_disposition_should_close_only_matching_debt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc_path = root / "docs" / "technical-debt.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text(
                "\n".join(
                    [
                        "# Technical Debt Register",
                        "",
                        "<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                        "## Task 11",
                        "- latest_run_id: oldrun",
                        "",
                        "### P2",
                        "- [code-reviewer] rejected item {finding_id=F-REJECT}",
                        "- [code-reviewer] untouched item {finding_id=F-KEEP}",
                        "",
                        "<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            child_dir = root / "child-artifacts" / "sc-llm-review"
            child_dir.mkdir(parents=True, exist_ok=True)
            child_summary = child_dir / "summary.json"
            child_summary.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "completion_status": "completed",
                        "results": [
                            {
                                "agent": "code-reviewer",
                                "status": "ok",
                                "output_path": str(child_dir / "review-code-reviewer.md"),
                                "details": {
                                    "review_contract": {
                                        "completion_status": "completed",
                                        "lenses": [],
                                        "findings": [
                                            {
                                                "finding_id": "F-REJECT",
                                                "claim": "Old debt is not applicable after verification.",
                                                "severity": "P2",
                                                "evidence": ["Game.Core.Tests/Tasks/Task11Tests.cs"],
                                                "verification": "Bound regression confirms the old claim is invalid.",
                                                "disposition": {
                                                    "action": "reject",
                                                    "rationale": "Re-review disproved the old finding.",
                                                },
                                            }
                                        ],
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out_dir = root / "logs" / "ci" / "2026-09-22" / "sc-review-pipeline-task-11-run"
            out_dir.mkdir(parents=True, exist_ok=True)

            result = write_low_priority_debt_artifacts(
                out_dir=out_dir,
                summary={
                    "steps": [
                        {
                            "name": "sc-llm-review",
                            "status": "ok",
                            "summary_file": str(child_summary),
                        }
                    ]
                },
                task_id="11",
                run_id="newrun",
                delivery_profile="fast-ship",
                root=root,
            )

            text = doc_path.read_text(encoding="utf-8")
            self.assertEqual("updated", result["register_status"])
            self.assertNotIn("F-REJECT", text)
            self.assertIn("F-KEEP", text)
            self.assertIn("untouched item", text)

    def test_invalid_child_review_cannot_close_existing_debt(self) -> None:
        for completion, errors, contract_completion in (
            ("incomplete", [], "completed"),
            ("completed", ["required_lens_missing:Edge Case"], "completed"),
            ("completed", [], "incomplete"),
        ):
            with self.subTest(completion=completion, errors=errors, contract_completion=contract_completion), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                out_dir = root / "run"
                out_dir.mkdir()
                debt_file = root / "docs" / "technical-debt.md"
                update_technical_debt_register(
                    doc_path=debt_file, task_id="11", run_id="old",
                    findings=[{"finding_id": "F-KEEP", "severity": "P2", "message": "Open issue", "agent": "code-reviewer"}],
                    delivery_profile="fast-ship",
                )
                before = debt_file.read_text(encoding="utf-8")
                child_path = out_dir / "child.json"
                child_path.write_text(json.dumps({
                    "completion_status": completion,
                    "results": [{"agent": "code-reviewer", "status": "ok", "details": {
                        "review_contract_errors": errors,
                        "review_contract": {"completion_status": contract_completion, "findings": [{
                            "finding_id": "F-KEEP", "evidence": ["test evidence"], "verification": "Rechecked",
                            "disposition": {"action": "reject", "rationale": "Invalid conclusion"},
                        }]},
                    }}],
                }), encoding="utf-8")
                result = write_low_priority_debt_artifacts(
                    out_dir=out_dir,
                    summary={"status": "fail", "steps": [{"name": "sc-llm-review", "status": "fail", "summary_file": str(child_path)}]},
                    task_id="11", run_id="new", delivery_profile="fast-ship", root=root,
                )
                self.assertEqual("skipped", result["register_status"])
                self.assertEqual(before, debt_file.read_text(encoding="utf-8"))
    def test_write_artifacts_should_not_touch_register_when_llm_review_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc_path = root / "docs" / "technical-debt.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            original = "\n".join(
                [
                    "# Technical Debt Register",
                    "",
                    "<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                    "## Task 11",
                    "- latest_run_id: oldrun",
                    "",
                    "### P2",
                    "- stale item",
                    "",
                    "<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->",
                    "",
                ]
            )
            doc_path.write_text(original, encoding="utf-8")
            out_dir = root / "logs" / "ci" / "2026-03-22" / "sc-review-pipeline-task-11-run"
            out_dir.mkdir(parents=True, exist_ok=True)

            result = write_low_priority_debt_artifacts(
                out_dir=out_dir,
                summary={
                    "steps": [{"name": "sc-llm-review", "status": "planned"}],
                    "results": [],
                },
                task_id="11",
                run_id="run",
                delivery_profile="fast-ship",
                root=root,
            )

            self.assertEqual("skipped", result["register_status"])
            self.assertEqual(original, doc_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
