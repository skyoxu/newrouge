# B 路线当前基线与消费者盘点

Story 1.1 提供独立只读盘点，不改变默认路线，也不调用 planner、三联编译、Chapter6、页面动作或发布入口。输出是当前工作树的观测记录；正式成熟成果保护基准由 Story 1.5 承接。Taskmaster master 继续是任务状态权威，业务视图的合法状态差异只报告。

## Windows 运行

要求 Python 3.12 或更新版本及 Git。必须显式指定仓库根目录、正式 B 路线 epics 和全新 run-id。以下 PowerShell 命令可从仓库根目录运行：

```powershell
py -3 --version
py -3 scripts/python/inventory_b_route_baseline.py `
  --root (Get-Location).Path `
  --epics _bmad-output/planning-artifacts/b-route/epics.md `
  --run-id story-1-1-baseline-001
$LASTEXITCODE
```

报告保存到 `logs/ci/<UTC-date>/b-route-baseline-inventory/<run-id>/inventory.json` 与 `inventory.md`。只创建新运行目录，目录即使为空也不复用。不要删除旧报告后重跑覆盖；改用新的 run-id。

```powershell
py -3 -m unittest discover -s scripts/python/tests -p test_b_route_inventory.py
```

本工具强制 Python 3.12 最低版本，并使用 `lstat` 检查符号链接和 Windows reparse 属性，不依赖可选的 `Path.is_junction`。输入必须使用真实大小写的仓库相对 POSIX 路径；重复分隔符、点段、Windows 尾点／尾空格别名、设备名和链接被拒绝。输入禁止 `.git` 和 `logs` 的大小写别名；仅三联中明确的 `evidence_refs` 可只读访问具体历史日志文件，不递归搜索日志。

## 报告含义

JSON 保留完整三联原始记录及累计 manifest。报告分开列出当前完整 HEAD／分支、声明的代码基线与输入快照提交、工作区差异、文件 raw 摘要、规范化换行摘要及 HEAD blob。历史提交不会被当成当前工作树。消费者矩阵包含文件／符号行定位、读写职责、当前 A 与目标 B 的差异、后续 Epic；实际 Capability／MVG 技能、Chapter4 sc 生成器、既有 worker／checkpoint／恢复均显式收录。Python 文档和示例按文件定位，不要求伪符号。

来源来自 epics 中十份不同的 canonical 输入，以及 AGENTS、ADR 正文状态、Base、M1 Overlay、契约、source-set 声明、三联和累计 manifest。沿三联 `test_refs`、`evidence_refs`、`source_refs` 保存原引用、所属文件和 JSON pointer、原任务 ID、master join 与实际文件 raw 身份；manifest 的实际测试／source／handoff 契约也进入闭包。`source_refs` 的行号须有效，事件／语义 ID 不冒充文件。

历史 `<date>` 等模板标记为 `unknown`，planned 测试、历史缺失证据均明确记录限制，不能作为运行通过。具体必需文件缺失、格式错误、失效定位、坏 join／重复 ID／缺失或非法原始状态、ADR 正文状态缺失或冲突都会阻止可采纳结论。master 每项至少映射一侧业务视图，每侧自身 ID 与 `taskmaster_id` 都必须唯一；保留原值，不反向同步状态。

### v2 引用角色合同

当前报告使用 `newrouge.b-route-baseline-inventory.v2`。每条 `task_and_manifest_references[]` 在原定位和观测上增加 `reference_role` 字符串及 `required` 布尔值，由 owning field 推导，调用者或 Task 状态不能改写角色。角色不删除任何原 Task 字段、历史引用或既有附件 bytes。

| 原 owning field／用途 | `reference_role` | `required` | 缺失的含义 |
| --- | --- | --- | --- |
| Task `evidence_refs` | `historical-debug-attachment` | false | 保留原引用、owner／pointer、Task 身份、`state=missing`、null raw 身份和 `missing-input` warning；附件单独缺失不阻断当前盘点 |
| Task `source_refs`／`test_refs`、manifest source／contract、已实现 manifest test | `current-input` | true | 保留 error，不能获得可采纳结论 |
| manifest 显式 planned test | `planned-input` | false | 保留原 planned 与 missing 观测，不冒称已实现或运行通过 |

同一路径若也被当前必需 owner 读取，其必需性仍生效；历史角色不豁免其他读取。不安全路径、大小写别名、reparse／链接、不可读文件和双采漂移继续阻断。历史附件实际存在时仍读取并绑定真实 bytes；存在、缺失及变化均进入内容身份与双采。若具体操作确实需要某份历史运行证据，该操作必须按自己的当前输入合同验证原件，不能从 `evidence_refs` 或盘点可采纳推断通过。语义决定见 [ADR-0049 提案](../adr/ADR-0049-b-route-reference-roles.md)。

v1 材料保留原始解释和 bytes，当前 reader 明确拒绝其 schema。v2 的 `rules` 必须完整、精确匹配 `inventory.rule_identity()` 返回的当前已安装五项实现／CLI raw 摘要；旧、缺失、删改或被替换的 rules 不能仅靠新版本字符串和重签摘要被接为当前支持规则的结果。采集与复核共用这一个规则身份 owner，不提供兼容升级或自动修补入口；需要当前材料时使用新 run ID 重新采集。

这项检查证明规则身份与当前支持集合一致，并与原 bytes 派生重建共同限定归档的语义解释。普通可变 JSON 中的规则摘要、checksum 和 `collection` 不认证采集事件来源，也不证明报告生成于某个真实新进程；复制当前摘要不是不可伪造的证书。归档复核不证明工作区仍与归档相同，实际当前性仍由新采集／compare 和具体操作的 currentness 检查负责。旧历史报告不能替代这些检查。

内容身份包含采集集合、raw bytes、Git 身份和执行规则实现；排除采集时间、事件 ID 和绝对工作目录。同内容重采应保持内容身份，事件 ID 不同。两轮均重新发现集合并读取完整引用闭包；集合、bytes 或 Git 身份改变时标记 `unstable`。两次读取只提供观察稳定性，不能隔离任意外部并发写者。消费者清单可核查位置，不自动证明语义完备；静态 manifest 校验也不证明游戏或 MVG 已运行。

## 退出码与处置

| 退出码 | 含义 | 处置 |
| --- | --- | --- |
| 0 | 两轮稳定且无阻断诊断，`adoptable: true` | 保留原报告供后续审阅，仍不等于运行通过或正式保护基准 |
| 1 | 输入损坏／缺失、未知必需状态或采集漂移，`adoptable: false` | 按 `diagnostics` 的文件／pointer 修复权威来源，或待外部编辑停止后换新 run-id 重采 |
| 2 | 根目录不是实际 Git 工作树根、输出位置不安全／已存在、run-id 不合法或运行版本不满足 | 修正参数或环境；原目录及旧证据保持不变 |

根目录及输出前置检查在创建运行目录前执行；此阶段失败退出 2，只输出终端诊断，不创建证据目录。已保留新运行目录后，能建立报告时仍保存 JSON／Markdown 的具体诊断；采集启动失败或 Git 超时时保存 `failure.json` 并退出 1。错误不会自动写回来源、任务、manifest、发布指针或既有日志。缺失历史证据应保留 missing／unknown 原因，不制造文件或日期来换取绿色结论。

例如，重复上述 run-id 应退出 2；指定 `--epics planning/missing.md` 且使用新 run-id 应退出 1。真实仓库原生 Windows CLI 与链接／junction 行为仍须在 Windows 环境留存原始证据。Linux fixture、模拟 reparse 属性和真实仓库双采不能替代该平台验收。
