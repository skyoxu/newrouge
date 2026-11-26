# B 路线生产者消费者对齐与切换前只读审计

本文是 Story 4.9 的 owner 说明。共享只读审计服务 `scripts/python/_b_route_consumer_alignment.py`（`newrouge.b-route-consumer-alignment.v1`）与公共 CLI `py -3 -B scripts/python/dev_cli.py b-route-consumer-alignment`（直接入口 `scripts/python/audit_b_route_consumer_alignment.py`）用于按消费者矩阵逐项核对全部生产者、消费者、五态版本合同、Skill 与治理文档、clean-clone 布局及无私有 codec 约束，产出可重建的切换前覆盖报告。本入口严格只读，不修改 `workflow.md`、7 个 FORMAL schema、`CONTROL_PLANE_PATHS` 或分支保护，不切默认 B，不退役 A 写入兼容，不建第二状态机。

- 公共 CLI：`py -3 -B scripts/python/dev_cli.py b-route-consumer-alignment [--root <root>] [--skip-live-probes] [--report <logs/**/*.json>]`
- 直接入口：`py -3 -B scripts/python/audit_b_route_consumer_alignment.py [--root <root>] [--skip-live-probes] [--report <logs/**/*.json>]`
- 禁止标志：拒绝 `--apply`、`--switch-default-b`、`--retire-a`、`--write-tasks`、`--publish`、`--refresh-knowledge`、`--write`、`--commit`、`--mutate-tasks`、`--set-status`（退出码 `2`）。
- `--skip-live-probes` 严格 fail-closed：跳过活体五态合同与 clean-clone 探针时，`five_state_version_contract.ok=false`、`legacy_a_bounded_to_frozen_scope=false`、`clean_clone_verified=false`、`epic4_alignment_ready=false`、`ok=false`，输出六字段诊断并以退出码 `2` 退出，绝不误报通过。
- `--report` 预检与防覆盖约束：在执行探针前预检路径，仅允许仓库相对非保留 `logs/**/*.json`（拒绝所有生产者/运行保留目录及带日期生产者子树，拒绝符号链接/联接点），并采用 `open(..., "xb")` 原子新建防覆盖；若目标文件已存在一律返回 `conflict`（退出码 `2`）；写入前将 `report_path` 写入报告对象，确保磁盘 JSON 与 stdout JSON 完全一致。

## 十组消费者逐项核对（AC-1）

逐项盘点并核对 `_b_route_inventory.GROUPS` 全部 10 组及全部 40 项 `(path, symbol)` 注册消费者（`source-ledger-audit`、`capability-mvg`、`worker-checkpoint-recovery`、`business-triplet`、`chapter4-5`、`chapter6-direct-resume-route`、`chapter7`、`manifest-runner-handoff`、`knowledge-planning-page`、`cli-skill-routing-examples`），并覆盖全部 Epic 2–4 共享门禁、直接脚本、查询 CLI（`query_b_route_*.py`、`apply_chapter7_status_patch.py`、`create_chapter7_tasks_from_ui_candidates.py`）与跨多计划共享 Task 场景（共 60+ 具名项）：

- 对每个消费者通过真实 AST 与文件内容校验（非文本摘要宣称）记录实际读写路径、调用的公共 B 路线模块与符号、共享 Task 多范围支持、有效输入合同、精确测试函数名的正反测试证据及适用 Epic 5 剩余项；纯静态非执行文档（`workflow.md`）在运行时门禁项标为 `not_applicable`，并在 AC-3 单独核对不可变性。
- 对四个底层直接写入口（`compile_task_triplet.py`、`build_taskmaster_tasks.py`、`create_chapter7_tasks_from_ui_candidates.py`、`scripts/sc/llm_generate_overlays_batch.py`）实施受控 B 路线写保护：当仓库存在活跃 B 路线治理记录时阻断直接越权写入并导向 `b-route-task-compile`/`b-route-chapter4-binding`/`b-route-chapter7-slice`；纯旧 A 仓库仍保持兼容。
- 显式拒绝仅凭 `workflow.md`、dispatcher 或总摘要宣称完成覆盖（`summary_only_claim_rejected=true`）。

## 五态版本合同与格式迁移说明（AC-2）

对真实 B 路线校验器与解析器（`_b_route_codec`、`_b_route_records`、`_b_route_task_resolver`、`_b_route_chapter6_gate`、`_b_route_verification_scope`、`_b_route_knowledge_projection`）执行确定性五态活体探针与防降级验证：

