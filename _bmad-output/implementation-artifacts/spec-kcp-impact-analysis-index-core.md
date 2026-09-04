---
title: 'KCP Impact Analysis Index Core'
type: 'feature'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
baseline_commit: '985f095e4975e7cf1c4477993447c2cfd4f2ed5c'
context:
  - '_bmad-output/specs/spec-kcp-impact-analysis/SPEC.md'
  - '_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/ARCHITECTURE-SPINE.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
  - 'AGENTS.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** KCP Impact Analysis 已有契约与 Adapter Handoff，但仓库还没有可复用的、修订绑定的 Impact Index；后续 TargetResolver 和 Analyzer 因此无法安全地读取统一 source universe，也无法拒绝脏、过期或不完整证据。

**Approach:** 实现一个只读、确定性的 Windows-safe index builder。它从可信 Git tree 构建完整 source manifest，记录每个纳入文件的 kind/parser/hash，并以 JCS 派生 `index_id` 发布不可变 `impact-index.v1.json` 与 `index-manifest.v1.json`；任何 revision、配置、实现版本、哈希或锁不匹配均 fail-closed。

## Boundaries & Constraints

**Always:** 以完整 40 位 Git revision 和 `git ls-tree`/blob 为 canonical source；repository-relative POSIX path；显式 scan roots、suffix 与 exclusions；UTF-8 无 BOM；SHA-256；稳定排序；JCS golden vectors；原子写入；index identity、artifact hash、manifest hash 可复核；成功输出只放 `logs/ci/<UTC-date>/impact-analysis/indexes/<index_id>/`。

**Ask First:** 若实现需要改变现有 KCP publication/current/LKG、ADR-0035、Impact contract、现有 sidecar schema，或需要纳入未被架构列出的 source class，必须先暂停并请求批准。

**Never:** 不扫描工作树未跟踪文件作为事实；不读取 branch 名替代完整 revision；不修改业务源、KCP authority 或 freeze；不覆盖既有不同 identity 的目录；不静默复用 stale/dirty index；不实现 Analyzer、TargetResolver、Runtime mapping 或 Knowledge Binding。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | clean trusted revision, valid config, no conflicting lock | immutable index and manifest with matching hashes | exit 0 |
| DIRTY_OR_MISMATCH | worktree/blob, revision, config, or implementation identity differs | no successful publication; diagnostic JSON/log | `dirty_state`/`revision_mismatch`/`stale_index` |
| LOCK_CONTENTION | fresh same-host or cross-host lock | never overwrite another builder; bounded retry | `lock_unavailable`, exit 16 |
| COLLISION | target index path exists with different bytes/identity | preserve existing artifact and abort | `index_identity_collision`, exit 10 |
| INVALID_SOURCE | unreadable, escaping, symlink-ambiguous, or manifest-incomplete path | fail before publication | `source_read_failure`/`invalid_manifest` |

</frozen-after-approval>

## Code Map

