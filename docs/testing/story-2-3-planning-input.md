# Story 2.3：Task 无关的完整规划输入

本 Story 只实现正式 3B 的 prepare、只读重验及后继请求构造。它不执行模型、不生成或采纳候选、不分配正式 ID、不写正式 B 领域记录、旧 `run.json`、Task、readiness 或恢复／apply journal。默认入口仍使用 legacy 后置合同。Story 2.4–2.10 的语义生成、评选、采纳和集成保持后续范围。

## 单一 owner 与 CLI

`scripts/python/_b_route_planning_input.py` 是两个 prepare 的唯一 3B 输入 owner。直接脚本在任何旧 Task scope、Chapter 5 readiness、MVG capabilities／manifest 检查之前转入它。`dev_cli.py` 只转发到同一脚本，沿用当前 Python 解释器和绝对脚本路径。

```powershell
py -3 scripts/python/plan_capabilities.py --repo-root . prepare --run-id planning-3b --input-stage 3b --planning-contract logs/ci/<date>/planning-contract.json
py -3 scripts/python/plan_mvg.py --repo-root . prepare --run-id planning-3b --input-stage 3b --planning-contract logs/ci/<date>/planning-contract.json
py -3 scripts/python/dev_cli.py plan-capabilities --stage prepare --run-id planning-3b --input-stage 3b --planning-contract logs/ci/<date>/planning-contract.json
py -3 scripts/python/dev_cli.py plan-mvg --stage prepare --run-id planning-3b --input-stage 3b --planning-contract logs/ci/<date>/planning-contract.json
```

`--input-stage` 缺省为 `legacy`。本 Story 的输入合同只属于 prepare；合同不能在缺省 legacy 下使用，也不能在 generate／apply 等阶段被静默忽略。后续 [Story 2.4](story-2-4-flow-candidates.md) 仅沿 Capability validate-candidate／MVG validate 增加显式 3b 完整候选读取，使用 prepared-ref/candidate，仍共用本 owner 的默认当前重验和原 DRAFT 链检查，不构造下一次请求。3b 拒绝 Task ID、allow-unready，以及 MVG capabilities／manifest／evidence-ref／run-invocation-limit 等混合门禁。legacy MVG prepare 仍要求 capabilities 和 manifest，其他 legacy 阶段及 receipt／resume-evidence 验证逻辑保持原合同。

## 阶段合同

合同采用严格 UTF-8 JSON；重复键、非法编码、未知合同字段、未知类别或格式均阻断。下面的 schema 是 prepare 日志封装，不是新增第七类正式领域 schema。

```json
{
  "schema_version": "newrouge.b-route-planning-contract.v1",
  "input_stage": "3b",
  "audit_ref": "logs/ci/<date>/b-route-source-audit/<run>/<attempt>/report.json",
  "scope": {"scope_id": "reward", "kind": "all", "ids": []},
  "constraints": [{"path": "docs/prd/reward-constraints.md", "format": "text"}],
  "contexts": [
    {"kind": "shared_capability", "path": "docs/planning/shared.json", "required": true, "format": "json", "absence": null},
    {"kind": "implementation", "path": "Game.Core/Reward/NewRule.cs", "required": false, "format": "text", "absence": {"reason": "This declared implementation location does not exist yet."}}
  ],
  "limits": {"max_bytes": 1048576, "max_input_tokens": 96000, "reserved_tokens": 2000}
}
```

scope 必须与原审计 scope 相同。全范围使用 `all` 和空 IDs；局部选择使用 `capability` 或 `flow` 和非空原有 ID 列表。constraints 必须是非空列表，逐项原文非空；JSON 约束还要求非空对象／数组。contexts 显式列出实现、共享能力、Capability、Flow、Task 或治理对象，类别依次为 `implementation`、`shared_capability`、`capability`、`flow`、`task`、`governance`，格式为 `text` 或 `json`。JSON 复用上下文要求完整对象／数组，未知嵌套字段、原始 ID、CRLF、尾随空格与原字节完整保留。

只有 optional 项可以提供非空 reason 的 absence；声明后必须验证该精确路径不存在。没有 absence 的条目必须存在，即使 required 为 false。可选缺席的理由、路径、存在性及内容都参与身份。路径统一使用精确仓库相对 POSIX 拼写，拒绝目录逃逸、绝对路径、Windows 大小写／短名别名和 junction／symlink 后代。不会搜索猜测未声明的实现或 Task，也不读取旧 readiness／不完整 MVG 中间态作为准入。

