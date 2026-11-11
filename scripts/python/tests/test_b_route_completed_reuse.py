"""Offline completed-closure controls; synthetic transport is not native AC proof.

The integration fixture runs the original coordinator, paid-binding readers,
checkpoint and receipt owners. Only its producer transport/audit are synthetic.
No test invokes a provider or grants formal adoption/runtime eligibility.
"""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import _b_route_completed_reuse as reuse
import _b_route_planning_runtime as runtime
import _b_route_codec as codec
import _mvg_capability_recovery as recovery
import _mvg_capability_selection as selection
import _mvg_global_audit as audit
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
import test_b_route_planning_runtime as fixtures


class ReservedGenerationStateDataTests(unittest.TestCase):
    def test_original_archived_generation_is_used_after_pending_clears_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary)
            row={'number':1,'generation':1,'request_identity':{'planning_profile':'DATA-only'}}
            prior={'run_id':'DATA-only','capability_selection':{'generation':1,'calls':[row],
                'selected':[{'original':'retained selector'}]}}
            archive=run/'reopen-history/prior.json'
            atomic_json(archive,{'prior_state':prior})
            entry={'generation':2,'path':'reopen-history/prior.json','sha256':file_sha(archive)}
            pending={'run_id':'DATA-only','capability_selection':{'generation':2,'calls':[row],'selected':[]},
                'reopen_history':[entry]}
            atomic_json(run/'run.json',pending)
            self.assertIs(runtime._reserved_state(run,row,prior),prior)
            self.assertEqual(runtime._reserved_state(run,row,pending),prior)
            changed=deepcopy(prior);changed['run_id']='another-run'
            atomic_json(archive,{'prior_state':changed})
            with self.assertRaises(ValueError):runtime._reserved_state(run,row,pending)
            entry['sha256']=file_sha(archive)
            with self.assertRaisesRegex(ValueError,'generation_history_changed'):
                runtime._reserved_state(run,row,pending)

    def test_historical_mode_and_given_state_reach_original_receipt_verifier(self):
        import _mvg_capability_generation as generation
        state={'capability_selection':{'generation':1}}
        row={'number':1,'generation':1,'request_identity':{'planning_profile':'DATA-only'}}
        with patch.object(runtime,'verify_reserved_call') as verify:
            generation.verify_dispatch_receipts(Path('DATA-not-a-workspace'),[row],state=state,check_originals=False)
        verify.assert_called_once_with(Path('DATA-not-a-workspace'),row,state=state,check_originals=False)


class CompleteInputBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.prepared = Path(temporary.name)
        self.row = {"capability_id": "CAP-one", "unknown": {"flags": [True, 1], "text": "exact  text"}}

    def freeze(self, value, *, target=None, contexts=None):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        target = target or {"scope_id": "scope", "kind": "capability", "ids": ["CAP-one"]}
        closure = {"source_paths": ["source.json"], "mode": "full_audit", "reason": "fixture", "entities": []}
        envelope = {"inputs": {"contract": {"scope": target}, "closure": closure,
            "contexts": contexts or [], "evidence": [{"path": "source.json", "text": raw.decode("utf-8"),
                "sha256": codec.raw_digest(raw)}]}}
        atomic_json(self.prepared / "b-route-prepared.json", envelope)
        return {"unit_kind": "governed_planning_closure", "scope": target, "closure": closure}

    def test_complete_original_row_key_ignores_format_and_preserves_unknown_fields_types_and_order(self):
        scope = self.freeze({"capabilities": [self.row]})
        bound = reuse.binding(self.prepared, scope)
        self.assertEqual(bound["json_pointer"], "/capabilities/0")
        digest = recovery.capability_hash(bound["capability"])
        reordered = {"unknown": {"text": "exact  text", "flags": [True, 1]}, "capability_id": "CAP-one"}
        scope = self.freeze({"capabilities": [reordered]})
        self.assertEqual(digest, recovery.capability_hash(reuse.capability(self.prepared, scope)))
        for value in ([1, True], [True, "1"], [1, 1]):
            changed = deepcopy(self.row)
            changed["unknown"]["flags"] = value
            scope = self.freeze([changed])
            self.assertNotEqual(digest, recovery.capability_hash(reuse.capability(self.prepared, scope)))

    def test_multiple_targets_duplicate_rows_and_nested_references_stay_fresh(self):
        cases = [({"capabilities": [self.row, self.row]}, None),
            ({"nested": {"capabilities": [self.row]}}, None),
            ({"planning_relations": {"entities": [{"kind": "capability", "id": "CAP-one"}]}}, None),
            ({"capabilities": [self.row]}, {"scope_id": "scope", "kind": "capability", "ids": ["CAP-one", "CAP-two"]})]
        for document, target in cases:
            with self.subTest(document=document):
                scope = self.freeze(document, target=target)
                with self.assertRaisesRegex(ValueError, "single_capability_target|input_row_not_unique"):
                    reuse.binding(self.prepared, scope)

    def test_original_raw_identity_and_whole_closure_binding_are_independent_of_key(self):
        scope = self.freeze({"capabilities": [self.row]})
        changed = load_json(self.prepared / "b-route-prepared.json")
        changed["inputs"]["evidence"][0]["text"] += " "
        atomic_json(self.prepared / "b-route-prepared.json", changed)
        with self.assertRaisesRegex(ValueError, "original_bytes_changed"):
            reuse.binding(self.prepared, scope)
        scope = self.freeze({"capabilities": [self.row]})
        scope = deepcopy(scope)
        scope["closure"]["entities"] = ["different closure"]
        with self.assertRaisesRegex(ValueError, "single_capability_target"):
            reuse.binding(self.prepared, scope)

    @staticmethod
    def context(value, *, path="shared.json", kind="shared_capability"):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return {"kind": kind, "path": path, "required": True, "format": "json", "absence": None,
            "text": raw.decode("utf-8"), "value": deepcopy(value), "raw_digest": codec.raw_digest(raw),
            "raw_base64": base64.b64encode(raw).decode("ascii")}

    def test_shared_capability_context_outside_source_closure_binds_complete_original_row(self):
        context = self.context({"capabilities": [self.row]})
        scope = self.freeze({}, contexts=[context])
        self.assertNotIn(context["path"], scope["closure"]["source_paths"])
        bound = reuse.binding(self.prepared, scope)
        self.assertEqual(bound["capability"], self.row)
        self.assertEqual(bound["path"], context["path"])
        self.assertEqual(bound["json_pointer"], "/capabilities/0")
        self.assertEqual(bound["raw_digest"], context["raw_digest"])

    def test_complete_root_capability_uses_empty_pointer_and_keeps_unknown_nested_fields(self):
        original = {**deepcopy(self.row), "nested_reference": {"capability_id": "CAP-one"},
            "capabilities": [{"capability_id": "CAP-one", "reference_only": True}]}
        context = self.context(original)
        scope = self.freeze({}, contexts=[context])
        bound = reuse.binding(self.prepared, scope)
        self.assertEqual(bound["capability"], original)
        self.assertEqual(bound["path"], context["path"])
        self.assertEqual(bound["json_pointer"], "")
        self.assertEqual(bound["raw_digest"], context["raw_digest"])
        self.assertEqual(recovery.capability_hash(bound["capability"]), recovery.capability_hash(original))

    def test_newly_supported_complete_original_locations_still_reject_ambiguous_targets(self):
        cases = [(self.row, [self.context({"capabilities": [self.row]})]),
            ({"capabilities": [self.row]}, [self.context(self.row)]),
            ({}, [self.context(self.row), self.context(self.row, path="other.json", kind="capability")])]
        for source, contexts in cases:
            with self.subTest(source=source, paths=[row["path"] for row in contexts]):
                scope = self.freeze(source, contexts=contexts)
                with self.assertRaisesRegex(ValueError, "complete_input_row_not_unique:2"):
                    reuse.binding(self.prepared, scope)


