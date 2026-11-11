"""UNEXECUTED actual causal-close helper behavior, no native/source mocks.

The close callbacks are neutral DATA operations testing exception precedence;
no genuine SourceCapture/transport, PID or financial proof is simulated.
"""
import unittest
import _b_route_segmented_runtime as runtime


class TransportPrimaryErrorTests(unittest.TestCase):
    def test_no_primary_original_close_success_runs_once(self):
        calls=[]
        runtime._preserve_transport_primary(None,lambda:calls.append('original-close'))
        self.assertEqual(calls,['original-close'])

    def test_no_primary_same_close_error_is_still_raised(self):
        error=ValueError('neutral actual_runner_started_once failure')
        def close():raise error
        with self.assertRaises(ValueError) as caught:
            runtime._preserve_transport_primary(None,close)
        self.assertIs(caught.exception,error)

    def test_primary_identity_and_unknown_close_failure_are_both_retained(self):
        primary=OSError('neutral original constructor failure')
        secondary=ValueError('neutral missing child_pid close evidence')
        facts={'closed':False,'data':None,'child_pid':None}
        def close():raise secondary
        try:
            try:raise primary
            finally:runtime._preserve_transport_primary(primary,close)
        except OSError as caught:
            self.assertIs(caught,primary)
            self.assertTrue(any(repr(secondary) in note for note in caught.__notes__))
        else:self.fail('primary must remain raised')
        self.assertEqual(facts,{'closed':False,'data':None,'child_pid':None})
