# Recovery and Worker Boundaries

## Ownership

主协调器准备当前 Capability 的完整相关来源、只读累计 seed 和候选身份。三个候选生命周期分别在独立 OS 子进程执行生成、确定性门禁、独立模型上下文语义准入和有界修复。worker 不能写主 run 的 selected 状态或恢复索引；调用预算由主协调器持久预留，实际费用不能因失败或重启丢失。

worker 只返回候选状态、完整合格 proposal、identity/hash、proof/receipt 引用和调用记录。父进程必须独立机器复验，不信任 admitted 标记。失败草稿、模型对话和修复历史仅留 `logs/**`，不送评选模型。排名使用新的模型上下文，不能再次对已准入项施加语义否决。

下一 Capability 仅继承结构化累计选定结果和当前相关的完整跨项 flow/handoff/共享 Requirement 边界。完整全局输入留给机器验证；模型完整读取当前所需语义，不重复消费无关文件，也不截断来源。候选进程隔离不等于预算降低，预算由真实阶段成本核算。

## Completed-only recovery

完成点是三个候选均准入、父进程复验、评选和 checkpoint 原子提交全部完成。prepared bundle 或 selection 文件单独存在不算完成；崩溃提交未知必须先由磁盘 commit point 消歧。

单项哈希覆盖该 Capability 的完整 JSON 对象，规范化对象键序及 JSON 排版，保留数组顺序和 JSON 类型；不纳入 catalog 元信息、Git commit 或其他 Capability。忽略文件排版不能忽略字段值中的空白。Capability ID 及内容均保留，禁止 98% 或其他模糊匹配。

同 hash 结果必须验证不可变来源 checkpoint、proof/receipt 和当前累计 delta 重放。关联证据若已失效或基线不能安全合并，则不能直接跳过；记录明确不兼容原因并从当前输入重新生成，不调用 LLM 判断是否可以恢复。不能把旧累计 snapshot 直接覆盖新 seed。

跨 run 复用保留历史 proof 原始身份，以新的 adoption receipt 绑定旧事务、当前 Capability hash、当前 base/result hash 和机器验证。模型中间态不恢复；进程重启必须新建工作区并保留旧费用审计，不能删除旧日志或把已付费用归零。

全局审计显式 reopen/invalidation 同时撤销受影响结果及后继的复用资格；同一清理代际内也不得重新导入。现有 64 次预算属于 run 内稳定候选槽位，跨 Capability、替换 lineage 和 OS 进程持续累计，不能因更换进程 ID 而重置。

## Progressive projection and clear

Cumulative MVG scope 读取主协调器已提交投影，而非 worker 临时文件，显示 completed/total、current Capability、新生成/复用来源和全部已选累计内容。部分规划不得标为整个 run 已完成或 runtime verified。后续失败、服务重启和页面重载不丢已完成项。

生成期间自动刷新只读累计结果，操作锁继续阻止写操作，但不能让全页遮罩遮住这些进度。旧结果验证使用其原始冻结输入；当前复用兼容性单独对照当前输入，不能用新的 analysis identity 改写旧证明，也不能因旧 Git revision 与当前不同就一律拒绝未变内容。

清理针对当前项目本地生成 MVG 的显示和全部恢复资格，不修改 Git 中正式回归基线、Capability、任务或运行验收历史。历史生成日志可留审计，但旧 attempt/latest 指针、扫描 fallback 及 worker 晚到写入不得复活清理结果。清理与生成/验收操作共用服务锁；活动生成期间拒绝清理。通过持久清理代际实现失效，无需递归删除整个日志目录。之后下一次 Generate 创建新 run，零项可恢复。

## Acceptance matrix

| ID | Testable behavior |
| --- | --- |
| AC-01 | Three candidate lifecycles use separate OS processes/workspaces; no candidate reads sibling artifacts. |
| AC-02 | Tampered worker result is rejected by parent before selection; only three admitted results are ranked. |
| AC-03 | Same individual hash survives Git commit/catalog metadata/other-Capability changes without model calls. |
| AC-04 | Key order/JSON indentation keep hash; array/value/type changes alter hash and trigger fresh generation. |
| AC-05 | Interrupt after committed A during B; next run adopts A and discards all unfinished B model evidence. |
| AC-06 | Interrupted commit is resolved from the atomic run pointer; orphan prepared bundles are not recovered. |
| AC-07 | Reuse validates current cumulative compatibility; corrupt proof and incompatible delta never overwrite accepted state. |
| AC-08 | First committed result appears before later generation completes; later failure retains it with partial status. |
| AC-09 | Clear immediately shows zero completed results and invalidates every old local recovery pointer; audit remains. |
| AC-10 | Concurrent clear/generate is rejected; stale generation cannot republish into a cleared generation. |
| AC-11 | Candidate/context restart preserves charges; source inputs remain complete and relevant without truncation. |
| AC-12 | Final global audit remains machine-only; planning progress never grants runtime verification. |
| AC-13 | Explicitly invalidated checkpoints and descendants cannot be adopted again in the same epoch after restart. |

先用独立 fixture、真实子进程中的 fake runner、API/页面回归验证上述行为；真实付费模型整轮测试由后续明确测试阶段执行。
