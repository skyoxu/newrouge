#!/usr/bin/env python3
"""Validate security audit JSONL lines and emit machine-readable summary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ("ts", "action", "reason", "target", "caller")


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_line(raw_line: str, line_no: int) -> list[dict[str, object]]:
    line = raw_line.strip()
    if line == "":
        return [{"line": line_no, "reason": "empty_line", "fix": "remove blank line or provide valid JSON object"}]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return [{"line": line_no, "reason": "invalid_json", "fix": "correct JSON syntax on this line"}]
    if not isinstance(payload, dict):
        return [{"line": line_no, "reason": "non_object_json", "fix": "use JSON object with required fields"}]
    issues: list[dict[str, object]] = []
    for field in REQUIRED_FIELDS:
        if not _is_non_empty_string(payload.get(field)):
            issues.append(
                {
                    "line": line_no,
                    "reason": f"missing_or_invalid_field:{field}",
                    "fix": f"set non-empty string field '{field}'",
                }
            )
    return issues


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    return path.read_text(encoding="utf-8", errors="strict").splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to security-audit.jsonl")
    parser.add_argument("--out", required=True, help="Path to output summary JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    issues: list[dict[str, object]] = []
    total_lines = 0
    try:
        lines = _read_lines(input_path)
        total_lines = len(lines)
        for idx, raw in enumerate(lines, start=1):
            issues.extend(_validate_line(raw, idx))
    except Exception as exc:
        issues.append({"line": 0, "reason": "input_read_error", "fix": str(exc)})

    payload = {
        "ok": len(issues) == 0,
        "total_lines": total_lines,
        "invalid_lines": len({int(x.get("line", 0)) for x in issues if int(x.get("line", 0)) > 0}),
        "required_fields": list(REQUIRED_FIELDS),
        "issues": issues,
        "input": str(input_path),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if payload["ok"]:
        print(f"VALIDATE_AUDIT_LOGS status=ok lines={total_lines} out={out_path}")
        return 0
    print(f"VALIDATE_AUDIT_LOGS status=fail issues={len(issues)} out={out_path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
