#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


CARD_ID_PATTERN = re.compile(r'"(card\.warrior\.[a-z0-9_]+)"')
RELIC_KEY_PATTERN = re.compile(r'"(relic\.name\.[a-z0-9_]+)"')
EVENT_CONST_KEY_PATTERN = re.compile(r'private const string \w*Key = "(event\.[a-z0-9_.]+)"')
EVENT_OPTION_KEY_PATTERN = re.compile(r'new EventOption\("[^"]+",\s*"(event\.[a-z0-9_.]+)"')
UI_KEY_IN_TSCN_PATTERN = re.compile(
    r'(?:text|title|dialog_text|ok_button_text|cancel_button_text)\s*=\s*"((?:ui|event)\.[a-z0-9_.]+)"'
)
UI_KEY_IN_RESOLVE_CALL_PATTERN = re.compile(r'ResolveVisibleText\("((?:ui|event)\.[a-z0-9_.]+)"\)')
UI_KEY_IN_RESOLVE_TEXT_CALL_PATTERN = re.compile(r'ResolveText\("((?:ui|event)\.[a-z0-9_.]+)"\)')
UI_KEY_LITERAL_PATTERN = re.compile(r'"(ui\.[a-z0-9_.]+)"')

M1_UI_SCENE_SOURCES = (
    "Game.Godot/Scenes/UI/MainMenu.tscn",
    "Game.Godot/Scenes/UI/CharacterSelect.tscn",
    "Game.Godot/Scenes/UI/DifficultySelect.tscn",
)

M1_UI_SCRIPT_SOURCES = (
    "Game.Godot/Scripts/UI/MainMenu.cs",
    "Game.Godot/Scripts/UI/CharacterSelect.cs",
    "Game.Godot/Scripts/UI/DifficultySelect.cs",
    "Game.Godot/Scripts/UI/EventScene.cs",
)

