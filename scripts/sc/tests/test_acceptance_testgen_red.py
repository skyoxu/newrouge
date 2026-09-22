#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


red = _load_module("sc_acceptance_testgen_red_module", "scripts/sc/_acceptance_testgen_red.py")
gdunit = _load_module("run_gdunit_red_identity_module", "scripts/python/run_gdunit.py")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AcceptanceTestgenRedTests(unittest.TestCase):
    def test_evaluate_red_verification_should_fail_on_unexpected_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "ok", "rc": 0, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=ok\n",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )

        self.assertEqual("fail", report["status"])
        self.assertEqual("unexpected_green", report["reason"])

    def test_evaluate_red_verification_should_accept_unit_test_failure_without_compile_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "unit" / "2026-03-20" / "summary.json",
                {
                    "status": "tests_failed",
                    "filter": "FullyQualifiedName~RewardTests",
                    "failure_excerpt": [
                        "Failed Game.Core.Tests.Combat.RewardTests.ShouldAward",
                        "Expected: 2",
                        "But was: 1",
                    ],
                },
            )
            _write_json(root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run.json", {})
            (root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            (root / "logs" / "unit" / "2026-03-20" / "run_id.txt").write_text("run-red\n", encoding="utf-8")

            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail\n",
                expected_test_refs=["Tests.Godot/tests/Scenes/test_reward_scene.gd"],
            )

        self.assertEqual("ok", report["status"])
        self.assertEqual("unit_behavior_red", report["reason"])

    def test_evaluate_red_verification_should_reject_timeout_without_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 124, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="process timed out",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )
        self.assertEqual("fail", report["status"])
        self.assertEqual("verification_timeout", report["reason"])

    def test_evaluate_red_verification_should_reject_nonzero_without_behavior_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )
        self.assertEqual("fail", report["status"])
        self.assertEqual("verification_report_missing", report["reason"])

    def test_evaluate_red_verification_should_reject_tests_failed_without_assertion_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "unit" / "2026-03-20" / "summary.json",
                {
                    "status": "tests_failed",
                    "filter": "FullyQualifiedName~RewardTests",
                    "failure_excerpt": ["Failed Game.Core.Tests.Combat.RewardTests.ShouldAward", "process exited with code 1"],
                },
            )
            (root / "logs" / "ci" / "2026-03-20" / "sc-test").mkdir(parents=True, exist_ok=True)
            (root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            (root / "logs" / "unit" / "2026-03-20" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )
        self.assertEqual("fail", report["status"])
        self.assertEqual("unit_failure_not_causal", report["reason"])

    def test_evaluate_red_verification_should_fail_on_compile_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "unit" / "2026-03-20" / "summary.json",
                {
                    "status": "tests_failed",
                    "failure_excerpt": ["error CS1002: ; expected"],
                },
            )

            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="Build FAILED.\nerror CS1002: ; expected\n",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )

        self.assertEqual("fail", report["status"])
        self.assertEqual("compile_error", report["reason"])

    def test_evaluate_red_verification_should_accept_gdunit_failures_without_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "e2e" / "2026-03-20" / "sc-test" / "gdunit-hard" / "run-summary.json",
                {
                    "added": ["tests/Scenes/test_reward_scene.gd"],
                    "results": {
                        "tests": 1,
                        "failures": 1,
                        "errors": 0,
                        "failed_tests": ["test_reward_scene::test_missing_reward_behavior"],
                    }
                },
            )
            (root / "logs" / "ci" / "2026-03-20" / "sc-test").mkdir(parents=True, exist_ok=True)
            (root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            (root / "logs" / "e2e" / "2026-03-20" / "sc-test" / "gdunit-hard" / "run_id.txt").write_text("run-red\n", encoding="utf-8")

            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="all",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail\n",
                expected_test_refs=["Tests.Godot/tests/Scenes/test_reward_scene.gd"],
            )

        self.assertEqual("ok", report["status"])
        self.assertEqual("gdunit_behavior_red", report["reason"])


    def test_evaluate_red_verification_should_reject_unrelated_unit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "unit" / "2026-03-20" / "summary.json",
                {
                    "status": "tests_failed",
                    "filter": "FullyQualifiedName~RewardTests",
                    "failure_excerpt": [
                        "Failed Game.Core.Tests.Save.OtherTests.ShouldFail",
                        "Expected: true",
                        "But was: false",
                    ],
                },
            )
            (root / "logs" / "ci" / "2026-03-20" / "sc-test").mkdir(parents=True, exist_ok=True)
            (root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            (root / "logs" / "unit" / "2026-03-20" / "run_id.txt").write_text("run-red\n", encoding="utf-8")

            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="unit",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail\n",
                expected_test_refs=["Game.Core.Tests/Combat/RewardTests.cs"],
            )

        self.assertEqual("fail", report["status"])
        self.assertEqual("unit_failure_not_target", report["reason"])

    def test_evaluate_red_verification_should_reject_unrelated_gdunit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "logs" / "ci" / "2026-03-20" / "sc-llm-acceptance-tests"
            _write_json(
                root / "logs" / "e2e" / "2026-03-20" / "sc-test" / "gdunit-hard" / "run-summary.json",
                {
                    "added": ["tests/Scenes/test_reward_scene.gd"],
                    "results": {
                        "tests": 2,
                        "failures": 1,
                        "errors": 0,
                        "failed_tests": ["test_inventory_scene::test_unrelated_failure"],
                    },
                },
            )
            (root / "logs" / "ci" / "2026-03-20" / "sc-test").mkdir(parents=True, exist_ok=True)
            (root / "logs" / "ci" / "2026-03-20" / "sc-test" / "run_id.txt").write_text("run-red\n", encoding="utf-8")
            (root / "logs" / "e2e" / "2026-03-20" / "sc-test" / "gdunit-hard" / "run_id.txt").write_text("run-red\n", encoding="utf-8")

            report = red.evaluate_red_verification(
                repo_root=root,
                out_dir=out_dir,
                verify_mode="all",
                test_step={"status": "fail", "rc": 1, "cmd": ["py", "-3", "scripts/sc/test.py"]},
                verify_log_text="SC_TEST status=fail\n",
                expected_test_refs=["Tests.Godot/tests/Scenes/test_reward_scene.gd"],
            )

        self.assertEqual("fail", report["status"])
        self.assertEqual("gdunit_failure_not_target", report["reason"])

    def test_gdunit_result_parser_should_emit_failed_testcase_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "results.xml"
            result_path.write_text(
                '<testsuites tests="2" failures="1">'
                '<testsuite errors="0">'
                '<testcase classname="test_reward_scene" name="test_missing_reward_behavior">'
                '<failure message="expected reward"/>'
                '</testcase>'
                '<testcase classname="test_reward_scene" name="test_other"/>'
                '</testsuite>'
                '</testsuites>',
                encoding="utf-8",
            )

            parsed = gdunit._parse_results_xml(str(result_path))

        self.assertEqual(2, parsed["tests"])
        self.assertEqual(1, parsed["failures"])
        self.assertEqual(
            ["test_reward_scene::test_missing_reward_behavior"],
            parsed["failed_tests"],
        )


if __name__ == "__main__":
    unittest.main()
