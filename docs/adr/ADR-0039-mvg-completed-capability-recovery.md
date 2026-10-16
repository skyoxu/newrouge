# ADR-0039: MVG 完成项恢复与独立候选生命周期

- Status: Accepted
- Date: 2026-10-16
- Context: 用户批准以单项 Capability 内容复用已原子提交的规划成果，并在长时生成期间展示累计进度。
- Decision:
  - 规范化完整单项 JSON 对象作为唯一恢复键；对象键序与排版无关，数组顺序、值和类型有关。Git revision、catalog 元数据仅为来源信息，禁止相似度恢复。
  - 三个候选生命周期分别使用独立 OS 子进程与工作区。协调器拥有预算预留、父机器复验、评选与唯一原子提交点；worker 无权推进 selected 状态。
  - 只复用已由 run.json 原子提交的完成项；保留原 proof，通过原冻结输入验证历史证明，再验证当前相关依赖与 delta 重放。adoption 使用独立证明类型，不伪造当前 run 的语义准入。
  - 新执行不恢复候选、修复、检查、评选中间态；已付调用保留审计，稳定候选槽位的 run 内预算不因子进程或 lineage 改变而重置。
  - 每项提交后投影累计结果；部分规划与 runtime verification 分离，最终 planning complete 仍需全局机器审计。
  - 认证清理复用现有操作锁，持久推进本地 epoch；所有恢复、显示及发布路径检查 epoch。显式 reopen 同时撤销受影响项及后继的恢复资格，历史审计及正式基线保留。
  - ADR-0038-mvg-candidate-admission 的机器门禁、独立语义准入、有界修复仍有效；新的 Capability-local 路径以只读 accepted seed 代替 incumbent 参选，64 次上限属于稳定槽位，run 默认上限仍为 192，不增加预算。
- Consequences: 相同内容可跨无关提交零模型复用；不兼容或损坏项记录原因并重新生成。清理不会递归删除审计，也不会更改游戏、任务或正式运行证据。
- References: `_bmad-output/implementation-artifacts/spec-mvg-completed-capability-recovery.md`、`_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/SPEC.md`、`docs/workflows/mvg-integration-acceptance.md`。
