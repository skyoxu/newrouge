"""Deterministic semantic materials and owner-derived evidence roles.

The full host subject is never rewritten. Historical protocol/rendered carriers
remain mandatory host evidence; historical semantics travel once in this DAG.
This module allocates nothing, reads no filesystem and grants no approval.
"""
import base64
from copy import deepcopy

import _b_route_codec as codec
import _b_route_records as records
from _b_route_record_owners import OWNERS, resolve_owned_ref
import _planning_apply_journal as journal

MATERIALS = 'newrouge.b-route-compensation-review-materials.v1'
ROLES = 'newrouge.b-route-compensation-review-roles.v1'
PRESENTATION = 'newrouge.b-route-compensation-review-presentation.v1'
PACKET = 'newrouge.b-route-compensation-review-packet.v1'
CLAIM = 'complete_semantic_materials_with_owner_verified_host_evidence'
COMP_SUBJECT = 'newrouge.b-route-compensation-review-subject.v2'
OLD_SUBJECT = 'newrouge.b-route-adoption-review-subject.v1'
HOST_ROLES = frozenset({'host:subject', 'host:prompt', 'host:request', 'host:schema',
    'host:execution', 'host:output', 'host:proof', 'host:materials', 'host:roles', 'host:presentation'})
SEMANTIC_ROLES = frozenset({'semantic:formal_record', 'semantic:catalog_graph', 'semantic:task_join',
    'semantic:original_operation', 'semantic:original_target', 'semantic:declared_source',
    'semantic:manifest_source', 'semantic:retained_source'})
TASKS = ('.taskmaster/tasks/tasks.json', '.taskmaster/tasks/tasks_back.json',
         '.taskmaster/tasks/tasks_gameplay.json')


def require(condition, expected, actual, code=codec.ReasonCode.IDENTITY_UNPROVABLE):
    if not condition:
        raise codec.CodecError(codec.Diagnostic(code, codec.Stage.BUNDLE, expected=expected, actual=actual))


def shape(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), list(fields), label, codec.ReasonCode.UNKNOWN_FIELD)


def derive(subject, *, verify_review, checks):
    """Build from complete subjects and a mandatory original-owner verifier.

    verify_review(original_operation) returns that owner's checked subject,
    exact support byte map and roles. A path spelling alone never creates a
    host-only role. Callers cannot supply role overrides.
    """
    require(callable(verify_review), 'original saved-review verifier', 'unavailable')
    require(subject.get('schema_version') == COMP_SUBJECT, COMP_SUBJECT, subject.get('schema_version'))
    frames, states, bodies, observations = {}, {}, {}, []
    semantic_witnesses, semantic_origins = set(), {}

    def visit(value):
        identity = codec.canonical_digest(value)
        require(states.get(identity) != 'active', 'acyclic historical subject graph', identity)
        if identity in frames:
            return identity
        states[identity] = 'active'
        version = value.get('schema_version')
        require(version in (COMP_SUBJECT, OLD_SUBJECT), 'known original subject owner/version', version)
        frame = {'subject_digest': identity, 'operation_id': value['operation_id'],
            'subject_schema': version, 'semantic_fields': {key: deepcopy(item) for key, item in value.items()
                if key != 'current_files'}, 'previous_subject': None, 'files': []}
        if version == OLD_SUBJECT:
            # v1's native content, protection, Task definitions, before bytes,
            # explicit authority text/raw and all other original fields remain.
            frames[identity] = frame
            states[identity] = 'complete'
            return identity
        shape(value, ('schema_version', 'producer', 'operation_id', 'request', 'preview', 'policy_identity',
            'original_operation', 'original_effects', 'current_files', 'task_definitions',
            'native_threads', 'native_turns'), 'complete compensation subject')
        require(type(value['current_files']) is dict, 'complete current-file map', identity)
        raw, assigned, provenance, aliases = {}, {}, {}, set()
        for name, encoded in value['current_files'].items():
            codec.validate_reference_path(name)
            require(name.casefold() not in aliases, 'unaliased current-file names', name)
            aliases.add(name.casefold())
            require(type(encoded) is str, 'original base64 bytes', name)
            try:
                raw[name] = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                require(False, 'intact original file bytes', name)
            assigned[name] = set()
            provenance[name] = []

        def role(name, tag, *, owner=None, ref=None, source=None):
            require(name in raw, 'complete owner-required original file', name)
            require(tag in HOST_ROLES | SEMANTIC_ROLES, 'known evidence role', tag)
            assigned[name].add(tag)
            use = {'role': tag, 'owner': owner or tag, 'ref': ref or name,
                   'source': source or name, 'subject_digest': identity}
            if use not in provenance[name]:
                provenance[name].append(use)
            if tag in SEMANTIC_ROLES:
                witness = (name, codec.raw_digest(raw[name]))
                semantic_witnesses.add(witness)
                origins = semantic_origins.setdefault(witness, [])
                if use not in origins:
                    origins.append(use)

        original = value['original_operation']
        require(value['original_effects'] == original['frozen']['targets']
                and value['request']['compensates']['operation_id'] == original['operation_id'],
                'exact original effects and operation relation', value['operation_id'])
        saved = verify_review(original)
        shape(saved, ('subject', 'files', 'roles'), 'original owner result')
        require(set(saved['files']) == set(saved['roles']), 'complete original owner support roles', original['operation_id'])
        for name, data in saved['files'].items():
            require(name in raw and raw[name] == data, 'exact original owner-verified support bytes', name)
            role(name, saved['roles'][name], owner=original['schema_version'],
                 ref=original['frozen']['request']['host_review_ref']['path'], source=name)
        frame['previous_subject'] = visit(saved['subject'])
        operation_path = journal._operation_ref(original['operation_id'])
        require(operation_path in raw and codec.strict_json_loads(raw[operation_path]) == original,
                'complete original raw operation', operation_path)
        role(operation_path, 'semantic:original_operation', owner=original['schema_version'])

        # Registered formal schema/path adapters establish observed record
        # roles. They do not claim every observed immutable row was published.
        formal = {}
        for name, data in raw.items():
            if not data.lstrip().startswith(b'{'):
                continue
            try:
                document = codec.strict_json_loads(data)
            except codec.CodecError:
                continue
            if type(document) is dict and document.get('schema_version') in codec.SCHEMA_IDENTITY_REGISTRY:
                checked = records.validate_record(data, path=name)
                if not checked.ok:
                    raise codec.CodecError(checked.diagnostic)
                formal[name] = document
                role(name, 'semantic:formal_record', owner=document['schema_version'])
        require(records.CATALOG_PATH in formal, 'actual catalog root in complete subject', identity)
        bundle = records._Bundle(raw, None, records.CATALOG_PATH, None, None)
        bundle.load(records.CATALOG_PATH)
        bundle.expand()
        for name in bundle.records:
            role(name, 'semantic:catalog_graph', owner='records.TypedReference', ref=records.CATALOG_PATH)
        for target in original['frozen']['targets']:
            name = target['path']
            if name in raw:
                require(codec.raw_digest(raw[name]) in (target['before_raw_digest'], target['after_raw_digest'])
                        or name in formal, 'known original target image or validated later formal revision', name)
                role(name, 'semantic:original_target', owner=original['schema_version'], ref=operation_path)
        if value['preview']['allocations']['task_definitions'] or any(name in raw for name in TASKS):
            require(all(name in raw for name in TASKS), 'complete current Task join triplet', identity)
            join = records.TaskJoinContext(*(codec.strict_json_loads(raw[name]) for name in TASKS))
            master, _ = join.indexes()
            require(all(int(key) in master for key in value['preview']['allocations']['task_definitions']),
                    'actual affected Task identities', identity)
            for name in TASKS:
                role(name, 'semantic:task_join', owner='records.TaskJoinContext')

        def read(name):
            require(name in raw, 'complete declared semantic source', name)
            return raw[name]

        def contracts():
            return {name: data for name, data in raw.items()
                    if name.startswith('Game.Core/Contracts/') and name.endswith('.cs')}

        for record_path, document in formal.items():
            for locator in records._walk(document):
                if set(locator) != {'owner', 'ref', 'files'}:
                    continue
                require(locator['owner'] in OWNERS, 'registered semantic source owner', locator['owner'])
                resolved = resolve_owned_ref(locator, read_bytes=read, contract_sources=contracts)
                for name in resolved:
                    # Semantic use wins even when the same exact path is an
                    # original owner's valid protocol/support artifact.
                    role(name, 'semantic:declared_source', owner=locator['owner'], ref=locator['ref'], source=record_path)
                    if locator['owner'] == 'source_manifest':
                        manifest = codec.strict_json_loads(raw[name])
                        if type(manifest) is dict and type(manifest.get('sources')) is list:
                            for source in manifest['sources']:
                                require(type(source) is dict and type(source.get('path')) is str
                                        and type(source.get('sha256')) is str,
                                        'known source-manifest entry owner', name)
                                source_name, expected = source['path'], source['sha256']
                                expected = expected if expected.startswith('sha256:') else 'sha256:' + expected
                                require(codec.raw_digest(read(source_name)) == expected,
                                        'exact manifest source bytes', source_name)
                                role(source_name, 'semantic:manifest_source', owner='source_manifest', ref=name, source=record_path)
        for name, data in raw.items():
            digest = codec.raw_digest(data)
            if not assigned[name] and (name, digest) in semantic_witnesses:
                role(name, 'semantic:retained_source')
            require(assigned[name], 'owner-derived role for every original current file', name,
                    codec.ReasonCode.UNRESOLVED_REFERENCE)
            entry = {'subject_digest': identity, 'path': name, 'raw_digest': digest,
                'raw_bytes': len(data), 'roles': sorted(assigned[name]), 'document_ref': None,
                'owner_uses': sorted(provenance[name], key=codec.canonical_digest),
                'semantic_frame_ref': frame['previous_subject'] if 'host:subject' in assigned[name] else None}
            observations.append((entry, data))
            frame['files'].append(entry)
        frames[identity] = frame
        states[identity] = 'complete'
        return identity

    root = visit(subject)
    # A semantic role found in any ancestor wins for the same path and exact
    # bytes in every frame. Legitimate historical Task status images remain
    # separate nodes/frames, never merged by path alone.
    for entry, data in observations:
        if (entry['path'], entry['raw_digest']) in semantic_witnesses:
            inherited = semantic_origins[(entry['path'], entry['raw_digest'])]
            entry['roles'] = sorted(set(entry['roles']) | {use['role'] for use in inherited} | {'semantic:retained_source'})
            try:
                text = data.decode('utf-8', errors='strict')
            except UnicodeDecodeError:
                require(False, 'complete UTF-8 semantic source or explicit future adapter', entry['path'])
            node = {'raw_digest': entry['raw_digest'], 'raw_bytes': len(data), 'text': text}
            require(entry['raw_digest'] not in bodies or bodies[entry['raw_digest']] == node,
                    'one exact byte node per identity', entry['path'])
            bodies[entry['raw_digest']] = node
            entry['document_ref'] = entry['raw_digest']
            retained = {'role': 'semantic:retained_source', 'owner': MATERIALS, 'ref': entry['raw_digest'],
                        'source': entry['path'], 'subject_digest': entry['subject_digest']}
            entry['owner_uses'] = sorted({codec.canonical_digest(use): use
                for use in [*entry['owner_uses'], *inherited, retained]}.values(), key=codec.canonical_digest)
    ordered = sorted(frames)
    materials = {'schema_version': MATERIALS, 'full_subject_digest': root,
        'frames': [frames[key] for key in ordered], 'documents': [bodies[key] for key in sorted(bodies)]}
    roles = {'schema_version': ROLES, 'full_subject_digest': root,
        'files': [deepcopy(entry) for entry, _ in sorted(observations, key=lambda pair:
                  (pair[0]['subject_digest'], pair[0]['path']))]}
    presentation = {'schema_version': PRESENTATION, 'claim': CLAIM, 'full_subject_digest': root,
        'materials_digest': codec.canonical_digest(materials), 'roles_digest': codec.canonical_digest(roles),
        'policy_identity': subject['policy_identity'], 'required_checks': sorted(checks)}
    packet = {'schema_version': PACKET, 'presentation': presentation, 'roles': roles, 'materials': materials}
    validate(packet)
    return packet


