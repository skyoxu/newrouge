# MVG 集成验收

## 已完成 Capability 恢复与进度

ADR-0039 规定当前 `capability-local-selection.v1` 的候选生命周期分别运行于独立 OS 子进程。父协调器通过持久 mailbox 预留每次调用费用，独立复验 proposal、proof 和执行 receipt 后才评选三个 admitted 增量。各稳定候选槽位跨 Capability、上下文和进程累计 64 次调用；run 默认 192 次，不因恢复或换进程重置。

新执行只恢复 `run.json` 原子提交的完成 checkpoint。候选、检查、修复和评选中间文件只保留审计；未完成项换新工作区从头执行。恢复唯一匹配键为完整单项 Capability JSON 的规范化 SHA-256：对象键序与排版无关，数组顺序、类型和值有关，Git revision、catalog 元信息和其他 Capability 不参与匹配。历史 proof 对照原冻结输入验证；当前相关依赖与累计 delta 另作机器重放验证。复用写独立 `newrouge.mvg-capability-adoption.v1` receipt，不伪造当前 run 的普通语义准入；损坏、撤销或不兼容项记录原因后重新生成。显式 reopen 在推进前撤销受影响 checkpoint 及后继的恢复资格。

`/knowledge/scenes` 的 Cumulative MVG scope 通过只读 `GET /api/knowledge/mvg-progress` 展示每个已提交项及完整累计规划，区分 `new`/`reused`，后续失败仍保留部分成果。轮询采用单飞请求，生成期间写控件保持锁定，已完成内容可展开；GET 不修复活跃预算账。进度仅表示 `partial_planning`，最终完成仍需完整 proof、全局机器 audit、review、validate 和 apply；所有规划结果保持 runtime 未验收。

`POST /api/knowledge/mvg-clear` 要求现有 same-origin session token、空 JSON 请求和服务操作锁；CLI 生成与清理另共享跨进程 activity 锁。清理持久增加 `logs/ci/mvg-recovery/registry.json` 的 epoch 并清空恢复资格，旧 attempt/latest 指针、旧页面响应和晚到发布不能复活结果。历史账本留在 `logs/**`；正式 manifest、Capability、任务和运行验收历史保留。页面下一次 Generate 创建新 run。独立工作区通过 `SC_MVG_RECOVERY_ROOT`/`SC_MVG_RECOVERY_EPOCH` 绑定同一项目索引；这些变量是宿主内部协议。

本入口验证同一版本中多个功能提交组合后的行为。保留功能任务、Chapter 6 内置 review、现有交付 profile 门禁和 MVG 级知识库刷新节奏。不引入 Epic，也不自动修改任务状态。设计依据见 ADR-0037。

## 在现有章节中接入

| 阶段 | 补充动作 | 产物和检查 |
| --- | --- | --- |
| Chapter 3 任务编排 | 为跨任务链路指定整合责任。已有功能任务能承担就复用；无人承担时才通过现有任务三联流程补集成任务。 | manifest 的 task_ids 和 handoff 的 owner_task 必须引用真实任务。治理任务可以不属于玩家旅程。 |
| Chapter 4 契约基线 | 明确每次交接的生产方、消费方、归属任务、契约引用和可观察行为。 | 每条 handoff 至少关联一个测试；引用现有契约，不复制字段正文。 |
| Chapter 5 语义稳定化 | 检查 planned 测试是否有明确行为，补齐已有任务的验收引用。 | 继续使用现有 Refs/overlay 校验，不增加第二套任务状态。 |
| Chapter 6 开发和收尾 | 功能实现时逐步落地链路测试，改动时按建议优先回归；MVG 收尾在整合版本运行全部必测项。 | 精确提交或工作区摘要、执行命令、原始报告、summary.json。 |
| Chapter 7 UI 接线 | 为关键链路准备真实场景、引擎输入、状态等待与清理。 | 区分 scene-method 和 engine-input 证据；视觉、手感与空间可用性仍由人验收。 |

最初的“开发前就绪检查”拆入上述 Chapter 3/4/5，不再新建独立的重型流程。`plan` 只能发现清单结构和引用缺口，不能证明任务拆分合理或产品验收完整。

## 用户入口与执行归属

用户仍通过 Chapter Skill 提供来源或 task id。MVG 不要求把所有测试塞进一个特殊任务：每条 handoff 的 `owner_task` 负责该交接的集成验收，优先复用现有任务；只有无人承担时才新建整合任务。测试实现与修补进入对应任务的 Chapter 6，整组测试则由 `run-mvg-acceptance` 或 MVG CI 在同一 commit/workspace 快照执行。普通单任务 Chapter 6 不等于每次自动运行全部 MVG。

例如 reward pilot 的三条 handoff 分别由 Task 114、128、115 承担；它们共同引用领域/场景/引擎输入测试，而不是由某一个任务独占整个 MVG。清单是测试组合与责任映射，不是另一套任务状态。

若现有 Acceptance 显式分类为 `player-journey` 且 `journey_scope=mvg-critical|mvg-full`，最终 Acceptance 检查消费匹配 manifest、覆盖级别和当前 revision 的 `runtime_verified` 结果；缺失或过期就阻断，不会把普通任务测试报告自动升级为 MVG 证据。详见 [Acceptance evidence](acceptance-check-and-llm-review.md)。

## Knowledge 展示边界

