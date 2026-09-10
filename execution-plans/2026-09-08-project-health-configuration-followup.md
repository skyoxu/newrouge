# 配置来源统一后续计划

- Title: 配置来源统一后续计划
- Status: paused
- Branch: feat/project-health-local-scan
- Git Head: 14e2d3297830d6a34382c97a21d962ec3e063440
- Goal: 以权威玩法决策统一初始牌组和卡池来源
- Scope: WarriorStartingDeckService、CardPoolCatalog 与对应 JSON
- Current step: 等待玩法来源决策
- Last completed step: 修改导航、标题同义修复及定向验证
- Stop-loss: 禁止将十张独立卡与 5+4+1 自动互换
- Next action: 对齐 PRD/ADR 与数据后明确迁移规则
- Recovery command: py -3 scripts/python/project_health_knowledge.py task --task-id 24
- Open questions: 正式初始牌组及 shop/Act2/3 卡池口径
- Exit criteria: 权威规则一致且对应定向测试通过
- Related ADRs: ADR-0035、ADR-0007、ADR-0033
- Related decision logs: `decision-logs/2026-09-08-project-health-configuration-audit.md`
- Related task id(s): 24、115
- Related run id: modification-navigation-2026-09-08
- Related latest.json: `logs/ci/project-health-knowledge/latest.json`
- Related pipeline artifacts: `logs/ci/2026-09-08/modification-navigation/`、`logs/ci/2026-09-08/project-health-navigation/`

状态：待玩法决策。

关联决策：`decision-logs/2026-09-08-project-health-configuration-audit.md`。

1. 对齐 T24 初始牌组的 PRD、ADR-0033、现有十张独立卡测试和 5+4+1 JSON。先确定正式牌组及稀有度语义，再决定迁移实现；不得直接删除现有验收。
2. 对比 `CardPoolCatalog.cs` 与 `m1-card-pools.json` 全部 pool ID、Act、encounter type、稀有度；补齐 shop/Act2/3 的产品范围后，决定统一数据模型。
3. 若改变玩法规则，更新权威 PRD/ADR 后执行定向 xUnit/GdUnit，保留迁移前后证据。
4. 后续确认 pick 超过卡池大小时的标题语义及列表策略；本轮保留既有行为，不能把配置请求数量视为实际卡牌数。

验证证据路径：`logs/ci/2026-09-08/modification-navigation/`。导航使用 main `68d6d28b0361d116b18740b372c24a888ccdc142`；导航中的配置与素材关系仅为静态引用或候选，不代表运行观测。

已完成：任务详情修改导航、配置精确位置、静态资源链、建议测试入口、标题同义修复。剩余 Needs Fix 为上面两项玩法来源冲突，未经决策不自动迁移。