## 审计与闭包

`audit.verify_current_proof` 先用现有 `validate_proof` 重建完整历史 proof、原 batch、严格输出与执行 receipt，再按原 request 的 runner／expected_model 验证当前工具、规则、依赖与完整来源／记账。合同不能提供资格布尔值、替换 runner 或改变原执行记录的模型配置及证据范围；本轮官方 Codex 证据只核验运行时配置，服务端实际模型及物理请求数未知。3B 重新组合原 unresolved 和独立 findings，要求执行完整、真实模型证据、无阻断；synthetic 永不授准入。提取后的只读接口不会调用 audit execute，也不创建审计或预算事件。

局部闭包只接受**已独立审计的完整原始 JSON 来源**中的 `planning_relations`，不会信任调用方或复用上下文自报的依赖子集：

```json
{
  "planning_relations": {
    "schema_version": "newrouge.b-route-planning-relations.v1",
    "dependency_coverage": "complete",
    "entities": [
      {"kind": "capability", "id": "CAP-EXISTING", "source_paths": ["docs/reward.md"], "source_block_ids": [], "depends_on": [{"kind": "flow", "id": "FLOW-SHARED"}]},
      {"kind": "flow", "id": "FLOW-SHARED", "source_paths": ["docs/shared.md"], "source_block_ids": [], "depends_on": []}
    ]
  }
}
```

此结构只是输入中的治理证据，不会创建正式记录。每个节点必须有已审计来源，块必须在相应原文件中；记录路径、raw digest 和 JSON Pointer 一起冻结。按原 ID 遍历完整传递依赖，允许循环但不重复消费。关系来源本身总是适用。缺少完整关系、未知字段／实体／依赖、冲突或无法验证的来源关系均保守扩大至完整审计范围，并记录原因。该机制验证结构与原文回链；关系声明的业务完备性仍依赖独立审计，不能宣称机器证明任意业务语义。

局部原文投影不会缩小全局分母：完整 Ledger／manifest、首投影及提案、accounting／守恒信息、独立 extraction／comparison／原报告／工具身份和跨批义务仍在每次请求的 core 中。原审计执行 proof 与相关日志的全部原始字节保留在本地 raw-index／归档，逐文件哈希和字节数绑定输入，并由正式 loader 完整复验；模型接收完整语义审计对象和可核验的原证明库存。Story 2.5 的真实容量核算修正了早期把执行日志反复 base64 嵌入业务请求的传输选择：新材料声明 `host-verified-archive.v1`，不删原证明、不截断业务原文或语义对象；显式声明的必需日志上下文仍完整发送。旧 inline `archive:base64/` 材料仍按原格式只读重建与核验。

## 身份、独占日志与重验

内容身份包含合同原字节、所有声明输入及缺席、完整审计、source glob 成员、codec、相关传递源码／运行时／依赖版本、完整输出 schema、容量与 reserve。无关 Git HEAD 和未声明 Task status 不参与身份。相关来源变化可能首先使上游审计失效；此时必须显式重新取得合格审计，不能伪造新 proof。

成功目录为 `logs/ci/<UTC-date>/b-route-planning-input/<run-id>/<content-digest>/`，同 run 的相同完成身份跨日期只读复用。相关变化使用新内容目录，并逐项列出失效依赖与受影响的冻结输入、批次、后继请求和 synthesis。失败使用新独占事件；已完成或半写材料均不覆盖／修复。`event.json` 最后写入，绑定完整输出清单与字节 digest。终态写失败返回 partial_write 和恢复位置，后续不能把它当成功。

目录保存原始输入快照、完整 raw-index／归档、prepared、schema、逐批模板、最终 wrapper 的实测容量与逐对象重建证明。`load_prepared(root, prepared_ref)` 只读验证全部产物、原归档分母、原请求模板、覆盖／重建和当前准入／依赖，不会写日志或补文件。`revalidate=False` 仅用于历史材料检查和失效诊断；正式后继构造使用默认当前重验。

## 有界后继请求

`plan_batches` 复用既有传输 part／coverage 检查和最终 `measure_request`，不使用过滤型 model_context／model_projection 或 Task-dependent blinded bundle。按完整最终 prompt、input、schema 与 reserve 测量，先检查不可分 core，合法大原文／结构对象允许按精确字符地址无损分片。全局 proof、完整库存和跨批义务每次重带。

