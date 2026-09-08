---
title: 'Chapter 6 项目资源知识目录与知识库索引接入'
type: 'feature'
created: '2026-09-08'
status: 'in-progress'
baseline_commit: '14e2d3297830d6a34382c97a21d962ec3e063440'
review_loop_iteration: 0
context:
  - 'C:/buildgame/newrouge/AGENTS.md'
  - 'C:/buildgame/newrouge/docs/agents/13-rag-sources-and-session-ssot.md'
  - 'C:/buildgame/newrouge/docs/agents/16-directory-responsibilities.md'
  - 'C:/buildgame/newrouge/docs/workflows/project-health-knowledge.md'

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Chapter 6 当前能发现代码、场景、配置和素材关联，但没有稳定的生产目录承载这些关系；知识库因此只能从扫描日志或临时结果推断，无法可靠回答“哪个文件控制什么功能、如何调参或替换素材”。

**Approach:** 在 `docs/knowledge/**` 建立可提交的 schema/catalog，增加 `dev_cli.py` 幂等初始化命令；在 Chapter 6 完成阶段生成并校验任务到配置、素材、场景、代码和测试的轻量关联，再交给现有知识控制面构建索引。Chapter 4/5 不增加统一资源模型约束。

## Boundaries & Constraints

**Always:** 生产知识只写入 `docs/knowledge/**`；`logs/**` 只保存本次运行证据；条目必须带路径、kind、置信度、来源 revision 和 evidence；任务文件只保存 entry id/摘要引用；生成结果必须可重复、可校验、可增量更新；保留 `confirmed|inferred|unverified|removed` 生命周期。

**Ask First:** 若发现现有 Knowledge Control Plane 的 canonical publication 契约与新目录冲突，暂停并保留兼容映射，不自行替换既有 SSoT。

**Never:** 不把完整配置说明或素材说明塞进 `tasks_gameplay.json`；不把生产字典写进 `logs/**`；不强制所有游戏使用相同字段或资源组织；不把推断关系标成 confirmed；不让普通查询请求隐式发布全局知识。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 初始化 | `docs/knowledge` 不存在 | 创建 schema、空 catalog、README 和版本清单 | 已存在文件默认不覆盖，返回结构化结果 |
| 重复初始化 | 目录和文件已存在 | 幂等成功，不改变现有内容 | `--force` 才允许重建，并写证据 |
| Chapter 6 扫描 | 任务、代码、场景、测试和资源路径 | 生成/更新关联条目与 task entry ids | 路径缺失标记 warning/unverified，不伪造关系 |
| 索引校验 | catalog 有重复 id、失效 task 或 evidence | 不推进 current publication | 输出明确校验报告到 logs |

</frozen-after-approval>

## Code Map

- `scripts/python/dev_cli.py` -- 顶层 CLI 子命令注册与 JSON 输出，复用现有 deterministic command 模式。
- `scripts/python/build_knowledge_catalog.py` -- 现有知识目录构建入口；应复用其 publication/校验边界，而不是创建旁路索引。
- `scripts/python/publish_knowledge_catalog.py` -- 现有知识发布、current/LKG 绑定和恢复入口。
- `scripts/python/validate_knowledge_control_plane.py` -- 现有 schema、生成层和发布完整性校验入口。
- `scripts/python/project_health_navigation.py` 与相关导航扫描模块 -- 已有配置、素材、场景、代码关联发现逻辑，应抽取为 Chapter 6 可复用产物。
- `scripts/python/project_health_runtime.py` -- 任务运行证据、revision 和测试引用来源；不得把 logs 当知识 SSoT。
- `docs/agents/13-rag-sources-and-session-ssot.md` -- 知识权威、发布边界和 Chapter 6 查询规则。
- `docs/workflows/project-health-knowledge.md` -- 当前项目健康/知识页面工作流，需要补充 catalog 生命周期。
- `.taskmaster/tasks/tasks_gameplay.json` -- 仅增加轻量 `knowledge_entry_ids`/revision 引用，不承载正文。

## Tasks & Acceptance

**Execution:**
- [x] `docs/knowledge/**` -- 创建 README、schema、catalog/generated 目录和版本清单 -- 固定生产知识边界。
- [x] `scripts/python/dev_cli.py` 与初始化模块 -- 增加 `init-knowledge-catalog`，支持幂等、`--force`、`--validate` 和日志证据 -- 让初始化由确定性 CLI 执行。
- [x] Chapter 6 资源关联生成模块 -- 生成配置/素材/场景/代码/测试条目、置信度和 evidence -- 保留项目特有结构。
- [ ] `build_knowledge_catalog.py`/校验入口 -- 接入新 catalog，拒绝失效引用后再发布 -- 保持现有控制面 SSoT。
- [x] Taskmaster 轻量回写与知识页面 -- 展示 entry id、作用、参数、绑定节点和证据 -- 让机器索引结果可读。
- [x] 相关 Python 测试与 workflow 文档 -- 覆盖初始化、增量更新、失效引用和不写 logs -- 固化边界。

**Acceptance Criteria:**
- Given 空仓库知识目录，when 执行初始化命令，then 生成标准文件且第二次执行不改变内容。
- Given Chapter 6 任务修改了配置或素材，when 资源扫描完成，then `docs/knowledge` 产生带 revision/evidence 的条目，任务只保存引用。
- Given 条目路径或任务 ID 无效，when 执行校验/发布，then publication 不推进并给出可定位错误。
- Given 机器知识查询，when 按任务、配置或素材检索，then 返回作用、关联代码/场景/测试和置信度，不读取 logs 作为事实来源。

## Design Notes

详细资源说明放 catalog；`generated` 只存可再生关系；索引发布沿用现有 Knowledge Control Plane。公共字段保持最小，项目专属字段允许扩展。

## Verification

**Commands:**
- `py -3 scripts/python/dev_cli.py init-knowledge-catalog --validate` -- expected: structured success and valid catalog.
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated` -- expected: no integrity errors.
- `py -3 -m unittest scripts.sc.tests.test_knowledge_*` -- expected: all related tests pass.
- `git diff --check` -- expected: no whitespace errors.
