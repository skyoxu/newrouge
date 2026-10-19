---
title: '瀹℃煡鍙戠幇鐨?Capability/MVG P1/P2 闂淇'
type: 'bugfix'
created: '2026-10-19'
status: 'done'
review_loop_iteration: 0
 baseline_commit: '7cdd9dd5e107cc6c74443c755150feb1fe521ef3'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/docs/workflows/mvg-integration-acceptance.md'
---

<frozen-after-approval reason="human-owned intent; do not modify unless human renegotiates">

## Intent

**Problem:** Capability/MVG 宸ヤ綔娴佷粛瀛樺湪棰勭畻浼扮畻涓庡疄闄呴噸璇曚笉涓€鑷淬€侀€€褰逛换鍔¤繘鍏?MVG 璇佹嵁銆佸叡浜?handoff 鍙樺寲鏈繀浣挎仮澶嶅け鏁堛€佸彇娑堣姹傚彲鑳藉湪鍙戝竷鍓嶇珵鎬侊紝浠ュ強鑻ュ共鍥炲綊瑕嗙洊鍜?Windows 骞跺彂 fixture 缂哄彛銆?
**Approach:** 缁熶竴澶嶇敤鏉冨▉浠诲姟鐘舵€佷笌 schema 鍏煎 helper锛屼慨姝?prepare/dispatch 鐨勯绠楄璐︼紝鎵╁ぇ鎭㈠渚濊禆闂寘锛屽湪姣忎釜闃舵鍜屽彂甯冨墠鎵ц鍙栨秷闂搁棬锛屽苟琛ュ厖 adoption銆佸苟鍙戞浛鎹㈠拰鍘嗗彶 fixture 鐨勫畾鍚戞祴璇曪紱涓嶆敼鍙?GDD銆佷换鍔℃暟閲忋€丆apability/MVG 涓氬姟璇箟鎴栧凡鏈夋湭鎻愪氦鏀瑰姩銆?
## Boundaries & Constraints

**Always:** 淇濈暀鐜版湁宸ヤ綔鍖烘敼鍔紱tasks.json 鏄换鍔＄姸鎬?SSOT锛涘疄闄呭彂鍑虹殑璇锋眰鍜岄噸璇曞繀椤诲彲瀹¤涓斾笉瓒呴绠楋紱閫€褰?鍙栨秷/superseded/orphan 浠诲姟涓嶅緱浣滀负鏈夋晥 MVG 杈撳叆锛涘彇娑堝悗涓嶅緱鍙戝竷 completed锛涙祴璇曞拰鏃ュ織缁熶竴浣跨敤 UTF-8 涓?logs/**銆?
**Ask First:** 鏃狅紱鐢ㄦ埛宸叉槑纭姹傚叏閮ㄤ慨澶嶃€?
**Never:** 涓嶉噸缃垨涓㈠純宸叉湁鏀瑰姩锛涗笉杩愯鐪熷疄妯″瀷锛涗笉鎵╁厖浠诲姟鎴栦慨鏀?GDD銆佹寮?Capability銆佹寮?MVG manifest锛涗笉寤虹珛绗簩濂椾换鍔＄姸鎬佹垨璇佹嵁鎼滅储閫昏緫銆?
## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| BUDGET_RETRY | source/task chunks with retry limit | prepare estimate includes all chunks, synthesis and bounded retries; actual reservations count attempted calls exactly once | fail closed with durable budget reason |
| RETIRED_TASK | view contains cancelled/retired task | MVG scope excludes it and preserves active master mapping | reject inconsistent task identity |
| SHARED_HANDOFF | unselected shared baseline flow changes | recovery dependency hash changes and old result is not reused | require fresh resolution |
| LATE_CANCEL | cancellation arrives after stage return before publish | result is cancelled, never completed/published | retain cancellation evidence |
| WINDOWS_PARALLEL | sibling workers write temporary run state | each fixture uses an isolated path or atomic retry; no PermissionError | record deterministic test failure |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_capabilities.py` -- prepare request-count estimate and task-view chunk accounting.
- `scripts/python/openai_isolated_model_runner.py` -- bounded batch retry loop and durable attempted-request accounting.
- `scripts/python/_mvg_capability_generation.py` -- complete MVG scope context and task-state filtering.
- `scripts/python/_capability_input_integrity.py` -- canonical task-state/schema helper to reuse for master and task views.
- `scripts/python/_mvg_capability_recovery.py` -- dependency boundaries and recovery reuse decision.
- `scripts/python/_project_health_planning.py` -- cancellation lifecycle, stage completion, result publication.
- `scripts/python/_mvg_global_audit.py` -- adoption/revoke/reopen audit behavior.
- `scripts/python/_mvg_worker_lifetime.py`, `scripts/python/_mvg_capability_worker.py` -- worker cleanup boundaries.
- `scripts/python/tests/test_mvg_capability_append.py` -- historical append fixtures and budget/retry contract.
- `scripts/python/tests/test_project_health_planning.py` -- cancellation and publish race coverage.
- `scripts/python/tests/test_mvg_recovery_review_integration.py` -- recovery and shared-flow dependency coverage.

## Tasks & Acceptance

**Execution:**
- [x] Add/reuse canonical task status and schema compatibility helpers, then filter MVG context and add regression tests.
- [x] Correct capability request preflight and durable dispatch accounting for task chunks, synthesis, retries, timeouts and transport failures.
- [x] Include all scope-affected shared baseline handoffs in recovery dependencies and test unselected-flow invalidation.
- [x] Recheck cancellation after every stage and immediately before result publication; add race tests.
- [x] Add adoption reopen tests, isolate Windows parallel fixtures, and explicitly migrate or quarantine historical append fixtures without weakening current contracts.
- [x] Run targeted regression, compile and diff checks; do not invoke real models.

**Acceptance Criteria:**
- Given any bounded retry/transport failure, when prepare or dispatch completes, then estimate and durable accounting include every attempted request exactly once.
- Given retired task-view entries, when MVG scope is built, then only active master tasks remain in effective evidence.
- Given any shared handoff affecting the scope, when recovery checks run, then changed dependency hashes prevent reuse.
- Given cancellation before publish, when the worker returns, then the job is terminal cancelled and no completed result is published.
- Given parallel Windows tests, when workers run concurrently, then no shared temporary file replacement race remains.

## Verification

- `py -3 -m unittest scripts.python.tests.test_capability_input_integrity scripts.python.tests.test_project_health_planning` -- expected: all pass.
- `py -3 -m unittest scripts.python.tests.test_mvg_evidence_scope_projection scripts.python.tests.test_mvg_recovery_review_integration` -- expected: all pass.
- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract` -- expected: all pass.
- `py -3 -m py_compile` on changed Python modules -- expected: success.
- `git diff --check` -- expected: success.

## Suggested Review Order

1. Review the canonical task-state and prepared-input filtering changes first.
2. Review request budgeting, retry accounting, and runner failure persistence.
3. Review recovery dependency expansion and cancellation/publish guards.
4. Review the targeted regression coverage and the final verification results.

