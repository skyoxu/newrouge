# Story 2.5 定向审核修复交接

## 回环4 CI 准备与维护选集

`run_gate_bundle.py` 的 `B_ROUTE_RUNTIME_DETERMINISTIC_TESTS` 是专用 PR 与两个 hard bundle 的共同显式选集。回环4补入 provider schema、indexed review/schema delivery、review/partial/path recovery、Capability synthesis、MVG prepare/synthesis/wiring、worker recovery 以及相关历史 source epoch 负例；新增 loop4 入口控制也由同组选集维护。wiring 原三稿链、ordinal 3 与原 prefix 断言保留。上述夹具包含上游资格或协议叶边界 stub，维护检查不等同原 native 准入。

三个实际 CI caller（`b-route-runtime-deterministic.yml`、`windows-quality-gate.yml`、`ci-windows.yml`）在运行前共用 `scripts/ci/prepare_b_route_runtime.ps1`。该脚本只在 runner 的独占 `RUNNER_TEMP/nr-br-runtime` 下创建 venv、双编码缓存与测试 TEMP；以官方 PyPI 安装既有固定版本 `jsonschema`/`tiktoken`，预热 `cl100k_base` 和 `o200k_base`。没有切换镜像、系统安装、激活 venv 或改写 PATH。安装 report、原输出及编码缓存哈希放在 `logs/ci/b-route-runtime-environment/`，由既有 always artifact 步骤保存；report 记录实际解析闭包，不声称它是依赖 hash lock。

准备脚本仅导出 `BR_PYTHON`、`BR_TIKTOKEN_CACHE_DIR`、`BR_TEST_TEMP`。hard bundle 只对新增 runtime 子命令使用这些值并设置 high 合成环境，其余既有 hard 命令继续使用原 launcher 与环境。七个新纳入维护的夹具只将固定 Windows TEMP 改为 `tempfile.gettempdir()`，Root/runner 可以提供任务私有短 TEMP；未更改容量公式、完整草案、原 prefix、unknown、schema 或资格断言。专用 job 增补 `_capability_input_integrity`、`_llm_backend`、对应测试与准备 owner 的路径触发。

专用 job 的总 timeout 从30增至60分钟，用于扩大后的离线维护选集；这是待 hosted 运行核对的保守配置，不能当作实际耗时或通过证据。实现者仅作标准库 AST、PowerShell 语法与文本/哈希检查，未执行安装、编码下载、项目导入、任何测试、模型或 hosted job。Root 应先执行 `test_b_route_runtime_ci`、本轮新入口控制以及受影响恢复检查；有效旧纪元结果与本轮新执行分别记录。`planning-production-acceptance.yml` 未调用此 runtime 组，其既有真实模型权限与执行命令不因本次 CI 修正扩大。

## R26 回环2当前记录

本轮实际验证与限制见 [原始对账](../../logs/ci/2026-11-07/story25-loop2-review-checkpoint/summary/report.md) 和 [归档清单](../../logs/ci/2026-11-07/story25-loop2-review-checkpoint/manifest.json)。184个不同方法分批通过；32项完整运行时/compact控制和63项源码/元数据硬化控制均已自然结束、源码稳定。本轮真实模型调用0，79/290与旧unknown不变；这不是新真实producer资格、托管CI通过或正式Story完成。

全链资源政策见 [ADR-0043](../adr/ADR-0043-b-route-resource-pipeline-preallocation.md)，原329024字节packet的纯compact通过而完整wire保守展开上界拒绝，两项结果同时保留。发布/前缀恢复与写入前见证见 [ADR-0044](../adr/ADR-0044-b-route-metadata-journal-publication.md)，宿主停止/诊断及精确源码边界见 [ADR-0045](../adr/ADR-0045-b-route-host-cancellation-diagnostics.md)、[ADR-0046](../adr/ADR-0046-b-route-host-fault-source-boundaries.md)，合法部分修复、路径与CI入口见 [ADR-0047](../adr/ADR-0047-b-route-legacy-progress-paths-and-ci.md)。包名入口已实际冒烟，两个PowerShell块仅语法解析；无完整YAML解析器或托管CI执行记录。

