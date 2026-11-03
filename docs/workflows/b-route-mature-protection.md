# B 路线成熟成果保护输入（Story 1.5）

本入口生成、复核和比较只读保护候选，供后续 Epic 2 审阅接收。Taskmaster master 仍是唯一 Task 状态权威；快照保存采集时的状态与历史定位，不成为另一套完成状态。[Story 1.5 spec](../../_bmad-output/implementation-artifacts/b-route/spec-1-5-mature-protection-and-frozen-a-input.md) 确定本次范围，[ADR-0040](../adr/ADR-0040-b-route-stages-authority-and-activation.md) 继续约束正式保护、冻结 A 和迁移启用。

实际存量的 T108 历史 summary 仍缺失，不能补造或借旧 `done` 消除。不可采纳的 Story 1.1 盘点不能认证正式保护基准。本次交付能力及保留未决项的候选；正式保护、A 资格和策略生效须另有完整有效依据及受治理提交。

## Windows 入口

在仓库根目录使用 Python 3.12 或更新版本及现有 Git。入口只执行必要的只读 Git 观察，不调用 Chapter 6、游戏、模型或规划写者；内部禁写 pycache。

```powershell
$repoRoot = (Get-Location).Path
$epics = '_bmad-output/planning-artifacts/b-route/epics.md'
$runId = 'story-1-5-capture-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
py -3.12 -B scripts/python/capture_b_route_protection.py capture --root $repoRoot --epics $epics --run-id $runId
```

如需核对一份明确指定的旧 Story 1.1 报告，使用 `--historical-inventory logs/ci/.../inventory.json`。旧报告自身 bytes、原内容身份和各输入的当前差异分别保存；旧报告只作回链，不替代重新采集的当前证明。历史报告缺失、损坏或内容身份无法复核会保留阻断。

命令向 stdout 输出单个 JSON 结果，其中 `output` 是本次实际目录。以下路径必须替换为已返回的 `snapshot.json` 路径；复核与比较也使用全新 run ID。

```powershell
$snapshot = 'logs/ci/2026-11-03/b-route-protection/example-capture/snapshot.json'
py -3.12 -B scripts/python/capture_b_route_protection.py verify --root $repoRoot --snapshot $snapshot --run-id story-1-5-verify-001
py -3.12 -B scripts/python/capture_b_route_protection.py compare --root $repoRoot --epics $epics --baseline $snapshot --run-id story-1-5-compare-001
```

`--root` 必须是 Git 仓库顶层目录，其余输入路径使用仓库相对 POSIX 拼写。run ID 只允许 1–96 个 ASCII 字母、数字、连字符或下划线，首字符须为字母或数字。现有 run 不复用、不覆盖；输入和输出拒绝 symlink、Windows reparse point／junction、路径逃逸、大小写别名及设备名。

| 命令 | 退出 0 的准确含义 | 本次保存 |
| --- | --- | --- |
| `capture` | 当前观察稳定、完整三联可重建且 Story 1.1 盘点可采纳，即 `capture_complete=true` | 当前 inventory、snapshot、raw 及 result |
| `verify` | 所给归档的 bytes、身份与派生材料可复核，`claim=protection_archive_integrity_only` | verification 及 result |
| `compare` | 旧归档可复核且本次当前采集 `capture_complete=true`，只读差异已生成 | 重新采集的当前 inventory、snapshot、raw、comparison 及 result |

输入／核验失败退出 1；参数、根目录或新输出目录准入失败退出 2。已建立 run 后的失败尽量保存 `failure.json`。公共诊断使用 `reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref` 六字段，空项显式 null；原 Story 1.1 诊断另保原形状。T108 等真实缺失令当前 `capture_complete=false` 时，capture 和 compare 均退出 1；仍保存候选、当前 raw 及能够形成的差异。`verify` 的归档完整性成功或 `stable=true` 都不把不可采纳的当前输入提升为完整保护。

## 唯一 API 与文件形状

共享实现为 `scripts/python/_b_route_protection.py`；CLI 仅封装该模块，不复制投影或身份算法。调用方将 `scripts/python` 加入 import 路径，并按仓库约定使用 `python -B`。

