"""Read-only B-route target-slice Chapter 7 UI closure, Chapter 6 evidence reuse, and governed handoff.

Responsibilities (Story 3.11):
- AC-1 (SLICE_SCOPE): Evaluate ONLY the selected target Flow / backlog slice / Task set
  without waiting for unrelated game Tasks or unrelated profile buckets to become done.
  Consume Flow/binding-declared UI obligations (scene entry/return, real engine input,
  feedback, four-part bindings, manual obligations) and chapter7-profile.json contracts.
  Return ui_applicability="not_applicable" ONLY for committed non-UI/non-Flow scopes with
  substantive rationale and live adoption_proof_refs / other_verification_refs; fail closed
  if player-facing UI fields are merely blank or undeclared.
- AC-2 (EVIDENCE_REUSE): Match Chapter 6 / runtime UI evidence against current live
  InputSet digest, committed binding/condition identity, and live test file sha256.
  Reuse verified implementations/obligations preserving original Task/Flow/binding/evidence
  identity without proposing synonymous duplicate Tasks. Reject stale InputSet, mismatched
  condition, static-wiring-only, or method-call-only evidence from satisfying real engine
  input obligations.
- AC-3 (HONEST_WIRING): Deterministically inspect target-slice .tscn scenes and C#/GD
  adapters for broken node/signal bindings, Godot control/node type mismatches, lifecycle
  mismatches, and empty/skipped/planned/unexecuted test evidence. Keep manual visual/feel
  obligations independent and never claim Flow full completion from partial UI closure.
- AC-4 (GOV_GAP_PATCH): Route definition/contract/ownership/binding gaps to exact
  owning_stage (3A..5) via Story 3.10 defect routing; emit read-only Story 3.1/3.2
  governed business-view delta candidates without writing .taskmaster/tasks/*.json or
  allocating permanent IDs; protect mature done status and native .tscn manual regions.
- AC-5 (HANDOFF_NOKCP): Emit traceable target-slice handoff separating verified_items,
  pending_items, manual_items, and blocked_items with binding_ref/task_id/flow_id/
  evidence_ref on every item; preserve downstream Flow and cumulative milestone closure
  responsibilities; NEVER trigger implicit global Knowledge refresh; maintain
  runtime_verified=False and default_b_enabled=False unconditionally.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import _b_route_chapter4_binding as ch4_binding
import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_codec as codec
import _b_route_defect_routing as defect_routing
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _b_route_records as records
import _b_route_stage5_obligations as stage5_obls
import _b_route_task_resolver as task_resolver
import _chapter7_profile as ch7_profile


SCHEMA = "newrouge.b-route-chapter7-slice.v1"
HANDOFF_SCHEMA = "newrouge.b-route-chapter7-handoff.v1"
DELTA_CANDIDATE_SCHEMA = "newrouge.b-route-task-change-intents.v1"

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

STAGE_RANK = input_set.STAGE_RANK

_STATIC_EVIDENCE_KINDS = frozenset(
    {
        "static_wiring",
        "static_grep",
        "tscn_text_check",
        "scene_text_grep",
        "wiring_only",
    }
)
_METHOD_CALL_EVIDENCE_KINDS = frozenset(
    {
        "method_call_only",
        "dotnet_unit",
        "unit_only",
        "core_unit",
    }
)
_REAL_ENGINE_EVIDENCE_KINDS = frozenset(
    {
        "gdunit_engine_input",
        "gdunit_scene",
        "scene_integration",
        "engine_input",
        "godot_ui_runtime",
        "chapter6_ui_runtime",
    }
)

_UI_KEYWORD_RE = re.compile(
    r"\b(?:ui|screen|scene|panel|button|dialog|hud|overlay|menu|click|drag|input|tooltip|widget|modal)\b",
    re.IGNORECASE,
)

# Minimal Godot 4 node inheritance table (child -> direct parent) for honest type checks.
_GODOT_TYPE_PARENT: dict[str, str] = {
    "Control": "CanvasItem",
    "Node2D": "CanvasItem",
    "CanvasItem": "Node",
    "CanvasLayer": "Node",
    "AnimationPlayer": "Node",
    "AudioStreamPlayer": "Node",
    "AudioStreamPlayer2D": "Node2D",
    "GPUParticles2D": "Node2D",
    "CPUParticles2D": "Node2D",
    "Camera2D": "Node2D",
    "Timer": "Node",
    "BaseButton": "Control",
    "Button": "BaseButton",
    "MenuButton": "Button",
    "CheckBox": "Button",
    "CheckButton": "CheckBox",
    "OptionButton": "Button",
    "TextureButton": "BaseButton",
    "LinkButton": "BaseButton",
    "Label": "Control",
    "RichTextLabel": "Control",
    "LineEdit": "Control",
    "TextEdit": "Control",
    "TextureRect": "Control",
    "NinePatchRect": "Control",
    "ColorRect": "Control",
    "Panel": "Control",
    "Container": "Control",
    "PanelContainer": "Container",
    "MarginContainer": "Container",
    "CenterContainer": "Container",
    "AspectRatioContainer": "Container",
    "FlowContainer": "Container",
    "HFlowContainer": "FlowContainer",
    "VFlowContainer": "FlowContainer",
    "ScrollContainer": "Container",
    "GridContainer": "Container",
    "BoxContainer": "Container",
    "VBoxContainer": "BoxContainer",
    "HBoxContainer": "BoxContainer",
    "TabContainer": "Container",
    "SplitContainer": "Container",
    "HSplitContainer": "SplitContainer",
    "VSplitContainer": "SplitContainer",
    "SubViewportContainer": "Container",
    "SubViewport": "Viewport",
    "Separator": "Control",
    "HSeparator": "Separator",
    "VSeparator": "Separator",
    "ProgressBar": "Range",
    "TextureProgressBar": "Range",
    "Slider": "Range",
    "HSlider": "Slider",
    "VSlider": "Slider",
    "SpinBox": "Range",
    "Range": "Control",
    "ItemList": "Control",
    "Tree": "Control",
    "Popup": "Window",
    "PopupPanel": "Popup",
    "PopupMenu": "Popup",
    "AcceptDialog": "Window",
    "ConfirmationDialog": "AcceptDialog",
    "Window": "Viewport",
    "Viewport": "Node",
    "Sprite2D": "Node2D",
    "CharacterBody2D": "Node2D",
    "Area2D": "Node2D",
}

_GODOT_BUILTIN_NODE_METHODS = frozenset(
    {
        "hide",
        "show",
        "queue_free",
        "free",
        "set_visible",
        "set_process",
        "set_physics_process",
        "grab_focus",
        "release_focus",
        "play",
        "stop",
        "start",
        "clear",
        "popup",
        "popup_centered",
        "Hide",
        "Show",
        "QueueFree",
        "Free",
        "SetVisible",
        "GrabFocus",
        "Play",
        "Stop",
        "Start",
        "Clear",
        "Popup",
        "PopupCentered",
    }
)

_EXT_RES_RE = re.compile(
    r'^\[ext_resource\b[^\]]*?\bpath="([^"]+)"[^\]]*?\bid="([^"]+)"',
    re.MULTILINE,
)
_EXT_RES_ALT_RE = re.compile(
    r'^\[ext_resource\b[^\]]*?\bid="([^"]+)"[^\]]*?\bpath="([^"]+)"',
    re.MULTILINE,
)
_NODE_HEADER_RE = re.compile(r"^\[node\b([^\]]+)\]$")
_CONN_HEADER_RE = re.compile(r"^\[connection\b([^\]]+)\]$")
_SUB_RES_HEADER_RE = re.compile(r"^\[sub_resource\b([^\]]+)\]$")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_SCRIPT_EXT_RE = re.compile(r'^script\s*=\s*ExtResource\(\s*"?([^"\)]+)"?\s*\)')
_INSTANCE_EXT_RE = re.compile(r'\binstance\s*=\s*ExtResource\(\s*"?([^"\)]+)"?\s*\)')

_CS_GETNODE_RE = re.compile(
    r'\bGetNode(?:OrNull)?\s*<\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*>\s*\(\s*"([^"]+)"\s*\)'
)
_CS_GETNODE_UNTYPED_RE = re.compile(
    r'\bGetNode(?:OrNull)?\s*\(\s*"([^"]+)"\s*\)'
)
_CS_CLASS_RE = re.compile(
    r"\b(?:public|internal|private|protected)?\s*(?:sealed\s+|abstract\s+|partial\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([A-Za-z_][A-Za-z0-9_\.]*))?"
)
_GD_NODE_REF_RE = re.compile(r'(?:get_node(?:_or_null)?\(\s*"([^"]+)"\s*\)|\$(?:"([^"]+)"|([A-Za-z0-9_/%]+)))')
_GD_FUNC_RE = re.compile(r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_CS_METHOD_RE = re.compile(
    r"(?:^|[;\}\n])\s*(?:(?:public|private|protected|internal)\s+)?(?:(?:static|virtual|override|async|sealed|new|partial)\s+)*(?:void|Task(?:<[^>]+>)?|[A-Za-z_][A-Za-z0-9_<>\.\?]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)
_CS_CONTROL_KEYWORDS = frozenset(
    {"if", "for", "foreach", "while", "switch", "catch", "lock", "using", "return", "new", "typeof", "sizeof", "nameof", "fixed"}
)

_MANUAL_PROP_PREFIXES = (
    "offset_left",
    "offset_top",
    "offset_right",
    "offset_bottom",
    "anchor_left",
    "anchor_top",
    "anchor_right",
    "anchor_bottom",
    "layout_mode",
    "anchors_preset",
    "size_flags_",
    "theme_override_",
    "custom_minimum_size",
    "modulate",
    "self_modulate",
    "position",
    "scale",
    "rotation",
    "pivot_offset",
    "z_index",
    "theme",
)

_MATURE_DONE_STATUSES = frozenset({"done", "completed", "complete"})

_DEFAULT_PROFILE_PLACEHOLDERS = frozenset(
    {
        "Unclassified UI surface",
        "Use the configured product flow",
        "Show the configured governed runtime state",
        "Configure an explicit project bucket or fallback.",
    }
)

_TEST_SKIP_PATTERNS = (
    re.compile(r"\[[^\]]*\b(?:Fact|Theory|SkippableFact|SkippableTheory|TestCase)\b[^\]]*\bSkip\s*=", re.IGNORECASE),
    re.compile(r"\[\s*Ignore\b", re.IGNORECASE),
    re.compile(r"\[\s*IgnoreUntil\b", re.IGNORECASE),
    re.compile(r"\bAssert\.Skip\s*\(", re.IGNORECASE),
    re.compile(r"^\s*#if\s+(?:false|0)\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bskip_test\s*(?:=\s*True|\()", re.IGNORECASE),
    re.compile(r"\bdo_skip\s*\(", re.IGNORECASE),
)
_CS_TEST_ATTR_RE = re.compile(
    r"\[[^\]]*\b(?:Fact|Theory|SkippableFact|SkippableTheory|TestCase|Test|TestMethod)\b",
    re.IGNORECASE,
)
_GD_TEST_FUNC_RE = re.compile(r"^\s*func\s+test_", re.MULTILINE)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "into",
        "from",
        "wire",
        "wiring",
        "ui",
        "task",
        "flow",
        "slice",
        "implement",
        "add",
        "create",
        "update",
        "fix",
        "surface",
        "surfaces",
        "screen",
        "scene",
        "panel",
    }
)


def _norm_rel(raw: str) -> str:
    """Normalize repository-relative POSIX path without stripping leading dots like .taskmaster."""
    s = str(raw or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s.removeprefix("./")
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _diag(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(
        code,
        stage,
        entity_id,
        expected,
        actual,
        resume_ref,
    ).to_dict()


def _earliest_stage(stages: list[str | None], default: str | None = None) -> str | None:
    valid = [s for s in stages if s in STAGE_RANK]
    if not valid:
        return default
    return min(valid, key=lambda s: STAGE_RANK[s])


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9]+", str(text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _strict_nonneg_int(val: Any, *, default: int | None = None) -> int | None:
    if val is None:
        return default
    if type(val) is not int or val < 0:
        return None
    return val


def _strip_comments(text: str, *, is_cs: bool, mask_strings: bool = False) -> str:
    """Strip C# (//, /* */) or GDScript (#) comments, optionally masking string literal bodies."""
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if is_cs:
            # Verbatim string @"..."
            if ch == "@" and i + 1 < n and text[i + 1] == '"':
                if mask_strings:
                    out.append('""')
                else:
                    out.append('@"')
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
                while i < n:
                    if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                        i += 2
                        break
                    if text[i] == "\n":
                        out.append("\n")
                    i += 1
                continue
            out.append(ch)
            i += 1
        else:
            # GDScript triple-quoted strings
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
            if ch == "#":
                i += 1
                while i < n and text[i] != "\n":
                    i += 1
                continue
            out.append(ch)
            i += 1
    return "".join(out)


def _check_ancestors_no_reparse(root_resolved: Path, target: Path) -> None:
    rel = target.relative_to(root_resolved)
    cur = root_resolved
    for part in rel.parts:
        cur = cur / part
        if os.path.lexists(cur):
            inventory.no_reparse(cur)


def _resolve_contained_path(
    root_path: Path,
    raw_path: str | Path,
    *,
    label: str,
    entity_id: str | None,
) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    text = str(raw_path or "").strip()
    if not text:
        return None, None, None
    root_resolved = root_path.resolve()
    cand = Path(text)
    try:
        if cand.is_absolute():
            for ancestor in reversed((cand, *cand.parents)):
                if os.path.lexists(ancestor):
                    inventory.no_reparse(ancestor)
            resolved = cand.resolve()
            rel = resolved.relative_to(root_resolved).as_posix()
            target = inventory.safe_input(root_resolved, rel, allow_logs=True)
            _check_ancestors_no_reparse(root_resolved, target)
        else:
            norm = _norm_rel(text)
            target = inventory.safe_input(root_resolved, norm, allow_logs=True)
            _check_ancestors_no_reparse(root_resolved, target)
            rel = target.relative_to(root_resolved).as_posix()
        return target, rel, None
    except (codec.CodecError, ValueError, OSError) as exc:
        diag = _diag(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=f"safe repository-contained path for {label}",
            actual={"path": text, "error": f"{type(exc).__name__}: {exc}"},
            resume_ref=text,
        )
        return None, text, diag


def _safe_load_json_arg(
    root_path: Path,
    raw_arg: dict[str, Any] | list[Any] | str | Path | None,
    *,
    label: str,
    entity_id: str | None,
) -> tuple[Any, str | None, dict[str, Any] | None]:
    if raw_arg is None:
        return None, None, None
    if isinstance(raw_arg, (dict, list)):
        return deepcopy(raw_arg), None, None
    text = str(raw_arg).strip()
    if not text:
        return None, None, None
    target, rel, path_err = _resolve_contained_path(
        root_path, text, label=label, entity_id=entity_id
    )
    if path_err is not None or target is None:
        return None, rel, path_err
    if not os.path.lexists(target):
        return (
            None,
            rel,
            _diag(
                codec.ReasonCode.FILE_NOT_FOUND,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected=f"existing JSON file for {label}",
                actual={"path": rel, "exists": False},
                resume_ref=rel,
            ),
        )
    try:
        inventory.no_reparse(target)
        if not target.is_file():
            raise ValueError("not a regular file")
        parsed = codec.strict_json_loads(target.read_bytes())
        return parsed, rel, None
    except (codec.CodecError, OSError, ValueError) as exc:
        rc = (
            exc.diagnostic.reason_code
            if isinstance(exc, codec.CodecError)
            else codec.ReasonCode.INVALID_JSON
        )
        return (
            None,
            rel,
            _diag(
                rc,
                stage=codec.Stage.DECODE,
                entity_id=entity_id,
                expected=f"valid JSON for {label}",
                actual={"path": rel, "error": f"{type(exc).__name__}: {exc}"},
                resume_ref=rel,
            ),
        )


def _file_raw_digest(root_path: Path, rel_path: str) -> str | None:
    norm = _norm_rel(rel_path)
    if not norm:
        return None
    target, _rel, err = _resolve_contained_path(root_path, norm, label="digest_ref", entity_id=norm)
    if err is not None or target is None:
        return None
    try:
        if not target.is_file():
            return None
        inventory.no_reparse(target)
        return codec.raw_digest(target.read_bytes())
    except (codec.CodecError, OSError, ValueError):
        return None


def _evidence_ref(root_path: Path, rel_path: str | None, *, fallback_digest: str | None = None) -> dict[str, Any] | None:
    if not rel_path:
        return None
    norm = _norm_rel(rel_path)
    digest = _file_raw_digest(root_path, norm) or fallback_digest
    return {"path": norm, "raw_digest": digest}


def _declaring_evidence_ref(
    root_path: Path,
    candidates: list[str | None],
    *,
    fallback_digest: str | None = None,
) -> dict[str, Any]:
    """Resolve a guaranteed non-null {path, raw_digest} pointing to the live declaring binding/manifest/plan."""
    first_nonempty: str | None = None
    for cand in candidates:
        if not cand:
            continue
        norm = _norm_rel(cand)
        if not norm:
            continue
        if first_nonempty is None:
            first_nonempty = norm
        digest = _file_raw_digest(root_path, norm)
        if digest:
            return {"path": norm, "raw_digest": digest}
    chosen = first_nonempty or records.CATALOG_PATH
    return {
        "path": chosen,
        "raw_digest": fallback_digest or codec.canonical_digest({"declaring_ref": chosen}),
    }


def _make_item(
    *,
    item_id: str,
    category: str,
    status: str,
    binding_ref: str | None,
    task_id: int | None,
    flow_id: str | None,
    evidence_ref: dict[str, Any] | None,
    summary: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "category": category,
        "status": status,
        "binding_ref": binding_ref,
        "task_id": task_id,
        "flow_id": flow_id,
        "evidence_ref": evidence_ref,
        "summary": summary,
        "details": deepcopy(details or {}),
    }


def _is_godot_type_compatible(
    actual_type: str,
    expected_type: str,
    *,
    node_script_class: tuple[str, str | None] | None = None,
    script_class_bases: dict[str, str] | None = None,
) -> bool:
    """Check whether actual_type (or attached C# script subclass) is compatible with expected_type in Godot."""
    a = str(actual_type or "").strip().split(".")[-1]
    e = str(expected_type or "").strip().split(".")[-1]
    if not a or not e:
        return True
    if e == "Node":
        return True
    if a == e:
        return True

    parent_map = dict(_GODOT_TYPE_PARENT)
    if script_class_bases:
        for cname, base in script_class_bases.items():
            if cname and base:
                parent_map[cname] = base.split(".")[-1]

    def _inherits(start: str, target: str) -> bool:
        if start == target:
            return True
        cur = start
        visited: set[str] = set()
        while cur in parent_map and cur not in visited:
            visited.add(cur)
            cur = parent_map[cur]
            if cur == target:
                return True
        return False

    if _inherits(a, e):
        return True
    if node_script_class is not None:
        cls_name, base_type = node_script_class
        if cls_name and _inherits(cls_name, e):
            return True
        if base_type and _inherits(base_type.split(".")[-1], e):
            return True
    return False


def _res_to_repo_rel(res_path: str) -> str:
    s = str(res_path or "").strip()
    if s.startswith("res://"):
        s = s.removeprefix("res://")
    return _norm_rel(s)


def _is_manual_sub_resource_type(sub_type: str) -> bool:
    return sub_type in {"Animation", "AnimationLibrary", "Theme"} or sub_type.startswith("StyleBox")


