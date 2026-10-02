"""Asynchronous planning operations sharing the local host's operation lock."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from _project_health_planning import create_job, generated_view, public_job, run_job


def start_planning(handler, root, request, operation, guard, state):
    if set(request) - {'action', 'manifest'}:
        raise ValueError('Unexpected planning request fields')
    if not operation.acquire(blocking=False):
        handler.send({'reason': 'Another operation is running'}, 409)
        return
    try:
        job = create_job(root, request.get('action'), request.get('manifest'))
        if job['status'] == 'completed':
            generated_view(root, job['action'])
            handler.send(public_job(job))
            operation.release()
            return
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
