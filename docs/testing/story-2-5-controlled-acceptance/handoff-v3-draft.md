# Reward handoff test

This toy test has one fixed reward R, one process at a time and serial harness calls. New R starts without durable Accepted(R) or MapReturnCommitted(R) records. Each journal append is atomic and durable. Only injected crashes interrupt calls; storage otherwise succeeds.

A completed return means the first durable MapReturnCommitted(R) append. Showing the map after restart is restoration, not another return. The journal must never contain more than one Accepted(R) or MapReturnCommitted(R) record for R, and a return record must never exist without acceptance.

The harness invokes accept(R) or resume(R). Each call is a state-machine operation. One harness step is one state-machine transition. With crash injection disabled, each call must emit CallComplete within ten harness steps; leaving a pending return beyond this boundary is a failure, not waiting for eligibility.

accept(R) must persist acceptance and complete the return before CallComplete. resume(R), when acceptance exists, must complete any missing return and show MapReady before CallComplete. When the return already exists, both calls must show the restored MapReady state without appending a second return. resume(R) without acceptance must show Idle and append no acceptance or return record.

Inject a crash before and after each durable append, and after the return append but before CallComplete. A crashed call emits no CallComplete. Preserve the journal across restart. Then disable crash injection and invoke resume(R), applying the same ten-step completion rule. Repeat restarts and resume calls. Verify the journal, transition count, visible state and CallComplete boundary in every case.
