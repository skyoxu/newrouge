"""Read a selected run through its exact preserved R10, R19 or R22 implementation.

The caller owns the project activity and native coordinator locks. This adapter
never locks, repairs counters, dispatches models or grants adoption. A fresh
isolated child performs native verification; only byte and directory pins are
rechecked at persistence. Synthetic tests do not establish native acceptance.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, redirect_stdout
import ast
import hashlib
import importlib.machinery
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from types import CodeType, FunctionType

SCHEMA = "newrouge.b-route-frozen-native-capture.v1"
SOURCE_COMMIT = "dc245b3b3d14abd512879369b30692536dfac4fd"
TASK_ROOT = Path(__file__).absolute().parents[3]
SOURCE_ROOT = TASK_ROOT / "r10"
R19_SOURCE_COMMIT = "1d126b85b908ba1eea4b27ceeb8a9669a771e6f3"
R19_EPOCH = "newrouge.b-route-mvg-source-epoch.v1"
R19_RECOVERY = "newrouge.b-route-mvg-synthesis-recovery.v1"
R22_SOURCE_COMMIT = "6d4ab1c3cba67bebe98f75c9462af613bf9d739a"
R22_EPOCH = "newrouge.b-route-selector-source-epoch.v1"
R22_RECOVERY = "newrouge.b-route-selector-recovery.v1"
READER = Path(__file__).absolute()
_REQUEST_FIELDS = {"source_root", "source_commit", "artifact_root", "planner", "run_id", "expected_run_raw_digest",
                   "expected_handoff_ref", "dependency_paths", "reader_path", "reader_raw_digest"}
_RESULT_FIELDS = {"schema_version", "handoff", "prepared", "run_identity", "source_identity", "files", "directories", "result_digest"}
_FORBIDDEN = {".codex", ".aws", ".ssh", "sessions", "archived_sessions", "credentials"}
_SECRETS = {"auth.json", "credentials", "credentials.json", "credentials.toml", "id_rsa", "id_ed25519"}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_DIAGNOSTIC_PHASES = frozenset({
    "reader_child", "parent_verify_capture", "independent_source", "native_import",
    "source_open", "prefix", "validate_input", "published_chain", "active_chain",
    "frozen_input", "dependency_closure", "handoff", "source_close",
    "transaction_close", "artifact_closure", "child_verify_capture",
})


class NativeReaderError(ValueError):
    """Public-safe structured metadata; raw output remains private on the cause."""
    def __init__(self, outcome, *, stdout=b'', stderr=b'', cleanup='unconfirmed', exit_code=None, reason=None):
        super().__init__('b_route_frozen_native_reader:' + outcome)
        self.reader_diagnostic = {
            'schema_version': 'newrouge.b-route-reader-failure.v1', 'outcome': outcome,
            'cleanup': cleanup, 'exit_code': exit_code, 'host_timeout_seconds': 3600,
            'reason': reason, 'native': _failure_records(stderr),
            'stdout': {'byte_count': len(stdout), 'raw_digest': digest(stdout)},
            'stderr': {'byte_count': len(stderr), 'raw_digest': digest(stderr)}}


def _safe_reason(error):
    # Only closed identifier-shaped reasons survive. Never include paths, JSON,
    # argv, request data, native tracebacks or the source/bootstrap program.
    value = str(error)
    prefix = 'b_route_frozen_native_reader:'
    if value.startswith(prefix):
        value = value[len(prefix):]
    value = value.split(':', 1)[0]
    if re.fullmatch(r'[a-z][a-z0-9_]{0,127}', value):
        return value
    diagnostic = getattr(error, 'diagnostic', None)
    code = getattr(getattr(diagnostic, 'reason_code', None), 'value', None)
    return code if type(code) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,127}', code) else type(error).__name__


def _failure_records(raw):
    records = []
    for line in raw.splitlines():
        if len(line) > 2048:
            continue
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if (type(value) is dict and set(value) == {'schema_version', 'phase', 'exception_type', 'reason'}
                and value['schema_version'] == 'newrouge.b-route-native-rejection.v1'
                and type(value['phase']) is str
                and value['phase'] in _DIAGNOSTIC_PHASES
                and all(type(value[key]) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,127}', value[key])
                        for key in ('exception_type', 'reason'))):
            records.append(value)
            del records[:-4]
    return records[-4:]


def _run_reader(command, **options):
    # Parent-only import: the isolated reader loads no host project helper before
    # its independently authenticated native source is installed.
    from _b_route_reader_lifetime import GATE, ReaderTransportError, run_reader
    try:
        return run_reader([*command[:-1], GATE + command[-1]], **options)
    except ReaderTransportError as error:
        raise NativeReaderError(error.outcome, stdout=error.stdout, stderr=error.stderr,
                                cleanup=error.cleanup, reason=error.cause_type) from error


class _Diagnostics:
    """Bounded stderr observations; never evidence or a validation result.

    Parent and reader allowances total at most 64 records per capture. Counters
    describe this reader audit's hash reads (including repeats) and directory
    scans, not work in descendants. Progress needs an existing audit operation;
    it adds no timer thread or process and is not a liveness guarantee.
    """
    def __init__(self, scope):
        require(scope in {"parent", "reader"}, "closed_diagnostic_scope_required")
        self.scope = scope
        self.limit = 4 if scope == "parent" else 60
        self.records = 0
        self.hashed_reads = self.hashed_bytes = self.directory_scans = 0
        self.started = self.last_record = time.monotonic()
        self.active = []
        self.last_phase = 'reader_child'
        self.enabled = True

    def _emit(self, phase, event, started):
        if not self.enabled or self.records >= self.limit:
            return
        now = time.monotonic()
        value = {"schema_version": "newrouge.b-route-reader-diagnostic.v1",
                 "scope": self.scope, "phase": phase, "event": event,
                 "elapsed_ms": int(max(0, now - self.started) * 1000),
                 "phase_elapsed_ms": int(max(0, now - started) * 1000),
                 "hashed_reads": self.hashed_reads, "hashed_bytes": self.hashed_bytes,
                 "directory_scans": self.directory_scans}
        self.records += 1
        self.last_record = now
        try:
            sys.stderr.write(json.dumps(value, separators=(",", ":")) + "\n")
            sys.stderr.flush()
        except OSError:
            # A broken diagnostic pipe cannot replace success or the original
            # validation failure. Do not catch any validation operation here.
            self.enabled = False

    @contextmanager
    def phase(self, phase):
        require(phase in _DIAGNOSTIC_PHASES, "closed_diagnostic_phase_required")
        started = time.monotonic()
        self.active.append((phase, started))
        self.last_phase = phase
        self._emit(phase, "start", started)
        try:
            yield
        finally:
            try:
                self._emit(phase, "end", started)
            finally:
                self.active.pop()

    def _progress(self):
        if self.active and time.monotonic() - self.last_record >= 30:
            phase, started = self.active[-1]
            self._emit(phase, "progress", started)

    def hashed_read(self, byte_count):
        self.hashed_reads += 1
        self.hashed_bytes += byte_count
        self._progress()

    def scanned_directory(self):
        self.directory_scans += 1
        self._progress()


_DESCRIBE_FILES = {
    "scripts/python/codex_isolated_model_runner.py": "ab5c5886b748b95e7c28e44d9fadfe73fefdf2ee1ed9651a321816006ac99d78",
    "scripts/python/openai_isolated_model_runner.py": "fbec85b64d0ad355fb3c497e13f619cf9648ab68dca34271e18370eb3bc85827",
    "scripts/python/_planning_skill_common.py": "f44235ae7dc1bd8c7078abf260b6a4262a76a59c282997fb9db37114fc452e19",
    "scripts/python/_codex_app_server.py": "81af09f9949f28338d21912a8906d85c6c1a00abf448c79ce61a77e3d6781dcd",
    "scripts/python/_model_response_identity.py": "de5ca1fd28af4590d9198be4d96c6b23bb86e94c1dc3544920eebaffad5d1d75",
    "scripts/python/_capability_task_evidence.py": "bfce5397f758a4337864da5d4537c1fc602ffcb0a1cb5bd5a4a63bf34444d92e",
    "scripts/python/_capability_input_integrity.py": "9fa2a097d4b8da99cb6365317037c5c0a95d82d7e93e6c715075c4f04ff20b85",
    "scripts/sc/_llm_backend.py": "29bf80c1d2e377c172fb42a13992d3f26f24444d4c17783402f0f66109bd80a8",
}

# This policy is installed before a project directory enters sys.path. It does
# not merely disable cache writes: every Python source module is compiled from
# its actual .py bytes, and a sourceless module is ineligible for verification.
_SOURCE_ONLY_BOOTSTRAP = r'''
import importlib.machinery, sys
class _BRouteSourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        return self.source_to_code(self.get_data(self.path), self.path)
class _BRouteSourceFinder:
    _b_route_source_only = True
    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None:
            return None
        if isinstance(spec.loader, importlib.machinery.SourcelessFileLoader):
            raise ImportError('b_route_frozen_native_reader:sourceless_bytecode_forbidden')
        if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            spec.loader = _BRouteSourceLoader(fullname, spec.origin)
            return spec
        return None
if not any(getattr(finder, '_b_route_source_only', False) for finder in sys.meta_path):
    sys.meta_path.insert(0, _BRouteSourceFinder())
sys.dont_write_bytecode = True
'''


def _install_source_only():
    exec(_SOURCE_ONLY_BOOTSTRAP, {})


def _reader_bootstrap(path, expected_digest):
    require(type(expected_digest) is str and _DIGEST.fullmatch(expected_digest), "authenticated_reader_digest_required")
    return _SOURCE_ONLY_BOOTSTRAP + (
        "\nimport hashlib,pathlib,types\n"
        "p=pathlib.Path(" + repr(str(path)) + ")\n"
        "source=p.read_bytes()\n"
        "assert 'sha256:'+hashlib.sha256(source).hexdigest()==" + repr(expected_digest) + ", 'reader_source_changed_before_execution'\n"
        "r=types.ModuleType('_b_route_frozen_native_reader')\n"
        "r.__file__=str(p)\n"
        "r.__dict__['_authenticated_reader_raw_digest']=" + repr(expected_digest) + "\n"
        "sys.modules[r.__name__]=r\n"
        "exec(compile(source,str(p),'exec'),r.__dict__)\n"
        "r._main()\n")


def _cache_roots(dependencies, source_root=None):
    source_root = Path(source_root) if source_root is not None else TASK_ROOT / 'r5'
    return [str(source_root / 'scripts/python'), str(source_root / 'scripts/sc')] + list(dependencies)


def _original_bootstrap(original_code, dependencies):
    # The frozen verifier remains byte-for-byte literal data. Only the Python
    # import transport preceding it changes; stdin is exclusively its own.
    return _SOURCE_ONLY_BOOTSTRAP + (
        "\nimport hashlib,os,subprocess\n"
        "_original_code=" + repr(original_code) + "\n"
        "assert 'sha256:'+hashlib.sha256(_original_code.encode('utf-8')).hexdigest()==" + repr(digest(original_code.encode('utf-8'))) + "\n"
        "_cache_roots=" + repr(_cache_roots(dependencies)) + "\n"
        "def _describe_cache_guard(event,args):\n"
        " if event!='subprocess.Popen': return\n"
        " command=args[1]\n"
        " if not ((isinstance(command,(list,tuple)) and list(command)[-1:]==['--describe']) or (isinstance(command,str) and command.endswith(' --describe'))): return\n"
        " for root in _cache_roots:\n"
        "  for parent,dirs,names in os.walk(root):\n"
        "   dirs[:]=[name for name in dirs if name not in {'.git','logs'}]\n"
        "   if any(name.lower().endswith(('.pyc','.pyo')) for name in names):\n"
        "    raise RuntimeError('b_route_frozen_native_reader:describe_unverified_bytecode_forbidden')\n"
        "sys.addaudithook(_describe_cache_guard)\n"
        "exec(compile(_original_code,'<unchanged-frozen-R5-verifier>','exec'),{'__name__':'__main__'})\n")


def _original_argv(original_code, dependencies, *, source_root=None):
    if source_root is not None:
        _reader_raw_pin()
    code = (_original_bootstrap(original_code, dependencies) if source_root is None else
            _metadata_bootstrap("original", _transport_spec(original_code, source_root)))
    command = [sys.executable, "-I", "-S", "-B", "-c", code]
    require(len(subprocess.list2cmdline(command)) < 30000, "source_only_child_command_too_long")
    return command


def _authenticated_original_code(transition, audit, source_root=None):
    source_root = SOURCE_ROOT if source_root is None else Path(source_root)
    path = _reference(source_root, "scripts/python/_b_route_execution_transition.py")
    raw = path.read_bytes()
    require(audit.files.get(str(path)) == digest(raw), "original_child_source_not_independently_authenticated")
    values = [node.value.value for node in ast.parse(raw).body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == '_CHILD' for target in node.targets)
              and isinstance(node.value, ast.Constant) and type(node.value.value) is str]
    require(len(values) == 1 and transition._CHILD == values[0], "original_child_code_changed")
    return values[0]


def _describe_cache_guard(dependencies, source_root=None):
    for root in _cache_roots(dependencies, source_root):
        for _, directories, names in os.walk(root):
            directories[:] = [name for name in directories if name not in {'.git', 'logs'}]
            require(not any(name.lower().endswith(('.pyc', '.pyo')) for name in names), "describe_unverified_bytecode_forbidden")


@contextmanager
def _original_transport(original_code, dependencies, source_root=None):
    """Only the exact authenticated child receives the source-only envelope."""
    prior = subprocess.Popen
    original = [sys.executable, "-I", "-S", "-B", "-c", original_code]
    wrapped = _original_argv(original_code, dependencies, source_root=source_root)
    authenticated = source_root is not None
    source_root = SOURCE_ROOT if source_root is None else Path(source_root)
    require(source_root in {SOURCE_ROOT, TASK_ROOT / 'r19', TASK_ROOT / 'r22'}, "closed_transport_source_required")
    describes = [[sys.executable, *flags, str(root / 'scripts/python/codex_isolated_model_runner.py'), '--describe']
                 for root in (TASK_ROOT / 'r5', source_root) for flags in ([], ['-B'])]
    def launch(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and list(command) == original:
            command = wrapped
        elif isinstance(command, (list, tuple)) and list(command) in describes:
            if authenticated:
                command = _describe_argv(_describe_spec(Path(command[-2]).parents[2]), list(command))
            else:
                _describe_cache_guard(dependencies, Path(command[-2]).parents[2])
        return prior(command, *args, **kwargs)
    subprocess.Popen = launch
    try:
        yield
    finally:
        subprocess.Popen = prior


def _source_commits():
    return {str(TASK_ROOT / "r5"): "988022094381c2b190b30c7702ed77aadda3805a",
            str(SOURCE_ROOT): SOURCE_COMMIT, str(TASK_ROOT / "r19"): R19_SOURCE_COMMIT,
            str(TASK_ROOT / "r22"): R22_SOURCE_COMMIT}


def _describe_spec(source_root):
    source_root = Path(source_root)
    require(str(source_root) in _source_commits(), "closed_describe_source_required")
    value = {"source_root": str(source_root), "source_commit": _source_commits()[str(source_root)],
             "files": dict(_DESCRIBE_FILES)}
    _describe_sources(value)
    return value


def _describe_sources(value):
    require(type(value) is dict and set(value) == {"source_root", "source_commit", "files"}
            and value["source_root"] in _source_commits()
            and value["source_commit"] == _source_commits()[value["source_root"]]
            and value["files"] == _DESCRIBE_FILES, "closed_describe_source_required")
    root = _safe(Path(value["source_root"]), directory=True)
    result = {}
    for name, expected in _DESCRIBE_FILES.items():
        path = _reference(root, name)
        info = path.stat()
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, "describe_source_changed")
        result[str(path)] = (raw, (info.st_dev, info.st_ino))
    return result


def _original_reference(original_code, source_root):
    source_root = Path(source_root)
    require(source_root in {SOURCE_ROOT, TASK_ROOT / "r19", TASK_ROOT / "r22"}, "closed_original_source_required")
    path = _reference(source_root, "scripts/python/_b_route_execution_transition.py")
    value = {"source_root": str(source_root), "source_commit": _source_commits()[str(source_root)],
             "path": str(path), "raw_digest": digest(path.read_bytes()),
             "child_digest": digest(original_code.encode("utf-8"))}
    require(_original_program(value) == original_code, "original_child_code_changed")
    return value


def _original_program(value):
    require(type(value) is dict and set(value) == {"source_root", "source_commit", "path", "raw_digest", "child_digest"}
            and value["source_root"] in {str(SOURCE_ROOT), str(TASK_ROOT / "r19"), str(TASK_ROOT / "r22")}
            and value["source_commit"] == _source_commits()[value["source_root"]]
            and value["path"] == str(Path(value["source_root"]) / "scripts/python/_b_route_execution_transition.py"),
            "closed_original_source_required")
    raw = _safe(Path(value["path"])).read_bytes()
    require(digest(raw) == value["raw_digest"], "original_child_source_changed")
    literals = [node.value.value for node in ast.parse(raw).body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "_CHILD" for target in node.targets)
                and isinstance(node.value, ast.Constant) and type(node.value.value) is str]
    require(len(literals) == 1 and digest(literals[0].encode("utf-8")) == value["child_digest"],
            "original_child_code_changed")
    return literals[0]


def _transport_spec(original_code, source_root):
    return {"original": _original_reference(original_code, source_root),
            "describes": [_describe_spec(root) for root in (TASK_ROOT / "r5", Path(source_root))]}


def _metadata_bootstrap(action, payload):
    """Compact authenticated source loader; never embed the large verifier."""
    expected = _reader_raw_pin()
    return _SOURCE_ONLY_BOOTSTRAP + (
        "\nimport hashlib,pathlib,types\n"
        "p=pathlib.Path(" + repr(str(READER)) + ")\n"
        "source=p.read_bytes()\n"
        "assert 'sha256:'+hashlib.sha256(source).hexdigest()==" + repr(expected) + ", 'reader_source_changed'\n"
        "r=types.ModuleType('_b_route_metadata_source')\nr.__file__=str(p)\n"
        "r.__dict__['_authenticated_reader_raw_digest']=" + repr(expected) + "\n"
        "exec(compile(source,str(p),'exec'),r.__dict__)\n"
        "r._metadata_main(" + repr(action) + "," + repr(payload) + ")\n")


def _describe_argv(specification, original):
    script = str(Path(specification["source_root"]) / "scripts/python/codex_isolated_model_runner.py")
    require(original in ([sys.executable, script, "--describe"], [sys.executable, "-B", script, "--describe"]),
            "exact_describe_argv_required")
    command = [sys.executable, "-I", "-S", "-B", "-c",
               _metadata_bootstrap("describe", {"source": specification, "original_argv": original})]
    require(len(subprocess.list2cmdline(command)) < 30000, "source_only_describe_command_too_long")
    return command


def _metadata_describe(payload):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            "isolated_no_site_describe_required")
    require(type(payload) is dict and set(payload) == {"source", "original_argv"}, "closed_describe_payload_required")
    source = payload["source"]
    snapshots = _describe_sources(source)
    root = Path(source["source_root"])
    script = str(root / "scripts/python/codex_isolated_model_runner.py")
    require(payload["original_argv"] in ([sys.executable, script, "--describe"],
                                        [sys.executable, "-B", script, "--describe"]), "exact_describe_argv_required")
    stdlib_roots = (Path(sys.base_prefix) / "Lib", Path(sys.base_prefix) / "DLLs")
    class SourceLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            path = _safe(Path(self.path))
            if str(path) in snapshots:
                raw, identity = snapshots[str(path)]
                info = path.stat()
                require((info.st_dev, info.st_ino) == identity and path.read_bytes() == raw, "describe_source_changed")
                return compile(raw, str(path), "exec", dont_inherit=True, optimize=0)
            return self.source_to_code(self.get_data(self.path), self.path)
    class Finder:
        def find_spec(self, fullname, path=None, target=None):
            found = importlib.machinery.PathFinder.find_spec(fullname, path, target)
            if found is None:
                return None
            if found.origin in {"built-in", "frozen"}:
                return None
            require(found.origin is not None, "describe_import_outside_source_closure")
            origin = Path(found.origin).absolute()
            trusted_stdlib = (any(origin.is_relative_to(base) for base in stdlib_roots)
                              and all(part.casefold() != "site-packages" for part in origin.parts))
            require(str(origin) in snapshots or trusted_stdlib, "describe_import_outside_source_closure")
            require(not isinstance(found.loader, importlib.machinery.SourcelessFileLoader), "describe_sourceless_forbidden")
            if isinstance(found.loader, importlib.machinery.SourceFileLoader):
                found.loader = SourceLoader(fullname, found.origin)
                return found
            require(trusted_stdlib, "describe_import_outside_source_closure")
            return None
    audit = _Audit([root])
    sys.addaudithook(audit.check)
    sys.meta_path.insert(0, Finder())
    sys.path[:0] = [str(root / "scripts/python"), str(root / "scripts/sc")]
    sys.argv = [script, "--describe"]
    try:
        exec(compile(snapshots[script][0], script, "exec", dont_inherit=True, optimize=0),
             {"__name__": "__main__", "__file__": script, "__package__": None})
    finally:
        require(_describe_sources(source) == snapshots, "describe_source_changed_during_execution")


def _metadata_original(payload):
    """Adapt only the authenticated project's own blocked hook, never others."""
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            "isolated_no_site_original_required")
    require(type(payload) is dict and set(payload) == {"original", "describes"}, "closed_original_transport_required")
    original = _original_program(payload["original"])
    expected_roots = [str(TASK_ROOT / "r5"), payload["original"]["source_root"]]
    require(type(payload["describes"]) is list and len(payload["describes"]) == 2
            and [value["source_root"] for value in payload["describes"]] == expected_roots,
            "closed_describe_sources_required")
    mappings = {}
    for specification in payload["describes"]:
        _describe_sources(specification)
        script = str(Path(specification["source_root"]) / "scripts/python/codex_isolated_model_runner.py")
        for flags in ([], ["-B"]):
            logical = [sys.executable, *flags, script, "--describe"]
            mappings[tuple(logical)] = _describe_argv(specification, logical)
    compiled = compile(original, "<unchanged-frozen-R5-verifier>", "exec", dont_inherit=True, optimize=0)
    hook_codes = [value for value in compiled.co_consts if isinstance(value, CodeType) and value.co_name == "blocked"]
    require(len(hook_codes) == 1, "original_project_audit_hook_required")
    namespace = {"__name__": "__main__"}
    registered = []
    add_hook, popen = sys.addaudithook, subprocess.Popen
    def register(callback):
        if (type(callback) is FunctionType and callback.__code__ is hook_codes[0]
                and callback.__globals__ is namespace and callback.__closure__ is None):
            require(not registered, "one_original_project_audit_hook_required")
            probe, installed = object(), []
            def project_only(event, arguments):
                if event == "newrouge.b_route_metadata_audit_probe" and len(arguments) == 1 and arguments[0] is probe:
                    installed.append(True)
                if event == "subprocess.Popen":
                    command = arguments[1]
                    for logical, actual in mappings.items():
                        if ((isinstance(command, (list, tuple)) and list(command) == actual)
                                or (type(command) is str and command == subprocess.list2cmdline(actual))):
                            values = list(arguments)
                            values[1] = list(logical)
                            return callback(event, tuple(values))
                return callback(event, arguments)
            result = add_hook(project_only)
            sys.audit("newrouge.b_route_metadata_audit_probe", probe)
            require(installed == [True], "original_project_audit_registration_not_confirmed")
            registered.append(callback)
            return result
        return add_hook(callback)
    def launch(command, *args, **kwargs):
        require(not kwargs.get("shell") and "executable" not in kwargs, "describe_shell_or_executable_override_forbidden")
        for logical, actual in mappings.items():
            if ((isinstance(command, (list, tuple)) and tuple(command) == logical)
                    or (type(command) is str and command == subprocess.list2cmdline(logical))):
                command = actual
                break
        return popen(command, *args, **kwargs)
    try:
        sys.addaudithook, subprocess.Popen = register, launch
        exec(compiled, namespace)
        require(len(registered) == 1, "original_project_audit_hook_required")
    finally:
        sys.addaudithook, subprocess.Popen = add_hook, popen
        require(_original_program(payload["original"]) == original, "original_child_source_changed_during_execution")


