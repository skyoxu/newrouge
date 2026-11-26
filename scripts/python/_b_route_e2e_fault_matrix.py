"""Story 4.10 end-to-end Windows fault, shared-change, evidence authenticity,
and cross-surface parity verification matrix + Epic 4 -> Epic 5 handoff service.

Strictly read-only on the target repository root:
- Runs controlled real Windows lock contention (msvcrt.locking in real child
  processes terminated with taskkill /F /T) and 6-stage mid-lifecycle child
  exits/restarts strictly inside ephemeral temporary directories.
- Invokes the real Epic 2-4 producers, readers, gates, scope runner, evidence
  reuse, completion verdict, Knowledge projection, planning page, observability,
  and Story 4.9 consumer alignment audit.
- Uses _b_route_codec.strict_json_loads exclusively (zero private json.loads).
- Never modifies target repository authority files, never switches default B,
  never retires A write compatibility, never refreshes Knowledge implicitly,
  and never claims protocol fixture output as real Godot/C# Reward acceptance.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any

import _b_route_chapter4_binding as ch4_binding
import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_rec
import _b_route_chapter7_slice as ch7_slice
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_completion_verdict as completion_verdict
import _b_route_consumer_alignment as alignment
import _b_route_defect_routing as defect_routing
import _b_route_entrypoint_parity as parity
import _b_route_evidence_reuse as evidence_reuse
import _b_route_impact_closure as impact_closure
import _b_route_input_set as input_set_mod
import _b_route_inventory as inventory
import _b_route_knowledge_projection as knowledge_projection
import _b_route_observability as observability
import _b_route_operation_scope as op_scope
import _b_route_planning_page as planning_page
import _b_route_records as records
import _b_route_scope_runner as scope_runner
import _b_route_task_resolver as task_resolver
import _b_route_verification_scope as verification_scope
import _planning_apply_journal as journal
from _mvg_manifest import manifest_sha256


SCHEMA_VERSION = "newrouge.b-route-e2e-fault-matrix.v1"
DIAGNOSTIC_KEYS = ("reason_code", "stage", "entity_id", "expected", "actual", "resume_ref")

INVARIANTS: dict[str, Any] = {
    "protocol_fixture_is_not_reward_gameplay_acceptance": True,
    "runtime_verified": False,
    "default_b_enabled": False,
    "a_write_compatibility_retired": False,
    "second_state_machine_created": False,
    "implicit_global_refresh_performed": False,
    "mock_os_exception_claimed_as_windows_proof": False,
}

UNTESTED_WINDOWS_BOUNDARIES: tuple[str, ...] = (
    "hardware_power_loss_and_disk_controller_write_cache_flush",
    "windows_kernel_bugcheck_bsod_or_unexpected_host_reboot",
    "ntfs_filter_driver_antivirus_async_quarantine_or_volume_unplug",
    "bitlocker_volume_lock_or_smb_network_share_disconnect",
    "real_godot_451_windows_gui_input_and_csharp_reward_runtime",
)

EPIC5_DEFERRED_GATES: tuple[dict[str, Any], ...] = (
    {
        "gate_id": "reward_production_csharp_thin_adapter_and_controlled_command",
        "stories": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
        "status": "pending_epic5",
        "description": (
            "Real Reward gap boundary, zero-Task 3B Reward adoption, incremental 3C "
            "binding, controlled production C# command, native Reward.tscn thin adapter, "
            "and continue/re-entry save recovery remain deferred to Epic 5."
        ),
    },
    {
        "gate_id": "reward_dual_path_real_windows_godot_csharp_evidence",
        "stories": ["5.2", "5.3", "5.7"],
        "status": "pending_epic5",
        "description": (
            "Dual-path real Windows Godot 4.5.1 + C# execution with genuine OS/engine "
            "InputEvent verification and independent manual signoff remains deferred to Epic 5."
        ),
    },
    {
        "gate_id": "conditional_default_b_switch_for_new_requirements",
        "stories": ["5.8"],
        "status": "pending_epic5",
        "description": (
            "Switching default_route from A to B for new requirements requires Epic 5 "
            "real Reward dual-path evidence and governed policy review."
        ),
    },
    {
        "gate_id": "independent_a_exit_gate_and_actual_revocation",
        "stories": ["5.9", "5.10", "5.11"],
        "status": "pending_epic5",
        "description": (
            "Independent A exit qualification, actual A write compatibility revocation, "
            "and compensation rollback closure remain deferred to Epic 5."
        ),
    },
)

SCRIPTS_PY = Path(__file__).resolve().parent
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"


# ---------------------------------------------------------------------------
# Child process scripts (real Windows msvcrt lock & mid-stage exit harness)
# ---------------------------------------------------------------------------

_WIN_MSVCRT_LOCK_HOLDER_CODE = r"""
import msvcrt
import os
from pathlib import Path
import sys
import time

lock_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
lock_path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
if os.fstat(fd).st_size == 0:
    os.write(fd, b"0")
os.lseek(fd, 0, os.SEEK_SET)
msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
ready_path.write_text(f"LOCKED:{os.getpid()}\n", encoding="utf-8")
while True:
    time.sleep(0.05)
"""

_STAGE_CHILD_RUNNER_CODE = r"""
import json
import os
from pathlib import Path
import sys

scripts_py = sys.argv[1]
scripts_sc = sys.argv[2]
root = Path(sys.argv[3]).resolve()
action = sys.argv[4]
op_id = sys.argv[5]
arg_extra = sys.argv[6]
crash_at = sys.argv[7]
ready_file = sys.argv[8]

for p in (scripts_py, scripts_sc):
    if p not in sys.path:
        sys.path.insert(0, p)

import _b_route_chapter4_binding as ch4
import _b_route_codec as codec
import _b_route_commit as commit
import _planning_apply_journal as journal

if crash_at and crash_at != "NONE":
    def _fault_checkpoint(name):
        if name == crash_at:
            if ready_file and ready_file != "NONE":
                Path(ready_file).write_text(f"CRASHING:{name}:{os.getpid()}\n", encoding="utf-8")
            os._exit(73)
    commit._checkpoint = _fault_checkpoint

    if crash_at in ("mid_prepare_write", "mid_reserve_write"):
        _orig_op_write = journal._operation_write
        _orig_append_event = ch4.append_event
        _op_write_reached = [False]

        def _hooked_op_write(*args, **kwargs):
            _op_write_reached[0] = True
            return _orig_op_write(*args, **kwargs)

        def _hooked_append_event(*args, **kwargs):
            if _op_write_reached[0]:
                if ready_file and ready_file != "NONE":
                    Path(ready_file).write_text(f"CRASHING:{crash_at}:{os.getpid()}\n", encoding="utf-8")
                os._exit(73)
            return _orig_append_event(*args, **kwargs)

        journal._operation_write = _hooked_op_write
        ch4.append_event = _hooked_append_event

try:
    if action == "prepare":
        res = ch4.prepare(root, operation_id=op_id, request_ref=arg_extra)
    elif action == "reserve":
        res = ch4.reserve(root, operation_id=op_id)
    elif action in ("apply", "verify", "publish"):
        res = commit.execute(root, operation_id=op_id, stage=action)
    elif action == "recover":
        res = commit.recover(root, operation_id=op_id)
    else:
        raise ValueError(f"unsupported action: {action}")
    print(json.dumps(res, ensure_ascii=True, allow_nan=False))
    raise SystemExit(0)
except codec.CodecError as err:
    print(json.dumps({"ok": False, "status": "blocked", "diagnostic": err.diagnostic.to_dict()}, ensure_ascii=True))
    raise SystemExit(2)
"""

_PARALLEL_WORKER_CODE = r"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
scripts_py = sys.argv[1]
scripts_sc = sys.argv[2]
mode = sys.argv[3]
out_file = Path(sys.argv[4])
extra = sys.argv[5:]

for p in (scripts_py, scripts_sc):
    if p not in sys.path:
        sys.path.insert(0, p)

import _b_route_e2e_fault_matrix as m

res = m._dispatch_parallel_worker(mode, extra)
out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_bytes(m._encoded_json(res))
"""

_PROTOCOL_FIXTURE_RUNNER_CODE = r'''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
inv_log = os.environ.get("E2E_FIXTURE_INVOCATIONS", "")
fail_selector = os.environ.get("E2E_FIXTURE_FAIL_SELECTOR", "")
fail_suite = os.environ.get("E2E_FIXTURE_FAIL_SUITE", "")
emit_empty = os.environ.get("E2E_FIXTURE_EMIT_EMPTY", "") == "1"
emit_skipped = os.environ.get("E2E_FIXTURE_EMIT_SKIPPED", "") == "1"
assert_clean = os.environ.get("E2E_FIXTURE_ASSERT_CLEAN", "") == "1"


def log_call(entry):
    if inv_log:
        Path(inv_log).parent.mkdir(parents=True, exist_ok=True)
        with open(inv_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def check_and_touch_isolated_state(label):
    appdata = Path(os.environ.get("APPDATA", ""))
    localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
    tempdir = Path(os.environ.get("TEMP", ""))
    m1 = appdata / "e2e_mutable_save.txt"
    m2 = localappdata / "e2e_mutable_local.txt"
    m3 = tempdir / "e2e_mutable_temp.txt"
    leaked = m1.exists() or m2.exists() or m3.exists()
    for d in (appdata, localappdata, tempdir):
        d.mkdir(parents=True, exist_ok=True)
    m1.write_text(f"written:{label}\n", encoding="utf-8")
    m2.write_text(f"written:{label}\n", encoding="utf-8")
    m3.write_text(f"written:{label}\n", encoding="utf-8")
    return leaked, str(appdata), str(localappdata), str(tempdir)


if args and args[0] == "test":
    selector = ""
    results_dir = ""
    no_build = "--no-build" in args
    for i, tok in enumerate(args):
        if tok == "--filter" and i + 1 < len(args):
            selector = args[i + 1].removeprefix("FullyQualifiedName~")
        elif tok == "--results-directory" and i + 1 < len(args):
            results_dir = args[i + 1]
    leaked, appdata_s, local_s, temp_s = check_and_touch_isolated_state(selector)
    if not no_build:
        for rel, body in (
            ("Game.Core/bin/Debug/net8.0/Game.Core.dll", b"E2E-CORE-DLL-V1"),
            ("Game.Core/obj/project.assets.json", b'{"version": 3, "targets": {}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.dll", b"E2E-TESTS-DLL-V1"),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.deps.json", b'{"runtimeTarget": {"name": ".NETCoreApp,Version=v8.0"}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.runtimeconfig.json", b'{"runtimeOptions": {"tfm": "net8.0"}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/testhost.dll", b"E2E-TESTHOST-V1"),
            ("Game.Core.Tests/obj/project.assets.json", b'{"version": 3, "targets": {}}\n'),
            ("Game.Core.Tests/obj/Game.Core.Tests.csproj.nuget.dgspec.json", b'{"format": 1}\n'),
        ):
            p = Path(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
    log_call({
        "kind": "dotnet",
        "selector": selector,
        "no_build": no_build,
        "appdata": appdata_s,
        "localappdata": local_s,
        "temp": temp_s,
        "leaked": leaked,
    })
    out = Path(results_dir) / "results.trx"
    out.parent.mkdir(parents=True, exist_ok=True)
    if emit_empty:
        out.write_text('<TestRun><Counters total="0" passed="0" failed="0"/></TestRun>', encoding="utf-8")
        sys.exit(0)
    if emit_skipped:
        out.write_text(
            f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="NotExecuted"/>'
            '<Counters total="1" passed="0" failed="0" notExecuted="1"/></TestRun>',
            encoding="utf-8",
        )
        sys.exit(0)
    if (assert_clean and leaked) or (fail_selector and fail_selector == selector):
        out.write_text(
            f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="Failed"/>'
            '<Counters total="1" passed="0" failed="1"/></TestRun>',
            encoding="utf-8",
        )
        sys.exit(1)
    out.write_text(
        f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="Passed"/>'
        '<Counters total="1" passed="1" failed="0"/></TestRun>',
        encoding="utf-8",
    )
    sys.exit(0)
else:
    add_path = ""
    rd = ""
    prewarm = "--prewarm" in args
    challenge_mode = os.environ.get("MVG_INPUT_CHALLENGE", "") == "disconnect-reward-input"
    for i, tok in enumerate(args):
        if tok == "--add" and i + 1 < len(args):
            add_path = args[i + 1]
        elif tok == "--rd" and i + 1 < len(args):
            rd = args[i + 1]
    suite = Path(add_path).stem
    leaked, appdata_s, local_s, temp_s = check_and_touch_isolated_state(suite)
    if prewarm:
        cache = Path("Tests.Godot/.godot/uid_cache.bin")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"E2E-PREWARM-V1")
    log_call({
        "kind": "gdunit",
        "suite": suite,
        "prewarm": prewarm,
        "challenge": challenge_mode,
        "appdata": appdata_s,
        "localappdata": local_s,
        "temp": temp_s,
        "leaked": leaked,
    })
    out = Path(rd) / "report_1" / "results.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    if emit_empty:
        out.write_text(f'<testsuites tests="0"><testsuite name="{suite}" tests="0" failures="0" errors="0" skipped="0"/></testsuites>', encoding="utf-8")
        sys.exit(0)
    if emit_skipped:
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="0" errors="0" skipped="1">'
            f'<testcase name="test_case" classname="{suite}"><skipped/></testcase></testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(0)
    if challenge_mode or (assert_clean and leaked) or (fail_suite and fail_suite == suite):
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="1" errors="0" skipped="0">'
            f'<testcase name="test_case" classname="{suite}"><failure message="failed"/></testcase></testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(1)
    out.write_text(
        f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase name="test_case" classname="{suite}"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    sys.exit(0)
'''


# ---------------------------------------------------------------------------
# Generic helpers (strictly codec.strict_json_loads; never raw json.loads)
# ---------------------------------------------------------------------------

def _diag(
    code: codec.ReasonCode,
    stage: codec.Stage,
    entity_id: Any,
    expected: Any,
    actual: Any,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref).to_dict()


def _is_valid_six_field_diag(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value.keys()) != set(DIAGNOSTIC_KEYS):
        return False
    return value.get("reason_code") in {c.value for c in codec.ReasonCode}


def _is_valid_obs_diag(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value.keys()) != (set(DIAGNOSTIC_KEYS) | {"diagnostic_category", "original_locator"}):
        return False
    return _is_valid_six_field_diag({k: value[k] for k in DIAGNOSTIC_KEYS})


def _encoded_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _put_bytes(root: Path, rel: str, data: bytes | str) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return raw


def _put_json(root: Path, rel: str, value: Any) -> bytes:
    return _put_bytes(root, rel, _encoded_json(value))


def _read_json(root: Path, rel: str) -> Any:
    return codec.strict_json_loads((root / rel).read_bytes())


def _typed_ref(path: str, schema_version: str, entity_id: str, revision: int, raw: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.raw_digest(raw),
        "verification_mode": "raw",
        "codec_version": None,
    }


def _canonical_ref(root: Path, schema_version: str, rel: str, entity_id: str, revision: int = 1) -> dict[str, Any]:
    doc = _read_json(root, rel)
    return {
        "path": rel,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.canonical_digest(doc),
        "verification_mode": "canonical",
        "codec_version": codec.CODEC_VERSION,
    }


def _owned_ref(owner: str, ref: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    return {
        "owner": owner,
        "ref": ref,
        "files": [{"path": p, "raw_digest": codec.raw_digest(raw)} for p, raw in files],
    }


def _four_parts(*, domain: bool = True, adapter: bool = True, binding: bool = True, scene: bool = False) -> list[dict[str, Any]]:
    specs = (
        ("domain_rules", domain, "Core deterministic domain rules."),
        ("csharp_adapter", adapter, "Thin C# adapter forwarding commands."),
        ("binding", binding, "Resource and event binding contracts."),
        ("scene", scene, "Godot scene wiring for display."),
    )
    return [
        {
            "kind": kind,
            "applicability": "applicable" if applicable else "not_applicable",
            "rationale": desc if applicable else f"{kind} is not applicable for this flow.",
            "responsibilities": [desc] if applicable else [],
        }
        for kind, applicable, desc in specs
    ]


def _stage5_resp(summary: str, stage5_meta: dict[str, Any], stage4_meta: dict[str, Any]) -> str:
    return (
        f"{summary}\n"
        f"[stage4-meta]{json.dumps(stage4_meta, ensure_ascii=False, separators=(',', ':'))}[/stage4-meta]\n"
        f"[stage5-meta]{json.dumps(stage5_meta, ensure_ascii=False, separators=(',', ':'))}[/stage5-meta]"
    )


def _git(root: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=30,
            env=env,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "git",
            f"git {' '.join(args)} exit 0",
            str(exc)[:200],
            None,
        )) from exc
    return proc.stdout.strip()


def _ephemeral_temp_base() -> str:
    """Choose a short plain non-reparse temp directory on Windows; fail closed if none is safe."""
    for candidate in (
        os.environ.get("SC_KNOWLEDGE_PLANNING_CHECKOUT_ROOT"),
        os.environ.get("ADOPTION_TEST_TEMP"),
        os.environ.get("BR_TEST_TEMP"),
        tempfile.gettempdir(),
    ):
        if not candidate:
            continue
        p = Path(candidate)
        if p.is_dir():
            try:
                for anc in reversed((p.absolute(), *p.absolute().parents)):
                    inventory.no_reparse(anc)
                return str(p.resolve())
            except (OSError, ValueError):
                continue
    raise codec.CodecError(codec.Diagnostic(
        codec.ReasonCode.UNSAFE_PATH,
        codec.Stage.PATH,
        "temp_base",
        "safe non-reparse temporary directory",
        None,
        None,
    ))


def _rmtree_readonly_safe(path: Path) -> None:
    """Remove an ephemeral workspace with read-only S_IWRITE reset and bounded Windows retry."""
    def _on_exc(func: Any, p: str, _exc: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(p)
        except OSError:
            pass

    for attempt in range(6):
        if not os.path.lexists(path):
            return
        try:
            shutil.rmtree(path, onexc=_on_exc)
            return
        except OSError:
            if attempt == 5:
                shutil.rmtree(path, ignore_errors=True)
                return
            time.sleep(0.05 * (attempt + 1))


@contextlib.contextmanager
def _temp_workspace(prefix: str):
    base = _ephemeral_temp_base()
    tmp_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=base)).resolve()
    try:
        yield tmp_dir
    finally:
        _rmtree_readonly_safe(tmp_dir)


def _copy_repo_schemas_and_adr(source_root: Path, dest_root: Path) -> None:
    adr_rel = task_resolver.ADR_0040
    _put_bytes(dest_root, adr_rel, (source_root / adr_rel).read_bytes())
    schemas_dir = source_root / "docs/planning/b-route/schemas"
    for schema_file in sorted(schemas_dir.glob("*.schema.json")):
        _put_bytes(dest_root, f"docs/planning/b-route/schemas/{schema_file.name}", schema_file.read_bytes())
    excl_rel = "knowledge/policies/source-exclusions.v1.json"
    if (source_root / excl_rel).is_file():
        _put_bytes(dest_root, excl_rel, (source_root / excl_rel).read_bytes())


def _kill_child_process_tree(proc: subprocess.Popen[Any]) -> bool:
    """Forcibly terminate a Windows child process tree via taskkill /F /T (or kill on non-Windows)."""
    if proc.poll() is not None:
        return True
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    return proc.returncode is not None


def _run_stage_child(
    root: Path,
    *,
    action: str,
    op_id: str,
    arg_extra: str = "",
    crash_at: str = "NONE",
    ready_file: str = "NONE",
    timeout_sec: float = 90.0,
) -> tuple[int, dict[str, Any] | None, str]:
    cmd = [
        sys.executable,
        "-B",
        "-c",
        _STAGE_CHILD_RUNNER_CODE,
        str(SCRIPTS_PY),
        str(SCRIPTS_SC),
        str(root),
        action,
        op_id,
        arg_extra,
        crash_at,
        ready_file,
    ]
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "cwd": str(root),
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **kwargs)
    try:
        stdout_s, stderr_s = proc.communicate(timeout=timeout_sec)
        rc = proc.returncode if proc.returncode is not None else 124
    except subprocess.TimeoutExpired:
        _kill_child_process_tree(proc)
        stdout_s, stderr_s = "", f"stage child timed out after {timeout_sec}s"
        rc = 124
    finally:
        _kill_child_process_tree(proc)
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    parsed: dict[str, Any] | None = None
    out = (stdout_s or "").strip()
    if out:
        last_line = out.splitlines()[-1].strip()
        try:
            obj = codec.strict_json_loads(last_line.encode("utf-8"))
            if isinstance(obj, dict):
                parsed = obj
        except codec.CodecError:
            parsed = None
    return rc, parsed, (stderr_s or "")


def _start_parallel_workers(
    work_dir: Path,
    specs: dict[str, tuple[str, list[str]]],
) -> dict[str, tuple[subprocess.Popen[Any], Path]]:
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    handles: dict[str, tuple[subprocess.Popen[Any], Path]] = {}
    try:
        for key, (mode, extra_args) in specs.items():
            out_path = work_dir / f"worker-{key}.json"
            cmd = [
                sys.executable,
                "-B",
                "-c",
                _PARALLEL_WORKER_CODE,
                str(SCRIPTS_PY),
                str(SCRIPTS_SC),
                mode,
                str(out_path),
                *extra_args,
            ]
            kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "cwd": str(work_dir),
                "env": env,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            handles[key] = (subprocess.Popen(cmd, **kwargs), out_path)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        _cleanup_parallel_workers(handles)
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "parallel_workers",
            "spawn isolated verification workers",
            str(exc)[:200],
            None,
        )) from exc
    return handles


def _cleanup_parallel_workers(handles: dict[str, tuple[subprocess.Popen[Any], Path]]) -> None:
    for proc, _ in handles.values():
        try:
            _kill_child_process_tree(proc)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except OSError:
                pass
            try:
                if proc.stderr:
                    proc.stderr.close()
            except OSError:
                pass


def _collect_parallel_workers(
    handles: dict[str, tuple[subprocess.Popen[Any], Path]],
    *,
    timeout_sec: float = 240.0,
) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    results: dict[str, dict[str, Any]] = {}
    for key, (proc, out_path) in handles.items():
        rem = max(1.0, deadline - time.monotonic())
        try:
            _out, err = proc.communicate(timeout=rem)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            _kill_child_process_tree(proc)
            rc = 124
            err = f"worker {key} timed out after {timeout_sec}s"
        if rc != 0 or not out_path.is_file():
            raise codec.CodecError(codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                f"worker:{key}",
                "parallel worker exit 0 with JSON output",
                f"rc={rc}: {(err or '')[-240:]}",
                None,
            ))
        loaded = codec.strict_json_loads(out_path.read_bytes())
        if not isinstance(loaded, dict):
            raise codec.CodecError(codec.Diagnostic(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                codec.Stage.DECODE,
                f"worker:{key}",
                "JSON object payload from parallel worker",
                type(loaded).__name__,
                None,
            ))
        results[key] = loaded
    return results


def _snapshot_tree_bytes(root: Path, prefixes: tuple[str, ...]) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    for prefix in prefixes:
        target = root / prefix
        if target.is_file():
            snap[prefix] = target.read_bytes()
        elif target.is_dir():
            for p in sorted(target.rglob("*")):
                if p.is_file():
                    snap[p.relative_to(root).as_posix()] = p.read_bytes()
    return snap


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# AC-1: Real Windows Lock Contention, Child Exit/Restart & 6-Stage Fault Points
# ---------------------------------------------------------------------------

