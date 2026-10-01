#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CHAPTER7_PROFILE_OVERRIDE_PATH = Path("docs/workflows/chapter7-profile.json")
DEFAULT_BUCKET_ORDER = ["unclassified"]
PROFILE_REPLACE_SECTIONS = {
    "bucket_order",
    "fallback_bucket",
    "surface_aliases",
    "task_scope",
    "buckets",
}

DEFAULT_CHAPTER7_PROFILE: dict[str, Any] = {
    "bucket_order": DEFAULT_BUCKET_ORDER,
    "fallback_bucket": "unclassified",
    "surface_aliases": {},
    "task_creation": {
        "priority_by_bucket": {"default": "medium"},
        "layer_by_bucket": {"default": "adapter"},
        "view_priority_map": {"high": "P1", "medium": "P2", "low": "P3"},
        "adr_refs": [],
        "chapter_refs": [],
        "base_labels": ["taskmaster-view", "chapter7-ui"],
        "owners": {"NG": "architecture", "GM": "gameplay"},
        "source_labels": {"NG": "backlog", "GM": "prd"},
        "view_id_templates": {
            "NG": "NG-{task_id:04d}",
            "GM": "GM-{task_id_plus_100:04d}",
        },
        "default_story_templates": {
            "back": "BACKLOG-{repo_label_upper_underscore}-M1",
            "gameplay": "PRD-{repo_label_upper_underscore}-v1.2",
        },
    },
    "buckets": {
        "unclassified": {
            "feature_task_ids": [],
            "feature_families": [],
            "slice_title": "Unclassified",
            "screen_group": "Unclassified Chapter 7 Surface",
            "audience": "player-facing",
            "ui_entry": "Unclassified UI surface",
            "player_action": "Use the configured product flow",
            "system_response": "Show the configured governed runtime state",
            "suggested_surfaces": [],
            "section_headings": [],
            "scene_rel_path": "",
            "closure_task_ids": [],
            "wiring_task_id": 0,
            "semantics_defaults": {
                "failure": "Unclassified behavior requires project configuration before closure.",
                "empty": "No project-specific Chapter 7 mapping is configured.",
                "completion": "Project-specific Chapter 7 mapping is configured and validated.",
            },
            "screen_contract": {
                "must_show": "Only project-configured behavior.",
                "must_not_hide": "Missing Chapter 7 mapping.",
                "validation_focus": "Project profile completeness and mapping validity.",
            },
            "screen_state": {
                "entry_state": "Unclassified until project mapping is configured.",
                "interaction_state": "No project-specific interaction is assumed.",
                "failure_state": "Report the missing mapping instead of assigning a business bucket.",
                "recovery_exit": "Configure an explicit project bucket or fallback.",
            },
        }
    },
}
def build_default_chapter7_profile() -> dict[str, Any]:
    return deepcopy(DEFAULT_CHAPTER7_PROFILE)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Chapter 7 profile must be a JSON object: {path}")
    return payload


