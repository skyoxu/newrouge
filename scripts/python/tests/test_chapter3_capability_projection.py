"""Capability projection preserves reviewed memberships and rejects stale sources."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_frozen_task_projection as projection

class CapabilityProjectionTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Sample\n| T1 | Shared behavior |\n", encoding="utf-8")
        data = {
            "source_path": source.relative_to(root).as_posix(),
            "source_text_sha256": hashlib.sha256(source.read_text(encoding="utf-8").encode()).hexdigest(),
            "capabilities": [
                {"capability_id": "CAP-A", "title": "First", "description": "First scope", "included_task_ids": [1]},
                {"capability_id": "CAP-B", "title": "Second", "description": "Second scope", "included_task_ids": [1]},
            ],
        }
        path = root / "docs/planning/semantic-topology/capability-review.v1.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return source, path, data

    def project(self, root, ids):
        function = getattr(projection, "reviewed_capabilities", None)
        self.assertTrue(callable(function), "Reviewed capability input must be consumed without hardcoded task bands")
        return function(root, ids)

    def test_cross_domain_membership_survives_projection_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            first = self.project(root, ["FR-T0001"])
            self.assertEqual(["CAP-A", "CAP-B"], [r["capability_id"] for r in first])
            self.assertTrue(all(r["requirement_ids"] == ["FR-T0001"] for r in first))
            self.assertEqual(first, self.project(root, ["FR-T0001"]))

    def test_source_drift_requires_new_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, _, _ = self.fixture(root)
            source.write_text("Changed scope", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source"):
                self.project(root, ["FR-T0001"])

    def test_missing_or_inactive_task_membership_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path, data = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "coverage"):
                self.project(root, ["FR-T0001", "NFR-T0002"])
            data["capabilities"][0]["included_task_ids"].append(117)
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage"):
                self.project(root, ["FR-T0001"])

if __name__ == "__main__":
    unittest.main()
