"""Offline CI selector and invocation controls; no provider or test child starts."""
import ast
import fnmatch
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / 'scripts/python/run_gate_bundle.py'
WORKFLOW = ROOT / '.github/workflows/b-route-runtime-deterministic.yml'
PREPARE = ROOT / 'scripts/ci/prepare_b_route_runtime.ps1'


def selector_names():
    tree = ast.parse(BUNDLE.read_text(encoding='utf-8'))
    value = next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name)
            and target.id == 'B_ROUTE_RUNTIME_DETERMINISTIC_TESTS' for target in node.targets))
    return ast.literal_eval(value)


class RuntimeCITests(unittest.TestCase):
    def test_complete_commit_modules_are_selected_once_without_replacing_existing_owners(self):
        selected = selector_names()
        for name in ('commit', 'commit_e1', 'commit_projection', 'commit_images', 'commit_recovery', 'compensation',
                     'initial_legacy', 'qualified_historical_v3'):
            selector = 'scripts.python.tests.test_b_route_' + name
            self.assertEqual(1, selected.count(selector))
            self.assertFalse(any(value.startswith(selector + '.') for value in selected))
        for selector in ('scripts.python.tests.test_b_route_recovery_funding',
                         'scripts.python.tests.test_mvg_capability_worker',
                         'scripts.python.tests.test_inherited_pipe_cleanup'):
            self.assertIn(selector, selected)

    def test_dedicated_mode_invokes_only_the_maintained_runtime_gate(self):
        from scripts.python import run_gate_bundle as gates
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {'BR_PYTHON': ''}), \
                patch.object(sys, 'argv', ['run_gate_bundle.py', '--mode', 'b-route-runtime',
                    '--out-dir', temporary, '--skip-prune-runs']), \
                patch.object(gates, '_run_group', return_value=(7, {})) as run:
            self.assertEqual(gates.main(), 7)
        self.assertEqual(run.call_count, 1)
        mode, commands = run.call_args.args[:2]
        self.assertEqual(mode, 'b-route-runtime')
        self.assertEqual(len(commands), 1)
        command = commands[0]['cmd']
        self.assertEqual(command[:4], [sys.executable, '-B', '-m', 'unittest'])
        self.assertEqual(command[4:-1], list(gates.B_ROUTE_RUNTIME_DETERMINISTIC_TESTS))

    def test_runtime_child_uses_local_high_environment_and_failed_gate_stays_failed(self):
        from scripts.python import run_gate_bundle as gates
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(gates, '_run_command', return_value=(9, 'synthetic gate failure')) as run:
            code, summary = gates._run_group('b-route-runtime', [gates._b_route_runtime_gate()],
                False, Path(temporary), 'synthetic', ROOT, [])
        self.assertEqual(code, 1)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(summary['gates'][0]['test_selectors'], list(gates.B_ROUTE_RUNTIME_DETERMINISTIC_TESTS))
        environment = run.call_args.kwargs['environment']
        self.assertEqual(environment['NEWROGUE_CODEX_REASONING_EFFORT'], 'high')
        self.assertEqual(environment['NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT'], 'high')
        self.assertEqual(environment['PYTHONNOUSERSITE'], '1')
        self.assertEqual(environment['PYTHONPATH'].split(os.pathsep),
            [str(ROOT / 'scripts/python'), str(ROOT / 'scripts/python/tests'),
             str(ROOT / 'scripts/sc'), str(ROOT)])

    def test_private_runtime_interpreter_cache_and_temp_do_not_replace_other_hard_commands(self):
        from scripts.python import run_gate_bundle as gates
        private = {'BR_PYTHON': 'private-python.exe', 'BR_TIKTOKEN_CACHE_DIR': 'private-cache',
                   'BR_TEST_TEMP': 'private-temp'}
        with patch.dict(os.environ, private), tempfile.TemporaryDirectory() as temporary, \
                patch.object(gates, '_run_command', return_value=(0, '')) as run:
            commands = [gates._b_route_runtime_gate(), {'name': 'unrelated', 'cmd': ['py', '-3', 'original.py']}]
            code, _ = gates._run_group('hard', commands, False, Path(temporary), 'synthetic', ROOT, [])
        self.assertEqual(code, 0)
        runtime_call, original_call = run.call_args_list
        self.assertEqual(runtime_call.args[0][0], 'private-python.exe')
        environment = runtime_call.kwargs['environment']
        self.assertEqual(environment['TIKTOKEN_CACHE_DIR'], 'private-cache')
        self.assertEqual((environment['TEMP'], environment['TMP']), ('private-temp', 'private-temp'))
        self.assertEqual(original_call.args[0], ['py', '-3', 'original.py'])
        self.assertNotIn('environment', original_call.kwargs)

    def test_all_actual_ci_runtime_callers_prepare_the_same_private_environment_before_the_gate(self):
        workflows = ROOT / '.github/workflows'
        callers = {}
        for path in workflows.glob('*.yml'):
            text = path.read_text(encoding='utf-8')
            if any('run_gate_bundle.py --mode ' + mode in text for mode in ('hard', 'all', 'b-route-runtime')):
                callers[path.name] = text
        self.assertEqual(set(callers), {'b-route-runtime-deterministic.yml', 'windows-quality-gate.yml', 'ci-windows.yml'})
        for name, text in callers.items():
            with self.subTest(workflow=name):
                prepare = text.index('./scripts/ci/prepare_b_route_runtime.ps1')
                self.assertLess(prepare, text.index('scripts/python/run_gate_bundle.py --mode'))
                self.assertEqual(text.count('./scripts/ci/prepare_b_route_runtime.ps1'), 1)
                self.assertIn('if: always()', text)
                self.assertIn('logs/ci/', text)
                self.assertNotIn('continue-on-error: true\n        run: |\n          ./scripts/ci/prepare_b_route_runtime.ps1', text)
        production = (workflows / 'planning-production-acceptance.yml').read_text(encoding='utf-8')
        self.assertNotIn('BR_PYTHON', production)
        self.assertNotIn('--mode b-route-runtime', production)

    def test_shared_preparation_keeps_official_dependencies_and_both_real_encoding_caches(self):
        text = PREPARE.read_text(encoding='utf-8')
        self.assertIn('python -m venv $ciEnvironmentRoot', text)
        self.assertIn('& $ciPython -m pip --isolated install --no-input --index-url https://pypi.org/simple', text)
        self.assertIn("'jsonschema==4.26.0' 'tiktoken==0.14.0'", text)
        self.assertIn("for name in ('cl100k_base', 'o200k_base'):", text)
        self.assertIn('tiktoken.get_encoding(name)', text)
        for value in ('BR_PYTHON=', 'BR_TIKTOKEN_CACHE_DIR=', 'BR_TEST_TEMP=',
                      'install-report.json', 'encodings.json', 'hashlib.sha256'):
            self.assertIn(value, text)
        self.assertNotIn('GITHUB_PATH', text)
        self.assertNotIn('Activate.ps1', text)
        self.assertNotIn('--user', text)

    def test_recovery_producer_and_historical_negative_controls_remain_in_the_maintenance_selection(self):
        required = ('provider_schema', 'indexed_review', 'review_schema_delivery', 'review_recovery',
                    'partial_generation_recovery', 'input_path_recovery', 'input_path_runtime',
                    'synthesis_recovery', 'mvg_recovery_prepare', 'mvg_synthesis_recovery',
                    'mvg_recovery_wiring', 'worker_recovery', 'source_epoch', 'source_epoch_v2',
                    'source_epoch_scope', 'mvg_source_epoch', 'selector_source_epoch',
                    'execution_transition_ordering', 'loop4_runtime')
        selected = set(selector_names())
        self.assertTrue({'scripts.python.tests.test_b_route_' + name for name in required} <= selected)
        self.assertIn('scripts.python.tests.test_codex_isolated_model_runner', selected)
        self.assertIn('scripts.python.tests.test_capability_input_integrity', selected)

    def test_every_maintained_selector_resolves_before_unittest_import(self):
        selectors = selector_names()
        self.assertEqual(len(selectors), len(set(selectors)))
        for selector in selectors:
            with self.subTest(selector=selector):
                parts = selector.split('.')
                module_parts, members = parts[:4], parts[4:]
                self.assertEqual(module_parts[:3], ['scripts', 'python', 'tests'])
                source = ROOT.joinpath(*module_parts).with_suffix('.py')
                tree = ast.parse(source.read_text(encoding='utf-8'))
                if not members:
                    self.assertTrue(any(isinstance(node, ast.FunctionDef)
                        and node.name.startswith('test_') for node in ast.walk(tree)))
                    continue
                owner = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == members[0])
                self.assertLessEqual(len(members), 2)
                if len(members) == 2:
                    self.assertTrue(any(isinstance(node, ast.FunctionDef)
                        and node.name == members[1] for node in owner.body))

    def test_full_codec_and_source_audit_modules_use_the_shared_maintenance_gate(self):
        required = ('compact_literal', 'compact_literal_v3', 'tuplecompact_v2',
                    'input_compact_runtime', 'source_audit', 'audit_partial_reuse',
                    'audit_recovery', 'review_source_policy')
        selected = selector_names()
        for name in required:
            with self.subTest(module=name):
                selector = 'scripts.python.tests.test_b_route_' + name
                self.assertEqual(selected.count(selector), 1)
                # A single class/method does not cover the full maintained module.
                self.assertFalse(any(value.startswith(selector + '.') for value in selected))

    def test_funding_and_os_worker_modules_are_selected_in_full_exactly_once(self):
        selected = selector_names()
        for module in ('test_b_route_recovery_funding', 'test_mvg_capability_worker'):
            with self.subTest(module=module):
                selector = 'scripts.python.tests.' + module
                self.assertEqual(selected.count(selector), 1)
                self.assertFalse(any(value.startswith(selector + '.') for value in selected))

    def test_pr_paths_include_selected_tests_and_actual_pipe_fixture_owners(self):
        workflow = WORKFLOW.read_text(encoding='utf-8')
        path_block = workflow.split('    paths:\n', 1)[1].split('  workflow_dispatch:', 1)[0]
        patterns = [line.strip()[3:-1] for line in path_block.splitlines()
            if line.strip().startswith("- '") and line.strip().endswith("'")]
        paths = [selector.split('.')[3] for selector in selector_names()]
        governed = ['scripts/python/tests/' + name + '.py' for name in paths]
        governed.extend([
            'scripts/python/_mvg_worker_lifetime.py',
            'scripts/python/_planning_skill_common.py',
            'scripts/python/_codex_app_server.py',
            'scripts/python/_planning_execution_binding.py',
            'scripts/python/run_gate_bundle.py',
            'scripts/python/b_route_worker_recovery.py',
            'scripts/python/openai_isolated_model_runner.py',
            'scripts/python/_capability_input_integrity.py',
            'scripts/sc/_llm_backend.py',
            'scripts/ci/prepare_b_route_runtime.ps1',
            'scripts/python/tests/test_mvg_capability_worker.py',
            'scripts/python/tests/fixtures/story25_loop3_planning_input_base.py.txt',
            'scripts/python/tests/fixtures/story25_loop3_worker_lifetime_base.py.txt',
            'scripts/python/tests/fixtures/codex_app_server_stdio_child.py',
            'scripts/python/tests/fixtures/b_route_bound_protocol_runner.py',
            'scripts/python/tests/fixtures/story25_host_fault_base_sources.json',
        ])
        for path in governed:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path)


if __name__ == '__main__':
    unittest.main()
