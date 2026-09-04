---
title: 'KCP Impact Analysis Index Production Readiness'
type: 'bugfix'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
baseline_commit: '985f095e4975e7cf1c4477993447c2cfd4f2ed5c'
context:
  - '_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-index-core.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/ARCHITECTURE-SPINE.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
  - 'AGENTS.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Impact Index Core 的 fixture 已通过，但真实 source universe 有 36 个 included tracked text files 带 UTF-8 BOM，构建会以 `source_read_failure` 停止；新增 identity files 尚未进入 HEAD，也无法直接用当前 revision 做提交前 smoke。

**Approach:** 仅移除这 36 个文件的 BOM prefix，保持其余字节和 EOL；补齐 BOM/identity 回归，并在临时 Git repo 提交拟交付输入后执行正式 build/reuse smoke，不向工作区留下索引工件。

## Boundaries & Constraints

**Always:** 保持 `utf-8-no-bom`、Git-tree/blob authority、完整 revision、JCS identity、不可变 publication 和 fail-closed；BOM 清理只删除开头 `EF BB BF`；smoke 覆盖全部 scan roots、identity files 和真实 tracked contents，并调用正式 builder。

**Ask First:** 若发现除已识别 36 个 included files 外还需修改其他业务文件，或需要改变 source rules、scan roots、identity schema、failure-code contract、KCP authority/current/LKG，必须暂停并请求批准。

