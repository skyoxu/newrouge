---
title: 'MVG 独立候选与完成项恢复'
type: 'feature'
created: '2026-10-16'
status: 'done'
baseline_commit: 'da5bce2e9f73f968bd867c4bbb4cc7dddcfa2d92'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 长时 MVG 工作不能按已完成 Capability 跨运行复用；候选生命周期未独立为子进程，页面不能及时展示或清理累计成果。

**Approach:** 主流程准备完整相关输入，独立 worker 生成并准入；主流程复验、评选、原子提交。以单 Capability 内容哈希恢复完成项，逐项展示。

## Boundaries & Constraints

**Always:** 遵守 SPEC CAP-1～9、架构 AD-1～14；保持原始 proof 和预算留痕；来源完整；原工作区已有成本优化保留。

**Ask First:** 扩大游戏范围、改变预算政策、启动真实付费模型整轮。

**Never:** 使用相似度；恢复未完成模型中间态；以 Git hash 代替内容键；改任务三联、GDD 或游戏；把规划显示为运行通过。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 结果 |
| --- | --- | --- |
| 内容相同 | Git/catalog 改变，单项未变 | 机器验证后零模型复用 |
| 内容变化 | 单项值/类型/数组改变 | 全新三个候选与评选 |
| 未完成 | 仅候选或评选中间文件 | 不恢复，预算记录保留 |
| 不兼容 | 旧证明损坏、delta 冲突或被撤销 | 不推进，记录原因并新生成 |
| 清理 | 无活动写操作 | 新代际、零完成项，旧指针不复活 |

</frozen-after-approval>

## Code Map

- `_mvg_capability_selection.py`：`candidate_artifacts` 父复验；`verified_prefix` 验证累计链；`reserve` 唯一预算账；selector 当前复制全部输入。
- `_mvg_capability_checkpoint.py`：`commit_checkpoint` 唯一提交点；`recover_commit_outcome` 处理提交未知。
- `_mvg_capability_generation.py`：`complete_scope_context` 和 `generate_append`，保留无损传输、独立准入与有界修复。
- `_project_health_planning.py`：`create_job`、`run_job`、`generated_view`；`_project_health_http.py` 分发请求，`_project_health_planning_http.py` 持有操作锁。
- 文件均在 `scripts/python/`；页面为 `project_health_scenes.html`、`project_health_mvg_versions.js`、`project_health_planning.js`。不得让原全页遮罩遮住只读进度。

## Tasks & Acceptance

**Execution:**

- [x] `docs/adr/ADR-0039-mvg-completed-capability-recovery.md`、ADR 索引：记录用户批准的恢复政策及 ADR-0038 的适用边界。
- [x] `scripts/python/_mvg_capability_worker.py`、selection、`plan_mvg.py`：候选子进程与父预算 mailbox；干净输出复验；rank 只消费相关完整比较输入。
- [x] `scripts/python/_mvg_capability_recovery.py`、checkpoint、selection、`_mvg_global_audit.py`：规范化单项 hash、完成项 registry/adoption proof、完整链验证、撤销与清理代际；旧 proof 不变，新执行不恢复半成品。
- [x] planning、HTTP、三个页面文件：提交后进度投影与轮询；认证清理、锁互斥、防旧指针回落和晚到发布。
- [x] `scripts/python/tests/test_mvg_capability_recovery.py`、`test_mvg_capability_worker.py` 及现有 append/global-audit/planning HTTP/JS 测试：独立 fixture 和实际子进程 fake runner 覆盖 SPEC AC-01～13。补齐父边界产物篡改、终止清理分支及锁释放、实际来源 delta 冲突与 adoption 后继撤销、内容变化重生成的四项窄测；结果见 Verification evidence。
- [x] `workflow.md`、plan-mvg Skill、MVG owning doc、run-protocol、project-health-knowledge：同步实际部署规则；证据写 `logs/ci/2026-10-16/mvg-recovery-redesign/`。

**Acceptance Criteria:**

- Given A 已提交、B 中断，when 无关提交后新 run，then 复用 A、全新执行 B，期间页面可见累计结果。
- Given worker 返回篡改 proof，when 父复验，then 不进入排名且已选状态不变。
- Given 当前存在完成项，when 清理后重启刷新，then 零项可恢复且正式回归基线和审计保留。

## Spec Change Log

### Review Findings

BMAD code review of `253cdacf`, 2026-10-16. Four review layers completed. No implementation patches were applied during this review. Detailed evidence: `logs/ci/2026-10-16/mvg-recovery-redesign/bmad-review-253cdacf.md`.

