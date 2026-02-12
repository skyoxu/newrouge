#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for legacy path.
Delegates to scripts/sc/llm_align_acceptance_semantics.py without modification.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    target = Path(__file__).resolve().parents[1] / "sc" / "llm_align_acceptance_semantics.py"
    if not target.exists():
        print(f"Target script not found: {target}")
        return 1
    sys.path.insert(0, str(target.parent))
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