Requirement accounting is independent of runtime acceptance. `requirement_verification` has one authoritative disposition per Requirement, matching the lossless `coverage_table` projection. `requirement_evidence` deduplicates `(requirement_id, evidence_id)` and records `kind`, `source_ref`, `covered_behavior`, `flow_ids` and `test_ids`. Newly frozen runs require both arrays; new authority rows belong only to newly accounted Requirements. Shared evidence may extend an existing row's `evidence_ids` without changing its owner, disposition or authorization. Legacy artifacts/checkpoints are read without rewriting original fields or hashes, and original verification fragments remain preserved.

Story 3.3 deploys the same deterministic route/accounting boundary at proposal admission, each reconstructed proof prefix, append-ledger recovery and final local validation. Every admitted cumulative prefix must preserve unique authority, route/evidence keys, frozen resolvable sources and consistent flow/test scope; a valid final object cannot repair an invalid accepted intermediate prefix. A historical seed retains its frozen owner-only read projection until the first new-protocol increment supplies complete memberships. Errors identify the Capability and accounting object before semantic dispatch or cumulative publication.

Apply recovery validates the prepared envelope/copies, original proposal and proof, exact journal authority inventory, and both actual trace/manifest payloads before any target write. Live authority checks retain the existing journal rules, allowing its own valid partial after-images; recovery does not rerun freshness against an already replaced predecessor. New-protocol fields cannot be deleted to downgrade recovery. Historical completed journals and checkpoints keep their original hashes, owners, dispositions, evidence and completion counts; independent read projections expose routes without rewriting those objects. This final audit covers the frozen cumulative accounting scope. No planning check grants runtime acceptance.

Story 4.2 adds deterministic `plan-mvg --stage audit`, automatically run after the complete selected chain. Repeated Requirements, shared Contracts and overlapping journeys are ordinary overlaps. An explicit reviewed declaration under `logs/**` may report a real source conflict using `--conflict-report <repo-relative-file> --conflict-report-sha256 <exact-file-hash>`. The `newrouge.mvg-source-conflicts.v1` declaration binds `run_id`, `analysis_identity_sha256`, canonical `checkpoint_head_sha256`, canonical `proposal_sha256`, `status=reviewed`, `reviewer`, `rationale` and nonempty `conflicts`. Each conflict has a unique `id`, `kind=source_conflict`, `severity=hard`, explicit `contradiction`, affected `capability_ids`/`flow_ids`, and `source_refs` with frozen repository-relative `path`, raw-file `sha256`, and exact `citations` (`line`, original `text`, including its line ending). These declarations supply reviewed semantics; the audit validates identity and evidence without inferring natural-language contradictions or calling another model. Missing or drifted evidence cannot authorize reopening.

Inspect the audit, then explicitly request `--stage reopen-plan --audit <run-relative-path> --audit-sha256 <file-hash>`. Inspect that plan before executing `--stage reopen --plan <run-relative-path> --plan-sha256 <file-hash>`. A source-backed hard conflict is required. The plan binds the same run, exact head/proposal/frozen input, invocation ledger and budget; it invalidates the earliest affected accepted checkpoint and every cumulative successor, with an explicit replacement order. Changed identities or any existing pending/completed apply journal reject execution with diagnostics under the run. Product-source changes still require their owner; reopening never changes those authorities or an applied baseline.

Reopen uses the shared activity lock, coordinator lock and a single atomic `run.json` switch. Before revocation it persists an immutable `reopen-transactions` intent binding the exact prior/pending states and plan. An interruption requires the explicit same `reopen --plan ... --plan-sha256 ...` retry; ordinary consumers report `pending_reopen_same_plan_recovery_required` and read-only views never repair it. Recovery verifies the frozen historical proof, exact disk projection, current epoch/authority and retained prefix, completes any missing revocation, then commits the pending state and immutable completion receipt. It never restores revoked eligibility or refunds calls. Content-addressed audit/plan/history and original checkpoint/selection/proof bytes stay immutable. `proposal.json` remains the current projection; history embeds its original proposal. New generation paths and candidate lineages isolate every replacement, while candidate cumulative 64-call and run budgets retain all prior charges. Each replacement again requires three independent admissions, comparison and atomic checkpoint. The complete source-bound conflicts and plan are supplied to generation and the existing independent admission review. Cumulative `resolution_boundaries` assign each conflict to the latest affected Capability or flow-change checkpoint: earlier scopes retain its context without certifying future replacements; at that boundary and every successor, exact `reopen_reviews` must report it resolved against the replacement and predecessor. Final audit binds these resolutions to the replacement checkpoints; missing/unresolved reviews remain blocking evidence gaps. Local recovery revalidates the same complete prefix without charging another call. This offline capability is covered by `test_mvg_global_audit.py`; historical production acceptance does not certify a paid execution of this new path.

