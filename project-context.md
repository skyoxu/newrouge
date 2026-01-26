---
project_name: newrouge
user_name: skyo
date: "2026-01-23"
sources:
  - AGENTS.md
  - docs/testing-framework.md
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
  - _bmad-output/gdd.md
  - _bmad-output/epics.md
  - _bmad-output/content-id-standard.md
  - _bmad-output/content-registry.md
  - _bmad-output/audit-artifact-pipeline.md
  - project.godot
  - docs/adr/ADR-0032-save-resume-determinism.md
adr_refs:
  - ADR-0001-tech-stack
  - ADR-0003-observability-release-health
  - ADR-0004-event-bus-and-contracts
  - ADR-0005-quality-gates
  - ADR-0007-ports-adapters
  - ADR-0010-internationalization
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0015-performance-budgets-and-gates
  - ADR-0019-godot-security-baseline
  - ADR-0020-contract-location-standardization
  - ADR-0025-godot-test-strategy
  - ADR-0030-core-threading-model
  - ADR-0031-build-reproducibility-and-version-pinning
  - ADR-0032-save-resume-determinism
sections_completed:
  - technology_stack
  - technology_stack_versions
  - engine_rules
  - repo_rules
  - architecture_boundaries
  - testing_and_gates
  - security_baseline
  - logging_and_artifacts
  - performance_rules
  - code_organization
  - localization_and_content_pipeline
  - platform_build_rules
  - dont_miss_rules
  - gameplay_invariants
status: complete
optimized_for_llm: true
rule_count: 175
section_count: 12
---

# project-context.md（AI 协作戒律）

这份文件是 AI 在本仓库写代码/测试/脚本时必须遵守的“硬口径”，目标是减少多代理协作时的口径漂移与返工。

---

## 1) 绝对约束（违反即视为缺陷）

- 只支持 Windows（见 ADR-0011-windows-only-platform-and-ci）
- 只用 UTF-8 编码处理中文；仓库文本统一 `charset=utf-8`（见 `.editorconfig`）
- 禁止 Emoji 字符（输出与提交内容均不使用）
- 文档正文用中文；代码/脚本/测试文件只用英文（含注释与日志打印）
- 日志与取证统一写入 `logs/**`（不要散落到其他目录）
- 仅防御安全；拒绝任何可被滥用的进攻性实现
- 除非明确要求，不引入新第三方库/插件（先复用现有依赖与脚本）
- 不写占位 TODO；要么完整实现并可运行，要么明确拒绝并说明阻塞条件

---

## 2) 技术栈与版本（从仓库实物发现）

- 引擎：Godot 4.5.1 .NET（锁死；见 ADR-0031）
- 渲染：Forward Plus（见 `project.godot` `config/features`）
- 语言与运行时：C# / .NET 8（`net8.0`，`Nullable=enable`）
- 数据库：SQLite（`Microsoft.Data.Sqlite`，`SQLitePCLRaw.bundle_e_sqlite3`）
- 单元测试：xUnit + FluentAssertions + coverlet.collector（见 `Game.Core.Tests/Game.Core.Tests.csproj`）

### 2.1 版本锁定与可复现（硬规则；SSoT：ADR-0031）

- Godot .NET：锁死 4.5.1；`GODOT_BIN` 必须使用 4.5.1 的 console 版二进制；export templates 必须匹配 4.5.1
- .NET：目标 `net8.0`；不使用 `global.json`
- NuGet：必须启用并提交 `packages.lock.json`（`RestorePackagesWithLockFile=true`）；若 lock 缺失视为阻塞前置条件，需 `dotnet restore .\\NewRouge.sln` 生成
- 取证：门禁必须写 `logs/ci/<YYYY-MM-DD>/env-evidence/`（Godot/DotNet/Python 版本、`GODOT_BIN` 路径与 sha256）
- SQLite：v1 保持当前 provider/bundling 不变；任何变更必须先写 ADR 并补齐 headless 冒烟与 `logs/**` 取证

---

## 3) 目录边界与分层（不要越界）

- `Game.Core/**`：纯 C# 领域层，禁止引用 Godot API（可被 xUnit 毫秒级测试）
- `Game.Godot/**`：适配层与引擎层，只在这里调用 Godot API；通过接口把依赖注入 Core（见 ADR-0007-ports-adapters）
- `Game.Core/Contracts/**`：契约与事件 SSoT（见 ADR-0020-contract-location-standardization）
- `Game.Core.Tests/**`：xUnit 单测（领域规则与状态机优先）
- `Tests.Godot/**`：GdUnit4/冒烟等引擎侧测试

