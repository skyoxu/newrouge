"""Offline 3B contracts and explicit positive assembly seams, never real AC proof.

Audit preparation uses the existing named fixture seam. Positive model responses
below patch only replay in this test process; no public switch accepts them.
OS-child tests retain the real reader and demonstrate rejection of that seam.
"""
from copy import deepcopy
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import _b_route_planning_runtime as runtime
import _b_route_planning_input as planning
import _b_route_codec as codec
import _mvg_capability_append as append
import _mvg_capability_selection as selection
import _mvg_capability_checkpoint as checkpoint
import _mvg_capability_worker as worker
import _planning_execution_binding as execution_binding
import _planning_skill_common as common
import codex_isolated_model_runner as official
import dev_cli
import dev_cli_builders as builders
import plan_mvg
import plan_capabilities
import test_b_route_candidate as candidate_fixture
import test_codex_app_server_stdio as protocol_fixture


@unittest.skipUnless(sys.platform.startswith("linux"), "Actual Linux atomic publication")
class LinuxInitialPublicationTests(unittest.TestCase):
    """Actual storage/process boundaries; fixture payloads grant no native proof."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nr-pub-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_existing_empty_nonempty_and_file_targets_are_never_replaced(self):
        for kind in ("empty", "nonempty", "file"):
            with self.subTest(kind=kind):
                source = self.root / ("source-" + kind)
                source.mkdir()
                (source / "payload").write_bytes(b"new owned payload")
                target = self.root / kind
                if kind == "file":
                    target.write_bytes(b"foreign file")
                else:
                    target.mkdir()
                    if kind == "nonempty":
                        (target / "prior").write_bytes(b"foreign directory")
                inode = target.stat().st_ino
                with self.assertRaises(FileExistsError):
                    runtime._publish_run_directory(source, target)
                self.assertEqual(inode, target.stat().st_ino)
                self.assertEqual(b"new owned payload", (source / "payload").read_bytes())
                if kind == "file":
                    self.assertEqual(b"foreign file", target.read_bytes())
                elif kind == "nonempty":
                    self.assertEqual(b"foreign directory", (target / "prior").read_bytes())
                else:
                    self.assertEqual([], list(target.iterdir()))

    def test_two_real_initializers_have_one_complete_winner_and_retained_loser(self):
        import time
        script = r'''
import json, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[3])
import _b_route_planning_runtime as runtime
root, owner = Path(sys.argv[1]), sys.argv[2]
publish = runtime._publish_run_directory
def synchronized(source, target):
    (root / ('ready-' + owner)).write_bytes(b'ready')
    until = time.monotonic() + 10
    while not (root / 'release').exists():
        if time.monotonic() > until:
            raise TimeoutError('Fixture release missing')
        time.sleep(.01)
    publish(source, target)
runtime._publish_run_directory = synchronized
state = {'run_id':'n', 'runtime_identity':owner, 'fixture_owner':owner}
try:
    runtime.publish_initial_run(root, root/'logs/ci/mvg-planning/n', state, {'fixture_owner':owner})
except FileExistsError:
    raise SystemExit(17)
'''
        processes = [subprocess.Popen([sys.executable, "-B", "-c", script, str(self.root), owner,
                         str(Path(runtime.__file__).parent)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for owner in ("one", "two")]
        try:
            until = time.monotonic() + 10
            while not all((self.root / ("ready-" + owner)).exists() for owner in ("one", "two")):
                self.assertTrue(all(p.poll() is None for p in processes))
                self.assertLess(time.monotonic(), until)
                time.sleep(.01)
            (self.root / "release").write_bytes(b"release both initializers")
            outcomes = [p.communicate(timeout=10) for p in processes]
            self.assertEqual([0, 17], sorted(p.returncode for p in processes), outcomes)
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
        target = self.root / "logs/ci/mvg-planning/n"
        state = json.loads((target / "run.json").read_bytes())
        frozen = json.loads((target / "analysis-input/b-route-prepared.json").read_bytes())
        initialization = json.loads((target / "initialization.json").read_bytes())
        self.assertEqual(state["fixture_owner"], frozen["fixture_owner"])
        self.assertEqual(runtime.canonical_sha(state), initialization["initial_state_sha256"])
        self.assertEqual(runtime.canonical_sha(frozen), initialization["frozen_sha256"])
        staging = list(target.parent.glob(".init-*"))
        self.assertEqual(1, len(staging))
        self.assertNotEqual(state["fixture_owner"], json.loads((staging[0] / "run.json").read_bytes())["fixture_owner"])

    def test_interrupted_staging_is_retained_without_authoritative_partial_run(self):
        target = self.root / "logs/ci/mvg-planning/n"
        original = runtime.atomic_json
        def fail_before_state(path, value):
            if path.name == "run.json":
                raise OSError("fixture_staging_interrupt")
            return original(path, value)
        with patch.object(runtime, "atomic_json", side_effect=fail_before_state), self.assertRaisesRegex(OSError, "staging_interrupt"):
            runtime.publish_initial_run(self.root, target, {"run_id":"n", "runtime_identity":"fixture"}, {"fixture":True})
        self.assertFalse(target.exists())
        staging = list(target.parent.glob(".init-*"))
        self.assertEqual(1, len(staging))
        self.assertEqual({"fixture":True}, json.loads((staging[0] / "analysis-input/b-route-prepared.json").read_bytes()))

    def test_postpublication_interrupt_keeps_complete_identity_for_existing_owner_reentry(self):
        target = self.root / "logs/ci/mvg-planning/n"
        state = {"run_id":"n", "runtime_identity":"fixture"}
        publish = runtime._publish_run_directory
        def interrupted(source, destination):
            publish(source, destination)
            raise OSError("fixture_after_publication")
        with patch.object(runtime, "_publish_run_directory", side_effect=interrupted), self.assertRaises(FileExistsError):
            runtime.publish_initial_run(self.root, target, state, {"fixture":True})
        self.assertEqual(state, json.loads((target / "run.json").read_bytes()))
        before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            runtime.publish_initial_run(self.root, target, state, {"fixture":True})
        self.assertEqual(before, {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()})

    def test_missing_or_unsupported_noreplace_never_uses_ordinary_rename(self):
        import ctypes
        import errno
        from types import SimpleNamespace
        source, target = self.root / "source", self.root / "target"
        source.mkdir()
        def unsupported(*_args):
            ctypes.set_errno(errno.EOPNOTSUPP)
            return -1
        for library in (SimpleNamespace(), SimpleNamespace(renameat2=unsupported)):
            with self.subTest(library=library), patch.object(ctypes, "CDLL", return_value=library), \
                 patch.object(os, "rename", side_effect=AssertionError("No ordinary rename fallback")), self.assertRaises(OSError):
                runtime._publish_run_directory(source, target)
            self.assertTrue(source.exists())
            self.assertFalse(target.exists())


def carrier(draft):
    """Synthetic producer fixture; production never constructs semantic content."""
    return {**{key: deepcopy(value) for key, value in draft.items() if key != "content"},
            "producer_schema_version": runtime.DRAFT_CARRIER,
            "content_json": json.dumps(draft["content"], ensure_ascii=False, separators=(",", ":"), allow_nan=False)}


def fixture_review_carrier(review, materials):
    """Encode only synthetic provider output using the actual request codebooks."""
    if materials.get("review_source_policy") != runtime.REVIEW_SOURCE_POLICY:
        return deepcopy(review)  # Preserve the historical absent/v1 fixture response.
    obligations = materials["obligations"]
    sources = materials["qualified_sources"]
    obligation_indices = {row["id"]: index for index, row in enumerate(obligations)}
    source_indices = {row["id"]: index for index, row in enumerate(sources)}
    assert len(obligation_indices) == len(obligations) and len(source_indices) == len(sources)
    value = deepcopy(review)
    value["schema_version"] = runtime.INDEXED_REVIEW
    for row in value["checks"]:
        row["id"] = obligation_indices[row["id"]]
        row["source_block_ids"] = [source_indices[source] for source in row["source_block_ids"]]
    return value


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = candidate_fixture.CandidateTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.frozen = self.fixture.frozen
        self.ref = self.fixture.prepared["resume_ref"]
        self.value = self.fixture.value

    def create(self, profile="3b-mvg-v1", run_id="runtime", *, complete_wire=False, wire_delivery=runtime.wire.SCHEMA):
        planner = runtime.PROFILES[profile][0]
        directory = runtime.run_location(self.root, planner, run_id)
        state = runtime.create_run(self.root, directory, run_id, self.ref, profile)
        # These pre-loop-four fixtures explicitly replay the historical producer
        # and machine-adaptation policy. Fresh create/producer activation is
        # exercised without this fixture conversion in test_b_route_loop4_runtime.
        state.pop("b_route_output_schema_policy")
        state.pop("b_route_machine_business_policy")
        if not complete_wire:
            # Explicit historical plain/core fixture; new native runs keep the delivery tag.
            state["planning_runtime"].pop("wire_delivery")
            state["runtime_identity"] = common.canonical_sha(state["planning_runtime"])
            common.atomic_json(directory / "run.json", state)
        else:
            # Existing complete-wire fixtures explicitly retain historical v1.
            state["planning_runtime"]["wire_delivery"] = wire_delivery
            state["runtime_identity"] = common.canonical_sha(state["planning_runtime"])
            common.atomic_json(directory / "run.json", state)
        return directory, state

    def test_profiles_preserve_cardinality_defaults_and_no_legacy_objects(self):
        for profile, size, limit in (("3b-mvg-v1", 3, 192), ("3b-capabilities-v1", 2, 96)):
            run, state = self.create(profile, profile)
            self.assertEqual(len(runtime.labels(state)), size)
            self.assertEqual(state["mvg.run_invocation_limit"], limit)
            self.assertNotIn("formal_ready", state)
            self.assertEqual(runtime.scopes(state, run / "analysis-input")[0]["unit_kind"], "governed_planning_closure")
            self.assertEqual(runtime.seed(state, run / "analysis-input")["contexts"], self.frozen["inputs"]["contexts"])
            self.assertEqual(runtime.frozen_input(self.root, state), self.frozen)
        self.assertFalse((self.root / ".taskmaster").exists())
        self.assertFalse((self.root / "docs/planning/semantic-topology").exists())

    def test_unknown_profiles_descriptor_input_and_rules_drift_fail_before_dispatch(self):
        run, state = self.create()
        for mutate in (lambda s: s["planning_runtime"].update(profile="import:arbitrary.module"),
                       lambda s: s["planning_runtime"].update(input_identity="changed"),
                       lambda s: s.update(input_stage="legacy"),
                       lambda s: s.update(**{"mvg.run_invocation_limit": 193})):
            changed = deepcopy(state)
            mutate(changed)
            with self.assertRaises(ValueError):
                runtime.validate_input(self.root, run, changed)
        original = self.root / "docs/source.md"
        original.write_bytes(original.read_bytes() + b"drift")
        with self.assertRaises(ValueError):
            runtime.frozen_input(self.root, state)

    def test_complete_extra_materials_remeasured_and_chain_not_mutated(self):
        run, state = self.create()
        frozen_hash = codec.canonical_digest(self.frozen)
        base = runtime.seed(state, run / "analysis-input")
        payload = runtime.request_payload(self.frozen, phase="generation", seed_value=base, batch=1)
        measured = runtime.measure_actual(self.frozen, json.dumps(payload), planning.output_schema())
        payload["accepted_seed"]["extra_original"] = "x" * 10000
        larger = runtime.measure_actual(self.frozen, json.dumps(payload), planning.output_schema())
        self.assertGreater(larger["request_bytes"], measured["request_bytes"])
        self.assertEqual(codec.canonical_digest(self.frozen), frozen_hash)
        with self.assertRaises(ValueError):
            runtime.request_payload(self.frozen, phase="generation", seed_value=base, batch=2, drafts=[])
        with self.assertRaises(ValueError):
            runtime.request_payload(self.frozen, phase="semantic", seed_value=base)
        with self.assertRaises(ValueError):
            runtime.measure_actual(self.frozen, "x" * (self.frozen["inputs"]["contract"]["limits"]["max_bytes"] + 1), {})

    def test_generation_producer_metadata_consts_preserve_complete_drafts_and_frozen_bytes(self):
        import jsonschema
        run, state = self.create()
        before = {p: p.read_bytes() for p in (self.root / Path(self.ref).parent).rglob("*") if p.is_file()}
        frozen_before = deepcopy(self.frozen)
        base = runtime.seed(state, run / "analysis-input")
        drafts = []
        # The original successor API also accepts a complete synthesis predecessor;
        # two parent identities make ordering independently observable here.
        stages = [*range(1, len(self.frozen["transport"]["batches"]) + 1), None, None]
        for batch in stages:
            payload = runtime.request_payload(self.frozen, phase="generation", seed_value=base, drafts=drafts, batch=batch)
            original = deepcopy(payload["root_request"])
            schema = runtime.generation_schema(self.frozen, original)
            expected = deepcopy(self.frozen["inputs"]["delivery"]["output_schema"])
            expected["properties"]["schema_version"]["type"] = "string"
            expected["properties"]["stage"]["type"] = "string"
            values = {"input_identity": self.frozen["input_identity"], "stage": original["input"]["stage"],
                "ordinal": original["input"]["ordinal"], "parent_draft_identities": [row["identity"] for row in original["input"]["prior_drafts"]]}
            for key, value in values.items():
                expected["properties"][key]["const"] = value
            expected["properties"].pop("content")
            expected["properties"]["producer_schema_version"] = {"type": "string", "const": runtime.DRAFT_CARRIER}
            expected["properties"]["content_json"] = {"type": "string", "minLength": 1}
            expected["required"] = [field for field in expected["required"] if field != "content"] + ["producer_schema_version", "content_json"]
            self.assertEqual(schema, expected)
            self.assertEqual(original, payload["root_request"])
            self.assertEqual([row["value"] for row in original["input"]["prior_drafts"]], drafts)
            value = {"schema_version": planning.DRAFT, **values, "content": deepcopy(self.value["content"])}
            jsonschema.Draft202012Validator(schema).validate(carrier(value))
            self.assertEqual(runtime.decode_generation_carrier(carrier(value)), value)
            for key, wrong in (("input_identity", values["input_identity"] + "7"), ("stage", "synthesis" if batch else "batch"),
                               ("ordinal", values["ordinal"] + 1), ("parent_draft_identities", ["foreign"] )):
                changed = deepcopy(value)
                changed[key] = wrong
                self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(carrier(changed))))
                with self.assertRaises(ValueError):
                    planning.validate_draft_chain(self.frozen, [*drafts, changed])
            if len(drafts) > 1:
                reordered = deepcopy(value)
                reordered["parent_draft_identities"].reverse()
                self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(carrier(reordered))))
            drafts.append(value)
            planning.validate_draft_chain(self.frozen, drafts)
        self.assertEqual(self.frozen, frozen_before)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_all_actual_producer_schemas_declare_string_const_and_enum_types(self):
        frozen_before = deepcopy(self.frozen)
        for profile in ("3b-mvg-v1", "3b-capabilities-v1"):
            run, state = self.create(profile, profile)
            payload = runtime.request_payload(self.frozen, phase="generation", seed_value=runtime.seed(state, run / "analysis-input"), batch=1)
            schemas = (runtime.generation_schema(self.frozen, payload["root_request"]),
                       runtime.review_producer_schema(state, self.value, self.frozen), runtime.selection_schema(state))
            for schema in schemas:
                for row in runtime.candidate.walk(schema):
                    if row.get("type") == "object":
                        self.assertIs(row.get("additionalProperties"), False, row)
                        self.assertEqual(set(row.get("required", [])), set(row.get("properties", {})))
                    if isinstance(row.get("const"), str) or ("enum" in row and all(isinstance(value, str) for value in row["enum"])):
                        self.assertEqual(row.get("type"), "string", row)
            self.assertEqual(schemas[0]["properties"]["schema_version"], {"const": planning.DRAFT, "type": "string"})
            for field in ("schema_version", "input_identity", "runtime_identity", "proposal_sha256", "verdict"):
                self.assertEqual(schemas[1]["properties"][field]["type"], "string")
            schema = schemas[2]
            self.assertEqual(schema["properties"]["status"], {"type": "string", "const": "selected"})
            self.assertEqual(schema["properties"]["selected"]["type"], "string")
        self.assertEqual(self.frozen, frozen_before)
        self.assertNotIn("type", self.frozen["inputs"]["delivery"]["output_schema"]["properties"]["schema_version"])
        self.assertNotIn("type", self.frozen["inputs"]["delivery"]["output_schema"]["properties"]["stage"])

    def test_generation_carrier_strict_lossless_unknown_nested_json_and_rejection(self):
        content = {"unknown": {"strings": ["", "  \r\n", "\u0000", "\u4e2d\u6587", "quotes \" \\ paths"],
            "types": [None, True, False, 0, 1, -1, 1.25, -0.0, 10 ** 80, [], {}, [{"deep": [False, 1]}]]},
            "content_json": "A user field with the same name remains untouched", "schema_version": "unknown original metadata"}
        draft = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"], "stage": "batch", "ordinal": 1,
                 "parent_draft_identities": [], "content": content}
        wire = carrier(draft)
        before = deepcopy(wire)
        decoded = runtime.decode_generation_carrier(codec.strict_json_loads(json.dumps(wire, ensure_ascii=False).encode()))
        self.assertTrue(runtime.same_json(decoded, draft), "Exact JSON types and unknown values survive")
        self.assertEqual(wire, before)
        self.assertEqual(decoded["content"]["unknown"]["strings"], content["unknown"]["strings"])
        for text in ("", "[]", "null", "42", '{"duplicate":1,"duplicate":2}', '{"nonfinite":NaN}', '{"overflow":1e999}', '{"broken":'):
            with self.subTest(content_json=text):
                changed = {**wire, "content_json": text}
                with self.assertRaises(ValueError):
                    runtime.decode_generation_carrier(changed)
        for changed in ({**wire, "producer_schema_version": "unknown"}, {**wire, "unexpected": True},
                        {**wire, "content_json": {}}, {**wire, "ordinal": True}, draft):
            with self.assertRaises(ValueError):
                runtime.decode_generation_carrier(changed)
        with self.assertRaises(ValueError):
            codec.strict_json_loads('{"producer_schema_version":"a","producer_schema_version":"b"}')

    def test_generation_producer_schema_rederived_before_dispatch_and_bound_replay(self):
        run, state = self.create()
        state["runner_configuration"] = {"backend_info": official.description()}
        base = runtime.seed(state, run / "analysis-input")
        payload = runtime.request_payload(self.frozen, phase="generation", seed_value=base, batch=1)
        payload.update(runtime_identity=state["runtime_identity"], run_id=state["run_id"], lineage_identity="fixture-lineage")
        expected = runtime.generation_schema(self.frozen, payload["root_request"])
        workspace = run / "schema-preflight"
        workspace.mkdir()
        schema_path, prompt = workspace / "schema.json", workspace / "prompt.txt"
        binding = {"prompt_path": str(prompt), "schema_path": str(schema_path)}
        for change in ("missing-const", "foreign-const", "semantic-constraint", "forged-root"):
            with self.subTest(change=change):
                materials, schema = deepcopy(payload), deepcopy(expected)
                if change == "missing-const":
                    schema["properties"]["input_identity"].pop("const")
                elif change == "foreign-const":
                    schema["properties"]["ordinal"]["const"] += 1
                elif change == "semantic-constraint":
                    schema["properties"]["content_json"]["const"] = '{"host_invented":true}'
                else:
                    materials["root_request"]["input"]["ordinal"] += 1
                materials["actual_output_schema"] = schema
                materials["materials_identity"] = common.canonical_sha({k: v for k, v in materials.items() if k != "materials_identity"})
                common.atomic_json(schema_path, schema)
                prompt.write_text("Use complete governed originals\n" + json.dumps(materials), encoding="utf-8")
                with self.assertRaises(ValueError):
                    runtime.bound_materials(binding, state, self.frozen)
                with self.assertRaises(ValueError):
                    runtime.prepare_dispatch(self.root, run, state, Path(official.__file__), workspace, prompt,
                        schema_path, workspace / "output.json", 1, run / "binding.json", timeout_sec=5)
        self.assertNotIn("capability_selection", state)

    def test_machine_structure_is_not_real_execution_or_manual_admission(self):
        run, state = self.create()
        self.assertEqual(runtime.machine(self.root, state, self.value), [])
        fake = runtime.admission_proof(state, runtime.seed(state, run / "analysis-input"),
            runtime.scopes(state, run / "analysis-input"), [], self.value)
        self.assertTrue(runtime.proof_errors(self.root, state, self.value, fake))
        with self.assertRaises(ValueError):
            runtime.verify_call({"synthetic": True})

    def test_independent_semantics_accounts_every_requirement_flow_facet_and_source(self):
        run, state = self.create()
        obligations = runtime.obligations(self.value, self.frozen)
        facets = [row["target"] for row in obligations]
        for aspect in ("graph", "handoffs", "ui", "human_verification"):
            self.assertTrue(any(row[0] == "flow" and row[2] == aspect for row in facets))
        self.assertEqual(len([r for r in facets if r[0] == "flow_branch"]), 3)
        self.assertEqual(len([r for r in facets if r[0] == "flow_part"]), 4)
        self.assertEqual(len([r for r in facets if r[0] == "source"]), 2)
        review = {"schema_version": runtime.REVIEW, "runtime_identity": state["runtime_identity"],
            "input_identity": self.frozen["input_identity"], "proposal_sha256": common.canonical_sha(self.value),
            "verdict": "approved", "findings": [], "checks": [{"id": row["id"], "verdict": "approved",
                "rationale": "Offline assembly seam source-backed review", "source_block_ids": row["source_block_ids"][:1]} for row in obligations]}
        self.assertEqual(runtime.review_issues(state, self.value, self.frozen, review), [])
        review["checks"][0]["verdict"] = "blocked"
        review.update(verdict="blocked", findings=[review["checks"][0]["rationale"]])
        self.assertTrue(runtime.review_issues(state, self.value, self.frozen, review))
        for change in (lambda r: r["checks"].pop(), lambda r: r["checks"][0].update(source_block_ids=[]),
                       lambda r: r["checks"][0].update(id=r["checks"][1]["id"])):
            altered = deepcopy(review)
            change(altered)
            with self.assertRaises(ValueError):
                runtime.review_issues(state, self.value, self.frozen, altered)

    def review(self, state, proposal=None, frozen=None):
        """Build every check from actual obligations and their qualified sources."""
        proposal, frozen = proposal or self.value, frozen or self.frozen
        return {"schema_version": runtime.REVIEW, "runtime_identity": state["runtime_identity"],
            "input_identity": frozen["input_identity"], "proposal_sha256": common.canonical_sha(proposal),
            "verdict": "approved", "findings": [], "checks": [{"id": row["id"], "verdict": "approved",
                "rationale": "Offline source-qualified check", "source_block_ids": row["source_block_ids"][:1]}
                for row in runtime.obligations(proposal, frozen)]}

    def repair_issue_for(self, state, target):
        """Derive a synthetic blocked finding from its actual obligation owner."""
        obligation = next(row for row in runtime.obligations(self.value, self.frozen) if row["target"] == target)
        review = self.review(state)
        check = next(row for row in review["checks"] if row["id"] == obligation["id"])
        check.update(verdict="blocked", rationale="Synthetic issue at this exact obligation")
        review.update(verdict="blocked", findings=[check["rationale"]])
        return runtime.review_issues(state, self.value, self.frozen, review)[0]

    def test_two_actual_flows_and_helper_only_source_migration_mutation(self):
        """Check both actual Flow obligations and a helper-only source mutation."""
        import _b_route_execution_transition as transition
        proposal = deepcopy(self.value)
        proposal["content"]["definitions"]["flows"].append(self.fixture.flow("OTHER"))
        required = runtime.obligations(proposal, self.frozen)
        self.assertEqual({row["target"][1] for row in required if row["target"][0] == "flow"}, {"FLOW", "OTHER"})
        old, new = self.root / "source-old", self.root / "source-new"
        for root in (old, new):
            target = root / "scripts/python"
            target.mkdir(parents=True)
            for reference in transition._ALLOWED | {transition._HOST_FAULT_MODULE}:
                name = Path(reference).name
                shutil.copyfile(Path(runtime.__file__).with_name(name), target / name)
        transition._semantic_unchanged(old, new)
        path = new / "scripts/python/_b_route_planning_runtime.py"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("return flows, source_blocks"), 1)
        path.write_text(text.replace("return flows, source_blocks", "return flows[:1], source_blocks"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "canonical_semantics_changed"):
            transition._semantic_unchanged(old, new)

    def test_repair_domain_keeps_unrelated_flow_requirement_source_and_parts(self):
        run, state = self.create()
        issue = self.repair_issue_for(state, ["flow", "FLOW", "entry_condition"])
        revised = deepcopy(self.value)
        revised["content"]["definitions"]["flows"][0]["entry_condition"] = "Explicit revised source-backed entry"
        self.assertEqual(runtime.repair_scope_errors(self.root, state, self.value, revised, issue), [])
        changes = (
            lambda value: value["content"]["definitions"]["flows"][0]["parts"][0].update(rationale="Still legal but unrelated"),
            lambda value: value["content"]["requirements"][0].update(acceptance_intent="Unrelated original change"),
            lambda value: value["content"]["source_identity"].update(source_revision="Unrelated source"),
            lambda value: value["content"]["definitions"]["flows"].append(self.fixture.flow("OTHER")),
        )
        # The first mutation remains structurally valid, exposing the gap that
        # another full semantic review alone could not close deterministically.
        for change in changes:
            value = deepcopy(revised)
            change(value)
            with self.subTest(change=change):
                self.assertIn("b_route_repair_outside_domain", runtime.repair_scope_errors(self.root, state, self.value, value, issue))

    def test_part_and_branch_repair_domain_do_not_grant_other_responsibilities(self):
        run, state = self.create()
        for target_kind, field in (("flow_part", "parts"), ("flow_branch", "branches")):
            target = next(row["target"] for row in runtime.obligations(self.value, self.frozen) if row["target"][0] == target_kind)
            issue = self.repair_issue_for(state, target)
            index = next(n for n, row in enumerate(self.value["content"]["definitions"]["flows"][0][field]) if row["kind"] == target[2])
            revised = deepcopy(self.value)
            revised["content"]["definitions"]["flows"][0][field][index]["rationale"] = "Revised bounded responsibility"
            self.assertEqual(runtime.repair_scope_errors(self.root, state, self.value, revised, issue), [])
            other = (index + 1) % len(revised["content"]["definitions"]["flows"][0][field])
            revised["content"]["definitions"]["flows"][0][field][other]["rationale"] = "Unrelated legal change"
            self.assertIn("b_route_repair_outside_domain", runtime.repair_scope_errors(self.root, state, self.value, revised, issue))

    def test_machine_issue_owns_graph_field_without_granting_other_flow_parts(self):
        run, state = self.create()
        before = deepcopy(self.value)
        boundary = before["content"]["definitions"]["flows"][0]["graph"]["boundaries"][0]
        boundary["required"] = False
        issue = runtime.machine(self.root, state, before)[0]
        self.assertEqual(runtime.repair_scope_errors(self.root, state, before, self.value, issue), [])
        after = deepcopy(self.value)
        after["content"]["definitions"]["flows"][0]["parts"][0]["rationale"] = "Unrelated valid part"
        self.assertIn("b_route_repair_outside_domain", runtime.repair_scope_errors(self.root, state, before, after, issue))

    def test_unknown_issue_or_scope_policy_cannot_expand_repair_domain(self):
        run, state = self.create()
        issue = {"code": "semantic_review_blocked:unknown", "path": "semantic-review", "detail": "Repair every Flow"}
        self.assertEqual(runtime.repair_scope_errors(self.root, state, self.value, self.value, issue), ["b_route_repair_domain_unresolved"])
        materials = {"phase": "generation", "repair_issue": issue, "prior_candidate": self.value}
        with self.assertRaisesRegex(ValueError, "policy_missing"):
            runtime.check_repair_policy(materials, required=True)
        materials["repair_scope_policy"] = "unknown"
        with self.assertRaisesRegex(ValueError, "policy_invalid"):
            runtime.check_repair_policy(materials, required=True)

    def test_repair_replay_rejects_unpaid_cross_slot_and_edited_before(self):
        """A claimed before hash cannot replace earlier paid output in the same slot."""
        run, state = self.create()
        drafts = []
        for number in range(1, len(self.frozen["transport"]["batches"]) + 2):
            drafts.append({"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
                "stage": "batch" if number <= len(self.frozen["transport"]["batches"]) else "synthesis",
                "ordinal": number, "parent_draft_identities": [codec.canonical_digest(row) for row in drafts],
                "content": deepcopy(self.value["content"])})
        prior = deepcopy(self.value)
        prior["provenance"].update(kind="model_draft", upstream_model_history="declared_model", draft_chain=drafts,
                                   final_draft_identity=codec.canonical_digest(drafts[-1]))
        materials = {"prior_candidate": prior, "repair_issue": {}, "lineage_identity": "same-lineage", "lineage_context": 1}
        binding = {"binding_sha256": "synthetic-current", "output_path": str(run / "after.json")}
        current = {"number": 2, "candidate": "candidate-1", "generation": 1, "execution": 1,
                   "request_identity": {"output_path": "after.json"}}
        foreign = {"number": 1, "candidate": "candidate-2", "generation": 1, "execution": 1,
                   "outcome": {"status": "completed"}, "request_identity": {"output_path": "foreign.json"}}
        for calls in ([current], [foreign, current]):
            state["capability_selection"] = {"calls": calls}
            with patch.object(runtime, "verify_reserved_call") as verify:
                with self.assertRaisesRegex(ValueError, "prior_not_original_paid_output"):
                    runtime.verify_repair_origin(self.root, state, self.frozen, materials, binding)
                verify.assert_not_called()
        edited = deepcopy(materials)
        edited["prior_candidate"]["content"]["definitions"]["flows"][0]["entry_condition"] = "Edited original"
        with self.assertRaisesRegex(ValueError, "prior_content_changed"):
            runtime.verify_repair_origin(self.root, state, self.frozen, edited, binding)

    def test_repair_scope_metadata_and_prompt_bind_exact_before_and_paths(self):
        """Host-owned scope cannot expand through edited prompt metadata paths."""
        run, state = self.create()
        issue = self.repair_issue_for(state, ["flow", "FLOW", "entry_condition"])
        delivery = runtime.wire_delivery(state)
        payload = runtime.request_payload(self.frozen, phase="generation",
            seed_value=runtime.seed(state, run / "analysis-input"), batch=1, delivery=delivery)
        payload.update(content_contract=runtime.generation_schemas(), final_content_target=runtime.generation_target(),
            runtime_identity=state["runtime_identity"], run_id=state["run_id"], slot="candidate-1", generation=1, execution=1)
        payload["lineage_identity"] = runtime.lineage_identity(state, payload["accepted_seed"], "candidate-1", 1)
        payload["actual_output_schema"] = runtime.generation_schema(self.frozen, payload["root_request"], delivery=delivery)
        payload.update(prior_candidate=deepcopy(self.value), repair_issue=issue,
            repair_scope_policy=runtime.REPAIR_SCOPE_POLICY,
            repair_scope=runtime.repair_scope_metadata(self.value, self.frozen, issue))
        payload["materials_identity"] = common.canonical_sha({key: value for key, value in payload.items() if key != "materials_identity"})
        runtime.check_repair_policy(payload, required=True, frozen=self.frozen)
        self.assertIn("repair_scope.allowed_content_paths", runtime.materials_prompt(payload).split("\n", 1)[0])
        self.assertIn(["definitions", "flows", 0, "entry_condition"], payload["repair_scope"]["allowed_content_paths"])
        payload["repair_scope"]["allowed_content_paths"].append(["requirements"])
        with self.assertRaisesRegex(ValueError, "metadata_changed"):
            runtime.check_repair_policy(payload, required=True, frozen=self.frozen)

    def test_selected_formal_flow_keeps_its_actual_schema_and_semantic_obligations(self):
        import test_b_route_records as records_fixture
        self.fixture.selected_plan()
        original_path = records_fixture.plan_path()
        original = self.fixture.dependency_models[original_path]
        original_flow = records_fixture.flow("FORMAL-FLOW", "REQ-p")
        original["definitions"]["flows"] = [deepcopy(original_flow)]
        original["requirement_verification"][0].update(disposition="flow", flow_id="FORMAL-FLOW")
        original["coverage_table"][0].update(disposition="flow", flow_id="FORMAL-FLOW")
        original["applicability"][0].update(disposition="flow")
        original["requirement_route_memberships"] = [{"requirement_id": "REQ-p", "flow_id": "FORMAL-FLOW",
            "observable_role": "Original result"}]
        self.fixture.freeze_dependencies("formal-flow", out_of_scope=["REQ-p"])
        self.frozen = self.fixture.frozen
        self.value = self.fixture.value
        # Exercise the real formal record validator and candidate structural owner.
        # Existing formal Flow has required branches/parts, but intentionally has
        # entry/success_end/loops instead of auxiliary graph/UI/human fields.
        result = runtime.candidate.records.validate_record(records_fixture.encoded(original), path=original_path)
        self.assertTrue(result.ok, result.diagnostic)
        store = runtime.candidate.frozen_bytes(self.root, self.fixture.prepared["resume_ref"], self.frozen,
            runtime.sources.Observations(self.root))
        runtime.candidate.check(self.value, self.frozen, store)
        before = deepcopy(self.frozen)
        flow_targets = [row["target"] for row in runtime.obligations(self.value, self.frozen)
            if row["target"][0] == "flow" and row["target"][1] == "FORMAL-FLOW"]
        aspects = {target[2] for target in flow_targets}
        self.assertTrue({"entry", "success_end", "loops", "handoffs", "verification_targets"} <= aspects)
        self.assertFalse({"graph", "ui", "human_verification"} & aspects)
        self.assertEqual(self.frozen, before)
        retained = next(flow for flow in runtime.semantic_domain(self.value, self.frozen)[0] if flow["id"] == "FORMAL-FLOW")
        self.assertEqual(retained, original_flow)

    def test_replacement_rounds_shared_across_scopes_and_clean_context(self):
        _run, state = self.create()
        state["capability_selection"] = {"current": {"capability_id": "scope"}}
        for depth in range(1, 4):
            for label in runtime.labels(state):
                event = runtime.replacement_reservation(state, label, depth + 1, "stable-issue")
                self.assertEqual(event["round"], depth)
                self.assertNotIn("proposal", event)
            state["capability_selection"]["current"]["capability_id"] = "next-original-scope"
        self.assertEqual(len(state["capability_selection"]["replacement_events"]), 9)
        self.assertIsNone(runtime.replacement_reservation(state, "candidate-1", 5, "stable-issue"))
        self.assertEqual(state["capability_selection"]["replacement_round"], 3)

    def test_unknown_dispatch_stays_unqualified_and_input_edit_blocks_failed_receipt(self):
        run, state = self.create()
        state["runner_configuration"] = {"backend_info": official.description()}
        sandbox = run / "reserved"
        sandbox.mkdir()
        prompt, schema, output = sandbox / "prompt.txt", sandbox / "schema.json", sandbox / "r.json"
        prompt.write_text("Complete frozen fixture request", encoding="utf-8")
        common.atomic_json(schema, {"type": "object"})
        request, actual, measured = runtime.prepare_dispatch(self.root, run, state, Path(official.__file__),
            sandbox, prompt, schema, output, 1, run / "binding.json", timeout_sec=10)
        self.assertTrue(actual)
        self.assertGreater(measured["request_bytes"], 0)
        row = {"number": 1, "request_identity": request}
        with self.assertRaisesRegex(ValueError, "outcome_unknown"):
            runtime.verify_reserved_call(run, row)
        row["outcome"] = {"status": "failed", "error_type": "runner_execution_failed", "error_class": "RuntimeError"}
        runtime.verify_reserved_call(run, row)
        schema.write_text('{"type":"array"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs_changed"):
            runtime.verify_reserved_call(run, row)
        self.assertFalse(output.exists())

    def test_slot_64_budget_survives_reentry_and_does_not_fake_issue_exhaustion(self):
        scope = {"capability_id": "same-governed-scope"}
        def propose(scope, base, prior, issue, context, call):
            for _ in range(40):
                call("generate")
            return {}
        kwargs = dict(scopes=[scope], seed={}, identity="same-frozen-input", propose=propose,
            machine=lambda *_: [], semantic=lambda scope, base, proposal, call, context: {
                "issues": [{"code": "hard", "path": "stable"}], "proof": {}, "execution": {}},
            final_machine=lambda _: [], merge=lambda *_: {}, preserve=lambda *_: [])
        first = append.run_capability_append(self.root / "bounded", **kwargs)
        self.assertEqual(first["total_invocations"], 64)
        self.assertEqual(first["errors"][0]["code"], "capability_append_invocation_budget_exhausted")
        self.assertLess(first["current"]["issue_attempts"]["hard@stable"], 3)
        later = append.run_capability_append(self.root / "bounded", invocation_limit=192, **kwargs)
        self.assertEqual(later, first)

    def test_epoch_invalidation_busy_coordinator_and_json_type_delta(self):
        run, state = self.create()
        original = (run / "run.json").read_bytes()
        with checkpoint.coordinator_lock(run):
            with self.assertRaises(ValueError):
                runtime.operate(self.root, planner="mvg", command="status", run_id=state["run_id"],
                    prepared_ref=self.ref, profile="3b-mvg-v1")
        self.assertEqual((run / "run.json").read_bytes(), original)
        import _mvg_capability_recovery as recovery
        recovery.bind_epoch(self.root, state)
        common.atomic_json(recovery.store_root(self.root) / "registry.json",
            {"schema_version": recovery.SCHEMA, "epoch": state["recovery"]["epoch"] + 1, "entries": [], "revoked": []})
        with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
            runtime.validate_input(self.root, run, state)
        self.assertTrue(runtime.json_delta({"id": True}, {"id": 1}))
        self.assertTrue(runtime.json_delta({"id": 1}, {"id": "1"}))
        self.assertTrue(runtime.json_delta([1, 2], [2, 1]))

    def test_existing_append_three_repairs_then_parent_replacement_and_no_execution_issue(self):
        calls, inputs, replacements = [], [], []
        scope = {"capability_id": "governed-scope"}
        def propose(scope, base, prior, issue, context, call):
            call("generate")
            inputs.append((context, deepcopy(prior), deepcopy(issue)))
            return {"content": context}
        def semantic(scope, base, proposal, call, context):
            call("semantic")
            return {"issues": [] if context == 2 else [{"code": "hard", "path": "same"}], "proof": {}, "execution": {}}
        result = append.run_capability_append(self.root / "append", scopes=[scope], seed={}, identity="fixture",
            propose=propose, machine=lambda *_: [], semantic=semantic, final_machine=lambda _: [],
            merge=lambda base, delta, scope: delta, preserve=lambda *_: [],
            before_call=lambda phase: calls.append(phase),
            replacement=lambda **kwargs: replacements.append(kwargs) or {"round": 1}, fail_execution_closed=True)
        self.assertEqual(result["status"], "admitted")
        self.assertEqual(result["restarts"][0]["repair_attempts"], 3)
        self.assertEqual(len(replacements), 1)
        self.assertEqual(inputs[-1], (2, None, None))
        self.assertEqual(result["total_invocations"], len(calls))
        def broken(scope, base, prior, issue, context, call):
            call("generate")
            raise ValueError("runner_identity_invalid")
        failed = append.run_capability_append(self.root / "failed", scopes=[scope], seed={}, identity="fixture",
            propose=broken, machine=lambda *_: [], semantic=semantic, final_machine=lambda _: [],
            merge=lambda *_: {}, preserve=lambda *_: [], fail_execution_closed=True)
        self.assertEqual(failed["total_invocations"], 1)
        self.assertEqual(failed["errors"][0]["code"], "append_execution_failure")
        self.assertFalse(failed.get("issue_events"))

    def test_real_child_resolves_descriptor_and_cannot_commit_parent(self):
        run, state = self.create()
        workspace = run / "candidates/candidate-1/scope-1"
        workspace.mkdir(parents=True)
        shutil.copytree(run / "analysis-input", workspace / "analysis-input")
        private = deepcopy(state)
        private["planning_runtime"]["profile"] = "unknown-profile"
        data = {"root": str(self.root), "run_dir": str(run), "workspace": str(workspace), "state": private,
            "scope_index": 0, "accepted_seed": {}, "selected_records": [], "runner": {}}
        original = (run / "run.json").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "candidate_worker_failed"):
            worker.run_candidate(workspace / "lifecycle", data,
                reserve=lambda *_: self.fail("No model reservation"), cost_budget=lambda *_: {}, outcome=lambda *_: None)
        process = common.load_json(workspace / "lifecycle/process.json")
        self.assertNotEqual(process["pid"], os.getpid())
        self.assertEqual((run / "run.json").read_bytes(), original)
        self.assertFalse((workspace / "proposal.json").exists())
        self.assertIn("b_route_runtime_descriptor_invalid", (workspace / "lifecycle/worker.log").read_text(encoding="utf-8"))

    def test_real_valid_profile_child_uses_parent_mailbox_and_rejects_synthetic_execution(self):
        run, state = self.create()
        runner = Path(__file__).parent / "fixtures/b_route_runtime_offline_runner.py"
        info = common.inspect_isolated_runner(runner)
        config = {"runner": str(runner.resolve()), "runner_sha256": common.file_sha(runner), "backend": "offline-fixture",
            "backend_info": info, "timeout_sec": 10}
        state["runner_configuration"] = config
        common.atomic_json(run / "run.json", state)
        wrapper = self.root / "child-assembly-only.py"
        # The test launches the real production worker with one explicit upstream
        # assembly seam in that child. No runtime profile, environment switch or
        # production proof validator can enable this seam. All descriptor, append,
        # worker, mailbox, runner subprocess and receipt validation code is real.
        wrapper.write_text("import sys\nfrom pathlib import Path\n" +
            "sys.path.insert(0, " + repr(str(Path(worker.__file__).parent)) + ")\n" + '''
import argparse
import subprocess
import _b_route_codec as codec
import _b_route_planning_input as planning
import _mvg_capability_worker as worker
from _planning_skill_common import atomic_json

def prepared_assembly(root, reference, **kwargs):
    return planning.validate_frozen(codec.strict_json_loads((Path(root) / reference).read_bytes()))

planning.load_prepared = prepared_assembly
parser = argparse.ArgumentParser()
parser.add_argument("--job", type=Path, required=True)
parser.add_argument("--start-gate", action="store_true")
args = parser.parse_args()
original_popen = subprocess.Popen
def launch(command, *values, **kwargs):
    if "--workspace" in command:
        job = codec.strict_json_loads(args.job.read_bytes())
        run = Path(job["input"]["run_dir"])
        parent = codec.strict_json_loads((run / "run.json").read_bytes())
        ledger = parent["capability_selection"]
        atomic_json(args.job.parent / "reserved-at-dispatch.json", {
            "total_invocations": ledger["total_invocations"],
            "reservation": ledger["calls"][-1],
            "output_existed": Path(command[command.index("--output") + 1]).exists()})
    return original_popen(command, *values, **kwargs)
subprocess.Popen = launch
if not args.start_gate or sys.stdin.buffer.readline() == b"start\\n":
    worker.execute(args.job)
''', encoding="utf-8", newline="\n")
        # Preserve the original start gate, Job Object and run_candidate API.
        actual_popen = subprocess.Popen
        def launch(command, *args, **kwargs):
            if isinstance(command, list) and len(command) > 1 and Path(command[1]).resolve() == Path(worker.__file__).resolve():
                command = [command[0], str(wrapper), *command[2:]]
            return actual_popen(command, *args, **kwargs)
        with patch.dict(os.environ, {"SC_KNOWLEDGE_PLANNING_RUNNER": str(runner.resolve())}), \
             patch.object(subprocess, "Popen", side_effect=launch):
            with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                selection.generate_selected_capabilities(self.root, run, state, backend="offline-fixture",
                    invoke_factory=None, selector_factory=lambda *_args, **_kwargs: self.fail("No selector"), worker_config=config)
        ledger = state["capability_selection"]
        self.assertEqual(ledger["total_invocations"], 1)
        self.assertEqual(ledger["lineage_invocations"], {"candidate-1": 1, "candidate-2": 0, "candidate-3": 0})
        self.assertEqual(ledger["selected"], [])
        self.assertEqual(ledger["calls"][0]["outcome"]["status"], "failed")
        self.assertEqual(common.load_json(run / "run.json")["capability_selection"]["total_invocations"], 1)
        lifecycle = run / "candidates/candidate-1/scope-1/lifecycle"
        dispatched = common.load_json(lifecycle / "reserved-at-dispatch.json")
        self.assertEqual(dispatched["total_invocations"], 1)
        self.assertEqual(dispatched["reservation"]["status"], "reserved")
        self.assertNotIn("outcome", dispatched["reservation"])
        self.assertFalse(dispatched["output_existed"])
        kinds = [common.load_json(path)["kind"] for path in sorted((lifecycle / "mailbox").glob("*.request.json"))]
        self.assertEqual(kinds, ["cost", "reserve", "outcome"])
        self.assertEqual(common.load_json(lifecycle / "result.json")["status"], "blocked")
        self.assertNotEqual(common.load_json(lifecycle / "process.json")["pid"], os.getpid())
        host = next(run.glob("candidates/candidate-1/scope-1/capability-append/c1/host-execution-*.json"))
        self.assertEqual(common.load_json(host)["status"], "completed")
        self.assertIn('"synthetic": true', common.load_json(host)["stdout"])
        self.assertFalse(list(run.glob("capability-checkpoints/*/payload.json")))
        before = ledger["total_invocations"]
        with patch.object(worker, "run_candidate", side_effect=AssertionError("No unchanged retry")):
            with self.assertRaises(ValueError):
                selection.generate_selected_capabilities(self.root, run, state, backend="offline-fixture",
                    invoke_factory=None, selector_factory=None, worker_config=config)
        self.assertEqual(state["capability_selection"]["total_invocations"], before)

    def test_public_cli_requires_explicit_profile_and_rejects_legacy_adoption(self):
        parser = dev_cli.build_parser()
        for command, profile, builder in (("plan-mvg", "3b-mvg-v1", builders.build_plan_mvg_cmd),
                                          ("plan-capabilities", "3b-capabilities-v1", builders.build_plan_capabilities_cmd)):
            for stage in ("generate", "review", "verify-selection", "status"):
                args = parser.parse_args([command, "--stage", stage, "--run-id", "r", "--input-stage", "3b",
                    "--planning-profile", profile, "--prepared-ref", self.ref])
                cmd = builder(args)
                self.assertIn("--planning-profile", cmd)
                self.assertIn(self.ref, cmd)
            for stage in ("apply", "prepare"):
                args = parser.parse_args([command, "--stage", stage, "--run-id", "r", "--input-stage", "3b",
                    "--planning-profile", profile, "--prepared-ref", self.ref])
                with self.assertRaises(ValueError):
                    builder(args)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(plan_mvg.main(["--repo-root", str(self.root), "generate", "--run-id", "no-profile", "--input-stage", "3b"]), 0)
        self.assertFalse(runtime.run_location(self.root, "mvg", "no-profile").exists())

    def assembly(self, profile="3b-mvg-v1", *, block_candidate=None, interrupt_selector=False):
        run, state = self.create(profile)
        observed = []
        def factory(workspace, **kwargs):
            def invoke(prompt, number, *, output_name, output_schema_path, output_schema, before_dispatch):
                common.atomic_json(output_schema_path, output_schema)
                prompt_path = workspace / f"prompt-{number}.txt"
                prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
                output = workspace / output_name
                request = {"runtime_identity": state["runtime_identity"], "planning_profile": profile, "requested_timeout_sec": 10}
                before_dispatch(request_identity=request)
                reserved = state["capability_selection"]["calls"][-1]
                if "selected" in output_schema.get("properties", {}):
                    self.assertIn("All candidates share the same frozen input and base.", prompt)
                    self.assertNotIn("All three share the", prompt)
                    observed.append("selector")
                    aliases = list("ABC"[:len(runtime.labels(state))])
                    value = {"status": "selected", "selected": "A", "candidate_reviews": [
                        {"candidate": alias, "rank": index + 1, "verdict": "viable", "rationale": "Offline comparative assembly seam"}
                        for index, alias in enumerate(aliases)]}
                else:
                    payload = json.loads(prompt.split("\n", 1)[1])
                    observed.append(payload)
                    if payload["phase"] == "generation":
                        original = payload["root_request"]["input"]
                        value = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
                            "stage": original["stage"], "ordinal": original["ordinal"],
                            "parent_draft_identities": [row["identity"] for row in original["prior_drafts"]],
                            "content": deepcopy(self.value["content"])}
                        value = carrier(value)
                    else:
                        value = {"schema_version": runtime.REVIEW, "input_identity": self.frozen["input_identity"],
                            "runtime_identity": state["runtime_identity"], "proposal_sha256": common.canonical_sha(payload["proposal"]),
                            "verdict": "approved", "findings": [], "checks": [{"id": row["id"], "verdict": "approved",
                                "rationale": "Offline independent semantic assembly seam", "source_block_ids": row["source_block_ids"][:1]}
                                for row in payload["obligations"]]}
                        value = fixture_review_carrier(value, payload)
                        if reserved.get("candidate") == block_candidate:
                            raise ValueError("fixture_execution_failure")
                common.atomic_json(output, value)
                outcome = {"status": "completed", "completed_at_utc": "offline-fixture", "error_type": None,
                    "output_sha256": common.file_sha(output)}
                if kwargs.get("outcome"):
                    kwargs["outcome"](reserved["reservation_id"], outcome)
                    if interrupt_selector:
                        raise KeyboardInterrupt("offline completed selector before receipt publication")
                else:
                    reserved["outcome"] = outcome
                    common.atomic_json(run / "run.json", state)
                return output, {"backend_info": official.description(), "receipt": {"model": "fixture-runtime-model", "model_tools": []},
                    "execution_binding": {"output_path": str(output), "prompt_path": str(prompt_path), "schema_path": str(output_schema_path)}}
            return invoke
        # These explicit patches model assembly only. Production has no equivalent
        # profile, CLI flag, environment bypass or arbitrary module hook.
        with patch.object(runtime, "verify_call", side_effect=lambda binding: common.load_json(Path(binding["output_path"]))), \
             patch.object(runtime, "verify_reserved_call", return_value=None), \
             patch.object(runtime, "verify_proof_reservations", return_value=None), \
             patch.object(runtime, "verify_selector_reservation", return_value=None):
            result = None
            error = None
            try:
                result = selection.generate_selected_capabilities(self.root, run, state, backend="offline-assembly-seam",
                    invoke_factory=lambda budget, workspace, label: factory(workspace), selector_factory=factory)
            except (ValueError, KeyboardInterrupt) as exc:
                error = exc
            if interrupt_selector:
                self.assertIsInstance(error, KeyboardInterrupt)
                charged = state["capability_selection"]["total_invocations"]
                fixed = deepcopy(state["capability_selection"]["current"]["input_identity"])
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        selection.generate_selected_capabilities(self.root, run, state, backend="offline-assembly-seam",
                            invoke_factory=lambda *_: self.fail("No repeated candidate call"),
                            selector_factory=lambda *_args, **_kwargs: self.fail("No repeated paid selector"))
                    self.assertEqual(state["capability_selection"]["total_invocations"], charged)
                    self.assertEqual(state["capability_selection"]["current"]["input_identity"], fixed)
                self.assertTrue(state["capability_selection"]["terminal"])
            if result is not None:
                selection.verify_published_chain(self.root, run, state)
                fixed = deepcopy(state["capability_selection"]["selected"])
                replay_files = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
                replay_state = deepcopy(state)
                with patch.object(selection, "_monotonic", return_value=999999):
                    selection.generate_selected_capabilities(self.root, run, state, backend="offline-assembly-seam",
                        invoke_factory=None, selector_factory=None)
                self.assertEqual(state, replay_state)
                self.assertEqual(replay_files, {path: path.read_bytes() for path in run.rglob("*") if path.is_file()})
                receipt = runtime.handoff(self.root, run, state)
                self.assertEqual(receipt["proposal"], common.load_json(run / "proposal.json"))
                self.assertFalse(receipt["formal_adoption"] or receipt["readiness"] or receipt["runtime_verified"])
                self.assertEqual(state["capability_selection"]["selected"], fixed)
                # Replaying a genuinely committed 3B bundle must preserve both
                # checkpoint-protocol checking and the profile location adapter.
                step = fixed[0]
                stored = checkpoint.load_checkpoint(run, step["checkpoint"])
                frozen_files = {path: common.file_sha(path) for path in (run / "run.json", run / step["checkpoint"]["path"])}
                count_before_replay = len(observed)
                replay_pointer = checkpoint.prepare_checkpoint(run, state, stored["identity"]["capability_id"], 0,
                    stored["accepted_seed"], stored["accepted"], step)
                from unittest.mock import Mock
                writer = Mock(side_effect=AssertionError("Committed replay cannot republish state"))
                self.assertEqual(checkpoint.commit_checkpoint(run, state, replay_pointer, step, stored["accepted"], writer=writer), "no-op")
                writer.assert_not_called()
                self.assertEqual(count_before_replay, len(observed))
                self.assertEqual(frozen_files, {path: common.file_sha(path) for path in frozen_files})
                # A selected proof edit blocks fixed-winner verification; it
                # neither dispatches nor changes the authoritative checkpoint.
                admission = fixed[0]["admissions"][fixed[0]["selected_candidate"]]
                proof_path = run / admission["proof_path"]
                proof_path.write_bytes(proof_path.read_bytes() + b" ")
                with self.assertRaises(ValueError):
                    runtime.handoff(self.root, run, state)
                self.assertEqual(state["capability_selection"]["selected"], fixed)
            return result, error, observed, state, run

    def test_positive_assembly_three_admitted_before_selector_and_fixed_checkpoint(self):
        result, error, observed, state, run = self.assembly()
        self.assertIsNone(error, str(error) + repr(state.get("candidate_admissions")))
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(observed.count("selector"), 1)
        self.assertEqual(sum(isinstance(row, dict) and row["phase"] == "independent_admission" for row in observed), 3)
        self.assertEqual(state["capability_selection"]["total_invocations"], len(observed))
        self.assertEqual(len(list(run.glob("capability-checkpoints/*/payload.json"))), 1)
        self.assertEqual(state["selection_status"], "selected")

    def test_positive_capability_assembly_keeps_two_and_96(self):
        result, error, observed, state, _run = self.assembly("3b-capabilities-v1")
        self.assertIsNone(error, str(error) + repr(state.get("candidate_admissions")))
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(state["mvg.run_invocation_limit"], 96)
        self.assertEqual(observed.count("selector"), 1)

    def test_incomplete_mvg_admission_never_invokes_selector_or_creates_checkpoint(self):
        result, error, observed, state, run = self.assembly(block_candidate="candidate-3")
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertNotIn("selector", observed)
        self.assertEqual(state["capability_selection"]["selected"], [])
        self.assertEqual(state["selection_status"], "blocked")
        self.assertFalse(list(run.glob("capability-checkpoints/*/payload.json")))


class ProtocolBindingTests(unittest.TestCase):
    def test_offline_protocol_replay_environment_default_and_tamper(self):
        # This synthetic child deliberately reports the environment default.
        fixture_environment = patch.dict(os.environ, {"NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "medium"})
        fixture_environment.start()
        self.addCleanup(fixture_environment.stop)
        os.environ.pop("NEWROGUE_CODEX_REASONING_EFFORT", None)
        fixture = protocol_fixture.AppServerStdioTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(protocol_fixture.transport, "command", side_effect=lambda *_: fixture.command("success")):
            output, proof = fixture.call("success", requested_reasoning_effort=None)
        receipt = {"schema_version": "newrouge.isolated-model-runner-receipt.v1", "model": proof["model"],
            "model_provider": proof["model_provider"], "model_identity": proof["model_provider"] + "/" + proof["model"],
            "model_identity_source": official.MODEL_IDENTITY_SOURCE, "model_identity_verified": False,
            "runtime_identity_verified": True, "model_identity_scope": "runtime_configuration",
            "evidence_policy": official.APP_SERVER_EVIDENCE_POLICY, "provider_reported_model": None,
            "provider_identity_verified": False, "provider_dispatch_count": "unknown", "model_identity_evidence": [proof],
            "model_tools": [], "runner_invocations": 1, "request_count_observable": True, "model_request_count": 1,
            "output_chars": len(output), "workspace": fixture.cwd.as_posix()}
        def captured(value):
            stdout = json.dumps(value) + "\n"
            return {"status": "completed", "returncode": 0, "runner_dispatch_count": 1, "active_elapsed_seconds": 0.1,
                "stdout": stdout, "stdout_base64": base64.b64encode(stdout.encode()).decode()}
        replay_command = patch.object(protocol_fixture.transport, "command", side_effect=lambda *_: fixture.command("success"))
        replay_command.start()
        self.addCleanup(replay_command.stop)
        for requested in ("auto", "environment-default", "fixture-model", "fixture/fixture-model"):
            execution_binding.validate_execution(fixture.cwd, captured(receipt), receipt, requested, output.encode(),
                prompt="complete input", schema={"type": "object"}, require_runtime=True)
        for alter in (lambda r: r.update(synthetic=True), lambda r: r.update(model="requested-only"),
                      lambda r: r["model_identity_evidence"][0].update(model="forged")):
            changed = deepcopy(receipt)
            alter(changed)
            with self.assertRaises(ValueError):
                execution_binding.validate_execution(fixture.cwd, captured(changed), changed, "environment-default", output.encode(),
                    prompt="complete input", schema={"type": "object"}, require_runtime=True)
        with self.assertRaises(ValueError):
            execution_binding.validate_execution(fixture.cwd, captured(receipt), receipt, "environment-default", output.encode(),
                prompt="different input", schema={"type": "object"}, require_runtime=True)

    def test_literal_official_environment_default_description_selection_regression(self):
        state = {"analysis_identity_sha256": "input"}
        receipt = {"schema_version": "newrouge.mvg-selection-execution-receipt.v1", "analysis_identity_sha256": "input",
            "selection_input_sha256": "selection", "output_sha256": "output", "runner_info": official.description(),
            "runner_receipt": {"model": "actual-runtime-model", "model_tools": []}}
        self.assertEqual(plan_mvg.validate_selection_execution_receipt(state, {"status": "selected"}, receipt,
            selection_input_sha256="selection", output_sha256="output"), [])


class CheckpointProtocolReplayTests(unittest.TestCase):
    def test_actual_legacy_committed_bundle_replay_uses_checkpoint_enabled(self):
        import tempfile
        import test_mvg_capability_append as fixture
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / plan_mvg.DEFAULT_RUN_ROOT / "checkpoint-fixture"
            run.mkdir(parents=True)
            state, seed, accepted, step = fixture.CapabilityAppendTests().checkpoint_fixture(run)
            state.update(checkpoint_strategy=checkpoint.STRATEGY, checkpoint_schema_version=checkpoint.SCHEMA)
            common.atomic_json(run / "run.json", state)
            pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            self.assertEqual(checkpoint.commit_checkpoint(run, state, pointer, step, accepted), "committed")
            original = {path: common.file_sha(path) for path in (run / "run.json", run / pointer["path"])}
            # Prefix evidence is its own existing owner; this narrow seam isolates
            # protocol/location dispatch while replay still reads and verifies
            # the actual selected bundle, receipt and run.json commit point.
            with patch.object(selection, "verified_prefix", return_value=([], accepted, [])) as prefix:
                writer = Mock(side_effect=AssertionError("No state publication during replay"))
                self.assertEqual(checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step), pointer)
                self.assertEqual(checkpoint.commit_checkpoint(run, state, pointer, step, accepted, writer=writer), "no-op")
                writer.assert_not_called()
                self.assertTrue(prefix.called)
                for call in prefix.call_args_list:
                    self.assertEqual(call.args[:2], (root, run))
                    self.assertFalse(runtime.enabled(call.args[2]))
            self.assertEqual(original, {path: common.file_sha(path) for path in original})


class ReviewFixTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    create = RuntimeTests.create
    review = RuntimeTests.review

    def test_review_producer_subset_keeps_strict_host_uniqueness_and_exact_binding(self):
        import jsonschema
        run, state = self.create()
        canonical = runtime.review_schema(state, self.value, self.frozen)
        original = deepcopy(canonical)
        wire = runtime.review_producer_schema(state, self.value, self.frozen)
        source = canonical["properties"]["checks"]["items"]["properties"]["source_block_ids"]
        self.assertIs(source["uniqueItems"], True)
        self.assertNotIn("uniqueItems", wire["properties"]["checks"]["items"]["properties"]["source_block_ids"])
        expected = deepcopy(canonical)
        expected["properties"]["checks"]["items"]["properties"]["source_block_ids"].pop("uniqueItems")
        self.assertTrue(runtime.same_json(wire, expected))
        duplicate = self.review(state)
        duplicate["checks"][0]["source_block_ids"] *= 2
        self.assertFalse(list(jsonschema.Draft202012Validator(wire).iter_errors(duplicate)))
        self.assertTrue(list(jsonschema.Draft202012Validator(canonical).iter_errors(duplicate)))
        with self.assertRaises(ValueError):
            runtime.review_issues(state, self.value, self.frozen, duplicate)
        workspace = run / "review-wire"
        workspace.mkdir()
        schema, prompt = workspace / "schema.json", workspace / "prompt.txt"
        for actual, accepted in ((wire, True), (canonical, False)):
            materials = {"phase": "independent_admission", "proposal": self.value, "actual_output_schema": actual,
                "root_input_identity": self.frozen["input_identity"], "runtime_identity": state["runtime_identity"], "run_id": state["run_id"]}
            materials["materials_identity"] = common.canonical_sha(materials)
            common.atomic_json(schema, actual)
            prompt.write_text("Use complete governed originals\n" + json.dumps(materials), encoding="utf-8")
            binding = {"prompt_path": str(prompt), "schema_path": str(schema)}
            if accepted:
                self.assertEqual(runtime.bound_materials(binding, state, self.frozen), materials)
            else:
                with self.assertRaisesRegex(ValueError, "review_producer_schema_changed"):
                    runtime.bound_materials(binding, state, self.frozen)
        self.assertEqual(canonical, original)

    def test_machine_business_findings_use_original_three_repairs_and_schema_faults_close(self):
        run, state = self.create()
        broken = deepcopy(self.value)
        broken["content"]["definitions"]["flows"][0]["graph"]["edges"][0]["to"]["node_id"] = "missing"
        findings = runtime.machine(self.root, state, broken)
        self.assertTrue(findings and findings[0]["code"].startswith("b_route_machine:"))
        self.assertEqual(findings, runtime.machine(self.root, state, broken))
        wrong_owner = deepcopy(self.value)
        wrong_owner["content"]["definitions"]["flows"][0]["graph"]["nodes"][0]["owner"]["proposed_owner_key"] = "not-the-selected-owner"
        wrong_route = deepcopy(self.value)
        wrong_route["content"]["requirement_route_memberships"][0]["flow_id"] = "unknown-flow"
        for value in (wrong_owner, wrong_route):
            runtime.candidate.schemas.validate(value, runtime.candidate.SCHEMA, auxiliary=True)
            self.assertTrue(runtime.machine(self.root, state, value))
        scope = runtime.scopes(state, run / "analysis-input")[0]
        def propose(scope, base, prior, issue, context, call):
            call("generate")
            return deepcopy(broken if context == 1 else self.value)
        result = append.run_capability_append(self.root / "repair-business", scopes=[scope], seed={}, identity="fixture",
            propose=propose, machine=lambda _scope, _base, value: runtime.machine(self.root, state, value),
            semantic=lambda *_: {"issues": [], "proof": {}, "execution": {}}, final_machine=lambda _: [],
            merge=lambda _base, value, _scope: value, preserve=lambda *_: [],
            replacement=lambda **kwargs: {"round": 1}, fail_execution_closed=True)
        self.assertEqual(result["status"], "admitted")
        self.assertEqual(result["restarts"][0]["repair_attempts"], 3)
        invalid = deepcopy(self.value)
        invalid["content"]["definitions"]["flows"][0]["graph"]["boundaries"][0]["required"] = 1
        with self.assertRaises(codec.CodecError):
            runtime.machine(self.root, state, invalid)
        invalid = deepcopy(self.value)
        invalid["input_identity"] = "sha256:" + "0" * 64
        with self.assertRaises(codec.CodecError):
            runtime.machine(self.root, state, invalid)

    def test_shared_ledger_dedup_lazy_text_context_and_conflicting_originals(self):
        import test_b_route_records as records_fixture
        self.fixture.selected_plan()
        original = self.fixture.dependency_fixture
        qpath = original.add_plan("q", 1)
        self.fixture.dependency_models[qpath] = deepcopy(original.models[qpath])
        self.fixture.dependency_paths.append(qpath)
        self.fixture.freeze_dependencies("shared-ledger", out_of_scope=["REQ-p", "REQ-q"])
        self.value, self.frozen = self.fixture.value, self.fixture.frozen
        store = runtime.candidate.frozen_bytes(self.root, self.fixture.prepared["resume_ref"], self.frozen,
            runtime.sources.Observations(self.root))
        runtime.candidate.check(self.value, self.frozen, store)
        before = deepcopy(self.frozen)
        obligations = runtime.obligations(self.value, self.frozen)
        self.assertEqual(len(obligations), len({row["id"] for row in obligations}))
        self.assertEqual(len(runtime.semantic_domain(self.value, self.frozen)[1]), 3)
        # An explicitly text, non-JSON original remains complete evidence and is
        # never parsed merely because its name ends in .json.
        extra_path, extra_text = "notes/unselected.json", "This is a legitimate non-JSON original."
        self.fixture.put(extra_path, extra_text.encode("utf-8"))
        contract = json.loads((self.root / "contract.json").read_bytes())
        contract["contexts"].append({"kind": "governance", "path": extra_path, "format": "text", "required": True, "absence": None})
        prepared = self.fixture.fixture.prepare("text-named-json", contract=contract)
        self.frozen = self.fixture.fixture.frozen(prepared)
        self.value["input_identity"] = self.frozen["input_identity"]
        store = runtime.candidate.frozen_bytes(self.root, prepared["resume_ref"], self.frozen, runtime.sources.Observations(self.root))
        runtime.candidate.check(self.value, self.frozen, store)
        self.assertEqual([row for row in runtime.obligations(self.value, self.frozen) if row["target"][0] != "cumulative"],
                         [row for row in obligations if row["target"][0] != "cumulative"])
        self.assertEqual(next(row["text"] for row in self.frozen["inputs"]["evidence"] if row["path"] == extra_path), extra_text)
        ledger = json.loads(original.artifacts["sources/ledger.json"])
        ledger["blocks"][0]["text"] = "Conflicting original"
        self.frozen["inputs"]["evidence"].append({"path": "sources/ledger.json", "text": json.dumps(ledger)})
        with self.assertRaisesRegex(ValueError, "conflicting"):
            runtime.obligations(self.value, self.frozen)
        self.assertEqual(before["inputs"]["global_proof"], self.frozen["inputs"]["global_proof"])

    def test_source_obligations_are_qualified_and_cannot_borrow_another_block(self):
        _run, state = self.create()
        review = self.review(state)
        obligations = runtime.obligations(self.value, self.frozen)
        sources = [row for row in obligations if row["target"][0] == "source"]
        target = next(row for row in review["checks"] if row["id"] == sources[1]["id"])
        target["source_block_ids"] = sources[0]["source_block_ids"]
        with self.assertRaisesRegex(ValueError, "source_support_invalid"):
            runtime.review_issues(state, self.value, self.frozen, review)
        blocks = runtime.semantic_domain(self.value, self.frozen)[1]
        duplicate_id = {**blocks[0], "semantic_namespace": "different/ledger.json"}
        self.assertNotEqual(runtime.source_key(blocks[0]), runtime.source_key(duplicate_id))

    def test_distinct_selected_ledgers_keep_same_block_id_separate(self):
        self.fixture.selected_plan()
        original = self.fixture.dependency_fixture
        qpath = original.add_plan("q", 1)
        original.artifacts["sources/other-ledger.json"] = original.artifacts["sources/ledger.json"]
        q = deepcopy(original.models[qpath])
        q["source_identity"]["ledger_ref"] = original.owned("source_ledger", "sources/other-ledger.json")
        self.fixture.dependency_models[qpath] = q
        self.fixture.dependency_paths.append(qpath)
        self.fixture.freeze_dependencies("separate-ledgers", out_of_scope=["REQ-p", "REQ-q"])
        self.value, self.frozen = self.fixture.value, self.fixture.frozen
        self.ref = self.fixture.prepared["resume_ref"]
        _run, state = self.create()
        self.assertEqual(runtime.machine(self.root, state, self.value), [])
        blocks = [row for row in runtime.semantic_domain(self.value, self.frozen)[1] if row["block_id"] == "BLOCK-1"]
        self.assertEqual(len(blocks), 2)
        self.assertNotEqual(runtime.source_key(blocks[0]), runtime.source_key(blocks[1]))
        review = self.review(state)
        obligation = next(row for row in runtime.obligations(self.value, self.frozen)
            if row["target"][0] == "source" and row["target"][1] == runtime.source_key(blocks[1]))
        next(row for row in review["checks"] if row["id"] == obligation["id"])["source_block_ids"] = [runtime.source_key(blocks[0])]
        with self.assertRaisesRegex(ValueError, "source_support_invalid"):
            runtime.review_issues(state, self.value, self.frozen, review)

    def test_individual_findings_are_stable_and_inconsistent_summary_is_rejected(self):
        _run, state = self.create()
        review = self.review(state)
        review["checks"][0].update(verdict="blocked", rationale="Missing observable outcome")
        review.update(verdict="blocked", findings=["Missing observable outcome"])
        first = runtime.review_issues(state, self.value, self.frozen, review)
        reordered = deepcopy(review)
        reordered["checks"].reverse()
        self.assertEqual(first, runtime.review_issues(state, self.value, self.frozen, reordered))
        second = deepcopy(review)
        second["checks"][0]["rationale"] = "A different actual business finding"
        second["findings"] = [second["checks"][0]["rationale"]]
        self.assertNotEqual(first[0]["code"], runtime.review_issues(state, self.value, self.frozen, second)[0]["code"])
        for change in (lambda r: r.update(findings=["Unbound overall finding"]),
                       lambda r: r.update(verdict="approved"), lambda r: r.update(findings=[])):
            invalid = deepcopy(review)
            change(invalid)
            with self.assertRaises(ValueError):
                runtime.review_issues(state, self.value, self.frozen, invalid)

    def test_branch_reordering_does_not_create_new_business_issue(self):
        run, state = self.create()
        revised = deepcopy(self.value)
        revised["content"]["definitions"]["flows"][0]["branches"].reverse()
        original_ids = {row["id"] for row in runtime.obligations(self.value, self.frozen)}
        self.assertEqual(original_ids, {row["id"] for row in runtime.obligations(revised, self.frozen)})
        scope = runtime.scopes(state, run / "analysis-input")[0]
        attempts = []
        def propose(scope, base, prior, issue, context, call):
            call("generate")
            attempts.append(True)
            return deepcopy(self.value if len(attempts) == 1 else revised)
        branch_id = next(row["id"] for row in runtime.obligations(self.value, self.frozen) if row["target"][0] == "flow_branch")
        def semantic(scope, base, proposal, call, context):
            call("semantic")
            review = self.review(state, proposal)
            if len(attempts) == 1:
                row = next(row for row in review["checks"] if row["id"] == branch_id)
                row.update(verdict="blocked", rationale="Repair this source-backed branch condition")
                review.update(verdict="blocked", findings=[row["rationale"]])
            return {"issues": runtime.review_issues(state, proposal, self.frozen, review), "proof": {}, "execution": {}}
        result = append.run_capability_append(self.root / "reorder-repair", scopes=[scope], seed={}, identity="fixture",
            propose=propose, machine=lambda *_: [], semantic=semantic, final_machine=lambda _: [],
            merge=lambda _base, value, _scope: value, preserve=lambda *_: [])
        self.assertEqual(result["status"], "admitted")
        self.assertFalse(result.get("rejected_repairs"))

    def test_formal_same_kind_branch_multiplicity_survives_reordering(self):
        import test_b_route_records as records_fixture
        RuntimeTests.test_selected_formal_flow_keeps_its_actual_schema_and_semantic_obligations(self)
        path = records_fixture.plan_path()
        plan = self.fixture.dependency_models[path]
        branches = plan["definitions"]["flows"][0]["branches"]
        branches.extend([{**deepcopy(branches[0]), "description": "A second source-backed return branch"}, deepcopy(branches[0])])
        self.fixture.freeze_dependencies("formal-multiple", out_of_scope=["REQ-p"])
        validation = runtime.candidate.records.validate_record(records_fixture.encoded(plan), path=path)
        self.assertTrue(validation.ok, validation.diagnostic)
        def identities():
            return [row["id"] for row in runtime.obligations(self.fixture.value, self.fixture.frozen)
                if row["target"][0] == "flow_branch" and row["target"][1] == "FORMAL-FLOW"]
        original = identities()
        self.assertEqual(len(original), 3)
        self.assertEqual(len(set(original)), 3)
        branches.reverse()
        self.fixture.freeze_dependencies("formal-reorder", out_of_scope=["REQ-p"])
        self.assertEqual(identities(), original)

    def test_native_verify_selection_requires_explicit_3b_for_both_planners(self):
        for module in (plan_mvg, plan_capabilities):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = module.main(["--repo-root", str(self.root), "verify-selection", "--run-id", "pending"])
            self.assertNotEqual(result, 0, output.getvalue())

    def bound_call(self, run, state, slot="candidate-1", number=1, response=None, materials=None, phase="generate"):
        """Actual OS runner + synthetic stdio; all binding validators stay real."""
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        info = official.description()
        state["runner_configuration"] = {"runner": str(runner.resolve()), "runner_sha256": common.file_sha(runner),
            "backend_info": info, "timeout_sec": 5}
        workspace = selection.scope_workspace(run, slot, 0, 1)
        call_root = workspace / "capability-append" / f"c{number}"
        sandbox = call_root / "llm-sandbox" / f"attempt-{number}" / "r"
        sandbox.mkdir(parents=True)
        schema = sandbox / "output-schema.json"
        actual_schema = (runtime.generation_schema(self.frozen, materials["root_request"])
                         if materials is not None and materials["phase"] == "generation" else
                         runtime.review_producer_schema(state, materials["proposal"], self.frozen)
                         if materials is not None and materials["phase"] == "independent_admission" else {"type": "object"})
        common.atomic_json(schema, actual_schema)
        prompt = sandbox / f"prompt-{number}-r.txt"
        if materials is None:
            prompt.write_text("Deterministic offline full-binding transport fixture", encoding="utf-8")
        else:
            materials = deepcopy(materials)
            materials["actual_output_schema"] = actual_schema
            materials["materials_identity"] = common.canonical_sha({k: v for k, v in materials.items() if k != "materials_identity"})
            prompt.write_text("Use complete governed originals\n" + json.dumps(materials), encoding="utf-8")
        if response is None and materials is not None and materials["phase"] == "generation":
            original = materials["root_request"]["input"]
            response = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
                "stage": original["stage"], "ordinal": original["ordinal"],
                "parent_draft_identities": [row["identity"] for row in original["prior_drafts"]], "content": deepcopy(self.value["content"])}
            response = carrier(response)
        elif response is None and materials is not None and materials["phase"] == "independent_admission":
            response = self.review(state, proposal=materials["proposal"])
        response = response or {"status": "offline-transport-ok"}
        common.atomic_json(call_root / "fixture-response.json", response)
        output = sandbox / "r.json"
        binding_path, host = call_root / f"execution-binding-{number}-r.json", call_root / "host.json"
        request, payload, measurement = runtime.prepare_dispatch(self.root, run, state, runner, sandbox, prompt,
            schema, output, number, binding_path, timeout_sec=5)
        request["timeout_sec"] = 5
        request["request_sha256"] = common.canonical_sha({k: v for k, v in request.items() if k != "request_sha256"})
        ledger = state.setdefault("capability_selection", {"calls": []})
        index = len(ledger["calls"]) + 1
        row = {"number": index, "run_id": state["run_id"], "reservation_id": state["run_id"] + ":dispatch:" + str(index),
            "status": "reserved", "candidate": slot, "phase": phase, "generation": 1, "execution": 1,
            "capability_id": "scope", "request_identity": request}
        ledger["calls"].append(row)
        common.atomic_json(run / "run.json", state)
        cache = self.root / "offline-model-metadata"
        cache.mkdir(exist_ok=True)
        common.atomic_json(cache / "models_cache.json", {"models": [{"slug": "fixture-model"}]})
        with patch.dict(os.environ, {"CODEX_HOME": str(cache)}):
            receipt = common.run_isolated_model(runner, workspace=sandbox, prompt_path=prompt, output_path=output,
                output_schema=schema, timeout_sec=5, model_request_budget=1, execution_log=host,
                wall_timeout_sec=5, suppress_bytecode=True)
        binding = runtime.capture_binding(sandbox, prompt, schema, output, payload, measurement, host, info, receipt)
        common.atomic_json(binding_path, binding)
        if materials is not None and materials["phase"] == "generation":
            common.atomic_json(call_root / "canonical-draft.json", runtime.decode_generation_carrier(response))
        row["outcome"] = {"status": "completed", "error_type": None, "output_sha256": common.file_sha(output),
            "active_elapsed_seconds": binding["host_execution"]["active_elapsed_seconds"]}
        common.atomic_json(run / "run.json", state)
        self.assertEqual(runtime.verify_call(binding), response)
        self.assertEqual(runtime.verify_reserved_call(run, row), binding)
        return binding, row

    def test_full_capture_protocol_reserved_roundtrip_and_cross_slot_run_substitutions(self):
        run, state = self.create()
        first, row = self.bound_call(run, state)
        sandbox, output = Path(first["workspace"]), Path(first["output_path"])
        runtime.verify_bound_reservation(run, state, first, candidate_slot="candidate-1", scope_id="scope", phase="generate",
            generation=1, execution=1, expected_workspace=sandbox, expected_output=output)
        other, _ = self.bound_call(run, state, "candidate-2")
        with self.assertRaises(ValueError):
            runtime.verify_bound_reservation(run, state, other, candidate_slot="candidate-1", scope_id="scope", phase="generate",
                generation=1, execution=1, expected_workspace=sandbox, expected_output=output)
        with self.assertRaises(ValueError):
            runtime.verify_bound_reservation(run, state, other, candidate_slot="candidate-1", scope_id="scope", phase="generate",
                generation=1, execution=1, expected_workspace=Path(other["workspace"]), expected_output=Path(other["output_path"]))
        another_run, another_state = self.create(run_id="other-run")
        with self.assertRaises(ValueError):
            runtime.verify_bound_reservation(another_run, another_state, first, candidate_slot="candidate-1", scope_id="scope",
                phase="generate", generation=1, execution=1, expected_workspace=sandbox, expected_output=output)
        edited = deepcopy(first)
        edited["receipt"]["model"] = "requested-not-returned"
        edited["binding_sha256"] = common.canonical_sha({k: v for k, v in edited.items() if k != "binding_sha256"})
        with self.assertRaises(ValueError):
            runtime.verify_call(edited)
        stderr = next(Path(first["workspace"]).glob("*.app-server.stderr.txt"))
        original = stderr.read_bytes()
        stderr.write_bytes(original + b"changed original stderr")
        with self.assertRaisesRegex(ValueError, "generated_output_changed"):
            runtime.verify_call(first)
        stderr.write_bytes(original)
        self.assertEqual(row["outcome"]["status"], "completed")

    def test_hash_bound_runner_high_expectation_rejects_default_child_protocol(self):
        # Capture a genuine default-effort fake turn before testing a forged high claim.
        fixture_environment = patch.dict(os.environ, {"NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "medium"})
        fixture_environment.start()
        self.addCleanup(fixture_environment.stop)
        os.environ.pop("NEWROGUE_CODEX_REASONING_EFFORT", None)
        run, state = self.create()
        binding, _ = self.bound_call(run, state)
        binding["runner_info"]["requested_reasoning_effort"] = "high"
        binding["binding_sha256"] = common.canonical_sha({k: v for k, v in binding.items() if k != "binding_sha256"})
        with self.assertRaises(codec.CodecError) as failed:
            runtime.verify_call(binding)
        self.assertEqual(failed.exception.diagnostic.entity_id, "receipt.reasoning_effort")

    def test_carrier_raw_binding_and_canonical_artifact_substitutions_rejected(self):
        run, state = self.create()
        base = runtime.seed(state, run / "analysis-input")
        materials = runtime.request_payload(self.frozen, phase="generation", seed_value=base, batch=1)
        materials.update(runtime_identity=state["runtime_identity"], run_id=state["run_id"], slot="candidate-1",
            generation=1, execution=1, lineage_identity=runtime.lineage_identity(state, base, "candidate-1", 1))
        binding, row = self.bound_call(run, state, materials=materials)
        raw = runtime.verify_call(binding)
        self.assertIn("content_json", raw)
        self.assertNotIn("content", raw, "Physical replay must return the original carrier")
        canonical_path = (run / row["request_identity"]["execution_binding_path"]).parent / "canonical-draft.json"
        canonical_bytes = canonical_path.read_bytes()
        self.assertTrue(runtime.same_json(common.load_json(canonical_path), runtime.decode_generation_carrier(raw)))
        changed = common.load_json(canonical_path)
        changed["content"]["unexpected_original"] = True
        common.atomic_json(canonical_path, changed)
        try:
            with self.assertRaisesRegex(ValueError, "canonical_draft_changed"):
                runtime.verify_reserved_call(run, row)
        finally:
            canonical_path.write_bytes(canonical_bytes)
        output = Path(binding["output_path"])
        original = output.read_bytes()
        try:
            # Even a valid decoded draft cannot replace the raw model response.
            output.write_bytes(canonical_bytes)
            substituted = deepcopy(binding)
            substituted["output_sha256"] = common.file_sha(output)
            substituted["binding_sha256"] = common.canonical_sha({k: v for k, v in substituted.items() if k != "binding_sha256"})
            with self.assertRaises(ValueError):
                runtime.verify_call(substituted)
        finally:
            output.write_bytes(original)
        self.assertEqual(runtime.verify_reserved_call(run, row), binding)

    def test_nested_genuine_other_slot_binding_cannot_replace_this_slots_charged_proof(self):
        run, state = self.create()
        base = runtime.seed(state, run / "analysis-input")
        scope = runtime.scopes(state, run / "analysis-input")[0]
        records = []
        for slot in ("candidate-1", "candidate-2"):
            identity = runtime.lineage_identity(state, base, slot, 1)
            material = {"phase": "generation", "runtime_identity": state["runtime_identity"], "run_id": state["run_id"],
                "root_input_identity": self.frozen["input_identity"], "slot": slot, "generation": 1, "execution": 1,
                "lineage_identity": identity, "lineage_context": 1, "repair_issue": None,
                "root_request": runtime.request_payload(self.frozen, phase="generation", seed_value=base, batch=1)["root_request"]}
            generated, grow = self.bound_call(run, state, slot, 1, materials=material)
            material["phase"] = "independent_admission"
            material["proposal"] = deepcopy(self.value)
            reviewed, rrow = self.bound_call(run, state, slot, 2, materials=material, phase="semantic")
            workspace = selection.scope_workspace(run, slot, 0, 1)
            common.atomic_json(workspace / "capability-append/append-ledger.json", {"calls": [
                {"number": 1, "phase": "generate", "context": 1, "reservation_id": grow["reservation_id"]},
                {"number": 2, "phase": "semantic", "context": 1, "reservation_id": rrow["reservation_id"]}]})
            record = {"scope": scope, "context": 1, "delta": {"lineage": {"slot": slot, "generation": 1,
                "execution": 1, "context": 1, "identity": identity}, "generation_calls": [generated]}, "execution": reviewed}
            runtime.verify_proof_reservations(self.root, state, {"seed": base, "records": [record]},
                admission={"candidate": slot})
            records.append(record)
        substituted = deepcopy(records[0])
        substituted["delta"]["generation_calls"][0] = records[1]["delta"]["generation_calls"][0]
        with self.assertRaises(ValueError):
            runtime.verify_proof_reservations(self.root, state, {"seed": base, "records": [substituted]},
                admission={"candidate": "candidate-1"})
        substituted = deepcopy(records[0])
        substituted["execution"] = records[1]["execution"]
        with self.assertRaises(ValueError):
            runtime.verify_proof_reservations(self.root, state, {"seed": base, "records": [substituted]},
                admission={"candidate": "candidate-1"})
        changed_run = deepcopy(state)
        changed_run["run_id"] = "other-run"
        with self.assertRaises(ValueError):
            runtime.verify_proof_reservations(self.root, changed_run, {"seed": base, "records": [records[0]]},
                admission={"candidate": "candidate-1"})

    def test_completed_selector_without_receipt_is_terminal_without_another_paid_call(self):
        RuntimeTests.assembly(self, interrupt_selector=True)

    def complete_offline_transport_coordinator(self, profile, *, complete_wire=False, candidate_contents=None):
        run, state = self.create(profile, complete_wire=complete_wire)
        candidate_count = len(runtime.labels(state))
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        config = {"runner": str(runner.resolve()), "runner_sha256": common.file_sha(runner), "backend": "offline-transport",
            "backend_info": official.description(), "timeout_sec": 5}
        state["runner_configuration"] = config
        common.atomic_json(run / "run.json", state)
        cache = self.root / "offline-model-metadata"
        cache.mkdir()
        common.atomic_json(cache / "models_cache.json", {"models": [{"slug": "fixture-model"}]})
        observed = []
        def factory(workspace, *, outcome=None):
            class Mailbox:
                reservation = None
                def request(self, kind, **data):
                    if kind != "outcome":
                        raise AssertionError(kind)
                    if outcome is not None:
                        return outcome(data["reservation_id"], data["outcome"])
                    # Inline candidate transport uses an explicit parent-journal
                    # publisher fixture. No validation function is replaced.
                    row = next(row for row in state["capability_selection"]["calls"] if row["reservation_id"] == data["reservation_id"])
                    row["outcome"] = data["outcome"]
                    common.atomic_json(run / "run.json", state)
                    common.atomic_json(run / "dispatch-receipts" / f"dispatch-{row['number']}.json",
                        {**{k: v for k, v in row.items() if k != "outcome"}, **row["outcome"]})
                    return True
            mailbox = Mailbox()
            actual = worker.runner_invoke(self.root, run, state, workspace, config, mailbox)
            def invoke(prompt, number, *, output_name, output_schema_path, output_schema, before_dispatch):
                if output_name == "selection.json":
                    aliases = list("ABC"[:candidate_count])
                    response = {"status": "selected", "selected": "A", "candidate_reviews": [
                        {"candidate": alias, "rank": index + 1, "verdict": "viable", "rationale": "Offline comparison fixture"}
                        for index, alias in enumerate(aliases)]}
                    observed.append("selector")
                else:
                    payload = runtime.wire.read_prompt(prompt, runtime.wire_delivery(state))
                    observed.append(payload["phase"])
                    if payload["phase"] == "generation":
                        original = payload["root_request"]["input"]
                        self.assertEqual(output_schema, runtime.generation_producer_schema(self.frozen, payload))
                        response = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
                            "stage": original["stage"], "ordinal": original["ordinal"],
                            "parent_draft_identities": [row["identity"] for row in original["prior_drafts"]],
                            "content": deepcopy(self.value["content"] if candidate_contents is None
                                else candidate_contents[payload["slot"]])}
                        response = carrier(response)
                    else:
                        response = {"schema_version": runtime.REVIEW, "input_identity": self.frozen["input_identity"],
                            "runtime_identity": state["runtime_identity"], "proposal_sha256": common.canonical_sha(payload["proposal"]),
                            "verdict": "approved", "findings": [], "checks": [{"id": row["id"], "verdict": "approved",
                                "rationale": "Offline source-qualified semantic fixture", "source_block_ids": row["source_block_ids"][:1]}
                                for row in payload["obligations"]]}
                        response = fixture_review_carrier(response, payload)
                common.atomic_json(workspace / "fixture-response.json", response)
                def reserved(request_identity):
                    before_dispatch(request_identity=request_identity)
                    mailbox.reservation = deepcopy(state["capability_selection"]["calls"][-1])
                    return mailbox.reservation
                output, execution = actual(prompt, number, output_name=output_name, output_schema_path=output_schema_path,
                    output_schema=output_schema, before_dispatch=reserved)
                if output_name == "selection.json":
                    from openai_isolated_model_runner import _file_section
                    sandbox = Path(execution["execution_binding"]["workspace"])
                    for name in (*[alias + ".json" for alias in "ABC"[:candidate_count]], "accepted-seed.json", "comparison-context.json"):
                        if complete_wire:
                            self.assertFalse((sandbox / name).exists())
                            materials = runtime.wire.read_prompt(prompt, runtime.wire_delivery(state))
                            original = (workspace / name).read_bytes()
                            expected = json.loads(original)
                            if name == "comparison-context.json":
                                from _mvg_evidence_transport import restore_lossless_context
                                expected = restore_lossless_context(expected)
                            self.assertEqual(runtime.wire.text(materials["files"][name]["value"]), runtime.wire.text(expected))
                            self.assertEqual(materials["files"][name]["raw_digest"], codec.raw_digest(original))
                        else:
                            self.assertIn(_file_section(sandbox, sandbox / name), execution["execution_binding"]["request_payload"])
                return output, execution
            return invoke
        with patch.dict(os.environ, {"CODEX_HOME": str(cache), "SC_KNOWLEDGE_PLANNING_RUNNER": str(runner.resolve()),
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            try:
                result = selection.generate_selected_capabilities(self.root, run, state, backend="offline-transport",
                    invoke_factory=lambda budget, workspace, label: factory(workspace), selector_factory=factory)
            except ValueError as exc:
                self.fail(str(exc) + repr(state.get("candidate_admissions")))
            self.assertEqual(result["candidate_count"], candidate_count)
            self.assertEqual(observed.count("independent_admission"), candidate_count)
            self.assertEqual(observed.count("selector"), 1)
            self.assertEqual(state["capability_selection"]["total_invocations"], 3 * candidate_count + 1)
            delivery = runtime.handoff(self.root, run, state)
            step = deepcopy(state["capability_selection"]["selected"][0])
            stored = checkpoint.load_checkpoint(run, step["checkpoint"])
            other_slot = next(label for label in step["admissions"] if label != step["selected_candidate"])
            other_proof = common.load_json(run / step["admissions"][other_slot]["proof_path"])
            receipt_path = run / step["receipt_path"]
            original_receipt = receipt_path.read_bytes()
            borrowed = json.loads(original_receipt)
            borrowed["execution_binding"] = other_proof["records"][-1]["execution"]
            try:
                common.atomic_json(receipt_path, borrowed)
                step["receipt_sha256"] = common.file_sha(receipt_path)
                with self.assertRaises(ValueError):
                    selection._selected_step(self.root, run, state, runtime.scopes(state, run / "analysis-input"), 0,
                        stored["accepted_seed"], [], step)
            finally:
                receipt_path.write_bytes(original_receipt)
            common.atomic_json(run / "handoff.json", delivery)
            before = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
            original = deepcopy(state)
            selection.generate_selected_capabilities(self.root, run, state, backend="offline-transport",
                invoke_factory=None, selector_factory=None)
            self.assertEqual(state, original)
            self.assertEqual(before, {path: path.read_bytes() for path in run.rglob("*") if path.is_file()})
            self.assertEqual(runtime.handoff(self.root, run, state), delivery)
        self.assertEqual(set(runtime.generation_schemas()), {"common", "flow-graph", "planning-candidate"})
        return delivery, state, run

    def test_complete_offline_transport_coordinator_keeps_all_production_binding_validators(self):
        self.complete_offline_transport_coordinator("3b-mvg-v1")

    def test_capability_offline_transport_coordinator_keeps_all_production_binding_validators(self):
        self.complete_offline_transport_coordinator("3b-capabilities-v1")


class CompleteWireTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    create = RuntimeTests.create
    complete_offline_transport_coordinator = ReviewFixTests.complete_offline_transport_coordinator

    def test_complete_wire_lossless_types_order_nested_namespaces_and_ref_tampering(self):
        wire = runtime.wire
        original = {"unknown": [{"value": False}, {"value": 0}, {"value": 0.0}, {"value": None}],
            "unicode": "\u4e2d\u6587\r\n\u00e9\r", "$mvg_ref": 99, "$mvg_object": [["literal", "data"]],
            "nested_legacy": wire.lossless_context({"large": ["original " * 200] * 6}),
            "duplicates": [{"text": "full original " * 400, "nested": {"$mvg_ref": "literal"}}] * 8}
        envelope = wire.encode(original)
        self.assertEqual(wire.text(wire.decode(envelope)), wire.text(original))
        self.assertEqual(wire.read_prompt(wire.render("Use complete governed originals", original, wire.SCHEMA), wire.SCHEMA), original)
        for mutation in ("version", "bytes", "identity", "extra", "content", "encoded-shape", "encoded-version", "dangling", "cycle"):
            broken = deepcopy(envelope)
            if mutation == "version": broken["schema_version"] += ".unknown"
            elif mutation == "bytes": broken["materials_bytes_sha256"] = "foreign"
            elif mutation == "identity": broken["materials_identity"] = "foreign"
            elif mutation == "extra": broken["unknown"] = True
            elif mutation == "content": broken["encoded"]["content_sha256"] = "foreign"
            elif mutation == "encoded-shape": broken["encoded"] = []
            elif mutation == "encoded-version": broken["encoded"]["schema_version"] = "unknown"
            elif mutation == "dangling": broken["encoded"]["value"] = {"$mvg_ref": 999999}
            else:
                broken["encoded"]["shared"] = [{"$mvg_ref": 0}]
                broken["encoded"]["value"] = {"$mvg_ref": 0}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): wire.decode(broken)
        with self.assertRaises(ValueError): wire.read_prompt(wire.render("header", original, wire.SCHEMA))
        with self.assertRaises(ValueError): wire.read_prompt("header\n" + wire.text(original), wire.SCHEMA)
        with self.assertRaises(ValueError): wire.read_prompt("header\n{}", "unknown")

    def wire_generation(self, state, draft):
        payload = runtime.request_payload(self.frozen, phase="generation", seed_value=runtime.seed(state, self.run / "analysis-input"),
            drafts=[draft], delivery=runtime.wire.SCHEMA)
        payload.update(content_contract=runtime.generation_schemas(), final_content_target=runtime.generation_target(),
            runtime_identity=state["runtime_identity"], run_id=state["run_id"], slot="candidate-1", generation=1, execution=1)
        payload["lineage_identity"] = runtime.lineage_identity(state, payload["accepted_seed"], "candidate-1", 1)
        schema = runtime.generation_schema(self.frozen, payload["root_request"], delivery=runtime.wire.SCHEMA)
        payload["actual_output_schema"] = schema
        payload["materials_identity"] = common.canonical_sha({k: v for k, v in payload.items() if k != "materials_identity"})
        return payload, schema

    def prepare_actual(self, state, payload, schema, name):
        sandbox = self.run / name / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        prompt, schema_path = sandbox / "prompt.txt", sandbox / "schema.json"
        prompt.write_text(runtime.materials_prompt(payload), encoding="utf-8", newline="\n")
        common.atomic_json(schema_path, schema)
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        state["runner_configuration"] = {"backend_info": official.description()}
        return runtime.prepare_dispatch(self.root, self.run, state, runner, sandbox, prompt, schema_path,
            sandbox / "r.json", 1, self.run / name / "binding.json", timeout_sec=5)

    def test_large_canonical_draft_kept_complete_and_final_encoded_wrapper_preflighted(self):
        self.run, state = self.create(complete_wire=True)
        draft = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"], "stage": "batch", "ordinal": 1,
            "parent_draft_identities": [], "content": {"unknown": [{"text": "Preserve \u4e2d\u6587 reward order. " * 2000,
                "typed": [False, 0, 0.0, None], "$mvg_ref": "literal source key"}] * 35}}
        with self.assertRaises(planning.CapacityBlocked): planning.build_request(self.frozen, previous_drafts=[draft])
        payload, schema = self.wire_generation(state, draft)
        self.assertEqual(runtime.wire.text(payload["root_request"]["input"]["prior_drafts"][0]["value"]), runtime.wire.text(draft))
        request, actual, measured = self.prepare_actual(state, payload, schema, "fit")
        self.assertEqual(request["wire_delivery"], runtime.wire.SCHEMA)
        self.assertLess(measured["request_bytes"], self.frozen["inputs"]["contract"]["limits"]["max_bytes"])
        self.assertEqual(measured, runtime.measure_actual(self.frozen, actual, schema))
        self.assertNotIn("capability_selection", state)
        restored = runtime.wire.read_prompt(runtime.materials_prompt(payload), runtime.wire.SCHEMA)
        self.assertEqual(runtime.wire.text(restored), runtime.wire.text(payload))
        with self.assertRaises(ValueError): planning.build_wire_request(self.frozen, wire_delivery="unknown", previous_drafts=[draft])
        limits = self.frozen["inputs"]["contract"]["limits"]
        with self.assertRaisesRegex(ValueError, "runner_context_budget_exceeded"):
            planning.measure_request(json.dumps({"prompt": actual, "output_schema": schema}, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False), max_bytes=limits["max_bytes"],
                max_input_tokens=runtime.measure_actual(self.frozen, actual, schema)["input_token_estimate"] + limits["reserved_tokens"] - 1,
                reserved_tokens=limits["reserved_tokens"])
        (self.run / "fit/sandbox/padding.txt").write_bytes(b"x" * limits["max_bytes"])
        with self.assertRaises(ValueError): self.prepare_actual(state, payload, schema, "fit")
        self.assertNotIn("capability_selection", state)

    def test_final_content_guidance_and_metadata_are_bound_without_repairing_invalid_content(self):
        self.run, state = self.create(complete_wire=True)
        draft = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"], "stage": "batch", "ordinal": 1,
            "parent_draft_identities": [], "content": deepcopy(self.value["content"])}
        payload, schema = self.wire_generation(state, draft)
        self.prepare_actual(state, payload, schema, "original")
        self.assertEqual(payload["final_content_target"]["json_pointer"], "/properties/content")
        self.assertIn("entire", payload["final_content_target"]["cross_field_rules"]["verification_projection"].lower())
        self.assertEqual(set(payload["content_contract"]), {"common", "flow-graph", "planning-candidate"})
        instruction = runtime.materials_prompt(payload).split("\n", 1)[0]
        self.assertIn("Generate NEW", instruction)
        self.assertNotIn("complete original content object", instruction)
        historical = deepcopy(payload)
        historical.pop("wire_delivery")
        self.assertIn("complete original content object", runtime.materials_prompt(historical).split("\n", 1)[0])
        for mutation in ("target", "schema", "root", "delivery", "extra", "identity"):
            altered, changed_schema = deepcopy(payload), deepcopy(schema)
            if mutation == "target": altered["final_content_target"]["json_pointer"] = "/input"
            elif mutation == "schema": changed_schema["properties"]["ordinal"]["const"] = 999
            elif mutation == "root": altered["root_request"]["input"]["prior_drafts"][0]["value"]["content"]["unknown"] = 0
            elif mutation == "delivery": altered["wire_delivery"] = "unknown"
            elif mutation == "extra": altered["unbound"] = "extra orchestration"
            else: altered["materials_identity"] = "wrong"
            if mutation != "identity":
                altered["actual_output_schema"] = changed_schema
                altered["materials_identity"] = common.canonical_sha({k: v for k, v in altered.items() if k != "materials_identity"})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.prepare_actual(state, altered, changed_schema, mutation)
        for mutation in ("extras", "projection", "unused", "owner", "entry"):
            invalid = deepcopy(self.value)
            content = invalid["content"]
            if mutation == "extras": content.update(prior_drafts=[draft], synthesis_context={"input": "orchestration"})
            elif mutation == "projection": content["coverage_table"][0]["rationale"] += "different"
            elif mutation == "unused": content["evidence_source_refs"].append(self.fixture.owned("planning_proof", "native-manifest.json"))
            elif mutation == "owner": content["source_identity"]["ledger_ref"]["files"].extend(content["source_identity"]["manifest_ref"]["files"])
            else:
                entry = deepcopy(content["definitions"]["flows"][0]["graph"]["boundaries"][0])
                entry["id"] += "-second"
                content["definitions"]["flows"][0]["graph"]["boundaries"].append(entry)
            before = runtime.wire.text(invalid)
            with self.subTest(mutation=mutation): self.fixture.rejects(invalid)
            self.assertEqual(before, runtime.wire.text(invalid), "Original invalid output is never stripped or repaired")

    def test_selector_virtual_files_restore_complete_comparison_and_reject_host_tampering(self):
        from _mvg_evidence_transport import lossless_context, restore_lossless_context, MODEL_ENCODING
        for profile in runtime.PROFILES:
            run, state = self.create(profile, run_id=profile, complete_wire=True)
            scope = runtime.scopes(state, run / "analysis-input")[0]
            base = runtime.seed(state, run / "analysis-input")
            aliases = dict(zip("ABC", runtime.labels(state)))
            proposals = {label: deepcopy(self.value) for label in aliases.values()}
            workspace = run / "selector-materials"
            workspace.mkdir()
            for alias, label in aliases.items(): common.atomic_json(workspace / (alias + ".json"), proposals[label])
            common.atomic_json(workspace / "accepted-seed.json", base)
            comparison = {alias: {"frozen_input": self.frozen, "scope": scope, "accepted_seed": base, "proposal": proposals[label]}
                          for alias, label in aliases.items()}
            common.atomic_json(workspace / "comparison-context.json", lossless_context(comparison))
            originals = {path: path.read_bytes() for path in workspace.iterdir()}
            # Wire assembly only: this fixture does not assert semantic admission.
            public = {"candidates": {alias: {"proposal_sha256": common.canonical_sha(proposals[label])}
                                     for alias, label in aliases.items()}, "order_index": 0}
            materials = runtime.selector_materials(state, self.frozen, scope, public, base, proposals, aliases, workspace)
            restored = runtime.wire.read_prompt(runtime.selector_prompt(materials), runtime.wire_delivery(state))
            self.assertEqual(runtime.wire.text(restored), runtime.wire.text(materials))
            file = restored["files"]["comparison-context.json"]
            self.assertEqual(file["decoded_from"], MODEL_ENCODING)
            self.assertEqual(runtime.wire.text(file["value"]), runtime.wire.text(comparison))
            self.assertEqual(runtime.wire.text(file["value"]), runtime.wire.text(restore_lossless_context(json.loads(originals[workspace / "comparison-context.json"]))))
            for name in ("A.json", "accepted-seed.json", "comparison-context.json"):
                path = workspace / name
                path.write_bytes(originals[path] + b" ")
                with self.subTest(profile=profile, name=name), self.assertRaisesRegex(ValueError, "original_artifact_changed"):
                    runtime.selector_materials(state, self.frozen, scope, public, base, proposals, aliases, workspace)
                path.write_bytes(originals[path])
            self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_final_actual_token_limit_blocks_before_any_reservation(self):
        import hashlib
        self.run, state = self.create(complete_wire=True)
        unique = " ".join(hashlib.sha256(str(index).encode()).hexdigest()[:20] for index in range(14000))
        draft = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"], "stage": "batch", "ordinal": 1,
            "parent_draft_identities": [], "content": {"unknown_complete_original": unique}}
        payload, schema = self.wire_generation(state, draft)
        with self.assertRaisesRegex(ValueError, "runner_context_budget_exceeded"):
            self.prepare_actual(state, payload, schema, "token-limit")
        self.assertNotIn("capability_selection", state)

    def test_selector_alias_domain_and_checked_path_precede_host_reads_and_ledger_replay(self):
        run, state = self.create(complete_wire=True)
        scope = runtime.scopes(state, run / "analysis-input")[0]
        base = runtime.seed(state, run / "analysis-input")
        labels = runtime.labels(state)
        aliases = dict(zip(selection.alias_keys(state), labels))
        proposals = {label: deepcopy(self.value) for label in labels}
        workspace = run / "selector-alias-boundary"
        workspace.mkdir()
        # A valid original bound public domain can coexist with a later edited ledger domain.
        materials = {"identity": {"order_index": 0, "candidates": {alias: {} for alias in aliases}}}
        invalid = [{**aliases, "A": labels[1]}, {"A": labels[0]}, {**aliases, "C": "foreign-candidate"}]
        for bad in ("../harmless-outside", str(self.root / "harmless-absolute")):
            invalid.append({bad: labels[0], **{alias: label for alias, label in aliases.items() if alias != "A"}})
        for changed in invalid:
            reads = []
            def forbidden_read(path):
                reads.append(str(path))
                raise AssertionError("Host bytes attempted before alias validation: " + str(path))
            with self.subTest(aliases=changed):
                with patch.object(Path, "read_bytes", new=forbidden_read), self.assertRaisesRegex(ValueError, "selector_aliases"):
                    runtime.selector_materials(state, self.frozen, scope, materials["identity"], base, proposals, changed, workspace)
                self.assertEqual(reads, [], "No attempted outside or unvalidated read, including fictitious harmless targets")
                state["capability_selection"] = {"selected": [], "current": {"order_index": 0, "aliases": changed, "admissions": {}}}
                with patch.object(selection, "candidate_artifacts", side_effect=AssertionError("Aliases precede replay artifact access")), \
                        self.assertRaisesRegex(ValueError, "selector_aliases"):
                    runtime.check_selector_materials(self.root, run, state, materials, workspace)
        with patch.object(runtime.sources, "checked_path", side_effect=ValueError("checked-host-stop")) as checked, \
                patch.object(Path, "read_bytes", side_effect=AssertionError("No unchecked host read")):
            with self.assertRaisesRegex(ValueError, "checked-host-stop"):
                runtime.selector_materials(state, self.frozen, scope, materials["identity"], base, proposals, aliases, workspace)
            checked.assert_called_once_with(workspace, "A.json")

    def test_selector_rehashed_index_metadata_refused_before_reservation(self):
        run, state = self.create(complete_wire=True)
        aliases = dict(zip(selection.alias_keys(state), runtime.labels(state)))
        state["capability_selection"] = {"selected": [], "current": {"order_index": 0, "aliases": aliases, "admissions": {}}}
        state["runner_configuration"] = {"backend_info": official.description()}
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        schema = runtime.selection_schema(state)
        sandbox = run / "selector-index/llm-sandbox/attempt-1/selection"
        sandbox.mkdir(parents=True)
        schema_path, prompt_path = sandbox / "schema.json", sandbox / "prompt.txt"
        common.atomic_json(schema_path, schema)
        for index in (False, -1, 1, "0", 0.0):
            materials = {"wire_delivery": runtime.wire.SCHEMA, "phase": "selection", "runtime_identity": state["runtime_identity"],
                "run_id": state["run_id"], "identity": {"order_index": index, "candidates": {alias: {} for alias in aliases}}}
            materials["materials_identity"] = common.canonical_sha(materials)
            prompt = runtime.selector_prompt(materials)
            prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            self.assertEqual(runtime.wire.text(runtime.wire.read_prompt(prompt, runtime.wire.SCHEMA)), runtime.wire.text(materials))
            with self.subTest(index=index), patch.object(selection, "candidate_artifacts",
                    side_effect=AssertionError("Index must reject before reconstructing candidate artifacts")), \
                    self.assertRaisesRegex(ValueError, "selector_scope_index_invalid"):
                runtime.prepare_dispatch(self.root, run, state, runner, sandbox, prompt_path, schema_path,
                    sandbox / "selection.json", 1, run / "binding.json", timeout_sec=5)
            self.assertEqual(state["capability_selection"].get("calls", []), [])

    def test_native_wire_mvg_coordinator_full_protocol_and_selector(self):
        self.complete_offline_transport_coordinator("3b-mvg-v1", complete_wire=True)

    def test_native_wire_capability_coordinator_full_protocol_and_selector(self):
        self.complete_offline_transport_coordinator("3b-capabilities-v1", complete_wire=True)


class CompactWireTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    prepare_actual = CompleteWireTests.prepare_actual
    test_compact_selector_virtual_files_and_original_file_tampering = (
        CompleteWireTests.test_selector_virtual_files_restore_complete_comparison_and_reject_host_tampering)

    def create(self, profile="3b-mvg-v1", run_id="runtime", *, complete_wire=True):
        return RuntimeTests.create(self, profile, run_id, complete_wire=complete_wire,
            wire_delivery=runtime.wire.CURRENT_SCHEMA)

    def complete_offline_transport_coordinator(self, profile, *, complete_wire=False):
        # The synthetic response is explicit test data, never provider evidence.
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high",
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            ReviewFixTests.complete_offline_transport_coordinator(self, profile, complete_wire=complete_wire)

    def generation(self, state):
        draft = {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
            "stage": "batch", "ordinal": 1, "parent_draft_identities": [],
            "content": {"unknown": [{"source": "Complete original \u4e2d\u6587. " * 600,
                "types": [False, 0, 0.0, None], "$mvg_ref": "literal marker"}] * 7}}
        delivery = runtime.wire_delivery(state)
        payload = runtime.request_payload(self.frozen, phase="generation",
            seed_value=runtime.seed(state, self.run / "analysis-input"), drafts=[draft], delivery=delivery)
        payload.update(content_contract=runtime.generation_schemas(), final_content_target=runtime.generation_target(),
            runtime_identity=state["runtime_identity"], run_id=state["run_id"], slot="candidate-1", generation=1, execution=1)
        payload["lineage_identity"] = runtime.lineage_identity(state, payload["accepted_seed"], "candidate-1", 1)
        schema = runtime.generation_schema(self.frozen, payload["root_request"], delivery=delivery)
        payload["actual_output_schema"] = schema
        payload["materials_identity"] = common.canonical_sha({k: v for k, v in payload.items() if k != "materials_identity"})
        return payload, schema

    def test_native_default_and_versioned_descriptor_preserve_original_limits(self):
        for profile in runtime.PROFILES:
            planner = runtime.PROFILES[profile][0]
            run = runtime.run_location(self.root, planner, profile)
            state = runtime.create_run(self.root, run, profile, self.ref, profile)
            self.assertEqual(runtime.wire_delivery(state), runtime.wire.CURRENT_SCHEMA)
            self.assertEqual(state["mvg.run_invocation_limit"], runtime.PROFILES[profile][2])
            self.assertEqual(runtime.descriptor(state)["limits"], runtime.profile_limits(profile))
            self.assertIn("_b_route_compact_literal.py", runtime.rules_identity()["runtime"])
            for delivery in (None, "unknown", [], True):
                broken = deepcopy(state)
                broken["planning_runtime"]["wire_delivery"] = delivery
                broken["runtime_identity"] = common.canonical_sha(broken["planning_runtime"])
                with self.subTest(profile=profile, delivery=delivery), self.assertRaises(ValueError):
                    runtime.descriptor(broken)

    def test_compact_generation_actual_string_wrapper_bound_before_reservation(self):
        self.run, state = self.create()
        payload, schema = self.generation(state)
        request, actual, measured = self.prepare_actual(state, payload, schema, "compact-fit")
        self.assertIs(type(actual), str)
        self.assertEqual(request["wire_delivery"], runtime.wire.CURRENT_SCHEMA)
        self.assertEqual(measured, runtime.measure_actual(self.frozen, actual, schema))
        self.assertEqual(measured["token_counter"], "max(o200k_base,cl100k_base)+10_percent")
        restored = runtime.wire.read_prompt(runtime.materials_prompt(payload), runtime.wire.CURRENT_SCHEMA)
        self.assertEqual(runtime.wire.text(restored), runtime.wire.text(payload))
        self.assertNotIn("capability_selection", state)
        for delivery in (runtime.wire.SCHEMA, "unknown"):
            changed = deepcopy(payload)
            changed["wire_delivery"] = delivery
            changed["materials_identity"] = common.canonical_sha({k: v for k, v in changed.items() if k != "materials_identity"})
            with self.subTest(delivery=delivery), self.assertRaises(ValueError):
                self.prepare_actual(state, changed, schema, "mixed-" + str(len(delivery)))
        self.assertNotIn("capability_selection", state)

    def test_compact_mixed_versions_and_literal_expression_tampering_rejected(self):
        from _b_route_compact_literal import dumps
        wire = runtime.wire
        value = {"unknown": [False, 0, 0.0, None], "text": "Complete original \u4e2d\u6587\r\n", "$mvg_ref": "literal"}
        current = wire.render("Use complete governed originals", value, wire.CURRENT_SCHEMA)
        self.assertEqual(wire.text(wire.read_prompt(current, wire.CURRENT_SCHEMA)), wire.text(value))
        self.assertEqual(wire.decode(wire.encode(value)), value)
        with self.assertRaises(ValueError): wire.decode(wire.encode(value, wire.CURRENT_SCHEMA))
        with self.assertRaises(ValueError): wire.read_prompt(current, wire.SCHEMA)
        with self.assertRaises(ValueError): wire.read_prompt(current)
        with self.assertRaises(ValueError): wire.read_prompt(wire.render("header", value, wire.SCHEMA), wire.CURRENT_SCHEMA)
        with self.assertRaises(ValueError): wire.read_prompt("header\n" + dumps(wire.encode(value)), wire.CURRENT_SCHEMA)
        for body in (current.split("\n", 1)[1] + " ", "__import__('os').system('forbidden')"):
            with self.subTest(body=body[:40]), self.assertRaises(ValueError):
                wire.read_prompt("header\n" + body, wire.CURRENT_SCHEMA)

    def test_projection_guidance_is_new_delivery_only_and_machine_still_rejects_changes(self):
        self.run, state = self.create()
        payload, _ = self.generation(state)
        instruction = runtime.materials_prompt(payload).split("\n", 1)[0]
        for field in ("source_block_ids", "acceptance_intent", "non_task_sinks", "prior_requirement_ids"):
            self.assertIn(field, instruction)
        self.assertIn("Copy those complete original values", instruction)
        for delivery in (None, runtime.wire.SCHEMA):
            old = deepcopy(payload)
            if delivery is None: old.pop("wire_delivery")
            else: old["wire_delivery"] = delivery
            self.assertNotIn("Copy those complete original values", runtime.materials_prompt(old).split("\n", 1)[0])
        invalid = deepcopy(self.value)
        invalid["content"]["requirements"][0]["acceptance_intent"] += " changed original"
        before = runtime.wire.text(invalid)
        issues = runtime.machine(self.root, state, invalid)
        self.assertTrue(any(row.get("detail", {}).get("expected") == "preserved original acceptance_intent" for row in issues))
        self.assertEqual(runtime.wire.text(invalid), before)

    def test_native_compact_mvg_coordinator_full_protocol_and_selector(self):
        self.complete_offline_transport_coordinator("3b-mvg-v1", complete_wire=True)

    def test_native_compact_capability_coordinator_full_protocol_and_selector(self):
        self.complete_offline_transport_coordinator("3b-capabilities-v1", complete_wire=True)


class TimeAndDeadlineFixTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    create = RuntimeTests.create

    def test_capability_literal_legacy_helper_boundary_and_mvg_original_timeout(self):
        _run, state = self.create("3b-capabilities-v1")
        state["runner_configuration"] = {"backend_info": official.description()}
        for consumed in (0, 2700, 3299.5, 3899, 3899.5, 3900):
            state["capability_selection"] = {"calls": [{"candidate": "candidate-1",
                "outcome": {"active_elapsed_seconds": consumed}}]}
            legacy = {"budget": {"total_budget_sec": 13500, "activity_sec": consumed, "candidate_budget_sec": 2700,
                "candidate_activity_sec": {"candidate-1": consumed}, "request_limit": 96,
                "model_requests_observed": 0, "model_requests_reserved": 0}}
            if int(3900 - consumed) < 1:
                with self.assertRaises(ValueError):
                    plan_capabilities._remaining_attempt_budget(legacy, label="candidate-1", timeout_sec=2700,
                        runner_info=official.description(), synthesis_timeout_sec=1200)
                with self.assertRaises(append.RunBudgetExhausted):
                    selection.funded_timeout(state, "candidate-1", {"requested_timeout_sec": 3900})
            else:
                actual = plan_capabilities._remaining_attempt_budget(legacy, label="candidate-1", timeout_sec=2700,
                    runner_info=official.description(), synthesis_timeout_sec=1200)
                self.assertEqual(selection.funded_timeout(state, "candidate-1", {"requested_timeout_sec": 3900}), actual)
        _run, mvg = self.create("3b-mvg-v1", "mvg-timeout")
        mvg["capability_selection"] = {"calls": [{"candidate": "candidate-1", "outcome": {"active_elapsed_seconds": 999999}}]}
        self.assertIsNone(selection.remaining_time(mvg, "candidate-1"))
        self.assertEqual(selection.funded_timeout(mvg, "candidate-1", {"requested_timeout_sec": 4321}), 4321)

    def test_actual_coordinator_reservation_and_worker_timeout_clamps_or_refuses(self):
        cases = [("slot", 3890, 0, False, 10), ("run", 0, 13494, False, 6),
                 ("synthesis", 2800, 0, True, 1100), ("slot-subsecond", 3899.5, 0, False, None),
                 ("run-subsecond", 0, 13499.5, False, None)]
        for name, slot_time, other_time, synthesis, expected in cases:
            with self.subTest(name=name):
                run, state = self.create("3b-capabilities-v1", name)
                runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
                config = {"runner": str(runner.resolve()), "runner_sha256": common.file_sha(runner),
                    "backend_info": official.description(), "backend": "offline-clock-fixture", "timeout_sec": 2700}
                state["runner_configuration"] = config
                scope = runtime.scopes(state, run / "analysis-input")[0]
                base = runtime.seed(state, run / "analysis-input")
                prior_calls = [{"number": 1, "candidate": "candidate-1", "outcome": {"active_elapsed_seconds": slot_time}},
                               {"number": 2, "candidate": "candidate-2", "outcome": {"active_elapsed_seconds": other_time}}]
                state["capability_selection"] = {"binding": "accounting-fixture", "order": ["scope"], "selected": [],
                    "accepted_sha256": common.canonical_sha(base), "current": None, "total_invocations": 2,
                    "calls": prior_calls, "lineage_invocations": {"candidate-1": 1, "candidate-2": 1}}
                common.atomic_json(run / "run.json", state)
                observed = []
                def generation(root, private, workspace, **kwargs):
                    target = workspace / "capability-append/c3"
                    class Mailbox:
                        reservation = None
                        def request(self, kind, **data):
                            if kind == "outcome":
                                state["capability_selection"]["calls"][-1]["outcome"] = data["outcome"]
                                common.atomic_json(run / "run.json", state)
                                return True
                            raise AssertionError(kind)
                    mailbox = Mailbox()
                    invoke = worker.runner_invoke(root, run, private, target, config, mailbox)
                    schema = target / "schema.json"
                    # This accounting fixture exercises the real dispatcher and
                    # reservation; proof qualification is not under test here.
                    def reserve(request_identity):
                        request_identity["synthesis"] = synthesis
                        return kwargs["before_call"]("generate", request_identity=request_identity)
                    try:
                        invoke("Offline controlled-clock accounting fixture", 3, output_name="r.json",
                            output_schema_path=schema, output_schema={"type": "object"}, before_dispatch=reserve)
                    except append.RunBudgetExhausted:
                        raise
                    except RuntimeError:
                        pass
                    return {"status": "blocked", "total_invocations": 1, "errors": [{"code": "fixture_stop"}]}
                def dispatch(*args, **kwargs):
                    saved = common.load_json(run / "run.json")["capability_selection"]["calls"][-1]
                    observed.append((saved["request_identity"]["timeout_sec"], kwargs["timeout_sec"], kwargs["wall_timeout_sec"]))
                    raise RuntimeError("Offline stop after timeout observation")
                with patch.object(selection, "verified_prefix", return_value=([scope], base, [])), \
                     patch.object(selection, "valid_current_candidates", return_value=[]), \
                     patch.object(selection, "generate_append", side_effect=generation), \
                     patch.object(selection, "_monotonic", return_value=100), \
                     patch.object(runtime, "validate_input", return_value=None), \
                     patch.object(runtime, "frozen_input", return_value=self.frozen), \
                     patch.object(plan_mvg, "run_isolated_model", side_effect=dispatch), \
                     patch("_mvg_capability_generation.preflight_dispatch", return_value=None):
                    with self.assertRaises(ValueError):
                        selection.generate_selected_capabilities(self.root, run, state, backend="offline-clock-fixture",
                            invoke_factory=None, selector_factory=None)
                if expected is None:
                    self.assertEqual(observed, [])
                    self.assertEqual(state["capability_selection"]["total_invocations"], 2)
                else:
                    self.assertEqual(observed, [(expected, expected, expected)])
                    self.assertEqual(state["capability_selection"]["total_invocations"], 3)

    def test_existing_worker_deadline_reaps_stalled_owned_preparation_and_keeps_unknown_charge(self):
        import time
        run, state = self.create("3b-capabilities-v1")
        workspace = run / "worker-deadline"
        workspace.mkdir()
        wrapper = self.root / "stalled-worker-fixture.py"
        wrapper.write_text('''import argparse, json, os, sys, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--job", type=Path);p.add_argument("--start-gate", action="store_true");a=p.parse_args()
if sys.stdin.buffer.readline() == b"start\\n":
    job=json.loads(a.job.read_bytes());mail=a.job.parent/"mailbox"
    request={"identity":job["identity"],"sequence":1,"kind":"reserve","phase":"generate","request_identity":{}}
    (mail/"1.request.json").write_text(json.dumps(request),encoding="utf-8")
    while not (mail/"1.response.json").exists():time.sleep(.01)
    time.sleep(30)
''', encoding="utf-8", newline="\n")
        original = subprocess.Popen
        processes, charges = [], []
        def launch(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).resolve() == Path(worker.__file__).resolve():
                command = [command[0], str(wrapper), *command[2:]]
            process = original(command, *args, **kwargs)
            processes.append(process)
            return process
        def reserve(*args):
            row = {"reservation_id": "fixture:dispatch:1", "status": "reserved"}
            charges.append(row)
            return row
        started = time.monotonic()
        with patch.object(subprocess, "Popen", side_effect=launch):
            with self.assertRaisesRegex(TimeoutError, "candidate_worker_deadline_exhausted"):
                worker.run_candidate(workspace / "lifecycle", {"workspace": str(workspace), "state": state},
                    reserve=reserve, cost_budget=lambda *_: {}, outcome=lambda *_: self.fail("Unknown outcome must stay unknown"), timeout_sec=1)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(processes and all(process.poll() is not None for process in processes))
        self.assertEqual(charges, [{"reservation_id": "fixture:dispatch:1", "status": "reserved"}])
        self.assertTrue((workspace / "lifecycle/lifecycle-timeout.json").exists())
        self.assertFalse((workspace / "lifecycle/result.json").exists())
