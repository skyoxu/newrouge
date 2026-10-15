"""Focused source, conflict-scope and malformed-declaration regression tests."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_global_audit as audit
from _planning_skill_common import atomic_json, canonical_sha, file_sha


class GlobalAuditBoundaryTests(unittest.TestCase):
    def test_source_citations_preserve_original_line_endings_and_bom(self):
        for ending in ("\n", "\r\n", "\r"):
            for bom in (b"", b"\xef\xbb\xbf"):
                with self.subTest(ending=repr(ending), bom=bool(bom)), tempfile.TemporaryDirectory() as folder:
                    run = Path(folder)
                    ref = "docs/source.md"
                    path = run / "analysis-input/sources" / ref
                    path.parent.mkdir(parents=True)
                    path.write_bytes(bom + ("Source boundary" + ending + "Second line" + ending).encode("utf-8"))
                    digest = file_sha(path)
                    atomic_json(run / "analysis-input/analysis-index.json", {
                        "files": {"sources/" + ref: digest}, "authority_inputs": {ref: digest}})
                    reference = {"path": ref, "sha256": digest,
                        "citations": [{"line": 1, "text": "Source boundary" + ending}]}
                    audit._source(run, reference)
                    if ending != "\n":
                        reference["citations"][0]["text"] = "Source boundary\n"
                        with self.assertRaisesRegex(ValueError, "citations_changed"):
                            audit._source(run, reference)

    def chain(self):
        order = ["CAP-a", "CAP-b", "CAP-c"]
        steps = [{"checkpoint": {"id": cid}, "record": {"delta": {"flows": flows}}}
                 for cid, flows in zip(order, ([{"id": "shared"}], [], [{"id": "last"}]))]
        state = {"capability_selection": {"order": order, "selected": steps}}
        proposal = {"manifest_candidate": {"flows": [
            {"id": "shared", "capability_refs": ["CAP-b"]},
            {"id": "last", "capability_refs": ["CAP-c"]}]}}
        return state, proposal

    def test_closure_uses_earliest_introduction_and_all_cumulative_successors(self):
        for caps, flows, earliest, resolution in (
                (["CAP-b"], [], 1, 1), ([], ["shared"], 0, 1),
                (["CAP-c"], [], 2, 2), (["CAP-c"], ["shared"], 0, 2)):
            with self.subTest(caps=caps, flows=flows):
                state, proposal = self.chain()
                conflicts = [{"id": "hard-a", "capability_ids": caps, "flow_ids": flows}]
                result = audit.closure(state, proposal, conflicts)
                self.assertEqual(earliest, result["earliest_order_index"])
                self.assertEqual(state["capability_selection"]["order"][earliest:], result["replacement_order"])
                self.assertEqual(state["capability_selection"]["order"][earliest:], result["invalidated_capability_ids"])
                self.assertEqual([step["checkpoint"] for step in state["capability_selection"]["selected"][earliest:]],
                                 result["invalidated_checkpoints"])
                self.assertEqual({"hard-a": resolution}, audit.resolution_boundaries(state, proposal, conflicts))
        state, proposal = self.chain()
        proposal["manifest_candidate"]["flows"][0]["capability_refs"] = ["CAP-a", "CAP-b"]
        conflicts = [{"id": "shared-conflict", "capability_ids": [], "flow_ids": ["shared"]}]
        self.assertEqual(0, audit.closure(state, proposal, conflicts)["earliest_order_index"])
        self.assertEqual({"shared-conflict": 1}, audit.resolution_boundaries(state, proposal, conflicts))

    def context(self):
        return {"generation": 2, "plan": {"path": "reopen-plans/fixture.json", "sha256": "sha256:plan"},
            "conflicts": [{"id": "hard-a"}, {"id": "hard-b"}],
            "replacement_order": ["CAP-a", "CAP-b", "CAP-c"],
            "resolution_boundaries": {"hard-a": 0, "hard-b": 1}}

    def test_future_conflicts_are_transmitted_without_premature_resolution(self):
        original = self.context()
        state = {"capability_selection": {"order": ["CAP-a", "CAP-b", "CAP-c"], "generation": 2},
                 "reopen_contexts": {"2": original}}
        for cid, required in (("CAP-a", ["hard-a"]), ("CAP-b", ["hard-a", "hard-b"]),
                              ("CAP-c", ["hard-a", "hard-b"])):
            with self.subTest(capability=cid):
                directive = audit.reopen_context(state, {"capability_id": cid})
                self.assertEqual(original["conflicts"], directive["conflicts"])
                self.assertEqual(required, directive["resolution_required_conflict_ids"])
                rows = [{"conflict_id": key, "plan_sha256": "sha256:plan", "verdict": "resolved",
                         "rationale": "Resolved at the current cumulative boundary"} for key in required]
                self.assertEqual([], audit.reopen_review_errors(directive, {"reopen_reviews": rows}))
                self.assertTrue(audit.reopen_review_errors(directive, {"reopen_reviews": rows[:-1]}))
        self.assertEqual(original, self.context())

    def test_declaration_text_fields_require_actual_nonempty_strings(self):
        state = {"run_id": "fixture", "analysis_identity_sha256": "sha256:analysis",
                 "capability_selection": {"checkpoint_head": {"id": "checkpoint"}}}
        proposal = {"manifest_candidate": {"flows": [{"id": "flow-a"}]}}
        report = {"schema_version": audit.REPORT_SCHEMA, "run_id": state["run_id"],
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "checkpoint_head_sha256": canonical_sha(state["capability_selection"]["checkpoint_head"]),
            "proposal_sha256": canonical_sha(proposal), "status": "reviewed", "reviewer": "Owner",
            "rationale": "Reviewed original sources", "conflicts": [{"id": "hard-a", "kind": "source_conflict",
                "severity": "hard", "contradiction": "Explicit source contradiction", "capability_ids": ["CAP-a"],
                "flow_ids": ["flow-a"], "source_refs": [{"path": "docs/source.md", "sha256": "sha256:source", "citations": []}]}]}
        scopes = [{"capability_id": "CAP-a"}]
        with patch.object(audit, "_source"):
            self.assertEqual(report["conflicts"], audit.validate_report(Path("."), state, scopes, proposal, report))
            for field in ("reviewer", "rationale", "contradiction"):
                for value in (True, 1, [], {}, "", "  "):
                    with self.subTest(field=field, value=value):
                        changed = deepcopy(report)
                        target = changed["conflicts"][0] if field == "contradiction" else changed
                        target[field] = value
                        with self.assertRaises(ValueError):
                            audit.validate_report(Path("."), state, scopes, proposal, changed)

    def test_malformed_resolution_context_and_nonstring_rationale_fail_closed(self):
        for context in (None, "invalid", [], True, {}, {"generation": 2}):
            with self.subTest(context=context):
                self.assertTrue(audit.reopen_review_errors(context, {"reopen_reviews": []}))
        context = self.context()
        context["resolution_required_conflict_ids"] = ["hard-a"]
        for rationale in (True, 1, [], {}, "", "  "):
            with self.subTest(rationale=rationale):
                self.assertTrue(audit.reopen_review_errors(context, {"reopen_reviews": [
                    {"conflict_id": "hard-a", "plan_sha256": "sha256:plan", "verdict": "resolved", "rationale": rationale}]}))


if __name__ == "__main__":
    unittest.main()
