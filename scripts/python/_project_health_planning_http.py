"""Asynchronous planning operations sharing the local host's operation lock."""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

from _project_health_planning import create_job, generated_view, public_job, request_cancel, run_job


def start_planning(handler, root, request, operation, guard, state):
    if set(request) - {'action', 'manifest'}:
        raise ValueError('Unexpected planning request fields')
    if not operation.acquire(blocking=False):
        handler.send({'reason': 'Another operation is running'}, 409)
        return
    try:
        job = create_job(root, request.get('action'), request.get('manifest'), fresh=True)
        with guard:
            state.update(active=True, action='planning-' + job['action'], task_ids=[],
                         started_at=datetime.now(timezone.utc).isoformat(), verification_mode='main',
                         planning_job_id=job['job_id'])

        def execute():
            try:
                run_job(root, job)
            finally:
                with guard:
                    state.update(active=False, action=None, task_ids=[], started_at=None,
                                 verification_mode=None, planning_job_id=None)
                operation.release()

        # Finish registering/starting the job before responding. A browser
        # disconnect cannot cancel the original run or cause a second invocation.
        threading.Thread(target=execute, name=job['job_id'], daemon=True).start()
    except Exception:
        with guard:
            state.update(active=False, action=None, task_ids=[], started_at=None,
                         verification_mode=None, planning_job_id=None)
        operation.release()
        raise
    handler.send(public_job(job), 202)


def cancel_planning(handler, root, request, guard, state):
    if set(request) - {'job_id'} or not request.get('job_id'):
        raise ValueError('job_id is required')
    job = request_cancel(root, str(request['job_id']))
    with guard:
        state['cancel_requested'] = True
    handler.send(public_job(job), 202)


def clear_mvg(handler, root, request, operation):
    if request:
        raise ValueError('Unexpected MVG clear request fields')
    if not operation.acquire(blocking=False):
        handler.send({'reason': 'Another operation is running'}, 409)
        return
    try:
        from _mvg_capability_recovery import clear
        before = _formal_adoption_digests(root)
        try:
            result = clear(root)
        except ValueError as exc:
            if str(exc) != 'capability_coordinator_busy':
                raise
            handler.send({'reason': 'Another operation is running'}, 409)
            return
        result = {**result, 'formal_git_adoptions_preserved': before == _formal_adoption_digests(root)}
        handler.send(result)
    finally:
        operation.release()


def _formal_adoption_digests(root):
    """Digest formal Git-governed B-route adoptions and cumulative MVG baselines.

    Covers catalog.v1.json, task-origins.v1.json and policy.v1.json (top-level records),
    plus the plans/, bindings/, commits/ and receipts/ record trees and docs/testing/mvg/*.json.
    """
    paths = []
    catalog = root / 'docs/planning/b-route'
    if catalog.is_dir():
        paths.extend(path for path in catalog.glob('*.json') if path.is_file())
        for name in ('plans', 'bindings', 'commits', 'receipts'):
            if (catalog / name).is_dir():
                paths.extend(path for path in (catalog / name).rglob('*.json') if path.is_file())
    baseline = root / 'docs/testing/mvg'
    if baseline.is_dir():
        paths.extend(path for path in baseline.glob('*.json') if path.is_file())
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}
