#!/usr/bin/env python3
"""Execute the controlled real-model Capability -> MVG planning acceptance chain in an isolated fixture."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, file_sha, load_json
from chapter5_semantic_reconciliation import load_task_readiness
from planning_acceptance_fixture import TASK_IDS, build_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
CAP_SCRIPT = REPO_ROOT / "scripts/python/plan_capabilities.py"
MVG_SCRIPT = REPO_ROOT / "scripts/python/plan_mvg.py"
OPENAI_RUNNER = REPO_ROOT / "scripts/python/openai_isolated_model_runner.py"
COPILOT_RUNNER = REPO_ROOT / "scripts/python/copilot_isolated_model_runner.py"


def _run(
    evidence_dir: Path,
    name: str,
    args: list[str],
    *,
    env: dict[str, str],
    timeout_sec: int,
) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_sec,
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_path = evidence_dir / f"{name}.log"
    log_path.write_text(proc.stdout, encoding="utf-8", newline="\n")
    result = {
        "stage": name,
        "returncode": proc.returncode,
        "command": args,
        "log": log_path.as_posix(),
    }
    if proc.returncode != 0:
        raise RuntimeError(
            f"{name} failed rc={proc.returncode}; "
            f"tail={proc.stdout[-2500:]}"
        )
    return result


def _read_capability_run(fixture_root: Path, run_id: str) -> dict[str, Any]:
    return load_json(fixture_root / f"logs/ci/capability-planning/{run_id}/run.json", {})


def _read_mvg_run(fixture_root: Path, run_id: str) -> dict[str, Any]:
    return load_json(fixture_root / f"logs/ci/mvg-planning/{run_id}/run.json", {})


def execute(
    *,
    fixture_root: Path,
    evidence_dir: Path,
    model: str,
    timeout_sec: int,
    backend: str = "auto",
) -> dict[str, Any]:
    fixture = build_fixture(fixture_root)
    env = dict(os.environ)
    selected_backend = backend
    if selected_backend == "auto":
        selected_backend = (
            "openai-api"
            if str(env.get("OPENAI_API_KEY") or "").strip()
            else "copilot-cli"
        )
    if selected_backend == "openai-api":
        if not str(env.get("OPENAI_API_KEY") or "").strip():
            raise ValueError("OPENAI_API_KEY is required for openai-api acceptance")
        runner = OPENAI_RUNNER
        env["SC_OPENAI_MODEL"] = model
        env["OPENAI_MODEL"] = model
        mvg_backend = "openai-api"
    elif selected_backend == "copilot-cli":
        if not str(env.get("GITHUB_TOKEN") or env.get("COPILOT_GITHUB_TOKEN") or "").strip():
            raise ValueError("GITHUB_TOKEN/COPILOT_GITHUB_TOKEN is required for Copilot acceptance")
        runner = COPILOT_RUNNER
        env["SC_COPILOT_MODEL"] = model or "auto"
        mvg_backend = "copilot-cli"
    else:
        raise ValueError(f"unsupported production acceptance backend: {selected_backend}")
    env["PYTHONUTF8"] = "1"

    cap_run = "production-capability"
    mvg_run = "production-mvg"
    stages: list[dict[str, Any]] = []

    base = [sys.executable, str(CAP_SCRIPT), "--repo-root", str(fixture_root)]
    stages.append(_run(
        evidence_dir, "01-capability-prepare",
        [*base, "prepare", "--run-id", cap_run, "--task-id", "7", "--task-id", "42",
         "--model-batch-char-budget", "12000", "--candidate-retry-limit", "5",
         "--review-retry-limit", "1", "--candidate-budget-sec", str(timeout_sec),
         "--total-budget-sec", str(timeout_sec * 6), "--request-limit", "50"],
        env=env, timeout_sec=120,
    ))
    stages.append(_run(
        evidence_dir, "02-capability-generate",
        [*base, "generate", "--run-id", cap_run, "--runner", str(runner),
         "--timeout-sec", str(timeout_sec)],
        env=env, timeout_sec=timeout_sec * 4,
    ))
    stages.append(_run(
        evidence_dir, "03-capability-review",
        [*base, "review", "--run-id", cap_run, "--runner", str(runner),
         "--timeout-sec", str(timeout_sec)],
        env=env, timeout_sec=timeout_sec * 2,
    ))
    stages.append(_run(
        evidence_dir, "04-capability-alignment",
        [*base, "preview-alignment", "--run-id", cap_run],
        env=env, timeout_sec=120,
    ))
    stages.append(_run(
        evidence_dir, "05-capability-apply",
        [*base, "apply", "--run-id", cap_run, "--confirm"],
        env=env, timeout_sec=180,
    ))

    readiness = {}
    for task_id in map(str, TASK_IDS):
        ok, payload, reason = load_task_readiness(fixture_root, task_id)
        readiness[task_id] = {
            "ready": ok,
            "reason": reason,
            "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
        }
        if not ok:
            raise RuntimeError(
                f"Capability apply left Chapter 5 readiness invalid for task {task_id}: {reason}"
            )

    mvg_base = [sys.executable, str(MVG_SCRIPT), "--repo-root", str(fixture_root)]
    manifest_rel = "docs/testing/mvg/harbor-relay-acceptance.json"
    stages.append(_run(
        evidence_dir, "06-mvg-prepare",
        [*mvg_base, "prepare", "--run-id", mvg_run,
         "--capabilities", "docs/planning/semantic-topology/capabilities.v1.json",
         "--manifest", manifest_rel, "--task-id", "7", "--task-id", "42"],
        env=env, timeout_sec=120,
    ))
    stages.append(_run(
        evidence_dir, "07-mvg-generate",
        [*mvg_base, "generate", "--run-id", mvg_run,
         "--llm-backend", mvg_backend, "--timeout-sec", str(timeout_sec)],
        env=env, timeout_sec=timeout_sec + 120,
    ))
    stages.append(_run(
        evidence_dir, "08-mvg-independent-review",
        [*mvg_base, "review", "--run-id", mvg_run, "--runner", str(runner), "--timeout-sec", str(timeout_sec)],
        env=env, timeout_sec=timeout_sec + 120,
    ))
    stages.append(_run(
        evidence_dir, "08-mvg-validate",
        [*mvg_base, "validate", "--run-id", mvg_run],
        env=env, timeout_sec=180,
    ))

    cap_state = _read_capability_run(fixture_root, cap_run)
    if cap_state.get("review_status") != "selected":
        raise RuntimeError("Capability acceptance did not produce a selected winner")
    attempts = cap_state.get("candidate_attempts", {})
    if sorted(attempts) != ["candidate-1", "candidate-2", "candidate-3"]:
        raise RuntimeError("Capability acceptance did not retain exactly three candidate records")
    candidate_models: set[str] = set()
    for label, record in attempts.items():
        if not isinstance(record, dict) or not record.get("valid_attempt"):
            raise RuntimeError(f"Capability candidate is not valid: {label}")
        final_meta = record.get("final_meta") or {}
        actual_model = str(final_meta.get("model") or "").strip()
        if not actual_model:
            raise RuntimeError(f"Capability candidate model identity missing: {label}")
        candidate_models.add(actual_model)
        runner = final_meta.get("runner") or {}
        if runner.get("fresh_session_per_invocation") is not True or runner.get("model_tools") != []:
            raise RuntimeError(f"Capability candidate isolation contract failed: {label}")
    if len(candidate_models) != 1:
        raise RuntimeError(
            "Capability candidates did not use one actual model: "
            + ",".join(sorted(candidate_models))
        )
    candidate_model = next(iter(candidate_models))
    review_attempts = [
        row for row in cap_state.get("review_attempts", [])
        if isinstance(row, dict) and not row.get("validation_errors")
    ]
    if not review_attempts:
        raise RuntimeError("Capability acceptance has no valid independent review attempt")
    review_model = str(review_attempts[-1].get("model") or "").strip()
    if not review_model:
        raise RuntimeError("Capability independent review model identity is missing")

    cap_apply = load_json(
        fixture_root / f"logs/ci/capability-planning/{cap_run}/apply-summary.json", {}
    )
    if cap_apply.get("status") != "applied" or cap_apply.get("mvg_formal_planning_allowed") is not True:
        raise RuntimeError("Capability application/readiness rebind is incomplete")

    mvg_state = _read_mvg_run(fixture_root, mvg_run)
    mvg_review_execution = load_json(fixture_root / f"logs/ci/mvg-planning/{mvg_run}/semantic-review-execution.json", {})
    mvg_validation = load_json(
        fixture_root / f"logs/ci/mvg-planning/{mvg_run}/validation.json", {}
    )
    if mvg_validation.get("status") != "passed" or mvg_validation.get("formal_applicable") is not True:
        raise RuntimeError(f"MVG production proposal failed formal validation: {mvg_validation}")

    proposal_path = fixture_root / f"logs/ci/mvg-planning/{mvg_run}/proposal.json"
    execution_path = fixture_root / f"logs/ci/mvg-planning/{mvg_run}/model-execution.json"
    execution = load_json(execution_path, {})
    trace = execution.get("trace") if isinstance(execution, dict) else {}
    receipt = execution.get("receipt") if isinstance(execution, dict) else {}
    request_count = int((cap_state.get("budget") or {}).get("model_requests_observed") or 0)
    if isinstance(receipt, dict) and type(receipt.get("model_request_count")) is int:
        mvg_request_count = int(receipt["model_request_count"])
    elif isinstance(trace, dict) and type(trace.get("request_count")) is int:
        mvg_request_count = int(trace["request_count"])
    else:
        mvg_request_count = None

    summary = {
        "schema_version": "newrouge.planning-production-acceptance.v1",
        "status": "passed",
        "fixture": fixture,
        "candidate_model": candidate_model,
        "review_model": review_model,
        "requested_model": model,
        "backend": selected_backend,
        "capability": {
            "run_id": cap_run,
            "analysis_identity_sha256": cap_state.get("analysis_identity_sha256"),
            "selected_candidate": cap_state.get("selected_candidate"),
            "final_candidate_path": cap_state.get("final_candidate_path"),
            "candidate_count": 3,
            "review_status": cap_state.get("review_status"),
            "model_requests_observed": request_count,
            "request_count_complete": (cap_state.get("budget") or {}).get("request_count_complete"),
            "capabilities_sha256": cap_apply.get("capabilities_sha256"),
            "chapter5_post_apply_readiness": readiness,
        },
        "mvg": {
            "run_id": mvg_run,
            "backend": mvg_state.get("model_backend"),
            "proposal_sha256": file_sha(proposal_path),
            "validation": mvg_validation,
            "model_request_count": mvg_request_count,
            "independent_semantic_review_model": (mvg_review_execution.get("receipt") or {}).get("model"),
            "independent_semantic_review_sha256": file_sha(fixture_root / f"logs/ci/mvg-planning/{mvg_run}/semantic-review.json"),
            "manifest_applied": False,
            "runtime_verified": False,
        },
        "acceptance_retry_policy": {
            "candidate_retry_limit": 5,
            "reason": "Copilot auto routing may expose multiple internal models; mismatched-model attempts are discarded so the three accepted candidates still use one actual model.",
        },
        "cost": {
            "amount_available": False,
            "note": "The runner records observable model requests but the API response path does not expose billing amount; no cost amount is invented.",
        },
        "stages": stages,
    }
    atomic_json(evidence_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default="logs/ci/planning-production-acceptance/workspace")
    parser.add_argument("--evidence-dir", default="logs/ci/planning-production-acceptance/evidence")
    parser.add_argument("--backend", choices=("auto", "openai-api", "copilot-cli"), default="auto")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout-sec", type=int, default=900)
    args = parser.parse_args()
    fixture_root = (REPO_ROOT / args.workspace).resolve()
    evidence_dir = (REPO_ROOT / args.evidence_dir).resolve()
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    try:
        backend = str(args.backend)
        if args.model:
            model = str(args.model)
        elif backend == "openai-api" or (
            backend == "auto" and str(os.environ.get("OPENAI_API_KEY") or "").strip()
        ):
            model = str(os.environ.get("SC_OPENAI_MODEL") or "gpt-5")
        else:
            model = str(os.environ.get("SC_COPILOT_MODEL") or "auto")
        summary = execute(
            fixture_root=fixture_root,
            evidence_dir=evidence_dir,
            model=model,
            timeout_sec=int(args.timeout_sec),
            backend=backend,
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(evidence_dir / "summary.json", {
            "schema_version": "newrouge.planning-production-acceptance.v1",
            "status": "blocked",
            "reason": str(exc),
            "model": str(args.model or os.environ.get("SC_COPILOT_MODEL") or os.environ.get("SC_OPENAI_MODEL") or ""),
        })
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
