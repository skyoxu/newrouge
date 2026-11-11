# B-route operation lease support

`scripts/python/_b_route_operation_leases.py` is an independent support adapter.
It does not complete Story 2.6 or grant acceptance, publication, or integration
authority. Full operation reservation, journal, and identity integration waits
for the actual Story 2.5 handoff proof and the operation owner's contract.

## Caller contract

Call `operation_leases(repo_root, metadata_dir, scope_dirs,
prepare_under_lease=callback)` as a context manager. Supply absolute paths to an
existing repository root, an existing contained metadata directory, and a
nonempty complete mapping from canonical scope keys to existing contained
directories. The adapter creates no directories and infers no business scopes.

Scope keys are case-sensitive, lowercase ASCII strings of 1 to 128 characters:
`[a-z0-9][a-z0-9._:-]{0,127}`. This is an adapter ordering contract, not a business
ID schema. Keys are validated without normalization and acquired in ascending
Python string order. All cooperating callers must use the same metadata
directory and a stable one-to-one scope-key-to-directory mapping; the adapter
cannot prove that a supplied set is complete or that other callers use it.

Paths must be existing directories beneath the supplied root. Validation rejects
parent traversal, device namespaces, alternate data streams, reserved Win32
names, trailing dots/spaces, symlinks, junctions, and other reparse points,
including ancestors. Physical directory aliases, duplicate scope directories,
and metadata/scope aliases are rejected. Existing lock paths must be ordinary
files with one link. All inputs are checked before any lock acquisition.

The caller must keep the directory topology and lock paths stable throughout
validation and use. The existing path-based lock primitive cannot defend against
an adversary replacing directories or files concurrently. This adapter does not
add a second mutex system or claim such protection.

## Lock lifetime and failure behavior

The adapter reuses `_mvg_capability_checkpoint.coordinator_lock` unchanged,
including `capability-coordinator.lock`, Windows `msvcrt.LK_NBLCK`, and the existing
`ValueError("capability_coordinator_busy")` contention behavior. No retry, timeout,
stale-lock removal, or lock unlinking is added.

1. Acquire the short metadata lease.
2. Acquire every supplied scope lease in canonical key order.
3. Invoke the required zero-argument `prepare_under_lease` callback while metadata
   and every scope lease remain held.
4. Release metadata, then yield the callback's unchanged result.
5. Keep every scope lease through the caller's context body, then release them
   in reverse acquisition order.

Contention, acquisition failure, callback failure (including `BaseException`),
and context-body failure unwind acquired leases. The OS releases a crashed
owner's handles; the lock files remain in place. The adapter itself only allows
the existing primitive to create/initialize its lock files. It allocates no IDs
and writes no formal state. The callback belongs to the future operation owner;
it must be short and must implement its own business transaction/rollback
semantics. Lease cleanup does not roll back callback writes or a crashed process's
business state.

## Focused verification

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B scripts/python/tests/test_b_route_operation_leases.py
git diff --check
```

The stdlib-only module uses per-test UUID temporary directories beneath its own
test directory and OS child processes. It verifies ordering, real callback lock
boundaries, metadata availability during long work, scope contention, partial
failure cleanup, callback result/exception handling, process termination release
without unlinking, path/reparse rejection, and unchanged formal fixture bytes.
The suite prints the actual platform and interpreter. POSIX execution is not
Windows acceptance. It does not use shared root-thread scratch, models, network,
authentication, databases, accounts, or the full Story 2.6 workflow.

On 2026-11-05, the focused module passed all 11 tests in 4.826 seconds on actual
Windows (`win32`, `nt`), CPython 3.12.10 AMD64. This included real Windows byte-lock
contention, terminated-owner release, and NTFS junction rejection. The initial
sandbox-identity run failed during temporary-directory setup with WinError 5;
the successful run used the authorized worktree owner. Its empty failed fixtures
were removed. This evidence applies to this support component at public base
`cb55bb592a5027c1f39768ca08b1c7e49346b3d9`, not full Story 2.6 acceptance.
