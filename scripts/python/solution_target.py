#!/usr/bin/env python3
"""Solution target resolution helpers."""

from __future__ import annotations

from pathlib import Path

from solution_resolver import resolve_solution_path, resolve_test_solution_path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _preferred_solution_names(resolved_root: Path) -> tuple[str, ...]:
    return (
        f"{resolved_root.name}.sln",
        f"{resolved_root.name.lower()}.sln",
        "Game.sln",
        "GodotGame.sln",
    )


def _discover_solutions(resolved_root: Path) -> list[Path]:
    return sorted(resolved_root.glob("*.sln"))


def _pick_by_preferred_name(candidates: list[Path], preferred_names: tuple[str, ...]) -> str | None:
    lowered = {candidate.name.lower(): candidate.name for candidate in candidates}
    for preferred in preferred_names:
        hit = lowered.get(preferred.lower())
        if hit:
            return hit
    return None


def _looks_like_test_solution(candidate: Path) -> bool:
    try:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    normalized = text.replace("\\\\", "\\").lower()
    return "game.core.tests" in normalized or "tests.godot" in normalized


def resolve_solution_arg(solution: str, *, root: Path | None = None) -> str:
    return resolve_solution_path(solution, repo_root=root or repo_root())


def resolve_test_solution_arg(solution: str, *, root: Path | None = None) -> str:
    return resolve_test_solution_path(solution, repo_root=root or repo_root())