def _merge_profile(
    base: dict[str, Any],
    overlay: dict[str, Any],
    *,
    inherit_sections: set[str],
) -> dict[str, Any]:
    for key, value in overlay.items():
        if key == "_inherit_sections":
            continue
        if key in PROFILE_REPLACE_SECTIONS and key not in inherit_sections:
            base[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_profile(base[key], value, inherit_sections=inherit_sections)
        else:
            base[key] = deepcopy(value)
    return base


def _validate_effective_profile(profile: dict[str, Any]) -> None:
    raw_order = profile["bucket_order"] if "bucket_order" in profile else DEFAULT_BUCKET_ORDER
    if not isinstance(raw_order, list):
        raise ValueError("Chapter 7 bucket_order must be a list")
    names = [str(item).strip() for item in raw_order if str(item).strip()]
    if len(names) != len(set(names)):
        raise ValueError("Chapter 7 bucket_order contains duplicate buckets")
    buckets = profile.get("buckets", {})
    if not isinstance(buckets, dict):
        raise ValueError("Chapter 7 buckets must be an object")
    missing = [name for name in names if name not in buckets]
    if missing:
        raise ValueError(f"Chapter 7 bucket_order references missing buckets: {missing}")
    fallback = str(profile.get("fallback_bucket") or "").strip()
    if fallback and fallback not in buckets:
        raise ValueError(f"Chapter 7 fallback_bucket is not configured: {fallback}")
    task_owner: dict[int, str] = {}
    for bucket in names:
        config = buckets.get(bucket, {})
        if not isinstance(config, dict):
            raise ValueError(f"Chapter 7 bucket must be an object: {bucket}")
        for raw_id in config.get("feature_task_ids", []):
            if type(raw_id) is not int:
                raise ValueError(f"Chapter 7 feature_task_ids must be integers: {bucket}")
            previous = task_owner.get(raw_id)
            if previous is not None:
                raise ValueError(
                    f"Chapter 7 task {raw_id} is assigned to multiple buckets: {previous}, {bucket}"
                )
            task_owner[raw_id] = bucket

    templates = (
        profile.get("task_creation", {}).get("view_id_templates", {})
        if isinstance(profile.get("task_creation"), dict)
        else {}
    )
    if not isinstance(templates, dict):
        raise ValueError("Chapter 7 view_id_templates must be an object")
    for prefix, raw_template in templates.items():
        template = str(raw_template)
        rendered: dict[str, int] = {}
        for task_id in sorted(task_owner):
            try:
                value = template.format(
                    prefix=str(prefix),
                    task_id=task_id,
                    task_id_plus_100=task_id + 100,
                    task_id_plus_1000=task_id + 1000,
                )
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    f"Invalid Chapter 7 view id template for {prefix}: {template}"
                ) from exc
            previous = rendered.get(value)
            if previous is not None and previous != task_id:
                raise ValueError(
                    f"Chapter 7 view id template collision for {prefix}: "
                    f"tasks {previous} and {task_id} both render {value}"
                )
            rendered[value] = task_id


