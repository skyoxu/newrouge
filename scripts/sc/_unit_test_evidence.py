"""Archive only unit artifacts explicitly emitted by the current dotnet attempt."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from _util import write_text


def _normalized_artifact_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def reserve_unit_output_dir(parent: Path) -> Path:
    directory = parent / ('sc-test-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    return directory


def _emitted_path(summary: dict[str, Any], selected_key: str, detected_key: str) -> Path | None:
    selected = summary.get('artifacts_selected')
    detected = summary.get('artifacts_detected')
    if not isinstance(selected, dict) or not isinstance(detected, dict):
        return None
    raw = selected.get(selected_key)
    paths = detected.get(detected_key)
    if not isinstance(raw, str) or not raw or not isinstance(paths, list):
        return None
    if _normalized_artifact_path(raw) not in {
        _normalized_artifact_path(value) for value in paths if isinstance(value, str) and value
    }:
        return None
    return Path(raw)


def emitted_trx_path(summary: dict[str, Any]) -> Path | None:
    path = _emitted_path(summary, 'trx', 'trx_paths')
    return path if path is not None and path.suffix.lower() == '.trx' else None


def emitted_coverage_path(summary: dict[str, Any]) -> Path | None:
    if summary.get('restore_rc') != 0 or 'test_rc' not in summary:
        return None
    path = _emitted_path(summary, 'coverage', 'coverage_paths')
    return path if path is not None and path.name.lower() == 'coverage.cobertura.xml' else None


def save_unit_artifacts(*, source_dir: Path, out_dir: Path, run_id: str) -> Path:
    saved = out_dir / 'unit-artifacts' / uuid.uuid4().hex
    saved.mkdir(parents=True)
    summary: dict[str, Any] = {}
    try:
        value = json.loads((source_dir / 'summary.json').read_text(encoding='utf-8-sig'))
        summary = value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError):
        pass
    for name in ['summary.json', 'dotnet-restore.log', 'dotnet-test-output.txt']:
        source = source_dir / name
        if source.is_file():
            shutil.copy2(source, saved / name)
    current_trx = emitted_trx_path(summary)
    if summary.get('restore_rc') == 0 and 'test_rc' in summary and current_trx is not None and current_trx.is_file():
        shutil.copy2(current_trx, saved / 'tests.trx')
    current_coverage = emitted_coverage_path(summary)
    if current_coverage is not None and current_coverage.is_file():
        shutil.copy2(current_coverage, saved / 'coverage.cobertura.xml')
    write_text(saved / 'run_id.txt', run_id + '\n')
    return saved
