"""R10 four-epoch cache fixtures; no models or real native acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_execution_transition as transition

spec = importlib.util.spec_from_file_location("epoch_fixture_v2", Path(__file__).with_name("test_b_route_source_epoch_v2.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class SourceEpochScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SourceEpochV2Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.r10root = f.f.root / "r10"
        self.r10root.mkdir()
        self.r10commit = "a" * 40
        f.manifests[str(self.r10root)] = f.f.envelope(self.r10root, self.r10commit)["current_tracked_sources"]
        f.commits[str(self.r10root)] = self.r10commit
        self.r9 = deepcopy(f.r9)
        self.r9.update(active_elapsed_seconds=5398.0,
                       b_route_partial_generation_recovery={"fixture": "exact old R9 reference"},
                       b_route_input_compact_policy="fixture-input-v2")
        f.f.put(f.f.run / "run.json", self.r9)
        self.r10 = f.activate(self.r9, self.r10root, self.r10commit, f.r9root, f.r9commit)
        f.native.reset_mock()
        f.source_calls.clear()

    def test_four_epoch_archive_preserves_actual_sources_and_eight_paid_calls(self):
        f = self.fixture
        before = {p: p.read_bytes() for p in (f.f.run / "recovery").rglob("*.json")}
        with transition._verification_transaction():
            self.assertEqual(transition.historical_state(f.f.root, self.r10,
                self.r9["b_route_execution_transition"]["transition_digest"]), self.r9)
            self.assertEqual(transition.source_state_for_proof(f.f.root, self.r10, f.f.proof)
                             ["b_route_execution_transition"], f.f.prior)
            for index in (6, 7):
                self.assertEqual(transition.source_state_for_materials(f.f.root, self.r10,
                    {"execution_source_transition": f.r8["b_route_execution_transition"]["transition_digest"]},
                    f.f.bindings[index]), f.r8)
        self.assertEqual(f.native.call_count, 1)
        self.assertEqual(self.r10["capability_selection"], self.r9["capability_selection"])
        self.assertEqual(self.r10["active_elapsed_seconds"], 5398.0)
        self.assertEqual(self.r10["b_route_partial_generation_recovery"], self.r9["b_route_partial_generation_recovery"])
        self.assertEqual(len(self.r10["b_route_execution_history"]), 3)
        self.assertEqual(before, {p: p.read_bytes() for p in (f.f.run / "recovery").rglob("*.json")})

    def test_identical_frames_and_sources_scan_once_then_fresh_at_closure(self):
        f = self.fixture
        with patch.object(transition, "_collect", wraps=transition._collect) as collected:
            with transition._verification_transaction():
                first = transition.load_prepared(f.f.root, self.r10)
                self.assertEqual(collected.call_count, 4)
                second = transition.load_prepared(f.f.root, deepcopy(self.r10))
                self.assertEqual(first, second)
                self.assertEqual(collected.call_count, 4)
                self.assertEqual(f.native.call_count, 0)  # Fresh witness belongs to closure.
                for root in f.manifests:
                    self.assertEqual(f.source_calls.count(root), 1)
                changed = deepcopy(self.r10)
                changed["active_elapsed_seconds"] += 1
                transition.validate_transition(f.f.root, changed)
                self.assertEqual(collected.call_count, 5)  # Whole state is part of the frame key.
            self.assertEqual(f.native.call_count, 1)
            for root in f.manifests:
                self.assertEqual(f.source_calls.count(root), 2)
            transition.validate_transition(f.f.root, self.r10)
            self.assertEqual(collected.call_count, 9)  # Independent call never reuses frames.
            self.assertEqual(f.native.call_count, 2)
            for root in f.manifests:
                self.assertEqual(f.source_calls.count(root), 4)
        self.assertIsNone(transition._ACTIVE_VERIFICATION.get())

    def test_raw_artifact_mutation_rejects_cached_frame_and_late_closure(self):
        f = self.fixture
        binding = f.f.run / f.r8["capability_selection"]["calls"][7]["request_identity"]["execution_binding_path"]
        original = binding.read_bytes()
        for when in ("cached_hit", "closure"):
            try:
                with self.subTest(when=when), self.assertRaisesRegex(transition.TransitionError, "historical_artifact"):
                    with transition._verification_transaction():
                        transition.validate_transition(f.f.root, self.r10)
                        binding.write_bytes(original + b"\n")
                        if when == "cached_hit":
                            transition.validate_transition(f.f.root, self.r10)
            finally:
                binding.write_bytes(original)
            self.assertIsNone(transition._ACTIVE_VERIFICATION.get())

    def test_source_mutation_at_closure_and_next_call_cannot_reuse_snapshot(self):
        f = self.fixture
        with self.assertRaisesRegex(transition.TransitionError, "source_changed_during_transaction"):
            with transition._verification_transaction():
                transition.validate_transition(f.f.root, self.r10)
                transition.validate_transition(f.f.root, self.r10)
                f.manifests[str(self.r10root)]["runtime.py"]["raw_digest"] = "changed"
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(f.f.root, self.r10)
        self.assertIsNone(transition._ACTIVE_VERIFICATION.get())

    def test_mixed_artifact_root_prepared_raw_and_partial_reference_fail_closed(self):
        f = self.fixture
        foreign = f.f.root / "foreign"
        prepared = foreign / self.r10["planning_runtime"]["prepared_ref"]
        prepared.parent.mkdir(parents=True)
        prepared.write_bytes((f.f.root / self.r10["planning_runtime"]["prepared_ref"]).read_bytes())
        with self.assertRaises(transition.TransitionError):
            with transition._verification_transaction():
                transition.validate_transition(f.f.root, self.r10)
                transition.validate_transition(foreign, self.r10)
        changed = deepcopy(self.r10)
        changed["b_route_partial_generation_recovery"] = {"fixture": "replacement"}
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(f.f.root, changed)
        raw_path = f.f.root / self.r10["planning_runtime"]["prepared_ref"]
        original = raw_path.read_bytes()
        try:
            with self.assertRaises(transition.TransitionError):
                with transition._verification_transaction():
                    transition.validate_transition(f.f.root, self.r10)
                    raw_path.write_bytes(original + b"\n")
                    transition.validate_transition(f.f.root, self.r10)
        finally:
            raw_path.write_bytes(original)
        self.assertIsNone(transition._ACTIVE_VERIFICATION.get())


if __name__ == "__main__":
    unittest.main()
