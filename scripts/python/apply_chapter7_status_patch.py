#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from copy import deepcopy
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

_STRICT_TASK_ID_RE = re.compile(r'^[1-9][0-9]*$', re.ASCII)
_MATURE_DONE_STATUSES = frozenset({'done', 'completed', 'complete'})


def _today() -> str:
    return dt.date.today().strftime('%Y-%m-%d')


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def _apply_master_status(data: dict[str, Any], *, task_id: int, to_status: str) -> bool:
    for item in data.get('master', {}).get('tasks', []):
        if isinstance(item, dict) and item.get('id') == task_id:
            item['status'] = to_status
            return True
    return False


def _apply_view_status(data: list[dict[str, Any]], *, task_id: int, to_status: str) -> bool:
    for item in data:
        if isinstance(item, dict) and item.get('taskmaster_id') == task_id:
            item['status'] = to_status
            return True
    return False


def _infer_repo_root_for_task_file(path: Path, *, explicit_repo_root: Path | None = None) -> Path | None:
    if explicit_repo_root is not None:
        return explicit_repo_root.resolve()
    resolved = path.resolve()
    parts = [p.lower() for p in resolved.parts]
    for idx in range(len(parts) - 2):
        if parts[idx] == '.taskmaster' and parts[idx + 1] == 'tasks':
            return Path(*resolved.parts[:idx])
    for parent in resolved.parents:
        if (
            (parent / 'docs' / 'planning' / 'b-route').exists()
            or (parent / '.taskmaster' / 'tasks').exists()
            or (parent / '.git').exists()
        ):
            return parent
    return None


def _extract_status_from_doc(doc: Any, *, is_master: bool, task_id: int) -> str:
    if is_master:
        if not isinstance(doc, dict):
            raise ValueError('master tasks.json must be a JSON object')
        tasks = doc.get('master', {}).get('tasks', [])
        if not isinstance(tasks, list):
            raise ValueError('master.tasks must be a list')
        for mrow in tasks:
            if isinstance(mrow, dict) and mrow.get('id') == task_id:
                return str(mrow.get('status') or '').strip().lower()
        return ''
    if not isinstance(doc, list):
        raise ValueError('task view JSON must be a list')
    for vrow in doc:
        if isinstance(vrow, dict) and vrow.get('taskmaster_id') == task_id:
            return str(vrow.get('status') or '').strip().lower()
    return ''


def _check_all_triplet_mature_done(
    root_path: Path,
    *,
    task_id: int,
    target_path: Path,
    view: str,
    to_status: str,
) -> tuple[bool, str | None, str | None]:
    """Fail-closed check across all three triplet files plus target_path for mature done status."""
    import _b_route_codec as codec
    import _b_route_inventory as inventory
    import _b_route_task_resolver as task_resolver

    to_norm = to_status.strip().lower()
    candidates: list[tuple[str, Path, bool]] = [
        ('tasks_json', inventory.safe_input(root_path, task_resolver.TRIPLET['master'], allow_logs=False), True),
        ('tasks_back', inventory.safe_input(root_path, task_resolver.TRIPLET['back'], allow_logs=False), False),
        ('tasks_gameplay', inventory.safe_input(root_path, task_resolver.TRIPLET['gameplay'], allow_logs=False), False),
    ]
    seen_resolved = {p.resolve() for _v, p, _m in candidates}
    if target_path.exists() and target_path.resolve() not in seen_resolved:
        candidates.append((view or 'target', target_path.resolve(), view == 'tasks_json'))

    for view_label, fpath, is_master in candidates:
        if not fpath.is_file():
            continue
        inventory.no_reparse(fpath)
        doc = codec.strict_json_loads(fpath.read_bytes())
        live_status = _extract_status_from_doc(doc, is_master=is_master, task_id=task_id)
        if live_status in _MATURE_DONE_STATUSES and to_norm not in _MATURE_DONE_STATUSES:
            return True, live_status, view_label
    return False, None, None


