"""Synthetic host account contracts; never independent model qualification."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_issue_accounts as accounts


def material(branches=None, *, source="source-1", selected=False):
    branches = branches or [{"kind": "failure", "boundary_ids": ["failure-1"],
                             "applicability": "applicable", "rationale": "original branch"}]
    flow = {"id": "flow-1", "proposed_owner_key": "owner-1", "entry_condition": "ready",
            "branches": deepcopy(branches), "parts": [{"kind": "execution", "description": "work"}]}
    proposal = {"content": {"requirements": [{"requirement_id": "R1"}],
                            "definitions": {"flows": [deepcopy(flow)]}}}
    if selected:
        proposal["content"]["definitions"]["flows"] = []
        flow.pop("proposed_owner_key")
    frozen = {"input_identity": "frozen-input"}
    sources = [{"id": source, "ledger_ref": "docs/source.json", "ledger_digest": "source-digest",
                "block_id": "block-1", "original": {"statement": "original frozen source"}}]
    return proposal, frozen, [flow], sources


def review_for(targets, *, source="source-1", rationale="original finding", blocked=None):
    required = [{"id": accounts.digest(target), "target": deepcopy(target), "source_block_ids": [source]}
                for target in targets]
    blocked = set(range(len(required))) if blocked is None else set(blocked)
    checks = [{"id": row["id"], "verdict": "blocked" if index in blocked else "approved",
               "rationale": rationale + " " + str(index), "source_block_ids": [source]}
              for index, row in enumerate(required)]
    review = {"verdict": "blocked" if blocked else "approved", "checks": checks,
              "findings": [row["rationale"] for row in checks if row["verdict"] == "blocked"]}
    return required, review


def branch_targets(flows):
    targets = []
    for flow in flows:
        multiplicity = {}
        for digest, kind in sorted((accounts.digest(row), row["kind"]) for row in flow["branches"]):
            multiplicity[digest] = multiplicity.get(digest, 0) + 1
            targets.append(["flow_branch", flow["id"], kind, digest, multiplicity[digest]])
    return targets


def adapted(values, required, review, *, origin=None):
    proposal, frozen, flows, sources = values
    return accounts.build_accounts(proposal, frozen, review, required, flows, sources, origin=origin)


class IssueAccountsTests(unittest.TestCase):
    def test_finding_prose_is_bound_but_does_not_reset_account(self):
        values = material()
        required, review = review_for([["flow", "flow-1", "entry_condition"]])
        original = adapted(values, required, review)[0]
        changed = deepcopy(review)
        changed["checks"][0]["rationale"] = "A differently worded same obligation finding"
        changed["findings"] = [changed["checks"][0]["rationale"]]
        revised = adapted(values, required, changed)[0]
        self.assertEqual(original["code"], revised["code"])
        self.assertNotEqual(original["review_sha256"], revised["review_sha256"])
        self.assertNotEqual(original["detail"], revised["detail"])

    def test_unique_kind_branch_body_and_obligation_hash_may_change(self):
        before = material()
        required, review = review_for(branch_targets(before[2]))
        original = adapted(before, required, review)[0]
        after = deepcopy(before)
        after[0]["content"]["definitions"]["flows"][0]["branches"][0]["rationale"] = "partly repaired"
        after[2][0]["branches"][0]["rationale"] = "partly repaired"
        new_required, new_review = review_for(branch_targets(after[2]), rationale="same problem, new wording")
        revised = adapted(after, new_required, new_review)[0]
        self.assertEqual(original["code"], revised["code"])
        self.assertNotEqual(original["obligation_id"], revised["obligation_id"])
        self.assertTrue(revised["local_repairable"])

    def test_same_kind_different_boundary_owners_remain_distinct(self):
        branches = [{"kind": "failure", "boundary_ids": ["failure-1"], "rationale": "first"},
                    {"kind": "failure", "boundary_ids": ["failure-2"], "rationale": "second"}]
        values = material(branches)
        required, review = review_for(branch_targets(values[2]))
        issues = adapted(values, required, review)
        self.assertEqual(len({issue["code"] for issue in issues}), 2)
        self.assertTrue(all(issue["local_repairable"] for issue in issues))
        reversed_values = material(list(reversed(branches)))
        again_required, again_review = review_for(branch_targets(reversed_values[2]))
        again = adapted(reversed_values, again_required, again_review)
        self.assertEqual({issue["code"] for issue in issues}, {issue["code"] for issue in again})

    def test_ambiguous_same_kind_same_anchor_keeps_every_blocked_occurrence(self):
        branches = [{"kind": "failure", "boundary_ids": ["failure-1"], "rationale": "first"},
                    {"kind": "failure", "boundary_ids": ["failure-1"], "rationale": "second"}]
        values = material(branches)
        required, review = review_for(branch_targets(values[2]))
        issues = adapted(values, required, review)
        self.assertEqual(len(issues), 2)
        self.assertEqual(len({issue["code"] for issue in issues}), 2)
        self.assertTrue(all(not issue["local_repairable"] for issue in issues))
        self.assertTrue(all(issue["local_owner_path"] is None for issue in issues))

    def test_identical_duplicate_branch_multiplicity_is_not_merged(self):
        branch = {"kind": "failure", "boundary_ids": ["failure-1"], "rationale": "same"}
        values = material([branch, deepcopy(branch)])
        required, review = review_for(branch_targets(values[2]))
        issues = adapted(values, required, review)
        self.assertEqual(len({issue["code"] for issue in issues}), 2)
        self.assertEqual({issue["account_target"][4] for issue in issues}, {1, 2})
        self.assertTrue(all(not issue["local_repairable"] for issue in issues))

    def test_distinct_frozen_source_namespaces_never_share_account(self):
        first = material()
        required, review = review_for([["requirement", "R1", "meaning_and_disposition"]])
        original = adapted(first, required, review)[0]
        second = material(source="source-2")
        second[3][0]["ledger_ref"] = "docs/other-source.json"
        changed_required, changed_review = review_for([["requirement", "R1", "meaning_and_disposition"]], source="source-2")
        revised = adapted(second, changed_required, changed_review)[0]
        self.assertNotEqual(original["code"], revised["code"])

    def test_cumulative_and_selected_flow_have_no_mutable_local_owner(self):
        values = material(selected=True)
        required, review = review_for([["flow", "flow-1", "entry_condition"],
                                       ["cumulative", "frozen-input", "preservation"]])
        issues = adapted(values, required, review)
        self.assertTrue(all(not issue["local_repairable"] for issue in issues))
        self.assertTrue(all(issue["local_owner_path"] is None for issue in issues))

    def test_root_source_requires_actual_local_requirement_or_flow_support(self):
        values = material()
        values[0]["content"]["source_identity"] = {"ledger_ref": {"ref": "docs/source.json#root"}}
        values[0]["content"]["requirements"][0]["source_block_ids"] = ["block-1"]
        required, review = review_for([["source", "source-1", "coverage_and_support"]])
        issue = adapted(values, required, review)[0]
        self.assertTrue(issue["local_repairable"])
        self.assertIsNone(issue["local_owner_path"])
        target, mutable, path = accounts.resolve_target(values[0], values[1], required, values[2], values[3], issue)
        self.assertEqual(target, required[0]["target"])
        self.assertTrue(mutable)
        self.assertIsNone(path)
        values[0]["content"]["source_identity"]["ledger_ref"]["ref"] = "docs/selected.json#root"
        selected_issue = adapted(values, required, review)[0]
        self.assertFalse(selected_issue["local_repairable"])

    def test_origin_preserves_only_the_original_unique_branch_scope(self):
        branches = [{"kind": "failure", "boundary_ids": ["failure-1"], "rationale": "first"},
                    {"kind": "failure", "boundary_ids": ["failure-2"], "rationale": "second"}]
        before = material(branches)
        required, review = review_for(branch_targets(before[2]))
        old_issues = adapted(before, required, review)
        original = next(issue for issue in old_issues if issue["local_owner_path"][-1] == 0)
        after = deepcopy(before)
        for flow in (after[0]["content"]["definitions"]["flows"][0], after[2][0]):
            flow["branches"][0].update(boundary_ids=["replacement-boundary"], rationale="partly repaired")
        new_required, new_review = review_for(branch_targets(after[2]))
        origin = before[0], required, before[2], original
        revised = adapted(after, new_required, new_review, origin=origin)
        inherited = next(issue for issue in revised if issue["local_owner_path"][-1] == 0)
        self.assertEqual(original["code"], inherited["code"])
        self.assertNotEqual(original["obligation_id"], inherited["obligation_id"])
        self.assertEqual(len({issue["code"] for issue in revised}), 2)
        target, mutable, path = accounts.resolve_target(after[0], after[1], new_required, after[2], after[3], inherited)
        self.assertEqual(target, inherited["account_target"])
        self.assertTrue(mutable)
        self.assertEqual(path, inherited["local_owner_path"])

    def test_resolve_target_rejects_self_reported_scope_or_foreign_owner(self):
        values = material()
        required, review = review_for(branch_targets(values[2]))
        issue = adapted(values, required, review)[0]
        scope = deepcopy(issue)
        scope["local_owner_path"][-1] = 5
        with self.assertRaisesRegex(ValueError, "issue_invalid"):
            accounts.resolve_target(values[0], values[1], required, values[2], values[3], scope)
        foreign = deepcopy(issue)
        foreign["account_identity"]["owner"][1] = "foreign-flow"
        foreign["code"] = "semantic_review_account:" + accounts.digest(foreign["account_identity"])
        with self.assertRaisesRegex(ValueError, "owner_changed"):
            accounts.resolve_target(values[0], values[1], required, values[2], values[3], foreign)

    def test_origin_does_not_hide_a_new_same_kind_branch(self):
        before = material()
        required, review = review_for(branch_targets(before[2]))
        original = adapted(before, required, review)[0]
        after = deepcopy(before)
        new = {"kind": "failure", "boundary_ids": ["new-failure"], "rationale": "new problem"}
        for flow in (after[0]["content"]["definitions"]["flows"][0], after[2][0]):
            flow["branches"].append(deepcopy(new))
        new_required, new_review = review_for(branch_targets(after[2]))
        revised = adapted(after, new_required, new_review, origin=(before[0], required, before[2], original))
        self.assertEqual(len({issue["code"] for issue in revised}), 2)
        self.assertTrue(all(issue["code"] != original["code"] for issue in revised))

    def test_origin_identity_tamper_is_rejected(self):
        values = material()
        required, review = review_for(branch_targets(values[2]))
        original = adapted(values, required, review)[0]
        original["account_identity"]["input_identity"] = "another-input"
        with self.assertRaisesRegex(ValueError, "origin_invalid"):
            adapted(values, required, review, origin=(values[0], required, values[2], original))

    def test_complete_obligation_denominator_is_still_required(self):
        values = material()
        required, review = review_for([["flow", "flow-1", "entry_condition"], ["flow", "flow-1", "graph"]])
        review["checks"].pop()
        with self.assertRaisesRegex(ValueError, "review_domain_invalid"):
            adapted(values, required, review)

    def test_wrong_source_or_unknown_policy_is_rejected(self):
        values = material()
        required, review = review_for([["flow", "flow-1", "entry_condition"]])
        wrong = deepcopy(review)
        wrong["checks"][0]["source_block_ids"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "review_source_invalid"):
            adapted(values, required, wrong)
        with self.assertRaisesRegex(ValueError, "policy_invalid"):
            accounts.build_accounts(values[0], values[1], review, required, values[2], values[3], policy="unknown")


if __name__ == "__main__":
    unittest.main()
