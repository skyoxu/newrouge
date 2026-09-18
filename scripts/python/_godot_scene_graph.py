"""Conservative static Godot scene graph extraction for project-health snapshots."""
from __future__ import annotations

import re
import posixpath
from collections import deque
from pathlib import PurePosixPath


SCENE_SUFFIX = '.tscn'
CONFIG_SUFFIXES = {'.json', '.cfg', '.ini', '.csv', '.yaml', '.yml', '.tres', '.res'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif'}


def _is_excluded_asset_path(path: str) -> bool:
    normalized = str(path).replace('\\', '/').casefold()
    return '{' in normalized or '}' in normalized or 'log' in normalized
_PATH = re.compile(r'res://([^"\'\s)]+\.tscn)')
_RES_PATH = re.compile(r'res://([^"\'\s)]+)')
_EXT = re.compile(r'^\[ext_resource\b[^\]]*\bpath="([^"]+)"[^\]]*\bid="([^"]+)"')
_NODE = re.compile(r'^\[node\b([^\]]*)\]')
_SUB = re.compile(r'^\[sub_resource\s+type="([^"]+)"\s+id="([^"]+)"\]')


def _clean(path: str) -> str:
    return path.removeprefix('res://').replace('\\', '/')


def _resolve_target(source: str, target: str, known: set[str]) -> str:
    """Resolve plugin-local res:// paths when a nested Godot project is scanned."""
    target = posixpath.normpath(target).lstrip('./')
    if target in known:
        return target
    parts = source.split('/')
    for index in range(len(parts) - 1, 0, -1):
        candidate = posixpath.normpath('/'.join(parts[:index] + [target]))
        if candidate in known:
            return candidate
    return target


def _scene_evidence(line: str) -> tuple[str, str]:
    """Return a conservative trigger level and reason for a scene literal."""
    if re.search(r'\b(?:change_scene(?:_to_file|_to_packed)?|switch_to|instantiate)\s*\(', line):
        return 'effective', 'explicit scene switch or instantiation call'
    return 'possible', 'scene path literal without a statically proven trigger'


def _main_scene(project_text: str) -> str | None:
    match = re.search(r'(?:run/main_scene|application/run/main_scene)\s*=\s*"res://([^"\r\n]+)"', project_text)
    return match.group(1) if match else None


def _gd_function_bodies(text: str) -> dict[str, str]:
    """Extract bounded GDScript function bodies for conservative route tracing."""
    lines = text.splitlines()
    starts = []
    for index, line in enumerate(lines):
        match = re.match(r'^(\s*)func\s+([A-Za-z_]\w*)\s*\(', line)
        if match:
            starts.append((index, len(match.group(1)), match.group(2)))
    bodies = {}
    for position, (start, indent, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        bodies[name] = '\n'.join(lines[start:end])
    return bodies


def _parse_scene(path: str, text: str) -> tuple[dict, list[dict], list[dict]]:
    ext = {}
    sub_resources = []
    nodes = []
    errors = []
    for line_no, line in enumerate(text.splitlines(), 1):
        m = _EXT.match(line)
        if m:
            ext[m.group(2)] = _clean(m.group(1))
            continue
        m = _SUB.match(line)
        if m:
            sub_resources.append({'type': m.group(1), 'id': m.group(2), 'line': line_no})
            continue
        m = _NODE.match(line)
        if m:
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            instance = re.search(r'instance=ExtResource\("([^"]+)"\)', m.group(1))
            node = {'name': attrs.get('name', ''), 'type': attrs.get('type', 'inherited'),
                    'parent': attrs.get('parent', '.'), 'line': line_no,
                    'instance': ext.get(instance.group(1)) if instance else None,
                    'resources': []}
            if instance and instance.group(1) not in ext:
                node['parse_error'] = 'missing ExtResource ' + instance.group(1)
                errors.append({'kind': 'parse_error', 'scene': path, 'line': line_no,
                                'reason': node['parse_error']})
            nodes.append(node)
        elif nodes:
            resources = [_clean(m.group(1)) for m in re.finditer(r'res://([^"\'\s)]+)', line)]
            resources.extend(f'SubResource({m.group(1)})' for m in re.finditer(r'SubResource\("([^"]+)"\)', line))
            nodes[-1]['resources'].extend(resources)
    if not text.lstrip().startswith(('[gd_scene', '[gd_resource')):
        errors.append({'kind': 'parse_error', 'scene': path, 'line': 1, 'reason': 'missing gd_scene header'})
    refs = [{'target': target, 'source': path, 'line': line_no, 'kind': 'packed_scene',
             'evidence_level': 'effective', 'evidence': 'PackedScene instance declared in scene'}
            for line_no, line in enumerate(text.splitlines(), 1)
            for target in [_clean(m.group(1)) for m in _PATH.finditer(line)]
            if target != path]
    # Keep only actual PackedScene references; arbitrary resource paths are not scene edges.
    refs = [r for r in refs if r['target'].lower().endswith(SCENE_SUFFIX)]
    root = next((n for n in nodes if n.get('parent') == '.'), nodes[0] if nodes else {})
    scripts = [v for v in ext.values() if v.endswith(('.cs', '.gd'))]
    result = {'path': path, 'nodes': nodes, 'external_resources': ext, 'sub_resources': sub_resources,
              'child_scene_references': [ref['target'] for ref in refs],
              'description': f"Godot {root.get('type', 'scene')} scene with {len(nodes)} nodes" + (f"; script: {scripts[0]}" if scripts else '')}
    if errors:
        result['parse_error'] = '; '.join(item['reason'] for item in errors)
    return result, refs, errors


def build_scene_graph(sources: dict[str, str], task_details: list[dict] | None = None, known_paths: list[str] | tuple[str, ...] | None = None) -> dict:
    normalized = {path.replace('\\', '/'): text for path, text in sources.items()}
    known_file_paths = {path.replace('\\', '/') for path in (known_paths or [])}
    scenes = {path: text for path, text in normalized.items() if path.lower().endswith(SCENE_SUFFIX)}
    main = _main_scene(normalized.get('project.godot', ''))
    diagnostics = []
    if not main:
        diagnostics.append({'kind': 'missing_main_scene', 'reason': 'project.godot has no application/run/main_scene'})
    elif main not in scenes:
        diagnostics.append({'kind': 'missing_main_scene', 'reason': 'configured main scene is not scanned', 'path': main})

    parsed, edges = {}, []
    for path, text in sorted(scenes.items()):
        try:
            parsed[path], refs, errors = _parse_scene(path, text)
            edges.extend(refs)
            diagnostics.extend(errors)
        except Exception as exc:  # preserve malformed input as evidence
            parsed[path] = {'path': path, 'nodes': [], 'external_resources': {}, 'parse_error': str(exc)}
            diagnostics.append({'kind': 'parse_error', 'scene': path, 'reason': str(exc)})

    known_paths = set(normalized) | known_file_paths
    for scene in parsed.values():
        for key, target in list(scene.get('external_resources', {}).items()):
            scene['external_resources'][key] = _resolve_target(scene['path'], target, known_paths)
        for node in scene.get('nodes', []):
            if node.get('instance'):
                node['instance'] = _resolve_target(scene['path'], node['instance'], known_paths)
    for edge in edges:
        edge['target'] = _resolve_target(edge['source'], edge['target'], known_paths)

    static_code = []
    dynamic_code = []
    for path, text in normalized.items():
        if not path.lower().endswith(('.gd', '.cs')):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in _RES_PATH.finditer(line):
                target = _clean(match.group(1))
                if target.lower().endswith(SCENE_SUFFIX):
                    evidence_level, evidence = _scene_evidence(line)
                    static_code.append({'source': path, 'target': target, 'line': line_no,
                                        'classification': 'static-reference',
                                        'evidence_level': evidence_level, 'evidence': evidence})
                elif PurePosixPath(target).suffix.lower() in CONFIG_SUFFIXES:
                    static_code.append({'source': path, 'target': target, 'line': line_no,
                                        'classification': 'static-reference', 'kind': 'config-reference'})
                else:
                    suffix = PurePosixPath(target).suffix.lower()
                    if suffix in IMAGE_SUFFIXES | {'.wav', '.ogg', '.mp3', '.ttf', '.otf'} and not _is_excluded_asset_path(target):
                        static_code.append({'source': path, 'target': target, 'line': line_no,
                                            'classification': 'static-reference', 'kind': 'asset-reference'})
            if re.search(r'\b(?:load|preload|ResourceLoader\.load)\s*\(', line) and not _PATH.search(line):
                dynamic_code.append({'source': path, 'line': line_no,
                                      'classification': 'dynamic-unknown', 'evidence': line.strip()[:400]})

    for edge in static_code:
        edge['target'] = _resolve_target(edge['source'], edge['target'], known_paths)

    for scene_path, scene in parsed.items():
        scripts = sorted({value for value in scene.get('external_resources', {}).values()
                          if value.lower().endswith(('.gd', '.cs'))})
        events = set()
        functions = set()
        routes = set()
        config_references = set()
        for script in scripts:
            text = normalized.get(script, '')
            events.update(re.findall(r'(?:Publish|PublishSimple)\s*\(\s*["\']([^"\']+)', text))
            events.update(re.findall(r'["\'](ui\.[A-Za-z0-9_.-]+)["\']', text))
            functions.update(re.findall(r'\b(?:func|void|bool|private|public|protected|internal|static)\s+([A-Za-z_]\w*)\s*\(', text))
            routes.update(edge['target'] for edge in static_code
                          if edge['source'] == script and edge['target'].lower().endswith(SCENE_SUFFIX))
            config_references.update(edge['target'] for edge in static_code
                                     if edge['source'] == script and edge.get('kind') == 'config-reference')
        node_types = sorted({node.get('type', '') for node in scene.get('nodes', []) if node.get('type')})
        scene['functional_summary'] = {'scripts': scripts, 'events': sorted(events),
                                       'functions': sorted(functions), 'scene_routes': sorted(routes),
                                       'node_types': node_types,
                                       'config_references': sorted(config_references)}

        # Resolve static and interpolated texture candidates from attached scripts
        # to the concrete display node they serve (portraits, cards, intent icons).
        for script in scripts:
            script_text = normalized.get(script, '')
            if not script_text:
                continue
            function_starts = re.finditer(r'(?:Build|Resolve)([A-Za-z0-9_]*?(?:Portrait|Card|Intent|Texture)[A-Za-z0-9_]*)[^{;]*\{', script_text, re.S)
            for function_match in function_starts:
                function_name = function_match.group(1)
                body_start = function_match.end()
                depth = 1
                cursor = body_start
                while cursor < len(script_text) and depth:
                    if script_text[cursor] == '{': depth += 1
                    elif script_text[cursor] == '}': depth -= 1
                    cursor += 1
                body = script_text[body_start:cursor - 1] if depth == 0 else script_text[body_start:]
                candidates = []
                for raw in re.findall(r'res://([^"\'\s)]+)', body):
                    if '{' in raw:
                        prefix, suffix = raw.split('{', 1)[0], raw.split('}', 1)[-1]
                        candidates.extend(path for path in known_paths if path.startswith(prefix) and path.endswith(suffix))
                    else:
                        candidates.append(_resolve_target(script, raw, known_paths))
                candidates = sorted(set(path for path in candidates if path in known_paths and PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES and not _is_excluded_asset_path(path)))
                if not candidates:
                    continue
                lowered = function_name.lower()
                if 'player' in lowered:
                    node_names = {'PlayerPortrait'}
                elif 'enemy' in lowered and 'intent' not in lowered:
                    node_names = {'EnemyPortrait'}
                elif 'intent' in lowered:
                    node_names = {'EnemyIntent', 'EnemyIntentIcon', 'IntentIcon'}
                else:
                    node_names = {'CardFace', 'GhostFace', 'HandCards', 'CardButtonRow'}
                owners = [node for node in scene.get('nodes', []) if node.get('name') in node_names]
                if not owners:
                    # Some C# UIs create their display controls at runtime.  Preserve
                    # the resource-to-node relationship in the scene detail instead
                    # of silently discarding it merely because the .tscn has no node.
                    runtime_name = sorted(node_names)[0]
                    runtime_node = {'name': runtime_name, 'type': 'TextureRect (runtime)',
                                    'parent': 'Runtime', 'resources': [],
                                    'runtime_created': True}
                    scene.setdefault('nodes', []).append(runtime_node)
                    owners = [runtime_node]
                for owner in owners:
                    for candidate in candidates:
                        if candidate not in owner['resources']:
                            owner['resources'].append(candidate)
                        static_code.append({'source': script, 'target': candidate, 'line': script_text[:function_match.start()].count('\n') + 1,
                                            'kind': 'asset-reference', 'classification': 'dynamic-candidate',
                                            'evidence_level': 'possible', 'evidence': f'{function_name} candidate resolved to scene display node',
                                            'owner_scene': scene_path, 'owner_node': owner.get('name')})
        if scripts:
            scene['description'] = (f"Godot {scene.get('nodes', [{}])[0].get('type', 'scene')} scene with "
                                    f"{len(scene.get('nodes', []))} nodes; scripts: {', '.join(scripts)}")

        # A compact fallback for scripts whose portrait-candidate method is
        # declared elsewhere or has no literal body in the scanned source.
        for script in scripts:
            text = normalized.get(script, '')
            match = re.search(r'DefaultPlayerPortraitId\s*=\s*"([^"]+)"', text)
            candidate = f'Game.Godot/Assets/Textures/Combat/Player/{match.group(1)}.png' if match else ''
            portrait = next((node for node in scene.get('nodes', []) if node.get('name') == 'PlayerPortrait'), None)
            if portrait and candidate in known_paths and candidate not in portrait['resources']:
                portrait['resources'].append(candidate)
                static_code.append({'source': script, 'target': candidate, 'line': 1,
                                    'kind': 'asset-reference', 'classification': 'dynamic-candidate',
                                    'evidence_level': 'possible', 'evidence': 'default character id expands to a PlayerPortrait texture candidate',
                                    'owner_scene': scene_path, 'owner_node': 'PlayerPortrait'})

    # Bridge event-driven UI navigation: a scene script publishes an event,
    # while a controller script handles that event and references destination
    # scenes. This is intentionally conservative and only uses literal strings.
    event_constants = {}
    for text in normalized.values():
        for match in re.finditer(r'\bconst\s+string\s+(\w+)\s*=\s*["\']([^"\']+)["\']', text):
            event_constants[match.group(1)] = match.group(2)
    event_publishers = {}
    for script_path, text in normalized.items():
        if not script_path.lower().endswith(('.gd', '.cs')):
            continue
        for match in re.finditer(r'(?:Publish|PublishSimple)\s*\(\s*["\']([^"\']+)', text):
            event_publishers.setdefault(match.group(1), set()).add(script_path)
        for match in re.finditer(r'(?:Publish|PublishSimple)\s*\(\s*EventTypes\.(\w+)', text):
            event = event_constants.get(match.group(1))
            if event:
                event_publishers.setdefault(event, set()).add(script_path)
    event_handlers = {}
    for script_path, text in normalized.items():
        if not script_path.lower().endswith(('.gd', '.cs')):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = re.search(r'(?:if|elif|else\s+if)\s+[^\n]*["\']([^"\']+)["\']', line)
            if not match or match.group(1) not in event_publishers:
                continue
            event = match.group(1)
            indent = len(line) - len(line.lstrip())
            end = len(lines)
            for cursor in range(index + 1, len(lines)):
                candidate = lines[cursor]
                if (re.match(r'\s*(?:elif|else\s+if|else)\b', candidate)
                        and len(candidate) - len(candidate.lstrip()) == indent):
                    end = cursor
                    break
                if candidate.strip() and len(candidate) - len(candidate.lstrip()) < indent:
                    end = cursor
                    break
            event_handlers.setdefault(event, []).append((script_path, set(range(index + 1, end + 1))))
    scene_constants = {}
    for script_path, text in normalized.items():
        if not script_path.lower().endswith(('.gd', '.cs')):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            match = re.search(r'\b([A-Z][A-Z0-9_]*)\b[^"\']*["\']res://([^"\']+\.tscn)["\']', line)
            if match:
                scene_constants[(script_path, match.group(1))] = (_clean(match.group(2)), line_no)
    # A scene constant becomes an effective route only when it is passed to an
    # explicit switch/instantiation call; its declaration alone remains possible.
    for (script_path, constant), (target, declaration_line) in scene_constants.items():
        for line_no, line in enumerate(normalized[script_path].splitlines(), 1):
            if line_no == declaration_line:
                continue
            if re.search(r'\b(?:change_scene(?:_to_file|_to_packed)?|_?switch_to|instantiate)\s*\([^\n]*\b' + re.escape(constant) + r'\b', line):
                static_code.append({'source': script_path, 'target': target, 'line': line_no,
                                    'classification': 'static-reference',
                                    'evidence_level': 'effective',
                                    'evidence': 'scene constant passed to explicit route call'})
    effective_scene_targets = {
        (item['source'], item['target']) for item in static_code
        if item.get('evidence_level') == 'effective' and item['target'].lower().endswith(SCENE_SUFFIX)
    }
    static_code = [item for item in static_code if not (
        item.get('evidence_level') == 'possible'
        and item['target'].lower().endswith(SCENE_SUFFIX)
        and (item['source'], item['target']) in effective_scene_targets
    )]
    function_bodies = {
        path: _gd_function_bodies(text) for path, text in normalized.items()
        if path.lower().endswith('.gd')
    }
    def controller_targets(script_path: str, method: str, visited: set[str] | None = None) -> set[str]:
        visited = visited or set()
        if method in visited:
            return set()
        body = function_bodies.get(script_path, {}).get(method, '')
        if not body:
            return set()
        next_visited = visited | {method}
        targets = {target for (source, constant), (target, _) in scene_constants.items()
                   if source == script_path and re.search(r'\breturn\s+' + re.escape(constant) + r'\b', body)}
        targets.update(_clean(match.group(1)) for match in _PATH.finditer(body))
        for called in re.findall(r'\b([A-Za-z_]\w*)\s*\(', body):
            if called in function_bodies.get(script_path, {}):
                targets.update(controller_targets(script_path, called, next_visited))
        return targets
    controller_methods = {
        method: script_path for script_path, methods in function_bodies.items() for method in methods
    }
    controller_links = []
    for scene_path, scene in parsed.items():
        scripts = {value for value in scene.get('external_resources', {}).values()
                   if value.lower().endswith(('.gd', '.cs'))}
        for script_path in scripts:
            text = normalized.get(script_path, '')
            for call in re.finditer(r'\b(?:call|Call|call_deferred)\s*\(\s*["\']([A-Za-z_]\w*)', text):
                controller = controller_methods.get(call.group(1))
                if not controller or controller == script_path:
                    continue
                for target in controller_targets(controller, call.group(1)):
                    if target.lower().endswith(SCENE_SUFFIX):
                        controller_links.append({'source': scene_path, 'target': target,
                                                 'line': text[:call.start()].count('\n') + 1,
                                                 'kind': 'controller-route',
                                                 'handler': f'{controller}:{call.group(1)}',
                                                 'evidence_level': 'effective',
                                                 'evidence': 'scene script calls controller route method'})
    event_links = []
    event_handler_locations = {
        (handler, line_no)
        for handlers in event_handlers.values()
        for handler, handler_lines in handlers
        for line_no in handler_lines
    }
    for scene_path, scene in parsed.items():
        attached = {value for value in scene.get('external_resources', {}).values()
                    if value.lower().endswith(('.gd', '.cs'))}
        for event, publishers in event_publishers.items():
            if not attached.intersection(publishers):
                continue
            for handler, handler_lines in event_handlers.get(event, ()):
                for reference in static_code:
                    if (reference['source'] == handler and reference['line'] in handler_lines
                            and reference['target'].lower().endswith(SCENE_SUFFIX)):
                        event_links.append({'source': scene_path, 'target': reference['target'],
                                            'line': reference['line'], 'kind': 'event-route',
                                            'event': event, 'handler': handler,
                                            'evidence_level': 'effective',
                                            'evidence': 'event handler contains explicit scene route'})
                for line_no in handler_lines:
                    if line_no > len(normalized[handler].splitlines()):
                        continue
                    line = normalized[handler].splitlines()[line_no - 1]
                    for constant in re.findall(r'\b[A-Z][A-Z0-9_]*\b', line):
                        target = scene_constants.get((handler, constant))
                        if target:
                            event_links.append({'source': scene_path, 'target': target[0],
                                                'line': target[1], 'kind': 'event-route',
                                                'event': event, 'handler': handler,
                                                'evidence_level': 'effective',
                                                'evidence': 'event handler resolves scene constant'})

    adjacency = {}
    for edge in edges + [{'source': x['source'], 'target': x['target'], 'kind': 'code-reference', 'line': x['line'],
                          'evidence_level': x.get('evidence_level', 'possible')} for x in static_code
                         if x.get('evidence_level', 'possible') == 'effective']:
        adjacency.setdefault(edge['source'], []).append(edge)
    # A script attached to a reachable scene is part of that scene's execution
    # surface; follow its static scene references from the scene as well.
    for scene_path, scene in parsed.items():
        for script_path in scene.get('external_resources', {}).values():
            if not script_path.lower().endswith(('.gd', '.cs')):
                continue
            for reference in static_code:
                if reference['source'] == script_path and reference.get('evidence_level', 'possible') == 'effective':
                    adjacency.setdefault(scene_path, []).append({
                        **reference, 'kind': 'script-reference'})
    for edge in event_links:
        adjacency.setdefault(edge['source'], []).append(edge)
    for edge in controller_links:
        adjacency.setdefault(edge['source'], []).append(edge)
    scene_edges = list(edges) + event_links + controller_links
    for scene_path, scene in parsed.items():
        scripts = {value for value in scene.get('external_resources', {}).values()
                   if value.lower().endswith(('.gd', '.cs'))}
        for reference in static_code:
            if (reference['source'] in scripts and reference['target'].lower().endswith(SCENE_SUFFIX)
                    and reference['target'] != scene_path
                    and (reference['source'], reference['line']) not in event_handler_locations):
                scene_edges.append({**reference, 'source': scene_path, 'kind': 'script-reference'})
    scene_edges.extend(edge for edge in controller_links if edge.get('source') != edge.get('target'))
    # Collapse duplicate source-target rows: effective trigger evidence takes
    # precedence over a weaker literal declaration for the same relation.
    deduplicated_edges = {}
    for edge in scene_edges:
        key = (edge.get('source'), edge.get('target'), edge.get('kind'), edge.get('event'))
        existing = deduplicated_edges.get(key)
        if existing is None or (edge.get('evidence_level') == 'effective'
                                and existing.get('evidence_level') != 'effective'):
            deduplicated_edges[key] = edge
    scene_edges = list(deduplicated_edges.values())
    reachable, queue = set(), deque()
    if main in scenes:
        reachable.add(main); queue.append(main)
    while queue:
        source = queue.popleft()
        for edge in adjacency.get(source, []):
            target = edge['target']
            if target in scenes and target not in reachable:
                reachable.add(target); queue.append(target)

    # Detect cycles with recursion-stack coloring; previously processed sibling
    # nodes are not cycles (for example, B -> A after Main -> A and Main -> B).
    colors = {}
    def visit(source: str) -> None:
        colors[source] = 1
        for edge in adjacency.get(source, []):
            target = edge['target']
            if target not in scenes or target not in reachable:
                continue
            if colors.get(target) == 1:
                diagnostics.append({'kind': 'cycle', 'source': source, 'target': target, 'line': edge.get('line')})
            elif colors.get(target, 0) == 0:
                visit(target)
        colors[source] = 2
    if main in reachable:
        visit(main)

    nodes = {}
    for path, data in parsed.items():
        classification = 'confirmed-reachable' if path in reachable else 'unreachable-candidate'
        item = {**data, 'classification': classification}
        nodes[path] = item
    for detail in task_details or []:
        task = detail.get('task', {})
        for binding in detail.get('godot', {}).get('scenes', []):
            scene = nodes.get(binding.get('scene'))
            if scene is not None:
                scene.setdefault('knowledge_context', []).append({
                    'task_id': task.get('id'), 'title': task.get('title'),
                    'status': task.get('status'), 'witness': binding.get('witness'),
                    'level': 'verified', 'evidence': binding.get('kind'),
                })
        for candidate in detail.get('godot', {}).get('candidates', []):
            scene = nodes.get(candidate.get('scene'))
            if scene is not None:
                scene.setdefault('knowledge_context', []).append({
                    'task_id': task.get('id'), 'title': task.get('title'),
                    'status': task.get('status'), 'level': 'candidate',
                    'evidence': candidate.get('kind'), 'source': candidate.get('evidence'),
                })
    for scene in nodes.values():
        context = scene.get('knowledge_context', [])
        deduplicated = {}
        for item in context:
            key = item.get('task_id')
            existing = deduplicated.get(key)
            if existing is None or item.get('level') == 'verified':
                deduplicated[key] = item
        if deduplicated:
            scene['knowledge_context'] = sorted(
                deduplicated.values(), key=lambda item: (item.get('level') != 'verified', item.get('task_id', 0)))
    # Scripts inherit a scene link only when they are directly attached to that
    # scene.  The relation remains explicit about its evidence level.
    script_tasks = {}
    for scene_path, scene in nodes.items():
        for script in scene.get('functional_summary', {}).get('scripts', []):
            for task_link in scene.get('knowledge_context', []):
                script_tasks.setdefault(script, []).append({
                    'task_id': task_link.get('task_id'), 'title': task_link.get('title'),
                    'level': task_link.get('level'), 'relation': 'scene-inherited',
                    'scene': scene_path, 'evidence': task_link.get('evidence'),
                })
    for script, links in script_tasks.items():
        unique = {}
        for link in links:
            existing = unique.get(link['task_id'])
            if existing is None or link['level'] == 'verified': unique[link['task_id']] = link
        script_tasks[script] = sorted(unique.values(), key=lambda link: (link['level'] != 'verified', link['task_id']))
    for item in dynamic_code:
        diagnostics.append({'kind': 'dynamic-reference', **item})
    return {'schema_version': 'newrouge.godot-scene-graph.v1', 'main_scene': main,
            'nodes': nodes, 'edges': scene_edges,
            'code_references': static_code + dynamic_code + event_links,
            'script_task_context': script_tasks,
            'diagnostics': diagnostics}
