"""UNEXECUTED focused unit candidates for the new owner after Root integration.

No test here claims a real native execution or validates the real 180 MB archive.
The issuance tests explicitly substitute the expensive already-verified facts;
the filesystem support bytes and opaque-identity/closing gates remain real.
Root must add/select the independent archive/held-receipt integration controls
under its fixed read-only roles before using this owner on the real operation.
"""
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import _b_route_retained_execution as retained


class RetainedExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory(prefix='retained-unit-')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name).resolve()
        target = patch.object(retained, 'TARGET', self.root)
        target.start()
        self.addCleanup(target.stop)

    def test_other_operation_keeps_default_fresh_without_support_or_execution_io(self):
        with patch.object(retained, '_record') as record, patch.object(retained, '_execution') as execution:
            self.assertIsNone(retained.capture_for_material(self.root, operation_id='OTHER',
                                                           material={}, review_ref={}))
        record.assert_not_called()
        execution.assert_not_called()

    def test_designated_operation_missing_support_never_falls_back_to_new_execution(self):
        with patch.object(retained, '_execution') as execution:
            with self.assertRaisesRegex(ValueError, 'requires admitted retained binding; no fresh fallback'):
                retained.capture_for_material(self.root, operation_id=retained.OPERATION,
                                              material={}, review_ref={})
        execution.assert_not_called()

    def test_dictionary_and_unissued_same_class_token_reject_before_any_read(self):
        with patch.object(retained, '_read') as read:
            for token in ({'native': {}}, retained._Action()):
                with self.subTest(kind=type(token).__name__):
                    with self.assertRaisesRegex(ValueError, 'owner-issued action token required'):
                        retained.native_from_action(self.root, token, operation_id=retained.OPERATION)
        read.assert_not_called()

    def _support(self):
        record = {'schema_version': retained.SCHEMA, 'material': {'sample': 1},
                  'review_ref': {'sample': 'review'}, 'consumer_policy_identity': 'fixture-only'}
        path = self.root / retained.binding_path(retained.OPERATION)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(record), encoding='utf-8')
        return record, path

    def test_real_support_disk_pins_and_opaque_token_close_without_transport(self):
        record, path = self._support()
        native = {'fixture_only': ['complete object']}
        # This is the explicit synthetic execution/current-authority seam.
        # No real source/reader/archive or process is accessed by this test.
        verifier = Mock()
        with patch.object(retained, '_binding_value', return_value=(record, native)), \
             patch.object(retained, '_original_reader', return_value=nullcontext(verifier)):
            action = retained.capture_for_material(self.root, operation_id=retained.OPERATION,
                material=record['material'], review_ref=record['review_ref'])
            value = retained.native_from_action(self.root, action, operation_id=retained.OPERATION)
            self.assertEqual(value, native)
            self.assertIsNot(value, native)
            value['fixture_only'].append('caller mutation')
            self.assertEqual(native, {'fixture_only': ['complete object']})
            path.write_text(json.dumps({**record, 'consumer_policy_identity': 'changed'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'immutable support changed'):
                retained.verify_action(self.root, action, operation_id=retained.OPERATION)
        verifier.verify_capture.assert_called_once_with(retained.ORIGIN, native)

    def test_material_boolean_number_change_and_current_policy_drift_are_not_equal(self):
        record, _ = self._support()
        with patch.object(retained, '_binding_value', return_value=(record, {})):
            with self.assertRaisesRegex(ValueError, 'same retained operation/material/source/current authority'):
                retained.capture_for_material(self.root, operation_id=retained.OPERATION,
                    material={'sample': True}, review_ref=record['review_ref'])
        changed = {**record, 'consumer_policy_identity': 'new-policy'}
        with patch.object(retained, '_binding_value', return_value=(changed, {})):
            with self.assertRaisesRegex(ValueError, 'same retained operation/material/source/current authority'):
                retained.capture_for_material(self.root, operation_id=retained.OPERATION,
                    material=record['material'], review_ref=record['review_ref'])
