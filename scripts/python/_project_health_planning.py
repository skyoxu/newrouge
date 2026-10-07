"""Durable local planning jobs using the existing planners and real main checkout."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _planning_skill_common import atomic_json, file_sha, load_json, normalized_file_sha, repo_path
from _project_health_planning_inputs import (
    LOCAL_DERIVED_TOPOLOGY, MainCheckout, TOPOLOGY_ROOT, git, prepare_checkout, task_scope, validate_checkout,
    workspace_revision,
)

JOB_ROOT = Path('logs/ci/knowledge-planning')


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
        'recoverable_stage',
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


def create_job(root: Path, action: str, manifest: str | None = None) -> dict:
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
    # Continue the same persisted attempt after a disconnect/restart. Reusing a
    # terminal result also avoids silently paying for another identical review.
    pointer = load_json(root / JOB_ROOT / f'{action}-attempt.json', {})
    if pointer.get('job_id'):
        prior = read_job(root, pointer['job_id'])
        if prior.get('manifest') == manifest and (
                prior.get('revision') == revision or _planning_input_fresh(root, prior)):
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
    # The planner emits JSON with human-readable (possibly non-ASCII) reasons.
    # A redirected Windows stdout otherwise uses the active code page even
    # though the log file itself is opened as UTF-8, producing mixed/invalid
    # bytes when the log is read back below.
    child_env = {
        **os.environ,
        'PYTHONUNBUFFERED': '1',
        'PYTHONIOENCODING': 'utf-8',
    }
    with log.open('w', encoding='utf-8', newline='\n') as output:
        result = subprocess.run(command, cwd=checkout, stdout=output, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', env=child_env)
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
    from _project_health_mvg_versions import build_overview
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
        valid.append(str(label))
    return sorted(valid)


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
    invoked_stage: str | None = None
    try:
        job.update(status='running', message=f'Generating {action} from local workspace {job["revision"][:12]}')
        atomic_json(directory / 'job.json', job)
        derived_source = None
        if action == 'mvg' and job.get('checkout_job_id'):
            parent = read_job(root, job['checkout_job_id'])
            derived_source = execution_root(root, parent)
        prepare_checkout(root, checkout, job['revision'], derived_source=derived_source)
        validate_checkout(root, checkout, job['revision'])
        runner = runner_path()
        task_args = [value for tid in task_scope(checkout) for value in ('--task-id', tid)]
        run_id = job['job_id']
        script = 'plan_capabilities.py' if action == 'capability' else 'plan_mvg.py'
        stages = ['prepare', 'generate', 'review', 'align', 'apply'] if action == 'capability' else ['prepare', 'generate', 'review', 'validate', 'apply']
        for stage in stages[stages.index(job['stage']):]:
            invoked_stage = None
            validate_checkout(root, checkout, job['revision'])
            job['stage'] = stage
            atomic_json(directory / 'job.json', job)
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
            result = invoke(checkout, script, args, directory / f'{stage}.log')
            if result.get('status') in ('blocked', 'failed') or result.get('formal_applicable') is False:
                errors = result.get('errors') or result.get('formal_blockers') or []
                raise ValueError(result.get('reason') or '; '.join(str(error) for error in errors[:3]) or 'Planning stage blocked')
            if stage == 'review' and result.get('status') == 'no_valid_winner':
                raise ValueError('Capability review found no valid winner; inspect the retained review')
            if stage == 'align' and result.get('resolved') is not True:
                raise ValueError('Capability ID alignment needs explicit reviewed decisions; existing data is preserved')
        # Errors while building or publishing the read-only result are not an
        # invocation-stage interruption.  Keep that distinction so durable
        # model evidence is never mistaken for a safe Apply retry.
        invoked_stage = None
        stage = 'publish'
        validate_checkout(root, checkout, job['revision'])
        result = build_result(checkout, job)
        atomic_json(directory / 'result.json', result)
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
        job.update(status='completed', stage='complete', message=f'{action.title()} generated: {job["count"]} '
                   + ('capabilities' if action == 'capability' else 'flows') +
                   f' · local workspace {job["revision"][:12]} · local planning result')
        atomic_json(directory / 'job.json', job)
        atomic_json(root / JOB_ROOT / f'{action}-latest.json', {'job_id': job['job_id']})
    except Exception as exc:
        error = compact_error(str(exc))
        recovery_stage = (
            _capability_recovery_stage(root, checkout, job, stage)
            if invoked_stage is not None and invoked_stage == stage
            else None
        )
        if recovery_stage:
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
        atomic_json(directory / 'job.json', job)
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