class CompletedCoordinatorTests(unittest.TestCase):
    create = fixtures.RuntimeTests.create
    review = fixtures.RuntimeTests.review

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        inputs = self.fixture.fixture
        self.capability = {"capability_id": "CAP-one", "unknown": {"values": [True, 1], "text": "Keep  original"}}
        inputs.put("reuse/capabilities.json", {"capabilities": [self.capability, {"capability_id": "CAP-other", "value": 1}]})
        inputs.put("reuse/tasks.json", {"master": {"tasks": [{"id": "unrelated", "status": "todo"}]}})
        contract = deepcopy(inputs.contract)
        contract["scope"].update(kind="capability", ids=["CAP-one"])
        contract["contexts"] = [{"kind": kind, "path": path, "format": "json", "required": True, "absence": None}
            for kind, path in (("capability", "reuse/capabilities.json"), ("task", "reuse/tasks.json"))]
        self.contract = contract
        self.prepare("single")

    def prepare(self, name):
        inputs = self.fixture.fixture
        report = inputs.prepare(name, contract=self.contract)
        self.frozen = inputs.frozen(report)
        self.ref = report["resume_ref"]
        self.fixture.prepared, self.fixture.frozen = report, self.frozen
        self.value = self.fixture.envelope()

    def install_reference_catalog(self):
        target = deepcopy(self.capability)
        target["unknown"]["dependency"] = {"exact_original_id": "CAP-related"}
        self.reference_catalog = {"capabilities": [target,
            {"capability_id": "CAP-related", "unknown": {"values": [True, 1]}},
            {"capability_id": "CAP-other", "value": 1}]}
        self.fixture.fixture.put("reuse/capabilities.json", self.reference_catalog)
        self.prepare("with-reference")
        self.assertNotIn("reuse/capabilities.json", self.frozen["inputs"]["closure"]["source_paths"])

    def complete_source(self):
        return fixtures.ReviewFixTests.complete_offline_transport_coordinator(self, "3b-mvg-v1")

    def empty(self, name):
        run, state = self.create("3b-mvg-v1", name)
        scopes = runtime.scopes(state, run / "analysis-input")
        base = runtime.seed(state, run / "analysis-input")
        state["capability_selection"] = {"binding": canonical_sha({"strategy": selection.STRATEGY,
            "scopes": scopes, "seed": base}), "order": [scope["capability_id"] for scope in scopes],
            "selected": [], "checkpoint_head": None, "accepted_sha256": canonical_sha(base), "current": None,
            "calls": [], "total_invocations": 0, "lineage_invocations": {label: 0 for label in runtime.labels(state)}}
        recovery.bind_epoch(self.root, state)
        atomic_json(run / "run.json", state)
        return run, state, scopes[0], base

    def adopt(self, name):
        run, state, scope, base = self.empty(name)
        with patch.object(selection, "generate_append", side_effect=AssertionError("Completed reuse must not generate")):
            selection.generate_selected_capabilities(self.root, run, state, backend="offline-transport",
                invoke_factory=None, selector_factory=None)
        self.assertEqual(state["capability_selection"]["total_invocations"], 0)
        self.assertFalse((run / "candidates").exists())
        self.assertEqual(state["capability_selection"]["selected"][0]["kind"], "adoption")
        return run, state, scope, base

    def test_actual_completed_checkpoint_adopts_across_canonical_and_unrelated_metadata_changes_and_handoff_retry(self):
        _delivery, original, source = self.complete_source()
        source_bytes = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
        original_costs = deepcopy(original["capability_selection"])
        # New complete envelopes differ, but only the original complete target
        # row and relevant governed dependencies determine local eligibility.
        inputs = self.fixture.fixture
        inputs.put("reuse/capabilities.json", {"capabilities": [{"unknown": {"text": "Keep  original", "values": [True, 1]},
            "capability_id": "CAP-one"}, {"capability_id": "CAP-other", "value": 2}]})
        inputs.put("reuse/tasks.json", {"master": {"tasks": [{"id": "unrelated", "status": "done"}]}})
        inputs.put("unrelated-catalog.json", {"HEAD": "unrelated", "entries": ["new"]})
        self.prepare("canonical")
        run, state, _scope, _base = self.adopt("next")
        proof = load_json(self.root / state["selected_admission_review"]["path"])
        execution = load_json(self.root / state["selected_admission_review"]["execution_path"])
        self.assertEqual(execution["total_invocations"], 0)
        self.assertEqual(proof["records"][0]["kind"], "adoption")
        self.assertNotIn("proof", proof["records"][0])
        proposal = load_json(run / "proposal.json")
        self.assertEqual(proposal["provenance"]["kind"], "external")
        handoff = runtime.handoff(self.root, run, state)
        self.assertEqual(handoff["comparisons"][0]["new_model_calls"], 0)
        self.assertEqual(handoff["cost"], "unknown")
        self.assertFalse(handoff["runtime_verified"] or handoff["formal_adoption"])
        actual_write = runtime.atomic_json
        def failed_handoff(path, value):
            if path.name == "handoff.json":
                raise OSError("fixture_downstream_handoff_failure")
            return actual_write(path, value)
        with patch.object(runtime, "atomic_json", side_effect=failed_handoff), self.assertRaisesRegex(OSError, "downstream"):
            runtime.operate(self.root, planner="mvg", command="verify-selection", run_id="next",
                prepared_ref=self.ref, profile="3b-mvg-v1")
        restarted = load_json(run / "run.json")
        with patch.object(selection, "generate_append", side_effect=AssertionError("No upstream rerun")):
            selection.generate_selected_capabilities(self.root, run, restarted, backend="offline-transport",
                invoke_factory=None, selector_factory=None)
        self.assertEqual(restarted["capability_selection"], state["capability_selection"])
        self.assertEqual(load_json(source / "run.json")["capability_selection"], original_costs)
        self.assertEqual(source_bytes, {path: path.read_bytes() for path in source_bytes})

    def test_uncommitted_corrupt_proof_and_related_drift_record_fresh_without_new_calls(self):
        _delivery, original, source = self.complete_source()
        source_state_raw = (source / "run.json").read_bytes()
        try:
            uncommitted = deepcopy(original)
            uncommitted["capability_selection"]["selected"] = []
            atomic_json(source / "run.json", uncommitted)
            run, state, scope, base = self.empty("uncommitted")
            self.assertIsNone(recovery.try_adopt(self.root, run, state, scope, 0, base))
            self.assertIn("not_committed", str(load_json(run / "recovery-lookups/scope-1.json")))
        finally:
            (source / "run.json").write_bytes(source_state_raw)
        selected = original["capability_selection"]["selected"][0]
        proof_path = source / selected["admissions"][selected["selected_candidate"]]["proof_path"]
        original_proof = proof_path.read_bytes()
        try:
            proof_path.write_bytes(original_proof + b" ")
            run, state, scope, base = self.empty("corrupt")
            self.assertIsNone(recovery.try_adopt(self.root, run, state, scope, 0, base))
            self.assertIn("artifact_identity_changed", str(load_json(run / "recovery-lookups/scope-1.json")))
        finally:
            proof_path.write_bytes(original_proof)
        self.fixture.fixture.put("docs/constraint.md", b"Different relevant constraint.\n")
        self.prepare("drift")
        run, state, scope, base = self.empty("drift")
        self.assertIsNone(recovery.try_adopt(self.root, run, state, scope, 0, base))
        self.assertIn("dependencies_incompatible", str(load_json(run / "recovery-lookups/scope-1.json")))
        self.assertEqual(state["capability_selection"]["calls"], [])
        self.assertFalse((run / "adoptions").exists())

    def test_original_reopen_transaction_revokes_adoption_and_keeps_costs_then_clear_keeps_audit_and_formal_files(self):
        _delivery, original, source = self.complete_source()
        reused, adopted, _scope, _base = self.adopt("next")
        before = deepcopy(original["capability_selection"])
        proposal = load_json(source / "proposal.json")
        text = (self.root / "docs/source.md").read_bytes().decode("utf-8")
        report = {"schema_version": audit.REPORT_SCHEMA, "run_id": original["run_id"],
            "analysis_identity_sha256": original["analysis_identity_sha256"],
            "checkpoint_head_sha256": canonical_sha(before["checkpoint_head"]), "proposal_sha256": canonical_sha(proposal),
            "status": "reviewed", "reviewer": "offline-source-owner", "rationale": "Explicit source-bound conflict fixture",
            "conflicts": [{"id": "declared-conflict", "kind": "source_conflict", "severity": "hard",
                "contradiction": "Declared replacement must resolve this source boundary", "capability_ids": ["CAP-one"],
                "flow_ids": ["FLOW"], "source_refs": [{"path": "docs/source.md", "sha256": codec.raw_digest(text.encode("utf-8")),
                    "citations": [{"line": 1, "text": text.splitlines(keepends=True)[0]}]}]}]}
        path = self.fixture.fixture.put("logs/conflict.json", report)
        receipt = audit.operate(self.root, run_id=original["run_id"], operation="audit",
            conflict_report=str(path), conflict_report_sha256=file_sha(path))
        self.assertEqual(receipt["evidence_gaps"], [])
        plan = audit.operate(self.root, run_id=original["run_id"], operation="reopen-plan",
            audit_path=receipt["path"], audit_sha256=receipt["sha256"])
        audit.operate(self.root, run_id=original["run_id"], operation="reopen", plan_path=plan["path"], plan_sha256=plan["sha256"])
        pending = load_json(source / "run.json")
        self.assertEqual(pending["capability_selection"]["selected"], [])
        self.assertEqual(pending["capability_selection"]["calls"], before["calls"])
        self.assertEqual(pending["capability_selection"]["lineage_invocations"], before["lineage_invocations"])
        with self.assertRaisesRegex(ValueError, "source_revoked"):
            recovery.assert_active_chain(self.root, adopted, reused)
        scope = runtime.scopes(pending, source / "analysis-input")[0]
        self.assertIsNotNone(runtime.reopen_directive(pending, self.frozen))
        schema = runtime.review_schema(pending, proposal, self.frozen)
        self.assertIn("reopen_reviews", schema["required"])
        self.assertIsNone(recovery.try_adopt(self.root, source, pending, scope, 0, runtime.seed(pending, source / "analysis-input")))
        published = self.fixture.fixture.put("formal/preserved.json", {"adopted": "formal baseline is separate"})
        original_formal = published.read_bytes()
        audit_bytes = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
        recovery.clear(self.root)
        with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
            recovery.assert_epoch(self.root, pending)
        self.assertEqual(published.read_bytes(), original_formal)
        self.assertEqual(audit_bytes, {path: path.read_bytes() for path in audit_bytes})


    def test_current_wire_completed_reuse_separates_related_drift_and_unrelated_context(self):
        self.install_reference_catalog()
        def current_wire(profile='3b-mvg-v1',run_id='runtime',**_kwargs):
            return fixtures.RuntimeTests.create(self,profile,run_id,complete_wire=True,
                wire_delivery=runtime.wire.CURRENT_SCHEMA)
        self.create=current_wire
        _delivery,state,source=fixtures.ReviewFixTests.complete_offline_transport_coordinator(
            self,'3b-mvg-v1',complete_wire=True)
        original=deepcopy(state)
        changed=deepcopy(self.reference_catalog)
        changed['capabilities'][1]['unknown']['values']=[1,1]
        self.fixture.fixture.put('reuse/capabilities.json',changed)
        self.prepare('current-wire-related')
        target,current,scope,base=self.empty('cw-rel')
        self.assertIsNone(recovery.try_adopt(self.root,target,current,scope,0,base))
        self.assertIn('dependencies_incompatible',str(load_json(target/'recovery-lookups/scope-1.json')))
        self.assertEqual([],current['capability_selection']['calls'])
        changed=deepcopy(self.reference_catalog)
        changed['capabilities'][2]['value']=2
        self.fixture.fixture.put('reuse/capabilities.json',changed)
        self.fixture.fixture.put('reuse/tasks.json',{'master':{'tasks':[{'id':'unrelated','status':'done'}]}})
        self.prepare('current-wire-unrelated')
        self.adopt('cw-unrel')
        self.assertEqual(original,load_json(source/'run.json'))

    def test_current_wire_reopen_replacement_and_historical_reuse_keep_original_receipts(self):
        # Real coordinator and protocol fixture; producer-policy remains the
        # original pre-loop-four fixture, never native/provider qualification.
        self.install_reference_catalog()
        captured={}
        generate=selection.generate_selected_capabilities
        def observed(*args,**kwargs):
            if kwargs.get('invoke_factory') is not None and not captured:
                captured.update(invoke_factory=kwargs['invoke_factory'],selector_factory=kwargs['selector_factory'])
            return generate(*args,**kwargs)
        def current_wire(profile='3b-mvg-v1',run_id='runtime',**_kwargs):
            return fixtures.RuntimeTests.create(self,profile,run_id,complete_wire=True,
                wire_delivery=runtime.wire.CURRENT_SCHEMA)
        self.create=current_wire
        with patch.object(selection,'generate_selected_capabilities',side_effect=observed):
            _delivery,state,run=fixtures.ReviewFixTests.complete_offline_transport_coordinator(
                self,'3b-mvg-v1',complete_wire=True)
        self.assertEqual(runtime.wire_delivery(state),runtime.wire.CURRENT_SCHEMA)
        calls=deepcopy(state['capability_selection']['calls'])
        proposal=load_json(run/'proposal.json')
        raw=(self.root/'docs/source.md').read_bytes()
        report={'schema_version':audit.REPORT_SCHEMA,'run_id':state['run_id'],
            'analysis_identity_sha256':state['analysis_identity_sha256'],
            'checkpoint_head_sha256':canonical_sha(state['capability_selection']['checkpoint_head']),
            'proposal_sha256':canonical_sha(proposal),'status':'reviewed','reviewer':'offline-wire-fixture',
            'rationale':'Bounded wire replacement check','conflicts':[{
                'id':'wire-conflict','kind':'source_conflict','severity':'hard',
                'contradiction':'Resolve the original source boundary','capability_ids':['CAP-one'],
                'flow_ids':['FLOW'],'source_refs':[{'path':'docs/source.md','sha256':codec.raw_digest(raw),
                    'citations':[{'line':1,'text':raw.decode('utf-8').splitlines(keepends=True)[0]}]}]}]}
        path=self.fixture.fixture.put('logs/wire-conflict.json',report)
        receipt=audit.operate(self.root,run_id=state['run_id'],operation='audit',
            conflict_report=str(path),conflict_report_sha256=file_sha(path))
        plan=audit.operate(self.root,run_id=state['run_id'],operation='reopen-plan',
            audit_path=receipt['path'],audit_sha256=receipt['sha256'])
        result=audit.operate(self.root,run_id=state['run_id'],operation='reopen',
            plan_path=plan['path'],plan_sha256=plan['sha256'])
        self.assertEqual(result['status'],'reopened')
        pending=load_json(run/'run.json')
        self.assertEqual(pending['capability_selection']['calls'],calls)
        state.clear();state.update(pending)
        carrier=fixtures.fixture_review_carrier
        def resolved(review,materials):
            directive=materials.get('reopen_context')
            if directive is not None:
                review=deepcopy(review)
                review['reopen_reviews']=[{'conflict_id':cid,'plan_sha256':directive['plan']['sha256'],
                    'verdict':'resolved','rationale':'Explicit synthetic replacement resolution'}
                    for cid in directive['resolution_required_conflict_ids']]
            return carrier(review,materials)
        runner=Path(fixtures.__file__).parent/'fixtures/b_route_bound_protocol_runner.py'
        with patch.dict(os.environ,{'CODEX_HOME':str(self.root/'offline-model-metadata'),
                'SC_KNOWLEDGE_PLANNING_RUNNER':str(runner.resolve()),
                'NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT':'high'}), \
                patch.object(fixtures,'fixture_review_carrier',side_effect=resolved):
            generate(self.root,run,state,backend='offline-transport',**captured)
        self.assertEqual(state['capability_selection']['generation'],2)
        self.assertEqual(state['capability_selection']['calls'][:len(calls)],calls)
        self.assertEqual(len(state['capability_selection']['calls']),2*len(calls))
        proof=load_json(self.root/state['selected_admission_review']['path'])
        directive=runtime.reopen_directive(state,self.frozen)
        self.assertEqual(proof['records'][0]['proof']['reopen_context'],directive)
        self.assertEqual(proof['records'][0]['proof']['review']['reopen_reviews'][0]['verdict'],'resolved')
        selection.verified_prefix(self.root,run,state)
        # A new prepared target may differ in unrelated context while historical
        # dispatches must still bind to their own original generation and input.
        changed=deepcopy(self.reference_catalog)
        changed['capabilities'][1]['unknown']['values']=[1,1]
        self.fixture.fixture.put('reuse/capabilities.json',changed)
        self.prepare('wire-related-drift')
        target,current,scope,base=self.empty('wire-related-next')
        self.assertIsNone(recovery.try_adopt(self.root,target,current,scope,0,base))
        self.assertIn('dependencies_incompatible',str(load_json(target/'recovery-lookups/scope-1.json')))
        self.assertEqual(current['capability_selection']['calls'],[])
        changed=deepcopy(self.reference_catalog)
        changed['capabilities'][2]['value']=2
        self.fixture.fixture.put('reuse/capabilities.json',changed)
        self.fixture.fixture.put('reuse/tasks.json',{'master':{'tasks':[{'id':'unrelated','status':'done'}]}})
        self.prepare('wire-canonical')
        self.adopt('wire-next')

    def test_required_constraint_outside_audit_closure_can_reopen_through_original_transaction(self):
        _delivery, original, source = self.complete_source()
        reference = "docs/constraint.md"
        inputs = self.frozen["inputs"]
        self.assertNotIn(reference, inputs["closure"]["source_paths"])
        self.assertIn(reference, [row["path"] for row in inputs["contract"]["constraints"]])
        self.assertIn(reference, [row["path"] for row in inputs["evidence"]])
        before = deepcopy(original["capability_selection"])
        proposal = load_json(source / "proposal.json")
        raw = (self.root / reference).read_bytes()
        report = {"schema_version": audit.REPORT_SCHEMA, "run_id": original["run_id"],
            "analysis_identity_sha256": original["analysis_identity_sha256"],
            "checkpoint_head_sha256": canonical_sha(before["checkpoint_head"]), "proposal_sha256": canonical_sha(proposal),
            "status": "reviewed", "reviewer": "offline-source-owner", "rationale": "Explicit required-constraint conflict fixture",
            "conflicts": [{"id": "required-constraint", "kind": "source_conflict", "severity": "hard",
                "contradiction": "Declared replacement must resolve the required frozen constraint", "capability_ids": ["CAP-one"],
                "flow_ids": ["FLOW"], "source_refs": [{"path": reference, "sha256": codec.raw_digest(raw),
                    "citations": [{"line": 1, "text": raw.decode("utf-8").splitlines(keepends=True)[0]}]}]}]}
        path = self.fixture.fixture.put("logs/constraint-conflict.json", report)
        receipt = audit.operate(self.root, run_id=original["run_id"], operation="audit",
            conflict_report=str(path), conflict_report_sha256=file_sha(path))
        self.assertEqual(receipt["evidence_gaps"], [])
        self.assertEqual(receipt["hard_conflicts"], report["conflicts"])
        plan = audit.operate(self.root, run_id=original["run_id"], operation="reopen-plan",
            audit_path=receipt["path"], audit_sha256=receipt["sha256"])
        result = audit.operate(self.root, run_id=original["run_id"], operation="reopen",
            plan_path=plan["path"], plan_sha256=plan["sha256"])
        self.assertEqual(result["status"], "reopened")
        pending = load_json(source / "run.json")
        self.assertEqual(pending["capability_selection"]["selected"], [])
        self.assertEqual(pending["capability_selection"]["calls"], before["calls"])
        self.assertEqual(pending["capability_selection"]["lineage_invocations"], before["lineage_invocations"])
        self.assertIn(before["checkpoint_head"]["transaction_id"], recovery.registry(self.root, pending)["revoked"])


