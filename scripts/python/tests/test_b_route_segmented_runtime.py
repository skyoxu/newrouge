"""Synthetic upstream qualification; real new birth, registry and file journal.

No model, subprocess, actual Nx, original audit replay or native qualification is
performed. Historical audit/fee observations and runner --describe are explicit
test boundaries. New-runtime preparation, its real original OS locks, publication
journal, raw references and immutable birth checks are exercised unchanged.
Only Root executes these methods after the shared source barrier.
"""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import secrets
import shutil
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_sources as sources
import _b_route_segmented_runtime as runtime
import _b_route_segmented_workflow as core
import _b_route_segmented_journal as journal


class SegmentedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(os.environ.get('TEMP', r'C:\Windows\TEMP')).absolute()
        self.name = 'sr23_' + secrets.token_hex(5)
        self.root = self.parent / self.name
        self.root.mkdir(exist_ok=False)
        self.success = False
        self.mvg_count = 12
        self.policy_owner = runtime.policy_identity
        self.stack = ExitStack()
        self.stack.enter_context(patch.dict(os.environ, {}, clear=False))
        os.environ.pop('SC_MVG_RECOVERY_ROOT', None)
        os.environ.pop('SC_MVG_RECOVERY_EPOCH', None)
        self.policy = {'schema_version': 'synthetic-upstream-source-boundary', 'files': {},
                       'source_root': str(self.root / 'synthetic-source'), 'model_source_files': {}}
        actual_source = Path(runtime.__file__).absolute().parents[2]
        for relative in runtime._DESCRIBE_NAMES:
            original = (actual_source / relative).read_bytes()
            copied = Path(self.policy['source_root']) / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(original)
            self.policy['model_source_files'][relative] = codec.raw_digest(original)
        self.stack.enter_context(patch.object(runtime, 'policy_identity', return_value=deepcopy(self.policy)))
        self.stack.enter_context(patch.object(runtime.planning, 'rules_identity', return_value={'synthetic_rules': 1}))
        self.stack.enter_context(patch.object(runtime, '_capture_campaign', side_effect=self.campaign))
        self.stack.enter_context(patch.object(runtime, '_close_campaign', return_value=None))
        self.stack.enter_context(patch.object(runtime, '_describe', return_value={'supports_synthesis_budget': True}))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no subprocess or model in runtime fixture')))
        self.addCleanup(self.finish)

    def finish(self):
        self.stack.close()
        # Failed cases remain for Root's evidence. Cleanup never enumerates or
        # accepts an external/derived target: only this exact allocated child.
        result = getattr(self._outcome, 'result', None)
        failed = result is not None and any(test is self for test, _ in [*result.failures, *result.errors])
        if not failed and self.root.exists():
            self.assertEqual(self.root.parent.resolve(), self.parent.resolve())
            self.assertEqual(self.root.name, self.name)
            self.assertTrue(self.name.startswith('sr23_') and len(self.name) == 15)
            self.assertFalse(self.root.is_symlink())
            self.assertFalse(self.root.lstat().st_file_attributes & 0x400 if hasattr(self.root.lstat(), 'st_file_attributes') else False)
            shutil.rmtree(self.root)

    def write(self, relative, item):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(runtime.wire(item))
        return target

    def read(self, relative):
        return codec.strict_json_loads((self.root / relative).read_bytes())

    def source(self, planner='mvg', run_id='new'):
        original = self.root / 'docs/original.txt'
        original.parent.mkdir(exist_ok=True)
        if not original.exists():
            original.write_bytes(b'Preserve Q before R, shared state and non-Flow audit.\n')
        data = original.read_bytes()
        count = runtime.PROFILE[planner][2]
        manifest = core.freeze_manifest(self.root, run_id=run_id,
            materials=[{'material_id': 'source', 'path': 'docs/original.txt', 'version': 'v1',
                        'role': 'source', 'candidate_label': None, 'boundaries': [0, len(data)]}],
            candidates=[{'label': chr(65 + n), 'candidate_id': 'candidate-' + str(n + 1), 'material_ids': []}
                        for n in range(count)], final_required_segments=['source.0'])
        obligations = [{'obligation_id': 'original-complete-domain', 'kind': 'preservation',
                        'segment_ids': ['source.0'], 'dependency_ids': []}]
        domain = {'manifest': manifest, 'dimensions': ['source-fidelity'], 'obligations': obligations, 'dependency_edges': []}
        frozen = {'schema_version': runtime.HOST, 'inputs': {'dependencies': {'rules': {'synthetic_rules': 1}}}}
        frozen['input_identity'] = codec.canonical_digest(frozen)
        payload = {'run_id': run_id, 'planner': planner, 'frozen': frozen, 'source_identity': {
            'schema_version': runtime.SOURCE, 'planning_contract_ref': 'docs/contract.json',
            'audit_verifier_source': {'mode': 'current-source-owner'},
            'upstream_turns': [{'thread_id': 'synthetic-audit-thread', 'turn_id': 'synthetic-audit-turn'}]},
            'policy_identity': self.policy, 'domain': domain}
        token = runtime._SourceCapture(runtime._SEAL)
        runtime._SOURCES[token] = {'root': self.root, 'data': runtime.wire(payload),
            'files': (('docs/original.txt', data), ('docs/absent.txt', None)),
            'globs': runtime.wire([]), 'policy': runtime.wire(self.policy)}
        nodes, previous = [], {}
        labels = [row['label'] for row in manifest['candidates']]
        for phase in core.PHASES[:3]:
            for label in labels:
                node = phase.replace('independent-', '') + '-' + label
                nodes.append({'node_id': node, 'phase': phase, 'ordinal': len(nodes), 'candidate_labels': [label],
                    'segment_ids': ['source.0'], 'obligation_ids': ['original-complete-domain'],
                    'dependencies': [] if phase == 'generation' else [previous[label]], 'output_reserve': 2000, 'final': False})
                previous[label] = node
        nodes.append({'node_id': 'panel', 'phase': 'selection', 'ordinal': len(nodes), 'candidate_labels': labels,
            'segment_ids': ['source.0'], 'obligation_ids': ['original-complete-domain'],
            'dependencies': list(previous.values()), 'output_reserve': 2000, 'final': False})
        nodes.append({'node_id': 'final', 'phase': 'selection', 'ordinal': len(nodes), 'candidate_labels': labels,
            'segment_ids': ['source.0'], 'obligation_ids': ['original-complete-domain'],
            'dependencies': ['panel'], 'output_reserve': 2000, 'final': True})
        plan = core.build_plan(manifest, planner=planner, dimensions=domain['dimensions'], obligations=obligations,
                               dependency_edges=[], nodes=nodes)
        return token, plan

    def campaign(self, root):
        cap = [{'candidate': 'candidate-1', 'outcome': {'active_elapsed_seconds': 1}} for _ in range(11)]
        mvg = [{'candidate': 'candidate-1', 'outcome': {'active_elapsed_seconds': 1}} for _ in range(self.mvg_count)]
        snapshots = {runtime._OLD_CAP + '/run.json': {'schema_version': 'synthetic-old-native', 'calls': cap},
                     runtime._OLD_MVG + '/run.json': {'schema_version': 'synthetic-old-native', 'calls': mvg}}
        obs = SimpleNamespace(files={name: runtime.wire(item) for name, item in snapshots.items()},
                              json=lambda name: deepcopy(snapshots[name]))
        return runtime._CampaignCapture(self.root, obs, tuple(cap), tuple(mvg), None, {}, {}, (), 66, runtime._SEAL)

    def prepare(self, planner='mvg', run_id='new'):
        token, plan = self.source(planner, run_id)
        with patch.object(runtime, 'capture_source', return_value=token):
            result = runtime.prepare_run(self.root, run_id=run_id, planner=planner, plan=plan, planning_contract='docs/contract.json')
        run = runtime._homes(self.root, planner, run_id)
        return token, plan, result, run

    def test_real_zero_call_birth_has_directed_refs_original_index_and_journal(self):
        token, plan, result, run = self.prepare()
        state = self.read(result['run_ref'])
        born = self.read(state['segmented_born_ref']['path'])
        initial = self.read(born['initial_run_ref']['path'])
        self.assertNotIn('segmented_born_ref', initial)
        self.assertEqual(initial['capability_selection']['calls'], [])
        self.assertEqual(state['capability_selection']['total_invocations'], 0)
        self.assertEqual(state['b_route_campaign_funding']['paid_or_unknown_before_run'], 78)
        self.assertEqual(state['b_route_campaign_funding']['retained_profile_calls'], 12)
        runner_raw = (Path(self.policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py').read_bytes()
        self.assertEqual(state['runtime_identity']['runner']['raw_digest'], codec.raw_digest(runner_raw))
        self.assertEqual(state['runtime_identity']['runner']['raw_digest'],
            self.policy['model_source_files']['scripts/python/codex_isolated_model_runner.py'])
        self.assertFalse(state['formal_adoption'])
        registry = runtime.recovery.registry(self.root)
        entry = registry['segmented_runs']['runs'][0]
        self.assertEqual(entry['born_ref'], state['segmented_born_ref'])
        self.assertEqual(entry['head']['native_run_after_digest'], codec.raw_digest((run / 'run.json').read_bytes()))
        history = runtime._history(self.root, entry, state)
        self.assertEqual(history['charged_or_pending_calls'], 0)
        original_binding = deepcopy(state['recovery'])
        canonical = runtime._fixed_recovery_store(self.root, original_binding, entry['epoch'])
        self.assertEqual(canonical, runtime.recovery.store_root(self.root, state))
        self.assertEqual(canonical, (self.root / 'logs/ci/mvg-recovery').resolve())
        alternate_case = {**original_binding, 'store': original_binding['store'].swapcase()}
        self.assertEqual(runtime._fixed_recovery_store(self.root, alternate_case, entry['epoch']), canonical)
        self.assertEqual(state['recovery'], original_binding)
        invalid = [({**original_binding, 'epoch': True}, 'original_recovery_store_epoch'),
            ({**original_binding, 'extra': 1}, 'closed_original_recovery_store'),
            ({**original_binding, 'store': str(self.root / '.codex/auth.json')}, 'fixed_original_recovery_store_role'),
            ({**original_binding, 'store': str(self.root / 'foreign-store')}, 'fixed_original_recovery_store_role')]
        for binding, reason in invalid:
            with self.subTest(binding=binding), \
                 patch.object(Path, 'lstat', side_effect=AssertionError('reject foreign/invalid store before metadata')), \
                 patch.object(Path, 'read_bytes', side_effect=AssertionError('reject foreign/invalid store before bytes')):
                with self.assertRaisesRegex(core.SegmentedBlocked, reason):
                    runtime._fixed_recovery_store(self.root, binding, entry['epoch'])
        self.assertEqual(self.read(entry['head']['journal_ref'])['status'], 'complete')
        obs = sources.Observations(self.root)
        runtime._birth(self.root, run, state, plan, obs)
        obs.verify()
        with patch.object(runtime, 'capture_source', return_value=token), runtime.verified_run(self.root, run, plan):
            witness = runtime.segmented_run_contract(self.root, state, run, plan_digest=plan['plan_digest'], protocol=core.PROTOCOL)
            self.assertEqual(witness['native_limit'], 192)
            self.assertEqual(witness['funding']['retained_profile_calls'], 12)
            self.assertEqual(runtime.excluded_turns(self.root, run, plan), token['source_identity']['upstream_turns'])
        self.assertEqual(sorted(p.name for p in run.iterdir()), ['b', 'capability-coordinator.lock', 'run.json'])

    def test_legacy_retrofit_and_repeat_prepare_reject_before_publication(self):
        token, plan = self.source()
        for old in ('c4', 'm4'):
            with patch.object(runtime, 'capture_source', side_effect=AssertionError('legacy must reject before qualification')):
                with self.assertRaisesRegex(core.SegmentedBlocked, 'fresh_declared_run_only'):
                    runtime.prepare_run(self.root, run_id=old, planner='mvg', plan=plan, planning_contract='docs/contract.json')
        _, _, result, run = self.prepare()
        before = (run / 'run.json').read_bytes()
        with self.assertRaisesRegex(core.SegmentedBlocked, 'namespace_already_exists'):
            runtime.prepare_run(self.root, run_id='new', planner='mvg', plan=plan, planning_contract='docs/contract.json')
        self.assertEqual((run / 'run.json').read_bytes(), before)

    def test_partial_birth_keeps_claim_journal_and_refuses_second_prepare(self):
        original = journal._original_writer
        def fail_after_claim(root, target, payload):
            if Path(target).name == 'run.json':
                raise OSError('synthetic-host-loss-after-permanent-birth-claim')
            return original(root, target, payload)
        token, plan = self.source()
        with patch.object(runtime, 'capture_source', return_value=token), patch.object(journal, '_original_writer', side_effect=fail_after_claim):
            with self.assertRaisesRegex(OSError, 'synthetic-host-loss'):
                runtime.prepare_run(self.root, run_id='new', planner='mvg', plan=plan, planning_contract='docs/contract.json')
        run = runtime._homes(self.root, 'mvg', 'new')
        before_claim = (run / 'b/claim.json').read_bytes()
        self.assertFalse((run / 'run.json').exists())
        entries = list((self.root / 'logs/ci/mvg-recovery/activity/segmented-journals').iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual(codec.strict_json_loads(entries[0].read_bytes())['status'], 'pending')
        with self.assertRaisesRegex(core.SegmentedBlocked, 'namespace_already_exists'):
            runtime.prepare_run(self.root, run_id='new', planner='mvg', plan=plan, planning_contract='docs/contract.json')
        self.assertEqual((run / 'b/claim.json').read_bytes(), before_claim)

    def test_original_source_capture_is_opaque_and_current_raw_absence_are_closed(self):
        token, _ = self.source()
        runtime.verify_candidate_context(self.root, token)
        same_fields_but_unissued = runtime._SourceCapture(runtime._SEAL)
        self.assertIsNot(token, same_fields_but_unissued)
        self.assertNotEqual(token, same_fields_but_unissued)
        self.assertNotIn(same_fields_but_unissued, runtime._SOURCES)
        self.assertEqual(runtime._SOURCES[token]['root'], self.root)
        with self.assertRaisesRegex(core.SegmentedBlocked, 'not_issued_by_actual_owner'):
            runtime.verify_candidate_context(self.root, same_fields_but_unissued)
        with self.assertRaisesRegex(core.SegmentedBlocked, 'original_source_capture_required'):
            runtime.verify_candidate_context(self.root, dict(token))
        copy = token['frozen']
        copy['input_identity'] = 'forged'
        self.assertNotEqual(token['frozen']['input_identity'], 'forged')
        (self.root / 'docs/absent.txt').write_bytes(b'new')
        with self.assertRaisesRegex(core.SegmentedBlocked, 'raw_or_absence_changed'):
            runtime.verify_candidate_context(self.root, token)

    def test_real_capture_factory_derives_original_ledger_not_model_reported_denominator(self):
        original = self.root / 'docs/original.txt'
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(b'Q before R; preserve shared state and non-Flow audit.\n')
        contract = {'scope': {'scope_id': 'synthetic-qualified-scope'}, 'constraints': [], 'contexts': [], 'audit_ref': 'audit/proof.json'}
        self.write('docs/contract.json', contract)
        inputs = {'contract': deepcopy(contract), 'constraints': [], 'evidence': [
            {'path': 'docs/original.txt', 'sha256': codec.raw_digest(original.read_bytes())}],
            'source_inventory': [], 'dependencies': {'rules': {'synthetic_rules': 1}},
            'global_proof': {'identity': {'expected_reasoning_effort': 'high'},
                'ledger': {'blocks': [{'block_id': 'b1', 'source_path': 'docs/original.txt'}]},
                'proposals': [{'original': 'full synthetic upstream semantic object'}]}}
        def read_contract(obs, name):
            return codec.strict_json_loads(obs.read(name))
        def assemble(obs, name):
            obs.read('docs/original.txt')
            obs.read('docs/contract.json')
            obs.read('docs/absent.txt', optional=True)
            return deepcopy(inputs)
        with patch.object(runtime, '_preserved_owner', return_value=None), \
             patch.object(runtime.planning, 'read_contract', side_effect=read_contract), \
             patch.object(runtime.planning, 'assemble', side_effect=assemble), \
             patch('_b_route_source_audit.verify_current_proof', return_value=None), \
             patch.object(runtime, '_turns', return_value=[{'thread_id': 'synthetic-audit', 'turn_id': 'synthetic-turn'}]):
            token = runtime.capture_source(self.root, run_id='genuine-factory', planner='mvg', planning_contract='docs/contract.json')
        domain = token['domain']
        self.assertIn('original-b1', {row['obligation_id'] for row in domain['obligations']})
        self.assertEqual(domain['original_semantic_objects'], inputs['global_proof']['proposals'])
        self.assertEqual(domain['partition_mode'], 'whole-qualified-semantic-domain')
        self.assertEqual(domain['dependency_edges'], sorted(domain['dependency_edges']))
        self.assertEqual(len(domain['manifest']['candidates']), 3)
        self.assertTrue(all(row['material_ids'] == [] for row in domain['manifest']['candidates']))
        runtime.verify_candidate_context(self.root, token)
        original.write_bytes(b'changed original')
        with self.assertRaisesRegex(core.SegmentedBlocked, 'raw_or_absence_changed'):
            runtime.verify_candidate_context(self.root, token)

    def test_born_controls_and_fake_native_selected_cannot_follow_legitimate_ledger(self):
        _, plan, result, run = self.prepare()
        state = self.read(result['run_ref'])
        for field, item in [('formal_adoption', True), ('b_route_campaign_funding', {})]:
            changed = deepcopy(state)
            changed[field] = item
            with self.assertRaisesRegex(core.SegmentedBlocked, 'immutable_born_controls_changed'):
                runtime._birth(self.root, run, changed, plan, sources.Observations(self.root))
        changed = deepcopy(state)
        changed['capability_selection']['selected'] = [{'fake': 'selected'}]
        with self.assertRaisesRegex(core.SegmentedBlocked, 'does_not_grant_native_selected'):
            runtime._birth(self.root, run, changed, plan, sources.Observations(self.root))
        changed = deepcopy(state)
        changed['capability_selection']['calls'] = [{'synthetic-unverified-progress': 1}]
        changed['capability_selection']['total_invocations'] = 1
        changed['active_elapsed_seconds'] = 1
        # _birth deliberately permits the mutable projection, but it alone
        # grants nothing: the independent original journal history rejects it.
        runtime._birth(self.root, run, changed, plan, sources.Observations(self.root))
        self.write(result['run_ref'], changed)
        with self.assertRaisesRegex(ValueError, 'unclaimed_native_row'):
            journal.inspect_native_history(self.root, run, changed)

    def test_clear_archives_cost_index_and_old_run_cannot_reopen_current_epoch(self):
        _, plan, result, run = self.prepare()
        before = runtime.recovery.registry(self.root)
        runtime.recovery.clear(self.root)
        current, entries = runtime._registry_entries(self.root)
        self.assertEqual(current['epoch'], 1)
        self.assertEqual(entries[result['run_ref']], before['segmented_runs']['runs'][0])
        self.assertEqual(self.read('logs/ci/mvg-recovery/clears/epoch-0.json'), before)
        state = self.read(result['run_ref'])
        with self.assertRaisesRegex(ValueError, 'epoch_invalidated'):
            runtime.recovery.assert_epoch(self.root, state, value=current)
        self.assertEqual(state['b_route_campaign_funding']['paid_or_unknown_before_run'], 78)

    def test_sensitive_role_rejected_with_zero_file_reads(self):
        for name in ('docs/auth.json', 'docs/.env.local', 'archived_sessions/a.json', 'docs/.SSH/id_ed25519'):
            with self.subTest(name=name), patch.object(Path, 'read_bytes', side_effect=AssertionError('role must precede IO')):
                with self.assertRaisesRegex(core.SegmentedBlocked, 'sensitive_role_before_io'):
                    runtime.raw(self.root, name)

    def test_source_only_transport_records_actual_argv_and_restores_process_boundary(self):
        source, _ = self.source()
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        runner = Path(self.policy['source_root']) / 'scripts/python/codex_isolated_model_runner.py'
        logical = [sys.executable, '-B', str(runner), '--describe']
        forwarded = []
        stdin = object()
        def synthetic_os(command, *args, **kwargs):
            forwarded.append((list(command), kwargs))
            return SimpleNamespace(pid=1729)
        with patch.object(runtime.subprocess, 'Popen', side_effect=synthetic_os) as original:
            with runtime._source_runner_scope(self.root, runner, source) as issued:
                runtime.subprocess.Popen(logical, stdin=stdin)
            self.assertIs(runtime.subprocess.Popen, original)
            provenance = runtime.verify_runner_transport(self.root, issued, logical_command=logical)
        self.assertEqual(len(forwarded), 1)
        self.assertIs(forwarded[0][1]['stdin'], stdin)
        self.assertEqual(provenance['logical_argv'], logical)
        self.assertEqual(provenance['transport_argv'], forwarded[0][0])
        self.assertEqual(forwarded[0][0][:5], [sys.executable, '-I', '-S', '-B', '-c'])
        self.assertNotEqual(provenance['logical_argv'], provenance['transport_argv'])
        self.assertEqual(provenance['bootstrap_raw_digest'], codec.raw_digest(forwarded[0][0][5].encode('utf-8')))
        self.assertEqual(provenance['child_pid'], 1729)
        unissued = runtime._RunnerTransport(runtime._SEAL)
        self.assertNotEqual(issued, unissued)
        self.assertNotIn(unissued, runtime._TRANSPORTS)
        with self.assertRaisesRegex(core.SegmentedBlocked, 'original_closed_runner_transport_token'):
            runtime.verify_runner_transport(self.root, unissued, logical_command=logical)
        with self.assertRaisesRegex(core.SegmentedBlocked, 'original_closed_runner_transport_token'):
            runtime.verify_runner_transport(self.root, dict(provenance), logical_command=logical)
        self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)

    def test_original_unknown_time_is_charged_not_refunded(self):
        self.assertEqual(runtime._activity({'request_identity': {'timeout_sec': 1800}}), 1800)
        self.assertEqual(runtime._activity({'outcome': {'status': 'unknown'}, 'request_identity': {'timeout_sec': 2700}}), 2700)
        self.assertEqual(runtime._activity({'outcome': {'active_elapsed_seconds': 47}, 'request_identity': {'timeout_sec': 1800}}), 47)
        for bad in (True, float('nan'), -1, None):
            with self.subTest(bad=bad), self.assertRaisesRegex(core.SegmentedBlocked, 'original_requested_timeout'):
                runtime._activity({'request_identity': {'timeout_sec': bad}})

    def test_timeout_preserves_original_capability_pools_and_blocks_old_unknown_exhaustion(self):
        source, plan, result, run = self.prepare('capability')
        state = self.read(result['run_ref'])
        with patch.object(runtime, 'capture_source', return_value=source), runtime.verified_run(self.root, run, plan):
            witness = runtime.segmented_run_contract(self.root, state, run, plan_digest=plan['plan_digest'], protocol=core.PROTOCOL)
            self.assertEqual(witness['native_limit'], 96)
            self.assertEqual(witness['funding']['retained_profile_calls'], 11)
            self.assertEqual(runtime.request_timeout(self.root, run, state, plan, plan['nodes'][0], witness), 2700)
            synthesis = next(node for node in plan['nodes'] if node['phase'] == 'synthesis')
            self.assertEqual(runtime.request_timeout(self.root, run, state, plan, synthesis, witness), 1200)
        historical = self.campaign(self.root)
        exhausted = [deepcopy(row) for row in historical.cap_rows]
        exhausted[0] = {'candidate': 'candidate-1', 'outcome': {'status': 'unknown'},
                        'request_identity': {'timeout_sec': 3900}}
        campaign = runtime._CampaignCapture(self.root, historical.obs, tuple(exhausted), historical.mvg_rows,
            None, {}, {}, (), 66, runtime._SEAL)
        with patch.object(runtime, 'capture_source', return_value=source), patch.object(runtime, '_capture_campaign', return_value=campaign):
            with runtime.verified_run(self.root, run, plan):
                witness = runtime.segmented_run_contract(self.root, state, run, plan_digest=plan['plan_digest'], protocol=core.PROTOCOL)
                with self.assertRaisesRegex(core.SegmentedBlocked, 'active_time_pool_exhausted'):
                    runtime.request_timeout(self.root, run, state, plan, plan['nodes'][0], witness)
        self.assertEqual(self.read(result['run_ref'])['capability_selection']['calls'], [])

    def test_registry_head_update_is_pure_preserves_old_fields_and_rejects_cross_run_claim(self):
        _, plan, result, run = self.prepare()
        registry = runtime.recovery.registry(self.root)
        before = deepcopy(registry)
        witness = {'run_path': result['run_ref'], 'plan_digest': plan['plan_digest'], 'registry_epoch': 0,
                   'born_ref': result['born_ref']}
        next_registry = runtime.with_ledger_head(self.root, registry, run, plan, witness,
            journal_ref='logs/ci/mvg-recovery/activity/segmented-journals/' + 'a' * 24 + '-001-reserve.json',
            claim_ref=run.relative_to(self.root).as_posix() + '/q/n0/claim.json',
            claim_raw_digest='sha256:' + '1' * 64, run_after_digest='sha256:' + '2' * 64)
        self.assertEqual(registry, before)
        self.assertEqual(next_registry['entries'], registry['entries'])
        self.assertEqual(next_registry['revoked'], registry['revoked'])
        self.assertEqual(next_registry['epoch'], registry['epoch'])
        with self.assertRaisesRegex(core.SegmentedBlocked, 'claim_in_original_run'):
            runtime.with_ledger_head(self.root, registry, run, plan, witness,
                journal_ref='logs/ci/mvg-recovery/activity/segmented-journals/' + 'a' * 24 + '-001-reserve.json',
                claim_ref='logs/ci/mvg-planning/foreign/claim.json', claim_raw_digest='sha256:' + '1' * 64,
                run_after_digest='sha256:' + '2' * 64)

    def test_preplan_factory_needs_no_future_plan_and_reports_real_79_not_static_lower_bound(self):
        self.mvg_count = 13
        source, unused_plan = self.source()
        with patch.object(runtime, 'capture_source', return_value=source), \
             patch.object(core, 'build_plan', side_effect=AssertionError('pre-plan authority must not need a plan')):
            authority = runtime.capture_plan_authority(self.root, run_id='new', planner='mvg', planning_contract='docs/contract.json')
            facts = runtime.verify_plan_authority(self.root, authority)
        self.assertEqual(set(facts), {'schema_version', 'run_id', 'planner', 'source_input_identity', 'domain',
            'funding', 'retained_time', 'registry_epoch', 'source_policy', 'authority_digest'})
        self.assertEqual(facts['funding']['paid_or_unknown_before_run'], 79)
        self.assertEqual(facts['funding']['retained_profile_calls'], 13)
        self.assertEqual(facts['retained_time']['total_active_seconds'], 13)
        self.assertEqual(facts['retained_time']['lineage_active_seconds'], {'candidate-1': 13})
        self.assertEqual(facts['source_input_identity'], source['frozen']['input_identity'])
        self.assertEqual(facts['domain'], source['domain'])
        self.assertEqual(set(unused_plan['budget']), {'native_limit', 'campaign_limit', 'released', 'worst_case_calls'})
        self.assertEqual(facts['authority_digest'], codec.canonical_digest({k: v for k, v in facts.items() if k != 'authority_digest'}))
        self.assertFalse((self.root / 'logs').exists())
        with self.assertRaisesRegex(core.SegmentedBlocked, 'genuine_preplan_authority_required'):
            runtime.verify_plan_authority(self.root, dict(authority))
        unissued = runtime._PlanAuthority(runtime._SEAL)
        self.assertNotEqual(unissued, authority)
        with self.assertRaisesRegex(core.SegmentedBlocked, 'genuine_preplan_authority_required'):
            runtime.verify_plan_authority(self.root, unissued)
        facts['funding']['paid_or_unknown_before_run'] = 0
        self.assertEqual(runtime.verify_plan_authority(self.root, authority)['funding']['paid_or_unknown_before_run'], 79)

    def test_preplan_original_registry_or_retained_time_drift_rejects_without_namespace(self):
        source, _ = self.source()
        with patch.object(runtime, 'capture_source', return_value=source):
            authority = runtime.capture_plan_authority(self.root, run_id='new', planner='mvg', planning_contract='docs/contract.json')
        # The explicit synthetic historical authority changes its observed time;
        # fresh arithmetic must reject this rather than trust public self-hash.
        historical = runtime._PLAN_AUTHORITIES[authority]['campaign']
        historical.mvg_rows[0]['outcome']['active_elapsed_seconds'] = 2
        with self.assertRaisesRegex(core.SegmentedBlocked, 'funding_time_or_epoch_changed'):
            runtime.verify_plan_authority(self.root, authority)
        self.assertFalse(runtime._homes(self.root, 'mvg', 'new').exists())
        with patch.object(runtime, 'capture_source', return_value=source):
            authority = runtime.capture_plan_authority(self.root, run_id='new', planner='mvg', planning_contract='docs/contract.json')
        self.write('logs/ci/mvg-recovery/registry.json', {'schema_version': runtime.recovery.SCHEMA,
            'epoch': 0, 'entries': [], 'revoked': []})
        with self.assertRaises(codec.CodecError):
            runtime.verify_plan_authority(self.root, authority)
        self.assertFalse(runtime._homes(self.root, 'mvg', 'new').exists())

    def test_prepare_recaptures_source_and_budget_cas_before_creating_born_namespace(self):
        self.mvg_count = 13
        source, plan = self.source()
        def change_original(*args):
            (self.root / 'docs/original.txt').write_bytes(b'changed during preflight')
            return {'supports_synthesis_budget': True}
        with patch.object(runtime, 'capture_source', return_value=source), patch.object(runtime, '_describe', side_effect=change_original):
            with self.assertRaisesRegex(core.SegmentedBlocked, 'raw_or_absence_changed'):
                runtime.prepare_run(self.root, run_id='new', planner='mvg', plan=plan, planning_contract='docs/contract.json')
        run = runtime._homes(self.root, 'mvg', 'new')
        self.assertFalse(run.exists())
        self.assertFalse((self.root / 'logs/ci/mvg-recovery/registry.json').exists())

    def test_paid_gate_rejects_caller_only_reservation_without_real_native_charge(self):
        source, plan, result, run = self.prepare()
        node = plan['nodes'][0]
        caller_only = {'reservation_id': plan['run_id'] + ':dispatch:1', 'number': 1, 'phase': node['phase'],
                       'run_id': plan['run_id'], 'request_identity': {'node_id': node['node_id']}}
        with self.assertRaisesRegex(core.SegmentedBlocked, 'genuine_action_context'):
            runtime.assert_paid_reservation(self.root, plan, node, caller_only)
        with patch.object(runtime, 'capture_source', return_value=source), runtime.verified_run(self.root, run, plan):
            with self.assertRaisesRegex(core.SegmentedBlocked, 'paid_original_row_missing_or_caller_changed'):
                runtime.assert_paid_reservation(self.root, plan, node, caller_only)
        self.assertEqual(self.read(result['run_ref'])['capability_selection']['calls'], [])
        self.assertFalse((run / 'q').exists())

    def test_real_paid_single_node_protocol_roundtrip_complete_and_cold_replay(self):
        """Real new owners/paid gate; only upstream facts and OS are synthetic."""
        import _b_route_segmented_requests as requests
        import _b_route_planning_runtime as native
        import _planning_skill_common as common
        import codex_isolated_model_runner as official
        from _planning_execution_binding import receipt_from
        from test_b_route_segmented_workflow import SegmentedWorkflowTests as ProtocolFixture
        actual_source = Path(runtime.__file__).absolute().parents[2]
        self.active_plan = None
        self.dispatched = []
        def response(plan, node, _envelope):
            segment = plan['manifest']['segments'][0]
            cite = {key: segment[key] for key in ('segment_id', 'start', 'end', 'raw_digest')}
            oid = plan['obligations'][0]['obligation_id']
            return {'schema_version': core.RESPONSE, 'protocol': core.PROTOCOL, 'run_id': plan['run_id'],
                'plan_digest': plan['plan_digest'], 'node_id': node['node_id'], 'phase': node['phase'],
                'coverage': [{'obligation_id': oid, 'citations': [cite]}],
                'decisions': [{'decision_id': 'preserve-original', 'obligation_ids': [oid], 'depends_on': [],
                    'citations': [cite], 'statement': 'Preserve Q before R, shared state and non-Flow audit.'}],
                'dependency_edges': [], 'unresolved': [], 'findings': [], 'checks': [], 'comparisons': [],
                'candidate_pieces': [], 'product_checks': [], 'joint_checks': [], 'selected_label': None, 'rationale': '',
                'derived_not_lossless': True}
        self.response_factory = response
        with patch.dict(os.environ, {'NEWROGUE_CODEX_REASONING_EFFORT': 'high'}), \
             patch.object(runtime, 'policy_identity', side_effect=self.policy_owner):
            self.policy = self.policy_owner()
            info = official.description()
            with patch.object(runtime, '_describe', return_value=info):
                source, plan, result, run = self.prepare()
            self.active_plan = plan
            node = plan['nodes'][0]
            runner = actual_source / 'scripts/python/codex_isolated_model_runner.py'
            # This dummy is the declared original OS boundary. No child process
            # or model starts. The actual new source transport still records
            # its exact logical/physical argv and issued token unchanged.
            launches = []
            def synthetic_os(command, *args, **kwargs):
                launches.append(list(command))
                return SimpleNamespace(pid=42000 + len(launches))
            with patch.object(runtime, 'capture_source', return_value=source), \
                 patch.object(runtime.subprocess, 'Popen', side_effect=synthetic_os), \
                 runtime.verified_run(self.root, run, plan):
                with journal.open_workflow(self.root, run_dir=run, plan=plan) as session:
                    self.assertEqual(session.snapshot()['completed'], [])
                    with runtime.source_only_runner(self.root, runner) as describe_token:
                        common.subprocess.Popen([*common._runner_prefix(runner, suppress_bytecode=True), '--describe'])
                    description = runtime.verify_runner_transport(self.root, describe_token,
                        logical_command=[*common._runner_prefix(runner, suppress_bytecode=True), '--describe'])
                    dispatch_policy = core.policy_identity(self.root)
                    envelope = core._envelope(self.root, plan, node, {}, run_dir=run)
                    request = requests.render_request(self.root, envelope=envelope, schema=core.output_schema(envelope),
                        instruction=core.phase_instruction(node['phase'], False), workspace=session.workspace(node),
                        output_reserve=node['output_reserve'])
                    decoded = requests.read_input_envelope(self.root, Path(request['workspace']))
                    self.assertEqual(codec.canonical_digest(decoded), codec.canonical_digest(envelope))
                    archive = requests.archive_request_inputs(self.root, request)
                    timeout = session.timeout(node)
                    identity = {'protocol': core.PROTOCOL, 'plan_digest': plan['plan_digest'], 'node_id': node['node_id'],
                        'phase': node['phase'], 'request_sha256': request['request_sha256'],
                        'input_measurement': request['measurement'], 'output_reserve': node['output_reserve'],
                        'source_hashes': deepcopy(dispatch_policy), 'schema_digest': request['schema_digest'],
                        'request_ref': runtime.ref_for(Path(request['prompt_path']).relative_to(self.root).as_posix(),
                            'newrouge.b-route-segmented-prompt.v1', Path(request['prompt_path']).read_bytes()),
                        'schema_ref': runtime.ref_for(Path(request['schema_path']).relative_to(self.root).as_posix(),
                            'newrouge.b-route-segmented-output-schema.v1', Path(request['schema_path']).read_bytes()),
                        'input_archive_ref': archive, 'timeout_sec': timeout}
                    reservation = session.reserve(node, identity, rendered_request=request,
                        completed_prefix=core._capture_prefix(self.root, plan, {}))
                    fixed_workspace = runtime.path(self.root,
                        (run / 'q' / ('n' + str(node['ordinal'])) / 'm').relative_to(self.root).as_posix())
                    self.assertEqual(reservation['workspace'], str(fixed_workspace.resolve()))
                    paid = runtime.assert_paid_reservation(self.root, plan, node, reservation)
                    self.assertEqual(paid['publication'], 'encumbered')
                    self.assertEqual(paid['released'], 0)
                    claim_path = self.root / paid['claim_ref']['path']
                    permanent_claim = claim_path.read_bytes()
                    workspace = Path(request['workspace'])
                    host_path = workspace.parent / (workspace.name + '-execution.json')
                    with runtime.source_only_runner(self.root, runner) as model_token:
                        host = ProtocolFixture.fake_os_turn(self, runner, workspace=workspace,
                            prompt_path=Path(request['prompt_path']), output_path=Path(request['output_path']),
                            output_schema=Path(request['schema_path']), timeout_sec=timeout,
                            wall_timeout_sec=timeout + 30, model_request_budget=1, execution_log=host_path,
                            suppress_bytecode=True)
                        common.subprocess.Popen(host['command'])
                    host['source_transport'] = runtime.verify_runner_transport(self.root, model_token, logical_command=host['command'])
                    host['command_scope'] = 'original-logical-runner-argv'
                    common.atomic_json(host_path, host)
                    binding = native.capture_binding(workspace, Path(request['prompt_path']), Path(request['schema_path']),
                        Path(request['output_path']), request['model_prompt'], request['measurement'], host_path, info, receipt_from(host))
                    close = core._capture_execution_close(self.root, request, binding)
                    core._fresh_turn(self.root, run, plan, {}, binding)
                    requests.verify_rendered_request(self.root, request, execution_close=close)
                    output_raw = Path(request['output_path']).read_bytes()
                    from _capability_input_integrity import measure_request
                    measure_request(output_raw.decode('utf-8', errors='strict'), max_bytes=1024 * 1024,
                        max_input_tokens=node['output_reserve'], reserved_tokens=0)
                    answer = core.verify_response(plan, node, core.decode_response_wire(codec.strict_json_loads(output_raw), envelope),
                        candidate_products=envelope['candidate_products'], candidate_contract=envelope['candidate_contract'])
                    core.verify_manifest(self.root, plan['manifest'])
                    self.assertEqual(core.policy_identity(self.root), dispatch_policy)
                    expected_names = {'prompt.txt', 'input.json', 'output-schema.json'} | set(close['files'])
                    self.assertEqual({p.name for p in workspace.iterdir()}, expected_names)
                    record_root = self.root.resolve()
                    files = {(workspace / name).relative_to(record_root).as_posix(): codec.raw_digest(core._read(workspace, name))
                             for name in expected_names}
                    files[host_path.relative_to(record_root).as_posix()] = codec.raw_digest(host_path.read_bytes())
                    recorded = {'schema_version': core.RESULT, 'protocol': core.PROTOCOL, 'root': record_root.as_posix(),
                        'plan_digest': plan['plan_digest'], 'node_id': node['node_id'], 'reservation': deepcopy(reservation),
                        'request_sha256': request['request_sha256'], 'response': answer,
                        'candidate_products': deepcopy(envelope['candidate_products']), 'runner_description_transport': description,
                        'workspace_files': sorted(expected_names),
                        'binding': binding, 'files': files, 'policy_identity': deepcopy(dispatch_policy)}
                    recorded['result_digest'] = core._digest(recorded, 'result_digest')
                    verified = core.VerifiedResult(recorded, core._SEAL)
                    core.validate_verified_result(plan, node, reservation, verified)
                    session.complete(reservation, verified)
                    core.validate_verified_result(plan, node, reservation, verified)
                    self.assertEqual(claim_path.read_bytes(), permanent_claim)
                    forged = deepcopy(reservation)
                    forged['request_identity']['request_sha256'] = 'sha256:' + '0' * 64
                    with self.assertRaisesRegex(core.SegmentedBlocked, 'paid_original_row_missing_or_caller_changed'):
                        runtime.assert_paid_reservation(self.root, plan, node, forged)
                    changed_spelling = deepcopy(reservation)
                    changed_spelling['workspace'] = reservation['workspace'].swapcase()
                    with self.assertRaisesRegex(core.SegmentedBlocked, 'paid_original_row_missing_or_caller_changed'):
                        runtime.assert_paid_reservation(self.root, plan, node, changed_spelling)
            self.assertEqual(len(self.dispatched), 1)
            self.assertEqual(len(launches), 2)
            # Fresh action and read-only session reconstruct the stored result
            # through original high protocol replay and the actual paid gate.
            with patch.object(runtime, 'capture_source', return_value=source), runtime.verified_run(self.root, run, plan):
                with journal.open_workflow(self.root, run_dir=run, plan=plan, read_only=True) as session:
                    snapshot = session.snapshot()
                    self.assertEqual(len(snapshot['completed']), 1)
                    self.assertEqual(snapshot['completed'][0]['node_id'], node['node_id'])
                    self.assertEqual(snapshot['completed'][0]['result']['result_digest'], recorded['result_digest'])
        state = self.read(result['run_ref'])
        self.assertEqual(state['capability_selection']['total_invocations'], 1)
        self.assertEqual(state['capability_selection']['calls'][0]['outcome']['status'], 'completed')
        self.assertFalse(state['formal_adoption'])
        self.assertEqual(state['capability_selection']['selected'], [])
        self.assertFalse((run / 'q/n1/claim.json').exists())


if __name__ == '__main__':
    unittest.main()
