from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", capture_output=True, check=False, timeout=120)


class AnalyzeImpactCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        for relative in (
            "scripts/python/analyze_impact.py",
            "scripts/python/impact_analyzer.py",
            "scripts/python/impact_analysis_handoff.py",
            "scripts/python/impact_analysis_index.py",
            "scripts/python/build_impact_index.py",
            "scripts/python/impact_analysis_config.v1.json",
            "scripts/python/impact_target_aliases.v1.json",
        ):
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        files = {
            "project.godot": "[application]\nconfig/name=\"CLI Harness\"\n",
            "NewRouge.csproj": "<Project />\n",
            "Game.Core/Game.Core.csproj": "<Project />\n",
            "Game.Core.Tests/Game.Core.Tests.csproj": "<Project />\n",
            "Tests.Godot/Tests.Godot.csproj": "<Project />\n",
            "global.json": "{}\n",
            "Game.Godot/README.md": "# fixture\n",
            ".taskmaster/tasks/README.md": "# fixture\n",
            "docs/adr/README.md": "# fixture\n",
            "docs/architecture/README.md": "# fixture\n",
            "execution-plans/README.md": "# fixture\n",
            "decision-logs/README.md": "# fixture\n",
            "Game.Core/ImpactEvent.cs": "namespace Demo; public class ImpactEvent {}\n",
            "Game.Core/Consumer.cs": "namespace Demo; public class Consumer { private ImpactEvent? _event; }\n",
        }
        for relative, content in files.items():
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        for command in (("git", "init", "-b", "main"), ("git", "config", "user.email", "cli@example.com"), ("git", "config", "user.name", "CLI Harness"), ("git", "add", "."), ("git", "commit", "-m", "fixture")):
            result = run(*command, cwd=self.repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        revision = run("git", "rev-parse", "HEAD", cwd=self.repo)
        self.assertEqual(revision.returncode, 0, revision.stderr)
        self.revision = revision.stdout.strip()
        build = run(sys.executable, "scripts/python/build_impact_index.py", "--revision", self.revision, "--trusted-ref", "refs/heads/main", "--output-root", "logs/ci", cwd=self.repo)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        self.index_payload = json.loads(build.stdout)
        self.index_path = self.repo / self.index_payload["index_path"]
        self.frozen_path = self.repo / "logs/ci/frozen.json"
        self.frozen_path.parent.mkdir(parents=True, exist_ok=True)
        self.frozen_path.write_text(json.dumps({
            "schema_version": "newrouge.knowledge-frozen-context.v1",
            "freeze_state": "frozen",
            "snapshot": {"commit": self.revision},
            "consumer": "chapter6",
            "task_id": "T-CLI",
            "decision_set_sha256": "1" * 64,
            "freeze_point": "before-red",
            "publication_generation": "generation-1",
            "publication_sha256": "2" * 64,
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_real_cli_success_discovery_and_manifest_hashes(self) -> None:
        output = "logs/ci/cli-run/impact-report.v1.json"
        command = (sys.executable, "scripts/python/analyze_impact.py", "--target", '{"type":"file","id":"Game.Core/ImpactEvent.cs"}', "--revision", self.revision, "--trusted-ref", "refs/heads/main", "--frozen-context", "logs/ci/frozen.json", "--consumer", "chapter6", "--task-id", "T-CLI", "--output", output, "--repository-root", ".")
        result = run(*command, cwd=self.repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        report_path = self.repo / payload["report_path"]
        manifest_path = report_path.parent / "run-manifest.v1.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(report["repository_revision"], self.revision)
        self.assertEqual(manifest["repository_revision"], self.revision)
        self.assertEqual(manifest["report_sha256"], hashlib.sha256(report_path.read_bytes()).hexdigest())
        self.assertEqual(manifest["index_sha256"], hashlib.sha256(self.index_path.read_bytes()).hexdigest())

    def test_invalid_handoff_fails_closed_without_success_report(self) -> None:
        output = self.repo / "logs/ci/cli-run-invalid/impact-report.v1.json"
        result = run(sys.executable, "scripts/python/analyze_impact.py", "--target", '{"type":"file","id":"Game.Core/ImpactEvent.cs"}', "--revision", self.revision, "--index", str(self.index_path.relative_to(self.repo)), "--frozen-context", "logs/ci/missing.json", "--consumer", "chapter6", "--task-id", "T-CLI", "--output", output.relative_to(self.repo).as_posix(), cwd=self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(output.exists())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "invalid_kcp_binding")

    def test_discovery_rejects_multiple_index_provenances(self) -> None:
        duplicate = self.repo / "logs/ci/duplicate/impact-analysis/indexes/duplicate"
        shutil.copytree(self.index_path.parent, duplicate)
        manifest = duplicate / "index-manifest.v1.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["trusted_ref"] = "refs/heads/other"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        output = "logs/ci/cli-collision-discovery/impact-report.v1.json"
        result = run(sys.executable, "scripts/python/analyze_impact.py", "--target", '{"type":"file","id":"Game.Core/ImpactEvent.cs"}', "--revision", self.revision, "--frozen-context", "logs/ci/frozen.json", "--consumer", "chapter6", "--task-id", "T-CLI", "--output", output, cwd=self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.repo / output).read_text(encoding="utf-8"))["status"], "index_identity_collision")

    def test_output_collision_does_not_overwrite_report(self) -> None:
        output = self.repo / "logs/ci/cli-collision/report.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        original = b"existing"
        output.write_bytes(original)
        manifest = output.parent / "run-manifest.v1.json"
        manifest_original = b"existing-manifest"
        manifest.write_bytes(manifest_original)
        result = run(sys.executable, "scripts/python/analyze_impact.py", "--target", '{"type":"file","id":"Game.Core/ImpactEvent.cs"}', "--revision", self.revision, "--index", self.index_path.relative_to(self.repo).as_posix(), "--frozen-context", "logs/ci/frozen.json", "--consumer", "chapter6", "--task-id", "T-CLI", "--output", output.relative_to(self.repo).as_posix(), cwd=self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(manifest.read_bytes(), manifest_original)

    def test_malformed_target_fails_closed(self) -> None:
        output = self.repo / "logs/ci/cli-malformed/impact-report.v1.json"
        result = run(sys.executable, "scripts/python/analyze_impact.py", "--target", "{type:unknown}", "--revision", self.revision, "--index", self.index_path.relative_to(self.repo).as_posix(), "--frozen-context", "logs/ci/frozen.json", "--consumer", "chapter6", "--task-id", "T-CLI", "--output", output.relative_to(self.repo).as_posix(), cwd=self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
