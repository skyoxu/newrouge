# B 路线受治理反向关系完整传递影响闭包

本文档定义 Story 4.1 的 owner 边界：从受治理反向关系计算变更根的完整传递影响集合，并对既有影响证明做分区选择性复验。本入口只做影响记账，不授予实施权、readiness 或运行验收。

## Owner 与入口

- 领域 owner：`scripts/python/_b_route_impact_closure.py`（`build_governed_reverse_graph`、`compute_impact_closure`、`revalidate_impact_proof`）。
- 直接 CLI owner：`scripts/python/compute_b_route_impact_closure.py`。
- 公共入口：`py -3 -B scripts/python/dev_cli.py b-route-impact-closure (--change-root <root> ... | --revalidate-proof <path>) [--root <root>] [--plan-id <id> ...] [--manifest <path> ...] [--operation <op>] [--report <logs/**/*.json>] [--events-log <logs/**/*.jsonl>]`。
- `--change-root` 接受 `contract:<path>`、`rule:<plan>:<id>`、`state:<id>`、`command:<id>`、`flow:<id>`、`task:<id>`、`test:<id>`、`requirement:<id>`、`impl:<id>` 或仓库相对路径，可重复；与 `--revalidate-proof` 互斥，复验时 `--plan-id` 取自证明本身。
- 退出码：`0` 成功，`1` 阻断，`2` 参数非法（结构化 `invalid_arguments:<reason_code>`）。

## 受治理反向边来源

反向图只取已提交、可追溯的权威记录，不从 Knowledge 摘要或缓存推导：

1. 四部分定义（rule/state/command/part）与已提交 `plan`、Stage-3C/4/5 `binding`、`catalog.v1.json`、`task-origins.v1.json`。
2. 契约（`Game.Core/Contracts/**`）、场景资源、适配器与测试基础设施路径。
3. 测试义务与验证依据（含 Stage-5 义务与合法非 Flow 依据）。
4. Taskmaster 三联依赖（`tasks.json` 与 `tasks_back.json`、`tasks_gameplay.json` 视图映射）。
5. 累计 MVG manifest（`docs/testing/mvg/**` 及 `--manifest` 追加项），同时纳入 active 与 `planned` Flow。
6. 跨 Capability 与共享 Task 传播：共享 Task 跨多个计划时影响联合扩散至全部适用计划。

## 环安全去重与唯一语义 owner

- 每个节点以 `(entity_kind, entity_id)` 唯一标识，同一语义实体只归属一个 owner（`catalog.v1.json` 的 `definition_owners` 为 flow/command/state/rule 的首要 owner 权威，计划与之冲突记 `definition_owner_conflict`），重复路径合并而非重复计数。
- 反向图为有向因果图：Flow 触达的 Requirement 与负责 Task 只做记账（`accounting_only`），不经共享 Requirement、Capability 或测试回流到无关 Flow。
- 遍历对环安全：`cycle_witnesses` 只基于 Flow 节点级 `graph.edges`/`graph.loops`（含自环）、跨 Flow handoff、Task 依赖/handoff 与 `prior_requirement_ids` 的真实有向拓扑记录，无环 DAG 为空，不导致死循环或闭包截断。

## 保守扩大

- 反向边缺失、映射未知或来源无法证明时向保守方向扩大影响集合并给出诊断，绝不收缩为空集；manifest/plan/binding/catalog/三联不可读、缺 Stage-5 绑定、存在未完成 journal 或引用文件缺失时扩大到全部累计 manifest 与已提交计划；仍无任何可证实体时以 `unresolved_reference` 阻断。
- 未来 `planned` Flow 仅标记为计划内影响（`declared_planned`/`out_of_scope_future`），`immediate_regression_required=false`；有已实现测试的 active Flow 单调保持 `current`。

## 类型化输入身份与分区选择性复验

- 每个输入记录类型化身份（`category`、`locator`、`partition_keys`、`raw_digest`、`normalized_digest` 等），分区键前缀为 `plan:`、`manifest:`、`task:`、`path:` 与 `governance`；分区引用的契约、场景、适配、测试、测试设施、其他验证与来源 manifest/ledger 文件均纳入身份。
- `impact_proof_id` 封存除状态/度量外的完整证明内容，篡改任一字段即 `digest_mismatch`。
- Task 投影剥离 `status`、`updatedAt` 等易变字段，合法状态推进不使影响证明失效。
- `--revalidate-proof` 按分区逐一复验：仅变动分区失效，无关分区复用；新计划触及证明中的任一实体（共享契约、Task、规则等）即并入重算，完全不相交的新计划保持 `valid_reused`。
- 损坏证明、缺字段或仅单一哈希的身份记录一律拒绝，不降级为全量信任。

## 只读与非授权不变量

- 恒定 `impact_accounting_only=true`、`implementation_completed=false`、`runtime_verified=false`、`default_b_enabled=false`。
- 零修改 `.taskmaster/tasks/*.json`、`catalog`、发布指针（`current`/`last-known-good`/`latest.json`/`main`），不刷新 Knowledge、不调用模型。
- 默认严格零写盘；仅在显式提供时以独占创建方式写入新的 `--report`（`logs/**/*.json`）与 `--events-log`（`logs/**/*.jsonl`），拒绝已存在路径或 `logs/**` 之外路径。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_impact_closure -v`。
- CI：`run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml` 纳入上述单测，`test_b_route_runtime_ci.py` 守护接线。
