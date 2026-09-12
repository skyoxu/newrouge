from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class KnowledgePublicationFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.check_call(["git", "init", "-b", "main"], cwd=self.repo, stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=self.repo)
        subprocess.check_call(["git", "config", "user.name", "Test"], cwd=self.repo)

        for relative in [
            "knowledge/policies/consumer-policies.v1.json",
            "knowledge/policies/source-exclusions.v1.json",
            "scripts/python/_knowledge_catalog_builder.py",
            "scripts/python/_knowledge_locator_core.py",
            "scripts/python/knowledge_locator.py",
            "scripts/python/publish_knowledge_catalog.py",
        ]:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

        suite = {
            "schema_version": "newrouge.knowledge-evaluation-suite.v1",
            "cases": [
                {
                    "id": "repository-rules",
                    "consumer": "repository-session",
                    "query": "Repository Guide startup rules",
                    "must_include": [
                        {"any_paths": ["AGENTS.md"], "domains": ["toolchain"], "statuses": ["active"]}
                    ],
                    "forbidden_path_prefixes": ["logs/"],
                }
            ],
        }
        suite_path = self.repo / "knowledge/evaluation/queries.v1.json"
        suite_path.parent.mkdir(parents=True, exist_ok=True)
        suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")

        files = {
            "AGENTS.md": "# Repository Guide\nStartup rules and authority.\n",
            "README.md": "# Game\nWindows Godot game.\n",
            "workflow.md": "# Workflow\nChapter 6 single task loop.\n",
            "DELIVERY_PROFILE.md": "# Delivery\nfast-ship\n",
            "docs/PROJECT_DOCUMENTATION_INDEX.md": "# Index\nRoutes.\n",
            "docs/testing-framework.md": "# Tests\nxUnit and GdUnit4.\n",
            "docs/architecture/ADR_INDEX_GODOT.md": "# ADR Index Godot\nAccepted ADRs.\n",
            "docs/adr/ADR-0034-test.md": "# ADR-0034: Test\n\n- Status: Accepted\n",
            "docs/prd/game.md": "# Game PRD\nCard combat.\n",
            ".taskmaster/tasks/tasks.json": "{\"master\":{\"tasks\":[]}}\n",
        }
        for relative, content in files.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        subprocess.check_call(["git", "add", "."], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "baseline"], cwd=self.repo, stdout=subprocess.DEVNULL)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_publish(self, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/python/publish_knowledge_catalog.py", mode],
            cwd=self.repo,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def request(self) -> dict:
        snapshot = json.loads(
            (self.repo / "knowledge/snapshots/repository-source-snapshot.v1.json").read_text(encoding="utf-8")
        )
        policies = json.loads(
            (self.repo / "knowledge/policies/consumer-policies.v1.json").read_text(encoding="utf-8")
        )
        request = {
            "schema_version": "newrouge.knowledge-locator-request.v1",
            "request_id": "freshness-test",
            "consumer": "repository-session",
            "query": "Repository Guide startup rules",
            "snapshot": {"ref": snapshot["ref"], "commit": snapshot["commit"]},
            "policy_revision": policies["policy_revision"],
        }
        completed = subprocess.run(
            [sys.executable, "scripts/python/knowledge_locator.py"],
            cwd=self.repo,
            input=json.dumps(request),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_generated_state_and_unrelated_commits_do_not_stale_publication(self) -> None:
        published = self.run_publish("--publish")
        self.assertEqual(published.returncode, 0, published.stdout + published.stderr)
        self.assertEqual(self.request()["status"], "matched")

        subprocess.check_call(["git", "add", "knowledge/catalogs", "knowledge/indexes", "knowledge/projections", "knowledge/snapshots"], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "publish generated knowledge state"], cwd=self.repo, stdout=subprocess.DEVNULL)
        checked = self.run_publish("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(self.request()["status"], "matched")

        unrelated = self.repo / "scripts/python/project_health_knowledge.py"
        unrelated.write_text("# unrelated local project-health change\n", encoding="utf-8")
        subprocess.check_call(["git", "add", str(unrelated.relative_to(self.repo))], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "change unrelated project health"], cwd=self.repo, stdout=subprocess.DEVNULL)
        checked = self.run_publish("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(self.request()["status"], "matched")

    def test_authoritative_source_change_stales_publication(self) -> None:
        published = self.run_publish("--publish")
        self.assertEqual(published.returncode, 0, published.stdout + published.stderr)
        subprocess.check_call(["git", "add", "knowledge/catalogs", "knowledge/indexes", "knowledge/projections", "knowledge/snapshots"], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "publish generated knowledge state"], cwd=self.repo, stdout=subprocess.DEVNULL)

        readme = self.repo / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "Authoritative change.\n", encoding="utf-8")
        subprocess.check_call(["git", "add", "README.md"], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "change authority"], cwd=self.repo, stdout=subprocess.DEVNULL)

        checked = self.run_publish("--check")
        self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
        payload = json.loads(checked.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason"], "authority_inputs_changed")
        self.assertEqual(self.request()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
