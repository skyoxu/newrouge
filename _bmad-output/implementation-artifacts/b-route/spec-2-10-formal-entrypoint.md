---
title: 'Story 2.10：现有正式入口的零 Task 采纳与跨会话复验'
type: 'feature'
created: '2026-11-11'
status: 'in-progress'
baseline_commit: '50923dc290885cb414f0a722276731c0fc53514d'
source_repository: 'r64'
review_loop_iteration: 0
---

# Intent

从已有公共 CLI/owning scripts 走通原 Epic2 的零 Task 正式规划、采纳、持久读取和原 journal 恢复，并保留同一计划身份、阻断依据及 resume_ref。本轮先实施最小入口适配；原真实验收与预算仍由既有前置和权限控制。Root 是唯一产品、Git 与测试 owner。

完整源码对账、证据范围、文件边界及顺序见Task `night-handoff/story210-latest-entrypoint-plan-20261111/plan.md`。原 AC 权威为 `r63/_bmad-output/planning-artifacts/b-route/epics.md:1198–1252`；以下没有添加 AC 或豁免前置。

# Scope and prerequisites

保留原 2.1–2.9 前置（epics.md:1206）。独立分支 R64 从 R62 8b5988f 起步，初次纳入 R63 7b806df7 与 8505729f，集成基线为 50923dc2。后续已纳入 R65 的历史模式透传修复、短 ID 夹具修正及真实尾段证据，对应 R64 提交 a05067a、8df4828b、75e935e0。2.8 realprepare10 已自然 OS2（100M 工作预算耗尽），保存原完整输入供局部诊断；2.9 原超时和失败记录保留，定向尾段已通过，但正式前置仍未完成。两项均未正式验收。R23 已批准分段/R59 fe175b49 继续独立跟踪额度接口真实组合与付费验证，不取消、不升格为 2.8/2.9 新前置。

本 Task 使用现有 prepare/account/audit/verify、plan-capabilities/plan-mvg、b-route-adoption 的原 stages。不给 3A/3B/3C 新建公共命令；不改默认 B、不写 Task/manifest、不调用未来编译器、不做 Knowledge 页面，不代验 runtime/full-MVG。

# Original AC mapping

| 原 AC | 本 Task 接线与可观察结果 | 前置／验收边界 |
| --- | --- | --- |
| AC-1，epics.md:1212–1217 | 由原 3A 到显式 B prepare/native，再由原 adoption review/prepare/reserve/apply/verify/publish/read；公开 reader 能核对 policy/origins/plan/receipt/catalog。修复 B MVG 默认 runner 接缝。 | 不能伪造 Task/witness/节点；原 source/native/review owner 资格仍必须成立。零 Task 与存量 Task 都由原 join 判定。 |
| AC-2，1219–1224 | 用原全局 audit、适用 native semantic admission 与原 published reader 联合验收；原诊断可显示合法前缀，任何缺口保持 blocked。 | accounted ≠ satisfied；planned ≠ runtime；formal_adoption ≠ 全局 planning complete。不创建新 completion carrier，不把 A manifest report 生套给 B。 |
| AC-3，1226–1231 | 原 ID inspect/read/context/recover-inspect/recover；重复 apply 的原 no-op 与 plan/binding 独立 revision；保留 owner diagnostics/resume_ref。 | native 2.9 adoption、Capability evidence resume 与文件 journal 恢复三类分开。损坏、unknown、后编辑、pending 沿原 owner 拒绝，不给新 ID 代替恢复。 |
| AC-4，1233–1238 | 正式入口引用并消费原合法循环、跨 Capability Flow、多 Flow 共享 Requirement、合法非 Flow 及对应失败证据。 | 不重写图或准入算法、不新建测试框架、不提前生成实施绑定；原算法缺陷仍回原 Story 修复。 |
| AC-5，1240–1245 | help、示例、AGENTS、两个 Skill 与阶段文档指向真实入口和恢复 owner；展示实际已有计时/dispatch/reuse/返工/终止事实。 | A 入口保持可定位；provider/cost 缺测量则 unknown；页面与默认 B 属 Epic4/5，不作为此 CLI 新前置。 |
| AC-6，1247–1252 | Root 在目标 Windows 完成原前置与本入口取证后，对照采纳 identity、逻辑四部分、review proof、不可变 plan、独立 binding revision、冻结 A 与原提交/恢复服务。 | 本草案不宣称验收；不提前实施 Epic3–5、4–7、Godot/C#、full-MVG。 |