`accounted` and `satisfied` are separate. `flow` and `other_verification` require all referenced authoritative proof and complete route coverage to satisfy; `deferred` remains unsatisfied; `source_gap` blocks planning completion. Prepared copies retain byte-exact inventory hashes. Source references use canonical repository-relative POSIX paths; independent live reads compare UTF-8 content after BOM and newline normalization, retaining original raw hashes for audit. `implementation_reference` only proves code/test existence and does not block subsequently appended authoritative proof. `verification_record` resolves explicit frozen passed JSON (also accepted inside a document JSON fence), binding Requirement IDs, behavior and flow/test scope. `runtime_acceptance` resolves only `logs/ci/mvg-acceptance/<run>/summary.json` with its derived sibling `input-manifest.json` and `snapshot/<manifest>` bytes. Validate the producer inventory digest, main/workspace identity, full base commit, exact manifest path and snapshot manifest hash/content together; Capability revisions and later Knowledge commits are unrelated. Knowledge rechecks independently available source bytes against the manifest-bound trace; unavailable or drifted sources display gaps. Planning success and accounting satisfaction never set whole-MVG `runtime_verified`.

[Knowledge 的场景页面](project-health-knowledge.md) 提供当前 main 的 GDD 候选版本与累计 MVG manifest 的只读汇总：flow、handoff owner、任务、测试和精确匹配当前 revision/manifest 的运行摘要。未追踪来源的任务不能被归属到某个 GDD，静态场景关联不能证明实际可玩。页面上的任务验证按钮不能代替整组 MVG 执行。

完整核查路径是：manifest（范围/责任/测试）→ CLI `plan` / `recommend`（结构/影响建议）→ `run` / CI → `logs/ci/mvg-acceptance/<run-id>/summary.json` 与原始报告。Knowledge 汇总帮助定位证据，但人工可玩性判断仍需实际试玩。

## 清单与责任

当前清单分三层：

- `docs/testing/mvg/reward-pilot.json`：单一奖励链路 pilot，仅用于窄范围示例与反例实验。
- `docs/testing/mvg/m1-critical.json`：当前默认可执行的多 flow critical regression，只引用 Taskmaster 中已 `done` 的关键 Continue/Resume 与 Combat→Reward→Return 边界。
- `docs/testing/mvg/m1-full.json`：M1 自动化 full-scope 目标 inventory。它把 New Run→Map、Map→Node、Continue/Resume、Combat→Reward→Return 全部列入范围；只要 scoped task 仍非 `done`，就必须把对应 task id 写入 `coverage.blocking_task_ids`，`run` 模式会 fail-closed，不能产生 full runtime_verified。

`m1-full` 的每条 flow 显式列出 `requirement_ids` 和 `capability_refs`，冻结的是该玩家旅程的语义范围。Task 103 保留为历史 Continue 评审证据 owner；其 `NFR-T0103` 要求拆分 Chapter 6 评审通道，属于工作流治理，不能由 Continue 运行时旅程证明，因此不列入这些 flow 的 Requirement 成员。Task 110 同样保留为历史证据引用，但地图节点路由清单不承担完整遗物 run-trigger 效果执行的 `FR-T0110`。这些需求仍保留在 GDD、任务和 Capability 中，未被延期、退役或声明已由该 MVG 验证。规划器仅对旧 flow 缺失的成员字段读取任务视图回退，不扩大已有显式成员。

累计规划保留旧测试和原交接点的测试绑定，同时允许同一 flow 内追加 `planned` 验证。新增项由 CLI schema 与本地归属检查共同约束，必须给出真实 owner、Requirement、handoff 索引、输入、断言与实现验收；不得跨越所选 flow 范围或将旧测试重标为 planned。它是待实现的验证计划，不是已通过的运行时证据。只增加原交接点的测试义务不构成基线削弱；修改行为、归属或移除旧测试仍需规格依据及独立审查。审查返回结构化 `repair_action`，缺少验证修补当前 flow，只有错误归属才触发路由重分配；修复器接收该条审查 rationale，而不是只有错误编号。

每个 manifest 必须包含 `coverage`：`mode`、`scope_id`、与 flow 顺序完全一致的 `required_flow_ids`、真实的 `blocking_task_ids` 和非空 `excluded_claims`。这让“跑完整个当前清单”与“整个 M1 MVG 已覆盖”成为两个不同命题。

扩展时复制其结构，替换 mvg_id、coverage、flows 和 tests，并逐条核对范围：

- flow：可观察 outcome、真实 task_ids、显式 source_paths、handoffs、test_ids。
- 更新现有 flow 的 `outcome`、`requirement_ids` 或 `capability_refs` 属于语义重写，即使只是扩展映射，也必须在 delta 中附带真实规格 `authority_ref` 和已审阅的 `authority_review`；无此授权时 apply 阻断。保留旧 flow 的身份本身不代表它的语义字段可被静默改写。
- critical/full 执行仍要求真实 producer/consumer 功能任务先 done；若某任务仅作为 handoff `owner_task` 承担本次整合验证、从不作为 producer/consumer，则它是专用整合 owner，不以“自身先 done”阻断同一次 MVG，避免形成自依赖。
- handoff：producer_task / consumer_task / owner_task、contract_ref、behavior、test_ids。
- test：唯一 id、kind（dotnet/gdunit）、state（planned/implemented）、仓库相对 path、evidence_level、min_tests；dotnet 还需测试类 selector。
- planned 允许测试文件暂不存在；run 必须全部 implemented 且文件存在。implemented 只表示实现已存在，不表示通过。

清单验证器检查归属、任务引用、测试覆盖关系和文件存在性，但不理解行为语义。事件契约引用表示交接设计来源，不代表测试已断言事件总线发布。跨层真实性需看测试实际调用路径。测试入口不得使用重建领域模型的 fake 作为生产集成证据。

## Windows 命令

