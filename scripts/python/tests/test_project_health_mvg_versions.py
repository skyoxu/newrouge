from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _project_health_mvg_versions import build_overview, with_runtime_evidence


class Snapshot:
    commit = 'a' * 40

    def __init__(self):
        self.files = {
            'docs/workflows/chapter3-source-set.json': json.dumps({'active_sources': ['docs/gdd/old.md', 'docs/gdd/new.md']}).encode(),
            'docs/gdd/old.md': b'old', 'docs/gdd/new.md': b'new',
            'docs/testing/mvg/cumulative.json': json.dumps({
                'schema_version': 'newrouge.mvg-integration.v1', 'mvg_id': 'cumulative',
                'coverage': {'mode': 'full', 'blocking_task_ids': [3]},
                'flows': [{'id': 'save-return', 'outcome': 'Save and return', 'task_ids': [1, 2, 3],
                           'test_ids': ['save'], 'handoffs': [{'producer_task': 1, 'consumer_task': 2, 'owner_task': 2, 'contract_ref': 'Game.Core/Contracts/Save.cs'}]}],
                'tests': [{'id': 'save', 'evidence_level': 'runtime'}],
            }).encode(),
        }
        self.paths = tuple(self.files)

    def read_bytes(self, path):
        return self.files[path]

    def read_text(self, path):
        return self.files[path].decode()

    def digest(self, path):
        return hashlib.sha256(self.files[path]).hexdigest()


class MvgVersionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Snapshot()
        self.details = [
            {'task': {'id': id_, 'title': f'Task {id_}', 'status': 'done'},
             'mappings': {'tasks_back': [{'overlay_refs': [f'docs/overlay/{id_}.md'],
                                          'contractRefs': [f'Game.Core/Contracts/{id_}.cs'], 'adr_refs': ['ADR-0001']}], 'tasks_gameplay': []},
             'godot': {'scenes': [{'scene': f'Game.Godot/Scenes/{id_}.tscn'}]}}
            for id_ in (1, 2, 3)
        ]
        self.graph = {'nodes': {f'Game.Godot/Scenes/{id_}.tscn': {
            'classification': 'confirmed-reachable', 'nodes': [{'parent': '.', 'name': 'Root', 'resources': [f'Game.Godot/Assets/{id_}.png']}]}
            for id_ in (1, 2, 3)}}
        self.topology = {'available': True, 'fresh': True, 'identity': {'revision': self.snapshot.commit},
                         'nodes': {'source_blocks': [{'block_id': f'B{id_}', 'source_path': f'docs/gdd/{name}.md',
                                                     'source_sha256': self.snapshot.digest(f'docs/gdd/{name}.md')}
                                                    for id_, name in ((1, 'old'), (2, 'new'))]},
                         'task_trace': {'1': {'source_blocks': ['B1']}, '2': {'source_blocks': ['B2']},
                                        '3': {'source_blocks': []}}}

    def test_two_gdds_share_cumulative_flow_without_stealing_unmapped_task(self):
        overview = build_overview(self.snapshot, self.details, self.topology, self.graph)
        versions = {version['gdd_path']: version for version in overview['versions']}
        self.assertEqual(['1'], versions['docs/gdd/old.md']['task_ids'])
        self.assertEqual(['2'], versions['docs/gdd/new.md']['task_ids'])
        self.assertNotIn('3', [id_ for version in overview['versions'] for id_ in version['task_ids']])
        self.assertEqual(['Game.Godot/Assets/2.png'], versions['docs/gdd/new.md']['scenes'][0]['resources'])
        self.assertEqual(2, len(overview['manifests'][0]['flows'][0]['version_ids']))
        self.assertEqual(['1', '2', '3'], overview['manifests'][0]['flows'][0]['task_ids'])

    def test_stale_topology_and_changed_gdd_do_not_assign_tasks(self):
        self.topology['identity']['revision'] = 'b' * 40
        self.assertTrue(all(not version['task_ids'] for version in build_overview(self.snapshot, self.details, self.topology, self.graph)['versions']))
        self.topology['identity']['revision'] = self.snapshot.commit
        self.snapshot.files['docs/gdd/new.md'] = b'changed'
        overview = build_overview(self.snapshot, self.details, self.topology, self.graph)
        self.assertEqual([], next(v for v in overview['versions'] if v['gdd_path'].endswith('new.md'))['task_ids'])

    def test_runtime_requires_same_main_and_exact_manifest(self):
        overview = build_overview(self.snapshot, self.details, self.topology, self.graph)
        manifest = overview['manifests'][0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'logs/ci/mvg-acceptance/20260101'
            folder.mkdir(parents=True)
            run = {'manifest': manifest['path'], 'manifest_sha256': manifest['sha256'],
                   'mode': 'run', 'source_revision': overview['revision'], 'base_commit': overview['revision'],
                   'workspace_dirty': False, 'status': 'passed', 'runtime_verified': True, 'run_id': '20260101'}
            target = folder / 'summary.json'
            target.write_text(json.dumps(run))
            self.assertEqual('passed', with_runtime_evidence(overview, root)['manifests'][0]['evidence']['status'])
            for field, wrong in (('manifest_sha256', 'sha256:wrong'), ('source_revision', 'workspace:dirty'),
                                 ('workspace_dirty', True), ('mode', 'plan')):
                changed = {**run, field: wrong}
                target.write_text(json.dumps(changed))
                self.assertEqual('not_verified', with_runtime_evidence(overview, root)['manifests'][0]['evidence']['status'], field)


if __name__ == '__main__':
    unittest.main()
