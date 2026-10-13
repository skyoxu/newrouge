# Addendum: MVG Capability 增量规划与准入优化

本文件保留实现机制、仓库映射和取舍，不替代 [prd.md](prd.md) 的用户可观察需求。下列具体机制是待架构/实现阶段验证的建议，不代表已批准变更。

## 当前实现与目标差异

| 主题 | 当前仓库现实 | PRD 目标 |
|---|---|---|
| 规划顺序 | 每个独立 candidate 按完整 Capability 列表依次 append；全部处理完才整体选择 | 当前 Capability 的三个增量候选先准入和选择，再合并并推进下一项 |
| Requirement 覆盖 | `coverage_table` 对 Requirement 作独占 coverage accounting | 多条不同操作路线可引用同一 Requirement；路线引用与权威验证记账分离 |
| 生成与准入 | 生成后执行 proposal machine checks；部分 selector、handoff、source/contract 关系问题会在生成后才出现 | 尽可能在调用 schema、确定性 skeleton 和预生成域中前置；剩余跨字段约束生成后立即 machine-check，且不得进入语义审查 |
| 证据传输 | 已支持完整辅助证据分片、哈希、receipt 和合成去重；最近第三 Capability 21 批证据检查通过，生成后仍有结构错误 | 保留完整证据保障，同时改进格式/结构硬约束在模型生成前的约束能力 |
| 失败恢复 | 主工作流具有局部修复状态机；单 Capability 诊断脚本特意在首个问题处停止 | 正常路径实施每问题三次修复、之后干净 lineage 重启；诊断 fixture 不得被误解为生产准入流程 |
| 最终结果 | 候选在全部 Capability 后统一选择，最终 `review/validate/apply` 检查累计结果 | 每 Capability 选择并原子累计合并，所有 Capability 完成后做跨 Capability 全局审计 |

## 建议的工作流状态

```text
prepare 当前 Capability + 当前 accepted baseline
  -> 建立三个隔离 candidate lineage
  -> 前置 schema/path/domain preflight
  -> generate increment
  -> deterministic structural gate
       -> 失败：按稳定问题局部修复，每问题最多 3 次
       -> 同一问题耗尽：从 immutable inputs 创建干净 lineage
       -> 输入/runner 失败：停止并分类，不作为语义 finding
  -> independent semantic hard gate
       -> 失败：相同局部修复和 machine recheck 路径
  -> admitted candidates 达到选择条件
  -> comparative selection
  -> bind selection + base hash；原子 delta merge
  -> 固定当前 Capability 的结果并进入下一 Capability
  -> 全部完成后做跨 Capability 全局 consistency audit
```

实施时必须检查当前生产约束：现行 `run_capability_append` 的 64 次调用预算是每个 candidate lineage 共享；拆成每 Capability 三候选后，首版不得默默把每 Capability 的预算乘以 Capability 数量。当前 PRD 决定保留 lineage 上限，并要求实现提供显式 run-level 总上限和超限终态；具体数值沿用仓库配置或在实现设计中确认。

## Requirement 数据模型建议

不要把“Requirement 在某路线中出现”存成一个全局互斥 coverage owner。建议概念上分成：

- `requirement_route_memberships`: Requirement 到多个 flow 的关联，描述每条路线中相关的结果/边界。
- `requirement_verification`: 每个 Requirement 的验证 disposition、权威验证证据或合法 deferred/source-gap 状态。
- route-specific verification refs: 在路线行为不同且有必要时绑定对应测试；允许多个 flow 共享证据，但必须显式说明该证据验证的行为范围。

最小唯一性规则：`requirement_route_memberships` 以 `(requirement_id, flow_id)` 去重；`requirement_verification` 以 `requirement_id` 保持单一权威 disposition；证据引用以 `(requirement_id, evidence_id)` 去重。共享证据不增加完成计数，且必须记录覆盖行为范围。

落地 schema 前先盘点 `docs/testing/mvg/*.json`、planning proposal、coverage builder/validator、delta replay、Knowledge 汇总和现存 fixture。迁移须可逆或保留原始快照；不能把多条 route membership 合并/丢弃，也不能把重复引用误算为多次 Requirement 完成。

