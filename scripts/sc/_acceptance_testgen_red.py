from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _identity_tokens(refs: list[str]) -> list[str]:
    tokens: list[str] = []
    for raw in refs:
        stem = Path(str(raw or "").replace("\\", "/")).stem.strip().casefold()
        if stem and stem not in tokens:
            tokens.append(stem)
    return tokens


def _contains_expected_identity(text: str, refs: list[str]) -> bool:
    haystack = str(text or "").casefold()
    return any(token in haystack for token in _identity_tokens(refs))


def _failed_trx_results(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []
    failed: list[dict[str, str]] = []
    for elem in root.iter():
        if not elem.tag.endswith("UnitTestResult"):
            continue
        if str(elem.attrib.get("outcome") or "").strip().casefold() != "failed":
            continue
        name = str(elem.attrib.get("testName") or "").strip()
        messages = [
            str(child.text or "").strip()
            for child in elem.iter()
            if child.tag.endswith("Message") and str(child.text or "").strip()
        ]
        failed.append({"test_name": name, "message": "\n".join(messages)})
    return failed


def _contains_compile_error(*, verify_log_text: str, unit_summary: dict[str, Any]) -> bool:
    haystacks = [verify_log_text]
    excerpt = unit_summary.get("failure_excerpt")
    if isinstance(excerpt, list):
        haystacks.extend(str(item) for item in excerpt)
    for blob in haystacks:
        lower = str(blob or "").lower()
        if "error cs" in lower or "build failed" in lower:
            return True
    return False


def evaluate_red_verification(
    *,
    repo_root: Path,
    out_dir: Path,
    verify_mode: str,
    test_step: dict[str, Any] | None,
    verify_log_text: str,
    expected_test_refs: list[str],
) -> dict[str, Any]:
    date = out_dir.parent.name
    expected_refs = [str(item).replace("\\", "/") for item in expected_test_refs if str(item).strip()]
    report: dict[str, Any] = {
        "verify_mode": verify_mode,
        "status": "fail",
        "reason": "unknown",
        "expected_test_refs": expected_refs,
    }
    if not expected_refs:
        report["reason"] = "target_test_identity_missing"
        return report
    if verify_mode == "none":
        report["reason"] = "verify_disabled"
        return report
    if not isinstance(test_step, dict):
        report["reason"] = "verify_step_missing"
        return report

    rc = test_step.get("rc")
    if rc == 0:
        report["reason"] = "unexpected_green"
        return report

    sc_test_dir = repo_root / "logs" / "ci" / date / "sc-test"
    unit_dir = repo_root / "logs" / "unit" / date
    gdunit_dir = repo_root / "logs" / "e2e" / date / "sc-test" / "gdunit-hard"
    unit_summary = _read_json(unit_dir / "summary.json")
    gdunit_summary = _read_json(gdunit_dir / "run-summary.json")
    current_run_id = _read_text(sc_test_dir / "run_id.txt")
    unit_run_id = _read_text(unit_dir / "run_id.txt")
    gdunit_run_id = _read_text(gdunit_dir / "run_id.txt")
    report["sc_test_run_id"] = current_run_id
    report["unit_run_id"] = unit_run_id
    report["gdunit_run_id"] = gdunit_run_id
    report["unit_summary_status"] = unit_summary.get("status")
    report["gdunit_failures"] = ((gdunit_summary.get("results") or {}).get("failures") if gdunit_summary else None)
    report["gdunit_errors"] = ((gdunit_summary.get("results") or {}).get("errors") if gdunit_summary else None)

    if _contains_compile_error(verify_log_text=verify_log_text, unit_summary=unit_summary):
        report["reason"] = "compile_error"
        return report

    results = gdunit_summary.get("results") if isinstance(gdunit_summary, dict) else {}
    failures = int((results or {}).get("failures") or 0)
    errors = int((results or {}).get("errors") or 0)
    gdunit_tests = int((results or {}).get("tests") or 0)
    failed_gdunit_tests = [str(item) for item in (results or {}).get("failed_tests", []) if str(item).strip()]
    report["gdunit_tests"] = gdunit_tests
    report["gdunit_failed_tests"] = failed_gdunit_tests
    gd_expected = [ref for ref in expected_refs if ref.casefold().endswith(".gd")]
    if failures > 0 and errors == 0:
        if not current_run_id or gdunit_run_id != current_run_id:
            report["reason"] = "gdunit_run_identity_mismatch"
            return report
        if gdunit_tests <= 0:
            report["reason"] = "gdunit_zero_tests"
            return report
        added = [str(item).replace("\\", "/") for item in gdunit_summary.get("added", []) if str(item).strip()]
        added_text = "\n".join(added)
        failed_text = "\n".join(failed_gdunit_tests)
        if not gd_expected or not _contains_expected_identity(added_text, gd_expected):
            report["reason"] = "gdunit_target_not_selected"
            return report
        if not failed_gdunit_tests or not _contains_expected_identity(failed_text, gd_expected):
            report["reason"] = "gdunit_failure_not_target"
            return report
        report["status"] = "ok"
        report["reason"] = "gdunit_behavior_red"
        return report
    if errors > 0:
        report["reason"] = "gdunit_errors"
        return report

    unit_status = str(unit_summary.get("status") or "").strip()
    failure_excerpt = unit_summary.get("failure_excerpt")
    failure_lines = [str(item) for item in failure_excerpt] if isinstance(failure_excerpt, list) else []
    combined_failure = "\n".join([verify_log_text, *failure_lines]).lower()

    if int(rc or 0) == 124 or "timed out" in combined_failure or "timeout" in combined_failure:
        report["reason"] = "verification_timeout"
        return report

    environment_tokens = (
        "permission denied",
        "access is denied",
        "connection reset",
        "network path",
        "file is locked",
        "being used by another process",
        "could not find godot",
        "dotnet was not found",
    )
    if any(token in combined_failure for token in environment_tokens):
        report["reason"] = "verification_environment_failure"
        return report

    if unit_status == "tests_failed":
        cs_expected = [ref for ref in expected_refs if ref.casefold().endswith(".cs")]
        unit_filter = str(unit_summary.get("filter") or "")
        trx_failed = _failed_trx_results(unit_dir / "tests.trx")
        report["unit_filter"] = unit_filter
        report["unit_failed_tests"] = [item["test_name"] for item in trx_failed if item.get("test_name")]
        if not current_run_id or unit_run_id != current_run_id:
            report["reason"] = "unit_run_identity_mismatch"
            return report
        if not cs_expected or not _contains_expected_identity(unit_filter, cs_expected):
            report["reason"] = "unit_target_not_selected"
            return report
        assertion_tokens = (
            "expected:",
            "actual:",
            "but was:",
            "assert.",
            "assertion",
        )
        if trx_failed:
            target_rows = [
                item for item in trx_failed
                if _contains_expected_identity(str(item.get("test_name") or ""), cs_expected)
            ]
            if not target_rows:
                report["reason"] = "unit_failure_not_target"
                return report
            target_failure_text = "\n".join(
                str(item.get("message") or "") for item in target_rows
            ).casefold()
            if any(token in target_failure_text for token in assertion_tokens):
                report["status"] = "ok"
                report["reason"] = "unit_behavior_red"
                return report
            report["reason"] = "unit_failure_not_causal"
            return report

        if not _contains_expected_identity("\n".join(failure_lines), cs_expected):
            report["reason"] = "unit_failure_not_target"
            return report
        if failure_lines and any(token in combined_failure for token in assertion_tokens):
            report["status"] = "ok"
            report["reason"] = "unit_behavior_red"
            return report
        report["reason"] = "unit_failure_not_causal"
        return report

    if unit_status in {"ok", "coverage_failed"}:
        report["reason"] = "unexpected_green"
        return report

    if not unit_summary and not gdunit_summary:
        report["reason"] = "verification_report_missing"
        return report

    report["reason"] = "verification_failure_unclassified"
    return report
