=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_BEGIN ===
{
  "schema": "taskmaster-prd-part/v1",
  "generated_at_utc": "2026-01-29T12:44:47+00:00",
  "rel_path": ".taskmaster/docs/prd_parts/00-taskmaster-directives.md",
  "title": "Taskmaster directives",
  "sha256": "8553e1aa6bec7eba892663d2c2504f2a9a2b4abca89ec2b980c939866799f738",
  "bytes": 1187
}
=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_END ===

# Taskmaster 指令（M1 任务生成约束）

你正在基于 NewRouge 的 SSoT 文档生成 M1（仅 Warrior）任务。

## 生成范围（硬约束）
- 仅生成 M1（Warrior 可玩纵切）相关任务。
- 必须包含：难度选择 UI（全局设置、局内不可变），Act 结构模块化（可扩展，不硬编码成 3 Act 死规则）。
- 不生成：三角色完整实现、云同步、多槽存档、出网/后端等 v1 非目标。

## 任务结构（强制）
- 任务按泳道拆分：Game.Core / Game.Godot / Tests / Docs&QA。
- 每个任务必须引用至少 1 条 Accepted ADR（若无则视为拆分失败）。
- 每个任务必须回链到：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md` 的对应条目。

## 复杂度要求（强制）
- 在任务描述中给出 `Complexity:`（1-10）。
- 平均复杂度 <= 6；单任务最大复杂度 <= 8。
- 如出现 >8，必须继续拆分该任务，直到满足约束。

## 特别提醒（Gate-0）
- ADR-0032（Save/Resume determinism）已是 Accepted，作为 M1 Gate-0：与存档/确定性相关的任务必须优先拆分并显式标注验收与取证（logs/**）。