## 生成前约束与机器 gate 的取舍

机器前置不是把所有语义判断写进 JSON Schema。按可靠性分层：

1. **CLI schema 可强制项**：输出对象形状、必填字段、类型、枚举、已知 ID enum、selector 类名 enum、当前 flow/test 路由域、明确禁止空数组等。
2. **Prepared-input 静态校验**：已有路径、Contract 名称、Task/Requirement/Capability membership、类名抽取、旧 baseline ID、owner 状态、source hash。
3. **生成后 deterministic gate**：唯一性、跨字段依赖、test-flow 双向绑定、handoff 索引、Coverage 路线引用、无未知字段和累计 delta replay。此 gate 失败时不能调用 semantic reviewer。
4. **独立语义准入**：只回答来源含义、路线连贯性、真实 producer/consumer、failure/recovery 和测试是否覆盖意图；不得替格式错误补救，也不得覆盖 source-backed hard conflict。
5. **最终全局审计**：只处理跨 Capability 才能判断的一致性，不将既有局部选择默认视为无效；发现真实硬冲突后生成显式、可审阅的重开计划。

生成 schema 可用 enum/受限 pattern 提前约束真实 selector 与已知路径，但外部 Codex CLI schema 子集兼容性需以实际 runner contract 测试。若 CLI 不支持约束，调用前应生成结构化的 allowed domain/skeleton 并做本地 preflight，不能仅退回 prompt。

## 候选数、预算和 incumbent

- “三个候选”是用户当前认可的比较基数，应以每个 Capability 的完整准入候选数解释，不是三个任意 proposal。
- 现行 64 invocation stop-loss 是候选 lineage 预算。需确认逐 Capability 拆分后，是每条候选 lineage 仍 64 次，还是增加一个 run-level 总预算；在做费用估算前不应默认扩大累计最大费用。
- 首版不把全范围 incumbent 作为第四个候选；当前 accepted baseline 只作为只读增量底座。若未来比较 incumbent，必须先抽取同 Capability scope 的 delta 并通过相同 admission gate。
- 选择器应比较增量的 Requirement/Capability fidelity、flow cohesion、用户可理解性、handoff continuity、证据可验证性和对累计基线的影响；候选不能因排序字段顺序或 JSON 数组顺序而失败。

## 仓库落点与集成边界

可能影响的实现和测试边界（具体改动需先经架构/实现拆分）：

- 生产入口：`scripts/python/plan_mvg.py`
- Capability append 生成/Schema/局部修复：`scripts/python/_mvg_capability_generation.py`、`scripts/python/_mvg_capability_append.py`
- Requirement coverage / semantic review：`scripts/python/_mvg_planning_review.py` 及其校验调用方
- 权威行为说明：`.agents/skills/plan-mvg/SKILL.md`、`workflow.md` §5.4、`docs/workflows/mvg-integration-acceptance.md`
- 回归测试：`scripts/python/tests/test_mvg_capability_append.py`、`test_mvg_planning_contract.py`、`test_mvg_evidence_transport.py` 以及 Knowledge/MVG summary 的契约测试
- 正式运行证据：遵从 `docs/workflows/mvg-integration-acceptance.md` 及 `docs/testing/mvg/` manifest；规划通过不代表 runtime acceptance 通过。

不得只改 prompt、测试 fixture 或 UI 文案。必须有回归证明：格式错误不会进入 semantic call；重复 Requirement route membership 被接受而重复验证不会虚增；当前增量不能静默削弱已确认 baseline；delta 失败不会部分写入；恢复不会混用 lineage；最后全局审计可以定位真实跨 Capability 矛盾。

## 明确排除的方案

- 用 prompt 文字代替 CLI schema 和机器 gate。
- 以模型摘要替代未完整传输的来源文件。
- 允许不合格候选进入比较，期待 selector 替它做审查。
- 仅通过放宽 validator 处理失败，而不区分合法多路线引用与虚假重复完成。
- 每个 Capability 写独立完整 manifest，然后末尾做字符串式拼接。
- 失败时继续复用失败上下文，或自动提高 64 次 lineage 上限。
- 自动重写早期 Capability 选择而不产生冲突证据和审计记录。