如果需要引入“事件/契约”，统一遵循 ADR-0004-event-bus-and-contracts，并将 DTO/事件类型落盘到 `Game.Core/Contracts/**`，不要在文档里复制粘贴源码。

---

## 4) Godot 运行时约定（从 `project.godot` 发现）

- 主场景：`res://Game.Godot/Scenes/Main.tscn`
- Autoload（全局单例）已定义：`EventBus`、`DataStore`、`Logger`、`SecurityAudit`、`PerformanceTracker`、`SentryClient`、`FeatureFlags`、`CompositionRoot` 等
- 原则：只把“不可避免的引擎胶水”留在 Autoload；领域规则仍在 `Game.Core/**`

### 4.1 引擎硬规则（Godot + C#，失败模式防护）

#### 生命周期与装配
- 禁止在字段初始化/构造函数中访问 `/root/*` Autoload 或场景节点；只允许在 `_Ready()`（或更晚）做依赖获取与连线
- 依赖 Autoload（如 `CompositionRoot`、`EventBus`）必须做存在性校验；缺失时必须 fail-fast（日志 + 禁用功能/退出），禁止静默吞错
- `CompositionRoot` 是装配唯一入口：场景脚本只做 UI/信号路由与胶水，不在 Scene 内自行 new 领域服务

#### Signals 与契约
- 场景内通信用本地 Signals；跨场景/全局事件统一走 `EventBus`（ADR-0004）
- 新增事件/DTO 必须落盘到 `Game.Core/Contracts/**`（ADR-0020）；引擎层只引用，不复制实现
- 订阅必须可回收：重复进入场景会触发重复订阅的地方，必须在 `_ExitTree()`/Dispose 断开信号或解除订阅，避免重复响应与泄漏

#### Headless 可测性（GdUnit4）
- 禁止依赖真实 `InputEvent` 完成关键流程（headless 不可靠）；关键路径必须提供可调用的公开方法（如 `ShowPanel()`、`StartRun()`）或可直接 `emit_signal` 的入口
- 等待异步/装配只允许有上限的帧轮询（常规 <=60 帧，复杂 <=120 帧）；超过上限视为失败，禁止无限等待

#### 线程边界
- `Game.Core/**` 默认线程封闭（ADR-0030）；跨线程传递必须使用不可变 DTO/快照
- 后台线程不得触碰 Godot 对象/SceneTree；应用结果必须回到主线程并走受控入口（Adapters/调度器）

#### 安全基线（默认拒绝）
- 文件路径只允许 `res://`（只读）与 `user://`（读写）；拒绝绝对路径与越权路径；失败必须审计落盘 `logs/**`（ADR-0019）
- 网络/外链：只允许 HTTPS + 白名单；`GD_OFFLINE_MODE=1` 必须拒绝出网并审计（ADR-0019）
- 禁止运行期动态加载外部程序集/脚本；`OS.execute` 默认禁用或仅开发态启用且强审计（ADR-0019）

#### 反模式（出现即要求重构）
- 禁止在 Node/Scene 内实现领域规则（战斗结算、卡牌效果、掉落权重等）：必须下沉到 `Game.Core/**` 并用 xUnit 覆盖
- 禁止用静态全局状态绕过装配（不可测、不可控）
- 禁止在文档中复制契约/阈值源码：必须引用 ADR/Base/Contracts 作为单一口径

---

## 5) 测试与质量门禁（必须先绿后动）

- TDD 优先：先写 `Game.Core.Tests/**` 失败测试，再写 `Game.Core/**` 实现
- 禁止为了推进而跳过/禁用测试（见 ADR-0005-quality-gates）
- 引擎侧验证用 GdUnit4（headless 友好），只覆盖场景树/信号/装配关键路径
- Windows 命令统一使用：
  - 单测：`dotnet test --collect:\"XPlat Code Coverage\"`
  - 一键门禁：`py -3 scripts/python/quality_gates.py all ...`
- 所有测试与审计产物写入 `logs/**`（见 `docs/testing-framework.md` 与 `AGENTS.md`）

---

## 6) 安全基线（只做防御，默认拒绝）

遵循 ADR-0019-godot-security-baseline：
- 文件路径：只允许 `res://`（只读）与 `user://`（读写）；拒绝绝对路径与越权路径
- 外链与网络：只允许 HTTPS；主机白名单；`GD_OFFLINE_MODE=1` 时拒绝出网并审计
- `OS.execute` 默认禁用（或仅开发态开启并强审计）
- 审计输出写入 `logs/**`（例如 `logs/ci/<date>/security-audit.jsonl`）

