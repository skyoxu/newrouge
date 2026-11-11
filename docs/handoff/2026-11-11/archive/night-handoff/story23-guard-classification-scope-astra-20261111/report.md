**独立结论：同意一个有限的 Task H 等价调度候选。** 只复用原 `Guard.role` 中 `Path(key(co_filename)).is_relative_to(SOURCE)` 的纯分类结果；不复用整次角色检查或任何输入当前性结论。已有静态源码、trace06 的真实路径分类采样、role07 已执行针对结果和 role08 原 3600 秒终态，足以支持这一候选，不要求再做诊断或增加性能门。该同意是必要性及最小范围判断，尚不代表候选已实现、组合已通过或 paid/正式分段验收成立。

本次为新独立只读评判。Root 另行澄清允许现有 shell 做静态文件读取和文本搜索，禁止启动项目、测试、worker、监督、模型、网络及新诊断。实际只用 PowerShell 读取源码和现有小型终态元数据；没有导入或执行项目代码、调用 Git、读取 payload 正文、凭据、sessions 或 S2。唯一写入为本报告。Root 仍是唯一产品 writer/testing owner。

任务仅涉及已批准的 NewRogue Epic 2 / R23 Capability、MVG 分段。R59 的 `.git`、实际 worktree HEAD 与分支 ref 静态读取为 `fe175b49e668551b175f8d5c53a91d6c53ef59f2`；未做 Git status 或重新计算文件指纹，下面结论针对实际读取的当前源码。预算沿用 `paid-or-unknown=83`、重叠 guard 占用 `181`、cap `290`、released `0`，两类计数不相加。本候选仍零项目模型、零财政、零目标写入；high、禁 Fast/main/Epic 3–5 等限制均沿用。

**直接证据及本次纠正。**

| 已读来源 | 可确认的事实及限度 |
| --- | --- |
| 原 H `review_prepare_host.draft.py:57–68,503–558` | `key` 做普通绝对盘符、冒号/NUL、规范化及敏感路径检查；没有 stat、resolve、文件读取或目录枚举。随后 `is_relative_to` 为词法分类。每个未提前返回的 call 都重新计算它。分类后另有实际 model/native 拒绝、SourceOnly loader、code/globals、frame、locals、调用父链及一次性 public 状态检查，不能整体缓存。 |
| 原 H `:492–501,581–705` | `assert_active`、constructor、audit、profile 引用和原 FD 路径独立存在；`returned:612–631` 在 role 返回之后处理真实 codec descriptor。非 call 的 role 早返回不能挪到外层 returned。 |
| 08 host `metadata_host.Root-only.py:304–319,499–527` | 07 已批准的 Task 谓词前置保留；未拒绝的每个 call 仍委托 H。关闭时仍核对真实 FD、原 Observations、已耗用文件身份、486 个 R5 原资料及输出写域。 |
| trace06 `out/worker-stderr.bin` | 60/120 秒样本确有 Task role、H returned 和 pathlib 路径分类；120 秒仍在 `_original_assemble:273` 后置 source manifest。180 秒出现 access violation。不能归因 AV，不能从稀疏栈声称 H:506 独占 CPU，也没有 strict JSON 为主要耗时的采样证明。 |
| `story23-r59-role07-targeted-01/result.json` 及实际 `test_role.py` | 既有 4 项针对测试记录 OS0/PASS；其范围为原 AST Task 谓词/委托、原 H 拒绝、真实 FD 已关闭观察。结果明确不是完整 Guard 安装或组合。 |
| `story23-core-metadata-preflight-01/result.json,unit.json` | 既有 core-only OS0/PASS：capture 23.372 秒、describe/closing 9.529 秒、45 subprocess、零模型。unit 的 source commit 实际为 `62db4e411012ab6bbcedba3781bf7a4a63ca5188`，不是当前 R59；仅作既有能力/成本背景，不提升为当前组合证明，不需重跑。 |
| `story23-r59-metadata-role-08/result.json` | 2026-11-11 14:30:36 UTC，`passed=false`、`reader_outcome=timeout`、`cleanup=confirmed_empty`、零项目模型。 |

08 的子进程证据应从“仅 11 条”纠正为 **43 条连续 terminal 元数据：39 metadata-git、4 metadata-bridge**。本次只读聚合全部 `out/worker/metadata/1-terminal.json` 至 `43-terminal.json`；全部记录 OS0、terminal known、held handle/原 pipes/pipe workers 已关闭、双 audit、零模型、terminal_errors 空。bridge #6 的 stdout 为 110373021 字节；#17/#28/#39 均为 15443 字节。这些是现有本地 IPC 元数据，未读 stdout 正文。

第 12、23、34 条子进程的 birth UTC 分别为 13:49:37、14:06:43、14:23:39；第 43 条为 14:30:03。原 `_source_manifest` 每轮 5 个 Git 调用，`_original_assemble` 在 bridge 前后各跑一次。结合源码和上述输出规模，已有记录与“首次完整 assemble 后，多轮 rules/currentness 验证，第四组后置 manifest 尚未完成”相符；不能再说 08 一直停在首组 11 个子进程之后。具体调用点属于静态流程推断，不是 08 现场栈定位。仍无 actual describe 子进程或最终输入关闭产物，不能宣称 capture/describe/关闭整体完成。

