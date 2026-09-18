import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))

from _godot_scene_graph import build_scene_graph


class GodotSceneGraphTests(unittest.TestCase):
    def test_main_scene_and_packed_scene_instance_are_confirmed_reachable(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Game.Godot/Scenes/Main.tscn"\n',
            'Game.Godot/Scenes/Main.tscn': '[gd_scene load_steps=2 format=3]\n[ext_resource type="PackedScene" path="res://Game.Godot/Scenes/Hud.tscn" id="1"]\n[node name="Main" type="Node"]\n[node name="Hud" parent="." instance=ExtResource("1")]\n',
            'Game.Godot/Scenes/Hud.tscn': '[gd_scene format=3]\n[node name="Hud" type="Control"]\n',
        }

        graph = build_scene_graph(sources)

        self.assertEqual(graph['main_scene'], 'Game.Godot/Scenes/Main.tscn')
        self.assertEqual(graph['nodes']['Game.Godot/Scenes/Main.tscn']['classification'], 'confirmed-reachable')
        self.assertEqual(graph['nodes']['Game.Godot/Scenes/Hud.tscn']['classification'], 'confirmed-reachable')
        self.assertEqual(graph['edges'][0]['target'], 'Game.Godot/Scenes/Hud.tscn')

    def test_cycle_is_bounded_and_reported(self):
        sources = {
            'project.godot': 'run/main_scene="res://Game.Godot/Scenes/A.tscn"',
            'Game.Godot/Scenes/A.tscn': '[gd_scene]\n[ext_resource type="PackedScene" path="res://Game.Godot/Scenes/B.tscn" id="1"]',
            'Game.Godot/Scenes/B.tscn': '[gd_scene]\n[ext_resource type="PackedScene" path="res://Game.Godot/Scenes/A.tscn" id="1"]',
        }

        graph = build_scene_graph(sources)

        self.assertEqual(len(graph['nodes']), 2)
        self.assertTrue(any(item['kind'] == 'cycle' for item in graph['diagnostics']))

    def test_dynamic_code_reference_is_unknown_and_not_confirmed(self):
        sources = {
            'project.godot': '',
            'Game.Godot/Scenes/Unused.tscn': '[gd_scene]\n',
            'Game.Godot/Scripts/Loader.gd': 'var scene = load(scene_path)\n',
        }

        graph = build_scene_graph(sources)

        self.assertEqual(graph['nodes']['Game.Godot/Scenes/Unused.tscn']['classification'], 'unreachable-candidate')
        self.assertTrue(any(item['classification'] == 'dynamic-unknown' for item in graph['code_references']))

    def test_static_scene_reference_from_attached_script_is_reachable(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")',
            'Main.gd': 'extends Node\nfunc go(): change_scene_to_file("res://Other.tscn")',
            'Other.tscn': '[gd_scene]\n[node name="Other" type="Node"]',
        }
        graph = build_scene_graph(sources)
        self.assertEqual(graph['nodes']['Other.tscn']['classification'], 'confirmed-reachable')
        edge = next(edge for edge in graph['edges'] if edge.get('kind') == 'script-reference')
        self.assertEqual(edge['evidence_level'], 'effective')

    def test_isolated_scene_literal_is_possible_reference(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")',
            'Main.gd': 'const NEXT_SCENE = "res://Other.tscn"',
            'Other.tscn': '[gd_scene]\n[node name="Other" type="Node"]',
        })
        edge = next(edge for edge in graph['edges'] if edge.get('kind') == 'script-reference')
        self.assertEqual(edge['evidence_level'], 'possible')

    def test_scene_constant_used_by_switch_call_is_effective_reference(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")',
            'Main.gd': 'const NEXT_SCENE = "res://Other.tscn"\nfunc go():\n    _switch_to(nav, NEXT_SCENE)',
            'Other.tscn': '[gd_scene]\n[node name="Other" type="Node"]',
        })
        edge = next(edge for edge in graph['edges'] if edge.get('kind') == 'script-reference')
        self.assertEqual(edge['evidence_level'], 'effective')

    def test_shared_child_does_not_report_false_cycle(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://A.tscn" type="PackedScene" id="1"]\n[ext_resource path="res://B.tscn" type="PackedScene" id="2"]\n[node name="Main" type="Node"]\n[node name="A" parent="." instance=ExtResource("1")]\n[node name="B" parent="." instance=ExtResource("2")]',
            'A.tscn': '[gd_scene]\n[ext_resource path="res://Shared.tscn" type="PackedScene" id="1"]\n[node name="A" type="Node"]\n[node name="Shared" parent="." instance=ExtResource("1")]',
            'B.tscn': '[gd_scene]\n[ext_resource path="res://A.tscn" type="PackedScene" id="1"]\n[node name="B" type="Node"]\n[node name="A" parent="." instance=ExtResource("1")]',
            'Shared.tscn': '[gd_scene]\n[node name="Shared" type="Node"]',
        }
        graph = build_scene_graph(sources)
        self.assertFalse(any(item['kind'] == 'cycle' for item in graph['diagnostics']))

    def test_nested_project_resolves_plugin_res_paths(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Tests.Godot/tests/Smoke.tscn" type="PackedScene" id="1"]\n[node name="Main" type="Node"]\n[node name="Smoke" parent="." instance=ExtResource("1")]',
            'Tests.Godot/project.godot': '[application]',
            'Tests.Godot/tests/Smoke.tscn': '[gd_scene]\n[ext_resource path="res://addons/gdUnit4/src/ui/parts/InspectorTreePanel.tscn" type="PackedScene" id="1"]\n[node name="Smoke" type="Node"]\n[node name="Inspector" parent="." instance=ExtResource("1")]',
            'Tests.Godot/addons/gdUnit4/src/ui/parts/InspectorTreePanel.tscn': '[gd_scene]\n[node name="InspectorTreePanel" type="Control"]',
        }
        graph = build_scene_graph(sources)
        scene = graph['nodes']['Tests.Godot/tests/Smoke.tscn']
        self.assertEqual(scene['external_resources']['1'], 'Tests.Godot/addons/gdUnit4/src/ui/parts/InspectorTreePanel.tscn')
        self.assertEqual(scene['nodes'][1]['instance'], 'Tests.Godot/addons/gdUnit4/src/ui/parts/InspectorTreePanel.tscn')

    def test_event_driven_scene_route_is_linked_through_controller(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[ext_resource path="res://Menu.tscn" type="PackedScene" id="2"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")\n[node name="Menu" parent="." instance=ExtResource("2")',
            'Main.gd': 'const OTHER := "res://Other.tscn"\nfunc _on_domain_event(type):\n    if type == "ui.menu.start":\n        _switch_to(nav, "res://Difficulty.tscn")',
            'Menu.tscn': '[gd_scene]\n[ext_resource path="res://Menu.gd" type="Script" id="1"]\n[node name="Menu" type="Control"]\nscript = ExtResource("1")',
            'Menu.gd': 'func start():\n    EventBus.PublishSimple("ui.menu.start", "ui", "{}")',
            'Difficulty.tscn': '[gd_scene]\n[node name="Difficulty" type="Control"]',
            'Other.tscn': '[gd_scene]\n[node name="Other" type="Control"]',
        }
        graph = build_scene_graph(sources)
        self.assertTrue(any(edge['kind'] == 'event-route' and edge['source'] == 'Menu.tscn' and edge['target'] == 'Difficulty.tscn' for edge in graph['edges']))
        route = next(edge for edge in graph['edges'] if edge.get('kind') == 'event-route')
        self.assertEqual(route['evidence_level'], 'effective')
        self.assertEqual(graph['nodes']['Difficulty.tscn']['classification'], 'confirmed-reachable')

    def test_event_constant_publisher_is_linked_through_controller(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Menu.tscn" type="PackedScene" id="1"]\n[node name="Main" type="Node"]\n[node name="Menu" parent="." instance=ExtResource("1")]',
            'Menu.tscn': '[gd_scene]\n[ext_resource path="res://Menu.cs" type="Script" id="1"]\n[node name="Menu" type="Control"]\nscript = ExtResource("1")',
            'Menu.cs': 'void Select() { EventBus.PublishSimple(EventTypes.Selected, "ui", "{}"); }',
            'EventTypes.cs': 'public const string Selected = "core.menu.selected";',
            'Controller.gd': 'func handle(type):\n    if type == "core.menu.selected":\n        _switch_to(nav, "res://Next.tscn")',
            'Next.tscn': '[gd_scene]\n[node name="Next" type="Control"]',
        }
        graph = build_scene_graph(sources)
        self.assertTrue(any(edge['source'] == 'Menu.tscn' and edge['target'] == 'Next.tscn' and edge['kind'] == 'event-route' for edge in graph['edges']))

    def test_scene_controller_call_resolves_conditional_scene_routes(self):
        sources = {
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")',
            'Main.gd': 'const COMBAT = "res://Combat.tscn"\nconst SHOP = "res://Shop.tscn"\nfunc StartRoute(kind):\n    var destination := ResolveRoute(kind)\n    _switch_to(nav, destination)\nfunc ResolveRoute(kind):\n    if kind == "combat":\n        return COMBAT\n    if kind == "shop":\n        return SHOP',
            'Map.tscn': '[gd_scene]\n[ext_resource path="res://Map.cs" type="Script" id="1"]\n[node name="Map" type="Control"]\nscript = ExtResource("1")',
            'Map.cs': 'void Start() { main.Call("StartRoute", "combat"); }',
            'Combat.tscn': '[gd_scene]\n[node name="Combat" type="Control"]',
            'Shop.tscn': '[gd_scene]\n[node name="Shop" type="Control"]',
        }
        graph = build_scene_graph(sources)
        targets = {edge['target'] for edge in graph['edges'] if edge.get('source') == 'Map.tscn' and edge.get('kind') == 'controller-route'}
        self.assertEqual(targets, {'Combat.tscn', 'Shop.tscn'})
        self.assertFalse(any(edge['kind'] == 'event-route' and edge['source'] == 'Menu.tscn' and edge['target'] == 'Other.tscn' for edge in graph['edges']))

    def test_invalid_scene_keeps_parse_error(self):
        graph = build_scene_graph({'project.godot': '', 'Game.Godot/Scenes/Broken.tscn': '[node name="Broken" type="Node"]'})

        node = graph['nodes']['Game.Godot/Scenes/Broken.tscn']
        self.assertEqual(node['classification'], 'unreachable-candidate')
        self.assertIn('parse_error', node)

    def test_missing_main_scene_is_explicit(self):
        graph = build_scene_graph({'project.godot': '[application]\nconfig/name="test"\n'})

        self.assertIsNone(graph['main_scene'])
        self.assertTrue(any(item['kind'] == 'missing_main_scene' for item in graph['diagnostics']))

    def test_script_relationships_include_scene_and_config_literals(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Game.Godot/Scenes/Main.tscn"',
            'Game.Godot/Scenes/Main.tscn': '[gd_scene]\n',
            'Game.Godot/Scripts/Main.gd': 'load("res://Game.Godot/Scenes/Other.tscn")\nFileAccess.open("res://Game.Core/Data/config.json", FileAccess.READ)',
        })
        refs = graph['code_references']
        self.assertTrue(any(x.get('target') == 'Game.Godot/Scenes/Other.tscn' and x.get('classification') == 'static-reference' for x in refs))
        self.assertTrue(any(x.get('target') == 'Game.Core/Data/config.json' and x.get('kind') == 'config-reference' for x in refs))

    def test_script_relationships_include_static_asset_literals(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"\n',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")',
            'Main.gd': 'load("res://Game.Godot/Assets/icon.png")',
            'Game.Godot/Assets/icon.png': '',
        })
        self.assertTrue(any(x.get('target') == 'Game.Godot/Assets/icon.png' and x.get('kind') == 'asset-reference' for x in graph['code_references']))

    def test_dynamic_player_portrait_candidate_attaches_to_player_portrait_node(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Combat.tscn"\n',
            'Combat.tscn': '[gd_scene]\n[ext_resource path="res://CombatScene.cs" type="Script" id="1"]\n[node name="Combat" type="Control"]\nscript = ExtResource("1")\n[node name="PlayerPortrait" type="TextureRect" parent="."]',
            'CombatScene.cs': 'private const string DefaultPlayerPortraitId = "player_fungal_knight";\nprivate static IEnumerable<string> BuildPlayerPortraitTextureCandidates(string portraitId) {}',
            'Game.Godot/Assets/Textures/Combat/Player/player_fungal_knight.png': '',
        }, known_paths=['Game.Godot/Assets/Textures/Combat/Player/player_fungal_knight.png'])
        node = next(n for n in graph['nodes']['Combat.tscn']['nodes'] if n['name'] == 'PlayerPortrait')
        self.assertIn('Game.Godot/Assets/Textures/Combat/Player/player_fungal_knight.png', node['resources'])

    def test_dynamic_asset_candidates_cover_enemy_card_and_intent_nodes(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Combat.tscn"\n',
            'Combat.tscn': '[gd_scene]\n[ext_resource path="res://CombatScene.cs" type="Script" id="1"]\n'
                           '[node name="Combat" type="Control"]\nscript = ExtResource("1")\n'
                           '[node name="EnemyPortrait" type="TextureRect" parent="."]\n'
                           '[node name="EnemyIntentIcon" type="TextureRect" parent="."]\n'
                           '[node name="CardButtonRow" type="Control" parent="."]\n',
            'CombatScene.cs': (
                'IEnumerable<string> BuildEnemyPortraitTextureCandidates(string id) {\n'
                '    yield return $"res://Game.Godot/Assets/Textures/Combat/Enemies/{id}.png";\n'
                '}\n'
                'IEnumerable<string> BuildEnemyIntentTextureCandidates(string key) {\n'
                '    yield return $"res://Game.Godot/Assets/UI/EnemyIntent/{key}.png";\n'
                '}\n'
                'IEnumerable<string> BuildCardFaceTextureCandidates(string id) {\n'
                '    yield return $"res://Game.Godot/Assets/Textures/Cards/{id}.png";\n'
                '}\n'
            ),
            'Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight.png': '',
            'Game.Godot/Assets/UI/EnemyIntent/attack.png': '',
            'Game.Godot/Assets/Textures/Cards/card_spore_slash.png': '',
        }, known_paths=[
            'Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight.png',
            'Game.Godot/Assets/UI/EnemyIntent/attack.png',
            'Game.Godot/Assets/Textures/Cards/card_spore_slash.png',
        ])
        nodes = {n['name']: n for n in graph['nodes']['Combat.tscn']['nodes']}
        self.assertIn('Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight.png', nodes['EnemyPortrait']['resources'])
        self.assertIn('Game.Godot/Assets/UI/EnemyIntent/attack.png', nodes['EnemyIntentIcon']['resources'])
        self.assertIn('Game.Godot/Assets/Textures/Cards/card_spore_slash.png', nodes['CardButtonRow']['resources'])

    def test_dynamic_asset_candidates_survive_nested_conditional_blocks(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Combat.tscn"\n',
            'Combat.tscn': '[gd_scene]\n[ext_resource path="res://CombatScene.cs" type="Script" id="1"]\n'
                           '[node name="Combat" type="Control"]\nscript = ExtResource("1")\n'
                           '[node name="EnemyPortrait" type="TextureRect" parent="."]\n',
            'CombatScene.cs': (
                'IEnumerable<string> BuildEnemyPortraitTextureCandidates(string id) {\n'
                '    if (id == "boss") { yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/boss.png"; }\n'
                '    yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/fallback.png";\n'
                '}\n'
            ),
            'Game.Godot/Assets/Textures/Combat/Enemies/boss.png': '',
            'Game.Godot/Assets/Textures/Combat/Enemies/fallback.png': '',
        }, known_paths=[
            'Game.Godot/Assets/Textures/Combat/Enemies/boss.png',
            'Game.Godot/Assets/Textures/Combat/Enemies/fallback.png',
        ])
        node = next(n for n in graph['nodes']['Combat.tscn']['nodes'] if n['name'] == 'EnemyPortrait')
        self.assertIn('Game.Godot/Assets/Textures/Combat/Enemies/boss.png', node['resources'])
        self.assertIn('Game.Godot/Assets/Textures/Combat/Enemies/fallback.png', node['resources'])

    def test_dynamic_asset_candidates_create_a_runtime_owner_when_scene_has_no_static_node(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Combat.tscn"\n',
            'Combat.tscn': '[gd_scene]\n[ext_resource path="res://CombatScene.cs" type="Script" id="1"]\n'
                           '[node name="Combat" type="Control"]\nscript = ExtResource("1")\n',
            'CombatScene.cs': 'IEnumerable<string> BuildEnemyPortraitTextureCandidates(string id) {\n'
                              '    yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/fallback.png";\n}\n',
            'Game.Godot/Assets/Textures/Combat/Enemies/fallback.png': '',
        }, known_paths=['Game.Godot/Assets/Textures/Combat/Enemies/fallback.png'])
        node = next(n for n in graph['nodes']['Combat.tscn']['nodes'] if n['name'] == 'EnemyPortrait')
        self.assertEqual(node['type'], 'TextureRect (runtime)')
        self.assertIn('Game.Godot/Assets/Textures/Combat/Enemies/fallback.png', node['resources'])

    def test_dynamic_asset_candidates_exclude_template_names_and_log_paths(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Combat.tscn"\n',
            'Combat.tscn': '[gd_scene]\n[ext_resource path="res://CombatScene.cs" type="Script" id="1"]\n'
                           '[node name="Combat" type="Control"]\nscript = ExtResource("1")\n'
                           '[node name="PlayerPortrait" type="TextureRect" parent="."]\n',
            'CombatScene.cs': (
                'IEnumerable<string> BuildPlayerPortraitTextureCandidates(string id) {\n'
                '    yield return $"res://Game.Godot/Assets/Textures/Combat/Player/{id}.png";\n'
                '    yield return "res://logs/cache/player_debug.png";\n'
                '    yield return "res://Game.Godot/Assets/Textures/Combat/Player/player_ok.png";\n'
                '}\n'
            ),
            'Game.Godot/Assets/Textures/Combat/Player/player_ok.png': '',
            'logs/cache/player_debug.png': '',
        }, known_paths=[
            'Game.Godot/Assets/Textures/Combat/Player/{id}.png',
            'Game.Godot/Assets/Textures/Combat/Player/player_ok.png',
            'logs/cache/player_debug.png',
        ])
        node = next(n for n in graph['nodes']['Combat.tscn']['nodes'] if n['name'] == 'PlayerPortrait')
        self.assertEqual(node['resources'], ['Game.Godot/Assets/Textures/Combat/Player/player_ok.png'])
        self.assertFalse(any('{id}' in ref.get('target', '') or '/logs/' in ref.get('target', '')
                             for ref in graph['code_references']))

    def test_scene_records_inheritance_and_subresources(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Game.Godot/Scenes/Main.tscn"',
            'Game.Godot/Scenes/Main.tscn': '[gd_scene load_steps=2 format=3]\n[ext_resource type="PackedScene" path="res://Game.Godot/Scenes/Base.tscn" id="1"]\n[sub_resource type="StyleBoxFlat" id="Style"]\n[node name="Main" type="Control" instance=ExtResource("1")]\ntheme_override_styles/panel = SubResource("Style")\n',
            'Game.Godot/Scenes/Base.tscn': '[gd_scene format=3]\n[node name="Base" type="Control"]\n'
        })
        scene = graph['nodes']['Game.Godot/Scenes/Main.tscn']
        self.assertEqual(scene['sub_resources'][0]['type'], 'StyleBoxFlat')
        self.assertTrue(any('SubResource' in r for n in scene['nodes'] for r in n['resources']))

    def test_scene_description_aggregates_nodes_scripts_events_and_routes(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Control"]\nscript = ExtResource("1")',
            'Main.gd': 'func _ready(): pass\nfunc _on_domain_event(type):\n    if type == "ui.menu.start":\n        change_scene_to_file("res://Next.tscn")',
            'Next.tscn': '[gd_scene]\n[node name="Next" type="Control"]',
        })
        scene = graph['nodes']['Main.tscn']
        self.assertIn('Main.gd', scene['functional_summary']['scripts'])
        self.assertIn('ui.menu.start', scene['functional_summary']['events'])
        self.assertIn('Next.tscn', scene['functional_summary']['scene_routes'])

    def test_scene_functional_summary_includes_script_configuration_references(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"\n',
            'Main.tscn': '[gd_scene]\n[ext_resource path="res://Main.gd" type="Script" id="1"]\n[node name="Main" type="Control"]\nscript = ExtResource("1")',
            'Main.gd': 'const CONFIG = "res://Game.Core/Data/settings.json"\n',
            'Game.Core/Data/settings.json': '{}',
        })
        summary = graph['nodes']['Main.tscn']['functional_summary']
        self.assertEqual(summary['config_references'], ['Game.Core/Data/settings.json'])

    def test_verified_task_binding_is_exposed_as_knowledge_context(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[node name="Main" type="Node"]',
        }, [{'task': {'id': 7, 'title': 'Reward flow', 'status': 'done'}, 'godot': {
            'scenes': [{'scene': 'Main.tscn', 'kind': 'declared_task_with_verified_static_attachment', 'witness': 'func go()'}]}}])
        context = graph['nodes']['Main.tscn']['knowledge_context'][0]
        self.assertEqual(context['task_id'], 7)
        self.assertEqual(context['title'], 'Reward flow')

    def test_task_test_reference_is_exposed_as_candidate_knowledge_context(self):
        graph = build_scene_graph({
            'project.godot': '[application]\nrun/main_scene="res://Main.tscn"',
            'Main.tscn': '[gd_scene]\n[node name="Main" type="Node"]',
        }, [{'task': {'id': 8, 'title': 'Menu flow', 'status': 'in-progress'}, 'godot': {
            'scenes': [], 'candidates': [{'scene': 'Main.tscn', 'kind': 'test_reference', 'evidence': 'Tests/SceneTests.gd'}]}}])
        context = graph['nodes']['Main.tscn']['knowledge_context'][0]
        self.assertEqual(context['task_id'], 8)
        self.assertEqual(context['level'], 'candidate')
        self.assertEqual(context['evidence'], 'test_reference')


if __name__ == '__main__':
    unittest.main()