---

## 7) 可观测性与性能（不要复制阈值，引用口径）

- 可观测性：按 ADR-0003-observability-release-health 与 `docs/architecture/base/03-observability-sentry-logging-v2.md`
- 性能预算：按 ADR-0015-performance-budgets-and-gates 与 `docs/architecture/base/09-performance-and-capacity-v2.md`
- 原则：文档与实现里不要硬编码阈值数字；引用 ADR/Base 作为单一口径

### 7.1 帧预算与关键路径（默认面向 60fps）

- 目标帧率与预算口径以 ADR-0015 为准；任何“帧预算/首屏/卡顿阈值”的数字只允许出现在 ADR/Base/门禁脚本里
- 热路径定义：战斗回合推进、卡牌 UI 列表渲染/布局、特效/音频触发、地图节点生成与渲染
- 关键路径的实现必须可被性能烟测覆盖（见 `scripts/python/perf_smoke.py`；产物写 `logs/perf/**`）

### 7.2 Hot Path 规则（Godot + C#）

- 禁止在 `_Process()` / `_PhysicsProcess()` 中做可避免的分配与反射：避免 LINQ、字符串拼接、临时集合、频繁 `new`
- 节点查找要缓存：`GetNode()`/`GetTree()`/`GetNodesInGroup()` 在热路径内必须避免频繁调用；使用 `NodePath`/引用缓存
- UI 更新要“批量化”：同一帧内多次刷新/重排要合并；列表/卡牌视图优先复用实例（池化或复用容器子节点）
- 事件风暴要限流：`EventBus` 上高频事件需要聚合或采样，避免每帧广播大量 payload（参考 ADR-0004）

### 7.3 内存与资源加载（避免抖动）

- 资源加载分层：启动/场景切换阶段做预加载；战斗热路径禁止同步加载大资源（贴图/音频/场景）
- 大对象复用：卡牌 UI、弹幕/特效节点、临时提示等高频对象优先采用对象池或复用策略
- 长会话泄漏防护：订阅/Signal 绑定必须可回收（见 4.1）；长期运行（60 分钟）仍需保持稳定内存曲线
### 7.4 取证要求（可观测性 + 性能）

- 性能相关回归必须附带 `logs/perf/**` 摘要与关键场景说明；若触及预算口径，先更新 ADR-0015（或新增 Supersede ADR）

---

## 8) 玩法不变量（实现必须对齐 PRD）

SSoT：`docs/prd/PRD-NEWROUGE-GAME-0001.md`

- 单局结构：3 Act 分叉路线图；目标时长约 60 分钟
- 战斗能量：每回合基础能量 `X=3`
- 初始套牌：10 张（7 普通 + 2 优良 + 1 精英）
- 角色：3 个
  - 战士：怒气为可叠加状态 Buff（不是第二属性条）
  - 刺客：擅长施加多种 Debuff，并在合适时机兑现收益
  - 德鲁伊：持久 Buff + 姿态切换触发定点爆发；切换必须有成本
- 卡牌：每角色 30 张基础卡（不含升级版本）；v1 有卡牌升级系统（U1 二选一路线 + Ultimate 终极形态）
- 遗物：首发 20 个
- 事件：首发 40 个；同一局内事件不重复
- 元系统：共享天赋树，可无条件重置；天赋树与 10 档难度不强绑定
- 难度：10 档，首发以数值调整为主
- 存档：节点前存档；进入战斗后自动保存“战斗初始状态”；不允许战斗中退出续打

当上述不变量改变时，必须先更新 PRD（并补齐对应测试/取证），再改实现。

---

## 9) 代码组织与内容管线（新增必须遵守）

### 9.1 命名空间与身份统一（新增代码硬规则）

- 新增 C# 代码命名空间一律使用 `NewRouge.*`；禁止新增 `Game.*`
- 允许短期保留既有 `Game.*`，但后续只能“一次性全量迁移”，禁止长期混用

### 9.2 场景/脚本命名与绑定（Godot）

- `.tscn` 统一 PascalCase + 类型后缀（从新增开始强制）：`*Screen.tscn`、`*Panel.tscn`、`*Menu.tscn`、`*Hud.tscn`、`*View.tscn`
- 一个场景一个同名脚本：`X.tscn` ↔ `X.cs`；禁止“一个脚本服务多个不相干场景”

