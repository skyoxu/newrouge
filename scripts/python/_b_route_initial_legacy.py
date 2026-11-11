"""Bounded governed Git/owner evidence for initially absent legacy manifests.

This observes one repository, not a machine's unrecorded filesystem history.
All Git calls are local reads. Missing/partial/unsafe evidence is unknown.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import stat

VERSION = 'newrouge.b-route-legacy-manifest-requirement.v3'
MAX_COMMITS = 512
MAX_OBJECTS = 8192
MAX_BYTES = 32 * 1024 * 1024
FORMAL = {'docs/planning/b-route/policy.v1.json': ('newrouge.b-route-policy.v1', 'frozen_a_refs'),
          'docs/planning/b-route/task-origins.v1.json': ('newrouge.b-route-origins.v1', 'frozen_legacy_refs')}
LEGACY_PATHS = ('docs/planning/semantic-topology/capabilities.v1.json',
                'docs/planning/semantic-topology/capability-apply.pending.json')
APPLY_ROOTS = ('logs/ci/capability-planning', 'logs/ci/mvg-planning')
CONTROL_PATHS = ('shallow', 'info/grafts', 'objects/info/alternates', 'commondir')


def _encode(raw):
    return base64.b64encode(raw).decode('ascii')


def _decode(value):
    return base64.b64decode(value, validate=True)


def _manifest(path):
    return path.casefold().startswith('docs/testing/mvg/') and path.casefold().endswith('.json')


def _empty(documents):
    return (type(documents) is dict and set(documents) == {'master', 'back', 'gameplay'}
        and type(documents['master']) is dict and type(documents['master'].get('master')) is dict
        and documents['master']['master'].get('tasks') == []
        and type(documents['master']['master'].get('tasks')) is list
        and documents['back'] == [] and type(documents['back']) is list
        and documents['gameplay'] == [] and type(documents['gameplay']) is list)


def _declaration(value):
    import _b_route_inventory as inventory
    if type(value) is not dict:
        raise ValueError('Complete source-set declaration required')
    if value.get('schema_version') != 'chapter3.source-set.v1':
        raise ValueError('Unknown source-set declaration')
    patterns = value.get('active_patterns')
    if type(patterns) is not list or not patterns or any(type(path) is not str for path in patterns):
        raise ValueError('Complete source-set pattern list required')
    for pattern in patterns:
        inventory.canonical_path(pattern, pattern=True)
        if any(c in pattern.split('/')[0] for c in '*?['):
            raise ValueError('Source patterns require a literal non-log tree prefix')
    sources, retirements = value.get('active_sources'), value.get('retirements', [])
    if type(sources) is not list or type(retirements) is not list:
        raise ValueError('Complete source-set lists required')
    paths = []
    for path in sources:
        inventory.canonical_path(path)
        paths.append(path)
    for row in retirements:
        if type(row) is not dict or type(row.get('path')) is not str:
            raise ValueError('Original retirement object/path required')
        inventory.canonical_path(row['path'])
        paths.append(row['path'])
    return (any(path.casefold().startswith('docs/testing/mvg/') for path in patterns)
            or any(_manifest(path) for path in paths))


def _epics_declaration(raw):
    import _b_route_inventory as inventory
    inputs = inventory.frontmatter(raw).get('inputDocuments')
    if type(inputs) is not list or any(type(path) is not str for path in inputs):
        raise ValueError('Original epics input declaration is malformed')
    for path in inputs:
        inventory.canonical_path(path)
    return any(_manifest(path) for path in inputs)


def _query(root, *args):
    import _b_route_inventory as inventory
    return inventory.git(root, *args)


def _controls(root):
    import _b_route_inventory as inventory
    base = root / '.git'
    for ancestor in reversed((base, *base.parents)):
        inventory.no_reparse(ancestor)
    if not base.is_dir():
        raise ValueError('Ordinary independent Git directory required')
    for name in CONTROL_PATHS:
        path = base.joinpath(*name.split('/'))
        for parent in (path, *path.parents):
            inventory.no_reparse(parent)
        if os.path.lexists(path):
            raise ValueError('Unsupported shallow/graft/alternate/shared Git control: ' + name)
    if _query(root, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('Complete non-shallow history required')
    if _query(root, 'for-each-ref', '--format=%(objectname)', 'refs/replace').strip():
        raise ValueError('Replacement history is unknown')
    return list(CONTROL_PATHS)


class Objects:
    def __init__(self, root=None, saved=None):
        self.root, self.values = root, {} if saved is None else saved
        self.bytes, self.seen = 0, set()
        if (type(self.values) is not dict or any(type(v) is not dict or type(v.get('raw_base64')) is not str
                for v in self.values.values()) or len(self.values) > MAX_OBJECTS
                or sum(len(_decode(v['raw_base64'])) for v in self.values.values()) > MAX_BYTES):
            raise ValueError('Bounded original-object archive required')

    def get(self, kind, oid):
        if type(oid) is not str or re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', oid) is None:
            raise ValueError('Full Git object identity required')
        if oid not in self.values:
            if self.root is None:
                raise ValueError('Missing original Git object')
            raw = _query(self.root, 'cat-file', kind, oid)
            self.values[oid] = {'kind': kind, 'raw_base64': _encode(raw)}
        value = self.values[oid]
        if type(value) is not dict or set(value) != {'kind', 'raw_base64'} or value['kind'] != kind:
            raise ValueError('Exact original Git object kind required')
        raw = _decode(value['raw_base64'])
        algorithm = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
        actual = algorithm(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != oid:
            raise ValueError('Git object raw bytes do not match its identity')
        if oid not in self.seen:
            self.bytes += len(raw)
            self.seen.add(oid)
        if len(self.values) > MAX_OBJECTS or self.bytes > MAX_BYTES:
            raise ValueError('Complete history exceeds bounded original-object observation')
        return raw

    def tree(self, oid):
        raw = self.get('tree', oid)
        width, index, rows = len(oid) // 2, 0, {}
        while index < len(raw):
            end = raw.index(b' ', index)
            mode = raw[index:end].decode('ascii')
            zero = raw.index(b'\0', end + 1)
            name = raw[end+1:zero].decode('utf-8')
            if not name or name in ('.', '..') or '/' in name or name.casefold() in {n.casefold() for n in rows}:
                raise ValueError('Unsafe or duplicate original tree entry')
            index = zero + 1
            identity = raw[index:index+width]
            if len(identity) != width:
                raise ValueError('Truncated Git tree identity')
            index += width
            rows[name] = (mode, identity.hex())
        return rows

    def lookup(self, tree, path):
        parts = path.split('/')
        for index, name in enumerate(parts):
            rows = self.tree(tree)
            if name not in rows:
                if any(key.casefold() == name.casefold() for key in rows):
                    raise ValueError('Case-aliased governed history')
                return None
            mode, oid = rows[name]
            if index == len(parts)-1:
                return mode, oid
            if mode != '40000':
                raise ValueError('Governed history traverses a non-tree')
            tree = oid

    def file(self, tree, path):
        entry = self.lookup(tree, path)
        if entry is None:
            raise ValueError('Missing governed original: ' + path)
        if entry[0] not in ('100644', '100755'):
            raise ValueError('Governed original is not a regular Git blob')
        return self.get('blob', entry[1])

    def manifest_present(self, tree):
        for name, (mode, oid) in self.tree(tree).items():
            if mode == '40000':
                if self.manifest_present(oid):
                    return True
            elif name.casefold().endswith('.json'):
                return True
        return False


def _history(objects, proof, triplet, strict_json):
    graph = proof['parents']
    head = proof['head']
    if type(graph) is not dict or not graph or len(graph) > MAX_COMMITS or head not in graph:
        raise ValueError('Bounded complete reachable ancestry required')
    pending, seen, roots, required = [head], set(), set(), False
    while pending:
        oid = pending.pop()
        if oid in seen:
            continue
        seen.add(oid)
        raw = objects.get('commit', oid)
        headers = raw.split(b'\n\n', 1)[0].splitlines()
        trees = [row[5:].decode('ascii') for row in headers if row.startswith(b'tree ')]
        parents = [row[7:].decode('ascii') for row in headers if row.startswith(b'parent ')]
        if len(trees) != 1 or graph.get(oid) != parents or len(set(parents)) != len(parents):
            raise ValueError('Original commit/tree/parent graph mismatch')
        if not parents:
            roots.add(oid)
        pending.extend(parents)
        documents = {key: strict_json(objects.file(trees[0], path)) for key,path in triplet.items()}
        if not _empty(documents):
            required = True
        source = strict_json(objects.file(trees[0], 'docs/workflows/chapter3-source-set.json'))
        required = _declaration(source) or required
        if objects.lookup(trees[0], proof['epics_path']) is not None:
            required = _epics_declaration(objects.file(trees[0], proof['epics_path'])) or required
        entry = objects.lookup(trees[0], 'docs/testing/mvg')
        if entry is not None:
            if entry[0] != '40000':
                raise ValueError('Original manifest namespace is not a tree')
            required = objects.manifest_present(entry[1]) or required
        required = any(objects.lookup(trees[0], path) is not None for path in LEGACY_PATHS) or required
        for path, (schema, field) in FORMAL.items():
            if objects.lookup(trees[0], path) is not None:
                import _b_route_records as records
                raw = objects.file(trees[0], path)
                if not records.validate_record(raw, path=path).ok:
                    raise ValueError('Invalid original frozen-A owner')
                value = strict_json(raw)
                if value.get('schema_version') != schema or type(value.get(field)) is not list:
                    raise ValueError('Unknown original frozen-A owner')
                required = bool(value[field]) or required
    if seen != set(graph) or len(roots) != 1 or any(anchor not in seen for anchor in proof['anchors']):
        raise ValueError('Incomplete, unrelated or ambiguous governed anchors/history')
    return required


def _index_paths(proof, triplet):
    return (*triplet.values(), 'docs/workflows/chapter3-source-set.json',
            proof['epics_path'], *FORMAL, *LEGACY_PATHS, 'docs/testing/mvg')


def _index(objects, proof, triplet, strict_json):
    import _b_route_records as records
    seen, required = set(), False
    for record in _decode(proof['index_base64']).split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        name = name.decode('utf-8')
        if name in seen or stage != '0' or mode not in ('100644', '100755'):
            raise ValueError('Complete ordinary unmerged-free governed index required')
        seen.add(name)
        if _manifest(name):
            objects.get('blob', oid)
            required = True
        elif name in triplet.values():
            value = strict_json(objects.get('blob', oid))
            rows = value.get('master', {}).get('tasks') if name == triplet['master'] and type(value) is dict else value
            if type(rows) is not list:
                raise ValueError('Original indexed Task container required')
            required = bool(rows) or required
        elif name == 'docs/workflows/chapter3-source-set.json':
            required = _declaration(strict_json(objects.get('blob', oid))) or required
        elif name == proof['epics_path']:
            required = _epics_declaration(objects.get('blob', oid)) or required
        elif name in FORMAL:
            raw = objects.get('blob', oid)
            if not records.validate_record(raw, path=name).ok:
                raise ValueError('Invalid indexed frozen-A owner')
            value, (schema, field) = strict_json(raw), FORMAL[name]
            if value.get('schema_version') != schema or type(value.get(field)) is not list:
                raise ValueError('Unknown indexed frozen-A owner')
            required = bool(value[field]) or required
        elif name in LEGACY_PATHS:
            strict_json(objects.get('blob', oid))
            required = True
        else:
            raise ValueError('Unexpected governed index path')
    if not {*triplet.values(), 'docs/workflows/chapter3-source-set.json'} <= seen:
        raise ValueError('All genuine triplet/source-set originals must remain tracked')
    return required


def _owner_files(root, exclude=None):
    """Only existing fixed inventory/protection owner outputs, never all logs."""
    import _b_route_inventory as inventory
    result = []
    home = inventory.safe_input(root, 'logs/ci', allow_logs=True)
    if not home.exists():
        return result
    for date in sorted(home.iterdir()):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date.name) is None:
            continue
        inventory.no_reparse(date)
        if not date.is_dir():
            raise ValueError('Known owner date namespace is not a directory')
        for owner in ('b-route-baseline-inventory', 'b-route-protection'):
            base = inventory.safe_input(root, date.relative_to(root).as_posix()+'/'+owner, allow_logs=True)
            if not base.exists():
                continue
            if not base.is_dir():
                raise ValueError('Known owner namespace is not a directory')
            for run in sorted(base.iterdir()):
                inventory.no_reparse(run)
                if not run.is_dir():
                    raise ValueError('Unknown owner namespace member')
                if exclude is not None and run.relative_to(root).as_posix() == exclude:
                    continue
                names = {p.name for p in run.iterdir()}
                selected = names & {'inventory.json', 'snapshot.json'}
                # Completed read-only verification output is not an archive or
                # activation of the Task/MVG system. Its creation must not make
                # the very proof it verified permanently unusable.
                verification_only = names <= {'verification.json', 'result.json', 'failure.json'}
                if names and not selected and not verification_only:
                    raise ValueError('Partial known owner capture')
                for name in sorted(selected):
                    result.append((run/name).relative_to(root).as_posix())
    for prefix in APPLY_ROOTS:
        base = inventory.safe_input(root, prefix, allow_logs=True)
        if not base.exists():
            continue
        if not base.is_dir():
            raise ValueError('Known legacy apply namespace is not a directory')
        for run in sorted(base.iterdir()):
            inventory.no_reparse(run)
            if not run.is_dir():
                raise ValueError('Known legacy apply run is not a directory')
            path = inventory.safe_input(root, run.relative_to(root).as_posix()+'/apply-journal.json', allow_logs=True)
            if os.path.lexists(path):
                result.append(path.relative_to(root).as_posix())
    return result


def _owner_scope(value, path, files, root_real, ancestors, strict_json):
    """An unrelated historical/debug record cannot activate this root's legacy."""
    if type(value) is not dict:
        raise ValueError('Known owner record must be an object')
    schema = value.get('schema_version')
    if schema == 'newrouge.planning-apply-journal.v1':
        return 'apply'
    if type(schema) is str and schema.startswith('newrouge.b-route-protection-snapshot.'):
        source = path.rsplit('/', 1)[0]+'/inventory.json'
        if source not in files:
            raise ValueError('Missing original inventory for a prior protection capture')
        value = strict_json(_decode(files[source]))
        if type(value) is not dict:
            raise ValueError('Original owner inventory must be an object')
    git = value.get('git')
    if type(git) is not dict or type(git.get('head')) is not str:
        raise ValueError('Known owner has no attributable Git history')
    if git['head'] not in ancestors:
        return 'unrelated'
    collection = value.get('collection')
    if type(collection) is not dict:
        raise ValueError('Known owner collection metadata must be an object')
    observed_root = collection.get('root_real')
    if type(observed_root) is str and observed_root != root_real:
        return 'unrelated'
    if observed_root != root_real:
        raise ValueError('Same-lineage prior owner has unknown root applicability')
    return 'related'


