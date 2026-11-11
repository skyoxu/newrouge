# Native 3B content to formal plan projection

`_b_route_adoption_projection.project_content(content, allocations)` is the
single typed adaptation owner between the actual native 3B content schema and
the formal plan fields. It validates the full native input schema, performs no
allocation/write/model call and leaves both inputs unchanged. It does not grant
admission, adoption, publication, readiness or runtime acceptance.

The return value contains exactly source_identity, requirements, definitions,
logical_references, requirement_verification, requirement_route_memberships,
requirement_evidence, evidence_source_refs, coverage_table and applicability.
Requirement and Flow maps are complete and one-to-one for their respective
native domains. Command/state maps are optional: absent maps preserve those
native definition IDs. Other allocation fields are not interpreted here.

## Typed identities and logical owners

Only the relevant semantic channel is renamed: requirement_id(s), flow_id(s),
and each definition's own typed id. Node, boundary, edge, loop, source-block,
Capability, evidence, textual content and prior_requirement_ids are preserved.
The same literal in different domains is not a global replacement key.

Each proposed LogicalDefinitionUse resolves the exact triple
`(kind, definition_id, proposed_owner_key)` to a declared native definition and
the host's allocated plan_id/plan_revision. Unknown owners are rejected; no
first-match, fallback or guessed owner is permitted. Existing full formal
LogicalDefinitionUse values retain their original definition ID and owner/revision,
even if the literal also names a new definition. Top definition owner keys are
removed from the projected body and remain available in the original native proof.

Graph, branches, handoffs, state owners, UI/human responsibilities, source blocks,
Capability IDs, four parts, observable result and verification targets remain
structured data with their original complete semantics. There is no reduction to
entry/success text, JSON-in-string carrier or fabricated boundary/handoff.

## Compatible formal schema extension

The existing plan.v1 Flow item selects its new branch only when graph is present.
The else branch is the complete prior legacy Flow shape; existing records remain
valid. The Graph Flow branch reuses `newrouge.b-route-flow-graph.v1` references
rather than copying its definitions. Its four-part constraints retain the prior
formal requirements. Requirements additionally allow the native optional
prior_requirement_ids array, preserving its original values.

A plan with any Graph Flow requires native_candidate_ref, a public PlanningProofRef
owned by planning_proof. The adoption service must construct and bind it to the
actual verified handoff file, exact raw digest, and `#/proposal/content` locator.
It must not trust an arbitrary caller-supplied reference or treat structural
validation as proof of native eligibility.

The complete native out_of_scope_requirement_ids, selected_dependencies,
unresolved and implementation_objects remain in that original reference. They
are not silently dropped, reclassified as prose, or copied into a private carrier.
The projector's ten-field result is not a standalone lossless substitute for the
whole native document. The caller must keep and verify the full original proof.

## Shared registry and formal local checks

Formal-only schema resources still require only the original formal resource set.
When the local shared flow-graph file exists, it is additionally registered and
its actual bytes participate in the cache identity. It is optional for legacy
records; without it Graph plans fail explicitly through local resource resolution.
Adding/removing its bytes changes the resource cache key. No network retrieval
occurs. Auxiliary callers continue to require the full original auxiliary set,
including adoption-operation; the graph resource is not registered twice.

This does not add a formal entity to the codec identity registry or allow callers
to select an auxiliary root schema through a formal-only validator. Because the
shared Graph input schema also permits proposed uses, the formal record owner
recursively rejects any residual proposed_owner_key after structural validation.
The existing owned-reference traversal resolves native_candidate_ref through the
same public resolver; its cycle checks also exclude formal commit/catalog proofs.

## Verification boundary

Tests use the existing test_b_route_candidate native fixture and its full native
schema. MatrixFixture is used only for a separate legacy formal-record regression,
never as native candidate eligibility. Exact field preservation, typed literal
collisions, existing owners, unknown owner rejection, proof reference requirements,
formal-only absence/cache behavior and retained prior requirements are covered.
All tests are offline structural/adapter evidence; the original selected-run owner
and current native proofs remain prerequisites for public adoption preparation.
