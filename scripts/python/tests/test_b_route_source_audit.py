"""Synthetic orchestration contracts; these tests do not prove model semantics."""
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import concurrent.futures
import base64
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_source_audit as audit
import _b_route_sources as sources
import _b_route_codec as codec
from test_b_route_sources import SourceAccountingTests


class SourceAuditTests(SourceAccountingTests):
    # Inherit fixture helpers only; inherited Story 2.1 methods run in their own suite.
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).parent / "fixtures/b_route_audit_synthetic_runner.py"
        self.fixture = fixture.read_text(encoding="utf-8")
        self.runner = "runner.py"
        self.put(self.runner, self.fixture.encode("utf-8"))

    def mode(self, value):
        self.put(self.runner, self.fixture.replace('MODE = "clean"', 'MODE = ' + repr(value)).encode("utf-8"))

    def accounted(self, attempt="base", disposition=None):
        prepared = self.prepare(attempt)
        self.candidate(prepared, disposition=disposition)
        code, report = self.account(prepared, attempt)
        self.assertEqual(code, 1 if disposition == "unresolved" else 0, report)
        return report, prepared

    def audit(self, report, attempt="audit", extras=(), **kwargs):
        return self.invoke("audit", attempt, ["--accounted", report["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", *extras], **kwargs)

    def verify(self, report, attempt="verify", extras=(), **kwargs):
        return self.invoke("verify", attempt, ["--audit-ref", report["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", *extras], **kwargs)

    def test_complete_zero_task_os_lifecycle_verify_and_exact_replay(self):
        account, _ = self.accounted()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        self.assertFalse(report["planning_eligible"], "Synthetic evidence cannot grant real planning eligibility")
        self.assertEqual(report["evidence_class"], "synthetic")
        self.assertEqual(report["runner_dispatch_count"], 2)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertEqual(report["synthetic_dispatch_count"], 2)
        self.assertFalse((self.root / ".taskmaster").exists())
        for path, raw in before.items():
            self.assertEqual((self.root / path).read_bytes(), raw)
        code, verified = self.verify(report)
        self.assertEqual(code, 0, verified)
        self.assertEqual(verified["runner_dispatch_count"], 0)
        code, replay = self.audit(account)
        self.assertEqual(code, 0, replay)
        self.assertEqual(report, replay)

    def test_complete_reuse_zero_dispatch_and_unrelated_state(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put(".taskmaster/tasks/tasks.json", {"irrelevant": "status change"})
        self.put("unrelated-head.txt", b"Unrelated HEAD provenance.\n")
        code, reused = self.audit(account, "reused", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertEqual(reused["reuse_reason"], "complete_identity_and_original_proof_match")
        code, verified = self.verify(reused)
        self.assertEqual(code, 0, verified)

    def test_os_runner_workspace_drift_blocks_fresh_completion_with_verify_reuse_control(self):
        account, _ = self.accounted()
        marker = "SYNTHETIC_WORKSPACE_DRIFT"
        hook = "    output = execute(request)"
        self.assertEqual(self.fixture.count(hook), 1)
        mutations = {
            "input": ('    (workspace / "input.json").write_bytes(b\'{"SYNTHETIC_WORKSPACE_DRIFT":true}\\n\')\n', "input.json", 1),
            "schema": ('    changed = json.loads((workspace / "schema.json").read_bytes())\n'
                       '    changed["description"] = "SYNTHETIC_WORKSPACE_DRIFT"\n'
                       '    (workspace / "schema.json").write_bytes(json.dumps(changed).encode("utf-8"))\n', "schema.json", 1),
            "prompt": ('    target = workspace / "prompt.txt"\n'
                       '    target.write_bytes(target.read_bytes() + b"SYNTHETIC_WORKSPACE_DRIFT")\n', "prompt.txt", 1),
            "earlier-step": ('    if request["phase"] == "compare":\n'
                             '        target = workspace.parents[1] / "extract-000001/workspace/input.json"\n'
                             '        target.write_bytes(b\'{"SYNTHETIC_WORKSPACE_DRIFT":true}\\n\')\n', "input.json", 2),
        }
        for mutation, (injected, filename, dispatches) in mutations.items():
            with self.subTest(mutation=mutation):
                self.put(self.runner, self.fixture.replace(hook, injected + hook).encode("utf-8"))
                run = "workspace-" + mutation
                code, blocked = self.audit(account, run=run)
                self.assertEqual(code, 1, blocked)
                self.assertFalse(blocked["execution_complete"])
                self.assertFalse(blocked["planning_eligible"])
                self.assertEqual(blocked["runner_dispatch_count"], dispatches)
                self.assertEqual(blocked["synthetic_dispatch_count"], dispatches)
                self.assertEqual(blocked["model_dispatch_count"], 0)
                prefix = blocked["output_ref"]
                changed = "steps/extract-000001/workspace/" + filename
                event = self.json(prefix + "/event.json")
                raw = (self.root / prefix / changed).read_bytes()
                self.assertIn(marker.encode(), raw)
                self.assertEqual(event["artifacts"][changed], codec.raw_digest(raw))
                self.assertNotEqual(event["observations"][prefix + "/" + changed], codec.raw_digest(raw))
                self.assertNotIn(marker.encode(), (self.root / prefix / "steps/extract-000001/request.txt").read_bytes())
                self.assertTrue((self.root / prefix / "steps/extract-000001/execution.json").is_file())
                self.assertEqual(self.verify(blocked, "verify-blocked", run=run)[0], 1)
                code, reuse = self.audit(account, "reuse-blocked", ["--audit-ref", prefix + "/report.json"], run=run)
                self.assertEqual(code, 1, reuse)
                self.assertEqual(reuse["runner_dispatch_count"], 0)
                self.assertEqual((self.root / prefix / changed).read_bytes(), raw)
        self.put(self.runner, self.fixture.encode("utf-8"))
        code, clean = self.audit(account, run="workspace-control")
        self.assertEqual(code, 0, clean)
        self.assertTrue(clean["execution_complete"])
        self.assertEqual(self.verify(clean, run="workspace-control")[0], 0)
        code, reused = self.audit(account, "reused", ["--audit-ref", clean["output_ref"] + "/report.json"], run="workspace-control")
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertTrue(reused["execution_complete"])
        self.assertEqual(self.verify(reused, "verify-reused", run="workspace-control")[0], 0)

    def test_fresh_execution_proof_is_validated_before_completion(self):
        account, _ = self.accounted()
        invoke = audit.run_isolated_model
        def alter_captured_command(*args, **kwargs):
            receipt = invoke(*args, **kwargs)
            path = kwargs["execution_log"]
            execution = json.loads(path.read_bytes())
            execution["command"].append("--synthetic-undispatched-argument")
            path.write_bytes(json.dumps(execution).encode("utf-8"))
            return receipt
        with patch.object(audit, "run_isolated_model", side_effect=alter_captured_command):
            code, report = self.audit(account)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["execution_complete"])
        self.assertEqual(report["runner_dispatch_count"], 1)
        self.assertEqual(report["synthetic_dispatch_count"], 1)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertIn("proof.execution", json.dumps(report["diagnostics"]))
        execution = self.json(report["output_ref"] + "/steps/extract-000001/execution.json")
        self.assertEqual(execution["command"][-1], "--synthetic-undispatched-argument")

    def test_audit_python_runner_suppresses_bytecode_without_environment_override(self):
        account, _ = self.accounted()
        self.put("runner_dependency.py", b"VALUE = 42\n")
        self.put(self.runner, ("from runner_dependency import VALUE\nassert VALUE == 42\n" + self.fixture).encode("utf-8"))
        scripts = Path(__file__).resolve().parents[1]
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONDONTWRITEBYTECODE", None)
        clean_env.pop("PYTHONPYCACHEPREFIX", None)
        # Actual legacy describe control proves the local dependency creates
        # bytecode without an environment guard; the helper default is unchanged.
        control = ("import sys; from pathlib import Path; "
                   "sys.path.insert(0, sys.argv[1]); "
                   "from _planning_skill_common import inspect_isolated_runner; "
                   "inspect_isolated_runner(Path(sys.argv[2]))")
        proc = subprocess.run([sys.executable, "-B", "-c", control, str(scripts), str(self.root / self.runner)],
                              env=clean_env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cache = self.root / "__pycache__"
        self.assertTrue(list(cache.glob("runner_dependency.*.pyc")), "The legacy control must actually create dependency bytecode")
        shutil.rmtree(cache)
        entry = scripts / "account_b_route_sources.py"
        def cli(stage, attempt, extra):
            command = [sys.executable, str(entry), "--stage", stage, "--root", str(self.root), "--run-id", "bytecode",
                "--scope-id", "scope", "--attempt-id", attempt, "--runner", self.runner,
                "--expected-model", "synthetic/source-audit-v1", *extra]
            result = subprocess.run(command, env=clean_env, capture_output=True, text=True)
            self.assertEqual(result.stderr, "", result.stderr)
            return result.returncode, json.loads(result.stdout)
        accounted = account["output_ref"] + "/report.json"
        code, report = cli("audit", "fresh", ["--accounted", accounted])
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        expected_runner = self.root.resolve(strict=True) / self.runner
        for step in ("extract-000001", "compare"):
            execution = self.json(report["output_ref"] + "/steps/" + step + "/execution.json")
            self.assertEqual(execution["command"][:3], [sys.executable, "-B", str(expected_runner)])
        ref = report["output_ref"] + "/report.json"
        self.assertEqual(cli("verify", "verify", ["--audit-ref", ref])[0], 0)
        code, reused = cli("audit", "reused", ["--accounted", accounted, "--audit-ref", ref])
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])
        self.assertEqual(list(self.root.rglob("__pycache__")), [])

    def test_unprojected_handoff_multifile_and_conflict_are_blocking(self):
        self.put("docs/second.md", b"Return to map after the reward handoff.\n")
        self.registration(["docs/source.md", "docs/second.md"])
        account, _ = self.accounted(disposition="context")
        for index, mode in enumerate(("omission", "conflict")):
            self.mode(mode)
            code, report = self.audit(account, "blocking-" + str(index))
            self.assertEqual(code, 1, report)
            self.assertTrue(report["execution_complete"])
            self.assertFalse(report["planning_eligible"])
            finding = report["semantic_blockers"][0]
            self.assertEqual(finding["affected_proposal_ids"], [])
            self.assertTrue(finding["unprojected"])
            if mode == "conflict":
                self.assertEqual(len({r["path"] for r in finding["citations"]}), 2)
            code, verified = self.verify(report, "verify-" + str(index))
            self.assertEqual(code, 1, verified)
            self.assertTrue(verified["execution_complete"])

    def test_original_unresolved_survives_synthetic_acceptance(self):
        account, _ = self.accounted(disposition="unresolved")
        code, report = self.audit(account)
        self.assertEqual(code, 1, report)
        self.assertTrue(report["execution_complete"])
        self.assertEqual(report["semantic_blockers"][:len(account["unresolved"])], account["unresolved"])

    def test_full_files_and_empty_file_denominators(self):
        self.put("docs/empty.md", b"")
        self.registration(["docs/source.md", "docs/empty.md"])
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        raw = (self.root / "docs/source.md").read_bytes()
        candidate["file_results"][0].update(disposition="context", reason="Empty file independently reviewed.",
            evidence={"path": "docs/source.md", "raw_digest": codec.raw_digest(raw), "byte_start": 0, "byte_end": 6})
        self.put("candidate.json", candidate)
        code, account = self.account(prepared)
        self.assertEqual(code, 0, account)
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["runner_dispatch_count"], 3)
        self.assertEqual(self.verify(report)[0], 0)

    def test_invalid_output_receipt_and_dispositions_fail_closed(self):
        account, _ = self.accounted()
        for mode in ("bad-quote", "missing-block", "duplicate-block", "reordered-blocks", "fake-pass", "bad-proposal",
                     "missing-file", "tools", "extra-dispatch", "unknown", "deferred"):
            with self.subTest(mode=mode):
                self.mode(mode)
                code, report = self.audit(account, mode, run=mode)
                self.assertEqual(code, 1, report)
                self.assertFalse(report["execution_complete"])
                self.assertFalse(report["planning_eligible"])
                self.assertEqual(report["termination_reason"], "execution_blocked")
                self.assertTrue((self.root / report["output_ref"] / "event.json").is_file())

    def test_capacity_zero_dispatch_and_persistent_budget_cannot_increase(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--transport-max-bytes", "100"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "capacity_blocked")
        self.assertEqual(report["runner_dispatch_count"], 0)
        code, report = self.audit(account, "raised", ["--request-budget", "100"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_budget_across_attempt_and_date_failure_not_refunded(self):
        account, _ = self.accounted()
        self.mode("crash")
        code, first = self.audit(account, extras=["--request-budget", "1", "--active-budget-seconds", "330"])
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 1)
        self.assertEqual(first["model_dispatch_count"], "unknown")
        home = (self.root / first["output_ref"]).parent
        date_path = home.parents[1]
        destination = self.root / "logs/ci/2001-01-01/b-route-source-audit/run"
        destination.parent.mkdir(parents=True)
        home.rename(destination)
        code, second = self.audit(account, "second", ["--request-budget", "1", "--active-budget-seconds", "330"])
        self.assertEqual(code, 1, second)
        self.assertEqual(second["termination_reason"], "budget_blocked")
        self.assertEqual(second["runner_dispatch_count"], 0)
        self.assertEqual(len(list((destination / "reservations").iterdir())), 1)

    def test_pending_metadata_lock_does_not_dispatch(self):
        account, _ = self.accounted()
        code, first = self.audit(account)
        self.assertEqual(code, 0, first)
        home = (self.root / first["output_ref"]).parent
        (home / "budget.lock").write_bytes(b"Interrupted metadata reservation.")
        code, report = self.audit(account, "busy")
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "budget_blocked")
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_budget_deletion_and_corruption_fail_closed_without_rewriting_history(self):
        account, _ = self.accounted()
        for mutation in ("budget", "tail", "tail-and-step-copy", "all-permits", "permit-duration",
                         "permit-scope", "step-copy", "binding", "terminal-count", "invalid-json"):
            with self.subTest(mutation=mutation):
                run = "integrity-" + mutation
                code, first = self.audit(account, run=run)
                self.assertEqual(code, 0, first)
                home = (self.root / first["output_ref"]).parent
                permit = sorted((home / "reservations").glob("*.json"))[-1]
                value = self.json(permit.relative_to(self.root).as_posix())
                step_copy = home / first["attempt_id"] / "steps" / value["step"] / "reservation.json"
                missing = []
                if mutation == "budget":
                    missing = [home / "budget.json"]
                elif mutation in {"tail", "tail-and-step-copy"}:
                    missing = [permit] + ([step_copy] if mutation == "tail-and-step-copy" else [])
                elif mutation == "all-permits":
                    missing = list((home / "reservations").iterdir())
                elif mutation in {"permit-duration", "permit-scope", "step-copy"}:
                    target = step_copy if mutation == "step-copy" else permit
                    value["reserved_seconds"] = 1
                    if mutation == "permit-scope":
                        value["scope_id"] = "wrong-scope"
                    self.put(target.relative_to(self.root).as_posix(), value)
                elif mutation == "binding":
                    target = home / first["attempt_id"] / "budget-binding.json"
                    value = self.json(target.relative_to(self.root).as_posix())
                    value["request_budget"] += 1
                    self.put(target.relative_to(self.root).as_posix(), value)
                elif mutation == "terminal-count":
                    target = home / first["attempt_id"] / "report.json"
                    value = self.json(target.relative_to(self.root).as_posix())
                    value["runner_dispatch_count"] += 1
                    self.put(target.relative_to(self.root).as_posix(), value)
                else:
                    (home / "budget.json").write_bytes(b'{"broken":')
                for path in missing:
                    path.unlink()
                before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
                with patch.object(audit, "run_isolated_model") as model:
                    code, blocked = self.audit(account, "after-corruption", run=run)
                self.assertEqual(code, 1, blocked)
                self.assertEqual(blocked["runner_dispatch_count"], 0)
                self.assertFalse(blocked["execution_complete"])
                model.assert_not_called()
                for path, raw in before.items():
                    self.assertEqual((home / path).read_bytes(), raw)
                self.assertTrue(all(not p.exists() for p in missing))

    def test_missing_fixed_budget_after_zero_dispatch_cannot_raise_limits(self):
        account, _ = self.accounted()
        code, first = self.audit(account, extras=["--transport-max-bytes", "100"])
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 0)
        home = (self.root / first["output_ref"]).parent
        (home / "budget.json").unlink()
        shutil.rmtree(home / "reservations")
        with patch.object(audit, "run_isolated_model") as model:
            code, blocked = self.audit(account, "raised-after-deletion", ["--request-budget", "100"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertFalse((home / "budget.json").exists())
        model.assert_not_called()

    def test_orphan_reservation_witness_prevents_refund_before_step_copy(self):
        account, _ = self.accounted()
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "orphan",
            "--scope-id", "scope", "--attempt-id", "lost-process", "--accounted", "account.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1",
            "--request-budget", "1", "--timeout-seconds", "1", "--active-budget-seconds", "31"])
        root, home, _, _ = audit.enter(args)
        audit.reserve(root, home, args, None)
        audit.reserve(root, home, args, "extract-000001")
        witness = home / "lost-process/budget-permits/000001.json"
        raw = witness.read_bytes()
        (home / "reservations/000001.json").unlink()
        code, blocked = self.audit(account, "after-loss", ["--request-budget", "1", "--timeout-seconds", "1",
            "--active-budget-seconds", "31"], run="orphan")
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(witness.read_bytes(), raw)
        self.assertFalse((home / "reservations/000001.json").exists())

    def test_legacy_partial_dispatch_with_deleted_permits_remains_blocked(self):
        account, _ = self.accounted()
        self.mode("crash")
        code, first = self.audit(account)
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 1)
        home = (self.root / first["output_ref"]).parent
        attempt = home / first["attempt_id"]
        # Remove only the new witness entries from this controlled fixture to
        # reproduce the pre-patch evidence layout; retain actual OS failure proof.
        (attempt / "budget-binding.json").unlink()
        shutil.rmtree(attempt / "budget-permits")
        event = self.json(first["output_ref"] + "/event.json")
        event["artifacts"] = {p: digest for p, digest in event["artifacts"].items()
                              if p != "budget-binding.json" and not p.startswith("budget-permits/")}
        self.put(first["output_ref"] + "/event.json", event)
        (home / "reservations/000001.json").unlink()
        (attempt / "steps/extract-000001/reservation.json").unlink()
        code, blocked = self.audit(account, "after-partial-loss")
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertTrue((attempt / "steps/extract-000001/execution.json").is_file())

    def test_legacy_valid_budget_continues_without_rewriting_old_evidence(self):
        account, _ = self.accounted()
        code, first = self.audit(account)
        self.assertEqual(code, 0, first)
        home = (self.root / first["output_ref"]).parent
        attempt = home / first["attempt_id"]
        (attempt / "budget-binding.json").unlink()
        shutil.rmtree(attempt / "budget-permits")
        event = self.json(first["output_ref"] + "/event.json")
        event["artifacts"] = {p: digest for p, digest in event["artifacts"].items()
                              if p != "budget-binding.json" and not p.startswith("budget-permits/")}
        self.put(first["output_ref"] + "/event.json", event)
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        code, second = self.audit(account, "legacy-next")
        self.assertEqual(code, 0, second)
        self.assertEqual(len(list((home / "reservations").iterdir())), 4)
        for path, raw in before.items():
            self.assertEqual((home / path).read_bytes(), raw)

    def test_first_initialization_survives_unfunded_concurrent_lock_failure(self):
        account, _ = self.accounted()
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "first-concurrent",
            "--scope-id", "scope", "--attempt-id", "waiting", "--accounted", account["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", "--request-budget", "32",
            "--timeout-seconds", "300", "--active-budget-seconds", "3600"])
        root, home, waiting, _ = audit.enter(args)
        sources.write(waiting / "request.json", {**vars(args), "root": str(root)})
        (home / "budget.lock").write_bytes(b"Synthetic concurrent first initializer.")
        code, loser = self.audit(account, "lock-loser", run="first-concurrent")
        self.assertEqual(code, 1, loser)
        self.assertEqual(loser["termination_reason"], "budget_blocked")
        self.assertEqual(loser["runner_dispatch_count"], 0)
        (home / "budget.lock").unlink()
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        code, winner = self.audit(account, "initializer", run="first-concurrent")
        self.assertEqual(code, 0, winner)
        self.assertEqual(len(list((home / "reservations").iterdir())), 2)
        for path, raw in before.items():
            self.assertEqual((home / path).read_bytes(), raw)

    def test_damaged_proof_rejected_without_rerun(self):
        account, _ = self.accounted()
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        path = self.root / report["output_ref"] / "steps/extract-000001/workspace/output.json"
        path.write_bytes(b"{}\n")
        code, failed = self.audit(account, "reuse-broken", ["--audit-ref", report["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, failed)
        self.assertEqual(failed["runner_dispatch_count"], 0)
        self.assertEqual(self.verify(report)[0], 1)

    def test_source_changes_reuse_only_unchanged_extraction_and_global_reruns(self):
        self.put("docs/second.md", b"A second complete file.\n")
        self.registration(["docs/source.md", "docs/second.md"])
        account, prepared = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put("docs/second.md", b"A changed complete second file.\n")
        next_prepared = self.prepare("changed", ["--previous", prepared["prepared_ref"]["path"]])
        self.candidate(next_prepared)
        code, next_account = self.account(next_prepared, "changed")
        self.assertEqual(code, 0, next_account)
        code, changed = self.audit(next_account, "changed-audit", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, changed)
        self.assertEqual(changed["runner_dispatch_count"], 2)
        self.assertEqual([r["path"] for r in changed["reused_extractions"]], ["docs/source.md"])
        self.assertEqual(self.verify(changed)[0], 0)
        self.assertEqual(self.verify(original, "stale-original")[0], 1)

    def test_projection_only_change_reuses_all_extractions(self):
        account, prepared = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        candidate = self.json("candidate.json")
        for row in candidate["block_results"]:
            for atom in row["atoms"]:
                atom["acceptance_intent"] = "Reviewed changed acceptance intent."
        self.put("candidate.json", candidate)
        code, next_account = self.account(prepared, "changed-proposal")
        self.assertEqual(code, 0, next_account)
        code, changed = self.audit(next_account, "changed-audit", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, changed)
        self.assertEqual(changed["runner_dispatch_count"], 1)
        self.assertEqual(len(changed["reused_extractions"]), 1)

    def test_runner_and_expected_model_changes_reject_reuse(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put(self.runner, (self.fixture + "\n# Relevant runner byte change.\n").encode())
        code, report = self.audit(account, "changed-tool", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)
        self.assertEqual(self.verify(original)[0], 1)
        self.assertEqual(self.audit(account, "wrong-model", ["--expected-model", "wrong-model"])[0], 1)

    def test_terminal_event_conflict_partial_and_argument_rejection(self):
        account, _ = self.accounted()
        self.assertEqual(self.audit(account, "reservations", run="reserved-first")[0], 2)
        self.assertEqual(list((self.root / "logs/ci").glob("*/b-route-source-audit/reserved-first")), [])
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        event = self.root / original["output_ref"] / "event.json"
        before = event.read_bytes()
        self.assertEqual(self.audit(account, extras=["--request-budget", "99"])[0], 2)
        self.assertEqual(event.read_bytes(), before)
        event.unlink()
        self.assertEqual(self.audit(account)[0], 2)
        for extras in (["--runner", "../escape.py"], ["--expected-model", "environment-default"], ["--prepared", "unwanted.json"]):
            self.assertEqual(self.audit(account, "bad-args", extras)[0], 2)

    def test_old_prepare_account_request_identity_and_audit_options_rejected(self):
        account, prepared = self.accounted()
        for report in (account, prepared):
            request = self.json(report["output_ref"] + "/request.json")
            self.assertEqual(len(request), 14)
            self.assertTrue(set(request).isdisjoint(sources.AUDIT_ARGUMENTS))
        self.assertEqual(self.prepare("base"), prepared)
        self.assertEqual(self.account(prepared, "base")[1], account)
        for option, value in (("--runner", "runner.py"), ("--accounted", "a.json"),
                              ("--request-budget", "32"), ("--timeout-seconds", "300")):
            code, _ = self.invoke("prepare", "invalid-old", ["--source-set", "docs/source-set.json", option, value])
            self.assertEqual(code, 2)

    def test_actual_timeout_kills_runner_and_retains_unknown_reservation(self):
        account, _ = self.accounted()
        self.mode("timeout")
        code, report = self.audit(account, extras=["--timeout-seconds", "1", "--active-budget-seconds", "31", "--request-budget", "1"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "time_blocked")
        self.assertEqual(report["diagnostics"][0]["reason_code"], "budget_exhausted")
        self.assertEqual(report["runner_dispatch_count"], 1)
        self.assertEqual(report["model_dispatch_count"], "unknown")
        execution = self.json(report["output_ref"] + "/steps/extract-000001/execution.json")
        self.assertEqual(execution["status"], "timeout")
        self.assertNotEqual(execution["returncode"], 0)
        self.assertLess(report["active_elapsed_seconds"], 30)

    def test_transitive_runner_dependency_and_sc_backend_are_bound(self):
        account, _ = self.accounted()
        self.put("runner_dependency.py", b"MARKER = 'original'\n")
        self.put(self.runner, ("from runner_dependency import MARKER\n" + self.fixture).encode())
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        identity = self.json(original["output_ref"] + "/identity.json")
        self.assertIn("runner_dependency.py", identity["tools"])
        backend = (Path(audit.__file__).resolve().parents[1] / "sc" / "_llm_backend.py").resolve(strict=True)
        self.assertEqual(codec.raw_digest(backend.read_bytes()), identity["tools"][str(backend)])
        self.put("runner_dependency.py", b"MARKER = 'changed'\n")
        code, report = self.audit(account, "changed-dependency", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_same_sources_and_proposals_new_preparation_time_reuses_global(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        next_account, _ = self.accounted("new-prepare")
        code, report = self.audit(next_account, "same-content", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_concurrent_budget_permits_cannot_overspend(self):
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "parallel", "--scope-id", "scope",
            "--attempt-id", "one", "--accounted", "account.json", "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1",
            "--request-budget", "1", "--timeout-seconds", "1", "--active-budget-seconds", "31"])
        root, home, _, _ = audit.enter(args)
        audit.reserve(root, home, args, None)
        def reserve_one(index):
            try:
                return audit.reserve(root, home, args, "step-" + str(index))
            except (audit.AuditStop, codec.CodecError):
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve_one, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(list((home / "reservations").iterdir())), 1)

    def test_actual_cli_audit_verify_both_entries_and_negative_without_bytecode(self):
        account, _ = self.accounted()
        script_root = Path(__file__).resolve().parents[1]
        for name in ("account_b_route_sources.py", "dev_cli.py"):
            entry = script_root / name
            code, report = self.audit(account, "cli-" + name.replace(".", "-"), entry=entry)
            self.assertEqual(code, 0, report)
            code, verified = self.verify(report, "verify-" + name.replace(".", "-"), entry=entry)
            self.assertEqual(code, 0, verified)
            self.assertEqual(self.verify(report, "bad-" + name.replace(".", "-"), ["--expected-model", "default"], entry=entry)[0], 2)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])

    def test_rehashed_proof_with_bad_quote_is_still_rejected(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        prefix = original["output_ref"]
        step = prefix + "/steps/extract-000001"
        value = self.json(step + "/workspace/output.json")
        value["obligations"][0]["citations"][0]["quote"] = "Invented original quotation."
        self.put(step + "/workspace/output.json", value)
        receipt = self.json(step + "/receipt.json")
        receipt["output_chars"] = len((self.root / step / "workspace/output.json").read_text(encoding="utf-8"))
        self.put(step + "/receipt.json", receipt)
        execution = self.json(step + "/execution.json")
        execution["stdout"] = json.dumps(receipt) + "\n"
        execution["stdout_base64"] = base64.b64encode(execution["stdout"].encode()).decode()
        self.put(step + "/execution.json", execution)
        event = self.json(prefix + "/event.json")
        for name in event["artifacts"]:
            event["artifacts"][name] = codec.raw_digest((self.root / prefix / name).read_bytes())
        self.put(prefix + "/event.json", event)
        code, report = self.audit(account, "rehashed", ["--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)
        self.assertIn("citation.quote", json.dumps(report["diagnostics"]))

    def test_source_and_glob_drift_fail_before_dispatch(self):
        self.registration(["docs/*.md"], active=["docs/source.md"])
        account, _ = self.accounted()
        raw = (self.root / "docs/source.md").read_bytes()
        self.put("docs/source.md", raw + b"Drift.\n")
        code, changed = self.audit(account)
        self.assertEqual(code, 1, changed)
        self.assertEqual(changed["runner_dispatch_count"], 0)
        self.put("docs/source.md", raw)
        self.put("docs/added.md", b"A new glob member.\n")
        code, added = self.audit(account, "new-member")
        self.assertEqual(code, 1, added)
        self.assertEqual(added["runner_dispatch_count"], 0)

    def test_supported_deferred_obligation_keeps_explicit_review(self):
        account, _ = self.accounted()
        self.mode("supported-deferred")
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        self.assertEqual(self.verify(report)[0], 0)

    def test_rule_schema_and_parser_change_do_not_reuse_old_conclusions(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        ref = original["output_ref"] + "/report.json"
        with patch.object(audit, "RULES", "changed-rule"):
            code, changed = self.audit(account, "rule-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        with patch.dict(audit.PROMPTS, {"extract": audit.PROMPTS["extract"] + "Changed prompt rule."}):
            code, changed = self.audit(account, "prompt-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        schema = audit.output_schema
        def changed_schema(phase):
            result = schema(phase)
            result["properties"]["new_field"] = {"type": "string"}
            result["required"].append("new_field")
            return result
        with patch.object(audit, "output_schema", changed_schema):
            code, changed = self.audit(account, "schema-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        build = sources.native.build_ledger
        def changed_parser(*args, **kwargs):
            manifest, ledger = build(*args, **kwargs)
            ledger["blocks"][0]["raw_text"] = "A changed native parser result."
            return manifest, ledger
        with patch.object(sources.native, "build_ledger", changed_parser):
            code, changed = self.audit(account, "parser-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)

    def test_disk_failure_and_end_read_drift_never_claim_completion(self):
        account, _ = self.accounted()
        write = sources.write
        def disk_failure(path, value):
            if path.name == "event.json" and "b-route-source-audit" in str(path):
                raise OSError("Synthetic final event persistence failure.")
            return write(path, value)
        with patch.object(sources, "write", disk_failure):
            code, failed = self.audit(account, "partial")
        self.assertEqual(code, 1, failed)
        self.assertEqual(failed["termination_reason"], "partial_write")
        self.assertFalse(failed["execution_complete"])
        self.assertEqual(self.audit(account, "partial")[0], 2)
        verify = sources.Observations.verify
        changed = False
        def drift(obs):
            nonlocal changed
            if not changed:
                self.put("docs/source.md", b"Synthetic concurrent source edit.\n")
                changed = True
            return verify(obs)
        with patch.object(sources.Observations, "verify", drift):
            code, failed = self.audit(account, "drift")
        self.assertEqual(code, 1, failed)
        self.assertFalse(failed["execution_complete"])
        self.assertFalse(failed["planning_eligible"])

    @unittest.skipUnless(os.name == "nt", "Requires actual Windows junction and short-path rejection")
    def test_windows_audit_real_junction_and_short_path_rejected(self):
        account, _ = self.accounted()
        outside = self.root / "outside-long-audit-directory"
        outside.mkdir()
        (outside / "runner.py").write_bytes(self.fixture.encode("utf-8"))
        link = self.root / "junction"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        try:
            self.assertEqual(self.audit(account, extras=["--runner", "junction/runner.py"])[0], 2)
            self.assertEqual([p.name for p in outside.iterdir()], ["runner.py"])
        finally:
            os.rmdir(link)
        directory = self.root / "long-runner-directory-for-source-audit"
        directory.mkdir()
        (directory / "runner.py").write_bytes(self.fixture.encode("utf-8"))
        buffer = ctypes.create_unicode_buffer(32768)
        self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(directory), buffer, len(buffer)), 0)
        if "~" not in buffer.value:
            proc = subprocess.run(["fsutil", "file", "setshortname", str(directory), "AUDIT2~2"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(directory), buffer, len(buffer)), 0)
        self.assertIn("~", buffer.value)
        relative_alias = Path(buffer.value).name + "/runner.py"
        self.assertTrue((self.root / relative_alias).is_file(), "The alias must address the actual existing runner")
        self.assertEqual(self.audit(account, "alias", ["--runner", relative_alias])[0], 2)
        self.assertEqual(list(directory.iterdir()), [directory / "runner.py"])


# Prevent duplicated inherited Story 2.1 test execution in this targeted suite.
for _name in list(vars(SourceAccountingTests)):
    if _name.startswith("test_") and _name not in vars(SourceAuditTests):
        setattr(SourceAuditTests, _name, None)
del SourceAccountingTests

if __name__ == "__main__":
    unittest.main()
