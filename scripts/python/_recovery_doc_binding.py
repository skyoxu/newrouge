"""Select recovery documents by their declared task/run links, never directory age."""
from __future__ import annotations

from pathlib import Path

from validate_recovery_docs import extract_repo_paths, is_readme, is_template, parse_fields


def _tokens(value: str) -> list[str]:
    text = str(value or '').strip()
    if not text or text.lower().startswith(('n/a', 'none')):
        return []
    return [token.strip().strip('`').strip() for token in text.split(',') if token.strip().strip('`').strip()]


def _normalized_path(value: str) -> str:
    text = str(value or '').strip().replace('\\', '/')
    while text.startswith('./'):
        text = text[2:]
    return text


def _match_score(fields: dict[str, str], *, task_id: str, run_id: str, latest_rel: str) -> int:
    tasks = _tokens(fields.get('Related task id(s)', ''))
    runs = _tokens(fields.get('Related run id', ''))
    task_match = bool(task_id and task_id in tasks)
    run_match = bool(run_id and run_id in runs)
    # A copied run/pointer link cannot override an explicit different task.
    if task_id and tasks and not task_match:
        return 0
    if run_id and runs and not run_match and not task_match:
        return 0
    pointers = [_normalized_path(item) for item in extract_repo_paths(fields.get('Related latest.json', ''))]
    pointer_match = bool(latest_rel and _normalized_path(latest_rel) in pointers)
    return 100 * task_match + 10 * run_match + int(pointer_match)


def find_related_docs(root: Path, dir_name: str, *, task_id: str, run_id: str, latest_rel: str) -> list[str]:
    """Rank exact task/run bindings first; retain task history as related evidence.

    Equal bindings use the versioned filename for reproducible ordering across
    checkouts. Filesystem modification times carry no recovery authority.
    """
    matches: list[tuple[int, str]] = []
    for path in (root / dir_name).glob('*.md'):
        if is_readme(path) or is_template(path):
            continue
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
            fields = parse_fields(path)
        except (OSError, UnicodeError, ValueError):
            continue
        score = _match_score(fields, task_id=task_id, run_id=run_id, latest_rel=latest_rel)
        if score:
            matches.append((score, relative))
    return [relative for _score, relative in sorted(matches, reverse=True)]