def validate(packet):
    """Closed auxiliary packet; caller also compares to owner derivation."""
    shape(packet, ('schema_version', 'presentation', 'roles', 'materials'), 'review packet')
    require(packet['schema_version'] == PACKET, PACKET, packet['schema_version'])
    p, roles, material = packet['presentation'], packet['roles'], packet['materials']
    shape(p, ('schema_version', 'claim', 'full_subject_digest', 'materials_digest', 'roles_digest',
              'policy_identity', 'required_checks'), 'presentation')
    shape(roles, ('schema_version', 'full_subject_digest', 'files'), 'roles')
    shape(material, ('schema_version', 'full_subject_digest', 'frames', 'documents'), 'materials')
    require(p['schema_version'] == PRESENTATION and p['claim'] == CLAIM and roles['schema_version'] == ROLES
            and material['schema_version'] == MATERIALS, 'closed material/presentation versions', p['schema_version'])
    require(p['full_subject_digest'] == roles['full_subject_digest'] == material['full_subject_digest']
            and p['materials_digest'] == codec.canonical_digest(material)
            and p['roles_digest'] == codec.canonical_digest(roles), 'complete material and roles identities', p)
    require(p['required_checks'] == sorted(set(p['required_checks'])) and p['required_checks'],
            'complete distinct semantic denominator', p['required_checks'])
    documents = {}
    for node in material['documents']:
        shape(node, ('raw_digest', 'raw_bytes', 'text'), 'semantic document')
        require(type(node['text']) is str and type(node['raw_bytes']) is int
                and node['raw_digest'] not in documents and len(node['text'].encode('utf-8')) == node['raw_bytes']
                and codec.raw_digest(node['text'].encode('utf-8')) == node['raw_digest'], 'exact semantic bytes', node)
        documents[node['raw_digest']] = node
    frames, flattened, used = {}, [], set()
    for frame in material['frames']:
        shape(frame, ('subject_digest', 'operation_id', 'subject_schema', 'semantic_fields', 'previous_subject', 'files'), 'semantic frame')
        require(frame['subject_digest'] not in frames and frame['subject_schema'] in (COMP_SUBJECT, OLD_SUBJECT),
                'unique known semantic frame', frame['subject_digest'])
        frames[frame['subject_digest']] = frame
        paths = set()
        for row in frame['files']:
            shape(row, ('subject_digest', 'path', 'raw_digest', 'raw_bytes', 'roles', 'document_ref', 'semantic_frame_ref', 'owner_uses'), 'file role')
            codec.validate_reference_path(row['path'])
            require(row['subject_digest'] == frame['subject_digest'] and row['path'].casefold() not in paths
                    and row['roles'] == sorted(set(row['roles'])) and row['roles']
                    and set(row['roles']) <= HOST_ROLES | SEMANTIC_ROLES,
                    'complete unaliased known role collection', row['path'])
            paths.add(row['path'].casefold())
            require(type(row['owner_uses']) is list and row['owner_uses'], 'actual owner provenance', row['path'])
            for use in row['owner_uses']:
                shape(use, ('role', 'owner', 'ref', 'source', 'subject_digest'), 'owner provenance')
                require(use['role'] in HOST_ROLES | SEMANTIC_ROLES
                        and all(type(use[name]) is str and use[name] for name in ('owner', 'ref', 'source', 'subject_digest')),
                        'known owner role and exact original reference', row['path'])
            require({use['role'] for use in row['owner_uses']} == set(row['roles']),
                    'complete role/provenance correspondence', row['path'])
            semantic = bool(set(row['roles']) & SEMANTIC_ROLES)
            require(semantic == (row['document_ref'] is not None), 'semantic role takes precedence', row['path'])
            if semantic:
                require(row['document_ref'] in documents and row['document_ref'] == row['raw_digest']
                        and documents[row['document_ref']]['raw_bytes'] == row['raw_bytes'], 'complete semantic node', row['path'])
                used.add(row['document_ref'])
            flattened.append(row)
    require(material['full_subject_digest'] in frames and used == set(documents),
            'one self-contained reachable document collection', material['full_subject_digest'])
    require(all(use['subject_digest'] in frames for row in flattened for use in row['owner_uses']),
            'owner provenance references complete historical frames', 'unknown frame')
    require(sorted(flattened, key=lambda row: (row['subject_digest'], row['path'])) == roles['files'],
            'exact complete roles/frame reverse mapping', 'role mismatch')
    reached, active = set(), set()
    def walk(identity):
        require(identity in frames and identity not in active, 'known acyclic history frame', identity)
        if identity in reached:
            return
        active.add(identity)
        previous = frames[identity]['previous_subject']
        if previous is not None:
            walk(previous)
        for row in frames[identity]['files']:
            require(row['semantic_frame_ref'] is None or row['semantic_frame_ref'] == previous,
                    'original subject semantic frame binding', row['path'])
        active.remove(identity)
        reached.add(identity)
    walk(material['full_subject_digest'])
    require(reached == set(frames), 'no omitted or unrelated history frames', sorted(set(frames) - reached))
    return packet