```powershell
# 默认清单现在是可执行的 M1 critical scope：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode plan
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode recommend --base origin/main
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode run --snapshot commit --revision HEAD --godot-bin $env:GODOT_BIN --challenge-input
# 目标 full scope：先以 manifest 当前 blocking_task_ids 和 required_flow_ids 做 plan；任何阻断存在时 run 必须 fail-closed：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --manifest docs/testing/mvg/m1-full.json --mode plan --snapshot commit --revision HEAD
# 开发中的未提交改动：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode run --snapshot workspace --godot-bin $env:GODOT_BIN
```

可通过 `--manifest <repo-relative.json>` 选择其他 MVG。正式收尾优先 commit 模式；workspace 模式记录文件内容摘要，不得冒充某个提交的验证。运行器将输入复制到独立快照，隔离 user:// 数据，复用 xUnit 和现有 GdUnit4 Windows Junction 入口。全局预算默认 900 秒，可用 `--timeout-sec` 调整；超时不是缺陷被检测的证据。

每次输出到 `logs/ci/mvg-acceptance/<run-id>/`。plan/recommend 返回成功时 runtime_verified 仍为 false。run 只有所有清单测试实际执行、达到 min_tests、零失败、零跳过且进程成功，才会标记 runtime_verified=true。缺报告、空报告、错误测试选择、计数不一致、重复用例结果和准备失败均阻断。测试类/套件身份精确匹配，不接受近似名称。摘要只代表该清单范围与该输入版本，不能自动写任务 done。

## 奖励旅程试点

领域测试组合真实 CardPoolCatalog、CardPoolSelectionService 和 DeterministicOfferService，验证相同上下文重新进入时奖励锁定稳定。引擎测试实例化真实 Main 与 EventBus，通过准备接口建立已结束战斗的奖励状态，随后使用 Viewport InputEventAction 激活 UI，验证选择一张卡、领取入口移除、金币准确增加配置金额、领取剩余奖励后返回地图。独立 scene-method 套件向真实结算入口重复提交同一领卡/金币请求，验证第二次拒绝且资源只增加一次。

准备/观察接口可以读取状态；触发领取不能直接调用业务方法或手工 emit pressed。等待以界面/领域状态为条件，使用有上限的逐帧轮询，超时输出场景与状态；清理节点、输入和语言设置。此测试主动设置按钮焦点，不证明导航顺序、鼠标命中、遮挡、OS 输入或存档重载，也不证明完整战斗流程。

`--challenge-input` 在基线通过后断开领取入口的 pressed 接线。必须出现实际断言失败才认定发现缺陷；运行器缺失、编译错误或超时不算。这个反例用于检验旅程确实依赖 UI 接线，不修改生产代码。

新增其他旅程时遵循同一结构：隔离种子/存档和起始场景 → 输入动作 → 有界状态等待 → 跨层结果断言 → 清理。优先选启动到首场战斗、失败重开、结算到地图等真实高风险链路，不为每个任务强造旅程。

## 影响建议与边界

recommend 比较 Git 改动与清单中 source_paths、contract_ref、测试路径，输出命中链路及文件证据。commit 模式的清单和比较终点均绑定 --revision，不混入当前工作区；workspace 模式明确标记包含工作区改动。未知文件、无映射或取不到比较范围时回退到 full-mvg。这里的 `full-mvg` 仅表示“运行当前选中 manifest 的全部 required_tests”；输出同时携带 `manifest_coverage_mode`、`manifest_scope_id` 和 `manifest_blocking_task_ids`。只有 coverage.mode=full、blocking_task_ids 为空且对应 run 真正 runtime_verified，才有资格描述为该 scope 的 full-MVG 运行证据。所有情况下 required_tests 保持完整；related-first 仅表示优先级建议，当前执行器仍运行全部清单测试。

这是一层独立的回归建议，不是完整调用图，也不替代正式 Impact/KCP。需要覆盖新场景引用、动态加载或信号边时，以真实链路测试和显式路径补充映射；不要把“没有找到边”解释成“不受影响”。无需按任务刷新知识库。

## 可选测试强度实验

```powershell
py -3 scripts/python/run_mvg_mutation_probe.py --snapshot commit --revision HEAD
```

该实验仅在隔离快照中对 RewardEntryModifierPipeline 的两个金币边界施加已知变异。先验证原始基线，再逐个运行冻结的测试，最后恢复快照源码。输出 killed / survived / unverified 及原始证据到 `logs/ci/mvg-mutation/`。这不是全程序变异覆盖率，不作为默认门禁；survived 要调查测试缺口或等价变异，不能自动认定业务错误。可在高风险函数开发时运行，亦可在 MVG 收尾抽样，不必都推迟到收尾。

挖空回填保留为低频人工组织实验：固定原提交、契约和验收测试，在独立临时分支/快照隐藏一个小实现；让实现者仅按契约回填，独立评估者运行冻结测试和额外边界测试。记录原版本、隐藏范围、可见上下文、用例变化和反例。禁止为了通过而修改冻结测试；成功不证明语义完备，失败也要区分规格不足与实现失败。当前不提供自动回填代理或默认门禁。

## CI 与人工验收