- `scripts/python/_knowledge_catalog_builder.py:47-208` -- existing canonical JSON/hash, path normalization, Git tree/blob snapshot and deterministic source classification patterns to reuse without changing KCP behavior.
- `scripts/python/build_knowledge_catalog.py:24-37` -- existing same-directory temporary JSON + `os.replace` pattern; adapt only for the new immutable index writer.
- `scripts/python/freeze_knowledge_context.py:28-39,100-208` -- fail-closed hash/revision/source-reread conventions and canonical-byte handling; read-only reference.
- `scripts/python/impact_analysis_handoff.py:20-155` -- stable impact failure code map and exact-byte SHA-256 identity conventions; do not duplicate conflicting codes.
- `_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md:70-110,330-365` -- authoritative index lifecycle, manifest, invalidation, lock, atomicity, and exit contracts.
- `_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md:41-60` -- artifact naming and lineage boundary for the future analyzer; this slice must emit only index artifacts.
- `scripts/python/tests/` -- unittest style and temporary-repository fixtures; add focused index tests without changing existing KCP tests.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/impact_analysis_index.py` -- add shared canonical path/hash, JCS identity, Git-tree manifest, lock, schema validation, and atomic publication helpers -- keep builder and future analyzer consistent.
- [x] `scripts/python/build_impact_index.py` -- implement CLI for explicit `--revision`/verified ref, config, output root, reuse, and fail-closed diagnostics -- provide the Phase 1 entrypoint.
- [x] `scripts/python/impact_analysis_config.v1.json` and `scripts/python/impact_target_aliases.v1.json` -- define versioned scan/exclusion/parser policy and a valid empty kind-scoped alias table -- make identity inputs explicit.
- [x] `scripts/python/tests/test_impact_analysis_index.py` -- cover manifest determinism, JCS golden vectors, stale/dirty/revision mismatch, path policy, lock lifecycle, collision, and atomic publication -- prove edge cases before implementation is accepted.
- [x] `scripts/python/tests/fixtures/impact-index-id-jcs-v1.json` -- store canonical input, bytes, and expected digest vectors -- prevent serializer drift.

**Acceptance Criteria:**
- Given the same clean Git revision and unchanged config/implementation identity, when the builder runs twice, then both manifests have the same `index_id`, source-manifest hash, sorted paths, and source hashes, and the second run reuses only the exact immutable artifact.
- Given a dirty worktree, missing tracked blob, revision mismatch, malformed config, or manifest path escape, when the builder runs, then it exits non-zero with the specified stable code and publishes no successful index.
- Given a fresh or cross-host lock, when publication is attempted, then the builder never overwrites the owner, obeys the bounded retry policy, and reports `lock_unavailable` when retries are exhausted.
- Given an existing index directory, when identity or artifact bytes differ, then the builder preserves the existing artifact and returns `index_identity_collision`.
- Given a successful build, when the index and manifest are reread, then schema, artifact SHA-256, revision, config revision, implementation revision, and every source entry validate without consulting KCP current/LKG or mutating repository authority.

## Spec Change Log

## Design Notes

`index_id` is content-derived from the full revision, source-manifest hash, index schema, analyzer implementation revision, and config revision. The UTC date is archival metadata only; discovery must use the manifest and exact identity. Worktree bytes are accepted only when every included tracked blob matches the trusted Git tree. Generated, ignored, submodule, sparse-checkout, and dynamic runtime inputs remain outside this slice unless explicitly marked authoritative by the policy.

## Verification

**Commands:**
- `py -3 -m unittest scripts/python/tests/test_impact_analysis_index.py` -- expected: all focused index tests pass.
- `py -3 scripts/python/build_impact_index.py --help` -- expected: CLI exposes explicit revision/config/output controls and stable failure description.
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated` -- expected: existing KCP generated state remains unchanged and passes.

## Suggested Review Order

**构建入口与信任边界**

- 显式 revision 驱动不可变构建
  [`build_impact_index.py:25`](../../scripts/python/build_impact_index.py#L25)

- Git tree/blob 与工作树复核
  [`impact_analysis_index.py:302`](../../scripts/python/impact_analysis_index.py#L302)

- 发布前复用与最终校验
  [`impact_analysis_index.py:1262`](../../scripts/python/impact_analysis_index.py#L1262)

**策略与工件校验**

- 配置规范化及重复项拒绝
  [`impact_analysis_index.py:473`](../../scripts/python/impact_analysis_index.py#L473)

- 别名表结构与冲突校验
  [`impact_analysis_index.py:567`](../../scripts/python/impact_analysis_index.py#L567)

- 原子写入与工件哈希绑定
  [`impact_analysis_index.py:896`](../../scripts/python/impact_analysis_index.py#L896)

**并发与回归证据**

- 锁竞争和所有权安全
  [`impact_analysis_index.py:996`](../../scripts/python/impact_analysis_index.py#L996)

- Index Core 全量边界测试
  [`test_impact_analysis_index.py:337`](../../scripts/python/tests/test_impact_analysis_index.py#L337)

- 真实 source universe 构建复用
  [`test_impact_analysis_index_repository_smoke.py:38`](../../scripts/python/tests/test_impact_analysis_index_repository_smoke.py#L38)
