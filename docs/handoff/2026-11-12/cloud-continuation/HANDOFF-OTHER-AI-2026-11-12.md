# NewRogue Epic 2：其他 AI 助手接续交接（2026-11-12）

## 当前指令与阅读顺序

用户因本周额度将用尽，要求停止新增业务执行、模型调用和测试，保全并提交推送现有进度，交由其他 AI 编程助手接手。本指令覆盖旧文档中的“继续执行”授权。当前只完成保全、隐私检查、文档与 Git 操作；接手助手先只读核对，得到用户恢复执行的指令后再推进。不要依据本目录历史段落自动登录、启动审阅、测试或执行业务。

先读本文件、根 `AGENTS.md`，再读 `logs/ci/2026-11-12/cloud-epic2-recovery-25/REPORT.md`、同目录 `PRESERVATION.md`、原 Story 与相关 owner 文档。`execution-plans/2026-11-11-cloud-epic2-recovery.md` 是累计执行史；其旧阻塞、预算未使用、未发布、必须 Windows 初始化等描述都有后续进展，不是当前指令。本目录旧 `MANIFEST.json` 保留最初恢复基线，不改写为本轮清单。

## 分支、提交与保全边界

- 仓库：`https://github.com/skyoxu/newrouge`。
- 唯一续接分支：`build/cloud-epic2-recovery-20261111`。不要在环境默认 main 开发，不合并 main、不 force push、不覆盖并发修改。
- 本轮开始时已在远端核实的基线：`0c4d16c1b7fa8d8302d58a6c764d481e8f9a0755`。
- 本轮源码及完整证据保全提交：`a4cced184e50c6e1d61a74ea44bb74c18f3a82af`（186 文件；Linux 窄适配、ADR0061、实际审计和失败准备原件）。本文件所在的后续文档提交是最终交接提交；用分支 HEAD 与远端核验其确切 SHA，不把前一提交当最终 HEAD。

| 已有提交 | 内容与边界 |
| --- | --- |
| `f94847e2b7b4d5092984294b46a2905212528f30` | 重建 Cloud 任务时已核实的非 main 恢复点；此前18提交已全部推送 |
| `76d3282359a931b2cd249f8dd41250d36c2bbaff` | 正式审阅修复、真实补偿发布及 continuation20–22 证据 |
| `b44d0820778711b4cb6d49e0962b85bb1ed373ca` | continuation23 跨进程公共入口观测和 m4 限制 |
| `92c5532536b77d38730c2b59e9fe5e06b4662445` | 原 Windows workflow 的固定四项窄 selector |
| `0c4d16c1b7fa8d8302d58a6c764d481e8f9a0755` | continuation24 的真实 Windows、独立克隆读取和单 Capability 来源准备/记账 |
| `a4cced184e50c6e1d61a74ea44bb74c18f3a82af` | continuation25 完整来源审计、真实容量拒绝、Linux 发布适配及停工保全 |

四个原有无关 EOL 状态路径一直没有纳入本轮提交、没有 reset/覆盖；原始 bytes 等于0c4d16c1对应 Git blob，但 Git 状态可能继续显示修改：

1. `docs/handoff/2026-11-11/archive/uncommitted-r22/_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md`
2. `docs/handoff/2026-11-11/archive/uncommitted-r60/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml`
3. `docs/handoff/2026-11-11/archive/uncommitted-r60/docs/workflows/mvg-integration-acceptance.md`
4. `workflow.md`

不要用 `git reset --hard`、`git checkout .` 或全量 add 清理它们。新环境的换行策略可能使显示不同；先比原始 bytes，不假定可以覆盖。

## 实际完成、未知与未完成