# Proposed minimal implementation

## Runner and help

`dev_cli.py:891` 的 plan-mvg runner 默认与 direct `plan_mvg.py:7336` 不同，builder `dev_cli_builders.py:752–755` 把它传给 B runtime 的 Codex-only 门（`_b_route_planning_runtime.py:2291–2295`）。

只在现有 parser/builder 区分未指定和显式 runner：显式 B 默认原 Codex；原 A 默认/backend 行为保持；显式 runner 继续透传，非法值由原 owner 拒绝。不放宽 runner/effort/transition/预算验证，不添加 provider fallback。

planner help 清楚区分原 A 后置 Chapter5 与显式 B，无 Task 规划不带 legacy Task/readiness/draft 参数。实际 prepare 参数见 `_b_route_planning_input.py:789–808`。

## Exact existing commands

以下是待 Root 使用的参数形态，不是本次执行记录。所有占位符须由同一原有效链提供；脚本路径在目标 root 下执行。实际模型运行由 Root 另按已有预算/资格控制。

```powershell
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage prepare --run-id <fresh-id> --input-stage 3b --planning-contract <original-contract.json>
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage generate --run-id <same-id> --input-stage 3b --prepared-ref <original-prepared-ref> --planning-profile 3b-mvg-v1 --runner scripts/python/codex_isolated_model_runner.py
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage status --run-id <same-id> --input-stage 3b --prepared-ref <original-prepared-ref> --planning-profile 3b-mvg-v1
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage audit --run-id <original-B-mvg-run>
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage reopen-plan --run-id <original-B-mvg-run> --audit <original-run-relative-audit.json> --audit-sha256 <exact-sha256>
py -3 scripts/python/dev_cli.py plan-mvg --repo-root <root> --stage reopen --run-id <original-B-mvg-run> --plan <original-run-relative-plan.json> --plan-sha256 <exact-sha256>
py -3 scripts/python/dev_cli.py b-route-adoption --root <root> --stage inspect --operation-id <original-operation-id> --context
py -3 scripts/python/dev_cli.py b-route-adoption --root <root> --stage read --operation-id <original-operation-id> --context
py -3 scripts/python/dev_cli.py b-route-adoption --root <root> --stage recover-inspect --operation-id <original-operation-id>
py -3 scripts/python/dev_cli.py b-route-adoption --root <root> --stage recover --operation-id <original-operation-id>
```

当前源码即可显式给原 Codex runner；下一小改消除省略 runner 时的接缝，不改变显式调用权。audit/reopen 故意不含 `--input-stage`、prepared-ref、profile：这些 stage 的 direct parser 没有注册它们（`plan_mvg.py:7307–7318,7331–7337`），builder 也拒绝该组合（`dev_cli_builders.py:684,714`）。原 `_mvg_global_audit.operate:678–705` 从 MVG run.json 识别 B。不要把此路由描述成 capability-planning 的自动审计路由。

正式 host review 仍使用已有 review-prepare/review-complete，再接 prepare/reserve/apply/verify/publish；不在本草案写一个未经原 request/profile 确认的万能 request。`_b_route_adoption_review.py:511` 只描述原 runner command，不执行调用；原 source/native/host review proof 各自核对。`origin-prepare` 的有限历史 profile 不是任意新来源入口。

## Documentation and diagnostic presentation

补齐唯一 `docs/workflows/b-route-native-planning-status.md`，并定点更新 adoption owning doc、稳定入口、脚本索引、workflow、AGENTS、两个 Skill 链接。文档只说明真实支持，不发明 stage flags 或把 context 观察变成复用/恢复动作。

优先展示已有 `b_route_adoption.py:54–64` 的 codec diagnostics；`_b_route_commit.py:786–856` 的 recovery facts/next_stage/resume_ref；`889–918` 的正式 reader。native status 可能恢复 checkpoint，read 可能初始化协调元数据，recover-inspect 的只读事实不授初始准入。当前 native planner 的 status/reason 异常出口保持其真实形态，不为格式一致建立新 carrier。

