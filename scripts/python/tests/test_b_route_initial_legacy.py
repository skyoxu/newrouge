"""Real owned Git/filesystem collector/archive tests; no native/model seam."""
from __future__ import annotations

import copy
import importlib
import io
import json
from pathlib import Path
import shutil
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import _b_route_inventory as inventory
import _b_route_initial_legacy as initial
import _b_route_protection as protection
import capture_b_route_protection as cli


class InitialLegacyProtectionTests(unittest.TestCase):
    def fixture(self, *, empty=True):
        fixtures = importlib.import_module('test_b_route_inventory')
        fx = fixtures.InventoryTests(methodName='runTest')
        def initialize(*args):
            if args == ('init', '-q') and empty:
                # Change only this new fixture before its first Git object.
                for key, value in {'master': {'master': {'tasks': []}}, 'back': [], 'gameplay': []}.items():
                    fx.dump(inventory.TRIPLET[key], value)
                (fx.root/'docs/testing/mvg/fixture.json').unlink()
            actual = (*args, '--template=') if args == ('init', '-q') else args
            return inventory.git(fx.root, *actual).decode('utf-8')
        fx.run_git = initialize
        fx.setUp()
        self.addCleanup(fx.tearDown)
        return fx

    def capture(self, fx):
        return protection.collect_protection(fx.root, fx.epics)

    def archive(self, fx, capture, name='capture'):
        output = protection.create_run_directory(fx.root, name)
        protection.write_capture(output, capture)
        return output.relative_to(fx.root).as_posix()+'/snapshot.json'

    def stage_then_restore(self, fx, path, raw):
        target = fx.root/path
        original = target.read_bytes() if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        fx.run_git('add', path)
        if original is None:
            target.unlink()
        else:
            target.write_bytes(original)

    def test_actual_new_root_empty_collector_archive_and_live_verifier(self):
        fx = self.fixture()
        capture = self.capture(fx)
        self.assertTrue(capture.snapshot['capture_complete'], capture.snapshot['diagnostics'])
        requirement = capture.inventory['legacy_manifest_requirement']
        self.assertEqual(requirement['state'], 'initially_absent')
        self.assertEqual(capture.inventory['manifests'], [])
        self.assertEqual(capture.snapshot['cumulative'], [])
        self.assertEqual(capture.snapshot['frozen_a']['candidate_count'], 0)
        self.assertTrue(requirement['proof']['objects'])
        self.assertEqual(requirement['proof']['anchors'], [fx.head, fx.head])
        for value in capture.snapshot['authorization'].values():
            self.assertIs(value, False)
        path = self.archive(fx, capture)
        self.assertTrue(protection.verify_protection(fx.root, path)['ok'])
        # A prior real v3 empty capture is history, not a permanent retry gate.
        successor = self.capture(fx)
        self.assertTrue(successor.snapshot['capture_complete'], successor.snapshot['diagnostics'])
        self.assertTrue(protection.verify_protection(fx.root, self.archive(fx, successor, 'successor'))['ok'])

    def test_public_protection_cli_uses_real_empty_path_and_grants_nothing(self):
        fx = self.fixture()
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(['capture','--root',str(fx.root),'--epics',fx.epics,'--run-id','public-empty'])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0, result)
        self.assertTrue(result['capture_complete'])
        self.assertTrue(all(value is False for value in result['authorization'].values()))
        with redirect_stdout(io.StringIO()):
            code = cli.main(['verify','--root',str(fx.root),'--snapshot',result['output']+'/snapshot.json',
                             '--run-id','public-verify'])
        self.assertEqual(code, 0)

    def test_mature_tasks_and_manifest_keep_original_validator_without_extra_history(self):
        fx = self.fixture(empty=False)
        with patch.object(initial, '_query', side_effect=AssertionError('No initial-history cost for mature inputs')):
            capture = self.capture(fx)
        self.assertTrue(capture.snapshot['capture_complete'], capture.snapshot['diagnostics'])
        self.assertEqual(capture.inventory['legacy_manifest_requirement']['state'], 'required')
        self.assertEqual(len(capture.snapshot['cumulative']), 1)

    def test_present_invalid_manifest_and_nonempty_or_partial_triplet_never_waive(self):
        for case in ('invalid-manifest','orphan-view','missing-view','malformed-master'):
            with self.subTest(case=case):
                fx = self.fixture()
                if case == 'invalid-manifest':
                    fx.dump('docs/testing/mvg/invalid.json', fx.manifest)
                elif case == 'orphan-view':
                    fx.dump(inventory.TRIPLET['back'], [{'id':'B','taskmaster_id':1,'status':'pending'}])
                elif case == 'missing-view':
                    (fx.root/inventory.TRIPLET['gameplay']).unlink()
                else:
                    fx.dump(inventory.TRIPLET['master'], {'master': {'tasks': False}})
                report = inventory.collect_inventory(fx.root, fx.epics)
                self.assertFalse(report['adoptable'])
                self.assertNotEqual(report['legacy_manifest_requirement']['state'], 'initially_absent')

    def test_deleted_old_manifest_and_nonempty_task_history_remain_required(self):
        fx = self.fixture(empty=False)
        for key, value in {'master':{'master':{'tasks':[]}},'back':[],'gameplay':[]}.items():
            fx.dump(inventory.TRIPLET[key], value)
        (fx.root/'docs/testing/mvg/fixture.json').unlink()
        fx.run_git('add','.')
        fx.run_git('commit','-qm','Retain the actual old history')
        report = inventory.collect_inventory(fx.root, fx.epics)
        self.assertFalse(report['adoptable'])
        self.assertEqual(report['legacy_manifest_requirement']['state'], 'required')
        self.assertTrue(any(d['code']=='missing-manifests' for d in report['diagnostics']))

    def test_indexed_missing_and_prior_owner_captured_untracked_manifest_block(self):
        for route in ('index','owner','explicit-history','nested-history'):
            with self.subTest(route=route):
                fx = self.fixture()
                path = ('docs/testing/mvg/nested/old.json' if route == 'nested-history'
                        else 'docs/testing/mvg/untracked.json')
                fx.dump(path, fx.manifest)
                historical = None
                if route in ('index', 'nested-history'):
                    fx.run_git('add',path)
                    if route == 'nested-history':
                        fx.run_git('commit','-qm','Original nested manifest')
                else:
                    original = inventory.collect_inventory(fx.root, fx.epics)
                    self.assertTrue(original['manifests'])
                    historical = ('logs/ci/history/prior-inventory.json' if route == 'explicit-history' else
                                  'logs/ci/2026-11-08/b-route-baseline-inventory/prior/inventory.json')
                    fx.dump(historical, original)
                (fx.root/path).unlink()
                if route == 'nested-history':
                    fx.run_git('add','.')
                    fx.run_git('commit','-qm','Retain deleted nested manifest history')
                report = inventory.collect_inventory(fx.root, fx.epics,
                    **({'historical_inventory':historical} if route == 'explicit-history' else {}))
                self.assertFalse(report['adoptable'])
                self.assertEqual(report['legacy_manifest_requirement']['state'], 'required')

    def test_old_source_declaration_and_partial_known_owner_are_not_absence(self):
        for case in ('declared-history','partial-owner','malformed-owner','namespace-file'):
            with self.subTest(case=case):
                fx = self.fixture()
                if case == 'declared-history':
                    original = json.loads((fx.root/inventory.SOURCE_SET).read_text(encoding='utf-8'))
                    changed = copy.deepcopy(original)
                    changed['retirements'] = [{'path':'docs/testing/mvg/retired.json'}]
                    fx.dump(inventory.SOURCE_SET, changed)
                    fx.run_git('add',inventory.SOURCE_SET)
                    fx.run_git('commit','-qm','Original governed declaration')
                    fx.dump(inventory.SOURCE_SET, original)
                    fx.run_git('add',inventory.SOURCE_SET)
                    fx.run_git('commit','-qm','Retain the declaration in history')
                elif case == 'partial-owner':
                    fx.write('logs/ci/2026-11-08/b-route-protection/partial/raw/orphan.bin','Original partial capture')
                elif case == 'malformed-owner':
                    fx.dump('logs/ci/2026-11-08/b-route-protection/malformed/snapshot.json',
                            {'schema_version':'newrouge.b-route-protection-snapshot.v3','raw_files':False,'frozen_a':False})
                else:
                    fx.write('logs/ci/2026-11-08','Not a directory')
                report = inventory.collect_inventory(fx.root, fx.epics)
                self.assertFalse(report['adoptable'])
                self.assertNotEqual(report['legacy_manifest_requirement']['state'], 'initially_absent')

    def test_shallow_graft_replaced_or_bounded_unknown_never_qualifies(self):
        for case in ('shallow','graft','replace','bound'):
            with self.subTest(case=case):
                fx = self.fixture()
                if case == 'shallow':
                    fx.write('.git/shallow',fx.head+'\n')
                    report = inventory.collect_inventory(fx.root, fx.epics)
                elif case == 'graft':
                    fx.write('.git/info/grafts',fx.head+'\n')
                    report = inventory.collect_inventory(fx.root, fx.epics)
                elif case == 'replace':
                    # Real repository ref observation; no replacement is used
                    # by the observer's no-replace Git calls.
                    fx.run_git('update-ref','refs/replace/'+fx.head,fx.head)
                    report = inventory.collect_inventory(fx.root, fx.epics)
                else:
                    with patch.object(initial,'MAX_COMMITS',1):
                        report = inventory.collect_inventory(fx.root, fx.epics)
                self.assertFalse(report['adoptable'])
                self.assertEqual(report['legacy_manifest_requirement']['state'], 'unknown')

    def test_live_creation_source_history_drift_and_root_switch_reject(self):
        for case in ('manifest','nested-manifest','source','head','root'):
            with self.subTest(case=case):
                fx = self.fixture()
                if case == 'nested-manifest':
                    fx.write('docs/testing/mvg/nested/.keep','Existing ordinary namespace')
                capture = self.capture(fx)
                self.assertTrue(capture.snapshot['capture_complete'])
                path = self.archive(fx, capture)
                root = fx.root
                if case == 'manifest':
                    fx.dump('docs/testing/mvg/new.json',fx.manifest)
                elif case == 'nested-manifest':
                    fx.dump('docs/testing/mvg/nested/new.json',fx.manifest)
                elif case == 'source':
                    fx.write('docs/source.md','# Changed governed source\n')
                elif case == 'head':
                    fx.write('new.txt','New actual commit\n')
                    fx.run_git('add','new.txt')
                    fx.run_git('commit','-qm','New actual history')
                else:
                    other = self.fixture()
                    source = fx.root/Path(path).parent
                    destination = other.root/Path(path).parent
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(source,destination)
                    root = other.root
                self.assertFalse(protection.verify_protection(root,path)['ok'])

    def test_resigned_state_removed_objects_or_boundary_summary_reject(self):
        for change in ('state','object','summary','proof-type'):
            with self.subTest(change=change):
                fx = self.fixture()
                original = self.capture(fx)
                report, snapshot = copy.deepcopy(original.inventory), copy.deepcopy(original.snapshot)
                if change == 'state':
                    report['legacy_manifest_requirement']['state'] = 'required'
                elif change == 'object':
                    report['legacy_manifest_requirement']['proof']['objects'].pop(report['git']['head'])
                elif change == 'summary':
                    snapshot['legacy_manifest_requirement']['state'] = 'required'
                else:
                    report['legacy_manifest_requirement']['proof']['objects'] = []
                body = {k:v for k,v in report.items() if k not in protection._INVENTORY_ENVELOPE}
                report['content_identity'] = report['second_pass_identity'] = inventory.canonical_sha(body)
                snapshot['inventory']['content_identity'] = report['content_identity']
                snapshot['inventory']['raw_digest'] = inventory.digest(protection._json_bytes(report))
                if change != 'summary':
                    snapshot['legacy_manifest_requirement'] = initial.summary(report)
                snapshot['snapshot_digest'] = inventory.canonical_sha({k:v for k,v in snapshot.items() if k!='snapshot_digest'})
                forged = protection.ProtectionCapture(snapshot,report,original.raw_files,fx.root)
                path = self.archive(fx,forged)
                self.assertFalse(protection.verify_protection(fx.root,path)['ok'])

    def test_unrelated_historical_report_keeps_missing_debug_optional(self):
        foreign = self.fixture(empty=False)
        foreign.edit_task('back', lambda rows: rows[0]['evidence_refs'].append('logs/ci/debug/missing-summary.json'))
        original = inventory.collect_inventory(foreign.root, foreign.epics)
        self.assertTrue(original['adoptable'], original['diagnostics'])
        fx = self.fixture()
        historical = 'logs/ci/history/unrelated-inventory.json'
        fx.dump(historical, original)
        capture = protection.collect_protection(fx.root, fx.epics, historical_inventory=historical)
        self.assertTrue(capture.snapshot['capture_complete'], capture.snapshot['diagnostics'])
        self.assertEqual(capture.inventory['legacy_manifest_requirement']['state'], 'initially_absent')
        self.assertTrue(any(row['path']=='logs/ci/debug/missing-summary.json'
                            and row['state']=='missing-or-unreadable'
                            for row in capture.snapshot['historical_inventory']['input_comparison']))
        self.assertFalse((fx.root/'logs/ci/debug/missing-summary.json').exists())
        self.assertTrue(protection.verify_protection(fx.root,self.archive(fx,capture))['ok'])

    def test_staged_governance_is_archived_after_worktree_restore(self):
        for case in ('source-retirement','source-active','epics','policy','origins','capabilities','pending'):
            with self.subTest(case=case):
                fx = self.fixture()
                source = json.loads((fx.root/inventory.SOURCE_SET).read_bytes())
                reference = {'owner':'authority','ref':'docs/source.md',
                    'files':[{'path':'docs/source.md','raw_digest':inventory.digest((fx.root/'docs/source.md').read_bytes())}]}
                if case.startswith('source-'):
                    path = inventory.SOURCE_SET
                    if case == 'source-retirement':
                        source['retirements'] = [{'path':'docs/testing/mvg/staged-old.json'}]
                    else:
                        source['active_sources'].append('docs/testing/mvg/staged-old.json')
                        source['active_patterns'].append('docs/testing/mvg/staged-old.json')
                    raw = json.dumps(source).encode('utf-8')
                elif case == 'epics':
                    path = fx.epics
                    raw = (fx.root/path).read_bytes().replace(json.dumps(fx.sources[0]).encode('utf-8'),
                        b'"docs/testing/mvg/staged-old.json"')
                elif case == 'policy':
                    path = 'docs/planning/b-route/policy.v1.json'
                    raw = json.dumps({'schema_version':'newrouge.b-route-policy.v1','policy_id':'index-fixture',
                        'policy_revision':1,'switch_boundary':{'default_route':'A','a_write_allowed':False,
                        'allowed_a_operations':[],'authority_refs':[]},'frozen_a_refs':[reference]}).encode('utf-8')
                elif case == 'origins':
                    path = 'docs/planning/b-route/task-origins.v1.json'
                    raw = json.dumps({'schema_version':'newrouge.b-route-origins.v1','origins_id':'task-origins',
                        'revision':1,'tasks':[],'frozen_legacy_refs':[reference]}).encode('utf-8')
                else:
                    path = ('docs/planning/semantic-topology/capabilities.v1.json' if case == 'capabilities'
                            else 'docs/planning/semantic-topology/capability-apply.pending.json')
                    raw = b'{"legacy_index_trace":"synthetic negative only"}'
                self.stage_then_restore(fx, path, raw)
                report = inventory.collect_inventory(fx.root, fx.epics)
                self.assertFalse(report['adoptable'])
                self.assertEqual(report['legacy_manifest_requirement']['state'], 'required', report['diagnostics'])
                proof = report['legacy_manifest_requirement']['proof']
                rows = [row for row in initial._decode(proof['index_base64']).split(b'\0') if row]
                record = next(row for row in rows if row.split(b'\t',1)[1].decode('utf-8') == path)
                oid = record.split(b'\t',1)[0].split()[1].decode('ascii')
                self.assertEqual(initial._decode(proof['objects'][oid]['raw_base64']), raw)
                originals = {row['path']:(fx.root/row['path']).read_bytes() for row in report['inputs'] if row['exists']}
                self.assertEqual(initial.rederive(report, originals), 'required')
                forged = copy.deepcopy(report)
                forged['legacy_manifest_requirement']['proof']['objects'].pop(oid)
                with self.assertRaises(ValueError):
                    initial.rederive(forged, originals)

    def test_malformed_staged_governance_is_unknown_after_worktree_restore(self):
        cases = [(inventory.SOURCE_SET, b'{"schema_version":"chapter3.source-set.v1","active_patterns":false}'),
            ('epics', b'---\nstatus: final\ninputDocuments: false\n---\n'),
            ('epics', b'---\ninputDocuments:\n  - "../docs/testing/mvg/old.json"\n---\n'),
            ('docs/planning/b-route/policy.v1.json', b'{"schema_version":"newrouge.b-route-policy.v1","frozen_a_refs":false}'),
            ('docs/planning/b-route/task-origins.v1.json', b'{"schema_version":"newrouge.b-route-origins.v1","frozen_legacy_refs":false}'),
            ('docs/planning/semantic-topology/capabilities.v1.json', b'{invalid'),
            ('docs/planning/semantic-topology/capability-apply.pending.json', b'{invalid')]
        for path, raw in cases:
            with self.subTest(path=path, raw=raw):
                fx = self.fixture()
                self.stage_then_restore(fx, fx.epics if path == 'epics' else path, raw)
                report = inventory.collect_inventory(fx.root, fx.epics)
                self.assertFalse(report['adoptable'])
                self.assertEqual(report['legacy_manifest_requirement']['state'], 'unknown', report['diagnostics'])

    def test_unsafe_source_declarations_in_history_or_index_never_qualify(self):
        self.assertFalse(initial._declaration({'schema_version':'chapter3.source-set.v1',
            'active_patterns':['docs/source.md'],'active_sources':['docs/source.md']}))
        for route in ('history','index'):
            for field in ('active_sources','active_patterns','retirements'):
                with self.subTest(route=route, field=field):
                    fx = self.fixture()
                    original = json.loads((fx.root/inventory.SOURCE_SET).read_bytes())
                    changed = copy.deepcopy(original)
                    changed[field] = ([{'path':'../docs/testing/mvg/old.json'}] if field == 'retirements'
                                      else ['../docs/testing/mvg/old.json'])
                    fx.dump(inventory.SOURCE_SET, changed)
                    fx.run_git('add', inventory.SOURCE_SET)
                    if route == 'history':
                        fx.run_git('commit','-qm','Retain unsafe governed declaration')
                    fx.dump(inventory.SOURCE_SET, original)
                    if route == 'history':
                        fx.run_git('add', inventory.SOURCE_SET)
                        fx.run_git('commit','-qm','Restore safe governed declaration')
                    report = inventory.collect_inventory(fx.root, fx.epics)
                    self.assertFalse(report['adoptable'])
                    self.assertEqual(report['legacy_manifest_requirement']['state'], 'unknown', report['diagnostics'])


if __name__ == '__main__':
    unittest.main()
