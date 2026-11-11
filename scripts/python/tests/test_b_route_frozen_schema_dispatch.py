"""Strict frozen request-version dispatch through the actual receipt consumer.

Pure synthetic records only: no native proof, model, child or formal writes.
Root alone executes these tests after freezing the current source/dependency set.
"""
from copy import deepcopy
import unittest

import _b_route_codec as codec
import _b_route_commit_projection as projection
from test_b_route_commit_projection import frozen_for
from test_b_route_records import MatrixFixture, POLICY, ORIGINS, plan_path


class FrozenSchemaDispatchTests(unittest.TestCase):
    def frozen(self, version=1):
        fixture = MatrixFixture()
        files = fixture.render()
        frozen = frozen_for(fixture, files, [POLICY, ORIGINS, plan_path()])
        frozen['request']['schema_version'] = 'newrouge.b-route-adoption-request.v' + str(version)
        if version == 2:
            frozen['request']['material']['origin_profile'] = 'r22-m4-nx-original.v1'
        return frozen

    def receipt(self, frozen):
        return projection.receipt_for_frozen(operation_id='publish-1', frozen=frozen,
                                             resolved_definitions=[])

    def assert_schema_rejected(self, frozen):
        before = deepcopy(frozen)
        with self.assertRaises(codec.CodecError) as caught:
            self.receipt(frozen)
        self.assertEqual(codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                         caught.exception.diagnostic.reason_code)
        self.assertEqual(before, frozen)

    def test_v1_frozen_receipt_keeps_original_identity_without_origin_profile(self):
        frozen = self.frozen()
        before = deepcopy(frozen)
        receipt = self.receipt(frozen)
        self.assertNotIn('origin_profile', frozen['request']['material'])
        self.assertEqual('publish-1', receipt['operation_id'])
        self.assertEqual(codec.canonical_digest(frozen), receipt['operation_digest'])
        self.assertEqual(before, frozen)

    def test_v2_frozen_receipt_validates_embedded_request_and_binds_complete_identity(self):
        frozen = self.frozen(2)
        before = deepcopy(frozen)
        receipt = self.receipt(frozen)
        self.assertEqual('r22-m4-nx-original.v1', frozen['request']['material']['origin_profile'])
        self.assertEqual(codec.canonical_digest(frozen), receipt['operation_digest'])
        self.assertNotEqual(codec.canonical_digest(self.frozen()), receipt['operation_digest'])
        self.assertEqual(before, frozen)

    def test_unknown_and_nonstring_embedded_versions_reject_as_schema_errors(self):
        versions = ('newrouge.b-route-adoption-request.v3',
                    'newrouge.b-route-adoption-operation.v2', 'unknown',
                    None, False, 7, [], {})
        for version in versions:
            with self.subTest(version=version):
                frozen = self.frozen(2)
                frozen['request']['schema_version'] = version
                self.assert_schema_rejected(frozen)

    def test_v2_missing_origin_profile_rejects_before_receipt_projection(self):
        frozen = self.frozen(2)
        del frozen['request']['material']['origin_profile']
        self.assert_schema_rejected(frozen)

    def test_v2_foreign_origin_profile_rejects_before_receipt_projection(self):
        frozen = self.frozen(2)
        frozen['request']['material']['origin_profile'] = 'caller-selected-origin'
        self.assert_schema_rejected(frozen)

    def test_v1_cannot_smuggle_v2_origin_profile(self):
        frozen = self.frozen()
        frozen['request']['material']['origin_profile'] = 'r22-m4-nx-original.v1'
        self.assert_schema_rejected(frozen)

    def test_missing_and_malformed_embedded_request_reject_before_interpretation(self):
        frozen = self.frozen()
        del frozen['request']
        self.assert_schema_rejected(frozen)
        for request in (None, [], {}, 'request'):
            with self.subTest(request=request):
                frozen = self.frozen()
                frozen['request'] = request
                self.assert_schema_rejected(frozen)

    def test_frozen_and_target_shapes_remain_closed_with_no_version_override(self):
        for version in (1, 2):
            for mutation in ('header', 'extra', 'target'):
                with self.subTest(version=version, mutation=mutation):
                    frozen = self.frozen(version)
                    if mutation == 'header':
                        frozen['schema_version'] = 'newrouge.b-route-adoption-operation.v2'
                    elif mutation == 'extra':
                        frozen['caller_authority'] = True
                    else:
                        del frozen['targets'][0]['verification_mode']
                    self.assert_schema_rejected(frozen)