**Never:** 不用 `utf-8-sig` 放宽读取；不做全文件重编码或 EOL 归一化；不纳入 `.gd`、`.feature`、`.csv`；不实现 Analyzer、TargetResolver、Godot Runtime、Knowledge Binding；不修改或提交 `docs/121.txt`；不 publish KCP generated state。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| REAL_REPOSITORY_BUILD | 临时 Git repo 含全部真实 scan roots 与 identity files | 正式 builder 发布可验证 index/manifest；相同输入 exact reuse | source、identity 或 hash 不一致即失败且不发布 |
| INCLUDED_TEXT_BOM | 普通 included text 以 `EF BB BF` 开头 | 拒绝 source universe | `source_read_failure`，不发布 |
| IDENTITY_BOM_OR_MISSING | config/alias/implementation identity 带 BOM或缺失 | 拒绝 identity | `invalid_manifest`，不发布 |
| REUSE_MISS | source universe 合法但 exact artifact 不存在且指定 reuse-only | 不创建 artifact | `stale_index`；不得误报 source failure |

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analysis_index.py:503-572` -- `build_source_manifest` 区分普通 source BOM (`source_read_failure`) 与 identity (`invalid_manifest`)；保持严格策略。
- `scripts/python/impact_analysis_index.py:1073-1160` -- 正式 build/reuse/publication 路径；repository smoke 必须调用此入口或 CLI，不复制实现。
- `scripts/python/build_impact_index.py:20-84` -- 生产 CLI、稳定退出码和 `--reuse-only` 入口。
- `scripts/python/impact_analysis_config.v1.json` -- scan roots、source rules 与 11 个 identity files 的 SSoT；不扩大文件类型。
- `scripts/python/tests/test_impact_analysis_index.py:43-916` -- 复用现有 fixture、publication、lock 与 hard-gate tests，新增 BOM/identity cases。
- `scripts/python/run_gate_bundle.py:331` -- 已注册 focused index suite；保持 hard gate 可发现性。
- `Game.Core/**`, `Game.Core.Tests/**`, `Game.Godot/**` -- 当前 policy 纳入的真实文本中共有 36 个 BOM 文件；仅做 prefix-only 清理，其他 41 个未纳入 policy 的 BOM 文件保持不动。

## Tasks & Acceptance

**Execution:**
- [x] `Game.Core/**`, `Game.Core.Tests/**`, `Game.Godot/**` -- 对 config 判定为 included 的 36 个 tracked text files 精确删除 BOM prefix，并用 byte-level 前后检查证明除前三字节外内容完全一致。
- [x] `scripts/python/tests/test_impact_analysis_index.py` -- 增加普通 included text BOM、identity JSON BOM、missing identity 与 reuse-miss 回归，证明稳定错误分类及零 publication。
- [x] `scripts/python/tests/test_impact_analysis_index_repository_smoke.py` -- 从真实工作树组装临时 Git repo，纳入全部 scan roots 与 identity files，提交后运行正式 build、schema/hash validation 和 exact reuse；自动清理且不改变仓库 `logs/**`。
- [x] `scripts/python/run_gate_bundle.py` -- 若独立 smoke suite 未被现有 module discovery 覆盖，则显式注册，避免生产 readiness 只在手工验证中存在。

**Acceptance Criteria:**
- Given 当前 config 与拟提交 source universe，when 执行 BOM census，then included non-binary files 均无 BOM，且另 41 个 excluded BOM files 未改变。
- Given 临时 commit 包含拟提交实现和真实 scan roots，when 执行 build 与 reuse，then `index_id` 相同，schema、revision、source hashes 通过，真实工作区无长期 artifact。
- Given普通 source BOM、identity BOM、missing identity 或 reuse miss，when 运行 builder，then 分别得到 `source_read_failure`、`invalid_manifest`、`invalid_manifest`、`stale_index`，并且没有成功 publication。
- Given现有 43 个 focused tests 与新 readiness tests，when hard gate 执行，then 全部通过且既有 lock、collision、dirty-state、revision-binding 行为无回归。

## Spec Change Log

## Design Notes

真实 smoke 不用缺少新增 identity files 的当前 HEAD。它按 Git tracked set 复制真实 scan roots/root identity，加入当前实现/config/alias，提交临时 revision 后调用生产 builder；不得暂存用户工作树或依赖长期工件。

## Verification

**Commands:**
- `py -3 -m unittest scripts/python/tests/test_impact_analysis_index.py scripts/python/tests/test_impact_analysis_index_repository_smoke.py` -- expected: existing and production-readiness suites all pass.
- `py -3 scripts/python/build_impact_index.py --help` -- expected: CLI remains importable and documents stable failures.
- `py -3 scripts/python/validate_knowledge_control_plane.py` -- expected: KCP kernel/unit validation passes without publishing or requiring the known-stale generated state.
- `git status --short` -- expected: only intended source/test/spec changes plus preserved untracked `docs/121.txt`; no generated index or KCP publication files.

## Suggested Review Order

**Source-universe validation**

- Enforces Git-tree authority, strict classification, and fail-closed source reads.
  [`impact_analysis_index.py:573`](../../scripts/python/impact_analysis_index.py#L573)

- Validates immutable index and manifest bytes before any reuse is accepted.
  [`impact_analysis_index.py:745`](../../scripts/python/impact_analysis_index.py#L745)

**Build, reuse, and publication safety**

- Coordinates revision binding, exact reuse, locking, and atomic index publication.
  [`impact_analysis_index.py:1152`](../../scripts/python/impact_analysis_index.py#L1152)

- Exposes the production entry point and stable fail-closed exit-code contract.
  [`build_impact_index.py:20`](../../scripts/python/build_impact_index.py#L20)

- Reclaims stale locks without allowing replacement races during release.
  [`impact_analysis_index.py:909`](../../scripts/python/impact_analysis_index.py#L909)

**Production-readiness evidence**

- Exercises a temporary real Git repository through the formal build and exact-reuse path.
  [`test_impact_analysis_index_repository_smoke.py:59`](../../scripts/python/tests/test_impact_analysis_index_repository_smoke.py#L59)

- Covers BOM, identity, reuse-miss, collision, dirty-state, and publication regressions.
  [`test_impact_analysis_index.py:335`](../../scripts/python/tests/test_impact_analysis_index.py#L335)

- Records prefix-only BOM cleanup against the trusted baseline for auditability.
  [`audit_impact_index_bom_cleanup.py:30`](../../scripts/python/audit_impact_index_bom_cleanup.py#L30)

- Registers the real-repository smoke suite in the hard-gate bundle.
  [`run_gate_bundle.py:332`](../../scripts/python/run_gate_bundle.py#L332)

**Policy inputs**

- Defines the versioned scan, exclusion, source-rule, and identity policy.
  [`impact_analysis_config.v1.json:1`](../../scripts/python/impact_analysis_config.v1.json#L1)

- Constrains target aliases to the supported kind-scoped contract.
  [`impact_target_aliases.v1.json:1`](../../scripts/python/impact_target_aliases.v1.json#L1)
