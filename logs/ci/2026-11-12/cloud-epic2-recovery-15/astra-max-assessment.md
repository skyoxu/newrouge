# Clean Astra max proportionality assessment and implementation recheck

Reviewer: `/root/cloud_ac4_proportionality_review`, fresh context, gpt-6-astra, max reasoning. The user expressly requested this independent assessment. Initial baseline53e7eddd8c594b23b1620d2e737e84b2b12c88ab; later rechecks inspected the actual uncommitted implementation. All reviewer work was read-only: no code edits, project tests, old owner/driver execution, model dispatch, ledger or network action. This file is the parent's faithful summary of the reviewer's conclusions, not an execution certificate.

## Agreed scope

The reviewer agrees that a published-only PublishedHistoryVerification is an appropriate and proportionate AC4 implementation under the user's new explicit instruction. The difference from fresh original-owner execution authentication is covered by that instruction when clearly stated. No further unapproved major tradeoff was identified. Original AC4 and Accepted ADR0040 require reviewed current-image compensation and preservation; neither requires a fixed Windows owner to execute again. Proposed ADR0053 is not an additional business gate. Accepted ADR0050 needs an explicit separate branch contract while original proof semantics and anti-re-signing remain intact; ADR0056 records that branch without a routine approval loop.

Prefer a new subject/proof/delivery/claim with an immutable explicit profile in the existing DAG/codec/materials/review implementation. Do not duplicate the entire protocol, monkeypatch globals, add the new type to AUTHENTICATED_TYPES, or shrink public protection/history semantics merely to fit capacity.

## Required retained checks

- Actual journal/index/intent/receipt/catalog and complete publication ancestry/current relevant formal chain, not state/phase/receipt existence alone. Native03 reserved plus durable complete is a valid combination. Pending/unknown/damaged publication does not enter this route; no fallback after old authentication failure.
- Complete operation/embedded request/frozen/effects/scopes, old review and all raw support/protocol/output/runtime, capsule/retained binding and recorded policy/schema relationships. Keep the three request identities and readerOS0/parentOS2/workerOS1 distinct. No old-ticket re-signing.
- Independently rebuild the complete recorded public view, including source/candidate/targets/allocations, SourceSet/protection/selected history, ten inline and four retained-native fields. Shape/hash validation or copying the saved view alone is insufficient.
- All current-before, scope union, pending/old marker, Task join, cumulative/status/Acceptance/history/B-source, unique successor, leases and short writer checks. A historical after image must not overwrite today's legitimate edits.
- A new genuinely independent semantic review with its own version, actual complete input/output/schema/protocol/runtime and all current check obligations. Recorded23-check review DATA and the new handle cannot approve/reserve/apply a new compensation.
- Current root/policy/raw pins and same-read rechecks; old physical identities remain historical observations. Exact saved-input scopes can explain only this consumer's reviewed before images and owned exact effects.

Only original-execution-specific old interpreter/absolute module installation/old device-inode/Job repetition and noncurrent debug-prerequisite cold rereads can be removed from this branch. Do not remove any required source bytes or saved public semantics.

## Actual implementation findings and closure

The recheck found four necessary issues, all repaired in the inspected diff:

1. Commit context initially omitted the saved v3 profile. It now derives the profile from the verified saved subject before build, matching prepare/run/recovery dispatch.
2. Proof reference accepted either version without matching actual proof/subject. Exact ref/proof/subject version equality is restored; a targeted cross-version negative check passes.
3. The old DATA helper bound execution to request.txt, while public reconstruction read prompt.txt. The new factory now checks the exact full runner wrapper and independently rederives the complete original schema bytes.
4. Current bundle validation would reject the legitimate origins-after/catalog-before intermediate state. The limited recovery path now binds actual _SavedInputs, consumer operation/intent/proof, exact target before bytes, current scope/frame, allowed actual before/after and catalog progression, plus original complete/no marker/receipt/lineage. The common lineage algorithm was extracted without changing normal publication checks. No recursive verify_saved call or broad publication exemption was introduced. Normal proof production before a consumer intent exists retains the actual-current-chain path.

Final limited static recheck: no new necessary repair identified; these findings are closed at source-review level. The reviewer explicitly leaves targeted execution, real new semantic review/commit and AC4 completion to their actual evidence. This review does not grant model expenditure or financial actions.
