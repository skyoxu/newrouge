# ADR-0052: 初始空 Task 仓库的 legacy manifest 保护边界

- Status: Proposed
- Date: 2026-11-08
- Scope: inventory/protection v3；不改变 Task、manifest validator 或默认路线
- Authority: Root 批准的 R50 最小通用 bootstrap 修复；实现已编写，实际验证和本决定收口待 Root 完成

## 问题

原 inventory 无条件要求成熟累计 MVG manifest，而原 manifest validator 要求 Flow 的非空 Task 映射。真实完整空三联因此不能通过实际 protection collector。只删 missing-manifests 诊断、接受一个调用者布尔或伪造 Task/PASS 都不能解决归档重建与当前资格问题。

## 决定

当前采集使用 `newrouge.b-route-baseline-inventory.v3`、`newrouge.b-route-protection-snapshot.v3`。私有观察使用 `newrouge.b-route-legacy-manifest-requirement.v3`，状态只含 required、initially_absent、unknown。没有 bootstrap CLI 开关，也没有 approved 或 not_required 授权标记。

现存 manifest 或非空真实 Task 仍直接走 required 与原完整 validator，不增加不相关全历史费用。只有完整真实空三联、无当前 manifest 的候选需要额外证明：当前明确的两个 Git anchors 属于完整可重建的真实祖先图；初始和相关全部历史树中的三联真实为空；没有受治理 manifest、明确 legacy apply 目标、冻结 A 或相关既有 owner 的 required 事实；当前 source-set、canonical sources、manifest 递归成员与相关 owner 原件可关闭。缺失、损坏、未知、截断、unsafe 或漂移均不构成初始豁免。

初始提交不可能预先包含自己的 hash，因此不要求初始 epics 的旧声明 hash 在新 root 解析；只验证当前明确 anchors 和它们的真实祖先。Git 原始 commit/tree/blob 按对象格式校验 OID、父图、固定受治理路径和 index，再保留在 inventory 原字节中供 archive-only 重导。当前 initial 资格另复查真实 root/history/member/owner 事实；复制或重签 state、删 raw/support 或换 root 不能替代复核。

只有明确现有 owner 路径和记录参与观察：实际 manifest namespace、三联/source-set/epics 声明、正式 frozen-A refs、原 Capability/MVG apply journal 与固定 inventory/protection capture 输出。native 3B 的 run.json、普通示例/prose、无关 JSON 和 read-only verification/failure 调试输出本身不表示 legacy 启用。已知 partial raw capture、不可归属且可能相关的原件仍阻断；不扫描整个机器或任意 logs。

显式 historical inventory 仍按原引用角色保存观察。只有同 root 且在当前真实祖先图中的具体 manifest/Task/frozen-A/治理事实影响当前 initial 决定；其他 root/无关历史不能因为含有 Task 或缺失调试附件就激活本 root 的 legacy。ADR-0049 的 Task evidence_refs=historical-debug-attachment/false 不变；缺失事实、null digest、warning 和旧原 bytes 保留。当前必要 source/test、明确治理前置和实际同路径当前需要仍严格核验。

只支持当前 v3 与完整已安装 rules；旧 v1/v2 不升级、不重签、不作当前资格兼容。历史原件及其失败解释保留。v3 的 semantic subject 包含实际 root/anchors/成员/owner/digests 和完整观察 digest；不重复展开 opaque Git 对象 bytes。完整原始对象及当前材料仍在 inventory/raw archive，机器独立重导后才接受摘要。

## 有界性与局限

初版最多 512 个 reachable commits、8192 个 Git 对象/当前原件、32 MiB 原始对象/当前观察，以及 16 层已有 owner 链。超界返回 unknown，不截断后声称完整，也不是速度或成本验收阈值。Git 使用固定本地读取、30 秒单次界限，禁 lazy fetch、replacement、网络协议、hooks、签名及外部/global config；不修改 host 设置。实际 argv/env 与测试 fixture 的有限变更角色由作者 handoff 列出，Root 独立控制执行。

这证明有界 governed Git/path/owner 事实，不证明机器从未出现未记录临时文件，不认证 collection 事件来源，也不提供任意外部写者隔离。普通 JSON 可以重算；真正执行仍依赖原始 Root-held 运行证据。protection verify 的 initial live 子检查不替代 native/source audit、独立 host review、scope/lease/before-after 或公共 commit/read。

所有 protection authorization 继续 false；零候选不是冻结 A 授权，初始缺失不是 manifest/runtime PASS。默认 B、readiness、runtime、预算、未知请求与原 frozen native owner 不变。正式 2.7 与本 ADR 接受需 Root 当前来源下验证；作者只作静态读写/AST/hash。

Refs: [inventory owner](../workflows/b-route-baseline-inventory.md)、[protection owner](../workflows/b-route-mature-protection.md)、[ADR-0049](ADR-0049-b-route-reference-roles.md)、Story2.7 AC4。
