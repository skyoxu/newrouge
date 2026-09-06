---
title: 'KCP Impact Analysis main 集成与真实验收'
type: 'chore'
created: '2026-09-06'
status: 'in-progress'
review_loop_iteration: 0
baseline_commit: '9ac14ac27e39630ad393c74a5190c8c755f48fa6'
context:
  - 'execution-plans/2026-09-05-kcp-impact-analysis-completion.md'
  - 'decision-logs/2026-09-05-kcp-impact-analysis-open-findings.md'
  - '_bmad-output/implementation-artifacts/spec-kcp-cap-final-acceptance.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 Impact Analysis 的 index、analyzer、handoff 入口存在于功能分支，但 `main` 尚未包含这些文件，因此现有分支测试不能证明生产链路完成。

**Approach:** 先以当前功能分支作为待合入变更完成审计收口；合入 `main` 后，基于新的 main commit 重新发布知识目录并执行真实的 index → analyzer → handoff → consumer 验收。

## Boundaries & Constraints

**Always:** 只提交源码、测试和审计文档；generated state 在 main 上重新生成；保留 fail-closed、revision/hash lineage、正负向测试和真实证据。

**Ask First:** 是否允许创建提交、推送分支或合并 PR；是否接受任何新增实现范围。

**Never:** 不修改 `docs/121.txt`；不把 synthetic fixture、功能分支 PASS 或 CAP 矩阵 PASS 当作 main 生产验收；不放宽 Locator、freeze 或负向约束。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|-----------------------------|----------------|
| FEATURE_BRANCH_READY | 非 generated 修改已审计，Impact 入口存在 | 分支可供 PR 审查 | 工作区含未审计改动时停止 |
| MAIN_MISSING_IMPLEMENTATION | main 缺少 Impact 入口 | ACCEPT-01 保持 OPEN | 记录阻塞，不伪造证据 |
| MAIN_REAL_CHAIN | main 已包含入口且 publication 与 commit 一致 | index、analyzer、handoff、consumer 全链通过 | 任一 revision/hash/binding 不一致时 fail-closed |

</frozen-after-approval>

## Code Map

- `scripts/python/build_impact_index.py` -- Impact Index 构建入口，仅存在于功能分支，需由 main 集成后验证。
- `scripts/python/analyze_impact.py` -- 影响分析 CLI，消费 index 与目标，输出 report/manifest。
- `scripts/python/impact_analysis_handoff.py` -- frozen context、report、revision 与 binding 校验入口。
- `scripts/python/freeze_knowledge_context.py` -- publication lineage 与 task-id fail-closed 规则。
- `scripts/python/validate_knowledge_control_plane.py` -- main 上 generated state 与知识管线终端门禁。
- `execution-plans/2026-09-05-kcp-impact-analysis-completion.md` -- ACCEPT-01 阻塞与恢复入口。
- `decision-logs/2026-09-05-kcp-impact-analysis-open-findings.md` -- 未关闭项及证据边界。

## Tasks & Acceptance

**Execution:**
- [ ] 审核并提交当前分支的非 generated 修改；保留 generated state 不入库。
- [ ] 创建或更新 PR，将 Impact Analysis 三个入口及其测试合入 `main`。
- [ ] 在最新 `main` 重新执行 publication、freeze、index、analyzer、handoff 与 consumer 验收，并记录 logs 证据。

**Acceptance Criteria:**
- Given 最新 `main` 包含三个 Impact Analysis 入口，when 运行真实链路，then 每一步均以当前 main commit、publication generation 和 hash lineage 通过。
- Given 任一入口缺失或绑定不一致，when 执行验收，then 流程 fail-closed 且 ACCEPT-01 保持 OPEN。

## Verification

**Commands:**
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated` -- expected: status `passed`。
- `py -3 -m unittest scripts.python.tests.test_analyze_impact_cli -q` -- expected: all tests pass。
- `git diff --check` -- expected: no output and exit code 0。
