"""Durable local planning jobs using the existing planners and real main checkout."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from _planning_skill_common import (
    _terminate_process_tree, atomic_json, canonical_sha, file_sha, load_json,
    normalized_file_sha, repo_path,
)
from _project_health_planning_inputs import (
    LOCAL_DERIVED_TOPOLOGY, MainCheckout, TOPOLOGY_ROOT, git, prepare_checkout, task_scope, validate_checkout,
    workspace_revision,
)

JOB_ROOT = Path('logs/ci/knowledge-planning')
_JOB_LOCKS: dict[str, threading.Lock] = {}
_JOB_LOCKS_GUARD = threading.Lock()
_RUN_LOCKS: dict[str, threading.Lock] = {}
_RUN_LOCKS_GUARD = threading.Lock()
_ACTIVE_JOB_CONTEXT: ContextVar[tuple[Path, str] | None] = ContextVar(
    'project_health_active_job_context', default=None
)


class PlanningCancelled(RuntimeError):
    pass


def _job_lock(job_id: str) -> threading.Lock:
    with _JOB_LOCKS_GUARD:
        return _JOB_LOCKS.setdefault(job_id, threading.Lock())


def _run_lock(run_dir: Path) -> threading.Lock:
    """Serialize cancellation cleanup with the publication boundary."""
    key = str(run_dir.resolve())
    with _RUN_LOCKS_GUARD:
        return _RUN_LOCKS.setdefault(key, threading.Lock())


def update_job(root: Path, job: dict, **values) -> dict:
    """Merge worker updates with a concurrent cancellation request."""
    with _job_lock(job['job_id']):
        path = job_path(root, job['job_id'])
        current = load_json(path, {})
        merged = {**current, **job, **values}
        if current.get('cancel_requested'):
            merged['cancel_requested'] = True
            merged['cancel_requested_at'] = current.get('cancel_requested_at')
            if current.get('status') == 'cancelling' and merged.get('status') in ('queued', 'running'):
                merged['status'] = 'cancelling'
        merged['heartbeat_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, merged)
        job.clear()
        job.update(merged)
        return merged


def request_cancel(root: Path, job_id: str) -> dict:
    # Set the cancellation token under the durable job lock first.  The worker
    # checks this token while holding the run lock before publishing a latest
    # pointer, so a request arriving in that narrow window wins deterministically.
    with _job_lock(job_id):
        path = job_path(root, job_id)
        job = load_json(path, {})
        if job.get('job_id') != job_id:
            raise ValueError('Planning job is unavailable')
        if job.get('status') not in ('queued', 'running', 'cancelling'):
            raise ValueError('Planning job is not active')
        job.update(status='cancelling', cancel_requested=True,
                   cancel_requested_at=datetime.now(timezone.utc).isoformat(),
                   message='Cancellation requested; waiting for the current stage to stop')
        job['heartbeat_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, job)
    # Cleanup is serialized with publication, but never holds the job lock
    # while waiting for the run lock (the worker uses the opposite order).
    try:
        run_dir = execution_root(root, job) / 'logs/ci' / (
            'capability-planning' if job.get('action') == 'capability' else 'mvg-planning'
        ) / job_id
        with _run_lock(run_dir):
            _isolate_cancelled_result(root, job)
            _revoke_latest_pointer(root, job)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return job


def recover_stale_jobs(root: Path) -> list[str]:
    """Close jobs left active after the previous server process exited."""
    jobs_dir = repo_path(root, JOB_ROOT.as_posix())
    recovered = []
    if not jobs_dir.is_dir():
        return recovered
    for path in jobs_dir.glob('planning-*/job.json'):
        try:
            job = load_json(path, {})
            if job.get('status') not in ('queued', 'running', 'cancelling'):
                continue
            owner_pid = int(job.get('owner_pid') or 0)
            if owner_pid and _pid_alive(owner_pid):
                continue
            cancelled = bool(job.get('cancel_requested')) or job.get('status') == 'cancelling'
            job.update(status='cancelled' if cancelled else 'failed',
                       message=('Cancelled during service restart' if cancelled else
                                f'Interrupted by service restart during {job.get("stage", "unknown")}'),
                       interrupted_at=datetime.now(timezone.utc).isoformat(),
                       heartbeat_at=datetime.now(timezone.utc).isoformat())
            atomic_json(path, job)
            recovered.append(str(job.get('job_id') or path.parent.name))
        except (OSError, ValueError, TypeError):
            continue
    return recovered


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == 'nt':
        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                                capture_output=True, text=True, check=False)
        return result.returncode == 0 and f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _cancel_requested(root: Path, job_id: str) -> bool:
    return bool(load_json(job_path(root, job_id), {}).get('cancel_requested'))


def _applied_truth(run_dir: Path, state: dict) -> bool:
    """Return true only for an explicit apply receipt, never generic phases."""
    if state.get('applied') is True:
        return True
    journal = load_json(run_dir / 'apply-journal.json', {})
    summary = load_json(run_dir / 'apply-summary.json', {})
    if not isinstance(journal, dict) or journal.get('status') != 'complete':
        return False
    if not isinstance(summary, dict) or not summary:
        return False
    # Both production apply paths persist an explicit digest in state and a
    # non-empty summary after the journal reaches complete.
    return any(key in state for key in (
        'applied_manifest_sha256', 'applied_capabilities_sha256', 'changed_task_ids'))


def _close_attempt_records(value, *, stage: str, cancelled_at: str):
    if isinstance(value, dict):
        result = dict(value)
        if str(result.get('status', '')).casefold() in {
                'queued', 'running', 'in_progress', 'pending', 'started'}:
            result['status'] = 'cancelled'
            result['cancelled_at'] = cancelled_at
            result['cancelled_stage'] = stage
        return {key: _close_attempt_records(child, stage=stage, cancelled_at=cancelled_at)
                for key, child in result.items()}
    if isinstance(value, list):
        return [_close_attempt_records(child, stage=stage, cancelled_at=cancelled_at)
                for child in value]
    return value


def _isolate_cancelled_result(root: Path, job: dict) -> None:
    result_path = job_path(root, job['job_id']).parent / 'result.json'
    if not result_path.is_file():
        return
    quarantine = result_path.with_name('result.cancelled.json')
    if quarantine.exists():
        quarantine = result_path.with_name(f'result.cancelled.{uuid.uuid4().hex}.json')
    result_path.replace(quarantine)


def _revoke_latest_pointer(root: Path, job: dict) -> None:
    action = job.get('action')
    if action not in ('capability', 'mvg'):
        return
    pointer_path = root / JOB_ROOT / f'{action}-latest.json'
    pointer = load_json(pointer_path, {})
    if pointer.get('job_id') == job.get('job_id'):
        pointer_path.unlink(missing_ok=True)


def _write_result_if_not_cancelled(root: Path, job: dict, result: dict) -> bool:
    """Publish result.json only while the cancellation token is clear."""
    run_dir = execution_root(root, job) / 'logs/ci' / (
        'capability-planning' if job.get('action') == 'capability' else 'mvg-planning'
    ) / job['job_id']
    with _job_lock(job['job_id']):
        current = load_json(job_path(root, job['job_id']), {})
        if current.get('cancel_requested') or current.get('status') == 'cancelling':
            return False
        with _run_lock(run_dir):
            atomic_json(job_path(root, job['job_id']).parent / 'result.json', result)
            return True


def _publish_latest_if_not_cancelled(root: Path, job: dict) -> bool:
    """Publish a latest pointer using a cancellation-token compare-and-set."""
    action = job.get('action')
    if action not in ('capability', 'mvg'):
        return False
    with _job_lock(job['job_id']):
        current = load_json(job_path(root, job['job_id']), {})
        if (current.get('cancel_requested') or current.get('status') in ('cancelling', 'cancelled')
                or current.get('status') != 'completed'):
            return False
        run_dir = execution_root(root, job) / 'logs/ci' / (
            'capability-planning' if action == 'capability' else 'mvg-planning'
        ) / job['job_id']
        with _run_lock(run_dir):
            atomic_json(root / JOB_ROOT / f'{action}-latest.json', {'job_id': job['job_id']})
            return True


def _mark_run_cancelled(run_dir: Path, *, action: str, stage: str) -> None:
    """Close active child attempts after a planning run is cancelled.

    The HTTP job and the planner's durable ``run.json`` are separate state
    machines.  Updating only the former leaves a stale ``running`` attempt
    that recovery can later mistake for resumable work.  Preserve completed
    evidence and only transition active attempt records to ``cancelled``.
    """
    path = run_dir / 'run.json'
    with _run_lock(run_dir):
        state = load_json(path, {})
        if not isinstance(state, dict) or not state:
            return
        cancelled_at = datetime.now(timezone.utc).isoformat()
        applied_truth = _applied_truth(run_dir, state)
        updated = dict(state)
        # Only known attempt containers are mutable cancellation state.  Do
        # not recursively rewrite arbitrary evidence payloads containing a
        # business-level status such as ``running``.
        for key in ('candidate_attempts', 'review_attempts', 'alignment_attempts',
                    'generation_attempts', 'selection_attempts', 'semantic_review_attempts'):
            if key in updated:
                updated[key] = _close_attempt_records(updated[key], stage=stage,
                                                      cancelled_at=cancelled_at)
        selection = updated.get('capability_selection')
        if isinstance(selection, dict) and 'attempts' in selection:
            selection = dict(selection)
            selection['attempts'] = _close_attempt_records(
                selection['attempts'], stage=stage, cancelled_at=cancelled_at)
            updated['capability_selection'] = selection
        # A late cancellation request must not rewrite a successfully applied
        # projection as if it had never happened. Keep the applied phase and add a
        # cancellation audit marker; only unfinished runs become cancelled.
        if not applied_truth:
            updated['phase'] = 'cancelled'
            updated['status'] = 'cancelled'
        else:
            updated['cancel_requested_after_apply'] = True
        updated['cancelled_action'] = action
        updated['cancelled_stage'] = stage
        updated['cancelled_at'] = cancelled_at
        atomic_json(path, updated)


def _touch_job(root: Path, job_id: str) -> None:
    """Refresh liveness without allowing a worker snapshot to overwrite state."""
    with _job_lock(job_id):
        path = job_path(root, job_id)
        current = load_json(path, {})
        if not current or current.get('job_id') != job_id:
            return
        current['heartbeat_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, current)


def compact_error(value: str) -> str:
    try:
        payload = json.loads(value)
        if isinstance(payload, dict) and payload.get('reason'):
            details = [str(payload['reason'])]
            if payload.get('error_type'):
                details.append(f"error_type={payload['error_type']}")
            if payload.get('attempts_used') is not None and payload.get('attempt_limit') is not None:
                details.append(f"attempts={payload['attempts_used']}/{payload['attempt_limit']}")
            if payload.get('last_error'):
                details.append(f"last_error={str(payload['last_error'])[:320]}")
            value = '; '.join(details)
    except (ValueError, TypeError):
        pass
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    return ' '.join((lines[-1:] or ['Planning failed']))[:320]


def job_path(root: Path, job_id: str) -> Path:
    if not re.fullmatch(r'planning-[0-9a-f]{32}', job_id):
        raise ValueError('Invalid planning job ID')
    return repo_path(root, (JOB_ROOT / job_id / 'job.json').as_posix())


def public_job(job: dict) -> dict:
    return {key: job.get(key) for key in (
        'job_id', 'action', 'status', 'stage', 'revision', 'message', 'count',
        'recoverable_stage', 'heartbeat_at', 'cancel_requested', 'cancel_requested_at',
    )}


def read_job(root: Path, job_id: str) -> dict:
    result = load_json(job_path(root, job_id), {})
    if result.get('job_id') != job_id:
        raise ValueError('Planning job is unavailable')
    return result


def _planning_input_fresh(root: Path, job: dict) -> bool:
    """Check a result against local authoritative inputs, not a branch commit.

    Planning checkouts may be based on an older commit after a harmless local
    commit advances. The prepared input bundle records the exact source hashes;
    only changes to those inputs invalidate the result. Derived planning files
    needed by an MVG job are resolved from its owned checkout when they are not
    present in the local worktree.
    """
    checkout = execution_root(root, job)
    family = 'capability-planning' if job.get('action') == 'capability' else 'mvg-planning'
    index_path = checkout / 'logs/ci' / family / job['job_id'] / 'analysis-input' / 'analysis-index.json'
    index = load_json(index_path, {}) if index_path.is_file() else {}
    # Story 1.1 runs carry a single input envelope whose inventory includes
    # Chapter 5 evidence and explicit references that are not all represented
    # by the older authority_inputs map. Validate that envelope before the
    # legacy hash loop; pre-envelope runs retain the historical behavior.
    run_state = load_json(index_path.parent.parent / 'run.json', {}) if index_path.parent.parent.is_dir() else {}
    applied_outputs = {}
    if (job.get('action') == 'mvg' and job.get('status') == 'completed'
            and run_state.get('applied') is True):
        manifest = run_state.get('manifest_path')
        expected = (job.get('output_hashes') or {}).get(manifest)
        journal = load_json(index_path.parent.parent / 'apply-journal.json', {})
        entries = journal.get('entries', [])
        bound = next((row for row in entries if row.get('path') == manifest), {})
        if (journal.get('schema_version') != 'newrouge.planning-apply-journal.v1'
                or journal.get('status') != 'complete' or not expected
                or expected != run_state.get('applied_manifest_sha256')
                or expected != bound.get('after_sha256')):
            return False
        manifest_path = repo_path(checkout, manifest)
        if not manifest_path.is_file() or file_sha(manifest_path) != expected:
            return False
        applied_outputs[manifest] = expected
    if job.get('action') == 'mvg' and (
            'input_envelope_sha256' in run_state or 'input_envelope' in index):
        try:
            from _mvg_input_envelope import validate_envelope
            try:
                validate_envelope(checkout, index_path.parent, run_state or job)
            except ValueError:
                # A completed apply may introduce/replace its manifest. The
                # full original-source and Chapter 5 gate has already run;
                # accept only that exact journal/output-bound predecessor drift.
                diagnostic = load_json(index_path.parent.parent / 'input-freshness.json', {})
                if (not applied_outputs or diagnostic.get('status') != 'blocked'
                        or diagnostic.get('drift') != sorted(applied_outputs)):
                    raise
                validate_envelope(checkout, index_path.parent, run_state or job, check_originals=False)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return False
    authority = index.get('authority_inputs')
    if not isinstance(authority, dict) or not authority:
        return False
    authority_root = root
    checkout_job_id = job.get('checkout_job_id')
    if checkout_job_id:
        try:
            parent = read_job(root, checkout_job_id)
            authority_root = execution_root(root, parent)
        except (OSError, ValueError, KeyError, TypeError):
            return False
    for relative, expected in authority.items():
        relative = str(relative).replace('\\', '/')
        if relative in applied_outputs:
            if file_sha(repo_path(checkout, relative)) != applied_outputs[relative]:
                return False
            continue
        if expected is None:
            # An initial MVG run may intentionally plan a manifest that is not
            # yet present in the local repository. Its absence is part of the
            # prepared identity until the generated result is promoted.
            continue
        # Only local derived Capability projections come from the selected
        # Capability checkout. All committed source/task evidence must match
        # the current MVG checkout revision, even when the parent Capability
        # was generated before a later local commit.
        is_capability_projection = relative in {
            f'{TOPOLOGY_ROOT}/{name}' for name in LOCAL_DERIVED_TOPOLOGY
        }
        primary_root = (
            authority_root
            if authority_root == root or is_capability_projection
            else checkout
        )
        path = repo_path(primary_root, relative)
        if not path.is_file():
            fallback_root = checkout if primary_root == authority_root else authority_root
            path = repo_path(fallback_root, relative)
        if not path.is_file() and primary_root != root and fallback_root != root:
            path = repo_path(root, relative)
        if not path.is_file() or (normalized_file_sha(path) != expected and file_sha(path) != expected):
            return False
    return True


def _derived_output_is_current(root: Path, job: dict, relative: str) -> bool:
    """Allow a dependent local planning job to advance shared derived files."""
    for action in ('mvg', 'capability'):
        pointer = load_json(root / JOB_ROOT / f'{action}-latest.json', {})
        if not pointer.get('job_id'):
            continue
        try:
            child = read_job(root, pointer['job_id'])
        except ValueError:
            continue
        if child.get('checkout_job_id') != job.get('job_id'):
            continue
        expected = (child.get('output_hashes') or {}).get(relative)
        if expected and file_sha(execution_root(root, child) / relative) == expected:
            return True
    return False


def selected_result(root: Path, action: str) -> dict | None:
    latest_pointer_path = root / JOB_ROOT / f'{action}-latest.json'
    pointer = load_json(latest_pointer_path, {})
    # A completed local planning result is derived state and its latest pointer
    # can be lost during an interrupted backup/restore.  Recover only when the
    # durable attempt pointer identifies a completed, still-fresh result; failed
    # or incomplete attempts must never become public main data.
    if not pointer.get('job_id') and not latest_pointer_path.is_file():
        pointer = load_json(root / JOB_ROOT / f'{action}-attempt.json', {})
    if not pointer.get('job_id'):
        return None
    job = read_job(root, pointer['job_id'])
    if action == 'mvg' and not _mvg_epoch_current(root, job):
        return None
    if (job.get('action') != action or job['status'] != 'completed'
            or not _planning_input_fresh(root, job)):
        return None
    if file_sha(job_path(root, job['job_id']).parent / 'result.json') != job.get('result_sha256'):
        raise ValueError('Generated planning result identity changed')
    return job


def execution_root(root: Path, job: dict) -> Path:
    # `checkout_job_id` records the selected Capability source for dependent
    # MVG runs.  It must not identify the physical checkout: each planning job
    # needs its own revision-bound worktree, otherwise an MVG job can reuse a
    # Capability worktree at a different commit.
    checkout_id = job['job_id']
    # Keep the Git worktree outside the repository's long logs path. Windows
    # checkout can otherwise fail on tracked execution-plan filenames before
    # the planner gets a chance to read its actual inputs.
    checkout_root = Path(os.environ.get('SC_KNOWLEDGE_PLANNING_CHECKOUT_ROOT', tempfile.gettempdir()))
    # Keep the per-job directory short as well; the full UUID is retained in
    # logs and job metadata, while the checkout only needs a collision-safe
    # prefix to stay below Windows path limits.
    short_id = checkout_id.removeprefix('planning-')[:12]
    return checkout_root / 'nrp' / short_id


def create_job(root: Path, action: str, manifest: str | None = None, *, fresh: bool = False) -> dict:
    if action not in ('capability', 'mvg'):
        raise ValueError('Unknown planning action')
    revision = workspace_revision(root)
    if action == 'mvg':
        manifest = manifest or 'docs/testing/mvg/m1-full.json'
        if not re.fullmatch(r'docs/testing/mvg/[A-Za-z0-9][A-Za-z0-9_.-]*\.json', manifest):
            raise ValueError('Choose a repository MVG manifest')
        existing = set(git(root, 'ls-files').splitlines())
        if manifest not in existing and manifest != 'docs/testing/mvg/m1-full.json':
            prior = selected_result(root, 'mvg')
            if not prior or prior.get('manifest') != manifest:
                raise ValueError('Selected manifest is not in the local workspace or an owned generated result')
    current_capability = selected_result(root, 'capability') if action == 'mvg' else None
    current_capability_id = current_capability.get('job_id') if current_capability else None
    current_capability_hash = current_capability.get('output_hashes', {}).get(
        'docs/planning/semantic-topology/capabilities.v1.json') if current_capability else None
    # A committed main topology may be the selected Capability source even
    # when no page-generated parent job exists. Bind its exact bytes so the
    # planner still has a durable identity without inventing a parent job.
    capability_rel = 'docs/planning/semantic-topology/capabilities.v1.json'
    if action == 'mvg' and not current_capability_hash:
        capability_file = root / capability_rel
        if capability_file.is_file() and capability_rel in set(git(root, 'ls-files').splitlines()):
            current_capability_hash = normalized_file_sha(capability_file)
    # Continue the same persisted attempt after a disconnect/restart. Reusing a
    # terminal result also avoids silently paying for another identical review.
    # A user-initiated page action always requests a fresh generation. Explicit
    # operator recovery may still resume a durable run independently of clicks.
    pointer = {} if fresh else load_json(root / JOB_ROOT / f'{action}-attempt.json', {})
    if pointer.get('job_id'):
        prior = read_job(root, pointer['job_id'])
        same_capability = action != 'mvg' or (
            prior.get('checkout_job_id') == current_capability_id and
            prior.get('capabilities_sha256') == current_capability_hash
        )
        if (prior.get('manifest') == manifest and same_capability
                and (action != 'mvg' or _mvg_epoch_current(root, prior))
                and _planning_input_fresh(root, prior)):
            # Resume interrupted planner stages, but never keep retrying a
            # prepare failure that happened before the planner created its
            # durable run state (for example, Git could not create the worktree).
            family = 'capability-planning' if action == 'capability' else 'mvg-planning'
            run_state = execution_root(root, prior) / 'logs/ci' / family / prior['job_id'] / 'run.json'
            # A failed generation run may have exhausted all candidate retry
            # slots under an older runner (for example OpenAI API).  Reusing
            # it after the runner configuration changes leaves no slot for the
            # current runner and reports an empty error.  Prepare failures are
            # still resumable because they have not consumed model attempts.
            if prior.get('status') == 'failed' and prior.get('stage') == 'generate':
                # Resume an interrupted run only when it persisted at least
                # one reusable candidate.  A run whose candidates all failed
                # must start fresh so a changed runner gets new retry slots.
                state = load_json(run_state, {}) if run_state.is_file() else {}
                if action == 'mvg' and state.get('selection_block_reason') == 'run_blocked_budget_exhausted':
                    # Explicit recovery retains the ended run and its receipts.
                    # A fresh page action intentionally bypasses this pointer.
                    return prior
                if action == 'mvg':
                    reusable = bool(_mvg_valid_candidates(run_state.parent, state))
                    if state.get('generation_strategy') == 'capability-local-selection.v1':
                        try:
                            from _mvg_capability_selection import recovery_available
                            checkout = execution_root(root, prior)
                            # Current admissions and the selected prefix are
                            # independent recovery assets; never lose a valid
                            # prefix because this scope has no admitted slot.
                            reusable = recovery_available(checkout, run_state.parent, state)
                        except (OSError, ValueError, KeyError, TypeError, AttributeError):
                            reusable = False
                else:
                    candidates = state.get('candidate_attempts') or {}
                    reusable = any(
                        isinstance(row, dict) and row.get('final_meta')
                        for row in candidates.values()
                    )
                if not reusable:
                    pass
                else:
                    return prior
            elif prior.get('status') != 'failed' or run_state.is_file():
                return prior
    job_id = 'planning-' + uuid.uuid4().hex
    job = {'schema_version': 'newrouge.knowledge-planning-job.v1', 'job_id': job_id,
           'action': action, 'revision': revision, 'manifest': manifest, 'stage': 'prepare',
           'status': 'queued', 'created_at': datetime.now(timezone.utc).isoformat(),
           'message': f'Queued {action} generation from local workspace {revision[:12]}'}
    if action == 'mvg':
        from _mvg_capability_recovery import registry
        job['mvg_epoch'] = registry(root)['epoch']
        capability = current_capability
        if capability:
            job['checkout_job_id'] = capability['job_id']
        if current_capability_hash:
            job['capabilities_sha256'] = current_capability_hash
    atomic_json(job_path(root, job_id), job)
    atomic_json(root / JOB_ROOT / f'{action}-attempt.json', {'job_id': job_id})
    return job


def invoke(checkout: Path, script: str, arguments: list[str], log: Path) -> dict:
    command = [sys.executable, str(Path(__file__).with_name(script)), '--repo-root', str(checkout), *arguments]
    # Planners retain their original per-attempt/time gates and process cleanup.
    # No outer timeout abandons a still-active model child or resets its budget.
    # The planner emits JSON with human-readable (possibly non-ASCII) reasons.
    # A redirected Windows stdout otherwise uses the active code page even
    # though the log file itself is opened as UTF-8, producing mixed/invalid
    # bytes when the log is read back below.
    child_env = {
        **os.environ,
        'PYTHONUNBUFFERED': '1',
        'PYTHONIOENCODING': 'utf-8',
    }
    recovery_binding = load_json(checkout / 'logs/ci/mvg-recovery-store.json', {})
    if script == 'plan_mvg.py' and recovery_binding:
        child_env.update(SC_MVG_RECOVERY_ROOT=recovery_binding['store'],
                         SC_MVG_RECOVERY_EPOCH=str(recovery_binding['epoch']))
    with log.open('w', encoding='utf-8', newline='\n') as output:
        process = subprocess.Popen(command, cwd=checkout, stdout=output, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', env=child_env)
        last_heartbeat = 0.0
        while process.poll() is None:
            context = _ACTIVE_JOB_CONTEXT.get()
            if context and _cancel_requested(*context):
                _terminate_process_tree(process)
                process.wait(timeout=15)
                raise PlanningCancelled('Planning cancelled by operator')
            if context and time.monotonic() - last_heartbeat >= 2.0:
                _touch_job(*context)
                last_heartbeat = time.monotonic()
            time.sleep(0.2)
        result = process
    text = log.read_text(encoding='utf-8')
    if result.returncode:
        raise ValueError(compact_error(text))
    try:
        # Current planners print one complete JSON result, not log chatter.
        return json.loads(text)
    except ValueError as exc:
        raise ValueError('Planning stage returned an invalid result') from exc


def _refresh_capability_knowledge(root: Path, checkout: Path, job: dict) -> dict:
    """Refresh the workspace Chapter 5 topology after a Capability apply.

    Capability planning runs in an isolated worktree.  The planner's result is
    therefore not visible to the Knowledge workspace until the registered
    Chapter Knowledge refresh hook consumes that same worktree.  Refreshing the
    worktree first keeps the source/Requirement/Capability hashes coherent; the
    runtime snapshots are copied back only after a successful, closed refresh.
    This never publishes main or changes task authority.
    """
    import shutil
    from refresh_chapter_knowledge import run as refresh_knowledge

    topology = checkout / TOPOLOGY_ROOT
    evidence = checkout / 'logs/ci/task-generation'
    # Capability apply rebinds the Chapter 5 fingerprint for every task whose
    # capability_refs changed.  The global ``latest.json`` pointer may still
    # refer to an older task, so close the refresh against a re-bound pair.
    apply_summary = load_json(
        checkout / 'logs/ci/capability-planning' / job['job_id'] / 'apply-summary.json', {}
    )
    changed_task_ids = [str(value) for value in apply_summary.get('changed_task_ids', [])]
    candidates = evidence / 'task-candidates.enriched.json'
    # Chapter 5 closure does not inspect the Chapter 3 candidate body, but the
    # refresh contract requires the path to exist.  Hydrate it from the parent
    # workspace when available; otherwise use an explicit empty source5 view.
    if not candidates.is_file():
        source_candidates = root / 'logs/ci/task-generation/task-candidates.enriched.json'
        candidates.parent.mkdir(parents=True, exist_ok=True)
        if source_candidates.is_file():
            shutil.copyfile(source_candidates, candidates)
        else:
            atomic_json(candidates, {'schema_version': 'task-generation.candidates.v1', 'candidates': []})

    # Validate every re-bound task, but build the expensive workspace topology
    # once.  All task-scoped readiness files share the same source/ledger and
    # Capability projection; one current pair is sufficient for the view after
    # the complete set has passed its freshness gate.
    if changed_task_ids:
        from chapter5_semantic_reconciliation import load_task_readiness
        for task_id in changed_task_ids:
            ready, _payload, reason = load_task_readiness(checkout, task_id)
            if not ready:
                raise ValueError(f'Capability Knowledge refresh readiness blocked:{task_id}:{reason}')
    task_id = changed_task_ids[0] if changed_task_ids else None
    reconciliation = checkout / 'logs/ci/chapter5/reconciliation' / (
        f'task-{task_id}.json' if task_id else 'latest.json'
    )
    readiness = checkout / 'logs/ci/chapter5/readiness' / (
        f'task-{task_id}.json' if task_id else 'latest.json'
    )
    summary = refresh_knowledge(
        checkout,
        source='chapter5',
        trigger_run_id=f'{job["job_id"]}:chapter5-knowledge-refresh:{task_id or "latest"}',
        refresh_local=True,
        write_planning=False,
        publish_if_eligible=False,
        triplet_status='unknown',
        source_manifest_path=evidence / 'source-manifest.v1.json',
        ledger_path=evidence / 'source-blocks.v1.json',
        semantics_path=evidence / 'semantic-requirements.v1.json',
        capabilities_path=topology / 'capabilities.v1.json',
        edges_path=topology / 'topology-edges.v1.json',
        candidates_path=candidates,
        report_path=evidence / 'semantic-conservation-report.json',
        reconciliation_path=reconciliation,
        readiness_path=readiness,
    )
    if summary.get('closure_passed') is not True or summary.get('local_refresh_status') not in {
        'stable_refreshed', 'stable_reused'
    }:
        raise ValueError(
            'Capability Knowledge refresh did not produce a stable workspace topology: '
            + compact_error(json.dumps(summary, ensure_ascii=False))
        )

    runtime = checkout / 'logs/ci/project-health-knowledge/topology'
    target = root / 'logs/ci/project-health-knowledge/topology'
    copied: list[str] = []
    for name in (
        'workspace-last-attempt.json', 'workspace-latest.json',
        'workspace-latest-successful.json', 'workspace-latest-stabilized.json',
    ):
        source = runtime / name
        if not source.is_file():
            continue
        target_path = target / name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = target_path.with_name(target_path.name + '.tmp')
        shutil.copyfile(source, temporary)
        temporary.replace(target_path)
        copied.append((target_path.relative_to(root)).as_posix())
    if not copied:
        raise ValueError('Capability Knowledge refresh produced no workspace topology snapshot')
    return {
        'status': 'refreshed',
        'source': 'chapter5',
        'local_refresh_status': summary.get('local_refresh_status'),
        'closure_passed': summary.get('closure_passed'),
        'topology_revision': summary.get('topology_revision'),
        'trigger_run_id': summary.get('trigger_run_id'),
        'task_ids': changed_task_ids,
        'paths': copied,
    }


def capability_runner_path() -> Path:
    import shutil
    if not (shutil.which('codex') or shutil.which('codex.cmd') or os.environ.get('CODEX_MANAGED_PACKAGE_ROOT')):
        raise ValueError('Codex CLI is required for Capability planning; authenticate Codex CLI or configure it on PATH')
    return Path(__file__).with_name('codex_isolated_model_runner.py')


def runner_path() -> Path:
    """Resolve the configurable runner used by non-Capability planning jobs."""
    configured = os.environ.get('SC_KNOWLEDGE_PLANNING_RUNNER')
    if configured:
        return Path(configured).resolve()
    import shutil
    if shutil.which('codex') or shutil.which('codex.cmd') or os.environ.get('CODEX_MANAGED_PACKAGE_ROOT'):
        return Path(__file__).with_name('codex_isolated_model_runner.py')
    if shutil.which('copilot'):
        return Path(__file__).with_name('copilot_isolated_model_runner.py')
    if os.environ.get('OPENAI_API_KEY'):
        return Path(__file__).with_name('openai_isolated_model_runner.py')
    raise ValueError('Configure an authenticated Codex/Copilot CLI or explicit OpenAI API runner for planning')


def mvg_backend() -> str:
    backend = os.environ.get('SC_KNOWLEDGE_MVG_BACKEND')
    if not backend:
        backend = 'codex-cli'
    if backend not in ('codex-cli', 'openai-api', 'copilot-cli'):
        raise ValueError('Unsupported MVG planning backend')
    return backend


def build_result(checkout: Path, job: dict) -> dict:
    from _project_health_tasks import task_details
    from _semantic_topology import build_topology_view
    from _project_health_mvg_versions import build_overview, attach_planning_routes
    from _mvg_requirement_routes import authority_ids
    extra = [job['manifest']] if job.get('manifest') else []
    reader = MainCheckout(checkout, job['revision'], extra)
    details = task_details(reader)
    documents = [load_json(checkout / TOPOLOGY_ROOT / name, {}) for name in (
        'topology-manifest.v1.json', 'source-blocks.v1.json', 'semantic-requirements.v1.json',
        'capabilities.v1.json', 'topology-edges.v1.json')]
    topology = build_topology_view({'kind': 'workspace', 'revision': job['revision'],
        'authority_ref': 'local-workspace'}, *documents, details, [])
    provenance = {'planning_result': True, 'planning_job_id': job['job_id'],
                  'publication_state': 'local_generated', 'runtime_verified': False}
    topology.update(provenance)
    topology['input_identity_sha256'] = job.get('input_identity_sha256')
    topology['status'] = 'generated_from_local_inputs'
    overview = build_overview(reader, details, topology, {'nodes': {}})
    overview.update(provenance)
    overview['revision'] = topology.get('identity', {}).get('revision')
    overview['input_identity_sha256'] = job.get('input_identity_sha256')
    for manifest in overview['manifests']:
        if manifest['path'] == job.get('manifest'):
            manifest.update(provenance)
            manifest['evidence'] = {'status': 'not_verified', 'reason': 'Generated planning scope; runtime not executed'}
            run_dir = checkout / 'logs/ci/mvg-planning' / job['job_id']
            state = load_json(run_dir / 'run.json', {})
            if (state.get('manifest_path') == manifest['path'] and state.get('applied') is True
                    and state.get('applied_manifest_sha256') == manifest['sha256']):
                proposal_path = run_dir / 'proposal.json'
                proposal = load_json(proposal_path, {})
                # The selected proposal must also be the published, manifest-bound trace.
                summary = load_json(run_dir / 'apply-summary.json', {})
                trace_ref = summary.get('trace_path')
                expected_trace = f'docs/testing/mvg/planning/{job["job_id"]}.json'
                trace = load_json(checkout / expected_trace, {}) if trace_ref == expected_trace else {}
                if (trace.get('applied_manifest_path') == manifest['path']
                        and trace.get('applied_manifest_sha256') == manifest['sha256']
                        and {key: value for key, value in trace.items() if key in proposal} == proposal
                        and trace.get('applied_manifest_candidate', trace.get('manifest_candidate'))
                            == load_json(repo_path(checkout, manifest['path']), {})):
                    attach_planning_routes(manifest, trace, {'kind': 'local_selected_proposal',
                        'path': proposal_path.relative_to(checkout).as_posix(), 'sha256': file_sha(proposal_path)},
                        requirement_ids=authority_ids(
                            load_json(run_dir / 'analysis-input/semantic-requirements.v1.json', {}),
                            load_json(run_dir / 'analysis-input/capabilities.v1.json', {})),
                        applied_manifest=load_json(repo_path(checkout, manifest['path']), {}),
                        read_source=lambda ref: repo_path(checkout, ref).read_bytes())
    return {'topology': topology, 'overview': overview}


def _capability_valid_candidates(run_dir: Path, state: dict) -> list[str]:
    """Return candidate labels whose persisted artifacts passed validation.

    This deliberately checks the durable final metadata and byte identity rather
    than merely counting attempt records.  A recoverable HTTP job must never
    skip back to review on the strength of a partial or stale model output.
    """
    valid: list[str] = []
    for label, record in (state.get('candidate_attempts') or {}).items():
        if not isinstance(record, dict):
            continue
        meta = record.get('final_meta')
        path = run_dir / 'candidates' / f'{label}.json'
        if not isinstance(meta, dict) or meta.get('validation_errors') or not path.is_file():
            continue
        if meta.get('output_sha256') != file_sha(path):
            continue
        try:
            candidate_payload = load_json(path, None)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(candidate_payload, dict):
            continue
        expected_identity = str(state.get('analysis_identity_sha256') or '')
        if expected_identity and str(candidate_payload.get('analysis_identity_sha256') or '') != expected_identity:
            continue
        valid.append(str(label))
    return sorted(valid)


def _mvg_valid_candidates(run_dir: Path, state: dict) -> list[str]:
    """Return MVG candidates whose durable file and formal validation agree."""
    # A prepared MVG run must be checked against the frozen envelope before
    # any admitted candidate can be reused. Older synthetic recovery fixtures
    # have no envelope and intentionally continue through the legacy checks.
    prepared = run_dir / 'analysis-input'
    run_index = load_json(prepared / 'analysis-index.json', {}) if prepared.is_dir() else {}
    run_state = load_json(run_dir / 'run.json', state) if (run_dir / 'run.json').is_file() else state
    if not isinstance(run_state, dict):
        return []
    state = run_state
    run_has_envelope = ('input_envelope_sha256' in state or 'input_envelope' in run_index)
    checkout_root = run_dir.parents[3] if len(run_dir.parents) > 3 else run_dir
    if run_has_envelope:
        try:
            from _mvg_input_envelope import validate_envelope
            validate_envelope(checkout_root, prepared, run_state)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return []
    if state.get('generation_strategy') == 'capability-local-selection.v1':
        try:
            from _mvg_capability_selection import valid_current_candidates
            return valid_current_candidates(checkout_root, run_dir, state)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return []
    valid: list[str] = []
    for label, record in (state.get('candidate_attempts') or {}).items():
        if label not in {'candidate-1', 'candidate-2', 'candidate-3'} or not isinstance(record, dict):
            continue
        # MVG candidate proposals are stored in their isolated candidate
        # workspace. Keep the historical flat path readable for older runs.
        admission = (state.get('candidate_admissions') or {}).get(label)
        if not isinstance(admission, dict) or admission.get('status') != 'admitted':
            continue
        workspace_path = str(admission.get('workspace') or '')
        if workspace_path:
            try:
                candidate_root = repo_path(run_dir, workspace_path)
            except ValueError:
                continue
            if not candidate_root.is_relative_to(run_dir.resolve()):
                continue
            paths = (candidate_root / 'proposal.json',)
        else:
            candidate_root = None
            paths = (run_dir / 'candidates' / label / 'proposal.json',
                     run_dir / 'candidates' / f'{label}.json')
        path = next((candidate_path for candidate_path in paths if candidate_path.is_file()), paths[0])
        if run_has_envelope:
            candidate_input = candidate_root / 'analysis-input' if candidate_root is not None else None
            if candidate_input is None or not candidate_input.is_dir():
                continue
            try:
                validate_envelope(checkout_root, candidate_input, run_state)
            except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
                continue
        validation = record.get('validation') or {}
        if not isinstance(admission, dict):
            admission = {}
        proof = admission.get('review_path')
        execution = admission.get('review_execution_path')
        if not proof or not execution:
            continue
        try:
            proof_path = repo_path(checkout_root, str(proof))
            execution_path = repo_path(checkout_root, str(execution))
        except ValueError:
            continue
        if candidate_root is not None and (
                not proof_path.is_relative_to(candidate_root.resolve())
                or not execution_path.is_relative_to(candidate_root.resolve())):
            continue
        if not proof_path.is_file() or not execution_path.is_file():
            continue
        proof_sha = str(admission.get('proof_sha256') or '')
        execution_sha = str(admission.get('execution_sha256') or '')
        if (not proof_sha or not execution_sha
                or file_sha(proof_path) != proof_sha
                or file_sha(execution_path) != execution_sha):
            continue
        try:
            candidate_payload = load_json(path, {})
            proof_payload = load_json(proof_path, {})
            execution_payload = load_json(execution_path, {})
            if (proof_payload.get('schema_version') not in {
                        'newrouge.mvg-semantic-review.v1', 'newrouge.mvg-capability-admission.v1'}
                    or proof_payload.get('analysis_identity_sha256') != state.get('analysis_identity_sha256')
                    or proof_payload.get('proposal_sha256') != canonical_sha(candidate_payload)
                    or proof_payload.get('verdict') != 'approved'
                    or proof_payload.get('findings') != []):
                continue
            semantics = load_json(run_dir / 'analysis-input/semantic-requirements.v1.json', None)
            if not isinstance(semantics, dict) or not isinstance(semantics.get('requirements'), list):
                continue
            from _mvg_planning_review import review_execution_errors, semantic_review_errors
            scope = state.get('planning_scope') if isinstance(state.get('planning_scope'), dict) else None
            allowed = set(scope.get('requirement_ids', [])) if scope else None
            if semantic_review_errors(state, candidate_payload, proof_payload, semantics, allowed):
                continue
            if review_execution_errors(state, candidate_payload, execution_payload, proof_payload):
                continue
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if (record.get('status') == 'valid' and path.is_file()
                and record.get('proposal_sha256') == file_sha(path)
                and validation.get('status') == 'passed'
                and validation.get('formal_applicable') is True):
            expected_identity = str(state.get('analysis_identity_sha256') or '')
            if not expected_identity:
                continue
            try:
                candidate = load_json(path, {})
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if str(candidate.get('analysis_identity_sha256') or '') != expected_identity:
                continue
            valid.append(label)
    return sorted(valid)


def validate_mvg_capability_binding(root: Path, checkout: Path, job: dict) -> None:
    """Verify the prepared MVG run still consumes its bound Capability.

    ``create_job`` binds the selected parent, but the durable prepared bundle
    is the runtime authority.  Check both identities before invoking any stage
    so stale or tampered run inputs cannot be resumed under a newer Capability.
    """
    if job.get('action') != 'mvg':
        return
    run_dir = checkout / 'logs/ci/mvg-planning' / str(job.get('job_id'))
    index = load_json(run_dir / 'analysis-input' / 'analysis-index.json', {})
    actual = str(index.get('capabilities_sha256') or '')
    expected = str(job.get('capabilities_sha256') or '')
    normalized_actual = normalized_file_sha(capability_path) if (
        (capability_path := run_dir / 'analysis-input' / 'capabilities.v1.json').is_file()
    ) else ''
    exact_actual = file_sha(capability_path) if capability_path.is_file() else ''
    if not expected or not actual or actual not in {exact_actual, normalized_actual}:
        raise ValueError(
            f'Capability identity mismatch: job={expected or "missing"} prepared={actual or "missing"}'
        )
    if not capability_path.is_file() or expected not in {exact_actual, normalized_actual}:
        raise ValueError('Capability identity mismatch: prepared Capability bytes do not match bound hash')
    run_state = load_json(run_dir / 'run.json', {})
    if run_state:
        state_hash = str(run_state.get('capabilities_sha256') or '')
        if state_hash != actual:
            raise ValueError('Capability identity mismatch: planner run state differs from selected job')
    parent_id = str(job.get('checkout_job_id') or '')
    if parent_id:
        parent = read_job(root, parent_id)
        parent_hash = str((parent.get('output_hashes') or {}).get(
            'docs/planning/semantic-topology/capabilities.v1.json') or '')
        if parent_hash != expected:
            raise ValueError('Capability identity mismatch: selected parent output hash changed')


def _capability_review_artifacts_available(run_dir: Path, state: dict) -> bool:
    """Return whether an independent selected review is durably readable."""
    if state.get('review_status') != 'selected' or not state.get('selected_candidate'):
        return False
    review = run_dir / 'review'
    candidate = run_dir / 'candidates' / f"{state['selected_candidate']}.json"
    report = review / 'review.json'
    try:
        report_payload = load_json(report, None)
        metadata = load_json(review / 'review.meta.json', {})
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        report.is_file()
        and isinstance(report_payload, dict)
        and isinstance(metadata, dict)
        and metadata.get('output_sha256') == file_sha(report)
        and candidate.is_file()
    )


def _capability_recovery_stage(root: Path, checkout: Path, job: dict, failed_stage: str) -> str | None:
    """Find the earliest durable Capability stage that can be resumed.

    The planner writes evidence before each stage returns.  If the outer worker
    is interrupted after that write (or an Apply journal is left pending), the
    HTTP layer must expose a resumable job instead of converting the completed
    prefix into a terminal failure.  Main revision drift remains a hard stop.
    """
    if job.get('action') != 'capability':
        return None
    try:
        # Recovery is bound to the prepared authoritative input hashes. A new
        # local commit with unchanged inputs is safe and must not discard the
        # durable candidate/review prefix.
        if not _planning_input_fresh(root, job):
            return None
    except (OSError, ValueError):
        return None
    run_state = checkout / 'logs/ci/capability-planning' / job['job_id'] / 'run.json'
    try:
        state = load_json(run_state, {})
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not state:
        return None
    run_dir = run_state.parent
    valid_candidates = _capability_valid_candidates(run_dir, state)
    review_available = _capability_review_artifacts_available(run_dir, state)

    if failed_stage in {'generate', 'review'}:
        # `no_valid_winner` is an intentional independent-review verdict, not
        # a transport or persistence interruption. Preserve it as terminal
        # evidence instead of silently paying for another review.
        if failed_stage == 'review' and state.get('review_status') == 'no_valid_winner':
            return None
        if review_available:
            return 'align'
        if len(valid_candidates) >= 2:
            return 'review'
    if failed_stage == 'align' and review_available:
        return 'align'
    if failed_stage == 'apply' and review_available:
        try:
            journal = load_json(run_dir / 'apply-journal.json', {})
            alignment = load_json(run_dir / 'alignment-preview.json', {})
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if journal and journal.get('status') != 'complete':
            return 'apply'
        if alignment.get('resolved') is True:
            return 'apply'
        # Apply can fail before alignment is resolved (for example when an
        # older manually supplied override was rejected). Resume the missing
        # LLM alignment stage instead of invoking Apply repeatedly.
        return 'align'
    return None


def run_job(root: Path, job: dict) -> dict:
    directory = job_path(root, job['job_id']).parent
    checkout = execution_root(root, job)
    stage, action = job['stage'], job['action']
    run_id = job['job_id']
    invoked_stage: str | None = None
    try:
        update_job(root, job, status='running',
                   message=f'Generating {action} from local workspace {job["revision"][:12]}',
                   owner_pid=os.getpid())
        derived_source = None
        if action == 'mvg' and job.get('checkout_job_id'):
            parent = read_job(root, job['checkout_job_id'])
            derived_source = execution_root(root, parent)
        prepare_checkout(root, checkout, job['revision'], derived_source=derived_source)
        if action == 'mvg':
            from _mvg_capability_recovery import store_root
            if not _mvg_epoch_current(root, job):
                raise ValueError('MVG generation was cleared; start a new job')
            atomic_json(checkout / 'logs/ci/mvg-recovery-store.json', {
                'store': str(store_root(root)), 'epoch': job.get('mvg_epoch', 0)})
        validate_checkout(root, checkout, job['revision'])
        if action == 'mvg' and job.get('capabilities_sha256'):
            prepared_index = (checkout / 'logs/ci/mvg-planning' / run_id / 'analysis-input' /
                              'analysis-index.json')
            if prepared_index.is_file():
                validate_mvg_capability_binding(root, checkout, job)
        runner = capability_runner_path() if action == 'capability' else runner_path()
        task_args = [value for tid in task_scope(checkout) for value in ('--task-id', tid)]
        script = 'plan_capabilities.py' if action == 'capability' else 'plan_mvg.py'
        stages = ['prepare', 'generate', 'review', 'align', 'apply'] if action == 'capability' else ['prepare', 'generate', 'review', 'validate', 'apply']
        for stage in stages[stages.index(job['stage']):]:
            if _cancel_requested(root, run_id):
                raise PlanningCancelled('Planning cancelled by operator')
            if action == 'mvg' and not _mvg_epoch_current(root, job):
                raise ValueError('MVG generation was cleared; start a new job')
            invoked_stage = None
            validate_checkout(root, checkout, job['revision'])
            job['stage'] = stage
            update_job(root, job, stage=stage)
            args = [stage, '--run-id', run_id]
            if stage == 'prepare':
                args += task_args
                if action == 'mvg':
                    args += ['--capabilities', f'{TOPOLOGY_ROOT}/capabilities.v1.json', '--manifest', job['manifest']]
            elif stage in ('generate', 'review', 'align'):
                if action == 'mvg' and stage == 'generate':
                    args += ['--llm-backend', mvg_backend()]
                else:
                    args += ['--runner', str(runner)]
            elif stage == 'apply':
                args += ['--confirm']
                if action == 'capability':
                    # The align stage is LLM-reviewed. Apply must consume
                    # that exact reviewed artifact instead of rebuilding the
                    # unresolved deterministic preview from the candidate.
                    args += ['--alignment-override',
                             f'logs/ci/capability-planning/{run_id}/alignment-preview.json']
            run_state = checkout / 'logs/ci' / ('capability-planning' if action == 'capability' else 'mvg-planning') / run_id / 'run.json'
            if stage == 'prepare' and run_state.is_file():
                continue
            invoked_stage = stage
            context_token = _ACTIVE_JOB_CONTEXT.set((root, run_id))
            try:
                result = invoke(checkout, script, args, directory / f'{stage}.log')
            finally:
                _ACTIVE_JOB_CONTEXT.reset(context_token)
            # Cancellation may arrive while the child is returning.  Check it
            # before accepting the stage result so a late request cannot race
            # into a completed publication.
            if _cancel_requested(root, run_id):
                raise PlanningCancelled('Planning cancelled before stage result acceptance')
            if action == 'mvg' and stage == 'prepare' and job.get('capabilities_sha256'):
                validate_mvg_capability_binding(root, checkout, job)
            if result.get('status') in ('blocked', 'failed') or result.get('formal_applicable') is False:
                errors = result.get('errors') or result.get('formal_blockers') or []
                raise ValueError(result.get('reason') or '; '.join(str(error) for error in errors[:3]) or 'Planning stage blocked')
            if stage == 'review' and result.get('status') == 'no_valid_winner':
                raise ValueError('Capability review found no valid winner; inspect the retained review')
            if stage == 'align' and result.get('resolved') is not True:
                raise ValueError('Capability ID alignment needs explicit reviewed decisions; existing data is preserved')
            if action == 'capability' and stage == 'apply':
                # Apply updates the derived Capability projection inside the
                # isolated checkout. Refresh Chapter 5 Knowledge before
                # publishing the planning result so workspace consumers and
                # the subsequent MVG job see the same selected bytes.
                job['knowledge_refresh'] = _refresh_capability_knowledge(root, checkout, job)
            update_job(root, job)
        # Errors while building or publishing the read-only result are not an
        # invocation-stage interruption.  Keep that distinction so durable
        # model evidence is never mistaken for a safe Apply retry.
        invoked_stage = None
        stage = 'publish'
        if _cancel_requested(root, run_id):
            raise PlanningCancelled('Planning cancelled before publication')
        validate_checkout(root, checkout, job['revision'])
        result = build_result(checkout, job)
        if action == 'capability':
            result['knowledge_refresh'] = job.get('knowledge_refresh')
        if _cancel_requested(root, run_id):
            raise PlanningCancelled('Planning cancelled before result write')
        if not _write_result_if_not_cancelled(root, job, result):
            raise PlanningCancelled('Planning cancelled before result publication')
        owned_paths = set(git(checkout, 'diff', '--name-only', 'HEAD').splitlines())
        # Formal planning outputs are intentionally ignored by Git. Keep their
        # hashes in the local job record so a tampered generated result is still
        # rejected without making the files repository authority.
        if action == 'capability':
            owned_paths.update({
                'docs/planning/semantic-topology/capabilities.v1.json',
                'docs/planning/semantic-topology/capability-selection.v1.json',
                'docs/planning/semantic-topology/topology-edges.v1.json',
                'docs/planning/semantic-topology/topology-manifest.v1.json',
            })
        elif job.get('manifest'):
            owned_paths.add(str(job['manifest']).replace('\\', '/'))
        owned = {
            path: file_sha(checkout / path) for path in sorted(owned_paths)
            if (checkout / path).is_file()
        }
        job['input_identity_sha256'] = load_json(
            checkout / 'logs/ci' / ('capability-planning' if action == 'capability' else 'mvg-planning') /
            job['job_id'] / 'analysis-input/analysis-index.json', {}
        ).get('analysis_identity_sha256')
        job['output_hashes'] = owned
        job['result_sha256'] = file_sha(directory / 'result.json')
        job['count'] = len(result['topology']['nodes']['capabilities']) if action == 'capability' else len(next(
            row['flows'] for row in result['overview']['manifests'] if row['path'] == job['manifest']))
        job.pop('recoverable_stage', None)
        if _cancel_requested(root, run_id):
            raise PlanningCancelled('Planning cancelled before completion')
        job.update(status='completed', stage='complete', message=f'{action.title()} generated: {job["count"]} '
                   + ('capabilities' if action == 'capability' else 'flows') +
                   f' · local workspace {job["revision"][:12]} · local planning result')
        update_job(root, job)
        if action == 'mvg' and not _mvg_epoch_current(root, job):
            raise ValueError('MVG generation was cleared before publication')
        if not _publish_latest_if_not_cancelled(root, job):
            raise PlanningCancelled('Planning cancelled before latest pointer publication')
    except Exception as exc:
        error = compact_error(str(exc))
        recovery_stage = (
            _capability_recovery_stage(root, checkout, job, stage)
            if invoked_stage is not None and invoked_stage == stage
            else None
        )
        if isinstance(exc, PlanningCancelled) or _cancel_requested(root, run_id):
            run_dir = checkout / 'logs/ci' / (
                'capability-planning' if action == 'capability' else 'mvg-planning'
            ) / run_id
            try:
                _mark_run_cancelled(run_dir, action=action, stage=stage)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # The HTTP job must still reach a terminal cancelled state if
                # a very early cancellation happened before run.json existed.
                pass
            job.pop('recoverable_stage', None)
            job.update(status='cancelled', stage=stage,
                       message=f'{action.title()} planning cancelled during {stage}')
        elif recovery_stage:
            job.update(
                status='recoverable',
                stage=recovery_stage,
                recoverable_stage=recovery_stage,
                message=(
                    f'Capability {recovery_stage} needs retry '
                    f'(durable planning evidence preserved): {error}'
                ),
            )
        else:
            job.pop('recoverable_stage', None)
            job.update(status='failed', message=f'{action.title()} failed ({stage}): {error}')
        update_job(root, job)
    return public_job(job)


def generated_view(root: Path, action: str) -> dict | None:
    job = selected_result(root, action)
    if not job:
        return None
    checkout = execution_root(root, job)
    validate_checkout(root, checkout, job['revision'])
    for path, expected in job.get('output_hashes', {}).items():
        if file_sha(repo_path(checkout, path)) != expected and not _derived_output_is_current(root, job, path):
            raise ValueError('Generated planning output changed; retained main data is preserved')
    result = load_json(job_path(root, job['job_id']).parent / 'result.json')
    return result['topology' if action == 'capability' else 'overview']


def _mvg_epoch_current(root: Path, job: dict) -> bool:
    from _mvg_capability_recovery import registry
    return job.get('mvg_epoch', 0) == registry(root)['epoch']


def mvg_progress(root: Path) -> dict:
    """Current-epoch committed state survives failed jobs and server restart."""
    from _mvg_capability_recovery import registry, progress
    epoch = registry(root)['epoch']
    empty = {'epoch': epoch, 'completed': 0, 'total': 0, 'items': [],
             'status': 'partial_planning', 'runtime_verified': False}
    pointer = load_json(root / JOB_ROOT / 'mvg-attempt.json', {})
    if not pointer.get('job_id'):
        return empty
    job = read_job(root, pointer['job_id'])
    if job.get('action') != 'mvg' or not _mvg_epoch_current(root, job):
        return empty
    checkout = execution_root(root, job)
    run_dir = checkout / 'logs/ci/mvg-planning' / job['job_id']
    state = load_json(run_dir / 'run.json', {})
    if not state.get('capability_selection') or not state.get('recovery'):
        return {**empty, 'job_status': job['status'], 'current': None}
    try:
        return {**progress(checkout, run_dir, state), 'job_status': job['status'],
                'manifest': job.get('manifest'), 'planning_result': True}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        return {**empty, 'job_status': job['status'], 'reason': compact_error(str(exc))}


def planning_source(root: Path, job_id: str, path: str) -> dict:
    job = read_job(root, job_id)
    selected = selected_result(root, 'capability')
    if job['action'] != 'capability' or not selected or selected.get('job_id') != job_id:
        raise ValueError('Generated topology changed; refresh before reading source')
    topology = generated_view(root, 'capability')
    if path not in {row['source_path'] for row in topology['nodes']['source_blocks']}:
        raise ValueError('Source is not in the generated topology')
    checkout = execution_root(root, job)
    source = repo_path(checkout, path)
    if not source.is_file():
        raise ValueError('Source is not present in the generated local planning checkout')
    return {'path': path, 'revision': job['revision'], 'content': source.read_text(encoding='utf-8-sig')}