| 项目 | 当前事实 | 主要证据 |
| --- | --- | --- |
| 官方订阅认证恢复 | 之前官方设备登录 OS0、在线元数据成功；不是当前已验证的新账户会话，也没有可转移的凭据包 | continuation19–20 的非敏感报告；凭据不在 Git |
| 真实补偿 | `NativeV15Origin03Compensation01` 的 prepare/reserve/apply/verify/publish/read 都已 OS0，原操作显式 resolved_by；无 active operation/pending marker | continuation22 的 `compensation-result.json`、`final-state-audit.json`、`formal-proof-audit.json`、`published-artifacts/` |
| 正式发布状态 | `PLAN-bed480ce3e404b2cbaf5514d80a7f941` rev2，新 receipt rev1/catalog rev2；formal_adoption=true，readiness/runtime_verified/default_b_enabled=false | continuation22 的正式原件与 `publication-artifact-manifest.json` |
| 跨会话读取 | 无关 cwd 的新进程读取同一正式状态；真正9文件、无历史 logs 的 receipt-sealed clone 读取成功；另一个改 plan 副本按 digest 精确拒绝 | continuation23；continuation24 `published-clone-input/`、`real-clone-observations.json`；continuation25 `post-adapter-real-clone-read.json` |
| Windows 窄验证 | GitHub `windows-latest` run43211116759 attempt1/job131158674714，源码92c55325，四项通过、零跳过、287.578s、零模型 | continuation24 `windows-actual-summary.json`、`windows-decoded-job.log`、`windows-final-run-state.json`、`windows-artifact/` |
| 单 Capability 真实来源 | 原受控来源1文件/8块/7提议；prepare、account02成功；account01调用方 typed prepared_ref 错误完整保留 | `b-route-sources/cloud-singlecap-source-20261112/`、continuation24 `single-capability-input/` |
| 两阶段实际来源审计 | run `cloud-singlecap-audit-20261112` /scope `controlled-exclusive-resolution-v15` /audit-01；extract和compare都 OS0，public0，338.9435s；当时 eligible=true、无 semantic blockers | `b-route-source-audit/cloud-singlecap-audit-20261112/` 全部61原件；continuation25 `actual-source-audit-summary.json` |
| 正式3B准备 | run `sc25` 实际 OS1，完整 common-core 下界请求278315字节，经 UTF8 byte upper bound 加2000超过96000；在 native/model dispatch前拒绝 | continuation25 `public-3b-prepare-before-linux.stdout/.stderr`、`blocked-3b-common-core-request.txt`、`blocked-3b-request-data-provenance.json`；下文原失败目录 |
| Linux 初始化适配 | 原子不覆盖发布窄适配已实现并由干净 Astra max 独立检查，无确认 P1/P2；只涉及现有初始化发布点，Windows 路径保留 | `scripts/python/_b_route_planning_runtime.py`、ADR0061、continuation25 `independent-native-platform-assessment.md` |
| 已执行的定向测试 | 停工前5项 Linux 真文件系统/竞争进程控制通过，5项相邻 frozen-owner控制通过；不是 native/模型/完整重入证明 | continuation25 `linux-publication-targeted-01.txt`、`frozen-owner-targeted-01.txt` |
| 原始未知 | 最初补偿第二节点的 blocked/findings不一致和 unknown 记录保留；m4公共status的旧包装解析错误导致子进程 exit未保存，仍未知；provider物理请求/真实费用未知 | continuation20、23 原件；不因后续完成而抹除 |
| 未执行/未验收 | 修改源码后的新来源审计0，native调用0；未产生新的 committed 单 Capability、registry条目或跨新执行 adoption/epoch/reopen 阳性链 | continuation25 `post-adapter-evidence-state.json`；原 Story2.9仍未完成正式验收 |
| Epic 总验收 | 2.8原Windows AC5及完整前置、2.9真实完成项链、2.10全部前置/图样例/真实模型全链和Windows AC6仍未完整验收 | 原 Story 和以下下一步，不可宣布 Epic2完成 |

Windows四项是 `WindowsRecoveryTests` 一项与 `WindowsCompensationTests` 三项。它们使用合成上游 fixture，只证明相应真实 Windows 文件/进程/占用/清理行为；不能冒充真实模型全链。Story2.8只有 AC1–AC5；Windows总验收是2.10 AC6，2.7 AC6也有Windows条件。远端 artifact13941297656 元数据已保留；本地受支持下载物化失败，没有声称本地ZIP hash验证成功，不必重跑成功 job。

