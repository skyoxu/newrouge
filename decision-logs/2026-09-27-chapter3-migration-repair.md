# Chapter 3 迁移修复决策记录

## 决策

1. `_bmad-output/gdd.md` 是当前有效 GDD 来源，纳入 Chapter 3 source-set。
2. `_bmad-output/epics.md` 是旧生成规划视图，`docs/gdd/ui-gdd-flow.candidates.json` 是候选投影；两者不再作为权威来源，但保留显式 retirement 记录。
3. Task 433 与主任务 14 的行为和验收相同，采用 reuse；Task 398 与主任务 63 的 Continue 失败提示行为相同，采用 reuse。
4. Task 490 的三条语义来自历史填写示例。Translations 示例并入现有权威翻译约束，ADR-0032 示例并入现有 Gate-0 约束，文档扫描示例作为 context；INT-0357/主任务 490 退役。
5. 退役任务编号保留，状态设为 `cancelled`，不删除、不复用、不作为有效语义 sink。

## 依据

- `docs/newrouge-chapter3-bb3bb1f8-repair-plan-revised.md`
- `docs/gdd/GDD-NEWROUGE-V1.md`
- `docs/prd/PLAYTEST-ISSUE-GRADING-AND-REVISION-GUIDE-NEWROUGE-V1.md`
- 主任务 14、63 的现有验收与实现证据

## 结果

- 有效 Requirement：1253
- Source Block：3273
- Requirement→Task 边：1253，全部使用 Taskmaster 主编号
- 未知语义引用：0
- 未闭包 Requirement：0
