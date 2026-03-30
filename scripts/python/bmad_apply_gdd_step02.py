#!/usr/bin/env python3
"""
Apply BMAD GDD Step-02 (Executive Summary) into `_bmad-output/gdd.md`.

Design goals:
- Windows-friendly: run with `py -3`.
- Always write UTF-8 without BOM.
- Idempotent: re-running replaces the same section.
- Emit evidence logs under `logs/ci/<YYYY-MM-DD>/gdd/`.

Note: To keep this work file English-only, the Step-02 markdown content is read
from a UTF-8 snippet file under `_bmad-output/snippets/`.

This script intentionally avoids third-party dependencies.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
BMAD_ROOT = REPO_ROOT / "_bmad-output"
GDD_PATH = BMAD_ROOT / "gdd.md"
SNIPPET_PATH = BMAD_ROOT / "snippets" / "gdd-step-02-executive-summary.md"


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat()


def _today() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    with io.open(path, "rb") as f:
        return _sha256_bytes(f.read())


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _repo_rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")


def _encoding_evidence(path: Path) -> dict:
    raw = io.open(path, "rb").read()
    first3_hex = " ".join(f"{x:02X}" for x in raw[:3])
    return {
        "path": _repo_rel(path),
        "first3_hex": first3_hex,
        "utf8_bom": raw.startswith(b"\xEF\xBB\xBF"),
    }


def _update_frontmatter(text: str, *, steps: str, last_step: str, game_type: str, game_name: str) -> str:
    if not text.startswith("---\n"):
        raise ValueError("Missing YAML frontmatter header '---' at file start.")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Missing YAML frontmatter closing '---'.")

    fm = text[4:end]
    body = text[end + 5 :]

    def repl_line(key: str, value_line: str) -> None:
        nonlocal fm
        rx = re.compile(rf"^(?P<k>{re.escape(key)}):[^\n]*$", re.MULTILINE)
        if rx.search(fm):
            fm = rx.sub(f"{key}: {value_line}", fm)
        else:
            fm = fm.rstrip("\n") + f"\n{key}: {value_line}\n"

    repl_line("stepsCompleted", steps)
    repl_line("lastStep", last_step)
    repl_line("game_type", f"\"{game_type}\"")
    repl_line("game_name", f"\"{game_name}\"")

    return "---\n" + fm.rstrip("\n") + "\n---\n" + body


def _replace_header_placeholders(text: str, *, author: str, game_type: str, game_name: str, platforms: str) -> str:
    text = text.replace("# {{game_name}} - Game Design Document", f"# {game_name} - Game Design Document")
    text = text.replace("**Author:** {{user_name}}", f"**Author:** {author}")
    text = text.replace("**Game Type:** {{game_type}}", f"**Game Type:** {game_type}")
    text = text.replace("**Target Platform(s):** {{platforms}}", f"**Target Platform(s):** {platforms}")
    return text


def _replace_exec_summary_block(text: str, new_exec_summary: str) -> str:
    # Replace the first "## Executive Summary" block up to the next "---" divider before "## Goals and Context".
    anchor = "\n---\n\n## Goals and Context"
    start = text.find("## Executive Summary")
    if start < 0:
        raise ValueError("Cannot find '## Executive Summary' block to replace.")
    end = text.find(anchor, start)
    if end < 0:
        raise ValueError("Cannot find Executive Summary block end anchor.")
    return text[:start] + new_exec_summary.rstrip("\n") + "\n" + text[end:]


def _load_exec_summary_snippet() -> str:
    if not SNIPPET_PATH.is_file():
        raise FileNotFoundError(
            f"Missing snippet file: {SNIPPET_PATH}. Create it as UTF-8 and re-run."
        )
    with io.open(SNIPPET_PATH, "r", encoding="utf-8") as f:
        txt = f.read()
    if "## Executive Summary" not in txt:
        raise ValueError("Snippet must include '## Executive Summary' header.")
    return txt


def apply() -> Tuple[str, str]:
    if not GDD_PATH.is_file():
        raise FileNotFoundError(GDD_PATH)

    before_sha = _sha256_file(GDD_PATH)
    with io.open(GDD_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    text = _update_frontmatter(
        text,
        steps="[1, 2]",
        last_step="2",
        game_type="card-game",
        game_name="NewRouge",
    )
    text = _replace_header_placeholders(
        text,
        author="skyo",
        game_type="card-game",
        game_name="NewRouge",
        platforms="Windows (Steam)",
    )
    text = _replace_exec_summary_block(text, _load_exec_summary_snippet())

    # Always write UTF-8 without BOM.
    with io.open(GDD_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    after_sha = _sha256_file(GDD_PATH)
    return before_sha, after_sha


def main() -> int:
    date = _today()
    out_dir = REPO_ROOT / "logs" / "ci" / date / "gdd"
    out_dir.mkdir(parents=True, exist_ok=True)

    step_init_path = out_dir / "step-02.init.json"
    step_complete_path = out_dir / "step-02.complete.json"
    enc_path = out_dir / "check_encoding.gdd.step-02.log.json"

    _write_json(
        step_init_path,
        {
            "ts": _now_iso(),
            "action": "gdd.step-02.init",
            "output_file": _repo_rel(GDD_PATH),
        },
    )

    before_sha, after_sha = apply()
    _write_json(enc_path, {"ts": _now_iso(), "action": "encoding.check", "files": [_encoding_evidence(GDD_PATH)]})
    _write_json(
        step_complete_path,
        {
            "ts": _now_iso(),
            "action": "gdd.step-02.complete",
            "output_file": _repo_rel(GDD_PATH),
            "sha256_before": before_sha,
            "sha256_after": after_sha,
            "stepsCompleted": ["1", "2"],
            "lastStep": 2,
            "game_type": "card-game",
            "game_name": "NewRouge",
        },
    )

    print(f"GDD_STEP_02_APPLIED file={_repo_rel(GDD_PATH)} sha256={after_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
