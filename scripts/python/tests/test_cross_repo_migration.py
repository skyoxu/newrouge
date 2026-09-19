"""Regression tests for repository-neutral cross-repository migration reconciliation."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_cross_repo_migration as migration


class CrossRepoMigrationReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for rel, text in [
            ("shared.py", "print('shared')\n"),
            ("adapted.py", "print('adapted')\n"),
            ("validation.py", "print('validation')\n"),
        ]:
            path = self.root / rel
            path.write_text(text, encoding="utf-8")
        changed = ["shared.py", "source-business.cs", "source-adapted.py"]
        self.manifest = {
            "schema_version": migration.SCHEMA_VERSION,
            "source": {
                "repo": "owner/source",
                "pr": 7,
                "merge_commit": "a" * 40,
                "changed_file_count": len(changed),
                "changed_files": changed,
                "changed_files_sha256": migration._changed_files_sha256(changed),
            },
            "target": {"repo": "owner/target"},
            "entries": [
                {
                    "source_path": "shared.py",
                    "classification": "copy_exact",
                    "target_paths": ["shared.py"],
                    "source_blob_sha": migration._git_blob_sha(self.root / "shared.py", self.root),
                    "rationale": "shared control plane",
                },
                {
                    "source_path": "source-business.cs",
                    "classification": "business_only_drop",
                    "rationale": "source-only business behavior",
                },
                {
                    "source_path": "source-adapted.py",
                    "classification": "adapt_target_native",
                    "target_paths": ["adapted.py"],
                    "validation_paths": ["validation.py"],
                    "rationale": "target-native equivalent",
                },
            ],
        }

    def test_valid_manifest_accepts_exact_adapted_and_dropped_files(self):
        self.assertEqual([], migration.validate_manifest(self.manifest, self.root))

    def test_changed_file_inventory_digest_is_optional_but_checked_when_present(self):
        doc = copy.deepcopy(self.manifest)
        doc["source"].pop("changed_files_sha256")
        self.assertEqual([], migration.validate_manifest(doc, self.root))
        doc["source"]["changed_files_sha256"] = "0" * 64
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("changed_files_sha256" in item for item in errors))

    def test_unclassified_source_file_is_rejected(self):
        doc = copy.deepcopy(self.manifest)
        doc["entries"].pop()
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("unclassified source files" in item for item in errors))
        self.assertTrue(any("entry count" in item for item in errors))

    def test_copy_exact_drift_is_rejected(self):
        (self.root / "shared.py").write_text("print('drift')\n", encoding="utf-8")
        errors = migration.validate_manifest(self.manifest, self.root)
        self.assertTrue(any("copy_exact drift" in item for item in errors))

    def test_copy_exact_target_must_be_a_file(self):
        directory = self.root / "shared-dir"
        directory.mkdir()
        doc = copy.deepcopy(self.manifest)
        doc["entries"][0]["target_paths"] = ["shared-dir"]
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("copy_exact target must be a file" in item for item in errors))

    def test_source_repo_and_changed_paths_must_be_safe(self):
        doc = copy.deepcopy(self.manifest)
        doc["source"]["repo"] = "owner/source?ref=evil"
        doc["source"]["changed_files"][0] = "../shared.py"
        doc["source"]["changed_files_sha256"] = migration._changed_files_sha256(doc["source"]["changed_files"])
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("source.repo must be a safe owner/name" in item for item in errors))
        self.assertTrue(any("unsafe source changed-file path" in item for item in errors))

    def test_dot_segment_repository_names_are_rejected(self):
        for repo_name in ["../source", "owner/..", "./source", "owner/."]:
            with self.subTest(repo_name=repo_name):
                doc = copy.deepcopy(self.manifest)
                doc["source"]["repo"] = repo_name
                errors = migration.validate_manifest(doc, self.root)
                self.assertTrue(any("source.repo must be a safe owner/name" in item for item in errors))

    def test_windows_absolute_target_path_is_rejected(self):
        doc = copy.deepcopy(self.manifest)
        doc["entries"][0]["target_paths"] = ["C:/shared.py"]
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("unsafe repository path" in item for item in errors))

    def test_adapted_entry_requires_validation_and_drop_cannot_target(self):
        doc = copy.deepcopy(self.manifest)
        doc["entries"][1]["target_paths"] = ["adapted.py"]
        doc["entries"][2]["validation_paths"] = []
        errors = migration.validate_manifest(doc, self.root)
        self.assertTrue(any("business_only_drop must not declare target_paths" in item for item in errors))
        self.assertTrue(any("adapt_target_native requires validation_paths" in item for item in errors))

    def test_remote_source_verification_rejects_manifest_inventory_drift(self):
        remote = {
            "merge_commit": "a" * 40,
            "changed_files": ["shared.py", "source-business.cs", "source-adapted.py", "missed.py"],
        }
        with mock.patch.object(migration, "fetch_github_source_inventory", return_value=remote):
            errors = migration.verify_source_github(self.manifest)
        self.assertTrue(any("changed-file inventory mismatch" in item for item in errors))
        self.assertIn("missed.py", errors[0])

    def test_remote_source_verification_rejects_merge_commit_drift(self):
        remote = {
            "merge_commit": "b" * 40,
            "changed_files": list(self.manifest["source"]["changed_files"]),
        }
        with mock.patch.object(migration, "fetch_github_source_inventory", return_value=remote):
            errors = migration.verify_source_github(self.manifest)
        self.assertTrue(any("source merge commit mismatch" in item for item in errors))

    def test_no_manifests_is_skipped_unless_required(self):
        out = self.root / "summary.json"
        rc = migration.main(["--root", str(self.root), "--out", str(out)])
        self.assertEqual(0, rc)
        self.assertEqual("skipped", json.loads(out.read_text(encoding="utf-8"))["status"])

        required = self.root / "required.json"
        rc = migration.main([
            "--root", str(self.root),
            "--require-manifests",
            "--out", str(required),
        ])
        self.assertEqual(1, rc)
        self.assertEqual("failed", json.loads(required.read_text(encoding="utf-8"))["status"])


if __name__ == "__main__":
    unittest.main()
