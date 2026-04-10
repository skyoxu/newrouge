#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "scripts" / "python"
SC_DIR = REPO_ROOT / "scripts" / "sc"
for candidate in (PYTHON_DIR, SC_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


inspect_run = _load_module("inspect_run_module", "scripts/python/inspect_run.py")


class InspectRunTests(unittest.TestCase):
    def test_inspect_run_artifacts_should_fallback_to_repair_guide_route_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            latest = root / "logs" / "ci" / "2026-04-10" / "sc-review-pipeline-task-15" / "latest.json"
            out_dir = root / "logs" / "ci" / "2026-04-10" / "sc-review-pipeline-task-15-run-15"
            _write_json(
                latest,
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "15",
                    "run_id": "run-15",
                    "status": "fail",
                    "latest_out_dir": str(out_dir),
                    "summary_path": str(out_dir / "summary.json"),
                    "execution_context_path": str(out_dir / "execution-context.json"),
                    "repair_guide_json_path": str(out_dir / "repair-guide.json"),
                },
            )
            _write_json(
                out_dir / "summary.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "15",
                    "run_id": "run-15",
                    "status": "fail",
                    "reason": "rerun_blocked:chapter6_route_run_6_8",
                    "steps": [],
                    "latest_summary_signals": {
                        "reason": "rerun_blocked:chapter6_route_run_6_8",
                    },
                    "chapter6_hints": {
                        "next_action": "",
                        "blocked_by": "rerun_guard",
                    },
                },
            )
            _write_json(
                out_dir / "execution-context.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "15",
                    "run_id": "run-15",
                    "status": "fail",
                    "delivery_profile": "fast-ship",
                    "security_profile": "host-safe",
                    "diagnostics": {
                        "rerun_guard": {
                            "kind": "chapter6_route_run_6_8",
                            "blocked": True,
                            "recommended_path": "run-6.8",
                        }
                    },
                },
            )
            _write_json(
                out_dir / "repair-guide.json",
                {
                    "status": "needs-fix",
                    "task_id": "15",
                    "summary_status": "fail",
                    "failed_step": "",
                    "recommendations": [
                        {
                            "id": "chapter6-route-run-6-8",
                            "title": "Use the narrow 6.8 lane instead of reopening a full 6.7 rerun",
                            "why": "The latest route already proved deterministic evidence is sufficient for this task. Continue with the targeted Needs Fix closure lane.",
                            "commands": [
                                "py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1"
                            ],
                            "files": [],
                        }
                    ],
                },
            )

            rc, payload = inspect_run.inspect_run_artifacts(repo_root=root, kind="pipeline", task_id="15")

            self.assertEqual(1, rc)
            self.assertEqual("needs-fix-fast", payload["recommended_action"])
            self.assertEqual(
                "py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1",
                payload["recommended_command"],
            )
            self.assertIn("deterministic evidence is sufficient", payload["recommended_action_why"].lower())

    def test_inspect_run_artifacts_should_surface_planned_only_recovery_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            latest = root / "logs" / "ci" / "2026-04-08" / "sc-review-pipeline-task-14" / "latest.json"
            out_dir = root / "logs" / "ci" / "2026-04-08" / "sc-review-pipeline-task-14-planned-run"
            _write_json(
                latest,
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "planned-run",
                    "status": "ok",
                    "latest_out_dir": str(out_dir),
                    "summary_path": str(out_dir / "summary.json"),
                    "execution_context_path": str(out_dir / "execution-context.json"),
                    "repair_guide_json_path": str(out_dir / "repair-guide.json"),
                    "run_events_path": str(out_dir / "run-events.jsonl"),
                },
            )
            _write_json(
                out_dir / "summary.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "planned-run",
                    "status": "ok",
                    "run_type": "planned-only",
                    "reason": "pipeline_clean",
                    "steps": [
                        {"name": "sc-test", "status": "planned"},
                        {"name": "sc-acceptance-check", "status": "planned"},
                    ],
                    "finished_at_utc": "2026-04-08T10:00:00+00:00",
                },
            )
            _write_json(
                out_dir / "execution-context.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "planned-run",
                    "status": "ok",
                    "delivery_profile": "fast-ship",
                    "security_profile": "host-safe",
                    "diagnostics": {},
                },
            )
            _write_json(
                out_dir / "repair-guide.json",
                {
                    "status": "not-needed",
                    "task_id": "14",
                    "summary_status": "ok",
                    "failed_step": "",
                    "recommendations": [],
                },
            )
            (out_dir / "run-events.jsonl").write_text(
                json.dumps(
                    {
                        "event": "run_completed",
                        "task_id": "14",
                        "run_id": "planned-run",
                        "status": "ok",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )

            rc, payload = inspect_run.inspect_run_artifacts(repo_root=root, kind="pipeline", task_id="14")

            self.assertEqual(1, rc)
            self.assertEqual("fail", payload["status"])
            self.assertEqual("planned_only_incomplete", payload["latest_summary_signals"]["reason"])
            self.assertEqual("planned-only", payload["latest_summary_signals"]["run_type"])
            self.assertEqual("planned_only_incomplete", payload["latest_summary_signals"]["artifact_integrity_kind"])
            self.assertEqual("rerun", payload["chapter6_hints"]["next_action"])
            self.assertEqual("artifact_integrity", payload["chapter6_hints"]["blocked_by"])
            self.assertIn("planned-only evidence", payload["recommended_action_why"])
            self.assertIn("rerun 6.7", payload["recommended_action_why"])

    def test_resolve_latest_path_should_prefer_real_bundle_over_newer_dry_run_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            real_latest = root / "logs" / "ci" / "2026-04-07" / "sc-review-pipeline-task-14" / "latest.json"
            real_out_dir = root / "logs" / "ci" / "2026-04-07" / "sc-review-pipeline-task-14-real-run"
            _write_json(
                real_latest,
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "real-run",
                    "status": "ok",
                    "latest_out_dir": str(real_out_dir),
                    "summary_path": str(real_out_dir / "summary.json"),
                },
            )
            _write_json(
                real_out_dir / "summary.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "real-run",
                    "status": "ok",
                    "run_type": "full",
                    "reason": "pipeline_clean",
                    "steps": [{"name": "sc-test", "status": "ok"}],
                    "finished_at_utc": "2026-04-07T10:00:00+00:00",
                },
            )

            dry_latest = root / "logs" / "ci" / "2026-04-08" / "sc-review-pipeline-task-14" / "latest.json"
            dry_out_dir = root / "logs" / "ci" / "2026-04-08" / "sc-review-pipeline-task-14-dry-run"
            _write_json(
                dry_latest,
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "dry-run",
                    "status": "fail",
                    "latest_out_dir": str(dry_out_dir),
                    "summary_path": str(dry_out_dir / "summary.json"),
                },
            )
            _write_json(
                dry_out_dir / "summary.json",
                {
                    "cmd": "sc-review-pipeline",
                    "task_id": "14",
                    "run_id": "dry-run",
                    "status": "fail",
                    "run_type": "planned-only",
                    "reason": "planned_only_incomplete",
                    "steps": [
                        {"name": "sc-test", "status": "planned"},
                        {"name": "sc-acceptance-check", "status": "planned"},
                    ],
                    "finished_at_utc": "2026-04-08T10:00:00+00:00",
                },
            )

            os.utime(real_latest, (1712560000, 1712560000))
            os.utime(dry_latest, (1712646400, 1712646400))

            resolved = inspect_run._resolve_latest_path(root, latest="", kind="pipeline", task_id="14", run_id="")
            self.assertEqual(real_latest.resolve(), resolved)

    def test_render_recommendation_only_should_surface_compact_recovery_fields(self) -> None:
        payload = {
            "task_id": "15",
            "run_id": "run-15",
            "recommended_action": "needs-fix-fast",
            "recommended_command": "py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1",
            "forbidden_commands": ["py -3 scripts/sc/run_review_pipeline.py --task-id 15"],
            "recommended_action_why": "Deterministic evidence is already sufficient.",
            "latest_summary_signals": {
                "reason": "rerun_blocked:repeat_review_needs_fix",
            },
            "chapter6_hints": {
                "next_action": "needs-fix-fast",
                "blocked_by": "rerun_guard",
            },
            "failure": {
                "code": "review-needs-fix",
            },
        }

        text = inspect_run._render_recommendation_only(payload)

        self.assertIn("task_id=15", text)
        self.assertIn("run_id=run-15", text)
        self.assertIn("failure_code=review-needs-fix", text)
        self.assertIn("recommended_action=needs-fix-fast", text)
        self.assertIn(
            "recommended_command=py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1",
            text,
        )
        self.assertIn("forbidden_commands=py -3 scripts/sc/run_review_pipeline.py --task-id 15", text)
        self.assertIn("latest_reason=rerun_blocked:repeat_review_needs_fix", text)
        self.assertIn("chapter6_next_action=needs-fix-fast", text)
        self.assertIn("blocked_by=rerun_guard", text)

    def test_main_recommendation_only_should_print_compact_text(self) -> None:
        payload = {
            "task_id": "15",
            "run_id": "run-15",
            "recommended_action": "needs-fix-fast",
            "recommended_command": "py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1",
            "forbidden_commands": ["py -3 scripts/sc/run_review_pipeline.py --task-id 15"],
            "recommended_action_why": "Deterministic evidence is already sufficient.",
            "latest_summary_signals": {"reason": "rerun_blocked:repeat_review_needs_fix"},
            "chapter6_hints": {"next_action": "needs-fix-fast", "blocked_by": "rerun_guard"},
            "failure": {"code": "review-needs-fix"},
        }
        stdout = io.StringIO()
        argv = [
            "--repo-root",
            str(REPO_ROOT),
            "--kind",
            "pipeline",
            "--task-id",
            "15",
            "--recommendation-only",
        ]
        with (
            mock.patch.object(inspect_run, "inspect_run_artifacts", return_value=(1, payload)),
            mock.patch.object(sys, "argv", ["inspect_run.py", *argv]),
            redirect_stdout(stdout),
        ):
            rc = inspect_run.main()

        self.assertEqual(1, rc)
        output = stdout.getvalue()
        self.assertIn("task_id=15", output)
        self.assertIn("recommended_action=needs-fix-fast", output)
        self.assertNotIn('"recommended_action": "needs-fix-fast"', output)

    def test_main_recommendation_only_json_should_print_compact_json(self) -> None:
        payload = {
            "task_id": "15",
            "run_id": "run-15",
            "recommended_action": "needs-fix-fast",
            "recommended_command": "py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 15 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1",
            "forbidden_commands": ["py -3 scripts/sc/run_review_pipeline.py --task-id 15"],
            "recommended_action_why": "Deterministic evidence is already sufficient.",
            "latest_summary_signals": {"reason": "rerun_blocked:repeat_review_needs_fix"},
            "chapter6_hints": {"next_action": "needs-fix-fast", "blocked_by": "rerun_guard"},
            "failure": {"code": "review-needs-fix"},
        }
        stdout = io.StringIO()
        argv = [
            "--repo-root",
            str(REPO_ROOT),
            "--kind",
            "pipeline",
            "--task-id",
            "15",
            "--recommendation-only",
            "--recommendation-format",
            "json",
        ]
        with (
            mock.patch.object(inspect_run, "inspect_run_artifacts", return_value=(1, payload)),
            mock.patch.object(sys, "argv", ["inspect_run.py", *argv]),
            redirect_stdout(stdout),
        ):
            rc = inspect_run.main()

        self.assertEqual(1, rc)
        compact = json.loads(stdout.getvalue())
        self.assertEqual("15", compact["task_id"])
        self.assertEqual("review-needs-fix", compact["failure_code"])
        self.assertEqual("rerun_guard", compact["blocked_by"])


if __name__ == "__main__":
    unittest.main()