def _read_original(root, path, read):
    import _b_route_inventory as inventory
    target = inventory.safe_input(root, path, allow_logs=path.startswith('logs/'))
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
        raise ValueError('Single ordinary original file required')
    raw = read(path, 'initial-legacy-owner' if path.startswith('logs/') else 'initial-legacy-boundary',
               evidence=path.startswith('logs/'))
    if raw is None:
        raise ValueError('Required observed original unavailable')
    return raw


def _current(root, read, epics, exclude, ancestors, historical_inventory=None):
    import _b_route_inventory as inventory
    files = {}
    for path in (*inventory.TRIPLET.values(), inventory.SOURCE_SET, epics):
        files[path] = _encode(_read_original(root, path, read))
    header = inventory.frontmatter(_decode(files[epics]))
    source_set = inventory.strict_json(_decode(files[inventory.SOURCE_SET]))
    for path in header['inputDocuments'] + source_set['active_sources']:
        files[path] = _encode(_read_original(root, path, read))
    manifest_dir = inventory.safe_input(root, 'docs/testing/mvg')
    members = []
    if manifest_dir.exists():
        if not manifest_dir.is_dir():
            raise ValueError('Ordinary manifest directory required')
        def unreadable(error):
            raise ValueError('Unreadable manifest namespace') from error
        for parent, directories, names in os.walk(manifest_dir, followlinks=False, onerror=unreadable):
            directories.sort()
            for name in directories + sorted(names):
                path = Path(parent)/name
                inventory.no_reparse(path)
                members.append(path.relative_to(manifest_dir).as_posix()+('/' if name in directories else ''))
        members.sort()
    for path in (*FORMAL, *LEGACY_PATHS):
        target = inventory.safe_input(root, path)
        if target.exists():
            files[path] = _encode(_read_original(root, path, read))
    owner_records = _owner_files(root, exclude)
    if historical_inventory is not None:
        # The existing optional historical operand is observed, not promoted
        # into a current prerequisite. Only attributable owner facts below can
        # affect the initial-absence decision; Task evidence_refs stay optional.
        raw = read(historical_inventory, 'historical-inventory', required=False, evidence=True)
        if raw is not None:
            if historical_inventory not in owner_records:
                owner_records.append(historical_inventory)
            files[historical_inventory] = _encode(raw)
    owner_records.sort()
    for path in owner_records:
        files[path] = _encode(_read_original(root, path, read))
        value = inventory.strict_json(_decode(files[path]))
        scope = _owner_scope(value, path, files, str(root.resolve()), ancestors, inventory.strict_json)
        if path.endswith('/snapshot.json') and scope == 'related':
            snapshot = inventory.strict_json(_decode(files[path]))
            if type(snapshot.get('raw_files')) is not list or any(type(row) is not dict for row in snapshot['raw_files']):
                raise ValueError('Complete prior owner raw index required')
            for row in snapshot['raw_files']:
                if row.get('exists') is not True:
                    continue
                digest = row.get('raw_digest')
                if (type(digest) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is None
                        or row.get('artifact') != 'raw/'+digest[7:]+'.bin'):
                    raise ValueError('Unknown prior owner raw archive')
                support = path.rsplit('/', 1)[0]+'/'+row['artifact']
                raw = _read_original(root, support, read)
                if inventory.digest(raw) != digest:
                    raise ValueError('Changed prior owner raw original')
                files[support] = _encode(raw)
    if len(files) > MAX_OBJECTS or sum(len(_decode(raw)) for raw in files.values()) > MAX_BYTES:
        raise ValueError('Complete current owner archive exceeds bounded observation')
    return {'files': files, 'owner_records': owner_records,
            'manifest_directory_exists': manifest_dir.exists(), 'manifest_members': members}


