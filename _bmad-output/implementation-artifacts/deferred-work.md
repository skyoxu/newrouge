- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md`
  summary: Add deterministic integration tests for TOCTOU replacement, malformed resume/fork identity, and full handoff preflight through real mains.
  evidence: Current focused suites pass, but review found these implementation-hardening cases are not yet directly covered.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md`
  summary: Resolve the pre-existing warn-mode fork expectation mismatch in the marathon suite.
  evidence: Full marathon run retains one unrelated failure where expected rc=1 but actual rc=0.
