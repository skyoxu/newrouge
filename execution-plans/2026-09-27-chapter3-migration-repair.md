# Chapter 3 旧数据迁移修复执行计划

- 输入方案：`docs/newrouge-chapter3-bb3bb1f8-repair-plan-revised.md`
- 修复分支：`chapter3-init-20260926`
- 起点提交：`bb3bb1f8e56b5e46351d9b0d144f7e101533546c`
- 范围：来源集合、语义投影、任务承接、规划拓扑与闭包证据；不发布 Main。

## 已执行

1. 将 `_bmad-output/gdd.md` 纳入有效来源集合，并将 `_bmad-output/epics.md`、`docs/gdd/ui-gdd-flow.candidates.json` 明确记录为历史/候选来源，不再作为权威输入。
2. 复用同一来源修订的 3273 个已审阅 Source Block，修订历史 playtest 填写示例的语义投影。
3. 将主任务 433 复用到主任务 14，将主任务 398 复用到主任务 63；将 490 及其三条历史示例语义退役，保留编号且不复用。
4. 修正退役任务的直接生成依赖：399→63、434→14、491→489。
5. 生成 1253 条有效 Requirement 的规划拓扑，并将 1253 条 Requirement→Task 边解析为 Taskmaster 主编号。

## 证据

- `logs/ci/chapter3-migration-repair/20260927-repair/`
- `logs/ci/project-health-knowledge/topology/workspace-latest-successful.json`
- `docs/planning/semantic-topology/topology-manifest.v1.json`

## 验收状态

- projection conservation：passed
- closure conservation：passed，blocking=0
- semantic sink coverage：ok，missing=0，invalid=0，stale=0
- persisted semantic coverage：ok
- triplet baseline attestation：passed
- Workspace stable refresh：passed
- Main/KCP publication：未执行

## 保留边界

- Chapter 4/5 的 Overlay、契约、Acceptance 深化仍按后续流程处理。
- 历史任务仍可能没有来源映射；本轮只要求新增/修复承接可追溯。
- 运行时 Godot 代码未修改。
