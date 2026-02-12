from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


MANIFEST_BEGIN = "=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_BEGIN ==="
MANIFEST_END = "=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_END ==="


@dataclass(frozen=True)
class Part:
    rel_path: str
    title: str
    content: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _read_text_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _default_log_dir(repo_root: Path) -> Path:
    date = datetime.now(tz=timezone.utc).date().isoformat()
    return repo_root / "logs" / "ci" / date / "taskmaster-prd-parts"


def _write_log_json(log_dir: Path, file_name: str, payload: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / file_name
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return out


def _taskmaster_directives() -> str:
    # Chinese docs are allowed; keep code/scripts in English.
    return "\n".join(
        [
            "# Taskmaster 指令（M1 任务生成约束）",
            "",
            "你正在基于 NewRouge 的 SSoT 文档生成 M1（仅 Warrior）任务。",
            "",
            "## 生成范围（硬约束）",
            "- 仅生成 M1（Warrior 可玩纵切）相关任务。",
            "- 必须包含：难度选择 UI（全局设置、局内不可变），Act 结构模块化（可扩展，不硬编码成 3 Act 死规则）。",
            "- 不生成：三角色完整实现、云同步、多槽存档、出网/后端等 v1 非目标。",
            "",
            "## 任务结构（强制）",
            "- 任务按泳道拆分：Game.Core / Game.Godot / Tests / Docs&QA。",
            "- 每个任务必须引用至少 1 条 Accepted ADR（若无则视为拆分失败）。",
            "- 每个任务必须回链到：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md` 的对应条目。",
            "",
            "## 复杂度要求（强制）",
            "- 在任务描述中给出 `Complexity:`（1-10）。",
            "- 平均复杂度 <= 6；单任务最大复杂度 <= 8。",
            "- 如出现 >8，必须继续拆分该任务，直到满足约束。",
            "",
            "## 特别提醒（Gate-0）",
            "- ADR-0032（Save/Resume determinism）已是 Accepted，作为 M1 Gate-0：与存档/确定性相关的任务必须优先拆分并显式标注验收与取证（logs/**）。",
            "",
        ]
    ).rstrip() + "\n"


def _default_sources() -> list[tuple[str, str]]:
    # (source_path, part_file_name)
    return [
        ("project-context.md", "10-project-context.md"),
        ("docs/prd/PRD-NEWROUGE-GAME-0001.md", "20-prd.md"),
        ("docs/gdd/GDD-NEWROUGE-V1.md", "30-gdd.md"),
        ("docs/prd/SSOT-LOCKS-NEWROUGE-V1.md", "40-ssot-locks.md"),
        ("docs/prd/MECHANICS-EDGE-CASES-SSOT-NEWROUGE-V1.md", "50-mechanics-edge-cases.md"),
        (
            "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md",
            "60-m1-acceptance-checklist.md",
        ),
        ("docs/adr/ADR-0032-save-resume-determinism.md", "70-adr-0032.md"),
        ("docs/adr/ADR-0033-card-identity-and-forms.md", "71-adr-0033.md"),
    ]


def _build_parts(repo_root: Path, parts_dir_rel: str, include_directives: bool) -> list[Part]:
    parts_dir_rel = parts_dir_rel.replace("\\", "/").rstrip("/")
    parts: list[Part] = []

    if include_directives:
        rel_path = f"{parts_dir_rel}/00-taskmaster-directives.md"
        parts.append(Part(rel_path=rel_path, title="Taskmaster directives", content=_taskmaster_directives()))

    for src_rel, file_name in _default_sources():
        src_path = repo_root / src_rel
        if not src_path.exists():
            raise FileNotFoundError(f"Missing source: {src_rel}")
        rel_path = f"{parts_dir_rel}/{file_name}"
        parts.append(Part(rel_path=rel_path, title=src_rel, content=_read_text_utf8(src_path).rstrip() + "\n"))

    return parts


def write_parts_and_bundle(
    repo_root: Path,
    parts_dir_rel: str,
    index_rel: str,
    bundle_rel: str,
    include_directives: bool,
    log_dir: Path | None,
) -> dict:
    generated_at_utc = _utc_iso(datetime.now(tz=timezone.utc))
    parts = _build_parts(repo_root, parts_dir_rel, include_directives=include_directives)

    index_lines: list[str] = []
    written_parts: list[dict] = []
    for p in parts:
        out_path = repo_root / p.rel_path
        content_bytes = p.content.encode("utf-8")
        part_manifest = {
            "schema": "taskmaster-prd-part/v1",
            "generated_at_utc": generated_at_utc,
            "rel_path": p.rel_path,
            "title": p.title,
            "sha256": _sha256_bytes(content_bytes),
            "bytes": len(content_bytes),
        }
        payload = "\n".join(
            [
                MANIFEST_BEGIN,
                json.dumps(part_manifest, ensure_ascii=False, indent=2),
                MANIFEST_END,
                "",
                p.content.rstrip(),
                "",
            ]
        )
        _write_text_utf8(out_path, payload)
        index_lines.append(p.rel_path.replace("\\", "/"))
        written_parts.append(part_manifest)

    index_path = repo_root / index_rel
    _write_text_utf8(index_path, "\n".join(index_lines).rstrip() + "\n")

    bundle_parts: list[str] = []
    for rel in index_lines:
        bundle_parts.append(f"===== BEGIN PART: {rel} =====\n")
        bundle_parts.append(_read_text_utf8(repo_root / rel).rstrip() + "\n")
        bundle_parts.append(f"===== END PART: {rel} =====\n\n")

    bundle_text = "".join(bundle_parts).rstrip() + "\n"
    bundle_manifest = {
        "schema": "taskmaster-prd-bundle/v1",
        "generated_at_utc": generated_at_utc,
        "index": index_rel.replace("\\", "/"),
        "parts": written_parts,
        "bundle_sha256": _sha256_bytes(bundle_text.encode("utf-8")),
        "bundle_bytes": len(bundle_text.encode("utf-8")),
        "bundle_output": bundle_rel.replace("\\", "/"),
    }
    bundle_payload = "\n".join(
        [
            MANIFEST_BEGIN,
            json.dumps(bundle_manifest, ensure_ascii=False, indent=2),
            MANIFEST_END,
            "",
            bundle_text.rstrip(),
            "",
        ]
    )
    bundle_path = repo_root / bundle_rel
    _write_text_utf8(bundle_path, bundle_payload)

    result = {
        "ok": True,
        "generated_at_utc": generated_at_utc,
        "parts_dir": parts_dir_rel.replace("\\", "/"),
        "index": index_rel.replace("\\", "/"),
        "bundle": bundle_rel.replace("\\", "/"),
        "part_count": len(parts),
        "bundle_sha256": bundle_manifest["bundle_sha256"],
    }
    if log_dir is not None:
        _write_log_json(log_dir, "write.json", result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Split .taskmaster/docs/prd input into parts + bundle for Taskmaster.")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="Write parts, index, and bundle.")
    w.add_argument("--parts-dir", default=".taskmaster/docs/prd_parts")
    w.add_argument("--index", default=".taskmaster/docs/prd_parts.index")
    w.add_argument("--bundle", default=".taskmaster/docs/prd.bundle.txt")
    w.add_argument("--no-directives", action="store_true", help="Do not generate 00-taskmaster-directives.md.")
    w.add_argument("--log-dir", default=None)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = _repo_root()
    log_dir = Path(args.log_dir) if args.log_dir else _default_log_dir(repo_root)

    if args.cmd == "write":
        write_parts_and_bundle(
            repo_root,
            parts_dir_rel=args.parts_dir,
            index_rel=args.index,
            bundle_rel=args.bundle,
            include_directives=not args.no_directives,
            log_dir=log_dir,
        )
        return 0

    raise RuntimeError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())

