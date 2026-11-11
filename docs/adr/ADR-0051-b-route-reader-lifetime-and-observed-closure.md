# ADR-0051: Frozen reader ownership and observed evidence closure

- Status: Accepted for implementation; current execution qualification pending
- Date: 2026-11-08
- Scope: Story 2.6 auxiliary adoption review/prepare/reserve/inspect
- Authority: Root's adjudicated Story 2.6 Step 4 patch groups B1-B6/B8/B10/E1/G1.

## Decision

Restore the existing read-only, fail-closed adoption contract without changing
native eligibility, Task identity, source profiles, call accounting or funding.
The private reader transport reuses `WindowsWorkerJob` and the existing stdin
start-gate pattern. Its unnamed, non-inherited Job is configured before launch;
the exact held reader handle must be assigned before the gate releases any
project source execution. Assignment failure has no unowned fallback or breakaway.
Authenticated Python/Git CreateProcess descendants inherit Job ownership.

The host deadline remains 3600 seconds, independent of every preserved native
verifier/model timeout and every logical or unknown paid charge. Separate binary
stdout/stderr owners preserve delivered bytes. A single five-second cleanup
window covers Job termination/accounting, held-reader wait, and cancellation of
only recorded pipe workers. Direct exit with remaining Job activity is failure.
Normal completion requires Job `ActiveProcesses == 0` plus successful IO cleanup.
Only real Job accounting can establish that the owned tree is empty. No taskkill,
PID tree discovery, PID-based descendant termination or retry is introduced.

If an API/IO error prevents confirmation, fail closed with `cleanup=unconfirmed`,
retain bounded structural diagnostics, and accept no capture. The last Job
handle close remains a parent-death backstop; it is not fabricated evidence that
cleanup completed. Bounded failure cannot promise quiescence under arbitrary OS
failure. Root must inspect an unconfirmed cleanup before later operations reuse
the affected reader, evidence or store. Independent authorized work can continue.
Cancellation preserves its original exception after the bounded cleanup attempt.

Observable extension-import filenames (`.pyd` and platform extension suffixes)
join the read audit's byte closure and closing rechecks. This covers observable
imports after installation of the hook. It does not claim complete OS/DLL
dependency closure, already-loaded interpreter modules, hostile in-process
monkeypatching, or broker/WMI-created processes outside the authenticated chain.

Native rejection/timeout metadata contains fixed outcomes, safe identifier
reasons/phases, exit status, cleanup status, byte counts and raw digests, with at
most four bounded native rejection records. It excludes raw request/argv/source
programs and native tracebacks. CLI JSON uses ASCII escapes so its original
Unicode values survive Windows redirected locale encodings.

## Shared formal Graph semantics

Native and formal Graph consumers use `_b_route_flow_graph` for declared nodes,
endpoints, owners, branch/boundary correspondence, required reachability, SCC
exits, parts and UI/human obligations. Native adapters keep the actual source
membership predicate in its original order. A formal local record has no ledger
context; its existing bundle source owner applies that same predicate to the
already authenticated ledger. Legacy text-only plans retain their prior branch.
The graph schema and native frozen R5/R10/R19/R22 sources remain unchanged.

## Evidence epochs

Current host policy pins the actual source/protection/inventory/Graph/transport
support owners. A changed policy or reader cannot reuse or re-sign an earlier
host review as current. R41's six successful public stages and original op02
remain valid historical facts for their original source epoch. They do not prove
these repaired sources executed successfully. New deterministic Windows tests
and, where Root authorizes it, a new native read/review need their own source-bound
evidence. No old operation, proof, scope claim or unknown charge is edited/retried.

The maintained hard/Windows gate selects the deterministic adoption, operation,
candidate/record suites and all self-contained native-reader boundary methods,
including the new genuine Windows Job tests. Six unchanged pinned R22 owner
integration methods require the private preserved source and remain separately
selected by Root; standalone CI does not invent or download that authority. Compilation/static review is not a test or native pass.
Default route, formal adoption, publication, readiness and runtime flags stay
under their existing gates. B7's nullable resume contract and B9's deferred lease
question introduce no new gate here.

## Primary API references

- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
- [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
- [Job basic accounting](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)

These are the primary references retained by the preceding read-only lifecycle
investigation. Their presence is not evidence of an actual Windows API test.