def _metadata_main(action, payload):
    _reader_raw_pin(require_authenticated=True)
    require(action in {"original", "describe"}, "closed_metadata_action_required")
    if action == "describe":
        return _metadata_describe(payload)
    return _metadata_original(payload)


def require(value, reason):
    if not value:
        raise ValueError("b_route_frozen_native_reader:" + reason)


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _reader_raw_pin(*, require_authenticated=False):
    """Inherit loader authority; private construction alone grants no capture."""
    pins = [value for value in (globals().get("_authenticated_reader_raw_digest"),
                               globals().get("_adoption_source_digest")) if value is not None]
    require(all(type(value) is str and _DIGEST.fullmatch(value) for value in pins)
            and (not pins or all(value == pins[0] for value in pins)), "authenticated_reader_digest_required")
    require(not require_authenticated or bool(pins), "authenticated_reader_digest_required")
    actual = digest(_safe(READER).read_bytes())
    require(not pins or actual == pins[0], "reader_source_changed_since_authentication")
    return pins[0] if pins else actual


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, "non_finite_json"))


def _safe(path, *, missing=False, directory=False):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "absolute_safe_path_required")
    require(not any(part.lower() in _FORBIDDEN for part in path.parts)
            and path.name.lower() not in _SECRETS, "credentials_or_sessions_forbidden")
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            require(missing, "missing_ancestor")
            return path
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "reparse_forbidden")
        if item != path or directory:
            require(stat.S_ISDIR(info.st_mode), "directory_required")
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "regular_single_link_file_required")
    return path


