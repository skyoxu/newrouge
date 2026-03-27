#!/usr/bin/env python3
"""Windows quality gates entry (Godot+C#)."""
from __future__ import annotations
import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from _task0056_audit import run_task0056_audit_validation, write_task0056_record
ALL_GDUNIT_SUITES = ("adapters", "security", "integration", "ui")
HARD_GDUNIT_SUITES = ("adapters", "security")
SOFT_GDUNIT_SUITES = ("integration", "ui")
SUITE_TO_ADD_PATH = {
    "adapters": "tests/Adapters/Config",
    "security": "tests/Security/Hard",
    "integration": "tests/Integration",
    "ui": "tests/UI",
}
SUITE_TO_GATE_LEVEL = {
    "adapters": "hard",
    "security": "hard",
    "integration": "soft",
    "ui": "soft",
}
def _fake_rc(env_name: str) -> int | None:
    raw = os.environ.get(env_name)
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())
def run_ci_pipeline(solution: str, configuration: str, godot_bin: str, build_solutions: bool) -> int:
    fake_rc = _fake_rc("QUALITY_GATES_FAKE_CI_RC")
    if fake_rc is not None:
        return fake_rc
    args = [
        "py",
        "-3",
        "scripts/python/ci_pipeline.py",
        "all",
        "--solution",
        solution,
        "--configuration",
        configuration,
        "--godot-bin",
        godot_bin,
    ]
    if build_solutions:
        args.append("--build-solutions")
    proc = subprocess.run(args, text=True)
    return proc.returncode
def run_gdunit_suite(*, godot_bin: str, suite_name: str, date: str) -> tuple[int, str]:
    report_dir = f"logs/e2e/{date}/quality-gates/gdunit-{suite_name}"
    fake_rc = _fake_rc(f"QUALITY_GATES_FAKE_GDUNIT_RC_{suite_name.upper()}")
    if fake_rc is not None:
        if str(os.environ.get("QUALITY_GATES_FAKE_SKIP_XML", "0")).strip() != "1":
            _emit_fake_results_xml(Path(report_dir), failed=fake_rc != 0)
        return fake_rc, report_dir
    args = [
        "py",
        "-3",
        "scripts/python/run_gdunit.py",
        "--prewarm",
        "--godot-bin",
        godot_bin,
        "--project",
        "Tests.Godot",
        "--add",
        SUITE_TO_ADD_PATH[suite_name],
        "--timeout-sec",
        "300",
        "--rd",
        report_dir,
    ]
    proc = subprocess.run(args, text=True)
    return proc.returncode, report_dir
def run_smoke_headless(godot_bin: str) -> int:
    fake_rc = _fake_rc("QUALITY_GATES_FAKE_SMOKE_RC")
    if fake_rc is not None:
        return fake_rc
    args = [
        "py",
        "-3",
        "scripts/python/smoke_headless.py",
        "--godot-bin",
        godot_bin,
        "--project-path",
        ".",
        "--scene",
        "res://Game.Godot/Scenes/Main.tscn",
        "--timeout-sec",
        "5",
        "--strict",
    ]
    proc = subprocess.run(args, text=True)
    return proc.returncode
def _repo_root() -> Path: return Path(__file__).resolve().parents[2]
def _date_stamp() -> str: return _dt.date.today().strftime("%Y-%m-%d")
def _resolve_default_solution(root: Path | None = None) -> str:
    resolved_root = root or _repo_root()
    candidates = sorted(item.name for item in resolved_root.glob("*.sln"))
    if not candidates:
        return "Game.sln"
    by_name = {item.lower(): item for item in candidates}
    preferred_names = (
        f"{resolved_root.name}.sln",
        "NewRouge.sln",
        "GodotGame.sln",
        "Game.sln",
    )
    for preferred in preferred_names:
        matched = by_name.get(preferred.lower())
        if matched is not None:
            return matched
    return candidates[0]

