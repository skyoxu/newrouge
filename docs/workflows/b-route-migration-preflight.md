# B 路线只读迁移预检

Story 1.6 提供 `b-route-preflight`，比较明确候选与当前工作区，保留成熟 Task 身份、当前状态、历史和累计义务。依据是 [ADR-0040](../adr/ADR-0040-b-route-stages-authority-and-activation.md)、唯一 codec／六 schema 与 Story 1.5 保护输入。预览可用不表示来源语义已审、正式保护认证、冻结 A、采纳发布、Task readiness、游戏验收或默认 B 启用。

## 公共入口与返回约定

在仓库根目录使用 Python 3.12 或更新版本。六个参数都必须显式提供，输入路径采用仓库相对 POSIX 拼写，根目录可以是 Windows 原生路径。

```powershell
py -3 -B scripts/python/dev_cli.py b-route-preflight --help
py -3 -B scripts/python/preflight_b_route_migration.py --help
py -3 -B scripts/python/dev_cli.py b-route-preflight `
  --root (Get-Location).Path `
  --epics _bmad-output/planning-artifacts/b-route/epics.md `
  --protection-input docs/planning/b-route/protection-input.v1.json `
  --candidate logs/ci/my-review/candidate.json `
  --intents logs/ci/my-review/intents.json `
  --run-id my-reviewed-preview-001
$code = $LASTEXITCODE
```

直接 owner 入口 `preflight_b_route_migration.py` 使用完全相同的参数及服务。公共 CLI 对此命令局部路由，不经会向 stdout 打印命令的通用 runner。普通执行仅输出一份 JSON；help 保留 argparse 的英文帮助。没有 apply 参数。

| 退出码 | 含义 |
| --- | --- |
| 0 | 本次稳定的机器预览可审阅；语义来源支持及外部审阅仍未核验，不授予写入或启用权限 |
| 1 | 必需输入缺失／损坏／未知、迁移冲突、未决语义、pending 或观察漂移 |
| 2 | 命令参数不合法、新输出目录不准入或报告无法独占创建 |

报告写入全新的 `logs/ci/<UTC-date>/b-route-preflight/<run-id>/report.json`；已有 run-id 拒绝覆盖。命令参数错误没有报告目录。失败诊断统一是 codec 的 `reason_code / stage / entity_id / expected / actual / resume_ref` 六字段，不另建枚举。不生成候选、不调用模型／旧 compiler／apply／恢复写者／Chapter 6／游戏，不写 Task、正式规划、manifest 或发布指针，不生成 pycache。

## 输入与原始身份

候选载体沿用 Story 1.4 的唯一外层形状，无隐式默认值：

```json
{
  "records": [
    {
      "path": "docs/planning/b-route/plans/example/1.json",
      "source_path": "logs/ci/my-review/original-plan.json"
    }
  ]
}
```

`path` 是逻辑目标，`source_path` 是完整原始 bytes 的位置，两者独立。重复逻辑目标、大小写别名、根外路径、符号链接／reparse point、Windows 设备别名及损坏 JSON 均阻断。可提供六类记录、Task 三联、累计 manifest、来源集合及明确的原始来源文件；注册来源可在 `docs/**` 外，不另造来源根目录限制。Task 或 manifest 不强套 B schema。提供三联时必须三份完整；未提供三联时使用当前三份原始 bytes，不补 status、不转换 ID、不把 retire 改成 cancelled。

`--protection-input` 必须是 `newrouge.b-route-protection-input.v1`，绑定可重建的 snapshot／inventory／归档、精确投影 codec、原始 review locator 及 manifest 身份。五项 authorization 必须保持 false。保护归档经 1.5 原验证器从 bytes 重建；不能用候选自报 digest 代替原件。归档到当前工作区的差异单独报告，当前到候选的差异另列；status 合法推进不构成定义变化，候选仍必须保留本次读到的每一项状态。

当前仓库的 T108 必需历史原件 `logs/ci/2026-05-06/sc-build-tdd/summary.json` 仍缺失。版本化 1.5 输入也不使其变 optional；归档或原证据缺失时，真实预检保留阻断。完整合成 fixture 证明预检能力，不能认证真实保护基准或 A 资格。

