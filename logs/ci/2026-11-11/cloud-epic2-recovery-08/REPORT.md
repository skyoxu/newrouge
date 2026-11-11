# Story 2.10 receipt recheck diagnostic repair

The branch remains build/cloud-epic2-recovery-20261111. Work starts from db452a0c; only the known raw-identical workflow EOL noise existed. The consolidated material list is operation-specific and is not used as a global prerequisite here.

An actual temporary receipt is read, then deleted by the explicitly synthetic published-reader seam before the CLI performs its context stability recheck. Both direct/dev-cli cases returned blocked/file_not_found but lost resume_ref. The new regression failed first. The CLI now routes both receipt reads through its same local diagnostic enrichment, preserving original reason/stage and any existing reference. It does not recreate the deleted receipt, issue a success context or change admission/financial behavior.

Five focused affected methods pass: deletion on reread (direct and dev-cli subcases), initially missing receipt (both entries), normal exact receipt/reader binding, wrong operation/changed receipt, and original pending-owner diagnostics. No unrelated suite was rerun.

The first temporary harness summary incorrectly computed passed=-1 by subtracting two failed subtests from one method. That original failed result remains unchanged. red-count-normalization.json records the correct interpretation: one method failed in two subcases, zero passed methods. The local helper's future count calculation was corrected; no original failure was relabelled passed.

The receipt deletion is real local filesystem behavior; upstream publication/validation remains explicitly synthetic. This proves the CLI error boundary only, not an original historical operation, provider semantics, Windows durability or formal Story acceptance. No private package was needed, no new material/authority gate was introduced, and no old operation/model turn/network-policy workaround/main merge/remote write/Fast setting change occurred.
