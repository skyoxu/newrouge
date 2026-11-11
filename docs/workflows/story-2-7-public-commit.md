# Shared public commit owner (Story 2.7)

Status: R43 implementation integrated offline onto qualified Story 2.6 in R48.
Story 2.7 execution and formal acceptance remain pending; no default-route activation is asserted.
Active baseline: `4d0aa32195b10347d92370b82c673043e550224b`, isolated R48.
That R47 base qualifies Story 2.6 AC1-5 only, with no adoption/runtime grant.
R43 offline35 retains its original source identity; it is not R48 test evidence.
R42 and its recovered raw preimages remain historical evidence, never acceptance.

Authority: original epics Story 2.7 AC1-6; architecture planning-records.md
sections 1-3 and 46-63; ADR-0040. The six formal record identities and Taskmaster
state ownership remain unchanged. A commit intent is auxiliary process evidence,
not a seventh formal record or a new model/recovery database.

## Public route and actual supported bootstrap

The existing `b-route-adoption` route adds explicit `apply`, `verify`, `publish`
and `read` stages, using the same direct and dev_cli parser/service owner.
Only the existing review-prepare/prepare stages accept `--request`.

```powershell
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage apply --operation-id OP-1
py -3 scripts/python/b_route_adoption.py --root . --stage verify --operation-id OP-1
py -3 scripts/python/b_route_adoption.py --root . --stage publish --operation-id OP-1
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage read --operation-id OP-1
```

Apply requires the original reserved operation and a fresh initial native,
protection, authority and complete independent host-review recheck. It does not
create a reservation or dispatch work. `read` uses the formal receipt's scopes;
the API `read_committed(root, scope_ids=...)` also supports explicit scopes.
No operation log is needed to resolve a formal receipt on a clone.

The current producer supports a real independently admitted native plan together
with policy and genuinely empty origins in the same reviewed frozen request.
This supports zero Tasks, absent or complete empty triplets, empty frozen A and
no Chapter5 witness. It never invents a Task, scene or readiness. It does not
claim an independent policy-only preparation/review producer or substitute a
fake native plan for one. Later policy and Task/binding adapters must use the
same commit owner and explicit authorization contract. Current write targets
are the immutable-byte formal target family produced by Story 2.6; Task-writing
producers are not added here.

The original five Story 2.6 stage results keep formal_adoption/readiness/
runtime_verified false. Commit apply/verify also grant no publication. Only a
validated complete publish/read reports formal_adoption; readiness, runtime and
default_b_enabled stay false. A recorded policy value does not activate routing.

## Intent, closure, pending and failure ordering

`_b_route_commit` owns commit actions; `_b_route_commit_projection` drafts products;
`_planning_apply_journal` continues owning the original operation/index pair.
The original v1 operation, request bytes, allocations and history are retained.
The new strict `commit-intent.schema.json` has an explicit auxiliary v1 identity.

Each original operation directory may additionally contain `commit.json` and
`commit.pending.json`. Unknown names, damaged schemas or mismatched bindings
block; the service never repairs them. The original pending.json remains the
exact complete operation index. `active_operation_inventory` derives active
claims without deleting history or reusing allocated identities.

Ordering is:

1. Outside metadata, replay the original native admission and independent host
   review. Recheck the complete context and future candidate bundle while all
   original before images still exist. Reuse the existing native activity and
   coordinator locks and the shared metadata/ordered scope leases.
2. Persist the exact pending marker, then the sealed intent with all original
   before bytes, full observed source/authority/absence/membership closure,
   current review policy and receipt draft. No formal file is written first.
3. Recheck before every target. Accept only its exact recorded before or after;
   skip after. The intent moves to applied only after all targets are after.
4. Re-read actual targets, current authority, stage relationships and cumulative
   bundle obligations. Persist the immutable minimal receipt; then verified.
5. Under the same shared writer protection, save the complete final catalog bytes
   in publishing before replacing catalog last. All affected scopes select the
   same receipt; unrelated heads remain. An unchanged related catalog frame may
   be rebased onto a valid unrelated publication; retain prior catalog attempts.
6. Revalidate actual formal files/catalog, persist published then complete, and
   finally remove the exact owned pending marker. A cleanup failure leaves the
   marker blocking even when catalog and complete intent are already present.

