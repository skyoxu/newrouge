"""Finite R22 profile boundaries; all artifacts and authority are synthetic.

These tests do not qualify m4 or Story 2.5/2.6. Native orchestration is mocked.
Selected boundary tests compile the exact pinned R22 selector owner with owned
codec/source adapters, then call its unchanged functions over toy TEMP files.
No model, native child, Git, describe process or actual run is used.
"""
from contextlib import ExitStack, contextmanager, nullcontext
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_frozen_native_reader as reader
import _b_route_adoption as adoption
import _b_route_adoption_review as adoption_review
import _b_route_operation_scope as operation_scope
import _planning_apply_journal as journal

_PRODUCER = Path(__file__).resolve().parents[4] / "r22/scripts/python/_b_route_selector_recovery.py"
_PRODUCER_SHA256 = "34100f801338a523c0bcdb1a38222d8c8d8afd4f350911d26c0d3538bd7cc695"


class FrozenNativeReaderR22Tests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(os.environ.get('FROZEN_READER_TEST_TEMP',
            r"C:\Windows\TEMP" if os.name == "nt" else "/tmp")).resolve()
        self.task = self.base / ("a22-" + uuid.uuid4().hex[:10])
        self.task.mkdir()
        self.addCleanup(self.cleanup_owned)
        self.root = self.task / "artifact"
        self.root.mkdir()
        for name in ("r5", "r7", "r8", "r9", "r10", "r19", "r22"):
            (self.task / name / "scripts/python").mkdir(parents=True)
        self.r10, self.r19, self.r22 = (self.task / name for name in ("r10", "r19", "r22"))
        self.stack.enter_context(patch.multiple(reader, TASK_ROOT=self.task, SOURCE_ROOT=self.r10))
        self.stack.enter_context(patch.object(reader, "_authenticated_reader_raw_digest",
            reader.digest(reader.READER.read_bytes()), create=True))
        self.stack.enter_context(patch.object(reader, "_dependencies", return_value=[]))
        self.audit = reader._Audit([self.task])
        self.prepared = {"input_identity": "SYNTHETIC-NOT-QUALIFICATION", "inputs": {"dependencies": {
            "files": {"input.txt": reader.digest(b"toy input"), "absent.txt": None},
            "globs": [{"patterns": ["business/*.md"], "result": []}]}}}
        self.write_bytes(self.root / "input.txt", b"toy input")
        (self.root / "business").mkdir()
        self.run = self.root / "logs/ci/mvg-planning/m4"

    def cleanup_owned(self):
        result = getattr(getattr(self, "_outcome", None), "result", None)
        if result is not None and any(test is self or getattr(test, "test_case", None) is self
                                      for test, _ in result.errors + result.failures):
            return
        if (self.task.resolve().parent != self.base.resolve() or not self.task.name.startswith("a22-")
                or self.task.is_symlink()):
            raise AssertionError("Synthetic R22 fixture escaped owned TEMP root")
        shutil.rmtree(self.task)

    def write_bytes(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def put(self, path, value):
        self.write_bytes(path, reader.canonical(value))

    def reference(self, schema, namespace):
        return {"schema_version": schema, "record_ref": "logs/ci/mvg-planning/m4/recovery/" + namespace + "/record.json",
                "record_digest": "sha256:" + "1" * 64, "artifact_root": str(self.root)}

    def fixture(self):
        original = {"current_source_root": str(self.r10), "current_commit": reader.SOURCE_COMMIT,
                    "original_source_root": str(self.task / "r5"),
                    "original_commit": reader._source_commits()[str(self.task / "r5")]}
        prior = {**original, "schema_version": reader.R19_EPOCH, "current_source_root": str(self.r19),
                 "current_commit": reader.R19_SOURCE_COMMIT, "prior_transition": deepcopy(original)}
        frame = {**original, "schema_version": reader.R22_EPOCH, "current_source_root": str(self.r22),
                 "current_commit": reader.R22_SOURCE_COMMIT, "prior_transition": prior}
        state = {"schema_version": "newrouge.b-route-planning-run.v2", "input_stage": "3b",
            "selection_status": "selected", "run_id": "m4", "b_route_execution_transition": frame,
            "b_route_execution_history": {"synthetic-r19": deepcopy(prior)},
            "b_route_selector_recovery": self.reference(reader.R22_RECOVERY, "s1"),
            "b_route_mvg_synthesis_recovery": self.reference(reader.R19_RECOVERY, "m1"),
            "planning_runtime": {"planner": "mvg", "input_identity": self.prepared["input_identity"],
                "frozen_sha256": reader.digest(reader.canonical(self.prepared)), "prepared_ref": "prepared/input.json"},
            "runner_configuration": {"backend": "isolated-runner", "backend_info": {"requested_reasoning_effort": "high"},
                "runner": str(self.task / "r5/scripts/python/codex_isolated_model_runner.py")},
            "capability_selection": {"total_invocations": 13, "calls": [{"number": number,
                "request_identity": {"execution_binding_path": "bindings/" + str(number) + ".json"},
                "outcome": {"status": "completed"}} for number in range(1, 14)],
                "selected": [{"admissions": {"candidate-" + str(i): {"synthetic": True} for i in range(1, 4)}}]}}
        handoff = {"schema_version": "newrouge.b-route-planning-handoff.v1", "synthetic": True}
        for namespace in ("m1", "s1"):
            for name in ("record.json", "claim.json", "committed.json", "intent.json"):
                self.put(self.run / "recovery" / namespace / name, {"synthetic": name})
        self.put(self.run / "run.json", state)
        self.put(self.run / "handoff.json", handoff)
        self.put(self.root / "prepared/input.json", self.prepared)
        for row in state["capability_selection"]["calls"]:
            self.put(self.run / row["request_identity"]["execution_binding_path"],
                     {"runner_info": {"requested_reasoning_effort": "high"}})
        for source in (self.r10, self.r19, self.r22):
            self.write_bytes(source / "scripts/python/toy.py", b"# SYNTHETIC\n")
        request = {"source_root": str(self.r22), "source_commit": reader.R22_SOURCE_COMMIT,
            "artifact_root": str(self.root), "planner": "mvg", "run_id": "m4",
            "expected_run_raw_digest": reader.digest((self.run / "run.json").read_bytes()),
            "expected_handoff_ref": {"schema_version": handoff["schema_version"],
                "path": "logs/ci/mvg-planning/m4/handoff.json", "raw_digest": reader.digest((self.run / "handoff.json").read_bytes())},
            "dependency_paths": [], "reader_path": str(reader.READER), "reader_raw_digest": reader.digest(reader.READER.read_bytes())}
        return request, state, handoff

    def capture(self, request, handoff, *, observe_namespace=False, observe_scope_directory=False,
                observe_review_directory=False):
        def synthetic_native(actual, state, audit):
            for path in (self.root / "input.txt", self.root / "absent.txt", self.root / "prepared/input.json",
                         self.run / "registry.json"):
                audit._pin_file(path)
            audit._pin_directory(self.root / "business")
            if observe_namespace:
                # Real absence observation: the missing foreign parent makes
                # logs/ci the nearest existing directory whose members are pinned.
                audit._pin_file(self.root / "logs/ci/namespace-probe-missing/record.json")
            if observe_scope_directory:
                audit._pin_directory(self.root / operation_scope.STORE / "locks/scopes")
            if observe_review_directory:
                audit._pin_directory(self.root / adoption_review.BASE)
            for source in reader._profile_source_roots(self.r22):
                reader._pin_source_directories(audit, source)
            for source in (self.r10, self.r19, self.r22):
                audit._pin_file(source / "scripts/python/toy.py")
            return deepcopy(handoff), deepcopy(self.prepared)
        with patch.object(reader, "_native_witness", side_effect=synthetic_native):
            return reader._capture_request(request, self.audit)

    @contextmanager
    def snapshot_reader_context(self):
        # Keep the existing explicitly synthetic profile/source fixture in the
        # module context. Snapshot.verify, source binding and verify_capture are
        # all real; no directory or absence check is replaced.
        with patch.object(reader, "_adoption_source_digest", reader.digest(reader.READER.read_bytes()), create=True), \
             patch.object(adoption, "_frozen_native_reader", lambda: nullcontext(reader)):
            yield

    def test_fresh_scope_namespace_creation_after_capture_invalidates_snapshot(self):
        request, _, handoff = self.fixture()
        self.assertFalse((self.root / operation_scope.STORE).exists())
        capture = self.capture(request, handoff, observe_namespace=True)
        original = reader.canonical(capture)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        with self.snapshot_reader_context():
            snapshot.verify()
            with self.assertRaises(ValueError) as caught:
                with operation_scope.scope_guard(self.root, ['plan:namespace-probe'],
                        prepare_under_lease=snapshot.verify):
                    self.fail('The old capture-then-create ordering must fail')
        self.assertIn('closure_directory_changed:' + str(self.root / 'logs/ci'), str(caught.exception))
        self.assertEqual(original, reader.canonical(capture))
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_initialized_scope_namespace_preserves_real_native_directory_closure(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        capture = self.capture(request, handoff, observe_namespace=True)
        original = reader.canonical(capture)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        verified = []
        def verify():
            snapshot.verify()
            verified.append(True)
        with self.snapshot_reader_context():
            with operation_scope.scope_guard(self.root, ['plan:namespace-probe'], prepare_under_lease=verify):
                snapshot.verify()
        self.assertEqual([True], verified)
        self.assertEqual(original, reader.canonical(capture))
        self.assertEqual([], journal.operation_inventory(self.root))
        self.assertEqual({'locks'}, {path.name for path in (self.root / operation_scope.STORE).iterdir()})

    def test_initialized_scope_namespace_does_not_hide_arbitrary_ci_directory_drift(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        capture = self.capture(request, handoff, observe_namespace=True)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        (self.root / 'logs/ci/arbitrary-new-directory').mkdir()
        with self.snapshot_reader_context(), self.assertRaises(ValueError) as caught:
            snapshot.verify()
        self.assertIn('closure_directory_changed:' + str(self.root / 'logs/ci'), str(caught.exception))

    def test_initialized_scope_namespace_does_not_hide_deep_observed_directory_drift(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        capture = self.capture(request, handoff, observe_namespace=True, observe_scope_directory=True)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        with self.snapshot_reader_context(), self.assertRaises(ValueError) as caught:
            with operation_scope.scope_guard(self.root, ['plan:namespace-probe'],
                    prepare_under_lease=snapshot.verify):
                self.fail('An observed deep lock directory is never exempt')
        self.assertIn('closure_directory_changed:' + str(self.root / operation_scope.STORE / 'locks/scopes'),
                      str(caught.exception))

    def test_review_namespace_created_after_capture_cannot_be_repaired_by_late_initialization(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        self.assertFalse((self.root / adoption_review.BASE).exists())
        first = self.capture(request, handoff, observe_namespace=True)
        original = reader.canonical(first)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = first
        subject = adoption_review.location('OP-review-namespace') + '/subject.json'
        payload = b'{"synthetic_namespace_only":true}\n'
        with self.snapshot_reader_context():
            snapshot.verify()
            adoption_review.write_once(self.root, subject, payload)
            with self.assertRaises(ValueError) as caught:
                snapshot.verify()
            self.assertIn('closure_directory_changed:' + str(self.root / 'logs/ci'), str(caught.exception))
            adoption_review.initialize_namespace(self.root)
            with self.assertRaises(ValueError):
                snapshot.verify()
        self.assertEqual(original, reader.canonical(first))
        self.assertEqual(payload, (self.root / subject).read_bytes())
        # A second action has a new real observation, not a repair of the old one.
        self.audit = reader._Audit([self.task])
        second = self.capture(request, handoff, observe_namespace=True)
        for key in ('schema_version', 'run_identity', 'source_identity', 'files', 'handoff', 'prepared'):
            self.assertEqual(first[key], second[key])
        self.assertNotEqual(first['directories'], second['directories'])
        self.assertNotEqual(first['result_digest'], second['result_digest'])

    def test_preinitialized_review_namespace_stays_stable_across_real_subject_persistence(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        base = adoption_review.initialize_namespace(self.root)
        self.assertEqual([], list(base.iterdir()))
        first = self.capture(request, handoff, observe_namespace=True)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = first
        subject = adoption_review.location('OP-review-namespace') + '/subject.json'
        payload = b'{"synthetic_namespace_only":true}\n'
        with self.snapshot_reader_context():
            snapshot.verify()
            adoption_review.write_once(self.root, subject, payload)
            snapshot.verify()
        self.audit = reader._Audit([self.task])
        second = self.capture(request, handoff, observe_namespace=True)
        self.assertEqual(first, second)
        snapshot.native_capture = second
        with self.snapshot_reader_context():
            snapshot.verify()
        self.assertEqual(payload, (self.root / subject).read_bytes())
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_preinitialized_review_namespace_does_not_hide_deep_review_directory_drift(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        adoption_review.initialize_namespace(self.root)
        capture = self.capture(request, handoff, observe_namespace=True, observe_review_directory=True)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        adoption_review.write_once(self.root, adoption_review.location('OP-review-namespace') + '/subject.json',
                                   b'{"synthetic_namespace_only":true}\n')
        with self.snapshot_reader_context(), self.assertRaises(ValueError) as caught:
            snapshot.verify()
        self.assertIn('closure_directory_changed:' + str(self.root / adoption_review.BASE), str(caught.exception))

    def test_preinitialized_review_namespace_does_not_hide_unrelated_ci_drift(self):
        request, _, handoff = self.fixture()
        operation_scope.initialize_lock_namespace(self.root)
        adoption_review.initialize_namespace(self.root)
        capture = self.capture(request, handoff, observe_namespace=True)
        snapshot = adoption.Snapshot(self.root)
        snapshot.native_capture = capture
        (self.root / 'logs/ci/unrelated-after-review-initialization').mkdir()
        with self.snapshot_reader_context(), self.assertRaises(ValueError) as caught:
            snapshot.verify()
        self.assertIn('closure_directory_changed:' + str(self.root / 'logs/ci'), str(caught.exception))

    def test_structural_r10_r19_r22_profiles_preserve_original_proof_bytes(self):
        request, state, handoff = self.fixture()
        for label, source in (("candidate-1", self.r10), ("candidate-2", self.r19), ("candidate-3", self.r19)):
            self.put(self.run / "proofs" / (label + ".json"), {"source": str(source), "original_bytes": label})
        before = {p: p.read_bytes() for p in (self.run / "proofs").glob("*.json")}
        self.assertEqual((self.r22, reader.R22_SOURCE_COMMIT), reader._eligibility(state, "mvg", "m4", self.root))
        old = deepcopy(state)
        old["b_route_execution_transition"] = deepcopy(state["b_route_execution_transition"]["prior_transition"])
        old.pop("b_route_selector_recovery")
        self.assertEqual((self.r19, reader.R19_SOURCE_COMMIT), reader._state_profile(old, "mvg", "m4", self.root))
        old["b_route_execution_transition"] = old["b_route_execution_transition"]["prior_transition"]
        self.assertEqual((self.r10, reader.SOURCE_COMMIT), reader._state_profile(old, "capabilities", "legacy", self.root))
        capture = self.capture(request, handoff)
        reader.verify_capture(self.root, capture)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_wrong_source_commit_planner_run_and_sensitive_root_reject_before_io(self):
        request, _, _ = self.fixture()
        for mutation in ({"source_root": str(self.r19)}, {"source_commit": "0" * 40}, {"planner": "capabilities"},
                         {"run_id": "other"}, {"source_root": str(self.task / "sessions/private")}):
            with (self.subTest(mutation=mutation), patch.object(reader, "_safe", side_effect=AssertionError("No path IO")),
                  self.assertRaises(ValueError)):
                reader._request(reader.canonical({**request, **mutation}))

    def test_missing_s1_m1_wrong_parent_and_original_root_reject_before_native(self):
        request, state, _ = self.fixture()
        mutations = []
        for key in ("b_route_selector_recovery", "b_route_mvg_synthesis_recovery"):
            for replacement in (None, {}, {**state[key], "artifact_root": str(self.task)},
                                {**state[key], "record_ref": "unbound/record.json"}):
                changed = deepcopy(state); changed[key] = replacement; mutations.append(changed)
        for path, key, value in (((), "schema_version", reader.R19_EPOCH),
                (("prior_transition",), "current_commit", "0" * 40),
                (("prior_transition", "prior_transition"), "current_source_root", str(self.r19)),
                (("prior_transition", "prior_transition"), "original_source_root", str(self.task / "r7"))):
            changed = deepcopy(state); frame = changed["b_route_execution_transition"]
            for name in path: frame = frame[name]
            frame[key] = value; mutations.append(changed)
        with patch.object(reader, "_native_witness", side_effect=AssertionError("No native witness")):
            for index, changed in enumerate(mutations):
                self.put(self.run / "run.json", changed)
                current = {**request, "expected_run_raw_digest": reader.digest((self.run / "run.json").read_bytes())}
                with self.subTest(case=index), self.assertRaises(ValueError):
                    reader._capture_request(current, reader._Audit([]))

    def test_unknown_pending_failed_selector_and_added_call14_reject_before_native(self):
        request, state, _ = self.fixture()
        mutations = []
        for status in ("unknown", "pending", "failed"):
            changed = deepcopy(state); changed["capability_selection"]["calls"][12]["outcome"]["status"] = status
            mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["calls"].append({"number": 14, "outcome": {"status": "completed"}})
        changed["capability_selection"]["total_invocations"] = 14; mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["calls"].pop(); changed["capability_selection"]["total_invocations"] = 12
        mutations.append(changed)
        with patch.object(reader, "_native_witness", side_effect=AssertionError("No native witness")):
            for index, changed in enumerate(mutations):
                self.put(self.run / "run.json", changed)
                with self.subTest(case=index), self.assertRaises(ValueError):
                    reader._capture_request({**request, "expected_run_raw_digest": reader.digest((self.run / "run.json").read_bytes())}, reader._Audit([]))

    def test_cheap_close_refuses_source_input_registry_and_recovery_raw_drift(self):
        request, _, handoff = self.fixture()
        self.put(self.run / "registry.json", {"synthetic_epoch": 1, "revoked": []})
        capture = self.capture(request, handoff)
        for path in (self.r19 / "scripts/python/toy.py", self.r22 / "scripts/python/toy.py", self.root / "input.txt",
                     self.run / "registry.json", self.run / "recovery/s1/committed.json", self.run / "recovery/m1/record.json"):
            before = path.read_bytes(); path.write_bytes(b"synthetic changed bytes")
            with self.subTest(path=str(path)), self.assertRaisesRegex(ValueError, "closure_file_changed"):
                reader.verify_capture(self.root, capture)
            path.write_bytes(before)

    def test_cheap_close_refuses_r19_member_glob_and_absence_drift(self):
        request, _, handoff = self.fixture()
        capture = self.capture(request, handoff)
        for path in (self.r19 / "scripts/python/extra.py", self.root / "business/extra.md", self.root / "absent.txt"):
            path.write_bytes(b"new synthetic member")
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                reader.verify_capture(self.root, capture)
            path.unlink()

    def test_capture_cannot_be_rehashed_as_r19_or_rewrite_old_admission(self):
        request, _, handoff = self.fixture()
        self.put(self.run / "proofs/old-admission.json", {"synthetic_original_source": "R10"})
        capture = self.capture(request, handoff)
        changed = deepcopy(capture)
        changed["source_identity"].update(source_root=str(self.r19), source_commit=reader.R19_SOURCE_COMMIT)
        changed["result_digest"] = reader.digest(reader.canonical({k: v for k, v in changed.items() if k != "result_digest"}))
        with self.assertRaisesRegex(ValueError, "source_epoch_relabel_forbidden"):
            reader.verify_capture(self.root, changed)
        self.put(self.run / "proofs/old-admission.json", {"synthetic_original_source": "R22"})
        with self.assertRaisesRegex(ValueError, "closure_file_changed"):
            reader.verify_capture(self.root, capture)

    def transport_fixture(self):
        toy_pins = {}
        for name in reader._DESCRIBE_FILES:
            raw = ("# SYNTHETIC " + name + "\n").encode()
            toy_pins[name] = hashlib.sha256(raw).hexdigest()
            for root in (self.task / "r5", self.r22): self.write_bytes(root / name, raw)
        self.stack.enter_context(patch.object(reader, "_DESCRIBE_FILES", toy_pins))
        code = "# unchanged synthetic child, never executed\n"
        self.write_bytes(self.r22 / "scripts/python/_b_route_execution_transition.py", ("_CHILD = " + repr(code) + "\n").encode())
        return code

    def test_r22_exact_source_only_transport_and_ancestor_commands_are_bounded(self):
        _, state, _ = self.fixture(); code = self.transport_fixture()
        state["_reader_artifact_root"] = str(self.root)
        with patch.object(reader.shutil, "which", return_value="git"):
            commands = reader._source_commands(state, SimpleNamespace(), code, [])
            self.assertTrue(any(str(self.r19) in command for command in commands))
            argv = reader._original_argv(code, [], source_root=self.r22)
            self.assertIn(argv, commands)
            self.assertLess(len(subprocess.list2cmdline(argv)), 30000)
            self.assertIn("_BRouteSourceLoader", argv[-1])
            self.assertIn(reader._reader_raw_pin(), argv[-1])
            self.assertEqual(code, reader._original_program(reader._original_reference(code, self.r22)))
            for root, commit in ((self.r19, "0" * 40), (self.r22, "0" * 40)):
                changed = deepcopy(state)
                changed["b_route_execution_history"]["bad"] = {"original_source_root": str(root), "original_commit": commit,
                    "current_source_root": str(root), "current_commit": commit}
                with self.subTest(root=root), self.assertRaises(ValueError): reader._source_commands(changed, None, code, [])
        path = self.r22 / "scripts/python/_planning_skill_common.py"
        path.write_bytes(b"changed synthetic describe dependency")
        with self.assertRaisesRegex(ValueError, "describe_source_changed"): reader._describe_spec(self.r22)

    def test_audit_denies_unwrapped_modified_process_network_write_and_sensitive_read(self):
        code = self.transport_fixture()
        argv = reader._original_argv(code, [], source_root=self.r22)
        audit = reader._Audit([]); audit.commands = [argv]
        audit.check("subprocess.Popen", (None, argv, None, None))
        for event, arguments in (("subprocess.Popen", (None, argv[:-1] + [argv[-1] + "\n# altered"], None, None)),
                ("subprocess.Popen", (None, [sys.executable, "--version"], None, None)),
                ("socket.connect", (None,)), ("os.mkdir", (str(self.root / "new"),)),
                ("open", (str(self.root / "output"), "w", os.O_WRONLY)),
                ("open", (str(self.task / "sessions/private"), "r", 0))):
            with self.subTest(event=event), self.assertRaises(ValueError): audit.check(event, arguments)

    def test_r22_native_order_retains_original_checks_flags_and_both_source_directories(self):
        request, state, handoff = self.fixture()
        state.update(checkpoint_strategy="synthetic-checkpoints", recovery={"store": str(self.root / "logs/ci/mvg-recovery")})
        self.put(self.root / "logs/ci/mvg-recovery/registry.json", {"synthetic_epoch": 1})
        events = []
        @contextmanager
        def transaction(): yield
        def event(name, value=None):
            def execute(*args, **kwargs):
                events.append((name, kwargs)); return value
            return execute
        observations = SimpleNamespace(read=lambda name, **kwargs: b"toy input" if name == "input.txt" else None,
            watch=lambda patterns: [], verify=Mock())
        modules = {
            "_b_route_execution_transition": SimpleNamespace(_verification_transaction=transaction,
                _source_manifest=Mock(return_value={"synthetic": "manifest"})),
            "_b_route_planning_runtime": SimpleNamespace(validate_input=event("validate"), frozen_input=event("frozen", self.prepared),
                handoff=event("handoff", handoff), sources=SimpleNamespace(Observations=lambda root: observations)),
            "_mvg_capability_selection": SimpleNamespace(verified_prefix=event("prefix", ()), verify_published_chain=event("published")),
            "_mvg_capability_recovery": SimpleNamespace(CHECKPOINT_STRATEGY="synthetic-checkpoints", assert_active_chain=event("active"))}
        for name, module in modules.items():
            module.__name__, module.__file__ = name, str(self.r22 / "scripts/python" / (name + ".py"))
        # Isolate module-origin assertions from preceding synthetic test imports.
        unrelated = {name: module for name, module in sys.modules.items() if name.startswith(("_b_route_", "_mvg_", "_planning_"))
                     and name not in modules and name != reader.__name__}
        with (patch.dict(sys.modules, modules), patch.object(reader, "_source_commands", return_value=[]),
              patch.object(sys, "path", list(sys.path)), patch.object(sys, "dont_write_bytecode", True),
              patch.object(reader, "_independent_source", return_value={"synthetic": True}) as independent,
              patch.object(reader, "_install_source_only"), patch.object(reader, "_authenticated_original_code", return_value="toy child"),
              patch.object(reader, "_original_transport", side_effect=lambda *args: nullcontext()) as transport,
              patch.object(reader, "_pin_source_directories", wraps=reader._pin_source_directories) as directories):
            for name in unrelated: sys.modules.pop(name, None)
            try:
                self.assertEqual((handoff, self.prepared), reader._native_witness(request, state, self.audit))
                independent.assert_called_once_with(self.audit, source_profile=(self.r22, reader.R22_SOURCE_COMMIT))
                transport.assert_called_once_with("toy child", [], self.r22)
                self.assertEqual(["prefix", "validate", "published", "active", "frozen", "handoff"], [name for name, _ in events])
                self.assertEqual({"verify_history": True, "recover_counters": False, "check_originals": True}, events[0][1])
                self.assertEqual({"verified": (), "check_originals": True}, events[2][1])
                self.assertIn(self.r19, [call.args[1] for call in directories.call_args_list])
                self.assertIn(self.r22, [call.args[1] for call in directories.call_args_list])
                modules["_mvg_capability_selection"].verified_prefix = Mock(side_effect=ValueError("original counter rejection"))
                events.clear()
                with self.assertRaisesRegex(ValueError, "original counter rejection"):
                    reader._native_witness(request, state, reader._Audit([]))
                self.assertEqual([], events)
            finally:
                sys.modules.update(unrelated)

    def owner(self):
        """Compile exact preserved owner; adapters have no native authority."""
        raw = _PRODUCER.read_bytes()
        self.assertEqual(_PRODUCER_SHA256, hashlib.sha256(raw).hexdigest())
        codec = ModuleType("_b_route_codec")
        codec.canonical_digest = lambda value: reader.digest(reader.canonical(value))
        codec.raw_digest, codec.strict_json_loads = reader.digest, reader.strict_json
        def read(root, name):
            path = reader._reference(Path(root), name)
            self.audit._pin_file(path)
            return path.read_bytes()
        codec.read_reference_bytes = read
        sources = ModuleType("_b_route_sources")
        sources.checked_path = lambda root, name: reader._reference(Path(root), name)
        owner = ModuleType("_synthetic_pinned_r22_selector")
        owner.__file__ = str(_PRODUCER)
        with patch.dict(sys.modules, {"_b_route_codec": codec, "_b_route_sources": sources}):
            exec(compile(raw, str(_PRODUCER), "exec"), owner.__dict__)
        return owner

    def projection(self, owner):
        _, state, _ = self.fixture()
        ledger = state["capability_selection"]
        ledger["lineage_invocations"] = {"candidate-1": 5, "candidate-2": 4, "candidate-3": 3}
        ledger["generation"] = 1
        view = {"order_index": 0, "execution": 1, "admissions": deepcopy(ledger["selected"][0]["admissions"]),
                "aliases": {"A": "candidate-2", "B": "candidate-3", "C": "candidate-1"},
                "input_identity": {"synthetic": True}, "input_sha256": "sha256:" + "2" * 64}
        ledger["selected"] = [{**view, "input_identity": {"order_index": 0}}]
        ledger["selected"][0]["input_identity"] = view["input_identity"] = {"order_index": 0, "synthetic": True}
        state["active_elapsed_seconds"] = 100.0
        original = deepcopy(state)
        original["capability_selection"].update(calls=deepcopy(ledger["calls"][:12]), total_invocations=12, selected=[], current=deepcopy(view))
        original["b_route_execution_transition"] = deepcopy(state["b_route_execution_transition"]["prior_transition"])
        original.pop("b_route_selector_recovery")
        state["capability_selection"]["calls"][12].update(reservation_id="m4:dispatch:13", phase="selection", candidate=None, generation=1, execution=1)
        state["capability_selection"]["calls"][12]["request_identity"].update(attempt=1,
            selector_transport_policy="newrouge.b-route-compact-literal.v3", selection_input_sha256=view["input_sha256"])
        return {"original_state": original, "selection": {"input_sha256": view["input_sha256"]}}, state

    def test_original_owner_refuses_changed_old12_admissions_clock_and_charge(self):
        owner = self.owner(); anchor, state = self.projection(owner)
        owner._current_projection(anchor, state)
        mutations = []
        changed = deepcopy(state); changed["capability_selection"]["calls"][0]["request_identity"]["output_path"] = "swapped"; mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["selected"][0]["admissions"]["candidate-1"] = {"resigned": "R22"}; mutations.append(changed)
        changed = deepcopy(state); changed["active_elapsed_seconds"] = 99.0; mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["total_invocations"] = 12; mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["calls"].append(deepcopy(changed["capability_selection"]["calls"][12])); changed["capability_selection"]["total_invocations"] = 14; mutations.append(changed)
        changed = deepcopy(state); changed["capability_selection"]["calls"][12]["request_identity"]["selector_transport_policy"] = "newrouge.b-route-compact-literal.v2"; mutations.append(changed)
        for index, changed in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(ValueError): owner._current_projection(anchor, changed)

    def test_completed13_reaches_original_full_reserved_verifier_and_errors_propagate(self):
        owner = self.owner(); _, state = self.projection(owner)
        runtime = ModuleType("_b_route_planning_runtime"); runtime.verify_reserved_call = Mock()
        def checked_run(root, name):
            self.assertEqual((self.root.resolve(), owner.RUN_REF), (Path(root), name))
            return reader._safe(self.run, directory=True)
        with (patch.object(owner, "validate_recovery", return_value={}),
              patch.object(owner.sources, "checked_path", side_effect=checked_run),
              patch.dict(sys.modules, {runtime.__name__: runtime})):
            result = owner.verify_retained_dispatches(self.root, self.run, state)
            runtime.verify_reserved_call.assert_called_once_with(self.run.resolve(), state["capability_selection"]["calls"][12])
            self.assertEqual({"retained_original_calls": 12, "new_selector_calls": 1, "logical_reserved_calls": 13, "released": 0}, result)
            for status in ("unknown", "failed", "pending"):
                changed = deepcopy(state); changed["capability_selection"]["calls"][12]["outcome"]["status"] = status
                with self.subTest(status=status), self.assertRaisesRegex(ValueError, "selector_dispatch_not_completed"):
                    owner.verify_retained_dispatches(self.root, self.run, changed)
            for reason in ("schema", "material", "path", "citation", "receipt", "protocol", "high", "tools"):
                runtime.verify_reserved_call.side_effect = ValueError("original verifier rejects " + reason)
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "original verifier rejects"):
                    owner.verify_retained_dispatches(self.root, self.run, state)

    def control_fixture(self, owner):
        anchor = dict.fromkeys(owner._CAPTURE_FIELDS)
        source = self.r19 / "scripts/python/toy.py"
        self.write_bytes(source, b"toy preserved source")
        bridge = self.task / "continue_story25_mvg_synthesis_recovery_v17.py"
        self.write_bytes(bridge, b"toy original bridge")
        self.write_bytes(self.task / owner.HELPER_REF, b"toy helper")
        terminal = self.root / "logs/ci/v17/terminal.json"
        self.put(terminal, {"synthetic_terminal": True})
        anchor.update(schema_version=owner.CAPTURE_SCHEMA, artifact_root=str(self.root), run_ref=owner.RUN_REF,
            original_run_raw_digest=owner.ORIGINAL_RUN_DIGEST, helper_sha256=reader.digest(b"toy helper"),
            actual_model_dispatches=0, original_state={"b_route_mvg_synthesis_recovery": {"synthetic": True}},
            original_m1_ref={"synthetic": True}, admissions={"candidate-" + str(i): {} for i in range(1, 4)},
            selection={"scopes": ["synthetic-scope"], "records": []}, terminal_controls={"terminal.json": reader.digest(terminal.read_bytes())},
            source={"commit": reader.R19_SOURCE_COMMIT, "root": str(self.r19), "verifier_bridge_sha256": reader.digest(bridge.read_bytes()),
                "source_hashes": {"sources": {str(self.r19): {"manifest": {"scripts/python/toy.py": {"raw_digest": reader.digest(source.read_bytes())}}}}}})
        home = self.task / owner.CAPTURE_HOME
        self.put(home / "anchor.json", anchor)
        for name in ("stdout", "stderr"): self.write_bytes(home / (name + ".txt"), ("toy " + name).encode())
        receipt = {"os_exit_code": 0, "exit_source": "held_subprocess_handle_wait", "source_pins_unchanged": True,
            "anchor_sha256": reader.digest((home / "anchor.json").read_bytes()),
            "source_pins": {str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
            "stdout_sha256": hashlib.sha256((home / "stdout.txt").read_bytes()).hexdigest(),
            "stderr_sha256": hashlib.sha256((home / "stderr.txt").read_bytes()).hexdigest()}
        self.put(home / "exit.json", receipt)
        return anchor, home, {"HELPER_DIGEST": reader.digest(b"toy helper"),
            "ANCHOR_DIGEST": reader.digest((home / "anchor.json").read_bytes()),
            "CAPTURE_EXIT_DIGEST": reader.digest((home / "exit.json").read_bytes())}

    def test_self_signed_fake_anchor_rejects_original_fixed_root_pins(self):
        owner = self.owner(); _, _, _ = self.control_fixture(owner)
        with self.assertRaisesRegex(ValueError, "trusted_capture_controls_changed"): owner._trusted_anchor(self.root)

    def test_original_control_reads_close_raw_helper_anchor_exit_outputs_source_bridge_terminal(self):
        owner = self.owner(); anchor, home, toy_pins = self.control_fixture(owner)
        # Explicit toy root authority substitutes only in this boundary fixture.
        with patch.multiple(owner, **toy_pins), patch.object(owner, "retained_shape"):
            self.assertEqual(anchor, owner._trusted_anchor(self.root))
            owner._close_sources(self.root, anchor)
            controls = [self.task / owner.HELPER_REF, home / "anchor.json", home / "exit.json", home / "stdout.txt", home / "stderr.txt",
                self.r19 / "scripts/python/toy.py", self.task / "continue_story25_mvg_synthesis_recovery_v17.py",
                self.root / "logs/ci/v17/terminal.json"]
            for path in controls:
                self.assertEqual(reader.digest(path.read_bytes()), self.audit.files[str(path)])
                before = path.read_bytes(); path.write_bytes(b"changed toy control")
                # A fresh observation isolates producer pin rejection from audit drift.
                prior_audit = self.audit; self.audit = reader._Audit([])
                try:
                    with self.subTest(path=str(path)), self.assertRaises((ValueError, json.JSONDecodeError)):
                        owner._trusted_anchor(self.root); owner._close_sources(self.root, anchor)
                finally:
                    path.write_bytes(before); self.audit = prior_audit

    def recovery_fixture(self, owner):
        anchor, state = self.projection(owner); original = anchor["original_state"]
        record = {"schema_version": owner.SCHEMA, "run_id": "m4", "run_ref": owner.RUN_REF,
            "anchor_identity": {"synthetic": True}, "previous_run": owner.image(reader.canonical(original)),
            "model_execution_preimage": owner.image(b"toy original model projection"),
            "transition": {**state["b_route_execution_transition"], "transition_digest": "sha256:" + "3" * 64},
            "history": deepcopy(state["b_route_execution_history"]), "selector_transport_policy": owner._POLICY,
            "retained_calls": 12, "maximum_selector_dispatches": 1, "released": 0}
        reference = self.reference(owner.SCHEMA, "s1")
        reference["record_digest"] = reader.digest(reader.canonical(record))
        state.update(b_route_selector_recovery=reference, b_route_execution_transition=record["transition"])
        home = self.run / "recovery/s1"
        self.put(home / "record.json", record)
        self.put(home / "claim.json", {"schema_version": owner.SCHEMA, "record_digest": reference["record_digest"],
            "retained_calls": 12, "maximum_selector_dispatches": 1})
        # Native _record decodes both published record and archived preimage.
        # Their stored key order determines its exact indented initial bytes.
        published_record = reader.strict_json((home / "record.json").read_bytes())
        archived_original = reader.strict_json(owner.image_bytes(published_record["previous_run"]))
        initial = owner._prepared_state(archived_original, published_record, reference)
        self.put(home / "committed.json", {"record_digest": reference["record_digest"],
            "transition_digest": record["transition"]["transition_digest"],
            "prepared_run_digest": reader.digest((json.dumps(initial, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())})
        self.put(home / "intent.json", {"schema_version": owner.SCHEMA + ".selector-intent", "record_digest": reference["record_digest"],
            "anchor_identity": record["anchor_identity"], "retained_calls": 12,
            "request_identity": state["capability_selection"]["calls"][12]["request_identity"], "next_global_call": 13})
        return anchor, state, record, home

    def test_original_s1_record_rejects_missing_or_changed_claim_and_committed_marker(self):
        owner = self.owner(); _, state, record, home = self.recovery_fixture(owner)
        with patch.object(owner, "ORIGINAL_RUN_DIGEST", record["previous_run"]["raw_digest"]):
            self.assertEqual(record, owner._record(self.root, state))
            for name in ("claim.json", "committed.json"):
                path = home / name; before = path.read_bytes()
                for raw in (None, reader.canonical({"self_rehashed": True})):
                    if raw is None: path.unlink()
                    else: path.write_bytes(raw)
                    self.audit = reader._Audit([])
                    with self.subTest(name=name, missing=raw is None), self.assertRaises((ValueError, KeyError)):
                        owner._record(self.root, state)
                    path.write_bytes(before)

    def test_original_s1_validates_m1_against_archived_r19_and_rejects_intent_or_history_swap(self):
        owner = self.owner(); anchor, state, record, home = self.recovery_fixture(owner)
        capture = SimpleNamespace(_anchor={"manifest": {"files": {
            owner.RUN_REF + "/model-execution.json": record["model_execution_preimage"]["raw_digest"]}}})
        capture_identity = record["anchor_identity"]
        class ToyCapture:
            _anchor = capture._anchor
            def __getitem__(self, key): return capture_identity
        previous = ModuleType("_b_route_mvg_synthesis_recovery"); previous.validate_recovery = Mock()
        original = anchor["original_state"]
        with (patch.object(owner, "_record", return_value=record), patch.object(owner, "capture_retained_selector", return_value=ToyCapture()),
              patch.object(owner, "verify_retained_selector_capture", return_value=original), patch.dict(sys.modules, {previous.__name__: previous})):
            owner.validate_recovery(self.root, state)
            previous.validate_recovery.assert_called_once_with(self.root.resolve(), original)
            self.assertEqual(reader.R19_EPOCH, previous.validate_recovery.call_args.args[1]["b_route_execution_transition"]["schema_version"])
            for changed in ({**state, "b_route_execution_history": {"swapped": True}},
                            {**state, "b_route_execution_transition": {"self_rehashed": True}}):
                with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "source_frame_changed"):
                    owner.validate_recovery(self.root, changed)
            path = home / "intent.json"; before = path.read_bytes()
            for raw in (None, reader.canonical({"next_global_call": 14})):
                if raw is None: path.unlink()
                else: path.write_bytes(raw)
                self.audit = reader._Audit([])
                with self.subTest(missing=raw is None), self.assertRaises(ValueError): owner.validate_recovery(self.root, state)
                path.write_bytes(before)


class FrozenNativeReaderTransportTests(unittest.TestCase):
    """Only pipe serialization is exercised; every native action is synthetic."""

    def emit(self, value):
        binary = io.BytesIO()
        stream = io.TextIOWrapper(binary, encoding="gbk", errors="strict", newline="\n")
        request = {"artifact_root": "synthetic", "dependency_paths": []}
        audit = SimpleNamespace(subprocesses=nullcontext, check=lambda *_: None)
        try:
            with (patch.object(reader, "_reader_raw_pin"),
                  patch.object(reader, "_install_source_only"),
                  patch.object(reader, "_request", return_value=request),
                  patch.object(reader, "_request_profile", return_value=(Path("synthetic"),)),
                  patch.object(reader, "_profile_source_roots", return_value=[]),
                  patch.object(reader, "_Audit", return_value=audit),
                  patch.object(reader, "_capture_request", return_value=value),
                  patch.object(sys, "addaudithook"),
                  patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}"))),
                  patch.object(sys, "stdout", stream)):
                reader._main()
            stream.flush()
            return binary.getvalue()
        finally:
            stream.detach()

    def test_locale_pipe_roundtrip_preserves_unicode_and_canonical_identity(self):
        value = {"path": "synthetic/\u00b9/\u6e38\u620f/\U0001f680", "literal": "\\u00b9", "order": ["\u00b9", 1, False, None]}
        with self.assertRaises(UnicodeEncodeError):
            json.dumps(value, ensure_ascii=False).encode("gbk")
        raw = self.emit(value)
        self.assertTrue(raw.isascii())
        decoded = reader.strict_json(raw)
        self.assertEqual(value, decoded)
        self.assertEqual(reader.digest(reader.canonical(value)), reader.digest(reader.canonical(decoded)))

    def test_locale_pipe_still_rejects_nonfinite_result_without_partial_json(self):
        with self.assertRaises(ValueError):
            self.emit({"invalid": float("nan")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
