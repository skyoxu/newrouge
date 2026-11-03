# newrouge B 路线工作区与继续入口

## 当前工作位置

- 仓库与后续命令目录：`/workspace/newrouge`。
- 本地分支：`fix/capability-synthesis-input-integrity`，跟踪 `origin/fix/capability-synthesis-input-integrity`。
- 本轮迁移使用的远端起始提交：`cd925bdcae4b61992320773497f7edb729aac244`。本地文档提交在其上继续，不把旧 main 或旧工作分支当作当前工作树。
- BMAD：6.12.4，Core／BMM，29个 Codex 技能，中文交互及文档输出。运行目录为仓库内 `_bmad/`，技能位于 `.agents/skills/bmad-*/`，按既有 `.gitignore` 保持本地安装。

## 本轮产物

| 内容 | 路径（相对此目录） | 状态 |
| --- | --- | --- |
| 原始附件 | [newrouge-b-route-original-requirements.md](sources/newrouge-b-route-original-requirements.md) | 原始字节不变；嵌入示例指令不作为额外执行授权 |
| PRD | [prd.md](prds/prd-newrouge-b-route-2026-11-03/prd.md) | 已定稿，18条FR；目标为路线改变，不以提速验收 |
| 工程及23项验收补充 | [addendum.md](prds/prd-newrouge-b-route-2026-11-03/addendum.md) | 保留原始固定基线资料，当前事实结合下一项读取 |
| 当前分支基线 | [baseline-update.md](prds/prd-newrouge-b-route-2026-11-03/baseline-update.md) | 对齐ADR-0039、checkpoint／worker／恢复及核算能力 |
| SPEC包 | [SPEC.md](../specs/spec-newrouge-b-route/SPEC.md) | 11个CAP身份保留；下游须读取全部companions |
| 架构准备记录 | [架构 memlog](architecture/architecture-newrouge-b-route-2026-11-03/.memlog.md) | 只有准备和继承约束，尚无最终架构主干 |

PRD／SPEC 各目录内保留原有 memlog、来源对账及审查记录。历史记录中的旧绝对路径或提交身份是当时事实；迁移映射及新基线通过追加记录说明，不改写 canonical memlog 历史。

## 已确认的决定与下一步

使用附件创建 PRD，再由 SPEC 消费 PRD，架构消费 SPEC；架构完成后判断并按需进行一次 SPEC 回补。当前尚未进入最终架构或架构后回补。

已确认 B 顺序、完整Task三联和Chapter3–7、能力／阶段交接优先、奖励领取／跳过／返回的最小真实生产适配试点、五批交付与有界A兼容退出。成本记录用于观测重复与失败，不是提速或成本下降承诺。选择Coaching，真正新的关键决定先讨论，常规实现细节不重复增加审批。

架构阶段尚待讨论的取舍是沿用现有版本化文件流水线、分阶段绑定及journal／消费者门禁，还是需要新增规划数据库。迁移分支不等于已经选择该方案；新架构应先继承当前ADR-0039及已有worker／checkpoint能力，避免重复设计。

后续工作以此仓库目录和本文件明确绑定的产物为入口，不使用迁移前 `/workspace/_bmad-output` 作为另一套活动来源。不触发开发、任务生成、游戏运行验收或远端发布。

## 本地安装恢复

在仓库目录执行已有版本的官方安装器可恢复被忽略的本地工具：

```powershell
npx bmad-method@6.12.4 install --directory . --modules bmm --tools codex --user-name Agent --communication-language Chinese --document-output-language Chinese --yes
```

遵守既有Node／Python／uv前置要求；配置和渲染检查属于本地BMAD可用性检查，不代替Windows／Godot的项目运行验收。

迁移前完整备份、14个原产物的字节哈希、旧基线源码资料、历史302项脚本测试及本轮迁移检查保存在 `logs/ci/2026-11-03/bmad-b-route-migration/`。过程证据继续按仓库日志规则管理。
