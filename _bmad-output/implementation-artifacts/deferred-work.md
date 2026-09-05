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
  summary: Add a successful analyze_impact CLI integration test covering index discovery, frozen context binding, report output, and run manifest hashes.
  evidence: Review found only analyzer unit tests; the production CLI success path is not exercised by the current verification suite.
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