以下R25记录属于原检查点10398b41及其旧源码纪元，不覆盖或改写本轮失败、资源政策拒绝或原R22真实资格。


R25 已完成定向工程修正及 102 个不同方法的通过记录，正式复审和 Story 收口仍未完成。原 R22 原生资格保持冻结；本分支离线结果不冒称新的真实模型资格或默认 B 激活。宿主政策见 [ADR-0041](../adr/ADR-0041-b-route-review-hardening-resource-and-metadata-boundaries.md)。

## 修改与边界

- S4-B1：语义等价检查跟随本地 helper、常量及导入的实际依赖。运输/宿主故障边界单列；公共模块其余语句和纯 helper 不允许漂移。
- S4-E1：原 append 接入 3B repair_check。语义义务只开放对应字段/分支/四部分及原图直接依赖；machine 使用宿主 diagnostic 的精确实体和字段规则；未知/歧义域拒绝。修复策略、原稿/issue 哈希、允许路径进入原实际 generation 材料、提示和重放，原稿/finding 由同槽位更早已付执行关闭。字段域保守，无法准确定位的 machine issue 会拒绝修复而不是开放全对象。
- S4-B3/B4/B5/B10：原 selector recovery 增加 `prepare`、`reservation`、`unknown` 三类元数据 journal。准备的 claim/record/run/committed 和 intent/原父 row 都有精确前后镜像。只在原 coordinator 锁内对明确事务恢复。`reconcile(root, run_dir, retained_capture=...)` 为显式宿主 API；不是新的 CLI，也不执行模型。未知原请求保守计费并终止，不重发。
- S4-B6/B7：分配前用保守 DAG/文本长度、节点与深度分析拒绝展开；v3 工作计数在编码和最终计量前止损。完整资源政策和局限见 ADR；旧规范小输入输出不变，超资源拒绝不能冒称旧 proof 不真实。
- S4-B8/G1/R1：原异常、清理异常和已捕获原字节分别保存；Windows 测试注入当前 reader 的实际等待点，保真实短自限 OS child、终止和回收；缺可信耗时保 unknown 并使用原预留回退。

## Root 必要定向验证

实现者未执行以下任何方法。新增方法和精确哈希见任务日志 `logs/ci/2026-11-07/story25-r25-review-hardening/static-handoff.json`。

1. `test_b_route_story25_review_hardening`：语义 helper-only 变异、宿主边界、资源负向及小规范样本、实际磁盘 prepare 各提交窗口、完整/部分临时字节保留、陌生/坏临时物拒绝、intent→父 row 的 unknown 保守恢复、原锁互斥、旧未 journal 阻断、cleanup 抛错与耗时回退。
2. `test_b_route_planning_runtime.RuntimeTests` 中本轮修复域、同槽原稿回放、范围元数据/提示和实际双 Flow/helper-only 迁移测试，以及原 generation 捕获→binding→reservation、两个 profile、selector、proof/replay 等直接受影响方法。不得用只跑新增纯函数测试替代必要的原接线验证。
3. `test_planning_main_audit_fixes.PlanningMainAuditFixesTests.test_interrupted_runner_terminates_and_reaps_real_child`：Windows 真 child/reader 边界。子进程自行三秒退出，测试优先主动中断并确认真实回收，不再靠三十秒等待。
4. `test_b_route_selector_recovery.SelectorRecoveryTests.test_intent_requires_original_parent_row_and_never_invents_it` 及原 source epoch/recovery/canonical 小样本直接受影响方法。prepare 多窗口使用磁盘故障注入；原 source/qualification 接缝仅明确模拟，不能当原 R22 实验已重跑。

不要重跑无关全套来声称旧 131 baseline 全绿。保留失败与 source 前后快照，按实际结果修正交付；实施者禁止实际模型、native CLI、Git 提交和新资格操作。Root 决定冻结、历史原 producer 复核和必要新验证，原费用权威保持在原 owner。

