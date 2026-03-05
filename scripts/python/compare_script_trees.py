from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_TARGETS = ("scripts/sc", "scripts/python", "scripts/ci")
DEFAULT_EXCLUDES = ("**/__pycache__/**", "**/*.pyc")


@dataclass(frozen=True)
class CompareMaps:
    raw: dict[str, str]
    normalized: dict[str, str]


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_eol(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _matches_any_glob(path_posix: str, globs: Iterable[str]) -> bool:
    for pattern in globs:
        if fnmatch.fnmatch(path_posix, pattern):
            return True
    return False


def _collect_file_bytes(repo_root: Path, targets: list[str], excludes: list[str]) -> dict[str, bytes]:
    collected: dict[str, bytes] = {}
    for target in targets:
        target_dir = (repo_root / target).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            continue
        for file_path in sorted(target_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(repo_root).as_posix()
            if _matches_any_glob(rel, excludes):
                continue
            collected[rel] = file_path.read_bytes()
    return collected


def _build_maps(repo_root: Path, targets: list[str], excludes: list[str], normalize_eol: bool) -> CompareMaps:
    raw_files = _collect_file_bytes(repo_root=repo_root, targets=targets, excludes=excludes)
    raw_map: dict[str, str] = {}
    norm_map: dict[str, str] = {}
    for rel, raw in raw_files.items():
        raw_map[rel] = _hash_bytes(raw)
        norm_map[rel] = _hash_bytes(_normalize_eol(raw) if normalize_eol else raw)
    return CompareMaps(raw=raw_map, normalized=norm_map)


def _sorted_write(path: Path, items: Iterable[str]) -> None:
    path.write_text("\n".join(sorted(items)) + "\n", encoding="utf-8")


def _default_out_dir(repo_a: Path, repo_b: Path) -> Path:
    label = repo_b.name.strip() or "repo-b"
    return repo_a / "logs" / "ci" / _today() / f"scripts-compare-{label}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare script trees between two repositories with optional EOL normalization.",
    )
    parser.add_argument("--repo-a", default=".", help="Primary repository root (default: current directory).")
    parser.add_argument("--repo-b", required=True, help="Secondary repository root to compare against.")
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        help="Target directory relative to repo root. Repeatable. Defaults to scripts/sc, scripts/python, scripts/ci.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="excludes",
        help="Glob to exclude relative paths. Repeatable.",
    )
    parser.add_argument(
        "--normalize-eol",
        choices=("none", "lf"),
        default="lf",
        help="Comparison mode for content hash. 'lf' normalizes CRLF/CR to LF before hashing (default: lf).",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory for reports. Default: logs/ci/<date>/scripts-compare-<repo-b-name> under repo-a.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_a = Path(args.repo_a).resolve()
    repo_b = Path(args.repo_b).resolve()
    if not repo_a.exists() or not repo_a.is_dir():
        print(f"SCRIPTS_COMPARE status=fail reason=repo_a_not_found path={repo_a.as_posix()}")
        return 2
    if not repo_b.exists() or not repo_b.is_dir():
        print(f"SCRIPTS_COMPARE status=fail reason=repo_b_not_found path={repo_b.as_posix()}")
        return 2

    targets = args.targets if args.targets else list(DEFAULT_TARGETS)
    excludes = args.excludes if args.excludes else list(DEFAULT_EXCLUDES)
    normalize_eol = args.normalize_eol == "lf"

    maps_a = _build_maps(repo_root=repo_a, targets=targets, excludes=excludes, normalize_eol=normalize_eol)
    maps_b = _build_maps(repo_root=repo_b, targets=targets, excludes=excludes, normalize_eol=normalize_eol)

    keys_a = set(maps_a.raw.keys())
    keys_b = set(maps_b.raw.keys())
    only_a = sorted(keys_a - keys_b)
    only_b = sorted(keys_b - keys_a)
    common = sorted(keys_a & keys_b)

    raw_diff = sorted(rel for rel in common if maps_a.raw[rel] != maps_b.raw[rel])
    normalized_diff = sorted(rel for rel in common if maps_a.normalized[rel] != maps_b.normalized[rel])
    eol_only_diff = sorted(set(raw_diff) - set(normalized_diff))

    out_dir = Path(args.out_dir).resolve() if str(args.out_dir).strip() else _default_out_dir(repo_a=repo_a, repo_b=repo_b)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "status": "ok",
        "generated_at": _iso_now(),
        "repo_a": repo_a.as_posix(),
        "repo_b": repo_b.as_posix(),
        "targets": targets,
        "exclude_globs": excludes,
        "normalize_eol": args.normalize_eol,
        "counts": {
            "files_a": len(keys_a),
            "files_b": len(keys_b),
            "only_in_a": len(only_a),
            "only_in_b": len(only_b),
            "raw_diff": len(raw_diff),
            "normalized_diff": len(normalized_diff),
            "eol_only_diff": len(eol_only_diff),
        },
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _sorted_write(out_dir / "only_in_a.txt", only_a)
    _sorted_write(out_dir / "only_in_b.txt", only_b)
    _sorted_write(out_dir / "diff_raw.txt", raw_diff)
    _sorted_write(out_dir / "diff_normalized.txt", normalized_diff)
    _sorted_write(out_dir / "diff_eol_only.txt", eol_only_diff)

    print(
        "SCRIPTS_COMPARE status=ok "
        f"files_a={len(keys_a)} files_b={len(keys_b)} "
        f"only_a={len(only_a)} only_b={len(only_b)} "
        f"raw_diff={len(raw_diff)} normalized_diff={len(normalized_diff)} eol_only={len(eol_only_diff)} "
        f"out={out_dir.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