class FollowupFrozenOwnerTests(unittest.TestCase):
    """Negative owner rules over synthetic files, without native publication.

    The production Windows initializer has its own IO contract. This fixture
    supplies initial JSON only; historical proof/rule/epoch checks stay live.
    """
    setUp = CompletedCoordinatorTests.setUp
    prepare = CompletedCoordinatorTests.prepare

    def create(self, *args, **kwargs):
        def initial_data(_root, run_dir, state, frozen):
            atomic_json(run_dir / "analysis-input/b-route-prepared.json", frozen)
            atomic_json(run_dir / "run.json", state)
        with patch.object(runtime, "publish_initial_run", side_effect=initial_data):
            return fixtures.RuntimeTests.create(self, *args, **kwargs)

    def test_resigned_runtime_rules_do_not_authorize_historical_read_or_prefix_or_proof(self):
        run, state = self.create()
        changed = deepcopy(state)
        changed["planning_runtime"]["rules"]["runtime"]["_b_route_planning_runtime.py"] = "sha256:" + "0" * 64
        # This descriptor is internally hash-consistent. It still cannot claim
        # that the currently executing verifier implements these old rules.
        changed["runtime_identity"] = canonical_sha(changed["planning_runtime"])
        with self.assertRaisesRegex(ValueError, "input_or_rules_changed"):
            runtime.validate_input(self.root, run, changed, check_originals=False)
        with self.assertRaisesRegex(ValueError, "input_or_rules_changed"):
            selection.verified_prefix(self.root, run, changed, check_originals=False)
        self.assertIn("input_or_rules_changed", str(runtime.proof_errors(self.root, changed, {}, {}, check_originals=False)))

    def test_historical_read_keeps_actual_planning_rules_comparison(self):
        run, state = self.create()
        rules = self.root / "rules.py"
        rules.write_bytes(rules.read_bytes() + b"# Actual fixture planning-rule drift\n")
        with self.assertRaisesRegex(ValueError, "planning_rules_changed"):
            runtime.validate_input(self.root, run, state, check_originals=False)
        with self.assertRaisesRegex(ValueError, "planning_rules_changed"):
            selection.verified_prefix(self.root, run, state, check_originals=False)
        self.assertIn("planning_rules_changed", str(runtime.proof_errors(self.root, state, {}, {}, check_originals=False)))

    def test_historical_prefix_never_disables_persistent_recovery_epoch_check(self):
        run, state = self.create()
        recovery.bind_epoch(self.root, state)
        recovery.clear(self.root)
        with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
            runtime.validate_input(self.root, run, state, check_originals=False)
        with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
            selection.verified_prefix(self.root, run, state, check_originals=False)

    def test_unsupported_old_transition_uses_real_owner_and_never_falls_back_to_current_json(self):
        _run, state = self.create()
        changed = deepcopy(state)
        changed["schema_version"] = runtime.CONTINUATION_RUN
        changed["b_route_execution_transition"] = {"schema_version": "unsupported-old-source"}
        with patch.object(runtime.planning, "load_prepared", side_effect=AssertionError("No same-source fallback")) as fallback:
            with self.assertRaisesRegex(ValueError, "execution_transition_closed_record_required"):
                runtime.frozen_input(self.root, changed, check_originals=False)
        fallback.assert_not_called()

    def test_declared_present_context_uses_frozen_raw_and_citations_without_authorizing_unlisted_evidence(self):
        run, state = self.create()
        reference = "reuse/capabilities.json"
        self.assertNotIn(reference, self.frozen["inputs"]["closure"]["source_paths"])
        raw = (self.root / reference).read_bytes()
        locator = {"path": reference, "sha256": codec.raw_digest(raw),
            "citations": [{"line": 1, "text": raw.decode("utf-8").splitlines(keepends=True)[0]}]}
        audit._source(run, locator, state)
        for field in ("sha256", "citations"):
            changed = deepcopy(locator)
            changed[field] = "sha256:" + "0" * 64 if field == "sha256" else [{"line": 1, "text": "Invented quote\n"}]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "source_not_frozen|citations_changed"):
                audit._source(run, changed, state)
        # A locator-only negative control removes the declaration but leaves
        # its evidence row. The public owner separately validates the envelope.
        envelope = load_json(run / "analysis-input/b-route-prepared.json")
        envelope["inputs"]["contract"]["contexts"] = [row for row in envelope["inputs"]["contract"]["contexts"] if row["path"] != reference]
        atomic_json(run / "analysis-input/b-route-prepared.json", envelope)
        with self.assertRaisesRegex(ValueError, "source_not_frozen"):
            audit._source(run, locator, state)

