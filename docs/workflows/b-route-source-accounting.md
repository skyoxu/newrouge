# B 路线 3A 来源记账

`_b_route_sources.py` 是唯一编排 owner；`account_b_route_sources.py` 和 `dev_cli.py b-route-sources` 共用该服务。它准备累计来源并消费显式语义提议，不要求 Task、Chapter 5 readiness 或既有场景。现行 A 命令继续有效，本入口不启用 B。

来源准备、完整记账、独立来源审计和正式采纳分别判断；本命令只提供前两项。报告中的 `satisfied`、`independent_audit`、`formal_adoption` 始终为 false。不调用模型、apply、来源注册写入、Taskmaster／MVG 修改、Knowledge 发布或旧操作恢复。

## 准备来源

使用 Windows／Python 3.12 及以上版本。文件参数采用精确的仓库相对 POSIX 路径，`--root` 显式选择仓库根。ID 为 1–96 个 ASCII 字母、数字、下划线或连字符，首字符为字母或数字。根目录真实短路径别名解析为实际根；后代别名、链接和 junction 拒绝。

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage prepare --root C:/work/newrouge --run-id source-review --scope-id reward --attempt-id prepare-01 --source-set docs/workflows/chapter3-source-set.json
```

source-set 使用既有 `chapter3.source-set.v1` 合同；当前 patterns 与 `active_sources` 均累计保留，旧来源消失须显式退役。历史退役继续排除，包括三份已退役 GDD。可选 `--previous <prepared.json>` 提供旧归档 Ledger，供原生 add 稳定块 ID 和计算 delta。新一次准备允许当前来源变化，旧 proof 保持不可变。

可选 `--declaration <path>` 是显式待核对输入载体，不是第七类正式规划记录。精确结构：

```json
{
  "schema_version": "newrouge.b-route-sources-declaration.v1",
  "additions": ["docs/prd/reward-change.md"],
  "retirements": [{
    "path": "docs/prd/old-reward.md",
    "reason": "The cited reviewed change replaces this source.",
    "evidence": {
      "path": "docs/prd/reviewed-change.md",
      "raw_digest": "sha256:<64 lowercase hexadecimal characters>",
      "byte_start": 0,
      "byte_end": 40
    }
  }]
}
```

证据采用非空原字节区间，结束位置不包含在内；文件必须存在且 raw digest 相等。定位证据不证明语义审阅或批准。新退役理由非空；新增不能复活历史退役或与退役冲突。历史移除文件、存在／不存在状态及可用原 bytes 保存在准备证据中，本工具不写更新后的 source-set。

排他创建 `logs/ci/<UTC-date>/b-route-sources/<run-id>/<attempt-id>/prepare/`，保存原生 manifest／Ledger、完整语义 batches／index、无损传输 proof、原字节归档、`prepared.json`、未审 `candidate.json` 和终态 report／event。原生文本 hash 和块 ID 保留换行归一化／trim 语义；原字节 digest 和归档另行证明 CRLF、尾空白、空输入及未形成语义块的字符。

`--max-blocks`（24）和 `--max-chars`（24000）约束完整语义对象，超限阻断而不截断。`--transport-max-bytes`（1048576）和 `--transport-max-input-tokens`（96000）通过既有 measurer 独立约束每个含 schema 的最终请求。传输可跨请求分片并完整还原原文，但不证明任一请求见到完整语义对象或正确理解。dispatch 始终为零，估算不是账单。

## 核对显式提议

将准备好的 candidate 复制到独立文件，保持准备产物原样。审阅每块并核对每批；准备阶段不编造验收意图或声称去向已审。

atom 的提议数据：

```json
{
  "proposal_id": "proposal:reward-order",
  "kind": "functional",
  "statement": "Preserve reward candidate ordering.",
  "source_block_ids": ["SB-<existing-block-id>"],
  "acceptance_intent": "Selecting a reward preserves the displayed candidate ordering.",
  "prior_requirement_ids": ["FR-EXISTING"],
  "non_task_sinks": ["reward-order-check"]
}
```

`proposal_id` 使用 `proposal:` 命名空间，不是正式分配。`prior_requirement_ids` 仅回链已知旧身份，可为空；`non_task_sinks` 是明确去向标识字符串，后续规划尚需选择责任时可为空。拒绝正式 `requirement_id`／Capability 分配。共享提议可出现在多个主归属块中，但正文和完整跨批 `source_block_ids` 必须一致且包含各主块。原生 compiler 仅在中间投影使用 proposal key；交接原样保留验收意图、旧 ID 与 sink 字符串，不臆造旧 typed sink 分类。

每块显式填写 `delivery_potential`，提供 atoms 或合法原生 disposition；后者须有非空 `reason` 及包含自身的已知 `source_block_ids`。上下文、共享约束、其他验证、延期和排除仍保累计责任。未决或歧义即使标为非交付也继续阻断。缺验收意图或理由时保留局部提议且 `accounting_complete=false`；数量只核机械守恒。

空文件及空 JSON 对象／数组保留在文件分母内。`file_results` 须有 disposition（`context`／`rationale`／`deferred`／`out_of_scope`／`adr_owned`）、非空理由、原始 raw digest 及与退役同形的来源原字节定位依据，否则保持未决。损坏 UTF-8／JSON 明确失败。

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage account --root C:/work/newrouge --run-id source-review --scope-id reward --attempt-id account-01 --prepared logs/ci/<date>/b-route-sources/source-review/prepare-01/prepare/prepared.json --candidate logs/ci/<date>/reviewed-candidate.json
```

直接入口 `py -3 scripts/python/account_b_route_sources.py` 接受相同参数。两入口导入 owner 前就禁止字节码写入，无 `-B` 也相同。account 核准备产物、归档、完整原生解析、批正文／顺序／上下文、candidate 引用、跨批引用、最终请求测量、来源 raw 身份及 glob 成员；只调用 native compile／projection，不调用 Task closure／covered。

结尾重读全部已观察 bytes、缺失状态和 glob 成员。漂移使结论失效，定位可确定的受影响文件／块，要求新 attempt／重审。这是有界观察，不声称隔离不配合的并发写者。

## 退出码与事件

stdout 为单 JSON，help 为普通 CLI 帮助。退出 0 表示准备成功或完整机械记账成功；1 表示已定位的输入／记账阻断；2 表示参数／输出准入失败或既有 event 冲突／部分写入。准入后的成功和失败均保存 `report.json`／`event.json`；实际无法保存终态则报 `partial_write`，不声称持久化成功。

event key 为 `(run_id, scope_id, stage, attempt_id)`。完成后精确重放复验原始输入及成员，返回原报告，不重写或重复计数，跨 UTC 日期同样适用。参数、绑定内容变化或部分输出产生冲突，须用新 attempt。事件记录实测单调活动秒数、零 dispatch、复用／终止原因及 unknown 账单成本，不实现采纳 journal 或自动恢复。

Linux 明确跳过真实 Windows 路径测试；Windows 专项必须执行真实短路径／junction 并保存实际终态。Windows 中 POSIX-only 对应测试如跳过须单列，不计作通过；强制 Windows 方法不能跳过。Linux 或历史 CI 均不代证本轮 Windows。T108 历史原件缺失及 Epic1 五项 false 权限保持原样。
