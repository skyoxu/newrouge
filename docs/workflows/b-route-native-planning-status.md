# 显式 B 路线规划、状态与恢复

本文导航已有 owner。原 A 路线保持有效，B 必须显式选择；本文不授予模型调用、正式采纳、Task readiness 或默认 B 启用资格。Story 2.10 的正式验收仍依赖 Story 2.1～2.9。

## 从来源到原生候选

3A 沿用[来源记账](b-route-source-accounting.md)与[独立来源审计](b-route-source-audit.md)。完整记账与审计证明不同；复用原审计前确认相关来源与规则仍适用。

Capability 与 MVG 使用同一个显式 3B 输入合同，分别保留原 planner、运行 ID、prepared 引用和执行 profile：

```powershell
py -3 scripts/python/dev_cli.py plan-capabilities --stage prepare --run-id <cap-run> --input-stage 3b --planning-contract <contract.json>
py -3 scripts/python/dev_cli.py plan-mvg --stage prepare --run-id <mvg-run> --input-stage 3b --planning-contract <contract.json>
py -3 scripts/python/dev_cli.py plan-mvg --stage generate --run-id <mvg-run> --input-stage 3b --prepared-ref <returned-prepared-ref> --planning-profile 3b-mvg-v1
py -3 scripts/python/dev_cli.py plan-mvg --stage status --run-id <mvg-run> --input-stage 3b --prepared-ref <returned-prepared-ref> --planning-profile 3b-mvg-v1
```

Capability 使用其原 `3b-capabilities-v1` profile。实际 profile 以当前 owner 的 `--help` 与冻结输入为准。显式 B 的默认隔离 runner 是官方 Codex；显式指定的 runner 原样传递，由执行 owner 检查合法性。现有 A 的生成 backend 和 review 默认值保留。不得把 Task、manifest、readiness 或 `allow-unready-draft` 当作 3B 的替代入口。

`generate` 会执行模型工作，必须已有实际预算与授权。`status` 会检查原 checkpoint，并可能恢复该 checkpoint；它不是完全无副作用的文件浏览。中断后先检查原进程、回执与 journal，保留未知调用占用，不重发未知请求或通过换 ID 清空历史。

## 全局审计与重开

候选独立准入、候选选择、全局审计与正式发布各有证据。一个合法 selected/handoff 或已发布前缀都不能单独证明全局规划完成。完成判断需共同核对原生语义准入、全局义务/依赖与冲突审计，以及正式 committed reader；缺少任一项时明确记录尚缺证据。

MVG 的原全局审计按原运行 ID 路由，**不附加** `--input-stage 3b`、prepared-ref 或 execution profile：

```powershell
py -3 scripts/python/dev_cli.py plan-mvg --stage audit --run-id <original-mvg-run>
py -3 scripts/python/dev_cli.py plan-mvg --stage reopen-plan --run-id <original-mvg-run> --audit <returned-audit-path> --audit-sha256 <returned-hash>
py -3 scripts/python/dev_cli.py plan-mvg --stage reopen --run-id <original-mvg-run> --plan <returned-plan-path> --plan-sha256 <returned-hash>
```

先审阅实际审计/重开计划，再执行原 `reopen`。需要源冲突声明时，按[原全局审计合同](mvg-integration-acceptance.md)传递 `--conflict-report` 与 `--conflict-report-sha256`。普通重叠不能自行授权重开。旧代次、回执与费用保留，新代次只执行新允许的工作。此入口不是独立 Capability run 的通用重开命令。

## 从候选到正式 operation

[采纳与 host review owner](b-route-adoption.md)负责 `review-prepare → review-complete → prepare → reserve`，随后原 commit owner 负责 `apply → verify → publish → read`。使用原 request、operation ID 与返回引用。`review-prepare` 只准备材料；它不执行模型、不创建预算。独立 reviewer 必须有真实执行证明，不能以人工布尔值或请求参数代替。

```powershell
py -3 scripts/python/dev_cli.py b-route-adoption --root <target-root> --stage inspect --operation-id <original-id> --context
py -3 scripts/python/dev_cli.py b-route-adoption --root <target-root> --stage read --operation-id <original-id> --context
```

只有校验通过的 committed publication 可以返回 `formal_adoption=true`；这仍不代表 runtime verified、Task readiness 或默认 B 已启用。`read` 使用受保护的原 committed reader，可能初始化本地协调锁元数据；不写入或修复正式内容。`--context` 仅支持 inspect/read，显示同一 operation 的原证据，不执行采纳、复用或全局完成判断。

## 三类恢复分别处理

1. 原生候选/代次恢复：原 planner 与其 checkpoint、dispatch、receipt owner；completed-unit reuse 仍由原 coordinator 校验。不能用 operation context 替代。
2. 已持久化 operation 中断：先 `b-route-adoption --root <target-root> --stage recover-inspect --operation-id <original-id>`，按实际 `next_stage`、`target_states` 和 `resume_ref` 决定原 `recover`。不先重做 apply 或更换 ID。
3. 已正式定义的补偿：沿用原 lineage、authority 和 compensation request；`read` 返回 successor 时定位该原 successor，不伪装为旧 receipt。本文不创建新补偿权限。

错误保持原 owner 的实际输出：adoption/commit 使用结构化 diagnostic 与 resume_ref；原 planner 可能只返回 status/reason。不得补写成功回执。逻辑调用次数不等于物理请求数；官方返回的运行时模型/high 配置可记录，但服务端实际模型、实际推理与实际费用未知时必须保留未知。
