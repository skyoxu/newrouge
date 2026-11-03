# B 路线当前分支基线与原始依据对照

## 当前工作基线

后续工作目录为 `/workspace/newrouge`，本地分支 `fix/capability-synthesis-input-integrity` 跟踪同名 origin 分支，迁移时 HEAD 为 `cd925bdcae4b61992320773497f7edb729aac244`。它完整包含原始需求所用 `a8a363aa5f4ad09d5032731b0e7dfc5a17b8c89b`，并增加33个提交。原始附件及旧提交引用保留为历史来源，不将其改写为新分支当下状态。

当前源码共同根：`https://github.com/skyoxu/newrouge/blob/cd925bdcae4b61992320773497f7edb729aac244/`。主要约束继续由 `AGENTS.md`、实际有效 ADR、Base／Overlay 及 owning workflow 文件承担。分支变更不改变 B 路线、奖励最小试点、存量保护和“路线改变而非提速”的产品决定。

## 已有能力与剩余路线缺口

| 领域 | 新基线已存在的代码与合同 | B 路线仍须完成的工作 |
| --- | --- | --- |
| Capability 输入 | `_capability_input_integrity.py`、`_capability_task_evidence.py` 及 Skill：完整任务／来源对象校验、关联输入投影、分阶段 synthesis、实际返回大小再预检、模型真实身份与 receipt、显式完整证据恢复 | 将适用的完整来源及独立审计前移到 Task 之前；不能让后置 Task／readiness 输入继续成为正式前置规划必要条件 |
| MVG 逐项生命周期 | `_mvg_capability_selection.py`、`_mvg_capability_checkpoint.py`：每 Capability 三个合格增量后评选，已接受累计 seed 只读；`run.json` 原子提交 selected 前缀与 checkpoint 指针 | 新增 Task 无关采纳阶段与后置绑定阶段，保同一 Flow 身份；复用而非另建第二套 selected／完成状态机 |
| worker 和预算 | `_mvg_capability_worker.py`：独立 OS 进程／工作区，协调器预留预算、独立机器复验及唯一提交；worker 不推进 selected | 前移规划时保留隔离、admission 和预算保护，不用 Agent 自报通过替代 |
| 恢复与失效 | `_mvg_capability_recovery.py`、Accepted `ADR-0039-mvg-completed-capability-recovery.md`：只恢复已原子提交完成项，原 proof 与新 adoption 分离，当前依赖／delta 重验，epoch clear 及 reopen 后继撤销 | 将新采纳记录／Task 生成／绑定应用纳入适用幂等及一致可见性，不把未完成模型状态当可移植成果 |
| Requirement 核算 | `_mvg_requirement_routes.py`、`_mvg_requirement_accounting.py`、Skill：route membership、唯一验证处置和去重共享证据分离 | 沿用现有键和权威规则，承接 Task 无关语义／合法非 Flow 去向，不另造重复覆盖或完成计数 |
| 规划收口与页面 | 全局机器 audit、显式 reopen、提交前缀进度、清理代际和规划完成检查已有实现 | 将3A／3B／3C及后续消费者接上 B 顺序，保 planning complete 与 runtime acceptance 分离 |

当前 `plan-capabilities` Skill 仍定义为相关 Chapter3–5 范围就绪之后执行，`plan-mvg` prepare 仍核对实际 Task sinks 和 Chapter5 证据。新分支强化了原有路线的实现；“无 Task／readiness 正式规划”仍是本次改造的目标，不能因新模块存在宣称 B 已完成。

## 必须继承的语义澄清

### 单一权威处置与多路线成员关系

“Requirement 单一覆盖归属”指唯一权威验证处置／owner，不禁止同一 Requirement 在多条 Flow 中表达可观察角色。沿用现有 `requirement_route_memberships` 的 `(requirement_id, flow_id)`、`requirement_verification` 的 `requirement_id` 及 `requirement_evidence` 的 `(requirement_id, evidence_id)`。共享证据可支撑多个明确覆盖的路线，但不重复计完成；`coverage_table` 是兼容投影，不成为第二权威。

`accounted` 与 `satisfied` 分开：实现引用证明存在，不等于运行验收；满足要求需对应的权威验证记录、覆盖行为及所有适用路线，planned 或模型自报不构成证据。来源缺口可以已记账但仍阻断规划完成。受治理的非 Flow 验证去向继续合法，不因多路线关系强造 Flow。

### 完成项复用与模型中间态

MVG 新执行仅恢复已由 `run.json` 提交的完成项，prepared bundle、候选草稿、修复／检查／评选中间态不单独授予跨新执行恢复资格；费用、proof 与失败历史保留。单项 Capability 的规范化内容哈希是匹配键，Git／catalog 元信息不是该键；命中后仍须验证历史 proof、当前相关依赖及累计 delta，不能以内容命中绕过有效性。

这与“完整相关输入不变才复用有效证据”不矛盾：匹配键、当前复用资格和运行证据有效性属于不同检查。显式 Capability `--resume-evidence` 按其完整准备输入与历史 batch 身份复验，不能被泛化成 MVG 新执行的中间态恢复许可。多产物正式应用的 journal 恢复同样与模型中间态恢复不同。

### 来源完整性与作用域投影

新分支已有定向证据闭包、关联 Task／readiness 投影及全局机器完整性证明，历史 proof 的版本／hash 语义保持。应复用当前共享解析与校验路径，不复制第二条搜索或任意摘录管线。

Chapter3A 的独立来源遗漏审计仍以完整声明来源和 Ledger 定界，不能被第一轮 Requirement／Flow 投影反向裁剪。后续模型调用可按受治理边界投影相关输入，但须保留适用原文、全局记账和可重建证明；投影不使未知或损坏输入自动获得“不相关”豁免。

## 本轮迁移的状态边界

PRD 的18条 FR、原始23个 AC及 SPEC 的11个 CAP 身份不变；当前更新是基线事实和既有接口对齐。此前针对旧基线的审查及 BMAD 安装测试作为历史证据保存，新目录下另做配置、技能渲染、文件哈希与相对链接检查，不把历史302项脚本测试改称本分支全套运行验收。

迁移时只搬入架构准备 memlog，当时尚未生成主干，切换分支未被当作架构选择。随后用户明确确认文件流水线／分阶段绑定／journal／消费者门禁、Knowledge派生及不新增数据库；架构与一次SPEC回补的最终状态以 `../../newrouge-b-route-workspace.md` 的实际工作入口为准。