def _proof_shape(proof):
    keys = {'root_real','head','epics_path','anchors','parents','controls_absent','objects',
            'current','source_members','index_base64'}
    if type(proof) is not dict or set(proof) != keys:
        raise ValueError('Complete versioned original proof structure required')
    if (any(type(proof[k]) is not str for k in ('root_real','head','epics_path','index_base64'))
            or type(proof['parents']) is not dict or type(proof['objects']) is not dict
            or any(type(k) is not str or type(v) is not list or any(type(p) is not str for p in v)
                   for k,v in proof['parents'].items())
            or any(type(proof[k]) is not list or any(type(v) is not str for v in proof[k])
                   for k in ('anchors','controls_absent','source_members'))):
        raise ValueError('Typed Git/root/source proof observations required')
    current = proof['current']
    if (type(current) is not dict or set(current) != {'files','owner_records','manifest_directory_exists','manifest_members'}
            or type(current['files']) is not dict or type(current['manifest_directory_exists']) is not bool
            or any(type(k) is not str or type(v) is not str for k,v in current['files'].items())
            or any(type(current[k]) is not list or any(type(v) is not str for v in current[k])
                   for k in ('owner_records','manifest_members'))
            or len(set(current['owner_records'])) != len(current['owner_records'])
            or not set(current['owner_records']) <= set(current['files'])):
        raise ValueError('Complete typed current boundary observations required')
    if (len(current['files']) > MAX_OBJECTS
            or sum(len(_decode(raw)) for raw in current['files'].values()) > MAX_BYTES):
        raise ValueError('Bounded complete current original archive required')