## 显式意图格式

意图是外部审阅输入，不是第七类正式治理记录。精确版本为 `newrouge.b-route-preflight-intents.v1`，顶层只允许：

| 字段 | 形状与约束 |
| --- | --- |
| `document_version` | 上述精确版本，未知版本阻断 |
| `scope_id` | 非空、无首尾空白字符串 |
| `inputs` | 仅 `epics / protection_input / inventory / targets` |
| `changes` | 意图数组，实体不得重复；所有实际变更必须双向对应 |
| `unresolved` | 未决项数组，非空会阻断本次预览 |

`inputs.epics / protection_input / inventory` 各为 `{ "path": "...", "raw_digest": "sha256:<64 lowercase hex>" }`。`inventory` 须为保护 snapshot 绑定的同一原始 inventory。`inputs.targets` 是同样的身份行数组，集合必须精确等于全部候选逻辑目标与当前三联路径；实际不存在的目标必须显式使用 null digest，不能自报不存在。重复目标或当前前像不符会阻断。

每项 `changes` 只允许以下字段：

```json
{
  "scope_id": "review-scope",
  "entity_type": "file",
  "entity_id": "docs/example-source.md",
  "operation": "new",
  "before": [],
  "after": [
    {
      "path": "docs/example-source.md",
      "json_pointer": "",
      "raw_digest": "sha256:<complete-original-candidate-digest>"
    }
  ],
  "source_refs": [
    {
      "owner": "authority",
      "ref": "docs/requirements.md#L1-L3",
      "files": [
        {"path": "docs/requirements.md", "raw_digest": "sha256:<original-source-digest>"}
      ]
    }
  ],
  "reason": "Explicit rationale for this proposed change.",
  "review_ref": {
    "owner": "authority",
    "ref": "logs/ci/my-review/review.json#/finding",
    "files": [
      {"path": "logs/ci/my-review/review.json", "raw_digest": "sha256:<original-review-digest>"}
    ]
  },
  "unresolved": []
}
```

上例 digest 是占位说明，不能直接运行。可运行的完整输入由下方专项 fixture 构造。`source_refs` 和 `review_ref` 使用公共 OwnedRef，验证实际 locator、完整 files 集合与 raw digest；文件内容自称 approved 不会变成授权。

`entity_type` 可以是 `task / file / obligation`。Task `entity_id` 必须是原正整数 ID；file 使用逻辑路径；obligation 使用 `<manifest-path>#/flows/<stable-id>` 或 `<manifest-path>#/tests/<stable-id>`。每个 locator 仅含 `path / json_pointer / raw_digest`，Task 要列出该 ID 在三联全部现存行的位置；候选 locator 的 digest 是该完整原始候选文件 bytes 的身份，path 仍为逻辑地址。文件 locator 的 pointer 为空。新增 before 为空，退役 after 为空。

`operation` 仅允许 `reuse / update / new / retire`，必须与实际定义比较相同。reuse 不允许定义变化；new 只描述已给身份，不分配 ID。已存在的 plan／binding／receipt 修订不可原地改写；policy／origins／catalog 的定义变化须保原身份且递增自身修订。候选完整三联中的 reuse 也须显式声明，无变化且未提供的当前 Task 不强制重复声明。每个变更 manifest 必须声明文件意图及每个新增／更新／退役 Flow／test 的独立 obligation 意图。三联外层 metadata／顺序变化使用 `file`、`entity_id: task-triplet-envelope`，保留全部三份文件身份。

当前成熟 ID／业务 ID、Task／subtask 状态、历史及 evidence 引用受保护，旧 done 不满足新增义务。删 B 来源／plan／binding 归属阻断。删来源、退役 Flow／test、降低累计义务即使附了 source／review locator，也仍需要独立语义审阅，不能自报已批准而放行。

## 输出审阅与治理边界

报告列出 `changes`、`cumulative_changes`、`protection_to_current`、`semantic_review_inputs`、`candidate_validation`、`governance`、`pending`、每一观察的原始身份和诊断。确定性的 `difference_identity` 不包含时间及随机 collection；重复预检不生成语义候选。语义字段 `source_semantics_verified / external_review_verified` 始终 false。