### 9.3 Assets vs Resources（目录边界）

- `Game.Godot/Assets/**`：源素材（`.png/.svg/.wav/.ogg/.ttf/.otf` 等）
- `Game.Godot/Resources/**`：数据/配置型 Godot Resource（`.tres/.res`）
- `Game.Godot/Scenes/**`：只放 `.tscn`
- `Game.Godot/Scripts/**`：只放 `.cs`

### 9.4 Translations（UI 文案与叙事文本）

- SSoT：`Game.Godot/Translations/**`（格式默认 `csv`；初期语言默认 `en` + `zh-CN`；口径见 ADR-0010）
- 脚本里禁止硬编码“可见文本”（UI/叙事/奖励文案等）；仅允许 debug 日志/异常消息/审计 reason 使用英文硬编码（非 UI 可见）
- Key 命名：点分层 + 强制域前缀：`ui.*`、`card.*`、`relic.*`、`event.*`、`meta.*`、`enemy.*`、`status.*`
- 占位符：使用 `{name}` 命名占位符；禁止对翻译字符串使用 `string.Format`（必须使用“命名占位符替换”约定实现）
- Key 生命周期：发布后视为稳定 ID；允许改名/删除，但必须提供迁移映射并写入 `logs/ci/**` 取证；未使用 key 初期按 CI warning 处理

### 9.5 事件结构与文本解耦（可测试）

- 事件结构（触发条件/权重/奖励表/分支）放 `Game.Godot/Resources/**`
- 事件文本（标题/描述/选项）只放 `Game.Godot/Translations/**`
- 抽样抑制逻辑（同局不重复/冷却）必须在 `Game.Core/**`（可 xUnit 单测）
- 内容稳定 ID：点分层（例如 `event.act1.bandits`、`card.warrior.strike`）
- 稳定 ID 语法：全小写 ASCII；用 `.` 分层；slug 仅允许 `[a-z0-9_]+`；禁止空格/中文；一旦发布不得重命名（只允许新增并通过迁移/别名兼容）
- Events 目录默认：`Game.Godot/Resources/Events/Common/**` + `Act1/**` + `Act2/**` + `Act3/**`
- 文本 key 与事件 ID 强绑定：事件 ID `act1.bandits` 对应 `event.act1.bandits.title/desc/opt.*`

### 9.6 测试对齐（强制映射）

- `Game.Core/<Area>/Foo.cs` → `Game.Core.Tests/<Area>/FooTests.cs`
- 新增 Core 类型必须有对应单测；仅纯 DTO 允许例外

### 9.7 导出与归档命名

- 导出产物名：`NewRouge.exe` / `NewRouge.pck`
- 稳定 slug：`newrouge`

---

## 10) 平台与构建（Windows-only，门禁入口）

### 10.1 平台与引擎版本（硬规则）

- 只支持 Windows（ADR-0011）
- Godot .NET 必须锁死 `4.5.1`，`GODOT_BIN` 必须指向 4.5.1 console 版二进制（ADR-0031）
- export templates 必须匹配 `4.5.1`（不提交到仓库；由本机/CI 预装并在门禁中取证）

### 10.2 环境变量（最小集）

- 必需：`GODOT_BIN`
- 建议：`GODOT_PROJECT`（仓库根目录，避免 CWD 漂移）
- CI 安全默认：`GD_SECURE_MODE=1`、`SECURITY_TEST_MODE=1`（`GD_OFFLINE_MODE=1` 时必须拒绝出网并审计）

### 10.3 门禁入口（Python 为唯一口径）

- 唯一口径命令（Windows）：
  - `py -3 scripts/python/quality_gates.py all --godot-bin \"%GODOT_BIN%\" --solution Game.sln --configuration Debug --build-solutions`
- PowerShell 包装器（可选，内部仍调用 Python）：
  - `powershell -ExecutionPolicy Bypass -File scripts/ci/quality_gate.ps1 -GodotBin $env:GODOT_BIN`

### 10.4 可复现硬前置（失败即阻塞）

- 必须安装 .NET 8 SDK（未安装视为门禁失败）
- 必须提交并保持最新的 `packages.lock.json`（缺失视为阻塞前置条件）：
  - `packages.lock.json`（仓库根，`NewRouge.csproj`）
  - `Game.Core.Tests/packages.lock.json`
  - `Tests.Godot/packages.lock.json`
- 生成方式：`dotnet restore .\\NewRouge.sln`

### 10.5 取证与日志（SSoT）