M1_UI_KEY_PREFIXES = (
    "ui.menu.",
    "ui.character.",
    "ui.difficulty.",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_csv_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    result: dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        value = str(row[1]).strip()
        if key:
            result[key] = value
    return result


def _read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _to_rel_posix(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _is_m1_ui_key(key: str) -> bool:
    return any(key.startswith(prefix) for prefix in M1_UI_KEY_PREFIXES)


def extract_required_keys(root: Path) -> tuple[list[str], list[str], list[str]]:
    required: set[str] = set()
    scanned_files: list[str] = []
    extraction_patterns: list[str] = []

    def add_required(key: str) -> None:
        if key:
            required.add(key)

    def mark_scanned(path: Path) -> str:
        rel = _to_rel_posix(root, path)
        if rel not in scanned_files:
            scanned_files.append(rel)
        return rel

    warrior_service = root / "Game.Core" / "Services" / "WarriorStartingDeckService.cs"
    warrior_text = _read_text_if_exists(warrior_service)
    if warrior_text:
        mark_scanned(warrior_service)
        extraction_patterns.append("card_id_pattern")
    for card_id in CARD_ID_PATTERN.findall(warrior_text):
        add_required(f"{card_id}.name")

    relic_service = root / "Game.Core" / "Services" / "StartingRelicService.cs"
    relic_text = _read_text_if_exists(relic_service)
    if relic_text:
        mark_scanned(relic_service)
        extraction_patterns.append("relic_key_pattern")
    for relic_key in RELIC_KEY_PATTERN.findall(relic_text):
        add_required(relic_key)

    event_scene = root / "Game.Godot" / "Scripts" / "UI" / "EventScene.cs"
    event_text = _read_text_if_exists(event_scene)
    if event_text:
        mark_scanned(event_scene)
        extraction_patterns.extend(
            [
                "event_const_key_pattern",
                "event_option_key_pattern",
                "ui_key_in_resolve_text_call_pattern",
            ]
        )
    for key in EVENT_CONST_KEY_PATTERN.findall(event_text):
        add_required(key)
    for key in EVENT_OPTION_KEY_PATTERN.findall(event_text):
        add_required(key)
    for key in UI_KEY_IN_RESOLVE_TEXT_CALL_PATTERN.findall(event_text):
        if key.startswith("event.") or _is_m1_ui_key(key):
            add_required(key)

    for rel_path in M1_UI_SCENE_SOURCES:
        scene_path = root / rel_path
        scene_text = _read_text_if_exists(scene_path)
        if not scene_text:
            continue
        mark_scanned(scene_path)
        extraction_patterns.append("ui_key_in_tscn_pattern")
        for key in UI_KEY_IN_TSCN_PATTERN.findall(scene_text):
            if key.startswith("event.") or _is_m1_ui_key(key):
                add_required(key)

    for rel_path in M1_UI_SCRIPT_SOURCES:
        script_path = root / rel_path
        script_text = _read_text_if_exists(script_path)
        if not script_text:
            continue
        mark_scanned(script_path)
        extraction_patterns.extend(
            [
                "ui_key_in_resolve_call_pattern",
                "ui_key_in_resolve_text_call_pattern",
                "ui_key_literal_pattern",
            ]
        )
        for key in UI_KEY_IN_RESOLVE_CALL_PATTERN.findall(script_text):
            if _is_m1_ui_key(key) or key.startswith("event."):
                add_required(key)
        for key in UI_KEY_IN_RESOLVE_TEXT_CALL_PATTERN.findall(script_text):
            if _is_m1_ui_key(key) or key.startswith("event."):
                add_required(key)
        for key in UI_KEY_LITERAL_PATTERN.findall(script_text):
            if _is_m1_ui_key(key):
                add_required(key)

    extraction_patterns = sorted(set(extraction_patterns))
    scanned_files = sorted(set(scanned_files))
    return sorted(required), scanned_files, extraction_patterns


def collect_missing(required_keys: list[str], en_map: dict[str, str], zh_map: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for key in required_keys:
        en_value = en_map.get(key)
        if en_value is None:
            missing.append(f"en::{key}")
        elif not is_translation_value_valid(key, en_value, "en"):
            missing.append(f"en::{key}::invalid_value")

        zh_value = zh_map.get(key)
        if zh_value is None:
            missing.append(f"zh-CN::{key}")
        elif not is_translation_value_valid(key, zh_value, "zh-CN"):
            missing.append(f"zh-CN::{key}::invalid_value")
    return missing


def is_translation_value_valid(key: str, value: str, locale: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text == key:
        return False
    if all(ch in {"?", "？"} for ch in text):
        return False
    if "�" in text:
        return False
    if locale.lower() == "zh-cn" and "(zh)" in text.lower():
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify Task 39 M1 translation keys in en/zh-CN resources.")
    ap.add_argument("--task-id", default="39")
    ap.add_argument("--output", default="logs/ci/manual/task-39-translation-check.json")
    args = ap.parse_args()

    root = repo_root()
    en_path = root / "Game.Godot" / "Translations" / "en.csv"
    zh_path = root / "Game.Godot" / "Translations" / "zh-CN.csv"

    en_map = load_csv_map(en_path)
    zh_map = load_csv_map(zh_path)
    required_keys, scanned_files, extraction_patterns = extract_required_keys(root)
    missing = collect_missing(required_keys, en_map, zh_map)

    payload = {
        "schema_version": "1.0.0",
        "task_id": str(args.task_id),
        "status": "ok" if not missing else "fail",
        "en_path": str(en_path.relative_to(root)).replace("\\", "/"),
        "zh_path": str(zh_path.relative_to(root)).replace("\\", "/"),
        "required_keys": required_keys,
        "missing_keys": missing,
        "scanned_files": scanned_files,
        "extraction_patterns": extraction_patterns,
    }

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "TASK39_TRANSLATION_VERIFY "
        f"status={payload['status']} "
        f"required={len(required_keys)} "
        f"missing={len(missing)} "
        f"scanned={len(scanned_files)} "
        f"out={output_path}"
    )
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
