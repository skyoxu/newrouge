# ADR-0032: Save/Resume Policy and Deterministic Outcomes

- Status: Proposed
- Context:
  - NewRouge 是单人卡牌构筑的 run-based 游戏，设计目标包含“决策重量”与“玩家信任”。
  - 玩家必须允许中断与继续（手动退出、崩溃、断电），但不允许通过退出重进来“刷随机结果”。
  - 游戏必须可复现以支持 QA 与公平性：同一存档点 + 同一输入序列产生同一结果。
  - 本决策会影响：存档结构（schema）、RNG 设计、事件/奖励生成、主菜单入口、迁移策略与取证日志。
- Decision:
  1) 单槽自动存档（Single autosave slot）
     - 游戏仅维护一个系统自动保存记录。
     - 主菜单提供唯一入口 Continue Game，用于读取该自动存档。
     - 新开一局允许覆盖旧自动存档，但必须二次确认，且覆盖不可撤销。
  2) 战斗保存边界（Combat save boundary）
     - 进入战斗时保存“战斗初始状态”。
     - 战斗过程中绝不保存任何中间态（不设置战斗检查点）。
     - 任意战斗中断（手动退出、崩溃、断电）后继续游戏，都只能回到战斗初始状态。
  3) 确定性契约与“结果不变”的严格定义（Determinism contract）
     - “退出重进不会导致事件及结果不同”被严格定义为：
       - 不重抽不重滚：退出重进不得触发任何重抽或重滚。
       - 确定性：同一 seed + 同一输入序列 = 同一结果。
       - 玩家操作不同可以导致不同结果（不锁死为同一个结局）。
     - 对事件奖励等“三选一”场景，退出重进后的候选项集合必须保持不变：
       - 允许重新选择，但候选项集合固定不变。
  4) 版本升级与迁移门禁（Upgrade and migration gate）
     - 继续游戏要求存档迁移成功（迁移必须幂等）。
     - 若迁移失败，必须阻止 Continue Game 并提示错误，避免损坏扩大。
     - 迁移取证必须写入 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。
- Consequences:
  - Pros:
    - 玩家信任更高：允许中断与继续，不需要惩罚性“禁止退出”。
    - 公平性更强：退出重进无法用于刷奖励候选项。
    - 可复现性更强：QA 可基于相同 seed 与输入序列复现问题。
  - Cons / Risks:
    - 进度损失是预期行为：战斗中断后回到战斗初始状态。
    - 单槽覆盖存在误操作风险：需要明确 UI 提示与二次确认。
    - 确定性提高实现复杂度：需要严格定义存档点、输入序列与 RNG 流拆分。
  - Acceptance Criteria（成为 Accepted 的门槛）:
    1) 存档边界实现到位：
       - 节点前存档 + 进入战斗保存“战斗初始状态”。
       - 战斗中绝不保存中间态。
       - 战斗中断继续只能回到战斗初始状态。
    2) “三选一”锁定到位（候选集固定）：
       - 首次生成即落盘 `stable_ids[] + display_order[] + provenance`。
       - 退出重进后候选集与顺序完全一致（含顺序）。
       - 允许重新选择，但不得重抽/重滚。
    3) 确定性边界到位（Scope）：
       - 纯 UI 行为不得推进 RNG、不得改变候选集。
       - 同一存档点 + 同一输入序列可复现。
       - RNG streams 拆分（run/combat/event/loot）并在存档边界持久化必要状态。
    4) 原子写与坏档处置到位：
       - autosave 写入原子化；失败保留上一份 autosave。
       - Continue 读档完整性校验；损坏/不兼容必须阻断 Continue 并提示。
    5) 迁移门禁到位：
       - 迁移幂等；失败不得写回；失败必须阻断 Continue 并提示。
       - 迁移取证写入 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。
    6) 审计取证到位：
       - 关键动作写入 `user://logs/security/security-audit.jsonl`（JSONL，一行一个 JSON）。
       - 字段至少包含 `{ts, area, action, reason, target, caller}`，用于复现与客服排障闭环。
    7) 自动化验证到位（最小集）：
       - 至少 1 个 xUnit 用例覆盖“候选集锁定不漂移”的核心逻辑（Core 层）。
       - 至少 1 个 headless 冒烟覆盖“Continue 被阻断（坏档/迁移失败）”路径（Godot 层/Runner 任选）。
       - 测试文件必须采用稳定命名并可被 PRD 的 `Test-Refs` 引用（允许后续按需追加更多用例，但不得重命名已引用的用例路径）。

    8) Test-Refs（用于 PRD/GDD 回链；在成为 Accepted 前必须补齐为真实文件）：
       - `Game.Core.Tests/Determinism/OfferLockingTests.cs`
       - `Game.Core.Tests/Save/SaveResumeBoundaryTests.cs`
       - `Tests.Godot/Smoke/ContinueGateTests.gd`
       - `Tests.Godot/Security/SaveMigrationFailureBlocksContinueTests.gd`

    9) `logs/**` 证据链（在成为 Accepted 前必须能稳定产出）：
       - `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`
       - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（或等价汇总文件，字段口径不变）

  - Definition of Done:
    - 当以上 Acceptance Criteria 满足，并且具备对应 `logs/**` 证据路径与测试引用后，将本 ADR 的 Status 从 `Proposed` 更新为 `Accepted`。
  - Required follow-ups:
    - 必须同步更新 `project-context.md` 与 PRD 中关于 save/resume 的口径，避免文档漂移。
    - 门禁必须能产出与该策略一致的 `logs/**` 取证。
- Supersedes: None
- References:
  - `docs/prd/PRD-NEWROUGE-GAME-0001.md`
  - `project-context.md`
  - `docs/adr/ADR-0033-card-identity-and-forms.md`
  - ADR-0005-quality-gates
  - ADR-0019-godot-security-baseline
  - ADR-0030-core-threading-model
  - ADR-0031-build-reproducibility-and-version-pinning
