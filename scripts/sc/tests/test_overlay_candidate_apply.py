from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SC_DIR))

from _overlay_candidate_store import build_candidate_inputs, save_candidate, write_candidate_bundle
from _overlay_candidate_apply import apply_candidate_pages


class OverlayCandidateApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prd = self.root / "prd.md"
        self.prd.write_text("New requirements", encoding="utf-8")
        self.companion = self.root / "rules.md"
        self.companion.write_text("Rules", encoding="utf-8")
        for name in ("tasks.json", "tasks_back.json", "tasks_gameplay.json"):
            path = self.root / ".taskmaster" / "tasks" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}" if name == "tasks.json" else "[]", encoding="utf-8")
        self.target = self.root / "docs/architecture/overlays/PRD-TEST/08"
        self.target.mkdir(parents=True)
        (self.target / "_index.md").write_bytes(b"Old index\r\n")

    def context(self, mode: str = "scaffold") -> dict:
        return build_candidate_inputs(
            repo_root=self.root, prd_path=self.prd, companion_paths=[self.companion],
            prd_id="PRD-TEST", page_mode=mode,
        )

    def candidate(self, name: str = "simulate", pages: dict[str, bytes] | None = None) -> tuple[Path, dict]:
        pages = pages or {"_index.md": b"Reviewed candidate\r\n"}
        out = self.root / "logs/ci/2026-10-07" / name
        generated = out / "generated/PRD-TEST/08"
        generated.mkdir(parents=True)
        for filename, content in pages.items():
            (generated / filename).write_bytes(content)
        base = {filename: (self.target / filename).read_bytes() if (self.target / filename).exists() else None for filename in pages}
        pointer = save_candidate(
            repo_root=self.root, out_dir=out, context=self.context(),
            base_files=base, generated_dir=generated,
        )
        return out, pointer

    def apply(self, pages: list[str] | None = None, source: str = "") -> dict:
        return apply_candidate_pages(
            repo_root=self.root, out_dir=self.root / "logs/ci/2026-10-07/apply",
            context=self.context(), pages=pages or ["_index.md"], candidate_from=source,
        )

    def test_apply_should_promote_exact_saved_bytes_without_model_execution(self) -> None:
        self.candidate()
        with patch("_overlay_generator_prompting.run_codex_exec", side_effect=AssertionError("Model must not run")):
            result = self.apply()
        self.assertEqual("apply", result["mode"])
        self.assertEqual(b"Reviewed candidate\r\n", (self.target / "_index.md").read_bytes())

    def test_explicit_candidate_should_not_use_a_newer_simulation(self) -> None:
        first, _ = self.candidate("first", {"_index.md": b"Reviewed first"})
        self.candidate("second", {"_index.md": b"Unreviewed second"})
        self.apply(source=str(first))
        self.assertEqual(b"Reviewed first", (self.target / "_index.md").read_bytes())

    def test_input_drift_should_block_without_writing(self) -> None:
        for relative in ("prd.md", "rules.md", ".taskmaster/tasks/tasks_back.json"):
            with self.subTest(source=relative):
                self.candidate(relative.replace("/", "-"))
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b" changed")
                with self.assertRaisesRegex(ValueError, "input.*(changed|drift)"):
                    self.apply()
                self.assertEqual(b"Old index\r\n", (self.target / "_index.md").read_bytes())
                path.write_bytes(original)

    def test_source_and_generated_drift_should_block_all_selected_pages(self) -> None:
        out, _ = self.candidate(pages={"_index.md": b"New index", "feature.md": b"New feature"})
        (out / "generated/PRD-TEST/08/feature.md").write_bytes(b"Tampered")
        with self.assertRaisesRegex(ValueError, "(?i)candidate.*(changed|drift)"):
            self.apply(["_index.md", "feature.md"])
        self.assertEqual(b"Old index\r\n", (self.target / "_index.md").read_bytes())
        self.assertFalse((self.target / "feature.md").exists())

    def test_new_file_created_after_simulate_should_block(self) -> None:
        self.candidate(pages={"feature.md": b"New feature"})
        (self.target / "feature.md").write_bytes(b"Concurrent change")
        with self.assertRaisesRegex(ValueError, "(?i)overlay source"):
            self.apply(["feature.md"])

    def test_missing_candidate_should_not_generate_or_write(self) -> None:
        with self.assertRaisesRegex(ValueError, "(?i)candidate.*missing"):
            self.apply()
        self.assertEqual(b"Old index\r\n", (self.target / "_index.md").read_bytes())

    def test_manifest_mutation_should_block(self) -> None:
        out, _ = self.candidate()
        (out / "candidate.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.apply()

    def test_bundle_should_support_a_selected_subset(self) -> None:
        first, a = self.candidate("index")
        _, b = self.candidate("feature", {"feature.md": b"Reviewed feature"})
        bundle = self.root / "logs/ci/2026-10-07/batch"
        write_candidate_bundle(repo_root=self.root, out_dir=bundle, results=[
            {"page": "_index.md", **a}, {"page": "feature.md", **b},
        ])
        self.apply(["feature.md"], str(bundle))
        self.assertEqual(b"Reviewed feature", (self.target / "feature.md").read_bytes())
        self.assertEqual(b"Old index\r\n", (self.target / "_index.md").read_bytes())

    def test_path_traversal_should_block(self) -> None:
        self.candidate()
        with self.assertRaisesRegex(ValueError, "filename"):
            self.apply(["../outside.md"])

    def test_newlines_changed_in_original_page_should_block(self) -> None:
        self.candidate()
        (self.target / "_index.md").write_bytes(b"Old index\n")
        with self.assertRaisesRegex(ValueError, "(?i)overlay source"):
            self.apply()

    def test_unselected_generated_files_should_not_be_promoted(self) -> None:
        out, _ = self.candidate()
        (out / "generated/PRD-TEST/08/unselected.md").write_bytes(b"Uninspected")
        self.apply()
        self.assertFalse((self.target / "unselected.md").exists())

    def test_page_mode_mismatch_should_block_explicit_candidate(self) -> None:
        out, _ = self.candidate()
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            apply_candidate_pages(repo_root=self.root, out_dir=self.root / "logs/ci/apply", context=self.context("replace"), pages=["_index.md"], candidate_from=str(out))

    def test_malformed_bundle_should_block_with_a_clear_error(self) -> None:
        self.candidate()
        source = self.root / "logs/ci/batch/candidate-bundle.json"
        source.parent.mkdir(parents=True)
        source.write_text('{"schema_version":1,"pages":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid candidate page pointers"):
            self.apply(source=str(source))

    def test_failed_replacement_should_restore_all_original_pages(self) -> None:
        self.candidate(pages={"_index.md": b"New index", "feature.md": b"New feature"})
        import _overlay_generator_runtime as runtime
        original_replace = runtime.os.replace
        calls = []
        def fail_second(source: object, target: object) -> None:
            calls.append(target)
            if len(calls) == 2:
                raise OSError("Injected write failure")
            original_replace(source, target)
        with patch.object(runtime.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "Injected"):
                self.apply(["_index.md", "feature.md"])
        self.assertEqual(b"Old index\r\n", (self.target / "_index.md").read_bytes())
        self.assertFalse((self.target / "feature.md").exists())


if __name__ == "__main__":
    unittest.main()