有候选 catalog 时复用唯一 `validate_bundle`；无 catalog 的前置候选只做单记录 schema／外部引用核验，明确 `relationships_verified: false`，不捏造 receipt 或 catalog。合法零 Task、3B 和 planned 对象不会被要求提供假的 readiness、场景或实现符号。原始空三联和完整归档已核验、且旧盘点唯一错误是 `missing-manifests` 时，预检明确记录无 Task 累计 manifest 的合法缺失；保留旧 capture_complete 的原值，不改写历史采集结果。任何其他采集错误仍阻断。结构结果仍不是正式提交证明。

明确未启用必须能读取 ADR 的 Accepted 正文及明确未启用依据，同时没有相反的当前治理记录或 Task B 痕迹。存在治理痕迹后，必需 policy／catalog／origins 任一缺失、损坏、未知即 `unknown_or_damaged`，不从文件缺失推 legacy，也没有 `schema.enabled` 字段。完整结构可列 `structure_valid_publication_unverified`，不授予提交或启用结论。

旧 `capability-apply.pending.json` 保留，读取其 `run_id / journal_path`、原 journal、authority 和目标，报告 `pending_unknown_scope`，阻断迁移。旧 journal 没有 scope_id；不得伪造 scope、删除 marker 换绿或调用未来 journal。报告导航回原入口：

```powershell
py -3 scripts/python/dev_cli.py plan-capabilities --stage apply --run-id <original-run-id> --confirm
```

这只是恢复定位；预检不会执行它。Capability 模型 `--resume-evidence`、MVG completed-only recovery、原 apply journal 各守自己的恢复边界。

报告形成前重读全部已观察输入、缺失项、保护引用、来源、review、候选原件、当前目标、治理与 pending，并复核治理目录成员。实际后编辑或新增治理痕迹使 `stable / conclusion_valid / ok` 为 false，诊断给出重采位置。双读只能检测观察到的漂移，不能提供文件系统事务隔离，也不能供未来写者直接复用为应用授权。

## Windows 专项与八组实际 CLI 样本

以下 PowerShell 命令实际启动公共 CLI 子进程，使用独立合成仓库，不写真实来源。每组构造完整保护归档、原 bytes 候选和意图，核对精确退出码、单 JSON stdout、stderr 为空、持久报告及全部原 bytes；只把新报告写入指定输出目录。

```powershell
py -3 -B -m unittest discover -s scripts/python/tests -p test_b_route_preflight.py -v
if ($LASTEXITCODE -ne 0) { throw 'Preflight tests failed' }
$out = 'logs/ci/story-1-6-cli-' + [guid]::NewGuid().ToString('N')
py -3 -B scripts/python/tests/test_b_route_preflight.py --cli-matrix $out
if ($LASTEXITCODE -ne 0) { throw 'CLI matrix failed' }
$summary = Get-Content "$out/summary.json" -Raw -Encoding utf8 | ConvertFrom-Json
if ($summary.case_count -ne 8) { throw 'Expected eight CLI cases' }
$summary.cases | Select-Object case, exit_code, original_bytes_unchanged, only_fresh_log_report_added
```

| case | 实际输入 | 预期退出码 |
| --- | --- | --- |
| success | 完整来源新增与显式原身份绑定 | 0 |
| missing-input | 原候选载体不存在 | 1 |
| unknown-version | 意图版本 v99 | 1 |
| path-escape | 逻辑目标 `../outside.json` | 1 |
| state-overwrite | 完整三联候选把当前 done 改成 pending | 1 |
| unsupported-retirement | 移除旧 Flow；有 locator 仍不伪造语义批准 | 1 |
| old-pending | 原 Capability marker／journal，无 scope_id | 1 |
| zero-task | 真实空三联、无假 readiness，完整保护和来源新增 | 0 |

还需由主审阅者核对当前真实仓库的受阻报告与最小 Epic2 交接。专项 fixture 通过只证明 Epic1 的预检与保护工具能力；正式采纳 publisher／journal、Task gate、游戏运行及默认 B 切换仍由后续 Epic 交付。CI 使用专用 test 分支固定 SHA、有界执行并仅上传合成报告；原始内部过程日志保留于本地 logs。