**认可的唯一实现范围。**

1. 新建明确命名、位于 Task 新 attempt 的 H 变体文件。以原 H 为基线，只改 `Guard.__init__` 的一个实例内分类表初始化及 `role` 的该分类表达式；其余控制逻辑原样。允许原文件复制后形成极小、可读 diff，不重新设计或手抄改写 control plane。原 H、R59、metadata06 和历史 attempt 保持原身份。
2. 表只保存原表达式成功算出的布尔值，键为原始 `co_filename` 与固定 `SOURCE`；使用二者的 tuple 也可避免把不同 source 根混作一个键。同一 Guard 生命周期最多 256 项。命中必须能区分 `False` 与“无记录”；满后新文件名仍执行原表达式，不失败、不扩容、不跳过。表不跨 Guard/attempt，不持久化，不保存 frame、owner、token、路径身份、文件内容或校验结果；无 registry、carrier、seal 或新 fingerprint 体系。
3. 保留原 `event != 'call'` 及 `<...>` 处理。未缓存项调用原 `key` 和原 `Path(...).is_relative_to(SOURCE)`；异常不缓存、不吞掉，因此非法/敏感路径原拒绝不变。`key` 本身和它的所有 I/O 调用者不改。固定源码/策略下已成功分类的同一字符串重复命中只复用这个纯值；不把“在 SOURCE 下”或“不在 SOURCE 下”扩展成新的读取许可。
4. 分类为 source 时，每次仍从原 H:508 执行完整动态分支，包括当前 name、model/native 拒绝、owner/loader/code/globals/frame/locals/父链及原 public 状态判断。Task:304–319 的禁止谓词和委托保留。不得以文件名、generator、已加载 stdlib、上次成功或分类命中为由提前返回整次 role。
5. 新 driver 显式加载这个新 H 文件/模块身份，沿用现有 `H_FILE/H_PIN` 与 control-pins 机制绑定新字节；旧 H pin 不能冒充新变体 pin。仅需与新 attempt/实际控制身份相关的接线变更，不改原 `sys.setprofile`、returned、SourceOnly、constructor、双 audit、FD-return/held-close、I/O 允许域、R5 完整 manifest/proof/rules/currentness、实际 `_reader_lifetime.HOST_TIMEOUT=3600` 或原 bridge deadline。

本候选的理由是其输入/输出与无 I/O 性质可以直接从源码证明，重复路径分类也有真实样本支持。它不需要先证明精确耗时占比；但不能预先保证解决 timeout，亦不能宣称修复 AV。256 是小表实现上限，不是新业务阈值或新的必交指标；无需另加命中率遥测、基准或压力验证门。

**对重复 JSON/context 验证的判断。**

`runtime._SourceCapture.__getitem__:511–514` 除 byte_store 外，确实每次严格解码完整私有 data；`__iter__`、`__len__` 也会解码。它还提供每次独立的嵌套可变返回值；生产层缓存解析对象会改变别名/修改隔离语义，单凭“data 是私有 bytes”不能直接批准。`verify_candidate_context:583,587` 在同一函数内两次取 source_identity，有局部变量复用的潜在小改法，但属于 R59 产品改动，当前没有该解码阶段的热点证据，也不是此次 Task H 候选的必要组成部分。此次不改通用 strict codec，不缓存生产 SourceCapture，不引入新的 token/issuer/registry。

`verify_candidate_context:574–589` 不只是校验冻结 token。它重新检查 policy，读当前文件/absence、目录 watch，并通过原 owner 核对当前 rules 及完整 R5 verifier manifest。因此相同 token 并不等于相同外部当前性；不能把 capture 内部 `:570`、runner scope 前 `:1147`、实际构造前 metadata06 `:442`、runner 后 `:1197` 全部折叠成一次成功缓存。当前 43 条终态也显示这些原 owner 路径确有推进，不能说它们只是无效空转。

单独看 Task driver `:222`，它在 `_describe` 已经执行原 scope finally 的关闭验证后再显式验证，确有较小的测试编排去重候选；但 08 尚未产生实际 describe 子进程，删这一最后的调用不能修复已观察到的前置超时。当前最小、可归因的下一步只改 H 纯分类；本轮保留 driver 原组合及全部原 currentness 验证，不混入这个不解决当前失败阶段的第二个变量。成功后也不必为了“更多证据”另跑同一冻结上下文的 core-only 或全量深验。

**Root 后续的最小验证及停止条件。** 本次没有执行以下检查。

