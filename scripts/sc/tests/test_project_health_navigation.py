"""Static navigation boundaries and resource provenance (ADR-0035)."""
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from _project_health_navigation import build_navigation, scene_nodes
from _knowledge_catalog_builder import DirectorySnapshot


class NavigationTests(unittest.TestCase):
    def test_core_does_not_expand_test_bootstrap_dependencies(self):
        scene = 'Game.Godot/Scenes/Reward.tscn'
        script = 'Game.Godot/Scripts/Reward.gd'
        test = 'Tests.Godot/tests/reward.gd'
        config = 'Game.Core/Data/cards.json'
        sources = {scene: '[ext_resource path="res://' + script + '" id="1"]\n[node name="Reward"]\nscript = ExtResource("1")',
                   script: 'load("res://' + config + '")\n# card.warrior.strike',
                   config: '{"cards":[{"id":"card.warrior.strike","cost":1},{"id":"card.warrior.other","cost":9}]}',
                   test: 'load("res://Game.Godot/Scenes/Main.tscn")',
                   'Game.Godot/Scenes/Main.tscn': '[node name="Main"]'}
        detail = {'task': {'id': 115, 'test_refs': [test]}, 'godot': {'scenes': [{'scene': scene}]}}
        nav = build_navigation(detail, {'sources': sources, 'revision': 'r'})
        self.assertEqual({s['path'] for s in nav['scenes'] if s['focus'] == 'core'}, {scene})
        self.assertEqual(nav['code'][0]['focus'], 'core')
        fields = nav['configs'][0]['focused_fields']
        self.assertEqual({f['record_id'] for f in fields}, {'card.warrior.strike'})
        self.assertEqual(nav['configs'][0]['field_count'], 4)

    def test_missing_and_illegal_task_roots_are_reported(self):
        nav = build_navigation({'task': {'refs': ['Game.Core/Missing.cs', 'Game.Core/../secret.json']}}, {'sources': {}, 'revision': 'r'})
        self.assertEqual({r['path'] for r in nav['unresolved_references']}, {'Game.Core/Missing.cs', 'Game.Core/../secret.json'})
        self.assertFalse(nav['code'])

    def test_quoted_spaces_and_uppercase_suffixes(self):
        from _project_health_navigation import references
        path = 'Game.Core/Data/My Deck.JSON'
        text = 'load("res://' + path + '"); other_call()'
        self.assertEqual([r['path'] for r in references(text)], [path])
        nav = build_navigation({'task': {'ref': path}}, {'sources': {path: '{"pick":2}'}})
        self.assertEqual(nav['configs'][0]['fields'][0]['value'], 2)

    def test_multiline_resources_and_complete_node_paths(self):
        path = 'Game.Godot/Scenes/A.tscn'
        text = '[ext_resource path="res://Game.Godot/Assets/a.PNG" id="1"]\n[node name="Root"]\n[node name="Left" parent="."]\n[node name="Right" parent="."]\n[node name="Icon" parent="Left"]\ntextures = [\n ExtResource("1"),\n]\n[node name="Icon" parent="Right"]\ntextures = {\n "art": ExtResource("1")\n}'
        nodes = scene_nodes(path, {path: text}, {path, 'Game.Godot/Assets/a.PNG'})
        self.assertEqual([n['node_path'] for n in nodes], ['.', 'Left', 'Right', 'Left/Icon', 'Right/Icon'])
        self.assertEqual(nodes[3]['properties'][0]['resources'][0]['path'], 'Game.Godot/Assets/a.PNG')
        self.assertEqual(nodes[4]['properties'][0]['resources'][0]['path'], 'Game.Godot/Assets/a.PNG')

    def test_resource_depth_and_expansion_limits_are_visible(self):
        path = 'Game.Godot/Scenes/A.tscn'
        blocks = ['[sub_resource type="Resource" id="%s"]\nnext = SubResource("%s")' % (i, i + 1) for i in range(100)]
        text = '\n'.join(blocks) + '\n[node name="A"]\nvalue = SubResource("0")'
        nodes = scene_nodes(path, {path: text}, {path})
        self.assertIn('depth_limit', str(nodes))
        wide = '[node name="A"]\nvalue = [' + ','.join('SubResource("missing")' for _ in range(600)) + ']'
        self.assertIn('expansion_limit', str(scene_nodes(path, {path: wide}, {path})))

    def test_cross_tres_depth_limit_and_uppercase_resources(self):
        sources = {'Game.Godot/Resources/%s.TRES' % i:
                   '[ext_resource path="res://Game.Godot/Resources/%s.TRES" id="1"]\n[resource]\nnext = ExtResource("1")' % (i + 1)
                   for i in range(12)}
        nodes = scene_nodes('Game.Godot/Resources/0.TRES', sources, set(sources))
        self.assertIn('cross_resource_depth_limit', str(nodes))

    def test_uppercase_asset_is_classified_from_literal_path(self):
        path = 'Game.Godot/Scripts/A.GD'
        asset = 'Game.Godot/Assets/My Image.PNG'
        nav = build_navigation({'task': {'ref': path}}, {'sources': {path: 'load("res://' + asset + '")'}, 'file_manifest': [path, asset]})
        self.assertEqual(nav['assets'][0]['path'], asset)
        self.assertEqual(nav['code'][0]['path'], path)

    def test_deep_json_returns_parse_error_without_failing_task(self):
        path = 'Game.Core/Data/deep.json'
        nav = build_navigation({'task': {'ref': path}}, {'sources': {path: '[' * 1200 + '0' + ']' * 1200}})
        self.assertTrue(nav['configs'][0]['parse_error'])

    def test_json_raw_escapes_columns_and_repeated_values(self):
        from _project_health_navigation import located_fields
        text = '{"x":"a\\nb","y":2,"z":2}'
        rows = located_fields(text)
        self.assertEqual([(r['pointer'], r['column'], r['evidence']) for r in rows], [('/x', 6, '"a\\nb"'), ('/y', 17, '2'), ('/z', 23, '2')])

    def test_scan_includes_config_but_source_endpoint_rejects_binary(self):
        import contextlib
        import io
        from project_health_knowledge import scan, read_json, write_json, base_dir, main
        from scripts.sc.tests.test_project_health_knowledge import TasksTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            TasksTests().make_scan_source(root)
            config_path = root / 'scripts/python/project_health_knowledge_config.json'
            config = read_json(config_path)
            config['source_paths'].extend(['Game.Core', 'Game.Godot'])
            write_json(config_path, config)
            write_json(root / 'Game.Core/Data/deck.json', {'pick': 2})
            assets = root / 'Game.Godot/Assets'
            assets.mkdir(parents=True)
            (assets / 'a.png').write_bytes(b'\xff\x00')
            scan(root)
            state = read_json(base_dir(root) / 'latest.json')
            self.assertIn('Game.Core/Data/deck.json', state['sources'])
            self.assertIn('Game.Godot/Assets/a.png', state['file_manifest'])
            self.assertNotIn('Game.Godot/Assets/a.png', state['sources'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['source', '--repo-root', str(root), '--path', 'Game.Godot/Assets/a.png']), 1)

    def test_binary_manifest_is_content_bound_and_not_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / 'Game.Godot/Assets'
            assets.mkdir(parents=True)
            image = assets / 'a.png'
            image.write_bytes(b'\xff\x00')
            first = DirectorySnapshot(root, ['Game.Godot'])
            self.assertIn('Game.Godot/Assets/a.png', first.paths)
            image.write_bytes(b'\xff\x01')
            self.assertNotEqual(first.commit, DirectorySnapshot(root, ['Game.Godot']).commit)
            self.assertEqual(first.read_bytes('Game.Godot/Assets/a.png'), b'\xff\x00')

    def test_resource_cycles_stop_and_missing_paths_stay_unavailable(self):
        sources = {'Game.Godot/Resources/A.tres': '[ext_resource path="res://Game.Godot/Resources/A.tres" id="1"]\n[resource]\ntexture = ExtResource("1")'}
        nodes = scene_nodes(next(iter(sources)), sources, set(sources))
        self.assertEqual(len(nodes[0]['properties'][0]['resources']), 1)

    def test_repeated_keys_have_distinct_pointer_locations(self):
        from _project_health_navigation import located_fields
        rows = located_fields('{"cards":[{"pick":1},\n{"pick":2}],"a/b~":true}')
        self.assertEqual([(r['pointer'], r['line']) for r in rows], [('/cards/0/pick', 1), ('/cards/1/pick', 2), ('/a~1b~0', 2)])

    def test_real_task_sources_cover_starter_deck_and_dynamic_reward(self):
        from _project_health_tasks import task_details, attach_task_scenes
        from project_health_knowledge import DEFAULT_CONFIG
        root = Path(__file__).resolve().parents[3]
        snapshot = DirectorySnapshot(root, ['.taskmaster/tasks', 'Game.Core', 'Game.Core.Tests', 'Game.Godot', 'Tests.Godot/tests'])
        sources = {p: snapshot.read_text(p) for p in snapshot.paths if Path(p).suffix in {'.json', '.cs', '.gd', '.tscn', '.tres'}}
        details = task_details(snapshot)
        attach_task_scenes(details, sources, DEFAULT_CONFIG['task_scene_bindings'])
        state = {'revision': snapshot.commit, 'sources': sources, 'file_manifest': snapshot.paths}
        starter = build_navigation(next(d for d in details if str(d['task']['id']) == '24'), state)
        self.assertIn('Game.Core/Data/m1-warrior-starting-deck.json', [c['path'] for c in starter['configs']])
        reward = build_navigation(next(d for d in details if str(d['task']['id']) == '115'), state)
        self.assertIn('Game.Godot/Scenes/Reward.tscn', [s['path'] for s in reward['scenes']])
        self.assertTrue(reward['assets'])
        self.assertTrue(all(not a['runtime_observed'] for a in reward['assets']))

    def test_resource_chain_crosses_tres_and_preserves_instance(self):
        sources = {
            'Game.Godot/Scenes/A.tscn': '[ext_resource path="res://Game.Godot/Resources/A.tres" id="1"]\n[node name="A" instance=ExtResource("1")]\ntexture = ExtResource("1")',
            'Game.Godot/Resources/A.tres': '[ext_resource path="res://Game.Godot/Assets/a.png" id="2"]\n[resource]\ntexture = ExtResource("2")',
        }
        nodes = scene_nodes('Game.Godot/Scenes/A.tscn', sources, {*sources, 'Game.Godot/Assets/a.png'})
        self.assertTrue(nodes[0]['instance'])
        self.assertIn('Game.Godot/Assets/a.png', [x['path'] for x in nodes[0]['properties'][0]['resources']])

    def test_candidate_traversal_and_exact_field_location(self):
        sources = {'Game.Core.Tests/DeckTests.cs': 'card.warrior.strike',
                   'Game.Core/Data/deck.json': '{\n "id": "card.warrior.strike",\n "art": "Game.Godot/Assets/a.png",\n "pick": 2\n}'}
        detail = {'task': {'id': 24, 'ref': 'Game.Core.Tests/DeckTests.cs'}}
        nav = build_navigation(detail, {'revision': 'main-revision', 'sources': sources,
                                       'file_manifest': [*sources, 'Game.Godot/Assets/a.png']})
        self.assertEqual(nav['assets'][0]['evidence_kind'], 'static_candidate')
        field = next(f for f in nav['configs'][0]['fields'] if f['pointer'] == '/pick')
        self.assertEqual(field['line'], 4)
        self.assertEqual(field['value'], 2)
        self.assertFalse(nav['assets'][0]['runtime_observed'])
        self.assertEqual(nav['tests'][0]['command_status'], 'suggested_not_executed')

    def test_unscanned_reference_is_reported_without_reading_it(self):
        path = 'Game.Godot/Scripts/A.gd'
        nav = build_navigation({'task': {'ref': path}}, {'sources': {path: 'load("res://Game.Godot/Assets/missing.png")'}, 'revision': 'r'})
        self.assertTrue(nav['unresolved_references'])
        self.assertFalse(nav['assets'])


if __name__ == '__main__':
    unittest.main()