import _b_route_candidate as candidate
import _b_route_planning_input as planning
import test_b_route_candidate as audit_candidate_fixtures
import test_b_route_records as audit_record_fixtures

# Draft only. Append after the existing classes and before unittest.main()
# in test_b_route_completed_reuse.py. Existing imports are reused.
# Not executed; pure projection controls are not coordinator/native evidence.


class ExplicitContextFormatTests(unittest.TestCase):
    setUp = CompleteInputBindingTests.setUp
    freeze = CompleteInputBindingTests.freeze
    context = staticmethod(CompleteInputBindingTests.context)

    def text_context(self, text):
        raw = text.encode("utf-8")
        return {"kind": "shared_capability", "path": "notes.json", "required": True,
            "format": "text", "absence": None, "text": text,
            "raw_digest": codec.raw_digest(raw), "raw_base64": base64.b64encode(raw).decode("ascii")}

    def test_text_json_never_parses_or_competes_with_unique_source_definition(self):
        for text in ("This is deliberately not JSON.\n", json.dumps({"capabilities": [self.row]})):
            with self.subTest(text=text):
                scope = self.freeze({"capabilities": [self.row]}, contexts=[self.text_context(text)])
                bound = reuse.binding(self.prepared, scope)
                self.assertEqual(bound["path"], "source.json")
                self.assertEqual(bound["capability"], self.row)
                self.assertEqual(bound["json_pointer"], "/capabilities/0")

    def test_json_looking_text_cannot_supply_missing_definition(self):
        scope = self.freeze({}, contexts=[self.text_context(json.dumps(self.row))])
        with self.assertRaisesRegex(ValueError, "complete_input_row_not_unique:0"):
            reuse.binding(self.prepared, scope)

    def test_explicit_json_without_json_suffix_and_undeclared_source_inference_survive(self):
        context = self.context(self.row, path="capability.data")
        scope = self.freeze({}, contexts=[context])
        self.assertEqual(reuse.binding(self.prepared, scope)["path"], "capability.data")
        scope = self.freeze({"capabilities": [self.row]})
        self.assertEqual(reuse.binding(self.prepared, scope)["capability"], self.row)
        scope = self.freeze({"capabilities": [self.row]}, contexts=[self.context(self.row)])
        with self.assertRaisesRegex(ValueError, "complete_input_row_not_unique:2"):
            reuse.binding(self.prepared, scope)