def _seed_chapter4_commit_workspace(root: Path, source_root: Path) -> dict[str, Any]:
    """Create a committed 3C B-route workspace ready for real 6-stage Chapter 4 commit lifecycle."""
    _copy_repo_schemas_and_adr(source_root, root)
    scope_id = "scope-e2e-win"
    plan_id = "plan-win-reward"
    op_id = "OP-WIN-CH4-01"

    src_gdd = _put_bytes(root, "sources/reward-gdd.md", "# Reward Flow\n\nPlayer selects one reward and returns to map.\n")
    source_entries = [{"path": "sources/reward-gdd.md", "source_type": "markdown", "sha256": codec.raw_digest(src_gdd)}]
    manifest_digest = codec.canonical_digest(source_entries)
    source_revision = "source-set:" + manifest_digest[7:31]
    manifest_raw = _put_json(root, "sources/source-manifest.json", {
        "schema_version": "chapter3.source-manifest.v1",
        "source_revision": source_revision,
        "manifest_sha256": manifest_digest,
        "sources": source_entries,
    })
    ledger_raw = _put_json(root, "sources/source-blocks.json", {
        "schema_version": "newrouge.source-blocks.v1",
        "source_revision": source_revision,
        "source_manifest_sha256": manifest_digest,
        "blocks": [{"block_id": "BLK-REWARD-1", "source_path": "sources/reward-gdd.md"}],
    })
    proof_raw = _put_json(root, "evidence/admission-proof.json", {"selected_candidate": "cand-1"})

    _put_bytes(root, "Game.Core/Contracts/EventTypes.cs",
               'namespace Game.Core.Contracts;\n/// <summary>Canonical domain event type constants.</summary>\n'
               'public static class EventTypes { public const string RewardOffered = "core.reward.offered"; }\n')
    reward_cmd_raw = _put_bytes(root, "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                                "namespace Game.Core.Contracts.Reward;\n"
                                "/// <summary>Production command to select a locked reward option.</summary>\n"
                                "public sealed record SelectRewardCommand(string RunId, int OptionIndex);\n")
    reward_state_raw = _put_bytes(root, "Game.Core/Contracts/Reward/RewardReadOnlyState.cs",
                                  "using System.Collections.Generic;\nnamespace Game.Core.Contracts.Reward;\n"
                                  "/// <summary>Read-only reward state snapshot exposed by RewardStateOwner.</summary>\n"
                                  "public sealed record RewardReadOnlyState(string RunId, IReadOnlyList<string> Options, bool Locked);\n")
    adapter_raw = _put_bytes(root, "Game.Godot/Adapters/RewardSceneAdapter.cs",
                             "namespace Game.Godot.Adapters;\npublic sealed class RewardSceneAdapter { public void OnSelectOption(int index) { } }\n")
    scene_raw = _put_bytes(root, "Game.Godot/Scenes/RewardScene.tscn",
                           '[gd_scene load_steps=1 format=3]\n[node name="RewardScene" type="Control"]\n[node name="ConfirmButton" type="Button" parent="."]\n')
    resource_raw = _put_bytes(root, "Game.Godot/Resources/RewardTheme.tres",
                              '[gd_resource type="Resource" script_class="RewardThemeResource" format=3]\n[resource]\n')
    overlay_raw = _put_bytes(root, "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md",
                             "---\nPRD-ID: PRD-REWARD\nTitle: Reward Feature Slice\nArch-Refs: [docs/architecture/base/08.md]\nADRs: [ADR-0040]\nTest-Refs: [Game.Core.Tests/RewardTests.cs]\n---\n\n# Reward Feature Slice\n\n- NG-0101, NG-0102\n")

    # Live triplet with BOTH done (101) and in-progress (102) tasks that MUST be preserved!
    _put_json(root, ".taskmaster/tasks/tasks.json", {
        "master": {
            "tasks": [
                {"id": 101, "title": "Reward Core Commands", "description": "Core", "status": "done", "priority": "high", "dependencies": [], "details": "Story: B-ROUTE-win", "testStrategy": "xUnit"},
                {"id": 102, "title": "Reward Scene Binding", "description": "UI", "status": "in-progress", "priority": "medium", "dependencies": [101], "details": "Story: B-ROUTE-win", "testStrategy": "GdUnit4"},
            ]
        }
    })
    _put_json(root, ".taskmaster/tasks/tasks_back.json", [
        {
            "id": "NG-0101", "taskmaster_id": 101, "title": "Reward Core Commands", "status": "done",
            "layer": "core", "owner": "architecture", "labels": ["b-route", "3c-compiled"],
            "contractRefs": ["core.reward.offered"], "overlay_refs": ["docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"],
            "requirement_ids": ["RQ-REWARD-1"], "source_refs": [f"docs/planning/b-route/plans/{plan_id}/1.json"],
            "evidence_refs": [f"docs/planning/b-route/bindings/{plan_id}/1.json"],
            "acceptance": ["Preserve option order. Refs: Game.Core/Contracts/Reward/SelectRewardCommand.cs"],
            "semantic_review_tier": "targeted",
        },
        {
            "id": "NG-0102", "taskmaster_id": 102, "title": "Reward Scene Binding", "status": "in-progress",
            "layer": "adapter", "owner": "architecture", "labels": ["b-route", "3c-compiled"],
            "contractRefs": ["core.reward.offered"], "overlay_refs": ["docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"],
            "requirement_ids": ["RQ-REWARD-1"], "source_refs": [f"docs/planning/b-route/plans/{plan_id}/1.json"],
            "evidence_refs": [f"docs/planning/b-route/bindings/{plan_id}/1.json"],
            "acceptance": ["Thin adapter forwards command. Refs: Game.Godot/Adapters/RewardSceneAdapter.cs"],
            "semantic_review_tier": "targeted",
        },
    ])
    _put_json(root, ".taskmaster/tasks/tasks_gameplay.json", [])

    policy_rel = records.BASE + "policy.v1.json"
    policy_raw = _put_json(root, policy_rel, {
        "schema_version": "newrouge.b-route-policy.v1",
        "policy_id": "policy-main",
        "policy_revision": 1,
        "switch_boundary": {"default_route": "A", "a_write_allowed": True, "allowed_a_operations": ["resume-task"], "authority_refs": []},
        "frozen_a_refs": [],
    })
    policy_ref = _typed_ref(policy_rel, "newrouge.b-route-policy.v1", "policy-main", 1, policy_raw)

    source_identity = {
        "manifest_ref": _owned_ref("source_manifest", "sources/source-manifest.json", [("sources/source-manifest.json", manifest_raw)]),
        "ledger_ref": _owned_ref("source_ledger", "sources/source-blocks.json", [("sources/source-blocks.json", ledger_raw)]),
        "source_revision": source_revision,
        "source_manifest_digest": manifest_digest,
    }
    proof_ref = _owned_ref("planning_proof", "evidence/admission-proof.json", [("evidence/admission-proof.json", proof_raw)])
    reward_parts = _four_parts(domain=True, adapter=True, binding=True, scene=True)
    req_ver = [{
        "requirement_id": "RQ-REWARD-1", "disposition": "flow", "flow_id": "FLOW-REWARD",
        "rationale": "Verified by reward flow.", "sink_id": None, "verification_ref": None,
        "authority_ref": None, "evidence_ids": [],
    }]
    plan_rel = records.BASE + f"plans/{plan_id}/1.json"
    plan_raw = _put_json(root, plan_rel, {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": plan_id,
        "revision": 1,
        "source_identity": source_identity,
        "requirements": [{"requirement_id": "RQ-REWARD-1", "source_block_ids": ["BLK-REWARD-1"], "acceptance_intent": "Reward selection preserves locked order.", "non_task_sinks": []}],
        "definitions": {
            "flows": [{
                "id": "FLOW-REWARD", "requirement_ids": ["RQ-REWARD-1"],
                "entry": "EnterRewardScreen", "entry_condition": "Combat victory awards reward options.", "success_end": "ReturnToMap",
                "branches": [
                    {"kind": "failure", "rationale": "Reject invalid option.", "description": "Keep reward screen open."},
                    {"kind": "cancel", "rationale": "Allow skip reward.", "description": "Close without granting card."},
                    {"kind": "return", "rationale": "Return to map node.", "description": "Navigate back to map."},
                ],
                "handoffs": [],
                "state_owners": [{"kind": "state", "definition_id": "STATE-REWARD", "owner_plan_id": plan_id, "owner_revision": 1}],
                "parts": reward_parts,
                "observable_result": "Selected reward granted and player returns to map.",
                "verification_targets": ["RewardFlowTests"],
                "loops": [],
            }],
            "commands": [{
                "id": "CMD-SELECT-REWARD", "requirement_ids": ["RQ-REWARD-1"],
                "responsibility": "Select one locked reward option through domain command.",
                "uses": [{"kind": "state", "definition_id": "STATE-REWARD", "owner_plan_id": plan_id, "owner_revision": 1}],
            }],
            "states": [{
                "id": "STATE-REWARD", "requirement_ids": ["RQ-REWARD-1"],
                "responsibility": "Single authoritative owner of reward options.",
                "uses": [],
            }],
        },
        "logical_references": [],
        "requirement_verification": req_ver,
        "requirement_route_memberships": [{"requirement_id": "RQ-REWARD-1", "flow_id": "FLOW-REWARD", "observable_role": "Observe reward selection."}],
        "requirement_evidence": [],
        "evidence_source_refs": [],
        "coverage_table": [{k: v for k, v in r.items() if k != "evidence_ids"} for r in req_ver],
        "applicability": [{"requirement_id": "RQ-REWARD-1", "disposition": "flow", "rationale": "Verified by reward flow.", "other_verification_refs": []}],
        "adoption_proof_refs": [proof_ref],
        "lineage": {"previous_plan_ref": None, "change_summary": "Initial 3B plan for AC-1.", "identity_alignment": []},
    })
    plan_ref = _typed_ref(plan_rel, "newrouge.b-route-plan.v1", plan_id, 1, plan_raw)

    bind_rel = records.BASE + f"bindings/{plan_id}/1.json"
    bind_raw = _put_json(root, bind_rel, {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": plan_id, "binding_revision": 1, "plan_ref": plan_ref, "stage": "3C",
        "task_mappings": [
            {"task_id": 101, "view_refs": [{"view": "back", "business_id": "NG-0101"}], "requirement_ids": ["RQ-REWARD-1"], "flow_ids": ["FLOW-REWARD"], "part_kinds": ["domain_rules"], "roles": ["producer"], "obligation_ids": ["OBL-REWARD-CORE"]},
            {"task_id": 102, "view_refs": [{"view": "back", "business_id": "NG-0102"}], "requirement_ids": ["RQ-REWARD-1"], "flow_ids": ["FLOW-REWARD"], "part_kinds": ["csharp_adapter", "binding", "scene"], "roles": ["consumer"], "obligation_ids": ["OBL-REWARD-WIRE"]},
        ],
        "parts": reward_parts,
        "implementation_objects": [],
        "obligations": [
            {"id": "OBL-REWARD-CORE", "requirement_ids": ["RQ-REWARD-1"], "flow_ids": ["FLOW-REWARD"], "test_ids": ["RewardDomainTests"], "responsibility": "Verify reward selection.", "verification_refs": []},
            {"id": "OBL-REWARD-WIRE", "requirement_ids": ["RQ-REWARD-1"], "flow_ids": ["FLOW-REWARD"], "test_ids": ["RewardAdapterTests"], "responsibility": "Verify adapter wiring.", "verification_refs": []},
        ],
        "manifest_refs": [],
        "other_verification_refs": [],
    })
    bind_ref = _typed_ref(bind_rel, "newrouge.b-route-binding.v1", plan_id, 1, bind_raw)

    origins_rel = records.BASE + "task-origins.v1.json"
    origins_raw = _put_json(root, origins_rel, {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins", "revision": 1,
        "tasks": [
            {"task_id": 101, "source_refs": [source_identity["manifest_ref"]], "plan_refs": [plan_ref], "binding_refs": [bind_ref]},
            {"task_id": 102, "source_refs": [source_identity["manifest_ref"]], "plan_refs": [plan_ref], "binding_refs": [bind_ref]},
        ],
        "frozen_legacy_refs": [],
    })
    origins_ref = _typed_ref(origins_rel, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

    targets_boot = [
        {"path": p, "before_digest": None, "after_digest": codec.raw_digest(r), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(r)}
        for p, r in ((policy_rel, policy_raw), (plan_rel, plan_raw), (bind_rel, bind_raw), (origins_rel, origins_raw))
    ]
    boot_rel = records.BASE + "commits/OP-BOOTSTRAP-3C.json"
    boot_raw = _put_json(root, boot_rel, {
        "schema_version": "newrouge.b-route-commit.v1",
        "operation_id": "OP-BOOTSTRAP-3C", "revision": 1,
        "operation_digest": codec.canonical_digest({"bootstrap": "OP-BOOTSTRAP-3C", "scope": scope_id}),
        "scopes": [scope_id], "authority": [], "targets": targets_boot,
        "plan_refs": [plan_ref], "binding_refs": [bind_ref],
        "resolved_definitions": [{"kind": "state", "definition_id": "STATE-REWARD", "plan_ref": plan_ref}],
        "result": {"target_paths": [t["path"] for t in targets_boot], "scope_ids": [scope_id]},
    })
    boot_ref = _typed_ref(boot_rel, "newrouge.b-route-commit.v1", "OP-BOOTSTRAP-3C", 1, boot_raw)

    _put_json(root, records.CATALOG_PATH, {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog", "revision": 1,
        "policy_ref": policy_ref, "origins_ref": origins_ref,
        "scope_heads": [{"scope_id": scope_id, "plan_refs": [plan_ref], "binding_refs": [bind_ref], "receipt_ref": boot_ref}],
        "definition_owners": [
            {"kind": "command", "definition_id": "CMD-SELECT-REWARD", "plan_ref": copy.deepcopy(plan_ref)},
            {"kind": "flow", "definition_id": "FLOW-REWARD", "plan_ref": copy.deepcopy(plan_ref)},
            {"kind": "state", "definition_id": "STATE-REWARD", "plan_ref": copy.deepcopy(plan_ref)},
        ],
        "task_index": [
            {"task_id": 101, "plan_refs": [plan_ref], "binding_refs": [bind_ref]},
            {"task_id": 102, "plan_refs": [plan_ref], "binding_refs": [bind_ref]},
        ],
    })

    request_doc = {
        "schema_version": ch4_binding.REQUEST_SCHEMA,
        "producer": ch4_binding.PRODUCER,
        "operation_id": op_id,
        "plan_id": plan_id,
        "scope_id": scope_id,
        "reason": "Refine reward 3C binding into Stage-4 contracts and four-part definitions.",
        "commands": [{
            "id": "CMD-SELECT-REWARD", "owner": "RewardStateOwner",
            "preconditions": ["Reward session is active and unlocked."],
            "postconditions": ["Selected option is locked and reward granted once."],
            "invariants": ["Option ordering stays immutable."],
            "responsible_task_ids": [101], "availability": "existing",
            "expected_type": "Game.Core.Contracts.Reward.SelectRewardCommand",
            "target_ref": _owned_ref("contract", "Game.Core/Contracts/Reward/SelectRewardCommand.cs", [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", reward_cmd_raw)]),
            "later_checks": ["type", "compile"],
            "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            "handoff": "RewardSceneAdapter -> SelectRewardCommand -> RewardStateOwner",
        }],
        "read_only_states": [{
            "id": "STATE-REWARD", "single_owner": "RewardStateOwner",
            "read_only_views": ["RewardReadOnlyState"], "forbidden_direct_writers": ["adapter", "ui"],
            "responsible_task_ids": [101], "availability": "existing",
            "expected_type": "Game.Core.Contracts.Reward.RewardReadOnlyState",
            "target_ref": _owned_ref("contract", "Game.Core/Contracts/Reward/RewardReadOnlyState.cs", [("Game.Core/Contracts/Reward/RewardReadOnlyState.cs", reward_state_raw)]),
            "later_checks": ["type", "compile"],
            "contract_ref": "Game.Core/Contracts/Reward/RewardReadOnlyState.cs",
            "handoff": "RewardStateOwner exposes RewardReadOnlyState snapshot",
        }],
        "adapters": [{
            "id": "ADP-REWARD-SCENE", "dependencies": ["RewardStateOwner", "SelectRewardCommand"],
            "lifecycle": "Ready -> BindSignals -> ForwardCommands -> ExitTreeUnbind",
            "arbitrates_domain_rules": False, "direct_state_mutation": False,
            "responsible_task_ids": [102], "availability": "existing",
            "expected_type": "Game.Godot.Adapters.RewardSceneAdapter",
            "target_ref": _owned_ref("implementation_reference", "Game.Godot/Adapters/RewardSceneAdapter.cs", [("Game.Godot/Adapters/RewardSceneAdapter.cs", adapter_raw)]),
            "later_checks": ["type", "compile", "binding"],
        }],
        "bindings": [{
            "id": "BIND-REWARD-CONTROLS",
            "control_to_target": [{
                "control": "ConfirmButton.pressed", "target_object": "RewardSceneAdapter.OnSelectOption",
                "target_resource": "Game.Godot/Resources/RewardTheme.tres",
                "via_command": "CMD-SELECT-REWARD", "reads_state": "STATE-REWARD", "direct_state_write": False,
            }],
            "responsible_task_ids": [102], "availability": "existing",
            "expected_type": "RewardThemeResource",
            "target_ref": _owned_ref("implementation_reference", "Game.Godot/Resources/RewardTheme.tres", [("Game.Godot/Resources/RewardTheme.tres", resource_raw)]),
            "later_checks": ["type", "compile", "binding"],
        }],
        "scenes_and_resources": [{
            "id": "SCENE-REWARD", "kind": "scene",
            "scene_entry": ["CombatVictory -> RewardScene"], "scene_return": ["RewardSelected -> MapScene"],
            "responsible_task_ids": [102], "availability": "existing", "expected_type": "Control",
            "target_ref": _owned_ref("implementation_reference", "Game.Godot/Scenes/RewardScene.tscn", [("Game.Godot/Scenes/RewardScene.tscn", scene_raw)]),
            "later_checks": ["binding", "engine"],
        }],
        "obligations": [{
            "id": "OBL-REWARD-STAGE4", "requirement_ids": ["RQ-REWARD-1"], "flow_ids": ["FLOW-REWARD"],
            "test_ids": ["RewardStage4ContractTests"],
            "responsibility": "Verify Stage-4 command pre/post/inv and read-only state boundary.",
            "task_ids": [101, 102],
            "verification_refs": [_owned_ref("overlay", "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md", [("docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md", overlay_raw)])],
        }],
        "ui_slice": {
            "applicable": True,
            "rationale": "Reward screen has interactive selection controls.",
            "inputs": ["ConfirmButton.pressed"],
            "methods": ["RewardSceneAdapter.OnSelectOption"],
            "wiring": ["ConfirmButton.pressed -> RewardSceneAdapter.OnSelectOption -> CMD-SELECT-REWARD"],
            "human_zones": ["layout", "art", "animation"],
            "modified_zones": [],
            "direct_state_writes": [],
        },
    }
    req_rel = "logs/ci/test-inputs/ch4-commit-request.json"
    _put_json(root, req_rel, request_doc)
    return {
        "op_id": op_id,
        "scope_id": scope_id,
        "plan_id": plan_id,
        "request_rel": req_rel,
        "request_doc": request_doc,
    }


def _ac1_check_live_statuses_preserved(ws: Path) -> bool:
    master = _read_json(ws, ".taskmaster/tasks/tasks.json")
    by_id = {int(t["id"]): t.get("status") for t in master["master"]["tasks"]}
    return by_id.get(101) == "done" and by_id.get(102) == "in-progress"


def _ac1_check_readers_block_partial(ws: Path, *, probe_label: str = "ac1_partial_probe") -> dict[str, Any]:
    read_blocked = False
    read_diag: dict[str, Any] | None = None
    try:
        commit.read_committed(ws)
    except codec.CodecError as err:
        read_diag = err.diagnostic.to_dict()
        read_blocked = _is_valid_six_field_diag(read_diag)
    gate_res = ch6_gate.evaluate_chapter6_gate(ws, 101, consumer=probe_label, lock_mode="none")
    gate_diags = gate_res.get("diagnostics") or []
    gate_blocked = (
        (not gate_res.get("ok"))
        and gate_res.get("reason_code") in (codec.ReasonCode.PENDING.value, codec.ReasonCode.CONFLICT.value)
        and bool(gate_diags)
        and all(_is_valid_six_field_diag(d) for d in gate_diags)
    )
    proj = knowledge_projection.build_b_route_knowledge_projection(ws, mode="workspace_preview")
    page_state = planning_page.inspect_planning_page_state(ws, mode="workspace_preview")
    page_act = planning_page.execute_planning_page_action(
        ws,
        {"action": "chapter6", "sub_action": "gate", "task_id": 101, "mode": "workspace_preview", "recommendation_only": True},
    )
    proj_pending_or_blocked = (not proj.get("ok")) or bool(proj.get("pending_operations"))
    page_pending_nonempty = bool(page_state.get("pending_operations"))
    page_act_blocked = (
        (not page_act.get("ok"))
        and page_act.get("reason_code") in (codec.ReasonCode.PENDING.value, codec.ReasonCode.CONFLICT.value)
    )
    return {
        "read_committed_blocked": read_blocked,
        "read_diag": read_diag,
        "chapter6_gate_blocked": gate_blocked,
        "chapter6_gate_reason_code": gate_res.get("reason_code"),
        "projection_pending_or_blocked": proj_pending_or_blocked,
        "page_pending_nonempty": page_pending_nonempty,
        "page_action_blocked": page_act_blocked,
        "all_blocked": (
            read_blocked
            and gate_blocked
            and proj_pending_or_blocked
            and page_pending_nonempty
            and page_act_blocked
        ),
    }


def _ac1_run_post_reserve_stage(stage_name: str, ws: Path, op_id: str, req_rel: str) -> dict[str, Any]:
    if stage_name == "apply":
        rc_app_crash, _, _ = _run_stage_child(ws, action="apply", op_id=op_id, crash_at="after_target:0")
        readers_app = _ac1_check_readers_block_partial(ws, probe_label="ac1_partial_apply_probe")
        env_doc = journal.read_operation(ws, operation_id=op_id)
        first_target_rel = env_doc["frozen"]["targets"][0]["path"]
        first_target_orig = (ws / first_target_rel).read_bytes()
        human_edit_bytes = b'{"human_post_edit":"must_preserve_exact_bytes"}\n'
        (ws / first_target_rel).write_bytes(human_edit_bytes)
        pe_diag: dict[str, Any] | None = None
        try:
            commit.recover(ws, operation_id=op_id)
        except codec.CodecError as err:
            pe_diag = err.diagnostic.to_dict()
        post_edit_preserved = (
            _is_valid_six_field_diag(pe_diag)
            and (ws / first_target_rel).read_bytes() == human_edit_bytes
        )
        (ws / first_target_rel).write_bytes(first_target_orig)
        app_rec_out = commit.recover(ws, operation_id=op_id)
        app_committed = commit.read_committed(ws)
        app_ok = (
            rc_app_crash == 73
            and readers_app["all_blocked"]
            and post_edit_preserved
            and bool(app_rec_out.get("published"))
            and bool(app_committed.get("formal_adoption"))
            and _ac1_check_live_statuses_preserved(ws)
        )
        return {
            "ok": app_ok,
            "crash_rc": rc_app_crash,
            "readers_blocked_partial": readers_app["read_committed_blocked"],
            "projection_saw_pending": readers_app["projection_pending_or_blocked"],
            "page_pending_nonempty": readers_app["page_pending_nonempty"],
            "page_action_blocked_partial": readers_app["page_action_blocked"],
            "chapter6_gate_blocked_partial": readers_app["chapter6_gate_blocked"],
            "post_edit_preserved": post_edit_preserved,
            "recovered_published": bool(app_rec_out.get("published")),
            "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws),
        }

    if stage_name == "verify":
        commit.execute(ws, operation_id=op_id, stage="apply")
        rc_ver_crash, _, _ = _run_stage_child(ws, action="verify", op_id=op_id, crash_at="receipt_durable")
        readers_ver = _ac1_check_readers_block_partial(ws, probe_label="ac1_partial_verify_probe")
        intent_rel, _pending_rel = commit._paths(op_id)
        intent_orig = (ws / intent_rel).read_bytes()
        corrupt_bytes = b'{"truncated_corrupt_journal":'
        (ws / intent_rel).write_bytes(corrupt_bytes)
        corrupt_diag: dict[str, Any] | None = None
        try:
            commit.recover(ws, operation_id=op_id)
        except codec.CodecError as err:
            corrupt_diag = err.diagnostic.to_dict()
        corrupt_blocked = (
            _is_valid_six_field_diag(corrupt_diag)
            and (ws / intent_rel).read_bytes() == corrupt_bytes
        )
        (ws / intent_rel).write_bytes(intent_orig)
        ver_rec_out = commit.recover(ws, operation_id=op_id)
        ver_ok = (
            rc_ver_crash == 73
            and readers_ver["all_blocked"]
            and corrupt_blocked
            and bool(ver_rec_out.get("published"))
            and _ac1_check_live_statuses_preserved(ws)
        )
        return {
            "ok": ver_ok,
            "crash_rc": rc_ver_crash,
            "receipt_not_publication": readers_ver["read_committed_blocked"],
            "page_pending_nonempty": readers_ver["page_pending_nonempty"],
            "page_action_blocked_partial": readers_ver["page_action_blocked"],
            "chapter6_gate_blocked_partial": readers_ver["chapter6_gate_blocked"],
            "corrupt_journal_blocked_no_silent_repair": corrupt_blocked,
            "recovered_published": bool(ver_rec_out.get("published")),
            "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws),
        }

    if stage_name == "publish":
        commit.execute(ws, operation_id=op_id, stage="apply")
        commit.execute(ws, operation_id=op_id, stage="verify")
        rc_pub_crash, _, _ = _run_stage_child(ws, action="publish", op_id=op_id, crash_at="before_pending_cleanup")
        catalog_before_cleanup = (ws / records.CATALOG_PATH).read_bytes()
        readers_pub = _ac1_check_readers_block_partial(ws, probe_label="ac1_partial_publish_probe")
        pub_rec_out = commit.recover(ws, operation_id=op_id)
        catalog_after_cleanup = (ws / records.CATALOG_PATH).read_bytes()
        pub_committed = commit.read_committed(ws)
        pub_ok = (
            rc_pub_crash == 73
            and readers_pub["all_blocked"]
            and bool(pub_rec_out.get("published"))
            and catalog_before_cleanup == catalog_after_cleanup
            and bool(pub_committed.get("formal_adoption"))
            and _ac1_check_live_statuses_preserved(ws)
        )
        return {
            "ok": pub_ok,
            "crash_rc": rc_pub_crash,
            "uncleaned_pending_blocked_consumption": readers_pub["read_committed_blocked"],
            "page_pending_nonempty": readers_pub["page_pending_nonempty"],
            "page_action_blocked_partial": readers_pub["page_action_blocked"],
            "chapter6_gate_blocked_partial": readers_pub["chapter6_gate_blocked"],
            "catalog_bytes_preserved_across_cleanup": catalog_before_cleanup == catalog_after_cleanup,
            "recovered_published": bool(pub_rec_out.get("published")),
            "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws),
        }

    if stage_name == "recover":
        rc_pre_crash, _, _ = _run_stage_child(ws, action="apply", op_id=op_id, crash_at="after_target:0")
        rc_rec_crash, _, _ = _run_stage_child(ws, action="recover", op_id=op_id, crash_at="receipt_durable")
        readers_mid_rec = _ac1_check_readers_block_partial(ws, probe_label="ac1_partial_recover_probe")
        rc_rec_ok, rec_ok_out, _ = _run_stage_child(ws, action="recover", op_id=op_id)
        formal_before_noop = _snapshot_tree_bytes(ws, ("docs/planning/b-route", ".taskmaster/tasks"))
        rec_noop_out = commit.recover(ws, operation_id=op_id)
        formal_after_noop = _snapshot_tree_bytes(ws, ("docs/planning/b-route", ".taskmaster/tasks"))
        req_doc = _read_json(ws, req_rel)
        mutated_after = copy.deepcopy(req_doc)
        mutated_after["reason"] = "Mutated Stage-4 request payload after completion."
        mut_after_rel = "logs/ci/test-inputs/ch4-request-mutated-after.json"
        _put_json(ws, mut_after_rel, mutated_after)
        after_mut_diag: dict[str, Any] | None = None
        try:
            ch4_binding.prepare(ws, operation_id=op_id, request_ref=mut_after_rel)
        except codec.CodecError as err:
            after_mut_diag = err.diagnostic.to_dict()
        rec_stage_ok = (
            rc_pre_crash == 73
            and rc_rec_crash == 73
            and readers_mid_rec["all_blocked"]
            and rc_rec_ok == 0
            and bool((rec_ok_out or {}).get("published"))
            and bool(rec_noop_out.get("noop"))
            and formal_before_noop == formal_after_noop
            and _is_valid_six_field_diag(after_mut_diag)
            and (after_mut_diag or {}).get("reason_code") == codec.ReasonCode.CONFLICT.value
            and _ac1_check_live_statuses_preserved(ws)
        )
        return {
            "ok": rec_stage_ok,
            "mid_recover_crash_rc": rc_rec_crash,
            "mid_recover_blocked_mixed_read": readers_mid_rec["read_committed_blocked"],
            "page_pending_nonempty": readers_mid_rec["page_pending_nonempty"],
            "page_action_blocked_partial": readers_mid_rec["page_action_blocked"],
            "chapter6_gate_blocked_partial": readers_mid_rec["chapter6_gate_blocked"],
            "restart_published": bool((rec_ok_out or {}).get("published")),
            "idempotent_noop": bool(rec_noop_out.get("noop")),
            "noop_bytes_unchanged": formal_before_noop == formal_after_noop,
            "post_complete_same_id_mutated_conflict": (after_mut_diag or {}).get("reason_code") == codec.ReasonCode.CONFLICT.value,
            "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws),
        }

    raise ValueError(f"unsupported AC-1 stage: {stage_name}")


def _run_ac1_windows_fault_injection_matrix(source_root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    stage_results: dict[str, dict[str, Any]] = {}
    used_real_windows_msvcrt_lock = False
    used_real_child_process_termination = False

    if os.name != "nt":
        diagnostics.append(_diag(
            codec.ReasonCode.DEPENDENCY_UNAVAILABLE,
            codec.Stage.TARGET,
            "windows_platform",
            "os.name == 'nt' for real Windows msvcrt lock and child process fault verification",
            os.name,
            None,
        ))
        return {
            "ok": False,
            "status": "blocked",
            "platform_evidence": {
                "os_name": os.name,
                "platform": platform.platform(),
                "python_version": sys.version,
                "used_real_windows_msvcrt_lock": False,
                "used_real_child_process_termination": False,
                "mock_os_exception_claimed_as_windows_proof": False,
            },
            "untested_windows_boundaries": list(UNTESTED_WINDOWS_BOUNDARIES),
            "stages": stage_results,
            "diagnostics": diagnostics,
        }

    # 1. Real Windows msvcrt.locking contention in a real child process + taskkill /F /T release
    lock_contention_ok = False
    lock_release_ok = False
    lock_diag: dict[str, Any] | None = None
    with _temp_workspace("nr410-lock-") as lock_root:
        meta_dir, _scopes_dir = op_scope.initialize_lock_namespace(lock_root)
        lock_file = meta_dir / "capability-coordinator.lock"
        ready_file = lock_root / "lock-ready.txt"
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", _WIN_MSVCRT_LOCK_HOLDER_CODE, str(lock_file), str(ready_file)],
            cwd=str(lock_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            deadline = time.monotonic() + 3.0
            while not ready_file.is_file() and time.monotonic() < deadline:
                if child.poll() is not None:
                    break
                time.sleep(0.02)
            if ready_file.is_file():
                used_real_windows_msvcrt_lock = True
                try:
                    with op_scope.scope_guard(
                        lock_root,
                        ["plan:win-lock-probe"],
                        prepare_under_lease=lambda: "should-not-run",
                    ):
                        pass
                except codec.CodecError as err:
                    lock_diag = err.diagnostic.to_dict()
                    lock_contention_ok = _is_valid_six_field_diag(lock_diag) and lock_diag["reason_code"] in (
                        codec.ReasonCode.CONFLICT.value,
                        codec.ReasonCode.PENDING.value,
                    )
        finally:
            used_real_child_process_termination = _kill_child_process_tree(child)
            if child.stdout:
                child.stdout.close()
            if child.stderr:
                child.stderr.close()

        if used_real_child_process_termination:
            entered: list[str] = []
            with op_scope.scope_guard(
                lock_root,
                ["plan:win-lock-probe"],
                prepare_under_lease=lambda: entered.append("acquired_after_taskkill"),
            ):
                pass
            lock_release_ok = entered == ["acquired_after_taskkill"]

    if not (used_real_windows_msvcrt_lock and used_real_child_process_termination and lock_contention_ok and lock_release_ok):
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "windows_msvcrt_lock",
            "real Windows msvcrt child lock contention blocked + taskkill release succeeded",
            {
                "lock_acquired": used_real_windows_msvcrt_lock,
                "child_terminated": used_real_child_process_termination,
                "contention_blocked": lock_contention_ok,
                "release_ok": lock_release_ok,
            },
            None,
        ))

    # 2. Seed base workspace, snapshot base_prepared & base_reserved via shutil.copytree,
    #    and run isolated apply/verify/publish/recover stage workspaces concurrently.
    with _temp_workspace("nr410-ac1-") as ac1_tmp:
        base_seeded = ac1_tmp / "base_seeded"
        base_seeded.mkdir(parents=True, exist_ok=True)
        seed = _seed_chapter4_commit_workspace(base_seeded, source_root)
        op_id = seed["op_id"]
        req_rel = seed["request_rel"]
        req_doc = seed["request_doc"]
        initial_tasks_raw = (base_seeded / ".taskmaster/tasks/tasks.json").read_bytes()

        ws_prep = ac1_tmp / "ws_prep"
        shutil.copytree(base_seeded, ws_prep)
        prep_ready = ac1_tmp / "prep-crash-marker.txt"
        rc_crash, _, _ = _run_stage_child(
            ws_prep, action="prepare", op_id=op_id, arg_extra=req_rel,
            crash_at="mid_prepare_write", ready_file=str(prep_ready),
        )
        prep_mid_hook_hit = prep_ready.is_file() and "CRASHING:mid_prepare_write:" in prep_ready.read_text(encoding="utf-8")
        ch4_binding.prepare(ws_prep, operation_id=op_id, request_ref=req_rel)
        base_prepared = ac1_tmp / "base_prepared"
        shutil.copytree(ws_prep, base_prepared)

        ws_res = ac1_tmp / "ws_res"
        shutil.copytree(base_prepared, ws_res)
        res_ready = ac1_tmp / "res-crash-marker.txt"
        rc_res_crash, _, _ = _run_stage_child(
            ws_res, action="reserve", op_id=op_id,
            crash_at="mid_reserve_write", ready_file=str(res_ready),
        )
        res_mid_hook_hit = res_ready.is_file() and "CRASHING:mid_reserve_write:" in res_ready.read_text(encoding="utf-8")
        ch4_binding.reserve(ws_res, operation_id=op_id)
        base_reserved = ac1_tmp / "base_reserved"
        shutil.copytree(ws_res, base_reserved)

        worker_specs: dict[str, tuple[str, list[str]]] = {}
        for st_name in ("apply", "verify", "publish", "recover"):
            st_ws = ac1_tmp / f"ws_{st_name}"
            shutil.copytree(base_reserved, st_ws)
            worker_specs[st_name] = ("ac1_stage", [st_name, str(st_ws), op_id, req_rel])

        handles = _start_parallel_workers(ac1_tmp, worker_specs)
        try:
            # Complete Stage 1 (prepare) checks while post-reserve stages execute in parallel
            inspect_prep = commit.inspect_recovery(ws_prep, operation_id=op_id)
            prep_replay_ok = False
            try:
                ch4_binding.prepare(ws_prep, operation_id=op_id, request_ref=req_rel)
                prep_replay_ok = True
            except codec.CodecError:
                prep_replay_ok = False
            mutated_req = copy.deepcopy(req_doc)
            mutated_req["reason"] = "Mutated Stage-4 request payload for same-ID conflict check."
            mut_rel = "logs/ci/test-inputs/ch4-request-mutated.json"
            _put_json(ws_prep, mut_rel, mutated_req)
            mut_diag: dict[str, Any] | None = None
            try:
                ch4_binding.prepare(ws_prep, operation_id=op_id, request_ref=mut_rel)
            except codec.CodecError as err:
                mut_diag = err.diagnostic.to_dict()
            prep_ok = (
                rc_crash == 73
                and prep_mid_hook_hit
                and inspect_prep.get("next_stage") == "reserve"
                and prep_replay_ok
                and _is_valid_six_field_diag(mut_diag)
                and (mut_diag or {}).get("reason_code") == codec.ReasonCode.CONFLICT.value
                and _ac1_check_live_statuses_preserved(ws_prep)
                and (ws_prep / ".taskmaster/tasks/tasks.json").read_bytes() == initial_tasks_raw
            )
            prep_info = {
                "ok": prep_ok,
                "crash_rc": rc_crash,
                "mid_prepare_hook_reached": prep_mid_hook_hit,
                "next_stage_after_prepare": inspect_prep.get("next_stage"),
                "same_id_replay_ok": prep_replay_ok,
                "same_id_mutated_conflict": (mut_diag or {}).get("reason_code") == codec.ReasonCode.CONFLICT.value,
                "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws_prep),
            }

            # Complete Stage 2 (reserve) checks
            res_replay_ok = False
            try:
                ch4_binding.reserve(ws_res, operation_id=op_id)
                res_replay_ok = True
            except codec.CodecError:
                res_replay_ok = False
            inspect_res = commit.inspect_recovery(ws_res, operation_id=op_id)
            res_ok = (
                rc_res_crash == 73
                and res_mid_hook_hit
                and res_replay_ok
                and inspect_res.get("next_stage") == "apply"
                and _ac1_check_live_statuses_preserved(ws_res)
                and (ws_res / ".taskmaster/tasks/tasks.json").read_bytes() == initial_tasks_raw
            )
            res_info = {
                "ok": res_ok,
                "crash_rc": rc_res_crash,
                "mid_reserve_hook_reached": res_mid_hook_hit,
                "reserve_idempotent_replay_ok": res_replay_ok,
                "next_stage_after_reserve": inspect_res.get("next_stage"),
                "live_task_statuses_preserved": _ac1_check_live_statuses_preserved(ws_res),
            }

            post_reserve_results = _collect_parallel_workers(handles, timeout_sec=240.0)
        finally:
            _cleanup_parallel_workers(handles)

        stage_results = {
            "prepare": prep_info,
            "reserve": res_info,
            "apply": post_reserve_results["apply"],
            "verify": post_reserve_results["verify"],
            "publish": post_reserve_results["publish"],
            "recover": post_reserve_results["recover"],
        }

    for st_name, st_info in stage_results.items():
        if not st_info.get("ok"):
            diagnostics.append(_diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                f"ac1_stage:{st_name}",
                f"stage {st_name} fault injection passed",
                st_info,
                None,
            ))

    ok = (
        used_real_windows_msvcrt_lock
        and used_real_child_process_termination
        and lock_contention_ok
        and lock_release_ok
        and len(stage_results) == 6
        and all(v.get("ok") for v in stage_results.values())
        and not diagnostics
    )
    return {
        "ok": ok,
        "status": "passed" if ok else "blocked",
        "platform_evidence": {
            "os_name": os.name,
            "platform": platform.platform(),
            "python_version": sys.version,
            "used_real_windows_msvcrt_lock": used_real_windows_msvcrt_lock,
            "used_real_child_process_termination": used_real_child_process_termination,
            "mock_os_exception_claimed_as_windows_proof": False,
        },
        "windows_lock_contention": {
            "ok": lock_contention_ok and lock_release_ok,
            "contention_blocked": lock_contention_ok,
            "release_after_taskkill": lock_release_ok,
            "diagnostic": lock_diag,
        },
        "stages": stage_results,
        "untested_windows_boundaries": list(UNTESTED_WINDOWS_BOUNDARIES),
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# AC-2: Shared-Task Multi-Scope Join, Drift, Legacy Pending & Anti-Bypass
# ---------------------------------------------------------------------------

def _seed_shared_scope_repo(root: Path, source_root: Path) -> dict[str, Any]:
    """Seed a committed B-route repo with Scope 1 (Task 101), Scope 3 unrelated (Task 301),
    dedicated integration-owner (Task 200), and legal non-Flow plan (Task 401)."""
    _copy_repo_schemas_and_adr(source_root, root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "e2e@example.invalid")
    _git(root, "config", "user.name", "E2E")
    _put_bytes(root, ".gitignore", "logs/\n")

    gdd_s1 = _put_bytes(root, "docs/gdd/scope1.md", "# Scope 1\n\nShared task baseline.\n")
    gdd_s2 = _put_bytes(root, "docs/gdd/scope2.md", "# Scope 2\n\nSecond scope joining shared task.\n")
    gdd_s3 = _put_bytes(root, "docs/gdd/scope3.md", "# Scope 3\n\nUnrelated scope.\n")
    other_v_raw = _put_bytes(root, "docs/testing/nonflow-static-rule.md", "# Static Rule\n\nDeterministic check.\n")
    contract_1 = _put_bytes(root, "Game.Core/Contracts/E2E/Scope1Contract.cs", "public sealed class Scope1Contract { public int V = 1; }\n")
    contract_3 = _put_bytes(root, "Game.Core/Contracts/E2E/Scope3Contract.cs", "public sealed class Scope3Contract { public int V = 1; }\n")
    _put_bytes(root, "Game.Core.Tests/E2E/Scope1Tests.cs", "public class Scope1Tests { [Fact] public void Ok() {} }\n")
    _put_bytes(root, "Game.Core.Tests/E2E/Scope3Tests.cs", "public class Scope3Tests { [Fact] public void Ok() {} }\n")

    def _source_artifacts(tag: str, gdd_rel: str, gdd_raw: bytes, blk_id: str) -> dict[str, Any]:
        dg = codec.raw_digest(gdd_raw)
        m_rel = f"docs/planning/sources/{tag}-manifest.json"
        l_rel = f"docs/planning/sources/{tag}-ledger.json"
        p_rel = f"docs/planning/sources/{tag}-proof.json"
        m_raw = _put_json(root, m_rel, {
            "schema_version": "chapter3.source-manifest.v1",
            "source_revision": f"{tag}-rev-1",
            "manifest_sha256": dg,
            "sources": [{"path": gdd_rel, "raw_digest": dg}],
        })
        l_raw = _put_json(root, l_rel, {
            "schema_version": "chapter3.source-blocks.v1",
            "source_revision": f"{tag}-rev-1",
            "source_manifest_sha256": dg,
            "blocks": [{"block_id": blk_id, "path": gdd_rel}],
        })
        p_raw = _put_json(root, p_rel, {"schema_version": "e2e.proof.v1", "verdict": "approved"})
        return {
            "gdd_rel": gdd_rel, "gdd_raw": gdd_raw, "gdd_dg": dg,
            "source_revision": f"{tag}-rev-1",
            "m_rel": m_rel, "m_raw": m_raw,
            "l_rel": l_rel, "l_raw": l_raw,
            "p_rel": p_rel, "p_raw": p_raw,
            "blk_id": blk_id,
        }

    src1 = _source_artifacts("s1", "docs/gdd/scope1.md", gdd_s1, "BLK-S1")
    src2 = _source_artifacts("s2", "docs/gdd/scope2.md", gdd_s2, "BLK-S2")
    src3 = _source_artifacts("s3", "docs/gdd/scope3.md", gdd_s3, "BLK-S3")

    mvg_rel = "docs/testing/mvg/e2e-shared.json"
    mvg_raw = _put_json(root, mvg_rel, {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "e2e-shared",
        "coverage": {
            "mode": "full",
            "scope_id": "e2e-shared",
            "required_flow_ids": ["flow-s1", "flow-s3", "flow-s-base"],
            "blocking_task_ids": [],
            "excluded_claims": ["Manual playtest checks require explicit signoff"],
        },
        "flows": [
            {
                "id": "flow-s1",
                "outcome": "Scope 1 flow passes",
                "task_ids": [101],
                "requirement_ids": ["REQ-S1"],
                "source_paths": ["Game.Core/Contracts/E2E/Scope1Contract.cs"],
                "test_ids": ["t-s1"],
                "handoffs": [{
                    "producer_task": 101,
                    "consumer_task": 101,
                    "owner_task": 101,
                    "contract_ref": "Game.Core/Contracts/E2E/Scope1Contract.cs",
                    "behavior": "Scope 1 contract handoff",
                    "test_ids": ["t-s1"],
                }],
            },
            {
                "id": "flow-s3",
                "outcome": "Scope 3 flow passes",
                "task_ids": [301],
                "requirement_ids": ["REQ-S3"],
                "source_paths": ["Game.Core/Contracts/E2E/Scope3Contract.cs"],
                "test_ids": ["t-s3"],
                "handoffs": [{
                    "producer_task": 301,
                    "consumer_task": 301,
                    "owner_task": 301,
                    "contract_ref": "Game.Core/Contracts/E2E/Scope3Contract.cs",
                    "behavior": "Scope 3 contract handoff",
                    "test_ids": ["t-s3"],
                }],
            },
            {
                "id": "flow-s-base",
                "outcome": "Baseline third flow for full MVG mode",
                "task_ids": [301],
                "requirement_ids": ["REQ-S3"],
                "source_paths": ["Game.Core/Contracts/E2E/Scope3Contract.cs"],
                "test_ids": ["t-s3"],
                "handoffs": [{
                    "producer_task": 301,
                    "consumer_task": 301,
                    "owner_task": 301,
                    "contract_ref": "Game.Core/Contracts/E2E/Scope3Contract.cs",
                    "behavior": "Baseline third flow handoff",
                    "test_ids": ["t-s3"],
                }],
            },
        ],
        "tests": [
            {
                "id": "t-s1",
                "kind": "dotnet",
                "state": "implemented",
                "evidence_level": "domain-integration",
                "path": "Game.Core.Tests/E2E/Scope1Tests.cs",
                "selector": "Scope1Tests",
                "min_tests": 1,
            },
            {
                "id": "t-s3",
                "kind": "dotnet",
                "state": "implemented",
                "evidence_level": "domain-integration",
                "path": "Game.Core.Tests/E2E/Scope3Tests.cs",
                "selector": "Scope3Tests",
                "min_tests": 1,
            },
        ],
    })
    mvg_owned = _owned_ref("manifest", mvg_rel, [(mvg_rel, mvg_raw)])
    ov_owned = _owned_ref("other_verification", "docs/testing/nonflow-static-rule.md", [("docs/testing/nonflow-static-rule.md", other_v_raw)])

    _put_json(root, ".taskmaster/tasks/tasks.json", {
        "master": {
            "tasks": [
                {"id": 101, "title": "Shared Multi-Scope Task", "status": "in-progress", "dependencies": []},
                {"id": 200, "title": "Dedicated Integration Owner Task", "status": "in-progress", "dependencies": []},
                {"id": 301, "title": "Unrelated Scope3 Task", "status": "in-progress", "dependencies": []},
                {"id": 401, "title": "Legal Non-Flow Static Task", "status": "done", "dependencies": []},
            ]
        }
    })
    _put_json(root, ".taskmaster/tasks/tasks_back.json", [
        {"id": "NG-0101", "taskmaster_id": 101, "title": "Shared Multi-Scope Task", "status": "in-progress", "contractRefs": ["Game.Core/Contracts/E2E/Scope1Contract.cs"], "test_refs": ["Game.Core.Tests/E2E/Scope1Tests.cs"], "acceptance": ["Scope 1 baseline Refs: Game.Core.Tests/E2E/Scope1Tests.cs"]},
        {"id": "NG-0200", "taskmaster_id": 200, "title": "Dedicated Integration Owner Task", "status": "in-progress", "contractRefs": [], "test_refs": [], "acceptance": ["Integration owner"]},
        {"id": "NG-0301", "taskmaster_id": 301, "title": "Unrelated Scope3 Task", "status": "in-progress", "contractRefs": ["Game.Core/Contracts/E2E/Scope3Contract.cs"], "test_refs": ["Game.Core.Tests/E2E/Scope3Tests.cs"], "acceptance": ["Scope 3 baseline Refs: Game.Core.Tests/E2E/Scope3Tests.cs"]},
        {"id": "NG-0401", "taskmaster_id": 401, "title": "Legal Non-Flow Static Task", "status": "done", "contractRefs": [], "test_refs": [], "acceptance": ["Static verification Refs: docs/testing/nonflow-static-rule.md"]},
    ])
    _put_json(root, ".taskmaster/tasks/tasks_gameplay.json", [])

    def _build_flow_plan(plan_id: str, flow_id: str, req_id: str, src: dict[str, Any], *, nonflow: bool = False) -> tuple[str, bytes, dict[str, Any]]:
        if nonflow:
            rv = [{
                "requirement_id": req_id, "disposition": "other_verification",
                "flow_id": None, "sink_id": "sink:static-rule",
                "verification_ref": "docs/testing/nonflow-static-rule.md",
                "authority_ref": None, "rationale": "Static audit rule without fake flow.", "evidence_ids": [],
            }]
            flows = []
            memberships = []
            app_list = [{
                "requirement_id": req_id, "disposition": "other_verification",
                "rationale": "Static audit rule without fake flow.",
                "other_verification_refs": [copy.deepcopy(ov_owned)],
            }]
            ev_refs = [copy.deepcopy(ov_owned)]
        else:
            rv = [{
                "requirement_id": req_id, "disposition": "flow",
                "flow_id": flow_id, "sink_id": None,
                "verification_ref": None, "authority_ref": None,
                "rationale": f"Verified by {flow_id}.", "evidence_ids": [],
            }]
            flows = [{
                "id": flow_id, "requirement_ids": [req_id],
                "entry": f"enter:{flow_id}", "entry_condition": f"ready:{flow_id}", "success_end": f"done:{flow_id}",
                "branches": [
                    {"kind": "failure", "rationale": "Fail.", "description": "Abort."},
                    {"kind": "cancel", "rationale": "Cancel.", "description": "Return."},
                    {"kind": "return", "rationale": "Return.", "description": "Exit."},
                ],
                "handoffs": [], "state_owners": [],
                "parts": _four_parts(domain=True, adapter=True, binding=True, scene=False),
                "observable_result": f"observed:{flow_id}",
                "verification_targets": [f"mvg:{flow_id}"], "loops": [],
            }]
            memberships = [{"requirement_id": req_id, "flow_id": flow_id, "observable_role": "primary"}]
            app_list = [{"requirement_id": req_id, "disposition": "flow", "rationale": f"Verified by {flow_id}.", "other_verification_refs": []}]
            ev_refs = []
        doc = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": plan_id,
            "revision": 1,
            "source_identity": {
                "manifest_ref": _owned_ref("source_manifest", src["m_rel"], [(src["m_rel"], src["m_raw"])]),
                "ledger_ref": _owned_ref("source_ledger", src["l_rel"], [(src["l_rel"], src["l_raw"])]),
                "source_revision": src["source_revision"],
                "source_manifest_digest": src["gdd_dg"],
            },
            "requirements": [{
                "requirement_id": req_id,
                "source_block_ids": [src["blk_id"]],
                "acceptance_intent": f"Deliver {req_id}.",
                "non_task_sinks": ["sink:static-rule"] if nonflow else [],
            }],
            "definitions": {"flows": flows, "commands": [], "states": []},
            "logical_references": [],
            "requirement_verification": rv,
            "requirement_route_memberships": memberships,
            "requirement_evidence": [],
            "evidence_source_refs": ev_refs,
            "coverage_table": [{k: v for k, v in r.items() if k != "evidence_ids"} for r in rv],
            "applicability": app_list,
            "adoption_proof_refs": [_owned_ref("planning_proof", src["p_rel"], [(src["p_rel"], src["p_raw"])])],
            "lineage": {"previous_plan_ref": None, "change_summary": f"Committed {plan_id}.", "identity_alignment": []},
        }
        rel = f"docs/planning/b-route/plans/{plan_id}/1.json"
        raw = _put_json(root, rel, doc)
        return rel, raw, _typed_ref(rel, "newrouge.b-route-plan.v1", plan_id, 1, raw)

    def _build_binding(
        plan_id: str,
        plan_ref: dict[str, Any],
        task_id: int,
        biz_id: str,
        req_id: str,
        flow_id: str | None,
        *,
        contract_rel: str | None = None,
        contract_raw: bytes | None = None,
        test_id: str | None = None,
        nonflow: bool = False,
    ) -> tuple[str, bytes, dict[str, Any]]:
        obl_id = f"OBL-{plan_id}-1"
        s5_meta = {
            "stage": "5",
            "category": "current_new",
            "task_ids": [task_id],
            "newly_assigned_task_ids": [],
            "manifest_flow_ids": [] if nonflow else [flow_id],
            "non_catalog_flow_ids": [],
            "out_of_scope_future_flow_ids": [],
            "planned_test_ids": [],
            "has_new_obligation": False,
            "requires_reverification_on_done": False,
            "dedup_key": f"{plan_id}:{obl_id}",
        }
        s4_meta = {"stage": "4", "task_ids": [task_id], "test_ids": [test_id] if test_id else []}
        contract_bindings = []
        if contract_rel and contract_raw is not None:
            contract_bindings.append({
                "contract_ref": _owned_ref("contract", contract_rel, [(contract_rel, contract_raw)]),
                "flow_ids": [flow_id] if flow_id else [],
                "task_ids": [task_id],
            })
        doc = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": plan_id,
            "plan_ref": plan_ref,
            "binding_revision": 1,
            "stage": "5",
            "parts": _four_parts(domain=True, adapter=not nonflow, binding=not nonflow, scene=False),
            "manifest_refs": [] if nonflow else [copy.deepcopy(mvg_owned)],
            "other_verification_refs": [copy.deepcopy(ov_owned)] if nonflow else [],
            "task_mappings": [{
                "task_id": task_id,
                "view_refs": [{"view": "back", "business_id": biz_id}],
                "requirement_ids": [req_id],
                "flow_ids": [] if nonflow else [flow_id],
                "part_kinds": ["domain_rules"],
                "roles": ["producer", "consumer"] if not nonflow else ["producer"],
                "obligation_ids": [obl_id],
            }],
            "implementation_objects": [],
            "obligations": [{
                "id": obl_id,
                "requirement_ids": [req_id],
                "flow_ids": [] if nonflow else [flow_id],
                "test_ids": [test_id] if test_id else [],
                "responsibility": _stage5_resp(f"Obligation for {plan_id}.", s5_meta, s4_meta),
                "verification_refs": [copy.deepcopy(ov_owned)] if nonflow else [copy.deepcopy(mvg_owned)],
            }],
        }
        rel = f"docs/planning/b-route/bindings/{plan_id}/1.json"
        raw = _put_json(root, rel, doc)
        return rel, raw, _typed_ref(rel, "newrouge.b-route-binding.v1", plan_id, 1, raw)

    p1_rel, p1_raw, p1_ref = _build_flow_plan("plan-s1", "flow-s1", "REQ-S1", src1)
    b1_rel, b1_raw, b1_ref = _build_binding("plan-s1", p1_ref, 101, "NG-0101", "REQ-S1", "flow-s1",
                                            contract_rel="Game.Core/Contracts/E2E/Scope1Contract.cs", contract_raw=contract_1, test_id="t-s1")
    p3_rel, p3_raw, p3_ref = _build_flow_plan("plan-s3", "flow-s3", "REQ-S3", src3)
    b3_rel, b3_raw, b3_ref = _build_binding("plan-s3", p3_ref, 301, "NG-0301", "REQ-S3", "flow-s3",
                                            contract_rel="Game.Core/Contracts/E2E/Scope3Contract.cs", contract_raw=contract_3, test_id="t-s3")
    p4_rel, p4_raw, p4_ref = _build_flow_plan("plan-nonflow", None, "REQ-NF", src3, nonflow=True)
    b4_rel, b4_raw, b4_ref = _build_binding("plan-nonflow", p4_ref, 401, "NG-0401", "REQ-NF", None, nonflow=True)

    adr_raw = (root / task_resolver.ADR_0040).read_bytes()
    policy_rel = "docs/planning/b-route/policy.v1.json"
    policy_raw = _put_json(root, policy_rel, {
        "schema_version": "newrouge.b-route-policy.v1",
        "policy_id": "policy",
        "policy_revision": 1,
        "switch_boundary": {
            "default_route": "A",
            "a_write_allowed": True,
            "allowed_a_operations": ["inspect", "read"],
            "authority_refs": [_owned_ref("authority", task_resolver.ADR_0040, [(task_resolver.ADR_0040, adr_raw)])],
        },
        "frozen_a_refs": [],
    })
    policy_ref = _typed_ref(policy_rel, "newrouge.b-route-policy.v1", "policy", 1, policy_raw)

    origins_rel = "docs/planning/b-route/task-origins.v1.json"
    origins_raw = _put_json(root, origins_rel, {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": 1,
        "tasks": [
            {
                "task_id": 101,
                "source_refs": [_owned_ref("source_manifest", src1["m_rel"], [(src1["m_rel"], src1["m_raw"])])],
                "plan_refs": [p1_ref],
                "binding_refs": [b1_ref],
            },
            {
                "task_id": 301,
                "source_refs": [_owned_ref("source_manifest", src3["m_rel"], [(src3["m_rel"], src3["m_raw"])])],
                "plan_refs": [p3_ref],
                "binding_refs": [b3_ref],
            },
            {
                "task_id": 401,
                "source_refs": [_owned_ref("source_manifest", src3["m_rel"], [(src3["m_rel"], src3["m_raw"])])],
                "plan_refs": [p4_ref],
                "binding_refs": [b4_ref],
            },
        ],
        "frozen_legacy_refs": [],
    })
    origins_ref = _typed_ref(origins_rel, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

    def _write_commit(op_id: str, scope_id: str, plan_rel: str, plan_raw: bytes, plan_ref: dict, bind_rel: str, bind_raw: bytes, bind_ref: dict, src: dict[str, Any], extra_targets: list[tuple[str, bytes]] = ()) -> dict[str, Any]:
        targets = [
            {"path": plan_rel, "before_digest": None, "after_digest": codec.raw_digest(plan_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(plan_raw)},
            {"path": bind_rel, "before_digest": None, "after_digest": codec.raw_digest(bind_raw), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(bind_raw)},
        ]
        for ep, er in extra_targets:
            targets.append({"path": ep, "before_digest": None, "after_digest": codec.raw_digest(er), "verification_mode": "immutable_bytes", "codec_version": None, "projection_digest": codec.raw_digest(er)})
        c_rel = f"docs/planning/b-route/commits/{op_id}.json"
        c_raw = _put_json(root, c_rel, {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": op_id,
            "revision": 1,
            "operation_digest": codec.canonical_digest({"op": op_id, "scope": scope_id}),
            "scopes": [scope_id],
            "authority": [
                {"path": src["m_rel"], "before_digest": codec.raw_digest(src["m_raw"]), "after_digest": codec.raw_digest(src["m_raw"])},
                {"path": src["l_rel"], "before_digest": codec.raw_digest(src["l_raw"]), "after_digest": codec.raw_digest(src["l_raw"])},
                {"path": src["p_rel"], "before_digest": codec.raw_digest(src["p_raw"]), "after_digest": codec.raw_digest(src["p_raw"])},
                {"path": task_resolver.ADR_0040, "before_digest": codec.raw_digest(adr_raw), "after_digest": codec.raw_digest(adr_raw)},
            ],
            "targets": targets,
            "plan_refs": [plan_ref],
            "binding_refs": [bind_ref],
            "resolved_definitions": [],
            "result": {"target_paths": [t["path"] for t in targets], "scope_ids": [scope_id]},
        })
        return _typed_ref(c_rel, "newrouge.b-route-commit.v1", op_id, 1, c_raw)

    c1_ref = _write_commit("OP-S1", "scope-s1", p1_rel, p1_raw, p1_ref, b1_rel, b1_raw, b1_ref, src1, [(policy_rel, policy_raw), (origins_rel, origins_raw)])
    c3_ref = _write_commit("OP-S3", "scope-s3", p3_rel, p3_raw, p3_ref, b3_rel, b3_raw, b3_ref, src3)
    c4_ref = _write_commit("OP-NF", "scope-nonflow", p4_rel, p4_raw, p4_ref, b4_rel, b4_raw, b4_ref, src3)

    _put_json(root, records.CATALOG_PATH, {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": 1,
        "policy_ref": policy_ref,
        "origins_ref": origins_ref,
        "scope_heads": [
            {"scope_id": "scope-s1", "plan_refs": [p1_ref], "binding_refs": [b1_ref], "receipt_ref": c1_ref},
            {"scope_id": "scope-s3", "plan_refs": [p3_ref], "binding_refs": [b3_ref], "receipt_ref": c3_ref},
            {"scope_id": "scope-nonflow", "plan_refs": [p4_ref], "binding_refs": [b4_ref], "receipt_ref": c4_ref},
        ],
        "definition_owners": [
            {"kind": "flow", "definition_id": "flow-s1", "plan_ref": copy.deepcopy(p1_ref)},
            {"kind": "flow", "definition_id": "flow-s3", "plan_ref": copy.deepcopy(p3_ref)},
        ],
        "task_index": [
            {"task_id": 101, "plan_refs": [p1_ref], "binding_refs": [b1_ref]},
            {"task_id": 301, "plan_refs": [p3_ref], "binding_refs": [b3_ref]},
            {"task_id": 401, "plan_refs": [p4_ref], "binding_refs": [b4_ref]},
        ],
    })
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed shared scope repo")
    return {"src1": src1, "src2": src2, "src3": src3, "build_plan": _build_flow_plan, "build_binding": _build_binding, "write_commit": _write_commit}


def _reconcile_ac2_task_readiness(ws: Path, task_id: int, req_id: str, contract_rel: str, test_rel: str) -> dict[str, Any]:
    """Run real Chapter 5 reconciliation for an AC-2 task so initial gate readiness is genuinely green."""
    decisions = {
        "acceptance_links": [
            {
                "acceptance_index": 1,
                "requirement_ids": [req_id],
                "authority_refs": [contract_rel],
                "test_refs": [test_rel],
            }
        ],
        "authority_decisions": [
            {
                "authority_ref": contract_rel,
                "status": "compatible",
                "rationale": f"Contract {contract_rel} matches Stage-5 binding for task {task_id}.",
            }
        ],
        "dependency_decisions": [],
        "overlap_decisions": [],
    }
    return ch5_b.reconcile_b_route_chapter5(
        ws,
        task_id=task_id,
        decisions=decisions,
        require_full_audit_proof=False,
    )


def _ac2_run_drift_parity_worker(ws_drift: Path) -> dict[str, Any]:
    """Isolated parallel worker testing Scope 1 contract drift against live readiness (Tasks 101 & 301)."""
    c1_contract_path = ws_drift / "Game.Core/Contracts/E2E/Scope1Contract.cs"
    c1_contract_orig = c1_contract_path.read_bytes()
    c1_contract_path.write_bytes(b"public sealed class Scope1Contract { public int V = 2; }\n")
    drift_parity_101 = parity.evaluate_entrypoint_parity(ws_drift, task_id=101)
    drift_gate_301 = ch6_gate.evaluate_chapter6_gate(ws_drift, 301, consumer="ac2_drift_301", lock_mode="none")
    drift_committed = commit.read_committed(ws_drift)
    c1_contract_path.write_bytes(c1_contract_orig)
    gate_101_restored = ch6_gate.evaluate_chapter6_gate(ws_drift, 101, consumer="ac2_restored_101", lock_mode="none")
    ok = (
        bool(drift_parity_101.get("parity_ok"))
        and (drift_parity_101.get("admitted") is False)
        and drift_parity_101.get("public_reason_code") in (codec.ReasonCode.INPUT_STALE.value, codec.ReasonCode.DIGEST_MISMATCH.value)
        and bool(drift_committed.get("formal_adoption"))
        and (drift_gate_301.get("ok") is True)
        and (gate_101_restored.get("ok") is True)
    )
    return {"ok": ok}


def _run_ac2_shared_task_and_scope_drift_matrix(source_root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    with _temp_workspace("nr410-ac2-") as ac2_tmp:
        ws = ac2_tmp / "ws_main"
        ws.mkdir(parents=True, exist_ok=True)
        seeded = _seed_shared_scope_repo(ws, source_root)
        # Reconcile real Chapter 5 readiness for BOTH Task 101 and Task 301 BEFORE any drift or Scope 2 join!
        rec_101_init = _reconcile_ac2_task_readiness(
            ws, 101, "REQ-S1", "Game.Core/Contracts/E2E/Scope1Contract.cs", "Game.Core.Tests/E2E/Scope1Tests.cs"
        )
        rec_301_init = _reconcile_ac2_task_readiness(
            ws, 301, "REQ-S3", "Game.Core/Contracts/E2E/Scope3Contract.cs", "Game.Core.Tests/E2E/Scope3Tests.cs"
        )
        origin_101_before = task_resolver.resolve_task_origin(ws, 101)
        iset_101_before = input_set_mod.resolve_input_set(ws, task_id=101)
        origin_301_before = task_resolver.resolve_task_origin(ws, 301)
        iset_301_before = input_set_mod.resolve_input_set(ws, task_id=301)
        gate_101_before = ch6_gate.evaluate_chapter6_gate(ws, 101, consumer="ac2_before_101", lock_mode="none")
        gate_301_before = ch6_gate.evaluate_chapter6_gate(ws, 301, consumer="ac2_before_301", lock_mode="none")
        initial_readiness_ok = (
            bool(rec_101_init.get("ok"))
            and bool(rec_301_init.get("ok"))
            and (gate_101_before.get("ok") is True)
            and (gate_301_before.get("ok") is True)
        )

        # Snapshot reconciled workspace for parallel drift parity worker + parallel integration-owner worker!
        ws_drift = ac2_tmp / "ws_drift"
        shutil.copytree(ws, ws_drift)
        ws_io = ac2_tmp / "ws_io"
        ws_io.mkdir(parents=True, exist_ok=True)
        ac2_handles = _start_parallel_workers(
            ac2_tmp,
            {
                "drift": ("ac2_drift", [str(ws_drift)]),
                "intowner": ("ac2_intowner", [str(ws_io), str(source_root)]),
            },
        )
        try:
            # Now adopt Scope 2 (plan-s2) that ALSO maps to shared Task 101!
            p2_rel, p2_raw, p2_ref = seeded["build_plan"]("plan-s2", None, "REQ-S2", seeded["src2"], nonflow=True)
            b2_rel, b2_raw, b2_ref = seeded["build_binding"]("plan-s2", p2_ref, 101, "NG-0101", "REQ-S2", None, nonflow=True)
            origins_doc = _read_json(ws, task_resolver.ORIGINS_PATH)
            src2 = seeded["src2"]
            for row in origins_doc["tasks"]:
                if int(row["task_id"]) == 101:
                    row["source_refs"].append(_owned_ref("authority", src2["gdd_rel"], [(src2["gdd_rel"], src2["gdd_raw"])]))
                    row["plan_refs"].append(p2_ref)
                    row["binding_refs"].append(b2_ref)
            origins_raw = _put_json(ws, task_resolver.ORIGINS_PATH, origins_doc)
            origins_dg = codec.raw_digest(origins_raw)
            c1_rel = "docs/planning/b-route/commits/OP-S1.json"
            c1_doc = _read_json(ws, c1_rel)
            for tgt in c1_doc["targets"]:
                if tgt["path"] == task_resolver.ORIGINS_PATH:
                    tgt["after_digest"] = origins_dg
                    tgt["projection_digest"] = origins_dg
            c1_raw = _put_json(ws, c1_rel, c1_doc)
            c1_ref = _typed_ref(c1_rel, "newrouge.b-route-commit.v1", "OP-S1", 1, c1_raw)
            c2_ref = seeded["write_commit"]("OP-S2", "scope-s2", p2_rel, p2_raw, p2_ref, b2_rel, b2_raw, b2_ref, seeded["src2"])

            cat = _read_json(ws, records.CATALOG_PATH)
            cat["revision"] = 2
            cat["origins_ref"] = _typed_ref(task_resolver.ORIGINS_PATH, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)
            for sh in cat["scope_heads"]:
                if sh["scope_id"] == "scope-s1":
                    sh["receipt_ref"] = c1_ref
            cat["scope_heads"].append({"scope_id": "scope-s2", "plan_refs": [p2_ref], "binding_refs": [b2_ref], "receipt_ref": c2_ref})
            for trow in cat["task_index"]:
                if int(trow["task_id"]) == 101:
                    trow["plan_refs"].append(p2_ref)
                    trow["binding_refs"].append(b2_ref)
            _put_json(ws, records.CATALOG_PATH, cat)

            # Evaluate real 5-entrypoint parity + committed reader + Knowledge projection after Scope 2 joins Task 101
            origin_101_after = task_resolver.resolve_task_origin(ws, 101)
            iset_101_after = input_set_mod.resolve_input_set(ws, task_id=101)
            committed_after_join = commit.read_committed(ws)
            parity_101_after = parity.evaluate_entrypoint_parity(ws, task_id=101)
            proj_101_after = knowledge_projection.build_b_route_knowledge_projection(ws, mode="workspace_preview", task_id="101")

            # Unrelated Scope 3 (Task 301) MUST remain unaffected and still admitted (ok=True)!
            origin_301_after = task_resolver.resolve_task_origin(ws, 301)
            iset_301_after = input_set_mod.resolve_input_set(ws, task_id=301)
            gate_301_after = ch6_gate.evaluate_chapter6_gate(ws, 301, consumer="ac2_after_301", lock_mode="none")

            plans_101_after = sorted(r["entity_id"] for r in (origin_101_after.get("plan_refs") or []))
            digest_expanded = (
                initial_readiness_ok
                and origin_101_before.get("ok")
                and origin_101_after.get("ok")
                and origin_101_before.get("applicable_set_digest") != origin_101_after.get("applicable_set_digest")
                and plans_101_after == ["plan-s1", "plan-s2"]
                and iset_101_before.get("input_set_digest") != iset_101_after.get("input_set_digest")
            )
            ep_map = parity_101_after.get("entrypoints") or {}
            all_entrypoints_consistent = (
                bool(committed_after_join.get("formal_adoption"))
                and bool(parity_101_after.get("parity_ok"))
                and (parity_101_after.get("admitted") is False)
                and parity_101_after.get("public_reason_code") in (codec.ReasonCode.INPUT_STALE.value, codec.ReasonCode.DIGEST_MISMATCH.value)
                and set(ep_map.keys()) == {"cli", "direct", "resume", "route", "page"}
                and all(ep_map[k].get("admitted") is False for k in ("cli", "direct", "resume", "route", "page"))
                and parity_101_after.get("applicable_set_digest") == origin_101_after.get("applicable_set_digest")
                and bool(proj_101_after.get("layers", {}).get("tasks"))
            )
            unrelated_scope3_unaffected = (
                origin_301_after.get("ok")
                and origin_301_after.get("applicable_set_digest") == origin_301_before.get("applicable_set_digest")
                and iset_301_after.get("ok")
                and iset_301_after.get("input_set_digest") == iset_301_before.get("input_set_digest")
                and (gate_301_after.get("ok") is True)
            )

            # Inject unknown legacy pending journal -> blocks with resume_ref, recovers via real journal.resume_journal
            # following the exact plan_capabilities.apply completion contract (keeping apply-journal.json intact!).
            legacy_dir = ws / "logs/ci/capability-planning/old-legacy"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            cap_rel = "docs/planning/semantic-topology/capabilities.v1.json"
            cap_payload = {"schema_version": "newrouge.semantic-topology.capabilities.v1", "capabilities": []}
            cap_sha = codec.raw_digest(_encoded_json(cap_payload))
            _put_json(ws, "logs/ci/capability-planning/old-legacy/run.json", {
                "schema_version": "newrouge.capability-planning-run.v1",
                "run_id": "old-legacy", "phase": "prepared", "applied": False,
            })
            legacy_journal_path = legacy_dir / "apply-journal.json"
            journal.create_journal(
                ws,
                legacy_journal_path,
                {ws / cap_rel: cap_payload},
                {},
                {"status": "applied", "run_id": "old-legacy", "capabilities_sha256": cap_sha},
            )
            _put_json(ws, op_scope.CAP_PENDING, {
                "run_id": "old-legacy",
                "journal_path": "logs/ci/capability-planning/old-legacy/apply-journal.json",
            })
            legacy_routes = op_scope.legacy_recovery_routes(ws)
            union_guard_blocked = parity.verify_shared_task_union_scope_and_pending_guard(ws, task_id=101)
            legacy_pending_ok = (
                bool(legacy_routes)
                and legacy_routes[0].get("owner_api") == "plan_capabilities.apply"
                and bool(legacy_routes[0].get("requires_original_confirmation"))
                and (not union_guard_blocked.get("ok"))
                and bool(union_guard_blocked.get("diagnostics"))
                and all(_is_valid_six_field_diag(d) for d in union_guard_blocked["diagnostics"])
                and bool(union_guard_blocked["diagnostics"][0].get("resume_ref"))
            )
            # Recover legacy pending through real journal.resume_journal + original apply completion records
            resumed_legacy = journal.resume_journal(
                ws,
                legacy_journal_path,
                lambda target_path, payload: _put_json(ws, target_path.relative_to(ws).as_posix(), payload),
            )
            resumed_jdoc = _read_json(ws, "logs/ci/capability-planning/old-legacy/apply-journal.json")
            _put_json(ws, "logs/ci/capability-planning/old-legacy/apply-summary.json", {
                "run_id": "old-legacy",
                "status": "applied",
                "capabilities_sha256": cap_sha,
            })
            _put_json(ws, "logs/ci/capability-planning/old-legacy/run.json", {
                "schema_version": "newrouge.capability-planning-run.v1",
                "run_id": "old-legacy",
                "phase": "applied",
                "applied": True,
                "applied_capabilities_sha256": cap_sha,
            })
            if resumed_jdoc.get("status") == "complete" and (ws / op_scope.CAP_PENDING).is_file():
                (ws / op_scope.CAP_PENDING).unlink()
            b_intact_after_legacy_clear = (
                resumed_legacy.get("status") == "applied"
                and resumed_jdoc.get("status") == "complete"
                and legacy_journal_path.is_file()
                and (ws / cap_rel).is_file()
                and op_scope.legacy_recovery_routes(ws) == []
                and bool(task_resolver.resolve_task_origin(ws, 101).get("ok"))
                and (ch6_gate.evaluate_chapter6_gate(ws, 301, consumer="ac2_post_legacy_301", lock_mode="none").get("ok") is True)
            )

            # Anti-bypass negative controls: delete origins / delete manifest / delete commit trace / fake N/A / delete .pending
            anti_bypass: dict[str, bool] = {}

            # 1) Delete task-origins.v1.json -> NEVER downgrades to legacy A!
            origins_backup = (ws / task_resolver.ORIGINS_PATH).read_bytes()
            (ws / task_resolver.ORIGINS_PATH).unlink()
            res_no_origins = task_resolver.resolve_task_origin(ws, 101)
            anti_bypass["delete_origins_blocked_never_legacy_a"] = (not res_no_origins.get("ok")) and res_no_origins.get("route") == "blocked"
            (ws / task_resolver.ORIGINS_PATH).write_bytes(origins_backup)

            # 2) Delete manifest -> Chapter 6 gate & InputSet block!
            mvg_backup = (ws / "docs/testing/mvg/e2e-shared.json").read_bytes()
            (ws / "docs/testing/mvg/e2e-shared.json").unlink()
            res_no_mvg = input_set_mod.resolve_input_set(ws, task_id=101)
            anti_bypass["delete_manifest_blocked"] = not res_no_mvg.get("ok")
            (ws / "docs/testing/mvg/e2e-shared.json").write_bytes(mvg_backup)

            # 3) Delete commit receipt trace -> NEVER downgrades to legacy A!
            c1_backup = (ws / c1_rel).read_bytes()
            (ws / c1_rel).unlink()
            res_no_trace = task_resolver.resolve_task_origin(ws, 101)
            anti_bypass["delete_commit_trace_blocked_never_legacy_a"] = (not res_no_trace.get("ok")) and res_no_trace.get("route") == "blocked"
            (ws / c1_rel).write_bytes(c1_backup)

            # 4) Inject fake N/A acceptance label -> NEVER exempts or passes!
            back_backup = (ws / ".taskmaster/tasks/tasks_back.json").read_bytes()
            back_rows = _read_json(ws, ".taskmaster/tasks/tasks_back.json")
            back_rows[0]["labels"] = ["mvg:n/a", "N/A"]
            _put_json(ws, ".taskmaster/tasks/tasks_back.json", back_rows)
            res_fake_na = task_resolver.resolve_task_origin(ws, 101)
            gate_fake_na = ch6_gate.evaluate_chapter6_gate(ws, 101, consumer="ac2_fake_na_probe", lock_mode="none")
            anti_bypass["fake_na_never_bypasses"] = (
                (not gate_fake_na.get("ok"))
                and res_fake_na.get("route") != "A"
                and bool(res_fake_na.get("non_flow_summary", {}).get("detected_non_authoritative_labels"))
                and (not res_fake_na.get("non_flow_summary", {}).get("free_label_exemption_allowed"))
            )
            (ws / ".taskmaster/tasks/tasks_back.json").write_bytes(back_backup)

            # 5) Delete a .pending sync/commit marker on an incomplete operation -> NEVER grants unverified pass!
            pend_op_id = "OP-DEL-PENDING-PROBE"
            pend_intent_rel, pend_marker_rel = commit._paths(pend_op_id)
            pend_index_rel = journal.OPERATION_STORE + "/pending.json"
            _put_json(ws, pend_intent_rel, {
                "schema_version": "newrouge.b-route-commit-intent.v1",
                "operation_id": pend_op_id,
                "status": "pending",
            })
            _put_json(ws, pend_marker_rel, {"operation_id": pend_op_id, "status": "pending"})
            _put_json(ws, pend_index_rel, {
                "schema_version": journal.PENDING_SCHEMA,
                "operations": [{"operation_id": pend_op_id, "state": "applying"}],
            })
            (ws / pend_marker_rel).unlink()
            read_after_del_pend_blocked = False
            try:
                commit.read_committed(ws)
            except codec.CodecError as err:
                read_after_del_pend_blocked = _is_valid_six_field_diag(err.diagnostic.to_dict())
            gate_after_del_pend = ch6_gate.evaluate_chapter6_gate(ws, 301, consumer="ac2_del_pending_probe", lock_mode="none")
            anti_bypass["delete_pending_marker_never_bypasses"] = (
                read_after_del_pend_blocked and (gate_after_del_pend.get("ok") is False)
            )
            _rmtree_readonly_safe(ws / journal.OPERATION_STORE)

            # Positive & negative: Legal non-Flow other_verification
            nf_pos = task_resolver.resolve_task_origin(ws, 401)
            nf_pos_ok = bool(nf_pos.get("ok")) and nf_pos.get("route") == "B" and nf_pos["non_flow_summary"]["dispositions_by_kind"]["other_verification"] >= 1
            # Negative: delete other_verification_refs file -> InputSet blocks!
            ov_path = ws / "docs/testing/nonflow-static-rule.md"
            ov_backup = ov_path.read_bytes()
            ov_path.unlink()
            nf_neg = input_set_mod.resolve_input_set(ws, task_id=401)
            nf_neg_blocked = not nf_neg.get("ok")
            ov_path.write_bytes(ov_backup)

            ac2_sub = _collect_parallel_workers(ac2_handles, timeout_sec=180.0)
        finally:
            _cleanup_parallel_workers(ac2_handles)

        source_drift_isolated = bool(ac2_sub["drift"].get("ok"))
        io_check = ac2_sub["intowner"]

    checks = {
        "initial_readiness_tasks_101_and_301_ok": initial_readiness_ok,
        "applicable_set_digest_expanded": digest_expanded,
        "all_entrypoints_consistent_block": all_entrypoints_consistent,
        "unrelated_scope3_unaffected": unrelated_scope3_unaffected,
        "source_drift_isolated_to_affected_scope": source_drift_isolated,
        "legacy_pending_blocked_and_original_contract_preserved": legacy_pending_ok and b_intact_after_legacy_clear,
        "anti_bypass": anti_bypass,
        "non_flow_positive_ok": nf_pos_ok and io_check["nonflow_verdict_pos_ok"],
        "non_flow_negative_blocked": nf_neg_blocked and io_check["nonflow_verdict_neg_blocked"],
        "integration_owner_positive_non_self_locking": io_check["integration_owner_pos_ok"],
        "integration_owner_negative_blocked": io_check["integration_owner_neg_blocked"],
    }
    all_ok = (
        initial_readiness_ok
        and digest_expanded
        and all_entrypoints_consistent
        and unrelated_scope3_unaffected
        and source_drift_isolated
        and legacy_pending_ok
        and b_intact_after_legacy_clear
        and all(anti_bypass.values())
        and nf_pos_ok
        and nf_neg_blocked
        and io_check["nonflow_verdict_pos_ok"]
        and io_check["nonflow_verdict_neg_blocked"]
        and io_check["integration_owner_pos_ok"]
        and io_check["integration_owner_neg_blocked"]
    )
    if not all_ok:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "ac2_shared_scope",
            "all shared-task multi-scope, drift, legacy pending, anti-bypass, and non-flow/integration-owner checks pass",
            checks,
            None,
        ))
    return {
        "ok": all_ok,
        "status": "passed" if all_ok else "blocked",
        "applicable_set_digest_before": origin_101_before.get("applicable_set_digest"),
        "applicable_set_digest_after": origin_101_after.get("applicable_set_digest"),
        "plans_for_shared_task_after": plans_101_after,
        "checks": checks,
        "diagnostics": diagnostics,
    }


def _seed_flow_ab_git_repo(
    root: Path,
    source_root: Path,
    *,
    flow_b_implemented: bool = False,
    include_flow_b_in_manifest: bool = True,
    include_nonflow_plan: bool = False,
    nonflow_valid: bool = True,
    owner200_is_integration_owner: bool = True,
    shared_test_across_ac: bool = False,
) -> dict[str, Any]:
    """Seed a clean git repo for Story 4.1 -> 4.2 -> 4.3 -> 4.4 -> 4.5 end-to-end chains."""
    _copy_repo_schemas_and_adr(source_root, root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "e2e@example.invalid")
    _git(root, "config", "user.name", "E2E")

    contract_a = "Game.Core/Contracts/Offers/OfferLockSnapshot.cs"
    contract_c = "Game.Core/Contracts/Map/MapRouteSnapshot.cs"
    contract_b = "Game.Core/Contracts/Shop/ShopOfferSnapshot.cs"
    adapter_a = "Game.Godot/Scripts/Reward/RewardOfferProvider.cs"
    scene_a = "Game.Godot/Scenes/Reward.tscn"
    input_test_a = "Tests.Godot/tests/Integration/Mvg/test_reward_input_journey.gd"
    scene_test_c = "Tests.Godot/tests/Integration/Mvg/test_map_scene.gd"
    scene_test_b = "Tests.Godot/tests/Integration/Mvg/test_shop_scene.gd"
    core_test_a = "Game.Core.Tests/Integration/RewardTests.cs"
    core_test_c = "Game.Core.Tests/Integration/MapRouteTests.cs"
    core_test_b = "Game.Core.Tests/Integration/ShopTests.cs"
    nonflow_script = "scripts/python/verify_nonflow_budget.py"

    flow_a = "combat-reward-return"
    flow_b = "shop-purchase-flow"
    flow_c = "map-route-flow"
    full_manifest = "docs/testing/mvg/m1-full.json"

    _put_bytes(root, ".gitignore", "logs/\n")
    _put_bytes(root, "project.godot", '[application]\nconfig/name="newrouge"\n')
    _put_bytes(root, "Tests.Godot/project.godot", '[application]\nconfig/name="newrouge-tests"\n')
    _put_bytes(root, contract_a, "public sealed class OfferLockSnapshot { public int V = 1; }\n")
    _put_bytes(root, contract_c, "public sealed class MapRouteSnapshot { public int V = 1; }\n")
    _put_bytes(root, contract_b, "public sealed class ShopOfferSnapshot { public int V = 1; }\n")
    _put_bytes(root, adapter_a, (
        "using Godot;\n"
        "public partial class RewardOfferProvider : Control\n"
        "{\n"
        "    public override void _Ready()\n"
        "    {\n"
        "        var claimBtn = GetNode<Button>(\"ClaimButton\");\n"
        "        claimBtn.Pressed += OnClaimPressed;\n"
        "    }\n"
        "    public void OnClaimPressed() {}\n"
        "}\n"
    ))
    _put_bytes(root, scene_a, (
        "[gd_scene load_steps=2 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://Game.Godot/Scripts/Reward/RewardOfferProvider.cs\" id=\"1_rew\"]\n"
        "[node name=\"RewardRoot\" type=\"Control\"]\n"
        "script = ExtResource(\"1_rew\")\n"
        "[node name=\"ClaimButton\" type=\"Button\" parent=\".\"]\n"
    ))
    _put_bytes(root, input_test_a, 'extends GdUnitTestSuite\nfunc test_reward_input():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n')
    _put_bytes(root, scene_test_c, "extends GdUnitTestSuite\nfunc test_map_scene():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n")
    _put_bytes(root, scene_test_b, "extends GdUnitTestSuite\nfunc test_shop_scene():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n")
    _put_bytes(root, core_test_a, "public class RewardTests { [Fact] public void TestCase() {} }\n")
    _put_bytes(root, core_test_c, "public class MapRouteTests { [Fact] public void TestCase() {} }\n")
    _put_bytes(root, core_test_b, "public class ShopTests { [Fact] public void TestCase() {} }\n")
    if nonflow_valid:
        _put_bytes(root, nonflow_script, "print('nonflow ok')\n")

    master_rows = [
        {"id": 84, "title": "Offer Core", "status": "done", "dependencies": []},
        {"id": 114, "title": "Reward UI", "status": "done", "dependencies": [84]},
        {"id": 60, "title": "Map Route", "status": "done", "dependencies": []},
        {"id": 70, "title": "Shop Core", "status": "done" if flow_b_implemented else "pending", "dependencies": [84]},
        {"id": 200, "title": "Dedicated Integration Owner", "status": "in-progress", "dependencies": []},
    ]
    if include_nonflow_plan:
        master_rows.append({"id": 95, "title": "Static Budget Check", "status": "done", "dependencies": []})
    _put_json(root, ".taskmaster/tasks/tasks.json", {"master": {"tasks": master_rows}})
    back_rows = [
        {"id": "B-84", "taskmaster_id": 84, "status": "done", "contractRefs": [contract_a], "overlay_refs": [], "test_refs": [core_test_a]},
        {"id": "B-60", "taskmaster_id": 60, "status": "done", "contractRefs": [contract_c], "overlay_refs": [], "test_refs": [core_test_c]},
        {"id": "B-70", "taskmaster_id": 70, "status": "done" if flow_b_implemented else "pending", "contractRefs": [contract_b, contract_a], "overlay_refs": [], "test_refs": [core_test_b]},
    ]
    if include_nonflow_plan:
        back_rows.append({"id": "B-95", "taskmaster_id": 95, "status": "done", "contractRefs": [], "overlay_refs": [], "test_refs": []})
    _put_json(root, ".taskmaster/tasks/tasks_back.json", back_rows)
    _put_json(root, ".taskmaster/tasks/tasks_gameplay.json", [
        {"id": "G-114", "taskmaster_id": 114, "status": "done", "contractRefs": [contract_a], "overlay_refs": [], "test_refs": [input_test_a]},
        {"id": "G-60", "taskmaster_id": 60, "status": "done", "contractRefs": [contract_c], "overlay_refs": [], "test_refs": [scene_test_c]},
        {"id": "G-70", "taskmaster_id": 70, "status": "done" if flow_b_implemented else "pending", "contractRefs": [contract_b], "overlay_refs": [], "test_refs": [scene_test_b]},
        {"id": "G-200", "taskmaster_id": 200, "status": "in-progress", "contractRefs": [], "overlay_refs": [], "test_refs": []},
    ])

    def _use(kind: str, def_id: str, pid: str) -> dict[str, Any]:
        return {"kind": kind, "definition_id": def_id, "owner_plan_id": pid, "owner_revision": 1}

    def _owned_zero(owner: str, ref: str, *paths: str) -> dict[str, Any]:
        return {"owner": owner, "ref": ref, "files": [{"path": p, "raw_digest": "sha256:" + "0" * 64} for p in paths]}

    p1 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P1",
        "revision": 1,
        "requirements": [{"requirement_id": "FR-1", "source_block_ids": ["SB-1"], "acceptance_intent": "claim reward", "non_task_sinks": []}],
        "definitions": {
            "flows": [{
                "id": flow_a, "requirement_ids": ["FR-1"], "source_block_ids": ["SB-1"], "capability_ids": ["cap-reward"],
                "state_owners": [_use("state", "OfferLock", "P1")],
                "ui": {"applicability": "applicable", "scene_refs": [scene_a]},
                "human_verification": {"applicability": "applicable", "checks": ["Verify reward claim feel on Windows"]},
            }],
            "commands": [{"id": "ClaimReward", "requirement_ids": ["FR-1"], "responsibility": "claim", "uses": [_use("state", "OfferLock", "P1")]}],
            "states": [{"id": "OfferLock", "requirement_ids": ["FR-1"], "responsibility": "lock", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "primary flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-1", "disposition": "flow", "primary_flow_id": flow_a}],
        "requirement_route_memberships": [{"requirement_id": "FR-1", "flow_id": flow_a, "observable_role": "Reward claim state"}],
    }
    p2 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P2",
        "revision": 1,
        "requirements": [{"requirement_id": "FR-60", "source_block_ids": ["SB-60"], "acceptance_intent": "map route", "non_task_sinks": []}],
        "definitions": {
            "flows": [{
                "id": flow_c, "requirement_ids": ["FR-60"], "source_block_ids": ["SB-60"], "capability_ids": ["cap-map"],
                "state_owners": [_use("state", "MapState", "P2")] + ([_use("state", "OfferLock", "P1")] if shared_test_across_ac else []),
            }],
            "commands": [],
            "states": [{"id": "MapState", "requirement_ids": ["FR-60"], "responsibility": "map", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-60", "disposition": "flow", "rationale": "map flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-60", "disposition": "flow", "primary_flow_id": flow_c}],
        "requirement_route_memberships": [{"requirement_id": "FR-60", "flow_id": flow_c, "observable_role": "Map route advancement"}],
    }
    p3 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P3",
        "revision": 1,
        "requirements": [{"requirement_id": "FR-70", "source_block_ids": ["SB-70"], "acceptance_intent": "shop purchase", "non_task_sinks": []}],
        "definitions": {
            "flows": [{
                "id": flow_b, "requirement_ids": ["FR-70"], "source_block_ids": ["SB-70"], "capability_ids": ["cap-shop"],
                "state_owners": [_use("state", "OfferLock", "P1"), _use("state", "ShopState", "P3")],
            }],
            "commands": [],
            "states": [{"id": "ShopState", "requirement_ids": ["FR-70"], "responsibility": "shop", "uses": [_use("state", "OfferLock", "P1")]}],
        },
        "applicability": [{"requirement_id": "FR-70", "disposition": "flow", "rationale": "shop flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-70", "disposition": "flow", "primary_flow_id": flow_b}],
        "requirement_route_memberships": [{"requirement_id": "FR-70", "flow_id": flow_b, "observable_role": "Shop offer lock"}],
    }
    _put_json(root, "docs/planning/b-route/plans/P1.plan.v1.json", p1)
    _put_json(root, "docs/planning/b-route/plans/P2.plan.v1.json", p2)
    _put_json(root, "docs/planning/b-route/plans/P3.plan.v1.json", p3)

    p1_ref = _canonical_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P1.plan.v1.json", "P1")
    p2_ref = _canonical_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P2.plan.v1.json", "P2")
    p3_ref = _canonical_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P3.plan.v1.json", "P3")

    t200_mapping = (
        {"task_id": 200, "requirement_ids": ["FR-1"], "flow_ids": [flow_a], "role": "integration_only_owner", "integration_only_owner": True}
        if owner200_is_integration_owner
        else {"task_id": 200, "requirement_ids": ["FR-1"], "flow_ids": [flow_a], "role": "producer"}
    )
    b1 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P1", "plan_ref": p1_ref, "binding_revision": 1, "stage": "5", "parts": [],
        "manifest_refs": [_owned_zero("manifest", "m1-full", full_manifest)],
        "other_verification_refs": [],
        "task_mappings": [
            {"task_id": 84, "requirement_ids": ["FR-1"], "flow_ids": [flow_a], "role": "producer"},
            {"task_id": 114, "requirement_ids": ["FR-1"], "flow_ids": [flow_a], "role": "consumer"},
            t200_mapping,
        ],
        "contract_bindings": [{"contract_ref": contract_a, "flow_ids": [flow_a], "task_ids": [84, 114]}],
        "implementation_objects": [],
        "obligations": [],
    }
    b2 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P2", "plan_ref": p2_ref, "binding_revision": 1, "stage": "5", "parts": [],
        "manifest_refs": [_owned_zero("manifest", "m1-full", full_manifest)],
        "other_verification_refs": [],
        "task_mappings": [{"task_id": 60, "requirement_ids": ["FR-60"], "flow_ids": [flow_c], "role": "producer"}],
        "contract_bindings": [{"contract_ref": contract_c, "flow_ids": [flow_c], "task_ids": [60]}]
        + ([{"contract_ref": contract_a, "flow_ids": [flow_c], "task_ids": [60]}] if shared_test_across_ac else []),
        "implementation_objects": [],
        "obligations": [],
    }
    b3 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P3", "plan_ref": p3_ref, "binding_revision": 1, "stage": "5", "parts": [],
        "manifest_refs": [_owned_zero("manifest", "m1-full", full_manifest)],
        "other_verification_refs": [],
        "task_mappings": [
            {"task_id": 70, "requirement_ids": ["FR-70"], "flow_ids": [flow_b], "role": "producer"},
            {"task_id": 84, "requirement_ids": ["FR-70"], "flow_ids": [flow_b], "role": "consumer"},
        ],
        "contract_bindings": [
            {"contract_ref": contract_b, "flow_ids": [flow_b], "task_ids": [70]},
            {"contract_ref": contract_a, "flow_ids": [flow_b], "task_ids": [84, 70]},
        ],
        "implementation_objects": [] if flow_b_implemented else [{
            "id": "shop-service-planned", "kind": "domain_service", "availability": "planned",
            "responsible_task_ids": [70], "expected_type": "ShopService", "lifecycle": "domain",
            "later_checks": ["type"], "target_ref": None,
        }],
        "obligations": [] if flow_b_implemented else [{
            "id": "OB-SHOP-NEW", "flow_ids": [flow_b], "requirement_ids": ["FR-70"],
            "task_ids": [70], "test_ids": ["shop-core-planned"],
            "responsibility": "shop purchase planned verification", "verification_refs": [],
        }],
    }
    _put_json(root, "docs/planning/b-route/bindings/P1.binding.v1.json", b1)
    _put_json(root, "docs/planning/b-route/bindings/P2.binding.v1.json", b2)
    _put_json(root, "docs/planning/b-route/bindings/P3.binding.v1.json", b3)
    b1_ref = _canonical_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P1.binding.v1.json", "P1")
    b2_ref = _canonical_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P2.binding.v1.json", "P2")
    b3_ref = _canonical_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P3.binding.v1.json", "P3")

    scope_heads = [
        {"scope_id": "S1", "plan_refs": [p1_ref], "binding_refs": [b1_ref]},
        {"scope_id": "S2", "plan_refs": [p2_ref], "binding_refs": [b2_ref]},
        {"scope_id": "S3", "plan_refs": [p3_ref], "binding_refs": [b3_ref]},
    ]
    task_index = [
        {"task_id": 84, "plan_refs": [p1_ref, p3_ref], "binding_refs": [b1_ref, b3_ref]},
        {"task_id": 114, "plan_refs": [p1_ref], "binding_refs": [b1_ref]},
        {"task_id": 60, "plan_refs": [p2_ref], "binding_refs": [b2_ref]},
        {"task_id": 70, "plan_refs": [p3_ref], "binding_refs": [b3_ref]},
        {"task_id": 200, "plan_refs": [p1_ref], "binding_refs": [b1_ref]},
    ]

    if include_nonflow_plan:
        nf_owned_ref = (
            _owned_ref("other_verification", nonflow_script, [(nonflow_script, (root / nonflow_script).read_bytes())])
            if nonflow_valid
            else None
        )
        p4 = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "P4", "revision": 1,
            "requirements": [{"requirement_id": "FR-NF-95", "source_block_ids": ["SB-95"], "acceptance_intent": "budget guard", "non_task_sinks": [nonflow_script]}],
            "definitions": {"flows": [], "commands": [], "states": []},
            "applicability": [{
                "requirement_id": "FR-NF-95",
                "disposition": "other_verification",
                "rationale": "Governance script check outside player gameplay journey" if nonflow_valid else "",
                "other_verification_refs": [copy.deepcopy(nf_owned_ref)] if nf_owned_ref else [],
            }],
            "requirement_verification": [{
                "requirement_id": "FR-NF-95",
                "disposition": "other_verification",
                "verification_ref": nonflow_script if nonflow_valid else "",
            }],
            "requirement_route_memberships": [],
        }
        _put_json(root, "docs/planning/b-route/plans/P4.plan.v1.json", p4)
        p4_ref = _canonical_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P4.plan.v1.json", "P4")
        b4 = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": "P4", "plan_ref": p4_ref, "binding_revision": 1, "stage": "5", "parts": [],
            "manifest_refs": [],
            "other_verification_refs": [copy.deepcopy(nf_owned_ref)] if nf_owned_ref else [],
            "task_mappings": [{"task_id": 95, "requirement_ids": ["FR-NF-95"], "flow_ids": [], "role": "producer"}],
            "contract_bindings": [], "implementation_objects": [],
            "obligations": [{
                "id": "OB-NF-95", "flow_ids": [], "requirement_ids": ["FR-NF-95"], "task_ids": [95], "test_ids": [],
                "responsibility": "Verify non-flow static budget.",
                "verification_refs": [copy.deepcopy(nf_owned_ref)] if nf_owned_ref else [],
            }],
        }
        _put_json(root, "docs/planning/b-route/bindings/P4.binding.v1.json", b4)
        b4_ref = _canonical_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P4.binding.v1.json", "P4")
        scope_heads.append({"scope_id": "S4", "plan_refs": [p4_ref], "binding_refs": [b4_ref]})
        task_index.append({"task_id": 95, "plan_refs": [p4_ref], "binding_refs": [b4_ref]})

    _put_json(root, records.CATALOG_PATH, {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": 1,
        "scope_heads": scope_heads,
        "task_index": task_index,
    })

    manifest_flows = [
        {
            "id": flow_a,
            "outcome": "Claim reward via engine input",
            "task_ids": [84, 114, 200],
            "requirement_ids": ["FR-1"],
            "source_paths": [contract_a, adapter_a, scene_a],
            "test_ids": ["reward-core", "reward-input"],
            "handoffs": [{
                "producer_task": 84,
                "consumer_task": 114,
                "owner_task": 200,
                "contract_ref": contract_a,
                "behavior": "Reward offer locks and claims via engine input",
                "test_ids": ["reward-core", "reward-input"],
            }],
        },
        {
            "id": flow_c,
            "outcome": "Advance map route",
            "task_ids": [60],
            "requirement_ids": ["FR-60"],
            "source_paths": [contract_c] + ([contract_a] if shared_test_across_ac else []),
            "test_ids": (["reward-core", "map-core"] if shared_test_across_ac else ["map-core"]),
            "handoffs": [{
                "producer_task": 60,
                "consumer_task": 60,
                "owner_task": 60,
                "contract_ref": contract_c,
                "behavior": "Map route advancement",
                "test_ids": (["reward-core", "map-core"] if shared_test_across_ac else ["map-core"]),
            }],
        },
    ]
    manifest_tests = [
        {
            "id": "reward-core",
            "kind": "dotnet",
            "state": "implemented",
            "evidence_level": "domain-integration",
            "path": core_test_a,
            "selector": "RewardTests",
            "min_tests": 1,
        },
        {
            "id": "reward-input",
            "kind": "gdunit",
            "state": "implemented",
            "evidence_level": "engine-input",
            "path": input_test_a,
            "min_tests": 1,
        },
        {
            "id": "map-core",
            "kind": "dotnet",
            "state": "implemented",
            "evidence_level": "domain-integration",
            "path": core_test_c,
            "selector": "MapRouteTests",
            "min_tests": 1,
        },
    ]
    required_flows = [flow_a, flow_c]
    blocking_tasks: list[int] = []
    if include_flow_b_in_manifest:
        required_flows.append(flow_b)
        if not flow_b_implemented:
            blocking_tasks.append(70)
        manifest_flows.append({
            "id": flow_b,
            "outcome": "Shop purchase completes cleanly",
            "status": "implemented" if flow_b_implemented else "planned",
            "task_ids": [70, 84],
            "requirement_ids": ["FR-70"],
            "source_paths": [contract_b, contract_a],
            "test_ids": ["shop-core"] if flow_b_implemented else [],
            "handoffs": [{
                "producer_task": 70,
                "consumer_task": 84,
                "owner_task": 70,
                "contract_ref": contract_b,
                "behavior": "Shop purchase flow",
                "test_ids": ["shop-core"] if flow_b_implemented else [],
            }],
        })
        if flow_b_implemented:
            manifest_tests.append({
                "id": "shop-core",
                "kind": "dotnet",
                "state": "implemented",
                "evidence_level": "domain-integration",
                "path": core_test_b,
                "selector": "ShopTests",
                "min_tests": 1,
            })
    else:
        # Full mode requires >= 3 implemented flows; include an unrelated 3rd flow while Flow B stays planned out-of-manifest.
        required_flows.append("continue-resume-flow")
        manifest_flows.append({
            "id": "continue-resume-flow",
            "outcome": "Continue resume baseline",
            "task_ids": [60],
            "requirement_ids": ["FR-60"],
            "source_paths": [contract_c],
            "test_ids": ["map-core"],
            "handoffs": [{
                "producer_task": 60,
                "consumer_task": 60,
                "owner_task": 60,
                "contract_ref": contract_c,
                "behavior": "Continue resume baseline",
                "test_ids": ["map-core"],
            }],
        })

    _put_json(root, full_manifest, {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "m1-full",
        "coverage": {
            "mode": "full",
            "scope_id": "m1-full",
            "required_flow_ids": required_flows,
            "blocking_task_ids": blocking_tasks,
            "excluded_claims": ["Manual playtest checks require explicit signoff"],
        },
        "flows": manifest_flows,
        "tests": manifest_tests,
    })

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed flow ab repo")
    rev = _git(root, "rev-parse", "HEAD")
    return {
        "rev": rev,
        "flow_a": flow_a,
        "flow_b": flow_b,
        "flow_c": flow_c,
        "contract_a": contract_a,
        "manifest_rel": full_manifest,
        "input_test_a": input_test_a,
        "scene_a": scene_a,
        "adapter_a": adapter_a,
    }