def _derive(proof, documents, source_set, triplet, strict_json, depth=0):
    import _b_route_inventory as inventory
    _proof_shape(proof)
    if depth > 16:
        raise ValueError('Bounded complete owner ancestry required')
    if not _empty(documents):
        raise ValueError('Complete genuine empty current triplet required')
    if proof['controls_absent'] != list(CONTROL_PATHS):
        raise ValueError('Complete Git control absence observations required')
    if len(proof['anchors']) != 2 or any(type(a) is not str for a in proof['anchors']):
        raise ValueError('Both current declared Git anchors required')
    objects = Objects(saved=proof['objects'])
    required = _history(objects, proof, triplet, strict_json) or _declaration(source_set)
    required = _index(objects, proof, triplet, strict_json) or required
    current = proof['current']
    for key,path in triplet.items():
        if inventory.canonical_sha(strict_json(_decode(current['files'][path]))) != inventory.canonical_sha(documents[key]):
            raise ValueError('Current triplet differs from original boundary bytes')
    if inventory.canonical_sha(strict_json(_decode(current['files']['docs/workflows/chapter3-source-set.json']))) != inventory.canonical_sha(source_set):
        raise ValueError('Current source declaration differs from original bytes')
    required = _epics_declaration(_decode(current['files'][proof['epics_path']])) or required
    required = any(n.casefold().endswith('.json') for n in current['manifest_members']) or required
    required = any(path in current['files'] for path in LEGACY_PATHS) or required
    for path, encoded in current['files'].items():
        value = strict_json(_decode(encoded)) if path.endswith('.json') else None
        if path in FORMAL:
            import _b_route_records as records
            checked = records.validate_record(_decode(encoded), path=path)
            if not checked.ok:
                raise ValueError('Invalid current frozen-A owner')
            schema, field = FORMAL[path]
            if value.get('schema_version') != schema or type(value.get(field)) is not list:
                raise ValueError('Unknown current frozen-A owner')
            required = bool(value[field]) or required
        elif path in current['owner_records']:
            if type(value) is not dict:
                raise ValueError('Unknown original owner record')
            scope = _owner_scope(value, path, current['files'], proof['root_real'], proof['parents'], strict_json)
            if scope == 'unrelated':
                continue
            if scope == 'apply':
                entries = value.get('entries')
                if type(entries) is not list or not entries or any(type(row) is not dict or type(row.get('path')) is not str for row in entries):
                    raise ValueError('Complete known legacy apply targets required')
                if any(_manifest(row['path']) or row['path'] in (*triplet.values(), *LEGACY_PATHS) for row in entries):
                    required = True
                    continue
                raise ValueError('Known legacy apply has unresolved target applicability')
            frozen = value.get('frozen_a', {})
            if type(frozen) is not dict:
                raise ValueError('Typed original frozen-A owner required')
            tasks = value.get('tasks', {})
            if type(tasks) not in (dict, list):
                raise ValueError('Typed original Task owner required')
            counts = tasks.get('counts', {}) if type(tasks) is dict else {}
            if type(counts) is not dict:
                raise ValueError('Typed original Task counts required')
            if (value.get('manifests') or value.get('cumulative')
                    or frozen.get('candidate_count') not in (None, 0)
                    or any(type(n) is int and n > 0 for n in counts.values())):
                required = True
            elif value.get('schema_version') == 'newrouge.b-route-baseline-inventory.v3':
                prior = value.get('legacy_manifest_requirement', {}).get('proof')
                if (type(prior) is not dict or prior.get('root_real') != proof['root_real']
                        or prior.get('head') not in proof['parents']
                        or rederive(value, {p:_decode(raw) for p,raw in prior['current']['files'].items()}, depth+1) != 'initially_absent'):
                    raise ValueError('Prior inventory has no proven empty initial boundary')
            elif value.get('schema_version') == 'newrouge.b-route-protection-snapshot.v3':
                import _b_route_inventory as inventory
                parent = path.rsplit('/', 1)[0]
                inventory_raw = _decode(current['files'][parent+'/inventory.json'])
                prior_inventory = strict_json(inventory_raw)
                original_files = {row['path']: _decode(current['files'][parent+'/'+row['artifact']])
                                  for row in value['raw_files'] if row.get('exists') is True}
                if (inventory.digest(inventory_raw) != value.get('inventory', {}).get('raw_digest')
                        or inventory.canonical_sha({k:v for k,v in value.items() if k != 'snapshot_digest'}) != value.get('snapshot_digest')
                        or value.get('cumulative') != []
                        or rederive(prior_inventory, original_files, depth+1) != 'initially_absent'):
                    raise ValueError('Prior protection is partial or non-initial')
            else:
                raise ValueError('Unknown or old owner policy is not an initial waiver')
    return 'required' if required else 'initially_absent'