def _parse_tscn(scene_text: str) -> dict[str, Any]:
    """Deterministically parse a Godot .tscn file into ext_resources, nodes, connections, and manual regions."""
    ext_resources: dict[str, str] = {}
    for m in _EXT_RES_RE.finditer(scene_text):
        ext_resources[m.group(2)] = m.group(1)
    for m in _EXT_RES_ALT_RE.finditer(scene_text):
        ext_resources.setdefault(m.group(1), m.group(2))

    nodes: dict[str, dict[str, Any]] = {}
    unique_names: dict[str, str] = {}
    connections: list[dict[str, str]] = []
    manual_regions: list[dict[str, Any]] = []
    sub_resources: list[dict[str, str]] = []

    current_node_path: str | None = None
    current_sub_res: dict[str, Any] | None = None
    current_sub_lines: list[str] = []
    root_name: str | None = None

    def _flush_sub_res() -> None:
        nonlocal current_sub_res, current_sub_lines
        if current_sub_res is not None:
            sub_type = current_sub_res.get("type", "")
            if _is_manual_sub_resource_type(sub_type):
                body_blob = "\n".join(current_sub_lines).encode("utf-8")
                manual_regions.append(
                    {
                        "kind": "sub_resource",
                        "type": sub_type,
                        "id": current_sub_res.get("id", ""),
                        "body_hash": codec.raw_digest(body_blob),
                    }
                )
        current_sub_res = None
        current_sub_lines = []

    for raw_line in scene_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m_sub = _SUB_RES_HEADER_RE.match(line)
        if m_sub:
            _flush_sub_res()
            current_node_path = None
            attrs = dict(_ATTR_RE.findall(m_sub.group(1)))
            sub_resources.append(attrs)
            current_sub_res = attrs
            current_sub_lines = []
            continue

        m_node = _NODE_HEADER_RE.match(line)
        if m_node:
            _flush_sub_res()
            header_body = m_node.group(1)
            attrs = dict(_ATTR_RE.findall(header_body))
            name = attrs.get("name", "")
            ntype = attrs.get("type", "")
            parent = attrs.get("parent")
            m_inst = _INSTANCE_EXT_RE.search(header_body)
            inst_res = None
            if m_inst:
                inst_id = m_inst.group(1)
                inst_res = ext_resources.get(inst_id) or inst_id
            if parent is None:
                node_path = "."
                root_name = name
            elif parent == ".":
                node_path = name
            else:
                node_path = f"{parent}/{name}"
            nodes[node_path] = {
                "name": name,
                "type": ntype,
                "parent": parent,
                "path": node_path,
                "script_res": None,
                "instance_res": inst_res,
                "unique": False,
                "manual_props": {},
            }
            if ntype in {"AnimationPlayer", "AudioStreamPlayer", "GPUParticles2D", "CPUParticles2D"}:
                manual_regions.append(
                    {
                        "kind": "node",
                        "path": node_path,
                        "type": ntype,
                    }
                )
            current_node_path = node_path
            continue

        m_conn = _CONN_HEADER_RE.match(line)
        if m_conn:
            _flush_sub_res()
            current_node_path = None
            attrs = dict(_ATTR_RE.findall(m_conn.group(1)))
            connections.append(
                {
                    "signal": attrs.get("signal", ""),
                    "from": attrs.get("from", ""),
                    "to": attrs.get("to", ""),
                    "method": attrs.get("method", ""),
                }
            )
            continue

        if line.startswith("["):
            _flush_sub_res()
            current_node_path = None
            continue

        if current_sub_res is not None:
            current_sub_lines.append(line)
            continue

        if current_node_path is not None and current_node_path in nodes:
            node_info = nodes[current_node_path]
            m_script = _SCRIPT_EXT_RE.match(line)
            if m_script:
                res_id = m_script.group(1)
                node_info["script_res"] = ext_resources.get(res_id) or res_id
                continue
            if line.replace(" ", "") == "unique_name_in_owner=true":
                node_info["unique"] = True
                unique_names[node_info["name"]] = current_node_path
                continue
            if "=" in line:
                prop_key, prop_val = [p.strip() for p in line.split("=", 1)]
                if any(prop_key == pref or prop_key.startswith(pref) for pref in _MANUAL_PROP_PREFIXES):
                    node_info["manual_props"][prop_key] = prop_val
                    manual_regions.append(
                        {
                            "kind": "property",
                            "path": current_node_path,
                            "property": prop_key,
                            "value": prop_val,
                        }
                    )

    _flush_sub_res()

    return {
        "root_name": root_name,
        "ext_resources": ext_resources,
        "nodes": nodes,
        "unique_names": unique_names,
        "connections": connections,
        "sub_resources": sub_resources,
        "manual_regions": manual_regions,
    }