def _candidate_dotnet_paths() -> list[Path]:
    exe_name = "dotnet.exe" if os.name == "nt" else "dotnet"
    candidates: list[Path] = []
    which_dotnet = shutil.which("dotnet")
    if which_dotnet:
        candidates.append(Path(which_dotnet))
    for env_key in ("DOTNET_ROOT", "DOTNET_HOME"):
        env_val = os.environ.get(env_key)
        if env_val:
            candidates.append(Path(env_val) / exe_name)
    candidates.append(Path.home() / ".dotnet" / exe_name)
    if os.name == "nt":
        for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
            env_val = os.environ.get(env_key)
            if env_val:
                candidates.append(Path(env_val) / "dotnet" / "dotnet.exe")
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.normpath(str(candidate)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique
def _ensure_dotnet_on_path() -> Path | None:
    for candidate in _candidate_dotnet_paths():
        if not candidate.is_file():
            continue
        dotnet_dir = str(candidate.parent)
        current_path = os.environ.get("PATH", "")
        path_items = [p for p in current_path.split(os.pathsep) if p]
        normalized = {os.path.normcase(os.path.normpath(p)) for p in path_items}
        dotnet_dir_norm = os.path.normcase(os.path.normpath(dotnet_dir))
        if dotnet_dir_norm not in normalized:
            os.environ["PATH"] = dotnet_dir + os.pathsep + current_path
        if os.name == "nt":
            os.environ.setdefault("DOTNET_ROOT", dotnet_dir)
        return candidate
    return None
def _ci_dir(date: str, category: str) -> Path: return _repo_root() / "logs" / "ci" / date / category
def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="ignore")
def _emit_fake_results_xml(report_dir: Path, *, failed: bool) -> None:
    target = _repo_root() / report_dir / "report_1" / "results.xml"
    failures = "1" if failed else "0"
    xml = f'<testsuites tests="1" failures="{failures}"><testsuite tests="1" failures="{failures}" errors="0"></testsuite></testsuites>\n'
    _write_text(target, xml)

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _run_to_file(cmd: list[str], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        _write_text(out_path, combined)
        return proc.returncode
    except Exception as exc:  # pragma: no cover
        _write_text(out_path, f"Failed to run command: {' '.join(cmd)}\nError: {exc}\n")
        return 1

def _resolve_security_profile(raw: str | None) -> str:
    return "strict" if str(raw or "").strip().lower() == "strict" else "host-safe"

def _write_env_evidence(date: str, godot_bin: str | None, dotnet_resolved: Path | None, security_profile: str) -> None:
    d = _ci_dir(date, "env-evidence")
    d.mkdir(parents=True, exist_ok=True)
    _write_text(d / "python.runtime.txt", sys.version)
    _run_to_file(["py", "-3", "--version"], d / "py.version.txt")
    _write_text(d / "security.profile.txt", f"SECURITY_PROFILE={security_profile}\n")
    dotnet = shutil.which("dotnet")
    if dotnet:
        _run_to_file(["dotnet", "--info"], d / "dotnet.info.txt")
        _run_to_file(["dotnet", "--list-sdks"], d / "dotnet.list-sdks.txt")
        _write_text(d / "dotnet.bin.txt", f"dotnet={dotnet}\nresolved={str(dotnet_resolved) if dotnet_resolved else ''}\n")
    else:
        _write_text(d / "dotnet.info.txt", "dotnet CLI not found in PATH.\n")
        _write_text(d / "dotnet.list-sdks.txt", "dotnet CLI not found in PATH.\n")
        _write_text(d / "dotnet.bin.txt", f"resolved={str(dotnet_resolved) if dotnet_resolved else ''}\n")
    if godot_bin:
        gb = Path(godot_bin)
        _write_text(d / "godot.bin.txt", f"GODOT_BIN={godot_bin}\n")
        if gb.is_file():
            _write_text(d / "godot.bin.sha256.txt", _sha256(gb) + "\n")
            _run_to_file([godot_bin, "--version"], d / "godot.version.txt")
        else:
            _write_text(d / "godot.version.txt", "GODOT_BIN path does not exist.\n")
    else:
        _write_text(d / "godot.bin.txt", "GODOT_BIN is not set.\n")
        _write_text(d / "godot.version.txt", "GODOT_BIN is not set.\n")

def _require_prereqs(date: str, godot_bin: str | None, require_lock_files: bool, dotnet_resolved: Path | None) -> bool:
    d = _ci_dir(date, "prereqs")
    d.mkdir(parents=True, exist_ok=True)
    ok = True
    if dotnet_resolved is None:
        _write_text(d / "dotnet.missing.txt", "dotnet CLI not found. Install .NET 8 SDK and re-run.\n")
        ok = False
    if not godot_bin:
        _write_text(d / "godot.missing.txt", "GODOT_BIN is not set. Provide --godot-bin or set env var.\n")
        ok = False
    else:
        gb = Path(godot_bin)
        if not gb.is_file():
            _write_text(d / "godot.missing.txt", f"GODOT_BIN not found: {godot_bin}\n")
            ok = False
        else:
            ver_path = d / "godot.version.check.txt"
            _run_to_file([godot_bin, "--version"], ver_path)
            ver = ver_path.read_text(encoding="utf-8", errors="ignore")
            if "4.5.1" not in ver:
                _write_text(d / "godot.version.mismatch.txt", f"Expected Godot 4.5.1, got: {ver}\n")
                ok = False
    if require_lock_files:
        missing: list[str] = []
        rr = _repo_root()
        for p in [rr / "packages.lock.json", rr / "Game.Core.Tests" / "packages.lock.json", rr / "Tests.Godot" / "packages.lock.json"]:
            if not p.is_file():
                missing.append(str(p))
        if missing:
            lines = ["packages.lock.json missing. This is a blocking prerequisite.", "Generate lock files by running: dotnet restore .\\NewRouge.sln", "Missing files:", *[f" - {m}" for m in missing], ""]
            _write_text(d / "packages-lock.missing.txt", "\n".join(lines))
            ok = False
    return ok

def _normalize_suite_token(raw: str) -> str: return str(raw or "").strip().lower()

def _resolve_selected_suites(raw_csv: str | None, legacy_hard: bool) -> tuple[list[str], list[str]]:
    selected: set[str] = set()
    invalid: list[str] = []
    if legacy_hard:
        selected.update(HARD_GDUNIT_SUITES)
    for token in [t for t in str(raw_csv or "").split(",") if t.strip()]:
        name = _normalize_suite_token(token)
        if name == "all":
            selected.update(ALL_GDUNIT_SUITES)
            continue
        if name in ALL_GDUNIT_SUITES:
            selected.add(name)
            continue
        invalid.append(name)
    ordered = [name for name in ALL_GDUNIT_SUITES if name in selected]
    return ordered, invalid

def _suite_record(*, gate_level: str, selected: bool, executed: bool, status: str, rc: int | None) -> dict[str, object]:
    return {
        "gate_level": gate_level,
        "selected": selected,
        "executed": executed,
        "state": "executed" if executed else "skipped",
        "status": status,
        "rc": rc,
    }

def _group_status(records: dict[str, dict[str, object]], suites: tuple[str, ...], gate_level: str) -> dict[str, object]:
    selected = any(bool(records[s].get("selected")) for s in suites)
    executed = any(bool(records[s].get("executed")) for s in suites)
    if not selected:
        status = "skipped"
    else:
        status = "failed" if any(records[s].get("status") == "failed" for s in suites if bool(records[s].get("selected"))) else "passed"
    return _suite_record(gate_level=gate_level, selected=selected, executed=executed, status=status, rc=None)

def _find_latest_results_xml(report_dir: Path) -> Path | None:
    if not report_dir.is_dir():
        return None
    candidates = sorted(report_dir.glob("report_*/results.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None

def _collect_junit_artifact(date: str, suite_runs: dict[str, dict[str, object]], gdunit_enabled: bool) -> dict[str, object]:
    rel = f"logs/e2e/{date}/gdunit/junit.xml"
    target = _repo_root() / rel
    if not gdunit_enabled:
        return {"path": rel, "status": "skipped", "exists": False, "missing_reason": "gdunit_not_enabled", "source": None}
    latest: Path | None = None
    for suite in ALL_GDUNIT_SUITES:
        run = suite_runs.get(suite) or {}
        if not bool(run.get("selected")):
            continue
        report_dir = _repo_root() / str(run.get("report_dir") or "")
        xml = _find_latest_results_xml(report_dir)
        if not xml:
            continue
        if latest is None or xml.stat().st_mtime > latest.stat().st_mtime:
            latest = xml
    if latest is None:
        return {"path": rel, "status": "missing", "exists": False, "missing_reason": "gdunit_results_xml_not_found", "source": None}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(latest, target)
    source = str(latest.relative_to(_repo_root())).replace("\\", "/")
    return {"path": rel, "status": "present", "exists": True, "missing_reason": None, "source": source}

def _quality_summary_path(date: str) -> Path:
    return _repo_root() / f"logs/ci/{date}/quality-gates/summary.json"

def _write_quality_summary(*, date: str, security_profile: str, suite_runs: dict[str, dict[str, object]], ci_rc: int, smoke_rc: int | None, smoke_enabled: bool, invalid_suites: list[str], junit_artifact: dict[str, object]) -> dict[str, object]:
    suites: dict[str, dict[str, object]] = {
        "ci_pipeline": _suite_record(gate_level="hard", selected=True, executed=True, status="passed" if ci_rc == 0 else "failed", rc=ci_rc),
        "adapters_security": _group_status(suite_runs, HARD_GDUNIT_SUITES, "hard"),
        "integration_ui": _group_status(suite_runs, SOFT_GDUNIT_SUITES, "soft"),
        "smoke_headless": _suite_record(
            gate_level="hard",
            selected=smoke_enabled,
            executed=smoke_enabled,
            status=("passed" if smoke_rc == 0 else "failed") if smoke_enabled else "skipped",
            rc=smoke_rc if smoke_enabled else None,
        ),
    }
    hard_failed = any(suites[name]["status"] == "failed" for name in ("ci_pipeline", "adapters_security", "smoke_headless"))
    summary_path = _quality_summary_path(date)
    rel_output = str(summary_path.relative_to(_repo_root())).replace("\\", "/")
    payload = {
        "security_profile": security_profile,
        "chapter_refs": ["CH06", "CH07", "CH10"],
        "gate_level": "mixed",
        "overall_gate_conclusion": "fail" if hard_failed else "pass",
        "output": rel_output,
        "selected_gdunit_suites": [s for s in ALL_GDUNIT_SUITES if bool((suite_runs.get(s) or {}).get("selected"))],
        "invalid_gdunit_suites": invalid_suites,
        "suites": suites,
        "gdunit_suites": {s: suite_runs[s] for s in ALL_GDUNIT_SUITES},
        "junit_artifact": junit_artifact,
    }
    _write_text(summary_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload

def _write_task_0054_record(*, date: str, selected_suites: list[str], summary_payload: dict[str, object], final_exit_code: int) -> None:
    path = _repo_root() / f"logs/ci/{date}/task-0054.json"
    payload = {
        "task_id": 54,
        "platform": "windows-powershell",
        "selected_gdunit_suites": selected_suites,
        "summary_path": f"logs/ci/{date}/quality-gates/summary.json",
        "junit_path": f"logs/e2e/{date}/gdunit/junit.xml",
        "overall_gate_conclusion": summary_payload.get("overall_gate_conclusion"),
        "exit_code": final_exit_code,
        "suites": summary_payload.get("suites", {}),
        "gdunit_suites": summary_payload.get("gdunit_suites", {}),
    }
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_all = sub.add_parser("all", help="run quality gates (ci_pipeline + optional GdUnit/Smoke)")
    p_all.add_argument("--solution", default="", help="solution path; auto-resolved when omitted")
    p_all.add_argument("--configuration", default="Debug")
    p_all.add_argument("--godot-bin", default=os.environ.get("GODOT_BIN"))
    p_all.add_argument("--build-solutions", action="store_true")
    p_all.add_argument("--gdunit-hard", action="store_true", help="legacy switch, equivalent to --gdunit-suites adapters,security")
    p_all.add_argument("--gdunit-suites", default="", help="csv suites: adapters,security,integration,ui,all")
    p_all.add_argument("--smoke", action="store_true", help="run headless smoke (strict marker/DB check)")
    p_all.add_argument("--security-profile", default=os.environ.get("SECURITY_PROFILE", "host-safe"), help="security profile: host-safe|strict")
    p_all.add_argument("--require-lock-files", action="store_true", default=True, help="require packages.lock.json (default: true)")
    p_all.add_argument("--no-require-lock-files", action="store_false", dest="require_lock_files", help="do not require lock files")
    args = parser.parse_args(argv)

    if args.cmd != "all":
        print("Unsupported command", file=sys.stderr)
        return 1

    resolved_solution = str(args.solution or "").strip() or _resolve_default_solution()
    date = _date_stamp()
    security_profile = _resolve_security_profile(args.security_profile)
    os.environ["SECURITY_PROFILE"] = security_profile
    dotnet_resolved = _ensure_dotnet_on_path()
    _write_env_evidence(date, args.godot_bin, dotnet_resolved, security_profile)
    skip_prereqs = str(os.environ.get("QUALITY_GATES_SKIP_PREREQS", "0")).strip() == "1"
    if not skip_prereqs and not _require_prereqs(date, args.godot_bin, args.require_lock_files, dotnet_resolved):
        return 1

    ci_rc = run_ci_pipeline(resolved_solution, args.configuration, args.godot_bin, args.build_solutions)
    os.environ["QUALITY_GATES_CI_RC"] = str(ci_rc)
    hard_failed = ci_rc != 0
    audit_validation = run_task0056_audit_validation(_repo_root(), date)
    if bool(audit_validation.get("enabled")) and int(audit_validation.get("rc") or 0) != 0:
        hard_failed = True

    selected_suites, invalid_suites = _resolve_selected_suites(args.gdunit_suites, args.gdunit_hard)
    suite_runs: dict[str, dict[str, object]] = {}
    for suite in ALL_GDUNIT_SUITES:
        selected = suite in selected_suites
        if not selected:
            suite_runs[suite] = _suite_record(gate_level=SUITE_TO_GATE_LEVEL[suite], selected=False, executed=False, status="skipped", rc=None)
            suite_runs[suite]["report_dir"] = None
            continue
        rc, report_dir = run_gdunit_suite(godot_bin=args.godot_bin, suite_name=suite, date=date)
        suite_runs[suite] = _suite_record(
            gate_level=SUITE_TO_GATE_LEVEL[suite],
            selected=True,
            executed=True,
            status="passed" if rc == 0 else "failed",
            rc=rc,
        )
        suite_runs[suite]["report_dir"] = report_dir
        if SUITE_TO_GATE_LEVEL[suite] == "hard" and rc != 0:
            hard_failed = True

    smoke_rc: int | None = None
    if args.smoke:
        smoke_rc = run_smoke_headless(args.godot_bin)
        if smoke_rc != 0:
            hard_failed = True

    junit_artifact = _collect_junit_artifact(date, suite_runs, bool(selected_suites))
    summary_payload = _write_quality_summary(
        date=date,
        security_profile=security_profile,
        suite_runs=suite_runs,
        ci_rc=ci_rc,
        smoke_rc=smoke_rc,
        smoke_enabled=bool(args.smoke),
        invalid_suites=invalid_suites,
        junit_artifact=junit_artifact,
    )
    provisional_exit_code = 1 if hard_failed else 0
    _write_task_0054_record(
        date=date,
        selected_suites=selected_suites,
        summary_payload=summary_payload,
        final_exit_code=provisional_exit_code,
    )
    record_validation = write_task0056_record(_repo_root(), date, audit_validation, provisional_exit_code)
    final_exit_code = provisional_exit_code
    if not bool(record_validation.get("valid")):
        final_exit_code = 1
        write_task0056_record(_repo_root(), date, audit_validation, final_exit_code)
    return final_exit_code

if __name__ == "__main__":
    sys.exit(main())
