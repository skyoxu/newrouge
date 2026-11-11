"""Exact R19 reader profile tests; every native/semantic success is synthetic.

No actual project artifact, model, Git command or source policy runs. The final
three methods launch only source-bound Python children over owned toy sources.
The fixed-profile codecs, raw/absence/membership closing and argv construction
are real. Native authority is explicitly mocked and never claimed as accepted.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import ast
import hashlib
import os
from pathlib import Path
import py_compile
import queue
import shutil
import subprocess
import sys
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_frozen_native_reader as reader


class AdoptionR19ReaderTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(r"C:\Windows\TEMP") if os.name == "nt" else Path("/tmp")
        self.task = self.base / ("a19-" + uuid.uuid4().hex[:10])
        self.task.mkdir(exist_ok=False)
        self.addCleanup(self.cleanup_owned)
        self.root = self.task / "artifact"
        self.root.mkdir()
        self.r10, self.r19 = self.task / "r10", self.task / "r19"
        for name in ("r5", "r7", "r8", "r9", "r10", "r19"):
            (self.task / name / "scripts/python").mkdir(parents=True)
        self.stack.enter_context(patch.multiple(reader, TASK_ROOT=self.task, SOURCE_ROOT=self.r10))
        self.stack.enter_context(patch.object(reader, "_authenticated_reader_raw_digest",
                                              reader.digest(reader.READER.read_bytes()), create=True))
        self.stack.enter_context(patch.object(reader, "_dependencies", return_value=[]))
        self.business = self.root / "business/requirements.md"
        self.business.parent.mkdir()
        self.business.write_bytes(b"Synthetic complete business requirement")
        self.prepared = {"input_identity": "synthetic-complete-input", "inputs": {"dependencies": {
            "files": {"business/requirements.md": reader.digest(self.business.read_bytes()), "business/absent.md": None},
            "globs": [{"patterns": ["business/*.md"], "result": ["business/requirements.md"]}]}}}

    def cleanup_owned(self):
        result = getattr(getattr(self, "_outcome", None), "result", None)
        if result is not None and any(test is self or getattr(test, "test_case", None) is self
                                      for test, _ in result.errors + result.failures):
            return  # Preserve the exact failed or errored owned fixture.
        if (self.task.resolve().parent != self.base.resolve()
                or not self.task.name.startswith("a19-") or self.task.is_symlink()):
            raise AssertionError("Reader fixture escaped its allocated TEMP root")
        shutil.rmtree(self.task)

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(reader.canonical(value))

    def fixture(self, *, r19=True):
        planner, run_id, source, commit = (("mvg", "m4", self.r19, reader.R19_SOURCE_COMMIT) if r19 else
                                         ("capabilities", "c4", self.r10, reader.SOURCE_COMMIT))
        run = self.root / reader._run_ref(planner, run_id)
        prior = {"current_source_root": str(self.r10), "current_commit": reader.SOURCE_COMMIT}
        frame = {"current_source_root": str(source), "current_commit": commit,
                 "original_source_root": str(self.task / "r5"),
                 "original_commit": "988022094381c2b190b30c7702ed77aadda3805a"}
        if r19:
            frame.update(schema_version=reader.R19_EPOCH, prior_transition=prior)
        state = {"schema_version": "newrouge.b-route-planning-run.v2", "input_stage": "3b",
            "selection_status": "selected", "run_id": run_id,
            "planning_runtime": {"planner": planner, "input_identity": self.prepared["input_identity"],
                "frozen_sha256": reader.digest(reader.canonical(self.prepared)), "prepared_ref": "preparation/prepared.json"},
            "b_route_execution_transition": frame, "b_route_execution_history": {},
            "runner_configuration": {"backend": "isolated-runner", "backend_info": {"requested_reasoning_effort": "high"},
                "runner": str(self.task / "r5/scripts/python/codex_isolated_model_runner.py")},
            "capability_selection": {"total_invocations": 8, "calls": [{"number": number,
                "request_identity": {"execution_binding_path": "bindings/call-" + str(number) + ".json"},
                "outcome": {"status": "completed"}} for number in range(1, 9)],
                "selected": [{"admissions": {"candidate-" + str(number): {"synthetic": True}
                    for number in range(1, 4 if r19 else 3)}}]}}
        if r19:
            record_ref = "logs/ci/mvg-planning/m4/recovery/m1/record.json"
            self.put(self.root / record_ref, {"schema_version": reader.R19_RECOVERY, "synthetic_native_record": True})
            state["b_route_mvg_synthesis_recovery"] = {"schema_version": reader.R19_RECOVERY,
                "record_ref": record_ref, "record_digest": reader.digest((self.root / record_ref).read_bytes()),
                "artifact_root": str(self.root)}
        handoff = {"schema_version": "newrouge.b-route-planning-handoff.v1", "run_id": run_id,
            "proposal": {"synthetic_complete_proposal": True}, "provider_actual_model": "unknown"}
        self.put(run / "run.json", state)
        self.put(run / "handoff.json", handoff)
        self.put(self.root / "preparation/prepared.json", self.prepared)
        self.put(source / "scripts/python/native_source.py", {"synthetic_source": str(source.name)})
        for row in state["capability_selection"]["calls"]:
            self.put(run / row["request_identity"]["execution_binding_path"], {"runner_info": {"requested_reasoning_effort": "high"}})
        request = {"source_root": str(source), "source_commit": commit, "artifact_root": str(self.root),
            "planner": planner, "run_id": run_id, "expected_run_raw_digest": reader.digest((run / "run.json").read_bytes()),
            "expected_handoff_ref": {"path": reader._run_ref(planner, run_id) + "/handoff.json",
                "schema_version": handoff["schema_version"], "raw_digest": reader.digest((run / "handoff.json").read_bytes())},
            "dependency_paths": [], "reader_path": str(reader.READER), "reader_raw_digest": reader.digest(reader.READER.read_bytes())}
        return request, state, handoff, run

    def capture(self, request, state, handoff):
        def fake_native(actual_request, actual_state, audit):
            self.assertEqual(request, actual_request)
            self.assertEqual(state, actual_state)
            for path in (Path(request["source_root"]) / "scripts/python/native_source.py", self.business,
                         self.business.parent / "absent.md", self.root / "preparation/prepared.json"):
                audit._pin_file(path)
            audit._pin_directory(self.business.parent)
            return deepcopy(handoff), deepcopy(self.prepared)
        with patch.object(reader, "_native_witness", side_effect=fake_native):
            return reader._capture_request(reader._request(reader.canonical(request)), reader._Audit([self.root]))

    def test_exact_r19_m4_and_legacy_r10_capability_profiles_coexist_without_relabel(self):
        for r19 in (False, True):
            request, state, handoff, _ = self.fixture(r19=r19)
            capture = self.capture(request, state, handoff)
            reader.verify_capture(self.root, capture)
            self.assertEqual((request["source_root"], request["source_commit"]),
                (capture["source_identity"]["source_root"], capture["source_identity"]["source_commit"]))
            self.assertEqual(self.prepared, capture["prepared"])
            changed = deepcopy(capture)
            changed["source_identity"].update(source_root=str(self.r10 if r19 else self.r19),
                source_commit=reader.SOURCE_COMMIT if r19 else reader.R19_SOURCE_COMMIT)
            changed["result_digest"] = reader.digest(reader.canonical({k: v for k, v in changed.items() if k != "result_digest"}))
            with self.assertRaises(ValueError):
                reader.verify_capture(self.root, changed)

    def test_unknown_source_requests_reject_before_source_or_sensitive_io(self):
        request, _, _, _ = self.fixture()
        changes = ({"source_root": str(self.task / "auth.json")}, {"source_root": str(self.task / "r20")},
                   {"source_commit": "0" * 40}, {"planner": "capabilities"}, {"run_id": "other"})
        for mutation in changes:
            changed = {**request, **mutation}
            with (self.subTest(mutation=mutation),
                  patch.object(reader, "_safe", side_effect=AssertionError("Unknown profile must reject before path IO")),
                  self.assertRaises(ValueError)):
                reader._request(reader.canonical(changed))

    def test_r19_wrong_epoch_reference_low_unknown_or_cardinality_never_calls_native(self):
        request, state, _, run = self.fixture()
        mutations = []
        value = deepcopy(state); value["b_route_execution_transition"]["schema_version"] = "newrouge.b-route-source-epoch.v1"; mutations.append(value)
        value = deepcopy(state); value["b_route_execution_transition"]["prior_transition"]["current_commit"] = "0" * 40; mutations.append(value)
        value = deepcopy(state); value.pop("b_route_mvg_synthesis_recovery"); mutations.append(value)
        value = deepcopy(state); value["b_route_mvg_synthesis_recovery"]["caller_approved"] = True; mutations.append(value)
        value = deepcopy(state); value["b_route_mvg_synthesis_recovery"]["record_ref"] = "archived_sessions/private.json"; mutations.append(value)
        value = deepcopy(state); value["b_route_mvg_synthesis_recovery"]["artifact_root"] = str(self.task); mutations.append(value)
        value = deepcopy(state); value["runner_configuration"]["backend_info"]["requested_reasoning_effort"] = "low"; mutations.append(value)
        value = deepcopy(state); value["capability_selection"]["calls"][6]["outcome"]["status"] = "unknown"; mutations.append(value)
        value = deepcopy(state); value["capability_selection"]["selected"][0]["admissions"].pop("candidate-3"); mutations.append(value)
        with patch.object(reader, "_native_witness", side_effect=AssertionError("Invalid profile must not reach native")):
            for index, value in enumerate(mutations):
                self.put(run / "run.json", value)
                current = {**request, "expected_run_raw_digest": reader.digest((run / "run.json").read_bytes())}
                with self.subTest(case=index), self.assertRaises(ValueError):
                    reader._capture_request(current, reader._Audit([self.root]))

    def test_r19_raw_absence_membership_and_typed_record_drift_reject_at_cheap_closing(self):
        request, state, handoff, run = self.fixture()
        capture = self.capture(request, state, handoff)
        targets = [self.business, run / "recovery/m1/record.json", self.r19 / "scripts/python/native_source.py"]
        for path in targets:
            before = path.read_bytes(); path.write_bytes(b"changed synthetic raw")
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                reader.verify_capture(self.root, capture)
            path.write_bytes(before)
        absent = self.business.parent / "absent.md"
        absent.write_bytes(b"new synthetic dependency")
        with self.assertRaises(ValueError):
            reader.verify_capture(self.root, capture)
        absent.unlink()
        extra = self.business.parent / "extra.md"
        extra.write_bytes(b"new synthetic glob member")
        with self.assertRaises(ValueError):
            reader.verify_capture(self.root, capture)

    def test_r19_metadata_and_describe_transport_are_exact_and_cache_guarded(self):
        request, state, _, _ = self.fixture()
        state["_reader_artifact_root"] = str(self.root)
        original_code = "# unchanged synthetic original child; never executed"
        # This older routing fixture mocks the newly authenticated transport;
        # the actual source-bound transport has its own fixtures below.
        with (patch.object(reader.shutil, "which", return_value="synthetic-git"),
              patch.object(reader, "_transport_spec", return_value={"synthetic_transport": True}),
              patch.object(reader, "_describe_spec", side_effect=lambda path: {"source_root": str(path)}),
              patch.object(reader, "_metadata_bootstrap", return_value="# synthetic metadata bootstrap")):
            commands = reader._source_commands(state, SimpleNamespace(), original_code, [])
            describe = [sys.executable, "-B", str(self.r19 / "scripts/python/codex_isolated_model_runner.py"), "--describe"]
            actual_describe = reader._describe_argv({"source_root": str(self.r19)}, describe)
            self.assertIn(actual_describe, commands)
            with patch.object(reader.subprocess, "Popen", return_value="synthetic-no-process") as spawn:
                with patch.object(reader, "_describe_cache_guard", side_effect=AssertionError("No dependency cache walk")):
                    with reader._original_transport(original_code, [], self.r19):
                        self.assertEqual("synthetic-no-process", reader.subprocess.Popen(describe))
                    spawn.assert_called_once_with(actual_describe)
        self.assertIn(["synthetic-git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(self.r19),
                       "rev-parse", "--verify", reader.R19_SOURCE_COMMIT + "^{commit}"], commands)
        state["b_route_execution_history"]["wrong-r19"] = {"original_source_root": str(self.r10),
            "original_commit": reader.SOURCE_COMMIT, "current_source_root": str(self.r19), "current_commit": "0" * 40}
        with patch.object(reader.shutil, "which", return_value="synthetic-git"), self.assertRaisesRegex(ValueError, "closed_r19_ancestor_commit"):
            reader._source_commands(state, SimpleNamespace(), original_code, [])

    def test_r19_full_native_order_uses_exact_source_and_propagates_owner_rejection(self):
        request, state, handoff, _ = self.fixture()
        state.update(checkpoint_strategy="synthetic-checkpoint", recovery={"store": str(self.root / "logs/ci/mvg-recovery")})
        self.put(self.root / "logs/ci/mvg-recovery/registry.json", {"synthetic": True})
        calls = []
        @contextmanager
        def transaction():
            yield
        def event(name, value=None):
            def invoke(*args, **kwargs):
                calls.append((name, kwargs))
                return value
            return invoke
        observations = SimpleNamespace(read=lambda path, optional=False: None if path.endswith("absent.md") else self.business.read_bytes(),
            watch=lambda patterns: ["business/requirements.md"], verify=event("dependency-close"))
        native = {
            "_b_route_execution_transition": SimpleNamespace(_verification_transaction=transaction,
                _source_manifest=Mock(return_value={"synthetic": "source-manifest"})),
            "_b_route_planning_runtime": SimpleNamespace(validate_input=event("validate"),
                frozen_input=event("frozen", self.prepared), handoff=event("handoff", handoff),
                sources=SimpleNamespace(Observations=lambda root: observations)),
            "_mvg_capability_selection": SimpleNamespace(verified_prefix=event("prefix", ([], {}, [])),
                verify_published_chain=event("published")),
            "_mvg_capability_recovery": SimpleNamespace(CHECKPOINT_STRATEGY="synthetic-checkpoint", assert_active_chain=event("active")),
        }
        for name, module in native.items():
            module.__name__, module.__file__ = name, str(self.r19 / "scripts/python" / (name + ".py"))
        with (patch.dict(sys.modules), patch.object(sys, "path", list(sys.path)), patch.object(sys, "dont_write_bytecode", True),
              patch.object(reader, "_install_source_only"), patch.object(reader, "_source_commands", return_value=[]),
              patch.object(reader, "_original_transport", side_effect=lambda *args, **kwargs: transaction()),
              patch.object(reader, "_authenticated_original_code", return_value="# synthetic original child"),
              patch.object(reader, "_independent_source", return_value={"synthetic": True}) as independent):
            for name in list(sys.modules):
                if name.startswith(("_b_route_", "_mvg_", "_planning_")) and name != reader.__name__:
                    del sys.modules[name]
            sys.modules.update(native)
            result = reader._native_witness(request, state, reader._Audit([self.root]))
            self.assertEqual((handoff, self.prepared), result)
            independent.assert_called_once()
            self.assertEqual((self.r19, reader.R19_SOURCE_COMMIT), independent.call_args.kwargs["source_profile"])
            self.assertEqual(["prefix", "validate", "published", "active", "frozen", "dependency-close", "handoff"], [row[0] for row in calls])
            self.assertEqual({"verify_history": True, "recover_counters": False, "check_originals": True}, calls[0][1])
            native["_mvg_capability_selection"].verified_prefix = Mock(side_effect=ValueError("synthetic native epoch rejected"))
            with self.assertRaisesRegex(ValueError, "synthetic native epoch rejected"):
                reader._native_witness(request, state, reader._Audit([self.root]))
            native["_b_route_planning_runtime"].__file__ = str(self.r10 / "scripts/python/_b_route_planning_runtime.py")
            with self.assertRaisesRegex(ValueError, "native_module_origin_changed"):
                reader._native_witness(request, state, reader._Audit([self.root]))

    def test_parent_r19_child_request_has_exact_profile_and_no_dispatch(self):
        request, state, handoff, run = self.fixture()
        capture = self.capture(request, state, handoff)
        response = SimpleNamespace(returncode=0, stdout=reader.canonical(capture), stderr=b"")
        with patch.object(reader.subprocess, "run", return_value=response) as child:
            result = reader.capture_completed(self.root, planner="mvg", run_id="m4", state_raw=(run / "run.json").read_bytes(),
                expected_handoff_ref=request["expected_handoff_ref"])
        self.assertEqual(capture, result)
        args, kwargs = child.call_args
        self.assertEqual(["-X", "dev", "-I", "-S", "-B", "-c"], args[0][1:7])
        self.assertEqual(self.r19, kwargs["cwd"])
        sent = reader.strict_json(kwargs["input"])
        self.assertEqual(reader._REQUEST_FIELDS, set(sent))
        self.assertEqual((str(self.r19), reader.R19_SOURCE_COMMIT), (sent["source_root"], sent["source_commit"]))
        self.assertNotIn("shell", kwargs)


class SourceBoundDescribeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(r"C:\Windows\TEMP") if os.name == "nt" else Path("/tmp")
        self.task = self.base / ("a19-" + uuid.uuid4().hex[:10])
        self.task.mkdir(exist_ok=False)
        self.addCleanup(self.cleanup_owned)
        self.r5, self.r19 = self.task / "r5", self.task / "r19"
        script = ("import json,os,sys\nimport openai_isolated_model_runner as api\n"
            "assert sys.argv[1:]==['--describe']\n"
            "if os.environ.get('SYNTHETIC_IMPORT_EXTERNAL')=='1': import injected_extra\n"
            "if os.environ.get('SYNTHETIC_DESCRIBE_PAUSE')=='1':\n print('READY',flush=True)\n sys.stdin.readline()\n"
            "print(json.dumps({'marker':api.MARK,'argv':sys.argv,'isolated':sys.flags.isolated,"
            "'no_site':sys.flags.no_site,'requested':os.environ.get('NEWROGUE_CODEX_REASONING_EFFORT')}),flush=True)\n").encode()
        self.raws = {name: b"# Authenticated synthetic helper, never a native owner\n" for name in reader._DESCRIBE_FILES}
        self.raws["scripts/python/codex_isolated_model_runner.py"] = script
        self.raws["scripts/python/openai_isolated_model_runner.py"] = b"MARK='SOURCE'\n"
        self.files = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.raws.items()}
        for root in (self.r5, self.r19):
            for name, raw in self.raws.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        original_reader = reader.READER.read_text(encoding="utf-8")
        tree = ast.parse(original_reader)
        target = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(item, ast.Name) and item.id == "_DESCRIBE_FILES" for item in node.targets))
        lines = original_reader.splitlines(keepends=True)
        copied = "".join(lines[:target.lineno - 1]) + "_DESCRIBE_FILES=" + repr(self.files) + "\n" + "".join(lines[target.end_lineno:])
        self.copied_reader = self.task / "r20/scripts/python/_b_route_frozen_native_reader.py"
        self.copied_reader.parent.mkdir(parents=True)
        self.copied_reader.write_text(copied, encoding="utf-8", newline="\n")
        self.stack.enter_context(patch.multiple(reader, TASK_ROOT=self.task, SOURCE_ROOT=self.task / "r10",
                                                READER=self.copied_reader, _DESCRIBE_FILES=self.files))
        # Private command construction has no capture authority. The actual
        # loaders below establish their own inherited raw pin before exec.
        self.stack.enter_context(patch.object(reader, "_authenticated_reader_raw_digest", None, create=True))
        self.stack.enter_context(patch.object(reader, "_adoption_source_digest", None, create=True))
        self.outside = self.task / "unrelated-dependency"
        self.outside.mkdir()
        (self.outside / "sitecustomize.py").write_text("raise RuntimeError('UNTRUSTED SITE STARTUP')\n", encoding="utf-8")
        irrelevant = self.outside / "unused.py"
        irrelevant.write_text("UNUSED=True\n", encoding="utf-8")
        py_compile.compile(str(irrelevant), doraise=True)

    def cleanup_owned(self):
        result = getattr(getattr(self, "_outcome", None), "result", None)
        if result is not None and any(test is self or getattr(test, "test_case", None) is self
                                      for test, _ in result.errors + result.failures):
            return
        if self.task.resolve().parent != self.base.resolve() or not self.task.name.startswith("a19-") or self.task.is_symlink():
            raise AssertionError("Describe fixture escaped its allocated TEMP root")
        shutil.rmtree(self.task)

    def command(self):
        specification = reader._describe_spec(self.r5)
        return reader._describe_argv(specification, [sys.executable,
            str(self.r5 / "scripts/python/codex_isolated_model_runner.py"), "--describe"])

    def run_child(self, command, **kwargs):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.outside)
        environment.update(kwargs.pop("extra_env", {}))
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                              check=False, env=environment, **kwargs)

    def test_source_bound_describe_ignores_poisoned_toy_pyc_and_unrelated_site_dependency(self):
        api = self.r5 / "scripts/python/openai_isolated_model_runner.py"
        api.write_bytes(b"MARK='CACHED'\n")
        py_compile.compile(str(api), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        api.write_bytes(self.raws["scripts/python/openai_isolated_model_runner.py"])
        baseline = subprocess.run([sys.executable, "-B", str(self.r5 / "scripts/python/codex_isolated_model_runner.py"), "--describe"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        self.assertEqual(0, baseline.returncode, baseline.stderr.decode(errors="replace"))
        self.assertEqual("CACHED", reader.strict_json(baseline.stdout)["marker"])
        actual = self.run_child(self.command())
        self.assertEqual(0, actual.returncode, actual.stderr.decode(errors="replace"))
        value = reader.strict_json(actual.stdout)
        self.assertEqual("SOURCE", value["marker"])
        self.assertEqual([str(self.r5 / "scripts/python/codex_isolated_model_runner.py"), "--describe"], value["argv"])
        self.assertEqual((1, 1), (value["isolated"], value["no_site"]))
        self.assertEqual(os.environ.get("NEWROGUE_CODEX_REASONING_EFFORT"), value["requested"])
        (self.r5 / "scripts/python/injected_extra.py").write_text("raise RuntimeError('MUST NOT EXECUTE')\n", encoding="utf-8")
        refused = self.run_child(self.command(), extra_env={"SYNTHETIC_IMPORT_EXTERNAL": "1"})
        self.assertNotEqual(0, refused.returncode)
        self.assertIn(b"describe_import_outside_source_closure", refused.stderr)
        self.assertNotIn(b"MUST NOT EXECUTE", refused.stderr)

    def test_exact_args_source_and_external_raw_closing_reject(self):
        specification = reader._describe_spec(self.r5)
        logical = [sys.executable, str(self.r5 / "scripts/python/codex_isolated_model_runner.py"), "--describe"]
        with self.assertRaises(ValueError):
            reader._describe_argv(specification, logical + ["--extra"])
        with patch.object(reader, "_safe", side_effect=AssertionError("Unknown source must reject before IO")), self.assertRaises(ValueError):
            reader._describe_sources({**specification, "source_root": str(self.outside)})
        command = self.command()
        api = self.r5 / "scripts/python/openai_isolated_model_runner.py"
        original = api.read_bytes()
        api.write_bytes(b"# Changed after command authentication\n")
        rejected = self.run_child(command)
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn(b"describe_source_changed", rejected.stderr)
        api.write_bytes(original)
        environment = dict(os.environ, SYNTHETIC_DESCRIBE_PAUSE="1")
        child = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", env=environment)
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True).start()
            self.assertEqual("READY\n", ready.get(timeout=20))
            api.write_bytes(b"# External drift after the child read the source\n")
            output, errors = child.communicate("\n", timeout=30)
            self.assertNotEqual(0, child.returncode)
            self.assertIn("changed", errors)
            self.assertIn("SOURCE", output)
        finally:
            if child.poll() is None:
                child.kill()  # Only this test's held owned toy process handle.
                child.wait(timeout=10)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    stream.close()

    def test_original_literal_stdin_and_only_project_audit_hook_are_adapted(self):
        script = str(self.r5 / "scripts/python/codex_isolated_model_runner.py")
        original = ("import hashlib,json,subprocess,sys\n"
            "request=json.loads(sys.stdin.buffer.read())\nseen=[]\nproject=[]\nlogical=[sys.executable," + repr(script) + ",'--describe']\n"
            "def unrelated(event,args):\n"
            " if event=='sys.addaudithook' and request.get('veto_registration'): raise RuntimeError('platform_registration_veto')\n"
            " if event=='subprocess.Popen': seen.append(args[1] if isinstance(args[1],str) else subprocess.list2cmdline(args[1]))\n"
            "sys.addaudithook(unrelated)\n"
            "def blocked(event,args):\n"
            " if event=='subprocess.Popen':\n"
            "  if list(args[1]) not in [logical,[sys.executable,'-B'," + repr(script) + ",'--describe']]: raise RuntimeError('original_project_audit_rejected')\n"
            "  project.append(list(args[1]))\n"
            "sys.addaudithook(blocked)\n"
            "command=logical+(['--extra'] if request.get('bad') else [])\n"
            "result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)\n"
            "assert result.returncode==0,result.stderr.decode()\n"
            "print(json.dumps({'request':request,'describe':json.loads(result.stdout),'seen':seen,'project':project}))\n")
        transition = self.r19 / "scripts/python/_b_route_execution_transition.py"
        transition.write_text("_CHILD=" + repr(original) + "\n", encoding="utf-8")
        command = reader._original_argv(original, [str(self.outside)], source_root=self.r19)
        self.assertLess(len(subprocess.list2cmdline(command)), 30000)
        supplied = {"input": {"ordinal": 8, "high": True}}
        actual = self.run_child(command, input=reader.canonical(supplied))
        self.assertEqual(0, actual.returncode, actual.stderr.decode(errors="replace"))
        value = reader.strict_json(actual.stdout)
        self.assertEqual(supplied, value["request"])
        self.assertEqual("SOURCE", value["describe"]["marker"])
        logical = [sys.executable, script, "--describe"]
        expected_actual = reader._describe_argv(reader._describe_spec(self.r5), logical)
        self.assertEqual([subprocess.list2cmdline(expected_actual)], value["seen"])
        self.assertNotEqual(subprocess.list2cmdline(logical), value["seen"][0])
        self.assertEqual([[sys.executable, script, "--describe"]], value["project"])
        rejected = self.run_child(command, input=reader.canonical({"bad": True}))
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn(b"original_project_audit_rejected", rejected.stderr)
        vetoed = self.run_child(command, input=reader.canonical({"veto_registration": True}))
        self.assertNotEqual(0, vetoed.returncode)
        self.assertIn(b"original_project_audit_registration_not_confirmed", vetoed.stderr)
        transition.write_text("_CHILD='modified source'\n", encoding="utf-8")
        changed = self.run_child(command, input=reader.canonical(supplied))
        self.assertNotEqual(0, changed.returncode)
        self.assertIn(b"original_child_source_changed", changed.stderr)

    def test_inherited_reader_pin_rejects_disk_rebind_before_command(self):
        source = self.copied_reader.read_bytes()
        pin = reader.digest(source)
        loaded = ModuleType("owned_authenticated_reader_H1")
        loaded.__file__ = str(self.copied_reader)
        loaded.__dict__["_authenticated_reader_raw_digest"] = pin
        exec(compile(source, str(self.copied_reader), "exec"), loaded.__dict__)
        specification = loaded._describe_spec(self.r5)
        logical = [sys.executable, str(self.r5 / "scripts/python/codex_isolated_model_runner.py"), "--describe"]
        command = loaded._describe_argv(specification, logical)
        self.copied_reader.write_bytes(source + b"\n# H2 must never become nested command authority\n")
        with patch.object(loaded.subprocess, "Popen", side_effect=AssertionError("No child before pin rejection")):
            with self.assertRaisesRegex(ValueError, "reader_source_changed_since_authentication"):
                loaded._describe_argv(specification, logical)
        rejected = self.run_child(command)
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn(b"reader_source_changed", rejected.stderr)
        with patch.object(reader.subprocess, "run", side_effect=AssertionError("No actual capture without authenticated loader")):
            with self.assertRaisesRegex(ValueError, "authenticated_reader_digest_required"):
                reader.capture_completed(self.task, planner="mvg", run_id="m4", state_raw=b"{}", expected_handoff_ref={})

    def test_actual_reader_and_metadata_loaders_propagate_original_pin(self):
        source = self.copied_reader.read_bytes()
        probes = ("\ndef _pin_probe():\n"
                  " print(json.dumps({'inherited':globals().get('_authenticated_reader_raw_digest'),"
                  "'checked':_reader_raw_pin(require_authenticated=True)}))\n"
                  "def _main(): _pin_probe()\n"
                  "def _metadata_main(action,payload): _pin_probe()\n").encode("utf-8")
        self.copied_reader.write_bytes(source + probes)
        pin = reader.digest(self.copied_reader.read_bytes())
        commands = [
            [sys.executable, "-I", "-S", "-B", "-c", reader._reader_bootstrap(self.copied_reader, pin)],
            [sys.executable, "-I", "-S", "-B", "-c", reader._metadata_bootstrap("describe", {})],
        ]
        for command in commands:
            with self.subTest(loader="reader" if "r._main()" in command[-1] else "metadata"):
                actual = self.run_child(command)
                self.assertEqual(0, actual.returncode, actual.stderr.decode(errors="replace"))
                self.assertEqual({"inherited": pin, "checked": pin}, reader.strict_json(actual.stdout))


if __name__ == "__main__":
    unittest.main(verbosity=2)