## 源码年代与调用账本

两阶段审计在适配改动**之前**完成，当时 cold current-identity/full-protocol验证通过，完整输出均保留。extract请求45113字节、compare实际请求80133字节；两个官方 runtime配置为 `openai/gpt-6.1-sol`、requested/returned high、无tools、普通服务层。它们只是记录的 runtime配置，不是 provider实际物理型号/请求数/计费证明。

适配改变了审计引用的传递工具身份。旧审计原报告不改写，其 planning_eligible=true只属于旧源码年代；不能用于当前修改后的3B资格。历史完整proof仍可核对，并不表示current一致。121份原Python前像逐个对上不可变0c4d16c1 Git blob；用 `pre-linux-source-epoch.json`、`pre-linux-source-git-verification.json` 复现原始 bytes。当前产品policy为 `sha256:51b963257a60aae6435d0e68c43064c53bda710e34f754379bf6db333ddc2014` /84pins。旧580ab96f.../84、65e75d61.../83年代和原测试记录保留，不重新签名。

- 原补偿限额2/2已占用，后有明确新增1次正式修复也已完成占用，累计3。第二节点的失败/unknown没有退款或重置。
- 本次独立来源审计是另一个真实来源与限额2，2/2已完成占用，active1500s/单次timeout600s。两份原reservation、budget、event都保留。
- 以上这几次 Cloud续接已知业务逻辑调用合计5；不是整个项目或订阅周额度的财务结余。m4历史13/campaign290是独立历史，不是可用余额。
- 适配后额外审计0、native0。曾讨论未来至多另增2次新审计，但**没有创建 allowance/home/permit，也没有调用**；不能记成已用4或把讨论当当前执行授权。
- 用户现在暂停所有新增调用/业务/测试。恢复后如确需新审计，先解决真实容量问题，再由新用户指令和实际可用额度决定；按新独立来源/预算如实追加，不能重置旧2/2、只改账本、重签旧proof或自动重试unknown。

## 真实容量阻塞与网络决定

失败准备原目录：

`logs/ci/2026-11-12/b-route-planning-input/sc25/347a984ba1e3e23266004e095be33f47a148bb7ce40d7fe132bd7bf700876dce/`

其中 inputs/raw-index/raw/event 是同一次实际失败原件，必须保留。278315是加入来源分片前的完整 common-core probe下界，**不是最终整个批次准确token数**。原门限1MiB/96000及reserve2000未调大，未删业务数据。不得重复运行同一失败内容寻址准备、删除event后重开，或凭这次下界推定任意新表示必然适配。

私有普通依赖环境仅安装了 tiktoken0.14.0、regex、requests、urllib3；未获得官方encoding表，未执行 `get_encoding` 下载、未获得准确token结果。用户对增加 `openaipublic.blob.core.windows.net` 的问题明确答复：**保持当前网络设置**。不要重问、改网络/安全设置、使用镜像绕过或把估算冒充准确计量。只有 auth.openai.com/chatgpt.com等原已发布网络规则可沿正式路径使用。

曾只读查看既有无损运输代码是否有离线路径，没有实现新codec、没有测试或模型调用。它只是恢复执行后可评估的技术方向，不是确认修复，也不是新增治理前置。若考虑表示修改，必须保持完整输入/可还原性、原proof/source/容量/资源约束；不要靠删减独立证据或关闭门禁拿通过。不要现在为解决此阻塞继续开发。

## 原 Story 与恢复后的最小后续顺序

权威原文在 `_bmad-output/planning-artifacts/b-route/epics.md`：2.7第1044行、2.8第1100行、2.9第1149行、2.10第1198行起。对应实施spec：