```python
from pathlib import Path
from _b_route_protection import (
    collect_protection, compare_protection, create_run_directory,
    task_definition_projection, triplet_definition_projection,
    verify_protection, write_capture,
)

root = Path(repo_root)
capture = collect_protection(root, epics_path, historical_inventory=None)
output = create_run_directory(root, run_id)
write_capture(output, capture)
verified = verify_protection(root, snapshot_path)
compared = compare_protection(root, snapshot_path, epics_path, historical_inventory=None)
```

`collect_protection` 返回 `ProtectionCapture(snapshot, inventory, raw_files, root)`；`raw_files` 是原仓库路径到真实 bytes 的映射，`root: Path` 仅是运行时写入边界，不写入 snapshot。可选 `between_reads` 是测试漂移注入 seam。`compare_protection` 返回 `ProtectionComparison(current, report)`，其中 `current` 仍是一次独立当前采集。`verify_protection` 返回结构化 dict。纯投影 API 接 Task 对象或 `{master, back, gameplay}` 三联对象，返回副本；错误抛出带公共 Diagnostic 的 `CodecError`。`write_capture` 强制输出位于该 capture 同一 root 下的 `logs/ci/`，核对全部祖先无 reparse／链接，只接受已新建的空目录，独占创建各文件。 根目录既存的 8.3／long 名别名按 `samefile` 证明物理身份；先检查原 root／output 全部祖先，再保留根下原拼写校验，不先 resolve 隐藏链接，也不放宽相对输入的拼写规则。

CLI 输出固定在 `logs/ci/<UTC-date>/b-route-protection/<run-id>/`：

| 文件 | 内容与身份 |
| --- | --- |
| `inventory.json` | 复用 Story 1.1 重新双采的完整派生报告，保留原诊断、引用闭包、累计 manifest 和 Git 观察 |
| `snapshot.json` | `schema_version=newrouge.b-route-protection-snapshot.v1`；包含内容／投影 codec、唯一状态权威、collection、inventory 身份、raw 索引、三联、逐 Task、累计义务、冻结候选、历史差异、诊断、限制及授权 false |
| `raw/<sha256-hex>.bin` | 每个实际取得文件的原 bytes，按 raw digest 去重；原路径、角色、长度及归档路径保存在 snapshot 索引中 |
| `result.json` | CLI 结果及本次目录；不能充当正式采纳证明 |
| `verification.json`／`comparison.json` | 对应命令的归档核验或只读差异；compare 目录中的 snapshot/raw 始终属于本次当前采集 |

`snapshot.raw_files[]` 保留 `path`、`exists`、`raw_digest`、`canonical_digest`、`size_bytes`、`artifact`、`roles`。缺失输入保留定位与 null 身份，不制造替代 bytes。raw 身份覆盖全部原始 bytes；仅可严格解码的 JSON 另有 canonical 身份。`snapshot_digest` 是除该字段自身外的快照 canonical digest，采集事件也参与其中，不能作为跨采集语义复用键。

Story 1.1 内存报告的 discovery tuple 仅按其原持久 JSON 合同转换为数组；这是新派生报告的传输形状。任何 Task、来源、测试、manifest、旧报告或历史文件都从安全 reader 重新取得真实 bytes，再核对盘点 raw 身份并末次重读。不会把 parsed document 的 JSON 序列化结果冒充原文件。双读可发现观察到的漂移，不提供外部写者隔离或全项目锁。

## 定义、状态和累计保护

投影标识 `newrouge.b-route-task-definition.v1` 由 `_b_route_codec.PROJECTION_CODEC` 唯一拥有，`_b_route_records.PROJECTION_CODEC` 保留原别名。仅删除真实 Task 行及其直接 `subtasks[]` 成员的 `status`；更深层 status、history、Acceptance、依赖、来源、责任、`semantic_review_tier`、未知字段和数组顺序均保留。三联 envelope 原样保留。master 的整数 ID 与业务视图原始 `taskmaster_id` 严格 join；拒绝 bool／字符串／浮点转换、重复和孤儿，每个 master 至少有一个业务视图映射。

`triplet` 保存完整原对象、整体定义投影和状态差异。`tasks[]` 按原 master 顺序保存 `task_id`、master／back／gameplay 的 `definition` 与 `state`、各自 digest、原 locator 及来源／测试／历史引用。状态合法推进只改变 state/raw；其他定义变化进入 definition。逐 Task 身份只包含本 Task 对应行，其他 Task 的无关变化不会使其定义身份连带变化。

