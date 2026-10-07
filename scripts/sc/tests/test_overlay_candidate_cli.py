from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm_generate_overlays_from_prd as single
import llm_generate_overlays_batch as batch
import _overlay_generator_execution as execution


class OverlayCandidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "prd.md").write_text("Requirements", encoding="utf-8")
        tasks = self.root / ".taskmaster/tasks"
        tasks.mkdir(parents=True)
        for name in ("tasks.json", "tasks_back.json", "tasks_gameplay.json"):
            (tasks / name).write_text('{"master":{"tasks":[]}}' if name == "tasks.json" else "[]", encoding="utf-8")
        self.target = self.root / "docs/architecture/overlays/PRD-TEST/08"
        self.target.mkdir(parents=True)
        for name in ("_index.md", "feature.md"):
            (self.target / name).write_text("# Page\n\n## Directory Role\n\n- Original\n", encoding="utf-8")
        stack = ExitStack()
        self.addCleanup(stack.close)
        for module in (single, batch):
            stack.enter_context(patch.object(module, "repo_root", return_value=self.root))
            stack.enter_context(patch.object(module, "ci_dir", side_effect=lambda name: self.root / "logs/ci/2026-10-07" / name))
        self.models = stack.enter_context(patch.object(execution, "run_codex_exec", side_effect=self.model))

    @staticmethod
    def model(**kwargs: object) -> tuple[int, str, list[str]]:
        path = kwargs["out_last_message"]
        name = Path(path).name.removesuffix(".output.json")
        Path(path).write_text(json.dumps({"filename": name, "update": {"sections": [{"heading": "Directory Role", "bullets": ["Reviewed"]}]}}), encoding="utf-8")
        return 0, "", ["codex", "exec"]

    def invoke_single(self, extra: list[str]) -> int:
        with patch.object(sys, "argv", ["overlay", "--prd", "prd.md", "--prd-id", "PRD-TEST", "--page-filter", "_index.md", *extra]):
            return single.main()

    def invoke_batch(self, extra: list[str]) -> int:
        with patch.object(sys, "argv", ["overlay-batch", "--prd", "prd.md", "--prd-id", "PRD-TEST", "--pages", "_index.md,feature.md", *extra]):
            return batch.main()

    def test_single_apply_should_reuse_the_recorded_candidate_without_an_extra_parameter(self) -> None:
        self.assertEqual(0, self.invoke_single(["--run-suffix", "sim"]))
        candidate = next((self.root / "logs/ci/2026-10-07").glob("*--sim/generated/PRD-TEST/08/_index.md")).read_bytes()
        self.models.reset_mock()
        self.assertEqual(0, self.invoke_single(["--apply", "--run-suffix", "apply"]))
        self.models.assert_not_called()
        self.assertEqual(candidate, (self.target / "_index.md").read_bytes())

    def test_apply_without_simulate_should_fail_without_running_the_model(self) -> None:
        self.assertEqual(1, self.invoke_single(["--apply"]))
        self.models.assert_not_called()
        self.assertNotIn("Reviewed", (self.target / "_index.md").read_text())

    def test_batch_apply_should_verify_every_page_before_writing_and_skip_child_processes(self) -> None:
        def child(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            with patch.object(sys, "argv", cmd[2:]):
                rc = single.main()
            return SimpleNamespace(returncode=rc, stdout="")
        with patch.object(batch.subprocess, "run", side_effect=child) as children:
            self.assertEqual(0, self.invoke_batch(["--batch-suffix", "sim"]))
            self.assertEqual(2, children.call_count)
        original = (self.target / "_index.md").read_bytes()
        (self.target / "feature.md").write_text("Changed after review", encoding="utf-8")
        self.models.reset_mock()
        source = "logs/ci/2026-10-07/sc-llm-overlay-gen-batch-prd-test--sim"
        with patch.object(batch.subprocess, "run", side_effect=AssertionError("No model children")):
            self.assertEqual(1, self.invoke_batch(["--apply", "--candidate-from", source, "--batch-suffix", "apply"]))
        self.models.assert_not_called()
        self.assertEqual(original, (self.target / "_index.md").read_bytes())

    def test_batch_apply_should_promote_the_selected_bundle(self) -> None:
        for name in ("_index.md", "feature.md"):
            with patch.object(sys, "argv", ["overlay", "--prd", "prd.md", "--prd-id", "PRD-TEST", "--page-filter", name, "--run-suffix", name]):
                self.assertEqual(0, single.main())
        self.models.reset_mock()
        with patch.object(batch.subprocess, "run", side_effect=AssertionError("No model children")):
            self.assertEqual(0, self.invoke_batch(["--apply", "--batch-suffix", "apply"]))
        self.models.assert_not_called()
        for name in ("_index.md", "feature.md"):
            self.assertIn("Reviewed", (self.target / name).read_text())

    def test_dry_run_should_not_publish_a_candidate_or_call_model(self) -> None:
        self.assertEqual(0, self.invoke_single(["--dry-run"]))
        self.models.assert_not_called()
        self.assertFalse((self.root / "logs/ci/overlay-candidates").exists())

    def test_failed_simulate_should_invalidate_its_default_candidate(self) -> None:
        self.assertEqual(0, self.invoke_single(["--run-suffix", "first"]))
        self.models.side_effect = lambda **kwargs: (124, "timeout", [])
        self.assertEqual(1, self.invoke_single(["--run-suffix", "failed"]))
        self.models.reset_mock()
        self.assertEqual(1, self.invoke_single(["--apply"]))
        self.models.assert_not_called()

    def test_input_change_during_generation_should_not_publish_a_ready_candidate(self) -> None:
        def change_input(**kwargs: object) -> tuple[int, str, list[str]]:
            result = self.model(**kwargs)
            (self.root / "prd.md").write_text("Requirements changed during generation", encoding="utf-8")
            return result
        self.models.side_effect = change_input
        self.assertEqual(1, self.invoke_single(["--run-suffix", "drift"]))
        self.assertFalse((self.root / "logs/ci/overlay-candidates").exists())
        self.assertNotIn("Reviewed", (self.target / "_index.md").read_text())


if __name__ == "__main__":
    unittest.main()
