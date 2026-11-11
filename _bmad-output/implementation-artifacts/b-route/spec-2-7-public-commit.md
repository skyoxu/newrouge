---
status: done
story_key: 2-7-一致提交采纳目标并以catalog发布
baseline_commit: dacd713984f91deed4ad80826d22459b819ffc06
original_story_baseline_commit: 4d0aa32195b10347d92370b82c673043e550224b
original_execution_commit: 22162e2a15e344ddcf0cbab0f8b1d0d5a1834b77
review_loop_iteration: 0
---

# Story 2.7：一致提交采纳目标并以 catalog 发布

本文件是当前修复与收口记录，不追认原实施时期不存在的 Step1/2 审批。原 Story 基线为已验收 2.6 的 4d0aa32；原真实执行冻结在 R56 22162e2a。当前独立修复分支由 DACD 基线建立，代码检查点 aba19609；未冒称 R56 与当前对象库具有已证实的 Git 祖先关系。

## 当前执行与验证记录

原 apply 的宿主 post-control OS1 真实失败保留。后续 verify 使用明确 applied-state 恢复来源，没有重放 apply、候选或模型请求；原 verify、publish、read 均已取得持有句柄的 OS0 自然终态与业务通过回执。原 read 返回 committed/formal_adoption=true，28 scopes、5 个正式文件；Task readiness/runtime/default B 仍为 false。

当前 aba19609 的真实公开 read 也已自然退出 OS0，读取同一原已发布 NativeV15Origin03，返回 committed；业务读取约 23.45 秒。该 Python 进程观察到 socket.connect 和子进程事件各 0；这不代表整台服务器的流量测量。不同源码/控制版本的耗时不得直接外推为整体优化收益。

证据均保留在 Task 根目录 logs；原 R56 记录不修改。原 35 个不同观察、14 个历史保护方法、5 个后续定向方法、26 个语义机制方法按原时代与实际覆盖复用；没有把它们改称本次全量通过或真实模型语义验收。当前修复仅运行受影响方法，具体原件、执行版本及失败历史见 `logs/ci/2026-11-11/story27-r61-review-close-Root-02/verification.json`；真实读取见 `story27-r61-real-read-smoke-01`。

## Owned implementation

Use `_b_route_commit` through the existing adoption CLI's explicit apply/verify/
publish/read stages. The journal retains the exact Story2.6 operation and index;
a versioned auxiliary commit intent adds crash-visible lifecycle and an owned
pending marker. Six formal records keep their original schemas and registry.
The current native/adoption producer remains the admission owner; no model,
allocator, alternate mutex or Task completion state is introduced.

## AC map and authored checks

- AC1: initial fresh reserved context, whole future-bundle checks, exact target
  before/after classification at every write, after skip, unknown edit/source/
  sharing refusal retention. Tests: after/unknown, required source drift,
  re-signed dropped observation, resumed frozen allocation/review mismatch,
  actual Windows sharing refusal.
- AC2: actual after target and authority re-read; strict complete bundle checks;
  immutable minimal receipt binds original frozen operation. Existing eight
  projection tests cover identities, independent references and digest cycles.
- AC3: final complete catalog payload in durable intent, replace-last, one
  receipt for all frozen affected scopes, independent plan/binding references,
  unrelated preservation and safe rebase. Replan freezes prior current head
  scopes before host review. Tests cover durable ordering, unrelated publication
  between steps, retained catalog attempts and original revision preservation.
  Plan-only publication reads existing governance via the shared safe byte owner.
- AC4: the actual implemented bootstrap combination is a real admitted native
  plan plus policy and genuinely empty origins in one reviewed operation, with
  no Task/triplet/Chapter5 witness requirement. No fake Task/readiness/scene.
  Independent policy-only producer coverage is not claimed.
- AC5: explicit committed records context, receipt-sealed historical log proof,
  real related source and formal target verification, shared pending protection,
  catalog before/after reread, scoped semantic key and clone without logs.
  Candidate external validation stays strict. Tests include re-signed missing
  proof authority, source drift, catalog drift, unrelated scope identity and
  existing declared Task status projection versus Acceptance changes.
- AC6: complete no-op writes nothing; each fixed crash boundary retains active
  pending; published-but-uncleared marker blocks. Terminal history must connect
  its saved catalog after image to actual publication, including after a replan;
  a re-signed phase or disappeared marker alone cannot release the active claim.
  Windows tests use actual file
  sharing and fixed synthetic-owned process crash/restart. Fresh child apply
  uses only an explicit synthetic capture seam; commit/records/leases/IO remain
  real. No arbitrary system
  reboot, power-loss or database isolation claim.

## Verification

已执行的检查：非对象公开输入/正常对象与 dispatch、维护选择器、真实 Win32 临时路径边界及超限拒绝、Task read 收口三种变化、历史完成与当前 freshness 分离、发布后 pending 加无关发布、四项跨 plan/binding/receipt 关联保留正反测试、当前历史适配器 15 个 DATA/接口方法。最后的真实公开读取确认当前 reader 可消费原正式链。重复 selector 方法不重复计数；没有开启全量或新的真实模型验收。

当前修改没有新增公共授权、记录种类或凭据/网络设置；继续使用原 registry、journal、claim、锁和正式记录。旧 unknown 占用、失败及 83/181/290/0 预算保留。high 是已保存的运行时配置证据，不宣称服务端实际模型身份或物理请求数已验证。

## 交付边界

