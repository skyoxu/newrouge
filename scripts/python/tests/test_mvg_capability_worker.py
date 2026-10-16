"""Independent two-Capability fixtures exercising actual OS worker subprocesses."""
from copy import deepcopy
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chapter5_semantic_reconciliation as chapter5
import planning_acceptance_fixture as fixture
import plan_mvg as pm
import _mvg_capability_recovery as recovery
from _planning_skill_common import atomic_json, file_sha, load_json

RUNNER = Path(__file__).parent / "fixtures/mvg_fake_runner.py"


@contextmanager
def project_directory():
    evidence = os.environ.get("SC_MVG_TEST_EVIDENCE_ROOT")
    if evidence:
        target = Path(evidence).resolve()
        target.mkdir(parents=True, exist_ok=True)
        directory = tempfile.mkdtemp(prefix="worker-fixture-", dir=target)
        print("Offline worker evidence: " + directory, flush=True)
        yield directory
    else:
        with tempfile.TemporaryDirectory() as directory:
            yield directory


def build_project(root):
    fixture.build_fixture(root)
    semantics = load_json(root / pm.SEMANTICS)
    source_views = load_json(root / pm.TASK_VIEWS[1])
    flows, tests, caps, views = [], [], [], []
    refs = [fixture.CONTRACT_PATH.as_posix(), "Game.Core/Runtime.cs", fixture.TEST_PATH.as_posix()]
    for index, req in enumerate(semantics["requirements"]):
        tid = fixture.TASK_IDS[index]
        cid, fid, test_id = "CAP-" + str(tid), "journey-" + str(tid), "verify-" + str(tid)
        caps.append({"capability_id": cid, "requirement_ids": [req["requirement_id"]],
            "description": "Observable relay journey " + str(tid), "source_block_ids": req["source_block_ids"]})
        flows.append({"id": fid, "outcome": "Observe relay state " + str(tid),
            "requirement_ids": [req["requirement_id"]], "capability_refs": [cid], "task_ids": [tid],
            "source_paths": [fixture.GDD_PATH.as_posix()], "test_ids": [test_id], "handoffs": [{
                "producer_task": tid, "consumer_task": tid, "owner_task": tid, "contract_ref": refs[0],
                "behavior": "Observe consumer state", "test_ids": [test_id]}]})
        tests.append({"id": test_id, "kind": "dotnet", "state": "implemented", "path": refs[2],
            "selector": "PlanningAcceptanceTests", "evidence_level": "domain-integration", "min_tests": 1})
        views.append(dict(next(row for row in source_views if row["taskmaster_id"] == tid), capability_refs=[cid]))
    atomic_json(root / "docs/testing/mvg/worker.json", {"schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "worker", "flows": flows, "tests": tests, "coverage": {"mode": "critical", "scope_id": "worker",
            "required_flow_ids": [row["id"] for row in flows], "blocking_task_ids": [],
            "excluded_claims": ["Runtime remains unverified"]}})
    atomic_json(root / "docs/planning/semantic-topology/capabilities.v1.json", {
        "schema_version": "newrouge.capabilities.v1", "capabilities": caps, "source_revision": semantics["source_revision"]})
    for path in pm.TASK_VIEWS:
        atomic_json(root / path, views)
    (root / refs[1]).parent.mkdir(parents=True, exist_ok=True)
    # Evidence already present in the portable fixture stays unchanged.
    atomic_json(root / refs[1], {"runtime": "planned fixture entrypoint"})
    snapshot = load_json(root / chapter5.DEFAULT_EXTRACTION_SNAPSHOT)
    fixture._write_readiness(root, snapshot, semantics,
        {block: req["requirement_id"] for req in semantics["requirements"] for block in req["source_block_ids"]},
        {str(view["taskmaster_id"]): view["semantic_refs"] for view in views})
    return refs


def prepare(root, run_id, refs, **kwargs):
    return pm.prepare(root, run_id=run_id,
        capabilities_path=root / "docs/planning/semantic-topology/capabilities.v1.json",
        manifest_path=root / "docs/testing/mvg/worker.json", task_ids=list(map(str, fixture.TASK_IDS)),
        allow_unready=False, evidence_refs=refs, **kwargs)


