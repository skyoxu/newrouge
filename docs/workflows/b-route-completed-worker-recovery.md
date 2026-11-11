# Completed-worker recovery

This explicit standalone tool recovers missing coordinator projections from an
already completed and admitted first-scope MVG worker. It never starts a worker,
runner or model. It does not retrieve provider results and cannot complete a lost
request from a partial protocol, process absence or a worker self-report.

The original runtime, worker, selection, checkpoint, audit and input owners remain
byte-identical. Do not import this tool from those frozen owners: changing their
bytes or transitive import closure invalidates existing execution/source rules.
The standalone CLI loads those owners from the explicit original repository and
rejects foreign cached project modules. An equal-byte relocated checkout is not
an interchangeable origin for an original proof.

## Supported state

- Explicit `3b-mvg-v1` run, pending first scope and generation 1, no selected
  checkpoint, terminal block, selector input or selection attempt.
- Original lifecycle/job/process/result remain in place. Every relevant worker
  PID is absent or observably exited. A live, reused live, or inaccessible PID
  blocks; the tool never stops a process or claims PID reuse is original identity.
- All paid calls retain their original reservation IDs, request identities,
  counts, lineage costs, execution/generation, limits and active elapsed time.
  Existing outcomes and admissions cannot be replaced.
- An unknown row can acquire an outcome only from one original completed mailbox
  message after its exact original reserve acknowledgment, validated by the
  unchanged full reserved-call verifier. Original output, host execution, complete
  protocol, binding and canonical draft must already exist. No missing model or
  host artifact is reconstructed. A failed message does not resolve unknown.
- Every original worker result must be admitted with exact artifact hashes;
  original machine, semantic, execution, reservation, lineage and local ledger
  admission checks all run before eligibility. Partial results are blocked.

Any unresolved unknown row blocks publication of the whole proposed state. No
refund, new reservation, new execution, replacement, cleared terminal or released
campaign/stage ceiling is provided. Capability recovery is explicitly rejected:
replacing its conservative unknown timeout debit with a shorter completed elapsed
time could release time budget under the existing accounting contract.

## Commands

Use the same interpreter, approved dependencies and `high`/NoSite environment as
the original run. The executable below is the standalone script, not the existing
`generate` command.

```powershell
$env:NEWROGUE_CODEX_REASONING_EFFORT = 'high'
$env:PYTHONNOUSERSITE = '1'
python -B scripts/python/b_route_worker_recovery.py --repo-root <original-repo> --run-id <run> --operation inspect
```

`inspect` writes nothing, obtains no lock, validates current input and original
source rules, and returns `blocked`, `ready`, or `no-op` with a sealed plan identity.
Missing evidence is not permission to call `generate` again. Preserve blocked runs
and their charges. Exit code 2 means blocked.

Only a ready plan can be explicitly published:

```powershell
python -B scripts/python/b_route_worker_recovery.py --repo-root <original-repo> --run-id <run> --operation apply --expected-plan sha256:<inspect-identity>
```

`apply` validates and obtains the existing native coordinator byte lock, recomputes
the complete plan, and rejects changed evidence/configuration or a blocked plan.
The native single-byte mutex is excluded from ordinary evidence hashes because
Windows forbids its second-handle read while owned. Its original byte and shape
are checked before locking; other run files remain raw-hash-bound.

A new immutable recovery journal seals the exact raw original run preimage, full
proposed state, plan/source identity and exact pre/post hashes. Existing lifecycle,
mailboxes, outputs, canonical drafts, bindings and dispatch sidecars are untouched.
Only `run.json` publishes the recovered completion/admission projections. The old
coordinator can subsequently validate and skip that admitted candidate instead of
recreating its lifecycle. Starting other workers is a separate action.

If the publisher's return becomes uncertain, inspect the sealed transaction:

```powershell
python -B scripts/python/b_route_worker_recovery.py --repo-root <original-repo> --run-id <run> --operation publication-status --expected-plan sha256:<inspect-identity>
```

This read-only operation compares exact raw old/new state hashes and reports
`not_committed`, `committed`, or `unknown_third_state`. It never redispatches or
republishes. This establishes only local publication status, not current semantic
qualification or provider outcome/billing. Reinspection is required after any
interruption or evidence change; stale plans cannot be replayed as writes.

## Verification boundaries

Focused assembly tests explicitly patch fixture origin/process/admission validators;
they verify error flow, CAS, invariants and fault handling, not real admission.
The completed-outcome transport test preserves the original full protocol/binding
verifier and rejects altered output. Its protocol is synthetic and makes zero
external model calls. The separate complete-proof fixture preserves all original
machine/semantic/reservation/protocol/binding checks with a synthetic worker envelope.
No offline fixture demonstrates a paid provider result or makes an interrupted
production run eligible. Cooperative coordinator locking and repeated snapshots
assume no separate hostile writer racing the filesystem checks.
