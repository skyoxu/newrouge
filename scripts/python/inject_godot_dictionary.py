"""Inject simulated LLM data-dictionary explanations into the latest Godot snapshot."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'logs/ci/project-health-knowledge/latest.json'
OUTPUT = ROOT / 'docs/knowledge/catalog/godot-elements.json'

def explain(kind: str, path: str, name: str = '') -> str:
    label = name or Path(path).stem
    if kind == 'scene':
        return f"Scene resource {label}; groups a reusable Godot UI or gameplay surface and participates in the statically detected scene graph."
    if kind == 'node':
        return f"Node {label}; provides the {name or 'declared'} scene element and is configured from the parent scene."
    if kind == 'script':
        return f"Script {label}; owns scene behavior, event handling, state binding, or navigation logic discovered by static analysis."
    if kind == 'config':
        return f"Configuration resource {label}; supplies structured data read by Godot or shared runtime code."
    if kind == 'asset':
        return f"Asset resource {label}; provides visual, audio, font, or other imported content referenced by the project."
    if kind == 'event':
        return f"Published event {label}; communicates a state or user action to subscribed handlers."
    if kind == 'function':
        return f"Function {label}; executable behavior entry point discovered in an attached script."
    return f"Godot element {label}; statically indexed project resource."

def main() -> int:
    state = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    graph = state.get('scene_graph') or {}
    dictionary = {'schema_version': 'newrouge.godot-data-dictionary.v1', 'generated_by': 'simulated-llm-chapter6', 'source_revision': state.get('revision'), 'entries': {}}
    for path, scene in graph.get('nodes', {}).items():
        entry = {'kind': 'scene', 'path': path, 'description': explain('scene', path), 'status': 'simulated'}
        dictionary['entries'][path] = entry
        scene['dictionary'] = entry
        for node in scene.get('nodes', []):
            node_path = f"{path}::{node.get('parent') or '.'}/{node.get('name') or '(unnamed)'}"
            node_entry = {'kind': 'node', 'path': node_path, 'description': explain('node', node_path, node.get('name') or node.get('type') or 'Node'), 'status': 'simulated'}
            dictionary['entries'][node_path] = node_entry
            node['dictionary'] = node_entry
        summary = scene.get('functional_summary', {})
        summary['script_descriptions'] = {script: explain('script', script) for script in summary.get('scripts', [])}
        for script in summary.get('scripts', []):
            dictionary['entries'].setdefault(script, {
                'kind': 'script', 'path': script,
                'description': explain('script', script), 'status': 'simulated'
            })
        summary['config_descriptions'] = {}
        for edge in graph.get('code_references', []):
            if edge.get('source') in summary['scripts'] and edge.get('kind') == 'config-reference':
                target = edge.get('target')
                summary['config_descriptions'][target] = explain('config', target)
                dictionary['entries'].setdefault(target, {'kind': 'config', 'path': target, 'description': explain('config', target), 'status': 'simulated'})
        summary['event_descriptions'] = {event: explain('event', event) for event in summary.get('events', [])}
        summary['function_descriptions'] = {name: explain('function', name) for name in summary.get('functions', [])}
        scene['functional_summary'] = summary
        for resource in scene.get('external_resources', {}).values():
            if resource and not resource.endswith(('.gd', '.cs')):
                kind = 'config' if Path(resource).suffix.lower() in {'.json', '.csv', '.cfg', '.ini', '.yaml', '.yml', '.tres', '.res'} else 'asset'
                dictionary['entries'].setdefault(resource, {'kind': kind, 'path': resource, 'description': explain(kind, resource), 'status': 'simulated'})
        for node in scene.get('nodes', []):
            for resource in node.get('resources', []):
                if not resource or resource.startswith('SubResource(') or resource.endswith(('.gd', '.cs')):
                    continue
                kind = 'config' if Path(resource).suffix.lower() in {'.json', '.csv', '.cfg', '.ini', '.yaml', '.yml', '.tres', '.res'} else 'asset'
                dictionary['entries'].setdefault(resource, {'kind': kind, 'path': resource, 'description': explain(kind, resource), 'status': 'simulated'})
    for edge in graph.get('edges', []):
        edge['dictionary'] = {'description': f"Static relation from {Path(edge.get('source', '')).name} to {Path(edge.get('target', '')).name}; evidence: {edge.get('evidence') or edge.get('kind', 'reference')}."}
    graph['data_dictionary'] = dictionary
    state['scene_graph'] = graph
    SNAPSHOT.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    OUTPUT.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'ok', 'entries': len(dictionary['entries']), 'snapshot': str(SNAPSHOT.relative_to(ROOT)).replace('\\', '/')}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
