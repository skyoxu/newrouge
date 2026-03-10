#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

REFS_RE = re.compile(r"\bRefs\s*:\s*(.+)$", flags=re.IGNORECASE)

_GOVERNANCE_PATTERNS = [
    re.compile(p, flags=re.IGNORECASE)
    for p in (
        r"\badr\b",
        r"\bacceptance_checklist\b",
        r"\bchecklist\b",
        r"\btest-refs\b",
        r"\boverlay\b",
        r"\btraceability\b",
        r"\bauditable\b",
        r"\bmarker\b",
        r"\bresult\s+json\s+refs\b",
        r"\bgate scripts?\b",
        r"\brefs\s+must\s+include\b",
    )
]


def split_refs_clause(line: str) -> tuple[str, str | None]:
    text = str(line or "")
    m = REFS_RE.search(text)
    if not m:
        return text.strip(), None
    prefix = text[: m.start()].rstrip()
    refs_blob = m.group(0).strip()
    return prefix.strip(), refs_blob


def is_governance_acceptance_line(line: Any) -> bool:
    prefix, _refs = split_refs_clause(str(line or ""))
    normalized = re.sub(r"\s+", " ", prefix).strip().lower()
    if not normalized:
        return False
    return any(p.search(normalized) for p in _GOVERNANCE_PATTERNS)


def split_acceptance_scope(lines: list[Any]) -> tuple[list[str], list[str]]:
    semantic: list[str] = []
    governance: list[str] = []
    for raw in lines or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if is_governance_acceptance_line(text):
            governance.append(text)
        else:
            semantic.append(text)
    return semantic, governance

