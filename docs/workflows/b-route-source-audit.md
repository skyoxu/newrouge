# B 路线 3A 独立来源审计

`_b_route_source_audit.py` 是审计 owner，通过既有 `account_b_route_sources.py` 与 `dev_cli.py b-route-sources --stage audit|verify` 进入。来源 prepare／account 仍由 `_b_route_sources.py` 唯一拥有；其共享只读接口重新验证终态 event、全部产物、原字节／glob、原生完整解析、注册推导和机械 accounting。合法但仍含 unresolved 的 account 可以进入审计，其未决项始终进入最终阻断。

本入口不需要 Task、Chapter 5 readiness 或所选 Flow。只写新 logs 和同一 run 的预算证据；不写来源注册、累计 manifest、Task 三联、游戏、正式规划记录、Knowledge stable 或旧 proof，不启用默认 B。T108 历史证据缺失、正式保护资格及 Epic 1 五项 false 权限保持不变。

## 两步独立性

1. 每个完整来源文件在 fresh 无工具 runner 会话中独立提取。请求含该文件全部原 bytes（base64）、原文、原生块和顺序，不含首投影。空文件也进入文件分母。
2. 全局比较在另一个 fresh 无工具会话中读取全部原文、全部 extraction、完整首投影、验收意图及去向。全局依赖是全部来源，不能只看已引用的 Requirement／Flow／Task。完整请求无法容纳时直接 capacity 阻断，不截断、不替换摘要。

模型提供义务、遗漏／冲突／未知等 finding 和明确的 disposition 审阅。协调器严格复验 JSON schema、逐文件／逐块／逐义务分母及顺序、已存在提议 ID、原字节 digest、精确 UTF-8 byte range 与 quote、块内定位、责任和阻断分类。完全未投影可使用空 `affected_proposal_ids` 并设 `unprojected=true`。模型自报 approved／PASS 不授予资格；额外 schema 字段直接拒绝。延期／范围外接受必须附来源原文依据及独立审阅理由。机器只能证明结构、定位和执行完整性，不能证明任意业务语义正确。

## 运行

