"""Root-only original public review-prepare with real original reader and readonly target Git."""
import argparse
import contextlib
import io
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import errno
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.resources.abc
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import traceback
import types

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
HOME = TASK / 'night-handoff/story27-r52-public-review-prepare-host-followup02'
SOURCE = TASK / 'r52'
ORIGIN = TASK / 'nx'
PYTHON = Path(r'C:\Program Files\Python312\python.exe')
PYTHON_SHA = '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a'
GIT = Path(r'C:\Program Files\Git\mingw64\bin\git.exe')
GIT_SHA = 'cab4c4eea1d869cf9f7be73868dc9a90ad2df1b1b673e5f8c8714a576c25ea96'
GIT_FILE_ID = [13874145219238003830, 562949953467635]
GIT_BYTES = 4422544
READER = SOURCE / 'scripts/python/_b_route_frozen_native_reader.py'
READER_SHA = '3c2b2c614082c3dcd04f5ac4866e0152fa93e4dc19ac5487853cef6731f41548'
MODEL_CATALOG = b'{"models":[{"slug":"offline-native-replay-metadata-only"}]}\n'
SECRETS = {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions', 'credentials',
           'auth.json', 'credentials.json', 'credentials.toml', 'id_rsa', 'id_ed25519'}
_OPEN, _LSTAT, _SCANDIR = open, os.lstat, os.scandir
_OS_OPEN, _FDOPEN, _OS_CLOSE = os.open, os.fdopen, os.close
ISOLATED_STARTUP_PATHS = tuple(sys.path)
POPEN = subprocess.Popen
INIT, EXECUTE, GET_HANDLES = POPEN.__init__, POPEN._execute_child, POPEN._get_handles


class Denied(RuntimeError):
    pass


def require(ok, why):
    if not ok:
        raise Denied(why)


def key(path):
    require(not isinstance(path, int), 'unowned descriptor')
    text = os.fsdecode(os.fspath(path))
    if text.startswith('\\\\?\\'):
        text = text[4:]
    drive, tail = ntpath.splitdrive(text)
    require(len(drive) == 2 and drive[1] == ':' and tail.startswith(('\\', '/'))
            and ':' not in tail and '\x00' not in text, 'ordinary absolute drive path')
    result = ntpath.normcase(ntpath.normpath(text))
    require(not any(part.casefold() in SECRETS or part.casefold().startswith('.env') for part in Path(result).parts),
            'secret/session path refused')
    return result


def plain(path, missing=False):
    path = Path(key(path))
    for part in reversed((path, *path.parents)):
        try:
            info = _LSTAT(part)
        except FileNotFoundError:
            require(missing, 'missing:' + str(part))
            continue
        require(not stat.S_ISLNK(info.st_mode) and not info.st_file_attributes & 0x400,
                'reparse:' + str(part))
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                'nonordinary/aliased:' + str(part))
    return path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def read(path):
    with _OPEN(plain(path), 'rb') as stream:
        return stream.read()


def hash_file(path):
    if key(path) == key(GIT):
        return git_program_hash()
    before = plain(path).stat()
    value = digest(read(path))
    after = plain(path).stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink), 'file drift while hashing')
    return value


def file_identity(path):
    value = git_program_metadata().stat() if key(path) == key(GIT) else plain(path).stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink]


def git_program_metadata():
    """One installed Git role only; plain() remains single-link everywhere."""
    path = GIT
    for ancestor in reversed(path.parents):
        plain(ancestor)
    resolved = path.resolve(strict=True)
    require(resolved == path and not resolved.is_relative_to(TASK.resolve(strict=True)), 'fixed Git reverse alias')
    info = _LSTAT(path)
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not info.st_file_attributes & 0x400 and info.st_nlink == 4
            and info.st_size == GIT_BYTES and [info.st_dev, info.st_ino] == GIT_FILE_ID,
            'exact installed Git metadata')
    return path


def git_program_hash():
    path = git_program_metadata()
    first = path.stat()
    before = [first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns, first.st_ctime_ns, first.st_nlink]
    with _OPEN(path, 'rb') as stream:
        value = digest(stream.read())
    last = git_program_metadata().stat()
    require(before == [last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns, last.st_ctime_ns, last.st_nlink]
            and value == GIT_SHA, 'installed Git stable exact raw hash')
    return value


def members(path, validate_children=True):
    with _SCANDIR(plain(path)) as entries:
        values = []
        for entry in entries:
            if validate_children:
                plain(entry.path)
            values.append(entry.name)
    require(len({n.casefold() for n in values}) == len(values), 'case alias')
    return sorted(values)


