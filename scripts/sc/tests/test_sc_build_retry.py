#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


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


sc_build = _load_module("sc_build_module", "scripts/sc/build.py")


class ScBuildRetryTests(unittest.TestCase):
    def test_should_retry_once_when_cs2012_file_lock_happens(self) -> None:
        outputs = [
            (1, "CSC : error CS2012: Cannot open file because it is being used by another process."),
            (0, "Build succeeded."),
        ]
        run_cmd_mock = mock.Mock(side_effect=outputs)
        with mock.patch.object(sc_build, "run_cmd", run_cmd_mock), \
            mock.patch.object(sc_build.time, "sleep") as sleep_mock:
            rc, out, attempts = sc_build.run_build_with_file_lock_retry(
                cmd=["dotnet", "build", "NewRouge.csproj"],
                retry_on_file_lock=1,
                retry_backoff_sec=0.01,
                timeout_sec=10,
            )

        self.assertEqual(0, rc)
        self.assertEqual(2, len(attempts))
        self.assertEqual(1, attempts[0]["rc"])
        self.assertTrue(attempts[0]["retryable_file_lock"])
        self.assertEqual(0, attempts[1]["rc"])
        self.assertEqual(2, run_cmd_mock.call_count)
        sleep_mock.assert_called_once()
        self.assertIn("attempt 1", out)
        self.assertIn("attempt 2", out)

    def test_should_not_retry_when_failure_is_not_file_lock(self) -> None:
        run_cmd_mock = mock.Mock(return_value=(1, "error CS1002: ; expected"))
        with mock.patch.object(sc_build, "run_cmd", run_cmd_mock), \
            mock.patch.object(sc_build.time, "sleep") as sleep_mock:
            rc, out, attempts = sc_build.run_build_with_file_lock_retry(
                cmd=["dotnet", "build", "NewRouge.csproj"],
                retry_on_file_lock=2,
                retry_backoff_sec=0.01,
                timeout_sec=10,
            )

        self.assertEqual(1, rc)
        self.assertEqual(1, len(attempts))
        self.assertFalse(attempts[0]["retryable_file_lock"])
        self.assertEqual(1, run_cmd_mock.call_count)
        sleep_mock.assert_not_called()
        self.assertIn("attempt 1", out)

    def test_should_stop_after_retry_budget_is_exhausted(self) -> None:
        run_cmd_mock = mock.Mock(
            return_value=(
                1,
                "CSC : error CS2012: Cannot open 'NewRouge.dll' because it is being used by another process.",
            )
        )
        with mock.patch.object(sc_build, "run_cmd", run_cmd_mock), \
            mock.patch.object(sc_build.time, "sleep") as sleep_mock:
            rc, _, attempts = sc_build.run_build_with_file_lock_retry(
                cmd=["dotnet", "build", "NewRouge.csproj"],
                retry_on_file_lock=1,
                retry_backoff_sec=0.01,
                timeout_sec=10,
            )

        self.assertEqual(1, rc)
        self.assertEqual(2, len(attempts))
        self.assertTrue(all(bool(item["retryable_file_lock"]) for item in attempts))
        self.assertEqual(2, run_cmd_mock.call_count)
        sleep_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
