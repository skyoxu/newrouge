#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate overlay execution readiness for the current project (manifest-driven).

Checks:
1) overlay manifest exists and required keys are present.
2) Manifest-referenced files exist on disk.
3) Markdown front matter has PRD-ID aligned (for files that declare front matter).
4) Concrete backtick path references resolve on disk.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

MANIFEST_FILE_NAME = "overlay-manifest.json"
MANIFEST_KEYS = ("index", "feature", "contracts", "testing", "observability", "acceptance")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def today_str() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def ci_out_dir() -> Path:
    out = repo_root() / "logs" / "ci" / today_str() / "overlay-lint"
    out.mkdir(parents=True, exist_ok=True)
    return out


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n") + "\n", encoding="utf-8", newline="\n")


def parse_front_matter(md: str) -> dict[str, Any]:
    lines = md.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}

    block = lines[1:end_idx]
    result: dict[str, Any] = {}
    current_key: str | None = None

    for raw in block:
        line = raw.rstrip()
        if not line.strip():
            continue

        if re.match(r"^\s+-\s+", line) and current_key:
            result.setdefault(current_key, [])
            if isinstance(result[current_key], list):
                result[current_key].append(re.sub(r"^\s+-\s+", "", line).strip())
            continue

        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not m:
            continue

        key = m.group(1).strip()
        value = m.group(2).strip()
        current_key = key

        if value.startswith("[") and value.endswith("]"):
            body = value[1:-1].strip()
            if not body:
                result[key] = []
            else:
                result[key] = [x.strip() for x in body.split(",") if x.strip()]
        elif value == "":
            result[key] = []
        else:
            result[key] = value

    return result


def has_markdown_heading(md: str, heading: str) -> bool:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    return re.search(pattern, md, flags=re.MULTILINE) is not None


def extract_backtick_paths(md: str) -> list[str]:
    refs = re.findall(r"`([^`]+)`", md)
    out: list[str] = []
    for ref in refs:
        txt = ref.strip()
        if not txt:
            continue
        if txt.startswith("py -3 ") or txt.startswith("dotnet "):
            continue
        if "/" not in txt and "\\" not in txt:
            continue
        out.append(txt.replace("\\", "/"))
    return out


def should_check_path(path: str) -> bool:
    if "<" in path or ">" in path:
        return False
    if "*" in path or "?" in path:
        return False
    if path.startswith("logs/"):
        return False
    prefixes = (
        "docs/",
        "scripts/",
        ".taskmaster/",
    )
    return path.startswith(prefixes)


