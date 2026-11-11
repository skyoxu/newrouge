"""Shared short write leases and conservative pending checks for adoption owners."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import ntpath
from pathlib import Path
import posixpath
import re

import _b_route_codec as codec
import _b_route_operation_leases as leases

STORE = 'logs/ci/b-route-operations'
CAP_PENDING = 'docs/planning/semantic-topology/capability-apply.pending.json'
WRITER_SCOPE = 'writer:planning'
_ROOTS = {'capabilities': 'logs/ci/capability-planning', 'mvg': 'logs/ci/mvg-planning'}
_SCHEMAS = {'capabilities': 'newrouge.capability-planning-run.v1', 'mvg': 'newrouge.mvg-planning-run.v1'}
_DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
_SCOPE = re.compile(r'[a-z0-9][a-z0-9._:-]{0,127}', re.ASCII)


def _fail(code, entity=None, expected=None, actual=None, resume=None):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.BUNDLE, entity,
                                           expected, actual, resume))


def _path(value):
    codec.validate_reference_path(value)
    return posixpath.normpath(value)


def _path_identity(value):
    return ntpath.normcase(_path(value)).replace('\\', '/')


def _hash(value):
    try:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()
    except UnicodeEncodeError:
        _fail(codec.ReasonCode.INVALID_UTF8, expected='UTF-8 resource identity', actual='invalid string')


def _values(values):
    if isinstance(values, (str, bytes)):
        _fail(codec.ReasonCode.INVALID_TYPE, expected='resource sequence', actual=type(values).__name__)
    return tuple(values)


def resource_scopes(*, target_paths=(), plan_ids=(), requirement_ids=(), flow_ids=(), task_ids=(),
                    command_ids=(), state_ids=()):
    """Return stable resource keys; the service owns complete current/new closure."""
    result = {'file:' + _hash(_path_identity(path)) for path in _values(target_paths)}
    for kind, values in (('plan', plan_ids), ('requirement', requirement_ids), ('flow', flow_ids),
                         ('command', command_ids), ('state', state_ids)):
        for value in _values(values):
            result.add(kind + ':' + _hash(codec.validate_business_id(value)))
    for value in _values(task_ids):
        result.add('task:' + str(codec.validate_task_id(value)))
    return tuple(sorted(result))


def _scopes(values, *, allow_empty=False):
    values = _values(values)
    if (not values and not allow_empty) or any(type(value) is not str or
            not _SCOPE.fullmatch(value) or value == WRITER_SCOPE for value in values):
        _fail(codec.ReasonCode.INVALID_ARGUMENT, expected='complete portable business scopes', actual=values)
    return tuple(sorted(set(values)))


def _safe(root, relative):
    """Check existing ancestors before any guarded directory/file access."""
    relative = _path(relative)
    current = root
    leases._directory(root)
    for part in relative.split('/'):
        current = current / part
        try:
            leases._no_reparse(current)
        except FileNotFoundError:
            continue
    if not current.resolve().is_relative_to(root):
        _fail(codec.ReasonCode.UNSAFE_PATH, relative, 'contained path', 'outside repository')
    return current


def _directory(root, relative):
    current = root
    for part in _path(relative).split('/'):
        current = current / part
        try:
            leases._directory(current)
        except FileNotFoundError:
            current.mkdir(exist_ok=True)
            leases._directory(current)
    return current



def initialize_lock_namespace(root):
    """Prepare only fixed lock parents before a managed writer captures inputs.

    Dynamic scope directories and lock files remain owned by scope_guard. This
    grants no operation/index/pending claim and changes no observation policy.
    """
    root = leases._directory(Path(root).absolute())
    metadata = _directory(root, STORE + '/locks/metadata')
    scopes = _directory(root, STORE + '/locks/scopes')
    return metadata, scopes

def _json(root, relative, *, optional=False):
    path = _safe(root, relative)
    if optional and not path.exists():
        return None
    return codec.strict_json_loads(codec.read_reference_bytes(root, relative))


def _operation_inventory(root):
    import _planning_apply_journal as journal
    function = getattr(journal, 'operation_inventory', None)
    if not callable(function):
        _fail(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, expected='operation_inventory storage owner', actual='unavailable')
    active = getattr(journal, 'active_operation_inventory', None)
    if not callable(active):
        _fail(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, expected='active operation inventory owner', actual='unavailable')
    return active(root)


def _new_pending(root, requested, operation_id, legacy_owner, compensation_frozen=None):
    values = _operation_inventory(root)
    if type(values) is not list:
        _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, expected='complete operation inventory', actual='invalid inventory')
    allowed = frozenset()
    if compensation_frozen is not None:
        import _b_route_compensation as compensation
        allowed = compensation.authorize_pending_claims(root, operation_id, compensation_frozen,
            pending_operations=values)
    seen = set()
    for value in values:
        if type(value) is not dict or value.get('state') not in ('prepared', 'reserved'):
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, expected='known pending operation', actual='unknown operation')
        identity = codec.validate_business_id(value.get('operation_id'))
        if identity in seen:
            _fail(codec.ReasonCode.CONFLICT, identity, 'unique operation', 'duplicate inventory operation')
        seen.add(identity)
        frozen = value.get('frozen')
        if type(frozen) is not dict or 'scope_ids' not in frozen:
            _fail(codec.ReasonCode.PENDING, identity, 'complete frozen pending scope', 'unknown scope')
        existing = _scopes(frozen['scope_ids'])
        if identity == operation_id:
            if existing != requested:
                _fail(codec.ReasonCode.INPUT_STALE, identity, existing, requested)
            continue
        if identity in allowed:
            continue
        if legacy_owner is not None or set(existing).intersection(requested):
            resume = STORE + '/operations/' + _hash(identity) + '/operation.json'
            _fail(codec.ReasonCode.PENDING, identity, 'nonoverlapping operation', existing, resume)


def _owner(root, value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'kind', 'run_id', 'journal_path'}:
        _fail(codec.ReasonCode.INVALID_ARGUMENT, expected='exact legacy owner fields', actual=value)
    kind, run_id = value['kind'], value['run_id']
    base_kind = 'mvg' if kind == 'mvg-rebind' else kind
    if (type(base_kind) is not str or base_kind not in _ROOTS or type(run_id) is not str or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) is None):
        _fail(codec.ReasonCode.INVALID_ARGUMENT, expected='known legacy owner/run', actual=value)
    expected = _ROOTS[base_kind] + '/' + run_id + '/apply-journal.json'
    if value['journal_path'] != expected:
        _fail(codec.ReasonCode.CONFLICT, run_id, expected, value['journal_path'])
    run = _json(root, _ROOTS[base_kind] + '/' + run_id + '/run.json')
    if (type(run) is not dict or run.get('schema_version') != _SCHEMAS[base_kind]
            or run.get('run_id') != run_id):
        _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, run_id, 'matching original legacy run', 'mismatched run')
    return {**value, 'base_kind': base_kind}


def _legacy_journal(root, relative):
    value = _json(root, relative)
    if (type(value) is not dict or value.get('schema_version') != 'newrouge.planning-apply-journal.v1'
            or value.get('status') not in ('pending', 'complete') or type(value.get('entries')) is not list
            or not value['entries'] or type(value.get('authority_inputs')) is not dict
            or type(value.get('result')) is not dict):
        _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, relative, 'complete original journal shape', 'damaged journal', relative)
    identities = set()
    for path in value['authority_inputs']:
        _safe(root, path)
    for row in value['entries']:
        if type(row) is not dict or not {'path', 'before_sha256', 'before_base64', 'after_sha256', 'payload'} <= set(row):
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, relative, 'complete target row', 'damaged journal', relative)
        _safe(root, row['path'])
        identity = _path_identity(row['path'])
        if identity in identities:
            _fail(codec.ReasonCode.CONFLICT, relative, 'unique journal targets', 'aliased targets', relative)
        identities.add(identity)
        before, encoded = row['before_sha256'], row['before_base64']
        if before is None:
            valid = encoded is None
        else:
            try:
                valid = (type(before) is str and _DIGEST.fullmatch(before) is not None and
                         type(encoded) is str and codec.raw_digest(base64.b64decode(encoded, validate=True)) == before)
            except ValueError:
                valid = False
        after = codec.raw_digest((json.dumps(row['payload'], ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        if not valid or row['after_sha256'] != after:
            _fail(codec.ReasonCode.DIGEST_MISMATCH, relative, 'intact original target images', 'changed journal image', relative)
    return value


def _completed(root, kind, run_id, journal):
    """Recognize original owned completion, not freshness of later formal files."""
    if journal['status'] != 'complete':
        return False
    prefix = _ROOTS[kind] + '/' + run_id
    run = _json(root, prefix + '/run.json', optional=True)
    summary = _json(root, prefix + '/apply-summary.json', optional=True)
    if (type(run) is not dict or run.get('schema_version') != _SCHEMAS[kind]
            or run.get('run_id') != run_id or run.get('applied') is not True
            or run.get('phase') != 'applied' or type(summary) is not dict
            or summary.get('status') != 'applied' or journal['result'].get('status') != 'applied'):
        return False
    result = journal['result']
    targets = {_path(row['path']): row for row in journal['entries']}
    if kind == 'capabilities':
        digest = result.get('capabilities_sha256')
        target = targets.get('docs/planning/semantic-topology/capabilities.v1.json', {})
        return (result.get('run_id') == run_id and summary.get('run_id') == run_id
            and type(digest) is str and _DIGEST.fullmatch(digest) is not None
            and run.get('applied_capabilities_sha256') == digest
            and summary.get('capabilities_sha256') == digest and target.get('after_sha256') == digest)
    manifest = result.get('manifest_path')
    trace = 'docs/testing/mvg/planning/' + run_id + '.json'
    if type(manifest) is not str or result.get('trace_path') != trace:
        return False
    target, trace_row = targets.get(_path(manifest), {}), targets.get(trace, {})
    trace_payload = trace_row.get('payload')
    digest = result.get('manifest_sha256')
    return (type(digest) is str and _DIGEST.fullmatch(digest) is not None
        and run.get('manifest_path') == manifest and run.get('applied_manifest_sha256') == digest
        and summary.get('manifest_path') == manifest and summary.get('manifest_sha256') == digest
        and summary.get('trace_path') == trace and target.get('after_sha256') == digest
        and type(trace_payload) is dict and trace_payload.get('applied_manifest_path') == manifest
        and trace_payload.get('applied_manifest_sha256') == digest)


def _own_journal(owner, kind, run_id, relative):
    return (owner is not None and owner['kind'] != 'mvg-rebind' and owner['base_kind'] == kind
            and owner['run_id'] == run_id and owner['journal_path'] == relative)


def _legacy_pending(root, owner):
    # JSON null is a damaged existing marker, never equivalent to missing bytes.
    if _safe(root, CAP_PENDING).exists():
        marker = _json(root, CAP_PENDING)
        if type(marker) is not dict or set(marker) != {'run_id', 'journal_path'}:
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, CAP_PENDING, 'original Capability marker', 'damaged marker', CAP_PENDING)
        run_id, relative = marker['run_id'], marker['journal_path']
        if type(run_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) is None:
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, CAP_PENDING, 'safe original run', 'invalid run', CAP_PENDING)
        expected = _ROOTS['capabilities'] + '/' + run_id + '/apply-journal.json'
        if relative != expected:
            _fail(codec.ReasonCode.CONFLICT, CAP_PENDING, expected, relative, CAP_PENDING)
        _legacy_journal(root, relative)
        if not _own_journal(owner, 'capabilities', run_id, relative):
            _fail(codec.ReasonCode.PENDING, run_id, 'resolved original Capability pending', 'unknown legacy scope', relative)
    for kind, prefix in _ROOTS.items():
        directory = _safe(root, prefix)
        if not directory.exists():
            continue
        leases._directory(directory)
        for run in directory.iterdir():
            leases._no_reparse(run)
            if not run.is_dir():
                continue
            relative = prefix + '/' + run.name + '/apply-journal.json'
            path = _safe(root, relative)
            if not path.exists():
                continue
            journal = _legacy_journal(root, relative)
            if _own_journal(owner, kind, run.name, relative):
                continue
            if not _completed(root, kind, run.name, journal):
                _fail(codec.ReasonCode.PENDING, run.name, 'resolved original legacy journal', 'unknown legacy scope', relative)


def legacy_recovery_routes(root):
    """Locate original apply owners without writing or granting an exemption.

    Unknown scope remains conservative. The owning public apply keeps its
    original confirmation, checkpoint/accounting and marker cleanup contract.
    """
    root = Path(root).absolute()
    routes = {}
    def include(kind, run_id, relative, marker=None):
        _owner(root, {'kind': kind, 'run_id': run_id, 'journal_path': relative})
        routes[relative] = {'kind': kind, 'run_id': run_id, 'journal_path': relative,
            'marker_path': marker, 'resume_ref': relative, 'scope': 'unknown',
            'owner_api': 'plan_capabilities.apply' if kind == 'capabilities' else 'plan_mvg.apply',
            'requires_original_confirmation': True}
    if _safe(root, CAP_PENDING).exists():
        marker = _json(root, CAP_PENDING)
        if type(marker) is not dict or set(marker) != {'run_id', 'journal_path'}:
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, CAP_PENDING,
                  'original Capability marker', 'damaged marker', CAP_PENDING)
        run_id, relative = marker['run_id'], marker['journal_path']
        if type(run_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) is None:
            _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, CAP_PENDING,
                  'safe original run', 'invalid run', CAP_PENDING)
        expected = _ROOTS['capabilities'] + '/' + run_id + '/apply-journal.json'
        if relative != expected:
            _fail(codec.ReasonCode.CONFLICT, CAP_PENDING, expected, relative, CAP_PENDING)
        _legacy_journal(root, relative)
        include('capabilities', run_id, relative, CAP_PENDING)
    for kind, prefix in _ROOTS.items():
        directory = _safe(root, prefix)
        if not directory.exists():
            continue
        leases._directory(directory)
        for run in sorted(directory.iterdir()):
            leases._no_reparse(run)
            if not run.is_dir():
                continue
            relative = prefix + '/' + run.name + '/apply-journal.json'
            if not _safe(root, relative).exists():
                continue
            value = _legacy_journal(root, relative)
            if relative not in routes and not _completed(root, kind, run.name, value):
                include(kind, run.name, relative)
    return [routes[key] for key in sorted(routes)]


@contextmanager
def scope_guard(root, scope_ids, *, prepare_under_lease, operation_id=None, legacy_owner=None):
    """Protect a short managed write; never acquire activity/run or call a model."""
    root = leases._directory(Path(root).absolute())
    if not callable(prepare_under_lease) or (operation_id is not None and legacy_owner is not None):
        _fail(codec.ReasonCode.INVALID_ARGUMENT, expected='one managed owner and callback', actual='invalid owner')
    if operation_id is not None:
        codec.validate_business_id(operation_id)
    requested = _scopes(scope_ids, allow_empty=legacy_owner is not None)
    metadata, _ = initialize_lock_namespace(root)
    scope_dirs = {value: _directory(root, STORE + '/locks/scopes/' + _hash(value))
                  for value in (*requested, WRITER_SCOPE)}
    def prepare():
        # Reload the owning run under the actual write boundary, not before it.
        owner = _owner(root, legacy_owner)
        _new_pending(root, requested, operation_id, owner)
        _legacy_pending(root, owner)
        return prepare_under_lease()
    try:
        with leases.operation_leases(root, metadata, scope_dirs, prepare_under_lease=prepare) as value:
            yield value
    except ValueError as error:
        if isinstance(error, codec.CodecError):
            raise
        if str(error) == 'capability_coordinator_busy':
            _fail(codec.ReasonCode.CONFLICT, operation_id, 'available managed write lease', 'busy scope', STORE)
        raise


@contextmanager
def business_guard(root, scope_ids, *, operation_id=None, compensation_frozen=None, review_only=False):
    """Hold the existing business lock family during expensive read-only work.

    Metadata protects only lock acquisition. No protocol replay, inventory or
    whole-record validation runs in its callback; the global writer is absent.
    Old managed writers still acquire these exact same business locks.
    """
    root = leases._directory(Path(root).absolute())
    requested = _scopes(scope_ids)
    metadata = _directory(root, STORE + '/locks/metadata')
    directories = {value: _directory(root, STORE + '/locks/scopes/' + _hash(value)) for value in requested}
    try:
        with leases.operation_leases(root, metadata, directories, prepare_under_lease=lambda: None):
            if not review_only:
                _new_pending(root, requested, operation_id, None, compensation_frozen)
            _legacy_pending(root, None)
            yield
    except ValueError as error:
        if not isinstance(error, codec.CodecError) and str(error) == 'capability_coordinator_busy':
            _fail(codec.ReasonCode.CONFLICT, operation_id, 'available business lease', 'busy scope', STORE)
        raise


@contextmanager
def writer_boundary(root, *, recheck):
    """Reacquire only original metadata/WRITER for a bounded byte operation.

    The caller already holds complete business scopes. recheck must compare
    captured facts only; it must not run full bundle/native/inventory replay.
    """
    root = leases._directory(Path(root).absolute())
    metadata = _directory(root, STORE + '/locks/metadata')
    writer = _directory(root, STORE + '/locks/scopes/' + _hash(WRITER_SCOPE))
    try:
        with leases.operation_leases(root, metadata, {WRITER_SCOPE: writer},
                                     prepare_under_lease=recheck) as value:
            yield value
    except ValueError as error:
        if not isinstance(error, codec.CodecError) and str(error) == 'capability_coordinator_busy':
            _fail(codec.ReasonCode.CONFLICT, expected='available short writer lease', actual='busy writer', resume=STORE)
        raise
