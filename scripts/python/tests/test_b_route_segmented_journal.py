"""Synthetic filesystem/fee fault tests; no model or native qualification.

The unavailable born, renderer and protocol factories are explicitly replaced
at their owner boundary. Original byte locks, apply journal, permanent claims,
registry head updater and run ledger are exercised, never mocked as paid proof.
Only Root executes this module after the shared source barrier.
"""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_segmented_journal as journal
import _b_route_segmented_runtime as runtime


class Prefix:
    def __init__(self, values=None):
        self.values = values or {}


class Result:
    def __init__(self, value):
        self.value = value


class SyntheticBoundary:
    """Explicitly not a native/runtime/model producer."""
    DependencyUnavailable = RuntimeError

    def __init__(self, fixture):
        self.fixture = fixture
        self.replays = 0
        self.independence_checks = 0

    def validate_plan(self, value):
        return deepcopy(value)

    def require_segmented_run(self, root, run, state, plan):
        return deepcopy(self.fixture.witness)

    def verify_completed_prefix(self, root, plan, token):
        journal.require(type(token) is Prefix, "synthetic_prefix_boundary")
        return deepcopy(token.values)

    def validate_request_identity(self, root, plan, node, value, workspace, witness, *, rendered_request, completed_prefix):
        journal.require(rendered_request is self.fixture.rendered, "synthetic_renderer_boundary")
        self.verify_completed_prefix(root, plan, completed_prefix)
        return deepcopy(value)

    def capture_completed_prefix(self, root, plan, values):
        return Prefix({key: value.value for key, value in values.items()})

    def replay_verified_result(self, root, plan, node, reservation, stored):
        self.replays += 1
        return Result(deepcopy(stored))

    def validate_verified_result(self, plan, node, reservation, token):
        journal.require(type(token) is Result and token.value["reservation"] == reservation,
                        "synthetic_protocol_boundary")
        return deepcopy(token.value)

    def validate_result_independence(self, root, run, plan, prefix, token):
        self.verify_completed_prefix(root, plan, prefix)
        journal.require(type(token) is Result, "synthetic_independence_boundary")
        self.independence_checks += 1

    def verify_manifest(self, root, manifest):
        return None

    def validate_completion(self, root, plan, token):
        journal.require(type(token) is Result, "synthetic_completion_boundary")
        return deepcopy(token.value)