def _reference(root, reference):
    require(type(reference) is str and bool(reference) and "\\" not in reference and ":" not in reference
            and not reference.startswith("/") and all(part not in {"", ".", ".."}
                and part[-1] not in {".", " "} and not any(ord(c) < 32 or c in '<>"|?*' for c in part)
                for part in reference.split("/")), "safe_reference_required")
    return _safe(root.joinpath(*reference.split("/")))


def _dependencies():
    candidates = [Path(sys.base_prefix) / "Lib/site-packages",
        TASK_ROOT.parent.parent / "2026-11-04/task-2/python-env/Lib/site-packages",
        TASK_ROOT / "story22-tokenizer-deps"]
    return [str(_safe(path, directory=True)) for path in candidates if path.is_dir()]


def _run_ref(planner, run_id):
    require(planner in {"capabilities", "mvg"} and type(run_id) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id) is not None, "planner_or_run_id")
    return "logs/ci/" + ("capability-planning" if planner == "capabilities" else "mvg-planning") + "/" + run_id


def _source_profile(source_root, source_commit, planner, run_id):
    """Finite source identities, never a caller-selectable native source root."""
    if source_root == str(SOURCE_ROOT) and source_commit == SOURCE_COMMIT:
        return SOURCE_ROOT, SOURCE_COMMIT
    if source_root == str(TASK_ROOT / "r22"):
        require(source_commit == R22_SOURCE_COMMIT and planner == "mvg" and run_id == "m4", "pinned_source_required")
        return TASK_ROOT / "r22", R22_SOURCE_COMMIT
    require(source_root == str(TASK_ROOT / "r19") and source_commit == R19_SOURCE_COMMIT
            and planner == "mvg" and run_id == "m4", "pinned_source_required")
    return TASK_ROOT / "r19", R19_SOURCE_COMMIT