def write_new(path, raw):
    path = plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _OPEN(path, 'xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def held(process):
    handle = int(process._handle)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    times = kernel.GetProcessTimes
    times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    times.restype = wintypes.BOOL
    values = [wintypes.FILETIME() for _ in range(4)]
    require(times(wintypes.HANDLE(handle), *(ctypes.byref(v) for v in values)), 'original held birth unavailable')
    born = values[0].dwHighDateTime << 32 | values[0].dwLowDateTime
    query = kernel.QueryFullProcessImageNameW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
    ok = query(wintypes.HANDLE(handle), 0, buffer, ctypes.byref(length))
    return {'pid': process.pid, 'held_handle': handle, 'birth_filetime': born,
            'image': buffer.value if ok else None, 'image_error': None if ok else ctypes.get_last_error()}


class Resources(importlib.resources.abc.TraversableResources):
    def __init__(self, path):
        self.path = Path(path)

    def files(self):
        return self.path


class Loader(importlib.machinery.SourceFileLoader):
    def __init__(self, guard, fullname, path):
        self.guard = guard
        super().__init__(fullname, path)

    def get_code(self, fullname):
        raw = self.guard.code_bytes(self.path)
        return compile(raw, self.path, 'exec', dont_inherit=True, optimize=0)

    def get_resource_reader(self, fullname):
        return Resources(Path(self.path).parent) if Path(self.path).name == '__init__.py' else None


class Finder:
    def __init__(self, guard):
        self.guard = guard

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None:
            return None
        if isinstance(spec.loader, importlib.machinery.SourcelessFileLoader):
            self.guard.deny('sourceless import', spec.origin)
        if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            self.guard.check_code_path(spec.origin)
            spec.loader = Loader(self.guard, fullname, spec.origin)
            return spec
        if isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            self.guard.code_bytes(spec.origin)
        return spec



HEAD = 'd1ceabeabe43bc4c2318fa0d5a3a4fe5ba25302b'

BASELINE = 'f6b023e8c4b5fda74965973762ced21fd8b1eadb'

TARGET = TASK / 'story27-r52-v15-empty-target-native01'
REQUEST = 'logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-01/request.json'
OPERATION = 'NativeV15Origin02'
REVIEW_HOME = 'logs/ci/b-route-adoption-reviews/' + hashlib.sha256(OPERATION.encode()).hexdigest()
REVIEW_FILES = tuple(REVIEW_HOME + '/' + name for name in ('subject.json','w/prompt.txt','w/schema.json','request.txt'))
PUBLIC_DIRECTORIES = ('logs','logs/ci','logs/ci/b-route-operations','logs/ci/b-route-operations/locks','logs/ci/b-route-operations/locks/metadata','logs/ci/b-route-operations/locks/scopes','logs/ci/b-route-adoption-reviews',REVIEW_HOME,REVIEW_HOME+'/w')

def original_frame(module_name, function_name):
    module = sys.modules.get(module_name)
    owner = getattr(module, function_name, None)
    require(owner is not None and isinstance(getattr(module, '__loader__', None), Loader), 'actual SourceOnly owner')
    frame = sys._getframe(1)
    while frame:
        if frame.f_code is owner.__code__ and frame.f_globals is module.__dict__:
            return frame
        frame = frame.f_back
    return None


def snapshot_tree(root, *, omit=()):
    """Exact ordinary file/raw/identity and complete directory-member closure."""
    root = plain(root)
    files, dirs = {}, {}
    pending = [root]
    omit = {key(p) for p in omit}
    while pending:
        base = plain(pending.pop())
        rows = []
        with _SCANDIR(base) as entries:
            for entry in entries:
                path = plain(entry.path)
                if key(path) in omit:
                    continue
                rows.append(entry.name)
                if path.is_dir():
                    pending.append(path)
                else:
                    before = file_identity(path)
                    files[path.relative_to(root).as_posix()] = {'sha256': hash_file(path), 'identity': before}
                    require(file_identity(path) == before, 'stable tree file identity')
        require(len({name.casefold() for name in rows}) == len(rows), 'tree case aliases')
        dirs[base.relative_to(root).as_posix()] = {'identity': list(file_identity(base)[:2]), 'members': sorted(rows)}
        require(len(files) <= 12000 and len(dirs) <= 12000, 'finite target/Git metadata bound')
    return {'files': files, 'directories': dirs}


def metadata_names(path):
    path = plain(path, missing=True)
    if not path.exists():
        return None
    require(path.is_dir(), 'metadata directory only')
    return {'identity': list(file_identity(path)[:2]), 'members': members(path, validate_children=False)}


def startup_metadata():
    allowed = {key(PYTHON.parent / name) for name in ('Lib', 'DLLs', 'python312.zip')} | {key(PYTHON.parent)}
    require(ISOLATED_STARTUP_PATHS and all(key(p) in allowed for p in ISOLATED_STARTUP_PATHS), 'official isolated startup paths')
    result = {}
    for value in ISOLATED_STARTUP_PATHS:
        p = plain(value, missing=True)
        result[value] = None if not p.exists() else ({'directory': file_identity(p)[:2]} if p.is_dir()
            else {'file': file_identity(p), 'sha256': hash_file(p)})
    return result


def source_close(config):
    source = config['source_files']
    for name, pin in source.items():
        require(hash_file(SOURCE / name) == pin, 'source raw drift:' + name)
    for name, row in config['source_full_directories'].items():
        require(metadata_names(SOURCE / name) == row, 'source full member/identity drift')
    for name, pin in config['schema_dependency_files'].items():
        require(hash_file(name) == pin, 'schema dependency raw drift')
    for name, row in config['import_metadata'].items():
        require(metadata_names(name) == row, 'finite import directory drift')
    require(startup_metadata() == config['protection_stdlib_search_metadata'], 'official isolated startup metadata drift')
    require(hash_file(PYTHON) == PYTHON_SHA and hash_file(GIT) == GIT_SHA, 'fixed program raw')
    require(file_identity(PYTHON) == config['program_identities']['Python']
            and file_identity(GIT) == config['program_identities']['Git'], 'fixed program identity')


class Guard:
    def __init__(self, config, out):
        self.c, self.out = config, Path(out)
        self.target = Path(config['target'])
        self.files = {key(SOURCE / name): pin for name, pin in config['source_files'].items()}
        self.code_files = set(self.files)
        self.files.update({key(name): row['sha256'] for name, row in config['dependency_files'].items()})
        self.code_files.update(key(name) for name in config['dependency_files'])
        self.directories = {key(SOURCE / name): row for name, row in config['source_full_members'].items()}
        self.directories.update({key(name): row for name, row in config['dependency_members'].items()})
        self.fixed = dict(config['fixed_original_reads'])
        self.files.update({key(path): value for path, value in self.fixed.items()})
        self.files.update({key(self.target / name): row['sha256'] for name, row in config['target_files'].items()})
        self.directories.update({key(self.target / name): row for name, row in config['target_directories'].items()})
        self.extra_files, self.extra_dirs, self.absences = {}, {}, {}
        self.metadata_directories = {key(name): row for name, row in config['metadata_ancestor_members'].items()}
        self.codec_fds = {}
        self.codec_fd_events = []
        self.locks = {key(path) for path in config['lock_paths']}
        self.write_targets = {key(self.target / name) for name in config['target_write_paths']}
        self.lock_parents = {key(Path(path).parent) for path in self.locks}
        self.lock_events, self.blocked, self.children, self.transport_events = [], [], [], []
        self.lock_descriptors = {}
        self.target_complete = False
        self.new_target_pins = {}
        self.nonce, self.ack = digest(os.urandom(32)), None
        self.active = self.token = None
        self.transport_calls = 0
        self.job_observations = {'assign_success': 0, 'active_queries': 0, 'last_active': None,
                                 'zero_observed': False, 'close_success': 0, 'errors': []}

        self.git_children, self.git_records, self.git_intents = [], [], []
        self.known_commits = {HEAD, BASELINE}
        self.known_objects = {HEAD: 'commit', BASELINE: 'commit'}
        self.inventory = None
        self.original_nx_locks = set(self.locks)
        self.target_scope_locks = set()
        self.public_scope_ids, self.completed_lock_rows = [], []
        self.public_scope_frame = None
        self.public_scope_admitted = False
        self.review_files = {key(self.target / name) for name in REVIEW_FILES}
        self.public_directories = {key(self.target / name) for name in PUBLIC_DIRECTORIES}
        self.absent_target_files = {key(self.target / name) for name in config['absent_target_files']}
        self.absent_target_directories = {key(self.target / name) for name in config['absent_target_directories']}

    def deny(self, role, value):
        if len(self.blocked) < 256:
            self.blocked.append({'role': role, 'value': str(value)})
        raise Denied(role + ':' + str(value))


    def runtime(self, path):
        parts = {p.casefold() for p in Path(path).parts}
        if {'site-packages', 'dist-packages'} & parts:
            return False
        root = key(PYTHON.parent)
        return (path in {root + '\\lib', root + '\\dlls'} or path.startswith(root + '\\lib\\') or path.startswith(root + '\\dlls\\')
                or path in {key(PYTHON), key(PYTHON.parent / 'python312.zip'), root}
                or ntpath.dirname(path) == root and path.endswith('.dll'))


    def original_codec_frame(self):
        module = sys.modules.get('_b_route_codec')
        owner = getattr(module, 'read_reference_bytes', None)
        frame = sys._getframe(1)
        while frame:
            if (owner is not None and isinstance(getattr(module, '__loader__', None), Loader)
                    and frame.f_code is owner.__code__
                    and key(frame.f_code.co_filename) == key(SOURCE / 'scripts/python/_b_route_codec.py')):
                return frame
            frame = frame.f_back
        return None


    def codec_fd_open(self, fd, mode, flags):
        row = self.codec_fds.get(fd)
        frame = self.original_codec_frame()
        caller = sys._getframe(1)
        while caller and caller.f_code is not _FDOPEN.__code__:
            caller = caller.f_back
        require(row is not None and frame is not None and caller is not None
                and caller.f_locals.get('fd') == fd and caller.f_locals.get('mode') == 'rb'
                and caller.f_locals.get('buffering') == 0 and caller.f_locals.get('encoding') is None
                and caller.f_locals.get('args') == () and caller.f_locals.get('kwargs') == {}
                and mode in ('r', 'rb') and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                and row['frame'] is frame and not row['fdopen_admitted'], 'owned original codec readonly fdopen')
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and self.fd_identity(info) == row['identity'], 'codec descriptor identity before fdopen')
        row['fdopen_admitted'] = True
        self.codec_fd_events.append({'path': row['path'], 'fd': fd, 'event': 'original codec fdopen', 'identity': row['identity']})
        return True


    @staticmethod
    def fd_identity(info):
        require(type(getattr(info, 'st_birthtime_ns', None)) is int, 'Windows descriptor birthtime must be observed')
        return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_birthtime_ns, info.st_nlink]


    def code_bytes(self, path):
        name = key(path)
        self.check_code_path(name)
        raw = read(name)
        if name in self.files:
            require(digest(raw) == self.files[name], 'source/dependency pin at import')
        return raw


    def check_code_path(self, path):
        name = key(path)
        if name.endswith(('.pyc', '.pyo')) or not (name in self.code_files or self.runtime(name)):
            self.deny('source-only exact code closure', name)


    def coordinator_frame(self, name):
        module_name = '_mvg_capability_checkpoint' if name == 'coordinator_lock' else '_mvg_capability_recovery'
        module = sys.modules.get(module_name)
        owner = getattr(module, name, None)
        function = getattr(owner, '__wrapped__', owner)
        code = getattr(function, '__code__', None)
        if code is None or not isinstance(getattr(module, '__loader__', None), Loader):
            return None
        frame = sys._getframe(1)
        while frame:
            if (frame.f_code is code and key(frame.f_code.co_filename) == key(SOURCE / 'scripts/python' /
                    ('_mvg_capability_checkpoint.py' if name == 'coordinator_lock' else '_mvg_capability_recovery.py'))):
                return frame
            frame = frame.f_back
        return None


    def allowed_read(self, path):
        name = key(path)
        if name.endswith(('.pyc', '.pyo')):
            self.deny('bytecode read', name)
        if (name in self.files or name in self.extra_files or name in self.write_targets
                or self.runtime(name) or Path(name).is_relative_to(self.out)):
            return
        if name in self.absent_target_files and not Path(name).exists():
            return
        if name in self.locks and self.coordinator_frame('coordinator_lock'):
            return
        self.deny('read outside fixed or authenticated positive closure', name)


    def allowed_write(self, path, mkdir=False, flags=None):
        name = key(plain(path, missing=True))
        if Path(name).is_relative_to(self.out):
            return
        frame = self.coordinator_frame('coordinator_lock')
        if name in self.locks and frame and key(frame.f_locals['path']) == name:
            self.lock_events.append({'path': name, 'role': 'original coordinator_lock open/write', 'thread': threading.get_ident()})
            return
        frame = self.coordinator_frame('operation_lock')
        if mkdir and name in self.lock_parents and frame and key(frame.f_locals['directory']) == name:
            self.lock_events.append({'path': name, 'role': 'original operation_lock activity directory'})
            return
        if mkdir and name in self.public_directories:
            scope = self.original_frame('_b_route_operation_scope', '_directory')
            review = self.original_frame('_b_route_adoption_review', 'write_once')
            require(scope is not None or review is not None, 'public mkdir only original finite namespace owner')
            return
        if name in self.review_files:
            frame = self.original_frame('_b_route_adoption_review', 'write_once')
            require(frame is not None and key(frame.f_locals['target']) == name
                    and not Path(name).exists() and type(flags) is int
                    and bool(flags & os.O_EXCL) and bool(flags & os.O_CREAT), 'exact four original create-once review files')
            return
        self.deny('write outside new review files / original nx or source-derived scope locks', name)


    def pipe_open(self, fd):
        token = self.token
        if type(fd) is not int or token is None or not token.get('constructing'):
            return False
        import msvcrt
        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
            return False
        handle = msvcrt.get_osfhandle(fd)
        if handle not in token['fresh_pipe_handles'] or handle in token['used_pipe_handles']:
            return False
        token['used_pipe_handles'].add(handle)
        return True


    def assert_active(self):
        self.ack = None
        sys.audit('Root.native.reader.guard', self.nonce)
        require(self.ack == self.nonce and self.finder in sys.meta_path and sys.getprofile() is self.profile_role
                and POPEN.__init__ is self.guarded_init and POPEN._get_handles is self.guarded_handles
                and POPEN._execute_child is EXECUTE and subprocess.Popen is POPEN
                and os.open is self.guarded_os_open and os.fdopen is _FDOPEN, 'installed actual guard/source/constructor/FD references')
        require(not self.blocked, 'a previous refusal remains fatal')

        require(subprocess.run == self.run_git, 'same original typed Git dispatcher')

    def role(self, frame, event, arg):
        if event != 'call' or frame.f_code.co_filename.startswith('<'):
            return
        if not Path(key(frame.f_code.co_filename)).is_relative_to(SOURCE):
            return
        module, name = Path(frame.f_code.co_filename).name, frame.f_code.co_name
        if module == '_b_route_operation_scope.py' and name == 'scope_guard':
            if frame is self.public_scope_frame:
                return  # Resume of this exact original context-manager frame.
            owner = sys.modules.get('_b_route_operation_scope')
            function = getattr(getattr(owner, 'scope_guard', None), '__wrapped__', None)
            require(isinstance(getattr(owner, '__loader__', None), Loader) and function is not None
                    and frame.f_code is function.__code__ and frame.f_globals is owner.__dict__, 'original scope_guard binding')
            require(key(frame.f_locals['root']) == key(TARGET)
                    and frame.f_locals['operation_id'] == 'NativeV15Origin02'
                    and frame.f_locals['legacy_owner'] is None, 'same actual public review scope call')
            parent = frame.f_back
            module_owner = sys.modules.get('_b_route_adoption')
            while parent and not (parent.f_globals is module_owner.__dict__
                                 and parent.f_code is module_owner._review_preview.__code__):
                parent = parent.f_back
            require(parent is not None and parent.f_locals['seal'] is False, 'actual review-prepare preview parent')
            scopes = frame.f_locals['scope_ids']
            require(scopes == parent.f_locals['frozen']['scope_ids']
                    and isinstance(scopes, (list, tuple)) and scopes
                    and all(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9._:-]{0,127}', value)
                            and value != 'writer:planning' for value in scopes), 'actual frozen portable scope denominator')
            paths = {TARGET / 'logs/ci/b-route-operations/locks/metadata/capability-coordinator.lock'}
            for scope in (*scopes, 'writer:planning'):
                paths.add(TARGET / 'logs/ci/b-route-operations/locks/scopes' /
                          hashlib.sha256(scope.encode('utf-8')).hexdigest() / 'capability-coordinator.lock')
            require(not self.public_scope_admitted, 'one original public scope_guard invocation')
            self.public_scope_admitted = True
            self.public_scope_frame = frame
            self.public_scope_ids = list(scopes)
            for path in paths:
                name = key(path)
                require(not path.exists(), 'new original public lock; do not reuse old namespace')
                self.target_scope_locks.add(name)
                self.locks.add(name)
                self.write_targets.add(name)
                self.public_directories.add(key(path.parent))
            return
        if module in {'_codex_app_server.py', '_llm_backend.py'} and name in {'run_request', 'call_llm', 'chat'}:
            self.deny('actual model dispatch', [module, name])
        if name == 'prepare_review' and module == '_b_route_adoption.py':
            owner = sys.modules.get('_b_route_adoption')
            function = getattr(getattr(owner, name, None), '__wrapped__', None)
            require(isinstance(getattr(owner, '__loader__', None), Loader) and function is not None
                    and frame.f_code is function.__code__ and frame.f_globals is owner.__dict__
                    and key(frame.f_locals['root']) == key(TARGET)
                    and frame.f_locals['operation_id'] == 'NativeV15Origin02'
                    and frame.f_locals['request_ref'] == REQUEST, 'one actual original public prepare_review call')
            return
        if name in {'run_candidate', 'prepare_review', 'complete_review', 'run_native', 'produce_proof', 'prepare_origin'}:
            self.deny('other planning/model/commit/origin stage', [module, name])


    def admit_capture(self, value, globals_):
        require(set(value) == globals_['_RESULT_FIELDS'] and value['schema_version'] == globals_['SCHEMA'], 'reader result shape')
        require(value['result_digest'] == globals_['digest'](globals_['canonical']({k: v for k, v in value.items() if k != 'result_digest'})),
                'actual reader result digest')
        source = value['source_identity']
        require(source == {'source_root': str(TASK / 'r22'), 'source_commit': '6d4ab1c3cba67bebe98f75c9462af613bf9d739a',
            'reader_path': str(READER), 'reader_raw_digest': 'sha256:' + READER_SHA}, 'actual R22 source/reader identity')
        require(value['run_identity']['path'] == str(ORIGIN / 'logs/ci/mvg-planning/m4/run.json')
                and value['run_identity']['raw_digest'] == self.c['run_digest'], 'actual original nx/m4 run')
        for name, pin in value['files'].items():
            require(pin is None or type(pin) is str and re.fullmatch('sha256:[0-9a-f]{64}', pin), 'capture file pin shape')
            name = key(name)
            require(name not in self.extra_files or self.extra_files[name] == pin, 'capture file inconsistency')
            self.extra_files[name] = pin
        for name, listing in value['directories'].items():
            require(type(listing) is list and listing == sorted(set(listing)), 'capture directory shape')
            self.extra_dirs[key(name)] = listing
        write_new(self.out / 'actual-native-capture.json', raw_json(value))


    def install(self):
        guard = self
        self.finder = Finder(self)
        sys.meta_path.insert(0, self.finder)
        # Same prepend policy as the actually closed focused17 host. Preserve
        # the official isolated startup search instead of discarding stdlib.
        require(list(ISOLATED_STARTUP_PATHS) == self.c['isolated_startup_paths'], 'same official isolated startup paths')
        sys.path[:] = self.c['parent_import_paths'] + list(ISOLATED_STARTUP_PATHS)
        sys.dont_write_bytecode = True

        def opened(path, flags, mode=0o777, *, dir_fd=None):
            frame = guard.original_codec_frame()
            if frame is None or sys._getframe(1) is not frame:
                return _OS_OPEN(path, flags, mode, dir_fd=dir_fd)
            expected = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
            require(flags == expected and dir_fd is None and key(path) == key(frame.f_locals['resolved']), 'original codec exact os.open')
            guard.allowed_read(path)
            before = plain(path).stat()
            descriptor = _OS_OPEN(path, flags, mode)
            try:
                info = os.fstat(descriptor)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        and guard.fd_identity(info) == guard.fd_identity(before), 'actual codec opened file identity')
                require(descriptor not in guard.codec_fds, 'no live codec descriptor reuse')
                guard.codec_fds[descriptor] = {'path': key(path), 'identity': guard.fd_identity(info),
                    'frame': frame, 'fdopen_admitted': False}
                return descriptor
            except BaseException:
                _OS_CLOSE(descriptor)
                raise

        def returned(frame, event, arg):
            # Profile return happens after the original with/fdopen close. No
            # fabricated close and no binding survives the original frame.
            guard.role(frame, event, arg)
            if event == 'return':
                for descriptor, row in list(guard.codec_fds.items()):
                    if row['frame'] is frame:
                        closed = False
                        close_error = None
                        try:
                            os.fstat(descriptor)
                        except OSError as error:
                            closed = True if error.errno == errno.EBADF else None
                            close_error = {'type': type(error).__name__, 'errno': error.errno}
                        guard.codec_fd_events.append({'path': row['path'], 'fd': descriptor,
                            'event': 'original codec returned', 'fdopen_admitted': row['fdopen_admitted'],
                            'actual_closed': closed, 'fstat_error': close_error})
                        if closed is True:
                            del guard.codec_fds[descriptor]
                        require(closed is True and row['fdopen_admitted'], 'original codec descriptor closed before return; unknown retained')

        self.profile_role = returned
        self.guarded_os_open = opened
        os.open = opened

        def handles(process, stdin, stdout, stderr):
            token = guard.token
            require(token and token.get('process') is process and token['constructing'], 'fresh pipe constructor owner')
            values = GET_HANDLES(process, stdin, stdout, stderr)
            token['fresh_pipe_handles'] = {int(values[i]) for i in (1, 2, 4)}
            return values

        def initialize(process, *args, **kwargs):
            if sys._getframe(1).f_code is Guard.run_git.__code__:
                require(sys._getframe(1).f_code is Guard.run_git.__code__ and guard.token is None, 'fixed Git envelope constructor only')
                require(len(args) == 1 and args[0] == guard.git_intents[-1]['argv'] and set(kwargs) == {'stdout','stderr','cwd','env','executable','close_fds','creationflags'}
                    and kwargs['stdout'] == kwargs['stderr'] == subprocess.PIPE and kwargs['cwd'] == str(TASK)
                    and kwargs['executable'] == str(GIT) and kwargs['close_fds'] is True
                    and kwargs['creationflags'] == subprocess.CREATE_NO_WINDOW, 'exact original query capture transport')
                token = {'process': process, 'argv': args[0], 'env': kwargs['env'], 'constructing': True, 'kind': 'git',
                         'popen': False, 'create': False, 'fresh_pipe_handles': set(), 'used_pipe_handles': set()}
                guard.token = token
                try:
                    return INIT(process, *args, **kwargs)
                finally:
                    token['constructing'] = False
                    guard.token = None
                    if getattr(process, '_child_created', False) and getattr(process, '_handle', None) is not None:
                        row = {'number': guard.git_intents[-1]['number'], 'process': process, 'pid': process.pid,
                               'held_handle': int(process._handle), 'Popen_audit': token['popen'],
                               'CreateProcess_audit': token['create'], 'identity_error': None}
                        guard.git_children.append(row)
                        try:
                            row.update(held(process))
                            require(row['birth_filetime'] > 0 and row['image'] is not None and key(row['image']) == key(GIT)
                                and token['popen'] and token['create'], 'actual fixed Git dual audits/birth/image')
                        except BaseException as error:
                            row['identity_error'] = type(error).__name__ + ':' + str(error)
                        write_new(guard.out / ('git/' + str(row['number']) + '-started.json'), raw_json({k:v for k,v in row.items() if k != 'process'}))
            active = guard.active
            require(active is not None and sys._getframe(1).f_code is active['original_run'].__code__, 'original run_reader constructor caller')
            require(len(args) == 1 and args[0] == active['argv']
                    and kwargs == {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE,
                        'cwd': active['cwd'], 'env': active['env'], 'close_fds': True,
                        'creationflags': subprocess.CREATE_NO_WINDOW}, 'exact original reader Popen arguments')
            require(hash_file(PYTHON) == PYTHON_SHA, 'program before original constructor')
            token = {'process': process, 'argv': args[0], 'cwd': str(active['cwd']), 'env': active['env'],
                'constructing': True, 'popen': False, 'create': False, 'fresh_pipe_handles': set(), 'used_pipe_handles': set()}
            guard.token = token
            try:
                return INIT(process, *args, **kwargs)
            finally:
                token['constructing'] = False
                guard.token = None
                if getattr(process, '_child_created', False) and getattr(process, '_handle', None) is not None:
                    row = {'process': process, 'pid': process.pid, 'held_handle': int(process._handle),
                           'Popen_audit': token['popen'], 'CreateProcess_audit': token['create'], 'identity_error': None}
                    guard.children.append(row)
                    try:
                        row.update(held(process))
                        require(row['birth_filetime'] > 0 and token['popen'] and token['create'], 'complete original constructor identity')
                        if row['image'] is not None:
                            require(key(row['image']) == key(PYTHON), 'actual held Python image')
                        require(hash_file(PYTHON) == PYTHON_SHA, 'program closing observation')
                    except BaseException as error:
                        # Retain the created object; let original owner assign/close its Job.
                        row['identity_error'] = type(error).__name__ + ':' + str(error)
                    write_new(guard.out / 'reader-held-started.json', raw_json({k: v for k, v in row.items() if k != 'process'}))

        self.guarded_init, self.guarded_handles = initialize, handles
        POPEN.__init__, POPEN._get_handles = initialize, handles
        subprocess.run = self.run_git
        sys.addaudithook(self.audit)
        sys.setprofile(self.profile_role)
        self.assert_active()


    def observe_original_locks(self):
        import msvcrt
        original_locking, original_close = msvcrt.locking, os.close
        guard = self

        def locking(fd, mode, count):
            frame = guard.coordinator_frame('coordinator_lock')
            require(frame is not None and key(frame.f_locals['path']) in guard.locks
                    and frame.f_locals['descriptor'] == fd and count == 1, 'only original two-lock byte-lock call')
            if fd in guard.lock_descriptors and guard.lock_descriptors[fd]['close_returned']:
                guard.completed_lock_rows.append(guard.lock_descriptors.pop(fd))
            row = guard.lock_descriptors.setdefault(fd, {'path': key(frame.f_locals['path']), 'fd': fd,
                'acquire_returned': False, 'unlock_returned': False, 'close_returned': False, 'errors': []})
            try:
                value = original_locking(fd, mode, count)
                if mode == msvcrt.LK_NBLCK:
                    row['acquire_returned'] = True
                elif mode == msvcrt.LK_UNLCK:
                    row['unlock_returned'] = True
                else:
                    guard.deny('unexpected original byte-lock mode', mode)
                return value
            except BaseException as error:
                row['errors'].append(type(error).__name__ + ':' + str(error))
                raise

        def closing(fd):
            row = guard.lock_descriptors.get(fd)
            if row and guard.coordinator_frame('coordinator_lock'):
                value = original_close(fd)
                row['close_returned'] = True
                return value
            return original_close(fd)

        msvcrt.locking, os.close = locking, closing


    def wrap_transport(self, lifetime):
        original = lifetime.run_reader
        assign, active, close = lifetime.ReaderJob.assign, lifetime.ReaderJob.active, lifetime.ReaderJob.close
        guard = self

        def assigned(job, process):
            value = assign(job, process)
            guard.job_observations['assign_success'] += 1
            return value

        def queried(job):
            value = active(job)
            guard.job_observations['active_queries'] += 1
            guard.job_observations['last_active'] = value
            guard.job_observations['zero_observed'] |= value == 0
            return value

        def closed(job):
            value = close(job)
            guard.job_observations['close_success'] += 1
            return value

        def transport(command, *, input, cwd, env, timeout):
            caller = sys._getframe(1)
            globals_ = caller.f_globals
            require(caller.f_code is globals_['_run_reader'].__code__ and key(globals_['__file__']) == key(READER)
                    and hash_file(READER) == READER_SHA, 'checked original reader transport caller')
            frame = caller
            while frame and not (frame.f_globals is globals_ and frame.f_code is globals_['capture_completed'].__code__):
                frame = frame.f_back
            require(frame is not None, 'only actual capture_completed call')
            request = frame.f_locals['request']
            require(request['artifact_root'] == str(ORIGIN) and request['source_root'] == str(TASK / 'r22')
                    and request['source_commit'] == '6d4ab1c3cba67bebe98f75c9462af613bf9d739a'
                    and request['planner'] == 'mvg' and request['run_id'] == 'm4'
                    and request['expected_run_raw_digest'] == self.c['run_digest']
                    and request['reader_raw_digest'] == 'sha256:' + READER_SHA
                    and input == globals_['canonical'](request), 'fixed original native request')
            expected = [str(PYTHON), '-X', 'dev', '-I', '-S', '-B', '-c',
                        lifetime.GATE + globals_['_reader_bootstrap'](READER, request['reader_raw_digest'])]
            require(command == expected and cwd == TASK / 'r22' and timeout == 3600
                    and env['CODEX_HOME'] == str(self.out / 'offline-codex-home')
                    and env['NEWROGUE_CODEX_REASONING_EFFORT'] == 'high', 'exact source-bound gate/argv/cwd/host cap/environment')
            self.transport_calls += 1
            require(self.transport_calls == 1, 'no repeated reader or retry')
            self.active = {'original_run': original, 'argv': command, 'cwd': cwd, 'env': env}
            completed = None
            try:
                completed = original(command, input=input, cwd=cwd, env=env, timeout=timeout)
                write_new(self.out / 'reader-stdout.bin', completed.stdout)
                write_new(self.out / 'reader-stderr.bin', completed.stderr)
                require(type(completed.returncode) is int and len(self.children) == 1, 'actual original reader exit/child count')
                require(self.job_observations['assign_success'] == 1 and self.job_observations['last_active'] == 0
                        and self.job_observations['close_success'] == 1, 'observed original Job assignment/quiescence/close')
                if completed.returncode == 0:
                    require(not self.children[0]['identity_error'], 'held identity unknown remains failure')
                    value = globals_['strict_json'](completed.stdout)
                    self.admit_capture(value, globals_)
                # Preserve the original nonzero CompletedProcess unchanged so
                # capture_completed emits its actual NativeReaderError contract.
                return completed
            except BaseException as error:
                for stream in ('stdout', 'stderr'):
                    raw = getattr(error, stream, None)
                    path = self.out / ('reader-' + stream + '-failure.bin')
                    if type(raw) is bytes and not path.exists():
                        write_new(path, raw)
                raise
            finally:
                self.active = None
                rows = []
                for row in self.children:
                    code = row['process'].poll()
                    rows.append({**{k: v for k, v in row.items() if k != 'process'},
                        'actual_original_held_OS_exit': code, 'exit_known': type(code) is int})
                write_new(self.out / 'reader-held-terminal.json', raw_json({'children': rows,
                    'Job_observations': self.job_observations, 'original_transport_returned_normally': completed is not None,
                    'cleanup_contract': 'unmodified original run_reader; normal return requires empty Job and closed IO'}))

        lifetime.ReaderJob.assign, lifetime.ReaderJob.active, lifetime.ReaderJob.close = assigned, queried, closed
        lifetime.run_reader = transport
        self.transport_wrapper = transport


    def close_inputs(self):
        self.assert_active()
        require(not self.codec_fds, 'no unclosed original codec descriptors')
        for name, row in self.c['official_CLI_binding']['files'].items():
            require(file_identity(name) == row['file_identity'], 'exact public CLI DATA identity close')
        for name, expected in self.c['stdlib_search_metadata'].items():
            path = plain(name, missing=True)
            actual = None
            if path.exists():
                info = path.stat()
                actual = {'kind': 'directory', 'identity': [info.st_dev, info.st_ino]} if path.is_dir() else {
                    'kind': 'file', 'identity': file_identity(path), 'sha256': hash_file(path)}
            require(actual == expected, 'official isolated stdlib search metadata drift')
        for name, expected in self.metadata_directories.items():
            path = plain(name, missing=True)
            observed_writes = {key(row['path']) for row in self.lock_events}
            observed_writes |= {name for name in self.public_directories | self.write_targets if Path(name).exists()}
            added = {Path(p).name for p in observed_writes if key(Path(p).parent) == name}
            if expected is None:
                require(not path.exists() or name in observed_writes and path.is_dir()
                        and set(members(path, validate_children=False)) <= added, 'unadmitted missing metadata ancestor creation')
            else:
                info = path.stat()
                require([info.st_dev, info.st_ino] == expected['identity']
                        and set(members(path, validate_children=False)) == set(expected['members']) | added,
                        'finite metadata ancestor identity/member drift')
        for name, expected in self.c['program_file_identities'].items():
            require(file_identity(name) == expected, 'actual installed program identity drift')
        for name, expected in self.files.items():
            require(hash_file(name) == expected, 'parent source/dependency/original/target-before input drift:' + name)
        for name, expected in self.directories.items():
            # Target-owned new descendants are allowed only at the exact three outputs.
            if not Path(name).is_relative_to(self.target):
                require(members(name) == expected, 'parent directory drift:' + name)
        for name, expected in self.extra_files.items():
            path = plain(name, missing=True)
            require(('sha256:' + hash_file(path) if path.is_file() else None) == expected, 'authenticated native capture drift')
        for name, expected in self.extra_dirs.items():
            # Match the original verify_capture member-name contract; observing
            # a name never authorizes that child's payload or adds new checks.
            require(members(name, validate_children=False) == expected, 'authenticated capture directory drift')
        for relative, expected in self.new_target_pins.items():
            require('sha256:' + hash_file(self.target / relative) == expected, 'new target capsule/support changed at close')
        allowed = {key(self.target / name) for name in self.c['target_files']}
        if self.target_complete:
            allowed |= self.write_targets
        expected_dirs = {key(self.target)} | self.public_directories | {key(self.target / name) for name in self.c['target_before']['directories']}
        for name in allowed:
            parent = Path(name).parent
            while parent.is_relative_to(self.target):
                expected_dirs.add(key(parent))
                if parent == self.target:
                    break
                parent = parent.parent
        actual = set()
        pending = [self.target]
        while pending:
            directory = plain(pending.pop())
            require(key(directory) in expected_dirs, 'unexpected target directory')
            with _SCANDIR(directory) as entries:
                for entry in entries:
                    path = plain(entry.path)
                    if path.is_dir():
                        require(key(path) in expected_dirs, 'unexpected target subdirectory')
                        pending.append(path)
                    else:
                        require(key(path) in allowed, 'unexpected target file; no payload read')
                        actual.add(key(path))
        require(actual == allowed, 'exact target file membership before/after')


    def audit_native(self, event, values):
        if event == 'Root.native.reader.guard':
            if values == (self.nonce,):
                self.ack = self.nonce
            return
        if event in ('subprocess.Popen', '_winapi.CreateProcess'):
            token = self.token
            require(token is not None and token['constructing'], 'only original reader constructor')
            command = subprocess.list2cmdline(token['argv'])
            if event == 'subprocess.Popen':
                require(len(values) == 4 and values[0] is None and values[1] == command
                        and values[2] == token['cwd'] and values[3] is token['env'] and not token['popen'], 'Popen exact audit')
                token['popen'] = True
            else:
                require(len(values) == 3 and values[0] is None and type(values[1]) is str
                        and values[2] == token['cwd'] and token['popen'] and not token['create'], 'CreateProcess shape/order')
                frame = sys._getframe(1)
                while frame and frame.f_code is not EXECUTE.__code__:
                    frame = frame.f_back
                require(frame is not None, 'original _execute_child frame')
                actual = frame.f_locals
                require(actual['self'] is token['process'] and actual['args'] == command and actual['executable'] is None
                        and actual['cwd'] == token['cwd'] and actual['env'] is token['env']
                        and actual['creationflags'] == subprocess.CREATE_NO_WINDOW, 'original actual call arguments')
                token['create'] = True
            return
        if event.startswith(('socket.', 'os.exec', 'os.spawn', 'os.posix_spawn')) or event in {
                'os.system', 'os.startfile', 'os.fork', 'os.forkpty', 'os.link', 'os.symlink'}:
            self.deny('network/tool/link role', event)
        if event == 'open':
            flags = values[2] or 0
            if type(values[0]) is int:
                if self.pipe_open(values[0]):
                    return
                self.codec_fd_open(values[0], values[1], flags)
                return
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if not writing and key(values[0]) == key(GIT):
                git_program_metadata()
                self.allowed_read(GIT)
                return
            (self.allowed_write if writing else self.allowed_read)(plain(values[0], missing=True))
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.chown', 'os.utime', 'os.truncate'):
            self.allowed_write(plain(values[0], missing=True), mkdir=event == 'os.mkdir')
        elif event in ('os.rename', 'os.replace'):
            self.allowed_write(values[0]); self.allowed_write(values[1])
        elif event in ('os.listdir', 'os.scandir'):
            name = key(values[0])
            if not (name in self.directories or name in self.metadata_directories or name in self.extra_dirs or self.runtime(name)
                    or Path(name).is_relative_to(self.out) or (Path(name).is_relative_to(self.target)
                    and any(Path(p).is_relative_to(name) for p in self.write_targets))):
                self.deny('enumeration outside declared/import/capture directories', name)


    def original_frame(self, module_name, function_name):
        module = sys.modules.get(module_name)
        function = getattr(module, function_name, None)
        function = getattr(function, '__wrapped__', function)
        if not isinstance(getattr(module, '__loader__', None), Loader):
            return None
        code = getattr(function, '__code__', None)
        frame = sys._getframe(1)
        while frame:
            if (frame.f_code is code and frame.f_globals is module.__dict__
                    and key(frame.f_code.co_filename) == key(SOURCE / 'scripts/python' / (module_name + '.py'))):
                return frame
            frame = frame.f_back
        return None


    def audit(self, event, values):
        try:
            return self.audit_checked(event, values)
        except BaseException as error:
            if len(self.blocked) < 256:
                self.blocked.append({'event': event, 'type': type(error).__name__, 'reason': str(error)[:512]})
            raise


    def audit_checked(self, event, values):
        if event == 'Root.native.reader.guard':
            if values == (self.nonce,):
                self.ack = self.nonce
            return
        if event in ('subprocess.Popen', '_winapi.CreateProcess'):
            if self.token is not None and self.token.get('kind') == 'git':
                return self.audit_git_process(event, values)
            return self.audit_native(event, values)
        if event.startswith(('socket.', 'os.exec', 'os.spawn', 'os.posix_spawn')) or event in {
                'os.system', 'os.startfile', 'os.fork', 'os.forkpty', 'os.link', 'os.symlink'}:
            self.deny('no network/model/other process/link', event)
        if event == 'exec' and values and hasattr(values[0], 'co_filename'):
            filename = values[0].co_filename
            if filename and not filename.startswith('<') and Path(key(filename)).is_relative_to(TARGET):
                self.deny('target locator is data only', filename)
        if event == 'open':
            path, mode, flags = values[0], values[1] or '', values[2] or 0
            if type(path) is int:
                if not self.pipe_open(path):
                    self.codec_fd_open(path, mode, flags)
                return
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                self.allowed_write(path, flags=flags)
            else:
                self.allowed_read(path)
                if key(path) == key(GIT):
                    git_program_metadata()
                else:
                    plain(path, missing=True)
        elif event in ('os.scandir', 'os.listdir'):
            path = plain(values[0], missing=True)
            name = key(path)
            if (name in self.directories or name in self.metadata_directories or name in self.extra_dirs
                    or name in self.public_directories or self.runtime(name) or path.is_relative_to(self.out)):
                return
            if name in self.absent_target_directories and not path.exists():
                return
            self.deny('enumeration outside fixed or authenticated metadata', name)
        elif event == 'os.mkdir':
            self.allowed_write(values[0], mkdir=True)
        elif event in {'os.remove', 'os.rmdir', 'os.rename', 'os.replace', 'os.chmod', 'os.chown', 'os.utime',
                       'os.truncate', 'shutil.rmtree', 'shutil.copyfile'}:
            if not Path(key(values[0])).is_relative_to(self.out):
                self.deny('no old target / lock destructive or copying role', event)


    def git_shape(self, suffix):
        fixed = [
            ['rev-parse','--show-toplevel'], ['rev-parse','HEAD'], ['symbolic-ref','--quiet','HEAD'],
            ['status','--porcelain=v1','-z','--untracked-files=all','--','.',':(exclude)logs'],
            ['diff','--no-ext-diff','--no-textconv','--binary','HEAD','--','.',':(exclude)logs'],
            ['diff','--no-ext-diff','--no-textconv','--cached','--binary','HEAD','--','.',':(exclude)logs'],
            ['diff','--no-ext-diff','--no-textconv','--binary','--','.',':(exclude)logs'],
            ['rev-parse','--is-shallow-repository'], ['for-each-ref','--format=%(objectname)','refs/replace'],
            ['rev-list','--topo-order','--parents','HEAD']]
        if suffix in fixed:
            return
        if len(suffix) == 3 and suffix[:2] == ['ls-tree','-r']:
            self.deny('original ls-tree requires -z', suffix)
        if len(suffix) == 4 and suffix[:3] == ['ls-tree','-r','-z']:
            require(suffix[3] in self.known_commits, 'actual observed target commit for ls-tree')
            return
        if len(suffix) == 3 and suffix[:2] == ['rev-parse','--verify']:
            require(suffix[2] in {BASELINE + '^{commit}', HEAD + '^{commit}'}, 'only actual declared target anchors')
            return
        if len(suffix) == 3 and suffix[0] == 'cat-file':
            require(suffix[1] in {'commit','tree','blob'} and self.known_objects.get(suffix[2]) == suffix[1], 'only target output-derived Git object')
            module = sys.modules.get('_b_route_initial_legacy')
            require(module is not None and isinstance(module.__loader__, Loader), 'original SourceOnly object reader')
            frame = sys._getframe(1)
            while frame and frame.f_code is not module.Objects.get.__code__:
                frame = frame.f_back
            require(frame is not None and frame.f_globals is module.__dict__
                    and frame.f_locals['kind'] == suffix[1] and frame.f_locals['oid'] == suffix[2]
                    and key(frame.f_locals['self'].root) == key(TARGET), 'actual original Objects.get kind/root/OID')
            return
        if suffix[:4] == ['ls-files','--stage','-z','--']:
            module = sys.modules.get('_b_route_initial_legacy')
            frame = original_frame('_b_route_initial_legacy', 'observe')
            require(frame is not None and isinstance(module.__loader__, Loader), 'original initial-boundary index caller')
            proof = frame.f_locals['proof']
            expected = tuple(module._index_paths(proof, self.inventory.TRIPLET))
            require(tuple(suffix[4:]) == expected and proof['head'] == HEAD
                    and proof['epics_path'] == 'planning/bootstrap-v15/epics.md', 'exact original governed index operand list')
            return
        self.deny('unreviewed Git read query', suffix)


    def observe_git_output(self, suffix, raw, code):
        if code != 0:
            return
        if suffix == ['rev-parse','HEAD']:
            require(raw.decode('ascii').strip() == HEAD, 'actual fixed target HEAD')
        elif suffix == ['rev-parse','--show-toplevel']:
            require(key(raw.decode().strip()) == key(TARGET), 'actual target top-level')
        elif suffix == ['symbolic-ref','--quiet','HEAD']:
            require(raw.strip() == b'refs/heads/synthetic-v15', 'actual fixed target branch')
        elif suffix == ['rev-list','--topo-order','--parents','HEAD']:
            rows = [line.split() for line in raw.decode('ascii').splitlines()]
            require(0 < len(rows) <= 512 and all(re.fullmatch('[0-9a-f]{40}', item) for row in rows for item in row), 'bounded actual commit graph')
            for row in rows:
                for oid in row:
                    self.known_commits.add(oid); self.known_objects[oid] = 'commit'
        elif suffix[:3] == ['ls-tree','-r','-z'] or suffix[:4] == ['ls-files','--stage','-z','--']:
            for row in raw.split(b'\0'):
                if not row:
                    continue
                meta, name = row.split(b'\t', 1)
                mode, middle, last = meta.decode('ascii').split()
                kind, oid = (middle, last) if suffix[0] == 'ls-tree' else ('blob', middle)
                require(kind in {'blob','tree'} and re.fullmatch('[0-9a-f]{40}', oid), 'ordinary target output object')
                self.known_objects[oid] = kind
        elif suffix[0] == 'cat-file':
            kind, oid = suffix[1:]
            require(hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == oid,
                    'actual Git object bytes match requested identity')
            if kind == 'commit':
                for line in raw.split(b'\n\n', 1)[0].splitlines():
                    if line.startswith((b'tree ', b'parent ')):
                        tag, value = line.decode('ascii').split()
                        require(re.fullmatch('[0-9a-f]{40}', value), 'actual commit object reference')
                        self.known_objects[value] = 'tree' if tag == 'tree' else 'commit'
                        if tag == 'parent':
                            self.known_commits.add(value)
            elif kind == 'tree':
                index = 0
                while index < len(raw):
                    end = raw.index(b' ', index); zero = raw.index(b'\0', end + 1)
                    mode = raw[index:end]; value = raw[zero+1:zero+21]
                    require(len(value) == 20 and mode in {b'40000',b'100644',b'100755'}, 'ordinary target tree reference')
                    self.known_objects[value.hex()] = 'tree' if mode == b'40000' else 'blob'
                    index = zero + 21
        require(len(self.known_objects) <= 8192, 'original bounded target object domain')


    def run_git(self, argv, **kwargs):
        self.assert_active()

        caller = sys._getframe(1)
        owner = self.inventory.git
        require(caller.f_code is owner.__code__ and caller.f_globals is self.inventory.__dict__
                and isinstance(self.inventory.__loader__, Loader) and key(caller.f_locals['root']) == key(TARGET), 'original inventory.git caller/root')
        prefix = ['git','--no-optional-locks','--no-replace-objects','-c','protocol.allow=never',
            '-c','core.hooksPath=' + os.devnull,'-c','commit.gpgSign=false','-c','tag.gpgSign=false','-C',str(TARGET)]
        require(type(argv) is list and argv == prefix + list(caller.f_locals['args'])
                and set(kwargs) == {'capture_output','timeout','env'} and kwargs['capture_output'] is True
                and type(kwargs['timeout']) is int and kwargs['timeout'] == 30
                and kwargs['env'] is caller.f_locals['child_env'], 'unchanged original argv/30s/capture_output/env object')
        self.git_shape(argv[len(prefix):])
        require(hash_file(GIT) == GIT_SHA and file_identity(GIT) == self.c['program_identities']['Git'], 'fixed Git before dispatch')
        number = len(self.git_intents) + 1
        require(number <= 4096, 'finite original Git read calls')
        stem = 'git/' + str(number) + '-'
        self.git_intents.append({'number':number, 'argv':argv})
        write_new(self.out / (stem+'intent.json'), raw_json({'argv':argv, 'executable':str(GIT),
            'timeout':30, 'capture_output':True, 'environment':kwargs['env'], 'original_optional':caller.f_locals['optional'], 'automatic_retry':False}))
        process = None; stdout = stderr = b''; error = None; timed_out = False; row = None
        try:
            process = POPEN(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(TASK),
                env=kwargs['env'], executable=str(GIT), close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
            row = self.git_children[-1]
            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()  # Same newly-owned-child timeout cleanup as stdlib subprocess.run.
                stdout, stderr = process.communicate(timeout=30)
        except BaseException as exc:
            error = exc
            if process is None and self.git_children and self.git_children[-1].get('number') == number:
                row = self.git_children[-1]; process = row['process']
            if process is not None and process.poll() is None:
                try:
                    process.wait(timeout=30)
                except BaseException as wait_error:
                    if row is not None:
                        row['finite_wait_error'] = type(wait_error).__name__ + ':' + str(wait_error)
        finally:
            actual = None; raw_exit_query = None; closed = False
            post_identity = None; post_identity_error = None; exit_query_error = None
            handle_close_error = None; handle_close_attempted = False
            pre_identity_verified = False; terminal_birth_verified = False
            if process is not None:
                try:
                    try:
                        pre_identity_verified = bool(row is not None and row['identity_error'] is None
                            and row['Popen_audit'] and row['CreateProcess_audit'] and row.get('image') is not None
                            and key(row['image']) == key(GIT) and row.get('birth_filetime',0) > 0)
                        post_identity = held(process)
                        require(pre_identity_verified, 'actual original pre-image/audits/birth fixed Git')
                        require(post_identity['pid'] == row['pid'] and post_identity['held_handle'] == row['held_handle']
                                and post_identity['birth_filetime'] == row['birth_filetime'], 'same original Git held handle/PID/birth at terminal')
                        terminal_birth_verified = True
                        # Windows can deny image lookup after a known process exit.
                        # Preserve the actual error; a returned image must still match.
                        if post_identity['image'] is not None:
                            require(key(post_identity['image']) == key(GIT), 'available post-image must remain fixed Git')
                    except BaseException as identity_error:
                        post_identity_error = type(identity_error).__name__ + ':' + str(identity_error)
                    try:
                        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                        query = kernel.GetExitCodeProcess
                        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]; query.restype = wintypes.BOOL
                        value = wintypes.DWORD()
                        require(query(wintypes.HANDLE(int(process._handle)), ctypes.byref(value)), 'actual Git held exit query')
                        raw_exit_query = value.value
                        require(raw_exit_query != 259 and process.poll() == raw_exit_query, 'actual known original held Git terminal')
                        actual = raw_exit_query
                    except BaseException as query_error:
                        exit_query_error = type(query_error).__name__ + ':' + str(query_error)
                finally:
                    # The original owned handle gets a close attempt even when
                    # post-identity or exit-query validation failed. No PID reopen.
                    handle_close_attempted = True
                    try:
                        process._handle.Close()
                        closed = True
                    except BaseException as close_error:
                        handle_close_error = type(close_error).__name__ + ':' + str(close_error)
            closing_errors = [value for value in (post_identity_error, exit_query_error, handle_close_error) if value is not None]
            closing_error = ';'.join(closing_errors) if closing_errors else None
            write_new(self.out / (stem+'stdout.bin'), stdout)
            write_new(self.out / (stem+'stderr.bin'), stderr)
            evidence = {k:v for k,v in (row or {}).items() if k != 'process'}
            evidence.update(number=number, argv=argv, actual_original_held_OS_exit=actual,
                raw_GetExitCodeProcess_value=raw_exit_query, terminal_known=actual is not None,
                python_returncode=None if process is None else process.returncode, timeout=timed_out,
                error=None if error is None else type(error).__name__ + ':' + str(error),
                post_identity=post_identity, post_identity_error=post_identity_error,
                pre_identity_verified=pre_identity_verified, terminal_birth_verified=terminal_birth_verified,
                exit_query_error=exit_query_error, handle_close_attempted=handle_close_attempted, handle_close_error=handle_close_error,
                closing_error=closing_error, actual_handle_closed=closed,
                stdout_sha256=digest(stdout), stderr_sha256=digest(stderr), stdout_bytes=len(stdout), stderr_bytes=len(stderr))
            write_new(self.out / (stem+'terminal.json'), raw_json(evidence))
            self.git_records.append(evidence)
        require(row is not None and row['identity_error'] is None and row['Popen_audit'] and row['CreateProcess_audit']
                and pre_identity_verified and terminal_birth_verified and actual is not None
                and closing_error is None and closed and hash_file(GIT) == GIT_SHA
                and file_identity(GIT) == self.c['program_identities']['Git'], 'actual held Git audits/identity/program close')
        if error is not None:
            raise error
        if timed_out:
            raise subprocess.TimeoutExpired(argv, 30, stdout, stderr)
        self.observe_git_output(argv[len(prefix):], stdout, actual)
        return subprocess.CompletedProcess(argv, actual, stdout, stderr)


    def audit_git_process(self, event, values):
        if event in ('subprocess.Popen', '_winapi.CreateProcess'):
            token = self.token
            require(token and token['constructing'], 'only fixed original inventory Git constructor')
            command = subprocess.list2cmdline(token['argv'])
            if event == 'subprocess.Popen':
                require(len(values) == 4 and values[0] == str(GIT) and values[1] == command
                        and values[2] == str(TASK) and values[3] is token['env'] and not token['popen'], 'fixed Git Popen audit')
                token['popen'] = True
            else:
                require(len(values) == 3 and values[0] == str(GIT) and type(values[1]) is str
                        and values[2] == str(TASK) and token['popen'] and not token['create'], 'known opaque C command shape and audit order')
                frame = sys._getframe(1)
                while frame and frame.f_code is not EXECUTE.__code__:
                    frame = frame.f_back
                require(frame is not None, 'original subprocess _execute_child frame')
                actual = frame.f_locals
                require(actual['self'] is token['process'] and actual['args'] == command
                        and actual['executable'] == str(GIT) and actual['cwd'] == str(TASK)
                        and actual['env'] is token['env'] and actual['creationflags'] == subprocess.CREATE_NO_WINDOW,
                        'actual original C-dispatch Python frame arguments; C command is not argv proof')
                token['create'] = True
            return

