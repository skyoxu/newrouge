# Story 2.8 compensation review capacity: independent scope assessment

只读评判，2026-11-11。基线 R62 `b24e1dfd35901389dc6297683cd1fe4b52ce3b58`。工作树已有 `scripts/python/qualified-historical-owner-authority.v2.json`、`workflow.md` 修改；本评判未改变它们。只读原合同、相关实现、原 prepare11 结果及本机官方 runner 元数据；未运行项目、测试、模型或网络，未读 auth、sessions 或 S2。唯一写入为本报告。

**结论：同意 A 为优先的最小方案方向，不同意现在直接调大容量或立即启动 B。先补齐 A 所需的现有官方元数据适用性证据，再作一次显式的补偿专用本地容量政策决定。若此证据仍不能成立，才评判 B 的具体最小新协议。C 目前没有充分实际依据。此结论不增加 Story AC，也不宣布 2.8、2.9、2.10 验收。**

## 原合同与当前事实

- `_bmad-output/planning-artifacts/b-route/epics.md:1100-1147`：Story 2.8 保留旧 journal/pending 恢复、后编辑及历史；AC-4 要求新的受审阅 operation，没有规定分段框架。AC-1 禁止为重建已有应用状态重新支付模型费用。
- 当前 qualified-public-private.v2 语义由 `_b_route_qualified_compensation_materials_v2.py:42-50` 明确：完整原 owner 公共语义及当前语义原件进入模型；完整 private bytes 由宿主精确认证，不能称为模型已读。
- `logs/ci/2026-11-11/story28-r62-public-prepare-11/{result,unit,genuine-render-complete}.json`：原生 prepare 自然 OS2、零模型调用；真实 render 已完成 166939774/170000000 work，frame 313388 bytes。`traceback.txt:24` 的真实阻断为最终请求 316309 bytes、保守输入 101371、预留 2000、限额 70000。identity_unprovable 是外层诊断包装问题；本评判不把它扩展成额外实施范围。
- `_capability_input_integrity.py:13,53-55,490-519`：共享默认实际为 96000；qualified owner 在 `_b_route_qualified_compensation_review_v2.py:295-299` 另取 `min(70000, configured_input_limit())`。70k 和96k均是项目政策，不能称为已验证官方硬窗口。只调到96k仍不足：101371+2000=103371。

## 方案评判

**A：首选，但有明确证据缺口。** 保留一个请求读完当前完整公共语义材料、现有 codec/canonical/语义合同及原检查分母。若采用新政策，只给 qualified-compensation 新的显式本地 profile；实际最低总 allowance 是103371，不改变 Cap/MVG 的70k、原96k组合约束或共享默认。应由一个明确固定值承载政策，不按包自动放大。

只改 artifacts 不够：`codex_isolated_model_runner.py:570-572,625` 在真实 dispatch 前再次按 CLI/config allowance 计量。现有 `--max-input-tokens` 已可承载专用值，应复用；新 profile 的 command、实际输入、schema、runtime 和原 saved-reader 精确回放必须保持一致。无需新增预算池、指纹门或泛化 runner 重写。阈值改变须依 AGENTS.md 的既有 ADR 规则显式更新 ADR-0050/0055 相关承继，不改写旧失败、旧 proof 或旧 reader。

本机 `C:/Users/Administrator/.codex/models_cache.json` 存在官方客户端模型目录元数据：读取时 fetched_at=2026-11-11T14:38:54.696143600Z，client_version=0.166.0；目录中的 context_window 为272000或500000，effective_context_window_percent=95。只读取容量/型号/时间字段，未输出 identity 或指令正文。项目 `_codex_app_server.py:56-65,373-383` 确实读取此类缓存并保留模型元数据，限制仅作用于工具能力；这是有用的官方 runner 侧支持线索，并非仅由模型名称猜测。

但本次没有证明该缓存与项目下一次实际 CODEX_HOME、environment-default 解析、有效配置及 CLI 相同。PATH npm包元数据版本为0.160.1；`thread/start` 没有固定model（`:505-507`）。仓库保存的官方 schema 只声明 `model_context_window` / `modelContextWindow` 字段，未给本次具体窗口。本评判没有足够证据声称103371已受本次官方服务窗口支持，亦不把服务端实际模型身份认证变成新要求。最小下一步是 Root 对现有已归档同 runner 的容量元数据与有效目标作窄核对；若没有适用来源，明确需要新的官方依据，再决定 profile。不得用改一个环境变量或无依据删限额代替这一政策决定。

**B：可作为显式后备方案，范围大于 A。** ADR-0042 的批准范围是 Capability/MVG；当前 runtime PROFILE 与 workflow plan 都只接受 capability/mvg，并附带固定2/3候选和四阶段语义。补偿不是新的候选生成任务。应只复用已有切片、完整引用、request/runtime/journal/fiscal原语，另立最小的补偿审阅 consumer/证明版本，明确完整原件覆盖、跨段依赖与相互影响、独立审阅、最终裁决及冷回放。不能声称与旧一次读完全部材料相同，不能迁移或重签旧proof。不能为复用而要求补偿执行整套候选生成，也不能把无关 Cap/MVG 付费验收变成 Story 2.8 的前置。

每请求仍按已批准70k及原输入加输出总限，保留无隐式记忆、无摘要替代原文、unknown占用及原账本。不可拆的依赖闭包超过上限仍明确阻断。既有 R23/R59 离线证据按原范围复用；它不能冒充新 consumer 的真实资格。新协议的实际范围/调用数/原预算接入应先可审阅，不能现在直接开启大重写或付费流程。

**C：当前不成立为下一步。** 现有完整材料已走 compact-v4；要保留2000预留并落入70k，输入需从101371降至68000，即减少约32.9%。最终 wrapper/schema 相对 frame 仅多2921 bytes，未见足以达到此幅度的无损替代证据。不能据局部压缩猜测整请求可过，也不应继续无收益微优化。将来若出现固定完整原件上的真实无损结果，才重新比较；这不是新增验证门。

## 边界

当前容量拒绝继续作为已知事实保留。83 paid-or-unknown / 181重叠guard / cap290 / released0 不相加、不释放、不扩额。high、关闭Fast、不合并main、保留旧R22合同及旧reader不变。本报告不授权新的模型调用、分段consumer实施、默认启用或正式验收。对A依据不足的说明属于本次方案选择的验证限度，不是新Story阻塞项。