def validate_file_paths(root: Path, md_text: str, rel: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    refs = extract_backtick_paths(md_text)

    for ref in refs:
        if not should_check_path(ref):
            continue
        p = root / ref
        if not p.exists():
            errors.append(f"{rel}: missing referenced path: {ref}")

    if not refs:
        warnings.append(f"{rel}: no backtick references found")

    return errors, warnings


def _resolve_overlay_file(base_rel: str, value: object) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("Manifest contains empty file path.")
    if raw.startswith("docs/"):
        return raw
    return f"{base_rel}/{raw.lstrip('./')}"


def validate_overlay(prd_id: str, overlay_dir: Path) -> dict[str, Any]:
    root = repo_root()
    errors: list[str] = []
    warnings: list[str] = []

    overlay_dir_rel = str(overlay_dir.relative_to(root)).replace("\\", "/")
    manifest_path = overlay_dir / MANIFEST_FILE_NAME
    manifest_rel = str(manifest_path.relative_to(root)).replace("\\", "/")
    if not manifest_path.exists():
        errors.append(f"missing required overlay manifest: {manifest_rel}")
        return {
            "prd_id": prd_id,
            "overlay_dir": overlay_dir_rel,
            "manifest": manifest_rel,
            "errors": errors,
            "warnings": warnings,
            "status": "fail",
        }

    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        errors.append(f"manifest is not a JSON object: {manifest_rel}")
        return {
            "prd_id": prd_id,
            "overlay_dir": overlay_dir_rel,
            "manifest": manifest_rel,
            "errors": errors,
            "warnings": warnings,
            "status": "fail",
        }

    manifest_prd = str(manifest.get("prd_id", "")).strip()
    if manifest_prd and manifest_prd != prd_id:
        errors.append(f"manifest prd_id mismatch: expected {prd_id}, got {manifest_prd}")

    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append(f"manifest missing 'files' object: {manifest_rel}")
        files = {}

    missing_keys = [k for k in MANIFEST_KEYS if k not in files]
    if missing_keys:
        errors.append(f"manifest missing keys: {missing_keys}")

    resolved_files: list[str] = []
    for key in MANIFEST_KEYS:
        if key not in files:
            continue
        try:
            resolved_files.append(_resolve_overlay_file(overlay_dir_rel, files.get(key)))
        except ValueError as exc:
            errors.append(f"manifest key '{key}' invalid: {exc}")

    for rel in resolved_files:
        p = root / rel
        if not p.exists():
            errors.append(f"missing manifest-referenced file: {rel}")
            continue

        text = read_text(p)
        fm = parse_front_matter(text)
        if fm:
            if str(fm.get("PRD-ID", "")).strip() and str(fm.get("PRD-ID", "")).strip() != prd_id:
                errors.append(f"{rel}: PRD-ID mismatch, expected {prd_id}")
            if not str(fm.get("Title", "")).strip():
                warnings.append(f"{rel}: front matter missing Title")
            if rel.endswith(".md") and "_index.md" not in rel and not fm.get("ADR-Refs"):
                warnings.append(f"{rel}: front matter missing ADR-Refs")
        elif rel.endswith(".md") and not rel.endswith("ACCEPTANCE_CHECKLIST.md"):
            warnings.append(f"{rel}: missing front matter block")

        e2, w2 = validate_file_paths(root, text, rel)
        errors.extend(e2)
        warnings.extend(w2)

    index_rel = next((x for x in resolved_files if x.endswith("/_index.md") or x.endswith("_index.md")), "")
    if index_rel and (root / index_rel).exists():
        index_text = read_text(root / index_rel)
        for rel in resolved_files:
            if rel == index_rel:
                continue
            if Path(rel).name not in index_text:
                warnings.append(f"{index_rel}: does not mention {Path(rel).name}")

    return {
        "prd_id": prd_id,
        "overlay_dir": overlay_dir_rel,
        "manifest": manifest_rel,
        "resolved_files": resolved_files,
        "errors": errors,
        "warnings": warnings,
        "status": "ok" if not errors else "fail",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate overlay execution readiness (manifest-driven).")
    ap.add_argument("--prd-id", default="PRD-NEWROUGE-GAME-0001")
    ap.add_argument("--overlay-dir", default="")
    args = ap.parse_args()

    root = repo_root()
    overlay_dir = (
        (root / args.overlay_dir)
        if args.overlay_dir
        else (root / "docs" / "architecture" / "overlays" / args.prd_id / "08")
    )

    report = validate_overlay(args.prd_id, overlay_dir)
    out_dir = ci_out_dir()

    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"

    write_json(report_json, report)

    md_lines = [
        "# Overlay Execution Validation",
        "",
        f"- prd_id: {report['prd_id']}",
        f"- overlay_dir: {report['overlay_dir']}",
        f"- status: {report['status']}",
        f"- errors: {len(report['errors'])}",
        f"- warnings: {len(report['warnings'])}",
        "",
    ]

    if report["errors"]:
        md_lines.append("## Errors")
        for err in report["errors"]:
            md_lines.append(f"- {err}")
        md_lines.append("")

    if report["warnings"]:
        md_lines.append("## Warnings")
        for w in report["warnings"]:
            md_lines.append(f"- {w}")
        md_lines.append("")

    write_text(report_md, "\n".join(md_lines).strip())

    print(
        f"OVERLAY_EXEC_VALIDATION status={report['status']} errors={len(report['errors'])} "
        f"warnings={len(report['warnings'])} out={out_dir}"
    )

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