- `_bmad-output/implementation-artifacts/b-route/spec-2-8-public-recovery.md`：保留原AC1–5；复用已真实完成补偿与Windows窄测试，按原前置核对未验收条件，不重放已解决操作。
- `_bmad-output/implementation-artifacts/b-route/spec-2-9-completed-planning-reuse.md`：AC1–5，必须从真正run.json committed完整单项，经原协调器、proof、当前相关依赖/delta登记与adoption；再验证跨新执行复用、epoch/reopen/后继撤销。现有m4 kind=all不是单项，registry epoch0/entries0，禁止改标签/手填完成项/种registry。
- `_bmad-output/implementation-artifacts/b-route/spec-2-10-formal-entrypoint.md`：沿现有3A、plan-mvg/plan-capabilities、adoption各stage与真实ID；零Task不等于无资格，formal_adoption不等于global planning complete/runtime。保留2.1–2.9正式前置、原合法循环/跨Capability Flow/共享Requirement/非Flow及失败证据；不另造框架或取消前置。

恢复执行后先只读确认分支、实际现存run与每项终态，沿 owner文档：`docs/workflows/b-route-source-accounting.md`、`b-route-source-audit.md`、`b-route-native-planning-status.md`、`b-route-adoption.md`，相关 `.agents/skills/plan-mvg/SKILL.md` 与 `plan-capabilities/SKILL.md`。现有CLI实现才是具体参数权威。

容量有可验证解决方案后，才评估真正必要的新当前审计与正式准备/生成；不能先消耗审阅再发现原容量阻塞不变。生产adapter目前仅通过存储发布定向控制；Linux子进程生命周期不提供Windows JobObject整棵子树父亡清理等价保证，真实运行一旦终态/清理不明就停原run保留占用，不能重开或虚报Windows能力。独立2.9步骤没有原需求的全局Windows-host门槛；Windows交付及故障总验收仍必须准确证明，不能据窄适配删掉。

若需要恢复现有正式发布读取样本，优先取 continuation24 `published-clone-input/` 的9个原始文件和manifest，在新隔离目录恢复并按原字节核对。旧外部真实目标路径记录在continuation22；它不在Git中，不要将缺失误认为业务未做。最初外部batch03/04数据的固定公开恢复来源在旧 `MANIFEST.json`；只在实际缺失时恢复到新隔离目录，不覆盖原数据/当前代码。原native/Python/依赖工具身份不自动跨环境成立。

## 禁止重跑、进程与隐私

停工时 `pause-process-snapshot.json` 没有活跃项目model/login/test子进程；一次性审计wrapper69745、审计child6053已终态0，正式准备session94670终态1，最后真实clone读取session22590终态0。没有在等待的设备登录、新审计或native任务。环境exec server及若干state Z的Git僵尸未盲杀；别将环境服务当业务任务终止。

不要执行历史一次性脚本，包括 continuation22 `run_formal_repair_once`/`continue_reviewed_compensation.py`、continuation24来源prepare/account/clone观察wrapper、continuation25 `run_current_audit_once.py`；它们保留的是原执行证据，不是重入入口。旧补偿已resolved/published，原失败与unknown不能靠重放清除。旧3B失败原目录和原m4状态也不应因为未完成总验收就重新执行。

保全扫描包含原始字节及36份base64协议buffer，零secret模式匹配，未发现非空私人用户/账户身份字段；唯一email匹配是公开依赖作者/维护者metadata。检查边界与每文件hash见 continuation25 `preservation-input-audit-01.json`、`-02.json` 和 `PRESERVATION.md`。不提交auth.json、令牌、私有账户协议、浏览器profile、环境secret或私有认证目录。新助手使用其自行获用户授权的官方订阅认证，绝不复制旧云环境秘密；需要用户设备登录或账户安全开关时，由用户亲自处理。

固定限制：不Fast、不收费API/API key、不未经授权账务操作、不合并main、不强推、不S2、不阿里云NewRogue开发、不无必要全量、不删改失败/unknown/预算，不把合成fixture或历史proof封存成当前完整验收。最终交接提交推送后以远端分支SHA核验为准。
