from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python._semantic_topology import (
    TOPOLOGY_ARTIFACTS,
    attach_scene_design_trace,
    load_topology_from_snapshot,
    load_workspace_topology,
)


class FakeSnapshot:
    authority_ref = "refs/heads/main"

    def __init__(self, docs, commit="a" * 40):
        self.docs = {
            path: value if isinstance(value, str) else json.dumps(value)
            for path, value in docs.items()
        }
        self.paths = tuple(sorted(self.docs))
        self.commit = commit

    def read_text(self, path):
        return self.docs[path]

    def digest(self, path):
        return hashlib.sha256(self.docs[path].encode("utf-8")).hexdigest()


def valid_docs(revision="a" * 40):
    docs = {
        TOPOLOGY_ARTIFACTS["source_blocks"]: {"blocks": [
            {"block_id": "SB-1", "source_path": "docs/gdd/a.md",
             "line_start": 1, "line_end": 2}
        ]},
        TOPOLOGY_ARTIFACTS["requirements"]: {"requirements": [
            {"requirement_id": "FR-1", "source_block_ids": ["SB-1"],
             "delivery_relevant": True, "status": "active",
             "capability_ids": ["CAP-1"]}
        ]},
        TOPOLOGY_ARTIFACTS["capabilities"]: {"capabilities": [
            {"capability_id": "CAP-1", "requirement_ids": ["FR-1"]}
        ]},
        TOPOLOGY_ARTIFACTS["edges"]: {"edges": [
            {"source_type": "requirement", "source_id": "FR-1",
             "target_type": "task", "target_id": "7",
             "relation": "implemented_by"}
        ]},
    }
    docs[TOPOLOGY_ARTIFACTS["manifest"]] = {
        "schema_version": "newrouge.semantic-topology-manifest.v1",
        "source_revision": revision,
        "schema_revision": "v1",
        "generator_revision": "test",
        "artifacts": {},
    }
    return docs


class SemanticTopologyTests(unittest.TestCase):
    def test_missing_artifacts_are_explicit_legacy_unmapped(self):
        view = load_topology_from_snapshot(FakeSnapshot({}), [])
        self.assertFalse(view["available"])
        self.assertEqual("legacy_unmapped", view["status"])

    def test_valid_topology_is_revision_bound_and_traces_tasks(self):
        details = [{
            "task": {"id": 7, "title": "Do it", "status": "pending"},
            "godot": {
                "status": "static_attached",
                "scenes": [{"scene": "Game.Godot/Scenes/Main.tscn"}],
            },
        }]
        view = load_topology_from_snapshot(FakeSnapshot(valid_docs()), details)
        self.assertTrue(view["available"])
        self.assertTrue(view["fresh"])
        self.assertEqual(["FR-1"], view["task_trace"]["7"]["requirements"])
        graph = {"nodes": {"Game.Godot/Scenes/Main.tscn": {}}, "edges": []}
        attach_scene_design_trace(graph, view, details)
        trace = graph["design_trace"]["Game.Godot/Scenes/Main.tscn"]
        self.assertEqual(["FR-1"], trace["requirements"])
        self.assertEqual("navigation_only", trace["semantic_claim"])

    def test_revision_mismatch_is_stale_not_rewritten(self):
        view = load_topology_from_snapshot(FakeSnapshot(valid_docs("b" * 40)), [])
        self.assertFalse(view["fresh"])
        self.assertTrue(any(
            x["kind"] == "source_revision_mismatch" for x in view["problems"]
        ))

    def test_workspace_preview_requires_workspace_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "logs/ci/project-health-knowledge/topology/workspace-latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "available": True,
                "identity": {"kind": "main", "revision": "x"},
            }), encoding="utf-8")
            view = load_workspace_topology(root)
            self.assertFalse(view["available"])
            self.assertEqual("workspace", view["identity"]["kind"])


if __name__ == "__main__":
    unittest.main()