LEGACY_DELIVERY = 'newrouge.b-route-compensation-review-delivery.v1'
DELIVERY = 'newrouge.b-route-compensation-review-delivery.v2'



TRANSPORT = 'newrouge.b-route-compensation-review-transport.v1'
PLACEHOLDER = 'newrouge.b-route-compensation-json2-placeholder.v1'
VIEW_KIND = 'original-operation-json2-lf.v1'
V2_DELIVERY = DELIVERY
DELIVERY = 'newrouge.b-route-compensation-review-delivery.v3'
TRANSPORT_INSTRUCTION = (
    'The compact body restores schema_version ' + TRANSPORT + '. '
    'packet_core contains the complete original Packet1 except at most one explicit placeholder. '
    'Each original-operation-json2-lf.v1 view names an internal source path and destination path. '
    'The COMPLETE source operation object is printed in packet_core. Restore its original JSON '
    'keys, types, insertion order and every value first. Serialize that complete object as JSON '
    'with ensure_ascii=False, indent=2, default separators, allow_nan=False and exactly one final LF; '
    'replace only the declared placeholder text with that exact string. No source, audit field '
    'or semantic obligation is omitted. Use ALL reconstructed Packet1 materials and history. '
    'The original_packet_ordered_digest is host-checked integrity metadata, not hidden source; '
    'do not compute hashes or reproduce the transport in your answer.'
)


def _live(work, phase, metrics=(), buffers=()):
    """Reserve actual owner-held graphs/raw buffers before the next allocation."""
    import _b_route_compact_literal as compact
    work.spend(8 + 6 * len(metrics) + 3 * len(buffers), phase=phase)
    size = sum(metric[0] for metric in metrics) + sum(buffers)
    nodes = sum(metric[1] for metric in metrics) + len(buffers)
    depth = max((metric[2] for metric in metrics), default=1)
    compact._metric(size, nodes, depth, phase=phase)
    return size, nodes, depth


def _ordered(value, work, metrics=(), buffers=(), phase='transport.ordered'):
    import json
    import _b_route_compact_literal as compact
    measured = compact._json_preflight(value, work)
    _live(work, phase, (*metrics, measured), (*buffers, measured[5]))
    work.spend(measured[5], phase=phase)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), measured


def _ordered_digest(text, bound, work, metrics=(), buffers=()):
    # bound is the same action's actual JSON preflight, never a wire len field.
    _live(work, 'transport.digest.utf8', metrics, (*buffers, bound, bound))
    work.spend(len(text) + bound, phase='transport.digest.utf8')
    raw = text.encode('utf-8', errors='strict')
    work.spend(len(raw) + 8, phase='transport.digest.hash')
    return codec.raw_digest(raw)


