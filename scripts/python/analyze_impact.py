#!/usr/bin/env python3
"""CLI for deterministic repository-local impact analysis."""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from impact_analysis_handoff import EXIT_CODES
    from impact_analysis_index import ImpactIndexError, validate_index_bytes
    from impact_analyzer import (
        ANALYZER_IMPLEMENTATION_REVISION,
        ImpactAnalyzer,
        atomic_write_json,
        failure_report,
        load_frozen_binding,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.python.impact_analysis_handoff import EXIT_CODES
    from scripts.python.impact_analysis_index import ImpactIndexError, validate_index_bytes
    from scripts.python.impact_analyzer import (
        ANALYZER_IMPLEMENTATION_REVISION,
        ImpactAnalyzer,
        atomic_write_json,
        failure_report,
        load_frozen_binding,
    )


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _resolve_inside(root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or (len(value) > 1 and value[1] == ":") or value.startswith("\\\\"):
        candidate = p.resolve()
    else:
        candidate = (root / p).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ImpactIndexError("path_outside_repository", f"path outside repository: {value}") from exc
    return candidate


def _discover_index(root: Path, revision: str) -> Path:
    base = root / "logs" / "ci"
    candidates: list[tuple[Path, str, str]] = []
    for path in base.glob("*/impact-analysis/indexes/*/impact-index.v1.json"):
        try:
            value = validate_index_bytes(path.read_bytes())
            if value.get("repository_revision") == revision.lower():
                manifest = path.with_name("index-manifest.v1.json")
                m = json.loads(manifest.read_text(encoding="utf-8"))
                candidates.append((path, str(value.get("index_id")), str(m.get("trusted_ref"))))
        except Exception:
            continue
    if not candidates:
        raise ImpactIndexError("missing_index", "no validated impact index found for revision")
    identities = {(idx, ref) for _, idx, ref in candidates}
    if len(identities) != 1:
        raise ImpactIndexError("index_identity_collision", "multiple index identities/provenance match revision")
    return sorted((p for p, _, _ in candidates), key=lambda p: p.as_posix())[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a target against an immutable Impact Index. Stable failure codes: "
        + ", ".join(f"{k}={v}" for k, v in sorted(EXIT_CODES.items()))
    )
    parser.add_argument("--target", required=True, help='JSON target, e.g. {"type":"event","id":"RewardOfferPresentedEvent"}')
    parser.add_argument("--revision", required=True, help="Full 40-character Git commit SHA.")
    parser.add_argument("--trusted-ref", default=None)
    parser.add_argument("--index", default=None, help="Repository-relative impact-index.v1.json (or containing directory).")
    parser.add_argument("--frozen-context", "--frozen-context-path", dest="frozen_context", required=False)
    parser.add_argument("--consumer", default=None, choices=["chapter4", "chapter5", "chapter6", "review"])
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--output", default=None, help="Report path; defaults to an isolated UTC run directory.")
    parser.add_argument("--repository-root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.repository_root).resolve()
    run_id = str(uuid.uuid4())
    output_path: Path | None = None
    try:
        if len(args.revision.strip()) != 40 or any(c not in "0123456789abcdefABCDEF" for c in args.revision.strip()):
            raise ImpactIndexError("revision_mismatch", "revision must be a full 40-character Git SHA")
        revision = args.revision.strip().lower()
        if isinstance(args.target, str):
            try:
                target_input = json.loads(args.target)
            except json.JSONDecodeError:
                raise ImpactIndexError("unsupported_target", "invalid target JSON")
        else:
            target_input = args.target
        if args.output:
            output_path = _resolve_inside(root, args.output)
            try:
                output_path.relative_to((root / "logs" / "ci").resolve())
            except ValueError as exc:
                raise ImpactIndexError("path_outside_repository", "successful output must remain under logs/ci") from exc
        else:
            output_path = root / "logs" / "ci" / _utc_date() / "impact-analysis" / run_id / "impact-report.v1.json"
        index_path = _resolve_inside(root, args.index) if args.index else _discover_index(root, revision)
        try:
            index_path.relative_to((root / "logs" / "ci").resolve())
        except ValueError as exc:
            raise ImpactIndexError("path_outside_repository", "index must remain under logs/ci immutable roots") from exc
        if output_path.exists():
            raise ImpactIndexError("index_identity_collision", "output report already exists")
        if index_path.is_dir(): index_path = index_path / "impact-index.v1.json"
        analyzer = ImpactAnalyzer(root, index_path, revision, args.trusted_ref)
        if not args.frozen_context:
            raise ImpactIndexError("invalid_kcp_binding", "--frozen-context is required for successful reports")
        binding = load_frozen_binding(root, args.frozen_context, revision, args.consumer, args.task_id)
        report = analyzer.analyze(target_input, binding)
        report_sha = atomic_write_json(output_path, report)
        manifest = {
            "schema_version": "newrouge.impact-analysis-run-manifest.v1", "run_id": run_id,
            "report_path": output_path.relative_to(root).as_posix(), "report_sha256": report_sha,
            "index_id": report["index_id"], "index_path": index_path.relative_to(root).as_posix(), "index_sha256": report["index_sha256"],
            "repository_revision": revision, "knowledge_binding_sha256": binding["frozen_context_sha256"],
            "status": "ok", "generated_at": report["generated_at"],
        }
        atomic_write_json(output_path.parent / "run-manifest.v1.json", manifest)
        print(json.dumps({"status": "ok", "run_id": run_id, "report_path": manifest["report_path"], "report_sha256": report_sha}, ensure_ascii=False, sort_keys=True))
        return 0
    except ImpactIndexError as exc:
        report = failure_report(locals().get("target_input", {}), locals().get("revision"), exc)
        if output_path is not None:
            try:
                if not output_path.exists():
                    atomic_write_json(output_path, report)
                manifest_path = output_path.parent / "run-manifest.v1.json"
                if not manifest_path.exists():
                    atomic_write_json(manifest_path, {
                        "schema_version": "newrouge.impact-analysis-run-manifest.v1", "run_id": run_id,
                        "report_path": output_path.relative_to(root).as_posix(), "status": exc.code,
                        "failure_reason": {"code": exc.code, "reason": exc.reason}, "generated_at": report["generated_at"],
                    })
            except Exception:
                pass
        print(json.dumps({"status": "failed", "code": exc.code, "exit_code": exc.exit_code, "reason": exc.reason, "run_id": run_id}, ensure_ascii=False, sort_keys=True))
        return exc.exit_code
    except Exception as exc:  # pragma: no cover
        reason = ImpactIndexError("internal_error", str(exc))
        if output_path is not None:
            try:
                atomic_write_json(output_path, failure_report(locals().get("target_input", {}), locals().get("revision"), reason))
            except Exception:
                pass
        print(json.dumps({"status": "failed", "code": "internal_error", "exit_code": EXIT_CODES["internal_error"], "reason": str(exc), "run_id": run_id}, ensure_ascii=False, sort_keys=True))
        return EXIT_CODES["internal_error"]


if __name__ == "__main__":
    raise SystemExit(main())