`.github/workflows/mvg-integration.yml` 对相关改动先 plan 校验 `m1-full` 目标 inventory，再在 commit 快照运行完整 `m1-critical` 多 flow 范围并执行奖励输入断线反例；workspace 快照继续运行较小的 `reward-pilot`，专门守住未提交输入与 GdUnit4 runtime-bin 快照语义，避免把完整 critical 套件重复执行两遍。变异实验仍仅手动选择。只要 `m1-full.coverage.blocking_task_ids` 非空，CI 不得把 critical 通过解释为 full-MVG runtime verified。它不修改分支保护或既有 profile 门禁。构建日志、JUnit/TRX 与摘要一起留存。视觉/手感/平衡/性能代表性仍需要人确认；机器报告不能替代试玩结论。

同一次快照执行仅在首个 Godot 套件预热，成功后后续套件和接线反例复用构建；每套件仍单独启动进程并隔离报告。已有质量流水线负责统一恢复文档门禁，MVG CI 不重复直接调用该门禁。\n

## 累计里程碑基线

后续里程碑在现有 manifest 上增量演进，不创建互不相干的 “M2 MVG” 测试岛。先用 `scripts/python/update_mvg_baseline.py --manifest <manifest> --delta <reviewed-delta>` 预览；确认后加 `--write`。delta 绑定预览时的 manifest SHA，支持 flow/test 的 `add/update/retain/retire`。同一对象在一个 delta 中只能出现一次，update 不能改写对象 ID，apply 后会重新校验完整 manifest。

Delta application preserves baseline flow order and appends new flows in operation order. If `coverage.required_flow_ids` contains exactly the resulting flow IDs, its order is projected from the applied flow rows; a proposal's different array order is not a semantic change or a reason for model regeneration. Missing, duplicate or unknown IDs are not repaired by this normalization, and retirement or coverage weakening still requires reviewed authority.

任何 retire 或确定性可识别的基线削弱都必须同时提供可解析的仓库内规格路径 `authority_ref`（可带 `#anchor`）和 `authority_review: {"status":"reviewed","rationale":"..."}`。脚本会验证规格文件真实存在；仅填非空字符串不构成授权。范围/required flow、handoff、task/source/test obligations、implemented state、测试最小数、coverage mode 或 evidence level 的削弱都受此门禁约束。自然语言 outcome 是否语义削弱仍由人工/模型语义评审负责，确定性 updater 不冒充语义理解器。

`run-mvg-acceptance` 的 summary 记录精确 `manifest_sha256` 和可选 `baseline_lineage`。单任务 Chapter 6 只运行任务声明的测试、受影响旧回归与必要冒烟；里程碑收尾则运行当前累计必测范围和本轮新增组合测试的同一整合版本。planned 新测试、blocking task 或人工义务仍未完成时只能报告 partial/blocked，不能把稳定子集绿色改写为 milestone passed。

### MVG planning generation safeguards

候选生成采用强制准入状态机。`candidate-1..3` 是三个评选槽位，槽位可跨退役轮次补位；只有通过确定性校验、累计 delta 校验和独立语义硬门禁的当前 lineage 才能进入选择器。硬问题按发现顺序逐个处理，同一问题最多三次修复；修复后从当前未解决问题重新检查。三次仍失败则完整退役该 lineage，写入退役与修复记录，并从不可变 `analysis-input` 创建全新 workspace/context 的 replacement。replacement 不读取退役 proposal、findings、prompt 或模型工作区；外部 runner/输入故障保留可恢复状态并停止，不伪造候选或评选结果。

当前默认按冻结 Capability 顺序逐项处理。每项三个候选从同一已接受累计 seed 独立生成、机器校验及语义准入；选择器只接收这三个增量，行统一为 `viable`，落选只能由比较排名决定。累计基线只读，不成为第四候选或 fallback。选定结果成为下一项共同 seed；不足三个则记录 `selection_blocked_insufficient_admitted_candidates`，保留前缀与当前项证据，不推进下一项。最终混合 winner chain 由本地 `review`/`validate` 重验，不追加整批语义硬审查。

候选准入、修复次数、退役、replacement lineage、逐项 base/proposal/proof/receipt hash 和选择结果持久化在 `logs/ci/mvg-planning/<run-id>/`，不修改任务、Requirement、Capability 或运行时状态。页面新点击创建新 job；当前逐项策略仅通过 adoption 跨 run 复用兼容完成项，未完成模型中间态不复用。历史整批候选与 incumbent D 仅按显式旧 run 已记录策略恢复。

Story 2.2 的 checkpoint transaction ID 由 schema/run/Capability/order/base/proposal/selection receipt tuple 的 canonical JSON hash 派生。不可变 bundle 包含相同 tuple、完整 delta 和 accepted proposal，在 commit 前完成校验；bundle 的存在本身只代表 prepared。唯一可见 commit 是 `run.json` 的一次 atomic replace，同时提交 checkpoint 指针、selected 前缀、accepted hash 和 current 清理。临时写入失败不会暴露半个 checkpoint，stale base 拒绝推进。Story 2.3 仅识别 selected 中已提交事务，完整验证 payload、receipt、累计前驱及后继后允许相同 canonical 内容 no-op；对象键序和空白不影响结果，布尔与数值类型差异、数组顺序变化均构成内容变化。较早事务不会回退最新 head，不重选、不重复添加 delta 或计费。第一项提交后尚未 dispatch 下一项时，恢复继续使用第一项记录的 accepted seed。