class CompleteCatalogProjectionTests(unittest.TestCase):
    def setUp(self):
        self.path = "docs/capabilities.json"
        self.target = {"capability_id": "CAP-one", "unknown": {"nested": [True, 1, "exact  text"]}}
        self.related = {"capability_id": "CAP-related", "unknown": {"values": [True, 1]}}
        self.other = {"capability_id": "CAP-other", "unknown": {"values": [1, True]}}
        self.catalog = {"capabilities": [self.target, self.related, self.other],
            "unknown_container": {"keep": [False, "1", 1]}}
        self.bound = {"path": self.path, "capability": deepcopy(self.target)}

    def governed(self, catalog):
        # Use the existing closure owner, not a hand-invented closure success.
        catalog = deepcopy(catalog)
        catalog["planning_relations"] = {"schema_version": runtime.planning.RELATIONS,
            "dependency_coverage": "complete", "entities": [
                {"kind": "capability", "id": "CAP-one", "source_paths": [self.path],
                    "source_block_ids": [], "depends_on": [{"kind": "capability", "id": "CAP-related"}]},
                {"kind": "capability", "id": "CAP-related", "source_paths": [self.path],
                    "source_block_ids": [], "depends_on": []},
                {"kind": "capability", "id": "CAP-other", "source_paths": ["docs/unrelated.md"],
                    "source_block_ids": [], "depends_on": []}]}
        raw = json.dumps(catalog).encode("utf-8")
        bundle = {"files": [{"path": self.path, "raw_digest": codec.raw_digest(raw),
            "raw_base64": base64.b64encode(raw).decode("ascii")},
            {"path": "docs/unrelated.md", "raw_digest": codec.raw_digest(b"unrelated\n"),
                "raw_base64": base64.b64encode(b"unrelated\n").decode("ascii")}],
            "ledger": {"blocks": []}}
        closure = runtime.planning.governed_closure(bundle,
            {"scope_id": "scope", "kind": "capability", "ids": ["CAP-one"]})
        self.assertEqual(closure["mode"], "governed_transitive_closure")
        self.assertEqual({row["id"] for row in closure["entities"]}, {"CAP-one", "CAP-related"})
        self.assertEqual(closure["source_paths"], [self.path])
        return catalog, closure

    def projection(self, catalog, closure, content=None):
        original = deepcopy(catalog)
        result = reuse._capability_container(catalog, self.bound, closure, content or {})
        self.assertEqual(catalog, original)
        return result

    def test_governed_related_full_unknown_body_matters_but_proven_outside_sibling_does_not(self):
        catalog, closure = self.governed(self.catalog)
        projected = self.projection(catalog, closure)
        self.assertEqual(projected["capabilities"], [self.target, self.related])
        self.assertEqual(projected["unknown_container"], catalog["unknown_container"])
        changed = deepcopy(catalog)
        changed["capabilities"][1]["unknown"]["values"] = [1, 1]
        self.assertNotEqual(canonical_sha(projected), canonical_sha(self.projection(changed, closure)))
        changed = deepcopy(catalog)
        changed["capabilities"][2]["unknown"]["values"] = ["different", False]
        self.assertEqual(canonical_sha(projected), canonical_sha(self.projection(changed, closure)))
        changed = deepcopy(catalog)
        changed["unknown_container"]["keep"] = [False, 1, "1"]
        self.assertNotEqual(canonical_sha(projected), canonical_sha(self.projection(changed, closure)))

    def test_full_audit_keeps_source_siblings_without_expanding_to_unrelated_context(self):
        closure = {"mode": "full_audit", "source_paths": [self.path], "entities": []}
        self.assertEqual(self.projection(self.catalog, closure)["capabilities"], self.catalog["capabilities"])
        closure["source_paths"] = ["docs/source.md"]
        projected = self.projection(self.catalog, closure)
        self.assertEqual(projected["capabilities"], [self.target])
        changed = deepcopy(self.catalog)
        changed["capabilities"][2]["unknown"]["values"].append("unrelated change")
        self.assertEqual(canonical_sha(projected), canonical_sha(self.projection(changed, closure)))

    def test_target_and_candidate_references_retain_transitive_complete_siblings(self):
        closure = {"mode": "full_audit", "source_paths": ["docs/source.md"], "entities": []}
        catalog = deepcopy(self.catalog)
        catalog["capabilities"][0]["unknown"]["dependency"] = [["CAP-related"]]
        catalog["capabilities"][1]["unknown"]["dependency"] = {"unrecognized": "CAP-other"}
        bound = {"path": self.path, "capability": deepcopy(catalog["capabilities"][0])}
        self.assertEqual(reuse._capability_container(catalog, bound, closure, {})["capabilities"], catalog["capabilities"])
        self.assertEqual(self.projection(self.catalog, closure,
            {"definitions": {"flows": [{"capability_ids": ["CAP-other"]}]}})["capabilities"],
            [self.target, self.other])
        catalog = deepcopy(self.catalog)
        catalog["capabilities"][0]["unknown"]["dependency_map"] = {"CAP-related": {"unrecognized": True}}
        self.assertEqual(self.projection(catalog, closure)["capabilities"], [catalog["capabilities"][0], self.related])

    def test_unknown_rows_duplicate_ids_root_row_and_top_level_array_keep_original_values(self):
        closure = {"mode": "full_audit", "source_paths": ["docs/source.md"], "entities": []}
        catalog = deepcopy(self.catalog)
        catalog["capabilities"] += [{"unknown": [True, 1]}, {"capability_id": "CAP-other", "duplicate": True}]
        projected = self.projection(catalog, closure)
        self.assertEqual(projected["capabilities"], [self.target, self.other,
            {"unknown": [True, 1]}, {"capability_id": "CAP-other", "duplicate": True}])
        root = {**deepcopy(self.target), "capabilities": [deepcopy(self.related)]}
        self.assertEqual(reuse._capability_container(root,
            {"path": self.path, "capability": root}, closure, {}), root)
        catalog, governed = self.governed(self.catalog)
        self.assertEqual(self.projection(catalog["capabilities"], governed), [self.target, self.related])




class BRouteAuditProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = audit_candidate_fixtures.CandidateTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def context(self):
        fixture = self.fixture
        proposal = deepcopy(fixture.value)
        scope = runtime.scope_value(fixture.frozen)
        run = fixture.root / "logs/ci/mvg-planning/projection-only"
        atomic_json(run / "analysis-input/b-route-prepared.json", fixture.frozen)
        step = {"checkpoint": {"transaction_id": "projection-fixture-only"},
            "record": {"scope": scope, "delta": {"candidate": proposal}}}
        state = {"run_id": "projection-only", "input_stage": "3b",
            "analysis_identity_sha256": fixture.frozen["input_identity"],
            "capability_selection": {"order": [scope["capability_id"]], "selected": [step],
                "checkpoint_head": step["checkpoint"], "accepted_sha256": canonical_sha(proposal),
                "total_invocations": 0, "calls": [], "lineage_invocations": {}}}
        return run, state, scope, proposal

    def report(self, state, proposal, *, caps=(), flows=()):
        raw = (self.fixture.root / "docs/source.md").read_bytes()
        return {"schema_version": audit.REPORT_SCHEMA, "run_id": state["run_id"],
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "checkpoint_head_sha256": canonical_sha(state["capability_selection"]["checkpoint_head"]),
            "proposal_sha256": canonical_sha(proposal), "status": "reviewed",
            "reviewer": "offline-projection-test", "rationale": "Explicit source-backed unit declaration",
            "conflicts": [{"id": "declared-conflict", "kind": "source_conflict", "severity": "hard",
                "contradiction": "The retained source boundary requires replacement",
                "capability_ids": list(caps), "flow_ids": list(flows),
                "source_refs": [{"path": "docs/source.md", "sha256": codec.raw_digest(raw),
                    "citations": [{"line": 1, "text": raw.decode("utf-8").splitlines(keepends=True)[0]}]}]}]}

    def test_selected_plan_flow_is_in_conflict_domain_and_affected_scope_but_unselected_history_is_not(self):
        fixture = self.fixture
        fixture.selected_plan()
        current = audit_record_fixtures.plan_path()
        historical = audit_record_fixtures.plan_path(revision=1)
        fixture.dependency_fixture.add_flow(current, "FLOW-SELECTED")
        fixture.dependency_fixture.models[historical] = fixture.dependency_models[historical]
        fixture.dependency_fixture.add_flow(historical, "FLOW-UNSELECTED")
        fixture.freeze_dependencies("effective-flow", out_of_scope=["REQ-p"])
        run, state, scope, proposal = self.context()
        projection = audit._audit_projection(fixture.root, run, proposal)
        self.assertEqual({"FLOW", "FLOW-SELECTED"}, {row["id"] for row in projection["flows"]})
        report = self.report(state, proposal, flows=["FLOW-SELECTED"])
        original = deepcopy(report)
        conflicts = audit.validate_report(run, state, [scope], proposal, report, projection=projection)
        closure = audit.closure(state, proposal, conflicts, projection=projection)
        self.assertEqual([scope["capability_id"]], closure["affected_capability_ids"])
        self.assertEqual(0, closure["earliest_order_index"])
        self.assertEqual({"declared-conflict": 0}, audit.resolution_boundaries(state, proposal, conflicts, projection=projection))
        self.assertEqual(original, report)
        self.assertEqual(original["conflicts"][0]["source_refs"], conflicts[0]["source_refs"])
        outside = self.report(state, proposal, flows=["FLOW-UNSELECTED"])
        with self.assertRaisesRegex(ValueError, "global_conflict_issue_invalid"):
            audit.validate_report(run, state, [scope], proposal, outside, projection=projection)
        # Original citation owner remains decisive after extending the domain.
        changed = deepcopy(report)
        changed["conflicts"][0]["source_refs"][0]["citations"][0]["text"] = "Invented source quote\n"
        with self.assertRaisesRegex(ValueError, "citations_changed"):
            audit.validate_report(run, state, [scope], proposal, changed, projection=projection)

    def test_governed_transitive_capability_and_flow_conflicts_map_to_the_existing_scope(self):
        fixture = self.fixture
        fixture.put("docs/relations.json", {"planning_relations": {
            "schema_version": planning.RELATIONS, "dependency_coverage": "complete", "entities": [
                {"kind": "capability", "id": "CAP-ROOT", "source_paths": ["docs/source.md"],
                    "source_block_ids": ["B1"], "depends_on": [{"kind": "capability", "id": "CAP-DEPENDENCY"}]},
                {"kind": "capability", "id": "CAP-DEPENDENCY", "source_paths": ["docs/source.md"],
                    "source_block_ids": ["B1"], "depends_on": [{"kind": "flow", "id": "FLOW-DEPENDENCY"}]},
                {"kind": "flow", "id": "FLOW-DEPENDENCY", "source_paths": ["docs/source.md"],
                    "source_block_ids": ["B1"], "depends_on": []}]}})
        fixture.fixture.source_paths.append("docs/relations.json")
        fixture.ledger["blocks"].append({"block_id": "B3", "source_path": "docs/relations.json"})
        fixture.manifest["sources"].append({"path": "docs/relations.json"})
        fixture.put("native-manifest.json", fixture.manifest)
        fixture.put("native-ledger.json", fixture.ledger)
        contract = deepcopy(fixture.fixture.contract)
        contract["scope"] = {"scope_id": "scope", "kind": "capability", "ids": ["CAP-ROOT"]}
        fixture.prepared = fixture.fixture.prepare("transitive-projection", contract=contract)
        fixture.frozen = fixture.fixture.frozen(fixture.prepared)
        fixture.value = fixture.envelope()
        self.assertEqual("governed_transitive_closure", fixture.frozen["inputs"]["closure"]["mode"])
        run, state, scope, proposal = self.context()
        projection = audit._audit_projection(fixture.root, run, proposal)
        for caps, flows in ((["CAP-DEPENDENCY"], []), ([], ["FLOW-DEPENDENCY"])):
            with self.subTest(capabilities=caps, flows=flows):
                report = self.report(state, proposal, caps=caps, flows=flows)
                refs = deepcopy(report["conflicts"][0]["source_refs"])
                conflicts = audit.validate_report(run, state, [scope], proposal, report, projection=projection)
                result = audit.closure(state, proposal, conflicts, projection=projection)
                self.assertEqual([scope["capability_id"]], result["affected_capability_ids"])
                self.assertEqual([scope["capability_id"]], result["replacement_order"])
                self.assertEqual({"declared-conflict": 0}, audit.resolution_boundaries(state, proposal, conflicts, projection=projection))
                self.assertEqual(refs, conflicts[0]["source_refs"])
        for caps, flows in ((["CAP-UNSELECTED"], []), ([], ["FLOW-UNSELECTED"])):
            with self.assertRaisesRegex(ValueError, "global_conflict_issue_invalid"):
                audit.validate_report(run, state, [scope], proposal,
                    self.report(state, proposal, caps=caps, flows=flows), projection=projection)

    def test_audit_projects_exact_planned_objects_and_checks_without_runtime_credit(self):
        run, state, scope, proposal = self.context()
        planned = deepcopy(proposal["content"]["implementation_objects"])
        # Existing objects do not become planned work; the current candidate
        # owner requires an exact frozen target reference for this availability.
        existing = deepcopy(planned[0])
        existing.update(id="existing-adapter", availability="existing",
            target_ref=self.fixture.owned("implementation_reference", "docs/constraint.md"))
        proposal["content"]["implementation_objects"].append(existing)
        state["capability_selection"]["accepted_sha256"] = canonical_sha(proposal)
        state["capability_selection"]["selected"][0]["record"]["delta"]["candidate"] = proposal
        # Prefix ownership is an explicit unit seam here, not coordinator proof.
        with patch.object(selection, "verified_prefix", return_value=([scope], proposal, [{}])), \
             patch.object(selection, "verify_published_chain"), \
             patch.object(candidate, "check_owners", wraps=candidate.check_owners) as owners:
            receipt = audit.audit(self.fixture.root, run, state)
        self.assertEqual(1, owners.call_count)
        self.assertEqual(planned, receipt["planned_obligations"]["implementation_objects"])
        self.assertEqual(["type", "compile", "binding", "engine"],
            receipt["planned_obligations"]["implementation_objects"][0]["later_checks"])
        self.assertFalse(receipt["runtime_verified"])
        self.assertEqual([], receipt["planned_obligations"]["tests"])
        self.assertEqual([], receipt["planned_obligations"]["entrypoints"])
        self.assertEqual([], receipt["planned_obligations"]["manual"])
        verified = audit.verified_audit(self.fixture.root, run, state, prefix=([scope], proposal, [{}]))
        self.assertEqual(receipt["planned_obligations"], verified["planned_obligations"])
        self.assertFalse(verified["runtime_verified"])
        receipt_path = run / state["global_audit"]["path"]
        changed = load_json(receipt_path)
        changed["planned_obligations"]["implementation_objects"] = []
        atomic_json(receipt_path, changed)
        state["global_audit"]["sha256"] = file_sha(receipt_path)
        with self.assertRaisesRegex(ValueError, "planned_obligations_changed"):
            audit.verified_audit(self.fixture.root, run, state, prefix=([scope], proposal, [{}]))

    def test_legacy_planned_obligation_projection_keeps_its_existing_shape(self):
        proposal = {"manifest_candidate": {"flows": [], "tests": [
            {"id": "TEST-P", "state": "planned"}, {"id": "TEST-E", "state": "existing"}]},
            "entrypoints": [{"path": "planned.cs", "status": "planned"}, {"path": "existing.cs", "status": "existing"}],
            "manual_obligations": [{"id": "manual", "description": "Retain this original"}]}
        result = audit._audit_projection(None, None, proposal)
        self.assertEqual({"tests": ["TEST-P"], "entrypoints": ["planned.cs"],
            "manual": proposal["manual_obligations"]}, result["planned_obligations"])




