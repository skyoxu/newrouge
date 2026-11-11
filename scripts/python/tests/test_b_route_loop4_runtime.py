"""Loop-four offline entry/publication controls, never native qualification.

Source audit preparation uses the existing explicit fixture seam. The producer
test stubs only execution replay; business classification uses the real native
candidate/record/source validators. Publication uses actual Windows rename.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

import _b_route_codec as codec
import _b_route_planning_runtime as runtime
import _mvg_capability_append as append
import _mvg_capability_generation as generation
import _mvg_capability_worker as worker
import _planning_skill_common as common
import codex_isolated_model_runner as official
import plan_mvg
import test_b_route_planning_runtime as fixtures
import test_b_route_records as record_fixtures


class Loop4EntryTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp

    def create(self, name="loop4", profile="3b-mvg-v1"):
        run = runtime.run_location(self.root, runtime.PROFILES[profile][0], name)
        return run, runtime.create_run(self.root, run, name, self.ref, profile)

    def test_fresh_create_enters_compiled_producer_with_zero_one_two_original_parents(self):
        run, state = self.create()
        self.assertEqual(state["b_route_output_schema_policy"], runtime.PROVIDER_SCHEMA_POLICY)
        self.assertEqual(state["b_route_machine_business_policy"], runtime.MACHINE_BUSINESS_POLICY)
        drafts, calls = [], []
        for number, batch in enumerate((1, None, None), 1):
            materials = runtime.request_payload(self.frozen, phase="generation", seed_value={},
                batch=batch, drafts=drafts, delivery=runtime.wire.CURRENT_SCHEMA)
            expected = materials["root_request"]["input"]
            draft = {"schema_version": runtime.planning.DRAFT, "input_identity": self.frozen["input_identity"],
                "stage": expected["stage"], "ordinal": expected["ordinal"],
                "parent_draft_identities": [row["identity"] for row in expected["prior_drafts"]],
                "content": {"unknown": [False, 0, "exact Unicode \u4e2d\u6587\r\n", {"nested": None}]}}
            canonical = runtime.accounted_generation_schema(self.frozen, materials["root_request"],
                delivery=runtime.wire.CURRENT_SCHEMA)
            captured = []
            directory = run / ("producer-" + str(number))
            directory.mkdir()
            def factory(workspace):
                def invoke(prompt, attempt, **kwargs):
                    captured.append((prompt, deepcopy(kwargs["output_schema"])))
                    common.atomic_json(workspace / "output-schema.json", kwargs["output_schema"])
                    output = workspace / "r.json"
                    common.atomic_json(output, fixtures.carrier(draft))
                    kwargs["before_dispatch"]({"synthetic_request": number})
                    return output, {"execution_binding": {"synthetic_leaf": True}}
                return invoke
            with patch.object(runtime, "verify_call", return_value={}):
                result, _ = runtime.invoke_data(factory, self.frozen, directory, number, materials, canonical,
                    "generate", lambda *args: calls.append(args), state=state)
            schema = captured[0][1]
            array = schema["properties"]["parent_draft_identities"]
            self.assertNotIn("const", array)
            self.assertEqual((array["minItems"], array["maxItems"]), (len(drafts), len(drafts)))
            self.assertTrue(runtime.same_json(result, draft))
            self.assertEqual(captured[0][0], runtime.materials_prompt(materials))
            runtime.check_generation_schema(self.frozen, materials, schema)
            runtime.planning.validate_draft_chain(self.frozen, [*drafts, result])
            if len(drafts) == 2:
                for wrong in (list(reversed(draft["parent_draft_identities"])),
                              [draft["parent_draft_identities"][0]] * 2, [True, False]):
                    with self.assertRaises(ValueError):
                        runtime.decode_generation_output(self.frozen, materials,
                            {**fixtures.carrier(draft), "parent_draft_identities": wrong})
            drafts.append(result)
        self.assertEqual(len(calls), 3)
        self.assertNotIn("capability_selection", common.load_json(run / "run.json"))

    def test_historical_absent_policy_is_not_filled_or_reinterpreted(self):
        run, state = self.create()
        historical = deepcopy(state)
        historical.pop("b_route_output_schema_policy")
        historical.pop("b_route_machine_business_policy")
        original = deepcopy(historical)
        payload = runtime.request_payload(self.frozen, phase="generation", seed_value={}, batch=1)
        schema = runtime.generation_producer_schema(self.frozen, payload)
        self.assertEqual(schema["properties"]["parent_draft_identities"]["const"], [])
        self.assertEqual(runtime.admission_machine(self.root, historical, self.value), [])
        self.assertEqual(historical, original)
        self.assertEqual(common.load_json(run / "run.json"), state)

    def test_live_high_matches_current_and_captured_description(self):
        _run, state = self.create()
        for captured, current, environment in ((None, "high", "high"), ("low", "high", "high"),
                ("high", None, "high"), ("high", "low", "high"),
                ("high", "high", None), ("high", "high", "low")):
            state["runner_configuration"] = {"backend_info": {"requested_reasoning_effort": captured}}
            with self.subTest(captured=captured, current=current, environment=environment), patch.dict(os.environ, {}, clear=False):
                if environment is None:
                    os.environ.pop("NEWROGUE_CODEX_REASONING_EFFORT", None)
                else:
                    os.environ["NEWROGUE_CODEX_REASONING_EFFORT"] = environment
                with self.assertRaisesRegex(ValueError, "live_.*(high|effort_changed)"):
                    runtime.require_live_high(state, current_info={"requested_reasoning_effort": current})
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high"}):
            info = official.description()
            state["runner_configuration"] = {"backend_info": info}
            runtime.require_live_high(state, current_info=info)

    def test_actual_high_prepare_keeps_compiled_schema_and_complete_request_for_both_profiles(self):
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        for profile in runtime.PROFILES:
            run, state = self.create(profile, profile)
            with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high"}):
                info = official.description()
                state["runner_configuration"] = {"backend_info": info}
                payload = runtime.request_payload(self.frozen, phase="generation",
                    seed_value=runtime.seed(state, run / "analysis-input"), batch=1,
                    delivery=runtime.wire.CURRENT_SCHEMA)
                payload.update(content_contract=runtime.generation_schemas(), final_content_target=runtime.generation_target(),
                    runtime_identity=state["runtime_identity"], run_id=state["run_id"], slot="candidate-1", generation=1, execution=1,
                    output_schema_policy=runtime.PROVIDER_SCHEMA_POLICY,
                    issue_account_policy=runtime.issue_account_policy(state),
                    machine_business_policy=runtime.MACHINE_BUSINESS_POLICY)
                payload["lineage_identity"] = runtime.lineage_identity(state, payload["accepted_seed"], "candidate-1", 1)
                schema = runtime.generation_producer_schema(self.frozen, payload)
                payload["actual_output_schema"] = schema
                payload["materials_identity"] = common.canonical_sha({k: v for k, v in payload.items() if k != "materials_identity"})
                sandbox = run / "positive/sandbox"
                sandbox.mkdir(parents=True)
                prompt, schema_path = sandbox / "prompt.txt", sandbox / "schema.json"
                prompt.write_text(runtime.materials_prompt(payload), encoding="utf-8", newline="\n")
                common.atomic_json(schema_path, schema)
                # The harmless --describe subprocess is real; no model turn,
                # reservation, execution receipt or validation seam is supplied.
                request, actual, measured = runtime.prepare_dispatch(self.root, run, state, runner, sandbox,
                    prompt, schema_path, sandbox / "r.json", 1, run / "binding.json", timeout_sec=5)
                self.assertEqual(request["runner_info_sha256"], common.canonical_sha(info))
                self.assertEqual(request["planning_profile"], profile)
                self.assertEqual(measured, runtime.measure_actual(self.frozen, actual, schema))
                self.assertEqual(runtime.bound_materials({"prompt_path": str(prompt), "schema_path": str(schema_path)},
                    state, self.frozen), payload)
                self.assertNotIn("capability_selection", state)
                for wrong in (None, "future"):
                    changed = deepcopy(payload)
                    if wrong is None:
                        changed.pop("machine_business_policy")
                    else:
                        changed["machine_business_policy"] = wrong
                    changed["materials_identity"] = common.canonical_sha({k: v for k, v in changed.items() if k != "materials_identity"})
                    prompt.write_text(runtime.materials_prompt(changed), encoding="utf-8", newline="\n")
                    with self.assertRaisesRegex(ValueError, "machine_business_material_policy_changed"):
                        runtime.bound_materials({"prompt_path": str(prompt), "schema_path": str(schema_path)}, state, self.frozen)

    def test_prepare_both_profiles_rejects_effort_before_frozen_reads_and_reservation(self):
        for profile in runtime.PROFILES:
            run, state = self.create(profile, profile)
            state["runner_configuration"] = {"backend_info": {"requested_reasoning_effort": "high"}}
            before = (run / "run.json").read_bytes()
            for environment in (None, "low"):
                with patch.dict(os.environ, {}, clear=False), patch.object(runtime, "frozen_input", side_effect=AssertionError("too late")):
                    if environment is None:
                        os.environ.pop("NEWROGUE_CODEX_REASONING_EFFORT", None)
                    else:
                        os.environ["NEWROGUE_CODEX_REASONING_EFFORT"] = environment
                    with self.assertRaisesRegex(ValueError, "live_dispatch_requires_high"):
                        runtime.prepare_dispatch(self.root, run, state, Path("unused.py"), run,
                            run / "prompt", run / "schema", run / "out", 1, run / "binding", timeout_sec=1)
            self.assertEqual((run / "run.json").read_bytes(), before)
            self.assertNotIn("capability_selection", state)

    def test_worker_common_prepare_blocks_before_call_callback(self):
        run, state = self.create()
        runner = Path(__file__).parent / "fixtures/b_route_bound_protocol_runner.py"
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high"}):
            info = official.description()
        config = {"runner": str(runner), "runner_sha256": common.file_sha(runner),
                  "backend_info": info, "timeout_sec": 5}
        state["runner_configuration"] = config
        mailbox = Mock(reservation=None)
        before_call = Mock(side_effect=AssertionError("reservation reached"))
        with patch.dict(os.environ, {}, clear=False), patch.object(plan_mvg, "_validate_input_freshness"), \
                patch.object(generation, "preflight_dispatch"), patch.object(plan_mvg, "run_isolated_model") as dispatch:
            invoke = worker.runner_invoke(self.root, run, state, run / "worker", config, mailbox)
            os.environ.pop("NEWROGUE_CODEX_REASONING_EFFORT", None)
            with self.assertRaisesRegex(ValueError, "live_dispatch_requires_high"):
                invoke("synthetic data", 1, output_name="r.json", output_schema_path=run / "schema.json",
                    output_schema={"type": "object"}, before_dispatch=before_call)
        before_call.assert_not_called()
        mailbox.request.assert_not_called()
        dispatch.assert_not_called()


class Loop4BusinessTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    create = Loop4EntryTests.create

    def duplicate(self, original=None, *, kind="command"):
        value = deepcopy(self.value if original is None else original)
        if kind == "flow":
            first = value["content"]["definitions"]["flows"][0]
            second = deepcopy(first)
            second["entry_condition"] += " with conflicting entry"
            second["proposed_owner_key"] = "second-flow-owner"
            value["content"]["definitions"]["flows"].append(second)
        else:
            value["content"]["definitions"][runtime.candidate.PLURALS[kind]] = [
                {"id": "DUP-CMD", "proposed_owner_key": "owner-1", "requirement_ids": [],
                 "responsibility": "First independently declared responsibility", "uses": []},
                {"id": "DUP-CMD", "proposed_owner_key": "owner-2", "requirement_ids": [],
                 "responsibility": "Second conflicting responsibility", "uses": []}]
        return value

    def test_real_tuple_owner_is_clean_replaced_with_original_round_account(self):
        for kind in runtime.candidate.PLURALS:
            with self.subTest(kind=kind):
                self.assert_tuple_round_account(kind)

    def assert_tuple_round_account(self, kind):
        run, state = self.create(kind)
        value = self.duplicate(kind=kind)
        issue = runtime.admission_machine(self.root, state, value)[0]
        self.assertEqual(issue["detail"]["entity_id"], str((kind, value["content"]["definitions"][runtime.candidate.PLURALS[kind]][0]["id"])))
        self.assertFalse(runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=state))
        with self.assertRaisesRegex(ValueError, "repair_domain_unresolved"):
            runtime.repair_domain(value, self.frozen, issue)
        scope = runtime.scopes(state, run / "analysis-input")[0]
        seed = runtime.seed(state, run / "analysis-input")
        state["capability_selection"] = {"current": {"capability_id": scope["capability_id"]}, "calls": [
            {"number": 1, "outcome": None, "reservation_id": "old-unknown"}]}
        original_calls = deepcopy(state["capability_selection"]["calls"])
        contexts = []
        def propose(scope, accepted, prior, finding, context, call):
            self.assertEqual(accepted, seed)
            self.assertIsNone(prior)
            self.assertIsNone(finding)
            call("generate")
            contexts.append(context)
            return deepcopy(value)
        result = append.run_capability_append(run / "business", scopes=[scope], seed=seed,
            identity=state["runtime_identity"], propose=propose,
            machine=lambda scope, accepted, proposal: runtime.admission_machine(self.root, state, proposal),
            final_machine=lambda proposal: runtime.admission_machine(self.root, state, proposal),
            semantic=Mock(side_effect=AssertionError("business blocked before review")),
            merge=lambda base, delta, scope: deepcopy(delta), preserve=lambda *_: [],
            repairability=lambda before, finding: runtime.repair_is_local(before, self.frozen, finding, root=self.root, state=state),
            replacement=lambda **event: runtime.replacement_reservation(state, "candidate-1", **event),
            invocation_limit=64, fail_execution_closed=True)
        self.assertEqual((result["status"], result["total_invocations"]), ("retired", 4))
        self.assertEqual(contexts, [1, 2, 3, 4])
        self.assertTrue(all(row["repair_attempts"] == 0 for row in result["restarts"]))
        self.assertEqual(state["capability_selection"]["replacement_depths"]["candidate-1"], 3)
        self.assertEqual(state["capability_selection"]["calls"], original_calls)
        self.assertEqual(result["accepted"], seed)
        for slot in runtime.labels(state)[1:]:
            self.assertEqual(state["capability_selection"]["replacement_depths"][slot], 0)

    def test_tuple_does_not_hide_schema_identity_provenance_or_source_errors(self):
        _run, state = self.create()
        original = self.duplicate()
        issue = runtime.admission_machine(self.root, state, original)[0]
        mutations = (
            lambda value: value.update(input_identity="sha256:" + "0" * 64),
            lambda value: value["content"].update(extra_field="invalid schema"),
            lambda value: value["provenance"].update(kind="model_draft"),
            lambda value: value["content"]["source_identity"].update(source_revision="foreign revision"),
            lambda value: value["content"]["source_identity"].update(source_manifest_digest="sha256:" + "0" * 64),
            lambda value: value["content"]["source_identity"]["manifest_ref"]["files"][0].update(raw_digest="sha256:" + "0" * 64),
            lambda value: value["content"]["requirements"][0].update(acceptance_intent="changed immutable source"))
        for mutate in mutations:
            value = deepcopy(original)
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=state)
        forged = deepcopy(issue)
        forged["detail"]["entity_id"] = str(("command", "another"))
        with self.assertRaisesRegex(ValueError, "original_host_finding"):
            runtime.repair_is_local(original, self.frozen, forged, root=self.root, state=state)

    def test_tuple_does_not_hide_selected_dependency_id_revision_schema_digest_or_native_source(self):
        candidate_fixture = self.fixture
        candidate_fixture.selected_plan()
        self.frozen, self.value = candidate_fixture.frozen, candidate_fixture.value
        self.ref = candidate_fixture.prepared["resume_ref"]
        _run, state = self.create()
        value = self.duplicate()
        issue = runtime.admission_machine(self.root, state, value)[0]
        self.assertFalse(runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=state))
        for field, wrong in (("entity_id", "foreign"), ("revision", 99),
                ("schema_version", "newrouge.b-route-policy.v1"), ("digest", "sha256:" + "0" * 64)):
            changed = deepcopy(value)
            changed["content"]["selected_dependencies"][0][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                runtime.repair_is_local(changed, self.frozen, issue, root=self.root, state=state)
        selected = candidate_fixture.dependency_models[candidate_fixture.dependency_paths[0]]
        selected["source_identity"]["source_revision"] = "bad selected source"
        candidate_fixture.freeze_dependencies("mixed-source", out_of_scope=["REQ-p"])
        self.frozen, self.value = candidate_fixture.frozen, candidate_fixture.value
        self.ref = candidate_fixture.prepared["resume_ref"]
        _run, new_state = self.create("mixed")
        with self.assertRaises(ValueError):
            runtime.admission_machine(self.root, new_state, self.duplicate())

    def test_equivalent_tuple_kinds_fail_closed_for_source_tamper_and_selected_only_findings(self):
        _run, state = self.create()
        for kind in runtime.candidate.PLURALS:
            with self.subTest(kind=kind):
                value = self.duplicate(kind=kind)
                issue = runtime.admission_machine(self.root, state, value)[0]
                self.assertFalse(runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=state))
                changed = deepcopy(value)
                changed["content"]["source_identity"]["source_revision"] = "foreign source"
                with self.assertRaises(ValueError):
                    runtime.repair_is_local(changed, self.frozen, issue, root=self.root, state=state)
                frozen_only = deepcopy(issue)
                frozen_only["detail"]["expected"] = "one explicitly selected effective owner"
                self.assertFalse(runtime.duplicate_proposed_owner_issue(value, frozen_only))
                with self.assertRaisesRegex(ValueError, "original_host_finding"):
                    runtime.repair_is_local(value, self.frozen, frozen_only, root=self.root, state=state)
                # A single mutable definition cannot repair a selected-only collision.
                changed = deepcopy(value)
                changed["content"]["definitions"][runtime.candidate.PLURALS[kind]].pop()
                self.assertFalse(runtime.duplicate_proposed_owner_issue(changed, issue))

    def test_real_selected_only_collisions_remain_frozen_for_all_definition_kinds(self):
        candidate_fixture = self.fixture
        candidate_fixture.selected_plan()
        originals = deepcopy(candidate_fixture.dependency_models)
        candidate_fixture.dependency_paths = list(originals)
        for kind, plural in runtime.candidate.PLURALS.items():
            with self.subTest(kind=kind):
                candidate_fixture.dependency_models = deepcopy(originals)
                for plan in candidate_fixture.dependency_models.values():
                    definition = (record_fixtures.flow("FROZEN-DUP", "REQ-p") if kind == "flow" else
                        {"id": "FROZEN-DUP", "requirement_ids": [], "responsibility": "Frozen shared owner", "uses": []})
                    plan["definitions"] = {name: [] for name in runtime.candidate.PLURALS.values()}
                    plan["definitions"][plural].append(definition)
                candidate_fixture.freeze_dependencies("frozen-" + kind, out_of_scope=["REQ-p"])
                self.frozen, self.value = candidate_fixture.frozen, candidate_fixture.value
                self.value["content"]["logical_references"] = []
                self.ref = candidate_fixture.prepared["resume_ref"]
                _run, state = self.create("frozen-" + kind)
                issue = runtime.admission_machine(self.root, state, self.value)[0]
                self.assertEqual(issue["detail"]["expected"], "one explicitly selected effective owner")
                self.assertEqual(issue["detail"]["entity_id"], str((kind, "FROZEN-DUP")))
                self.assertFalse(runtime.duplicate_proposed_owner_issue(self.value, issue))
                with self.assertRaisesRegex(ValueError, "repair_domain_unresolved"):
                    runtime.repair_is_local(self.value, self.frozen, issue, root=self.root, state=state)

    def test_unverified_machine_or_execution_errors_never_authorize_replacement(self):
        _run, state = self.create()
        for issue in ({"code": "b_route_machine:invented", "path": "candidate:content", "detail": {}},
                      {"code": "append_execution_failure", "path": "model", "detail": "failed"}):
            with self.subTest(issue=issue), self.assertRaisesRegex(ValueError, "original_host_finding"):
                runtime.repair_is_local(self.value, self.frozen, issue, root=self.root, state=state)


class Loop4PublicationTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    create = Loop4EntryTests.create

    def test_each_initial_write_interruption_preserves_non_authoritative_stage_and_allows_fresh_initialization(self):
        actual = runtime.atomic_json
        for point in ("b-route-prepared.json", "run.json", "initialization.json"):
            for after in (False, True):
                name = "p" + str(len(list((self.root / "logs").rglob(".init-*"))))
                run = runtime.run_location(self.root, "mvg", name)
                def interrupted(path, value):
                    if path.name == point:
                        if after:
                            actual(path, value)
                        raise OSError("synthetic initialization interruption")
                    return actual(path, value)
                with patch.object(runtime, "atomic_json", side_effect=interrupted), self.assertRaises(OSError):
                    runtime.create_run(self.root, run, name, self.ref, "3b-mvg-v1")
                self.assertFalse(run.exists())
                stages = {p: p.read_bytes() for d in run.parent.glob(".init-*") for p in d.rglob("*") if p.is_file()}
                self.assertTrue(list(run.parent.glob(".init-*")))
                state = runtime.create_run(self.root, run, name, self.ref, "3b-mvg-v1")
                self.assertEqual(common.load_json(run / "run.json"), state)
                self.assertEqual(common.load_json(run / "analysis-input/b-route-prepared.json"), self.frozen)
                self.assertTrue((run / "initialization.json").is_file())
                self.assertEqual(stages, {p: p.read_bytes() for p in stages})

    def test_actual_competing_publishers_have_one_complete_winner_and_keep_loser_stage(self):
        run = runtime.run_location(self.root, "mvg", "race")
        barrier = threading.Barrier(2)
        actual = os.rename
        def simultaneous(source, target):
            barrier.wait(timeout=20)
            return actual(source, target)
        def initialize():
            try:
                return runtime.create_run(self.root, run, "race", self.ref, "3b-mvg-v1")
            except FileExistsError:
                return "existing"
        with patch.object(os, "rename", side_effect=simultaneous), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: initialize(), range(2)))
        self.assertEqual(results.count("existing"), 1)
        winner = next(value for value in results if isinstance(value, dict))
        self.assertEqual(common.load_json(run / "run.json"), winner)
        self.assertEqual(common.load_json(run / "analysis-input/b-route-prepared.json"), self.frozen)
        self.assertEqual(len(list(run.parent.glob(".init-*"))), 1)
        before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
        status = runtime.operate(self.root, planner="mvg", command="status", run_id="race",
            prepared_ref=self.ref, profile="3b-mvg-v1")
        self.assertEqual(status["selection_status"], "pending")
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_foreign_partial_target_and_unknown_ledger_are_never_adopted_or_modified(self):
        run = runtime.run_location(self.root, "mvg", "partial")
        run.mkdir(parents=True)
        unknown = run / "unknown-ledger.json"
        unknown.write_bytes(b'{"reservation_id":"old","outcome":null,"released":0}')
        original = unknown.read_bytes()
        with self.assertRaises(FileExistsError):
            runtime.create_run(self.root, run, "partial", self.ref, "3b-mvg-v1")
        with self.assertRaisesRegex(ValueError, "incomplete_or_foreign"):
            runtime.operate(self.root, planner="mvg", command="generate", run_id="partial",
                prepared_ref=self.ref, profile="3b-mvg-v1")
        self.assertEqual(unknown.read_bytes(), original)
        self.assertEqual([p.name for p in run.iterdir()], [unknown.name])

    def test_interruption_after_directory_rename_retains_complete_authority_for_reentry(self):
        run = runtime.run_location(self.root, "mvg", "renamed")
        actual = os.rename
        def interrupted(source, target):
            actual(source, target)
            raise OSError("synthetic interruption after atomic publish")
        with patch.object(os, "rename", side_effect=interrupted), self.assertRaises(FileExistsError):
            runtime.create_run(self.root, run, "renamed", self.ref, "3b-mvg-v1")
        before = (run / "run.json").read_bytes()
        with patch.object(runtime, "create_run", side_effect=AssertionError("must reuse complete run")):
            status = runtime.operate(self.root, planner="mvg", command="status", run_id="renamed",
                prepared_ref=self.ref, profile="3b-mvg-v1")
        self.assertEqual(status["selection_status"], "pending")
        self.assertEqual((run / "run.json").read_bytes(), before)


class FreshProfileProtocolTests(unittest.TestCase):
    """Complete synthetic stdio/production-binding controls on fresh policies.

    The shared helper supplies only source preparation and synthetic model
    content/transport. Schema/canonical/business/admission/reservation/selector
    and checkpoint validation run unchanged, without the historical create seam.
    """
    setUp = fixtures.RuntimeTests.setUp
    review = fixtures.RuntimeTests.review

    def create(self, profile="3b-mvg-v1", run_id="fresh", *, complete_wire=False):
        planner = runtime.PROFILES[profile][0]
        self.run = runtime.run_location(self.root, planner, run_id)
        self.state = runtime.create_run(self.root, self.run, run_id, self.ref, profile)
        self.assertEqual(self.state["b_route_output_schema_policy"], runtime.PROVIDER_SCHEMA_POLICY)
        self.assertEqual(self.state["b_route_machine_business_policy"], runtime.MACHINE_BUSINESS_POLICY)
        self.assertEqual(runtime.wire_delivery(self.state), runtime.wire.CURRENT_SCHEMA)
        return self.run, self.state

    def complete(self, profile):
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high",
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            fixtures.ReviewFixTests.complete_offline_transport_coordinator(self, profile, complete_wire=True)
        self.assertEqual(self.state["selection_status"], "selected")
        for step in self.state["capability_selection"]["selected"]:
            for admitted in step["admissions"].values():
                proof = common.load_json(self.run / admitted["proof_path"])
                self.assertEqual(proof["machine_business_policy"], runtime.MACHINE_BUSINESS_POLICY)
                for record in proof["records"]:
                    for binding in [*record["delta"]["generation_calls"], record["execution"]]:
                        materials = runtime.wire.read_prompt(Path(binding["prompt_path"]).read_text(encoding="utf-8"),
                            runtime.wire.CURRENT_SCHEMA)
                        self.assertEqual(materials["machine_business_policy"], runtime.MACHINE_BUSINESS_POLICY)
                        if materials["phase"] == "generation":
                            self.assertEqual(materials["output_schema_policy"], runtime.PROVIDER_SCHEMA_POLICY)
                            self.assertNotIn("const", materials["actual_output_schema"]["properties"]["parent_draft_identities"])

    def test_fresh_mvg_full_protocol_binding_admission_selector_and_checkpoint(self):
        self.complete("3b-mvg-v1")

    def test_fresh_capability_full_protocol_binding_admission_selector_and_checkpoint(self):
        self.complete("3b-capabilities-v1")


if __name__ == "__main__":
    unittest.main()