def observe(snapshot, tasks, manifest_paths, header, *, exclude=None):
    """Derive facts, registering every current original with the inventory owner."""
    import _b_route_inventory as inventory
    base = {'schema_version': VERSION, 'state': 'required', 'reason': 'current_tasks_or_manifests', 'proof': None}
    counts = tasks.get('counts', {})
    if manifest_paths or any(type(counts.get(k)) is int and counts[k] > 0 for k in inventory.TRIPLET):
        return base
    try:
        if not _empty(tasks.get('documents')):
            raise ValueError('Complete genuine empty triplet required')
        controls = _controls(snapshot.root)
        parents = {}
        raw = _query(snapshot.root, 'rev-list', '--topo-order', '--parents', 'HEAD')
        for line in raw.decode('ascii').splitlines():
            row = line.split()
            if not row or row[0] in parents:
                raise ValueError('Ambiguous reachable ancestry')
            parents[row[0]] = row[1:]
        if not parents or len(parents) > MAX_COMMITS:
            raise ValueError('Complete ancestry exceeds bounded history observation')
        proof = {'root_real': str(snapshot.root.resolve()), 'head': snapshot.git_start['head'],
            'epics_path': snapshot.epics,
            'anchors': [header.get('codeBaselineCommit'), header.get('inputSnapshotCommit')],
            'parents': parents, 'controls_absent': controls, 'objects': {},
            'current': _current(snapshot.root, snapshot.read, snapshot.epics, exclude, parents,
                                snapshot.historical_inventory),
            'source_members': snapshot.source_set()['resolved_active_sources']}
        objects = Objects(snapshot.root, proof['objects'])
        _history(objects, proof, inventory.TRIPLET, inventory.strict_json)
        index = _query(snapshot.root, 'ls-files', '--stage', '-z', '--', *_index_paths(proof, inventory.TRIPLET))
        proof['index_base64'] = _encode(index)
        for record in index.split(b'\0'):
            if record:
                metadata, name = record.split(b'\t', 1)
                objects.get('blob', metadata.decode('ascii').split()[1])
        state = _derive(proof, tasks['documents'], snapshot.json(inventory.SOURCE_SET, 'source-set'),
                        inventory.TRIPLET, inventory.strict_json)
        return {'schema_version': VERSION, 'state': state, 'reason': 'governed_originals', 'proof': proof}
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, AttributeError, IndexError, RecursionError) as error:
        return {'schema_version': VERSION, 'state': 'unknown', 'reason': type(error).__name__+':'+str(error), 'proof': None}