def _seal_receipt_doc(receipt: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in receipt.items() if k not in scope_runner._VOLATILE_RECEIPT_FIELDS}
    receipt["receipt_id"] = codec.canonical_digest(body)
    return receipt


def _write_raw_trx(root: Path, run_dir_rel: str, step_id: str, selector: str, *, passed: int = 1, failed: int = 0, skipped: int = 0) -> str:
    rel = f"{run_dir_rel}/{step_id}/results.trx"
    total = passed + failed + skipped
    if total == 0:
        xml = '<TestRun><Counters total="0" passed="0" failed="0"/></TestRun>'
    else:
        outcome = "Passed" if (failed == 0 and skipped == 0) else ("Failed" if failed > 0 else "NotExecuted")
        xml = (
            f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="{outcome}"/>'
            f'<Counters total="{total}" passed="{passed}" failed="{failed}" notExecuted="{skipped}"/></TestRun>'
        )
    _put_bytes(root, rel, xml)
    return rel


def _write_raw_gdunit_xml(root: Path, run_dir_rel: str, step_id: str, suite: str, *, tests: int = 1, failures: int = 0, skipped: int = 0) -> str:
    rel = f"{run_dir_rel}/{step_id}/results.xml"
    body = ""
    if tests > 0:
        if failures > 0:
            body = f'<testcase name="test_case" classname="{suite}"><failure message="failed"/></testcase>'
        elif skipped > 0:
            body = f'<testcase name="test_case" classname="{suite}"><skipped/></testcase>'
        else:
            body = f'<testcase name="test_case" classname="{suite}"/>'
    xml = f'<testsuites><testsuite name="{suite}" tests="{tests}" failures="{failures}" errors="0" skipped="{skipped}">{body}</testsuite></testsuites>'
    _put_bytes(root, rel, xml)
    return rel