def _request_profile(request):
    return _source_profile(request["source_root"], request["source_commit"], request["planner"], request["run_id"])


def _state_profile(state, planner, run_id, artifact_root=None):
    frame = state.get("b_route_execution_transition", {})
    require(type(frame) is dict, "source_epoch_relabel_forbidden")
    profile = _source_profile(frame.get("current_source_root"), frame.get("current_commit"), planner, run_id)
    if profile[0] == TASK_ROOT / "r22":
        prior = frame.get("prior_transition")
        original = prior.get("prior_transition") if type(prior) is dict else None
        require(frame.get("schema_version") == R22_EPOCH and type(prior) is dict
                and prior.get("schema_version") == R19_EPOCH
                and prior.get("current_source_root") == str(TASK_ROOT / "r19")
                and prior.get("current_commit") == R19_SOURCE_COMMIT
                and type(original) is dict and original.get("current_source_root") == str(SOURCE_ROOT)
                and original.get("current_commit") == SOURCE_COMMIT
                and all(item.get("original_source_root") == str(TASK_ROOT / "r5")
                        and item.get("original_commit") == _source_commits()[str(TASK_ROOT / "r5")]
                        for item in (frame, prior, original)), "typed_r22_selector_source_epoch_required")
        for key, schema, namespace in (("b_route_selector_recovery", R22_RECOVERY, "s1"),
                                       ("b_route_mvg_synthesis_recovery", R19_RECOVERY, "m1")):
            reference = state.get(key)
            require(type(reference) is dict
                    and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
                    and reference["schema_version"] == schema
                    and reference["record_ref"] == "logs/ci/mvg-planning/m4/recovery/" + namespace + "/record.json"
                    and type(reference["record_digest"]) is str and _DIGEST.fullmatch(reference["record_digest"])
                    and type(reference["artifact_root"]) is str
                    and (artifact_root is None or reference["artifact_root"] == str(artifact_root)),
                    "typed_r22_" + namespace + "_recovery_reference_required")
        # The original R22 owner authenticates archived bytes, anchor, history
        # and m1 using the genuine R19 state. Never validate m1 against R22.
    elif profile[0] != SOURCE_ROOT:
        prior = frame.get("prior_transition")
        reference = state.get("b_route_mvg_synthesis_recovery")
        require(frame.get("schema_version") == R19_EPOCH and type(prior) is dict
                and prior.get("current_source_root") == str(SOURCE_ROOT)
                and prior.get("current_commit") == SOURCE_COMMIT,
                "typed_r19_mvg_source_epoch_required")
        require(type(reference) is dict
                and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
                and reference["schema_version"] == R19_RECOVERY
                and reference["record_ref"] == "logs/ci/mvg-planning/m4/recovery/m1/record.json"
                and type(reference["record_digest"]) is str and _DIGEST.fullmatch(reference["record_digest"])
                and type(reference["artifact_root"]) is str
                and (artifact_root is None or reference["artifact_root"] == str(artifact_root)),
                "typed_r19_mvg_recovery_reference_required")
    return profile


