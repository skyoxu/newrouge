"""Durable local planning jobs using the existing planners and real main checkout."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _planning_skill_common import atomic_json, file_sha, load_json, repo_path
from _project_health_planning_inputs import (
    MainCheckout, TOPOLOGY_ROOT, committed_text, git, main_revision, prepare_checkout,
    require_main, task_scope, validate_checkout,
)

JOB_ROOT = Path('logs/ci/knowledge-planning')


def compact_error(value: str) -> str:
    try:
        payload = json.loads(value)
        if isinstance(payload, dict) and payload.get('reason'):
            value = str(payload['reason'])
    except (ValueError, TypeError):
        pass
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    return ' '.join((lines[-1:] or ['Planning failed']))[:320]


def job_path(root: Path, job_id: str) -> Path:
    if not re.fullmatch(r'planning-[0-9a-f]{32}', job_id):
        raise ValueError('Invalid planning job ID')
    return repo_path(root, (JOB_ROOT / job_id / 'job.json').as_posix())


def public_job(job: dict) -> dict:
    return {key: job.get(key) for key in ('job_id', 'action', 'status', 'stage', 'revision', 'message', 'count')}


def read_job(root: Path, job_id: str) -> dict:
    result = load_json(job_path(root, job_id), {})
    if result.get('job_id') != job_id:
        raise ValueError('Planning job is unavailable')
    return result


def selected_result(root: Path, action: str) -> dict | None:
    pointer = load_json(root / JOB_ROOT / f'{action}-latest.json', {})
    if not pointer.get('job_id'):
        return None
    job = read_job(root, pointer['job_id'])
    if job['status'] != 'completed' or job['revision'] != main_revision(root):
        return None
    if file_sha(job_path(root, job['job_id']).parent / 'result.json') != job.get('result_sha256'):
        raise ValueError('Generated planning result identity changed')
    return job


def execution_root(root: Path, job: dict) -> Path:
    checkout_id = job.get('checkout_job_id') or job['job_id']
    return job_path(root, checkout_id).parent / 'checkout'


def create_job(root: Path, action: str, manifest: str | None = None) -> dict:
    if action not in ('capability', 'mvg'):
        raise ValueError('Unknown planning action')
    revision = main_revision(root)
    if action == 'mvg':
        manifest = manifest or 'docs/testing/mvg/m1-full.json'
        if not re.fullmatch(r'docs/testing/mvg/[A-Za-z0-9][A-Za-z0-9_.-]*\.json', manifest):
            raise ValueError('Choose a repository MVG manifest')
        existing = set(git(root, 'ls-tree', '-r', '--name-only', revision).splitlines())
        if manifest not in existing and manifest != 'docs/testing/mvg/m1-full.json':
            prior = selected_result(root, 'mvg')
            if not prior or prior.get('manifest') != manifest:
                raise ValueError('Selected manifest is not in committed main or an owned generated result')
    # Continue the same persisted attempt after a disconnect/restart. Reusing a
    # terminal result also avoids silently paying for another identical review.
    pointer = load_json(root / JOB_ROOT / f'{action}-attempt.json', {})
    if pointer.get('job_id'):
        prior = read_job(root, pointer['job_id'])
        if prior['revision'] == revision and prior.get('manifest') == manifest:
            return prior
    job_id = 'planning-' + uuid.uuid4().hex
    job = {'schema_version': 'newrouge.knowledge-planning-job.v1', 'job_id': job_id,
           'action': action, 'revision': revision, 'manifest': manifest, 'stage': 'prepare',
           'status': 'queued', 'created_at': datetime.now(timezone.utc).isoformat(),
           'message': f'Queued {action} generation from main {revision[:12]}'}
    if action == 'mvg':
        capability = selected_result(root, 'capability')
        if capability:
            job['checkout_job_id'] = capability['job_id']
    atomic_json(job_path(root, job_id), job)
    atomic_json(root / JOB_ROOT / f'{action}-attempt.json', {'job_id': job_id})
    return job


def invoke(checkout: Path, script: str, arguments: list[str], log: Path) -> dict:
    command = [sys.executable, str(Path(__file__).with_name(script)), '--repo-root', str(checkout), *arguments]
    # Planners retain their original per-attempt/time gates and process cleanup.
    # No outer timeout abandons a still-active model child or resets its budget.
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=checkout, stdout=output, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    text = log.read_text(encoding='utf-8')
    if result.returncode:
        raise ValueError(compact_error(text))
    try:
        # Current planners print one complete JSON result, not log chatter.
        return json.loads(text)
    except ValueError as exc:
        raise ValueError('Planning stage returned an invalid result') from exc


def runner_path() -> Path:
    configured = os.environ.get('SC_KNOWLEDGE_PLANNING_RUNNER')
    if configured:
        return Path(configured).resolve()
    if os.environ.get('OPENAI_API_KEY'):
        return Path(__file__).with_name('openai_isolated_model_runner.py')
    import shutil
    if shutil.which('copilot'):
        return Path(__file__).with_name('copilot_isolated_model_runner.py')
    raise ValueError('Configure OPENAI_API_KEY or an authenticated Copilot CLI for planning')


def mvg_backend() -> str:
    backend = os.environ.get('SC_KNOWLEDGE_MVG_BACKEND')
    if not backend:
        backend = 'openai-api' if os.environ.get('OPENAI_API_KEY') else 'copilot-cli'
    if backend not in ('codex-cli', 'openai-api', 'copilot-cli'):
        raise ValueError('Unsupported MVG planning backend')
    return backend


def build_result(checkout: Path, job: dict) -> dict:
    from _project_health_tasks import task_details
    from _semantic_topology import build_topology_view
    from _project_health_mvg_versions import build_overview
    extra = [job['manifest']] if job.get('manifest') else []
    reader = MainCheckout(checkout, job['revision'], extra)
    details = task_details(reader)
    documents = [load_json(checkout / TOPOLOGY_ROOT / name, {}) for name in (
        'topology-manifest.v1.json', 'source-blocks.v1.json', 'semantic-requirements.v1.json',
        'capabilities.v1.json', 'topology-edges.v1.json')]
    topology = build_topology_view({'kind': 'main', 'revision': job['revision'],
        'authority_ref': 'refs/heads/main'}, *documents, details, [])
    provenance = {'planning_result': True, 'planning_job_id': job['job_id'],
                  'publication_state': 'local_generated', 'runtime_verified': False}
    topology.update(provenance)
    topology['status'] = 'generated_from_main'
    overview = build_overview(reader, details, topology, {'nodes': {}})
    overview.update(provenance)
    for manifest in overview['manifests']:
        if manifest['path'] == job.get('manifest'):
            manifest.update(provenance)
            manifest['evidence'] = {'status': 'not_verified', 'reason': 'Generated planning scope; runtime not executed'}
    return {'topology': topology, 'overview': overview}


def run_job(root: Path, job: dict) -> dict:
    directory = job_path(root, job['job_id']).parent
    checkout = execution_root(root, job)
    stage, action = job['stage'], job['action']
    try:
        job.update(status='running', message=f'Generating {action} from main {job["revision"][:12]}')
        atomic_json(directory / 'job.json', job)
        prepare_checkout(root, checkout, job['revision'])
        validate_checkout(root, checkout, job['revision'])
        runner = runner_path()
        task_args = [value for tid in task_scope(checkout) for value in ('--task-id', tid)]
        run_id = job['job_id']
        script = 'plan_capabilities.py' if action == 'capability' else 'plan_mvg.py'
        stages = ['prepare', 'generate', 'review', 'preview-alignment', 'apply'] if action == 'capability' else ['prepare', 'generate', 'review', 'validate', 'apply']
        for stage in stages[stages.index(job['stage']):]:
            validate_checkout(root, checkout, job['revision'])
            job['stage'] = stage
            atomic_json(directory / 'job.json', job)
            args = [stage, '--run-id', run_id]
            if stage == 'prepare':
                args += task_args
                if action == 'mvg':
                    args += ['--capabilities', f'{TOPOLOGY_ROOT}/capabilities.v1.json', '--manifest', job['manifest']]
            elif stage in ('generate', 'review'):
                if action == 'mvg' and stage == 'generate':
                    args += ['--llm-backend', mvg_backend()]
                else:
                    args += ['--runner', str(runner)]
            elif stage == 'apply':
                args += ['--confirm']
            run_state = checkout / 'logs/ci' / ('capability-planning' if action == 'capability' else 'mvg-planning') / run_id / 'run.json'
            if stage == 'prepare' and run_state.is_file():
                continue
            result = invoke(checkout, script, args, directory / f'{stage}.log')
            if result.get('status') in ('blocked', 'failed') or result.get('formal_applicable') is False:
                errors = result.get('errors') or result.get('formal_blockers') or []
                raise ValueError(result.get('reason') or '; '.join(str(error) for error in errors[:3]) or 'Planning stage blocked')
            if stage == 'review' and result.get('status') == 'no_valid_winner':
                raise ValueError('Capability review found no valid winner; inspect the retained review')
            if stage == 'preview-alignment' and result.get('resolved') is not True:
                raise ValueError('Capability ID alignment needs explicit reviewed decisions; existing data is preserved')
        validate_checkout(root, checkout, job['revision'])
        result = build_result(checkout, job)
        atomic_json(directory / 'result.json', result)
        owned = {path: file_sha(checkout / path) for path in git(checkout, 'diff', '--name-only', 'HEAD').splitlines()}
        job['output_hashes'] = owned
        job['result_sha256'] = file_sha(directory / 'result.json')
        job['count'] = len(result['topology']['nodes']['capabilities']) if action == 'capability' else len(next(
            row['flows'] for row in result['overview']['manifests'] if row['path'] == job['manifest']))
        job.update(status='completed', stage='complete', message=f'{action.title()} generated: {job["count"]} '
                   + ('capabilities' if action == 'capability' else 'flows') + f' · main {job["revision"][:12]} · local planning result')
        atomic_json(directory / 'job.json', job)
        require_main(root, job['revision'])
        atomic_json(root / JOB_ROOT / f'{action}-latest.json', {'job_id': job['job_id']})
    except Exception as exc:
        job.update(status='failed', message=f'{action.title()} failed ({stage}): {compact_error(str(exc))}')
        atomic_json(directory / 'job.json', job)
    return public_job(job)


def generated_view(root: Path, action: str) -> dict | None:
    job = selected_result(root, action)
    if not job:
        return None
    checkout = execution_root(root, job)
    validate_checkout(root, checkout, job['revision'])
    for path, expected in job.get('output_hashes', {}).items():
        if file_sha(repo_path(checkout, path)) != expected:
            raise ValueError('Generated planning output changed; retained main data is preserved')
    result = load_json(job_path(root, job['job_id']).parent / 'result.json')
    return result['topology' if action == 'capability' else 'overview']


def planning_source(root: Path, job_id: str, path: str) -> dict:
    job = read_job(root, job_id)
    if job['action'] != 'capability' or selected_result(root, 'capability') != job:
        raise ValueError('Generated topology changed; refresh before reading source')
    topology = generated_view(root, 'capability')
    if path not in {row['source_path'] for row in topology['nodes']['source_blocks']}:
        raise ValueError('Source is not in the generated topology')
    return committed_text(root, job['revision'], path)
