"""Synthetic, non-authorizing commit projections; no models or formal writes."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

import _b_route_codec as codec
import _b_route_commit_projection as projection
import _b_route_records as records
from test_b_route_records import MatrixFixture, CATALOG, POLICY, ORIGINS, encoded, plan_path


def frozen_for(fx, files, paths, *, operation_id='publish-1', scopes=None):
    ref = {'path': 'evidence/admission.json', 'schema_version': 'synthetic.proof.v1',
        'raw_digest': codec.raw_digest(files['evidence/admission.json'])}
    # Schema-complete synthetic material, expressly not native eligibility.
    request = {'schema_version': 'newrouge.b-route-adoption-request.v1',
        'operation_id': operation_id, 'review_ref': ref,
        'material': {'planner': 'mvg', 'run_id': 'synthetic', 'handoff_ref': ref,
            'protection_ref': ref, 'authority_refs': [], 'lineage_refs': [],
            'identity_alignment': {'plan': {}, 'binding': {}, 'requirements': [],
                'flows': [], 'tasks': []}, 'target_templates': [{}]}}
    return {'request': request, 'allocations': {}, 'scope_ids': scopes or ['scope-main'],
        'authority_refs': [], 'targets': [{'path': p,
            'schema_version': codec.strict_json_loads(files[p])['schema_version'],
            'before_raw_digest': None, 'after_payload': codec.strict_json_loads(files[p]),
            'after_raw_digest': codec.raw_digest(files[p]), 'verification_mode': 'immutable_bytes'}
            for p in paths]}


class CommitProjectionTests(unittest.TestCase):
    def receipt(self, frozen, owners=None):
        return projection.receipt_for_frozen(operation_id=frozen['request']['operation_id'],
            frozen=frozen, resolved_definitions=owners or [])

    def test_complete_frozen_binding_and_original_id_without_digest_cycle(self):
        fx = MatrixFixture()
        binding = fx.add_binding()
        files = fx.render()
        frozen = frozen_for(fx, files, [POLICY, ORIGINS, plan_path(), binding])
        before = deepcopy(frozen)
        receipt = self.receipt(frozen)
        self.assertEqual(codec.canonical_digest(frozen), receipt['operation_digest'])
        self.assertEqual((2, 7), (receipt['plan_refs'][0]['revision'], receipt['binding_refs'][0]['revision']))
        self.assertEqual(before, frozen)
        self.assertNotIn(CATALOG, receipt['result']['target_paths'])
        self.assertEqual('publish-1', receipt['operation_id'])
        receipt['targets'].clear()
        self.assertEqual(before, frozen)

    def test_invalid_id_payload_modes_aliases_and_cycles_fail_closed(self):
        fx = MatrixFixture(); files = fx.render()
        original = frozen_for(fx, files, [POLICY, ORIGINS, plan_path()])
        changes = [
            lambda f: f['request'].update(operation_id='CON'),
            lambda f: f['request'].update(operation_id='../escape'),
            lambda f: f['targets'][0]['after_payload'].update(policy_revision=2),
            lambda f: f['targets'][0].update(verification_mode='task_definition_projection'),
            lambda f: f['targets'].append(deepcopy(f['targets'][0])),
            lambda f: f['targets'][0].update(path=CATALOG),
            lambda f: f['targets'][0].update(path=records.BASE + 'commits/other.json'),
            lambda f: f['authority_refs'].append({'path': records.BASE + 'commits/publish-1.json',
                'schema_version': 'raw.bytes.v1', 'raw_digest': codec.raw_digest(b'cycle')}),
            lambda f: f['authority_refs'].append({'path': POLICY,
                'schema_version': 'raw.bytes.v1', 'raw_digest': codec.raw_digest(b'wrong before')}),
        ]
        for i, change in enumerate(changes):
            with self.subTest(case=i):
                frozen = deepcopy(original); change(frozen)
                with self.assertRaises(codec.CodecError):
                    self.receipt(frozen)

    def test_zero_task_bootstrap_products_pass_real_bundle_validator(self):
        fx = MatrixFixture(); files = fx.render()
        frozen = frozen_for(fx, files, [POLICY, ORIGINS, plan_path()])
        receipt = self.receipt(frozen)
        files.pop(CATALOG); files.pop(records.BASE + 'commits/operation-1.json')
        before = deepcopy(files)
        catalog = projection.catalog_for_receipt(current_catalog=None, receipt=receipt, candidates=files)
        self.assertEqual([], catalog['task_index'])
        self.assertEqual(1, catalog['revision'])
        self.assertEqual(before, files)
        self.assertEqual('A', codec.strict_json_loads(files[POLICY])['switch_boundary']['default_route'])

    def two_scopes(self, *, binding_only=False):
        fx = MatrixFixture()
        q = fx.add_plan('q', 1)
        binding = fx.add_binding() if binding_only else None
        files = fx.render()
        oldpath = records.BASE + 'commits/operation-1.json'
        old = codec.strict_json_loads(files[oldpath])
        old['scopes'] = old['result']['scope_ids'] = ['scope-main', 'scope-q']
        files[oldpath] = encoded(old)
        catalog = codec.strict_json_loads(files[CATALOG])
        catalog['scope_heads'] = [
            {'scope_id': 'scope-main', 'plan_refs': [] if binding_only else [fx.reference(plan_path(), files)],
             'binding_refs': [fx.reference(binding, files)] if binding else [],
             'receipt_ref': fx.reference(oldpath, files)},
            {'scope_id': 'scope-q', 'plan_refs': [fx.reference(q, files)], 'binding_refs': [],
             'receipt_ref': fx.reference(oldpath, files)}]
        files[CATALOG] = encoded(catalog)
        return fx, files, q

    def test_unrelated_scope_is_preserved_from_exact_fresh_snapshot(self):
        fx, files, q = self.two_scopes()
        self.assertTrue(records.validate_bundle(files).ok)
        oldraw = files[CATALOG]
        unrelated = deepcopy(codec.strict_json_loads(oldraw)['scope_heads'][1])
        frozen = frozen_for(fx, files, [plan_path()])
        receipt = self.receipt(frozen)
        catalog = projection.catalog_for_receipt(current_catalog=oldraw, receipt=receipt, candidates=files)
        self.assertEqual(unrelated, next(h for h in catalog['scope_heads'] if h['scope_id'] == 'scope-q'))
        self.assertEqual(2, catalog['revision'])
        self.assertEqual(oldraw, files[CATALOG])
        stale = deepcopy(codec.strict_json_loads(oldraw)); stale['revision'] = 2
        with self.assertRaises(codec.CodecError) as failure:
            projection.catalog_for_receipt(current_catalog=encoded(stale), receipt=receipt, candidates=files)
        self.assertEqual(codec.ReasonCode.INPUT_STALE, failure.exception.diagnostic.reason_code)

    def test_plan_only_projection_reads_actual_existing_governance_without_inventing_targets(self):
        fx, files, _ = self.two_scopes()
        frozen = frozen_for(fx, files, [plan_path()])
        receipt = self.receipt(frozen)
        original = deepcopy(receipt)
        with tempfile.TemporaryDirectory(prefix='nr27-projection-',
                dir=os.environ.get('ADOPTION_TEST_TEMP')) as temporary:
            root = Path(temporary)
            for name, data in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            supplied = {CATALOG: files[CATALOG], plan_path(): files[plan_path()]}
            catalog = projection.catalog_for_receipt(current_catalog=files[CATALOG],
                receipt=receipt, candidates=supplied, root=root)
            self.assertEqual(codec.strict_json_loads(files[CATALOG])['policy_ref'], catalog['policy_ref'])
            self.assertEqual(codec.strict_json_loads(files[CATALOG])['origins_ref'], catalog['origins_ref'])
            self.assertEqual(original, receipt)
            self.assertEqual({CATALOG, plan_path()}, set(supplied))
            self.assertEqual([plan_path()], receipt['result']['target_paths'])
            (root / POLICY).unlink()
            with self.assertRaises(codec.CodecError):
                projection.catalog_for_receipt(current_catalog=files[CATALOG],
                    receipt=receipt, candidates=supplied, root=root)

    def test_binding_only_unrelated_head_keeps_plan_and_exact_task_reverse_mapping(self):
        fx, files, q = self.two_scopes(binding_only=True)
        before = codec.strict_json_loads(files[CATALOG])['scope_heads'][0]
        frozen = frozen_for(fx, files, [q], scopes=['scope-q'])
        catalog = projection.catalog_for_receipt(current_catalog=files[CATALOG],
            receipt=self.receipt(frozen), candidates=files, task_join=fx.join())
        self.assertEqual(before, next(h for h in catalog['scope_heads'] if h['scope_id'] == 'scope-main'))
        self.assertEqual(11, catalog['task_index'][0]['task_id'])
        self.assertEqual(2, catalog['task_index'][0]['plan_refs'][0]['revision'])
        self.assertEqual(7, catalog['task_index'][0]['binding_refs'][0]['revision'])

    def test_all_affected_scopes_share_one_receipt_without_replacing_unrelated_head(self):
        fx, files, q = self.two_scopes()
        before = codec.strict_json_loads(files[CATALOG])['scope_heads'][1]
        frozen = frozen_for(fx, files, [plan_path()], scopes=['scope-extra', 'scope-main'])
        catalog = projection.catalog_for_receipt(current_catalog=files[CATALOG],
            receipt=self.receipt(frozen), candidates=files)
        heads = {row['scope_id']: row for row in catalog['scope_heads']}
        self.assertEqual(before, heads['scope-q'])
        for scope in frozen['scope_ids']:
            self.assertEqual('publish-1', heads[scope]['receipt_ref']['entity_id'])
        self.assertEqual(heads['scope-main']['receipt_ref'], heads['scope-extra']['receipt_ref'])

    def test_existing_receipt_and_missing_proof_or_formal_target_are_rejected(self):
        fx = MatrixFixture(); files = fx.render()
        frozen = frozen_for(fx, files, [POLICY, ORIGINS, plan_path()])
        receipt = self.receipt(frozen)
        files.pop(CATALOG); files.pop(records.BASE + 'commits/operation-1.json')
        for bad in ['changed-receipt', 'evidence/admission.json', plan_path(), POLICY, ORIGINS]:
            with self.subTest(case=bad):
                supplied = deepcopy(files)
                if bad == 'changed-receipt':
                    supplied[records.BASE + 'commits/publish-1.json'] = b'{"changed":true}'
                else:
                    supplied.pop(bad)
                with self.assertRaises(codec.CodecError):
                    projection.catalog_for_receipt(current_catalog=None, receipt=receipt, candidates=supplied)

    def test_incomplete_receipt_result_owner_and_task_correspondence_are_rejected(self):
        fx = MatrixFixture(); binding = fx.add_binding(); files = fx.render()
        frozen = frozen_for(fx, files, [POLICY, ORIGINS, plan_path(), binding])
        receipt = self.receipt(frozen)
        files.pop(CATALOG); files.pop(records.BASE + 'commits/operation-1.json')
        for mutation in ['result', 'scopes', 'owner', 'origins']:
            with self.subTest(case=mutation):
                candidate, draft = deepcopy(files), deepcopy(receipt)
                if mutation == 'result':
                    draft['result']['target_paths'].pop()
                elif mutation == 'scopes':
                    draft['result']['scope_ids'] = ['other-scope']
                elif mutation == 'owner':
                    draft['resolved_definitions'].append({'kind': 'state', 'definition_id': 'missing',
                        'plan_ref': draft['plan_refs'][0]})
                else:
                    origins = codec.strict_json_loads(candidate[ORIGINS]); origins['tasks'].clear()
                    candidate[ORIGINS] = encoded(origins)
                    # Make receipt match this bad origins image: the independent
                    # correspondence check, rather than only raw hashing, must fail.
                    target = next(row for row in draft['targets'] if row['path'] == ORIGINS)
                    target['after_digest'] = target['projection_digest'] = codec.raw_digest(candidate[ORIGINS])
                with self.assertRaises(codec.CodecError):
                    projection.catalog_for_receipt(current_catalog=None, receipt=draft,
                        candidates=candidate, task_join=fx.join())
