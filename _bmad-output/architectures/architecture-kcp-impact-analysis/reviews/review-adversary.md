# Adversarial Architecture Re-review (final)

## Verdict

**PASS — no remaining architecture-level divergence blockers.**

The latest patch closes the previously identified convergence gaps. Two independent downstream implementations are now constrained to the same behavior for the requested dimensions:

- `index_id` uses exact RFC 8785/JCS bytes, a golden vector, and is the concrete immutable index path key; artifact and manifest hashes are verified.
- KCP lineage has explicit byte-level hash sources (`frozen_context`, canonical decision set, published catalog) and `publication_generation` source semantics; `knowledge_binding` is mandatory for successful coding/review reports.
- The status set and numeric exit map are closed, including `dirty_state`, `unsupported_target`, `invalid_manifest`, and `lock_unavailable`.
- Canonical target kinds include `acceptance`; resolver identity/alias/path rules are explicit and fail closed.
- Index/run manifest names, fields, atomic publication order, UTC discovery policy, and cross-date lookup are defined.
- Git-tree blob bytes are canonical; worktree/sparse/submodule/ignored/generated policies are explicit.
- Lock schema, stale-owner rules, cross-host polling, retry counts/backoff, and atomic replace behavior are specified.

## Non-blocking implementation follow-ups

These do not create architectural divergence once implemented against the contract; they should be covered by Phase 1 tests:

1. Execute the JCS/index-id golden vectors and verify manifest ordering/hash fixtures.
2. Add fixture tests for all target-kind identities, alias precedence, method signatures, and evidence-anchor grammar.
3. Exercise run/index manifest atomic publication and cross-date discovery under concurrent writers.
4. Exercise Windows PID reuse, stale/fresh locks, sharing-violation retry exhaustion, and exit-code propagation.
5. Add adapter tests proving exact forwarding and rejection of wrong revision, index hash, frozen-context hash, and KCP lineage.

These are implementation/test obligations, not reasons to keep the architecture in a conditional gate.

