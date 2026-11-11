# Known synthesis failure recovery

This recovery continues the original c4 candidate-2, generation 1, execution 1.
It does not qualify Story 2.5 by itself. The native independent admission,
two-candidate selection, full MVG reservation and three-candidate MVG remain
required. The original v15 unknown request remains charged and unresolved.

## Retained evidence

The R7 source at `d7d0dad0acef19ea829da39a52738865de256ff9` produced native
calls 4 and 5. Candidate-1 was independently admitted. Call 5 completed the
candidate-2 batch, with raw output SHA-256
`ffac881cfef08028ac5d7ca25b433dd1493b1f041449f70bad8b6e9fb2f25423`.
Call 6 ended with a recorded provider `invalid_json_schema` rejection of the
`parent_draft_identities` array constant. Its failed receipt, protocol, schema,
worker and 408.219 seconds remain unchanged. Another earlier call using an
array constant succeeded; the observed rejection does not establish universal
provider behavior.

The new versioned producer policy changes only transport constraints. It
compiles primitive array constants to item constraints and exact lengths. The
host still validates the complete raw carrier against the original exact
schema and ordered draft chain. It does not repair model output. Historical
requests retain their exact old schema, prompt, source envelope and receipts.

## Bounds and transaction

The explicit source epoch archives the previous run bytes and verifies both
frozen source trees. Only archived completed paid bindings and the actual old
admission artifacts may use the old source identity. New calls use the new
source identity. The synthesis recovery retains all six paid slots, local
append count 2, clocks, candidate lineage, seed, original input and funding.
An exclusive claim precedes state changes; a committed marker binds the new
record. Partial or ambiguous transactions cannot dispatch automatically.

The next local attempt is 3 and the next global reservation is 7. It reuses
the actual completed batch and makes at most one new synthesis attempt for
this interrupted proposal. Existing native business repair rules still own
any later genuine semantic findings. The old worker and stage costs are
preserved in their original locations; the new worker has a separate lifecycle.

The native candidate time limit is 2700 seconds plus the declared 1200-second
synthesis pool. Candidate-2 has consumed 251.25 + 408.219 = 659.469 seconds,
leaving 3240.531 seconds under that formula. Each new synthesis is still
bounded by 1200 seconds, remaining native allowance and worker deadline. The
run's 2400.407-second host active clock is cumulative evidence, not a new
per-candidate subtraction rule. No clock is reset.

Campaign accounting remains `55 + c4_count + m4_count`, with a limit of 290.
At preparation, 61 paid-or-unknown logical slots remain occupied. Capability
cannot reserve beyond 43 total slots if the entire original MVG ceiling of
192 is to remain available. Failed and unknown calls are never refunded or
used as successful admission proof.

## Verification scope

Offline fixtures cover producer constraints, original schema rejection,
historical source routing, known-failed retention, input and artifact tampering,
partial commits, duplicate attempts and time or budget rollback. They are not
real model qualification. Actual qualification additionally requires original
native replay, actual high runtime configuration, complete bound inputs and
outputs, independent review and native selection. Returned runtime configuration
does not attest the provider's actual backend model, reasoning or request count.