class WorkerRecoveryIntegrationTests(unittest.TestCase):
    def test_real_workers_commit_and_new_run_reuses_without_model_dispatch(self):
        with project_directory() as directory, patch.dict(os.environ, {
                "SC_KNOWLEDGE_PLANNING_RUNNER": str(RUNNER.resolve())}):
            root = Path(directory)
            refs = build_project(root)
            prepare(root, "original", refs)
            pm.generate(root, run_id="original", timeout_sec=10, llm_backend="codex-cli")
            run = root / "logs/ci/mvg-planning/original"
            state = load_json(run / "run.json")
            workers = list(run.rglob("process.json"))
            self.assertEqual(6, len(workers))
            self.assertEqual(6, len({load_json(path)["pid"] for path in workers}))
            self.assertNotIn(os.getpid(), {load_json(path)["pid"] for path in workers})
            self.assertEqual(14, state["capability_selection"]["total_invocations"])
            self.assertEqual(2, recovery.progress(root, run, state)["completed"])
            original_proof = file_sha(run / "accepted-chain/admission-review.json")
            # Catalog and unrelated Git identity changes do not affect local keys.
            capabilities_path = root / "docs/planning/semantic-topology/capabilities.v1.json"
            catalog = load_json(capabilities_path)
            catalog["generated_at"] = "unrelated catalog metadata"
            atomic_json(capabilities_path, catalog)
            subprocess.run(["git", "-C", str(root), "commit", "--allow-empty", "-m", "fixture: unrelated revision"],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            prepare(root, "reused", refs, run_invocation_limit=1)
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Reuse must not invoke a model")):
                pm.generate(root, run_id="reused", timeout_sec=10, llm_backend="codex-cli")
            next_run = root / "logs/ci/mvg-planning/reused"
            adopted = load_json(next_run / "run.json")
            self.assertEqual(["adoption", "adoption"], [row["kind"] for row in adopted["capability_selection"]["selected"]])
            self.assertEqual(0, adopted["capability_selection"]["total_invocations"])
            from _mvg_global_audit import verified_audit
            self.assertEqual("passed", verified_audit(root, next_run, adopted)["status"])
            self.assertEqual(original_proof, file_sha(run / "accepted-chain/admission-review.json"))
            from _mvg_capability_selection import verify_published_chain
            verify_published_chain(root, next_run, adopted)
            # Mutated historical proof and current dependency drift both fail
            # before any checkpoint can become visible.
            from _mvg_capability_selection import frozen_scopes
            scopes = frozen_scopes(adopted, next_run / "analysis-input")
            from _mvg_capability_generation import seed_proposal
            base = seed_proposal(adopted, next_run / "analysis-input")
            entry = recovery.registry(root)["entries"][0]
            receipt = run / state["capability_selection"]["selected"][0]["receipt_path"]
            receipt_bytes = receipt.read_text(encoding="utf-8")
            try:
                atomic_json(receipt, {"tampered": True})
                with self.assertRaises(ValueError):
                    recovery.replay(root, next_run, adopted, scopes[0], base, entry)
            finally:
                # Restore only this test-owned disposable fixture artifact.
                receipt.write_text(receipt_bytes, encoding="utf-8", newline="\n")
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Reuse consumers must stay machine-only")):
                self.assertEqual("approved", pm.review(root, run_id="reused", runner=RUNNER.resolve(), timeout_sec=10)["status"])
                result = pm.validate(root, run_id="reused")
                self.assertEqual("passed", result["status"], result)
                self.assertTrue(result["planning_complete"], result)
                self.assertEqual("not_verified", result["planning_completion"]["runtime_acceptance"]["status"])
                applied = pm.apply(root, run_id="reused", confirm=True)
                self.assertEqual("applied", applied["status"])

    def test_interrupted_scope_discards_worker_artifacts_and_busy_progress_is_read_only(self):
        import _mvg_capability_worker as worker
        with project_directory() as directory, patch.dict(os.environ, {
                "SC_KNOWLEDGE_PLANNING_RUNNER": str(RUNNER.resolve())}):
            root = Path(directory)
            refs = build_project(root)
            prepare(root, "interrupted", refs)
            run = root / "logs/ci/mvg-planning/interrupted"
            real_run = worker.run_candidate
            observed = []
            def interrupt(job_dir, data, **kwargs):
                if data["scope_index"] == 1:
                    original_reserve = kwargs["reserve"]
                    def busy_reserve(*args, **keys):
                        reserved = original_reserve(*args, **keys)
                        before = {p: file_sha(p) for p in run.rglob("*.json")}
                        projection = recovery.progress(root, run, load_json(run / "run.json"))
                        after = {p: file_sha(p) for p in run.rglob("*.json")}
                        self.assertEqual(before, after, "GET projection must never repair a budget journal")
                        self.assertEqual(1, projection["completed"])
                        self.assertFalse(projection["runtime_verified"])
                        observed.append(projection)
                        return reserved
                    kwargs["reserve"] = busy_reserve
                    real_run(job_dir, data, **kwargs)
                    raise KeyboardInterrupt("Fixture interruption after unfinished B candidate")
                return real_run(job_dir, data, **kwargs)
            with patch.object(worker, "run_candidate", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
                pm.generate(root, run_id="interrupted", timeout_sec=10, llm_backend="codex-cli")
            self.assertTrue(observed)
            interrupted = load_json(run / "run.json")
            self.assertEqual(1, len(interrupted["capability_selection"]["selected"]))
            self.assertEqual(9, interrupted["capability_selection"]["total_invocations"])
            self.assertEqual(1, recovery.progress(root, run, interrupted)["completed"])
            catalog_path = root / "docs/planning/semantic-topology/capabilities.v1.json"
            catalog = load_json(catalog_path)
            catalog["capabilities"][1]["description"] += " changed individual content"
            atomic_json(catalog_path, catalog)
            prepare(root, "next", refs)
            pm.generate(root, run_id="next", timeout_sec=10, llm_backend="codex-cli")
            next_run = root / "logs/ci/mvg-planning/next"
            state = load_json(next_run / "run.json")
            selected = state["capability_selection"]["selected"]
            self.assertEqual("adoption", selected[0]["kind"])
            self.assertNotIn("kind", selected[1])
            self.assertEqual(7, state["capability_selection"]["total_invocations"])
            self.assertEqual(3, len(list(next_run.rglob("process.json"))))
            self.assertEqual(9, load_json(run / "run.json")["capability_selection"]["total_invocations"])
            with recovery.operation_lock(root), self.assertRaisesRegex(ValueError, "coordinator_busy"):
                recovery.clear(root)
            recovery.clear(root)
            self.assertEqual([], recovery.registry(root)["entries"])
            with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
                recovery.progress(root, run, interrupted)
            with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
                recovery.register_committed(root, next_run, state)
            self.assertTrue((run / "run.json").is_file())


if __name__ == "__main__":
    unittest.main()