def _rederive(report, raw_files, depth=0):
    """Archive-only recomputation; a re-signed state is never an authority."""
    import _b_route_inventory as inventory
    claimed = report.get('legacy_manifest_requirement')
    if (type(claimed) is not dict or set(claimed) != {'schema_version','state','reason','proof'}
            or claimed.get('schema_version') != VERSION
            or claimed.get('state') not in ('required','initially_absent','unknown')):
        raise ValueError('Versioned legacy requirement observation required')
    documents = {k: inventory.strict_json(raw_files[p]) for k,p in inventory.TRIPLET.items()}
    paths = [p for role,p in report['discovery'] if role == 'manifest']
    if paths or any(report['tasks']['counts'].get(k, 0) for k in inventory.TRIPLET):
        expected = 'required'
    elif claimed['proof'] is None:
        expected = 'unknown'
    else:
        proof = claimed['proof']
        _proof_shape(proof)
        if (proof['head'] != report['git']['head'] or proof['epics_path'] != report['epics']
                or proof['root_real'] != report['collection']['root_real']
                or proof['anchors'] != [report['declared_code_baseline'], report['declared_input_snapshot']]
                or proof['source_members'] != report['source_set']['resolved_active_sources']):
            raise ValueError('Original Git and current declared anchors differ')
        for p, encoded in proof['current']['files'].items():
            if raw_files.get(p) != _decode(encoded):
                raise ValueError('Missing or changed archived initial-boundary original')
        expected = _derive(proof, documents, inventory.strict_json(raw_files[inventory.SOURCE_SET]),
                           inventory.TRIPLET, inventory.strict_json, depth)
    if claimed['state'] != expected:
        raise ValueError('Derived requirement state does not match archived originals')
    return expected


