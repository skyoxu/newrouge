"""UNEXECUTED Root-only one-worker metadata driver; zero paid calls.

Only HOME/out is created. Existing held identity/exit helpers are reused;
the old supervisor's fixed paid main and its lane registration are not called.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
HOME = TASK / 'night-handoff/story23-metadata-role09-20261111'
OUT = HOME / 'out'
WORK = OUT / 'worker'
PYTHON = Path(r'C:\Program Files\Python312\python.exe')
GIT = Path(r'C:\Program Files\Git\mingw64\bin\git.exe')
HEAD = 'fe175b49e668551b175f8d5c53a91d6c53ef59f2'
H_FILE = TASK / 'night-handoff/story23-metadata-role09-20261111/review_prepare_host.classification.py'
H_PIN = '3f43a3c5a55ce37f9a94295cf5943972504b912d3fe24931efc8557fb7ff2459'
M_FILE = TASK / 'night-handoff/story23-segmented-paid-metadata-followup06-draft/segmented_paid_guard.Root-only.py'
M_PIN = '4507c6eb40b0bb4c09fb33f2954f75022de7416e87a89df13b07a602dbd4d18e'
CORE = TASK / 'night-handoff/story27-r52-native-persistent-supervision-draft-01/held_supervisor_core.py'
CORE_PIN = 'cd06568f6520f8ea7f337d46b76e1a13437f2fd2069c54fe51fb85e8ed2e33c0'
RUNTIME_PIN = 'a07402a2f838b534171e22757ec12a6d5be2accedeea966b5a136c86e2d01e0e'
DEPENDENCY_DATA = TASK / 'logs/ci/2026-11-09/story27-r56-zero03-review-prepare-seal-02/config.json'
DEPENDENCY_PIN = 'f294fae890df3cf4fcb52b9473ab43148d6f3d76703cf662f9e72bd24c3eb7d4'
SECRET = {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions', 'credentials', 's2', 'auth.json',
          'credentials.json', 'credentials.toml', 'id_rsa', 'id_ed25519'}


def need(ok, why):
    if not ok:
        raise RuntimeError('metadata_driver:' + why)


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path, missing=False):
    p = Path(path).absolute()
    need(not any(x.casefold() in SECRET or x.casefold().startswith('.env') for x in p.parts), 'no sensitive path')
    for item in reversed((p, *p.parents)):
        try:
            value = item.lstat()
        except FileNotFoundError:
            need(missing, 'missing actual file:' + str(item))
            continue
        need(not stat.S_ISLNK(value.st_mode) and not getattr(value, 'st_file_attributes', 0) & 0x400,
             'ordinary non-reparse actual path')
        need(stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode) and value.st_nlink == 1,
             'ordinary single-link actual input')
    return p


def read(path, pin=None):
    p = plain(path)
    before = p.stat()
    raw = p.read_bytes()
    after = p.stat()
    fields = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns, x.st_nlink)
    need(fields(before) == fields(after), 'actual control stable during read')
    need(pin is None or digest(raw) == pin, 'actual original control pin:' + str(p))
    return raw


def load(name, path, pin):
    raw = read(path, pin)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), module.__dict__)
    return module


def write(path, value):
    p = plain(path, missing=True)
    need(p.is_relative_to(OUT), 'only fresh own output')
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    with p.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def source_head():
    """Finite ordinary Git metadata reads only; no Git/config/process call."""
    p = TASK / 'r59/.git'
    git = p
    pins = {}
    if p.is_file():
        raw = read(p)
        pins[p] = digest(raw)
        text = raw.decode('utf-8').strip()
        need(text.startswith('gitdir: '), 'ordinary actual worktree gitdir')
        q = Path(text[8:])
        git = q if q.is_absolute() else (p.parent / q).absolute()
    raw = read(git / 'HEAD')
    pins[git / 'HEAD'] = digest(raw)
    value = raw.decode('ascii').strip()
    if value.startswith('ref: '):
        ref = value[5:]
        need(re.fullmatch(r'refs/heads/[A-Za-z0-9_./-]+', ref) is not None and '..' not in ref.split('/'), 'ordinary branch ref')
        common = git
        c = git / 'commondir'
        if c.exists():
            raw = read(c)
            pins[c] = digest(raw)
            q = Path(raw.decode('utf-8').strip())
            common = q if q.is_absolute() else (git / q).resolve(strict=True)
        locations = [git / ref, common / ref]
        found = next((x for x in locations if x.exists()), None)
        if found is not None:
            raw = read(found)
            pins[found] = digest(raw)
            value = raw.decode('ascii').strip()
        else:
            raw = read(common / 'packed-refs')
            pins[common / 'packed-refs'] = digest(raw)
            rows = [line.split() for line in raw.decode('ascii').splitlines() if line and line[0] not in '#^']
            matches = [row[0] for row in rows if len(row) == 2 and row[1] == ref]
            need(len(matches) == 1, 'actual branch ref present exactly once')
            value = matches[0]
    need(value == HEAD, 'actual selected R59 fe175 HEAD, no silent successor')
    return pins


def startup():
    need(os.name == 'nt' and Path.cwd() == TASK and Path(sys.executable).absolute() == PYTHON,
         'fixed ordinary Windows Python/cwd')
    need(sys.flags.dev_mode and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
         and not sys.flags.optimize, 'original dev isolated no-site no-bytecode flags')
    need(Path(__file__).absolute() == HOME / 'run_metadata.Root-only.py', 'real driver path')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetPriorityClass.argtypes = [ctypes.c_void_p]
    kernel.GetPriorityClass.restype = ctypes.c_ulong
    need(kernel.GetPriorityClass(kernel.GetCurrentProcess()) == 0x20, 'normal original process priority')


def arguments():
    parser = argparse.ArgumentParser(description='Root-only metadata, never paid or native')
    parser.add_argument('--host-sha256', required=True, help='actual reviewed new metadata_host control bytes')
    parser.add_argument('--driver-sha256', required=True, help='actual reviewed new driver control bytes')
    parser.add_argument('--run-id', required=True, help='observation ID only; no native run is created')
    parser.add_argument('--planner', choices=('capability', 'mvg'), required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    for value in (args.host_sha256, args.driver_sha256):
        need(re.fullmatch('[0-9a-f]{64}', value) is not None, 'real Root-reviewed control pin, never null')
    need(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_id) is not None and args.run_id not in {'c4', 'm4'},
         'fresh legal observation business ID')
    read(HOME / 'run_metadata.Root-only.py', args.driver_sha256)
    read(HOME / 'metadata_host.Root-only.py', args.host_sha256)
    return args


def worker(args):
    need(OUT.is_dir() and not WORK.exists(), 'one original supervisor-owned output, fresh worker output')
    WORK.mkdir(exist_ok=False)
    H = load('_Root_R23_H_classification09', H_FILE, H_PIN)
    metadata = load('_Root_R23_metadata06', M_FILE, M_PIN)
    adapter = load('_Root_R23_metadata_only_host', HOME / 'metadata_host.Root-only.py', args.host_sha256)
    H.SOURCE, H.TARGET = TASK / 'r59', TASK / 'nx'
    need(H.hash_file(H.PYTHON) == H.PYTHON_SHA and H.hash_file(H.GIT) == H.GIT_SHA, 'original fixed programs')
    controls = {H_FILE: H_PIN, M_FILE: M_PIN, CORE: CORE_PIN,
                HOME / 'metadata_host.Root-only.py': args.host_sha256,
                HOME / 'run_metadata.Root-only.py': args.driver_sha256,
                DEPENDENCY_DATA: DEPENDENCY_PIN,
                TASK / 'r59/scripts/python/_b_route_segmented_runtime.py': RUNTIME_PIN}
    controls.update(source_head())
    # The old JSON is only the existing dependency DATA provenance. No source,
    # target, 208 controls, financial, request or public admission is consumed.
    dependency = json.loads(read(DEPENDENCY_DATA, DEPENDENCY_PIN))
    dependencies = [TASK / 'story22-tokenizer-deps',
                    Path(r'C:\Users\Administrator\Documents\Codex\2026-11-04\task-2\python-env\Lib\site-packages'),
                    Path(r'C:\Program Files\Python312\Lib\site-packages')]
    imports = [H.SOURCE / 'scripts/python', H.SOURCE / 'scripts/sc', *dependencies]
    Guard = adapter.make_metadata_guard(H, metadata)  # capture real run before install
    guard = Guard(WORK, dependency_files=dependency['dependency_files'],
                  dependency_members=dependency['dependency_members'], import_paths=imports, control_pins=controls)
    result = {'utc': utc(), 'passed': False, 'source_commit': HEAD, 'planner': args.planner,
              'run_id': args.run_id, 'new_project_model_calls': 0, 'claim_or_birth_requested': False,
              'paid_guard_composition_verified': False, 'formal_segmentation_acceptance': False,
              'paid_or_unknown': 83, 'overlapping_guard_occupancy': 181, 'campaign_limit': 290, 'released': 0}
    primary = None
    close_error = None
    children_closed = False
    try:
        guard.install()
        inventory = H.importlib.import_module('_b_route_inventory')
        runtime = H.importlib.import_module('_b_route_segmented_runtime')
        transition = H.importlib.import_module('_b_route_execution_transition')
        common = H.importlib.import_module('_planning_skill_common')
        sources = H.importlib.import_module('_b_route_sources')
        native = H.importlib.import_module('build_source_ledger')
        codec = H.importlib.import_module('_b_route_codec')
        schemas = H.importlib.import_module('_b_route_schema_resources')
        workflow = H.importlib.import_module('_b_route_segmented_workflow')
        guard.inventory = inventory
        guard.bind_metadata_sources(runtime, transition, common, root=H.TARGET, run_id=args.run_id,
                                    planner=args.planner, planning_contract=adapter.CONTRACT)
        guard.bind_input_owners(sources, native, inventory, codec, schemas, workflow)
        source = runtime.capture_source(H.TARGET, run_id=args.run_id, planner=args.planner,
                                        planning_contract=adapter.CONTRACT, semantic_catalog_ref=None)
        verifier = source['source_identity']['audit_verifier_source']
        need(verifier['root'] == str(adapter.PRESERVED) and verifier['commit'] == runtime._PRESERVED_COMMIT
             and len(verifier['manifest']) == 486, 'original real full486 manifest/currentness retained')
        description = runtime._describe(H.TARGET, source)
        runtime.verify_candidate_context(H.TARGET, source)
        children_closed = True
        rows = guard.close_children()
        need(len(rows) == len(guard.describe_rows) == 1 and not guard.runner_rows and not guard.cleanup_rows,
             'exactly one real zero-model describe child; zero paid/cleanup')
        need(all(row['terminal_known'] and row['actual_original_held_OS_exit'] == 0
                 and row['actual_handle_closed'] and not row['terminal_errors']
                 and row['Popen_audit'] and row['CreateProcess_audit'] for row in rows), 'actual describe dual audit/held OS0 close')
        need(guard.metadata_records and all(row['terminal_known'] and row['actual_original_held_OS_exit'] == 0
                 and row['actual_handle_closed'] and not row['terminal_errors']
                 and row['Popen_audit'] and row['CreateProcess_audit'] for row in guard.metadata_records),
             'actual original metadata dual audit and terminal close')
        closure = guard.close_inputs()
        H.write_new(WORK / 'description.json', H.raw_json(description))
        H.write_new(WORK / 'input-close.json', H.raw_json(closure))
        result.update(passed=True, metadata_only_guard_composition_verified=True,
                      original_metadata_children=len(guard.metadata_records), original_r5_manifest_count=486,
                      describe_children=rows, blocked=guard.blocked, no_target_write_role_observed=True)
    except BaseException as error:
        primary = error
        result.update(error=type(error).__name__ + ':' + str(error), blocked=guard.blocked)
        frames = []
        trace = error.__traceback__
        while trace is not None and len(frames) < 64:
            frame = trace.tb_frame
            frames.append({'filename': frame.f_code.co_filename, 'function': frame.f_code.co_name,
                           'line': trace.tb_lineno, 'module': frame.f_globals.get('__name__')})
            trace = trace.tb_next
        result.update(error_frames=frames, error_frames_truncated=trace is not None,
                      enumeration_refusals=guard.enumeration_refusals,
                      enumeration_diagnostic_errors=guard.enumeration_diagnostic_errors)
    finally:
        if not children_closed:
            try:
                # Exactly one close attempt for each actual describe child.
                children_closed = True
                result['failure_child_close'] = guard.close_children()
            except BaseException as error:
                close_error = error
                result['close_error'] = repr(error)
        result['passed'] = bool(result['passed'] and primary is None and close_error is None)
        H.write_new(WORK / 'result.json', H.raw_json(result))
    return 0 if result['passed'] else 1


def supervise(args):
    C = load('_Root_R23_original_held_helpers', CORE, CORE_PIN)
    need(C.sha(C.read(PYTHON)) == C.PYTHON_SHA, 'fixed original Python raw before worker launch')
    need(not OUT.exists(), 'exclusive new output; never restart/overwrite an attempt')
    OUT.mkdir(exist_ok=False)
    os_keys = ('SystemRoot', 'WINDIR', 'SystemDrive', 'TEMP', 'TMP', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS')
    env = {k: os.environ[k] for k in os_keys if k in os.environ}
    env.update(NEWROGUE_CODEX_REASONING_EFFORT='high', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
               PATH=os.pathsep.join((str(GIT.parent),str(PYTHON.parent),r'C:\Users\Administrator\AppData\Roaming\npm')), PATHEXT='.EXE;.CMD',
               TIKTOKEN_CACHE_DIR=str(TASK / 'story22-tokenizer-cache'),
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_COUNT='0', GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    limit = os.environ.get('SC_CAPABILITY_MAX_INPUT_TOKENS')
    need(limit in (None, '70000', '96000'), 'original finite inherited input limit')
    if limit is not None:
        env['SC_CAPABILITY_MAX_INPUT_TOKENS'] = limit
    argv = [str(PYTHON), '-X', 'dev', '-I', '-S', '-B', str(HOME / 'run_metadata.Root-only.py'),
            '--host-sha256', args.host_sha256, '--driver-sha256', args.driver_sha256,
            '--run-id', args.run_id, '--planner', args.planner, '--worker']
    write(OUT / 'started.json', {'utc': utc(), 'argv': argv, 'new_project_model_calls_allowed': 0,
                              'claim_or_birth_requested': False, 'automatic_retry': False})
    process = None
    pre = post = None
    code = raw_exit = None
    errors = []
    known = closed = False
    with (OUT / 'worker-stdout.bin').open('xb') as stdout, (OUT / 'worker-stderr.bin').open('xb') as stderr:
        try:
            process = subprocess.Popen(argv, cwd=TASK, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       env=env, creationflags=subprocess.CREATE_NO_WINDOW)
            pre = C.identity(int(process._handle), process.pid)
            need(pre['image'] is not None and Path(pre['image']) == PYTHON and pre['birth_filetime'] > 0,
                 'actual original worker image/birth')
            code = process.wait()
        except BaseException as error:
            errors.append(repr(error))
        finally:
            if process is not None:
                if process.returncode is None:
                    try:
                        code = process.wait()
                    except BaseException as error:
                        errors.append('wait:' + repr(error))
                try:
                    post = C.identity(int(process._handle), process.pid)
                    need(pre is not None and all(post[k] == pre[k] for k in ('pid', 'held_handle', 'birth_filetime')),
                         'same original held worker')
                    if post['image'] is not None:
                        need(Path(post['image']) == PYTHON, 'available original post image')
                    raw_exit = C.exit_value(int(process._handle))
                    known = type(code) is int and raw_exit != 259 and raw_exit == code
                except BaseException as error:
                    errors.append('terminal:' + repr(error))
                finally:
                    try:
                        process._handle.Close()
                        closed = True
                    except BaseException as error:
                        errors.append('Close:' + repr(error))
    result = WORK / 'result.json'
    unit = json.loads(read(result)) if result.exists() else None
    passed = bool(known and closed and code == 0 and not errors and unit and unit['passed'])
    write(OUT / 'result.json', {'utc': utc(), 'passed': passed, 'original_pre_identity': pre,
                              'original_post_identity': post, 'actual_child_OS_exit': code,
                              'raw_GetExitCodeProcess_value': raw_exit, 'terminal_known': known,
                              'actual_handle_closed': closed, 'errors': errors, 'unit_present': unit is not None,
                              'automatic_retry': False, 'new_project_model_calls': 0,
                              'formal_segmentation_acceptance': False, 'released': 0})
    return 0 if passed else 1


def main():
    startup()
    args = arguments()
    return worker(args) if args.worker else supervise(args)


if __name__ == '__main__':
    raise SystemExit(main())
