---
id: SPEC-newrouge-b-route
status: final
created: 2026-11-03
updated: 2026-11-03
companions:
  - workflow-contract.md
  - verification-contract.md
  - migration-and-pilot.md
  - ../../planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/addendum.md
  - ../../planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/baseline-update.md
sources:
  - ../../planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/prd.md
---

# newrouge B 路线实施合同

## Why

将新增需求由先定 Task 改为先明确 Requirement、Capability／MVG Flow 与交接，再据真实缺口生成或复用完整 Task 三联，使 Agent 按持久且有效的定义实施。保留 Chapter3–7、存量身份及累计验证。成功在于路线、约束与完成责任成立，不以提速或成本下降判定。

## Capabilities

- **CAP-1**
  - **intent:** 规划者在拆任务前获得完整来源、Requirement、验收意图与独立来源审计。
  - **success:** 每个声明来源块有投影或明确去向；未被首轮 Task／Flow 引用的交接遗漏仍能被发现。
- **CAP-2**
  - **intent:** 无 Task／readiness 时正式规划、审阅和采纳 Flow 或合法非 Flow 验证去向。
  - **success:** 起终点、必要分支、状态所有者及四部分职责可核对；合法循环和有理由的不适用不误拒，不造假对象过检。
- **CAP-3**
  - **intent:** 以持久、可追溯的采纳决定连续细化同一 Flow。
  - **success:** 来源与内容身份明确，前后阶段 Flow 身份不变；同输入恢复复用有效计划，显式重规划产生差异与身份对齐。
- **CAP-4**
  - **intent:** 根据复用盘点与真实实施缺口生成受治理任务三联。
  - **success:** Task 回链需求、Acceptance、责任、依赖和义务；多对多关系成立，成熟 ID／状态／历史不被候选默认值覆盖。
- **CAP-5**
  - **intent:** 各实施及恢复入口只消费当前有效的阶段定义、readiness 和适用义务。
  - **success:** 缺失、损坏、未知或过期 B 依据统一阻断；有合法其他验证依据且无 MVG 义务的非 Flow Task 可实施；纯实现修复复用规划但不跳就绪检查。
- **CAP-6**
  - **intent:** 由单 Task 局部自检、目标 UI 收口及 Flow 集成各自承接验证责任。
  - **success:** Chapter7 复用已验证 UI，无重复同义任务；局部、静态、场景方法、真实输入及人工证据不混用，全部必需义务满足才完成 Flow。
- **CAP-7**
  - **intent:** 对共享变更登记传递影响并执行真实适用回归。
  - **success:** 既有回归、本次新增、范围外未来义务分别处置；失败不能重分类，执行范围与实际覆盖相符，单 Flow／partial 不冒充累计 full-MVG。
- **CAP-8**
  - **intent:** 在重试、中断和无关变化下保留有效结果并安全恢复。
  - **success:** 同操作同内容无重复副作用；后编辑、同身份异内容或损坏记录产生冲突；完整相关输入及验证身份匹配才复用证据，累计通过不拼接不同整合快照。
- **CAP-9**
  - **intent:** 有界迁移旧路线，并使生产者、真实消费者和操作面使用一致依据。
  - **success:** 五批交付与 A 退出条件成立；新旧格式和合法缺失／损坏／未知可区分；Knowledge 的计划、实现、运行及分支身份不混淆，不推进未授权发布指针。
- **CAP-10**
  - **intent:** 保留有界但完整的证据、独立候选审查、预算止损和过程观测。
  - **success:** 大输入不静默截断，已完成并持久化且仍有效的成果按其工作流规则复用，MVG 新执行不恢复未完成模型中间态；耗时、调用、复用及返工可追溯，且不设置提速门槛。
- **CAP-11**
  - **intent:** 以奖励真实变更证明零 Task 新规划及存量增量两条路径。
  - **success:** 同一 `combat-reward-return` 身份下，生产命令／只读状态及必要 C# 适配改动走通 Chapter4–7 和适用 MVG，保留候选锁定、路由、旧 Task 与累计测试，并具有 Windows／Godot／C# 原始证据。

## Constraints

- 下游必须读取所有 companions；阶段、四部分、门禁见 `workflow-contract.md`，验证与复用见 `verification-contract.md`，迁移及试点见 `migration-and-pilot.md`，固定技术／ADR／消费者及23个原始验收场景见采纳的 PRD addendum，当前工作分支及 ADR-0039 对齐见 baseline-update。
- 沿用 Windows-only、Godot4.5.1、C#／net8.0 和当前有效 ADR。Core／Contracts 保持 BCL-only，原生场景可编辑；适配不复制领域裁决。
- 原始来源管语义，采纳决定从属于来源，Taskmaster 三联保留唯一任务状态权威，契约源码管程序契约，manifest 管累计验证义务，原始运行报告证明执行，Knowledge 仅派生定位。
- Requirement 保留唯一权威验证处置／覆盖 owner；允许多 Flow 路线成员关系及去重共享证据，不重复计完成。Flow 可跨 Capability、Task 与 Flow 可多对多；四部分不强制机械拆任务。集成 owner 不增加自身完成前置。
- 前置采纳不依赖 Task／readiness，进入实施不先要求待实施任务完成；planned 不冒充已实现。真实对象出现后补编译／绑定／引擎检查，结构不替代语义或运行。
- 相关输入变化精确失效，无关变化复用；B 丢标识不能转 legacy；未知／损坏不能当合法缺失。所有真实入口执行相同规则。
- 继承已有 P1 必修底线、独立语义 admission、累计防削弱与日志规则；UTF-8，中文沟通，代码／脚本／测试遵守英文约定。Chapter6 不隐式全局 Knowledge refresh。
- 当前分支为 `fix/capability-synthesis-input-integrity`，起始提交 `cd925bdcae4b61992320773497f7edb729aac244`；原始 `a8a363aa…` 及旧本地 `8f93557…` 是历史来源。继承 ADR-0039 完成项恢复；单项匹配键、当前依赖／delta 兼容性和运行证据身份分开核对。

## Non-goals

- 不重建／重编号全部历史任务，不新增第二套 Task 状态或 MVG 生命周期，不以旧 done 证明新义务。
- 不建设通用游戏 DSL、解释器、全量代码／场景生成；不做全仓 GDScript→C#、玩法重设计、数值平衡、美术或全场景重制。
- 不引入 ji-mu-yun 平台、轻量 Task 替换、沙箱、认证、多租户或其他控制面；不增加 Unity、移动、Web、多人或引擎升级。
- 不降低质量门槛、删除有效回归、更改分支保护；不承诺两小时交付、固定 Task 数／时长、提速或成本下降。
- 当前文档链不创建实施任务、不执行开发／运行验收或发布；不生成 Story Breakdown。

## Success signal

所选奖励真实变更先在目标变更范围无实施 Task／readiness 时完成正式规划，再形成稳定任务并按有效定义完成相应验证；同时旧 Flow／Task 及累计义务保留，关键缺失、漂移、重复应用和后编辑反例符合预期。全部原始 AC-BR-01–23 按当前适用范围有证据，过程记录可追溯；单 Flow 与累计完成口径分明。