def rederive(report, raw_files, depth=0):
    """Malformed archived structures become a structured unknown/error upstream."""
    try:
        return _rederive(report, raw_files, depth)
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as error:
        raise ValueError('Malformed original legacy proof/owner structure') from error


def verify_live(root, report, *, exclude=None):
    """Initial absence alone adds a live root/history/namespace recheck."""
    import _b_route_inventory as inventory
    claimed = report['legacy_manifest_requirement']
    if claimed['state'] != 'initially_absent':
        return
    snapshot = inventory.Snapshot(Path(root).absolute(), report['epics'],
                                  historical_inventory=report.get('historical_inventory_ref'))
    header = snapshot._canonical_inputs()
    tasks = snapshot.tasks()
    current = observe(snapshot, tasks, [], header, exclude=exclude)
    if inventory.canonical_sha(current) != inventory.canonical_sha(claimed) or any(d['severity'] == 'error' for d in snapshot.diagnostics):
        raise ValueError('Current initial boundary/root/history/membership changed')


def summary(report):
    """Complete semantic boundary facts; opaque object bytes remain archived."""
    import _b_route_inventory as inventory
    value = report['legacy_manifest_requirement']
    result = {key: value[key] for key in ('schema_version', 'state', 'reason')}
    result['original_observation_digest'] = inventory.canonical_sha(value)
    proof = value['proof']
    if proof is not None:
        current = proof['current']
        result['governed_boundary'] = {'root_real': proof['root_real'], 'head': proof['head'],
            'anchors': proof['anchors'], 'reachable_commit_ids': sorted(proof['parents']),
            'controls_absent': proof['controls_absent'], 'source_members': proof['source_members'],
            'manifest_directory_exists': current['manifest_directory_exists'],
            'manifest_members': current['manifest_members'], 'owner_records': current['owner_records'],
            'original_raw_digests': {path: inventory.digest(_decode(raw)) for path,raw in current['files'].items()}}
    return result