def configured_feature_task_ids(profile: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for bucket in bucket_names(profile):
        config = bucket_profile(profile, bucket)
        result.update(
            int(value)
            for value in config.get("feature_task_ids", [])
            if type(value) is int
        )
    return result


def _resolve_profile_path(repo_root: Path, value: Path | None) -> Path | None:
    if value is not None:
        path = value if value.is_absolute() else (repo_root / value)
        if not path.exists():
            raise FileNotFoundError(f"missing Chapter 7 profile: {path}")
        return path
    default_path = repo_root / DEFAULT_CHAPTER7_PROFILE_OVERRIDE_PATH
    return default_path if default_path.exists() else None


def load_chapter7_profile(*, repo_root: Path, profile_path: Path | None = None) -> dict[str, Any]:
    profile = build_default_chapter7_profile()
    sources = ["built-in-generic"]
    resolved_path = _resolve_profile_path(repo_root, profile_path)
    if resolved_path is not None:
        overlay = _read_json(resolved_path)
        raw_inherit = overlay.get("_inherit_sections", [])
        if not isinstance(raw_inherit, list):
            raise ValueError("Chapter 7 _inherit_sections must be a list")
        inherit_sections = {str(item).strip() for item in raw_inherit if str(item).strip()}
        unknown = sorted(inherit_sections - PROFILE_REPLACE_SECTIONS)
        if unknown:
            raise ValueError(f"Unknown Chapter 7 inherited sections: {unknown}")
        profile = _merge_profile(profile, overlay, inherit_sections=inherit_sections)
        loaded = str(resolved_path.resolve()).replace("\\", "/")
        profile["_loaded_profile_path"] = loaded
        sources.append(loaded)
    else:
        profile["_loaded_profile_path"] = ""
    profile["_profile_sources"] = sources
    _validate_effective_profile(profile)
    return profile


def bucket_names(profile: dict[str, Any]) -> list[str]:
    names = profile["bucket_order"] if "bucket_order" in profile else DEFAULT_BUCKET_ORDER
    if not isinstance(names, list):
        raise ValueError("Chapter 7 bucket_order must be a list")
    return [str(item) for item in names if str(item).strip()]


def bucket_profile(profile: dict[str, Any], bucket: str) -> dict[str, Any]:
    return dict(profile.get("buckets", {}).get(bucket, {}))


def feature_bucket(profile: dict[str, Any], feature: dict[str, Any]) -> str:
    task_id = int(feature["task_id"])
    feature_family = str(feature.get("feature_family") or "").strip()
    for bucket in bucket_names(profile):
        config = bucket_profile(profile, bucket)
        task_ids = {int(item) for item in config.get("feature_task_ids", [])}
        families = {str(item).strip() for item in config.get("feature_families", []) if str(item).strip()}
        if task_id in task_ids or (feature_family and feature_family in families):
            return bucket
    fallback = str(profile.get("fallback_bucket") or "").strip()
    return fallback


def surface_aliases(profile: dict[str, Any], surface: str) -> list[str]:
    aliases = profile.get("surface_aliases", {}).get(surface) or [surface]
    out: list[str] = []
    seen: set[str] = set()
    for item in [surface, *aliases]:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out or [surface]


def task_creation_config(profile: dict[str, Any]) -> dict[str, Any]:
    return dict(profile.get("task_creation", {}))


def task_scope(profile: dict[str, Any]) -> dict[str, int | None]:
    raw = profile.get("task_scope", {})
    if not isinstance(raw, dict):
        return {"min_task_id": None, "max_task_id": None}
    min_task_id = raw.get("min_task_id")
    max_task_id = raw.get("max_task_id")
    return {
        "min_task_id": int(min_task_id) if isinstance(min_task_id, int) else None,
        "max_task_id": int(max_task_id) if isinstance(max_task_id, int) else None,
    }


def task_id_in_scope(profile: dict[str, Any], task_id: int) -> bool:
    scope = task_scope(profile)
    min_task_id = scope.get("min_task_id")
    max_task_id = scope.get("max_task_id")
    if min_task_id is not None and task_id < min_task_id:
        return False
    if max_task_id is not None and task_id > max_task_id:
        return False
    return True


def priority_for_bucket(profile: dict[str, Any], bucket: str) -> str:
    config = task_creation_config(profile).get("priority_by_bucket", {})
    return str(config.get(bucket) or config.get("default") or "medium")


def layer_for_bucket(profile: dict[str, Any], bucket: str) -> str:
    config = task_creation_config(profile).get("layer_by_bucket", {})
    return str(config.get(bucket) or config.get("default") or "adapter")


def view_priority_for_bucket(profile: dict[str, Any], bucket: str) -> str:
    master_priority = priority_for_bucket(profile, bucket)
    mapping = task_creation_config(profile).get("view_priority_map", {})
    return str(mapping.get(master_priority) or "P2")


def _repo_label_tokens(repo_label: str) -> dict[str, str]:
    normalized = (repo_label or "").strip() or "taskmaster"
    repo_label_kebab = normalized.replace("_", "-")
    repo_label_upper_underscore = repo_label_kebab.upper().replace("-", "_").replace(".", "_")
    return {
        "repo_label": normalized,
        "repo_label_kebab": repo_label_kebab,
        "repo_label_upper_underscore": repo_label_upper_underscore,
    }


def format_story_id(template: str, repo_label: str) -> str:
    return str(template).format(**_repo_label_tokens(repo_label))


def default_story_ids(profile: dict[str, Any], repo_label: str) -> tuple[str, str]:
    templates = task_creation_config(profile).get("default_story_templates", {})
    back_template = str(templates.get("back") or "BACKLOG-{repo_label_upper_underscore}-M1")
    gameplay_template = str(templates.get("gameplay") or "PRD-{repo_label_upper_underscore}-v1.2")
    return format_story_id(back_template, repo_label), format_story_id(gameplay_template, repo_label)


def owner_for_prefix(profile: dict[str, Any], prefix: str) -> str:
    owners = task_creation_config(profile).get("owners", {})
    return str(owners.get(prefix) or "gameplay")


def source_label_for_prefix(profile: dict[str, Any], prefix: str) -> str:
    labels = task_creation_config(profile).get("source_labels", {})
    return str(labels.get(prefix) or prefix.lower())


def view_id_for_prefix(profile: dict[str, Any], prefix: str, task_id: int) -> str:
    templates = task_creation_config(profile).get("view_id_templates", {})
    template = str(templates.get(prefix) or f"{prefix}-{{task_id:04d}}")
    return template.format(
        prefix=prefix,
        task_id=task_id,
        task_id_plus_100=task_id + 100,
        task_id_plus_1000=task_id + 1000,
    )
