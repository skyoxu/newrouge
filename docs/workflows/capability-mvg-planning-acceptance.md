# Capability / MVG Planning Acceptance Map

This file maps REQ-CAPABILITY-MVG-SKILLS-001 to executable evidence. It is an acceptance index only; formal Capability, Chapter 5 readiness, MVG manifest/runtime evidence, and milestone handoff remain owned by their existing artifacts.

## Current status

- Deterministic implementation/contract acceptance: implemented and exercised by the PR CI.
- Cross-project fixture: Harbor Relay, Taskmaster IDs 7 and 42, real Chapter 5 Extraction B/reconciliation/readiness path.
- Controlled real-model production acceptance: **blocked until the repository provides `OPENAI_API_KEY`**. The workflow intentionally fails at the credential gate and must not be interpreted as a semantic pass.
- A passing real-model run must execute the complete chain in `.github/workflows/planning-production-acceptance.yml`; mock output, a pre-seeded Capability, or a pre-seeded MVG manifest does not satisfy the requirement.

## Acceptance mapping

| AC | Evidence / status |
| --- | --- |
| AC01 | Chapter 3-5 remains independently executable; Harbor fixture reaches real Chapter 5 readiness before any Capability file exists. |
| AC02 | Capability prepare requires explicit task scope and fresh Chapter 5 readiness; partial/unready scope fails closed. |
| AC03 | Isolation runner contract enforces workspace-only reads, fresh invocation, no outside read and no model tools. **Final semantic acceptance still requires a passing real-model three-candidate run.** |
| AC04 | Source-block model batches account for every block; oversized blocks are explicit and never silently truncated. |
| AC05 | Candidate attempts/retries are bounded; invalid/missing candidates stop review rather than fabricating a winner. |
| AC06 | Review is a fourth fresh invocation; A/B/C order is reproducibly shuffled and the private mapping is outside the review workspace. No default union is produced. |
| AC07 | Capability apply changes derived Capability/topology/task `capability_refs` only; mature task intent ID/key is preserved by portability tests. |
| AC08 | Candidate validation requires full source accounting and explicit multi-membership rationale; upstream gaps remain questions instead of Requirement mutation. |
| AC09 | `plan-mvg` is independently callable and takes an explicit Capability file/hash; it never invokes Capability generation. |
| AC10 | MVG prompt/validator allows many Capabilities per journey and many journeys per Capability; coverage table and non-journey obligations are explicit. |
| AC11 | Initial manifests use the existing MVG schema; existing manifests evolve through guarded cumulative delta with stable IDs. |
| AC12 | Unknown task/Capability/Requirement refs are blocked; missing real contracts/entrypoints remain gaps/planned state, never fabricated passed evidence. |
| AC13 | Planning preserves evidence levels and never writes `passed` or `runtime_verified`; existing test bodies are copied into the planning input when referenced. |
| AC14 | Refresh rules separate semantic replanning, reference maintenance, structural scans and runtime evidence refresh. |
| AC15 | Run state, candidates, review, alignment, input freshness, budgets and stage outputs are durable; stale authority inputs block apply. |
| AC16 | Knowledge/Main/Workspace/runtime boundaries remain separate; planning apply does not publish KCP or claim runtime verification. |
| AC17 | Harbor Relay cross-project fixture uses non-contiguous Taskmaster IDs 7/42 and different gameplay semantics without newrouge business mappings. |
| AC18 | Capability apply performs capability-only Chapter 5 fingerprint rebind; any non-Capability fingerprint change blocks automatic rebind and formal MVG planning. |
| AC19 | Upstream semantic correction remains owned by Chapter 5 findings → Chapter 3 projection/task preview → affected Chapter 4/5 recheck; planning tools do not edit Requirements. |
| AC20 | MVG planned entrypoints require real owner task plus target path/symbol/inputs/state/assertions/implementation acceptance; nonexistent files cannot be `existing_verified`. |
| AC21 | Consumer migration is indexed in `workflow-portability-acceptance.md`; old replay is historical-only and new multi-membership topology is compiled/refreshed through current contracts. |
| AC22 | Prior derived Capability fields are scrubbed from Requirement/task analysis views; native source wording is copied unchanged; anonymous review mapping stays outside the reviewer workspace. |
| AC23 | Candidate/review retries, candidate active-time budget, total active-time budget, observable request limit and process-tree timeout termination are implemented; unavailable billing amount is never invented. |
| AC24 | MVG apply lists tasks requiring handoff applicability review. Applicable milestone-owned tasks use `plan-mvg rebind-handoff`, which reuses `milestone_incremental_handoff.py` against current Chapter 5 readiness and exact applied manifest. Ordinary tasks do not receive fabricated handoffs. |
| AC25 | Source-native capability/module wording is preserved in copied GDD source text while prior derived Capability answers are scrubbed. |
| AC26 | `run_planning_production_acceptance.py` executes actual selected Capability → independent MVG `openai-api` planning → existing plan validation. **Not satisfied until the real-model workflow passes with a configured credential.** |

## Production acceptance command

GitHub Actions owns the controlled run so the model credential never enters committed files:

```text
Planning Production Acceptance
  deterministic Harbor fixture
  -> Capability prepare
  -> three isolated same-model candidates
  -> anonymous independent review
  -> stable ID alignment + apply
  -> Chapter 5 capability-only readiness rebind
  -> independent MVG prepare/generate
  -> MVG plan validation
  -> evidence artifact upload
```

The run records model identity and observable request counts. If the API transport does not expose billing amount, the evidence must state that cost amount is unavailable rather than estimating it.