原始 Step4 三层完整 diff 审核已完成，Root 阅读有关实现及全部本轮修复并逐项核实。Root 没有宣称逐行全文重读 746KB 原 diff；原工作流没有要求 Root 重复每位审核员的全文阅读，不将其新增为阻塞。原 diff 与当前修复 diff 分别记录，不能拼接后冒称同一基线的最终树。

B1 原子写入 rename 前硬退出残留仍需显式消歧，自动恢复属于 2.8。B7 分配前资源限额、B9 有界历史 capture 和 G2/G3 历史维护覆盖限制均如实保留。没有机器断电、数据库隔离、独立 policy-only producer、Task readiness、runtime PASS 或默认 B 启用承诺。Story2.8 的真实历史 proof3 恢复/补偿验收尚未完成；不反向阻断当前 2.7。

## Review Triage Log

| ID | 判定 | 处置 | 逐项依据与证据 |
| --- | --- | --- | --- |
| B1 | medium | defer：原有中断消歧边界，交 2.8 | 硬退出可留下原子临时文件，严格 inventory 会安全阻断。原 AC 明确自动 recover 属于 2.8；不忽略或删除残留，不宣称该窗口已恢复。独立 Astra 范围评判确认不新增 2.7 自动恢复前置。 |
| B2 | medium | patch：复用已有分支，已验证 | R56 的发布后 pending 加无关发布组合存在实际缺陷。当前已有 published-after/lineage 分支；cleanup-publish 对显式 publish 的精确清理及无关 catalog 字节保留通过，不重建原正式提交。 |
| B3 | false | reject | 公共 owner 文档明确 receipt 只选择 scope；read 返回当前正式链且没有宣称指定 operation 已发布。未发布 receipt 本身不能授予正式采纳，相关正式链及 pending 仍由真实 reader 核验。 |
| B4 | false | reject：保留所观察到的遍历事实 | 完整 catalog 的正式链展开是事实，但原合同不承诺跳过未选中正式记录的损坏；R56 原执行有 writer-scope 保护。独立评判未证实 AC5 违约，不裁剪现有正式链校验或新增选择性读取门禁。 |
| B5 | medium | patch：00126a20 | 历史发布事实与当前 freshness 已分开；history-after-3 证明来源变化不复活旧 claim，而当前 read/no-op 仍拒绝陈旧来源，receipt/不可变目标损坏仍拒绝。 |
| B6 | medium | patch：2d3f8d88；与 E2 同因 | 实际 commit 临时路径复用既有 atomic_json_temp_path。writer-after-2 实测 Windows 合法边界可原字节写入、邻接超限在创建目录前拒绝。 |
| B7 | low | reject：非本轮新增资源框架 | Git 对象先读取后执行 32MiB 归档限额的事实保留；尚无本次超大对象故障，原合同未保证分配前硬内存限额。为罕见超大对象引入进程流式读取超出最小修复；不称该资源风险已修复。 |
| B8 | maybe-false | defer：原有配置风险，未证实 medium | 基线已使用同一 git status，未取得本工作实际 fsmonitor 配置或执行证据；需实际配置和可达调用证据才能判断影响。本轮不修改 Git 或主机安全配置。 |
| B9 | low | reject：保留明确容量限制 | 历史 proof 重复内嵌可增长并触及既有深度/容量限制；原合同不保证无限连续 capture。未证明本次正常输入已失败，不为该低频容量边界新增登记库、seal 或去重框架，也不宣称已消除此限制。 |
| B10 | medium | patch：2d3f8d88 | 公共 read 保留既有 Task Snapshot 并在收口复核；reader-after 的定义/视图/文件消失三种变化均拒绝，未增加全层指纹扫描。 |
| E1 | medium | patch：19221621 | P 引用 Q 时保留未授权替换的 Q 与独立 binding；旧 receipt 原件通过现有 authority_refs 及有限显式边保持可达。四个定向方法通过，含两次合法 P 修订、无 logs clone、丢失/篡改旧 Q 拒绝及无关有效 receipt 不可顶替。缺失 Q/owner 冲突仍在写前拒绝。 |
| E2 | medium | patch：2d3f8d88；与 B6 合并 | 独立发现同一临时路径公式偏差；B6 的实际 Win32 边界正反验证覆盖此主张。没有把审核中的估计数字冒称测量值。 |
| E3 | medium | patch：89c09a05 | read_subject 在读取版本前要求对象类型；shape-only-2 经两条真实 CLI 路径对七种非对象 JSON 拒绝，remaining 验证对象形状和已有 dispatch 入口。原 AttributeError 及夹具失败保留。 |
| G1 | medium | patch：89c09a05 | initial_legacy 现有模块维护选择器遗漏已修复并断言只注册一次；复用原 14 个历史方法，不重新运行已适用方法。 |
| G2 | medium | defer：历史 v3 维护覆盖限制 | 旧公开 v3 正向渲染接线缺直接维护断言，原 26 方法只按实际覆盖复用。独立 Astra 确认当前默认 2.7 已拒绝 fresh v3，此历史消费属于 2.8，不能倒加为当前 2.7 前置；真实 proof3 仍待完成。 |
| G3 | medium | defer：历史 OP03 维护覆盖限制 | 原七方法确实执行过，但不能宣称全部验证成功 binding 构造。当前 2.8 历史消费者不重构旧 binding；不移植旧实现或改冻结 R56。当前 15 方法 DATA/接口适配器已注册并通过，但不充当真实恢复验收。 |
