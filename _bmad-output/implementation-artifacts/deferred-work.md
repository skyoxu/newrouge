- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md`
  summary: Add deterministic integration tests for TOCTOU replacement, malformed resume/fork identity, and full handoff preflight through real mains.
  evidence: Current focused suites pass, but review found these implementation-hardening cases are not yet directly covered.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md`
  summary: Resolve the pre-existing warn-mode fork expectation mismatch in the marathon suite.
  evidence: Full marathon run retains one unrelated failure where expected rc=1 but actual rc=0.
- source_spec: none
  summary: Implement the Impact Analyzer Core with symbol indexing, TargetResolver, dependency and test mapping, risk classification, report emission, and run manifests.
  evidence: This is an independently testable producer slice that depends on a production-ready immutable Impact Index.
- source_spec: none
  summary: Implement bounded Godot Runtime Mapping for scenes, nodes, scripts, signals, resources, and binds edges.
  evidence: Runtime evidence is independently shippable and depends on the analyzer object model and edge contract.
- source_spec: none
  summary: Implement the read-only Knowledge Binding producer for ADR, Task, Contract, Decision, source reread, and SHA-bound evidence.
  evidence: Knowledge binding is independently reviewable and must preserve KCP authority while consuming analyzer evidence.
- source_spec: none
  summary: Complete adapter hardening, producer-to-consumer workflow integration, and final CAP-1 through CAP-6 acceptance.
  evidence: End-to-end integration and acceptance depend on the Index, Analyzer, Runtime, and Knowledge Binding slices being complete.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-index-core.md`
  summary: Register the Impact Analyzer unittest module in the default obligations hard gate.
  evidence: The analyzer tests exist and pass, but run_gate_bundle.py currently invokes only the Index and repository smoke modules.
- source_spec: none
  summary: Implement bounded Godot Runtime Mapping for Scene, Node, signal, resource, script, connection, and binds evidence.
  evidence: Runtime Mapping is an independently reviewable producer slice that depends on the corrected Analyzer object model.
- source_spec: none
  summary: Implement the read-only Knowledge Binding producer with KCP routing, source reread, and SHA-bound ADR, Task, Contract, and Decision evidence.
  evidence: Knowledge Binding is independently shippable after Analyzer correctness is established and must preserve KCP authority.
- source_spec: none
  summary: Complete end-to-end workflow integration and execute final CAP-1 through CAP-6 acceptance.
  evidence: Final acceptance depends on Analyzer, Runtime Mapping, Knowledge Binding, and existing adapters all being complete.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analyzer-production-readiness.md`
  summary: Complete the Analyzer CLI production harness with validated index discovery, immutable report/run-manifest publication, real success/failure E2E tests, and default hard-gate registration.
  evidence: CLI publication and gate integration are independently shippable operational concerns; splitting them keeps the current semantic correctness specification within the safe implementation context size.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analyzer-cli-production-harness.md`
  summary: Harden concurrent CLI publication against report/run-manifest TOCTOU races and guarantee internal-error run-manifest lineage.
  evidence: The current harness verifies single-process collision preservation; atomic create-if-absent and broad-exception manifest publication require a separate concurrency-focused slice.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-analyzer-cli-production-harness.md`
  summary: Reconcile real freeze artifact binding fields and extend CLI E2E to handoff validator and all consumer modes.
  evidence: Real freeze schema lineage is intentionally outside this synthetic-binding slice; cross-consumer and downstream handoff coverage remain pending KCP integration.
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-cli-artifact-integrity.md`
  summary: 补齐 Analyzer 失败报告中已知 index/binding 来源与被拒绝 revision 请求值的追溯。
  evidence: 旧 CLI failure_report 调用未传已读 index，invalid revision 也在赋值前抛错；本轮审查确认这是既有缺口。
- source_spec: `_bmad-output/implementation-artifacts/spec-kcp-impact-cli-artifact-integrity.md`
  summary: 在 adapter 崩溃一致性验收中明确残留发布目录锁的人工恢复规程。
  evidence: 本轮冻结规格排除进程强杀保证；不得将强杀后残留锁视为自动清理授权。