## Root 实际执行记录


已执行 102 个不同方法的通过记录，分布于多个显式源码纪元，不是单轮全套通过。原完整失败和未执行组保留。最后两项为现有 Capability/MVG 完整协调器合成协议控制：保真实 OS stdio、capture、binding、原预留、独立准入、selector、checkpoint、篡改拒绝与无调用重复读取；传输响应是合成数据，不能当作官方模型语义或 R25 当前原生资格。

此前编码资源修正单轮 54/54；后续 v3 matcher 受影响组结果见第16次执行；两项完整协调器控制在第14次 2/2 通过，后继只改 v3 匹配实现，未重跑这两项不走 v3 的控制。Windows 真子进程中断/回收与构造器错误保存、语义 helper 漂移、局部修复域、原元数据事务及 unknown 保守终止均有定向通过记录。env 专属的原 tuplecompact 实际请求测量未执行，不计入通过。

## 失败与最窄修复

- regression-06 实际执行 10/71：Windows 通过；Runtime 9 项中 4 个 error，后续余组未运行。修正测试基类的真实 fixture helper，并把 copyfile 审计事件分为只读源/写入目标；输出与独立 TEMP 写边界不变。
- regression-targeted-07 执行 56/65，v3 私有 helper 新参数缺默认值导致唯一 error；后继 13/13 覆盖该方法、v2 九项、构造器错误及真实 Windows 中断。此前成功项复用，不伪称整套重跑。
- 资源计数发现 exact-int 固定 32 与空容器低估；增加保守十进制上界、分隔符及编码前止损。自建成本边界从缺陷值 72 更正为 74；原模型/token/调用阈值和原断言未降。新修正 54 项全部通过。
- 完整协调器第 10/11 次在合成进程前被 harness 的 env/metadata 角色判定阻断，未启动子进程；第 12 次进入合成协议但 fixture 默认 medium 被生产 high 门禁拒绝。只把原局部 fixture 环境显式设 high；第 13 次完成候选链但子进程未见任务私有 tokenizer，字节回退上界令 selector 失败。只在 harness 进程环境传递已批准的同一依赖路径，第 14 次复验。每次失败独立保留，没有关闭隔离、安装软件或放宽生产校验。
- Root 额外发现 Popen 成功后 reader 构造器位于异常保存边界外，现纳入既有 try；定向测试证明保原始错误、清理异常和日志。此项为 S4-R2，自检修正；不是原真实请求重发。
- 原真实 selector 编码包的第15次纯 codec 检查揭示 regex 笛卡尔积上界会误拒已知规范输入；不是原资格失败。保留该反例，改为逐步计量且保持 escaped-literal 左端/首项/不重叠语义的确定性匹配，阈值不扩。第16次做实际差分和 v3 定向验证，第17次对原329024字节 prompt 的完整 packet执行 digest及精确规范重编码，通过；这1项兼容性检查单列，不计作新的 unittest方法或 native qualification。

## 原合同与证明范围

原 R22/6d4ab1c3cba67bebe98f75c9462af613bf9d739a 的三候选、唯一 winner、13 次请求和外部 OS0 资格保持冻结。原 qualified SHA 为 af853ce0ea84812ae30c5cf94f04ef174c5da3046ad06da0b3289f0b0e7ba36a。R25 改进不能重签或冒充这项历史资格；本检查点只关闭工程修正的离线验证。正式 Story Step4/5 尚未完成，采纳/readiness/运行资格仍为 false。

累计 campaign 最后观察仍为 79/290，release=0，旧 unknown 与失败保留；本检查点新增实际模型调用 0。high 保留，没有开启 Fast；工具未读取 UI 速度设置。服务端实际模型/推理、物理请求数和费用均未知。源码前后哈希与实际结果逐次保存在 manifest 指向的 raw JSON，不能用静态方法数替代执行分母。
