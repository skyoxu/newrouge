# Workflow Source Summary: Chapter 3

Generated from the template repo `workflow.md` by `scripts/python/update_workflow_chapter_skills.py`.

- Canonical English name: Phase 1: Task Triplet Initialization
- Source line span: 204-413
- Heading count: 14
- Command-like line count: 24
- Artifact/reference line count: 0

## Headings

- 3. Phase 1: Task Triplet Initialization
- 3.0 Choose the Chapter 3 route first
- 3.1 Declare authoritative planning inputs
- 3.2 Build the complete source block ledger
- 3.3 Semantic projection A in bounded batches
- 3.4 Normalize coarse task intents from validated semantics
- 3.5 Generate and enrich task candidates
- 3.6 Audit semantic sink coverage
- 3.7 Compile and review the task triplet patch
- 3.8 Build and validate the authoritative triplet
- 3.9 Refresh workspace topology at every run end
- 3.10 Chapter 3 stop-loss
- 3.11 Optional regression check
- 3.12 Chapter 3 semantic boundary

## Command And Artifact Signals

- `py -3 scripts/python/build_source_ledger.py --mode <init|add> --prd-path <path> --gdd-path <path> ...`
- `py -3 scripts/python/extract_requirement_anchors.py --mode <init|add> --ledger-input logs/ci/task-generation/source-blocks.v1.json`
- `py -3 scripts/python/project_semantics_from_sources.py prepare --max-blocks-per-batch 40 --max-chars-per-batch 24000`
- `py -3 scripts/python/project_semantics_from_sources.py compile`
- `py -3 scripts/python/validate_semantic_conservation.py --stage projection`
- `py -3 scripts/python/normalize_task_intents.py --mode <init|add> --id-prefix <prefix>`
- `py -3 scripts/python/audit_task_intents_quality.py`
- `py -3 scripts/python/generate_task_candidates_from_sources.py --mode <init|add> --id-prefix <prefix>`
- `py -3 scripts/python/enrich_task_candidates.py`
- `py -3 scripts/python/audit_task_candidate_coverage.py`
- `py -3 scripts/python/validate_semantic_conservation.py --stage closure`
- `py -3 scripts/python/compile_task_triplet.py --mode <init|add>`
- `py -3 scripts/python/compile_task_triplet.py --mode <init|add> --write`
- `py -3 scripts/python/build_taskmaster_tasks.py`
- `py -3 scripts/python/task_links_validate.py`
- `py -3 scripts/python/check_tasks_all_refs.py`
- `py -3 scripts/python/validate_task_master_triplet.py`
- `py -3 scripts/python/backfill_semantic_review_tier.py --mode conservative --write`
- `py -3 scripts/python/validate_semantic_review_tier.py --mode conservative`
- `py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter3 --trigger-run-id <run-id> --begin-run`
- `py -3 scripts/python/dev_cli.py run-chapter3-guarded --trigger-run-id <run-id> --triplet-status-on-success <passed|blocked|unknown> -- <command...>`
- `py -3 scripts/python/attest_chapter3_triplet_baseline.py`
- `py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter3 --trigger-run-id <run-id> --refresh-local --triplet-status <passed|blocked|unknown>`
- `py -3 scripts/python/run_chapter3_regression_check.py <business-repo> --prd-path docs/prd --gdd-path docs/gdd --gdd-path _bmad-output/gdd.md`
