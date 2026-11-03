# newrouge B 路线工作区与继续入口

## 当前工作位置

- 仓库与后续命令目录：`/workspace/newrouge`。
- 本地分支：`fix/capability-synthesis-input-integrity`，跟踪 `origin/fix/capability-synthesis-input-integrity`。
- 本轮迁移使用的远端起始提交：`cd925bdcae4b61992320773497f7edb729aac244`。本地文档提交在其上继续，不把旧 main 或旧工作分支当作当前工作树。
- BMAD：6.12.4，Core／BMM，29个 Codex 技能，中文交互及文档输出。运行目录为仓库内 `_bmad/`，技能位于 `.agents/skills/bmad-*/`，按既有 `.gitignore` 保持本地安装。

## 本轮产物

| 内容 | 路径（相对此目录） | 状态 |
| --- | --- | --- |
| 原始附件 | [newrouge-b-route-original-requirements.md](sources/newrouge-b-route-original-requirements.md) | 原始字节不变；嵌入示例指令不作为额外执行授权 |
| PRD | [prd.md](prds/prd-newrouge-b-route-2026-11-03/prd.md) | 已定稿，18条FR；目标为路线改变，不以提速验收 |
| 工程及23项验收补充 | [addendum.md](prds/prd-newrouge-b-route-2026-11-03/addendum.md) | 保留原始固定基线资料，当前事实结合下一项读取 |
| 当前分支基线 | [baseline-update.md](prds/prd-newrouge-b-route-2026-11-03/baseline-update.md) | 对齐ADR-0039、checkpoint／worker／恢复及核算能力 |
| SPEC包 | [SPEC.md](../specs/spec-newrouge-b-route/SPEC.md) | 11个CAP身份保留，7份companions；已完成1次架构后回补 |
| 架构主干 | [ARCHITECTURE-SPINE.md](architecture/architecture-newrouge-b-route-2026-11-03/ARCHITECTURE-SPINE.md) | 已定稿，18个AD；输入对账、机械及三项独立审查通过 |
| 共享记录与提交合同 | [planning-records.md](architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md) | 必读架构伴随文档；由架构拥有，SPEC只读采纳 |
| B 路线 Epic／Story 分解 | [epics.md](b-route/epics.md) | 5个Epic、49个Story／256组验收场景全部获批并保存；最终文档校验PASS、0项未关闭检查，用户已以最终C完成工作流，状态final |
| B 路线 Sprint 规划 | [sprint-status.yaml](../implementation-artifacts/b-route/sprint-status.yaml)／[范围与依赖](../implementation-artifacts/b-route/SPRINT-SCOPE.md) | 准备度PASS；5个Epic／49个Story均backlog，5项回顾optional；Taskmaster仍是唯一任务状态权威，5.10保留条件阻塞 |

PRD／SPEC 各目录内保留原有 memlog、来源对账及审查记录。历史记录中的旧绝对路径或提交身份是当时事实；迁移映射及新基线通过追加记录说明，不改写 canonical memlog 历史。

## 已确认的决定与下一步

使用附件创建 PRD，再由 SPEC 消费 PRD，架构消费 SPEC；架构完成后判断并按需进行一次 SPEC 回补。本轮文档链及1次必要架构后SPEC回补均已完成。

已确认 B 顺序、完整Task三联和Chapter3–7、能力／阶段交接优先、奖励领取／跳过／返回的最小真实生产适配试点、五批交付与有界A兼容退出。成本记录用于观测重复与失败，不是提速或成本下降承诺。选择Coaching，真正新的关键决定先讨论，常规实现细节不重复增加审批。

用户已明确确认：版本化文件流水线、分阶段绑定、journal恢复与统一消费者门禁，Knowledge保持派生，不新增规划数据库。架构继承当前ADR-0039及已有worker／checkpoint能力；新增B记录、提交可见性和阶段适配属于后续待实现目标。

