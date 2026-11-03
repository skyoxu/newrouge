# 当前分支基线更新：输入一致性复核

- 日期：2026-11-03。
- 工作基线：`fix/capability-synthesis-input-integrity`，`cd925bdcae4b61992320773497f7edb729aac244`。
- 范围：仅复核本次已授权分支／目录迁移涉及的输入合同、基线事实、稳定身份与术语；不重审全部分支代码，不运行工作流或运行时测试。
- 结论：**通过；未发现需要阻断此次文档迁移的实际问题。原始需求与用户已确认的产品方向得到保留，新增基线语义有明确分层，未将历史依据冒充当前代码或运行证据。**

## 核对材料

1. 原始输入副本 `../../sources/newrouge-b-route-original-requirements.md`，以及此前完整输入对账结论。
2. 当前 `prd.md`、`addendum.md` 和 `baseline-update.md`。
3. `../../../specs/spec-newrouge-b-route/SPEC.md` 及三个自写伴随文档：`workflow-contract.md`、`verification-contract.md`、`migration-and-pilot.md`。
4. 当前基线的专项只读证据：`../../../../logs/ci/2026-11-03/bmad-b-route-migration/new-baseline-evidence.md`。
5. 当前 `AGENTS.md` 的权威、平台、任务状态、证据和累积验收约束。

## 窄范围结果

| 检查项 | 结果与依据 |
| --- | --- |
| 原始输入未被静默改写 | 搬迁副本与上传附件逐字节相同；SHA-256 为 `61127cd155c243ce3102fd1004e1d147b6beeb65183a1b8d24a560f09f1fbeb2`。历史需求依据仍是 `a8a363aa…`，没有将其正文改成新分支事实 |
| 稳定需求／能力身份 | 当前 PRD 仍逐项承接 BR-01–18；addendum 的 AC-BR-01–23 全部保留；SPEC 的 CAP-1–11 连续且无重编号。`workflow-contract.md` 末尾保留 CAP→FR 对应关系，本次没有合并／拆出新的范围 |
| 当前与历史基线分开 | PRD“当前核对基线”、SPEC Constraints、migration第一批及 baseline-update 均以完整 `cd925bdcae4b61992320773497f7edb729aac244` 为工作源码身份；`a8a363aa…` 与 `8f93557…` 被明确标为原需求／迁移前历史，未将旧本地 HEAD 继续称为当前 |
| 历史 addendum 仍可解释 | addendum 顶部明确旧源码共同根是历史，当前分支事实由 baseline-update 更新；SPEC 将两者都列为必读 companions，因此历史接口接入表不会单独被误作当前能力全表 |
| 路线而非提速 | PRD目标、FR-16、SM-4、SPEC Why／Non-goals、验证合同AC-BR-20段均保留“路线改变，不以提速或成本下降判成功”；仍保留耗时／调用／复用／返工观测与预算停损，无新增速度或成本下降门槛 |
| 奖励最小真实试点 | `combat-reward-return`、生产命令／只读状态／必要C#适配、独立Reward路由、原生人工区域、既有Task／Flow身份均保留。新增变更范围无Task/readiness的B规划与旧任务增量路径继续分开证明，未借迁移变更玩法或扩大为全游戏重构 |
| 唯一验证权威与多Flow参与 | PRD FR-4、SPEC Constraints、workflow术语、baseline-update 明确：Requirement唯一verification／owner，不禁止多条 `(requirement_id, flow_id)` 路线参与；证据按 `(requirement_id, evidence_id)` 去重；coverage_table仅兼容投影。未把“唯一归属”误写成单Flow参与限制 |
| accounted与satisfied不混 | baseline-update 保留“记账不等于满足”，实现引用非运行通过、source_gap仍阻断、适用路线全部覆盖才满足。合法非Flow去向仍受治理，不强造Flow以满足核算 |
| MVG完成项恢复边界 | PRD FR-13／16、SPEC CAP-10和Constraints、workflow门禁段、verification稳定性段及baseline-update 均继承ADR-0039：仅已提交完成项可跨新执行adoption，先验原proof再验当前依赖／delta；匹配键、复用资格、运行证据身份分开，未完成模型中间态保审计而不移植 |
| Capability显式恢复没有被混同 | baseline-update 与两个合同均单列 Capability `--resume-evidence` 的完整准备输入／历史batch／receipt验证；没有把它泛化为MVG新执行可续跑半成品的许可。正式多产物apply journal恢复也明确是另一协议 |
| 既有能力与B剩余缺口 | baseline-update 承认当前worker、原子checkpoint、逐Capability三候选、恢复、Requirement accounting及planning completion已有；仍明确Task/readiness正式前置依赖未解除。未把已有能力重复列为全新建设，也未据此宣称无Task B路线已交付 |
| planning与runtime保持分离 | 当前completion report及committed-prefix进度被作为继承能力；planning complete不改变runtime not_verified。旧302项BMAD安装脚本测试只作历史，不改称当前分支业务验收 |

## 对原始要求的相容性判断

本次“单一验证权威／多路线参与”澄清仍满足原始 BR-04／06 的共享定义、单一责任与多对多边界，不新增重复完成计数或第二任务状态权威。“完成项复用／Capability显式恢复／apply journal”分层仍满足 BR-13／16 的有效复用与恢复，未削弱输入身份、后编辑保护和累计同一整合快照要求。

原始23个改造验收场景、owner不形成自身done前置的反例、合法非Flow门禁、既有／本次／未来三类义务、防削弱、来源完整性和人工验证边界仍由当前PRD及SPEC采纳的伴随文档承接。此次复核不把这些未来实施义务标成已通过。

## 验证限度

本报告进行文档读取、稳定ID枚举和原始附件副本字节一致性核对；以专项 `new-baseline-evidence.md` 为当前相关模块的只读核对依据，没有逐行复核全部154个变更文件，也没有运行Chapter、模型候选、工作流、Godot或Windows业务试点。通过结论仅说明此次文档基线迁移未发现输入合同冲突，不证明B路线实现或运行验收完成。架构方案仍待Coaching选择，分支迁移不视为已选择文件流水线或规划数据库。