`cumulative[]` 保存每份 manifest 的完整 `document`、原路径、raw 与 canonical digest。Flow、test、handoff、Task 映射、lineage、未知字段及 `coverage.excluded_claims` 人工限制均保留。比较分别列出 Task definition、Task state、raw 文件、整体三联定义、来源／测试／历史引用及完整 manifest 差异。累计削弱复用既有 `_weakens_baseline` 规则；人工限制改写另列 `manual_limits_changed`，旧对象变化要求有来源支持的显式审阅。输出始终 `source_backed_review_verified=false`、`apply_authorized=false`，不执行 `apply_delta`，旧 done 不满足新增责任。

旧 snapshot 缺失、损坏或被后编辑时，compare 仍先采集并保存当前状态/raw，旧材料不可比较的原因另行报告。复核从归档 raw 重建定义、状态、manifest 和冻结候选，并核对完整索引；来源／测试／历史引用关系从原 Task 和 manifest bytes 复用 Story 1.1 的 locator 规则重建，不直接信任 inventory 自报引用。完成派生核验后，再次读取 snapshot、inventory 和全部实际归档 artifact，观察到任一变化即拒绝稳定结论；仅重新计算 snapshot 自报 checksum 不能绕过这些核验。复核旧归档不会宣称当前工作区仍与其相同，需要当前差异时使用 compare。

## 冻结候选与后续接收

`frozen_a.candidates[]` 为每个真实 Task 保留定义身份、`source_scope`、旧 implement／resume／route 入口候选及 raw 身份、`review_basis` 和阻断原因。旧操作项只是候选，均 `authorized=false`。缺少完整已提交反向治理证明时，每项均 `status=blocked`、`a_eligible=false`；缺来源或历史的 Task 另保相应阻断。当前没有 policy／catalog／origins 不证明 legacy，自报 reviewed、标签和旧 done 均不能授予资格。

完整三联确实为空时，`task_set=verified-empty`、候选为空；三联不可证明时是 `task_set=unproven`、`candidate_count=null`，不得把错误伪装为零 Task。空 Task 形状与完整采集分开判断：继承的 Story 1.1 manifest 静态规则仍需满足，无 Task 不豁免累计输入缺口，也不应为此伪造 Task。

所有结果的 `authorization` 五项 `formal_protection_baseline`、`frozen_a`、`write`、`policy_bootstrap`、`target_projection_verified` 均为 false。本实现不生成 policy、origins、catalog、journal 或 receipt。纯保护投影实现不扩展 Story 1.4 的 receipt 证明；其 `target_projection_verified=false` 继续有效，`frozen_a_inventory` owner 只核 locator／raw。

`docs/planning/b-route/protection-input.v1.json` 由 root 在实际审阅后保存最小版本、来源／身份引用、逐 Task 候选、审阅结果、未决项及 Epic 2 接收条件。完整采集仍留 logs；该最小材料是 external owner 输入，不增加第七类 policy 或新的状态权威。Epic 2 必须重新核对当前来源／定义／累计义务，处理 T108 等历史限制，并按所属 Story 交付已提交反向关系及受治理提交服务，才能判断后续接收／正式发布资格。

## 定向验证

```powershell
py -3.12 -B -m unittest discover -s scripts/python/tests -p test_b_route_protection.py -v
py -3.12 -B -m unittest discover -s scripts/python/tests -p test_b_route_codec.py -v
py -3.12 -B -m unittest discover -s scripts/python/tests -p test_b_route_records.py -v
```

Linux 每套预算 180 秒；Windows 保护 suite 240 秒并逐方法记录实测时间，codec／records 各 180 秒，整 job 10 分钟／内部 480 秒不变。CLI 验证覆盖正负参数、重复 run、重采／比较和输入 raw 不变。Linux 结果与真实 Windows 结果分别留证，必需平台项 skip 不算通过。Windows 专项由 root 按 spec 管理独立 test 分支与 10 分钟 job，检出事件 SHA、仅 `contents: read`，只上传合成 fixture 证据；本说明不声明其已执行或通过。内部原始日志留本地，不随文档发布。