def _write_synthetic_real_receipt(
    root: Path,
    run_id: str,
    *,
    scope: dict[str, Any],
    manifest_rel: str,
    snapshot_digest: str,
    source_revision: str,
    executed_tests: list[dict[str, Any]],
    runtime_verified: bool = True,
    protocol_fixture_only: bool = False,
) -> str:
    run_dir_rel = f"logs/ci/mvg-acceptance/{run_id}"
    m_sha = manifest_sha256((root / manifest_rel).read_bytes()) if (root / manifest_rel).is_file() else None
    passed_count = sum(1 for t in executed_tests if t.get("status") == "passed")
    failed_count = sum(1 for t in executed_tests if t.get("status") != "passed")
    receipt = {
        "schema_version": scope_runner.RECEIPT_SCHEMA,
        "receipt_id": "",
        "run_id": run_id,
        "scope_id": scope["scope_id"],
        "input_set_digest": scope["input_set_digest"],
        "manifest": manifest_rel,
        "manifest_sha256": m_sha,
        "source_revision": source_revision,
        "snapshot_digest": snapshot_digest,
        "workspace_dirty": False,
        "mode": "run",
        "status": "passed" if failed_count == 0 else "failed",
        "reason_code": "ok" if failed_count == 0 else "failed",
        "reason": "ok" if failed_count == 0 else "failed",
        "automated_scope_passed": failed_count == 0,
        "runtime_verified": bool(runtime_verified) and not protocol_fixture_only and failed_count == 0,
        "execution_strategy_used": "scoped",
        "superset_executed": False,
        "selective_execution_claimed": False,
        "superset_extra_tests": [],
        "requested_tests": [t["id"] for t in executed_tests],
        "executed_tests": executed_tests,
        "not_run": [],
        "manual_obligations": list(scope.get("manual_obligations") or []),
        "out_of_scope_future_obligations": list(scope.get("out_of_scope_future") or []),
        "challenges": [],
        "evidence_tiers": scope_runner._build_evidence_tiers_summary(executed_tests, [], list(scope.get("manual_obligations") or [])),
        "static_wiring": {"applicable": True, "wiring_static_ok": True, "scenes_inspected": ["Game.Godot/Scenes/Reward.tscn"], "adapters_inspected": ["Game.Godot/Scripts/Reward/RewardOfferProvider.cs"], "findings": []},
        "stop_loss": {"triggered": False, "source": None, "signals": [], "task_ids": [], "failed_prerequisite_id": None, "skipped_test_ids": []},
        "drift": {"pre_run_valid": True, "post_run_valid": True, "drift_detected": False, "invalidated_obligations": [], "invalidated_flows": [], "replacement_scope_id": None},
        "lease": {"acquired": True, "scope_keys": [], "uses_global_writer_lock": False, "lock_conflict": False},
        "build_artifacts": {"dotnet_build": None, "godot_prewarm": None},
        "reuse_rejections": [],
        "reuse_summary": {
            "build_reuses": 0, "reused_test_count": 0, "executed_test_count": len(executed_tests),
            "rejected_reuse_count": 0, "unique_test_identities": len(executed_tests),
            "requirement_routes_covered": [], "isolation_checked": True, "pollution_detected": False,
        },
        "environment": {
            "protocol_fixture_only": protocol_fixture_only,
            "evidence_role": "workflow_adapter_protocol_only" if protocol_fixture_only else "real_engine_runtime",
            "godot_bin": "godot.exe", "dotnet_bin": "dotnet.exe",
        },
        "counts": {"requested": len(executed_tests), "executed": len(executed_tests), "passed": passed_count, "failed": failed_count, "not_run": 0, "skipped": 0},
        "observed_active_elapsed_seconds": 0.5,
        "reserved_dispatches": len(executed_tests),
        "observed_dispatches": len(executed_tests),
        "generated_at": "2026-11-26T00:00:00Z",
        "finished_at": "2026-11-26T00:00:01Z",
    }
    _seal_receipt_doc(receipt)
    _put_json(root, f"{run_dir_rel}/input-manifest.json", {
        "mode": "main", "source_revision": source_revision, "snapshot_digest": snapshot_digest, "files": {},
    })
    rel = f"{run_dir_rel}/coverage-receipt.json"
    _put_json(root, rel, receipt)
    return rel


