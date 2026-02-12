"""Update overlay references for a set of M1 core tasks.

English-only script per repo rules.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Set


def parse_ids(spec: str) -> Set[int]:
    out: Set[int] = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            lo, hi = part.split('-', 1)
            lo_i = int(lo.strip())
            hi_i = int(hi.strip())
            for i in range(min(lo_i, hi_i), max(lo_i, hi_i) + 1):
                out.add(i)
        else:
            out.add(int(part))
    return out


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def update_master(tasks_path: Path, ids: Set[int], overlay_path: str) -> int:
    master = load_json(tasks_path)
    updated = 0
    for t in master['master']['tasks']:
        try:
            tid = int(t.get('id'))
        except Exception:
            continue
        if tid in ids:
            if t.get('overlay') != overlay_path:
                t['overlay'] = overlay_path
                updated += 1
    write_json(tasks_path, master)
    return updated


def update_view(view_path: Path, ids: Set[int], overlay_refs: Iterable[str]) -> int:
    data = load_json(view_path)
    updated = 0
    for t in data:
        tm_id = t.get('taskmaster_id')
        if tm_id is None:
            continue
        if int(tm_id) in ids:
            if t.get('overlay_refs') != list(overlay_refs):
                t['overlay_refs'] = list(overlay_refs)
                updated += 1
    write_json(view_path, data)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.', help='Repo root')
    parser.add_argument('--ids', default='1-52', help='Task id list, e.g. 1-52,60,61')
    parser.add_argument('--overlay-root', default='docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08')
    parser.add_argument('--overlay-main', default='08-Feature-Slice-M1-Warrior.md')
    args = parser.parse_args()

    repo = Path(args.repo)
    ids = parse_ids(args.ids)

    overlay_root = args.overlay_root.replace('\\', '/').rstrip('/')
    overlay_main = f"{overlay_root}/{args.overlay_main}"
    overlay_refs = [
        f"{overlay_root}/_index.md",
        f"{overlay_root}/08-Feature-Slice-M1-Warrior.md",
        f"{overlay_root}/ACCEPTANCE_CHECKLIST.md",
        f"{overlay_root}/08-Contracts-M1.md",
        f"{overlay_root}/08-Testing-M1.md",
        f"{overlay_root}/08-Observability-M1.md",
    ]

    tasks_path = repo / '.taskmaster' / 'tasks' / 'tasks.json'
    gameplay_path = repo / '.taskmaster' / 'tasks' / 'tasks_gameplay.json'
    back_path = repo / '.taskmaster' / 'tasks' / 'tasks_back.json'

    u1 = update_master(tasks_path, ids, overlay_main)
    u2 = update_view(gameplay_path, ids, overlay_refs)
    u3 = update_view(back_path, ids, overlay_refs)

    print(f"Updated tasks.json overlay: {u1}")
    print(f"Updated tasks_gameplay overlay_refs: {u2}")
    print(f"Updated tasks_back overlay_refs: {u3}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