handoff/3A/adoption 计量字段各按原 owner 提供；不把 logical_reserved_calls 当 provider dispatches 或账单，active elapsed 不伪造成 wall time，原 reason/unknown 保留。原阻断不得被 context 包装、Knowledge 摘要、换新 run ID 或 fresh apply 掩盖。

# Tasks

- [x] Root 核对原AC并采纳source-only边界，在独立r64基于50923dc2实施。
- [x] Root 修 parser/builder 的最小 runner 接缝和 planner help；不改 B runtime 原资格门。已提交 5e08a248。
- [x] Root 补 runner 默认/显式透传/A 默认保持的精准参数测试；复用原 audit/reopen 参数对测试，不扩展 stage。六项定向通过，非完整验收。
- [x] Root 创建 owning status 文档并定点修已有导航与 stage 权限陈述。已提交 5e08a248。
- [ ] Root 核对原 current-wire 与 R62 在途终态、组合源修订及前置 2.1–2.9 验收证据；不重开原 unknown。
- [ ] Root 从正式入口收集同原 identity 的真实 Windows 链与新会话复验，完成原 AC1–6；必要调用由 Root 掌握实际授权和预算。

# Verification and stop conditions

早期草案没有执行以上 Task；当前已实施和定向验证的范围见下文及上面的任务勾选。精确测试选择与已有证据限制见 plan.md 第 5 节；合成协议/服务 mock 只证明各自边界，不是 native/provider 资格，也不是 2.10 正式验收。

没有必要先做额外范围或防御性重构。若需要新增完成聚合返回、修改正式记录合同、跨 run 自动选择、额外源 hash/registry/carrier，或出现原 owner 无法提供 AC 所需事实的具体失败，停止该扩展，把文件、行号、输入/输出缺口交 Root 启动干净 Astra max；本草案不自行设计或实施。现有真实证据不足则保留 pending，不取消 R23，也不把它变成 2.8/2.9 新前置。

## 历史初次集成记录

独立分支`build/b-route-story210-entrypoint-2026-11-11`以最新2.8修复8b5988f为底，
仅整合已保存2.9的7b806df7/8505729f，得到当前基线50923dc2。原r62/r63文件未改。
runner/help与精准参数测试已写入，未执行。原audit参数测试的启动前缀仍为旧py -3，
已静态对照现有绝对入口修正，保留完整artifact/SHA配对和原owner透传，不改变stage。
2.8 prepare10已自然OS2，2.9完整样本超时后Job空且保留原generation2状态；
原前置、未知账本与分段工作仍待完成，不宣称2.10验收。

## 当前实施与定向证据

显式 B 的 Codex 默认 runner、显式 runner 保留和 A 路线默认值已实现。六项定向测试在原进程自然 OS0 后通过，证据为 Task/logs/ci/2026-11-11/story210-r64-entrypoint-focused-01/result.json 与 unit.json；零项目模型调用。新增 owning 导航与旧链接、stage 权限说明已写入。该结果不等同于本 Story 的真实全链验收。

后续基线 75e935e0 已集成 2.9 当前源码修复；三个相关文件与 R65 已保存版本逐字节一致，证据为 Task/logs/ci/2026-11-11/story210-r64-story29-integration-01/result.json。2.9 原 source 的定向尾段在实际 held OS exit 0、Job 静止后通过：相关依赖变化拒绝复用，无关变化可以采纳，保留原 10 次本地调用且新增调用为零。该结果只补齐其技术验证，不替代 2.8/2.9 正式验收，也不把六项 CLI 测试扩大成当前集成全链通过。

## Cloud public-read repair

The integrated public context now routes completed reuse to its existing native coordinator instead of claiming Story 2.9 is absent. An actual missing-receipt CLI failure exposed a null public resume_ref (AC3); the CLI now adds only the known receipt path when that read diagnostic lacks one, retaining original reasons and existing references. The failing RED, four affected passing checks, four actual fresh-process checks and the receipt-sealed clone control are recorded in `logs/ci/2026-11-11/cloud-epic2-recovery-03/REPORT.md`. Existing owner seams/clone upstream admission remain synthetic; these results do not qualify the original private operation or full Windows acceptance. Formal Story status remains in-progress.
