"""MVG-owned output paths; rejection receipts never trust a rejected run path."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import stat
import uuid

from _planning_skill_common import atomic_json

RUN_ROOT = "logs/ci/mvg-planning"
TRACE_ROOT = "docs/testing/mvg/planning"
_RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", re.I)


def _relative(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or value.startswith("/") or PureWindowsPath(value).is_absolute()
            or any(part in {"", ".", ".."} or part.endswith((".", " "))
                   or _RESERVED.fullmatch(part) for part in value.split("/"))
            or any(ord(char) < 32 or char in '<>"|?*' for char in value)):
        raise ValueError("noncanonical_repository_path")
    return value


def _checked(root: Path, reference: str) -> Path:
    reference = _relative(reference)
    root = root.resolve()
    target = root / reference
    current = root
    for part in reference.split("/"):
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("linked_output_path")
        if current.exists() and current.is_file() and current != target:
            raise ValueError("output_ancestor_is_file")
    if not target.resolve().is_relative_to(root):
        raise ValueError("output_escapes_repository")
    if target.is_file() and target.stat().st_nlink > 1:
        raise ValueError("aliased_output_file")
    if target.is_dir():
        raise ValueError("output_is_directory")
    temporary = target.with_name(target.name + ".tmp")
    if (temporary.is_symlink() or (hasattr(temporary, "is_junction") and temporary.is_junction())
            or temporary.is_dir() or (temporary.is_file() and temporary.stat().st_nlink > 1)):
        raise ValueError("aliased_atomic_temporary")
    return target


def reject(root: Path, reason: str, **details) -> None:
    """Fail closed even when the diagnostic directory itself is unsafe."""
    try:
        receipt = _checked(root, "logs/ci/mvg-planning-rejections/" + uuid.uuid4().hex + ".json")
    except (OSError, ValueError):
        raise ValueError("planning_write_boundary:" + reason + "; diagnostic_unavailable_unsafe_logs") from None
    atomic_json(receipt, {"status": "rejected", "reason": reason, **details})
    raise ValueError("planning_write_boundary:" + reason + "; receipt=" + receipt.relative_to(root.resolve()).as_posix())


def safe_reference(root: Path, reference: str) -> Path:
    try:
        return _checked(root, reference)
    except (OSError, ValueError) as exc:
        reject(root, str(exc), target=str(reference))


def run_directory_path(root: Path, run_id: str) -> Path:
    """Check the run identifier and ancestors without enumerating artifacts."""
    try:
        if (not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id)
                or run_id.endswith(".") or _RESERVED.fullmatch(run_id)):
            raise ValueError("invalid_run_id")
        # _checked accepts files, so use a child to check directory ancestors.
        return _checked(root, RUN_ROOT + "/" + run_id + "/run.json").parent
    except (OSError, ValueError) as exc:
        reject(root, str(exc), run_id=str(run_id))


def _scan_run_artifacts(path: Path) -> None:
    pending = [path] if path.exists() else []
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for child in entries:
                    # Windows directory enumeration already supplies reparse
                    # attributes; avoid reopening every immutable evidence file.
                    try:
                        metadata = child.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        # An atomic writer can replace/remove its temporary
                        # entry between enumeration and stat. Nothing remains
                        # here to follow or to authorize as output.
                        continue
                    attributes = getattr(metadata, "st_file_attributes", 0)
                    if child.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                        raise ValueError("linked_run_artifact")
                    if child.is_dir(follow_symlinks=False):
                        pending.append(child.path)
                    else:
                        links = metadata.st_nlink
                        if links == 0:
                            # Windows DirEntry metadata may omit link counts.
                            # Query the file only when enumeration is incomplete.
                            try:
                                links = os.stat(child.path, follow_symlinks=False).st_nlink
                            except FileNotFoundError:
                                continue
                        if links != 1:
                            raise ValueError("aliased_run_artifact")
        except FileNotFoundError:
            # A directory queued during enumeration may also disappear.
            continue


def safe_run_dir(root: Path, run_id: str) -> Path:
    path = run_directory_path(root, run_id)
    try:
        _scan_run_artifacts(path)
        return path
    except (OSError, ValueError) as exc:
        reject(root, str(exc), run_id=str(run_id))


def planning_targets(root: Path, run_id: str, manifest_ref: str) -> tuple[Path, Path]:
    run_directory_path(root, run_id)
    try:
        _relative(manifest_ref)
        if not re.fullmatch(r"docs/testing/mvg/[A-Za-z0-9][A-Za-z0-9_.-]*\.json", manifest_ref):
            raise ValueError("manifest_outside_planning_projection")
        manifest = _checked(root, manifest_ref)
        trace = _checked(root, TRACE_ROOT + "/" + run_id + ".json")
        if manifest.resolve() == trace.resolve() or (manifest.exists() and trace.exists() and manifest.samefile(trace)):
            raise ValueError("manifest_trace_collision")
        return manifest, trace
    except (OSError, ValueError) as exc:
        reject(root, str(exc), run_id=run_id, target=str(manifest_ref))


def validate_journal_targets(root: Path, run_id: str, manifest_ref: str, journal: dict) -> None:
    manifest, trace = planning_targets(root, run_id, manifest_ref)
    expected = {path.relative_to(root.resolve()).as_posix() for path in (manifest, trace)}
    if not isinstance(journal, dict):
        reject(root, "journal_target_not_owned", run_id=run_id)
    entries = journal.get("entries")
    if (not isinstance(entries, list) or len(entries) != 2
            or any(not isinstance(row, dict) or not isinstance(row.get("path"), str) for row in entries)
            or {row["path"] for row in entries} != expected):
        reject(root, "journal_target_not_owned", run_id=run_id)
    # Check every target before the generic journal can invoke any writer.
    for row in entries:
        safe_reference(root, row["path"])


def handoff_target(root: Path, run_id: str, out_path: Path) -> Path:
    run_dir = run_directory_path(root, run_id)
    try:
        path = Path(out_path)
        reference = path.relative_to(root.resolve()).as_posix() if path.is_absolute() else path.as_posix()
        _relative(reference)
        parent = run_dir.relative_to(root.resolve()).as_posix() + "/handoffs/"
        if not reference.startswith(parent) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", reference[len(parent):]):
            raise ValueError("handoff_outside_run_evidence")
        return _checked(root, reference)
    except (OSError, ValueError) as exc:
        reject(root, str(exc), run_id=run_id, target=str(out_path))
