"""Story 4.3 real runner VerificationScope consumer and coverage receipt builder.

Consumes a sealed Story 4.2 VerificationScope (`newrouge.b-route-verification-scope.v1`),
validates live freshness and formal manifest binding against an isolated integration
snapshot, holds scoped Windows msvcrt business leases (short metadata lock only, never
the global writer lock), executes either the declared scoped test set or an explicit
conservative superset, checks six evidence tiers (including static .tscn/adapter wiring
and real engine-input vs fixture/backdoor authenticity), respects durable and intra-run
stop-loss signals, checks mid-run drift, and emits a sealed execution coverage receipt
(`newrouge.b-route-execution-receipt.v1`).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import _b_route_chapter6_recovery as ch6_recovery
import _b_route_chapter7_slice as ch7_slice
import _b_route_codec as codec
import _b_route_evidence_reuse as evidence_reuse
import _b_route_inventory as inventory
import _b_route_operation_scope as op_scope
import _b_route_verification_scope as verification_scope
from _mvg_execution import execute_test, run_child
from _mvg_manifest import manifest_sha256, read_manifest, recommend, safe_path, validate_manifest
from _project_health_runtime_snapshot import prepare_snapshot

RECEIPT_SCHEMA = "newrouge.b-route-execution-receipt.v1"

INVARIANT_FLAGS: dict[str, bool] = {
    "authorizes_task_status_write": False,
    "task_completed": False,
    "flow_completed": False,
    "milestone_completed": False,
    "default_b_enabled": False,
    "build_reuse_implies_test_pass": False,
    "manual_satisfied_by_machine_reuse": False,
    "planning_adoption_interchangeable": False,
    "speedup_or_cost_gate_enforced": False,
    "reserved_budget_claimed_as_savings": False,
}

SIX_EVIDENCE_TIERS: tuple[str, ...] = (
    "domain-xunit",
    "godot-gdunit",
    "static-wiring",
    "scene-method",
    "engine-input",
    "manual",
)

_VOLATILE_RECEIPT_FIELDS = frozenset({"receipt_id", "generated_at", "finished_at"})

_PROTOCOL_FIXTURE_EXTS = (".py", ".bat", ".cmd", ".ps1", ".sh")
_PROTOCOL_FIXTURE_MARKERS = ("fixture", "fake", "mock", "stub", "harness")

_ENGINE_INPUT_CONSTRUCT_PATTERNS = (
    re.compile(r"\bInputEventAction\b"),
    re.compile(r"\bInputEventKey\b"),
    re.compile(r"\bInputEventMouseButton\b"),
    re.compile(r"\bInputEventJoypadButton\b"),
    re.compile(r"\bInputEventMouseMotion\b"),
    re.compile(r"\bInputEventScreenTouch\b"),
)

_ENGINE_INPUT_DISPATCH_PATTERNS = (
    re.compile(r"\bpush_input\s*\("),
    re.compile(r"\bparse_input_event\s*\("),
    re.compile(r"\bsimulate_(?:action|key|mouse)[A-Za-z0-9_]*\s*\("),
    re.compile(r"\b_input\s*\("),
    re.compile(r"\b_unhandled_input\s*\("),
)

_FIXTURE_SETUP_PATTERNS = (
    re.compile(r"\bfixture\b", re.IGNORECASE),
    re.compile(r"\b(?:setup|prepare|seed|before_test|load_scene|auto_free|add_child)\w*\s*\("),
    re.compile(r"\bpreload\s*\("),
)

_FORBIDDEN_BACKDOOR_MASKED_PATTERNS = (
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*ForTest\s*\("),
    re.compile(r"\b[A-Za-z0-9_]*_for_test\s*\("),
    re.compile(r"\bfor_test_[A-Za-z0-9_]+\s*\("),
    re.compile(r"\.pressed\.emit\s*\("),
)

_FORBIDDEN_BACKDOOR_RAW_PATTERNS = (
    re.compile(r"""\.\s*call(?:_deferred)?\s*\(\s*["'][^"']*(?:ForTest|_for_test)["']"""),
    re.compile(r"""\bemit_signal\s*\(\s*["']pressed["']"""),
)

_GD_PRELOAD_RE = re.compile(r"""(?:preload|load)\s*\(\s*["']res://([^"']+\.gd)["']\s*\)""")
_CS_GETNODE_ASSIGN_RE = re.compile(
    r"""(?:(?:var|[A-Za-z_][A-Za-z0-9_<>.?]*)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*GetNode(?:OrNull)?(?:<[^>]+>)?\s*\(\s*"([^"]+)"\s*\)"""
)
_CS_VAR_PRESSED_ADD_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\?\.|\.)\s*Pressed\s*\+=\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_CS_VAR_CONNECT_PRESSED_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\?\.|\.)\s*Connect\s*\(\s*(?:BaseButton\.SignalName\.Pressed|"pressed"|StringName\(\s*"pressed"\s*\))\s*,\s*(?:Callable\.From\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)|new\s+Callable\s*\([^,]+,\s*(?:MethodName\.([A-Za-z_][A-Za-z0-9_]*)|"([A-Za-z_][A-Za-z0-9_]*)")\s*\))"""
)
_CS_INLINE_PRESSED_ADD_RE = re.compile(
    r"""GetNode(?:OrNull)?(?:<[^>]+>)?\s*\(\s*"([^"]+)"\s*\)\s*(?:\?\.|\.)\s*Pressed\s*\+=\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_CS_SELF_PRESSED_ADD_RE = re.compile(
    r"""(?<![A-Za-z0-9_.])(?:this\.)?Pressed\s*\+=\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_GD_GETNODE_ASSIGN_RE = re.compile(
    r"""(?:^|\n)\s*(?:@onready\s+)?(?:var\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=\s*(?:get_node(?:_or_null)?\s*\(\s*["']([^"']+)["']\s*\)|\$["']?([A-Za-z0-9_/]+)["']?|%["']?([A-Za-z0-9_/]+)["']?)"""
)
_GD_VAR_PRESSED_CONNECT_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\.pressed\.connect\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_GD_VAR_CONNECT_STR_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\.connect\s*\(\s*["']pressed["']\s*,\s*(?:Callable\s*\([^,]+,\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\)|([A-Za-z_][A-Za-z0-9_]*))"""
)
_GD_INLINE_PRESSED_CONNECT_RE = re.compile(
    r"""(?:\$["']?([A-Za-z0-9_/]+)["']?|%["']?([A-Za-z0-9_/]+)["']?|get_node(?:_or_null)?\s*\(\s*["']([^"']+)["']\s*\))\.pressed\.connect\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_GD_SELF_PRESSED_CONNECT_RE = re.compile(
    r"""(?<![A-Za-z0-9_.])(?:self\.)?pressed\.connect\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)"""
)
_CS_METHOD_DECL_RE = re.compile(
    r"""\b(?:public|private|protected|internal)\s+(?:(?:static|virtual|override|async|sealed|new)\s+)*[A-Za-z_][A-Za-z0-9_<>,.\[\]?]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("""
)
_GD_FUNC_DECL_RE = re.compile(r"""^\s*(?:static\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(""", re.MULTILINE)
_CS_HANDLER_PRESSED_RE = re.compile(r"\b(?:public|private|protected|internal)?\s*(?:async\s+)?void\s+(On[A-Za-z0-9_]*Pressed)\s*\(")
_GD_HANDLER_PRESSED_RE = re.compile(r"\bfunc\s+(_on_[A-Za-z0-9_]*pressed)\s*\(")
_BUTTON_NODE_TYPES = frozenset({"Button", "BaseButton", "TextureButton", "LinkButton", "CheckButton", "MenuButton"})
_EXT_RES_PATH_RE = re.compile(r"""\[ext_resource\b[^\]]*\bpath="res://([^"]+)\"""")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
_DOTNET_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?$")
_GODOT_VERSION_RE = re.compile(
    r"(?:\bgodot\b[^\r\n]*\d+\.\d+|^\d+\.\d+(?:\.\d+)?\.(?:stable|rc\d*|beta\d*|alpha\d*|dev\d*)\.(?:mono\.)?(?:official|custom_build)\b)",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _check_ancestors_no_reparse(path: Path) -> Path:
    abs_path = path.absolute()
    for ancestor in reversed((abs_path, *abs_path.parents)):
        inventory.no_reparse(ancestor)
    return abs_path


def _check_no_reparse_chain(root: Path, target: Path) -> None:
    root_abs = _check_ancestors_no_reparse(root)
    target_abs = target.absolute()
    try:
        rel_parts = target_abs.relative_to(root_abs).parts
    except ValueError as exc:
        raise ValueError(f"Path escapes repository: {target}") from exc
    current = root_abs
    for part in rel_parts:
        current = current / part
        if os.path.lexists(current):
            inventory.no_reparse(current)
    # Defense-in-depth containment check only AFTER every ancestor and component passed no_reparse.
    if not target_abs.resolve(strict=False).is_relative_to(root_abs.resolve(strict=False)):
        raise ValueError(f"Path resolves outside repository: {target}")


def _normalize_repo_rel(root: Path, raw: str, *, allow_logs: bool = False) -> tuple[Path, str]:
    """Validate repo-relative POSIX path via .absolute() + no_reparse + inventory.safe_input BEFORE resolve()."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Expected non-empty repository-relative path")
    root_abs = _check_ancestors_no_reparse(root)
    raw_s = raw.strip()
    cand = Path(raw_s)
    if cand.is_absolute():
        cand_abs = _check_ancestors_no_reparse(cand)
        try:
            rel_posix = cand_abs.relative_to(root_abs).as_posix()
        except ValueError:
            # Handle case-only drive-letter mismatch on Windows after both chains passed no_reparse.
            root_res = root_abs.resolve()
            cand_res = cand_abs.resolve(strict=False)
            if not cand_res.is_relative_to(root_res):
                raise ValueError(f"Path resolves outside repository: {raw}")
            rel_posix = cand_res.relative_to(root_res).as_posix()
        cleaned = rel_posix
    else:
        cleaned = raw_s.replace("\\", "/")
        while cleaned.startswith("./"):
            cleaned = cleaned.removeprefix("./")
    if not cleaned:
        raise ValueError("Expected non-empty repository-relative path")
    target = inventory.safe_input(root_abs, cleaned, allow_logs=allow_logs)
    _check_no_reparse_chain(root_abs, target)
    return target, cleaned


def _strip_comments(text: str, *, is_cs: bool, mask_strings: bool = False) -> str:
    """Strip C# (//, /* */) or GDScript (#) comments while respecting/optionally masking string literals."""
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if is_cs:
            # Verbatim string @"..."
            if ch == "@" and i + 1 < n and text[i + 1] == '"':
                out.append('""' if mask_strings else '@"')
                i += 2
                while i < n:
                    if text[i] == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            if not mask_strings:
                                out.append('""')
                            i += 2
                            continue
                        if not mask_strings:
                            out.append('"')
                        i += 1
                        break
                    if not mask_strings:
                        out.append(text[i])
                    elif text[i] == "\n":
                        out.append("\n")
                    i += 1
                continue
            # Regular string or char literal
            if ch in ('"', "'"):
                quote = ch
                out.append(quote)
                i += 1
                while i < n:
                    c = text[i]
                    if c == "\\" and i + 1 < n:
                        if not mask_strings:
                            out.append(text[i : i + 2])
                        i += 2
                        continue
                    if c == quote:
                        out.append(quote)
                        i += 1
                        break
                    if not mask_strings:
                        out.append(c)
                    elif c == "\n":
                        out.append("\n")
                    i += 1
                continue
            # Line comment //
            if ch == "/" and i + 1 < n and text[i + 1] == "/":
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
                continue
            # Block comment /* ... */
            if ch == "/" and i + 1 < n and text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    if text[i] == "\n":
                        out.append("\n")
                    i += 1
                i = min(n, i + 2)
                continue
            out.append(ch)
            i += 1
        else:
            # GDScript triple-quoted string """...""" or '''...'''
            if text[i : i + 3] in ('"""', "'''"):
                delim = text[i : i + 3]
                out.append('""' if mask_strings else delim)
                i += 3
                while i < n:
                    if text[i : i + 3] == delim:
                        if not mask_strings:
                            out.append(delim)
                        i += 3
                        break
                    if text[i] == "\\" and i + 1 < n:
                        if not mask_strings:
                            out.append(text[i : i + 2])
                        i += 2
                        continue
                    if not mask_strings:
                        out.append(text[i])
                    elif text[i] == "\n":
                        out.append("\n")
                    i += 1
                continue
            # GDScript single/double-quoted string
            if ch in ('"', "'"):
                quote = ch
                out.append(quote)
                i += 1
                while i < n:
                    c = text[i]
                    if c == "\\" and i + 1 < n:
                        if not mask_strings:
                            out.append(text[i : i + 2])
                        i += 2
                        continue
                    if c == quote:
                        out.append(quote)
                        i += 1
                        break
                    if not mask_strings:
                        out.append(c)
                    elif c == "\n":
                        out.append("\n")
                    i += 1
                continue
            # GDScript line comment #
            if ch == "#":
                i += 1
                while i < n and text[i] != "\n":
                    i += 1
                continue
            out.append(ch)
            i += 1
    return "".join(out)


def normalize_evidence_tier(kind: str, manifest_evidence_level: str | None) -> str:
    """Map runner kind and manifest evidence_level onto the canonical six evidence tiers."""
    k = str(kind or "").strip().lower()
    lvl = str(manifest_evidence_level or "").strip().lower()
    if k == "static-wiring" or lvl == "static-wiring":
        return "static-wiring"
    if k == "manual" or lvl == "manual":
        return "manual"
    if k == "dotnet":
        return "domain-xunit"
    if k == "gdunit":
        if lvl == "engine-input":
            return "engine-input"
        if lvl == "scene-method":
            return "scene-method"
        return "godot-gdunit"
    if k == "other_verification":
        return "other-verification"
    return lvl or k or "godot-gdunit"


def _is_protocol_fixture_bin(bin_path: str) -> bool:
    if not bin_path:
        return False
    low = bin_path.strip().lower()
    if low.endswith(_PROTOCOL_FIXTURE_EXTS):
        return True
    name = Path(bin_path).name.lower()
    return any(marker in name for marker in _PROTOCOL_FIXTURE_MARKERS)


def _resolve_executable(bin_path: str) -> str | None:
    if not bin_path or not bin_path.strip():
        return None
    raw = bin_path.strip()
    cand = Path(raw)
    if cand.is_file():
        return str(cand.resolve())
    found = shutil.which(raw)
    return str(Path(found).resolve()) if found else None


def _is_temp_or_fixture_path(resolved_exe: str) -> bool:
    low = resolved_exe.lower()
    if low.endswith(_PROTOCOL_FIXTURE_EXTS):
        return True
    p = Path(resolved_exe)
    name = p.name.lower()
    if any(marker in name for marker in _PROTOCOL_FIXTURE_MARKERS):
        return True
    parts_low = {part.lower() for part in p.parts}
    if parts_low & {"fixture", "fixtures", "fake", "mock", "stub", "harness"}:
        return True
    temp_roots = {tempfile.gettempdir(), os.environ.get("TEMP", ""), os.environ.get("TMP", "")}
    for tr in temp_roots:
        if not tr:
            continue
        try:
            if p.resolve().is_relative_to(Path(tr).resolve()):
                return True
        except OSError:
            continue
    return False


def _probe_binary_version(resolved_exe: str | None, *, tool: str, is_fixture: bool) -> tuple[str, bool]:
    if is_fixture:
        return "protocol_fixture", False
    if not resolved_exe:
        return "unavailable", False
    try:
        proc = subprocess.run(
            [resolved_exe, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        lines = [ln.strip() for ln in (proc.stdout or proc.stderr or "").splitlines() if ln.strip()]
        if proc.returncode != 0 or not lines:
            return "unavailable", False
        first = lines[0]
        if tool == "godot":
            genuine = bool(_GODOT_VERSION_RE.search(first))
            return first, genuine
        if tool == "dotnet":
            genuine = bool(_DOTNET_VERSION_RE.match(first))
            return first, genuine
        return first, True
    except (OSError, subprocess.SubprocessError):
        return "unavailable", False


def probe_environment(
    *,
    dotnet_bin: str,
    godot_bin: str,
    explicit_protocol_fixture: bool,
    needs_dotnet: bool = True,
    needs_godot: bool = True,
) -> dict[str, Any]:
    """Collect honest Windows, Python, dotnet, and Godot version & fixture authenticity metadata."""
    dotnet_resolved = _resolve_executable(dotnet_bin)
    godot_resolved = _resolve_executable(godot_bin)

    dotnet_fixture = (
        explicit_protocol_fixture
        or _is_protocol_fixture_bin(dotnet_bin)
        or (bool(dotnet_resolved) and _is_temp_or_fixture_path(dotnet_resolved))
    )
    godot_fixture = (
        explicit_protocol_fixture
        or _is_protocol_fixture_bin(godot_bin)
        or (bool(godot_resolved) and _is_temp_or_fixture_path(godot_resolved))
    )

    if not godot_bin:
        godot_bin_kind = "unavailable"
        godot_version = "unavailable"
        godot_genuine = False
    elif godot_fixture:
        godot_bin_kind = "protocol_fixture"
        godot_version = "protocol_fixture"
        godot_genuine = False
    elif not godot_resolved:
        godot_bin_kind = "unavailable"
        godot_version = "unavailable"
        godot_genuine = False
    else:
        godot_version, godot_genuine = _probe_binary_version(godot_resolved, tool="godot", is_fixture=False)
        godot_bin_kind = "real_godot" if godot_genuine else "protocol_fixture"

    dotnet_version, dotnet_genuine = _probe_binary_version(dotnet_resolved, tool="dotnet", is_fixture=dotnet_fixture)
    dotnet_non_genuine = dotnet_fixture or not dotnet_resolved or not dotnet_genuine
    godot_non_genuine = godot_fixture or not godot_resolved or not godot_genuine

    protocol_fixture_only = bool(
        explicit_protocol_fixture
        or (needs_dotnet and dotnet_non_genuine)
        or (needs_godot and godot_non_genuine)
        or (not needs_dotnet and not needs_godot and (dotnet_fixture or godot_fixture))
    )
    windows_version = "non-windows"
    if hasattr(sys, "getwindowsversion"):
        wv = sys.getwindowsversion()
        windows_version = f"Windows-{wv.major}.{wv.minor}.{wv.build}"
    exclusions: list[str] = []
    if protocol_fixture_only:
        exclusions.append(
            "protocol_fixture_only: runner binary is a protocol fixture or unverified executable; proves adapter/report parsing only, not real Godot gameplay"
        )
    if godot_bin_kind == "unavailable" and needs_godot:
        exclusions.append("godot_bin_unavailable: real Godot runtime binary was not available")
    return {
        "os_platform": platform.platform(),
        "windows_version": windows_version,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "dotnet_bin": dotnet_bin,
        "dotnet_resolved_bin": dotnet_resolved or "",
        "dotnet_version": dotnet_version,
        "dotnet_genuine": dotnet_genuine,
        "godot_bin": godot_bin or "",
        "godot_resolved_bin": godot_resolved or "",
        "godot_version": godot_version,
        "godot_bin_kind": godot_bin_kind,
        "godot_genuine": godot_genuine,
        "protocol_fixture_only": protocol_fixture_only,
        "evidence_authenticity": "protocol_fixture" if protocol_fixture_only else "real_runtime",
        "unverified_exclusions": exclusions,
    }


def inspect_gdunit_input_authenticity(
    snapshot_root: Path,
    test_path: str,
    evidence_level: str,
) -> dict[str, Any]:
    """Inspect a GdUnit4 .gd test (and preloaded helpers) for real engine input vs fixture/backdoor."""
    tier = normalize_evidence_tier("gdunit", evidence_level)
    target = safe_path(snapshot_root, test_path)
    if not target.is_file():
        return {
            "checked": True,
            "evidence_tier": tier,
            "valid": False,
            "player_action_input_detected": False,
            "fixture_setup_detected": False,
            "forbidden_backdoor_detected": False,
            "backdoor_matches": [],
            "input_markers": [],
            "fixture_markers": [],
            "inspected_files": [test_path],
            "reason": "test_file_missing_in_snapshot",
        }

    texts: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    queue = [test_path]
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        try:
            fp = safe_path(snapshot_root, rel)
        except ValueError:
            continue
        if not fp.is_file():
            continue
        raw = fp.read_text(encoding="utf-8", errors="replace")
        no_comments = _strip_comments(raw, is_cs=False, mask_strings=False)
        masked = _strip_comments(raw, is_cs=False, mask_strings=True)
        texts.append((rel, no_comments, masked))
        for m in _GD_PRELOAD_RE.finditer(no_comments):
            helper_rel = m.group(1)
            if helper_rel.startswith("Tests.Godot/") and helper_rel not in seen:
                queue.append(helper_rel)
            elif not helper_rel.startswith("Game.") and (snapshot_root / "Tests.Godot" / helper_rel).is_file():
                cand = "Tests.Godot/" + helper_rel
                if cand not in seen:
                    queue.append(cand)

    construct_markers: list[str] = []
    dispatch_markers: list[str] = []
    fixture_markers: list[str] = []
    backdoor_matches: list[str] = []
    for rel, no_comments, masked in texts:
        for pat in _ENGINE_INPUT_CONSTRUCT_PATTERNS:
            for m in pat.finditer(masked):
                marker = f"{rel}:{m.group(0).strip()}"
                if marker not in construct_markers:
                    construct_markers.append(marker)
        for pat in _ENGINE_INPUT_DISPATCH_PATTERNS:
            for m in pat.finditer(masked):
                marker = f"{rel}:{m.group(0).strip()}"
                if marker not in dispatch_markers:
                    dispatch_markers.append(marker)
        for pat in _FIXTURE_SETUP_PATTERNS:
            for m in pat.finditer(masked):
                marker = f"{rel}:{m.group(0).strip()}"
                if marker not in fixture_markers:
                    fixture_markers.append(marker)
        for pat in _FORBIDDEN_BACKDOOR_MASKED_PATTERNS:
            for m in pat.finditer(masked):
                marker = f"{rel}:{m.group(0).strip()}"
                if marker not in backdoor_matches:
                    backdoor_matches.append(marker)
        for pat in _FORBIDDEN_BACKDOOR_RAW_PATTERNS:
            for m in pat.finditer(no_comments):
                marker = f"{rel}:{m.group(0).strip()}"
                if marker not in backdoor_matches:
                    backdoor_matches.append(marker)

    input_markers = construct_markers + [m for m in dispatch_markers if m not in construct_markers]
    player_action = bool(construct_markers) and bool(dispatch_markers)
    fixture_setup = bool(fixture_markers)
    forbidden = bool(backdoor_matches)

    valid = True
    reason = "verified"
    if forbidden:
        valid = False
        reason = "forbidden_test_backdoor_or_signal_spoof_detected"
    elif tier == "engine-input" and not player_action:
        valid = False
        reason = "engine_input_missing_real_player_input_event"

    return {
        "checked": True,
        "evidence_tier": tier,
        "valid": valid,
        "player_action_input_detected": player_action,
        "input_construct_detected": bool(construct_markers),
        "input_dispatch_detected": bool(dispatch_markers),
        "fixture_setup_detected": fixture_setup,
        "forbidden_backdoor_detected": forbidden,
        "backdoor_matches": backdoor_matches,
        "input_markers": input_markers,
        "fixture_markers": fixture_markers,
        "inspected_files": [rel for rel, _, _ in texts],
        "reason": reason,
    }


def _collect_scoped_wiring_targets(
    snapshot_root: Path,
    scope_doc: dict[str, Any],
    manifest_doc: dict[str, Any],
    selected_flow_ids: set[str],
    *,
    is_superset: bool = False,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Collect .tscn scenes, .cs/.gd adapters, and Stage-4 binding objects strictly in scope."""
    scenes: set[str] = set()
    adapters: set[str] = set()
    binding_objects: list[dict[str, Any]] = []

    boundary = scope_doc.get("delivery_boundary") or {}
    in_scope_flows: set[str] = set(selected_flow_ids) | set(boundary.get("in_scope_flow_ids") or [])
    in_scope_tasks: set[int] = {t for t in (boundary.get("in_scope_task_ids") or []) if type(t) is int and t >= 1}
    in_scope_plans: set[str] = set(boundary.get("in_scope_plan_ids") or [])
    for obl in scope_doc.get("obligations") or []:
        if not isinstance(obl, dict) or obl.get("tier") not in {"existing_required", "current_new"}:
            continue
        in_scope_flows.update(f for f in (obl.get("flow_ids") or []) if isinstance(f, str) and f)
        in_scope_tasks.update(t for t in (obl.get("task_ids") or []) if type(t) is int and t >= 1)
        owner_pid = (obl.get("semantic_owner") or {}).get("owner_plan_id")
        if isinstance(owner_pid, str) and owner_pid:
            in_scope_plans.add(owner_pid)

    for flow in manifest_doc.get("flows") or []:
        if not isinstance(flow, dict):
            continue
        fid = flow.get("id")
        if not is_superset and fid not in selected_flow_ids:
            continue
        if is_superset:
            if isinstance(fid, str) and fid:
                in_scope_flows.add(fid)
            in_scope_tasks.update(t for t in (flow.get("task_ids") or []) if type(t) is int and t >= 1)
        for sp in flow.get("source_paths") or []:
            if isinstance(sp, str):
                if sp.endswith(".tscn"):
                    scenes.add(sp)
                elif sp.startswith("Game.Godot/") and sp.endswith((".cs", ".gd")):
                    adapters.add(sp)

    for obl in scope_doc.get("obligations") or []:
        if not isinstance(obl, dict):
            continue
        if obl.get("tier") not in {"existing_required", "current_new"}:
            continue
        for ref in obl.get("source_refs") or []:
            if isinstance(ref, str):
                if ref.endswith(".tscn"):
                    scenes.add(ref)
                elif ref.startswith("Game.Godot/") and ref.endswith((".cs", ".gd")):
                    adapters.add(ref)
        for ref in obl.get("implementation_refs") or []:
            if isinstance(ref, str):
                if ref.endswith(".tscn"):
                    scenes.add(ref)
                elif ref.startswith("Game.Godot/") and ref.endswith((".cs", ".gd")):
                    adapters.add(ref)

    # Load referenced Stage-5 bindings from snapshot, filtering strictly to in-scope flows/tasks!
    for bref in (scope_doc.get("authority_refs") or {}).get("binding_refs") or []:
        bpath = bref.get("path") if isinstance(bref, dict) else None
        if not isinstance(bpath, str) or not bpath:
            continue
        try:
            fp = safe_path(snapshot_root, bpath)
        except ValueError:
            continue
        if not fp.is_file():
            continue
        try:
            bdoc = codec.strict_json_loads(fp.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        b_plan_id = bdoc.get("plan_id")
        b_scoped_tasks: set[int] = set()
        for tm in bdoc.get("task_mappings") or []:
            if not isinstance(tm, dict):
                continue
            tid = tm.get("task_id")
            tm_flows = set(tm.get("flow_ids") or [])
            if (type(tid) is int and tid in in_scope_tasks) or bool(tm_flows & in_scope_flows):
                if type(tid) is int:
                    b_scoped_tasks.add(tid)
        effective_tasks = in_scope_tasks | b_scoped_tasks
        binding_in_scope = bool(b_scoped_tasks) or (isinstance(b_plan_id, str) and b_plan_id in in_scope_plans)
        if not binding_in_scope:
            continue
        for obj in bdoc.get("implementation_objects") or []:
            if not isinstance(obj, dict) or obj.get("availability") != "existing":
                continue
            resp_tasks = {t for t in (obj.get("responsible_task_ids") or []) if type(t) is int and t >= 1}
            obj_flows = {f for f in (obj.get("flow_ids") or []) if isinstance(f, str) and f}
            if resp_tasks or obj_flows:
                if not (resp_tasks & effective_tasks) and not (obj_flows & in_scope_flows):
                    continue
            binding_objects.append(obj)
            tref = obj.get("target_ref")
            if isinstance(tref, dict):
                for fitem in tref.get("files") or []:
                    fpath = fitem.get("path") if isinstance(fitem, dict) else None
                    if isinstance(fpath, str):
                        if fpath.endswith(".tscn"):
                            scenes.add(fpath)
                        elif fpath.startswith("Game.Godot/") and fpath.endswith((".cs", ".gd")):
                            adapters.add(fpath)

    return sorted(scenes), sorted(adapters), binding_objects


def _resolve_button_target(raw_ref: str, owner_path: str, button_nodes: list[str]) -> str | None:
    cleaned = raw_ref.strip().lstrip("%$")
    if not cleaned:
        return None
    candidates: list[str] = []
    if owner_path in {"", "."}:
        candidates.append(cleaned)
    else:
        candidates.append(f"{owner_path}/{cleaned}")
        candidates.append(cleaned)
    for cand in candidates:
        if cand in button_nodes:
            return cand
    # Match unique node name (e.g. %ClaimButton) or trailing path segment if unambiguous.
    tail_matches = [bp for bp in button_nodes if bp == cleaned or bp.endswith("/" + cleaned)]
    if len(tail_matches) == 1:
        return tail_matches[0]
    return None


def inspect_scoped_static_wiring(
    snapshot_root: Path,
    *,
    scene_paths: list[str],
    adapter_paths: list[str],
    binding_objects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run static .tscn/adapter/signal/node/type wiring inspection in the isolated snapshot."""
    if not scene_paths and not adapter_paths:
        return {
            "applicable": False,
            "wiring_static_ok": True,
            "scenes_inspected": [],
            "adapters_inspected": [],
            "findings": [],
        }

    base = ch7_slice.inspect_scene_and_adapter_wiring(
        snapshot_root,
        scene_paths=scene_paths,
        adapter_paths=adapter_paths,
        binding_objects=binding_objects,
    )
    findings = list(base.get("findings") or [])
    parsed_scenes = base.get("parsed_scenes") or {}

    for srel in base.get("scenes_inspected") or []:
        scene_file = safe_path(snapshot_root, srel)
        if not scene_file.is_file():
            continue
        scene_text = scene_file.read_text(encoding="utf-8", errors="replace")
        # 1. Verify all [ext_resource path="res://..."] targets exist in snapshot.
        for m in _EXT_RES_PATH_RE.finditer(scene_text):
            res_rel = m.group(1)
            try:
                res_file = safe_path(snapshot_root, res_rel)
            except ValueError:
                findings.append({
                    "failure_kind": "unsafe_ext_resource",
                    "status": "failed",
                    "scene_path": srel,
                    "adapter_path": res_rel,
                    "node_path": None,
                    "message": f"Scene {srel} references unsafe ext_resource res://{res_rel}",
                    "return_stage": "4",
                })
                continue
            if not res_file.is_file():
                findings.append({
                    "failure_kind": "missing_ext_resource",
                    "status": "failed",
                    "scene_path": srel,
                    "adapter_path": res_rel,
                    "node_path": None,
                    "message": f"Scene {srel} references missing ext_resource res://{res_rel}",
                    "return_stage": "4",
                })

        parsed = parsed_scenes.get(srel)
        if not isinstance(parsed, dict):
            continue
        nodes = parsed.get("nodes") or {}
        connections = parsed.get("connections") or []
        button_nodes = [
            npath for npath, ninfo in nodes.items()
            if ninfo.get("type") in _BUTTON_NODE_TYPES
        ]
        pressed_sources = {
            conn.get("from", "") for conn in connections if conn.get("signal") == "pressed"
        }
        connected_methods = {conn.get("method", "") for conn in connections if conn.get("method")}
        programmatically_connected_buttons: set[str] = set()
        script_methods_by_node: dict[str, tuple[str, set[str]]] = {}
        declared_pressed_handlers: list[tuple[str, str]] = []

        # Collect attached scripts, declared methods, and PER-BUTTON programmatic pressed bindings.
        for npath, ninfo in nodes.items():
            sres = ninfo.get("script_res") or ""
            if not sres:
                continue
            script_rel = sres.removeprefix("res://")
            try:
                sfile = safe_path(snapshot_root, script_rel)
            except ValueError:
                continue
            if not sfile.is_file():
                continue
            raw_stext = sfile.read_text(encoding="utf-8", errors="replace")
            is_cs = script_rel.endswith(".cs")
            no_comments = _strip_comments(raw_stext, is_cs=is_cs, mask_strings=False)
            masked = _strip_comments(raw_stext, is_cs=is_cs, mask_strings=True)

            if is_cs:
                methods = set(_CS_METHOD_DECL_RE.findall(masked))
                script_methods_by_node[npath] = (script_rel, methods)
                for mh in _CS_HANDLER_PRESSED_RE.finditer(masked):
                    declared_pressed_handlers.append((script_rel, mh.group(1)))
                var_to_node: dict[str, str] = {}
                for mv in _CS_GETNODE_ASSIGN_RE.finditer(no_comments):
                    resolved_btn = _resolve_button_target(mv.group(2), npath, button_nodes)
                    if resolved_btn:
                        var_to_node[mv.group(1)] = resolved_btn
                # Direct inline GetNode<Button>("...").Pressed += Handler
                for mi in _CS_INLINE_PRESSED_ADD_RE.finditer(no_comments):
                    resolved_btn = _resolve_button_target(mi.group(1), npath, button_nodes)
                    handler = mi.group(2)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler:
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                # Variable btn.Pressed += Handler
                for mp in _CS_VAR_PRESSED_ADD_RE.finditer(masked):
                    var_name, handler = mp.group(1), mp.group(2)
                    resolved_btn = var_to_node.get(var_name)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler:
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                # Variable btn.Connect(BaseButton.SignalName.Pressed, ...)
                for mc in _CS_VAR_CONNECT_PRESSED_RE.finditer(no_comments):
                    var_name = mc.group(1)
                    handler = mc.group(2) or mc.group(3) or mc.group(4) or ""
                    resolved_btn = var_to_node.get(var_name)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler:
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                # Self-attached script on a Button node: Pressed += Handler
                if npath in button_nodes:
                    for ms in _CS_SELF_PRESSED_ADD_RE.finditer(masked):
                        handler = ms.group(1)
                        programmatically_connected_buttons.add(npath)
                        if handler:
                            connected_methods.add(handler)
                            if handler not in methods:
                                findings.append({
                                    "failure_kind": "missing_signal_handler",
                                    "status": "failed",
                                    "scene_path": srel,
                                    "adapter_path": script_rel,
                                    "node_path": npath,
                                    "message": f"Self pressed handler '{handler}' is not declared in {script_rel}",
                                    "return_stage": "4",
                                })
            elif script_rel.endswith(".gd"):
                methods = set(_GD_FUNC_DECL_RE.findall(masked))
                script_methods_by_node[npath] = (script_rel, methods)
                for mh in _GD_HANDLER_PRESSED_RE.finditer(masked):
                    declared_pressed_handlers.append((script_rel, mh.group(1)))
                var_to_node = {}
                for mv in _GD_GETNODE_ASSIGN_RE.finditer(no_comments):
                    raw_target = mv.group(2) or mv.group(3) or mv.group(4) or ""
                    resolved_btn = _resolve_button_target(raw_target, npath, button_nodes)
                    if resolved_btn:
                        var_to_node[mv.group(1)] = resolved_btn
                for mi in _GD_INLINE_PRESSED_CONNECT_RE.finditer(no_comments):
                    raw_target = mi.group(1) or mi.group(2) or mi.group(3) or ""
                    handler = mi.group(4)
                    resolved_btn = _resolve_button_target(raw_target, npath, button_nodes)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler and handler != "func":
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                for mp in _GD_VAR_PRESSED_CONNECT_RE.finditer(masked):
                    var_name, handler = mp.group(1), mp.group(2)
                    resolved_btn = var_to_node.get(var_name)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler and handler != "func":
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                for mc in _GD_VAR_CONNECT_STR_RE.finditer(no_comments):
                    var_name = mc.group(1)
                    handler = mc.group(2) or mc.group(3) or ""
                    resolved_btn = var_to_node.get(var_name)
                    if resolved_btn:
                        programmatically_connected_buttons.add(resolved_btn)
                    if handler and handler != "func":
                        connected_methods.add(handler)
                        if handler not in methods:
                            findings.append({
                                "failure_kind": "missing_signal_handler",
                                "status": "failed",
                                "scene_path": srel,
                                "adapter_path": script_rel,
                                "node_path": resolved_btn or npath,
                                "message": f"Programmatic pressed handler '{handler}' is not declared in {script_rel}",
                                "return_stage": "4",
                            })
                if npath in button_nodes:
                    for ms in _GD_SELF_PRESSED_CONNECT_RE.finditer(masked):
                        handler = ms.group(1)
                        programmatically_connected_buttons.add(npath)
                        if handler and handler != "func":
                            connected_methods.add(handler)
                            if handler not in methods:
                                findings.append({
                                    "failure_kind": "missing_signal_handler",
                                    "status": "failed",
                                    "scene_path": srel,
                                    "adapter_path": script_rel,
                                    "node_path": npath,
                                    "message": f"Self pressed handler '{handler}' is not declared in {script_rel}",
                                    "return_stage": "4",
                                })

        # 2. Verify EVERY interactive Button node individually has a pressed connection (in .tscn or programmatic).
        for bpath in button_nodes:
            if bpath not in pressed_sources and bpath not in programmatically_connected_buttons:
                findings.append({
                    "failure_kind": "disconnected_signal_binding",
                    "status": "failed",
                    "scene_path": srel,
                    "adapter_path": None,
                    "node_path": bpath,
                    "message": (
                        f"Interactive button node '{bpath}' in {srel} has no 'pressed' signal connection "
                        "in .tscn or attached adapter script"
                    ),
                    "return_stage": "4",
                })

        # 3. Verify pressed handler methods declared in attached scripts are wired if buttons exist.
        if button_nodes:
            for script_rel, handler in declared_pressed_handlers:
                if handler not in connected_methods:
                    findings.append({
                        "failure_kind": "disconnected_signal_binding",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": script_rel,
                        "node_path": ".",
                        "message": (
                            f"Pressed handler '{handler}' in {script_rel} is not connected by any "
                            f"[connection] in {srel} or programmatic subscription"
                        ),
                        "return_stage": "4",
                    })

    return {
        "applicable": True,
        "wiring_static_ok": len(findings) == 0,
        "scenes_inspected": list(base.get("scenes_inspected") or []),
        "adapters_inspected": list(base.get("adapters_inspected") or []),
        "findings": findings,
    }


def _validate_manifest_for_scope(
    snapshot_root: Path,
    manifest_doc: dict[str, Any],
    scope_doc: dict[str, Any],
    manifest_rel: str,
    *,
    is_superset: bool = False,
) -> tuple[list[str], str]:
    """Validate target manifest via full _mvg_manifest.validate_manifest + verify scheduled tests exist."""
    errors: list[str] = []
    reason_code = "ok"
    if not isinstance(manifest_doc, dict):
        return ["Manifest must be a JSON object"], "schema_validation_failed"
    if manifest_doc.get("schema_version") != "newrouge.mvg-integration.v1":
        return ["Unsupported manifest schema_version"], "unknown_schema"

    base_errors = validate_manifest(snapshot_root, manifest_doc, executable=False)
    errors.extend(base_errors)

    tests = manifest_doc.get("tests") or []
    test_by_id: dict[str, dict[str, Any]] = {
        row["id"]: row for row in tests
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    # Verify every executable dotnet/gdunit test declared by VerificationScope is present and implemented.
    scope_exec = (scope_doc.get("execution_plan") or {}).get("executable_tests") or []
    for item in scope_exec:
        if not isinstance(item, dict) or item.get("kind") not in {"dotnet", "gdunit"}:
            continue
        tid = item.get("test_id")
        if tid not in test_by_id:
            errors.append(f"Manifest {manifest_rel} is missing scope-required test: {tid}")
            reason_code = "missing_required_test"
            continue
        mrow = test_by_id[tid]
        if mrow.get("state") != "implemented":
            errors.append(f"Scope-required test {tid} is not implemented in {manifest_rel} (state={mrow.get('state')})")
            reason_code = "missing_required_test"
        elif not safe_path(snapshot_root, mrow["path"]).is_file():
            errors.append(f"Scope-required test file missing in snapshot: {mrow['path']}")
            reason_code = "missing_required_test"
        else:
            # Verify descriptor compatibility between VerificationScope and manifest (fail closed on conflict!).
            desc_diffs: list[str] = []
            if str(item.get("kind") or "") != str(mrow.get("kind") or ""):
                desc_diffs.append(f"kind({item.get('kind')}!={mrow.get('kind')})")
            item_path = str(item.get("path") or "").replace("\\", "/")
            mrow_path = str(mrow.get("path") or "").replace("\\", "/")
            if item_path and item_path != mrow_path:
                desc_diffs.append(f"path({item_path}!={mrow_path})")
            item_sel = str(item.get("selector") or "")
            mrow_sel = str(mrow.get("selector") or "")
            if item_sel != mrow_sel:
                desc_diffs.append(f"selector({item_sel}!={mrow_sel})")
            if item.get("min_tests") is not None and int(item["min_tests"]) != int(mrow.get("min_tests") or 1):
                desc_diffs.append(f"min_tests({item.get('min_tests')}!={mrow.get('min_tests')})")
            item_lvl = item.get("evidence_level")
            mrow_lvl = mrow.get("evidence_level")
            if item_lvl and mrow_lvl:
                norm_item_lvl = normalize_evidence_tier(str(item.get("kind") or ""), str(item_lvl))
                norm_mrow_lvl = normalize_evidence_tier(str(mrow.get("kind") or ""), str(mrow_lvl))
                if norm_item_lvl != norm_mrow_lvl:
                    desc_diffs.append(f"evidence_level({item_lvl}!={mrow_lvl})")
            if desc_diffs:
                errors.append(
                    f"Descriptor mismatch between VerificationScope and manifest for test {tid}: {', '.join(desc_diffs)}"
                )
                reason_code = "descriptor_mismatch"

    # When running conservative_superset, verify all implemented extra tests exist in snapshot too.
    if is_superset:
        for mrow in tests:
            if not isinstance(mrow, dict) or mrow.get("state") != "implemented":
                continue
            tpath = mrow.get("path")
            if not isinstance(tpath, str) or not tpath:
                continue
            try:
                if not safe_path(snapshot_root, tpath).is_file():
                    errors.append(f"Superset test file missing in snapshot: {tpath}")
                    reason_code = "missing_required_test"
            except ValueError as exc:
                errors.append(f"{mrow.get('id')}: unsafe path ({exc})")

    if errors and reason_code == "ok":
        reason_code = "schema_validation_failed"
    return errors, reason_code


def _scope_manifest_map(scope_doc: dict[str, Any]) -> dict[str, str]:
    """Return {manifest_rel_path: declared_manifest_sha256} from VerificationScope authority_refs."""
    auth = scope_doc.get("authority_refs") or {}
    result: dict[str, str] = {}
    for bucket in ("manifest_refs", "cumulative_baseline_refs"):
        for item in auth.get(bucket) or []:
            if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("manifest_sha256"), str):
                result[item["path"]] = item["manifest_sha256"]
    return result


def _compute_business_scope_keys(
    scope_doc: dict[str, Any],
    manifest_rel: str,
    *,
    manifest_doc: dict[str, Any] | None = None,
    is_superset: bool = False,
) -> tuple[str, ...]:
    """Compute exact business scope lease keys (including obligation tasks & superset resources) without WRITER_SCOPE."""
    boundary = scope_doc.get("delivery_boundary") or {}
    plan_ids = set(boundary.get("in_scope_plan_ids") or [])
    flow_ids = set(boundary.get("in_scope_flow_ids") or [])
    task_ids = set(boundary.get("in_scope_task_ids") or [])
    req_ids = set(boundary.get("in_scope_requirement_ids") or [])
    target_paths = {manifest_rel}
    for obl in scope_doc.get("obligations") or []:
        if not isinstance(obl, dict) or obl.get("tier") not in {"existing_required", "current_new"}:
            continue
        owner = (obl.get("semantic_owner") or {}).get("owner_plan_id")
        if isinstance(owner, str) and owner:
            plan_ids.add(owner)
        for fid in obl.get("flow_ids") or []:
            if isinstance(fid, str) and fid:
                flow_ids.add(fid)
        for rid in obl.get("requirement_ids") or []:
            if isinstance(rid, str) and rid:
                req_ids.add(rid)
        for tid in obl.get("task_ids") or []:
            if type(tid) is int and tid >= 1:
                task_ids.add(tid)
    for item in (scope_doc.get("execution_plan") or {}).get("executable_tests") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]:
            target_paths.add(item["path"])

    effective_superset = bool(
        is_superset or (scope_doc.get("impact_binding") or {}).get("conservative_expanded")
    )
    if effective_superset and isinstance(manifest_doc, dict):
        for flow in manifest_doc.get("flows") or []:
            if not isinstance(flow, dict):
                continue
            fid = flow.get("id")
            if isinstance(fid, str) and fid:
                flow_ids.add(fid)
            for tid in flow.get("task_ids") or []:
                if type(tid) is int and tid >= 1:
                    task_ids.add(tid)
            for rid in flow.get("requirement_ids") or []:
                if isinstance(rid, str) and rid:
                    req_ids.add(rid)
            for sp in flow.get("source_paths") or []:
                if isinstance(sp, str) and sp:
                    target_paths.add(sp)
            for edge in flow.get("handoffs") or []:
                if isinstance(edge, dict) and isinstance(edge.get("contract_ref"), str) and edge["contract_ref"]:
                    target_paths.add(edge["contract_ref"])
        for t in manifest_doc.get("tests") or []:
            if isinstance(t, dict) and t.get("state") == "implemented" and isinstance(t.get("path"), str) and t["path"]:
                target_paths.add(t["path"])

    def _valid_biz(values: set[str]) -> list[str]:
        out = []
        for v in sorted(values):
            try:
                out.append(codec.validate_business_id(v))
            except codec.CodecError:
                continue
        return out

    valid_tasks = []
    for t in sorted(task_ids):
        if type(t) is int and t >= 1:
            valid_tasks.append(t)

    return op_scope.resource_scopes(
        target_paths=sorted(target_paths),
        plan_ids=_valid_biz(plan_ids),
        requirement_ids=_valid_biz(req_ids),
        flow_ids=_valid_biz(flow_ids),
        task_ids=valid_tasks,
    )


def _check_durable_stop_loss(root: Path, task_ids: list[int]) -> dict[str, Any]:
    """Check durable cross-date stop-loss signals for all in-scope tasks."""
    triggered_tasks: list[int] = []
    signals: list[dict[str, Any]] = []
    for tid in sorted(set(task_ids)):
        scan = ch6_recovery.scan_durable_recovery_signals(root, tid)
        if scan.get("has_active_stop_loss"):
            triggered_tasks.append(tid)
            signals.append({
                "task_id": tid,
                "blocked_by": scan.get("blocked_by", ""),
                "blocking_reason": scan.get("blocking_reason", ""),
                "blocking_run_dir": scan.get("blocking_run_dir", ""),
                "active_stop_loss_signals": list(scan.get("active_stop_loss_signals") or []),
            })
    return {
        "triggered": bool(triggered_tasks),
        "source": "durable_task_signal" if triggered_tasks else None,
        "signals": signals,
        "task_ids": triggered_tasks,
        "failed_prerequisite_id": None,
        "skipped_test_ids": [],
    }


def _seal_receipt(receipt: dict[str, Any]) -> None:
    body = {k: v for k, v in receipt.items() if k not in _VOLATILE_RECEIPT_FIELDS}
    receipt["receipt_id"] = codec.canonical_digest(body)


def _build_evidence_tiers_summary(
    executed_tests: list[dict[str, Any]],
    not_run: list[dict[str, Any]],
    manual_obligations: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    tiers: dict[str, dict[str, int]] = {
        name: {"count": 0, "passed": 0, "failed": 0, "not_run": 0, "pending": 0}
        for name in SIX_EVIDENCE_TIERS
    }

    def _tier_names(item: dict[str, Any]) -> list[str]:
        primary = item.get("evidence_level") or "godot-gdunit"
        return [primary]

    for item in executed_tests:
        for t in _tier_names(item):
            bucket = tiers.setdefault(t, {"count": 0, "passed": 0, "failed": 0, "not_run": 0, "pending": 0})
            bucket["count"] += 1
            if item.get("status") == "passed":
                bucket["passed"] += 1
            else:
                bucket["failed"] += 1
    for item in not_run:
        for t in _tier_names(item):
            bucket = tiers.setdefault(t, {"count": 0, "passed": 0, "failed": 0, "not_run": 0, "pending": 0})
            bucket["count"] += 1
            bucket["not_run"] += 1
            if item.get("blocking_current_delivery"):
                bucket["pending"] += 1
    for _m in manual_obligations:
        tiers["manual"]["count"] += 1
        tiers["manual"]["pending"] += 1
    return tiers


def _run_other_verification_script(
    snapshot_root: Path,
    item: dict[str, Any],
    out: Path,
    deadline: float,
    env: dict[str, str],
) -> dict[str, Any]:
    if (out / "command.json").exists() or (out / "console.log").exists():
        raise FileExistsError(f"Output directory already contains execution artifacts: {out}")
    out.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    started_mono = time.monotonic()
    script_rel = str(item.get("path") or "")
    target = safe_path(snapshot_root, script_rel)
    log_path = out / "console.log"
    if not target.is_file():
        log_path.write_text(f"Missing other_verification script: {script_rel}\n", encoding="utf-8")
        command: list[str] = []
        rc = 127
    elif script_rel.lower().endswith(".py"):
        command = [sys.executable, "-B", str(target)]
        rc = run_child(command, snapshot_root, log_path, deadline - time.monotonic(), env)
    elif script_rel.lower().endswith(".ps1"):
        command = ["pwsh", "-NoProfile", "-File", str(target)]
        rc = run_child(command, snapshot_root, log_path, deadline - time.monotonic(), env)
    else:
        log_path.write_text(f"Unsupported other_verification script type: {script_rel}\n", encoding="utf-8")
        command = []
        rc = 127
    finished_at = _now()
    elapsed_seconds = round(max(0.0, time.monotonic() - started_mono), 4)
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    non_empty_output = bool(log_text.strip())
    cmd_rec = out / "command.json"
    _write_json(cmd_rec, {
        "id": item["test_id"],
        "kind": "other_verification",
        "evidence_level": "other-verification",
        "cwd": str(snapshot_root),
        "command": command,
        "exit_code": rc,
        "non_empty_output": non_empty_output,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed_seconds,
        "log_path": str(log_path),
        "report_paths": [str(log_path)] if non_empty_output else [],
    })
    passed = rc == 0 and bool(command) and non_empty_output
    reason = (
        "verified" if passed
        else ("other_verification_empty_output" if (rc == 0 and bool(command) and not non_empty_output)
              else "other_verification_script_failed")
    )
    return {
        "id": item["test_id"],
        "obligation_id": item.get("obligation_id"),
        "tier": item.get("tier", "current_new"),
        "kind": "other_verification",
        "evidence_level": "other-verification",
        "manifest_evidence_level": "other-verification",
        "command": command,
        "command_record": str(cmd_rec),
        "exit_code": rc,
        "status": "passed" if passed else "failed",
        "passed_cases": 1 if passed else 0,
        "failed_cases": 0 if passed else 1,
        "skipped_cases": 0,
        "log_path": str(log_path),
        "report_paths": [str(log_path)] if non_empty_output else [],
        "input_authenticity": {"checked": False, "valid": True, "reason": "not_applicable"},
        "evidence_reason": reason,
        "reused": False,
        "freshly_executed": True,
        "original_executed_at": finished_at,
        "referencing_flow_ids": sorted(set(item.get("flow_ids") or [])),
        "elapsed_seconds": elapsed_seconds,
    }


def _git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout.decode("utf-8").strip()


def _changed_paths_for_recommendation(
    root: Path, base: str, revision: str = "HEAD", *, workspace: bool = True
) -> tuple[list[str], str]:
    try:
        paths: set[str] = set()
        if base:
            resolved = _git_output(root, "rev-parse", "--verify", base + "^{commit}")
            paths.update(_git_output(root, "diff", "--name-only", "--no-renames", "-z", resolved, revision).split("\0"))
        if workspace:
            paths.update(_git_output(root, "diff", "--name-only", "--no-renames", "-z", revision).split("\0"))
            paths.update(_git_output(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
        clean = sorted(paths - {""})
        return clean, "" if clean else "No changed paths; absence is not proof of no impact"
    except (subprocess.SubprocessError, OSError) as exc:
        return [], "Git change range unavailable: " + str(exc)


def run_scoped_mvg(
    *,
    root: Path,
    out: Path,
    run_id: str,
    verification_scope_arg: str,
    manifest_arg: str,
    mode: str,
    snapshot_mode: str,
    revision_arg: str,
    base_arg: str,
    godot_bin: str,
    dotnet_bin: str,
    timeout_sec: int,
    challenge_input: bool,
    execution_strategy: str = "scoped",
    protocol_fixture: bool = False,
    stop_on_deterministic_failure: bool = True,
    reuse_evidence_from: list[str] | None = None,
    reuse_build_from: str | None = None,
    events_log: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Consume a VerificationScope, execute tests under business lease & snapshot, emit coverage receipt."""
    started_at = _now()
    run_started_mono = time.monotonic()
    observed_elapsed = 0.0
    missed_build_elapsed = 0.0
    reserved_dispatches = 0
    observed_dispatches = 0
    reused_dispatches = 0
    build_reuses = 0
    events_path: Path | None = None
    events_emitted = 0
    events_deduplicated = 0

    def _emit_event(payload: dict[str, Any]) -> None:
        nonlocal events_emitted, events_deduplicated
        if events_path is None:
            return
        appended = evidence_reuse.append_deduplicated_event(events_path, payload)
        if appended:
            events_emitted += 1
        else:
            events_deduplicated += 1

    env_meta = probe_environment(
        dotnet_bin=dotnet_bin,
        godot_bin=godot_bin,
        explicit_protocol_fixture=protocol_fixture,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": "",
        "run_id": run_id,
        "scope_id": None,
        "input_set_digest": None,
        "manifest": manifest_arg,
        "manifest_sha256": None,
        "source_revision": None,
        "snapshot_digest": None,
        "workspace_dirty": False,
        "mode": mode,
        "status": "blocked",
        "reason_code": "blocked",
        "reason": "",
        "automated_scope_passed": False,
        "runtime_verified": False,
        "execution_strategy_used": execution_strategy,
        "superset_executed": False,
        "selective_execution_claimed": False,
        "superset_extra_tests": [],
        "requested_tests": [],
        "executed_tests": [],
        "not_run": [],
        "manual_obligations": [],
        "out_of_scope_future_obligations": [],
        "challenges": [],
        "evidence_tiers": _build_evidence_tiers_summary([], [], []),
        "static_wiring": {"applicable": False, "wiring_static_ok": True, "scenes_inspected": [], "adapters_inspected": [], "findings": []},
        "stop_loss": {"triggered": False, "source": None, "signals": [], "task_ids": [], "failed_prerequisite_id": None, "skipped_test_ids": []},
        "drift": {"pre_run_valid": False, "post_run_valid": False, "drift_detected": False, "invalidated_obligations": [], "invalidated_flows": [], "replacement_scope_id": None},
        "lease": {"acquired": False, "scope_keys": [], "uses_global_writer_lock": False, "lock_conflict": False},
        "build_artifacts": {"dotnet_build": None, "godot_prewarm": None},
        "reuse_rejections": [],
        "reuse_summary": {
            "unique_executed_test_count": 0,
            "freshly_executed_count": 0,
            "reused_test_count": 0,
            "reused_test_ids": [],
            "freshly_executed_test_ids": [],
            "build_reuse_count": 0,
            "rejection_count": 0,
            "events_emitted": 0,
            "events_deduplicated": 0,
            "build_reuse_implies_test_pass": False,
            "manual_satisfied_by_machine_reuse": False,
            "planning_adoption_interchangeable": False,
        },
        "state_isolation": {
            "per_test_dirs_isolated": True,
            "pollution_detected": False,
            "polluted_tests": [],
            "checks": [],
        },
        "metrics": {
            "observed_elapsed_seconds": 0.0,
            "total_run_elapsed_seconds": 0.0,
            "missed_build_elapsed_seconds": 0.0,
            "reserved_dispatches": 0,
            "observed_dispatches": 0,
            "reused_dispatches": 0,
            "build_reuses": 0,
            "reserved_budget_claimed_as_savings": False,
            "speedup_or_cost_gate_enforced": False,
        },
        "events_log_path": None,
        "coverage_summary": {
            "requested_count": 0,
            "executed_count": 0,
            "unique_executed_test_count": 0,
            "freshly_executed_count": 0,
            "reused_test_count": 0,
            "referencing_flow_link_count": 0,
            "flow_count_inflation_prevented": True,
            "passed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "not_run_blocking_count": 0,
            "not_run_future_count": 0,
            "manual_pending_count": 0,
            "all_requested_automated_passed": False,
        },
        "environment": env_meta,
        "diagnostics": [],
        "generated_at": started_at,
        "finished_at": "",
        "INVARIANT_FLAGS": dict(INVARIANT_FLAGS),
        **INVARIANT_FLAGS,
    }
    summary: dict[str, Any] = {
        "schema_version": "newrouge.mvg-acceptance.v1",
        "run_id": run_id,
        "mode": mode,
        "status": "blocked",
        "runtime_verified": False,
        "automated_scope_passed": False,
        "steps": [],
        **INVARIANT_FLAGS,
    }
    exit_code = 1

    def _finalize() -> tuple[int, dict[str, Any], dict[str, Any]]:
        receipt["evidence_tiers"] = _build_evidence_tiers_summary(
            receipt["executed_tests"], receipt["not_run"], receipt["manual_obligations"]
        )
        req_count = len(receipt["requested_tests"])
        exec_list = receipt["executed_tests"]
        passed_count = sum(1 for item in exec_list if item.get("status") == "passed")
        failed_count = sum(1 for item in exec_list if item.get("status") != "passed")
        skipped_cases = sum(int(item.get("skipped_cases") or 0) for item in exec_list)
        not_run_blocking = sum(1 for item in receipt["not_run"] if item.get("blocking_current_delivery"))
        not_run_future = sum(1 for item in receipt["not_run"] if not item.get("blocking_current_delivery"))
        manual_pending = len(receipt["manual_obligations"])
        reused_items = [item for item in exec_list if item.get("reused")]
        fresh_items = [item for item in exec_list if not item.get("reused")]
        flow_links = sum(len(item.get("referencing_flow_ids") or []) for item in exec_list)

        _emit_event({
            "event_type": "mvg_run_completed",
            "scope_id": receipt["scope_id"],
            "snapshot_digest": receipt["snapshot_digest"],
            "status": receipt["status"],
            "reason_code": receipt["reason_code"],
            "automated_scope_passed": receipt["automated_scope_passed"],
            "runtime_verified": receipt["runtime_verified"],
            "reused_test_ids": sorted(item["id"] for item in reused_items),
            "freshly_executed_test_ids": sorted(item["id"] for item in fresh_items),
        })

        receipt["coverage_summary"] = {
            "requested_count": req_count,
            "executed_count": len(exec_list),
            "unique_executed_test_count": len(exec_list),
            "freshly_executed_count": len(fresh_items),
            "reused_test_count": len(reused_items),
            "referencing_flow_link_count": flow_links,
            "flow_count_inflation_prevented": True,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_cases,
            "not_run_blocking_count": not_run_blocking,
            "not_run_future_count": not_run_future,
            "manual_pending_count": manual_pending,
            "all_requested_automated_passed": bool(receipt["automated_scope_passed"]),
        }
        receipt["reuse_summary"] = {
            "unique_executed_test_count": len(exec_list),
            "freshly_executed_count": len(fresh_items),
            "reused_test_count": len(reused_items),
            "reused_test_ids": sorted(item["id"] for item in reused_items),
            "freshly_executed_test_ids": sorted(item["id"] for item in fresh_items),
            "build_reuse_count": build_reuses,
            "rejection_count": len(receipt["reuse_rejections"]),
            "events_emitted": events_emitted,
            "events_deduplicated": events_deduplicated,
            "build_reuse_implies_test_pass": False,
            "manual_satisfied_by_machine_reuse": False,
            "planning_adoption_interchangeable": False,
        }
        receipt["metrics"] = {
            "observed_elapsed_seconds": round(observed_elapsed, 4),
            "total_run_elapsed_seconds": round(max(0.0, time.monotonic() - run_started_mono), 4),
            "missed_build_elapsed_seconds": round(missed_build_elapsed, 4),
            "reserved_dispatches": reserved_dispatches,
            "observed_dispatches": observed_dispatches,
            "reused_dispatches": reused_dispatches,
            "build_reuses": build_reuses,
            "reserved_budget_claimed_as_savings": False,
            "speedup_or_cost_gate_enforced": False,
        }
        # Append honest unverified exclusions for manual/future/not_run obligations.
        exclusions = list(receipt["environment"].get("unverified_exclusions") or [])
        if manual_pending > 0 and not any("manual_obligations_pending" in e for e in exclusions):
            exclusions.append(f"manual_obligations_pending:{manual_pending} human verification checks remain manual_pending")
        if not_run_future > 0 and not any("out_of_scope_future" in e for e in exclusions):
            exclusions.append(f"out_of_scope_future:{not_run_future} future obligations are outside current delivery")
        if not_run_blocking > 0 and not any("not_run_blocking" in e for e in exclusions):
            exclusions.append(f"not_run_blocking:{not_run_blocking} requested obligations did not run")
        receipt["environment"]["unverified_exclusions"] = exclusions
        receipt["finished_at"] = _now()
        _seal_receipt(receipt)

        receipt_path = out / "coverage-receipt.json"
        _write_json(receipt_path, receipt)
        summary.update({
            "status": receipt["status"],
            "reason_code": receipt["reason_code"],
            "reason": receipt["reason"],
            "runtime_verified": receipt["runtime_verified"],
            "automated_scope_passed": receipt["automated_scope_passed"],
            "scope_id": receipt["scope_id"],
            "input_set_digest": receipt["input_set_digest"],
            "receipt_id": receipt["receipt_id"],
            "manifest": receipt["manifest"],
            "manifest_sha256": receipt["manifest_sha256"],
            "source_revision": receipt["source_revision"],
            "snapshot_digest": receipt["snapshot_digest"],
            "workspace_dirty": receipt["workspace_dirty"],
            "execution_strategy_used": receipt["execution_strategy_used"],
            "superset_executed": receipt["superset_executed"],
            "selective_execution_claimed": receipt["selective_execution_claimed"],
            "superset_extra_tests": receipt["superset_extra_tests"],
            "protocol_fixture_only": receipt["environment"]["protocol_fixture_only"],
            "build_artifacts": receipt["build_artifacts"],
            "reuse_summary": receipt["reuse_summary"],
            "reuse_rejections": receipt["reuse_rejections"],
            "state_isolation": receipt["state_isolation"],
            "metrics": receipt["metrics"],
            "events_log_path": receipt["events_log_path"],
            "coverage_receipt_path": str(receipt_path),
            "coverage_receipt": receipt,
            "finished_at": receipt["finished_at"],
        })
        return exit_code, summary, receipt

    try:
        if timeout_sec < 1:
            receipt["reason_code"] = "invalid_argument"
            receipt["reason"] = "timeout-sec must be positive"
            return _finalize()

        if events_log is not None:
            try:
                ev_text = str(events_log).strip()
                if not ev_text:
                    raise ValueError("--events-log cannot be empty")
                ev_path, ev_rel = _normalize_repo_rel(root, ev_text, allow_logs=True)
                if not ev_rel.startswith("logs/"):
                    raise ValueError(f"--events-log must reside under logs/: {ev_rel}")
                if not ev_rel.lower().endswith(".jsonl"):
                    raise ValueError(f"--events-log must use .jsonl suffix: {ev_rel}")
                if os.path.lexists(ev_path):
                    inventory.no_reparse(ev_path)
                    if ev_path.is_dir():
                        raise ValueError(f"--events-log cannot be a directory: {ev_rel}")
                events_path = ev_path
                receipt["events_log_path"] = ev_rel
            except ValueError as exc:
                receipt["reason_code"] = "unsafe_path"
                receipt["reason"] = str(exc)
                receipt["diagnostics"].append({"reason_code": "unsafe_path", "message": str(exc)})
                return _finalize()

        if reuse_build_from is not None and not str(reuse_build_from).strip():
            receipt["reason_code"] = "unsafe_path"
            receipt["reason"] = "--reuse-build-from cannot be empty"
            receipt["diagnostics"].append({"reason_code": "unsafe_path", "message": "--reuse-build-from cannot be empty"})
            return _finalize()

        # 1. Validate VerificationScope path, schema, seal, and semantic consistency.
        try:
            scope_path, scope_rel = _normalize_repo_rel(root, verification_scope_arg, allow_logs=True)
        except ValueError as exc:
            receipt["reason_code"] = "unsafe_path"
            receipt["reason"] = str(exc)
            receipt["diagnostics"].append({"reason_code": "unsafe_path", "message": str(exc)})
            return _finalize()

        val = verification_scope.validate_verification_scope(root, scope_rel)
        if not val.get("ok"):
            receipt["reason_code"] = str(val.get("reason_code") or "schema_validation_failed")
            receipt["diagnostics"] = list(val.get("diagnostics") or [])
            receipt["reason"] = f"Invalid VerificationScope ({receipt['reason_code']})"
            return _finalize()

        scope_doc = codec.strict_json_loads(scope_path.read_bytes())
        receipt["scope_id"] = scope_doc["scope_id"]
        receipt["input_set_digest"] = scope_doc["input_set_digest"]

        # Populate manual & future obligations immediately (preserving binding_obligation:* manual items too).
        manual_list = []
        seen_manual_ids: set[str] = set()
        for m in (scope_doc.get("execution_plan") or {}).get("manual_obligations") or []:
            mid = m.get("manual_id") or m.get("obligation_id")
            if isinstance(mid, str) and mid:
                seen_manual_ids.add(mid)
            manual_list.append({
                **m,
                "evidence_level": "manual",
                "status": "manual_pending",
                "verified_by_runner": False,
            })
        for o in scope_doc.get("obligations") or []:
            if not isinstance(o, dict) or o.get("tier") not in {"existing_required", "current_new"}:
                continue
            oid = o.get("obligation_id")
            if not isinstance(oid, str) or oid in seen_manual_ids:
                continue
            if (
                o.get("status") == "manual_required"
                or o.get("evidence_level") == "manual"
                or o.get("execution_kind") == "manual_check"
            ):
                seen_manual_ids.add(oid)
                manual_list.append({
                    "manual_id": oid,
                    "obligation_id": oid,
                    "tier": o["tier"],
                    "source": "binding_obligation" if oid.startswith("binding_obligation:") else "scope_obligation",
                    "flow_ids": list(o.get("flow_ids") or []),
                    "requirement_ids": list(o.get("requirement_ids") or []),
                    "owner_plan_id": (o.get("semantic_owner") or {}).get("owner_plan_id"),
                    "responsibilities": list(o.get("follow_up_responsibilities") or [oid]),
                    "blocking_current_delivery": bool(o.get("blocking_current_delivery", True)),
                    "evidence_level": "manual",
                    "status": "manual_pending",
                    "verified_by_runner": False,
                })
        receipt["manual_obligations"] = manual_list
        future_list = [
            {
                "obligation_id": o["obligation_id"],
                "tier": "out_of_scope_future",
                "status": o["status"],
                "flow_ids": list(o.get("flow_ids") or []),
                "requirement_ids": list(o.get("requirement_ids") or []),
                "test_ids": list(o.get("test_ids") or []),
                "blocking_current_delivery": False,
                "claimed_passed": False,
            }
            for o in scope_doc.get("obligations") or []
            if o.get("tier") == "out_of_scope_future"
        ]
        receipt["out_of_scope_future_obligations"] = future_list

        # 2. Verify target --manifest belongs to VerificationScope & matches its declared SHA256.
        try:
            live_manifest_path, manifest_rel = _normalize_repo_rel(root, manifest_arg, allow_logs=False)
        except ValueError as exc:
            receipt["reason_code"] = "unsafe_path"
            receipt["reason"] = str(exc)
            return _finalize()
        receipt["manifest"] = manifest_rel

        allowed_manifests = _scope_manifest_map(scope_doc)
        if manifest_rel not in allowed_manifests:
            receipt["reason_code"] = "manifest_mismatch"
            receipt["reason"] = (
                f"Manifest {manifest_rel} is not declared in VerificationScope authority_refs "
                f"({sorted(allowed_manifests)})"
            )
            receipt["diagnostics"].append({
                "reason_code": "manifest_mismatch",
                "expected": sorted(allowed_manifests),
                "actual": manifest_rel,
            })
            return _finalize()

        if not live_manifest_path.is_file():
            receipt["reason_code"] = "file_not_found"
            receipt["reason"] = f"Manifest file not found: {manifest_rel}"
            return _finalize()

        live_manifest_sha = manifest_sha256(live_manifest_path.read_bytes())
        expected_manifest_sha = allowed_manifests[manifest_rel]
        receipt["manifest_sha256"] = live_manifest_sha
        if live_manifest_sha != expected_manifest_sha:
            receipt["reason_code"] = "digest_mismatch"
            receipt["reason"] = (
                f"Manifest SHA256 mismatch for {manifest_rel}: expected {expected_manifest_sha}, got {live_manifest_sha}"
            )
            return _finalize()

        live_manifest_doc = read_manifest(root, manifest_rel)

        # 3. Resolve git revision & workspace cleanliness.
        revision = _git_output(root, "rev-parse", "--verify", revision_arg + "^{commit}")
        workspace_dirty = bool(_git_output(root, "status", "--porcelain"))
        receipt["workspace_dirty"] = workspace_dirty
        summary["base_commit"] = revision
        deadline = time.monotonic() + timeout_sec

        # 4. Compute full business scope lease keys (including obligation task_ids & superset resources) BEFORE leasing.
        forced_superset = bool((scope_doc.get("impact_binding") or {}).get("conservative_expanded"))
        strategy_used = (
            "conservative_superset"
            if (execution_strategy == "conservative_superset" or forced_superset)
            else "scoped"
        )
        is_superset = strategy_used == "conservative_superset"
        receipt["execution_strategy_used"] = strategy_used

        scope_keys = _compute_business_scope_keys(
            scope_doc, manifest_rel, manifest_doc=live_manifest_doc, is_superset=is_superset
        )
        receipt["lease"]["scope_keys"] = list(scope_keys)
        try:
            lease_ctx = op_scope.business_guard(root, scope_keys, review_only=True)
            lease_ctx.__enter__()
            receipt["lease"]["acquired"] = True
        except codec.CodecError as err:
            is_conflict = err.diagnostic.reason_code == codec.ReasonCode.CONFLICT
            receipt["lease"]["lock_conflict"] = is_conflict
            receipt["reason_code"] = err.diagnostic.reason_code.value
            receipt["reason"] = (
                "Overlapping business scope lease is currently held by another process"
                if is_conflict else str(err)
            )
            receipt["diagnostics"].append(err.diagnostic.to_dict())
            return _finalize()

        try:
            # 5. Validate live freshness INSIDE the held business_guard lease!
            pre_reval = verification_scope.revalidate_verification_scope(root, scope_doc)
            live_sha_under_lease = (
                manifest_sha256(live_manifest_path.read_bytes()) if live_manifest_path.is_file() else ""
            )
            if (
                not pre_reval.get("ok")
                or not pre_reval.get("valid")
                or pre_reval.get("stale")
                or live_sha_under_lease != expected_manifest_sha
            ):
                receipt["drift"] = {
                    "pre_run_valid": False,
                    "post_run_valid": False,
                    "drift_detected": True,
                    "invalidated_obligations": list(pre_reval.get("invalidated_obligations") or []),
                    "invalidated_flows": list(pre_reval.get("invalidated_flows") or []),
                    "replacement_scope_id": pre_reval.get("replacement_scope_id"),
                }
                receipt["reason_code"] = "input_stale"
                receipt["reason"] = "VerificationScope drifted before execution; rebuild scope before running"
                receipt["diagnostics"].extend(list(pre_reval.get("diagnostics") or []))
                return _finalize()
            receipt["drift"]["pre_run_valid"] = True

            # 6. Prepare isolated integration snapshot for execution or commit mode.
            execution_root = root
            if mode == "run" or snapshot_mode == "commit":
                execution_root = out / "snapshot"
                snap = prepare_snapshot(
                    root,
                    execution_root,
                    revision,
                    "main" if snapshot_mode == "commit" else "workspace",
                    deadline,
                )
                receipt["source_revision"] = snap["source_revision"]
                receipt["snapshot_digest"] = snap["snapshot_digest"]
                summary["input_manifest"] = str(out / "input-manifest.json")
            else:
                receipt["source_revision"] = revision

            snap_manifest_path = safe_path(execution_root, manifest_rel)
            if not snap_manifest_path.is_file():
                receipt["reason_code"] = "file_not_found"
                receipt["reason"] = f"Manifest missing from isolated snapshot: {manifest_rel}"
                return _finalize()
            snap_manifest_sha = manifest_sha256(snap_manifest_path.read_bytes())
            if snap_manifest_sha != expected_manifest_sha:
                receipt["reason_code"] = "input_stale" if snapshot_mode == "commit" else "digest_mismatch"
                receipt["reason"] = (
                    f"Snapshot manifest SHA256 mismatch: expected {expected_manifest_sha}, got {snap_manifest_sha}"
                )
                receipt["drift"]["pre_run_valid"] = False
                receipt["drift"]["drift_detected"] = True
                return _finalize()

            # Verify VerificationScope directly against execution_root snapshot (catches commit vs workspace drift!).
            if execution_root != root:
                snap_reval = verification_scope.revalidate_verification_scope(execution_root, scope_doc)
                if not snap_reval.get("ok") or not snap_reval.get("valid") or snap_reval.get("stale"):
                    receipt["drift"] = {
                        "pre_run_valid": False,
                        "post_run_valid": False,
                        "drift_detected": True,
                        "invalidated_obligations": list(snap_reval.get("invalidated_obligations") or []),
                        "invalidated_flows": list(snap_reval.get("invalidated_flows") or []),
                        "replacement_scope_id": snap_reval.get("replacement_scope_id"),
                    }
                    receipt["status"] = "blocked"
                    receipt["reason_code"] = "input_stale"
                    receipt["reason"] = (
                        "VerificationScope does not match prepared execution snapshot "
                        "(snapshot inputs differ from scope_id); rebuild scope for target revision"
                    )
                    receipt["diagnostics"].extend(list(snap_reval.get("diagnostics") or []))
                    return _finalize()

            manifest_doc = read_manifest(execution_root, manifest_rel)
            summary.update(
                mvg_id=manifest_doc.get("mvg_id"),
                baseline_lineage=manifest_doc.get("baseline_lineage"),
                coverage=manifest_doc.get("coverage", {}),
            )
            val_errors, val_code = _validate_manifest_for_scope(
                execution_root, manifest_doc, scope_doc, manifest_rel, is_superset=is_superset
            )
            summary["validation_errors"] = val_errors
            if val_errors:
                receipt["reason_code"] = val_code
                receipt["reason"] = "; ".join(val_errors)
                receipt["diagnostics"].append({"reason_code": val_code, "errors": val_errors})
                return _finalize()

            # 7. Build requested tests, execution selection (scoped vs conservative_superset), & not_run list.
            manifest_tests_by_id = {t["id"]: t for t in manifest_doc["tests"]}
            obligations_by_id = {o["obligation_id"]: o for o in scope_doc.get("obligations") or []}
            obligation_tier_by_test: dict[str, str] = {}
            for o in scope_doc.get("obligations") or []:
                for tid in o.get("test_ids") or []:
                    if tid not in obligation_tier_by_test or o["tier"] == "existing_required":
                        obligation_tier_by_test[tid] = o["tier"]

            scope_exec_items = list((scope_doc.get("execution_plan") or {}).get("executable_tests") or [])
            manifest_flow_ids = {f["id"] for f in manifest_doc["flows"]}
            single_manifest = len(allowed_manifests) <= 1

            scoped_dotnet_gdunit: list[dict[str, Any]] = []
            scoped_other_scripts: list[dict[str, Any]] = []
            scoped_test_ids: set[str] = set()
            selected_flows: set[str] = set()
            for item in scope_exec_items:
                if item.get("kind") == "other_verification":
                    scoped_other_scripts.append(item)
                    continue
                if item.get("kind") in {"dotnet", "gdunit"}:
                    item_flows = set(item.get("flow_ids") or [])
                    if single_manifest or bool(item_flows & manifest_flow_ids) or item.get("test_id") in manifest_tests_by_id:
                        scoped_dotnet_gdunit.append(item)
                        scoped_test_ids.add(item["test_id"])
                        selected_flows.update(item_flows & manifest_flow_ids)

            raw_test_specs: list[dict[str, Any]] = []
            superset_extra_ids: list[str] = []
            if strategy_used == "conservative_superset":
                receipt["superset_executed"] = True
                receipt["selective_execution_claimed"] = False
                for item in scoped_dotnet_gdunit:
                    mrow = manifest_tests_by_id[item["test_id"]]
                    raw_test_specs.append({
                        "test": mrow,
                        "obligation_id": item.get("obligation_id"),
                        "tier": item.get("tier", "existing_required"),
                        "flow_ids": list(item.get("flow_ids") or []),
                        "requirement_ids": list(item.get("requirement_ids") or []),
                        "is_superset_extra": False,
                    })
                for mrow in manifest_doc["tests"]:
                    tid = mrow["id"]
                    if mrow.get("state") == "implemented" and tid not in scoped_test_ids:
                        superset_extra_ids.append(tid)
                        tier = obligation_tier_by_test.get(tid, "existing_required")
                        if tier == "out_of_scope_future":
                            tier = "existing_required"
                        raw_test_specs.append({
                            "test": mrow,
                            "obligation_id": f"superset:{tid}",
                            "tier": tier,
                            "flow_ids": [f["id"] for f in manifest_doc["flows"] if tid in f.get("test_ids", [])],
                            "requirement_ids": [],
                            "is_superset_extra": True,
                        })
                        selected_flows.update(f["id"] for f in manifest_doc["flows"] if tid in f.get("test_ids", []))
                receipt["superset_extra_tests"] = sorted(superset_extra_ids)
            else:
                receipt["superset_executed"] = False
                receipt["selective_execution_claimed"] = True
                receipt["superset_extra_tests"] = []
                for item in scoped_dotnet_gdunit:
                    mrow = manifest_tests_by_id[item["test_id"]]
                    raw_test_specs.append({
                        "test": mrow,
                        "obligation_id": item.get("obligation_id"),
                        "tier": item.get("tier", "existing_required"),
                        "flow_ids": list(item.get("flow_ids") or []),
                        "requirement_ids": list(item.get("requirement_ids") or []),
                        "is_superset_extra": False,
                    })

            # Intra-run multi-Flow deduplication (AC-2): merge ONLY when exact test identity matches.
            manifest_flows_by_test: dict[str, set[str]] = {}
            for mf in manifest_doc.get("flows") or []:
                fid = mf.get("id")
                if not isinstance(fid, str):
                    continue
                for tid in mf.get("test_ids") or []:
                    manifest_flows_by_test.setdefault(tid, set()).add(fid)

            dedup_map: dict[tuple[Any, ...], dict[str, Any]] = {}
            run_test_specs: list[dict[str, Any]] = []
            for spec in raw_test_specs:
                t = spec["test"]
                norm_lvl = normalize_evidence_tier(t["kind"], t.get("evidence_level"))
                dedup_key = (
                    t["id"],
                    t["kind"],
                    t["path"],
                    str(t.get("selector") or ""),
                    int(t.get("min_tests") or 1),
                    norm_lvl,
                    str(t.get("challenge") or ""),
                )
                extra_flows = set(spec.get("flow_ids") or []) | (manifest_flows_by_test.get(t["id"], set()) & selected_flows)
                if dedup_key in dedup_map:
                    existing = dedup_map[dedup_key]
                    existing["flow_ids"] = sorted(set(existing["flow_ids"]) | extra_flows)
                    existing["requirement_ids"] = sorted(set(existing["requirement_ids"]) | set(spec.get("requirement_ids") or []))
                    if spec.get("obligation_id") and spec["obligation_id"] not in existing["obligation_ids"]:
                        existing["obligation_ids"].append(spec["obligation_id"])
                    if spec.get("tier") == "existing_required":
                        existing["tier"] = "existing_required"
                    existing["is_superset_extra"] = existing["is_superset_extra"] and bool(spec.get("is_superset_extra"))
                else:
                    merged_flows = sorted(extra_flows)
                    merged_spec = {
                        "test": t,
                        "obligation_id": spec.get("obligation_id"),
                        "obligation_ids": [spec["obligation_id"]] if spec.get("obligation_id") else [],
                        "tier": spec.get("tier", "existing_required"),
                        "flow_ids": merged_flows,
                        "requirement_ids": sorted(set(spec.get("requirement_ids") or [])),
                        "is_superset_extra": bool(spec.get("is_superset_extra")),
                    }
                    dedup_map[dedup_key] = merged_spec
                    run_test_specs.append(merged_spec)

            for spec in run_test_specs:
                spec["requirement_coverage"] = evidence_reuse.collect_requirement_route_coverage(
                    execution_root,
                    scope_doc,
                    spec["flow_ids"],
                    fallback_requirement_ids=spec["requirement_ids"],
                )

            # Collect static-wiring targets in the isolated snapshot (filtered strictly to scope).
            scene_paths, adapter_paths, binding_objects = _collect_scoped_wiring_targets(
                execution_root, scope_doc, manifest_doc, selected_flows, is_superset=is_superset
            )
            has_static_wiring = bool(scene_paths or adapter_paths)

            # Recompute accurate environment needs & fixture classification.
            needs_dotnet = any(spec["test"]["kind"] == "dotnet" for spec in run_test_specs)
            needs_godot = any(spec["test"]["kind"] == "gdunit" for spec in run_test_specs)
            receipt["environment"] = probe_environment(
                dotnet_bin=dotnet_bin,
                godot_bin=godot_bin,
                explicit_protocol_fixture=protocol_fixture,
                needs_dotnet=needs_dotnet,
                needs_godot=needs_godot,
            )
            evidence_authenticity = receipt["environment"]["evidence_authenticity"]

            sw_tier = (
                "existing_required"
                if any(spec["tier"] == "existing_required" for spec in run_test_specs)
                else "current_new"
            )

            # Populate requested_tests (all current-tier obligations: static wiring + executable + blocking pending).
            requested: list[dict[str, Any]] = []
            if has_static_wiring:
                requested.append({
                    "id": "static-wiring:scoped",
                    "obligation_id": "static-wiring:scoped",
                    "tier": sw_tier,
                    "kind": "static-wiring",
                    "evidence_level": "static-wiring",
                    "manifest_evidence_level": "static-wiring",
                    "path": scene_paths[0] if scene_paths else adapter_paths[0],
                    "flow_ids": sorted(selected_flows),
                    "state": "implemented",
                    "blocking_current_delivery": True,
                })
            for spec in run_test_specs:
                t = spec["test"]
                requested.append({
                    "id": t["id"],
                    "obligation_id": spec["obligation_id"],
                    "tier": spec["tier"],
                    "kind": t["kind"],
                    "evidence_level": normalize_evidence_tier(t["kind"], t.get("evidence_level")),
                    "manifest_evidence_level": t.get("evidence_level"),
                    "path": t["path"],
                    "flow_ids": spec["flow_ids"],
                    "state": t["state"],
                    "blocking_current_delivery": True,
                })
            for item in scoped_other_scripts:
                requested.append({
                    "id": item["test_id"],
                    "obligation_id": item["obligation_id"],
                    "tier": item.get("tier", "current_new"),
                    "kind": "other_verification",
                    "evidence_level": "other-verification",
                    "manifest_evidence_level": "other-verification",
                    "path": item["path"],
                    "flow_ids": list(item.get("flow_ids") or []),
                    "state": "implemented",
                    "blocking_current_delivery": True,
                })

            # Pending / blocked / future obligations from VerificationScope.
            not_run: list[dict[str, Any]] = []
            for pitem in (scope_doc.get("execution_plan") or {}).get("pending_obligations") or []:
                oid = pitem["obligation_id"]
                obl = obligations_by_id.get(oid) or {}
                tier = pitem.get("tier") or obl.get("tier") or "current_new"
                blocking = bool(pitem.get("blocking_current_delivery"))
                tids = list(obl.get("test_ids") or [])
                entry_id = tids[0] if tids else oid
                kind = obl.get("execution_kind") or "pending_obligation"
                ev_level = normalize_evidence_tier(kind, obl.get("evidence_level"))
                if blocking:
                    requested.append({
                        "id": entry_id,
                        "obligation_id": oid,
                        "tier": tier,
                        "kind": kind,
                        "evidence_level": ev_level,
                        "manifest_evidence_level": obl.get("evidence_level"),
                        "path": (pitem.get("missing_targets") or [None])[0],
                        "flow_ids": list(pitem.get("flow_ids") or []),
                        "state": "planned" if pitem.get("status") == "pending" else "blocked",
                        "blocking_current_delivery": True,
                    })
                not_run.append({
                    "id": entry_id,
                    "obligation_id": oid,
                    "tier": tier,
                    "kind": kind,
                    "evidence_level": ev_level,
                    "reason_code": "planned_not_implemented" if pitem.get("status") == "pending" else (
                        "out_of_scope_future" if not blocking else "pending_or_broken_obligation"
                    ),
                    "reason": str(pitem.get("reason") or "pending_obligation"),
                    "blocking_current_delivery": blocking,
                })
            receipt["requested_tests"] = requested
            receipt["not_run"] = not_run
            summary["required_tests"] = [item["id"] for item in requested]

            def _append_all_scheduled_to_not_run(reason_code_val: str, reason_text: str) -> list[str]:
                added_ids: list[str] = []
                if has_static_wiring:
                    added_ids.append("static-wiring:scoped")
                    receipt["not_run"].append({
                        "id": "static-wiring:scoped",
                        "obligation_id": "static-wiring:scoped",
                        "tier": sw_tier,
                        "kind": "static-wiring",
                        "evidence_level": "static-wiring",
                        "reason_code": reason_code_val,
                        "reason": reason_text,
                        "blocking_current_delivery": True,
                    })
                for ov_item in scoped_other_scripts:
                    added_ids.append(ov_item["test_id"])
                    receipt["not_run"].append({
                        "id": ov_item["test_id"],
                        "obligation_id": ov_item["obligation_id"],
                        "tier": ov_item.get("tier", "current_new"),
                        "kind": "other_verification",
                        "evidence_level": "other-verification",
                        "reason_code": reason_code_val,
                        "reason": reason_text,
                        "blocking_current_delivery": True,
                    })
                for spec in run_test_specs:
                    t = spec["test"]
                    added_ids.append(t["id"])
                    receipt["not_run"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "tier": spec["tier"],
                        "kind": t["kind"],
                        "evidence_level": normalize_evidence_tier(t["kind"], t.get("evidence_level")),
                        "reason_code": reason_code_val,
                        "reason": reason_text,
                        "blocking_current_delivery": True,
                    })
                return added_ids

            if mode != "run":
                comparison_revision = revision if snapshot_mode == "commit" else _git_output(root, "rev-parse", "HEAD")
                cpaths, unknown = _changed_paths_for_recommendation(
                    root, base_arg, comparison_revision, workspace=snapshot_mode == "workspace"
                )
                rec_info = recommend(manifest_doc, cpaths, unknown_reason=unknown)
                rec_info["comparison_target"] = (
                    receipt.get("source_revision") or "workspace" if snapshot_mode == "workspace" else revision
                )
                rec_info["includes_working_changes"] = snapshot_mode == "workspace"
                summary["recommendation"] = rec_info
                _append_all_scheduled_to_not_run("non_execution_mode", f"mode={mode}; tests not executed")
                receipt["status"] = "planned" if mode == "plan" else "recommended"
                receipt["reason_code"] = "ok"
                receipt["reason"] = "Non-execution mode; runtime_verified remains false"
                exit_code = 0
                return _finalize()

            # 8. Pre-execution durable stop-loss check for in-scope + superset tasks.
            task_id_set = set((scope_doc.get("delivery_boundary") or {}).get("in_scope_task_ids") or [])
            for obl in scope_doc.get("obligations") or []:
                if isinstance(obl, dict) and obl.get("tier") in {"existing_required", "current_new"}:
                    for tid in obl.get("task_ids") or []:
                        if type(tid) is int and tid >= 1:
                            task_id_set.add(tid)
            if is_superset:
                for flow in manifest_doc.get("flows") or []:
                    if isinstance(flow, dict):
                        for tid in flow.get("task_ids") or []:
                            if type(tid) is int and tid >= 1:
                                task_id_set.add(tid)
            in_scope_tasks = sorted(task_id_set)
            durable_sl = _check_durable_stop_loss(root, in_scope_tasks)
            receipt["stop_loss"] = durable_sl
            if durable_sl["triggered"]:
                first_sig = durable_sl["signals"][0]
                sl_reason = f"stopped_by_durable_stop_loss:{first_sig['blocked_by']}:{first_sig['blocking_reason']}"
                durable_sl["skipped_test_ids"] = _append_all_scheduled_to_not_run("stop_loss_active", sl_reason)
                receipt["status"] = "blocked"
                receipt["reason_code"] = "stop_loss_active"
                receipt["reason"] = sl_reason
                return _finalize()

            # 9. Deterministic execution order: static-wiring -> other_verification -> domain-xunit -> gdunit.
            base_env = dict(os.environ)
            base_env["GDUNIT_STRICT_EXIT_CODE"] = "1"
            base_env.pop("MVG_INPUT_CHALLENGE", None)

            deterministic_failed_id: str | None = None
            pollution_detected = False
            polluted_test_id: str | None = None
            pre_snapshot_hashes = evidence_reuse.capture_snapshot_file_hashes(execution_root)
            reserved_dispatches = len(scoped_other_scripts) + len(run_test_specs)

            # Build per-test relevant_paths strictly from the Flows, handoffs[].contract_ref, flow.source_paths,
            # and Stage-4/5 implementation_objects that apply to THAT test_id (never pooling unrelated Flows!).
            def _collect_per_test_relevant_paths(spec_row: dict[str, Any]) -> list[str]:
                t_obj = spec_row["test"]
                tid = str(t_obj.get("id") or "")
                t_flows = {f for f in (spec_row.get("flow_ids") or []) if isinstance(f, str) and f}
                t_tasks: set[int] = set()
                paths_set: set[str] = set()

                for mf_flow in manifest_doc.get("flows") or []:
                    if not isinstance(mf_flow, dict):
                        continue
                    fid = mf_flow.get("id")
                    if fid not in t_flows:
                        continue
                    for task_id in mf_flow.get("task_ids") or []:
                        if type(task_id) is int and task_id >= 1:
                            t_tasks.add(task_id)
                    for sp in mf_flow.get("source_paths") or []:
                        if isinstance(sp, str) and sp.strip():
                            paths_set.add(sp.strip())
                    cref = mf_flow.get("contract_ref")
                    if isinstance(cref, str) and cref.strip():
                        paths_set.add(cref.strip())
                    for hoff in mf_flow.get("handoffs") or []:
                        if not isinstance(hoff, dict):
                            continue
                        h_tids = hoff.get("test_ids") or []
                        if not h_tids or tid in h_tids:
                            h_cref = hoff.get("contract_ref")
                            if isinstance(h_cref, str) and h_cref.strip():
                                paths_set.add(h_cref.strip())

                for obl in scope_doc.get("obligations") or []:
                    if not isinstance(obl, dict) or obl.get("tier") not in {"existing_required", "current_new"}:
                        continue
                    o_tids = set(obl.get("test_ids") or [])
                    o_flows = set(obl.get("flow_ids") or [])
                    if tid in o_tids or (t_flows and bool(o_flows & t_flows)):
                        for task_id in obl.get("task_ids") or []:
                            if type(task_id) is int and task_id >= 1:
                                t_tasks.add(task_id)
                        for ref_key in ("source_refs", "implementation_refs"):
                            for ref_val in obl.get(ref_key) or []:
                                if isinstance(ref_val, str) and ref_val.strip():
                                    paths_set.add(ref_val.strip())

                for bref in (scope_doc.get("authority_refs") or {}).get("binding_refs") or []:
                    bpath = bref.get("path") if isinstance(bref, dict) else None
                    if not isinstance(bpath, str) or not bpath:
                        continue
                    try:
                        bfp = safe_path(execution_root, bpath)
                    except ValueError:
                        continue
                    if not bfp.is_file():
                        continue
                    try:
                        bdoc = codec.strict_json_loads(bfp.read_bytes())
                    except Exception:  # noqa: BLE001
                        continue
                    b_tasks: set[int] = set()
                    for tm in bdoc.get("task_mappings") or []:
                        if not isinstance(tm, dict):
                            continue
                        tm_tid = tm.get("task_id")
                        tm_flows = set(tm.get("flow_ids") or [])
                        if (type(tm_tid) is int and tm_tid in t_tasks) or bool(tm_flows & t_flows):
                            if type(tm_tid) is int and tm_tid >= 1:
                                b_tasks.add(tm_tid)
                    eff_tasks = t_tasks | b_tasks
                    if not eff_tasks and not t_flows:
                        continue
                    for obj in bdoc.get("implementation_objects") or []:
                        if not isinstance(obj, dict) or obj.get("availability") != "existing":
                            continue
                        resp_tasks = {x for x in (obj.get("responsible_task_ids") or []) if type(x) is int and x >= 1}
                        obj_flows = {f for f in (obj.get("flow_ids") or []) if isinstance(f, str) and f}
                        if not (resp_tasks & eff_tasks) and not (obj_flows & t_flows):
                            continue
                        tref = obj.get("target_ref")
                        if isinstance(tref, dict):
                            for fitem in tref.get("files") or []:
                                fpath = fitem.get("path") if isinstance(fitem, dict) else None
                                if isinstance(fpath, str) and fpath.strip():
                                    paths_set.add(fpath.strip())

                return sorted(paths_set)

            # 9a. Static wiring check in isolated snapshot.
            if has_static_wiring:
                if time.monotonic() >= deadline:
                    receipt["not_run"].append({
                        "id": "static-wiring:scoped",
                        "obligation_id": "static-wiring:scoped",
                        "tier": sw_tier,
                        "kind": "static-wiring",
                        "evidence_level": "static-wiring",
                        "reason_code": "timeout_budget_exhausted",
                        "reason": "Global runtime budget exhausted",
                        "blocking_current_delivery": True,
                    })
                else:
                    sw_mono = time.monotonic()
                    sw_result = inspect_scoped_static_wiring(
                        execution_root,
                        scene_paths=scene_paths,
                        adapter_paths=adapter_paths,
                        binding_objects=binding_objects,
                    )
                    sw_elapsed = round(max(0.0, time.monotonic() - sw_mono), 4)
                    sw_finished = _now()
                    receipt["static_wiring"] = sw_result
                    sw_dir = out / "static-wiring"
                    sw_report_path = sw_dir / "report.json"
                    sw_cmd_path = sw_dir / "command.json"
                    _write_json(sw_report_path, sw_result)
                    _write_json(sw_cmd_path, {
                        "id": "static-wiring:scoped",
                        "kind": "static-wiring",
                        "evidence_level": "static-wiring",
                        "cwd": str(execution_root),
                        "scenes_inspected": sw_result["scenes_inspected"],
                        "adapters_inspected": sw_result["adapters_inspected"],
                        "exit_code": 0 if sw_result["wiring_static_ok"] else 1,
                        "finished_at": sw_finished,
                        "elapsed_seconds": sw_elapsed,
                        "report_paths": [str(sw_report_path)],
                    })
                    sw_ok = bool(sw_result["wiring_static_ok"])
                    receipt["executed_tests"].append({
                        "id": "static-wiring:scoped",
                        "obligation_id": "static-wiring:scoped",
                        "tier": sw_tier,
                        "kind": "static-wiring",
                        "evidence_level": "static-wiring",
                        "manifest_evidence_level": "static-wiring",
                        "evidence_authenticity": "real_static_inspection",
                        "command": ["static-wiring-inspector", *sw_result["scenes_inspected"], *sw_result["adapters_inspected"]],
                        "command_record": str(sw_cmd_path),
                        "exit_code": 0 if sw_ok else 1,
                        "status": "passed" if sw_ok else "failed",
                        "passed_cases": len(sw_result["scenes_inspected"]) + len(sw_result["adapters_inspected"]) if sw_ok else 0,
                        "failed_cases": len(sw_result["findings"]),
                        "skipped_cases": 0,
                        "log_path": str(sw_report_path),
                        "report_paths": [str(sw_report_path)],
                        "input_authenticity": {"checked": False, "valid": True, "reason": "static_wiring"},
                        "evidence_reason": "verified" if sw_ok else "static_wiring_failed",
                        "reused": False,
                        "freshly_executed": True,
                        "original_executed_at": sw_finished,
                        "referencing_flow_ids": sorted(selected_flows),
                        "elapsed_seconds": sw_elapsed,
                    })
                    if not sw_ok:
                        deterministic_failed_id = "static-wiring:scoped"

            # 9b. Executable other_verification scripts (with per-test isolation).
            for item in scoped_other_scripts:
                if pollution_detected:
                    receipt["not_run"].append({
                        "id": item["test_id"],
                        "obligation_id": item["obligation_id"],
                        "tier": item.get("tier", "current_new"),
                        "kind": "other_verification",
                        "evidence_level": "other-verification",
                        "reason_code": "mutable_test_state_pollution_detected",
                        "reason": f"Aborted after mutable snapshot state pollution by {polluted_test_id}",
                        "blocking_current_delivery": True,
                    })
                    continue
                if time.monotonic() >= deadline:
                    receipt["not_run"].append({
                        "id": item["test_id"],
                        "obligation_id": item["obligation_id"],
                        "tier": item.get("tier", "current_new"),
                        "kind": "other_verification",
                        "evidence_level": "other-verification",
                        "reason_code": "timeout_budget_exhausted",
                        "reason": "Global runtime budget exhausted",
                        "blocking_current_delivery": True,
                    })
                    continue
                ov_dir = out / ("other-" + re.sub(r"[^A-Za-z0-9._-]+", "_", item["test_id"]))
                ov_env = evidence_reuse.prepare_isolated_test_env(base_env, ov_dir)
                ov_res = _run_other_verification_script(execution_root, item, ov_dir, deadline, ov_env)
                observed_dispatches += 1
                observed_elapsed += float(ov_res.get("elapsed_seconds") or 0.0)
                iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, ov_dir)
                receipt["state_isolation"]["checks"].append({"test_id": item["test_id"], **iso})
                ov_res["state_isolation"] = iso
                ov_res["evidence_authenticity"] = evidence_authenticity
                if iso["pollution_detected"]:
                    pollution_detected = True
                    polluted_test_id = item["test_id"]
                    receipt["state_isolation"]["pollution_detected"] = True
                    receipt["state_isolation"]["polluted_tests"].append(item["test_id"])
                    ov_res["status"] = "failed"
                    ov_res["evidence_reason"] = "mutable_test_state_pollution_detected"
                receipt["executed_tests"].append(ov_res)
                if ov_res["status"] != "passed" and deterministic_failed_id is None:
                    deterministic_failed_id = item["test_id"]

            # Partition dotnet vs gdunit specs so deterministic domain-xunit runs before expensive gdunit.
            dotnet_specs = [s for s in run_test_specs if s["test"]["kind"] == "dotnet"]
            gdunit_specs = [s for s in run_test_specs if s["test"]["kind"] == "gdunit"]
            reuse_candidates = list(reuse_evidence_from or [])

            # 9c. Run domain-xunit (dotnet) tests with build reuse, test evidence reuse, & per-test isolation.
            dotnet_build_record: dict[str, Any] | None = None
            if dotnet_specs and reuse_build_from:
                dotnet_build_record, br_rejs = evidence_reuse.load_prior_build_record(
                    root,
                    reuse_build_from,
                    kind="dotnet_build",
                    execution_root=execution_root,
                    toolchain_env=receipt["environment"],
                )
                for rej in br_rejs:
                    receipt["reuse_rejections"].append(rej)
                    _emit_event({
                        "event_type": "reuse_rejected",
                        "scope_id": receipt["scope_id"],
                        "snapshot_digest": receipt["snapshot_digest"],
                        **rej,
                    })
                if dotnet_build_record is not None:
                    receipt["build_artifacts"]["dotnet_build"] = dotnet_build_record

            for spec in dotnet_specs:
                t = spec["test"]
                if pollution_detected:
                    receipt["not_run"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "tier": spec["tier"],
                        "kind": t["kind"],
                        "evidence_level": "domain-xunit",
                        "reason_code": "mutable_test_state_pollution_detected",
                        "reason": f"Aborted after mutable snapshot state pollution by {polluted_test_id}",
                        "blocking_current_delivery": True,
                    })
                    continue
                if time.monotonic() >= deadline:
                    receipt["not_run"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "tier": spec["tier"],
                        "kind": t["kind"],
                        "evidence_level": "domain-xunit",
                        "reason_code": "timeout_budget_exhausted",
                        "reason": "Global runtime budget exhausted",
                        "blocking_current_delivery": True,
                    })
                    continue

                req_cov = spec.get("requirement_coverage") or {}
                test_relevant_paths = _collect_per_test_relevant_paths(spec)
                test_identity = evidence_reuse.compute_test_evidence_identity(
                    execution_root,
                    test_spec={**t, "relevant_paths": test_relevant_paths},
                    snapshot_digest=receipt["snapshot_digest"] or "",
                    source_revision=receipt["source_revision"] or "",
                    workspace_dirty=receipt["workspace_dirty"],
                    toolchain_env=receipt["environment"],
                    verification_semantics={
                        "challenge": t.get("challenge") or "",
                        "challenge_input": False,
                        "input_authenticity_required": False,
                        "input_authenticity_valid": True,
                        "evidence_authenticity": evidence_authenticity,
                        "protocol_fixture_only": receipt["environment"]["protocol_fixture_only"],
                    },
                )

                if reuse_candidates:
                    reuse_eval = evidence_reuse.evaluate_test_evidence_reuse(
                        root,
                        execution_root,
                        test_spec=t,
                        current_identity=test_identity,
                        candidate_run_dirs=reuse_candidates,
                        referencing_flow_ids=spec["flow_ids"],
                        requirement_routes=req_cov.get("route_memberships"),
                    )
                    for rej in reuse_eval["rejections"]:
                        receipt["reuse_rejections"].append(rej)
                        _emit_event({
                            "event_type": "reuse_rejected",
                            "scope_id": receipt["scope_id"],
                            "snapshot_digest": receipt["snapshot_digest"],
                            **rej,
                        })
                    if reuse_eval["reused"] and reuse_eval["reused_entry"] is not None:
                        entry = dict(reuse_eval["reused_entry"])
                        entry["obligation_id"] = spec["obligation_id"]
                        entry["obligation_ids"] = list(spec.get("obligation_ids") or [])
                        entry["tier"] = spec["tier"]
                        entry["requirement_dispositions"] = dict(req_cov.get("requirement_dispositions") or {})
                        receipt["executed_tests"].append(entry)
                        summary["steps"].append(entry)
                        reused_dispatches += 1
                        _emit_event({
                            "event_type": "test_evidence_reused",
                            "scope_id": receipt["scope_id"],
                            "snapshot_digest": receipt["snapshot_digest"],
                            "test_id": t["id"],
                            "reused_from_run_id": entry["reused_from_run_id"],
                            "reused_evidence_id": entry["reused_evidence_id"],
                            "original_executed_at": entry["original_executed_at"],
                            "match_reason": entry["match_reason"],
                            "referencing_flow_ids": entry["referencing_flow_ids"],
                        })
                        continue

                build_eval = evidence_reuse.evaluate_build_reuse(
                    execution_root,
                    kind="dotnet_build",
                    toolchain_env=receipt["environment"],
                    prior_build_record=dotnet_build_record,
                )
                if build_eval["reused"]:
                    build_reuses += 1
                _emit_event({
                    "event_type": "build_reuse_evaluated",
                    "scope_id": receipt["scope_id"],
                    "snapshot_digest": receipt["snapshot_digest"],
                    "test_id": t["id"],
                    "kind": "dotnet_build",
                    "reused": build_eval["reused"],
                    "artifact_id": build_eval["artifact_id"],
                    "source_run_id": build_eval["source_run_id"],
                    "reason_code": build_eval["reason_code"],
                })

                step_out = out / t["id"]
                step_env = evidence_reuse.prepare_isolated_test_env(base_env, step_out)
                res = execute_test(
                    execution_root,
                    t,
                    step_out,
                    godot_bin,
                    deadline,
                    step_env,
                    prewarm=False,
                    no_build=bool(build_eval["reused"]),
                    dotnet_bin=dotnet_bin,
                    protocol_fixture=receipt["environment"]["protocol_fixture_only"],
                )
                observed_dispatches += 1
                step_elapsed = float(res.get("elapsed_seconds") or 0.0)
                observed_elapsed += step_elapsed
                if not build_eval["reused"]:
                    missed_build_elapsed += step_elapsed
                iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, step_out)
                receipt["state_isolation"]["checks"].append({"test_id": t["id"], **iso})

                effective_status = res["status"]
                ev = res["evidence"]
                effective_reason = ev.get("reason", "")
                if iso["pollution_detected"]:
                    pollution_detected = True
                    polluted_test_id = t["id"]
                    receipt["state_isolation"]["pollution_detected"] = True
                    receipt["state_isolation"]["polluted_tests"].append(t["id"])
                    effective_status = "failed"
                    effective_reason = "mutable_test_state_pollution_detected"

                if effective_status == "passed" and not build_eval["reused"]:
                    post_build = evidence_reuse.compute_build_artifact_identity(
                        execution_root,
                        kind="dotnet_build",
                        toolchain_env=receipt["environment"],
                    )
                    if post_build["artifact_present"]:
                        dotnet_build_record = {
                            **post_build,
                            "status": "ready",
                            "source_run_id": run_id,
                            "source_step_id": t["id"],
                            "original_created_at": res.get("finished_at") or _now(),
                        }
                        receipt["build_artifacts"]["dotnet_build"] = dotnet_build_record

                res["build_reuse"] = build_eval
                res["state_isolation"] = iso
                res["reused"] = False
                res["freshly_executed"] = True
                res["original_executed_at"] = res.get("finished_at") or _now()
                res["referencing_flow_ids"] = list(spec["flow_ids"])
                summary["steps"].append(res)
                passed_cases = max(0, int(ev.get("tests", 0)) - int(ev.get("failed", 0)) - int(ev.get("skipped", 0)))
                receipt["executed_tests"].append({
                    "id": t["id"],
                    "obligation_id": spec["obligation_id"],
                    "obligation_ids": list(spec.get("obligation_ids") or []),
                    "tier": spec["tier"],
                    "kind": "dotnet",
                    "evidence_level": "domain-xunit",
                    "manifest_evidence_level": t.get("evidence_level"),
                    "evidence_authenticity": evidence_authenticity,
                    "command": res["command"],
                    "command_record": res.get("command_record"),
                    "exit_code": res["exit_code"],
                    "status": effective_status,
                    "passed_cases": passed_cases,
                    "failed_cases": int(ev.get("failed", 0)),
                    "skipped_cases": int(ev.get("skipped", 0)),
                    "log_path": res["log"],
                    "report_paths": list(ev.get("reports") or []),
                    "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
                    "evidence_reason": effective_reason,
                    "reused": False,
                    "freshly_executed": True,
                    "original_executed_at": res.get("finished_at") or _now(),
                    "referencing_flow_ids": list(spec["flow_ids"]),
                    "requirement_ids": list(req_cov.get("requirement_ids") or []),
                    "requirement_dispositions": dict(req_cov.get("requirement_dispositions") or {}),
                    "observable_roles": list(req_cov.get("observable_roles") or []),
                    "requirement_routes": list(req_cov.get("route_memberships") or []),
                    "test_identity": test_identity,
                    "build_reuse": build_eval,
                    "state_isolation": iso,
                    "elapsed_seconds": step_elapsed,
                })
                _emit_event({
                    "event_type": "test_executed",
                    "scope_id": receipt["scope_id"],
                    "snapshot_digest": receipt["snapshot_digest"],
                    "test_id": t["id"],
                    "kind": "dotnet",
                    "status": effective_status,
                    "build_reused": build_eval["reused"],
                    "evidence_reason": effective_reason,
                    "original_executed_at": res.get("finished_at") or _now(),
                })
                if effective_status != "passed" and deterministic_failed_id is None:
                    deterministic_failed_id = t["id"]

            # 9d. Intra-run deterministic stop-loss (or state pollution abort) before launching expensive gdunit suites.
            godot_prewarm_record: dict[str, Any] | None = None
            godot_prewarm_loaded = False
            godot_ready = False
            if pollution_detected and gdunit_specs:
                for spec in gdunit_specs:
                    t = spec["test"]
                    receipt["not_run"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "tier": spec["tier"],
                        "kind": "gdunit",
                        "evidence_level": normalize_evidence_tier("gdunit", t.get("evidence_level")),
                        "reason_code": "mutable_test_state_pollution_detected",
                        "reason": f"Aborted after mutable snapshot state pollution by {polluted_test_id}",
                        "blocking_current_delivery": True,
                    })
            elif deterministic_failed_id is not None and stop_on_deterministic_failure and gdunit_specs:
                skipped_ids: list[str] = []
                for spec in gdunit_specs:
                    t = spec["test"]
                    skipped_ids.append(t["id"])
                    receipt["not_run"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "tier": spec["tier"],
                        "kind": "gdunit",
                        "evidence_level": normalize_evidence_tier("gdunit", t.get("evidence_level")),
                        "reason_code": "deterministic_stop_loss",
                        "reason": f"stopped_by_deterministic_stop_loss:{deterministic_failed_id}",
                        "blocking_current_delivery": True,
                    })
                receipt["stop_loss"] = {
                    "triggered": True,
                    "source": "intra_run_deterministic_failure",
                    "signals": [{"failed_prerequisite_id": deterministic_failed_id}],
                    "task_ids": in_scope_tasks,
                    "failed_prerequisite_id": deterministic_failed_id,
                    "skipped_test_ids": skipped_ids,
                }
            else:
                # 9e. Run gdunit tests (with prewarm reuse, test evidence reuse, authenticity check, & isolation).
                if gdunit_specs and reuse_build_from:
                    godot_prewarm_loaded = True
                    godot_prewarm_record, pr_rejs = evidence_reuse.load_prior_build_record(
                        root,
                        reuse_build_from,
                        kind="godot_prewarm",
                        execution_root=execution_root,
                        toolchain_env=receipt["environment"],
                    )
                    for rej in pr_rejs:
                        receipt["reuse_rejections"].append(rej)
                        _emit_event({
                            "event_type": "reuse_rejected",
                            "scope_id": receipt["scope_id"],
                            "snapshot_digest": receipt["snapshot_digest"],
                            **rej,
                        })
                    if godot_prewarm_record is not None:
                        receipt["build_artifacts"]["godot_prewarm"] = godot_prewarm_record

                for spec in gdunit_specs:
                    t = spec["test"]
                    ev_tier = normalize_evidence_tier("gdunit", t.get("evidence_level"))
                    if pollution_detected:
                        receipt["not_run"].append({
                            "id": t["id"],
                            "obligation_id": spec["obligation_id"],
                            "tier": spec["tier"],
                            "kind": "gdunit",
                            "evidence_level": ev_tier,
                            "reason_code": "mutable_test_state_pollution_detected",
                            "reason": f"Aborted after mutable snapshot state pollution by {polluted_test_id}",
                            "blocking_current_delivery": True,
                        })
                        continue
                    if not godot_bin:
                        receipt["not_run"].append({
                            "id": t["id"],
                            "obligation_id": spec["obligation_id"],
                            "tier": spec["tier"],
                            "kind": "gdunit",
                            "evidence_level": ev_tier,
                            "reason_code": "missing_godot_bin",
                            "reason": "Godot runner binary not provided; cannot execute gdunit suite",
                            "blocking_current_delivery": True,
                        })
                        continue
                    if time.monotonic() >= deadline:
                        receipt["not_run"].append({
                            "id": t["id"],
                            "obligation_id": spec["obligation_id"],
                            "tier": spec["tier"],
                            "kind": "gdunit",
                            "evidence_level": ev_tier,
                            "reason_code": "timeout_budget_exhausted",
                            "reason": "Global runtime budget exhausted",
                            "blocking_current_delivery": True,
                        })
                        continue

                    auth_check = inspect_gdunit_input_authenticity(
                        execution_root, t["path"], t.get("evidence_level") or ""
                    )
                    req_cov = spec.get("requirement_coverage") or {}
                    test_relevant_paths = _collect_per_test_relevant_paths(spec)
                    test_identity = evidence_reuse.compute_test_evidence_identity(
                        execution_root,
                        test_spec={**t, "relevant_paths": test_relevant_paths},
                        snapshot_digest=receipt["snapshot_digest"] or "",
                        source_revision=receipt["source_revision"] or "",
                        workspace_dirty=receipt["workspace_dirty"],
                        toolchain_env=receipt["environment"],
                        verification_semantics={
                            "challenge": t.get("challenge") or "",
                            "challenge_input": False,
                            "input_authenticity_required": ev_tier == "engine-input",
                            "input_authenticity_valid": bool(auth_check["valid"]),
                            "evidence_authenticity": evidence_authenticity,
                            "protocol_fixture_only": receipt["environment"]["protocol_fixture_only"],
                        },
                    )

                    if reuse_candidates and auth_check["valid"]:
                        reuse_eval = evidence_reuse.evaluate_test_evidence_reuse(
                            root,
                            execution_root,
                            test_spec=t,
                            current_identity=test_identity,
                            candidate_run_dirs=reuse_candidates,
                            referencing_flow_ids=spec["flow_ids"],
                            requirement_routes=req_cov.get("route_memberships"),
                        )
                        for rej in reuse_eval["rejections"]:
                            receipt["reuse_rejections"].append(rej)
                            _emit_event({
                                "event_type": "reuse_rejected",
                                "scope_id": receipt["scope_id"],
                                "snapshot_digest": receipt["snapshot_digest"],
                                **rej,
                            })
                        if reuse_eval["reused"] and reuse_eval["reused_entry"] is not None:
                            entry = dict(reuse_eval["reused_entry"])
                            entry["obligation_id"] = spec["obligation_id"]
                            entry["obligation_ids"] = list(spec.get("obligation_ids") or [])
                            entry["tier"] = spec["tier"]
                            entry["input_authenticity"] = auth_check
                            entry["requirement_dispositions"] = dict(req_cov.get("requirement_dispositions") or {})
                            receipt["executed_tests"].append(entry)
                            summary["steps"].append(entry)
                            reused_dispatches += 1
                            _emit_event({
                                "event_type": "test_evidence_reused",
                                "scope_id": receipt["scope_id"],
                                "snapshot_digest": receipt["snapshot_digest"],
                                "test_id": t["id"],
                                "reused_from_run_id": entry["reused_from_run_id"],
                                "reused_evidence_id": entry["reused_evidence_id"],
                                "original_executed_at": entry["original_executed_at"],
                                "match_reason": entry["match_reason"],
                                "referencing_flow_ids": entry["referencing_flow_ids"],
                            })
                            continue

                    prewarm_eval = evidence_reuse.evaluate_build_reuse(
                        execution_root,
                        kind="godot_prewarm",
                        toolchain_env=receipt["environment"],
                        prior_build_record=godot_prewarm_record,
                    )
                    if prewarm_eval["reused"]:
                        build_reuses += 1
                    _emit_event({
                        "event_type": "build_reuse_evaluated",
                        "scope_id": receipt["scope_id"],
                        "snapshot_digest": receipt["snapshot_digest"],
                        "test_id": t["id"],
                        "kind": "godot_prewarm",
                        "reused": prewarm_eval["reused"],
                        "artifact_id": prewarm_eval["artifact_id"],
                        "source_run_id": prewarm_eval["source_run_id"],
                        "reason_code": prewarm_eval["reason_code"],
                    })

                    step_out = out / t["id"]
                    step_env = evidence_reuse.prepare_isolated_test_env(base_env, step_out)
                    res = execute_test(
                        execution_root,
                        t,
                        step_out,
                        godot_bin,
                        deadline,
                        step_env,
                        prewarm=not bool(prewarm_eval["reused"]),
                        dotnet_bin=dotnet_bin,
                        protocol_fixture=receipt["environment"]["protocol_fixture_only"],
                    )
                    observed_dispatches += 1
                    step_elapsed = float(res.get("elapsed_seconds") or 0.0)
                    observed_elapsed += step_elapsed
                    if not prewarm_eval["reused"]:
                        missed_build_elapsed += step_elapsed
                    iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, step_out)
                    receipt["state_isolation"]["checks"].append({"test_id": t["id"], **iso})

                    ev = res["evidence"]
                    passed_cases = max(0, int(ev.get("tests", 0)) - int(ev.get("failed", 0)) - int(ev.get("skipped", 0)))
                    effective_status = res["status"]
                    effective_reason = ev.get("reason", "")
                    if iso["pollution_detected"]:
                        pollution_detected = True
                        polluted_test_id = t["id"]
                        receipt["state_isolation"]["pollution_detected"] = True
                        receipt["state_isolation"]["polluted_tests"].append(t["id"])
                        effective_status = "failed"
                        effective_reason = "mutable_test_state_pollution_detected"
                    elif not auth_check["valid"]:
                        effective_status = "failed"
                        effective_reason = auth_check["reason"]

                    if effective_status == "passed":
                        godot_ready = True
                    if effective_status == "passed" and not prewarm_eval["reused"]:
                        post_prewarm = evidence_reuse.compute_build_artifact_identity(
                            execution_root,
                            kind="godot_prewarm",
                            toolchain_env=receipt["environment"],
                        )
                        if post_prewarm["artifact_present"]:
                            godot_prewarm_record = {
                                **post_prewarm,
                                "status": "ready",
                                "source_run_id": run_id,
                                "source_step_id": t["id"],
                                "original_created_at": res.get("finished_at") or _now(),
                            }
                            receipt["build_artifacts"]["godot_prewarm"] = godot_prewarm_record

                    res["build_reuse"] = prewarm_eval
                    res["state_isolation"] = iso
                    res["reused"] = False
                    res["freshly_executed"] = True
                    res["original_executed_at"] = res.get("finished_at") or _now()
                    res["referencing_flow_ids"] = list(spec["flow_ids"])
                    summary["steps"].append(res)
                    receipt["executed_tests"].append({
                        "id": t["id"],
                        "obligation_id": spec["obligation_id"],
                        "obligation_ids": list(spec.get("obligation_ids") or []),
                        "tier": spec["tier"],
                        "kind": "gdunit",
                        "evidence_level": ev_tier,
                        "manifest_evidence_level": t.get("evidence_level"),
                        "evidence_authenticity": evidence_authenticity,
                        "command": res["command"],
                        "command_record": res.get("command_record"),
                        "exit_code": res["exit_code"],
                        "status": effective_status,
                        "passed_cases": passed_cases,
                        "failed_cases": int(ev.get("failed", 0)),
                        "skipped_cases": int(ev.get("skipped", 0)),
                        "log_path": res["log"],
                        "report_paths": list(ev.get("reports") or []),
                        "input_authenticity": auth_check,
                        "evidence_reason": effective_reason,
                        "reused": False,
                        "freshly_executed": True,
                        "original_executed_at": res.get("finished_at") or _now(),
                        "referencing_flow_ids": list(spec["flow_ids"]),
                        "requirement_ids": list(req_cov.get("requirement_ids") or []),
                        "requirement_dispositions": dict(req_cov.get("requirement_dispositions") or {}),
                        "observable_roles": list(req_cov.get("observable_roles") or []),
                        "requirement_routes": list(req_cov.get("route_memberships") or []),
                        "test_identity": test_identity,
                        "build_reuse": prewarm_eval,
                        "state_isolation": iso,
                        "elapsed_seconds": step_elapsed,
                    })
                    _emit_event({
                        "event_type": "test_executed",
                        "scope_id": receipt["scope_id"],
                        "snapshot_digest": receipt["snapshot_digest"],
                        "test_id": t["id"],
                        "kind": "gdunit",
                        "status": effective_status,
                        "build_reused": prewarm_eval["reused"],
                        "evidence_reason": effective_reason,
                        "original_executed_at": res.get("finished_at") or _now(),
                    })

            # 9f. Optional --challenge-input verification (gated: only when mode==run, baseline passed without stop-loss/pollution, and godot_bin available; sealed in receipt!).
            challenge_failed = False
            if challenge_input:
                baseline_ok = (
                    not pollution_detected
                    and not receipt["stop_loss"]["triggered"]
                    and bool(receipt["executed_tests"])
                    and all(item.get("status") == "passed" for item in receipt["executed_tests"])
                    and not any(item.get("blocking_current_delivery") for item in receipt["not_run"])
                )
                if not baseline_ok:
                    challenge_failed = True
                elif not godot_bin:
                    challenge_failed = True
                    receipt["diagnostics"].append({
                        "reason_code": "missing_godot_bin",
                        "message": "Godot runner binary is required to run --challenge-input verification",
                    })
                else:
                    targets = [spec["test"] for spec in gdunit_specs if spec["test"].get("challenge") == "disconnect-reward-input"]
                    if not targets:
                        challenge_failed = True
                        receipt["diagnostics"].append({
                            "reason_code": "missing_challenge_target",
                            "message": "No scoped gdunit test declares challenge=disconnect-reward-input",
                        })
                    else:
                        if not godot_ready and not godot_prewarm_loaded and reuse_build_from:
                            godot_prewarm_loaded = True
                            godot_prewarm_record, pr_rejs = evidence_reuse.load_prior_build_record(
                                root,
                                reuse_build_from,
                                kind="godot_prewarm",
                                execution_root=execution_root,
                                toolchain_env=receipt["environment"],
                            )
                            for rej in pr_rejs:
                                receipt["reuse_rejections"].append(rej)
                                _emit_event({
                                    "event_type": "reuse_rejected",
                                    "scope_id": receipt["scope_id"],
                                    "snapshot_digest": receipt["snapshot_digest"],
                                    **rej,
                                })
                            if godot_prewarm_record is not None:
                                receipt["build_artifacts"]["godot_prewarm"] = godot_prewarm_record
                        summary["challenges"] = []
                        for t in targets:
                            c_prewarm_eval = evidence_reuse.evaluate_build_reuse(
                                execution_root,
                                kind="godot_prewarm",
                                toolchain_env=receipt["environment"],
                                prior_build_record=godot_prewarm_record,
                            )
                            need_challenge_prewarm = not (godot_ready or bool(c_prewarm_eval["reused"]))
                            if not godot_ready and c_prewarm_eval["reused"]:
                                build_reuses += 1
                            c_out = out / ("challenge-" + t["id"])
                            c_env = evidence_reuse.prepare_isolated_test_env(base_env, c_out)
                            c_env["MVG_INPUT_CHALLENGE"] = "disconnect-reward-input"
                            c_res = execute_test(
                                execution_root,
                                t,
                                c_out,
                                godot_bin,
                                deadline,
                                c_env,
                                prewarm=need_challenge_prewarm,
                                dotnet_bin=dotnet_bin,
                                protocol_fixture=receipt["environment"]["protocol_fixture_only"],
                            )
                            observed_dispatches += 1
                            observed_elapsed += float(c_res.get("elapsed_seconds") or 0.0)
                            c_iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, c_out)
                            receipt["state_isolation"]["checks"].append({"test_id": "challenge-" + t["id"], **c_iso})
                            if c_iso["pollution_detected"]:
                                pollution_detected = True
                                polluted_test_id = "challenge-" + t["id"]
                                receipt["state_isolation"]["pollution_detected"] = True
                                receipt["state_isolation"]["polluted_tests"].append(polluted_test_id)
                            elif need_challenge_prewarm and c_res["exit_code"] not in {124, 127}:
                                godot_ready = True
                                post_prewarm = evidence_reuse.compute_build_artifact_identity(
                                    execution_root,
                                    kind="godot_prewarm",
                                    toolchain_env=receipt["environment"],
                                )
                                if post_prewarm["artifact_present"]:
                                    godot_prewarm_record = {
                                        **post_prewarm,
                                        "status": "ready",
                                        "source_run_id": run_id,
                                        "source_step_id": "challenge-" + t["id"],
                                        "original_created_at": c_res.get("finished_at") or _now(),
                                    }
                                    receipt["build_artifacts"]["godot_prewarm"] = godot_prewarm_record
                            detected = (
                                not c_iso["pollution_detected"]
                                and c_res["exit_code"] not in {0, 124, 127}
                                and c_res["evidence"]["failed"] > 0
                                and c_res["evidence"]["skipped"] == 0
                                and any(
                                    "MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES" in msg
                                    for msg in c_res["evidence"]["failure_messages"]
                                )
                                and c_res["evidence"]["reason"] == "failed-skipped-or-empty-tests"
                            )
                            c_res["defect_detected"] = detected
                            c_res["build_reuse"] = c_prewarm_eval
                            c_res["state_isolation"] = c_iso
                            summary["challenges"].append(c_res)
                            receipt["challenges"].append(c_res)
                            if not detected:
                                challenge_failed = True

            # 10. Post-execution live drift check (AC-4): preserves already-executed tests on drift!
            post_reval = verification_scope.revalidate_verification_scope(root, scope_doc)
            live_sha_after = (
                manifest_sha256(live_manifest_path.read_bytes())
                if live_manifest_path.is_file() else ""
            )
            drifted = (
                not post_reval.get("ok")
                or not post_reval.get("valid")
                or bool(post_reval.get("stale"))
                or live_sha_after != expected_manifest_sha
            )
            receipt["drift"] = {
                "pre_run_valid": True,
                "post_run_valid": not drifted,
                "drift_detected": drifted,
                "invalidated_obligations": list(post_reval.get("invalidated_obligations") or []),
                "invalidated_flows": list(post_reval.get("invalidated_flows") or []),
                "replacement_scope_id": post_reval.get("replacement_scope_id"),
            }
            if drifted:
                receipt["status"] = "blocked"
                receipt["reason_code"] = "input_stale"
                receipt["reason"] = "Inputs/bindings/manifest drifted during execution; observed steps preserved"
                receipt["automated_scope_passed"] = False
                receipt["runtime_verified"] = False
                exit_code = 1
                return _finalize()

            # 11. Compute strict anti-false-PASS verdict (AC-2 & AC-5).
            executed_by_id = {item["id"]: item for item in receipt["executed_tests"]}
            blocking_not_run = [item for item in receipt["not_run"] if item.get("blocking_current_delivery")]
            failed_exec = [item for item in receipt["executed_tests"] if item.get("status") != "passed"]
            skipped_exec = [item for item in receipt["executed_tests"] if int(item.get("skipped_cases") or 0) > 0]
            missing_requested = [
                req["id"] for req in receipt["requested_tests"]
                if req["id"] not in executed_by_id or executed_by_id[req["id"]].get("status") != "passed"
            ]
            blocking_gaps = list(scope_doc.get("blocking_gaps") or [])
            scope_closable = scope_doc.get("scope_closable") is True
            invalid_input_tasks = [
                t.get("task_id")
                for t in (scope_doc.get("task_input_set_digests") or [])
                if isinstance(t, dict) and t.get("valid_input_set") is not True
            ]

            if (
                pollution_detected
                or not receipt["requested_tests"]
                or not scope_closable
                or invalid_input_tasks
                or blocking_not_run
                or failed_exec
                or skipped_exec
                or missing_requested
                or blocking_gaps
                or challenge_failed
                or receipt["stop_loss"]["triggered"]
            ):
                receipt["automated_scope_passed"] = False
                receipt["runtime_verified"] = False
                exit_code = 1
                if pollution_detected:
                    receipt["status"] = "blocked"
                    receipt["reason_code"] = "mutable_test_state_pollution_detected"
                    receipt["reason"] = (
                        f"Mutable snapshot state pollution detected during test execution ({polluted_test_id}); "
                        "subsequent tests aborted to prevent state inheritance"
                    )
                elif receipt["stop_loss"]["triggered"]:
                    receipt["status"] = "blocked"
                    receipt["reason_code"] = "deterministic_stop_loss"
                    receipt["reason"] = (
                        f"Stopped after deterministic failure ({receipt['stop_loss']['failed_prerequisite_id']}); "
                        f"downstream tests not run: {receipt['stop_loss']['skipped_test_ids']}"
                    )
                elif not scope_closable or invalid_input_tasks or blocking_not_run or blocking_gaps:
                    receipt["status"] = "blocked"
                    receipt["reason_code"] = "incomplete_scope"
                    receipt["reason"] = (
                        f"Scope not closable (scope_closable={scope_closable}, invalid_inputs={invalid_input_tasks}), "
                        f"blocking unexecuted/pending obligations ({len(blocking_not_run)}), "
                        f"or scope gaps ({len(blocking_gaps)}) prevent PASS"
                    )
                elif challenge_failed:
                    receipt["status"] = "failed"
                    receipt["reason_code"] = "challenge_input_failed"
                    receipt["reason"] = "Disconnected input challenge was not demonstrated by a test assertion"
                else:
                    # Inspect specific failure cause for clear diagnostics.
                    first_fail = failed_exec[0] if failed_exec else None
                    if first_fail and first_fail.get("kind") == "static-wiring":
                        receipt["status"] = "failed"
                        receipt["reason_code"] = "static_wiring_failed"
                        receipt["reason"] = "Static scene/adapter wiring verification failed"
                    elif first_fail and first_fail.get("input_authenticity", {}).get("checked") and not first_fail["input_authenticity"]["valid"]:
                        receipt["status"] = "failed"
                        receipt["reason_code"] = "input_authenticity_failed"
                        receipt["reason"] = f"Input authenticity check failed for {first_fail['id']}: {first_fail['input_authenticity']['reason']}"
                    else:
                        receipt["status"] = "blocked" if skipped_exec else "failed"
                        receipt["reason_code"] = "test_failed"
                        receipt["reason"] = f"Required test(s) failed or unverified: {[x['id'] for x in failed_exec]}"
                return _finalize()

            # All requested automated tests passed with zero blocking gaps, zero skipped, zero drift!
            receipt["automated_scope_passed"] = True
            executed_runtime_tests = [
                item for item in receipt["executed_tests"]
                if item.get("kind") in {"dotnet", "gdunit"} and item.get("status") == "passed"
            ]
            if receipt["environment"]["protocol_fixture_only"]:
                receipt["status"] = "passed_protocol_fixture_only"
                receipt["reason_code"] = "protocol_fixture_only"
                receipt["reason"] = (
                    "All requested automated checks passed under protocol fixture only; "
                    "runtime_verified remains false (does not certify real Godot gameplay)"
                )
                receipt["runtime_verified"] = False
            elif len(executed_runtime_tests) == 0:
                receipt["status"] = "passed_non_runtime_only"
                receipt["reason_code"] = "non_runtime_only"
                receipt["reason"] = (
                    "All requested non-runtime checks passed, but zero dotnet/gdunit runtime tests executed; "
                    "runtime_verified remains false"
                )
                receipt["runtime_verified"] = False
                exclusions = list(receipt["environment"].get("unverified_exclusions") or [])
                exclusions.append("non_runtime_only: zero dotnet/gdunit runtime tests executed")
                receipt["environment"]["unverified_exclusions"] = exclusions
            else:
                receipt["status"] = "passed"
                receipt["reason_code"] = "ok"
                receipt["reason"] = "All requested automated checks in VerificationScope passed"
                receipt["runtime_verified"] = True
            exit_code = 0
            return _finalize()
        finally:
            lease_ctx.__exit__(None, None, None)

    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
        receipt["status"] = "blocked"
        receipt["reason_code"] = "runner_error"
        receipt["reason"] = str(exc)
        receipt["automated_scope_passed"] = False
        receipt["runtime_verified"] = False
        exit_code = 1
        return _finalize()
