# Story 2.4：可审阅的 Flow 与非 Flow 候选

本 Story 实现读取完整 3B 候选的分支。`_b_route_candidate.py` 是两个 planner 的单一结构 owner；它默认调用 `load_prepared` 当前重验，在旧 run、Task、readiness、capabilities、manifest 门禁之前路由。读取不会执行模型、构造下一次 synthesis 请求、创建 Task、分配正式 ID 或写正式 B 记录。

## 入口与结果

```powershell
py -3 scripts/python/plan_capabilities.py --repo-root . validate-candidate --run-id candidate-check --input-stage 3b --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --candidate logs/ci/<date>/candidate.json
py -3 scripts/python/plan_mvg.py --repo-root . validate --run-id candidate-check --input-stage 3b --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --candidate logs/ci/<date>/candidate.json
py -3 scripts/python/dev_cli.py plan-capabilities --stage validate-candidate --run-id candidate-check --input-stage 3b --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --candidate logs/ci/<date>/candidate.json
py -3 scripts/python/dev_cli.py plan-mvg --stage validate --run-id candidate-check --input-stage 3b --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --candidate logs/ci/<date>/candidate.json
```

`run-id` 仅标识本次调用。缺省 `input-stage=legacy` 保持原合同；`planning-contract` 只属于显式 3b prepare。新读取入口要求 `prepared-ref` 与 `candidate`，不开放 generate/review/apply，不接受混用旧 Task/readiness/manifest/evidence 门禁。根路径和候选路径沿原 `root_path`、`Observations`、`checked_path` 校验，先检查 lexical 根，不用 resolve 隐藏 Windows junction。

结构通过返回 `claim=candidate_structure_only`、`formal_adoption=false`、`readiness=false`、`runtime_verified=false`。`facts.graph` 明确报告 SCC 与有限检查范围，`termination_proven=false`；`facts.accounting` 不声称完成。`model_dispatch_count=runner_dispatch_count=0` 只描述本次读取。manual/external 标签、上游模型历史声明、相同 input_identity 都不证明作者读过全部原文。

## 精确公开格式

公共辅助格式的完整字段、必需性、枚举及 null 位置由以下独立 Draft 2020-12 schema 拥有：

- `docs/planning/b-route/schemas/planning-candidate.schema.json`，`$id=newrouge.b-route-planning-candidate.v1`。
- `docs/planning/b-route/schemas/flow-graph.schema.json`，`$id=newrouge.b-route-flow-graph.v1`。

它们复用原 common 的 String、PartKind、PartResponsibility、LogicalDefinitionUse、RequirementVerification、CoverageRow，以及原 plan 的 Requirement、三关系、applicability 与来源结构。它们不是第七类正式记录，不加入 codec 的正式 identity registry，不放宽 plan.v1 的字段集合或 adoption_proof_refs。

候选 envelope 恰含 `schema_version,input_stage,input_identity,provenance,content`。`provenance` 恰含 `kind,declaration,upstream_model_history,draft_chain,final_draft_identity`。manual/external 要空链、null 最终身份；上游模型历史为 unknown/declared_none/declared_model，均是声明。model_draft 要 declared_model、完整有序原链及最终身份；复用 `validate_draft_chain` 检查冻结原输出 schema、相同 input_identity、连续 ordinal、batch 后 synthesis 的 stage 和全部有序 parent identities。至少全部 batch 与最终 synthesis；最终原 content 与本候选 content 严格相等。解析或链失败不会降级 manual/external，不构造额外请求，也不做下一次 synthesis 容量预检。

`content` 恰含以下字段：

