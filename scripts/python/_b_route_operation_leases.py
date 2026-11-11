"""Ordered operation leases over the existing nonblocking coordinator lock."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from typing import Iterator, TypeVar

from _mvg_capability_checkpoint import coordinator_lock


_RESULT = TypeVar("_RESULT")
_KEY = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}", re.ASCII)
_LOCK_NAME = "capability-coordinator.lock"


def _plain_path(value: str | os.PathLike[str]) -> Path:
    """Reject ambiguous Windows spellings before resolving an existing path."""
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("operation_lease_path_invalid")
    for part in path.parts[1:]:
        if (part.endswith((".", " ")) or ":" in part
                or PureWindowsPath(part).is_reserved()):
            raise ValueError("operation_lease_path_invalid")
    # Extended/device namespaces can bypass ordinary Win32 path semantics.
    if os.name == "nt" and str(path).startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("operation_lease_path_invalid")
    return path


def _no_reparse(path: Path) -> os.stat_result:
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
            or getattr(info, "st_reparse_tag", 0)):
        raise ValueError("operation_lease_reparse_path")
    return info


def _directory(value: str | os.PathLike[str]) -> Path:
    path = _plain_path(value)
    # Include ancestors above repo_root: resolving first would hide a junction.
    for current in reversed((path, *path.parents)):
        if not stat.S_ISDIR(_no_reparse(current).st_mode):
            raise ValueError("operation_lease_directory_required")
    return path.resolve(strict=True)


def _lock_file(directory: Path) -> None:
    path = directory / _LOCK_NAME
    try:
        info = _no_reparse(path)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("operation_lease_lock_path_invalid")


def _validated_directories(repo_root, metadata_dir, scope_dirs):
    if not isinstance(scope_dirs, Mapping) or not scope_dirs:
        raise ValueError("operation_lease_scopes_required")
    root = _directory(repo_root)
    metadata = _directory(metadata_dir)
    scopes = []
    keys = set()
    for key, directory in list(scope_dirs.items()):
        if not isinstance(key, str) or not _KEY.fullmatch(key) or key in keys:
            raise ValueError("operation_lease_scope_key_invalid")
        keys.add(key)
        scopes.append((key, _directory(directory)))
    directories = [metadata, *(directory for _, directory in scopes)]
    for index, directory in enumerate(directories):
        if not directory.is_relative_to(root):
            raise ValueError("operation_lease_path_outside_repo")
        if any(directory.samefile(prior) for prior in directories[:index]):
            raise ValueError("operation_lease_directory_alias")
        _lock_file(directory)
    return metadata, sorted(scopes)


@contextmanager
def operation_leases(
    repo_root: str | os.PathLike[str],
    metadata_dir: str | os.PathLike[str],
    scope_dirs: Mapping[str, str | os.PathLike[str]],
    *,
    prepare_under_lease: Callable[[], _RESULT],
) -> Iterator[_RESULT]:
    """Prepare under metadata plus all scopes; yield while retaining scopes.

    The caller supplies the complete scope set and owns all business writes.
    Directories must already exist and remain stable throughout this context.
    Contention keeps coordinator_lock's ValueError("capability_coordinator_busy").
    """
    if not callable(prepare_under_lease):
        raise TypeError("operation_lease_prepare_callback_required")
    metadata, scopes = _validated_directories(repo_root, metadata_dir, scope_dirs)
    with ExitStack() as held_scopes:
        with coordinator_lock(metadata):
            for _, directory in scopes:
                held_scopes.enter_context(coordinator_lock(directory))
            prepared = prepare_under_lease()
        yield prepared