1. `new_b_format`：合法 `v1` B 路线受治理记录按阶段边界通过，`runtime_verified=false`、`default_b_enabled=false`，支持共享 Task 多适用计划集合。
2. `legacy_a_format`：无 B 痕迹且 `ADR-0040` 为 `Accepted` 时归类 `explicit_not_enabled_a`；已冻结 A 仅在 `policy.v1.json` 的 `frozen_a_refs` 与 `allowed_a_operations` 边界内运行，范围外 Task、越权操作或定义漂移一律阻断。
3. `legal_absence`：3C 之前的 `3b_adopted_awaiting_3c` 允许在 3A/3B 与派生投影展示而不伪造 Task；合法非 Flow（`other_verification`）必须提供非空 `rationale` 与可解析 `other_verification_refs`，缺失任一依据即确定性拒绝。
4. `corrupted_input`：截断 JSON、非有限浮点（`NaN`）、重复键与内容摘要篡改一律确定性拒绝（`invalid_json`/`non_finite_number`/`duplicate_key`/`digest_mismatch`）。
5. `unknown_schema_version`：未知 `schema_version`（如 `newrouge.b-route-plan.v999`、`newrouge.b-route-catalog.v999`、`newrouge.b-route-verification-scope.v999`）一律以 `unknown_schema` 确定性拒绝。
6. 防降级红线：删除已治理 B 任务的 `task-origins.v1.json`、`manifest`、提交回执 `trace` 或残留 `plan_refs` 后，`_b_route_task_resolver` 与 `_b_route_chapter6_gate` 一律返回 `blocked`，绝不静默降回旧 `A`。

### 格式迁移契约（`input_contract` / `output_contract` / `identity_preservation` / `recovery_procedure`）

- **`input_contract`（输入契约）**：读取权威来源（`docs/workflows/chapter3-source-set.json`、`.taskmaster/tasks/*.json`、`docs/testing/mvg/*.json`、`docs/adr/ADR-*.md`）与版本化 B 路线最小治理记录（`docs/planning/b-route/policy.v1.json`、`catalog.v1.json`、`task-origins.v1.json`、`plans/**`、`bindings/**`、`commits/**`）。所有路径须先经 `_validate_root` / `safe_input` / 祖先 `no_reparse` 与 `os.path.lexists` 校验；输入须为严格 UTF-8 无 BOM JSON 且声明已知 `schema_version`。
- **`output_contract`（输出契约）**：只读审计仅向 stdout 输出单条严格 JSON（`newrouge.b-route-consumer-alignment.v1`），可选 `--report` 仅允许以防覆盖（`xb`）新建写入非保留 `logs/**/*.json`（拒绝所有生产者保留目录、带日期生产者子树、已存在目标与符号链接/联接点）；正式 B 路线写入仍仅由各所属阶段经 journal + `catalog.v1.json` 最后原子发布完成，不越过既有门禁。
- **`identity_preservation`（身份保留）**：保留既有 Taskmaster 数字 `id` 与业务视图字符串 `id`（`NG-*`/`GM-*`）、保留成熟 Task 活体 `status` 与 `subtasks[].status`、保留稳定 `plan_id`/`revision`/`operation_id`/`scope_id`/`flow_id` 及原始 `original_executed_at`；绝不以数字编号重排或重建新 ID 替代既有身份。
- **`recovery_procedure`（恢复步骤）**：
  - 区分 **journal 恢复**（`apply-journal.json`、`public-sync-journal`、`commit.pending.json`：按原始字节与前/后像校验重放，保留人工后编辑，绝不删除 pending 指针绕过）与 **模型恢复**（仅在原始输入与预算不变时按 `resume` 续跑且不重置预算，已耗尽或被 epoch/reopen 撤销的运行必须开启新 run）。
  - **clean-clone 恢复核验**：全新克隆仓库在 `logs/` 为空时，仅凭 Git 版本化 `docs/planning/b-route/**`（`catalog.v1.json`、`policy.v1.json`、`task-origins.v1.json`、已提交 `plans`/`bindings`/`commits` 回执与 schemas）即可经 `jsonschema` 校验、`_b_route_records` 与 `_b_route_knowledge_projection` 独立复验一致性，无需将 `logs/**` 提交入 Git。

## 文档、Skill、四组边界与 ADR 治理核对（AC-3）

