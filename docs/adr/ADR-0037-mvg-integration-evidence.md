# ADR-0037: Bounded MVG Integration Evidence

- Status: Proposed
- Date: 2026-09-18
- Context: Per-task commits and gates do not alone prove that the integrated MVG behaves correctly across task boundaries.
- Decision:
  - Add an opt-in manifest connecting existing task IDs, handoff ownership, contract references and integration tests. Keep Taskmaster as task-state authority; do not introduce Epics.
  - Execute all declared tests against an isolated, identified commit or workspace snapshot. Positive nonempty test reports, exact class/suite identity, consistent counts, process success and no skipped tests are required for runtime verification.
  - Distinguish pilot and production manifest scopes plus planning, domain composition, scene method and engine input evidence. Production scope must declare at least three cross-task flows, implemented tests across domain/scene/engine evidence, and explicit exclusions. Neither pilot nor production scope establishes human gameplay acceptance outside its declared manifest boundary.
  - Use explicit path mappings only for conservative regression recommendations. Unknown impact never authorizes excluding tests; formal Impact and KCP remain unchanged.
  - Keep seeded mutation and hole/refill experiments optional. Keep existing delivery-profile gates, Chapter 6 review and MVG knowledge publication cadence.
- Consequences: Integration gaps gain an explicit owner and executable evidence with bounded runtime cost. Manifest scope and behavior assertions still need review. No branch-protection or release-policy change is introduced.
- Supersedes: None
- References: `docs/adr/ADR-0025-godot-test-strategy.md`, `docs/adr/ADR-0035-repository-knowledge-control-plane.md`, `docs/workflows/mvg-integration-acceptance.md`.

- Implementation refinement: recommendation endpoints use the selected input revision. Reuse Godot prewarm only within one snapshot after a passing suite. Reject already-resolved typed reward claims before applying resource changes; scene-method replay tests remain distinct from engine-input evidence.

- 2026-09-19 refinement: `m1-production.json` becomes the default executable scope. `reward-pilot.json` remains a narrow example. `full-mvg` means all required tests in the selected manifest, not unlimited whole-game proof.
