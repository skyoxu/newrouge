"""Native candidate projection fixtures; never provider admission or publication."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_candidate as candidate
import _b_route_codec as codec
import _b_route_records as records
import _b_route_schema_resources as resources
import test_b_route_candidate as native_tests
from test_b_route_records import MatrixFixture


def formal_use(value, plan='PLAN-STABLE', revision=3, allocated_flow='FLOW-STABLE'):
    for row in candidate.walk(value):
        if set(row) == {'kind', 'definition_id', 'proposed_owner_key'}:
            kind, identity = row['kind'], row['definition_id']
            row.clear()
            row.update(kind=kind, definition_id=allocated_flow if kind == 'flow' and identity == 'FLOW' else identity,
                       owner_plan_id=plan, owner_revision=revision)
    return value


class NativePlanProjectionTests(unittest.TestCase):
    def setUp(self):
        self.native = native_tests.CandidateTests('test_complete_planned_reentry_scc_and_optional_unreachable_node')
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.content = deepcopy(self.native.value['content'])
        self.allocations = {'plan_id': 'PLAN-STABLE', 'plan_revision': 3,
            'requirements': {self.content['requirements'][0]['requirement_id']: 'RQ-STABLE'},
            'flows': {'FLOW': 'FLOW-STABLE'}}
        resources.validate(self.native.value, candidate.SCHEMA, auxiliary=True)

    def plan(self, projected):
        return {'schema_version': codec.PLAN_SCHEMA, 'plan_id': 'PLAN-STABLE', 'revision': 3,
            **projected,
            'adoption_proof_refs': [{'owner': 'planning_proof', 'ref': 'native/handoff.json#/admission',
                                    'files': [{'path': 'native/handoff.json', 'raw_digest': codec.raw_digest(b'native')}]}],
            'native_candidate_ref': {'owner': 'planning_proof', 'ref': 'native/handoff.json#/proposal/content',
                                    'files': [{'path': 'native/handoff.json', 'raw_digest': codec.raw_digest(b'native')}]},
            'lineage': {'previous_plan_ref': None, 'change_summary': 'Native unchanged semantics', 'identity_alignment': []}}

    def project(self, content=None, allocations=None):
        module = importlib.import_module('_b_route_adoption_projection')
        return module.project_content(content or self.content, allocations or self.allocations)

    def test_real_native_graph_preserved_and_formal_plan_valid(self):
        original = deepcopy(self.content)
        projected = self.project()
        self.assertEqual(original, self.content)
        self.assertEqual(set(projected), {'source_identity', 'requirements', 'definitions', 'logical_references',
            'requirement_verification', 'requirement_route_memberships', 'requirement_evidence',
            'evidence_source_refs', 'coverage_table', 'applicability'})
        expected = formal_use(deepcopy(original['definitions']['flows'][0]))
        expected.pop('proposed_owner_key')
        expected['id'] = 'FLOW-STABLE'
        expected['requirement_ids'] = ['RQ-STABLE']
        for row in candidate.walk(expected['graph']):
            if set(row) == {'flow_id', 'node_id'} and row['flow_id'] == 'FLOW':
                row['flow_id'] = 'FLOW-STABLE'
        self.assertEqual(expected, projected['definitions']['flows'][0])
        self.assertEqual(original['requirements'][0]['prior_requirement_ids'],
                         projected['requirements'][0]['prior_requirement_ids'])
        self.assertEqual(original['source_identity'], projected['source_identity'])
        result = records.validate_record(self.plan(projected))
        self.assertTrue(result.ok, result.to_dict())

    def test_native_graph_shape_has_a_public_formal_branch(self):
        shared = ('source_identity', 'requirements', 'definitions', 'logical_references',
            'requirement_verification', 'requirement_route_memberships', 'requirement_evidence',
            'evidence_source_refs', 'coverage_table', 'applicability')
        projected = {name: deepcopy(self.content[name]) for name in shared}
        for rows in projected['definitions'].values():
            for row in rows:
                row.pop('proposed_owner_key')
        formal_use(projected, allocated_flow='FLOW')
        result = records.validate_record(self.plan(projected))
        self.assertTrue(result.ok, result.to_dict())

    def test_projected_graph_requires_native_ref_and_rejects_proposed_use(self):
        plan = self.plan(self.project())
        plan.pop('native_candidate_ref')
        missing = records.validate_record(plan)
        self.assertFalse(missing.ok)
        self.assertEqual(missing.diagnostic.reason_code, codec.ReasonCode.MISSING_REQUIRED_FIELD)
        plan = self.plan(self.project())
        plan['definitions']['flows'][0]['graph']['nodes'][0]['owner'] = {
            'kind': 'flow', 'definition_id': 'FLOW-STABLE', 'proposed_owner_key': 'not-resolved'}
        # The shared input graph also permits proposal uses; formal local checks
        # must reject these after structural schema validation succeeds.
        resources.validate(plan, codec.PLAN_SCHEMA)
        unresolved = records.validate_record(plan)
        self.assertFalse(unresolved.ok)
        self.assertEqual(unresolved.diagnostic.reason_code, codec.ReasonCode.UNRESOLVED_REFERENCE)

    def test_unknown_proposed_owner_is_not_guessed(self):
        value = deepcopy(self.content)
        value['definitions']['flows'][0]['ui']['owner']['proposed_owner_key'] = 'unknown-owner'
        with self.assertRaises(codec.CodecError):
            self.project(value)

    def test_typed_identifiers_and_existing_owner_are_preserved(self):
        value = deepcopy(self.content)
        old_requirement = value['requirements'][0]['requirement_id']
        for row in candidate.walk(value):
            if row.get('requirement_id') == old_requirement:
                row['requirement_id'] = 'SAME'
            if 'requirement_ids' in row:
                row['requirement_ids'] = ['SAME' if x == old_requirement else x for x in row['requirement_ids']]
            if row.get('flow_id') == 'FLOW':
                row['flow_id'] = 'SAME'
            if row.get('kind') == 'flow' and row.get('definition_id') == 'FLOW':
                row['definition_id'] = 'SAME'
        flow = value['definitions']['flows'][0]
        flow['id'] = 'SAME'
        flow['capability_ids'] = ['SAME']
        flow['graph']['nodes'][0]['id'] = 'SAME'
        for row in candidate.walk(flow['graph']):
            if set(row) == {'flow_id', 'node_id'} and row['node_id'] == 'entry':
                row['node_id'] = 'SAME'
        value['definitions']['commands'] = [{'id': 'SAME', 'proposed_owner_key': 'command-owner',
            'requirement_ids': ['SAME'], 'responsibility': 'SAME', 'uses': []}]
        value['definitions']['states'] = [{'id': 'SAME', 'proposed_owner_key': 'state-owner',
            'requirement_ids': ['SAME'], 'responsibility': 'SAME', 'uses': []}]
        flow['graph']['nodes'][0]['command_uses'] = [
            {'kind': 'command', 'definition_id': 'SAME', 'proposed_owner_key': 'command-owner'}]
        existing = {'kind': 'flow', 'definition_id': 'SAME', 'owner_plan_id': 'EXTERNAL', 'owner_revision': 9}
        value['logical_references'] = [existing]
        projected = self.project(value, {'plan_id': 'PLAN-STABLE', 'plan_revision': 3,
            'requirements': {'SAME': 'RQ-DISTINCT'}, 'flows': {'SAME': 'FLOW-DISTINCT'}})
        result = projected['definitions']['flows'][0]
        self.assertEqual(result['id'], 'FLOW-DISTINCT')
        self.assertEqual(result['requirement_ids'], ['RQ-DISTINCT'])
        self.assertEqual(result['capability_ids'], ['SAME'])
        self.assertEqual(result['graph']['nodes'][0]['id'], 'SAME')
        self.assertEqual(result['graph']['nodes'][0]['command_uses'][0],
            {'kind': 'command', 'definition_id': 'SAME', 'owner_plan_id': 'PLAN-STABLE', 'owner_revision': 3})
        self.assertEqual(projected['definitions']['commands'][0]['responsibility'], 'SAME')
        self.assertEqual(projected['logical_references'], [existing])

    def test_formal_only_without_graph_keeps_legacy_and_blocks_graph(self):
        directory = self.native.root / 'formal-schemas'
        directory.mkdir()
        for name in resources.FORMAL:
            shutil.copyfile(resources.DIRECTORY / (name + '.schema.json'), directory / (name + '.schema.json'))
        old = MatrixFixture()
        old.add_flow(old.current_plans[0])
        legacy = old.models[old.current_plans[0]]
        graph = self.plan(self.project())
        with patch.object(records, 'SCHEMA_DIRECTORY', directory), \
             patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline schema only')):
            self.assertTrue(records.validate_record(legacy).ok)
            self.assertFalse(records.validate_record(graph).ok)
            without_graph = resources.validator(codec.PLAN_SCHEMA, directory)
            shutil.copyfile(resources.DIRECTORY / 'flow-graph.schema.json', directory / 'flow-graph.schema.json')
            with_graph = resources.validator(codec.PLAN_SCHEMA, directory)
            self.assertIsNot(without_graph, with_graph)
            self.assertTrue(records.validate_record(graph).ok)
            with self.assertRaises(codec.CodecError):
                resources.validator('newrouge.b-route-flow-graph.v1', directory)
            (directory / 'flow-graph.schema.json').unlink()
            self.assertTrue(records.validate_record(legacy).ok)
            self.assertFalse(records.validate_record(graph).ok)


if __name__ == '__main__':
    unittest.main(verbosity=2)
