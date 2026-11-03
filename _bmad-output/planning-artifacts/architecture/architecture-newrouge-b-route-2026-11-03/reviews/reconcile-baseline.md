# 当前工程基线与 B 路线架构对账

## 结论

目标架构与当前已部署规划治理一致，未发现对 ADR-0039、Requirement 核算权威或 Task/readiness 分阶段目标的直接冲突。唯一 BASE-1 消费者接入说明缺口已修复并通过定点复核；当前无未解决发现。

本轮比较的是目标设计与已存在的源码约束，不将新增记录、共享服务或 B 正式模式判作已实现，也不把当前正式 planner 拒绝零 Task 视为目标架构错误。

## 输入与核查范围

- 当前 HEAD：`e9cd3d9cb4f054f04348013c1cba926675fcca49`；工程行为基线：`cd925bdcae4b61992320773497f7edb729aac244`。
- 两提交在 `scripts/`、`docs/adr/`、`AGENTS.md`、`workflow.md` 下没有变更；本轮这些源码行号仍对应既有工程行为。
- 完整读取本次 `ARCHITECTURE-SPINE.md` 与 `planning-records.md`。
- 对照 `logs/ci/2026-11-03/bmad-b-route-migration/new-baseline-evidence.md`，复核相关实际源码：`_mvg_obligations.py`、`chapter5_semantic_reconciliation.py`、`plan_capabilities.py`、`plan_mvg.py`、`_mvg_capability_selection.py` 及 Accepted ADR-0039；已有证据中的 checkpoint、recovery、accounting 和 completion 函数作为受约束参照。
- 2026-10-12 的较窄 MVG 主干不是本 initiative 的父主干，其 TARGET 标记不证明当前实现；本次主干已正确说明。
- 未运行工作流、模型规划、测试、Godot 或运行验收；未修改其他文件或 memlog。

## 已解决的接入点

### BASE-1 现有 Capability pending 必须进入新共享门禁

- **级别：** P2，工程接入说明缺口；不是已经证实的目标不变量冲突。
- **状态：** Resolved，2026-11-03 定点复核通过；本次仅复查该项，没有扩大检查范围。
- **架构位置：** `planning-records.md`“共享 apply 与恢复协议”及“诊断与实施接入”；主干 AD-6、AD-8。
- **现有事实：** `chapter5_semantic_reconciliation.py:1574–1576` 的 `load_task_readiness` 只要发现 `docs/planning/semantic-topology/capability-apply.pending.json` 就返回 `capability_apply_pending_recovery`，不允许继续使用旧 readiness。`plan_capabilities.py:2205–2219` 用该 marker 标记现有 journal 的未完成恢复，并只在恢复完成、run／summary 写回后删除。
- **原缺口：** 新合同原先明确了相关 scope pending 与 catalog／receipt 验证，却没有命名此现存全局 marker 的兼容责任；下游若只查新的 B pending／catalog，可能遗漏现存执行阻断条件。
- **修复与复核证据：** 当前 `planning-records.md:53` 已显式要求共享 gate 同时识别 `docs/planning/semantic-topology/capability-apply.pending.json` 及其原 journal，按原 apply 恢复，不只查新 B pending；无法证明旧 marker 作用域时保守阻断适用规划／实施，catalog 有效也不豁免，不得删除 marker 获取通过。该文字覆盖原发现的全部接入要求，BASE-1 关闭。
- **可核对结果：** 在旧 Capability journal 未完成而新 B catalog 仍可读时，所有已接入的直接／恢复／页面实施入口给出一致 pending 原因；journal 验证并完成后才恢复资格。此处是未来实施的应验行为，本轮没有执行。

## 已正确保留的基线约束

| 基线约束 | 本次架构落点 | 判断 |
| --- | --- | --- |
| 正式 Capability/MVG 当前仍依赖 Task 和 Chapter5 readiness | AD-2明确3A/3B/3C与4–5分阶段，通过显式适配演进；records24允许3B无Task映射 | 正确。未用draft开关／假witness把旧gate伪装为新正式路径 |
| ADR0039独立OS worker、parent预算预留／复验／唯一selected提交点 | AD-9继承ADR0039；records3、50区分owning checkpoint与新catalog发布点 | 正确。新共享apply不接管worker selected权 |
| 三候选准入后排名，accepted seed只读；稳定槽位64／run默认192且重启不重置 | AD-9、15明确继承ADR0039及稳定预算；`_mvg_capability_selection.py:455–473`仍为当前reference | 正确。无需在initiative主干复制每个数值，但实施不能按每scope或worker另增预算 |
| 完整单项内容匹配、历史冻结proof、当前dependency／delta复核、独立adoption receipt | AD-9；AD-10将相关输入与整catalog/HEAD分开 | 正确。相同内容不被宣称是充分复用条件 |
| 新MVG执行不恢复未完成candidate/repair/inspection/selection模型状态 | AD-9明确；Capability显式证据恢复和正式apply journal单独遵守原合同 | 正确。没有把Capability的`--resume-evidence`推广为MVG半完成模型恢复 |
| epoch clear、reopen撤销相关完成项及后继，保留历史与formal baseline | AD-9继承其完整语义，AD-16只读展示committed prefix，records77列epoch/reopen反例 | 正确。新catalog不授予旧epoch重新发布资格 |
| route membership键为`(requirement_id,flow_id)`，unique verification按Requirement ID，evidence按二元键 | AD-4；records42继承现有三组键及coverage兼容投影 | 正确。多Flow参与不产生多份验证权威或重复完成计数 |
| planning complete与runtime acceptance分开 | AD-1、10、16及Consistency Conventions；records67沿正式receipt/inventory/snapshot验证 | 正确。新B commit receipt或catalog不成为full-MVG运行证明 |
| `_mvg_obligations.py:26–74` 无matching trace时返回current的既有legacy路径 | AD-5；records38–40、75先验证policy/catalog/origins及双向集合，再允许合法legacy使用旧返回路径 | 正确。B丢trace/origin/manifest不能先返回current再补检查 |
| 当前后编辑冲突与apply journal恢复，不以逐文件replace伪称整体事务 | AD-7、8；records46–59定义前后像、receipt、catalog唯一可见点及补偿rollback | 正确。state合并没有用宽泛mutable排除吞掉Acceptance/新进度 |
| 用户已选文件流水线、分阶段绑定、journal、sharedgate、derivedKnowledge、无新DB | Design Paradigm、AD-3/6/8/16/17及records公共合同 | 正确，属于已批准目标设计，不是关于当前实现的事实断言 |

## 验证限度

这是一轮有界基线输入对账，没有把 current source 的所有文件逐行审计，也没有证明新协议在 Windows 文件占用、崩溃、跨scope共享Task及不合作外部编辑下已经安全。主干与伴随合同把这些列为启用默认 B 前的故障注入及消费者验证义务，表达正确。