- [x] [Review][Patch][P1] 恢复依赖已绑定相关累计 flow/handoff、测试、入口及 Requirement 映射的已选与重放边界；行为变化阻断旧证明，无关 flow 变化不改变依赖键。独立单测及真实 proof 重放通过。`scripts/python/_mvg_capability_recovery.py:97`
- [x] [Review][Patch][P1] 同一 run 的恢复按当前 execution 读取工作区并过滤局部调用；历史执行费用继续累计。真实中断后 execution 2 提交成功，16 次费用全部保留。`scripts/python/_mvg_capability_selection.py:272`
- [x] [Review][Patch][P2] Windows Job Object 管理 worker/模型子树，并在绑定成功前保持启动门关闭。实际强杀父进程后两个后代均退出；绑定失败不放行。`scripts/python/_mvg_worker_lifetime.py`
- [x] [Review][Patch][P2] 重开进度保留历史归档绑定的全部调用，只排除后续活跃派发；实际重开 B 后仍显示 A，读取不修改账本。`scripts/python/_mvg_capability_recovery.py`
- [x] [Review][Patch][P2] 相同进度不重建 DOM；新 checkpoint 保留详情展开，清理代际变化不继承旧状态。前端回归通过。`scripts/python/project_health_mvg_versions.js`
- [x] [Review][Patch][P2] 已加入常规 discovery 的自包含集成回归：实际 adopted chain reopen 撤销原来源及后继，新 run 无法再采用；无需设备旧日志。`scripts/python/tests/test_mvg_recovery_review_integration.py`

### Review Fix Verification

本次 6 项全部修复，24 项 Python 定向测试、Node 前端回归、编译及 diff 检查通过。Windows 父进程强杀测试使用真实进程树，不再只有 Popen 模拟；候选集成仍使用离线 fake runner，未调用真实付费模型或 Godot。来源完整性与预算上限未放宽。旧依赖签名不能证明新边界完整性时，按不兼容处理并要求新生成，不改写旧证明。验证记录：`logs/ci/2026-10-16/mvg-recovery-redesign/bmad-review-253cdacf-fix-verification.md`。未绑定 sprint story key，不同步 sprint 状态。

## Design Notes

保留全部原始冻结输入供机器校验；模型只读完整相关来源。恢复旧 proof 时用旧冻结输入验证，再单独验证当前兼容性。adoption 是新证明类型，最终 audit/review/validate/apply 必须共同识别，不能伪造普通当前 run 的准入证明。

## Verification

Verification evidence: `logs/ci/2026-10-16/mvg-recovery-redesign/verification.md`. Two actual OS-worker integration scenarios passed once as a complete suite. The retained-artifact rerun passed interruption/progress/clear; its adoption case reached apply, exposed an added recursive-lock wrapper defect, and the same persisted journal then successfully recovered after that wrapper was removed. Four narrow follow-up checks passed: parent-bound child artifact tampering, Windows tree-termination finally branch and lock release using a controlled Popen double, incompatible delta rejection with original proofs and temporary registry, and real retained changed-item/fresh-worker evidence. No paid model or Godot run was used. Broader global-audit/completion suites were stopped without claiming a pass.

- 定向 unittest：规范化、跨 Git 复用、中断、提交故障、篡改、撤销、清理重启；不得调用真实模型。
- 实际子进程 fake runner 验证进程隔离、父预算计数、杀子进程后的日志与锁释放。
- 本地临时 HTTP 服务和 Node 页面测试验证逐项可见、认证清理、互斥及旧结果不复活。
- 重跑受影响的 append、global audit、planning completion/boundary 回归；`git diff --check`；不重跑 Godot 全量验收。

## Review Closure

三路独立审查确认的四个实现问题及旧指针测试缺口均已修补。历史真实性与当前恢复资格分开校验；reopen 同计划持久事务支持故障恢复；Apply 与审计写入口和清理互斥；未知未来成本不充当确定下界。原评审者窄复审通过，定向红绿与具体测试限制见 `logs/ci/2026-10-16/mvg-recovery-redesign/verification.md`。未运行付费模型整轮、完整历史 suite 或 Godot 验收。

## Suggested Review Order

**协调与恢复**

- 从唯一协调器理解逐项生成、采用与原子提交。
  [_mvg_capability_selection.py:406](../../scripts/python/_mvg_capability_selection.py#L406)

- 单项内容哈希和已完成证明决定恢复资格。
  [_mvg_capability_recovery.py:16](../../scripts/python/_mvg_capability_recovery.py#L16)

- 子进程仅返回结果，父进程复验并掌握预算。
  [_mvg_capability_worker.py:129](../../scripts/python/_mvg_capability_worker.py#L129)

- 持久事务使撤销与提交故障可按原计划恢复。
  [_mvg_global_audit.py:502](../../scripts/python/_mvg_global_audit.py#L502)

- 外层活动锁覆盖 Apply 的全部正式写入。
  [plan_mvg.py:6931](../../scripts/python/plan_mvg.py#L6931)

**展示与验证**

- 只读累计投影不依赖未完成模型中间态。
  [_mvg_capability_recovery.py:294](../../scripts/python/_mvg_capability_recovery.py#L294)

- 已提交进度保持可见，清理入口撤销本地恢复资格。
  [project_health_scenes.html:55](../../scripts/python/project_health_scenes.html#L55)

- 实际子进程假模型验证跨运行恢复与中断边界。
  [test_mvg_capability_worker.py:81](../../scripts/python/tests/test_mvg_capability_worker.py#L81)

- 窄测验证成本下界和正式写入的活动锁。
  [test_mvg_recovery_fixthrough.py:16](../../scripts/python/tests/test_mvg_recovery_fixthrough.py#L16)
