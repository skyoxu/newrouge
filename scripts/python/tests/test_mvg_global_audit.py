"""Exercise global audit and reopen using real offline selected checkpoints."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_global_audit as global_audit
import _mvg_capability_selection as selection
import _mvg_capability_checkpoint as checkpoint
import _mvg_capability_generation as generation
import plan_mvg
import dev_cli
from dev_cli_builders import build_plan_mvg_cmd
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
import test_mvg_capability_append as append_fixture


class GlobalAuditTests(unittest.TestCase):
    def test_public_cli_and_builder_preserve_exact_run_artifact_and_hash(self):
        cases = [("audit", ["--conflict-report", "logs/declared.json", "--conflict-report-sha256", "sha256:report"],
                  {"conflict_report_sha256": "sha256:report"}),
                 ("reopen-plan", ["--audit", "global-audits/a.json", "--audit-sha256", "sha256:audit"],
                  {"audit_path": "global-audits/a.json", "audit_sha256": "sha256:audit"}),
                 ("reopen", ["--plan", "reopen-plans/p.json", "--plan-sha256", "sha256:plan"],
                  {"plan_path": "reopen-plans/p.json", "plan_sha256": "sha256:plan"})]
        for stage, arguments, expected in cases:
            with self.subTest(stage=stage):
                parsed = dev_cli.build_parser().parse_args(["plan-mvg", "--stage", stage, "--run-id", "exact-run"] + arguments)
                command = build_plan_mvg_cmd(parsed)
                self.assertEqual(["py", "-3", "scripts/python/plan_mvg.py", "--repo-root", ".", stage,
                                  "--run-id", "exact-run"] + arguments, command)
                with patch.object(global_audit, "operate", return_value={"status": "offline"}) as operation, redirect_stdout(io.StringIO()):
                    self.assertEqual(0, plan_mvg.main(command[3:]))
                self.assertEqual("exact-run", operation.call_args.kwargs["run_id"])
                self.assertEqual(stage, operation.call_args.kwargs["operation"])
                for key, value in expected.items():
                    self.assertEqual(value, operation.call_args.kwargs[key])
                parsed = dev_cli.build_parser().parse_args(["plan-mvg", "--stage", stage, "--run-id", "exact-run"] + arguments[:2])
                with self.assertRaisesRegex(ValueError, "artifact and SHA-256 pair"):
                    build_plan_mvg_cmd(parsed)

    def report(self, run, *, capability="CAP-a", flow="flow-a", issue_id="conflict-a"):
        state = load_json(run / "run.json")
        proposal = load_json(run / "proposal.json")
        refs = []
        index = load_json(run / "analysis-input/analysis-index.json")
        row = next(row for row in proposal["manifest_candidate"]["flows"] if row["id"] == flow)
        for ref in [row["source_paths"][0], row["handoffs"][0]["contract_ref"]]:
            key = next(key for key in index["files"] if key in {"sources/" + ref, "references/" + ref})
            path = run / "analysis-input" / key
            refs.append({"path": ref, "sha256": file_sha(path),
                "citations": [{"line": 1, "text": path.read_bytes().decode("utf-8-sig").splitlines(keepends=True)[0]}]})
        return {"schema_version": global_audit.REPORT_SCHEMA, "run_id": state["run_id"],
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "checkpoint_head_sha256": canonical_sha(state["capability_selection"]["checkpoint_head"]),
            "proposal_sha256": canonical_sha(proposal), "status": "reviewed", "reviewer": "offline-owner",
            "rationale": "Explicit reviewed source conflict fixture", "conflicts": [{"id": issue_id,
                "kind": "source_conflict", "severity": "hard", "contradiction": "Accepted behavior contradicts the cited source boundary",
                "capability_ids": [capability], "flow_ids": [flow], "source_refs": refs}]}

    def audit_report(self, root, run, report):
        path = root / "logs/conflict-declaration.json"
        atomic_json(path, report)
        return global_audit.operate(root, run_id="fixture", operation="audit",
            conflict_report=str(path), conflict_report_sha256=file_sha(path))

    def test_offline_audit_reopen_replacements_and_stale_matrix(self):
        def completed(root, run):
            initial = load_json(run / "run.json")
            original_calls = deepcopy(initial["capability_selection"]["calls"])
            original_total = initial["capability_selection"]["total_invocations"]
            immutable = {path: path.read_bytes() for folder in ("candidates", "capability-selection", "capability-checkpoints", "accepted-chain")
                         for path in (run / folder).rglob("*") if path.is_file()}
            with self.subTest(scenario="OVERLAP"):
                receipt = global_audit.operate(root, run_id="fixture", operation="audit")
                self.assertEqual("passed", receipt["status"])
                self.assertTrue(any(row["kind"] == "contract" for row in receipt["ordinary_overlaps"]))
                self.assertTrue(any(row["kind"] == "requirement" for row in receipt["ordinary_overlaps"]))
                self.assertEqual([], receipt["hard_conflicts"])
                self.assertEqual(initial["capability_selection"], load_json(run / "run.json")["capability_selection"])
                with self.assertRaisesRegex(ValueError, "requires_source_backed"):
                    global_audit.operate(root, run_id="fixture", operation="reopen-plan",
                        audit_path=receipt["path"], audit_sha256=receipt["sha256"])
            report = self.report(run)
            report["conflicts"] += self.report(run, capability="CAP-b", flow="flow-b", issue_id="future-b")["conflicts"]
            good_state = load_json(run / "run.json")
            for mutation in ("missing-citations", "changed-quote", "changed-source-hash", "changed-head", "changed-proposal", "unreviewed"):
                with self.subTest(scenario="CONFLICT evidence gap", mutation=mutation):
                    invalid = deepcopy(report)
                    if mutation == "missing-citations":
                        invalid["conflicts"][0]["source_refs"][0]["citations"] = []
                    elif mutation == "changed-quote":
                        invalid["conflicts"][0]["source_refs"][0]["citations"][0]["text"] = "Invented quote"
                    elif mutation == "changed-source-hash":
                        invalid["conflicts"][0]["source_refs"][0]["sha256"] = "sha256:changed"
                    elif mutation == "unreviewed":
                        invalid["status"] = "draft"
                    else:
                        invalid["checkpoint_head_sha256" if mutation == "changed-head" else "proposal_sha256"] = "sha256:changed"
                    receipt = self.audit_report(root, run, invalid)
                    self.assertEqual("blocked", receipt["status"])
                    self.assertTrue(receipt["evidence_gaps"])
                    self.assertEqual([], receipt["hard_conflicts"])
                    with self.assertRaisesRegex(ValueError, "global_conflict_"):
                        global_audit.operate(root, run_id="fixture", operation="reopen-plan",
                            audit_path=receipt["path"], audit_sha256=receipt["sha256"])
                    atomic_json(run / "run.json", good_state)
            with self.subTest(scenario="CONFLICT exact closure"):
                receipt = self.audit_report(root, run, report)
                plan = global_audit.operate(root, run_id="fixture", operation="reopen-plan",
                    audit_path=receipt["path"], audit_sha256=receipt["sha256"])
                self.assertEqual(["CAP-a", "CAP-b"], plan["invalidated_capability_ids"])
                self.assertEqual(["CAP-a", "CAP-b"], plan["replacement_order"])
                self.assertEqual(2, len(plan["invalidated_checkpoints"]))
                self.assertEqual({"conflict-a": 0, "future-b": 1}, plan["conflict_resolution_boundaries"])
                self.assertFalse(plan["refund_invocations"])
                self.assertFalse(plan_mvg.validate(root, run_id="fixture")["formal_applicable"])
            bound_state = load_json(run / "run.json")
            for mutation in ("head", "budget", "source", "pending-journal", "completed-journal", "plan-hash"):
                with self.subTest(scenario="STALE", mutation=mutation):
                    changed = deepcopy(bound_state)
                    source = None
                    if mutation == "head":
                        changed["capability_selection"]["checkpoint_head"] = None
                    elif mutation == "budget":
                        changed["mvg.run_invocation_limit"] = 191
                    elif mutation == "source":
                        source = root / report["conflicts"][0]["source_refs"][0]["path"]
                        original_source = source.read_bytes()
                        source.write_bytes(original_source + b"\nChanged source\n")
                    elif mutation.endswith("journal"):
                        atomic_json(run / "apply-journal.json", {"status": "pending" if mutation.startswith("pending") else "complete"})
                    atomic_json(run / "run.json", changed)
                    before = (run / "run.json").read_bytes()
                    with self.assertRaises(ValueError):
                        global_audit.operate(root, run_id="fixture", operation="reopen", plan_path=plan["path"],
                            plan_sha256="sha256:changed" if mutation == "plan-hash" else plan["sha256"])
                    self.assertEqual(before, (run / "run.json").read_bytes())
                    if source:
                        source.write_bytes(original_source)
                    if mutation.endswith("journal"):
                        (run / "apply-journal.json").unlink()
                    atomic_json(run / "run.json", bound_state)
            with self.subTest(scenario="REOPEN atomic failure before replace"):
                def fail_before(path, value):
                    raise OSError("fixture_before_replace")
                before = (run / "run.json").read_bytes()
                with checkpoint.coordinator_lock(run), self.assertRaisesRegex(OSError, "before_replace"):
                    global_audit.execute_reopen(root, run, load_json(run / "run.json"),
                        plan_path=plan["path"], plan_sha256=plan["sha256"], writer=fail_before)
                self.assertEqual(before, (run / "run.json").read_bytes())
            with self.subTest(scenario="REOPEN replacement isolation and cost conservation"):
                reopened = global_audit.operate(root, run_id="fixture", operation="reopen",
                    plan_path=plan["path"], plan_sha256=plan["sha256"])
                self.assertEqual(original_total, reopened["total_invocations"])
                pending = load_json(run / "run.json")
                self.assertEqual([], pending["capability_selection"]["selected"])
                self.assertEqual(2, pending["capability_selection"]["generation"])
                gap = global_audit.operate(root, run_id="fixture", operation="audit")
                self.assertTrue(any(row["code"] == "unresolved_reopened_conflicts" for row in gap["evidence_gaps"]))
                original_runner = plan_mvg.run_isolated_model.side_effect
                real_preflight = generation.preflight_runner_payload
                injected = []
                transmitted = []
                def checked_runner(*args, **kwargs):
                    prompt = kwargs["prompt_path"].read_text(encoding="utf-8")
                    payload = json.loads(prompt.split("\n", 1)[1])
                    if "reopen_context" in payload:
                        current = load_json(run / "run.json")
                        expected = global_audit.reopen_context(current, payload["scope"])
                        self.assertEqual(expected, payload["reopen_context"])
                        self.assertEqual(["conflict-a"] if payload["scope"]["capability_id"] == "CAP-a"
                            else ["conflict-a", "future-b"], expected["resolution_required_conflict_ids"])
                        transmitted.append((payload["scope"]["capability_id"], kwargs["output_path"].name))
                    receipt = original_runner(*args, **kwargs)
                    if kwargs["output_path"].name == "capability-review.json" and not injected:
                        value = load_json(kwargs["output_path"])
                        value["reopen_reviews"][0]["verdict"] = "blocked"
                        atomic_json(kwargs["output_path"], value)
                        receipt["output_sha256"] = file_sha(kwargs["output_path"])
                        injected.append(True)
                    return receipt
                def stop_repair(*args, **kwargs):
                    payload = json.loads(args[2].split("\n", 1)[1])
                    if payload.get("hard_issue") and injected:
                        raise SystemExit("fixture_stop_after_blocked_resolution")
                    return real_preflight(*args, **kwargs)
                with patch.object(plan_mvg, "run_isolated_model", side_effect=checked_runner), \
                     patch.object(generation, "preflight_runner_payload", side_effect=stop_repair), \
                     self.assertRaisesRegex(SystemExit, "blocked_resolution"):
                    plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                stopped = load_json(run / "run.json")
                self.assertEqual([], stopped["capability_selection"]["selected"])
                self.assertEqual(original_total + 2, stopped["capability_selection"]["total_invocations"])
                ledgers = list((run / "candidates").rglob("append-ledger.json"))
                self.assertTrue(any("reopen_conflict_unresolved" in path.read_text(encoding="utf-8") for path in ledgers))
                retry_ledger_path = run / "candidates/candidate-1/generation-2/scope-1/capability-append/append-ledger.json"
                stopped_retry = load_json(retry_ledger_path)
                self.assertEqual([1], list(stopped_retry["current"]["issue_attempts"].values()))
                self.assertEqual(["generate", "semantic"], [row["phase"] for row in stopped_retry["calls"]])
                real_commit = checkpoint.commit_checkpoint
                def stop_after_commit(*args, **kwargs):
                    result = real_commit(*args, **kwargs)
                    if len(args[1]["capability_selection"]["selected"]) == 2:
                        raise SystemExit("fixture_after_checkpoint_commit")
                    return result
                with patch.object(plan_mvg, "run_isolated_model", side_effect=checked_runner), \
                     patch.object(checkpoint, "commit_checkpoint", side_effect=stop_after_commit), \
                     self.assertRaisesRegex(SystemExit, "after_checkpoint_commit"):
                    plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                interrupted = load_json(run / "run.json")
                self.assertEqual(2, len(interrupted["capability_selection"]["selected"]))
                self.assertEqual(1, len(interrupted["reopen_history"][0]["replacement_selections"]))
                with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected recovery dispatch")):
                    plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                self.assertEqual({("CAP-a", "capability-append.json"), ("CAP-a", "capability-review.json"),
                    ("CAP-b", "capability-append.json"), ("CAP-b", "capability-review.json")}, set(transmitted))
                state = load_json(run / "run.json")
                selection.verify_published_chain(root, run, state)
                self.assertEqual(original_total * 2 + 4, state["capability_selection"]["total_invocations"])
                retried = load_json(retry_ledger_path)
                self.assertEqual(["generate", "semantic", "repair", "repair", "generate", "semantic"],
                    [row["phase"] for row in retried["calls"]])
                self.assertEqual(2, len(retried["rejected_repairs"]))
                self.assertTrue(all("repair_target_unchanged" in row["errors"] for row in retried["rejected_repairs"]))
                self.assertEqual(1, len(retried["restarts"]))
                self.assertEqual(3, retried["restarts"][0]["repair_attempts"])
                self.assertEqual(original_calls, state["capability_selection"]["calls"][:original_total])
                self.assertEqual({label: 12 if label == "candidate-1" else 8 for label in plan_mvg.MVG_CANDIDATE_LABELS},
                                 state["capability_selection"]["lineage_invocations"])
                for step in state["capability_selection"]["selected"]:
                    for label, admission in step["admissions"].items():
                        self.assertEqual(label + "-r2", admission["lineage"])
                        self.assertIn("generation-2", admission["workspace"])
                        self.assertEqual(6 if label == "candidate-1" and step == state["capability_selection"]["selected"][0]
                            else 2, admission["total_invocations"])
                    self.assertEqual("resolved", step["record"]["proof"]["review"]["reopen_reviews"][0]["verdict"])
                self.assertEqual(2, len(state["reopen_history"][0]["replacement_selections"]))
                audited = global_audit.verified_audit(root, run, state)
                self.assertEqual("passed", audited["status"])
                self.assertEqual(["conflict-a", "future-b"], audited["resolved_reopened_conflicts"][0]["conflict_ids"])
                self.assertFalse(audited["runtime_verified"])
                self.assertEqual(immutable, {path: path.read_bytes() for path in immutable})
                with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected paid recovery")):
                    plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                self.assertEqual(original_total * 2 + 4, load_json(run / "run.json")["capability_selection"]["total_invocations"])
                proposal = load_json(run / "proposal.json")
                proof = load_json(root / state["selected_admission_review"]["path"])
                for bad in (None, [], "invalid", {"generation": "2"}, {"generation": 2, "plan": []}):
                    changed = deepcopy(proof)
                    if bad is None:
                        changed["records"][0]["proof"].pop("reopen_context")
                    else:
                        changed["records"][0]["proof"]["reopen_context"] = bad
                    self.assertTrue(any("reopen_context" in row["code"] for row in
                        plan_mvg.candidate_admission_errors(root, state, proposal, changed)))
                old = initial["capability_selection"]["selected"][0]
                unselected = next(label for label in old["admissions"] if label != old["selected_candidate"])
                historical = [run / old["admissions"][unselected][key + "_path"] for key in ("proposal", "proof")]
                historical += [(run / old["selection_path"]).parent / "A.json"]
                archived = global_audit.historical_states(run, state)[0]
                historical += [run / archived[key]["path"] for key in ("global_audit", "global_conflict_report")]
                historical += [run / call["request_identity"]["output_path"] for call in original_calls
                    if call["request_identity"]["output_path"].endswith("capability-review.json")][:1]
                for path in historical:
                    before = path.read_bytes()
                    try:
                        changed = load_json(path)
                        changed["fixture_tamper"] = True
                        atomic_json(path, changed)
                        for verify in (lambda: selection.verified_prefix(root, run, state),
                                lambda: global_audit.verified_audit(root, run, state),
                                lambda: plan_mvg._freeze_apply_checkpoint_binding(root, run, state)):
                            with self.assertRaises(ValueError):
                                verify()
                    finally:
                        path.write_bytes(before)
            with self.subTest(scenario="REOPEN atomic failure after replace and retained prefix"):
                report = self.report(run, capability="CAP-b", flow="flow-b", issue_id="conflict-b")
                receipt = self.audit_report(root, run, report)
                plan = global_audit.operate(root, run_id="fixture", operation="reopen-plan",
                    audit_path=receipt["path"], audit_sha256=receipt["sha256"])
                self.assertEqual(["CAP-b"], plan["replacement_order"])
                def fail_after(path, value):
                    atomic_json(path, value)
                    raise OSError("fixture_after_replace")
                with checkpoint.coordinator_lock(run), self.assertRaisesRegex(OSError, "after_replace"):
                    global_audit.execute_reopen(root, run, load_json(run / "run.json"),
                        plan_path=plan["path"], plan_sha256=plan["sha256"], writer=fail_after)
                state = load_json(run / "run.json")
                self.assertEqual(3, state["capability_selection"]["generation"])
                self.assertEqual(1, len(state["capability_selection"]["selected"]))
                selection.verified_prefix(root, run, state)
                with self.assertRaisesRegex(ValueError, "stale_binding"):
                    global_audit.operate(root, run_id="fixture", operation="reopen", plan_path=plan["path"], plan_sha256=plan["sha256"])
                plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                state = load_json(run / "run.json")
                self.assertEqual(39, state["capability_selection"]["total_invocations"])
                self.assertEqual("passed", global_audit.verified_audit(root, run, state)["status"])
                self.assertEqual(immutable, {path: path.read_bytes() for path in immutable})
            with self.subTest(scenario="REOPEN generation-bound apply and free journal replay"):
                with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected paid apply")):
                    self.assertEqual("approved", plan_mvg.review(root, run_id="fixture", runner=Path("unused"), timeout_sec=1)["status"])
                    self.assertTrue(plan_mvg.validate(root, run_id="fixture")["formal_applicable"])
                    applied = plan_mvg.apply(root, run_id="fixture", confirm=True)
                journal = load_json(run / "apply-journal.json")
                evidence = journal["result"]["_mvg_checkpoint_binding"]["evidence"]
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    self.assertIn((run / "candidates" / label / "generation-3/lineage-execution.json").relative_to(root).as_posix(), evidence)
                for path in historical:
                    self.assertIn(path.relative_to(root).as_posix(), evidence)
                dependency = historical[-2]
                before = dependency.read_bytes()
                targets = {root / row["path"]: (root / row["path"]).read_bytes() for row in journal["entries"]}
                try:
                    dependency.write_bytes(before + b"\n ")
                    with self.assertRaisesRegex(ValueError, "journal evidence changed"):
                        plan_mvg.apply(root, run_id="fixture", confirm=True)
                    self.assertEqual(targets, {path: path.read_bytes() for path in targets})
                finally:
                    dependency.write_bytes(before)
                self.assertEqual(applied, plan_mvg.apply(root, run_id="fixture", confirm=True))
                self.assertFalse(applied["runtime_verified"])
                self.assertEqual(39, load_json(run / "run.json")["capability_selection"]["total_invocations"])
        append_fixture.CapabilityAppendTests().exercise_public_generation(coordinator_case="mixed", multi_route=True, on_completed=completed)

    def test_unresolved_resolution_cannot_become_admitted(self):
        context = {"generation": 2, "plan": {"path": "plan.json", "sha256": "sha256:plan"},
            "conflicts": [{"id": "hard-a"}], "replacement_order": ["CAP-a"],
            "resolution_boundaries": {"hard-a": 0}, "resolution_required_conflict_ids": ["hard-a"]}
        for rows in (None, [], [{"conflict_id": "hard-a", "plan_sha256": "sha256:plan", "verdict": "blocked", "rationale": "Source conflict"}],
                     [{"conflict_id": "hard-a", "plan_sha256": "sha256:old", "verdict": "resolved", "rationale": "Changed"}]):
            with self.subTest(rows=rows):
                self.assertTrue(global_audit.reopen_review_errors(context, {"reopen_reviews": rows}))

    def test_audit_recomputes_completion_and_source_gap_verdict(self):
        state = {"global_audit": {"path": "audit.json", "sha256": "sha256:audit"},
                 "capability_selection": {"selected": [], "order": []}}
        for mutation in ("source-gap", "completion", "verdict"):
            with self.subTest(mutation=mutation):
                proposal = {"coverage_table": [{"requirement_id": "R-1", "disposition": "source_gap"}]
                            if mutation == "source-gap" else []}
                receipt = {"schema_version": global_audit.AUDIT_SCHEMA, "binding": {}, "conflict_report": None,
                    "hard_conflicts": [], "resolved_reopened_conflicts": [], "evidence_gaps": [],
                    "status": "blocked" if mutation == "verdict" else "passed", "complete_chain": mutation != "completion"}
                with patch.object(selection, "verified_prefix", return_value=([{}], proposal, [{}])), \
                     patch.object(global_audit, "chain_identity", return_value={}), \
                     patch.object(global_audit, "_artifact", return_value=Path("audit.json")), \
                     patch.object(global_audit, "load_json", return_value=receipt), \
                     self.assertRaisesRegex(ValueError, "verdict_changed"):
                    global_audit.verified_audit(Path("."), Path("."), state)


if __name__ == "__main__":
    unittest.main()
