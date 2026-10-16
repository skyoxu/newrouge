"""Frozen MVG input identity and zero-dispatch admission regressions."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_mvg as mvg
from _mvg_capability_generation import complete_scope_context, generate_append
from _mvg_input_envelope import _acceptance_refs
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, normalized_file_sha
from chapter5_semantic_reconciliation import DEFAULT_EXTRACTION_SNAPSHOT
from planning_acceptance_fixture import build_fixture, GDD_PATH, TEST_PATH, CONTRACT_PATH


class InputEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fixture"
        build_fixture(self.root)
        semantics = load_json(self.root / mvg.SEMANTICS)
        self.capabilities = self.root / "docs/planning/semantic-topology/capabilities.v1.json"
        atomic_json(self.capabilities, {
            "schema_version": "newrouge.capabilities.v1",
            "source_revision": semantics["source_revision"],
            "capabilities": [{"capability_id": f"CAP-{i}", "requirement_ids": [row["requirement_id"]],
                              "source_block_ids": row["source_block_ids"]}
                             for i, row in enumerate(semantics["requirements"], 1)]})
        self.run = self.root / mvg.DEFAULT_RUN_ROOT / "envelope"

    def prepare(self, **options):
        args = dict(run_id="envelope", capabilities_path=self.capabilities, task_ids=["7", "42"],
                    manifest_path=self.root / "docs/testing/mvg/envelope.json", allow_unready=False)
        args.update(options)
        return mvg.prepare(self.root, **args)

    def test_order_snapshot_inventory_and_explicit_absent_predecessor(self):
        state = self.prepare()
        index = load_json(self.run / "analysis-input/analysis-index.json")
        envelope = index["input_envelope"]
        self.assertEqual("envelope", envelope["run_id"])
        self.assertEqual(["CAP-1", "CAP-2"], [row["capability_id"] for row in envelope["capability_order"]])
        self.assertEqual([0, 1], [row["source_index"] for row in envelope["capability_order"]])
        self.assertEqual("absent", envelope["predecessor"]["status"])
        for row in envelope["chapter5"]["tasks"]:
            self.assertIn("input_fingerprint", row)
            self.assertIn("cache_key", row)
            for kind in ("readiness", "reconciliation"):
                bound = row[kind]
                self.assertEqual(bound["sha256"], file_sha(self.run / "analysis-input" / bound["prepared_path"]))
        required = {row["path"] for row in envelope["inventory"] if row["required"]}
        self.assertIn(GDD_PATH.as_posix(), required)
        self.assertIn(DEFAULT_EXTRACTION_SNAPSHOT.as_posix(), required)
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_model_excluded_readiness_still_blocks_global_generation_on_drift(self):
        state = self.prepare()
        prepared = self.run / "analysis-input"
        views = load_json(prepared / "task-views/tasks_gameplay.json")
        requirement = next(row for row in views if row["taskmaster_id"] == 7)["semantic_refs"][0]
        scope = {"capability": {}, "requirement_ids": [requirement], "cumulative_requirement_ids": [requirement]}
        base = {"manifest_candidate": {"flows": []}, "coverage_table": [], "entrypoints": [], "tests": []}
        context = complete_scope_context(prepared, scope, base)
        self.assertEqual(["7"], context["evidence_selection"]["model_task_ids"])
        self.assertEqual({"7", "42"}, set(context["evidence_selection"]["global_task_ids"]))
        excluded = next(task for task in load_json(prepared / "analysis-index.json")["input_envelope"]["chapter5"]["tasks"]
                        if task["task_id"] == "42")
        self.assertNotIn(excluded["readiness"]["path"], {row["path"] for row in context["evidence"]})
        (prepared / excluded["readiness"]["prepared_path"]).write_text("{}", encoding="utf-8")
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "MVG input drift"):
            generate_append(self.root, state, self.run, invoke_factory=invoke,
                            before_call=lambda phase: None, checkpoint=lambda ledger: None)
        invoke.assert_not_called()

    def test_run_budget_default_and_explicit_are_frozen_with_source(self):
        state = self.prepare()
        index = load_json(self.run / "analysis-input/analysis-index.json")
        for bound in (state, index, index["input_envelope"]):
            self.assertEqual(192, bound["mvg.run_invocation_limit"])
            self.assertEqual("default", bound["mvg.run_invocation_limit_source"])
        state["mvg.run_invocation_limit"] = 193
        with self.assertRaisesRegex(ValueError, "run:mvg.run_invocation_limit"):
            mvg._validate_input_freshness(self.root, self.run, state)
        explicit = self.prepare(run_id="explicit", run_invocation_limit=9)
        self.assertEqual(9, explicit["mvg.run_invocation_limit"])
        self.assertEqual("explicit", explicit["mvg.run_invocation_limit_source"])

    def test_invalid_run_budgets_are_rejected_before_preparation(self):
        for limit in (0, -1, True, False, 1.5, "8"):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "mvg_run_invocation_limit_invalid"):
                    self.prepare(run_invocation_limit=limit)
                self.assertFalse((self.run / "run.json").exists())

    def test_budget_binding_rejects_source_deletion_and_one_sided_drift(self):
        from copy import deepcopy
        state = self.prepare()
        path = self.run / "analysis-input/analysis-index.json"
        index = load_json(path)
        for owner in ("state", "index", "envelope"):
            for key in ("mvg.run_invocation_limit", "mvg.run_invocation_limit_source"):
                for deletion in (True, False):
                    changed, altered = deepcopy(state), deepcopy(index)
                    target = changed if owner == "state" else altered if owner == "index" else altered["input_envelope"]
                    if deletion:
                        target.pop(key)
                    else:
                        target[key] = 193 if key.endswith("limit") else "modified-source"
                    atomic_json(path, altered)
                    with self.subTest(owner=owner, key=key, deletion=deletion):
                        with self.assertRaisesRegex(ValueError, "MVG input drift"):
                            mvg._validate_input_freshness(self.root, self.run, changed)
        atomic_json(path, index)

    def test_final_preflight_rejects_invalid_schema_and_unexpected_batches(self):
        from _mvg_capability_generation import preflight_dispatch
        workspace = self.root / "logs/preflight-invalid"
        workspace.mkdir(parents=True)
        prompt = workspace / "prompt.txt"
        prompt.write_text("Return JSON", encoding="utf-8")
        schema = workspace / "output-schema.json"
        atomic_json(schema, {"type": "not-a-json-schema-type"})
        args = dict(workspace=workspace, prompt_path=prompt, output_path=workspace / "output.json",
                    output_schema=schema, timeout_sec=1)
        with self.assertRaisesRegex(ValueError, "runner_output_schema_preparation_invalid"):
            preflight_dispatch(Path("codex_isolated_model_runner.py"), **args)
        atomic_json(schema, {"type": "object"})
        atomic_json(workspace / "analysis-input/model-batches/batch-index.json", {})
        for runner in ("codex", "openai", "copilot"):
            with self.subTest(runner=runner), self.assertRaisesRegex(ValueError, "mvg_runner_batched_input_unsupported"):
                preflight_dispatch(Path(runner + "_isolated_model_runner.py"), **args)

    def test_final_codex_preflight_uses_complete_sandbox_without_dispatch(self):
        from _mvg_capability_generation import preflight_dispatch
        import codex_isolated_model_runner as codex
        workspace = self.root / "logs/final-sandbox"
        workspace.mkdir(parents=True)
        prompt = workspace / "prompt.txt"
        prompt.write_text("Return JSON", encoding="utf-8")
        schema = workspace / "output-schema.json"
        atomic_json(schema, {"type": "object"})
        runner = Path("codex_isolated_model_runner.py")
        with patch.object(codex, "_codex_executable", return_value="fixture-codex") as available, \
             patch.object(codex.subprocess, "run") as dispatch:
            preflight_dispatch(runner, workspace=workspace, prompt_path=prompt,
                output_path=workspace / "output.json", output_schema=schema, timeout_sec=1)
            available.assert_called_once()
            dispatch.assert_not_called()
        (workspace / "late-copy.txt").write_text("Complete late evidence line.\n" * 35_000, encoding="utf-8")
        with patch.object(codex, "_codex_executable", return_value="fixture-codex"), \
             patch.object(codex.subprocess, "run") as dispatch:
            with self.assertRaisesRegex(ValueError, "too_large|budget_exceeded"):
                preflight_dispatch(runner, workspace=workspace, prompt_path=prompt,
                    output_path=workspace / "output.json", output_schema=schema, timeout_sec=1)
            dispatch.assert_not_called()

    def test_concurrent_generate_rejects_second_coordinator_before_dispatch(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self.prepare()
        entered, release = threading.Event(), threading.Event()
        def execute(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("fixture_coordinator_wait_expired")
            return {"status": "fixture-completed"}
        with patch.object(mvg, "_generate", side_effect=execute) as dispatch, \
             ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(mvg.generate, self.root, run_id="envelope", timeout_sec=1,
                                    llm_backend="codex-cli")
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaisesRegex(ValueError, "capability_coordinator_busy"):
                    mvg.generate(self.root, run_id="envelope", timeout_sec=1, llm_backend="codex-cli")
            finally:
                release.set()
            self.assertEqual("fixture-completed", first.result()["status"])
            self.assertEqual(1, dispatch.call_count)

    def test_legacy_run_keeps_historical_freshness_validation(self):
        legacy = self.root / mvg.DEFAULT_RUN_ROOT / "legacy"
        prepared = legacy / "analysis-input"
        prepared.mkdir(parents=True)
        source = self.root / GDD_PATH
        copied = prepared / "gdd.md"
        copied.write_bytes(source.read_bytes())
        index = {
            "files": {"gdd.md": file_sha(copied)},
            "authority_inputs": {GDD_PATH.as_posix(): normalized_file_sha(source)},
        }
        index["analysis_identity_sha256"] = canonical_sha(index)
        atomic_json(prepared / "analysis-index.json", index)
        state = {"schema_version": mvg.RUN_SCHEMA,
                 "analysis_identity_sha256": index["analysis_identity_sha256"]}
        mvg._validate_input_freshness(self.root, legacy, state)
        source.write_text(source.read_text(encoding="utf-8") + "\nlegacy drift\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "MVG input drift"):
                mvg._validate_input_freshness(self.root, legacy, state)
        finally:
            source.write_bytes(copied.read_bytes())

    def test_checkpoint_protocol_is_frozen_before_any_model_dispatch(self):
        from copy import deepcopy
        state = self.prepare()
        self.assertEqual('capability-selected-checkpoint.v1', state['checkpoint_strategy'])
        self.assertEqual('newrouge.mvg-capability-checkpoint.v1', state['checkpoint_schema_version'])
        for key in ('checkpoint_strategy', 'checkpoint_schema_version'):
            for value in (None, 'unknown-protocol'):
                with self.subTest(key=key, value=value):
                    changed = deepcopy(state)
                    if value is None:
                        changed.pop(key)
                    else:
                        changed[key] = value
                    atomic_json(self.run / 'run.json', changed)
                    with patch.object(mvg, 'run_isolated_model') as dispatch:
                        with self.assertRaisesRegex(ValueError, 'checkpoint protocol changed'):
                            mvg.generate(self.root, run_id='envelope', timeout_sec=1, llm_backend='codex-cli')
                        dispatch.assert_not_called()
                    from _mvg_input_envelope import validate_envelope
                    with self.assertRaisesRegex(ValueError, 'run:' + key):
                        validate_envelope(self.root, self.run / 'analysis-input', changed)
        atomic_json(self.run / 'run.json', state)
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_requirement_route_protocol_state_is_bound_before_dispatch(self):
        from copy import deepcopy
        state = self.prepare()
        for value in (None, 'unknown-protocol'):
            changed = deepcopy(state)
            changed['requirement_routes_protocol'] = value
            atomic_json(self.run / 'run.json', changed)
            with patch.object(mvg, 'run_isolated_model') as dispatch:
                with self.assertRaisesRegex(ValueError, 'run:requirement_routes_protocol'):
                    mvg.generate(self.root, run_id='envelope', timeout_sec=1, llm_backend='codex-cli')
                dispatch.assert_not_called()

    def test_busy_incremental_generator_cannot_write_run_or_dispatch(self):
        from _mvg_capability_checkpoint import coordinator_lock
        self.prepare()
        before = (self.run / 'run.json').read_bytes()
        with coordinator_lock(self.run), patch.object(mvg, 'run_isolated_model') as dispatch, \
             patch.object(mvg, 'atomic_json') as writer:
            with self.assertRaisesRegex(ValueError, 'capability_coordinator_busy'):
                mvg.generate(self.root, run_id='envelope', timeout_sec=1, llm_backend='codex-cli')
            dispatch.assert_not_called()
            writer.assert_not_called()
        self.assertEqual(before, (self.run / 'run.json').read_bytes())

    def test_existing_predecessor_content_and_planned_reference_classification(self):
        dest = self.root / "docs/testing/mvg/envelope.json"
        baseline = {"flows": [{"id": "relay", "task_ids": [7, 42], "source_paths": [GDD_PATH.as_posix()],
                              "handoffs": [{"contract_ref": CONTRACT_PATH.as_posix()}]}],
                    "tests": [{"path": "Game.Core.Tests/Future.cs", "state": "planned"}]}
        atomic_json(dest, baseline)
        self.prepare()
        envelope = load_json(self.run / "analysis-input/analysis-index.json")["input_envelope"]
        self.assertEqual(file_sha(dest), envelope["predecessor"]["sha256"])
        planned = next(row for row in envelope["inventory"] if row["path"] == "Game.Core.Tests/Future.cs")
        self.assertEqual("planned", planned["classification"])
        self.assertFalse(planned["required"])

    def test_missing_required_baseline_dependency_blocks_prepare(self):
        dest = self.root / "docs/testing/mvg/envelope.json"
        atomic_json(dest, {"flows": [], "tests": [{"path": "Game.Core.Tests/Missing.cs", "state": "implemented"}]})
        with self.assertRaisesRegex(ValueError, "Missing.cs"):
            self.prepare()
        self.assertFalse((self.run / "run.json").exists())

    def test_missing_readiness_formal_blocks_but_draft_cannot_generate(self):
        (self.root / "logs/ci/chapter5/readiness/task-7.json").unlink()
        with self.assertRaisesRegex(ValueError, "readiness"):
            self.prepare()
        state = self.prepare(allow_unready=True)
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "readiness|formal"):
            generate_append(self.root, state, self.run, invoke_factory=invoke, before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

    def test_prepare_end_rechecks_early_source_drift(self):
        original = mvg._copy_file
        changed = False
        def drifting_copy(root, source, bundle, rel=None):
            nonlocal changed
            result = original(root, source, bundle, rel)
            if source == root / GDD_PATH and not changed:
                changed = True
                source.write_text(source.read_text(encoding="utf-8") + "\nChanged during prepare.\n", encoding="utf-8")
            return result
        with patch.object(mvg, "_copy_file", side_effect=drifting_copy):
            with self.assertRaisesRegex(ValueError, "drift"):
                self.prepare()
        self.assertFalse((self.run / "run.json").exists())
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(receipt["analysis_identity_sha256"])
        self.assertIn(GDD_PATH.as_posix(), receipt["drift"])
        self.assertFalse(any(item.startswith("prepare:") for item in receipt["drift"]))

    def test_candidate_drift_blocks_before_any_model_dispatch(self):
        state = self.prepare()
        candidate = self.run / "candidate"
        shutil.copytree(self.run / "analysis-input", candidate / "analysis-input")
        target = candidate / "analysis-input/capabilities.v1.json"
        data = load_json(target)
        data["capabilities"].reverse()
        atomic_json(target, data)
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "drift|identity"):
            generate_append(self.root, state, candidate, invoke_factory=invoke, before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()
        self.assertIn("capabilities.v1.json", str(load_json(candidate / "input-freshness.json")))

    def test_prepared_unregistered_file_blocks_before_dispatch(self):
        state = self.prepare()
        candidate = self.run / "candidate"
        shutil.copytree(self.run / "analysis-input", candidate / "analysis-input")
        injected = candidate / "analysis-input/references/injected.md"
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.write_text("unbound evidence", encoding="utf-8")
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "extra-file|unregistered"):
            generate_append(self.root, state, candidate, invoke_factory=invoke,
                            before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()
        receipt = load_json(candidate / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(any("injected.md" in item for item in receipt["drift"]))

    def test_frozen_formal_ready_mismatch_blocks_before_dispatch(self):
        state = self.prepare()
        state["formal_ready"] = False
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "formal_ready"):
            generate_append(self.root, state, self.run, invoke_factory=invoke,
                            before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

    def test_forged_envelope_state_hash_blocks_before_dispatch(self):
        state = self.prepare()
        state["input_envelope_sha256"] = "forged-envelope-hash"
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "input_envelope:sha256"):
            generate_append(self.root, state, self.run, invoke_factory=invoke,
                            before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

    def test_new_run_cannot_fall_back_to_legacy_freshness_when_envelope_is_removed(self):
        state = self.prepare()
        index_path = self.run / "analysis-input/analysis-index.json"
        index = load_json(index_path)
        index.pop("input_envelope", None)
        index["analysis_identity_sha256"] = canonical_sha({
            key: value for key, value in index.items() if key != "analysis_identity_sha256"
        })
        atomic_json(index_path, index)
        state["input_envelope_sha256"] = None
        with self.assertRaisesRegex(ValueError, "input_envelope_missing"):
            mvg._validate_input_freshness(self.root, self.run, state)

    def test_state_scope_and_manifest_identity_drift_blocks_before_dispatch(self):
        state = self.prepare()
        invoke = Mock()
        state["task_scope"] = ["different"]
        with self.assertRaisesRegex(ValueError, "run:task_scope"):
            generate_append(self.root, state, self.run, invoke_factory=invoke,
                            before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

        state = self.prepare(run_id="envelope-2")
        state["manifest_path"] = "docs/testing/mvg/other.json"
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "run:manifest_path"):
            generate_append(self.root, state, self.run.parent / "envelope-2",
                            invoke_factory=invoke, before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

    def test_source_snapshot_and_predecessor_drift_are_persisted(self):
        state = self.prepare()
        for rel in (self.capabilities.relative_to(self.root), DEFAULT_EXTRACTION_SNAPSHOT, TEST_PATH,
                    Path("logs/ci/chapter5/readiness/task-7.json"),
                    Path("logs/ci/chapter5/reconciliation/task-7.json")):
            target = self.root / rel
            before = target.read_bytes()
            target.write_bytes(before + b"\n")
            with self.assertRaisesRegex(ValueError, "drift"):
                mvg._validate_input_freshness(self.root, self.run, state)
            self.assertIn(rel.as_posix(), str(load_json(self.run / "input-freshness.json")))
            target.write_bytes(before)
        atomic_json(self.root / "docs/testing/mvg/envelope.json", {"new": "baseline"})
        with self.assertRaisesRegex(ValueError, "drift"):
            mvg._validate_input_freshness(self.root, self.run, state)

    def test_core_authority_drift_is_persisted(self):
        state = self.prepare()
        target = self.root / mvg.SEMANTICS
        before = target.read_bytes()
        try:
            target.write_bytes(before + b"\n")
            with self.assertRaisesRegex(ValueError, "semantic-requirements"):
                mvg._validate_input_freshness(self.root, self.run, state)
            receipt = load_json(self.run / "input-freshness.json")
            self.assertTrue(any("semantic-requirements" in item for item in receipt["drift"]))
        finally:
            target.write_bytes(before)

    def test_readiness_reconciliation_and_evidence_copy_drift_dispatch_zero_calls(self):
        state = self.prepare(evidence_refs=[TEST_PATH.as_posix()])
        candidate = self.run / "candidate"
        shutil.copytree(self.run / "analysis-input", candidate / "analysis-input")
        for rel in ("references/logs/ci/chapter5/readiness/task-7.json",
                    "references/logs/ci/chapter5/reconciliation/task-7.json",
                    "references/" + TEST_PATH.as_posix()):
            with self.subTest(path=rel):
                target = candidate / "analysis-input" / rel
                before = target.read_bytes()
                target.write_bytes(before + b"\n")
                invoke = Mock()
                with self.assertRaisesRegex(ValueError, "drift"):
                    generate_append(self.root, state, candidate, invoke_factory=invoke,
                                    before_call=Mock(), checkpoint=Mock())
                invoke.assert_not_called()
                self.assertIn(rel, str(load_json(candidate / "input-freshness.json")))
                target.write_bytes(before)

    def test_missing_explicit_evidence_blocks_before_prepared_state(self):
        with self.assertRaisesRegex(ValueError, "Missing.txt"):
            self.prepare(evidence_refs=["docs/Missing.txt"])
        self.assertFalse((self.run / "run.json").exists())
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(any("Missing.txt" in item for item in receipt["drift"]))

    def test_missing_readiness_writes_prepare_blocked_receipt(self):
        (self.root / "logs/ci/chapter5/readiness/task-7.json").unlink()
        with self.assertRaisesRegex(ValueError, "readiness"):
            self.prepare()
        self.assertFalse((self.run / "run.json").exists())
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(any("readiness" in item for item in receipt["drift"]))

    def test_copy_failure_writes_prepare_blocked_receipt_without_run(self):
        with patch.object(mvg, "_copy_file", side_effect=OSError("Fixture copy failed")):
            with self.assertRaisesRegex(OSError, "Fixture copy failed"):
                self.prepare()
        self.assertFalse((self.run / "run.json").exists())
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(any("Fixture copy failed" in item for item in receipt["drift"]))

    def test_prepare_retry_replaces_old_failure_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "missing or invalid"):
            self.prepare(capabilities_path=self.root / "missing.json")
        with patch.object(mvg, "_copy_file", side_effect=OSError("Latest copy failure")):
            with self.assertRaisesRegex(OSError, "Latest copy failure"):
                self.prepare()
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual(["prepare:Latest copy failure"], receipt["drift"])
        self.assertFalse((self.run / "run.json").exists())

    def test_successful_prepare_retry_clears_old_failure_and_existing_run_is_preserved(self):
        with self.assertRaises(ValueError):
            self.prepare(capabilities_path=self.root / "missing.json")
        state = self.prepare()
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("current", receipt["status"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()
        self.assertEqual(state, load_json(self.run / "run.json"))
        self.assertEqual(receipt, load_json(self.run / "input-freshness.json"))

    def test_missing_extensionless_source_ref_is_required(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        views[0]["source_refs"] = ["LICENSE"]
        atomic_json(views_path, views)
        with self.assertRaisesRegex(ValueError, "LICENSE"):
            self.prepare()
        receipt = load_json(self.run / "input-freshness.json")
        self.assertEqual("blocked", receipt["status"])
        self.assertTrue(any("LICENSE" in item for item in receipt["drift"]))

    def test_original_capability_order_drift_dispatch_zero_calls(self):
        state = self.prepare()
        data = load_json(self.capabilities)
        data["capabilities"].reverse()
        atomic_json(self.capabilities, data)
        invoke = Mock()
        with self.assertRaisesRegex(ValueError, "drift"):
            generate_append(self.root, state, self.run, invoke_factory=invoke,
                            before_call=Mock(), checkpoint=Mock())
        invoke.assert_not_called()

    def test_unrelated_git_commit_does_not_change_identity(self):
        state = self.prepare()
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "--allow-empty", "-m", "Unrelated provenance"], cwd=self.root, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_explicit_evidence_and_event_context_keep_distinct_roles(self):
        state = self.prepare(evidence_refs=[TEST_PATH.as_posix()])
        envelope = load_json(self.run / "analysis-input/analysis-index.json")["input_envelope"]
        row = next(row for row in envelope["inventory"] if row["path"] == TEST_PATH.as_posix())
        self.assertTrue(row["required"])
        self.assertIn("explicit_evidence", row["roles"])
        self.assertTrue(any(row["classification"] == "identifier" for row in envelope["inventory"]))

    def test_scope_context_carries_run_and_envelope_identity(self):
        from _mvg_capability_generation import capability_scopes, seed_proposal
        state = self.prepare()
        prepared = self.run / "analysis-input"
        scopes = capability_scopes(load_json(prepared / "capabilities.v1.json"),
                                  load_json(prepared / "semantic-requirements.v1.json"), None)
        context = complete_scope_context(prepared, scopes[0], seed_proposal(state, prepared))
        self.assertEqual("envelope", context["input_identity"]["run_id"])
        self.assertEqual(state["analysis_identity_sha256"], context["input_identity"]["analysis_identity_sha256"])
        self.assertTrue(context["input_identity"]["envelope_sha256"])
        evidence = {row["path"]: row for row in context["evidence"]}
        for rel in ("logs/ci/chapter5/readiness/task-7.json", "logs/ci/chapter5/reconciliation/task-7.json"):
            self.assertEqual((self.root / rel).read_text(encoding="utf-8"), evidence[rel]["text"])
        extraction = DEFAULT_EXTRACTION_SNAPSHOT.as_posix()
        self.assertNotIn(extraction, evidence)
        selection = next(row for row in context["evidence_selection"]["sources"] if row["path"] == extraction)
        self.assertFalse(selection["selected"])
        self.assertEqual("outside_model_dependency_scope", selection["reason"])
        envelope = load_json(prepared / "analysis-index.json")["input_envelope"]
        self.assertEqual(envelope["chapter5"]["extraction"], context["chapter5"]["extraction"])
        self.assertEqual(file_sha(self.root / extraction), context["chapter5"]["extraction"]["sha256"])

    def test_line_addressed_source_ref_resolves_to_prepared_file(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        views[0]["source_refs"] = [GDD_PATH.as_posix() + ":18"]
        atomic_json(views_path, views)
        state = self.prepare()
        prepared = self.run / "analysis-input"
        from _mvg_capability_generation import capability_scopes, seed_proposal
        scopes = capability_scopes(load_json(prepared / "capabilities.v1.json"),
                                  load_json(prepared / "semantic-requirements.v1.json"), None)
        context = complete_scope_context(prepared, scopes[0], seed_proposal(state, prepared))
        evidence = {row["path"]: row for row in context["evidence"]}
        self.assertIn(GDD_PATH.as_posix(), evidence)
        self.assertNotEqual("not_prepared", evidence[GDD_PATH.as_posix()].get("status"))

    def test_identifier_collision_is_not_a_missing_or_new_file_dependency(self):
        state = self.prepare()
        (self.root / "CAP-1").write_text("Unrelated file sharing an identifier", encoding="utf-8")
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_acceptance_refs_support_space_separated_paths(self):
        text = "Done. Refs: Tests.Godot/a.gd Game.Core.Tests/b.cs Game.Core.Tests/c.cs"
        self.assertEqual(["Tests.Godot/a.gd", "Game.Core.Tests/b.cs", "Game.Core.Tests/c.cs"],
                         _acceptance_refs(text))

    def test_acceptance_refs_strip_markdown_punctuation(self):
        text = "Done. Refs: `Tests.Godot/a.gd`, Game.Core.Tests/b.cs."
        self.assertEqual(["Tests.Godot/a.gd", "Game.Core.Tests/b.cs"], _acceptance_refs(text))

    def test_draft_prepare_copies_all_files_around_acceptance_anchor_annotations(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        acceptance = (f"Done. Refs: {TEST_PATH.as_posix()} (anchor: ACC:T7.1) "
                      f"{GDD_PATH.as_posix()} (anchor: ACC:T7.2)")
        views[0]["acceptance"] = [acceptance]
        atomic_json(views_path, views)
        # Changing acceptance intentionally invalidates Chapter 5 readiness.
        # A draft isolates reference transport without granting formal approval.
        state = self.prepare(allow_unready=True)
        self.assertFalse(state["formal_ready"])
        prepared = self.run / "analysis-input"
        index = load_json(prepared / "analysis-index.json")
        rows = {row["path"]: row for row in index["input_envelope"]["inventory"]}
        for ref in (TEST_PATH.as_posix(), GDD_PATH.as_posix()):
            with self.subTest(ref=ref):
                self.assertIn("acceptance_context", rows[ref]["roles"])
                self.assertTrue(rows[ref]["required"])
                self.assertEqual((self.root / ref).read_bytes(),
                                 (prepared / rows[ref]["prepared_path"]).read_bytes())
        self.assertEqual(acceptance, load_json(prepared / "task-views/tasks_gameplay.json")[0]["acceptance"][0])
        self.assertFalse(any("anchor:" in ref or ref.startswith("ACC:") for ref in rows))
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_missing_file_after_acceptance_anchor_still_blocks_preparation(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        views[0]["acceptance"] = [
            f"Done. Refs: {TEST_PATH.as_posix()} (anchor: ACC:T7.1) LICENSE"]
        atomic_json(views_path, views)
        with self.assertRaisesRegex(ValueError, "MVG required input missing:LICENSE"):
            self.prepare(allow_unready=True)
        self.assertFalse((self.run / "run.json").exists())
        self.assertEqual("blocked", load_json(self.run / "input-freshness.json")["status"])

    def test_template_evidence_reference_is_planned_not_required(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        template = "logs/ci/<date>/single-task-light-lane/summary.json"
        views[0]["test_refs"] = [template]
        atomic_json(views_path, views)
        state = self.prepare()
        rows = {row["path"]: row for row in load_json(
            self.run / "analysis-input/analysis-index.json")["input_envelope"]["inventory"]}
        self.assertIn(template, rows)
        self.assertEqual("planned", rows[template]["classification"])
        self.assertFalse(rows[template]["required"])
        self.assertIsNone(rows[template]["sha256"])
        mvg._validate_input_freshness(self.root, self.run, state)

    def test_missing_concrete_log_reference_still_blocks_done_task(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        reference = "logs/ci/2026-10-15/missing/summary.json"
        views[0]["test_refs"] = [reference]
        atomic_json(views_path, views)
        with self.assertRaisesRegex(ValueError, "MVG required input missing:" + reference):
            self.prepare()

    def test_template_source_reference_is_not_downgraded_to_log_example(self):
        views_path = self.root / mvg.TASK_VIEWS[1]
        views = load_json(views_path)
        reference = "logs/ci/<date>/authority.json"
        views[0]["source_refs"] = [reference]
        atomic_json(views_path, views)
        with self.assertRaisesRegex(ValueError, "MVG required input missing:" + reference):
            self.prepare()


class AcceptanceReferenceTests(unittest.TestCase):
    def test_anchor_annotations_do_not_replace_or_hide_file_references(self):
        cases = [
            ("Tests.Godot/a.gd (anchor: ACC:T44.8)", ["Tests.Godot/a.gd"]),
            ("Tests.Godot/a.gd (anchor: ACC:T59.4) Tests.Godot/b.gd (anchor: ACC:T59.4)",
             ["Tests.Godot/a.gd", "Tests.Godot/b.gd"]),
            ("`Tests.Godot/a.gd` (anchor: ACC:T7.1), Game.Core.Tests/b.cs; LICENSE",
             ["Tests.Godot/a.gd", "Game.Core.Tests/b.cs", "LICENSE"]),
            ("Tests.Godot/a.gd#ACC:T7.1 (anchor: ACC:T7.1) docs/design.md:18:2",
             ["Tests.Godot/a.gd#ACC:T7.1", "docs/design.md:18:2"]),
            ("Tests.Godot/a.gd ( Anchor: ACC:T7.1 ) Game.Core.Tests/b.cs.",
             ["Tests.Godot/a.gd", "Game.Core.Tests/b.cs"]),
        ]
        for tail, expected in cases:
            with self.subTest(tail=tail):
                self.assertEqual(expected, _acceptance_refs("Done. Refs: " + tail))

    def test_unrecognized_parenthesized_references_are_not_silently_discarded(self):
        self.assertEqual(["Tests.Godot/a.gd", "(anchor:", "docs/missing.md"],
                         _acceptance_refs("Done. Refs: Tests.Godot/a.gd (anchor: docs/missing.md)"))


if __name__ == "__main__":
    unittest.main()
