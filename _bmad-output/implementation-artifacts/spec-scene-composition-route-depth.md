---
title: 'Scene composition 深层路由场景可见性'
type: 'bugfix'
created: '2026-09-17'
status: 'done'
baseline_commit: 'b3c3c4ed3a3203980a5cbdd819eaf614ca9d5a53'
review_loop_iteration: 0
context:
  - 'docs/workflows/project-health-knowledge.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** `/knowledge/scenes` 的 Scene composition 默认只显示标为 `confirmed-reachable` 的场景。用户看到 route tree 的根和浅层场景，但深层 route-tree 节点可能遗漏，无法用 composition 视图完整审阅路由所覆盖的场景。

**Approach:** 默认从 main scene 沿 scene graph 的 route-tree 边递归计算全部可达场景；“Include resources not found by route tree”只补充该闭包外的资源，不改变默认路由范围。

## Boundaries & Constraints

**Always:** 保持浏览器只读；默认候选必须包含 route tree 全深度的场景；资源去重、类型筛选、分页、既有路径安全边界继续生效；保留当前未提交的 `docs/knowledge/catalog/godot-elements.json` 扫描产物。

**Ask First:** 若需要改变 route-tree 边的证据等级、后端 scene graph/API schema，或重新运行游戏/Godot，必须暂停并请求确认。

**Never:** 不将 route tree 外的资源默认加入；不修改游戏内容、任务数据、扫描快照或运行时验证逻辑。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| DEEP_ROUTE | main scene 经多级 route-tree 边到达场景 | 默认 Scene composition 包含每一级场景 | 循环或共享节点不重复显示 |
| OUTSIDE_ROUTE | 不在 route-tree 闭包的场景或资源 | 默认不显示；勾选复选框后显示 | 无 main scene 时保持现有空状态 |

</frozen-after-approval>

## Code Map

- `scripts/python/project_health_scenes.js` -- `compositionResources` 目前按后端 `classification` 过滤；应复用 `graphState.main_scene` 与 `graphState.edges` 计算递归 route-tree 场景集合，并保持 file manifest 的同一范围语义。
- `scripts/browser/project_health.spec.js` -- 已覆盖 Scene composition 切换与筛选；增加深层 route-tree 场景默认可见、树外场景仅在勾选后可见的浏览器断言。
- `scripts/python/_godot_scene_graph.py` -- 只读参考：`edges` 的 `source`/`target` 对应路由结构；不修改其静态解析和分类规则。
- `docs/knowledge/catalog/godot-elements.json` -- 用户允许保留的 Scan 产物；不属于本修复实现范围。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/browser/project_health.spec.js` -- 先加入深层 route-tree 场景与树外资源默认可见性断言 -- 固化用户发现的回归。
- [x] `scripts/python/project_health_scenes.js` -- 以全深度 route-tree 闭包替代 classification 过滤 -- 让默认 composition 覆盖完整路由。
- [x] `scripts/browser/project_health.spec.js` -- 运行浏览器回归 -- 验证默认与 opt-in 范围不交叉。

**Acceptance Criteria:**
- Given main scene 经至少两条路由边到达深层场景, when 打开默认 Scene composition, then 该深层场景可见。
- Given tree 外场景, when 未勾选复选框, then 它不在 Scene composition；勾选后才出现。

## Spec Change Log

## Design Notes

route-tree 可视性应由当前图中的边闭包决定，而非由后端的分类标签间接推断。这样即使分类策略将某个深层节点标为 candidate，用户仍能在默认 composition 中检查 route-tree 结构；树外资源仍由显式复选框控制。

## Verification

**Commands:**
- `node --check scripts/python/project_health_scenes.js` -- expected: syntax valid.
- `pwsh -File scripts/browser/run_project_health_tests.ps1` -- expected: Scene composition browser regression passes.
- `git diff --check` -- expected: no whitespace errors.

## Suggested Review Order

**Route tree closure**

- 从主场景计算完整闭包。
  [`project_health_scenes.js:161`](../../scripts/python/project_health_scenes.js#L161)

- 默认仅保留树内场景。
  [`project_health_scenes.js:177`](../../scripts/python/project_health_scenes.js#L177)

**Regression evidence**

- 固定深层与树外样本前提。
  [`project_health.spec.js:42`](../../scripts/browser/project_health.spec.js#L42)

- 验证默认与显式扩展范围。
  [`project_health.spec.js:68`](../../scripts/browser/project_health.spec.js#L68)