新材料用现有 request-local lossless codec 编码完整 core，并显式标记 `core_encoding`；定义、共享引用和完整恢复规则均在当前请求中。冻结 plan 仍保存未编码原对象，解码后每一字段、JSON 类型、未知字段、数组顺序与原值必须完全相等。此项只消除重复传输，不缩小来源或证明分母；旧无标记 plain 请求保持原字节重建。

prepare 保存的是明确标记的**模板和容量下界**，后续批次尚没有真实前序草案，不能直接当执行请求。`build_request(frozen, batch_ordinal=N, previous_drafts=[...])` 要求全部 N−1 个完整前序草案及有序 parent identity。`build_request(frozen, previous_drafts=[...])` 构造 synthesis，要求全部 batch 草案，重新携带适用完整原文／对象和全部先前 synthesis 草案，完整测量实际返回内容。缺草案、错身份或超限均停止；不截断、重新摘要或增加预算。

推荐后继 owner 调用 `prepare_successor(root, prepared_ref, ...)`：先当前只读重验，然后在新的 `successors/<unique-event>/` 保存完整 drafts、每个实际字节尺寸／identity、完整最终 request、测量或超限原因及 report resume_ref。它只构造请求，不执行模型，也不创建第二套预算或恢复 journal。完整原文加实际草案无法放入同一 synthesis 请求时即容量阻断；本 Story 不承诺任意大范围都可完成生成。

## 已执行验证与限制

新矩阵的阳性测试显式替换只读 audit seam，只证明输入组装、容量、缓存和 CLI 路由；不会把它称为真实审计通过。另用原始 synthetic OS proof 检查真实重验后的拒绝，并单列 CLI Python 子进程和 Windows OS 路径探针，正式 prepare 无 runner／模型调用。离线 harness 阻断 socket connect，使用已有任务独立依赖／tokenizer cache，绝不重复安装或改 ACL。

两份真实 `story22-real-omission-20261105/audit-04` 与 `story22-real-conflict-20261105/audit-04` 的历史完整 proof 已重建，原始 blocking findings 和所有历史字节保留。当前身份因相关源码变化失效，prepare 明确拒绝。证据：`logs/ci/2026-11-05/story23-real-negative/verify-01/verification.json`，两项真实模型与 runner 子进程计数均为零。没有合格真实阳性材料，本 Story 不发送新的真实请求，因此真实阳性准入仍未验证。

普通受限 token 的 mode700 临时目录权限失败报告永久保留；已按授权提权执行，不修改 ACL。所有报告位于 `logs/ci/2026-11-05/story23-tests/<label>.json` 和 `.log`，从不覆盖标签。

| 标签 | 执行 | failure | error | skip | 说明 |
| --- | ---: | ---: | ---: | ---: | --- |
| story23-first-matrix | 29 | 0 | 38 | 0 | 普通 token 的临时目录权限失败；包含 cleanup error |
| story23-matrix-elevated-01 | 29 | 1 | 1 | 0 | 首轮测试边界问题：Git provenance 误判为 runner，根祖先短名 relative_to |
| story23-matrix-elevated-02 | 33 | 0 | 0 | 0 | 修正测试边界后的新矩阵和 CLI |
| story23-final-matrix-03 | 128 | 0 | 0 | 0 | 新矩阵、CLI、实际 B-route records 模块 |
| story23-frozen-delivery-04 | 35 | 0 | 0 | 0 | 冻结 delivery 历史重验及精确 schema 失效 |
| story23-root-alias-05 | 15 | 0 | 0 | 0 | 最终源码的真实 Windows 根 junction、两个入口路由和 CLI |
| story23-legacy-and-3a-01 | 524 | 6 | 13 | 2 | 较广旧回归未全绿；完整原文保留，不能表述为通过 |
| story23-audit-stable-recheck-06 | 2 | 0 | 0 | 0 | 源码冻结后的两项 3A synthetic 定向重验 |

