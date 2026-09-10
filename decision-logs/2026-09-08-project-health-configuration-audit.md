# 游戏配置与硬编码差异审计

- Title: 游戏配置与硬编码差异审计
- Date: 2026-09-08
- Status: accepted
- Supersedes: n/a，本次新增审计
- Superseded by: n/a，尚无后续决策
- Branch: feat/project-health-local-scan
- Git Head: 14e2d3297830d6a34382c97a21d962ec3e063440
- Why now: 任务修改导航暴露配置与硬编码差异
- Context: T24 初始牌组与卡池数据不是同义规则
- Decision: 修复奖励标题同义重复，保留并记录玩法冲突
- Consequences: 初始牌组和卡池来源统一仍为 Needs Fix
- Recovery impact: 从关联 execution plan 继续，不自动替换玩法
- Validation: Python 64 tests 与定向 GdUnit 2 cases 通过，浏览器实际点击和快照漂移回归通过
- Related ADRs: ADR-0035、ADR-0007
- Related execution plans: `execution-plans/2026-09-08-project-health-configuration-followup.md`
- Related task id(s): 24、115
- Related run id: modification-navigation-2026-09-08
- Related latest.json: `logs/ci/project-health-knowledge/latest.json`
- Related pipeline artifacts: `logs/ci/2026-09-08/modification-navigation/`、`logs/ci/2026-09-08/project-health-navigation/`

状态：Needs Fix（玩法来源统一待决策）；导航与同义标题修复已完成。

依据：Accepted ADR-0035、ADR-0007；`_bmad-output/implementation-artifacts/spec-project-health-modification-navigation.md`。

`WarriorStartingDeckService.cs` 声明十张不同卡，稀有度分布为 7 common、2 uncommon、1 rare；`Game.Core/Data/m1-warrior-starting-deck.json` 则是 strike 5、defend 4、battle_focus 1。后者有实际加载线索，但不能据此推翻前者与 T24/PRD 的约束。这不是同义数据替换，保留两者并等待玩法权威决策。

`CardPoolCatalog.cs` 包含 shop 与 Act2/3，且与 `m1-card-pools.json` 的 pool ID、卡牌稀有度分组存在差异。不能自动用该 JSON 替换服务目录。

`Main.gd` 奖励卡数已读取 `config.pick`，标题固定 3-Choice 属于同义展示重复，已改为读取同一个 pick，缺省仍为 3；没有改变掉落规则。

证据入口：`logs/ci/2026-09-08/modification-navigation/`（task-24.json、task-115.json、python-regression.txt、gdunit-red-console.txt、gdunit-green/）。任务导航快照绑定 main revision；工作区标题修复的 GdUnit 结果不冒充该 main 的运行使用证据。

后续入口：`execution-plans/2026-09-08-project-health-configuration-followup.md`。

评审补充 deferred：当 pick 大于卡池可用数量时，标题显示配置请求数量，实际列表受卡池长度限制。这是修复前已存在的规则边界，本轮不改变玩法或截断策略；后续先确认标题应描述请求数量还是实际数量，再补对应数据与验证。