def _write_verified_ch7_report(root: Path, rel: str, flow_id: str, input_set_digest: str, meta: dict[str, Any]) -> str:
    _put_json(root, rel, {
        "schema_version": ch7_slice.SCHEMA,
        "ok": True,
        "target_flow_id": flow_id,
        "input_set_digest": input_set_digest,
        "ui_applicability": "applicable",
        "wiring_inspection": {
            "wiring_static_ok": True,
            "scenes_inspected": [meta["scene_a"]],
            "adapters_inspected": [meta["adapter_a"]],
            "findings": [],
        },
        "governed_gap_routing": [],
        "verified_items": [{"id": "ui-reward-claim"}],
        "pending_items": [],
        "blocked_items": [],
        "manual_items": [],
    })
    return rel


def _verify_integration_owner_and_nonflow_verdicts(ws: Path, source_root: Path) -> dict[str, bool]:
    # Positive: dedicated integration_only_owner (Task 200 in-progress) + valid manual signoff + Ch7 report -> Flow A verdict PASSES
    pos_dir = ws / "pos"
    pos_dir.mkdir(parents=True, exist_ok=True)
    meta_pos = _seed_flow_ab_git_repo(pos_dir, source_root, flow_b_implemented=True, include_nonflow_plan=True, nonflow_valid=True, owner200_is_integration_owner=True)
    sc_pos = verification_scope.build_verification_scope(
        pos_dir,
        change_roots=[{"kind": "contract", "id": meta_pos["contract_a"]}],
        in_scope_flow_ids=[meta_pos["flow_a"]],
        manifest_paths=[meta_pos["manifest_rel"]],
    )
    sc_pos_rel = "logs/ci/2026-11-26/e2e/scope-pos.json"
    _put_json(pos_dir, sc_pos_rel, sc_pos)
    snap_dg = "sha256:" + "a" * 64
    run_id = "run-intowner-pos"
    trx_rel = _write_raw_trx(pos_dir, f"logs/ci/mvg-acceptance/{run_id}", "reward-core", "RewardTests")
    xml_rel = _write_raw_gdunit_xml(pos_dir, f"logs/ci/mvg-acceptance/{run_id}", "reward-input", "test_reward_input_journey")
    rcpt_rel = _write_synthetic_real_receipt(
        pos_dir, run_id, scope=sc_pos, manifest_rel=meta_pos["manifest_rel"],
        snapshot_digest=snap_dg, source_revision=meta_pos["rev"],
        executed_tests=[
            {
                "id": "reward-core", "kind": "dotnet", "selector": "RewardTests", "status": "passed",
                "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                "flows": [meta_pos["flow_a"]], "report_paths": [trx_rel], "raw_report": trx_rel,
                "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                "executed_at": "2026-11-26T00:00:00Z",
            },
            {
                "id": "reward-input", "kind": "gdunit", "path": meta_pos["input_test_a"], "status": "passed",
                "evidence_level": "engine-input", "evidence_tier": "engine-input", "evidence_authenticity": "real_runtime",
                "flows": [meta_pos["flow_a"]], "report_paths": [xml_rel], "raw_report": xml_rel,
                "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                "input_authentic": True,
                "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True, "reason": "verified_real_input"},
                "executed_at": "2026-11-26T00:00:00Z",
            },
        ],
    )
    ch7_pos_rel = _write_verified_ch7_report(pos_dir, "logs/ci/2026-11-26/e2e/ch7-pos.json", meta_pos["flow_a"], sc_pos["input_set_digest"], meta_pos)
    manual_rel = "logs/ci/2026-11-26/e2e/manual-signoff.json"
    pos_manual_ids = [
        m["manual_id"]
        for m in ((sc_pos.get("execution_plan") or {}).get("manual_obligations") or [])
        if isinstance(m, dict) and m.get("manual_id")
    ]
    _put_json(pos_dir, manual_rel, {
        "schema_version": completion_verdict.MANUAL_SIGNOFF_SCHEMA,
        "scope_id": sc_pos["scope_id"],
        "snapshot_digest": snap_dg,
        "reviewer": "human-qa-windows",
        "entries": [
            {"manual_id": mid, "status": "approved", "notes": "Confirmed reward claim animation, layout, and controller input feel on Windows build.", "signed_at": "2026-11-26T00:05:00Z"}
            for mid in pos_manual_ids
        ],
    })
    v_io_pos = completion_verdict.evaluate_completion_verdict(
        pos_dir,
        level="flow",
        flow_id=meta_pos["flow_a"],
        manifest_path=meta_pos["manifest_rel"],
        verification_scope_path=sc_pos_rel,
        receipt_paths=[rcpt_rel],
        chapter7_slice_report=ch7_pos_rel,
        manual_signoff_path=manual_rel,
    )
    # Legal non-flow positive verdict (pure non-Flow without MVG flows in scope + sealed non-fixture receipt)
    sc_nf_pos = verification_scope.build_verification_scope(
        pos_dir,
        change_roots=["requirement:FR-NF-95"],
        in_scope_plan_ids=["P4"],
    )
    sc_nf_pos_rel = "logs/ci/2026-11-26/e2e/scope-nf-pos.json"
    _put_json(pos_dir, sc_nf_pos_rel, sc_nf_pos)
    ov_log = "logs/ci/mvg-acceptance/run-nf-pos/other-ov/console.log"
    _put_bytes(pos_dir, ov_log, "nonflow ok\n")
    ov_oids = [
        o["obligation_id"]
        for o in (sc_nf_pos.get("obligations") or [])
        if o.get("execution_kind") == "other_verification" or o.get("evidence_level") == "other-verification"
    ]
    rcpt_nf_pos = _write_synthetic_real_receipt(
        pos_dir, "run-nf-pos", scope=sc_nf_pos, manifest_rel=meta_pos["manifest_rel"],
        snapshot_digest=snap_dg, source_revision=meta_pos["rev"],
        runtime_verified=False, protocol_fixture_only=False,
        executed_tests=[{
            "id": "scripts/python/verify_nonflow_budget.py",
            "obligation_id": ov_oids[0] if ov_oids else "OB-NF-95",
            "obligation_ids": ov_oids,
            "kind": "other_verification",
            "evidence_level": "other-verification",
            "evidence_authenticity": "real_runtime",
            "status": "passed",
            "exit_code": 0,
            "passed_cases": 1,
            "failed_cases": 0,
            "skipped_cases": 0,
            "log_path": ov_log,
            "script_path": "scripts/python/verify_nonflow_budget.py",
        }],
    )
    v_nf_pos = completion_verdict.evaluate_completion_verdict(
        pos_dir,
        level="non_flow",
        task_id=95,
        verification_scope_path=sc_nf_pos_rel,
        receipt_paths=[rcpt_nf_pos],
    )

    # Negative: Task 200 is a regular producer (not integration_only_owner) while still in-progress -> Flow A verdict BLOCKS!
    neg_dir = ws / "neg"
    neg_dir.mkdir(parents=True, exist_ok=True)
    meta_neg = _seed_flow_ab_git_repo(neg_dir, source_root, flow_b_implemented=True, include_nonflow_plan=True, nonflow_valid=False, owner200_is_integration_owner=False)
    sc_neg = verification_scope.build_verification_scope(
        neg_dir,
        change_roots=[{"kind": "contract", "id": meta_neg["contract_a"]}],
        in_scope_flow_ids=[meta_neg["flow_a"]],
        manifest_paths=[meta_neg["manifest_rel"]],
    )
    sc_neg_rel = "logs/ci/2026-11-26/e2e/scope-neg.json"
    _put_json(neg_dir, sc_neg_rel, sc_neg)
    run_id_n = "run-intowner-neg"
    trx_n = _write_raw_trx(neg_dir, f"logs/ci/mvg-acceptance/{run_id_n}", "reward-core", "RewardTests")
    xml_n = _write_raw_gdunit_xml(neg_dir, f"logs/ci/mvg-acceptance/{run_id_n}", "reward-input", "test_reward_input_journey")
    rcpt_n = _write_synthetic_real_receipt(
        neg_dir, run_id_n, scope=sc_neg, manifest_rel=meta_neg["manifest_rel"],
        snapshot_digest=snap_dg, source_revision=meta_neg["rev"],
        executed_tests=[
            {
                "id": "reward-core", "kind": "dotnet", "selector": "RewardTests", "status": "passed",
                "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                "flows": [meta_neg["flow_a"]], "report_paths": [trx_n], "raw_report": trx_n,
                "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                "executed_at": "2026-11-26T00:00:00Z",
            },
            {
                "id": "reward-input", "kind": "gdunit", "path": meta_neg["input_test_a"], "status": "passed",
                "evidence_level": "engine-input", "evidence_tier": "engine-input", "evidence_authenticity": "real_runtime",
                "flows": [meta_neg["flow_a"]], "report_paths": [xml_n], "raw_report": xml_n,
                "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                "input_authentic": True,
                "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True, "reason": "verified_real_input"},
                "executed_at": "2026-11-26T00:00:00Z",
            },
        ],
    )
    ch7_neg_rel = _write_verified_ch7_report(neg_dir, "logs/ci/2026-11-26/e2e/ch7-neg.json", meta_neg["flow_a"], sc_neg["input_set_digest"], meta_neg)
    manual_n = "logs/ci/2026-11-26/e2e/manual-signoff-neg.json"
    neg_manual_ids = [
        m["manual_id"]
        for m in ((sc_neg.get("execution_plan") or {}).get("manual_obligations") or [])
        if isinstance(m, dict) and m.get("manual_id")
    ]
    _put_json(neg_dir, manual_n, {
        "schema_version": completion_verdict.MANUAL_SIGNOFF_SCHEMA,
        "scope_id": sc_neg["scope_id"],
        "snapshot_digest": snap_dg,
        "reviewer": "human-qa-windows",
        "entries": [
            {"manual_id": mid, "status": "approved", "notes": "Confirmed reward claim animation, layout, and controller input feel on Windows build.", "signed_at": "2026-11-26T00:05:00Z"}
            for mid in neg_manual_ids
        ],
    })
    v_io_neg = completion_verdict.evaluate_completion_verdict(
        neg_dir,
        level="flow",
        flow_id=meta_neg["flow_a"],
        manifest_path=meta_neg["manifest_rel"],
        verification_scope_path=sc_neg_rel,
        receipt_paths=[rcpt_n],
        chapter7_slice_report=ch7_neg_rel,
        manual_signoff_path=manual_n,
    )
    sc_nf_neg = verification_scope.build_verification_scope(
        neg_dir,
        change_roots=[{"kind": "plan", "id": "P4"}],
        in_scope_plan_ids=["P4"],
        manifest_paths=[meta_neg["manifest_rel"]],
    )
    sc_nf_neg_rel = "logs/ci/2026-11-26/e2e/scope-nf-neg.json"
    _put_json(neg_dir, sc_nf_neg_rel, sc_nf_neg)
    v_nf_neg = completion_verdict.evaluate_completion_verdict(
        neg_dir,
        level="non_flow",
        task_id=95,
        verification_scope_path=sc_nf_neg_rel,
    )
    return {
        "integration_owner_pos_ok": bool(v_io_pos.get("ok")),
        "integration_owner_neg_blocked": not v_io_neg.get("ok"),
        "nonflow_verdict_pos_ok": bool(v_nf_pos.get("ok")),
        "nonflow_verdict_neg_blocked": not v_nf_neg.get("ok"),
    }


