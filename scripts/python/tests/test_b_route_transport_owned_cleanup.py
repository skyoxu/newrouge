"""UNEXECUTED neutral cleanup-role regressions; no model or process is started.

Only common._terminate_process_tree's real code/frame is exercised. Its run
call is intercepted with a data callback and a neutral process double; neither
the double nor these tests supplies SourceCapture, transport, PID/OS, grant or
financial proof. Root must import the candidate runtime through its real host.
"""
import inspect
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import _b_route_segmented_runtime as runtime
import _planning_skill_common as common


class NeutralProcess:
    pid = 41001

    def __init__(self):
        self.terminal = False

    def poll(self):
        return 0 if self.terminal else None

    def kill(self):
        raise AssertionError('neutral interception must not reach a real kill')


class TransportOwnedCleanupTests(unittest.TestCase):
    def test_scope_owns_contextmanager_and_predicates_are_plain(self):
        self.assertTrue(inspect.isgeneratorfunction(runtime._source_runner_scope.__wrapped__))
        self.assertFalse(hasattr(runtime._is_original_owned_cleanup, '__wrapped__'))
        self.assertFalse(hasattr(runtime._preserve_transport_primary, '__wrapped__'))
        self.assertIs(runtime._is_original_owned_cleanup(None, None, None, None, None, [], (), {}), False)

    def call_original_cleanup(self, *, owned=None, changed_kwargs=None, changed_command=None, expected_file=None):
        proc = NeutralProcess()
        if owned is None:
            owned = proc
        observed = []
        cleanup = common._terminate_process_tree

        def intercepted_run(command, **run_kwargs):
            self.assertEqual(command, ['taskkill', '/PID', str(proc.pid), '/T', '/F'])
            self.assertEqual(run_kwargs, {'stdout':common.subprocess.DEVNULL,
                'stderr':common.subprocess.DEVNULL, 'timeout':15, 'check':False})
            popen_kwargs = {'stdout':common.subprocess.DEVNULL, 'stderr':common.subprocess.DEVNULL}
            if changed_kwargs is not None:
                popen_kwargs = changed_kwargs
            result = runtime._is_original_owned_cleanup(owned, common, cleanup, cleanup.__code__,
                expected_file or Path(common.__file__),
                command if changed_command is None else changed_command, (), popen_kwargs)
            observed.append(result)
            proc.terminal = True

        with patch.object(common.subprocess, 'run', intercepted_run):
            common._terminate_process_tree(proc)
        return observed

    @unittest.skipUnless(os.name == 'nt', 'original Windows taskkill branch')
    def test_real_original_cleanup_frame_accepts_only_exact_owned_child(self):
        self.assertEqual(self.call_original_cleanup(), [True])

    @unittest.skipUnless(os.name == 'nt', 'original Windows taskkill branch')
    def test_same_pid_different_process_object_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'same_original_owned_cleanup_process'):
            self.call_original_cleanup(owned=NeutralProcess())

    @unittest.skipUnless(os.name == 'nt', 'original Windows taskkill branch')
    def test_altered_cleanup_options_and_source_filename_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'original_owned_cleanup_Popen_arguments'):
            self.call_original_cleanup(changed_kwargs={'stdout':common.subprocess.PIPE,
                'stderr':common.subprocess.DEVNULL})
        with self.assertRaisesRegex(ValueError, 'original_cleanup_code_globals_file'):
            self.call_original_cleanup(expected_file=Path(common.__file__).with_name('unrelated.py'))

    @unittest.skipUnless(os.name == 'nt', 'original Windows taskkill branch')
    def test_altered_pid_command_never_acquires_cleanup_role(self):
        self.assertEqual(self.call_original_cleanup(
            changed_command=['taskkill', '/PID', '41002', '/T', '/F']), [False])

    def test_exact_command_without_original_cleanup_frame_is_rejected(self):
        child = NeutralProcess()
        cleanup = common._terminate_process_tree
        with self.assertRaisesRegex(ValueError, 'original_owned_cleanup_frame_required'):
            runtime._is_original_owned_cleanup(child, common, cleanup, cleanup.__code__,
                Path(common.__file__), ['taskkill', '/PID', str(child.pid), '/T', '/F'], (),
                {'stdout':common.subprocess.DEVNULL, 'stderr':common.subprocess.DEVNULL})

    def test_substituted_cleanup_code_is_rejected_before_frame_search(self):
        child = NeutralProcess()
        cleanup = common._terminate_process_tree
        unrelated_code = (lambda: None).__code__
        with self.assertRaisesRegex(ValueError, 'original_cleanup_code_globals_file'):
            runtime._is_original_owned_cleanup(child, common, cleanup, unrelated_code,
                Path(common.__file__), ['taskkill', '/PID', str(child.pid), '/T', '/F'], (),
                {'stdout':common.subprocess.DEVNULL, 'stderr':common.subprocess.DEVNULL})
