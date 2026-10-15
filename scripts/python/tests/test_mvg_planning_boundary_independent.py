"""Independent negative cases for MVG planning filesystem ownership."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_planning_boundary as boundary
import plan_mvg


class PlanningBoundaryIndependentTests(unittest.TestCase):
    def protected_files(self, root):
        paths = [".taskmaster/tasks/tasks.json", "docs/gdd/source.md", "Game.Core/Contracts/Boundary.cs",
                 "Game.Godot/Scenes/main.tscn", "Tests.Godot/tests/acceptance.gd",
                 "logs/ci/mvg-acceptance/accepted/summary.json"]
        for ref in paths:
            target = root / ref
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(("Protected authority: " + ref).encode("utf-8"))
        return {ref: (root / ref).read_bytes() for ref in paths}

    def assert_protected(self, root, original):
        self.assertEqual(original, {ref: (root / ref).read_bytes() for ref in original})

    def assert_receipts(self, root):
        receipts = list((root / "logs/ci/mvg-planning-rejections").glob("*.json"))
        self.assertTrue(receipts, "Rejected planning operations must have safe diagnostic receipts")
        self.assertTrue(all(path.resolve().is_relative_to((root / "logs").resolve()) for path in receipts))

    def junction(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        else:
            link.symlink_to(target, target_is_directory=True)
        self.assertEqual(target.resolve(), link.resolve())

    def test_run_ids_cannot_address_another_directory_or_windows_device(self):
        invalid = ("", ".", "..", "../escape", "..\\escape", "nested/run", "nested\\run",
                   "C:\\escape", "C:escape", "/escape", "CON", "con", "con.json", "NUL", "AUX", "PRN", "COM1", "LPT1",
                   "run.", "run ", "run:stream", "-run")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            original = self.protected_files(root)
            for run_id in invalid:
                with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                    boundary.safe_run_dir(root, run_id)
            self.assertEqual((root / "logs/ci/mvg-planning/run-1.2_ok").resolve(),
                             boundary.safe_run_dir(root, "run-1.2_ok").resolve())
            self.assertFalse((Path(folder) / "escape").exists())
            self.assert_receipts(root)
            self.assert_protected(root, original)

    def test_manifest_targets_reject_protected_paths_aliases_and_trace_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.protected_files(root)
            invalid = list(original) + ["../escape.json", "C:\\escape.json", "C:escape.json",
                "/escape.json", "docs/testing/mvg/../outside.json", "docs/testing/mvg/planning/fixture.json",
                "docs/testing/mvg/fixture.txt", "docs\\testing\\mvg\\fixture.json"]
            for ref in invalid:
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    boundary.planning_targets(root, "fixture", ref)
            manifest, trace = boundary.planning_targets(root, "fixture", "docs/testing/mvg/fixture.json")
            self.assertEqual((root / "docs/testing/mvg/fixture.json").resolve(), manifest.resolve())
            self.assertEqual((root / "docs/testing/mvg/planning/fixture.json").resolve(), trace.resolve())
            self.assert_receipts(root)
            self.assert_protected(root, original)

    def test_directory_junctions_cannot_redirect_run_manifest_or_trace_writes(self):
        for redirected in ("logs/ci/mvg-planning", "logs/ci/mvg-planning/fixture",
                           "docs/testing/mvg", "docs/testing/mvg/planning"):
            with self.subTest(redirected=redirected), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "repo"
                root.mkdir()
                original = self.protected_files(root)
                target = root / "Game.Core/Private"
                target.mkdir(parents=True)
                sentinel = target / "sentinel.json"
                sentinel.write_bytes(b"Original protected content")
                self.junction(root / redirected, target)
                with self.assertRaises(ValueError):
                    if redirected.startswith("logs/"):
                        boundary.safe_run_dir(root, "fixture")
                    else:
                        boundary.planning_targets(root, "fixture", "docs/testing/mvg/fixture.json")
                self.assertEqual([sentinel], list(target.iterdir()))
                self.assertEqual(b"Original protected content", sentinel.read_bytes())
                self.assert_receipts(root)
                self.assert_protected(root, original)

    def test_unsafe_logs_root_rejects_without_writing_diagnostic_outside_repo(self):
        with tempfile.TemporaryDirectory() as folder:
            root, foreign = Path(folder) / "repo", Path(folder) / "foreign"
            root.mkdir()
            foreign.mkdir()
            sentinel = foreign / "sentinel.txt"
            sentinel.write_bytes(b"Unchanged outside repository")
            self.junction(root / "logs", foreign)
            with self.assertRaises(ValueError):
                boundary.safe_run_dir(root, "fixture")
            self.assertEqual([sentinel], list(foreign.iterdir()))
            self.assertEqual(b"Unchanged outside repository", sentinel.read_bytes())

    def test_handoff_output_stays_within_run_planning_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.protected_files(root)
            for ref in list(original) + ["../handoff.json", "docs/testing/mvg/handoff.json",
                "logs/ci/mvg-planning/other/handoffs/task.json", "logs/ci/mvg-planning/fixture/run.json"]:
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    boundary.handoff_target(root, "fixture", Path(ref))
            target = boundary.handoff_target(root, "fixture", Path("logs/ci/mvg-planning/fixture/handoffs/task.json"))
            self.assertEqual((root / "logs/ci/mvg-planning/fixture/handoffs/task.json").resolve(), target.resolve())
            self.assert_receipts(root)
            self.assert_protected(root, original)

    def test_public_prepare_rejects_unsafe_outputs_before_consuming_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.protected_files(root)
            cases = [("../Game.Core", "docs/testing/mvg/fixture.json"),
                     ("fixture", ".taskmaster/tasks/tasks.json"),
                     ("fixture", "docs/testing/mvg/../source.json"),
                     ("fixture", str(root / "docs/testing/mvg/fixture.json"))]
            for run_id, manifest in cases:
                with self.subTest(run_id=run_id, manifest=manifest):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        result = plan_mvg.main(["--repo-root", str(root), "prepare",
                            "--run-id", run_id, "--manifest", manifest,
                            "--capabilities", "missing-source.json"])
                    self.assertEqual(2, result)
                    payload = json.loads(output.getvalue())
                    self.assertEqual("blocked", payload["status"])
                    self.assertIn("planning_write_boundary:", payload["reason"])
                    self.assertNotIn("missing-source", payload["reason"])
            self.assertFalse((root / "logs/ci/mvg-planning/fixture/run.json").exists())
            self.assertFalse((root / "docs/testing/mvg/fixture.json").exists())
            self.assert_receipts(root)
            self.assert_protected(root, original)

    def test_hardlinked_manifest_and_run_artifacts_cannot_alias_authority(self):
        for alias in ("docs/testing/mvg/fixture.json",
                      "logs/ci/mvg-planning/fixture/analysis-input/authority.json"):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original = self.protected_files(root)
                linked = root / alias
                linked.parent.mkdir(parents=True, exist_ok=True)
                os.link(root / ".taskmaster/tasks/tasks.json", linked)
                self.assertGreater(linked.stat().st_nlink, 1)
                with self.assertRaisesRegex(ValueError, "planning_write_boundary:"):
                    if alias.startswith("logs/"):
                        boundary.safe_run_dir(root, "fixture")
                    else:
                        boundary.planning_targets(root, "fixture", "docs/testing/mvg/fixture.json")
                self.assertEqual(original[".taskmaster/tasks/tasks.json"], linked.read_bytes())
                self.assert_receipts(root)
                self.assert_protected(root, original)


if __name__ == "__main__":
    unittest.main()