后续工作以此仓库目录和本文件明确绑定的产物为入口，不使用迁移前 `/workspace/_bmad-output` 作为另一套活动来源。用户已以C结束Party讨论、批准修订后的Epic5并授权最终校验，随后以最终C确认完成文档工作流；5个Epic、49个Story／256组验收场景全部获批并写入 `b-route/epics.md`。第4步已逐项对账18条FR、11项质量约束、28项架构要求及23个原始AC的具体Story／AC，核对单Agent范围、Epic独立价值、共享文件拆分理由、依赖、格式、批准正文及来源哈希，结果PASS、0项未关闭检查。用户已以最终C确认完成文档工作流，`epics.md` 已置为 `status: final`；未修改真实Task三联、实施代码、执行游戏验收、切默认B、退A或远端发布。

Party讨论已由用户明确结束。四项修订保留：退出门禁5.9与实际退役5.10拆分，未成熟blocked且补偿5.11不依赖实际退出；5.8 AC-3补候选切换前补偿演练；5.2 AC-6补Task无关输入证明；5.7 AC-7补输入／结果／环境证据对照。选择及批准记录见 `logs/ci/2026-11-03/b-route-epics/epic-5-party-discussion.json`；最终校验报告为同目录 `final-validation.md` 与结构化 `final-validation.json`。这是文档分解的就绪结论，不等于实施或Chapter5／运行就绪，5.10未来仍须按真实退出条件执行或保持blocked。

本轮使用 `b-route/epics.md`，保留较早的MVG优化 `epics.md`。共享schema／codec作为预检和后续消费者的共同前置，公共journal／提交服务由正式采纳路径交付，三联／绑定适配继续复用。全部批准快照、Party修订历史、来源哈希和校验证据保存在 `logs/ci/2026-11-03/b-route-epics/`；正式49个Story正文统一从 `b-route/epics.md` 消费。每项有Refs、前置、范围与具体验收／反例。文档中的模型／Windows／CLI／游戏测试均为未来实施义务，本轮未运行；当前无新Git提交或推送。

## 本地安装恢复

在仓库目录执行已有版本的官方安装器可恢复被忽略的本地工具：

```powershell
npx bmad-method@6.12.4 install --directory . --modules bmm --tools codex --user-name Agent --communication-language Chinese --document-output-language Chinese --yes
```

遵守既有Node／Python／uv前置要求；配置和渲染检查属于本地BMAD可用性检查，不代替Windows／Godot的项目运行验收。

迁移前完整备份、14个原产物的字节哈希、旧基线源码资料、历史302项脚本测试及本轮迁移检查保存在 `logs/ci/2026-11-03/bmad-b-route-migration/`。过程证据继续按仓库日志规则管理。

## Sprint Planning 完成与下一入口

用户在Epic／Story定稿后明确授权继续Sprint Planning。本轮只消费最终B路线清单；十份canonical输入哈希与已批准快照一致，复核追溯、前序依赖、架构／UX记录与条件退役，准备度为PASS。生成器识别5个Epic／49个Story，初始全部backlog；5项回顾optional，没有从旧MVG实施文件自动提升状态。两条解析提示来自文档总标题和Epic List目录标题，确认无实际遗漏。

正式入口为 `_bmad-output/implementation-artifacts/b-route/sprint-status.yaml` 和同目录 `SPRINT-SCOPE.md`。此文件是BMAD非权威规划视图，不分配Task ID、不覆盖Taskmaster，不作为Chapter5 readiness或运行PASS。标准状态没有blocked；5.10保持backlog并附真实条件约束，条件未成熟禁止实际退役，5.11不依赖5.10，但不能因此宣布Epic5全部完成。

准备度、生成、校验及刷新预览证据位于 `logs/ci/2026-11-03/b-route-sprint-planning/`。下一项建议在新上下文为Story1.1准备实施输入，显式指定本轮epics／Sprint／范围指南，并先核对真实Task复用／缺口与适用Chapter3–5入口；不将Story编号当真实Task ID。本次尚未启动Build、写Task、实施代码、调用付费模型、执行游戏验收或真实切换／退役，也没有新增Git提交或推送。