- 先审阅新 H 相对原 H 的窄 diff，确认原 role 动态尾部、returned/profile/constructor/audit/I/O 和 metadata06 未被改写，driver 仅接线新控制身份。沿用现有 pin 校验，不建立额外指纹包。
- 少量差分用例覆盖源内/源外/相邻前缀路径，冷/命中/达到上限后的原逻辑回落，以及非法相对/空/敏感 filename 的原拒绝。重点是原逻辑与候选的结果、异常语义相同，不以 cache 计数或性能目标作为通过门。
- 在同一已热 filename 上换成实际原 model/native 禁止函数名，及改变需要验证的 owner/frame/locals，仍必须触发原动态拒绝；保留 Task 原禁止谓词。这样能区分“纯分类复用”与危险的“整次角色授权复用”。既有 07 未修改分支的结果可复用，不重建全部旧 controls。
- 用候选的原 returned wrapper 复用真实 descriptor 关闭检查，并保留一个未关闭 descriptor 会被拒绝的反例；不伪造 EBADF、returncode 或闭合记录。无需单独展开全安装矩阵，实际组合承担真实安装/constructor/双 audit/SourceOnly/held 生命周期验证。
- 窄检查通过后，只做一次全原 `capture_source → _describe → verify_candidate_context → 原 close` 的 metadata 组合，使用实际原 3600 秒 host 上限。零模型/财政/目标写、原 486 资料/当前性、真实 describe 子进程双 audit/held OS0 与 FD/输入闭合证据共同成立才可称 metadata 组合通过；既有 core PASS 或 43 个 metadata OS0 不能替代。

若新差分失败，先停止组合并修正该窄变更；若组合 timeout、AV、拒绝或任何关闭未知，保留本次原失败和实际关闭状态，停止同候选重跑，不加 deadline、不重开 faulthandler、不转 core-only、不绕过 Guard 或删 R5 资料。后续只按新的具体失败事实选择必要工作，不能用本报告自动授权其他修复。一次完整组合通过且保护/关闭证据充分就停止诊断循环。

当前剩余问题是 **Task Guard metadata 组合活性及真实闭合尚未通过**。本报告同意上述单一候选进入 Root 实现及少量验证，不新增 Story 门，不改变既有 paid 或正式验收状态。本次无工具审批拒绝、无悬挂执行、无本评判发起而结果不明的操作。

**09 后续只读实装核对：符合上述范围，没有需要阻止唯一一次新组合的偏差。** Root 指定的候选为 `night-handoff/story23-metadata-role09-20261111/review_prepare_host.classification.py`；本节只核对已有文件及已记录结果，没有执行候选或测试，也没有启动任何组合。

- 候选 H `:309` 只新增每实例 `_filename_classifications = {}`；`:507–514` 使用 `(co_filename, SOURCE)` 键、`get` 的 None 未命中判别、成功计算布尔值后 `len < 256` 才写入。False 命中、非法/敏感路径异常不写入、满表回落原表达式均与批准方案一致。原 call/`<...>` 早返回及动态尾部保留。
- 本次对候选全文在内存中精确撤销上述初始化行及分类块，仅统一 CRLF/LF，结果与原 H 全文相等。其余源文本没有隐藏改写；不仅依赖作者的 AST 摘要。原 H 实际字节仍匹配既有 `3875a5...138449` pin；候选匹配 09 driver 的 `3f43a3...ff2459` pin；R59 `_b_route_segmented_runtime.py` 匹配既有 `a07402...01e0e` pin。本次仅比较这三个已存在控制 pin，没有建立新的 fingerprint 文件或全目录扫描；不据此宣称独立验证全部 R59 worktree 清洁。
- 09 `metadata_host.Root-only.py` 与 08 字节完全相同，均为 31993 字节。driver 的逐行差异仅 `HOME`、`H_FILE`、`H_PIN`、加载模块名 `_Root_R23_H_classification09`；仍通过原 `load`/`read` 校验候选 pin 并纳入原 control-pins，未把原 H 身份冒用于新变体。
- 已读 `night-handoff/story23_metadata_role09_owned_20261111.py` 及 08 对应文件。实际差异仅 home、out、run-id 的 08→09；`started.json` 中 timeout_seconds 与 `run_reader(..., timeout=3600)` 均为 3600。原新输出排他创建、`run_reader` 所有权/退出/清理路径及零 paid/financial 声明保留，没有把 deadline 修改成另一个 H 属性，也没有新增重试。
- 已读 `test_classification.py` 和 `logs/ci/2026-11-11/story23-r59-classification09-targeted-01/result.json`。结果在 14:56:30 UTC 记录 5 项、OS0、零 error/failure、0.621 秒；范围覆盖冷/命中/不同 SOURCE/256 后回落、重复非法/敏感拒绝、同热 filename 后的 model/native/owner/globals/locals 拒绝、原 Task 谓词，以及真实 closed/live descriptor 的返回处理。源码确有这些辨别用例。角色差分使用抽取的原 AST 方法与受控 frame/loader 测试替身，FD 检查使用实际 OS descriptor；它们不能冒充完整 SourceOnly 安装或组合。结果亦明确 `full_guard_composition_verified=false`、正式验收 false。本评判未重跑这些测试。

可由 Root 按原已同意边界启动 **唯一一次 09 原 metadata 组合**；无需补跑本报告未要求的测试、诊断或全量预检。原 3600 秒上限、所有 currentness/资料/保护/关闭条件与失败停止条件继续适用。Root 告知核对时 09 尚未启动，本评判未查询或操作进程；组合成功与否仍须由该次真实终态判定。该复核没有新增确认要求、Story 阻塞门或预算授权。