相同事务的 payload 冲突、receipt 缺失或改变、前驱 hash 改变均在模型调用前 fail closed。共同前缀验证供 CLI 与 Knowledge 使用；证据写入 `logs/**` 对应 run 的 `checkpoint-conflicts/**`，包含 transaction ID、原因和期望/实际 hash。诊断 sidecar 不成为新 authority，冲突不修改 checkpoint、selected/head、accepted projection 或已发布 proposal。

提交异常后若无法回读磁盘，工作流仅写入 `checkpoint-commit-outcome.json` 证据并停止，禁止旧内存状态覆盖 `run.json`。下次恢复在锁内读取磁盘、校验完整前缀并确定提交结果后才允许推进。下一项提交前重验前驱链；apply journal 原子绑定选定 checkpoint 和证据，恢复同样校验，不能绕过已提交链。

MVG generation separates deterministic completeness from LLM semantics. `plan_mvg prepare` writes immutable `coverage-skeleton.json` for every active delivery Requirement and an intentionally empty `entrypoint-skeleton.json`; Task IDs are evidence owners, not one-runtime-entrypoint placeholders. 当前 append 路径按当前 Capability 新增 Requirement 生成覆盖，保留唯一权威处置与此前有效映射，不能宣称尚未准入的未来项已覆盖。以下独立 routing table 和 bounded segment 规则属于历史整批策略恢复。Story 3.1 deploys independent `requirement_route_memberships` keyed by `(requirement_id, flow_id)`, each with a nonempty `observable_role`. One Requirement may participate in multiple flows; Story 3.2 separates its unique `requirement_verification` authority from deduplicated shared `requirement_evidence`, as described above. Default append output requires memberships within the cumulative Requirement scope; duplicate pairs, unknown objects, missing roles and invalid flow membership fail before semantic admission. Accepted roles and owners survive cumulative append, narrow repairs and checkpoint replay. Legacy reads retain every original authority/evidence field and project only recorded owners, without rewriting hash-bound artifacts. Applied planning traces persist memberships alongside the manifest transaction; Knowledge accepts only an exact manifest path/hash-bound formal trace or local selected proposal. Route counts never increase Requirement completion. A non-runtime Requirement without a legitimate prepared sink or reviewed deferral remains a blocking source gap, not a fabricated runtime obligation.

Bounded flow design follows the candidate routing table. The cumulative baseline projection completes at the flow barrier, before coverage, entrypoints and tests consume the final flow rows. Repairs operate on temporary hash-bound proposals and explicit row/field/dependency scopes. An atomic repair must reduce the current issue without introducing new deterministic errors; unrelated pre-existing issues may remain. Rejected patches never become later seeds or segment caches, and previously valid mappings remain intact. A supported routing change rebuilds its dependencies and invalidates prior semantic proof. Each segment uses the environment-default model in a fresh ephemeral context; this does not replace independent semantic admission or runtime MVG execution.

Page-driven planning binds the run to the selected Capability job ID and output hash. Before advancing a page job, the prepared Capability bytes, `analysis-index.json`, and planner `run.json` must still match that identity. Current executions restore only committed checkpoints; unfinished admitted candidates are audit, even if a sibling failed. Completed cross-run adoption retains the original proof/analysis identity and separately verifies current dependencies/delta replay. Legacy selected runs without hash-bound admission evidence fail closed and require a fresh planning run.

Comparative selection writes `selection-receipt.json` beside each selection output. Recovery and publication require the receipt schema, exact selection-input hash, exact output hash, workspace-only fresh-session runner description, and matching no-tools model receipt. A structurally valid selection JSON with a missing or drifted execution receipt is not reusable and remains execution-blocked.

每项候选在比较前完成确定性、累计 delta 与独立语义准入。稳定硬问题最多三次修复，即使报告顺序变化也继续处理当前未解决问题；干净重启只读冻结来源和已选前缀。64 次 lineage 调用止损保留，执行预算耗尽不能冒充语义否定。三个准入增量只按排名选择，绑定 proposal hash/lineage 及当前 Capability/order/base；最终 review 重验整条已选链，不能换 winner 或追加语义否决。历史策略的 replacement 轮次和 D 仅用于原策略恢复。

Cumulative delta validation runs before independent semantic admission, including when recovering a durable proposal. The admission CLI schema binds accounting echoes to the exact proposal rows; malformed echoes retry only the review, with classified errors persisted in `semantic-review-attempts.json`. A blocked semantic verdict still enters the hard-issue repair queue. Frozen baseline tests that are readable in the prepared bundle are valid evidence even when absent from task-view test refs. A candidate execution failure retains its classified error and does not cancel independent sibling slots. Clean replacements remain subject to the persisted replacement budget; selection stays blocked until all three slots are admitted.

Frozen flow segments must return `change_reviews` through the CLI-enforced schema. The field is an empty array for unchanged semantic fields; changes to an incumbent flow's outcome, Requirement membership or Capability membership require a source-backed review for that exact flow ID. Generation supplies the incumbent row and bounded prepared specification excerpts. The segment gate rejects missing, duplicate, foreign-flow, unreviewed or unprepared justifications before merge and retries only the affected segment. A repaired flow replaces its earlier justification rather than retaining stale authority. These proposal justifications are not approval: cumulative delta validation and independent semantic admission still decide whether the change is supported; no machine-generated authorization or automatic baseline weakening is permitted.