- 门禁必须写入 `logs/ci/<YYYY-MM-DD>/env-evidence/**` 与 `logs/ci/<YYYY-MM-DD>/prereqs/**`（Python 入口负责）
- 其他 CI 工件也必须落在 `logs/ci/<YYYY-MM-DD>/**`（禁止写到 `logs/ci/<timestamp>/...`）

---

## 11) 关键防踩坑规则（Don’t-Miss，违反即视为缺陷）

- v1 必须提供“卡牌升级系统”（仅休整或事件升级；商店任何时候都不提供升级服务）：
  - 休整节点：升级是“多选一”选项之一；若选择升级，则免费升级 1 张卡牌
  - 常规升级（U1）：每次升级必须在 Route A / Route B 二选一；选择不可逆
  - 特殊事件：允许对已 U1 的卡牌免费更换升级路线；事件内可无限次切换，离开事件时以最终选择为准
  - 终极形态（Ultimate）：每张卡 1 个终极形态；仅史诗事件/关卡 Boss 等稀有机会获取；可从未升级卡直接进阶；不可逆；不可再升级、不可再换路线
  - 升级是显式玩家输入，不得引入额外 RNG；禁止“通过 UI 操作推进 RNG”

### 11.1 存档：粒度、限制、版本化（硬规则）

- 存档/继续游戏/确定性反刷随机的口径以 ADR-0032 为准；任何变更必须先写 ADR 并补齐测试与 `logs/**` 取证
- 运行时审计写入 `user://logs/security/security-audit.jsonl`，自动化测试/门禁结束时（成功或失败）必须归档到仓库：`logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（无证据 = 不可复现；详见 `_bmad-output/audit-artifact-pipeline.md`）
- 存档粒度（玩法硬约束）：
  - 节点前：只保存“节点入口前状态”
  - 进战斗：只保存“战斗初始状态”
  - 战斗中：禁止保存中间态；禁止通过任何方式恢复到战斗中（包括自动备份、崩溃恢复、临时文件）
- 存档必须版本化：使用整型递增 `schema_version`（`1,2,3...`），并支持向后迁移（迁移必须幂等）
- 迁移取证必须落盘：`logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`

### 11.2 RNG：确定性与可回放（硬规则）

- 必须强制确定性：同一 `seed` + 同一输入序列 = 同一结果（用于复现与禁“退出重进”口径的取证）
- RNG 按系统拆分（禁止全局单一 RNG）：`run_rng`、`combat_rng`、`loot_rng`、`event_rng`（从 run seed 派生）
- 抽样与冷却逻辑的 SSoT 必须在 `Game.Core/**`（可 xUnit 单测）；Godot 只负责展示/资源加载

### 11.3 事件池：同局去重与跨局抑制（硬规则）

- 同局不重复的边界：事件“定义 ID”不重复（而非事件类型粗粒度去重）
- 跨局重复抑制策略：组合策略（权重衰减 + 硬冷却窗口），具体参数只在 ADR/Base/门禁中定义

### 11.4 安全开关：CI 默认（硬规则）

- CI 默认强制：`GD_SECURE_MODE=1`、`SECURITY_TEST_MODE=1`、`GD_OFFLINE_MODE=1`
- `GD_OFFLINE_MODE=1` 下必须拒绝所有出网并审计（审计产物写 `logs/**`，口径见 ADR-0019）

---

## 12) 使用与维护（面向 AI 与人类）

### 12.1 给 AI 的规则

- 写任何代码/脚本/测试前先读本文件；冲突时优先选择更保守、更可审计的方案
- 任何会落地为代码/测试的改动必须引用至少 1 条 `Accepted` ADR；若改变口径/阈值/契约/安全策略，先新增或 Supersede ADR
- 日志/取证一律写入 `logs/**`，并遵循 `logs/ci/<YYYY-MM-DD>/**` 的目录规范

### 12.2 给人类的维护准则

- 保持精炼：只保留“容易踩坑且必须一致”的规则，删除显而易见或过时内容
- 技术栈/版本/门禁口径变化时，先更新 ADR，再同步更新本文件
- 任何新增的跨切面约束（安全/可观测性/门禁/契约/存档）都必须被门禁脚本与取证目录验证

---

## 13) 内容登记（SSoT）

- 内容稳定 ID 与翻译 key 必须登记到 `_bmad-output/content-registry.md`（新增前登记，发布后不得重命名）
- `translation_key_prefix` 必须与 `content_id` 一致，避免 key 漂移与漏配
