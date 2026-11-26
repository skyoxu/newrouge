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
                     'published_history', 'qualified_render_retention_v2',
                     'compensation_partition', 'compensation_segments', 'compensation_segmented_execution',
                     'compensation_review_repair', 'compensation_multiview_owner', 'compensation_multiview_transport_v2',
                     'initial_legacy', 'qualified_historical_v3', 'planning_input', 'candidate',
                     'adoption', 'adoption_cli', 'adoption_concurrency', 'adoption_journal',
                     'adoption_projection', 'adoption_r10_capture', 'adoption_r10_reader',
                     'adoption_r19_reader', 'adoption_review', 'operation_leases',
                     'operation_scope', 'public_context', 'qualified_public_context', 'task_preview',
                     'task_compilation', 'task_resolver', 'chapter4_binding', 'input_set', 'stage5_obligations', 'chapter5_readiness', 'chapter6_gate', 'chapter6_recovery', 'defect_routing', 'chapter7_slice', 'entrypoint_parity', 'impact_closure', 'verification_scope', 'scope_runner', 'evidence_reuse', 'completion_verdict', 'knowledge_projection', 'planning_page', 'observability', 'consumer_alignment'):
            selector = 'scripts.python.tests.test_b_route_' + name
            self.assertEqual(1, selected.count(selector))
            self.assertFalse(any(value.startswith(selector + '.') for value in selected))
        for selector in ('scripts.python.tests.test_b_route_recovery_funding',
                         'scripts.python.tests.test_mvg_capability_worker',
                         'scripts.python.tests.test_mvg_capability_recovery',
                         'scripts.python.tests.test_mvg_recovery_fixthrough',
                         'scripts.python.tests.test_mvg_global_audit.GlobalAuditTests.test_public_cli_and_builder_preserve_exact_run_artifact_and_hash',
                         'scripts.python.tests.test_mvg_global_audit.GlobalAuditTests.test_unresolved_resolution_cannot_become_admitted',
                         'scripts.python.tests.test_mvg_global_audit.GlobalAuditTests.test_audit_recomputes_completion_and_source_gap_verdict',
                         'scripts.python.tests.test_mvg_global_audit_boundaries',
                         'scripts.python.tests.test_mvg_acceptance',
                         'scripts.python.tests.test_milestone_incremental_workflow',
                         'scripts.python.tests.test_milestone_authority_regression',
                         'scripts.python.tests.test_milestone_incremental_hotfixes',
                         'scripts.python.tests.test_milestone_two_stage_integration',
                         'scripts.python.tests.test_chapter7_backlog_gap',
                         'scripts.python.tests.test_topology_frontend',
                         'scripts.python.tests.test_inherited_pipe_cleanup'):
            self.assertIn(selector, selected)

    def test_windows_recovery_ci_runner_enforces_four_controls_windows_only_and_sha_match(self):
        import importlib.util
        import json
        script = ROOT / 'scripts/ci/run_b_route_windows_recovery_checks.py'
        spec = importlib.util.spec_from_file_location('b_route_windows_recovery_checks_test', script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in mod.SELECTORS)
        self.assertEqual(4, suite.countTestCases())
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            (temp_root / 'scripts/python').mkdir(parents=True)
            (temp_root / 'scripts/sc').mkdir(parents=True)
            with patch.object(mod, 'ROOT', temp_root), \
                    patch.object(mod.subprocess, 'check_output', return_value='deadbeef\n'), \
                    patch.dict(os.environ, {'GITHUB_SHA': 'deadbeef'}, clear=False), \
                    patch.object(mod.os, 'name', 'posix'):
                self.assertEqual(2, mod.main())
            summary = json.loads((temp_root / 'logs/ci/b-route-deterministic/windows-recovery/summary.json').read_text(encoding='utf-8'))
            self.assertEqual('blocked', summary['status'])
            self.assertEqual(0, summary['tests_run'])
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            (temp_root / 'scripts/python').mkdir(parents=True)
            (temp_root / 'scripts/sc').mkdir(parents=True)
            with patch.object(mod, 'ROOT', temp_root), \
                    patch.object(mod.subprocess, 'check_output', return_value='deadbeef\n'), \
                    patch.dict(os.environ, {'GITHUB_SHA': 'different_sha'}, clear=False), \
                    self.assertRaises(RuntimeError):
                mod.main()

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
        self.assertEqual(environment['ADOPTION_TEST_TEMP'], 'private-temp')
        self.assertEqual(environment['FROZEN_READER_TEST_TEMP'], 'private-temp')
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
        self.assertIn('timeout-minutes: 90', workflow)
        self.assertIn("- name: Verify clean-clone published adoption read and tamper rejection", workflow)
        self.assertIn("empty stdout (rc={proc.returncode})", workflow)
        self.assertIn("- 'scripts/python/_b_route_chapter6_recovery.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_defect_routing.py'", workflow)
        self.assertIn("- 'scripts/python/check_b_route_defect_routing.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_chapter7_slice.py'", workflow)
        self.assertIn("- 'scripts/python/check_b_route_chapter7_slice.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_entrypoint_parity.py'", workflow)
        self.assertIn("- 'scripts/python/check_b_route_entrypoint_parity.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_impact_closure.py'", workflow)
        self.assertIn("- 'scripts/python/compute_b_route_impact_closure.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_verification_scope.py'", workflow)
        self.assertIn("- 'scripts/python/build_b_route_verification_scope.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_scope_runner.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_evidence_reuse.py'", workflow)
        self.assertIn("- 'scripts/python/_b_route_completion_verdict.py'", workflow)
        self.assertIn("- 'scripts/python/check_b_route_completion_verdict.py'", workflow)
        self.assertIn("- 'scripts/python/milestone_incremental_handoff.py'", workflow)
        self.assertIn("- 'scripts/python/tests/test_milestone_*.py'", workflow)
        self.assertIn("- 'scripts/python/run_mvg_acceptance.py'", workflow)
        self.assertIn("- 'scripts/python/_mvg_execution.py'", workflow)
        self.assertIn("- 'docs/planning/b-route/schemas/**'", workflow)
        self.assertIn("- 'scripts/python/_project_health_http.py'", workflow)
        self.assertIn("- 'scripts/python/project_health_runtime.py'", workflow)
        self.assertIn("- 'scripts/python/project_health_knowledge.py'", workflow)
        self.assertIn("- 'scripts/python/_project_health_*.py'", workflow)
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
            'scripts/python/gemini_isolated_model_runner.py',
            'scripts/python/_gemini_cli_protocol.py',
            'scripts/python/_isolated_runner_registry.py',
            'scripts/python/_b_route_3b_segmented_input.py',
            'scripts/python/_b_route_3b_segmented_runtime.py',
            'scripts/python/b_route_adoption.py',
            'scripts/python/preview_b_route_task_changes.py',
            'scripts/python/compile_b_route_tasks.py',
            'scripts/python/resolve_b_route_task_origin.py',
            'scripts/python/refine_b_route_chapter4_binding.py',
            'scripts/python/resolve_b_route_input_set.py',
            'scripts/python/bind_b_route_stage5_obligations.py',
            'scripts/python/reconcile_b_route_chapter5_readiness.py',
            'scripts/python/check_b_route_chapter6_gate.py',
            'scripts/python/_b_route_chapter6_recovery.py',
            'scripts/python/_b_route_defect_routing.py',
            'scripts/python/check_b_route_defect_routing.py',
            'scripts/python/_b_route_chapter7_slice.py',
            'scripts/python/check_b_route_chapter7_slice.py',
            'scripts/python/_b_route_entrypoint_parity.py',
            'scripts/python/check_b_route_entrypoint_parity.py',
            'scripts/python/_b_route_impact_closure.py',
            'scripts/python/compute_b_route_impact_closure.py',
            'scripts/python/_b_route_verification_scope.py',
            'scripts/python/build_b_route_verification_scope.py',
            'scripts/python/_b_route_scope_runner.py',
            'scripts/python/_b_route_evidence_reuse.py',
            'scripts/python/_b_route_completion_verdict.py',
            'scripts/python/check_b_route_completion_verdict.py',
            'scripts/python/_b_route_knowledge_projection.py',
            'scripts/python/query_b_route_knowledge_projection.py',
            'scripts/python/_b_route_planning_page.py',
            'scripts/python/query_b_route_planning_page.py',
            'scripts/python/_b_route_observability.py',
            'scripts/python/query_b_route_observability.py',
            'scripts/python/_b_route_consumer_alignment.py',
            'scripts/python/audit_b_route_consumer_alignment.py',
            'scripts/python/project_health_planning.js',
            'scripts/python/project_health_topology.js',
            'scripts/python/project_health_topology.html',
            'scripts/python/project_health_scenes.html',
            'scripts/python/project_health_mvg_versions.js',
            'scripts/python/project_health_knowledge.js',
            'scripts/python/tests/js/test_b_route_planning_page_ui.cjs',
            'scripts/python/tests/js/test_knowledge_planning.cjs',
            'scripts/python/tests/js/test_topology_node_kinds.cjs',
            'scripts/python/_semantic_topology.py',
            'scripts/python/milestone_incremental_handoff.py',
            'scripts/python/run_mvg_acceptance.py',
            'scripts/python/_mvg_execution.py',
            'docs/planning/b-route/schemas/verification-scope.schema.json',
            'scripts/python/_project_health_http.py',
            'scripts/python/project_health_runtime.py',
            'scripts/python/project_health_knowledge.py',
            'scripts/python/_project_health_runtime_snapshot.py',
            'scripts/python/_project_health_server.py',
            'scripts/python/run_chapter7_ui_wiring.py',
            'scripts/python/run_chapter7_backlog_gap.py',
            'scripts/python/resume_task.py',
            'scripts/python/chapter6_route.py',
            'scripts/python/inspect_run.py',
            'scripts/python/_chapter6_recovery_common.py',
            'scripts/python/run_single_task_chapter6_lane.py',
            'scripts/python/update_task_test_refs_from_acceptance_refs.py',
            'scripts/python/apply_chapter7_status_patch.py',
            'scripts/python/run_single_task_light_lane.py',
            'scripts/sc/check_tdd_execution_plan.py',
            'scripts/sc/llm_generate_tests_from_acceptance_refs.py',
            'scripts/sc/build/tdd.py',
            'scripts/sc/run_review_pipeline.py',
            'scripts/sc/llm_review_needs_fix_fast.py',
            'scripts/sc/_llm_review_engine.py',
            'scripts/sc/acceptance_check.py',
            'scripts/sc/test.py',
            'scripts/python/_chapter5_contract_bindings.py',
            'scripts/python/chapter5_semantic_reconciliation.py',
            'scripts/python/refresh_chapter_knowledge.py',
            'scripts/python/run_chapter5_guarded.py',
            'docs/workflows/llm-routing.json',
            'scripts/python/_capability_input_integrity.py',
            'scripts/sc/_llm_backend.py',
            'scripts/ci/prepare_b_route_runtime.ps1',
            'scripts/python/tests/test_mvg_capability_worker.py',
            'scripts/python/tests/fixtures/story25_loop3_planning_input_base.py.txt',
            'scripts/python/tests/fixtures/story25_loop3_worker_lifetime_base.py.txt',
            'scripts/python/tests/fixtures/codex_app_server_stdio_child.py',
            'scripts/python/tests/fixtures/b_route_bound_protocol_runner.py',
            'scripts/python/tests/fixtures/b_route_fake_gemini_cli.py',
            'scripts/python/tests/fixtures/story25_host_fault_base_sources.json',
            'AGENTS.md',
            'workflow.md',
            'docs/workflows/b-route-consumer-alignment.md',
            'docs/workflows/stable-public-entrypoints.md',
            'docs/workflows/script-entrypoints-index.md',
            'docs/workflows/mvg-integration-acceptance.md',
            'docs/workflows/chapter3-source-set.json',
            '.agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md',
            '.agents/skills/maintain-knowledge-base/SKILL.md',
            'docs/adr/ADR-0040-b-route-stages-authority-and-activation.md',
            'docs/architecture/ADR_INDEX_GODOT.md',
            'knowledge/policies/source-exclusions.v1.json',
        ])
        for path in governed:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path)


if __name__ == '__main__':
    unittest.main()
