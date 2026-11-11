# Story 2.5 回环 4：入口、业务分类与初始化发布

本页说明 r35 工程修正。旧 R22/MVG、dc245b3/Capability 原生资格仅属于其原 producer；本轮代码、离线合成控制不改签旧 proof，不授正式采纳、readiness 或运行资格。规格冻结块、原费用与 unknown 现场不变。

## 新建 run 与真实请求边界

`_b_route_planning_runtime.create_run` 在新 state 显式启用已有 `PROVIDER_SCHEMA_POLICY`。generation 经原 `invoke_data` 编译实际 producer schema；原 canonical envelope、parent 顺序、重复、类型及完整 draft-chain 校验继续执行。旧 state 缺少此策略时保持旧 schema、prompt 和 replay，不补写旧记录。

共同 `prepare_dispatch` 在预留之前同时检查当前进程 `NEWROGUE_CODEX_REASONING_EFFORT=high`、捕获的 `runner_configuration.backend_info.requested_reasoning_effort` 以及当前 runner 的 `--describe`。worker 与 selector 共用该入口；worker 在外发前再次核对。`operate` 取得 runner description 后提前报告不一致。`--describe` 是本地元数据动作，没有 model turn；请求配置不代表服务端实际模型或推理证明。

通用历史 `verify_call`、`validate_execution` 不读当前环境解释旧回执；本轮 live 规则没有加入这两个历史 verifier。

## 有界机器业务替换

原 `machine`、candidate owner 及关键 canonical 函数保持不变。新 state 显式启用 `newrouge.b-route-machine-business-replacement.v1`，由同一 runtime 文件的完整 raw hash 纳入既有 `rules_identity`。该版本还写入完整请求 materials 和 admission proof；原 replay owner 独立重算并拒绝删改。

新 `admission_machine` 在原机器诊断之前，复用原 schema、draft provenance、TypedReference、record、OwnedRef、source_documents 与 check_sources，验证完整冻结引用闭包、selected dependency schema/ID/revision/digest、manifest/source revision 和不可变 Requirement 投影。它只读验证，不修补候选或生成业务 owner，防止较早的 duplicate 诊断遮蔽后续来源错误。

`repair_is_local` 重新运行上述验证并精确匹配原宿主 issue。对于已证实的“同 Flow、Command 或 State ID、不同 proposed 定义”且原 native tuple-owner 诊断、原 repair_domain 无局部位置的情形，返回不可局部修复，由原 append/replacement 回路执行有限 clean replacement。不能凭 code 前缀、模型 detail、任意 SEMANTIC_ERROR 或捕获 unresolved 获得替换资格。其他未证明的无局部 owner 仍失败关闭。

原三次 issue repair、三轮 run 级 replacement、每槽 64、Capability 96/MVG 192、阶段时钟及 unknown 占用不变。fresh context 只有原冻结输入和已接受 seed；不伪计三次修复、不修改 selected originals、不释放 unknown。

## 完整目录发布

初始化先在同一父目录独占创建 `.init-<nonce>` staging，写入并核对完整冻结输入、run.json 和 initialization.json，再使用 Windows 不覆盖既有目标的 `os.rename` 一次发布目录；不使用 `os.replace` 发布目录。

任一前置写点中断只留下非权威 staging；它保留原始证据，后续可另建独占初始化。旧权威 partial/foreign 目录不自动采用或删除，缺少 run.json 的目标在原 coordinator lock 之前拒绝。竞争发布最多一个成功，失败者 staging 保留；已发布完整 run 的重入继续走原锁及身份验证。原 unknown ledger 不被推断为未执行。

发布 owner 明确限制 Windows，与项目现有 Windows worker/CLI 合同一致。新初始化标记只描述最初完整发布，不是新收费权威或 selected/checkpoint journal。

## 验证边界

`test_b_route_loop4_runtime.py` 新增入口、provider parent 元数据、high 共同边界、真实候选 tuple/混合错误、原 replacement、实际 Windows 竞争与写点中断控制，以及两个 profile 的完整合成 stdio/binding/admission/selector/checkpoint 组合。完整组合直接使用真实 fresh create，不经过旧 fixture 的历史策略转换。

旧 `RuntimeTests.create` 的原 plain/core/compact 控制明确转为历史策略 absent；完整协议 helper 根据捕获 policy 检查实际 producer schema，原 canonical 解码和所有业务断言保留。provider/indexed-review 的旧叶夹具仅补明确历史账户上下文；它们不证明完整 runtime 身份。

实施作者仅完成源码文本、标准库 AST 和哈希核对，没有运行项目 imports、helpers、测试、安装、native、模型、网络或 Git。实际方法执行、完整 YAML、CI 安装及 hosted job 结果均由 Root 后续验证。CI 准备与维护选集见 [回环硬化 owner 说明](b-route-story25-review-hardening.md)。
