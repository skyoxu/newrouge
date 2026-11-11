"""UNEXECUTED owner candidate: install as _b_route_retained_execution.py.

One explicitly admitted historical R52 execution, not a general capture importer.
Default origin capture stays fresh unless this owner has durably bound an
operation to the exact archived execution. No subprocess/model/transport shim.
The old R52 reader is source-loaded at its actual old path for local closing.
Root must review/integrate the accompanying owner edits and tests before use.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
from types import ModuleType
from weakref import WeakKeyDictionary

import _b_route_codec as codec

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
OLD_SOURCE = TASK / 'r52'
ORIGIN = TASK / 'nx'
TARGET = TASK / 'story27-r52-v15-empty-target-native01'
OPERATION = 'NativeV15Origin02'
ATTEMPT = 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01'
SCHEMA = 'newrouge.b-route-retained-native-execution-binding.v1'
CONFIG = 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json'
REQUEST = 'logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-02/request.json'
REQUEST_SHA = '30b0c44c35000f5814f879266592c4d0bd3139b830dd3d782ad54448d4993413'
READER = OLD_SOURCE / 'scripts/python/_b_route_frozen_native_reader.py'
READER_SHA = '3c2b2c614082c3dcd04f5ac4866e0152fa93e4dc19ac5487853cef6731f41548'
PINS = {
    CONFIG: 'd6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d',
    ATTEMPT + '/reader-stdout.bin': '57b2c0d883ae6884b090a32d4652e367f22743d467c5d4b0fd6c4982eac2e295',
    ATTEMPT + '/reader-stderr.bin': 'ab643f2520346c6a2443c201fd3fe10779da2546ba9e263f563778827c40740e',
    ATTEMPT + '/actual-native-capture.json': '15771c58f9f7f8065b4b03a608d294625c88604a170d0a0d3235f1fd33b0785f',
    ATTEMPT + '/reader-held-started.json': '012731090b820c06579e91ab3a3daf851051fa328da954ebdf29d59155330354',
    ATTEMPT + '/reader-held-terminal.json': 'f8ccd45bf89c799692636bf77aa7c5aa8d08c2b0f669a3ed994984a754b66e42',
    ATTEMPT + '/stop.json': '8eeb2cb2399a4706316831564ec1d49042757fe6c02bccd8e485a4fbf2ed7f60',
    'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/result.json':
        '0e43c191bd9da4ec0110f82bece80bf72e547bbc4a8dd894ff533489d64f01ab',
    'night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py':
        '3875a5c8865fef7b4297fd8c62393429dea07a63f73b2a8ae051316e11138449',
    'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/manifest.json':
        '88a551e4a57a09a621990758ae6355d0de70651824a36faabc01ec991810fa25',
    'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/run_review_prepare.Root-only.py':
        '71e7f9241ae4485a525868060bff75db537fff15e1a6c2d4ce82f5c3fd4916c8',
    'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/control_common.py':
        '0ea4c7774dec93207fd1b5470ac29232fbcdf0d01b20b06f8db570d85c32ccbe',
    'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/supervisor-started.json':
        '8487cfa42819c94fd8481cc2af5436eecb3d166e42731a432bfe001272f33ab7',
    'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/child-started.json':
        'afc066d65dd521c1ea22375a9f359ed5c76af93b06f74273685c571d53998a8a',
    'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/child-terminal.json':
        '8b44bd98f93be1f9380ed81da84a3f71febfe4e397516ac0a814532b9ffea9a6',
}
SECRET = {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions', 'credentials',
          'auth.json', 'credentials.json', 'credentials.toml', 'id_rsa', 'id_ed25519'}
_ISSUED = WeakKeyDictionary()
# Original reviewed gate, used only to bind historical argv, never to spawn.
_ORIGINAL_READER_GATE = "import sys\nif sys.stdin.buffer.readline() != b'start\\n': raise SystemExit(2)\n"


def need(ok, why):
    if not ok:
        raise ValueError('retained_native_execution:' + why)


def _plain(path, *, missing=False):
    path = Path(path).absolute()
    need('..' not in path.parts and not any(p.casefold() in SECRET or p.casefold().startswith('.env')
                                           for p in path.parts), 'unsafe path')
    for item in reversed((path, *path.parents)):
        try:
            row = item.lstat()
        except FileNotFoundError:
            need(missing, 'missing path')
            continue
        need(not stat.S_ISLNK(row.st_mode) and not getattr(row, 'st_file_attributes', 0) & 0x400,
             'reparse path')
        need(stat.S_ISDIR(row.st_mode) or stat.S_ISREG(row.st_mode) and row.st_nlink == 1,
             'special or hardlinked path')
    return path


def _read(path):
    path = _plain(path)
    limit = 192 * 1024 * 1024  # Fixed real archive is 180700910 bytes.
    before = path.stat()
    need(before.st_size <= limit, 'fixed recovery input byte limit before allocation')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    need(len(raw) <= limit and len(raw) == before.st_size
         and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
         == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'bounded stable recovery read')
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _same(left, right):
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def binding_path(operation_id):
    codec.validate_business_id(operation_id)
    return ('logs/ci/b-route-retained-executions/'
            + hashlib.sha256(operation_id.encode('utf-8')).hexdigest() + '/binding.json')


def read_support(root, *, operation_id, expected_raw_digest):
    """Read real private support bytes for a separately verified history lane.

    This decoder does NOT run fresh target/protection/current-policy gates and
    does NOT issue an action token or grant adoption. The historical owner must
    obtain expected_raw_digest from its real pinned subject/proof/runtime.
    """
    raw = _read(_record(root, operation_id))
    need(type(expected_raw_digest) is str and codec.raw_digest(raw) == expected_raw_digest,
         'historical support exact raw pin')
    value = codec.strict_json_loads(raw)
    need(type(value) is dict and set(value) == {
        'schema_version', 'operation_id', 'target_root', 'request_ref', 'request_raw_digest',
        'request_body_digest', 'material', 'review_ref', 'execution', 'origin_capsule_digest',
        'target_authority', 'consumer_rule', 'consumer_policy_identity',
        'formal_adoption', 'readiness', 'runtime_verified'}, 'closed retained support schema')
    need(value['schema_version'] == SCHEMA and value['operation_id'] == operation_id
         and value['target_root'] == str(TARGET) and value['request_ref'] == REQUEST
         and value['request_raw_digest'] == 'sha256:' + REQUEST_SHA,
         'historical support exact operation/request identity')
    epoch = value['execution']['execution_epoch']
    need(epoch == {'source_root': str(TASK / 'r22'),
                   'source_commit': '6d4ab1c3cba67bebe98f75c9462af613bf9d739a',
                   'reader_path': str(READER), 'reader_raw_digest': 'sha256:' + READER_SHA}
         and _same(value['execution']['raw_pins'], PINS)
         and value['execution']['execution_reused'] is True
         and type(value['execution']['new_native_executions']) is int
         and value['execution']['new_native_executions'] == 0
         and all(value[key] is False for key in ('formal_adoption', 'readiness', 'runtime_verified')),
         'historical support original execution epoch, no new grant')
    return {'reference': binding_path(operation_id), 'raw_digest': expected_raw_digest, 'value': value,
            'claim': 'archive-only support decoder; no fresh eligibility or action token'}


def _record(root, operation_id):
    need(os.path.normcase(str(Path(root).absolute())) == os.path.normcase(str(TARGET))
         and operation_id == OPERATION, 'fixed original operation/target before I/O')
    need(_plain(root).resolve() == TARGET, 'plain actual fixed target root')
    return _plain(TARGET / binding_path(operation_id), missing=True)


def _fixed_json(reference):
    raw = _read(TASK / reference)
    need(_sha(raw) == PINS[reference], 'changed archived execution/control: ' + reference)
    return codec.strict_json_loads(raw)


@contextmanager
def _original_reader():
    raw = _read(READER)
    info = _plain(READER).stat()
    identity = (info.st_dev, info.st_ino)
    need(_sha(raw) == READER_SHA, 'old reader raw changed')
    module = ModuleType('_retained_original_R52_reader')
    module.__file__ = str(READER)
    # Full original source; do not import an installed/cached reader or relabel it.
    exec(compile(raw, str(READER), 'exec', dont_inherit=True, optimize=0), module.__dict__)
    module._adoption_source_digest = 'sha256:' + READER_SHA
    try:
        yield module
    finally:
        current = _plain(READER).stat()
        need((current.st_dev, current.st_ino) == identity and _read(READER) == raw,
             'old reader bytes/file changed during local verification')


def _original_controls():
    config = _fixed_json(CONFIG)
    for reference, expected in PINS.items():
        if reference in {ATTEMPT + '/reader-stdout.bin', ATTEMPT + '/actual-native-capture.json',
                         ATTEMPT + '/reader-stderr.bin'}:
            continue  # Complete raw bytes are read and checked exactly below.
        need(_sha(_read(TASK / reference)) == expected, 'original execution/control raw changed')
    need(config['operation_id'] == OPERATION and config['request_ref'] == REQUEST
         and config['request_sha256'] == REQUEST_SHA and Path(config['target']) == TARGET
         and config['actual_counts']['source'] == 885, 'original closed config')
    # Historical parent source885 is data, not a claim that new consumer owners
    # still have old bytes. Root archives the two changed owner originals before
    # installing this feature. Only the actual native footprint (reader3c2)
    # must retain its original path/current bytes; native.verify_capture closes
    # all other real native source/data/dependency pins below.
    historical = TASK / 'logs/ci/2026-11-09/story27-r52-retained-execution-admission-01/old-owner-sources'
    for name in ('_b_route_qualified_origin.py', '_b_route_adoption_review.py'):
        need(_sha(_read(historical / name)) == config['source_files']['scripts/python/' + name],
             'real archived original owner bytes required before in-place upgrade')
    need(config['source_commit'] == '680e4f7d2ddfd67d4b9eaa411f290fb9120a8a45'
         and config['source_overlay_sha256'] == 'b6d4a56b25117fa42915f510615e60e21a653fbb37572aa1346428d0aef83b33',
         'original parent execution epoch identity')
    for reference, digest in {**config['parent_pins'], **config['prerequisite_pins']}.items():
        codec.validate_reference_path(reference)
        need(_sha(_read(TASK / reference)) == digest, 'old prerequisite/control drift')
    return config


def _execution():
    """Actual archived result + original observed terminal, no new execution."""
    config = _original_controls()
    started = _fixed_json(ATTEMPT + '/reader-held-started.json')
    terminal = _fixed_json(ATTEMPT + '/reader-held-terminal.json')
    stop = _fixed_json(ATTEMPT + '/stop.json')
    supervisor = _fixed_json('logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/result.json')
    need(supervisor['transport_complete'] is True and supervisor['terminal_known'] is True
         and supervisor['actual_original_held_child_exit_code'] == 1 and supervisor['child_pid'] == 8468
         and supervisor['original_program_and_control_pins_unchanged'] is True
         and supervisor['automatic_retry'] is False, 'preserve actual failed worker terminal')
    need(started['pid'] == 32180 and started['birth_filetime'] == 134387081439910300
         and started['Popen_audit'] is True and started['CreateProcess_audit'] is True
         and started['identity_error'] is None, 'actual original reader started identity')
    rows = terminal['children']
    need(len(rows) == 1 and all(rows[0][key] == started[key] for key in
         ('pid', 'held_handle', 'birth_filetime', 'image', 'identity_error', 'Popen_audit', 'CreateProcess_audit'))
         and type(rows[0]['actual_original_held_OS_exit']) is int
         and rows[0]['actual_original_held_OS_exit'] == 0 and rows[0]['exit_known'] is True
         and terminal['original_transport_returned_normally'] is True, 'actual original reader OS0')
    job = terminal['Job_observations']
    need(job['assign_success'] == 1 and job['last_active'] == 0 and job['zero_observed'] is True
         and job['close_success'] == 1 and job['errors'] == [], 'original Job empty and closed')
    need(stop['passed'] is False and stop['original_owner_returncode'] == 2
         and stop['reader_calls'] == 1 and stop['operation_id'] == OPERATION
         and stop['model_calls'] == 0 and stop['paid_or_unknown'] == 80
         and stop['guard_occupancy'] == 178 and stop['campaign_limit'] == 290
         and stop['released'] == 0, 'old failure and charged facts stay unchanged')
    missing = str(TARGET / 'docs/planning/b-route/plans/plan-735858d844794547bfe433abfabb3bbd/1.json')
    blocks = stop['blocked_actions']
    need(len(blocks) == 2 and blocks[0]['role'] == 'read outside fixed or authenticated positive closure'
         and os.path.normcase(blocks[0]['value']) == os.path.normcase(missing)
         and blocks[1]['event'] == 'open' and blocks[1]['type'] == 'Denied', 'exact old host-only stop boundary')
    stdout = _read(TASK / (ATTEMPT + '/reader-stdout.bin'))
    archive = _read(TASK / (ATTEMPT + '/actual-native-capture.json'))
    stderr = _read(TASK / (ATTEMPT + '/reader-stderr.bin'))
    need(len(stdout) == 178321214 and len(archive) == 180700910
         and _sha(stdout) == PINS[ATTEMPT + '/reader-stdout.bin']
         and _sha(archive) == PINS[ATTEMPT + '/actual-native-capture.json']
         and _sha(stderr) == PINS[ATTEMPT + '/reader-stderr.bin'], 'exact original raw outputs')
    with _original_reader() as reader:
        native = reader.strict_json(stdout)
        need(_same(native, reader.strict_json(archive)), 'pretty archive is original output, not replacement')
        footprint = {name: pin for name, pin in native['files'].items()
                     if Path(name).is_relative_to(OLD_SOURCE)}
        need(footprint == {str(READER): 'sha256:' + READER_SHA}
             and not any(Path(name).is_relative_to(OLD_SOURCE) for name in native['directories']),
             'actual captured R52 footprint is only unchanged reader3c2')
        reader.verify_capture(ORIGIN, native)
        # Original request/argv are reconstructed under the exact old reader
        # contract. The archived Guard body/terminal authenticates their prior
        # check; this is not a claim that a new process or raw argv log exists.
        state_raw = _read(ORIGIN / 'logs/ci/mvg-planning/m4/run.json')
        need(reader.digest(state_raw) == config['run_digest'], 'original input state still current')
        request = {'source_root': str(TASK / 'r22'), 'source_commit': reader.R22_SOURCE_COMMIT,
            'artifact_root': str(ORIGIN), 'planner': 'mvg', 'run_id': 'm4',
            'expected_run_raw_digest': config['run_digest'],
            'expected_handoff_ref': {'path': 'logs/ci/mvg-planning/m4/handoff.json',
                'schema_version': 'newrouge.b-route-planning-handoff.v1',
                'raw_digest': 'sha256:caea69f6af1d0c7e34f1e098979e38065832e35d8de9219c664f6166d3707cbf'},
            'dependency_paths': config['parent_import_paths'][2:],
            'reader_path': str(READER), 'reader_raw_digest': 'sha256:' + READER_SHA}
        reader._request(reader.canonical(request))
        argv = [str(Path(r'C:\Program Files\Python312\python.exe')), '-X', 'dev', '-I', '-S', '-B', '-c',
                _ORIGINAL_READER_GATE + reader._reader_bootstrap(READER, 'sha256:' + READER_SHA)]
    guard_raw = _read(TASK / 'night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py')
    need(_sha(guard_raw) == PINS['night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py'],
         'old exact argv/input/transport guard changed')
    return native, {'execution_schema': 'newrouge.b-route-retained-native-execution.v1',
        'execution_epoch': {'source_root': str(TASK / 'r22'), 'source_commit': reader.R22_SOURCE_COMMIT,
                            'reader_path': str(READER), 'reader_raw_digest': 'sha256:' + READER_SHA},
        'original_parent_source_epoch': {'source_commit': config['source_commit'],
            'source_manifest_ref': CONFIG, 'source_manifest_raw_sha256': PINS[CONFIG],
            'source_overlay_ref': config['source_overlay_ref'], 'source_overlay_sha256': config['source_overlay_sha256']},
        'request_digest': reader.digest(reader.canonical(request)),
        'argv_digest': codec.canonical_digest(argv), 'cwd': str(TASK / 'r22'), 'host_timeout': 3600,
        'argv_input_basis': 'reconstructed_original_contract_verified_by_pinned_original_Guard',
        'raw_pins': PINS, 'native_result_digest': native['result_digest'],
        'old_worker_exit': 1, 'old_reader_exit': 0, 'execution_reused': True, 'new_native_executions': 0}


def _request(root, operation_id):
    _record(root, operation_id)
    raw = _read(TARGET / REQUEST)
    need(_sha(raw) == REQUEST_SHA, 'unchanged original Request02 raw')
    value = codec.strict_json_loads(raw)
    need(value['operation_id'] == operation_id and 'host_review_ref' not in value, 'original unsealed request')
    return value


def _target_facts(root, request):
    import _b_route_adoption as adoption
    import _b_route_qualified_origin as origin
    import _b_route_protection as protection
    snapshot = adoption.Snapshot(root)
    identity, source = origin.target_source(snapshot)
    cap = snapshot.ref(request['material']['handoff_ref'])
    native = origin.verify_capsule(root, cap)
    snapshot.ref(request['material']['protection_ref'])
    result = protection.verify_protection(root, request['material']['protection_ref']['path'])
    need(result['ok'] and result.get('capture_complete') is True, 'original target protection current')
    adoption._committed(snapshot)
    need(snapshot.catalog is None and not snapshot.committed, 'same fresh target namespace')
    snapshot.verify()
    return {'identity': identity, 'source': source, 'files': snapshot.files,
            'directories': snapshot.directories}, cap, native


def _binding_value(root, operation_id):
    request = _request(root, operation_id)
    native, execution = _execution()
    facts, capsule, prior = _target_facts(root, request)
    need(_same(native, prior), 'same full actual capture as original capsule')
    return {'schema_version': SCHEMA, 'operation_id': operation_id, 'target_root': str(TARGET),
        'request_ref': REQUEST, 'request_raw_digest': 'sha256:' + REQUEST_SHA,
        'request_body_digest': codec.canonical_digest(request), 'material': request['material'],
        'review_ref': request['review_ref'], 'execution': execution,
        'origin_capsule_digest': codec.canonical_digest(capsule),
        # This support binds only immutable target authority/source facts. Later
        # review files and operation metadata are closed by their original owners.
        'target_authority': facts, 'consumer_rule': codec.raw_digest(_read(Path(__file__).absolute())),
        'consumer_policy_identity': __import__('_b_route_adoption_review').policy_identity(),
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False}, native


def admit(root, *, operation_id, execution_ref):
    """Named explicit owner write; only this exact old archive may be bound.

    Caller-supplied dictionaries, arbitrary capture files and implicit activation
    are not accepted. The resulting per-operation binding is immutable support.
    """
    if operation_id == OPERATION03:
        return _admit03(root, operation_id=operation_id, execution_ref=execution_ref)
    need(execution_ref == ATTEMPT + '/actual-native-capture.json', 'one original execution ref')
    import _b_route_qualified_origin as origin
    from _b_route_adoption_review import write_once, raw
    from _b_route_operation_scope import scope_guard, resource_scopes
    path = _record(root, operation_id)
    with origin.activity():
        value, _ = _binding_value(root, operation_id)
        def persist():
            fresh, _ = _binding_value(root, operation_id)
            need(_same(fresh, value), 'complete support stable under lease')
            write_once(root, binding_path(operation_id), raw(value))
            need(_same(codec.strict_json_loads(_read(path)), value), 'exact persisted retained binding')
            return {'status': 'retained_execution_bound', 'support_ref': binding_path(operation_id),
                    'support_raw_digest': codec.raw_digest(_read(path)),
                    'execution_reused': True, 'new_native_executions': 0, 'formal_adoption': False}
        with scope_guard(root, resource_scopes(target_paths=[binding_path(operation_id)]),
                         operation_id=operation_id, prepare_under_lease=persist) as result:
            return result


class _Action:
    __slots__ = ('__weakref__',)
    __hash__ = object.__hash__
    __eq__ = object.__eq__


def capture_for_material(root, *, operation_id, material, review_ref):
    """Return None only if never explicitly bound; malformed support is fatal."""
    # This version has one literal admitted scope; every other operation keeps
    # the pre-existing fresh path without consulting any foreign support path.
    if operation_id == OPERATION03:
        return _capture_for_material03(root, operation_id=operation_id, material=material, review_ref=review_ref)
    if (os.path.normcase(str(Path(root).absolute())) != os.path.normcase(str(TARGET))
            or operation_id != OPERATION):
        return None
    path = _record(root, operation_id)
    # This exact old failed operation is explicitly designated by this version.
    # Missing/deleted/partial support may never silently fall back to a new run.
    need(path.is_file(), 'explicit old operation requires admitted retained binding; no fresh fallback')
    record_raw = _read(path)
    stored = codec.strict_json_loads(record_raw)
    actual, native = _binding_value(root, operation_id)
    need(_same(stored, actual) and _same(material, stored['material'])
         and _same(review_ref, stored['review_ref']), 'same retained operation/material/source/current authority')
    token = _Action()
    _ISSUED[token] = {'root': str(Path(root).resolve()), 'operation_id': operation_id,
                      'binding_raw': record_raw, 'binding': actual, 'native': native, 'building': False}
    return token


def verify_action(root, token, *, operation_id):
    if operation_id == OPERATION03:
        return _verify_action03(root, token, operation_id=operation_id)
    need(type(token) is _Action and token in _ISSUED, 'owner-issued action token required')
    issued = _ISSUED[token]
    need(issued.get('building') is False and issued['root'] == str(Path(root).resolve()) and issued['operation_id'] == operation_id,
         'action root/operation mismatch')
    need(_read(_record(root, operation_id)) == issued['binding_raw'], 'immutable support changed')
    with _original_reader() as reader:
        reader.verify_capture(ORIGIN, issued['native'])
    current, _ = _binding_value(root, operation_id)
    need(_same(current, issued['binding']), 'action currentness drift')


def native_from_action(root, token, *, operation_id):
    verify_action(root, token, operation_id=operation_id)
    return deepcopy(_ISSUED[token]['native'])


# Fixed new consumer. Old OP02/Request02 and its v1 support remain untouched.
from types import FunctionType

CONSUMER_SOURCE03 = TASK / 'r56'
OPERATION03 = 'NativeV15Origin03'
REQUEST03 = 'logs/ci/2026-11-09/b-route-requests/native-v15-origin03-request-01/request.json'
SCHEMA03 = 'newrouge.b-route-retained-native-execution-binding.v2'
EXECUTION_REF03 = ATTEMPT + '/actual-native-capture.json'
_EXECUTIONS03 = WeakKeyDictionary()


class _Execution:
    __slots__ = ('__weakref__',)
    __hash__ = object.__hash__
    __eq__ = object.__eq__


def _scope03(root, operation_id):
    # Reject another operation/root before archive or consumer-source I/O.
    need(operation_id == OPERATION03
         and os.path.normcase(str(Path(root).absolute())) == os.path.normcase(str(TARGET)),
         'fixed new03 operation and target before I/O')
    need(_plain(root).resolve() == TARGET, 'plain original target for new03 consumer')
    return str(Path(root).resolve())


def _consumer03():
    import _b_route_adoption_review as review
    expected = CONSUMER_SOURCE03 / 'scripts/python/_b_route_retained_execution.py'
    need(Path(__file__).absolute() == expected and _plain(expected).resolve() == expected,
         'actual R56 consumer source; no copied filename or reader alias')
    policy_source = CONSUMER_SOURCE03 / 'scripts/python/_b_route_adoption_review.py'
    policy = getattr(review, 'policy_identity_v3', None)
    need(Path(review.__file__).absolute() == policy_source
         and type(policy) is FunctionType
         and Path(policy.__code__.co_filename).absolute() == policy_source
         and policy.__globals__ is review.__dict__,
         'current R56 v3 policy owner, never default v2 or historical R52 consumer')
    return {'consumer_source_root': str(CONSUMER_SOURCE03),
            'consumer_rule': codec.raw_digest(_read(expected)),
            'consumer_policy_identity': policy()}


def authenticate_execution(root, *, operation_id, execution_ref):
    """Authenticate ONE old execution; issue no consumer Action or permission.

    No request/capsule/binding is needed here. The caller's original activity
    lease continues to protect origin metadata at capsule persistence.
    """
    resolved = _scope03(root, operation_id)
    need(execution_ref == EXECUTION_REF03, 'one fixed historical execution for new03')
    consumer = _consumer03()
    native, execution = _execution()  # Complete old archive, held chain, real R52 reader.
    need(_same(_consumer03(), consumer), 'consumer source/policy stable during authentication')
    token = _Execution()
    _EXECUTIONS03[token] = {'root': resolved, 'operation_id': operation_id,
        'native': native, 'execution': execution, 'consumer': consumer}
    return token


def _execution_token03(root, token, operation_id, *, replay=True):
    need(type(token) is _Execution and token in _EXECUTIONS03,
         'owner-issued authenticated execution token required')
    issued = _EXECUTIONS03[token]
    need(_scope03(root, operation_id) == issued['root']
         and operation_id == issued['operation_id'], 'execution token root/operation mismatch')
    need(_same(_consumer03(), issued['consumer']), 'authenticated consumer source/policy changed')
    if replay:
        native, execution = _execution()
        need(_same(native, issued['native']) and _same(execution, issued['execution']),
             'complete original execution/held identity changed')
        need(_same(_consumer03(), issued['consumer']), 'consumer changed during producer closing')
    return issued


def native_from_execution(root, token, *, operation_id):
    """Original producer value only; never a current consumer Action."""
    issued = _execution_token03(root, token, operation_id)
    return deepcopy(issued['native'])


def verify_producer_capture(root, native, *, operation_id, execution_token=None):
    """Named local producer bridge for every new03 capsule/Snapshot recheck.

    No-token verification authenticates the literal archive independently; a
    supplied capture/dict is never trusted. This path never consults or mints
    the current consumer Action, breaking the capsule -> request -> Action cycle.
    Other operations retain their original reader branch in the origin owner.
    """
    if execution_token is None:
        execution_token = authenticate_execution(root, operation_id=operation_id,
                                                  execution_ref=EXECUTION_REF03)
        issued = _execution_token03(root, execution_token, operation_id, replay=False)
    else:
        issued = _execution_token03(root, execution_token, operation_id)
    need(_same(native, issued['native']), 'whole new03 capture equals authenticated original archive')
    with _original_reader() as reader:
        need(native['source_identity']['reader_path'] == str(READER)
             and native['source_identity']['reader_raw_digest'] == 'sha256:' + READER_SHA,
             'original R52 producer path/raw identity; not current R56 reader')
        reader.verify_capture(ORIGIN, native)
    need(_same(_consumer03(), issued['consumer']), 'consumer stable after producer verification')
    return None


def prepare_retained_origin03(root, token, *, operation_id):
    """Original capsule producer/persistence, with no request or Action yet."""
    import _b_route_qualified_origin as origin
    from _b_route_adoption_review import write_once
    _execution_token03(root, token, operation_id)
    with origin.activity():
        value, native = origin.capture_value(root, operation_id, origin.PROFILE,
                                             _retained_execution=token)
        verify_producer_capture(root, native, operation_id=operation_id, execution_token=token)
        for name, expected in value['source_support'].items():
            original = _read(ORIGIN / name)
            need(codec.raw_digest(original) == expected, 'original synthetic provenance raw')
            write_once(root, name, original)
        ref = origin.capsule_path(operation_id)
        data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        write_once(root, ref, data)
        need(_read(_plain(Path(root) / ref)) == data, 'exact new03 derived capsule readback')
        origin.verify_capsule(root, value)
        _execution_token03(root, token, operation_id)
    return {'status': 'origin_captured', 'capsule_ref': {'path': ref,
        'schema_version': origin.CAPSULE, 'raw_digest': codec.raw_digest(data)},
        'execution_reused': True, 'new_native_executions': 0, 'model_dispatches': 0,
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False,
        'default_b_enabled': False, 'formal_story29_acceptance': False}


def _record03(root, operation_id):
    _scope03(root, operation_id)
    return _plain(TARGET / binding_path(operation_id), missing=True)


def _request03(root, operation_id):
    _scope03(root, operation_id)
    import _planning_apply_journal as journal
    raw = _read(TARGET / REQUEST03)
    request = journal.validate_operation_request(raw)
    need(request['operation_id'] == operation_id and 'host_review_ref' not in request,
         'new03 original unsealed request; no borrowed current/old review')
    need(request.get('review_profile') == 'expanded-semantics.v3',
         'new03 explicitly selects expanded-semantics.v3; no default-v2 consumer')
    need(request['material']['origin_profile'] == __import__('_b_route_qualified_origin').PROFILE,
         'original finite native profile in new consumer request')
    return request, codec.raw_digest(raw)


def _binding_value03(root, operation_id):
    # Authenticate producer independently of any capsule/request consumer grant.
    token = authenticate_execution(root, operation_id=operation_id, execution_ref=EXECUTION_REF03)
    request, request_raw_digest = _request03(root, operation_id)
    import _b_route_qualified_origin as origin
    expected_ref = origin.capsule_path(operation_id)
    need(request['review_ref'] == request['material']['handoff_ref']
         and request['review_ref']['path'] == expected_ref
         and request['review_ref']['schema_version'] == origin.CAPSULE,
         'new03 request references its own capsule, never old02 binding/subject')
    facts, capsule, native = _target_facts(root, request)
    need(capsule['operation_id'] == operation_id, 'new03 operation-owned capsule')
    verify_producer_capture(root, native, operation_id=operation_id, execution_token=token)
    issued = _execution_token03(root, token, operation_id, replay=False)
    consumer = issued['consumer']
    return {'schema_version': SCHEMA03, 'operation_id': operation_id, 'target_root': str(TARGET),
        'request_ref': REQUEST03, 'request_raw_digest': request_raw_digest,
        'request_body_digest': codec.canonical_digest(request), 'material': request['material'],
        'review_ref': request['review_ref'], 'execution': deepcopy(issued['execution']),
        'origin_capsule_digest': codec.canonical_digest(capsule), 'target_authority': facts,
        'consumer_source_root': consumer['consumer_source_root'],
        'consumer_rule': consumer['consumer_rule'],
        'consumer_policy_identity': consumer['consumer_policy_identity'],
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False}, native


def _admit03(root, *, operation_id, execution_ref):
    need(execution_ref == EXECUTION_REF03, 'one original execution ref for new03')
    import _b_route_qualified_origin as origin
    from _b_route_adoption_review import write_once, raw
    from _b_route_operation_scope import scope_guard, resource_scopes
    path = _record03(root, operation_id)
    with origin.activity():
        value, _ = _binding_value03(root, operation_id)
        def persist():
            fresh, _ = _binding_value03(root, operation_id)
            need(_same(fresh, value), 'new03 producer/request/consumer current under lease')
            write_once(root, binding_path(operation_id), raw(value))
            need(_same(codec.strict_json_loads(_read(path)), value), 'exact immutable new03 binding')
            return {'status': 'retained_execution_bound', 'support_ref': binding_path(operation_id),
                'support_raw_digest': codec.raw_digest(_read(path)), 'execution_reused': True,
                'new_native_executions': 0, 'formal_adoption': False}
        with scope_guard(root, resource_scopes(target_paths=[binding_path(operation_id)]),
                         operation_id=operation_id, prepare_under_lease=persist) as result:
            return result


def _capture_for_material03(root, *, operation_id, material, review_ref):
    path = _record03(root, operation_id)
    need(path.is_file(), 'new03 requires admitted current consumer binding; no fresh fallback')
    record_raw = _read(path)
    stored = codec.strict_json_loads(record_raw)
    actual, native = _binding_value03(root, operation_id)
    need(_same(stored, actual) and _same(material, stored['material'])
         and _same(review_ref, stored['review_ref']), 'same new03 request/consumer policy/target authority')
    token = _Action()
    _ISSUED[token] = {'root': str(Path(root).resolve()), 'operation_id': operation_id,
        'binding_raw': record_raw, 'binding': actual, 'native': native, 'building': False}
    return token


def _verify_action03(root, token, *, operation_id):
    need(type(token) is _Action and token in _ISSUED, 'owner-issued current new03 Action required')
    issued = _ISSUED[token]
    need(issued.get('building') is False and issued['root'] == _scope03(root, operation_id)
         and issued['operation_id'] == operation_id and issued['binding']['schema_version'] == SCHEMA03,
         'new03 Action exact consumer/root/operation')
    need(_read(_record03(root, operation_id)) == issued['binding_raw'], 'immutable new03 binding changed')
    verify_producer_capture(root, issued['native'], operation_id=operation_id)
    current, _ = _binding_value03(root, operation_id)
    need(_same(current, issued['binding']), 'new03 current request/source/authority drift')
