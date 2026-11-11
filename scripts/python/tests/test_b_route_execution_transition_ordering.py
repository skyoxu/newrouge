"""Original JSON order is material when native requests bind exact bytes.

The focused unit fixtures replace only source-freeze gates to exercise _collect
before a new commit exists. They are not transition qualification. The opt-in
real fixture additionally uses the unchanged original subprocess verifier and
native prepared/wire/review assembly, with no model dispatch.
"""
from copy import deepcopy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_execution_transition as transition


class PreparedOrderingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('EXECUTION_TRANSITION_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = self.root / 'old-source'
        self.original.mkdir()
        self.reference = 'logs/ci/fixture/b-route-planning-input/run/prepared.json'
        self.path = self.root / self.reference
        self.path.parent.mkdir(parents=True)
        self.frozen = {'schema_version': 'fixture', 'input_identity': 'original-input',
                       'inputs': {'z-original-first': {'z': 3, 'a': 1}, 'a-original-last': [2]},
                       'transport': {'z-plan-first': True, 'a-plan-last': False}}
        self.path.write_text(json.dumps(self.frozen, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.desc = {'prepared_ref': self.reference, 'input_identity': self.frozen['input_identity'],
                     'frozen_sha256': transition.codec.canonical_digest(self.frozen), 'rules': {'original': True}}
        self.state = {'schema_version': transition.ORIGINAL_RUN_SCHEMA, 'planning_runtime': self.desc,
                      'runtime_identity': transition.codec.canonical_digest(self.desc)}

    def freeze_fixture(self, stack, original):
        before = {'scripts/python/_b_route_planning_runtime.py': {'raw_digest': 'fixture-runtime'}}
        after = {**before, 'scripts/python/_b_route_execution_transition.py': {'raw_digest': 'fixture-transition'}}
        stack.enter_context(patch.object(transition, '_source_manifest',
            side_effect=lambda root, commit: deepcopy(before if root == original else after)))

    def witness(self):
        # Exactly emulate the verified child JSON transport's sort_keys=True.
        sorted_value = json.loads(json.dumps(self.frozen, ensure_ascii=False, sort_keys=True))
        return {'frozen': sorted_value, 'prepared_raw_digest': transition.codec.raw_digest(self.path.read_bytes()),
                'runtime_rules': self.desc['rules'], 'runtime_identity': self.state['runtime_identity'],
                'frozen_sha256': self.desc['frozen_sha256']}

    def test_sorted_child_result_returns_exact_nested_raw_order(self):
        with ExitStack() as stack:
            self.freeze_fixture(stack, self.original)
            stack.enter_context(patch.object(transition, '_semantic_unchanged', return_value={}))
            stack.enter_context(patch.object(transition, '_run_original', return_value=self.witness()))
            body, restored = transition._collect(self.root, self.state, self.original, 'f' * 40)
        self.assertNotEqual(list(self.witness()['frozen']), list(self.frozen))
        self.assertEqual(json.dumps(self.frozen, ensure_ascii=False), json.dumps(restored, ensure_ascii=False))
        self.assertEqual(transition.codec.raw_digest(self.path.read_bytes()), body['prepared_raw_digest'])
        self.assertEqual(self.desc['frozen_sha256'], transition.codec.canonical_digest(restored))

    def test_canonical_child_content_mismatch_is_still_rejected(self):
        witness = self.witness()
        witness['frozen']['inputs']['z-original-first']['z'] = 99
        with ExitStack() as stack:
            self.freeze_fixture(stack, self.original)
            stack.enter_context(patch.object(transition, '_semantic_unchanged', return_value={}))
            stack.enter_context(patch.object(transition, '_run_original', return_value=witness))
            with self.assertRaisesRegex(transition.TransitionError, 'verified_prepared_content_changed'):
                transition._collect(self.root, self.state, self.original, 'f' * 40)

    @unittest.skipUnless(os.environ.get('B_ROUTE_ORDERING_FIXTURE_ROOT')
                         and os.environ.get('B_ROUTE_ORDERING_ORIGINAL_SOURCE'),
                         'Explicit original offline c4 fixture required')
    def test_real_prepared_native_wire_and_complete_review_assembly(self):
        import _b_route_planning_input as planning
        import _b_route_planning_runtime as runtime
        import _b_route_planning_wire as wire
        root = Path(os.environ['B_ROUTE_ORDERING_FIXTURE_ROOT']).resolve()
        original = Path(os.environ['B_ROUTE_ORDERING_ORIGINAL_SOURCE']).resolve()
        run = root / 'logs/ci/capability-planning/c4'
        state = transition.codec.strict_json_loads((run / 'run.json').read_bytes())
        reference = state['planning_runtime']['prepared_ref']
        raw = transition._path(root, reference).read_bytes()
        ordered = transition.codec.strict_json_loads(raw)
        sorted_child = json.loads(json.dumps(ordered, ensure_ascii=False, sort_keys=True))
        self.assertEqual(transition.codec.canonical_digest(ordered), transition.codec.canonical_digest(sorted_child))
        with self.assertRaises(transition.codec.CodecError) as caught:
            planning.validate_frozen(sorted_child)
        self.assertEqual('prepared.request', caught.exception.diagnostic.entity_id)
        with ExitStack() as stack:
            # The new R7 source is not committed yet in this regression. Source
            # manifest binding is separately checked after the root freezes it.
            self.freeze_fixture(stack, original)
            stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline test')))
            _, restored = transition._collect(root, state, original, 'f' * 40)
            self.assertEqual(json.dumps(ordered, ensure_ascii=False), json.dumps(restored, ensure_ascii=False))
            self.assertEqual(ordered, planning.validate_frozen(restored))
            delivery = runtime.wire_delivery(state)
            request = planning.build_wire_request(restored, wire_delivery=delivery, batch_ordinal=1)
            self.assertTrue(request['payload'])
            calls = state['capability_selection']['calls']
            binding = transition.codec.strict_json_loads((run / calls[2]['request_identity']['execution_binding_path']).read_bytes())
            previous = wire.read_prompt(Path(binding['prompt_path']).read_text(encoding='utf-8'), delivery)
            proposal = previous['proposal']
            payload = runtime.request_payload(restored, phase='independent_admission',
                seed_value=previous['accepted_seed'], proposal=proposal, context=previous['lineage_context'],
                drafts=proposal['provenance']['draft_chain'], delivery=delivery)
            payload.update(runtime_identity=state['runtime_identity'], run_id=state['run_id'],
                slot=previous['slot'], generation=previous['generation'], execution=previous['execution'],
                lineage_identity=previous['lineage_identity'], review_source_policy=runtime.REVIEW_SOURCE_POLICY,
                execution_source_transition=state['b_route_execution_transition']['transition_digest'])
            payload['obligations'] = runtime.obligations(proposal, restored)
            payload['qualified_sources'] = runtime.qualified_sources(proposal, restored)
            schema = runtime.review_producer_schema(state, proposal, restored, policy=runtime.REVIEW_SOURCE_POLICY)
            payload['actual_output_schema'] = schema
            payload['materials_identity'] = transition.codec.canonical_digest(
                {key: value for key, value in payload.items() if key != 'materials_identity'})
            prompt = runtime.materials_prompt(payload)
            decoded = wire.read_prompt(prompt, delivery)
            self.assertTrue(runtime.same_json(decoded, payload))
            self.assertTrue(prompt)
            self.assertTrue(payload['obligations'])
        self.assertEqual(raw, transition._path(root, reference).read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