Adding or removing `requirement_ids` or `capability_refs` on an incumbent flow is a change even when the added or removed value is an empty array; unchanged fields require identical presence and value.

Admission repair is locally routed when a hard issue names a Requirement or flow. Existing cumulative flow Requirement/Capability ownership remains frozen unless that exact flow has an explicit reviewed change record. The deterministic coverage gate rejects repeated authoritative coverage rows; independent route validation rejects repeated `(requirement_id, flow_id)` pairs before merge while allowing distinct routes. A requirement-scoped repair changes only its row and dependent flow/entrypoint/test data; a flow-scoped repair changes only that flow and its dependent sections, preserving unrelated memberships. Internal correction calls count toward the current issue's three repair attempts and the hard 64-invocation lineage budget; repair cannot enable overflow. Retirement starts a clean replacement in the available slot immediately, without waiting for siblings. Aggregate semantic rejection is not queued as a second issue when the reviewer identifies blocked Requirement/flow rows; those concrete rows drive repair routing.


### Capability-local append admission (current default)

Story 4.3 final completion is deployed. `validate` emits `planning_completion`, binding the exact proposal, selected checkpoint head, prepared identity, current final global audit and target manifest content. Apply and journal recovery publish the same report in the result and formal planning trace. Passed items, hard conflicts, planned obligations, Requirement accounting, evidence gaps and runtime acceptance remain separate. Only a complete valid chain/audit authorizes `planning_complete=true`; stale evidence, `source_gap` and unresolved reopened conflicts block. Pending tests and entrypoints may remain planned, and implementation references do not increase `satisfied_count`. Runtime is `not_verified`, not failed, until the existing formal `mode=run`/passed MVG receipt matches. Planning never writes runtime receipts.

Output authority is restricted to the prepared direct `docs/testing/mvg/<manifest>.json`, the fixed `docs/testing/mvg/planning/<run-id>.json` and safe planning logs. Explicit milestone handoffs use `logs/ci/mvg-planning/<run-id>/handoffs/<name>.json`; ordinary readiness rebind still needs no synthetic handoff. Reject unsafe run identifiers, absolute CLI outputs, traversal, Windows device/drive syntax, links/junctions and aliases before any writer. Journal recovery checks all targets first and permits its own valid after-images; it does not reinterpret historical completed journals as new permissions. Rejection receipts use independent safe `logs/ci/mvg-planning-rejections/`; unsafe logs produce an explicit diagnostic-unavailable error and zero out-of-bound writes. GDD/Requirements, tasks/status, Contracts, tests, game files and runtime state remain owned by their original workflows. This implements the existing authority boundary under Accepted ADR-0005; no runtime gate changes.

新 run 策略为 `capability-local-selection.v1`。coordinator 按冻结顺序逐项创建三个独立 append worker，worker 不推进已选序列；当前项各 worker 共用同一个只读 seed，准入后评选胜者，下一项再消费该胜者。一个 Capability 可以扩展多个 flow 或共享动线。语义准入覆盖每个受影响 flow、与此前项的 handoff、消费方可观察结果及失败/恢复义务；完整 Requirement/source-block/Acceptance 来源保留。

For input size, prefer complete inline requests. Oversized auxiliary references use complete-text isolated inspection batches, each with the full core authority. Contiguous fragments of a large file must reassemble exactly; every file/part is hash-bound and every model report is accounted, cited and bound to its actual input receipt. All batches are preflighted before an inspection starts. The main generator receives full Capability/Requirement/source-block/Acceptance context plus every source inspection result, rather than clipped source files. Repeated task-view rows may be encoded losslessly as shared fields plus per-view differences, and source lines addressed by citations are not duplicated in the synthesis prompt. The original rows, complete auxiliary files, path index and resolved citation lines remain in the hash-bound transport and admission proof. The repository-wide path index is local discovery metadata; prepared-reference and proposal-path checks remain authoritative. The semantic path independently inspects complete source text against the proposal and binds those inspections into admission; main approval cannot override a concrete inspected hard conflict. Core context and all reports must still fit the final synthesis request or preparation stops. Schema-domain sharing and JSON whitespace minification preserve all constraints and source values. No automatic excerpt shrinkage applies to this append path.

All inspection calls consume the existing 64-call budget. Successful identical inspections may be reused only within the same candidate and clean Capability context; reviewed proposal identity is also exact. Page clicks and clean restarts allocate fresh inspection contexts. Full input context, partition plans, reports and receipts are persisted under `capability-append/evidence-contexts/` and in the independent admission proof. Files and source text are fully delivered across the isolated calls; the synthesis call consumes their derived reports, not the original full auxiliary file bodies.

新传输计划默认使用 `newrouge.mvg-complete-evidence-transport.v3`，仍使用自包含的 `newrouge.mvg-lossless-context.v1`，保留片段位置与相对行号。至少 4096 字符且字面完全相同的原始块按起点、最长优先选取后稳定归组，优先同批共享定义；全部来源、间隙、尾部、阈值以下和非重复原文及空文件仍完整发送。每个路径/offset 保留独立 part、来源及片段 hash、地址和强制报告；独立 review 继续读取完整原文，不能共享模型结论。生产校验按确定性原始分片顺序验证，容量拆分只允许在单个原始片段内连续前进，任何跨边界、遗漏、重复或错序均失败，不能靠排序还原绕过。派发前继续检查每个字符、字段、类型与顺序。显式历史 v1/v2 保留原始 prompt、proof hash 和严格文件顺序校验，不改旧证据。最终完整包装仍需容量预检，归组不保证满足总预算。本地有界缓存只存精确包装请求及限制对应的容量测量，不存模型结果或跨 run 检查证据。

