"""Offline acceptance for independent Requirement routes and conserved authority."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _mvg_requirement_routes import FIELD, membership_schema, memberships, project_routes, route_errors
from _mvg_capability_append import merge_append, preservation_errors
from _mvg_capability_generation import append_output_schema, repair_scope_errors, review_projection
from _mvg_planning_review import coverage_errors
from _planning_skill_common import atomic_json, canonical_sha
import plan_mvg


def fixture():
    return {"manifest_candidate": {"flows": [
        {"id": fid, "requirement_ids": ["RQ-1"], "capability_refs": ["CAP-A"],
         "task_ids": [7], "handoffs": [], "test_ids": []} for fid in ("flow-a", "flow-b")]},
        "coverage_table": [{"requirement_id": "RQ-1", "flow_id": "flow-a", "disposition": "flow",
            "capability_ref": "CAP-A", "task_id": 7, "rationale": "Original owner role",
            "legacy_evidence": {"id": "evidence-a"}}], "tests": [], "entrypoints": [], "notes": [],
        FIELD: [{"requirement_id": "RQ-1", "flow_id": "flow-a", "observable_role": "Original owner role"},
                {"requirement_id": "RQ-1", "flow_id": "flow-b", "observable_role": "Recover the same state"}]}


class RequirementRouteTests(unittest.TestCase):
    def test_public_generate_checkpoint_review_apply_replay_and_local_knowledge(self):
        from scripts.python.tests.test_mvg_capability_append import CapabilityAppendTests
        CapabilityAppendTests().exercise_public_generation(multi_route=True, coordinator_case='apply-replay')

    def test_public_new_run_generates_explicit_complete_roles_from_legacy_trace(self):
        from scripts.python.tests.test_mvg_capability_append import CapabilityAppendTests
        CapabilityAppendTests().exercise_public_generation(multi_route=True, coordinator_case='apply-replay', legacy_next=True)

    def test_multi_route_preserves_one_authoritative_row(self):
        proposal = fixture()
        self.assertEqual([], route_errors(proposal, {"RQ-1"}))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual([], coverage_errors(Path(directory), proposal,
                {"requirements": [{"requirement_id": "RQ-1"}]},
                {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-1"]}]}, []))
        self.assertEqual(1, len(proposal["coverage_table"]))
        self.assertEqual(2, len(proposal[FIELD]))

    def test_bad_pairs_and_roles_are_located_and_never_migrated(self):
        for mutation, expected in (("duplicate", "pair_duplicate"), ("requirement", "unknown_requirement"),
                ("flow", "unknown_flow"), ("not_member", "flow_membership_invalid"),
                ("role", "role_missing"), ("empty", "pair_missing"), ("null", "not_array")):
            with self.subTest(mutation=mutation):
                proposal = fixture()
                if mutation == "duplicate":
                    proposal[FIELD].append(deepcopy(proposal[FIELD][0]))
                elif mutation == "requirement":
                    proposal[FIELD][0]["requirement_id"] = "RQ-unknown"
                elif mutation == "flow":
                    proposal[FIELD][0]["flow_id"] = "flow-unknown"
                elif mutation == "not_member":
                    proposal["manifest_candidate"]["flows"][0]["requirement_ids"] = []
                elif mutation == "role":
                    proposal[FIELD][0]["observable_role"] = "  "
                else:
                    proposal[FIELD] = [] if mutation == "empty" else None
                self.assertEqual(proposal[FIELD], memberships(proposal))
                self.assertTrue(any(expected in error for error in route_errors(proposal, {"RQ-1"})))

    def test_legacy_projection_conserves_every_field_and_hash(self):
        legacy = fixture()
        legacy.pop(FIELD)
        before, digest = deepcopy(legacy), canonical_sha(legacy)
        projected = project_routes(legacy)
        self.assertEqual(before, legacy)
        self.assertEqual(digest, canonical_sha(legacy))
        self.assertEqual(legacy["coverage_table"], projected["coverage_table"])
        self.assertEqual([{"requirement_id": "RQ-1", "flow_id": "flow-a",
                           "observable_role": "Original owner role"}], projected[FIELD])
        self.assertEqual(projected, project_routes(projected))
        merged = merge_append(legacy, {"flows": [], "coverage_table": [], "tests": [], "entrypoints": []})
        self.assertNotIn(FIELD, merged)

    def test_legacy_checkpoint_read_projection_keeps_payload_and_transaction_hash(self):
        from _mvg_capability_checkpoint import prepare_checkpoint, load_checkpoint, verify_checkpoint
        from scripts.python.tests.test_mvg_capability_append import CapabilityAppendTests
        from _planning_skill_common import file_sha
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            state, seed, accepted, step = CapabilityAppendTests().checkpoint_fixture(run)
            accepted.update(fixture())
            accepted.pop(FIELD)
            step['proposal_sha256'] = canonical_sha(accepted)
            pointer = prepare_checkpoint(run, state, 'CAP-A', 0, seed, accepted, step)
            step['checkpoint'] = pointer
            path = run / pointer['path']
            digest = file_sha(path)
            payload = load_checkpoint(run, pointer)
            projected = project_routes(payload['accepted'])
            self.assertEqual(1, len(projected[FIELD]))
            self.assertEqual(accepted, verify_checkpoint(run, state, 'CAP-A', 0, seed, accepted, step, None))
            self.assertEqual(digest, file_sha(path))
            self.assertEqual(payload, load_checkpoint(run, pointer))

    def test_legacy_migration_preserves_coverage_alias_verbatim(self):
        legacy = fixture()
        legacy.pop(FIELD)
        legacy["coverage_table"][0].pop("rationale")
        legacy["coverage_table"][0]["coverage"] = "Original legacy coverage explanation"
        self.assertEqual("Original legacy coverage explanation", memberships(legacy)[0]["observable_role"])
        self.assertEqual([], route_errors(legacy, {"RQ-1"}))
        self.assertEqual(legacy["coverage_table"], project_routes(legacy)["coverage_table"])
        legacy["coverage_table"][0]["rationale"] = "Preferred original rationale"
        self.assertEqual("Preferred original rationale", memberships(legacy)[0]["observable_role"])
        legacy['coverage_table'][0]['rationale'] = '  \t'
        self.assertEqual('Original legacy coverage explanation', memberships(legacy)[0]['observable_role'])

    def test_cumulative_pair_append_preserves_owner_and_previous_role(self):
        base = fixture()
        base["manifest_candidate"]["flows"].pop()
        base[FIELD].pop()
        delta = {"flows": [fixture()["manifest_candidate"]["flows"][1]], "coverage_table": [],
                 FIELD: [fixture()[FIELD][1]], "tests": [], "entrypoints": []}
        combined = merge_append(base, delta)
        self.assertEqual([], preservation_errors(base, combined))
        self.assertEqual([], route_errors(combined, {"RQ-1"}))
        self.assertEqual(base["coverage_table"], combined["coverage_table"])
        self.assertEqual(fixture()[FIELD], combined[FIELD])
        changed = deepcopy(combined)
        changed[FIELD][0]["observable_role"] = "Reassigned"
        self.assertTrue(preservation_errors(base, changed))

    def test_raw_duplicate_pair_or_authority_cannot_disappear_in_merge(self):
        delta = {FIELD: [fixture()[FIELD][0], fixture()[FIELD][0]], "coverage_table": []}
        with self.assertRaisesRegex(ValueError, "pair_duplicate"):
            merge_append(fixture(), delta)
        with self.assertRaisesRegex(ValueError, "coverage_requirement_duplicate"):
            plan_mvg.merge_planning_segments({}, [{"coverage_table": fixture()["coverage_table"] * 2}])
        with self.assertRaisesRegex(ValueError, "already_accepted"):
            merge_append(fixture(), {FIELD: [], "coverage_table": fixture()["coverage_table"]})

    def test_repair_cannot_change_unrelated_pair_of_same_requirement(self):
        old, revised = fixture(), fixture()
        revised[FIELD][0]["observable_role"] = "Unrelated role changed"
        issue = {"code": "requirement_route_role_missing", "path": "flow-b"}
        errors = repair_scope_errors(old, revised, issue)
        self.assertIn("repair_unrelated_requirement_route_changed:RQ-1:flow-a", errors)
        issue['path'] = 'RQ-1:flow-b'
        self.assertIn("repair_unrelated_requirement_route_changed:RQ-1:flow-a",
                      repair_scope_errors(old, revised, issue))

    def test_review_projection_keeps_related_owner_and_unique_review_count(self):
        base = fixture()
        base["manifest_candidate"]["flows"].pop()
        base[FIELD].pop()
        proposal = fixture()
        scope = {"requirement_ids": ["RQ-2"], "cumulative_requirement_ids": ["RQ-1", "RQ-2"]}
        projection, required = review_projection(scope, base, proposal)
        self.assertEqual({"flow-a", "flow-b"}, {row["id"] for row in projection["manifest_candidate"]["flows"]})
        self.assertEqual(1, len(projection["coverage_table"]))
        self.assertEqual(2, len(projection[FIELD]))

    def test_default_generation_schema_requires_cumulative_memberships(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": [{"capability_id": "CAP-B"}]})
            scope = {"capability_id": "CAP-B", "new_requirement_ids": ["RQ-2"],
                     "cumulative_requirement_ids": ["RQ-1", "RQ-2"]}
            schema = append_output_schema({"analysis_identity_sha256": "sha256:fixture"}, scope, fixture(), prepared)
            self.assertIn(FIELD, schema["required"])
            self.assertEqual(["RQ-1", "RQ-2"], schema["properties"][FIELD]["items"]["properties"]["requirement_id"]["enum"])
            self.assertEqual(["RQ-2"], schema["properties"]["coverage_table"]["items"]["properties"]["requirement_id"]["enum"])

    def test_prepared_trace_protocol_hash_and_legacy_isolation(self):
        from _mvg_requirement_routes import PROTOCOL, prepared_trace
        from _planning_skill_common import file_sha
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            path = prepared / 'existing-planning-trace.json'
            atomic_json(path, fixture())
            self.assertEqual({}, prepared_trace(prepared))
            index = {'files': {'existing-planning-trace.json': file_sha(path)}}
            atomic_json(prepared / 'analysis-index.json', index)
            self.assertEqual({}, prepared_trace(prepared))
            index['requirement_routes_protocol'] = PROTOCOL
            atomic_json(prepared / 'analysis-index.json', index)
            self.assertEqual(fixture(), prepared_trace(prepared))
            atomic_json(path, {**fixture(), 'notes': ['tampered']})
            with self.assertRaisesRegex(ValueError, 'snapshot_changed'):
                prepared_trace(prepared)
            index['requirement_routes_protocol'] = 'unknown'
            atomic_json(prepared / 'analysis-index.json', index)
            with self.assertRaisesRegex(ValueError, 'protocol_unknown'):
                prepared_trace(prepared)

    def test_knowledge_uses_only_exact_manifest_bound_trace(self):
        from scripts.python.tests.test_project_health_mvg_versions import Snapshot
        from _project_health_mvg_versions import build_overview
        from _mvg_manifest import manifest_sha256
        snapshot = Snapshot()
        path = 'docs/testing/mvg/cumulative.json'
        manifest = json.loads(snapshot.files[path])
        manifest['flows'] = fixture()['manifest_candidate']['flows']
        snapshot.files[path] = json.dumps(manifest).encode()
        trace_path = 'docs/testing/mvg/planning/routes.json'
        trace = dict(fixture(), applied_manifest_path=path,
                     applied_manifest_sha256=manifest_sha256(snapshot.files[path]))
        trace['manifest_candidate'] = deepcopy(manifest)
        for mutation in ('valid', 'legacy', 'path', 'hash', 'bad_role', 'absent'):
            with self.subTest(mutation=mutation):
                current = deepcopy(trace)
                if mutation == 'legacy':
                    current.pop(FIELD)
                elif mutation == 'path':
                    current['applied_manifest_path'] = 'docs/testing/mvg/other.json'
                elif mutation == 'hash':
                    current['applied_manifest_sha256'] = 'sha256:other'
                elif mutation == 'bad_role':
                    current[FIELD][0]['observable_role'] = ''
                snapshot.files[trace_path] = json.dumps(current).encode()
                snapshot.paths = tuple(key for key in snapshot.files if mutation != 'absent' or key != trace_path)
                overview = build_overview(snapshot, [], {'available': True, 'fresh': True,
                    'identity': {'revision': snapshot.commit}, 'nodes': {'requirements': [{'requirement_id': 'RQ-1'}]}}, {'nodes': {}})
                row = overview['manifests'][0]
                self.assertEqual(2 if mutation == 'valid' else 1 if mutation == 'legacy' else 0, len(row[FIELD]))
                if mutation in ('valid', 'legacy'):
                    self.assertEqual(fixture()['coverage_table'], row['coverage_table'])
                    self.assertEqual(trace_path, row['requirement_routes_source']['path'])

    def test_membership_only_change_and_joint_closure_reach_owner(self):
        base = fixture()
        base['manifest_candidate']['flows'] += [
            {'id': 'flow-c', 'requirement_ids': ['RQ-2'], 'test_ids': []},
            {'id': 'flow-d', 'requirement_ids': ['RQ-2'], 'test_ids': []}]
        base['entrypoints'] = [{'flow_ids': ['flow-b', 'flow-c']}]
        base[FIELD] += [{'requirement_id': 'RQ-2', 'flow_id': fid, 'observable_role': 'Original'}
                        for fid in ('flow-c', 'flow-d')]
        revised = deepcopy(base)
        revised[FIELD][0]['observable_role'] = 'Changed role only'
        scope = {'requirement_ids': [], 'cumulative_requirement_ids': ['RQ-1', 'RQ-2']}
        projection, required = review_projection(scope, base, revised)
        self.assertEqual({'flow-a', 'flow-b', 'flow-c', 'flow-d'},
            {row['id'] for row in projection['manifest_candidate']['flows']})
        self.assertEqual({'RQ-1', 'RQ-2'}, required)

    def test_protocol_requires_real_new_memberships_and_rejects_unknown_version(self):
        from _mvg_requirement_routes import PROTOCOL, protocol_errors
        legacy = fixture(); legacy.pop(FIELD)
        self.assertTrue(protocol_errors({'requirement_routes_protocol': PROTOCOL}, legacy))
        self.assertTrue(protocol_errors({'requirement_routes_protocol': 'unknown'}, fixture()))
        self.assertEqual([], protocol_errors({}, legacy))
        self.assertTrue(protocol_errors({'requirement_routes_protocol': PROTOCOL}, project_routes(legacy)))

    def test_field_contract_and_cross_segment_duplicates_fail_before_merge(self):
        from _mvg_requirement_routes import pair_errors
        self.assertTrue(pair_errors([{**fixture()[FIELD][0], 'extra': 'invalid'}]))
        with self.assertRaisesRegex(ValueError, 'pair_duplicate'):
            plan_mvg.merge_planning_segments({}, [{FIELD: fixture()[FIELD][:1]}, {FIELD: fixture()[FIELD][:1]}])
        with self.assertRaisesRegex(ValueError, 'pair_conflict'):
            plan_mvg.merge_planning_segments(fixture(), [{FIELD: [{**fixture()[FIELD][0], 'observable_role': 'Changed'}]}])

    def test_trace_authority_is_bound_to_real_semantics_and_applied_flow(self):
        from _mvg_requirement_routes import trace_errors
        trace = fixture(); manifest = deepcopy(trace['manifest_candidate'])
        self.assertEqual([], trace_errors(trace, manifest, {'RQ-1'}))
        self.assertTrue(trace_errors(trace, manifest, set()))
        trace['coverage_table'] *= 2
        self.assertTrue(any('duplicate' in error for error in trace_errors(trace, manifest, {'RQ-1'})))
        trace = fixture(); trace['applied_manifest_candidate'] = deepcopy(manifest)
        trace['applied_manifest_candidate']['flows'][0]['outcome'] = 'Invented applied outcome'
        self.assertTrue(trace_errors(trace, manifest, {'RQ-1'}))
        for invalid in (None, [], {'flows': None}, {'flows': [None]},
                        {'flows': [{'handoffs': [None]}]}):
            with self.subTest(invalid=invalid):
                self.assertTrue(trace_errors({**fixture(), 'manifest_candidate': invalid}, manifest, {'RQ-1'}))

    def test_protocol_gate_rejects_missing_field_in_real_validator(self):
        from scripts.python.tests.test_planning_audit_repair import prepared_mvg
        from planning_acceptance_fixture import build_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); build_fixture(root)
            state, proposal, _ = prepared_mvg(root)
            proposal.pop(FIELD)
            errors = plan_mvg.validate_proposal(root, state, proposal)['errors']
            self.assertIn('requirement_route_memberships_required_by_protocol', errors)

    def test_legacy_apply_trace_next_prepare_preserves_owner_and_authority(self):
        from scripts.python.tests.test_mvg_input_envelope import InputEnvelopeTests
        from _planning_skill_common import file_sha, load_json
        from _mvg_capability_generation import seed_proposal
        case = InputEnvelopeTests(); case.setUp()
        self.addCleanup(case.doCleanups)
        root = case.root
        reqs = load_json(root / plan_mvg.SEMANTICS)['requirements']
        rid, historical = [row['requirement_id'] for row in reqs]
        proposal = fixture(); proposal.pop(FIELD)
        for flow in proposal['manifest_candidate']['flows']:
            flow['requirement_ids'] = [rid]
        proposal['coverage_table'][0]['requirement_id'] = rid
        proposal['coverage_table'] += [{'requirement_id': historical, 'disposition': disposition,
            'rationale': 'Retained historical authority', key: 'docs/testing/historical.md#record',
            'authority_review': {'status': 'reviewed', 'rationale': 'Reviewed retained deferral'},
            'original_evidence': {'unchanged': True}}
            for disposition, key in [('deferred', 'authority_ref')]]
        atomic_json(root / 'docs/testing/historical.md', {'reviewed': True})
        state = case.prepare()
        # This is a historical protocol fixture, before route/checkpoint fields existed.
        run = case.run
        index_path = run / 'analysis-input/analysis-index.json'
        index = load_json(index_path)
        for key in ('requirement_routes_protocol', 'requirement_accounting_protocol', 'checkpoint_strategy', 'checkpoint_schema_version'):
            index.pop(key, None); state.pop(key, None)
        state.pop('generation_strategy', None)
        atomic_json(index_path, index); atomic_json(run / 'run.json', state)
        atomic_json(run / 'proposal.json', proposal)
        digest = file_sha(run / 'proposal.json')
        with patch.object(plan_mvg, '_load_run', return_value=(run / 'run.json', state)), \
             patch.object(plan_mvg, 'validate', return_value={'status': 'passed', 'formal_applicable': True}), \
             patch.object(plan_mvg, 'validate_manifest', return_value=[]):
            applied = plan_mvg.apply(root, run_id='envelope', confirm=True)
            self.assertEqual(applied, plan_mvg.apply(root, run_id='envelope', confirm=True))
        self.assertEqual(digest, file_sha(run / 'proposal.json'))
        trace = load_json(root / applied['trace_path'])
        self.assertEqual(1, len(trace[FIELD]))
        next_state = case.prepare(run_id='next')
        prepared = root / plan_mvg.DEFAULT_RUN_ROOT / 'next/analysis-input'
        seed = seed_proposal(next_state, prepared)
        self.assertEqual(proposal['coverage_table'], seed['coverage_table'])
        self.assertEqual(trace[FIELD], seed[FIELD])
        self.assertEqual([], route_errors(seed, {rid, historical}))
        next_index = load_json(prepared / 'analysis-index.json')
        self.assertIn('references/docs/testing/historical.md', next_index['files'])
        self.assertIn('docs/testing/historical.md', next_index['authority_inputs'])
        incomplete = merge_append(seed, {FIELD: [], 'coverage_table': []})
        self.assertIn('requirement_routes_projection', incomplete)
        complete = merge_append(seed, {FIELD: [{'requirement_id': rid, 'flow_id': 'flow-b',
            'observable_role': 'Explicit new recovery role'}], 'coverage_table': []})
        self.assertNotIn('requirement_routes_projection', complete)
        self.assertEqual([], route_errors(complete, {rid, historical}))

    def test_legacy_multi_flow_owner_projection_remains_readable_without_inventing_roles(self):
        from _mvg_requirement_routes import trace_errors, PROTOCOL
        from _mvg_capability_generation import seed_proposal
        from _planning_skill_common import file_sha
        legacy = fixture(); legacy.pop(FIELD)
        trace = project_routes(legacy)
        self.assertEqual([], trace_errors(trace, legacy['manifest_candidate'], {'RQ-1'}))
        self.assertEqual(1, len(trace[FIELD]))
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            atomic_json(prepared / 'existing-manifest.json', legacy['manifest_candidate'])
            atomic_json(prepared / 'existing-planning-trace.json', trace)
            atomic_json(prepared / 'analysis-index.json', {'requirement_routes_protocol': PROTOCOL,
                'files': {'existing-planning-trace.json': file_sha(prepared / 'existing-planning-trace.json')}})
            seed = seed_proposal({'run_id': 'legacy', 'analysis_identity_sha256': 'old'}, prepared)
            self.assertEqual(trace[FIELD], seed[FIELD])
            self.assertEqual(legacy['coverage_table'], seed['coverage_table'])
            self.assertEqual([], route_errors(seed, {'RQ-1'}))


if __name__ == '__main__':
    unittest.main()
