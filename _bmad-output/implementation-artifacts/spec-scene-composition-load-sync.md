---
title: 'Scene composition 图谱加载同步'
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

**Problem:** `/knowledge/scenes` 的图谱请求仍在进行时，用户可以切换到 Scene composition。此时表格按空图谱渲染，图谱完成加载后也不会自行刷新，导致资源类别暂时显示为空或不完整。

**Approach:** 在图谱成功加载后，若当前已处于 Scene composition，使用已有视图状态重新渲染表格；用受控延迟 API 响应的浏览器回归覆盖该交互顺序。

## Boundaries & Constraints

**Always:** 保持页面只读；不改变 route-tree 闭包、资源分类、复选框、筛选或分页语义；保留当前未提交的 Scan 目录结果和已完成的深层路由修复。

**Ask First:** 若需要改变图谱 API、加载失败状态、按钮可用性策略或服务端扫描流程，先请求确认。

**Never:** 不新增轮询、任意等待时间或第二次网络请求；不修改游戏内容、扫描快照和任务数据。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| EARLY_COMPOSITION | 图谱请求未完成时切换 Composition | 请求完成后自动显示已加载图谱的资源，无需再次点击 | 请求失败时保留既有错误状态，不渲染伪数据 |
| ROUTE_TREE_VIEW | 图谱请求未完成时保持 route tree 视图 | 请求完成后仍按现有逻辑渲染 route tree | 不额外渲染隐藏的 Composition |

</frozen-after-approval>

## Code Map

- `scripts/python/project_health_scenes.js` -- `loadGraph()` 在异步响应后更新 `graphState` 并重建 route tree；`structureButton` 的 `aria-pressed` 已表达当前是否为 Composition 视图，可作为条件重绘入口。
- `scripts/browser/project_health.spec.js` -- 已有页面级 Playwright 基础设施；增加受控延迟 `/api/knowledge/scene-graph` 响应的回归，验证早切换后自动出现资源行。
- `docs/workflows/project-health-knowledge.md` -- 只读页面和图谱 API 行为约束；不修改。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/browser/project_health.spec.js` -- 先增加早期切换的失败回归 -- 固化异步加载完成后必须补刷 Composition 的用户路径。
- [x] `scripts/python/project_health_scenes.js` -- 图谱加载成功后仅在 Composition 已打开时重渲染表格 -- 让视图与最新 `graphState` 同步且不改变 route tree 行为。
- [x] `scripts/browser/project_health.spec.js` -- 运行完整 Project Health 浏览器回归 -- 验证受控竞态和既有交互共同通过。

**Acceptance Criteria:**
- Given Scene composition 在图谱请求返回前已打开, when 图谱成功返回, then 至少一个场景资源行自动出现且用户无需再次切换视图。
- Given 图谱请求返回时 Scene route tree 仍为当前视图, when 加载完成, then 仅更新既有 route tree，不显示 Composition 工具栏。

## Spec Change Log

## Design Notes

不禁用按钮或加入延迟，因为页面已有明确的当前视图状态。加载回调只在 Composition 已处于活动状态时调用既有渲染函数，保持单一数据源和原有交互。

## Verification

**Commands:**
- `powershell -ExecutionPolicy Bypass -File scripts/browser/run_project_health_tests.ps1 -ProjectHealthUrl http://127.0.0.1:8765 -Reporter line` -- expected: all Project Health browser tests pass.
- `node --check scripts/python/project_health_scenes.js` -- expected: syntax valid.
- `git diff --check` -- expected: no whitespace errors.

## Suggested Review Order

**Load Synchronization**

- 完成请求后同步活动视图。
  [`project_health_scenes.js:120`](../../scripts/python/project_health_scenes.js#L120)

- 单一入口控制工具栏显示。
  [`project_health_scenes.js:225`](../../scripts/python/project_health_scenes.js#L225)

**Regression Evidence**

- 延迟响应后自动补刷表格。
  [`project_health.spec.js:40`](../../scripts/browser/project_health.spec.js#L40)

- 非 Composition 视图保持隐藏。
  [`project_health.spec.js:59`](../../scripts/browser/project_health.spec.js#L59)