def _apply_operation(
    op: dict[str, Any],
    *,
    dry_run: bool,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    path = Path(str(op.get('path') or ''))
    view = str(op.get('view') or '')
    to_status = str(op.get('to_status') or '')
    raw_tid_val = op.get('task_id')
    raw_tid = '' if raw_tid_val is None else str(raw_tid_val)
    if isinstance(raw_tid_val, bool) or _STRICT_TASK_ID_RE.fullmatch(raw_tid) is None:
        return {
            'path': str(path.resolve()).replace('\\', '/') if str(op.get('path') or '').strip() else '',
            'view': view,
            'task_id': raw_tid_val,
            'task_ref': op.get('task_ref', ''),
            'from_status': op.get('from_status', ''),
            'to_status': to_status,
            'applied': False,
            'dry_run': dry_run,
            'error': 'invalid_task_id',
            'runtime_verified': False,
            'default_b_enabled': False,
        }
    task_id = int(raw_tid)
    inferred_root = _infer_repo_root_for_task_file(path, explicit_repo_root=repo_root)
    if inferred_root is not None:
        import _b_route_chapter6_gate as ch6_gate
        import _b_route_codec as codec
        import _b_route_inventory as inventory
        import _b_route_operation_scope as op_scope
        import _b_route_protection as protection
        import _b_route_task_resolver as task_resolver

        presence = ch6_gate.detect_b_route_presence(inferred_root, task_id)
        if (
            presence.get('has_b_traces')
            or presence.get('capability_apply_pending')
            or presence.get('pending_journals')
            or presence.get('na_labels')
        ):
            if view == 'tasks_json':
                sync_views = False
                target_views: tuple[str, ...] = ('back', 'gameplay')
            elif view == 'tasks_back':
                sync_views = True
                target_views = ('back',)
            elif view == 'tasks_gameplay':
                sync_views = True
                target_views = ('gameplay',)
            else:
                sync_views = True
                target_views = ('back', 'gameplay')

            def _mature_done_blocked(found_status: str, found_view: str) -> dict[str, Any]:
                diag = codec.Diagnostic(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    str(task_id),
                    {'mature_done_status_preserved': True, 'return_stage': '3C'},
                    {
                        'current_status': found_status,
                        'attempted_to_status': to_status,
                        'view': found_view,
                        'return_stage': '3C',
                    },
                    '.taskmaster/tasks/tasks.json',
                ).to_dict()
                return {
                    'path': str(path.resolve()).replace('\\', '/'),
                    'view': view,
                    'task_id': task_id,
                    'task_ref': op.get('task_ref', ''),
                    'from_status': op.get('from_status', found_status),
                    'to_status': to_status,
                    'applied': False,
                    'dry_run': dry_run,
                    'guarded_write': True,
                    'done_status_preserved': True,
                    'error': 'cannot_clear_mature_done_status',
                    'reason_code': codec.ReasonCode.CONFLICT.value,
                    'diagnostics': [diag],
                    'runtime_verified': False,
                    'default_b_enabled': False,
                }

            try:
                # Validate status/view/B-route guards and compute scopes covering all 3 triplet views.
                root_path, tid, selected_views, base_scopes = ch6_gate.validate_taskmaster_status_write_guard(
                    inferred_root,
                    task_id,
                    to_status,
                    sync_views=sync_views,
                    target_views=target_views,
                )
                all_triplet_paths = [
                    task_resolver.TRIPLET['master'],
                    task_resolver.TRIPLET['back'],
                    task_resolver.TRIPLET['gameplay'],
                ]
                scopes = op_scope.resource_scopes(target_paths=all_triplet_paths, task_ids=[tid])
                env_path = os.environ.get(ch6_gate.ENV_LEASE_PATH)
                env_secret = os.environ.get(ch6_gate.ENV_LEASE_SECRET)
                has_lease_env = env_path is not None or env_secret is not None

                def _prepare_checked_update() -> dict[str, Any]:
                    is_mature, found_status, found_view = _check_all_triplet_mature_done(
                        root_path,
                        task_id=tid,
                        target_path=path,
                        view=view,
                        to_status=to_status,
                    )
                    if is_mature and found_status is not None and found_view is not None:
                        return {'blocked': _mature_done_blocked(found_status, found_view)}

                    master_rel = task_resolver.TRIPLET['master']
                    master_path = inventory.safe_input(root_path, master_rel, allow_logs=False)
                    inventory.no_reparse(master_path)
                    master_doc = codec.strict_json_loads(master_path.read_bytes())
                    tasks_list = ((master_doc.get('master') or {}).get('tasks')) if type(master_doc) is dict else None
                    if type(tasks_list) is not list:
                        raise codec.CodecError(
                            codec.Diagnostic(
                                codec.ReasonCode.INVALID_TYPE,
                                codec.Stage.CONTENT,
                                str(tid),
                                'master.tasks list in tasks.json',
                                type(tasks_list).__name__,
                                master_rel,
                            )
                        )
                    target_row = next((row for row in tasks_list if type(row) is dict and row.get('id') == tid), None)
                    if target_row is None:
                        raise codec.CodecError(
                            codec.Diagnostic(
                                codec.ReasonCode.UNKNOWN_ENTITY,
                                codec.Stage.CONTENT,
                                str(tid),
                                f'master task id {tid} in {master_rel}',
                                'not found',
                                master_rel,
                            )
                        )
                    before_proj = protection.task_definition_projection(target_row)
                    updated_master = deepcopy(master_doc)
                    updated_row = next(row for row in updated_master['master']['tasks'] if row.get('id') == tid)
                    updated_row['status'] = to_status
                    after_proj = protection.task_definition_projection(updated_row)
                    if codec.canonical_digest(before_proj) != codec.canonical_digest(after_proj):
                        raise codec.CodecError(
                            codec.Diagnostic(
                                codec.ReasonCode.CONFLICT,
                                codec.Stage.CONTENT,
                                str(tid),
                                'invariant task_definition_projection across status write',
                                'definition projection changed',
                                master_rel,
                            )
                        )
                    view_updates: list[tuple[Path, Any]] = []
                    if sync_views:
                        for view_name in selected_views:
                            vrel = task_resolver.TRIPLET[view_name]
                            vpath = inventory.safe_input(root_path, vrel, allow_logs=False)
                            if not vpath.is_file():
                                continue
                            inventory.no_reparse(vpath)
                            vdoc = codec.strict_json_loads(vpath.read_bytes())
                            if type(vdoc) is not list:
                                raise codec.CodecError(
                                    codec.Diagnostic(
                                        codec.ReasonCode.INVALID_TYPE,
                                        codec.Stage.CONTENT,
                                        str(tid),
                                        f'list in {vrel}',
                                        type(vdoc).__name__,
                                        vrel,
                                    )
                                )
                            v_updated = deepcopy(vdoc)
                            changed_v = False
                            for vrow in v_updated:
                                if type(vrow) is dict and vrow.get('taskmaster_id') == tid:
                                    vb = protection.task_definition_projection(vrow)
                                    vrow['status'] = to_status
                                    va = protection.task_definition_projection(vrow)
                                    if codec.canonical_digest(vb) != codec.canonical_digest(va):
                                        raise codec.CodecError(
                                            codec.Diagnostic(
                                                codec.ReasonCode.CONFLICT,
                                                codec.Stage.CONTENT,
                                                str(tid),
                                                'invariant view task_definition_projection',
                                                'view definition projection changed',
                                                vrel,
                                            )
                                        )
                                    changed_v = True
                            if changed_v:
                                view_updates.append((vpath, v_updated))
                    return {
                        'blocked': None,
                        'master_path': master_path,
                        'updated_master': updated_master,
                        'view_updates': view_updates,
                        'updated': True,
                    }

                def _commit_if_live(prepared: dict[str, Any]) -> None:
                    if dry_run or prepared.get('blocked') is not None:
                        return
                    ch6_gate._atomic_write_json(prepared['master_path'], prepared['updated_master'])
                    for vpath, vdoc in prepared['view_updates']:
                        ch6_gate._atomic_write_json(vpath, vdoc)

                if has_lease_env:
                    receipt = ch6_gate._verify_inherited_lease_receipt(
                        root_path,
                        tid,
                        str(env_path or ''),
                        str(env_secret or ''),
                    )
                    held_scopes = set(receipt['scope_ids'])
                    unheld_scopes = tuple(s for s in scopes if s not in held_scopes)
                    if not unheld_scopes:
                        prepared = _prepare_checked_update()
                        _commit_if_live(prepared)
                    else:
                        with op_scope.scope_guard(
                            root_path, unheld_scopes, prepare_under_lease=_prepare_checked_update
                        ) as prepared:
                            _commit_if_live(prepared)
                else:
                    with op_scope.scope_guard(
                        root_path, scopes, prepare_under_lease=_prepare_checked_update
                    ) as prepared:
                        _commit_if_live(prepared)

                if prepared.get('blocked') is not None:
                    return prepared['blocked']

                return {
                    'path': str(path.resolve()).replace('\\', '/'),
                    'view': view,
                    'task_id': task_id,
                    'task_ref': op.get('task_ref', ''),
                    'from_status': op.get('from_status', ''),
                    'to_status': to_status,
                    'applied': bool(prepared.get('updated')),
                    'dry_run': dry_run,
                    'guarded_write': True,
                    'definition_projection_preserved': True,
                    'runtime_verified': False,
                    'default_b_enabled': False,
                }
            except (ch6_gate.Chapter6GateBlockedError, codec.CodecError, ValueError, OSError, json.JSONDecodeError) as exc:
                if isinstance(exc, ch6_gate.Chapter6GateBlockedError):
                    reason_code = str(exc.gate_result.get('reason_code') or 'conflict')
                    diagnostics = list(exc.gate_result.get('diagnostics') or [])
                elif isinstance(exc, codec.CodecError):
                    diag = exc.diagnostic.to_dict()
                    reason_code = str(diag.get('reason_code') or 'conflict')
                    diagnostics = [diag]
                elif isinstance(exc, json.JSONDecodeError):
                    reason_code = codec.ReasonCode.INVALID_JSON.value
                    diagnostics = [{'reason_code': reason_code, 'actual': str(exc)}]
                elif isinstance(exc, OSError):
                    reason_code = codec.ReasonCode.READ_ERROR.value
                    diagnostics = [{'reason_code': reason_code, 'actual': str(exc)}]
                else:
                    reason_code = codec.ReasonCode.INVALID_ARGUMENT.value
                    diagnostics = [{'reason_code': reason_code, 'actual': str(exc)}]
                return {
                    'path': str(path.resolve()).replace('\\', '/'),
                    'view': view,
                    'task_id': task_id,
                    'task_ref': op.get('task_ref', ''),
                    'from_status': op.get('from_status', ''),
                    'to_status': to_status,
                    'applied': False,
                    'dry_run': dry_run,
                    'guarded_write': True,
                    'reason_code': reason_code,
                    'diagnostics': diagnostics,
                    'runtime_verified': False,
                    'default_b_enabled': False,
                }
    payload = _load_json(path)
    if view == 'tasks_json':
        updated = _apply_master_status(payload, task_id=task_id, to_status=to_status)
    else:
        updated = _apply_view_status(payload, task_id=task_id, to_status=to_status)
    if updated and not dry_run:
        _write_json(path, payload)
    return {
        'path': str(path.resolve()).replace('\\', '/'),
        'view': view,
        'task_id': task_id,
        'task_ref': op.get('task_ref', ''),
        'from_status': op.get('from_status', ''),
        'to_status': to_status,
        'applied': bool(updated),
        'dry_run': dry_run,
    }


def apply_patch_contract(
    *,
    patch_path: Path,
    dry_run: bool,
    repo_root: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    contract = _load_json(patch_path)
    operations = list(contract.get('operations') or [])
    results = [_apply_operation(item, dry_run=dry_run, repo_root=repo_root) for item in operations]
    failed = [item for item in results if not item['applied']]
    return (
        0 if not failed else 1,
        {
            'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
            'action': 'apply-chapter7-status-patch',
            'status': 'ok' if not failed else 'fail',
            'dry_run': dry_run,
            'patch_path': str(patch_path.resolve()).replace('\\', '/'),
            'operation_count': len(operations),
            'applied_count': sum(1 for item in results if item['applied']),
            'failed_count': len(failed),
            'results': results,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Apply or preview a Chapter 7 task status patch contract.')
    parser.add_argument('--patch', required=True)
    parser.add_argument('--repo-root', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out-json', default='')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args(argv)

    patch_path = Path(args.patch).resolve()
    explicit_root = Path(args.repo_root).resolve() if str(args.repo_root or '').strip() else None
    if args.self_check:
        payload = {
            'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
            'action': 'apply-chapter7-status-patch',
            'status': 'ok',
            'dry_run': bool(args.dry_run),
            'patch': str(patch_path).replace('\\', '/'),
            'repo_root': str(explicit_root).replace('\\', '/') if explicit_root else '',
            'planned_steps': ['load-patch', 'apply-operations', 'emit-summary'],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    rc, payload = apply_patch_contract(patch_path=patch_path, dry_run=bool(args.dry_run), repo_root=explicit_root)
    out = Path(args.out_json) if args.out_json else (patch_path.parent / ('apply-dry-run-summary.json' if args.dry_run else 'apply-summary.json'))
    _write_json(out, payload)
    print(f"CHAPTER7_STATUS_PATCH status={payload['status']} dry_run={str(bool(args.dry_run)).lower()} out={str(out).replace('\\', '/')}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