def _parse_tscn_with_instances(
    root_path: Path,
    srel: str,
    *,
    depth: int = 0,
    visited: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Parse a .tscn file and recursively resolve child scene instances via instance=ExtResource(...)."""
    findings: list[dict[str, Any]] = []
    target, canon_rel, path_err = _resolve_contained_path(
        root_path, srel, label="scene_path", entity_id=srel
    )
    if path_err is not None or target is None or canon_rel is None:
        findings.append(
            {
                "failure_kind": "unsafe_scene_path",
                "status": "failed",
                "scene_path": srel,
                "adapter_path": None,
                "node_path": None,
                "message": f"Scene path escapes repository or crosses reparse point: {srel}",
                "return_stage": "4",
            }
        )
        return None, findings
    if not target.is_file():
        findings.append(
            {
                "failure_kind": "missing_scene_file" if depth == 0 else "broken_node_binding",
                "status": "failed",
                "scene_path": canon_rel,
                "adapter_path": None,
                "node_path": None,
                "message": (
                    f"Declared target-slice scene file does not exist: {canon_rel}"
                    if depth == 0
                    else f"Instanced child scene does not exist: {canon_rel}"
                ),
                "return_stage": "4",
            }
        )
        return None, findings

    text = target.read_text(encoding="utf-8", errors="replace")
    parsed = _parse_tscn(text)
    if depth >= 16 or canon_rel in visited:
        return parsed, findings

    next_visited = visited | {canon_rel}
    node_items = list(parsed["nodes"].items())
    for npath, ninfo in node_items:
        inst_res = ninfo.get("instance_res")
        if not inst_res:
            continue
        child_rel = _res_to_repo_rel(inst_res)
        child_parsed, child_findings = _parse_tscn_with_instances(
            root_path, child_rel, depth=depth + 1, visited=next_visited
        )
        for cf in child_findings:
            if cf.get("node_path") is None:
                cf["node_path"] = npath
            findings.append(cf)
        if child_parsed is None:
            continue
        child_root = child_parsed["nodes"].get(".")
        if child_root is not None:
            if ninfo.get("type") and child_root.get("type"):
                if not _is_godot_type_compatible(child_root["type"], ninfo["type"]):
                    findings.append(
                        {
                            "failure_kind": "object_type_mismatch",
                            "status": "failed",
                            "scene_path": canon_rel,
                            "adapter_path": None,
                            "node_path": npath,
                            "message": (
                                f"Instanced scene '{child_rel}' root type '{child_root['type']}' "
                                f"is incompatible with node '{npath}' type '{ninfo['type']}' in {canon_rel}"
                            ),
                            "return_stage": "4",
                        }
                    )
            if not ninfo.get("type") and child_root.get("type"):
                ninfo["type"] = child_root["type"]
            if not ninfo.get("script_res") and child_root.get("script_res"):
                ninfo["script_res"] = child_root["script_res"]
        for cpath, cinfo in child_parsed["nodes"].items():
            if cpath == ".":
                continue
            merged_path = cpath if npath == "." else f"{npath}/{cpath}"
            if merged_path not in parsed["nodes"]:
                merged_node = deepcopy(cinfo)
                merged_node["path"] = merged_path
                parsed["nodes"][merged_path] = merged_node
            else:
                # Preserve parent override while inheriting child type/script if omitted in parent.
                existing_n = parsed["nodes"][merged_path]
                if not existing_n.get("type") and cinfo.get("type"):
                    existing_n["type"] = cinfo["type"]
                if not existing_n.get("script_res") and cinfo.get("script_res"):
                    existing_n["script_res"] = cinfo["script_res"]

    return parsed, findings


def _resolve_scene_node(
    parsed_scene: dict[str, Any],
    raw_ref: str,
    *,
    owner_path: str = ".",
) -> dict[str, Any] | None:
    """Resolve a Godot node path relative to owner_path (supports '.', '..', and '%UniqueName', no bare-name fallback)."""
    ref = str(raw_ref or "").strip()
    if not ref:
        return None
    nodes = parsed_scene["nodes"]
    norm_owner = "." if not owner_path or owner_path == "." else _norm_rel(owner_path)
    if ref == ".":
        return nodes.get(norm_owner)
    if ref.startswith("%"):
        body = ref[1:]
        uname = body.split("/", 1)[0]
        target_path = parsed_scene["unique_names"].get(uname)
        if not target_path:
            return None
        rest = body.split("/", 1)[1] if "/" in body else ""
        if not rest:
            return nodes.get(target_path)
        return _resolve_scene_node(parsed_scene, rest, owner_path=target_path)

    cleaned = ref.replace("\\", "/")
    if cleaned.startswith("/"):
        # Absolute tree paths are outside local scene-tree relative binding unless anchored at root name.
        return None
    base_parts = [] if norm_owner == "." else [p for p in norm_owner.split("/") if p]
    for seg in cleaned.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if not base_parts:
                return None
            base_parts.pop()
        else:
            base_parts.append(seg)
    resolved_path = "." if not base_parts else "/".join(base_parts)
    return nodes.get(resolved_path)


def _extract_cs_constructor_bodies(cs_clean_text: str) -> list[tuple[str, str]]:
    """Extract C# class constructor bodies from comment/string-stripped source for lifecycle checks."""
    out: list[tuple[str, str]] = []
    for m_cls in _CS_CLASS_RE.finditer(cs_clean_text):
        cls_name = m_cls.group(1)
        ctor_re = re.compile(
            rf"\b(?:(?:public|private|protected|internal)\s+)?{re.escape(cls_name)}\s*\([^)]*\)\s*(?::\s*(?:base|this)\s*\([^)]*\)\s*)?\{{",
            re.MULTILINE,
        )
        for m_ctor in ctor_re.finditer(cs_clean_text, m_cls.end()):
            start = m_ctor.end()
            depth = 1
            idx = start
            while idx < len(cs_clean_text) and depth > 0:
                ch = cs_clean_text[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                idx += 1
            out.append((cls_name, cs_clean_text[start : max(start, idx - 1)]))
    return out


def _extract_cs_ready_bodies(cs_clean_text: str) -> list[str]:
    ready_re = re.compile(r"\boverride\s+void\s+_Ready\s*\(\s*\)\s*\{", re.MULTILINE)
    bodies: list[str] = []
    for m in ready_re.finditer(cs_clean_text):
        start = m.end()
        depth = 1
        idx = start
        while idx < len(cs_clean_text) and depth > 0:
            if cs_clean_text[idx] == "{":
                depth += 1
            elif cs_clean_text[idx] == "}":
                depth -= 1
            idx += 1
        bodies.append(cs_clean_text[start : max(start, idx - 1)])
    return bodies


def inspect_scene_and_adapter_wiring(
    root_path: Path,
    *,
    scene_paths: list[str],
    adapter_paths: list[str],
    binding_objects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministically inspect .tscn scenes (recursively) and C#/GD adapters for honest AC-3 checks."""
    findings: list[dict[str, Any]] = []
    parsed_scenes: dict[str, dict[str, Any]] = {}
    manual_region_inventory: dict[str, list[dict[str, Any]]] = {}
    scene_node_script_classes: dict[str, dict[str, tuple[str, str | None]]] = {}
    script_class_bases: dict[str, str] = {}

    all_scene_paths: list[str] = []
    seen_scenes: set[str] = set()
    for p in scene_paths:
        raw_p = str(p or "").strip()
        if not raw_p:
            continue
        _target, canon, path_err = _resolve_contained_path(
            root_path, raw_p, label="scene_path", entity_id=raw_p
        )
        if path_err is not None or canon is None:
            findings.append(
                {
                    "failure_kind": "unsafe_scene_path",
                    "status": "failed",
                    "scene_path": raw_p,
                    "adapter_path": None,
                    "node_path": None,
                    "message": f"Declared scene path escapes repository or crosses reparse point: {raw_p}",
                    "return_stage": "4",
                }
            )
            continue
        if canon.endswith(".tscn") and canon not in seen_scenes:
            seen_scenes.add(canon)
            all_scene_paths.append(canon)

    all_adapter_paths: list[str] = []
    seen_adapters: set[str] = set()
    for p in adapter_paths:
        raw_p = str(p or "").strip()
        if not raw_p:
            continue
        _target, canon, path_err = _resolve_contained_path(
            root_path, raw_p, label="adapter_path", entity_id=raw_p
        )
        if path_err is not None or canon is None:
            findings.append(
                {
                    "failure_kind": "unsafe_adapter_path",
                    "status": "failed",
                    "scene_path": all_scene_paths[0] if all_scene_paths else None,
                    "adapter_path": raw_p,
                    "node_path": None,
                    "message": f"Declared adapter path escapes repository or crosses reparse point: {raw_p}",
                    "return_stage": "4",
                }
            )
            continue
        if canon.endswith((".cs", ".gd")) and canon not in seen_adapters:
            seen_adapters.add(canon)
            all_adapter_paths.append(canon)

    for srel in all_scene_paths:
        parsed, scene_findings = _parse_tscn_with_instances(root_path, srel)
        findings.extend(scene_findings)
        if parsed is None:
            continue
        parsed_scenes[srel] = parsed
        manual_region_inventory[srel] = list(parsed["manual_regions"])
        node_classes: dict[str, tuple[str, str | None]] = {}
        scene_node_script_classes[srel] = node_classes

        # Collect attached scripts from scene nodes (including inherited scripts from instanced child scenes).
        attached_methods: dict[str, set[str]] = {}
        for npath, ninfo in parsed["nodes"].items():
            sres = ninfo.get("script_res")
            if not sres:
                continue
            raw_script_rel = _res_to_repo_rel(sres)
            script_file, script_rel, path_err = _resolve_contained_path(
                root_path, raw_script_rel, label="script_res", entity_id=f"{srel}:{npath}"
            )
            if path_err is not None or script_file is None or script_rel is None:
                findings.append(
                    {
                        "failure_kind": "broken_script_attachment",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": raw_script_rel,
                        "node_path": npath,
                        "message": f"Scene {srel} node '{npath}' attaches unsafe script path {raw_script_rel}",
                        "return_stage": "4",
                    }
                )
                continue
            if not script_file.is_file():
                findings.append(
                    {
                        "failure_kind": "broken_script_attachment",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": script_rel,
                        "node_path": npath,
                        "message": f"Scene {srel} node '{npath}' attaches missing script {script_rel}",
                        "return_stage": "4",
                    }
                )
                continue
            if script_rel not in seen_adapters and script_rel.endswith((".cs", ".gd")):
                seen_adapters.add(script_rel)
                all_adapter_paths.append(script_rel)
            stext = script_file.read_text(encoding="utf-8", errors="replace")
            if script_rel.endswith(".cs"):
                clean_cs = _strip_comments(stext, is_cs=True, mask_strings=True)
                methods = {m for m in _CS_METHOD_RE.findall(clean_cs) if m not in _CS_CONTROL_KEYWORDS}
                attached_methods[npath] = methods
                for m_cls in _CS_CLASS_RE.finditer(clean_cs):
                    cname = m_cls.group(1)
                    bname = m_cls.group(2)
                    if cname:
                        node_classes.setdefault(npath, (cname, bname))
                        if bname:
                            script_class_bases[cname] = bname.split(".")[-1]
            else:
                clean_gd = _strip_comments(stext, is_cs=False, mask_strings=True)
                attached_methods[npath] = set(_GD_FUNC_RE.findall(clean_gd))

        # Check all [connection] signal bindings (paths relative to scene root).
        for conn in parsed["connections"]:
            from_node = _resolve_scene_node(parsed, conn["from"], owner_path=".")
            to_node = _resolve_scene_node(parsed, conn["to"], owner_path=".")
            method = conn["method"]
            if from_node is None:
                findings.append(
                    {
                        "failure_kind": "broken_signal_binding",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": None,
                        "node_path": conn["from"],
                        "message": f"Broken signal '{conn['signal']}': source node '{conn['from']}' not found in {srel}",
                        "return_stage": "4",
                    }
                )
            if to_node is None:
                findings.append(
                    {
                        "failure_kind": "broken_signal_binding",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": None,
                        "node_path": conn["to"],
                        "message": f"Broken signal '{conn['signal']}': target node '{conn['to']}' not found in {srel}",
                        "return_stage": "4",
                    }
                )
            elif method and method not in _GODOT_BUILTIN_NODE_METHODS:
                target_path = to_node["path"]
                if target_path in attached_methods and method not in attached_methods[target_path]:
                    findings.append(
                        {
                            "failure_kind": "broken_signal_binding",
                            "status": "failed",
                            "scene_path": srel,
                            "adapter_path": _res_to_repo_rel(to_node.get("script_res") or ""),
                            "node_path": target_path,
                            "message": (
                                f"Broken signal '{conn['signal']}': handler method '{method}' "
                                f"missing on node '{target_path}' script in {srel}"
                            ),
                            "return_stage": "4",
                        }
                    )
                elif target_path not in attached_methods and not to_node.get("script_res"):
                    findings.append(
                        {
                            "failure_kind": "lifecycle_mismatch",
                            "status": "failed",
                            "scene_path": srel,
                            "adapter_path": None,
                            "node_path": target_path,
                            "message": (
                                f"Signal '{conn['signal']}' targets method '{method}' on node '{target_path}' "
                                f"without an attached script in {srel}"
                            ),
                            "return_stage": "4",
                        }
                    )

        # Check root script presence if adapters exist for this slice.
        root_node = parsed["nodes"].get(".")
        if all_adapter_paths and root_node is not None and not root_node.get("script_res"):
            any_script = any(n.get("script_res") for n in parsed["nodes"].values())
            if not any_script:
                findings.append(
                    {
                        "failure_kind": "lifecycle_mismatch",
                        "status": "failed",
                        "scene_path": srel,
                        "adapter_path": all_adapter_paths[0],
                        "node_path": ".",
                        "message": f"Scene {srel} has no attached adapter script despite bound adapter {all_adapter_paths[0]}",
                        "return_stage": "4",
                    }
                )

    # Check adapter GetNode<T> bindings, type compatibility, and lifecycle anti-patterns.
    for arel in all_adapter_paths:
        afile, canon_arel, path_err = _resolve_contained_path(
            root_path, arel, label="adapter_path", entity_id=arel
        )
        if path_err is not None or afile is None or canon_arel is None:
            findings.append(
                {
                    "failure_kind": "unsafe_adapter_path",
                    "status": "failed",
                    "scene_path": all_scene_paths[0] if all_scene_paths else None,
                    "adapter_path": arel,
                    "node_path": None,
                    "message": f"Declared adapter path is unsafe: {arel}",
                    "return_stage": "4",
                }
            )
            continue
        if not afile.is_file():
            findings.append(
                {
                    "failure_kind": "missing_adapter_file",
                    "status": "failed",
                    "scene_path": all_scene_paths[0] if all_scene_paths else None,
                    "adapter_path": canon_arel,
                    "node_path": None,
                    "message": f"Declared adapter file does not exist: {canon_arel}",
                    "return_stage": "4",
                }
            )
            continue
        atext = afile.read_text(encoding="utf-8", errors="replace")

        # Match this adapter to (scene, owner_node_path) pairs where it is attached.
        attached_targets: list[tuple[str, str]] = []
        for srel, parsed in parsed_scenes.items():
            for npath, ninfo in parsed["nodes"].items():
                if _res_to_repo_rel(ninfo.get("script_res") or "").casefold() == canon_arel.casefold():
                    attached_targets.append((srel, npath))
        candidate_targets = attached_targets or [(srel, ".") for srel in parsed_scenes.keys()]

        if canon_arel.endswith(".cs"):
            no_comments = _strip_comments(atext, is_cs=True, mask_strings=False)
            clean_code = _strip_comments(atext, is_cs=True, mask_strings=True)
            for m_cls in _CS_CLASS_RE.finditer(clean_code):
                if m_cls.group(1) and m_cls.group(2):
                    script_class_bases[m_cls.group(1)] = m_cls.group(2).split(".")[-1]

            # Lifecycle anti-pattern 1: accessing scene tree nodes in constructor before _Ready().
            for cls_name, ctor_body in _extract_cs_constructor_bodies(clean_code):
                if re.search(r"\b(?:GetNode|GetNodeOrNull|GetTree)\s*[<\(]", ctor_body):
                    findings.append(
                        {
                            "failure_kind": "lifecycle_mismatch",
                            "status": "failed",
                            "scene_path": candidate_targets[0][0] if candidate_targets else None,
                            "adapter_path": canon_arel,
                            "node_path": candidate_targets[0][1] if candidate_targets else ".",
                            "message": (
                                f"Lifecycle mismatch in {canon_arel}: constructor '{cls_name}' accesses "
                                "scene tree nodes before _Ready()"
                            ),
                            "return_stage": "6",
                        }
                    )
            # Lifecycle anti-pattern 2: unconditional self QueueFree/Free inside _Ready().
            for ready_body in _extract_cs_ready_bodies(clean_code):
                has_self_free = bool(
                    re.search(r"(?<![A-Za-z0-9_\.])(?:this\.)?(?:QueueFree|Free)\s*\(\s*\)", ready_body)
                )
                has_guard = bool(re.search(r"\bif\b|\?", ready_body))
                if has_self_free and not has_guard:
                    findings.append(
                        {
                            "failure_kind": "lifecycle_mismatch",
                            "status": "failed",
                            "scene_path": candidate_targets[0][0] if candidate_targets else None,
                            "adapter_path": canon_arel,
                            "node_path": candidate_targets[0][1] if candidate_targets else ".",
                            "message": (
                                f"Lifecycle mismatch in {canon_arel}: _Ready() unconditionally frees active bound surface"
                            ),
                            "return_stage": "6",
                        }
                    )

            # Verify GetNode<T>("path") bindings & node types relative to each attached owner node.
            if candidate_targets:
                for m_gn in _CS_GETNODE_RE.finditer(no_comments):
                    expected_t = m_gn.group(1).strip()
                    node_ref = m_gn.group(2).strip()
                    matched_node = None
                    matched_scene = None
                    for srel, owner_npath in candidate_targets:
                        found = _resolve_scene_node(parsed_scenes[srel], node_ref, owner_path=owner_npath)
                        if found is not None:
                            matched_node = found
                            matched_scene = srel
                            break
                    if matched_node is None:
                        findings.append(
                            {
                                "failure_kind": "broken_node_binding",
                                "status": "failed",
                                "scene_path": candidate_targets[0][0],
                                "adapter_path": canon_arel,
                                "node_path": node_ref,
                                "message": (
                                    f"Broken node binding in {canon_arel}: GetNode<{expected_t}>(\"{node_ref}\") "
                                    f"not found in {candidate_targets[0][0]}"
                                ),
                                "return_stage": "4",
                            }
                        )
                    else:
                        actual_t = matched_node.get("type", "")
                        n_cls = (
                            scene_node_script_classes.get(matched_scene or "", {}).get(matched_node["path"])
                            if matched_scene
                            else None
                        )
                        if actual_t and not _is_godot_type_compatible(
                            actual_t,
                            expected_t,
                            node_script_class=n_cls,
                            script_class_bases=script_class_bases,
                        ):
                            findings.append(
                                {
                                    "failure_kind": "object_type_mismatch",
                                    "status": "failed",
                                    "scene_path": matched_scene,
                                    "adapter_path": canon_arel,
                                    "node_path": node_ref,
                                    "message": (
                                        f"Object type mismatch in {canon_arel} vs {matched_scene}: "
                                        f"node '{node_ref}' is '{actual_t}' in .tscn but bound as '{expected_t}'"
                                    ),
                                    "return_stage": "4",
                                }
                            )
                for m_untyped in _CS_GETNODE_UNTYPED_RE.finditer(no_comments):
                    node_ref = m_untyped.group(1).strip()
                    if not any(
                        _resolve_scene_node(parsed_scenes[srel], node_ref, owner_path=owner_npath) is not None
                        for srel, owner_npath in candidate_targets
                    ):
                        findings.append(
                            {
                                "failure_kind": "broken_node_binding",
                                "status": "failed",
                                "scene_path": candidate_targets[0][0],
                                "adapter_path": canon_arel,
                                "node_path": node_ref,
                                "message": (
                                    f"Broken node binding in {canon_arel}: GetNode(\"{node_ref}\") "
                                    f"not found in {candidate_targets[0][0]}"
                                ),
                                "return_stage": "4",
                            }
                        )
        elif canon_arel.endswith(".gd") and candidate_targets:
            no_comments_gd = _strip_comments(atext, is_cs=False, mask_strings=False)
            for m_gd in _GD_NODE_REF_RE.finditer(no_comments_gd):
                node_ref = (m_gd.group(1) or m_gd.group(2) or m_gd.group(3) or "").strip()
                if not node_ref:
                    continue
                if not any(
                    _resolve_scene_node(parsed_scenes[srel], node_ref, owner_path=owner_npath) is not None
                    for srel, owner_npath in candidate_targets
                ):
                    findings.append(
                        {
                            "failure_kind": "broken_node_binding",
                            "status": "failed",
                            "scene_path": candidate_targets[0][0],
                            "adapter_path": canon_arel,
                            "node_path": node_ref,
                            "message": (
                                f"Broken node binding in {canon_arel}: node ref '{node_ref}' "
                                f"not found in {candidate_targets[0][0]}"
                            ),
                            "return_stage": "4",
                        }
                    )

    # Check Stage-4 binding_objects declared node_paths and expected_type against .tscn.
    for obj in binding_objects:
        if obj.get("availability") != "existing":
            continue
        kind = obj.get("kind")
        if kind not in {"binding", "scene", "adapter"}:
            continue
        meta = ch4_binding._parse_prefixed_json(obj.get("lifecycle", ""), ch4_binding.STAGE4_LIFECYCLE_PREFIX) or {}
        declared_paths = list(meta.get("node_paths") or [])
        expected_type = str(obj.get("expected_type") or "").strip()
        if declared_paths and parsed_scenes:
            for nref in declared_paths:
                nref_s = str(nref).strip()
                if not nref_s:
                    continue
                matched = None
                matched_srel = None
                for srel, parsed in parsed_scenes.items():
                    found = _resolve_scene_node(parsed, nref_s, owner_path=".")
                    if found is not None:
                        matched = found
                        matched_srel = srel
                        break
                if matched is None:
                    findings.append(
                        {
                            "failure_kind": "broken_node_binding",
                            "status": "failed",
                            "scene_path": all_scene_paths[0] if all_scene_paths else None,
                            "adapter_path": None,
                            "node_path": nref_s,
                            "message": f"Stage-4 binding '{obj.get('id')}' node_path '{nref_s}' missing in target .tscn",
                            "return_stage": "4",
                        }
                    )
                elif kind == "binding" and expected_type and matched.get("type"):
                    n_cls = scene_node_script_classes.get(matched_srel or "", {}).get(matched["path"])
                    if not _is_godot_type_compatible(
                        matched["type"],
                        expected_type,
                        node_script_class=n_cls,
                        script_class_bases=script_class_bases,
                    ):
                        findings.append(
                            {
                                "failure_kind": "object_type_mismatch",
                                "status": "failed",
                                "scene_path": matched_srel,
                                "adapter_path": None,
                                "node_path": nref_s,
                                "message": (
                                    f"Stage-4 binding '{obj.get('id')}' expects '{expected_type}' "
                                    f"but node '{nref_s}' in {matched_srel} is '{matched['type']}'"
                                ),
                                "return_stage": "4",
                            }
                        )

    return {
        "wiring_static_ok": len(findings) == 0,
        "scenes_inspected": all_scene_paths,
        "adapters_inspected": all_adapter_paths,
        "findings": findings,
        "parsed_scenes": parsed_scenes,
        "manual_region_inventory": manual_region_inventory,
    }


def _inspect_test_file_integrity(root_path: Path, rel_path: str) -> dict[str, Any]:
    target, canon, path_err = _resolve_contained_path(
        root_path, rel_path, label="test_path", entity_id=rel_path
    )
    if path_err is not None or target is None or canon is None:
        return {"exists": False, "path": str(rel_path), "sha256": None, "status": "unsafe", "reason": "unsafe_test_path"}
    if not target.is_file():
        return {"exists": False, "path": canon, "sha256": None, "status": "missing", "reason": "test_file_missing"}
    raw = target.read_bytes()
    digest = codec.raw_digest(raw)
    text = raw.decode("utf-8", errors="replace")
    is_cs = canon.lower().endswith(".cs")
    stripped = _strip_comments(text, is_cs=is_cs, mask_strings=False)
    if not stripped.strip():
        return {"exists": True, "path": canon, "sha256": digest, "status": "empty", "reason": "empty_test_file"}
    for pat in _TEST_SKIP_PATTERNS:
        if pat.search(stripped):
            return {"exists": True, "path": canon, "sha256": digest, "status": "skipped", "reason": "skipped_test_attribute"}
    if is_cs and not _CS_TEST_ATTR_RE.search(stripped):
        return {"exists": True, "path": canon, "sha256": digest, "status": "empty", "reason": "no_test_methods_found"}
    if canon.lower().endswith(".gd") and not _GD_TEST_FUNC_RE.search(stripped):
        return {"exists": True, "path": canon, "sha256": digest, "status": "empty", "reason": "no_gd_test_functions_found"}
    return {"exists": True, "path": canon, "sha256": digest, "status": "valid", "reason": "ok"}


def _collect_ui_evidence_records(
    root_path: Path,
    *,
    target_tids: set[int],
    evidence_dir: str | Path | None,
    ui_evidence_arg: dict[str, Any] | list[Any] | str | Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read-only collection of Chapter 6 / runtime UI evidence records with strict containment & reparse checks."""
    records_out: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    root_resolved = root_path.resolve()

    def _ingest_payload(payload: Any, source_rel: str | None, source_digest: str | None) -> None:
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict):
                    item = deepcopy(entry)
                    item.setdefault("_source_path", source_rel)
                    item.setdefault("_source_digest", source_digest)
                    records_out.append(item)
            return
        if not isinstance(payload, dict):
            return
        if isinstance(payload.get("evidence"), list):
            for entry in payload["evidence"]:
                if isinstance(entry, dict):
                    item = deepcopy(entry)
                    item.setdefault("_source_path", source_rel)
                    item.setdefault("_source_digest", source_digest)
                    records_out.append(item)
            return
        if isinstance(payload.get("ui_evidence"), list):
            for entry in payload["ui_evidence"]:
                if isinstance(entry, dict):
                    item = deepcopy(entry)
                    item.setdefault("_source_path", source_rel)
                    item.setdefault("_source_digest", source_digest)
                    records_out.append(item)
            return
        if any(k in payload for k in ("test_path", "evidence_kind", "input_set_digest", "real_engine_input")):
            item = deepcopy(payload)
            item.setdefault("_source_path", source_rel)
            item.setdefault("_source_digest", source_digest)
            records_out.append(item)

    if ui_evidence_arg is not None:
        parsed, rel, err = _safe_load_json_arg(
            root_path, ui_evidence_arg, label="ui_evidence", entity_id="ui_evidence"
        )
        if err is not None:
            diags.append(err)
        else:
            if rel:
                seen_files.add(rel)
            src_digest = _file_raw_digest(root_path, rel) if rel else codec.canonical_digest(parsed)
            _ingest_payload(parsed, rel or "inline:ui_evidence", src_digest)

    scan_dirs: list[Path] = []
    if evidence_dir is not None and str(evidence_dir).strip():
        target, rel_dir, err = _resolve_contained_path(
            root_path, evidence_dir, label="evidence_dir", entity_id="evidence_dir"
        )
        if err is not None:
            diags.append(err)
        elif target is not None:
            if not os.path.lexists(target):
                diags.append(
                    _diag(
                        codec.ReasonCode.FILE_NOT_FOUND,
                        stage=codec.Stage.PATH,
                        entity_id="evidence_dir",
                        expected="existing repository-contained evidence directory",
                        actual={"path": rel_dir, "exists": False},
                        resume_ref=rel_dir,
                    )
                )
            elif not target.is_dir():
                diags.append(
                    _diag(
                        codec.ReasonCode.INVALID_ARGUMENT,
                        stage=codec.Stage.PATH,
                        entity_id="evidence_dir",
                        expected="directory path for --evidence-dir",
                        actual={"path": rel_dir, "is_dir": False},
                        resume_ref=rel_dir,
                    )
                )
            else:
                try:
                    _check_ancestors_no_reparse(root_resolved, target)
                    scan_dirs.append(target)
                except (codec.CodecError, ValueError, OSError) as exc:
                    diags.append(
                        _diag(
                            codec.ReasonCode.UNSAFE_PATH,
                            stage=codec.Stage.PATH,
                            entity_id="evidence_dir",
                            expected="non-reparse directory for --evidence-dir",
                            actual={"path": rel_dir, "error": f"{type(exc).__name__}: {exc}"},
                            resume_ref=rel_dir,
                        )
                    )
    else:
        logs_ci = root_resolved / "logs" / "ci"
        if logs_ci.is_dir():
            try:
                _check_ancestors_no_reparse(root_resolved, logs_ci)
                scan_dirs.append(logs_ci)
            except (codec.CodecError, ValueError, OSError):
                pass

    for base in scan_dirs:
        patterns = (
            "**/chapter6-ui-evidence*.json",
            "**/ui-evidence*.json",
            "project-health-knowledge/runtime/task-*.json",
            "*/sc-review-pipeline-task-*/ui-evidence.json",
            "*/sc-review-pipeline-task-*/gdunit-summary.json",
        )
        for pat in patterns:
            for fpath in sorted(base.glob(pat)):
                if not fpath.is_file():
                    continue
                try:
                    _check_ancestors_no_reparse(root_resolved, fpath)
                    canon_target, rel, cerr = _resolve_contained_path(
                        root_resolved, fpath, label="scanned_evidence", entity_id="evidence_dir"
                    )
                    if cerr is not None or canon_target is None or rel is None:
                        continue
                except (codec.CodecError, ValueError, OSError):
                    continue
                if rel in seen_files:
                    continue
                seen_files.add(rel)
                try:
                    raw = canon_target.read_bytes()
                    parsed = codec.strict_json_loads(raw)
                except (codec.CodecError, OSError):
                    continue
                if isinstance(parsed, dict) and target_tids:
                    tid_val = parsed.get("task_id")
                    if tid_val is not None and not isinstance(tid_val, bool):
                        try:
                            if int(tid_val) not in target_tids:
                                continue
                        except (TypeError, ValueError):
                            pass
                _ingest_payload(parsed, rel, codec.raw_digest(raw))

    return records_out, diags


def _evaluate_evidence_reuse(
    root_path: Path,
    *,
    raw_records: list[dict[str, Any]],
    task_contexts: dict[int, dict[str, Any]],
    target_flow_ids: set[str],
    target_slice: str | None = None,
    expected_profile: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """AC-2: Match Chapter 6 UI evidence to current InputSet & test identity; separate failed runtime blockers."""
    reused: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    failed_runtime: list[dict[str, Any]] = []

    for idx, rec in enumerate(raw_records):
        src_path = str(rec.get("evidence_path") or rec.get("_source_path") or f"evidence:{idx}")
        src_digest = rec.get("evidence_sha256") or rec.get("_source_digest") or _file_raw_digest(root_path, src_path)
        raw_tid = rec.get("task_id")
        try:
            tid = int(raw_tid) if raw_tid is not None and not isinstance(raw_tid, bool) else None
        except (TypeError, ValueError):
            tid = None
        flow_id = str(rec.get("flow_id") or "").strip() or None
        raw_binding_ref = str(rec.get("binding_ref") or "").strip() or None
        binding_ref = _norm_rel(raw_binding_ref) if raw_binding_ref else None
        ev_kind = str(rec.get("evidence_kind") or "").strip().lower()
        raw_test_path = str(rec.get("test_path") or "").strip()
        recorded_test_sha = str(rec.get("test_sha256") or "").strip()
        rec_iset = str(rec.get("input_set_digest") or "").strip()
        state = str(rec.get("state") or "passed").strip().lower()
        tests_count = _strict_nonneg_int(rec.get("tests"))
        failures_count = _strict_nonneg_int(rec.get("failures"), default=0)
        errors_count = _strict_nonneg_int(rec.get("errors"), default=0)
        skipped_count = _strict_nonneg_int(rec.get("skipped"), default=0)
        real_engine_input = rec.get("real_engine_input")

        def _reject(reason: str, reason_code: str, *, blocks_closure: bool = False) -> None:
            entry = {
                "task_id": tid,
                "flow_id": flow_id,
                "binding_ref": binding_ref,
                "evidence_path": _norm_rel(src_path),
                "evidence_sha256": src_digest,
                "evidence_kind": ev_kind or "unknown",
                "test_path": raw_test_path or None,
                "reason": reason,
                "reason_code": reason_code,
                "input_set_digest": rec_iset or None,
                "blocks_closure": blocks_closure,
            }
            rejected.append(entry)
            if blocks_closure:
                failed_runtime.append(entry)

        if tid is None or tid not in task_contexts:
            _reject("task_not_in_target_slice", codec.ReasonCode.MAPPING_MISMATCH.value)
            continue

        tctx = task_contexts[tid]
        live_iset = str(tctx.get("input_set_digest") or "")
        live_bindings = {str(r.get("path")) for r in (tctx.get("binding_refs") or []) if isinstance(r, dict) and r.get("path")}
        revs_by_path: dict[str, int] = dict(tctx.get("binding_revisions_by_path") or {})

        # 1. InputSet exact digest match.
        if not rec_iset or not live_iset or rec_iset != live_iset:
            _reject("stale_input_set_digest", codec.ReasonCode.INPUT_STALE.value)
            continue

        # 2. Binding / condition / slice / profile / per-binding revision match.
        if binding_ref:
            _bt, canon_bref, berr = _resolve_contained_path(
                root_path, binding_ref, label="binding_ref", entity_id=f"evidence:{idx}"
            )
            if berr is not None or canon_bref is None:
                _reject("unsafe_binding_ref", codec.ReasonCode.UNSAFE_PATH.value)
                continue
            binding_ref = canon_bref
            if live_bindings and binding_ref not in live_bindings:
                _reject("mismatched_binding_ref", codec.ReasonCode.INPUT_STALE.value)
                continue
        if flow_id and target_flow_ids and flow_id not in target_flow_ids:
            _reject("mismatched_flow_id", codec.ReasonCode.MAPPING_MISMATCH.value)
            continue
        rec_slice = str(rec.get("slice_name") or rec.get("target_slice") or "").strip()
        if rec_slice and target_slice and rec_slice != target_slice:
            _reject("mismatched_target_slice", codec.ReasonCode.INPUT_STALE.value)
            continue
        rec_condition = str(rec.get("condition") or "").strip()
        allowed_conditions = {"default", "target_slice", "windows_godot"}
        if target_slice:
            allowed_conditions.add(f"slice:{target_slice.lower()}")
        if rec_condition and rec_condition.lower() not in allowed_conditions:
            _reject("mismatched_execution_condition", codec.ReasonCode.INPUT_STALE.value)
            continue
        rec_conditions = rec.get("conditions")
        if isinstance(rec_conditions, dict):
            cond_slice = str(rec_conditions.get("slice") or rec_conditions.get("target_slice") or "").strip()
            cond_flow = str(rec_conditions.get("flow_id") or "").strip()
            cond_prof = str(rec_conditions.get("delivery_profile") or "").strip()
            cond_bref = str(rec_conditions.get("binding_ref") or "").strip()
            if cond_slice and target_slice and cond_slice != target_slice:
                _reject("mismatched_execution_condition", codec.ReasonCode.INPUT_STALE.value)
                continue
            if cond_flow and target_flow_ids and cond_flow not in target_flow_ids:
                _reject("mismatched_execution_condition", codec.ReasonCode.INPUT_STALE.value)
                continue
            if cond_prof and expected_profile and cond_prof != expected_profile:
                _reject("mismatched_delivery_profile", codec.ReasonCode.INPUT_STALE.value)
                continue
            if cond_bref and live_bindings and _norm_rel(cond_bref) not in live_bindings:
                _reject("mismatched_binding_ref", codec.ReasonCode.INPUT_STALE.value)
                continue
        rec_profile = str(rec.get("delivery_profile") or "").strip()
        if expected_profile and rec_profile and rec_profile != expected_profile:
            _reject("mismatched_delivery_profile", codec.ReasonCode.INPUT_STALE.value)
            continue
        resolved_binding_ref = binding_ref or (sorted(live_bindings)[0] if live_bindings else None)
        rec_binding_rev = rec.get("binding_revision")
        if rec_binding_rev is not None:
            if type(rec_binding_rev) is not int:
                _reject("invalid_binding_revision_type", codec.ReasonCode.INVALID_TYPE.value)
                continue
            if resolved_binding_ref and resolved_binding_ref in revs_by_path:
                if rec_binding_rev != revs_by_path[resolved_binding_ref]:
                    _reject("mismatched_binding_revision", codec.ReasonCode.REVISION_MISMATCH.value)
                    continue
            elif revs_by_path and rec_binding_rev not in set(revs_by_path.values()):
                _reject("mismatched_binding_revision", codec.ReasonCode.REVISION_MISMATCH.value)
                continue

        # 3. Reject static-wiring-only, method-call-only, and non-engine evidence unconditionally.
        if ev_kind in _STATIC_EVIDENCE_KINDS:
            _reject("static_wiring_cannot_satisfy_real_engine_input", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue
        if ev_kind in _METHOD_CALL_EVIDENCE_KINDS:
            _reject("method_call_only_cannot_satisfy_real_engine_input", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue
        if real_engine_input is not True:
            _reject("real_engine_input_not_exercised", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue
        if ev_kind not in _REAL_ENGINE_EVIDENCE_KINDS:
            _reject("unrecognized_non_engine_evidence_kind", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue

        # Canonicalize test_path via safe_input + no_reparse before prefix check!
        _tp_target, canon_test_path, tp_err = _resolve_contained_path(
            root_path, raw_test_path, label="test_path", entity_id=f"evidence:{idx}"
        )
        if tp_err is not None or not canon_test_path:
            _reject("unsafe_or_missing_test_path", codec.ReasonCode.UNSAFE_PATH.value)
            continue
        if canon_test_path.lower().startswith("game.core.tests/"):
            _reject("method_call_only_cannot_satisfy_real_engine_input", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue
        if not canon_test_path.lower().startswith("tests.godot/"):
            _reject("missing_godot_engine_test_path", codec.ReasonCode.SEMANTIC_ERROR.value)
            continue

        # 4. Reject planned / empty / skipped / failing execution (and block closure on failed/skipped/zero-test!).
        if state == "planned":
            _reject("planned_evidence_is_not_executed", codec.ReasonCode.PENDING.value, blocks_closure=False)
            continue
        counts_invalid = (
            tests_count is None
            or failures_count is None
            or errors_count is None
            or skipped_count is None
        )
        if counts_invalid:
            _reject("invalid_test_count_type", codec.ReasonCode.INVALID_TYPE.value, blocks_closure=True)
            continue
        if state != "passed" or tests_count <= 0 or failures_count > 0 or errors_count > 0 or skipped_count > 0:
            _reject("empty_skipped_or_failed_execution", codec.ReasonCode.CONFLICT.value, blocks_closure=True)
            continue

        # 5. Live test file identity match (exact sha256 + not empty/skipped/unsafe).
        integrity = _inspect_test_file_integrity(root_path, canon_test_path)
        if integrity["status"] != "valid":
            _reject(
                f"test_file_invalid:{integrity['reason']}",
                codec.ReasonCode.CONFLICT.value,
                blocks_closure=True,
            )
            continue
        if not recorded_test_sha or integrity["sha256"] != recorded_test_sha:
            _reject("test_identity_mismatch", codec.ReasonCode.DIGEST_MISMATCH.value)
            continue

        resolved_flow = flow_id or (sorted(target_flow_ids)[0] if target_flow_ids else None)
        reused.append(
            {
                "task_id": tid,
                "flow_id": resolved_flow,
                "binding_ref": resolved_binding_ref,
                "obligation_id": str(rec.get("obligation_id") or f"UI-INPUT-T{tid}"),
                "requirement_ids": [str(r) for r in (rec.get("requirement_ids") or []) if str(r).strip()],
                "obligation_categories": list(rec.get("covered_categories") or ["real_engine_input", "scene_entry", "feedback"]),
                "evidence_kind": ev_kind,
                "evidence_path": _norm_rel(src_path),
                "evidence_sha256": src_digest,
                "test_path": canon_test_path,
                "test_sha256": integrity["sha256"],
                "test_identity_matched": True,
                "input_set_digest": live_iset,
                "tests": tests_count,
                "real_engine_input": True,
                "reused_from_chapter6": True,
            }
        )

    return reused, rejected, failed_runtime


def _check_manual_region_preservation(
    root_path: Path,
    *,
    wiring_report: dict[str, Any],
    gap_doc: dict[str, Any] | None,
) -> tuple[bool, list[dict[str, Any]]]:
    """AC-4: Verify native .tscn manual layout/theme/animation regions (including sub_resource bodies) are preserved."""
    violations: list[dict[str, Any]] = []
    if not isinstance(gap_doc, dict):
        return True, violations

    if gap_doc.get("overwrite_manual_regions") is True:
        scene_ref = (wiring_report.get("scenes_inspected") or [None])[0]
        violations.append(
            {
                "scene_path": scene_ref,
                "reason": "explicit_overwrite_manual_regions_forbidden",
                "diagnostic": _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=str(scene_ref or "scene"),
                    expected={"native_scene_manual_regions_preserved": True, "return_stage": "4"},
                    actual={"overwrite_manual_regions": True, "return_stage": "4"},
                    resume_ref=scene_ref,
                ),
            }
        )

    patches = gap_doc.get("proposed_scene_patches")
    if isinstance(patches, dict):
        for raw_srel, proposed_text in patches.items():
            raw_key = str(raw_srel or "").strip()
            live_file, srel, path_err = _resolve_contained_path(
                root_path, raw_key, label="proposed_scene_patches", entity_id=raw_key
            )
            if path_err is not None or live_file is None or srel is None:
                violations.append(
                    {
                        "scene_path": raw_key,
                        "reason": "unsafe_proposed_scene_patch_path",
                        "diagnostic": path_err
                        or _diag(
                            codec.ReasonCode.UNSAFE_PATH,
                            stage=codec.Stage.PATH,
                            entity_id=raw_key,
                            expected="safe repository-contained .tscn path",
                            actual={"path": raw_key, "return_stage": "4"},
                            resume_ref=raw_key,
                        ),
                    }
                )
                continue
            if not srel.endswith(".tscn") or not isinstance(proposed_text, str):
                continue
            if not live_file.is_file():
                continue
            live_parsed = wiring_report.get("parsed_scenes", {}).get(srel) or _parse_tscn(
                live_file.read_text(encoding="utf-8", errors="replace")
            )
            prop_parsed = _parse_tscn(proposed_text)
            live_regions = live_parsed.get("manual_regions") or []
            if not live_regions:
                continue
            prop_prop_keys = {
                (r["path"], r["property"]): r["value"]
                for r in prop_parsed.get("manual_regions", [])
                if r.get("kind") == "property"
            }
            prop_nodes = {
                (r["path"], r["type"])
                for r in prop_parsed.get("manual_regions", [])
                if r.get("kind") == "node"
            }
            prop_subs = {
                (r["type"], r["id"]): r.get("body_hash")
                for r in prop_parsed.get("manual_regions", [])
                if r.get("kind") == "sub_resource"
            }
            clobbered: list[dict[str, Any]] = []
            for reg in live_regions:
                kind = reg.get("kind")
                if kind == "property":
                    key = (reg["path"], reg["property"])
                    if key not in prop_prop_keys or prop_prop_keys[key] != reg["value"]:
                        clobbered.append(reg)
                elif kind == "node":
                    if (reg["path"], reg["type"]) not in prop_nodes:
                        clobbered.append(reg)
                elif kind == "sub_resource":
                    sub_key = (reg["type"], reg["id"])
                    if sub_key not in prop_subs or prop_subs[sub_key] != reg.get("body_hash"):
                        clobbered.append(reg)
            if clobbered:
                violations.append(
                    {
                        "scene_path": srel,
                        "reason": "native_scene_manual_regions_clobbered",
                        "clobbered_regions": clobbered,
                        "diagnostic": _diag(
                            codec.ReasonCode.CONFLICT,
                            stage=codec.Stage.CONTENT,
                            entity_id=srel,
                            expected={"native_scene_manual_regions_preserved": True, "return_stage": "4"},
                            actual={"clobbered_count": len(clobbered), "clobbered_regions": clobbered[:5], "return_stage": "4"},
                            resume_ref=srel,
                        ),
                    }
                )

    return len(violations) == 0, violations


def _load_existing_tasks(root_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, set[str]]]:
    """Load master tasks plus all three triplet views (tasks.json, tasks_back.json, tasks_gameplay.json)."""
    master_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    statuses_by_tid: dict[int, set[str]] = {}

    tasks_file = root_path / ".taskmaster" / "tasks" / "tasks.json"
    if tasks_file.is_file():
        try:
            doc = json.loads(tasks_file.read_text(encoding="utf-8"))
            rows = (doc.get("master") or {}).get("tasks") or []
            for r in rows:
                if isinstance(r, dict):
                    master_rows.append(r)
                    all_rows.append(r)
                    if type(r.get("id")) is int:
                        statuses_by_tid.setdefault(r["id"], set()).add(str(r.get("status") or "").strip().lower())
        except Exception:
            pass

    for view_name in ("tasks_back.json", "tasks_gameplay.json"):
        vfile = root_path / ".taskmaster" / "tasks" / view_name
        if not vfile.is_file():
            continue
        try:
            vrows = json.loads(vfile.read_text(encoding="utf-8"))
            if isinstance(vrows, list):
                for vr in vrows:
                    if isinstance(vr, dict):
                        all_rows.append(vr)
                        if type(vr.get("taskmaster_id")) is int:
                            statuses_by_tid.setdefault(vr["taskmaster_id"], set()).add(
                                str(vr.get("status") or "").strip().lower()
                            )
        except Exception:
            pass

    return master_rows, all_rows, statuses_by_tid


def _is_synonymous_with_existing(
    proposed_title: str,
    proposed_flow_ids: set[str],
    proposed_req_ids: set[str],
    *,
    existing_tasks: list[dict[str, Any]],
    covered_flow_req_pairs: set[tuple[str, str]],
) -> dict[str, Any] | None:
    if proposed_flow_ids and proposed_req_ids:
        for fid in proposed_flow_ids:
            for rid in proposed_req_ids:
                if (fid, rid) in covered_flow_req_pairs:
                    return {"reason": "flow_and_requirement_already_covered", "flow_id": fid, "requirement_id": rid}
    ptoks = _tokens(proposed_title)
    if not ptoks:
        return None
    for row in existing_tasks:
        ttoks = _tokens(f"{row.get('title', '')} {row.get('description', '')} {row.get('summary', '')}")
        if not ttoks:
            continue
        overlap = len(ptoks & ttoks) / max(1, len(ptoks))
        if overlap >= 0.75:
            return {
                "reason": "synonymous_title_with_existing_task",
                "existing_task_id": row.get("taskmaster_id") or row.get("id"),
                "existing_title": row.get("title"),
                "overlap": round(overlap, 3),
            }
    return None


def _load_committed_b_context(root_path: Path) -> dict[str, Any]:
    """Read-only load of committed B-route catalog, plans, bindings, and origins."""
    out: dict[str, Any] = {
        "has_bundle": False,
        "plans": {},
        "bindings": {},
        "origins": None,
        "plan_paths": {},
        "binding_paths": {},
        "errors": [],
    }
    catalog_rel = records.CATALOG_PATH
    try:
        catalog_path = inventory.safe_input(root_path.resolve(), catalog_rel, allow_logs=False)
    except (codec.CodecError, ValueError, OSError) as exc:
        out["errors"].append(
            _diag(
                codec.ReasonCode.UNSAFE_PATH,
                stage=codec.Stage.PATH,
                expected="safe repository-contained catalog.v1.json",
                actual=f"{type(exc).__name__}: {exc}",
                resume_ref=catalog_rel,
            )
        )
        return out
    if not catalog_path.is_file():
        return out

    def _read_verified_ref(ref_obj: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
        rel = _norm_rel(str(ref_obj.get("path") or ""))
        if not rel:
            return None, None
        fpath = inventory.safe_input(root_path.resolve(), rel, allow_logs=False)
        inventory.no_reparse(fpath)
        if not fpath.is_file():
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.FILE_NOT_FOUND,
                    codec.Stage.REFERENCE,
                    str(ref_obj.get("entity_id") or rel),
                    rel,
                    "missing",
                    rel,
                )
            )
        raw = fpath.read_bytes()
        expected_digest = ref_obj.get("digest")
        if expected_digest and codec.raw_digest(raw) != expected_digest:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    codec.Stage.REFERENCE,
                    str(ref_obj.get("entity_id") or rel),
                    expected_digest,
                    codec.raw_digest(raw),
                    rel,
                )
            )
        doc = codec.strict_json_loads(raw)
        return rel, doc if isinstance(doc, dict) else None

    try:
        inventory.no_reparse(catalog_path)
        catalog = codec.strict_json_loads(catalog_path.read_bytes())
        if not isinstance(catalog, dict) or catalog.get("schema_version") != "newrouge.b-route-catalog.v1":
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.SCHEMA_MISMATCH,
                    codec.Stage.SCHEMA,
                    "catalog",
                    "newrouge.b-route-catalog.v1",
                    catalog.get("schema_version") if isinstance(catalog, dict) else type(catalog).__name__,
                    catalog_rel,
                )
            )
        origins_ref = catalog.get("origins_ref")
        if isinstance(origins_ref, dict):
            _orel, odoc = _read_verified_ref(origins_ref)
            out["origins"] = odoc

        plan_refs: list[dict[str, Any]] = []
        binding_refs: list[dict[str, Any]] = []
        for head in catalog.get("scope_heads") or []:
            if isinstance(head, dict):
                plan_refs.extend(r for r in (head.get("plan_refs") or []) if isinstance(r, dict))
                binding_refs.extend(r for r in (head.get("binding_refs") or []) if isinstance(r, dict))
        for trow in catalog.get("task_index") or []:
            if isinstance(trow, dict):
                plan_refs.extend(r for r in (trow.get("plan_refs") or []) if isinstance(r, dict))
                binding_refs.extend(r for r in (trow.get("binding_refs") or []) if isinstance(r, dict))

        for pref in plan_refs:
            pid = str(pref.get("entity_id") or "").strip()
            if not pid or pid in out["plans"]:
                continue
            prel, pdoc = _read_verified_ref(pref)
            if prel and pdoc is not None:
                out["plan_paths"][pid] = prel
                out["plans"][pid] = pdoc

        for bref in binding_refs:
            bid = str(bref.get("entity_id") or "").strip()
            if not bid or bid in out["bindings"]:
                continue
            brel, bdoc = _read_verified_ref(bref)
            if brel and bdoc is not None:
                out["binding_paths"][bid] = brel
                out["bindings"][bid] = bdoc
        out["has_bundle"] = True
    except (codec.CodecError, OSError, ValueError) as exc:
        if isinstance(exc, codec.CodecError):
            out["errors"].append(exc.diagnostic.to_dict())
        else:
            out["errors"].append(
                _diag(
                    codec.ReasonCode.READ_ERROR,
                    stage=codec.Stage.BUNDLE,
                    expected="valid published B-route catalog bundle",
                    actual=f"{type(exc).__name__}: {exc}",
                    resume_ref=catalog_rel,
                )
            )
    return out


def _verify_owned_ref_files(
    root_path: Path,
    ref_list: list[Any],
    *,
    label: str,
) -> tuple[bool, list[str], str | None]:
    """Verify live owned ref files exist, are repository-contained/non-reparse, and match declared raw_digest."""
    verified_paths: list[str] = []
    for ref_obj in ref_list:
        if not isinstance(ref_obj, dict):
            continue
        files = ref_obj.get("files") or []
        for f in files:
            if not isinstance(f, dict) or not f.get("path"):
                continue
            raw_p = str(f["path"])
            target, canon_rel, path_err = _resolve_contained_path(
                root_path, raw_p, label=label, entity_id=raw_p
            )
            if path_err is not None or target is None or canon_rel is None:
                return False, [], f"unsafe_{label}_path:{raw_p}"
            if not target.is_file():
                return False, [], f"missing_{label}_file:{canon_rel}"
            try:
                inventory.no_reparse(target)
                live_digest = codec.raw_digest(target.read_bytes())
            except (codec.CodecError, OSError, ValueError):
                return False, [], f"unreadable_{label}_file:{canon_rel}"
            expected_digest = str(f.get("raw_digest") or "").strip()
            if expected_digest and live_digest != expected_digest:
                return False, [], f"digest_mismatch_{label}:{canon_rel}"
            verified_paths.append(canon_rel)
    if not verified_paths:
        return False, [], f"missing_live_{label}"
    return True, sorted(set(verified_paths)), None


def _plan_non_ui_proof_valid(
    root_path: Path,
    *,
    plan_doc: dict[str, Any],
    binding_doc: dict[str, Any],
    flow_doc: dict[str, Any] | None,
    bucket_cfg: dict[str, Any],
    impl_objects: list[dict[str, Any]],
    target_tids: set[int] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Determine whether a target slice has legal committed non-UI proof (never auto-skip on missing fields)."""
    ui_impl_objs = [o for o in impl_objects if o.get("kind") in {"scene", "binding", "adapter"}]
    if ui_impl_objs:
        return False, {"reason": "ui_implementation_objects_present", "count": len(ui_impl_objs)}

    if bucket_cfg:
        audience = str(bucket_cfg.get("audience") or "").strip().lower()
        cand_mode = str(bucket_cfg.get("candidate_mode") or "").strip().lower()
        surfaces = [str(s).strip() for s in (bucket_cfg.get("suggested_surfaces") or []) if str(s).strip()]
        if audience == "player-facing" and cand_mode != "audit-only" and surfaces:
            return False, {"reason": "profile_bucket_requires_player_facing_surfaces", "surfaces": surfaces}

    ok_proofs, proof_paths, proof_err = _verify_owned_ref_files(
        root_path, list(plan_doc.get("adoption_proof_refs") or []), label="adoption_proof_refs"
    )
    if not ok_proofs:
        return False, {"reason": proof_err or "missing_live_adoption_proof_refs"}

    # Case A: Committed non-Flow or pure-domain/deferred scope.
    scoped_req_ids: set[str] | None = None
    if target_tids:
        mapped_reqs: set[str] = set()
        mapped_flows: set[str] = set()
        mapped_parts: set[str] = set()
        for tm in binding_doc.get("task_mappings") or []:
            if int(tm.get("task_id") or 0) in target_tids:
                mapped_reqs.update(str(r) for r in (tm.get("requirement_ids") or []) if str(r).strip())
                mapped_flows.update(str(f) for f in (tm.get("flow_ids") or []) if str(f).strip())
                mapped_parts.update(str(p) for p in (tm.get("part_kinds") or []) if str(p).strip())
        if mapped_reqs and not mapped_flows and not (mapped_parts & {"scene", "binding", "csharp_adapter"}):
            scoped_req_ids = mapped_reqs

    if flow_doc is None and (not (plan_doc.get("definitions", {}).get("flows") or []) or scoped_req_ids is not None):
        all_verifs = [v for v in (plan_doc.get("requirement_verification") or []) if isinstance(v, dict)]
        verifs = (
            [v for v in all_verifs if v.get("requirement_id") in scoped_req_ids]
            if scoped_req_ids is not None
            else all_verifs
        )
        allowed_non_flow = {"other_verification", "deferred"}
        if not verifs or not all(v.get("disposition") in allowed_non_flow for v in verifs):
            return False, {"reason": "not_pure_other_verification_or_deferred_scope"}
        app_by_req = {
            a.get("requirement_id"): a
            for a in (plan_doc.get("applicability") or [])
            if isinstance(a, dict) and a.get("requirement_id")
        }
        rationales: list[str] = []
        for v in verifs:
            arow = app_by_req.get(v.get("requirement_id")) or {}
            rat = str(arow.get("rationale") or v.get("rationale") or "").strip()
            if len(rat) < 12:
                return False, {"reason": "insufficient_non_ui_rationale"}
            rationales.append(rat)
        has_other = any(v.get("disposition") == "other_verification" for v in verifs)
        other_refs: list[Any] = list(binding_doc.get("other_verification_refs") or [])
        for v in verifs:
            arow = app_by_req.get(v.get("requirement_id")) or {}
            other_refs.extend(arow.get("other_verification_refs") or [])
        other_paths: list[str] = []
        if has_other:
            ok_other, other_paths, other_err = _verify_owned_ref_files(
                root_path, other_refs, label="other_verification_refs"
            )
            if not ok_other:
                return False, {"reason": other_err or "missing_live_other_verification_refs"}
        elif other_refs:
            ok_other, other_paths, other_err = _verify_owned_ref_files(
                root_path, other_refs, label="other_verification_refs"
            )
            if not ok_other:
                return False, {"reason": other_err or "invalid_other_verification_refs"}
        mode_name = "non_flow_other_verification" if has_other else "pure_domain_deferred"
        return True, {
            "mode": mode_name,
            "rationales": rationales,
            "adoption_proof_refs": proof_paths,
            "other_verification_refs": other_paths,
        }

    # Case B: Committed Flow explicitly declares ui.applicability == "not_applicable" + non-UI parts.
    if isinstance(flow_doc, dict):
        ui_block = flow_doc.get("ui") if isinstance(flow_doc.get("ui"), dict) else None
        if ui_block is None or ui_block.get("applicability") != "not_applicable":
            return False, {"reason": "flow_ui_not_declared_not_applicable"}
        ui_rationale = str(ui_block.get("rationale") or "").strip()
        if len(ui_rationale) < 12:
            return False, {"reason": "missing_substantive_flow_ui_rationale"}
        parts_by_kind = {p.get("kind"): p for p in (binding_doc.get("parts") or []) if isinstance(p, dict)}
        for ui_part in ("binding", "scene"):
            p = parts_by_kind.get(ui_part)
            if not p or p.get("applicability") != "not_applicable" or len(str(p.get("rationale") or "").strip()) < 10:
                return False, {"reason": f"part_{ui_part}_not_proven_not_applicable"}
        req_ids = set(flow_doc.get("requirement_ids") or [])
        for req in plan_doc.get("requirements") or []:
            if req.get("requirement_id") in req_ids:
                if _UI_KEYWORD_RE.search(str(req.get("acceptance_intent") or "")):
                    return False, {"reason": "requirement_demands_player_facing_ui", "requirement_id": req.get("requirement_id")}
        return True, {
            "mode": "flow_explicit_not_applicable",
            "rationales": [ui_rationale],
            "adoption_proof_refs": proof_paths,
            "other_verification_refs": [],
        }

    return False, {"reason": "no_committed_non_ui_proof"}


def _eval_single_task_gate_worker(
    args: tuple[str, int, str | None],
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Top-level worker for parallel live Story 3.8 gate evaluation across CPU cores."""
    sys.dont_write_bytecode = True
    root_str, tid_arg, op_arg = args
    rpath = Path(root_str)
    g_res = ch6_gate.evaluate_chapter6_gate(
        rpath,
        tid_arg,
        operation=op_arg,
        consumer="b_route_chapter7_slice",
        lock_mode="none",
    )
    i_res: dict[str, Any] = {}
    reason_s = str(g_res.get("reason") or "")
    if not g_res.get("input_set_digest") and not reason_s.startswith(
        ("origin_blocked:", "input_set_blocked:", "frozen_a_input_set_blocked:")
    ):
        i_res = input_set.resolve_input_set(
            rpath,
            tid_arg,
            operation=op_arg,
        )
    return tid_arg, g_res, i_res


def evaluate_chapter7_slice(
    root: Path | str,
    *,
    flow_id: str | None = None,
    slice_name: str | None = None,
    task_ids: list[int | str] | None = None,
    profile_path: Path | str | None = None,
    evidence_dir: Path | str | None = None,
    ui_evidence: dict[str, Any] | list[Any] | str | Path | None = None,
    gap_input: dict[str, Any] | str | Path | None = None,
    operation: str | None = None,
    delivery_profile: str | None = None,
) -> dict[str, Any]:
    """Evaluate target-slice Chapter 7 UI closure in strict zero-write read-only mode."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))

    norm_flow_id = str(flow_id or "").strip() or None
    norm_slice = str(slice_name or "").strip() or None
    parsed_tids: list[int] = []
    for raw_tid in list(task_ids or []):
        parsed_tids.append(ch6_gate.parse_strict_task_id(raw_tid))
    parsed_tids = sorted(set(parsed_tids))

    def _finish(payload: dict[str, Any]) -> dict[str, Any]:
        elapsed = round(max(0.0, time.monotonic() - started), 6)
        payload.setdefault("schema_version", SCHEMA)
        payload.setdefault("flow_all_required_obligations_completed", False)
        payload["flow_completed"] = False
        payload["cumulative_milestone_completed"] = False
        payload["downstream_flow_obligations_preserved"] = True
        payload["cumulative_milestone_obligations_preserved"] = True
        payload["task_triplet_written"] = False
        payload["global_knowledge_refresh"] = "not_performed"
        payload["runtime_verified"] = False
        payload["default_b_enabled"] = False
        payload.setdefault("report_path", None)
        payload["metrics"] = {
            **dict(payload.get("metrics") or {}),
            "active_elapsed_seconds": elapsed,
            "model_invocation_count": 0,
        }
        payload["handoff"] = {
            "schema_version": HANDOFF_SCHEMA,
            "target_slice": payload.get("target_slice"),
            "target_flow_id": payload.get("target_flow_id"),
            "target_task_ids": list(payload.get("target_task_ids") or []),
            "ui_applicability": payload.get("ui_applicability"),
            "verified_items": list(payload.get("verified_items") or []),
            "pending_items": list(payload.get("pending_items") or []),
            "manual_items": list(payload.get("manual_items") or []),
            "blocked_items": list(payload.get("blocked_items") or []),
            "reused_ui_obligations": list(payload.get("reused_ui_obligations") or []),
            "governed_gap_routing": list(payload.get("governed_gap_routing") or []),
            "proposed_governed_deltas": payload.get("proposed_governed_deltas"),
            "downstream_flow_obligations_preserved": True,
            "cumulative_milestone_obligations_preserved": True,
            "flow_all_required_obligations_completed": False,
            "flow_completed": False,
            "cumulative_milestone_completed": False,
            "global_knowledge_refresh": "not_performed",
            **INVARIANT_FLAGS,
        }
        return payload

    if not norm_flow_id and not norm_slice and not parsed_tids:
        diag = _diag(
            codec.ReasonCode.INVALID_ARGUMENT,
            stage=codec.Stage.PATH,
            expected="at least one of --flow-id, --slice, or --task-id",
            actual={"flow_id": norm_flow_id, "slice": norm_slice, "task_ids": parsed_tids},
        )
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": [],
                "ui_applicability": "unknown",
                "reason_code": codec.ReasonCode.INVALID_ARGUMENT.value,
                "reason": "missing_target_selector",
                "return_stage": "4",
                "diagnostics": [diag],
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": [],
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": True,
            }
        )

    # Load optional profile safely.
    resolved_profile_arg: Path | None = None
    if profile_path is not None and str(profile_path).strip():
        target_p, _rel_p, err_p = _resolve_contained_path(
            root_path, profile_path, label="profile", entity_id="chapter7-profile"
        )
        if err_p is not None or target_p is None:
            return _finish(
                {
                    "ok": False,
                    "route": "blocked",
                    "target_slice": norm_slice,
                    "target_flow_id": norm_flow_id,
                    "target_task_ids": parsed_tids,
                    "ui_applicability": "unknown",
                    "reason_code": (err_p or {}).get("reason_code", codec.ReasonCode.UNSAFE_PATH.value),
                    "reason": "invalid_profile_path",
                    "return_stage": "4",
                    "diagnostics": [err_p] if err_p else [],
                    "verified_items": [],
                    "pending_items": [],
                    "manual_items": [],
                    "blocked_items": [],
                    "reused_ui_obligations": [],
                    "rejected_evidence": [],
                    "governed_gap_routing": [],
                    "proposed_governed_deltas": None,
                    "native_scene_manual_regions_preserved": True,
                }
            )
        resolved_profile_arg = target_p

    try:
        profile = ch7_profile.load_chapter7_profile(
            repo_root=root_path, profile_path=resolved_profile_arg
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        rc = codec.ReasonCode.FILE_NOT_FOUND if isinstance(exc, FileNotFoundError) else codec.ReasonCode.INVALID_JSON
        diag = _diag(
            rc,
            stage=codec.Stage.CONTENT,
            entity_id="chapter7-profile",
            expected="valid chapter7-profile.json",
            actual=str(exc),
            resume_ref=str(profile_path or "docs/workflows/chapter7-profile.json"),
        )
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": parsed_tids,
                "ui_applicability": "unknown",
                "reason_code": rc.value,
                "reason": "invalid_chapter7_profile",
                "return_stage": "4",
                "diagnostics": [diag],
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": [],
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": True,
            }
        )

    profile_is_explicit = bool(str(profile.get("_loaded_profile_path") or "").strip())
    profile_rel_ref: str | None = None
    if profile_is_explicit:
        try:
            profile_rel_ref = Path(profile["_loaded_profile_path"]).resolve().relative_to(root_path.resolve()).as_posix()
        except ValueError:
            profile_rel_ref = "docs/workflows/chapter7-profile.json"

    bucket_cfg: dict[str, Any] = {}
    if norm_slice:
        available_buckets = set(ch7_profile.bucket_names(profile))
        if norm_slice not in available_buckets:
            diag = _diag(
                codec.ReasonCode.UNKNOWN_ENTITY,
                stage=codec.Stage.CONTENT,
                entity_id=norm_slice,
                expected={"available_slices": sorted(available_buckets)},
                actual={"slice": norm_slice, "return_stage": "4"},
                resume_ref=profile_rel_ref or "docs/workflows/chapter7-profile.json",
            )
            return _finish(
                {
                    "ok": False,
                    "route": "blocked",
                    "target_slice": norm_slice,
                    "target_flow_id": norm_flow_id,
                    "target_task_ids": parsed_tids,
                    "ui_applicability": "unknown",
                    "reason_code": codec.ReasonCode.UNKNOWN_ENTITY.value,
                    "reason": "unknown_target_slice",
                    "return_stage": "4",
                    "diagnostics": [diag],
                    "verified_items": [],
                    "pending_items": [],
                    "manual_items": [],
                    "blocked_items": [],
                    "reused_ui_obligations": [],
                    "rejected_evidence": [],
                    "governed_gap_routing": [],
                    "proposed_governed_deltas": None,
                    "native_scene_manual_regions_preserved": True,
                }
            )
        bucket_cfg = ch7_profile.bucket_profile(profile, norm_slice)

    # Load optional gap_input safely.
    gap_doc, gap_rel, gap_err = _safe_load_json_arg(
        root_path, gap_input, label="gap_input", entity_id=norm_flow_id or norm_slice or "gap"
    )
    if gap_err is not None:
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": parsed_tids,
                "ui_applicability": "unknown",
                "reason_code": gap_err["reason_code"],
                "reason": "invalid_gap_input",
                "return_stage": "4",
                "diagnostics": [gap_err],
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": [],
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": True,
            }
        )

    # Detect B-route presence and read committed plans/bindings (zero writes).
    presence = ch6_gate.detect_b_route_presence(root_path, parsed_tids[0] if parsed_tids else None)
    b_ctx = _load_committed_b_context(root_path)
    is_b_repo = bool(
        presence.get("has_b_traces")
        or presence.get("capability_apply_pending")
        or presence.get("pending_journals")
        or presence.get("na_labels")
        or b_ctx["has_bundle"]
    )

    if b_ctx["errors"] and is_b_repo:
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": parsed_tids,
                "ui_applicability": "unknown",
                "reason_code": b_ctx["errors"][0]["reason_code"],
                "reason": "committed_b_route_bundle_invalid",
                "return_stage": "3B",
                "diagnostics": b_ctx["errors"],
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": [],
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": True,
            }
        )

    # Discover target-slice Tasks and Flows without scanning or waiting for unrelated game Tasks.
    master_tasks, all_existing_tasks, triplet_statuses_by_tid = _load_existing_tasks(root_path)
    existing_tids = {int(t["id"]) for t in master_tasks if type(t.get("id")) is int}
    master_status_by_tid = {
        int(t["id"]): str(t.get("status") or "").strip().lower()
        for t in master_tasks
        if type(t.get("id")) is int
    }

    target_tids: set[int] = set(parsed_tids)
    matched_plan_ids: list[str] = []
    matched_flow_docs: dict[str, tuple[str, dict[str, Any]]] = {}

    if b_ctx["has_bundle"]:
        for pid, bdoc in sorted(b_ctx["bindings"].items()):
            pdoc = b_ctx["plans"].get(pid)
            if not isinstance(pdoc, dict):
                continue
            plan_flows = {f["id"]: f for f in (pdoc.get("definitions", {}).get("flows") or []) if isinstance(f, dict) and f.get("id")}
            if norm_flow_id and norm_flow_id in plan_flows:
                matched_plan_ids.append(pid)
                matched_flow_docs[norm_flow_id] = (pid, plan_flows[norm_flow_id])
                for tm in bdoc.get("task_mappings") or []:
                    if norm_flow_id in (tm.get("flow_ids") or []):
                        target_tids.add(int(tm["task_id"]))

        if norm_slice:
            bucket_tids = set(int(x) for x in (bucket_cfg.get("feature_task_ids") or []) if type(x) is int)
            bucket_tids.update(int(x) for x in (bucket_cfg.get("closure_task_ids") or []) if type(x) is int)
            w_tid = bucket_cfg.get("wiring_task_id")
            if type(w_tid) is int and w_tid > 0:
                bucket_tids.add(w_tid)
            present_bucket_tids = bucket_tids & existing_tids if existing_tids else bucket_tids
            target_tids.update(present_bucket_tids)
            slice_toks = _tokens(norm_slice.replace("_", " "))
            for pid, bdoc in sorted(b_ctx["bindings"].items()):
                pdoc = b_ctx["plans"].get(pid)
                if not isinstance(pdoc, dict):
                    continue
                for tm in bdoc.get("task_mappings") or []:
                    tid = int(tm["task_id"])
                    if tid in target_tids:
                        if pid not in matched_plan_ids:
                            matched_plan_ids.append(pid)
                        for fid in tm.get("flow_ids") or []:
                            fdoc = next(
                                (f for f in (pdoc.get("definitions", {}).get("flows") or []) if f.get("id") == fid),
                                None,
                            )
                            if fdoc is not None:
                                matched_flow_docs[fid] = (pid, fdoc)
                if not target_tids and slice_toks:
                    for fdoc in pdoc.get("definitions", {}).get("flows") or []:
                        fid = str(fdoc.get("id") or "")
                        if slice_toks & _tokens(fid.replace("-", " ")):
                            if pid not in matched_plan_ids:
                                matched_plan_ids.append(pid)
                            matched_flow_docs[fid] = (pid, fdoc)
                            for tm in bdoc.get("task_mappings") or []:
                                if fid in (tm.get("flow_ids") or []):
                                    target_tids.add(int(tm["task_id"]))

        if parsed_tids:
            for pid, bdoc in sorted(b_ctx["bindings"].items()):
                pdoc = b_ctx["plans"].get(pid)
                if not isinstance(pdoc, dict):
                    continue
                for tm in bdoc.get("task_mappings") or []:
                    if int(tm["task_id"]) in set(parsed_tids):
                        if pid not in matched_plan_ids:
                            matched_plan_ids.append(pid)
                        for fid in tm.get("flow_ids") or []:
                            fdoc = next(
                                (f for f in (pdoc.get("definitions", {}).get("flows") or []) if f.get("id") == fid),
                                None,
                            )
                            if fdoc is not None:
                                matched_flow_docs[fid] = (pid, fdoc)
    else:
        if norm_slice:
            bucket_tids = set(int(x) for x in (bucket_cfg.get("feature_task_ids") or []) if type(x) is int)
            bucket_tids.update(int(x) for x in (bucket_cfg.get("closure_task_ids") or []) if type(x) is int)
            w_tid = bucket_cfg.get("wiring_task_id")
            if type(w_tid) is int and w_tid > 0:
                bucket_tids.add(w_tid)
            target_tids.update(bucket_tids & existing_tids if existing_tids else bucket_tids)

    sorted_tids = sorted(target_tids)
    primary_binding_ref = (
        b_ctx["binding_paths"].get(matched_plan_ids[0])
        if matched_plan_ids
        else (records.CATALOG_PATH if b_ctx["has_bundle"] else (profile_rel_ref or "docs/workflows/chapter7-profile.json"))
    )
    primary_plan_ref = b_ctx["plan_paths"].get(matched_plan_ids[0]) if matched_plan_ids else None
    primary_flow_id = norm_flow_id or (sorted(matched_flow_docs)[0] if matched_flow_docs else None)
    primary_tid = sorted_tids[0] if sorted_tids else None
    default_declaring_candidates: list[str | None] = [
        primary_binding_ref,
        primary_plan_ref,
        records.CATALOG_PATH if b_ctx["has_bundle"] else None,
        profile_rel_ref,
        ".taskmaster/tasks/tasks.json",
    ]

    # P-01: Validate --evidence-dir / --ui-evidence and gap_doc anti-tamper guards BEFORE legacy-A and not_applicable early returns!
    raw_evidence, ev_diags = _collect_ui_evidence_records(
        root_path,
        target_tids=target_tids,
        evidence_dir=evidence_dir,
        ui_evidence_arg=ui_evidence,
    )
    early_tamper_diags: list[dict[str, Any]] = []
    early_tamper_blocked: list[dict[str, Any]] = []
    early_tamper_stages: list[str | None] = []
    early_manual_preserved = True

    if ev_diags:
        for ed in ev_diags:
            early_tamper_stages.append("4")
            early_tamper_diags.append(ed)
            early_tamper_blocked.append(
                _make_item(
                    item_id=f"blocked:evidence-input:{ed.get('entity_id') or 'evidence'}",
                    category="evidence_input",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [ed.get("resume_ref"), *default_declaring_candidates]),
                    summary=f"Invalid evidence input rejected fail-closed: {ed.get('reason_code')}",
                    details=ed,
                )
            )
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": sorted_tids,
                "ui_applicability": "unknown",
                "reason_code": str(ev_diags[0]["reason_code"]),
                "reason": "invalid_evidence_input",
                "return_stage": "4",
                "diagnostics": early_tamper_diags,
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": early_tamper_blocked,
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": True,
            }
        )

    if isinstance(gap_doc, dict):
        if gap_doc.get("direct_triplet_write") is True:
            early_tamper_stages.append("3C")
            diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(primary_tid or norm_slice or norm_flow_id or "gap"),
                expected={"task_triplet_written": False, "route_via": "b-route-task-preview/b-route-task-compile", "return_stage": "3C"},
                actual={"direct_triplet_write": True, "return_stage": "3C"},
                resume_ref=".taskmaster/tasks/tasks.json",
            )
            early_tamper_diags.append(diag)
            early_tamper_blocked.append(
                _make_item(
                    item_id="blocked:direct-triplet-write",
                    category="governed_gap_protection",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [".taskmaster/tasks/tasks.json", *default_declaring_candidates]),
                    summary="Direct unreviewed write to .taskmaster/tasks/*.json is forbidden; route via 3.1/3.2.",
                    details={"return_stage": "3C"},
                )
            )

        # Block permanent ID allocation or non-null task_id on create intents (P-01 + P-02).
        perm_id_violations: list[dict[str, Any]] = []
        if gap_doc.get("allocate_permanent_id") is True:
            perm_id_violations.append({"scope": "gap_input", "allocate_permanent_id": True})
        for idx_g, tg in enumerate(list(gap_doc.get("missing_ui_tasks") or [])):
            if not isinstance(tg, dict):
                continue
            action_s = str(tg.get("action") or "create").strip().lower()
            if tg.get("allocate_permanent_id") is True:
                perm_id_violations.append({"index": idx_g, "allocate_permanent_id": True})
            if action_s == "create" and tg.get("task_id") is not None:
                perm_id_violations.append({"index": idx_g, "action": "create", "task_id": tg.get("task_id")})
        if perm_id_violations:
            early_tamper_stages.append("3C")
            diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.CONTENT,
                entity_id=str(primary_tid or norm_slice or norm_flow_id or "gap"),
                expected={"permanent_ids_allocated": False, "create_task_id": None, "return_stage": "3C"},
                actual={"violations": perm_id_violations, "return_stage": "3C"},
                resume_ref=gap_rel or primary_binding_ref,
            )
            early_tamper_diags.append(diag)
            early_tamper_blocked.append(
                _make_item(
                    item_id="blocked:permanent-id-allocation",
                    category="governed_gap_protection",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [gap_rel, *default_declaring_candidates]),
                    summary="Permanent Task ID allocation or non-null task_id on create intent is forbidden; route via Story 3.2.",
                    details={"violations": perm_id_violations, "return_stage": "3C"},
                )
            )

        clear_done_tids: list[int] = []
        if gap_doc.get("clear_done_status") is True:
            clear_done_tids.extend(
                [
                    tid
                    for tid in sorted_tids
                    if bool(triplet_statuses_by_tid.get(tid, set()) & _MATURE_DONE_STATUSES)
                ]
            )
            if not clear_done_tids and primary_tid is not None:
                clear_done_tids.append(primary_tid)
            if not clear_done_tids:
                clear_done_tids.append(0)
        for sp in list(gap_doc.get("proposed_status_patches") or []):
            if isinstance(sp, dict):
                raw_stid = sp.get("task_id")
                if isinstance(raw_stid, bool):
                    continue
                try:
                    stid = int(raw_stid)
                except (TypeError, ValueError):
                    continue
                to_st = str(sp.get("to_status") or "").strip().lower()
                cur_statuses = set(triplet_statuses_by_tid.get(stid) or set())
                from_st = str(sp.get("from_status") or "").strip().lower()
                if from_st:
                    cur_statuses.add(from_st)
                if (cur_statuses & _MATURE_DONE_STATUSES) and to_st and to_st not in _MATURE_DONE_STATUSES:
                    clear_done_tids.append(stid)
        if clear_done_tids:
            early_tamper_stages.append("3C")
            diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.CONTENT,
                entity_id=str(clear_done_tids[0]),
                expected={"mature_done_status_preserved": True, "return_stage": "3C"},
                actual={"attempted_clear_done_task_ids": sorted(set(clear_done_tids)), "return_stage": "3C"},
                resume_ref=".taskmaster/tasks/tasks.json",
            )
            early_tamper_diags.append(diag)
            early_tamper_blocked.append(
                _make_item(
                    item_id=f"blocked:clear-done:{clear_done_tids[0]}",
                    category="governed_gap_protection",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=clear_done_tids[0] if clear_done_tids[0] > 0 else primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [".taskmaster/tasks/tasks.json", *default_declaring_candidates]),
                    summary=f"Clearing mature 'done' status on Task(s) {sorted(set(clear_done_tids))} is forbidden.",
                    details={"task_ids": sorted(set(clear_done_tids)), "return_stage": "3C"},
                )
            )

        pre_scene_list = [str(bucket_cfg.get("scene_rel_path") or "").strip()] if bucket_cfg.get("scene_rel_path") else []
        early_manual_preserved, early_manual_violations = _check_manual_region_preservation(
            root_path,
            wiring_report={"scenes_inspected": pre_scene_list, "parsed_scenes": {}},
            gap_doc=gap_doc,
        )
        for mv in early_manual_violations:
            early_tamper_stages.append("4")
            early_tamper_diags.append(mv["diagnostic"])
            early_tamper_blocked.append(
                _make_item(
                    item_id=f"manual-region:{mv.get('scene_path') or 'scene'}",
                    category="native_scene_manual_region",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [mv.get("scene_path"), *default_declaring_candidates]),
                    summary=f"Proposed scene patch violates native .tscn manual regions: {mv['reason']}",
                    details=mv,
                )
            )

    if norm_flow_id and is_b_repo and norm_flow_id not in matched_flow_docs:
        diag = _diag(
            codec.ReasonCode.UNKNOWN_ENTITY,
            stage=codec.Stage.BUNDLE,
            entity_id=norm_flow_id,
            expected="committed B-route Flow definition matching --flow-id",
            actual={"flow_id": norm_flow_id, "return_stage": "3B"},
            resume_ref=records.CATALOG_PATH,
        )
        return _finish(
            {
                "ok": False,
                "route": "blocked",
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": sorted_tids,
                "ui_applicability": "unknown",
                "reason_code": codec.ReasonCode.UNKNOWN_ENTITY.value,
                "reason": "unknown_target_flow",
                "return_stage": "3B",
                "diagnostics": [*early_tamper_diags, diag],
                "verified_items": [],
                "pending_items": [],
                "manual_items": [],
                "blocked_items": [
                    *early_tamper_blocked,
                    _make_item(
                        item_id=f"blocked:flow:{norm_flow_id}",
                        category="slice_scope",
                        status="blocked",
                        binding_ref=primary_binding_ref,
                        task_id=primary_tid,
                        flow_id=norm_flow_id,
                        evidence_ref=_declaring_evidence_ref(root_path, [records.CATALOG_PATH, *default_declaring_candidates]),
                        summary=f"Flow '{norm_flow_id}' not found in committed B-route catalog.",
                    ),
                ],
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "native_scene_manual_regions_preserved": early_manual_preserved,
            }
        )

    # Pure legacy explicit_not_enabled_a passthrough (zero B traces) — STILL enforces early tamper & evidence-input guards!
    if not is_b_repo:
        if early_tamper_diags or early_tamper_blocked:
            return _finish(
                {
                    "ok": False,
                    "route": "blocked",
                    "legacy_a_passthrough": False,
                    "target_slice": norm_slice,
                    "target_flow_id": norm_flow_id,
                    "target_task_ids": sorted_tids,
                    "ui_applicability": "applicable" if (bucket_cfg or sorted_tids) else "not_applicable",
                    "reason_code": str(early_tamper_diags[0]["reason_code"]) if early_tamper_diags else codec.ReasonCode.CONFLICT.value,
                    "reason": "anti_tamper_or_invalid_input_blocked",
                    "return_stage": _earliest_stage(early_tamper_stages, default="4"),
                    "diagnostics": early_tamper_diags,
                    "verified_items": [],
                    "pending_items": [],
                    "manual_items": [],
                    "blocked_items": early_tamper_blocked,
                    "reused_ui_obligations": [],
                    "rejected_evidence": [],
                    "governed_gap_routing": [],
                    "proposed_governed_deltas": None,
                    "native_scene_manual_regions_preserved": early_manual_preserved,
                }
            )
        scene_rel = str(bucket_cfg.get("scene_rel_path") or "").strip()
        wiring_rep = inspect_scene_and_adapter_wiring(
            root_path,
            scene_paths=[scene_rel] if scene_rel else [],
            adapter_paths=[],
            binding_objects=[],
        )
        legacy_decl_ref = _declaring_evidence_ref(root_path, [scene_rel, profile_rel_ref, ".taskmaster/tasks/tasks.json"])
        pending_items = [
            _make_item(
                item_id=f"legacy:ui:{norm_slice or 'slice'}:{s}",
                category="scene_entry",
                status="pending",
                binding_ref=primary_binding_ref,
                task_id=primary_tid,
                flow_id=norm_flow_id,
                evidence_ref=legacy_decl_ref,
                summary=f"Legacy A slice surface '{s}' pending verification.",
            )
            for s in (bucket_cfg.get("suggested_surfaces") or [])
        ]
        legacy_blocked = [
            _make_item(
                item_id=f"legacy:wiring:{f['failure_kind']}:{f.get('scene_path') or 'scene'}",
                category="wiring_check",
                status="failed",
                binding_ref=primary_binding_ref,
                task_id=primary_tid,
                flow_id=norm_flow_id,
                evidence_ref=_declaring_evidence_ref(root_path, [f.get("scene_path"), *default_declaring_candidates]),
                summary=f["message"],
                details=f,
            )
            for f in wiring_rep["findings"]
        ]
        return _finish(
            {
                "ok": wiring_rep["wiring_static_ok"],
                "route": "explicit_not_enabled_a",
                "legacy_a_passthrough": True,
                "target_slice": norm_slice,
                "target_flow_id": norm_flow_id,
                "target_task_ids": sorted_tids,
                "ui_applicability": "applicable" if (bucket_cfg or sorted_tids) else "not_applicable",
                "reason_code": codec.ReasonCode.OK.value if wiring_rep["wiring_static_ok"] else codec.ReasonCode.CONFLICT.value,
                "reason": "explicit_not_enabled_a",
                "return_stage": None if wiring_rep["wiring_static_ok"] else "4",
                "diagnostics": [],
                "verified_items": [],
                "pending_items": pending_items,
                "manual_items": [],
                "blocked_items": legacy_blocked,
                "reused_ui_obligations": [],
                "rejected_evidence": [],
                "governed_gap_routing": [],
                "proposed_governed_deltas": None,
                "wiring_inspection": {
                    "wiring_static_ok": wiring_rep["wiring_static_ok"],
                    "scenes_inspected": wiring_rep["scenes_inspected"],
                    "adapters_inspected": wiring_rep["adapters_inspected"],
                    "findings": wiring_rep["findings"],
                },
                "native_scene_manual_regions_preserved": True,
            }
        )

    # Evaluate ONLY target-slice Tasks via LIVE Story 3.8 gate + Story 3.5 InputSet (never wait on unrelated tasks!).
    task_contexts: dict[int, dict[str, Any]] = {}
    all_diagnostics: list[dict[str, Any]] = list(early_tamper_diags)
    verified_items: list[dict[str, Any]] = []
    pending_items: list[dict[str, Any]] = []
    manual_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = list(early_tamper_blocked)
    return_stages: list[str | None] = list(early_tamper_stages)

    gate_args = [(str(root_path), tid, operation) for tid in sorted_tids]
    if len(gate_args) > 1:
        try:
            with ProcessPoolExecutor(max_workers=min(4, len(gate_args))) as gate_pool:
                evaluated_gates = list(gate_pool.map(_eval_single_task_gate_worker, gate_args))
        except (OSError, PermissionError, RuntimeError):
            evaluated_gates = [_eval_single_task_gate_worker(item) for item in gate_args]
    else:
        evaluated_gates = [_eval_single_task_gate_worker(item) for item in gate_args]

    for tid, gate_res, iset_res in evaluated_gates:
        revs_by_path: dict[str, int] = {}
        for pid, bdoc in b_ctx["bindings"].items():
            if any(int(tm.get("task_id") or 0) == tid for tm in (bdoc.get("task_mappings") or [])):
                bpath = b_ctx["binding_paths"].get(pid)
                if bpath:
                    revs_by_path[bpath] = int(bdoc.get("binding_revision") or 0)
        task_contexts[tid] = {
            "task_id": tid,
            "gate": gate_res,
            "input_set": iset_res,
            "input_set_digest": gate_res.get("input_set_digest") or iset_res.get("input_set_digest"),
            "binding_refs": list(gate_res.get("binding_refs") or iset_res.get("binding_refs") or []),
            "plan_refs": list(gate_res.get("plan_refs") or iset_res.get("plan_refs") or []),
            "binding_revisions": list(revs_by_path.values()),
            "binding_revisions_by_path": revs_by_path,
            "master_status": master_status_by_tid.get(tid, ""),
        }
        if not gate_res.get("ok"):
            rstage = str(gate_res.get("return_stage") or "5")
            return_stages.append(rstage)
            diags = list(gate_res.get("diagnostics") or [])
            all_diagnostics.extend(diags)
            first_bref = next(
                (str(r.get("path")) for r in task_contexts[tid]["binding_refs"] if isinstance(r, dict) and r.get("path")),
                primary_binding_ref,
            )
            blocked_items.append(
                _make_item(
                    item_id=f"gate:task-{tid}",
                    category="chapter6_gate",
                    status="blocked",
                    binding_ref=first_bref,
                    task_id=tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [first_bref, *default_declaring_candidates]),
                    summary=f"Target-slice Task {tid} blocked by Story 3.8 gate: {gate_res.get('reason')}",
                    details={"return_stage": rstage, "reason_code": gate_res.get("reason_code")},
                )
            )

    # Gather target-slice plans, bindings, Stage-4/5 semantics, implementation objects, and obligations.
    target_plans = [b_ctx["plans"][pid] for pid in matched_plan_ids if pid in b_ctx["plans"]]
    target_bindings = [b_ctx["bindings"][pid] for pid in matched_plan_ids if pid in b_ctx["bindings"]]

    all_impl_objects: list[dict[str, Any]] = []
    all_obligations: list[dict[str, Any]] = []
    stage4_semantics_list: list[dict[str, Any]] = []
    scene_paths: list[str] = []
    adapter_paths: list[str] = []
    manifest_paths: list[str] = []
    covered_flow_req_pairs: set[tuple[str, str]] = set()
    committed_plan_req_ids: set[str] = set()
    flow_to_binding_ref: dict[str, str] = {}
    flow_to_task_ids: dict[str, list[int]] = {}
    target_stage5_test_ids: set[str] = set()

    for pid in matched_plan_ids:
        pdoc = b_ctx["plans"].get(pid)
        bdoc = b_ctx["bindings"].get(pid)
        bpath = b_ctx["binding_paths"].get(pid) or primary_binding_ref
        if not isinstance(pdoc, dict) or not isinstance(bdoc, dict):
            continue
        for req_row in pdoc.get("requirements") or []:
            if isinstance(req_row, dict) and req_row.get("requirement_id"):
                committed_plan_req_ids.add(str(req_row["requirement_id"]))
        plan_flow_tids: set[int] = set()
        for tm in bdoc.get("task_mappings") or []:
            tm_tid = int(tm.get("task_id") or 0)
            tm_flows = [str(f) for f in (tm.get("flow_ids") or []) if str(f).strip()]
            if set(tm_flows) & set(matched_flow_docs.keys()):
                plan_flow_tids.add(tm_tid)
            for fid in tm_flows:
                if fid in matched_flow_docs:
                    flow_to_binding_ref.setdefault(fid, bpath)
                    flow_to_task_ids.setdefault(fid, [])
                    if tm_tid not in flow_to_task_ids[fid]:
                        flow_to_task_ids[fid].append(tm_tid)
            if tm_tid in target_tids or not target_tids:
                for fid in tm_flows:
                    for rid in tm.get("requirement_ids") or []:
                        covered_flow_req_pairs.add((fid, str(rid)))
        # P-04: Include ALL Flow-associated UI implementation_objects across producer+consumer tasks!
        effective_obj_tids = target_tids | plan_flow_tids
        for obj in bdoc.get("implementation_objects") or []:
            resp_tids = set(int(x) for x in (obj.get("responsible_task_ids") or []) if type(x) is int or str(x).isdigit())
            obj_flows = set(str(f) for f in (obj.get("flow_ids") or []) if str(f).strip())
            is_ui_obj = obj.get("kind") in {"scene", "binding", "adapter"}
            include_obj = (
                not effective_obj_tids
                or bool(resp_tids & effective_obj_tids)
                or (is_ui_obj and bool(obj_flows & set(matched_flow_docs.keys())))
            )
            if include_obj:
                all_impl_objects.append(obj)
                tref = obj.get("target_ref")
                if isinstance(tref, dict):
                    for f in tref.get("files") or []:
                        fpath = str(f.get("path") or "").strip()
                        if fpath.lower().endswith(".tscn"):
                            scene_paths.append(fpath)
                        elif fpath.lower().endswith((".cs", ".gd")) and obj.get("kind") in {"adapter", "binding"}:
                            adapter_paths.append(fpath)
        for obl in bdoc.get("obligations") or []:
            if not isinstance(obl, dict):
                continue
            obl_copy = deepcopy(obl)
            obl_copy["_binding_ref"] = bpath
            all_obligations.append(obl_copy)
            s4_meta = ch4_binding._parse_prefixed_json(str(obl.get("responsibility") or ""), ch4_binding.STAGE4_OBL_PREFIX) or {}
            obl_tids = set(int(x) for x in (s4_meta.get("task_ids") or []) if type(x) is int)
            obl_flows = set(str(f) for f in (obl.get("flow_ids") or []) if str(f).strip())
            if (not target_tids or (obl_tids & target_tids)) or (obl_flows & set(matched_flow_docs.keys())):
                for tid_s in s4_meta.get("test_ids") or []:
                    if str(tid_s).strip():
                        target_stage5_test_ids.add(str(tid_s).strip())
        for mref in bdoc.get("manifest_refs") or []:
            if isinstance(mref, dict):
                if mref.get("path"):
                    manifest_paths.append(str(mref["path"]).strip())
                mfiles = mref.get("files") or []
                for mf in mfiles:
                    if isinstance(mf, dict) and mf.get("path"):
                        manifest_paths.append(str(mf["path"]).strip())
                if not mref.get("path") and not mfiles and mref.get("ref"):
                    manifest_paths.append(str(mref["ref"]).strip())
        if bdoc.get("stage") in {"4", "5"}:
            try:
                stage4_semantics_list.append(ch4_binding.extract_stage4_semantics(pdoc, bdoc))
            except codec.CodecError:
                pass

    if bucket_cfg.get("scene_rel_path"):
        scene_paths.append(str(bucket_cfg["scene_rel_path"]).strip())

    # AC-1 (P-04): Check legal non-UI / zero-UI applicability across ALL matched flows (never bypass early tamper blocks!).
    if target_plans and target_bindings and not blocked_items and not all_diagnostics:
        all_non_ui = True
        non_ui_proofs: list[dict[str, Any]] = []
        for pid in matched_plan_ids:
            pdoc = b_ctx["plans"][pid]
            bdoc = b_ctx["bindings"][pid]
            plan_flows = [fdoc for _fid, (fpid, fdoc) in sorted(matched_flow_docs.items()) if fpid == pid]
            if plan_flows:
                for fdoc in plan_flows:
                    ok_non_ui, proof_info = _plan_non_ui_proof_valid(
                        root_path,
                        plan_doc=pdoc,
                        binding_doc=bdoc,
                        flow_doc=fdoc,
                        bucket_cfg=bucket_cfg,
                        impl_objects=all_impl_objects,
                        target_tids=target_tids,
                    )
                    if not ok_non_ui:
                        all_non_ui = False
                        break
                    non_ui_proofs.append(proof_info)
                if not all_non_ui:
                    break
            else:
                ok_non_ui, proof_info = _plan_non_ui_proof_valid(
                    root_path,
                    plan_doc=pdoc,
                    binding_doc=bdoc,
                    flow_doc=None,
                    bucket_cfg=bucket_cfg,
                    impl_objects=all_impl_objects,
                    target_tids=target_tids,
                )
                if not ok_non_ui:
                    all_non_ui = False
                    break
                non_ui_proofs.append(proof_info)

        if all_non_ui and non_ui_proofs:
            proof_ref_path = (
                non_ui_proofs[0]["other_verification_refs"][0]
                if non_ui_proofs[0].get("other_verification_refs")
                else non_ui_proofs[0]["adoption_proof_refs"][0]
            )
            verified_items.append(
                _make_item(
                    item_id=f"non-ui:{matched_plan_ids[0]}",
                    category="non_ui_applicability",
                    status="verified",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [proof_ref_path, *default_declaring_candidates]),
                    summary="Committed non-UI / non-Flow scope verified with substantive rationale and live proof.",
                    details=non_ui_proofs[0],
                )
            )
            return _finish(
                {
                    "ok": True,
                    "route": "B",
                    "legacy_a_passthrough": False,
                    "target_slice": norm_slice,
                    "target_flow_id": primary_flow_id,
                    "target_task_ids": sorted_tids,
                    "ui_applicability": "not_applicable",
                    "non_ui_proof": non_ui_proofs[0],
                    "reason_code": codec.ReasonCode.OK.value,
                    "reason": "ui_not_applicable_with_committed_proof",
                    "return_stage": None,
                    "diagnostics": [],
                    "verified_items": verified_items,
                    "pending_items": [],
                    "manual_items": [],
                    "blocked_items": [],
                    "reused_ui_obligations": [],
                    "rejected_evidence": [],
                    "governed_gap_routing": [],
                    "proposed_governed_deltas": None,
                    "wiring_inspection": {
                        "wiring_static_ok": True,
                        "scenes_inspected": [],
                        "adapters_inspected": [],
                        "findings": [],
                    },
                    "native_scene_manual_regions_preserved": True,
                }
            )

    # P-04: Fail closed if a B-route UI Flow maps to zero tasks (sorted_tids empty)!
    if matched_flow_docs and not sorted_tids:
        return_stages.append("3C")
        diag = _diag(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=primary_flow_id or norm_slice or "flow",
            expected="at least one mapped Task for B-route UI Flow",
            actual={"flow_ids": sorted(matched_flow_docs.keys()), "mapped_task_ids": [], "return_stage": "3C"},
            resume_ref=primary_binding_ref,
        )
        all_diagnostics.append(diag)
        blocked_items.append(
            _make_item(
                item_id=f"blocked:flow-zero-tasks:{primary_flow_id or 'flow'}",
                category="slice_scope",
                status="blocked",
                binding_ref=primary_binding_ref,
                task_id=None,
                flow_id=primary_flow_id,
                evidence_ref=_declaring_evidence_ref(root_path, default_declaring_candidates),
                summary=f"B-route UI Flow(s) {sorted(matched_flow_docs.keys())} map to zero Tasks; cannot close empty scope.",
                details={"flow_ids": sorted(matched_flow_docs.keys()), "return_stage": "3C"},
            )
        )

    # AC-1 (P-04): Extract declared UI obligations ONLY from explicit Flow.ui / Stage-4 UI metadata / explicit non-default repo profile.
    # Forbid generic Flow fields (entry/success_end/observable_result) or built-in default profile placeholders from masking blank UI declarations!
    declared_ui: dict[str, Any] = {
        "scene_entry": [],
        "return_path": [],
        "real_engine_input": [],
        "feedback": [],
        "four_part_bindings": {},
        "manual_obligations": [],
    }
    any_flow_has_explicit_ui_block = False
    for fid, (_pid, fdoc) in sorted(matched_flow_docs.items()):
        if isinstance(fdoc.get("ui"), dict):
            any_flow_has_explicit_ui_block = True
            ui_blk = fdoc["ui"]
            declared_ui["scene_entry"].extend(str(x).strip() for x in (ui_blk.get("scene_entry") or []) if str(x).strip())
            declared_ui["return_path"].extend(str(x).strip() for x in (ui_blk.get("scene_return") or []) if str(x).strip())
            declared_ui["real_engine_input"].extend(str(x).strip() for x in (ui_blk.get("inputs") or []) if str(x).strip())
            declared_ui["feedback"].extend(str(x).strip() for x in (ui_blk.get("feedback") or []) if str(x).strip())

        hv = fdoc.get("human_verification") if isinstance(fdoc.get("human_verification"), dict) else {}
        if hv.get("applicability") == "applicable":
            for resp in hv.get("responsibilities") or []:
                if str(resp).strip():
                    declared_ui["manual_obligations"].append(
                        {"zone": "human_verification", "description": str(resp).strip(), "source": f"flow:{fid}", "flow_id": fid}
                    )

    # Collect four-part bindings and Stage-4 UI metadata/manual zones.
    for bdoc in target_bindings:
        for part in bdoc.get("parts") or []:
            if isinstance(part, dict) and part.get("kind"):
                declared_ui["four_part_bindings"][part["kind"]] = {
                    "applicability": part.get("applicability"),
                    "rationale": part.get("rationale"),
                    "responsibilities": list(part.get("responsibilities") or []),
                }
                ui_meta = ch4_binding._parse_prefixed_json(str(part.get("rationale") or ""), ch4_binding.STAGE4_UI_PREFIX)
                if isinstance(ui_meta, dict):
                    for key_src, key_dst in (
                        ("scene_entry", "scene_entry"),
                        ("scene_return", "return_path"),
                        ("inputs", "real_engine_input"),
                        ("feedback", "feedback"),
                    ):
                        val = ui_meta.get(key_src)
                        if isinstance(val, list):
                            declared_ui[key_dst].extend(str(x).strip() for x in val if str(x).strip())
                        elif isinstance(val, str) and val.strip():
                            declared_ui[key_dst].append(val.strip())
                    for z in ui_meta.get("human_owned_zones") or []:
                        declared_ui["manual_obligations"].append(
                            {"zone": str(z), "description": f"Human-owned UI zone: {z}", "source": "stage4:ui"}
                        )
    for sem4 in stage4_semantics_list:
        for z in (sem4.get("ui_manual_zones") or []):
            z_str = str(z) if not isinstance(z, dict) else str(z.get("zone") or z.get("name") or z)
            declared_ui["manual_obligations"].append(
                {"zone": z_str, "description": f"Stage-4 human-owned zone: {z_str}", "source": "stage4:semantics"}
            )

    # Explicit repo-local / CLI chapter7-profile.json bucket contract supplements UI obligations
    # ONLY when loaded from a real profile file (never built-in defaults) AND not overriding an explicit blank Flow.ui block!
    if bucket_cfg and profile_is_explicit and not any_flow_has_explicit_ui_block:
        def _non_placeholder(val: Any) -> str:
            s = str(val or "").strip()
            return "" if s in _DEFAULT_PROFILE_PLACEHOLDERS else s

        ui_entry_v = _non_placeholder(bucket_cfg.get("ui_entry"))
        if ui_entry_v:
            declared_ui["scene_entry"].append(ui_entry_v)
        screen_state = bucket_cfg.get("screen_state") if isinstance(bucket_cfg.get("screen_state"), dict) else {}
        rec_exit_v = _non_placeholder(screen_state.get("recovery_exit"))
        if rec_exit_v:
            declared_ui["return_path"].append(rec_exit_v)
        player_act_v = _non_placeholder(bucket_cfg.get("player_action"))
        if player_act_v:
            declared_ui["real_engine_input"].append(player_act_v)
        sys_resp_v = _non_placeholder(bucket_cfg.get("system_response"))
        if sys_resp_v:
            declared_ui["feedback"].append(sys_resp_v)

    # Load committed MVG manifests via _resolve_contained_path (P-01).
    manifest_docs: dict[str, dict[str, Any]] = {}
    for raw_mrel in sorted(set(manifest_paths)):
        mfile, canon_mrel, merr = _resolve_contained_path(
            root_path, raw_mrel, label="manifest_ref", entity_id=raw_mrel
        )
        if merr is not None or mfile is None or canon_mrel is None:
            return_stages.append("5")
            all_diagnostics.append(
                merr
                or _diag(
                    codec.ReasonCode.UNSAFE_PATH,
                    stage=codec.Stage.PATH,
                    entity_id=raw_mrel,
                    expected="safe repository-contained MVG manifest path",
                    actual={"path": raw_mrel, "return_stage": "5"},
                    resume_ref=raw_mrel,
                )
            )
            blocked_items.append(
                _make_item(
                    item_id=f"blocked:unsafe-manifest:{raw_mrel}",
                    category="manifest_integrity",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, default_declaring_candidates),
                    summary=f"Bound MVG manifest path is unsafe: {raw_mrel}",
                    details={"manifest_path": raw_mrel, "return_stage": "5"},
                )
            )
            continue
        if mfile.is_file():
            try:
                inventory.no_reparse(mfile)
                mdoc = codec.strict_json_loads(mfile.read_bytes())
                if isinstance(mdoc, dict):
                    manifest_docs[canon_mrel] = mdoc
                    for claim in (mdoc.get("coverage") or {}).get("excluded_claims") or []:
                        if str(claim).strip():
                            declared_ui["manual_obligations"].append(
                                {"zone": "visual_feel_manual", "description": str(claim).strip(), "source": canon_mrel}
                            )
            except (codec.CodecError, OSError):
                pass

    # Check undeclared/blank UI obligations unconditionally when UI IS required (never silently skip!).
    missing_ui_fields: list[str] = []
    if not declared_ui["scene_entry"]:
        missing_ui_fields.append("scene_entry")
    if not declared_ui["return_path"]:
        missing_ui_fields.append("return_path")
    if not declared_ui["feedback"]:
        missing_ui_fields.append("feedback")
    if not declared_ui["real_engine_input"]:
        missing_ui_fields.append("real_engine_input")

    # Reject any Flow claiming ui.applicability=="not_applicable" WITHOUT legal proof across ALL matched flows!
    invalid_not_applicable_claims: list[str] = []
    for fid, (pid, fdoc) in sorted(matched_flow_docs.items()):
        ui_blk = fdoc.get("ui") if isinstance(fdoc.get("ui"), dict) else None
        if ui_blk and ui_blk.get("applicability") == "not_applicable":
            ok_proof, why = _plan_non_ui_proof_valid(
                root_path,
                plan_doc=b_ctx["plans"][pid],
                binding_doc=b_ctx["bindings"][pid],
                flow_doc=fdoc,
                bucket_cfg=bucket_cfg,
                impl_objects=all_impl_objects,
                target_tids=target_tids,
            )
            if not ok_proof:
                invalid_not_applicable_claims.append(f"{fid}:{why.get('reason')}")

    if invalid_not_applicable_claims:
        return_stages.append("3B")
        diag = _diag(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=primary_flow_id or norm_slice,
            expected="committed non-UI proof without player-facing UI contradiction",
            actual={"invalid_not_applicable_claims": invalid_not_applicable_claims, "return_stage": "3B"},
            resume_ref=primary_plan_ref or primary_binding_ref,
        )
        all_diagnostics.append(diag)
        blocked_items.append(
            _make_item(
                item_id=f"blocked:invalid-non-ui:{primary_flow_id or norm_slice}",
                category="ui_applicability",
                status="blocked",
                binding_ref=primary_binding_ref,
                task_id=primary_tid,
                flow_id=primary_flow_id,
                evidence_ref=_declaring_evidence_ref(root_path, [primary_plan_ref, *default_declaring_candidates]),
                summary=f"Invalid non-UI skip claim rejected fail-closed: {', '.join(invalid_not_applicable_claims)}",
                details={"return_stage": "3B"},
            )
        )

    if missing_ui_fields:
        rstage = "3B" if any(f in {"scene_entry", "return_path", "feedback"} for f in missing_ui_fields) else "4"
        return_stages.append(rstage)
        diag = _diag(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            stage=codec.Stage.CONTENT,
            entity_id=primary_flow_id or norm_slice or str(primary_tid),
            expected={"declared_ui_fields": ["scene_entry", "return_path", "real_engine_input", "feedback"]},
            actual={"missing_ui_fields": missing_ui_fields, "return_stage": rstage},
            resume_ref=primary_binding_ref,
        )
        all_diagnostics.append(diag)
        blocked_items.append(
            _make_item(
                item_id=f"blocked:missing-ui-fields:{primary_flow_id or norm_slice or primary_tid}",
                category="ui_declaration",
                status="blocked",
                binding_ref=primary_binding_ref,
                task_id=primary_tid,
                flow_id=primary_flow_id,
                evidence_ref=_declaring_evidence_ref(root_path, default_declaring_candidates),
                summary=f"Required UI obligations undeclared/blank (cannot auto-skip): {', '.join(missing_ui_fields)}",
                details={"missing_ui_fields": missing_ui_fields, "return_stage": rstage},
            )
        )

    # AC-2 (P-01 + P-05): Match Chapter 6 UI evidence to current InputSet & test identity; block failed/skipped/zero-test runtime evidence!
    reused_ui_obligations, rejected_evidence, failed_runtime_evidence = _evaluate_evidence_reuse(
        root_path,
        raw_records=raw_evidence,
        task_contexts=task_contexts,
        target_flow_ids=set(matched_flow_docs.keys()),
        target_slice=norm_slice,
        expected_profile=delivery_profile,
    )

    for idx_f, frev in enumerate(failed_runtime_evidence):
        return_stages.append("6")
        f_bref = frev.get("binding_ref") or primary_binding_ref
        f_tid = frev.get("task_id") if frev.get("task_id") is not None else primary_tid
        f_fid = frev.get("flow_id") or primary_flow_id
        f_diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.TARGET,
            entity_id=str(frev.get("test_path") or frev.get("evidence_path") or f"runtime-evidence-{idx_f + 1}"),
            expected="passed real-engine-input execution with tests > 0 and failures == errors == skipped == 0",
            actual={
                "reason": frev.get("reason"),
                "test_path": frev.get("test_path"),
                "evidence_path": frev.get("evidence_path"),
                "return_stage": "6",
            },
            resume_ref=frev.get("evidence_path") or frev.get("test_path") or f_bref,
        )
        all_diagnostics.append(f_diag)
        blocked_items.append(
            _make_item(
                item_id=f"runtime-evidence-failed:{idx_f + 1}:{frev.get('test_path') or 'evidence'}",
                category="runtime_evidence_failed",
                status="failed",
                binding_ref=f_bref,
                task_id=f_tid,
                flow_id=f_fid,
                evidence_ref=_declaring_evidence_ref(
                    root_path,
                    [frev.get("evidence_path"), frev.get("test_path"), f_bref, *default_declaring_candidates],
                    fallback_digest=frev.get("evidence_sha256"),
                ),
                summary=f"Runtime UI evidence failed/skipped/empty ({frev.get('reason')}): {frev.get('test_path') or frev.get('evidence_path')}",
                details=frev,
            )
        )

    reused_flows: set[str] = set()
    reused_keys: set[tuple[str | None, int, str]] = set()
    reused_test_paths: set[str] = set()
    for rev in reused_ui_obligations:
        if rev.get("flow_id"):
            reused_flows.add(str(rev["flow_id"]))
        reused_keys.add((rev.get("flow_id"), int(rev["task_id"]), str(rev["obligation_id"])))
        if rev.get("test_path"):
            reused_test_paths.add(str(rev["test_path"]).casefold())
        verified_items.append(
            _make_item(
                item_id=f"reused:{rev['obligation_id']}:T{rev['task_id']}",
                category="real_engine_input",
                status="verified",
                binding_ref=rev["binding_ref"] or primary_binding_ref,
                task_id=rev["task_id"],
                flow_id=rev["flow_id"] or primary_flow_id,
                evidence_ref=_declaring_evidence_ref(
                    root_path,
                    [rev["evidence_path"], rev["test_path"], rev["binding_ref"], *default_declaring_candidates],
                    fallback_digest=rev.get("evidence_sha256"),
                ),
                summary=f"Reused verified Chapter 6 real-engine-input UI evidence for Task {rev['task_id']} ({rev['test_path']}).",
                details={
                    "test_path": rev["test_path"],
                    "test_sha256": rev["test_sha256"],
                    "input_set_digest": rev["input_set_digest"],
                    "tests": rev["tests"],
                    "reused_from_chapter6": True,
                },
            )
        )

    # AC-3 (P-06): Deterministic .tscn (recursive) + .cs/.gd wiring, type, and lifecycle inspection.
    wiring_report = inspect_scene_and_adapter_wiring(
        root_path,
        scene_paths=scene_paths,
        adapter_paths=adapter_paths,
        binding_objects=all_impl_objects,
    )
    for finding in wiring_report["findings"]:
        rstage = str(finding.get("return_stage") or "4")
        return_stages.append(rstage)
        ref_path = finding.get("adapter_path") or finding.get("scene_path") or primary_binding_ref
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.TARGET,
            entity_id=str(finding.get("node_path") or ref_path),
            expected="intact scene/adapter binding, compatible Godot node type, and valid lifecycle",
            actual={
                "failure_kind": finding["failure_kind"],
                "scene_path": finding.get("scene_path"),
                "adapter_path": finding.get("adapter_path"),
                "node_path": finding.get("node_path"),
                "return_stage": rstage,
            },
            resume_ref=ref_path,
        )
        all_diagnostics.append(diag)
        blocked_items.append(
            _make_item(
                item_id=f"wiring:{finding['failure_kind']}:{finding.get('node_path') or ref_path}",
                category="wiring_check",
                status="failed",
                binding_ref=primary_binding_ref,
                task_id=primary_tid,
                flow_id=primary_flow_id,
                evidence_ref=_declaring_evidence_ref(root_path, [ref_path, *default_declaring_candidates]),
                summary=finding["message"],
                details=finding,
            )
        )

    # AC-3 (P-05): Filter cumulative MVG manifest tests strictly to target Flow(s) / target_tids test_ids!
    for mrel, mdoc in sorted(manifest_docs.items()):
        target_manifest_test_ids: set[str] = set(target_stage5_test_ids)
        for mflow in mdoc.get("flows") or []:
            if not isinstance(mflow, dict):
                continue
            mfid = str(mflow.get("id") or "")
            mf_tids = {int(x) for x in (mflow.get("task_ids") or []) if type(x) is int}
            if mfid in matched_flow_docs or (mf_tids & target_tids):
                for tid_s in mflow.get("test_ids") or []:
                    if str(tid_s).strip():
                        target_manifest_test_ids.add(str(tid_s).strip())
                for hoff in mflow.get("handoffs") or []:
                    if isinstance(hoff, dict):
                        for tid_s in hoff.get("test_ids") or []:
                            if str(tid_s).strip():
                                target_manifest_test_ids.add(str(tid_s).strip())

        for test_row in mdoc.get("tests") or []:
            if not isinstance(test_row, dict):
                continue
            tid_label = str(test_row.get("id") or "").strip()
            if target_manifest_test_ids and tid_label and tid_label not in target_manifest_test_ids:
                continue
            tpath = _norm_rel(str(test_row.get("path") or ""))
            tstate = str(test_row.get("state") or "").strip().lower()
            tid_key = tid_label or tpath
            if tstate == "planned":
                pending_items.append(
                    _make_item(
                        item_id=f"planned-test:{tid_key}",
                        category="planned_test_obligation",
                        status="pending",
                        binding_ref=primary_binding_ref,
                        task_id=primary_tid,
                        flow_id=primary_flow_id,
                        evidence_ref=_declaring_evidence_ref(root_path, [mrel, *default_declaring_candidates]),
                        summary=f"Planned test '{tid_key}' ({tpath}) is not executed yet (never counted as passed).",
                        details={"test_path": tpath, "manifest_path": mrel, "state": "planned"},
                    )
                )
                continue
            if tpath:
                integrity = _inspect_test_file_integrity(root_path, tpath)
                if integrity["status"] in {"empty", "skipped", "missing", "unsafe"}:
                    return_stages.append("5" if integrity["status"] in {"missing", "unsafe"} else "6")
                    diag = _diag(
                        codec.ReasonCode.UNSAFE_PATH if integrity["status"] == "unsafe" else codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.PATH if integrity["status"] == "unsafe" else codec.Stage.TARGET,
                        entity_id=tid_key,
                        expected="executable non-empty non-skipped repository-contained bound test file",
                        actual={"test_path": tpath, "integrity": integrity["status"], "reason": integrity["reason"]},
                        resume_ref=tpath,
                    )
                    all_diagnostics.append(diag)
                    blocked_items.append(
                        _make_item(
                            item_id=f"test-integrity:{tid_key}",
                            category="test_evidence_integrity",
                            status="failed",
                            binding_ref=primary_binding_ref,
                            task_id=primary_tid,
                            flow_id=primary_flow_id,
                            evidence_ref=_declaring_evidence_ref(root_path, [tpath, mrel, *default_declaring_candidates]),
                            summary=f"Bound test '{tid_key}' failed integrity check: {integrity['reason']} ({tpath}).",
                            details=integrity,
                        )
                    )
                elif integrity["path"].casefold() not in reused_test_paths:
                    # P-05: Unexecuted implemented bound test stays in pending_items (never silently treated as runtime passed!).
                    pending_items.append(
                        _make_item(
                            item_id=f"unexecuted-test:{tid_key}",
                            category="unexecuted_bound_test",
                            status="pending",
                            binding_ref=primary_binding_ref,
                            task_id=primary_tid,
                            flow_id=primary_flow_id,
                            evidence_ref=_declaring_evidence_ref(root_path, [integrity["path"], mrel, *default_declaring_candidates]),
                            summary=f"Implemented bound test '{tid_key}' ({integrity['path']}) has no matching runtime execution evidence yet.",
                            details={"test_path": integrity["path"], "manifest_path": mrel, "state": tstate or "implemented"},
                        )
                    )

    # P-05: Track real_engine_input coverage per Flow AND per Stage-5 UI (flow_id, task_id, obligation_id)!
    if not any(b.get("category") in {"ui_declaration", "ui_applicability"} for b in blocked_items):
        flows_to_check = sorted(matched_flow_docs.keys()) if matched_flow_docs else [primary_flow_id]
        for fid in flows_to_check:
            flow_bref = flow_to_binding_ref.get(fid or "", primary_binding_ref) if fid else primary_binding_ref
            flow_tids = flow_to_task_ids.get(fid or "", []) if fid else []
            flow_tid = flow_tids[0] if flow_tids else primary_tid
            if fid is not None:
                flow_covered = fid in reused_flows
            else:
                flow_covered = len(reused_ui_obligations) > 0
            if not flow_covered:
                pending_items.append(
                    _make_item(
                        item_id=f"pending:real_engine_input:{fid or norm_slice or flow_tid}",
                        category="real_engine_input",
                        status="pending",
                        binding_ref=flow_bref,
                        task_id=flow_tid,
                        flow_id=fid,
                        evidence_ref=_declaring_evidence_ref(root_path, [flow_bref, *default_declaring_candidates]),
                        summary=(
                            f"Real engine input UI verification pending for '{fid or norm_slice or flow_tid}': "
                            "no matching Chapter 6 GdUnit4 engine-input evidence matches current InputSet."
                        ),
                        details={
                            "wiring_static_ok": wiring_report["wiring_static_ok"],
                            "rejected_evidence_count": len(rejected_evidence),
                        },
                    )
                )

        # Also check explicit Stage-5 UI obligations per (flow_id, task_id, obligation_id).
        for obl in all_obligations:
            obl_id = str(obl.get("id") or "").strip()
            if not obl_id:
                continue
            resp_text = str(obl.get("responsibility") or "")
            is_ui_obl = bool(_UI_KEYWORD_RE.search(f"{obl_id} {resp_text}"))
            if not is_ui_obl:
                continue
            obl_flows = [str(f) for f in (obl.get("flow_ids") or []) if str(f).strip()]
            s4_meta = ch4_binding._parse_prefixed_json(resp_text, ch4_binding.STAGE4_OBL_PREFIX) or {}
            obl_tids = [int(x) for x in (s4_meta.get("task_ids") or []) if type(x) is int and int(x) in target_tids]
            if not obl_tids:
                obl_tids = [primary_tid] if primary_tid is not None else []
            obl_bref = str(obl.get("_binding_ref") or primary_binding_ref)
            for fid in (obl_flows or [primary_flow_id]):
                if fid and matched_flow_docs and fid not in matched_flow_docs:
                    continue
                for otid in obl_tids:
                    if (fid, otid, obl_id) not in reused_keys:
                        pending_items.append(
                            _make_item(
                                item_id=f"pending:stage5-ui-obl:{obl_id}:T{otid}:{fid or 'slice'}",
                                category="stage5_ui_obligation",
                                status="pending",
                                binding_ref=obl_bref,
                                task_id=otid,
                                flow_id=fid,
                                evidence_ref=_declaring_evidence_ref(root_path, [obl_bref, *default_declaring_candidates]),
                                summary=f"Stage-5 UI obligation '{obl_id}' for Task {otid} ({fid or norm_slice}) pending matching runtime evidence.",
                                details={"obligation_id": obl_id, "task_id": otid, "flow_id": fid},
                            )
                        )

    # AC-3: Always keep manual visual/feel obligations independent (never auto-cleared by automated checks!).
    seen_manual: set[str] = set()
    if not declared_ui["manual_obligations"]:
        declared_ui["manual_obligations"].append(
            {
                "zone": "visual_feel_manual",
                "description": "Manual visual layout, readability, and interaction feel review for target UI slice.",
                "source": primary_binding_ref,
            }
        )
    for idx, mobl in enumerate(declared_ui["manual_obligations"]):
        key = f"{mobl['zone']}:{mobl['description']}"
        if key in seen_manual:
            continue
        seen_manual.add(key)
        m_source = str(mobl.get("source") or "")
        m_flow = mobl.get("flow_id") or primary_flow_id
        m_bref = flow_to_binding_ref.get(m_flow or "", primary_binding_ref) if m_flow else primary_binding_ref
        src_path_cand = m_source if "/" in m_source else None
        manual_items.append(
            _make_item(
                item_id=f"manual:{mobl['zone']}:{idx + 1}",
                category="manual_visual_feel",
                status="manual_pending",
                binding_ref=m_bref,
                task_id=primary_tid,
                flow_id=m_flow,
                evidence_ref=_declaring_evidence_ref(root_path, [src_path_cand, m_bref, *default_declaring_candidates]),
                summary=mobl["description"],
                details={"zone": mobl["zone"], "source": m_source, "auto_clearable": False},
            )
        )

    # AC-4: Governed gap routing (3A..5 via Story 3.10), Story 3.1/3.2 schema-conformant "operations" deltas,
    # and native .tscn manual-region preservation (using full parsed_scenes from wiring_report).
    governed_gap_routing: list[dict[str, Any]] = []
    proposed_governed_deltas: dict[str, Any] | None = None
    manual_regions_preserved = early_manual_preserved
    if isinstance(gap_doc, dict) and early_manual_preserved:
        manual_regions_preserved, manual_violations = _check_manual_region_preservation(
            root_path, wiring_report=wiring_report, gap_doc=gap_doc
        )
        for mv in manual_violations:
            return_stages.append("4")
            all_diagnostics.append(mv["diagnostic"])
            blocked_items.append(
                _make_item(
                    item_id=f"manual-region:{mv.get('scene_path') or 'scene'}",
                    category="native_scene_manual_region",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [mv.get("scene_path"), *default_declaring_candidates]),
                    summary=f"Proposed scene patch violates native .tscn manual regions: {mv['reason']}",
                    details=mv,
                )
            )

    if isinstance(gap_doc, dict):
        # 4b. Route definition/contract/ownership/binding/obligation gaps to exact owning_stage (3A..5).
        changed_paths = [_norm_rel(str(p)) for p in (gap_doc.get("changed_paths") or []) if str(p).strip()]
        gap_cats = [str(c).strip().lower() for c in (gap_doc.get("gap_categories") or []) if str(c).strip()]
        def_stages: list[str] = []
        def_paths: list[str] = []
        for p in changed_paths:
            cls, stg = defect_routing._classify_path(p, root_path=root_path)
            if cls == "definition":
                def_paths.append(p)
                def_stages.append(stg)
        for cat in gap_cats:
            if cat != "pure_implementation":
                def_stages.append(defect_routing._GAP_CATEGORY_STAGE.get(cat, "4"))

        if def_stages:
            owning_stage = _earliest_stage(def_stages, default="4") or "4"
            return_stages.append(owning_stage)
            route_ref = (def_paths[0] if def_paths else None) or primary_binding_ref
            routed_diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(primary_tid or primary_flow_id or norm_slice),
                expected={"route_via_owning_stage": owning_stage, "return_stage": owning_stage},
                actual={"definition_paths": def_paths, "gap_categories": gap_cats, "owning_stage": owning_stage, "return_stage": owning_stage},
                resume_ref=route_ref,
            )
            all_diagnostics.append(routed_diag)
            governed_gap_routing.append(
                {
                    "owning_stage": owning_stage,
                    "return_stage": owning_stage,
                    "recommended_command": defect_routing._OWNING_STAGE_COMMANDS.get(owning_stage),
                    "affected_paths": def_paths,
                    "gap_categories": sorted(set(gap_cats)),
                    "resume_ref": route_ref,
                    "diagnostic": routed_diag,
                }
            )
            blocked_items.append(
                _make_item(
                    item_id=f"governed-gap:stage-{owning_stage}",
                    category="governed_gap",
                    status="blocked",
                    binding_ref=primary_binding_ref,
                    task_id=primary_tid,
                    flow_id=primary_flow_id,
                    evidence_ref=_declaring_evidence_ref(root_path, [route_ref, *default_declaring_candidates]),
                    summary=f"UI definition/contract/binding gap routed to owning stage {owning_stage}.",
                    details={"owning_stage": owning_stage, "affected_paths": def_paths, "gap_categories": gap_cats},
                )
            )

        # 4c (P-02): Validate & build read-only Story 3.1/3.2 business-view delta candidate ("operations", task_id=None).
        raw_task_gaps = list(gap_doc.get("missing_ui_tasks") or [])
        accepted_operations: list[dict[str, Any]] = []
        batch_seen_rows: list[dict[str, Any]] = []
        batch_seen_pairs: set[tuple[str, str]] = set(covered_flow_req_pairs)

        for idx_g, tg in enumerate(raw_task_gaps):
            if not isinstance(tg, dict):
                continue
            action_s = str(tg.get("action") or "create").strip().lower()
            if tg.get("allocate_permanent_id") is True or (action_s == "create" and tg.get("task_id") is not None):
                # Already recorded in early_tamper_blocked.
                continue
            view_s = str(tg.get("view") or "gameplay").strip()
            if view_s not in ("back", "gameplay"):
                return_stages.append("3C")
                v_diag = _diag(
                    codec.ReasonCode.INVALID_ENUM,
                    stage=codec.Stage.CONTENT,
                    entity_id=f"missing_ui_tasks[{idx_g}]",
                    expected=["back", "gameplay"],
                    actual={"view": view_s, "return_stage": "3C"},
                    resume_ref=gap_rel or primary_binding_ref,
                )
                all_diagnostics.append(v_diag)
                blocked_items.append(
                    _make_item(
                        item_id=f"blocked:invalid-delta-view:{idx_g + 1}",
                        category="governed_gap_protection",
                        status="blocked",
                        binding_ref=primary_binding_ref,
                        task_id=primary_tid,
                        flow_id=primary_flow_id,
                        evidence_ref=_declaring_evidence_ref(root_path, [gap_rel, *default_declaring_candidates]),
                        summary=f"Invalid business view '{view_s}' in missing_ui_tasks[{idx_g}]; must be 'back' or 'gameplay'.",
                        details={"view": view_s, "return_stage": "3C"},
                    )
                )
                continue

            title = str(tg.get("title") or "").strip()
            g_flows = {str(x).strip() for x in (tg.get("flow_ids") or ([primary_flow_id] if primary_flow_id else [])) if str(x).strip()}
            g_reqs = {str(x).strip() for x in (tg.get("requirement_ids") or []) if str(x).strip()}
            # Reject uncommitted requirement_ids as 3B gap so emitted operations always satisfy Story 3.1 preview!
            uncommitted_reqs = sorted(g_reqs - committed_plan_req_ids) if committed_plan_req_ids else []
            if uncommitted_reqs:
                return_stages.append("3B")
                u_diag = _diag(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.CONTENT,
                    entity_id=title or f"gap-{idx_g}",
                    expected="requirement_ids committed in 3B plan before proposing 3C create task delta",
                    actual={"uncommitted_requirement_ids": uncommitted_reqs, "return_stage": "3B"},
                    resume_ref=primary_plan_ref or primary_binding_ref,
                )
                all_diagnostics.append(u_diag)
                blocked_items.append(
                    _make_item(
                        item_id=f"blocked:uncommitted-req:{idx_g + 1}",
                        category="governed_gap",
                        status="blocked",
                        binding_ref=primary_binding_ref,
                        task_id=primary_tid,
                        flow_id=primary_flow_id,
                        evidence_ref=_declaring_evidence_ref(root_path, [primary_plan_ref, *default_declaring_candidates]),
                        summary=f"Proposed UI task '{title}' references uncommitted requirement(s) {uncommitted_reqs}; route to 3B first.",
                        details={"uncommitted_requirement_ids": uncommitted_reqs, "return_stage": "3B"},
                    )
                )
                continue

            dup = _is_synonymous_with_existing(
                title,
                g_flows,
                g_reqs,
                existing_tasks=[*all_existing_tasks, *batch_seen_rows],
                covered_flow_req_pairs=batch_seen_pairs,
            )
            if dup is not None:
                return_stages.append("3C")
                dup_diag = _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=title or f"gap-{idx_g}",
                    expected={"synonymous_duplicate_task": False, "return_stage": "3C"},
                    actual={"proposed_title": title, "duplicate_info": dup, "return_stage": "3C"},
                    resume_ref=primary_binding_ref,
                )
                all_diagnostics.append(dup_diag)
                blocked_items.append(
                    _make_item(
                        item_id=f"blocked:synonymous-task:{idx_g + 1}",
                        category="synonymous_duplicate_task",
                        status="blocked",
                        binding_ref=primary_binding_ref,
                        task_id=dup.get("existing_task_id") or primary_tid,
                        flow_id=primary_flow_id,
                        evidence_ref=_declaring_evidence_ref(root_path, default_declaring_candidates),
                        summary=f"Rejected synonymous duplicate UI task '{title}': {dup['reason']}",
                        details=dup,
                    )
                )
                continue

            op_entry = {
                "action": "create",
                "task_id": None,
                "view": view_s,
                "title": title,
                "summary": str(tg.get("summary") or title or "Uncovered target-slice UI gap"),
                "flow_ids": sorted(g_flows),
                "requirement_ids": sorted(g_reqs),
                "part_kinds": list(tg.get("part_kinds") or ["csharp_adapter", "binding", "scene"]),
                "roles": list(tg.get("roles") or ["consumer"]),
                "rationale": str(tg.get("rationale") or "Uncovered target-slice UI gap routed via Story 3.1/3.2."),
            }
            accepted_operations.append(op_entry)
            batch_seen_rows.append({"id": None, "title": title, "summary": op_entry["summary"]})
            for fid in g_flows:
                for rid in g_reqs:
                    batch_seen_pairs.add((fid, rid))

        if accepted_operations:
            proposed_governed_deltas = {
                "schema_version": DELTA_CANDIDATE_SCHEMA,
                "compatible_with": ["b-route-task-preview", "b-route-task-compile"],
                "task_triplet_written": False,
                "permanent_ids_allocated": False,
                "mature_done_status_preserved": True,
                "plan_ids": list(matched_plan_ids),
                "target_slice": norm_slice,
                "target_flow_id": primary_flow_id,
                "operations": accepted_operations,
            }

    overall_ok = len(blocked_items) == 0 and len(all_diagnostics) == 0
    earliest_rstage = _earliest_stage(return_stages)
    if overall_ok:
        reason_code = codec.ReasonCode.OK.value
        reason = (
            "target_slice_ui_reused_and_verified_with_manual_independent"
            if reused_ui_obligations and not pending_items
            else "target_slice_ui_evaluated_pending_items_remaining"
        )
    else:
        reason_code = str(all_diagnostics[0]["reason_code"]) if all_diagnostics else codec.ReasonCode.CONFLICT.value
        reason = "target_slice_chapter7_blocked"

    return _finish(
        {
            "ok": overall_ok,
            "route": "B",
            "legacy_a_passthrough": False,
            "target_slice": norm_slice,
            "target_flow_id": primary_flow_id,
            "target_task_ids": sorted_tids,
            "ui_applicability": "applicable",
            "reason_code": reason_code,
            "reason": reason,
            "return_stage": earliest_rstage,
            "declared_ui_obligations": declared_ui,
            "task_input_sets": {
                str(tid): {
                    "input_set_digest": ctx["input_set_digest"],
                    "gate_ok": bool(ctx["gate"].get("ok")),
                    "master_status": ctx["master_status"],
                    "binding_refs": [
                        r["path"] for r in ctx["binding_refs"] if isinstance(r, dict) and r.get("path")
                    ],
                }
                for tid, ctx in sorted(task_contexts.items())
            },
            "verified_items": verified_items,
            "pending_items": pending_items,
            "manual_items": manual_items,
            "blocked_items": blocked_items,
            "reused_ui_obligations": reused_ui_obligations,
            "rejected_evidence": rejected_evidence,
            "wiring_inspection": {
                "wiring_static_ok": wiring_report["wiring_static_ok"],
                "scenes_inspected": wiring_report["scenes_inspected"],
                "adapters_inspected": wiring_report["adapters_inspected"],
                "findings": wiring_report["findings"],
                "manual_region_counts": {
                    k: len(v) for k, v in sorted(wiring_report["manual_region_inventory"].items())
                },
            },
            "governed_gap_routing": governed_gap_routing,
            "proposed_governed_deltas": proposed_governed_deltas,
            "native_scene_manual_regions_preserved": manual_regions_preserved,
            "diagnostics": all_diagnostics,
        }
    )


def validate_report_path(root: Path | str, report_rel: str) -> tuple[Path, str]:
    """Validate that a report target is a new non-reparse logs/ci/.../*.json path without writing."""
    root_path = task_resolver._validate_root(Path(root))
    target, rel = ch5_b._validate_log_path(root_path, report_rel, require_logs=True)
    if os.path.lexists(target):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.PATH,
                rel,
                "new non-existent report path",
                {"path": rel, "exists": True},
                rel,
            )
        )
    _check_ancestors_no_reparse(root_path.resolve(), target)
    return target, rel


def write_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> str:
    """Exclusively create a report at a new non-reparse logs/ci/.../*.json path with report_path set before write."""
    root_path = task_resolver._validate_root(Path(root))
    target, rel = validate_report_path(root_path, report_rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    _check_ancestors_no_reparse(root_path.resolve(), target.parent)
    output_payload = deepcopy(payload)
    output_payload["report_path"] = rel
    raw = (json.dumps(output_payload, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        with target.open("xb") as fh:
            fh.write(raw)
    except FileExistsError as exc:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.PATH,
                rel,
                "new non-existent report path",
                {"path": rel, "exists": True},
                rel,
            )
        ) from exc
    return rel
