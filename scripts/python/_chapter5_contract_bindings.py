"""Bind event references to declarations and their local contract type dependencies."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path


def resolve_contract(root: Path, ref: str, *, sources: Mapping[str, bytes] | None = None) -> dict | None:
    """Resolve from disk, or exclusively from an already read source collection.

    The sources seam preserves read_text's universal-newline text identity. Its
    caller owns path containment and raw-byte verification before parsing.
    """
    if sources is None:
        files = {p: p.read_text(encoding='utf-8')
                 for p in sorted((root / 'Game.Core/Contracts').rglob('*.cs'))}
    else:
        files = {root / path: data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                 for path, data in sorted(sources.items())}
    direct = root / ref
    seeds = {p for p, text in files.items() if ref in text}
    if ref.startswith('Game.Core/Contracts/') and direct in files:
        seeds = {direct}
    if not seeds:
        return None
    primary = sorted(seeds)[0]
    # Follow the particular event constant, not every member of EventTypes.
    symbols = set()
    for p in seeds:
        text = files[p]
        owners = re.findall(r'\b(?:class|struct)\s+(\w+)', text)
        members = re.findall(r'\bconst\s+string\s+(\w+)\s*=\s*"' + re.escape(ref) + r'"', text)
        symbols.update(owner + '.' + member for owner in owners for member in members)
    bound = set(seeds)
    for p, text in files.items():
        if any(re.search(r'\b' + re.escape(symbol) + r'\b', text) for symbol in symbols):
            bound.add(p)
    declarations = {}
    for p, text in files.items():
        for name in re.findall(r'\b(?:record(?:\s+(?:class|struct))?|class|struct|enum|interface)\s+(\w+)', text):
            declarations.setdefault(name, set()).add(p)
    # Traverse referenced DTOs and enums without traversing unrelated event constants.
    pending = list(bound)
    while pending:
        p = pending.pop()
        text = files[p]
        if p.name == 'EventTypes.cs' or (p in seeds and symbols):
            continue
        for token in set(re.findall(r'\b[A-Za-z_]\w*\b', text)):
            for dependency in declarations.get(token, set()):
                if dependency not in bound:
                    bound.add(dependency)
                    pending.append(dependency)
    def digest(text):
        return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
    return {
        'ref': ref,
        'path': primary.relative_to(root).as_posix(),
        'line': next((i for i, line in enumerate(files[primary].splitlines(), 1) if ref in line), None),
        'sha256': digest(files[primary]),
        'bindings': [{'path': p.relative_to(root).as_posix(), 'sha256': digest(files[p])}
                     for p in sorted(bound)],
    }
