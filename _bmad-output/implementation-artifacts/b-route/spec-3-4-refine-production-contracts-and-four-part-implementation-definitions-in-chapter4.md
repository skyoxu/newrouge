---
title: 'Story 3.4：在Chapter4细化生产契约与四部分实施定义'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'f11b8c4373f794c12815713452d94629b89da047'
story_key: '3-4-在chapter4细化生产契约与四部分实施定义'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3B 定义与 3C 绑定未细化为命令、只读状态、唯一所有者、适配与场景绑定，易生空 DTO、直写状态、假 readiness、毁人工区或失配。
**Approach:** 交付 _b_route_chapter4_binding.py 与 b-route-chapter4-binding，配原始字节同步日志、双态核验与归因，经 commit 发 stage=4 binding。

## Boundaries & Constraints

**Always:** prepare/preview 经 published_bundle 与 3.3 验 Task 全为 B 无冲突，reserve/apply 在 read_operation_context 重验；定命令(pre/post/inv)、只读状态与唯一所有者、C# 适配依赖/生命周期、控件至对象/资源、场景进出与测试义务(入 lifecycle/parts/obligations，extract_stage4_semantics 供无 logs/ 解析)；Flow 四部分全而单 Task 仅取适用(integration_only_owner 不变 API，适用无孤儿)；守恒原 3C/4 task_id 集并保共享 Task 他计划 plan_refs/binding_refs；优先引 Game.Core/Contracts/**(BCL-only，禁 Godot.*/非 BCL/空接口/空 DTO)与既有 Overlay，仅显式变更在 writer_boundary 经 base64 字节 public-sync-journal.json+.pending(禁喂 JSON create_journal，pending 时 3.3 阻 PENDING/UNPUBLISHED)、sha256 合并(保表/文/码)、EventTypes.cs 及保活投影同步引用；planned 齐备责任 Task、类型/生命周期、交接与必选 later_checks，existing 实证符号/.cs/.tscn/.tres 摘要与类型；UI 分列输入、方法、接线与 layout,art,animation 人工区，有据无 UI 不造 Ch7；错配返 3A/3B/3C/4；接通 _b_route_commit(_original_activity/execute/投影)、validate_operations 与 2.8 补偿，发 bindings/<plan_id>/<rev>.json 与 task-origins.v1.json(末推 catalog.v1.json)，写 logs/ci/b-route-chapter4-binding/<op>/events.jsonl，readiness/runtime_verified/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、实现游戏功能或改 ADR。
**Never:** 造空接口/空 DTO/假节点/假 readiness；四拆或改 task_id 集/丢他计划引用；适配裁决或 UI 直写状态；改旧 plan/Flow 或弱 Acceptance；免未声明 UI 或毁人工区。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| REUSE | 3B+3C，复用契约/Overlay(含共享 Task) | 零改源码/Overlay/三联，保 task_id 与他计划引用，发 stage=4 | 非 B、缺 3C 或改 task_id 阻断 |
| PUB_SYNC | 显式契约/Overlay 变更或中断 | 字节 journal+.pending 前滚 BCL/EventTypes 与合并，保活同步 | Godot.*、空 DTO、漂移、pending 或弱 Acceptance 阻断 |
| PLANNED | 待建标 planned | 保责任 Task、类型/生命周期与必选 later_checks，不称通过 | 缺 later_checks、existing 缺失或假节点阻断 |
| MISMATCH | 来源/定义/Task/契约错配 | 拒发定位实体，返 3A/3B/3C/4 与六字段诊断 | 禁改旧 plan 或吞冲突 |
| UI_SLICE | 有 UI 或 3B 有据无 UI | 有 UI 记输入/方法/接线/人工区；无 UI 不造 Ch7 | 未声明豁免或侵人工区阻断 |

</frozen-after-approval>

## Code Map

- `binding.schema.json:19,116`、`plan.schema.json:301,706` -- 绑定/3B
- `_b_route_task_compilation.py:157,1080`、`_b_route_task_resolver.py:359,1535` -- 投影/3.3
- `_b_route_commit.py:90,770,903`、`_b_route_commit_projection.py:59,181`、`_b_route_adoption.py:432`、`_b_route_compensation.py:357` -- 提交/补偿
- `_b_route_record_owners.py:113`、`validate_contracts.py:106,174`、`check_task_contract_refs.py:69` -- 契约
- `_overlay_generator_markdown_patch.py:200`、`validate_overlay_execution.py:141` -- 合并

