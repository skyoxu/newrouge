"""Synthetic adoption/reader seam only; never actual native qualification."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
import importlib.util
import os
from pathlib import Path
import py_compile
import shutil
import tempfile
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch
import uuid

import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_planning_input as planning
import _b_route_planning_runtime as runtime
from _planning_skill_common import canonical_sha


class AdoptionR10CaptureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / ("nr11-" + uuid.uuid4().hex[:10])
        self.root.mkdir()
        self.addCleanup(self.cleanup)
        self.flags = {"activity": False, "coordinator": False}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("No native subprocess in capture fixture")))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("No model/network in capture fixture")))

    def cleanup(self):
        target = self.root.resolve()
        if target.parent != Path(tempfile.gettempdir()).resolve() or not target.name.startswith("nr11-"):
            raise AssertionError("Fixture cleanup escaped its owned temp root")
        shutil.rmtree(target)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if type(value) is bytes else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return path

    def reference(self, name):
        raw = (self.root / name).read_bytes()
        return {"path": name, "schema_version": codec.strict_json_loads(raw)["schema_version"], "raw_digest": codec.raw_digest(raw)}

    def fixture(self):
        self.run = runtime.run_location(self.root, "capabilities", "fixture")
        self.run.mkdir(parents=True)
        run_ref = self.run.relative_to(self.root).as_posix()
        prepared_ref = "logs/ci/b-route-planning-input/fixture/prepared.json"
        dependency = self.put("evidence/source.txt", b"Full original source.\r\n")
        prepared = {"input_identity": "sha256:" + "1" * 64, "resume_ref": prepared_ref,
                    "inputs": {"dependencies": {"files": {"evidence/source.txt": codec.raw_digest(dependency.read_bytes()),
                                                          "evidence/absent-original.txt": None}}, "complete": [True, 1, "原文"]}}
        self.put(prepared_ref, prepared)
        admission = {"schema_version": runtime.PROOF, "original": "four-epoch synthetic proof"}
        proof_ref = run_ref + "/selected-admission.json"
        self.put(proof_ref, admission)
        handoff = {"schema_version": "newrouge.b-route-planning-handoff.v1", "original_prepared_ref": prepared_ref,
                   "proposal": {"content": {"complete": [True, 1, "unchanged"]}}, "admission": admission,
                   "unknown_original": {"must": "survive"}}
        self.put(run_ref + "/handoff.json", handoff)
        self.put(run_ref + "/candidates/candidate-2/scope-1/capability-append/p1/c5/paid.json", {"original": True})
        desc = {"schema_version": runtime.PROFILE, "profile": "3b-capabilities-v1", "planner": "capabilities",
                "prepared_ref": prepared_ref, "input_identity": prepared["input_identity"],
                "frozen_sha256": canonical_sha(prepared), "rules": {}, "limits": runtime.profile_limits("3b-capabilities-v1")}
        store = self.root / "logs/ci/mvg-recovery"
        store.mkdir(parents=True)
        state = {"schema_version": runtime.CONTINUATION_RUN, "run_id": "fixture", "input_stage": "3b",
                 "selection_status": "selected", "planning_runtime": desc, "runtime_identity": canonical_sha(desc),
                 "analysis_identity_sha256": prepared["input_identity"], "recovery": {"store": str(store)},
                 "b_route_execution_transition": {"four_epochs": "synthetic; reader owns exact validation"},
                 "b_route_partial_generation_recovery": {"retained": True}, "b_route_input_path_recovery": {"namespace": "p1"},
                 "selected_admission_review": {"path": proof_ref}}
        state_path = self.put(run_ref + "/run.json", state)
        protection_ref = "evidence/protection/protection.json"
        self.put(protection_ref, {"schema_version": "synthetic.protection.v1", "tasks": []})
        material = {"planner": "capabilities", "run_id": "fixture", "handoff_ref": self.reference(run_ref + "/handoff.json"),
                    "protection_ref": self.reference(protection_ref), "authority_refs": [], "lineage_refs": []}
        source = self.put("synthetic-frozen-source.py", b"# own fixture; never executed\n")
        capture = {"schema_version": "synthetic.frozen-native-capture.v1", "handoff": deepcopy(handoff), "prepared": deepcopy(prepared),
                   "run_identity": {"path": str(state_path), "raw_digest": codec.raw_digest(state_path.read_bytes()),
                                    "canonical_digest": codec.canonical_digest(state), "byte_count": len(state_path.read_bytes())},
                   "source_identity": {"source_root": str(self.root), "source_commit": "f" * 40,
                                       "reader_path": str(source), "reader_raw_digest": codec.raw_digest(source.read_bytes())},
                   "files": {str(source): codec.raw_digest(source.read_bytes()), str(self.root / "absent-eligibility"): None},
                   "directories": {str(source.parent): sorted(path.name for path in source.parent.iterdir())},
                   "result_digest": "sha256:" + "c" * 64}
        return material, self.reference(proof_ref), state_path.read_bytes(), capture

    def seams(self, capture):
        import _b_route_protection as protection
        import _mvg_capability_checkpoint as checkpoint
        import _mvg_capability_recovery as recovery
        stack = ExitStack()
        @contextmanager
        def activity(*_args):
            self.assertFalse(self.flags["activity"])
            self.flags["activity"] = True
            try:
                yield
            finally:
                self.flags["activity"] = False
        @contextmanager
        def coordinator(*_args):
            self.assertTrue(self.flags["activity"])
            self.flags["coordinator"] = True
            try:
                yield
            finally:
                self.flags["coordinator"] = False
        def capture_native(*args, **kwargs):
            self.assertTrue(all(self.flags.values()), "Fresh capture is inside both original locks")
            return capture
        stack.enter_context(patch.object(recovery, "operation_lock", side_effect=activity))
        stack.enter_context(patch.object(checkpoint, "coordinator_lock", side_effect=coordinator))
        called, closing = Mock(side_effect=capture_native), Mock()
        source_digest = capture["source_identity"]["reader_raw_digest"]
        @contextmanager
        def reader():
            yield SimpleNamespace(capture_completed=called, verify_capture=closing, _adoption_source_digest=source_digest)
        stack.enter_context(patch.object(adoption, "_frozen_native_reader", side_effect=reader))
        stack.enter_context(patch.object(protection, "verify_protection", return_value={"ok": True, "capture_complete": True}))
        stack.enter_context(patch.object(runtime, "validate_input", side_effect=AssertionError("No R11 native validation of continued proof")))
        stack.enter_context(patch.object(runtime, "handoff", side_effect=AssertionError("No current-rule handoff relabel")))
        stack.enter_context(patch.object(planning, "load_prepared", side_effect=AssertionError("No current-rule prepared reassembly")))
        return stack, called, closing

    def test_continued_capture_uses_original_reader_under_both_locks_and_keeps_complete_values(self):
        material, proof_ref, state_raw, capture = self.fixture()
        stack, native, closing = self.seams(capture)
        with stack:
            for _ in range(2):
                with adoption.capture_completed(self.root, material, proof_ref) as snapshot:
                    self.assertTrue(self.flags["activity"])
                    self.assertFalse(self.flags["coordinator"])
                    self.assertEqual(snapshot.handoff, capture["handoff"])
                    self.assertEqual(snapshot.prepared, capture["prepared"])
                    self.assertIsNot(snapshot.prepared, capture["prepared"])
                    self.assertIs(snapshot.native_capture, capture)
                    self.assertIsNone(snapshot.files["evidence/absent-original.txt"])
                    snapshot.verify()
                self.assertFalse(any(self.flags.values()))
            self.assertEqual(native.call_count, 2, "Each public capture performs fresh reader work")
            native.assert_called_with(self.root, planner="capabilities", run_id="fixture", state_raw=state_raw,
                                      expected_handoff_ref=material["handoff_ref"])
            self.assertEqual(closing.call_count, 4)

    def test_current_supplied_handoff_and_closing_source_drift_still_fail_closed(self):
        material, proof_ref, _state_raw, capture = self.fixture()
        stack, _native, closing = self.seams(capture)
        with stack:
            with adoption.capture_completed(self.root, material, proof_ref) as snapshot:
                closing.side_effect = ValueError("external source currentness changed")
                with self.assertRaisesRegex(ValueError, "external source currentness changed"):
                    snapshot.verify()
            closing.side_effect = None
            name = material["handoff_ref"]["path"]
            self.put(name, {**capture["handoff"], "unknown_original": "replacement"})
            changed_material = {**material, "handoff_ref": self.reference(name)}
            with self.assertRaises(codec.CodecError):
                with adoption.capture_completed(self.root, changed_material, proof_ref):
                    self.fail("A valid self-reported handoff cannot replace native output")

    def test_host_subject_binds_external_native_closure_and_rejects_unknown_capture_fields(self):
        material, _proof_ref, _state_raw, capture = self.fixture()
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture, snapshot.handoff = capture, capture["handoff"]
        snapshot.prepared, snapshot.protection = capture["prepared"], {"tasks": []}
        request = {"operation_id": "fixture", "material": {**material, "identity_alignment": {}}, "review_ref": {}}
        frozen = {"scope_ids": ["plan:fixture"], "allocations": {"plan_id": "fixture"}, "targets": []}
        with patch.object(review, "policy_identity", return_value="synthetic-policy"):
            subject = review.make_subject(snapshot, request, frozen)
            self.assertEqual(subject["native_capture"]["files"], capture["files"])
            self.assertEqual(subject["native_capture"]["directories"], capture["directories"])
            self.assertEqual(subject["native_capture"]["run_identity"], capture["run_identity"])
            original = deepcopy(subject)
            capture["source_identity"]["source_commit"] = "e" * 40
            self.assertNotEqual(review.make_subject(snapshot, request, frozen), original)
            path = review.location("fixture") + "/subject.json"
            self.put(path, original)
            self.assertEqual(review.read_subject(self.root, "fixture"), original)
            original["native_capture"]["caller_approved"] = True
            self.put(path, original)
            with self.assertRaises(codec.CodecError):
                review.read_subject(self.root, "fixture")

    def test_parent_reader_executes_checked_source_despite_poisoned_pyc_and_module_cache(self):
        source = self.put("scripts/python/_b_route_frozen_native_reader.py", b"VALUE = 'poisoned-cache'\n")
        py_compile.compile(str(source), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        self.assertTrue(Path(importlib.util.cache_from_source(str(source))).is_file())
        trusted = b"VALUE = 'checked-source'\n"
        source.write_bytes(trusted)
        cached = ModuleType('_b_route_frozen_native_reader')
        cached.VALUE = 'poisoned-sys-modules'
        with patch.object(adoption, '__file__', str(self.root / "scripts/python/_b_route_adoption.py")), \
                patch.dict(sys.modules, {'_b_route_frozen_native_reader': cached}):
            with adoption._frozen_native_reader() as reader:
                self.assertEqual(reader.VALUE, 'checked-source')
                self.assertEqual(reader._adoption_source_digest, codec.raw_digest(trusted))
                self.assertIs(sys.modules['_b_route_frozen_native_reader'], cached)

    def test_parent_reader_closes_source_drift_and_unbound_capture_before_return(self):
        source = self.put("scripts/python/_b_route_frozen_native_reader.py", b"VALUE = 'checked'\n")
        with patch.object(adoption, '__file__', str(self.root / "scripts/python/_b_route_adoption.py")):
            with self.assertRaises(codec.CodecError):
                with adoption._frozen_native_reader():
                    source.write_bytes(b"VALUE = 'changed'\n")
            with adoption._frozen_native_reader() as reader:
                with self.assertRaises(codec.CodecError):
                    adoption._reader_capture_source(reader, {'source_identity': {'reader_raw_digest': 'sha256:' + '0' * 64}})
            alias = self.root / "source-alias.py"
            os.link(source, alias)
            with self.assertRaises(codec.CodecError):
                with adoption._frozen_native_reader():
                    self.fail('An aliased source must not execute')

    def test_parent_checked_reader_loads_final_api_without_dispatch(self):
        with adoption._frozen_native_reader() as reader:
            source = Path(adoption.__file__).with_name('_b_route_frozen_native_reader.py')
            self.assertEqual(Path(reader.__file__), source)
            self.assertEqual(reader._adoption_source_digest, codec.raw_digest(source.read_bytes()))
            self.assertTrue(callable(reader.capture_completed))
            self.assertTrue(callable(reader.verify_capture))

    def test_review_policy_rehashes_reader_source_and_rejects_saved_previous_policy(self):
        before = review.policy_identity()
        subject = {'schema_version': review.SUBJECT, 'operation_id': 'fixture', 'request': {},
                   'policy_identity': before, 'preview': {}, 'native_content': {}, 'prepared': {},
                   'protection': {}, 'related_records': {}, 'task_definitions': {}, 'authority_files': [],
                   'target_before_files': [], 'affected_catalog': None, 'native_threads': [], 'native_turns': []}
        self.put(review.location('fixture') + '/subject.json', subject)
        self.assertEqual(review.read_subject(self.root, 'fixture'), subject)
        source = Path(review.__file__).with_name('_b_route_frozen_native_reader.py')
        original_read = Path.read_bytes
        def edited_reader(path):
            raw = original_read(path)
            return raw + b'\n# synthetic source-policy delta\n' if path == source else raw
        with patch.object(Path, 'read_bytes', autospec=True, side_effect=edited_reader):
            self.assertNotEqual(review.policy_identity(), before)
            with self.assertRaises(codec.CodecError):
                review.read_subject(self.root, 'fixture')


if __name__ == "__main__":
    unittest.main()
