from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(*args: str, cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, input=input_text, text=True, encoding="utf-8", capture_output=True, check=False)


class KnowledgeControlPlaneTests(unittest.TestCase):
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
            "scripts/python/build_knowledge_catalog.py",
            "scripts/python/_knowledge_locator_core.py",
            "scripts/python/knowledge_locator.py",
        ]:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        files = {
            "AGENTS.md": "# Rules\nUse Chinese with users.\n",
            "README.md": "# Game\nWindows Godot game.\n",
            "DELIVERY_PROFILE.md": "# Delivery\nfast-ship\n",
            "docs/PROJECT_DOCUMENTATION_INDEX.md": "# Index\nADR and PRD routes.\n",
            "docs/testing-framework.md": "# Tests\nxUnit and GdUnit4.\n",
            "docs/adr/ADR-0034-test.md": "# ADR-0034: Test\n\n- Status: Accepted\n\nContracts live in Game.Core/Contracts.\n",
            "docs/adr/ADR-0033-old.md": "# ADR-0033: Old\n\n- Status: Superseded\n",
            "docs/prd/game.md": "# Game PRD\nCard combat and roguelike progression.\n",
            "execution-plans/2026-01-01-old.md": "# Old Plan\n\n- Status: done\n",
            "logs/ci/latest.md": "# Very relevant ADR card combat text that must stay excluded\n",
        }
        for relative, text in files.items():
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.check_call(["git", "add", "."], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "seed"], cwd=self.repo, stdout=subprocess.DEVNULL)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self) -> dict:
        completed = run(sys.executable, "scripts/python/build_knowledge_catalog.py", "--write", cwd=self.repo)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def request(self, query: str, consumer: str = "repository-session") -> dict:
        snapshot = json.loads((self.repo / "knowledge/snapshots/repository-source-snapshot.v1.json").read_text(encoding="utf-8"))
        request = {
            "schema_version": "newrouge.knowledge-locator-request.v1",
            "request_id": "t1",
            "consumer": consumer,
            "query": query,
            "snapshot": {"ref": snapshot["ref"], "commit": snapshot["commit"]},
            "policy_revision": "newrouge-knowledge-consumer-policies.v1",
        }
        completed = run(sys.executable, "scripts/python/knowledge_locator.py", cwd=self.repo, input_text=json.dumps(request))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_build_excludes_logs_and_classifies_domains(self) -> None:
        summary = self.build()
        self.assertGreater(summary["modules"], 3)
        catalog = json.loads((self.repo / "knowledge/catalogs/repository-knowledge-catalog.v1.json").read_text(encoding="utf-8"))
        paths = {module["source_path"] for module in catalog["modules"]}
        self.assertNotIn("logs/ci/latest.md", paths)
        prd = next(module for module in catalog["modules"] if module["source_path"] == "docs/prd/game.md")
        self.assertEqual(prd["primary_domain"], "game-design")

    def test_locator_is_location_only_and_hides_historical_without_exact_name(self) -> None:
        self.build()
        result = self.request("card combat roguelike")
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["candidates"])
        self.assertTrue(all("answer" not in candidate for candidate in result["candidates"]))
        self.assertTrue(all(candidate["path"] != "logs/ci/latest.md" for candidate in result["candidates"]))
        self.assertTrue(all(candidate["path"] != "execution-plans/2026-01-01-old.md" for candidate in result["candidates"]))

    def test_locator_blocks_when_authority_ref_moves(self) -> None:
        self.build()
        (self.repo / "docs/prd/game.md").write_text("# Game PRD\nChanged.\n", encoding="utf-8")
        subprocess.check_call(["git", "add", "docs/prd/game.md"], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "change source"], cwd=self.repo, stdout=subprocess.DEVNULL)
        result = self.request("card combat")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["candidates"], [])

    def test_superseded_adr_is_historical_but_exact_query_can_find_it(self) -> None:
        self.build()
        general = self.request("old architecture")
        self.assertTrue(all(candidate["path"] != "docs/adr/ADR-0033-old.md" for candidate in general["candidates"]))
        exact = self.request("ADR-0033")
        self.assertTrue(any(candidate["path"] == "docs/adr/ADR-0033-old.md" for candidate in exact["candidates"]))


if __name__ == "__main__":
    unittest.main()
