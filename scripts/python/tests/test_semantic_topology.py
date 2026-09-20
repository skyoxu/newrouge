from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python._knowledge_catalog_builder import build_layers
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
    source_text = "Requirement text\n"
    source_sha = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    docs = {
        "docs/gdd/a.md": source_text,
        TOPOLOGY_ARTIFACTS["source_blocks"]: {"schema_version": "newrouge.source-blocks.v1", "blocks": [
            {"block_id": "SB-1", "source_path": "docs/gdd/a.md",
             "line_start": 1, "line_end": 1, "content_hash": "sha256:" + ("1" * 64),
             "source_sha256": source_sha}
        ]},
        TOPOLOGY_ARTIFACTS["requirements"]: {"schema_version": "newrouge.semantic-requirements.v1", "requirements": [
            {"requirement_id": "FR-1", "kind": "functional", "statement": "Requirement text",
             "source_block_ids": ["SB-1"], "delivery_relevant": True, "status": "active",
             "sink_policy": "task_or_global_constraint", "capability_ids": ["CAP-1"]}
        ]},
        TOPOLOGY_ARTIFACTS["capabilities"]: {"schema_version": "newrouge.capabilities.v1", "capabilities": [
            {"capability_id": "CAP-1", "title": "Test capability", "requirement_ids": ["FR-1"]}
        ]},
        TOPOLOGY_ARTIFACTS["edges"]: {"schema_version": "newrouge.topology-edges.v1", "edges": [
            {"source_type": "requirement", "source_id": "FR-1",
             "target_type": "task", "target_id": "7",
             "relation": "implemented_by"}
        ]},
    }
    artifacts = {}
    for key in ("source_blocks", "requirements", "capabilities", "edges"):
        artifact_path = TOPOLOGY_ARTIFACTS[key]
        raw = json.dumps(docs[artifact_path]).encode("utf-8")
        artifacts[artifact_path] = "sha256:" + hashlib.sha256(raw).hexdigest()
    docs[TOPOLOGY_ARTIFACTS["manifest"]] = {
        "schema_version": "newrouge.semantic-topology-manifest.v1",
        "source_revision": "source-set:test",
        "source_manifest_sha256": "sha256:" + ("0" * 64),
        "repository_revision": revision,
        "schema_revision": "v1",
        "generator_revision": "test",
        "artifacts": artifacts,
    }
    return docs


class SemanticTopologyTests(unittest.TestCase):
    def test_kcp_builder_classifies_topology_as_derived_planning_source(self):
        snapshot = FakeSnapshot({
            "docs/planning/semantic-topology/semantic-requirements.v1.json": {
                "requirements": [{"requirement_id": "FR-1"}]
            }
        })
        policies = {
            "policy_revision": "test",
            "policies": [{
                "consumer": "repository-session",
                "domains": ["game-design"],
                "statuses": ["active"],
                "visibility": ["active"],
                "exact_paths": [],
                "path_prefixes": ["docs/planning/semantic-topology/"],
            }],
        }
        _snapshot, catalog, projections = build_layers(snapshot, {"rules": []}, policies)
        self.assertEqual(1, len(catalog["modules"]))
        module = catalog["modules"][0]
        self.assertEqual("semantic-topology", module["kind"])
        self.assertEqual("derived-planning-topology", module["source_role"])
        eligible = projections["projections"][0]["eligible_module_ids"]
        self.assertEqual([module["module_id"]], eligible)

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

    def test_capability_without_delivery_sink_keeps_requirement_orphan(self):
        docs = valid_docs()
        docs[TOPOLOGY_ARTIFACTS["edges"]] = {"edges": [
            {"source_type": "requirement", "source_id": "FR-1",
             "target_type": "capability", "target_id": "CAP-1",
             "relation": "grouped_by"}
        ]}
        view = load_topology_from_snapshot(FakeSnapshot(docs), [])
        self.assertEqual(1, view["summary"]["orphan_requirements"])
        docs[TOPOLOGY_ARTIFACTS["edges"]]["edges"].append(
            {"source_type": "capability", "source_id": "CAP-1",
             "target_type": "task", "target_id": "7",
             "relation": "implemented_by"}
        )
        details = [{"task": {"id": 7, "status": "pending"}, "godot": {"scenes": []}}]
        view = load_topology_from_snapshot(FakeSnapshot(docs), details)
        self.assertEqual(0, view["summary"]["orphan_requirements"])

    def test_revision_mismatch_is_stale_not_rewritten(self):
        view = load_topology_from_snapshot(FakeSnapshot(valid_docs("b" * 40)), [])
        self.assertFalse(view["fresh"])
        self.assertTrue(any(
            x["kind"] == "repository_revision_mismatch" for x in view["problems"]
        ))

    def test_source_hash_drift_marks_topology_stale(self):
        docs = valid_docs()
        docs["docs/gdd/a.md"] = "Changed requirement text\n"
        view = load_topology_from_snapshot(FakeSnapshot(docs), [])
        self.assertFalse(view["fresh"])
        self.assertTrue(any(x["kind"] == "source_hash_mismatch" for x in view["problems"]))

    def test_task_semantic_refs_must_resolve(self):
        details = [{"task": {"id": 7, "status": "pending", "semantic_refs": ["FR-MISSING"]},
                    "godot": {"scenes": []}}]
        view = load_topology_from_snapshot(FakeSnapshot(valid_docs()), details)
        self.assertFalse(view["fresh"])
        self.assertTrue(any(x["kind"] == "invalid_task_semantic_ref" for x in view["problems"]))

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