def _request(raw):
    request = strict_json(raw)
    require(type(request) is dict and set(request) == _REQUEST_FIELDS, "closed_stdin_required")
    source_root, _ = _request_profile(request)
    require(request["reader_path"] == str(READER) and request["reader_raw_digest"] == _reader_raw_pin(), "reader_source_changed")
    _safe(Path(request["artifact_root"]), directory=True)
    _safe(source_root, directory=True)
    require(type(request["dependency_paths"]) is list and request["dependency_paths"] == _dependencies(), "closed_dependency_roots")
    _run_ref(request["planner"], request["run_id"])
    require(type(request["expected_run_raw_digest"]) is str and _DIGEST.fullmatch(request["expected_run_raw_digest"]), "run_digest_required")
    ref = request["expected_handoff_ref"]
    require(type(ref) is dict and set(ref) == {"path", "schema_version", "raw_digest"}
            and ref["schema_version"] == "newrouge.b-route-planning-handoff.v1"
            and ref["path"] == _run_ref(request["planner"], request["run_id"]) + "/handoff.json"
            and type(ref["raw_digest"]) is str and _DIGEST.fullmatch(ref["raw_digest"]), "exact_handoff_reference_required")
    return request


class _Audit:
    """A process-local deny boundary and complete observed read closure."""
    def __init__(self, roots, diagnostics=None):
        self.roots = tuple(Path(root) for root in roots)
        self.files, self.directories, self.commands = {}, {}, []
        self.busy = False
        self._pipe_tickets = []
        self.diagnostics = diagnostics if diagnostics is not None else _Diagnostics("reader")

    def _command_allowed(self, command):
        return any((isinstance(command, (tuple, list)) and list(command) == allowed)
                   or (type(command) is str and command == subprocess.list2cmdline(allowed))
                   for allowed in self.commands)

    @contextmanager
    def subprocesses(self):
        """Authorize one fresh stdin pipe wrap per approved Popen constructor.

        CPython wraps the parent pipe FD before emitting subprocess.Popen.
        Keep that transport exception scoped to the real handle constructor;
        never treat an arbitrary existing pipe descriptor as write permission.
        """
        audit, base = self, subprocess.Popen
        require(isinstance(base, type) and base.__module__ == "subprocess" and base.__name__ == "Popen",
                "stdlib_popen_class_required")
        get_handles = base._get_handles
        require(get_handles.__module__ == "subprocess", "stdlib_pipe_constructor_required")
        class OwnedPopen(base):
            def __init__(self, command, *positional, **options):
                require(not positional and audit._command_allowed(command), "native_dispatch_forbidden")
                require(not options.get("shell") and options.get("executable") is None
                        and options.get("preexec_fn") is None and options.get("startupinfo") is None
                        and not options.get("pass_fds") and options.get("close_fds", True) is True
                        and not options.get("start_new_session") and options.get("process_group") in (None, -1),
                        "native_process_override_forbidden")
                flags = options.get("creationflags", 0)
                require(type(flags) is int and flags in (0, getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                        "native_process_override_forbidden")
                for name in ("stdin", "stdout", "stderr"):
                    value = options.get(name)
                    permitted = (subprocess.PIPE, subprocess.STDOUT) if name == "stderr" else (subprocess.PIPE,)
                    require(value is None or type(value) is int and value in permitted,
                            "native_existing_stdio_forbidden")
                self._pipe_constructing, self._pipe_ticket = True, None
                self._pipe_thread = threading.get_ident()
                self._pipe_command = command if type(command) is str else tuple(command)
                try:
                    super().__init__(command, **options)
                finally:
                    self._pipe_constructing = False
                    if self._pipe_ticket is not None:
                        audit._pipe_tickets.remove(self._pipe_ticket)
                        self._pipe_ticket = None

            def _get_handles(self, stdin, stdout, stderr):
                require(self._pipe_constructing and self._pipe_ticket is None
                        and self._pipe_thread == threading.get_ident(),
                        "native_pipe_constructor_required")
                handles = get_handles(self, stdin, stdout, stderr)
                if stdin == subprocess.PIPE:
                    parent = handles[1]
                    # On Windows this exact Handle is subsequently Detach'ed
                    # into an FD by the unchanged stdlib Popen constructor.
                    ticket = {"owner": self, "thread": threading.get_ident(),
                              "handle": int(parent), "command": self._pipe_command, "used": False}
                    self._pipe_ticket = ticket
                    audit._pipe_tickets.append(ticket)
                return handles
        subprocess.Popen = OwnedPopen
        try:
            yield
        finally:
            require(subprocess.Popen is OwnedPopen, "native_popen_scope_changed")
            subprocess.Popen = base
            require(not self._pipe_tickets, "native_pipe_constructor_incomplete")

    def _owned_pipe_open(self, fd, mode, flags):
        if (type(fd) is not int or mode not in ("w", "wb") or type(flags) is not int
                or not flags & os.O_WRONLY or flags & (os.O_RDWR | os.O_APPEND | os.O_EXCL)):
            return False
        for ticket in self._pipe_tickets:
            if (ticket["used"] or ticket["thread"] != threading.get_ident()
                    or not ticket["owner"]._pipe_constructing
                    or ticket["owner"]._pipe_ticket is not ticket
                    or not self._command_allowed(ticket["command"])):
                continue
            try:
                if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                    continue
                if os.name == "nt":
                    import msvcrt
                    handle = msvcrt.get_osfhandle(fd)
                else:
                    handle = fd
                if handle != ticket["handle"]:
                    continue
            except (OSError, ValueError, OverflowError):
                continue
            ticket["used"] = True
            return True
        return False

    def _watched(self, path):
        # External 3A observations and their glob/absence directories are part
        # of the eligibility closure too; do not truncate at artifact_root.
        return True

    def _pin_file(self, path):
        if self.busy or not self._watched(path):
            return
        self.busy = True
        try:
            _safe(path, missing=True)
            if path.is_file():
                raw = path.read_bytes()
                value = digest(raw)
                self.diagnostics.hashed_read(len(raw))
            else:
                value = None
            key = str(path)
            require(key not in self.files or self.files[key] == value, "file_changed_during_native_read")
            self.files[key] = value
            if value is None:
                parent = path.parent
                while not parent.exists():
                    parent = parent.parent
                _safe(parent, directory=True)
                members = sorted(item.name for item in parent.iterdir())
                self.diagnostics.scanned_directory()
                key = str(parent)
                require(key not in self.directories or self.directories[key] == members, "directory_changed_during_native_read")
                self.directories[key] = members
        finally:
            self.busy = False

    def _pin_directory(self, path):
        if self.busy or not self._watched(path):
            return
        self.busy = True
        try:
            _safe(path, directory=True)
            members = sorted(item.name for item in path.iterdir())
            self.diagnostics.scanned_directory()
            key = str(path)
            require(key not in self.directories or self.directories[key] == members, "directory_changed_during_native_read")
            self.directories[key] = members
        finally:
            self.busy = False

    def check(self, event, args):
        if event.startswith("socket.") or event in {"os.system", "os.startfile", "os.exec", "os.spawn", "pty.spawn"}:
            require(False, "network_or_process_forbidden")
        if event in {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.truncate",
                     "os.chmod", "os.chown", "os.utime", "shutil.copyfile", "shutil.rmtree"}:
            require(False, "native_reader_write_forbidden")
        if event == "import" and len(args) > 1 and type(args[1]) is str:
            # CPython exposes a filename for an observable extension-module
            # load. Pin the actual .pyd/.so before execution and at closure.
            # This does not claim OS DLL closure or preloaded interpreter bytes.
            if any(args[1].lower().endswith(suffix.lower())
                   for suffix in importlib.machinery.EXTENSION_SUFFIXES):
                self._pin_file(Path(args[1]).absolute())
        if event == "open":
            flags = args[2]
            if self._owned_pipe_open(args[0], args[1], flags):
                return
            require(not isinstance(flags, int) or not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND),
                    "native_reader_write_forbidden")
            require(not isinstance(args[1], str) or not any(char in args[1] for char in "wax+"), "native_reader_write_forbidden")
            if isinstance(args[0], (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(args[0])).absolute()
                require(not any(part.lower() in _FORBIDDEN for part in path.parts)
                        and path.name.lower() not in _SECRETS, "credentials_or_sessions_forbidden")
                self._pin_file(path)
        if event in {"os.scandir", "os.listdir"} and isinstance(args[0], (str, bytes, os.PathLike)):
            self._pin_directory(Path(os.fsdecode(args[0])).absolute())
        if event == "subprocess.Popen":
            command = args[1]
            require(self._command_allowed(command), "native_dispatch_forbidden")


def _profile_source_roots(source_root):
    roots = {TASK_ROOT / name for name in ("r5", "r7", "r8", "r9", "r10")}
    roots.add(source_root)
    if source_root == TASK_ROOT / "r22":
        roots.add(TASK_ROOT / "r19")
    return roots


def _source_commands(state, transition, original_code, dependencies):
    frames = list(state.get("b_route_execution_history", {}).values()) + [state["b_route_execution_transition"]]
    source_root, _ = _state_profile(state, state["planning_runtime"]["planner"], state["run_id"])
    roots = {str(root) for root in _profile_source_roots(source_root)}
    git = shutil.which("git")
    require(git is not None, "git_unavailable")
    commands = [["git", "-C", state["_reader_artifact_root"], "rev-parse", "HEAD"]]
    for frame in frames:
        for root_key, commit_key in (("original_source_root", "original_commit"), ("current_source_root", "current_commit")):
            root, commit = frame[root_key], frame[commit_key]
            require(root in roots and type(commit) is str and _COMMIT.fullmatch(commit), "closed_ancestor_source_required")
            require(root != str(TASK_ROOT / "r19") or commit == R19_SOURCE_COMMIT,
                    "closed_r19_ancestor_commit_required")
            require(root != str(TASK_ROOT / "r22") or commit == R22_SOURCE_COMMIT,
                    "closed_r22_ancestor_commit_required")
            prefix = [git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", root]
            commands += [prefix + ["rev-parse", "--verify", commit + "^{commit}"],
                prefix + ["ls-tree", "-rz", "--full-tree", commit], prefix + ["ls-tree", "-rz", "--full-tree", "HEAD"],
                prefix + ["check-attr", "--source=" + commit, "--stdin", "-z", "text", "eol", "filter", "working-tree-encoding", "ident"],
                prefix + ["ls-files", "--others", "-z"]]
    original = str(TASK_ROOT / "r5")
    commands.append(_original_argv(original_code, dependencies, source_root=source_root))
    for root in (original, str(source_root)):
        runner = str(Path(root) / "scripts/python/codex_isolated_model_runner.py")
        specification = _describe_spec(Path(root))
        commands += [_describe_argv(specification, [sys.executable, *flags, runner, "--describe"])
                     for flags in ([], ["-B"])]
    return commands


def _production(name):
    parts = PurePosixPath(name).parts
    return bool(parts) and parts[0] not in {"logs", ".git"} and not any(
        part in {"tests", "__pycache__"} for part in parts) and (parts[-1] == ".gitattributes"
        or name.endswith(".py") or name.startswith("scripts/sc/") or name.endswith(".schema.json")
        or "schemas" in parts and name.endswith(".json"))


def _independent_source(audit, source_profile=None):
    """Verify frozen bytes before executing any module from that source tree."""
    source_root, source_commit = (SOURCE_ROOT, SOURCE_COMMIT) if source_profile is None else source_profile
    git = shutil.which("git")
    require(git is not None, "git_unavailable")
    prefix = [git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(source_root)]
    operations = [["rev-parse", "--verify", source_commit + "^{commit}"],
        ["ls-tree", "-rz", "--full-tree", source_commit], ["ls-tree", "-rz", "--full-tree", "HEAD"],
        ["check-attr", "--source=" + source_commit, "--stdin", "-z", "text", "eol", "filter", "working-tree-encoding", "ident"],
        ["ls-files", "--others", "-z"]]
    audit.commands = [prefix + operation for operation in operations]
    def invoke(index, payload=None):
        result = subprocess.run(audit.commands[index], input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        require(result.returncode == 0, "independent_source_git_failed")
        return result.stdout
    def tree(raw):
        result = {}
        for row in raw.split(b'\0'):
            if not row:
                continue
            header, name = row.split(b'\t', 1)
            name = name.decode('utf-8')
            if _production(name):
                mode, kind, blob = header.decode('ascii').split(' ')
                require(kind == 'blob' and mode in {'100644', '100755'} and _COMMIT.fullmatch(blob), "independent_source_blob_shape")
                result[name] = (mode, blob)
        return result
    require(invoke(0).decode('ascii').strip() == source_commit, "independent_source_commit_missing")
    tracked = tree(invoke(1))
    require(bool(tracked) and tree(invoke(2)) == tracked, "independent_source_membership_changed")
    fields = ('text', 'eol', 'filter', 'working-tree-encoding', 'ident')
    attr_raw = invoke(3, b'\0'.join(name.encode('utf-8') for name in sorted(tracked)) + b'\0').split(b'\0')
    require(attr_raw[-1] == b'' and (len(attr_raw) - 1) % 3 == 0, "independent_source_attribute_shape")
    attributes = {}
    for index in range(0, len(attr_raw) - 1, 3):
        name, key, value = (item.decode('utf-8') for item in attr_raw[index:index + 3])
        require(name in tracked and key in fields and key not in attributes.setdefault(name, {}), "independent_source_attribute_shape")
        attributes[name][key] = value
    manifest = {}
    for name, (_, expected) in tracked.items():
        path = _reference(source_root, name)
        audit._pin_file(path)
        value = path.read_bytes()
        blob = lambda content: hashlib.sha1(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()
        require(set(attributes.get(name, {})) == set(fields), "independent_source_attribute_shape")
        if blob(value) != expected:
            attrs = attributes[name]
            normalized = value.replace(b'\r\n', b'\n')
            require(attrs['text'] in {'set', 'auto'} and attrs['eol'] == 'crlf'
                    and all(attrs[field] in {'unspecified', 'unset'} for field in fields[2:])
                    and normalized.replace(b'\n', b'\r\n') == value and blob(normalized) == expected,
                    "independent_source_raw_changed")
        manifest[name] = digest(value)
    require(not any(_production(name.decode('utf-8')) for name in invoke(4).split(b'\0') if name), "independent_source_untracked_production")
    return manifest


def _pin_membership(audit, root, patterns):
    for pattern in patterns:
        prefix = []
        for part in pattern.split("/"):
            if any(char in part for char in "*?["):
                break
            prefix.append(part)
        path = root.joinpath(*prefix)
        if path.is_dir():
            for parent, directories, _ in os.walk(path):
                audit._pin_directory(Path(parent))
        else:
            audit._pin_file(path)


def _pin_source_directories(audit, source):
    for parent, directories, _ in os.walk(source):
        directories[:] = [name for name in directories if name not in {".git", "logs", "tests", "__pycache__"}]
        audit._pin_directory(Path(parent))


def _eligibility(state, planner, run_id, artifact_root=None):
    require(state.get("schema_version") == "newrouge.b-route-planning-run.v2"
            and state.get("input_stage") == "3b" and state.get("selection_status") == "selected"
            and state.get("run_id") == run_id and state.get("planning_runtime", {}).get("planner") == planner,
            "complete_original_v2_run_required")
    profile = _state_profile(state, planner, run_id, artifact_root)
    config = state.get("runner_configuration", {})
    require(config.get("backend") == "isolated-runner" and config.get("backend_info", {}).get("requested_reasoning_effort") == "high",
            "official_high_configuration_required")
    require(config.get("runner") == str(TASK_ROOT / "r5/scripts/python/codex_isolated_model_runner.py"), "original_official_runner_required")
    ledger = state.get("capability_selection", {})
    calls = ledger.get("calls", [])
    require(type(ledger.get("total_invocations")) is int and ledger["total_invocations"] == len(calls)
            and [row.get("number") for row in calls] == list(range(1, len(calls) + 1))
            and all(row.get("outcome", {}).get("status") in {"completed", "failed"} for row in calls), "unknown_or_unaccounted_call")
    if profile[0] == TASK_ROOT / "r22":
        require(len(calls) == 13 and all(row["outcome"]["status"] == "completed" for row in calls),
                "completed_r22_thirteen_call_prefix_required")
    if state.get("b_route_partial_generation_recovery") or state.get("b_route_input_path_recovery"):
        require(len(calls) >= 8 and [row["outcome"]["status"] for row in calls[:8]]
                == ["completed"] * 5 + ["failed", "completed", "completed"], "retained_eight_call_prefix_required")
    labels = {"candidate-" + str(i + 1) for i in range(2 if planner == "capabilities" else 3)}
    require(bool(ledger.get("selected")) and all(set(step.get("admissions", {})) == labels for step in ledger["selected"]),
            "native_candidate_cardinality_changed")
    return profile


def _native_witness(request, state, audit):
    root = Path(request["artifact_root"])
    profile = _request_profile(request)
    source_root, source_commit = profile
    require(_state_profile(state, request["planner"], request["run_id"], root) == profile, "source_epoch_relabel_forbidden")
    with audit.diagnostics.phase("independent_source"):
        if source_root == SOURCE_ROOT:
            _independent_source(audit)
        else:
            _independent_source(audit, source_profile=profile)
    with audit.diagnostics.phase("native_import"):
        _install_source_only()
        sys.path[:0] = [str(source_root / "scripts/python"), str(source_root / "scripts/sc"), *request["dependency_paths"]]
        sys.dont_write_bytecode = True
        import _b_route_execution_transition as transition
        import _b_route_planning_runtime as runtime
        import _mvg_capability_selection as selection
        import _mvg_capability_recovery as recovery
        for module in (transition, runtime, selection, recovery):
            require(Path(module.__file__).resolve() == source_root / "scripts/python" / (module.__name__ + ".py"), "native_module_origin_changed")
    commands_state = dict(state, _reader_artifact_root=str(root))
    original_code = (_authenticated_original_code(transition, audit) if source_root == SOURCE_ROOT else
                     _authenticated_original_code(transition, audit, source_root))
    audit.commands = _source_commands(commands_state, transition, original_code, request["dependency_paths"])
    run = root / _run_ref(request["planner"], request["run_id"])
    require(state.get("checkpoint_strategy") == recovery.CHECKPOINT_STRATEGY
            and state.get("recovery", {}).get("store") == str(root / "logs/ci/mvg-recovery"), "active_checkpoint_epoch_required")
    audit._pin_file(root / "logs/ci/mvg-recovery/registry.json")
    with _original_transport(original_code, request["dependency_paths"], source_root), ExitStack() as closing:
        with transition._verification_transaction():
            try:
                with audit.diagnostics.phase("source_open"):
                    before = transition._source_manifest(source_root, source_commit)
                with audit.diagnostics.phase("prefix"):
                    verified = selection.verified_prefix(root, run, state, verify_history=True, recover_counters=False, check_originals=True)
                with audit.diagnostics.phase("validate_input"):
                    runtime.validate_input(root, run, state)
                with audit.diagnostics.phase("published_chain"):
                    selection.verify_published_chain(root, run, state, verified=verified, check_originals=True)
                with audit.diagnostics.phase("active_chain"):
                    recovery.assert_active_chain(root, state, run)
                with audit.diagnostics.phase("frozen_input"):
                    prepared = runtime.frozen_input(root, state, prepared=run / "analysis-input")
                with audit.diagnostics.phase("dependency_closure"):
                    # The R5 subprocess revalidated this full denominator under original
                    # rules. Replay its observations here so every byte, absence and glob
                    # membership is also visible in the parent-persisted closure pins.
                    observations = runtime.sources.Observations(root)
                    dependencies = prepared["inputs"]["dependencies"]
                    for reference, expected in dependencies["files"].items():
                        value = observations.read(reference, optional=expected is None)
                        require((digest(value) if value is not None else None) == expected, "declared_dependency_changed")
                        audit._pin_file(root.joinpath(*reference.split("/")))
                    for watch in dependencies["globs"]:
                        require(observations.watch(watch["patterns"]) == watch["result"], "declared_dependency_membership_changed")
                        _pin_membership(audit, root, watch["patterns"])
                    observations.verify()
                    original_prepared = _reference(root, state["planning_runtime"]["prepared_ref"])
                    for path in sorted(original_prepared.parent.rglob("*")):
                        if path.is_file():
                            audit._pin_file(path)
                    cache = TASK_ROOT / "story22-tokenizer-cache"
                    if cache.is_dir():
                        for path in sorted(cache.rglob("*")):
                            if path.is_file():
                                audit._pin_file(path)
                with audit.diagnostics.phase("handoff"):
                    handoff = runtime.handoff(root, run, state)
                with audit.diagnostics.phase("source_close"):
                    for row in state["capability_selection"]["calls"]:
                        if row["outcome"]["status"] == "completed":
                            binding = strict_json(_reference(run, row["request_identity"]["execution_binding_path"]).read_bytes())
                            require(binding.get("runner_info", {}).get("requested_reasoning_effort") == "high", "completed_call_high_evidence_required")
                    for source in sorted(_profile_source_roots(source_root)):
                        _pin_source_directories(audit, source)
                    require(before == transition._source_manifest(source_root, source_commit), "native_source_drift")
            finally:
                # Enter immediately before the original transaction exits; the
                # outer ExitStack closes timing after its fresh R5 witness and
                # source/artifact close, including exceptional unwinding.
                closing.enter_context(audit.diagnostics.phase("transaction_close"))
    for name, module in list(sys.modules.items()):
        if name.startswith(("_b_route_", "_mvg_", "_planning_")) and name != __name__ and getattr(module, "__file__", None):
            require(Path(module.__file__).resolve().is_relative_to(source_root / "scripts/python"), "native_transitive_module_origin_changed")
    return handoff, prepared


def _capture_request(request, audit):
    root = Path(request["artifact_root"])
    run_path = _reference(root, _run_ref(request["planner"], request["run_id"]) + "/run.json")
    audit._pin_file(run_path)
    raw = run_path.read_bytes()
    require(digest(raw) == request["expected_run_raw_digest"], "original_run_raw_changed")
    state = strict_json(raw)
    profile = _eligibility(state, request["planner"], request["run_id"], root)
    require(profile == _request_profile(request), "source_epoch_relabel_forbidden")
    handoff, prepared = _native_witness(request, state, audit)
    with audit.diagnostics.phase("artifact_closure"):
        handoff_path = _reference(root, request["expected_handoff_ref"]["path"])
        audit._pin_file(handoff_path)
        handoff_raw = handoff_path.read_bytes()
        require(digest(handoff_raw) == request["expected_handoff_ref"]["raw_digest"]
                and canonical(strict_json(handoff_raw)) == canonical(handoff), "original_handoff_changed")
        require(run_path.read_bytes() == raw, "original_run_drift")
        require(prepared.get("input_identity") == state["planning_runtime"]["input_identity"]
                and digest(canonical(prepared)) == state["planning_runtime"]["frozen_sha256"], "original_prepared_changed")
        # Include every native run artifact, including failed-but-charged evidence.
        # The caller owns the coordinator byte lock; it is metadata, never proof data.
        for path in sorted(run_path.parent.rglob("*")):
            if path.is_file() and path.name != "capability-coordinator.lock":
                audit._pin_file(path)
        audit._pin_file(READER)
        result = {"schema_version": SCHEMA, "handoff": handoff, "prepared": prepared,
            "run_identity": {"path": str(run_path), "raw_digest": digest(raw), "canonical_digest": digest(canonical(state)), "byte_count": len(raw)},
            "source_identity": {"source_root": str(profile[0]), "source_commit": profile[1],
                                "reader_path": str(READER), "reader_raw_digest": request["reader_raw_digest"]},
            "files": dict(sorted(audit.files.items())), "directories": dict(sorted(audit.directories.items()))}
        result["result_digest"] = digest(canonical(result))
    with audit.diagnostics.phase("child_verify_capture"):
        verify_capture(root, result)
    return result


def _main():
    _reader_raw_pin(require_authenticated=True)
    _install_source_only()
    request = _request(sys.stdin.buffer.read())
    watched = [Path(request["artifact_root"]), READER.parent,
               *sorted(_profile_source_roots(_request_profile(request)[0])),
               *map(Path, request["dependency_paths"])]
    audit = _Audit(watched)
    sys.addaudithook(audit.check)
    try:
        with audit.subprocesses(), redirect_stdout(io.StringIO()):
            result = _capture_request(request, audit)
    except Exception as error:
        # Retain a bounded reason instead of printing a bootstrap traceback.
        print(json.dumps({'schema_version': 'newrouge.b-route-native-rejection.v1',
            'phase': audit.diagnostics.last_phase, 'exception_type': type(error).__name__,
            'reason': _safe_reason(error)}, ensure_ascii=True, separators=(',', ':')), file=sys.stderr)
        raise SystemExit(2) from None
    # The pipe is a JSON transport: ASCII escapes survive Windows locale codecs
    # and decode to the exact original Unicode values and canonical identities.
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False))


def capture_completed(root, *, planner, run_id, state_raw, expected_handoff_ref):
    """Caller holds both original locks; launch one read-only frozen reader."""
    reader_pin = _reader_raw_pin(require_authenticated=True)
    root = _safe(Path(root).absolute(), directory=True)
    require(type(state_raw) is bytes, "original_state_bytes_required")
    profile = _state_profile(strict_json(state_raw), planner, run_id, root)
    request = {"source_root": str(profile[0]), "source_commit": profile[1], "artifact_root": str(root),
        "planner": planner, "run_id": run_id, "expected_run_raw_digest": digest(state_raw),
        "expected_handoff_ref": expected_handoff_ref, "dependency_paths": _dependencies(),
        "reader_path": str(READER), "reader_raw_digest": reader_pin}
    _request(canonical(request))
    code = _reader_bootstrap(READER, request["reader_raw_digest"])
    environment = dict(os.environ)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", GIT_OPTIONAL_LOCKS="0",
                       TIKTOKEN_CACHE_DIR=str(TASK_ROOT / "story22-tokenizer-cache"))
    # Replay uses the existing approved offline cache; the audit still rejects writes.
    # The full retained-prefix/handoff/closure replay has its own bounded host budget,
    # independent of every frozen model invocation and funding limit.
    diagnostics = _Diagnostics("parent")
    with diagnostics.phase("reader_child"):
        try:
            completed = _run_reader([sys.executable, "-X", "dev", "-I", "-S", "-B", "-c", code],
                input=canonical(request), env=environment, cwd=profile[0], timeout=3600)
        except subprocess.TimeoutExpired as error:
            # Also cover a transport seam refusing before it can establish Job
            # quiescence. No result or known-empty claim is manufactured.
            raise NativeReaderError('timeout', stdout=error.stdout or b'', stderr=error.stderr or b'') from error
    if completed.returncode != 0:
        raise NativeReaderError('native_rejected', stdout=completed.stdout, stderr=completed.stderr,
                                cleanup='confirmed_empty', exit_code=completed.returncode)
    try:
        result = strict_json(completed.stdout)
        with diagnostics.phase("parent_verify_capture"):
            verify_capture(root, result)
    except (ValueError, TypeError, KeyError, OSError) as error:
        raise NativeReaderError('invalid_capture', stdout=completed.stdout, stderr=completed.stderr,
                                cleanup='confirmed_empty', reason=_safe_reason(error)) from error
    require(result["run_identity"]["raw_digest"] == digest(state_raw), "child_run_identity_changed")
    return result


def verify_capture(root, capture):
    """Cheap local recheck at persistence; no imports of native rules or child."""
    root = _safe(Path(root).absolute(), directory=True)
    require(type(capture) is dict and set(capture) == _RESULT_FIELDS and capture["schema_version"] == SCHEMA, "closed_capture_required")
    require(capture["result_digest"] == digest(canonical({key: value for key, value in capture.items() if key != "result_digest"})), "capture_digest_changed")
    source = capture["source_identity"]
    require(type(source) is dict and set(source) == {"source_root", "source_commit", "reader_path", "reader_raw_digest"},
            "frozen_reader_identity_changed")
    require((source["source_root"], source["source_commit"]) in {
                (str(SOURCE_ROOT), SOURCE_COMMIT), (str(TASK_ROOT / "r19"), R19_SOURCE_COMMIT),
                (str(TASK_ROOT / "r22"), R22_SOURCE_COMMIT)}
            and source["reader_path"] == str(READER)
            and source["reader_raw_digest"] == _reader_raw_pin(), "frozen_reader_identity_changed")
    require(type(capture["files"]) is dict and type(capture["directories"]) is dict and bool(capture["files"]), "closure_required")
    for name, expected in list(capture["files"].items()):
        path = _safe(Path(name), missing=True)
        require(expected is None or type(expected) is str and _DIGEST.fullmatch(expected), "closure_digest_shape")
        require((digest(path.read_bytes()) if path.is_file() else None) == expected, "closure_file_changed:" + name)
    for name, expected in list(capture["directories"].items()):
        require(type(expected) is list and expected == sorted(set(expected)) and all(type(item) is str for item in expected), "directory_pin_shape")
        path = _safe(Path(name), directory=True)
        require(sorted(item.name for item in path.iterdir()) == expected, "closure_directory_changed:" + name)
    identity = capture["run_identity"]
    require(type(identity) is dict and set(identity) == {"path", "raw_digest", "canonical_digest", "byte_count"}, "closed_run_identity")
    path = _safe(Path(identity["path"]))
    require(path.is_relative_to(root) and path.name == "run.json" and capture["files"].get(str(path)) == identity["raw_digest"], "run_closure_required")
    raw = path.read_bytes()
    require(type(identity["byte_count"]) is int and identity["byte_count"] == len(raw)
            and identity["raw_digest"] == digest(raw) and identity["canonical_digest"] == digest(canonical(strict_json(raw))), "run_identity_changed")
    state = strict_json(raw)
    profile = _eligibility(state, state["planning_runtime"]["planner"], state["run_id"], root)
    require((str(profile[0]), profile[1]) == (source["source_root"], source["source_commit"]),
            "source_epoch_relabel_forbidden")
    require(capture["prepared"].get("input_identity") == state["planning_runtime"]["input_identity"]
            and digest(canonical(capture["prepared"])) == state["planning_runtime"]["frozen_sha256"], "captured_prepared_changed")
    handoff_path = _safe(path.with_name("handoff.json"))
    require(capture["files"].get(str(handoff_path)) == digest(handoff_path.read_bytes())
            and canonical(strict_json(handoff_path.read_bytes())) == canonical(capture["handoff"]), "captured_handoff_changed")
