"""Offline public completion, retained-prefix reopen and authority-safe replay."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_mvg
import _mvg_global_audit as audit
from _mvg_planning_completion import FIELD, bound_report, build_report
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, text_sha
import _mvg_planning_boundary as boundary
from _project_health_mvg_versions import attach_planning_routes, with_runtime_evidence
from scripts.python.tests import test_mvg_capability_append as append_fixture
from scripts.python.tests import test_mvg_global_audit as audit_fixture
from scripts.python.tests import test_mvg_requirement_accounting as accounting_fixture


class PlanningCompletionTests(unittest.TestCase):
    def test_public_complete_blocked_obligations_reopen_and_journal_matrix(self):
        def completed(root, run):
            state = load_json(run / "run.json")
            proposal = load_json(run / "proposal.json")
            report = load_json(run / "validation.json")[FIELD]
            self.assertTrue(report["planning_complete"])
            self.assertEqual("complete", report["status"])
            self.assertTrue(report["passed_items"])
            self.assertEqual([], report["hard_conflicts"])
            self.assertEqual([], report["evidence_gaps"])
            self.assertEqual(2, len(report["obligations"]["tests"]))
            self.assertEqual(2, report["requirement_accounting"]["accounted_count"])
            self.assertEqual(0, report["requirement_accounting"]["satisfied_count"])
            self.assertEqual("not_verified", report["runtime_acceptance"]["status"])
            index_path = run / "analysis-input/analysis-index.json"
            for target in (run / "run.json", index_path):
                with self.subTest(protocol_deleted_from=target.name):
                    original = target.read_bytes()
                    changed = load_json(target)
                    changed.pop("planning_completion_protocol")
                    atomic_json(target, changed)
                    try:
                        with self.assertRaisesRegex(ValueError, "checkpoint protocol changed|analysis identity changed"):
                            plan_mvg.validate(root, run_id="fixture")
                    finally:
                        target.write_bytes(original)
            with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected paid validation")):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(0, plan_mvg.main(["--repo-root", str(root), "validate", "--run-id", "fixture"]))
                self.assertEqual(report, json.loads(output.getvalue())[FIELD])
            audit_path = run / state["global_audit"]["path"]
            original_audit = audit_path.read_bytes()
            original_proposal = (run / "proposal.json").read_bytes()
            for case in ("stale-audit", "source-gap"):
                with self.subTest(blocked=case):
                    if case == "stale-audit":
                        audit_path.write_bytes(original_audit + b" ")
                    else:
                        changed = deepcopy(proposal)
                        changed["coverage_table"][0]["disposition"] = "source_gap"
                        changed["requirement_verification"][0]["disposition"] = "source_gap"
                        atomic_json(run / "proposal.json", changed)
                    try:
                        blocked = plan_mvg.validate(root, run_id="fixture")[FIELD]
                        self.assertFalse(blocked["planning_complete"])
                        self.assertTrue(blocked["evidence_gaps"])
                        with self.assertRaises(ValueError):
                            plan_mvg.apply(root, run_id="fixture", confirm=True)
                        self.assertFalse((run / "apply-journal.json").exists())
                    finally:
                        audit_path.write_bytes(original_audit)
                        (run / "proposal.json").write_bytes(original_proposal)
                        atomic_json(run / "run.json", state)
            # Reopen only the later Capability: the early generation-1 prefix
            # remains selected while generation 2 supplies its replacement.
            owner = audit_fixture.GlobalAuditTests()
            conflict = owner.audit_report(root, run, owner.report(run, capability="CAP-b", flow="flow-b"))
            blocked = plan_mvg.validate(root, run_id="fixture")[FIELD]
            self.assertFalse(blocked["planning_complete"])
            self.assertEqual(1, len(blocked["hard_conflicts"]))
            self.assertIn("selected_prefix", blocked["passed_items"])
            self.assertIn("proposal_validation", blocked["passed_items"])
            self.assertEqual("validation-blocked", load_json(run / "run.json")["phase"])
            plan = audit.operate(root, run_id="fixture", operation="reopen-plan",
                audit_path=conflict["path"], audit_sha256=conflict["sha256"])
            self.assertEqual(["CAP-b"], plan["replacement_order"])
            audit.operate(root, run_id="fixture", operation="reopen", plan_path=plan["path"], plan_sha256=plan["sha256"])
            unresolved = audit.operate(root, run_id="fixture", operation="audit")
            self.assertTrue(unresolved["evidence_gaps"])
            self.assertFalse(plan_mvg.validate(root, run_id="fixture")[FIELD]["planning_complete"])
            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
            plan_mvg.review(root, run_id="fixture", runner=Path("unused"), timeout_sec=1)
            validated = plan_mvg.validate(root, run_id="fixture")
            self.assertTrue(validated[FIELD]["planning_complete"])
            current = load_json(run / "run.json")
            generations = [step["admissions"][step["selected_candidate"]].get("generation", 1)
                           for step in current["capability_selection"]["selected"]]
            self.assertEqual([1, 2], generations)
            with patch("_planning_apply_journal.resume_journal", side_effect=SystemExit("Stop before output writers")), \
                 self.assertRaisesRegex(SystemExit, "before output"):
                plan_mvg.apply(root, run_id="fixture", confirm=True)
            journal = load_json(run / "apply-journal.json")
            expected_targets = {root / row["path"]: (root / row["path"]).read_bytes() if (root / row["path"]).is_file() else None
                                for row in journal["entries"]}
            protected = [".taskmaster/tasks/tasks.json", "docs/gdd/protected.md", "Game.Core/Contracts/Protected.cs",
                         "Game.Core.Tests/ProtectedTests.cs", "Game.Godot/protected.tscn",
                         "logs/ci/mvg-acceptance/protected/summary.json"]
            for ref in protected:
                target = root / ref
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"Protected authority bytes")
            protected_before = {root / ref: (root / ref).read_bytes() for ref in protected}
            for ref in protected:
                with self.subTest(journal_target=ref):
                    illegal = deepcopy(journal)
                    illegal["entries"][0]["path"] = ref
                    atomic_json(run / "apply-journal.json", illegal)
                    with patch("_planning_apply_journal.resume_journal", side_effect=AssertionError("Writer reached")), \
                         self.assertRaisesRegex(ValueError, "planning_write_boundary"):
                        plan_mvg.apply(root, run_id="fixture", confirm=True)
                    self.assertEqual(protected_before, {path: path.read_bytes() for path in protected_before})
                    self.assertEqual(expected_targets, {path: path.read_bytes() if path.is_file() else None for path in expected_targets})
            for changed in (None, [], {}, {"entries": None}, {"entries": [None, None]}):
                with self.subTest(malformed_journal=changed):
                    atomic_json(run / "apply-journal.json", changed)
                    with self.assertRaises(ValueError):
                        plan_mvg.apply(root, run_id="fixture", confirm=True)
            self.assertTrue(list((root / "logs/ci/mvg-planning-rejections").glob("*.json")))
            atomic_json(run / "apply-journal.json", journal)
            # Freeze dependencies include the actual later-generation lineage
            # and the earlier retained prefix, final audit and reopen history.
            evidence = journal["result"]["_mvg_checkpoint_binding"]["evidence"]
            self.assertTrue(any("generation-2/lineage-execution.json" in key for key in evidence))
            dependency = run / current["global_audit"]["path"]
            self.assertIn(dependency.relative_to(root).as_posix(), evidence)
            self.assertTrue(any("reopen-history" in key for key in evidence))
            before = dependency.read_bytes()
            dependency.write_bytes(before + b" ")
            try:
                with self.assertRaisesRegex(ValueError, "journal evidence changed"):
                    plan_mvg.apply(root, run_id="fixture", confirm=True)
            finally:
                dependency.write_bytes(before)
            changed = deepcopy(current)
            changed["global_conflict_report"] = {"path": "new-conflict.json", "sha256": "sha256:new"}
            atomic_json(run / "run.json", changed)
            try:
                with self.assertRaisesRegex(ValueError, "journal binding changed"):
                    plan_mvg.apply(root, run_id="fixture", confirm=True)
            finally:
                atomic_json(run / "run.json", current)
            manifest_path = root / current["manifest_path"]
            def stop_after_manifest(path, value):
                atomic_json(path, value)
                if path == manifest_path:
                    raise OSError("Interrupted after valid manifest after-image")
            with patch.object(plan_mvg, "atomic_json", side_effect=stop_after_manifest), \
                 self.assertRaisesRegex(OSError, "after-image"):
                plan_mvg.apply(root, run_id="fixture", confirm=True)
            self.assertEqual("pending", load_json(run / "apply-journal.json")["status"])
            with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected paid recovery")):
                applied = plan_mvg.apply(root, run_id="fixture", confirm=True)
                self.assertEqual(applied, plan_mvg.apply(root, run_id="fixture", confirm=True))
            self.assertTrue(applied["planning_complete"])
            self.assertFalse(applied["runtime_verified"])
            trace = load_json(root / applied["trace_path"])
            manifest = load_json(manifest_path)
            self.assertEqual(validated[FIELD], applied[FIELD])
            self.assertEqual(applied[FIELD], bound_report(trace, manifest, current["manifest_path"]))
            self.knowledge_checks(root, run, applied, trace, manifest)
            self.assertEqual(protected_before, {path: path.read_bytes() for path in protected_before})
        append_fixture.CapabilityAppendTests().exercise_public_generation(planned_verification=True, coordinator_case="mixed",
            multi_route=True, on_completed=completed)

    def knowledge_checks(self, root, run, applied, trace, manifest):
        item = {"path": applied["manifest_path"], "sha256": applied["manifest_sha256"]}
        self.assertTrue(attach_planning_routes(item, trace, {"kind": "formal_planning_trace"},
            requirement_ids={"FR-a", "FR-b"}, applied_manifest=manifest,
            read_source=lambda ref: (root / ref).read_bytes()))
        self.assertEqual(applied[FIELD], item[FIELD])
        historical = deepcopy(trace)
        historical.pop(FIELD)
        self.assertIsNone(bound_report(historical, manifest, item["path"])["planning_complete"])
        stale = deepcopy(trace)
        stale["notes"] = ["Changed after the audit"]
        self.assertEqual("unavailable", bound_report(stale, manifest, item["path"])["status"])
        for key in ("obligations", "requirement_accounting"):
            changed = deepcopy(trace)
            changed[FIELD][key] = {}
            attached = {"path": item["path"]}
            self.assertTrue(attach_planning_routes(attached, changed, {}, requirement_ids={"FR-a", "FR-b"},
                applied_manifest=manifest, read_source=lambda ref: (root / ref).read_bytes()))
            self.assertEqual("unavailable", attached[FIELD]["status"])
        summary = load_json(run / "apply-summary.json")
        summary["planning_complete"] = False
        atomic_json(run / "apply-summary.json", summary)
        from _project_health_planning import build_result
        clean = {"path": item["path"], "sha256": item["sha256"]}
        def local_result():
            return build_result(root, {"manifest": item["path"], "revision": "fixture", "job_id": "fixture"})
        with patch("_project_health_tasks.task_details", return_value=[]), \
             patch("_semantic_topology.build_topology_view", return_value={}), \
             patch("_project_health_mvg_versions.build_overview", side_effect=lambda *args: {"manifests": [deepcopy(clean)]}):
            result = local_result()
            for path, field in ((run / "run.json", "manifest_path"), (run / "run.json", "applied_manifest_sha256"),
                    (root / applied["trace_path"], "applied_manifest_path"),
                    (root / applied["trace_path"], "applied_manifest_sha256"),
                    (run / "proposal.json", "notes")):
                with self.subTest(local_binding=field):
                    original = path.read_bytes()
                    changed = load_json(path)
                    changed[field] = ["Changed proposal"] if field == "notes" else "changed-binding"
                    atomic_json(path, changed)
                    try:
                        self.assertNotIn(FIELD, local_result()["overview"]["manifests"][0])
                    finally:
                        path.write_bytes(original)
            manifest_path = root / item["path"]
            original = manifest_path.read_bytes()
            changed = deepcopy(manifest)
            changed["mvg_id"] = "changed-manifest"
            atomic_json(manifest_path, changed)
            try:
                self.assertNotIn(FIELD, local_result()["overview"]["manifests"][0])
            finally:
                manifest_path.write_bytes(original)
        self.assertTrue(result["overview"]["manifests"][0][FIELD]["planning_complete"])
        overview = {"revision": "fixture-main", "manifests": [item]}
        self.assertEqual("not_verified", with_runtime_evidence(overview, root)["manifests"][0]["evidence"]["status"])
        runtime = {"mode": "run", "status": "passed", "runtime_verified": True,
            "manifest": item["path"], "manifest_sha256": item["sha256"],
            "source_revision": "fixture-main", "base_commit": "fixture-main", "run_id": "formal-fixture"}
        atomic_json(root / "logs/ci/mvg-acceptance/formal-fixture/summary.json", runtime)
        self.assertEqual("passed", with_runtime_evidence(overview, root)["manifests"][0]["evidence"]["status"])

    def test_historical_trace_without_report_never_infers_completion(self):
        self.assertEqual("unavailable", bound_report({"planning_complete": True}, {}, "docs/testing/mvg/old.json")["status"])

    def evidence_report_fixture(self, root):
        proposal = accounting_fixture.proposal()
        prepared = accounting_fixture.RequirementAccountingTests().prepared(root, proposal)
        run = root / "logs/ci/mvg-planning/evidence"
        run.mkdir(parents=True)
        prepared.rename(run / "analysis-input")
        state = {"run_id": "evidence", "analysis_identity_sha256": "sha256:" + "1" * 64,
            "generation_strategy": "capability-local-selection.v1", "manifest_path": "docs/testing/mvg/evidence.json",
            "capability_selection": {"selected": [], "accepted_sha256": canonical_sha(proposal), "total_invocations": 0,
                "lineage_invocations": {}, "checkpoint_head": None}}
        machine = {"schema_version": audit.AUDIT_SCHEMA, "binding": audit.chain_identity(run, state),
            "status": "passed", "complete_chain": True, "conflict_report": None,
            "hard_conflicts": [], "evidence_gaps": [], "resolved_reopened_conflicts": [], "ordinary_overlaps": [],
            "passed_checks": ["selected_prefix", "frozen_sources", "invocation_accounting"],
            "planned_obligations": {"tests": [], "entrypoints": [], "manual": []},
            "runtime_verified": False, "claim": "Verified offline unit fixture"}
        pointer = run / "global-audits" / (canonical_sha(machine)[7:] + ".json")
        atomic_json(pointer, machine)
        state["global_audit"] = {"path": pointer.relative_to(run).as_posix(), "sha256": file_sha(pointer)}
        validation = {"status": "passed", "formal_applicable": True, "delta_status": "passed"}
        manifest = proposal["manifest_candidate"]
        report = build_report(root, run, state, proposal, validation, machine, manifest)
        trace = deepcopy(proposal)
        trace.update(accounting_fixture.freeze_accounting_sources(proposal, run / "analysis-input"))
        trace[FIELD] = report
        return run, state, proposal, validation, machine, manifest, trace

    def test_positive_evidence_and_missing_or_drifted_source_downgrade_knowledge(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, state, _, _, _, manifest, trace = self.evidence_report_fixture(root)
            self.assertEqual(1, bound_report(trace, manifest, state["manifest_path"])["requirement_accounting"]["satisfied_count"])
            def attached():
                item = {"path": state["manifest_path"]}
                attach_planning_routes(item, trace, {}, requirement_ids={"RQ-1"}, applied_manifest=manifest,
                    read_source=lambda ref: (root / ref).read_bytes())
                return item
            self.assertTrue(attached()[FIELD]["planning_complete"])
            path = root / "docs/testing/proof.md"
            before = path.read_bytes()
            for case in ("removed", "drifted"):
                with self.subTest(evidence=case):
                    if case == "removed":
                        path.unlink()
                    else:
                        path.write_bytes(b"Changed source evidence")
                    item = attached()
                    self.assertEqual("unavailable", item[FIELD]["status"])
                    self.assertEqual(0, item["requirement_accounting"]["satisfied_count"])
                    self.assertTrue(item["requirement_accounting"]["evidence_errors"])
                    path.write_bytes(before)

    def test_rehashed_incomplete_or_inconsistent_reports_are_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, state, _, _, _, manifest, trace = self.evidence_report_fixture(root)
            mutations = {
                "missing_passed": lambda row: row.pop("passed_items"),
                "false_passed": lambda row: row.update(passed_items=["invented_pass"]),
                "missing_obligations": lambda row: row.pop("obligations"),
                "false_obligations": lambda row: row["obligations"].update(tests=["invented-test"]),
                "missing_accounting": lambda row: row.pop("requirement_accounting"),
                "false_accounting": lambda row: row["requirement_accounting"].update(satisfied_count=0),
                "bool_accounting": lambda row: row["requirement_accounting"].update(evidence_count=True),
                "missing_conflicts": lambda row: row.pop("hard_conflicts"),
                "wrong_gaps": lambda row: row.update(evidence_gaps={}),
                "missing_runtime": lambda row: row.pop("runtime_acceptance"),
                "wrong_runtime": lambda row: row["runtime_acceptance"].update(runtime_verified=True),
                "missing_audit_schema": lambda row: row["final_machine_audit"].pop("schema_version"),
                "wrong_audit_schema": lambda row: row["final_machine_audit"].update(schema_version="wrong"),
                "missing_audit_ref": lambda row: row["binding"].pop("audit_ref"),
                "wrong_audit_path": lambda row: row["binding"]["audit_ref"].update(path="global-audits/wrong.json"),
                "wrong_audit_hash": lambda row: row["binding"]["audit_ref"].update(sha256="sha256:" + "0" * 64),
            }
            for name, mutate in mutations.items():
                with self.subTest(report=name):
                    changed = deepcopy(trace)
                    report = changed[FIELD]
                    mutate(report)
                    if name in {"missing_audit_schema", "wrong_audit_schema"}:
                        machine = report["final_machine_audit"]
                        report["binding"]["audit_ref"] = {"path": "global-audits/" + canonical_sha(machine)[7:] + ".json",
                            "sha256": text_sha(json.dumps(machine, ensure_ascii=False, indent=2) + "\n")}
                    report["report_sha256"] = canonical_sha({key: value for key, value in report.items() if key != "report_sha256"})
                    self.assertEqual("unavailable", bound_report(changed, manifest, state["manifest_path"])["status"])

    def test_broken_chain_reports_block_and_preserve_known_checks_and_proposal_obligations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run, state, proposal, validation, _, manifest, _ = self.evidence_report_fixture(root)
            proposal["entrypoints"] = [{"path": "Game.Core/Planned.cs", "status": "planned"}]
            for missing in ("accepted_sha256", "selected"):
                changed = deepcopy(state)
                changed["capability_selection"].pop(missing)
                report = build_report(root, run, changed, proposal, validation, None, manifest)
                self.assertFalse(report["planning_complete"])
                self.assertIsNone(report["binding"]["chain"])
                self.assertTrue(any(row["code"] == "selected_chain_identity_unavailable" for row in report["evidence_gaps"]))
                self.assertIn("proposal_validation", report["passed_items"])
                self.assertNotIn("all_capability_admissions", report["passed_items"])
                self.assertEqual(["Game.Core/Planned.cs"], report["obligations"]["entrypoints"])
                self.assertEqual("proposal_only_unverified", report["obligations_binding"])

    def test_run_scan_tolerates_disappearing_temporary_and_load_scans_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "logs/ci/mvg-planning/fixture"
            atomic_json(run / "run.json", {"schema_version": plan_mvg.RUN_SCHEMA, "run_id": "fixture",
                "manifest_path": "docs/testing/mvg/fixture.json"})
            for index in range(40):
                atomic_json(run / "evidence" / str(index) / "receipt.json", {"index": index})
            original_scan = boundary._scan_run_artifacts
            with patch.object(boundary, "_scan_run_artifacts", wraps=original_scan) as scan:
                plan_mvg._load_run(root, "fixture")
                scan.assert_called_once_with(run)
            vanished = SimpleNamespace(stat=lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("Atomic temporary removed")))
            with patch.object(boundary.os, "scandir") as scandir:
                scandir.return_value.__enter__.return_value = iter([vanished])
                self.assertEqual(run, boundary.safe_run_dir(root, "fixture"))
            omitted_links = SimpleNamespace(path=str(run / "vanished.tmp"),
                stat=lambda **kwargs: SimpleNamespace(st_file_attributes=0, st_nlink=0),
                is_symlink=lambda: False, is_dir=lambda **kwargs: False)
            with patch.object(boundary.os, "scandir") as scandir:
                scandir.return_value.__enter__.return_value = iter([omitted_links])
                self.assertEqual(run, boundary.safe_run_dir(root, "fixture"))
            protected = root / "protected.json"
            protected.write_bytes(b"Protected hardlink target")
            linked = run / "linked.json"
            linked.hardlink_to(protected)
            with self.assertRaisesRegex(ValueError, "aliased_run_artifact"):
                boundary.safe_run_dir(root, "fixture")
            self.assertEqual(b"Protected hardlink target", protected.read_bytes())


if __name__ == "__main__":
    unittest.main()