class HistoricalReservationModeTests(unittest.TestCase):
    def test_bound_reservation_preserves_historical_mode_and_current_default(self):
        run=Path('mode-only-run').absolute()
        workspace=run/'sandbox'
        output=workspace/'r.json'
        binding={'workspace':str(workspace),'output_path':str(output)}
        row={'run_id':'mode','candidate':None,'capability_id':'scope','phase':'selection',
            'generation':2,'execution':1,'reservation_id':'original-reservation',
            'request_identity':{'workspace':'sandbox','output_path':'sandbox/r.json'},
            'outcome':{'status':'completed'}}
        state={'run_id':'mode','capability_selection':{'calls':[row]}}
        for mode in (None,False,True):
            kwargs={} if mode is None else {'check_originals':mode}
            with self.subTest(mode=mode),patch.object(runtime,'verify_reserved_call',return_value=binding) as checked:
                actual=runtime.verify_bound_reservation(run,state,binding,candidate_slot=None,
                    scope_id='scope',phase='selection',generation=2,execution=1,
                    expected_workspace=workspace,expected_output=output,**kwargs)
                self.assertIs(actual,row)
                checked.assert_called_once_with(run,row,state=state,
                    check_originals=True if mode is None else mode)
        row['outcome']['status']='unknown'
        with patch.object(runtime,'verify_reserved_call') as checked:
            with self.assertRaisesRegex(ValueError,'reserved_identity_changed'):
                runtime.verify_bound_reservation(run,state,binding,candidate_slot=None,
                    scope_id='scope',phase='selection',generation=2,execution=1,
                    expected_workspace=workspace,expected_output=output,check_originals=False)
            checked.assert_not_called()

    def test_selector_forwards_mode_before_any_prompt_or_original_input_read(self):
        class BoundaryReached(Exception):pass
        run=Path('selector-mode-run').absolute()
        for mode in (None,False,True):
            kwargs={} if mode is None else {'check_originals':mode}
            with self.subTest(mode=mode), \
                    patch.object(runtime,'verify_bound_reservation',side_effect=BoundaryReached) as checked:
                with self.assertRaises(BoundaryReached):
                    runtime.verify_selector_reservation(run,{}, {'capability_id':'scope'},0,
                        {'attempt':1,'reservation_id':'original-reservation'},
                        {'execution_binding':{}},run/'comparison',run/'selection.json',**kwargs)
                self.assertEqual(True if mode is None else mode,checked.call_args.kwargs['check_originals'])


if __name__ == "__main__":
    unittest.main()
