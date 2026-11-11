"""Host routing tests with explicit owner spies, no paid/native execution."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import plan_segmented as cli


class SegmentedHostTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sc-")).resolve()
        self.authority = object()
        self.plan = {"run_id": "fresh", "planner": "mvg", "plan_digest": "sha256:" + "1" * 64}
        self.aux = self.root / "logs/ci/mvg-planning/fresh/q/state.json"
        self.aux.parent.mkdir(parents=True)
        self.aux.write_text("{}", encoding="utf-8")
        self.events = []
        self.snapshot = {"completed": [{"node_id": "g", "verified_result": object()}], "blocked": None,
                         "budget": {"campaign_paid_or_unknown": 79, "released": 0}}
        self.session = SimpleNamespace(snapshot=Mock(side_effect=lambda: deepcopy(self.snapshot)),
            resume=Mock(side_effect=lambda: deepcopy(self.snapshot)))
        @contextmanager
        def verified(root, run, plan):
            self.events.append("genuine-owner-current-action")
            yield
        @contextmanager
        def opened(root, *, run_dir, plan, read_only=False):
            self.events.append(("open", read_only))
            yield self.session
        def value(root, name):
            if name.endswith("b/plan.json"):
                return deepcopy(self.plan)
            if name.endswith("q/completion.json"):
                return {"candidate_proof": {"synthetic_data_not_qualification": True}}
            if name == "catalog.json":
                return {"schema_version": "newrouge.b-route-segmented-source-contract.v1"}
            if name.endswith("run.json"):
                return {"capability_selection": {"calls": []}}
            raise ValueError("unexpected_synthetic_read:" + name)
        self.runtime = SimpleNamespace(
            path=lambda root, name, missing=False: root / name,
            role=Mock(), value=Mock(side_effect=value), raw=Mock(return_value=b"{}"),
            ref_for=lambda name, schema, raw: {"path": name, "schema_version": schema, "raw_digest": codec.raw_digest(raw)},
            CATALOG="newrouge.b-route-segmented-source-contract.v1",
            capture_plan_authority=Mock(return_value=self.authority), prepare_run=Mock(return_value={"logical_calls": 0}),
            segmented_run_contract=Mock(return_value={"funding": {"paid_or_unknown_before_run": 79}}),
            verified_run=verified)
        def build(root, authority, *, partition_policy):
            if authority is not self.authority:
                raise ValueError("synthetic_authority_boundary")
            return deepcopy(self.plan)
        self.producer = SimpleNamespace(PARTITIONS=("whole", "audited-components"), build_plan=Mock(side_effect=build))
        self.core = SimpleNamespace(PROTOCOL="newrouge.b-route-segmented-workflow.v1", validate_plan=lambda value: value,
            execute_workflow=Mock(return_value={"native_qualified": False}))
        self.products = SimpleNamespace(verify_proof=Mock(return_value={"new_segmented_candidate_qualified": True,
                                                                         "legacy_native_admission": False}))
        self.journal = SimpleNamespace(open_workflow=opened, inspect_native_history=Mock(return_value={
            "native_reserved_calls": 0, "charged_or_pending_calls": 1,
            "pending_publications": [{"run_id": "fresh", "journal_ref": "synthetic_original_pending_metadata"}]}))
        self.owners = patch.object(cli, "_owners", return_value=(codec, self.products, self.journal,
                                                               self.producer, self.runtime, self.core))
        self.owners.start()
        self.addCleanup(self.owners.stop)

    def args(self, stage, *extra):
        return ["--root", str(self.root), "--planner", "mvg", "--run-id", "fresh", "--stage", stage, *extra]

    def call(self, stage, *extra):
        stream = io.StringIO()
        with redirect_stdout(stream):
            status = cli.main(self.args(stage, *extra))
        return status, json.loads(stream.getvalue())

    def test_plan_uses_actual_capture_and_producer_without_birth_or_dispatch(self):
        code, result = self.call("plan", "--planning-contract", "planning.json")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "plan-declared")
        self.assertEqual(result["logical_calls"], 0)
        self.runtime.capture_plan_authority.assert_called_once()
        self.assertIs(self.producer.build_plan.call_args.args[1], self.authority)
        self.runtime.prepare_run.assert_not_called()
        self.core.execute_workflow.assert_not_called()

    def test_prepare_calls_original_fresh_birth_not_execute(self):
        code, result = self.call("prepare", "--planning-contract", "planning.json")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "segmented-run-prepared")
        kwargs = self.runtime.prepare_run.call_args.kwargs
        self.assertEqual(kwargs["plan"], self.plan)
        self.assertNotIn("authority", kwargs)
        self.core.execute_workflow.assert_not_called()

    def test_execute_only_uses_original_saved_plan(self):
        code, result = self.call("execute")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "segmented-protocol-completed")
        self.assertFalse(result["legacy_native_admission"])
        self.assertTrue(self.runtime.value.call_args.args[1].endswith("b/plan.json"))
        self.core.execute_workflow.assert_called_once()
        self.producer.build_plan.assert_not_called()

    def test_status_is_read_only_and_tokens_are_not_serialized(self):
        code, result = self.call("status")
        self.assertEqual(code, 0)
        self.assertIn(("open", True), self.events)
        self.assertEqual(result["completed_nodes"], ["g"])
        self.assertEqual(result["budget"]["campaign_paid_or_unknown"], 79)
        self.session.resume.assert_not_called()
        self.core.execute_workflow.assert_not_called()

    def test_resume_is_metadata_only_and_never_retry(self):
        self.snapshot["blocked"] = {"reason": "unknown", "may_redispatch": False}
        code, result = self.call("resume-publication")
        self.assertEqual(code, 0)
        self.assertIn(("open", False), self.events)
        self.session.resume.assert_called_once()
        self.assertFalse(result["may_redispatch_unknown"])
        self.core.execute_workflow.assert_not_called()

    def test_status_of_actual_prepared_run_does_not_initialize_workflow(self):
        self.aux.unlink()
        code, result = self.call("status")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "segmented-prepared-status")
        self.runtime.segmented_run_contract.assert_called_once()
        self.assertNotIn(("open", True), self.events)
        self.assertFalse(self.aux.exists())

    def test_resume_without_actual_pending_transaction_does_not_initialize(self):
        self.journal.inspect_native_history.return_value["pending_publications"] = []
        code, result = self.call("resume-publication")
        self.assertEqual(code, 1)
        self.assertIn("exact_pending_metadata_publication_required", result["reason"])
        self.session.resume.assert_not_called()
        self.assertNotIn(("open", False), self.events)

    def test_verify_replays_own_proof_without_native_admission_claim(self):
        code, result = self.call("verify")
        self.assertEqual(code, 0)
        self.products.verify_proof.assert_called_once()
        self.assertEqual(result["status"], "new-segmented-candidate-proof-verified")
        self.assertFalse(result["legacy_native_admission"])
        self.core.execute_workflow.assert_not_called()

    def test_existing_input_override_is_blocked_before_execution(self):
        code, result = self.call("execute", "--planning-contract", "replacement.json")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["automatic_retry"])
        self.core.execute_workflow.assert_not_called()

    def test_unknown_outcome_is_not_retried(self):
        self.core.execute_workflow.side_effect = ValueError("original_request_unknown")
        code, result = self.call("execute")
        self.assertEqual(code, 1)
        self.assertFalse(result["automatic_retry"])
        self.core.execute_workflow.assert_called_once()

    def test_legacy_run_id_rejected_before_owner_read(self):
        args = cli.parser().parse_args(self.args("execute"))
        args.run_id = "m4"
        with patch.object(cli, "_owners", side_effect=AssertionError("must_not_read_legacy")):
            with self.assertRaisesRegex(ValueError, "legacy_run_cannot_opt_in"):
                cli.run(args)

    def test_missing_original_contract_rejected_before_source_capture(self):
        code, result = self.call("plan")
        self.assertEqual(code, 1)
        self.assertIn("original_planning_contract_required", result["reason"])
        self.runtime.capture_plan_authority.assert_not_called()

    def test_parser_has_no_raw_plan_fee_or_claim_override(self):
        for switch in ("--plan-json", "--paid-before", "--claim-id", "--retry", "--reasoning-effort", "--backend"):
            with self.subTest(switch=switch), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.parser().parse_args(self.args("execute", switch, "override"))

    def test_saved_plan_wrong_planner_is_not_routed_to_other_engine(self):
        self.plan["planner"] = "capability"
        code, result = self.call("execute")
        self.assertEqual(code, 1)
        self.assertIn("original_saved_plan_identity", result["reason"])
        self.core.execute_workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
