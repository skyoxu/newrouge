import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.impact_analyzer import SymbolIndex, TargetResolver, classify_risk, _edge, ImpactAnalyzer, load_frozen_binding
from scripts.python.impact_analyzer import ResolvedTarget


class ImpactAnalyzerUnitTests(unittest.TestCase):
    def test_symbol_extraction_and_unique_resolution(self):
        source = {
            "Game.Core/Contracts/Events/TestEvent.cs": "namespace Demo; public sealed record TestEvent(int Value);",
            "Game.Core/Services/TestService.cs": "using Demo; namespace Demo; public sealed class TestService { public void Publish(TestEvent value) {} }",
        }
        hashes = {path: hashlib.sha256(text.encode()).hexdigest() for path, text in source.items()}
        index = SymbolIndex(source, hashes)
        resolver = TargetResolver({"source_manifest": []}, source, hashes, {"schema_version":"newrouge.impact-target-aliases.v1","alias_table_revision":"x","aliases": {"event": {}, "contract": {}}})
        target = resolver.resolve({"type": "event", "id": "Demo.TestEvent"})
        self.assertEqual(target.canonical_path, "Game.Core/Contracts/Events/TestEvent.cs")
        self.assertEqual(target.kind, "event")
        self.assertTrue(index.find("event", "Demo.TestEvent"))

    def test_risk_contract_is_high(self):
        target = ResolvedTarget("contract", "Demo.Contract", "Game.Core/Contracts/Contract.cs", "a" * 64, "exact")
        risk, rules, _ = classify_risk(target, [])
        self.assertEqual(risk, "high")
        self.assertIn("contract-target", rules)

    def test_underqualified_event_and_method_rejected(self):
        source = {"Game.Core/Contracts/Events/TestEvent.cs": "namespace A; public sealed record TestEvent(int Value);"}
        hashes = {p: hashlib.sha256(t.encode()).hexdigest() for p, t in source.items()}
        resolver = TargetResolver({"source_manifest": []}, source, hashes, {"schema_version":"newrouge.impact-target-aliases.v1","alias_table_revision":"x","aliases":{"event":{},"contract":{}}})
        with self.assertRaises(Exception) as event_error:
            resolver.resolve({"type":"event","id":"TestEvent"})
        self.assertEqual(event_error.exception.code, "underqualified_target")
        with self.assertRaises(Exception) as method_error:
            resolver.resolve({"type":"method","id":"Publish"})
        self.assertEqual(method_error.exception.code, "underqualified_target")

    def test_edge_endpoint_and_anchor_validation(self):
        with self.assertRaises(Exception):
            _edge("event", "E", "class", "C", "consumes", "x.cs", "line:1-1", "a"*64)

    def test_ambiguous_target_is_rejected(self):
        source = {
            "Game.Core/Contracts/A.cs": "namespace Demo; public sealed record TestEvent;",
            "Game.Core/Contracts/B.cs": "namespace Demo; public sealed record TestEvent;",
        }
        hashes = {p: hashlib.sha256(t.encode()).hexdigest() for p, t in source.items()}
        resolver = TargetResolver({}, source, hashes, {"schema_version":"newrouge.impact-target-aliases.v1","alias_table_revision":"x","aliases":{"event":{},"contract":{}}})
        with self.assertRaises(Exception) as error:
            resolver.resolve({"type":"event","id":"Demo.TestEvent"})
        self.assertEqual(error.exception.code, "ambiguous_target")

    def test_index_unavailable_is_fail_closed(self):
        with self.assertRaises(Exception) as error:
            ImpactAnalyzer(Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "impact-index.v1.json", "a" * 40)
        self.assertEqual(error.exception.code, "missing_index")

    def test_kcp_binding_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.json"
            path.write_text(json.dumps({"schema_version":"newrouge.knowledge-frozen-context.v1", "freeze_state":"frozen", "snapshot":{"commit":"b"*40}, "consumer":"chapter6"}), encoding="utf-8")
            with self.assertRaises(Exception) as error:
                load_frozen_binding(Path(directory), "frozen.json", "a" * 40, "chapter6", "T1")
            self.assertEqual(error.exception.code, "revision_mismatch")


if __name__ == "__main__":
    unittest.main()
