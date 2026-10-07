# Closed-Loop Testing

Current first-phase loop:
1. Run `scripts/sc/run_review_pipeline.py`.
2. If it fails, open `repair-guide.md`.
3. Fix the first hard failure only.
4. Rerun the narrowest step first.
5. Rerun the full review pipeline only after the narrow step is green.

Repair guidance automatically expands the failed step's existing structured artifacts:
- Unit failures expose failed TRX test names, recorded stack/source locations, and a narrow rerun command. Each unit invocation archives its summary and explicitly emitted TRX in its own `sc-test/unit-artifacts/<attempt-id>/` directory. Recovery prefers the pipeline snapshot. A matching run marker plus `test_rc` alone is insufficient: the selected TRX must have been emitted by the current dotnet command. Restore/compilation failures do not reuse a retained TRX; compilation errors remain in the saved unit log.
- Acceptance failures expose the failed child check, its report errors, and referenced test/task/ADR/contract/overlay paths when those paths are recorded. Saved child reports take precedence over mutable live copies.
- Model review findings expose their existing severity, claim, required action, verification, and evidence. Required findings are retained without a five-item cutoff; deferred lower-priority findings continue through the existing debt workflow. Advisory producer results can still carry detailed repair actions when the reviewer requests follow-up.
- Missing, corrupt, or mismatched child artifacts retain the existing recovery guidance. Diagnosis adds no user input or extra gate and does not change the producer verdict.

Stop-loss rules:
- Do not rerun the full pipeline before isolating the failing step.
- Do not lower hard gates before identifying the failing contract.
- Do not let `llm_review` become the first diagnostic tool when `sc-test` or `sc-acceptance-check` already failed.
