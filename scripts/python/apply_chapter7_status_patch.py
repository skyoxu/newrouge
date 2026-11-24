#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

_STRICT_TASK_ID_RE = re.compile(r'^[1-9][0-9]*$', re.ASCII)


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


def _infer_repo_root_for_task_file(path: Path) -> Path | None:
    resolved = path.resolve()
    parts = [p.lower() for p in resolved.parts]
    for idx in range(len(parts) - 2):
        if parts[idx] == '.taskmaster' and parts[idx + 1] == 'tasks':
            return Path(*resolved.parts[:idx])
    return None


def _apply_operation(op: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
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
    inferred_root = _infer_repo_root_for_task_file(path)
    if inferred_root is not None:
        import _b_route_chapter6_gate as ch6_gate
        import _b_route_codec as codec

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
            try:
                if dry_run:
                    ch6_gate.validate_taskmaster_status_write_guard(
                        inferred_root,
                        task_id,
                        to_status,
                        sync_views=sync_views,
                        target_views=target_views,
                    )
                    payload = _load_json(path)
                    updated = (
                        _apply_master_status(payload, task_id=task_id, to_status=to_status)
                        if view == 'tasks_json'
                        else _apply_view_status(payload, task_id=task_id, to_status=to_status)
                    )
                    return {
                        'path': str(path.resolve()).replace('\\', '/'),
                        'view': view,
                        'task_id': task_id,
                        'task_ref': op.get('task_ref', ''),
                        'from_status': op.get('from_status', ''),
                        'to_status': to_status,
                        'applied': bool(updated),
                        'dry_run': True,
                        'guarded_write': True,
                        'definition_projection_preserved': True,
                        'runtime_verified': False,
                        'default_b_enabled': False,
                    }
                guarded = ch6_gate.write_taskmaster_status_guarded(
                    inferred_root,
                    task_id,
                    to_status,
                    sync_views=sync_views,
                    target_views=target_views,
                )
                return {
                    'path': str(path.resolve()).replace('\\', '/'),
                    'view': view,
                    'task_id': task_id,
                    'task_ref': op.get('task_ref', ''),
                    'from_status': op.get('from_status', ''),
                    'to_status': to_status,
                    'applied': bool(guarded.get('ok')),
                    'dry_run': dry_run,
                    'guarded_write': True,
                    'definition_projection_preserved': bool(guarded.get('definition_projection_preserved')),
                    'runtime_verified': False,
                    'default_b_enabled': False,
                }
            except (ch6_gate.Chapter6GateBlockedError, codec.CodecError, ValueError) as exc:
                if isinstance(exc, ch6_gate.Chapter6GateBlockedError):
                    reason_code = str(exc.gate_result.get('reason_code') or 'conflict')
                    diagnostics = list(exc.gate_result.get('diagnostics') or [])
                elif isinstance(exc, codec.CodecError):
                    diag = exc.diagnostic.to_dict()
                    reason_code = str(diag.get('reason_code') or 'conflict')
                    diagnostics = [diag]
                else:
                    reason_code = 'invalid_argument'
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


def apply_patch_contract(*, patch_path: Path, dry_run: bool) -> tuple[int, dict[str, Any]]:
    contract = _load_json(patch_path)
    operations = list(contract.get('operations') or [])
    results = [_apply_operation(item, dry_run=dry_run) for item in operations]
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
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out-json', default='')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args(argv)

    patch_path = Path(args.patch).resolve()
    if args.self_check:
        payload = {
            'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
            'action': 'apply-chapter7-status-patch',
            'status': 'ok',
            'dry_run': bool(args.dry_run),
            'patch': str(patch_path).replace('\\', '/'),
            'planned_steps': ['load-patch', 'apply-operations', 'emit-summary'],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    rc, payload = apply_patch_contract(patch_path=patch_path, dry_run=bool(args.dry_run))
    out = Path(args.out_json) if args.out_json else (patch_path.parent / ('apply-dry-run-summary.json' if args.dry_run else 'apply-summary.json'))
    _write_json(out, payload)
    print(f"CHAPTER7_STATUS_PATCH status={payload['status']} dry_run={str(bool(args.dry_run)).lower()} out={str(out).replace('\\', '/')}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