每项报告的真实模型计数均为零。failure／error 包含 unittest subtest 事件，不能简单相减当作精确通过项数。第二轮以后使用：

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B .\run_story23_tests.py <unique-label> test_b_route_planning_input test_planning_dev_cli
```

较广回归实际选择：`test_b_route_sources`、`test_b_route_source_audit`、`test_b_route_codec`、误列不存在的 `test_b_route_schema`、`test_capability_planning_contract`、`test_capability_input_integrity`、`test_capability_staged_synthesis`、`test_capability_task_evidence`、`test_capability_incumbent_review`、`test_mvg_planning_contract`、`test_mvg_input_envelope`、`test_mvg_planning_boundary_independent`、`test_mvg_evidence_transport`、`test_mvg_dispatch_identity`、`test_mvg_planning_completion`、`test_mvg_review_regressions`。误列模块没有执行领域测试；正确的 `test_b_route_records` 已在 128 项报告中通过。

该回归已知现象包括 Windows cmd 输出按 UTF-8 解码的 readerthread 异常、长临时路径下临时文件不存在、API 模拟响应的实际模型证据校验失败及并发 fixture 时序差异。两项审计 failure 在实现源码变化期间出现，源码冻结后定向重验 2/2 通过。这些现象除不存在的模块和直接观测到的解码错误外，尚未做隔离基线对照，不宣称为既有缺陷，也不宣称本 Story 回归无风险。未为了消除噪声改动无关旧测试。两项 skip 分别是 POSIX symlink 对应测试及缺少本地真实失败 source-batch 材料。

官方 runner/backend 引用的测试使用 preflight、mock dispatch、API response stub 或临时假 runner；3A OS 编排使用显式 synthetic fixture。没有启动现有官方模型 CLI/backend。逐项保留全部 6 failure／13 error 测试名、原文及目前分类的索引为 `story23-legacy-and-3a-01-triage.json`。主线程已确认本次 `-X utf8` 与上一轮 harness 的 OEM 解码差异，将独立处理无源码改动的验证命令／短临时路径复验及必要基线对照。本实现代理不再启动额外回归；Story 原生状态保持 in-progress，尚未完成独立 Step4／Step5。

主线程已完成环境与基线对照：`story23-stable-environment-07` 在源码冻结、UTF-8 mode=0 和私有短临时目录下执行 50 项，无 skip；其中新矩阵／CLI 全部通过，仍有 2 failure／4 error。独立 detached worktree `task/b23-baseline` 的 HEAD 为 `2d3d3ba7e81dd21ca559614f599e8c633e65945b`，同依赖、同短临时根执行这 6 项，得到相同的 2 failure／4 error 及错误类型／调用位置，见 `story23-baseline-comparison-08`。因此这 6 项是在本环境可复现的基线问题，尚未修复，不能把旧全套回归称为通过。

Story 2.3 明确要求的 legacy readiness／draft、Capability resume-evidence、完整 receipt／模型配置绑定、apply 阻断和预算门禁已在最终源码下单独验证：`story23-legacy-gates-09` 共 14/14 通过，无 skip、无真实模型调用。旧失败、初始 harness 问题和真实阳性缺口均继续保留；它们不被定向通过结果抹去。

## 原生审核与最终相关验证

三层原生审核逐项裁定 16 条：13 条合并为 9 个修复根因，2 条驳回，1 条真实阳性验证缺口延期。修复包括重复长块的按 offset 重建、不会与真实仓库路径冲突的 `archive:base64/` 内部标记、未知治理类型回退、当前身份在发布末尾重验、历史字节／原请求完整性与当前容量分离、拒绝路径的旧准备失效引用，以及 prepare／successor 写失败的独占诊断与诚实恢复位置。诊断本身也不可持久化时，返回空 `resume_ref` 和具体 `partial_ref`，不把原成功形态 report 冒充失败诊断。没有新增公共恢复 loader 或领域 schema 门槛。

多批回归现实际通过 `prepare_successor` 构造第 2、3 批请求，读取保存的 `request.json` 验证全部完整前序草案、身份、payload 测量及 UTF-8 字节长度。定向 `story23-review-fixes-01` 为 31/31 通过；主线程 `story23-root-final-10` 执行 274 项，0 failure/error，1 项 POSIX 对应测试 skip，Windows 实际 junction／短路径项通过，真实模型调用 0。`story23-root-final-10-source.json` 记录相关 8 个源码文件测试前后哈希一致。

原边界审核方已复核其 4 项关闭，验证缺口审核方已确认后续批次断言能检出丢草案突变。完整矩阵及修复映射为 `logs/ci/2026-11-05/b-route-story-2-3-build/matrix-audit-02-final.json`。spec 按原生 Step5 标为 done，sprint 视图标为 review；真实阳性准入和六项旧基线失败仍按上述边界保留，未推送或合并。