- 校验 `AGENTS.md`、`docs/workflows/stable-public-entrypoints.md`、`docs/workflows/script-entrypoints-index.md`、`docs/workflows/mvg-integration-acceptance.md`、全部 `docs/workflows/b-route-*.md`、8 个受治理 Skill（`workflow-chapter3..7*`、`plan-capabilities`、`plan-mvg`、`maintain-knowledge-base`）及 `examples/**` 中的仓库文件路径链接、全部 `dev_cli.py <subcommand>` 注册子命令与真实 `argparse` 参数标志、代码块围栏闭合与逐 Skill 边界覆盖。
- 校验四组强制边界清晰分离：
  1. `3A_3B_3C_vs_4_to_7_boundary`：3A/3B/3C 规划与任务编译区别于 Chapter 4–7 契约绑定、实施与 UI 收口。
  2. `model_resume_vs_journal_recovery_boundary`：模型恢复区别于 journal 事务恢复与后编辑保留。
  3. `task_vs_flow_vs_cumulative_milestone_completion_boundary`：单 Task 局部通过、目标 Flow 完成与同快照累计 `full-MVG` 里程碑完成严格分离。
  4. `workspace_preview_attempt_vs_main_publication_boundary`：`workspace_preview`/`attempt`/`stable`/`stabilized` 永不推进 `knowledge/indexes/current.json`、`last-known-good.json` 或 `refs/heads/main`。
- 核对 `docs/adr/ADR-*.md` 与 `docs/architecture/ADR_INDEX_GODOT.md` 全部分节（含尾部 94–109 行）：严格保留冲突与未识别 `Status:`（绝不视作 `Accepted`）；确认 `ADR-0040` 为 `Accepted`（默认 B 未启用）；跟踪全部 `Proposed` ADR（`ADR-0016`、`ADR-0017`、`ADR-0021`、`ADR-0022`、`ADR-0031`、`ADR-0036`、`ADR-0037`、`ADR-0043`..`ADR-0048`、`ADR-0053`），禁止任一 `Proposed` ADR 落入 `Accepted` 分节或被治理文档宣称为 `Accepted`；确认 `docs/adr/ADR-0038-semantic-delivery-topology.md` 与 `docs/adr/ADR-0038-mvg-candidate-admission.md` 均存在且全范围文档/Skill/示例中零裸写无文件名后缀的短号引用（CJK 邻接安全扫描）。
- 核对 `.github/workflows/*.yml` 质量与保护流水线保持完整，并以只读 CRLF 归一化 `HEAD` 字节比对与 `b-route-` 注入扫描验证 `workflow.md` 未被篡改（绝不修改 `workflow.md`）。

## 最小治理布局、Clean-Clone 与零私有 Codec（AC-4）

- 核对最小治理依据入 Git、原始运行证据留 `logs/**`；执行空 `logs/` 目录的 clean-clone 实测，并在 clean-clone 根目录内校验全部 7 个 FORMAL schema、`_b_route_records` 与 `_b_route_knowledge_projection`。
- 核对 `knowledge/policies/source-exclusions.v1.json` 并只读调用 `_knowledge_catalog_builder._excluded` 实测确认 `logs/ci/x.json`、`backup/x.md`、`docs/migration/x.md` 全部被排除出全局语义检索。
- 扫描全部 `scripts/python/*b_route*.py` AST（含 `Assign`/`AnnAssign`、函数式 `Enum(...)`、7-schema `FORMAL` 集合及未批准 `json.loads`），确认 `_b_route_codec.py` 与 `_b_route_schema_resources.py` 为唯一公共所有权，零私有复制。

## 可重建切换前覆盖报告与 Epic 5 边界（AC-5）

- 产出 `pre_switch_coverage_report`：包含逐项 `passed`/`blocked`/`not_applicable` 计数、按 10 组汇总、可重建证据定位器（`module_path`、`sha256`、`test_files`、`doc_paths`），并通过 AST 扫描确认通用 B 路线门禁无奖励特化旁路（`generic_b_route_ready_without_reward_hacks=true`）。
- 恒定治理不变量：`default_b_enabled=false`、`a_write_compatibility_retired=false`、`second_state_machine_created=false`、`runtime_verified=false`，并显式列出 5 项 `epic5_remaining_gates`（奖励真实缺口与无 Task 3B 采纳、奖励增量 3C 与 C# 薄适配、Windows 真实 Godot 双路径奖励取证、新增需求受治理默认切 B、独立 A 退出门禁与撤权）。
- 退出码：Epic 4 切换前对齐全项通过时退出 `0`；任一消费者、五态探针、文档/ADR/Skill、clean-clone/codec 核对阻断、使用 `--skip-live-probes`、目标 `--report` 已存在或参数/路径非法时退出 `2`。
- 验证套件：`scripts/python/tests/test_b_route_consumer_alignment.py`，已纳入 `scripts/python/run_gate_bundle.py`、`scripts/python/tests/test_b_route_runtime_ci.py` 与 `.github/workflows/b-route-runtime-deterministic.yml`。
