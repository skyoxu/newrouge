# 架构现实与来源核实

- 结论：PASS；未发现需修复的 P0／P1／P2 问题。
- 日期：2026-11-03。
- 范围：`ARCHITECTURE-SPINE.md` 全文与 `planning-records.md` 全文；检查现存能力、技术版本及目标设计的表述是否有依据，不替代实施验收。
- 基线：代码 `cd925bdcae4b61992320773497f7edb729aac244`，文档输入 `e9cd3d9cb4f054f04348013c1cba926675fcca49`。核对的现存源码／版本文件相对代码基线无差异。

## 核实结果

| 声明 | 依据与判断 |
| --- | --- |
| 沿用 Godot.NET.Sdk 4.5.1、net8.0、SDK 8.0.401／latestPatch | `NewRouge.csproj:1`、`NewRouge.csproj:3`、`Game.Core/Game.Core.csproj:4`、`global.json:3`。与当日 `reference-research.md` 的官方存在性／适用性核实一致；主干明确不称最新、不升级。 |
| Python CI compatibility 3.12 | `.github/workflows/planning-production-acceptance.yml:61`、`.github/workflows/mvg-integration.yml:66` 明确为 3.12；其余若干 CI 仍为 3.x。主干将其表述为兼容基线，没有声称所有 CI 已固定同一解释器或新增 patch 门槛。 |
| 独立 worker、协调器预算与唯一 selected 提交点已存在 | Accepted `docs/adr/ADR-0039-mvg-completed-capability-recovery.md`；`scripts/python/_mvg_capability_worker.py:130` 使用独立 OS 进程和 workspace，调用经协调器 reserve；`scripts/python/_mvg_capability_checkpoint.py:310` 由协调器提交 `run.json`。AD-9 及新 catalog 协议保留原 selected 权威，没有把新 catalog 当作其替代品。 |
| 完成项恢复保原 proof、当前依赖重验及独立 adoption | `scripts/python/_mvg_capability_recovery.py:161` 只登记磁盘已提交 checkpoint；`:250` 起验证冻结来源及 proof，`:290` 起重放当前依赖／delta，`:314` 起创建独立 adoption。主干与伴随文件保持 ADR-0039 的 epoch／reopen 和禁止恢复未完成模型上下文边界，另行保留 Capability 显式证据及正式 apply 恢复。 |
| 现有 pending marker／journal 须适配 | `scripts/python/plan_capabilities.py:2207` 使用 `docs/planning/semantic-topology/capability-apply.pending.json`；`scripts/python/_planning_apply_journal.py:29` 检查 authority、前后像和后编辑。伴随文件第55行明确同时消费旧 marker／原 journal，没有误称现有代码已经具备新的 catalog、scope 租约或跨文件事务。 |
| Task／Chapter5 readiness 仍是现有后置 planner 输入 | `.agents/skills/plan-capabilities/SKILL.md:10`、`:24`，`scripts/python/plan_capabilities.py:99`、`:292`、`:2268`；`scripts/python/_mvg_obligations.py:52` 核对绑定 readiness，`:74` 在无适用 trace 时返回 current。AD-2、AD-5／6 及伴随文件第81行将消除这些 B 路线缺口明确写作目标适配，未冒称当前 B 已完成。 |
| 新记录、schema 与共享服务是目标设计 | 主干开篇明确“本主干规定目标一致性约束，不表示 B 已实现”；伴随文件第3行明确新增记录尚待实施。`docs/planning/b-route/`、新 schema ID、InputSet、VerificationScope、catalog／receipt 和租约均属于本次架构合同，未被表述为已部署模块。 |
| 文件提交与 Windows 能力边界 | AD-8／17 和伴随协议区分逐文件写入、receipt 与最终发布；明确人工后编辑、占用与故障注入限制，未从 Python replace 推导多文件数据库隔离或已验证 Windows 崩溃耐久性。与 `reference-research.md` 的官方文档核实及推论边界一致。 |

## 验证边界

仅执行只读文档／源码核对与定向 diff，并写入本审查文件；未运行测试、模型规划、Chapter 工作流、Windows／Godot、发布或部署。已核实的官方固定版本事实沿用当日原始参考证据；没有追加“最新版本”或运行通过声明。未发现需要重新外部检索的事实冲突。
