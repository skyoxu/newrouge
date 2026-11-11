"""Offline completed-closure controls; synthetic transport is not native AC proof.

The integration fixture runs the original coordinator, paid-binding readers,
checkpoint and receipt owners. Only its producer transport/audit are synthetic.
No test invokes a provider or grants formal adoption/runtime eligibility.
"""
from copy import deepcopy
import base64
import json
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
    """Narrow negative owner controls; no fabricated old-source success seam."""
    setUp = CompletedCoordinatorTests.setUp
    prepare = CompletedCoordinatorTests.prepare
    create = fixtures.RuntimeTests.create

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


if __name__ == "__main__":
    unittest.main()
