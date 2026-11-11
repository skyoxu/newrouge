"""Offline segmented composition; synthetic OS/native funding, real replay.

Never imports a project fixture, starts a subprocess, dispatches a model, or
changes a real run. Root alone runs this module after the common source barrier.
The hand-authored oracle tests preservation and mechanical symmetry, not actual
model quality or native qualification. Journal accounting/fault ownership has
its own tests; FakeSession below explicitly grants no real funding authority.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
SOURCE = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _b_route_codec as codec
import _b_route_segmented_workflow as core
import _b_route_segmented_requests as requests
import _b_route_planning_runtime as runtime
import _planning_skill_common as common
import _planning_execution_binding as execution_binding
import _codex_app_server as app_server
import codex_isolated_model_runner as official
from fixtures.codex_app_server_protocol import protocol, encoded


GLOBAL = b"Never delete an existing record. Preserve non-Flow audit.\n"
LEFT = "Shared command Q must validate before writing; \u03b1.\n".encode("utf-8")
RIGHT = b"Requirement R depends on Q, preserves state, and emits audit without a Flow.\n"
CANDIDATES = {
    "complete": b"Q validates, then writes. R preserves state and records audit.\n",
    "drops-audit": b"Q validates, then writes. R omits the non-Flow audit.\n",
    "wrong-order": b"Q writes before validating. R preserves state and audit.\n",
}
ORACLE = {"winner": "complete", "obligations": ["shared-command", "ordered-edge", "non-flow"],
          "edges": [["non-flow", "shared-command"], ["ordered-edge", "shared-command"]],
          "dimensions": ["source-preservation", "interaction-order"],
          "meanings": {"shared-command": "Q validates before writing",
                       "ordered-edge": "R depends on Q and preserves state",
                       "non-flow": "R emits audit without a Flow"}}


def raw_sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def resign(value, key):
    value[key] = codec.canonical_digest({k: v for k, v in value.items() if k != key})
    return value


def write(root, relative, raw):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    return path


def high_protocol(workspace, **kwargs):
    """Author explicit requested high in the synthetic client RPC itself.

    The generic fixture deliberately has no requested effort by default. An
    environment setting and returned high alone cannot satisfy the original
    binding owner's requested-and-returned-high requirement.
    """
    records = protocol(workspace, **kwargs)
    starts = [row["message"] for row in records if row["direction"] == "client"
              and row["message"].get("method") == "thread/start"]
    if len(starts) != 1:
        raise AssertionError("Expected one synthetic fresh thread request")
    starts[0]["params"]["config"] = app_server.thread_config(reasoning_effort="high")
    return records


def authored_case(root, *, order=("complete", "drops-audit", "wrong-order"), split=True, run_id="small-case"):
    """Authored business denominator, never inferred from a response/schema."""
    source_path = root / "docs/case/source.txt"
    if not source_path.exists():
        write(root, "docs/case/source.txt", LEFT + RIGHT)
        write(root, "docs/case/global.txt", GLOBAL)
        for name, body in CANDIDATES.items():
            write(root, "docs/case/" + name + ".txt", body)
    materials = [{"material_id": "source", "path": "docs/case/source.txt", "version": "v1",
                  "role": "source", "candidate_label": None,
                  "boundaries": [0, len(LEFT), len(LEFT + RIGHT)] if split else [0, len(LEFT + RIGHT)]},
                 {"material_id": "global", "path": "docs/case/global.txt", "version": "v1",
                  "role": "global", "candidate_label": None, "boundaries": [0, len(GLOBAL)]}]
    candidates = []
    for label, identity in zip("ABC", order):
        mid = "candidate-" + label
        candidates.append({"label": label, "candidate_id": identity, "material_ids": [mid]})
        materials.append({"material_id": mid, "path": "docs/case/" + identity + ".txt", "version": "v1",
                          "role": "candidate", "candidate_label": label, "boundaries": [0, len(CANDIDATES[identity])]})
    manifest = core.freeze_manifest(root, run_id=run_id, materials=materials, candidates=candidates)
    original_ids = [s["segment_id"] for s in manifest["segments"] if s["material_id"] == "source"]
    obligations = [
        {"obligation_id": "shared-command", "kind": "definition",
         "segment_ids": [original_ids[0], "global.0"] + ["candidate-" + c + ".0" for c in "ABC"], "dependency_ids": []},
        {"obligation_id": "ordered-edge", "kind": "edge", "segment_ids": original_ids, "dependency_ids": ["shared-command"]},
        {"obligation_id": "non-flow", "kind": "non-flow", "segment_ids": [original_ids[-1]], "dependency_ids": ["shared-command"]},
    ]
    nodes = []
    by_phase = {}
    for phase in core.PHASES[:3]:
        for label in "ABC":
            previous = [] if phase == "generation" else [by_phase[(core.PHASES[core.PHASES.index(phase)-1], label)]]
            # v1 generates source-cited decision records, not native candidate
            # bodies: the complete comparison snapshot is explicit to every
            # candidate's G/R turn. No foreign candidate is cited unseen.
            originals = original_ids + ["candidate-" + c + ".0" for c in "ABC"] if phase != "synthesis" else []
            node_id = phase.replace("independent-", "") + "-" + label
            nodes.append({"node_id": node_id, "phase": phase, "ordinal": len(nodes), "candidate_labels": [label],
                          "segment_ids": originals, "obligation_ids": ORACLE["obligations"][:],
                          "dependencies": previous, "output_reserve": 26000, "final": False})
            by_phase[(phase, label)] = node_id
    nodes.append({"node_id": "joint-panel", "phase": "selection", "ordinal": len(nodes),
                  "candidate_labels": list("ABC"), "segment_ids": original_ids + ["candidate-" + c + ".0" for c in "ABC"],
                  "obligation_ids": ORACLE["obligations"][:], "dependencies": [by_phase[("independent-review", c)] for c in "ABC"],
                  "output_reserve": 26000, "final": False})
    nodes.append({"node_id": "global-choice", "phase": "selection", "ordinal": len(nodes),
                  "candidate_labels": list("ABC"), "segment_ids": [], "obligation_ids": ORACLE["obligations"][:],
                  "dependencies": ["joint-panel"], "output_reserve": 26000, "final": True})
    plan = core.build_plan(manifest, planner="mvg", dimensions=ORACLE["dimensions"][:], obligations=obligations,
                           dependency_edges=deepcopy(ORACLE["edges"]), nodes=nodes)
    return manifest, plan


def citation(plan, sid):
    source = next(s for s in plan["manifest"]["segments"] if s["segment_id"] == sid)
    return {key: source[key] for key in ("segment_id", "start", "end", "raw_digest")}


def authored_response(plan, node):
    """Synthetic semantic decisions are an explicit oracle, not a real model."""
    obligation_by_id = {o["obligation_id"]: o for o in plan["obligations"]}
    coverage, decisions, checks = [], [], []
    for oid in node["obligation_ids"]:
        row = obligation_by_id[oid]
        cites = [citation(plan, sid) for sid in row["segment_ids"]]
        coverage.append({"obligation_id": oid, "citations": cites})
        decisions.append({"decision_id": node["node_id"] + "/" + oid, "obligation_ids": [oid],
                          "depends_on": row["dependency_ids"][:], "citations": cites, "statement": ORACLE["meanings"][oid]})
        if node["phase"] == "independent-review":
            checks.append({"obligation_id": oid, "verdict": "supported", "citations": cites})
    comparisons = []
    if node["phase"] == "selection":
        identities = {c["label"]: c["candidate_id"] for c in plan["manifest"]["candidates"]}
        all_cites = [citation(plan, s["segment_id"]) for s in plan["manifest"]["segments"]]
        for label in node["candidate_labels"]:
            for dimension in ORACLE["dimensions"]:
                comparisons.append({"candidate_label": label, "dimension": dimension,
                                    "obligation_ids": ORACLE["obligations"][:],
                                    "assessment": identities[label] + ": " + dimension,
                                    "citations": all_cites,
                                    "cross_impacts": [{"from": edge[0], "to": edge[1],
                                                       "explanation": "R must follow Q validation and retain audit", "citations": all_cites}
                                                      for edge in ORACLE["edges"]]})
    winner = next(c["label"] for c in plan["manifest"]["candidates"] if c["candidate_id"] == ORACLE["winner"])
    return {"schema_version": core.RESPONSE, "protocol": core.PROTOCOL, "run_id": plan["run_id"],
            "plan_digest": plan["plan_digest"], "node_id": node["node_id"], "phase": node["phase"],
            "coverage": coverage, "decisions": decisions,
            "dependency_edges": [e for e in plan["dependency_edges"] if e[0] in node["obligation_ids"]],
            "unresolved": [], "findings": [], "checks": checks, "comparisons": comparisons,
            "candidate_pieces": [], "product_checks": [], "joint_checks": [],
            "selected_label": winner if node["final"] else None,
            "rationale": "Preserve Q ordering, state and non-Flow audit" if node["final"] else "",
            "derived_not_lossless": True}


class FakeSession:
    """Explicit unavailable native/funding boundary, not a journal substitute."""
    def __init__(self, root, plan):
        self.root, self.plan = root, plan
        self.home = root / "logs/ci" / ("turns-" + secrets.token_hex(3))
        self.completed, self.reservations, self.failures = [], [], []
        self.blocked = None

    def snapshot(self):
        return {"completed": deepcopy(self.completed), "blocked": self.blocked}

    def workspace(self, node):
        # H's permanent input archive is the sibling of each node's workspace,
        # as in the original journal layout; different nodes cannot share it.
        return self.home / node["node_id"] / "w"

    def timeout(self, node):
        return 30

    def reserve(self, node, identity, *, rendered_request, completed_prefix):
        if self.blocked is not None:
            raise AssertionError("No retry after unknown")
        core.validate_request_identity(self.root, self.plan, node, identity, self.workspace(node),
            {"run_id": self.plan["run_id"], "plan_digest": self.plan["plan_digest"], "run_path": "logs/ci/native/run.json"},
            rendered_request=rendered_request, completed_prefix=completed_prefix)
        official_path = SCRIPTS / "codex_isolated_model_runner.py"
        result = {"node_id": node["node_id"], "run_id": self.plan["run_id"], "phase": node["phase"],
                  "workspace": str(rendered_request["workspace"]), "timeout_sec": 30,
                  "request_identity": deepcopy(identity), "model_identity": {"runner": {
                      "path": str(official_path), "raw_digest": raw_sha(official_path.read_bytes()),
                      "description": official.description()}}}
        self.reservations.append(result)
        return result

    def complete(self, reservation, result):
        node = self.plan["nodes"][len(self.completed)]
        value = core.validate_verified_result(self.plan, node, reservation, result)
        self.completed.append({"node_id": node["node_id"], "reservation": deepcopy(reservation), "result": value})

    def fail(self, reservation, reason):
        self.failures.append((deepcopy(reservation), deepcopy(reason)))
        self.blocked = "unknown-retains-charge"

    def finalize(self, token):
        self.finalized = core.validate_completion(self.root, self.plan, token)


class SegmentedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_parent = Path(os.environ.get("TEMP", "C:/Windows/Temp")).resolve()
        self.root = self.temp_parent / ("sg" + secrets.token_hex(5))
        self.root.mkdir(exist_ok=False)
        self.addCleanup(self.cleanup_owned)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(subprocess, "Popen", side_effect=AssertionError("No subprocess in offline fixture")))
        self.stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("No network in offline fixture")))
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("No network in offline fixture")))
        self.stack.enter_context(patch.object(socket.socket, "connect_ex", side_effect=AssertionError("No network in offline fixture")))
        self.stack.enter_context(patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high"}))
        self.manifest, self.plan = authored_case(self.root)

    def cleanup_owned(self):
        outcome = getattr(getattr(self, "_outcome", None), "result", None)
        if outcome is not None and any(test is self or getattr(test, "test_case", None) is self
                                       for test, _ in outcome.errors + outcome.failures):
            print(json.dumps({"event": "fixture-retained", "test": self.id(), "root": str(self.root)}), flush=True)
            return
        resolved = self.root.resolve()
        if resolved.parent != self.temp_parent or not resolved.name.startswith("sg"):
            raise AssertionError("Refuse cleanup outside unique owned fixture")
        if resolved.exists():
            for parent, directories, files in os.walk(resolved):
                for name in directories + files:
                    info = (Path(parent) / name).lstat()
                    if getattr(info, "st_file_attributes", 0) & 0x400:
                        raise AssertionError("Refuse cleanup through reparse point")
            shutil.rmtree(resolved)

    def blocked(self, expected, action):
        with self.assertRaisesRegex(ValueError, expected):
            action()

    def assert_portable_output_schema(self, schema):
        scalar_types = {str: "string", bool: "boolean", int: "integer", float: "number", type(None): "null"}
        pending = [schema]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if "const" in node:
                    self.assertIn(type(node["const"]), scalar_types, "Provider array/object const is unsupported")
                    expected = scalar_types[type(node["const"]) ]
                    declared = node.get("type")
                    self.assertTrue(declared == expected or isinstance(declared, list) and expected in declared)
                if "enum" in node:
                    self.assertTrue(node["enum"])
                    declared = node.get("type")
                    for value in node["enum"]:
                        self.assertIn(type(value), scalar_types)
                        expected = scalar_types[type(value)]
                        self.assertTrue(declared == expected or isinstance(declared, list) and expected in declared)
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                    self.assertEqual(len(node["required"]), len(set(node["required"])))
                pending.extend(value for value in node.values() if isinstance(value, (dict, list)))
            elif isinstance(node, list):
                pending.extend(value for value in node if isinstance(value, (dict, list)))
        self.assertEqual(set(schema["properties"]), {"schema_version", "citation_sets", "result"})
        self.assertEqual(schema["properties"]["schema_version"]["const"], core.RESPONSE_WIRE)
        joint = schema["properties"]["result"]["properties"]["joint_checks"]["items"]
        self.assertEqual(set(joint["properties"]), {"candidate_label", "domain_digest", "member_digests",
            "interaction_edges", "source_obligation_ids", "verdict", "citation_set_index"})

    def render(self, plan, node, *, suffix="", results=None):
        envelope = core._envelope(self.root, plan, node, results or {})
        return requests.render_request(self.root, envelope=envelope, schema=core.output_schema(envelope),
            instruction=core.phase_instruction(node["phase"], node["final"]),
            workspace=self.root / "logs/ci/render" / (node["node_id"] + suffix), output_reserve=node["output_reserve"])

    def fake_os_turn(self, runner, **kwargs):
        """Writes captured synthetic OS/protocol bytes; actual replay is real."""
        self.dispatched.append(kwargs)
        workspace = Path(kwargs["workspace"])
        # Decode only to author the fixture response. The provider prompt below
        # remains the actual serialized wire workspace, including its decoder.
        logical_workspace = workspace
        if kwargs.get("fixture_input_workspace") is not None:
            # Only the deliberate binding-path attack uses this canonical read
            # view. The alias is retained in RPC cwd/receipt/argv/binding paths;
            # production read_input_envelope is never called with an alias or
            # weakened. Both views must name the exact same owned fixture dir.
            logical_workspace = Path(kwargs["fixture_input_workspace"])
            self.assertIn("..", workspace.parts)
            self.assertNotIn("..", logical_workspace.parts)
            self.assertTrue(logical_workspace.is_relative_to(self.root))
            self.assertEqual(logical_workspace.resolve(strict=True), workspace.resolve(strict=True))
            self.assertIsNotNone(kwargs.get("fixture_request_payload"))
        envelope = requests.read_input_envelope(self.root, logical_workspace)
        node = next(n for n in self.active_plan["nodes"] if n["node_id"] == envelope["node_id"])
        factory = getattr(self, "response_factory", None)
        response = factory(self.active_plan, node, envelope) if factory else authored_response(self.active_plan, node)
        if getattr(self, "alter_response", None):
            self.alter_response(node, response)
        # Factories and semantic attacks author complete logical data. Encode
        # exactly once; the real protocol and receipt bind these physical bytes.
        physical_response = core.encode_response_wire(response)
        self.assertEqual(core.decode_response_wire(physical_response, envelope), response)
        output = json.dumps(physical_response, ensure_ascii=False, separators=(",", ":"))
        schema = codec.strict_json_loads(Path(kwargs["output_schema"]).read_bytes())
        prompt = kwargs.get("fixture_request_payload")
        if prompt is None:
            prompt = requests._model_prompt(workspace, Path(kwargs["prompt_path"]), Path(kwargs["output_path"]))
        records = high_protocol(workspace, prompt=prompt, output=output, schema=schema)
        serial = len(self.dispatched) + getattr(self, "fixture_serial_offset", 0)
        records = json.loads(json.dumps(records).replace("fresh-thread", "thread-" + str(serial)).replace("fresh-turn", "turn-" + str(serial)))
        if getattr(self, "alter_protocol", None):
            self.alter_protocol(node, records)
        protocol_raw = encoded(records)
        # Construct the host receipt from the actual original replay, not a
        # model-provided success field or a patched validate_execution.
        actual, proof = app_server.replay(protocol_raw, prompt=prompt, schema=schema)
        self.assertEqual(proof["requested_reasoning_effort"], "high")
        self.assertEqual(proof["runtime_reasoning_effort"], "high")
        Path(kwargs["output_path"]).write_bytes(actual.encode("utf-8"))
        protocol_path = Path(str(kwargs["output_path"]) + "." + secrets.token_hex(16) + ".app-server.jsonl")
        protocol_path.write_bytes(protocol_raw)
        protocol_path.with_suffix(".stderr.txt").write_bytes(b"")
        receipt = {"schema_version": "newrouge.isolated-model-runner-receipt.v1", "model": proof["model"],
            "model_provider": proof["model_provider"], "model_identity": proof["model_provider"] + "/" + proof["model"],
            "model_identity_source": official.MODEL_IDENTITY_SOURCE, "model_identity_verified": False,
            "runtime_identity_verified": True, "model_identity_scope": "runtime_configuration",
            "evidence_policy": official.APP_SERVER_EVIDENCE_POLICY, "provider_reported_model": None,
            "provider_identity_verified": False, "provider_dispatch_count": "unknown", "model_identity_evidence": [proof],
            "model_tools": [], "runner_invocations": 1, "request_count_observable": True, "model_request_count": 1,
            "output_chars": len(actual), "workspace": workspace.as_posix()}
        stdout = json.dumps(receipt) + "\n"
        host = {"status": "completed", "returncode": 0, "runner_dispatch_count": 1,
                "active_elapsed_seconds": 0.1, "stdout": stdout,
                "stdout_base64": base64.b64encode(stdout.encode()).decode()}
        host["command"] = [*common._runner_prefix(Path(runner), suppress_bytecode=True),
            "--workspace", str(workspace), "--prompt-file", str(kwargs["prompt_path"]),
            "--output", str(kwargs["output_path"]), "--timeout-sec", str(kwargs["timeout_sec"]),
            "--output-schema", str(kwargs["output_schema"]), "--model-request-budget", "1"]
        Path(kwargs["execution_log"]).write_bytes(json_bytes(host))
        return host

    @contextmanager
    def composition(self, plan=None, session=None):
        import _b_route_segmented_journal as journal
        import _b_route_segmented_runtime as segmented_runtime
        self.active_plan = plan or self.plan
        self.dispatched = []
        self.session = session or FakeSession(self.root, self.active_plan)
        if not (self.root / "scripts/python/codex_isolated_model_runner.py").exists():
            write(self.root, "scripts/python/codex_isolated_model_runner.py", b"# Offline path only; never executed.\n")
        # Bind the real current source policy, while fake business files live
        # only under this test's owned root. No native acceptance is fabricated.
        policy_owner = core.policy_identity
        @contextmanager
        def fake_open(*args, **kwargs):
            yield self.session
        @contextmanager
        def fake_native_source(*args, **kwargs):
            core.validate_plan(args[2] if len(args) > 2 else kwargs["plan"])
            yield None
        transports = set()
        @contextmanager
        def fake_source_transport(*args, **kwargs):
            token = object()
            transports.add(token)
            yield token
        def fake_verify_transport(root, token, *, logical_command):
            self.assertIn(token, transports)
            return {"schema_version": "newrouge.b-route-segmented-runner-transport.v1",
                "logical_argv": list(logical_command), "transport_argv": ["SYNTHETIC_NO_PROCESS"],
                "source_pins": {"explicit-fake-native-source-observation": raw_sha(b"no actual source OS child")},
                "bootstrap_raw_digest": raw_sha(b"explicit synthetic bootstrap"), "child_pid": 42424242}
        def fake_replay_transport(root, provenance, *, logical_command):
            self.assertEqual(set(provenance), {"schema_version", "logical_argv", "transport_argv", "source_pins", "bootstrap_raw_digest", "child_pid"})
            self.assertEqual(provenance["logical_argv"], list(logical_command))
            self.assertEqual(provenance["transport_argv"], ["SYNTHETIC_NO_PROCESS"])
            self.assertEqual(provenance["source_pins"], {"explicit-fake-native-source-observation": raw_sha(b"no actual source OS child")})
            self.assertEqual(provenance["child_pid"], 42424242)
        def fake_paid_reservation(root, plan, node, reservation):
            # Explicit original funding observer only: a caller copy may match
            # one immutable FakeSession charge, but cannot create a new charge.
            self.assertTrue(any(codec.canonical_digest(row) == codec.canonical_digest(reservation)
                                for row in self.session.reservations))
            self.assertEqual(reservation["node_id"], node["node_id"])
            return deepcopy(reservation)
        with ExitStack() as scope:
            scope.enter_context(patch.object(journal, "open_workflow", side_effect=fake_open))
            scope.enter_context(patch.object(segmented_runtime, "verified_run", side_effect=fake_native_source))
            scope.enter_context(patch.object(segmented_runtime, "excluded_turns", return_value=[
                {"thread_id": "upstream-audit-thread", "turn_id": "upstream-audit-turn"}]))
            scope.enter_context(patch.object(segmented_runtime, "source_only_runner", side_effect=fake_source_transport))
            scope.enter_context(patch.object(segmented_runtime, "verify_runner_transport", side_effect=fake_verify_transport))
            scope.enter_context(patch.object(segmented_runtime, "replay_runner_transport", side_effect=fake_replay_transport))
            scope.enter_context(patch.object(segmented_runtime, "assert_paid_reservation", side_effect=fake_paid_reservation))
            scope.enter_context(patch.object(core, "policy_identity", side_effect=lambda root: policy_owner(SOURCE)))
            scope.enter_context(patch.object(common, "inspect_isolated_runner", return_value=official.description()))
            scope.enter_context(patch.object(common, "run_isolated_model", side_effect=self.fake_os_turn))
            yield self.session

    def test_complete_four_phase_original_protocol_and_small_fit_oracle(self):
        with self.composition():
            outcome = core.execute_workflow(self.root, run_dir=self.root / "logs/ci/native", plan=self.plan)
        self.assertEqual(outcome["selected_original_candidate"], ORACLE["winner"])
        self.assertEqual(len(self.dispatched), len(self.plan["nodes"]))
        self.assertEqual({n["phase"] for n in self.plan["nodes"]}, set(core.PHASES))
        for field in ("native_qualified", "readiness", "runtime_verified", "b_default_active", "legacy_all_materials_proof"):
            self.assertIs(outcome[field], False)
        threads = []
        for previous in self.session.completed:
            value = previous["result"]
            self.assertEqual([d["statement"] for d in value["response"]["decisions"]], list(ORACLE["meanings"].values()))
            proof = value["binding"]["receipt"]["model_identity_evidence"][0]
            threads.append(proof["thread_id"])
            self.assertEqual(proof["requested_reasoning_effort"], "high")
            self.assertEqual(proof["runtime_reasoning_effort"], "high")
            self.assertEqual(value["binding"]["receipt"]["provider_dispatch_count"], "unknown")
        self.assertEqual(len(threads), len(set(threads)))
        # Reuse this completed paid chain; no second workflow is needed for the
        # standalone high-receipt substitution/claim-binding regression matrix.
        session = self.session
        with self.composition(session=session):
            self.assert_paid_request_substitutions()

    def assert_paid_request_substitutions(self):
        import _b_route_segmented_runtime as native
        original = self.session.completed[0]["result"]
        node = self.plan["nodes"][0]
        reservation = deepcopy(original["reservation"])
        binding = deepcopy(original["binding"])
        workspace = Path(binding["workspace"])
        raw_files = {p.name: p.read_bytes() for p in workspace.iterdir()}
        paid_before = deepcopy(self.session.reservations)
        self.fixture_serial_offset = 1000
        original_envelope = requests.read_input_envelope(self.root, workspace)
        self.assertEqual(core.decode_response_wire(runtime.verify_call(binding), original_envelope), original["response"])
        core.validate_paid_binding(self.root, self.plan, node, reservation, binding,
                                   request_sha256=original["request_sha256"])

        def restore_workspace():
            # Only this unique synthetic workspace is restored. No real run,
            # claim, paid record, archive, or original fixture sidecar is removed.
            for path in workspace.iterdir():
                if path.name not in raw_files:
                    self.assertEqual(path.parent, workspace)
                    path.unlink()
            for name, raw in raw_files.items():
                (workspace / name).write_bytes(raw)

        def high_binding(request, *, use_original=False, alias=False):
            target = workspace if use_original else Path(request["workspace"])
            if alias:
                target = target / ".." / target.name
            host = Path(request["workspace"]).parent / "observed-execution.json"
            runner = SCRIPTS / "codex_isolated_model_runner.py"
            with native.source_only_runner(self.root, runner) as transport:
                self.fake_os_turn(runner, workspace=target, prompt_path=target / "prompt.txt",
                    output_path=target / "output.json", output_schema=target / "output-schema.json",
                    timeout_sec=reservation["timeout_sec"], execution_log=host,
                    fixture_request_payload=request["model_prompt"],
                    fixture_input_workspace=request["workspace"] if alias else None)
            execution = codec.strict_json_loads(host.read_bytes())
            execution["command_scope"] = "original-logical-runner-argv"
            execution["source_transport"] = native.verify_runner_transport(self.root, transport,
                                                                          logical_command=execution["command"])
            host.write_bytes(json_bytes(execution))
            receipt = execution_binding.receipt_from(execution)
            actual = runtime.capture_binding(target, target / "prompt.txt", target / "output-schema.json",
                target / "output.json", request["model_prompt"], request["measurement"], host,
                official.description(), receipt)
            observed_envelope = requests.read_input_envelope(self.root, Path(request["workspace"]))
            self.assertEqual(core.decode_response_wire(runtime.verify_call(actual), observed_envelope), original["response"])
            proof = actual["receipt"]["model_identity_evidence"][0]
            self.assertEqual((proof["requested_reasoning_effort"], proof["runtime_reasoning_effort"]), ("high", "high"))
            return actual

        # These are independently real original protocol replays at the same
        # plan/node. The actual synthetic paid reservation is held unchanged.
        for kind in ("workspace", "input", "prompt", "schema", "path-alias"):
            with self.subTest(paid_binding_attack=kind):
                envelope = core._envelope(self.root, self.plan, node, {})
                schema = core.output_schema(envelope)
                instruction = core.phase_instruction(node["phase"])
                if kind == "input":
                    envelope["dimensions"].reverse()
                elif kind == "prompt":
                    instruction += "\nAnother complete high request; not the paid request."
                elif kind == "schema":
                    schema["description"] = "A different legitimate schema at the same plan and node"
                request = requests.render_request(self.root, envelope=envelope, schema=schema, instruction=instruction,
                    workspace=self.root / "logs/ci/attacks" / kind / "w", output_reserve=node["output_reserve"])
                encoded_input = json_bytes(requests.encode_input_envelope(envelope))
                self.assertEqual((Path(request["workspace"]) / "input.json").read_bytes(), encoded_input)
                self.assertEqual(requests.read_input_envelope(self.root, Path(request["workspace"])), envelope)
                try:
                    original_location = kind in {"input", "prompt", "schema"}
                    if original_location:
                        for name in ("prompt.txt", "input.json", "output-schema.json"):
                            raw = encoded_input if name == "input.json" else (Path(request["workspace"]) / name).read_bytes()
                            (workspace / name).write_bytes(raw)
                    actual = high_binding(request, use_original=original_location, alias=kind == "path-alias")
                    if kind == "workspace":
                        self.assertEqual(request["request_sha256"], original["request_sha256"])
                    expected = ("archive_original_input_bytes_changed" if original_location else "paid_binding.original_paths")
                    self.blocked(expected, lambda: core.validate_paid_binding(self.root, self.plan, node, reservation,
                        actual, request_sha256=request["request_sha256"]))
                    substituted = deepcopy(original)
                    substituted["binding"] = actual
                    substituted["request_sha256"] = request["request_sha256"]
                    # A recomputed result hash and a genuine high protocol do
                    # not turn another request into this immutable paid claim.
                    resign(substituted, "result_digest")
                    self.blocked(expected, lambda: core.replay_verified_result(self.root, self.plan, node,
                                                                              reservation, substituted))
                finally:
                    restore_workspace()

        for kind in ("measurement", "wrapper", "execution-argv"):
            with self.subTest(paid_binding_attack=kind):
                changed = deepcopy(binding)
                if kind == "measurement":
                    changed["measurement"]["input_token_estimate"] += 1
                elif kind == "wrapper":
                    changed["request_payload"] += "\nUnpaid extra material"
                else:
                    changed["host_execution"]["command"][-1] = "2"
                changed["binding_sha256"] = runtime.canonical_sha({k: v for k, v in changed.items() if k != "binding_sha256"})
                if kind != "wrapper":
                    # These two metadata fields were outside the original
                    # single-turn verifier's scope, but the new paid owner must
                    # bind them. Its protocol/receipt remains genuine high.
                    self.assertEqual(core.decode_response_wire(runtime.verify_call(changed), original_envelope), original["response"])
                expected = "paid_binding.original_execution_argv" if kind == "execution-argv" else "paid_binding.actual_request_changed"
                self.blocked(expected, lambda: core.validate_paid_binding(self.root, self.plan, node, reservation,
                    changed, request_sha256=original["request_sha256"]))
        self.assertEqual(self.session.reservations, paid_before)
        self.assertEqual({p.name: p.read_bytes() for p in workspace.iterdir()}, raw_files)
        core.validate_paid_binding(self.root, self.plan, node, reservation, binding,
                                   request_sha256=original["request_sha256"])
        del self.fixture_serial_offset

    def test_partition_bytes_utf8_predecessor_missing_duplicate_order_and_global(self):
        parts = [s for s in self.manifest["segments"] if s["material_id"] == "source"]
        self.assertEqual(b"".join((LEFT + RIGHT)[s["start"]:s["end"]] for s in parts), LEFT + RIGHT)
        self.assertEqual(parts[1]["parent_digest"], raw_sha(LEFT))
        for mutate, expected in [
            (lambda m: m["segments"].pop(1), "segment.omission"),
            (lambda m: m["segments"].insert(1, deepcopy(m["segments"][0])), "segment.order_parent_range"),
            (lambda m: m["segments"].reverse(), "segment.order_parent_range|segment.inventory_order"),
            (lambda m: m["segments"][1].update(parent_digest=raw_sha(b"foreign")), "segment.order_parent_range"),
        ]:
            changed = deepcopy(self.manifest)
            mutate(changed)
            resign(changed, "manifest_digest")
            self.blocked(expected, lambda: core.verify_manifest(self.root, changed))
        materials = [{"material_id": "global", "path": "docs/case/global.txt", "version": "v1", "role": "global", "candidate_label": None,
                      "boundaries": [0, 1, len(GLOBAL)]}]
        # Reuse the two candidate declarations; the global split must be the
        # reached guard before any unrelated missing-candidate validation.
        self.blocked("global.indivisible", lambda: core.freeze_manifest(self.root, run_id="bad", materials=materials,
                     candidates=self.manifest["candidates"]))
        bad = deepcopy(self.manifest)
        bad["segments"][0]["end"] = LEFT.index("\u03b1".encode()) + 1
        resign(bad, "manifest_digest")
        with self.assertRaises(UnicodeDecodeError):
            core.verify_manifest(self.root, bad)

    def test_cross_dependency_closure_and_complete_denominator_not_caller_mask(self):
        for change, expected in [
            (lambda p: p["dependency_edges"].pop(), "dependency.complete_denominator"),
            (lambda p: p["nodes"][0].update(obligation_ids=["ordered-edge"]), "node.dependency_closure"),
            (lambda p: p["nodes"][0].update(segment_ids=["source.0", "candidate-A.0"]), "node.complete_original_closure"),
            (lambda p: p["nodes"][3].update(dependencies=[]), "node.parent_coverage"),
            (lambda p: p["nodes"][-2].update(segment_ids=["source.0"]), "selection.joint_original_closure"),
            (lambda p: p["nodes"].pop(0), "node.identity_order"),
            (lambda p: p["nodes"].insert(1, deepcopy(p["nodes"][0])), "node.identity_order"),
            (lambda p: p["nodes"].reverse(), "node.identity_order"),
            (lambda p: p.update(run_id="different-run"), "plan.manifest"),
        ]:
            altered = deepcopy(self.plan)
            change(altered)
            resign(altered, "plan_digest")
            self.blocked(expected, lambda: core.validate_plan(altered))

    def test_every_phase_identity_coverage_order_and_foreign_citation_rejects(self):
        for phase in core.PHASES:
            node = next(n for n in self.plan["nodes"] if n["phase"] == phase)
            original = authored_response(self.plan, node)
            self.assertEqual(core.verify_response(self.plan, node, original), original)
            for mutate, expected in [
                (lambda r: r.update(plan_digest=raw_sha(b"other")), "response.complete_output_schema"),
                (lambda r: r["coverage"].pop(), "coverage.missing_duplicate_order"),
                (lambda r: r["coverage"].reverse(), "coverage.missing_duplicate_order"),
                (lambda r: r["coverage"][0]["citations"][0].update(raw_digest=raw_sha(b"other")), "citation.exact_original_segment"),
                (lambda r: r["dependency_edges"].append(["non-flow", "new-unlisted"]), "response.new_missing_dependency"),
            ]:
                with self.subTest(phase=phase, boundary=expected):
                    changed = deepcopy(original)
                    mutate(changed)
                    self.blocked(expected, lambda: core.verify_response(self.plan, node, changed))

    def test_reported_conflict_omission_boundary_unresolved_stops_before_later_call(self):
        for key, reason in [("findings", "cross-segment conflict"), ("findings", "omitted audit"),
                            ("unresolved", "semantic boundary not established")]:
            node = self.plan["nodes"][0]
            result = authored_response(self.plan, node)
            result[key].append({"obligation_id": "non-flow", "reason": reason, "citations": [citation(self.plan, "source.1")]})
            self.blocked("response.unresolved_or_conflict", lambda: core.verify_response(self.plan, node, result))
        self.alter_response = lambda node, response: response["findings"].append(
            {"obligation_id": "non-flow", "reason": "audit omitted", "citations": [citation(self.plan, "source.1")]})
        with self.composition():
            self.blocked("response.unresolved_or_conflict", lambda: core.execute_workflow(
                self.root, run_dir=self.root / "logs/ci/native", plan=self.plan))
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(len(self.session.reservations), 1)
        self.assertEqual(len(self.session.failures), 1)
        self.assertFalse(self.session.completed)

    def test_bounded_final_keeps_globals_full_evidence_without_all_originals_or_drafts(self):
        results = {}
        for node in self.plan["nodes"]:
            envelope = core._envelope(self.root, self.plan, node, results)
            # Inspect actual schema dictionaries only. Business value_json is a
            # string format, never recursively parsed as a provider subschema.
            self.assert_portable_output_schema(core.output_schema(envelope))
            self.assertEqual(envelope["global_constraints"][0]["text"].encode(), GLOBAL)
            self.assertEqual(envelope["global_constraints"][0]["raw_digest"], raw_sha(GLOBAL))
            if node["phase"] == "independent-review":
                self.assertEqual({s["segment_id"] for s in envelope["original_segments"]},
                                 {"source.0", "source.1", "candidate-A.0", "candidate-B.0", "candidate-C.0"})
            response = authored_response(self.plan, node)
            core.verify_response(self.plan, node, response)
            results[node["node_id"]] = {"result_digest": codec.canonical_digest(response), "response": response}
        final = core._envelope(self.root, self.plan, self.plan["nodes"][-1], results)
        self.assertEqual(final["original_segments"], [])
        self.assertEqual([p["node_id"] for p in final["predecessors"]], ["joint-panel"])
        self.assertEqual(final["predecessors"][0]["output"]["dependency_edges"], ORACLE["edges"])
        request = self.render(self.plan, self.plan["nodes"][-1], results=results)
        requests.verify_rendered_request(self.root, request)
        self.assertEqual(json.loads(request["full_request"])["output_schema"], core.output_schema(final))
        self.assertNotIn(LEFT.decode() + RIGHT.decode(), request["full_request"])
        self.assertIn("Derived predecessor decisions are not lossless", request["model_prompt"])

    def test_final_wrapper_capacity_before_reservation_and_opaque_reconstruction(self):
        first = self.plan["nodes"][0]
        request = self.render(self.plan, first)
        self.assertEqual(request["request_sha256"], raw_sha(request["full_request"].encode()))
        self.assertLessEqual(request["measurement"]["input_token_estimate"], 70000)
        self.blocked("request_not_issued", lambda: requests.verify_rendered_request(self.root, dict(request)))
        # Deterministic conservative UTF-8 upper bound is an original supported
        # counter mode; only size is synthetic, never a caller measurement API.
        original_measure = requests._measure
        def oversized(text, reserve):
            report = deepcopy(original_measure(text, reserve))
            report.update(input_token_estimate=70001, token_counter="max(o200k_base,cl100k_base)+10_percent",
                          token_counts={"o200k_base": 63637, "cl100k_base": 63637})
            return report
        with self.composition(), patch.object(requests, "_measure", side_effect=oversized):
            self.blocked("input_over_70000", lambda: core.execute_workflow(self.root,
                run_dir=self.root / "logs/ci/native", plan=self.plan))
        self.assertFalse(self.session.reservations)
        self.assertFalse(self.dispatched)

    def test_selection_equal_candidate_dimension_cells_and_one_original_winner(self):
        node = self.plan["nodes"][-1]
        response = authored_response(self.plan, node)
        expected = [(c, d) for c in "ABC" for d in ORACLE["dimensions"]]
        self.assertEqual([(r["candidate_label"], r["dimension"]) for r in response["comparisons"]], expected)
        for mutate, expected_error in [
            (lambda r: r["comparisons"].pop(), "comparison.missing_duplicate_order"),
            (lambda r: r["comparisons"].append(deepcopy(r["comparisons"][0])), "comparison.missing_duplicate_order"),
            (lambda r: r["comparisons"].reverse(), "comparison.missing_duplicate_order"),
            (lambda r: r["comparisons"][0].update(obligation_ids=["shared-command"]), "comparison.equal_denominator"),
            (lambda r: r.update(selected_label="A+B"), "selection.original_candidate_only"),
        ]:
            changed = deepcopy(response)
            mutate(changed)
            self.blocked(expected_error, lambda: core.verify_response(self.plan, node, changed))

    def test_candidate_order_blind_identity_and_partition_small_fit_preservation(self):
        observed = []
        for index, (order, split) in enumerate([(("complete", "drops-audit", "wrong-order"), True),
                                               (("wrong-order", "complete", "drops-audit"), True),
                                               (("drops-audit", "wrong-order", "complete"), False)]):
            _, plan = authored_case(self.root, order=order, split=split, run_id="permutation-" + str(index))
            outputs = [core.verify_response(plan, node, authored_response(plan, node)) for node in plan["nodes"]]
            winner = next(c["candidate_id"] for c in plan["manifest"]["candidates"] if c["label"] == outputs[-1]["selected_label"])
            observed.append(winner)
            self.assertEqual([d["statement"] for d in outputs[-1]["decisions"]], list(ORACLE["meanings"].values()))
        self.assertEqual(observed, [ORACLE["winner"]] * 3)
        other = deepcopy(self.plan)
        other["manifest"]["candidates"].reverse()
        resign(other["manifest"], "manifest_digest")
        resign(other, "plan_digest")
        self.blocked("selection.fixed_equal_blind_candidates", lambda: core.validate_plan(other))

    def test_completed_resume_replays_without_dispatch_and_unknown_never_retries(self):
        with self.composition():
            first = core.execute_workflow(self.root, run_dir=self.root / "logs/ci/native", plan=self.plan)
            paid = len(self.session.reservations)
            self.dispatched.clear()
            second = core.execute_workflow(self.root, run_dir=self.root / "logs/ci/native", plan=self.plan)
            self.assertEqual(first, second)
            self.assertEqual(len(self.session.reservations), paid)
            self.assertFalse(self.dispatched)
            self.session.blocked = "unknown-retains-charge"
            self.blocked("journal.blocked", lambda: core.execute_workflow(self.root,
                run_dir=self.root / "logs/ci/native", plan=self.plan))
            self.assertEqual(len(self.session.reservations), paid)
            self.assertFalse(self.dispatched)

    def test_stale_original_and_reordered_or_dictionary_resume_cannot_authorize(self):
        with self.composition():
            core.execute_workflow(self.root, run_dir=self.root / "logs/ci/native", plan=self.plan)
            completed = deepcopy(self.session.completed)
            self.dispatched.clear()
            self.session.completed.reverse()
            self.blocked("journal.prefix_order", lambda: core.execute_workflow(self.root,
                run_dir=self.root / "logs/ci/native", plan=self.plan))
            self.session.completed = completed
            first = completed[0]
            self.blocked("result.genuine_factory_token", lambda: core.validate_verified_result(
                self.plan, self.plan["nodes"][0], first["reservation"], first["result"]))
            path = self.root / "docs/case/source.txt"
            path.write_bytes(LEFT + RIGHT + b"changed\n")
            self.blocked("manifest.original_changed", lambda: core.execute_workflow(self.root,
                run_dir=self.root / "logs/ci/native", plan=self.plan))
            self.assertFalse(self.dispatched)

    def test_high_no_tools_original_execution_replay_rejects_invalid_protocol(self):
        node = self.plan["nodes"][0]
        request = self.render(self.plan, node)
        logical_response = authored_response(self.plan, node)
        physical_response = core.encode_response_wire(logical_response)
        output = json.dumps(physical_response, separators=(",", ":"))
        schema = codec.strict_json_loads(request["schema_path"].read_bytes())
        original = high_protocol(Path(request["workspace"]), prompt=request["model_prompt"], output=output, schema=schema)
        actual, proof = app_server.replay(encoded(original), prompt=request["model_prompt"], schema=schema)
        self.assertEqual(actual, output)
        envelope = requests.read_input_envelope(self.root, Path(request["workspace"]))
        self.assertEqual(core.decode_response_wire(codec.strict_json_loads(actual), envelope), logical_response)
        self.assertEqual(proof["requested_reasoning_effort"], "high")
        self.assertEqual(proof["runtime_reasoning_effort"], "high")
        for kind in ("low", "tool", "incomplete", "wrong-input", "wrong-schema", "wrong-output"):
            # Independent JSON observations avoid the fixture helper's shared
            # Python item object making both transcript events change together.
            rows = json.loads(json.dumps(original))
            prompt, supplied_schema = request["model_prompt"], schema
            for row in rows:
                message = row["message"]
                if kind == "low" and row["direction"] == "server" and message.get("id") == 2:
                    message["result"]["reasoningEffort"] = "low"
                if kind == "tool" and message.get("method") == "thread/start":
                    message["params"]["dynamicTools"] = [{"name": "forbidden"}]
                if kind == "incomplete" and message.get("method") == "turn/completed":
                    message["params"]["turn"]["status"] = "failed"
                if kind == "wrong-output" and message.get("method") == "item/completed":
                    message["params"]["item"]["text"] = "{}"
            if kind == "wrong-input":
                prompt += "different"
            if kind == "wrong-schema":
                supplied_schema = {"type": "object"}
            expected = (self.assertRaisesRegex(ValueError, "requested_reasoning_effort_mismatch")
                        if kind == "low" else self.assertRaises(ValueError))
            with self.subTest(kind=kind), expected:
                app_server.replay(encoded(rows), prompt=prompt, schema=supplied_schema)
        for identity in ("thread", "turn"):
            def reuse_identity(node, records):
                def replace(value):
                    if isinstance(value, dict):
                        for key, child in list(value.items()):
                            value[key] = replace(child)
                        return value
                    if isinstance(value, list):
                        return [replace(child) for child in value]
                    if isinstance(value, str) and value.startswith(identity + "-"):
                        return identity + "-reused-across-prefix"
                    return value
                replace(records)
            self.alter_protocol = reuse_identity
            with self.subTest(reused=identity), self.composition():
                self.blocked("execution.reused_thread_or_turn", lambda: core.execute_workflow(self.root,
                    run_dir=self.root / "logs/ci/native", plan=self.plan))
            # The first real replay succeeded. The second distinct complete
            # prompt/schema/output turn, not a malformed first fixture, reached
            # the cross-prefix independence owner and remained charged.
            self.assertEqual(len(self.dispatched), 2)
            self.assertEqual(len(self.session.completed), 1)
            self.assertEqual(len(self.session.reservations), 2)
            self.assertEqual(len(self.session.failures), 1)
            self.assertEqual(self.session.blocked, "unknown-retains-charge")
        del self.alter_protocol

    def test_native_born_missing_or_legacy_flag_and_finite_budget_never_reset(self):
        with patch.dict(sys.modules, {"_b_route_segmented_runtime": None}), patch.object(
                Path, "read_bytes", side_effect=AssertionError("No source/run bytes before missing born owner")):
            for state in ({"run_id": "c4"}, {"run_id": "m4", "segmented": True},
                          {"schema_version": core.NATIVE_RUN, "protocol": core.PROTOCOL, "verified": True}):
                self.blocked("segmented_native_born_contract_unavailable", lambda: core.require_segmented_run(
                    self.root, self.root / "logs/ci/native", state, self.plan))
        budget = self.plan["budget"]
        self.assertEqual(budget, {"native_limit": 192, "campaign_limit": 290,
            "released": 0, "worst_case_calls": len(self.plan["nodes"])})
        self.assertNotIn("retained_paid_or_unknown", budget)  # Only the native ledger can assert actual liabilities.
        for key, value in (("released", 1), ("native_limit", 193),
                           ("campaign_limit", 291), ("worst_case_calls", 1)):
            changed = deepcopy(self.plan)
            changed["budget"][key] = value
            resign(changed, "plan_digest")
            self.blocked("budget.worst_case", lambda: core.validate_plan(changed))
        sensitive = write(self.root, "docs/case/credentials/auth.json", b'{"benign":"fixture"}')
        original_read = Path.read_bytes
        observed = []
        def observed_read(path):
            observed.append(Path(path))
            if Path(path) == sensitive:
                raise AssertionError("Sensitive role reached bytes access")
            return original_read(path)
        with patch.object(Path, "read_bytes", observed_read):
            self.blocked("reference.sensitive_role", lambda: core._read(self.root, "docs/case/credentials/auth.json"))
        self.assertNotIn(sensitive, observed)


if __name__ == "__main__":
    unittest.main()