| 字段 | 合同 |
| --- | --- |
| source_identity | 原 manifest_ref/ledger_ref/source_revision/source_manifest_digest；精确匹配 prepared 原 native 对象与原字符串 |
| requirements | requirement_id/source_block_ids/acceptance_intent/non_task_sinks/prior_requirement_ids；temporary proposal 保原 proposal: ID，prior 只作回链 |
| out_of_scope_requirement_ids | 原全局分母中本 scope 外的完整清单，不自动改为 deferred |
| selected_dependencies | 显式选定的完整七字段 PlanRef；仅从 prepared 原字节映射读取 |
| definitions | flows/commands/states；同类型与 ID 只有一个有效 owner |
| logical_references | 新 proposed use 或原 LogicalDefinitionUse |
| requirement_verification | 原唯一处置与 evidence_ids；逐 Requirement 恰一行 |
| requirement_route_memberships | 原 requirement_id/flow_id/observable_role；完整 Requirement×Flow 角色 |
| requirement_evidence | 原七字段；按 (requirement_id,evidence_id) 去重，证据只引用同 Requirement 路线 |
| evidence_source_refs | 原 OwnedRef，严格 owner/locator 对应与 raw bytes，拒绝未使用描述 |
| coverage_table | 对应 verification 删除 evidence_ids 后的完整七字段对象，全等投影，不补旧字段 |
| applicability | 原处置、理由及 other_verification_refs；other_verification 对应明确验证义务 |
| unresolved | requirement_id/reason/source_block_ids；恰好覆盖 source_gap，不计完成 |
| implementation_objects | id/kind/availability/owner/expected_type/lifecycle/target_ref/later_checks；planned 可 null，existing 要可解析原字节引用 |

新 use 为 `{kind,definition_id,proposed_owner_key}`；已有 use 为原 `{kind,definition_id,owner_plan_id,owner_revision}`。两者是不同封闭分支。proposed_owner_key 不是已分配 plan ID/revision。commands/states 保 `id,proposed_owner_key,requirement_ids,responsibility,uses`。Flow 保 `id,proposed_owner_key,capability_ids,requirement_ids,source_block_ids,entry_condition,branches,handoffs,state_owners,parts,observable_result,verification_targets,ui,human_verification,graph`；capability_ids 可跨 Capability，不证明正式 owner 权威。

每 Flow 四种 PartKind 各一行，适用时责任非空，不适用时明确源理由。UI 和人工义务分别含 applicability/rationale/responsibilities/owner；适用时责任非空。UI 额外始终保 inputs/feedback/scene_entry/scene_return，适用时四组非空。planned 对象不要求真实 C# 类型或场景存在；later_checks 保类型、编译、绑定和引擎检查的后续义务，结构通过不能替代它们。

## 图与所有权

Graph 恰含 nodes/edges/boundaries/loops。节点为 id/responsibility/owner/command_uses/state_uses。边为 id/from/to/condition/responsibility/owner。端点为 `{flow_id,node_id}`；节点、边、边界、循环说明及交接 ID 分别在所属 Flow 内唯一，内部同名可跨 Flow。所有端点必须对应真实声明节点；旧 plan 只有文字 Flow 时不会据此制造外部节点。

Boundary 为 id/kind/node/condition/required/rationale，kind 为 entry/success/failure/cancel/return；一个 required entry，至少一个 required success。一个节点可以有多个边界角色。branches 明确 failure/cancel/return 的适用性、理由及精确 boundary_ids。不要求边界是 sink。handoffs 的 from/to 必须对应实际边；状态、命令和交接 owner 均解析到唯一声明 owner。

Loop 为 id/anchors/exit_boundary_ids/description/exit_condition。使用非递归 Kosaraju SCC，识别真实自环和多节点循环。一条说明可通过多个 anchors 覆盖多个 SCC，所有真实循环必须有关联说明，说明出口必须解析并从相应分量可达。每个 required boundary 从所属 entry 及相关已进入循环位置可达。成功边界可位于 SCC 内且继续重入，不要求每 SCC 外出边，不强制可选节点从入口可达或每个节点最终终止。

selected_dependencies 明确选当前候选需要的冻结修订；其他冻结历史修订不竞争 owner。完整 TypedReference 闭包及 OwnedRef 原 bytes 从 prepared 的 raw-index/archive 构建只读映射，root=None，无磁盘回退，不自由查找当前 catalog。既有内容匹配只证明冻结内容与引用相等，不证明 published/current 权威。当前候选与显式选择依赖中的同类符号 owner 冲突、未知符号、错误 owner 修订均阻断。

