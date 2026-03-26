import tempfile
import unittest
from pathlib import Path

from scripts.sc._repo_targets import resolve_solution_file


class RepoTargetsTests(unittest.TestCase):
    def test_resolve_solution_file_prefers_repo_named_solution_over_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.sln").write_text("game", encoding="utf-8")
            (root / f"{root.name}.sln").write_text("repo", encoding="utf-8")

            chosen = resolve_solution_file(root)

            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name.lower(), f"{root.name}.sln".lower())

    def test_resolve_solution_file_falls_back_to_game_when_repo_named_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.sln").write_text("game", encoding="utf-8")

            chosen = resolve_solution_file(root)

            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name, "Game.sln")


if __name__ == "__main__":
    unittest.main()