## Tasks & Acceptance

**Execution:**
- [x] `docs/planning/b-route/schemas/chapter4-binding-operation.schema.json` -- 辅助 schema 与 commit/projection/adoption/task_resolver 钩子及 pending 阻断（AC-1,2,4）
- [x] `scripts/python/_b_route_chapter4_binding.py` -- 细化、双态、原始字节 journal 与归因（AC-1..5）
- [x] `scripts/python/refine_b_route_chapter4_binding.py` -- CLI、builders 与策略锚定（AC-1,4,5）
- [x] `scripts/python/tests/test_b_route_chapter4_binding.py` -- 矩阵/补偿/恢复单测、门禁与文档（AC-1..5）

**Acceptance Criteria:**
- Given 3B+3C/4 且 Task 判 B，when prepare/reserve/apply/recover，then 发 stage=4 binding/origins/catalog，保旧 plan、他计划引用与活 status，兼容补偿且无 logs/ 可解析语义。
- Given 中断在 public-sync-journal 或 commit.json，when recover，then 原身份恢复且不弱化 Acceptance。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_chapter4_binding -v`
- `py -3 -B scripts/ci/run_b_route_windows_recovery_checks.py`
- `py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding --help`

### Step 4 Review & Verification Record

- **对抗审查闭环**（见 `logs/ci/2026-11-23/story-3-4-step4-triage.md`，第 1 轮）：`intent_gap=0`、`bad_spec=0`、`defer=0`，共识别并修复 8 组补丁 `P-01`..`P-08`：
  - `P-01`：调整 `business_guard` 与 `apply_public_sync` 锁序，传播原地编辑前 `before_base64` 覆盖、钉住同步后摘要、修正 `inspect_recovery` 判定与非 dict `public-sync-journal.json` 拦截。
  - `P-02`：强制 3B `commands`/`states` 全覆盖与所有者对齐、校验 `ControlBindingEntry`、迭代 Stage-4 时去重旧 `stage4:*` 标签，并核验 3A `source-manifest.json` 摘要。
  - `P-03`：以单遍字符状态词法器替换 C# 注释正则清洗，拦截空主构造 DTO 与纯 `const` 壳，并严格校验资产后缀、分层路径与 Godot 文本注释。
  - `P-04`：校验 `add_overlay_refs` 路径、保留共享 Task 非空 `overlay` 字段，并对受影响 `task_id` 执行 `check_task_contract_refs` 规则。
  - `P-05`：在 `validate_operations` 中纳入 `public_sync_entries` 路径作用域校验。
  - `P-06`：洁净克隆 `--stage read` 校验发布历史、活跃 catalog 头部、原始摘要与 `stage=="4"` 目标，并在写阶段不吞 `append_event` 的 `OSError`。
  - `P-07`：补充契约与 Overlay 校验脚本至 `.github/workflows/b-route-runtime-deterministic.yml` 的 `pull_request.paths`。
  - `P-08`：在 `test_b_route_chapter4_binding.py` 中缓存不可变模板并补全 `P-01`..`P-07` 专项回归测试。
- **最终洁净验证结果**（无缓冲日志见 `logs/ci/2026-11-23/story-3-4-final-verify.log`，全量通过）：
  1. `scripts.python.tests.test_b_route_chapter4_binding`：`15/15 OK`（`0` skipped，`1297.98s`）
  2. `scripts.python.tests.test_b_route_task_resolver`：`11/11 OK`（`0` skipped，`68.94s`）
  3. `scripts.python.tests.test_b_route_runtime_ci`：`12/12 OK`（`0` skipped，`3.13s`）
  4. `scripts.python.tests.test_b_route_records`：`100` 项 `OK`（`14` skipped 仅因本机无符号链接权限，`39.89s`）
  5. `scripts.python.tests.test_b_route_adoption_journal`：`11/11 OK`（`0` skipped，`2.06s`）
  6. `scripts/ci/run_b_route_windows_recovery_checks.py`：`4/4 passed`（`0` skipped，源码零变更，`440.97s`；清理陈旧 `logs/ci/b-route-deterministic/windows-recovery` 后重跑通过）
  7. `scripts.python.tests.test_b_route_3b_70k_segmented.TrackBSegmented70kTests.test_01_story25_ast_and_semantic_lock_guard`：`1/1 OK`（`2.50s`）
  8. `scripts/python/dev_cli.py b-route-chapter4-binding --help`：`rc=0`（`0.69s`）

## Suggested Review Order

按入口路由、核心细化、提交门禁与测试文档顺序审阅：

### 1. 公共入口与阶段编排
- [dev_cli.py:646](../../../scripts/python/dev_cli.py#L646) — 公开 `b-route-chapter4-binding` 子命令分发入口
- [dev_cli_builders.py:933](../../../scripts/python/dev_cli_builders.py#L933) — 组装隔离 CLI 命令参数
- [refine_b_route_chapter4_binding.py:103](../../../scripts/python/refine_b_route_chapter4_binding.py#L103) — 十阶段调度、洁净克隆复验与结构化阻断

### 2. 核心细化、原始字节同步与双态核验
- [chapter4-binding-operation.schema.json:1](../../../docs/planning/b-route/schemas/chapter4-binding-operation.schema.json#L1) — 辅助操作 schema（零改动 7 个 FORMAL schema）
- [_b_route_chapter4_binding.py:391](../../../scripts/python/_b_route_chapter4_binding.py#L391) — `public-sync-journal` 原始字节前滚与清理
- [_b_route_chapter4_binding.py:659](../../../scripts/python/_b_route_chapter4_binding.py#L659) — C# 词法清洗、空 DTO 拦截与资产实证
- [_b_route_chapter4_binding.py:1229](../../../scripts/python/_b_route_chapter4_binding.py#L1229) — 无 `logs/` 可解析 Stage-4 语义提取
- [_b_route_chapter4_binding.py:2125](../../../scripts/python/_b_route_chapter4_binding.py#L2125) — 四部分定义、3B/3A 对齐、UI 策略与归因
- [_b_route_chapter4_binding.py:3050](../../../scripts/python/_b_route_chapter4_binding.py#L3050) — Stage-4 绑定构建与保活投影同步

### 3. 提交协议、锁序与 3.3 门禁集成
- [_b_route_commit.py:959](../../../scripts/python/_b_route_commit.py#L959) — `business_guard` 先行、同步执行与崩溃恢复
- [_b_route_commit_projection.py:71](../../../scripts/python/_b_route_commit_projection.py#L71) — `catalog` 头部选择与不可变字节投影
- [_b_route_task_resolver.py:394](../../../scripts/python/_b_route_task_resolver.py#L394) — 拦截待决 `public-sync-journal` 防止静默放行
- [_b_route_adoption.py:511](../../../scripts/python/_b_route_adoption.py#L511) — `validate_operations` 纳入公共同步路径作用域
- [_planning_apply_journal.py:119](../../../scripts/python/_planning_apply_journal.py#L119) — 注册 Chapter 4 绑定操作状态图
- [_b_route_records.py:1559](../../../scripts/python/_b_route_records.py#L1559) — 已发布 bundle 读取与补偿来源兼容
- [_b_route_schema_resources.py:14](../../../scripts/python/_b_route_schema_resources.py#L14) — 注册辅助 schema 并保持 7 个 FORMAL 列表不变

### 4. 测试覆盖、CI 门禁与治理文档
- [test_b_route_chapter4_binding.py:1052](../../../scripts/python/tests/test_b_route_chapter4_binding.py#L1052) — 五类矩阵、恢复补偿与 `P-01`..`P-07` 回归
- [test_b_route_runtime_ci.py:250](../../../scripts/python/tests/test_b_route_runtime_ci.py#L250) — 确定性门禁选择器与路径断言
- [run_gate_bundle.py:171](../../../scripts/python/run_gate_bundle.py#L171) — 纳入确定性运行门禁测试集
- [b-route-runtime-deterministic.yml:53](../../../.github/workflows/b-route-runtime-deterministic.yml#L53) — 补充契约/Overlay 校验脚本触发路径
- [b-route-chapter4-binding.md:1](../../../docs/workflows/b-route-chapter4-binding.md#L1) — Chapter 4 绑定细化 owner 说明
- [AGENTS.md:39](../../../AGENTS.md#L39) — 仓库路由锚点登记
- [stable-public-entrypoints.md:589](../../../docs/workflows/stable-public-entrypoints.md#L589) — 稳定公共入口说明
- [script-entrypoints-index.md:1819](../../../docs/workflows/script-entrypoints-index.md#L1819) — 脚本入口索引更新
