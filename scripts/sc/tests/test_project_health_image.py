"""Revision-bound image preview boundaries."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from _project_health_http import image_bytes
from project_health_knowledge import write_json, base_dir


class ImageTests(unittest.TestCase):
    def test_reads_blob_from_exact_snapshot_and_rejects_other_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = 'Game.Godot/Assets/card.png'
            revision = 'a' * 40
            write_json(base_dir(root) / 'latest.json', {'revision': revision, 'file_manifest': [path]})
            with patch('_project_health_http.subprocess.run') as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, b'4'), subprocess.CompletedProcess([], 0, b'PNG!')]
                self.assertEqual(image_bytes(root, path, revision), (b'PNG!', 'image/png'))
                self.assertEqual(run.call_args.args[0][-1], revision + ':' + path)
            for invalid_path, invalid_revision in [(path, 'b' * 40), ('../secret.png', revision), ('Game.Godot/Assets/missing.png', revision)]:
                with self.assertRaises(ValueError):
                    image_bytes(root, invalid_path, invalid_revision)


if __name__ == '__main__':
    unittest.main()