def _json2(source, work, metrics=(), buffers=()):
    """Bound the real source graph before formatting or allocating UTF-8."""
    import json
    import _b_route_compact_literal as compact
    measured = compact._json_preflight(source, work)
    require(type(source) is dict, 'complete original operation object', type(source).__name__)
    work.spend(12, phase='transport.json2.bound')
    bound = measured[5] + 4 * measured[1] * (measured[2] + 1) + 1
    # A JSON text is itself a restored string; include its escaped logical
    # bound, two transient formatter strings and a UTF-8 buffer concurrently.
    _live(work, 'transport.json2.allocate', (*metrics, measured), (*buffers, 6 * bound + 2, 3 * bound))
    work.spend(3 * bound + measured[1] + 8, phase='transport.json2.format')
    text = json.dumps(source, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    work.spend(len(text) + bound, phase='transport.json2.utf8')
    raw = text.encode('utf-8', errors='strict')
    require(len(raw) <= bound, 'source-derived JSON2 allocation bound', len(raw))
    return text, raw, bound


def _json2_equals(source, target, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    require(type(target) is str, 'complete original document text', type(target).__name__)
    target_bytes = compact._utf8_size(target, work)
    text, raw, bound = _json2(source, work, metrics, (*buffers, target_bytes))
    _live(work, 'transport.json2.compare', metrics, (*buffers, 6 * bound + 2, len(raw), target_bytes))
    work.spend(len(target) + target_bytes, phase='transport.json2.target_utf8')
    original = target.encode('utf-8', errors='strict')
    work.spend(len(raw) + len(original) + 8, phase='transport.json2.compare')
    return raw == original


def _source_relations(packet, work):
    """Owner-derived fixed internal pairs; a digest only locates the raw node."""
    import _b_route_compact_literal as compact
    require(type(packet) is dict and packet.get('schema_version') == PACKET, PACKET, 'transport core')
    material = packet.get('materials')
    require(type(material) is dict, 'complete material object', type(material).__name__)
    frames, documents = material.get('frames'), material.get('documents')
    require(type(frames) is list and type(documents) is list, 'complete frame/document arrays', 'missing arrays')
    work.spend(16 + 8 * len(documents) + 8 * len(frames), phase='transport.relations.metadata')
    by_digest, pairs, seen = {}, [], set()
    for index, document in enumerate(documents):
        require(type(document) is dict, 'complete document node', index)
        identity = document.get('raw_digest')
        require(type(identity) is str and len(identity) == 71, 'complete raw digest', identity)
        work.spend(4 * len(identity) + 16, phase='transport.relations.digest')
        require(compact._FULL_SHA256.fullmatch(identity) is not None and identity not in by_digest,
                'unique complete raw document identity', identity)
        by_digest[identity] = (index, document)
    for index, frame in enumerate(frames):
        work.spend(16, phase='transport.relations.frame')
        if type(frame) is not dict or frame.get('subject_schema') != COMP_SUBJECT:
            continue
        fields = frame.get('semantic_fields')
        if type(fields) is not dict:
            continue
        operation, request = fields.get('original_operation'), fields.get('request')
        if type(operation) is not dict or type(request) is not dict:
            continue
        relation = request.get('compensates')
        if type(relation) is not dict or relation.get('operation_id') != operation.get('operation_id'):
            continue
        version, operation_id = operation.get('schema_version'), operation.get('operation_id')
        if version not in ('newrouge.b-route-adoption-operation.v1', 'newrouge.b-route-compensation-operation.v2'):
            continue
        require(type(operation_id) is str, 'original operation ID', operation_id)
        work.spend(4 * len(operation_id) + 64, phase='transport.relations.operation_path')
        path = journal._operation_ref(operation_id)
        entries = frame.get('files')
        require(type(entries) is list, 'complete owner file entries', index)
        work.spend(8 * len(entries), phase='transport.relations.files')
        for entry in entries:
            work.spend(4 * len(path) + 256, phase='transport.relations.owner')
            if (type(entry) is not dict or entry.get('path') != path
                    or type(entry.get('roles')) is not list):
                continue
            work.spend(8 * len(entry['roles']) + 8, phase='transport.relations.roles')
            if 'semantic:original_operation' not in entry['roles']:
                continue
            uses = entry.get('owner_uses')
            require(type(uses) is list, 'complete original-owner provenance', path)
            legitimate = False
            for use in uses:
                work.spend(4 * len(path) + 256, phase='transport.relations.provenance')
                if (type(use) is dict and use.get('role') == 'semantic:original_operation'
                        and use.get('owner') == version and use.get('ref') == path and use.get('source') == path
                        and use.get('subject_digest') == frame.get('subject_digest')):
                    legitimate = True
            identity = entry.get('document_ref')
            require(type(identity) is str and len(identity) == 71, 'original document reference', identity)
            work.spend(2 * len(identity) + 16, phase='transport.relations.lookup')
            if not legitimate or identity not in by_digest or entry.get('raw_digest') != identity:
                continue
            document_index, document = by_digest[identity]
            require(entry.get('raw_bytes') == document.get('raw_bytes'), 'same exact owned document', path)
            key = (index, document_index)
            work.spend(16, phase='transport.relations.pair')
            require(key not in seen, 'one original owner relation per source/destination', key)
            seen.add(key)
            pairs.append((index, document_index, operation, document))
    return pairs


def _view_row(frame_index, document_index, work):
    work.spend(128, phase='transport.view.metadata')
    return {'kind': VIEW_KIND,
        'source': ['materials', 'frames', frame_index, 'semantic_fields', 'original_operation'],
        'destination': ['materials', 'documents', document_index, 'text']}


def _select_view(packet, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    pairs = _source_relations(packet, work)
    work.spend(8 + 6 * len(pairs) * (len(pairs).bit_length() + 1), phase='transport.view.order')
    ranked = []
    for frame_index, document_index, source, document in pairs:
        text = document.get('text')
        require(type(text) is str, 'original text before view derivation', document_index)
        size = compact._utf8_size(text, work)
        work.spend(8, phase='transport.view.rank')
        ranked.append((-size, frame_index, document_index, source, text))
    ranked.sort(key=lambda row: row[:3])
    for _size, frame_index, document_index, source, text in ranked:
        if _json2_equals(source, text, work, metrics, buffers):
            return [_view_row(frame_index, document_index, work)]
    return []


def _shell(value, work):
    # Prepay the metadata sum itself, then the actual dictionary copy/hash work.
    work.spend(6 * len(value) + 4, phase='transport.shell.metadata')
    work.spend(sum(2 * len(key) + 1 for key in value) + len(value) + 8, phase='transport.shell.copy')
    return dict(value)


def _core_with_text(packet, document_index, text, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    measured = compact._json_preflight(packet, work)
    # Two logical graphs are conservative for the four copy-on-write shells.
    _live(work, 'transport.core.shells', (*metrics, measured, measured), (*buffers, 4096))
    core = _shell(packet, work)
    material = _shell(packet['materials'], work)
    documents = packet['materials']['documents']
    work.spend(len(documents) + 8, phase='transport.core.documents')
    copied = list(documents)
    document = _shell(documents[document_index], work)
    document['text'] = text
    copied[document_index] = document
    material['documents'] = copied
    core['materials'] = material
    return core


def _transport_envelope(packet, digest, work, metrics=(), buffers=()):
    views = _select_view(packet, work, metrics, buffers)
    if views:
        placeholder = {'schema_version': PLACEHOLDER, 'view': 0}
        core = _core_with_text(packet, views[0]['destination'][2], placeholder, work, metrics, buffers)
    else:
        core = packet
    _live(work, 'transport.envelope.metadata', metrics, (*buffers, 4096))
    work.spend(256, phase='transport.envelope.metadata')
    return {'schema_version': TRANSPORT, 'original_packet_ordered_digest': digest,
            'packet_core': core, 'views': views}


def _transport_shape(envelope, work):
    import _b_route_compact_literal as compact
    work.spend(128, phase='transport.shape')
    require(type(envelope) is dict and tuple(envelope) ==
            ('schema_version', 'original_packet_ordered_digest', 'packet_core', 'views'),
            'closed ordered transport fields', 'unknown/missing/reordered fields')
    require(envelope['schema_version'] == TRANSPORT, TRANSPORT, envelope['schema_version'])
    digest = envelope['original_packet_ordered_digest']
    require(type(digest) is str and len(digest) == 71, 'complete ordered packet digest', digest)
    work.spend(2 * len(digest) + 8, phase='transport.shape.digest')
    require(compact._FULL_SHA256.fullmatch(digest) is not None, 'complete ordered packet digest', digest)
    core, views = envelope['packet_core'], envelope['views']
    require(type(core) is dict and type(views) is list and len(views) <= 1,
            'one complete core and zero/one views', 'invalid cardinality')
    shape(core, ('schema_version', 'presentation', 'roles', 'materials'), 'transport core')
    require(core['schema_version'] == PACKET, PACKET, core['schema_version'])
    for view in views:
        require(type(view) is dict and tuple(view) == ('kind', 'source', 'destination'),
                'closed ordered view fields', 'unknown/missing/reordered fields')
        require(view['kind'] == VIEW_KIND, VIEW_KIND, view['kind'])
        source, destination = view['source'], view['destination']
        require(type(source) is list and len(source) == 5 and source[:2] == ['materials', 'frames']
                and type(source[2]) is int and source[2] >= 0
                and source[3:] == ['semantic_fields', 'original_operation'], 'fixed internal operation path', source)
        require(type(destination) is list and len(destination) == 4 and destination[:2] == ['materials', 'documents']
                and type(destination[2]) is int and destination[2] >= 0 and destination[3] == 'text',
                'fixed internal text destination', destination)
        pairs = _source_relations(core, work)
        work.spend(12 * len(pairs) + 8, phase='transport.shape.relation_filter')
        matches = [(i, j, operation, document) for i, j, operation, document in pairs
                   if (i, j) == (source[2], destination[2])]
        require(len(matches) == 1, 'one exact owner-bound visible source/destination', (source, destination))
        marker = matches[0][3].get('text')
        require(type(marker) is dict and tuple(marker) == ('schema_version', 'view')
                and marker['schema_version'] == PLACEHOLDER and type(marker['view']) is int and marker['view'] == 0,
                'exact versioned placeholder for view zero', marker)
    return core, views


def _restore_transport_data(envelope, work, metrics=(), buffers=()):
    """Restore/validate Packet1; both callers separately prove its ordered identity."""
    import _b_route_compact_literal as compact
    envelope_metric = compact._json_preflight(envelope, work)
    core, views = _transport_shape(envelope, work)
    if views:
        view = views[0]
        i, j = view['source'][2], view['destination'][2]
        source = core['materials']['frames'][i]['semantic_fields']['original_operation']
        text, raw, bound = _json2(source, work, (*metrics, envelope_metric), buffers)
        document = core['materials']['documents'][j]
        require(type(document.get('raw_bytes')) is int and len(raw) == document['raw_bytes'],
                'exact restored document byte count', document.get('raw_bytes'))
        work.spend(len(raw) + 8, phase='transport.restore.raw_digest')
        require(codec.raw_digest(raw) == document.get('raw_digest'), 'exact restored raw document digest', j)
        packet = _core_with_text(core, j, text, work, (*metrics, envelope_metric), (*buffers, len(raw), 6 * bound + 2))
    else:
        packet = core
    validate(packet)
    return packet, envelope_metric


def _read_transport(envelope, work, buffers=()):
    packet, envelope_metric = _restore_transport_data(envelope, work, buffers=buffers)
    ordered, measured = _ordered(packet, work, (envelope_metric,), buffers, 'transport.restore.ordered')
    actual = _ordered_digest(ordered, measured[5], work, (envelope_metric, measured), (*buffers, measured[5]))
    require(actual == envelope['original_packet_ordered_digest'], 'complete ordered original packet digest', actual)
    del ordered
    # The private reconstructed packet has not escaped. Plan derivation is
    # mandatory even after compact's separate complete canonical D/E check.
    expected = _select_view(packet, work, (envelope_metric, measured), buffers)
    require(expected == envelope['views'], 'canonical owner-derived view plan', envelope['views'])
    # Shape has fixed metadata key order/types. Restoration changed only the
    # exact placeholder slot; applying this same canonical plan is its inverse.
    return packet


def _produce_transport_roundtrip(packet, work, buffers=()):
    """One real private snapshot, installed E, full D and all exact comparisons."""
    import json
    import _b_route_compact_literal as compact
    original, measured = _ordered(packet, work, buffers=buffers, phase='transport.snapshot.ordered')
    digest = _ordered_digest(original, measured[5], work, (measured,), (*buffers, measured[5]))
    # Reserve original input, private complete Packet1 and its immutable JSON
    # witness before cloning. No caller len/witness/approved flag is accepted.
    _live(work, 'transport.snapshot.copy', (measured, measured), (*buffers, measured[5]))
    compact._syntax_preflight(original, work, json_only=True)
    work.spend(measured[0] + measured[1], phase='transport.snapshot.copy')
    snapshot = json.loads(original)
    validate(snapshot)
    held = (measured, measured)
    witness_buffers = (*buffers, measured[5])
    envelope = _transport_envelope(snapshot, digest, work, held, witness_buffers)
    envelope_json, envelope_metric = _ordered(envelope, work, held, witness_buffers, 'transport.envelope.ordered')
    # Envelope is made only from this call's private snapshot/COW shells. Its
    # immutable witness and current private graph must both survive E unchanged.
    retained = _live(work, 'transport.atomic.retained', (*held, envelope_metric),
        (*witness_buffers, envelope_metric[5], 2 * compact.MAX_ENCODED_BYTES))
    work.spend(20, phase='transport.atomic.retained_context')
    previous_retained = getattr(work, '_residual_retained', None)
    # Only this real owner's measured live graphs/raw buffers enter the context.
    # No wire length, caller approval or supplied witness authorizes a discount.
    work._residual_retained = retained
    try:
        body = compact._ATOMIC_PRODUCER(envelope, schema=compact.RESIDUAL_SCHEMA, work=work)
    finally:
        work._residual_retained = previous_retained  # Prepaid on every exit.
    require(type(body) is str, 'genuine producer completed a literal', type(body).__name__)
    restored, schema = compact._decode_complete(body, work, retained=retained)
    require(schema == compact.RESIDUAL_SCHEMA, compact.RESIDUAL_SCHEMA, schema)
    actual_buffers = (*witness_buffers, envelope_metric[5], 2 * compact.MAX_ENCODED_BYTES)
    checked_metrics = []
    work.spend(16, phase='transport.atomic.exact_metadata')
    for value in (restored, envelope):
        text, checked = _ordered(value, work, (*held, envelope_metric, *checked_metrics), actual_buffers, 'transport.atomic.exact')
        if not checked_metrics:
            checked_metrics.append(checked)
        work.spend(len(text) + len(envelope_json), phase='transport.atomic.compare')
        require(text == envelope_json, 'complete envelope snapshot/current-input ordered equality', 'changed envelope')
        del text
    # Producer owns this canonical plan and D returned the identical envelope;
    # cold untrusted reads independently rederive it in _read_transport.
    retained_graphs = (*held, envelope_metric, checked_metrics[0])
    output, _ = _restore_transport_data(restored, work, retained_graphs, actual_buffers)
    text, output_metric = _ordered(output, work, retained_graphs, actual_buffers, 'transport.packet.exact')
    work.spend(len(text) + len(original), phase='transport.packet.compare')
    require(text == original, 'complete original Packet1 ordered type-exact equality', 'changed packet')
    del text
    text, _ = _ordered(packet, work, (*retained_graphs, output_metric), actual_buffers, 'transport.packet.current')
    work.spend(len(text) + len(original), phase='transport.packet.compare')
    require(text == original, 'complete original Packet1 current-input exact equality', 'changed packet')
    # The owned envelope's digest is frozen from original, D returned that exact
    # envelope, and output's complete ordered text equals original. This proves
    # its ordered digest as well, without a redundant second full packet hash.
    return body, output, measured


def _cold_transport(body, work, buffers=()):
    """The original full compact D and canonical E, with owner live credits."""
    import _b_route_compact_literal as compact
    retained = _live(work, 'transport.cold.retained', buffers=buffers)
    envelope, schema = compact._decode_complete(body, work, retained=retained)
    require(schema == compact.RESIDUAL_SCHEMA, compact.RESIDUAL_SCHEMA, schema)
    measured = compact._json_preflight(envelope, work)
    canonical_retained = _live(work, 'transport.cold.canonical',
        (measured,), (*buffers, compact.MAX_ENCODED_BYTES))
    work.spend(20, phase='transport.cold.retained_context')
    previous_retained = getattr(work, '_residual_retained', None)
    work._residual_retained = canonical_retained
    try:
        canonical = compact._ATOMIC_PRODUCER(envelope, schema=compact.RESIDUAL_SCHEMA, work=work)
    finally:
        work._residual_retained = previous_retained  # Prepaid on every exit.
    require(type(canonical) is str, 'genuine canonical encoder completed text', type(canonical).__name__)
    work.spend(len(canonical) + len(body), phase='transport.cold.canonical_compare')
    require(canonical == body, 'full canonical compact-v4 transport body', 'noncanonical body')
    return _read_transport(envelope, work, (*buffers, compact.MAX_ENCODED_BYTES))


def read_prompt(prompt, *, work=None):
    """Read explicit v1/v3, v2/v4 or v3/transport.v1/v4; never fall back."""
    import _b_route_compact_literal as compact
    work = compact._work(work)
    try:
        require(type(prompt) is str, 'complete versioned delivery text', type(prompt).__name__)
        prompt_bytes = compact._encoded_preflight(prompt, work)
        work.spend(len(prompt), phase='compensation.delivery.frame_scan')
        boundary = prompt.find('\n')
        require(boundary > 0, 'one delivery header and complete literal body', 'missing boundary')
        _live(work, 'transport.frame.copy', buffers=(2 * prompt_bytes,))
        work.spend(len(prompt), phase='compensation.delivery.frame_copy')
        header, body = prompt[:boundary], prompt[boundary + 1:]
        current = compact._join([DELIVERY, ' '], work)
        previous = compact._join([V2_DELIVERY, ' '], work)
        legacy = compact._join([LEGACY_DELIVERY, ' '], work)
        work.spend(len(current) + len(previous) + len(legacy) + 8)
        transport = False
        if header.startswith(current):
            start, schema, transport = current, compact.RESIDUAL_SCHEMA, True
            end = compact._join([' ', TRANSPORT_INSTRUCTION, ' ', compact.instruction(schema)], work)
        elif header.startswith(previous):
            start, schema = previous, compact.RESIDUAL_SCHEMA
            end = compact._join([' ', compact.instruction(schema)], work)
        elif header.startswith(legacy):
            start, schema = legacy, compact.ATOM_SCHEMA
            end = compact._join([' ', compact.instruction(schema)], work)
        else:
            require(False, 'explicit known delivery version', 'unknown marker')
        work.spend(len(start) + len(end))
        require(header.startswith(start) and header.endswith(end), 'matched delivery and complete versioned decoder', 'mixed header')
        work.spend(len(header))
        instruction = header[len(start):-len(end)]
        work.spend(3 * len(instruction))
        require(instruction and instruction == instruction.strip() and '\r' not in instruction,
                'nonempty canonical one-line owner instruction', 'invalid instruction')
        prefix = compact._join(['{', compact._repr('schema_version', work), ':', compact._repr(schema, work), ','], work)
        work.spend(len(prefix))
        require(body.startswith(prefix), 'exact delivery-selected canonical body', 'unknown or mixed literal version')
        if transport:
            # Header/body together partition the copied prompt. Their combined
            # raw-buffer bound is at most two complete prompt UTF-8 lengths.
            return _cold_transport(body, work, (2 * prompt_bytes,))
        return validate(compact.loads(body, work=work))
    except codec.CodecError:
        raise
    except (ValueError, SyntaxError, RecursionError, UnicodeError) as error:
        require(False, 'complete direct delivery within unchanged codec limits', str(error), codec.ReasonCode.INVALID_ARGUMENT)


def render(instruction, packet, *, work=None):
    """One fixed owner envelope and original account for the complete round trip."""
    import _b_route_compact_literal as compact
    work = compact._work(work)
    try:
        require(type(instruction) is str, 'one-line owner instruction', type(instruction).__name__)
        work.spend(4 * len(instruction))
        require(instruction and instruction == instruction.strip() and '\n' not in instruction and '\r' not in instruction,
                'nonempty canonical one-line owner instruction', 'invalid instruction')
        fixed = (DELIVERY, ' ', ' ', TRANSPORT_INSTRUCTION, ' ', compact.instruction(compact.RESIDUAL_SCHEMA))
        work.spend(len(fixed) + sum(len(part) for part in fixed), phase='transport.header.fixed')
        header_bytes = sum(len(part) for part in fixed) + compact._utf8_size(instruction, work)
        if header_bytes > compact.MAX_ENCODED_BYTES:
            raise ValueError('Compact encoded bytes exceed ' + compact.RESOURCE_POLICY)
        body, restored, original_metric = _produce_transport_roundtrip(packet, work=work, buffers=(2 * header_bytes,))
        # Original Packet1 validation, immutable snapshot equality and current
        # input exact checks completed inside the private genuine E+D adapter.
        del restored
        _live(work, 'transport.render.frame', (original_metric,),
              (2 * header_bytes, 2 * compact.MAX_ENCODED_BYTES))
        header = compact._join([DELIVERY, ' ', instruction, ' ', TRANSPORT_INSTRUCTION, ' ',
                               compact.instruction(compact.RESIDUAL_SCHEMA)], work)
        rendered = compact._join([header, '\n', body], work)
        compact._encoded_preflight(rendered, work)
        return rendered
    except codec.CodecError:
        raise
    except (ValueError, SyntaxError, RecursionError, UnicodeError) as error:
        require(False, 'complete materials within unchanged codec resource limits', str(error), codec.ReasonCode.INVALID_ARGUMENT)


# Explicit new delivery: existing delivery/transport/compact writers above are
# unchanged. These helpers are private to this new producer/consumer lane.
MULTIVIEW_DELIVERY = 'newrouge.b-route-compensation-review-delivery.v4'
MULTIVIEW_TRANSPORT = 'newrouge.b-route-compensation-review-transport.v2'
MULTIVIEW_PLACEHOLDER = 'newrouge.b-route-compensation-json2-placeholder.v2'
MULTIVIEW_INSTRUCTION = (
    'The compact body restores schema_version ' + MULTIVIEW_TRANSPORT + '. '
    'packet_core contains the complete original Packet1 with explicit versioned text placeholders. '
    'Every original-operation-json2-lf.v1 view names one complete printed internal operation source '
    'and one document-text destination; view ordinals bind distinct destinations. Restore ALL '
    'complete source objects, original JSON keys, types, insertion order and every value first. '
    'Serialize each whole source as JSON with ensure_ascii=False, indent=2, default separators, '
    'allow_nan=False and exactly one final LF. Replace only that view ordinal\'s declared '
    'placeholder with the exact resulting text. Sources are inside frames, destinations inside '
    'documents; no view reads another view\'s destination. All raw byte counts/digests, roles, '
    'owners, files, every historical frame and semantic obligation remain present. Use ALL '
    'reconstructed Packet1 materials and history, not summaries. original_packet_ordered_digest '
    'is host-checked integrity metadata, not hidden source. Do not compute hashes or reproduce '
    'the transport in your answer.'
)


def _mv_metadata(work, count, metrics=(), buffers=(), phase='multiview.metadata'):
    """Pre-reserve bounded new refs/maps/rows/COW metadata, not a heap claim."""
    import _b_route_compact_literal as compact
    work.spend(32, phase=phase)
    # Fixed closed row shapes: 8KiB/128 nodes per actual relation exceeds the
    # two rank/map/row sets, two fixed paths, marker and COW document shell.
    extra = compact._metric(8192 * (count + 1), 128 * (count + 1), 8, phase=phase)
    _live(work, phase, (*metrics, extra), buffers)
    return extra


def _mv_relation_reservation(packet, work, metrics=(), buffers=(), phase='multiview.relations.live'):
    """Reserve the full relation index BEFORE the original helper allocates.

    D/F/E are actual current array lengths, never eligible-pair counts or wire
    witnesses. Existing owner metrics already retain the full referenced graph;
    this bound covers new dict/set/list/tuple/int/path and UTF8 metadata only.
    """
    import _b_route_compact_literal as compact
    work.spend(64, phase=phase)
    require(type(packet) is dict and type(packet.get('materials')) is dict,
            'complete actual material graph for relation preflight', 'invalid material')
    material = packet['materials']
    documents, frames = material.get('documents'), material.get('frames')
    require(type(documents) is list and type(frames) is list,
            'actual document/frame arrays for relation preflight', 'invalid arrays')
    entries, operation_chars = 0, 0
    for frame in frames:
        work.spend(64, phase='multiview.relations.dimensions')
        require(type(frame) is dict and type(frame.get('files')) is list,
                'actual frame file array for relation preflight', 'invalid frame/files')
        entries += len(frame['files'])
        fields = frame.get('semantic_fields')
        operation = fields.get('original_operation') if type(fields) is dict else None
        identity = operation.get('operation_id') if type(operation) is dict else None
        if type(identity) is str:
            operation_chars += len(identity)
    count = len(documents) + len(frames) + entries + 1
    work.spend(32, phase='multiview.relations.bound')
    # Per actual D/F/E item: >= digest-key ref, enumerate int, by_digest tuple
    # and dict slot, pair tuple/list ref, seen tuple/set slot, and fixed digest
    # path strings. 8*L conservatively retains all operation-id UTF8 temporaries
    # together although the original helper only uses them sequentially.
    reserved = compact._metric(1024 * count + 8 * operation_chars, 64 * count, 8, phase=phase)
    _live(work, phase, (*metrics, reserved), buffers)
    return reserved


def _mv_select_views(packet, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    relation_metric = _mv_relation_reservation(packet, work, metrics, buffers, 'multiview.plan.relations')
    pairs = _source_relations(packet, work)
    metadata_metric = _mv_metadata(work, len(pairs), (*metrics, relation_metric), buffers, 'multiview.plan.live')
    work.spend(16 + 12 * len(pairs) * (len(pairs).bit_length() + 1), phase='multiview.plan.order')
    ranked = []
    for i, j, source, document in pairs:
        text = document.get('text')
        require(type(text) is str, 'complete original text before view derivation', j)
        size = compact._utf8_size(text, work)
        work.spend(24, phase='multiview.plan.rank')
        ranked.append((-size, i, j, source, text))
    ranked.sort(key=lambda row: row[:3])
    views, destinations = [], set()
    for _size, i, j, source, text in ranked:
        work.spend(24, phase='multiview.plan.destination')
        if j in destinations:
            continue
        if _json2_equals(source, text, work, (*metrics, relation_metric, metadata_metric), buffers):
            views.append(_view_row(i, j, work))
            destinations.add(j)
    return views


def _mv_core_with_texts(packet, replacements, work, metrics=(), buffers=()):
    """One ordered COW batch. Retained new text/marker allocations are prepaid."""
    import _b_route_compact_literal as compact
    measured = compact._json_preflight(packet, work)
    _mv_metadata(work, len(replacements), (*metrics, measured, measured), buffers, 'multiview.core.live')
    work.spend(32 + 24 * len(replacements), phase='multiview.core.replacement_map')
    by_index = {}
    documents = packet['materials']['documents']
    for index, text in replacements:
        require(type(index) is int and 0 <= index < len(documents) and index not in by_index,
                'distinct exact destination index', index)
        by_index[index] = text
    core = _shell(packet, work)
    material = _shell(packet['materials'], work)
    work.spend(len(documents) + 8, phase='multiview.core.documents')
    copied = list(documents)
    for index, text in by_index.items():
        work.spend(16, phase='multiview.core.replace')
        document = _shell(documents[index], work)
        document['text'] = text
        copied[index] = document
    material['documents'] = copied
    core['materials'] = material
    return core


def _mv_transport_envelope(packet, digest, work, metrics=(), buffers=()):
    views = _mv_select_views(packet, work, metrics, buffers)
    _mv_metadata(work, len(views), metrics, buffers, 'multiview.envelope.live')
    replacements = []
    for ordinal, view in enumerate(views):
        work.spend(128, phase='multiview.placeholder')
        marker = {'schema_version': MULTIVIEW_PLACEHOLDER, 'view': ordinal}
        replacements.append((view['destination'][2], marker))
    core = _mv_core_with_texts(packet, replacements, work, metrics,
                               (*buffers, 8192 * (len(views) + 1))) if views else packet
    work.spend(256, phase='multiview.envelope.metadata')
    return {'schema_version': MULTIVIEW_TRANSPORT, 'original_packet_ordered_digest': digest,
            'packet_core': core, 'views': views}


def _mv_transport_shape(envelope, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    work.spend(128, phase='multiview.shape')
    require(type(envelope) is dict and tuple(envelope) ==
            ('schema_version', 'original_packet_ordered_digest', 'packet_core', 'views'),
            'closed ordered multiview transport fields', 'unknown/missing/reordered fields')
    require(envelope['schema_version'] == MULTIVIEW_TRANSPORT,
            MULTIVIEW_TRANSPORT, envelope['schema_version'])
    digest = envelope['original_packet_ordered_digest']
    require(type(digest) is str and len(digest) == 71, 'complete ordered packet digest', digest)
    work.spend(2 * len(digest) + 8, phase='multiview.shape.digest')
    require(compact._FULL_SHA256.fullmatch(digest) is not None, 'complete ordered packet digest', digest)
    core, views = envelope['packet_core'], envelope['views']
    shape(core, ('schema_version', 'presentation', 'roles', 'materials'), 'multiview core')
    require(core['schema_version'] == PACKET, PACKET, core['schema_version'])
    require(type(views) is list and type(core['materials']) is dict
            and type(core['materials'].get('frames')) is list
            and type(core['materials'].get('documents')) is list,
            'complete frame/document arrays and view list', 'invalid shape')
    frames, documents = core['materials']['frames'], core['materials']['documents']
    require(len(views) <= len(frames) and len(views) <= len(documents),
            'bounded distinct original-operation views', len(views))
    relation_metric = _mv_relation_reservation(core, work, metrics, buffers, 'multiview.shape.relations')
    pairs = _source_relations(core, work)
    _mv_metadata(work, len(pairs) + len(views), (*metrics, relation_metric), buffers, 'multiview.shape.live')
    work.spend(32 + 32 * (len(pairs) + len(views)), phase='multiview.shape.index')
    by_pair = {(i, j): (source, document) for i, j, source, document in pairs}
    destinations = set()
    for ordinal, view in enumerate(views):
        work.spend(256, phase='multiview.shape.view')
        require(type(view) is dict and tuple(view) == ('kind', 'source', 'destination'),
                'closed ordered view fields', 'unknown/missing/reordered fields')
        require(view['kind'] == VIEW_KIND, VIEW_KIND, view['kind'])
        source, destination = view['source'], view['destination']
        require(type(source) is list and len(source) == 5 and source[:2] == ['materials', 'frames']
                and type(source[2]) is int and 0 <= source[2] < len(frames)
                and source[3:] == ['semantic_fields', 'original_operation'],
                'fixed internal whole-operation path', source)
        require(type(destination) is list and len(destination) == 4
                and destination[:2] == ['materials', 'documents']
                and type(destination[2]) is int and 0 <= destination[2] < len(documents)
                and destination[3] == 'text' and destination[2] not in destinations,
                'distinct fixed internal text destination', destination)
        pair = (source[2], destination[2])
        require(pair in by_pair, 'same original owner-bound source and document', pair)
        marker = by_pair[pair][1].get('text')
        require(type(marker) is dict and tuple(marker) == ('schema_version', 'view')
                and marker['schema_version'] == MULTIVIEW_PLACEHOLDER
                and type(marker['view']) is int and marker['view'] == ordinal,
                'exact versioned ordinal placeholder', marker)
        destinations.add(destination[2])
    return core, views


def _mv_restore_transport_data(envelope, work, metrics=(), buffers=()):
    import _b_route_compact_literal as compact
    envelope_metric = compact._json_preflight(envelope, work)
    core, views = _mv_transport_shape(envelope, work, (*metrics, envelope_metric), buffers)
    restore_meta = _mv_metadata(work, len(views), (*metrics, envelope_metric), buffers, 'multiview.restore.live')
    replacements, retained_text_bound = [], 0
    for view in views:
        i, j = view['source'][2], view['destination'][2]
        source = core['materials']['frames'][i]['semantic_fields']['original_operation']
        text, raw, bound = _json2(source, work, (*metrics, envelope_metric, restore_meta),
                                 (*buffers, retained_text_bound))
        document = core['materials']['documents'][j]
        require(type(document.get('raw_bytes')) is int and len(raw) == document['raw_bytes'],
                'exact restored document byte count', document.get('raw_bytes'))
        work.spend(len(raw) + 8, phase='multiview.restore.raw_digest')
        require(codec.raw_digest(raw) == document.get('raw_digest'), 'exact restored document raw digest', j)
        work.spend(32, phase='multiview.restore.cache_metadata')
        _live(work, 'multiview.restore.text_cache', (*metrics, envelope_metric, restore_meta),
              (*buffers, retained_text_bound, 6 * bound + 2, len(raw)))
        retained_text_bound += 6 * bound + 2
        replacements.append((j, text))
        del raw
    packet = _mv_core_with_texts(core, replacements, work, (*metrics, envelope_metric, restore_meta),
             (*buffers, retained_text_bound)) if views else core
    validate(packet)
    return packet, envelope_metric


def _mv_read_transport(envelope, work, buffers=()):
    packet, envelope_metric = _mv_restore_transport_data(envelope, work, buffers=buffers)
    ordered, measured = _ordered(packet, work, (envelope_metric,), buffers, 'transport.restore.ordered')
    actual = _ordered_digest(ordered, measured[5], work, (envelope_metric, measured), (*buffers, measured[5]))
    require(actual == envelope['original_packet_ordered_digest'], 'complete ordered original packet digest', actual)
    del ordered
    expected = _mv_select_views(packet, work, (envelope_metric, measured), buffers)
    # Charge the complete nested view-list comparison rather than only length.
    work.spend(512 * (len(expected) + len(envelope['views'])) + 8, phase='multiview.canonical_plan.compare')
    require(expected == envelope['views'], 'complete canonical owner-derived multiview plan', envelope['views'])
    return packet


def _mv_produce_transport_roundtrip(packet, work, buffers=()):
    """One real private snapshot, installed E, full D and all exact comparisons."""
    import json
    import _b_route_compact_literal as compact
    original, measured = _ordered(packet, work, buffers=buffers, phase='transport.snapshot.ordered')
    digest = _ordered_digest(original, measured[5], work, (measured,), (*buffers, measured[5]))
    # Reserve original input, private complete Packet1 and its immutable JSON
    # witness before cloning. No caller len/witness/approved flag is accepted.
    _live(work, 'transport.snapshot.copy', (measured, measured), (*buffers, measured[5]))
    compact._syntax_preflight(original, work, json_only=True)
    work.spend(measured[0] + measured[1], phase='transport.snapshot.copy')
    snapshot = json.loads(original)
    validate(snapshot)
    held = (measured, measured)
    witness_buffers = (*buffers, measured[5])
    envelope = _mv_transport_envelope(snapshot, digest, work, held, witness_buffers)
    envelope_json, envelope_metric = _ordered(envelope, work, held, witness_buffers, 'transport.envelope.ordered')
    # Envelope is made only from this call's private snapshot/COW shells. Its
    # immutable witness and current private graph must both survive E unchanged.
    retained = _live(work, 'transport.atomic.retained', (*held, envelope_metric),
        (*witness_buffers, envelope_metric[5], 2 * compact.MAX_ENCODED_BYTES))
    work.spend(20, phase='transport.atomic.retained_context')
    previous_retained = getattr(work, '_residual_retained', None)
    # Only this real owner's measured live graphs/raw buffers enter the context.
    # No wire length, caller approval or supplied witness authorizes a discount.
    work._residual_retained = retained
    try:
        body = compact._ATOMIC_PRODUCER(envelope, schema=compact.RESIDUAL_SCHEMA, work=work)
    finally:
        work._residual_retained = previous_retained  # Prepaid on every exit.
    require(type(body) is str, 'genuine producer completed a literal', type(body).__name__)
    restored, schema = compact._decode_complete(body, work, retained=retained)
    require(schema == compact.RESIDUAL_SCHEMA, compact.RESIDUAL_SCHEMA, schema)
    actual_buffers = (*witness_buffers, envelope_metric[5], 2 * compact.MAX_ENCODED_BYTES)
    checked_metrics = []
    work.spend(16, phase='transport.atomic.exact_metadata')
    for value in (restored, envelope):
        text, checked = _ordered(value, work, (*held, envelope_metric, *checked_metrics), actual_buffers, 'transport.atomic.exact')
        if not checked_metrics:
            checked_metrics.append(checked)
        work.spend(len(text) + len(envelope_json), phase='transport.atomic.compare')
        require(text == envelope_json, 'complete envelope snapshot/current-input ordered equality', 'changed envelope')
        del text
    # Producer owns this canonical plan and D returned the identical envelope;
    # cold untrusted reads independently rederive it in _read_transport.
    retained_graphs = (*held, envelope_metric, checked_metrics[0])
    output, _ = _mv_restore_transport_data(restored, work, retained_graphs, actual_buffers)
    text, output_metric = _ordered(output, work, retained_graphs, actual_buffers, 'transport.packet.exact')
    work.spend(len(text) + len(original), phase='transport.packet.compare')
    require(text == original, 'complete original Packet1 ordered type-exact equality', 'changed packet')
    del text
    text, _ = _ordered(packet, work, (*retained_graphs, output_metric), actual_buffers, 'transport.packet.current')
    work.spend(len(text) + len(original), phase='transport.packet.compare')
    require(text == original, 'complete original Packet1 current-input exact equality', 'changed packet')
    # The owned envelope's digest is frozen from original, D returned that exact
    # envelope, and output's complete ordered text equals original. This proves
    # its ordered digest as well, without a redundant second full packet hash.
    return body, output, measured


def _mv_cold_transport(body, work, buffers=()):
    """The original full compact D and canonical E, with owner live credits."""
    import _b_route_compact_literal as compact
    retained = _live(work, 'transport.cold.retained', buffers=buffers)
    envelope, schema = compact._decode_complete(body, work, retained=retained)
    require(schema == compact.RESIDUAL_SCHEMA, compact.RESIDUAL_SCHEMA, schema)
    measured = compact._json_preflight(envelope, work)
    canonical_retained = _live(work, 'transport.cold.canonical',
        (measured,), (*buffers, compact.MAX_ENCODED_BYTES))
    work.spend(20, phase='transport.cold.retained_context')
    previous_retained = getattr(work, '_residual_retained', None)
    work._residual_retained = canonical_retained
    try:
        canonical = compact._ATOMIC_PRODUCER(envelope, schema=compact.RESIDUAL_SCHEMA, work=work)
    finally:
        work._residual_retained = previous_retained  # Prepaid on every exit.
    require(type(canonical) is str, 'genuine canonical encoder completed text', type(canonical).__name__)
    work.spend(len(canonical) + len(body), phase='transport.cold.canonical_compare')
    require(canonical == body, 'full canonical compact-v4 transport body', 'noncanonical body')
    return _mv_read_transport(envelope, work, (*buffers, compact.MAX_ENCODED_BYTES))


def render_multi_view(instruction, packet, *, work=None):
    """One fixed owner envelope and original account for the complete round trip."""
    import _b_route_compact_literal as compact
    work = compact._work(work)
    try:
        require(type(instruction) is str, 'one-line owner instruction', type(instruction).__name__)
        work.spend(4 * len(instruction))
        require(instruction and instruction == instruction.strip() and '\n' not in instruction and '\r' not in instruction,
                'nonempty canonical one-line owner instruction', 'invalid instruction')
        fixed = (MULTIVIEW_DELIVERY, ' ', ' ', MULTIVIEW_INSTRUCTION, ' ', compact.instruction(compact.RESIDUAL_SCHEMA))
        work.spend(len(fixed) + sum(len(part) for part in fixed), phase='transport.header.fixed')
        header_bytes = sum(len(part) for part in fixed) + compact._utf8_size(instruction, work)
        if header_bytes > compact.MAX_ENCODED_BYTES:
            raise ValueError('Compact encoded bytes exceed ' + compact.RESOURCE_POLICY)
        body, restored, original_metric = _mv_produce_transport_roundtrip(packet, work=work, buffers=(2 * header_bytes,))
        # Original Packet1 validation, immutable snapshot equality and current
        # input exact checks completed inside the private genuine E+D adapter.
        del restored
        _live(work, 'transport.render.frame', (original_metric,),
              (2 * header_bytes, 2 * compact.MAX_ENCODED_BYTES))
        header = compact._join([MULTIVIEW_DELIVERY, ' ', instruction, ' ', MULTIVIEW_INSTRUCTION, ' ',
                               compact.instruction(compact.RESIDUAL_SCHEMA)], work)
        rendered = compact._join([header, '\n', body], work)
        compact._encoded_preflight(rendered, work)
        return rendered
    except codec.CodecError:
        raise
    except (ValueError, SyntaxError, RecursionError, UnicodeError) as error:
        require(False, 'complete materials within unchanged codec resource limits', str(error), codec.ReasonCode.INVALID_ARGUMENT)


def read_prompt_multi_view(prompt, *, work=None):
    """Explicit new delivery only. Never reinterpret any old header/body."""
    import _b_route_compact_literal as compact
    work = compact._work(work)
    try:
        require(type(prompt) is str, 'complete multiview delivery text', type(prompt).__name__)
        prompt_bytes = compact._encoded_preflight(prompt, work)
        work.spend(len(prompt), phase='compensation.delivery.frame_scan')
        boundary = prompt.find('\n')
        require(boundary > 0, 'one multiview header and complete body', 'missing boundary')
        _live(work, 'transport.frame.copy', buffers=(2 * prompt_bytes,))
        work.spend(len(prompt), phase='compensation.delivery.frame_copy')
        header, body = prompt[:boundary], prompt[boundary + 1:]
        start = compact._join([MULTIVIEW_DELIVERY, ' '], work)
        end = compact._join([' ', MULTIVIEW_INSTRUCTION, ' ', compact.instruction(compact.RESIDUAL_SCHEMA)], work)
        work.spend(len(start) + len(end))
        require(header.startswith(start) and header.endswith(end), 'exact explicit multiview header', 'mixed version')
        work.spend(len(header))
        instruction = header[len(start):-len(end)]
        work.spend(3 * len(instruction))
        require(instruction and instruction == instruction.strip() and '\r' not in instruction,
                'canonical one-line owner instruction', 'invalid instruction')
        prefix = compact._join(['{', compact._repr('schema_version', work), ':',
                                compact._repr(compact.RESIDUAL_SCHEMA, work), ','], work)
        work.spend(len(prefix))
        require(body.startswith(prefix), 'exact unchanged compact-v4 body grammar', 'mixed literal version')
        return _mv_cold_transport(body, work, (2 * prompt_bytes,))
    except codec.CodecError:
        raise
    except (ValueError, SyntaxError, RecursionError, UnicodeError) as error:
        require(False, 'complete multiview materials within unchanged resource limits', str(error),
                codec.ReasonCode.INVALID_ARGUMENT)