Windows Python 3.12+，使用仓库 B 路线依赖安装合同（`requirements-b-route.txt`）。runner、accounted、audit-ref 都采用精确仓库相对 POSIX 路径；根短路径按既有合同解析为真实根，后代别名、symlink 和 junction 拒绝。attempt-id 不得使用预算目录保留名 `reservations`。显式选择可信本地 runner；其 transitive Python 源码、相关可执行文件、Python 与结果相关依赖版本均绑定到审计 identity。

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage audit --root C:/work/newrouge --run-id reward-audit --scope-id reward --attempt-id audit-01 --accounted logs/ci/<date>/b-route-sources/source-review/account-01/account/report.json --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>
```

`--expected-model` 必须与可信 runner receipt 的实际 `model_identity` 完全相等（包括有值的 provider 前缀）；不接受 `environment-default` 或 `default` 代称。`--describe` 只证明 runner 合同，不能证明认证或模型调用成功。每次执行须有协调器捕获的 OS 完成结果、实际模型 identity evidence、无工具 receipt、单次完成／dispatch 计数及精确输出。失败或观察不到 provider dispatch 时写 `unknown`，不冒称零调用或已知账单。

每个 audit step 仅将 `input.json`、`schema.json`、`prompt.txt` 放入固定受限 workspace，再使用公共隔离 runner 生命周期。保存完整最终可见 request、schema、prompt、measurement、原始模型 output bytes、OS stdout 原 bytes／returncode／耗时、receipt 和 reservation。模型调用期间不持全局 metadata 锁。

输出为独占目录 `logs/ci/<UTC-date>/b-route-source-audit/<run-id>/<attempt-id>/`。`report.json` 中：

| 字段 | 含义 |
| --- | --- |
| `execution_complete` | 所有完整 extraction 和全局 comparison 已通过协调器复验 |
| `semantic_blockers` | 原 account 全部未决，加独立语义 finding；有项即阻断 |
| `planning_eligible` | 当前原文／规则有效、真实模型执行完整且无阻断；不等于正式采纳 |
| `evidence_class` | `real_model`／`synthetic`／`unverified`，明确证明范围 |
| `formal_adoption` | 始终 false |
| `runner_dispatch_count` | 本次实际启动的 runner 次数 |
| `model_dispatch_count` | 本次可观察的真实模型 dispatch 数；不可知则 unknown |
| `synthetic_dispatch_count` | 本次受控 fixture dispatch 数，不计真实模型调用 |
| `active_elapsed_seconds` | 实测单调活动耗时，非账单 |

有 findings 的报告仍可证明执行完整并定位问题，但不能作为有效 3A 规划准入。

## 预算与停止

`--request-budget` 默认 32；`--active-budget-seconds` 默认 3600；`--timeout-seconds` 默认 300。前两者在 run／scope 首次进入时持久固定，跨日期、attempt 和进程不能增加、归零或并发超支。run 只对应一个 scope。每次调用在短 metadata 保护下排他追加不可退还 reservation；失败／unknown 不退账。每次预留 1 request 和 timeout + 30 秒（包含终止／捕获余量），它是保守许可，不是实际耗时或成本。metadata 保护忙或遗留时 fail closed，不擅自清锁。

`--transport-max-bytes` 默认 1048576，`--transport-max-input-tokens` 默认 96000；实际最终可见请求含完整 schema 与 wrapper，经现有 measurer 预检。全部原文的全局下界也在任何模型 dispatch 前预检；加入 extraction 后再测真实完整请求，超限保留已发生调用并明确 capacity 阻断。

终止分别记录 capacity、budget、time、execution、input 或 semantic 阻断；无法持久化终态则显式 `partial_write`。stdout 单 JSON；0 表示有效无语义阻断的执行／复验（synthetic 仍不授规划资格），1 表示已定位阻断，2 表示参数／输出冲突。event 相同则复验原输入、旧产物及当前工具后返回原报告，不重写、不重新预留／dispatch；partial 或不同参数不能重放。

## 完成复用与只读复验

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage audit --root C:/work/newrouge --run-id reward-audit --scope-id reward --attempt-id audit-02 --accounted <current-account-report.json> --audit-ref <completed-audit-report.json> --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>

py -3 scripts/python/dev_cli.py b-route-sources --stage verify --root C:/work/newrouge --run-id verify-reward --scope-id reward --attempt-id verify-01 --audit-ref <completed-audit-report.json> --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>
```

显式 audit-ref 先重新验证原所有 proof、冻结原始输入、原生机械 accounting、每个模型输出、实际执行／receipt、保留的预算许可及原模型身份。缺失、损坏、partial、失败不按 cache miss 悄悄重跑。

全部输入及相关规则／工具一致时零 dispatch 复用。仅来源变化时，完整未变文件的原 extraction 可以复用；变更文件重新提取，全局比较始终重做。只改首投影可复用全部 extraction，重新全局比较。parser、审计 schema／prompt、相关 owner、transitive runner bytes、Python／相关依赖版本、指定模型及原实际模型 identity 改变，拒绝旧引用并要求显式 fresh audit。无关 HEAD、Task status 和时间戳不是有效性条件。

verify 不调用 runner，不刷新 readiness；它新建自身只读验证事件，核对原完整 proof 和当前来源／提议／工具规则身份。有阻断仍返回可定位报告但退出 1。它不修改或覆盖原审计。

## Synthetic 与实际验收

`scripts/python/tests/fixtures/b_route_audit_synthetic_runner.py` 是明确标记的 OS 编排 fixture，身份 `synthetic/source-audit-v1`，没有调用任何真实模型。它只用于检查独立 workspace、子进程、原字节引用／schema／分母、预算、失败和复用。其 `evidence_class=synthetic`，`planning_eligible=false`，不能代替真实模型发现遗漏／跨来源冲突的验收。

定向测试为 `test_b_route_source_audit.py`、`test_b_route_sources.py` 和共享 runner 生命周期相关已有回归。Windows 必须实际执行 `test_windows_audit_real_junction_and_short_path_rejected` 及旧来源路径方法；Linux skip 单列，不代证 Windows。实际模型后端不可用时保留其真实阻塞与原始日志，不手填语义 PASS。

3A 证据交给后续 3B 和 Chapter 5。Chapter 5 仍须核对真实 Task Acceptance、ADR、Overlay、契约、依赖和绑定；来源审计不免除实施定义或 readiness 审查。
