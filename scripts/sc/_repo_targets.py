from __future__ import annotations

import os
from pathlib import Path


def _prefer_named(candidates: list[Path], preferred_names: tuple[str, ...]) -> Path | None:
    if not candidates:
        return None
    by_name = {candidate.name.lower(): candidate for candidate in candidates}
    for preferred_name in preferred_names:
        matched = by_name.get(preferred_name.lower())
        if matched is not None:
            return matched
    return None


def resolve_solution_file(root: Path) -> Path | None:
    candidates = sorted(root.glob('*.sln'))
    if not candidates:
        return None
    # Keep Task1 deterministic: prefer the repository solution naming first.
    # Fallback to legacy names only when canonical names are missing.
    preferred = _prefer_named(candidates, (f'{root.name}.sln', 'NewRouge.sln', 'GodotGame.sln', 'Game.sln'))
    if preferred is not None:
        return preferred
    return candidates[0]


def resolve_build_target(root: Path) -> Path | None:
    csproj_candidates = sorted(root.glob('*.csproj'))
    if csproj_candidates:
        preferred = _prefer_named(csproj_candidates, (f'{root.name}.csproj', 'GodotGame.csproj', 'Game.csproj'))
        if preferred is not None:
            return preferred
        return csproj_candidates[0]
    return resolve_solution_file(root)


def resolve_acceptance_checklist(root: Path) -> Path | None:
    override = str(os.environ.get('TASK1_ACCEPTANCE_CHECKLIST') or '').strip()
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        if candidate.is_file():
            return candidate
    candidates = sorted((root / 'docs' / 'architecture' / 'overlays').glob('**/08/ACCEPTANCE_CHECKLIST.md'))
    if not candidates:
        return None
    return candidates[0]
