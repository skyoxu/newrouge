#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import json
import sys
import tempfile
import types
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


dev_cli = _load_module("dev_cli_module_generate_image", "scripts/python/dev_cli.py")


class DevCliGenerateImageTests(unittest.TestCase):
    def test_generate_image_command_writes_png_and_manifest(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\nfake-png"
        response = types.SimpleNamespace(
            created=1_747_000_000,
            data=[
                types.SimpleNamespace(
                    b64_json=base64.b64encode(png_bytes).decode("ascii"),
                    revised_prompt="refined prompt",
                    url=None,
                )
            ],
        )

        fake_client = types.SimpleNamespace(
            images=types.SimpleNamespace(generate=mock.Mock(return_value=response))
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            prompt_file = tmp_path / "prompt.txt"
            prompt_file.write_text("draw a battle arena", encoding="utf-8")
            output_path = tmp_path / "arena.png"
            manifest_path = tmp_path / "arena.manifest.json"

            with mock.patch.dict("os.environ", {"AIARTMIRROR_API_KEY": "test-key"}, clear=False), \
                mock.patch.object(dev_cli, "_create_openai_image_client", return_value=fake_client):
                rc = dev_cli.main(
                    [
                        "generate-image",
                        "--prompt-file",
                        str(prompt_file),
                        "--out",
                        str(output_path),
                        "--manifest-out",
                        str(manifest_path),
                        "--model",
                        "gpt-image-2",
                        "--size",
                        "1024x1024",
                        "--quality",
                        "high",
                        "--background",
                        "transparent",
                        "--output-format",
                        "png",
                        "--response-format",
                        "b64_json",
                    ]
                )

            self.assertEqual(0, rc)
            self.assertEqual(png_bytes, output_path.read_bytes())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("gpt-image-2", manifest["model"])
            self.assertEqual("draw a battle arena", manifest["prompt"])
            self.assertEqual("refined prompt", manifest["revised_prompt"])
            self.assertEqual("transparent", manifest["background"])
            self.assertEqual("png", manifest["output_format"])
            fake_client.images.generate.assert_called_once()
            kwargs = fake_client.images.generate.call_args.kwargs
            self.assertEqual("gpt-image-2", kwargs["model"])
            self.assertEqual("draw a battle arena", kwargs["prompt"])
            self.assertEqual("1024x1024", kwargs["size"])
            self.assertEqual("high", kwargs["quality"])
            self.assertEqual("transparent", kwargs["background"])
            self.assertEqual("png", kwargs["output_format"])

    def test_generate_image_command_supports_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_path = tmp_path / "dry-run.png"
            manifest_path = tmp_path / "dry-run.manifest.json"

            with mock.patch.object(dev_cli, "_create_openai_image_client") as create_client:
                rc = dev_cli.main(
                    [
                        "generate-image",
                        "--prompt",
                        "draw a prop sheet",
                        "--out",
                        str(output_path),
                        "--manifest-out",
                        str(manifest_path),
                        "--dry-run",
                    ]
                )

            self.assertEqual(0, rc)
            create_client.assert_not_called()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["dry_run"])
            self.assertEqual("draw a prop sheet", manifest["prompt"])
            self.assertEqual(str(output_path), manifest["out"])
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
