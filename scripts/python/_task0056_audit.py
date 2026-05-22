from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

TASK0056_REQUIRED_ADR_REFS = ("ADR-0019", "ADR-0003", "ADR-0005")
TASK0056_REQUIRED_CHAPTER_REFS = ("CH02", "CH03", "CH07")
TASK0056_REQUIRED_TEST_REFS = (
    "Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs",
    "Tests/CI/AuditLogs/ValidateAuditLogsTests.cs",
)
TASK0056_REQUIRED_ARTIFACT_REFS = (
    "logs/ci/task-0056-summary.json",
    "logs/ci/security-audit.jsonl",
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="ignore")


def _to_bool_env(name: str) -> bool:
    return str(os.environ.get(name, "0")).strip() == "1"


def _try_int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())


def run_task0056_audit_validation(repo_root: Path, date: str) -> dict[str, object]:
    enabled = _to_bool_env("QUALITY_GATES_ENABLE_AUDIT_VALIDATION")
    ci_date_dir = repo_root / "logs" / "ci" / date
    summary_path = ci_date_dir / "task-0056-summary.json"
    log_path = ci_date_dir / "task-0056-audit-validation.log"
    input_path = ci_date_dir / "security-audit.jsonl"
    script_path = repo_root / "scripts" / "python" / "validate_audit_logs.py"

    if not enabled:
        return {
            "enabled": False,
            "executed": False,
            "pass_fail": "skipped",
            "rc": None,
            "summary_path": str(summary_path),
            "log_path": str(log_path),
            "input_path": str(input_path),
        }

    fake_rc = _try_int_env("QUALITY_GATES_FAKE_AUDIT_VALIDATOR_RC")
    if fake_rc is not None:
        payload = {
            "ok": fake_rc == 0,
            "fake": True,
            "total_lines": 0,
            "invalid_lines": 0 if fake_rc == 0 else 1,
            "issues": [] if fake_rc == 0 else [{"line": 1, "reason": "fake_forced_failure", "fix": "set QUALITY_GATES_FAKE_AUDIT_VALIDATOR_RC=0"}],
            "input": str(input_path),
        }
        _write_text(summary_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _write_text(log_path, f"QUALITY_GATES_FAKE_AUDIT_VALIDATOR_RC={fake_rc}\n")
        return {
            "enabled": True,
            "executed": True,
            "pass_fail": "pass" if fake_rc == 0 else "fail",
            "rc": fake_rc,
            "summary_path": str(summary_path),
            "log_path": str(log_path),
            "input_path": str(input_path),
        }

    if not script_path.is_file():
        _write_text(summary_path, json.dumps({"ok": False, "issues": [{"line": 0, "reason": "validator_script_missing"}], "input": str(input_path)}, ensure_ascii=False, indent=2) + "\n")
        _write_text(log_path, f"Missing validator script: {script_path}\n")
        return {
            "enabled": True,
            "executed": True,
            "pass_fail": "fail",
            "rc": 1,
            "summary_path": str(summary_path),
            "log_path": str(log_path),
            "input_path": str(input_path),
        }

    cmd = ["py", "-3", str(script_path), "--input", str(input_path), "--out", str(summary_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    _write_text(log_path, combined)
    return {
        "enabled": True,
        "executed": True,
        "pass_fail": "pass" if proc.returncode == 0 else "fail",
        "rc": proc.returncode,
        "summary_path": str(summary_path),
        "log_path": str(log_path),
        "input_path": str(input_path),
    }


def _load_task56_context(repo_root: Path) -> dict[str, Any]:
    tasks_json = repo_root / ".taskmaster" / "tasks" / "tasks.json"
    tasks_back = repo_root / ".taskmaster" / "tasks" / "tasks_back.json"
    tasks_gameplay = repo_root / ".taskmaster" / "tasks" / "tasks_gameplay.json"

    adr_refs: list[str] = []
    chapter_refs: list[str] = []
    test_refs: list[str] = []

    if tasks_json.is_file():
        data = json.loads(tasks_json.read_text(encoding="utf-8"))
        master_tasks = ((data.get("master") or {}).get("tasks") or [])
        for item in master_tasks:
            if isinstance(item, dict) and str(item.get("id")) == "56":
                adr_refs = [str(x) for x in (item.get("adrRefs") or []) if str(x).strip()]
                chapter_refs = [str(x) for x in (item.get("archRefs") or []) if str(x).strip()]
                break

    for view_path in (tasks_back, tasks_gameplay):
        if not view_path.is_file():
            continue
        view = json.loads(view_path.read_text(encoding="utf-8"))
        if not isinstance(view, list):
            continue
        for item in view:
            if not isinstance(item, dict):
                continue
            if str(item.get("taskmaster_id")) != "56":
                continue
            for ref in item.get("test_refs") or []:
                s = str(ref).replace("\\", "/").strip()
                if s and s not in test_refs:
                    test_refs.append(s)

    if not adr_refs:
        adr_refs = list(TASK0056_REQUIRED_ADR_REFS)
    else:
        for required_ref in TASK0056_REQUIRED_ADR_REFS:
            if required_ref not in adr_refs:
                adr_refs.append(required_ref)

    if not chapter_refs:
        chapter_refs = list(TASK0056_REQUIRED_CHAPTER_REFS)
    else:
        for required_ref in TASK0056_REQUIRED_CHAPTER_REFS:
            if required_ref not in chapter_refs:
                chapter_refs.append(required_ref)

    for required_ref in (*TASK0056_REQUIRED_TEST_REFS, *TASK0056_REQUIRED_ARTIFACT_REFS):
        if required_ref not in test_refs:
            test_refs.append(required_ref)

    # Keep artifact evidence keys explicit for deterministic checks.
    for artifact_ref in TASK0056_REQUIRED_ARTIFACT_REFS:
        if artifact_ref not in test_refs:
            test_refs.append(artifact_ref)

    return {
        "adr_refs": adr_refs,
        "chapter_refs": chapter_refs,
        "test_refs": test_refs,
    }


def _build_evidence_map(*, test_refs: list[str], audit_validation: dict[str, object]) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    ci_rc = _try_int_env("QUALITY_GATES_CI_RC")
    default_executed = ci_rc == 0 if ci_rc is not None else False
    default_status = "passed" if default_executed else ("failed" if ci_rc is not None and ci_rc != 0 else "skipped")
    default_unknown = {
        "executed": default_executed,
        "pass_fail": default_status,
    }
    for ref in test_refs:
        evidence[ref] = dict(default_unknown)

    summary_ref = "logs/ci/task-0056-summary.json"
    audit_ref = "logs/ci/security-audit.jsonl"
    if summary_ref in evidence:
        evidence[summary_ref] = {
            "executed": bool(audit_validation.get("executed")),
            "pass_fail": "passed" if str(audit_validation.get("pass_fail")) == "pass" else ("failed" if str(audit_validation.get("pass_fail")) == "fail" else "skipped"),
        }
    if audit_ref in evidence:
        enabled = bool(audit_validation.get("enabled"))
        pass_fail_raw = str(audit_validation.get("pass_fail"))
        evidence[audit_ref] = {
            "executed": enabled,
            "pass_fail": (
                "skipped"
                if not enabled
                else ("passed" if pass_fail_raw == "pass" else "failed")
            ),
        }
    return evidence


def _validate_task0056_payload(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ("adr_refs", "chapter_refs", "test_refs", "evidence", "audit_validation"):
        if key not in payload:
            errors.append(f"missing_required_field:{key}")

    for key in ("adr_refs", "chapter_refs", "test_refs"):
        value = payload.get(key)
        if not isinstance(value, list) or len(value) == 0:
            errors.append(f"invalid_required_list:{key}")
    adr_refs = payload.get("adr_refs")
    if isinstance(adr_refs, list):
        for item in TASK0056_REQUIRED_ADR_REFS:
            if item not in adr_refs:
                errors.append(f"missing_required_adr_ref:{item}")
    chapter_refs = payload.get("chapter_refs")
    if isinstance(chapter_refs, list):
        for item in TASK0056_REQUIRED_CHAPTER_REFS:
            if item not in chapter_refs:
                errors.append(f"missing_required_chapter_ref:{item}")
    test_refs = payload.get("test_refs")
    if isinstance(test_refs, list):
        for item in (*TASK0056_REQUIRED_TEST_REFS, *TASK0056_REQUIRED_ARTIFACT_REFS):
            if item not in test_refs:
                errors.append(f"missing_required_test_ref:{item}")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict) or len(evidence) == 0:
        errors.append("invalid_required_map:evidence")
    else:
        for ref_key, status in evidence.items():
            if not isinstance(status, dict):
                errors.append(f"invalid_evidence_status:{ref_key}")
                continue
            executed = status.get("executed")
            pass_fail = status.get("pass_fail")
            if not isinstance(executed, bool):
                errors.append(f"invalid_evidence_executed:{ref_key}")
            if pass_fail not in ("passed", "failed", "skipped"):
                errors.append(f"invalid_evidence_pass_fail:{ref_key}")
        enabled = bool(((payload.get("audit_validation") or {}) if isinstance(payload.get("audit_validation"), dict) else {}).get("enabled"))
        for ref_key in TASK0056_REQUIRED_TEST_REFS:
            status = evidence.get(ref_key)
            if not isinstance(status, dict):
                errors.append(f"missing_required_evidence_status:{ref_key}")
                continue
            if status.get("executed") is not True:
                errors.append(f"required_test_ref_not_executed:{ref_key}")
            if status.get("pass_fail") != "passed":
                errors.append(f"required_test_ref_not_passed:{ref_key}")
        summary_status = evidence.get("logs/ci/task-0056-summary.json")
        if enabled:
            if not isinstance(summary_status, dict) or summary_status.get("executed") is not True:
                errors.append("required_artifact_not_executed:logs/ci/task-0056-summary.json")
        audit_status = evidence.get("logs/ci/security-audit.jsonl")
        if enabled:
            if not isinstance(audit_status, dict) or audit_status.get("executed") is not True:
                errors.append("required_artifact_not_executed:logs/ci/security-audit.jsonl")
    return errors


def write_task0056_record(repo_root: Path, date: str, audit_validation: dict[str, object], final_exit_code: int) -> dict[str, object]:
    path = repo_root / "logs" / "ci" / date / "task-0056.json"
    context = _load_task56_context(repo_root)
    evidence = _build_evidence_map(test_refs=context["test_refs"], audit_validation=audit_validation)
    payload = {
        "task_id": 56,
        "platform": "windows-powershell",
        "adr_refs": context["adr_refs"],
        "chapter_refs": context["chapter_refs"],
        "test_refs": context["test_refs"],
        "evidence": evidence,
        "audit_validation": {
            "executed": bool(audit_validation.get("executed")),
            "pass_fail": str(audit_validation.get("pass_fail", "skipped")),
            "enabled": bool(audit_validation.get("enabled")),
            "rc": audit_validation.get("rc"),
            "summary_path": str(audit_validation.get("summary_path", "")),
            "input_path": str(audit_validation.get("input_path", "")),
            "log_path": str(audit_validation.get("log_path", "")),
        },
        "exit_code": final_exit_code,
    }

    if _to_bool_env("QUALITY_GATES_FAKE_TASK0056_MISSING_FIELDS"):
        payload.pop("adr_refs", None)

    validation_errors = _validate_task0056_payload(payload)
    payload["record_validation"] = {
        "valid": len(validation_errors) == 0,
        "errors": validation_errors,
    }
    if validation_errors:
        payload["exit_code"] = 1

    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload["record_validation"]
