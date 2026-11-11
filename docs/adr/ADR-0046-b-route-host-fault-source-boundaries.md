# ADR-0046：精确的宿主故障源码边界

- 状态：提议；实现已冻结，交由 Root 审核与执行。
- 日期：2026-11-07。
- 范围：Story 2.5 第二轮审核，仅涉及源码身份工程。
- 基线：`10398b4179cd15342b2c0db02111136180654025`。
- 守卫政策：`newrouge.b-route-host-fault-source-boundaries.v2`。
- 相关文档：[ADR-0045](ADR-0045-b-route-host-cancellation-diagnostics.md)；本记录的规范目标为 [ADR-0046](ADR-0046-b-route-host-fault-source-boundaries.md)。

## 背景

此前批准的宿主例外允许修改 `run_isolated_model`，同时仍比较 common 模块的其他每条语句。Windows 停止与读取取消的握手还会修改三个读取器方法，并新增一个停止辅助函数。AppServer 的独立清理会修改一个辅助函数、一个 stderr 循环和主 finally 块。如果把整个模块或整个读取器类都视为可修改，就会隐藏无关的协议、身份或语义变化。

这些宿主实现明确发生了变化，不能称为源码未变。每次新的 transition 都必须继续绑定其真实原始源码身份及已提交源码树。原 R22/R24 producer 文件、原 prepared/proof 字节和历史失败均不会被改写，也不会被重新签署为当前证据。

## 决策

前置源码差异成员守卫仅将 common 和 AppServer 两条路径识别为独立、有限的宿主集合，不把它们加入普通可变模块白名单。原有真实 commit/tree/raw/attribute/untracked-production/removal 守卫仍在强制宿主检查之前执行。

纯宿主检查设有两个明确的配置：

1. `historical-runner-only` 保留既有 R25 common `run_isolated_model` 例外及其最小源码夹具。common 的其他全部 AST 仍须绑定一致。AppServer 存在时必须保持不变；仅历史最小纯夹具允许比较两端都缺少 AppServer，这不能绕过真实源码成员检查。
2. `reviewed-loop2` 仅允许下表列出的已审核 AST 位置。守卫记录其精确 SHA-256 AST 摘要，同时检查原位置的摘要。所属定义缺失、混用、未知或重复时一律拒绝。

| 模块 | 精确允许的位置 |
| --- | --- |
| common | 新增 `_stop_owned_pipe_workers` 函数 |
| common | `_WindowsRunnerOutput.__init__`、`_read`、`cancel` 方法体；签名和类的其余部分仍须比较 |
| common | `run_isolated_model` 必须等于已批准的 R25 基线函数，只保留原历史例外，不引入新变化 |
| AppServer | 恰好一条不带别名的 `import sys` |
| AppServer | 新增 `_cleanup_request` 函数 |
| AppServer | `run_request` 中对 common 辅助函数的精确导入替换，不允许别名或额外导入名称 |
| AppServer | 嵌套 `read_stderr` 的精确方法体 |
| AppServer | 主协议的精确 `Try.finalbody`，使用 `sys.exc_info()[1]` 和实际导入的清理函数调用已审核辅助函数 |

`communicate` 方法、底层取消与终止原语、common 纯辅助函数、AppServer 的全部正常协议语句、EOF/drain/wait/replay、model/tool/high 检查、其他嵌套辅助函数、模块全局值及导入均继续参与 AST 比较。允许修改的方法体也不是任意遮罩：只有其完整已审核 AST 摘要匹配后，才能进行投影。

语义辅助函数闭包沿导入关系进入两个宿主模块，并比较实际、未投影的 AST 源码，不新增任何语义截断边界。如果正式语义根依赖发生变化的宿主辅助函数，语义等价检查仍会拒绝该变化。

投影绝不替代 manifest、源码哈希、模型输出或 proof。既有 transition 字段继续保留真实、完整的原始及当前 tracked-source manifests，以及当前 commit。本次变化不修改原 verifier 子进程、重放算法、prompt/schema/output 绑定、high/no-tools 要求、请求与时间预算、unknown 费用占用或额度上限。

## 固定的已审核输入

用于推导精确绑定值的宿主实现单独冻结如下：

- common：`5b30ceb66c2ec9a3d828ade9a6fc9e67449382fc8828a42b9058dd473a92b45b`。
- AppServer：`e59ddf3daab0f0e5f77afa5853a23686ca2029e0a57c8b2dc77d3bd45372e756`。
- C 的静态交接：`1ed0dec02c11c70352dbdf21160ce82b1ed0a5e09855b2f00da084ee5cd71b0c`。

已静态读取原 R5 读取器方法及 AppServer stderr/finally 的 AST 哈希，结果与所检查的原位置摘要一致。这项源码观察不构成新的 native proof，也不构成测试执行。

## 验证与限制

专用可移植测试草案仅加载实际守卫的标准库 AST 定义，再将已批准宿主源码及一个纳入版本管理的基线源码 JSON 夹具作为数据解析。它不导入项目模块、不执行宿主辅助函数、不启动进程，也不调用 Git。覆盖范围包括已审核正例、历史 R25 兼容性、common 与正常协议变异、已绑定 cleanup/import/finally 变异、未知或重复所属定义、前置有限源码成员检查，以及未遮罩的语义导入闭包。既有五个 `SemanticClosureTests` 保持不变。

实现者仅进行了 AST 与哈希检查。Root 负责执行针对性测试及必要的源码与 native 兼容性检查。静态源码认证不能证明 OS 取消成功、清理始终完成，也不能证明存在当前 native/model 资格。仅在失败时产生的宿主诊断仍属于宿主证据，不能当作 provider 输出或协议批准。stdout 累积政策仍是单独延后的风险，本记录不引入新阈值。

工程许可、测试成功、正式 Story 验收、adoption/readiness 和默认 B 启用仍须分别决策。本 ADR 不授予后述权限。