# ---------------------------------------------------------------------------
# AC-3: Shared Change Affecting Flow A (implemented) + Out-of-Scope Flow B -> Flow B Moved In-Scope
# ---------------------------------------------------------------------------

def _write_protocol_fixture_wrappers(ws: Path) -> tuple[str, str]:
    script_path = ws / "_e2e_protocol_runner.py"
    script_path.write_text(_PROTOCOL_FIXTURE_RUNNER_CODE, encoding="utf-8")
    if os.name == "nt":
        dotnet_cmd = ws / "_e2e_dotnet.cmd"
        godot_cmd = ws / "_e2e_godot.cmd"
        body = f'@echo off\r\n"{sys.executable}" -B "{script_path}" %*\r\n'
        dotnet_cmd.write_text(body, encoding="utf-8")
        godot_cmd.write_text(body, encoding="utf-8")
        return str(dotnet_cmd), str(godot_cmd)
    sh = ws / "_e2e_runner.sh"
    sh.write_text(f'#!/usr/bin/env sh\nexec "{sys.executable}" -B "{script_path}" "$@"\n', encoding="utf-8")
    sh.chmod(0o755)
    return str(sh), str(sh)


def _run_ac3_shared_change_flow_ab_evolution_matrix(source_root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    with _temp_workspace("nr410-ac3-") as ws:
        meta = _seed_flow_ab_git_repo(ws, source_root, flow_b_implemented=False, include_flow_b_in_manifest=False)
        dotnet_bin, godot_bin = _write_protocol_fixture_wrappers(ws)
        flow_a = meta["flow_a"]
        flow_b = meta["flow_b"]
        manifest_rel = meta["manifest_rel"]

        # Step 1 (4.1): Compute transitive impact closure on shared contract
        imp = impact_closure.compute_impact_closure(
            ws,
            change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
            manifest_paths=[manifest_rel],
        )
        impacted_flows = sorted(
            f["entity_id"] if isinstance(f, dict) else str(f)
            for f in (imp.get("impacted_flows") or [])
        )
        both_ab_impacted = bool(imp.get("ok")) and (flow_a in impacted_flows) and (flow_b in impacted_flows)

        # Step 2 (4.2 Phase 1): Build VerificationScope with ONLY Flow A in scope; Flow B is out_of_scope_future
        sc_p1 = verification_scope.build_verification_scope(
            ws,
            impact_proof=imp,
            in_scope_flow_ids=[flow_a],
            manifest_paths=[manifest_rel],
        )
        sc_p1_rel = "logs/ci/2026-11-26/e2e/scope-phase1.json"
        _put_json(ws, sc_p1_rel, sc_p1)
        p1_obls = sc_p1.get("obligations") or []
        p1_existing = {fid for o in p1_obls if o.get("tier") == "existing_required" for fid in (o.get("flow_ids") or [])}
        p1_future = {fid for o in p1_obls if o.get("tier") == "out_of_scope_future" for fid in (o.get("flow_ids") or [])}
        p1_buckets_ok = bool(sc_p1.get("ok")) and (flow_a in p1_existing) and (flow_b in p1_future)

        # Step 3a (4.3 + 4.5 Phase 1 - Flow A RUNNER LAUNCH FAILURE before test execution):
        rc_launch, _, rcpt_launch = scope_runner.run_scoped_mvg(
            root=ws,
            out=ws / "logs/ci/mvg-acceptance/ac3-launch-fail-a",
            run_id="ac3-launch-fail-a",
            verification_scope_arg=sc_p1_rel,
            manifest_arg=manifest_rel,
            mode="run",
            snapshot_mode="worktree",
            revision_arg="HEAD",
            base_arg="HEAD",
            godot_bin=godot_bin,
            dotnet_bin=str(ws / "_nonexistent_dotnet_runner.cmd"),
            timeout_sec=30,
            challenge_input=False,
            protocol_fixture=True,
        )
        verdict_launch_a = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=manifest_rel,
            verification_scope_path=sc_p1_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac3-launch-fail-a/coverage-receipt.json"],
        )
        flow_a_launch_failure_blocked = (
            rc_launch != 0
            and (not rcpt_launch.get("automated_scope_passed"))
            and (not rcpt_launch.get("runtime_verified"))
            and (not verdict_launch_a.get("ok"))
        )

        # Step 3b (4.3 + 4.5 Phase 1 - Flow A TEST FAILURE):
        old_fail_sel = os.environ.get("E2E_FIXTURE_FAIL_SELECTOR")
        os.environ["E2E_FIXTURE_FAIL_SELECTOR"] = "RewardTests"
        try:
            rc_fail, _, rcpt_fail = scope_runner.run_scoped_mvg(
                root=ws,
                out=ws / "logs/ci/mvg-acceptance/ac3-fail-a",
                run_id="ac3-fail-a",
                verification_scope_arg=sc_p1_rel,
                manifest_arg=manifest_rel,
                mode="run",
                snapshot_mode="worktree",
                revision_arg="HEAD",
                base_arg="HEAD",
                godot_bin=godot_bin,
                dotnet_bin=dotnet_bin,
                timeout_sec=60,
                challenge_input=False,
                protocol_fixture=True,
            )
        finally:
            if old_fail_sel is None:
                os.environ.pop("E2E_FIXTURE_FAIL_SELECTOR", None)
            else:
                os.environ["E2E_FIXTURE_FAIL_SELECTOR"] = old_fail_sel

        verdict_fail_a = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=manifest_rel,
            verification_scope_path=sc_p1_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac3-fail-a/coverage-receipt.json"],
        )
        flow_a_failure_blocked = (
            flow_a_launch_failure_blocked
            and rc_fail != 0
            and (not rcpt_fail.get("automated_scope_passed"))
            and (not rcpt_fail.get("runtime_verified"))
            and (not verdict_fail_a.get("ok"))
        )

        # Step 4 (Phase 1 - Flow A FIXED while Flow B stays out_of_scope_future):
        rc_pass_a, _, rcpt_pass_a = scope_runner.run_scoped_mvg(
            root=ws,
            out=ws / "logs/ci/mvg-acceptance/ac3-pass-a",
            run_id="ac3-pass-a",
            verification_scope_arg=sc_p1_rel,
            manifest_arg=manifest_rel,
            mode="run",
            snapshot_mode="worktree",
            revision_arg="HEAD",
            base_arg="HEAD",
            godot_bin=godot_bin,
            dotnet_bin=dotnet_bin,
            timeout_sec=60,
            challenge_input=False,
            protocol_fixture=True,
        )
        verdict_p1_b = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_b,
            manifest_path=manifest_rel,
            verification_scope_path=sc_p1_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac3-pass-a/coverage-receipt.json"],
        )
        executed_ids_p1 = {t["id"] for t in (rcpt_pass_a.get("executed_tests") or []) if not str(t.get("id") or "").startswith("static-wiring:")}
        declared_ids_p1 = {
            tid
            for o in p1_obls
            if o.get("tier") in ("existing_required", "current_new")
            for tid in (o.get("test_ids") or [])
        }
        future_preserved_in_receipt = any(
            flow_b in (o.get("flow_ids") or [])
            for o in (rcpt_pass_a.get("out_of_scope_future_obligations") or [])
        )
        phase1_b_verdict_future = (
            (not verdict_p1_b.get("ok"))
            and verdict_p1_b.get("verdict_status") == "out_of_scope_future"
            and flow_b in (verdict_p1_b.get("out_of_scope_future_tracked") or [])
        )
        phase1_fixed_ok = (
            rc_pass_a == 0
            and bool(rcpt_pass_a.get("automated_scope_passed"))
            and (rcpt_pass_a.get("runtime_verified") is False)
            and (rcpt_pass_a.get("environment", {}).get("protocol_fixture_only") is True)
            and (rcpt_pass_a.get("environment", {}).get("evidence_authenticity") == "protocol_fixture")
            and bool(executed_ids_p1)
            and (executed_ids_p1 == declared_ids_p1)
            and future_preserved_in_receipt
            and phase1_b_verdict_future
        )

        # Anti-evasion 1: Reclassify failing Flow A to "planned" -> REJECTED!
        m_doc = _read_json(ws, manifest_rel)
        m_reclass = copy.deepcopy(m_doc)
        for fl in m_reclass["flows"]:
            if fl["id"] == flow_a:
                fl["status"] = "planned"
        reclass_rel = "docs/testing/mvg/m1-reclass-bad.json"
        _put_json(ws, reclass_rel, m_reclass)
        sc_reclass = verification_scope.build_verification_scope(
            ws,
            change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
            in_scope_flow_ids=[flow_a],
            manifest_paths=[reclass_rel],
            cumulative_baseline_manifests=[manifest_rel],
        )
        reclass_rejected = not sc_reclass.get("ok")

        # Anti-evasion 2: Swap an older manifest missing Flow A against the PASSING receipt & scope builder -> REJECTED!
        m_older = copy.deepcopy(m_doc)
        m_older["flows"] = [fl for fl in m_older["flows"] if fl["id"] != flow_a]
        m_older["coverage"]["required_flow_ids"] = [fid for fid in m_older["coverage"]["required_flow_ids"] if fid != flow_a]
        m_older["tests"] = [t for t in m_older["tests"] if t["id"] not in ("reward-core", "reward-input")]
        older_rel = "docs/testing/mvg/m0-older-missing-a.json"
        _put_json(ws, older_rel, m_older)
        sc_older = verification_scope.build_verification_scope(
            ws,
            change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
            in_scope_flow_ids=[flow_a],
            manifest_paths=[older_rel],
            cumulative_baseline_manifests=[manifest_rel],
        )
        verdict_older_manifest = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=older_rel,
            verification_scope_path=sc_p1_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac3-pass-a/coverage-receipt.json"],
        )
        older_manifest_rejected = (not sc_older.get("ok")) and (not verdict_older_manifest.get("ok"))
        (ws / reclass_rel).unlink()
        (ws / older_rel).unlink()

        # Step 5 (Phase 2 - Flow B moved into current delivery boundary while still incomplete/untested):
        sc_p2 = verification_scope.build_verification_scope(
            ws,
            impact_proof=imp,
            in_scope_flow_ids=[flow_a, flow_b],
            manifest_paths=[manifest_rel],
        )
        sc_p2_rel = "logs/ci/2026-11-26/e2e/scope-phase2.json"
        _put_json(ws, sc_p2_rel, sc_p2)
        p2_obls = sc_p2.get("obligations") or []
        p2_current_new = {fid for o in p2_obls if o.get("tier") == "current_new" for fid in (o.get("flow_ids") or [])}
        p2_future = {fid for o in p2_obls if o.get("tier") == "out_of_scope_future" for fid in (o.get("flow_ids") or [])}
        flow_b_moved_to_current_new = bool(sc_p2.get("ok")) and (flow_b in p2_current_new) and (flow_b not in p2_future)

        rc_p2, _, rcpt_p2 = scope_runner.run_scoped_mvg(
            root=ws,
            out=ws / "logs/ci/mvg-acceptance/ac3-phase2-b-unready",
            run_id="ac3-phase2-b-unready",
            verification_scope_arg=sc_p2_rel,
            manifest_arg=manifest_rel,
            mode="run",
            snapshot_mode="worktree",
            revision_arg="HEAD",
            base_arg="HEAD",
            godot_bin=godot_bin,
            dotnet_bin=dotnet_bin,
            timeout_sec=60,
            challenge_input=False,
            protocol_fixture=True,
        )
        verdict_p2_b = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_b,
            manifest_path=manifest_rel,
            verification_scope_path=sc_p2_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac3-phase2-b-unready/coverage-receipt.json"],
        )
        p2_not_run = rcpt_p2.get("not_run") or []
        p2_b_in_not_run_or_missing = any(
            flow_b in (item.get("flow_ids") or []) or flow_b in str(item.get("obligation_id") or "") or flow_b in str(item.get("id") or "")
            for item in p2_not_run
            if isinstance(item, dict)
        ) or bool((verdict_p2_b.get("missing_flow_obligations") or {}).get("missing_implementations"))
        phase2_b_blocked_until_implemented = (
            flow_b_moved_to_current_new
            and (rc_p2 != 0)
            and (rcpt_p2.get("scope_id") == sc_p2.get("scope_id"))
            and (not rcpt_p2.get("automated_scope_passed"))
            and (not rcpt_p2.get("runtime_verified"))
            and p2_b_in_not_run_or_missing
            and (not verdict_p2_b.get("ok"))
        )

    checks = {
        "both_flow_a_and_flow_b_impacted": both_ab_impacted,
        "phase1_buckets_existing_a_and_future_b": p1_buckets_ok,
        "phase1_flow_a_launch_failure_blocked": flow_a_launch_failure_blocked,
        "phase1_flow_a_failure_blocks_runner_and_verdict": flow_a_failure_blocked,
        "failed_flow_reclassification_to_planned_rejected": reclass_rejected,
        "older_manifest_hiding_flow_a_rejected": older_manifest_rejected,
        "phase1_flow_a_fixed_passes_protocol_while_b_stays_future": phase1_fixed_ok,
        "phase2_flow_b_moves_to_current_new": flow_b_moved_to_current_new,
        "phase2_incomplete_flow_b_blocks_completion": phase2_b_blocked_until_implemented,
    }
    all_ok = all(checks.values())
    if not all_ok:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "ac3_flow_ab_evolution",
            "all Phase 1 and Phase 2 Flow A/B evolution checks pass",
            checks,
            None,
        ))
    return {
        "ok": all_ok,
        "status": "passed" if all_ok else "blocked",
        "checks": checks,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# AC-4: Multi-Flow Shared Test Reuse, Isolation, Cross-Snapshot & Fake-Evidence Rejections
# ---------------------------------------------------------------------------

def _run_ac4_shared_evidence_and_authenticity_matrix(source_root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    with _temp_workspace("nr410-ac4-") as ws:
        meta = _seed_flow_ab_git_repo(ws, source_root, flow_b_implemented=True, include_flow_b_in_manifest=True, shared_test_across_ac=True)
        dotnet_bin, godot_bin = _write_protocol_fixture_wrappers(ws)
        flow_a = meta["flow_a"]
        flow_c = meta["flow_c"]
        manifest_rel = meta["manifest_rel"]

        sc_ac = verification_scope.build_verification_scope(
            ws,
            change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
            in_scope_flow_ids=[flow_a, flow_c],
            manifest_paths=[manifest_rel],
        )
        sc_ac_rel = "logs/ci/2026-11-26/e2e/scope-ac.json"
        _put_json(ws, sc_ac_rel, sc_ac)

        inv_log_path = ws / "logs/ci/2026-11-26/e2e/invocations.jsonl"
        old_env = {k: os.environ.get(k) for k in ("E2E_FIXTURE_INVOCATIONS", "E2E_FIXTURE_ASSERT_CLEAN", "E2E_FIXTURE_EMIT_EMPTY", "E2E_FIXTURE_EMIT_SKIPPED")}
        os.environ["E2E_FIXTURE_INVOCATIONS"] = str(inv_log_path)
        os.environ["E2E_FIXTURE_ASSERT_CLEAN"] = "1"
        os.environ.pop("E2E_FIXTURE_EMIT_EMPTY", None)
        os.environ.pop("E2E_FIXTURE_EMIT_SKIPPED", None)
        try:
            # Run 1: Shared test (reward-core) referenced by BOTH Flow A and Flow C executes ONCE with isolated dirs!
            rc1, _, rcpt1 = scope_runner.run_scoped_mvg(
                root=ws,
                out=ws / "logs/ci/mvg-acceptance/ac4-run1",
                run_id="ac4-run1",
                verification_scope_arg=sc_ac_rel,
                manifest_arg=manifest_rel,
                mode="run",
                snapshot_mode="worktree",
                revision_arg="HEAD",
                base_arg="HEAD",
                godot_bin=godot_bin,
                dotnet_bin=dotnet_bin,
                timeout_sec=60,
                challenge_input=False,
                protocol_fixture=True,
            )
            calls_run1 = [
                codec.strict_json_loads(line.encode("utf-8"))
                for line in inv_log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ] if inv_log_path.is_file() else []
            reward_core_calls_r1 = [c for c in calls_run1 if c.get("kind") == "dotnet" and c.get("selector") == "RewardTests"]
            isolation_zero_leak = bool(calls_run1) and all(c.get("leaked") is False for c in calls_run1)
            distinct_isolated_dirs = len({c.get("appdata") for c in calls_run1}) == len(calls_run1)
            shared_executed_once = rc1 == 0 and len(reward_core_calls_r1) == 1 and not rcpt1.get("reuse_summary", {}).get("pollution_detected")
            r1_ts_by_id = {
                t["id"]: (t.get("original_executed_at") or t.get("executed_at"))
                for t in (rcpt1.get("executed_tests") or [])
            }

            # Run 2 on SAME snapshot with --reuse-evidence-from Run 1 -> zero redundant execution + original_executed_at preserved!
            inv_log_path.unlink(missing_ok=True)
            rc2, _, rcpt2 = scope_runner.run_scoped_mvg(
                root=ws,
                out=ws / "logs/ci/mvg-acceptance/ac4-run2-reuse",
                run_id="ac4-run2-reuse",
                verification_scope_arg=sc_ac_rel,
                manifest_arg=manifest_rel,
                mode="run",
                snapshot_mode="worktree",
                revision_arg="HEAD",
                base_arg="HEAD",
                godot_bin=godot_bin,
                dotnet_bin=dotnet_bin,
                timeout_sec=60,
                challenge_input=False,
                protocol_fixture=True,
                reuse_evidence_from=["logs/ci/mvg-acceptance/ac4-run1/coverage-receipt.json"],
            )
            calls_run2 = [
                codec.strict_json_loads(line.encode("utf-8"))
                for line in inv_log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ] if inv_log_path.is_file() else []
            reused_entries = [t for t in (rcpt2.get("executed_tests") or []) if t.get("reused")]
            non_static_r1 = [t for t in (rcpt1.get("executed_tests") or []) if not str(t.get("id") or "").startswith("static-wiring:")]
            same_snapshot_reuse_ok = (
                rc2 == 0
                and len(calls_run2) == 0
                and len(reused_entries) == len(non_static_r1)
                and all(t.get("original_executed_at") == r1_ts_by_id.get(t["id"]) for t in reused_entries)
            )

            # Empty report (total=0) -> REJECTED!
            os.environ["E2E_FIXTURE_EMIT_EMPTY"] = "1"
            rc_empty, _, rcpt_empty = scope_runner.run_scoped_mvg(
                root=ws,
                out=ws / "logs/ci/mvg-acceptance/ac4-empty",
                run_id="ac4-empty",
                verification_scope_arg=sc_ac_rel,
                manifest_arg=manifest_rel,
                mode="run",
                snapshot_mode="worktree",
                revision_arg="HEAD",
                base_arg="HEAD",
                godot_bin=godot_bin,
                dotnet_bin=dotnet_bin,
                timeout_sec=60,
                challenge_input=False,
                protocol_fixture=True,
            )
            os.environ.pop("E2E_FIXTURE_EMIT_EMPTY", None)
            empty_report_rejected = rc_empty != 0 and (not rcpt_empty.get("automated_scope_passed"))

            # Skipped test (skipped=1) -> REJECTED!
            os.environ["E2E_FIXTURE_EMIT_SKIPPED"] = "1"
            rc_skip, _, rcpt_skip = scope_runner.run_scoped_mvg(
                root=ws,
                out=ws / "logs/ci/mvg-acceptance/ac4-skipped",
                run_id="ac4-skipped",
                verification_scope_arg=sc_ac_rel,
                manifest_arg=manifest_rel,
                mode="run",
                snapshot_mode="worktree",
                revision_arg="HEAD",
                base_arg="HEAD",
                godot_bin=godot_bin,
                dotnet_bin=dotnet_bin,
                timeout_sec=60,
                challenge_input=False,
                protocol_fixture=True,
            )
            os.environ.pop("E2E_FIXTURE_EMIT_SKIPPED", None)
            skipped_report_rejected = rc_skip != 0 and (not rcpt_skip.get("automated_scope_passed"))
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        # Input authenticity negative checks: method call without InputEvent & ForTest backdoor -> REJECTED!
        _put_bytes(ws, "Tests.Godot/tests/Integration/Mvg/test_fake_method_only.gd",
                   "extends GdUnitTestSuite\nfunc test_fake():\n    var p = load('res://Game.Godot/Scenes/Reward.tscn').instantiate()\n    p.OnClaimPressed()\n")
        _put_bytes(ws, "Tests.Godot/tests/Integration/Mvg/test_fortest_backdoor.gd",
                   "extends GdUnitTestSuite\nfunc test_backdoor():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n    panel.SetRewardForTest(1)\n")
        auth_method = scope_runner.inspect_gdunit_input_authenticity(ws, "Tests.Godot/tests/Integration/Mvg/test_fake_method_only.gd", "engine-input")
        auth_fortest = scope_runner.inspect_gdunit_input_authenticity(ws, "Tests.Godot/tests/Integration/Mvg/test_fortest_backdoor.gd", "engine-input")
        scene_method_without_input_rejected = not auth_method.get("valid")
        fortest_backdoor_rejected = not auth_fortest.get("valid")

        # Cross-snapshot splicing rejection in cumulative milestone (full-MVG) verdict!
        sc_full = verification_scope.build_verification_scope(
            ws,
            change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
            in_scope_flow_ids=[flow_a, flow_c, meta["flow_b"]],
            manifest_paths=[manifest_rel],
        )
        sc_full_rel = "logs/ci/2026-11-26/e2e/scope-full.json"
        _put_json(ws, sc_full_rel, sc_full)
        trx1 = _write_raw_trx(ws, "logs/ci/mvg-acceptance/snap1", "reward-core", "RewardTests")
        xml1 = _write_raw_gdunit_xml(ws, "logs/ci/mvg-acceptance/snap1", "reward-input", "test_reward_input_journey")
        rcpt_s1 = _write_synthetic_real_receipt(
            ws, "snap1", scope=sc_full, manifest_rel=manifest_rel,
            snapshot_digest="sha256:" + "1" * 64, source_revision=meta["rev"],
            executed_tests=[
                {
                    "id": "reward-core", "kind": "dotnet", "selector": "RewardTests", "status": "passed",
                    "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                    "flows": [flow_a, flow_c], "report_paths": [trx1], "raw_report": trx1,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                    "executed_at": "2026-11-26T00:00:00Z",
                },
                {
                    "id": "reward-input", "kind": "gdunit", "path": meta["input_test_a"], "status": "passed",
                    "evidence_level": "engine-input", "evidence_tier": "engine-input", "evidence_authenticity": "real_runtime",
                    "flows": [flow_a], "report_paths": [xml1], "raw_report": xml1,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authentic": True,
                    "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True, "reason": "verified_real_input"},
                    "executed_at": "2026-11-26T00:00:00Z",
                },
            ],
        )
        # Non-vacuous missing-manual check on the valid same-snapshot passing Flow A setup (BEFORE second commit!)
        ch7_ac4_rel = _write_verified_ch7_report(ws, "logs/ci/2026-11-26/e2e/ch7-ac4.json", flow_a, sc_full["input_set_digest"], meta)
        v_no_manual = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=manifest_rel,
            verification_scope_path=sc_full_rel,
            receipt_paths=[rcpt_s1],
            chapter7_slice_report=ch7_ac4_rel,
            manual_signoff_path=None,
        )
        missing_manual_signoff_rejected = (
            (v_no_manual.get("ok") is False)
            and (v_no_manual.get("automated_flow_passed") is True)
            and (v_no_manual.get("manual_pending") is True)
            and (v_no_manual.get("verdict_status") == "manual_pending")
        )

        # Protocol fixture receipt AND fake scene-method/ForTest receipt supplied to completion_verdict -> MUST fail!
        ch7_ac4_ac_rel = _write_verified_ch7_report(ws, "logs/ci/2026-11-26/e2e/ch7-ac4-ac.json", flow_a, sc_ac["input_set_digest"], meta)
        v_proto_flow = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=manifest_rel,
            verification_scope_path=sc_ac_rel,
            receipt_paths=["logs/ci/mvg-acceptance/ac4-run1/coverage-receipt.json"],
            chapter7_slice_report=ch7_ac4_ac_rel,
        )
        trx_fake = _write_raw_trx(ws, "logs/ci/mvg-acceptance/snap-fake-input", "reward-core", "RewardTests")
        xml_fake = _write_raw_gdunit_xml(ws, "logs/ci/mvg-acceptance/snap-fake-input", "reward-input", "test_reward_input_journey")
        rcpt_fake_input = _write_synthetic_real_receipt(
            ws, "snap-fake-input", scope=sc_full, manifest_rel=manifest_rel,
            snapshot_digest="sha256:" + "1" * 64, source_revision=meta["rev"],
            executed_tests=[
                {
                    "id": "reward-core", "kind": "dotnet", "selector": "RewardTests", "status": "passed",
                    "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                    "flows": [flow_a, flow_c], "report_paths": [trx_fake], "raw_report": trx_fake,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                    "executed_at": "2026-11-26T00:00:00Z",
                },
                {
                    "id": "reward-input", "kind": "gdunit", "path": "Tests.Godot/tests/Integration/Mvg/test_fake_method_only.gd", "status": "passed",
                    "evidence_level": "engine-input", "evidence_tier": "engine-input", "evidence_authenticity": "real_runtime",
                    "flows": [flow_a], "report_paths": [xml_fake], "raw_report": xml_fake,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authentic": False,
                    "input_authenticity": {"checked": True, "valid": False, "player_action_input_detected": False, "reason": "direct_method_call_without_input_event"},
                    "executed_at": "2026-11-26T00:00:00Z",
                },
            ],
        )
        v_fake_input_flow = completion_verdict.evaluate_completion_verdict(
            ws,
            level="flow",
            flow_id=flow_a,
            manifest_path=manifest_rel,
            verification_scope_path=sc_full_rel,
            receipt_paths=[rcpt_fake_input],
            chapter7_slice_report=ch7_ac4_rel,
        )
        # Non-full manifest ("critical") -> verified_scope MUST be "critical" / "partial" (never "full")!
        m_crit = copy.deepcopy(_read_json(ws, manifest_rel))
        m_crit["coverage"]["mode"] = "critical"
        crit_rel = "docs/testing/mvg/m1-critical.json"
        _put_json(ws, crit_rel, m_crit)
        try:
            sc_crit = verification_scope.build_verification_scope(
                ws,
                change_roots=[{"kind": "contract", "id": meta["contract_a"]}],
                in_scope_flow_ids=[flow_a],
                manifest_paths=[crit_rel],
            )
            sc_crit_rel = "logs/ci/2026-11-26/e2e/scope-crit.json"
            _put_json(ws, sc_crit_rel, sc_crit)
            trx_crit = _write_raw_trx(ws, "logs/ci/mvg-acceptance/snap-crit", "reward-core", "RewardTests")
            xml_crit = _write_raw_gdunit_xml(ws, "logs/ci/mvg-acceptance/snap-crit", "reward-input", "test_reward_input_journey")
            rcpt_crit = _write_synthetic_real_receipt(
                ws, "snap-crit", scope=sc_crit, manifest_rel=crit_rel,
                snapshot_digest="sha256:" + "1" * 64, source_revision=meta["rev"],
                executed_tests=[
                    {
                        "id": "reward-core", "kind": "dotnet", "selector": "RewardTests", "status": "passed",
                        "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                        "flows": [flow_a, flow_c], "report_paths": [trx_crit], "raw_report": trx_crit,
                        "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                        "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                        "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                        "executed_at": "2026-11-26T00:00:00Z",
                    },
                    {
                        "id": "reward-input", "kind": "gdunit", "path": meta["input_test_a"], "status": "passed",
                        "evidence_level": "engine-input", "evidence_tier": "engine-input", "evidence_authenticity": "real_runtime",
                        "flows": [flow_a], "report_paths": [xml_crit], "raw_report": xml_crit,
                        "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                        "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                        "input_authentic": True,
                        "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True, "reason": "verified_real_input"},
                        "executed_at": "2026-11-26T00:00:00Z",
                    },
                ],
            )
            ch7_crit_rel = _write_verified_ch7_report(ws, "logs/ci/2026-11-26/e2e/ch7-crit.json", flow_a, sc_crit["input_set_digest"], meta)
            v_crit = completion_verdict.evaluate_completion_verdict(
                ws,
                level="milestone",
                manifest_path=crit_rel,
                verification_scope_path=sc_crit_rel,
                receipt_paths=[rcpt_crit],
                chapter7_slice_report=ch7_crit_rel,
            )
        finally:
            if (ws / crit_rel).exists():
                (ws / crit_rel).unlink()

        # Create a second commit so source_revision & snapshot_digest genuinely differ!
        _put_bytes(ws, "docs/gdd/rev2-note.md", "# Rev 2\n")
        _git(ws, "add", "docs/gdd/rev2-note.md")
        _git(ws, "commit", "-q", "-m", "second snapshot rev")
        rev2 = _git(ws, "rev-parse", "HEAD")
        trx2 = _write_raw_trx(ws, "logs/ci/mvg-acceptance/snap2", "map-core", "MapRouteTests")
        trx3 = _write_raw_trx(ws, "logs/ci/mvg-acceptance/snap2", "shop-core", "ShopTests")
        rcpt_s2 = _write_synthetic_real_receipt(
            ws, "snap2", scope=sc_full, manifest_rel=manifest_rel,
            snapshot_digest="sha256:" + "2" * 64, source_revision=rev2,
            executed_tests=[
                {
                    "id": "map-core", "kind": "dotnet", "selector": "MapRouteTests", "status": "passed",
                    "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                    "flows": [flow_c], "report_paths": [trx2], "raw_report": trx2,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                    "executed_at": "2026-11-26T00:02:00Z",
                },
                {
                    "id": "shop-core", "kind": "dotnet", "selector": "ShopTests", "status": "passed",
                    "evidence_level": "domain-xunit", "evidence_tier": "domain-xunit", "evidence_authenticity": "real_runtime",
                    "flows": [meta["flow_b"]], "report_paths": [trx3], "raw_report": trx3,
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                    "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                    "executed_at": "2026-11-26T00:02:00Z",
                },
            ],
        )
        v_splice = completion_verdict.evaluate_completion_verdict(
            ws,
            level="milestone",
            manifest_path=manifest_rel,
            verification_scope_path=sc_full_rel,
            receipt_paths=[rcpt_s1, rcpt_s2],
        )
        cross_snapshot_splicing_rejected = (
            (v_splice.get("ok") is False)
            and (v_splice.get("cross_snapshot_splicing_detected") is True)
        )

        # Real verified_scope labels + protocol_fixture & fake-input receipt rejection on Flow completion!
        protocol_fixture_honest = (
            rcpt1.get("runtime_verified") is False
            and rcpt1.get("environment", {}).get("protocol_fixture_only") is True
            and rcpt1.get("environment", {}).get("evidence_authenticity") == "protocol_fixture"
            and (v_proto_flow.get("ok") is False)
            and (v_fake_input_flow.get("ok") is False)
        )
        single_flow_bounded_label = (
            v_no_manual.get("level") == "flow"
            and v_no_manual.get("verified_scope") == "single_flow"
            and v_proto_flow.get("verified_scope") == "single_flow"
            and v_crit.get("verified_scope") in ("partial", "critical")
        )

    checks = {
        "shared_test_executed_once_across_flows": shared_executed_once,
        "per_test_isolated_dirs_zero_leak": isolation_zero_leak and distinct_isolated_dirs,
        "same_snapshot_reuse_preserves_original_executed_at": same_snapshot_reuse_ok,
        "cross_snapshot_splicing_rejected": cross_snapshot_splicing_rejected,
        "empty_report_rejected": empty_report_rejected,
        "skipped_test_rejected": skipped_report_rejected,
        "scene_method_without_input_event_rejected": scene_method_without_input_rejected,
        "fortest_backdoor_rejected": fortest_backdoor_rejected,
        "missing_manual_independent_signoff_rejected": missing_manual_signoff_rejected,
        "protocol_fixture_honest_runtime_verified_false": protocol_fixture_honest,
        "single_flow_bounded_scope_not_full_mvg": single_flow_bounded_label,
    }
    all_ok = all(checks.values())
    if not all_ok:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "ac4_evidence_authenticity",
            "all shared evidence reuse, isolation, cross-snapshot rejection, and authenticity checks pass",
            checks,
            None,
        ))
    return {
        "ok": all_ok,
        "status": "passed" if all_ok else "blocked",
        "checks": checks,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# AC-5: Page / Knowledge / Observability Parity, Epoch/Reopen, Zero Pointer Mutation & Non-Offsetting Metrics
# ---------------------------------------------------------------------------

def _run_ac5_page_knowledge_observability_parity_matrix(source_root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    with _temp_workspace("nr410-ac5-") as ws:
        _seed_shared_scope_repo(ws, source_root)
        # Ensure branch is named main for refs/heads/main immutability verification
        _git(ws, "branch", "-M", "main")
        _put_json(ws, "docs/workflows/chapter3-source-set.json", {
            "schema_version": "chapter3.source-set.v1",
            "active_patterns": ["docs/gdd/scope1.md"],
            "active_sources": ["docs/gdd/scope1.md"],
            "retirements": [],
        })
        # Publication pointers + committed catalog that MUST stay 100% byte-identical!
        pointer_rels = (
            "knowledge/indexes/current.json",
            "knowledge/indexes/last-known-good.json",
            "logs/ci/project-health-knowledge/latest.json",
            "logs/ci/project-health-knowledge/runtime/latest.json",
        )
        for prel in pointer_rels:
            _put_json(ws, prel, {"pointer": prel, "revision": "a" * 40})

        _git(ws, "add", "docs", "knowledge")
        _git(ws, "commit", "-q", "-m", "main baseline for ac5")
        main_sha_before = _git(ws, "rev-parse", "refs/heads/main")
        pointers_before = {p: (ws / p).read_bytes() for p in pointer_rels}
        catalog_before = (ws / records.CATALOG_PATH).read_bytes()

        # Introduce dirty workspace edit + pending operation (corrupt commit.json so commit.recover blocks cleanly)
        _put_bytes(ws, "docs/gdd/scope1.md", "# Scope 1\n\nDirty workspace preview edit.\n")
        pend_op_id = "OP-AC5-PEND"
        pend_intent_rel, pend_marker_rel = commit._paths(pend_op_id)
        _put_bytes(ws, pend_intent_rel, b'{"truncated_ac5_pending":')
        _put_json(ws, pend_marker_rel, {"operation_id": pend_op_id, "status": "pending"})
        _put_json(ws, journal.OPERATION_STORE + "/pending.json", {
            "schema_version": journal.PENDING_SCHEMA,
            "operations": [{"operation_id": pend_op_id, "state": "applying"}],
        })

        # Seed 3A audit report + mvg-recovery epoch bump + reopen revocation + fast zero-dispatch quality-floor violation
        _put_json(ws, "logs/ci/2026-11-26/b-route-source-audit/run-a/attempt-1/report.json", {
            "schema_version": "newrouge.b-route-source-audit.v1",
            "planning_eligible": True, "execution_complete": True, "independent_audit": True,
            "evidence_class": "real_model", "semantic_blockers": [], "formal_adoption": False, "diagnostics": [],
        })
        _put_json(ws, "logs/ci/mvg-recovery/registry.json", {
            "schema_version": "newrouge.mvg-completed-registry.v1",
            "epoch": 1, "entries": [], "revoked": ["tx-revoked-01"],
        })
        _put_json(ws, "logs/ci/mvg-recovery/clears/epoch-0.json", {
            "schema_version": "newrouge.mvg-completed-registry.v1",
            "epoch": 0, "cleared_at": "2026-11-26T00:00:00Z", "reason": "mvg-clear epoch bump",
        })
        _put_json(ws, "logs/ci/mvg-planning/run-epoch-old/run.json", {
            "phase": "generate", "input_stage": "3b", "recovery": {"epoch": 0},
            "planning_runtime": {"profile": "mvg_3b", "prepared_ref": "logs/ci/b-route-planning-input/r0/prepared.json"},
            "capability_selection": {"selected": [{"checkpoint": {"transaction_id": "tx-old"}}], "total": 1, "total_invocations": 1},
            "mvg": {"run_invocation_limit": 4},
            "request_budget": {"limit": 4, "used": 1},
        })
        _put_json(ws, "logs/ci/mvg-planning/run-revoked-01/run.json", {
            "phase": "generate", "input_stage": "3b", "recovery": {"epoch": 1},
            "planning_runtime": {"profile": "mvg_3b", "prepared_ref": "logs/ci/b-route-planning-input/r0/prepared.json"},
            "capability_selection": {"selected": [{"checkpoint": {"transaction_id": "tx-revoked-01"}}], "total": 1, "total_invocations": 1},
            "mvg": {"run_invocation_limit": 4},
            "request_budget": {"limit": 4, "used": 1},
        })
        _put_json(ws, "logs/ci/b-route-reopen/reopen-global.json", {
            "status": "reopened", "reopened": True, "global": True,
            "reason": "Story 2.9 reopen revocation",
        })

        # Events log with measured active/paused elapsed, reserved budget, unknown billed cost,
        # AND a fast zero-dispatch quality-floor violation (weakened_acceptance)!
        events_rel = "logs/ci/2026-11-26/e2e/ac5-events.jsonl"
        ev_rows = [
            {
                "event_id": "ev-ac5-1",
                "operation_id": "OP-AC5",
                "run_id": "run-epoch-old",
                "scope_id": "scope-ac5",
                "flow_id": "FLOW-AC5",
                "stage": "3b",
                "attempt": 1,
                "status": "blocked",
                "observed_active_elapsed_seconds": 0.25,
                "paused_wall_clock_seconds": 12.0,
                "reserved_requests": 4,
                "actual_dispatches": 0,
                "billed_cost": "unknown",
                "diagnostic": _diag(codec.ReasonCode.INPUT_STALE, codec.Stage.BUNDLE, "run-epoch-old", "epoch==1", "epoch==0", "logs/ci/mvg-planning/run-epoch-old/run.json"),
            },
            {
                "event_id": "ev-ac5-2",
                "operation_id": "OP-AC5",
                "run_id": "run-revoked-01",
                "scope_id": "scope-ac5",
                "flow_id": "FLOW-AC5",
                "stage": "6",
                "attempt": 1,
                "status": "blocked",
                "observed_active_elapsed_seconds": 0.01,
                "actual_dispatches": 0,
                "quality_floor_violations": ["weakened_acceptance"],
                "diagnostic": _diag(codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, "FLOW-AC5", "preserved acceptance criteria", "weakened_acceptance", "logs/ci/b-route-reopen/reopen-global.json"),
            },
        ]
        _put_bytes(ws, events_rel, "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in ev_rows))

        # Fast zero-dispatch verdict violating a non-offsettable quality floor (failure_reclassification)
        qf_verdict_rel = "logs/ci/2026-11-26/e2e/ac5-qf-verdict.json"
        _put_json(ws, qf_verdict_rel, {
            "schema_version": "newrouge.b-route-completion-verdict.v1",
            "run_id": "run-fast-qf",
            "flow_id": "FLOW-AC5",
            "status": "passed",
            "active_elapsed_seconds": 0.05,
            "failure_reclassification": True,
            "reclassified_failed_flows": ["FLOW-AC5"],
        })

        # Invoke real Ch6 gate, defect_routing, ch6_rec, and commit.recover to prove zero implicit Knowledge refresh/publish!
        ch6_probe = ch6_gate.evaluate_chapter6_gate(ws, 101, consumer="ac5_zero_refresh_gate", lock_mode="none")
        defect_probe = defect_routing.evaluate_defect_routing(
            ws,
            101,
            defect_input={"summary": "AC-5 local bug probe", "changed_paths": ["Game.Core/Contracts/E2E/Scope1Contract.cs"]},
        )
        rec_probe = ch6_rec.evaluate_chapter6_recovery(ws, 101, consumer="resume-task", recommendation_only=True)
        recover_blocked_diag: dict[str, Any] | None = None
        try:
            commit.recover(ws, operation_id=pend_op_id)
        except codec.CodecError as err:
            recover_blocked_diag = err.diagnostic.to_dict()

        # Invoke all three surfaces (4.6, 4.7, 4.8) in workspace_preview / attempt modes
        proj_ws = knowledge_projection.build_b_route_knowledge_projection(ws, mode="workspace_preview")
        proj_att = knowledge_projection.build_b_route_knowledge_projection(ws, mode="attempt")
        page_ws = planning_page.inspect_planning_page_state(ws, mode="workspace_preview")
        page_att = planning_page.inspect_planning_page_state(ws, mode="attempt")
        obs_rep = observability.build_b_route_observability_report(
            ws,
            events_logs=[events_rel],
            verdict_or_scope_refs=[qf_verdict_rel],
        )

        # Attempt to resume BOTH epoch-invalidated and reopen-revoked runs -> MUST NEVER resurrect!
        resume_epoch = planning_page.execute_planning_page_action(
            ws, {"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-epoch-old", "mode": "workspace_preview"}
        )
        resume_epoch_2 = planning_page.execute_planning_page_action(
            ws, {"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-epoch-old", "mode": "workspace_preview"}
        )
        resume_revoked = planning_page.execute_planning_page_action(
            ws, {"action": "3b_mvg", "invocation_mode": "resume", "run_id": "run-revoked-01", "mode": "workspace_preview"}
        )

        # Verify pointer, catalog.v1.json & refs/heads/main immutability + zero implicit global Knowledge refresh
        main_sha_after = _git(ws, "rev-parse", "refs/heads/main")
        pointers_after = {p: (ws / p).read_bytes() for p in pointer_rels}
        catalog_after = (ws / records.CATALOG_PATH).read_bytes()
        pointers_unchanged = (
            (pointers_before == pointers_after)
            and (catalog_before == catalog_after)
            and (main_sha_before == main_sha_after)
        )

        # Verify consistent snapshot identity, pending ops & exact 6-field Diagnostic parity across 4.6, 4.7, and 4.8!
        proj_prov = proj_ws.get("provenance") or {}
        page_prov = page_ws.get("provenance") or {}
        proj_diags = proj_ws.get("diagnostics") or []
        page_diags = page_ws.get("diagnostics") or []
        obs_diags = obs_rep.get("diagnostics") or []
        proj_reason_codes = {d.get("reason_code") for d in proj_diags if isinstance(d, dict)}
        page_reason_codes = {d.get("reason_code") for d in page_diags if isinstance(d, dict)}
        obs_reason_codes = {d.get("reason_code") for d in obs_diags if isinstance(d, dict)}
        all_three_six_field_diags_valid = (
            bool(proj_diags)
            and bool(page_diags)
            and bool(obs_diags)
            and all(_is_valid_six_field_diag(d) for d in proj_diags)
            and all(_is_valid_six_field_diag(d) for d in page_diags)
            and all(_is_valid_obs_diag(d) for d in obs_diags)
            and proj_reason_codes == page_reason_codes
            and bool(obs_reason_codes & {codec.ReasonCode.INPUT_STALE.value, codec.ReasonCode.CONFLICT.value})
        )
        snapshot_identity_consistent = (
            proj_ws.get("mode") == "workspace_preview"
            and page_ws.get("mode") == "workspace_preview"
            and proj_att.get("mode") == "attempt"
            and page_att.get("mode") == "attempt"
            and page_prov.get("mode") == proj_prov.get("mode")
            and page_prov.get("snapshot_digest") == proj_prov.get("snapshot_digest")
            and bool(proj_ws.get("pending_operations"))
            and proj_ws.get("pending_operations") == page_ws.get("pending_operations")
            and bool(proj_ws.get("chapter6_reopen", {}).get("global"))
            and bool(page_ws.get("chapter6_reopen", {}).get("global"))
            and all_three_six_field_diags_valid
        )
        revoked_never_resurrects = (
            (not resume_epoch.get("ok"))
            and (not resume_epoch_2.get("ok"))
            and (not resume_revoked.get("ok"))
            and all(_is_valid_six_field_diag(d) for d in (resume_epoch.get("diagnostics") or []))
            and all(_is_valid_six_field_diag(d) for d in (resume_revoked.get("diagnostics") or []))
            and resume_epoch.get("reason_code") in (codec.ReasonCode.INPUT_STALE.value, codec.ReasonCode.CONFLICT.value)
            and resume_revoked.get("reason_code") == codec.ReasonCode.CONFLICT.value
        )
        zero_implicit_refresh = (
            (not ch6_probe.get("ok"))
            and (not rec_probe.get("ok"))
            and (defect_probe.get("global_knowledge_refresh") == "forbidden")
            and _is_valid_six_field_diag(recover_blocked_diag)
            and (proj_ws.get("implicit_global_refresh_performed", False) is False)
            and (page_ws.get("implicit_global_refresh_performed", False) is False)
            and (obs_rep.get("implicit_global_refresh_performed", False) is False)
            and pointers_unchanged
        )

        # Verify unknown billed_cost vs measured active/paused/reserved separation AND non-offsettable quality floor!
        tc = obs_rep.get("timing_and_cost_summary") or {}
        qf = obs_rep.get("quality_floor") or {}
        metrics_honest_and_non_offsetting = (
            tc.get("billed_cost") == "unknown"
            and (tc.get("billed_cost_verified") is False)
            and isinstance(tc.get("observed_active_elapsed_seconds"), (int, float))
            and tc.get("observed_active_elapsed_seconds", 0.0) > 0.0
            and (not obs_rep.get("ok"))
            and bool(qf.get("violated"))
            and (qf.get("process_metrics_can_offset") is False)
            and bool(qf.get("checks", {}).get("failure_reclassification"))
            and all(_is_valid_obs_diag(d) for d in obs_diags)
        )

    checks = {
        "snapshot_identity_and_reopen_consistent_across_surfaces": snapshot_identity_consistent,
        "revoked_epoch_and_reopen_never_resurrect": revoked_never_resurrects,
        "preview_and_attempt_leave_pointers_and_main_byte_identical": pointers_unchanged,
        "zero_implicit_global_knowledge_refresh": zero_implicit_refresh,
        "unknown_vs_measured_separated_and_quality_floor_non_offsetting": metrics_honest_and_non_offsetting,
    }
    all_ok = all(checks.values())
    if not all_ok:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            "ac5_surface_parity",
            "all page, knowledge projection, and observability parity checks pass",
            checks,
            None,
        ))
    return {
        "ok": all_ok,
        "status": "passed" if all_ok else "blocked",
        "checks": checks,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# Report path validation & atomic write (no overwrite, no reparse, non-reserved logs/**)
# ---------------------------------------------------------------------------

E2E_EXTRA_RESERVED_REPORT_PREFIXES: tuple[str, ...] = (
    "logs/ci/b-route-chapter6-leases",
    "logs/ci/b-route-chapter6-gate",
    "logs/ci/b-route-adoption-reviews",
    "logs/ci/b-route-compensation-segments",
)

_E2E_DATED_RESERVED_NAMES: frozenset[str] = frozenset({
    "b-route-candidate-check",
    "b-route-chapter6-leases",
    "b-route-chapter6-gate",
    "b-route-adoption-reviews",
    "b-route-compensation-segments",
})

_E2E_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_e2e_extra_reserved_path(cleaned: str) -> bool:
    if any(cleaned == prefix or cleaned.startswith(prefix + "/") for prefix in E2E_EXTRA_RESERVED_REPORT_PREFIXES):
        return True
    parts = cleaned.split("/")
    if len(parts) >= 4 and parts[0] == "logs" and parts[1] == "ci" and _E2E_DATE_DIR_RE.fullmatch(parts[2]):
        if parts[3] in _E2E_DATED_RESERVED_NAMES:
            return True
    return False


def validate_e2e_report_path(root: Path | str, report_rel: Any) -> tuple[Path, str, Path]:
    """Pre-validate --report path: non-reserved logs/**/*.json, no reparse, no overwrite."""
    target, cleaned, root_path = alignment.validate_alignment_report_path(root, report_rel)
    if _is_e2e_extra_reserved_path(cleaned):
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            "report",
            "path outside reserved operational and producer log directories",
            cleaned,
            cleaned,
        ))
    return target, cleaned, root_path


