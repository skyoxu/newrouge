---
title: 'Godot 场景图证据分级与纵向展示'
type: 'feature'
created: '2026-09-14'
status: 'done'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前场景图横向展开、节点显示完整路径，且只要脚本出现路径就形成关联，容易将未实际触发的场景引用误作跳转。

**Approach:** 改为自上而下的树形展示，节点只显示文件名并在悬停时给出完整路径；依据可复核的调用或事件链路区分有效关联（绿色）与可能关联（黄色）。

## Boundaries & Constraints

**Always:** 保持浏览期纯静态、确定性分析；有效关联必须具有场景实例化/切换调用，或可静态追踪的输入或事件到处理分支再到切换的证据；仅预加载、常量或孤立字符串引用必须标为可能。

**Ask First:** 若需要执行游戏、接入运行时遥测，或改变既有 Knowledge API 的安全边界。

**Never:** 不把无触发证据的脚本场景路径伪装为有效跳转；不修改游戏内容或用户已有的 `.import` 改动。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| EFFECTIVE_ROUTE | 场景脚本内存在明确切换调用，或事件发布到处理分支并解析到切换 | 边携带 `effective` 证据等级，页面用绿色显示 | N/A |
| POSSIBLE_REFERENCE | 脚本仅声明或预加载 `.tscn`，没有可静态确认的触发链 | 边携带 `possible` 证据等级，页面用黄色显示 | N/A |
| CYCLE | 已在递归栈中的场景再次出现 | 保持 cycle 标记并终止该分支 | 不无限递归 |

</frozen-after-approval>

## Code Map

- `scripts/python/_godot_scene_graph.py` -- 静态解析器；当前为 `script-reference` 和 `event-route` 生成场景边，需要为边附加触发证据等级，避免孤立常量被视为有效跳转。
- `scripts/python/project_health_scenes.js` -- `/knowledge/scenes` 的递归树和弹窗；当前节点使用完整路径，并把全部边无差别作为子节点。
- `scripts/python/project_health_knowledge.css` -- 当前 `.scene-map`、`.scene-map-branch` 和 `.scene-card` 的场景图视觉样式。
- `scripts/sc/tests/test_godot_scene_graph.py` -- 解析器场景边、事件路由、循环测试。
- `scripts/browser/project_health.spec.js` -- 浏览器场景图行为与页面布局测试入口。

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/sc/tests/test_godot_scene_graph.py` -- 先添加有效与可能脚本引用的失败测试。
- [ ] `scripts/python/_godot_scene_graph.py` -- 产出可审计的关联证据等级。
- [ ] `scripts/browser/project_health.spec.js` -- 添加纵向树、短文件名、路径悬停和颜色状态的浏览器断言。
- [ ] `scripts/python/project_health_scenes.js`、`scripts/python/project_health_knowledge.css` -- 渲染纵向树、短名称、完整路径提示和绿/黄证据样式。

**Acceptance Criteria:**
- Given 一个仅含场景常量的脚本，when 构建场景图，then 该关联为可能而非有效。
- Given 一个可识别的事件或调用链，when 构建场景图，then 该关联为有效且保留其可复核证据。
- Given 用户打开场景图页，when 查看节点，then 树由上向下延伸、节点只显示文件名，完整路径可通过悬停获得。

## Spec Change Log

## Design Notes

边不因颜色而消失：绿色回答“静态可证明会触发”，黄色回答“存在引用但缺少触发证据”。这样既不夸大静态分析能力，也避免遗漏开发者需要审阅的预加载或常量依赖。

## Verification

**Commands:**
- `py -3 -m unittest scripts.sc.tests.test_godot_scene_graph -q` -- 解析器测试全绿。
- `node --check scripts/python/project_health_scenes.js` -- 前端脚本语法有效。
- `git diff --check` -- 无空白或补丁格式问题。