"""AST assembly tail; no author execution. The assembled host is the entry."""


def target_close(config, guard):
    actual = snapshot_tree(TARGET)
    before = config['target_before']
    new_files = {Path(name).relative_to(Path(key(TARGET))).as_posix()
                 for name in guard.review_files | guard.target_scope_locks}
    require(set(actual['files']) == set(before['files']) | new_files, 'only actual four review files and original new scope locks')
    for name, row in before['files'].items():
        require(actual['files'][name] == row, 'all original target/Git/capsule/request raw and identities unchanged')
    allowed_dirs = {Path(name).relative_to(Path(key(TARGET))).as_posix() for name in guard.public_directories}
    for name in new_files:
        parent = Path(name).parent
        while str(parent) != '.':
            allowed_dirs.add(parent.as_posix())
            parent = parent.parent
    require(set(actual['directories']) <= set(before['directories']) | allowed_dirs, 'only finite original namespace directories')
    for name, row in before['directories'].items():
        now = actual['directories'][name]
        require(now['identity'] == row['identity'], 'old target directory identity unchanged')
        additions = {Path(path).name for path in new_files | allowed_dirs
                     if Path(path).parent.as_posix() == (name or '.')}
        require(set(now['members']) == set(row['members']) | additions.intersection(now['members']), 'old target directory membership unchanged except admitted children')
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args()
    require(os.name == 'nt' and sys.flags.dev_mode and sys.flags.isolated and sys.flags.no_site
            and sys.dont_write_bytecode and not sys.flags.optimize and Path.cwd() == TASK
            and Path(sys.executable).absolute() == PYTHON and Path(__file__).absolute() == HOME / 'review_prepare_host.draft.py', 'fixed isolated Root entry')
    require(datetime.now(timezone.utc).date().isoformat() == '2026-11-09', 'new day requires new reviewed namespace')
    require(hash_file(HOME / 'manifest.json') == args.manifest_sha256, 'exact reviewed manifest')
    manifest = json.loads(read(HOME / 'manifest.json'))
    for name, row in manifest['files'].items():
        require(hash_file(HOME / name) == row['sha256'], 'all reviewed control bytes')
    config_path = plain(TASK / args.config)
    require(config_path.is_relative_to(TASK / 'logs/ci/2026-11-09') and hash_file(config_path) == args.config_sha256, 'actual Root config pin')
    config = json.loads(read(config_path))
    require(all(config[name] is True for name in ('Root_public_review_prepare_admitted','Root_request_actual_ready_staged',
            'Root_fresh_source_closed','Root_normal_token','original_nx_two_lock_scope_admitted',
            'authenticated_capture_exact_reads_admitted','official_CLI_public_data_only_scope_admitted')),
            'actual Root admission and source/request seal required')
    require(config['target'] == str(TARGET) and config['operation_id'] == OPERATION
            and config['request_ref'] == REQUEST and config['model_calls_allowed'] == 0, 'only exact original public review-prepare')
    out = plain(TASK / 'logs/ci/2026-11-09/story27-r52-public-review-prepare-02', missing=True)
    require(not out.exists(), 'fresh output; preserve any attempt')
    source_close(config)
    require(snapshot_tree(TARGET) == config['target_before'], 'fresh staged target/Git equals actual seal')
    require(hash_file(TARGET / REQUEST) == config['request_sha256'] and not (TARGET / REVIEW_HOME).exists(), 'actual new request and review namespace')
    out.mkdir(exist_ok=False)
    write_new(out / 'offline-codex-home/models_cache.json', MODEL_CATALOG)
    inherited_limit = os.environ.get('SC_CAPABILITY_MAX_INPUT_TOKENS')
    require(inherited_limit in (None,'70000','96000'), 'same finite native04 inherited input limit')
    safe_env = {name: os.environ[name] for name in ('SystemRoot','WINDIR','SystemDrive','TEMP','TMP',
                'PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS') if name in os.environ}
    safe_env.update(CODEX_HOME=str(out / 'offline-codex-home'), NEWROGUE_CODEX_REASONING_EFFORT='high',
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', TIKTOKEN_CACHE_DIR=str(TASK / 'story22-tokenizer-cache'),
        PATH=str(GIT.parent)+os.pathsep+str(PYTHON.parent), PATHEXT='.EXE',
        GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_COUNT='0',
        GIT_TERMINAL_PROMPT='0',GIT_OPTIONAL_LOCKS='0')
    cli_path = HOME / 'cli_binding.draft.py'
    require(hash_file(cli_path) == '13e51ca6a806505b68b8bc73b216530809f09d438c6d94b9ada30f7ae7fc6fbd', 'same validated CLI DATA helper')
    cli = types.ModuleType('_Root_review_prepare_CLI_environment'); cli.__file__ = str(cli_path)
    exec(compile(read(cli_path), str(cli_path), 'exec'), cli.__dict__)
    safe_env = cli.bind_environment(safe_env)
    if inherited_limit is not None:
        safe_env['SC_CAPABILITY_MAX_INPUT_TOKENS'] = inherited_limit
    os.environ.clear(); os.environ.update(safe_env)
    guard = Guard(config, out)
    guard.files.update({key(config_path):args.config_sha256,key(PYTHON):PYTHON_SHA,key(GIT):GIT_SHA,
        key(out/'offline-codex-home/models_cache.json'):digest(MODEL_CATALOG),key(HOME/'manifest.json'):args.manifest_sha256})
    guard.files.update({key(HOME/name):row['sha256'] for name,row in manifest['files'].items()})
    guard.files.update({key(TASK/name):pin for name,pin in config['prerequisite_pins'].items()})
    guard.files[key(TASK/config['Root_STOP_ref'])] = config['Root_STOP_sha256']
    guard.files[key(TASK/config['stage_receipt_ref'])] = config['stage_receipt_sha256']
    stdout, stderr = io.StringIO(), io.StringIO()
    outcome = {'passed':False,'operation_id':OPERATION,'stage':'review-prepare','model_calls':0,
        'formal_acceptance':False,'automatic_retry':False,'paid_or_unknown':80,'guard_occupancy':178,'campaign_limit':290,'released':0,
        'offline_catalog_is_current_model_or_high_evidence':False}
    write_new(out/'intent.json',raw_json(outcome))
    code = None
    try:
        guard.install(); guard.close_inputs(); guard.observe_original_locks()
        lifetime = importlib.import_module('_b_route_reader_lifetime')
        guard.wrap_transport(lifetime)
        guard.inventory = importlib.import_module('_b_route_inventory')
        owner = importlib.import_module('b_route_adoption')
        require(owner.__file__ == str(SOURCE/'scripts/python/b_route_adoption.py') and isinstance(owner.__loader__,Loader), 'original public SourceOnly CLI owner')
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = owner.main(['--root',str(TARGET),'--stage','review-prepare','--operation-id',OPERATION,'--request',REQUEST])
        write_new(out/'owner-stdout.bin',stdout.getvalue().encode('utf-8'))
        write_new(out/'owner-stderr.bin',stderr.getvalue().encode('utf-8'))
        result = json.loads(stdout.getvalue())
        require(type(code) is int and code == 0 and result['status'] == 'review_prepared'
                and result['operation_id'] == OPERATION and result['model_dispatched'] is False
                and result['semantic_execution_required'] is True and result['machine_preservation'] is None
                and all(result[name] is False for name in ('formal_adoption','readiness','runtime_verified')), 'actual complete public review-prepare result')
        require(guard.transport_calls == 1 and len(guard.children) == 1
                and guard.job_observations['assign_success'] == 1 and guard.job_observations['last_active'] == 0
                and guard.job_observations['close_success'] == 1, 'actual original full reader/Job completed')
        require(guard.public_scope_admitted and guard.target_scope_locks, 'actual original scope denominator and locks')
        lock_rows = guard.completed_lock_rows + list(guard.lock_descriptors.values())
        require({row['path'] for row in lock_rows} == guard.locks
                and all(row['acquire_returned'] and row['unlock_returned'] and row['close_returned'] and not row['errors'] for row in lock_rows), 'all actual original nx and target scope locks acquired/unlocked/closed')
        require(len(guard.git_intents) == len(guard.git_records) > 0 and all(row['actual_original_held_OS_exit'] is not None
                and row['actual_handle_closed'] and row['closing_error'] is None and not row['timeout']
                and row['Popen_audit'] and row['CreateProcess_audit'] for row in guard.git_records), 'all original readonly Git held terminals closed')
        guard.target_complete = True
        guard.close_inputs(); source_close(config)
        after = target_close(config, guard)
        review_pins = {name:hash_file(TARGET/name) for name in REVIEW_FILES}
        require(result['subject_ref'] == REVIEW_HOME+'/subject.json' and result['workspace'] == REVIEW_HOME+'/w'
                and result['execution_capture_ref'] == REVIEW_HOME+'/execution.json'
                and result['required_environment'] == {'NEWROGUE_CODEX_REASONING_EFFORT':'high'}, 'actual exact original review outputs and command description')
        write_new(out/'owner-result.json',raw_json(result))
        write_new(out/'lock-events.json',raw_json({'path_events':guard.lock_events,'actual_byte_lock_and_close':lock_rows}))
        write_new(out/'codec-fd-events.json',raw_json(guard.codec_fd_events))
        outcome.update(passed=True,original_owner_returncode=code,owner_result=result,review_files=review_pins,
            actual_native_capture_sha256=hash_file(out/'actual-native-capture.json'),Job_observations=guard.job_observations,
            actual_held_Git=guard.git_records,all_scope_lock_rows=lock_rows,target_after=after,source_closed=True,
            request_ref=REQUEST,request_sha256=config['request_sha256'],stage_receipt_ref=config['stage_receipt_ref'],
            stage_receipt_sha256=config['stage_receipt_sha256'],actual_counts=config['actual_counts'])
        write_new(out/'result.json',raw_json(outcome))
        guard.close_inputs(); source_close(config)
        require(snapshot_tree(TARGET) == after,'post-result original target/member closure')
        print(json.dumps({'passed':True,'stage':'review-prepare','result_sha256':hash_file(out/'result.json'),
                          'model_calls':0,'formal_acceptance':False}),flush=True)
        return 0
    except BaseException as error:
        for name,value in (('owner-stdout.bin',stdout.getvalue()),('owner-stderr.bin',stderr.getvalue())):
            if not (out/name).exists():write_new(out/name,value.encode('utf-8'))
        outcome.update(passed=False,error_type=type(error).__name__,reason=str(error)[:2048],original_owner_returncode=code,
            blocked_actions=guard.blocked,Git_records=guard.git_records,reader_calls=guard.transport_calls,
            Job_observations=guard.job_observations,original_lock_rows=guard.completed_lock_rows+list(guard.lock_descriptors.values()))
        write_new(out/'STOP.json',raw_json(outcome));traceback.print_exc();return 1


if __name__ == '__main__':
    raise SystemExit(main())