Requirement 主分母来自当前审计 proposals；保留的既有 Requirement 仅从显式 selected_dependencies 选定的有效精确 PlanRef 读取。任意 context 中恰有 requirements 字段，或同一历史原文在 text/json 之间改换解析格式，都不会激活当前 Requirement 域。previous_plan_ref 等纯历史引用的完整闭包仍验原 bytes、正式 schema 和引用完整性，但不会授予历史版本当前资格，历史同 RID 旧 body 不与有效版本竞争。每个选定既有 Requirement 用所属 plan 的冻结 source_identity/ledger 将原 block ID 映射到 source_path，再与当前受治理 closure 核对；不把旧 block ID 改写成当前 ledger ID。scope 外既有项保留在完整 out_of_scope_requirement_ids，不自动生成 deferred。两个显式有效依赖中的重复既有 RID 必须具有相同原 body、原 block 声明及相关 manifest source bindings；冲突拒绝，不取最后一次出现。候选图自己的 source_block_ids 仍只绑定当前 native ledger，不混入旧 ledger。

## 身份、日志和失败

`_b_route_schema_resources.py` 是正式六记录与辅助格式共用的离线 registry。未知 $ref 不联网；缓存键包含实际原字节，因此同长度、同 mtime 的 schema 变化也失效。正式记录入口资格仍由原 codec registry 限定；formal-only 部署不因缺少两份辅助 schema 失败。

只写 `logs/ci/<date>/b-route-candidate-check/<run-id>/<check-identity>/`；失败写独占 failures。check identity 包含当前 input_identity、候选 raw digest、相关源码、运行时及完整 schema raw digest。完成目录保 candidate.json、candidate.raw.json、完整原观察归档、report 和最后写入的 event。当前 prepared、原字节及规则发布前再次核对；未变的完整当前检查可只读复用。输入或规则变化阻断旧身份或产生新身份，无关 HEAD 不单独失效。

partial write 不修复原目录、不补写旧 event；返回 blocked/partial_write 与真实 partial_ref，并尽可能在新 failures 保存恢复 report。诊断本身也无法写入时 resume_ref=null，保具体现场位置，不能把旧成功 report 当作恢复入口。

## 验证与真实证据边界

`test_b_route_candidate` 阳性使用明确的只读 audit assembly seam，只证明组装、公开 schema、图、关系、引用和 CLI。真实 synthetic 拒绝及原真实负向 proof 继续单列；没有新真实模型请求，没有合格真实 3A 阳性材料，不声称真实正向准入已验证。已知六项旧基线失败保留原证据，不以定向通过说全套绿。

开发验证日志位于 `logs/ci/2026-11-05/story24-tests/`：impl01 是受限 token 的私有 TEMP 权限失败，impl02 的 17 项候选/算法测试全部通过、无 skip、真实模型调用 0。后续扩展矩阵及最终冻结验证由主线程记录；本文件不提前授予原生审核或本地提交完成状态。

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B ..\run_story24_tests.py <unique-label> test_b_route_candidate test_planning_dev_cli test_b_route_records test_b_route_planning_input
```

候选/admission/正式采纳及运行资格是不同阶段。独立语义审阅、实际生成与候选评选属于 2.5；持久身份、可移植完整图采纳与正式 receipt/catalog 写入属于 2.6，不能将完整图丢为文字摘要或提前伪造正式记录。

最终原生审核：14 条逐项裁定，13 条完成最小修复（12 组），1 条驳回；独立复核确认 E1/G1–G3 闭合。主线程 root-review-final-12 实际 291 项，286 通过、5 项既有 legacy errors 与旧基线精确相同、0 skip；候选 44 项及 14 项旧门禁全部通过，源码前后字节不变。缓存报告与原候选重算比对，State 使用对应 Flow 声明，交接保持 Flow 归属，依赖证据及 manifest 唯一绑定均失败关闭；SCC 第二遍不重遍已处理分量。真实准入阳性仍未验证，不新增真实模型请求。

## Story 2.5 执行边界

上述结构读取合同保持不变，不提供真实执行准入。显式 profile 绑定的执行入口见
[Story 2.5](story-2-5-independent-admission-selection.md)。这些独立阶段复用本候选及
schema owner，另须重放原执行证据；不会把 manual/external 候选或 structure-only
PASS 晋升为真实准入。