Stage-cost reports account for the known inspection batches plus synthesis, other unfinished candidates in the current scope and its selector. Future scopes have unknown accepted bases and may permit zero-call adoption, so their conservative fresh-generation estimates are reported separately and never treated as hard minima. Recheck the unchanged remaining lineage/run allowance on entering each scope, after dynamically planned reviews and before selector retries. `mvg_stage_cost_budget_insufficient` stops the coordinator without further dispatch and is not a semantic defect to repair. This is a rolling known-cost guard, not a guarantee that unknown future outputs or repairs fit. Default 64/192 limits are unchanged; a complete frozen capacity replay can still show an unaffordable workflow.

Inspection citations are exact 1-based source-part line addresses enforced by the CLI output schema. Compact line labels do not remove or normalize original source characters. The caller resolves cited text from the immutable part and keeps it in the transport proof; synthesis receives the exact addresses and derived facts without duplicating the same source lines, so paraphrased quote strings, foreign-part addresses and out-of-range lines remain invalid. Identical repeated schema objects may share `$defs`, preserving every validation constraint.

Each stable hard issue receives at most three repairs. Repairs preserve accepted predecessors and valid unrelated increment rows and cannot introduce new machine/semantic defects. Three failed repairs restart the same Capability using immutable prepared inputs plus accepted predecessors only, without failed proposals, findings, prompts, segments or workspaces. A Capability cannot be skipped. Generation, repair and semantic checks share one durable 64-call lineage budget; slice restarts do not reset it. Exhaustion retires the complete candidate batch without automatic full-batch replacement. Deterministic input/preparation failures stop locally.

Story 4.1 已部署持久 dispatch 预算：`prepare --run-invocation-limit <positive-integer>`（公共 `dev_cli.py plan-mvg --stage prepare` 同参数）把默认或显式值及来源同时冻结在 run、analysis index 与 input envelope，缺省值为 192。恢复不得修改 `run.json` 扩额，也不重封旧 run 的身份 hash。coordinator receipts 是总账；lineage 与 worker 只投影相同 reservation ID。最终沙箱复制、schema/prompt、来源 freshness、runner 输入与可用性预检完成后，在 runner dispatch 边界持久预留一次。只有准备工作不收费；已预留的超时、坏 JSON、transport 失败及未知中断不退款。`dispatch-receipts/**` 保留阶段、attempt、时间、输出 hash 或错误类，`model-execution.json` 从总账与回执投影进度。lineage 达限为 `retired`，run 达限为独立 `run_blocked_budget_exhausted`，保留已选前缀及全部诊断；同 run 恢复不再调用，也不自动创建新预算。用户明确的新页面请求仍创建新 run 与新证据。依据 `ADR-0005-quality-gates` 验证该离线矩阵，不把执行预算错误转成语义 finding。

Missing Requirement rows are repair targets from the immutable cumulative Capability scope, even when absent from the failed proposal. Machine diagnostics carry explicit Requirement/flow/test addresses; missing entrypoints are routed to the affected handoff flows. Candidate defects receive the same three-repair policy rather than being treated as input preparation failures. Repairs cannot add unrelated runtime entrypoints. New or changed entrypoints and every flow linked through a shared entrypoint enter the independent increment review, including unchanged predecessors and their complete owner Acceptance/reference evidence. Admission recovery recomputes this projection and rejects proofs that omit those boundaries.

全部项选定后执行完整机器/累计 delta 校验，不进行整批模型语义硬审查。最终 proof 从原始 seed 回放所有选中 records，逐项保留独立 reviewer receipt；`review` 与 `validate` 本地重验链。当前项候选证据位于 `candidates/<candidate>/scope-<N>/capability-append/`，比较证据位于 `capability-selection/scope-<N>/`，最终 proof 位于 `accepted-chain/`；`run.json.capability_selection` 展示当前项、已选前缀、累计 hash 与调用计数。

此前整批 append/segmented 细节仅用于显式旧 run 的原策略恢复。新页面点击分配全新逐项 run；兼容完成项经 adoption 复用其原始证明，未完成模型中间态只保留审计。

### Incremental harness regression (T26)

```powershell
py -3 -m unittest discover -s scripts/python/tests -p test_milestone_two_stage_integration.py -v
```

This two-stage fixture exercises source accumulation, task preview/apply/export, sparse overlays, Chapter 5 reconciliation and handoff, cumulative baseline updates, and regression evidence consumption. It preserves the old done task and subtasks, blocks planned tests, proves that a passing new shop test cannot hide a failing old reward regression, and accepts both only after correction on one committed revision. Replaying a stale task preview is rejected without changing the triplet.

The fixture replaces the engine adapter with deterministic subprocess assertions and actual TRX parsing in git snapshots. It validates workflow integration, not Godot gameplay or the real next-milestone GDD. Actual milestone acceptance still requires the manifest's real engine/domain tests and human obligations. Chapter 6 rejects previously passed evidence when the current worktree has tracked or untracked changes, even if HEAD is unchanged.