An intent's hash checks declared integrity; it is not cryptographic attestation
of a physical collection event. Required observations are reconstructed from
the immutable reviewed dependencies/native closure and original frozen refs;
re-signing an intent cannot simply drop those observations. Subsequent explicit
steps recheck that closure, allowing only this operation's authorized target
before/after transitions. They do not reinterpret self-written targets through
Story 2.6's before-only capture or use a historical summary as qualification.
Full semantic protocol replay stays outside metadata; exact support bytes and
current policy are checked again at side-effect boundaries. Unfinished later
steps reacquire original activity/coordinator locks before shared write leases.

Only a complete intent, absent owned marker, unchanged receipt and actual valid
formal chain release the active claim. Pending disappearance, receipt existence,
an after target, or a phase string alone is insufficient. Unknown legacy marker
or journal scopes retain their existing conservative block. No implicit retry,
automatic recovery, compensation, model dispatch, unknown replay or refund is
introduced. An explicit same-operation command may finish known before/after
work; unknown edits stop and remain intact. Complete same-content actions are
no-ops and do not rewrite target/receipt/catalog side effects.

Terminal proof also connects the saved complete catalog image to the actual
current catalog through retained publication before/after images. A later valid
revision can replace the original heads without resurrecting its active claim.
A successor whose catalog is already visible but pending cleanup still proves
older publication history, while its own active claim continues blocking reads.
An invented later catalog image cannot pass merely because its phase says complete.
These catalog digests prove publication history; they are not Task freshness keys.

## Formal consumption without local proof logs

The new records `published_bundle` context shares the existing strict schemas,
typed reference/identity resolver, definition/Task relationship checks and actual
target revalidation. The default candidate `validate_bundle` is unchanged and
still resolves every required original external proof.

In committed context only, a historical log locator may be consumed without its
local bytes when its complete locator/file set is inside an unchanged formal
target and every declared file is bound by that target's actual receipt authority.
This is a published-chain interpretation, not a global reference skip. Formal
typed refs, actual target bytes and relevant non-log source/authority bytes are
still verified. Relevant current source manifests/ledgers keep their owning
checks. Local native clear/epoch state is not a new publication authority.

Related scopes expand through logical definition ownership and complete shared
Task applicability. Only the related external/current source closure contributes
to semantic identity. The semantic key includes relevant heads/owners/Task rows,
policy, projected related Task definitions, authority and supported reader/schema
rules; the whole catalog hash/revision is an observation, not every Task's key.
The reader holds shared protection, checks relevant pending, validates actual
records, then re-reads the same catalog identity. Coordination can initialize
ordinary local lock metadata on a clone; no formal file is written or repaired.

Existing formally declared task_definition_projection targets are re-proved by
the existing codec/Task projection owner. Only actual Task/direct-subtask status
is excluded; view definitions, Acceptance, row order and other metadata remain.
This reader capability does not add a Task write producer or permit unfinished
raw-before conflicts to be merged away.

## Evidence and limits

The original i6 checkpoint at baseline f699c12e114706c132f9779af0a310993ab2d8b3
reported eight projection methods, three image methods and one existing reserve
regression. Its initial Windows ACL failure remains historical evidence. Those
results are not R43 execution or Story acceptance.

Authored R43 tests cover actual storage/schema/locks with native eligibility
explicitly replaced by a synthetic fixture; semantic executions are constructed
protocol bytes, never provider execution. Windows tests use actual sharing
handles and a fixed owned-TEMP child with deliberate os._exit(73), then a fresh
process rechecks/continues the retained operation. They do not prove machine
reboot/power-loss behavior, database isolation or protection from arbitrary
noncooperating editors. Replacement flushes full temporary bytes before rename
and rechecks the installed bytes. Formal acceptance still needs Root's actual
targeted Windows runs, current integrated native prerequisites, public operation
evidence and formal Step4/Step5; none was executed by the source author.

R43 static follow-up includes existing-governance reads for plan-only publication,
resumed frozen-request equality against the independently reviewed preview and
support closure, saved publication lineage, and corresponding negative controls.
The fixed process fixture starts a fresh apply through its explicit synthetic
capture seam; it never calls an actual native verifier or model. The marker and
plain owned-TEMP ancestry checks run before project imports.

The maintained deterministic gate registers all three commit test modules once,
retaining existing funding, worker and inherited-pipe selectors. It does not
grant actual native eligibility. Original producer, paid/unknown accounting,
79/290 and default A remain under their original owners.