def write_e2e_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> Path:
    """Atomically create a new JSON report under non-reserved logs/**/*.json without overwrite."""
    validate_e2e_report_path(root, report_rel)
    return alignment.write_alignment_report(root, report_rel, payload)


def _dispatch_parallel_worker(mode: str, extra: list[str]) -> dict[str, Any]:
    if mode == "ac1_stage":
        st_name, ws_str, op_id, req_rel = extra[0], extra[1], extra[2], extra[3]
        return _ac1_run_post_reserve_stage(st_name, Path(ws_str).resolve(), op_id, req_rel)
    if mode == "ac1_full":
        return _run_ac1_windows_fault_injection_matrix(Path(extra[0]).resolve())
    if mode == "ac2_full":
        return _run_ac2_shared_task_and_scope_drift_matrix(Path(extra[0]).resolve())
    if mode == "ac2_drift":
        return _ac2_run_drift_parity_worker(Path(extra[0]).resolve())
    if mode == "ac2_intowner":
        return _verify_integration_owner_and_nonflow_verdicts(Path(extra[0]).resolve(), Path(extra[1]).resolve())
    raise codec.CodecError(codec.Diagnostic(
        codec.ReasonCode.INVALID_ARGUMENT,
        codec.Stage.TARGET,
        "worker_mode",
        "ac1_stage|ac1_full|ac2_full|ac2_drift|ac2_intowner",
        mode,
        None,
    ))


