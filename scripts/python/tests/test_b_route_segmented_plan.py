"""Pure plan composition from explicit synthetic PlanAuthority boundary.

Real manifest bytes, dependency/phase/slot validators and source drift checks;
no original native/3A qualification, paid result, runner or model is fabricated.
Only Root executes after the common source barrier.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_segmented_plan as producer
import _b_route_segmented_workflow as core
import _b_route_segmented_candidates as products


class SyntheticAuthority:
    pass


class SegmentedPlanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sp-")).resolve()
        self.source = self.root / "source.txt"
        self.source.write_bytes(b"First independent rule.\nSecond independent rule.\n")
        self.authority = SyntheticAuthority()
        self.facts = self.make_facts("mvg")
        def verify(root, authority):
            if type(authority) is not SyntheticAuthority or authority is not self.authority:
                raise ValueError("synthetic_boundary_not_original_factory_token")
            return deepcopy(self.facts)
        self.verifier = patch.object(producer.runtime, "verify_plan_authority", side_effect=verify, create=True)
        self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def make_facts(self, planner):
        count = 2 if planner == "capability" else 3
        manifest = core.freeze_manifest(self.root, run_id="fresh", materials=[{
            "material_id": "source", "path": "source.txt", "version": "original", "role": "source",
            "candidate_label": None, "boundaries": [0, 24, len(self.source.read_bytes())]}],
            candidates=[{"label": chr(65 + index), "candidate_id": "business-" + str(index), "material_ids": []}
                        for index in range(count)])
        obligations = [{"obligation_id": "left", "kind": "preservation", "segment_ids": ["source.0"], "dependency_ids": []},
            {"obligation_id": "right", "kind": "requirement", "segment_ids": ["source.1"], "dependency_ids": []}]
        return {"schema_version": producer.AUTHORITY, "run_id": "fresh", "planner": planner,
            "source_input_identity": "sha256:" + "1" * 64,
            "domain": {"manifest": manifest, "dimensions": ["preservation", "order"], "obligations": obligations,
                       "dependency_edges": [], "original_contract": None},
            "funding": {"paid_or_unknown_before_run": 79, "campaign_limit": 290, "released": 0,
                "maximum_native_charges": 211, "subsequent_full_reservation": 0,
                "retained_profile_calls": 13 if planner == "mvg" else 11, "retained_lineage_calls": {}},
            "retained_time": {"total_active_seconds": 100, "lineage_active_seconds": {}},
            "registry_epoch": 0, "source_policy": {"synthetic_boundary": True}, "authority_digest": "sha256:" + "2" * 64}

    def test_mvg_baseline_real_validator_all_targets_and_static_budget(self):
        plan = producer.build_plan(self.root, self.authority)
        self.assertEqual(len(plan["nodes"]), 11)
        self.assertEqual(plan["budget"], {"native_limit": 192, "campaign_limit": 290, "released": 0, "worst_case_calls": 11})
        self.assertNotIn("retained_paid_or_unknown", plan["budget"])
        for label in ("A", "B", "C"):
            slots = [slot for slot in plan["candidate_contract"]["slots"] if slot["candidate_label"] == label]
            self.assertEqual([slot["target"] for slot in slots], list(products.TARGETS))
            self.assertEqual(sum(slot["target"] == "source_identity" for slot in slots), 1)
        self.assertEqual(plan["candidate_contract"]["final_required_slot_ids"], [])
        self.assertEqual(core.validate_plan(plan), plan)

    def test_capability_has_actual_two_candidates_and_eight_nodes(self):
        self.facts = self.make_facts("capability")
        plan = producer.build_plan(self.root, self.authority)
        self.assertEqual(len(plan["manifest"]["candidates"]), 2)
        self.assertEqual(len(plan["nodes"]), 8)
        self.assertEqual(plan["budget"]["native_limit"], 96)

    def test_raw_copied_authority_dictionary_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "not_original_factory"):
            producer.build_plan(self.root, deepcopy(self.facts))

    def test_unaudited_partition_cannot_be_guessed_from_token_sizes(self):
        with self.assertRaisesRegex(ValueError, "audited_partition_owner_required"):
            producer.build_plan(self.root, self.authority, partition_policy="audited-components")

    def test_audited_components_preserve_complete_source_and_slots(self):
        self.facts["domain"]["original_contract"] = {"synthetic_actual_catalog_boundary": True}
        plan = producer.build_plan(self.root, self.authority, partition_policy="audited-components")
        self.assertEqual(len(plan["nodes"]), 21)
        for label in ("A", "B", "C"):
            slots = [slot for slot in plan["candidate_contract"]["slots"] if slot["candidate_label"] == label]
            self.assertEqual(len(slots), 31)
            self.assertEqual(sum(slot["target"] == "source_identity" for slot in slots), 1)
            generated = [node for node in plan["nodes"] if node["phase"] == "generation" and node["candidate_labels"] == [label]]
            self.assertEqual({sid for node in generated for sid in node["segment_ids"]}, {"source.0", "source.1"})

    def test_actual_reverse_dependency_merges_joint_component(self):
        self.facts["domain"]["original_contract"] = {"synthetic_actual_catalog_boundary": True}
        self.facts["domain"]["obligations"][1]["dependency_ids"] = ["left"]
        self.facts["domain"]["dependency_edges"] = [["right", "left"]]
        plan = producer.build_plan(self.root, self.authority, partition_policy="audited-components")
        self.assertEqual(len(plan["nodes"]), 11)
        self.assertEqual(plan["nodes"][0]["obligation_ids"], ["left", "right"])

    def test_missing_original_edge_is_not_filled_by_host_guess(self):
        self.facts["domain"]["obligations"][1]["dependency_ids"] = ["left"]
        with self.assertRaisesRegex(ValueError, "original_complete_edge_denominator"):
            producer.build_plan(self.root, self.authority)

    def test_current_campaign_liability_not_plan_id_controls_budget(self):
        self.facts["funding"]["paid_or_unknown_before_run"] = 280
        self.facts["funding"]["maximum_native_charges"] = 10
        with self.assertRaisesRegex(ValueError, "current_original_budget"):
            producer.build_plan(self.root, self.authority)

    def test_retained_native_profile_cannot_be_reset_by_business_id(self):
        self.facts["funding"]["retained_profile_calls"] = 182
        with self.assertRaisesRegex(ValueError, "current_original_budget"):
            producer.build_plan(self.root, self.authority)

    def test_original_counter_slot_64_retained_across_new_business_ids(self):
        self.facts["funding"]["retained_lineage_calls"]["candidate-1"] = 62
        with self.assertRaisesRegex(ValueError, "original_lineage_budget"):
            producer.build_plan(self.root, self.authority)

    def test_source_bytes_changed_since_actual_manifest_are_rejected(self):
        self.source.write_bytes(b"changed original bytes\n")
        with self.assertRaises(ValueError):
            producer.build_plan(self.root, self.authority)

    def test_fee_drift_during_construction_rejects_declaration(self):
        first, second = deepcopy(self.facts), deepcopy(self.facts)
        second["funding"]["paid_or_unknown_before_run"] += 1
        with patch.object(producer.runtime, "verify_plan_authority", side_effect=[first, second]):
            with self.assertRaisesRegex(ValueError, "authority_changed_during_plan"):
                producer.build_plan(self.root, self.authority)


if __name__ == "__main__":
    unittest.main()
