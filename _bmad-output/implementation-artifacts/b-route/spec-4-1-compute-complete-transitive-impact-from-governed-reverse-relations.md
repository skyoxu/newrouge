---
title: 'Story 4.1：从受治理反向关系计算完整传递影响'
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_commit: 'f684224ec07295a2c25055af8109526c766b3180'
story_key: '4-1-从受治理反向关系计算完整传递影响'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 既有符号影响分析与页面可见图未能串联 B 路线已提交四部分定义、绑定、契约、测试责任与累计 manifest（含 planned Flow 及跨 Capability/共享 Task），变更或边缺失时易漏后续责任或误作全仓失效。
**Approach:** 交付 _b_route_impact_closure.py 与 b-route-impact-closure 只读入口，在既有 plan/binding/origins/三联与累计 manifest 上构建反向边、环安全闭包、保守扩大与分区复验，不建数据库、不跑测、不改状态或提前建未来 Task。

## Boundaries & Constraints

**Always:** 按已提交四部分定义、plan、绑定、契约、测试责任、三联依赖与累计 manifest 构建反向边并查直接与传递影响，含当前 Task、已有与 planned Flow 及其他验证，给根、路径与来源身份，保跨 Capability 与共享 Task 完整；稳定身份去重并在环中终止，保路径与唯一语义 owner，不判遍历环非法，不按路线重计 Requirement 覆盖或复制共享规则；缺边、未知映射或不可验引用保守扩大到可证累计 manifest/来源范围并留未知与原因，分 planned 与当前责任，无边界不置空且不迫全部未来 planned 立即回归；相关 source/plan/binding/契约/规则/manifest/定义投影变化重算适用分区，无关 HEAD/catalog/status 不废全仓闭包，未知相关性保守扩大，拒损坏/未知 proof，不以文件名或单 hash 代完整身份；只读接口定位义务/来源/修订/未知项，仅证影响核算，不改状态、发布指针或退旧 Flow/test，事件与可选排他报告落 logs/**。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、建规划库或启付费 API。
**Never:** 按标签/可见图/已实现过滤；环死循环或重计覆盖；置空或迫未来 planned 立即回归；用损坏/单 hash proof；改状态或指针。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| REVERSE_CLOSURE | 共享规则/状态/命令/契约/适配/场景/测试设施变更 | 报直接与传递 Task、已有与 planned Flow 及其他验证，含根/路径/身份，跨 Capability/共享 Task 完整 | 按标签/可见图/已实现过滤阻断 |
| CYCLE_DEDUP | 共享对象、合法环、多 Flow 引用与唯一 owner | 稳定去重并终止环，保路径与唯一 owner，不重计覆盖/共享规则 | 死循环、判环非法或重计阻断 |
| CONSERVATIVE | 缺边、未知映射或不可验引用 | 扩大到可证累计 manifest/来源范围，留未知与原因，分 planned 与当前 | 置空或迫未来 planned 立即回归阻断 |
| REVALIDATE | 相关变化 vs 无关 HEAD/catalog/status vs 损坏 proof | 相关变化重算分区；无关保复用；未知保守扩大 | 用损坏 proof 或单文件名/单 hash 阻断 |
| READONLY_PROOF | 只读查询或交接影响报告 | 定位义务/来源/修订/未知，仅证影响核算，可选排他写 logs/** | 冒充实现/运行、改状态/指针或退旧测阻断 |

</frozen-after-approval>


## Code Map

- _b_route_flow_graph.py:27, _b_route_input_set.py:74, dev_cli_builders.py:1217 -- 环分量、Stage-5 元数据、只读 CLI

## Tasks & Acceptance

- [x] _b_route_impact_closure.py、compute_b_route_impact_closure.py、dev_cli*.py、owner 文档与 CI 接线
- [x] test_b_route_impact_closure.py -- AC1-AC5

## Spec Change Log

- Step 4 patch 6/defer 0/dismiss 0：P-01 反向边补全；P-02 记账边与拓扑环；P-03 单调 current 与保守扩大；P-04 全量封存与并入复验；P-05 守卫与 CLI；P-06 单测。证据 `logs/ci/2026-11-25/story-4-1-final-verify.log`。

## Suggested Review Order

1. [_b_route_impact_closure.py:127](../../../scripts/python/_b_route_impact_closure.py) -- 记账边
2. [_b_route_impact_closure.py:529](../../../scripts/python/_b_route_impact_closure.py) -- 计划与绑定反向边
3. [_b_route_impact_closure.py:1327](../../../scripts/python/_b_route_impact_closure.py) -- owner 与可用性
4. [_b_route_impact_closure.py:1539](../../../scripts/python/_b_route_impact_closure.py) -- 闭包与保守扩大
5. [_b_route_impact_closure.py:2021](../../../scripts/python/_b_route_impact_closure.py) -- 封存与复验
6. [test_b_route_impact_closure.py:283](../../../scripts/python/tests/test_b_route_impact_closure.py) -- 单测

## Verification

- 见 `logs/ci/2026-11-25/story-4-1-final-verify.log`（Python 3.12，`PYTHONPATH=scripts/python;scripts/python/tests`）