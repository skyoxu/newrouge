from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from _knowledge_catalog_builder import _eligible_source, _excluded, normalize_path

CONTROL_PLANE_INPUT_FILES = {
    "scripts/python/_knowledge_catalog_builder.py",
    "scripts/python/_knowledge_locator_core.py",
    "scripts/python/publish_knowledge_catalog.py",
}
CONTROL_PLANE_INPUT_PREFIXES = (
    "knowledge/policies/",
    "knowledge/evaluation/",
)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _publication_relevant(path: str, exclusions: dict[str, Any]) -> bool:
    normalized = normalize_path(path)
    if normalized in CONTROL_PLANE_INPUT_FILES:
        return True
    if normalized.startswith(CONTROL_PLANE_INPUT_PREFIXES):
        return True
    return _eligible_source(normalized) and not _excluded(normalized, exclusions)


def publication_freshness_reason(
    root: Path,
    published_commit: str,
    authority_ref: str,
    exclusions: dict[str, Any],
) -> str | None:
    """Return why a publication is stale, or None when current authority inputs are equivalent.

    A publication may remain valid after main advances when every change since the published
    commit is outside the Knowledge Control Plane inputs. This deliberately ignores generated
    publication outputs under knowledge/catalogs, knowledge/indexes, knowledge/projections, and
    knowledge/snapshots so committing those outputs does not invalidate the publication that
    produced them.
    """
    if not published_commit or not authority_ref:
        return "authority_binding_invalid"

    current = _git(root, "rev-parse", "--verify", authority_ref)
    if current.returncode:
        return "authority_ref_unavailable"

    published = _git(root, "cat-file", "-e", f"{published_commit}^{{commit}}")
    if published.returncode:
        return "published_commit_unavailable"

    ancestor = _git(root, "merge-base", "--is-ancestor", published_commit, current.stdout.strip())
    if ancestor.returncode != 0:
        return "authority_ref_diverged"

    changed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            published_commit,
            current.stdout.strip(),
        ],
        capture_output=True,
        check=False,
    )
    if changed.returncode:
        return "authority_diff_failed"

    for raw in changed.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            path = raw.decode("utf-8")
        except UnicodeDecodeError:
            return "authority_path_encoding_invalid"
        try:
            if _publication_relevant(path, exclusions):
                return "authority_inputs_changed"
        except ValueError:
            return "authority_path_invalid"
    return None
