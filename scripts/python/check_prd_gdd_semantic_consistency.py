#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hard semantic consistency gate for PRD/GDD.

Checks:
1) Required rule clauses exist in core files (PRD + GDD)
2) Contradictory clauses are absent in PRD/GDD corpus

Output:
  logs/ci/<YYYY-MM-DD>/prd-gdd-consistency/summary.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


CORE_FILES = [
    "docs/prd/PRD-NEWROUGE-GAME-0001.md",
    "docs/gdd/GDD-NEWROUGE-V1.md",
]

SCAN_GLOBS = [
    "docs/prd/*.md",
    "docs/gdd/*.md",
]

NEGATION_TOKENS = ["不", "禁", "无", "不得", "永不", "禁止"]

CONTEXT_NEGATION_HINTS = [
    "锁定",
    "禁用",
    "禁词",
    "反例",
    "误解",
    "不得出现",
    "避免",
    "例如",
    "示例",
    "检查",
    "清单",
    "风险",
]

WINDOW_NEGATIVE_HINTS = [
    "不允许",
    "禁止",
    "禁用",
    "避开",
    "反例",
    "错误处理",
    "高风险缺陷",
    "会诱导",
    "以下语境",
    "文档自检",
    "仅用于",
    "扫描",
]

REQUIRED_RULES = {
    "shop_no_upgrade": [
        r"商店.*不.*升级",
        r"商店.*永不.*升级",
        r"商店.*禁止.*升级",
        r"商店.*不提供升级",
    ],
    "no_mid_combat_save": [
        r"战斗.*不保存中间态",
        r"战斗中.*绝不保存.*中间态",
        r"战斗.*中间态.*不保存",
    ],
    "upgrade_only_rest_event": [
        r"升级.*(仅|只).*(休整|Rest).*(事件|特殊事件)",
        r"(休整|Rest).*(事件|特殊事件).*升级",
        r"升级发生.*(休整|Rest).*(事件|特殊事件)",
    ],
    "card_id_immutable": [
        r"card_id.*(不变|不改变|保持不变)",
        r"升级.*不改变.*card_id",
    ],
    "difficulty_not_bound_talent": [
        r"难度.*不.*天赋树.*强绑定",
        r"难度.*与天赋树.*不.*绑定",
        r"天赋树.*不与难度.*强绑定",
    ],
}


def _today_str() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def _to_posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_scope_files(repo_root: Path) -> list[Path]:
    files: set[Path] = set()
    for glob_pattern in SCAN_GLOBS:
        for item in repo_root.glob(glob_pattern):
            if item.is_file():
                files.add(item.resolve())
    return sorted(files, key=lambda path: _to_posix(path).lower())


def _line_has_negation(line: str) -> bool:
    return any(token in line for token in NEGATION_TOKENS)


def _line_is_contextual_negative(line: str) -> bool:
    if _line_has_negation(line):
        return True
    return any(hint in line for hint in CONTEXT_NEGATION_HINTS)


def _window_has_negative_context(lines: list[str], index: int) -> bool:
    start = max(0, index - 3)
    end = min(len(lines), index + 4)
    context = "\n".join(lines[start:end])
    return any(hint in context for hint in WINDOW_NEGATIVE_HINTS)


def _required_rules_check(repo_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for rel_path in CORE_FILES:
        file_path = (repo_root / rel_path).resolve()
        if not file_path.exists():
            checks.append(
                {
                    "file": rel_path,
                    "status": "fail",
                    "reason": "missing_core_file",
                    "rules": {},
                }
            )
            continue
        text = _load_text(file_path)
        file_rules: dict[str, bool] = {}
        for rule_name, patterns in REQUIRED_RULES.items():
            matched = any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)
            file_rules[rule_name] = matched
        checks.append(
            {
                "file": rel_path,
                "status": "ok" if all(file_rules.values()) else "fail",
                "reason": "" if all(file_rules.values()) else "missing_required_rule_clause",
                "rules": file_rules,
            }
        )
    return checks


def _contradiction_hits(repo_root: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for file_path in _iter_scope_files(repo_root):
        text = _load_text(file_path)
        lines = text.splitlines()
        in_code_block = False
        for line_number, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            if not line:
                continue

            idx = line_number - 1
            if _window_has_negative_context(lines, idx):
                continue

            if "商店" in line and "升级" in line and not _line_is_contextual_negative(line):
                hits.append(
                    {
                        "rule": "shop_upgrade_positive_statement",
                        "file": _to_posix(file_path.relative_to(repo_root)),
                        "line": line_number,
                        "text": line,
                    }
                )

            if "战斗" in line and "中间态" in line and "保存" in line and not _line_is_contextual_negative(line):
                hits.append(
                    {
                        "rule": "combat_mid_state_save_positive_statement",
                        "file": _to_posix(file_path.relative_to(repo_root)),
                        "line": line_number,
                        "text": line,
                    }
                )

            if "难度" in line and "天赋" in line and "绑定" in line and not _line_is_contextual_negative(line):
                hits.append(
                    {
                        "rule": "difficulty_talent_positive_binding_statement",
                        "file": _to_posix(file_path.relative_to(repo_root)),
                        "line": line_number,
                        "text": line,
                    }
                )

            if "升级" in line and ("仅" in line or "只" in line) and "商店" in line and not _line_is_contextual_negative(line):
                hits.append(
                    {
                        "rule": "upgrade_scope_conflict_with_shop",
                        "file": _to_posix(file_path.relative_to(repo_root)),
                        "line": line_number,
                        "text": line,
                    }
                )

    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="PRD/GDD semantic consistency hard gate")
    parser.add_argument("--max-print", type=int, default=20)
    parser.add_argument("--out", default="", help="Optional custom output JSON path")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    required_checks = _required_rules_check(repo_root)
    contradiction_checks = _contradiction_hits(repo_root)

    required_failures = [item for item in required_checks if item.get("status") != "ok"]

    summary: dict[str, Any] = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "action": "prd-gdd-semantic-consistency-gate",
        "reason": "enforce frozen gameplay and save/determinism semantics in PRD/GDD",
        "target": ["docs/prd/*.md", "docs/gdd/*.md"],
        "caller": "python-check_prd_gdd_semantic_consistency",
        "required_checks": required_checks,
        "required_failures": required_failures,
        "contradiction_hits": contradiction_checks,
        "status": "ok" if not required_failures and not contradiction_checks else "fail",
    }

    date = _today_str()
    default_out = Path("logs") / "ci" / date / "prd-gdd-consistency" / "summary.json"
    out_path = Path(args.out) if args.out else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = str(summary["status"])
    print(
        "PRD_GDD_CONSISTENCY "
        f"status={status} required_failures={len(required_failures)} contradictions={len(contradiction_checks)} "
        f"out={_to_posix(out_path)}"
    )

    if required_failures:
        print("PRD_GDD_CONSISTENCY required failures:")
        for item in required_failures[: max(1, int(args.max_print))]:
            print(f" - file={item.get('file')} missing_rules={ [k for k,v in (item.get('rules') or {}).items() if not v] }")

    if contradiction_checks:
        print("PRD_GDD_CONSISTENCY contradiction hits:")
        for hit in contradiction_checks[: max(1, int(args.max_print))]:
            print(
                " - "
                f"{hit.get('file')}:{hit.get('line')} rule={hit.get('rule')} text={hit.get('text')}"
            )

    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
