#!/usr/bin/env python3
"""
Quality gates entry for Windows (Godot+C# variant).

Current minimal implementation:
- Delegates to ci_pipeline.py `all` command, which runs:
  * dotnet tests + coverage (soft gate on coverage)
  * Godot self-check (hard gate)
  * encoding scan (soft gate)

Usage (Windows):
  py -3 scripts/python/quality_gates.py all \
    --solution Game.sln --configuration Debug \
    --godot-bin "C:\\Godot\\Godot_v4.5.1-stable_mono_win64_console.exe" \
    --build-solutions

Exit codes:
  0  all hard gates passed
  1  hard gate failed (dotnet tests or self-check)

This script is designed to be extended in Phase 13 to include
additional gates (GdUnit4 sets, smoke, perf, etc.).
"""

import argparse
import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_ci_pipeline(solution: str, configuration: str, godot_bin: str, build_solutions: bool) -> int:
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


def run_gdunit_hard(godot_bin: str) -> int:
    """Run a small hard-gated GdUnit4 set (Adapters/Config + Security).

    Design goals:
    - Keep the selection aligned with the CI hard gate set.
    - Write reports under logs/e2e/<YYYY-MM-DD>/quality-gates/gdunit-hard.
    """

    date = _date_stamp()
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
        "tests/Adapters/Config",
        "--add",
        "tests/Security/Hard",
        "--timeout-sec",
        "300",
        "--rd",
        f"logs/e2e/{date}/quality-gates/gdunit-hard",
    ]
    proc = subprocess.run(args, text=True)
    return proc.returncode


def run_smoke_headless(godot_bin: str) -> int:
    """Run Python headless smoke in strict mode.

    - Uses Main scene as entry.
    - Strict mode requires marker or a "[DB] opened" line.
    """

    args = [
        "py",
        "-3",
        "scripts/python/smoke_headless.py",
        "--godot-bin",
        godot_bin,
        "--project",
        ".",
        "--scene",
        "res://Game.Godot/Scenes/Main.tscn",
        "--timeout-sec",
        "5",
        "--mode",
        "strict",
    ]
    proc = subprocess.run(args, text=True)
    return proc.returncode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _date_stamp() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")


def _ci_dir(date: str, category: str) -> Path:
    return _repo_root() / "logs" / "ci" / date / category


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="ignore")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_to_file(cmd: list[str], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        _write_text(out_path, combined)
        return proc.returncode
    except Exception as exc:  # pragma: no cover - environment specific
        _write_text(out_path, f"Failed to run command: {' '.join(cmd)}\nError: {exc}\n")
        return 1


def _write_env_evidence(date: str, godot_bin: str | None) -> None:
    d = _ci_dir(date, "env-evidence")
    d.mkdir(parents=True, exist_ok=True)

    _write_text(d / "python.runtime.txt", sys.version)
    _run_to_file(["py", "-3", "--version"], d / "py.version.txt")

    dotnet = shutil.which("dotnet")
    if dotnet:
        _run_to_file(["dotnet", "--info"], d / "dotnet.info.txt")
        _run_to_file(["dotnet", "--list-sdks"], d / "dotnet.list-sdks.txt")
    else:
        _write_text(d / "dotnet.info.txt", "dotnet CLI not found in PATH.\n")
        _write_text(d / "dotnet.list-sdks.txt", "dotnet CLI not found in PATH.\n")

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


def _require_prereqs(date: str, godot_bin: str | None, require_lock_files: bool) -> bool:
    d = _ci_dir(date, "prereqs")
    d.mkdir(parents=True, exist_ok=True)

    ok = True

    if not shutil.which("dotnet"):
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
        expected = [
            rr / "packages.lock.json",
            rr / "Game.Core.Tests" / "packages.lock.json",
            rr / "Tests.Godot" / "packages.lock.json",
        ]
        for p in expected:
            if not p.is_file():
                missing.append(str(p))
        if missing:
            lines = [
                "packages.lock.json missing. This is a blocking prerequisite.",
                "Generate lock files by running: dotnet restore .\\NewRouge.sln",
                "Missing files:",
                *[f" - {m}" for m in missing],
                "",
            ]
            _write_text(d / "packages-lock.missing.txt", "\n".join(lines))
            ok = False

    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_all = sub.add_parser("all", help="run quality gates (ci_pipeline + optional GdUnit/Smoke)")
    p_all.add_argument("--solution", default="Game.sln")
    p_all.add_argument("--configuration", default="Debug")
    p_all.add_argument("--godot-bin", default=os.environ.get("GODOT_BIN"))
    p_all.add_argument("--build-solutions", action="store_true")
    p_all.add_argument("--gdunit-hard", action="store_true", help="run hard GdUnit set (Adapters/Config + Security)")
    p_all.add_argument("--smoke", action="store_true", help="run headless smoke (strict marker/DB check)")
    p_all.add_argument("--require-lock-files", action="store_true", default=True, help="require packages.lock.json (default: true)")
    p_all.add_argument("--no-require-lock-files", action="store_false", dest="require_lock_files", help="do not require lock files")

    args = parser.parse_args()

    if args.cmd == "all":
        date = _date_stamp()
        _write_env_evidence(date, args.godot_bin)

        prereqs_ok = _require_prereqs(date, args.godot_bin, args.require_lock_files)
        if not prereqs_ok:
            return 1

        # 1) Base gates: dotnet + self-check + encoding scan
        rc = run_ci_pipeline(args.solution, args.configuration, args.godot_bin, args.build_solutions)
        hard_failed = rc != 0

        # 2) Optional hard gate: GdUnit4 subset
        if args.gdunit_hard:
            gd_rc = run_gdunit_hard(args.godot_bin)
            if gd_rc != 0:
                hard_failed = True

        # 3) Optional hard gate: headless smoke (strict mode)
        if args.smoke:
            sm_rc = run_smoke_headless(args.godot_bin)
            if sm_rc != 0:
                hard_failed = True

        return 0 if not hard_failed else 1

    print("Unsupported command", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
