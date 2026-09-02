from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_CONSUMERS = {"repository-session", "chapter4", "chapter5", "chapter6", "review"}
EXPECTED_DOMAINS = {"toolchain", "game-design", "game-runtime", "delivery"}
REQUIRED_EXCLUSION_IDS = {"logs", "backup", "migration", "godot-cache", "bin", "obj"}
FORBIDDEN_RUNTIME_TOKENS = (
    "PhaseA.Platform",
    "HostedContextGate",
    "runtime/phase-a",
    "predecessor_judge_hash",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _static_checks(root: Path) -> list[str]:
    issues: list[str] = []
    required_files = [
        "docs/adr/ADR-0035-repository-knowledge-control-plane.md",
        "knowledge/README.md",
        "knowledge/contracts/knowledge-locator-request.v1.schema.json",
        "knowledge/contracts/knowledge-locator-result.v1.schema.json",
        "knowledge/contracts/knowledge-consumption-decision.v1.schema.json",
        "knowledge/policies/consumer-policies.v1.json",
        "knowledge/policies/source-exclusions.v1.json",
        "scripts/python/_knowledge_catalog_builder.py",
        "scripts/python/_knowledge_locator_core.py",
        "scripts/python/build_knowledge_catalog.py",
        "scripts/python/knowledge_locator.py",
        "scripts/python/evaluate_knowledge_queries.py",
        "scripts/python/prepare_knowledge_context.py",
        "knowledge/evaluation/queries.v1.json",
        "knowledge/contracts/knowledge-context-candidates.v1.schema.json",
        "knowledge/contracts/knowledge-consumption-decision-set.v1.schema.json",
        "knowledge/contracts/knowledge-frozen-context.v1.schema.json",
        "scripts/python/freeze_knowledge_context.py",
        "docs/workflows/knowledge-context-shadow.md",
        "docs/workflows/knowledge-context-freeze.md",
        ".agents/skills/maintain-knowledge-base/SKILL.md",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            issues.append(f"missing:{relative}")

    policies = _load(root / "knowledge/policies/consumer-policies.v1.json")
    consumers = {item.get("consumer") for item in policies.get("policies", []) if isinstance(item, dict)}
    if consumers != EXPECTED_CONSUMERS:
        issues.append("consumer-policy-set-mismatch")
    for policy in policies.get("policies", []):
        if not set(policy.get("domains", [])).issubset(EXPECTED_DOMAINS):
            issues.append(f"invalid-domain:{policy.get('consumer')}")
        if not policy.get("required_context_classes"):
            issues.append(f"missing-required-context-class:{policy.get('consumer')}")

    exclusions = _load(root / "knowledge/policies/source-exclusions.v1.json")
    exclusion_ids = {rule.get("id") for rule in exclusions.get("rules", []) if isinstance(rule, dict)}
    missing_exclusions = sorted(REQUIRED_EXCLUSION_IDS - exclusion_ids)
    if missing_exclusions:
        issues.append("missing-exclusions:" + ",".join(missing_exclusions))

    request_schema = _load(root / "knowledge/contracts/knowledge-locator-request.v1.schema.json")
    enum = set(request_schema.get("properties", {}).get("consumer", {}).get("enum", []))
    if enum != EXPECTED_CONSUMERS:
        issues.append("locator-request-consumer-enum-mismatch")

    routing = (root / "docs/agents/13-rag-sources-and-session-ssot.md").read_text(encoding="utf-8")
    for marker in ("Knowledge Control Plane", "knowledge_locator.py", "direct authoritative source"):
        if marker not in routing:
            issues.append(f"routing-doc-missing:{marker}")

    for relative in (
        ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md",
        ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md",
        ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
    ):
        if (root / relative).is_file():
            skill_text = (root / relative).read_text(encoding="utf-8")
            if "knowledge-context-shadow.md" not in skill_text:
                issues.append(f"shadow-routing-missing:{relative}")

    for relative in (
        "scripts/python/_knowledge_catalog_builder.py",
        "scripts/python/_knowledge_locator_core.py",
        "scripts/python/build_knowledge_catalog.py",
        "scripts/python/knowledge_locator.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                issues.append(f"saas-runtime-token:{relative}:{token}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminal validation for the newrouge repository Knowledge Control Plane.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--require-generated", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()

    issues = _static_checks(root)
    checks: list[dict[str, Any]] = []

    unit = _run([sys.executable, "scripts/python/tests/test_knowledge_control_plane.py"], root)
    checks.append({"name": "unit-kernel", "returncode": unit.returncode})
    if unit.returncode:
        issues.append("unit-kernel-tests-failed")
    freeze_unit = _run([sys.executable, "scripts/python/tests/test_knowledge_freeze.py"], root)
    checks.append({"name": "unit-freeze", "returncode": freeze_unit.returncode})
    if freeze_unit.returncode:
        issues.append("unit-freeze-tests-failed")

    if args.require_generated:
        build = _run([sys.executable, "scripts/python/build_knowledge_catalog.py", "--check"], root)
        checks.append({"name": "generated-layers", "returncode": build.returncode})
        if build.returncode:
            issues.append("generated-layers-stale")
        evaluation = _run([sys.executable, "scripts/python/evaluate_knowledge_queries.py"], root)
        checks.append({"name": "repository-query-evaluation", "returncode": evaluation.returncode})
        if evaluation.returncode:
            issues.append("repository-query-evaluation-failed")

    result = {
        "schema_version": "newrouge.knowledge-terminal-validation.v1",
        "status": "passed" if not issues else "failed",
        "require_generated": args.require_generated,
        "checks": checks,
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