# ---------------------------------------------------------------------------
# Public Entrypoint (AC-1..AC-6 + Epic 5 Handoff Readiness Report)
# ---------------------------------------------------------------------------

def run_b_route_e2e_fault_matrix(
    root: Path | str,
    *,
    include_fault_harness: bool = True,
) -> dict[str, Any]:
    """Run the Story 4.10 read-only E2E Windows fault & shared-change matrix + Epic 5 handoff."""
    started = time.monotonic()
    root_path = observability._validate_root(root)
    diagnostics: list[dict[str, Any]] = []

    if not include_fault_harness:
        alignment_report = alignment.audit_b_route_consumer_alignment(
            root_path,
            probe_temp_contracts=False,
        )
        if not alignment_report.get("ok"):
            for d in (alignment_report.get("diagnostics") or []):
                diagnostics.append(d)
        skip_diag = _diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.TARGET,
            "include_fault_harness",
            "include_fault_harness=True (real Windows fault & shared-change harness required for PASS)",
            False,
            None,
        )
        diagnostics.append(skip_diag)
        empty_skipped = {"ok": False, "status": "blocked", "skipped_by_flag": True, "diagnostics": [skip_diag]}
        matrices = {
            "windows_fault_injection_matrix": {
                **empty_skipped,
                "platform_evidence": {
                    "os_name": os.name,
                    "platform": platform.platform(),
                    "python_version": sys.version,
                    "used_real_windows_msvcrt_lock": False,
                    "used_real_child_process_termination": False,
                    "mock_os_exception_claimed_as_windows_proof": False,
                },
                "untested_windows_boundaries": list(UNTESTED_WINDOWS_BOUNDARIES),
            },
            "shared_task_and_scope_drift_matrix": dict(empty_skipped),
            "shared_change_flow_ab_evolution_matrix": dict(empty_skipped),
            "shared_evidence_and_authenticity_matrix": dict(empty_skipped),
            "page_knowledge_observability_parity_matrix": dict(empty_skipped),
        }
    else:
        with _temp_workspace("nr410-workers-") as worker_tmp:
            handles = _start_parallel_workers(
                worker_tmp,
                {
                    "ac1": ("ac1_full", [str(root_path)]),
                    "ac2": ("ac2_full", [str(root_path)]),
                },
            )
            try:
                alignment_report = alignment.audit_b_route_consumer_alignment(
                    root_path,
                    probe_temp_contracts=True,
                )
                ac3_res = _run_ac3_shared_change_flow_ab_evolution_matrix(root_path)
                ac4_res = _run_ac4_shared_evidence_and_authenticity_matrix(root_path)
                ac5_res = _run_ac5_page_knowledge_observability_parity_matrix(root_path)
                worker_res = _collect_parallel_workers(handles, timeout_sec=300.0)
            finally:
                _cleanup_parallel_workers(handles)

        if not alignment_report.get("ok"):
            for d in (alignment_report.get("diagnostics") or []):
                diagnostics.append(d)

        matrices = {
            "windows_fault_injection_matrix": worker_res["ac1"],
            "shared_task_and_scope_drift_matrix": worker_res["ac2"],
            "shared_change_flow_ab_evolution_matrix": ac3_res,
            "shared_evidence_and_authenticity_matrix": ac4_res,
            "page_knowledge_observability_parity_matrix": ac5_res,
        }
        for m in matrices.values():
            for d in (m.get("diagnostics") or []):
                diagnostics.append(d)

    all_matrices_ok = bool(include_fault_harness) and all(m.get("ok") for m in matrices.values())
    epic4_capabilities_verified = bool(alignment_report.get("ok")) and all_matrices_ok and not diagnostics

    evidence_locators = []
    for rel in (
        "scripts/python/_b_route_e2e_fault_matrix.py",
        "scripts/python/verify_b_route_e2e_fault_matrix.py",
        "scripts/python/_b_route_consumer_alignment.py",
        "scripts/python/tests/test_b_route_e2e_fault_matrix.py",
        "docs/workflows/b-route-e2e-fault-matrix.md",
    ):
        p = root_path / rel
        evidence_locators.append({
            "path": rel,
            "exists": p.is_file(),
            "sha256": _file_sha(p) if p.is_file() else None,
        })

    ac_status = {
        "AC-1": "passed" if matrices["windows_fault_injection_matrix"].get("ok") else "blocked",
        "AC-2": "passed" if matrices["shared_task_and_scope_drift_matrix"].get("ok") else "blocked",
        "AC-3": "passed" if matrices["shared_change_flow_ab_evolution_matrix"].get("ok") else "blocked",
        "AC-4": "passed" if matrices["shared_evidence_and_authenticity_matrix"].get("ok") else "blocked",
        "AC-5": "passed" if matrices["page_knowledge_observability_parity_matrix"].get("ok") else "blocked",
        "AC-6": "passed" if epic4_capabilities_verified else "blocked",
    }

    align_diags = alignment_report.get("diagnostics") or []
    align_reason_code = (
        alignment_report.get("reason_code")
        or ("ok" if alignment_report.get("ok") else (align_diags[0].get("reason_code") if align_diags else codec.ReasonCode.CONFLICT.value))
    )
    pre_switch = alignment_report.get("pre_switch_coverage_report") or {}
    ac1_mat = matrices["windows_fault_injection_matrix"]
    ac1_stages = ac1_mat.get("stages") or {}
    ac2_checks = matrices["shared_task_and_scope_drift_matrix"].get("checks") or {}
    ac3_checks = matrices["shared_change_flow_ab_evolution_matrix"].get("checks") or {}
    ac4_checks = matrices["shared_evidence_and_authenticity_matrix"].get("checks") or {}

    handoff = {
        "epic4_capabilities_verified": epic4_capabilities_verified,
        "consumer_alignment_ok": bool(alignment_report.get("ok")),
        "fault_harness_executed": bool(include_fault_harness),
        "ac_status": ac_status,
        "consumer_coverage": {
            "counts": dict(pre_switch.get("counts") or {}),
            "group_summary": dict(pre_switch.get("group_summary") or {}),
            "epic4_alignment_ready": bool(pre_switch.get("epic4_alignment_ready", alignment_report.get("ok"))),
            "generic_b_route_ready_without_reward_hacks": bool(pre_switch.get("generic_b_route_ready_without_reward_hacks", False)),
            "switch_blocked": True,
            "switch_blocked_reasons": list(pre_switch.get("switch_blocked_reasons") or []),
        },
        "migration_readiness": {
            "epic4_capabilities_verified": epic4_capabilities_verified,
            "consumer_alignment_ok": bool(alignment_report.get("ok")),
            "default_b_enabled": False,
            "a_write_compatibility_retired": False,
            "switch_ready_now": False,
            "blocked_by_epic5_gates": [g["gate_id"] for g in EPIC5_DEFERRED_GATES],
        },
        "scope_evidence_summary": {
            "shared_task_multi_scope_verified": bool(ac2_checks.get("applicable_set_digest_expanded") and ac2_checks.get("all_entrypoints_consistent_block")),
            "flow_ab_evolution_verified": bool(ac3_checks.get("phase1_flow_a_fixed_passes_protocol_while_b_stays_future") and ac3_checks.get("phase2_incomplete_flow_b_blocks_completion")),
            "shared_test_reuse_and_isolation_verified": bool(ac4_checks.get("shared_test_executed_once_across_flows") and ac4_checks.get("per_test_isolated_dirs_zero_leak")),
            "cross_snapshot_splicing_rejected": bool(ac4_checks.get("cross_snapshot_splicing_rejected")),
            "authenticity_tiers_enforced": bool(ac4_checks.get("scene_method_without_input_event_rejected") and ac4_checks.get("fortest_backdoor_rejected") and ac4_checks.get("missing_manual_independent_signoff_rejected")),
            "protocol_fixture_is_not_reward_gameplay_acceptance": True,
            "runtime_verified": False,
        },
        "windows_fault_summary": {
            "ok": bool(ac1_mat.get("ok")),
            "platform_evidence": dict(ac1_mat.get("platform_evidence") or {}),
            "windows_lock_contention_ok": bool((ac1_mat.get("windows_lock_contention") or {}).get("ok")),
            "stage_outcomes": {k: bool(v.get("ok")) for k, v in ac1_stages.items()} if isinstance(ac1_stages, dict) else {},
        },
        "evidence_locators": evidence_locators,
        "untested_windows_boundaries": list(UNTESTED_WINDOWS_BOUNDARIES),
        "epic5_deferred_gates": [dict(g) for g in EPIC5_DEFERRED_GATES],
        **INVARIANTS,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": epic4_capabilities_verified,
        "status": "passed" if epic4_capabilities_verified else "blocked",
        "reason_code": "ok" if epic4_capabilities_verified else (diagnostics[0]["reason_code"] if diagnostics else codec.ReasonCode.CONFLICT.value),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "root": root_path.as_posix(),
        "epic4_capabilities_verified": epic4_capabilities_verified,
        "consumer_alignment_summary": {
            "ok": bool(alignment_report.get("ok")),
            "status": alignment_report.get("status"),
            "epic4_alignment_ready": bool(alignment_report.get("epic4_alignment_ready", alignment_report.get("ok"))),
            "reason_code": align_reason_code,
        },
        **matrices,
        "epic5_handoff_readiness_report": handoff,
        "diagnostics": diagnostics,
        **INVARIANTS,
        "invariants": dict(INVARIANTS),
    }
