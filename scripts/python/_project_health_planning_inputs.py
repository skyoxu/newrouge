"""Local-workspace Git checkouts and validated Chapter 3/5 planning evidence."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from _planning_skill_common import file_sha, load_json, repo_path

SOURCE_ROOT = 'logs/ci/task-generation'
TOPOLOGY_ROOT = 'docs/planning/semantic-topology'
LOCAL_DERIVED_TOPOLOGY = (
    'capabilities.v1.json', 'capability-review.v1.json',
    'capability-selection.v1.json', 'topology-edges.v1.json',
    'topology-manifest.v1.json',
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Git operation failed')
    return result.stdout.strip()


def main_revision(root: Path) -> str:
    try:
        revision = git(root, 'rev-parse', '--verify', 'refs/heads/main^{commit}')
    except ValueError as exc:
        raise ValueError('A local committed main branch is required; directory and scan snapshots are unsupported') from exc
    if not re.fullmatch(r'[0-9a-f]{40,64}', revision):
        raise ValueError('Invalid main commit identity')
    return revision


def workspace_revision(root: Path) -> str:
    """Return the current local checkout identity without requiring a main ref.

    The commit is retained as provenance for the temporary planning checkout,
    but planning result freshness is checked against authoritative input hashes,
    not against this value.
    """
    try:
        revision = git(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    except ValueError as exc:
        raise ValueError('A local committed checkout is required for planning') from exc
    if not re.fullmatch(r'[0-9a-f]{40,64}', revision):
        raise ValueError('Invalid local checkout identity')
    return revision


def require_main(root: Path, revision: str) -> None:
    if main_revision(root) != revision:
        raise ValueError('Main changed during planning; regenerate against the latest main commit')


def hydrate_evidence(source: Path, checkout: Path) -> None:
    """Evidence is a gate, never a replacement for committed design/task inputs."""
    # repo_path resolves directories, including Windows short-name aliases.
    source = source.resolve()
    # These projections are intentionally ignored by Git. Carry the current
    # device's local result into the isolated checkout when it exists; a clean
    # device simply proceeds without a derived baseline.
    for name in LOCAL_DERIVED_TOPOLOGY:
        local = repo_path(source, f'{TOPOLOGY_ROOT}/{name}')
        target = repo_path(checkout, f'{TOPOLOGY_ROOT}/{name}')
        if local.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, target)
    for name in ('source-blocks.v1.json', 'semantic-requirements.v1.json'):
        evidence = repo_path(source, f'{SOURCE_ROOT}/{name}')
        committed = repo_path(checkout, f'{TOPOLOGY_ROOT}/{name}')
        if not evidence.is_file() or load_json(evidence) != load_json(committed):
            raise ValueError(f'Chapter 3 evidence does not match the local authoritative inputs: {name}')
    manifest = repo_path(source, f'{SOURCE_ROOT}/source-manifest.v1.json')
    payload = load_json(manifest, {})
    if payload.get('schema_version') != 'chapter3.source-manifest.v1' or not payload.get('sources'):
        raise ValueError('Current Chapter 3 source manifest is required')
    tracked = set(git(checkout, 'ls-files').splitlines())
    for row in payload['sources']:
        path = row.get('path', '')
        # Chapter 3 hashes decoded text; Git's CRLF checkout conversion does not
        # change that source identity. Readiness still checks its full bytes.
        digest = hashlib.sha256(repo_path(checkout, path).read_text(encoding='utf-8').encode()).hexdigest() if path in tracked else None
        if digest != str(row.get('sha256', '')).removeprefix('sha256:'):
            raise ValueError(f'Chapter 3 source evidence is stale or uncommitted: {path}')
    # A stale local projection is disposable derived state. The Chapter 3
    # source manifest remains authoritative; Capability/MVG generation will
    # replace invalid local topology projections after validating source hashes.
    paths = [f'{SOURCE_ROOT}/{name}' for name in (
        'source-manifest.v1.json', 'source-blocks.v1.json', 'semantic-requirements.v1.json')]
    paths.append('logs/ci/chapter5/extraction-b.snapshot.json')
    for family in ('readiness', 'reconciliation'):
        directory = repo_path(source, f'logs/ci/chapter5/{family}')
        paths.extend(p.relative_to(source).as_posix() for p in directory.glob('*.json'))
    for relative in paths:
        original, target = repo_path(source, relative), repo_path(checkout, relative)
        if original.is_file() and not target.exists():
            if original.stat().st_size > 32 * 1024 * 1024:
                raise ValueError(f'Planning evidence exceeds its size limit: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)


def prepare_checkout(root: Path, checkout: Path, revision: str) -> None:
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        git(root, 'worktree', 'add', '--detach', str(checkout), revision)
    if git(checkout, 'rev-parse', 'HEAD') != revision:
        raise ValueError('Planning checkout is not the selected local workspace commit')
    hydrate_evidence(root, checkout)


def task_scope(checkout: Path) -> list[str]:
    from _planning_scope import round_scope
    scope = round_scope(checkout, [], checkout / SOURCE_ROOT / 'source-blocks.v1.json',
                        checkout / SOURCE_ROOT / 'semantic-requirements.v1.json')
    return scope['required_task_ids']


def journal_targets(checkout: Path) -> dict[str, str]:
    targets = {}
    for family in ('capability-planning', 'mvg-planning'):
        for path in (checkout / 'logs/ci' / family).glob('*/apply-journal.json'):
            journal = load_json(path, {})
            if journal.get('schema_version') != 'newrouge.planning-apply-journal.v1':
                raise ValueError('Invalid planning apply journal')
            for row in journal.get('entries', []):
                actual = file_sha(repo_path(checkout, row['path']))
                if actual not in {row.get('before_sha256'), row['after_sha256']}:
                    raise ValueError(f'Planning output was edited: {row["path"]}')
                targets[row['path']] = actual
    return targets


def validate_checkout(root: Path, checkout: Path, revision: str) -> None:
    if git(checkout, 'rev-parse', 'HEAD') != revision:
        raise ValueError('Planning checkout commit changed')
    owned = journal_targets(checkout)
    changed = set(git(checkout, 'diff', '--name-only', 'HEAD').splitlines())
    changed.update(git(checkout, 'ls-files', '--others', '--exclude-standard').splitlines())
    allowed_local = {f'{TOPOLOGY_ROOT}/{name}' for name in LOCAL_DERIVED_TOPOLOGY}
    if changed - set(owned) - allowed_local:
        raise ValueError('Uncommitted input changes in planning checkout: ' + ', '.join(sorted(changed - set(owned))[:3]))


def committed_text(root: Path, revision: str, path: str) -> dict:
    require_main(root, revision)
    repo_path(root, path)
    entry = git(root, 'ls-tree', revision, '--', path)
    if not entry.startswith(('100644 blob ', '100755 blob ')):
        raise ValueError('Source is not a regular committed local workspace file')
    blob = entry.split()[2]
    if int(git(root, 'cat-file', '-s', blob)) > 2 * 1024 * 1024:
        raise ValueError('Source exceeds the 2 MiB preview limit')
    result = subprocess.run(['git', '-C', str(root), 'cat-file', 'blob', blob],
                            capture_output=True, check=True, timeout=30)
    require_main(root, revision)
    return {'path': path, 'revision': revision, 'content': result.stdout.decode('utf-8-sig')}


class MainCheckout:
    """Read a live local Git checkout; no scan, catalog or archive fallback."""
    def __init__(self, root: Path, revision: str, extra_paths=()):
        self.root, self.commit, self.authority_ref = root, revision, 'local-workspace'
        self.paths = tuple(sorted(set(git(root, 'ls-files').splitlines()) | set(extra_paths)))

    def read_bytes(self, path: str) -> bytes:
        if path not in self.paths:
            raise ValueError('File is not a committed local input or owned planning output')
        return repo_path(self.root, path).read_bytes()

    def read_text(self, path: str) -> str:
        return self.read_bytes(path).decode('utf-8-sig')

    def digest(self, path: str) -> str:
        return hashlib.sha256(self.read_bytes(path).replace(b'\r\n', b'\n')).hexdigest()
