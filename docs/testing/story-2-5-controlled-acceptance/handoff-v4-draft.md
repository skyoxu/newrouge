# Reward handoff test

Each isolated test scenario has one fixed reward R, one process at a time, serial calls and an initially empty durable journal. Only the named injected crashes interrupt calls; storage otherwise succeeds. Restart preserves that scenario's journal. Scenarios never share a journal.

The only durable records are Accepted(R) and MapReturnCommitted(R). Each append is atomic and durable. A return means a MapReturnCommitted(R) append; rendering restored map state is not another return. At every observed journal prefix, each record occurs at most once and a return record requires an earlier acceptance record. Existing records must never be appended again.

The external harness invokes accept(R, call_id) or resume(R, call_id) with a fresh call_id. It records CallStart, Crash and CallComplete events outside the process in a single sequence. CallComplete carries that call_id and an observable ui_state: Idle or MapReady. Every non-crashing call must produce exactly one CallComplete within 10000 milliseconds of CallStart, measured by the harness's monotonic clock and including all recovery work. A missing, late, duplicate or wrong-call completion fails the test. No eligibility condition postpones this deadline.

accept must append missing acceptance, append any missing return and expose MapReady before CallComplete. If either record already exists, retain it without another append. In particular, first acceptance must expose MapReady, not merely write the return record.

resume with acceptance must append any missing return and expose MapReady before CallComplete. resume without acceptance must append neither record and expose Idle before CallComplete. resume after a committed return must expose MapReady without another return append. Neither operation requires another user action to finish.

Crash tests inject one crash before or after each append that is actually reached, or immediately before CallComplete. A crash before completion ends that invocation with Crash and no CallComplete. A process crash after CallComplete does not undo that completed invocation. Then restart, disable injection and invoke resume with a new call_id; the same completion deadline and state rules apply. Repeat this restart/resume cycle twice more without resetting the journal.

For each normal completion, verify call identity, completion count and time, ui_state, full journal order and record counts. For a crashed invocation, verify its ordered prefix, absence of CallComplete and the subsequent resume result. A deadline already missed remains a failure even if a later crash occurs. Test normal acceptance, idle resume, pending-return recovery, committed-return restoration, repeated accept and repeated restart/resume. Reject a result that reports completion while its required state or journal conditions are missing.
