# Bounded Windows execution and independent Epic2 progress

## Actual Windows result

Commit92c5532536b77d38730c2b59e9fe5e06b4662445 adds a fixed selector to the existing Windows runtime workflow. Its exact-branch push produced one new run, [43211116759](https://github.com/skyoxu/newrouge/actions/runs/43211116759), attempt1/job131158674714. The connected GitHub API confirms completed/success at that exact SHA. The broad runtime step was skipped; only WindowsRecoveryTests plus WindowsCompensationTests executed.

All4 methods passed, no failures/errors/skips,287.578 seconds, no source changes and no new model calls. The runner was Microsoft Windows Server2025/10.0.26100, Python3.12.10 on GitHub-hosted Azure, not Aliyun. Exact test names/timings and the actual helper result parsed from the job log are in `windows-actual-summary.json`; decoded complete job text, run identity and artifact metadata are also retained. The decoded log is UTF-8 text with normalized line endings, not an attestation of raw service log bytes.

| Existing method | Native behavior established |
| --- | --- |
| WindowsRecoveryTests.test_fixed_process_crash_then_public_recover_completes_without_replaying_after | Child exits at the actual target-write barrier; restarted public recovery completes, and a subsequent known-complete recovery is no-op with unchanged formal bytes in the fixture |
| WindowsCompensationTests.test_actual_windows_origins_sharing_refusal_and_release_resume | kernel32 sharing refusal retains before bytes and blocks resolution/reading; releasing the handle permits original recovery |
| WindowsCompensationTests.test_actual_windows_pending_delete_refusal_retains_block_until_cleanup | A real Windows deny-delete handle preserves the published pending fence and blocks resolution until cleanup succeeds |
| WindowsCompensationTests.test_process_exit_and_restart_derive_resolution_from_retained_formal_evidence | Child crash/restart uses retained formal evidence and derives the correct original-operation compensation successor |

These4 tests use explicit synthetic native/admission/review fixtures. They prove the corresponding actual Windows kernel/process/storage behavior, not provider execution, all cross-scope concurrency, machine reboot/power loss, or the entire real-model chain. Original Story2.8 hasAC1–5; its Windows fault criterion isAC5. Original Story2.10AC6 is the target-Windows/all-prerequisite contract; these results contribute only their demonstrated scope. They do not turn the whole Epic green.

The existing workflow permissions/dependency setup and PR/manual runtime default remain unchanged. No Codex credentials or API key were transferred to CI. No new formal contract, protection policy, threshold, model authorization or fiscal owner was added. The exact branch/path trigger avoids a broad default run and does not rerun when these evidence documents alone are pushed. A nonfatal preexisting checkout warning about GIT_CONFIG_GLOBAL=NUL is retained; checkout and the exact-SHA assertion succeeded. It was not used as a reason to change unrelated settings or repeat the successful run.

The original artifact remains on GitHub:13941297656,89,238 bytes, service SHA256 ba244098fb217e84f0757732c08a0dbc68b8fa5155cb7d340c844c3acc804bad. The connected download returned a file reference, but the supported local file-transfer helper failed with generic `download failed`. Local ZIP bytes/hash are therefore not claimed. No network workaround/retry occurred. Complete decoded job output and the native4-test summary were retained separately; `artifact-local-transfer-limit.json` states the limit without signed URLs or transfer tokens.

## Real2.10 work independent of Windows

Two actual fresh CLI processes read genuine receipt-sealed clone inputs without a native/provider/service seam. The exact clone consists of9 real formal/non-log source files, with no historical review logs, journal or operation state copied. The complete9 inputs are preserved in `published-clone-input/` with their raw manifest, so this observed published-read case no longer depends on the external1.1GB original dataset.

The exact clone read completed exit0 in4.956s, returning the same genuine receipt, plan revision2 and formal_adoption=true. The reader initialized only ordinary coordination lock metadata. A separately created derivative with one extra newline in its plan2 file was rejected exit2 in0.750s with digest_mismatch, exact expected/actual hashes and plan resume_ref. Both readers left all clone formal/source bytes unchanged. The genuine original published root was never modified. `real-clone-observations.json`, `clone-exact.json` and `clone-changed-plan.json` retain actual commands/results.

This adds real no-local-history published clone and immutable-target rejection evidence for the public contract/AC3, beyond the prior synthetic clone seam. It does not replay apply/recover/publication, prove global planning completion, grant completed-unit reuse or change readiness/runtime/default B.

## New explicit single-Capability input and current accounting

The genuine existing controlled source `exclusive-resolution-v15.md` is present in the repository. Its current CRLF bytes are7,059/SHA46453447335769fbf4d8001ade9f2090a8799809380ea0df026a0637bc67338a; the preserved original LF source was7,044/SHA7e5e1fe8... . No source was edited to make a match. Native normalized8 block identities equal the original set.

`single-capability-input/capability.json` is explicitly a new complete planning input context for that entire existing controlled source. Its kind=capability/one ID is declared in the pending-audit planning contract, and no block or original obligation is excluded. It is not a historical completed item, a new formal allocated definition, a Task or a relabeled m4 scope. The original m4 all-scope input, checkpoint,13-call history and empty registry remain untouched.

The real public source prepare succeeded, then the real public source account succeeded with1 file/8 blocks/7 proposals, accounting_complete=true and unresolved=[]. Original first-projection business fields were reused unchanged as unreviewed proposals. These results are mechanical current accounting, not independent audit or formal3B preparation.

The first account attempt01 failed because the caller script supplied a string prepared_ref instead of the service's exact typed path/raw_digest object. Its original candidate/report/event/trace are preserved. A new deterministic attempt02 corrects only that reference; no business field or old failure was overwritten, no model was called and no unknown outcome was retried. `single-capability-material-result.json` records the exact successful references.

## Why old audit reuse does not currently admit the new native execution

The actual captured old3A identity and current identity differ in Python/executable, packages and transitive tool entries, despite the same requested openai/gpt-6.1-sol/high model. Current CPython is3.12.14; the old capture was Windows3.12.10. The recovery dataset also lacks the old audit's complete raw request/runner/identity/proof files at its referenced prefix. These facts are in `singlecap-audit-reuse-assessment.json`. The published-history reader can use genuine receipt sealing for publication, but that is not a current independent native3A audit grant.

No old proof was re-signed and no global new data collection/fiscal dependency is requested. A fresh current audit of the existing complete source through the existing owner is the normal available route. Its actual extraction request preflight fits45,113 UTF8-byte-upper-bound tokens, and the complete-source comparison lower-bound request fits67,821 at the unchanged96,000/1MiB gates. The actual comparison must be remeasured with genuine extraction output; no fake output or approval was inserted. Full request/schema/input/prompt and measurements are retained under `singlecap-audit-request-preflight/`.

For one source, a fresh audit requires the existing two phases: one extraction plus one global comparison. Neither was dispatched/reserved. A Linux-bound audit cannot silently become a current Windows audit because the existing owner binds the actual executable/tool/package identity. Starting two reviews on the wrong eventual native host would not solve that condition. The new source/accounting/input packet is ready for the intended current native host; full current audit and a genuine native run remain outstanding. No new native run or registry entry exists and no new numeric allowance is claimed from historical290 or the resolved compensation's spent3.

The exact next audit command shape on a legitimately authenticated intended host is:

```text
py -3 scripts/python/dev_cli.py b-route-sources --root <intended-native-root> --stage audit --run-id cloud-singlecap-audit-20261112 --scope-id controlled-exclusive-resolution-v15 --attempt-id audit-01 --accounted <genuine-current-account-report> --runner scripts/python/codex_isolated_model_runner.py --expected-model openai/gpt-6.1-sol --citation-guidance full-block --request-budget 2 --active-budget-seconds 1500 --timeout-seconds 600
```

Set NEWROGUE_CODEX_REASONING_EFFORT=high for that owned child process and use the existing subscription through an official login on that host. Do not copy the current Cloud auth file or use an API key. If checkout/runtime identities change, regenerate only the current mechanical preparation/accounting under the existing owner from the same genuine source/proposals. The pending contract must use the actual successful current audit report reference, then formal `plan-mvg --stage prepare --input-stage 3b --planning-contract ...` returns the real prepared_ref. Continue generate/adoption through the original native coordinator; its existing run/lineage caps and failed/unknown occupancy remain binding. Do not invent the future native call count or seed the registry.

The GitHub job proved an available target-Windows test route; it intentionally carries no model credentials and did not execute a provider/native generation chain. Establishing the appropriate subscribed native execution host is a separate remaining execution need. It does not block the completed clone work or the source/accounting packet, and it is not a subscription shortage or an added review/governance requirement.

## Preserved boundaries

Current original compensation remains terminal, proof policy580ab96f.../84 pins unchanged, original2 plus additional1 occupied, old refusal/unknown and all original34 review records retained. Existing56 affected tests are reused; this continuation changes only CI selection/harness and evidence, not product source or business semantics. No Fast, separately billed API, broad/full suite, main merge, unauthorized ledger action, Aliyun/S2 or historical unknown replay occurred. Stories2.9/2.10 remain in-progress, with the concrete progress and remaining real audit/native qualification stated above.