class SegmentedJournalTests(unittest.TestCase):
    def setUp(self):
        # Each test owns an isolated short TEMP root; artifacts remain for audit.
        self.root = Path(tempfile.mkdtemp(prefix="sj-" )).resolve()
        self.run = self.root / "logs/ci/mvg-planning/s"
        self.store = self.root / "logs/ci/mvg-recovery"
        self.run.mkdir(parents=True)
        self.store.mkdir(parents=True)
        self.plan = {"protocol": "newrouge.b-route-segmented-workflow.v1", "plan_digest": "sha256:" + "1" * 64,
            "run_id": "s", "planner": "mvg", "manifest": {}, "nodes": [
                {"node_id": "g", "phase": "generation", "ordinal": 0, "candidate_labels": ["a", "b"], "dependencies": []},
                {"node_id": "s", "phase": "selection", "ordinal": 1, "candidate_labels": ["a", "b"], "dependencies": ["g"]}],
            "budget": {"native_limit": 192, "campaign_limit": 290, "released": 0, "worst_case_calls": 2}}
        self.funding = {"paid_or_unknown_before_run": 79, "campaign_limit": 290, "subsequent_full_reservation": 0,
            "maximum_native_charges": 179, "released": 0, "retained_profile_calls": 13, "retained_lineage_calls": {}}
        self.state = {"run_id": "s", "recovery": {"store": str(self.store), "epoch": 0},
            "mvg.run_invocation_limit": 192, "b_route_campaign_funding": deepcopy(self.funding),
            "active_elapsed_seconds": 0, "capability_selection": {"calls": [], "total_invocations": 0,
                "lineage_invocations": {"ca": 0, "cb": 0}, "selected": []}}
        born = {"schema_version": "newrouge.b-route-segmented-born.v1", "run_id": "s"}
        self.write(self.run / "b/born.json", born)
        born_ref = {"path": self.rel(self.run / "b/born.json"), "schema_version": born["schema_version"],
                    "raw_digest": journal.file_sha(self.run / "b/born.json")}
        self.witness = {"registry_store": str(self.store), "registry_epoch": 0, "born_ref": born_ref,
            "run_path": self.rel(self.run / "run.json"), "plan_digest": self.plan["plan_digest"], "native_limit": 192,
            "candidate_lineages": {"a": "ca", "b": "cb"}, "funding": deepcopy(self.funding),
            "runtime_identity": {"reasoning_effort": "high"}}
        self.write(self.run / "run.json", self.state)
        self.write(self.store / "registry.json", {"schema_version": journal.recovery.SCHEMA, "epoch": 0,
            "entries": [], "revoked": [], "segmented_runs": {"schema_version": runtime.INDEX, "campaign": "story25",
                "runs": [{"run_path": self.rel(self.run / "run.json"), "born_ref": born_ref, "planner": "mvg", "epoch": 0,
                    "head": {"journal_ref": "logs/ci/mvg-recovery/activity/segmented-journals/" + "0" * 24 + "-000-born.json",
                        "claim_ref": self.rel(self.run / "b/claim.json"), "claim_raw_digest": "sha256:" + "2" * 64,
                        "native_run_after_digest": journal.file_sha(self.run / "run.json")}}]}})
        self.rendered = object()
        self.boundary = SyntheticBoundary(self)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(journal, "_core", return_value=self.boundary))
        self.stack.enter_context(patch.object(runtime, "request_timeout", return_value=10, create=True))
        self.addCleanup(self.stack.close)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(journal._json_bytes(value))

    def read(self, path):
        return journal._read(self.root, path)

    def rel(self, path):
        return path.relative_to(self.root).as_posix()

    def open(self, **kwargs):
        return journal.open_workflow(self.root, run_dir=self.run, plan=self.plan, **kwargs)

    def identity(self, node):
        value = {key: {} for key in journal._REQUEST_FIELDS}
        archive_path = self.run / "q" / ("n" + str(node["ordinal"])) / "input-archive.json"
        if not archive_path.exists():
            self.write(archive_path, {"synthetic_renderer_archive_boundary": True})
        value.update(protocol=self.plan["protocol"], request_sha256="sha256:" + "3" * 64,
            plan_digest=self.plan["plan_digest"], node_id=node["node_id"], phase=node["phase"], timeout_sec=10,
            input_archive_ref={"path": self.rel(archive_path), "schema_version": "newrouge.b-route-segmented-input-archive.v1",
                               "raw_digest": journal.file_sha(archive_path)})
        return value

    def reserve(self, session, index=0, prefix=None):
        node = self.plan["nodes"][index]
        return session.reserve(node, self.identity(node), rendered_request=self.rendered, completed_prefix=prefix or Prefix())

    def result(self, reservation):
        return Result({"reservation": deepcopy(reservation), "result_digest": "sha256:" + "4" * 64,
            "binding": {"output_sha256": "sha256:" + "5" * 64, "host_execution": {"active_elapsed_seconds": 2}}})

    def test_dynamic_campaign_79_and_profile_13_are_retained(self):
        value = journal._ledger_budget(self.state, self.plan, self.witness)
        self.assertEqual(value["campaign_paid_or_unknown"], 79)
        self.assertEqual(value["remaining_reservable_calls"], 179)
        self.witness["funding"]["retained_profile_calls"] = 191
        with self.assertRaisesRegex(ValueError, "cannot_fund_complete"):
            with self.open():
                pass

    def test_unknown_reservation_is_charged_once_and_head_is_original_registry(self):
        with self.open() as session:
            reservation = self.reserve(session)
            with self.assertRaises(ValueError):
                self.reserve(session)
            self.assertFalse(session.snapshot()["blocked"]["may_redispatch"])
        state = self.read(self.run / "run.json")
        self.assertEqual(state["capability_selection"]["total_invocations"], 1)
        self.assertEqual(state["capability_selection"]["lineage_invocations"], {"ca": 1, "cb": 1})
        head = self.read(self.store / "registry.json")["segmented_runs"]["runs"][0]["head"]
        self.assertEqual(head["native_run_after_digest"], journal.file_sha(self.run / "run.json"))
        self.assertEqual(head["claim_raw_digest"], journal.file_sha(self.root / head["claim_ref"]))
        self.assertEqual(reservation["lineage_ids"], ["ca", "cb"])

    def test_failure_keeps_unknown_and_never_refunds(self):
        with self.open() as session:
            reservation = self.reserve(session)
            failed = session.fail(reservation, {"reason": "synthetic_known_transport_error"})
            self.assertEqual(failed["outcome"], "unknown")
            self.assertEqual(failed["released"], 0)
            with self.assertRaises(ValueError):
                self.reserve(session)
        self.assertNotIn("outcome", self.read(self.run / "run.json")["capability_selection"]["calls"][0])

    def test_partial_reserve_rolls_forward_metadata_without_dispatch(self):
        original = journal._original_writer
        def writer(root, target, value):
            if target == self.run / "run.json":
                raise OSError("synthetic_native_replace_interruption")
            original(root, target, value)
        with self.open() as session:
            with patch.object(journal, "_original_writer", side_effect=writer):
                with self.assertRaises(OSError):
                    self.reserve(session)
        state = self.read(self.run / "run.json")
        history = journal.inspect_native_history(self.root, self.run, state)
        self.assertEqual(history["native_reserved_calls"], 0)
        self.assertEqual(history["charged_or_pending_calls"], 1)
        with self.open() as session:
            self.assertIsNotNone(session.snapshot()["blocked"])
            self.assertIsNotNone(session.resume()["blocked"])
            with self.assertRaises(ValueError):
                self.reserve(session)
        self.assertEqual(len(self.read(self.run / "run.json")["capability_selection"]["calls"]), 1)

    def test_partially_written_permanent_claim_stays_blocked_and_charged(self):
        original = journal._original_writer
        def writer(root, target, value):
            if target.name == "claim.json":
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(journal._json_bytes(value)[:13])
                raise OSError("synthetic_partial_exclusive_claim")
            original(root, target, value)
        with self.open() as session:
            with patch.object(journal, "_original_writer", side_effect=writer):
                with self.assertRaises(OSError):
                    self.reserve(session)
        history = journal.inspect_native_history(self.root, self.run, self.read(self.run / "run.json"))
        self.assertEqual(history["charged_or_pending_calls"], 1)
        with self.open() as session:
            with self.assertRaisesRegex(ValueError, "target drift"):
                session.resume()
            self.assertIsNotNone(session.snapshot()["blocked"])

    def test_claim_tamper_blocks_completion(self):
        with self.open() as session:
            reservation = self.reserve(session)
            path = self.run / "q/n0/claim.json"
            value = self.read(path)
            value["reservation"]["timeout_sec"] = 9
            self.write(path, value)
            with self.assertRaisesRegex(ValueError, "permanent_claim_changed"):
                session.complete(reservation, self.result(reservation))

    def test_partial_complete_keeps_paid_outcome_and_resumes_without_replay(self):
        original = journal._original_writer
        def writer(root, target, value):
            if target == self.run / "q/state.json":
                raise OSError("synthetic_completed_aux_interruption")
            original(root, target, value)
        with self.open() as session:
            reservation = self.reserve(session)
            with patch.object(journal, "_original_writer", side_effect=writer):
                with self.assertRaises(OSError):
                    session.complete(reservation, self.result(reservation))
        state = self.read(self.run / "run.json")
        self.assertEqual(state["capability_selection"]["calls"][0]["outcome"]["status"], "completed")
        history = journal.inspect_native_history(self.root, self.run, state)
        self.assertEqual(history["pending_native_views"][0]["actual_relation"], "after")
        self.assertEqual(history["charged_or_pending_calls"], 1)
        with self.assertRaisesRegex(ValueError, "read_only_pending"):
            with self.open(read_only=True):
                pass
        with self.open() as session:
            snapshot = session.resume()
            self.assertEqual(len(snapshot["completed"]), 1)
            self.assertIsNone(snapshot["blocked"])
        self.assertEqual(len(self.read(self.run / "run.json")["capability_selection"]["calls"]), 1)

    def test_completion_has_independent_claim_and_semantic_parent_digest(self):
        with self.open() as session:
            first = self.reserve(session)
            session.complete(first, self.result(first))
            snapshot = session.snapshot()
            self.assertEqual(self.boundary.independence_checks, 1)
            self.assertIsInstance(snapshot["completed"][0]["verified_result"], Result)
            prefix = Prefix({"g": snapshot["completed"][0]["result"]})
            second = self.reserve(session, 1, prefix)
            self.assertEqual(second["lineage_ids"], [])
            self.assertEqual(self.read(self.run / "q/n1/claim.json")["parents"], {"g": "sha256:" + "4" * 64})
        history = journal.inspect_native_history(self.root, self.run, self.read(self.run / "run.json"))
        self.assertEqual(len(history["completions"]), 1)
        self.assertEqual(history["native_reserved_calls"], 2)

    def test_fabricated_prefix_and_renderer_rejected_before_charge(self):
        with self.open() as session:
            with self.assertRaisesRegex(ValueError, "prefix_boundary"):
                session.reserve(self.plan["nodes"][0], self.identity(self.plan["nodes"][0]),
                                rendered_request=self.rendered, completed_prefix={})
            with self.assertRaisesRegex(ValueError, "renderer_boundary"):
                session.reserve(self.plan["nodes"][0], self.identity(self.plan["nodes"][0]),
                                rendered_request={}, completed_prefix=Prefix())
        self.assertEqual(self.read(self.run / "run.json")["capability_selection"]["calls"], [])

    def test_missing_input_archive_identity_rejected_before_charge(self):
        with self.open() as session:
            value = self.identity(self.plan["nodes"][0])
            del value["input_archive_ref"]
            with self.assertRaisesRegex(ValueError, "actual_request_identity_shape"):
                session.reserve(self.plan["nodes"][0], value, rendered_request=self.rendered, completed_prefix=Prefix())
            value = self.identity(self.plan["nodes"][0])
            value["input_archive_ref"]["raw_digest"] = "sha256:" + "f" * 64
            with self.assertRaisesRegex(ValueError, "original_input_archive_reference"):
                session.reserve(self.plan["nodes"][0], value, rendered_request=self.rendered, completed_prefix=Prefix())
        self.assertEqual(self.read(self.run / "run.json")["capability_selection"]["calls"], [])

    def test_paid_metadata_view_uses_actual_claim_row_and_auxiliary(self):
        with self.open() as session:
            reservation = self.reserve(session)
            with patch.dict(os.environ, {"SC_MVG_RECOVERY_ROOT": str(self.root / "unrelated-env-store")}):
                observed = journal.inspect_reservation_metadata(self.root, self.run, plan=self.plan,
                    node=self.plan["nodes"][0], reservation=reservation)
            self.assertEqual(observed["original_reservation"], reservation)
            self.assertEqual(observed["workspace"], str(self.run / "q/n0/m"))
            self.assertEqual(observed["aux_node"]["status"], "unknown")
            forged = deepcopy(reservation)
            forged["request_identity"]["request_sha256"] = "sha256:" + "f" * 64
            with self.assertRaisesRegex(ValueError, "paid_original_reservation_required"):
                journal.inspect_reservation_metadata(self.root, self.run, plan=self.plan,
                    node=self.plan["nodes"][0], reservation=forged)
            session.complete(reservation, self.result(reservation))
            actual = journal.inspect_reservation_metadata(self.root, self.run, plan=self.plan,
                node=self.plan["nodes"][0], reservation=reservation)
            self.assertEqual(actual["actual_row"]["outcome"]["status"], "completed")

    def test_paid_metadata_cannot_promote_auxiliary_boolean_to_completed(self):
        with self.open() as session:
            reservation = self.reserve(session)
            path = self.run / "q/state.json"
            auxiliary = self.read(path)
            auxiliary["nodes"]["g"].update(status="completed", result_digest="sha256:" + "4" * 64)
            self.write(path, auxiliary)
            with self.assertRaisesRegex(ValueError, "paid_completed_auxiliary_not_native"):
                journal.inspect_reservation_metadata(self.root, self.run, plan=self.plan,
                    node=self.plan["nodes"][0], reservation=reservation)

    def test_zero_based_node_exact_and_final_workspace_absent(self):
        with self.open() as session:
            workspace = session.workspace(self.plan["nodes"][0])
            self.assertTrue(workspace.parent.is_dir())
            self.assertFalse(workspace.exists())
            bad = deepcopy(self.plan["nodes"][0]); bad["ordinal"] = True
            with self.assertRaises(ValueError):
                session.workspace(bad)

    def test_retained_lineage_and_future_shared_reviews_cannot_reset_64(self):
        self.witness["funding"]["retained_lineage_calls"] = {"ca": 64}
        with self.assertRaisesRegex(ValueError, "cannot_fund_original_lineage"):
            journal._ledger_budget(self.state, self.plan, self.witness)

    def test_original_operation_mutex_blocks_second_session(self):
        with self.open():
            with self.assertRaises(ValueError):
                with self.open():
                    self.fail("second original operation lock unexpectedly acquired")

    def test_read_only_existing_snapshot_no_writes_and_no_mutator(self):
        with self.open():
            pass
        before = {self.rel(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.open(read_only=True) as session:
            self.assertEqual(session.snapshot()["completed"], [])
            with self.assertRaisesRegex(ValueError, "read_only_session"):
                session.workspace(self.plan["nodes"][0])
            with self.assertRaisesRegex(ValueError, "read_only_session"):
                session.resume()
        after = {self.rel(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_read_only_never_initializes_auxiliary(self):
        with self.assertRaisesRegex(ValueError, "existing_workflow_required"):
            with self.open(read_only=True):
                pass
        self.assertFalse((self.run / "q").exists())

    def test_unavailable_born_boundary_has_zero_writes(self):
        before = {self.rel(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(self.boundary, "require_segmented_run", side_effect=RuntimeError("unsupported_old_run")):
            with self.assertRaisesRegex(RuntimeError, "unsupported_old_run"):
                with self.open():
                    pass
        self.assertEqual(before, {self.rel(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_unknown_shared_journal_member_is_not_ignored(self):
        with self.open() as session:
            session.journals.joinpath("unknown.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown_shared_publication"):
                self.reserve(session)

    def test_native_row_rollback_rejected_by_original_journal(self):
        with self.open() as session:
            self.reserve(session)
        self.write(self.run / "run.json", self.state)
        with self.assertRaisesRegex(ValueError, "paid_prefix_rollback"):
            journal.inspect_native_history(self.root, self.run, self.state)

    def test_finalize_is_auxiliary_only_and_immutable(self):
        with self.open() as session:
            first = self.reserve(session)
            session.complete(first, self.result(first))
            first_result = session.snapshot()["completed"][0]["result"]
            second = self.reserve(session, 1, Prefix({"g": first_result}))
            session.complete(second, self.result(second))
            completion = Result({"results": [{"node_id": node["node_id"], "result_digest": "sha256:" + "4" * 64}
                                             for node in self.plan["nodes"]], "native_qualified": False})
            original = (self.run / "run.json").read_bytes()
            result = session.finalize(completion)
            self.assertEqual(result["model_calls"], 0)
            self.assertEqual(result, session.finalize(completion))
            self.assertEqual(original, (self.run / "run.json").read_bytes())
            completion.value["native_qualified"] = True
            with self.assertRaisesRegex(ValueError, "never_replaced"):
                session.finalize(completion)


if __name__ == "__main__":
    unittest.main()
