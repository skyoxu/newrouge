#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


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


ci_pipeline = _load_module("ci_pipeline_module", "scripts/python/ci_pipeline.py")


class CiPipelineTimeoutTests(unittest.TestCase):
    def test_resolve_timeout_ms_should_fallback_to_default_when_invalid(self) -> None:
        with mock.patch.dict(os.environ, {"CI_DOTNET_STAGE_TIMEOUT_MS": "bad"}, clear=False):
            self.assertEqual(900_000, ci_pipeline._resolve_timeout_ms("CI_DOTNET_STAGE_TIMEOUT_MS", 900_000))

    def test_resolve_timeout_ms_should_clamp_minimum(self) -> None:
        with mock.patch.dict(os.environ, {"CI_DOTNET_STAGE_TIMEOUT_MS": "1000"}, clear=False):
            self.assertEqual(60_000, ci_pipeline._resolve_timeout_ms("CI_DOTNET_STAGE_TIMEOUT_MS", 900_000))

    def test_resolve_timeout_ms_should_use_env_value(self) -> None:
        with mock.patch.dict(os.environ, {"CI_DOTNET_STAGE_TIMEOUT_MS": "4200000"}, clear=False):
            self.assertEqual(4_200_000, ci_pipeline._resolve_timeout_ms("CI_DOTNET_STAGE_TIMEOUT_MS", 900_000))


if __name__ == "__main__":
    unittest.main()
